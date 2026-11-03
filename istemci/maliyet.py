"""Ürün maliyet kalemleri ve fiyat tespit özeti."""
from __future__ import annotations

from uuid import uuid4

import flet as ft

try:
    from . import tanimlar as T
    from .ekranlar import Ekran, secim_kutusu
    from .finans import kayit_sonrasi_yenile, para
except ImportError:
    import tanimlar as T
    from ekranlar import Ekran, secim_kutusu
    from finans import kayit_sonrasi_yenile, para

KALEM_TURLERI = [
    "Direkt İlk Madde ve Malzeme",
    "Ambalaj / Etiket",
    "Direkt İşçilik (Personel)",
    "Öğrenci Hakkı",
    "Genel Üretim Gideri",
    "Enerji",
    "Nakliye",
    "Diğer",
]


class MaliyetEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        self.urun_id: int | None = None
        self.veri: dict = {"urunler": [], "kalemler": [], "toplam": None, "yazabilir": False}
        self.satirlar: list[dict] = []
        self.kirli = False
        self.istek_id = ""

    def kaydedilmemis(self) -> bool:
        return self.kirli

    def _degisti(self, _=None):
        self.kirli = True

    async def yukle(self):
        self.veri = await self.app.supa.rpc("dose_maliyet_veri", p_urun=self.urun_id)
        self.satirlar = []
        for k in self.veri.get("kalemler") or []:
            self._satir_ekle(k)
        self.kirli = False
        self.istek_id = str(uuid4())
        self._ciz()

    def duzen(self):
        self._ciz()

    def _urun_sec(self, e):
        self.urun_id = int(e.control.value) if e.control.value else None
        self.app.page.run_task(self.app.guvenli, self.yukle)

    def _satir_ekle(self, k: dict | None = None):
        k = k or {}
        tur = k.get("kalem_turu") or KALEM_TURLERI[0]
        self.satirlar.append({
            "kalem_turu": secim_kutusu("Kalem türü *", [(t, t) for t in KALEM_TURLERI], tur,
                                      bos=False, on_select=self._degisti),
            "aciklama": ft.TextField(label="Açıklama", value=k.get("aciklama") or "", on_change=self._degisti),
            "miktar": ft.TextField(label="Miktar *", value=T.siparis_sayisi_yaz(k.get("miktar") or "1"),
                                   keyboard_type=ft.KeyboardType.NUMBER, on_change=self._degisti),
            "birim": ft.TextField(label="Birim", value=k.get("birim") or "Adet", on_change=self._degisti),
            "birim_fiyat": ft.TextField(label="Birim fiyat *", value=T.siparis_sayisi_yaz(k.get("birim_fiyat") or "0"),
                                        keyboard_type=ft.KeyboardType.NUMBER, on_change=self._degisti),
        })

    async def _kaydet(self, dugme):
        async def is_():
            if not self.urun_id:
                raise ValueError("Önce ürün seçiniz.")
            kalemler = []
            for i, s in enumerate(self.satirlar, 1):
                tur = (s["kalem_turu"].value or "").strip()
                if not tur:
                    raise ValueError(f"{i}. satırda kalem türü zorunludur.")
                kalemler.append({
                    "kalem_turu": tur,
                    "aciklama": (s["aciklama"].value or "").strip() or None,
                    "miktar": format(T.ondalik_coz(s["miktar"].value or "0"), "f"),
                    "birim": (s["birim"].value or "Adet").strip(),
                    "birim_fiyat": format(T.ondalik_coz(s["birim_fiyat"].value or "0"), "f"),
                })
            self.veri = await self.app.supa.rpc("dose_maliyet_kaydet", p_urun=self.urun_id, p_kalemler=kalemler,
                                                p_istek=self.istek_id)
            self.kirli = False
            self.istek_id = str(uuid4())
            await kayit_sonrasi_yenile(self, "Maliyet kalemleri kaydedildi.")
            await self.yukle()
        await self.guvenli_islem(is_, dugme)

    def _ciz(self):
        urunler = [(str(u["id"]), u["ad"]) for u in self.veri.get("urunler") or []]
        yaz = bool(self.veri.get("yazabilir"))
        c: list[ft.Control] = [
            ft.Text("Maliyet / fiyat tespit", size=20, weight=ft.FontWeight.BOLD),
            ft.Text("Ürün kartına bağlı maliyet kalemleri. Satış fiyatı ürün tanımındadır; burada maliyet özeti tutulur."),
            secim_kutusu("Ürün *", urunler, self.urun_id, on_select=self._urun_sec),
        ]
        if self.urun_id:
            for i, s in enumerate(self.satirlar):
                c.append(ft.Card(ft.Container(ft.Row([
                    s["kalem_turu"], s["aciklama"], s["miktar"], s["birim"], s["birim_fiyat"],
                    ft.IconButton(ft.Icons.DELETE, visible=yaz,
                                  on_click=lambda _, ix=i: (self.satirlar.pop(ix), self._degisti(), self._ciz()))
                ], wrap=True), padding=8)))
            if yaz:
                kaydet = ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, disabled=self.islemde)
                kaydet.on_click = lambda _: self.app.page.run_task(self._kaydet, kaydet)
                c.append(ft.Row([
                    ft.TextButton("Kalem ekle", icon=ft.Icons.ADD,
                                  on_click=lambda _: (self._satir_ekle(), self._degisti(), self._ciz())),
                    kaydet]))
            if self.veri.get("toplam") is not None:
                c.append(ft.Text(f"Toplam maliyet: {para(self.veri['toplam'])} TL", weight=ft.FontWeight.BOLD))
        self.kontrol.controls = c
        self.guncelle()
