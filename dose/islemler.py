"""Masaüstü ve mobil ortak kayıt işlemleri: fazla çalışma kaydı ve sipariş taslağı (iş talebi)."""
from __future__ import annotations

from datetime import date

from . import mevzuat as M
from .denetim import fazla_calisma_denetimi, puantaj_coz, puantaj_yaz
from .hesap import (esas_kurallari, kalem_hatalari, kalem_tutari, para, siparis_kaydi_tahsisi, ucret_kesintileri,
                    yasal_ust_sinir_iscilik, yuvarla)

MALZEME_UNSURLARI = ("Direkt İlk Madde ve Malzeme", "Ambalaj / Etiket")


class IslemHatasi(ValueError):
    pass


# ---------------------------------------------------------------- fazla çalışma
def fc_onceki_kumulatif(db, yil: int, ay: int, personel_id: int) -> float:
    """Personelin yıl içinde önceki aylarda döner sermayeden aldığı parça başı ve fazla çalışma brütü (GV matrahı)."""
    pb = db.deger("""SELECT SUM(r.brut) FROM parca_basi_satir r JOIN parca_basi p ON p.id = r.parca_basi_id
                     WHERE p.yil = ? AND p.ay < ? AND r.kisi_turu = 'Personel' AND r.kisi_id = ?""", (yil, ay, personel_id), 0.0)
    fc = db.deger("SELECT SUM(brut) FROM fazla_calisma WHERE yil = ? AND ay < ? AND personel_id = ?", (yil, ay, personel_id), 0.0)
    return yuvarla((pb or 0) + (fc or 0))


def fc_odeme_var(db, yil: int, ay: int) -> bool:
    return bool(db.deger("SELECT COUNT(*) FROM kasa_banka WHERE kaynak = 'FazlaCalisma' AND kaynak_id = ?", (yil * 100 + ay,), 0))


def fc_hesapla(db, v: dict, kid: int | None = None, p: dict | None = None):
    """v: yil, ay, personel_id, siparis_id, saat, saat_ucreti, puantaj, onceki_kumulatif.
    (kayda yazılacak değerler, hatalar, uyarılar) döndürür."""
    yil, ay = int(v["yil"]), int(v["ay"])
    p = p or db.parametreler(yil)
    puantaj = puantaj_coz(v.get("puantaj"))
    saat = yuvarla(sum(puantaj.values()), 2) if puantaj else float(v.get("saat") or 0)
    ucret = float(v.get("saat_ucreti") or p["fazla_calisma_saat_ucreti"] or 0)
    pid = v.get("personel_id")
    onceki = v.get("onceki_kumulatif")
    if onceki is None:
        onceki = fc_onceki_kumulatif(db, yil, ay, pid) if pid else 0.0
    kayit = {"yil": yil, "ay": ay, "personel_id": pid, "siparis_id": v.get("siparis_id") or None, "saat": saat,
             "saat_ucreti": ucret, "puantaj": puantaj_yaz(puantaj)}
    brut = yuvarla(saat * ucret)
    k = ucret_kesintileri(brut, onceki, ay, p)
    hatalar = []
    if not pid:
        hatalar.append("Personel seçilmemiş.")
    if not ucret:
        hatalar.append("Saat ücreti girilmemiş. Parametreler sayfasında güncel fazla çalışma saat ücretini tanımlayınız.")
    h, uyarilar = fazla_calisma_denetimi(db, kayit, kid, p)
    hatalar += h
    if fc_odeme_var(db, yil, ay):
        hatalar.append("Bu ayın fazla çalışma ödeme kaydı oluşturulmuş; kayıt eklenemez veya değiştirilemez.")
    kayit.update({"brut": brut, "onceki_kumulatif": onceki, "gelir_vergisi": k.gelir_vergisi,
                  "damga_vergisi": k.damga_vergisi, "net": k.net, "aciklama": (v.get("aciklama") or "").strip() or None,
                  "durum": "Taslak"})
    return kayit, hatalar, uyarilar


# ---------------------------------------------------------------- sipariş taslağı
def kart_malzemesi(db, kalemler: list[dict]) -> float:
    """Kalemlerdeki ürünlerin maliyet kartındaki malzeme ve ambalaj giderleri × miktar."""
    toplam = 0.0
    for k in kalemler:
        if k.get("urun_id"):
            birim = db.deger(f"SELECT SUM(miktar * birim_fiyat) FROM maliyet_kalem WHERE urun_id = ? AND kalem_turu IN "
                             f"({', '.join('?' for _ in MALZEME_UNSURLARI)})", (k["urun_id"], *MALZEME_UNSURLARI), 0.0)
            toplam += (birim or 0) * (k.get("miktar") or 0)
    return yuvarla(toplam)


