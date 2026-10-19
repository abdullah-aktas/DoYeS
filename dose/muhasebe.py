"""İşlemlerden otomatik yardımcı yevmiye kaydı üretimi, mizan ve gelir tablosu."""
from __future__ import annotations

from . import mevzuat
from .db import al
from .hesap import yuvarla

KASA_KODU = {"Kasa (100)": "100", "Banka (102)": "102"}
STOK_HESABI = {"İlk Madde ve Malzeme": "150", "Yarı Mamul": "151", "Mamul": "152", "Ticari Mal": "153"}


def fis_sil(kaynak: str, kaynak_id: int):
    db = al()
    with db.islem():
        for f in db.q("SELECT id FROM yevmiye WHERE kaynak = ? AND kaynak_id = ?", (kaynak, kaynak_id)):
            db.ex("DELETE FROM yevmiye_satir WHERE yevmiye_id = ?", (f["id"],))
            db.ex("DELETE FROM yevmiye WHERE id = ?", (f["id"],))


def fis_olustur(tarih: str, aciklama: str, kaynak: str, kaynak_id: int | None, satirlar: list[tuple]) -> int | None:
    """satirlar: (hesap_kodu, aciklama, borc, alacak). Aynı kaynak için eski fiş silinip yeniden üretilir."""
    db = al()
    satirlar = [(h, a, yuvarla(b), yuvarla(c)) for h, a, b, c in satirlar if yuvarla(b) or yuvarla(c)]
    borc = yuvarla(sum(s[2] for s in satirlar))
    alacak = yuvarla(sum(s[3] for s in satirlar))
    if abs(borc - alacak) > 0.01:
        raise ValueError(f"Yevmiye fişi dengesiz: borç {borc} / alacak {alacak}")
    with db.islem():
        if kaynak_id is not None and kaynak != "Manuel":
            fis_sil(kaynak, kaynak_id)
        if not satirlar:
            return None
        yil = int((tarih or "2000")[:4])
        fis_no = db.sonraki_no("yevmiye", yil, "MIF")
        yid = db.ekle("yevmiye", {"fis_no": fis_no, "tarih": tarih, "aciklama": aciklama, "kaynak": kaynak,
                                  "kaynak_id": kaynak_id}, log=False)
        for h, a, b, c in satirlar:
            db.ekle("yevmiye_satir", {"yevmiye_id": yid, "hesap_kodu": h, "aciklama": a, "borc": b, "alacak": c}, log=False)
    return yid


# ---------------------------------------------------------------- belge bazlı kayıtlar
def fatura_kaydi(fatura_id: int):
    db = al()
    f = db.q1("SELECT f.*, c.unvan FROM fatura f LEFT JOIN cari c ON c.id = f.cari_id WHERE f.id = ?", (fatura_id,))
    if not f:
        return
    if f["iptal"]:
        fis_sil("Fatura", fatura_id)
        return
    ack = f"{f['tur']} faturası {f['belge_no'] or ''} - {f['unvan'] or ''}".strip()
    if f["tur"] == "Satış":
        satirlar = [
            ("120", ack, f["net_tutar"], 0),
            ("600", ack, 0, f["matrah"]),
            ("391", "Hesaplanan KDV", 0, f["kdv"] - f["tevkif_kdv"]),
            ("340", "Sipariş avansı mahsubu", f["avans_mahsup"] or 0, 0),
            ("120", "Sipariş avansı mahsubu", 0, f["avans_mahsup"] or 0),
        ]
    else:
        gider_hesabi = mevzuat.GIDER_TURLERI.get(f["gider_turu"] or "", ("740", False))[0]
        satirlar = [
            (gider_hesabi, ack, f["matrah"], 0),
            ("191", "İndirilecek KDV", f["kdv"], 0),
            ("320", ack, 0, f["net_tutar"]),
            ("360", "Stopaj / KDV tevkifatı", 0, f["stopaj"] + f["tevkif_kdv"]),
        ]
    fis_olustur(f["tarih"], ack, "Fatura", fatura_id, satirlar)


