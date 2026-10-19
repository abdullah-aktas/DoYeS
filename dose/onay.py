"""Belge onay akışı: hazırlama → aşamalı uygun görüş / kontrol → harcama yetkilisi onayı; iade, geri çekme, geri alma.

Onay akışı Kullanıcılar ekranından açılır. Kapalıyken belgeler (eski sürümdeki gibi) tek adımda onaylanır;
her iki durumda da onay geçmişi onay_kaydi tablosunda tutulur.
"""
from __future__ import annotations

from datetime import date, datetime

from . import mevzuat as M
from . import muhasebe
from .db import al
from .denetim import fazla_calisma_denetimi
from .hesap import para, siparis_kaydi_tahsisi
from .yetki import AKISLAR, GERI_ALABILEN

HAZIRLANIYOR, BEKLIYOR, ONAYLANDI, IADE = "Hazırlanıyor", "Onay bekliyor", "Onaylandı", "İade edildi"


class OnayHatasi(Exception):
    pass


def akis_acik() -> bool:
    return str(al().ayar("onay_akisi", "0")) == "1"


def akis_ayarla(acik: bool):
    al().ayar_yaz("onay_akisi", "1" if acik else "0")


# ---------------------------------------------------------------- durum sorguları
def durum(tur: str, bid: int) -> dict:
    r = al().q1("SELECT * FROM onay_durum WHERE belge_turu = ? AND belge_id = ?", (tur, bid))
    if r:
        return r
    eski_onay = KANCALAR[tur]["onayli"](bid)
    return {"belge_turu": tur, "belge_id": bid, "asama": len(AKISLAR[tur]) + 1 if eski_onay else 0,
            "durum": ONAYLANDI if eski_onay else HAZIRLANIYOR, "bolum_id": None, "hazirlayan": None}


def asama_bilgisi(tur: str, asama: int) -> tuple[str, str] | None:
    a = AKISLAR[tur]
    return a[asama - 1] if 1 <= asama <= len(a) else None


def durum_metni(d: dict) -> str:
    if d["durum"] == BEKLIYOR:
        b = asama_bilgisi(d["belge_turu"], d["asama"])
        return f"Bekliyor: {b[1]}" if b else BEKLIYOR
    return d["durum"]


def durumlar(tur: str) -> dict[int, dict]:
    return {r["belge_id"]: r for r in al().q("SELECT * FROM onay_durum WHERE belge_turu = ?", (tur,))}


def gecmis(tur: str, bid: int) -> list[dict]:
    return al().q("SELECT * FROM onay_kaydi WHERE belge_turu = ? AND belge_id = ? ORDER BY id", (tur, bid))


def kullanici_bolumu(k: dict) -> int | None:
    if k.get("bolum_id"):
        return k["bolum_id"]
    if k.get("personel_id"):
        return al().deger("SELECT bolum_id FROM personel WHERE id = ?", (k["personel_id"],), None)
    return None


def _rol_uyar(rol: str, d: dict, k: dict) -> bool:
    if k.get("rol") != rol:
        return False
    if rol == M.ROL_SEF and d.get("bolum_id"):
        return kullanici_bolumu(k) == d["bolum_id"]
    return True


def yetkili_mi(d: dict, k: dict) -> bool:
    """Kullanıcı belgenin bekleyen aşamasında karar verebilir mi?"""
    if d["durum"] != BEKLIYOR:
        return False
    b = asama_bilgisi(d["belge_turu"], d["asama"])
    return bool(b) and _rol_uyar(b[1], d, k)


def _rol_kullanicisi_var(rol: str, bolum_id) -> bool:
    db = al()
    if rol == M.ROL_SEF and bolum_id:
        return bool(db.deger("""SELECT COUNT(*) FROM kullanici k LEFT JOIN personel p ON p.id = k.personel_id
                                WHERE k.aktif = 1 AND k.rol = ? AND COALESCE(k.bolum_id, p.bolum_id) = ?""", (rol, bolum_id), 0))
    return bool(db.deger("SELECT COUNT(*) FROM kullanici WHERE aktif = 1 AND rol = ?", (rol,), 0))


