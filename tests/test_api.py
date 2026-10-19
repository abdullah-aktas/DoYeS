"""Mobil API: giriş, rol yetkileri, bölüm kısıtı, onay akışı, fazla çalışma, iş talebi, çakışma ve işlem izi.
python -m unittest tests.test_api"""
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from dose import db as dbm  # noqa: E402
from dose import mevzuat as M  # noqa: E402
from dose import onay  # noqa: E402
from dose.db import Veritabani, sifre_hashle  # noqa: E402
from sunucu import api  # noqa: E402

YIL = 2026
FC = quote("Fazla Çalışma")


class MobilApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.yol = Path(cls.tmp.name) / "api.db"
        cls.app = api.uygulama_olustur(cls.yol)
        cls.c = TestClient(cls.app)
        d = cls.db = dbm.al()
        d.guncelle("kurum", 1, {"okul_adi": "Derik Mesleki ve Teknik Anadolu Lisesi",
                                "harcama_yetkilisi": "Ali Müdür", "kurum_kodu": "765432"})
        d.parametre_yaz(YIL, "fazla_calisma_saat_ucreti", 67.5)
        cls.bolum = d.ekle("bolum", {"ad": "Gıda Teknolojisi"})
        cls.bolum2 = d.ekle("bolum", {"ad": "Bilişim"})
        P = lambda ad, gorev, b: d.ekle("personel", {"ad_soyad": ad, "dose_gorevi": gorev, "bolum_id": b,
                                                      "hizmet_sinifi": "Eğitim ve Öğretim Hizmetleri"})
        cls.p_ogr = P("Deniz Öğretmen", "Öğretmen", cls.bolum)
        cls.p_ogr2 = P("Ece Öğretmen", "Öğretmen", cls.bolum)
        cls.p_sef = P("Can Şef", "Bölüm/Alan Şefi", cls.bolum)
        cls.p_bilisim = P("Bora Bilişim", "Öğretmen", cls.bolum2)
        for ad, rol, pid in (("deniz", M.ROL_OGRETMEN, cls.p_ogr), ("can", M.ROL_SEF, cls.p_sef),
                             ("veli", M.ROL_TMY, None), ("ali", M.ROL_MUDUR, None), ("ayse", M.ROL_SAYMAN, None),
                             ("deneme", M.ROL_IZLEYICI, None)):
            h, tuz = sifre_hashle("Gizli123")
            d.ekle("kullanici", {"kullanici_adi": ad, "ad_soyad": ad.title(), "rol": rol, "sifre_hash": h, "tuz": tuz,
                                 "personel_id": pid})
        d.guncelle("kullanici", d.deger("SELECT id FROM kullanici WHERE kullanici_adi = 'deniz'"), {"ad_soyad": "Deniz Öğretmen"})
        cls.musteri = d.ekle("cari", {"unvan": "Derik Belediyesi", "tur": "Müşteri", "kamu_kurumu": 1})
        cls.urun = d.ekle("urun", {"ad": "Zeytinyağı 1 L", "birim": "Adet", "satis_fiyati": 400, "bolum_id": cls.bolum})
        d.ekle("maliyet_kalem", {"urun_id": cls.urun, "kalem_turu": "Direkt İlk Madde ve Malzeme", "miktar": 5, "birim_fiyat": 40})
        d.ekle("maliyet_kalem", {"urun_id": cls.urun, "kalem_turu": "Ambalaj / Etiket", "miktar": 1, "birim_fiyat": 20})
        onay.akis_ayarla(True)

    @classmethod
    def tearDownClass(cls):
        cls.c.close()
        dbm.al().kapat()
        cls.tmp.cleanup()

    def giris(self, ad, sifre="Gizli123", cihaz="Test telefonu", kurum_kodu="765432") -> dict:
        govde = {"kullanici_adi": ad, "sifre": sifre, "cihaz": cihaz}
        if kurum_kodu:
            govde["kurum_kodu"] = kurum_kodu
        r = self.c.post("/api/giris", json=govde)
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": "Bearer " + r.json()["token"]}

    def test_kurum_kodu_ve_kesif(self):
        d = self.c.get("/api/durum").json()
        self.assertEqual(d["kurum_kodu"], "765432")
        self.assertFalse(d["coklu"])
        r = self.c.post("/api/kesif", json={"kurum_kodu": "765432"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["uygun"])
        self.assertEqual(self.c.post("/api/kesif", json={"kurum_kodu": "111111"}).status_code, 404)
        r = self.c.post("/api/giris", json={"kullanici_adi": "deniz", "sifre": "Gizli123", "cihaz": "t",
                                           "kurum_kodu": "111111"})
        self.assertEqual(r.status_code, 403)
        r = self.c.post("/api/giris", json={"kullanici_adi": "deniz", "sifre": "Gizli123", "cihaz": "t",
                                           "kurum_kodu": "765432"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["kurum_kodu"], "765432")
        ben = self.c.get("/api/ben", headers={"Authorization": "Bearer " + r.json()["token"]}).json()
        self.assertEqual(ben["kurum_kodu"], "765432")

    def test_giris_kilit_ve_yetkiler(self):
        self.assertEqual(self.c.get("/api/durum").json()["satici"], "Derik MTAL Döner Sermaye İşletmesi")
        self.assertEqual(self.c.get("/api/panel").status_code, 401)
        r = self.c.post("/api/giris", json={"kullanici_adi": "ayse", "sifre": "yanlis", "kurum_kodu": "765432"})
        self.assertEqual((r.status_code, r.json()["hata"]), (401, "Kullanıcı adı veya şifre hatalı."))
        for _ in range(4):
            self.c.post("/api/giris", json={"kullanici_adi": "ayse", "sifre": "yanlis", "kurum_kodu": "765432"})
        r = self.c.post("/api/giris", json={"kullanici_adi": "ayse", "sifre": "Gizli123", "kurum_kodu": "765432"})
        self.assertEqual(r.status_code, 429)
        api._hatali_girisler.clear()

        ogr = self.giris("deniz")
        ben = self.c.get("/api/ben", headers=ogr).json()
        self.assertEqual(ben["moduller"]["fazla"], "y")
        self.assertEqual(ben["moduller"]["kasa"], "")
        self.assertEqual(ben["kullanici"]["bolum_id"], self.bolum)
        r = self.c.get("/api/kasa", headers=ogr)
        self.assertEqual(r.status_code, 403)
        self.assertIn("Kasa / Banka", r.json()["hata"])
        self.assertEqual(self.c.get("/api/islem-kaydi", headers=ogr).status_code, 403)
        izl = self.giris("deneme")
        self.assertEqual(self.c.get("/api/kasa", headers=izl).status_code, 200)
        r = self.c.post("/api/fazla-calisma", headers=izl, json={"yil": YIL, "ay": 3, "personel_id": self.p_ogr, "saat": 2})
        self.assertEqual(r.status_code, 403)
        self.c.post("/api/cikis", headers=izl)
        self.assertEqual(self.c.get("/api/ben", headers=izl).status_code, 401)

    def test_ilk_giriste_sifre_degistirme(self):
        adm = self.giris("admin", "admin")
        r = self.c.get("/api/panel", headers=adm)
        self.assertEqual(r.status_code, 403)
        self.assertIn("şifrenizi", r.json()["hata"])
        self.assertEqual(self.c.post("/api/sifre", headers=adm, json={"eski": "admin", "yeni": "123"}).status_code, 400)
        self.assertEqual(self.c.post("/api/sifre", headers=adm, json={"eski": "admin", "yeni": "YeniSifre1"}).status_code, 200)
        r = self.c.get("/api/panel", headers=adm)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("nakit", r.json()["ozet"])

    def test_ogretmen_fazla_calisma_ve_mobil_onay(self):
        ogr = self.giris("deniz", cihaz="Samsung A54")
        sec = self.c.get(f"/api/fazla-calisma/secenekler?yil={YIL}&ay=3", headers=ogr).json()
        self.assertEqual([p["id"] for p in sec["personeller"]], [self.p_ogr])
        gun = next(g for g in sec["gunler"] if g["tur"] == "ogretim")
        istek = {"yil": YIL, "ay": 3, "personel_id": self.p_ogr2, "puantaj": {str(gun["gun"]): gun["azami"]},
                 "aciklama": "Zeytinyağı dolumu", "onizleme": True}
        on = self.c.post("/api/fazla-calisma", headers=ogr, json=istek).json()
        self.assertEqual(on["hatalar"], [])
        self.assertEqual(on["kayit"]["personel_id"], self.p_ogr)  # öğretmen yalnız kendisi için girer
        self.assertAlmostEqual(on["kayit"]["brut"], gun["azami"] * 67.5)
        istek["onizleme"] = False
        r = self.c.post("/api/fazla-calisma", headers=ogr, json=istek)
        self.assertEqual(r.status_code, 200, r.text)
        fid = r.json()["id"]
        fazla = dict(istek, puantaj={str(gun["gun"]): 99})
        r = self.c.post("/api/fazla-calisma", headers=ogr, json=fazla)
        self.assertEqual(r.status_code, 400)
        self.assertIn("günlük azami", r.json()["hata"])

        r = self.c.post(f"/api/onay/{FC}/{fid}/gonder", headers=ogr, json={"aciklama": "Mobilden gönderildi"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.c.put(f"/api/fazla-calisma/{fid}", headers=ogr, json=istek).status_code, 400)

        sef, tmy, mdr = self.giris("can"), self.giris("veli"), self.giris("ali", cihaz="iPhone 15")
        self.assertEqual(self.c.post(f"/api/onay/{FC}/{fid}/karar", headers=mdr, json={"onay": True}).status_code, 400)
        for h in (sef, tmy, mdr):
            bekleyen = self.c.get("/api/onay", headers=h).json()["bana_bekleyen"]
            self.assertIn(fid, [b["belge_id"] for b in bekleyen if b["belge_turu"] == "Fazla Çalışma"])
            belge = self.c.get(f"/api/onay/{FC}/{fid}", headers=h).json()
            self.assertTrue(belge["islemler"]["karar"])
            self.assertEqual(belge["detay"]["ad_soyad"], "Deniz Öğretmen")
            r = self.c.post(f"/api/onay/{FC}/{fid}/karar", headers=h, json={"onay": True, "aciklama": "Uygundur"})
            self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.db.deger("SELECT durum FROM fazla_calisma WHERE id = ?", (fid,)), "Onaylandı")
        self.assertEqual(self.c.delete(f"/api/fazla-calisma/{fid}", headers=ogr).status_code, 400)

        kayit = self.c.get("/api/islem-kaydi?istemci=Mobil", headers=mdr).json()["kayitlar"]
        ekleme = next(k for k in kayit if k["tablo"] == "fazla_calisma" and k["islem"] == "Ekleme")
        self.assertEqual((ekleme["kim"], ekleme["rol"], ekleme["bilgisayar"], ekleme["istemci"]),
                         ("Deniz Öğretmen", M.ROL_OGRETMEN, "Samsung A54", "Mobil"))
        ayrinti = self.c.get(f"/api/islem-kaydi/{ekleme['id']}", headers=mdr).json()
        self.assertTrue(any(x["alan"] == "brut" for x in ayrinti["degisiklikler"]))
        gecmis = self.db.q("SELECT karar, rol FROM onay_kaydi WHERE belge_turu = 'Fazla Çalışma' AND belge_id = ? ORDER BY id", (fid,))
        self.assertEqual([g["rol"] for g in gecmis][-3:], [M.ROL_SEF, M.ROL_TMY, M.ROL_MUDUR])

    def test_is_talebi_ve_bolum_kisiti(self):
        ogr = self.giris("deniz")
        sec = self.c.get("/api/secenekler/siparis", headers=ogr).json()
        self.assertEqual([b["id"] for b in sec["bolumler"]], [self.bolum])
        talep = {"cari_id": self.musteri, "tarih": f"{YIL}-04-01", "konu": "Belediye için zeytinyağı",
                 "kalemler": [{"urun_id": self.urun, "miktar": 10}]}
        r = self.c.post("/api/siparisler", headers=ogr, json=talep)
        self.assertEqual(r.status_code, 200, r.text)
        s = self.c.get(f"/api/siparisler/{r.json()['id']}", headers=ogr).json()
        self.assertEqual((s["durum"], s["bolum_id"], s["sozlesme_bedeli"]), ("Teklif", self.bolum, 4000))
        self.assertEqual(s["malzeme_maliyeti"], 2200)  # (5 x 40 + 20) x 10
        self.assertAlmostEqual(s["iscilik_tutari"], s["tahsis"]["azami_iscilik"])
        self.assertEqual(s["kalemler"][0]["birim_fiyat"], 400)
        r = self.c.post("/api/siparisler", headers=ogr, json=dict(talep, bolum_id=self.bolum2))
        self.assertEqual(r.status_code, 400)
        self.assertIn("kendi bölümünüz", r.json()["hata"])
        r = self.c.post("/api/siparisler", headers=ogr, json=dict(talep, kalemler=[{"urun_id": self.urun, "miktar": 1,
                                                                                    "birim_fiyat": 300}]))
        self.assertTrue(any("tespit edilen satış fiyatının" in u for u in r.json()["uyarilar"]))
        self.assertEqual(self.c.post("/api/siparisler", headers=ogr, json={"cari_id": self.musteri}).status_code, 400)
        diger = self.db.ekle("siparis", {"siparis_no": "SIP-X", "tarih": f"{YIL}-04-02", "bolum_id": self.bolum2,
                                         "konu": "Bilişim işi", "durum": "Teklif"})
        liste = self.c.get(f"/api/siparisler?yil={YIL}", headers=ogr).json()["siparisler"]
        self.assertNotIn(diger, [x["id"] for x in liste])
        self.assertEqual(self.c.get(f"/api/siparisler/{diger}", headers=ogr).status_code, 403)

    def test_masaustu_ile_cakisma(self):
        sef = self.giris("can")
        istek = {"yil": YIL, "ay": 4, "personel_id": self.p_ogr2, "saat": 2}
        fid = self.c.post("/api/fazla-calisma", headers=sef, json=istek).json()["id"]
        surum = self.c.get(f"/api/fazla-calisma?yil={YIL}&ay=4", headers=sef).json()["surum"]
        masaustu = Veritabani(self.yol)
        masaustu.oturum_ac({"kullanici_adi": "veli", "ad_soyad": "Veli Yardımcı", "rol": M.ROL_TMY}, bilgisayar="TMY-PC")
        masaustu.guncelle("fazla_calisma", fid, {"aciklama": "Masaüstünde düzeltildi"})
        masaustu.kapat()
        r = self.c.put(f"/api/fazla-calisma/{fid}", headers=sef, json=dict(istek, saat=3, surum=surum))
        self.assertEqual(r.status_code, 409)
        self.assertIn("Veli Yardımcı", r.json()["hata"])
        yeni = self.c.get(f"/api/fazla-calisma?yil={YIL}&ay=4", headers=sef).json()["surum"]
        r = self.c.put(f"/api/fazla-calisma/{fid}", headers=sef, json=dict(istek, saat=3, surum=yeni))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.db.deger("SELECT saat FROM fazla_calisma WHERE id = ?", (fid,)), 3)
        r = self.c.post("/api/fazla-calisma", headers=sef, json=dict(istek, personel_id=self.p_bilisim))
        self.assertEqual(r.status_code, 403)

    def test_salt_okunur_lisans(self):
        ogr = self.giris("deniz")
        self.db.salt_okunur = True
        try:
            r = self.c.post("/api/fazla-calisma", headers=ogr, json={"yil": YIL, "ay": 5, "saat": 1})
            self.assertEqual(r.status_code, 403)
            self.assertEqual(self.c.get("/api/ben", headers=ogr).json()["moduller"]["fazla"], "g")
            self.assertEqual(self.c.get(f"/api/fazla-calisma?yil={YIL}&ay=5", headers=ogr).status_code, 200)
        finally:
            self.db.salt_okunur = False


if __name__ == "__main__":
    unittest.main()
