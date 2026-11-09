import asyncio
import json
import re
import time
import unittest
from datetime import date
from pathlib import Path

from dose import mevzuat
from istemci import tanimlar as T
from istemci import takvim
from istemci.supa import Supa, SupaHata, hata_coz

KOK = Path(__file__).resolve().parent.parent


class SahteTasima:
    """Records every request and answers from a route table: {(method, path prefix): (status, body)}."""

    def __init__(self, yollar=None):
        self.istekler = []
        self.yollar = yollar or {}

    async def __call__(self, yontem, url, basliklar, govde):
        yol = url.split(".co", 1)[1]
        self.istekler.append((yontem, yol, basliklar, json.loads(govde) if govde else None))
        for (y, onek), cevap in self.yollar.items():
            if y == yontem and yol.startswith(onek):
                durum, veri = cevap(yol, govde) if callable(cevap) else cevap
                return durum, json.dumps(veri) if not isinstance(veri, str) else veri
        return 404, json.dumps({"message": "yok"})


def oturum(sure=3600, belirtec="A1"):
    return {"access_token": belirtec, "refresh_token": "R1", "expires_in": sure, "user": {"id": "u"}}


def calistir(coro):
    return asyncio.run(coro)


class SupaIstemciTest(unittest.TestCase):
    def test_giris_oturumu_saklar_ve_yetki_basligi_gonderir(self):
        kayitlar = []

        async def degisti(o):
            kayitlar.append(o and o["refresh_token"])

        t = SahteTasima({("POST", "/auth/v1/token?grant_type=password"): (200, oturum()),
                         ("GET", "/rest/v1/bolum"): (200, [{"id": 1}])})
        s = Supa("https://x.supabase.co", "pk", t, degisti)

        async def akis():
            await s.giris(" Mudur@Okul.k12.tr ", "gizli")
            return await s.sec("bolum", sira="ad", aktif=1)

        self.assertEqual(calistir(akis()), [{"id": 1}])
        self.assertEqual(t.istekler[0][3]["email"], "mudur@okul.k12.tr")
        self.assertNotIn("Authorization", t.istekler[0][2])
        yontem, yol, basliklar, _ = t.istekler[1]
        self.assertEqual(basliklar["Authorization"], "Bearer A1")
        self.assertEqual(basliklar["apikey"], "pk")
        self.assertIn("aktif=eq.1", yol)
        self.assertIn("order=ad", yol)
        self.assertEqual(kayitlar, ["R1"])

    def test_suresi_dolan_belirtec_once_yenilenir(self):
        t = SahteTasima({("POST", "/auth/v1/token?grant_type=refresh_token"): (200, oturum(belirtec="A2")),
                         ("POST", "/rest/v1/rpc/dose_ben"): (200, {"uye": False})})
        s = Supa("https://x.supabase.co", "pk", t)
        s.oturum = {"access_token": "A1", "refresh_token": "R0", "expires_at": int(time.time()) + 10}
        calistir(s.rpc("dose_ben"))
        self.assertEqual(t.istekler[0][3], {"refresh_token": "R0"})
        self.assertEqual(t.istekler[1][2]["Authorization"], "Bearer A2")

    def test_guncelleme_surumu_ve_filtreyi_gonderir(self):
        t = SahteTasima({("PATCH", "/rest/v1/cari"): (200, [{"id": 5, "surum": 4}])})
        s = Supa("https://x.supabase.co", "pk", t)
        s.oturum = {"access_token": "A", "refresh_token": "R", "expires_at": int(time.time()) + 3600}
        sonuc = calistir(s.guncelle("cari", {"unvan": "X", "surum": 3}, id=5))
        yontem, yol, basliklar, govde = t.istekler[0]
        self.assertEqual(sonuc["surum"], 4)
        self.assertEqual(govde, {"unvan": "X", "surum": 3})
        self.assertIn("id=eq.5", yol)
        self.assertEqual(basliklar["Prefer"], "return=representation")

    def test_bos_guncelleme_yetkisizlik_sayilir(self):
        t = SahteTasima({("PATCH", "/rest/v1/cari"): (200, [])})
        s = Supa("https://x.supabase.co", "pk", t)
        with self.assertRaises(SupaHata) as h:
            calistir(s.guncelle("cari", {"unvan": "X"}, id=5))
        self.assertIn("yetkiniz yok", h.exception.mesaj)

    def test_cakisma_ipucu_tanir(self):
        hata = hata_coz(400, json.dumps({"code": "P0001", "hint": "surum_cakismasi",
                                         "message": "Bu kaydı siz düzenlerken Ali (Sayman) değiştirdi"}))
        self.assertTrue(hata.cakisma)
        self.assertIn("Sayman", hata.mesaj)

    def test_hata_turkcelestirilir(self):
        self.assertEqual(hata_coz(400, json.dumps({"error_code": "invalid_credentials", "msg": "x"})).mesaj,
                         "E-posta veya şifre hatalı.")
        self.assertIn("doğrulanmamış", hata_coz(400, json.dumps({"error_code": "email_not_confirmed"})).mesaj)
        self.assertEqual(hata_coz(403, json.dumps({"code": "42501", "message": "new row violates row-level security "
                                                                              "policy for table \"cari\""})).mesaj,
                         "Bu işlem için yetkiniz yok.")
        self.assertEqual(hata_coz(400, json.dumps({"code": "22023", "message": "'Unvan' alanı zorunludur."})).mesaj,
                         "'Unvan' alanı zorunludur.")
        self.assertIn("Sunucu şu an yanıt vermiyor", hata_coz(502, "<html>").mesaj)

    def test_401_oturumu_dusurur(self):
        dusen = []

        async def degisti(o):
            dusen.append(o)

        t = SahteTasima({("GET", "/rest/v1/kurum"): (401, {"code": "PGRST301", "message": "JWT expired"})})
        s = Supa("https://x.supabase.co", "pk", t, degisti)
        s.oturum = {"access_token": "A", "refresh_token": "R", "expires_at": int(time.time()) + 3600}
        with self.assertRaises(SupaHata) as h:
            calistir(s.sec("kurum"))
        self.assertTrue(h.exception.oturum_gecersiz)
        self.assertIsNone(s.oturum)
        self.assertEqual(dusen, [None])


class DonusumTest(unittest.TestCase):
    def test_girdi_donusumleri(self):
        self.assertEqual(T.girdiden("oran", "KDV", "20"), 0.2)
        self.assertEqual(T.girdiden("oran", "KDV", "0,5"), 0.005)
        self.assertEqual(T.girdiden("para", "Fiyat", "1.234,56"), 1234.56)
        self.assertEqual(T.girdiden("para", "Fiyat", "1234.5"), 1234.5)
        self.assertEqual(T.girdiden("para", "Fiyat", "1.250.000"), 1250000.0)
        self.assertEqual(T.girdiden("ondalik", "Miktar", "0.005"), 0.005)
        self.assertEqual(T.girdiden("tarih", "Tarih", "05.03.2026"), "2026-03-05")
        self.assertEqual(T.girdiden("tarih", "Tarih", "2026-03-05"), "2026-03-05")
        self.assertEqual(T.girdiden("bool", "Aktif", True), 1)
        self.assertEqual(T.girdiden("fk_bolum", "Bölüm", "7"), 7)
        self.assertIsNone(T.girdiden("metin", "Ad", "   "))
        with self.assertRaisesRegex(ValueError, "'Fiyat' geçerli bir sayı"):
            T.girdiden("para", "Fiyat", "on lira")
        with self.assertRaisesRegex(ValueError, "GG.AA.YYYY"):
            T.girdiden("tarih", "Tarih", "31.02.2026")

    def test_gosterim(self):
        self.assertEqual(T.gosterim("oran", 0.2), "20")
        self.assertEqual(T.gosterim("para", 1234.5), "1.234,50")
        self.assertEqual(T.gosterim("tarih", "2026-03-05"), "05.03.2026")
        self.assertEqual(T.gosterim("metin", None), "")
        self.assertIs(T.gosterim("bool", 0), False)

    def test_form_verisi_zorunlu_ve_salt(self):
        alanlar = T.KURUM_ALANLARI
        with self.assertRaisesRegex(ValueError, "Okul adı"):
            T.form_verisi(alanlar, {"okul_adi": " ", "kurum_kodu": "123456"})
        veri = T.form_verisi(alanlar, {"okul_adi": "Derik MTAL", "kurum_kodu": "999", "tahsis_sermaye": "10.000"})
        self.assertNotIn("kurum_kodu", veri)
        self.assertEqual(veri["tahsis_sermaye"], 10000.0)

    def test_arama(self):
        self.assertTrue(T.eslesir({"ad_soyad": "Ayşe Yılmaz", "tckn": "123"}, "yıl", "personel"))
        self.assertTrue(T.eslesir({"unvan": "X", "vkn_tckn": "0010000009"}, "00100", "cari"))
        self.assertFalse(T.eslesir({"ad": "Masa"}, "sandalye", "urun"))

    def test_siparis_kalem_tutari_yuvarlama_ve_indirim(self):
        self.assertEqual(T.siparis_kalem_tutari(3, 10.005, 10), (30.02, 3.0, 27.02))
        with self.assertRaisesRegex(ValueError, "Miktar pozitif"):
            T.siparis_kalem_tutari(0, 10)
        with self.assertRaisesRegex(ValueError, "indirim"):
            T.siparis_kalem_tutari(1, 10, 101)


class SecenekTohumTest(unittest.TestCase):
    def test_tohum_mevzuatla_ayni(self):
        sql = (KOK / "supabase" / "migrations" / "20261030000100_cok_okul_sema.sql").read_text(encoding="utf-8")
        govde = sql[sql.index("INSERT INTO public.secenek"):sql.index(") AS l (liste")]
        listeler = {}
        for ad, dizi in re.findall(r"\('(\w+)',\s*ARRAY\[(.*?)\]", govde, re.S):
            listeler[ad] = re.findall(r"'((?:[^']|'')*)'", dizi)
        beklenen = {
            "utp_yontemi": list(mevzuat.UTP_BOLUM_YONTEMLERI), "hizmet_sinifi": list(mevzuat.HIZMET_SINIFLARI),
            "dose_gorevi": list(mevzuat.DOSE_GOREVLERI), "cari_tur": list(mevzuat.CARI_TURLERI),
            "malzeme_tur": list(mevzuat.MALZEME_TURLERI), "urun_tur": list(mevzuat.URUN_TURLERI),
            "birim": list(mevzuat.BIRIMLER), "ucret_esasi": list(mevzuat.UCRET_ESASLARI),
            "unvan_grubu": [str(k) for k in sorted(mevzuat.UNVAN_GRUPLARI)],
        }
        for ad, degerler in beklenen.items():
            self.assertEqual(listeler[ad], degerler, ad)
        kullanilan = {liste for alanlar in T.TANIM_ALANLARI.values() for *_, liste in alanlar if liste}
        self.assertLessEqual(kullanilan, set(listeler))
        self.assertEqual(T.ROLLER, list(mevzuat.ROLLER))


