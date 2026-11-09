"""DÖSE Yönetim — single Flet client for desktop, phone and browser. Every record lives in Supabase."""
from __future__ import annotations

import asyncio
import os

import flet as ft

try:
    from . import ayar, takvim, tema
    from . import tanimlar as T
    from .supa import Supa, SupaHata
    from .tema import (ANA_RENK, GIRIS_GRADYANI, KENAR, MARKA_VURGU, METIN, METIN_IKINCIL, YUZEY, ZEMIN,
                       aciklama, baslik, deneme_rozeti, giris_kart, ozellik_satiri)
except ImportError:
    import ayar
    import takvim
    import tema
    import tanimlar as T
    from supa import Supa, SupaHata
    from tema import (ANA_RENK, GIRIS_GRADYANI, KENAR, MARKA_VURGU, METIN, METIN_IKINCIL, YUZEY, ZEMIN,
                      aciklama, baslik, deneme_rozeti, giris_kart, ozellik_satiri)

OTURUM_ANAHTARI = "dose.oturum"
GENIS_EKRAN = 900
VARLIK_KLASORU = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
CIZGI = KENAR

SAYFALAR = [
    ("ana", "Ana ekran", ft.Icons.HOME, None),
    ("kurum", "Kurum bilgileri", ft.Icons.APARTMENT, "kurum"),
    ("bolum", "Bölüm / atölye", ft.Icons.ACCOUNT_TREE, "bolum"),
    ("personel", "Personel", ft.Icons.BADGE, "personel"),
    ("ogrenci", "Öğrenciler", ft.Icons.SCHOOL, "ogrenci"),
    ("cari", "Cariler", ft.Icons.STOREFRONT, "cari"),
    ("malzeme", "Malzeme / stok kartı", ft.Icons.INVENTORY_2, "malzeme"),
    ("urun", "Ürün / hizmet", ft.Icons.CATEGORY, "urun"),
    ("siparis", "Sipariş / iş emirleri", ft.Icons.SHOPPING_CART, "siparis"),
    ("parca_basi", "Parça başı hakediş", ft.Icons.ENGINEERING, "parca_basi"),
    ("fazla_calisma", "Fazla çalışma", ft.Icons.MORE_TIME, "fazla_calisma"),
    ("fatura", "Fatura kayıtları", ft.Icons.RECEIPT_LONG, "fatura"),
    ("kasa", "Kasa / Banka", ft.Icons.ACCOUNT_BALANCE_WALLET, "kasa"),
    ("stok", "Stok hareketleri", ft.Icons.SWAP_VERT, "stok"),
    ("yevmiye", "Yevmiye / mizan", ft.Icons.BALANCE, "yevmiye"),
    ("hazine_payi", "Hazine payı / vergi takvimi", ft.Icons.EVENT_NOTE, "hazine_payi"),
    ("yil_sonu", "Yıl sonu / ÜTP", ft.Icons.CALENDAR_MONTH, "yil_sonu"),
    ("vergi_hesap", "Muhasebe hesapları", ft.Icons.ACCOUNT_BALANCE, "vergi_hesap"),
    ("maliyet", "Maliyet / fiyat tespit", ft.Icons.PRICE_CHANGE, "urun"),
    ("raporlar", "Raporlar", ft.Icons.ASSESSMENT, "yevmiye"),
    ("resmi_yazi", "Resmi yazılar", ft.Icons.MAIL, "resmi_yazi"),
    ("denetim", "Denetim formu", ft.Icons.FACT_CHECK, "islem_kaydi"),
    ("mevzuat", "Okul parametre doğrulaması", ft.Icons.SETTINGS, "mevzuat"),
    ("merkez_mevzuat", "Merkez parametre yayını", ft.Icons.SETTINGS, "merkez_mevzuat"),
    ("kullanici", "Kullanıcılar", ft.Icons.MANAGE_ACCOUNTS, "kullanici"),
    ("islem_kaydi", "İşlem kaydı", ft.Icons.HISTORY, "islem_kaydi"),
]
SAYFA_ADI = {a: e for a, e, _, _ in SAYFALAR}

# Top menu groups; "ana" is a direct item, the others open as drop-down menus.
MENU_GRUPLARI = [
    ("Tanımlar", ft.Icons.FOLDER_OPEN, ("kurum", "bolum", "personel", "ogrenci", "cari", "malzeme", "urun")),
    ("İşlemler", ft.Icons.WORK_OUTLINE, ("siparis", "parca_basi", "fazla_calisma", "fatura", "kasa", "stok")),
    ("Muhasebe", ft.Icons.ACCOUNT_BALANCE, ("yevmiye", "hazine_payi", "yil_sonu", "vergi_hesap", "raporlar")),
    ("Yönetim", ft.Icons.ADMIN_PANEL_SETTINGS,
     ("maliyet", "resmi_yazi", "denetim", "mevzuat", "merkez_mevzuat", "kullanici", "islem_kaydi")),
]


