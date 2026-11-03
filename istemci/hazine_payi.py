"""Hazine payı (Tebliğ 73 md.6-7) and monthly tax calendar (KDV 28, muhtasar 26).

The server (dose_hp_veri) computes each month's collected net-sales base, the share, deadlines, delay and the
KDV/withholding balances from the journal; this screen only shows them and calls the sayman-only actions.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from uuid import uuid4

import flet as ft

try:
    from . import takvim, tanimlar as T
    from .belgeler import AYLAR
    from .ekranlar import Ekran, secim_kutusu, uyari_seridi
    from .finans import kayit_sonrasi_yenile, para
    from .supa import SupaHata
except ImportError:
    import takvim
    import tanimlar as T
    from belgeler import AYLAR
    from ekranlar import Ekran, secim_kutusu, uyari_seridi
    from finans import kayit_sonrasi_yenile, para
    from supa import SupaHata

VARSAYILAN_ORAN = Decimal("0.01")
DURUM_RENGI = {
    "Ay devam ediyor": ft.Colors.BLUE_GREY,
    "Hasılat yok": ft.Colors.GREY,
    "Bildirilecek": ft.Colors.ORANGE_700,
    "Ödenecek": ft.Colors.AMBER_800,
    "Gecikmiş": ft.Colors.RED_700,
    "Ödendi": ft.Colors.GREEN_700,
}


def oran_coz(metin: str | None) -> Decimal:
    """'1' or '%1' or '1,5' (percent) -> Decimal fraction; the server accepts (0, 0.10]."""
    temiz = (metin or "").strip().lstrip("%").replace(" ", "").replace(",", ".")
    try:
        deger = Decimal(temiz) / 100
    except InvalidOperation as e:
        raise ValueError("Hazine payı oranını yüzde olarak giriniz (ör. 1).") from e
    if not deger.is_finite() or deger <= 0 or deger > Decimal("0.1"):
        raise ValueError("Hazine payı oranı %0 ile %10 arasında olmalıdır.")
    return deger


def belge_verisi(ay: dict) -> dict:
    """The declaration plus its period and delay, as consumed by belgeler.hp_belge_html."""
    return {**(ay.get("kayit") or {}), "yil": ay["yil"], "ay": ay["ay"], "gecikme_ay": ay.get("gecikme_ay") or 0,
            "gecikme_tutari": ay.get("gecikme_tutari") or "0"}


class HazinePayiEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        self.yil = takvim.bugun_istanbul().year
        self.veri: dict = {"aylar": [], "iptaller": [], "banka_bakiye": None}

    @property
    def rol(self) -> str:
        return (self.app.ben or {}).get("rol") or ""

    @property
    def sayman(self) -> bool:
        return self.rol == "Sayman" and self.app.yetki("hazine_payi") == "y"

    def bildirebilir(self, ay: dict) -> bool:
        return self.sayman and ay["tamamlandi"] and not ay.get("kayit") and Decimal(ay["hasilat"]) > 0

    def odeyebilir(self, ay: dict) -> bool:
        kayit = ay.get("kayit")
        return self.sayman and self.app.yetki("kasa") == "y" and bool(kayit) and not kayit.get("odeme")

    def iptal_edebilir(self, ay: dict) -> bool:
        kayit = ay.get("kayit")
        return self.sayman and bool(kayit) and not kayit.get("odeme")

    async def yukle(self):
        self.veri = await self.app.supa.rpc("dose_hp_veri", p_yil=self.yil)
        self._ciz()

    def duzen(self):
        self._ciz()

    def _yil_degisti(self, e):
        self.yil = int(e.control.value)
        self.app.page.run_task(self.app.guvenli, self.yukle)

    # ------------------------------------------------------------------ işlemler
    def _bildir_dialog(self, ay: dict):
        oran = ft.TextField(label="Oran (%) *", value="1", width=120, keyboard_type=ft.KeyboardType.NUMBER)
        aciklama = ft.TextField(label="Açıklama", multiline=True, min_lines=1)
        tamam = ft.FilledButton("Bildir ve tahakkuk et", icon=ft.Icons.SEND)
        vazgec = ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog())
        istek = str(uuid4())

        async def onay(_):
            async def is_():
                deger = oran_coz(oran.value)
                sonuc = await self.app.supa.rpc("dose_hp_bildir", p_yil=ay["yil"], p_ay=ay["ay"],
                                                p_oran=format(deger, "f"), p_aciklama=(aciklama.value or "").strip(),
                                                p_istek=istek)
                self.app.page.pop_dialog()
                await kayit_sonrasi_yenile(self, f"{sonuc['bildirim_no']} bildirildi: {para(sonuc['tutar'])} TL "
                                                 "(770/362 tahakkuk yevmiyesi oluşturuldu).")
            await self.guvenli_islem(is_, tamam, (oran, aciklama, vazgec))

        tamam.on_click = onay
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text(f"{AYLAR[ay['ay'] - 1]} {ay['yil']} hazine payı bildirimi"),
            content=ft.Column([
                ft.Text(f"Tahsil edilen hasılat (KDV hariç): {para(ay['hasilat'])} TL"),
                ft.Text(f"%1 ile hesaplanan: {para(ay['tahmini_tutar'])} TL · Son ödeme "
                        f"{T.gosterim('tarih', ay['son_odeme'])}"),
                ft.Text("Tebliğ oranı %1'dir; farklı oran yalnız yeni bir düzenleme varsa girilmelidir. Tutar sunucuda "
                        "yeniden hesaplanır.", size=12),
                oran, aciklama], tight=True),
            actions=[vazgec, tamam]))

    def _ode_dialog(self, ay: dict):
        kayit = ay["kayit"]
        tarih = ft.TextField(label="Ödeme (dekont) tarihi *", value=takvim.bugun_istanbul().strftime("%d.%m.%Y"),
                             hint_text="GG.AA.YYYY")
        belge = ft.TextField(label="Dekont / talimat no *")
        ode = ft.FilledButton("Ödemeyi kaydet", icon=ft.Icons.PAYMENTS)
        vazgec = ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog())
        istek = str(uuid4())

        async def onay(_):
            async def is_():
                try:
                    gun = T.tarih_coz(tarih.value or "")
                except ValueError as e:
                    raise ValueError("Geçerli ödeme tarihi giriniz (GG.AA.YYYY).") from e
                if not (belge.value or "").strip():
                    raise ValueError("Dekont veya ödeme talimatı numarası zorunludur.")
                try:
                    sonuc = await self.app.supa.rpc("dose_hp_ode", p_id=kayit["id"], p_tarih=gun,
                                                    p_belge_no=belge.value.strip(), p_istek=istek)
                except SupaHata as e:
                    if e.kod == "ag" or e.durum in (502, 503, 504):
                        raise SupaHata("Bağlantı kesildi; ödeme kaydedilmiş olabilir. Listeyi kontrol edin veya aynı "
                                       "işlemi tekrar deneyin; iki kez kaydedilmez.", e.durum, e.kod, e.ipucu) from e
                    raise
                self.app.page.pop_dialog()
                gecikme = int(sonuc.get("gecikme_ay") or 0)
                await kayit_sonrasi_yenile(self, "Hazine payı ödemesi ve yevmiye (362/102) kaydedildi."
                                           + (f" Ödeme {gecikme} ay gecikmeli; gecikme zammını ayrıca hesaplayın."
                                              if gecikme else ""))
            await self.guvenli_islem(is_, ode, (tarih, belge, vazgec))

        ode.on_click = onay
        bakiye = self.veri.get("banka_bakiye")
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text(f"{kayit['bildirim_no']} banka ödemesi"),
            content=ft.Column([
                ft.Text(f"Ödenecek hazine payı: {para(kayit['tutar'])} TL · Son ödeme "
                        f"{T.gosterim('tarih', kayit['son_odeme'])}"),
                ft.Text(f"Banka (102) bakiyesi: {para(bakiye)} TL" if bakiye is not None else ""),
                ft.Text("Bu ekran banka transferi yapmaz; muhasebe birimi hesabına yapılan ödemeyi kaydeder.", size=12),
                tarih, belge], tight=True),
            actions=[vazgec, ode]))

    def _iptal_dialog(self, ay: dict):
        kayit = ay["kayit"]
        gerekce = ft.TextField(label="İptal gerekçesi *", multiline=True, min_lines=2)
        tamam = ft.FilledButton("İptal et")
        vazgec = ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog())

        async def onay(_):
            async def is_():
                metin = (gerekce.value or "").strip()
                if not metin:
                    raise ValueError("İptal gerekçesi zorunludur.")
                await self.app.supa.rpc("dose_hp_iptal", p_id=kayit["id"], p_surum=kayit["surum"], p_gerekce=metin)
                self.app.page.pop_dialog()
                await kayit_sonrasi_yenile(self, "Bildirim iptal edildi; ters yevmiye kaydı oluşturuldu.")
            await self.guvenli_islem(is_, tamam, (gerekce, vazgec))

        tamam.on_click = onay
        self.app.page.show_dialog(ft.AlertDialog(modal=True, title=ft.Text(f"{kayit['bildirim_no']} iptali"),
                                                 content=ft.Column([gerekce], tight=True), actions=[vazgec, tamam]))

    def _belgeler(self, ay: dict):
        try:
            from . import belgeler as B
        except ImportError:
            import belgeler as B
        B.belge_menusu(self.app, self.veri.get("okul") or {}, belge_verisi(ay), B.HP_BELGELER)

    # ------------------------------------------------------------------ çizim
    def _ay_karti(self, ay: dict) -> ft.Control:
        kayit = ay.get("kayit")
        odeme = (kayit or {}).get("odeme")
        dugmeler: list[ft.Control] = []
        if self.bildirebilir(ay):
            dugmeler.append(ft.TextButton("Bildir", icon=ft.Icons.SEND, disabled=self.islemde,
                                          on_click=lambda _: self._bildir_dialog(ay)))
        if self.odeyebilir(ay):
            dugmeler.append(ft.TextButton("Bankadan öde", icon=ft.Icons.PAYMENTS, disabled=self.islemde,
                                          on_click=lambda _: self._ode_dialog(ay)))
        if self.iptal_edebilir(ay):
            dugmeler.append(ft.TextButton("İptal", icon=ft.Icons.CANCEL, disabled=self.islemde,
                                          on_click=lambda _: self._iptal_dialog(ay)))
        if kayit:
            dugmeler.append(ft.TextButton("Belgeler", icon=ft.Icons.PRINT, disabled=self.islemde,
                                          on_click=lambda _: self._belgeler(ay)))
        kdv, muhtasar = ay["kdv"], ay["muhtasar"]
        satirlar: list[ft.Control] = [
            ft.Row([ft.Text(f"{AYLAR[ay['ay'] - 1]} {ay['yil']}", weight=ft.FontWeight.BOLD, expand=True),
                    ft.Container(ft.Text(ay["durum"], color=ft.Colors.WHITE, size=12),
                                 bgcolor=DURUM_RENGI.get(ay["durum"], ft.Colors.GREY),
                                 padding=ft.Padding(8, 2, 8, 2), border_radius=10)], wrap=True),
            ft.Text(f"Tahsil edilen hasılat {para(ay['hasilat'])} TL · Hazine payı "
                    f"{para(kayit['tutar'] if kayit else ay['tahmini_tutar'])} TL · Son ödeme "
                    f"{T.gosterim('tarih', ay['son_odeme'])}"),
        ]
        if kayit:
            satirlar.append(ft.Text(f"{kayit['bildirim_no']} · bildirim {T.gosterim('tarih', kayit['bildirim_tarihi'])}"
                                    f" · oran %{T.siparis_yuzdesi_yaz(kayit['oran'])}", size=12))
            if Decimal(kayit.get("hasilat_farki") or "0") != 0:
                satirlar.append(ft.Text(f"Bildirimden sonra bu ayın tahsilatı {para(kayit['hasilat_farki'])} TL "
                                        "değişti; gerekirse iptal edip yeniden bildirin.", color=ft.Colors.RED_700))
        if odeme:
            satirlar.append(ft.Text(f"Ödendi: {T.gosterim('tarih', odeme['tarih'])} · {odeme.get('belge_no') or ''} · "
                                    f"{para(odeme['tutar'])} TL", color=ft.Colors.GREEN_800))
        if int(ay.get("gecikme_ay") or 0) > 0 and ay["durum"] != "Hasılat yok":
            satirlar.append(ft.Text(f"{ay['gecikme_ay']} ay gecikme · %1 aylık zam yaklaşık "
                                    f"{para(ay['gecikme_tutari'])} TL (yarısı müdürden, yarısı saymandan).",
                                    color=ft.Colors.RED_700))
        satirlar.append(ft.Text(
            f"KDV: hesaplanan {para(kdv['hesaplanan'])} · indirilecek {para(kdv['indirilecek'])} · ödenecek "
            f"{para(kdv['odenecek'])} · devreden {para(kdv['devreden'])} TL (son gün "
            f"{T.gosterim('tarih', kdv['son_gun'])}) · Muhtasar kesinti {para(muhtasar['kesinti'])} TL (son gün "
            f"{T.gosterim('tarih', muhtasar['son_gun'])})", size=12, color=ft.Colors.ON_SURFACE_VARIANT))
        if dugmeler:
            satirlar.append(ft.Row(dugmeler, wrap=True))
        return ft.Card(ft.Container(ft.Column(satirlar, spacing=6), padding=12))

    def _ciz(self):
        bugun = takvim.bugun_istanbul()
        yillar = [(str(y), str(y)) for y in range(bugun.year, bugun.year - 6, -1)]
        try:
            from .tema import sayfa_baslik_satiri
        except ImportError:
            from tema import sayfa_baslik_satiri
        kontroller: list[ft.Control] = [
            sayfa_baslik_satiri("Hazine payı ve vergi takvimi", [
                secim_kutusu("Yıl", yillar, self.yil, bos=False, disabled=self.islemde,
                             on_select=self._yil_degisti),
                ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile", disabled=self.islemde,
                              on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))],
                              ft.Icons.PERCENT),
            ft.Text("Her ay, satış faturalarından fiilen tahsil edilen tutarın KDV hariç kısmı üzerinden %1 hazine payı "
                    "izleyen ayın 20'sine kadar Örnek No:30 ile bildirilir ve ödenir. Bildirimde 770/362, ödemede "
                    "362/102 yevmiyesi otomatik oluşur.", size=12),
        ]
        gecikmis = [a for a in self.veri["aylar"] if a["durum"] == "Gecikmiş"]
        if gecikmis:
            kontroller.append(uyari_seridi(
                "Süresi geçen hazine payı: " + ", ".join(f"{AYLAR[a['ay'] - 1]} {a['yil']}" for a in gecikmis)
                + ". Gecikilen her ay için %1 zam uygulanır."))
        if not self.sayman:
            kontroller.append(ft.Text("Bildirim ve ödeme işlemlerini yalnız sayman yapar; bu ekranı izleyebilirsiniz.",
                                      color=ft.Colors.ON_SURFACE_VARIANT))
        for ay in reversed(self.veri["aylar"]):
            kontroller.append(self._ay_karti(ay))
        if not self.veri["aylar"]:
            kontroller.append(ft.Text("Bu yıl için gösterilecek ay yok."))
        for i in self.veri.get("iptaller") or []:
            kontroller.append(ft.Text(f"İptal: {i['bildirim_no']} ({AYLAR[i['ay'] - 1]}) · {para(i['tutar'])} TL · "
                                      f"{i.get('gerekce') or ''}", size=12, color=ft.Colors.ON_SURFACE_VARIANT))
        self.kontrol.controls = kontroller
        self.guncelle()