class TakvimTest(unittest.TestCase):
    def test_hazine_payi_ve_yil_donumu(self):
        sureler = {s["ad"]: s for s in takvim.yaklasan_sureler(date(2026, 12, 16))}
        self.assertEqual(sureler["Hazine payı"]["son_gun"], date(2026, 12, 20))
        self.assertEqual(sureler["Hazine payı"]["kalan"], 4)
        self.assertEqual(takvim.sure_cumlesi(sureler["Hazine payı"]), "Hazine payına 4 gün var.")
        self.assertEqual(sureler["SHÇEK payı"]["son_gun"], date(2027, 1, 31))
        self.assertEqual(sureler["Merkez payı"]["son_gun"], date(2027, 2, 28))
        sonraki = {s["ad"]: s for s in takvim.yaklasan_sureler(date(2026, 12, 29))}
        self.assertEqual(sonraki["KDV beyan ve ödeme"]["son_gun"], date(2027, 1, 28))
        self.assertEqual(takvim.yaklasan_sureler(date(2028, 2, 1))[0]["ad"], "Bakanlık aylık mizan")
        artik = {s["ad"]: s for s in takvim.yaklasan_sureler(date(2028, 2, 1))}
        self.assertEqual(artik["Merkez payı"]["son_gun"], date(2028, 2, 29))
        self.assertEqual(artik["Bakanlık aylık mizan"]["son_gun"], date(2028, 2, 5))
        self.assertEqual(artik["Üç aylık faaliyet raporu"]["son_gun"], date(2028, 4, 5))
        self.assertEqual(takvim.sure_cumlesi({"ad": "KDV beyan ve ödeme", "kalan": 0}),
                         "KDV beyan ve ödeme için son gün bugün.")


# ---------------------------------------------------------------------- UI smoke on a fake page
class SahteTercih:
    def __init__(self):
        self.d = {}

    async def get(self, k):
        return self.d.get(k)

    async def set(self, k, v):
        self.d[k] = v

    async def remove(self, k):
        self.d.pop(k, None)


class SahteSayfa:
    def __init__(self, genislik):
        self.width = genislik
        self.controls = []
        self.appbar = self.drawer = self.theme = self.on_resize = None
        self.title = ""
        self.padding = 0
        self.diyaloglar = []
        self.shared_preferences = SahteTercih()

    def add(self, *k):
        self.controls.extend(k)

    def update(self, *_):
        pass

    def show_dialog(self, d):
        self.diyaloglar.append(d)

    def pop_dialog(self):
        return self.diyaloglar.pop() if self.diyaloglar else None

    def run_task(self, fn, *a):
        return asyncio.ensure_future(fn(*a))

    async def show_drawer(self):
        pass

    async def close_drawer(self):
        pass


BEN = {"uye": True, "rol": "Okul Müdürü", "ad_soyad": "Ali Veli", "eposta": "m@o.k12.tr", "bolum_id": None,
       "yetkiler": {"kurum": "y", "bolum": "y", "personel": "y", "ogrenci": "g", "cari": "g", "malzeme": "g",
                    "urun": "g", "siparis": "y", "kullanici": "y", "islem_kaydi": "g", "resmi_yazi": "y"},
       "okul": {"id": 1, "ad": "Derik MTAL", "kurum_kodu": "123456", "lisans_bitis": None, "salt_okunur": False}}


