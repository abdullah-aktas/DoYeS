"""Mobil (Flet) arayüz: ekranlar gerçek API'ye karşı kurulur, düğmeler çalıştırılır ve kontroller Flet protokolüyle
kodlanabilir olmalıdır. python -m unittest tests.test_mobil"""
import asyncio
import dataclasses
import inspect
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
        self.shared_preferences = SahteTercihler()
        self.client_ip = "10.0.0.5"
        self.platform = None
        self.title = self.theme = self.theme_mode = self.on_view_pop = None

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
        for ad, rol, pid in (("deniz", M.ROL_OGRETMEN, cls.p_ogr), ("can", M.ROL_SEF, cls.p_sef), ("ali", M.ROL_MUDUR, None)):
            h, tuz = sifre_hashle("Gizli123")
            d.ekle("kullanici", {"kullanici_adi": ad, "ad_soyad": ad.title(), "rol": rol, "sifre_hash": h, "tuz": tuz,
                                 "personel_id": pid})
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

    async def giris(self, ad: str) -> U.Uygulama:
        self.s = SahteSayfa()
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
        self.calistir(senaryo())

    def test_ogretmen_fazla_calisma_ve_is_talebi(self):
        async def senaryo():
            u = await self.giris("deniz")
            self.assertEqual([s[1] for s in u.sekmeler], ["Özet", "Onaylar", "İşler", "Fazla Ç.", "Diğer"])
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


if __name__ == "__main__":
    unittest.main()
