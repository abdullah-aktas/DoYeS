"""Yönetim ve denetim raporları."""
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ... import belgeler, mevzuat, muhasebe
from ...hesap import para, yuvarla
from ...pdf import tr_buyuk
from ...yonerge_raporlari import idari_masraf_karsiligi, uc_aylik_faaliyet
from ..ortak import (Kolon, Oturum, SecimKutusu, VeriTablosu, baslik_etiketi, bicimle, buton, cikti_yolu, db, dosya_ac,
                     tablo_excele)


def r_siparis(yil):
    satirlar = db().q("""SELECT s.id, s.siparis_no, s.tarih, c.unvan, s.konu, s.ucret_esasi, s.durum, s.sozlesme_bedeli,
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
    for s in satirlar:
        s["maliyet"] = yuvarla(s["malzeme"] + s["dogrudan_gider"] + s["iscilik"] + s["fazla"])
        s["brut_kar"] = yuvarla(s["faturalanan"] - s["maliyet"])
    return [Kolon("siparis_no", "Sipariş"), Kolon("tarih", "Tarih", "tarih"), Kolon("unvan", "Cari"), Kolon("konu", "Konu"),
            Kolon("ucret_esasi", "Ücret esası"), Kolon("durum", "Durum"), Kolon("sozlesme_bedeli", "Sözleşme bedeli", "para"),
            Kolon("faturalanan", "Faturalanan", "para"), Kolon("tahsil", "Tahsil edilen", "para"), Kolon("malzeme", "Malzeme", "para"),
            Kolon("dogrudan_gider", "Doğrudan gider", "para"), Kolon("iscilik", "Parça başı", "para"), Kolon("fazla", "Fazla çalışma", "para"),
            Kolon("brut_kar", "Brüt kâr", "para")], satirlar


def r_bolum(yil):
    gel = muhasebe.bolum_gelirleri(yil)
    toplam = sum(gel.values()) or 1
    satirlar = [{"bolum": b["ad"], "gelir": gel.get(b["id"], 0.0), "oran": gel.get(b["id"], 0.0) / toplam,
                 "yontem": b["utp_yontemi"] or ""} for b in db().q("SELECT * FROM bolum ORDER BY ad")]
    return [Kolon("bolum", "Bölüm / Alan"), Kolon("gelir", "Satış matrahı", "para"), Kolon("oran", "Gelire katkı oranı", "oran"),
            Kolon("yontem", "ÜTP bölüm içi dağıtım yöntemi")], satirlar


def r_cari(_yil):
    satirlar = []
    for c in db().q("SELECT * FROM cari WHERE aktif = 1 ORDER BY unvan"):
        b = muhasebe.cari_bakiye(c["id"])
        if abs(b) > 0.009:
            satirlar.append({"kod": c["kod"], "unvan": c["unvan"], "tur": c["tur"], "vkn": c["vkn_tckn"],
                             "alacak": b if b > 0 else None, "borc": -b if b < 0 else None})
    return [Kolon("kod", "Kod"), Kolon("unvan", "Ünvan"), Kolon("tur", "Tür"), Kolon("vkn", "VKN/TCKN"),
            Kolon("alacak", "Alacağımız", "para"), Kolon("borc", "Borcumuz", "para")], satirlar


def r_aylik(yil):
    satirlar = []
    for ay in range(1, 13):
        d = f"{yil}-{ay:02d}"
        q = lambda sql: db().deger(sql, (d,), 0.0)
        satirlar.append({
            "ay": mevzuat.AYLAR[ay - 1],
            "satis": q("SELECT SUM(matrah) FROM fatura WHERE tur = 'Satış' AND iptal = 0 AND substr(tarih, 1, 7) = ?"),
            "alis": q("SELECT SUM(matrah) FROM fatura WHERE tur = 'Alış' AND iptal = 0 AND substr(tarih, 1, 7) = ?"),
            "giris": q("SELECT SUM(tutar) FROM kasa_banka WHERE yon = 'Giriş' AND substr(tarih, 1, 7) = ?"),
            "cikis": q("SELECT SUM(tutar) FROM kasa_banka WHERE yon = 'Çıkış' AND substr(tarih, 1, 7) = ?"),
            "hasilat": muhasebe.aylik_tahsil_edilen_hasilat(yil, ay)})
    return [Kolon("ay", "Ay"), Kolon("satis", "Satış matrahı", "para"), Kolon("alis", "Alış/gider matrahı", "para"),
            Kolon("giris", "Kasa/banka giriş", "para"), Kolon("cikis", "Kasa/banka çıkış", "para"),
            Kolon("hasilat", "Tahsil edilen hasılat", "para")], satirlar


def r_personel(yil):
    satirlar = db().q("""SELECT p.ad_soyad, p.dose_gorevi, p.hizmet_sinifi,
               COALESCE((SELECT SUM(r.brut) FROM parca_basi_satir r JOIN parca_basi b ON b.id = r.parca_basi_id
                         WHERE b.yil = ? AND b.durum = 'Onaylandı' AND r.kisi_turu = 'Personel' AND r.kisi_id = p.id), 0) parca,
               COALESCE((SELECT SUM(brut) FROM fazla_calisma f WHERE f.yil = ? AND f.durum = 'Onaylandı' AND f.personel_id = p.id), 0) fazla,
               COALESCE((SELECT brut FROM utp_kisi u WHERE u.yil = ? AND u.personel_id = p.id), 0) utp
        FROM personel p ORDER BY p.ad_soyad""", (yil, yil, yil))
    satirlar = [s for s in satirlar if s["parca"] or s["fazla"] or s["utp"]]
    for s in satirlar:
        s["toplam"] = yuvarla(s["parca"] + s["fazla"] + s["utp"])
    return [Kolon("ad_soyad", "Adı soyadı"), Kolon("dose_gorevi", "DÖSE görevi"), Kolon("hizmet_sinifi", "Hizmet sınıfı"),
            Kolon("parca", "Parça başı (brüt)", "para"), Kolon("fazla", "Fazla çalışma (brüt)", "para"),
            Kolon("utp", f"{yil} ÜTP (brüt)", "para"), Kolon("toplam", "Toplam", "para")], satirlar


def r_ogrenci(yil):
    satirlar = db().q("""SELECT o.okul_no, o.ad_soyad, o.sinif, b.ad bolum, o.veli_muvafakat, SUM(r.brut) brut, SUM(r.net) net,
                                COUNT(DISTINCT pb.ay) ay_sayisi
                         FROM parca_basi_satir r JOIN parca_basi pb ON pb.id = r.parca_basi_id JOIN ogrenci o ON o.id = r.kisi_id
                         LEFT JOIN bolum b ON b.id = o.bolum_id
                         WHERE r.kisi_turu = 'Öğrenci' AND pb.yil = ? AND pb.durum = 'Onaylandı' GROUP BY o.id, b.ad ORDER BY o.ad_soyad""", (yil,))
    return [Kolon("okul_no", "Okul no"), Kolon("ad_soyad", "Adı soyadı"), Kolon("sinif", "Sınıf"), Kolon("bolum", "Bölüm"),
            Kolon("veli_muvafakat", "Veli muvafakati", "bool"), Kolon("ay_sayisi", "Ödeme yapılan ay", "sayi"),
            Kolon("brut", "Brüt", "para"), Kolon("net", "Net", "para")], satirlar


def r_temin(yil):
    satirlar = db().q("""SELECT f.tarih, f.belge_no, c.unvan, f.gider_turu, f.temin_usulu, f.matrah, f.kdv, f.genel_toplam
                         FROM fatura f LEFT JOIN cari c ON c.id = f.cari_id
                         WHERE f.tur = 'Alış' AND f.iptal = 0 AND substr(f.tarih, 1, 4) = ? ORDER BY f.temin_usulu, f.tarih""", (str(yil),))
    return [Kolon("tarih", "Tarih", "tarih"), Kolon("belge_no", "Belge no"), Kolon("unvan", "Yüklenici"), Kolon("gider_turu", "Gider türü"),
            Kolon("temin_usulu", "Temin usulü"), Kolon("matrah", "Matrah", "para"), Kolon("kdv", "KDV", "para"),
            Kolon("genel_toplam", "Toplam", "para")], satirlar


def r_hazine(yil):
    satirlar = db().q("SELECT * FROM hazine_payi WHERE yil = ? ORDER BY ay", (yil,))
    for s in satirlar:
        s["ay_ad"] = mevzuat.AYLAR[s["ay"] - 1]
    return [Kolon("ay_ad", "Ay"), Kolon("tahsil_edilen", "Tahsil edilen hasılat", "para"), Kolon("oran", "Oran", "oran"),
            Kolon("tutar", "Hazine payı", "para"), Kolon("bildirim_tarihi", "Bildirim", "tarih"),
            Kolon("odeme_tarihi", "Ödeme", "tarih"), Kolon("durum", "Durum")], satirlar


def r_urun(yil):
    satirlar = db().q("""SELECT u.kod, u.ad, u.birim, SUM(k.miktar) miktar, SUM(k.tutar) tutar, SUM(k.kdv) kdv
                         FROM fatura_kalem k JOIN fatura f ON f.id = k.fatura_id JOIN urun u ON u.id = k.urun_id
                         WHERE f.tur = 'Satış' AND f.iptal = 0 AND substr(f.tarih, 1, 4) = ? GROUP BY u.id ORDER BY tutar DESC""", (str(yil),))
    return [Kolon("kod", "Kod"), Kolon("ad", "Ürün / hizmet"), Kolon("birim", "Birim"), Kolon("miktar", "Miktar", "sayi"),
            Kolon("tutar", "Satış matrahı", "para"), Kolon("kdv", "KDV", "para")], satirlar


def r_uc_aylik(yil):
    return [Kolon("donem", "Dönem"), Kolon("son_gun", "Rapor son günü", "tarih"), Kolon("siparis", "Alınan sipariş", "sayi"),
            Kolon("tamamlanan", "Kabulü yapılan", "sayi"), Kolon("satis", "Satış matrahı", "para"),
            Kolon("tahsilat", "Tahsilat", "para"), Kolon("alis", "Alış/gider matrahı", "para"),
            Kolon("parca_basi", "Personel parça başı", "para"), Kolon("ogrenci", "Öğrenci ücretleri", "para"),
            Kolon("fazla", "Fazla çalışma", "para"), Kolon("hazine", "Hazine payı", "para")], uc_aylik_faaliyet(db(), yil)


def r_idari_masraf(yil):
    return [Kolon("ay", "Ay"), Kolon("karsilik", "Ayrılan karşılık (faaliyet gideri)", "para"),
            Kolon("gider", "İşletme/idari giderler", "para"), Kolon("hazine", "Hazine payı", "para"),
            Kolon("harcama", "Toplam harcama", "para"), Kolon("kalan", "Kümülatif kalan karşılık", "para"),
            Kolon("durum", "Durum")], idari_masraf_karsiligi(db(), yil)


RAPORLAR = [
    ("Sipariş bazında gelir-maliyet raporu", r_siparis),
    ("Ürün / hizmet bazında satışlar", r_urun),
    ("Bölüm gelirleri ve katkı oranları", r_bolum),
    ("Aylık gelir-gider ve nakit akışı", r_aylik),
    ("Cari hesap bakiyeleri", r_cari),
    ("Personel yıllık DÖSE ödemeleri", r_personel),
    ("Öğrenci ödemeleri", r_ogrenci),
    ("Satın almalar (temin usulüne göre)", r_temin),
    ("Hazine payı yıllık özeti", r_hazine),
    ("Üç aylık faaliyet raporu (Çalışma Yönergesi md.48)", r_uc_aylik),
    ("İşletme ve idari masraflar karşılığı (Çalışma Yönergesi md.11)", r_idari_masraf),
]


class RaporSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi("Raporlar", "Çalışma yılına ait yönetim, denetim ve kontrol raporları."))
        ust = QHBoxLayout()
        ust.addWidget(QLabel("Rapor:"))
        self.secim = SecimKutusu(secenekler=[(i, r[0]) for i, r in enumerate(RAPORLAR)])
        self.secim.setMinimumWidth(340)
        self.secim.currentIndexChanged.connect(self.yenile)
        ust.addWidget(self.secim)
        ust.addWidget(buton("Yenile", self.yenile))
        ust.addWidget(buton("Excel'e Aktar", lambda: tablo_excele(self, self.tablo, RAPORLAR[self.secim.deger()][0])))
        ust.addWidget(buton("PDF", self.pdf))
        ust.addStretch()
        lay.addLayout(ust)
        self.tablo = VeriTablosu()
        lay.addWidget(self.tablo)
        self.ozet = QLabel()
        lay.addWidget(self.ozet)
        self.yenile()

    def yenile(self):
        ad, f = RAPORLAR[self.secim.deger() or 0]
        self.kolonlar, self.satirlar = f(Oturum.yil)
        self.tablo.doldur(self.kolonlar, self.satirlar)
        toplamlar = [f"{k.baslik}: {para(sum(s.get(k.anahtar) or 0 for s in self.satirlar))}"
                     for k in self.kolonlar if k.tur == "para"][:4]
        self.ozet.setText(f"{len(self.satirlar)} satır" + (" • " + " • ".join(toplamlar) if toplamlar else ""))

    def pdf(self):
        ad = RAPORLAR[self.secim.deger() or 0][0]
        sayisal = {i for i, k in enumerate(self.kolonlar) if k.tur in ("para", "sayi")}
        veri = [[s.get(k.anahtar) if k.tur in ("para", "sayi") else bicimle(s.get(k.anahtar), k.tur) for k in self.kolonlar]
                for s in self.satirlar]
        top = [(yuvarla(sum(s.get(k.anahtar) or 0 for s in self.satirlar)) if k.tur == "para" else "") for k in self.kolonlar]
        if top:
            top[0] = "TOPLAM"
        dosya_ac(belgeler.genel_liste(cikti_yolu(ad), f"{Oturum.yil} - {tr_buyuk(ad)}", [k.baslik for k in self.kolonlar], veri,
                                      sayisal, top if any(k.tur == "para" for k in self.kolonlar) else None, "",
                                      len(self.kolonlar) > 6))
