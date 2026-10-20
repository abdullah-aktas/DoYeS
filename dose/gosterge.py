"""Gösterge paneli göstergeleri ve uyarıları (masaüstü ve mobil ortak)."""
from __future__ import annotations

from datetime import date, datetime

from . import mevzuat, muhasebe
from .db import al
from .hesap import para, son_odeme_tarihleri, yuvarla


def ozet(yil: int) -> dict:
    d = al()
    y = str(yil)
    satis = d.deger("SELECT SUM(matrah) FROM fatura WHERE tur = 'Satış' AND iptal = 0 AND substr(tarih, 1, 4) = ?", (y,), 0.0)
    tahsil = d.deger("SELECT SUM(tutar) FROM kasa_banka WHERE yon = 'Giriş' AND tur IN ('Tahsilat', 'Peşinat/Avans Tahsilatı') "
                     "AND substr(tarih, 1, 4) = ?", (y,), 0.0)
    nakit = d.deger("SELECT SUM(CASE WHEN yon = 'Giriş' THEN tutar ELSE -tutar END) FROM kasa_banka", (), 0.0)
    alacak = d.deger("""SELECT SUM(f.net_tutar - COALESCE(f.avans_mahsup, 0) - COALESCE((SELECT SUM(tutar) FROM kasa_banka k
                        WHERE k.fatura_id = f.id), 0)) FROM fatura f WHERE f.tur = 'Satış' AND f.iptal = 0""", (), 0.0)
    acik = d.deger("SELECT COUNT(*) FROM siparis WHERE durum IN ('Sözleşme İmzalandı', 'Üretimde', 'Tamamlandı (Geçici Kabul)')", (), 0)
    gt = muhasebe.gelir_tablosu(yil)
    stok = sum(yuvarla(muhasebe.stok_miktari(m["id"]) * muhasebe.ortalama_maliyet(m["id"]))
               for m in d.q("SELECT id FROM malzeme WHERE aktif = 1"))
    hp_odenmemis = d.deger("""SELECT SUM(h.tutar) FROM hazine_payi h WHERE NOT EXISTS
                              (SELECT 1 FROM kasa_banka k WHERE k.kaynak = 'HazinePayi' AND k.kaynak_id = h.id)""", (), 0.0)
    return {"satis": yuvarla(satis), "tahsilat": yuvarla(tahsil), "nakit": yuvarla(nakit), "alacak": yuvarla(alacak),
            "acik_siparis": int(acik or 0), "kar": gt["kar"], "toplam_gelir": gt["toplam_gelir"],
            "toplam_gider": gt["toplam_gider"], "stok": yuvarla(stok), "hazine_odenmemis": yuvarla(hp_odenmemis)}