def kasa_kaydi(kasa_id: int):
    db = al()
    k = db.q1("SELECT * FROM kasa_banka WHERE id = ?", (kasa_id,))
    if not k:
        return
    nakit = KASA_KODU.get(k["hesap"], "102")
    t = k["tutar"]
    tur = k["tur"]
    ack = f"{tur} - {k['aciklama'] or ''}".strip(" -")
    karsi = {
        "Tahsilat": "120", "Peşinat/Avans Tahsilatı": "340", "Faiz/Diğer Gelir": "642",
        "Ödeme": "320", "Hazine Payı Ödemesi": "362", "SHÇEK Payı Ödemesi": "362", "Vergi Ödemesi": "360",
        "Personel Ödemesi": "335", "Merkez Saymanlık Kâr Aktarımı": "570", "Sermaye": "500",
    }.get(tur, "649" if k["yon"] == "Giriş" else "770")
    if k["yon"] == "Giriş":
        satirlar = [(nakit, ack, t, 0), (karsi, ack, 0, t)]
    else:
        satirlar = [(karsi, ack, t, 0), (nakit, ack, 0, t)]
    fis_olustur(k["tarih"], ack, "KasaBanka", kasa_id, satirlar)


def parca_basi_kaydi(pb_id: int):
    db = al()
    pb = db.q1("SELECT pb.*, s.siparis_no FROM parca_basi pb LEFT JOIN siparis s ON s.id = pb.siparis_id WHERE pb.id = ?", (pb_id,))
    if not pb:
        return
    if pb["durum"] != "Onaylandı":
        fis_sil("ParcaBasi", pb_id)
        return
    t = db.q1("SELECT SUM(brut) b, SUM(gelir_vergisi) gv, SUM(damga_vergisi) dv, SUM(sgk) sgk, SUM(net) n "
              "FROM parca_basi_satir WHERE parca_basi_id = ?", (pb_id,))
    tarih = f"{pb['yil']}-{pb['ay']:02d}-28"
    ack = f"Parça başı ücret {pb['ay']:02d}/{pb['yil']} - {pb['siparis_no'] or ''}"
    fis_olustur(tarih, ack, "ParcaBasi", pb_id, [
        ("720", ack, (t["b"] or 0) + (t["sgk"] or 0), 0),
        ("360", "GV + DV kesintisi", 0, (t["gv"] or 0) + (t["dv"] or 0)),
        ("361", "Öğrenci sigorta primi", 0, t["sgk"] or 0),
        ("335", "Personele borçlar (net)", 0, t["n"] or 0),
    ])


def fazla_calisma_kaydi(yil: int, ay: int):
    db = al()
    anahtar = yil * 100 + ay
    t = db.q1("SELECT SUM(brut) b, SUM(gelir_vergisi) gv, SUM(damga_vergisi) dv, SUM(net) n FROM fazla_calisma "
              "WHERE yil = ? AND ay = ? AND durum = 'Onaylandı'", (yil, ay))
    if not t or not t["b"]:
        fis_sil("FazlaCalisma", anahtar)
        return
    ack = f"Fazla çalışma ücreti {ay:02d}/{yil}"
    fis_olustur(f"{yil}-{ay:02d}-28", ack, "FazlaCalisma", anahtar, [
        ("720", ack, t["b"], 0),
        ("360", "GV + DV kesintisi", 0, (t["gv"] or 0) + (t["dv"] or 0)),
        ("335", "Personele borçlar (net)", 0, t["n"]),
    ])


def hazine_payi_kaydi(hp_id: int):
    db = al()
    h = db.q1("SELECT * FROM hazine_payi WHERE id = ?", (hp_id,))
    if not h:
        return
    import calendar
    son = calendar.monthrange(h["yil"], h["ay"])[1]
    ack = f"Hazine payı {h['ay']:02d}/{h['yil']} (tahsil edilen hasılatın {h['oran'] * 100:.2f}%)"
    fis_olustur(f"{h['yil']}-{h['ay']:02d}-{son}", ack, "HazinePayi", hp_id, [
        ("770", ack, h["tutar"], 0), ("362", ack, 0, h["tutar"])])


def shcek_kaydi(yil: int, tutar: float):
    ack = f"{yil} yılı SHÇEK payı (2828 s.K. md.18/1-k)"
    fis_olustur(f"{yil}-12-31", ack, "SHCEK", yil, [("770", ack, tutar, 0), ("362", ack, 0, tutar)])


def utp_kaydi(yil: int):
    db = al()
    t = db.q1("SELECT SUM(brut) b, SUM(gelir_vergisi) gv, SUM(damga_vergisi) dv, SUM(net) n FROM utp_kisi WHERE yil = ?", (yil,))
    if not t or not t["b"]:
        fis_sil("UTP", yil)
        return
    ack = f"{yil} yılı üretimi teşvik primi tahakkuku"
    fis_olustur(f"{yil + 1}-01-31", ack, "UTP", yil, [
        ("570", ack, t["b"], 0),
        ("360", "GV + DV kesintisi", 0, (t["gv"] or 0) + (t["dv"] or 0)),
        ("335", "Personele borçlar (net)", 0, t["n"]),
    ])


