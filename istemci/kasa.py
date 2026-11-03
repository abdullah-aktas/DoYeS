"""Invoice-linked cash and bank records; no actual bank transfer is performed."""
from __future__ import annotations

from decimal import Decimal
from typing import TypedDict
from uuid import uuid4

import flet as ft

try:
    from . import takvim, tanimlar as T
    from .ekranlar import Ekran, secim_kutusu, uyari_seridi
    from .finans import hesap_secenekleri, kayit_sonrasi_yenile, para
    from .supa import SupaHata
except ImportError:
    import takvim
    import tanimlar as T
    from ekranlar import Ekran, secim_kutusu, uyari_seridi
    from finans import hesap_secenekleri, kayit_sonrasi_yenile, para
    from supa import SupaHata


class KasaFormu(TypedDict):
    hesap: ft.Dropdown
    tarih: ft.TextField
    tutar: ft.TextField
    fatura: ft.Dropdown | None
    karsi_hesap: ft.Dropdown | None
    belge_no: ft.TextField
    aciklama: ft.TextField


class KasaEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        self.veri: dict = {"hesaplar": [], "hesap_plani": [], "faturalar": [], "hareketler": []}
        self.form: KasaFormu | None = None
        self.tur = ""
        self.istek_id = ""
        self.kirli = False
        self.uzak_uyari = False

    @property
    def yazabilir(self) -> bool:
        return self.app.yetki("kasa") == "y" and (self.app.ben or {}).get("rol") == "Sayman"

    def kaydedilmemis(self) -> bool:
        return self.form is not None and self.kirli

    def _degisti(self, _=None):
        self.kirli = True

    async def yukle(self):
        self.veri = await self.app.supa.rpc("dose_kasa_veri")
        self._ciz()

    async def uzaktan_degisti(self):
        if self.form is not None:
            self.uzak_uyari = True
        await self.yukle()

    def duzen(self):
        self._ciz()

    def _yeni(self, tur: str):
        if self.form is not None or self.islemde or not self.yazabilir:
            return
        self.tur = tur
        fatura = karsi = None
        if tur == "Virman":
            pass  # kaynak hesap seçilir; hedef otomatik diğer nakit hesabı
        elif tur in ("Açılış", "Avans", "Faturasız gelir", "Faturasız gider"):
            etiket = ("Açılış karşı hesabı *" if tur == "Açılış"
                      else "Karşı hesap (avans / gelir-gider) *")
            karsi = secim_kutusu(etiket, hesap_secenekleri(self.veri["hesap_plani"]),
                                 None, on_select=self._degisti)
        else:
            fatura_turu = "Satış" if tur == "Tahsilat" else "Alış"
            faturalar = [(str(f["id"]), f"{f['belge_no']} · {f['cari_unvan']} · kalan {para(f['kalan'])} TL")
                         for f in self.veri["faturalar"]
                         if f["tur"] == fatura_turu and Decimal(f["kalan"]) > 0]
            fatura = secim_kutusu(f"{fatura_turu} faturası *", faturalar, None, on_select=self._degisti)
        self.form = {
            "hesap": secim_kutusu("Kasa / banka hesabı *",
                                   [(h["hesap"], h["hesap"]) for h in self.veri["hesaplar"]],
                                   None, on_select=self._degisti),
            "tarih": ft.TextField(label="İşlem tarihi *", value=takvim.bugun_istanbul().strftime("%d.%m.%Y"),
                                  hint_text="GG.AA.YYYY", on_change=self._degisti),
            "tutar": ft.TextField(label="Tutar (TL) *", keyboard_type=ft.KeyboardType.NUMBER, on_change=self._degisti),
            "fatura": fatura,
            "karsi_hesap": karsi,
            "belge_no": ft.TextField(label="Ödeme / tahsilat belge numarası", on_change=self._degisti),
            "aciklama": ft.TextField(label="Açıklama *", multiline=True, min_lines=2, on_change=self._degisti),
        }
        self.istek_id = str(uuid4())
        self.kirli = False
        self.uzak_uyari = False
        self._ciz()

    def _kapat(self, _=None):
        if self.islemde:
            self.app.bildir("İşlem tamamlanana kadar bekleyin.", hata=True)
        elif self.kaydedilmemis():
            self.app.onayla("Kaydedilmemiş kasa/banka hareketi bırakılacak.", "Değişiklikleri bırak", self._kapat_uygula)
        else:
            self.form = None
            self._ciz()

    async def _kapat_uygula(self):
        self.form = None
        self.kirli = False
        self._ciz()

    async def _kaydet(self, dugme):
        async def is_():
            form = self.form
            if form is None:
                raise ValueError("Önce kasa/banka hareketi açın.")
            if not form["hesap"].value or not (form["aciklama"].value or "").strip():
                raise ValueError("Hesap ve işlem açıklaması zorunludur.")
            if form["fatura"] is not None and not form["fatura"].value:
                raise ValueError("İşlem türüne uygun fatura seçiniz.")
            if form["karsi_hesap"] is not None and not form["karsi_hesap"].value:
                raise ValueError("Karşı hesabı seçiniz.")
            try:
                tarih = T.tarih_coz(form["tarih"].value or "")
            except ValueError as e:
                raise ValueError("Geçerli işlem tarihi giriniz (GG.AA.YYYY).") from e
            try:
                tutar = T.ondalik_coz(form["tutar"].value or "")
            except ValueError as e:
                raise ValueError("Geçerli bir tutar giriniz.") from e
            _, rakamlar, us = tutar.as_tuple()
            fazla = max(-us - 2, 0) if isinstance(us, int) else 0
            if tutar <= 0 or (fazla and any(rakamlar[-fazla:])):
                raise ValueError("Tutar sıfırdan büyük ve en fazla iki ondalık basamaklı olmalıdır.")
            try:
                await self.app.supa.rpc(
                    "dose_kasa_kaydet", p_tur=self.tur, p_hesap=form["hesap"].value,
                    p_tarih=tarih, p_tutar=str(tutar),
                    p_fatura=int(form["fatura"].value) if form["fatura"] is not None and form["fatura"].value else None,
                    p_karsi_hesap=form["karsi_hesap"].value if form["karsi_hesap"] is not None else None,
                    p_belge_no=(form["belge_no"].value or "").strip(),
                    p_aciklama=form["aciklama"].value.strip(), p_istek=self.istek_id)
            except SupaHata as e:
                if e.kod == "ag" or e.durum in (502, 503, 504):
                    raise SupaHata("Bağlantı kesildi; hareket kaydedilmiş olabilir. Listeyi kontrol edin veya "
                                   "aynı formu tekrar gönderin; aynı işlem iki kez kaydedilmez.",
                                   e.durum, e.kod, e.ipucu) from e
                raise
            self.form = None
            self.kirli = False
            self._ciz()
            await kayit_sonrasi_yenile(self, "Kasa/banka hareketi ve yevmiye kaydedildi.")
        await self.guvenli_islem(is_, dugme)

    def _ters_dialog(self, hareket: dict):
        if self.islemde or self.form is not None:
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
                    await self.app.supa.rpc("dose_kasa_tersle", p_hareket=hareket["id"],
                                            p_gerekce=gerekce.value.strip(), p_istek=istek)
                except SupaHata as e:
                    if e.kod == "ag" or e.durum in (502, 503, 504):
                        raise SupaHata("Bağlantı kesildi; ters kayıt oluşmuş olabilir. Listeyi kontrol edin veya "
                                       "aynı işlemi tekrar deneyin.", e.durum, e.kod, e.ipucu) from e
                    raise
                self.app.page.pop_dialog()
                await kayit_sonrasi_yenile(self, "Kasa/banka ters kaydı oluşturuldu.")
            await self.guvenli_islem(is_, tersle, (gerekce, vazgec))

        tersle.on_click = onay
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text("Kasa/banka hareketini tersle"),
            content=ft.Column([ft.Text("Aynı hesaptaki daha yeni açık hareketler önce terslenmelidir."), gerekce],
                              tight=True),
            actions=[vazgec, tersle]))

    def _ciz(self):
        engelli = self.form is not None or self.islemde
        kontroller: list[ft.Control] = [
            ft.Row([ft.Text("Kasa / Banka", size=20, weight=ft.FontWeight.BOLD, expand=True),
                    ft.FilledButton("Açılış bakiyesi", visible=self.yazabilir, disabled=engelli,
                                    on_click=lambda _: self._yeni("Açılış")),
                    ft.FilledButton("Fatura tahsilatı", visible=self.yazabilir, disabled=engelli,
                                    on_click=lambda _: self._yeni("Tahsilat")),
                    ft.FilledButton("Fatura ödemesi", visible=self.yazabilir, disabled=engelli,
                                    on_click=lambda _: self._yeni("Ödeme")),
                    ft.FilledButton("Avans", visible=self.yazabilir, disabled=engelli,
                                    on_click=lambda _: self._yeni("Avans")),
                    ft.FilledButton("Virman (Kasa↔Banka)", visible=self.yazabilir, disabled=engelli,
                                    on_click=lambda _: self._yeni("Virman")),
                    ft.FilledButton("Faturasız gelir", visible=self.yazabilir, disabled=engelli,
                                    on_click=lambda _: self._yeni("Faturasız gelir")),
                    ft.FilledButton("Faturasız gider", visible=self.yazabilir, disabled=engelli,
                                    on_click=lambda _: self._yeni("Faturasız gider")),
                    ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile", disabled=self.islemde,
                                  on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))], wrap=True),
            ft.Text("Bu ekran bankaya gerçek para göndermez; gerçekleşmiş hareketi kaydeder. "
                    "Virman kasa ile banka arasında iç kayıt açar. Bakiye eksiye düşemez."),
            ft.Text("Tahsilatların hazine payına esas KDV hariç hasılatı Muhasebe > Hazine payı ekranında aylık "
                    "hesaplanır.", size=12),
        ]
        for hesap in self.veri["hesaplar"]:
            kontroller.append(ft.ListTile(title=ft.Text(hesap["hesap"]),
                                         subtitle=ft.Text(f"Bakiye: {para(hesap['bakiye'])} TL")))
        if self.form is not None:
            form = self.form
            alanlar: list[ft.Control] = [form["hesap"], form["tarih"], form["tutar"]]
            if form["fatura"] is not None:
                alanlar.append(form["fatura"])
            if form["karsi_hesap"] is not None:
                alanlar.append(form["karsi_hesap"])
            alanlar.extend([form["belge_no"], form["aciklama"]])
            for alan in alanlar:
                alan.disabled = self.islemde
            kaydet = ft.FilledButton("Hareketi kaydet", icon=ft.Icons.SAVE, disabled=self.islemde)
            kaydet.on_click = lambda _: self.app.page.run_task(self._kaydet, kaydet)
            kontroller.append(ft.Card(ft.Container(ft.Column([
                ft.Text(self.tur, size=18, weight=ft.FontWeight.BOLD),
                *([uyari_seridi("Kayıtlar değişti; formunuz korundu. Bakiye ve fatura kalanı kayıtta yeniden denetlenir.")]
                  if self.uzak_uyari else []),
                ft.ResponsiveRow([ft.Container(k, col={"xs": 12, "md": 6}) for k in alanlar]),
                ft.Row([kaydet, ft.TextButton("Vazgeç", disabled=self.islemde, on_click=self._kapat)], wrap=True),
            ], spacing=12), padding=16)))
        kontroller.append(ft.Text("Hareket geçmişi", size=18, weight=ft.FontWeight.BOLD))
        for hareket in self.veri["hareketler"]:
            durum = " · Terslendi" if hareket["terslendi"] else ""
            fatura = f" · Fatura {hareket['fatura_no']}" if hareket["fatura_no"] else ""
            ters = None
            if self.yazabilir and not hareket["terslendi"] and hareket["ters_hareket_id"] is None:
                ters = ft.IconButton(ft.Icons.UNDO, tooltip="Gerekçeli ters kayıt", disabled=engelli,
                                     on_click=lambda _, h=hareket: self._ters_dialog(h))
            kontroller.append(ft.ListTile(
                title=ft.Text(f"{hareket['hesap']} · {hareket['tur']}{durum}"),
                subtitle=ft.Text(f"{T.gosterim('tarih', hareket['tarih'])} · {hareket['yon']} · "
                                 f"{para(hareket['tutar'])} TL{fatura} · {hareket['aciklama']}"),
                trailing=ters))
        if not self.veri["hareketler"]:
            kontroller.append(ft.Text("Kasa/banka hareketi yok."))
        self.kontrol.controls = kontroller
        self.guncelle()
