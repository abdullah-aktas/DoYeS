"""Mobil (Flet) arayüz: ekranlar gerçek API'ye karşı kurulur, düğmeler çalıştırılır ve kontroller Flet protokolüyle
kodlanabilir olmalıdır. python -m unittest tests.test_mobil"""
import asyncio
import dataclasses
import inspect
from io import BytesIO
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import flet as ft  # noqa: E402
import msgpack  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from flet.controls.base_control import BaseControl  # noqa: E402
from flet.controls.object_patch import ObjectPatch  # noqa: E402
from flet.messaging.protocol import configure_encode_object_for_msgpack  # noqa: E402

from dose import db as dbm  # noqa: E402
from dose import mevzuat as M  # noqa: E402
from dose import onay  # noqa: E402
from dose.db import sifre_hashle  # noqa: E402
from mobil import istemci as ist  # noqa: E402
from mobil import uygulama as U  # noqa: E402
from sunucu import api  # noqa: E402

YIL = U.date.today().year
AY = U.date.today().month


class SahteTercihler:
    def __init__(self):
        self.d = {}

    async def get(self, k):
        return self.d.get(k)

    async def set(self, k, v):
        self.d[k] = v


class SahteSayfa:
    """Uygulamanın kullandığı ft.Page yüzeyi; her update'te görünümler Flet protokolüyle kodlanır."""

    def __init__(self):
        self.views: list[ft.View] = []
        self.dialoglar: list = []
        self.gorevler: list[asyncio.Task] = []
        self.overlay: list[ft.Control] = []
        self.shared_preferences = SahteTercihler()
        self.client_ip = "10.0.0.5"
        self.platform = None
        self.title = self.theme = self.theme_mode = self.on_view_pop = None
        self.width: float | None = None

    def update(self):
        kodla = configure_encode_object_for_msgpack(BaseControl)
        for v in self.views:
            ObjectPatch.from_diff(None, v, control_cls=BaseControl)
            msgpack.packb(v, default=kodla)
        for d in self.dialoglar:
            msgpack.packb(d, default=kodla)

    def show_dialog(self, d):
        self.dialoglar.append(d)
        self.update()

    def pop_dialog(self):
        if self.dialoglar:
            self.dialoglar.pop()

    def run_task(self, islev, *args):
        g = asyncio.ensure_future(islev(*args))
        self.gorevler.append(g)
        return g


def metin(c) -> str:
    parcalar = []
    for alan in ("value", "content", "label", "text", "tooltip"):
        x = getattr(c, alan, None)
        if isinstance(x, str):
            parcalar.append(x)
        elif isinstance(x, ft.Text) and isinstance(x.value, str):
            parcalar.append(x.value)
    if isinstance(c, ft.ListTile) and isinstance(c.title, ft.Text):
        parcalar.append(c.title.value or "")
    return " ".join(parcalar)


def gez(kok):
    if isinstance(kok, BaseControl):
        yield kok
        for f in dataclasses.fields(kok):
            if f.name in ("parent", "page", "data"):
                continue
            yield from gez(getattr(kok, f.name, None))
    elif isinstance(kok, (list, tuple)):
        for x in kok:
            yield from gez(x)