class ArayuzTest(unittest.TestCase):
    def test_merkez_oranlari_kesin_ve_sinirlidir(self):
        from istemci.mevzuat import kesin_oran
        for metin, beklenen in (("0", "0"), ("-0", "0"), ("100", "1"),
                                ("0,759", "0.00759"), ("6,00000001", "0.0600000001")):
            with self.subTest(metin=metin):
                self.assertEqual(kesin_oran(metin, "Kâr"), beklenen)
        for metin in ("", "NaN", "Infinity", "-1", "100,01", "0,000000001"):
            with self.subTest(metin=metin):
                with self.assertRaises(ValueError):
                    kesin_oran(metin, "Kâr")

    def test_merkez_yayini_ag_kaybinda_formu_ve_istek_kimligini_korur(self):
        yollar = self._temel_yollar([])
        yollar[("POST", "/rest/v1/rpc/dose_ben")] = (200, {
            "uye": True, "merkez_mevzuat": True, "rol": "Merkez Mevzuat Yöneticisi",
            "ad_soyad": "Merkez Yönetici", "okul": None, "yetkiler": {"merkez_mevzuat": "y"}})
        yollar[("POST", "/rest/v1/rpc/dose_mevzuat_merkez_veri")] = (200, {
            "alanlar": [{"anahtar": "pb_kar_orani", "etiket": "Kâr", "aciklama": "Sipariş bedeline oranı"}],
            "yayinlar": []})
        yanitlar = [(503, {"message": "Bağlantı kesildi"}), (200, {"id": 1})]
        yollar[("POST", "/rest/v1/rpc/dose_mevzuat_yayinla")] = lambda *_: yanitlar.pop(0)
        app, sayfa = self._uygulama(400, yollar)

        async def akis():
            import flet as ft
            await app.ben_yukle()
            app._dongu.cancel()
            self.assertEqual([s[0] for s in app.gorunur_sayfalar()], ["ana", "merkez_mevzuat"])
            await app.sayfa_ac("merkez_mevzuat")
            ekran = app.ekran
            ekran._yeni()
            form = ekran.form
            form["baslangic"].value = "01.01.2026"
            form["kaynak"].value = "İncelenen örnek test kaynağı"
            form["pb_kar_orani"].value = "6,00000001"
            ekran._degisti()
            await ekran.uzaktan_degisti()
            self.assertIs(ekran.form, form)
            await ekran._yayinla(ft.FilledButton("Yayını kaydet"))
            self.assertIs(ekran.form, form)
            self.assertIn("kaydedilmiş olabilir", sayfa.diyaloglar[-1].content.value)
            await ekran._yayinla(ft.FilledButton("Yayını kaydet"))
            self.assertIsNone(ekran.form)
            self.assertEqual(sayfa.diyaloglar[-1].content.value, "Merkez parametre yayını kaydedildi.")

        calistir(akis())
        istekler = [i[3] for i in app.supa.tasima.istekler if "/rpc/dose_mevzuat_yayinla" in i[1]]
        self.assertEqual(len(istekler), 2)
        self.assertEqual(istekler[0]["p_istek"], istekler[1]["p_istek"])
        self.assertEqual(istekler[0]["p_degerler"], {"pb_kar_orani": "0.0600000001"})

    def test_merkez_yayini_surerken_form_ve_gezinme_kilitlenir(self):
        yollar = self._temel_yollar([])
        yollar[("POST", "/rest/v1/rpc/dose_ben")] = (200, {
            "uye": True, "merkez_mevzuat": True, "rol": "Merkez Mevzuat Yöneticisi",
            "ad_soyad": "Merkez Yönetici", "okul": None, "yetkiler": {"merkez_mevzuat": "y"}})
        yollar[("POST", "/rest/v1/rpc/dose_mevzuat_merkez_veri")] = (200, {
            "alanlar": [{"anahtar": "pb_kar_orani", "etiket": "Kâr", "aciklama": "Sipariş bedeline oranı"}],
            "yayinlar": []})
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            import flet as ft
            basladi, devam = asyncio.Event(), asyncio.Event()
            tasima = app.supa.tasima

            async def bekleyen_tasima(yontem, url, basliklar, govde):
                if "/rpc/dose_mevzuat_yayinla" in url:
                    basladi.set()
                    await devam.wait()
                    return 200, '{"id": 1}'
                return await tasima(yontem, url, basliklar, govde)

            app.supa.tasima = bekleyen_tasima
            await app.ben_yukle()
            app._dongu.cancel()
            await app.sayfa_ac("merkez_mevzuat")
            ekran = app.ekran
            ekran._yeni()
            form = ekran.form
            form["baslangic"].value = "01.01.2026"
            form["kaynak"].value = "Kontrol edilmiş örnek kaynak"
            form["pb_kar_orani"].value = "10"
            islem = asyncio.create_task(ekran._yayinla(ft.FilledButton("Yayını kaydet")))
            await basladi.wait()
            try:
                self.assertTrue(ekran.islemde)
                self.assertTrue(all(k.disabled for k in form.values()))
                await app.sayfa_ac("ana")
                self.assertEqual(app.sayfa, "merkez_mevzuat")
                ekran._kapat()
                self.assertIs(ekran.form, form)
                self.assertIn("tamamlanana kadar", sayfa.diyaloglar[-1].content.value)
            finally:
                devam.set()
                await islem
            self.assertFalse(ekran.islemde)
            self.assertIsNone(ekran.form)

        calistir(akis())

    def _uygulama(self, genislik, yollar):
        from istemci.uygulama import Uygulama
        sayfa = SahteSayfa(genislik)
        app = Uygulama(sayfa)
        app.supa.tasima = SahteTasima(yollar)
        app.supa.oturum = {"access_token": "A", "refresh_token": "R", "expires_at": int(time.time()) + 3600}
        return app, sayfa

    def _temel_yollar(self, bolumler):
        yollar = {("POST", "/rest/v1/rpc/dose_ben"): (200, BEN),
                ("POST", "/rest/v1/rpc/dose_son_degisiklik"): (200, 10),
                ("GET", "/rest/v1/secenek"): (200, [{"liste": "utp_yontemi", "deger": "A", "etiket": "A"}]),
                ("GET", "/rest/v1/bolum"): lambda yol, g: (200, bolumler),
                ("GET", "/rest/v1/kurum"): (200, [{"okul_id": 1, "okul_adi": "Derik MTAL", "surum": 1,
                                                   "kurum_kodu": "123456", "guncelleyen": "Ali Veli (Okul Müdürü)"}]),
                ("GET", "/rest/v1/islem_log"): (200, [{"id": 1, "islem": "ekle", "tablo": "bolum", "kayit_id": 1,
                                                       "zaman": "2026-10-30 10:00", "ad_soyad": "Ali", "rol": "Sayman"}]),
                ("POST", "/rest/v1/rpc/dose_kullanicilar"): (200, {"uyeler": [
                    {"id": "u1", "eposta": "m@o.k12.tr", "ad_soyad": "Ali Veli", "rol": "Okul Müdürü", "aktif": True,
                     "ben": True}], "davetler": [{"eposta": "s@o.k12.tr", "ad_soyad": "Sayman", "rol": "Sayman",
                                                  "bitis": "2026-11-06"}]}),
                ("GET", "/rest/v1/personel"): (200, []), ("GET", "/rest/v1/ogrenci"): (200, []),
                ("GET", "/rest/v1/cari"): (200, []), ("GET", "/rest/v1/malzeme"): (200, []),
                ("GET", "/rest/v1/urun"): (200, [])}
        yollar[("POST", "/rest/v1/rpc/dose_siparis_veri")] = (200, {"cariler": [], "bolumler": [], "urunler": []})
        yollar[("POST", "/rest/v1/rpc/dose_siparisler")] = (200, [])
        yollar[("POST", "/rest/v1/rpc/dose_gorevlerim")] = (200, {"gorevler": []})
        yollar[("POST", "/rest/v1/rpc/dose_ana_ozet")] = (200, {
            "yil": 2026, "finans_gorunur": True, "siparis_gorunur": True, "siparis": 0,
            "siparis_durum": {}, "fatura_satis": "0", "fatura_alis": "0", "kasa_bakiye": "0",
            "banka_bakiye": "0", "hp_hasilat": "0"})
        yollar[("POST", "/rest/v1/rpc/dose_maliyet_veri")] = (200, {"urunler": [], "kalemler": [], "toplam": None,
                                                                     "yazabilir": False})
        yollar[("POST", "/rest/v1/rpc/dose_rapor_ozet")] = (200, {"yil": 2026, "siparis": 0, "fatura_satis": "0",
                                                                   "fatura_alis": "0", "kasa_bakiye": "0",
                                                                   "banka_bakiye": "0", "hp_hasilat": "0"})
        yollar[("POST", "/rest/v1/rpc/dose_resmi_veri")] = (200, {"yazilar": [], "yazabilir": False})
        yollar[("POST", "/rest/v1/rpc/dose_denetim_veri")] = (200, {"formlar": [], "yazabilir": False})
        yollar[("POST", "/rest/v1/rpc/dose_ys_veri")] = (200, {"yil": 2025, "kayit": None, "iptaller": [],
                                                                "varsayilan": {}, "personel": []})
        return yollar

    def test_tum_sayfalar_iki_genislikte_acilir(self):
        bolumler = [{"id": 1, "ad": "Mobilya", "aktif": 1, "surum": 1, "utp_yontemi": "A"}]
        for genislik in (1280, 400):
            app, sayfa = self._uygulama(genislik, self._temel_yollar(bolumler))

            async def akis():
                await app.ben_yukle()
                app._dongu.cancel()
                for anahtar, *_ in app.gorunur_sayfalar():
                    await app.sayfa_ac(anahtar)
                    self.assertIs(app.govde.content, app.ekran.kontrol, anahtar)
                    self.assertEqual(sayfa.diyaloglar, [], anahtar)

            calistir(akis())
            self.assertEqual(app.genis, genislik >= 900)
            self.assertIsNone(sayfa.appbar)
            self.assertIsNone(sayfa.drawer)
            # menu_kutu → Container(Row([MenuBar(controls=…)]))
            menubar = app.menu_kutu.content.content.controls[0]
            menudekiler = [o.content.value for o in menubar.controls if not getattr(o, "controls", None)]
            for grup in menubar.controls:
                menudekiler += [o.content.value for o in getattr(grup, "controls", None) or []]
            self.assertEqual(sorted(menudekiler), sorted(e for _, e, *_ in app.gorunur_sayfalar()))
            self.assertEqual(len(app.gorunur_sayfalar()), 14)

    def test_siparis_yenileme_kaydedilmemis_alani_korumali(self):
        siparis = {"id": 7, "siparis_no": "SIP-2026-00001", "tarih": "2026-10-31",
                   "konu": "Kayıtlı iş", "durum": "Taslak", "surum": 1, "kalemler": []}
        yollar = self._temel_yollar([])
        yollar[("POST", "/rest/v1/rpc/dose_siparisler")] = (200, [siparis])
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            await app.ben_yukle()
            app._dongu.cancel()
            await app.sayfa_ac("siparis")
            ekran = app.ekran
            ekran._sec(ekran.kayitlar[0])
            ekran.form["konu"].value = "Kaydedilmemiş değişiklik"
            await ekran.uzaktan_degisti()
            self.assertEqual(ekran.form["konu"].value, "Kaydedilmemiş değişiklik")
            ekran._yeni()
            self.assertEqual(ekran.form["konu"].value, "Kaydedilmemiş değişiklik")
            self.assertIn("Kaydedilmemiş", sayfa.diyaloglar[-1].content.value)
            sayfa.pop_dialog()
            ekran._yenile()
            self.assertEqual(ekran.form["konu"].value, "Kaydedilmemiş değişiklik")
            self.assertIn("Kaydedilmemiş", sayfa.diyaloglar[-1].content.value)
            sayfa.pop_dialog()
            await ekran._gonder()
            self.assertEqual(ekran.form["konu"].value, "Kaydedilmemiş değişiklik")
            self.assertFalse(any("/rpc/dose_siparis_gonder" in istek[1] for istek in app.supa.tasima.istekler))
            self.assertIn("kayded", sayfa.diyaloglar[-1].content.value.lower())

        calistir(akis())

    def test_siparis_oran_ve_birim_fiyat_kesinligini_korumali(self):
        siparis = {"id": 7, "siparis_no": "SIP-2026-00001", "tarih": "2026-10-31",
                   "cari_id": 1, "bolum_id": 1, "konu": "İş", "ucret_esasi": "A", "kdv_orani": 0.2,
                   "durum": "Taslak", "surum": 1,
                   "kalemler": [{"aciklama": "A", "miktar": 1, "birim_fiyat": 50, "iskonto_orani": 0.0057},
                                {"aciklama": "B", "miktar": 1, "birim_fiyat": 1.005, "iskonto_orani": 0}]}
        yollar = self._temel_yollar([])
        yollar[("POST", "/rest/v1/rpc/dose_siparisler")] = (200, [siparis])
        app, _ = self._uygulama(1280, yollar)

        async def akis():
            await app.ben_yukle()
            app._dongu.cancel()
            await app.sayfa_ac("siparis")
            ekran = app.ekran
            ekran._sec(ekran.kayitlar[0])
            self.assertEqual(ekran.kalem_formlari[1]["birim_fiyat"].value, "1,005")
            _, kalemler = ekran._form_verisi()
            self.assertEqual(str(kalemler[0]["iskonto_orani"]), "0.0057")
            self.assertEqual(T.siparis_kalem_tutari(1, 50, 0.57)[2], 49.71)

        calistir(akis())

    def test_siparis_duzenlerken_sayfa_degistirme_ve_cikis_onay_ister(self):
        yollar = self._temel_yollar([])
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            await app.ben_yukle()
            app._dongu.cancel()
            await app.sayfa_ac("siparis")
            ekran = app.ekran
            ekran._yeni()
            ekran.form["konu"].value = "Kaydedilmemiş iş"
            ekran.duzen()
            self.assertEqual(ekran.form["konu"].value, "Kaydedilmemiş iş")
            await app.sayfa_ac("bolum")
            self.assertIs(app.ekran, ekran)
            self.assertIn("Kaydedilmemiş", sayfa.diyaloglar[-1].content.value)
            sayfa.pop_dialog()
            await app.cikis()
            self.assertIs(app.ekran, ekran)
            self.assertIn("Kaydedilmemiş", sayfa.diyaloglar[-1].content.value)
            sayfa.pop_dialog()
            await app.sayfa_ac("bolum")
            await sayfa.diyaloglar[-1].actions[1].on_click(None)
            self.assertIsNot(app.ekran, ekran)
            self.assertEqual(app.sayfa, "bolum")

        calistir(akis())

    def _stok_yollari(self):
        yollar = self._temel_yollar([])
        sayman = dict(BEN, rol="Sayman", yetkiler={**BEN["yetkiler"], "stok": "y"})
        yollar[("POST", "/rest/v1/rpc/dose_ben")] = (200, sayman)
        yollar[("POST", "/rest/v1/rpc/dose_stok_veri")] = (200, {
            "kartlar": [{"id": 1, "ad": "Kereste", "tur": "İlk Madde ve Malzeme", "birim": "Adet",
                         "aktif": 1, "miktar": "0", "tutar": "0"}],
            "hareketler": []})
        yollar[("POST", "/rest/v1/rpc/dose_finans_tanimlari")] = (200, {
            "hesaplar": [{"kod": "500", "ad": "Sermaye"}], "vergi_hesaplari": []})
        return yollar

    async def _stok_formu_ac(self, app):
        await app.ben_yukle()
        app._dongu.cancel()
        await app.sayfa_ac("stok")
        ekran = app.ekran
        ekran._yeni()
        ekran.form["malzeme"].value = "1"
        ekran.form["yon"].value = "Giriş"
        ekran.form["miktar"].value = "1"
        ekran.form["tutar"].value = "10"
        ekran.form["hesap"].value = "500"
        ekran.form["aciklama"].value = "Açılış"
        ekran._degisti()
        return ekran

    def test_stok_baglanti_kaybinda_ayni_istekle_tekrar_dener(self):
        yollar = self._stok_yollari()
        sayac = [0]

        def kaydet(_yol, _govde):
            sayac[0] += 1
            if sayac[0] == 1:
                raise SupaHata("Bağlantı kesildi.", 0, "ag")
            return 200, {"id": 9, "yevmiye_id": 10}

        yollar[("POST", "/rest/v1/rpc/dose_stok_kaydet")] = kaydet
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            ekran = await self._stok_formu_ac(app)
            await ekran._kaydet(ft_dugme())
            self.assertTrue(ekran.kaydedilmemis())
            self.assertIn("kaydedilmiş olabilir", sayfa.diyaloglar[-1].content.value)
            await ekran._kaydet(ft_dugme())
            self.assertIsNone(ekran.form)
            self.assertIn("kaydedildi", sayfa.diyaloglar[-1].content.value)

        calistir(akis())
        istekler = [i[3] for i in app.supa.tasima.istekler if "/rpc/dose_stok_kaydet" in i[1]]
        self.assertEqual(len(istekler), 2)
        self.assertEqual(istekler[0], istekler[1])

    def test_stok_kaydedildikten_sonra_yenileme_hatasi_aciklanir(self):
        yollar = self._stok_yollari()
        stok_veri = yollar[("POST", "/rest/v1/rpc/dose_stok_veri")][1]
        sayac = [0]

        def stok(_yol, _govde):
            sayac[0] += 1
            return (200, stok_veri) if sayac[0] == 1 else (503, {"message": "Listeye ulaşılamıyor."})

        yollar[("POST", "/rest/v1/rpc/dose_stok_veri")] = stok
        yollar[("POST", "/rest/v1/rpc/dose_stok_kaydet")] = (200, {"id": 9, "yevmiye_id": 10})
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            ekran = await self._stok_formu_ac(app)
            await ekran._kaydet(ft_dugme())
            self.assertIsNone(ekran.form)
            self.assertIn("kaydedildi", sayfa.diyaloglar[-1].content.value)
            self.assertIn("liste yenilenemedi", sayfa.diyaloglar[-1].content.value)

        calistir(akis())

    def test_stok_kaydi_sururken_form_ve_sayfa_kilitlenir(self):
        yollar = self._stok_yollari()
        yollar[("POST", "/rest/v1/rpc/dose_stok_kaydet")] = (200, {"id": 9, "yevmiye_id": 10})
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            ekran = await self._stok_formu_ac(app)
            basladi, devam = asyncio.Event(), asyncio.Event()
            onceki_tasima = app.supa.tasima

            async def yavas(yontem, url, basliklar, govde):
                if "/rpc/dose_stok_kaydet" in url:
                    basladi.set()
                    await devam.wait()
                return await onceki_tasima(yontem, url, basliklar, govde)

            app.supa.tasima = yavas
            gorev = asyncio.create_task(ekran._kaydet(ft_dugme()))
            await basladi.wait()
            self.assertTrue(ekran.islemde)
            self.assertTrue(ekran.form["miktar"].disabled)
            ekran._kapat()
            self.assertIsNotNone(ekran.form)
            await app.sayfa_ac("ana")
            self.assertIs(app.ekran, ekran)
            await app.cikis()
            self.assertIs(app.ekran, ekran)
            self.assertIn("tamamlanana kadar", sayfa.diyaloglar[-1].content.value)
            devam.set()
            await gorev
            self.assertFalse(ekran.islemde)
            self.assertIsNone(ekran.form)

        calistir(akis())

    def _fatura_yollari(self):
        yollar = self._temel_yollar([])
        sayman = dict(BEN, rol="Sayman", yetkiler={**BEN["yetkiler"], "fatura": "y"})
        yollar[("POST", "/rest/v1/rpc/dose_ben")] = (200, sayman)
        yollar[("POST", "/rest/v1/rpc/dose_fatura_secimleri")] = (200, {
            "cariler": [{"id": 1, "unvan": "Tedarikçi", "tur": "Tedarikçi"}],
            "stoklar": [], "hesaplar": [{"kod": "740", "ad": "Hizmet"}],
            "vergi_hesaplari": [], "siparisler": [],
            "temin_usulleri": [{"deger": "Doğrudan Temin", "etiket": "Doğrudan Temin (4734 md.22)"}],
            "gider_turleri": [{"deger": "Hizmet Alımı", "etiket": "Hizmet Alımı"}],
            "alis_belge_turleri": [{"deger": "e-Fatura", "etiket": "e-Fatura"}],
            "alim_belgeler": {"Doğrudan Temin": [
                {"anahtar": "ihtiyac", "etiket": "İhtiyaç / talep belgesi", "zorunlu": True},
                {"anahtar": "yaklasik_maliyet", "etiket": "Yaklaşık maliyet hesabı", "zorunlu": True},
                {"anahtar": "piyasa", "etiket": "Piyasa fiyat araştırma tutanağı", "zorunlu": True},
                {"anahtar": "onay", "etiket": "Harcama yetkilisi onay belgesi", "zorunlu": True},
                {"anahtar": "muayene", "etiket": "Muayene ve kabul tutanağı", "zorunlu": True},
                {"anahtar": "odeme", "etiket": "Ödeme belgesi / banka dekontu", "zorunlu": False}]},
            "dogrudan_temin_limit": "340391"})
        yollar[("POST", "/rest/v1/rpc/dose_faturalar")] = (200, [])
        yollar[("POST", "/rest/v1/rpc/dose_fatura_onizle")] = (200, {
            "imza": "a" * 32,
            "detay": {"matrah": "10.00", "kdv": "2.00", "tevkif_kdv": "0", "stopaj": "0", "net_tutar": "12.00",
                      "tevkifat_hesabi": None, "stopaj_hesabi": None,
                      "kalemler": [{"aciklama": "Hizmet", "tutar": "10.00", "iskonto": "0.00", "kdv": "2.00"}]}})
        yollar[("POST", "/rest/v1/rpc/dose_alim_onizle")] = (200, {
            "temin_usulu": "Doğrudan Temin", "gider_turu": "Hizmet Alımı", "belge_turu": "e-Fatura",
            "belgeler": {}, "uyarilar": []})
        yollar[("POST", "/rest/v1/rpc/dose_alim_hazirla")] = (200, {
            "temin_usulu": "Doğrudan Temin", "gider_turu": "Hizmet Alımı", "belge_turu": "e-Fatura",
            "belgeler": {}, "uyarilar": []})
        return yollar

    def _kasa_yollari(self):
        yollar = self._temel_yollar([])
        sayman = dict(BEN, rol="Sayman", yetkiler={**BEN["yetkiler"], "kasa": "y"})
        yollar[("POST", "/rest/v1/rpc/dose_ben")] = (200, sayman)
        yollar[("POST", "/rest/v1/rpc/dose_kasa_veri")] = (200, {
            "hesaplar": [{"hesap": "Kasa (100)", "bakiye": "0"}, {"hesap": "Banka (102)", "bakiye": "0"}],
            "hesap_plani": [{"kod": "500", "ad": "Sermaye"}],
            "faturalar": [{"id": 3, "tur": "Satış", "belge_no": "F-1", "cari_unvan": "Müşteri", "kalan": "100"}],
            "hareketler": []})
        return yollar

    async def _kasa_formu_ac(self, app, tur="Tahsilat"):
        await app.ben_yukle()
        app._dongu.cancel()
        await app.sayfa_ac("kasa")
        ekran = app.ekran
        ekran._yeni(tur)
        ekran.form["hesap"].value = "Kasa (100)"
        ekran.form["tutar"].value = "10"
        ekran.form["aciklama"].value = "İşlem"
        if tur == "Açılış":
            ekran.form["karsi_hesap"].value = "500"
        else:
            ekran.form["fatura"].value = "3"
        ekran._degisti()
        return ekran

    def test_kasa_baglanti_kaybinda_ayni_istekle_tekrar_dener(self):
        yollar = self._kasa_yollari()
        sayac = [0]

        def kaydet(_yol, _govde):
            sayac[0] += 1
            if sayac[0] == 1:
                raise SupaHata("Bağlantı kesildi.", 0, "ag")
            return 200, {"id": 9, "yevmiye_id": 10}

        yollar[("POST", "/rest/v1/rpc/dose_kasa_kaydet")] = kaydet
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            ekran = await self._kasa_formu_ac(app)
            await ekran._kaydet(ft_dugme())
            self.assertTrue(ekran.kaydedilmemis())
            self.assertIn("kaydedilmiş olabilir", sayfa.diyaloglar[-1].content.value)
            await ekran._kaydet(ft_dugme())
            self.assertIsNone(ekran.form)

        calistir(akis())
        istekler = [i[3] for i in app.supa.tasima.istekler if "/rpc/dose_kasa_kaydet" in i[1]]
        self.assertEqual(len(istekler), 2)
        self.assertEqual(istekler[0], istekler[1])

    def test_kasa_kaydi_sururken_form_ve_sayfa_kilitlenir(self):
        yollar = self._kasa_yollari()
        yollar[("POST", "/rest/v1/rpc/dose_kasa_kaydet")] = (200, {"id": 9, "yevmiye_id": 10})
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            ekran = await self._kasa_formu_ac(app)
            basladi, devam = asyncio.Event(), asyncio.Event()
            onceki_tasima = app.supa.tasima

            async def yavas(yontem, url, basliklar, govde):
                if "/rpc/dose_kasa_kaydet" in url:
                    basladi.set()
                    await devam.wait()
                return await onceki_tasima(yontem, url, basliklar, govde)

            app.supa.tasima = yavas
            gorev = asyncio.create_task(ekran._kaydet(ft_dugme()))
            await basladi.wait()
            self.assertTrue(ekran.islemde)
            self.assertTrue(ekran.form["tutar"].disabled)
            await app.sayfa_ac("ana")
            await app.cikis()
            self.assertIs(app.ekran, ekran)
            self.assertIn("tamamlanana kadar", sayfa.diyaloglar[-1].content.value)
            devam.set()
            await gorev
            self.assertIsNone(ekran.form)
            self.assertFalse(ekran.islemde)

        calistir(akis())

    def test_kasa_tutar_hassasiyetini_korur_ve_kurus_altini_reddeder(self):
        yollar = self._kasa_yollari()
        yollar[("POST", "/rest/v1/rpc/dose_kasa_kaydet")] = (200, {"id": 9, "yevmiye_id": 10})
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            ekran = await self._kasa_formu_ac(app, "Açılış")
            ekran.form["tutar"].value = "1,001"
            await ekran._kaydet(ft_dugme())
            self.assertIn("iki ondalık", sayfa.diyaloglar[-1].content.value)
            ekran.form["tutar"].value = "123456789012345678901234567890,99"
            await ekran._kaydet(ft_dugme())
            self.assertIsNone(ekran.form)

        calistir(akis())
        istekler = [i[3] for i in app.supa.tasima.istekler if "/rpc/dose_kasa_kaydet" in i[1]]
        self.assertEqual(len(istekler), 1)
        self.assertEqual(istekler[0]["p_tutar"], "123456789012345678901234567890.99")

    async def _fatura_formu_ac(self, app):
        await app.ben_yukle()
        app._dongu.cancel()
        await app.sayfa_ac("fatura")
        ekran = app.ekran
        ekran._yeni("Alış")
        ekran.ust["cari"].value = "1"
        ekran.ust["belge_no"].value = "A-1"
        ekran.ust["tevkifat"].value = "0"
        ekran.ust["stopaj"].value = "0"
        ekran.ust["temin_usulu"].value = "Doğrudan Temin"
        ekran.ust["gider_turu"].value = "Hizmet Alımı"
        ekran.ust["belge_turu"].value = "e-Fatura"
        for kutu in ekran.alim_isaretleri.values():
            kutu.value = True
        satir = ekran.alis_satirlari[0]
        satir["hesap"].value = "740"
        satir["aciklama"].value = "Hizmet"
        satir["miktar"].value = "1"
        satir["fiyat"].value = "10"
        satir["kdv"].value = "20"
        satir["iskonto"].value = "0"
        ekran._degisti()
        await ekran._onizle(ft_dugme())
        return ekran

    def test_fatura_baglanti_kaybinda_ayni_istekle_tekrar_dener(self):
        yollar = self._fatura_yollari()
        sayac = [0]

        def kaydet(_yol, _govde):
            sayac[0] += 1
            if sayac[0] == 1:
                raise SupaHata("Bağlantı kesildi.", 0, "ag")
            return 200, {"id": 3, "yevmiye_id": 4}

        yollar[("POST", "/rest/v1/rpc/dose_fatura_kaydet")] = kaydet
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            ekran = await self._fatura_formu_ac(app)
            await ekran._kaydet(ft_dugme())
            self.assertTrue(ekran.kaydedilmemis())
            self.assertIn("kaydedilmiş olabilir", sayfa.diyaloglar[-1].content.value)
            await ekran._kaydet(ft_dugme())
            self.assertIsNone(ekran.ust)

        calistir(akis())
        istekler = [i[3] for i in app.supa.tasima.istekler if "/rpc/dose_fatura_kaydet" in i[1]]
        self.assertEqual(len(istekler), 2)
        self.assertEqual(istekler[0], istekler[1])

    def test_eski_siparis_faturasi_icin_stok_baglantisi_acikca_onaylanir(self):
        yollar = self._fatura_yollari()
        yollar[("POST", "/rest/v1/rpc/dose_fatura_secimleri")][1]["siparisler"] = [{
            "id": 5, "siparis_no": "S-5", "konu": "Eski sipariş", "cari_id": 2,
            "kalemler": [{"id": 6, "aciklama": "Hizmet", "miktar": "1", "kalan": "1", "birim": "Adet",
                           "malzeme_id": None, "malzeme_ad": None, "stok_baglanti_kaynagi": None}]}]
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            await app.ben_yukle()
            app._dongu.cancel()
            await app.sayfa_ac("fatura")
            ekran = app.ekran
            ekran._yeni("Satış")
            ekran._siparis_uygula("5")
            ekran.ust["belge_no"].value = "S-1"
            ekran.ust["tevkifat"].value = "0"
            ekran.ust["stopaj"].value = "0"
            satir = ekran.satis_satirlari[0]
            satir["miktar"].value = "1"
            await ekran._onizle(ft_dugme())
            self.assertIn("bağlantısını", sayfa.diyaloglar[-1].content.value)
            self.assertIsNone(ekran.onizleme)
            satir["eski_baglanti_onayi"].value = True
            await ekran._onizle(ft_dugme())
            self.assertTrue(ekran.hazir["p_kalemler"][0]["eski_baglanti_onayi"])

        calistir(akis())

    def test_finans_ters_kaydi_baglanti_kaybinda_ayni_istekle_denenir(self):
        for anahtar, rpc_adi, yollar in [
            ("stok", "dose_stok_tersle", self._stok_yollari()),
            ("fatura", "dose_fatura_tersle", self._fatura_yollari()),
            ("kasa", "dose_kasa_tersle", self._kasa_yollari()),
        ]:
            with self.subTest(ekran=anahtar):
                sayac = [0]

                def tersle(_yol, _govde):
                    sayac[0] += 1
                    if sayac[0] == 1:
                        raise SupaHata("Bağlantı kesildi.", 0, "ag")
                    return 200, {"id": 9, "yevmiye_id": 10}

                yollar[("POST", "/rest/v1/rpc/" + rpc_adi)] = tersle
                app, sayfa = self._uygulama(1280, yollar)

                async def akis():
                    await app.ben_yukle()
                    app._dongu.cancel()
                    await app.sayfa_ac(anahtar)
                    ekran = app.ekran
                    ekran._ters_dialog({"id": 9})
                    dialog = sayfa.diyaloglar[-1]
                    gerekce = dialog.content.controls[1]
                    gerekce.value = "Düzeltme"
                    await dialog.actions[1].on_click(None)
                    self.assertIn("oluşmuş olabilir", sayfa.diyaloglar[-1].content.value)
                    sayfa.pop_dialog()
                    await dialog.actions[1].on_click(None)
                    self.assertFalse(ekran.islemde)

                calistir(akis())
                istekler = [i[3] for i in app.supa.tasima.istekler if "/rpc/" + rpc_adi in i[1]]
                self.assertEqual(len(istekler), 2)
                self.assertEqual(istekler[0], istekler[1])

    def test_fatura_kaydi_sururken_duzenleme_ve_sayfa_degistirme_engellenir(self):
        yollar = self._fatura_yollari()
        yollar[("POST", "/rest/v1/rpc/dose_fatura_kaydet")] = (200, {"id": 3, "yevmiye_id": 4})
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            ekran = await self._fatura_formu_ac(app)
            basladi, devam = asyncio.Event(), asyncio.Event()
            onceki_tasima = app.supa.tasima

            async def yavas(yontem, url, basliklar, govde):
                if "/rpc/dose_fatura_kaydet" in url:
                    basladi.set()
                    await devam.wait()
                return await onceki_tasima(yontem, url, basliklar, govde)

            app.supa.tasima = yavas
            gorev = asyncio.create_task(ekran._kaydet(ft_dugme()))
            await basladi.wait()
            self.assertTrue(ekran.islemde)
            self.assertTrue(ekran.ust["belge_no"].disabled)
            self.assertTrue(ekran.alis_satirlari[0]["fiyat"].disabled)
            await app.sayfa_ac("ana")
            self.assertIs(app.ekran, ekran)
            self.assertIn("tamamlanana kadar", sayfa.diyaloglar[-1].content.value)
            await app.cikis()
            self.assertIs(app.ekran, ekran)
            devam.set()
            await gorev
            self.assertFalse(ekran.islemde)
            self.assertIsNone(ekran.ust)

        calistir(akis())

    def test_alis_faturasi_temin_ve_belgeleri_kayittan_once_hazirlar(self):
        yollar = self._fatura_yollari()
        yollar[("POST", "/rest/v1/rpc/dose_fatura_kaydet")] = (200, {"id": 3, "yevmiye_id": 4})
        app, _ = self._uygulama(1280, yollar)

        async def akis():
            ekran = await self._fatura_formu_ac(app)
            self.assertEqual(ekran.onizleme["alim"]["temin_usulu"], "Doğrudan Temin")
            self.assertTrue(ekran.hazir["alim"]["belgeler"]["ihtiyac"])
            await ekran._kaydet(ft_dugme())
            self.assertIsNone(ekran.ust)

        calistir(akis())
        alimlar = [i[3] for i in app.supa.tasima.istekler if "/rpc/dose_alim_hazirla" in i[1]]
        faturalar = [i[3] for i in app.supa.tasima.istekler if "/rpc/dose_fatura_kaydet" in i[1]]
        self.assertEqual(len(alimlar), 1)
        self.assertEqual(len(faturalar), 1)
        self.assertEqual(alimlar[0]["p_istek"], faturalar[0]["p_istek"])
        self.assertEqual(alimlar[0]["p_alim"]["temin_usulu"], "Doğrudan Temin")
        self.assertEqual(alimlar[0]["p_matrah"], "10.00")
        self.assertNotIn("alim", faturalar[0])
        self.assertNotIn("p_alim", faturalar[0])

    def test_tanim_kaydet_surum_ve_cakisma(self):
        bolumler = [{"id": 1, "ad": "Mobilya", "aktif": 1, "surum": 3, "utp_yontemi": "A", "guncelleyen": "X"}]
        yollar = self._temel_yollar(bolumler)
        yollar[("PATCH", "/rest/v1/bolum")] = (400, {"code": "P0001", "hint": "surum_cakismasi",
                                                     "message": "Bu kaydı siz düzenlerken Ayşe (Sayman) değiştirdi"})
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            await app.ben_yukle()
            app._dongu.cancel()
            await app.sayfa_ac("bolum")
            ekran = app.ekran
            ekran._sec(ekran.kayitlar[0])
            ekran.form.kontroller["ad"].value = "Mobilya Atölyesi"
            ekran.form.kirli = True
            bolumler[0] = dict(bolumler[0], surum=4, ad="Mobilya-2", guncelleyen="Ayşe (Sayman)")
            await ekran.uzaktan_degisti()
            self.assertTrue(ekran.serit.visible)
            self.assertEqual(ekran.form.kontroller["ad"].value, "Mobilya Atölyesi")
            await ekran._kaydet(ft_dugme())
            return ekran

        ekran = calistir(akis())
        patch = [i for i in app.supa.tasima.istekler if i[0] == "PATCH"][0]
        self.assertEqual(patch[3]["surum"], 3)
        self.assertEqual(patch[3]["ad"], "Mobilya Atölyesi")
        self.assertNotIn("okul_id", patch[3])
        self.assertIn("Ayşe (Sayman)", sayfa.diyaloglar[-1].content.value)
        self.assertEqual(ekran.secili["surum"], 4)
        self.assertEqual(ekran.form.kontroller["ad"].value, "Mobilya-2")
        self.assertFalse(ekran.serit.visible)

    def test_salt_okunur_tanimda_kaydet_yok(self):
        yollar = self._temel_yollar([])
        yollar[("GET", "/rest/v1/cari")] = (200, [{"id": 2, "unvan": "ABC Ltd", "tur": "Müşteri", "aktif": 1,
                                                   "surum": 1}])
        app, _ = self._uygulama(400, yollar)

        async def akis():
            await app.ben_yukle()
            app._dongu.cancel()
            await app.sayfa_ac("cari")
            app.ekran._sec(app.ekran.kayitlar[0])
            return app.ekran

        ekran = calistir(akis())
        self.assertFalse(ekran.yazabilir)
        self.assertIs(ekran.kontrol.content, ekran.form_kutusu)
        self.assertTrue(ekran.form.kontroller["unvan"].read_only)
        # Son kontrol yuzey_kart: Container(Column([form, Row([kaydet, sil])]))
        kart = ekran.form_kutusu.controls[-1]
        dugmeler = kart.content.controls[-1].controls
        self.assertFalse(any(d.visible for d in dugmeler))

    def test_uye_olmayan_etkinlestirme_ekrani(self):
        yollar = {("POST", "/rest/v1/rpc/dose_ben"): (200, {"uye": False, "eposta": "m@o", "eposta_dogrulandi": True})}
        app, sayfa = self._uygulama(400, yollar)
        calistir(app.ben_yukle())
        metinler = json.dumps([str(getattr(k, "value", "")) for k in _gez(sayfa.controls)], ensure_ascii=False)
        self.assertIn("Okulu etkinleştir", json.dumps([str(getattr(k, "content", "")) for k in _gez(sayfa.controls)],
                                                       ensure_ascii=False))
        self.assertIn("henüz bir okula bağlı değil", metinler)


