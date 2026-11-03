"""Central allocation-rate publications and school treasurer confirmations."""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import flet as ft

try:
    from . import tanimlar as T
    from .ekranlar import Ekran, uyari_seridi
    from .finans import kayit_sonrasi_yenile
    from .supa import SupaHata
except ImportError:
    import tanimlar as T
    from ekranlar import Ekran, uyari_seridi
    from finans import kayit_sonrasi_yenile
    from supa import SupaHata


def kesin_oran(metin: str, etiket: str) -> str:
    try:
        yuzde = T.ondalik_coz(metin)
    except ValueError as e:
        raise ValueError(f"{etiket} için geçerli bir yüzde giriniz.") from e
    if not Decimal(0) <= yuzde <= Decimal(100):
        raise ValueError(f"{etiket} %0 ile %100 arasında olmalıdır.")
    if yuzde == 0:
        return "0"
    oran = format(T.siparis_yuzdesi_orana(yuzde), "f")
    if "." in oran:
        oran = oran.rstrip("0").rstrip(".")
    if len(oran.partition(".")[2]) > 10:
        raise ValueError(f"{etiket} en fazla 10 ondalıklı oranla ifade edilmelidir.")
    return oran


class MevzuatEkrani(Ekran):
    def __init__(self, app, merkez: bool):
        super().__init__(app)
        self.merkez = merkez
        self.veri: dict = {"alanlar": [], "yayinlar": []}
        self.secili: dict | None = None
        self.form: dict[str, ft.TextField] | None = None
        self.istek_id = ""
        self.kirli = False
        self.uzak_uyari = False

    @property
    def karar_verebilir(self) -> bool:
        return (not self.merkez and self.app.yetki("mevzuat") == "y"
                and (self.app.ben or {}).get("rol") == "Sayman")

    def kaydedilmemis(self) -> bool:
        return self.form is not None and self.kirli

    def _degisti(self, _=None):
        self.kirli = True

    async def yukle(self):
        ad = "dose_mevzuat_merkez_veri" if self.merkez else "dose_mevzuat_okul_veri"
        self.veri = await self.app.supa.rpc(ad)
        if self.secili:
            self.secili = next((y for y in self.veri["yayinlar"] if y["id"] == self.secili["id"]), None)
        self._ciz()

    async def uzaktan_degisti(self):
        if self.form is not None:
            self.uzak_uyari = True
        await self.yukle()

    def duzen(self):
        self._ciz()

    def _yeni(self, _=None):
        if not self.merkez or self.form is not None or self.islemde:
            return
        self.form = {
            "baslangic": ft.TextField(label="Geçerlilik başlangıcı *", hint_text="GG.AA.YYYY",
                                       on_change=self._degisti),
            "kaynak": ft.TextField(label="Resmî dayanak / kontrol kaynağı *", multiline=True,
                                    min_lines=2, on_change=self._degisti),
        }
        for alan in self.veri["alanlar"]:
            self.form[alan["anahtar"]] = ft.TextField(
                label=f"{alan['etiket']} (%) *", helper=alan["aciklama"],
                keyboard_type=ft.KeyboardType.NUMBER, on_change=self._degisti)
        self.istek_id = str(uuid4())
        self.kirli = False
        self.uzak_uyari = False
        self._ciz()

    def _kapat(self, _=None):
        if self.islemde:
            self.app.bildir("İşlem tamamlanana kadar bekleyin.", hata=True)
        elif self.kaydedilmemis():
            self.app.onayla("Kaydedilmemiş parametre yayını bırakılacak.", "Değişiklikleri bırak", self._kapat_uygula)
        else:
            self.form = None
            self._ciz()

    async def _kapat_uygula(self):
        self.form = None
        self.kirli = False
        self._ciz()

    async def _yayinla(self, dugme):
        async def is_():
            form = self.form
            if form is None:
                raise ValueError("Önce yeni bir parametre yayını açın.")
            try:
                baslangic = T.tarih_coz(form["baslangic"].value or "")
            except ValueError as e:
                raise ValueError("Geçerli bir başlangıç tarihi giriniz (GG.AA.YYYY).") from e
            kaynak = (form["kaynak"].value or "").strip()
            if len(kaynak) < 5:
                raise ValueError("İncelenen resmî dayanağı veya kontrol kaynağını yazınız.")
            degerler = {
                alan["anahtar"]: kesin_oran(form[alan["anahtar"]].value or "", alan["etiket"])
                for alan in self.veri["alanlar"]
            }
            try:
                await self.app.supa.rpc("dose_mevzuat_yayinla", p_baslangic=baslangic, p_kaynak=kaynak,
                                        p_degerler=degerler, p_istek=self.istek_id)
            except SupaHata as e:
                if e.kod == "ag" or e.durum in (502, 503, 504):
                    raise SupaHata("Bağlantı kesildi; yayın kaydedilmiş olabilir. Listeyi kontrol edin veya "
                                   "aynı formu tekrar gönderin; aynı işlem iki kez kaydedilmez.",
                                   e.durum, e.kod, e.ipucu) from e
                raise
            self.form = None
            self.kirli = False
            self._ciz()
            await kayit_sonrasi_yenile(self, "Merkez parametre yayını kaydedildi.")

        await self.guvenli_islem(is_, dugme)

    def _karar_dialog(self, yayin: dict, onay: bool):
        if self.islemde or self.form is not None or not self.karar_verebilir:
            return
        aciklama = ft.TextField(label="Doğrulama açıklaması *" if onay else "Geri çekme gerekçesi *",
                                 multiline=True, min_lines=2)
        kaydet = ft.FilledButton("Doğrulamayı kaydet" if onay else "Doğrulamayı geri çek")
        vazgec = ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog())
        istek = str(uuid4())

        async def onayla(_):
            async def is_():
                not_ = (aciklama.value or "").strip()
                if len(not_) < 5:
                    raise ValueError("En az 5 karakterlik açıklama veya gerekçe giriniz.")
                try:
                    await self.app.supa.rpc("dose_mevzuat_karar", p_yayin=yayin["id"], p_onay=onay,
                                            p_aciklama=not_, p_istek=istek)
                except SupaHata as e:
                    if e.kod == "ag" or e.durum in (502, 503, 504):
                        raise SupaHata("Bağlantı kesildi; karar kaydedilmiş olabilir. Listeyi kontrol edin veya "
                                       "aynı işlemi tekrar deneyin.", e.durum, e.kod, e.ipucu) from e
                    raise
                self.app.page.pop_dialog()
                await kayit_sonrasi_yenile(
                    self, "Parametre yayını okulunuz için doğrulandı." if onay
                    else "Okulunuzun doğrulaması geri çekildi.")

            await self.guvenli_islem(is_, kaydet, (aciklama, vazgec))

        kaydet.on_click = onayla
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text("Merkez yayını kontrolü"),
            content=ft.Column([
                ft.Text(f"Yayın #{yayin['id']} · başlangıç {T.gosterim('tarih', yayin['baslangic'])}"),
                ft.Text("Değerleri ve dayanağı kontrol ettiğinizi doğrulayın." if onay
                        else "Geri çekildikten sonra bu yayın okulunuz için kullanılamaz."),
                aciklama], tight=True),
            actions=[vazgec, kaydet]))

    def _sec(self, yayin: dict):
        if self.islemde or self.form is not None:
            return
        self.secili = yayin
        self._ciz()

    def _ciz(self):
        kontroller: list[ft.Control] = [
            ft.Row([ft.Text("Merkez parametre yayını" if self.merkez else "Okul parametre doğrulaması",
                            size=20, weight=ft.FontWeight.BOLD, expand=True),
                    ft.FilledButton("Yeni yayın", icon=ft.Icons.ADD, visible=self.merkez,
                                    disabled=self.form is not None or self.islemde, on_click=self._yeni),
                    ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile", disabled=self.islemde,
                                  on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))],
                   wrap=True),
            ft.Text("Burada sipariş maliyet ve işçilik tahsis oranlarının yasal alt/üst sınırları yayımlanır. "
                    "Gelir vergisi oranı, damga vergisi, asgari ücret, peşin vergi ve SHÇEK payı her parça başı "
                    "hakedişte ayrıca girilir ve hakediş onayıyla dondurulur."),
            ft.Text("Değerler girilen tarihten aynı yılın sonuna kadar, varsa daha sonraki başlangıç tarihine dek "
                    "geçerlidir. Aynı başlangıç tarihli son yayın kullanılır; okul saymanı ayrıca doğrular.", size=12),
        ]
        if self.form is not None:
            for kontrol in self.form.values():
                kontrol.disabled = self.islemde
            kaydet = ft.FilledButton("Yayını kaydet", icon=ft.Icons.SAVE, disabled=self.islemde)
            kaydet.on_click = lambda _: self.app.onayla(
                "Aynı başlangıç tarihli yeni bir yayın, önceki sürümün okul doğrulamalarını geçersiz kılar. "
                "Değerleri ve dayanağı kontrol ettiniz mi?", "Yayımla", lambda: self._yayinla(kaydet))
            alanlar: list[ft.Control] = list(self.form.values())
            kontroller.append(ft.Card(ft.Container(ft.Column([
                ft.Text("Yeni merkez yayını", size=18, weight=ft.FontWeight.BOLD),
                *([uyari_seridi("Sunucu kayıtları değişti. Formunuz korundu.")] if self.uzak_uyari else []),
                ft.Text("Varsayılan oran yoktur. Her değeri ve resmî kaynağı yayınlamadan önce kontrol edin."),
                ft.ResponsiveRow([ft.Container(k, col={"xs": 12, "md": 6}) for k in alanlar]),
                ft.Row([kaydet, ft.TextButton("Vazgeç", disabled=self.islemde, on_click=self._kapat)], wrap=True),
            ], spacing=12), padding=16)))
        kontroller.append(ft.Text("Yayın geçmişi", size=18, weight=ft.FontWeight.BOLD))
        for yayin in self.veri["yayinlar"]:
            durum = "Son sürüm" if yayin["son_surum"] else "Eski sürüm"
            if not self.merkez:
                durum += " · Okulca doğrulandı" if yayin["onay"] else " · Okulca doğrulanmadı"
            kontroller.append(ft.ListTile(
                title=ft.Text(f"{T.gosterim('tarih', yayin['baslangic'])} · Yayın #{yayin['id']}"),
                subtitle=ft.Text(durum), selected=bool(self.secili and self.secili["id"] == yayin["id"]),
                disabled=self.form is not None or self.islemde,
                on_click=lambda _, y=yayin: self._sec(y)))
        if not self.veri["yayinlar"]:
            kontroller.append(ft.Text("Henüz merkez parametre yayını yok."))
        if self.secili is not None and self.form is None:
            yayin = self.secili
            detay: list[ft.Control] = [
                ft.Text(f"Yayın #{yayin['id']} · {T.gosterim('tarih', yayin['baslangic'])}",
                        size=18, weight=ft.FontWeight.BOLD),
                ft.Text(f"Dayanak / kaynak: {yayin['kaynak']}"),
            ]
            if not yayin["son_surum"]:
                detay.append(uyari_seridi("Aynı başlangıç tarihi için daha yeni bir yayın var; bu sürüm kullanılmaz."))
            detay.extend(ft.Text(f"{a['etiket']}: %{T.siparis_yuzdesi_yaz(yayin['degerler'][a['anahtar']])}")
                         for a in self.veri["alanlar"])
            if not self.merkez:
                if yayin.get("onay_aciklama"):
                    detay.append(ft.Text(f"Son okul kararı: {yayin['onay_aciklama']}"))
                if self.karar_verebilir and (yayin["onay"] or yayin["son_surum"]):
                    detay.append(ft.FilledButton(
                        "Doğrulamayı geri çek" if yayin["onay"] else "Okul için doğrula",
                        disabled=self.islemde,
                        on_click=lambda _, y=yayin: self._karar_dialog(y, not y["onay"])))
            kontroller.append(ft.Card(ft.Container(ft.Column(detay, spacing=8), padding=16)))
        self.kontrol.controls = kontroller
        self.guncelle()