class MobilArayuz(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.yedekler = Path(cls.tmp.name) / "yedekler"
        cls.yedekler.mkdir()
        cls.onceki_api_yedekler, cls.onceki_db_yedekler = api.YEDEKLER, dbm.YEDEKLER
        api.YEDEKLER = dbm.YEDEKLER = cls.yedekler
        cls.app = api.uygulama_olustur(Path(cls.tmp.name) / "mobil.db")
        cls.c = TestClient(cls.app)
        d = cls.db = dbm.al()
        d.guncelle("kurum", 1, {"okul_adi": "Derik Mesleki ve Teknik Anadolu Lisesi",
                                "harcama_yetkilisi": "Ali Müdür", "kurum_kodu": "765432"})
        d.parametre_yaz(YIL, "fazla_calisma_saat_ucreti", 67.5)
        cls.bolum = d.ekle("bolum", {"ad": "Gıda Teknolojisi"})
        P = lambda ad, gorev: d.ekle("personel", {"ad_soyad": ad, "dose_gorevi": gorev, "bolum_id": cls.bolum,
                                                  "hizmet_sinifi": "Eğitim ve Öğretim Hizmetleri"})
        cls.p_ogr, cls.p_sef = P("Deniz Öğretmen", "Öğretmen"), P("Can Şef", "Bölüm/Alan Şefi")
        for ad, rol, pid in (("deniz", M.ROL_OGRETMEN, cls.p_ogr), ("can", M.ROL_SEF, cls.p_sef),
                             ("ali", M.ROL_MUDUR, None), ("ayse", M.ROL_SAYMAN, None)):
            h, tuz = sifre_hashle("Gizli123")
            d.ekle("kullanici", {"kullanici_adi": ad, "ad_soyad": ad.title(), "rol": rol, "sifre_hash": h, "tuz": tuz,
                                 "personel_id": pid})
        h, tuz = sifre_hashle("Gizli123")
        d.ekle("kullanici", {"kullanici_adi": "sistem", "ad_soyad": "Sistem Yöneticisi",
                             "rol": M.ROL_SISTEM, "sifre_hash": h, "tuz": tuz,
                             "sifre_degismeli": 0})
        cls.musteri = d.ekle("cari", {"unvan": "Derik Belediyesi", "tur": "Müşteri", "kamu_kurumu": 1})
        cls.urun = d.ekle("urun", {"ad": "Zeytinyağı 1 L", "birim": "Adet", "satis_fiyati": 400, "bolum_id": cls.bolum})
        d.ekle("maliyet_kalem", {"urun_id": cls.urun, "kalem_turu": "Direkt İlk Madde ve Malzeme", "miktar": 5, "birim_fiyat": 40})
        onay.akis_ayarla(True)
        test_istemcisi = cls.c

        class TestIstemci(ist.Istemci):
            def istek(self, yontem, yol, veri=None, **sorgu):
                sorgu = {k: v for k, v in sorgu.items() if v not in (None, "")}
                basliklar = dict(self.ek_basliklar)
                if self.token:
                    basliklar["Authorization"] = "Bearer " + self.token
                r = test_istemcisi.request(yontem, "/api" + yol, params=sorgu, json=veri, headers=basliklar)
                if r.status_code >= 400:
                    raise ist.ApiHatasi(r.json().get("hata") or f"Sunucu hatası ({r.status_code}).", r.status_code)
                return r.json()

        cls.yama = mock.patch.object(U, "Istemci", TestIstemci)
        cls.yama.start()

    @classmethod
    def tearDownClass(cls):
        cls.yama.stop()
        cls.c.close()
        dbm.al().kapat()
        api.YEDEKLER = cls.onceki_api_yedekler
        dbm.YEDEKLER = cls.onceki_db_yedekler
        cls.tmp.cleanup()

    # ------------------------------------------------------------ yardımcılar
    async def bekle(self):
        while self.s.gorevler:
            await self.s.gorevler.pop(0)

    async def tetikle(self, c, olay: str = "on_click", **ek):
        h = getattr(c, olay)
        self.assertIsNotNone(h, f"{type(c).__name__} '{metin(c)}' için {olay} yok")
        r = h(SimpleNamespace(control=c, data=None, **ek))
        if inspect.isawaitable(r):
            await r
        await self.bekle()

    def bul(self, tur, parca: str = "", kok=None):
        kok = kok if kok is not None else self.s.views[-1]
        for c in gez(kok):
            if isinstance(c, tur) and parca in metin(c):
                return c
        self.fail(f"{tur.__name__} '{parca}' bulunamadı")

    def hepsi(self, tur, kok=None):
        return [c for c in gez(kok if kok is not None else self.s.views[-1]) if isinstance(c, tur)]

    def hata_dialogu_yok(self):
        hatalar = [metin(d.title) + ": " + metin(d.content) for d in self.s.dialoglar
                   if isinstance(d, ft.AlertDialog) and metin(d.title) in ("İşlem yapılamadı", "Bağlantı sorunu")]
        self.assertEqual(hatalar, [])

    async def giris(self, ad: str, width: float | None = None) -> U.Uygulama:
        self.s = SahteSayfa()
        self.s.width = width
        u = U.Uygulama(self.s, "http://test")
        await u.baslat()
        self.assertFalse(u.t_adres.visible)
        u.t_kurum.value, u.t_kullanici.value, u.t_sifre.value = "765432", ad, "Gizli123"
        await self.tetikle(u.b_giris)
        self.assertEqual(u.l_hata.value, "", u.l_hata.value)
        self.assertEqual(self.s.views[-1].route, "/ana")
        return u

    async def sekme(self, u: U.Uygulama, ad: str):
        i = [s[1] for s in u.sekmeler].index(ad)
        u.nav.selected_index = i
        await self.tetikle(u.nav, "on_change")
        self.assertEqual(u.sekme, i)
        self.hata_dialogu_yok()

    def calistir(self, coro):
        asyncio.run(coro)

    # ------------------------------------------------------------ senaryolar
    def test_giris_ekrani_mobil_genisligine_uyar_ve_hatalari_gosterir(self):
        async def senaryo():
            self.s = SahteSayfa()
            self.s.width = 360
            u = U.Uygulama(self.s, "http://test")
            with mock.patch.object(self.s, "run_task"):
                await u.giris_ekrani()
            self.assertTrue(any(c.width == 328 for c in self.hepsi(ft.Container)))
            self.assertFalse(u.hata_alani.visible)
            await u.giris_yap()
            self.assertTrue(u.hata_alani.visible)
            self.assertIn("Kurum kodu", u.l_hata.value)
            self.assertIsNotNone(self.bul(ft.OutlinedButton, "Lisansı görüntüle / etkinleştir"))
        self.calistir(senaryo())

    def test_flet_giris_ekranindan_lisans_bilgisi_acilir(self):
        async def senaryo():
            self.s = SahteSayfa()
            u = U.Uygulama(self.s, "http://test")
            with mock.patch.object(self.s, "run_task"):
                await u.giris_ekrani()
            u.t_kurum.value = "765432"
            await self.tetikle(self.bul(ft.OutlinedButton, "Lisansı görüntüle / etkinleştir"))
            self.assertIn("Lisans", metin(self.s.dialoglar[-1].title))
            self.assertIn("Deneme", " ".join(metin(c) for c in gez(self.s.dialoglar[-1].content)))
            self.hata_dialogu_yok()
        self.calistir(senaryo())

    def test_ana_ekran_genislikte_masaustu_gezinmesine_gecer(self):
        async def senaryo():
            u = await self.giris("ali", 1280)
            self.assertTrue(u.rail.visible)
            self.assertFalse(u.nav.visible)
            self.assertIsNone(u.ana.navigation_bar)
            etiketler = {sekme.label for sekme in u.rail.destinations}
            self.assertTrue({"Stok Durumu", "Kasa / Banka", "Satış Faturaları", "Alış / Gider Belgeleri",
                             "Denetim Formu", "İşlem Kaydı", "Mevzuat Rehberi"}.issubset(etiketler))

            for etiket, ekran in (("Stok Durumu", "Stok / Ambar"), ("Kasa / Banka", "Kasa / banka"),
                                  ("Satış Faturaları", "Satış faturaları"),
                                  ("Alış / Gider Belgeleri", "Alış / gider belgeleri"),
                                  ("Denetim Formu", "Denetim formları"), ("İşlem Kaydı", "İşlem kaydı")):
                u.rail.selected_index = next(i for i, sekme in enumerate(u.rail.destinations)
                                             if sekme.label == etiket)
                await self.tetikle(u.rail, "on_change")
                self.assertIn(ekran, self.s.views[-1].appbar.title.value)
                u.geri()
                self.hata_dialogu_yok()

            u.rail.selected_index = next(i for i, sekme in enumerate(u.rail.destinations)
                                         if sekme.label == "Mevzuat Rehberi")
            await self.tetikle(u.rail, "on_change")
            self.assertTrue(any("DÖSE İşlemleri Mevzuat Rehberi" in metin(c) for c in gez(u.govde)))

            onay_index = next(i for i, sekme in enumerate(u.rail.destinations) if sekme.label == "Onaylar")
            u.rail.selected_index = onay_index
            await self.tetikle(u.rail, "on_change")
            self.assertEqual(u.sekme, 1)
            self.assertEqual(u.nav.selected_index, 1)
            self.s.width = 360
            u._boyut_degisti()
            self.assertFalse(u.rail.visible)
            self.assertTrue(u.nav.visible)
            self.assertIs(u.ana.navigation_bar, u.nav)
            self.assertEqual(u.nav.selected_index, 1)
        self.calistir(senaryo())

    def test_tum_masaustu_sayfalari_flet_gezinmesinde_acilir(self):
        from dose.kilavuz import SAYFA_YARDIMI

        async def senaryo():
            u = await self.giris("sistem", 1280)
            sayfa_modulleri = set(api.MOBIL_MODULLER) - {"denetim"}
            for modul in sayfa_modulleri:
                ad = api.MOBIL_MODULLER[modul]
                self.assertIn(ad, SAYFA_YARDIMI)
                self.assertIn(ad, U.SAYFA_YARDIM_ESLEME.values())

            diger_modulleri = {"yapilacaklar", "uyum", "kilavuz", "rehber", "kullanicilar"}
            dogrudan_moduller = {sekme[0] for sekme in u.masaustu_sekmeler}
            self.assertTrue(sayfa_modulleri <= dogrudan_moduller | diger_modulleri)

            await u.diger_sekmesi()
            diger_basliklari = {
                "Bugün ne yapmalıyım?", "Mevzuat uyum denetimi", "Nasıl yaparım? (adım adım)",
                "Mevzuat Rehberi", "Kullanıcılar ve roller",
            }
            gorunen_basliklar = {
                kontrol.title.value for kontrol in self.hepsi(ft.ListTile)
                if isinstance(kontrol.title, ft.Text) and kontrol.title.value
            }
            self.assertTrue(diger_basliklari <= gorunen_basliklar)

            for i, (modul, _etiket, _ikon, _islev) in enumerate(u.masaustu_sekmeler):
                if modul == "diger":
                    continue
                u.rail.selected_index = i
                await self.tetikle(u.rail, "on_change")
                self.hata_dialogu_yok()

        self.calistir(senaryo())

    def test_sayman_kasa_flet_yeni_hareket_formunu_ve_bakiye_onayini_gosterir(self):
        async def senaryo():
            u = await self.giris("ayse")
            await u.kasa_ekrani(0)
            self.assertIsNotNone(u.ana.floating_action_button)
            self.assertTrue(any("Kasa (100) bakiyesi" in metin(c) for c in gez(self.s.views[-1])))

            await u.kasa_formu()
            yon = self.bul(ft.Dropdown, "Yön")
            tur = self.bul(ft.Dropdown, "İşlem türü")
            onay = self.bul(ft.Checkbox, "Bakiye yetersiz")
            self.assertFalse(onay.visible)
            yon.value = "Çıkış"
            await self.tetikle(yon, "on_select")
            self.assertTrue(onay.visible)
            self.assertIn("Vergi Ödemesi", {secenek.text for secenek in tur.options})
            self.s.update()
            self.hata_dialogu_yok()
        self.calistir(senaryo())

    def test_flet_sayfa_baglamli_yardimi_api_icerigini_gosterir(self):
        async def senaryo():
            u = await self.giris("ayse")
            await u.kasa_ekrani(0)
            await self.tetikle(self.bul(ft.IconButton, "Bu sayfa hakkında yardım"))
            self.assertIn("Yardım — Kasa / Banka", metin(self.s.dialoglar[-1].title))
            self.assertTrue(any("Hazine payı" in metin(c) for c in gez(self.s.dialoglar[-1].content)))
            self.bul(ft.FilledButton, "Adım adım rehber", kok=self.s.dialoglar[-1])
            self.hata_dialogu_yok()
        self.calistir(senaryo())

    def test_sayman_stok_flet_giris_cikis_formlarini_gosterir(self):
        async def senaryo():
            u = await self.giris("ayse")
            await u.stok_ekrani(YIL, "hareketler")
            self.bul(ft.Dropdown, "Görünüm")
            self.bul(ft.OutlinedButton, "Excel'e aktar")

            await u.stok_hareket_formu("Giriş")
            sifir_onay = self.bul(ft.Checkbox, "Sıfır fiyatlı")
            self.assertTrue(sifir_onay.visible)
            self.assertFalse(self.bul(ft.TextField, "Birim fiyat").disabled)

            await u.stok_hareket_formu("Çıkış")
            self.assertFalse(self.bul(ft.Checkbox, "Sıfır fiyatlı").visible)
            self.assertTrue(self.bul(ft.TextField, "Birim fiyat").disabled)
            self.assertTrue(any("ağırlıklı ortalama maliyetle" in metin(c).lower()
                                for c in gez(self.s.views[-1])))
            self.s.update()
            self.hata_dialogu_yok()
        self.calistir(senaryo())

    def test_sayman_personel_excel_aktarimini_onizleyip_onaylar(self):
        async def senaryo():
            from openpyxl import Workbook

            u = await self.giris("ayse")
            wb = Workbook()
            ws = wb.active
            ws.append(["Sicil No", "Adı Soyadı", "Unvan"])
            ws.append(["FLET-EXCEL-01", "Flet Excel Personeli", "Öğretmen"])
            akim = BytesIO()
            wb.save(akim)
            icerik = akim.getvalue()

            class SahteDosyaSecici:
                async def pick_files(self, **_kwargs):
                    return [SimpleNamespace(name="personel.xlsx", size=len(icerik), bytes=icerik)]

            picker = SahteDosyaSecici()
            with mock.patch.object(U.ft, "FilePicker", return_value=picker):
                await u.tanim_ekrani("personel")
                self.assertIsNotNone(self.bul(ft.OutlinedButton, "Excel'den İçe Aktar"))
                await self.tetikle(self.bul(ft.OutlinedButton, "Excel'den İçe Aktar"))
                self.assertIn("Excel içe aktarma önizlemesi", metin(self.s.dialoglar[-1].title))
                self.assertIn("Flet Excel Personeli", metin(self.s.dialoglar[-1].content))
                await self.tetikle(self.bul(ft.FilledButton, "İçe aktar", kok=self.s.dialoglar[-1]))
            kayit = self.db.q1("SELECT * FROM personel WHERE sicil_no = 'FLET-EXCEL-01'")
            self.assertIsNotNone(kayit)
            self.assertEqual(kayit["ad_soyad"], "Flet Excel Personeli")
            self.db.sil("personel", kayit["id"])
            self.hata_dialogu_yok()
        self.calistir(senaryo())

    def test_kullanici_yonetimi_flet_ekranindan_hesap_ekler_ve_yetki_tablosunu_gosterir(self):
        async def senaryo():
            u = await self.giris("sistem")
            await u.diger_sekmesi()
            await self.tetikle(self.bul(ft.ListTile, "Kullanıcılar ve roller"))
            self.bul(ft.FilledButton, "Yeni kullanıcı")
            await self.tetikle(self.bul(ft.FilledButton, "Yeni kullanıcı"))
            self.bul(ft.TextField, "Kullanıcı adı").value = "arayuz.kullanici"
            self.bul(ft.TextField, "Ad soyad").value = "Arayüz Kullanıcısı"
            self.bul(ft.TextField, "Geçici şifre").value = "Gecici123"
            self.bul(ft.Dropdown, "Rol").value = M.ROL_MEMUR
            await self.tetikle(self.bul(ft.FilledButton, "Kaydet"))
            kayit = self.db.q1("SELECT * FROM kullanici WHERE kullanici_adi = 'arayuz.kullanici'")
            self.assertIsNotNone(kayit)
            self.assertEqual(kayit["rol"], M.ROL_MEMUR)
            self.assertTrue(kayit["sifre_degismeli"])
            await self.tetikle(self.bul(ft.OutlinedButton, "Rol / yetki tablosu"))
            self.assertTrue(self.hepsi(ft.DataTable, self.s.dialoglar[-1]))
            self.s.pop_dialog()
            self.s.update()
            self.hata_dialogu_yok()
        self.calistir(senaryo())

    def test_yedekleme_ekrani_yedek_alir_ve_geri_yukleme_secenegini_gosterir(self):
        async def senaryo():
            once = {p.name for p in self.yedekler.glob("*.db")}
            try:
                u = await self.giris("sistem")
                await u.diger_sekmesi()
                await self.tetikle(self.bul(ft.ListTile, "Yedekleme"))
                self.assertEqual(self.s.views[-1].appbar.title.value, "Yedekleme")
                await self.tetikle(self.bul(ft.FilledButton, "Şimdi yedekle"))
                sonra = {p.name for p in self.yedekler.glob("*.db")}
                self.assertGreater(len(sonra), len(once))
                self.bul(ft.TextButton, "Bu yedekten geri yükle")
                with tempfile.TemporaryDirectory() as dizin:
                    kaynak = Path(dizin) / "yerel_dose.db"
                    self.db.yedekle(kaynak)
                    secim = [SimpleNamespace(name=kaynak.name, size=kaynak.stat().st_size,
                                              bytes=kaynak.read_bytes())]
                    with mock.patch.object(ft.FilePicker, "pick_files",
                                           new=mock.AsyncMock(return_value=secim)):
                        await self.tetikle(self.bul(ft.OutlinedButton, "Dosyadan yedek yükle"))
                self.assertTrue(any("dose_yedek_yuklenen_" in p.name for p in self.yedekler.glob("*.db")))
                self.hata_dialogu_yok()
            finally:
                for ad in {p.name for p in self.yedekler.glob("*.db")} - once:
                    (self.yedekler / ad).unlink(missing_ok=True)
        self.calistir(senaryo())

    def test_masaustu_tanim_ekranindan_yetkili_kayit_olusturulur(self):
        async def senaryo():
            u = await self.giris("ali", 1280)
            bolum_sekmesi = next(i for i, sekme in enumerate(u.rail.destinations)
                                 if sekme.label == "Bölüm / Atölyeler")
            u.rail.selected_index = bolum_sekmesi
            await self.tetikle(u.rail, "on_change")
            self.assertEqual(self.s.views[-1].appbar.title.value, "Bölüm / Alan / Atölyeler")

            await self.tetikle(self.bul(ft.FilledButton, "Yeni kayıt"))
            self.bul(ft.TextField, "Bölüm / atölye adı").value = "Flet Masaüstü Bölümü"
            yontem = self.bul(ft.Dropdown, "ÜTP dağıtım yöntemi")
            yontem.value = yontem.options[0].key
            await self.tetikle(self.bul(ft.FilledButton, "Kaydet"))
            self.hata_dialogu_yok()
            kayit = self.db.q1("SELECT * FROM bolum WHERE ad = ?", ("Flet Masaüstü Bölümü",))
            self.assertIsNotNone(kayit)
            self.assertEqual(self.s.views[-1].appbar.title.value, "Bölüm / Alan / Atölyeler")

            await self.tetikle(self.bul(ft.ListTile, "Flet Masaüstü Bölümü"))
            self.bul(ft.TextField, "Bölüm / atölye adı").value = "Flet Güncellenmiş Bölüm"
            await self.tetikle(self.bul(ft.FilledButton, "Kaydet"))
            self.assertIsNone(self.db.q1("SELECT id FROM bolum WHERE ad = ?", ("Flet Masaüstü Bölümü",)))
            self.assertIsNotNone(self.db.q1("SELECT id FROM bolum WHERE ad = ?", ("Flet Güncellenmiş Bölüm",)))

            await self.tetikle(self.bul(ft.ListTile, "Flet Güncellenmiş Bölüm"))
            await self.tetikle(self.bul(ft.OutlinedButton, "Kaydı sil"))
            await self.tetikle(self.s.dialoglar[-1].actions[-1])
            self.assertIsNone(self.db.q1("SELECT id FROM bolum WHERE ad = ?", ("Flet Güncellenmiş Bölüm",)))
        self.calistir(senaryo())

    def test_urun_maliyet_analizi_flet_hesaplar_ve_kaydeder(self):
        urun_id = self.db.ekle("urun", {
            "ad": "Flet maliyet testi", "birim": "Adet", "bolum_id": self.bolum,
            "ucret_esasi": M.UCRET_ESASLARI[0], "satis_fiyati": 250, "kar_orani": 0.1, "kdv_orani": 0.2,
        })

        async def senaryo():
            u = await self.giris("can", 1280)
            index = next(i for i, sekme in enumerate(u.rail.destinations)
                         if sekme.label == "Ürün / Hizmet Kartları")
            u.rail.selected_index = index
            await self.tetikle(u.rail, "on_change")
            await self.tetikle(self.bul(ft.ListTile, "Flet maliyet testi"))
            await self.tetikle(self.bul(ft.OutlinedButton, "Maliyet Analizi / Fiyat Tespiti"))

            oto = self.bul(ft.Checkbox, "İşçilik ve diğer giderleri")
            oto.value = False
            await self.tetikle(oto, "on_change")
            self.bul(ft.TextField, "Birim fiyat").value = "100"
            await self.tetikle(self.bul(ft.OutlinedButton, "Hesapla"))
            texts = " ".join(metin(c) for c in self.hepsi(ft.Text))
            self.assertIn("Birim maliyet", texts)
            self.assertIn("100,00 TL", texts)
            await self.tetikle(self.bul(ft.FilledButton, "Kaydet"))
            self.assertEqual(self.db.deger(
                "SELECT COUNT(*) FROM maliyet_kalem WHERE urun_id = ?", (urun_id,)), 5)
            self.assertEqual(self.db.q1(
                "SELECT kalem_turu, birim_fiyat FROM maliyet_kalem WHERE urun_id = ? ORDER BY id LIMIT 1",
                (urun_id,))["birim_fiyat"], 100)

        try:
            self.calistir(senaryo())
        finally:
            self.db.ex("DELETE FROM maliyet_kalem WHERE urun_id = ?", (urun_id,))
            self.db.sil("urun", urun_id)

    def test_masaustu_muhasebe_mizan_yevmiye_ve_fis_detayini_acar(self):
        fis_id = self.db.ekle("yevmiye", {"fis_no": "FLET-MUH-TEST", "tarih": f"{YIL}-01-15",
                                          "aciklama": "Flet muhasebe testi", "kaynak": "Manuel"})
        self.db.ekle("yevmiye_satir", {"yevmiye_id": fis_id, "hesap_kodu": "100", "aciklama": "Kasa",
                                       "borc": 250, "alacak": 0})
        self.db.ekle("yevmiye_satir", {"yevmiye_id": fis_id, "hesap_kodu": "600", "aciklama": "Gelir",
                                       "borc": 0, "alacak": 250})
        try:
            async def senaryo():
                u = await self.giris("ali", 1280)
                muhasebe_sekmesi = next(i for i, sekme in enumerate(u.rail.destinations)
                                         if sekme.label == "Yevmiye / Mizan")
                u.rail.selected_index = muhasebe_sekmesi
                await self.tetikle(u.rail, "on_change")
                self.assertEqual(self.s.views[-1].appbar.title.value, "Muhasebe • Yevmiye")

                await self.tetikle(self.bul(ft.OutlinedButton, "Mizan"))
                self.bul(ft.Text, "100 • Kasa")
                self.bul(ft.Text, "Denk")

                await self.tetikle(self.bul(ft.OutlinedButton, "Yevmiye"))
                await self.tetikle(self.bul(ft.ListTile, "FLET-MUH-TEST"))
                self.assertEqual(self.s.views[-1].appbar.title.value, "Yevmiye FLET-MUH-TEST")
                self.bul(ft.Text, "100 • Kasa")
                self.bul(ft.Text, "600")
                self.bul(ft.Text, "Gelir")
                self.hata_dialogu_yok()
            self.calistir(senaryo())
        finally:
            with self.db.islem():
                self.db.ex("DELETE FROM yevmiye_satir WHERE yevmiye_id = ?", (fis_id,))
                self.db.sil("yevmiye", fis_id)

    def test_sayman_flet_masaustunde_manuel_fis_kaydeder_ve_siler(self):
        async def senaryo():
            u = await self.giris("ayse", 1280)
            muhasebe_sekmesi = next(i for i, sekme in enumerate(u.rail.destinations)
                                     if sekme.label == "Yevmiye / Mizan")
            u.rail.selected_index = muhasebe_sekmesi
            await self.tetikle(u.rail, "on_change")
            self.bul(ft.OutlinedButton, "Kayıtları yeniden üret")
            await self.tetikle(self.bul(ft.FilledButton, "Manuel fiş"))

            self.bul(ft.TextField, "Fiş tarihi").value = f"{YIL}-02-01"
            self.bul(ft.TextField, "Fiş açıklaması").value = "Flet manuel muhasebe"
            hesaplar = [c for c in self.hepsi(ft.Dropdown) if c.label == "Hesap"]
            self.assertEqual(len(hesaplar), 2)
            hesaplar[0].value, hesaplar[1].value = "100", "600"
            tutarlar = [c for c in self.hepsi(ft.TextField) if c.label in ("Borç", "Alacak")]
            self.assertEqual(len(tutarlar), 4)
            tutarlar[0].value, tutarlar[3].value = "300", "300"
            await self.tetikle(self.bul(ft.FilledButton, "Kaydet"))
            self.hata_dialogu_yok()
            fis = self.db.q1("SELECT * FROM yevmiye WHERE aciklama = ?", ("Flet manuel muhasebe",))
            self.assertIsNotNone(fis)

            await self.tetikle(self.bul(ft.ListTile, "Flet manuel muhasebe"))
            await self.tetikle(self.bul(ft.OutlinedButton, "Manuel fişi sil"))
            await self.tetikle(self.s.dialoglar[-1].actions[-1])
            self.assertIsNone(self.db.q1("SELECT id FROM yevmiye WHERE id = ?", (fis["id"],)))
            self.hata_dialogu_yok()
        self.calistir(senaryo())

    def test_sayman_flet_hesap_plani_hesabi_ekler_ve_siler(self):
        async def senaryo():
            u = await self.giris("ayse", 1280)
            muhasebe_sekmesi = next(i for i, sekme in enumerate(u.rail.destinations)
                                     if sekme.label == "Yevmiye / Mizan")
            u.rail.selected_index = muhasebe_sekmesi
            await self.tetikle(u.rail, "on_change")
            await self.tetikle(self.bul(ft.OutlinedButton, "Hesap planı"))
            await self.tetikle(self.bul(ft.FilledButton, "Hesap ekle"))
            self.bul(ft.TextField, "Hesap kodu").value = "FLET-900"
            self.bul(ft.TextField, "Hesap adı").value = "Flet test hesabı"
            await self.tetikle(self.bul(ft.FilledButton, "Kaydet"))
            self.hata_dialogu_yok()
            self.assertIsNotNone(self.db.q1("SELECT kod FROM hesap_plani WHERE kod = 'FLET-900'"))
            hesap_karti = next(c for c in self.hepsi(ft.Card)
                               if any(isinstance(x, ft.ListTile) and "FLET-900" in metin(x) for x in gez(c)))
            sil_butonu = next(c for c in gez(hesap_karti)
                              if isinstance(c, ft.IconButton) and c.tooltip == "Hesabı sil")
            await self.tetikle(sil_butonu)
            await self.tetikle(self.s.dialoglar[-1].actions[-1])
            self.hata_dialogu_yok()
            self.assertIsNone(self.db.q1("SELECT kod FROM hesap_plani WHERE kod = 'FLET-900'"))
        self.calistir(senaryo())

    def test_sayman_flet_yonetim_raporlarini_yil_ve_turle_goruntuler(self):
        async def senaryo():
            u = await self.giris("ayse", 1280)
            rapor_sekmesi = next(i for i, sekme in enumerate(u.rail.destinations)
                                 if sekme.label == "Raporlar")
            u.rail.selected_index = rapor_sekmesi
            await self.tetikle(u.rail, "on_change")
            self.assertIn(f"Raporlar • {YIL}", self.s.views[-1].appbar.title.value)
            secim = self.bul(ft.Dropdown, "Rapor")
            secim.value = "uc_aylik"
            await self.tetikle(secim, "on_select")
            self.bul(ft.Text, "Üç aylık faaliyet raporu (Çalışma Yönergesi md.48)")
            self.bul(ft.Text, "I. Dönem (Ocak-Mart)")
            self.bul(ft.OutlinedButton, "Excel")
            self.bul(ft.OutlinedButton, "PDF")
            self.hata_dialogu_yok()

            u_mobil = await self.giris("ayse", 360)
            await self.sekme(u_mobil, "Diğer")
            await self.tetikle(self.bul(ft.ListTile, "Yönetim raporları"))
            self.assertIn(f"Raporlar • {YIL}", self.s.views[-1].appbar.title.value)
            self.hata_dialogu_yok()
        self.calistir(senaryo())

    def test_sayman_flet_hazine_ve_vergi_yukumluluklerini_goruntuler(self):
        async def senaryo():
            u = await self.giris("ayse", 1280)
            hazine_index = next(i for i, sekme in enumerate(u.rail.destinations)
                                if sekme.label == "Hazine Payı / SHÇEK")
            u.rail.selected_index = hazine_index
            await self.tetikle(u.rail, "on_change")
            self.assertIn(f"Hazine Payı / SHÇEK • {YIL}", self.s.views[-1].appbar.title.value)
            self.bul(ft.Text, "Ocak")
            self.bul(ft.Text, "SHÇEK oranı / payı")
            self.bul(ft.OutlinedButton, "Excel")
            self.bul(ft.OutlinedButton, "PDF")
            self.hata_dialogu_yok()

            vergi_index = next(i for i, sekme in enumerate(u.rail.destinations)
                               if sekme.label == "KDV / Muhtasar")
            u.rail.selected_index = vergi_index
            await self.tetikle(u.rail, "on_change")
            self.assertIn(f"KDV / Muhtasar • {YIL}", self.s.views[-1].appbar.title.value)
            self.bul(ft.Text, "Ödenecek / devreden KDV")
            self.bul(ft.OutlinedButton, "Muhtasar ayrıntısı")
            self.hata_dialogu_yok()

            ay_detay = self.bul(ft.OutlinedButton, "Muhtasar ayrıntısı")
            await self.tetikle(ay_detay)
            self.assertIn("Muhtasar ayrıntısı", self.s.views[-1].appbar.title.value)
            self.hata_dialogu_yok()
        self.calistir(senaryo())

    def test_parca_basi_flet_bordro_taslagi_olusturup_hesaplar(self):
        siparis_id = self.db.ekle("siparis", {
            "siparis_no": "PB-FLET-TEST", "tarih": f"{YIL}-{AY:02d}-01", "bolum_id": self.bolum,
            "konu": "Flet parça başı testi", "ucret_esasi": "Parça Başı Ücret (Yön. md.8)",
            "sozlesme_bedeli": 1000, "kdv_orani": 0.2, "iscilik_tutari": 700,
            "kabul_tarihi": f"{YIL}-{AY:02d}-15", "durum": "Tamamlandı (Geçici Kabul)",
        })

        async def senaryo():
            u = await self.giris("can")
            await self.sekme(u, "Parça Başı")
            self.assertIsNotNone(u.ana.floating_action_button)
            await self.tetikle(u.ana.floating_action_button)
            self.assertIn("Parça başı bordro", self.s.views[-1].appbar.title.value)
            self.bul(ft.Dropdown, "Sipariş").value = str(siparis_id)
            self.bul(ft.TextField, "Ay içinde kabul edilen işçilik").value = "100"
            kisi = next(c for c in self.hepsi(ft.Dropdown) if c.label == "Kişi")
            kisi.value = str(self.p_ogr)
            await self.tetikle(self.bul(ft.FilledButton, "Kişi ekle"))
            await self.tetikle(self.bul(ft.OutlinedButton, "Hesapla"))
            self.hata_dialogu_yok()
            self.assertIn("Mevzuat kontrolünden geçti", " ".join(metin(c) for c in self.hepsi(ft.Text)))
            await self.tetikle(self.bul(ft.FilledButton, "Taslak kaydet"))
            self.hata_dialogu_yok()
            pb = self.db.q1("SELECT * FROM parca_basi WHERE siparis_id = ?", (siparis_id,))
            self.assertIsNotNone(pb)
            row = self.db.q1("SELECT * FROM parca_basi_satir WHERE parca_basi_id = ?", (pb["id"],))
            self.assertEqual((row["kisi_turu"], row["kisi_id"], row["katki"]), ("Personel", self.p_ogr, 1))

        try:
            self.calistir(senaryo())
        finally:
            for pb in self.db.q("SELECT id FROM parca_basi WHERE siparis_id = ?", (siparis_id,)):
                self.db.ex("DELETE FROM parca_basi_satir WHERE parca_basi_id = ?", (pb["id"],))
                self.db.sil("parca_basi", pb["id"])
                onay.sil("Parça Başı", pb["id"])
            self.db.sil("siparis", siparis_id)

    def test_ogretmen_fazla_calisma_ve_is_talebi(self):
        async def senaryo():
            u = await self.giris("deniz")
            self.assertEqual([s[1] for s in u.sekmeler],
                             ["Özet", "Onaylar", "İşler", "Fazla Ç.", "Parça Başı", "Diğer"])
            await self.sekme(u, "Fazla Ç.")
            await self.tetikle(u.ana.floating_action_button)
            self.assertTrue(self.s.views[-1].appbar.title.value.startswith("Fazla çalışma"))
            sec = u.api.get("/fazla-calisma/secenekler", yil=YIL, ay=AY)
            gun = next(g for g in sec["gunler"] if g["azami"])
            alanlar = [c for c in self.hepsi(ft.TextField) if c.keyboard_type == ft.KeyboardType.NUMBER]
            alan = alanlar[[g["gun"] for g in sec["gunler"]].index(gun["gun"])]
            alan.value = f"{gun['azami']:g}".replace(".", ",")
            await self.tetikle(alan, "on_change")
            await self.tetikle(self.bul(ft.OutlinedButton, "Hesapla"))
            self.hata_dialogu_yok()
            self.assertIn("Mevzuat kontrolünden geçti", " ".join(metin(c) for c in self.hepsi(ft.Text)))
            await self.tetikle(self.bul(ft.FilledButton, "onaya gönder"))
            self.hata_dialogu_yok()
            self.assertIn("onaya gönderildi", metin(self.s.dialoglar[-1].content))
            fc = self.db.q("SELECT * FROM fazla_calisma")
            self.assertEqual((len(fc), fc[0]["personel_id"], fc[0]["saat"]), (1, self.p_ogr, gun["azami"]))
            self.assertEqual(self.s.views[-1].route, "/ana")

            await self.sekme(u, "İşler")
            await self.tetikle(u.ana.floating_action_button)
            self.bul(ft.Dropdown, "Müşteri").value = str(self.musteri)
            self.bul(ft.Dropdown, "Ürün").value = str(self.urun)
            self.bul(ft.TextField, "Miktar").value = "10"
            await self.tetikle(self.bul(ft.FilledButton, "Kaydet"))
            self.hata_dialogu_yok()
            d = self.s.dialoglar[-1]
            self.assertEqual(d.title.value, "İş talebi kaydedildi")
            await self.tetikle(d.actions[0])
            s = self.db.q("SELECT * FROM siparis")
            self.assertEqual((len(s), s[0]["durum"], s[0]["bolum_id"], s[0]["sozlesme_bedeli"]), (1, "Teklif", self.bolum, 4000))
            await self.tetikle(self.bul(ft.ListTile, s[0]["siparis_no"], u.govde))
            self.assertEqual(self.s.views[-1].appbar.title.value, s[0]["siparis_no"])
            u.geri()
            await self.sekme(u, "Özet")
            await self.sekme(u, "Diğer")
            await self.tetikle(self.bul(ft.ListTile, "Çıkış", u.govde))
            self.assertEqual(self.s.views[-1].route, "/")
        self.calistir(senaryo())

    def test_sef_onayi_ve_mudur_ekranlari(self):
        fid = self.db.ekle("fazla_calisma", {"yil": YIL, "ay": AY, "personel_id": self.p_ogr, "saat": 2, "saat_ucreti": 67.5,
                                              "brut": 135, "net": 120, "durum": "Taslak"})
        token = self.c.post("/api/giris", json={"kullanici_adi": "deniz", "sifre": "Gizli123"}).json()["token"]
        r = self.c.post(f"/api/onay/{ist.Istemci.yol('onay', 'Fazla Çalışma', fid, 'gonder')[6:]}",
                        headers={"Authorization": "Bearer " + token}, json={})
        self.assertEqual(r.status_code, 200, r.text)

        async def senaryo():
            u = await self.giris("can")
            await self.sekme(u, "Onaylar")
            await self.tetikle(self.bul(ft.ListTile, "Fazla Çalışma", u.govde))
            self.assertEqual(self.s.views[-1].appbar.title.value, "Fazla Çalışma onayı")
            sef_kararlari = "SELECT COUNT(*) FROM onay_kaydi WHERE belge_turu = 'Fazla Çalışma' AND rol = ? AND karar = 'Uygun'"
            once = self.db.deger(sef_kararlari, (M.ROL_SEF,))
            await self.tetikle(self.bul(ft.FilledButton, "Uygun gör"))
            self.hata_dialogu_yok()
            self.assertEqual(self.db.deger(sef_kararlari, (M.ROL_SEF,)), once + 1)
            self.assertEqual(self.s.views[-1].route, "/ana")

            u = await self.giris("ali")
            await self.sekme(u, "Özet")
            await self.sekme(u, "Onaylar")
            await self.sekme(u, "Diğer")
            for oge in ("Stok durumu", "Kasa / banka", "Satış faturaları", "Alış / gider belgeleri", "İşlem kaydı"):
                await self.tetikle(self.bul(ft.ListTile, oge, u.govde))
                self.hata_dialogu_yok()
                self.assertEqual(len(self.s.views), 2, oge)
                if oge == "İşlem kaydı":
                    self.bul(ft.Dropdown, "Kullanıcı")
                    self.bul(ft.TextField, "Başlangıç")
                    self.bul(ft.TextField, "Bitiş")
                    self.bul(ft.OutlinedButton, "Excel'e aktar")
                    await self.tetikle(self.hepsi(ft.ListTile)[0])
                    self.assertEqual(self.s.views[-1].appbar.title.value, "İşlem ayrıntısı")
                    self.assertIn("Mobil", " ".join(metin(c) for c in self.hepsi(ft.Text)))
                    u.geri()
                u.geri()
            await self.tetikle(self.bul(ft.ListTile, "Şifre değiştir", u.govde))
            self.assertEqual(self.s.views[-1].appbar.title.value, "Şifre değiştir")
        self.calistir(senaryo())

    def test_ogretmen_denetime_kendi_gorev_maddesini_kaydeder(self):
        giris = self.c.post("/api/giris", json={"kullanici_adi": "ali", "sifre": "Gizli123"})
        token = {"Authorization": "Bearer " + giris.json()["token"]}
        olustur = self.c.post("/api/denetimler", headers=token,
                              json={"baslik": "Mobil denetim", "bilgiler": {"okul_adi": "Derik MTAL"}})
        self.assertEqual(olustur.status_code, 200, olustur.text)
        denetim_id = olustur.json()["id"]

        async def senaryo():
            u = await self.giris("deniz")
            await self.sekme(u, "Diğer")
            await self.tetikle(self.bul(ft.ListTile, "Denetim formu", u.govde))
            await self.tetikle(self.bul(ft.ListTile, "Mobil denetim"))
            bolum = self.bul(ft.Dropdown, "Denetim alanı")
            bolum.value = "3.1"
            await self.tetikle(bolum, "on_select")
            self.bul(ft.Dropdown, "Değerlendirme").value = "Uygun"
            self.bul(ft.TextField, "Açıklama / kanıt").value = "Öğrenci uygulama planı kontrol edildi."
            await self.tetikle(self.bul(ft.FilledButton, "Maddeyi kaydet"))
            madde = self.db.q1("SELECT durum, aciklama FROM denetim_madde WHERE denetim_id = ? AND madde_kodu = ?",
                               (denetim_id, "3.1.01"))
            self.assertEqual((madde["durum"], madde["aciklama"]),
                             ("Uygun", "Öğrenci uygulama planı kontrol edildi."))

        self.calistir(senaryo())

    def test_sayman_yil_sonu_utp_ekraninda_hesaplar_ve_taslak_kaydeder(self):
        self.db.ex("DELETE FROM utp_kisi WHERE yil = ?", (YIL,))
        self.db.ex("DELETE FROM yil_sonu WHERE yil = ?", (YIL,))

        async def senaryo():
            u = await self.giris("ayse", width=390)
            await self.sekme(u, "Diğer")
            await self.tetikle(self.bul(ft.ListTile, "Yıl sonu kârı", u.govde))
            self.assertIn("Yıl Sonu Kârı ve ÜTP", self.s.views[-1].appbar.title.value)
            self.assertTrue(self.hepsi(ft.Card))
            self.bul(ft.TextField, "Bilanço kârı").value = "10.000"
            await self.tetikle(self.bul(ft.OutlinedButton, "Hesapla"))
            self.hata_dialogu_yok()
            self.assertTrue(any("Bölüşüm sonucu" in metin(c) for c in self.hepsi(ft.Text)))
            await self.tetikle(self.bul(ft.FilledButton, "Kaydet (taslak)"))
            self.hata_dialogu_yok()
            self.assertIsNotNone(self.db.q1("SELECT yil FROM yil_sonu WHERE yil = ?", (YIL,)))
            self.assertGreater(self.db.deger("SELECT COUNT(*) FROM utp_kisi WHERE yil = ?", (YIL,), 0), 0)
            await self.tetikle(self.bul(ft.FilledButton, "Onaya gönder"))
            await self.tetikle(self.bul(ft.FilledButton, "Devam et", self.s.dialoglar[-1]))
            self.hata_dialogu_yok()
            kilit = self.c.get(f"/api/yil-sonu?yil={YIL}",
                               headers={"Authorization": "Bearer " + u.api.token})
            self.assertEqual(kilit.status_code, 200, kilit.text)
            self.assertTrue(kilit.json()["kilitli"])
            self.bul(ft.Text, "Durum: Bekliyor")

        try:
            self.calistir(senaryo())
        finally:
            with self.db.islem():
                self.db.ex("DELETE FROM utp_kisi WHERE yil = ?", (YIL,))
                self.db.ex("DELETE FROM yil_sonu WHERE yil = ?", (YIL,))
                self.db.ex("DELETE FROM onay_kaydi WHERE belge_turu = 'Yıl Sonu' AND belge_id = ?", (YIL,))
                self.db.ex("DELETE FROM onay_durum WHERE belge_turu = 'Yıl Sonu' AND belge_id = ?", (YIL,))

    def test_sayman_resmi_yazi_sablonunu_flet_ile_kaydeder(self):
        self.db.ex("DELETE FROM resmi_yazi WHERE konu = ?", ("Flet belge testi",))

        async def senaryo():
            u = await self.giris("ayse", width=390)
            await self.sekme(u, "Diğer")
            await self.tetikle(self.bul(ft.ListTile, "Resmi yazılar / belgeler", u.govde))
            self.assertEqual(self.s.views[-1].appbar.title.value, "Resmi Yazılar / Belgeler")
            await self.tetikle(self.bul(ft.FilledButton, "Yeni resmi yazı"))
            sablon = self.bul(ft.Dropdown, "Yazı şablonu")
            sablon.value = "Hazine payı ödemesi bildirimi"
            await self.tetikle(sablon, "on_select")
            self.assertIn("hazine payı", self.bul(ft.TextField, "Metin").value.lower())
            self.bul(ft.TextField, "Konu").value = "Flet belge testi"
            self.bul(ft.TextField, "Metin").value = "Flet test yazısı."
            await self.tetikle(self.bul(ft.FilledButton, "Kaydet"))
            self.hata_dialogu_yok()
            yazi = self.db.q1("SELECT * FROM resmi_yazi WHERE konu = ?", ("Flet belge testi",))
            self.assertIsNotNone(yazi)
            self.assertEqual(yazi["metin"], "Flet test yazısı.")

        try:
            self.calistir(senaryo())
        finally:
            self.db.ex("DELETE FROM resmi_yazi WHERE konu = ?", ("Flet belge testi",))

    def test_flet_uyum_yapilacaklar_ve_adim_adim_rehberi_gosterir(self):
        async def senaryo():
            u = await self.giris("ali", width=390)
            await self.sekme(u, "Diğer")
            await self.tetikle(self.bul(ft.ListTile, "Bugün ne yapmalıyım?", u.govde))
            self.assertIn("Bugün Ne Yapmalıyım?", [metin(c) for c in gez(u.govde)])
            await self.sekme(u, "Diğer")
            await self.tetikle(self.bul(ft.ListTile, "Mevzuat uyum denetimi", u.govde))
            self.assertIn("Mevzuat Uyum Denetimi", [metin(c) for c in gez(u.govde)])
            self.assertTrue(any("Uyum puanı" in metin(c) for c in gez(u.govde)))
            await self.sekme(u, "Diğer")
            await self.tetikle(self.bul(ft.ListTile, "Nasıl yaparım?", u.govde))
            self.assertTrue(any("Nasıl Yaparım?" in metin(c) for c in gez(u.govde)))
            self.assertTrue(any("Adım Adım" in metin(c) for c in gez(u.govde)))
            self.hata_dialogu_yok()

        self.calistir(senaryo())

    def test_flet_mevzuat_rehberi_tum_bolumleri_ve_yil_parametrelerini_gosterir(self):
        async def senaryo():
            u = await self.giris("ali", width=390)
            await self.sekme(u, "Diğer")
            await self.tetikle(self.bul(ft.ListTile, "Mevzuat Rehberi", u.govde))
            self.assertTrue(any("DÖSE İşlemleri Mevzuat Rehberi" in metin(c) for c in gez(u.govde)))

            bolum = self.bul(ft.Dropdown, "Rehber bölümü", u.govde)
            bolum.value = "Terimler Sözlüğü"
            await self.tetikle(bolum, "on_select")
            self.assertTrue(any("Harcama yetkilisi" in metin(c) for c in gez(u.govde)))

            bolum.value = "Yasal Takvim"
            await self.tetikle(bolum, "on_select")
            self.assertTrue(any("Önümüzdeki 60 gün" in metin(c) for c in gez(u.govde)))
            self.assertTrue(any("Merkez Saymanlık" in metin(c) for c in gez(u.govde)))

            bolum.value = "Yıllık Parametreler"
            await self.tetikle(bolum, "on_select")
            self.assertTrue(any("33.030,00 TL" in metin(c) for c in gez(u.govde)))
            self.hata_dialogu_yok()

        self.calistir(senaryo())


if __name__ == "__main__":
    unittest.main()
