"""Screens of the core phase: home, institution, definitions, users, audit log."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path
from typing import TypedDict

import flet as ft

from dose import excel as X
from dose import pdf_ice

try:
    from . import takvim, tema
    from . import tanimlar as T
    from .supa import SupaHata
    from .tema import (ANA_RENK, MARKA_VURGU, METIN_IKINCIL, bilgi_karti, dialog_genislik,
                       kahraman_seridi, kpi_karti, liste_satiri, oran_cubugu, sayfa_baslik_satiri,
                       yuzey_kart)
except ImportError:
    import takvim
    import tema
    import tanimlar as T
    from supa import SupaHata
    from tema import (ANA_RENK, MARKA_VURGU, METIN_IKINCIL, bilgi_karti, dialog_genislik,
                      kahraman_seridi, kpi_karti, liste_satiri, oran_cubugu, sayfa_baslik_satiri,
                      yuzey_kart)

KLAVYE = {"para": ft.KeyboardType.NUMBER, "ondalik": ft.KeyboardType.NUMBER, "oran": ft.KeyboardType.NUMBER,
          "tarih": ft.KeyboardType.DATETIME}
ROL_GOREVI = {
    "Okul Müdürü": "Harcama yetkilisi ve okul yöneticisi: tüm işlemlere yazma yetkiniz vardır; "
                   "kullanıcılara rol ve sayfa yetkisi verirsiniz.",
    "Teknik Müdür Yardımcısı": "Gerçekleştirme görevlisi: işi ve puantajı kontrol edip imzalarsınız; taslak da hazırlayabilirsiniz.",
    "Sayman": "Fatura, kasa, hazine payı, ÜTP ödemesi ve merkez parametre doğrulamasını yaparsınız.",
    "Alan Şefi": "Atölyenizin siparişini yürütür, puantajı imzalar ve onayın ilk aşamasını verirsiniz.",
    "Öğretmen": "Kendi atölyenizde parça başı ve fazla çalışma puantajını yazarsınız; sipariş taslağı açabilirsiniz.",
    "Memur / Veri Girişi": "Cari, stok kartı, öğrenci gibi tanımları ve resmi yazı taslaklarını girersiniz.",
    "İzleyici / Denetçi": "Kayıtları ve işlem izini değiştirmeden incelersiniz; iç denetim formu doldurabilirsiniz.",
    "Sistem Yöneticisi": "Okulun tüm ekranlarında yazma yetkisi; kullanıcıları davet eder, rol ve sayfa yetkisi atarsınız.",
}

YETKI_SECENEKLERI = [("varsayilan", "Rol varsayılanı"), ("y", "Yazma"), ("g", "Okuma"), ("-", "Kapalı")]
DURUM_RENKLERI = {
    "Taslak": "#8ec5d6", "Onay Bekliyor": "#d48f2a", "Sözleşme İmzalandı": "#2f9e6b",
    "İade Edildi": "#b3261e", "İptal": "#5c6b7a",
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


def uyari_seridi(metin: str, on_kapat=None, kapat_ipucu: str = "Bir daha gösterme") -> ft.Control:
    satir = [ft.Icon(ft.Icons.WARNING_AMBER, color=ft.Colors.ON_ERROR_CONTAINER),
             ft.Text(metin, color=ft.Colors.ON_ERROR_CONTAINER, expand=True)]
    if on_kapat is not None:
        satir.append(ft.IconButton(
            ft.Icons.CLOSE, icon_color=ft.Colors.ON_ERROR_CONTAINER, tooltip=kapat_ipucu,
            on_click=on_kapat))
    return ft.Container(ft.Row(satir), bgcolor=ft.Colors.ERROR_CONTAINER, padding=10, border_radius=8)


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
        try:
            self.kontrol.update()
        except Exception:
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
    def __init__(self, app):
        super().__init__(app)
        self.ozet: dict = {}
        self.gorevler: list = []
        self._duyuru_gizli = False

    @staticmethod
    def _para(deger) -> str:
        if deger is None or deger == "":
            return "—"
        try:
            from decimal import Decimal
            return f"{T.sayi_yaz(Decimal(str(deger)), 2)} ₺"
        except Exception:
            return str(deger)

    async def yukle(self):
        ben = self.app.ben
        okul = ben.get("okul") or {}
        if ben.get("merkez_mevzuat") and not okul:
            self.kontrol.controls = [
                kahraman_seridi("Merkez parametreleri", "Yayınları hazırlayıp kaynaklarıyla yayımlayın."),
                bilgi_karti("Merkez", "Her okulun saymanı yayını ayrıca doğrular.", ft.Icons.HUB_OUTLINED)]
            self.guncelle()
            return
        try:
            self.ozet = await self.app.supa.rpc("dose_ana_ozet") or {}
        except SupaHata:
            self.ozet = {}
        try:
            gorev = await self.app.supa.rpc("dose_gorevlerim")
        except SupaHata:
            gorev = {"gorevler": []}
        try:
            from . import medya
        except ImportError:
            import medya
        uyg = (self.app.ben or {}).get("uygulama") or {}
        self._duyuru_gizli = await medya.duyuru_okundu_mu(self.app.page, uyg)
        ham = gorev.get("gorevler") or []
        if self._duyuru_gizli:
            ham = [g for g in ham if (g.get("tur") or "") != "guncelleme"]
        self.gorevler = ham
        self._ciz()

    def duzen(self):
        if self.app.ben and (self.app.ben.get("okul") or self.app.ben.get("merkez_mevzuat")):
            self._ciz()

    def _duyuru_kapat(self, _=None):
        async def is_():
            try:
                from . import medya
            except ImportError:
                import medya
            uyg = (self.app.ben or {}).get("uygulama") or {}
            await medya.duyuru_okundu_isaretle(self.app.page, uyg)
            self._duyuru_gizli = True
            self.gorevler = [g for g in self.gorevler if (g.get("tur") or "") != "guncelleme"]
            self._ciz()
            self.app.bildir("Güncelleme uyarısı kapatıldı; bu sürüm için bir daha gösterilmez.")

        self.app.page.run_task(self.app.guvenli, is_)

    def _ciz(self):
        ben = self.app.ben or {}
        okul = ben.get("okul") or {}
        ozet = self.ozet or {}
        yil = ozet.get("yil") or takvim.bugun_istanbul().year
        ad = (ben.get("ad_soyad") or "").split()[0] if ben.get("ad_soyad") else ""
        kompakt = not self.app.genis
        c: list[ft.Control] = [
            kahraman_seridi(
                f"Merhaba{(' ' + ad) if ad else ''}",
                f"{okul.get('ad') or 'DÖSE'} · {ben.get('rol') or ''} · {yil}",
                kompakt=kompakt),
        ]
        if okul.get("salt_okunur"):
            c.append(uyari_seridi("Lisans süresi doldu. Kayıtları görebilirsiniz ama değiştiremezsiniz. "
                                  "Lisansı yenilemek için satıcınıza başvurun."))
        uyg = ben.get("uygulama") or {}
        if (not self._duyuru_gizli) and uyg.get("aktif") and (uyg.get("duyuru") or "").strip():
            c.append(uyari_seridi(
                f"Güncelleme {uyg.get('surum') or ''}: {(uyg.get('duyuru') or '').strip()}",
                on_kapat=self._duyuru_kapat))

        kpis: list[ft.Control] = [
            kpi_karti("Bekleyen görev", str(len(self.gorevler)), ft.Icons.TASK_ALT, MARKA_VURGU)]
        if ozet.get("siparis_gorunur"):
            kpis.append(kpi_karti(f"{yil} sipariş", str(ozet.get("siparis") or 0),
                                  ft.Icons.SHOPPING_CART, ANA_RENK))
        if ozet.get("finans_gorunur"):
            kpis.extend([
                kpi_karti("Satış (net)", self._para(ozet.get("fatura_satis")),
                          ft.Icons.TRENDING_UP, "#2f9e6b"),
                kpi_karti("Alış (net)", self._para(ozet.get("fatura_alis")),
                          ft.Icons.TRENDING_DOWN, "#b3261e"),
                kpi_karti("Kasa", self._para(ozet.get("kasa_bakiye")),
                          ft.Icons.ACCOUNT_BALANCE_WALLET, "#2f6aa3"),
                kpi_karti("Banka", self._para(ozet.get("banka_bakiye")),
                          ft.Icons.ACCOUNT_BALANCE, "#1f4e79"),
            ])
            if ozet.get("hp_hasilat") is not None:
                kpis.append(kpi_karti("HP hasılat (ay)", self._para(ozet.get("hp_hasilat")),
                                      ft.Icons.EVENT_NOTE, MARKA_VURGU))
        c.append(ft.ResponsiveRow(kpis, spacing=12, run_spacing=12))

        grafik_kolonlari: list[ft.Control] = []
        durum = ozet.get("siparis_durum") or {}
        if durum:
            maks = max(int(v) for v in durum.values()) or 1
            cubuklar = [
                oran_cubugu(str(ad_), float(adet), float(maks),
                            DURUM_RENKLERI.get(str(ad_), ANA_RENK), sag_metin=str(adet))
                for ad_, adet in sorted(durum.items(), key=lambda x: -int(x[1]))]
            grafik_kolonlari.append(yuzey_kart(
                ft.Text(f"{yil} sipariş durumu", weight=ft.FontWeight.BOLD),
                *cubuklar, padding=18, genislik_kolon={"xs": 12, "md": 6}))
        if ozet.get("finans_gorunur"):
            try:
                from decimal import Decimal
                satis = float(Decimal(str(ozet.get("fatura_satis") or 0)))
                alis = float(Decimal(str(ozet.get("fatura_alis") or 0)))
            except Exception:
                satis = alis = 0.0
            maks_f = max(satis, alis, 1.0)
            grafik_kolonlari.append(yuzey_kart(
                ft.Text(f"{yil} fatura özeti", weight=ft.FontWeight.BOLD),
                oran_cubugu("Satış", satis, maks_f, "#2f9e6b", sag_metin=self._para(satis)),
                oran_cubugu("Alış", alis, maks_f, "#b3261e", sag_metin=self._para(alis)),
                padding=18, genislik_kolon={"xs": 12, "md": 6}))
        if grafik_kolonlari:
            c.append(ft.ResponsiveRow(grafik_kolonlari, spacing=12, run_spacing=12))

        c.append(bilgi_karti("Yasal göreviniz", ROL_GOREVI.get(ben.get("rol"), ""), ft.Icons.GAVEL))

        if self.gorevler:
            satirlar = [
                liste_satiri(g.get("baslik") or g.get("ozet") or "Görev", g.get("ozet") or "",
                             on_click=lambda _, s=g.get("sayfa"): self.app.page.run_task(self.app.sayfa_ac, s) if s else None,
                             trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, color=ANA_RENK))
                for g in self.gorevler[:12]]
            c.append(yuzey_kart(ft.Text("Bugün ne yapmalıyım?", weight=ft.FontWeight.BOLD),
                                *satirlar, padding=16))
        else:
            c.append(ft.Text("Şu an size düşen bekleyen onay yok.", size=13, color=METIN_IKINCIL))

        if ben.get("rol") in SURE_GOREN:
            sureler = takvim.yaklasan_sureler(takvim.bugun_istanbul())
            satirlar = []
            for s in sureler:
                acil = s["kalan"] <= 3
                satirlar.append(liste_satiri(
                    takvim.sure_cumlesi(s),
                    f"Son gün {s['son_gun'].strftime('%d.%m.%Y')}. {s['gecikme']}",
                    trailing=ft.Icon(ft.Icons.EVENT, color="#b3261e" if acil else ANA_RENK)))
            c.append(yuzey_kart(ft.Text("Yaklaşan yasal süreler", weight=ft.FontWeight.BOLD),
                                *satirlar, padding=16))

        lisans = okul.get("lisans_bitis")
        c.append(ft.Text(
            f"Kurum kodu {okul.get('kurum_kodu', '')} · Lisans "
            f"{'bitişi ' + T.gosterim('tarih', lisans) if lisans else 'süresiz'}",
            size=12, color=METIN_IKINCIL))
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
            sayfa_baslik_satiri("Kurum bilgileri",
                                [ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile", on_click=yenile)],
                                ft.Icons.APARTMENT),
            self.serit, son_degisiklik(self.kayit),
            yuzey_kart(self.form.kontrol, ft.Row([kaydet]), padding=16)]
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
                                  border_radius=12, on_change=lambda _: self._liste_ciz())
        self.liste = ft.ListView(expand=True, spacing=0)
        self.serit = ft.Container(visible=False)
        self.form_kutusu = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
        self.kontrol = ft.Container(expand=True)
        self._picker: ft.FilePicker | None = None
        self._ice_kayitlar: list[dict] = []
        # FilePicker service is attached lazily in _picker_hazirla.

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

    def _aksiyonlar(self) -> list[ft.Control]:
        aksiyonlar: list[ft.Control] = []
        if self.yazabilir and self.tablo in X.TABLO_ICE_AKTARMA:
            if self.app.genis:
                aksiyonlar += [
                    ft.OutlinedButton("Şablon", icon=ft.Icons.TABLE_VIEW, on_click=self._sablon_indir),
                    ft.OutlinedButton("Dosya / resim", icon=ft.Icons.UPLOAD_FILE, on_click=self._ice_aktar_ac),
                    ft.OutlinedButton("Metin / ses", icon=ft.Icons.MIC, on_click=self._ice_metin_ac),
                ]
            else:
                aksiyonlar.append(ft.PopupMenuButton(
                    icon=ft.Icons.UPLOAD_FILE, tooltip="İçe aktar",
                    items=[
                        ft.PopupMenuItem(content=ft.Text("Şablon indir"), icon=ft.Icons.TABLE_VIEW,
                                         on_click=self._sablon_indir),
                        ft.PopupMenuItem(content=ft.Text("Dosya / resim yükle"), icon=ft.Icons.UPLOAD_FILE,
                                         on_click=self._ice_aktar_ac),
                        ft.PopupMenuItem(content=ft.Text("Metin / sesle yaz"), icon=ft.Icons.MIC,
                                         on_click=self._ice_metin_ac),
                    ]))
        if self.yazabilir:
            aksiyonlar.append(ft.FilledButton("Yeni", icon=ft.Icons.ADD, on_click=self._yeni))
        aksiyonlar.append(ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile", on_click=self._yenile))
        return aksiyonlar

    def _ciz(self):
        self.serit.visible = False
        self._liste_ciz(guncelle=False)
        self._form_ciz()
        self._yerlesim()
        self.guncelle()

    def _yerlesim(self):
        kompakt = not self.app.genis
        ust = sayfa_baslik_satiri(self.baslik, self._aksiyonlar(), kompakt=kompakt)
        liste_kolonu = ft.Column([ust, self.arama, self.liste], expand=True, spacing=8 if kompakt else 10)
        if self.app.genis:
            self.kontrol.content = ft.Row([
                ft.Container(liste_kolonu, width=400),
                ft.VerticalDivider(width=1, color=tema.KENAR),
                ft.Container(self.form_kutusu, expand=True, padding=ft.Padding.only(left=12))],
                expand=True, vertical_alignment=ft.CrossAxisAlignment.START)
        else:
            self.kontrol.content = self.form_kutusu if self.form_acik else liste_kolonu

    def _liste_ciz(self, guncelle: bool = True):
        baslik_alani = T.TANIM_BASLIK_ALANI[self.tablo]
        a1, a2 = T.TANIM_ALT_ALANLAR[self.tablo]
        kompakt = not self.app.genis
        satirlar = []
        for k in self.kayitlar:
            if not T.eslesir(k, self.arama.value or "", self.tablo):
                continue
            alt = " · ".join(str(k[a]) for a in (a1, a2) if k.get(a))
            if not k.get("aktif", 1):
                alt = ("Pasif · " + alt) if alt else "Pasif"
            secili = bool(self.secili and self.secili["id"] == k["id"])
            satirlar.append(liste_satiri(
                k.get(baslik_alani) or "(adsız)", alt, secili=secili, kompakt=kompakt,
                on_click=lambda _, kayit=k: self._sec(kayit)))
        self.liste.controls = satirlar or [ft.Text("Kayıt yok.", color=METIN_IKINCIL)]
        if guncelle:
            try:
                self.liste.update()
            except Exception:
                self.guncelle()

    def _form_ciz(self):
        if not self.form_acik:
            self.form = None
            self.form_kutusu.controls = [yuzey_kart(ft.Text(
                "Soldaki listeden bir kayıt seçin." if self.kayitlar or not self.yazabilir
                else "Henüz kayıt yok. 'Yeni' ile ilk kaydı ekleyin.", color=METIN_IKINCIL), padding=24)]
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
            ft.Row([geri, ft.Text(ad or "", size=17 if not self.app.genis else 18,
                                  weight=ft.FontWeight.BOLD, color=tema.METIN, expand=True,
                                  max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)]),
            self.serit, son_degisiklik(self.secili),
            yuzey_kart(self.form.kontrol, ft.Row([kaydet, sil], wrap=True),
                       padding=12 if not self.app.genis else 16)]

    def _picker_hazirla(self):
        if self._picker is None:
            self._picker = ft.FilePicker()
            self.app.page.services.append(self._picker)
            self.app.page.update()

    def _sablon_indir(self, _=None):
        async def is_():
            try:
                from .belgeler import belge_klasoru
            except ImportError:
                from belgeler import belge_klasoru
            yol = belge_klasoru() / f"DOSE_{self.tablo}_sablon.xlsx"
            X.sablon_yaz(self.tablo, yol)
            self.app.bildir(f"Şablon kaydedildi: {yol}")

        self.app.page.run_task(self.app.guvenli, is_)

    def _ice_aktar_ac(self, _=None):
        self.app.page.run_task(self._ice_aktar_sec)

    def _ice_metin_ac(self, _=None):
        try:
            from . import medya
        except ImportError:
            import medya

        async def tamam(metin: str):
            async def is_():
                from dose import gorsel_ice
                kayitlar = gorsel_ice.tanim_oku_metin(metin, self.tablo)
                self._ice_kayitlar = kayitlar
                self._ice_onizle_dialog(kayitlar)

            await self.app.guvenli(is_)

        medya.ses_veya_metin_dialog(
            self.app,
            baslik="Tanım satırlarını yazın / dikte edin",
            ipucu="İlk satır başlıklar (Şablon ile aynı). Sonra veri satırları. Win+H veya Mikrofon.",
            on_tamam=tamam)

    async def _ice_aktar_sec(self):
        self._picker_hazirla()
        dosyalar = await self._picker.pick_files(
            dialog_title="Tanım dosyası seçin (xlsx, PDF veya belge resmi)",
            allowed_extensions=["xlsx", "xls", "pdf", "png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp"],
            with_data=True)
        if not dosyalar:
            return
        dosya = dosyalar[0]
        await self._ice_aktar_isle(yol=dosya.path, veri=dosya.bytes, ad=dosya.name or "")

    async def _ice_aktar_isle(self, yol: str | None = None, veri: bytes | None = None, ad: str = ""):
        async def is_():
            from dose import gorsel_ice
            ad_kucuk = (ad or (Path(yol).name if yol else "")).lower()
            if ad_kucuk.endswith(".xls") and not ad_kucuk.endswith(".xlsx"):
                raise ValueError(
                    "Eski .xls desteklenmez. Excel'de «Farklı Kaydet → *.xlsx» yapın veya Şablon indirin.")
            if not yol and not veri:
                raise ValueError("Dosya okunamadı. Masaüstünde yeniden deneyin veya .xlsx şablon kullanın.")
            if gorsel_ice.gorsel_mi(ad=ad_kucuk, yol=Path(yol) if yol else None):
                kayitlar = gorsel_ice.tanim_oku_gorsel(
                    yol=Path(yol) if yol else None, tablo=self.tablo, veri=veri, ad=ad)
            elif ad_kucuk.endswith(".pdf") or (yol and Path(yol).suffix.lower() == ".pdf"):
                try:
                    kayitlar = pdf_ice.tanim_oku_pdf(
                        yol=Path(yol) if yol else None, tablo=self.tablo, veri=veri)
                except ValueError as e:
                    # Tarama PDF: kullanıcıya metin/ses veya resim yolu öner
                    raise ValueError(
                        f"{e} Tarama ise sayfayı PNG/JPG olarak kaydedip yükleyin "
                        "veya «Metin / sesle yaz» kullanın.") from e
            else:
                kayitlar = X.tanim_oku(
                    yol=Path(yol) if yol else None, tablo=self.tablo, veri=veri, ad=ad or None)
            self._ice_kayitlar = kayitlar
            self._ice_onizle_dialog(kayitlar)

        await self.app.guvenli(is_)

    def _ice_onizle_dialog(self, kayitlar: list[dict]):
        ornek = kayitlar[:8]
        satirlar = [ft.Text(f"{i + 1}. " + " · ".join(f"{k}={v}" for k, v in r.items() if v not in (None, "")),
                            size=12) for i, r in enumerate(ornek)]
        if len(kayitlar) > 8:
            satirlar.append(ft.Text(f"… ve {len(kayitlar) - 8} satır daha", size=12, color=METIN_IKINCIL))
        satirlar.insert(0, ft.Text(
            "Önizlemeyi kontrol edin. Hatalı satırlar aktarım sonunda ayrı listelenir.",
            size=12, color=METIN_IKINCIL))

        async def kaydet(_):
            self.app.page.pop_dialog()
            await self._ice_toplu_kaydet()

        genislik = dialog_genislik(self.app.page, 480)
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text(f"{len(kayitlar)} satır bulundu"),
            content=ft.Column(satirlar, tight=True, scroll=ft.ScrollMode.AUTO, height=280, width=genislik),
            actions=[ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog()),
                     ft.FilledButton("İçe aktar", icon=ft.Icons.SAVE, on_click=kaydet)]))

    def _ice_hata_dialog(self, ozet: str, hatalar: list[str]):
        satirlar = [ft.Text(ozet, weight=ft.FontWeight.BOLD)]
        satirlar += [ft.Text(h, size=12, color="#b3261e") for h in hatalar[:25]]
        if len(hatalar) > 25:
            satirlar.append(ft.Text(f"… ve {len(hatalar) - 25} hata daha", size=12, color=METIN_IKINCIL))
        genislik = dialog_genislik(self.app.page, 520)
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text("İçe aktarma sonucu"),
            content=ft.Column(satirlar, tight=True, scroll=ft.ScrollMode.AUTO, height=320, width=genislik),
            actions=[ft.TextButton("Tamam", on_click=lambda _: self.app.page.pop_dialog())]))

    async def _ice_toplu_kaydet(self):
        async def is_():
            eklenen = guncellenen = 0
            hatalar: list[str] = []
            anahtar = {"personel": "tckn", "ogrenci": "tckn", "cari": "kod",
                       "malzeme": "kod", "urun": "kod", "bolum": "kod"}.get(self.tablo)
            yedek_anahtar = {"cari": "unvan", "malzeme": "ad", "urun": "ad", "bolum": "ad"}.get(self.tablo)
            for no, ham in enumerate(self._ice_kayitlar, 1):
                try:
                    veri = self._ice_satir_verisi(ham)
                    mevcut = None
                    if anahtar and veri.get(anahtar):
                        mevcut = next((k for k in self.kayitlar if str(k.get(anahtar) or "") == str(veri[anahtar])), None)
                    if not mevcut and yedek_anahtar and veri.get(yedek_anahtar):
                        mevcut = next((k for k in self.kayitlar
                                       if str(k.get(yedek_anahtar) or "").casefold() == str(veri[yedek_anahtar]).casefold()),
                                      None)
                    if mevcut:
                        veri["surum"] = mevcut["surum"]
                        await self.app.supa.guncelle(self.tablo, veri, id=mevcut["id"])
                        guncellenen += 1
                    else:
                        await self.app.supa.ekle(self.tablo, veri)
                        eklenen += 1
                except SupaHata as e:
                    hatalar.append(f"Satır {no}: {e.mesaj}")
                except (ValueError, KeyError, TypeError) as e:
                    hatalar.append(f"Satır {no}: {e}")
            await self.yukle()
            ozet = f"İçe aktarma: {eklenen} yeni, {guncellenen} güncellendi"
            if hatalar:
                ozet += f", {len(hatalar)} hatalı"
                self.app.bildir(ozet, hata=True)
                self._ice_hata_dialog(ozet, hatalar)
            else:
                self.app.bildir(ozet)

        await self.app.guvenli(is_)

    def _ice_satir_verisi(self, ham: dict) -> dict:
        """Ham Excel/PDF alanlarını form_verisi ile doğrulanabilir metin sözlüğüne çevirir."""
        metin = {}
        for alan, _, tur, zorunlu, _ in self.alanlar:
            if alan not in ham or ham[alan] in (None, ""):
                if tur == "bool":
                    metin[alan] = True
                continue
            v = ham[alan]
            if tur == "bool":
                metin[alan] = str(v).strip().lower() in ("1", "true", "evet", "x", "var")
            elif tur in ("para", "ondalik", "oran"):
                metin[alan] = str(v).replace(".", ",") if isinstance(v, float) else str(v)
            else:
                metin[alan] = str(v).strip()
        # Zorunlu seçimler için kaba varsayılanlar
        if self.tablo == "personel":
            metin.setdefault("hizmet_sinifi", "Öğretmen")
            metin.setdefault("dose_gorevi", "Öğretmen")
        if self.tablo == "cari":
            metin.setdefault("tur", "Tedarikçi")
        if self.tablo == "malzeme":
            metin.setdefault("tur", "İlk Madde ve Malzeme")
        if self.tablo == "urun":
            metin.setdefault("tur", "Mal")
        if self.tablo == "bolum":
            metin.setdefault("utp_yontemi", "A")
        metin.setdefault("aktif", True)
        return T.form_verisi(self.alanlar, metin)

    def _sec(self, kayit: dict):
        self.secili, self.form_acik = kayit, True
        self._liste_ciz(guncelle=False)
        self._form_ciz()
        self._yerlesim()
        self.guncelle()

    def _yeni(self, _=None):
        self.secili, self.form_acik = None, True
        self._form_ciz()
        self._yerlesim()
        self.guncelle()

    def _kapat(self, _=None):
        self.form_acik = False
        self._liste_ciz(guncelle=False)
        self._form_ciz()
        self._yerlesim()
        self.guncelle()

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
            title=ft.Text(f"{s.get('siparis_no')} · {s.get('konu') or ''}",
                          max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
            subtitle=ft.Text(f"{s.get('cari_unvan') or ''} · {s.get('bolum_ad') or ''} · "
                             f"{T.sayi_yaz(Decimal(str(self._kesin_deger(s, 'sozlesme_bedeli', 0))))} TL · "
                             f"{s.get('onay_durumu') or s.get('durum') or ''}",
                             max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
            selected=s.get("id") == secili_id, dense=not self.app.genis,
            on_click=lambda _, kayit=s: self._sec(kayit)) for s in self.kayitlar]
        if not satirlar:
            satirlar = [ft.Text("Henüz sipariş yok.", color=ft.Colors.ON_SURFACE_VARIANT)]
        liste_govde = ft.ListView(satirlar, expand=True, spacing=0)
        self.liste = ft.Column([
            sayfa_baslik_satiri("Sipariş / iş emirleri", [
                ft.FilledButton("Yeni", icon=ft.Icons.ADD, visible=self.yazabilir, on_click=self._yeni),
                ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile", on_click=self._yenile)],
                              ft.Icons.ASSIGNMENT, kompakt=not self.app.genis),
            liste_govde],
            expand=True, spacing=4)
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
        self.veri: dict = {"uyeler": [], "davetler": [], "sayfalar": []}
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
            ozel = u.get("yetki_ozel") or {}
            ozel_not = f" · {len(ozel)} özel yetki" if ozel else ""
            alt = " · ".join(x for x in (u.get("rol"), u.get("eposta"), self._bolum_adi(u.get("bolum_id")),
                                         None if u.get("aktif") else "Pasif") if x) + ozel_not
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
            sayfa_baslik_satiri("Kullanıcılar", [
                ft.FilledButton("Davet et", icon=ft.Icons.PERSON_ADD, on_click=lambda _: self._davet()),
                ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile",
                              on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))],
                              ft.Icons.GROUP),
            ft.Text("Davet ettiğiniz kişi aynı e-postayla hesap açıp doğruladığında okula kendiliğinden bağlanır. "
                    "Okul Müdürü ve Sistem Yöneticisi tüm sayfalarda yazabilir; diğer kullanıcılara rol dışında "
                    "sayfa yetkisi (yazma / okuma / kapalı) verebilirsiniz.", size=12,
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

    def _yetki_formu(self, uye: dict) -> tuple[list[ft.Control], dict[str, ft.Dropdown]]:
        """Özel sayfa yetkisi; müdür/sistem için gösterilmez (roller zaten tam yetkili)."""
        if uye.get("ben") or uye.get("rol") in ("Okul Müdürü", "Sistem Yöneticisi"):
            return [ft.Text(
                "Kendi hesabınızın veya Okul Müdürü / Sistem Yöneticisi rollerinin özel yetkisi düzenlenmez; "
                "bu roller tüm sayfalarda yazabilir.",
                size=12, color=METIN_IKINCIL)], {}
        ozel = uye.get("yetki_ozel") or {}
        kutular: dict[str, ft.Dropdown] = {}
        satirlar: list[ft.Control] = [
            ft.Text("Sayfa yetkileri", weight=ft.FontWeight.BOLD),
            ft.Text("Boş bırakılanlar rolün varsayılanına uyar. Yazma / okuma / kapalı ile rolü aşabilir "
                    "veya kısıtlayabilirsiniz.", size=12, color=METIN_IKINCIL)]
        for s in self.veri.get("sayfalar") or []:
            kod = s.get("sayfa")
            if not kod:
                continue
            mevcut = ozel.get(kod) if isinstance(ozel, dict) else None
            if mevcut not in ("y", "g", "-"):
                mevcut = "varsayilan"
            kutu = secim_kutusu(s.get("baslik") or kod, YETKI_SECENEKLERI, mevcut, bos=False)
            kutular[kod] = kutu
            satirlar.append(kutu)
        return satirlar, kutular

    @staticmethod
    def _yetki_payload(kutular: dict[str, ft.Dropdown]) -> dict:
        out = {}
        for sayfa, kutu in kutular.items():
            deger = (kutu.value or "").strip()
            if deger in ("y", "g", "-"):
                out[sayfa] = deger
        return out

    @staticmethod
    def _sayi(deger):
        return int(deger) if deger else None

    def _dialog(self, baslik: str, kontroller: list, etiket: str, is_, genislik: int = 420):
        dugme = ft.FilledButton(etiket)
        genislik = dialog_genislik(self.app.page, genislik)

        async def tik(_):
            if await self.app.guvenli(is_, dugme):
                self.app.page.pop_dialog()
                self.app.bildir(f"{etiket} işlemi tamamlandı.")
                await self.app.guvenli(self.yukle)

        dugme.on_click = tik
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text(baslik), scrollable=True,
            content=ft.Column(kontroller, tight=True, spacing=12, width=genislik, scroll=ft.ScrollMode.AUTO,
                              height=min(520, 80 + 48 * max(1, len(kontroller)))),
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
        yetki_satir, yetki_kutulari = self._yetki_formu(uye)

        async def is_():
            await self.app.supa.rpc(
                "dose_kullanici_guncelle", p_kullanici=uye["id"],
                p_ad_soyad=k["ad_soyad"].value.strip(), p_rol=k["rol"].value,
                p_bolum_id=self._sayi(k["bolum_id"].value),
                p_personel_id=self._sayi(k["personel_id"].value), p_aktif=bool(aktif.value),
                p_yetki_ozel=self._yetki_payload(yetki_kutulari) if yetki_kutulari else None)
            if uye.get("ben"):
                await self.app.ben_yukle()

        self._dialog("Kullanıcıyı düzenle", list(k.values()) + [aktif] + yetki_satir, "Kaydet", is_,
                     genislik=460)

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
                          f"{' #' + str(s['kayit_id']) if s.get('kayit_id') else ''}",
                          max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            subtitle=ft.Text(f"{s.get('zaman') or ''} — {s.get('ad_soyad') or ''}"
                             f"{' (' + s['rol'] + ')' if s.get('rol') else ''}"
                             f"{chr(10) + s['detay'] if s.get('detay') else ''}",
                             max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
            dense=True) for s in satirlar]
        self.kontrol.scroll = None
        self.kontrol.controls = [
            sayfa_baslik_satiri("İşlem kaydı", [
                ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile",
                              on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))],
                              ft.Icons.HISTORY, kompakt=not self.app.genis),
            ft.Text("Kim, hangi rolde, neyi, ne zaman yaptı. Son 200 işlem; değiştirilemez.",
                    size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.ListView(liste or [ft.Text("Henüz işlem yok.")], expand=True, spacing=0)]
        self.guncelle()