def ortalama_maliyet(malzeme_id: int, tarihe_kadar: str | None = None) -> float:
    db = al()
    sql = "SELECT SUM(miktar) m, SUM(miktar * birim_fiyat) t FROM stok_hareket WHERE malzeme_id = ? AND yon = 'Giriş'"
    prm = [malzeme_id]
    if tarihe_kadar:
        sql += " AND tarih <= ?"
        prm.append(tarihe_kadar)
    r = db.q1(sql, prm)
    return yuvarla((r["t"] or 0) / r["m"], 4) if r and r["m"] else 0.0


def stok_miktari(malzeme_id: int) -> float:
    db = al()
    return db.deger("SELECT SUM(CASE WHEN yon = 'Giriş' THEN miktar ELSE -miktar END) FROM stok_hareket WHERE malzeme_id = ?",
                    (malzeme_id,), 0.0)


def stok_cikis_kaydi(hareket_id: int):
    db = al()
    h = db.q1("SELECT h.*, m.ad, m.tur FROM stok_hareket h JOIN malzeme m ON m.id = h.malzeme_id WHERE h.id = ?", (hareket_id,))
    if not h or h["yon"] != "Çıkış" or h["kaynak"] == "Fatura":
        return
    tutar = yuvarla(h["miktar"] * (h["birim_fiyat"] or 0))
    stok_hesabi = STOK_HESABI.get(h["tur"], "150")
    gider = "710" if stok_hesabi in ("150", "151") else "740"
    ack = f"Stok çıkışı: {h['ad']} ({h['miktar']})"
    fis_olustur(h["tarih"], ack, "Stok", hareket_id, [(gider, ack, tutar, 0), (stok_hesabi, ack, 0, tutar)])


def tum_kayitlari_yeniden_uret() -> int:
    """Manuel fişler hariç bütün otomatik yevmiye kayıtlarını kaynak işlemlerden yeniden üretir."""
    db = al()
    with db.islem():
        db.ex("DELETE FROM yevmiye_satir WHERE yevmiye_id IN (SELECT id FROM yevmiye WHERE kaynak != 'Manuel')")
        db.ex("DELETE FROM yevmiye WHERE kaynak != 'Manuel'")
    for r in db.q("SELECT id FROM fatura WHERE iptal = 0 ORDER BY tarih, id"):
        fatura_kaydi(r["id"])
    for r in db.q("SELECT id FROM kasa_banka ORDER BY tarih, id"):
        kasa_kaydi(r["id"])
    for r in db.q("SELECT id FROM stok_hareket WHERE yon = 'Çıkış' AND kaynak != 'Fatura' ORDER BY tarih, id"):
        stok_cikis_kaydi(r["id"])
    for r in db.q("SELECT id FROM parca_basi WHERE durum = 'Onaylandı'"):
        parca_basi_kaydi(r["id"])
    for r in db.q("SELECT DISTINCT yil, ay FROM fazla_calisma WHERE durum = 'Onaylandı'"):
        fazla_calisma_kaydi(r["yil"], r["ay"])
    for r in db.q("SELECT id FROM hazine_payi"):
        hazine_payi_kaydi(r["id"])
    for r in db.q("SELECT yil, shcek FROM yil_sonu WHERE durum = 'Onaylandı'"):
        utp_kaydi(r["yil"])
        if r["shcek"]:
            shcek_kaydi(r["yil"], r["shcek"])
    return db.deger("SELECT COUNT(*) FROM yevmiye", (), 0)


# ---------------------------------------------------------------- raporlar
def mizan(baslangic: str, bitis: str) -> list[dict]:
    db = al()
    return db.q(
        """SELECT s.hesap_kodu kod, COALESCE(h.ad, '') ad, SUM(s.borc) borc, SUM(s.alacak) alacak,
                  CASE WHEN SUM(s.borc) > SUM(s.alacak) THEN SUM(s.borc) - SUM(s.alacak) ELSE 0 END borc_bakiye,
                  CASE WHEN SUM(s.alacak) > SUM(s.borc) THEN SUM(s.alacak) - SUM(s.borc) ELSE 0 END alacak_bakiye
           FROM yevmiye_satir s JOIN yevmiye y ON y.id = s.yevmiye_id
           LEFT JOIN hesap_plani h ON h.kod = s.hesap_kodu
           WHERE y.tarih BETWEEN ? AND ?
           GROUP BY s.hesap_kodu, h.ad ORDER BY s.hesap_kodu""", (baslangic, bitis))


