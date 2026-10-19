"""Lisans imzası, deneme süresi, kurum koduna bağlılık ve salt okunur kip testleri.
python -m unittest tests.test_lisans"""
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from dose import db as dbm  # noqa: E402
from dose import lisans  # noqa: E402

OZEL = Ed25519PrivateKey.generate()
ACIK = lisans._b64(OZEL.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def anahtar(kod="123456", bitis=date.today() + timedelta(days=365), okul="Deneme MTAL", ozel=OZEL):
    return lisans.imzala(ozel, okul, kod, bitis, "L-TEST-0001", "1 yıl")


class Lisans(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.yama = mock.patch.object(lisans, "ACIK_ANAHTAR", ACIK)
        self.yama.start()
        self.db = dbm.baslat(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.yama.stop()
        self.db.kapat()
        dbm.db = None
        self.tmp.cleanup()

    def _deneme_gecmis(self):
        eski = (date.today() - timedelta(days=lisans.DENEME_GUN + 1)).isoformat()
        self.db.ayar_yaz("deneme_baslangic", eski)

    def test_imza_ve_bozulma(self):
        a = anahtar()
        lis = lisans.coz(a)
        self.assertEqual((lis.okul, lis.kurum_kodu), ("Deneme MTAL", "123456"))
        onek, yuk, imza = a.split(".")
        bozuk = lisans._b64(lisans._b64_coz(yuk).replace(b"123456", b"654321"))
        with self.assertRaises(lisans.LisansHatasi):
            lisans.coz(f"{onek}.{bozuk}.{imza}")
        with self.assertRaises(lisans.LisansHatasi):
            lisans.coz(anahtar(ozel=Ed25519PrivateKey.generate()))
        with self.assertRaises(lisans.LisansHatasi):
            lisans.coz("rastgele metin")
        self.assertEqual(lisans.coz(a[:40] + "\n  " + a[40:]).kurum_kodu, "123456")

    def test_deneme_suresi(self):
        d = lisans.uygula(self.db)
        self.assertTrue(d.yazilabilir and d.deneme)
        self.assertEqual(d.kalan_gun, lisans.DENEME_GUN)
        self._deneme_gecmis()
        d = lisans.uygula(self.db)
        self.assertFalse(d.yazilabilir)
        self.assertTrue(self.db.salt_okunur)

    def test_deneme_ayar_silinse_de_islem_kaydindan_hesaplanir(self):
        eski = (datetime.now() - timedelta(days=lisans.DENEME_GUN + 5)).strftime("%Y-%m-%d %H:%M:%S")
        self.db.ex("INSERT INTO islem_log (zaman, kullanici, islem) VALUES (?, 'admin', 'Oturum açma')", (eski,))
        self.db.ex("DELETE FROM ayar WHERE anahtar = 'deneme_baslangic'")
        self.assertFalse(lisans.durum(self.db).yazilabilir)

    def test_salt_okunur_kip(self):
        bid = self.db.ekle("bolum", {"ad": "Gıda"})
        self._deneme_gecmis()
        lisans.uygula(self.db)
        with self.assertRaises(lisans.SaltOkunurHata):
            self.db.ekle("bolum", {"ad": "Mobilya"})
        with self.assertRaises(lisans.SaltOkunurHata):
            self.db.guncelle("bolum", bid, {"ad": "X"})
        with self.assertRaises(lisans.SaltOkunurHata):
            self.db.sil("bolum", bid)
        with self.assertRaises(lisans.SaltOkunurHata):
            self.db.sonraki_no("SIP", 2026, "SIP")
        self.assertEqual(self.db.q1("SELECT ad FROM bolum WHERE id = ?", (bid,))["ad"], "Gıda")
        self.db.log("Oturum açma")
        self.db.ayar_yaz("ilk_giris_yapildi", "1")
        kid = self.db.q1("SELECT id FROM kullanici")["id"]
        self.db.sifre_degistir(kid, "yeni-sifre")
        yedek = self.db.yedekle(Path(self.tmp.name) / "yedek.db")
        self.assertTrue(yedek.exists())

    def test_etkinlestirme_kurum_koduna_baglanir(self):
        self._deneme_gecmis()
        lisans.uygula(self.db)
        lis = lisans.etkinlestir(self.db, anahtar())
        self.assertEqual(lis.kurum_kodu, "123456")
        self.assertEqual(self.db.kurum()["kurum_kodu"], "123456")
        self.assertFalse(self.db.salt_okunur)
        self.db.ekle("bolum", {"ad": "Mobilya"})
        self.assertTrue(lisans.lisansli_mi(self.db))
        with self.assertRaises(lisans.LisansHatasi):
            lisans.etkinlestir(self.db, anahtar(kod="999999"))
        self.db.guncelle("kurum", 1, {"kurum_kodu": "999999"})
        self.assertFalse(lisans.uygula(self.db).yazilabilir)

    def test_suresi_dolan_lisans(self):
        with self.assertRaises(lisans.LisansHatasi):
            lisans.etkinlestir(self.db, anahtar(bitis=date.today() - timedelta(days=1)))
        lisans.etkinlestir(self.db, anahtar(bitis=date.today() + timedelta(days=10)))
        d = lisans.durum(self.db)
        self.assertTrue(d.yazilabilir and d.uyari)
        self.db.ayar_yaz("lisans", anahtar(bitis=date.today() - timedelta(days=1)))
        self.assertFalse(lisans.uygula(self.db).yazilabilir)

    def test_saat_geri_alinirsa_son_islem_tarihi_esas(self):
        lisans.etkinlestir(self.db, anahtar(bitis=date.today() + timedelta(days=5)))
        ileri = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
        self.db.ex("INSERT INTO islem_log (zaman, kullanici, islem) VALUES (?, 'admin', 'x')", (ileri,))
        self.assertFalse(lisans.durum(self.db).yazilabilir)

    def test_suresiz_lisans(self):
        lisans.etkinlestir(self.db, anahtar(bitis=None))
        d = lisans.durum(self.db)
        self.assertTrue(d.yazilabilir)
        self.assertFalse(d.uyari)
        self.assertIsNone(d.lisans.bitis)


if __name__ == "__main__":
    unittest.main()
