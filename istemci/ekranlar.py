"""Screens of the core phase: home, institution, definitions, users, audit log."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, localcontext
from typing import TypedDict

import flet as ft

try:
    from . import takvim
    from . import tanimlar as T
    from .supa import SupaHata
except ImportError:
    import takvim
    import tanimlar as T
    from supa import SupaHata

KLAVYE = {"para": ft.KeyboardType.NUMBER, "ondalik": ft.KeyboardType.NUMBER, "oran": ft.KeyboardType.NUMBER,
          "tarih": ft.KeyboardType.DATETIME}
ROL_GOREVI = {
    "Okul Müdürü": "Harcama yetkilisi: sipariş, parça başı ve fazla çalışma olurunu verir; kullanıcıları yönetirsiniz.",
    "Teknik Müdür Yardımcısı": "Gerçekleştirme görevlisi: işi ve puantajı kontrol edip imzalarsınız; taslak da hazırlayabilirsiniz.",
    "Sayman": "Fatura, kasa, hazine payı, ÜTP ödemesi ve merkez parametre doğrulamasını yaparsınız.",
    "Alan Şefi": "Atölyenizin siparişini yürütür, puantajı imzalar ve onayın ilk aşamasını verirsiniz.",
    "Öğretmen": "Kendi atölyenizde parça başı ve fazla çalışma puantajını yazarsınız; sipariş taslağı açabilirsiniz.",
    "Memur / Veri Girişi": "Cari, stok kartı, öğrenci gibi tanımları ve resmi yazı taslaklarını girersiniz.",
    "İzleyici / Denetçi": "Kayıtları ve işlem izini değiştirmeden incelersiniz; iç denetim formu doldurabilirsiniz.",
    "Sistem Yöneticisi": "Okulun tanımlarını ve kullanıcılarını yönetirsiniz (onay ve tahsilat sizde değildir).",
}
SURE_GOREN = {"Okul Müdürü", "Sayman", "Teknik Müdür Yardımcısı", "Sistem Yöneticisi", "İzleyici / Denetçi"}


def secim_kutusu(etiket: str, secenekler: list[tuple[str, str]], deger, bos: bool = True,
                 disabled: bool = False, on_select=None) -> ft.Dropdown:
    deger = "" if deger is None else str(deger)
    liste = ([("", "—")] if bos else []) + [(str(k), e) for k, e in secenekler]
    if deger and deger not in {k for k, _ in liste}:
        liste.append((deger, deger))
    return ft.Dropdown(label=etiket, options=[ft.DropdownOption(key=k, text=e) for k, e in liste],
                       value=deger if deger or bos else None, disabled=disabled, on_select=on_select, expand=True)


class Form:
    """Field widgets for one record; knows which fields changed and builds the payload."""

    def __init__(self, app, alanlar, kayit: dict | None, yazabilir: bool, fk: dict | None = None):
        self.app = app
        self.alanlar = alanlar
        self.kirli = False
        self.kontroller: dict[str, ft.Control] = {}
        hucreler = []
        for alan, etiket, tur, zorunlu, liste in alanlar:
            deger = (kayit or {}).get(alan, 1 if alan == "aktif" else None)
            k = self._kontrol(etiket + (" *" if zorunlu else ""), tur, zorunlu, liste, deger, yazabilir, fk or {})
            self.kontroller[alan] = k
            hucreler.append(ft.Container(k, col={"xs": 12, "md": 12 if tur in ("cokmetin", "bool") else 6}))
        self.kontrol = ft.ResponsiveRow(hucreler, spacing=12, run_spacing=12)

    def _degisti(self, _=None):
        self.kirli = True

    def _kontrol(self, etiket, tur, zorunlu, liste, deger, yazabilir, fk):
        if tur == "bool":
            return ft.Checkbox(label=etiket, value=bool(deger), disabled=not yazabilir, on_change=self._degisti)
        if tur in ("secim", "secim_sayi"):
            return secim_kutusu(etiket, self.app.secenek.get(liste, []), deger, bos=not zorunlu or deger is None,
                                disabled=not yazabilir, on_select=self._degisti)
        if tur in ("fk_bolum", "fk_malzeme"):
            secenek = [(str(i), ad) for i, ad, aktif in fk.get(tur, []) if aktif or i == deger]
            return secim_kutusu(etiket, secenek, deger, disabled=not yazabilir, on_select=self._degisti)
        return ft.TextField(
            label=etiket, value=T.gosterim(tur, deger), read_only=not yazabilir or tur == "salt",
            multiline=tur == "cokmetin", min_lines=2 if tur == "cokmetin" else None,
            hint_text="GG.AA.YYYY" if tur == "tarih" else None,
            keyboard_type=KLAVYE.get(tur, ft.KeyboardType.TEXT), on_change=self._degisti)

    def veri(self) -> dict:
        return T.form_verisi(self.alanlar, {a: k.value for a, k in self.kontroller.items()})


def son_degisiklik(kayit: dict | None) -> ft.Control:
    if not kayit or not kayit.get("guncelleyen"):
        return ft.Container()
    return ft.Text(f"Son değişiklik: {kayit['guncelleyen']} — {kayit.get('guncelleme') or ''}", size=12,
                   color=ft.Colors.ON_SURFACE_VARIANT)


def uyari_seridi(metin: str) -> ft.Control:
    return ft.Container(ft.Row([ft.Icon(ft.Icons.WARNING_AMBER, color=ft.Colors.ON_ERROR_CONTAINER),
                                ft.Text(metin, color=ft.Colors.ON_ERROR_CONTAINER, expand=True)]),
                        bgcolor=ft.Colors.ERROR_CONTAINER, padding=10, border_radius=8)


class Ekran:
    def __init__(self, app):
        self.app = app
        self.kontrol = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
        self.islemde = False

    async def yukle(self):
        pass

    async def uzaktan_degisti(self):
        await self.yukle()

    def duzen(self):
        pass

    def kaydedilmemis(self) -> bool:
        return False

    def guncelle(self):
        self.app.page.update()

    async def guvenli_islem(self, is_, dugme: ft.Control, kilitlenecek: tuple[ft.Control, ...] = ()):
        if self.islemde:
            return False
        onceki_durumlar = [kontrol.disabled for kontrol in kilitlenecek]
        self.islemde = True
        for kontrol in kilitlenecek:
            kontrol.disabled = True
        self.duzen()
        try:
            return await self.app.guvenli(is_, dugme)
        finally:
            self.islemde = False
            for kontrol, onceki in zip(kilitlenecek, onceki_durumlar):
                kontrol.disabled = onceki
            self.duzen()


class SiparisKalemKontrolleri(TypedDict):
    urun_id: ft.Dropdown
    aciklama: ft.TextField
    miktar: ft.TextField
    birim: ft.TextField
    birim_fiyat: ft.TextField
    iskonto: ft.TextField


# ---------------------------------------------------------------------- home
class AnaEkran(Ekran):
    async def yukle(self):
        ben = self.app.ben
        okul = ben.get("okul") or {}
        c: list[ft.Control] = [ft.Text(f"Merhaba {ben.get('ad_soyad') or ''}", size=24, weight=ft.FontWeight.BOLD),
                               ft.Text(f"{okul.get('ad', '')} · {ben.get('rol')}", size=15)]
        if ben.get("merkez_mevzuat") and not okul:
            c.append(ft.Text("Merkez parametre yayınlarını hazırlayıp kaynaklarıyla yayımlayabilirsiniz. "
                             "Her okulun saymanı yayını ayrıca doğrular."))
            self.kontrol.controls = c
            self.guncelle()
            return
        if okul.get("salt_okunur"):
            c.append(uyari_seridi("Lisans süresi doldu. Kayıtları görebilirsiniz ama değiştiremezsiniz. "
                                  "Lisansı yenilemek için satıcınıza başvurun."))
        c.append(ft.Card(ft.Container(ft.Column([
            ft.Text("Yasal göreviniz", weight=ft.FontWeight.BOLD),
            ft.Text(ROL_GOREVI.get(ben.get("rol"), ""))], spacing=6), padding=16)))
        try:
            gorev = await self.app.supa.rpc("dose_gorevlerim")
        except SupaHata:
            gorev = {"gorevler": []}
        bekleyen = gorev.get("gorevler") or []
        if bekleyen:
            satirlar = [ft.ListTile(
                leading=ft.Icon(ft.Icons.TASK_ALT, color=ft.Colors.TEAL_700),
                title=ft.Text(g.get("baslik") or g.get("ozet") or "Görev"),
                subtitle=ft.Text(g.get("ozet") or ""),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                on_click=lambda _, s=g.get("sayfa"): self.app.page.run_task(self.app.sayfa_ac, s) if s else None)
                for g in bekleyen[:12]]
            c.append(ft.Card(ft.Container(ft.Column(
                [ft.Text("Bugün ne yapmalıyım?", weight=ft.FontWeight.BOLD)] + satirlar, spacing=0), padding=12)))
        else:
            c.append(ft.Text("Şu an size düşen bekleyen onay yok.", size=13, color=ft.Colors.ON_SURFACE_VARIANT))
        if ben.get("rol") in SURE_GOREN:
            sureler = takvim.yaklasan_sureler(takvim.bugun_istanbul())
            satirlar = []
            for s in sureler:
                renk = ft.Colors.ERROR if s["kalan"] <= 3 else (ft.Colors.TERTIARY if s["kalan"] <= 7 else None)
                satirlar.append(ft.ListTile(
                    leading=ft.Icon(ft.Icons.EVENT, color=renk),
                    title=ft.Text(takvim.sure_cumlesi(s), color=renk, weight=ft.FontWeight.BOLD if renk else None),
                    subtitle=ft.Text(f"Son gün {s['son_gun'].strftime('%d.%m.%Y')}. {s['gecikme']}")))
            c.append(ft.Card(ft.Container(ft.Column(
                [ft.Text("Yaklaşan yasal süreler", weight=ft.FontWeight.BOLD)] + satirlar, spacing=0), padding=12)))
        lisans = okul.get("lisans_bitis")
        c.append(ft.Text(f"Kurum kodu {okul.get('kurum_kodu', '')} · Lisans "
                         f"{'bitişi ' + T.gosterim('tarih', lisans) if lisans else 'süresiz'}",
                         size=12, color=ft.Colors.ON_SURFACE_VARIANT))
        self.kontrol.controls = c
        self.guncelle()


# ---------------------------------------------------------------------- institution
class KurumEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        self.kayit: dict | None = None
        self.form: Form | None = None
        self.serit = ft.Container(visible=False)

    async def yukle(self, zorla: bool = True):
        satirlar = await self.app.supa.sec("kurum")
        yeni = satirlar[0] if satirlar else None
        if not zorla and self.form and self.form.kirli:
            if yeni and self.kayit and yeni.get("surum") != self.kayit.get("surum"):
                self.serit.content = uyari_seridi(f"{yeni.get('guncelleyen')} bu kaydı az önce değiştirdi. "
                                                  "Kaydederseniz reddedilir; güncelini görmek için Yenile'ye basın.")
                self.serit.visible = True
                self.guncelle()
            return
        self.kayit = yeni
        self.serit.visible = False
        self._ciz()

    async def uzaktan_degisti(self):
        await self.yukle(zorla=False)

    def _ciz(self):
        yazabilir = self.app.yetki("kurum") == "y"
        if not self.kayit:
            self.kontrol.controls = [ft.Text("Kurum kaydı bulunamadı.")]
            self.guncelle()
            return
        self.form = Form(self.app, T.KURUM_ALANLARI, self.kayit, yazabilir)
        kaydet = ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, visible=yazabilir)

        async def kaydet_tik(_):
            async def is_():
                veri = self.form.veri()
                veri["surum"] = self.kayit["surum"]
                try:
                    self.kayit = await self.app.supa.guncelle("kurum", veri, okul_id=self.kayit["okul_id"])
                except SupaHata as e:
                    if e.cakisma:
                        await self.yukle()
                    raise
                self.serit.visible = False
                self._ciz()
                self.app.bildir("Kurum bilgileri kaydedildi.")

            await self.app.guvenli(is_, kaydet)

        async def yenile(_):
            await self.app.guvenli(self.yukle)

        kaydet.on_click = kaydet_tik
        self.kontrol.controls = [
            ft.Row([ft.Text("Kurum bilgileri", size=20, weight=ft.FontWeight.BOLD, expand=True),
                    ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile", on_click=yenile)]),
            self.serit, son_degisiklik(self.kayit), self.form.kontrol, ft.Row([kaydet])]
        self.guncelle()


# ---------------------------------------------------------------------- definitions
class TanimEkrani(Ekran):
    def __init__(self, app, tablo: str, baslik: str):
        super().__init__(app)
        self.tablo = tablo
        self.baslik = baslik
        self.alanlar = T.TANIM_ALANLARI[tablo]
        self.kayitlar: list[dict] = []
        self.secili: dict | None = None
        self.form_acik = False
        self.form: Form | None = None
        self.fk: dict[str, list] = {}
        self.arama = ft.TextField(hint_text="Ara", prefix_icon=ft.Icons.SEARCH, dense=True,
                                  on_change=lambda _: self._liste_ciz())
        self.liste = ft.ListView(expand=True, spacing=0)
        self.serit = ft.Container(visible=False)
        self.form_kutusu = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
        self.kontrol = ft.Container(expand=True)

    @property
    def yazabilir(self) -> bool:
        return self.app.yetki(self.tablo) == "y"

    async def _fk_yukle(self):
        turler = {t for _, _, t, _, _ in self.alanlar}
        self.fk = {}
        try:
            if "fk_bolum" in turler:
                self.fk["fk_bolum"] = [(b["id"], b["ad"], b["aktif"]) for b in
                                       await self.app.supa.sec("bolum", secim="id,ad,aktif", sira="ad")]
            if "fk_malzeme" in turler:
                self.fk["fk_malzeme"] = [
                    (m["id"], m["ad"], m["aktif"]) for m in
                    await self.app.supa.sec("malzeme", secim="id,ad,aktif,tur", sira="ad")
                    if m["tur"] in ("Mamul", "Ticari Mal")]
        except SupaHata:
            pass

    async def yukle(self, zorla: bool = True):
        self.kayitlar = await self.app.supa.sec(self.tablo, sira=T.TANIM_SIRALAMA[self.tablo])
        await self._fk_yukle()
        guncel = self._bul(self.secili.get("id")) if self.secili else None
        if self.secili and not guncel:
            self.secili, self.form_acik = None, False
            self.app.bildir("Açık olan kayıt başka bir kullanıcı tarafından silindi.", hata=True)
        elif guncel and not zorla and self.form and self.form.kirli:
            if guncel.get("surum") != self.secili.get("surum"):
                self.serit.content = uyari_seridi(f"{guncel.get('guncelleyen')} bu kaydı az önce değiştirdi. "
                                                  "Kaydederseniz reddedilir; güncelini görmek için Yenile'ye basın.")
                self.serit.visible = True
            self._liste_ciz(guncelle=False)
            self.guncelle()
            return
        else:
            self.secili = guncel
        self._ciz()

    async def uzaktan_degisti(self):
        await self.yukle(zorla=False)

    def _bul(self, kimlik) -> dict | None:
        return next((k for k in self.kayitlar if k["id"] == kimlik), None)

    def duzen(self):
        self._ciz()

    def _ciz(self):
        self.serit.visible = False
        self._liste_ciz(guncelle=False)
        self._form_ciz()
        yeni = ft.FilledButton("Yeni", icon=ft.Icons.ADD, visible=self.yazabilir, on_click=self._yeni)
        ust = ft.Row([ft.Text(self.baslik, size=20, weight=ft.FontWeight.BOLD, expand=True), yeni,
                      ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile", on_click=self._yenile)])
        liste_kolonu = ft.Column([ust, self.arama, self.liste], expand=True, spacing=8)
        if self.app.genis:
            self.kontrol.content = ft.Row([
                ft.Container(liste_kolonu, width=380),
                ft.VerticalDivider(width=1),
                ft.Container(self.form_kutusu, expand=True, padding=ft.Padding.only(left=12))],
                expand=True, vertical_alignment=ft.CrossAxisAlignment.START)
        else:
            self.kontrol.content = self.form_kutusu if self.form_acik else liste_kolonu
        self.guncelle()

    def _liste_ciz(self, guncelle: bool = True):
        baslik_alani = T.TANIM_BASLIK_ALANI[self.tablo]
        a1, a2 = T.TANIM_ALT_ALANLAR[self.tablo]
        satirlar = []
        for k in self.kayitlar:
            if not T.eslesir(k, self.arama.value or "", self.tablo):
                continue
            alt = " · ".join(str(k[a]) for a in (a1, a2) if k.get(a))
            if not k.get("aktif", 1):
                alt = ("Pasif · " + alt) if alt else "Pasif"
            satirlar.append(ft.ListTile(
                title=ft.Text(k.get(baslik_alani) or "(adsız)",
                              color=None if k.get("aktif", 1) else ft.Colors.ON_SURFACE_VARIANT),
                subtitle=ft.Text(alt) if alt else None, dense=True,
                selected=bool(self.secili and self.secili["id"] == k["id"]),
                on_click=lambda _, kayit=k: self._sec(kayit)))
        self.liste.controls = satirlar or [ft.Text("Kayıt yok.", color=ft.Colors.ON_SURFACE_VARIANT)]
        if guncelle:
            self.guncelle()

    def _form_ciz(self):
        if not self.form_acik:
            self.form = None
            self.form_kutusu.controls = [ft.Container(
                ft.Text("Soldaki listeden bir kayıt seçin." if self.kayitlar or not self.yazabilir
                        else "Henüz kayıt yok. 'Yeni' ile ilk kaydı ekleyin.", color=ft.Colors.ON_SURFACE_VARIANT),
                padding=20)]
            return
        self.form = Form(self.app, self.alanlar, self.secili, self.yazabilir, self.fk)
        kaydet = ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, visible=self.yazabilir)
        kaydet.on_click = lambda _: self.app.page.run_task(self._kaydet, kaydet)
        sil = ft.OutlinedButton("Sil", icon=ft.Icons.DELETE, visible=self.yazabilir and self.secili is not None,
                                on_click=self._sil)
        geri = ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Listeye dön", visible=not self.app.genis,
                             on_click=self._kapat)
        ad = (self.secili or {}).get(T.TANIM_BASLIK_ALANI[self.tablo]) if self.secili else "Yeni kayıt"
        self.form_kutusu.controls = [
            ft.Row([geri, ft.Text(ad or "", size=18, weight=ft.FontWeight.BOLD, expand=True)]),
            self.serit, son_degisiklik(self.secili), self.form.kontrol,
            ft.Row([kaydet, sil], wrap=True)]

    def _sec(self, kayit: dict):
        self.secili, self.form_acik = kayit, True
        self._ciz()

    def _yeni(self, _=None):
        self.secili, self.form_acik = None, True
        self._ciz()

    def _kapat(self, _=None):
        self.form_acik = False
        self._ciz()

    async def _yenile(self, _=None):
        await self.app.guvenli(self.yukle)

    async def _kaydet(self, dugme):
        async def is_():
            veri = self.form.veri()
            try:
                if self.secili:
                    veri["surum"] = self.secili["surum"]
                    sonuc = await self.app.supa.guncelle(self.tablo, veri, id=self.secili["id"])
                else:
                    sonuc = await self.app.supa.ekle(self.tablo, veri)
            except SupaHata as e:
                if e.cakisma:
                    await self.yukle()
                raise
            self.secili = sonuc
            await self.yukle()
            self.app.bildir("Kaydedildi.")

        await self.app.guvenli(is_, dugme)

    def _sil(self, _=None):
        kayit = self.secili

        async def is_():
            await self.app.supa.sil(self.tablo, id=kayit["id"])
            self.secili, self.form_acik = None, False
            await self.yukle()
            self.app.bildir("Kayıt silindi.")

        self.app.onayla(f"'{kayit.get(T.TANIM_BASLIK_ALANI[self.tablo])}' kaydı silinsin mi? "
                        "Başka kayıtlarda kullanılıyorsa silinmez; pasif yapmanız istenir.", "Sil",
                        lambda: self.app.guvenli(is_))


# ---------------------------------------------------------------------- orders and approvals
class SiparisEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        self.kayitlar: list[dict] = []
        self.veri: dict = {"cariler": [], "bolumler": [], "urunler": []}
        self.secili: dict | None = None
        self.form_acik = False
        self.form: dict[str, ft.TextField | ft.Dropdown] = {}
        self.kalem_formlari: list[SiparisKalemKontrolleri] = []
        self.kalem_kutusu = ft.Column(spacing=8)
        self.kalem_toplami = ft.Text()
        self.serit = ft.Container(visible=False)
        self._ilk_degerler = None
        self.kontrol = ft.Container(expand=True)

    @property
    def yazabilir(self) -> bool:
        return self.app.yetki("siparis") == "y"

    async def yukle(self):
        self.veri = await self.app.supa.rpc("dose_siparis_veri") or self.veri
        self.kayitlar = await self.app.supa.rpc("dose_siparisler") or []
        if self.secili:
            self.secili = next((s for s in self.kayitlar if s["id"] == self.secili["id"]), None)
            if self.secili is None:
                self.form_acik = False
        self._ciz()

    async def uzaktan_degisti(self):
        if self._kirli():
            self.serit.content = uyari_seridi("Sunucuda değişiklik var. Kaydedilmemiş siparişiniz korundu; "
                                              "güncel kayıtları görmek için Yenile'yi kullanın.")
            self.serit.visible = True
            self.guncelle()
            return
        await self.yukle()

    def duzen(self):
        if self._kirli():
            self._yerlesim()
            self.guncelle()
        else:
            self._ciz()

    def _form_degerleri(self):
        return (tuple((ad, getattr(kontrol, "value")) for ad, kontrol in self.form.items()),
                tuple(tuple((ad, getattr(kontrol, "value")) for ad, kontrol in satir.items())
                      for satir in self.kalem_formlari))

    def _kirli(self):
        return (self.form_acik and self._duzenlenebilir() and self._ilk_degerler is not None
                and self._form_degerleri() != self._ilk_degerler)

    def kaydedilmemis(self) -> bool:
        return self._kirli()

    def _degisikligi_birak(self, devam):
        if not self._kirli():
            return False

        async def uygula():
            devam()

        self.app.onayla("Kaydedilmemiş sipariş değişiklikleri bırakılacak.", "Değişiklikleri bırak", uygula)
        return True

    def _yenile(self, _=None):
        if self._kirli():
            self.app.onayla("Kaydedilmemiş sipariş değişiklikleri bırakılacak.", "Yenile",
                            lambda: self.app.guvenli(self.yukle))
        else:
            self.app.page.run_task(self.app.guvenli, self.yukle)

    def _ciz(self):
        self.serit.visible = False
        secili_id = self.secili["id"] if self.secili else None
        satirlar = [ft.ListTile(
            title=ft.Text(f"{s.get('siparis_no')} · {s.get('konu') or ''}"),
            subtitle=ft.Text(f"{s.get('cari_unvan') or ''} · {s.get('bolum_ad') or ''} · "
                             f"{T.sayi_yaz(Decimal(str(self._kesin_deger(s, 'sozlesme_bedeli', 0))))} TL · "
                             f"{s.get('onay_durumu') or s.get('durum') or ''}"),
            selected=s.get("id") == secili_id,
            on_click=lambda _, kayit=s: self._sec(kayit)) for s in self.kayitlar]
        if not satirlar:
            satirlar = [ft.Text("Henüz sipariş yok.", color=ft.Colors.ON_SURFACE_VARIANT)]
        self.liste = ft.Column([
            ft.Row([ft.Text("Sipariş / iş emirleri", size=20, weight=ft.FontWeight.BOLD, expand=True),
                    ft.FilledButton("Yeni sipariş", icon=ft.Icons.ADD, visible=self.yazabilir,
                                    on_click=self._yeni),
                    ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile", on_click=self._yenile)],
                   wrap=True),
            *satirlar],
            expand=True, scroll=ft.ScrollMode.AUTO, spacing=4)
        self._form_ciz()
        self._yerlesim()
        self.guncelle()

    def _yerlesim(self):
        if self.app.genis:
            self.kontrol.content = ft.Row([
                ft.Container(self.liste, width=410),
                ft.VerticalDivider(width=1),
                ft.Container(self.form_kutusu, expand=True, padding=ft.Padding.only(left=12))],
                expand=True, vertical_alignment=ft.CrossAxisAlignment.START)
        else:
            self.kontrol.content = self.form_kutusu if self.form_acik else self.liste

    def _urun_adi(self, kimlik):
        return next((u.get("ad", "") for u in self.veri["urunler"] if str(u["id"]) == str(kimlik)), "")

    @staticmethod
    def _kesin_deger(kayit: dict, alan: str, varsayilan=None):
        deger = kayit.get(f"{alan}_kesin")
        return deger if deger is not None else kayit.get(alan, varsayilan)

    def _urun_secildi(self, indeks, kimlik):
        if not kimlik or indeks >= len(self.kalem_formlari):
            return
        urun = next((u for u in self.veri["urunler"] if str(u["id"]) == str(kimlik)), None)
        if not urun:
            return
        k = self.kalem_formlari[indeks]
        k["aciklama"].value = urun.get("ad", "")
        k["birim"].value = urun.get("birim") or "Adet"
        k["birim_fiyat"].value = T.siparis_sayisi_yaz(urun.get("satis_fiyati") or 0)
        self._toplam_guncelle()
        self.guncelle()

    def _satir_ekle(self, satir: dict | None = None):
        satir = satir or {}
        k: SiparisKalemKontrolleri = {
            "urun_id": secim_kutusu("Ürün / hizmet", [(str(u["id"]), u["ad"]) for u in self.veri["urunler"]],
                                    satir.get("urun_id")),
            "aciklama": ft.TextField(label="Açıklama", value=satir.get("aciklama") or "", expand=True),
            "miktar": ft.TextField(label="Miktar", value=T.siparis_sayisi_yaz(self._kesin_deger(satir, "miktar", 1)),
                                   keyboard_type=ft.KeyboardType.NUMBER, width=105, on_change=lambda _: self._toplam_guncelle()),
            "birim": ft.TextField(label="Birim", value=satir.get("birim") or "Adet", width=105),
            "birim_fiyat": ft.TextField(label="Birim fiyat (TL)", value=T.siparis_sayisi_yaz(self._kesin_deger(satir, "birim_fiyat", 0)),
                                        keyboard_type=ft.KeyboardType.NUMBER, width=145,
                                        on_change=lambda _: self._toplam_guncelle()),
            "iskonto": ft.TextField(label="İndirim (%)", value=T.siparis_yuzdesi_yaz(self._kesin_deger(satir, "iskonto_orani", 0)),
                                    keyboard_type=ft.KeyboardType.NUMBER, width=110,
                                    on_change=lambda _: self._toplam_guncelle()),
        }
        self.kalem_formlari.append(k)
        self._kalem_ciz()

    def _kalem_ciz(self):
        self.kalem_kutusu.controls = []
        for i, k in enumerate(self.kalem_formlari):
            k["urun_id"].on_select = lambda e, ix=i: self._urun_secildi(ix, e.control.value)
            k["urun_id"].disabled = not self._duzenlenebilir()
            for kontrol in (k["aciklama"], k["miktar"], k["birim"], k["birim_fiyat"], k["iskonto"]):
                kontrol.read_only = not self._duzenlenebilir()
            self.kalem_kutusu.controls.append(ft.Card(ft.Container(ft.Column([
                ft.Row([ft.Text(f"Kalem {i + 1}", weight=ft.FontWeight.BOLD, expand=True),
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Kalemi kaldır", visible=self._duzenlenebilir(),
                                      on_click=lambda _, ix=i: self._satir_sil(ix))]),
                k["urun_id"],
                ft.ResponsiveRow([
                    ft.Container(k["aciklama"], col={"xs": 12, "md": 6}),
                    ft.Container(k["miktar"], col={"xs": 6, "md": 2}),
                    ft.Container(k["birim"], col={"xs": 6, "md": 2}),
                    ft.Container(k["birim_fiyat"], col={"xs": 8, "md": 2}),
                    ft.Container(k["iskonto"], col={"xs": 4, "md": 2}),
                ], spacing=8, run_spacing=4)], spacing=8), padding=12)))
        self._toplam_guncelle()

    def _satir_sil(self, indeks):
        self.kalem_formlari.pop(indeks)
        self._kalem_ciz()
        self.guncelle()

    def _toplam_guncelle(self):
        try:
            tutarlar = []
            for k in self.kalem_formlari:
                miktar = T.ondalik_coz(k["miktar"].value or "0")
                fiyat = T.ondalik_coz(k["birim_fiyat"].value or "0")
                oran = T.ondalik_coz(k["iskonto"].value or "0")
                tutarlar.append(T.siparis_kalem_ondalik_tutari(miktar, fiyat, oran)[2])
            with localcontext() as baglam:
                baglam.prec = max(28, max((len(t.as_tuple().digits) for t in tutarlar), default=1)
                                  + len(str(len(tutarlar))) + 1)
                toplam = sum(tutarlar, Decimal("0"))
            self.kalem_toplami.value = f"İndirim sonrası KDV hariç toplam: {T.sayi_yaz(toplam)} TL"
            self.kalem_toplami.color = None
        except ValueError as e:
            self.kalem_toplami.value = str(e)
            self.kalem_toplami.color = ft.Colors.ERROR

    def _duzenlenebilir(self):
        if not self.yazabilir:
            return False
        return self.secili is None or self.secili.get("durum") in ("Taslak", "İade Edildi")

    def _esas_ozel_veya_tesis(self) -> bool:
        esas = (self.form.get("ucret_esasi").value if self.form else None) or ""
        return esas.startswith("Özel Sektör") or esas.startswith("Tesis")

    def _esas_gorunurluk(self):
        if not self.form or "pesinat" not in self.form:
            return
        self.form["pesinat"].visible = self._esas_ozel_veya_tesis() or bool(
            self.secili and Decimal(str(self.secili.get("pesinat") or 0)) > 0)

    def _esas_degisti(self, _=None):
        self._esas_gorunurluk()
        self.guncelle()

    def _yeni(self, _=None):
        def uygula():
            self.secili = None
            self.form_acik = True
            self._ciz()
        if not self._degisikligi_birak(uygula):
            uygula()

    def _sec(self, kayit):
        def uygula():
            self.secili = kayit
            self.form_acik = True
            self._ciz()
        if not self._degisikligi_birak(uygula):
            uygula()

    def _form_ciz(self):
        if not self.form_acik:
            self.kalem_formlari = []
            self._ilk_degerler = None
            self.form_kutusu = ft.Column([ft.Container(
                ft.Text("Listeden bir sipariş seçin veya yeni sipariş oluşturun.",
                        color=ft.Colors.ON_SURFACE_VARIANT), padding=20)], expand=True)
            return
        s = self.secili or {}
        self.form = {
            "tarih": ft.TextField(label="Sipariş tarihi", value=str(T.gosterim("tarih", s.get("tarih") or date.today().isoformat())),
                                  hint_text="GG.AA.YYYY", width=180),
            "cari_id": secim_kutusu("Müşteri", [(str(c["id"]), f"{c.get('unvan')} ({c.get('kod') or c.get('tur') or ''})")
                                                 for c in self.veri["cariler"]], s.get("cari_id"), bos=False),
            "bolum_id": secim_kutusu("Bölüm / atölye", [(str(b["id"]), b["ad"]) for b in self.veri["bolumler"]],
                                     s.get("bolum_id"), bos=False),
            "konu": ft.TextField(label="İşin konusu", value=s.get("konu") or "", expand=True),
            "ucret_esasi": secim_kutusu("Ücret esası", self.app.secenek.get("ucret_esasi", []),
                                        s.get("ucret_esasi"), bos=False, on_select=self._esas_degisti),
            "pesinat": ft.TextField(label="Peşinat (TL)", value=T.siparis_sayisi_yaz(self._kesin_deger(s, "pesinat", 0)),
                                    keyboard_type=ft.KeyboardType.NUMBER, width=160,
                                    helper="Özel sektör / tesis için asgari peşinat zorunlu"),
            "kdv_orani": ft.TextField(label="KDV oranı (%)", value=T.siparis_yuzdesi_yaz(self._kesin_deger(s, "kdv_orani", 0.20)),
                                      keyboard_type=ft.KeyboardType.NUMBER, width=160),
            "aciklama": ft.TextField(label="Açıklama", value=s.get("aciklama") or "", multiline=True, min_lines=2),
        }
        self._esas_gorunurluk()
        self.kalem_formlari = []
        for k in s.get("kalemler") or []:
            self._satir_ekle(k)
        if not self.kalem_formlari and self.secili is None:
            self._satir_ekle()
        read_only = not self._duzenlenebilir()
        for k in self.form.values():
            k.disabled = read_only
        if s.get("onay_durumu") == "Onay Bekliyor":
            durum_metni = f"Onay bekliyor · {s.get('bekleyen_rol') or 'aşama'}"
        else:
            durum_metni = s.get("onay_durumu") or s.get("durum") or "Yeni taslak"
        baslik = f"{s.get('siparis_no')} · {s.get('konu') or ''}" if s else "Yeni sipariş"
        gecmis = [ft.ListTile(
            leading=ft.Icon(ft.Icons.HISTORY),
            title=ft.Text(f"{g.get('asama_adi')}: {g.get('karar')}"),
            subtitle=ft.Text(f"{g.get('zaman') or ''} · {g.get('ad_soyad') or ''} ({g.get('rol') or ''})"
                             f"{' · ' + g['aciklama'] if g.get('aciklama') else ''}"))
            for g in (s.get("gecmis") or [])]
        actions = []
        if self._duzenlenebilir():
            actions.append(ft.FilledButton("Taslağı kaydet", icon=ft.Icons.SAVE,
                                           on_click=lambda e: self.app.page.run_task(self._kaydet)))
            if s:
                actions.append(ft.FilledButton("Onaya gönder", icon=ft.Icons.SEND,
                                               on_click=lambda e: self.app.page.run_task(self._gonder)))
        if s.get("onay_durumu") == "Onay Bekliyor":
            rol = self.app.ben.get("rol")
            if rol == s.get("bekleyen_rol") and (s.get("onay_asamasi") != 1
                                                 or self.app.ben.get("bolum_id") == s.get("bolum_id")):
                actions.extend([
                    ft.FilledButton("Uygun", icon=ft.Icons.CHECK,
                                    on_click=lambda e: self.app.page.run_task(self._karar, True, "")),
                    ft.OutlinedButton("İade et", icon=ft.Icons.REPLY,
                                      on_click=self._iade_dialog),
                ])
            if s.get("benim") or rol in ("Okul Müdürü", "Sistem Yöneticisi"):
                actions.append(ft.TextButton("Onaydan geri çek", on_click=self._geri_cek))
        self.form_kutusu = ft.Column([
            ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Listeye dön", visible=not self.app.genis,
                                  on_click=lambda _: self._listeye_don()),
                    ft.Text(baslik, size=19, weight=ft.FontWeight.BOLD, expand=True)]),
            self.serit,
            ft.Text(durum_metni, color=ft.Colors.PRIMARY, weight=ft.FontWeight.BOLD),
            ft.ResponsiveRow([
                ft.Container(self.form["tarih"], col={"xs": 12, "md": 3}),
                ft.Container(self.form["cari_id"], col={"xs": 12, "md": 5}),
                ft.Container(self.form["bolum_id"], col={"xs": 12, "md": 4}),
                ft.Container(self.form["konu"], col={"xs": 12, "md": 8}),
                ft.Container(self.form["ucret_esasi"], col={"xs": 12, "md": 6}),
                ft.Container(self.form["pesinat"], col={"xs": 12, "md": 3}),
                ft.Container(self.form["kdv_orani"], col={"xs": 12, "md": 3}),
                ft.Container(self.form["aciklama"], col={"xs": 12}),
            ], spacing=10, run_spacing=4),
            ft.Row([ft.Text("İş kalemleri", size=17, weight=ft.FontWeight.BOLD, expand=True),
                    ft.OutlinedButton("Kalem ekle", icon=ft.Icons.ADD, visible=self._duzenlenebilir(),
                                      on_click=lambda _: self._satir_ekle())]),
            self.kalem_kutusu, self.kalem_toplami, ft.Row(actions, wrap=True),
            ft.Divider(visible=bool(gecmis)),
            ft.Text("Onay geçmişi", weight=ft.FontWeight.BOLD, visible=bool(gecmis)),
            *gecmis,
        ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=10)
        self._ilk_degerler = self._form_degerleri()

    def _listeye_don(self):
        def uygula():
            self.form_acik = False
            self._ciz()
        if not self._degisikligi_birak(uygula):
            uygula()

    def _form_verisi(self):
        if not self.form["cari_id"].value:
            raise ValueError("Aktif müşteri seçiniz.")
        if not self.form["bolum_id"].value:
            raise ValueError("Aktif bölüm / atölye seçiniz.")
        if not (self.form["konu"].value or "").strip():
            raise ValueError("İşin konusu zorunludur.")
        if not self.form["ucret_esasi"].value:
            raise ValueError("Ücret esası seçiniz.")
        s = {
            "tarih": T.tarih_coz(self.form["tarih"].value or ""),
            "cari_id": int(self.form["cari_id"].value),
            "bolum_id": int(self.form["bolum_id"].value),
            "konu": (self.form["konu"].value or "").strip(),
            "ucret_esasi": self.form["ucret_esasi"].value,
            "pesinat": str(T.ondalik_coz(self.form["pesinat"].value or "0")),
            "kdv_orani": str(T.siparis_yuzdesi_orana(T.ondalik_coz(self.form["kdv_orani"].value or "0"))),
            "aciklama": (self.form["aciklama"].value or "").strip(),
        }
        kalemler = []
        for k in self.kalem_formlari:
            miktar = T.ondalik_coz(k["miktar"].value or "0")
            fiyat = T.ondalik_coz(k["birim_fiyat"].value or "0")
            oran = T.ondalik_coz(k["iskonto"].value or "0")
            _, _, net = T.siparis_kalem_ondalik_tutari(miktar, fiyat, oran)
            kalemler.append({
                "urun_id": int(k["urun_id"].value) if k["urun_id"].value else None,
                "aciklama": (k["aciklama"].value or "").strip(),
                "miktar": str(miktar),
                "birim": (k["birim"].value or "").strip(),
                "birim_fiyat": str(fiyat),
                "iskonto_orani": str(T.siparis_yuzdesi_orana(oran)),
                "hesaplanan_net": str(net),
            })
        if not kalemler:
            raise ValueError("En az bir sipariş kalemi ekleyiniz.")
        return s, kalemler

    async def _kaydet(self, _=None):
        async def is_():
            veri, kalemler = self._form_verisi()
            sonuc = await self.app.supa.rpc(
                "dose_siparis_kaydet", p_siparis_id=self.secili.get("id") if self.secili else None,
                p_sur=self.secili.get("surum") if self.secili else None,
                p_siparis=veri, p_kalemler=kalemler)
            self.secili = {"id": sonuc["id"]}
            await self.yukle()
            self.form_acik = True
            self.app.bildir(f"{sonuc['siparis_no']} taslağı kaydedildi.")
            self._ciz()
        await self.app.guvenli(is_)

    async def _gonder(self):
        async def is_():
            if self.secili is None:
                raise ValueError("Önce bir sipariş seçin.")
            if self._kirli():
                raise ValueError("Kaydedilmemiş değişiklikler var. Onaya göndermeden önce taslağı kaydedin.")
            sonuc = await self.app.supa.rpc("dose_siparis_gonder", p_siparis_id=self.secili["id"],
                                            p_aciklama="", p_sur=self.secili["surum"])
            await self.yukle()
            self.app.bildir(f"Sipariş onaya gönderildi. Bekleyen aşama: {(self.secili or {}).get('bekleyen_rol') or sonuc.get('durum')}.")
            self._ciz()
        await self.app.guvenli(is_)

    async def _karar(self, onayla: bool, aciklama: str, siparis: dict | None = None):
        siparis = siparis or self.secili
        if siparis is None:
            self.app.bildir("Önce bir sipariş seçin.", hata=True)
            return

        async def is_():
            await self.app.supa.rpc("dose_siparis_karar", p_siparis_id=siparis["id"],
                                    p_onayla=onayla, p_aciklama=aciklama, p_sur=siparis["surum"])
            await self.yukle()
            self.app.bildir("Sipariş onaylandı." if onayla else "Sipariş iade edildi.")
            self._ciz()
        await self.app.guvenli(is_)

    def _iade_dialog(self, _=None):
        if self.secili is None:
            self.app.bildir("Önce bir sipariş seçin.", hata=True)
            return
        gerekce = ft.TextField(label="İade gerekçesi", multiline=True, min_lines=2)
        dugme = ft.FilledButton("İade et", icon=ft.Icons.REPLY)
        siparis = dict(self.secili)

        async def iade(_):
            if not (gerekce.value or "").strip():
                self.app.bildir("İade gerekçesini yazınız.", hata=True)
                return
            self.app.page.pop_dialog()
            await self._karar(False, gerekce.value.strip(), siparis)

        dugme.on_click = iade
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text("Siparişi iade et"),
            content=ft.Column([ft.Text("Düzeltme için gerekçeyi yazın."), gerekce], tight=True),
            actions=[ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog()), dugme]))

    def _geri_cek(self, _=None):
        if self.secili is None:
            self.app.bildir("Önce bir sipariş seçin.", hata=True)
            return
        siparis = dict(self.secili)
        self.app.onayla("Sipariş onay sürecinden çıkarılıp yeniden taslağa alınsın mı?", "Geri çek",
                        lambda: self._geri_cek_uygula(siparis))

    async def _geri_cek_uygula(self, siparis: dict):
        async def is_():
            await self.app.supa.rpc("dose_siparis_geri_cek", p_siparis_id=siparis["id"],
                                    p_aciklama="", p_sur=siparis["surum"])
            await self.yukle()
            self.app.bildir("Sipariş taslağa geri çekildi.")
            self._ciz()
        await self.app.guvenli(is_)


# ---------------------------------------------------------------------- users
class KullaniciEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        self.veri: dict = {"uyeler": [], "davetler": []}
        self.bolumler: list[tuple[str, str]] = []
        self.personeller: list[tuple[str, str]] = []

    async def yukle(self):
        self.veri = await self.app.supa.rpc("dose_kullanicilar") or {}
        try:
            self.bolumler = [(str(b["id"]), b["ad"]) for b in
                             await self.app.supa.sec("bolum", secim="id,ad", sira="ad", aktif=1)]
            self.personeller = [(str(p["id"]), p["ad_soyad"]) for p in
                                await self.app.supa.sec("personel", secim="id,ad_soyad", sira="ad_soyad", aktif=1)]
        except SupaHata:
            pass
        self._ciz()

    def _bolum_adi(self, kimlik) -> str:
        return next((ad for k, ad in self.bolumler if k == str(kimlik)), "")

    def _ciz(self):
        uyeler = []
        for u in self.veri.get("uyeler") or []:
            alt = " · ".join(x for x in (u.get("rol"), u.get("eposta"), self._bolum_adi(u.get("bolum_id")),
                                         None if u.get("aktif") else "Pasif") if x)
            uyeler.append(ft.ListTile(
                leading=ft.Icon(ft.Icons.PERSON if u.get("aktif") else ft.Icons.PERSON_OFF),
                title=ft.Text(f"{u.get('ad_soyad') or u.get('eposta')}{' (siz)' if u.get('ben') else ''}"),
                subtitle=ft.Text(alt), trailing=ft.Icon(ft.Icons.EDIT),
                on_click=lambda _, uye=u: self._duzenle(uye)))
        davetler = []
        for d in self.veri.get("davetler") or []:
            davetler.append(ft.ListTile(
                leading=ft.Icon(ft.Icons.MAIL), title=ft.Text(d.get("eposta")),
                subtitle=ft.Text(f"{d.get('ad_soyad')} · {d.get('rol')} · son gün {str(d.get('bitis') or '')[:10]}"),
                trailing=ft.IconButton(ft.Icons.DELETE, tooltip="Daveti iptal et",
                                       on_click=lambda _, dv=d: self._davet_sil(dv))))
        self.kontrol.controls = [
            ft.Row([ft.Text("Kullanıcılar", size=20, weight=ft.FontWeight.BOLD, expand=True),
                    ft.FilledButton("Davet et", icon=ft.Icons.PERSON_ADD, on_click=lambda _: self._davet()),
                    ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile",
                                  on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))],
                   wrap=True),
            ft.Text("Davet ettiğiniz kişi aynı e-postayla hesap açıp doğruladığında okula kendiliğinden bağlanır. "
                    "Alan şefi ve öğretmen yalnız atandığı bölümü görür.", size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text("Üyeler", weight=ft.FontWeight.BOLD), *uyeler,
            ft.Text("Bekleyen davetler", weight=ft.FontWeight.BOLD),
            *(davetler or [ft.Text("Bekleyen davet yok.", color=ft.Colors.ON_SURFACE_VARIANT)])]
        self.guncelle()

    def _kisi_formu(self, kayit: dict, eposta_duzenlenir: bool):
        k = {
            "eposta": ft.TextField(label="E-posta", value=kayit.get("eposta") or "", read_only=not eposta_duzenlenir,
                                   keyboard_type=ft.KeyboardType.EMAIL),
            "ad_soyad": ft.TextField(label="Adı soyadı", value=kayit.get("ad_soyad") or ""),
            "rol": secim_kutusu("Rol", [(r, r) for r in T.ROLLER], kayit.get("rol"), bos=False),
            "bolum_id": secim_kutusu("Bölüm / atölye (şef ve öğretmen için)", self.bolumler, kayit.get("bolum_id")),
            "personel_id": secim_kutusu("Personel kartı", self.personeller, kayit.get("personel_id")),
        }
        return k

    @staticmethod
    def _sayi(deger):
        return int(deger) if deger else None

    def _dialog(self, baslik: str, kontroller: list, etiket: str, is_):
        dugme = ft.FilledButton(etiket)

        async def tik(_):
            if await self.app.guvenli(is_, dugme):
                self.app.page.pop_dialog()
                self.app.bildir(f"{etiket} işlemi tamamlandı.")
                await self.app.guvenli(self.yukle)

        dugme.on_click = tik
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text(baslik), scrollable=True,
            content=ft.Column(kontroller, tight=True, spacing=12, width=420),
            actions=[ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog()), dugme]))

    def _davet(self):
        k = self._kisi_formu({"rol": "Öğretmen"}, True)

        async def is_():
            await self.app.supa.rpc("dose_kullanici_davet", p_eposta=k["eposta"].value.strip(),
                                    p_ad_soyad=k["ad_soyad"].value.strip(), p_rol=k["rol"].value,
                                    p_bolum_id=self._sayi(k["bolum_id"].value),
                                    p_personel_id=self._sayi(k["personel_id"].value))

        self._dialog("Kullanıcı davet et", list(k.values()), "Davet et", is_)

    def _duzenle(self, uye: dict):
        k = self._kisi_formu(uye, False)
        aktif = ft.Checkbox(label="Aktif", value=bool(uye.get("aktif")))

        async def is_():
            await self.app.supa.rpc("dose_kullanici_guncelle", p_kullanici=uye["id"],
                                    p_ad_soyad=k["ad_soyad"].value.strip(), p_rol=k["rol"].value,
                                    p_bolum_id=self._sayi(k["bolum_id"].value),
                                    p_personel_id=self._sayi(k["personel_id"].value), p_aktif=bool(aktif.value))
            if uye.get("ben"):
                await self.app.ben_yukle()

        self._dialog("Kullanıcıyı düzenle", list(k.values()) + [aktif], "Kaydet", is_)

    def _davet_sil(self, davet: dict):
        async def is_():
            await self.app.supa.rpc("dose_davet_sil", p_eposta=davet["eposta"])
            await self.yukle()
            self.app.bildir("Davet iptal edildi.")

        self.app.onayla(f"{davet['eposta']} adresine yapılan davet iptal edilsin mi?", "İptal et",
                        lambda: self.app.guvenli(is_))


# ---------------------------------------------------------------------- audit log
class IslemKaydiEkrani(Ekran):
    async def yukle(self):
        satirlar = await self.app.supa.sec("islem_log", secim="id,zaman,ad_soyad,rol,islem,tablo,kayit_id,detay",
                                           sira="id.desc", limit=200)
        liste = [ft.ListTile(
            title=ft.Text(f"{s.get('islem') or ''} · {s.get('tablo') or ''}"
                          f"{' #' + str(s['kayit_id']) if s.get('kayit_id') else ''}"),
            subtitle=ft.Text(f"{s.get('zaman') or ''} — {s.get('ad_soyad') or ''}"
                             f"{' (' + s['rol'] + ')' if s.get('rol') else ''}"
                             f"{chr(10) + s['detay'] if s.get('detay') else ''}"),
            dense=True) for s in satirlar]
        self.kontrol.controls = [
            ft.Row([ft.Text("İşlem kaydı", size=20, weight=ft.FontWeight.BOLD, expand=True),
                    ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile",
                                  on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))]),
            ft.Text("Kim, hangi rolde, neyi, ne zaman yaptı. Bu kayıt değiştirilemez ve silinemez. Son 200 işlem.",
                    size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            *(liste or [ft.Text("Henüz işlem yok.")])]
        self.guncelle()