def bekleyenler(k: dict | None = None) -> list[dict]:
    """Onay bekleyen belgeler; kullanıcı verilirse yalnız onun karar vereceği belgeler."""
    sonuc = []
    for d in al().q("SELECT * FROM onay_durum WHERE durum = ? ORDER BY guncelleme", (BEKLIYOR,)):
        if d["belge_turu"] not in AKISLAR or (k is not None and not yetkili_mi(d, k)):
            continue
        d.update(ozet(d["belge_turu"], d["belge_id"]))
        b = asama_bilgisi(d["belge_turu"], d["asama"])
        d["asama_adi"], d["bekleyen_rol"] = b if b else ("", "")
        sonuc.append(d)
    return sonuc


def bekleyen_sayisi(k: dict) -> int:
    return sum(1 for d in al().q("SELECT * FROM onay_durum WHERE durum = ?", (BEKLIYOR,))
               if d["belge_turu"] in AKISLAR and yetkili_mi(d, k))


# ---------------------------------------------------------------- kayıt yardımcıları
def _simdi() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _durum_yaz(tur, bid, asama, durum_, bolum_id=None, hazirlayan=None):
    db = al()
    mevcut = db.q1("SELECT * FROM onay_durum WHERE belge_turu = ? AND belge_id = ?", (tur, bid))
    veri = {"asama": asama, "durum": durum_, "guncelleme": _simdi()}
    if bolum_id is not None:
        veri["bolum_id"] = bolum_id
    if hazirlayan is not None:
        veri["hazirlayan"] = hazirlayan
    if mevcut:
        atama = ", ".join(f"{a} = ?" for a in veri)
        db.ex(f"UPDATE onay_durum SET {atama} WHERE belge_turu = ? AND belge_id = ?", list(veri.values()) + [tur, bid])
    else:
        db.ekle("onay_durum", {"belge_turu": tur, "belge_id": bid, **veri}, log=False)


def _gunluk(tur, bid, asama, asama_adi, karar, k: dict, aciklama=""):
    db = al()
    db.ekle("onay_kaydi", {"belge_turu": tur, "belge_id": bid, "asama": asama, "asama_adi": asama_adi, "karar": karar,
                           "kullanici": k.get("kullanici_adi"), "ad_soyad": k.get("ad_soyad"), "rol": k.get("rol"),
                           "zaman": _simdi(), "aciklama": aciklama or None}, log=False)
    db.log(f"Onay: {karar}", tur, bid, f"{asama_adi} {aciklama or ''}".strip())


def _kanca(tur: str) -> dict:
    return KANCALAR[tur]


def _ilerlet(tur: str, bid: int, k: dict, hazirlayan_mi: bool):
    """Bekleyen aşamadan başlayarak hazırlayanın kendi rolüne ait ve sistemde kullanıcısı olmayan aşamaları geçer;
    son aşama da tamamlanırsa belgeyi kesinleştirir."""
    d = durum(tur, bid)
    asama, n = d["asama"], len(AKISLAR[tur])
    while asama <= n:
        ad, rol = AKISLAR[tur][asama - 1]
        if hazirlayan_mi and _rol_uyar(rol, d, k):
            _gunluk(tur, bid, asama, ad, "Uygun (hazırlayan)", k)
        elif not _rol_kullanicisi_var(rol, d.get("bolum_id")):
            _gunluk(tur, bid, asama, ad, "Atlandı", k, f"Sistemde bu aşama için aktif '{rol}' kullanıcısı yok.")
        else:
            break
        asama += 1
    if asama > n:
        _kanca(tur)["onay"](bid)
        _durum_yaz(tur, bid, n + 1, ONAYLANDI)
    else:
        _durum_yaz(tur, bid, asama, BEKLIYOR)


# ---------------------------------------------------------------- işlemler
def gonder(tur: str, bid: int, k: dict, aciklama: str = ""):
    d = durum(tur, bid)
    if d["durum"] == BEKLIYOR:
        raise OnayHatasi("Belge zaten onay sürecinde.")
    if d["durum"] == ONAYLANDI:
        raise OnayHatasi("Belge onaylanmış.")
    hatalar = _kanca(tur)["kontrol"](bid)
    if hatalar:
        raise OnayHatasi("Belge onaya gönderilemez:\n\n" + "\n".join(hatalar))
    db = al()
    with db.islem():
        _durum_yaz(tur, bid, 1, BEKLIYOR, _kanca(tur)["bolum"](bid) or 0, k.get("ad_soyad") or k.get("kullanici_adi"))
        _gunluk(tur, bid, 0, "Hazırlama", "Onaya gönderildi", k, aciklama)
        _ilerlet(tur, bid, k, hazirlayan_mi=True)


