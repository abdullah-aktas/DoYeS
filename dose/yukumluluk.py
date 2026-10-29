"""KDV, muhtasar ve hazine payı yükümlülüklerinin ortak hesaplamaları."""
from __future__ import annotations

from datetime import date

from . import mevzuat, muhasebe
from .hesap import son_odeme_tarihleri, yuvarla


def _ay_verisi(db, yil: int, ay: int) -> dict:
    donem = f"{yil}-{ay:02d}"
    sorgu = lambda sql: db.deger(sql, (donem,), 0.0)
    hesaplanan = sorgu(
        "SELECT SUM(kdv - tevkif_kdv) FROM fatura WHERE tur = 'Satış' AND iptal = 0 AND substr(tarih, 1, 7) = ?")
    indirilecek = sorgu(
        "SELECT SUM(kdv) FROM fatura WHERE tur = 'Alış' AND iptal = 0 AND substr(tarih, 1, 7) = ?")
    tevkifat = sorgu(
        "SELECT SUM(tevkif_kdv) FROM fatura WHERE tur = 'Alış' AND iptal = 0 AND substr(tarih, 1, 7) = ?")
    stopaj = sorgu(
        "SELECT SUM(stopaj) FROM fatura WHERE tur = 'Alış' AND iptal = 0 AND substr(tarih, 1, 7) = ?")
    satis_matrah = sorgu(
        "SELECT SUM(matrah) FROM fatura WHERE tur = 'Satış' AND iptal = 0 AND substr(tarih, 1, 7) = ?")
    parca = db.q1("""SELECT SUM(r.gelir_vergisi) gv, SUM(r.damga_vergisi) dv, SUM(r.brut) brut
                     FROM parca_basi_satir r JOIN parca_basi p ON p.id = r.parca_basi_id
                     WHERE p.durum = 'Onaylandı' AND p.yil = ? AND p.ay = ?""", (yil, ay)) or {}
    fazla = db.q1("""SELECT SUM(gelir_vergisi) gv, SUM(damga_vergisi) dv, SUM(brut) brut
                     FROM fazla_calisma WHERE durum = 'Onaylandı' AND yil = ? AND ay = ?""", (yil, ay)) or {}
    return {
        "satis_matrah": yuvarla(satis_matrah),
        "hesaplanan": yuvarla(hesaplanan),
        "indirilecek": yuvarla(indirilecek),
        "tevkifat": yuvarla(tevkifat),
        "stopaj": yuvarla(stopaj),
        "ucret_brut": yuvarla((parca.get("brut") or 0) + (fazla.get("brut") or 0)),
        "ucret_gv": yuvarla((parca.get("gv") or 0) + (fazla.get("gv") or 0)),
        "ucret_dv": yuvarla((parca.get("dv") or 0) + (fazla.get("dv") or 0)),
    }


def kdv_muhtasar_ozeti(db, yil: int) -> list[dict]:
    devreden = 0.0
    satirlar = []
    for ay in range(1, 13):
        veri = _ay_verisi(db, yil, ay)
        fark = yuvarla(veri["hesaplanan"] - veri["indirilecek"] - devreden)
        odenecek = max(fark, 0.0)
        devreden = max(-fark, 0.0)
        son_tarihler = son_odeme_tarihleri(yil, ay)
        veri.update({
            "ay": ay, "ay_ad": mevzuat.AYLAR[ay - 1],
            "odenecek_kdv": yuvarla(odenecek), "devreden": yuvarla(devreden),
            "muhtasar": yuvarla(veri["stopaj"] + veri["ucret_gv"] + veri["ucret_dv"]),
            "kdv_son": son_tarihler["KDV beyan"].isoformat(),
            "muhtasar_son": son_tarihler["Muhtasar beyan"].isoformat(),
        })
        satirlar.append(veri)
    return satirlar


