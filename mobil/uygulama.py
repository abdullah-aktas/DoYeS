"""DÖSE Yönetim Mobil (Flet): Android uygulaması ve web arayüzü.

Telefonda Python uygulamanın içinde çalışır ve okulun DÖSE Mobil Sunucusu'na HTTP ile bağlanır. Web sürümü
sunucunun kendisinde çalışır; tarayıcıya ayrıca bir şey kurulmaz.
"""
from __future__ import annotations

import asyncio
import base64
from html.parser import HTMLParser
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


class _HtmlMetin(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parcalar: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.parcalar.append("\n• ")
        elif tag == "br":
            self.parcalar.append("\n")
        elif tag in {"p", "h1", "h2", "h3", "h4", "tr"}:
            self.parcalar.append("\n\n")

    def handle_endtag(self, tag):
        if tag in {"p", "h1", "h2", "h3", "h4", "li", "tr"}:
            self.parcalar.append("\n")

    def handle_data(self, data):
        self.parcalar.append(data)


def html_metin(html: str) -> str:
    cevirici = _HtmlMetin()
    cevirici.feed(html)
    satirlar = [" ".join(s.split()) for s in "".join(cevirici.parcalar).splitlines()]
    return "\n".join(s for s in satirlar if s).strip()


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
        self._masaustu = False
        self.masaustu_sekmeler: list = []

    # ------------------------------------------------------------ altyapı
    async def baslat(self):
        p = self.page
        p.title = "DÖSE Yönetim Mobil"
        p.theme = ft.Theme(color_scheme_seed=ft.Colors.TEAL)
        p.theme_mode = ft.ThemeMode.LIGHT
        p.bgcolor = ft.Colors.GREY_50
        p.padding = 0
        p.on_view_pop = self._view_pop
        p.on_resize = self._boyut_degisti
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

    def _boyut_degisti(self, e=None):
        if not hasattr(self, "nav") or not hasattr(self, "rail"):
            return
        genis_ekran = (getattr(self.page, "width", None) or 0) >= 840
        if genis_ekran != self._masaustu:
            if genis_ekran:
                aktif = self.sekmeler[self.sekme][0]
                self.rail.selected_index = next(
                    (i for i, sekme in enumerate(self.masaustu_sekmeler) if sekme[0] == aktif),
                    next(i for i, sekme in enumerate(self.masaustu_sekmeler) if sekme[0] == "diger"),
                )
            else:
                aktif = self.masaustu_sekmeler[self.rail.selected_index][0]
                self.sekme = next((i for i, sekme in enumerate(self.sekmeler) if sekme[0] == aktif),
                                  next(i for i, sekme in enumerate(self.sekmeler) if sekme[0] == "diger"))
                self.nav.selected_index = self.sekme
        self._masaustu = genis_ekran
        self.nav.visible = not genis_ekran
        self.rail.visible = genis_ekran
        self.nav_ayrac.visible = genis_ekran
        self.ana.navigation_bar = None if genis_ekran else self.nav
        self.page.update()

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
                    ("fazla", "Fazla Ç.", ft.Icons.SCHEDULE, self.fazla_sekmesi),
                    ("parca_basi", "Parça Başı", ft.Icons.GROUPS, self.parca_basi_sekmesi)]
        self.sekmeler = [t for t in tanimlar if self.modul(t[0])] + [("diger", "Diğer", ft.Icons.MENU, self.diger_sekmesi)]
        masaustu_tanimlari = [
            ("panel", "Genel Bakış", ft.Icons.DASHBOARD_OUTLINED, self.panel_sekmesi),
            ("onay", "Onaylar", ft.Icons.TASK_ALT, self.onay_sekmesi),
            ("siparis", "İş Emirleri", ft.Icons.ASSIGNMENT_OUTLINED, self.siparis_sekmesi),
            ("fazla", "Fazla Çalışma", ft.Icons.SCHEDULE, self.fazla_sekmesi),
            ("parca_basi", "Parça Başı Ücret", ft.Icons.GROUPS, self.parca_basi_sekmesi),
            ("stok", "Stok Durumu", ft.Icons.INVENTORY_2, self.stok_ekrani),
            ("kasa", "Kasa / Banka", ft.Icons.ACCOUNT_BALANCE_WALLET, self.kasa_ekrani),
            ("satis", "Satış Faturaları", ft.Icons.RECEIPT_LONG,
             lambda: self.fatura_ekrani("Satış")),
            ("alis", "Alış / Gider Belgeleri", ft.Icons.SHOPPING_CART,
             lambda: self.fatura_ekrani("Alış")),
            ("denetim", "Denetim Formu", ft.Icons.FACT_CHECK_OUTLINED, self.denetim_listesi),
            ("islem", "İşlem Kaydı", ft.Icons.MANAGE_SEARCH, self.islem_kaydi_ekrani),
            ("bolum", "Bölüm / Atölyeler", ft.Icons.HUB,
             lambda: self.tanim_ekrani("bolum")),
            ("personel", "Personel", ft.Icons.BADGE,
             lambda: self.tanim_ekrani("personel")),
            ("ogrenci", "Öğrenciler", ft.Icons.SCHOOL,
             lambda: self.tanim_ekrani("ogrenci")),
            ("cari", "Cari Hesaplar", ft.Icons.PEOPLE,
             lambda: self.tanim_ekrani("cari")),
            ("malzeme", "Malzeme Kartları", ft.Icons.INVENTORY_2_OUTLINED,
             lambda: self.tanim_ekrani("malzeme")),
            ("urun", "Ürün / Hizmet Kartları", ft.Icons.CATEGORY,
             lambda: self.tanim_ekrani("urun")),
            ("parametre", "Mevzuat Parametreleri", ft.Icons.TUNE,
             self.parametre_ekrani),
            ("rehber", "Mevzuat Rehberi", ft.Icons.MENU_BOOK,
             self.mevzuat_rehberi_ekrani),
            ("kurum", "Kurum ve Görevliler", ft.Icons.ACCOUNT_BALANCE,
             self.kurum_ekrani),
            ("muhasebe", "Yevmiye / Mizan", ft.Icons.ACCOUNT_BALANCE_WALLET,
             lambda: self.muhasebe_ekrani()),
            ("raporlar", "Raporlar", ft.Icons.ANALYTICS,
             lambda: self.rapor_ekrani()),
            ("yukumluluk", "Hazine Payı / SHÇEK", ft.Icons.ACCOUNT_BALANCE,
             lambda: self.hazine_ekrani()),
            ("vergi", "KDV / Muhtasar", ft.Icons.REQUEST_QUOTE,
             lambda: self.vergi_ekrani()),
            ("yil_sonu", "Yıl Sonu Kârı ve ÜTP", ft.Icons.EVENT_AVAILABLE,
             lambda: self.yil_sonu_ekrani()),
            ("belgeler", "Resmi Yazılar / Belgeler", ft.Icons.DESCRIPTION,
             lambda: self.belgeler_ekrani()),
        ]
        self.masaustu_sekmeler = [sekme for sekme in masaustu_tanimlari if self.modul(sekme[0])]
        self.masaustu_sekmeler.append(("diger", "Hesap ve Diğer", ft.Icons.MENU, self.diger_sekmesi))
        bekleyen = ben.get("bekleyen_onay") or 0
        self.nav = ft.NavigationBar(selected_index=0, on_change=self._sekme_degisti, destinations=[
            ft.NavigationBarDestination(icon=ikon, label=etiket, badge=str(bekleyen) if a == "onay" and bekleyen else None)
            for a, etiket, ikon, _ in self.sekmeler],
            bgcolor=ft.Colors.WHITE, indicator_color=ft.Colors.TEAL_50, elevation=2)
        self.rail = ft.NavigationRail(selected_index=0, on_change=self._masaustu_sekme_degisti, extended=True,
                                      destinations=[
                                          ft.NavigationRailDestination(
                                              icon=ikon, label=etiket,
                                              badge=str(bekleyen) if a == "onay" and bekleyen else None)
                                          for a, etiket, ikon, _ in self.masaustu_sekmeler],
                                      bgcolor=ft.Colors.WHITE, indicator_color=ft.Colors.TEAL_50,
                                      min_extended_width=220, scrollable=True, expand=True)
        self.nav_ayrac = ft.VerticalDivider(width=1, color=ft.Colors.GREY_200)
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
                           controls=[ft.SafeArea(ft.Row([self.rail, self.nav_ayrac, self.govde],
                                                        spacing=0, expand=True), expand=True)])
        self.ana.data = {"halka": self.halka}
        self.page.views.clear()
        self.page.views.append(self.ana)
        self.sekme = 0
        self._boyut_degisti()
        if ben.get("salt_okunur"):
            self.bildir(ben.get("lisans") or "Program salt okunur çalışıyor.")
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
        self.ana.floating_action_button = None
        aktif = self.sekmeler[self.sekme][0]
        self.rail.selected_index = next(
            (i for i, sekme in enumerate(self.masaustu_sekmeler) if sekme[0] == aktif),
            next(i for i, sekme in enumerate(self.masaustu_sekmeler) if sekme[0] == "diger"),
        )
        await self.sekmeler[self.sekme][3]()
        self.page.update()

    async def _masaustu_sekme_degisti(self, e):
        i = e.control.selected_index
        self.ana.floating_action_button = None
        self.sekme = next((n for n, sekme in enumerate(self.sekmeler)
                           if sekme[0] == self.masaustu_sekmeler[i][0]),
                          next(n for n, sekme in enumerate(self.sekmeler) if sekme[0] == "diger"))
        self.nav.selected_index = self.sekme
        await self.masaustu_sekmeler[i][3]()
        self.page.update()

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
                self.rail.selected_index = i
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

    # ------------------------------------------------------------ parça başı
    async def parca_basi_sekmesi(self):
        if not hasattr(self, "pb_ay"):
            self.pb_ay = self.ay
        v = await self.cagir(self.api.get, "/parca-basi", yil=self.yil, ay=self.pb_ay)
        if v is None:
            return
        kontroller = [
            ft.Row([self._yil_secici(self.parca_basi_sekmesi),
                    ft.Dropdown(label="Ay", value=str(self.pb_ay), width=140, dense=True,
                                on_select=lambda e: self._pb_ay_degisti(e),
                                options=[secenek(i + 1, ad) for i, ad in enumerate(AYLAR)])], wrap=True),
            kart(satir("Toplam brüt", para(v["toplamlar"]["brut"]) + " TL"),
                 satir("Toplam net", para(v["toplamlar"]["net"]) + " TL", True)),
        ]
        for kayit in v["kayitlar"]:
            duzenlenebilir = (v["yazabilir"] and self.ben.get("kullanici", {}).get("rol") != "Öğretmen"
                              and kayit["durum"] != "Onaylandı"
                              and not str(kayit.get("onay") or "").startswith("Bekliyor"))

            async def ac(e, pb_id=kayit["id"], duzenle=duzenlenebilir):
                if duzenle:
                    await self.parca_basi_formu(pb_id)
                else:
                    await self.parca_basi_detay(pb_id)

            kontroller.append(ft.Card(content=ft.ListTile(
                leading=ft.Icon(ft.Icons.GROUPS, color=ft.Colors.TEAL_700),
                title=ft.Text(f"{AYLAR[kayit['ay'] - 1]} {kayit['yil']} • {kayit.get('siparis_no') or 'Siparişsiz'}",
                              weight=ft.FontWeight.BOLD),
                subtitle=ft.Text(f"{kayit.get('konu') or ''}\n{kayit.get('kisi') or 0} kişi • Brüt "
                                 f"{para(kayit.get('brut'))} TL • Net {para(kayit.get('net'))} TL • {kayit['onay']}",
                                 max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
                is_three_line=True, on_click=ac, trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT))))
        if not v["kayitlar"]:
            kontroller.append(ft.Text(f"{AYLAR[self.pb_ay - 1]} {self.yil} için parça başı bordro yok."))
        self.govde.content = self.liste(kontroller)
        if v["yazabilir"] and self.ben.get("kullanici", {}).get("rol") != "Öğretmen":
            self.ana.floating_action_button = ft.FloatingActionButton(
                icon=ft.Icons.ADD, tooltip="Parça başı bordro ekle",
                on_click=lambda e: self.page.run_task(self.parca_basi_formu))
        else:
            self.ana.floating_action_button = None

    async def _pb_ay_degisti(self, e):
        self.pb_ay = int(e.control.value)
        await self.parca_basi_sekmesi()

    async def parca_basi_detay(self, pb_id: int):
        v = await self.cagir(self.api.get, f"/parca-basi/{pb_id}")
        if v is None:
            return
        kontroller = [
            kart(satir("Dönem", f"{AYLAR[v['ay'] - 1]} {v['yil']}"),
                 satir("Sipariş", f"{v.get('siparis_no') or ''} • {v.get('konu') or ''}"),
                 satir("Kabul edilen işçilik", para(v["kabul_edilen_iscilik"]) + " TL"),
                 satir("Öğrenci hakkı oranı", f"%{100 * v['ogrenci_orani']:.1f}"),
                 satir("Durum", v["onay"]),
                 satir("Brüt", para(v["toplamlar"]["brut"]) + " TL", True),
                 satir("Net", para(v["toplamlar"]["net"]) + " TL", True)),
        ]
        if v.get("aciklama"):
            kontroller.append(kart(baslik("Açıklama"), ft.Text(v["aciklama"], selectable=True)))
        for r in v["satirlar"]:
            kontroller.append(kart(
                baslik(f"{r['kisi_turu']} • {r.get('ad_soyad') or '?'}"),
                satir("Katkı", f"{r['katki']:g}"),
                satir("Hesaplanan", para(r["hesaplanan"]) + " TL"),
                satir("Brüt / Net", f"{para(r['brut'])} / {para(r['net'])} TL", True),
                satir("GV / Damga", f"{para(r['gelir_vergisi'])} / {para(r['damga_vergisi'])} TL"),
            ))
        if self.ben.get("kullanici", {}).get("rol") != "Öğretmen":
            kontroller.append(ft.Row([
                ft.OutlinedButton("Bordro PDF", icon=ft.Icons.PICTURE_AS_PDF,
                                  on_click=lambda e: self.page.run_task(self.parca_basi_belge, pb_id, "bordro")),
                ft.OutlinedButton("Puantaj PDF", icon=ft.Icons.PICTURE_AS_PDF,
                                  on_click=lambda e: self.page.run_task(self.parca_basi_belge, pb_id, "puantaj")),
                ft.OutlinedButton("Banka Excel", icon=ft.Icons.TABLE_VIEW,
                                  on_click=lambda e: self.page.run_task(self.parca_basi_belge, pb_id, "banka")),
            ], wrap=True))
            if v["durum"] == "Onaylandı":
                kontroller.append(ft.FilledButton(
                    "Ödeme kaydı oluştur", icon=ft.Icons.PAYMENTS,
                    on_click=lambda e: self.page.run_task(self.parca_basi_odeme, v)))
        self.ac(self.gorunum(f"Parça Başı • {AYLAR[v['ay'] - 1]} {v['yil']}", kontroller))

    async def parca_basi_belge(self, pb_id: int, tur: str):
        dosya = await self.cagir(self.api.get, f"/parca-basi/{pb_id}/belge/{tur}")
        if dosya is not None:
            await self._dosyayi_kaydet(dosya, "Parça başı belgesini kaydet")

    async def parca_basi_odeme(self, kayit: dict):
        tarih_alani = ft.TextField(label="Ödeme tarihi (YYYY-AA-GG)", value=date.today().isoformat())
        hesap = ft.Dropdown(label="Ödeme hesabı", value="Banka (102)", options=[
            secenek("Banka (102)", "Banka (102)"), secenek("Kasa (100)", "Kasa (100)")])
        belge_no = ft.TextField(label="Belge / dekont no")
        aciklama = ft.TextField(label="Açıklama", value=f"{AYLAR[kayit['ay'] - 1]} {kayit['yil']} parça başı ücret "
                                                           f"({kayit.get('siparis_no') or ''})")

        async def kaydet(e=None):
            self.page.pop_dialog()
            sonuc = await self.cagir(self.api.post, f"/parca-basi/{kayit['id']}/odeme", {
                "tarih": tarih_alani.value or "", "hesap": hesap.value or "Banka (102)",
                "belge_no": belge_no.value or "", "aciklama": aciklama.value or "",
            })
            if sonuc is not None:
                self.bildir(f"{para(sonuc['tutar'])} TL tutarında ödeme kaydı oluşturuldu.")
                await self.parca_basi_detay(kayit["id"])

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("Parça başı ödemesi"),
            content=ft.Column([ft.Text(f"Onaylı net tutar: {para(kayit['toplamlar']['net'])} TL"),
                               tarih_alani, hesap, belge_no, aciklama], tight=True, scroll=ft.ScrollMode.AUTO),
            actions=[ft.TextButton("Vazgeç", on_click=lambda e: self.page.pop_dialog()),
                     ft.FilledButton("Ödeme kaydı oluştur", icon=ft.Icons.PAYMENTS, on_click=kaydet)]))

    async def parca_basi_formu(self, pb_id: int | None = None):
        kayit = await self.cagir(self.api.get, f"/parca-basi/{pb_id}") if pb_id else None
        if pb_id and kayit is None:
            return
        yil = kayit["yil"] if kayit else self.yil
        sec = await self.cagir(self.api.get, "/parca-basi/secenekler", yil=yil)
        if sec is None:
            return
        orders = sec["siparisler"]
        if kayit and not any(s["id"] == kayit["siparis_id"] for s in orders):
            orders.append({"id": kayit["siparis_id"], "siparis_no": kayit.get("siparis_no"),
                           "konu": kayit.get("konu"), "durum": kayit.get("siparis_durumu")})
        siparis = ft.Dropdown(label="Sipariş", expand=True, editable=True, enable_filter=True,
                              options=[secenek(s["id"], f"{s.get('siparis_no') or ''} • {s.get('konu') or ''} "
                                                        f"({s.get('durum') or ''})") for s in orders],
                              value=str(kayit["siparis_id"]) if kayit else None)
        ay = ft.Dropdown(label="Ay", width=140, value=str(kayit["ay"] if kayit else self.pb_ay),
                         options=[secenek(i + 1, ad) for i, ad in enumerate(AYLAR)])
        kabul = ft.TextField(label="Ay içinde kabul edilen işçilik (TL)", keyboard_type=ft.KeyboardType.NUMBER,
                             value=str(kayit["kabul_edilen_iscilik"]) if kayit else "0")
        oran = ft.TextField(label="Öğrenci hakkı oranı (0–1)",
                            value=str(kayit["ogrenci_orani"] if kayit else sec["ogrenci_hakki_orani"]))
        aciklama = ft.TextField(label="Açıklama", multiline=True, min_lines=2, value=(kayit or {}).get("aciklama") or "")
        kisi_turu = ft.Dropdown(label="Kişi türü", value="Personel", width=150,
                                options=[secenek("Personel", "Personel"), secenek("Öğrenci", "Öğrenci")])
        kisi_sec = ft.Dropdown(label="Kişi", expand=True)
        satir_kutusu = ft.Column(spacing=8)
        sonuc_kutusu = ft.Column(spacing=8)
        satirlar: list[dict] = []

        def kisi_seceneklerini_yenile(e=None):
            kisiler = sec["personeller"] if kisi_turu.value == "Personel" else sec["ogrenciler"]
            kisi_sec.options = [secenek(k["id"], f"{k['ad_soyad']}" +
                                         (f" • {k.get('sinif')}" if k.get("sinif") else "")) for k in kisiler]
            kisi_sec.value = None
            self.page.update()

        def puantaj_metni(p):
            return ", ".join(f"{g}={v:g}" for g, v in sorted(p.items()))

        def satirlari_goster():
            satir_kutusu.controls.clear()
            for idx, row in enumerate(satirlar):
                async def sil(e, i=idx):
                    satirlar.pop(i)
                    satirlari_goster()
                satir_kutusu.controls.append(ft.Card(content=ft.Container(
                    ft.Column([
                        ft.Row([ft.Text(f"{row['ad']} • {row['kisi_turu']}", expand=True, weight=ft.FontWeight.BOLD),
                                ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Satırı kaldır", on_click=sil)]),
                        ft.Row([row["katki"], row["onceki"]], wrap=True),
                        row["puantaj"],
                    ], spacing=6), padding=10)))
            self.page.update()

        def satir_ekle(kisi, tur, katki=1, onceki=None, puantaj=None):
            if any(r["kisi_turu"] == tur and r["kisi_id"] == int(kisi["id"]) for r in satirlar):
                self.bildir("Bu kişi bordroda zaten bulunuyor.")
                return
            satirlar.append({
                "kisi_turu": tur, "kisi_id": int(kisi["id"]), "ad": kisi["ad_soyad"],
                "katki": ft.TextField(label="Katkı (oran / adet)", width=180, keyboard_type=ft.KeyboardType.NUMBER,
                                      value=str(katki)),
                "onceki": ft.TextField(label="Önceki kümülatif (TL)", width=200, keyboard_type=ft.KeyboardType.NUMBER,
                                       value="" if onceki is None else str(onceki)),
                "puantaj": ft.TextField(label="Günlük puantaj (ör. 1=2, 2=3)", value=puantaj_metni(puantaj or {}),
                                        expand=True),
            })
            satirlari_goster()

        def kisi_ekle(e=None):
            if not kisi_sec.value:
                self.bildir("Önce eklenecek kişiyi seçiniz.")
                return
            tur = kisi_turu.value
            kisiler = sec["personeller"] if tur == "Personel" else sec["ogrenciler"]
            kisi = next((k for k in kisiler if str(k["id"]) == str(kisi_sec.value)), None)
            if kisi:
                satir_ekle(kisi, tur)

        for row in (kayit or {}).get("satirlar", []):
            personeller = sec["personeller"] if row["kisi_turu"] == "Personel" else sec["ogrenciler"]
            kisi = next((k for k in personeller if k["id"] == row["kisi_id"]),
                        {"id": row["kisi_id"], "ad_soyad": row.get("ad_soyad") or "?"})
            satir_ekle(kisi, row["kisi_turu"], row.get("katki") or 0, row.get("onceki_kumulatif"),
                       row.get("puantaj") or {})
        kisi_turu.on_select = kisi_seceneklerini_yenile
        kisi_seceneklerini_yenile()

        def form_verisi():
            if not siparis.value:
                raise ValueError("Sipariş seçiniz.")
            if not satirlar:
                raise ValueError("Bordroya en az bir kişi ekleyiniz.")
            try:
                kabul_tutari = sayi(kabul.value, "Kabul edilen işçilik")
                ogrenci_orani = sayi(oran.value, "Öğrenci hakkı oranı")
                if kabul_tutari is None or ogrenci_orani is None:
                    raise ValueError("İşçilik ve öğrenci hakkı oranı boş bırakılamaz.")
                veri_satirlari = []
                for row in satirlar:
                    katki = sayi(row["katki"].value, "Katkı")
                    onceki = sayi(row["onceki"].value, "Önceki kümülatif")
                    puantaj = {}
                    for parca in (row["puantaj"].value or "").replace(";", ",").replace("\\n", ",").split(","):
                        if not parca.strip():
                            continue
                        gun, ayirac, adet = parca.partition("=")
                        if not ayirac:
                            raise ValueError("Puantajı gün=adet biçiminde, virgülle ayırarak giriniz.")
                        g = int(gun.strip())
                        deger = sayi(adet, "Puantaj")
                        if not 1 <= g <= 31 or deger is None or deger < 0:
                            raise ValueError("Puantaj günü 1–31, adet ise sıfır veya daha büyük olmalıdır.")
                        puantaj[g] = deger
                    if katki is None:
                        raise ValueError("Katkı alanı boş bırakılamaz.")
                    veri_satirlari.append({"kisi_turu": row["kisi_turu"], "kisi_id": row["kisi_id"],
                                           "katki": katki, "onceki_kumulatif": onceki, "puantaj": puantaj})
                return {"yil": yil, "ay": int(ay.value), "siparis_id": int(siparis.value),
                        "kabul_edilen_iscilik": kabul_tutari, "ogrenci_orani": ogrenci_orani,
                        "aciklama": aciklama.value or "", "satirlar": veri_satirlari}
            except (TypeError, ValueError) as err:
                raise ValueError(str(err)) from None

        async def hesapla(e=None):
            try:
                veri = form_verisi()
            except ValueError as err:
                self.bilgi("Hatalı bilgi", str(err))
                return None
            endpoint = "/parca-basi/hesapla"
            args = {"pb_id": pb_id} if pb_id else {}
            sonuc = await self.cagir(self.api.istek, "POST", endpoint, veri, **args)
            if sonuc is None:
                return None
            h = sonuc["hesap"]
            sonuc_kutusu.controls = [kart(
                baslik("Hesap özeti"),
                satir("Hesaplanan / brüt", f"{para(h['toplamlar']['hesaplanan'])} / {para(h['toplamlar']['brut'])} TL"),
                satir("GV + damga", f"{para(h['toplamlar']['gelir_vergisi'] + h['toplamlar']['damga_vergisi'])} TL"),
                satir("Net ödenecek", para(h["toplamlar"]["net"]) + " TL", True),
            )]
            if h["hatalar"]:
                sonuc_kutusu.controls.append(mesaj_kutusu(h["hatalar"], "hata"))
            if h["uyarilar"]:
                sonuc_kutusu.controls.append(mesaj_kutusu(h["uyarilar"], "uyari"))
            if not h["hatalar"]:
                sonuc_kutusu.controls.append(mesaj_kutusu(["Mevzuat kontrolünden geçti."], "bilgi"))
            self.page.update()
            return h

        async def kaydet(e=None):
            h = await hesapla()
            if h is None:
                return

            async def devam():
                try:
                    veri = form_verisi()
                except ValueError as err:
                    self.bilgi("Hatalı bilgi", str(err))
                    return
                sonuc = await self.cagir(self.api.put if pb_id else self.api.post,
                                         f"/parca-basi/{pb_id}" if pb_id else "/parca-basi", veri)
                if sonuc is None:
                    return
                mesaj = "Parça başı bordro kaydedildi."
                if h["hatalar"]:
                    mesaj += " Mevzuat hataları kaydedildi; onaya gönderilemez."
                elif h["uyarilar"]:
                    mesaj += " Uyarıları kontrol ediniz."
                self.bildir(mesaj)
                self.geri()
                await self.parca_basi_sekmesi()

            if h["hatalar"]:
                self.sor("Mevzuat kontrolü", "Mevzuat hataları var. Taslak olarak yine de kaydedilsin mi?\n\n"
                         + "\n".join(h["hatalar"]), devam, "Taslak kaydet")
            else:
                await devam()

        async def onaya_gonder(e=None):
            h = await hesapla()
            if h is None:
                return
            if h["hatalar"]:
                self.bilgi("Onaya gönderilemez", "\n".join(h["hatalar"]))
                return
            try:
                veri = form_verisi()
            except ValueError as err:
                self.bilgi("Hatalı bilgi", str(err))
                return
            sonuc = await self.cagir(self.api.put if pb_id else self.api.post,
                                     f"/parca-basi/{pb_id}" if pb_id else "/parca-basi", veri)
            if sonuc is None:
                return
            belge_id = pb_id or sonuc["id"]
            tur = "gonder" if self.ben.get("onay_akisi") else "dogrudan"
            sonuc = await self.cagir(self.api.post, Istemci.yol("onay", "Parça Başı", belge_id, tur),
                                     {"aciklama": ""})
            if sonuc is not None:
                self.bildir(sonuc.get("durum_metni") or "Parça başı bordro onaya gönderildi.")
                self.geri()
                await self.parca_basi_sekmesi()

        actions = [
            ft.OutlinedButton("Hesapla ve kontrol et", icon=ft.Icons.CALCULATE, on_click=hesapla),
            ft.FilledButton("Taslak kaydet", icon=ft.Icons.SAVE, on_click=kaydet),
        ]
        actions.append(ft.FilledButton(
            "Kaydet ve onaya gönder" if self.ben.get("onay_akisi") else "Kaydet ve kesinleştir",
            icon=ft.Icons.SEND if self.ben.get("onay_akisi") else ft.Icons.TASK_ALT,
            on_click=lambda e: self.sor("Parça başı bordro", "Bordro kaydedilip onay akışına gönderilecek."
                                        if self.ben.get("onay_akisi") else
                                        "Bordro kaydedilip kesinleştirilecek ve yardımcı yevmiye kaydı oluşturulacak.",
                                        onaya_gonder, "Devam et")))
        if pb_id:
            async def sil():
                if await self.cagir(self.api.delete, f"/parca-basi/{pb_id}") is None:
                    return
                self.bildir("Bordro silindi.")
                self.geri()
                await self.parca_basi_sekmesi()
            actions.append(ft.OutlinedButton("Sil", icon=ft.Icons.DELETE_OUTLINE,
                                             on_click=lambda e: self.sor("Bordroyu sil", "Taslak bordro silinsin mi?",
                                                                         sil, "Sil")))
        self.ac(self.gorunum(f"Parça başı bordro • {yil}", [
            mesaj_kutusu(["Ay içinde geçici kabulü yapılan işçilik, öğrenci hakkı ayrıldıktan sonra katkıya göre dağıtılır. "
                          "Aylık kişi tavanı, vergi, puantaj ve aynı sipariş fazla çalışma çakışması sunucuda denetlenir."],
                         "bilgi"),
            ft.Row([ay, siparis], wrap=True), ft.Row([kabul, oran], wrap=True), aciklama,
            ft.Row([kisi_turu, kisi_sec, ft.FilledButton("Kişi ekle", icon=ft.Icons.PERSON_ADD, on_click=kisi_ekle)],
                   wrap=True),
            satir_kutusu, sonuc_kutusu,
            ft.Row([ft.OutlinedButton("Katkıları eşitle", on_click=lambda e: self._pb_esitle(satirlar, satirlari_goster))],
                   wrap=True),
            ft.Column(actions, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, spacing=8),
        ]))

    @staticmethod
    def _pb_esitle(satirlar: list[dict], yenile):
        for tur in ("Personel", "Öğrenci"):
            grup = [r for r in satirlar if r["kisi_turu"] == tur]
            for row in grup:
                row["katki"].value = str(round(100 / len(grup), 3)) if grup else "0"
        yenile()

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
            if self.ben.get("yedekleme_yetkisi"):
                kontroller.append(oge(ft.Icons.BACKUP, "Yedekleme", "Yedek al, indir ve güvenli geri yükle",
                                      lambda e: self.page.run_task(self.yedekleme_ekrani)))
        if self.modul("denetim"):
            kontroller.append(oge(ft.Icons.FACT_CHECK_OUTLINED, "Denetim formu",
                                  "Rehber kontrol listesi, ortak çalışma ve rapor",
                                  lambda e: self.page.run_task(self.denetim_listesi)))
        if self.modul("raporlar"):
            kontroller.append(oge(ft.Icons.ANALYTICS, "Yönetim raporları",
                                  "Yıllık gelir, gider, cari, personel ve mevzuat raporları",
                                  lambda e: self.page.run_task(self.rapor_ekrani)))
        if self.modul("yil_sonu"):
            kontroller.append(oge(ft.Icons.EVENT_AVAILABLE, "Yıl sonu kârı ve ÜTP",
                                  "Kâr bölüşümü, kişi bazlı dağıtım ve banka listesi",
                                  lambda e: self.page.run_task(self.yil_sonu_ekrani)))
        if self.modul("belgeler"):
            kontroller.append(oge(ft.Icons.DESCRIPTION, "Resmi yazılar / belgeler",
                                  "Yazı şablonları, öğrenci muvafakati ve listeler",
                                  lambda e: self.page.run_task(self.belgeler_ekrani)))
        if self.modul("yapilacaklar"):
            kontroller.append(oge(ft.Icons.TODAY, "Bugün ne yapmalıyım?",
                                  "Rolünüze göre işler, onaylar ve yaklaşan yasal süreler",
                                  lambda e: self.page.run_task(self.yapilacaklar_ekrani)))
        if self.modul("uyum"):
            kontroller.append(oge(ft.Icons.FACT_CHECK, "Mevzuat uyum denetimi",
                                  "Kayıtları tarayın, bulguları ve düzeltme adımlarını inceleyin",
                                  lambda e: self.page.run_task(self.uyum_ekrani)))
        if self.modul("kilavuz"):
            kontroller.append(oge(ft.Icons.MENU_BOOK, "Nasıl yaparım? (adım adım)",
                                  "Rolünüze uygun iş rehberleri ve görev adımları",
                                  lambda e: self.page.run_task(self.kilavuz_ekrani)))
        if self.modul("rehber"):
            kontroller.append(oge(ft.Icons.GAVEL, "Mevzuat Rehberi",
                                  "Mevzuat özeti, görevler, riskler, takvim ve yıllık parametreler",
                                  lambda e: self.page.run_task(self.mevzuat_rehberi_ekrani)))
        if self.modul("kullanicilar"):
            kontroller.append(oge(ft.Icons.MANAGE_ACCOUNTS, "Kullanıcılar ve roller",
                                  "Kullanıcı hesaplarını, geçici şifreleri ve onay akışını yönetin",
                                  lambda e: self.page.run_task(self.kullanicilar_ekrani)))
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

    async def kullanicilar_ekrani(self):
        veri = await self.cagir(self.api.get, "/kullanicilar")
        if veri is None:
            return

        def kisi_formu(kisi=None):
            yeni = kisi is None
            ad = ft.TextField(label="Kullanıcı adı", value="" if yeni else kisi["kullanici_adi"],
                              disabled=not yeni, max_length=80)
            ad_soyad = ft.TextField(label="Ad soyad", value="" if yeni else kisi.get("ad_soyad") or "",
                                    max_length=120)
            rol = ft.Dropdown(label="Rol", value=None if yeni else kisi["rol"], expand=True,
                              options=[secenek(r, r) for r in veri["roller"]])
            personel = ft.Dropdown(label="Bağlı personel", value=None if yeni or not kisi.get("personel_id")
                                   else str(kisi["personel_id"]), expand=True,
                                   options=[secenek("", "—")] + [
                                       secenek(str(p["id"]), p["ad_soyad"]) for p in veri["personeller"]])
            bolum = ft.Dropdown(label="Bölüm / alan", value=None if yeni or not kisi.get("bolum_id")
                                else str(kisi["bolum_id"]), expand=True,
                                options=[secenek("", "—")] + [
                                    secenek(str(b["id"]), b["ad"]) for b in veri["bolumler"]])
            sifre = ft.TextField(label="Geçici şifre (en az 6 karakter)", password=True,
                                 can_reveal_password=True, visible=yeni, max_length=256)
            aktif = ft.Switch(label="Aktif", value=True if yeni else kisi["aktif"], visible=not yeni)

            async def kaydet(e):
                ad_degeri = (ad.value or "").strip()
                ad_soyad_degeri = (ad_soyad.value or "").strip()
                if (yeni and len(ad_degeri) < 3) or not ad_soyad_degeri or (yeni and len(sifre.value or "") < 6):
                    self.bilgi("Eksik bilgi", "Kullanıcı adı en az 3, ad soyad zorunludur. Geçici şifre en az 6 karakter olmalıdır.")
                    return
                govde = {
                    "ad_soyad": ad_soyad_degeri,
                    "rol": rol.value,
                    "personel_id": int(personel.value) if personel.value else None,
                    "bolum_id": int(bolum.value) if bolum.value else None,
                }
                if yeni:
                    govde.update({"kullanici_adi": ad_degeri, "sifre": sifre.value})
                    sonuc = await self.cagir(self.api.post, "/kullanicilar", govde)
                else:
                    govde["aktif"] = aktif.value
                    sonuc = await self.cagir(self.api.put, f"/kullanicilar/{kisi['id']}", govde)
                if sonuc is not None:
                    self.geri()
                    if not yeni and kisi["id"] == (self.ben.get("kullanici") or {}).get("id"):
                        self.ben["kullanici"].update(govde)
                    await self.kullanicilar_ekrani()

            self.ac(self.gorunum(
                "Yeni kullanıcı" if yeni else f"Kullanıcıyı düzenle — {kisi['kullanici_adi']}",
                [ft.Text("İlk girişte kullanıcıdan geçici şifresini değiştirmesi istenir.", size=12,
                         color=ft.Colors.BLUE_GREY_700) if yeni else ft.Container(),
                 ad, ad_soyad, rol, personel, bolum, sifre, aktif,
                 ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, on_click=kaydet)],
            ))

        async def sifre_sifirla(kisi):
            yeni_sifre = ft.TextField(label="Yeni geçici şifre (en az 6 karakter)", password=True,
                                      can_reveal_password=True, max_length=256)

            async def kaydet(e):
                if len(yeni_sifre.value or "") < 6:
                    self.bilgi("Geçersiz şifre", "Şifre en az 6 karakter olmalıdır.")
                    return
                sonuc = await self.cagir(
                    self.api.post, f"/kullanicilar/{kisi['id']}/sifre", {"sifre": yeni_sifre.value})
                if sonuc is not None:
                    self.geri()
                    self.bilgi("Şifre sıfırlandı", "Kullanıcı ilk girişte yeni şifresini değiştirecektir.")
                    await self.kullanicilar_ekrani()

            self.ac(self.gorunum(
                f"Şifre sıfırla — {kisi['kullanici_adi']}",
                [ft.Text("Yeni şifre en az 6 karakter olmalıdır."), yeni_sifre,
                 ft.FilledButton("Şifreyi sıfırla", icon=ft.Icons.PASSWORD, on_click=kaydet)],
            ))

        async def sil(kisi):
            sonuc = await self.cagir(self.api.delete, f"/kullanicilar/{kisi['id']}")
            if sonuc is not None:
                await self.kullanicilar_ekrani()

        async def akis_degistir(e):
            sonuc = await self.cagir(self.api.put, "/kullanicilar/onay-akisi",
                                     {"acik": e.control.value})
            if sonuc is None:
                e.control.value = veri["akis_acik"]
                self.page.update()
                return
            await self.kullanicilar_ekrani()

        kontroller = [
            kart(baslik("Kullanıcılar ve Roller"),
                 ft.Text("Roller menü erişimini ve işlem yetkilerini belirler. Alan şefi ve öğretmen hesapları "
                         "personel kaydına ve bölüme bağlanmalıdır.", selectable=True)),
            ft.Row([ft.FilledButton("Yeni kullanıcı", icon=ft.Icons.PERSON_ADD,
                                    on_click=lambda e: kisi_formu()),
                    ft.OutlinedButton("Rol / yetki tablosu", icon=ft.Icons.VIEW_LIST,
                                      on_click=lambda e: self._yetki_tablosu_goster(veri["yetki_tablosu"],
                                                                                   veri["roller"]))],
                   wrap=True),
            ft.Switch(label="Onay akışı etkin", value=veri["akis_acik"], on_change=akis_degistir),
            ft.Text("Akış kapatılamazken bekleyen belgeler varsa; önce belgeleri sonuçlandırın.",
                    size=12, color=ft.Colors.BLUE_GREY_700),
        ]
        if not veri["kullanicilar"]:
            kontroller.append(mesaj_kutusu(["Kullanıcı bulunamadı."], "bilgi"))
        for kisi in veri["kullanicilar"]:
            durum = "Aktif" if kisi["aktif"] else "Pasif"
            detay = " • ".join(x for x in (
                kisi.get("rol"), kisi.get("personel_ad"), kisi.get("bolum_ad"), durum,
                "İlk girişte şifre değişecek" if kisi.get("sifre_degismeli") else None,
            ) if x)
            kontroller.append(kart(
                ft.Row([ft.Icon(ft.Icons.ACCOUNT_CIRCLE, color=ft.Colors.TEAL_700),
                        ft.Column([ft.Text(kisi.get("ad_soyad") or kisi["kullanici_adi"],
                                           weight=ft.FontWeight.BOLD),
                                   ft.Text("@" + kisi["kullanici_adi"], size=12,
                                           color=ft.Colors.BLUE_GREY_700),
                                   ft.Text(detay, size=12, selectable=True)],
                                  spacing=3, expand=True)]),
                ft.Row([
                    ft.TextButton("Düzenle", icon=ft.Icons.EDIT,
                                  on_click=lambda e, k=kisi: kisi_formu(k)),
                    ft.TextButton("Şifre sıfırla", icon=ft.Icons.PASSWORD,
                                  on_click=lambda e, k=kisi: self.page.run_task(sifre_sifirla, k)),
                    ft.TextButton("Sil", icon=ft.Icons.DELETE_OUTLINE,
                                  style=ft.ButtonStyle(color=ft.Colors.RED_700),
                                  on_click=lambda e, k=kisi: self.sor(
                                      "Kullanıcıyı sil", f"{k['kullanici_adi']} hesabı silinsin mi?",
                                      lambda: sil(k), "Sil")),
                ], wrap=True),
            ))
        self.govde.content = self.liste(kontroller)

    def _yetki_tablosu_goster(self, tablo, roller):
        satirlar = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(s["sayfa"])),
                *(ft.DataCell(ft.Text({"y": "Yazabilir", "g": "Görüntüleyebilir", "-": "—"}
                                      .get(s["roller"][rol], "—"))) for rol in roller),
            ])
            for s in tablo
        ]
        tablo_kontrolu = ft.DataTable(
            columns=[ft.DataColumn(ft.Text("Sayfa"))] +
                    [ft.DataColumn(ft.Text(rol)) for rol in roller],
            rows=satirlar, heading_row_height=60, data_row_min_height=44,
        )
        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("Rol / yetki tablosu"),
            content=ft.Column([ft.Row([tablo_kontrolu], scroll=ft.ScrollMode.AUTO)],
                              width=720, height=520, scroll=ft.ScrollMode.AUTO),
            scrollable=True,
            actions=[ft.TextButton("Kapat", on_click=lambda e: self.page.pop_dialog())],
        ))

    async def yapilacaklar_ekrani(self):
        veri = await self.cagir(self.api.get, "/yapilacaklar", yil=self.yil)
        if veri is None:
            return
        kontroller = [
            kart(baslik("Bugün Ne Yapmalıyım?"), ft.Text(
                f"{veri.get('rol_unvani') or ''} • {veri.get('rol_ozeti') or ''}",
                color=ft.Colors.BLUE_GREY_700, selectable=True)),
            ft.Row([self._yil_secici(self.yapilacaklar_ekrani)]),
            ft.ResponsiveRow([
                ft.Container(ft.Column([ft.Text(ad, size=12, color=ft.Colors.BLUE_GREY_700),
                                        ft.Text(str(sayi_), size=20, weight=ft.FontWeight.BOLD,
                                                color=renk)]), col={"xs": 6, "md": 3},
                             padding=14, bgcolor=ft.Colors.WHITE, border_radius=12)
                for ad, sayi_, renk in (
                    ("Acil / riskli", sum(x["seviye"] == "hata" for x in veri["bulgular"]), ft.Colors.RED_700),
                    ("Dikkat", sum(x["seviye"] == "uyari" for x in veri["bulgular"]), ft.Colors.ORANGE_800),
                    ("Onayınızı bekleyen", veri.get("bekleyen_onay", 0), ft.Colors.TEAL_700),
                    ("Yaklaşan yasal süre", len(veri["sureler"]), ft.Colors.BLUE_700),
                )
            ], spacing=8, run_spacing=8),
        ]
        if not veri["bulgular"] and not veri["sureler"] and not veri.get("bekleyen_onay"):
            kontroller.append(mesaj_kutusu(["Şu anda rolünüz için acil bir iş veya yaklaşan son tarih görünmüyor."], "bilgi"))
        for bulgu in veri["bulgular"]:
            kontroller.append(kart(
                ft.Row([ft.Icon(SEVIYE_IKON.get(bulgu["seviye"], ft.Icons.INFO_OUTLINE),
                                color=SEVIYE_RENK.get(bulgu["seviye"], ft.Colors.BLUE_700)),
                        ft.Text(bulgu["baslik"], weight=ft.FontWeight.BOLD, expand=True)]),
                ft.Text(bulgu.get("aciklama") or "", selectable=True),
                ft.Text(bulgu.get("cozum") or "", color=ft.Colors.GREEN_800, selectable=True),
                satir("Kim yapar", ", ".join(bulgu.get("sorumlular") or [])),
                satir("Dayanak", bulgu.get("dayanak") or "-"),
            ))
        for sure in veri["sureler"]:
            kalan = sure["kalan_gun"]
            seviye = "hata" if kalan <= 3 else "uyari" if kalan <= 10 else "bilgi"
            kontroller.append(kart(
                ft.Row([ft.Icon(SEVIYE_IKON[seviye], color=SEVIYE_RENK[seviye]),
                        ft.Text(f"{sure['ad']} — {tarih(sure['tarih'])} ({kalan} gün kaldı)",
                                weight=ft.FontWeight.BOLD, expand=True)]),
                ft.Text(sure["aciklama"], selectable=True),
            ))
        self.govde.content = self.liste(kontroller)

    async def uyum_ekrani(self):
        veri = await self.cagir(self.api.get, "/uyum", yil=self.yil)
        if veri is None:
            return
        secim = ft.Dropdown(
            label="Göster",
            value="hepsi",
            width=220,
            options=[secenek("hepsi", "Tüm bulgular"), secenek("hata", "Acil / riskli"),
                     secenek("uyari", "Dikkat edilecek"), secenek("benim", "Benim yapacaklarım")],
        )

        def gorunen():
            return [x for x in veri["bulgular"] if secim.value == "hepsi"
                    or (secim.value == "benim" and x["ilgili"])
                    or x["seviye"] == secim.value]

        def doldur(e=None):
            puan_rengi = {"İyi": ft.Colors.GREEN_800, "Dikkat gerekiyor": ft.Colors.ORANGE_800,
                          "Riskli": ft.Colors.RED_700}.get(veri["puan_durumu"], ft.Colors.GREY_800)
            kontroller = [
                kart(baslik("Mevzuat Uyum Denetimi"),
                     ft.Text(f"{veri['yil']} yılı • " +
                             ("yalnız kendi bölümünüz" if veri["bolum_kisitli"] else "tüm erişilebilir kayıtlar")),
                     ft.Text(f"Uyum puanı: {veri['puan']} / 100 — {veri['puan_durumu']}",
                             size=18, weight=ft.FontWeight.BOLD, color=puan_rengi)),
                ft.Row([self._yil_secici(self.uyum_ekrani), secim], wrap=True),
                ft.ResponsiveRow([
                    ft.Container(ft.Column([ft.Text(label, size=12),
                                            ft.Text(str(veri["sayilar"][sev]), size=20,
                                                    weight=ft.FontWeight.BOLD, color=color)]),
                                 col={"xs": 4}, padding=14, bgcolor=ft.Colors.WHITE, border_radius=12)
                    for sev, label, color in (("hata", "Acil / riskli", ft.Colors.RED_700),
                                              ("uyari", "Dikkat", ft.Colors.ORANGE_800),
                                              ("bilgi", "Bilgi", ft.Colors.BLUE_700))
                ], spacing=8),
            ]
            bulgular = gorunen()
            if not bulgular:
                kontroller.append(mesaj_kutusu(["Bu görünümde bulgu yok."], "bilgi"))
            for bulgu in bulgular:
                ayrintilar = [
                    ft.Text(bulgu.get("aciklama") or "", selectable=True),
                    ft.Text(bulgu.get("cozum") or "", color=ft.Colors.GREEN_800, selectable=True),
                    satir("Kim yapar", ", ".join(bulgu.get("sorumlular") or [])),
                ]
                if bulgu.get("dayanak"):
                    ayrintilar.append(satir("Dayanak", bulgu["dayanak"]))
                sayfa = bulgu.get("sayfa")
                rehber = bulgu.get("rehber")
                eylemler = []
                if sayfa and sayfa in self.ben.get("sayfa_modulleri", {}):
                    eylemler.append(ft.TextButton(
                        "İlgili sayfaya git",
                        on_click=lambda e, hedef=sayfa: self.page.run_task(self._kilavuz_sayfaya_git, hedef)))
                if rehber and self.modul("kilavuz"):
                    eylemler.append(ft.TextButton(
                        "Adım adım rehber",
                        on_click=lambda e, kod=rehber: self.page.run_task(self.kilavuz_ekrani, kod)))
                kontroller.append(kart(
                    ft.Row([ft.Icon(SEVIYE_IKON.get(bulgu["seviye"], ft.Icons.INFO_OUTLINE),
                                    color=SEVIYE_RENK.get(bulgu["seviye"], ft.Colors.BLUE_700)),
                            ft.Text(f"{bulgu['seviye_adi']} • {bulgu['konu']}", size=12,
                                    color=SEVIYE_RENK.get(bulgu["seviye"], ft.Colors.BLUE_700)),
                            ft.Container(expand=True)]),
                    ft.Text(bulgu["baslik"], weight=ft.FontWeight.BOLD, size=16, selectable=True),
                    *ayrintilar, ft.Row(eylemler, wrap=True),
                ))
            kontroller.append(ft.Text(veri["genel_uyari"], size=12, color=ft.Colors.GREY_700))
            self.govde.content = self.liste(kontroller)
            self.page.update()

        secim.on_select = doldur
        self.govde.content = self.liste([ft.ProgressRing()])
        doldur()

    async def mevzuat_rehberi_ekrani(self):
        veri = await self.cagir(self.api.get, "/rehber", yil=self.yil)
        if veri is None:
            return

        bolumler = [
            "Mevzuat Özeti", "Sık Yapılan Hatalar", "Terimler Sözlüğü",
            "Görev ve Sorumluluklar", "Yasal Takvim", "Yıllık Parametreler",
        ]
        secim = ft.Dropdown(
            label="Rehber bölümü", value=bolumler[0], expand=True,
            options=[secenek(bolum, bolum) for bolum in bolumler],
        )

        async def yili_yenile():
            nonlocal veri
            yeni_veri = await self.cagir(self.api.get, "/rehber", yil=self.yil)
            if yeni_veri is not None:
                veri = yeni_veri
                goster()

        yil = self._yil_secici(yili_yenile)

        def goster(e=None):
            bolum = secim.value
            kontroller: list[ft.Control] = [
                kart(baslik("Mevzuat Rehberi"),
                     ft.Text("DÖSE işlemlerinin mevzuat özeti, pratik görevler, riskler ve yıllık değerler.",
                             selectable=True)),
                ft.Row([secim, yil], wrap=True),
            ]
            if bolum == "Mevzuat Özeti":
                kontroller.append(kart(
                    baslik("Mevzuat özeti"),
                    ft.Text(html_metin(veri["mevzuat_html"]), selectable=True),
                    ft.Text(veri["genel_uyari"], size=12, color=ft.Colors.GREY_700, selectable=True),
                ))
            elif bolum == "Sık Yapılan Hatalar":
                kontroller.extend(kart(
                    ft.Text(risk["hata"], weight=ft.FontWeight.BOLD, selectable=True),
                    ft.Text("Olası sonuç: " + risk["sonuc"], selectable=True),
                    ft.Text("Programın önlemi: " + risk["koruma"], selectable=True),
                    ft.Text("Dayanak: " + risk["dayanak"], size=12, color=ft.Colors.BLUE_GREY_700,
                            selectable=True),
                ) for risk in veri["riskler"])
            elif bolum == "Terimler Sözlüğü":
                kontroller.extend(kart(
                    ft.Text(kayit["terim"], weight=ft.FontWeight.BOLD, selectable=True),
                    ft.Text(kayit["aciklama"], selectable=True),
                ) for kayit in veri["sozluk"])
            elif bolum == "Görev ve Sorumluluklar":
                kontroller.extend(kart(
                    ft.Text(rol["unvan"], size=17, weight=ft.FontWeight.BOLD, selectable=True),
                    ft.Text(rol["ozet"], selectable=True),
                    *(ft.Text("• " + gorev, selectable=True) for gorev in rol["gorevler"]),
                    *(ft.Text("⚠ " + madde, color=ft.Colors.ORANGE_900, selectable=True)
                      for madde in rol["dikkat"]),
                ) for rol in veri["roller"])
            elif bolum == "Yasal Takvim":
                yakin = veri["yaklasan_sureler"]
                kontroller.append(kart(
                    baslik("Önümüzdeki 60 gün"),
                    *(ft.Text(
                        f"{tarih(sure['tarih'])} — {sure['ad']} ({sure['kalan_gun']} gün)\n{sure['aciklama']}",
                        selectable=True,
                    ) for sure in yakin) if yakin else ft.Text("Önümüzdeki 60 gün içinde listelenen bir son tarih yok."),
                    ft.Text("Son gün hafta sonuna veya tatile denk gelse bile işi önceki iş gününde bitirmeniz önerilir.",
                            size=12, color=ft.Colors.GREY_700, selectable=True),
                ))
                kontroller.extend(kart(
                    ft.Text(satir["zaman"], weight=ft.FontWeight.BOLD, selectable=True),
                    ft.Text(satir["aciklama"], selectable=True),
                ) for satir in veri["yasal_takvim"])
                hesap = veri["merkez_saymanlik"]
                kontroller.append(kart(
                    baslik("MEB Merkez Saymanlık"),
                    ft.Text(hesap["ad"], selectable=True),
                    ft.Text(f"VKN: {hesap['vkn']}\nIBAN: {hesap['iban']}", selectable=True),
                ))
            else:
                kontroller.extend(kart(
                    ft.Text(parametre["etiket"], weight=ft.FontWeight.BOLD, selectable=True),
                    ft.Text(parametre["deger"], selectable=True),
                    ft.Text(parametre["dayanak"], size=12, color=ft.Colors.BLUE_GREY_700, selectable=True)
                    if parametre["dayanak"] else ft.Container(),
                ) for parametre in veri["parametreler"])
                kontroller.append(ft.Text(
                    f"{veri['yil']} yılı değerlerini 'Mevzuat Parametreleri' sayfasından güncelleyebilirsiniz.",
                    size=12, color=ft.Colors.GREY_700, selectable=True,
                ))
            self.govde.content = self.liste(kontroller)
            self.page.update()

        secim.on_select = goster
        self.govde.content = self.liste([ft.ProgressRing()])
        goster()

    async def kilavuz_ekrani(self, kod: str | None = None, tumu: bool = False):
        veri = await self.cagir(self.api.get, "/kilavuz", tumu=tumu)
        if veri is None:
            return
        rehberler = veri["rehberler"]
        if kod and not any(r["kod"] == kod for r in rehberler) and not tumu:
            return await self.kilavuz_ekrani(kod, tumu=True)
        secili = next((r for r in rehberler if r["kod"] == kod), rehberler[0] if rehberler else None)
        secim = ft.Dropdown(
            label="Ne yapmak istiyorsunuz?",
            value=secili["kod"] if secili else None,
            options=[secenek(r["kod"], f"{r['ikon']}  {r['baslik']}") for r in rehberler],
            expand=True,
        )
        tumu_sec = ft.Switch(label="Diğer rollerin rehberlerini de göster", value=tumu)

        async def ac(e=None):
            await self.kilavuz_ekrani(secim.value, tumu_sec.value)

        async def git(sayfa: str):
            await self._kilavuz_sayfaya_git(sayfa)

        def doldur(e=None):
            secili_rehber = next((r for r in rehberler if r["kod"] == secim.value), None)
            kontroller = [
                kart(baslik("Nasıl Yaparım? (Adım Adım)"),
                     ft.Text("Her adımda işi kimin yapacağı ve ilgili Flet ekranı gösterilir.",
                             color=ft.Colors.BLUE_GREY_700)),
                secim, tumu_sec,
            ]
            rol = veri["rol_bilgisi"]
            if rol.get("unvan"):
                kontroller.append(kart(baslik(f"Rolünüz: {rol['unvan']}"),
                                       ft.Text(rol.get("ozet") or "", selectable=True),
                                       *(ft.Text(f"• {g}", selectable=True) for g in rol.get("gorevler") or []),
                                       *(ft.Text(f"⚠ {d}", color=ft.Colors.ORANGE_900, selectable=True)
                                         for d in rol.get("dikkat") or [])))
            if secili_rehber:
                kontroller.append(kart(
                    ft.Text(f"{secili_rehber['ikon']} {secili_rehber['baslik']}", size=19,
                            weight=ft.FontWeight.BOLD),
                    ft.Text(secili_rehber["ozet"], selectable=True),
                    ft.Text("Kimler için: " + ", ".join(secili_rehber["roller"]),
                            size=12, color=ft.Colors.BLUE_GREY_700),
                ))
                for i, adim in enumerate(secili_rehber["adimlar"], 1):
                    meta = " • ".join(x for x in (adim.get("sayfa"), adim.get("kim")) if x)
                    eylemler = []
                    if adim.get("sayfa") in self.ben.get("sayfa_modulleri", {}):
                        eylemler.append(ft.TextButton(
                            "Git →", on_click=lambda e, hedef=adim["sayfa"]: self.page.run_task(git, hedef)))
                    kontroller.append(kart(
                        ft.Text(f"{i}. {adim['metin']}", weight=ft.FontWeight.W_600, selectable=True),
                        ft.Text(meta, size=12, color=ft.Colors.BLUE_GREY_700) if meta else ft.Container(),
                        ft.Row(eylemler),
                    ))
                if secili_rehber.get("yasaklar"):
                    kontroller.append(mesaj_kutusu(
                        ["Asla yapmayın: " + " • ".join(secili_rehber["yasaklar"])], "hata"))
                if secili_rehber.get("risk"):
                    kontroller.append(mesaj_kutusu(["Yanlış yapılırsa: " + secili_rehber["risk"]], "uyari"))
                if secili_rehber.get("dayanak"):
                    kontroller.append(satir("Dayanak", secili_rehber["dayanak"]))
            kontroller.append(ft.Text(veri["genel_uyari"], size=12, color=ft.Colors.GREY_700))
            self.govde.content = self.liste(kontroller)
            self.page.update()

        async def tumu_degisti(e):
            await ac()

        secim.on_select = doldur
        tumu_sec.on_change = tumu_degisti
        self.govde.content = self.liste([ft.ProgressRing()])
        doldur()

    async def _kilavuz_sayfaya_git(self, sayfa: str):
        module = self.ben.get("sayfa_modulleri", {}).get(sayfa)
        hedef = next((i for i, sekme in enumerate(self.masaustu_sekmeler) if sekme[0] == module), None)
        if hedef is None:
            self.bildir(f"'{sayfa}' ekranı bu Flet istemcisinde henüz taşınmadı.")
            return
        self.rail.selected_index = hedef
        self.sekme = next((i for i, sekme in enumerate(self.sekmeler) if sekme[0] == module),
                          next(i for i, sekme in enumerate(self.sekmeler) if sekme[0] == "diger"))
        self.nav.selected_index = self.sekme
        await self.masaustu_sekmeler[hedef][3]()
        self.page.update()

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

    async def yedekleme_ekrani(self):
        v = await self.cagir(self.api.get, "/yedekler")
        if v is None:
            return

        async def indir(dosya_adi: str):
            dosya = await self.cagir(self.api.get, f"/yedekler/{dosya_adi}")
            if dosya is None:
                return
            picker = ft.FilePicker()
            self.page.overlay.append(picker)
            self.page.update()
            try:
                yol = await picker.save_file(dialog_title="Yedeği kaydet", file_name=dosya["dosya_adi"],
                                             src_bytes=base64.b64decode(dosya["icerik"]))
                if yol:
                    self.bildir(f"Yedek kaydedildi: {yol}")
            finally:
                self.page.overlay.remove(picker)
                self.page.update()

        async def yeni_yedek(e=None):
            sonuc = await self.cagir(self.api.post, "/yedekler")
            if sonuc is not None:
                self.bildir(f"Yedek alındı: {sonuc['dosya_adi']}")
                await self.yedekleme_ekrani()

        async def dosya_yukle(e=None):
            picker = ft.FilePicker()
            self.page.overlay.append(picker)
            self.page.update()
            try:
                secilenler = await picker.pick_files(
                    dialog_title="SQLite yedek dosyası seç",
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["db"],
                    allow_multiple=False,
                    with_data=True,
                )
                if not secilenler:
                    return
                dosya = secilenler[0]
                if dosya.size > 100 * 1024 * 1024:
                    self.bilgi("Dosya çok büyük", "Yedek dosyası en fazla 100 MB olabilir.")
                    return
                if not dosya.name.lower().endswith(".db") or dosya.bytes is None:
                    self.bilgi("Dosya okunamadı", "SQLite .db dosyası seçiniz ve tekrar deneyiniz.")
                    return
                yukleme = await self.cagir(self.api.post, "/yedekler/yukle", {
                    "dosya_adi": dosya.name,
                    "icerik": base64.b64encode(dosya.bytes).decode("ascii"),
                })
                if yukleme is not None:
                    self.bildir("Yedek sunucuya yüklendi. Geri yüklemek için listeden dosyayı seçiniz.")
                    await self.yedekleme_ekrani()
            finally:
                self.page.overlay.remove(picker)
                self.page.update()

        async def geri_yukle_ac(kayit: dict):
            onay = ft.TextField(label="Onay metni", hint_text="Devam için: GERI YUKLE", autofocus=True, width=240)

            async def uygula(e=None):
                sonuc = await self.cagir(self.api.post, "/yedekler/geri-yukle", {
                    "dosya_adi": kayit["dosya_adi"], "onay_metni": onay.value or "",
                })
                if sonuc is None:
                    return
                self.page.pop_dialog()
                self.bildir("Geri yükleme tamamlandı. Açık ekranları yenileyiniz.")
                await self.yedekleme_ekrani()

            self.page.show_dialog(ft.AlertDialog(
                title=ft.Text("Yedekten geri yükle"),
                content=ft.Column([
                    ft.Text("Mevcut veriler bu yedekle değiştirilecek. İşlemden önce otomatik yedek alınır.", selectable=True),
                    ft.Text(f"Seçilen dosya: {kayit['dosya_adi']}"),
                    onay,
                ], tight=True),
                actions=[ft.TextButton("Vazgeç", on_click=lambda e: self.page.pop_dialog()),
                         ft.FilledButton("Geri yükle", icon=ft.Icons.WARNING_AMBER, on_click=uygula)],
                modal=True))

        kontroller: list[ft.Control] = [
            kart(baslik("Yedekleme ve Geri Yükleme"),
                 ft.Text("Yedekler sunucunun yedek klasöründe tutulur. Geri yükleme yalnız yönetici rollerine açıktır.",
                         selectable=True),
                 ft.Text("Bu cihazdaki yerel SQLite veritabanı da .db dosyası seçilerek sunucuya aktarılabilir. "
                         "Yüklenen dosya önce listelenir; geri yükleme ayrıca açık onay ister.",
                         size=12, color=ft.Colors.BLUE_GREY_700, selectable=True),
                 ft.Row([ft.FilledButton("Şimdi yedekle", icon=ft.Icons.BACKUP, on_click=yeni_yedek),
                         ft.OutlinedButton("Dosyadan yedek yükle / yerel veriyi aktar",
                                           icon=ft.Icons.UPLOAD_FILE, on_click=dosya_yukle)],
                        wrap=True))
        ]
        if not v["yedekler"]:
            kontroller.append(mesaj_kutusu(["Henüz yedek dosyası bulunmuyor."], "bilgi"))
        for kayit in v["yedekler"]:
            eylemler = [ft.TextButton("İndir", icon=ft.Icons.DOWNLOAD,
                                      on_click=lambda e, ad=kayit["dosya_adi"]: self.page.run_task(indir, ad))]
            if v.get("yonetici"):
                eylemler.append(ft.TextButton("Bu yedekten geri yükle", icon=ft.Icons.RESTORE,
                                              style=ft.ButtonStyle(color=ft.Colors.RED_700),
                                              on_click=lambda e, yedek=kayit: self.page.run_task(geri_yukle_ac, yedek)))
            kontroller.append(kart(satir("Dosya", kayit["dosya_adi"], True),
                                   satir("Tarih", tarih(kayit["tarih"])),
                                   satir("Boyut", f"{kayit['boyut_kb']} KB"),
                                   ft.Row(eylemler, wrap=True)))
        self.ac(self.gorunum("Yedekleme", kontroller))

    async def islem_kaydi_ekrani(self, ara: str = "", istemci: str = "", kullanici_adi: str = "",
                                  baslangic: str = "", bitis: str = ""):
        v = await self.cagir(self.api.get, "/islem-kaydi", ara=ara, istemci=istemci,
                             kullanici_adi=kullanici_adi, baslangic=baslangic, bitis=bitis, sinir=1000)
        if v is None:
            return

        async def yenile(e=None):
            self.geri()
            await self.islem_kaydi_ekrani(t_ara.value or "", d_kaynak.value or "",
                                           d_kullanici.value or "", t_baslangic.value or "",
                                           t_bitis.value or "")

        async def excel_indir(e=None):
            sonuc = await self.cagir(
                self.api.get, "/islem-kaydi/excel", ara=t_ara.value or "",
                istemci=d_kaynak.value or "", kullanici_adi=d_kullanici.value or "",
                baslangic=t_baslangic.value or "", bitis=t_bitis.value or "",
            )
            if sonuc is None:
                return
            picker = ft.FilePicker()
            self.page.overlay.append(picker)
            self.page.update()
            try:
                yol = await picker.save_file(
                    dialog_title="İşlem kaydını Excel'e aktar",
                    file_name=sonuc["dosya_adi"],
                    src_bytes=base64.b64decode(sonuc["icerik"]),
                )
                if yol:
                    self.bildir(f"İşlem kaydı Excel'e aktarıldı: {yol}")
            finally:
                self.page.overlay.remove(picker)
                self.page.update()

        t_ara = ft.TextField(label="Ara (kullanıcı, kayıt, değişiklik)", value=ara, prefix_icon=ft.Icons.SEARCH, dense=True,
                             on_submit=yenile)
        d_kaynak = ft.Dropdown(label="Kaynak", value=istemci, width=150, dense=True, on_select=yenile,
                               options=[secenek("", "Tümü"), secenek("Masaüstü", "Masaüstü"), secenek("Mobil", "Mobil")])
        d_kullanici = ft.Dropdown(label="Kullanıcı", value=kullanici_adi, width=190, dense=True,
                                  on_select=yenile,
                                  options=[secenek("", "Tüm kullanıcılar")] +
                                          [secenek(n, n) for n in v["kullanicilar"]])
        t_baslangic = ft.TextField(label="Başlangıç (YYYY-AA-GG)", value=baslangic, width=175, dense=True,
                                   on_submit=yenile)
        t_bitis = ft.TextField(label="Bitiş (YYYY-AA-GG)", value=bitis, width=160, dense=True,
                               on_submit=yenile)
        kontroller = [
            ft.Row([t_ara, d_kullanici, d_kaynak, t_baslangic, t_bitis,
                    ft.FilledButton("Süz", icon=ft.Icons.FILTER_ALT, on_click=yenile),
                    ft.OutlinedButton("Excel'e aktar", icon=ft.Icons.TABLE_VIEW, on_click=excel_indir)],
                   wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Text(f"Son {len(v['kayitlar'])} işlem", color=ft.Colors.GREY_700),
        ]
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
        if self.api is None:
            return
        r = await self.cagir(self.api.get, f"/islem-kaydi/{kid}")
        if r is None:
            return
        kontroller: list[ft.Control] = [
            kart(satir("Zaman", tarih(r["zaman"])), satir("Kullanıcı", f"{r.get('ad_soyad') or ''} ({r.get('kullanici')})"),
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

    async def tanim_ekrani(self, tur: str, ara: str = ""):
        api = self.api
        if api is None:
            return
        sonuc = await self.cagir(api.get, f"/tanimlar/{tur}", ara=ara)
        if sonuc is None:
            return
        alanlar = sonuc["alanlar"]
        arama = ft.TextField(label="Kayıtlarda ara", value=ara, prefix_icon=ft.Icons.SEARCH,
                             dense=True, on_submit=lambda e: self.page.run_task(
                                 self.tanim_ekrani, tur, e.control.value or ""))
        kontroller: list[ft.Control] = [arama]
        if sonuc["yazabilir"]:
            kontroller.append(ft.FilledButton("Yeni kayıt", icon=ft.Icons.ADD,
                                              on_click=lambda e: self.page.run_task(self.tanim_formu, tur, alanlar)))
        for kayit in sonuc["kayitlar"]:
            if not isinstance(kayit, dict):
                continue
            ozet = []
            for alan in alanlar:
                deger = kayit.get(alan["anahtar"])
                if deger not in (None, ""):
                    secenek = next((x["etiket"] for x in alan["secenekler"] if x["deger"] == deger), None)
                    ozet.append(f"{alan['etiket']}: {secenek or deger}")
            async def ac(e, r=kayit):
                await self.tanim_formu(tur, alanlar, r, sonuc["yazabilir"])
            kontroller.append(ft.Card(content=ft.ListTile(
                title=ft.Text(str(kayit.get("ad_soyad") or kayit.get("unvan") or kayit.get("ad") or
                                  kayit.get("kod") or f"Kayıt #{kayit['id']}"),
                              weight=ft.FontWeight.BOLD),
                subtitle=ft.Text("\n".join(ozet[:5]), max_lines=5, overflow=ft.TextOverflow.ELLIPSIS),
                is_three_line=True, trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT), on_click=ac)))
        if not sonuc["kayitlar"]:
            kontroller.append(ft.Text("Aramanızla eşleşen kayıt bulunamadı."))
        self.ac(self.gorunum(sonuc["baslik"], kontroller))

    async def tanim_formu(self, tur: str, alanlar: list[dict], kayit: dict | None = None,
                          yazabilir: bool = True):
        api = self.api
        if api is None:
            return
        alan_kontroller: dict[str, ft.TextField | ft.Dropdown | ft.Checkbox] = {}
        kontroller: list[ft.Control] = []
        for alan in alanlar:
            key, label, tip = alan["anahtar"], alan["etiket"], alan["tur"]
            value = (kayit or {}).get(key)
            if tip == "bool":
                control = ft.Checkbox(label=label, value=bool(value), disabled=not yazabilir)
            elif tip in ("secim", "fk"):
                secenekler = alan["secenekler"]
                secim_value = None
                for secim in secenekler:
                    if str(secim["deger"]) == str(value):
                        secim_value = str(secim["deger"])
                        break
                control = ft.Dropdown(
                    label=label, value=secim_value, disabled=not yazabilir,
                    options=[secenek(str(secim["deger"]), secim["etiket"]) for secim in secenekler])
            else:
                control = ft.TextField(
                    label=label, value="" if value is None else str(value),
                    multiline=tip == "cokmetin", min_lines=2 if tip == "cokmetin" else 1,
                    disabled=not yazabilir)
                if tip in ("para", "oran", "ondalik"):
                    control.keyboard_type = ft.KeyboardType.NUMBER
            alan_kontroller[key] = control
            kontroller.append(control)

        async def kaydet(e):
            degerler = {}
            try:
                for alan in alanlar:
                    key, tip = alan["anahtar"], alan["tur"]
                    control = alan_kontroller[key]
                    value = control.value
                    if tip == "bool":
                        degerler[key] = bool(value)
                    elif tip in ("para", "oran", "ondalik"):
                        degerler[key] = sayi(value, alan["etiket"]) if value else None
                    elif tip == "tarih":
                        degerler[key] = iso_tarih(value, alan["etiket"])
                    elif tip == "fk":
                        degerler[key] = int(value) if value else None
                    else:
                        degerler[key] = value or None
            except ValueError as hata:
                self.bilgi("Geçersiz değer", str(hata))
                return
            govde = {"degerler": degerler}
            sonuc = (await self.cagir(api.put, f"/tanimlar/{tur}/{kayit['id']}", govde)
                     if kayit else await self.cagir(api.post, f"/tanimlar/{tur}", govde))
            if sonuc is None:
                return
            self.geri()
            self.bildir("Kayıt güncellendi." if kayit else "Kayıt oluşturuldu.")
            await self.tanim_ekrani(tur)

        eylemler: list[ft.Control] = []
        if tur == "urun" and kayit:
            eylemler.append(ft.OutlinedButton(
                "Maliyet Analizi / Fiyat Tespiti", icon=ft.Icons.CALCULATE_OUTLINED,
                on_click=lambda e: self.page.run_task(self.urun_maliyet_ekrani, kayit["id"])))
        if yazabilir:
            eylemler.append(ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, on_click=kaydet))
        if kayit and yazabilir:
            async def sil():
                sonuc = await self.cagir(api.delete, f"/tanimlar/{tur}/{kayit['id']}")
                if sonuc is None:
                    return
                self.geri()
                self.bildir("Kayıt silindi.")
                await self.tanim_ekrani(tur)
            eylemler.append(ft.OutlinedButton(
                "Kaydı sil", icon=ft.Icons.DELETE_OUTLINE,
                style=ft.ButtonStyle(color=ft.Colors.RED_700),
                on_click=lambda e: self.sor("Kaydı sil", "Bu kayıt silinsin mi?", sil, "Sil")))
        kontroller.extend(eylemler)
        self.ac(self.gorunum("Kaydı düzenle" if kayit else "Yeni kayıt", kontroller))

    async def urun_maliyet_ekrani(self, urun_id: int):
        api = self.api
        if api is None:
            return
        sonuc = await self.cagir(api.get, f"/urun/{urun_id}/maliyet")
        if sonuc is None:
            return
        urun = sonuc["urun"]
        malzemeler = {str(m["id"]): m for m in sonuc["malzemeler"]}
        kalem_turleri = sonuc["kalem_turleri"]
        kayitli = bool(sonuc["kalemler"])
        oto = ft.Checkbox(label="İşçilik ve diğer giderleri yasal üst sınıra göre otomatik hesapla",
                          value=not kayitli or any(k.get("aciklama") in (
                              "Yasal üst sınır (otomatik)", "İşçiliğin asgari payı (otomatik)",
                              "Faaliyet gideri payının kalanı (otomatik)") for k in sonuc["kalemler"]),
                          disabled=not sonuc["yazabilir"])
        hedef_fiyat = ft.TextField(
            label="Hedef birim satış fiyatı (KDV hariç)",
            value=str(urun.get("satis_fiyati") or 0), keyboard_type=ft.KeyboardType.NUMBER,
            disabled=not sonuc["yazabilir"])
        hedef_dahil = ft.TextField(label="Hedef KDV dahil fiyat", value="0",
                                   keyboard_type=ft.KeyboardType.NUMBER, disabled=not sonuc["yazabilir"])
        kar = ft.TextField(label="Kâr oranı", value=str(urun.get("kar_orani") or 0.1),
                           keyboard_type=ft.KeyboardType.NUMBER,                            disabled=not sonuc["yazabilir"] or bool(oto.value))
        kdv = ft.TextField(label="KDV oranı", value=str(urun.get("kdv_orani") or 0.2),
                           keyboard_type=ft.KeyboardType.NUMBER, disabled=not sonuc["yazabilir"])
        piyasa = ft.TextField(label="Piyasa araştırması / değerlendirme (tutanağa yazılır)",
                              multiline=True, min_lines=2, max_lines=5, disabled=not sonuc["yazabilir"])
        satir_kutusu = ft.Column(spacing=8)
        sonuc_kutusu = ft.Column(spacing=8)
        satirlar = [{
            "kalem_turu": k["kalem_turu"], "aciklama": k.get("aciklama") or "",
            "malzeme_id": k.get("malzeme_id"), "miktar": k.get("miktar") or 0,
            "birim_fiyat": k.get("birim_fiyat") or 0,
        } for k in sonuc["kalemler"]]
        if not satirlar:
            satirlar = [
                {"kalem_turu": "Direkt İlk Madde ve Malzeme", "miktar": 1, "birim_fiyat": 0},
                {"kalem_turu": "Direkt İşçilik (Personel)", "miktar": 1, "birim_fiyat": 0},
                {"kalem_turu": "Öğrenci Hakkı", "miktar": 1, "birim_fiyat": 0},
                {"kalem_turu": "Enerji (Elektrik/Gaz/Su)", "miktar": 1, "birim_fiyat": 0},
                {"kalem_turu": "Amortisman / Bakım-Onarım", "miktar": 1, "birim_fiyat": 0},
            ]

        def satirlari_goster():
            satir_kutusu.controls.clear()
            for idx, row in enumerate(satirlar):
                tur = ft.Dropdown(
                    label="Maliyet unsuru", value=row.get("kalem_turu"), expand=True,
                    disabled=not sonuc["yazabilir"],
                    options=[secenek(t, t) for t in kalem_turleri])
                aciklama = ft.TextField(label="Açıklama", value=row.get("aciklama") or "",
                                        expand=True, disabled=not sonuc["yazabilir"])
                malzeme = ft.Dropdown(
                    label="Malzeme (stok)", value=str(row["malzeme_id"]) if row.get("malzeme_id") else "",
                    expand=True, disabled=not sonuc["yazabilir"],
                    options=[secenek("", "—")] + [secenek(m["id"], f"{m['ad']} • Ort. {para(m['ortalama_maliyet'])} TL")
                                                   for m in sonuc["malzemeler"]])
                miktar = ft.TextField(label="Miktar", value=str(row.get("miktar") or 0), width=130,
                                      keyboard_type=ft.KeyboardType.NUMBER, disabled=not sonuc["yazabilir"])
                birim_fiyat = ft.TextField(label="Birim fiyat", value=str(row.get("birim_fiyat") or 0), width=150,
                                           keyboard_type=ft.KeyboardType.NUMBER, disabled=not sonuc["yazabilir"])
                row["kontroller"] = (tur, aciklama, malzeme, miktar, birim_fiyat)

                def malzeme_secildi(e, fiyat=birim_fiyat, secim=malzeme):
                    secili = malzemeler.get(secim.value or "")
                    if secili:
                        fiyat.value = str(secili["ortalama_maliyet"])
                        self.page.update()

                malzeme.on_select = malzeme_secildi

                async def kaldir(e, i=idx):
                    satirlar.pop(i)
                    satirlari_goster()

                satir_kutusu.controls.append(ft.Card(content=ft.Container(ft.Column([
                    ft.Row([tur, aciklama], wrap=True),
                    ft.Row([malzeme, miktar, birim_fiyat,
                            ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Satırı sil",
                                          on_click=kaldir, disabled=not sonuc["yazabilir"])], wrap=True),
                ], spacing=6), padding=10)))
            self.page.update()

        def payload(hedef=None):
            def sayi_zorunlu(kontrol, etiket):
                deger = sayi(kontrol.value, etiket)
                if deger is None:
                    raise ValueError(f"{etiket} boş bırakılamaz.")
                return deger

            kalemler = []
            for row in satirlar:
                tur, aciklama, malzeme, miktar, fiyat = row["kontroller"]
                kalemler.append({
                    "kalem_turu": tur.value,
                    "aciklama": aciklama.value or "",
                    "malzeme_id": int(malzeme.value) if malzeme.value else None,
                    "miktar": sayi_zorunlu(miktar, "Miktar"),
                    "birim_fiyat": sayi_zorunlu(fiyat, "Birim fiyat"),
                })
            return {
                "oto": bool(oto.value), "hedef_fiyat": sayi_zorunlu(hedef_fiyat, "Hedef fiyat"),
                "hedef_dahil": hedef, "kar_orani": sayi_zorunlu(kar, "Kâr oranı"),
                "kdv_orani": sayi_zorunlu(kdv, "KDV oranı"), "piyasa": piyasa.value or "",
                "kalemler": kalemler,
            }

        def sonucu_goster(hesap):
            o = hesap["ozet"]
            sonuc_kutusu.controls = [kart(
                baslik("Birim fiyat hesabı"),
                satir("Birim maliyet", para(o["birim_maliyet"]) + " TL"),
                satir("Kâr / oran", f"{para(o['kar'])} TL / %{o['kar_orani'] * 100:.3f}"),
                satir("KDV hariç / dahil satış fiyatı",
                      f"{para(o['satis_fiyati'])} / {para(o['kdv_dahil'])} TL", True),
                satir("Otomatik dağılım", hesap["oto_bilgi"]),
            )]
            for mesaj in hesap["hatalar"]:
                sonuc_kutusu.controls.append(mesaj_kutusu([mesaj], "hata"))
            for mesaj in hesap["uyarilar"]:
                sonuc_kutusu.controls.append(mesaj_kutusu([mesaj], "uyari"))
            if not hesap["hatalar"] and not hesap["uyarilar"]:
                sonuc_kutusu.controls.append(mesaj_kutusu(
                    ["Maliyet unsurları mevzuat oranlarıyla uyumlu."], "bilgi"))
            self.page.update()

        async def hesapla(e=None, hedef=None):
            try:
                veri = payload(hedef)
            except ValueError as err:
                self.bilgi("Geçersiz değer", str(err))
                return None
            hesap = await self.cagir(api.post, f"/urun/{urun_id}/maliyet/hesapla", veri)
            if hesap is None:
                return None
            satirlar[:] = [{
                "kalem_turu": k["kalem_turu"], "aciklama": k.get("aciklama") or "",
                "malzeme_id": k.get("malzeme_id"), "miktar": k["miktar"],
                "birim_fiyat": k["birim_fiyat"],
            } for k in hesap["kalemler"]]
            kar.value = str(hesap["kar_orani"])
            kar.disabled = not sonuc["yazabilir"] or bool(oto.value)
            satirlari_goster()
            sonucu_goster(hesap)
            return hesap

        async def kaydet(e=None):
            try:
                veri = payload()
            except ValueError as err:
                self.bilgi("Geçersiz değer", str(err))
                return
            kayit_sonucu = await self.cagir(api.put, f"/urun/{urun_id}/maliyet", veri)
            if kayit_sonucu is not None:
                satirlar[:] = [{
                    "kalem_turu": k["kalem_turu"], "aciklama": k.get("aciklama") or "",
                    "malzeme_id": k.get("malzeme_id"), "miktar": k["miktar"],
                    "birim_fiyat": k["birim_fiyat"],
                } for k in kayit_sonucu["kalemler"]]
                satirlari_goster()
                sonucu_goster(kayit_sonucu)
                self.bildir("Maliyet analizi kaydedildi.")

        async def fiyat_isle(e=None):
            try:
                veri = payload()
            except ValueError as err:
                self.bilgi("Geçersiz değer", str(err))
                return

            async def uygula():
                kayit_sonucu = await self.cagir(api.post, f"/urun/{urun_id}/maliyet/fiyat", veri)
                if kayit_sonucu:
                    self.bildir(f"Ürün kartı fiyatı {para(kayit_sonucu['satis_fiyati'])} TL olarak güncellendi.")

            self.sor("Satış fiyatını güncelle",
                     "Ürünün KDV hariç satış fiyatı hesaplanan birim fiyata güncellensin mi?",
                     uygula, "Fiyatı güncelle")

        async def tutanak(e=None):
            try:
                veri = payload()
            except ValueError as err:
                self.bilgi("Geçersiz değer", str(err))
                return
            dosya = await self.cagir(api.post, f"/urun/{urun_id}/maliyet/tutanak", veri)
            if dosya is None:
                return
            picker = ft.FilePicker()
            self.page.overlay.append(picker)
            self.page.update()
            try:
                yol = await picker.save_file(
                    dialog_title="Fiyat tespit tutanağını kaydet",
                    file_name=dosya["dosya_adi"], src_bytes=base64.b64decode(dosya["icerik"]))
                if yol:
                    self.bildir(f"Fiyat tespit tutanağı kaydedildi: {yol}")
            finally:
                self.page.overlay.remove(picker)
                self.page.update()

        def satir_ekle(e=None):
            satirlar.append({"kalem_turu": kalem_turleri[0], "miktar": 1, "birim_fiyat": 0})
            satirlari_goster()

        def oto_degisti(e=None):
            kar.disabled = not sonuc["yazabilir"] or bool(oto.value)
            self.page.update()

        oto.on_change = oto_degisti
        satirlari_goster()
        eylemler: list[ft.Control] = [ft.OutlinedButton("＋ Satır", on_click=satir_ekle, disabled=not sonuc["yazabilir"]),
                                      ft.OutlinedButton("Hesapla", icon=ft.Icons.CALCULATE, on_click=hesapla)]
        if sonuc["yazabilir"]:
            async def hedeften(e=None):
                try:
                    hedef = sayi(hedef_dahil.value, "Hedef KDV dahil fiyat")
                except ValueError as err:
                    self.bilgi("Geçersiz değer", str(err))
                    return
                if hedef is None:
                    self.bilgi("Geçersiz değer", "Hedef fiyatı giriniz.")
                    return
                await hesapla(hedef=hedef)

            eylemler.extend([
                ft.OutlinedButton("Kâr oranını hedeften hesapla", on_click=hedeften),
                ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, on_click=kaydet),
                ft.OutlinedButton("Fiyatı ürün kartına işle", on_click=fiyat_isle),
                ft.OutlinedButton("Fiyat Tespit Tutanağı (PDF)", icon=ft.Icons.PICTURE_AS_PDF, on_click=tutanak),
            ])
        self.ac(self.gorunum(f"Maliyet Analizi • {urun['ad']}", [
            ft.Text("Değerler ürünün bir birimi içindir. Otomatik hesaplama, seçilen ücret esasının mevzuat sınırlarını uygular.",
                    size=12, color=ft.Colors.BLUE_GREY_700),
            ft.Row([oto, hedef_fiyat, hedef_dahil], wrap=True),
            ft.Row([kar, kdv], wrap=True), piyasa, satir_kutusu, sonuc_kutusu,
            ft.Row(eylemler, wrap=True),
        ]))

    async def parametre_ekrani(self):
        api = self.api
        if api is None:
            return
        sonuc = await self.cagir(api.get, "/parametreler", yil=self.yil)
        if sonuc is None:
            return
        kontroller: list[ft.Control] = [
            ft.Text(f"{sonuc['yil']} yılı mevzuat parametreleri. Hesaplamalarda işlem yılına ait değerler kullanılır.",
                    color=ft.Colors.BLUE_GREY_700)]
        alanlar = {}
        for parametre in sonuc["parametreler"]:
            key, tip = parametre["anahtar"], parametre["tur"]
            if tip in ("oran", "para", "sayi"):
                control = ft.TextField(label=parametre["etiket"], value=str(parametre["deger"]),
                                       keyboard_type=ft.KeyboardType.NUMBER, disabled=not sonuc["yazabilir"])
            else:
                control = ft.TextField(label=parametre["etiket"], value=str(parametre["deger"]),
                                       multiline=True, min_lines=2, max_lines=6,
                                       disabled=not sonuc["yazabilir"])
            alanlar[key] = control
            kontroller.append(control)
            if parametre.get("aciklama"):
                kontroller.append(ft.Text(parametre["aciklama"], size=12, color=ft.Colors.GREY_700))

        async def kaydet(e):
            degerler = {}
            try:
                for parametre in sonuc["parametreler"]:
                    key, tip = parametre["anahtar"], parametre["tur"]
                    value = alanlar[key].value or ""
                    if tip in ("oran", "para", "sayi"):
                        degerler[key] = sayi(value, parametre["etiket"])
                        if degerler[key] is None:
                            raise ValueError(f"{parametre['etiket']} boş bırakılamaz.")
                    else:
                        json.loads(value)
                        degerler[key] = value
            except (ValueError, json.JSONDecodeError) as hata:
                self.bilgi("Geçersiz parametre", str(hata))
                return
            kayit = await self.cagir(
                api.put, f"/parametreler?yil={self.yil}", {"degerler": degerler})
            if kayit is None:
                return
            self.bildir(f"{self.yil} yılı mevzuat parametreleri kaydedildi.")
            await self.parametre_ekrani()

        if sonuc["yazabilir"]:
            kontroller.append(ft.FilledButton("Parametreleri kaydet", icon=ft.Icons.SAVE, on_click=kaydet))
        self.ac(self.gorunum("Mevzuat Parametreleri", kontroller))

    async def kurum_ekrani(self):
        api = self.api
        if api is None:
            return
        sonuc = await self.cagir(api.get, "/kurum")
        if sonuc is None:
            return
        alan_tanimlari = [
            ("okul_adi", "Okul adı", "metin"), ("isletme_adi", "İşletme adı", "metin"),
            ("kurum_kodu", "Kurum kodu", "metin"), ("il", "İl", "metin"), ("ilce", "İlçe", "metin"),
            ("adres", "Adres", "cokmetin"), ("telefon", "Telefon", "metin"), ("eposta", "E-posta", "metin"),
            ("evrak_kodu", "Evrak sayı öneki", "metin"), ("vergi_dairesi", "Vergi dairesi", "metin"),
            ("vkn", "Vergi kimlik no", "metin"), ("banka", "Banka / şube", "metin"),
            ("iban", "IBAN", "metin"), ("harcama_yetkilisi", "Harcama yetkilisi", "metin"),
            ("gerceklestirme_gorevlisi", "Gerçekleştirme görevlisi", "metin"),
            ("sayman", "Sayman", "metin"), ("tahsis_sermaye", "Tahsis edilen sermaye (TL)", "para"),
            ("odenmis_sermaye", "Ödenmiş sermaye (TL)", "para"),
            ("buyuksehir", "Büyükşehir belediyesi sınırları içinde", "bool"),
            ("yuz_yuze_egitim", "Öğrenci ile yüz yüze eğitim yapan işletme", "bool"),
        ]
        kayit = sonuc["kayit"]
        alanlar: dict[str, ft.TextField | ft.Checkbox] = {}
        kontroller: list[ft.Control] = [
            ft.Text("Belgelerin antetinde, imza bloklarında ve yıl sonu kâr bölüşümünde kullanılır.",
                    color=ft.Colors.BLUE_GREY_700)]
        for key, label, tip in alan_tanimlari:
            if tip == "bool":
                control = ft.Checkbox(label=label, value=bool(kayit.get(key)), disabled=not sonuc["yazabilir"])
            else:
                control = ft.TextField(
                    label=label, value="" if kayit.get(key) is None else str(kayit[key]),
                    multiline=tip == "cokmetin", min_lines=3 if tip == "cokmetin" else 1,
                    disabled=not sonuc["yazabilir"] or (key == "kurum_kodu" and sonuc["kurum_kodu_kilitli"]))
                if tip == "para":
                    control.keyboard_type = ft.KeyboardType.NUMBER
            alanlar[key] = control
            kontroller.append(control)
        if sonuc["kurum_kodu_kilitli"]:
            kontroller.append(ft.Text("Lisans bu kurum koduna bağlıdır; değiştirilemez.",
                                     size=12, color=ft.Colors.BLUE_GREY_700))

        async def kaydet(e):
            degerler = {}
            try:
                for key, _label, tip in alan_tanimlari:
                    value = alanlar[key].value
                    degerler[key] = (bool(value) if tip == "bool" else
                                     sayi(value, key) if tip == "para" and value else
                                     0 if tip == "para" else value or None)
            except ValueError as hata:
                self.bilgi("Geçersiz değer", str(hata))
                return
            sonuc_kaydet = await self.cagir(api.put, "/kurum", {"degerler": degerler})
            if sonuc_kaydet is not None:
                self.bildir("Kurum bilgileri kaydedildi.")
                await self.kurum_ekrani()

        if sonuc["yazabilir"]:
            kontroller.append(ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, on_click=kaydet))
        self.ac(self.gorunum("Kurum ve Görevliler", kontroller))

    async def muhasebe_ekrani(self, sekme: str = "yevmiye", baslangic: str | None = None,
                              bitis: str | None = None):
        api = self.api
        if api is None:
            return
        baslangic = baslangic or f"{self.yil}-01-01"
        bitis = bitis or f"{self.yil}-12-31"
        sonuc = await self.cagir(api.get, "/muhasebe", yil=self.yil,
                                 baslangic=baslangic, bitis=bitis)
        if sonuc is None:
            return

        async def donem_sec(e):
            await self.muhasebe_ekrani(sekme, bas.value or "", bit.value or "")

        bas = ft.TextField(label="Başlangıç", value=baslangic, width=170,
                           hint_text="YYYY-AA-GG")
        bit = ft.TextField(label="Bitiş", value=bitis, width=170,
                           hint_text="YYYY-AA-GG")
        kontroller: list[ft.Control] = [
            ft.Row([bas, bit, ft.FilledButton("Dönemi uygula", icon=ft.Icons.FILTER_ALT,
                                               on_click=donem_sec)], wrap=True),
            ft.Row([
                ft.OutlinedButton("Yevmiye", on_click=lambda e: self.page.run_task(
                    self.muhasebe_ekrani, "yevmiye", bas.value, bit.value)),
                ft.OutlinedButton("Mizan", on_click=lambda e: self.page.run_task(
                    self.muhasebe_ekrani, "mizan", bas.value, bit.value)),
                ft.OutlinedButton("Gelir tablosu", on_click=lambda e: self.page.run_task(
                    self.muhasebe_ekrani, "gelir", bas.value, bit.value)),
                ft.OutlinedButton("Hesap planı", on_click=lambda e: self.page.run_task(
                    self.muhasebe_ekrani, "hesap", bas.value, bit.value)),
            ], wrap=True),
        ]
        if sekme == "yevmiye":
            if sonuc["yazabilir"]:
                async def manuel_fis(e):
                    await self.muhasebe_manuel_fis(baslangic, bitis)
                kontroller.append(ft.FilledButton("Manuel fiş", icon=ft.Icons.ADD,
                                                   on_click=manuel_fis))
            if sonuc["yeniden_uretebilir"] and sonuc["yazabilir"]:
                async def yeniden_uret(e):
                    async def calistir():
                        sonuc_yenile = await self.cagir(api.post, "/muhasebe/yeniden-uret")
                        if sonuc_yenile is None:
                            return
                        self.bildir(f"Yardımcı yevmiye kayıtları yeniden üretildi. Fiş sayısı: "
                                    f"{sonuc_yenile['fis_sayisi']}")
                        await self.muhasebe_ekrani("yevmiye", baslangic, bitis)
                    self.sor(
                        "Kayıtları yeniden üret",
                        "Manuel fişler korunur; diğer yevmiye kayıtları kaynak işlemlerden yeniden oluşturulur. "
                        "Fiş numaraları değişebilir. Devam edilsin mi?",
                        calistir, "Yeniden üret")
                kontroller.append(ft.OutlinedButton(
                    "Kayıtları yeniden üret", icon=ft.Icons.REFRESH, on_click=yeniden_uret))
            kontroller.append(baslik("Yardımcı yevmiye fişleri"))
            for fis in sonuc["fisler"]:
                async def ac(e, fid=fis["id"]):
                    await self.muhasebe_fis_detayi(fid)
                dengeli = abs(fis["borc"] - fis["alacak"]) < 0.01
                kontroller.append(ft.Card(content=ft.ListTile(
                    title=ft.Text(f"{fis['fis_no']} • {fis['aciklama']}", weight=ft.FontWeight.BOLD),
                    subtitle=ft.Text(f"{tarih(fis['tarih'])} • {fis['kaynak']}"),
                    trailing=ft.Text(f"Borç {para(fis['borc'])} / Alacak {para(fis['alacak'])}",
                                     color=ft.Colors.GREEN_800 if dengeli else ft.Colors.RED_700),
                    on_click=ac)))
            if not sonuc["fisler"]:
                kontroller.append(ft.Text("Bu tarih aralığında yevmiye fişi bulunamadı."))
        elif sekme == "mizan":
            mizan = sonuc["mizan"]
            toplam_borc = sum(row["borc"] or 0 for row in mizan)
            toplam_alacak = sum(row["alacak"] or 0 for row in mizan)
            kontroller.append(kart(
                satir("Toplam borç", para(toplam_borc) + " TL", True),
                satir("Toplam alacak", para(toplam_alacak) + " TL", True),
                satir("Kontrol", "Denk" if abs(toplam_borc - toplam_alacak) < 0.01 else "DENGESİZ",
                      True, ft.Colors.GREEN_800 if abs(toplam_borc - toplam_alacak) < 0.01 else ft.Colors.RED_700)))
            for row in mizan:
                kontroller.append(kart(
                    ft.Text(f"{row['kod']} • {row['ad']}", weight=ft.FontWeight.BOLD),
                    satir("Borç / Alacak", f"{para(row['borc'])} / {para(row['alacak'])} TL"),
                    satir("Borç / Alacak bakiyesi",
                          f"{para(row['borc_bakiye'])} / {para(row['alacak_bakiye'])} TL")))
        elif sekme == "gelir":
            gelir = sonuc["gelir_tablosu"]
            kontroller.append(baslik("Gelirler"))
            kontroller.extend(kart(ft.Text(f"{row['kod']} • {row['ad']}"),
                                   satir("Tutar", para(row["tutar"]) + " TL", True))
                              for row in gelir["gelirler"])
            kontroller.append(satir("Toplam gelir", para(gelir["toplam_gelir"]) + " TL", True))
            kontroller.append(baslik("Giderler"))
            kontroller.extend(kart(ft.Text(f"{row['kod']} • {row['ad']}"),
                                   satir("Tutar", para(row["tutar"]) + " TL", True))
                              for row in gelir["giderler"])
            kontroller.extend([
                satir("Toplam gider", para(gelir["toplam_gider"]) + " TL", True),
                satir("Dönem kârı / zararı", para(gelir["kar"]) + " TL", True),
            ])
        else:
            kontroller.append(baslik("Hesap planı"))
            if sonuc["yazabilir"]:
                kontroller.append(ft.FilledButton(
                    "Hesap ekle", icon=ft.Icons.ADD,
                    on_click=lambda e: self.page.run_task(self.muhasebe_hesap_ekle, baslangic, bitis)))
            for row in sonuc["hesap_plani"]:
                trailing = None
                if sonuc["yazabilir"] and sonuc["hesap_silebilir"]:
                    async def sil(e, kod=row["kod"], ad=row["ad"]):
                        async def onayla():
                            silindi = await self.cagir(api.delete, f"/muhasebe/hesap-plani/{kod}")
                            if silindi is None:
                                return
                            self.bildir(f"{kod} • {ad} hesabı silindi.")
                            await self.muhasebe_ekrani("hesap", baslangic, bitis)
                        self.sor("Hesabı sil", f"{kod} • {ad} hesap planından silinsin mi?",
                                 onayla, "Hesabı sil")
                    trailing = ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip="Hesabı sil", on_click=sil)
                kontroller.append(ft.Card(content=ft.ListTile(
                    title=ft.Text(f"{row['kod']} • {row['ad']}"), trailing=trailing)))
        self.ac(self.gorunum("Muhasebe • " + {
            "yevmiye": "Yevmiye", "mizan": "Mizan", "gelir": "Gelir tablosu", "hesap": "Hesap planı"
        }.get(sekme, "Yevmiye"), kontroller))

    async def muhasebe_hesap_ekle(self, baslangic: str, bitis: str):
        api = self.api
        if api is None:
            return
        kod = ft.TextField(label="Hesap kodu", max_length=40)
        ad = ft.TextField(label="Hesap adı", max_length=200)

        async def kaydet(e):
            if not (kod.value or "").strip() or not (ad.value or "").strip():
                self.bilgi("Eksik bilgi", "Hesap kodu ve adı zorunludur.")
                return
            kayit = await self.cagir(api.post, "/muhasebe/hesap-plani", {
                "kod": kod.value.strip(), "ad": ad.value.strip(),
            })
            if kayit is None:
                return
            self.bildir("Hesap planına yeni hesap eklendi.")
            self.geri()
            await self.muhasebe_ekrani("hesap", baslangic, bitis)

        self.ac(self.gorunum("Hesap planına hesap ekle", [
            ft.Text("Yeni hesap kodunu kurumunuzun muhasebe hesap planına göre giriniz.",
                    color=ft.Colors.BLUE_GREY_700),
            kod, ad,
            ft.Row([
                ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, on_click=kaydet),
                ft.TextButton("Vazgeç", on_click=lambda e: self.geri()),
            ], wrap=True),
        ]))

    async def muhasebe_fis_detayi(self, fis_id: int):
        api = self.api
        if api is None:
            return
        fis = await self.cagir(api.get, f"/muhasebe/yevmiye/{fis_id}")
        if fis is None:
            return
        kontroller: list[ft.Control] = [
            kart(satir("Fiş no", fis["fis_no"]), satir("Tarih", tarih(fis["tarih"])),
                 satir("Kaynak", fis["kaynak"]), satir("Açıklama", fis["aciklama"]))]
        kontroller.extend(ft.Card(content=ft.ListTile(
            title=ft.Text(f"{row['hesap_kodu']} • {row['hesap_adi'] or row['aciklama'] or 'Tanımsız hesap'}",
                          weight=ft.FontWeight.BOLD),
            subtitle=ft.Text(f"{row['aciklama'] or ''}\nBorç {para(row['borc'])} TL • Alacak {para(row['alacak'])} TL")))
                          for row in fis["satirlar"])
        if fis["yazabilir"] and fis["kaynak"] == "Manuel":
            async def sil():
                sonuc = await self.cagir(api.delete, f"/muhasebe/yevmiye/{fis_id}")
                if sonuc is None:
                    return
                self.bildir("Manuel yevmiye fişi silindi.")
                self.geri()
                await self.muhasebe_ekrani()
            kontroller.append(ft.OutlinedButton("Manuel fişi sil", icon=ft.Icons.DELETE_OUTLINE,
                                                on_click=lambda e: self.sor(
                                                    "Fişi sil", "Bu manuel fiş ve satırları silinecek. Devam edilsin?",
                                                    sil, "Fişi sil")))
        self.ac(self.gorunum(f"Yevmiye {fis['fis_no']}", kontroller))

    async def muhasebe_manuel_fis(self, baslangic: str, bitis: str):
        api = self.api
        if api is None:
            return
        sonuc = await self.cagir(api.get, "/muhasebe", yil=self.yil)
        if sonuc is None:
            return
        tarih_alani = ft.TextField(label="Fiş tarihi", value=date.today().isoformat(),
                                   hint_text="YYYY-AA-GG", width=190)
        aciklama = ft.TextField(label="Fiş açıklaması", max_length=500)
        satirlar: list[dict[str, ft.Control]] = []
        satir_kutusu = ft.Column(spacing=8)
        hesap_secenekleri = [secenek(row["kod"], f"{row['kod']} • {row['ad']}")
                             for row in sonuc["hesap_plani"]]

        def satir_ekle(e=None):
            satirlar.append({
                "hesap": ft.Dropdown(label="Hesap", options=hesap_secenekleri, width=220),
                "aciklama": ft.TextField(label="Satır açıklaması", width=190, max_length=500),
                "borc": ft.TextField(label="Borç", width=120, keyboard_type=ft.KeyboardType.NUMBER),
                "alacak": ft.TextField(label="Alacak", width=120, keyboard_type=ft.KeyboardType.NUMBER),
            })
            satirlari_goster()

        def satirlari_goster():
            satir_kutusu.controls = []
            for kayit in satirlar:
                async def sil(e, secili=kayit):
                    satirlar.remove(secili)
                    satirlari_goster()
                    self.page.update()
                satir_kutusu.controls.append(ft.Row([
                    kayit["hesap"], kayit["aciklama"], kayit["borc"], kayit["alacak"],
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip="Satırı sil", on_click=sil)
                ], wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER))
            self.page.update()

        async def kaydet(e):
            try:
                fis_tarihi = iso_tarih(tarih_alani.value, "Fiş tarihi")
                if not fis_tarihi:
                    raise ValueError("Fiş tarihi zorunludur.")
                if not (aciklama.value or "").strip():
                    raise ValueError("Fiş açıklaması zorunludur.")
                satir_govdeleri = []
                for i, row in enumerate(satirlar, 1):
                    borc = sayi(row["borc"].value, f"{i}. satır borç") or 0
                    alacak = sayi(row["alacak"].value, f"{i}. satır alacak") or 0
                    satir_govdeleri.append({
                        "hesap_kodu": row["hesap"].value or "",
                        "aciklama": row["aciklama"].value or "",
                        "borc": borc, "alacak": alacak,
                    })
            except ValueError as hata:
                self.bilgi("Geçersiz fiş", str(hata))
                return
            kayit = await self.cagir(api.post, "/muhasebe/yevmiye", {
                "tarih": fis_tarihi, "aciklama": aciklama.value.strip(), "satirlar": satir_govdeleri,
            })
            if kayit is None:
                return
            self.bildir("Manuel yevmiye fişi kaydedildi.")
            self.geri()
            await self.muhasebe_ekrani("yevmiye", baslangic, bitis)

        satir_ekle()
        satir_ekle()
        self.ac(self.gorunum("Manuel yevmiye fişi", [
            ft.Row([tarih_alani, aciklama], wrap=True),
            baslik("Fiş satırları"),
            satir_kutusu,
            ft.Row([
                ft.OutlinedButton("Satır ekle", icon=ft.Icons.ADD, on_click=satir_ekle),
                ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, on_click=kaydet),
                ft.TextButton("Vazgeç", on_click=lambda e: self.geri()),
            ], wrap=True),
        ]))

    async def rapor_ekrani(self, rapor: str = "siparis", yil: int | None = None):
        api = self.api
        if api is None:
            return
        yil = yil or self.yil
        veri = await self.cagir(api.get, "/raporlar", rapor=rapor, yil=yil)
        if veri is None:
            return

        async def rapor_degisti(e):
            await self.rapor_ekrani(e.control.value, yil)

        async def yil_degisti(e):
            await self.rapor_ekrani(rapor, int(e.control.value))

        secim = ft.Dropdown(
            label="Rapor", value=rapor, width=360,
            options=[secenek(row["id"], row["baslik"]) for row in veri["secenekler"]],
            on_select=rapor_degisti)
        yil_secim = ft.Dropdown(
            label="Çalışma yılı", value=str(yil), width=140,
            options=[secenek(y, y) for y in range(date.today().year - 5, date.today().year + 1)],
            on_select=yil_degisti)
        toplamlar = veri["ozet"]["toplamlar"]
        toplam_metinleri = [
            f"{kolon['baslik']}: {para(toplamlar[kolon['anahtar']])} TL"
            for kolon in veri["kolonlar"] if kolon["anahtar"] in toplamlar
        ][:4]
        kontroller: list[ft.Control] = [
            ft.Row([
                secim, yil_secim,
                ft.OutlinedButton("Excel", icon=ft.Icons.TABLE_VIEW,
                                  on_click=lambda e: self.page.run_task(
                                      self.rapor_disa_aktar, rapor, yil, "xlsx")),
                ft.OutlinedButton("PDF", icon=ft.Icons.PICTURE_AS_PDF,
                                  on_click=lambda e: self.page.run_task(
                                      self.rapor_disa_aktar, rapor, yil, "pdf")),
            ], wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Text(f"{veri['ozet']['satir_sayisi']} satır"
                    + (" • " + " • ".join(toplam_metinleri) if toplam_metinleri else ""),
                    color=ft.Colors.BLUE_GREY_700, selectable=True),
            baslik(veri["baslik"]),
        ]
        if not veri["satirlar"]:
            kontroller.append(ft.Text("Bu çalışma yılı için rapor verisi bulunamadı."))
        for row in veri["satirlar"]:
            alanlar = []
            for kolon in veri["kolonlar"]:
                deger = row.get(kolon["anahtar"])
                if kolon["tur"] == "para" and deger is not None:
                    deger = para(deger) + " TL"
                elif kolon["tur"] == "oran" and deger is not None:
                    deger = f"{float(deger):.2%}"
                elif kolon["tur"] == "bool" and deger is not None:
                    deger = "Evet" if deger else "Hayır"
                elif kolon["tur"] == "tarih":
                    deger = tarih(deger)
                elif kolon["tur"] == "sayi" and deger is not None:
                    deger = f"{deger:g}" if isinstance(deger, (int, float)) else str(deger)
                if deger not in (None, ""):
                    alanlar.append(satir(kolon["baslik"], deger))
            kontroller.append(kart(*alanlar))
        self.ac(self.gorunum(f"Raporlar • {yil}", kontroller))

    async def rapor_disa_aktar(self, rapor: str, yil: int, bicim: str):
        api = self.api
        if api is None:
            return
        dosya = await self.cagir(api.get, f"/raporlar/{rapor}/disa-aktar", yil=yil, bicim=bicim)
        if dosya is None:
            return
        picker = ft.FilePicker()
        self.page.overlay.append(picker)
        self.page.update()
        try:
            yol = await picker.save_file(
                dialog_title="Raporu kaydet", file_name=dosya["dosya_adi"],
                src_bytes=base64.b64decode(dosya["icerik"]))
            if yol:
                self.bildir(f"Rapor kaydedildi: {yol}")
        finally:
            self.page.overlay.remove(picker)
            self.page.update()

    async def hazine_ekrani(self, yil: int | None = None):
        api = self.api
        if api is None:
            return
        yil = yil or self.yil
        veri = await self.cagir(api.get, "/yukumluluk/hazine", yil=yil)
        if veri is None:
            return

        async def yil_degisti(e):
            await self.hazine_ekrani(int(e.control.value))

        kontroller: list[ft.Control] = [
            ft.Text("Hazine payı bildirimi ve yıllık yükümlülük takibi. Beyan/ödeme işlemlerini ilgili resmî sistemlerde ayrıca tamamlayınız.",
                    color=ft.Colors.BLUE_GREY_700, selectable=True),
            ft.Row([
                ft.Dropdown(label="Çalışma yılı", value=str(yil), width=140,
                            options=[secenek(y, y) for y in range(date.today().year - 5, date.today().year + 1)],
                            on_select=yil_degisti),
                ft.OutlinedButton("Excel", icon=ft.Icons.TABLE_VIEW,
                                  on_click=lambda e: self.page.run_task(
                                      self.yukumluluk_disa_aktar, "hazine", yil, "xlsx")),
                ft.OutlinedButton("PDF", icon=ft.Icons.PICTURE_AS_PDF,
                                  on_click=lambda e: self.page.run_task(
                                      self.yukumluluk_disa_aktar, "hazine", yil, "pdf")),
            ], wrap=True),
        ]
        if veri["yazabilir"]:
            async def hepsini_hesapla(e):
                sonuc = await self.cagir(api.post, "/yukumluluk/hazine/hesapla", {"yil": yil})
                if sonuc is None:
                    return
                self.bildir(f"Hesaplanan ay sayısı: {len(sonuc['hesaplanan_aylar'])}")
                await self.hazine_ekrani(yil)
            kontroller.append(ft.OutlinedButton("Geçmiş ayların tümünü hesapla",
                                                 icon=ft.Icons.CALCULATE, on_click=hepsini_hesapla))

        for kayit in veri["aylik"]:
            durum_rengi = (ft.Colors.GREEN_800 if kayit["durum"].startswith(("Ödendi", "Bildirildi ("))
                           else ft.Colors.RED_700 if kayit["gecikme"] and "gecikti" in kayit["gecikme"]
                           else ft.Colors.ORANGE_800 if kayit["fark"] else ft.Colors.BLUE_GREY_700)
            satir_kontroller: list[ft.Control] = [
                ft.Text(f"{kayit['ay_ad']} {yil}", weight=ft.FontWeight.BOLD),
                satir("Güncel tahsil edilen hasılat", para(kayit["guncel"]) + " TL"),
                satir("Bildirilen matrah", para(kayit["tahsil_edilen"]) + " TL"),
                satir("Oran / hazine payı", f"{kayit['oran'] * 100:g}% • {para(kayit['tutar'])} TL", True),
                satir("Son gün", tarih(kayit["son"])),
                satir("Bildirim / ödeme",
                      f"{tarih(kayit['bildirim_tarihi']) or '-'} / {tarih(kayit['odeme_tarihi']) or '-'}"),
                ft.Text(kayit["durum"], color=durum_rengi, weight=ft.FontWeight.BOLD),
            ]
            if kayit["gecikme"]:
                satir_kontroller.append(ft.Text(kayit["gecikme"], color=ft.Colors.RED_700))
            if kayit["fark"]:
                satir_kontroller.append(ft.Text(kayit["fark"], color=ft.Colors.ORANGE_800))
            eylemler = []
            if veri["yazabilir"]:
                async def hesapla(e, ay=kayit["ay"]):
                    sonuc = await self.cagir(api.post, "/yukumluluk/hazine/hesapla",
                                             {"yil": yil, "ay": ay})
                    if sonuc is not None:
                        await self.hazine_ekrani(yil)
                eylemler.append(ft.TextButton("Hesapla / güncelle", on_click=hesapla))
                if kayit["id"] and not kayit["bildirim_tarihi"] and kayit["durum"] != "Ödendi":
                    async def bildir(e, ay=kayit["ay"]):
                        sonuc = await self.cagir(api.post, "/yukumluluk/hazine/bildir",
                                                 {"yil": yil, "ay": ay})
                        if sonuc is not None:
                            await self.hazine_ekrani(yil)
                    eylemler.append(ft.TextButton("Bildirildi", on_click=bildir))
                if kayit["id"] and kayit["tutar"] and kayit["durum"] != "Ödendi":
                    async def odeme(e, ay=kayit["ay"], tutar=kayit["tutar"]):
                        await self.yukumluluk_odeme("hazine", yil, ay, tutar)
                    eylemler.append(ft.TextButton("Ödeme kaydı", on_click=odeme))
            if kayit["id"]:
                async def pdf(e, ay=kayit["ay"]):
                    await self.yukumluluk_pdf(yil, ay)
                eylemler.append(ft.TextButton("Örnek 30 PDF", on_click=pdf))
            if eylemler:
                satir_kontroller.append(ft.Row(eylemler, wrap=True))
            kontroller.append(kart(*satir_kontroller))

        shcek, merkez = veri["shcek"], veri["merkez"]
        kontroller.append(baslik("Yıllık yükümlülükler"))
        shcek_kart = [
            satir(f"{yil} brüt hasılat", para(shcek["hasilat"]) + " TL"),
            satir("SHÇEK oranı / payı", f"{shcek['oran'] * 100:g}% • {para(shcek['tutar'])} TL", True),
            satir("Son gün / ödeme", f"{tarih(shcek['son'])} / {tarih(shcek['odeme_tarihi']) or 'Ödenmedi'}"),
        ]
        if veri["yazabilir"] and not shcek["odeme_tarihi"] and shcek["tutar"] > 0:
            shcek_kart.append(ft.FilledButton(
                "SHÇEK ödeme kaydı", icon=ft.Icons.PAYMENTS,
                on_click=lambda e: self.page.run_task(
                    self.yukumluluk_odeme, "shcek", yil, None, shcek["tutar"])))
        kontroller.append(kart(*shcek_kart))
        merkez_kart = [
            satir("MEB Merkez Saymanlık kâr payı",
                  para(merkez["tutar"]) + " TL" if merkez["dagitim_var"] else "Yıl sonu dağıtımı yapılmadı"),
            satir("Alıcı", f"{merkez['ad']} • VKN {merkez['vkn']}"),
            satir("IBAN", merkez["iban"]),
            satir("Durum / ödeme", f"{merkez['durum'] or '-'} / {tarih(merkez['odeme_tarihi']) or 'Ödenmedi'}"),
        ]
        if (veri["yazabilir"] and merkez["dagitim_var"] and not merkez["odeme_tarihi"]
                and merkez["tutar"] and merkez["tutar"] > 0):
            merkez_kart.append(ft.FilledButton(
                "Merkez Saymanlık ödeme kaydı", icon=ft.Icons.PAYMENTS,
                on_click=lambda e: self.page.run_task(
                    self.yukumluluk_odeme, "merkez", yil, None, merkez["tutar"])))
        kontroller.append(kart(*merkez_kart))
        self.ac(self.gorunum(f"Hazine Payı / SHÇEK • {yil}", kontroller))

    async def vergi_ekrani(self, yil: int | None = None):
        api = self.api
        if api is None:
            return
        yil = yil or self.yil
        veri = await self.cagir(api.get, "/vergi", yil=yil)
        if veri is None:
            return

        async def yil_degisti(e):
            await self.vergi_ekrani(int(e.control.value))

        toplamlar = {}
        for anahtar in ("odenecek_kdv", "devreden", "tevkifat", "stopaj", "ucret_gv", "ucret_dv", "muhtasar"):
            toplamlar[anahtar] = sum(row[anahtar] or 0 for row in veri["aylar"])
        kontroller: list[ft.Control] = [
            ft.Text("Beyanname hazırlığı için kontrol özetidir; beyannameleri GİB e-Beyanname üzerinden ayrıca veriniz.",
                    color=ft.Colors.BLUE_GREY_700, selectable=True),
            ft.Row([
                ft.Dropdown(label="Çalışma yılı", value=str(yil), width=140,
                            options=[secenek(y, y) for y in range(date.today().year - 5, date.today().year + 1)],
                            on_select=yil_degisti),
                ft.OutlinedButton("Excel", icon=ft.Icons.TABLE_VIEW,
                                  on_click=lambda e: self.page.run_task(
                                      self.yukumluluk_disa_aktar, "vergi", yil, "xlsx")),
            ], wrap=True),
            kart(
                satir("Ödenecek KDV (yıl toplamı)", para(toplamlar["odenecek_kdv"]) + " TL", True),
                satir("Yıl sonu devreden KDV", para(veri["aylar"][-1]["devreden"]) + " TL"),
                satir("Sorumlu sıfatıyla KDV", para(toplamlar["tevkifat"]) + " TL"),
                satir("Muhtasar kesintiler toplamı", para(toplamlar["muhtasar"]) + " TL", True)),
        ]
        for ay in veri["aylar"]:
            kontroller.append(kart(
                ft.Text(f"{ay['ay_ad']} {yil}", weight=ft.FontWeight.BOLD),
                satir("Satış matrahı", para(ay["satis_matrah"]) + " TL"),
                satir("Hesaplanan / indirilecek KDV",
                      f"{para(ay['hesaplanan'])} / {para(ay['indirilecek'])} TL"),
                satir("Ödenecek / devreden KDV",
                      f"{para(ay['odenecek_kdv'])} / {para(ay['devreden'])} TL", True),
                satir("Sorumlu sıfatıyla KDV (2 No.)", para(ay["tevkifat"]) + " TL"),
                satir("Stopaj / ücret GV / ücret DV",
                      f"{para(ay['stopaj'])} / {para(ay['ucret_gv'])} / {para(ay['ucret_dv'])} TL"),
                satir("Muhtasar toplam / son gün",
                      f"{para(ay['muhtasar'])} TL / {tarih(ay['muhtasar_son'])}"),
                satir("KDV beyan son günü", tarih(ay["kdv_son"])),
                ft.OutlinedButton(
                    "Muhtasar ayrıntısı", icon=ft.Icons.RECEIPT_LONG,
                    on_click=lambda e, secili_ay=ay["ay"]: self.page.run_task(
                        self.vergi_muhtasar_detayi, yil, secili_ay)),
            ))
        self.ac(self.gorunum(f"KDV / Muhtasar • {yil}", kontroller))

    async def vergi_muhtasar_detayi(self, yil: int, ay: int):
        api = self.api
        if api is None:
            return
        veri = await self.cagir(api.get, f"/vergi/{yil}/{ay}/muhtasar")
        if veri is None:
            return
        kontroller: list[ft.Control] = [ft.Text(
            "Alış stopajı ve onaylanmış bordro GV/DV kesintileri.", color=ft.Colors.BLUE_GREY_700)]
        for row in veri["detay"]:
            kontroller.append(kart(
                ft.Text(row["belge_turu"] or row["tur"] or "Kesinti", weight=ft.FontWeight.BOLD),
                satir("Tarih / belge", f"{tarih(row['tarih'])} • {row['belge_no'] or '-'}"),
                satir("Ünvan / VKN-TCKN", f"{row['unvan'] or '-'} • {row['vkn_tckn'] or '-'}"),
                satir("Kesinti türü / matrah", f"{row['tur'] or '-'} • {para(row['matrah'])} TL"),
                satir("Kesinti", para(row["tutar"]) + " TL", True)))
        if not veri["detay"]:
            kontroller.append(ft.Text("Bu ay için muhtasar kesinti ayrıntısı yok."))
        self.ac(self.gorunum(f"Muhtasar ayrıntısı • {veri['ay']}/{veri['yil']}", kontroller))

    async def belgeler_ekrani(self):
        api = self.api
        if api is None:
            return
        veri = await self.cagir(api.get, "/belgeler")
        if veri is None:
            return
        kontroller: list[ft.Control] = [
            ft.Text(
                "Hazır şablonlarla resmi yazı oluşturun ve öğrenci/personel PDF belgelerini sunucuda üretin. "
                "Resmi yazıları ayrıca DYS/DETSİS üzerinden kayda alınız.",
                color=ft.Colors.BLUE_GREY_700, selectable=True),
        ]
        if veri["yazabilir"]:
            kontroller.append(ft.FilledButton(
                "Yeni resmi yazı", icon=ft.Icons.ADD,
                on_click=lambda e: self.page.run_task(self.resmi_yazi_formu, veri, None)))
        kontroller.append(baslik("Resmi yazılar"))
        for yazi in veri["yazilar"]:
            kontroller.append(kart(
                ft.Text(yazi["konu"], weight=ft.FontWeight.BOLD),
                satir("Tarih / sayı", f"{tarih(yazi['tarih'])} • {yazi['sayi'] or '-'}"),
                satir("Muhatap", yazi["muhatap"] or "-"),
                ft.Row([
                    ft.OutlinedButton("PDF", icon=ft.Icons.PICTURE_AS_PDF,
                                      on_click=lambda e, yazi_id=yazi["id"]:
                                      self.page.run_task(self.resmi_yazi_disa_aktar, yazi_id)),
                    *([ft.TextButton("Düzenle", icon=ft.Icons.EDIT,
                                     on_click=lambda e, yazi_id=yazi["id"]:
                                     self.page.run_task(self.resmi_yazi_duzenle, yazi_id, veri)),
                       ft.TextButton("Sil", icon=ft.Icons.DELETE_OUTLINE,
                                     on_click=lambda e, yazi_id=yazi["id"]:
                                     self.resmi_yazi_sil(yazi_id))]
                      if veri["yazabilir"] else []),
                ], wrap=True)))
        if not veri["yazilar"]:
            kontroller.append(ft.Text("Henüz resmi yazı kaydı yok."))

        kontroller.append(baslik("Öğrenci / personel belgeleri"))
        kontroller.append(ft.Text(f"Aktif personel: {veri['personel_sayisi']} • Aktif öğrenci: {len(veri['ogrenciler'])}",
                                  color=ft.Colors.BLUE_GREY_700))
        secimler: dict[int, ft.Checkbox] = {}
        kontroller.append(ft.Row([
            ft.OutlinedButton("Muvafakati eksik öğrencileri seç",
                              on_click=lambda e: self._belge_secimleri(
                                  secimler, veri["ogrenciler"], eksik=True)),
            ft.OutlinedButton("Seçimi temizle",
                              on_click=lambda e: self._belge_secimleri(secimler, veri["ogrenciler"], temizle=True)),
            ft.OutlinedButton("Veli muvafakatnamesi (seçilenler)", icon=ft.Icons.PICTURE_AS_PDF,
                              on_click=lambda e: self.page.run_task(
                                  self.muvafakatname_disa_aktar, secimler)),
            ft.OutlinedButton("Öğrenci listesi PDF", icon=ft.Icons.PICTURE_AS_PDF,
                              on_click=lambda e: self.page.run_task(
                                  self.belge_liste_disa_aktar, "ogrenci-listesi")),
            ft.OutlinedButton("Personel listesi PDF", icon=ft.Icons.PICTURE_AS_PDF,
                              on_click=lambda e: self.page.run_task(
                                  self.belge_liste_disa_aktar, "personel-listesi")),
        ], wrap=True))
        for ogrenci in veri["ogrenciler"]:
            checkbox = ft.Checkbox(label=ogrenci["ad_soyad"])
            secimler[ogrenci["id"]] = checkbox
            kontroller.append(kart(
                ft.Row([
                    checkbox,
                    ft.Text(" • ".join(str(x) for x in (ogrenci["okul_no"], ogrenci["sinif"], ogrenci["bolum"])
                                       if x), color=ft.Colors.BLUE_GREY_700, expand=True),
                    ft.Text("Muvafakat var" if ogrenci["veli_muvafakat"] else "Muvafakat eksik",
                            color=ft.Colors.GREEN_800 if ogrenci["veli_muvafakat"] else ft.Colors.RED_700),
                ], wrap=True),
                satir("Veli / tarih", f"{ogrenci['veli_adi'] or '-'} • {tarih(ogrenci['muvafakat_tarihi']) or '-'}"),
            ))
        self.ac(self.gorunum("Resmi Yazılar / Belgeler", kontroller))

    def _belge_secimleri(self, secimler: dict[int, ft.Checkbox], ogrenciler: list[dict],
                         eksik: bool = False, temizle: bool = False):
        for ogrenci in ogrenciler:
            if temizle:
                secimler[ogrenci["id"]].value = False
            elif eksik:
                secimler[ogrenci["id"]].value = not bool(ogrenci["veli_muvafakat"])
        self.page.update()

    async def resmi_yazi_formu(self, veri: dict, yazi: dict | None):
        api = self.api
        if api is None:
            return
        sablonlar = veri["sablonlar"]
        kurum = veri["kurum"]
        gerceklestirme = f"{kurum.get('gerceklestirme_gorevlisi') or ''}\nMüdür Yardımcısı"
        harcama = f"{kurum.get('harcama_yetkilisi') or ''}\nOkul Müdürü"
        alan = {
            "tarih": ft.TextField(label="Tarih", value=(yazi or {}).get("tarih") or date.today().isoformat(),
                                  hint_text="YYYY-AA-GG"),
            "sayi": ft.TextField(label="Sayı", value=(yazi or {}).get("sayi") or kurum.get("evrak_kodu") or ""),
            "konu": ft.TextField(label="Konu", value=(yazi or {}).get("konu") or ""),
            "muhatap": ft.TextField(label="Muhatap", value=(yazi or {}).get("muhatap") or ""),
            "ilgi": ft.TextField(label="İlgi", value=(yazi or {}).get("ilgi") or "", multiline=True, min_lines=2),
            "metin": ft.TextField(label="Metin (paragraflar arasında boş satır)", value=(yazi or {}).get("metin") or "",
                                  multiline=True, min_lines=6, max_lines=16),
            "imza1": ft.TextField(label="1. imza (Ad Soyad ve unvan)",
                                  value=yazi.get("imza1", "") if yazi else gerceklestirme,
                                  multiline=True, min_lines=2),
            "imza2": ft.TextField(label="2. imza (Ad Soyad ve unvan)",
                                  value=yazi.get("imza2", "") if yazi else harcama,
                                  multiline=True, min_lines=2),
        }

        def sablon_degisti(e):
            secili = sablonlar.get(e.control.value)
            if not secili:
                return
            konu, muhatap, metin = secili
            alan["konu"].value = konu
            alan["muhatap"].value = muhatap
            alan["metin"].value = metin.format(yil=self.yil, ay="........")
            self.page.update()

        sablon = ft.Dropdown(
            label="Yazı şablonu", value="Serbest yazı", options=[
                secenek(k, k) for k in sablonlar
            ], on_select=sablon_degisti)

        async def kaydet(e=None):
            govde = {anahtar: kontrol.value or "" for anahtar, kontrol in alan.items()}
            try:
                govde["tarih"] = iso_tarih(govde["tarih"], "Tarih") or ""
            except ValueError as exc:
                self.bilgi("Geçersiz tarih", str(exc))
                return
            if not govde["konu"].strip() or not govde["metin"].strip():
                self.bilgi("Eksik bilgi", "Konu ve metin alanları zorunludur.")
                return
            yol = f"/belgeler/yazilar/{yazi['id']}" if yazi else "/belgeler/yazilar"
            islem = api.put if yazi else api.post
            sonuc = await self.cagir(islem, yol, govde)
            if sonuc is not None:
                self.bildir("Resmi yazı kaydedildi.")
                await self.belgeler_ekrani()

        kontroller: list[ft.Control] = [
            sablon,
            alan["tarih"], alan["sayi"], alan["konu"], alan["muhatap"],
            alan["ilgi"], alan["metin"], alan["imza1"], alan["imza2"],
            ft.Row([ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, on_click=kaydet),
                    ft.TextButton("Vazgeç", on_click=lambda e: self.geri())], wrap=True),
        ]
        self.ac(self.gorunum("Resmi yazı düzenle" if yazi else "Yeni resmi yazı", kontroller))

    async def resmi_yazi_duzenle(self, yazi_id: int, liste: dict):
        api = self.api
        if api is None:
            return
        yazi = await self.cagir(api.get, f"/belgeler/yazilar/{yazi_id}")
        if yazi is not None:
            await self.resmi_yazi_formu(liste, yazi)

    async def resmi_yazi_sil(self, yazi_id: int):
        api = self.api
        if api is None:
            return

        async def sil():
            sonuc = await self.cagir(api.delete, f"/belgeler/yazilar/{yazi_id}")
            if sonuc is not None:
                self.bildir("Resmi yazı silindi.")
                await self.belgeler_ekrani()

        self.sor("Resmi yazıyı sil", "Bu işlem geri alınamaz. Seçili yazı silinsin mi?", sil, "Sil")

    async def resmi_yazi_disa_aktar(self, yazi_id: int):
        if self.api is None:
            return
        dosya = await self.cagir(self.api.get, f"/belgeler/yazilar/{yazi_id}/pdf")
        if dosya is not None:
            await self._dosyayi_kaydet(dosya, "Resmi yazı PDF'sini kaydet")

    async def muvafakatname_disa_aktar(self, secimler: dict[int, ft.Checkbox]):
        if self.api is None:
            return
        ids = [ogrenci_id for ogrenci_id, secim in secimler.items() if secim.value]
        if not ids:
            self.bilgi("Öğrenci seçilmedi", "Muvafakatname oluşturmak için en az bir öğrenci seçiniz.")
            return
        dosya = await self.cagir(
            self.api.post, "/belgeler/muvafakatname", {"ogrenci_idler": ids})
        if dosya is not None:
            await self._dosyayi_kaydet(dosya, "Veli muvafakatnamesini kaydet")

    async def belge_liste_disa_aktar(self, tur: str):
        if self.api is None:
            return
        dosya = await self.cagir(self.api.get, f"/belgeler/{tur}")
        if dosya is not None:
            await self._dosyayi_kaydet(dosya, "Liste PDF'sini kaydet")

    async def yil_sonu_ekrani(self, yil: int | None = None, onceki_girdiler: dict | None = None,
                              hesap_sonucu: dict | None = None):
        api = self.api
        if api is None:
            return
        yil = yil or self.yil
        veri = await self.cagir(api.get, "/yil-sonu", yil=yil)
        if veri is None:
            return
        kayit = veri["kayit"]
        kilitli = veri["kilitli"]
        durum = veri["onay"]["durum_metni"] if veri["onay"]["durum"] == "Onay bekliyor" else (
            kayit.get("durum") or veri["onay"]["durum_metni"] or "Kaydedilmedi")
        girdiler = {
            row["personel_id"]: row for row in (onceki_girdiler or {}).get("kisiler", [])
        }

        def yil_degisti(e):
            if e.control.value is not None:
                self.page.run_task(self.yil_sonu_ekrani, int(e.control.value))

        alanlar = {}
        kontroller: list[ft.Control] = [
            ft.Text(
                "Bilanço kârını BKMYBS bilançosundan giriniz. Dağıtım, mevzuat parametreleri ve personel çalışma verileriyle "
                "sunucuda hesaplanır; onaylanan kayıtlar kilitlenir.",
                color=ft.Colors.BLUE_GREY_700, selectable=True),
            ft.Row([
                ft.Dropdown(
                    label="Çalışma yılı", value=str(yil), width=145,
                    options=[secenek(y, y) for y in range(date.today().year - 5, date.today().year + 1)],
                    on_select=yil_degisti),
                ft.Text(f"Durum: {durum}", weight=ft.FontWeight.BOLD),
            ], wrap=True),
            kart(
                satir("Yardımcı defter gelirleri", para(veri["gelir_gider"]["toplam_gelir"]) + " TL"),
                satir("Yardımcı defter giderleri", para(veri["gelir_gider"]["toplam_gider"]) + " TL"),
                satir("Hesaplanan kâr / zarar", para(veri["gelir_gider"]["kar"]) + " TL"),
                satir("Önerilen kâr (SHÇEK sonrası)", para(veri["kar_onerilen"]) + " TL", True),
                satir("Yıllık brüt hasılat / sermaye",
                      f"{para(veri['hasilat'])} TL / tahsis {para(veri['tahsis_sermaye'])} • ödenmiş {para(veri['odenmis_sermaye'])} TL"),
                ft.Text("Yardımcı defter kârı BKMYBS bilançosu yerine geçmez; onaylı yasal bilanço kârını giriniz.",
                        size=12, color=ft.Colors.ORANGE_900)),
        ]
        kar = ft.TextField(
            label="Bilanço kârı (TL)", value=str((onceki_girdiler or {}).get("donem_kari",
                kayit.get("donem_kari", veri["kar_onerilen"]))), width=210, keyboard_type=ft.KeyboardType.NUMBER,
            disabled=kilitli)
        faiz = ft.TextField(
            label="Vadeli hesap faiz geliri (TL)", value=str((onceki_girdiler or {}).get("faiz_duzeltme",
                kayit.get("faiz_duzeltme") or 0)), width=220, keyboard_type=ft.KeyboardType.NUMBER,
            disabled=kilitli)
        oran = ft.TextField(
            label="ÜTP oranı (0–1)", value=str((onceki_girdiler or {}).get("utp_orani",
                kayit.get("utp_orani") if kayit.get("utp_orani") is not None
                else veri["parametreler"]["utp_azami_oran"])), width=155,
            keyboard_type=ft.KeyboardType.NUMBER, disabled=kilitli)
        kontroller.append(ft.Row([kar, faiz, oran], wrap=True))
        kontroller.append(baslik("ÜTP personel dağıtım girdileri"))
        kontroller.append(ft.Text(
            "Fiili gün, fazla çalışma, katkı ve takdir oranlarını gözden geçiriniz. Güncel onaylı fazla çalışma ve parça başı "
            "verileri saat alanına otomatik aktarılabilir.",
            size=12, color=ft.Colors.BLUE_GREY_700))
        kisiler = veri["kisiler"]
        for kisi in kisiler:
            pid = kisi["id"]
            eski = girdiler.get(pid, {})
            def deger(anahtar, varsayilan=0):
                return eski.get(anahtar, kisi.get(anahtar, varsayilan)) or varsayilan
            unvan = ft.Dropdown(
                label="Unvan grubu", value=str(deger("unvan_grubu", 5)), width=150,
                options=[secenek(i, f"Grup {i}") for i in range(1, 6)], disabled=kilitli)
            gun = ft.TextField(label="Fiili gün", value=str(deger("fiili_gun")), width=130,
                               keyboard_type=ft.KeyboardType.NUMBER, disabled=kilitli)
            saat = ft.TextField(label="F.Ç. saati", value=str(deger("fazla_calisma_saat")), width=130,
                                keyboard_type=ft.KeyboardType.NUMBER, disabled=kilitli)
            katki = ft.TextField(label="Katkı (%)", value=str(deger("katki_orani")), width=130,
                                 keyboard_type=ft.KeyboardType.NUMBER, disabled=kilitli)
            kayitli_takdir = eski.get("takdir_orani")
            if kayitli_takdir is None:
                kayitli_takdir = (kisi.get("takdir_orani") or 0) * 100
            takdir = ft.TextField(label="Takdir (%)", value=str(kayitli_takdir), width=130,
                                  keyboard_type=ft.KeyboardType.NUMBER, disabled=kilitli)
            haric = ft.Checkbox(label="Dağıtım dışında", value=bool(eski.get("haric", kisi.get("haric", False))),
                                disabled=kilitli)
            neden = ft.TextField(label="Hariç tutma nedeni (md.6)", value=str(
                eski.get("haric_neden", kisi.get("haric_neden") or "")), expand=True, disabled=kilitli)
            diger = ft.TextField(label="Diğer işletme ÜTP (Sayman)", value=str(
                deger("diger_isletme_utp")), width=230, keyboard_type=ft.KeyboardType.NUMBER,
                disabled=kilitli or kisi.get("dose_gorevi") != "Sayman")
            onceki = ft.TextField(label="Önceki kümülatif GV matrahı", value=str(
                deger("onceki_kumulatif")), width=250, keyboard_type=ft.KeyboardType.NUMBER,
                disabled=kilitli)
            alanlar[pid] = {
                "unvan_grubu": unvan, "fiili_gun": gun, "fazla_calisma_saat": saat,
                "katki_orani": katki, "takdir_orani": takdir, "haric": haric,
                "haric_neden": neden, "diger_isletme_utp": diger, "onceki_kumulatif": onceki,
            }
            card_controls: list[ft.Control] = [
                ft.Text(f"{kisi['ad_soyad']} • {kisi.get('dose_gorevi') or 'Görev belirtilmemiş'}"
                        + (f" • {kisi['bolum']}" if kisi.get("bolum") else ""),
                        weight=ft.FontWeight.BOLD),
                ft.Row([unvan, gun, saat, katki, takdir], wrap=True),
                ft.Row([haric, neden], wrap=True),
                ft.Row([diger, onceki], wrap=True),
            ]
            if hesap_sonucu:
                sonuc_kisi = next((r for r in hesap_sonucu["kisiler"] if r["personel_id"] == pid), None)
                if sonuc_kisi:
                    card_controls.append(ft.Text(
                        f"İdari {para(sonuc_kisi['idari_pay'])} • Takdir {para(sonuc_kisi['takdir_pay'])} • "
                        f"Bölüm {para(sonuc_kisi['bolum_pay'])} • Brüt {para(sonuc_kisi['brut'])} • "
                        f"GV {para(sonuc_kisi['gelir_vergisi'])} • DV {para(sonuc_kisi['damga_vergisi'])} • "
                        f"Net {para(sonuc_kisi['net'])} TL",
                        color=ft.Colors.BLUE_GREY_800, selectable=True))
            kontroller.append(kart(*card_controls))

        if hesap_sonucu:
            o = hesap_sonucu["ozet"]
            kontroller.append(baslik("Bölüşüm sonucu"))
            kontroller.append(kart(
                satir("ÜTP azami / dağıtıma esas", f"{para(o['utp_azami'])} / {para(o['dagitima_esas'])} TL"),
                satir("Dağıtılan ÜTP", para(o["dagitilan_utp"]) + " TL", True),
                satir("Sermaye payı / Merkez Saymanlık", f"{para(o['sermaye_payi'])} / {para(o['merkez_payi'])} TL"),
                satir("SHÇEK payı", para(o["shcek"]) + " TL", True)))
            for mesaj in hesap_sonucu["hatalar"]:
                kontroller.append(mesaj_kutusu([mesaj], "hata"))
            for mesaj in hesap_sonucu["uyarilar"]:
                kontroller.append(mesaj_kutusu([mesaj], "uyari"))

        def payload_olustur():
            def sayi_gir(kontrol, ad):
                try:
                    return sayi(kontrol.value, ad) or 0.0
                except ValueError as exc:
                    self.bilgi("Geçersiz değer", str(exc))
                    raise
            try:
                return {
                    "donem_kari": sayi_gir(kar, "Bilanço kârı"),
                    "faiz_duzeltme": sayi_gir(faiz, "Faiz geliri"),
                    "utp_orani": sayi_gir(oran, "ÜTP oranı"),
                    "kisiler": [{
                        "personel_id": pid,
                        "unvan_grubu": int(controls["unvan_grubu"].value),
                        "fiili_gun": sayi_gir(controls["fiili_gun"], "Fiili gün"),
                        "fazla_calisma_saat": sayi_gir(controls["fazla_calisma_saat"], "Fazla çalışma saati"),
                        "katki_orani": sayi_gir(controls["katki_orani"], "Katkı oranı"),
                        "takdir_orani": sayi_gir(controls["takdir_orani"], "Takdir oranı"),
                        "haric": bool(controls["haric"].value),
                        "haric_neden": controls["haric_neden"].value or "",
                        "diger_isletme_utp": sayi_gir(controls["diger_isletme_utp"], "Diğer işletme ÜTP"),
                        "onceki_kumulatif": sayi_gir(controls["onceki_kumulatif"], "Önceki kümülatif matrah"),
                    } for pid, controls in alanlar.items()],
                }
            except (TypeError, ValueError):
                return None

        async def saatleri_getir(e):
            sonuc = await self.cagir(api.post, f"/yil-sonu/{yil}/saat")
            if sonuc is None:
                return
            form = onceki_girdiler or {
                "donem_kari": sayi(kar.value) or 0,
                "faiz_duzeltme": sayi(faiz.value) or 0,
                "utp_orani": sayi(oran.value) or 0,
                "kisiler": [],
            }
            mevcut = {r["personel_id"]: r for r in form["kisiler"]}
            for kisi_id, saat_degeri in sonuc["saatler"].items():
                r = mevcut.get(int(kisi_id))
                if r:
                    r["fazla_calisma_saat"] = saat_degeri
                else:
                    kaynak = next(k for k in kisiler if k["id"] == int(kisi_id))
                    mevcut[int(kisi_id)] = {
                        "personel_id": int(kisi_id), "unvan_grubu": kaynak["unvan_grubu"],
                        "fiili_gun": kaynak.get("fiili_gun") or 0,
                        "fazla_calisma_saat": saat_degeri,
                        "katki_orani": kaynak.get("katki_orani") or 0,
                        "takdir_orani": (kaynak.get("takdir_orani") or 0) * 100,
                        "haric": bool(kaynak.get("haric")), "haric_neden": kaynak.get("haric_neden") or "",
                        "diger_isletme_utp": kaynak.get("diger_isletme_utp") or 0,
                        "onceki_kumulatif": kaynak.get("onceki_kumulatif") or 0,
                    }
            form["kisiler"] = list(mevcut.values())
            await self.yil_sonu_ekrani(yil, form)

        async def hesapla_ve_yenile(e):
            form = payload_olustur()
            if form is None:
                return
            sonuc = await self.cagir(api.post, f"/yil-sonu/{yil}/hesapla", form)
            if sonuc is not None:
                await self.yil_sonu_ekrani(yil, form, sonuc)

        async def kaydet(e=None):
            form = payload_olustur()
            if form is None:
                return
            sonuc = await self.cagir(api.post, f"/yil-sonu/{yil}", form)
            if sonuc is None:
                return
            self.bildir("Yıl sonu dağıtımı taslak olarak kaydedildi.")
            await self.yil_sonu_ekrani(yil, form, sonuc)

        async def onaya_gonder(e=None):
            form = payload_olustur()
            if form is None:
                return
            sonuc = await self.cagir(api.post, f"/yil-sonu/{yil}", form)
            if sonuc is None:
                return
            tur = "gonder" if self.ben.get("onay_akisi") else "dogrudan"
            yol = api.yol("onay", "Yıl Sonu", yil, tur)
            sonuc = await self.cagir(api.post, yol, {"aciklama": ""}) if tur == "gonder" else await self.cagir(api.post, yol)
            if sonuc is not None:
                self.bildir(sonuc.get("durum_metni") or "Yıl sonu dağıtımı onaya gönderildi.")
                await self.yil_sonu_ekrani(yil)

        async def ihrac(tur):
            dosya = await self.cagir(api.get, f"/yil-sonu/{yil}/disa-aktar", tur=tur)
            if dosya is not None:
                await self._dosyayi_kaydet(dosya, "Yıl sonu belgesini kaydet")

        async def kesinlestirmeyi_geri_al(e=None):
            sonuc = await self.cagir(api.post, f"/yil-sonu/{yil}/geri-al")
            if sonuc is not None:
                self.bildir(sonuc.get("durum_metni") or "Yıl sonu kesinleştirmesi kaldırıldı.")
                await self.yil_sonu_ekrani(yil)

        if veri["yazabilir"]:
            kontroller.extend([
                ft.Row([
                    ft.OutlinedButton("Saat verilerini getir", icon=ft.Icons.SCHEDULE,
                                      on_click=saatleri_getir),
                    ft.OutlinedButton("Hesapla", icon=ft.Icons.CALCULATE_OUTLINED,
                                      on_click=hesapla_ve_yenile),
                    ft.FilledButton("Kaydet (taslak)", icon=ft.Icons.SAVE, on_click=kaydet),
                ], wrap=True),
                ft.FilledButton(
                    "Onaya gönder" if self.ben.get("onay_akisi") else "Kesinleştir",
                    icon=ft.Icons.TASK_ALT,
                    on_click=lambda e: self.sor(
                        "Yıl sonu dağıtımı",
                        "Dağıtım kaydedilecek ve onay akışına gönderilecek."
                        if self.ben.get("onay_akisi") else
                        "Dağıtım kesinleştirilecek; ÜTP ve SHÇEK yardımcı yevmiye kayıtları oluşturulup tablo kilitlenecek.",
                        onaya_gonder, "Devam et")),
            ])
        if kayit:
            kontroller.append(ft.Row([
                ft.OutlinedButton("ÜTP dağıtım cetveli (PDF)", icon=ft.Icons.PICTURE_AS_PDF,
                                  on_click=lambda e: self.page.run_task(ihrac, "cetvel")),
                ft.OutlinedButton("Banka listesi (Excel)", icon=ft.Icons.TABLE_VIEW,
                                  on_click=lambda e: self.page.run_task(ihrac, "banka")),
                ft.OutlinedButton("Merkez Saymanlık yazısı", icon=ft.Icons.DESCRIPTION,
                                  on_click=lambda e: self.page.run_task(ihrac, "merkez-yazisi")),
                ft.OutlinedButton("SHÇEK yazısı", icon=ft.Icons.DESCRIPTION,
                                  on_click=lambda e: self.page.run_task(ihrac, "shcek-yazisi")),
            ], wrap=True))
        if veri["geri_alabilir"]:
            kontroller.append(ft.OutlinedButton(
                "Kesinleştirmeyi kaldır", icon=ft.Icons.LOCK_OPEN,
                on_click=lambda e: self.sor(
                    "Kesinleştirmeyi kaldır",
                    "ÜTP ve SHÇEK yardımcı yevmiye kayıtları da geri alınacak.",
                    kesinlestirmeyi_geri_al, "Kesinleştirmeyi kaldır")))
        self.ac(self.gorunum(f"Yıl Sonu Kârı ve ÜTP • {yil}", kontroller))

    async def yukumluluk_odeme(self, tur: str, yil: int, ay: int | None, tutar: float):
        api = self.api
        if api is None:
            return
        ad = {"hazine": "Hazine payı", "shcek": "SHÇEK", "merkez": "Merkez Saymanlık"}[tur]

        async def kaydet():
            sonuc = await self.cagir(api.post, "/yukumluluk/odeme", {"tur": tur, "yil": yil, "ay": ay})
            if sonuc is None:
                return
            self.bildir(f"{ad} için {para(sonuc['tutar'])} TL banka ödeme kaydı oluşturuldu.")
            await self.hazine_ekrani(yil)
        self.sor("Ödeme kaydı oluştur", f"{ad}: {para(tutar)} TL tutarında banka çıkışı ve muhasebe fişi oluşturulacak.",
                 kaydet, "Ödemeyi kaydet")

    async def yukumluluk_pdf(self, yil: int, ay: int):
        api = self.api
        if api is None:
            return
        dosya = await self.cagir(api.get, f"/yukumluluk/hazine/{yil}/{ay}/pdf")
        if dosya is not None:
            await self._dosyayi_kaydet(dosya, "Hazine payı bildirimini kaydet")

    async def yukumluluk_disa_aktar(self, tur: str, yil: int, bicim: str):
        api = self.api
        if api is None:
            return
        yol = "/yukumluluk/hazine/disa-aktar" if tur == "hazine" else "/vergi/disa-aktar"
        dosya = await self.cagir(api.get, yol, yil=yil, bicim=bicim)
        if dosya is not None:
            await self._dosyayi_kaydet(dosya, "Yükümlülük raporunu kaydet")

    async def _dosyayi_kaydet(self, dosya: dict, baslik_metni: str):
        picker = ft.FilePicker()
        self.page.overlay.append(picker)
        self.page.update()
        try:
            yol = await picker.save_file(
                dialog_title=baslik_metni, file_name=dosya["dosya_adi"],
                src_bytes=base64.b64decode(dosya["icerik"]))
            if yol:
                self.bildir(f"Dosya kaydedildi: {yol}")
        finally:
            self.page.overlay.remove(picker)
            self.page.update()


def calistir(sabit_adres: str | None = None):
    """Flet giriş noktası üretir; sabit_adres verilirse (web sürümü) sunucu adresi sorulmaz."""
    async def main(page: ft.Page):
        await Uygulama(page, sabit_adres).baslat()
    return main