PB_HESAP = {
    "gun_sayisi": 30, "bedel": "39603.96", "kdv_orani": "0.01", "kdv": "396.04", "fatura_tutari": "40000.00",
    "malzeme": "22500.00", "malzeme_kdv": "225.00", "malzeme_kdv_dahil": "22725.00", "malzeme_orani": "0.568125",
    "malzemeler": [{"sira": 1, "cins": "Zeytin <taze>", "miktar": "1500", "birim": "Kg", "birim_fiyat": "15",
                    "kdv_orani": "0.01", "tutar": "22500.00", "kdv": "225.00"}],
    "hizmet_alimi": "0", "faaliyet": "6336.63", "kar": "1980.20", "pesin_gelir_vergisi": "396.04", "shcek": "396.04",
    "iscilik": "7995.05", "ogrenci_havuz": "3997.53", "ogretmen_havuz": "3997.52", "ogretmen_adet": "3",
    "ogrenci_adet": "3", "ogretmen_parca_payi": "1332.506667", "ogrenci_parca_payi": "1332.510000",
    "kisiler": [
        {"kisi_turu": "Öğretmen", "kisi_id": 1, "ad_soyad": "Öğretmen A", "tckn": "10000000146", "gorev": "Alan Şefi",
         "iban": "TR330006100519786457841326", "gunler": ["0"] * 4 + ["1"] + ["0"] * 25, "adet": "1",
         "gv_orani": "0.27", "brut": "3997.52", "gelir_vergisi": "1079.33", "damga_vergisi": "30.34", "net": "2887.85"},
        {"kisi_turu": "Öğrenci", "kisi_id": 2, "ad_soyad": "Öğrenci Bir", "tckn": "", "gorev": "Öğrenci",
         "okul_no": "12", "sinif": "11-A", "iban": "TR330006100519786457841326", "gunler": ["0"] * 4 + ["3"] + ["0"] * 25,
         "adet": "3", "gv_orani": None, "brut": "3997.53", "gelir_vergisi": "0", "damga_vergisi": "0.00",
         "net": "3997.53"}],
    "toplam": {"brut": "7995.05", "gelir_vergisi": "1079.33", "damga_vergisi": "30.34", "net": "6885.38"},
    "hatalar": [], "uyarilar": []}