def muhtasar_detayi(db, yil: int, ay: int) -> list[dict]:
    donem = f"{yil}-{ay:02d}"
    satirlar = db.q("""SELECT f.tarih, f.belge_turu, f.belge_no, c.unvan, c.vkn_tckn,
                              f.stopaj_turu tur, f.matrah, f.stopaj tutar
                       FROM fatura f LEFT JOIN cari c ON c.id = f.cari_id
                       WHERE f.tur = 'Alış' AND f.iptal = 0 AND f.stopaj > 0
                         AND substr(f.tarih, 1, 7) = ? ORDER BY f.tarih, f.id""", (donem,))
    bordrolar = db.q("""SELECT pb.id, s.siparis_no, SUM(r.brut) brut, SUM(r.gelir_vergisi) gv,
                               SUM(r.damga_vergisi) dv
                        FROM parca_basi pb JOIN parca_basi_satir r ON r.parca_basi_id = pb.id
                        LEFT JOIN siparis s ON s.id = pb.siparis_id
                        WHERE pb.durum = 'Onaylandı' AND pb.yil = ? AND pb.ay = ?
                        GROUP BY pb.id, s.siparis_no""", (yil, ay))
    for bordro in bordrolar:
        satirlar.append({
            "tarih": f"{donem}-28", "belge_turu": "Parça başı bordro",
            "belge_no": bordro["siparis_no"], "unvan": "Personel/öğrenci", "vkn_tckn": "",
            "tur": "Ücret GV + DV", "matrah": bordro["brut"],
            "tutar": yuvarla((bordro["gv"] or 0) + (bordro["dv"] or 0)),
        })
    fazla = db.q1("""SELECT SUM(brut) brut, SUM(gelir_vergisi) gv, SUM(damga_vergisi) dv
                     FROM fazla_calisma WHERE durum = 'Onaylandı' AND yil = ? AND ay = ?""", (yil, ay))
    if fazla and fazla["brut"]:
        satirlar.append({
            "tarih": f"{donem}-28", "belge_turu": "Fazla çalışma bordrosu", "belge_no": "",
            "unvan": "Personel", "vkn_tckn": "", "tur": "Ücret GV + DV",
            "matrah": fazla["brut"],
            "tutar": yuvarla((fazla["gv"] or 0) + (fazla["dv"] or 0)),
        })
    return satirlar


def hazine_yukumlulukleri(db, yil: int) -> dict:
    parametreler = db.parametreler(yil)
    kayitlar = {row["ay"]: row for row in db.q("SELECT * FROM hazine_payi WHERE yil = ?", (yil,))}
    bugun = date.today()
    aylik = []
    for ay in range(1, 13):
        kayit = kayitlar.get(ay, {})
        son = son_odeme_tarihleri(yil, ay)["Hazine payı"]
        guncel = muhasebe.aylik_tahsil_edilen_hasilat(yil, ay)
        odeme = (db.q1("SELECT * FROM kasa_banka WHERE kaynak = ? AND kaynak_id = ? ORDER BY tarih LIMIT 1",
                       ("HazinePayi", kayit["id"])) if kayit else None)
        sifir_bildirim = bool(kayit) and not kayit.get("tutar") and bool(kayit.get("bildirim_tarihi"))
        durum = ("Ödendi" if odeme else ("Bildirildi (tutar yok)" if sifir_bildirim else
                                        (kayit.get("durum") or ("Hesaplanmadı" if date(yil, ay, 1) <= bugun else "-"))))
        gecikme = ""
        if not odeme and not sifir_bildirim and son < bugun and date(yil, ay, 1) <= bugun:
            gecikme = f"{(bugun - son).days} gün gecikti"
        elif odeme and odeme["tarih"] > son.isoformat():
            gecikme = f"{(date.fromisoformat(odeme['tarih']) - son).days} gün geç ödendi"
        fark = bool(kayit) and abs((kayit.get("tahsil_edilen") or 0) - guncel) > 0.009
        aylik.append({
            "id": kayit.get("id"), "ay": ay, "ay_ad": mevzuat.AYLAR[ay - 1],
            "guncel": guncel, "tahsil_edilen": kayit.get("tahsil_edilen"),
            "oran": kayit.get("oran") or parametreler["hazine_payi_orani"],
            "tutar": kayit.get("tutar") if kayit else yuvarla(guncel * parametreler["hazine_payi_orani"]),
            "son": son.isoformat(), "bildirim_tarihi": kayit.get("bildirim_tarihi"),
            "odeme_tarihi": odeme["tarih"] if odeme else kayit.get("odeme_tarihi"),
            "durum": durum, "gecikme": gecikme,
            "fark": "Tahsilat değişti, yeniden hesaplayın" if fark else "",
        })

    yillik_hasilat = muhasebe.yillik_brut_hasilat(yil)
    shcek_tutar = yuvarla(yillik_hasilat * parametreler["shcek_orani"])
    shcek_odeme = db.q1("SELECT * FROM kasa_banka WHERE kaynak = ? AND kaynak_id = ? ORDER BY tarih LIMIT 1",
                        ("SHCEK", yil))
    yil_sonu = db.q1("SELECT * FROM yil_sonu WHERE yil = ?", (yil,))
    merkez_odeme = db.q1("SELECT * FROM kasa_banka WHERE kaynak = ? AND kaynak_id = ? ORDER BY tarih LIMIT 1",
                         ("MerkezKar", yil))
    return {
        "yil": yil, "aylik": aylik,
        "shcek": {"hasilat": yillik_hasilat, "oran": parametreler["shcek_orani"], "tutar": shcek_tutar,
                  "son": f"{yil + 1}-01-31", "odeme_tarihi": shcek_odeme["tarih"] if shcek_odeme else None},
        "merkez": {
            "dagitim_var": bool(yil_sonu), "durum": yil_sonu.get("durum") if yil_sonu else None,
            "tutar": yil_sonu.get("merkez_payi") if yil_sonu else None,
            "odeme_tarihi": merkez_odeme["tarih"] if merkez_odeme else None,
            "ad": mevzuat.MERKEZ_SAYMANLIK["ad"], "vkn": mevzuat.MERKEZ_SAYMANLIK["vkn"],
            "iban": mevzuat.MERKEZ_SAYMANLIK["iban"],
        },
    }