def karar_ver(tur: str, bid: int, k: dict, onay: bool, aciklama: str = ""):
    d = durum(tur, bid)
    if not yetkili_mi(d, k):
        raise OnayHatasi("Bu belgenin bekleyen aşamasında karar yetkiniz bulunmuyor.")
    ad, _rol = asama_bilgisi(tur, d["asama"])
    db = al()
    if not onay:
        if not (aciklama or "").strip():
            raise OnayHatasi("İade gerekçesini yazınız.")
        with db.islem():
            _gunluk(tur, bid, d["asama"], ad, "İade edildi", k, aciklama)
            _durum_yaz(tur, bid, 0, IADE)
        return
    son = d["asama"] == len(AKISLAR[tur])
    if son:
        hatalar = _kanca(tur)["kontrol"](bid)
        if hatalar:
            raise OnayHatasi("Onaylanamaz:\n\n" + "\n".join(hatalar))
    with db.islem():
        _gunluk(tur, bid, d["asama"], ad, "Onaylandı" if son else "Uygun", k, aciklama)
        _durum_yaz(tur, bid, d["asama"] + 1, BEKLIYOR)
        _ilerlet(tur, bid, k, hazirlayan_mi=False)


def geri_cek(tur: str, bid: int, k: dict, aciklama: str = ""):
    """Onay sürecindeki belgeyi düzeltmek için hazırlama aşamasına çeker."""
    d = durum(tur, bid)
    if d["durum"] != BEKLIYOR:
        raise OnayHatasi("Yalnız onay bekleyen belge geri çekilebilir.")
    with al().islem():
        _gunluk(tur, bid, d["asama"], "Hazırlama", "Geri çekildi", k, aciklama)
        _durum_yaz(tur, bid, 0, HAZIRLANIYOR)


def geri_al(tur: str, bid: int, k: dict, aciklama: str = "", yetki_denetle: bool = True):
    """Onaylanmış belgenin onayını kaldırır (muhasebe kayıtları geri alınır)."""
    if yetki_denetle and akis_acik() and k.get("rol") not in GERI_ALABILEN:
        raise OnayHatasi("Onayı yalnız harcama yetkilisi (okul müdürü) veya sistem yöneticisi kaldırabilir.")
    d = durum(tur, bid)
    if d["durum"] != ONAYLANDI and not _kanca(tur)["onayli"](bid):
        raise OnayHatasi("Belge onaylı değil.")
    engel = _kanca(tur)["geri_al_engel"](bid)
    if engel:
        raise OnayHatasi(engel)
    with al().islem():
        _kanca(tur)["geri_al"](bid)
        _gunluk(tur, bid, 0, "Onay kaldırma", "Onay kaldırıldı", k, aciklama)
        _durum_yaz(tur, bid, 0, HAZIRLANIYOR)


def dogrudan_onayla(tur: str, bid: int, k: dict):
    """Onay akışı kapalıyken tek adımda onay (eski davranış)."""
    hatalar = _kanca(tur)["kontrol"](bid)
    if hatalar:
        raise OnayHatasi("Onaylanamaz:\n\n" + "\n".join(hatalar))
    with al().islem():
        _kanca(tur)["onay"](bid)
        _gunluk(tur, bid, len(AKISLAR[tur]), "Doğrudan onay", "Onaylandı", k, "Onay akışı kapalı")
        _durum_yaz(tur, bid, len(AKISLAR[tur]) + 1, ONAYLANDI, _kanca(tur)["bolum"](bid) or 0,
                   k.get("ad_soyad") or k.get("kullanici_adi"))


def sifirla(tur: str, bid: int, k: dict, neden: str):
    """Onaylı veya süreçteki belgede esaslı değişiklik yapıldığında akışı başa döndürür (yan etki üretmez)."""
    d = durum(tur, bid)
    if d["durum"] in (HAZIRLANIYOR,) and not d.get("hazirlayan"):
        return
    with al().islem():
        _gunluk(tur, bid, 0, "Hazırlama", "Akış sıfırlandı", k, neden)
        _durum_yaz(tur, bid, 0, HAZIRLANIYOR)