def siparis_taslagi_kaydet(db, veri: dict, bolum_kisiti: int | None = None) -> tuple[int, str, list[str]]:
    """Mobilden gelen iş talebini 'Teklif' durumunda sipariş olarak kaydeder. Malzeme maliyet kartından, işçilik yasal
    üst sınırdan hesaplanır. (sipariş id, sipariş no, uyarılar) döndürür; kayda engel hata varsa IslemHatasi verir."""
    tarih = veri.get("tarih") or date.today().isoformat()
    p = db.parametreler(int(tarih[:4]))
    hatalar, kalemler = [], []
    for i, k in enumerate(veri.get("kalemler") or [], 1):
        u = db.q1("SELECT * FROM urun WHERE id = ? AND aktif = 1", (k.get("urun_id"),)) if k.get("urun_id") else None
        if k.get("urun_id") and not u:
            hatalar.append(f"{i}. kalem: ürün bulunamadı.")
            continue
        kl = {"urun_id": k.get("urun_id"), "aciklama": (k.get("aciklama") or "").strip() or None,
              "miktar": float(k.get("miktar") or 0), "birim": k.get("birim") or (u["birim"] if u else None) or "Adet",
              "birim_fiyat": float(k["birim_fiyat"]) if k.get("birim_fiyat") is not None else float((u or {}).get("satis_fiyati") or 0),
              "iskonto_orani": float(k.get("iskonto_orani") or 0)}
        kl["iskonto"] = kalem_tutari(kl)[1]
        kalemler.append(kl)
    if not kalemler and not hatalar:
        hatalar.append("En az bir kalem giriniz.")
    hatalar += kalem_hatalari(kalemler)
    bolum_id = veri.get("bolum_id") or bolum_kisiti
    if bolum_kisiti and bolum_id != bolum_kisiti:
        hatalar.append("Yalnız kendi bölümünüz için iş talebi girebilirsiniz.")
    konu = (veri.get("konu") or "").strip()
    if not konu and kalemler and kalemler[0]["urun_id"]:
        konu = db.deger("SELECT ad FROM urun WHERE id = ?", (kalemler[0]["urun_id"],), "")
    for ad, deger in (("Müşteri", veri.get("cari_id")), ("Bölüm", bolum_id), ("İşin konusu", konu)):
        if not deger:
            hatalar.append(f"{ad} zorunludur.")
    esas = veri.get("ucret_esasi") or M.UCRET_ESASLARI[0]
    if esas not in M.UCRET_ESASLARI:
        hatalar.append("Ücret esası geçersiz.")
    if hatalar:
        raise IslemHatasi("\n".join(hatalar))

    v = {"tarih": tarih, "cari_id": veri["cari_id"], "bolum_id": bolum_id, "konu": konu, "ucret_esasi": esas,
         "sozlesme_bedeli": yuvarla(sum(kalem_tutari(k)[2] for k in kalemler)), "kdv_orani": p["kdv_genel"],
         "pesinat": 0.0, "baslama_tarihi": None, "teslim_tarihi": veri.get("teslim_tarihi") or None, "kabul_tarihi": None,
         "durum": "Teklif", "ogrenci_uygulamasi": 1, "malzeme_musteriden": 1 if esas.startswith(("Özel", "Tesis")) else 0,
         "kar_orani": esas_kurallari(esas, p)["kar"], "faaliyet_orani": None,
         "malzeme_maliyeti": kart_malzemesi(db, kalemler), "ogrenci_hakki_orani": p["ogrenci_hakki_orani"],
         "sozlesme_suresi_ay": 0, "bakanlik_izni": 0, "aciklama": (veri.get("aciklama") or "").strip() or None}
    v["iscilik_tutari"] = yasal_ust_sinir_iscilik(v, p)
    t = siparis_kaydi_tahsisi(v, p)
    uyarilar = list(t.hatalar) + list(t.uyarilar)
    if not v["malzeme_maliyeti"] and not v["malzeme_musteriden"]:
        uyarilar.append("Ürünlerin maliyet kartında malzeme yok; malzeme maliyeti 0 alındı. Masaüstünde siparişi açıp "
                        "malzeme tutarını kontrol ediniz.")
    for k in kalemler:
        u = db.q1("SELECT ad, satis_fiyati FROM urun WHERE id = ?", (k["urun_id"],)) if k["urun_id"] else None
        net = yuvarla(kalem_tutari(k)[2] / k["miktar"], 4) if k["miktar"] else 0
        if u and (u["satis_fiyati"] or 0) > 0 and net + 0.005 < u["satis_fiyati"]:
            uyarilar.append(f"'{u['ad']}' birim fiyatı ({para(net)} TL) tespit edilen satış fiyatının ({para(u['satis_fiyati'])} TL) "
                            "altında; işletme aleyhine müşteri lehine indirim yapılamaz (Çalışma Yönergesi md.26/g, md.29/a).")
    with db.islem():
        v["siparis_no"] = db.sonraki_no("siparis", int(tarih[:4]), "SIP")
        sid = db.ekle("siparis", v)
        for k in kalemler:
            db.ekle("siparis_kalem", dict(k, siparis_id=sid), log=False)
    return sid, v["siparis_no"], uyarilar
