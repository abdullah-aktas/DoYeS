"""Stock, journal and school-specific accounting settings for the Flet client."""
from __future__ import annotations

from decimal import Decimal
from typing import TypedDict
from uuid import uuid4

import flet as ft

try:
    from . import takvim, tanimlar as T
    from .ekranlar import Ekran, secim_kutusu, uyari_seridi
    from .supa import SupaHata
except ImportError:
    import takvim
    import tanimlar as T
    from ekranlar import Ekran, secim_kutusu, uyari_seridi
    from supa import SupaHata


VERGI_TURLERI = ("Satış KDV tevkifatı", "Satış stopajı", "Alış KDV tevkifatı", "Alış stopajı")


def para(deger: str) -> str:
    return T.sayi_yaz(Decimal(deger), 2)


def hesap_secenekleri(hesaplar: list[dict]) -> list[tuple[str, str]]:
    return [(h["kod"], f"{h['kod']} · {h['ad']}") for h in hesaplar
            if h["kod"].partition(".")[0] not in ("100", "102")]


async def kayit_sonrasi_yenile(ekran: Ekran, mesaj: str):
    try:
        await ekran.yukle()
    except SupaHata as e:
        ekran.app.bildir(f"{mesaj} Ancak liste yenilenemedi: {e.mesaj}", hata=True)
        return
    ekran.app.bildir(mesaj)


class StokFormu(TypedDict):
    malzeme: ft.Dropdown
    tarih: ft.TextField
    yon: ft.Dropdown
    miktar: ft.TextField
    tutar: ft.TextField
    hesap: ft.Dropdown
    aciklama: ft.TextField


class StokEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        self.veri: dict = {"kartlar": [], "hareketler": []}
        self.hesaplar: list[dict] = []
        self.form: StokFormu | None = None
        self.kirli = False
        self.uzak_uyari = False
        self.istek_id = ""

    @property
    def yazabilir(self) -> bool:
        return self.app.yetki("stok") == "y" and (self.app.ben or {}).get("rol") == "Sayman"

    def kaydedilmemis(self) -> bool:
        return self.form is not None and self.kirli

    def _degisti(self, _=None):
        self.kirli = True

    async def yukle(self):
        self.veri = await self.app.supa.rpc("dose_stok_veri")
        tanimlar = await self.app.supa.rpc("dose_finans_tanimlari")
        self.hesaplar = tanimlar["hesaplar"]
        self._ciz()

    async def uzaktan_degisti(self):
        if self.form is not None:
            self.uzak_uyari = True
        await self.yukle()

    def duzen(self):
        self._ciz()

    def _yeni(self, _=None):
        if self.form is not None or self.islemde:
            return
        kartlar = [(str(k["id"]), f"{k['ad']} · {k['tur']}") for k in self.veri["kartlar"] if k["aktif"]]
        self.form = {
            "malzeme": secim_kutusu("Stok kartı *", kartlar, None, on_select=self._degisti),
            "tarih": ft.TextField(label="Hareket tarihi *", value=takvim.bugun_istanbul().strftime("%d.%m.%Y"),
                                  hint_text="GG.AA.YYYY", on_change=self._degisti),
            "yon": secim_kutusu("Hareket yönü *", [("Giriş", "Giriş"), ("Çıkış", "Çıkış")], None,
                                on_select=self._degisti),
            "miktar": ft.TextField(label="Miktar *", keyboard_type=ft.KeyboardType.NUMBER, on_change=self._degisti),
            "tutar": ft.TextField(label="Toplam maliyet (TL) *", keyboard_type=ft.KeyboardType.NUMBER,
                                  helper="0 TL için açıkça 0 yazın.", on_change=self._degisti),
            "hesap": secim_kutusu("Muhasebe karşı hesabı *", hesap_secenekleri(self.hesaplar), None,
                                  on_select=self._degisti),
            "aciklama": ft.TextField(label="Hareket gerekçesi *", multiline=True, min_lines=2, on_change=self._degisti),
        }
        self.kirli = False
        self.uzak_uyari = False
        self.istek_id = str(uuid4())
        self._ciz()

    def _kapat(self, _=None):
        if self.islemde:
            self.app.bildir("İşlem tamamlanana kadar bekleyin.", hata=True)
        elif self.kaydedilmemis():
            self.app.onayla("Kaydedilmemiş stok hareketi bırakılacak.", "Değişiklikleri bırak", self._kapat_uygula)
        else:
            self.form = None
            self._ciz()

    async def _kapat_uygula(self):
        self.form = None
        self.kirli = False
        self._ciz()

    def _ciz(self):
        yeni = ft.FilledButton("Yeni stok hareketi", icon=ft.Icons.ADD, on_click=self._yeni,
                               visible=self.yazabilir, disabled=self.form is not None or self.islemde)
        try:
            from .tema import sayfa_baslik_satiri
        except ImportError:
            from tema import sayfa_baslik_satiri
        ust = sayfa_baslik_satiri("Stok durumu ve hareketleri", [
            yeni, ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile", disabled=self.islemde,
                                on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))],
                                 ft.Icons.SWAP_VERT)
        kontroller: list[ft.Control] = [
            ust,
            ft.Text("Giriş ve çıkışın toplam maliyetini ve karşı hesabını sayman belirler. "
                    "Hareketler silinmez; gerektiğinde gerekçeli ters kayıt oluşturulur."),
            ft.Text("0 TL maliyetli hareket izlenir ancak sıfır tutarlı yevmiye fişi oluşturulmaz. "
                    "İleri tarihli veya son hareketten eski tarihli kayıt yapılamaz.", size=12),
        ]
        if self.form is not None:
            f = self.form
            kaydet = ft.FilledButton("Stok hareketini kaydet", icon=ft.Icons.SAVE)
            kaydet.on_click = lambda _: self.app.page.run_task(self._kaydet, kaydet)
            alanlar = [f["malzeme"], f["tarih"], f["yon"], f["miktar"], f["tutar"], f["hesap"], f["aciklama"]]
            for alan in alanlar:
                alan.disabled = self.islemde
            kaydet.disabled = self.islemde
            kontroller.append(ft.Card(ft.Container(ft.Column([
                ft.Text("Yeni stok hareketi", size=18, weight=ft.FontWeight.BOLD),
                *([uyari_seridi("Kayıtlar başka bir kullanıcı tarafından değişti. Formunuz korundu; "
                                "güncel stok bakiyesi kayıtta yeniden denetlenir.")] if self.uzak_uyari else []),
                ft.ResponsiveRow([ft.Container(k, col={"xs": 12, "md": 6}) for k in alanlar]),
                ft.Row([kaydet, ft.TextButton("Vazgeç", disabled=self.islemde, on_click=self._kapat)], wrap=True),
            ], spacing=12), padding=16)))
        kontroller.append(ft.Text("Stok kartları", size=18, weight=ft.FontWeight.BOLD))
        for k in self.veri["kartlar"]:
            kontroller.append(ft.ListTile(
                title=ft.Text(k["ad"] + ("" if k["aktif"] else " · Pasif")),
                subtitle=ft.Text(f"{k['tur']} · {T.siparis_sayisi_yaz(k['miktar'])} {k.get('birim') or ''}"
                                 f" · {para(k['tutar'])} TL")))
        if not self.veri["kartlar"]:
            kontroller.append(ft.Text("Aktif stok kartı yok. Önce Malzeme / stok kartı ekranından kart tanımlayın."))
        kontroller.append(ft.Text("Hareket geçmişi", size=18, weight=ft.FontWeight.BOLD))
        for h in self.veri["hareketler"]:
            ters = None
            if self.yazabilir and h["kaynak"] == "Manuel" and not h["terslendi"]:
                ters = ft.IconButton(ft.Icons.UNDO, tooltip="Gerekçeli ters kayıt",
                                     disabled=self.islemde,
                                     on_click=lambda _, hareket=h: self._ters_dialog(hareket))
            durum = " · Terslendi" if h["terslendi"] else ""
            kontroller.append(ft.ListTile(
                title=ft.Text(f"{h['malzeme']} · {h['yon']}{durum}"),
                subtitle=ft.Text(f"{T.gosterim('tarih', h['tarih'])} · {T.siparis_sayisi_yaz(h['miktar'])}"
                                 f" · {para(h['tutar'])} TL · {h['aciklama']}"),
                trailing=ters))
        if not self.veri["hareketler"]:
            kontroller.append(ft.Text("Stok hareketi yok."))
        self.kontrol.controls = kontroller
        self.guncelle()

    async def _kaydet(self, dugme):
        async def is_():
            form = self.form
            if form is None:
                raise ValueError("Önce yeni bir stok hareketi açın.")
            if not form["malzeme"].value or not form["yon"].value or not form["hesap"].value:
                raise ValueError("Stok kartı, hareket yönü ve muhasebe karşı hesabı seçiniz.")
            if not (form["miktar"].value or "").strip() or not (form["tutar"].value or "").strip():
                raise ValueError("Miktarı ve saymanın belirlediği toplam maliyeti giriniz.")
            if not (form["aciklama"].value or "").strip():
                raise ValueError("Stok hareketi gerekçesi zorunludur.")
            try:
                tarih = T.tarih_coz(form["tarih"].value or "")
            except ValueError as e:
                raise ValueError("Geçerli hareket tarihi giriniz (GG.AA.YYYY).") from e
            try:
                miktar = T.ondalik_coz(form["miktar"].value or "")
                tutar = T.ondalik_coz(form["tutar"].value or "")
            except ValueError as e:
                raise ValueError("Miktar ve maliyet geçerli sayılar olmalıdır.") from e
            try:
                sonuc = await self.app.supa.rpc(
                    "dose_stok_kaydet", p_malzeme=int(form["malzeme"].value), p_tarih=tarih,
                    p_yon=form["yon"].value, p_miktar=str(miktar), p_tutar=str(tutar),
                    p_karsi_hesap=form["hesap"].value, p_aciklama=form["aciklama"].value.strip(), p_istek=self.istek_id)
            except SupaHata as e:
                if e.kod == "ag" or e.durum in (502, 503, 504):
                    raise SupaHata("Bağlantı kesildi; hareket kaydedilmiş olabilir. Listeyi kontrol edin veya "
                                   "aynı formu tekrar gönderin; aynı işlem iki kez kaydedilmez.",
                                   e.durum, e.kod, e.ipucu) from e
                raise
            self.form = None
            self.kirli = False
            self._ciz()
            await kayit_sonrasi_yenile(self, "Stok hareketi ve yevmiye kaydedildi." if sonuc["yevmiye_id"] is not None
                                      else "0 TL maliyetli stok hareketi kaydedildi; yevmiye fişi oluşmadı.")
        await self.guvenli_islem(is_, dugme)

    def _ters_dialog(self, hareket: dict):
        if self.islemde:
            return
        gerekce = ft.TextField(label="Ters kayıt gerekçesi *", multiline=True, min_lines=2)
        tersle = ft.FilledButton("Ters kayıt oluştur", icon=ft.Icons.UNDO)
        vazgec = ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog())
        istek = str(uuid4())

        async def onay(_):
            async def is_():
                if not (gerekce.value or "").strip():
                    raise ValueError("Ters kayıt gerekçesi zorunludur.")
                try:
                    await self.app.supa.rpc("dose_stok_tersle", p_hareket=hareket["id"],
                                            p_gerekce=gerekce.value.strip(), p_istek=istek)
                except SupaHata as e:
                    if e.kod == "ag" or e.durum in (502, 503, 504):
                        raise SupaHata("Bağlantı kesildi; ters kayıt oluşmuş olabilir. Listeyi kontrol edin veya "
                                       "aynı işlemi tekrar deneyin.", e.durum, e.kod, e.ipucu) from e
                    raise
                self.app.page.pop_dialog()
                await kayit_sonrasi_yenile(self, "Gerekçeli ters kayıt oluşturuldu.")
            await self.guvenli_islem(is_, tersle, (gerekce, vazgec))

        tersle.on_click = onay
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text("Stok hareketini tersle"),
            content=ft.Column([ft.Text("Daha yeni hareketler varsa önce onların terslenmesi gerekir."), gerekce],
                              tight=True),
            actions=[vazgec, tersle]))


class HesapEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        self.veri: dict = {"hesaplar": [], "vergi_hesaplari": []}

    @property
    def yazabilir(self) -> bool:
        return self.app.yetki("vergi_hesap") == "y" and (self.app.ben or {}).get("rol") == "Sayman"

    async def yukle(self):
        self.veri = await self.app.supa.rpc("dose_finans_tanimlari")
        self._ciz()

    def duzen(self):
        self._ciz()

    def _ciz(self):
        hesaplar = {h["kod"]: h["ad"] for h in self.veri["hesaplar"]}
        vergi = {h["tur"]: h for h in self.veri["vergi_hesaplari"]}
        try:
            from .tema import sayfa_baslik_satiri
        except ImportError:
            from tema import sayfa_baslik_satiri
        kontroller: list[ft.Control] = [
            sayfa_baslik_satiri("Muhasebe hesapları", [
                ft.FilledButton("Hesap tanımla", icon=ft.Icons.ADD, visible=self.yazabilir,
                                on_click=lambda _: self._hesap_dialog()),
                ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile",
                              on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))],
                              ft.Icons.ACCOUNT_TREE),
            ft.Text("Tevkifat ve stopaj hesapları otomatik seçilmez. Hesap kodunun ve kullanımının uygunluğunu "
                    "yetkili sayman doğrulamalıdır."),
            ft.Text("Vergi hesapları", size=18, weight=ft.FontWeight.BOLD),
        ]
        for tur in VERGI_TURLERI:
            kayit = vergi.get(tur)
            kod = kayit["hesap_kodu"] if kayit else None
            kontroller.append(ft.ListTile(
                title=ft.Text(tur), subtitle=ft.Text(f"{kod} · {hesaplar[kod]}" if kod else "Henüz belirlenmedi"),
                trailing=ft.IconButton(ft.Icons.EDIT, tooltip="Hesap seç", visible=self.yazabilir,
                                       on_click=lambda _, t=tur, k=kayit: self._vergi_dialog(t, k))))
        kontroller.append(ft.Text("Hesap planı", size=18, weight=ft.FontWeight.BOLD))
        kontroller.extend(ft.ListTile(title=ft.Text(f"{h['kod']} · {h['ad']}"), dense=True)
                          for h in self.veri["hesaplar"])
        self.kontrol.controls = kontroller
        self.guncelle()

    def _hesap_dialog(self):
        kod = ft.TextField(label="Hesap kodu *", hint_text="Örn. 193 veya 193.01")
        ad = ft.TextField(label="Hesap adı *")
        kaydet = ft.FilledButton("Hesabı tanımla")

        async def onay(_):
            async def is_():
                if not (kod.value or "").strip() or not (ad.value or "").strip():
                    raise ValueError("Hesap kodu ve adı zorunludur.")
                await self.app.supa.rpc("dose_hesap_ekle", p_kod=kod.value.strip(), p_ad=ad.value.strip())
                self.app.page.pop_dialog()
                await kayit_sonrasi_yenile(self, "Hesap tanımlandı.")
            await self.app.guvenli(is_, kaydet)

        kaydet.on_click = onay
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text("Okul için hesap tanımla"), content=ft.Column([kod, ad], tight=True),
            actions=[ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog()), kaydet]))

    def _vergi_dialog(self, tur: str, kayit: dict | None):
        secim = secim_kutusu("Hesap *", hesap_secenekleri(self.veri["hesaplar"]),
                             kayit["hesap_kodu"] if kayit else None)
        surum = kayit["surum"] if kayit else None
        kaydet = ft.FilledButton("Vergi hesabını kaydet")

        async def onay(_):
            async def is_():
                if not secim.value:
                    raise ValueError("Vergi hesabı seçiniz.")
                await self.app.supa.rpc("dose_vergi_hesabi_kaydet", p_tur=tur, p_hesap_kodu=secim.value, p_sur=surum)
                self.app.page.pop_dialog()
                await kayit_sonrasi_yenile(self, "Vergi hesabı kaydedildi.")
            await self.app.guvenli(is_, kaydet)

        kaydet.on_click = onay
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text(tur), content=secim,
            actions=[ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog()), kaydet]))


class YevmiyeEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        self.fisler: list[dict] = []
        self.mizan: list[dict] = []
        self.hesaplar: dict[str, str] = {}

    async def yukle(self):
        self.fisler = await self.app.supa.rpc("dose_yevmiye_veri")
        self.mizan = await self.app.supa.rpc("dose_mizan_veri")
        tanimlar = await self.app.supa.rpc("dose_finans_tanimlari")
        self.hesaplar = {h["kod"]: h["ad"] for h in tanimlar["hesaplar"]}
        self._ciz()

    def duzen(self):
        self._ciz()

    def _ciz(self):
        try:
            from .tema import sayfa_baslik_satiri
        except ImportError:
            from tema import sayfa_baslik_satiri
        kontroller: list[ft.Control] = [
            sayfa_baslik_satiri("Yevmiye / mizan", [
                ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile",
                              on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))],
                              ft.Icons.MENU_BOOK),
            ft.Text("Mizan", size=18, weight=ft.FontWeight.BOLD),
        ]
        for s in self.mizan:
            kod = s["hesap_kodu"]
            kontroller.append(ft.ListTile(
                title=ft.Text(f"{kod} · {self.hesaplar.get(kod, 'Hesap adı bulunamadı')}"),
                subtitle=ft.Text(f"Borç {para(s['borc'])} TL · Alacak {para(s['alacak'])} TL"
                                 f" · Borç - alacak {para(s['bakiye'])} TL")))
        if not self.mizan:
            kontroller.append(ft.Text("Henüz yevmiye kaydı yok."))
        kontroller.append(ft.Text("Yevmiye fişleri", size=18, weight=ft.FontWeight.BOLD))
        for fis in self.fisler:
            satirlar = [
                ft.Text(f"{s['hesap_kodu']} · {self.hesaplar.get(s['hesap_kodu'], 'Hesap adı bulunamadı')}"
                        f" — Borç {para(s['borc'])} TL / Alacak {para(s['alacak'])} TL")
                for s in fis["satirlar"]
            ]
            kontroller.append(ft.Card(ft.Container(ft.Column([
                ft.Text(f"{fis['fis_no']} · {T.gosterim('tarih', fis['tarih'])}", weight=ft.FontWeight.BOLD),
                ft.Text(f"{fis['kaynak']} · {fis['aciklama']}"), *satirlar,
            ], spacing=5), padding=12)))
        self.kontrol.controls = kontroller
        self.guncelle()