def sil(tur: str, bid: int):
    db = al()
    db.ex("DELETE FROM onay_durum WHERE belge_turu = ? AND belge_id = ?", (tur, bid))


# ---------------------------------------------------------------- belge türleri
def _ay(ay) -> str:
    return M.AYLAR[int(ay) - 1] if ay else ""


# --- sipariş
def _siparis_kontrol(bid):
    db = al()
    s = db.q1("SELECT * FROM siparis WHERE id = ?", (bid,))
    if not s:
        return ["Sipariş bulunamadı."]
    h = []
    if not db.deger("SELECT COUNT(*) FROM siparis_kalem WHERE siparis_id = ?", (bid,), 0):
        h.append("Siparişte kalem yok.")
    if s.get("durum") == "İptal":
        h.append("İptal edilmiş sipariş onaya gönderilemez.")
    p = db.parametreler(int((s.get("tarih") or str(date.today().year))[:4]))
    h += siparis_kaydi_tahsisi(s, p).hatalar
    return h


def _siparis_onay(bid):
    db = al()
    if db.deger("SELECT durum FROM siparis WHERE id = ?", (bid,), "") == "Teklif":
        db.guncelle("siparis", bid, {"durum": "Sözleşme İmzalandı"})


def _siparis_engel(bid):
    db = al()
    if db.deger("SELECT COUNT(*) FROM fatura WHERE siparis_id = ? AND iptal = 0", (bid,), 0) or \
            db.deger("SELECT COUNT(*) FROM parca_basi WHERE siparis_id = ?", (bid,), 0):
        return "Siparişe bağlı fatura veya parça başı bordrosu var; onay kaldırılamaz."
    return None


def _siparis_geri_al(bid):
    db = al()
    if db.deger("SELECT durum FROM siparis WHERE id = ?", (bid,), "") == "Sözleşme İmzalandı":
        db.guncelle("siparis", bid, {"durum": "Teklif"})


def _siparis_ozet(bid):
    s = al().q1("""SELECT s.siparis_no, s.konu, s.sozlesme_bedeli, b.ad bolum_ad FROM siparis s
                   LEFT JOIN bolum b ON b.id = s.bolum_id WHERE s.id = ?""", (bid,)) or {}
    return {"no": s.get("siparis_no"), "konu": s.get("konu"), "tutar": s.get("sozlesme_bedeli"), "bolum_ad": s.get("bolum_ad")}


# --- parça başı
def parca_basi_kontrol(bid) -> list[str]:
    db = al()
    pb = db.q1("SELECT * FROM parca_basi WHERE id = ?", (bid,))
    if not pb:
        return ["Bordro bulunamadı."]
    h = []
    if not db.deger("SELECT COUNT(*) FROM parca_basi_satir WHERE parca_basi_id = ?", (bid,), 0):
        h.append("Bordroda kişi yok.")
    p = db.parametreler(pb["yil"])
    if (pb["ogrenci_orani"] or 0) + 1e-9 < p["ogrenci_hakki_orani"]:
        h.append(f"Öğrenci hakkı oranı asgari %{p['ogrenci_hakki_orani'] * 100:.0f}'in altında (Yön. md.8/3).")
    eksik = db.q("""SELECT o.ad_soyad FROM parca_basi_satir r JOIN ogrenci o ON o.id = r.kisi_id
                    WHERE r.parca_basi_id = ? AND r.kisi_turu = 'Öğrenci' AND COALESCE(o.veli_muvafakat, 0) = 0""", (bid,))
    if eksik:
        h.append("Veli muvafakatnamesi olmayan öğrenci(ler) var (Yön. md.8/1): " + ", ".join(e["ad_soyad"] for e in eksik))
    cakisma = db.q("""SELECT DISTINCT p.ad_soyad FROM parca_basi_satir r JOIN personel p ON p.id = r.kisi_id
                      JOIN fazla_calisma f ON f.personel_id = r.kisi_id AND f.siparis_id = ?
                      WHERE r.parca_basi_id = ? AND r.kisi_turu = 'Personel'""", (pb["siparis_id"], bid))
    if cakisma:
        h.append("Aynı iş için fazla çalışma ücreti kaydı bulunan personel var (Yön. md.8/7): "
                 + ", ".join(c["ad_soyad"] for c in cakisma))
    s = db.q1("SELECT * FROM siparis WHERE id = ?", (pb["siparis_id"],))
    if s:
        if not s["kabul_tarihi"] and s["durum"] not in ("Tamamlandı (Geçici Kabul)", "Faturalandı", "Kapandı"):
            h.append("Siparişin geçici muayene ve kabulü yapılmamış; parça başı ücret yalnız ay içinde bitirilen ve geçici "
                     "muayene ve kabulü yapılan işin işçiliğinden ödenir (Yön. md.8/8-a).")
        iscilik = siparis_kaydi_tahsisi(dict(s), p).iscilik
        dagitilan = db.deger("SELECT SUM(kabul_edilen_iscilik) FROM parca_basi WHERE siparis_id = ?", (s["id"],), 0.0) or 0.0
        if dagitilan > iscilik + 0.009:
            h.append(f"Siparişte dağıtılan işçilik toplamı ({para(dagitilan)} TL) siparişin işçilik tutarını ({para(iscilik)} TL) "
                     "aşıyor (Yön. md.8/4).")
    return h


