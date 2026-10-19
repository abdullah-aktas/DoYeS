"""Uçtan uca senaryo: geçici veritabanında arayüz diyaloglarıyla tam bir DÖSE yılı işlenir.
python -m unittest tests.test_senaryo"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from dose import db as dbm  # noqa: E402
from dose import muhasebe  # noqa: E402

UYARILAR = []
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: UYARILAR.append(("bilgi", a[2] if len(a) > 2 else "")))
QMessageBox.warning = staticmethod(lambda *a, **k: UYARILAR.append(("uyari", a[2] if len(a) > 2 else "")))
QMessageBox.critical = staticmethod(lambda *a, **k: UYARILAR.append(("hata", a[2] if len(a) > 2 else "")))
os.startfile = lambda *a, **k: None

YIL = 2026


def test_kaynagi(klasor: Path):
    """DOSE_TEST_PG ortam değişkeni verilirse (ör. 'localhost:54329:postgres:dose_test') testler PostgreSQL'de,
    verilmezse geçici SQLite dosyasında çalışır. PostgreSQL şeması her testte sıfırlanır."""
    tanim = os.environ.get("DOSE_TEST_PG")
    if not tanim:
        return klasor / "test.db"
    import psycopg
    from dose.baglanti import BaglantiAyari
    sunucu, port, kullanici, vt = tanim.split(":")
    ayar = BaglantiAyari(tur="sunucu", sunucu=sunucu, port=int(port), kullanici=kullanici, veritabani=vt, ssl="disable")
    with psycopg.connect(host=sunucu, port=int(port), user=kullanici, dbname=vt, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE")
        c.execute("CREATE SCHEMA public")
    return ayar


class Senaryo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = dbm.baslat(test_kaynagi(Path(cls.tmp.name)))
        from dose.ui import ortak
        ortak.CIKTILAR = Path(cls.tmp.name)
        ortak.Oturum.kullanici = cls.db.q1("SELECT * FROM kullanici WHERE kullanici_adi = 'admin'")
        ortak.Oturum.yil = YIL
        cls.db.kullanici = "admin"
        cls._veri_hazirla()

    @classmethod
    def tearDownClass(cls):
        if os.environ.get("DOSE_TEST_AYRINTI"):
            for u in UYARILAR:
                print(u)
        cls.db.kapat()
        cls.tmp.cleanup()

    @classmethod
    def _veri_hazirla(cls):
        d = cls.db
        d.guncelle("kurum", 1, {"okul_adi": "Derik Mesleki ve Teknik Anadolu Lisesi", "il": "Mardin", "ilce": "Derik",
                                "vkn": "6210312482", "harcama_yetkilisi": "Ali Müdür", "gerceklestirme_gorevlisi": "Veli Yardımcı",
                                "sayman": "Ayşe Sayman", "tahsis_sermaye": 1000000, "odenmis_sermaye": 900000})
        for k, v in (("fazla_calisma_saat_ucreti", 67.5),):
            d.parametre_yaz(YIL, k, v)
        cls.bolum = d.ekle("bolum", {"ad": "Gıda Teknolojisi", "utp_yontemi": "Fiilen çalışılan gün ile orantılı (md.5/7-b)"})
        P = lambda ad, gorev, sinif: d.ekle("personel", {"ad_soyad": ad, "dose_gorevi": gorev, "hizmet_sinifi": sinif,
                                                         "bolum_id": cls.bolum, "iban": "TR020000100100000350154035"})
        cls.p_mudur = P("Ali Müdür", "Harcama Yetkilisi (Okul Müdürü)", "Eğitim ve Öğretim Hizmetleri")
        cls.p_yrd = P("Veli Yardımcı", "Gerçekleştirme Görevlisi (Teknik Md. Yrd.)", "Eğitim ve Öğretim Hizmetleri")
        cls.p_sef = P("Can Şef", "Bölüm/Alan Şefi", "Eğitim ve Öğretim Hizmetleri")
        cls.p_sayman = P("Ayşe Sayman", "Sayman", "Genel İdare Hizmetleri")
        cls.p_ogr1 = P("Deniz Öğretmen", "Öğretmen", "Eğitim ve Öğretim Hizmetleri")
        cls.p_ogr2 = P("Ece Öğretmen", "Öğretmen", "Eğitim ve Öğretim Hizmetleri")
        cls.ogrenci = d.ekle("ogrenci", {"ad_soyad": "Mehmet Öğrenci", "okul_no": "101", "bolum_id": cls.bolum, "veli_muvafakat": 1})
        cls.musteri = d.ekle("cari", {"kod": "C0001", "tur": "Müşteri", "unvan": "Derik Belediyesi", "kamu_kurumu": 1})
        cls.ciftci = d.ekle("cari", {"kod": "C0002", "tur": "Çiftçi (Müstahsil)", "unvan": "Hasan Çiftçi", "vkn_tckn": "10000000146"})
        cls.malzeme = d.ekle("malzeme", {"ad": "Zeytin", "tur": "İlk Madde ve Malzeme", "birim": "Kg", "kdv_orani": 0.01})
        cls.urun = d.ekle("urun", {"ad": "Zeytinyağı 1 L", "birim": "Adet", "bolum_id": cls.bolum, "kdv_orani": 0.01,
                                   "satis_fiyati": 400, "ucret_esasi": "Parça Başı Ücret (Yön. md.8)"})
        cls.siparis = d.ekle("siparis", {"siparis_no": "SIP-2026-0001", "tarih": f"{YIL}-03-01", "cari_id": cls.musteri,
                                         "bolum_id": cls.bolum, "konu": "Zeytinyağı üretimi", "ucret_esasi": "Parça Başı Ücret (Yön. md.8)",
                                         "sozlesme_bedeli": 100000, "kdv_orani": 0.01, "durum": "Tamamlandı (Geçici Kabul)",
                                         "kabul_tarihi": f"{YIL}-03-25", "malzeme_maliyeti": 30000, "ogrenci_uygulamasi": 1})
        d.ekle("siparis_kalem", {"siparis_id": cls.siparis, "urun_id": cls.urun, "miktar": 250, "birim": "Adet", "birim_fiyat": 400})
        for tur, kid in (("Personel", cls.p_ogr1), ("Personel", cls.p_ogr2), ("Öğrenci", cls.ogrenci)):
            d.ekle("siparis_gorevli", {"siparis_id": cls.siparis, "kisi_turu": tur, "kisi_id": kid})

    def _mizan_denk(self):
        m = muhasebe.mizan(f"{YIL}-01-01", f"{YIL + 1}-12-31")
        self.assertAlmostEqual(sum(r["borc"] for r in m), sum(r["alacak"] for r in m), places=2)
        return {r["kod"]: r for r in m}

    def test_1_alis_satis_kasa_stok(self):
        from dose.ui.sayfalar.fatura import FaturaDialog
        from dose.ui.sayfalar.kasa import KasaDialog
        from dose.ui.sayfalar.stok import StokHareketDialog

        # müstahsil makbuzu ile zeytin alımı (stoğa, %2 stopaj)
        f = FaturaDialog(None, "Alış")
        f.tarih.ayarla(f"{YIL}-03-02")
        f.belge_turu.ayarla("Müstahsil Makbuzu (e-MM)")
        f._belge_turu_degisti()
        f.cari.ayarla(self.ciftci)
        f.gider.ayarla("İlk Madde ve Malzeme (Stoğa)")
        f.kalem_ekle({"malzeme_id": self.malzeme, "miktar": 1000, "birim": "Kg", "birim_fiyat": 30, "kdv_orani": 0})
        f.kaydet()
        alis = self.db.q1("SELECT * FROM fatura WHERE tur = 'Alış'")
        self.assertEqual((alis["matrah"], alis["stopaj"], alis["net_tutar"]), (30000, 600, 29400))
        self.assertEqual(muhasebe.stok_miktari(self.malzeme), 1000)

        # siparişten satış faturası (kalemler siparişten gelir)
        s = FaturaDialog(None, "Satış", siparis_id=self.siparis)
        s.tarih.ayarla(f"{YIL}-03-26")
        s.kaydet()
        satis = self.db.q1("SELECT * FROM fatura WHERE tur = 'Satış'")
        self.assertEqual((satis["matrah"], satis["kdv"], satis["genel_toplam"]), (100000, 1000, 101000))

        # tahsilat: hasılat KDV hariç kısım
        k = KasaDialog(None, on_deger={"yon": "Giriş", "tur": "Tahsilat", "tutar": 101000, "cari_id": self.musteri,
                                       "fatura_id": satis["id"], "tarih": f"{YIL}-03-28"})
        k.hasilat_hesapla()
        k.kaydet()
        self.assertAlmostEqual(muhasebe.aylik_tahsil_edilen_hasilat(YIL, 3), 100000, places=2)
        self.assertEqual(muhasebe.fatura_kalan(satis["id"]), 0)

        # üretime sevk
        c = StokHareketDialog(None, "Çıkış", siparis_id=self.siparis)
        c.tarih.ayarla(f"{YIL}-03-05")
        c.malzeme.ayarla(self.malzeme)
        c.guncelle()
        c.miktar.ayarla(1000)
        c.kaydet()
        self.assertEqual(muhasebe.stok_miktari(self.malzeme), 0)
        m = self._mizan_denk()
        self.assertAlmostEqual(m["600"]["alacak"], 100000)
        self.assertAlmostEqual(m["710"]["borc"], 30000)

    def test_2_parca_basi(self):
        from dose.ui.sayfalar.parca_basi import ParcaBasiDialog, ParcaBasiSayfasi
        d = ParcaBasiDialog(None)
        d.ay.ayarla(3)
        d.siparis.ayarla(self.siparis)
        self.assertAlmostEqual(d.kabul.deger(), 40000)
        d.gorevlileri_getir()
        from dose.ui.sayfalar import parca_basi as pbm

        def puantaj_doldur(pd):
            for r in range(pd.t.rowCount()):
                pd.t.item(r, 2 + 1).setText(str(r + 2))
                pd.t.item(r, 5 + 1).setText("1,5")
                pd.t.item(r, 6 + 1).setText("abc")
            return True
        eski = pbm.PuantajDialog.exec
        pbm.PuantajDialog.exec = puantaj_doldur
        try:
            d.puantaj()
        finally:
            pbm.PuantajDialog.exec = eski
        self.assertEqual([s["katki_k"].deger() for s in d.satirlar], [3.5, 4.5, 5.5])
        self.assertEqual(d.satirlar[0]["puantaj"], {2: 2.0, 5: 1.5})
        d.kaydet()
        pb = self.db.q1("SELECT * FROM parca_basi")
        satirlar = self.db.q("SELECT * FROM parca_basi_satir WHERE parca_basi_id = ?", (pb["id"],))
        ogr = next(r for r in satirlar if r["kisi_turu"] == "Öğrenci")
        per = [r for r in satirlar if r["kisi_turu"] == "Personel"]
        self.assertAlmostEqual(ogr["hesaplanan"], 12000)
        self.assertEqual(ogr["gelir_vergisi"], 0)
        self.assertAlmostEqual(sum(r["hesaplanan"] for r in per), 28000)
        self.assertAlmostEqual(per[0]["hesaplanan"] if per[0]["katki"] == 3.5 else per[1]["hesaplanan"], 12250)
        import json
        self.assertEqual(json.loads(ogr["puantaj"]), {"2": 4.0, "5": 1.5})
        d2 = ParcaBasiDialog(None, pb["id"])
        self.assertEqual(sorted(len(s["puantaj"]) for s in d2.satirlar), [2, 2, 2])
        sayfa = ParcaBasiSayfasi()
        sayfa.tablo.selectRow(0)
        sayfa.onayla()
        self.assertEqual(self.db.deger("SELECT durum FROM parca_basi"), "Onaylandı")
        sayfa.pdf()
        sayfa.banka_listesi()
        self._mizan_denk()

    def test_3_hazine_payi_ve_vergi(self):
        from dose.ui.sayfalar.yukumluluk import HazinePayiSayfasi, VergiSayfasi
        h = HazinePayiSayfasi()
        self.assertTrue(h._hesapla_ay(3))
        hp = self.db.q1("SELECT * FROM hazine_payi WHERE ay = 3")
        self.assertAlmostEqual(hp["tutar"], 1000)
        h.yenile()
        h.tablo.selectRow(2)
        h.pdf()
        v = VergiSayfasi()
        mart = v.satirlar[2]
        self.assertAlmostEqual(mart["hesaplanan"], 1000)
        self.assertAlmostEqual(mart["stopaj"], 600)
        self._mizan_denk()

    def test_4_yil_sonu(self):
        from dose.ui.sayfalar.yil_sonu import YilSonuSayfasi
        y = YilSonuSayfasi()
        self.assertGreater(y.gt["kar"], 0)
        for s in y.satirlar:
            s["w"]["gun"].ayarla(200)
        y.hesapla()
        y.kesinlestir()
        ys = self.db.q1("SELECT * FROM yil_sonu WHERE yil = ?", (YIL,))
        self.assertEqual(ys["durum"], "Onaylandı")
        self.assertAlmostEqual(ys["dagitilan_utp"] + ys["sermaye_payi"] + ys["merkez_payi"], ys["donem_kari"], places=2)
        self.assertLessEqual(ys["dagitilan_utp"], ys["donem_kari"] / 3 + 0.01)
        y.cetvel()
        y.banka()
        y.merkez_yazisi()
        self._mizan_denk()

    def test_5_belgeler_ve_yeniden_uretim(self):
        from dose import belgeler
        t = Path(self.tmp.name)
        belgeler.teklif_mektubu(t / "teklif.pdf", self.siparis)
        belgeler.siparis_sozlesmesi(t / "sozlesme.pdf", self.siparis, {"pesin_orani": 0})
        belgeler.gorevlendirme_onayi(t / "gorev.pdf", self.siparis)
        belgeler.muayene_kabul_tutanagi(t / "kabul.pdf", self.siparis)
        belgeler.veli_muvafakatnamesi(t / "veli.pdf", [self.ogrenci])
        belgeler.muhasebe_islem_fisi(t / "mif.pdf", self.db.deger("SELECT MIN(id) FROM yevmiye"))
        from dose.hesap import siparis_kaydi_tahsisi
        p = self.db.parametreler(YIL)
        s = self.db.q1("SELECT * FROM siparis WHERE id = ?", (self.siparis,))
        belgeler.on_maliyet_cizelgesi(t / "maliyet.pdf", self.siparis, siparis_kaydi_tahsisi(s, p), p)
        belgeler.calisma_istek_listesi(t / "istek.pdf", self.siparis)
        belgeler.gecici_kabul_tutanagi(t / "gecici.pdf", self.siparis)
        belgeler.siparis_malzeme_listesi(t / "malzeme.pdf", self.siparis, p)
        belgeler.parca_basi_puantaj(t / "puantaj.pdf", self.db.deger("SELECT MIN(id) FROM parca_basi"))
        from dose.ui.sayfalar.fatura import DogrudanTeminDialog
        alis = self.db.q1("SELECT f.*, c.unvan FROM fatura f LEFT JOIN cari c ON c.id = f.cari_id WHERE f.tur = 'Alış'")
        dt = DogrudanTeminDialog(None, alis)
        self.assertEqual(dt.kt.item(0, 1).text(), "1000")
        dt._satir(dt.ft, ["Firma B", "31.500,00"])
        dt._en_dusuk()
        self.assertAlmostEqual(dt.yaklasik.deger(), 30000)
        d = {"konu": "Zeytin alımı", "tarih": f"{YIL}-03-01", "sayi": "1", "gider_turu": "", "gorevliler": ["Can Şef"],
             "kalemler": [{"ad": "Zeytin", "miktar": "1000", "birim": "Kg"}], "yaklasik_maliyet": 0, "teslim_yeri": "",
             "firmalar": [{"ad": "Hasan Çiftçi", "tutar": 30000}, {"ad": "Firma B", "tutar": 31500}, {"ad": "Firma C", "tutar": 0}]}
        belgeler.dogrudan_temin_dosyasi(t / "temin.pdf", d)
        for ad in ("teklif", "sozlesme", "gorev", "kabul", "veli", "mif", "maliyet", "istek", "gecici", "malzeme", "puantaj",
                   "temin"):
            self.assertGreater((t / f"{ad}.pdf").stat().st_size, 1000)
        once = self._mizan_denk()
        muhasebe.tum_kayitlari_yeniden_uret()
        sonra = self._mizan_denk()
        self.assertEqual({k: round(v["borc"] - v["alacak"], 2) for k, v in once.items()},
                         {k: round(v["borc"] - v["alacak"], 2) for k, v in sonra.items()})

    def test_6_tum_sayfalar_acilir(self):
        import importlib
        from dose.ui.ana_pencere import SAYFALAR
        for _g, ad, modul, sinif in SAYFALAR:
            with self.subTest(sayfa=ad):
                w = getattr(importlib.import_module(f"dose.ui.sayfalar.{modul}"), sinif)()
                if hasattr(w, "yenile"):
                    w.yenile()
                w.deleteLater()

    def test_7_raporlar_yedek_geri_yukleme(self):
        from dose.ui.sayfalar.raporlar import RAPORLAR
        for ad, f in RAPORLAR:
            with self.subTest(rapor=ad):
                f(YIL)
        haric = {"islem_log", "ayar"}
        sayim = lambda: {t: self.db.deger(f"SELECT COUNT(*) FROM {t}") for t in dbm.TABLOLAR if t not in haric}
        once, mizan_once = sayim(), self._mizan_denk()
        yedek = self.db.yedekle(Path(self.tmp.name) / "yedek.db")
        self.db.ekle("bolum", {"ad": "Geçici bölüm"})
        self.db.geri_yukle(yedek)
        self.assertEqual(once, sayim())
        self.assertEqual({k: round(v["borc"], 2) for k, v in mizan_once.items()},
                         {k: round(v["borc"], 2) for k, v in self._mizan_denk().items()})
        yeni = self.db.ekle("bolum", {"ad": "Yedek sonrası bölüm"})
        self.assertGreater(yeni, max(r["id"] for r in self.db.q("SELECT id FROM bolum WHERE id != ?", (yeni,))))

    def test_8_excel_ice_aktarma(self):
        """Hakediş dosyalarındaki gibi aynı sayfada alt alta öğretmen ve öğrenci tabloları, S.No sütunu, TOPLAM satırları,
        yan hesap alanı ve imza adları bulunan bir dosyadan yalnız ilgili tablo aktarılmalıdır."""
        from openpyxl import Workbook
        from dose.ui import ortak
        from dose.ui.sayfalar.tanimlar import OgrenciSayfasi, PersonelSayfasi

        def tc(ilk9):
            d = [int(c) for c in ilk9]
            d10 = (sum(d[0:9:2]) * 7 - sum(d[1:8:2])) % 10
            return int(ilk9 + str(d10) + str((sum(d) + d10) % 10))

        iban = "TR020000100100000350154035"
        wb = Workbook()
        ws = wb.active
        ws.title = " MALİYETİ"
        ws.append(["", "PARÇA BAŞI HAKEDİŞ"])
        ws.append([])
        ws.append(["", "S.No", "Görevi", "T.C. No", "Adı Soyadı ", "IBAN No"])
        ws.append(["", 1, "Alan Şefi", tc("184818424"), "Ümit Deneme", iban])
        ws.append(["", 2, "Öğretmen", tc("170786411"), "Ramazan Deneme", iban] + [None] * 8 + ["toplam", 14700])
        ws.append(["", 3, "Öğretmen", tc("152479707"), "Fulya Deneme", "TR12 3456"])
        ws.append(["", 4])
        ws.append(["", "", "", "", "TOPLAM", ""])
        ws.append([])
        ws.append(["", "S.No", "Okul No", "Görevi", "T.C. No", "Adı Soyadı", "Sınıfı", "IBAN"])
        ws.append(["", 1, 1692, "Öğrenci", tc("403458651"), "Fırat Deneme", "11AT", iban])
        ws.append(["", 2, 253, "Öğrenci", tc("212305021"), "Ramazan Öğrenci", "11AT", iban])
        ws.append(["", 3, 1668, "Öğrenci", tc("403458651"), "Fırat Deneme (tekrar)", "11AT", iban])
        ws.append(["", "", "", "", "", "TOPLAM"])
        ws.append([])
        ws.append([])
        ws.append([])
        ws.append(["", "", "", "", "", "Murat İmza"])
        yol = Path(self.tmp.name) / "hakedis.xlsx"
        wb.save(yol)

        eski = ortak.QFileDialog.getOpenFileName
        ortak.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(yol), ""))
        try:
            n_per, n_ogr = self.db.deger("SELECT COUNT(*) FROM personel"), self.db.deger("SELECT COUNT(*) FROM ogrenci")
            PersonelSayfasi().ice_aktar()
            PersonelSayfasi().ice_aktar()
            OgrenciSayfasi().ice_aktar()
        finally:
            ortak.QFileDialog.getOpenFileName = eski
        self.assertEqual(self.db.deger("SELECT COUNT(*) FROM personel"), n_per + 3)
        self.assertEqual(self.db.deger("SELECT COUNT(*) FROM ogrenci"), n_ogr + 2)
        fulya = self.db.q1("SELECT * FROM personel WHERE ad_soyad = 'Fulya Deneme'")
        self.assertIsNone(fulya["iban"])
        self.assertEqual((fulya["dose_gorevi"], fulya["kadro_unvani"]), ("Öğretmen", "Öğretmen"))
        firat = self.db.q1("SELECT * FROM ogrenci WHERE ad_soyad = 'Fırat Deneme'")
        self.assertEqual((firat["okul_no"], firat["sinif"], firat["aktif"]), ("1692", "11AT", 1))
        for ad in ("Murat İmza", "TOPLAM", "Fırat Deneme"):
            self.assertIsNone(self.db.q1("SELECT id FROM personel WHERE ad_soyad = ?", (ad,)))
        self.assertIsNone(self.db.q1("SELECT id FROM ogrenci WHERE ad_soyad LIKE '%Deneme' AND ad_soyad NOT LIKE 'Fırat%'"))


if __name__ == "__main__":
    unittest.main()
