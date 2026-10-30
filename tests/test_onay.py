"""Onay iş kuralları ve rol/bölüm kısıtları.
python -m unittest tests.test_onay (PostgreSQL için DOSE_TEST_PG ortam değişkeni desteklenir)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_support import YIL, test_kaynagi  # noqa: E402

from dose import db as dbm  # noqa: E402
from dose import mevzuat as M  # noqa: E402
from dose import onay  # noqa: E402


class OnayAkisi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = d = dbm.baslat(test_kaynagi(Path(cls.tmp.name)))
        d.kullanici = "admin"
        cls.gida = d.ekle("bolum", {"ad": "Gıda Teknolojisi"})
        cls.mobilya = d.ekle("bolum", {"ad": "Mobilya ve İç Mekân Tasarımı"})
        cls.musteri = d.ekle("cari", {"kod": "C0001", "tur": "Müşteri", "unvan": "Belediye", "kamu_kurumu": 1})
        cls.urun = d.ekle("urun", {"ad": "Zeytinyağı", "birim": "Adet", "bolum_id": cls.gida, "kdv_orani": 0.01, "satis_fiyati": 400})
        cls.k = {}
        cls.p = {}
        for ad, rol, bolum in (("mudur", M.ROL_MUDUR, None), ("tmy", M.ROL_TMY, None), ("sayman", M.ROL_SAYMAN, None),
                               ("sef_gida", M.ROL_SEF, cls.gida), ("sef_mob", M.ROL_SEF, cls.mobilya),
                               ("ogr_gida", M.ROL_OGRETMEN, cls.gida), ("ogr_mob", M.ROL_OGRETMEN, cls.mobilya),
                               ("memur", M.ROL_MEMUR, None), ("izleyici", M.ROL_IZLEYICI, None)):
            pid = d.ekle("personel", {"ad_soyad": ad.replace("_", " ").title(), "bolum_id": bolum or cls.gida,
                                      "iban": "TR020000100100000350154035"})
            h, tuz = dbm.sifre_hashle("123456")
            kid = d.ekle("kullanici", {"kullanici_adi": ad, "ad_soyad": ad.title(), "rol": rol, "sifre_hash": h, "tuz": tuz,
                                       "aktif": 1, "personel_id": pid})
            cls.p[ad] = pid
            cls.k[ad] = d.q1("SELECT * FROM kullanici WHERE id = ?", (kid,))
        cls.k["admin"] = d.q1("SELECT * FROM kullanici WHERE kullanici_adi = 'admin'")

    @classmethod
    def tearDownClass(cls):
        onay.akis_ayarla(False)
        cls.db.kapat()
        cls.tmp.cleanup()

    def setUp(self):
        onay.akis_ayarla(True)

    # ------------------------------------------------------------ yardımcılar
    def _siparis(self, bolum):
        d = self.db
        sid = d.ekle("siparis", {"siparis_no": f"SIP-{d.deger('SELECT COUNT(*) FROM siparis', (), 0) + 1}", "tarih": f"{YIL}-03-01",
                                 "cari_id": self.musteri, "bolum_id": bolum, "konu": "Üretim",
                                 "ucret_esasi": "Parça Başı Ücret (Yön. md.8)", "sozlesme_bedeli": 10000, "kdv_orani": 0.01,
                                 "durum": "Teklif", "malzeme_maliyeti": 3000, "ogrenci_uygulamasi": 1})
        d.ekle("siparis_kalem", {"siparis_id": sid, "urun_id": self.urun, "miktar": 25, "birim": "Adet", "birim_fiyat": 400})
        return sid

    def _fazla_calisma(self, kisi, ay=4):
        return self.db.ekle("fazla_calisma", {"yil": YIL, "ay": ay, "personel_id": self.p[kisi], "saat": 4, "saat_ucreti": 67.5,
                                              "brut": 270, "gelir_vergisi": 40.5, "damga_vergisi": 2.05, "net": 227.45})

    def _durum(self, tur, bid):
        return onay.durum(tur, bid)

    def _fis_var(self, kaynak, kid):
        return bool(self.db.deger("SELECT COUNT(*) FROM yevmiye WHERE kaynak = ? AND kaynak_id = ?", (kaynak, kid), 0))

    # ------------------------------------------------------------ testler
    def test_1_akis_kapali_tek_adim(self):
        onay.akis_ayarla(False)
        sid = self._siparis(self.gida)
        self.assertEqual(self._durum("Sipariş", sid)["durum"], onay.HAZIRLANIYOR)
        onay.dogrudan_onayla("Sipariş", sid, self.k["tmy"])
        self.assertEqual(self._durum("Sipariş", sid)["durum"], onay.ONAYLANDI)
        self.assertEqual(self.db.deger("SELECT durum FROM siparis WHERE id = ?", (sid,)), "Sözleşme İmzalandı")
        self.assertEqual([g["karar"] for g in onay.gecmis("Sipariş", sid)], ["Onaylandı"])
        onay.geri_al("Sipariş", sid, self.k["tmy"])
        self.assertEqual(self.db.deger("SELECT durum FROM siparis WHERE id = ?", (sid,)), "Proforma İletildi")

    def test_2_siparis_tam_akis(self):
        sid = self._siparis(self.gida)
        onay.gonder("Sipariş", sid, self.k["ogr_gida"])
        d = self._durum("Sipariş", sid)
        self.assertEqual((d["durum"], d["asama"]), (onay.BEKLIYOR, 1))
        # yalnız aynı bölümün alan şefi karar verebilir
        self.assertEqual([b["belge_id"] for b in onay.bekleyenler(self.k["sef_gida"]) if b["belge_turu"] == "Sipariş"], [sid])
        self.assertFalse([b for b in onay.bekleyenler(self.k["sef_mob"]) if b["belge_id"] == sid])
        for yetkisiz in ("sef_mob", "tmy", "mudur", "ogr_gida"):
            with self.subTest(yetkisiz=yetkisiz), self.assertRaises(onay.OnayHatasi):
                onay.karar_ver("Sipariş", sid, self.k[yetkisiz], True)
        with self.assertRaises(onay.OnayHatasi):
            onay.gonder("Sipariş", sid, self.k["ogr_gida"])
        onay.karar_ver("Sipariş", sid, self.k["sef_gida"], True, "Atölye kapasitesi uygun")
        self.assertEqual(self._durum("Sipariş", sid)["asama"], 2)
        self.assertEqual(onay.bekleyen_sayisi(self.k["tmy"]), 1)
        onay.karar_ver("Sipariş", sid, self.k["tmy"], True)
        self.assertEqual(self.db.deger("SELECT durum FROM siparis WHERE id = ?", (sid,)), "Teklif")
        onay.karar_ver("Sipariş", sid, self.k["mudur"], True)
        self.assertEqual(self._durum("Sipariş", sid)["durum"], onay.ONAYLANDI)
        self.assertEqual(self.db.deger("SELECT durum FROM siparis WHERE id = ?", (sid,)), "Sözleşme İmzalandı")
        self.assertEqual([g["karar"] for g in onay.gecmis("Sipariş", sid)], ["Onaya gönderildi", "Uygun", "Uygun", "Onaylandı"])
        # onayı yalnız müdür / sistem yöneticisi kaldırabilir
        with self.assertRaises(onay.OnayHatasi):
            onay.geri_al("Sipariş", sid, self.k["tmy"])
        onay.geri_al("Sipariş", sid, self.k["mudur"], "Sözleşme değişecek")
        self.assertEqual(self._durum("Sipariş", sid)["durum"], onay.HAZIRLANIYOR)
        self.assertEqual(self.db.deger("SELECT durum FROM siparis WHERE id = ?", (sid,)), "Proforma İletildi")

    def test_3_iade_ve_geri_cekme(self):
        sid = self._siparis(self.mobilya)
        onay.gonder("Sipariş", sid, self.k["sef_mob"])
        d = self._durum("Sipariş", sid)
        self.assertEqual(d["asama"], 2, "hazırlayan şefin kendi aşaması kendiliğinden geçilmeli")
        self.assertEqual(onay.gecmis("Sipariş", sid)[1]["karar"], "Uygun (hazırlayan)")
        with self.assertRaises(onay.OnayHatasi):
            onay.karar_ver("Sipariş", sid, self.k["tmy"], False, "")
        onay.karar_ver("Sipariş", sid, self.k["tmy"], False, "Maliyet hesabı eksik")
        self.assertEqual(self._durum("Sipariş", sid)["durum"], onay.IADE)
        onay.gonder("Sipariş", sid, self.k["sef_mob"], "Düzeltildi")
        self.assertEqual(self._durum("Sipariş", sid)["durum"], onay.BEKLIYOR)
        onay.geri_cek("Sipariş", sid, self.k["sef_mob"])
        self.assertEqual(self._durum("Sipariş", sid)["durum"], onay.HAZIRLANIYOR)

    def test_4_kullanicisi_olmayan_asama_atlanir_ve_yevmiye(self):
        fid = self._fazla_calisma("ogr_gida")
        self.db.ex("UPDATE kullanici SET aktif = 0 WHERE kullanici_adi = 'tmy'")
        try:
            onay.gonder("Fazla Çalışma", fid, self.k["ogr_gida"])
            self.assertEqual(self._durum("Fazla Çalışma", fid)["asama"], 1)
            onay.karar_ver("Fazla Çalışma", fid, self.k["sef_gida"], True)
            d = self._durum("Fazla Çalışma", fid)
            self.assertEqual(d["asama"], 3, "etkin TMY kullanıcısı yokken kontrol aşaması atlanmalı")
            self.assertIn("Atlandı", [g["karar"] for g in onay.gecmis("Fazla Çalışma", fid)])
            self.assertFalse(self._fis_var("FazlaCalisma", YIL * 100 + 4))
            onay.karar_ver("Fazla Çalışma", fid, self.k["mudur"], True)
        finally:
            self.db.ex("UPDATE kullanici SET aktif = 1 WHERE kullanici_adi = 'tmy'")
        self.assertEqual(self.db.deger("SELECT durum FROM fazla_calisma WHERE id = ?", (fid,)), "Onaylandı")
        self.assertTrue(self._fis_var("FazlaCalisma", YIL * 100 + 4))
        onay.geri_al("Fazla Çalışma", fid, self.k["mudur"])
        self.assertFalse(self._fis_var("FazlaCalisma", YIL * 100 + 4))

    def test_5_parca_basi_akis(self):
        sid = self._siparis(self.gida)
        oran = self.db.parametreler(YIL)["ogrenci_hakki_orani"]
        pb = self.db.ekle("parca_basi", {"yil": YIL, "ay": 5, "siparis_id": sid, "kabul_edilen_iscilik": 1000, "ogrenci_orani": oran})
        self.db.ekle("parca_basi_satir", {"parca_basi_id": pb, "kisi_turu": "Personel", "kisi_id": self.p["ogr_gida"], "katki": 1,
                                          "hesaplanan": 1000, "brut": 1000, "gelir_vergisi": 150, "damga_vergisi": 7.59,
                                          "net": 842.41})
        with self.assertRaisesRegex(onay.OnayHatasi, "md.8/8-a"):
            onay.gonder("Parça Başı", pb, self.k["sef_gida"])
        self.db.guncelle("siparis", sid, {"kabul_tarihi": f"{YIL}-05-20"})
        self.db.guncelle("parca_basi", pb, {"kabul_edilen_iscilik": 5000})
        with self.assertRaisesRegex(onay.OnayHatasi, "md.8/4"):
            onay.gonder("Parça Başı", pb, self.k["sef_gida"])
        self.db.guncelle("parca_basi", pb, {"kabul_edilen_iscilik": 1000})
        onay.gonder("Parça Başı", pb, self.k["sef_gida"])
        self.assertEqual(onay.durum_metni(self._durum("Parça Başı", pb)), f"Bekliyor: {M.ROL_TMY}")
        onay.karar_ver("Parça Başı", pb, self.k["tmy"], True)
        self.assertFalse(self._fis_var("ParcaBasi", pb))
        onay.karar_ver("Parça Başı", pb, self.k["mudur"], True)
        self.assertEqual(self.db.deger("SELECT durum FROM parca_basi WHERE id = ?", (pb,)), "Onaylandı")
        self.assertTrue(self._fis_var("ParcaBasi", pb))
        with self.assertRaises(onay.OnayHatasi):
            onay.geri_al("Sipariş", sid, self.k["mudur"])

    def test_6_yil_sonu_sayman_hazirlar(self):
        self.db.ekle("yil_sonu", {"yil": YIL, "durum": "Taslak", "dagitilan_utp": 0})
        onay.gonder("Yıl Sonu", YIL, self.k["sayman"])
        self.assertEqual(onay.durum_metni(self._durum("Yıl Sonu", YIL)), f"Bekliyor: {M.ROL_TMY}")
        onay.geri_cek("Yıl Sonu", YIL, self.k["sayman"])
        self.assertEqual(self.db.deger("SELECT durum FROM yil_sonu WHERE yil = ?", (YIL,)), "Taslak")

if __name__ == "__main__":
    unittest.main()