def _pb_onay(bid):
    al().guncelle("parca_basi", bid, {"durum": "Onaylandı", "onay_tarihi": date.today().isoformat()})
    muhasebe.parca_basi_kaydi(bid)


def _pb_engel(bid):
    if al().deger("SELECT COUNT(*) FROM kasa_banka WHERE kaynak = 'ParcaBasi' AND kaynak_id = ?", (bid,), 0):
        return "Bordroya ait ödeme kaydı var; önce kasa/banka kaydını siliniz."
    return None


def _pb_geri_al(bid):
    al().guncelle("parca_basi", bid, {"durum": "Taslak", "onay_tarihi": None})
    muhasebe.parca_basi_kaydi(bid)


def _pb_ozet(bid):
    r = al().q1("""SELECT pb.yil, pb.ay, s.siparis_no, s.konu, b.ad bolum_ad,
                          (SELECT SUM(brut) FROM parca_basi_satir WHERE parca_basi_id = pb.id) brut
                   FROM parca_basi pb LEFT JOIN siparis s ON s.id = pb.siparis_id LEFT JOIN bolum b ON b.id = s.bolum_id
                   WHERE pb.id = ?""", (bid,)) or {}
    return {"no": f"{r.get('siparis_no') or ''} / {_ay(r.get('ay'))} {r.get('yil') or ''}", "konu": r.get("konu"),
            "tutar": r.get("brut"), "bolum_ad": r.get("bolum_ad")}


# --- fazla çalışma (kişi-ay kaydı)
def _fc_kontrol(bid):
    f = al().q1("SELECT * FROM fazla_calisma WHERE id = ?", (bid,))
    if not f:
        return ["Kayıt bulunamadı."]
    return fazla_calisma_denetimi(al(), f, f["id"])[0]


def _fc_bolum(bid):
    return al().deger("""SELECT COALESCE(s.bolum_id, p.bolum_id) FROM fazla_calisma f JOIN personel p ON p.id = f.personel_id
                         LEFT JOIN siparis s ON s.id = f.siparis_id WHERE f.id = ?""", (bid,), None)


def _fc_onay(bid):
    db = al()
    f = db.q1("SELECT yil, ay FROM fazla_calisma WHERE id = ?", (bid,))
    db.guncelle("fazla_calisma", bid, {"durum": "Onaylandı"})
    muhasebe.fazla_calisma_kaydi(f["yil"], f["ay"])


def _fc_engel(bid):
    db = al()
    f = db.q1("SELECT yil, ay FROM fazla_calisma WHERE id = ?", (bid,))
    if f and db.deger("SELECT COUNT(*) FROM kasa_banka WHERE kaynak = 'FazlaCalisma' AND kaynak_id = ?",
                      (f["yil"] * 100 + f["ay"],), 0):
        return "Bu aya ait fazla çalışma ödeme kaydı var; önce kasa/banka kaydını siliniz."
    return None


def _fc_geri_al(bid):
    db = al()
    f = db.q1("SELECT yil, ay FROM fazla_calisma WHERE id = ?", (bid,))
    db.guncelle("fazla_calisma", bid, {"durum": "Taslak"})
    muhasebe.fazla_calisma_kaydi(f["yil"], f["ay"])


