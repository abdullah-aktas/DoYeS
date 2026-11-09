"""End-to-end: the real Flet screens talk over HTTP to a local Supabase stand-in that runs every migration.

Covers the full first-use path: vendor opens the school → manager signs up, confirms e-mail, logs in, activates
the school → definitions are entered → a workshop chief is invited, joins and sees only his workshop → two
devices edit the same record and the stale one is rejected → audit log, deadline dashboard, session restore.
Skips when Node or the PGlite dev dependency (supabase/node_modules) is missing.
"""
import asyncio
import json
import shutil
import subprocess
import time
import unittest
import urllib.request
from pathlib import Path

from tests.test_istemci import SahteSayfa

KOK = Path(__file__).resolve().parent.parent
SUPA = KOK / "supabase"


def _gez(kontroller):
    for k in kontroller:
        if k is None:
            continue
        yield k
        for ad in ("controls", "content", "actions", "destinations", "leading", "trailing", "title", "subtitle"):
            alt = getattr(k, ad, None)
            if isinstance(alt, list):
                yield from _gez(alt)
            elif alt is not None and hasattr(alt, "__dict__"):
                yield from _gez([alt])


def hepsi(sayfa):
    return list(_gez(list(sayfa.controls) + [sayfa.appbar, sayfa.drawer] + list(sayfa.diyaloglar)))


def alan(sayfa, etiket):
    return next(k for k in hepsi(sayfa) if getattr(k, "label", None) == etiket)


def dugme(sayfa, metin):
    return next(k for k in hepsi(sayfa) if getattr(k, "content", None) == metin and hasattr(k, "on_click"))


def metinler(sayfa) -> str:
    return "\n".join(str(k.value) for k in hepsi(sayfa) if isinstance(getattr(k, "value", None), str))


def son_bildirim(sayfa) -> str:
    return sayfa.diyaloglar[-1].content.value


@unittest.skipUnless(shutil.which("node") and (SUPA / "node_modules" / "@electric-sql" / "pglite").exists(),
                     "node + supabase/node_modules gerekli (cd supabase; npm install)")
class UctanUcaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sunucu = subprocess.Popen(["node", str(SUPA / "tests" / "yerel_supabase.cjs"), "0"],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        satir = cls.sunucu.stdout.readline()
        if not satir.startswith("HAZIR"):
            cls.sunucu.kill()
            raise RuntimeError("yerel Supabase başlamadı: " + satir + cls.sunucu.stderr.read())
        cls.url = f"http://127.0.0.1:{satir.split()[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.sunucu.kill()
        cls.sunucu.wait()
        cls.sunucu.stdout.close()
        cls.sunucu.stderr.close()

    def kontrol(self, yol, govde):
        istek = urllib.request.Request(self.url + yol, json.dumps(govde).encode(), method="POST",
                                       headers={"apikey": "test", "Content-Type": "application/json"})
        with urllib.request.urlopen(istek) as y:
            return json.loads(y.read())

    def uygulama(self, genislik=1280, sayfa=None):
        from istemci.uygulama import Uygulama
        sayfa = sayfa or SahteSayfa(genislik)
        app = Uygulama(sayfa)
        app.supa.url = self.url
        return app, sayfa

    @staticmethod
    def durdur(app):
        if app._dongu:
            app._dongu.cancel()

    async def hesap_ac_ve_gir(self, app, sayfa, eposta, sifre="Guclu-Sifre-1"):
        await app.basla()
        app.kayit_ekrani(eposta)
        alan(sayfa, "Şifre (en az 8 karakter)").value = sifre
        alan(sayfa, "Şifre tekrar").value = sifre
        await dugme(sayfa, "Hesap aç").on_click(None)
        self.assertIn("doğrulama bağlantısına", son_bildirim(sayfa))
        alan(sayfa, "Şifre").value = sifre
        await dugme(sayfa, "Giriş yap").on_click(None)
        self.assertIn("E-posta henüz doğrulanmadı", metinler(sayfa))
        self.assertTrue(dugme(sayfa, "Doğrulama e-postasını yeniden gönder").visible)
        self.kontrol("/_test/onayla", {"email": eposta})
        await dugme(sayfa, "Giriş yap").on_click(None)

    async def tanim_ekle(self, app, tablo, degerler):
        await app.sayfa_ac(tablo)
        ekran = app.ekran
        ekran._yeni()
        for ad, deger in degerler.items():
            ekran.form.kontroller[ad].value = deger
        await ekran._kaydet(dugme(app.page, "Kaydet"))
        self.assertEqual(son_bildirim(app.page), "Kaydedildi.", tablo)
        return ekran.secili

    def ilk_secenek(self, app, liste):
        return app.secenek[liste][0][0]

    def test_bir_aylik_deneme_ile_ilk_giris(self):
        mudur, sayfa = self.uygulama(400)

        async def akis():
            await mudur.basla()
            dugme(sayfa, "1 ay ücretsiz dene").on_click(None)
            self.assertIn("Ücretsiz denemeye başlayın", metinler(sayfa))
            await self.hesap_ac_ve_gir(mudur, sayfa, "deneme@ornekmtal.k12.tr")
            self.assertIn("1 ay ücretsiz deneyin", metinler(sayfa))
            alan(sayfa, "Adınız soyadınız").value = "Deniz Deneme"
            alan(sayfa, "MEB kurum kodu").value = "765432"
            alan(sayfa, "Okulun adı").value = "Örnek MTAL"
            await dugme(sayfa, "1 ay ücretsiz denemeyi başlat").on_click(None)
            self.durdur(mudur)
            self.assertIn("Deneme başladı.", son_bildirim(sayfa))
            self.assertEqual(mudur.ben["rol"], "Okul Müdürü")
            self.assertTrue(mudur.ben["okul"]["deneme"])
            self.assertFalse(mudur.ben["okul"]["salt_okunur"])
            self.assertRegex(metinler(sayfa), r"Deneme · \d+ gün kaldı")

        asyncio.run(akis())

    def test_ilk_kurulumdan_gunluk_kullanima(self):
        kod = self.kontrol("/_test/sql", {"sql": "SELECT dose_private.okul_ac('Derik MTAL', '123456') AS k"})[0]["k"]
        mudur, sayfa = self.uygulama()

        async def akis():
            # 1) First login: sign-up → unconfirmed e-mail is explained → confirm → activation screen.
            await self.hesap_ac_ve_gir(mudur, sayfa, "mudur@derikmtal.k12.tr")
            self.assertIn("henüz bir okula bağlı değil", metinler(sayfa))
            alan(sayfa, "Etkinleştirme kodu").value = "DOSE-0000-YANLIS"
            alan(sayfa, "MEB kurum kodu").value = "123456"
            alan(sayfa, "Adınız soyadınız").value = "Ayşe Yılmaz"
            await dugme(sayfa, "Okulu etkinleştir").on_click(None)
            self.assertIsNone(mudur.ben.get("rol"))
            alan(sayfa, "Etkinleştirme kodu").value = kod.lower()
            await dugme(sayfa, "Okulu etkinleştir").on_click(None)
            self.durdur(mudur)
            self.assertEqual(son_bildirim(sayfa), "Okul etkinleştirildi. Okul Müdürü olarak giriş yaptınız.")
            self.assertEqual(mudur.ben["rol"], "Okul Müdürü")
            self.assertEqual(mudur.ben["okul"]["kurum_kodu"], "123456")
            ana = metinler(sayfa)
            self.assertIn("Merhaba Ayşe", ana)
            self.assertIn("Bekleyen görev", ana)
            self.assertIn("Yaklaşan yasal süreler", ana)

            # 2) Every page the role can see opens against the real schema without an error.
            for anahtar, *_ in mudur.gorunur_sayfalar():
                once = len(sayfa.diyaloglar)
                await mudur.sayfa_ac(anahtar)
                self.assertEqual(len(sayfa.diyaloglar), once, f"{anahtar}: {sayfa.diyaloglar[-1:]}")
                self.assertIs(mudur.govde.content, mudur.ekran.kontrol, anahtar)

            # 3) Definitions through the real forms; the DB fills okul_id, surum and the editor.
            mobilya = await self.tanim_ekle(mudur, "bolum", {
                "ad": "Mobilya Atölyesi", "utp_yontemi": self.ilk_secenek(mudur, "utp_yontemi")})
            elektrik = await self.tanim_ekle(mudur, "bolum", {
                "ad": "Elektrik Atölyesi", "utp_yontemi": self.ilk_secenek(mudur, "utp_yontemi")})
            self.assertEqual(mobilya["surum"], 1)
            self.assertIn("Ayşe Yılmaz", mobilya["guncelleyen"])
            for ad, bolum in (("Mehmet Usta", mobilya), ("Veli Kablo", elektrik)):
                await self.tanim_ekle(mudur, "personel", {
                    "ad_soyad": ad, "hizmet_sinifi": self.ilk_secenek(mudur, "hizmet_sinifi"),
                    "dose_gorevi": "Öğretmen", "bolum_id": str(bolum["id"])})
            self.assertEqual(len(mudur.ekran.kayitlar), 2)

            # 4) Invite the workshop chief from the Users screen.
            await mudur.sayfa_ac("kullanici")
            mudur.ekran._davet()
            alan(sayfa, "E-posta").value = "sef@derikmtal.k12.tr"
            alan(sayfa, "Adı soyadı").value = "Hasan Şef"
            alan(sayfa, "Rol").value = "Alan Şefi"
            alan(sayfa, "Bölüm / atölye (şef ve öğretmen için)").value = str(mobilya["id"])
            await next(k for k in _gez(sayfa.diyaloglar[-1].actions) if k.content == "Davet et").on_click(None)
            self.assertEqual(mudur.ekran.veri["davetler"][0]["eposta"], "sef@derikmtal.k12.tr")
            mudur.ekran._davet()
            alan(sayfa, "E-posta").value = "tmy@derikmtal.k12.tr"
            alan(sayfa, "Adı soyadı").value = "Mehmet Yardımcı"
            alan(sayfa, "Rol").value = "Teknik Müdür Yardımcısı"
            await next(k for k in _gez(sayfa.diyaloglar[-1].actions) if k.content == "Davet et").on_click(None)
            self.assertTrue(any(d["eposta"] == "tmy@derikmtal.k12.tr" for d in mudur.ekran.veri["davetler"]),
                            mudur.ekran.veri["davetler"])
            mudur.ekran._davet()
            alan(sayfa, "E-posta").value = "sayman@derikmtal.k12.tr"
            alan(sayfa, "Adı soyadı").value = "Sena Sayman"
            alan(sayfa, "Rol").value = "Sayman"
            await next(k for k in _gez(sayfa.diyaloglar[-1].actions) if k.content == "Davet et").on_click(None)
            return mobilya, elektrik

        mobilya, elektrik = asyncio.run(akis())

        tmy, tmy_sayfa = self.uygulama()

        async def tmy_akisi():
            # The authorized accounting role creates the customer; the order form exposes only required selector data.
            await self.hesap_ac_ve_gir(tmy, tmy_sayfa, "tmy@derikmtal.k12.tr")
            self.durdur(tmy)
            self.assertEqual(tmy.ben["rol"], "Teknik Müdür Yardımcısı")
            cari = await self.tanim_ekle(tmy, "cari", {
                "tur": self.ilk_secenek(tmy, "cari_tur"), "unvan": "Okul Aile Birliği"})
            return cari

        cari = asyncio.run(tmy_akisi())

        sef, sef_sayfa = self.uygulama(400)

        async def sef_akisi():
            # 5) Chief signs up with the invited address and lands in the school, restricted to his workshop.
            await self.hesap_ac_ve_gir(sef, sef_sayfa, "sef@derikmtal.k12.tr")
            self.durdur(sef)
            self.assertEqual(sef.ben["rol"], "Alan Şefi")
            self.assertEqual(sef.ben["bolum_id"], mobilya["id"])
            self.assertNotIn("kullanici", [s[0] for s in sef.gorunur_sayfalar()])
            await sef.sayfa_ac("personel")
            self.assertEqual([k["ad_soyad"] for k in sef.ekran.kayitlar], ["Mehmet Usta"])
            self.assertFalse(sef.ekran.yazabilir)
            urun = await self.tanim_ekle(sef, "urun", {"ad": "Okul sırası", "tur": self.ilk_secenek(sef, "urun_tur"),
                                                       "bolum_id": str(mobilya["id"])})
            sef.ekran._yeni()
            sef.ekran.form.kontroller["ad"].value = "Başka atölyenin ürünü"
            sef.ekran.form.kontroller["tur"].value = self.ilk_secenek(sef, "urun_tur")
            sef.ekran.form.kontroller["bolum_id"].value = str(elektrik["id"])
            await sef.ekran._kaydet(dugme(sef_sayfa, "Kaydet"))
            self.assertEqual(son_bildirim(sef_sayfa), "Bu işlem için yetkiniz yok.")
            return urun

        urun = asyncio.run(sef_akisi())

        async def siparis_ve_onay():
            # The full order UI calculates the preview; its RPC persists header, lines and a DB-issued number atomically.
            await sef.sayfa_ac("siparis")
            ekran = sef.ekran
            ekran._yeni()
            ekran.form["tarih"].value = "31.10.2020"
            ekran.form["cari_id"].value = str(cari["id"])
            ekran.form["bolum_id"].value = str(mobilya["id"])
            ekran.form["konu"].value = "Okul sırası üretimi"
            ekran.form["ucret_esasi"].value = self.ilk_secenek(sef, "ucret_esasi")
            ekran.form["kdv_orani"].value = "20"
            ekran.kalem_formlari[0]["urun_id"].value = str(urun["id"])
            ekran._urun_secildi(0, str(urun["id"]))
            ekran.kalem_formlari[0]["miktar"].value = "2"
            ekran.kalem_formlari[0]["birim_fiyat"].value = "100"
            ekran.kalem_formlari[0]["iskonto"].value = "10"
            await ekran._kaydet()
            self.assertEqual(ekran.secili["sozlesme_bedeli"], 180)
            self.assertTrue(ekran.secili["siparis_no"].startswith("SIP-2020-"))
            await ekran._gonder()
            self.assertEqual(ekran.secili["onay_asamasi"], 2, "area chief's own approval is recorded on submission")
            self.assertEqual(ekran.secili["bekleyen_rol"], "Teknik Müdür Yardımcısı")

            await tmy.sayfa_ac("siparis")
            tmy_siparis = next(s for s in tmy.ekran.kayitlar if s["id"] == ekran.secili["id"])
            tmy.ekran._sec(tmy_siparis)
            await tmy.ekran._karar(True, "İş ve bedel kontrol edildi.")
            self.assertEqual(tmy.ekran.secili["bekleyen_rol"], "Okul Müdürü")

            await mudur.sayfa_ac("siparis")
            mudur_siparis = next(s for s in mudur.ekran.kayitlar if s["id"] == ekran.secili["id"])
            mudur.ekran._sec(mudur_siparis)
            await mudur.ekran._karar(True, "Onaylandı.")
            self.assertEqual(mudur.ekran.secili["durum"], "Sözleşme İmzalandı")
            self.assertEqual(len(mudur.ekran.secili["gecmis"]), 4)

            ekran._yeni()
            ekran.form["tarih"].value = "31.10.2026"
            ekran.form["cari_id"].value = str(cari["id"])
            ekran.form["bolum_id"].value = str(mobilya["id"])
            ekran.form["konu"].value = "Kuruş sınırı"
            ekran.form["ucret_esasi"].value = self.ilk_secenek(sef, "ucret_esasi")
            ekran.kalem_formlari[0]["aciklama"].value = "İş"
            ekran.kalem_formlari[0]["birim_fiyat"].value = "50"
            ekran.kalem_formlari[0]["iskonto"].value = "0,57"
            ekran._toplam_guncelle()
            self.assertIn("49,71 TL", ekran.kalem_toplami.value)
            await ekran._kaydet()
            self.assertEqual(ekran.secili["sozlesme_bedeli"], 49.71)
            ekran.kalem_formlari[0]["birim_fiyat"].value = "100000,00000000000001"
            ekran.kalem_formlari[0]["iskonto"].value = "12,3456789"
            await ekran._kaydet()
            self.assertEqual(ekran.secili["sozlesme_bedeli"], 87654.32)
            self.assertEqual(ekran.kalem_formlari[0]["birim_fiyat"].value, "100000,00000000000001")
            self.assertEqual(ekran.kalem_formlari[0]["iskonto"].value, "12,3456789")
            ekran.kalem_formlari[0]["birim_fiyat"].value = "9007199254740993,99"
            ekran.kalem_formlari[0]["iskonto"].value = "0"
            ekran._toplam_guncelle()
            self.assertIn("9.007.199.254.740.993,99 TL", ekran.kalem_toplami.value)
            await ekran._kaydet()
            self.assertEqual(ekran.secili["sozlesme_bedeli_kesin"], "9007199254740993.99")

        asyncio.run(siparis_ve_onay())

        sayman, sayman_sayfa = self.uygulama(400)

        async def satis_faturasi():
            await self.hesap_ac_ve_gir(sayman, sayman_sayfa, "sayman@derikmtal.k12.tr")
            self.durdur(sayman)
            await sayman.sayfa_ac("fatura")
            ekran = sayman.ekran
            ekran._yeni("Satış")
            onayli = next(s for s in ekran.veri["siparisler"] if s["konu"] == "Okul sırası üretimi")
            ekran._siparis_uygula(str(onayli["id"]))
            ekran.ust["belge_no"].value = "S-001"
            ekran.ust["tevkifat"].value = "0"
            ekran.ust["stopaj"].value = "0"
            ekran.satis_satirlari[0]["miktar"].value = "1"
            ekran._degisti()
            await ekran._onizle(dugme(sayman_sayfa, "Faturayı önizle"))
            self.assertEqual(ekran.onizleme["detay"]["matrah"], "90.00")
            self.assertEqual(ekran.onizleme["detay"]["kdv"], "18.00")
            await ekran._kaydet(dugme(sayman_sayfa, "Faturayı kaydet"))
            self.assertEqual(ekran.faturalar[0]["net_tutar"], "108.00")
            self.assertEqual(ekran.veri["siparisler"][0]["kalemler"][0]["kalan"], "1")
            self.assertIn("e-Fatura göndermez", metinler(sayman_sayfa))
            fatura_id = ekran.faturalar[0]["id"]

            await sayman.sayfa_ac("kasa")
            kasa = sayman.ekran
            kasa._yeni("Tahsilat")
            kasa.form["hesap"].value = "Banka (102)"
            kasa.form["fatura"].value = str(fatura_id)
            kasa.form["tutar"].value = "50"
            kasa.form["aciklama"].value = "Banka tahsilatı"
            kasa._degisti()
            await kasa._kaydet(dugme(sayman_sayfa, "Hareketi kaydet"))
            self.assertEqual(next(h for h in kasa.veri["hesaplar"] if h["hesap"] == "Banka (102)")["bakiye"], "50")
            self.assertEqual(next(f for f in kasa.veri["faturalar"] if f["id"] == fatura_id)["kalan"], "58.00")
            await sayman.sayfa_ac("fatura")
            self.assertEqual(sayman.ekran.faturalar[0]["odenen"], "50")
            self.assertEqual(sayman.ekran.faturalar[0]["kalan"], "58.00")

        asyncio.run(satis_faturasi())

        cihaz2, sayfa2 = self.uygulama(1280)

        async def cakisma():
            # 6) Same manager on a second device: the stale save is rejected with who changed it.
            await cihaz2.basla()
            alan(sayfa2, "E-posta").value = "mudur@derikmtal.k12.tr"
            alan(sayfa2, "Şifre").value = "Guclu-Sifre-1"
            await dugme(sayfa2, "Giriş yap").on_click(None)
            self.durdur(cihaz2)
            for app in (mudur, cihaz2):
                await app.sayfa_ac("bolum")
                app.ekran._sec(app.ekran._bul(mobilya["id"]))
            son_log = await mudur.supa.rpc("dose_son_degisiklik")
            mudur.ekran.form.kontroller["alan"].value = "Mobilya ve Dekorasyon"
            await mudur.ekran._kaydet(dugme(sayfa, "Kaydet"))
            self.assertEqual(mudur.ekran.secili["surum"], 2)
            self.assertGreater(await cihaz2.supa.rpc("dose_son_degisiklik"), son_log)
            cihaz2.ekran.form.kontroller["kod"].value = "MOB"
            await cihaz2.ekran._kaydet(dugme(sayfa2, "Kaydet"))
            self.assertIn("Ayşe Yılmaz", son_bildirim(sayfa2))
            self.assertEqual(cihaz2.ekran.secili["surum"], 2)
            self.assertEqual(cihaz2.ekran.secili["alan"], "Mobilya ve Dekorasyon")

            # 7) Deleting a workshop that personnel uses is refused by the database.
            once = len(sayfa.diyaloglar)
            mudur.ekran._sil()
            await sayfa.diyaloglar[-1].actions[1].on_click(None)
            self.assertGreater(len(sayfa.diyaloglar), once)
            self.assertIn("pasif", son_bildirim(sayfa).lower())

            # 8) Append-only audit log shows who did what.
            await mudur.sayfa_ac("islem_kaydi")
            kayit = metinler(sayfa)
            self.assertIn("Davet kabul edildi", kayit)
            self.assertIn("Hasan Şef", kayit)

        asyncio.run(cakisma())

        async def oturum_geri_yukle():
            # 9) Restarting the app restores the session from the stored refresh token; logout clears it.
            yeni, yeni_sayfa = self.uygulama(1280)
            yeni_sayfa.shared_preferences = sayfa.shared_preferences
            await yeni.basla()
            self.durdur(yeni)
            self.assertEqual(yeni.ben["rol"], "Okul Müdürü")
            await yeni.cikis()
            self.assertIsNone(yeni.supa.oturum)
            self.assertEqual(yeni_sayfa.shared_preferences.d, {})
            self.assertIn("Kendi e-postanız", metinler(yeni_sayfa))

        asyncio.run(oturum_geri_yukle())

    def test_merkez_yayini_ve_okul_saymani_dogrulamasi(self):
        merkez, merkez_sayfa = self.uygulama(400)
        mudur, mudur_sayfa = self.uygulama()
        sayman, sayman_sayfa = self.uygulama(400)
        kod = self.kontrol("/_test/sql", {
            "sql": "SELECT dose_private.okul_ac('Parametre Test Okulu', '908314') AS k"})[0]["k"]

        async def akis():
            await self.hesap_ac_ve_gir(merkez, merkez_sayfa, "mevzuat-merkez@ornek.test")
            self.kontrol("/_test/sql", {
                "sql": "SELECT dose_private.mevzuat_yoneticisi_ata("
                       "(SELECT id FROM auth.users WHERE email = $1), $2, true)",
                "params": ["mevzuat-merkez@ornek.test", "Merkez Yönetici"]})
            await merkez.ben_yukle()
            self.durdur(merkez)
            self.assertIsNone(merkez.ben["okul"])
            self.assertEqual([s[0] for s in merkez.gorunur_sayfalar()], ["ana", "merkez_mevzuat"])
            await merkez.sayfa_ac("merkez_mevzuat")
            ekran = merkez.ekran
            ekran._yeni()
            self.assertTrue(all(not k.value for k in ekran.form.values()))
            ekran.form["baslangic"].value = "01.01.2026"
            ekran.form["kaynak"].value = "Yalnız test için kontrol edilmiş örnek kaynak"
            for parametre in ekran.veri["alanlar"]:
                ekran.form[parametre["anahtar"]].value = "10"
            ekran.form["pb_kar_orani"].value = "6,00000001"
            ekran._degisti()
            await ekran.uzaktan_degisti()
            self.assertEqual(ekran.form["pb_kar_orani"].value, "6,00000001")
            dugme(merkez_sayfa, "Yayını kaydet").on_click(None)
            await dugme(merkez_sayfa, "Yayımla").on_click(None)
            self.assertEqual(son_bildirim(merkez_sayfa), "Merkez parametre yayını kaydedildi.")
            yayin = ekran.veri["yayinlar"][0]
            self.assertEqual(yayin["degerler"]["pb_kar_orani"], "0.0600000001")
            ekran._sec(yayin)
            self.assertIn("%6,00000001", metinler(merkez_sayfa))

            await self.hesap_ac_ve_gir(mudur, mudur_sayfa, "mevzuat-mudur@ornek.test")
            alan(mudur_sayfa, "Etkinleştirme kodu").value = kod
            alan(mudur_sayfa, "MEB kurum kodu").value = "908314"
            alan(mudur_sayfa, "Adınız soyadınız").value = "Parametre Müdürü"
            await dugme(mudur_sayfa, "Okulu etkinleştir").on_click(None)
            self.durdur(mudur)
            await mudur.sayfa_ac("kullanici")
            mudur.ekran._davet()
            alan(mudur_sayfa, "E-posta").value = "mevzuat-sayman@ornek.test"
            alan(mudur_sayfa, "Adı soyadı").value = "Parametre Saymanı"
            alan(mudur_sayfa, "Rol").value = "Sayman"
            await next(k for k in _gez(mudur_sayfa.diyaloglar[-1].actions) if k.content == "Davet et").on_click(None)
            await self.hesap_ac_ve_gir(sayman, sayman_sayfa, "mevzuat-sayman@ornek.test")
            self.durdur(sayman)
            await sayman.sayfa_ac("mevzuat")
            okul_ekrani = sayman.ekran
            okul_yayini = next(y for y in okul_ekrani.veri["yayinlar"] if y["id"] == yayin["id"])
            self.assertFalse(okul_yayini["onay"])
            okul_ekrani._sec(okul_yayini)
            dugme(sayman_sayfa, "Okul için doğrula").on_click(None)
            alan(sayman_sayfa, "Doğrulama açıklaması *").value = "Örnek değerler kontrol edildi"
            await dugme(sayman_sayfa, "Doğrulamayı kaydet").on_click(None)
            self.assertEqual(son_bildirim(sayman_sayfa), "Parametre yayını okulunuz için doğrulandı.")
            self.assertTrue(okul_ekrani.secili["onay"])
            dugme(sayman_sayfa, "Doğrulamayı geri çek").on_click(None)
            alan(sayman_sayfa, "Geri çekme gerekçesi *").value = "Kontrol yeniden yapılacak"
            await next(k for k in _gez(sayman_sayfa.diyaloglar[-1].actions)
                       if k.content == "Doğrulamayı geri çek").on_click(None)
            self.assertFalse(okul_ekrani.secili["onay"])
            self.assertEqual(son_bildirim(sayman_sayfa), "Okulunuzun doğrulaması geri çekildi.")

        asyncio.run(akis())

    def test_sayman_stok_hesap_ve_yevmiye_akisi(self):
        kod = self.kontrol("/_test/sql", {"sql": "SELECT dose_private.okul_ac('Finans Test Okulu', '237654') AS k"})[0]["k"]
        mudur, mudur_sayfa = self.uygulama()
        sayman, sayman_sayfa = self.uygulama(400)

        async def akis():
            await self.hesap_ac_ve_gir(mudur, mudur_sayfa, "finans-mudur@okul.k12.tr")
            alan(mudur_sayfa, "Etkinleştirme kodu").value = kod
            alan(mudur_sayfa, "MEB kurum kodu").value = "237654"
            alan(mudur_sayfa, "Adınız soyadınız").value = "Finans Müdürü"
            await dugme(mudur_sayfa, "Okulu etkinleştir").on_click(None)
            self.durdur(mudur)
            await mudur.sayfa_ac("kullanici")
            mudur.ekran._davet()
            alan(mudur_sayfa, "E-posta").value = "finans-sayman@okul.k12.tr"
            alan(mudur_sayfa, "Adı soyadı").value = "Sena Sayman"
            alan(mudur_sayfa, "Rol").value = "Sayman"
            await next(k for k in _gez(mudur_sayfa.diyaloglar[-1].actions) if k.content == "Davet et").on_click(None)

            await self.hesap_ac_ve_gir(sayman, sayman_sayfa, "finans-sayman@okul.k12.tr")
            self.durdur(sayman)
            self.assertEqual(sayman.ben["rol"], "Sayman")
            kart = await self.tanim_ekle(sayman, "malzeme", {
                "ad": "Kereste", "tur": "İlk Madde ve Malzeme", "birim": "Adet"})

            await sayman.sayfa_ac("vergi_hesap")
            hesap_ekrani = sayman.ekran
            hesap_ekrani._hesap_dialog()
            alan(sayman_sayfa, "Hesap kodu *").value = "193"
            alan(sayman_sayfa, "Hesap adı *").value = "Saymanın belirlediği hesap"
            await next(k for k in _gez(sayman_sayfa.diyaloglar[-1].actions)
                       if k.content == "Hesabı tanımla").on_click(None)
            hesap_ekrani._vergi_dialog("Satış stopajı", None)
            alan(sayman_sayfa, "Hesap *").value = "193"
            await next(k for k in _gez(sayman_sayfa.diyaloglar[-1].actions)
                       if k.content == "Vergi hesabını kaydet").on_click(None)
            self.assertEqual(hesap_ekrani.veri["vergi_hesaplari"][0]["hesap_kodu"], "193")

            await sayman.sayfa_ac("stok")
            ekran = sayman.ekran
            ekran._yeni()
            form = ekran.form
            form["malzeme"].value = str(kart["id"])
            form["yon"].value = "Giriş"
            form["miktar"].value = "10"
            form["tutar"].value = "9007199254740993,99"
            form["hesap"].value = "500"
            form["aciklama"].value = "Açılış sayımı"
            ekran._degisti()
            await ekran.uzaktan_degisti()
            self.assertIs(ekran.form, form)
            self.assertEqual(form["tutar"].value, "9007199254740993,99")
            sayman_sayfa.width = 1280
            await sayman._boyut_degisti()
            self.assertIs(ekran.form, form)
            await sayman.sayfa_ac("ana")
            self.assertEqual(sayman.sayfa, "stok")
            self.assertIn("Kaydedilmemiş", sayman_sayfa.diyaloglar[-1].content.value)
            sayman_sayfa.pop_dialog()
            await ekran._kaydet(dugme(sayman_sayfa, "Stok hareketini kaydet"))
            self.assertEqual(son_bildirim(sayman_sayfa), "Stok hareketi ve yevmiye kaydedildi.")
            self.assertEqual(ekran.veri["kartlar"][0]["tutar"], "9007199254740993.99")

            ekran._yeni()
            form = ekran.form
            form["malzeme"].value = str(kart["id"])
            form["yon"].value = "Çıkış"
            form["miktar"].value = "3"
            form["tutar"].value = "10,05"
            form["hesap"].value = "710"
            form["aciklama"].value = "Üretime sevk"
            ekran._degisti()
            await ekran._kaydet(dugme(sayman_sayfa, "Stok hareketini kaydet"))
            self.assertEqual(ekran.veri["kartlar"][0]["miktar"], "7")
            self.assertEqual(ekran.veri["kartlar"][0]["tutar"], "9007199254740983.94")
            cikis = ekran.veri["hareketler"][0]
            ekran._ters_dialog(cikis)
            alan(sayman_sayfa, "Ters kayıt gerekçesi *").value = "Yanlış malzeme seçildi"
            await next(k for k in _gez(sayman_sayfa.diyaloglar[-1].actions)
                       if k.content == "Ters kayıt oluştur").on_click(None)
            self.assertEqual(ekran.veri["kartlar"][0]["miktar"], "10")
            self.assertEqual(ekran.veri["kartlar"][0]["tutar"], "9007199254740993.99")

            await sayman.sayfa_ac("yevmiye")
            self.assertEqual(len(sayman.ekran.fisler), 3)
            stok_hesabi = next(s for s in sayman.ekran.mizan if s["hesap_kodu"] == "150")
            self.assertEqual(stok_hesabi["bakiye"], "9007199254740993.99")
            self.assertIn("9.007.199.254.740.993,99", metinler(sayman_sayfa))

            tedarikci = await self.tanim_ekle(sayman, "cari", {"unvan": "Malzeme Ltd", "tur": "Tedarikçi"})
            await sayman.sayfa_ac("fatura")
            ekran = sayman.ekran
            ekran._yeni("Alış")
            ekran.ust["cari"].value = str(tedarikci["id"])
            ekran.ust["belge_no"].value = "ALIŞ-001"
            ekran.ust["tevkifat"].value = "0"
            ekran.ust["stopaj"].value = "0"
            ekran.ust["temin_usulu"].value = "Doğrudan Temin"
            ekran.ust["gider_turu"].value = "İlk Madde ve Malzeme (Stoğa)"
            ekran.ust["belge_turu"].value = "e-Fatura"
            for kutu in ekran.alim_isaretleri.values():
                kutu.value = True
            satir = ekran.alis_satirlari[0]
            satir["malzeme"].value = str(kart["id"])
            satir["aciklama"].value = "Kereste alımı"
            satir["miktar"].value = "2"
            satir["fiyat"].value = "10,50"
            satir["kdv"].value = "20"
            satir["iskonto"].value = "0"
            ekran._degisti()
            await ekran._onizle(dugme(sayman_sayfa, "Faturayı önizle"))
            self.assertEqual(ekran.onizleme["detay"]["net_tutar"], "25.20")
            satir["fiyat"].value = "11"
            await ekran._kaydet(dugme(sayman_sayfa, "Faturayı kaydet"))
            self.assertIn("yeniden önizleyin", son_bildirim(sayman_sayfa))
            self.assertEqual(ekran.faturalar, [])
            satir["fiyat"].value = "10,50"
            await ekran._onizle(dugme(sayman_sayfa, "Faturayı önizle"))
            await ekran._kaydet(dugme(sayman_sayfa, "Faturayı kaydet"))
            self.assertEqual(ekran.faturalar[0]["net_tutar"], "25.20")
            self.assertEqual(ekran.faturalar[0]["temin_usulu"], "Doğrudan Temin")
            self.assertEqual(ekran.faturalar[0]["gider_turu"], "İlk Madde ve Malzeme (Stoğa)")
            self.assertTrue(ekran.faturalar[0]["alim_belgeler"]["muayene"])
            fatura_id = ekran.faturalar[0]["id"]

            await sayman.sayfa_ac("kasa")
            kasa = sayman.ekran
            kasa._yeni("Açılış")
            kasa.form["hesap"].value = "Banka (102)"
            kasa.form["karsi_hesap"].value = "500"
            kasa.form["tutar"].value = "30"
            kasa.form["aciklama"].value = "Banka açılışı"
            kasa._degisti()
            await kasa._kaydet(dugme(sayman_sayfa, "Hareketi kaydet"))
            kasa._yeni("Ödeme")
            kasa.form["hesap"].value = "Banka (102)"
            kasa.form["fatura"].value = str(fatura_id)
            kasa.form["tutar"].value = "25,20"
            kasa.form["aciklama"].value = "Tedarikçi ödemesi"
            kasa._degisti()
            await kasa._kaydet(dugme(sayman_sayfa, "Hareketi kaydet"))
            self.assertEqual(next(h for h in kasa.veri["hesaplar"] if h["hesap"] == "Banka (102)")["bakiye"], "4.80")
            odeme = kasa.veri["hareketler"][0]

            await sayman.sayfa_ac("fatura")
            ekran = sayman.ekran
            ekran._ters_dialog(ekran.faturalar[0])
            self.assertIn("GİB'de e-Fatura iptali yapmaz", metinler(sayman_sayfa))
            alan(sayman_sayfa, "Fatura ters kayıt gerekçesi *").value = "Belge hatası"
            await next(k for k in _gez(sayman_sayfa.diyaloglar[-1].actions)
                       if k.content == "Faturayı tersle").on_click(None)
            self.assertIn("açık ödeme veya tahsilat", son_bildirim(sayman_sayfa))
            sayman_sayfa.pop_dialog()
            sayman_sayfa.pop_dialog()
            await sayman.sayfa_ac("kasa")
            kasa = sayman.ekran
            kasa._ters_dialog(odeme)
            alan(sayman_sayfa, "Ters kayıt gerekçesi *").value = "Ödeme hatası"
            await next(k for k in _gez(sayman_sayfa.diyaloglar[-1].actions)
                       if k.content == "Ters kayıt oluştur").on_click(None)
            self.assertEqual(next(h for h in kasa.veri["hesaplar"] if h["hesap"] == "Banka (102)")["bakiye"], "30.00")
            await sayman.sayfa_ac("fatura")
            ekran = sayman.ekran
            ekran._ters_dialog(ekran.faturalar[0])
            alan(sayman_sayfa, "Fatura ters kayıt gerekçesi *").value = "Belge hatası"
            await next(k for k in _gez(sayman_sayfa.diyaloglar[-1].actions)
                       if k.content == "Faturayı tersle").on_click(None)
            self.assertEqual(ekran.faturalar[0]["iptal"], 1)

        asyncio.run(akis())


if __name__ == "__main__":
    unittest.main()
