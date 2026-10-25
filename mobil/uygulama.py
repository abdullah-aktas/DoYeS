"""DÖSE Yönetim Mobil (Flet): Android uygulaması ve web arayüzü.

Telefonda Python uygulamanın içinde çalışır ve okulun DÖSE Mobil Sunucusu'na HTTP ile bağlanır. Web sürümü
sunucunun kendisinde çalışır; tarayıcıya ayrıca bir şey kurulmaz.
"""
from __future__ import annotations

import asyncio
import base64
import json
from datetime import date, datetime

import flet as ft

try:
    from .istemci import ApiHatasi, Istemci
except ImportError:
    from istemci import ApiHatasi, Istemci

SURUM = "1.7.3"
SATICI = "Derik MTAL Döner Sermaye İşletmesi"

# Satıcı paketlemeden önce geçit adresini yazabilir. Boşsa: LAN keşif → GitHub surum.json → kayıtlı adres.
VARSAYILAN_GECIT = ""
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
SEVIYE_RENK = {"hata": ft.Colors.RED_700, "uyari": ft.Colors.ORANGE_800, "bilgi": ft.Colors.BLUE_700}
SEVIYE_IKON = {"hata": ft.Icons.ERROR, "uyari": ft.Icons.WARNING_AMBER, "bilgi": ft.Icons.INFO_OUTLINE}
GUN_RENK = {"ogretim": ft.Colors.GREY_800, "tatil": ft.Colors.BLUE_700, "pazar": ft.Colors.RED_400, "bayram": ft.Colors.RED_700}
BELGE_IKON = {"Sipariş": ft.Icons.ASSIGNMENT, "Fazla Çalışma": ft.Icons.SCHEDULE, "Parça Başı": ft.Icons.GROUPS,
              "Yıl Sonu": ft.Icons.EVENT_AVAILABLE}


# ---------------------------------------------------------------- biçimlendirme
def para(x) -> str:
    s = f"{float(x or 0):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def tarih(t) -> str:
    if not t:
        return ""
    t = str(t)
    try:
        if len(t) > 10:
            return datetime.strptime(t[:16], "%Y-%m-%d %H:%M").strftime("%d.%m.%Y %H:%M")
        return datetime.strptime(t, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return t


def sayi(metin, ad: str = "Değer") -> float | None:
    t = str(metin or "").strip().replace(" ", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        raise ValueError(f"{ad} geçerli bir sayı değil: {metin}") from None


def iso_tarih(metin, ad: str = "Tarih") -> str | None:
    t = str(metin or "").strip()
    if not t:
        return None
    for bicim in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, bicim).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"{ad} GG.AA.YYYY biçiminde olmalıdır: {metin}")


def satir(baslik: str, deger, kalin: bool = False, renk=None) -> ft.Row:
    return ft.Row([ft.Text(baslik, color=ft.Colors.GREY_700, expand=True, size=12),
                   ft.Text(str(deger if deger not in (None, "") else "-"),
                           weight=ft.FontWeight.BOLD if kalin else ft.FontWeight.W_500,
                           color=renk or ft.Colors.GREY_900, text_align=ft.TextAlign.RIGHT, expand=True,
                           selectable=True)])


def baslik(metin: str) -> ft.Text:
    return ft.Text(metin, size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900)


def kart(*kontroller, renk=None) -> ft.Card:
    return ft.Card(elevation=1, bgcolor=ft.Colors.WHITE,
                   content=ft.Container(ft.Column(list(kontroller), spacing=8), padding=16,
                                        bgcolor=renk or ft.Colors.WHITE, border_radius=16))


def mesaj_kutusu(metinler: list[str], seviye: str) -> ft.Container:
    return ft.Container(
        ft.Column([ft.Row([ft.Icon(SEVIYE_IKON[seviye], color=SEVIYE_RENK[seviye], size=18),
                           ft.Text(m, color=SEVIYE_RENK[seviye], expand=True, selectable=True)],
                          vertical_alignment=ft.CrossAxisAlignment.START) for m in metinler], spacing=6),
        padding=10, border_radius=10, bgcolor={"hata": ft.Colors.RED_50, "uyari": ft.Colors.ORANGE_50}.get(seviye, ft.Colors.BLUE_50))


def secenek(anahtar, metin) -> ft.DropdownOption:
    return ft.DropdownOption(key=str(anahtar), text=str(metin))