def tablo_disa_aktar(baslik: str, ad: str, kolonlar: list[dict], satirlar: list[dict],
                     bicim: str) -> tuple[str, bytes]:
    import tempfile
    from pathlib import Path

    from . import belgeler, excel

    basliklar = [kolon["baslik"] for kolon in kolonlar]
    veriler = [[gorunum_degeri(row.get(kolon["anahtar"]), kolon["tur"]) for kolon in kolonlar]
               for row in satirlar]
    with tempfile.TemporaryDirectory(prefix="dose-yukumluluk-") as dizin:
        if bicim == "xlsx":
            yol = excel.disa_aktar(Path(dizin) / f"{ad}.xlsx", [(ad, basliklar, veriler)], baslik)
            return f"{ad}.xlsx", yol.read_bytes()
        if bicim == "pdf":
            sayisal = {i for i, kolon in enumerate(kolonlar) if kolon["tur"] in ("para", "sayi")}
            toplam = [yuvarla(sum(row.get(kolon["anahtar"]) or 0 for row in satirlar))
                      if kolon["tur"] == "para" else "" for kolon in kolonlar]
            if toplam and any(kolon["tur"] == "para" for kolon in kolonlar):
                toplam[0] = "TOPLAM"
            yol = belgeler.genel_liste(
                Path(dizin) / f"{ad}.pdf", baslik, basliklar, veriler, sayisal,
                toplam if any(kolon["tur"] == "para" for kolon in kolonlar) else None,
                yatay=len(kolonlar) > 6)
            return f"{ad}.pdf", yol.read_bytes()
    raise ValueError(f"Desteklenmeyen dışa aktarma biçimi: {bicim}")


def gorunum_degeri(deger, tur: str):
    if deger is None:
        return ""
    if tur == "tarih":
        try:
            from datetime import datetime
            return datetime.strptime(str(deger)[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
        except ValueError:
            return str(deger)
    if tur == "bool":
        return "Evet" if deger else "Hayır"
    if tur == "oran":
        return f"{float(deger):.2%}"
    if tur == "para":
        return yuvarla(deger)
    return deger


VERGI_KOLONLARI = [
    ("ay_ad", "Ay", "metin"), ("satis_matrah", "Satış matrahı", "para"),
    ("hesaplanan", "Hesaplanan KDV", "para"), ("indirilecek", "İndirilecek KDV", "para"),
    ("odenecek_kdv", "Ödenecek KDV (1 No.)", "para"), ("devreden", "Devreden KDV", "para"),
    ("tevkifat", "Sorumlu sıfatıyla KDV (2 No.)", "para"), ("kdv_son", "KDV son gün", "tarih"),
    ("stopaj", "Stopaj (müstahsil/SM)", "para"), ("ucret_gv", "Ücret GV", "para"),
    ("ucret_dv", "Ücret DV", "para"), ("muhtasar", "Muhtasar toplam", "para"),
    ("muhtasar_son", "Muhtasar son gün", "tarih"),
]

HAZINE_KOLONLARI = [
    ("ay_ad", "Ay", "metin"), ("guncel", "Tahsil edilen hasılat (güncel)", "para"),
    ("tahsil_edilen", "Bildirilen matrah", "para"), ("oran", "Oran", "oran"),
    ("tutar", "Hazine payı", "para"), ("son", "Son gün", "tarih"),
    ("bildirim_tarihi", "Bildirim", "tarih"), ("odeme_tarihi", "Ödeme", "tarih"),
    ("durum", "Durum", "metin"), ("gecikme", "Gecikme", "metin"), ("fark", "Uyarı", "metin"),
]