def uyarilar(yil: int) -> list[tuple[str, str, str | None]]:
    """[(metin, seviye: 'hata' | 'uyari' | 'bilgi', ilgili sayfa)]"""
    d = al()
    sonuc: list[tuple[str, str, str | None]] = []

    def ekle(metin, seviye="bilgi", sayfa=None):
        sonuc.append((metin, seviye, sayfa))

    bugun = date.today()
    k = d.kurum()
    p = d.parametreler(yil)

    eksik = [e for a, e in (("harcama_yetkilisi", "harcama yetkilisi"), ("gerceklestirme_gorevlisi", "gerçekleştirme görevlisi"),
                            ("sayman", "sayman"), ("vkn", "VKN"), ("iban", "IBAN")) if not k.get(a)]
    if eksik or "....." in (k.get("okul_adi") or ""):
        ekle("Kurum bilgileri eksik: " + (", ".join(eksik) or "okul adı"), "uyari", "Kurum ve Görevliler")
    if not d.deger("SELECT COUNT(*) FROM parametre WHERE yil = ?", (yil,), 0):
        ekle(f"{yil} yılı mevzuat parametreleri kaydedilmemiş; önceki yıl/varsayılan değerler kullanılıyor.", "uyari",
             "Mevzuat Parametreleri")
    if not p["fazla_calisma_saat_ucreti"]:
        ekle("Fazla çalışma saat ücreti tanımlı değil (fazla çalışma bordrosu ve md.13/2 hesabı için gerekli).", "uyari",
             "Mevzuat Parametreleri")
    if not (k.get("tahsis_sermaye") or 0):
        ekle("Tahsis edilen sermaye tutarı girilmemiş (yıl sonu sermaye payı hesabı için gerekli).", "bilgi", "Kurum ve Görevliler")

    if yil == bugun.year:
        onceki_ay = bugun.month - 1 or 12
        onceki_yil = yil if bugun.month > 1 else yil - 1
        for ad, t in son_odeme_tarihleri(onceki_yil, onceki_ay).items():
            kalan = (t - bugun).days
            if 0 <= kalan <= 10:
                ekle(f"{mevzuat.AYLAR[onceki_ay - 1]} {onceki_yil} dönemi {ad.lower()} son günü: {t:%d.%m.%Y} ({kalan} gün kaldı)",
                     "uyari" if kalan <= 3 else "bilgi", "Hazine Payı / SHÇEK" if ad == "Hazine payı" else "KDV / Muhtasar Özeti")
    for ay in range(1, 13):
        if date(yil, ay, 1) >= date(bugun.year, bugun.month, 1):
            break
        son = son_odeme_tarihleri(yil, ay)["Hazine payı"]
        h = d.q1("SELECT id, tutar, bildirim_tarihi FROM hazine_payi WHERE yil = ? AND ay = ?", (yil, ay))
        odendi = h and d.q1("SELECT 1 FROM kasa_banka WHERE kaynak = 'HazinePayi' AND kaynak_id = ?", (h["id"],))
        if not odendi and son < bugun:
            tutar = muhasebe.aylik_tahsil_edilen_hasilat(yil, ay) * p["hazine_payi_orani"]
            if tutar > 0 or not h or not h["bildirim_tarihi"]:
                ekle(f"{mevzuat.AYLAR[ay - 1]} {yil} hazine payı bildirimi/ödemesi süresi geçti ({son:%d.%m.%Y}). "
                     f"Tutar: {para(tutar)} TL", "hata", "Hazine Payı / SHÇEK")
        on = date(yil + (ay == 12), ay % 12 + 1, 10)
        if on < bugun:
            donem = f"{mevzuat.AYLAR[ay - 1]} {yil}"
            if d.deger("SELECT COUNT(*) FROM fazla_calisma WHERE yil = ? AND ay = ?", (yil, ay), 0) and not d.q1(
                    "SELECT 1 FROM kasa_banka WHERE kaynak = 'FazlaCalisma' AND kaynak_id = ?", (yil * 100 + ay,)):
                ekle(f"{donem} fazla çalışma ücretleri ödenmemiş; son gün {on:%d.%m.%Y} (Çalışma Yönergesi md.9/b).",
                     "hata", "Fazla Çalışma Ücreti")
            odenmemis = d.deger("""SELECT COUNT(*) FROM parca_basi b WHERE b.yil = ? AND b.ay = ? AND b.durum = 'Onaylandı'
                                   AND EXISTS (SELECT 1 FROM parca_basi_satir r WHERE r.parca_basi_id = b.id
                                               AND r.kisi_turu = 'Öğrenci' AND r.net > 0)
                                   AND NOT EXISTS (SELECT 1 FROM kasa_banka k WHERE k.kaynak = 'ParcaBasi' AND k.kaynak_id = b.id)""",
                                (yil, ay), 0)
            if odenmemis:
                ekle(f"{donem}: {odenmemis} parça başı bordrosundaki öğrenci ücretleri ödenmemiş; son gün {on:%d.%m.%Y} "
                     "(Çalışma Yönergesi md.42/c).", "hata", "Parça Başı Ücret")
    onceki = yil - 1
    if bugun >= date(yil, 1, 1):
        if not d.q1("SELECT 1 FROM kasa_banka WHERE kaynak = 'SHCEK' AND kaynak_id = ?", (onceki,)) and muhasebe.yillik_brut_hasilat(onceki):
            ekle(f"{onceki} yılı SHÇEK payı ödeme kaydı yok (son gün 31.01.{yil}).",
                 "hata" if bugun > date(yil, 1, 31) else "uyari", "Hazine Payı / SHÇEK")
        ys = d.q1("SELECT * FROM yil_sonu WHERE yil = ?", (onceki,))
        if not ys and muhasebe.gelir_tablosu(onceki)["kar"] > 0:
            ekle(f"{onceki} yılı kâr dağıtımı / ÜTP işlemi yapılmamış (ÜTP bilanço tarihinden itibaren 2 ay içinde ödenir).",
                 "uyari", "Yıl Sonu Kârı ve ÜTP")
        elif ys and ys["merkez_payi"] and not d.q1("SELECT 1 FROM kasa_banka WHERE kaynak = 'MerkezKar' AND kaynak_id = ?", (onceki,)):
            ekle(f"{onceki} yılı Merkez Saymanlık kâr payı ({para(ys['merkez_payi'])} TL) ödeme kaydı yok (son gün Şubat sonu).",
                 "hata" if bugun.month > 2 and bugun.year == yil else "uyari", "Hazine Payı / SHÇEK")

    for s in d.q("""SELECT siparis_no, teslim_tarihi FROM siparis WHERE durum IN ('Sözleşme İmzalandı', 'Üretimde')
                    AND teslim_tarihi IS NOT NULL AND teslim_tarihi < ?""", (bugun.isoformat(),)):
        ekle(f"{s['siparis_no']} siparişinin teslim tarihi ({s['teslim_tarihi']}) geçti.", "uyari", "Siparişler / İş Emirleri")
    ogr = d.q("""SELECT DISTINCT o.ad_soyad, s.siparis_no FROM siparis_gorevli g JOIN ogrenci o ON o.id = g.kisi_id
                 JOIN siparis s ON s.id = g.siparis_id WHERE g.kisi_turu = 'Öğrenci' AND COALESCE(o.veli_muvafakat, 0) = 0
                 AND s.durum NOT IN ('İptal', 'Kapandı')""")
    for o in ogr[:10]:
        ekle(f"{o['ad_soyad']} ({o['siparis_no']}): veli muvafakatnamesi yok (Yön. md.8/1).", "hata", "Öğrenciler")
    from . import mevzuat as _M
    teklifler = "', '".join(_M.SIPARIS_TEKLIF_ASAMALARI)
    for s in d.q(f"SELECT siparis_no FROM siparis WHERE ogrenci_uygulamasi = 0 AND durum NOT IN ('İptal', 'Kapandı', '{teklifler}')"):
        ekle(f"{s['siparis_no']}: öğrencinin uygulamaya alınmadığı iş kabul edilemez.", "hata", "Siparişler / İş Emirleri")

    limit = p["dogrudan_temin_buyuksehir" if k.get("buyuksehir") else "dogrudan_temin_diger"]
    for r in d.q("""SELECT gider_turu, SUM(matrah) t FROM fatura WHERE tur = 'Alış' AND iptal = 0 AND temin_usulu = 'Doğrudan Temin'
                    AND substr(tarih, 1, 4) = ? GROUP BY gider_turu""", (str(yil),)):
        if r["t"] > limit:
            ekle(f"'{r['gider_turu']}' türünde yıllık doğrudan temin toplamı {para(r['t'])} TL; limit {para(limit)} TL. "
                 "İhtiyacın bölünmediğini kontrol ediniz (4734 md.22/d).", "uyari", "Alış / Gider Belgeleri")

    for m in d.q("SELECT id, ad, kritik_stok FROM malzeme WHERE aktif = 1 AND kritik_stok > 0"):
        miktar = muhasebe.stok_miktari(m["id"])
        if miktar <= m["kritik_stok"]:
            ekle(f"Kritik stok: {m['ad']} ({miktar:g})", "bilgi", "Stok Durumu ve Hareketleri")
    son_yedek = d.ayar("son_yedek")
    if not son_yedek or (datetime.now() - datetime.fromisoformat(son_yedek)).days >= 7:
        ekle("Son 7 günde yedek alınmamış. Verilerinizi düzenli yedekleyiniz.", "uyari", "Yedekleme / İşlem Kaydı")
    return sonuc