def pb_hakedis(durum="Taslak", **ek):
    h = {"id": 5, "hakedis_no": "PB-2026-0001", "siparis_id": 7, "siparis_no": "SIP-2026-00007",
         "siparis_konu": "Zeytin hasadı", "cari": "Müşteri", "bolum": "Tarım", "yil": 2026, "ay": 11,
         "baslama": "2026-11-01", "bitis": "2026-11-05", "bedel": "39603.96", "kdv_orani": "0.01", "hizmet_alimi": "0",
         "faaliyet_orani": "0.16", "kar_orani": "0.05", "pesin_orani": "0.01", "shcek_orani": "0.01",
         "ogrenci_orani": "0.5", "dv_orani": "0.00759", "asgari_ucret": "33030", "urun_aciklama": "Zeytin üretimi",
         "uretilen_miktar": "1500", "birim": "Kg", "aciklama": None, "durum": durum, "surum": 3,
         "olusturan_rol": "Alan Şefi", "malzemeler": [], "kisiler": [], "hesap": PB_HESAP, "odeme": None,
         "onaylar": [{"islem": "Hazırlandı", "rol": "Alan Şefi", "ad_soyad": "Şef Kişi", "aciklama": None,
                      "zaman": "2026-11-05 10:00"}]}
    h.update(ek)
    return h


