"""Kurum kodu / ağ yardımcıları."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dose import ag  # noqa: E402


class AgTest(unittest.TestCase):
    def test_kurum_db_adi(self):
        self.assertEqual(ag.kurum_db_adi("765432"), "okul_765432")
        self.assertEqual(ag.kurum_db_adi(" 76 5432 "), "okul_765432")
        with self.assertRaises(ValueError):
            ag.kurum_db_adi("12")
        with self.assertRaises(ValueError):
            ag.kurum_db_adi("abcde")

    def test_mobil_adres_coz(self):
        self.assertEqual(ag.mobil_adres_coz(sunucu_adresi="192.168.1.5:8765"), "192.168.1.5:8765")
        self.assertEqual(ag.mobil_adres_coz(gecit="https://mobil.ornek.tr", sunucu_adresi=""),
                         "https://mobil.ornek.tr")
        with self.assertRaises(ValueError):
            ag.mobil_adres_coz(kurum_kodu="765432", sunucu_adresi="", gecit="")

    def test_okullar_yaz_oku(self):
        with tempfile.TemporaryDirectory() as gd:
            eski = ag.OKULLAR_DOSYASI
            try:
                ag.OKULLAR_DOSYASI = Path(gd) / "okullar.json"
                ag.okullar_yaz({"sunucu": "db.test", "okullar": {"765432": {"sifre": "x", "ad": "T"}}})
                v = ag.okullar_oku()
                self.assertEqual(v["sunucu"], "db.test")
                self.assertEqual(v["okullar"]["765432"]["ad"], "T")
            finally:
                ag.OKULLAR_DOSYASI = eski


if __name__ == "__main__":
    unittest.main()