def _fc_ozet(bid):
    r = al().q1("""SELECT f.yil, f.ay, f.saat, f.brut, p.ad_soyad, s.siparis_no, b.ad bolum_ad
                   FROM fazla_calisma f JOIN personel p ON p.id = f.personel_id LEFT JOIN siparis s ON s.id = f.siparis_id
                   LEFT JOIN bolum b ON b.id = COALESCE(s.bolum_id, p.bolum_id) WHERE f.id = ?""", (bid,)) or {}
    return {"no": f"{r.get('ad_soyad') or ''} / {_ay(r.get('ay'))} {r.get('yil') or ''}",
            "konu": f"{(r.get('saat') or 0):g} saat" + (f" ({r['siparis_no']})" if r.get("siparis_no") else ""),
            "tutar": r.get("brut"), "bolum_ad": r.get("bolum_ad")}


# --- yıl sonu kâr dağıtımı (belge_id = yıl)
def _ys_kontrol(yil):
    db = al()
    if not db.q1("SELECT yil FROM yil_sonu WHERE yil = ?", (yil,)):
        return ["Yıl sonu dağıtımı kaydedilmemiş."]
    return []


def _ys_onay(yil):
    db = al()
    db.guncelle("yil_sonu", yil, {"durum": "Onaylandı"}, anahtar="yil")
    muhasebe.utp_kaydi(yil)
    shcek = db.deger("SELECT shcek FROM yil_sonu WHERE yil = ?", (yil,), 0)
    if shcek:
        muhasebe.shcek_kaydi(yil, shcek)


def _ys_geri_al(yil):
    al().guncelle("yil_sonu", yil, {"durum": "Taslak"}, anahtar="yil")
    muhasebe.fis_sil("UTP", yil)
    muhasebe.fis_sil("SHCEK", yil)


def _ys_ozet(yil):
    r = al().q1("SELECT dagitilan_utp FROM yil_sonu WHERE yil = ?", (yil,)) or {}
    return {"no": f"{yil} yılı", "konu": "Yıl sonu kâr dağıtımı ve ÜTP", "tutar": r.get("dagitilan_utp"), "bolum_ad": ""}


def _onayli(tablo, anahtar="id"):
    return lambda bid: al().deger(f"SELECT durum FROM {tablo} WHERE {anahtar} = ?", (bid,), "") == "Onaylandı"


KANCALAR = {
    "Sipariş": {"kontrol": _siparis_kontrol, "bolum": lambda b: al().deger("SELECT bolum_id FROM siparis WHERE id = ?", (b,), None),
                "onay": _siparis_onay, "geri_al_engel": _siparis_engel, "geri_al": _siparis_geri_al, "ozet": _siparis_ozet,
                "onayli": lambda b: al().deger("SELECT durum FROM siparis WHERE id = ?", (b,), "Teklif") not in ("Teklif", "İptal")},
    "Parça Başı": {"kontrol": parca_basi_kontrol, "onay": _pb_onay, "geri_al_engel": _pb_engel, "geri_al": _pb_geri_al,
                   "bolum": lambda b: al().deger("SELECT s.bolum_id FROM parca_basi pb JOIN siparis s ON s.id = pb.siparis_id "
                                                 "WHERE pb.id = ?", (b,), None),
                   "ozet": _pb_ozet, "onayli": _onayli("parca_basi")},
    "Fazla Çalışma": {"kontrol": _fc_kontrol, "bolum": _fc_bolum, "onay": _fc_onay, "geri_al_engel": _fc_engel,
                      "geri_al": _fc_geri_al, "ozet": _fc_ozet, "onayli": _onayli("fazla_calisma")},
    "Yıl Sonu": {"kontrol": _ys_kontrol, "bolum": lambda y: None, "onay": _ys_onay, "geri_al_engel": lambda y: None,
                 "geri_al": _ys_geri_al, "ozet": _ys_ozet, "onayli": _onayli("yil_sonu", "yil")},
}


def ozet(tur: str, bid: int) -> dict:
    try:
        return KANCALAR[tur]["ozet"](bid)
    except Exception:
        return {"no": str(bid), "konu": "", "tutar": None, "bolum_ad": ""}