class ParcaBasiTest(unittest.TestCase):
    _uygulama = ArayuzTest._uygulama
    _temel_yollar = ArayuzTest._temel_yollar

    def _yollar(self, rol, hakedisler=(), yetki="y", **ek_yetki):
        yollar = self._temel_yollar([])
        ben = dict(BEN, rol=rol, yetkiler={**BEN["yetkiler"], "parca_basi": yetki, **ek_yetki})
        yollar[("POST", "/rest/v1/rpc/dose_ben")] = (200, ben)
        yollar[("POST", "/rest/v1/rpc/dose_pb_veri")] = (200, {
            "okul": {"ad": "Derik MTAL", "kurum_kodu": "123456"},
            "siparisler": [{"id": 7, "siparis_no": "SIP-2026-00007", "konu": "Zeytin hasadı", "cari": "Müşteri",
                            "tarih": "2026-11-01", "kdv_orani": "0.01", "sozlesme_bedeli": "40400",
                            "kullanilan": "0"}],
            "personel": [{"id": 1, "ad_soyad": "Öğretmen A", "kadro_unvani": "Öğretmen", "iban_var": True}],
            "ogrenciler": [{"id": 2, "ad_soyad": "Öğrenci Bir", "sinif": "11-A", "veli_muvafakat": True,
                            "iban_var": True}],
            "hakedisler": list(hakedisler), "banka_bakiye": "10000",
            "mevzuat": {"yayin_id": 1, "degerler": {
                "pb_kar_orani": "0.05", "pb_faaliyet_orani": "0.11", "ogrenci_hakki_orani": "0.30",
                "malzeme_azami_orani": "0.60"}}})
        return yollar

    async def _ac(self, app):
        await app.ben_yukle()
        app._dongu.cancel()
        await app.sayfa_ac("parca_basi")
        return app.ekran

    def test_kdv_dahil_tutar_ve_oranlar_kesin_donusur(self):
        from decimal import Decimal
        from istemci.parca_basi import _oran, ay_gun_sayisi, binde_yaz, kdv_haric
        self.assertEqual(kdv_haric(Decimal("40000"), Decimal("0.01")), Decimal("39603.96"))
        self.assertEqual(_oran("DV", "7,59", 1000), "0.00759")
        self.assertEqual(_oran("Faaliyet", "16"), "0.16")
        self.assertEqual(binde_yaz("0.00759"), "7,59")
        self.assertEqual(ay_gun_sayisi("2028-02-10"), 29)
        with self.assertRaises(ValueError):
            _oran("Kâr", "101")

    def test_alan_sefi_puantaj_girer_ve_sunucu_hesabini_gosterir(self):
        yollar = self._yollar("Alan Şefi")
        hatali = dict(PB_HESAP, hatalar=["Faaliyet gideri oranı en az %11 olmalıdır."])
        yollar[("POST", "/rest/v1/rpc/dose_pb_kaydet")] = (200, {"id": 5, "surum": 1, "hesap": hatali})
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            ekran = await self._ac(app)
            self.assertIn("Parça başı hakediş", [e for _, e, *_ in app.gorunur_sayfalar()])
            ekran._ac()
            f = ekran.form
            f["siparis"].value = "7"
            f["baslama"].value = "01.11.2026"
            f["bitis"].value = "05.11.2026"
            f["fatura_tutari"].value = "40.000"
            ekran._fatura_tutari_degisti()
            self.assertEqual(f["bedel"].value, "39603,96")
            f["faaliyet"].value = "16"
            f["kar"].value = "5"
            f["asgari"].value = "33.030"
            f["urun"].value = "Zeytin üretimi"
            f["miktar"].value = "1500"
            ekran._donem_degisti()
            ekran._malzeme_ekle()
            m = ekran.malzemeler[0]
            m["cins"].value, m["miktar"].value, m["birim_fiyat"].value, m["kdv"].value = "Zeytin", "1500", "15", "1"
            sec = ft_secim("1")
            ekran._kisi_ekle("Öğretmen", sec)
            ekran._kisi_ekle("Öğretmen", sec)
            self.assertIn("zaten var", sayfa.diyaloglar[-1].content.value)
            ekran._kisi_ekle("Öğrenci", ft_secim("2"))
            ekran.puantaj[0].gv.value = "27"
            ekran.puantaj[0].gunler[4].value = "1"
            ekran.puantaj[1].gunler[4].value = "3"
            await ekran._kaydet(ft_dugme())
            self.assertEqual(ekran.kayit_id, 5)
            self.assertIn("1 kontrolü düzeltin", sayfa.diyaloglar[-1].content.value)
            gonder = next(k for k in _gez([ekran.kontrol]) if getattr(k, "content", None) == "Onaya gönder")
            self.assertTrue(gonder.disabled, "server errors block submission")
            self.assertIn("en az %11", json.dumps([str(getattr(k, "value", "")) for k in _gez([ekran.kontrol])],
                                                 ensure_ascii=False))

        calistir(akis())
        govde = next(i[3] for i in app.supa.tasima.istekler if "/rpc/dose_pb_kaydet" in i[1])
        self.assertIsNone(govde["p_id"])
        self.assertEqual(govde["p_veri"]["bedel"], "39603.96")
        self.assertEqual(govde["p_veri"]["faaliyet_orani"], "0.16")
        self.assertEqual(govde["p_veri"]["dv_orani"], "0.00759")
        self.assertEqual(govde["p_veri"]["asgari_ucret"], "33030")
        self.assertEqual(govde["p_veri"]["baslama"], "2026-11-01")
        self.assertEqual(govde["p_malzemeler"], [{"cins": "Zeytin", "miktar": "1500", "birim": "Adet",
                                                  "birim_fiyat": "15", "kdv_orani": "0.01"}])
        ogretmen, ogrenci = govde["p_kisiler"]
        self.assertEqual(len(ogretmen["gunler"]), 30)
        self.assertEqual(ogretmen["gunler"][4], "1")
        self.assertEqual(ogretmen["gv_orani"], "0.27")
        self.assertNotIn("gv_orani", ogrenci)
        self.assertEqual(ogrenci["gunler"][4], "3")

    def test_rol_ve_duruma_gore_islem_dugmeleri(self):
        def dugmeler(rol, h, **ek):
            app, _ = self._uygulama(1280, self._yollar(rol, [h], **ek))
            ekran = calistir(self._ac(app))
            return {k.content for k in _gez([ekran.kontrol]) if isinstance(getattr(k, "content", None), str)}

        self.assertTrue({"Düzenle", "Onaya gönder", "İptal"} <= dugmeler("Alan Şefi", pb_hakedis()))
        self.assertTrue({"Uygundur", "İade et"} <= dugmeler("Teknik Müdür Yardımcısı", pb_hakedis("TMY Onayında")))
        self.assertNotIn("Olur", dugmeler("Okul Müdürü", pb_hakedis("TMY Onayında")))
        self.assertTrue({"Olur", "İade et"} <= dugmeler("Okul Müdürü", pb_hakedis("Müdür Onayında")))
        self.assertIn("Bankadan öde", dugmeler("Sayman", pb_hakedis("Onaylandı"), kasa="y"))
        odenmis = pb_hakedis("Onaylandı", odeme={"id": 1, "tarih": "2026-11-06", "tutar": "6885.38", "belge_no": "D1"})
        self.assertNotIn("Bankadan öde", dugmeler("Sayman", odenmis, kasa="y"))
        self.assertNotIn("İptal", dugmeler("Okul Müdürü", odenmis))
        self.assertIn("İptal", dugmeler("Okul Müdürü", pb_hakedis("Onaylandı")))
        self.assertNotIn("Düzenle", dugmeler("Alan Şefi", pb_hakedis(), yetki="g"))

    def test_belgeler_sunucu_hesabindan_uretilir_ve_kacislanir(self):
        import tempfile
        from istemci import belgeler as B
        okul = {"ad": "Derik <MTAL>", "kurum_kodu": "123456"}
        h = pb_hakedis("Onaylandı")
        for tur, _ in B.BELGELER:
            metin = B.belge_html(tur, okul, h)
            self.assertIn("Derik &lt;MTAL&gt;", metin, tur)
            self.assertNotIn("<MTAL>", metin, tur)
        olur = B.belge_html("olur", okul, h)
        for parca in ("39.603,96", "22.500,00", "7.995,05", "6.885,38", "Şef Kişi", "OLUR"):
            self.assertIn(parca, olur)
        self.assertIn("Zeytin &lt;taze&gt;", B.belge_html("malzeme", okul, h))
        bordro = B.belge_html("ogretmen_bordro", okul, h)
        self.assertIn("1.079,33", bordro)
        self.assertNotIn("Öğrenci Bir", bordro)
        self.assertIn("istisnadır", B.belge_html("ogrenci_bordro", okul, h))
        puantaj = B.belge_html("puantaj", okul, h)
        self.assertEqual(puantaj.count("<th>30</th>"), 1)
        self.assertIn("TR330006100519786457841326", B.belge_html("iban", okul, h))
        with tempfile.TemporaryDirectory() as d:
            yol = B.belge_kaydet("ek3", okul, h, Path(d))
            self.assertEqual(yol.name, "PB-2026-0001_ek3.html")
            self.assertIn("6.336,63", yol.read_text(encoding="utf-8"))


FC_HESAP = {
    "gun_sayisi": 30, "gun_turleri": ["T"] + ["O"] * 29, "gun_sinirlari": ["8"] + ["3"] * 29, "aylik_sinir": "95",
    "kisiler": [
        {"personel_id": 1, "ad_soyad": "Öğretmen <A>", "tckn": "10000000146", "iban": "TR330006100519786457841326",
         "gorev": "Usta", "kadro_unvani": "Öğretmen", "gunler": ["5"] + ["0"] * 29, "saat": "5",
         "saat_ucreti": "67.50", "gv_orani": "0.15", "brut": "337.50", "gelir_vergisi": "50.63",
         "damga_vergisi": "2.56", "net": "284.31"},
        {"personel_id": 2, "ad_soyad": "Öğretmen B", "tckn": "10000000078", "iban": "TR330006100519786457841327",
         "gorev": "Öğretmen", "kadro_unvani": "Öğretmen", "gunler": ["0", "3"] + ["0"] * 28, "saat": "3",
         "saat_ucreti": "67.50", "gv_orani": "0.20", "brut": "202.50", "gelir_vergisi": "40.50",
         "damga_vergisi": "1.54", "net": "160.46"}],
    "toplam": {"saat": "8", "brut": "540.00", "gelir_vergisi": "91.13", "damga_vergisi": "4.10", "net": "444.77"},
    "siparis_iscilik": "8400.00", "siparis_diger_fc": "0", "siparis_kalan": "7860.00", "hatalar": [], "uyarilar": []}


def fc_bordro(durum="Taslak", **ek):
    b = {"id": 9, "bordro_no": "FC-2026-0001", "siparis_id": 8, "siparis_no": "SIP-2026-00008",
         "siparis_konu": "Masa <imalatı>", "cari": "Müşteri", "bolum": "Mobilya", "yil": 2026, "ay": 11,
         "saat_ucreti": "67.50", "azami_ucret": "67.50", "ogretim_gunu_saat": "3", "tatil_gunu_saat": "8",
         "pazar_izinli": True, "dv_orani": "0.00759", "malzeme_maliyeti": "0", "gun_turleri": ["T"] + ["O"] * 29,
         "is_tanimi": "Masa imalatı", "aciklama": None, "durum": durum, "surum": 2, "olusturan_rol": "Alan Şefi",
         "kisiler": [{"personel_id": 1, "gorev": "Usta", "gv_orani": "0.15", "gunler": ["5"] + ["0"] * 29}],
         "hesap": FC_HESAP, "odeme": None,
         "onaylar": [{"islem": "Hazırlandı", "rol": "Alan Şefi", "ad_soyad": "Şef Kişi", "aciklama": None,
                      "zaman": "2026-11-05 10:00"}]}
    b.update(ek)
    return b


