"""Hesaplama fonksiyonlarının birim testleri:  python -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dose import mevzuat  # noqa: E402
from dose.dogrulama import iban_gecerli, tckn_gecerli, vkn_gecerli  # noqa: E402
from dose.hesap import (UtpKisi, belge_toplami, gelir_vergisi, iskonto_dagit, kalem_hatalari, kalem_tutari,  # noqa: E402
                        orantili_dagit, parca_basi_gun, parca_basi_tavani, siparis_tahsis, tavan_uygula, ucret_kesintileri,
                        utp_dagit, yasal_maliyet_dagilimi, yasal_ust_sinir_iscilik, yil_sonu_bolusum)

P = mevzuat.varsayilan_parametreler()
import json  # noqa: E402

P["gv_tarifesi_ucret"] = json.loads(P["gv_tarifesi_ucret"])


class DogrulamaTest(unittest.TestCase):
    def test_tckn(self):
        self.assertTrue(tckn_gecerli("10000000146"))
        self.assertFalse(tckn_gecerli("12345678901"))
        self.assertFalse(tckn_gecerli("01234567890"))

    def test_vkn(self):
        self.assertTrue(vkn_gecerli(mevzuat.MERKEZ_SAYMANLIK["vkn"]))
        self.assertFalse(vkn_gecerli("6210312481"))
        self.assertFalse(vkn_gecerli("621031248"))

    def test_iban(self):
        self.assertTrue(iban_gecerli(mevzuat.MERKEZ_SAYMANLIK["iban"]))
        self.assertFalse(iban_gecerli("TR00 0000 1001 0000 0350 1540 35"))


class BelgeTest(unittest.TestCase):
    def test_kdv_tevkifat_stopaj(self):
        t = belge_toplami([{"miktar": 10, "birim_fiyat": 100, "kdv_orani": 0.20}], tevkifat_orani=0.5)
        self.assertEqual((t.matrah, t.kdv, t.tevkif_kdv, t.genel_toplam, t.net_tutar), (1000, 200, 100, 1200, 1100))
        m = belge_toplami([{"miktar": 1, "birim_fiyat": 5000, "kdv_orani": 0}], stopaj_orani=0.02)
        self.assertEqual((m.stopaj, m.net_tutar), (100, 4900))

    def test_iskonto_orandan_ve_tutardan(self):
        self.assertEqual(kalem_tutari({"miktar": 275, "birim_fiyat": 15, "iskonto_orani": 0.2}), (4125, 825, 3300))
        self.assertEqual(kalem_tutari({"miktar": 3, "birim_fiyat": 100, "iskonto": 33.33, "iskonto_orani": 0.5}), (300, 33.33, 266.67))

    def test_iskontolu_belge_kdv_ve_stopaj_net_tutardan(self):
        t = belge_toplami([{"miktar": 10, "birim_fiyat": 100, "kdv_orani": 0.20, "iskonto_orani": 0.10},
                           {"miktar": 1, "birim_fiyat": 500, "kdv_orani": 0.10, "iskonto": 50}], stopaj_orani=0.02)
        self.assertEqual((t.brut, t.iskonto, t.matrah), (1500, 150, 1350))
        self.assertEqual(t.kdv, 180 + 45)
        self.assertEqual(t.stopaj, 27)
        self.assertEqual(t.net_tutar, 1350 + 225 - 27)

    def test_kalem_hatalari(self):
        self.assertFalse(kalem_hatalari([{"miktar": 1, "birim_fiyat": 10, "iskonto": 10}]))
        self.assertTrue(kalem_hatalari([{"miktar": -1, "birim_fiyat": 10}]))
        self.assertTrue(kalem_hatalari([{"miktar": 1, "birim_fiyat": -10}]))
        self.assertTrue(kalem_hatalari([{"miktar": 1, "birim_fiyat": 10, "iskonto": 11}]))
        self.assertTrue(kalem_hatalari([{"miktar": 1, "birim_fiyat": 10, "iskonto": -1}]))

    def test_genel_iskonto_kurusu_kurusuna(self):
        kalemler = [{"miktar": 1, "birim_fiyat": 100}, {"miktar": 1, "birim_fiyat": 100}, {"miktar": 1, "birim_fiyat": 100}]
        paylar = iskonto_dagit(kalemler, 100)
        self.assertAlmostEqual(sum(paylar), 100, places=2)
        self.assertTrue(all(33.33 <= p <= 33.34 for p in paylar))


class VergiTest(unittest.TestCase):
    def test_dilim_gecisi(self):
        # 180.000 kümülatif + 20.000 brüt: 10.000 %15, 10.000 %20
        self.assertAlmostEqual(gelir_vergisi(20000, 180000, P["gv_tarifesi_ucret"]), 3500.0)

    def test_ogrenci_asgari_ucret_istisnasi(self):
        k = ucret_kesintileri(10000, 0, 3, P, ogrenci=True)
        self.assertEqual(k.gelir_vergisi, 0)
        self.assertEqual(k.damga_vergisi, 0)
        self.assertEqual(k.net, 10000)

    def test_personel_kesinti(self):
        k = ucret_kesintileri(10000, 0, 3, P)
        self.assertEqual(k.gelir_vergisi, 1500)
        self.assertEqual(k.damga_vergisi, 75.9)
        self.assertEqual(k.net, 8424.1)


class SiparisTest(unittest.TestCase):
    def test_parca_basi_tahsis(self):
        t = siparis_tahsis(100000, "Parça Başı Ücret (Yön. md.8)", P, malzeme_maliyeti=30000)
        self.assertEqual(t.kar, 5000)
        self.assertEqual(t.faaliyet, 25000)
        self.assertEqual(t.azami_iscilik, 40000)
        self.assertEqual(t.ogrenci_hakki, 12000)
        self.assertEqual(t.personel_iscilik, 28000)
        self.assertFalse(t.hatalar)

    def test_ozel_sektor_kurallari(self):
        t = siparis_tahsis(100000, "Özel Sektör İşbirliği (Yön. md.9-11)", P, pesinat=10000, sure_ay=40)
        self.assertEqual(t.kar, 10000)
        self.assertEqual(t.faaliyet, 40000)
        self.assertTrue(any("36 ay" in h for h in t.hatalar))
        self.assertTrue(any("peşin" in u for u in t.uyarilar))

    def test_ogrencisiz_is_kabul_edilmez(self):
        t = siparis_tahsis(1000, "Parça Başı Ücret (Yön. md.8)", P, ogrenci_uygulamasi=False)
        self.assertTrue(t.hatalar)

    def test_malzeme_sinir_uyarisi(self):
        uyari_var = lambda t: any("malzeme" in u.lower() for u in t.uyarilar)
        self.assertFalse(uyari_var(siparis_tahsis(100000, "Parça Başı Ücret (Yön. md.8)", P, malzeme_maliyeti=60000)))
        t = siparis_tahsis(100000, "Parça Başı Ücret (Yön. md.8)", P, malzeme_maliyeti=65000)
        self.assertTrue(uyari_var(t))
        self.assertEqual(t.azami_iscilik, 5000)
        self.assertFalse(uyari_var(siparis_tahsis(100000, "Parça Başı Ücret (Yön. md.8)", dict(P, malzeme_azami_orani=0),
                                                  malzeme_maliyeti=65000)))

    def test_isciligin_yasal_ust_siniri(self):
        s = {"sozlesme_bedeli": 3300, "ucret_esasi": "Parça Başı Ücret (Yön. md.8)", "malzeme_musteriden": 1,
             "kar_orani": 0.05, "ogrenci_hakki_orani": 0.3}
        self.assertEqual(yasal_ust_sinir_iscilik(s, P), 2310)
        s.update(malzeme_musteriden=0, malzeme_maliyeti=1000)
        self.assertEqual(yasal_ust_sinir_iscilik(s, P), 1310)
        f = {"sozlesme_bedeli": 10000, "ucret_esasi": "Fazla Çalışma Ücreti", "malzeme_maliyeti": 2000}
        self.assertEqual(yasal_ust_sinir_iscilik(f, P), 10000 - 500 - 2500 - 2000)
        self.assertFalse(siparis_tahsis(10000, "Fazla Çalışma Ücreti", P, 2000, yasal_ust_sinir_iscilik(f, P)).hatalar)


class YasalMaliyetTest(unittest.TestCase):
    def test_parca_basi_birim_fiyat_dagilimi(self):
        m = yasal_maliyet_dagilimi(15, 2, "Parça Başı Ücret (Yön. md.8)", P)
        self.assertFalse(m.hatalar)
        self.assertEqual((m.kar, m.faaliyet, m.genel_gider), (0.75, 3.75, 3.75))
        self.assertEqual(m.iscilik, 8.5)
        self.assertEqual((m.ogrenci_hakki, m.personel_iscilik), (2.55, 5.95))
        maliyet = m.malzeme + m.iscilik + m.faaliyet
        self.assertAlmostEqual(maliyet * (1 + m.kar_orani), 15, places=6)

    def test_girilen_giderler_ayrilir_kalani_genel_gider(self):
        m = yasal_maliyet_dagilimi(100, 20, "Parça Başı Ücret (Yön. md.8)", P, diger=10)
        self.assertEqual((m.faaliyet, m.genel_gider, m.iscilik), (25, 15, 50))
        a = yasal_maliyet_dagilimi(100, 20, "Parça Başı Ücret (Yön. md.8)", P, diger=30)
        self.assertEqual((a.genel_gider, a.iscilik), (0, 45))
        self.assertTrue(a.notlar)

    def test_fiyat_yetmezse_hata(self):
        self.assertTrue(yasal_maliyet_dagilimi(10, 9, "Parça Başı Ücret (Yön. md.8)", P).hatalar)
        self.assertTrue(yasal_maliyet_dagilimi(0, 1, "Parça Başı Ücret (Yön. md.8)", P).hatalar)

    def test_ozel_sektor_oranlari(self):
        m = yasal_maliyet_dagilimi(1000, 0, "Özel Sektör İşbirliği (Yön. md.9-11)", P)
        self.assertEqual((m.kar, m.faaliyet, m.iscilik), (100, 400, 500))


class ParcaBasiTest(unittest.TestCase):
    def test_tavanlar(self):
        au = P["asgari_ucret_brut"]
        self.assertEqual(parca_basi_tavani("Personel", "Eğitim ve Öğretim Hizmetleri", P), au * 2)
        self.assertEqual(parca_basi_tavani("Personel", "Teknik Hizmetler", P), au * 1.5)
        self.assertEqual(parca_basi_tavani("Personel", "Genel İdare Hizmetleri", P), au)
        self.assertEqual(parca_basi_tavani("Öğrenci", None, P), au)

    def test_tavan_ay_ici_toplam(self):
        self.assertEqual(tavan_uygula(20000, 20000, 33030), (13030, 6970))

    def test_orantili_dagit_kurus(self):
        d = orantili_dagit(100, {1: 1, 2: 1, 3: 1})
        self.assertAlmostEqual(sum(d.values()), 100)

    def test_gun_hesabi(self):
        self.assertEqual(parca_basi_gun(8000, 100), 10)


class YilSonuTest(unittest.TestCase):
    def test_sermaye_eksik(self):
        b = yil_sonu_bolusum(300000, 1000000, 900000, 1 / 3, P)
        self.assertEqual(b.utp_azami, 100000)
        self.assertEqual(b.sermaye_payi, 100000)
        self.assertEqual(b.merkez_payi, 100000)

    def test_sermaye_tamam(self):
        b = yil_sonu_bolusum(300000, 1000000, 1000000, 1 / 3, P)
        self.assertEqual(b.sermaye_payi, 0)
        self.assertEqual(b.merkez_payi, 200000)

    def test_faiz_duzeltmesi(self):
        b = yil_sonu_bolusum(300000, 0, 0, 1 / 3, P, faiz_duzeltme=30000)
        self.assertEqual(b.dagitima_esas, 90000)

    def test_utp_dagitim_ve_tavan(self):
        kisiler = [
            UtpKisi(1, "Müdür", "Harcama Yetkilisi (Okul Müdürü)", 1, None, 200),
            UtpKisi(2, "Md Yrd", "Gerçekleştirme Görevlisi (Teknik Md. Yrd.)", 2, None, 200),
            UtpKisi(3, "Şef", "Bölüm/Alan Şefi", 2, 10, 200),
            UtpKisi(4, "Sayman", "Sayman", 3, None, 200, onceki_utp=394000),
            UtpKisi(5, "Memur", "Diğer İdari Personel", 5, None, 200, takdir_orani=1),
            UtpKisi(6, "Öğretmen A", "Öğretmen", 3, 10, 200, fazla_calisma_saat=300),
            UtpKisi(7, "Öğretmen B", "Öğretmen", 3, 10, 200, fazla_calisma_saat=100),
        ]
        s = utp_dagit(100000, kisiler, {10: 50000}, {10: mevzuat.UTP_BOLUM_YONTEMLERI[0]}, P)
        k = {x.id: x for x in kisiler}
        self.assertEqual(k[1].idari, 8000)
        self.assertEqual(k[2].idari, 5000)
        self.assertEqual(k[3].idari, 5000)
        self.assertEqual(k[5].takdir, 5000)
        self.assertEqual(k[6].bolum, 52500)
        self.assertEqual(k[7].bolum, 17500)
        self.assertEqual(k[4].hesaplanan, 5000)
        self.assertEqual(k[4].odenecek, 396360 - 394000)
        self.assertEqual(k[4].tavan_asimi, 5000 - (396360 - 394000))
        self.assertAlmostEqual(s.toplam_odenecek + s.dagitilamayan, 100000, places=2)


if __name__ == "__main__":
    unittest.main()