def logo(genislik: int = 132, yukseklik: int = 72) -> ft.Control:
    return ft.Image(src="logo.png", width=genislik, height=yukseklik, fit=ft.BoxFit.CONTAIN,
                    error_content=ft.Icon(ft.Icons.ACCOUNT_BALANCE, size=min(48, yukseklik), color=ANA_RENK))


def uygulama_ikonu(boyut: int = 40) -> ft.Control:
    return ft.Image(src="ikon.png", width=boyut, height=boyut, fit=ft.BoxFit.CONTAIN,
                    border_radius=8,
                    error_content=ft.Icon(ft.Icons.ACCOUNT_BALANCE, size=boyut, color=ANA_RENK))


OZELLIKLER = [
    (ft.Icons.SHOPPING_CART, "Sipariş ve onay akışı", "#f5c76a"),
    (ft.Icons.RECEIPT_LONG, "Fatura, stok ve yevmiye", "#9fd4a8"),
    (ft.Icons.ACCOUNT_BALANCE_WALLET, "Kasa / banka takibi", "#8ec5d6"),
    (ft.Icons.VERIFIED_USER, "Rol bazlı yetki ve işlem kaydı", "#e8b4c8"),
]


def kart(*kontroller: ft.Control, genislik_kolon=None) -> ft.Container:
    return giris_kart(*kontroller, genislik_kolon=genislik_kolon)


def ortali(*kontroller: ft.Control) -> ft.Control:
    """Centered white card on the colourful background: fills a phone screen, stays readable on a desktop."""
    return ft.ResponsiveRow([giris_kart(*kontroller)], alignment=ft.MainAxisAlignment.CENTER)


