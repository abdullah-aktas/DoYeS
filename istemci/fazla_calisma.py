"""Overtime (fazla çalışma, Yön. md.9) payroll: day types, hourly sheet, approval chain and bank payment.

The server (dose_fc_kaydet / dose_fc_veri) enforces daily limits, exclusions and the order labour cap and
calculates every amount; this screen only collects input and shows the server's result.
"""
from __future__ import annotations

import calendar
from datetime import date
from uuid import uuid4

import flet as ft

try:
    from . import takvim, tanimlar as T
    from .ekranlar import Ekran, secim_kutusu, uyari_seridi
    from .finans import kayit_sonrasi_yenile, para
    from .parca_basi import DURUM_RENGI, HAZIRLAYAN_ROLLER, _oran, _sayi, binde_yaz, yuzde_yaz
    from .supa import SupaHata
except ImportError:
    import takvim
    import tanimlar as T
    from ekranlar import Ekran, secim_kutusu, uyari_seridi
    from finans import kayit_sonrasi_yenile, para
    from parca_basi import DURUM_RENGI, HAZIRLAYAN_ROLLER, _oran, _sayi, binde_yaz, yuzde_yaz
    from supa import SupaHata

VARSAYILAN = {"saat_ucreti": "67,50", "ogretim": "3", "tatil": "8", "dv": "7,59", "gv": "15"}
GUN_TURLERI = (("O", "Öğretim"), ("T", "Tatil"), ("B", "Bayram"))
GUN_KISA = ("Pt", "Sa", "Ça", "Pe", "Cu", "Ct", "Pz")


def varsayilan_gun_turleri(yil: int, ay: int) -> list[str]:
    """Weekdays are teaching days, weekends holidays; bayram days are marked by the user."""
    return ["T" if date(yil, ay, g).weekday() >= 5 else "O" for g in range(1, calendar.monthrange(yil, ay)[1] + 1)]


class SaatSatiri:
    def __init__(self, personel_id: int, ad: str, gorev: str, gv: str, gunler: list[str], degisti):
        self.personel_id = personel_id
        self.ad = ad
        self.degisti = degisti
        self.gorev = ft.TextField(label="Görevi", value=gorev, dense=True, width=150, on_change=degisti)
        self.gv = ft.TextField(label="GV %", value=gv, dense=True, width=80, keyboard_type=ft.KeyboardType.NUMBER,
                               on_change=degisti)
        self.gunler: list[ft.TextField] = []
        self.boyutla(len(gunler) or 31, gunler)

    def boyutla(self, gun_sayisi: int, degerler: list[str] | None = None):
        eski = degerler if degerler is not None else [g.value or "" for g in self.gunler]
        self.gunler = [ft.TextField(value=(T.siparis_sayisi_yaz(eski[i]) if i < len(eski)
                                           and eski[i] not in ("0", "", None) else ""),
                                    label=str(i + 1), dense=True, width=54, text_size=12,
                                    keyboard_type=ft.KeyboardType.NUMBER, on_change=self.degisti)
                       for i in range(gun_sayisi)]

    def veri(self) -> dict:
        gunler = []
        for i, alan in enumerate(self.gunler, 1):
            deger = _sayi(f"{self.ad} {i}. gün saati", alan.value, "0")
            if deger < 0 or deger > 24:
                raise ValueError(f"{self.ad} {i}. gün saati 0 ile 24 arasında olmalıdır.")
            gunler.append(format(deger, "f"))
        return {"personel_id": self.personel_id, "gorev": (self.gorev.value or "").strip(),
                "gv_orani": _oran(f"{self.ad} gelir vergisi oranı", self.gv.value), "gunler": gunler}


class FazlaCalismaEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        self.veri: dict = {"siparisler": [], "personel": [], "bordrolar": [], "banka_bakiye": None}
        self.form: dict | None = None
        self.gun_turleri: list[ft.Dropdown] = []
        self.kurulu_donem: tuple[int, int] | None = None
        self.pazar = ft.Checkbox()
        self.puantaj: list[SaatSatiri] = []
        self.kayit_id: int | None = None
        self.surum: int | None = None
        self.hesap: dict | None = None
        self.istek_id = ""
        self.kirli = False
        self.uzak_uyari = False

    # ------------------------------------------------------------------ yetki
    @property
    def rol(self) -> str:
        return (self.app.ben or {}).get("rol") or ""

    @property
    def hazirlayabilir(self) -> bool:
        return self.app.yetki("fazla_calisma") == "y" and self.rol in HAZIRLAYAN_ROLLER

    def karar_verebilir(self, b: dict) -> bool:
        return self.app.yetki("fazla_calisma") == "y" and (
            (b["durum"] == "TMY Onayında" and self.rol == "Teknik Müdür Yardımcısı")
            or (b["durum"] == "Müdür Onayında" and self.rol == "Okul Müdürü"))

    def odeyebilir(self, b: dict) -> bool:
        return (b["durum"] == "Onaylandı" and not b.get("odeme") and self.rol == "Sayman"
                and self.app.yetki("fazla_calisma") == "y" and self.app.yetki("kasa") == "y")

    def iptal_edebilir(self, b: dict) -> bool:
        if self.app.yetki("fazla_calisma") != "y":
            return False
        if b["durum"] == "Taslak":
            return self.rol in HAZIRLAYAN_ROLLER
        return b["durum"] == "Onaylandı" and not b.get("odeme") and self.rol == "Okul Müdürü"

    # ------------------------------------------------------------------ yaşam döngüsü
    def kaydedilmemis(self) -> bool:
        return self.form is not None and self.kirli

    def _degisti(self, _=None):
        self.kirli = True

    async def yukle(self):
        self.veri = await self.app.supa.rpc("dose_fc_veri")
        self._ciz()

    async def uzaktan_degisti(self):
        if self.form is not None:
            self.uzak_uyari = True
            self.veri = await self.app.supa.rpc("dose_fc_veri")
            self._ciz()
            return
        await self.yukle()

    def duzen(self):
        self._ciz()

    # ------------------------------------------------------------------ form
    def _ac(self, b: dict | None = None):
        if self.form is not None or self.islemde or not self.hazirlayabilir:
            return
        if not b and not self.veri.get("mevzuat"):
            self.app.bildir("Doğrulanmış merkez parametre yayını yok. Sayman önce Okul parametre "
                            "doğrulamasını tamamlamalıdır.", hata=True)
            return
        bugun = takvim.bugun_istanbul()
        b = b or {}
        siparisler = [(str(s["id"]), f"{s['siparis_no']} · {s['konu']} · {s.get('cari') or ''}")
                      for s in self.veri["siparisler"]]
        if b and str(b["siparis_id"]) not in {k for k, _ in siparisler}:
            siparisler.append((str(b["siparis_id"]), f"{b['siparis_no']} · {b['siparis_konu']}"))

        def alan(etiket, deger="", **ek):
            return ft.TextField(label=etiket, value=deger, on_change=self._degisti, **ek)

        sayi = {"keyboard_type": ft.KeyboardType.NUMBER}
        saat = T.siparis_sayisi_yaz(b["saat_ucreti"]) if b else VARSAYILAN["saat_ucreti"]
        self.form = {
            "siparis": secim_kutusu("Onaylı sipariş *", siparisler, b.get("siparis_id"), disabled=bool(b),
                                    on_select=self._degisti),
            "yil": alan("Yıl *", str(b.get("yil") or bugun.year), width=100, on_blur=self._donem_degisti, **sayi),
            "ay": secim_kutusu("Ay *", [(str(i), f"{i:02d}") for i in range(1, 13)], str(b.get("ay") or bugun.month),
                               bos=False, on_select=self._donem_degisti),
            "saat_ucreti": alan("Saat ücreti (TL) *", saat, **sayi),
            "azami_ucret": alan("(K) cetveli azami saat ücreti *",
                                T.siparis_sayisi_yaz(b["azami_ucret"]) if b else VARSAYILAN["saat_ucreti"], **sayi),
            "ogretim": alan("Öğretim günü azami saat *",
                            T.siparis_sayisi_yaz(b["ogretim_gunu_saat"]) if b else VARSAYILAN["ogretim"], **sayi),
            "tatil": alan("Tatil günü azami saat *",
                          T.siparis_sayisi_yaz(b["tatil_gunu_saat"]) if b else VARSAYILAN["tatil"], **sayi),
            "dv": alan("Damga vergisi (binde) *", binde_yaz(b.get("dv_orani")) or VARSAYILAN["dv"], **sayi),
            "malzeme": alan("Siparişin malzeme maliyeti (TL)", T.siparis_sayisi_yaz(b.get("malzeme_maliyeti") or "0"),
                            **sayi),
            "is_tanimi": alan("Yapılan iş *", b.get("is_tanimi") or ""),
            "aciklama": alan("Açıklama", b.get("aciklama") or "", multiline=True, min_lines=2),
        }
        self.pazar = ft.Checkbox(label="Pazar günü çalışma izni var (md.9/a)", value=bool(b.get("pazar_izinli")),
                                 on_change=self._degisti)
        adlar = {k["personel_id"]: k.get("ad_soyad") for k in (b.get("hesap") or {}).get("kisiler", [])}
        adlar.update({p["id"]: p["ad_soyad"] for p in self.veri["personel"]})
        self.puantaj = [SaatSatiri(k["personel_id"], adlar.get(k["personel_id"]) or f"#{k['personel_id']}",
                                   k.get("gorev") or "", yuzde_yaz(k.get("gv_orani")), k.get("gunler") or [],
                                   self._degisti) for k in b.get("kisiler", [])]
        self.gun_turleri = []
        self.kurulu_donem = None
        self.kayit_id = b.get("id")
        self.surum = b.get("surum")
        self.hesap = b.get("hesap")
        self.istek_id = str(uuid4())
        self.kirli = False
        self.uzak_uyari = False
        self._donem_kur(b.get("gun_turleri"))
        self._ciz()

    def _donem(self) -> tuple[int, int] | None:
        if self.form is None:
            return None
        try:
            yil, ay = int((self.form["yil"].value or "").strip()), int(self.form["ay"].value or "")
        except ValueError:
            return None
        return (yil, ay) if 2000 <= yil <= 2100 and 1 <= ay <= 12 else None

    def _donem_kur(self, turler: list[str] | None = None):
        donem = self._donem()
        if donem is None:
            return
        yil, ay = donem
        varsayilan = varsayilan_gun_turleri(yil, ay)
        if turler is None and self.kurulu_donem == donem:
            turler = [d.value or v for d, v in zip(self.gun_turleri, varsayilan)]
        if not turler or len(turler) != len(varsayilan):
            turler = varsayilan
        self.kurulu_donem = donem
        self.gun_turleri = [ft.Dropdown(
            label=f"{g} {GUN_KISA[date(yil, ay, g).weekday()]}", value=t, dense=True, width=82, text_size=12,
            options=[ft.DropdownOption(key=k, text=k) for k, _ in GUN_TURLERI], on_select=self._degisti)
            for g, t in enumerate(turler, 1)]
        for satir in self.puantaj:
            if len(satir.gunler) != len(turler):
                satir.boyutla(len(turler))

    def _donem_degisti(self, _=None):
        self._degisti()
        self._donem_kur()
        self._ciz()

    def _kisi_ekle(self, secim: ft.Dropdown):
        if not secim.value:
            self.app.bildir("Eklenecek personeli seçiniz.", hata=True)
            return
        kisi_id = int(secim.value)
        if any(s.personel_id == kisi_id for s in self.puantaj):
            self.app.bildir("Bu personel puantajda zaten var.", hata=True)
            return
        kisi = next(p for p in self.veri["personel"] if p["id"] == kisi_id)
        satir = SaatSatiri(kisi_id, kisi["ad_soyad"], kisi.get("kadro_unvani") or "Öğretmen", VARSAYILAN["gv"], [],
                           self._degisti)
        satir.boyutla(len(self.gun_turleri) or 31, [])
        self.puantaj.append(satir)
        self._degisti()
        self._ciz()

    def _kisi_sil(self, i: int):
        del self.puantaj[i]
        self._degisti()
        self._ciz()

    def _kapat(self, _=None):
        if self.islemde:
            self.app.bildir("İşlem tamamlanana kadar bekleyin.", hata=True)
        elif self.kaydedilmemis():
            self.app.onayla("Kaydedilmemiş bordro değişiklikleri bırakılacak.", "Değişiklikleri bırak",
                            self._kapat_uygula)
        else:
            self.form = None
            self._ciz()

    async def _kapat_uygula(self):
        self.form = None
        self.kirli = False
        self._ciz()

    def form_verisi(self) -> tuple[dict, list[dict]]:
        f = self.form
        if f is None:
            raise ValueError("Önce bordro formunu açın.")
        if not f["siparis"].value:
            raise ValueError("Onaylı siparişi seçiniz.")
        donem = self._donem()
        if donem is None:
            raise ValueError("Bordro yılını ve ayını geçerli giriniz.")
        yil, ay = donem
        gun = calendar.monthrange(yil, ay)[1]
        if len(self.gun_turleri) != gun:
            self._donem_kur()
        turler = [d.value or "" for d in self.gun_turleri]
        if any(t not in ("O", "T", "B") for t in turler):
            raise ValueError("Her gün için gün türünü (O/T/B) seçiniz.")
        if not (f["is_tanimi"].value or "").strip():
            raise ValueError("Yapılan işi yazınız.")
        veri = {
            "siparis_id": int(f["siparis"].value), "yil": yil, "ay": ay,
            "saat_ucreti": format(_sayi("Saat ücreti", f["saat_ucreti"].value), "f"),
            "azami_ucret": format(_sayi("Azami saat ücreti", f["azami_ucret"].value), "f"),
            "ogretim_gunu_saat": format(_sayi("Öğretim günü azami saati", f["ogretim"].value), "f"),
            "tatil_gunu_saat": format(_sayi("Tatil günü azami saati", f["tatil"].value), "f"),
            "pazar_izinli": bool(self.pazar.value),
            "dv_orani": _oran("Damga vergisi oranı", f["dv"].value, 1000),
            "malzeme_maliyeti": format(_sayi("Malzeme maliyeti", f["malzeme"].value, "0"), "f"),
            "gun_turleri": turler,
            "is_tanimi": f["is_tanimi"].value.strip(), "aciklama": (f["aciklama"].value or "").strip(),
        }
        if not self.puantaj:
            raise ValueError("Puantaja en az bir personel ekleyiniz.")
        for satir in self.puantaj:
            if len(satir.gunler) != gun:
                satir.boyutla(gun)
        return veri, [s.veri() for s in self.puantaj]

    async def _kaydet(self, dugme):
        async def is_():
            veri, kisiler = self.form_verisi()
            try:
                sonuc = await self.app.supa.rpc("dose_fc_kaydet", p_id=self.kayit_id, p_surum=self.surum, p_veri=veri,
                                                p_kisiler=kisiler, p_istek=self.istek_id)
            except SupaHata as e:
                if e.kod == "ag" or e.durum in (502, 503, 504):
                    raise SupaHata("Bağlantı kesildi; taslak kaydedilmiş olabilir. Listeyi yenileyip kontrol edin; "
                                   "aynı yeni taslak iki kez oluşturulmaz.", e.durum, e.kod, e.ipucu) from e
                raise
            self.kayit_id, self.surum, self.hesap = sonuc["id"], sonuc["surum"], sonuc["hesap"]
            self.istek_id = str(uuid4())
            self.kirli = False
            self.veri = await self.app.supa.rpc("dose_fc_veri")
            self._ciz()
            hatalar = len(self.hesap.get("hatalar") or [])
            self.app.bildir("Taslak kaydedildi ve hesaplandı." if not hatalar else
                            f"Taslak kaydedildi; onaya göndermeden önce {hatalar} kontrolü düzeltin.", hata=bool(hatalar))
        await self.guvenli_islem(is_, dugme)

    # ------------------------------------------------------------------ iş akışı
    async def _gonder(self, b: dict, dugme):
        async def is_():
            sonuc = await self.app.supa.rpc("dose_fc_gonder", p_id=b["id"], p_surum=b["surum"])
            if self.form is not None and self.kayit_id == b["id"]:
                self.form = None
                self.kirli = False
            await kayit_sonrasi_yenile(self, f"Bordro onaya gönderildi: {sonuc['durum']}.")
        await self.guvenli_islem(is_, dugme)

    def _gerekce_dialog(self, baslik: str, etiket: str, zorunlu: bool, dugme_metni: str, islem):
        gerekce = ft.TextField(label=etiket + (" *" if zorunlu else ""), multiline=True, min_lines=2)
        tamam = ft.FilledButton(dugme_metni)
        vazgec = ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog())

        async def onay(_):
            async def is_():
                metin = (gerekce.value or "").strip()
                if zorunlu and not metin:
                    raise ValueError(f"{etiket} zorunludur.")
                await islem(metin)
                self.app.page.pop_dialog()
            await self.guvenli_islem(is_, tamam, (gerekce, vazgec))

        tamam.on_click = onay
        self.app.page.show_dialog(ft.AlertDialog(modal=True, title=ft.Text(baslik),
                                                 content=ft.Column([gerekce], tight=True), actions=[vazgec, tamam]))

    def _karar_dialog(self, b: dict, onay: bool):
        etiket = ("Uygundur notu" if self.rol == "Teknik Müdür Yardımcısı" else "Olur notu") if onay else "İade gerekçesi"

        async def islem(metin):
            sonuc = await self.app.supa.rpc("dose_fc_karar", p_id=b["id"], p_surum=b["surum"], p_onay=onay,
                                            p_aciklama=metin)
            await kayit_sonrasi_yenile(self, f"Bordro durumu: {sonuc['durum']}.")

        baslik = ("Uygundur" if self.rol == "Teknik Müdür Yardımcısı" else "Olur") if onay else "Düzeltmeye iade et"
        self._gerekce_dialog(f"{b['bordro_no']} · {baslik}", etiket, not onay, baslik, islem)

    def _iptal_dialog(self, b: dict):
        async def islem(metin):
            await self.app.supa.rpc("dose_fc_iptal", p_id=b["id"], p_surum=b["surum"], p_gerekce=metin)
            await kayit_sonrasi_yenile(self, "Bordro iptal edildi." + (" Ters yevmiye kaydı oluşturuldu."
                                                                      if b["durum"] == "Onaylandı" else ""))
        self._gerekce_dialog(f"{b['bordro_no']} iptali", "İptal gerekçesi", True, "İptal et", islem)

    def _ode_dialog(self, b: dict):
        tarih = ft.TextField(label="Ödeme (dekont) tarihi *", value=takvim.bugun_istanbul().strftime("%d.%m.%Y"),
                             hint_text="GG.AA.YYYY")
        belge = ft.TextField(label="Dekont / talimat no *")
        ode = ft.FilledButton("Ödemeyi kaydet", icon=ft.Icons.PAYMENTS)
        vazgec = ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog())
        istek = str(uuid4())
        net = (b.get("hesap") or {}).get("toplam", {}).get("net", "0")

        async def onay(_):
            async def is_():
                try:
                    gun = T.tarih_coz(tarih.value or "")
                except ValueError as e:
                    raise ValueError("Geçerli ödeme tarihi giriniz (GG.AA.YYYY).") from e
                if not (belge.value or "").strip():
                    raise ValueError("Dekont veya ödeme talimatı numarası zorunludur.")
                try:
                    await self.app.supa.rpc("dose_fc_ode", p_id=b["id"], p_tarih=gun,
                                            p_belge_no=belge.value.strip(), p_istek=istek)
                except SupaHata as e:
                    if e.kod == "ag" or e.durum in (502, 503, 504):
                        raise SupaHata("Bağlantı kesildi; ödeme kaydedilmiş olabilir. Listeyi kontrol edin veya aynı "
                                       "işlemi tekrar deneyin; iki kez kaydedilmez.", e.durum, e.kod, e.ipucu) from e
                    raise
                self.app.page.pop_dialog()
                await kayit_sonrasi_yenile(self, "Banka ödemesi ve yevmiye (335/102) kaydedildi.")
            await self.guvenli_islem(is_, ode, (tarih, belge, vazgec))

        ode.on_click = onay
        bakiye = self.veri.get("banka_bakiye")
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text(f"{b['bordro_no']} banka ödemesi"),
            content=ft.Column([
                ft.Text(f"Net ödenecek: {para(net)} TL (IBAN'lara toplu ödeme)."),
                ft.Text(f"Banka (102) bakiyesi: {para(bakiye)} TL" if bakiye is not None else ""),
                ft.Text("Bu ekran banka transferi yapmaz; gerçekleşen toplu ödemeyi kaydeder. Fazla çalışma ücreti "
                        "izleyen ayın 10'una kadar ödenir (md.9/b).", size=12),
                tarih, belge], tight=True),
            actions=[vazgec, ode]))

    def _belgeler(self, b: dict):
        try:
            from . import belgeler as B
        except ImportError:
            import belgeler as B
        B.belge_menusu(self.app, self.veri.get("okul") or {}, b, B.FC_BELGELER)

    # ------------------------------------------------------------------ çizim
    def _hesap_ozeti(self, hesap: dict | None) -> list[ft.Control]:
        if not hesap:
            return [ft.Text("Hesap için taslağı kaydedin.", italic=True)]
        toplam = hesap.get("toplam") or {}
        satirlar = [("Toplam saat", T.siparis_sayisi_yaz(toplam.get("saat") or "0"), ""),
                    ("Aylık azami saat (kişi başı)", T.siparis_sayisi_yaz(hesap.get("aylik_sinir") or "0"), ""),
                    ("Brüt ücret", para(toplam.get("brut")), " TL"), ("Net ödenecek", para(toplam.get("net")), " TL")]
        if hesap.get("siparis_iscilik") is not None:
            satirlar += [("Siparişin işçilik payı (md.9/b)", para(hesap["siparis_iscilik"]), " TL"),
                         ("Diğer fazla çalışma bordroları", para(hesap.get("siparis_diger_fc") or "0"), " TL"),
                         ("Kalan işçilik", para(hesap.get("siparis_kalan") or "0"), " TL")]
        kontroller: list[ft.Control] = [
            ft.ResponsiveRow([ft.Container(ft.Column([ft.Text(e, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                                                      ft.Text(f"{d}{b}", weight=ft.FontWeight.BOLD)], spacing=0),
                                           col={"xs": 6, "md": 3}) for e, d, b in satirlar])]
        for hata in hesap.get("hatalar") or []:
            kontroller.append(uyari_seridi(hata))
        for uyari in hesap.get("uyarilar") or []:
            kontroller.append(ft.Container(ft.Row([ft.Icon(ft.Icons.INFO_OUTLINE, color=ft.Colors.AMBER_900),
                                                   ft.Text(uyari, expand=True)]),
                                           bgcolor=ft.Colors.AMBER_50, padding=8, border_radius=8))
        if hesap.get("kisiler"):
            kontroller.append(ft.Row([ft.DataTable(
                columns=[ft.DataColumn(ft.Text(b)) for b in
                         ("Ad soyad", "Saat", "Brüt", "Gelir V.", "Damga V.", "Net")],
                rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(str(v))) for v in (
                    k.get("ad_soyad") or "?", T.siparis_sayisi_yaz(k["saat"]), para(k["brut"]),
                    para(k["gelir_vergisi"]), para(k["damga_vergisi"]), para(k["net"]))])
                      for k in hesap["kisiler"]]
                + [ft.DataRow(cells=[ft.DataCell(ft.Text(v, weight=ft.FontWeight.BOLD)) for v in (
                    "TOPLAM", T.siparis_sayisi_yaz(toplam.get("saat") or "0"), para(toplam.get("brut")),
                    para(toplam.get("gelir_vergisi")), para(toplam.get("damga_vergisi")), para(toplam.get("net")))])])],
                scroll=ft.ScrollMode.AUTO))
        return kontroller

    def _form_karti(self) -> ft.Control:
        f = self.form
        assert f is not None
        kayitli = self.kayit_id is not None
        for k in f.values():
            k.disabled = self.islemde or (kayitli and (k is f["siparis"] or k is f["yil"] or k is f["ay"]))
        self.pazar.disabled = self.islemde
        for d in self.gun_turleri:
            d.disabled = self.islemde
        ust = ft.ResponsiveRow([ft.Container(f[a], col={"xs": 12, "md": 6 if a in ("siparis", "is_tanimi", "aciklama")
                                                         else 3})
                                for a in ("siparis", "yil", "ay", "saat_ucreti", "azami_ucret", "ogretim", "tatil",
                                          "dv", "malzeme", "is_tanimi", "aciklama")])
        personel_sec = secim_kutusu("Personel", [(str(p["id"]), p["ad_soyad"] + ("" if p["iban_var"] else " (IBAN yok)"))
                                                 for p in self.veri["personel"]], None)
        puantaj: list[ft.Control] = []
        for i, s in enumerate(self.puantaj):
            for alan in (s.gorev, s.gv, *s.gunler):
                alan.disabled = self.islemde
            puantaj.append(ft.Column([
                ft.Row([ft.Icon(ft.Icons.PERSON, size=18), ft.Text(s.ad, weight=ft.FontWeight.BOLD, expand=True),
                        s.gorev, s.gv,
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Puantajdan çıkar", disabled=self.islemde,
                                      on_click=lambda _, i=i: self._kisi_sil(i))], wrap=True),
                ft.Row(s.gunler, scroll=ft.ScrollMode.AUTO, spacing=4)], spacing=4))
        kaydet = ft.FilledButton("Kaydet ve hesapla", icon=ft.Icons.CALCULATE, disabled=self.islemde)
        kaydet.on_click = lambda _: self.app.page.run_task(self._kaydet, kaydet)
        gonderilebilir = kayitli and not self.kirli and self.hesap is not None and not self.hesap.get("hatalar")
        gonder = ft.OutlinedButton("Onaya gönder", icon=ft.Icons.SEND, disabled=self.islemde or not gonderilebilir)
        gonder.on_click = lambda _: self.app.page.run_task(
            self._gonder, {"id": self.kayit_id, "surum": self.surum}, gonder)
        return ft.Card(ft.Container(ft.Column([
            ft.Text("Fazla çalışma bordrosu" + (f" · {self._no()}" if kayitli else " · yeni taslak"),
                    size=18, weight=ft.FontWeight.BOLD),
            *([uyari_seridi("Kayıtlar başka bir kullanıcı tarafından değişti; formunuz korundu.")]
              if self.uzak_uyari else []),
            ft.Text("Fazla çalışma; öğretim günlerinde ders saatleri dışında, tatillerde ise günlük sınır içinde "
                    "yapılır. Bayram günleri ve (izin yoksa) Pazar günleri çalışılamaz. Yardımcı hizmetler personeli "
                    "ve şoförler fazla çalışma ücreti alamaz. Sınırlar ve tutarlar sunucuda denetlenir.", size=12),
            ust, self.pazar,
            ft.Text("Gün türleri (O: öğretim, T: tatil, B: bayram)", size=16, weight=ft.FontWeight.BOLD),
            ft.Row(self.gun_turleri, scroll=ft.ScrollMode.AUTO, spacing=4),
            ft.Text("Puantaj (günlük fazla çalışma saati)", size=16, weight=ft.FontWeight.BOLD),
            ft.Row([personel_sec, ft.IconButton(ft.Icons.PERSON_ADD, tooltip="Personel ekle", disabled=self.islemde,
                                                on_click=lambda _: self._kisi_ekle(personel_sec))]),
            *puantaj,
            ft.Row([kaydet, gonder, ft.TextButton("Kapat", disabled=self.islemde, on_click=self._kapat)], wrap=True),
            ft.Divider(),
            ft.Text("Sunucu hesabı (bordro ve md.9 sınırları)", size=16, weight=ft.FontWeight.BOLD),
            *self._hesap_ozeti(self.hesap),
        ], spacing=12), padding=16))

    def _no(self) -> str:
        return next((b["bordro_no"] for b in self.veri["bordrolar"] if b["id"] == self.kayit_id), f"#{self.kayit_id}")

    def _bordro_karti(self, b: dict, engelli: bool) -> ft.Control:
        hesap = b.get("hesap") or {}
        toplam = hesap.get("toplam") or {}
        dugmeler: list[ft.Control] = []
        if b["durum"] == "Taslak" and self.hazirlayabilir:
            dugmeler.append(ft.TextButton("Düzenle", icon=ft.Icons.EDIT, disabled=engelli,
                                          on_click=lambda _: self._ac(b)))
            gonder = ft.TextButton("Onaya gönder", icon=ft.Icons.SEND, disabled=engelli or bool(hesap.get("hatalar")))
            gonder.on_click = lambda _: self.app.page.run_task(self._gonder, b, gonder)
            dugmeler.append(gonder)
        if self.karar_verebilir(b):
            dugmeler += [ft.TextButton("Uygundur" if b["durum"] == "TMY Onayında" else "Olur", icon=ft.Icons.CHECK,
                                       disabled=engelli, on_click=lambda _: self._karar_dialog(b, True)),
                         ft.TextButton("İade et", icon=ft.Icons.UNDO, disabled=engelli,
                                       on_click=lambda _: self._karar_dialog(b, False))]
        if self.odeyebilir(b):
            dugmeler.append(ft.TextButton("Bankadan öde", icon=ft.Icons.PAYMENTS, disabled=engelli,
                                          on_click=lambda _: self._ode_dialog(b)))
        if self.iptal_edebilir(b):
            dugmeler.append(ft.TextButton("İptal", icon=ft.Icons.CANCEL, disabled=engelli,
                                          on_click=lambda _: self._iptal_dialog(b)))
        dugmeler.append(ft.TextButton("Belgeler", icon=ft.Icons.PRINT, disabled=engelli,
                                      on_click=lambda _: self._belgeler(b)))
        odeme = b.get("odeme")
        gecmis = " → ".join(f"{a['islem']} ({a['rol']})" for a in b.get("onaylar") or [])
        return ft.Card(ft.Container(ft.Column([
            ft.Row([ft.Text(f"{b['bordro_no']} · {b['siparis_no']} · {b['siparis_konu']}",
                            weight=ft.FontWeight.BOLD, expand=True),
                    ft.Container(ft.Text(b["durum"], color=ft.Colors.WHITE, size=12),
                                 bgcolor=DURUM_RENGI.get(b["durum"], ft.Colors.GREY), padding=ft.Padding(8, 2, 8, 2),
                                 border_radius=10)], wrap=True),
            ft.Text(f"{int(b['ay']):02d}/{b['yil']} · {b.get('bolum') or ''} · {b['is_tanimi']} · "
                    f"{T.siparis_sayisi_yaz(toplam.get('saat') or '0')} saat · Brüt {para(toplam.get('brut', '0'))} TL"
                    f" · Net {para(toplam.get('net', '0'))} TL"),
            *([ft.Text(f"Ödendi: {T.gosterim('tarih', odeme['tarih'])} · {odeme['belge_no']} · "
                       f"{para(odeme['tutar'])} TL", color=ft.Colors.GREEN_800)] if odeme else []),
            *([ft.Text(f"{len(hesap['hatalar'])} kontrol düzeltilmeli.", color=ft.Colors.RED_700)]
              if b["durum"] == "Taslak" and hesap.get("hatalar") else []),
            *([ft.Text(gecmis, size=12, color=ft.Colors.ON_SURFACE_VARIANT)] if gecmis else []),
            ft.Row(dugmeler, wrap=True),
        ], spacing=6), padding=12))

    def _ciz(self):
        engelli = self.form is not None or self.islemde
        kontroller: list[ft.Control] = [
            ft.Row([ft.Text("Fazla çalışma (Yön. md.9)", size=20, weight=ft.FontWeight.BOLD, expand=True),
                    ft.FilledButton("Yeni bordro", icon=ft.Icons.ADD, visible=self.hazirlayabilir,
                                    disabled=engelli or not self.veri["siparisler"], on_click=lambda _: self._ac()),
                    ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile", disabled=self.islemde,
                                  on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))], wrap=True),
            ft.Text("Akış: Alan Şefi hazırlar → Teknik Müdür Yardımcısı uygundur → Okul Müdürü olur → Sayman bankadan "
                    "öder. Onayda 720/335/360, ödemede 335/102 yevmiyesi otomatik oluşur.", size=12),
        ]
        if not self.veri.get("mevzuat"):
            kontroller.append(uyari_seridi(
                "Doğrulanmış merkez parametre yayını yok. Taslak açılamaz; sayman Okul parametre doğrulamasını tamamlamalıdır."))
        if self.hazirlayabilir and not self.veri["siparisler"]:
            kontroller.append(ft.Text("Bordro için onaylanmış ve parça başı esaslı olmayan sipariş yok.",
                                      color=ft.Colors.ON_SURFACE_VARIANT))
        if self.form is not None:
            kontroller.append(self._form_karti())
        for b in self.veri["bordrolar"]:
            kontroller.append(self._bordro_karti(b, engelli))
        if not self.veri["bordrolar"]:
            kontroller.append(ft.Text("Henüz fazla çalışma bordrosu yok."))
        self.kontrol.controls = kontroller
        self.guncelle()