class FazlaCalismaTest(unittest.TestCase):
    _uygulama = ArayuzTest._uygulama
    _temel_yollar = ArayuzTest._temel_yollar

    def _yollar(self, rol, bordrolar=(), yetki="y", **ek_yetki):
        yollar = self._temel_yollar([])
        ben = dict(BEN, rol=rol, yetkiler={**BEN["yetkiler"], "fazla_calisma": yetki, **ek_yetki})
        yollar[("POST", "/rest/v1/rpc/dose_ben")] = (200, ben)
        yollar[("POST", "/rest/v1/rpc/dose_fc_veri")] = (200, {
            "okul": {"ad": "Derik MTAL", "kurum_kodu": "123456"},
            "siparisler": [{"id": 8, "siparis_no": "SIP-2026-00008", "konu": "Masa imalatı", "cari": "Müşteri",
                            "tarih": "2026-11-01", "ucret_esasi": "Fazla Çalışma Ücreti", "sozlesme_bedeli": "12000"}],
            "personel": [{"id": 1, "ad_soyad": "Öğretmen A", "kadro_unvani": "Öğretmen", "iban_var": True},
                         {"id": 2, "ad_soyad": "Öğretmen B", "kadro_unvani": "Usta Öğretici", "iban_var": False}],
            "bordrolar": list(bordrolar), "banka_bakiye": "1000",
            "mevzuat": {"yayin_id": 1, "degerler": {"pb_kar_orani": "0.05", "pb_faaliyet_orani": "0.11"}}})
        return yollar

    async def _ac(self, app):
        await app.ben_yukle()
        app._dongu.cancel()
        await app.sayfa_ac("fazla_calisma")
        return app.ekran

    def test_varsayilan_gun_turleri_hafta_sonunu_tatil_sayar(self):
        from istemci.fazla_calisma import varsayilan_gun_turleri
        kasim = varsayilan_gun_turleri(2026, 11)
        self.assertEqual(len(kasim), 30)
        self.assertEqual(kasim[:3], ["T", "O", "O"])  # 1 Kasım 2026 Pazar
        self.assertEqual(kasim[6:8], ["T", "T"])
        self.assertEqual(len(varsayilan_gun_turleri(2028, 2)), 29)

    def test_alan_sefi_saat_girer_ve_sunucu_hesabini_gosterir(self):
        yollar = self._yollar("Alan Şefi")
        hatali = dict(FC_HESAP, hatalar=["Öğretmen A: 02.11.2026 günü 5 saat yazılmış; o gün için sınır 3 saat."])
        yollar[("POST", "/rest/v1/rpc/dose_fc_kaydet")] = (200, {"id": 9, "surum": 1, "hesap": hatali})
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            ekran = await self._ac(app)
            self.assertIn("Fazla çalışma", [e for _, e, *_ in app.gorunur_sayfalar()])
            ekran._ac()
            f = ekran.form
            f["siparis"].value = "8"
            f["yil"].value = "2026"
            f["ay"].value = "11"
            ekran._donem_degisti()
            self.assertEqual(len(ekran.gun_turleri), 30)
            self.assertEqual(ekran.gun_turleri[0].value, "T")
            ekran.gun_turleri[2].value = "B"
            f["ay"].value = "11"
            ekran._donem_degisti()
            self.assertEqual(ekran.gun_turleri[2].value, "B", "same period keeps manual day types")
            f["is_tanimi"].value = "Masa imalatı"
            ekran.pazar.value = True
            sec = ft_secim("1")
            ekran._kisi_ekle(sec)
            ekran._kisi_ekle(sec)
            self.assertIn("zaten var", sayfa.diyaloglar[-1].content.value)
            ekran._kisi_ekle(ft_secim("2"))
            ekran.puantaj[0].gunler[0].value = "5"
            ekran.puantaj[1].gunler[1].value = "2,5"
            ekran.puantaj[1].gv.value = "20"
            await ekran._kaydet(ft_dugme())
            self.assertEqual(ekran.kayit_id, 9)
            self.assertIn("1 kontrolü düzeltin", sayfa.diyaloglar[-1].content.value)
            gonder = next(k for k in _gez([ekran.kontrol]) if getattr(k, "content", None) == "Onaya gönder")
            self.assertTrue(gonder.disabled, "server errors block submission")
            metin = json.dumps([str(getattr(k, "value", "")) for k in _gez([ekran.kontrol])], ensure_ascii=False)
            self.assertIn("sınır 3 saat", metin)
            self.assertIn("444,77 TL", metin)
            self.assertTrue(ekran.form["yil"].disabled and ekran.form["siparis"].disabled,
                            "saved bordro period and order are fixed")

        calistir(akis())
        govde = next(i[3] for i in app.supa.tasima.istekler if "/rpc/dose_fc_kaydet" in i[1])
        self.assertIsNone(govde["p_id"])
        v = govde["p_veri"]
        self.assertEqual((v["siparis_id"], v["yil"], v["ay"]), (8, 2026, 11))
        self.assertEqual((v["saat_ucreti"], v["azami_ucret"]), ("67.50", "67.50"))
        self.assertEqual((v["ogretim_gunu_saat"], v["tatil_gunu_saat"]), ("3", "8"))
        self.assertEqual(v["dv_orani"], "0.00759")
        self.assertIs(v["pazar_izinli"], True)
        self.assertEqual(len(v["gun_turleri"]), 30)
        self.assertEqual(v["gun_turleri"][:3], ["T", "O", "B"])
        a, b = govde["p_kisiler"]
        self.assertEqual((a["personel_id"], a["gv_orani"], a["gunler"][0], len(a["gunler"])), (1, "0.15", "5", 30))
        self.assertEqual((b["personel_id"], b["gorev"], b["gv_orani"], b["gunler"][1]), (2, "Usta Öğretici", "0.2", "2.5"))

    def test_gecersiz_saat_ve_eksik_alanlar_sunucuya_gitmez(self):
        app, _ = self._uygulama(1280, self._yollar("Alan Şefi"))

        async def akis():
            ekran = await self._ac(app)
            ekran._ac()
            ekran.form["siparis"].value = "8"
            with self.assertRaisesRegex(ValueError, "Yapılan iş"):
                ekran.form_verisi()
            ekran.form["is_tanimi"].value = "İş"
            with self.assertRaisesRegex(ValueError, "en az bir personel"):
                ekran.form_verisi()
            ekran._kisi_ekle(ft_secim("1"))
            ekran.puantaj[0].gunler[0].value = "25"
            with self.assertRaisesRegex(ValueError, "0 ile 24"):
                ekran.form_verisi()

        calistir(akis())
        self.assertFalse(any("/rpc/dose_fc_kaydet" in i[1] for i in app.supa.tasima.istekler))

    def test_rol_ve_duruma_gore_islem_dugmeleri(self):
        def dugmeler(rol, b, **ek):
            app, _ = self._uygulama(1280, self._yollar(rol, [b], **ek))
            ekran = calistir(self._ac(app))
            return {k.content for k in _gez([ekran.kontrol]) if isinstance(getattr(k, "content", None), str)}

        self.assertTrue({"Düzenle", "Onaya gönder", "İptal", "Belgeler", "Yeni bordro"} <= dugmeler("Alan Şefi", fc_bordro()))
        self.assertNotIn("Düzenle", dugmeler("Okul Müdürü", fc_bordro()))
        self.assertTrue({"Uygundur", "İade et"} <= dugmeler("Teknik Müdür Yardımcısı", fc_bordro("TMY Onayında")))
        self.assertNotIn("Olur", dugmeler("Okul Müdürü", fc_bordro("TMY Onayında")))
        self.assertTrue({"Olur", "İade et"} <= dugmeler("Okul Müdürü", fc_bordro("Müdür Onayında")))
        self.assertIn("Bankadan öde", dugmeler("Sayman", fc_bordro("Onaylandı"), kasa="y"))
        self.assertNotIn("Bankadan öde", dugmeler("Sayman", fc_bordro("Onaylandı"), kasa="g"))
        odenmis = fc_bordro("Onaylandı", odeme={"id": 1, "tarih": "2026-12-05", "tutar": "444.77", "belge_no": "D1"})
        self.assertNotIn("Bankadan öde", dugmeler("Sayman", odenmis, kasa="y"))
        self.assertNotIn("İptal", dugmeler("Okul Müdürü", odenmis))
        self.assertIn("İptal", dugmeler("Okul Müdürü", fc_bordro("Onaylandı")))
        self.assertNotIn("Düzenle", dugmeler("Alan Şefi", fc_bordro(), yetki="g"))

    def test_belgeler_sunucu_hesabindan_uretilir_ve_kacislanir(self):
        import tempfile
        from istemci import belgeler as B
        okul = {"ad": "Derik <MTAL>", "kurum_kodu": "123456"}
        b = fc_bordro("Onaylandı")
        for tur, _ in B.FC_BELGELER:
            metin = B.belge_html(tur, okul, b)
            self.assertIn("Derik &lt;MTAL&gt;", metin, tur)
            self.assertNotIn("<MTAL>", metin, tur)
            self.assertNotIn("<imalatı>", metin, tur)
            self.assertIn("FC-2026-0001", metin, tur)
        olur = B.belge_html("fc_olur", okul, b)
        for parca in ("540,00", "95,23", "444,77", "Şef Kişi", "OLUR", "9. maddesi"):
            self.assertIn(parca, olur)
        bordro = B.belge_html("fc_bordro", okul, b)
        for parca in ("Öğretmen &lt;A&gt;", "50,63", "160,46", "91,13"):
            self.assertIn(parca, bordro)
        puantaj = B.belge_html("fc_puantaj", okul, b)
        self.assertEqual(puantaj.count(">30<br>"), 1)
        self.assertIn("bayram (fazla çalışma yapılamaz)", puantaj)
        self.assertNotIn("Pazar günleri", B.belge_html("fc_gorev", okul, b))
        self.assertIn("Pazar günleri", B.belge_html("fc_gorev", okul, fc_bordro(pazar_izinli=False)))
        self.assertIn("TR330006100519786457841327", B.belge_html("fc_iban", okul, b))
        with tempfile.TemporaryDirectory() as d:
            yol = B.belge_kaydet("fc_bordro", okul, b, Path(d))
            self.assertEqual(yol.name, "FC-2026-0001_fc_bordro.html")
        # existing piece-rate documents keep their hakediş number in the footer
        self.assertIn("Hakediş PB-2026-0001", B.belge_html("olur", okul, pb_hakedis("Onaylandı")))


def hp_ay(ay, durum, kayit=None, hasilat="50000.00", gecikme=0):
    return {"yil": 2026, "ay": ay, "tamamlandi": durum != "Ay devam ediyor", "durum": durum, "hasilat": hasilat,
            "tahmini_tutar": "500.00", "son_odeme": f"2026-{ay + 1:02d}-20", "gecikme_ay": gecikme,
            "gecikme_tutari": "5.00" if gecikme else "0.00", "kayit": kayit,
            "kdv": {"hesaplanan": "10000.00", "indirilecek": "2500.00", "odenecek": "7500.00", "devreden": "0",
                    "son_gun": f"2026-{ay + 1:02d}-28"},
            "muhtasar": {"kesinti": "95.23", "son_gun": f"2026-{ay + 1:02d}-26"}}


def hp_kayit(no="HP-2026-001", odeme=None):
    return {"id": 4, "bildirim_no": no, "hasilat": "50000.00", "oran": "0.01", "tutar": "500.00",
            "bildirim_tarihi": "2026-10-05", "son_odeme": "2026-10-20", "aciklama": None, "surum": 1,
            "yevmiye_id": 30, "hasilat_farki": "0.00", "odeme": odeme}


