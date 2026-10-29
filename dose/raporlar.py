"""Masaüstü ve API tarafından paylaşılan yönetim raporu verileri."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from . import mevzuat, muhasebe
from .hesap import esas_kurallari, yuvarla
from .yonerge_raporlari import IDARI_GIDERLER, idari_masraf_karsiligi, uc_aylik_faaliyet


def _kolonlar(*alanlar: tuple[str, str, str]) -> list[dict[str, str]]:
    return [{"anahtar": anahtar, "baslik": baslik, "tur": tur} for anahtar, baslik, tur in alanlar]


def _siparis(db, yil: int) -> list[dict]:
    satirlar = db.q("""SELECT s.id, s.siparis_no, s.tarih, c.unvan, s.konu, s.ucret_esasi, s.durum, s.sozlesme_bedeli,
               COALESCE((SELECT SUM(matrah) FROM fatura f WHERE f.siparis_id = s.id AND f.iptal = 0 AND f.tur = 'Satış'), 0) faturalanan,
               COALESCE((SELECT SUM(tutar) FROM kasa_banka k WHERE k.yon = 'Giriş' AND (k.siparis_id = s.id OR k.fatura_id IN
                        (SELECT id FROM fatura WHERE siparis_id = s.id AND iptal = 0))), 0) tahsil,
               COALESCE((SELECT SUM(miktar * birim_fiyat) FROM stok_hareket h WHERE h.siparis_id = s.id AND h.yon = 'Çıkış'
                         AND h.kaynak != 'Fatura'), 0) malzeme,
               COALESCE((SELECT SUM(matrah) FROM fatura f WHERE f.siparis_id = s.id AND f.iptal = 0 AND f.tur = 'Alış'
                         AND f.gider_turu NOT LIKE '%Stoğa%'), 0) dogrudan_gider,
               COALESCE((SELECT SUM(r.brut + r.sgk) FROM parca_basi_satir r JOIN parca_basi p ON p.id = r.parca_basi_id
                         WHERE p.siparis_id = s.id), 0) iscilik,
               COALESCE((SELECT SUM(brut) FROM fazla_calisma fc WHERE fc.siparis_id = s.id), 0) fazla
        FROM siparis s LEFT JOIN cari c ON c.id = s.cari_id WHERE substr(s.tarih, 1, 4) = ? ORDER BY s.tarih""", (str(yil),))
    for row in satirlar:
        row["brut_kar"] = yuvarla(row["faturalanan"] - row["malzeme"] - row["dogrudan_gider"]
                                  - row["iscilik"] - row["fazla"])
    return satirlar


def _bolum(db, yil: int) -> list[dict]:
    gelirler = muhasebe.bolum_gelirleri(yil)
    toplam = sum(gelirler.values()) or 1
    return [{"bolum": row["ad"], "gelir": gelirler.get(row["id"], 0.0),
             "oran": gelirler.get(row["id"], 0.0) / toplam, "yontem": row["utp_yontemi"] or ""}
            for row in db.q("SELECT * FROM bolum ORDER BY ad")]


def _cari(db, _yil: int) -> list[dict]:
    satirlar = []
    for cari in db.q("SELECT * FROM cari WHERE aktif = 1 ORDER BY unvan"):
        bakiye = muhasebe.cari_bakiye(cari["id"])
        if abs(bakiye) > 0.009:
            satirlar.append({"kod": cari["kod"], "unvan": cari["unvan"], "tur": cari["tur"],
                             "vkn": cari["vkn_tckn"], "alacak": bakiye if bakiye > 0 else None,
                             "borc": -bakiye if bakiye < 0 else None})
    return satirlar


def _aylik(db, yil: int) -> list[dict]:
    satirlar = []
    for ay in range(1, 13):
        donem = f"{yil}-{ay:02d}"
        sorgu = lambda sql: db.deger(sql, (donem,), 0.0)
        satirlar.append({
            "ay": mevzuat.AYLAR[ay - 1],
            "satis": sorgu("SELECT SUM(matrah) FROM fatura WHERE tur = 'Satış' AND iptal = 0 AND substr(tarih, 1, 7) = ?"),
            "alis": sorgu("SELECT SUM(matrah) FROM fatura WHERE tur = 'Alış' AND iptal = 0 AND substr(tarih, 1, 7) = ?"),
            "giris": sorgu("SELECT SUM(tutar) FROM kasa_banka WHERE yon = 'Giriş' AND substr(tarih, 1, 7) = ?"),
            "cikis": sorgu("SELECT SUM(tutar) FROM kasa_banka WHERE yon = 'Çıkış' AND substr(tarih, 1, 7) = ?"),
            "hasilat": muhasebe.aylik_tahsil_edilen_hasilat(yil, ay),
        })
    return satirlar


def _personel(db, yil: int) -> list[dict]:
    satirlar = db.q("""SELECT p.ad_soyad, p.dose_gorevi, p.hizmet_sinifi,
               COALESCE((SELECT SUM(r.brut) FROM parca_basi_satir r JOIN parca_basi b ON b.id = r.parca_basi_id
                         WHERE b.yil = ? AND b.durum = 'Onaylandı' AND r.kisi_turu = 'Personel' AND r.kisi_id = p.id), 0) parca,
               COALESCE((SELECT SUM(brut) FROM fazla_calisma f WHERE f.yil = ? AND f.durum = 'Onaylandı' AND f.personel_id = p.id), 0) fazla,
               COALESCE((SELECT brut FROM utp_kisi u WHERE u.yil = ? AND u.personel_id = p.id), 0) utp
        FROM personel p ORDER BY p.ad_soyad""", (yil, yil, yil))
    satirlar = [row for row in satirlar if row["parca"] or row["fazla"] or row["utp"]]
    for row in satirlar:
        row["toplam"] = yuvarla(row["parca"] + row["fazla"] + row["utp"])
    return satirlar


def _ogrenci(db, yil: int) -> list[dict]:
    return db.q("""SELECT o.okul_no, o.ad_soyad, o.sinif, b.ad bolum, o.veli_muvafakat,
                           SUM(r.brut) brut, SUM(r.net) net, COUNT(DISTINCT pb.ay) ay_sayisi
                    FROM parca_basi_satir r JOIN parca_basi pb ON pb.id = r.parca_basi_id
                    JOIN ogrenci o ON o.id = r.kisi_id LEFT JOIN bolum b ON b.id = o.bolum_id
                    WHERE r.kisi_turu = 'Öğrenci' AND pb.yil = ? AND pb.durum = 'Onaylandı'
                    GROUP BY o.id, b.ad ORDER BY o.ad_soyad""", (yil,))


def _temin(db, yil: int) -> list[dict]:
    return db.q("""SELECT f.tarih, f.belge_no, c.unvan, f.gider_turu, f.temin_usulu,
                          f.matrah, f.kdv, f.genel_toplam
                   FROM fatura f LEFT JOIN cari c ON c.id = f.cari_id
                   WHERE f.tur = 'Alış' AND f.iptal = 0 AND substr(f.tarih, 1, 4) = ?
                   ORDER BY f.temin_usulu, f.tarih""", (str(yil),))


def _hazine(db, yil: int) -> list[dict]:
    satirlar = db.q("SELECT * FROM hazine_payi WHERE yil = ? ORDER BY ay", (yil,))
    for row in satirlar:
        row["ay_ad"] = mevzuat.AYLAR[row["ay"] - 1]
    return satirlar


def _urun(db, yil: int) -> list[dict]:
    return db.q("""SELECT u.kod, u.ad, u.birim, SUM(k.miktar) miktar,
                          SUM(k.tutar) tutar, SUM(k.kdv) kdv
                   FROM fatura_kalem k JOIN fatura f ON f.id = k.fatura_id JOIN urun u ON u.id = k.urun_id
                   WHERE f.tur = 'Satış' AND f.iptal = 0 AND substr(f.tarih, 1, 4) = ?
                   GROUP BY u.id ORDER BY tutar DESC""", (str(yil),))


RAPORLAR: dict[str, tuple[str, list[dict[str, str]], Callable[[Any, int], list[dict]]]] = {
    "siparis": ("Sipariş bazında gelir-maliyet raporu", _kolonlar(
        ("siparis_no", "Sipariş", "metin"), ("tarih", "Tarih", "tarih"), ("unvan", "Cari", "metin"),
        ("konu", "Konu", "metin"), ("ucret_esasi", "Ücret esası", "metin"), ("durum", "Durum", "metin"),
        ("sozlesme_bedeli", "Sözleşme bedeli", "para"), ("faturalanan", "Faturalanan", "para"),
        ("tahsil", "Tahsil edilen", "para"), ("malzeme", "Malzeme", "para"),
        ("dogrudan_gider", "Doğrudan gider", "para"), ("iscilik", "Parça başı", "para"),
        ("fazla", "Fazla çalışma", "para"), ("brut_kar", "Brüt kâr", "para")), _siparis),
    "urun": ("Ürün / hizmet bazında satışlar", _kolonlar(
        ("kod", "Kod", "metin"), ("ad", "Ürün / hizmet", "metin"), ("birim", "Birim", "metin"),
        ("miktar", "Miktar", "sayi"), ("tutar", "Satış matrahı", "para"), ("kdv", "KDV", "para")), _urun),
    "bolum": ("Bölüm gelirleri ve katkı oranları", _kolonlar(
        ("bolum", "Bölüm / Alan", "metin"), ("gelir", "Satış matrahı", "para"),
        ("oran", "Gelire katkı oranı", "oran"), ("yontem", "ÜTP bölüm içi dağıtım yöntemi", "metin")), _bolum),
    "aylik": ("Aylık gelir-gider ve nakit akışı", _kolonlar(
        ("ay", "Ay", "metin"), ("satis", "Satış matrahı", "para"), ("alis", "Alış/gider matrahı", "para"),
        ("giris", "Kasa/banka giriş", "para"), ("cikis", "Kasa/banka çıkış", "para"),
        ("hasilat", "Tahsil edilen hasılat", "para")), _aylik),
    "cari": ("Cari hesap bakiyeleri", _kolonlar(
        ("kod", "Kod", "metin"), ("unvan", "Ünvan", "metin"), ("tur", "Tür", "metin"),
        ("vkn", "VKN/TCKN", "metin"), ("alacak", "Alacağımız", "para"), ("borc", "Borcumuz", "para")), _cari),
    "personel": ("Personel yıllık DÖSE ödemeleri", _kolonlar(
        ("ad_soyad", "Adı soyadı", "metin"), ("dose_gorevi", "DÖSE görevi", "metin"),
        ("hizmet_sinifi", "Hizmet sınıfı", "metin"), ("parca", "Parça başı (brüt)", "para"),
        ("fazla", "Fazla çalışma (brüt)", "para"), ("utp", "ÜTP (brüt)", "para"),
        ("toplam", "Toplam", "para")), _personel),
    "ogrenci": ("Öğrenci ödemeleri", _kolonlar(
        ("okul_no", "Okul no", "metin"), ("ad_soyad", "Adı soyadı", "metin"), ("sinif", "Sınıf", "metin"),
        ("bolum", "Bölüm", "metin"), ("veli_muvafakat", "Veli muvafakati", "bool"),
        ("ay_sayisi", "Ödeme yapılan ay", "sayi"), ("brut", "Brüt", "para"), ("net", "Net", "para")), _ogrenci),
    "temin": ("Satın almalar (temin usulüne göre)", _kolonlar(
        ("tarih", "Tarih", "tarih"), ("belge_no", "Belge no", "metin"), ("unvan", "Yüklenici", "metin"),
        ("gider_turu", "Gider türü", "metin"), ("temin_usulu", "Temin usulü", "metin"),
        ("matrah", "Matrah", "para"), ("kdv", "KDV", "para"), ("genel_toplam", "Toplam", "para")), _temin),
    "hazine": ("Hazine payı yıllık özeti", _kolonlar(
        ("ay_ad", "Ay", "metin"), ("tahsil_edilen", "Tahsil edilen hasılat", "para"),
        ("oran", "Oran", "oran"), ("tutar", "Hazine payı", "para"),
        ("bildirim_tarihi", "Bildirim", "tarih"), ("odeme_tarihi", "Ödeme", "tarih"),
        ("durum", "Durum", "metin")), _hazine),
    "uc_aylik": ("Üç aylık faaliyet raporu (Çalışma Yönergesi md.48)", _kolonlar(
        ("donem", "Dönem", "metin"), ("son_gun", "Rapor son günü", "tarih"), ("siparis", "Alınan sipariş", "sayi"),
        ("tamamlanan", "Kabulü yapılan", "sayi"), ("satis", "Satış matrahı", "para"),
        ("tahsilat", "Tahsilat", "para"), ("alis", "Alış/gider matrahı", "para"),
        ("parca_basi", "Personel parça başı", "para"), ("ogrenci", "Öğrenci ücretleri", "para"),
        ("fazla", "Fazla çalışma", "para"), ("hazine", "Hazine payı", "para")),
        lambda db, yil: uc_aylik_faaliyet(db, yil)),
    "idari_masraf": ("İşletme ve idari masraflar karşılığı (Çalışma Yönergesi md.11)", _kolonlar(
        ("ay", "Ay", "metin"), ("karsilik", "Ayrılan karşılık (faaliyet gideri)", "para"),
        ("gider", "İşletme/idari giderler", "para"), ("hazine", "Hazine payı", "para"),
        ("harcama", "Toplam harcama", "para"), ("kalan", "Kümülatif kalan karşılık", "para"),
        ("durum", "Durum", "metin")), lambda db, yil: idari_masraf_karsiligi(db, yil)),
}


def olustur(db, yil: int, rapor_id: str) -> dict:
    if rapor_id not in RAPORLAR:
        raise KeyError(rapor_id)
    baslik, kolonlar, uret = RAPORLAR[rapor_id]
    kolonlar = [dict(k) for k in kolonlar]
    if rapor_id == "personel":
        kolonlar[5]["baslik"] = f"{yil} ÜTP (brüt)"
    secenekler = [{"id": kimlik, "baslik": tanim[0]} for kimlik, tanim in RAPORLAR.items()]
    return {"id": rapor_id, "baslik": baslik, "yil": yil, "kolonlar": kolonlar,
            "satirlar": uret(db, yil), "secenekler": secenekler}


def ozet(rapor: dict) -> dict:
    satirlar, kolonlar = rapor["satirlar"], rapor["kolonlar"]
    toplamlar = {}
    for kolon in kolonlar:
        if kolon["tur"] == "para":
            toplamlar[kolon["anahtar"]] = yuvarla(sum(row.get(kolon["anahtar"]) or 0 for row in satirlar))
    return {"satir_sayisi": len(satirlar), "toplamlar": toplamlar}


def gorunum_degeri(deger, tur: str):
    if deger is None:
        return ""
    if tur == "tarih":
        try:
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


def disari_aktar(db, yil: int, rapor_id: str, bicim: str) -> tuple[str, bytes]:
    import tempfile
    from pathlib import Path

    rapor = olustur(db, yil, rapor_id)
    kolonlar, satirlar = rapor["kolonlar"], rapor["satirlar"]
    basliklar = [kolon["baslik"] for kolon in kolonlar]
    veriler = [[gorunum_degeri(row.get(k["anahtar"]), k["tur"]) for k in kolonlar] for row in satirlar]
    with tempfile.TemporaryDirectory(prefix="dose-rapor-") as dizin:
        if bicim == "xlsx":
            from . import excel
            yol = excel.disa_aktar(Path(dizin) / f"{rapor_id}.xlsx",
                                   [(rapor["baslik"][:31], basliklar, veriler)],
                                   f"{yil} - {rapor['baslik']}")
            return f"{yil}_{rapor_id}.xlsx", yol.read_bytes()
        if bicim == "pdf":
            from . import belgeler
            sayisal = {i for i, kolon in enumerate(kolonlar) if kolon["tur"] in ("para", "sayi")}
            toplam = [yuvarla(sum(row.get(kolon["anahtar"]) or 0 for row in satirlar))
                      if kolon["tur"] == "para" else "" for kolon in kolonlar]
            if toplam and any(k["tur"] == "para" for k in kolonlar):
                toplam[0] = "TOPLAM"
            yol = belgeler.genel_liste(Path(dizin) / f"{rapor_id}.pdf",
                                       f"{yil} - {rapor['baslik']}", basliklar, veriler, sayisal,
                                       toplam if any(k["tur"] == "para" for k in kolonlar) else None,
                                       yatay=len(kolonlar) > 6)
            return f"{yil}_{rapor_id}.pdf", yol.read_bytes()
    raise ValueError(f"Desteklenmeyen rapor dışa aktarma biçimi: {bicim}")
