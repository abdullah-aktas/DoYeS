"""Çalışma Yönergesi ve 2026 Bütçe K cetveli denetimleri.
python -m unittest tests.test_yonerge"""
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_senaryo import UYARILAR, YIL, test_kaynagi  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

from dose import belgeler, mevzuat, onay  # noqa: E402
from dose import db as dbm  # noqa: E402
from dose.denetim import fazla_calisma_denetimi, puantaj_yaz  # noqa: E402
from dose.hesap import ay_azami_fazla_calisma, fazla_calisma_gun_hatalari, gun_turu, takvim_tanimli  # noqa: E402
from dose.yonerge_raporlari import idari_masraf_karsiligi, uc_aylik_faaliyet  # noqa: E402

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


class FazlaCalismaDenetimi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.db = d = dbm.baslat(test_kaynagi(Path(cls.tmp.name)))
        from dose.ui import ortak
        ortak.CIKTILAR = Path(cls.tmp.name)
        ortak.Oturum.yil = YIL
        ortak.Oturum.kullanici = d.q1("SELECT * FROM kullanici WHERE kullanici_adi = 'admin'")
        d.kullanici = "admin"
        cls.admin = ortak.Oturum.kullanici
        cls.bolum = d.ekle("bolum", {"ad": "Mobilya"})
        cls.ogretmen = d.ekle("personel", {"ad_soyad": "Deniz Öğretmen", "dose_gorevi": "Öğretmen", "bolum_id": cls.bolum,
                                           "hizmet_sinifi": "Eğitim ve Öğretim Hizmetleri"})
        cls.hizmetli = d.ekle("personel", {"ad_soyad": "Hasan Hizmetli", "hizmet_sinifi": "Yardımcı Hizmetler", "bolum_id": cls.bolum})
        cls.sofor = d.ekle("personel", {"ad_soyad": "Ali Sürücü", "kadro_unvani": "Şoför", "hizmet_sinifi": "Teknik Hizmetler"})
        cls.sef = d.ekle("personel", {"ad_soyad": "Can Şef", "dose_gorevi": "Bölüm/Alan Şefi", "bolum_id": cls.bolum,
                                      "hizmet_sinifi": "Eğitim ve Öğretim Hizmetleri"})
        cls.musteri = d.ekle("cari", {"kod": "C1", "tur": "Müşteri", "unvan": "Belediye"})
        cls.siparis = d.ekle("siparis", {"siparis_no": "SIP-1", "tarih": f"{YIL}-03-01", "cari_id": cls.musteri, "bolum_id": cls.bolum,
                                         "ucret_esasi": "Fazla Çalışma Ücreti", "sozlesme_bedeli": 2000, "malzeme_maliyeti": 1000,
                                         "durum": "Üretimde", "ogrenci_uygulamasi": 1})

    @classmethod
    def tearDownClass(cls):
        cls.db.kapat()
        cls.tmp.cleanup()

    def setUp(self):
        UYARILAR.clear()
        onay.akis_ayarla(False)

    def _v(self, **k):
        v = {"yil": YIL, "ay": 3, "personel_id": self.ogretmen, "siparis_id": None, "saat": 3, "saat_ucreti": 67.5,
             "puantaj": puantaj_yaz({10: 3})}
        v.update(k)
        return v

    def test_uygun_kayit(self):
        hatalar, uyarilar = fazla_calisma_denetimi(self.db, self._v())
        self.assertEqual(hatalar, [])

    def test_ucret_tavani_ve_kapsam_disi(self):
        self.assertTrue(any("K cetveli" in h for h in fazla_calisma_denetimi(self.db, self._v(saat_ucreti=80))[0]))
        self.assertTrue(any("Yardımcı hizmetler" in h for h in fazla_calisma_denetimi(self.db, self._v(personel_id=self.hizmetli))[0]))
        self.assertTrue(any("Şoför" in h for h in fazla_calisma_denetimi(self.db, self._v(personel_id=self.sofor))[0]))

    def test_puantaj(self):
        hatalar = fazla_calisma_denetimi(self.db, self._v(saat=5))[0]
        self.assertTrue(any("uyuşmuyor" in h for h in hatalar))
        hatalar = fazla_calisma_denetimi(self.db, self._v(saat=4, puantaj=puantaj_yaz({10: 4})))[0]
        self.assertTrue(any("10.03.2026" in h for h in hatalar))
        # aynı gün iki ayrı kayıt: günlük toplam 3 saati aşamaz
        fid = self.db.ekle("fazla_calisma", {**self._v(saat=2, puantaj=puantaj_yaz({11: 2})), "brut": 135})
        try:
            hatalar = fazla_calisma_denetimi(self.db, self._v(saat=2, puantaj=puantaj_yaz({11: 2})))[0]
            self.assertTrue(any("11.03.2026" in h and "bütün kayıtları" in h for h in hatalar), hatalar)
        finally:
            self.db.sil("fazla_calisma", fid)
        h, u = fazla_calisma_denetimi(self.db, self._v(puantaj=None))
        self.assertEqual(h, [])
        self.assertTrue(any("Günlük puantaj girilmemiş" in x for x in u))

    def test_siparis_iscilik_tavani(self):
        # işçilik = 2000 - 1000 malzeme = 1000 TL; 15 saat x 67,50 = 1012,50 TL
        gunluk = {g: 3 for g in (2, 3, 4, 5, 6)}
        hatalar = fazla_calisma_denetimi(self.db, self._v(siparis_id=self.siparis, saat=15, puantaj=puantaj_yaz(gunluk)))[0]
        self.assertTrue(any("md.42/e" in h for h in hatalar), hatalar)
        gunluk = {g: 3 for g in (2, 3, 4, 5)}
        self.assertEqual(fazla_calisma_denetimi(self.db, self._v(siparis_id=self.siparis, saat=12, puantaj=puantaj_yaz(gunluk)))[0], [])

    def test_idari_gorevli_parca_basi(self):
        pb = self.db.ekle("parca_basi", {"yil": YIL, "ay": 3, "siparis_id": None, "kabul_edilen_iscilik": 100})
        self.db.ekle("parca_basi_satir", {"parca_basi_id": pb, "kisi_turu": "Personel", "kisi_id": self.sef, "brut": 100})
        self.db.ekle("parca_basi_satir", {"parca_basi_id": pb, "kisi_turu": "Personel", "kisi_id": self.ogretmen, "brut": 100})
        try:
            self.assertTrue(any("md.8/7" in h for h in fazla_calisma_denetimi(self.db, self._v(personel_id=self.sef))[0]))
            h, u = fazla_calisma_denetimi(self.db, self._v())
            self.assertEqual(h, [])
            self.assertTrue(any("md.8/7" in x for x in u))
        finally:
            self.db.ex("DELETE FROM parca_basi_satir WHERE parca_basi_id = ?", (pb,))
            self.db.sil("parca_basi", pb)

    def test_onay_engeli(self):
        fid = self.db.ekle("fazla_calisma", {**self._v(ay=4, saat_ucreti=100), "brut": 300, "net": 300})
        with self.assertRaisesRegex(onay.OnayHatasi, "K cetveli"):
            onay.dogrudan_onayla("Fazla Çalışma", fid, self.admin)
        self.db.guncelle("fazla_calisma", fid, {"saat_ucreti": 67.5, "brut": 202.5, "gelir_vergisi": 30.38, "damga_vergisi": 1.54,
                                                "net": 170.58})
        onay.dogrudan_onayla("Fazla Çalışma", fid, self.admin)
        self.assertEqual(self.db.deger("SELECT durum FROM fazla_calisma WHERE id = ?", (fid,)), "Onaylandı")
        yol = belgeler.fazla_calisma_puantaj(Path(self.tmp.name) / "puantaj.pdf", YIL, 4)
        self.assertGreater(yol.stat().st_size, 2000)

    def test_raporlar(self):
        urun = self.db.ekle("urun", {"ad": "Masa", "ucret_esasi": "Parça Başı Ücret (Yön. md.8)"})
        f1 = self.db.ekle("fatura", {"tur": "Satış", "tarih": f"{YIL}-05-10", "cari_id": self.musteri, "matrah": 1000, "iptal": 0})
        self.db.ekle("fatura_kalem", {"fatura_id": f1, "urun_id": urun, "miktar": 1, "birim_fiyat": 1000, "tutar": 1000})
        self.db.ekle("fatura", {"tur": "Alış", "tarih": f"{YIL}-05-12", "cari_id": self.musteri, "matrah": 400, "iptal": 0,
                                "gider_turu": "Enerji / Su / Yakıt"})
        r = idari_masraf_karsiligi(self.db, YIL)
        mayis = r[4]
        karsilik = 1000 * self.db.parametreler(YIL)["pb_faaliyet_orani"]
        self.assertAlmostEqual(mayis["karsilik"], karsilik)
        self.assertAlmostEqual(mayis["gider"], 400)
        self.assertEqual(mayis["durum"], "KARŞILIK AŞILDI" if karsilik < 400 else "")
        ceyrek = uc_aylik_faaliyet(self.db, YIL)
        self.assertEqual(len(ceyrek), 4)
        self.assertAlmostEqual(ceyrek[1]["satis"], 1000)
        self.assertEqual(ceyrek[3]["son_gun"], f"{YIL + 1}-01-05")


if __name__ == "__main__":
    unittest.main()