class HazinePayiTest(unittest.TestCase):
    _uygulama = ArayuzTest._uygulama
    _temel_yollar = ArayuzTest._temel_yollar

    def _yollar(self, rol, aylar, yetki="y", **ek_yetki):
        yollar = self._temel_yollar([])
        ben = dict(BEN, rol=rol, yetkiler={**BEN["yetkiler"], "hazine_payi": yetki, **ek_yetki})
        yollar[("POST", "/rest/v1/rpc/dose_ben")] = (200, ben)
        yollar[("POST", "/rest/v1/rpc/dose_hp_veri")] = (200, {
            "okul": {"ad": "Derik MTAL", "kurum_kodu": "123456"}, "yil": 2026, "bugun": "2026-11-03",
            "varsayilan_oran": "0.01", "aylar": list(aylar), "iptaller": [], "banka_bakiye": "1000"})
        return yollar

    async def _ac(self, app):
        await app.ben_yukle()
        app._dongu.cancel()
        await app.sayfa_ac("hazine_payi")
        return app.ekran

    def _dugmeler(self, ekran):
        return [k.content for k in _gez([ekran.kontrol]) if isinstance(getattr(k, "content", None), str)]

    def test_oran_yuzde_olarak_cozulur(self):
        from decimal import Decimal
        from istemci.hazine_payi import oran_coz
        self.assertEqual(oran_coz("1"), Decimal("0.01"))
        self.assertEqual(oran_coz("%1,5"), Decimal("0.015"))
        for hatali in ("", "0", "11", "abc", "NaN"):
            with self.assertRaises(ValueError, msg=hatali):
                oran_coz(hatali)

    def test_sayman_bildirir_odeme_ve_iptal_dugmeleri(self):
        aylar = [hp_ay(8, "Ödendi", hp_kayit("HP-2026-001", {"id": 1, "tarih": "2026-09-15", "tutar": "500.00",
                                                              "belge_no": "D1"})),
                 hp_ay(9, "Gecikmiş", hp_kayit("HP-2026-002"), gecikme=1),
                 hp_ay(10, "Bildirilecek"), hp_ay(11, "Ay devam ediyor")]
        yollar = self._yollar("Sayman", aylar, kasa="y")
        yollar[("POST", "/rest/v1/rpc/dose_hp_bildir")] = (200, {"id": 5, "bildirim_no": "HP-2026-003",
                                                               "tutar": "750.00", "hasilat": "50000.00"})
        app, sayfa = self._uygulama(1280, yollar)

        async def akis():
            ekran = await self._ac(app)
            self.assertIn("Hazine payı / vergi takvimi", [e for _, e, *_ in app.gorunur_sayfalar()])
            dugmeler = self._dugmeler(ekran)
            self.assertEqual(dugmeler.count("Bildir"), 1, "only the completed, undeclared month")
            self.assertEqual(dugmeler.count("Bankadan öde"), 1, "only the unpaid declaration")
            self.assertEqual(dugmeler.count("İptal"), 1)
            self.assertEqual(dugmeler.count("Belgeler"), 2)
            metin = json.dumps([str(getattr(k, "value", "")) for k in _gez([ekran.kontrol])], ensure_ascii=False)
            for parca in ("Süresi geçen hazine payı: Eylül 2026", "7.500,00", "95,23", "28.11.2026", "Ödendi: 15.09.2026"):
                self.assertIn(parca, metin)
            ekran._bildir_dialog(aylar[2])
            dialog = sayfa.diyaloglar[-1]
            oran = dialog.content.controls[3]
            oran.value = "1,5"
            await dialog.actions[1].on_click(None)

        calistir(akis())
        govde = next(i[3] for i in app.supa.tasima.istekler if "/rpc/dose_hp_bildir" in i[1])
        self.assertEqual((govde["p_yil"], govde["p_ay"], govde["p_oran"]), (2026, 10, "0.015"))
        self.assertTrue(govde["p_istek"])

    def test_mudur_yalniz_izler(self):
        aylar = [hp_ay(9, "Ödenecek", hp_kayit()), hp_ay(10, "Bildirilecek")]
        app, _ = self._uygulama(1280, self._yollar("Okul Müdürü", aylar, yetki="g", kasa="g"))
        ekran = calistir(self._ac(app))
        dugmeler = self._dugmeler(ekran)
        self.assertFalse({"Bildir", "Bankadan öde", "İptal"} & set(dugmeler))
        self.assertIn("Belgeler", dugmeler)

    def test_hazine_belgeleri_kacislanir(self):
        from istemci import belgeler as B
        from istemci.hazine_payi import belge_verisi
        okul = {"ad": "Derik <MTAL>", "kurum_kodu": "123456"}
        ay = hp_ay(9, "Ödendi", hp_kayit(odeme={"id": 1, "tarih": "2026-10-25", "tutar": "500.00", "belge_no": "<D1>"}),
                   gecikme=1)
        h = belge_verisi(ay)
        for tur, _ in B.HP_BELGELER:
            metin = B.belge_html(tur, okul, h)
            self.assertIn("Derik &lt;MTAL&gt;", metin, tur)
            self.assertIn("Bildirim HP-2026-001", metin, tur)
            self.assertNotIn("Sipariş", metin, tur)
        bildirim = B.belge_html("hp_bildirim", okul, h)
        for parca in ("Eylül 2026", "50.000,00", "%1", "500,00", "&lt;D1&gt;", "1 ay", "Örnek No:30"):
            self.assertIn(parca, bildirim)
        self.assertIn("25.10.2026 tarihinde yatırılmıştır", B.belge_html("hp_ust_yazi", okul, h))
        self.assertIn("yatırılacaktır", B.belge_html("hp_ust_yazi", okul, belge_verisi(hp_ay(9, "Ödenecek", hp_kayit()))))


class YeniEkranModulleriTest(unittest.TestCase):
    def test_ys_belge_html_ve_rapor_ozeti(self):
        from istemci import belgeler as B
        from istemci.raporlar import RaporlarEkrani
        okul = {"ad": "Test MTAL", "kurum_kodu": "123456"}
        h = {"belge_no": "YS-2025-01", "yil": 2025, "hesap": {"donem_kari": "100", "shcek": "1"},
             "kisiler": [], "odemeler": {}}
        html = B.ys_belge_html("ys_cetvel", okul, h)
        self.assertIn("YS-2025-01", html)
        self.assertIn("kâr dağıtım", html.lower())

        class SahteApp:
            ben = {"okul": okul, "rol": "Sayman", "yetkiler": {"yevmiye": "g"}}
            page = type("P", (), {"run_task": staticmethod(lambda *a, **k: None)})()
            def bildir(self, *a, **k): pass
            def yetki(self, s): return "g"

        ekran = RaporlarEkrani(SahteApp())
        ekran.veri = {"yil": 2025, "siparis": 2, "fatura_satis": "10", "fatura_alis": "3",
                      "kasa_bakiye": "1", "banka_bakiye": "2", "hp_hasilat": "4"}
        self.assertIn("Satış faturaları", ekran._html())
        self.assertIn("GİB", ekran._html())

    def test_maliyet_ve_resmi_modulleri_yuklenir(self):
        from istemci import maliyet, resmi, yil_sonu
        self.assertTrue(hasattr(maliyet, "MaliyetEkrani"))
        self.assertTrue(hasattr(resmi, "ResmiYaziEkrani"))
        self.assertTrue(hasattr(resmi, "DenetimEkrani"))
        self.assertTrue(hasattr(yil_sonu, "YilSonuEkrani"))

    def test_tanim_ekrani_ice_aktarma_aksiyonlari(self):
        import inspect
        from istemci.ekranlar import TanimEkrani
        kaynak = inspect.getsource(TanimEkrani)
        self.assertIn("Şablon", kaynak)
        self.assertIn("Excel/PDF yükle", kaynak)
        self.assertIn("_ice_aktar_sec", kaynak)
        self.assertIn("pick_files", kaynak)
        self.assertIn("FilePicker", kaynak)
        self.assertIn("TABLO_ICE_AKTARMA", kaynak)


class ExcelIceAktarmaTest(unittest.TestCase):
    def test_sablon_ve_cari_malzeme_esleme(self):
        import tempfile
        from dose import excel as X
        with tempfile.TemporaryDirectory() as tmp:
            yol = Path(tmp) / "cari.xlsx"
            X.sablon_yaz("cari", yol)
            from openpyxl import load_workbook
            wb = load_workbook(yol)
            ws = wb.active
            # Şablon: satır 1 başlık metni, satır 3 sütun başlıkları
            baslik_satiri = None
            for i, row in enumerate(ws.iter_rows(values_only=True), 1):
                if row and any(isinstance(c, str) and "kod" in str(c).casefold() for c in row):
                    baslik_satiri = i
                    break
            self.assertIsNotNone(baslik_satiri)
            ws.cell(baslik_satiri + 1, 1, "C0009")
            ws.cell(baslik_satiri + 1, 2, "Tedarikçi")
            ws.cell(baslik_satiri + 1, 3, "Örnek Ltd")
            wb.save(yol)
            kayitlar = X.tanim_oku(yol, "cari")
            self.assertEqual(len(kayitlar), 1)
            self.assertEqual(str(kayitlar[0].get("kod")), "C0009")
            self.assertIn("Örnek", str(kayitlar[0].get("unvan")))

            myol = Path(tmp) / "malzeme.xlsx"
            X.disa_aktar(myol, [("Malzeme", ["Stok kodu", "Malzeme adı", "Türü", "Birim", "KDV oranı (%)"],
                                [["M1", "Çelik sac", "İlk Madde ve Malzeme", "kg", 20]])])
            mk = X.tanim_oku(myol, "malzeme")
            self.assertEqual(mk[0]["kod"], "M1")
            self.assertEqual(mk[0]["ad"], "Çelik sac")

            byol = Path(tmp) / "bolum.xlsx"
            X.sablon_yaz("bolum", byol)
            self.assertTrue(byol.is_file())
            uyol = Path(tmp) / "urun.xlsx"
            X.disa_aktar(uyol, [("Ürün", ["Kod", "Ürün / hizmet adı", "Türü", "Birim"],
                                [["U1", "Kapı", "Mal", "adet"]])])
            uk = X.tanim_oku(uyol, "urun")
            self.assertEqual(uk[0]["kod"], "U1")

    def test_pdf_satir_listesi_esleme(self):
        from dose import excel as X
        satirlar = [
            ["Cari kodu", "Unvan / adı soyadı", "Türü"],
            ["C1", "ABC A.Ş.", "Müşteri"],
            ["C2", "XYZ Ltd", "Tedarikçi"],
        ]
        kayitlar = X.satir_listesinden_oku(satirlar, X.CARI_ICE_AKTARMA)
        self.assertEqual(len(kayitlar), 2)
        self.assertEqual(kayitlar[0]["kod"], "C1")


def ft_secim(deger):
    import flet as ft
    return ft.Dropdown(value=deger)


def ft_dugme():
    import flet as ft
    return ft.FilledButton("Kaydet")


def _gez(kontroller):
    for k in kontroller:
        yield k
        for ad in ("controls", "content"):
            alt = getattr(k, ad, None)
            if isinstance(alt, list):
                yield from _gez(alt)
            elif alt is not None and hasattr(alt, "__dict__"):
                yield from _gez([alt])


if __name__ == "__main__":
    unittest.main()