class Uygulama:
    def __init__(self, page: ft.Page, sabit_adres: str | None = None):
        self.page = page
        self.sabit_adres = sabit_adres
        self.web = sabit_adres is not None
        self.api: Istemci | None = None
        self.ben: dict = {}
        self.yil = date.today().year
        self.ay = date.today().month
        self.sekmeler: list = []
        self.sekme = 0
        self.fc_surum = None
        self._sync_cursor = 0
        self._sync_task: asyncio.Task | None = None
        self._sync_kesinti = False

    # ------------------------------------------------------------ altyapı
    async def baslat(self):
        p = self.page
        p.title = "DÖSE Yönetim Mobil"
        p.theme = ft.Theme(color_scheme_seed=ft.Colors.TEAL)
        p.theme_mode = ft.ThemeMode.LIGHT
        p.bgcolor = ft.Colors.GREY_50
        p.padding = 0
        p.on_view_pop = self._view_pop
        await self.giris_ekrani()

    async def _tercih(self, anahtar: str, varsayilan: str = "") -> str:
        try:
            return await self.page.shared_preferences.get(anahtar) or varsayilan
        except Exception:
            return varsayilan

    async def _tercih_yaz(self, anahtar: str, deger: str):
        try:
            await self.page.shared_preferences.set(anahtar, deger)
        except Exception:
            pass

    def _view_pop(self, e):
        self.geri()

    def geri(self):
        if len(self.page.views) > 1:
            self.page.views.pop()
            self.page.update()

    def gorunum(self, baslik_metni: str, kontroller: list, fab=None, eylemler=None) -> ft.View:
        halka = ft.ProgressRing(width=18, height=18, stroke_width=2, visible=False)
        v = ft.View(route=f"/s{len(self.page.views)}", padding=0, floating_action_button=fab,
                    appbar=ft.AppBar(title=ft.Text(baslik_metni), actions=[*(eylemler or []),
                                                                         ft.Container(halka, padding=ft.Padding.only(right=16))]),
                    controls=[ft.SafeArea(ft.ListView(kontroller, padding=12, spacing=10, expand=True), expand=True)])
        v.data = {"halka": halka}
        return v

    def ac(self, v: ft.View):
        self.page.views.append(v)
        self.page.update()

    def _halka(self):
        if self.page.views and isinstance(self.page.views[-1].data, dict):
            return self.page.views[-1].data.get("halka")
        return None

    async def cagir(self, islev, *args, **kwargs):
        """Sunucu çağrısını arka planda yapar; hata olursa kullanıcıya açıklar ve None döndürür."""
        halka = self._halka()
        if halka:
            halka.visible = True
            self.page.update()
        try:
            return await asyncio.to_thread(islev, *args, **kwargs)
        except ApiHatasi as e:
            if e.kod == 401 and self.api and self.api.token:
                await self.giris_ekrani(str(e))
            else:
                self.bilgi("İşlem yapılamadı" if e.kod else "Bağlantı sorunu", str(e))
            return None
        finally:
            if halka:
                halka.visible = False
                self.page.update()

    def bilgi(self, baslik_metni: str, metin: str, sonra=None):
        async def kapat(e):
            self.page.pop_dialog()
            if sonra:
                await sonra()
        self.page.show_dialog(ft.AlertDialog(title=ft.Text(baslik_metni), content=ft.Text(metin, selectable=True),
                                             scrollable=True, actions=[ft.TextButton("Tamam", on_click=kapat)]))

    def sor(self, baslik_metni: str, metin: str, evet, evet_metni: str = "Evet"):
        async def tamam(e):
            self.page.pop_dialog()
            await evet()
        self.page.show_dialog(ft.AlertDialog(title=ft.Text(baslik_metni), content=ft.Text(metin), modal=True,
                                             actions=[ft.TextButton("Vazgeç", on_click=lambda e: self.page.pop_dialog()),
                                                      ft.FilledButton(evet_metni, on_click=tamam)]))

    def bildir(self, metin: str):
        self.page.show_dialog(ft.SnackBar(ft.Text(metin)))

    def modul(self, ad: str) -> str:
        return (self.ben.get("moduller") or {}).get(ad) or ""

    async def cihaz_adi(self) -> str:
        if self.web:
            return f"Web tarayıcı ({self.page.client_ip or '?'})"
        try:
            b = await self.page.get_device_info()
            parcalar = [getattr(b, a, None) for a in ("brand", "manufacturer", "model", "name", "computer_name")]
            ad = " ".join(dict.fromkeys(str(x) for x in parcalar if x))
            if ad:
                return ad[:80]
        except Exception:
            pass
        return f"Mobil ({self.page.platform.value if self.page.platform else '?'})"

    # ------------------------------------------------------------ giriş
    async def giris_ekrani(self, mesaj: str = ""):
        self.ben = {}
        if self.api:
            self.api.token = None
        adres = self.sabit_adres or await self._tercih("adres")
        gecit = VARSAYILAN_GECIT or await self._tercih("gecit")
        self.t_kurum = ft.TextField(label="Kurum kodu", value=await self._tercih("kurum_kodu"),
                                    hint_text="MEB kurum kodu (5–8 rakam)", prefix_icon=ft.Icons.TAG,
                                    keyboard_type=ft.KeyboardType.NUMBER, autocorrect=False,
                                    filled=True, border=ft.OutlineInputBorder(border_radius=12),
                                    helper="Adres yazmadan: aynı Wi-Fi'de sunucu keşfedilir veya GitHub geçidi kullanılır.")
        self.t_kullanici = ft.TextField(label="Kullanıcı adı", value=await self._tercih("kullanici"),
                                        prefix_icon=ft.Icons.PERSON, autocorrect=False, enable_suggestions=False,
                                        filled=True, border=ft.OutlineInputBorder(border_radius=12))
        self.t_sifre = ft.TextField(label="Şifre", password=True, can_reveal_password=True, prefix_icon=ft.Icons.LOCK,
                                    on_submit=self.giris_yap, filled=True,
                                    border=ft.OutlineInputBorder(border_radius=12))
        self.t_adres = ft.TextField(label="Sunucu adresi (gerekirse)", value=adres or gecit,
                                    hint_text="ör. 192.168.1.10:8765 — genelde boş bırakın",
                                    prefix_icon=ft.Icons.DNS, keyboard_type=ft.KeyboardType.URL,
                                    filled=True, border=ft.OutlineInputBorder(border_radius=12),
                                    visible=False)
        self.c_sertifika = ft.Checkbox(label="Okulun kendi (imzasız) sertifikasına güven", visible=False,
                                       value=await self._tercih("sertifika_guven") == "1")
        self.b_gelismis = ft.TextButton("Gelişmiş: sunucu adresi…", on_click=self._gelismis_ac)
        self.b_gelismis.visible = not self.web
        self.l_hata = ft.Text(mesaj, color=ft.Colors.RED_800, selectable=True)
        self.b_giris = ft.FilledButton("Giriş yap", icon=ft.Icons.LOGIN, on_click=self.giris_yap, height=52)
        logo = ft.Image(src="logo.png", width=132, height=72, fit=ft.BoxFit.CONTAIN,
                        error_content=ft.Icon(ft.Icons.ACCOUNT_BALANCE, size=48, color=ft.Colors.TEAL_700))
        self.hata_alani = ft.Container(self.l_hata, padding=12, bgcolor=ft.Colors.RED_50,
                                       border_radius=12, visible=bool(mesaj))
        ekran_genisligi = getattr(self.page, "width", None) or 500
        kart_genisligi = max(240, min(460, ekran_genisligi - 32))
        giris_karti = ft.Container(
            ft.Column([
                ft.Container(logo, alignment=ft.Alignment.CENTER),
                ft.Text("DÖSE Yönetim", size=26, weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_GREY_900, text_align=ft.TextAlign.CENTER),
                ft.Text("Okul hesabınızla güvenli şekilde giriş yapın.",
                        color=ft.Colors.BLUE_GREY_600, text_align=ft.TextAlign.CENTER),
                ft.Divider(height=12, color=ft.Colors.GREY_200),
                self.t_kurum, self.t_kullanici, self.t_sifre,
                self.b_gelismis, self.t_adres, self.c_sertifika, self.hata_alani, self.b_giris,
            ], horizontal_alignment=ft.CrossAxisAlignment.STRETCH, spacing=14),
            width=kart_genisligi, padding=24, bgcolor=ft.Colors.WHITE, border_radius=22,
            border=ft.Border.all(1, ft.Colors.GREY_200),
        )
        icerik = ft.Column([
            giris_karti,
            ft.Text(f"Sürüm {SURUM}  •  {SATICI}", size=11, color=ft.Colors.BLUE_GREY_500,
                    text_align=ft.TextAlign.CENTER),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=16, scroll=ft.ScrollMode.AUTO)
        self.page.views.clear()
        self.page.views.append(ft.View(route="/", padding=16, bgcolor=ft.Colors.GREY_50, controls=[
            ft.SafeArea(ft.Container(icerik, width=kart_genisligi, alignment=ft.Alignment.CENTER), expand=True)],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER))
        self.page.update()
        self.page.run_task(self._guncelleme_kontrol_giris)

    async def _gelismis_ac(self, e=None):
        self.t_adres.visible = True
        self.c_sertifika.visible = True
        self.b_gelismis.visible = False
        self.page.update()

    def _adres_coz(self, kurum: str, adres: str) -> str:
        """Elle adres > web sabit > varsayılan > LAN keşif > GitHub gecit."""
        if self.sabit_adres:
            return self.sabit_adres
        try:
            from kesif import adres_coz
        except ImportError:
            from .kesif import adres_coz
        return adres_coz(kurum_kodu=kurum, sunucu_adresi=adres, varsayilan_gecit=VARSAYILAN_GECIT)

    async def giris_yap(self, e=None):
        kurum = "".join((self.t_kurum.value or "").split())
        ad, sifre = (self.t_kullanici.value or "").strip(), self.t_sifre.value or ""
        if not kurum or not ad or not sifre:
            self.l_hata.value = "Kurum kodu, kullanıcı adı ve şifreyi giriniz."
            self.hata_alani.visible = True
            self.page.update()
            return
        if not kurum.isdigit() or not (5 <= len(kurum) <= 8):
            self.l_hata.value = "Kurum kodu 5–8 rakam olmalıdır."
            self.hata_alani.visible = True
            self.page.update()
            return
        self.b_giris.disabled, self.l_hata.value = True, "Sunucu aranıyor…"
        self.hata_alani.visible = True
        self.b_giris.content = "Bağlanıyor…"
        self.page.update()
        try:
            adres = await asyncio.to_thread(
                self._adres_coz, kurum, "" if self.web else (self.t_adres.value or ""))
        except ValueError as h:
            self.l_hata.value = str(h)
            self.hata_alani.visible = True
            self.b_giris.disabled, self.b_giris.content = False, "Giriş yap"
            self.page.update()
            return
        self.l_hata.value = ""
        self.page.update()
        ek = {"X-Istemci-IP": self.page.client_ip or ""} if self.web else {}
        self.api = Istemci(adres, sertifika_dogrula=not (self.web or self.c_sertifika.value), ek_basliklar=ek)
        try:
            y = await asyncio.to_thread(self.api.giris, ad, sifre, await self.cihaz_adi(), kurum)
        except ApiHatasi as h:
            self.l_hata.value = str(h)
            self.hata_alani.visible = True
            self.b_giris.disabled, self.b_giris.content = False, "Giriş yap"
            self.page.update()
            return
        if not self.web:
            await self._tercih_yaz("adres", self.api.adres)
            await self._tercih_yaz("gecit", self.api.adres)
            await self._tercih_yaz("sertifika_guven", "1" if self.c_sertifika.value else "0")
        await self._tercih_yaz("kullanici", ad)
        await self._tercih_yaz("kurum_kodu", kurum)
        if y["kullanici"].get("sifre_degismeli"):
            self.page.views.clear()
            self.sifre_ekrani(zorunlu=True)
            return
        await self.ana_ekran()

    async def _guncelleme_kontrol_giris(self):
        try:
            try:
                from kesif import github_surum
            except ImportError:
                from .kesif import github_surum
            veri = await asyncio.to_thread(github_surum)
        except Exception:
            return
        if not veri or not veri.get("surum"):
            return
        uzak = str(veri["surum"]).strip()

        def parcala(s):
            return [int("".join(c for c in p if c.isdigit()) or 0) for p in str(s).split(".")]

        try:
            if parcala(uzak) <= parcala(SURUM):
                return
        except Exception:
            return
        url = str(veri.get("indir") or "https://github.com/abdullah-aktas/DoYeS/releases/latest")

        async def ac(e=None):
            self.page.pop_dialog()
            self.page.launch_url(url)

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text(f"Güncelleme var: {uzak}"),
            content=ft.Text(f"Sizin sürümünüz: {SURUM}\n\n{veri.get('notlar') or 'Yeni sürüm GitHub’da.'}"),
            actions=[ft.TextButton("Sonra", on_click=lambda e: self.page.pop_dialog()),
                     ft.FilledButton("GitHub’da aç", on_click=ac)]))

    async def cikis(self, e=None):
        if self.api and self.api.token:
            try:
                await asyncio.to_thread(self.api.post, "/cikis")
            except ApiHatasi:
                pass
        await self.giris_ekrani("Oturum kapatıldı.")

    def sifre_ekrani(self, zorunlu: bool = False):
        eski = ft.TextField(label="Mevcut şifre", password=True, can_reveal_password=True)
        yeni = ft.TextField(label="Yeni şifre (en az 6 karakter)", password=True, can_reveal_password=True)
        tekrar = ft.TextField(label="Yeni şifre (tekrar)", password=True, can_reveal_password=True)

        async def kaydet(e):
            if (yeni.value or "") != (tekrar.value or ""):
                self.bilgi("Şifre", "Yeni şifreler aynı değil.")
                return
            if await self.cagir(self.api.post, "/sifre", {"eski": eski.value or "", "yeni": yeni.value or ""}) is None:
                return
            self.bildir("Şifreniz değiştirildi.")
            if zorunlu:
                await self.ana_ekran()
            else:
                self.geri()

        aciklama = ("Güvenliğiniz için ilk girişte şifrenizi değiştirmeniz gerekiyor." if zorunlu else
                    "Şifre değişince diğer cihazlardaki mobil oturumlarınız kapanır.")
        self.ac(self.gorunum("Şifre değiştir", [ft.Text(aciklama), eski, yeni, tekrar,
                                                ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, on_click=kaydet)]))

    # ------------------------------------------------------------ ana ekran
    async def ana_ekran(self):
        ben = await self.cagir(self.api.get, "/ben")
        if ben is None:
            return
        self.ben = ben
        self.yil = ben.get("yil") or self.yil
        tanimlar = [("panel", "Özet", ft.Icons.DASHBOARD_OUTLINED, self.panel_sekmesi),
                    ("onay", "Onaylar", ft.Icons.TASK_ALT, self.onay_sekmesi),
                    ("siparis", "İşler", ft.Icons.ASSIGNMENT_OUTLINED, self.siparis_sekmesi),
                    ("fazla", "Fazla Ç.", ft.Icons.SCHEDULE, self.fazla_sekmesi)]
        self.sekmeler = [t for t in tanimlar if self.modul(t[0])] + [("diger", "Diğer", ft.Icons.MENU, self.diger_sekmesi)]
        bekleyen = ben.get("bekleyen_onay") or 0
        self.nav = ft.NavigationBar(selected_index=0, on_change=self._sekme_degisti, destinations=[
            ft.NavigationBarDestination(icon=ikon, label=etiket, badge=str(bekleyen) if a == "onay" and bekleyen else None)
            for a, etiket, ikon, _ in self.sekmeler],
            bgcolor=ft.Colors.WHITE, indicator_color=ft.Colors.TEAL_50, elevation=2)
        self.govde = ft.Container(expand=True)
        self.halka = ft.ProgressRing(width=18, height=18, stroke_width=2, visible=False)
        k = ben["kullanici"]
        kurum = (ben.get("kurum") or "DÖSE").replace("Mesleki ve Teknik Anadolu Lisesi", "MTAL")
        menu = ft.PopupMenuButton(icon=ft.Icons.ACCOUNT_CIRCLE, items=[
            ft.PopupMenuItem(content=ft.Text(f"{k.get('ad_soyad') or k['kullanici_adi']}\n{k['rol']}"), disabled=True),
            ft.PopupMenuItem(content="Şifre değiştir", icon=ft.Icons.PASSWORD, on_click=lambda e: self.sifre_ekrani()),
            ft.PopupMenuItem(content="Çıkış", icon=ft.Icons.LOGOUT, on_click=self.cikis)])
        self.ana = ft.View(route="/ana", padding=0, bgcolor=ft.Colors.GREY_50, navigation_bar=self.nav,
                           appbar=ft.AppBar(title=ft.Text(kurum, size=16, weight=ft.FontWeight.W_600),
                                            bgcolor=ft.Colors.WHITE, elevation=0, actions=[
                               ft.Container(self.halka, padding=ft.Padding.only(right=8)),
                               ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile", on_click=self.sekme_yenile), menu]),
                           controls=[ft.SafeArea(self.govde, expand=True)])
        self.ana.data = {"halka": self.halka}
        self.page.views.clear()
        self.page.views.append(self.ana)
        if ben.get("salt_okunur"):
            self.bildir(ben.get("lisans") or "Program salt okunur çalışıyor.")
        self.sekme = 0
        await self.sekme_yenile()
        if isinstance(self.page, ft.Page):
            if self._sync_task and not self._sync_task.done():
                self._sync_task.cancel()
            self._sync_task = asyncio.create_task(self._es_zamanli_izle())

    async def _es_zamanli_izle(self):
        while self.api and self.api.token:
            try:
                sonuc = await asyncio.to_thread(self.api.get, "/senkron", son_no=self._sync_cursor)
                self._sync_cursor = sonuc["son_no"]
                degisiklikler = sonuc["degisiklikler"]
                if self._sync_kesinti:
                    self._sync_kesinti = False
                    self.bildir("Eş zamanlı bağlantı yeniden kuruldu.")
                if degisiklikler and self.page.views:
                    if self.page.views[-1] is self.ana:
                        son = degisiklikler[-1]
                        self.bildir(f"{son.get('ad_soyad') or son.get('kullanici') or 'Başka bir kullanıcı'} "
                                    f"({son.get('rol') or 'kullanıcı'}) güncelleme yaptı; ekran yenilendi.")
                        await self.sekme_yenile()
                    else:
                        self.bildir("Başka kullanıcılar kayıtları güncelledi. Açık formu kapatıp yeniden açarak "
                                    "güncel bilgileri yükleyin.")
            except ApiHatasi as e:
                if e.kod == 401:
                    await self.giris_ekrani(str(e))
                    return
                if not self._sync_kesinti:
                    self._sync_kesinti = True
                    self.bildir("Eş zamanlı bağlantı kesildi; bağlantı sağlanınca yeniden denenecek.")
            await asyncio.sleep(5)

    async def _sekme_degisti(self, e):
        self.sekme = e.control.selected_index
        await self.sekme_yenile()

    async def sekme_yenile(self, e=None):
        if not self.sekmeler:
            return
        self.ana.floating_action_button = None
        await self.sekmeler[self.sekme][3]()
        self.page.update()

    def liste(self, kontroller: list) -> ft.ListView:
        return ft.ListView(kontroller, padding=16, spacing=12, expand=True)

    def _yil_secici(self, degisti) -> ft.Dropdown:
        async def sec(e):
            self.yil = int(e.control.value)
            await degisti()
        return ft.Dropdown(label="Yıl", value=str(self.yil), width=110, dense=True, on_select=sec,
                           options=[secenek(y, y) for y in range(date.today().year - 3, date.today().year + 1)])

    def _ay_secici(self, degisti, tumu: bool = False) -> ft.Dropdown:
        async def sec(e):
            self.ay = int(e.control.value)
            await degisti()
        secenekler = ([secenek(0, "Tüm yıl")] if tumu else []) + [secenek(i + 1, a) for i, a in enumerate(AYLAR)]
        return ft.Dropdown(label="Ay", value=str(self.ay), width=140, dense=True, on_select=sec, options=secenekler)

    # ------------------------------------------------------------ özet
    async def panel_sekmesi(self):
        v = await self.cagir(self.api.get, "/panel", yil=self.yil)
        if v is None:
            return
        o = v["ozet"]
        gostergeler = [("Satış hasılatı", para(o["satis"]) + " TL", ft.Icons.POINT_OF_SALE, ft.Colors.TEAL_700),
                       ("Tahsilat", para(o["tahsilat"]) + " TL", ft.Icons.PAYMENTS, ft.Colors.GREEN_700),
                       ("Kasa + banka", para(o["nakit"]) + " TL", ft.Icons.ACCOUNT_BALANCE_WALLET, ft.Colors.BLUE_700),
                       ("Açık alacak", para(o["alacak"]) + " TL", ft.Icons.REQUEST_QUOTE, ft.Colors.ORANGE_800),
                       ("Açık sipariş", str(o["acik_siparis"]), ft.Icons.ASSIGNMENT, ft.Colors.INDIGO_700),
                       ("Dönem kârı", para(o["kar"]) + " TL", ft.Icons.TRENDING_UP,
                        ft.Colors.GREEN_800 if o["kar"] >= 0 else ft.Colors.RED_700),
                       ("Stok değeri", para(o["stok"]) + " TL", ft.Icons.INVENTORY_2, ft.Colors.BROWN_600),
                       ("Ödenmemiş hazine payı", para(o["hazine_odenmemis"]) + " TL", ft.Icons.ACCOUNT_BALANCE,
                        ft.Colors.RED_700 if o["hazine_odenmemis"] else ft.Colors.GREY_700)]
        kutular = [ft.Container(
                       ft.Column([
                           ft.Row([
                               ft.Container(ft.Icon(ikon, color=renk, size=20), width=40, height=40,
                                            alignment=ft.Alignment.CENTER, bgcolor=ft.Colors.GREY_100,
                                            border_radius=12),
                               ft.Text(ad, size=12, color=ft.Colors.BLUE_GREY_700, expand=True, max_lines=2),
                           ], spacing=10),
                           ft.Text(deger, size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_900),
                       ], spacing=12),
                       col={"xs": 6, "md": 3}, padding=14, border_radius=16, bgcolor=ft.Colors.WHITE,
                       border=ft.Border.all(1, ft.Colors.GREY_200))
                   for ad, deger, ikon, renk in gostergeler]
        kullanici = self.ben.get("kullanici") or {}
        ad = kullanici.get("ad_soyad") or kullanici.get("kullanici_adi") or "Kullanıcı"
        kontroller = [
            ft.Container(
                ft.Column([
                    ft.Text(f"Merhaba, {ad.split()[0]}", size=22,
                            weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    ft.Text(f"{kullanici.get('rol') or 'Kullanıcı'}  •  {self.yil} çalışma özeti",
                            size=13, color=ft.Colors.TEAL_50),
                ], spacing=4),
                padding=20, border_radius=18, bgcolor=ft.Colors.TEAL_800,
            ),
            ft.Row([self._yil_secici(self.sekme_yenile)]),
            ft.ResponsiveRow(kutular, spacing=10, run_spacing=10),
        ]
        if v["bekleyen_onay"]:
            async def onaya(e):
                i = next(i for i, s in enumerate(self.sekmeler) if s[0] == "onay")
                self.nav.selected_index = self.sekme = i
                await self.sekme_yenile()
            kontroller.append(ft.Container(ft.ListTile(leading=ft.Icon(ft.Icons.PENDING_ACTIONS, color=ft.Colors.WHITE),
                                                       title=ft.Text(f"Onayınızı bekleyen {v['bekleyen_onay']} belge var",
                                                                     color=ft.Colors.WHITE),
                                                       trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, color=ft.Colors.WHITE),
                                                       on_click=onaya if self.modul("onay") else None),
                                           bgcolor=ft.Colors.TEAL_700, border_radius=12))
        uyarilar = v["uyarilar"]
        kontroller.append(baslik(f"Bugün ne yapmalıyım? ({len(uyarilar)})"))
        if not uyarilar:
            kontroller.append(mesaj_kutusu(["Şu anda sizin yapmanız gereken acil bir iş görünmüyor."], "bilgi"))
        for seviye in ("hata", "uyari", "bilgi"):
            metinler = [u["metin"] + (f"\n➜ {u['cozum']}" if u.get("cozum") else "") for u in uyarilar if u["seviye"] == seviye]
            if metinler:
                kontroller.append(mesaj_kutusu(metinler, seviye))
        sureler = v.get("sureler") or []
        if sureler:
            kontroller.append(baslik("Yaklaşan yasal son tarihler"))
            for seviye, kosul in (("hata", lambda g: g <= 3), ("uyari", lambda g: 3 < g <= 10), ("bilgi", lambda g: g > 10)):
                metinler = [f"{s['tarih'][8:10]}.{s['tarih'][5:7]}.{s['tarih'][:4]} ({s['kalan_gun']} gün): {s['ad']} — "
                            f"{s['aciklama']}" for s in sureler if kosul(s["kalan_gun"])]
                if metinler:
                    kontroller.append(mesaj_kutusu(metinler, seviye))
        self.govde.content = self.liste(kontroller)

    # ------------------------------------------------------------ onaylar
    def _belge_satiri(self, b: dict) -> ft.Control:
        async def ac(e):
            await self.onay_detay(b["belge_turu"], b["belge_id"])
        alt = " • ".join(x for x in (b.get("konu"), b.get("bolum_ad"), (para(b["tutar"]) + " TL") if b.get("tutar") else None) if x)
        return ft.Card(content=ft.ListTile(
            leading=ft.Icon(BELGE_IKON.get(b["belge_turu"], ft.Icons.DESCRIPTION), color=ft.Colors.TEAL_700),
            title=ft.Text(f"{b['belge_turu']}: {b.get('no') or b['belge_id']}", weight=ft.FontWeight.BOLD),
            subtitle=ft.Text(f"{alt}\nBekleyen: {b.get('asama_adi')} ({b.get('bekleyen_rol')})"
                             + (f"\nHazırlayan: {b['hazirlayan']}" if b.get("hazirlayan") else "")),
            is_three_line=True, trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT), on_click=ac))

    async def onay_sekmesi(self):
        v = await self.cagir(self.api.get, "/onay")
        if v is None:
            return
        kontroller = []
        if not v["akis_acik"]:
            kontroller.append(mesaj_kutusu(["Onay akışı kapalı. Belgeler masaüstünde veya belge ekranından doğrudan onaylanır."],
                                           "bilgi"))
        kontroller.append(baslik(f"Onayınızı bekleyenler ({len(v['bana_bekleyen'])})"))
        kontroller += [self._belge_satiri(b) for b in v["bana_bekleyen"]] or [ft.Text("Onayınızı bekleyen belge yok.")]
        if v["diger_bekleyen"]:
            kontroller.append(baslik(f"Süreçteki diğer belgeler ({len(v['diger_bekleyen'])})"))
            kontroller += [self._belge_satiri(b) for b in v["diger_bekleyen"]]
        self.govde.content = self.liste(kontroller)
        bekleyen = len(v["bana_bekleyen"])
        i = next((i for i, s in enumerate(self.sekmeler) if s[0] == "onay"), None)
        if i is not None:
            self.nav.destinations[i].badge = str(bekleyen) if bekleyen else None

    def _belge_detay_kontrolleri(self, tur: str, d: dict) -> list:
        if not d:
            return []
        if tur == "Sipariş":
            return self._siparis_kontrolleri(d)
        if tur == "Fazla Çalışma":
            puantaj = json.loads(d["puantaj"]) if d.get("puantaj") else {}
            gunler = ", ".join(f"{int(g)}. gün {s:g} sa" for g, s in sorted(puantaj.items(), key=lambda x: int(x[0])))
            return [kart(baslik("Fazla çalışma"), satir("Personel", d.get("ad_soyad")), satir("Görevi", d.get("dose_gorevi")),
                         satir("Dönem", f"{AYLAR[d['ay'] - 1]} {d['yil']}"), satir("Sipariş", d.get("siparis_no") or "Siparişsiz"),
                         satir("Saat", f"{d['saat']:g}"), satir("Saat ücreti", para(d["saat_ucreti"]) + " TL"),
                         satir("Brüt", para(d["brut"]) + " TL", True), satir("Gelir vergisi", para(d["gelir_vergisi"]) + " TL"),
                         satir("Damga vergisi", para(d["damga_vergisi"]) + " TL"), satir("Net", para(d["net"]) + " TL", True),
                         *( [ft.Text("Puantaj: " + gunler, size=12, color=ft.Colors.GREY_700)] if gunler else []),
                         *( [ft.Text("Açıklama: " + d["aciklama"], size=12)] if d.get("aciklama") else []))]
        if tur == "Parça Başı":
            satirlar = [satir(f"{r['ad_soyad']} ({r['kisi_turu']})", f"Brüt {para(r['brut'])} • Net {para(r['net'])}")
                        for r in d.get("satirlar") or []]
            return [kart(baslik("Parça başı bordrosu"), satir("Dönem", f"{AYLAR[d['ay'] - 1]} {d['yil']}"),
                         satir("Sipariş", f"{d.get('siparis_no') or ''} {d.get('konu') or ''}"),
                         satir("Kabul edilen işçilik", para(d.get("kabul_edilen_iscilik")) + " TL"), ft.Divider(), *satirlar)]
        return [kart(baslik("Yıl sonu dağıtımı"), satir("Dönem kârı", para(d.get("donem_kari")) + " TL"),
                     satir("Dağıtılan ÜTP", para(d.get("dagitilan_utp")) + " TL", True),
                     satir("Sermaye payı", para(d.get("sermaye_payi")) + " TL"),
                     satir("Merkez Saymanlık payı", para(d.get("merkez_payi")) + " TL"),
                     satir("SHÇEK", para(d.get("shcek")) + " TL"))]

    async def onay_detay(self, tur: str, bid: int):
        v = await self.cagir(self.api.get, Istemci.yol("onay", tur, bid))
        if v is None:
            return
        oz, dr, isl = v["ozet"], v["durum"], v["islemler"]
        kontroller = [kart(ft.Row([ft.Icon(BELGE_IKON.get(tur, ft.Icons.DESCRIPTION), color=ft.Colors.TEAL_700),
                                   ft.Text(f"{tur}: {oz.get('no') or bid}", size=17, weight=ft.FontWeight.BOLD, expand=True)]),
                           ft.Text(oz.get("konu") or ""), satir("Bölüm", oz.get("bolum_ad")),
                           satir("Tutar", para(oz.get("tutar")) + " TL" if oz.get("tutar") else "-"),
                           satir("Durum", v["durum_metni"], True,
                                 ft.Colors.GREEN_800 if dr["durum"] == "Onaylandı" else ft.Colors.ORANGE_800))]
        if v["kontrol_hatalari"]:
            kontroller.append(mesaj_kutusu(["Mevzuat kontrolü — son onaya engel eksikler:"] + v["kontrol_hatalari"], "hata"))
        asamalar = []
        for i, a in enumerate(v["asamalar"], 1):
            gecti = dr["durum"] == "Onaylandı" or (dr["durum"] == "Bekliyor" and i < dr["asama"])
            simdi = dr["durum"] == "Bekliyor" and i == dr["asama"]
            asamalar.append(ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE if gecti else (ft.Icons.PENDING if simdi else ft.Icons.RADIO_BUTTON_UNCHECKED),
                                            color=ft.Colors.GREEN_700 if gecti else (ft.Colors.ORANGE_800 if simdi else ft.Colors.GREY_500)),
                                    ft.Text(f"{a['ad']} ({a['rol']})", expand=True,
                                            weight=ft.FontWeight.BOLD if simdi else None)]))
        kontroller.append(kart(baslik("Onay aşamaları"), *asamalar))
        kontroller += self._belge_detay_kontrolleri(tur, v["detay"])
        if v["gecmis"]:
            kontroller.append(kart(baslik("Onay geçmişi"), *[
                ft.ListTile(dense=True, leading=ft.Icon(ft.Icons.HISTORY, size=18),
                            title=ft.Text(f"{g['karar']} • {g.get('ad_soyad') or g.get('kullanici')} ({g.get('rol') or ''})"),
                            subtitle=ft.Text(f"{tarih(g.get('zaman'))} • {g.get('asama_adi') or ''}"
                                             + (f"\n“{g['aciklama']}”" if g.get("aciklama") else "")))
                for g in reversed(v["gecmis"])]))
        aciklama = ft.TextField(label="Açıklama / gerekçe", multiline=True, min_lines=2, max_lines=4)

        def islem(etiket, yol, veri_fn, basari, renk=None, ikon=None, gerekce=False, soru=None):
            async def calistir():
                if gerekce and not (aciklama.value or "").strip():
                    self.bilgi(etiket, "Gerekçe yazınız.")
                    return
                y = await self.cagir(self.api.post, Istemci.yol("onay", tur, bid, yol), veri_fn())
                if y is None:
                    return
                self.bildir(f"{basari}. Yeni durum: {y.get('durum_metni')}")
                self.geri()
                await self.sekme_yenile()

            async def tikla(e):
                if soru:
                    self.sor(etiket, soru, calistir, etiket)
                else:
                    await calistir()
            stil = ft.ButtonStyle(bgcolor=renk) if renk else None
            return ft.FilledButton(etiket, icon=ikon, on_click=tikla, style=stil, height=46)

        not_ = lambda: {"aciklama": aciklama.value or ""}
        butonlar = []
        if isl["karar"]:
            son = dr["asama"] == len(v["asamalar"])
            butonlar.append(islem("Onayla" if son else "Uygun gör", "karar", lambda: {"onay": True, "aciklama": aciklama.value or ""},
                                  "Onay verildi", ft.Colors.GREEN_700, ft.Icons.CHECK,
                                  soru="Belge onaylanacak; son onayda muhasebe kayıtları oluşturulur. Devam edilsin mi?" if son else None))
            butonlar.append(islem("İade et", "karar", lambda: {"onay": False, "aciklama": aciklama.value or ""},
                                  "Belge iade edildi", ft.Colors.RED_700, ft.Icons.UNDO, gerekce=True))
        if isl["gonder"]:
            butonlar.append(islem("Onaya gönder", "gonder", not_, "Belge onaya gönderildi", None, ft.Icons.SEND))
        if isl["geri_cek"]:
            butonlar.append(islem("Geri çek", "geri-cek", not_, "Belge geri çekildi", ft.Colors.GREY_700, ft.Icons.REPLY,
                                  soru="Belge düzeltme için hazırlama aşamasına çekilsin mi?"))
        if isl["dogrudan_onay"]:
            butonlar.append(islem("Onayla", "dogrudan", lambda: {}, "Belge onaylandı", ft.Colors.GREEN_700, ft.Icons.CHECK,
                                  soru="Belge onaylanacak ve muhasebe kayıtları oluşturulacak. Devam edilsin mi?"))
        if butonlar:
            kontroller += [aciklama, ft.Column(butonlar, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, spacing=8)]
        elif dr["durum"] == "Bekliyor":
            kontroller.append(mesaj_kutusu([f"Belge {v['durum_metni'].replace('Bekliyor: ', '')} onayını bekliyor; "
                                            "bu aşamada sizin işlem yetkiniz yok."], "bilgi"))
        self.ac(self.gorunum(f"{tur} onayı", kontroller))

    # ------------------------------------------------------------ siparişler
    def _siparis_kontrolleri(self, s: dict) -> list:
        t = s.get("tahsis") or {}
        kalemler = [satir(f"{k.get('urun_ad') or k.get('aciklama') or 'Kalem'} — {k['miktar']:g} {k.get('birim') or ''}",
                          f"{para(k['birim_fiyat'])} TL" + (f" (−%{k['iskonto_orani'] * 100:g})" if k.get("iskonto_orani") else ""))
                    for k in s.get("kalemler") or []]
        k = [kart(baslik("Sipariş bilgileri"), satir("Müşteri", s.get("unvan")), satir("Bölüm", s.get("bolum_ad")),
                  satir("Tarih", tarih(s.get("tarih"))), satir("Ücret esası", s.get("ucret_esasi")),
                  satir("Bedel (KDV hariç)", para(s.get("sozlesme_bedeli")) + " TL", True),
                  satir("KDV oranı", f"%{(s.get('kdv_orani') or 0) * 100:g}"), satir("Teslim", tarih(s.get("teslim_tarihi"))),
                  satir("Durum", s.get("durum")), satir("Faturalanan", para(s.get("faturalanan")) + " TL")),
             kart(baslik("Kalemler"), *(kalemler or [ft.Text("Kalem yok.")]))]
        if t:
            k.append(kart(baslik("Yasal dağılım"), satir("Kâr", para(t["kar"]) + " TL"),
                          satir("Faaliyet gideri", para(t["faaliyet"]) + " TL"), satir("Malzeme", para(t["malzeme"]) + " TL"),
                          satir("Azami işçilik", para(t["azami_iscilik"]) + " TL"), satir("İşçilik", para(t["iscilik"]) + " TL", True),
                          satir("Öğrenci hakkı", para(t["ogrenci_hakki"]) + " TL"),
                          satir("Personel işçiliği", para(t["personel_iscilik"]) + " TL")))
            if t.get("hatalar"):
                k.append(mesaj_kutusu(t["hatalar"], "hata"))
            if t.get("uyarilar"):
                k.append(mesaj_kutusu(t["uyarilar"], "uyari"))
        if s.get("aciklama"):
            k.append(kart(baslik("Açıklama"), ft.Text(s["aciklama"], selectable=True)))
        return k

    async def siparis_sekmesi(self):
        if not hasattr(self, "s_durum"):
            self.s_durum, self.s_ara = "acik", ""

        async def durum_sec(e):
            self.s_durum = e.control.value
            await self.sekme_yenile()

        async def ara(e):
            self.s_ara = e.control.value or ""
            await self.sekme_yenile()
        v = await self.cagir(self.api.get, "/siparisler", yil=self.yil, durum=self.s_durum, ara=self.s_ara)
        if v is None:
            return
        ust = ft.Row([self._yil_secici(self.sekme_yenile),
                      ft.Dropdown(label="Durum", value=self.s_durum, width=150, dense=True, on_select=durum_sec,
                                  options=[secenek("acik", "Açık işler"), secenek("Teklif", "Teklifler"), secenek("tumu", "Tümü")])],
                     wrap=True)
        kontroller = [ust, ft.TextField(label="Ara (no, konu, müşteri)", value=self.s_ara, prefix_icon=ft.Icons.SEARCH, dense=True,
                                        on_submit=ara),
                      ft.Text(f"{len(v['siparisler'])} iş • Toplam {para(v['toplam'])} TL", color=ft.Colors.GREY_700)]
        for s in v["siparisler"]:
            async def ac(e, sid=s["id"]):
                await self.siparis_detay(sid)
            kontroller.append(ft.Card(content=ft.ListTile(
                title=ft.Text(f"{s['siparis_no']} • {s.get('konu') or ''}", weight=ft.FontWeight.BOLD),
                subtitle=ft.Text(f"{s.get('unvan') or ''} • {s.get('bolum_ad') or ''}\n{para(s['sozlesme_bedeli'])} TL • "
                                 f"{s['durum']} • Onay: {s['onay']}"),
                is_three_line=True, on_click=ac, trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT))))
        if not v["siparisler"]:
            kontroller.append(ft.Text("Kayıt bulunamadı."))
        self.govde.content = self.liste(kontroller)
        if v["yazabilir"]:
            self.ana.floating_action_button = ft.FloatingActionButton(icon=ft.Icons.ADD, tooltip="Yeni iş talebi",
                                                                      on_click=self.is_talebi_formu)

    async def siparis_detay(self, sid: int):
        s = await self.cagir(self.api.get, f"/siparisler/{sid}")
        if s is None:
            return

        async def onay(e):
            await self.onay_detay("Sipariş", sid)
        kontroller = self._siparis_kontrolleri(s)
        kontroller.insert(0, satir("Onay", s.get("onay"), True))
        if self.modul("onay") or self.modul("siparis"):
            kontroller.append(ft.FilledButton("Onay işlemleri", icon=ft.Icons.TASK_ALT, on_click=onay, height=46))
        self.ac(self.gorunum(s["siparis_no"], kontroller))

    async def is_talebi_formu(self, e=None):
        sec = await self.cagir(self.api.get, "/secenekler/siparis")
        if sec is None:
            return
        urunler = {str(u["id"]): u for u in sec["urunler"]}
        cari = ft.Dropdown(label="Müşteri (iş sahibi)", editable=True, enable_filter=True, expand=True,
                           options=[secenek(c["id"], c["unvan"]) for c in sec["cariler"]])
        bolum = ft.Dropdown(label="Bölüm / atölye", expand=True, options=[secenek(b["id"], b["ad"]) for b in sec["bolumler"]],
                            value=str(sec["bolumler"][0]["id"]) if len(sec["bolumler"]) == 1 else None)
        konu = ft.TextField(label="İşin konusu", hint_text="Boş bırakılırsa ilk ürünün adı yazılır")
        esas = ft.Dropdown(label="Ücret esası", value=sec["ucret_esaslari"][0], expand=True,
                           options=[secenek(x, x) for x in sec["ucret_esaslari"]])
        teslim = ft.TextField(label="Teslim tarihi", hint_text="GG.AA.YYYY", keyboard_type=ft.KeyboardType.DATETIME)
        aciklama = ft.TextField(label="Açıklama", multiline=True, min_lines=2)
        toplam = ft.Text(weight=ft.FontWeight.BOLD)
        kalem_kutusu = ft.Column(spacing=8)
        kalemler: list[dict] = []

        def hesapla(e=None):
            t = 0.0
            for k in kalemler:
                try:
                    u = urunler.get(k["urun"].value or "")
                    fiyat = sayi(k["fiyat"].value) if (k["fiyat"].value or "").strip() else (u or {}).get("satis_fiyati") or 0
                    t += (sayi(k["miktar"].value) or 0) * fiyat * (1 - (sayi(k["isk"].value) or 0) / 100)
                except ValueError:
                    pass
            toplam.value = f"Tahmini bedel (KDV hariç): {para(t)} TL"
            self.page.update()

        def kalem_ekle(e=None):
            urun = ft.Dropdown(label="Ürün / hizmet", editable=True, enable_filter=True, expand=True,
                               options=[secenek(u["id"], u["ad"]) for u in sec["urunler"]])
            miktar = ft.TextField(label="Miktar", value="1", width=90, keyboard_type=ft.KeyboardType.NUMBER, on_change=hesapla)
            fiyat = ft.TextField(label="Birim fiyat", width=120, keyboard_type=ft.KeyboardType.NUMBER, on_change=hesapla,
                                 hint_text="tespit fiyatı")
            isk = ft.TextField(label="İsk. %", width=80, keyboard_type=ft.KeyboardType.NUMBER, on_change=hesapla)
            k = {"urun": urun, "miktar": miktar, "fiyat": fiyat, "isk": isk}

            def urun_secildi(e):
                u = urunler.get(urun.value or "")
                fiyat.hint_text = f"{para(u['satis_fiyati'])}" if u else "tespit fiyatı"
                hesapla()
            urun.on_select = urun_secildi

            def sil(e):
                kalemler.remove(k)
                kalem_kutusu.controls.remove(k["kutu"])
                hesapla()
            k["kutu"] = ft.Container(ft.Column([ft.Row([urun, ft.IconButton(ft.Icons.DELETE_OUTLINE, on_click=sil, tooltip="Kalemi sil")]),
                                                ft.Row([miktar, fiyat, isk], wrap=True)], spacing=6),
                                     padding=8, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=10)
            kalemler.append(k)
            kalem_kutusu.controls.append(k["kutu"])
            self.page.update()

        async def kaydet(e):
            try:
                veri = {"cari_id": int(cari.value) if cari.value else None, "bolum_id": int(bolum.value) if bolum.value else None,
                        "konu": konu.value or "", "ucret_esasi": esas.value, "teslim_tarihi": iso_tarih(teslim.value, "Teslim tarihi"),
                        "aciklama": aciklama.value or "", "kalemler": []}
                for i, k in enumerate(kalemler, 1):
                    if not k["urun"].value:
                        raise ValueError(f"{i}. kalemde ürün seçiniz.")
                    veri["kalemler"].append({"urun_id": int(k["urun"].value), "miktar": sayi(k["miktar"].value, f"{i}. kalem miktarı") or 0,
                                             "birim_fiyat": sayi(k["fiyat"].value, f"{i}. kalem fiyatı"),
                                             "iskonto_orani": (sayi(k["isk"].value, f"{i}. kalem iskontosu") or 0) / 100})
            except ValueError as h:
                self.bilgi("Eksik veya hatalı bilgi", str(h))
                return
            y = await self.cagir(self.api.post, "/siparisler", veri)
            if y is None:
                return

            async def sonra():
                self.geri()
                await self.sekme_yenile()
            metin = (f"{y['siparis_no']} numaralı iş talebi 'Teklif' olarak kaydedildi. Malzeme maliyet kartından, işçilik yasal "
                     "üst sınırdan hesaplandı. Fiyat ve sözleşme kontrolünden sonra onaya gönderilir.")
            if y["uyarilar"]:
                metin += "\n\nDikkat:\n• " + "\n• ".join(y["uyarilar"])
            self.bilgi("İş talebi kaydedildi", metin, sonra)

        kalem_ekle()
        hesapla()
        self.ac(self.gorunum("Yeni iş talebi", [
            mesaj_kutusu(["İş talebi 'Teklif' durumunda kaydedilir. Kâr, faaliyet gideri, öğrenci hakkı ve işçilik mevzuattaki "
                          "oranlarla program tarafından hesaplanır."], "bilgi"),
            ft.Row([cari]), ft.Row([bolum]), konu, ft.Row([esas]), teslim, baslik("Kalemler"), kalem_kutusu,
            ft.TextButton("Kalem ekle", icon=ft.Icons.ADD, on_click=kalem_ekle), toplam, aciklama,
            ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, on_click=kaydet, height=48)]))

    # ------------------------------------------------------------ fazla çalışma
    async def fazla_sekmesi(self):
        v = await self.cagir(self.api.get, "/fazla-calisma", yil=self.yil, ay=self.ay)
        if v is None:
            return
        self.fc_surum = v["surum"]
        t = v["toplam"]
        kontroller = [ft.Row([self._ay_secici(self.sekme_yenile), self._yil_secici(self.sekme_yenile)], wrap=True),
                      kart(satir("Toplam saat", f"{t['saat']:g}"), satir("Toplam brüt", para(t["brut"]) + " TL"),
                           satir("Toplam net", para(t["net"]) + " TL", True))]
        for f in v["kayitlar"]:
            duzenlenebilir = v["yazabilir"] and f["durum"] != "Onaylandı" and not str(f["onay"]).startswith("Bekliyor")

            async def ac(e, f=f, d=duzenlenebilir):
                if d:
                    await self.fazla_formu(f)
                else:
                    await self.onay_detay("Fazla Çalışma", f["id"])

            async def onay(e, fid=f["id"]):
                await self.onay_detay("Fazla Çalışma", fid)
            kontroller.append(ft.Card(content=ft.ListTile(
                title=ft.Text(f["ad_soyad"], weight=ft.FontWeight.BOLD),
                subtitle=ft.Text(f"{f['saat']:g} saat • Brüt {para(f['brut'])} • Net {para(f['net'])} TL\n"
                                 f"{f.get('siparis_no') or 'Siparişsiz'} • {f['onay']}"),
                is_three_line=True, on_click=ac,
                trailing=ft.IconButton(ft.Icons.FACT_CHECK_OUTLINED, tooltip="Onay durumu", on_click=onay))))
        if not v["kayitlar"]:
            kontroller.append(ft.Text(f"{AYLAR[self.ay - 1]} {self.yil} için fazla çalışma kaydı yok."))
        self.govde.content = self.liste(kontroller)
        if v["yazabilir"]:
            self.ana.floating_action_button = ft.FloatingActionButton(icon=ft.Icons.ADD, tooltip="Fazla çalışma ekle",
                                                                      on_click=lambda e: self.page.run_task(self.fazla_formu))

    async def fazla_formu(self, kayit: dict | None = None):
        yil, ay = (kayit["yil"], kayit["ay"]) if kayit else (self.yil, self.ay)
        sec = await self.cagir(self.api.get, "/fazla-calisma/secenekler", yil=yil, ay=ay)
        if sec is None:
            return
        puantaj = json.loads(kayit["puantaj"]) if kayit and kayit.get("puantaj") else {}
        personel = ft.Dropdown(label="Personel", expand=True, options=[secenek(p["id"], p["ad_soyad"]) for p in sec["personeller"]],
                               value=str(kayit["personel_id"]) if kayit else (str(sec["personeller"][0]["id"]) if len(sec["personeller"]) == 1 else None))
        siparis = ft.Dropdown(label="Sipariş (varsa)", expand=True, editable=True, enable_filter=True,
                              options=[secenek("", "Siparişsiz")] + [secenek(s["id"], f"{s['siparis_no']} - {s.get('konu') or ''}")
                                                                     for s in sec["siparisler"]],
                              value=str(kayit["siparis_id"]) if kayit and kayit.get("siparis_id") else "")
        aciklama = ft.TextField(label="Yapılan iş / açıklama", multiline=True, min_lines=2, value=(kayit or {}).get("aciklama") or "")
        toplam = ft.Text(weight=ft.FontWeight.BOLD)
        sonuc = ft.Column(spacing=8)
        alanlar: dict[int, ft.TextField] = {}

        def topla(e=None):
            s = 0.0
            for a in alanlar.values():
                try:
                    s += sayi(a.value) or 0
                except ValueError:
                    pass
            toplam.value = f"Toplam: {s:g} saat (aylık azami {sec['azami_aylik_saat']:g}) • Saat ücreti {para(sec['saat_ucreti'])} TL"
            self.page.update()

        gun_satirlari = []
        for g in sec["gunler"]:
            alan = ft.TextField(width=90, dense=True, keyboard_type=ft.KeyboardType.NUMBER, on_change=topla,
                                value=f"{puantaj.get(str(g['gun'])):g}" if puantaj.get(str(g["gun"])) else "",
                                disabled=not g["azami"], hint_text=f"≤{g['azami']:g}" if g["azami"] else "—")
            alanlar[g["gun"]] = alan
            gun_satirlari.append(ft.Row([ft.Text(f"{g['gun']:02d} {g['hafta_gunu']}", width=70, weight=ft.FontWeight.BOLD),
                                         ft.Text(g["tur_adi"], color=GUN_RENK.get(g["tur"]), expand=True), alan]))

        def veri(onizleme: bool) -> dict:
            p = {}
            for g, a in alanlar.items():
                s = sayi(a.value, f"{g}. gün saati")
                if s:
                    p[str(g)] = s
            return {"yil": yil, "ay": ay, "personel_id": int(personel.value) if personel.value else None,
                    "siparis_id": int(siparis.value) if siparis.value else None, "puantaj": p, "saat": sum(p.values()),
                    "aciklama": aciklama.value or "", "onizleme": onizleme, "surum": self.fc_surum if kayit else None}

        async def gonder(onizleme: bool):
            try:
                v = veri(onizleme)
            except ValueError as h:
                self.bilgi("Hatalı bilgi", str(h))
                return None
            if kayit:
                return await self.cagir(self.api.put, f"/fazla-calisma/{kayit['id']}", v)
            return await self.cagir(self.api.post, "/fazla-calisma", v)

        async def hesapla(e=None):
            y = await gonder(True)
            if y is None:
                return
            k = y["kayit"]
            sonuc.controls = [kart(satir("Saat", f"{k['saat']:g}"), satir("Brüt", para(k["brut"]) + " TL", True),
                                   satir("Önceki kümülatif matrah", para(k["onceki_kumulatif"]) + " TL"),
                                   satir("Gelir vergisi", para(k["gelir_vergisi"]) + " TL"),
                                   satir("Damga vergisi", para(k["damga_vergisi"]) + " TL"),
                                   satir("Net ödenecek", para(k["net"]) + " TL", True, ft.Colors.GREEN_800))]
            if y["hatalar"]:
                sonuc.controls.append(mesaj_kutusu(y["hatalar"], "hata"))
            if y["uyarilar"]:
                sonuc.controls.append(mesaj_kutusu(y["uyarilar"], "uyari"))
            if not y["hatalar"]:
                sonuc.controls.append(mesaj_kutusu(["Mevzuat kontrolünden geçti; kaydedebilirsiniz."], "bilgi"))
            self.page.update()

        async def kaydet(onaya: bool):
            y = await gonder(False)
            if y is None:
                return
            fid = y["id"]
            mesaj = "Fazla çalışma kaydedildi."
            if onaya:
                g = await self.cagir(self.api.post, Istemci.yol("onay", "Fazla Çalışma", fid, "gonder"), {"aciklama": "Mobilden gönderildi"})
                if g is not None:
                    mesaj = f"Kaydedildi ve onaya gönderildi. Durum: {g['durum_metni']}"
            if y.get("uyarilar"):
                mesaj += " Uyarılar: " + " ".join(y["uyarilar"])
            self.bildir(mesaj)
            self.geri()
            await self.sekme_yenile()

        async def sil():
            if await self.cagir(self.api.delete, f"/fazla-calisma/{kayit['id']}", surum=self.fc_surum) is None:
                return
            self.bildir("Kayıt silindi.")
            self.geri()
            await self.sekme_yenile()

        butonlar = [ft.OutlinedButton("Hesapla ve kontrol et", icon=ft.Icons.CALCULATE, on_click=hesapla, height=46),
                    ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, on_click=lambda e: self.page.run_task(kaydet, False), height=46)]
        if self.ben.get("onay_akisi"):
            butonlar.append(ft.FilledButton("Kaydet ve onaya gönder", icon=ft.Icons.SEND, height=46,
                                            on_click=lambda e: self.page.run_task(kaydet, True)))
        if kayit:
            butonlar.append(ft.TextButton("Kaydı sil", icon=ft.Icons.DELETE_OUTLINE, style=ft.ButtonStyle(color=ft.Colors.RED_700),
                                          on_click=lambda e: self.sor("Kaydı sil", "Fazla çalışma kaydı silinsin mi?", sil, "Sil")))
        topla()
        self.ac(self.gorunum(f"Fazla çalışma — {AYLAR[ay - 1]} {yil}", [
            mesaj_kutusu(["Her gün için ders saatleri dışında fiilen çalışılan saati yazınız. Gün türüne göre azami süreler "
                          "ve aylık sınır program tarafından denetlenir; ücret ve vergiler otomatik hesaplanır."], "bilgi"),
            ft.Row([personel]), ft.Row([siparis]), baslik("Puantaj"), toplam, *gun_satirlari, aciklama, sonuc,
            ft.Column(butonlar, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, spacing=8)]))

    # ------------------------------------------------------------ diğer
    async def diger_sekmesi(self):
        def oge(ikon, metin, alt, islev):
            return ft.Card(content=ft.ListTile(leading=ft.Icon(ikon, color=ft.Colors.TEAL_700), title=ft.Text(metin),
                                               subtitle=ft.Text(alt) if alt else None, trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                                               on_click=islev))
        k = self.ben.get("kullanici") or {}
        kontroller = [kart(ft.Text(k.get("ad_soyad") or k.get("kullanici_adi") or "", size=17, weight=ft.FontWeight.BOLD),
                           ft.Text(k.get("rol") or ""), ft.Text(k.get("rol_aciklamasi") or "", size=12, color=ft.Colors.GREY_700),
                           ft.Text(self.ben.get("lisans") or "", size=12, color=ft.Colors.GREY_700))]
        if self.modul("stok"):
            kontroller.append(oge(ft.Icons.INVENTORY_2, "Stok durumu", "Malzeme bakiyeleri ve kritik stok", lambda e: self.page.run_task(self.stok_ekrani)))
        if self.modul("kasa"):
            kontroller.append(oge(ft.Icons.ACCOUNT_BALANCE_WALLET, "Kasa / banka", "Bakiyeler ve hareketler", lambda e: self.page.run_task(self.kasa_ekrani)))
        if self.modul("satis"):
            kontroller.append(oge(ft.Icons.RECEIPT_LONG, "Satış faturaları", "Kesilen faturalar ve tahsilat durumu",
                                  lambda e: self.page.run_task(self.fatura_ekrani, "Satış")))
        if self.modul("alis"):
            kontroller.append(oge(ft.Icons.SHOPPING_CART, "Alış / gider belgeleri", "Alış faturaları, müstahsil makbuzları",
                                  lambda e: self.page.run_task(self.fatura_ekrani, "Alış")))
        if self.modul("islem"):
            kontroller.append(oge(ft.Icons.MANAGE_SEARCH, "İşlem kaydı", "Kim, ne zaman, hangi cihazdan ne yaptı",
                                  lambda e: self.page.run_task(self.islem_kaydi_ekrani)))
        if self.modul("denetim"):
            kontroller.append(oge(ft.Icons.FACT_CHECK_OUTLINED, "Denetim formu",
                                  "Rehber kontrol listesi, ortak çalışma ve rapor",
                                  lambda e: self.page.run_task(self.denetim_listesi)))
        kk = self.ben.get("kurum_kodu") or ""
        kontroller += [oge(ft.Icons.PASSWORD, "Şifre değiştir", None, lambda e: self.sifre_ekrani()),
                       oge(ft.Icons.INFO_OUTLINE, "Hakkında", None, lambda e: self.bilgi(
                           "DÖSE Yönetim Mobil",
                           f"Sürüm {SURUM}\nKurum kodu: {kk or '—'}\nKurum: {self.ben.get('kurum') or '—'}\n\n"
                           f"Geliştiren, satan ve destek veren: {SATICI}\n\n"
                           "Aynı kurum kodu, kullanıcı adı ve şifre ile okul içinden veya internet üzerinden "
                           "(geçit / VPN / HTTPS) işlem yapabilirsiniz. Her işlem kullanıcı, rol, cihaz ve zaman "
                           "bilgisiyle işlem kaydına yazılır.")),
                       oge(ft.Icons.LOGOUT, "Çıkış", None, self.cikis)]
        self.govde.content = self.liste(kontroller)

    async def denetim_listesi(self):
        sonuc = await self.cagir(self.api.get, "/denetimler")
        if sonuc is None:
            return
        kontroller = [
            mesaj_kutusu(["Rehber maddeleri görev alanlarına göre farklı rollerce doldurulur. "
                          "Her madde için sonuç ve açıklama/kanıt kaydedilir; değişiklikler diğer kullanıcılara eşitlenir."],
                         "bilgi")
        ]
        if self.modul("denetim") == "y":
            kontroller.append(ft.FilledButton("Yeni denetim başlat", icon=ft.Icons.ADD,
                                              on_click=lambda e: self.page.run_task(self.denetim_yeni_formu)))
        for kayit in sonuc["denetimler"]:
            async def ac(e, denetim_id=kayit["id"]):
                await self.denetim_detay(denetim_id)
            toplam = kayit["madde_sayisi"] or 0
            tamam = kayit["degerlendirilen"] or 0
            kontroller.append(ft.Card(content=ft.ListTile(
                leading=ft.Icon(ft.Icons.FACT_CHECK_OUTLINED, color=ft.Colors.TEAL_700),
                title=ft.Text(kayit["baslik"], weight=ft.FontWeight.BOLD),
                subtitle=ft.Text(f"{kayit['durum']} • {tamam}/{toplam} madde değerlendirildi"
                                 + (f"\nSon işlem: {kayit.get('guncelleyen') or '-'}" if kayit.get("guncelleme") else "")),
                is_three_line=True, trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT), on_click=ac)))
        if not sonuc["denetimler"]:
            kontroller.append(ft.Text("Henüz denetim formu oluşturulmadı."))
        self.ac(self.gorunum("Denetim formları", kontroller))

    async def denetim_yeni_formu(self):
        baslik_alani = ft.TextField(label="Denetim başlığı", value=f"{date.today().year} Rehberlik ve Denetim Raporu")
        il = ft.TextField(label="İl")
        ilce = ft.TextField(label="İlçe")
        okul = ft.TextField(label="Okul adı", value=self.ben.get("kurum") or "")
        kod = ft.TextField(label="Kurum kodu", value=self.ben.get("kurum_kodu") or "")
        baslangic = ft.TextField(label="Denetim başlangıç tarihi (GG.AA.YYYY)")
        bitis = ft.TextField(label="Denetim bitiş tarihi (GG.AA.YYYY)")

        async def kaydet(e):
            baslik_metni = (baslik_alani.value or "").strip()
            if not baslik_metni:
                self.bilgi("Eksik bilgi", "Denetim başlığını giriniz.")
                return
            bilgiler = {
                "il": (il.value or "").strip(), "ilce": (ilce.value or "").strip(),
                "okul_adi": (okul.value or "").strip(), "kurum_kodu": (kod.value or "").strip(),
                "denetim_baslangic": (baslangic.value or "").strip(), "denetim_bitis": (bitis.value or "").strip(),
            }
            sonuc = await self.cagir(self.api.post, "/denetimler", {"baslik": baslik_metni, "bilgiler": bilgiler})
            if sonuc is None:
                return
            self.geri()
            await self.denetim_detay(sonuc["id"])

        self.ac(self.gorunum("Yeni denetim", [
            mesaj_kutusu(["Formu okul yöneticisi başlatır. Kontrol maddelerini alanlarına göre yetkili kullanıcılar "
                          "eş zamanlı doldurabilir."], "bilgi"),
            baslik_alani, okul, il, ilce, kod, baslangic, bitis,
            ft.FilledButton("Formu oluştur", icon=ft.Icons.SAVE, on_click=kaydet, height=48),
        ]))

    async def denetim_detay(self, denetim_id: int):
        kayit = await self.cagir(self.api.get, f"/denetimler/{denetim_id}")
        if kayit is None:
            return
        tum_maddeler = kayit["maddeler"]
        degerlendirilen = sum(m["durum"] != "Değerlendirilmedi" for m in tum_maddeler)
        gruplar = {}
        for madde in tum_maddeler:
            gruplar.setdefault((madde["bolum"], madde["baslik"]), []).append(madde)
        secimler = [ft.DropdownOption(key=k[0], text=f"{k[0]} {k[1]}") for k in gruplar]
        bolum = ft.Dropdown(label="Denetim alanı", value=secimler[0].key if secimler else None,
                            options=secimler, expand=True)
        govde = ft.Column(spacing=8)

        def bolum_goster(e=None):
            secili = bolum.value
            for (kod, baslik_metni), maddeler in gruplar.items():
                if kod != secili:
                    continue
                govde.controls = [baslik(f"{kod} {baslik_metni}")]
                for madde in maddeler:
                    sonuc = ft.Dropdown(
                        label="Değerlendirme", value=madde["durum"], expand=True,
                        options=[secenek(x, x) for x in ("Değerlendirilmedi", "Uygun", "Eksik", "Uygulanamaz")],
                        disabled=not madde["yazabilir"],
                    )
                    aciklama = ft.TextField(label="Açıklama / kanıt", value=madde["aciklama"], multiline=True,
                                            min_lines=1, max_lines=4, disabled=not madde["yazabilir"])

                    async def kaydet(e, m=madde, durum=sonuc, not_=aciklama):
                        y = await self.cagir(self.api.put,
                                             f"/denetimler/{denetim_id}/maddeler/{m['kod']}",
                                             {"surum": m["surum"], "durum": durum.value or "Değerlendirilmedi",
                                              "aciklama": not_.value or ""})
                        if y is None:
                            return
                        m["surum"] = y["surum"]
                        m["durum"] = durum.value or "Değerlendirilmedi"
                        m["aciklama"] = not_.value or ""
                        self.bildir(f"{m['kod']} maddesi kaydedildi.")

                    govde.controls.append(kart(
                        ft.Text(f"{madde['kod']} — {madde['soru']}", weight=ft.FontWeight.W_500, selectable=True),
                        sonuc, aciklama,
                        *( [ft.FilledButton("Maddeyi kaydet", icon=ft.Icons.SAVE,
                                           on_click=lambda e, fn=kaydet: self.page.run_task(fn, e))]
                           if madde["yazabilir"] else [ft.Text("Bu madde için yalnız görüntüleme yetkiniz var.",
                                                               size=12, color=ft.Colors.GREY_700)])))
            self.page.update()

        bolum.on_select = bolum_goster
        bolum_goster()

        kontroller = [
            kart(ft.Text(kayit["baslik"], size=18, weight=ft.FontWeight.BOLD),
                 satir("Durum", kayit["durum"]), satir("İlerleme", f"{degerlendirilen}/{len(tum_maddeler)} madde"),
                 satir("Son güncelleyen", kayit.get("guncelleyen") or kayit.get("olusturan"))),
            ft.Row([ft.OutlinedButton("Rapor bilgileri", icon=ft.Icons.EDIT,
                                      on_click=lambda e: self.page.run_task(self.denetim_bilgi_formu, kayit))
                    ] if kayit["bilgi_yazabilir"] else []),
            bolum,
            govde,
            *( [ft.OutlinedButton("PDF raporu oluştur", icon=ft.Icons.PICTURE_AS_PDF,
                                  on_click=lambda e: self.page.run_task(self.denetim_pdf, denetim_id))]
               if kayit["rapor_goruntuleyebilir"] else []),
        ]
        self.ac(self.gorunum(f"Denetim #{denetim_id}", kontroller))

    async def denetim_bilgi_formu(self, kayit: dict):
        alan_etiketleri = {
            "il": "İl", "ilce": "İlçe", "okul_adi": "Okul adı", "kurum_kodu": "Kurum kodu",
            "telefon_faks": "Telefon / faks", "alan_dallar": "Öğretim yapılan alan ve dallar",
            "isletme_acilis_tarihi": "İşletmenin açılış tarihi", "faaliyet_alani": "Faaliyet alanı",
            "makine_techizat": "Kullanılan makine ve teçhizat", "son_denetim_tarihi": "Son denetim tarihi",
            "denetim_baslangic": "Denetim başlangıç tarihi", "denetim_bitis": "Denetim bitiş tarihi",
            "yonetici_kadin": "Yönetici sayısı — kadın", "yonetici_erkek": "Yönetici sayısı — erkek",
            "sef_kadin": "Alan/atölye şefi sayısı — kadın", "sef_erkek": "Alan/atölye şefi sayısı — erkek",
            "ogretmen_kadin": "Öğretmen sayısı — kadın", "ogretmen_erkek": "Öğretmen sayısı — erkek",
            "diger_personel_kadin": "Diğer personel sayısı — kadın",
            "diger_personel_erkek": "Diğer personel sayısı — erkek",
            "ogrenci_kadin": "Öğrenci sayısı — kadın", "ogrenci_erkek": "Öğrenci sayısı — erkek",
            "giris": "1. Giriş", "hizmet_ortami_bulgulari": "2. Hizmet ortamları — bulgular",
            "hizmet_ortami_onerileri": "2. Hizmet ortamları — çözüm önerileri",
            "egitim_bulgulari": "3. Eğitim-öğretim faaliyetleri — bulgular",
            "egitim_onerileri": "3. Eğitim-öğretim faaliyetleri — çözüm önerileri",
            "yonetim_bulgulari": "4. Yönetim faaliyetleri — bulgular",
            "yonetim_onerileri": "4. Yönetim faaliyetleri — çözüm önerileri",
            "mali_bulgular": "5. Mali iş ve işlemler — bulgular",
            "mali_oneriler": "5. Mali iş ve işlemler — çözüm önerileri",
            "il_mudurlugune_oneriler": "İl/ilçe millî eğitim müdürlüğüne öneriler",
            "sonuc_ve_genel_oneriler": "7. Sonuç ve genel öneriler",
            "yonetici_bilgileri": "Değerlendirilen yöneticiler",
        }
        alanlar = {}
        for anahtar, etiket in alan_etiketleri.items():
            cok_satir = anahtar in {
                "makine_techizat", "faaliyet_alani", "giris", "hizmet_ortami_bulgulari",
                "hizmet_ortami_onerileri", "egitim_bulgulari", "egitim_onerileri",
                "yonetim_bulgulari", "yonetim_onerileri", "mali_bulgular", "mali_oneriler",
                "il_mudurlugune_oneriler", "sonuc_ve_genel_oneriler", "yonetici_bilgileri",
            }
            alanlar[anahtar] = ft.TextField(label=etiket, value=kayit["bilgiler"].get(anahtar) or "",
                                            multiline=cok_satir, min_lines=2 if cok_satir else 1,
                                            max_lines=6 if cok_satir else 1)
        baslik_alani = ft.TextField(label="Rapor başlığı", value=kayit["baslik"])
        durum = ft.Dropdown(label="Rapor durumu", value=kayit["durum"],
                            options=[secenek(x, x) for x in ("Taslak", "Tamamlandı")])

        async def kaydet(e):
            veri = {"surum": kayit["surum"], "baslik": baslik_alani.value or "",
                    "durum": durum.value or "Taslak",
                    "bilgiler": {k: v.value or "" for k, v in alanlar.items()}}
            sonuc = await self.cagir(self.api.put, f"/denetimler/{kayit['id']}", veri)
            if sonuc is None:
                return
            self.geri()
            await self.denetim_detay(kayit["id"])

        self.ac(self.gorunum("Rapor bilgileri", [
            mesaj_kutusu(["Formu yalnızca okul yöneticileri güncelleyebilir. Tamamlandı durumu için tüm kontrol "
                          "maddeleri değerlendirilmiş olmalıdır."], "bilgi"),
            baslik_alani, *alanlar.values(), durum,
            ft.FilledButton("Rapor bilgilerini kaydet", icon=ft.Icons.SAVE, on_click=kaydet, height=48),
        ]))

    async def denetim_pdf(self, denetim_id: int):
        sonuc = await self.cagir(self.api.get, f"/denetimler/{denetim_id}/rapor")
        if sonuc is None:
            return
        picker = ft.FilePicker()
        self.page.overlay.append(picker)
        self.page.update()
        try:
            yol = await picker.save_file(dialog_title="Denetim raporunu kaydet",
                                         file_name=sonuc["dosya_adi"], src_bytes=base64.b64decode(sonuc["icerik"]))
            if yol:
                self.bildir(f"PDF raporu kaydedildi: {yol}")
        finally:
            self.page.overlay.remove(picker)
            self.page.update()

    async def stok_ekrani(self):
        v = await self.cagir(self.api.get, "/stok")
        if v is None:
            return
        kontroller = [kart(satir("Toplam stok değeri", para(v["toplam"]) + " TL", True),
                           satir("Kritik seviyedeki malzeme", sum(1 for m in v["malzemeler"] if m["kritik"])))]
        for m in sorted(v["malzemeler"], key=lambda m: (not (m["kritik"] or m["kalan"] < 0), m["ad"])):
            renk = ft.Colors.RED_700 if m["kalan"] < 0 or m["kritik"] else None
            kontroller.append(ft.Card(content=ft.ListTile(
                leading=ft.Icon(ft.Icons.WARNING_AMBER if renk else ft.Icons.INVENTORY_2, color=renk or ft.Colors.TEAL_700),
                title=ft.Text(m["ad"], weight=ft.FontWeight.BOLD),
                subtitle=ft.Text(f"Kalan {m['kalan']:g} {m.get('birim') or ''}"
                                 + (f" (kritik {m['kritik_stok']:g})" if m.get("kritik_stok") else "")
                                 + f" • Ort. {para(m['ortalama_maliyet'])} TL", color=renk),
                trailing=ft.Text(para(m["tutar"]) + " TL"))))
        self.ac(self.gorunum("Stok durumu", kontroller))

    async def kasa_ekrani(self, ay: int | None = None):
        ay = self.ay if ay is None else ay
        v = await self.cagir(self.api.get, "/kasa", yil=self.yil, ay=ay)
        if v is None:
            return

        async def ay_sec(e):
            self.geri()
            await self.kasa_ekrani(int(e.control.value))
        kontroller = [ft.Dropdown(label="Dönem", value=str(ay), width=160, dense=True, on_select=ay_sec,
                                  options=[secenek(0, f"{self.yil} tüm yıl")] + [secenek(i + 1, a) for i, a in enumerate(AYLAR)]),
                      kart(satir("Kasa (100) bakiyesi", para(v["kasa"]) + " TL", True),
                           satir("Banka (102) bakiyesi", para(v["banka"]) + " TL", True),
                           satir("Dönem girişleri", para(v["giris"]) + " TL", renk=ft.Colors.GREEN_800),
                           satir("Dönem çıkışları", para(v["cikis"]) + " TL", renk=ft.Colors.RED_700))]
        for h in v["hareketler"]:
            giris = h["yon"] == "Giriş"
            kontroller.append(ft.Card(content=ft.ListTile(
                leading=ft.Icon(ft.Icons.SOUTH_WEST if giris else ft.Icons.NORTH_EAST,
                                color=ft.Colors.GREEN_700 if giris else ft.Colors.RED_700),
                title=ft.Text(f"{h['tur']} • {h.get('unvan') or h.get('aciklama') or ''}"),
                subtitle=ft.Text(f"{tarih(h['tarih'])} • {h['hesap']}" + (f" • {h['fatura_no']}" if h.get("fatura_no") else "")),
                trailing=ft.Text(("+" if giris else "−") + para(h["tutar"]), weight=ft.FontWeight.BOLD,
                                 color=ft.Colors.GREEN_800 if giris else ft.Colors.RED_700))))
        if not v["hareketler"]:
            kontroller.append(ft.Text("Bu dönemde hareket yok."))
        self.ac(self.gorunum("Kasa / banka", kontroller))

    async def fatura_ekrani(self, tur: str, ay: int = 0):
        v = await self.cagir(self.api.get, "/faturalar", tur=tur, yil=self.yil, ay=ay)
        if v is None:
            return

        async def ay_sec(e):
            self.geri()
            await self.fatura_ekrani(tur, int(e.control.value))
        kontroller = [ft.Dropdown(label="Dönem", value=str(ay), width=160, dense=True, on_select=ay_sec,
                                  options=[secenek(0, f"{self.yil} tüm yıl")] + [secenek(i + 1, a) for i, a in enumerate(AYLAR)]),
                      kart(satir("Belge sayısı", len([f for f in v["faturalar"] if not f["iptal"]])),
                           satir("Matrah", para(v["matrah"]) + " TL"), satir("KDV", para(v["kdv"]) + " TL"),
                           satir("Açık bakiye", para(v["acik_bakiye"]) + " TL", True))]
        for f in v["faturalar"]:
            renk = ft.Colors.GREY_500 if f["iptal"] else (ft.Colors.ORANGE_800 if f["durum"] == "Açık" else ft.Colors.GREEN_800)
            kontroller.append(ft.Card(content=ft.ListTile(
                title=ft.Text(f"{f.get('belge_no') or '-'} • {f.get('unvan') or ''}", weight=ft.FontWeight.BOLD),
                subtitle=ft.Text(f"{tarih(f['tarih'])} • {f.get('belge_turu') or ''}\nKalan {para(f['kalan'])} TL • {f['durum']}",
                                 color=renk if f["iptal"] else None),
                is_three_line=True, trailing=ft.Text(para(f["genel_toplam"]), weight=ft.FontWeight.BOLD, color=renk))))
        if not v["faturalar"]:
            kontroller.append(ft.Text("Bu dönemde belge yok."))
        self.ac(self.gorunum("Satış faturaları" if tur == "Satış" else "Alış / gider belgeleri", kontroller))

    async def islem_kaydi_ekrani(self, ara: str = "", istemci: str = ""):
        v = await self.cagir(self.api.get, "/islem-kaydi", ara=ara, istemci=istemci, sinir=300)
        if v is None:
            return

        async def yenile(e=None):
            self.geri()
            await self.islem_kaydi_ekrani(t_ara.value or "", d_kaynak.value or "")
        t_ara = ft.TextField(label="Ara (kullanıcı, kayıt, değişiklik)", value=ara, prefix_icon=ft.Icons.SEARCH, dense=True,
                             on_submit=yenile)
        d_kaynak = ft.Dropdown(label="Kaynak", value=istemci, width=150, dense=True, on_select=yenile,
                               options=[secenek("", "Tümü"), secenek("Masaüstü", "Masaüstü"), secenek("Mobil", "Mobil")])
        kontroller = [t_ara, d_kaynak, ft.Text(f"Son {len(v['kayitlar'])} işlem", color=ft.Colors.GREY_700)]
        for r in v["kayitlar"]:
            async def ac(e, kid=r["id"]):
                await self.islem_ayrinti(kid)
            mobil = r.get("istemci") == "Mobil"
            kontroller.append(ft.Card(content=ft.ListTile(
                leading=ft.Icon(ft.Icons.SMARTPHONE if mobil else ft.Icons.DESKTOP_WINDOWS, color=ft.Colors.TEAL_700),
                title=ft.Text(f"{r.get('kim') or r.get('kullanici')} ({r.get('rol') or '-'})", weight=ft.FontWeight.BOLD),
                subtitle=ft.Text(f"{tarih(r['zaman'])} • {r['islem']} {r.get('kayit_turu') or ''}"
                                 + (f" #{r['kayit_id']}" if r.get("kayit_id") else "") + f"\n{r.get('ozet') or ''}",
                                 max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
                is_three_line=True, on_click=ac)))
        self.ac(self.gorunum("İşlem kaydı", kontroller))

    async def islem_ayrinti(self, kid: int):
        r = await self.cagir(self.api.get, f"/islem-kaydi/{kid}")
        if r is None:
            return
        kontroller = [kart(satir("Zaman", tarih(r["zaman"])), satir("Kullanıcı", f"{r.get('ad_soyad') or ''} ({r.get('kullanici')})"),
                           satir("Rol", r.get("rol")), satir("İşlem", r.get("islem")),
                           satir("Kayıt", f"{r.get('kayit_turu') or ''} #{r.get('kayit_id') or ''}"),
                           satir("Kaynak", r.get("istemci")), satir("Bilgisayar / cihaz", r.get("bilgisayar")),
                           *( [ft.Text(r["detay"], size=12, selectable=True)] if r.get("detay") else []))]
        if r["degisiklikler"]:
            kontroller.append(baslik("Değişiklikler"))
            for d in r["degisiklikler"]:
                kontroller.append(kart(ft.Text(d["alan"], weight=ft.FontWeight.BOLD),
                                       ft.Text(f"Eski: {d['eski']}", color=ft.Colors.RED_700, selectable=True),
                                       ft.Text(f"Yeni: {d['yeni']}", color=ft.Colors.GREEN_800, selectable=True)))
        self.ac(self.gorunum("İşlem ayrıntısı", kontroller))


def calistir(sabit_adres: str | None = None):
    """Flet giriş noktası üretir; sabit_adres verilirse (web sürümü) sunucu adresi sorulmaz."""
    async def main(page: ft.Page):
        await Uygulama(page, sabit_adres).baslat()
    return main
