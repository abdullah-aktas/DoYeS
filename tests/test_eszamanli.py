"""Ortak çalışma: iki bilgisayar (iki ayrı bağlantı/oturum) aynı veritabanında.
python -m unittest tests.test_eszamanli"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dose import izleme, mevzuat  # noqa: E402
from dose.db import KayitCakismasi, Veritabani  # noqa: E402

AYSE = {"kullanici_adi": "ayse", "ad_soyad": "Ayşe Sayman", "rol": mevzuat.ROL_SAYMAN}
MEHMET = {"kullanici_adi": "mehmet", "ad_soyad": "Mehmet Müdür", "rol": mevzuat.ROL_MUDUR}


class Eszamanli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        yol = Path(self.tmp.name) / "ortak.db"
        self.a = Veritabani(yol)
        self.a.oturum_ac(AYSE, bilgisayar="SAYMANLIK-PC")
        self.b = Veritabani(yol)
        self.b.oturum_ac(MEHMET, istemci="Mobil", bilgisayar="Android telefon")

    def tearDown(self):
        self.a.kapat()
        self.b.kapat()
        self.tmp.cleanup()

    def test_islem_kaydi_kim_ne_zaman_ne(self):
        cid = self.a.ekle("cari", {"unvan": "Derik Belediyesi", "tur": "Müşteri"})
        self.a.guncelle("cari", cid, {"unvan": "Derik Belediye Başkanlığı", "tur": "Müşteri"})
        kayit = izleme.kayitlar(self.a, tablo="cari")
        guncelleme, ekleme = kayit[0], kayit[1]
        self.assertEqual(ekleme["islem"], "Ekleme")
        self.assertEqual((ekleme["kullanici"], ekleme["rol"], ekleme["ad_soyad"]), ("ayse", mevzuat.ROL_SAYMAN, "Ayşe Sayman"))
        self.assertEqual((ekleme["bilgisayar"], ekleme["istemci"]), ("SAYMANLIK-PC", "Masaüstü"))
        self.assertRegex(ekleme["zaman"], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")
        self.assertEqual(json.loads(guncelleme["eski"]), {"unvan": "Derik Belediyesi"})
        self.assertEqual(json.loads(guncelleme["yeni"]), {"unvan": "Derik Belediye Başkanlığı"})
        self.assertIn("unvan: Derik Belediyesi → Derik Belediye Başkanlığı", guncelleme["ozet"])
        self.b.sil("cari", cid)
        silme = izleme.kayitlar(self.a, tablo="cari")[0]
        self.assertEqual((silme["islem"], silme["istemci"], silme["kim"]), ("Silme", "Mobil", "Mehmet Müdür"))
        self.assertIn("Derik Belediye Başkanlığı", silme["ozet"])

    def test_sifre_kayda_gecmez(self):
        kid = self.a.q1("SELECT id FROM kullanici WHERE kullanici_adi = 'admin'")["id"]
        self.a.sifre_degistir(kid, "yeni-sifre-123")
        r = izleme.kayitlar(self.a, tablo="kullanici")[0]
        self.assertNotIn(self.a.q1("SELECT sifre_hash FROM kullanici WHERE id = ?", (kid,))["sifre_hash"], r["yeni"])
        self.assertEqual(json.loads(r["yeni"])["sifre_hash"], "***")

    def test_ayni_kaydi_ayni_anda_duzenleme(self):
        cid = self.a.ekle("cari", {"unvan": "Okul Aile Birliği"})
        self.a.kayit_ac("cari", cid)
        self.b.kayit_ac("cari", cid)
        self.b.guncelle("cari", cid, {"telefon": "0482 000 00 00"})
        with self.assertRaises(KayitCakismasi) as e:
            self.a.guncelle("cari", cid, {"telefon": "0555 111 11 11"})
        self.assertIn("Mehmet Müdür", str(e.exception))
        self.assertIn(mevzuat.ROL_MUDUR, str(e.exception))
        self.assertEqual(self.a.q1("SELECT telefon FROM cari WHERE id = ?", (cid,))["telefon"], "0482 000 00 00")
        self.b.guncelle("cari", cid, {"telefon": "0482 222 22 22"})  # kendi değişikliği kendisini engellemez
        self.a.kayit_birak("cari", cid)
        self.a.kayit_ac("cari", cid)  # kaydı yeniden açınca kaydedebilir
        self.a.guncelle("cari", cid, {"telefon": "0555 111 11 11"})

    def test_silinmis_kayit_kaydedilemez(self):
        cid = self.a.ekle("cari", {"unvan": "Silinecek"})
        with self.a.kayit_duzenleme("cari", cid):
            self.b.sil("cari", cid)
            with self.assertRaises(KayitCakismasi) as e:
                self.a.guncelle("cari", cid, {"unvan": "Değişti"})
            self.assertIn("silindi", str(e.exception))

    def test_degisiklikler_diger_bilgisayara_yansir(self):
        son_a, son_b = self.a.son_islem_no(), self.b.son_islem_no()
        cid = self.b.ekle("cari", {"unvan": "Mobilden eklenen"})
        self.a.ekle("cari", {"unvan": "Masaüstünden eklenen"})
        self.b.log("Oturum açma")
        gorulen_a = self.a.degisiklikler(son_a)
        self.assertEqual([(r["kullanici"], r["kayit_id"], r["istemci"]) for r in gorulen_a], [("mehmet", cid, "Mobil")])
        gorulen_b = self.b.degisiklikler(son_b)
        self.assertEqual([r["kullanici"] for r in gorulen_b], ["ayse"])


if __name__ == "__main__":
    unittest.main()