def gelir_tablosu(yil: int) -> dict:
    db = al()
    bas, bit = f"{yil}-01-01", f"{yil}-12-31"
    satirlar = db.q(
        """SELECT s.hesap_kodu kod, COALESCE(h.ad, '') ad, SUM(s.borc) b, SUM(s.alacak) a
           FROM yevmiye_satir s JOIN yevmiye y ON y.id = s.yevmiye_id LEFT JOIN hesap_plani h ON h.kod = s.hesap_kodu
           WHERE y.tarih BETWEEN ? AND ? GROUP BY s.hesap_kodu, h.ad""", (bas, bit))
    gelirler = [{"kod": s["kod"], "ad": s["ad"], "tutar": yuvarla((s["a"] or 0) - (s["b"] or 0))}
                for s in satirlar if s["kod"] in mevzuat.GELIR_HESAPLARI]
    giderler = [{"kod": s["kod"], "ad": s["ad"], "tutar": yuvarla((s["b"] or 0) - (s["a"] or 0))}
                for s in satirlar if s["kod"] in mevzuat.GIDER_HESAPLARI]
    tg = yuvarla(sum(g["tutar"] for g in gelirler))
    tgd = yuvarla(sum(g["tutar"] for g in giderler))
    return {"gelirler": gelirler, "giderler": giderler, "toplam_gelir": tg, "toplam_gider": tgd, "kar": yuvarla(tg - tgd)}


def bolum_gelirleri(yil: int) -> dict:
    """Bölüm bazında satış matrahı (kalem ürününün bölümü; yoksa siparişin bölümü)."""
    db = al()
    satirlar = db.q(
        """SELECT COALESCE(u.bolum_id, s.bolum_id) bolum_id, SUM(k.tutar) tutar
           FROM fatura_kalem k JOIN fatura f ON f.id = k.fatura_id
           LEFT JOIN urun u ON u.id = k.urun_id LEFT JOIN siparis s ON s.id = f.siparis_id
           WHERE f.tur = 'Satış' AND f.iptal = 0 AND substr(f.tarih, 1, 4) = ?
           GROUP BY COALESCE(u.bolum_id, s.bolum_id)""", (str(yil),))
    return {r["bolum_id"]: yuvarla(r["tutar"]) for r in satirlar if r["bolum_id"]}


def yillik_brut_hasilat(yil: int) -> float:
    db = al()
    satis = db.deger("SELECT SUM(matrah) FROM fatura WHERE tur = 'Satış' AND iptal = 0 AND substr(tarih, 1, 4) = ?", (str(yil),), 0.0)
    diger = db.deger("SELECT SUM(hasilat_tutari) FROM kasa_banka WHERE tur = 'Faiz/Diğer Gelir' AND substr(tarih, 1, 4) = ?", (str(yil),), 0.0)
    return yuvarla(satis + diger)


def aylik_tahsil_edilen_hasilat(yil: int, ay: int) -> float:
    db = al()
    return yuvarla(db.deger(
        "SELECT SUM(hasilat_tutari) FROM kasa_banka WHERE yon = 'Giriş' AND tur IN ('Tahsilat', 'Peşinat/Avans Tahsilatı', 'Faiz/Diğer Gelir') "
        "AND substr(tarih, 1, 7) = ?", (f"{yil}-{ay:02d}",), 0.0))


def cari_bakiye(cari_id: int) -> float:
    """Pozitif: cari bize borçlu (alacağımız), negatif: biz cariye borçluyuz."""
    db = al()
    satis = db.deger("SELECT SUM(net_tutar) FROM fatura WHERE cari_id = ? AND tur = 'Satış' AND iptal = 0", (cari_id,), 0.0)
    alis = db.deger("SELECT SUM(net_tutar) FROM fatura WHERE cari_id = ? AND tur = 'Alış' AND iptal = 0", (cari_id,), 0.0)
    tahsil = db.deger("SELECT SUM(tutar) FROM kasa_banka WHERE cari_id = ? AND yon = 'Giriş' AND tur IN ('Tahsilat','Peşinat/Avans Tahsilatı')", (cari_id,), 0.0)
    odeme = db.deger("SELECT SUM(tutar) FROM kasa_banka WHERE cari_id = ? AND yon = 'Çıkış' AND tur = 'Ödeme'", (cari_id,), 0.0)
    return yuvarla(satis - tahsil - (alis - odeme))


def fatura_kalan(fatura_id: int) -> float:
    db = al()
    f = db.q1("SELECT tur, net_tutar, avans_mahsup FROM fatura WHERE id = ?", (fatura_id,))
    if not f:
        return 0.0
    odenen = db.deger("SELECT SUM(tutar) FROM kasa_banka WHERE fatura_id = ?", (fatura_id,), 0.0)
    return yuvarla(f["net_tutar"] - (f["avans_mahsup"] or 0) - odenen)
