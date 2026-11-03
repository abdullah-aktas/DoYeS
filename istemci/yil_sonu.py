"""Yıl sonu kâr dağıtımı / ÜTP: sayman hazırlar, müdür onaylar, sayman ödemeleri kaydeder."""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import flet as ft


def binde_yaz(oran: str | None) -> str:
    if oran in (None, ""):
        return "7,59"
    metin = format(Decimal(oran) * 1000, "f")
    if "." in metin:
        metin = metin.rstrip("0").rstrip(".")
    return metin.replace(".", ",")

try:
    from . import takvim, tanimlar as T
    from .ekranlar import Ekran, secim_kutusu, uyari_seridi
    from .finans import kayit_sonrasi_yenile, para
    from .supa import SupaHata
except ImportError:
    import takvim
    import tanimlar as T
    from ekranlar import Ekran, secim_kutusu, uyari_seridi
    from finans import kayit_sonrasi_yenile, para
    from supa import SupaHata

DURUM_RENGI = {"Taslak": ft.Colors.GREY_600, "Müdür Onayında": ft.Colors.ORANGE_800,
               "Onaylandı": ft.Colors.GREEN_700, "İptal": ft.Colors.RED_700}
GOREV_SECIM = [
    ("Okul Müdürü", "Okul Müdürü"), ("Teknik Müdür Yardımcısı", "Teknik Müdür Yardımcısı"),
    ("Sayman", "Sayman"), ("Bölüm/Alan Şefi", "Bölüm/Alan Şefi"),
    ("Atölye/Laboratuvar Şefi", "Atölye/Laboratuvar Şefi"), ("Öğretmen", "Öğretmen"),
    ("Memur", "Memur"), ("Diğer", "Diğer"),
]


class YilSonuEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        bugun = takvim.bugun_istanbul()
        self.yil = bugun.year - 1
        self.veri: dict = {}
        self.form: dict | None = None
        self.kisiler: list[dict] = []
        self.kayit_id: int | None = None
        self.surum: int | None = None
        self.istek_id = ""
        self.kirli = False
        self.uzak_uyari = False

    @property
    def rol(self) -> str:
        return (self.app.ben or {}).get("rol") or ""

    @property
    def sayman(self) -> bool:
        return self.rol == "Sayman" and self.app.yetki("yil_sonu") == "y"

    @property
    def mudur(self) -> bool:
        return self.rol == "Okul Müdürü" and self.app.yetki("yil_sonu") == "y"

    def kaydedilmemis(self) -> bool:
        return self.form is not None and self.kirli

    def _degisti(self, _=None):
        self.kirli = True

    async def yukle(self):
        self.veri = await self.app.supa.rpc("dose_ys_veri", p_yil=self.yil)
        self.yil = int(self.veri.get("yil") or self.yil)
        self._ciz()

    async def uzaktan_degisti(self):
        if self.form is not None:
            self.uzak_uyari = True
            self.veri = await self.app.supa.rpc("dose_ys_veri", p_yil=self.yil)
            self._ciz()
            return
        await self.yukle()

    def duzen(self):
        self._ciz()

    def _yil_degisti(self, e):
        try:
            self.yil = int(e.control.value)
        except (TypeError, ValueError):
            return
        self.form = None
        self.app.page.run_task(self.app.guvenli, self.yukle)

    def _ac(self, kayit: dict | None = None):
        if self.form is not None or self.islemde or not self.sayman:
            return
        kayit = kayit or {}
        v = self.veri.get("varsayilan") or {}
        def alan(etiket, deger="", **ek):
            return ft.TextField(label=etiket, value=deger, on_change=self._degisti, **ek)
        sayi = {"keyboard_type": ft.KeyboardType.NUMBER}
        self.form = {
            "yil": alan("Yıl *", str(kayit.get("yil") or self.yil), width=100, disabled=bool(kayit), **sayi),
            "utp": alan("ÜTP oranı (%) *", T.siparis_yuzdesi_yaz(kayit.get("utp_orani") or v.get("utp_orani")), **sayi),
            "shcek": alan("SHÇEK oranı (%) *", T.siparis_yuzdesi_yaz(kayit.get("shcek_orani") or v.get("shcek_orani")), **sayi),
            "dv": alan("Damga vergisi (binde) *", binde_yaz(kayit.get("dv_orani") or v.get("dv_orani")), **sayi),
            "tavan": alan("Kişi başı yıllık ÜTP tavanı (TL) *",
                          T.siparis_sayisi_yaz(kayit.get("yillik_tavan") or v.get("yillik_tavan")), **sayi),
            "tahsis": alan("Tahsis edilen sermaye (TL)", T.siparis_sayisi_yaz(kayit.get("tahsis_sermaye") or "0"), **sayi),
            "odenmis": alan("Ödenmiş sermaye (TL)", T.siparis_sayisi_yaz(kayit.get("odenmis_sermaye") or "0"), **sayi),
            "aciklama": alan("Açıklama", kayit.get("aciklama") or "", multiline=True, min_lines=2),
        }
        self.yuz_yuze = ft.Checkbox(label="Yüz yüze eğitim yapıldı",
                                    value=bool(kayit["yuz_yuze"]) if "yuz_yuze" in kayit else True,
                                    on_change=self._degisti)
        self.kisiler = []
        for k in kayit.get("kisiler") or []:
            self._kisi_satir_ekle(k)
        self.kayit_id = kayit.get("id")
        self.surum = kayit.get("surum")
        self.istek_id = str(uuid4())
        self.kirli = False
        self.uzak_uyari = False
        self._ciz()

    def _kisi_satir_ekle(self, k: dict | None = None):
        k = k or {}
        personel = [(str(p["id"]), p["ad_soyad"]) for p in self.veri.get("personel") or []]
        bolumler = [(str(b["id"]), b["ad"]) for b in self.veri.get("bolumler") or []]
        satir = {
            "personel": secim_kutusu("Personel *", personel, k.get("personel_id"), bos=False, on_select=self._degisti),
            "gorev": secim_kutusu("Görev *", GOREV_SECIM, k.get("gorev") or "Öğretmen", bos=False, on_select=self._degisti),
            "unvan": ft.TextField(label="Unvan grubu (1-5) *", value=str(k.get("unvan_grubu") or 3),
                                  width=100, keyboard_type=ft.KeyboardType.NUMBER, on_change=self._degisti),
            "bolum": secim_kutusu("Bölüm", bolumler, k.get("bolum_id"), on_select=self._degisti),
            "haric": ft.Checkbox(label="Dağıtım dışı (md.6)", value=bool(k.get("haric")), on_change=self._degisti),
            "haric_neden": ft.TextField(label="Hariç nedeni", value=k.get("haric_neden") or "", on_change=self._degisti),
            "gv": ft.TextField(label="GV %", value=T.siparis_yuzdesi_yaz(k.get("gv_orani") or "0.15"),
                               width=80, keyboard_type=ft.KeyboardType.NUMBER, on_change=self._degisti),
        }
        self.kisiler.append(satir)

    def _kisiler_veri(self) -> list[dict]:
        sonuc = []
        for i, s in enumerate(self.kisiler, 1):
            if not s["personel"].value:
                raise ValueError(f"{i}. satırda personel seçiniz.")
            try:
                grup = int((s["unvan"].value or "").strip())
            except ValueError as e:
                raise ValueError(f"{i}. satırda unvan grubu 1-5 olmalıdır.") from e
            haric = bool(s["haric"].value)
            kayit = {
                "personel_id": int(s["personel"].value), "gorev": s["gorev"].value,
                "unvan_grubu": grup, "bolum_id": int(s["bolum"].value) if s["bolum"].value else None,
                "haric": haric, "haric_neden": (s["haric_neden"].value or "").strip() or None,
                "fiili_gun": "0", "fc_saat": "0", "katki_orani": "0", "takdir_orani": "0",
                "onceki_utp": "0", "gv_orani": format(T.ondalik_coz(s["gv"].value or "15") / 100, "f"),
            }
            sonuc.append(kayit)
        return sonuc

    def _form_veri(self) -> dict:
        f = self.form
        assert f is not None
        yil = int((f["yil"].value or "").strip())
        utp = T.ondalik_coz(f["utp"].value or "0") / 100
        shcek = T.ondalik_coz(f["shcek"].value or "0") / 100
        dv = T.ondalik_coz(f["dv"].value or "0") / 1000
        return {
            "yil": yil, "utp_orani": format(utp, "f"), "shcek_orani": format(shcek, "f"),
            "dv_orani": format(dv, "f"), "yillik_tavan": format(T.ondalik_coz(f["tavan"].value or "0"), "f"),
            "tahsis_sermaye": format(T.ondalik_coz(f["tahsis"].value or "0"), "f"),
            "odenmis_sermaye": format(T.ondalik_coz(f["odenmis"].value or "0"), "f"),
            "yuz_yuze": bool(self.yuz_yuze.value), "aciklama": (f["aciklama"].value or "").strip() or None,
        }

    async def _kaydet(self, dugme):
        async def is_():
            veri = self._form_veri()
            kisiler = self._kisiler_veri()
            sonuc = await self.app.supa.rpc(
                "dose_ys_kaydet", p_id=self.kayit_id, p_surum=self.surum, p_veri=veri,
                p_kisiler=kisiler, p_istek=self.istek_id)
            self.kayit_id = sonuc["id"]
            self.surum = sonuc["surum"]
            self.istek_id = str(uuid4())
            self.kirli = False
            await kayit_sonrasi_yenile(self, f"Cetvel kaydedildi ({sonuc.get('belge_no') or sonuc['id']}).")
            self.form = None
            await self.yukle()
        await self.guvenli_islem(is_, dugme)

    def _kapat(self, _=None):
        if self.islemde:
            self.app.bildir("İşlem tamamlanana kadar bekleyin.", hata=True)
        elif self.kaydedilmemis():
            self.app.onayla("Kaydedilmemiş değişiklikler bırakılacak.", "Değişiklikleri bırak", self._kapat_uygula)
        else:
            self.form = None
            self._ciz()

    async def _kapat_uygula(self):
        self.form = None
        self.kirli = False
        await self.yukle()

    async def _gonder(self, kayit, dugme):
        async def is_():
            sonuc = await self.app.supa.rpc("dose_ys_gonder", p_id=kayit["id"], p_surum=kayit["surum"])
            await kayit_sonrasi_yenile(self, f"Cetvel müdür onayına gönderildi ({sonuc['durum']}).")
            await self.yukle()
        await self.guvenli_islem(is_, dugme)

    def _karar_dialog(self, kayit: dict, onay: bool):
        etiket = "Olur notu" if onay else "İade gerekçesi *"
        alan = ft.TextField(label=etiket, multiline=True, min_lines=2)
        tamam = ft.FilledButton("Onayla" if onay else "İade et")
        vazgec = ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog())

        async def ok(_):
            async def is_():
                metin = (alan.value or "").strip()
                if not onay and not metin:
                    raise ValueError("İade gerekçesi zorunludur.")
                sonuc = await self.app.supa.rpc("dose_ys_karar", p_id=kayit["id"], p_surum=kayit["surum"],
                                                p_onay=onay, p_aciklama=metin)
                self.app.page.pop_dialog()
                await kayit_sonrasi_yenile(self, f"Karar: {sonuc['durum']}.")
                await self.yukle()
            await self.guvenli_islem(is_, tamam, (alan, vazgec))

        tamam.on_click = ok
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text(("Olur" if onay else "İade") + f" · {kayit.get('belge_no')}"),
            content=ft.Column([alan], tight=True), actions=[vazgec, tamam]))

    def _ode_dialog(self, kayit: dict, kalem: str):
        tarih = ft.TextField(label="Ödeme tarihi *", value=takvim.bugun_istanbul().strftime("%d.%m.%Y"))
        belge = ft.TextField(label="Dekont no *")
        ode = ft.FilledButton("Ödemeyi kaydet", icon=ft.Icons.PAYMENTS)
        vazgec = ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog())
        istek = str(uuid4())

        async def ok(_):
            async def is_():
                gun = T.tarih_coz(tarih.value or "")
                if not (belge.value or "").strip():
                    raise ValueError("Dekont numarası zorunludur.")
                try:
                    await self.app.supa.rpc("dose_ys_ode", p_id=kayit["id"], p_kalem=kalem, p_tarih=gun,
                                            p_belge_no=belge.value.strip(), p_istek=istek)
                except SupaHata as e:
                    if e.kod == "ag" or e.durum in (502, 503, 504):
                        raise SupaHata("Bağlantı kesildi; ödeme kaydedilmiş olabilir. Listeyi yenileyin.",
                                       e.durum, e.kod, e.ipucu) from e
                    raise
                self.app.page.pop_dialog()
                await kayit_sonrasi_yenile(self, f"{kalem} ödemesi kaydedildi.")
                await self.yukle()
            await self.guvenli_islem(is_, ode, (tarih, belge, vazgec))

        ode.on_click = ok
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text(f"{kalem} ödemesi"),
            content=ft.Column([
                ft.Text("Bu ekran banka transferi yapmaz; gerçekleşen ödemeyi kaydeder.", size=12),
                tarih, belge], tight=True),
            actions=[vazgec, ode]))

    def _iptal_dialog(self, kayit: dict):
        gerekce = ft.TextField(label="İptal gerekçesi *", multiline=True, min_lines=2)
        tamam = ft.FilledButton("İptal et")
        vazgec = ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog())

        async def ok(_):
            async def is_():
                if not (gerekce.value or "").strip():
                    raise ValueError("İptal gerekçesi zorunludur.")
                await self.app.supa.rpc("dose_ys_iptal", p_id=kayit["id"], p_surum=kayit["surum"],
                                        p_gerekce=gerekce.value.strip())
                self.app.page.pop_dialog()
                await kayit_sonrasi_yenile(self, "Cetvel iptal edildi.")
                await self.yukle()
            await self.guvenli_islem(is_, tamam, (gerekce, vazgec))

        tamam.on_click = ok
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text("Cetveli iptal et"), content=ft.Column([gerekce], tight=True),
            actions=[vazgec, tamam]))

    def _belgeler(self, kayit: dict):
        try:
            from . import belgeler as B
        except ImportError:
            import belgeler as B
        B.belge_menusu(self.app, self.veri.get("okul") or {}, kayit, B.YS_BELGELER)

    def _hesap_ozeti(self, hesap: dict | None) -> list[ft.Control]:
        if not hesap:
            return []
        satirlar = [("Hasılat", hesap.get("hasilat")), ("Gelir", hesap.get("gelir")), ("Gider", hesap.get("gider")),
                    ("Dönem kârı", hesap.get("donem_kari")), ("SHÇEK", hesap.get("shcek")),
                    ("Dağıtılan ÜTP", hesap.get("dagitilan_utp")), ("Merkez payı", hesap.get("merkez_payi")),
                    ("Sermaye payı", hesap.get("sermaye_payi"))]
        c = [ft.ResponsiveRow([ft.Container(ft.Column([
            ft.Text(e, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text(f"{para(t)} TL", weight=ft.FontWeight.BOLD)], spacing=0), col={"xs": 6, "md": 3})
            for e, t in satirlar if t is not None])]
        for h in hesap.get("hatalar") or []:
            c.append(uyari_seridi(h))
        return c

    def _ciz(self):
        engelli = self.form is not None or self.islemde
        yillar = [(str(y), str(y)) for y in range(takvim.bugun_istanbul().year, 2019, -1)]
        c: list[ft.Control] = [
            ft.Row([ft.Text("Yıl sonu kâr dağıtımı / ÜTP", size=20, weight=ft.FontWeight.BOLD, expand=True),
                    secim_kutusu("Yıl", yillar, self.yil, bos=False, on_select=self._yil_degisti),
                    ft.FilledButton("Yeni cetvel", visible=self.sayman and not self.veri.get("kayit"),
                                    disabled=engelli, on_click=lambda _: self._ac()),
                    ft.IconButton(ft.Icons.REFRESH, disabled=self.islemde,
                                  on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))], wrap=True),
            ft.Text("Cetveli sayman hazırlar; harcama yetkilisi (Okul Müdürü) onaylar. Onayda SHÇEK, kapanış ve "
                    "dağıtım yevmiyeleri oluşur. GİB/banka API’si yoktur.", size=12),
        ]
        if self.uzak_uyari:
            c.append(uyari_seridi("Kayıtlar değişti; formunuz korundu."))
        on = self.veri.get("on_hesap")
        if on and not self.veri.get("kayit"):
            c.append(ft.Card(ft.Container(ft.Column([
                ft.Text("Ön hesap (yevmiye özeti)", weight=ft.FontWeight.BOLD),
                ft.Text(f"Hasılat {para(on.get('hasilat'))} · Gelir {para(on.get('gelir'))} · "
                        f"Gider {para(on.get('gider'))} · SHÇEK tahmini {para(on.get('shcek'))} TL")],
                spacing=6), padding=12)))
        kayit = self.veri.get("kayit")
        if kayit and self.form is None:
            renk = DURUM_RENGI.get(kayit["durum"], ft.Colors.GREY)
            dugmeler = []
            if self.sayman and kayit["durum"] == "Taslak":
                dugmeler += [ft.FilledButton("Düzenle", on_click=lambda _: self._ac(kayit)),
                             ft.FilledButton("Onaya gönder", icon=ft.Icons.SEND, disabled=engelli,
                                             on_click=lambda e, k=kayit: self.app.page.run_task(
                                                 self._gonder, k, e.control))]
            if self.mudur and kayit["durum"] == "Müdür Onayında":
                dugmeler += [ft.FilledButton("Olur", icon=ft.Icons.CHECK,
                                             on_click=lambda _, k=kayit: self._karar_dialog(k, True)),
                             ft.OutlinedButton("İade", on_click=lambda _, k=kayit: self._karar_dialog(k, False))]
            if self.sayman and kayit["durum"] == "Onaylandı" and self.app.yetki("kasa") == "y":
                for kalem in ("SHÇEK", "Merkez payı", "ÜTP"):
                    od = (kayit.get("odemeler") or {}).get(kalem)
                    if not od:
                        dugmeler.append(ft.OutlinedButton(f"{kalem} öde",
                                                          on_click=lambda _, k=kayit, m=kalem: self._ode_dialog(k, m)))
            if self.app.yetki("yil_sonu") == "y" and kayit["durum"] != "İptal":
                dugmeler.append(ft.TextButton("İptal", on_click=lambda _, k=kayit: self._iptal_dialog(k)))
            dugmeler.append(ft.IconButton(ft.Icons.PRINT, tooltip="Belgeler",
                                          on_click=lambda _, k=kayit: self._belgeler(k)))
            c.append(ft.Card(ft.Container(ft.Column([
                ft.Row([ft.Text(f"{kayit.get('belge_no')} · {kayit['durum']}", weight=ft.FontWeight.BOLD,
                                color=renk, expand=True), *dugmeler], wrap=True),
                *self._hesap_ozeti(kayit.get("hesap")),
            ], spacing=8), padding=12)))
        if self.form is not None:
            f = self.form
            kisi_kartlari = []
            for i, s in enumerate(self.kisiler):
                kisi_kartlari.append(ft.Card(ft.Container(ft.Column([
                    ft.Row([s["personel"], s["gorev"], s["unvan"], s["bolum"], s["gv"], s["haric"],
                            ft.IconButton(ft.Icons.DELETE, on_click=lambda _, ix=i: self._kisi_sil(ix))], wrap=True),
                    s["haric_neden"]], spacing=8), padding=8)))
            kaydet = ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, disabled=self.islemde)
            kaydet.on_click = lambda _: self.app.page.run_task(self._kaydet, kaydet)
            c.append(ft.Card(ft.Container(ft.Column([
                ft.Text("Kâr dağıtım cetveli", size=18, weight=ft.FontWeight.BOLD),
                ft.ResponsiveRow([ft.Container(x, col={"xs": 12, "md": 4}) for x in
                                 (f["yil"], f["utp"], f["shcek"], f["dv"], f["tavan"], f["tahsis"], f["odenmis"])]),
                self.yuz_yuze, f["aciklama"],
                ft.Text("Personel dağıtım listesi", weight=ft.FontWeight.BOLD),
                *kisi_kartlari,
                ft.TextButton("Personel ekle", icon=ft.Icons.PERSON_ADD,
                              on_click=lambda _: (self._kisi_satir_ekle(), self._degisti(), self._ciz())),
                ft.Row([kaydet, ft.TextButton("Vazgeç", on_click=self._kapat)]),
            ], spacing=10), padding=16)))
        for ipt in self.veri.get("iptaller") or []:
            c.append(ft.Text(f"İptal: {ipt.get('belge_no')} — {ipt.get('gerekce') or ''}", size=12,
                             color=ft.Colors.ON_SURFACE_VARIANT))
        if not kayit and self.form is None:
            c.append(ft.Text("Bu yıl için cetvel yok. Sayman «Yeni cetvel» ile hazırlar."))
        self.kontrol.controls = c
        self.guncelle()

    def _kisi_sil(self, i: int):
        del self.kisiler[i]
        self._degisti()
        self._ciz()
