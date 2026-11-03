"""Çalışma Yönergesi ve 2026 Bütçe K cetveli denetimleri.
python -m unittest tests.test_yonerge"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dose import mevzuat  # noqa: E402
from dose.denetim import puantaj_coz, puantaj_yaz  # noqa: E402
from dose.hesap import ay_azami_fazla_calisma, fazla_calisma_gun_hatalari, gun_turu, takvim_tanimli  # noqa: E402

P = mevzuat.varsayilan_parametreler()
for _k in ("fc_ogretim_gunu_saat", "fc_tatil_gunu_saat", "fc_pazar_izinli", "fazla_calisma_azami_ucret"):
    P[_k] = float(P[_k])


class GunTurleri(unittest.TestCase):
    def test_gun_turu(self):
        beklenen = {date(2026, 3, 10): "ogretim", date(2026, 3, 14): "tatil", date(2026, 3, 15): "pazar",
                    date(2026, 3, 16): "tatil", date(2026, 3, 20): "bayram", date(2026, 3, 22): "bayram",
                    date(2026, 7, 15): "tatil", date(2026, 1, 22): "tatil", date(2026, 4, 23): "bayram",
                    date(2026, 9, 14): "ogretim", date(2026, 11, 17): "tatil"}
        for t, tur in beklenen.items():
            self.assertEqual(gun_turu(t, P), tur, t)

    def test_gunluk_sinirlar(self):
        gunluk = {10: 3, 11: 4, 14: 8, 15: 2, 20: 1}
        hatalar = fazla_calisma_gun_hatalari(2026, 3, gunluk, P)
        self.assertEqual(len(hatalar), 3, hatalar)
        self.assertTrue(any("11.03.2026" in h for h in hatalar))
        self.assertTrue(any("15.03.2026" in h and "md.9/a-12" in h for h in hatalar))
        self.assertTrue(any("20.03.2026" in h and "bayram" in h for h in hatalar))
        izinli = dict(P, fc_pazar_izinli=1.0)
        self.assertEqual(len(fazla_calisma_gun_hatalari(2026, 3, gunluk, izinli)), 2)

    def test_takvim(self):
        self.assertTrue(takvim_tanimli(2026, P))
        self.assertFalse(takvim_tanimli(2030, P))
        # Mart 2026: 17 öğretim günü x 3 + 7 tatil (3 Cumartesi, 16-19 Mart ara tatil) x 8; 4 Pazar ve 3 bayram günü 0
        self.assertEqual(ay_azami_fazla_calisma(2026, 3, P), 17 * 3 + 7 * 8)

    def test_puantaj_gidis_donus(self):
        self.assertEqual(puantaj_coz(puantaj_yaz({10: 3, 2: 1.5})), {2: 1.5, 10: 3})


if __name__ == "__main__":
    unittest.main()