class Uygulama:
    def __init__(self, page: ft.Page):
        self.page = page
        self.supa = Supa(ayar.SUPABASE_URL, ayar.SUPABASE_ANAHTAR, oturum_degisti=self._oturum_degisti,
                         auth_donus=ayar.AUTH_DONUS)
        self.ben: dict | None = None
        self.secenek: dict[str, list[tuple[str, str]]] = {}
        self.sayfa = "ana"
        self.ekran = None
        self.son_log: int | None = None
        self.genis: bool | None = None
        self.govde = ft.Container(expand=True, padding=ft.Padding.symmetric(horizontal=16, vertical=12),
                                  bgcolor=ZEMIN)
        self.menu_kutu: ft.Container | None = None
        self._dongu: asyncio.Task | None = None

    # ------------------------------------------------------------------ helpers
    @property
    def yetkiler(self) -> dict:
        return (self.ben or {}).get("yetkiler") or {}

    def yetki(self, sayfa: str) -> str:
        return self.yetkiler.get(sayfa, "")

    def bildir(self, mesaj: str, hata: bool = False):
        self.page.show_dialog(ft.SnackBar(ft.Text(mesaj), bgcolor=ft.Colors.ERROR if hata else None,
                                          duration=6000 if hata else 3500))

    async def guvenli(self, is_, dugme: ft.Control | None = None) -> bool:
        """Runs one server action; turns every expected failure into a readable message."""
        if dugme is not None:
            dugme.disabled = True
            self.page.update()
        try:
            await is_()
            return True
        except SupaHata as e:
            self.bildir(e.mesaj, hata=True)
        except ValueError as e:
            self.bildir(str(e), hata=True)
        finally:
            if dugme is not None:
                dugme.disabled = False
                self.page.update()
        return False

    def sayfayi_kur(self, icerik: ft.Control):
        """Pre-login screens: content scrolls over the full-screen teal gradient."""
        self.page.appbar = None
        self.page.drawer = None
        self.menu_kutu = None
        self.page.controls.clear()
        self.page.add(ft.Container(
            ft.Column([icerik], scroll=ft.ScrollMode.AUTO, expand=True,
                      alignment=ft.MainAxisAlignment.CENTER),
            gradient=GIRIS_GRADYANI, expand=True, padding=ft.Padding.symmetric(horizontal=16, vertical=24)))
        self.page.update()

    def onayla(self, soru: str, evet_etiketi: str, is_):
        async def evet(_):
            self.page.pop_dialog()
            await is_()

        self.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text("Onay"), content=ft.Text(soru),
            actions=[ft.TextButton("Vazgeç", on_click=lambda _: self.page.pop_dialog()),
                     ft.FilledButton(evet_etiketi, on_click=evet)]))

    # ------------------------------------------------------------------ session
    async def _oturum_degisti(self, oturum: dict | None):
        try:
            if oturum:
                await self.page.shared_preferences.set(OTURUM_ANAHTARI, oturum["refresh_token"])
            else:
                await self.page.shared_preferences.remove(OTURUM_ANAHTARI)
        except Exception:
            pass
        if oturum is None and self.ben is not None:
            self.ben = None
            self.giris_ekrani("Oturum süresi doldu. Yeniden giriş yapın.")

    async def basla(self):
        self.page.title = "DÖSE Yönetim"
        self.page.theme = tema.uygulama_temasi()
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.bgcolor = ZEMIN
        self.page.padding = 0
        self.page.on_resize = self._boyut_degisti
        try:
            ikon = os.path.join(os.environ.get("FLET_ASSETS_DIR") or VARLIK_KLASORU, "ikon.ico")
            if os.path.isfile(ikon):
                self.page.window.icon = ikon
        except Exception:
            pass
        yenileme = None
        try:
            yenileme = await self.page.shared_preferences.get(OTURUM_ANAHTARI)
        except Exception:
            pass
        if yenileme:
            self.sayfayi_kur(ortali(ft.ProgressRing(), aciklama("Oturum açılıyor…")))
            try:
                await self.supa.yenile(yenileme)
                await self.ben_yukle()
                return
            except SupaHata as e:
                if e.kod == "ag":
                    self.giris_ekrani(e.mesaj)
                    return
        self.giris_ekrani()

    async def ben_yukle(self):
        self.ben = await self.supa.rpc("dose_ben")
        if not self.ben.get("uye"):
            self.uyelik_yok_ekrani()
            return
        satirlar = await self.supa.sec("secenek", secim="liste,deger,etiket", sira="liste,sira")
        self.secenek = {}
        for s in satirlar:
            self.secenek.setdefault(s["liste"], []).append((s["deger"], s["etiket"] or s["deger"]))
        self.son_log = await self.supa.rpc("dose_son_degisiklik")
        self.sayfa = "ana"
        self.kabuk_kur()
        await self.sayfa_ac("ana")
        if self._dongu is None or self._dongu.done():
            self._dongu = asyncio.ensure_future(self._izle())

    async def cikis(self, _=None):
        if self.ekran is not None and self.ekran.islemde:
            self.bildir("İşlem tamamlanana kadar bekleyin.", hata=True)
            return
        if self.ekran is not None and self.ekran.kaydedilmemis():
            self.onayla("Kaydedilmemiş değişiklikler bırakılacak.", "Çıkış yap", self._cikis_uygula)
            return
        await self._cikis_uygula()

    async def _cikis_uygula(self):
        self.ben = None
        self.ekran = None
        await self.supa.cikis()
        self.giris_ekrani()

    # ------------------------------------------------------------------ login / sign-up / reset
    def giris_ekrani(self, mesaj: str | None = None, eposta: str = ""):
        e_posta = ft.TextField(label="E-posta", value=eposta, keyboard_type=ft.KeyboardType.EMAIL, autofocus=True)
        sifre = ft.TextField(label="Şifre", password=True, can_reveal_password=True)
        durum = ft.Text(mesaj or "", color=ft.Colors.ERROR, visible=bool(mesaj))
        tekrar_gonder = ft.TextButton("Doğrulama e-postasını yeniden gönder", visible=False)
        dugme = ft.FilledButton("Giriş yap", icon=ft.Icons.LOGIN)

        async def giris(_):
            durum.visible = False
            tekrar_gonder.visible = False
            if not e_posta.value.strip() or not sifre.value:
                durum.value, durum.visible = "E-posta ve şifre giriniz.", True
                self.page.update()
                return
            dugme.disabled = True
            self.page.update()
            try:
                await self.supa.giris(e_posta.value, sifre.value)
                await self.ben_yukle()
            except SupaHata as h:
                metin = h.mesaj
                if h.kod == "email_not_confirmed" or "doğrulanmamış" in (h.mesaj or "").lower():
                    metin = ("E-posta henüz doğrulanmadı. Gelen kutusu / gereksiz klasöründeki bağlantıya tıklayın; "
                             "gelmezse aşağıdan yeniden gönderin.")
                    tekrar_gonder.visible = True
                else:
                    tekrar_gonder.visible = h.kod == "email_not_confirmed"
                durum.value, durum.visible = metin, True
                dugme.disabled = False
                self.page.update()

        async def yeniden_gonder(_):
            if await self.guvenli(lambda: self.supa.dogrulama_gonder(e_posta.value), tekrar_gonder):
                self.bildir("Doğrulama e-postası gönderildi.")

        dugme.on_click = giris
        sifre.on_submit = giris
        tekrar_gonder.on_click = yeniden_gonder
        e_posta.prefix_icon = ft.Icons.EMAIL_OUTLINED
        sifre.prefix_icon = ft.Icons.LOCK_OUTLINE
        dugme.height = 48
        deneme = ft.FilledButton(
            "1 ay ücretsiz dene", icon=ft.Icons.ROCKET_LAUNCH, height=48,
            style=ft.ButtonStyle(bgcolor=ft.Colors.AMBER_400, color=ft.Colors.BROWN_900, icon_color=ft.Colors.BROWN_900),
            on_click=lambda _: self.kayit_ekrani(e_posta.value, deneme=True))
        form = giris_kart(
            ft.Container(logo(), alignment=ft.Alignment.CENTER),
            ft.Text("Hoş geldiniz", size=26, weight=ft.FontWeight.BOLD, color=METIN,
                    text_align=ft.TextAlign.CENTER),
            ft.Text("Kendi e-postanız ve şifrenizle giriş yapın.", color=METIN_IKINCIL,
                    text_align=ft.TextAlign.CENTER),
            e_posta, sifre, durum, dugme, tekrar_gonder,
            ft.Row([ft.TextButton("Hesap aç", on_click=lambda _: self.kayit_ekrani(e_posta.value)),
                    ft.TextButton("Şifremi unuttum", on_click=lambda _: self.sifre_ekrani(e_posta.value))],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
            ft.Row([ft.Container(ft.Divider(color=CIZGI), expand=True),
                    ft.Text("veya", size=12, color=METIN_IKINCIL),
                    ft.Container(ft.Divider(color=CIZGI), expand=True)]),
            deneme,
            ft.Text("Ödeme bilgisi istenmez. Süre bitince kayıtlarınız silinmez, salt okunur kalır.",
                    size=11, color=METIN_IKINCIL, text_align=ft.TextAlign.CENTER),
            genislik_kolon={"xs": 12, "sm": 10, "md": 6, "lg": 5, "xl": 4})
        tanitim = ft.Container(ft.Column([
            ft.Container(logo(160, 86), bgcolor=YUZEY, border_radius=18, padding=14,
                         width=200, alignment=ft.Alignment.CENTER,
                         shadow=ft.BoxShadow(blur_radius=16, color=ft.Colors.with_opacity(0.2, "#000000"))),
            ft.Text("DÖSE Yönetim", size=36, weight=ft.FontWeight.BOLD, color="#ffffff"),
            ft.Text("Döner sermaye işletmenizin siparişten muhasebeye tüm süreçleri tek ekranda, "
                    "bulutta ve güvenle.", size=15, color="#d6e6f5"),
            deneme_rozeti(),
            *[ozellik_satiri(ikon, metin, renk) for ikon, metin, renk in OZELLIKLER],
        ], spacing=18, tight=True), padding=ft.Padding.symmetric(horizontal=8, vertical=12),
            col={"xs": 12, "md": 6, "lg": 5, "xl": 4})
        self.sayfayi_kur(ft.ResponsiveRow([tanitim, form], alignment=ft.MainAxisAlignment.CENTER,
                                          vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=36, run_spacing=24))

    def kayit_ekrani(self, eposta: str = "", deneme: bool = False):
        e_posta = ft.TextField(label="E-posta", value=eposta, keyboard_type=ft.KeyboardType.EMAIL)
        sifre = ft.TextField(label="Şifre (en az 8 karakter)", password=True, can_reveal_password=True)
        sifre2 = ft.TextField(label="Şifre tekrar", password=True, can_reveal_password=True)
        dugme = ft.FilledButton("Hesap aç", icon=ft.Icons.PERSON_ADD)

        async def kaydol(_):
            if len(sifre.value) < 8:
                self.bildir("Şifre en az 8 karakter olmalıdır.", hata=True)
                return
            if sifre.value != sifre2.value:
                self.bildir("Şifreler aynı değil.", hata=True)
                return

            async def is_():
                sonuc = await self.supa.kaydol(e_posta.value, sifre.value)
                if sonuc.get("access_token"):
                    await self.ben_yukle()
                else:
                    self.giris_ekrani(None, e_posta.value)
                    self.bildir("Hesap açıldı. E-postanıza gelen doğrulama bağlantısına tıklayıp giriş yapın.")

            await self.guvenli(is_, dugme)

        dugme.on_click = kaydol
        if deneme:
            bilgi = [ft.Container(deneme_rozeti(), alignment=ft.Alignment.CENTER),
                     aciklama("1) Hesabınızı açın ve e-postanıza gelen bağlantıyla doğrulayın. "
                              "2) Giriş yapın, okul adınızı ve kurum kodunuzu girerek denemeyi başlatın. "
                              "Bir ay boyunca tüm özellikler açıktır.")]
        else:
            bilgi = [aciklama("Okul müdürü hesabını açıp lisans kodunu girer veya 1 aylık denemeyi başlatır. "
                              "Diğer kullanıcılar, müdürün davet ettiği e-postayla hesap açar; doğrulamadan sonra "
                              "okula kendiliğinden bağlanır.")]
        self.sayfayi_kur(ortali(
            ft.Container(logo(96, 52), alignment=ft.Alignment.CENTER),
            baslik("Ücretsiz denemeye başlayın" if deneme else "Hesap aç"),
            *bilgi,
            e_posta, sifre, sifre2, dugme,
            ft.TextButton("Girişe dön", on_click=lambda _: self.giris_ekrani(None, e_posta.value)),
        ))

    def sifre_ekrani(self, eposta: str = ""):
        e_posta = ft.TextField(label="E-posta", value=eposta, keyboard_type=ft.KeyboardType.EMAIL)
        dugme = ft.FilledButton("Sıfırlama bağlantısı gönder", icon=ft.Icons.LOCK_RESET)

        async def gonder(_):
            if await self.guvenli(lambda: self.supa.sifre_sifirla(e_posta.value), dugme):
                self.giris_ekrani(None, e_posta.value)
                self.bildir("Şifre sıfırlama bağlantısı e-postanıza gönderildi.")

        dugme.on_click = gonder
        self.sayfayi_kur(ortali(
            ft.Container(logo(96, 52), alignment=ft.Alignment.CENTER),
            baslik("Şifremi unuttum"), aciklama("E-postanıza bir sıfırlama bağlantısı gönderilir."),
            e_posta, dugme,
            ft.TextButton("Girişe dön", on_click=lambda _: self.giris_ekrani(None, e_posta.value)),
        ))

    # ------------------------------------------------------------------ not yet a member
    def uyelik_yok_ekrani(self):
        ben = self.ben or {}
        cikis = ft.TextButton("Çıkış yap", icon=ft.Icons.LOGOUT, on_click=self.cikis)
        yenile = ft.OutlinedButton("Yenile", icon=ft.Icons.REFRESH)

        async def yenile_tik(_):
            await self.guvenli(self.ben_yukle, yenile)

        yenile.on_click = yenile_tik
        if ben.get("pasif"):
            self.sayfayi_kur(ortali(baslik("Hesabınız pasif"),
                                    aciklama("Okul müdürünüz hesabınızı pasif yaptı. Yeniden açılması için "
                                             "müdürünüze başvurun."), yenile, cikis))
            return
        if ben.get("okul_kapali"):
            self.sayfayi_kur(ortali(baslik("Okul lisansı kapalı"),
                                    aciklama("Okulunuzun DÖSE lisansı kapatılmış. Kayıtlarınız silinmedi; "
                                             "lisans açıldığında kaldığınız yerden devam edersiniz."),
                                    yenile, cikis))
            return
        kod = ft.TextField(label="Etkinleştirme kodu", hint_text="DOSE-XXXX-XXXX-…",
                           capitalization=ft.TextCapitalization.CHARACTERS)
        kurum_kodu = ft.TextField(label="MEB kurum kodu", keyboard_type=ft.KeyboardType.NUMBER)
        ad_soyad = ft.TextField(label="Adınız soyadınız")
        etkinlestir = ft.FilledButton("Okulu etkinleştir", icon=ft.Icons.KEY)

        async def etkinlestir_tik(_):
            async def is_():
                sonuc = await self.supa.rpc("dose_okul_etkinlestir", p_kod=kod.value.strip(),
                                            p_kurum_kodu=kurum_kodu.value.strip(), p_ad_soyad=ad_soyad.value.strip())
                if not sonuc.get("basarili"):
                    raise SupaHata(sonuc.get("hata") or "Kod kabul edilmedi.")
                await self.ben_yukle()
                self.bildir("Okul etkinleştirildi. Okul Müdürü olarak giriş yaptınız.")

            await self.guvenli(is_, etkinlestir)

        etkinlestir.on_click = etkinlestir_tik
        okul_adi = ft.TextField(label="Okulun adı", hint_text="Örn. Derik Mesleki ve Teknik Anadolu Lisesi")
        deneme = ft.FilledButton(
            "1 ay ücretsiz denemeyi başlat", icon=ft.Icons.ROCKET_LAUNCH, height=46,
            style=ft.ButtonStyle(bgcolor=ft.Colors.AMBER_400, color=ft.Colors.BROWN_900, icon_color=ft.Colors.BROWN_900))

        async def deneme_tik(_):
            async def is_():
                sonuc = await self.supa.rpc("dose_deneme_baslat", p_okul_adi=okul_adi.value.strip(),
                                            p_kurum_kodu=kurum_kodu.value.strip(), p_ad_soyad=ad_soyad.value.strip())
                await self.ben_yukle()
                bitis = str(sonuc.get("lisans_bitis") or "")
                gun = ".".join(reversed(bitis.split("-"))) if bitis else ""
                self.bildir(f"Deneme başladı. {gun} tarihine kadar tüm özellikler açık." if gun
                            else "Deneme başladı. Okul Müdürü olarak giriş yaptınız.")

            await self.guvenli(is_, deneme)

        deneme.on_click = deneme_tik
        uyari = None if ben.get("eposta_dogrulandi", True) else ft.Text(
            "E-posta adresiniz doğrulanmamış. Önce gelen kutunuzdaki bağlantıya tıklayın.", color=ft.Colors.ERROR)
        self.sayfayi_kur(ortali(*[k for k in (
            ft.Container(logo(96, 52), alignment=ft.Alignment.CENTER),
            baslik("Okula bağlanın"),
            aciklama(f"{ben.get('eposta', '')} hesabı henüz bir okula bağlı değil."),
            uyari,
            ft.Text("Okul müdürüyseniz önce bu bilgileri girin:", weight=ft.FontWeight.BOLD),
            ad_soyad, kurum_kodu,
            ft.Container(ft.Column([
                ft.Row([ft.Icon(ft.Icons.CARD_GIFTCARD, color=ft.Colors.AMBER_900),
                        ft.Text("1 ay ücretsiz deneyin", weight=ft.FontWeight.BOLD, color=ft.Colors.BROWN_900)]),
                aciklama("Lisans kodunuz yoksa okulunuzu hemen açın. Bir ay boyunca tüm özellikler açıktır; "
                         "süre bitince kayıtlarınız korunur ve lisans alınca kaldığınız yerden devam edersiniz. "
                         "Her hesap bir kez deneme açabilir."),
                okul_adi, deneme], spacing=10),
                padding=16, border_radius=16, bgcolor=ft.Colors.AMBER_50, border=ft.Border.all(1, ft.Colors.AMBER_200)),
            ft.Container(ft.Column([
                ft.Row([ft.Icon(ft.Icons.KEY, color=ANA_RENK),
                        ft.Text("Lisans kodunuz varsa", weight=ft.FontWeight.BOLD, color=ANA_RENK)]),
                aciklama("Satıcının verdiği tek kullanımlık kodu girin. Okulun ilk Okul Müdürü siz olursunuz."),
                kod, etkinlestir], spacing=10),
                padding=16, border_radius=16, bgcolor=ft.Colors.TEAL_50, border=ft.Border.all(1, ft.Colors.TEAL_100)),
            ft.Container(ft.Column([
                ft.Row([ft.Icon(ft.Icons.GROUPS, color=ft.Colors.BLUE_GREY_700),
                        ft.Text("Okul çalışanıysanız", weight=ft.FontWeight.BOLD)]),
                aciklama("Müdürünüz bu e-posta adresini Kullanıcılar ekranından eklesin. Sonra Yenile'ye basın."),
                yenile], spacing=10),
                padding=16, border_radius=16, bgcolor=ft.Colors.BLUE_GREY_50),
            cikis) if k is not None]))

    # ------------------------------------------------------------------ main shell
    def gorunur_sayfalar(self) -> list[tuple]:
        return [s for s in SAYFALAR if s[3] is None or self.yetki(s[3])]

    def _menu_cubugu(self) -> ft.Control:
        """Top menu bar built from the pages this user may open; the open page and its group are highlighted."""
        gorunur = {s[0]: s for s in self.gorunur_sayfalar()}

        def ac(anahtar):
            async def tikla(_):
                await self.sayfa_ac(anahtar)
            return tikla

        def ust_stil(secili: bool) -> ft.ButtonStyle:
            return ft.ButtonStyle(color="#ffffff", icon_color="#ffffff",
                                  bgcolor="#163a5c" if secili else ANA_RENK,
                                  padding=ft.Padding.symmetric(horizontal=14, vertical=12),
                                  shape=ft.RoundedRectangleBorder(radius=8))

        def ust_baslik(etiket: str, secili: bool) -> ft.Text:
            return ft.Text(etiket, color="#ffffff",
                           weight=ft.FontWeight.BOLD if secili else ft.FontWeight.W_500)

        ogeler: list[ft.Control] = []
        ana = gorunur["ana"]
        ogeler.append(ft.MenuItemButton(content=ust_baslik(ana[1], self.sayfa == "ana"),
                                        leading=ft.Icon(ana[2], color="#ffffff"),
                                        style=ust_stil(self.sayfa == "ana"), on_click=ac("ana")))
        for grup, grup_ikonu, anahtarlar in MENU_GRUPLARI:
            sayfalar = [gorunur[a] for a in anahtarlar if a in gorunur]
            if not sayfalar:
                continue
            grup_secili = any(s[0] == self.sayfa for s in sayfalar)
            alt = [ft.MenuItemButton(
                content=ft.Text(e, weight=ft.FontWeight.BOLD if a == self.sayfa else None,
                                color=ANA_RENK if a == self.sayfa else METIN),
                leading=ft.Icon(i, color=ANA_RENK if a == self.sayfa else METIN_IKINCIL),
                style=ft.ButtonStyle(bgcolor=tema.SECILI_DOLGU if a == self.sayfa else YUZEY,
                                     padding=ft.Padding.symmetric(horizontal=16, vertical=12)),
                on_click=ac(a)) for a, e, i, _ in sayfalar]
            ogeler.append(ft.SubmenuButton(content=ust_baslik(grup, grup_secili),
                                           leading=ft.Icon(grup_ikonu, color="#ffffff"),
                                           style=ust_stil(grup_secili),
                                           menu_style=ft.MenuStyle(bgcolor=YUZEY, elevation=6),
                                           controls=alt))
        cubuk = ft.MenuBar(controls=ogeler, style=ft.MenuStyle(
            bgcolor=ANA_RENK, elevation=0, padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            shape=ft.RoundedRectangleBorder(radius=0)))
        return ft.Container(ft.Row([cubuk], scroll=ft.ScrollMode.AUTO, spacing=0),
                            bgcolor=ANA_RENK, padding=ft.Padding.symmetric(horizontal=4, vertical=2))

    @staticmethod
    def _lisans_rozeti(okul: dict) -> ft.Control:
        """Trial countdown or read-only warning next to the user name; hidden for a valid paid license."""
        if okul.get("salt_okunur"):
            metin, ikon, zemin, renk = ("Deneme bitti · salt okunur" if okul.get("deneme") else "Lisans bitti · salt okunur",
                                        ft.Icons.LOCK_CLOCK, ft.Colors.RED_50, ft.Colors.RED_800)
        elif okul.get("deneme"):
            metin, ikon, zemin, renk = (f"Deneme · {okul.get('kalan_gun', '?')} gün kaldı", ft.Icons.CARD_GIFTCARD,
                                        ft.Colors.AMBER_100, ft.Colors.BROWN_900)
        else:
            return ft.Container(visible=False)
        return ft.Container(ft.Row([ft.Icon(ikon, size=16, color=renk),
                                    ft.Text(metin, size=12, weight=ft.FontWeight.BOLD, color=renk)],
                                   spacing=4, tight=True),
                            bgcolor=zemin, border_radius=14, padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                            tooltip="Lisans için yetkili satıcıyla iletişime geçin.")

    def kabuk_kur(self):
        self.genis = (self.page.width or 0) >= GENIS_EKRAN
        okul = (self.ben or {}).get("okul") or {}
        cikis = ft.IconButton(ft.Icons.LOGOUT, tooltip="Çıkış yap", icon_color=ANA_RENK, on_click=self.cikis)
        kullanici = ft.Column([
            ft.Text(self.ben.get("ad_soyad") or self.ben.get("eposta") or "", size=13, weight=ft.FontWeight.W_600,
                    color=METIN),
            ft.Text(self.ben.get("rol") or "", size=11, color=METIN_IKINCIL)],
            spacing=0, horizontal_alignment=ft.CrossAxisAlignment.END, visible=self.genis)
        baslik_satiri = ft.Container(ft.Row([
            logo(120, 44) if self.genis else uygulama_ikonu(36),
            ft.Column([ft.Text("DÖSE Yönetim", size=18 if self.genis else 15, weight=ft.FontWeight.BOLD,
                               color=METIN),
                       ft.Text(okul.get("ad", ""), size=12, color=METIN_IKINCIL,
                               max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)], spacing=0, expand=True),
            kullanici,
            self._lisans_rozeti(okul),
            ft.Icon(ft.Icons.ACCOUNT_CIRCLE, color=ANA_RENK, size=30, visible=self.genis),
            cikis,
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=16, vertical=10), bgcolor=YUZEY,
            border=ft.Border.only(bottom=ft.BorderSide(1, KENAR)))
        self.menu_kutu = ft.Container(self._menu_cubugu(), bgcolor=ANA_RENK)
        self.sayfa_ikonu = ft.Icon(ft.Icons.HOME, color=ANA_RENK)
        self.sayfa_basligi = ft.Text(SAYFA_ADI.get(self.sayfa, "DÖSE"), size=18, weight=ft.FontWeight.BOLD,
                                     color=METIN)
        sayfa_satiri = ft.Container(ft.Row([self.sayfa_ikonu, self.sayfa_basligi], spacing=10),
                                    padding=ft.Padding.only(left=20, right=16, top=12, bottom=0), bgcolor=ZEMIN)
        self.page.appbar = None
        self.page.drawer = None
        self.page.controls.clear()
        self.page.add(ft.Column([baslik_satiri, self.menu_kutu, sayfa_satiri, self.govde], spacing=0, expand=True))
        self._sayfa_basligini_guncelle()
        self.page.update()

    def _sayfa_basligini_guncelle(self):
        if getattr(self, "menu_kutu", None) is None:
            return
        self.menu_kutu.content = self._menu_cubugu()
        self.sayfa_basligi.value = SAYFA_ADI.get(self.sayfa, "DÖSE")
        self.sayfa_ikonu.icon = next((i for a, _, i, _ in SAYFALAR if a == self.sayfa), ft.Icons.HOME)

    async def sayfa_ac(self, anahtar: str):
        if self.ekran is not None and self.ekran.islemde:
            self.bildir("İşlem tamamlanana kadar bekleyin.", hata=True)
            return
        if self.ekran is not None and self.ekran.kaydedilmemis():
            self.kabuk_kur()

            async def devam():
                await self._sayfa_ac_uygula(anahtar)
                self.kabuk_kur()

            self.onayla("Kaydedilmemiş değişiklikler bırakılacak.", "Değişiklikleri bırak", devam)
            return
        await self._sayfa_ac_uygula(anahtar)

    async def _sayfa_ac_uygula(self, anahtar: str):
        try:
            from . import ekranlar as E
        except ImportError:
            import ekranlar as E
        self.sayfa = anahtar
        if anahtar == "ana":
            ekran = E.AnaEkran(self)
        elif anahtar == "kurum":
            ekran = E.KurumEkrani(self)
        elif anahtar in T.TANIM_ALANLARI:
            ekran = E.TanimEkrani(self, anahtar, SAYFA_ADI[anahtar])
        elif anahtar == "siparis":
            ekran = E.SiparisEkrani(self)
        elif anahtar == "fatura":
            try:
                from . import faturalar as Fatura
            except ImportError:
                import faturalar as Fatura
            ekran = Fatura.FaturaEkrani(self)
        elif anahtar == "kasa":
            try:
                from . import kasa as Kasa
            except ImportError:
                import kasa as Kasa
            ekran = Kasa.KasaEkrani(self)
        elif anahtar == "parca_basi":
            try:
                from . import parca_basi as PB
            except ImportError:
                import parca_basi as PB
            ekran = PB.ParcaBasiEkrani(self)
        elif anahtar == "fazla_calisma":
            try:
                from . import fazla_calisma as FC
            except ImportError:
                import fazla_calisma as FC
            ekran = FC.FazlaCalismaEkrani(self)
        elif anahtar == "hazine_payi":
            try:
                from . import hazine_payi as HP
            except ImportError:
                import hazine_payi as HP
            ekran = HP.HazinePayiEkrani(self)
        elif anahtar == "yil_sonu":
            try:
                from . import yil_sonu as YS
            except ImportError:
                import yil_sonu as YS
            ekran = YS.YilSonuEkrani(self)
        elif anahtar == "maliyet":
            try:
                from . import maliyet as Mal
            except ImportError:
                import maliyet as Mal
            ekran = Mal.MaliyetEkrani(self)
        elif anahtar == "raporlar":
            try:
                from . import raporlar as Rap
            except ImportError:
                import raporlar as Rap
            ekran = Rap.RaporlarEkrani(self)
        elif anahtar in ("resmi_yazi", "denetim"):
            try:
                from . import resmi as Res
            except ImportError:
                import resmi as Res
            ekran = Res.ResmiYaziEkrani(self) if anahtar == "resmi_yazi" else Res.DenetimEkrani(self)
        elif anahtar in ("stok", "yevmiye", "vergi_hesap"):
            try:
                from . import finans as F
            except ImportError:
                import finans as F
            ekran = {"stok": F.StokEkrani, "yevmiye": F.YevmiyeEkrani, "vergi_hesap": F.HesapEkrani}[anahtar](self)
        elif anahtar in ("mevzuat", "merkez_mevzuat"):
            try:
                from . import mevzuat as M
            except ImportError:
                import mevzuat as M
            ekran = M.MevzuatEkrani(self, merkez=anahtar == "merkez_mevzuat")
        elif anahtar == "kullanici":
            ekran = E.KullaniciEkrani(self)
        else:
            ekran = E.IslemKaydiEkrani(self)
        self.ekran = ekran
        self._sayfa_basligini_guncelle()
        self.govde.content = ft.Container(ft.ProgressRing(), alignment=ft.Alignment.CENTER)
        self.page.update()
        self.govde.content = ekran.kontrol
        if not await self.guvenli(ekran.yukle):
            self.govde.content = ft.Container(ft.Text("Bu sayfa yüklenemedi. Bağlantınızı kontrol edip yeniden açın."),
                                              padding=20)
        self.page.update()

    async def _boyut_degisti(self, _=None):
        if self.ben is None or not self.ben.get("uye"):
            return
        genis = (self.page.width or 0) >= GENIS_EKRAN
        if genis != self.genis:
            self.kabuk_kur()
            if self.ekran is not None:
                self.govde.content = self.ekran.kontrol
                self.ekran.duzen()
                self.page.update()

    async def _izle(self):
        """Live refresh: when anyone in the school writes, the open screen reloads (unsaved edits are kept)."""
        while self.ben is not None and self.ben.get("uye"):
            await asyncio.sleep(ayar.YENILEME_ARALIGI)
            if self.ben is None:
                break
            try:
                son = await self.supa.rpc("dose_son_degisiklik")
                if self.son_log is not None and son != self.son_log and self.ekran is not None:
                    self.son_log = son
                    await self.ekran.uzaktan_degisti()
                self.son_log = son
            except SupaHata:
                pass
            except Exception:
                pass


def calistir():
    async def main(page: ft.Page):
        await Uygulama(page).basla()

    return main
