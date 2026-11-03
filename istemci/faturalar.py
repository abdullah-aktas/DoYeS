"""Invoice record screens. These records do not submit e-invoices to GİB."""
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
    from .tema import sayfa_baslik_satiri
except ImportError:
    import takvim
    import tanimlar as T
    from ekranlar import Ekran, secim_kutusu, uyari_seridi
    from finans import hesap_secenekleri, kayit_sonrasi_yenile, para
    from supa import SupaHata
    from tema import sayfa_baslik_satiri


class SatisSatiri(TypedDict):
    kaynak: dict
    miktar: ft.TextField
    maliyet: ft.TextField | None
    maliyet_hesabi: ft.Dropdown | None
    eski_baglanti_onayi: ft.Checkbox | None


class AlisSatiri(TypedDict):
    malzeme: ft.Dropdown
    hesap: ft.Dropdown
    aciklama: ft.TextField
    miktar: ft.TextField
    fiyat: ft.TextField
    kdv: ft.TextField
    iskonto: ft.TextField


def sayi(metin: str | None, etiket: str) -> Decimal:
    if not (metin or "").strip():
        raise ValueError(f"{etiket} zorunludur.")
    try:
        return T.ondalik_coz(metin or "")
    except ValueError as e:
        raise ValueError(f"{etiket} geçerli bir sayı olmalıdır.") from e


def oran(metin: str | None, etiket: str) -> str:
    deger = sayi(metin, etiket)
    if deger < 0 or deger > 100:
        raise ValueError(f"{etiket} %0 ile %100 arasında olmalıdır.")
    return str(T.siparis_yuzdesi_orana(deger))


class FaturaEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        self.veri: dict = {"cariler": [], "stoklar": [], "hesaplar": [], "vergi_hesaplari": [], "siparisler": []}
        self.faturalar: list[dict] = []
        self.ust: dict[str, ft.TextField | ft.Dropdown] | None = None
        self.tur = ""
        self.siparis: dict | None = None
        self.satis_satirlari: list[SatisSatiri] = []
        self.alis_satirlari: list[AlisSatiri] = []
        self.alim_isaretleri: dict[str, ft.Checkbox] = {}
        self.satir_sayaci = 0
        self.kirli = False
        self.uzak_uyari = False
        self.girdi_surumu = 0
        self.onizleme: dict | None = None
        self.hazir: dict | None = None
        self.istek_id = ""
        self.islemde = False

    @property
    def yazabilir(self) -> bool:
        return self.app.yetki("fatura") == "y" and (self.app.ben or {}).get("rol") == "Sayman"

    def kaydedilmemis(self) -> bool:
        return self.ust is not None and self.kirli

    def _degisti(self, _=None):
        onizleme_vardi = self.onizleme is not None
        self.kirli = True
        self.girdi_surumu += 1
        self.onizleme = None
        self.hazir = None
        if onizleme_vardi:
            self._ciz()

    async def yukle(self):
        self.veri = await self.app.supa.rpc("dose_fatura_secimleri")
        self.faturalar = await self.app.supa.rpc("dose_faturalar")
        self._ciz()

    async def uzaktan_degisti(self):
        if self.ust is not None:
            self.uzak_uyari = True
            self.onizleme = None
            self.hazir = None
            self.girdi_surumu += 1
        await self.yukle()

    def duzen(self):
        self._ciz()

    def _yeni(self, tur: str):
        if self.ust is not None or not self.yazabilir:
            return
        self.tur = tur
        self.siparis = None
        self.satis_satirlari = []
        self.alis_satirlari = []
        self.satir_sayaci = 0
        self.ust = {
            "belge_no": ft.TextField(label="Belge numarası *", on_change=self._degisti),
            "tarih": ft.TextField(label="Belge tarihi *", value=takvim.bugun_istanbul().strftime("%d.%m.%Y"),
                                  hint_text="GG.AA.YYYY", on_change=self._degisti),
            "tevkifat": ft.TextField(label="KDV tevkifatı (%) *", hint_text="Yoksa 0", on_change=self._degisti),
            "stopaj": ft.TextField(label="Stopaj (%) *", hint_text="Yoksa 0", on_change=self._degisti),
        }
        if tur == "Satış":
            siparisler = [(str(s["id"]), f"{s['siparis_no']} · {s['konu']}") for s in self.veri["siparisler"]
                          if any(Decimal(k["kalan"]) > 0 for k in s["kalemler"])]
            self.ust["siparis"] = secim_kutusu("Onaylı sipariş *", siparisler, None,
                                               on_select=lambda e: self._siparis_degisti(e.control.value))
        else:
            cariler = [(str(c["id"]), c["unvan"]) for c in self.veri["cariler"]
                       if c["tur"] in ("Tedarikçi", "Müşteri ve Tedarikçi")]
            teminler = [(t["deger"], t["etiket"]) for t in self.veri.get("temin_usulleri") or []]
            giderler = [(t["deger"], t["etiket"]) for t in self.veri.get("gider_turleri") or []]
            belgeler = [(t["deger"], t["etiket"]) for t in self.veri.get("alis_belge_turleri") or []]
            self.ust["cari"] = secim_kutusu("Tedarikçi *", cariler, None, on_select=self._degisti)
            self.ust["temin_usulu"] = secim_kutusu("Temin usulü *", teminler, "Doğrudan Temin",
                                                   bos=False, on_select=self._temin_degisti)
            self.ust["gider_turu"] = secim_kutusu("Gider / alım türü *", giderler,
                                                  "İlk Madde ve Malzeme (Stoğa)", bos=False, on_select=self._degisti)
            self.ust["belge_turu"] = secim_kutusu("Alış belge türü *", belgeler, "e-Fatura",
                                                  bos=False, on_select=self._degisti)
            self.alim_isaretleri: dict[str, ft.Checkbox] = {}
            self._temin_degisti()
            self._alis_satiri_ekle()
        self.kirli = False
        self.uzak_uyari = False
        self.girdi_surumu += 1
        self.onizleme = None
        self.hazir = None
        self.istek_id = str(uuid4())
        self._ciz()

    def _temin_degisti(self, _=None):
        if self.ust is None or "temin_usulu" not in self.ust:
            return
        temin = self.ust["temin_usulu"].value or "Doğrudan Temin"
        liste = (self.veri.get("alim_belgeler") or {}).get(temin) or []
        onceki = {k: bool(c.value) for k, c in getattr(self, "alim_isaretleri", {}).items()}
        self.alim_isaretleri = {
            b["anahtar"]: ft.Checkbox(
                label=(b["etiket"] + (" *" if b.get("zorunlu") else "")),
                value=onceki.get(b["anahtar"], False),
                on_change=self._degisti)
            for b in liste
        }
        self._degisti()
        self._ciz()

    def _siparis_degisti(self, kimlik: str | None):
        eski = str(self.siparis["id"]) if self.siparis else ""
        yeni = kimlik or ""
        if eski == yeni:
            return
        if self.satis_satirlari and any((s["miktar"].value or "").strip() for s in self.satis_satirlari):
            if self.ust is not None:
                self.ust["siparis"].value = eski

            async def uygula():
                self._siparis_uygula(yeni)

            self.app.onayla("Seçilen siparişin girilmiş fatura miktarları bırakılacak.", "Siparişi değiştir", uygula)
            return
        self._siparis_uygula(yeni)

    def _siparis_uygula(self, kimlik: str):
        self.siparis = next((s for s in self.veri["siparisler"] if str(s["id"]) == kimlik), None)
        if self.ust is None:
            return
        self.ust["siparis"].value = kimlik
        self.satis_satirlari = []
        if self.siparis:
            for k in self.siparis["kalemler"]:
                if Decimal(k["kalan"]) <= 0:
                    continue
                maliyet = hesap = None
                if k["malzeme_id"] is not None:
                    maliyet = ft.TextField(label=f"{k['aciklama']} toplam stok maliyeti (TL) *",
                                            hint_text="0 ise 0 girin", on_change=self._degisti)
                    hesap = secim_kutusu(f"{k['aciklama']} maliyet hesabı *",
                                         hesap_secenekleri(self.veri["hesaplar"]), None, on_select=self._degisti)
                eski_onay = None
                if k["stok_baglanti_kaynagi"] is None:
                    eski_onay = ft.Checkbox(
                        label="Eski siparişin onay anındaki stok bağlantısı bilinmiyor; yukarıdaki güncel bağlantıyla "
                              "faturalamayı onaylıyorum.",
                        value=False, on_change=self._degisti)
                self.satis_satirlari.append({
                    "kaynak": k, "miktar": ft.TextField(label=f"{k['aciklama']} fatura miktarı",
                                                         hint_text=f"En fazla {T.siparis_sayisi_yaz(k['kalan'])}",
                                                         on_change=self._degisti),
                    "maliyet": maliyet, "maliyet_hesabi": hesap,
                    "eski_baglanti_onayi": eski_onay,
                })
        self._degisti()
        self._ciz()

    def _alis_satiri_ekle(self, _=None):
        self.satir_sayaci += 1
        n = self.satir_sayaci
        stoklar = [(str(k["id"]), f"{k['ad']} · {k['tur']}") for k in self.veri["stoklar"]]
        hesap = secim_kutusu(f"{n}. kalem gider / varlık hesabı", hesap_secenekleri(self.veri["hesaplar"]),
                             None, on_select=self._degisti)

        def stok_sec(e):
            hesap.value = ""
            hesap.disabled = bool(e.control.value) or self.islemde
            self._degisti()
            self.guncelle()

        self.alis_satirlari.append({
            "malzeme": secim_kutusu(f"{n}. kalem stok kartı (stoksuzsa boş)", stoklar, None, on_select=stok_sec),
            "hesap": hesap,
            "aciklama": ft.TextField(label=f"{n}. kalem açıklaması *", on_change=self._degisti),
            "miktar": ft.TextField(label=f"{n}. kalem miktarı *", on_change=self._degisti),
            "fiyat": ft.TextField(label=f"{n}. kalem birim fiyatı *", on_change=self._degisti),
            "kdv": ft.TextField(label=f"{n}. kalem KDV (%) *", hint_text="Yoksa 0", on_change=self._degisti),
            "iskonto": ft.TextField(label=f"{n}. kalem indirim (%) *", hint_text="Yoksa 0", on_change=self._degisti),
        })
        if self.ust is not None and self.tur == "Alış" and len(self.alis_satirlari) > 1:
            self._degisti()
            self._ciz()

    def _alis_satiri_sil(self, satir: AlisSatiri):
        self.alis_satirlari.remove(satir)
        self._degisti()
        self._ciz()

    def _kapat(self, _=None):
        if self.islemde:
            self.app.bildir("İşlem tamamlanana kadar bekleyin.", hata=True)
        elif self.kaydedilmemis():
            self.app.onayla("Kaydedilmemiş fatura alanları bırakılacak.", "Değişiklikleri bırak", self._kapat_uygula)
        else:
            self.ust = None
            self._ciz()

    async def _kapat_uygula(self):
        self.ust = None
        self.kirli = False
        self.onizleme = None
        self.hazir = None
        self._ciz()

    def _form_verisi(self) -> dict:
        if self.ust is None:
            raise ValueError("Önce bir fatura kaydı açın.")
        ust = self.ust
        belge_no = (ust["belge_no"].value or "").strip()
        if not belge_no:
            raise ValueError("Belge numarası zorunludur.")
        try:
            tarih = T.tarih_coz(ust["tarih"].value or "")
        except ValueError as e:
            raise ValueError("Geçerli belge tarihi giriniz (GG.AA.YYYY).") from e
        tevkifat = oran(ust["tevkifat"].value, "KDV tevkifatı")
        stopaj = oran(ust["stopaj"].value, "Stopaj")
        surumler = {v["tur"]: v["surum"] for v in self.veri["vergi_hesaplari"]}
        kalemler = []
        if self.tur == "Satış":
            if self.siparis is None:
                raise ValueError("Onaylı sipariş seçiniz.")
            cari = self.siparis["cari_id"]
            siparis = self.siparis["id"]
            for s in self.satis_satirlari:
                if not (s["miktar"].value or "").strip():
                    continue
                k = s["kaynak"]
                kalem = {"siparis_kalem_id": k["id"], "miktar": str(sayi(s["miktar"].value, "Fatura miktarı")),
                         "malzeme_id": k["malzeme_id"]}
                if s["eski_baglanti_onayi"] is not None:
                    if not s["eski_baglanti_onayi"].value:
                        raise ValueError("Eski siparişin güncel stok bağlantısını faturalama için doğrulayın.")
                    kalem["eski_baglanti_onayi"] = True
                if s["maliyet"] is not None and s["maliyet_hesabi"] is not None:
                    if not s["maliyet_hesabi"].value:
                        raise ValueError("Stok çıkışının maliyet hesabını seçiniz.")
                    kalem["stok_maliyeti"] = str(sayi(s["maliyet"].value, "Stok maliyeti"))
                    kalem["stok_maliyet_hesabi"] = s["maliyet_hesabi"].value
                kalemler.append(kalem)
        else:
            if not ust["cari"].value:
                raise ValueError("Tedarikçi seçiniz.")
            cari, siparis = int(ust["cari"].value), None
            for s in self.alis_satirlari:
                aciklama = (s["aciklama"].value or "").strip()
                if not aciklama:
                    raise ValueError("Her alış kaleminin açıklaması zorunludur.")
                malzeme = int(s["malzeme"].value) if s["malzeme"].value else None
                if malzeme is None and not s["hesap"].value:
                    raise ValueError("Stoksuz alış kalemi için gider veya varlık hesabı seçiniz.")
                kalemler.append({
                    "aciklama": aciklama, "malzeme_id": malzeme,
                    "hesap_kodu": None if malzeme is not None else s["hesap"].value,
                    "miktar": str(sayi(s["miktar"].value, "Miktar")),
                    "birim_fiyat": str(sayi(s["fiyat"].value, "Birim fiyat")),
                    "kdv_orani": oran(s["kdv"].value, "KDV oranı"),
                    "iskonto_orani": oran(s["iskonto"].value, "İndirim oranı"),
                })
        if not kalemler:
            raise ValueError("En az bir fatura kalemi giriniz.")
        veri = {"p_tur": self.tur, "p_belge_no": belge_no, "p_tarih": tarih, "p_cari": cari,
                "p_siparis": siparis, "p_kalemler": kalemler, "p_tevkifat": tevkifat, "p_stopaj": stopaj,
                "p_vergi_surumleri": surumler}
        if self.tur == "Alış":
            if not ust["temin_usulu"].value or not ust["gider_turu"].value or not ust["belge_turu"].value:
                raise ValueError("Temin usulü, gider türü ve alış belge türü zorunludur.")
            veri["alim"] = {
                "temin_usulu": ust["temin_usulu"].value,
                "gider_turu": ust["gider_turu"].value,
                "belge_turu": ust["belge_turu"].value,
                "belgeler": {k: bool(c.value) for k, c in self.alim_isaretleri.items()},
            }
        return veri

    async def _onizle(self, dugme):
        async def is_():
            veri = self._form_verisi()
            surum = self.girdi_surumu
            fatura_veri = {k: v for k, v in veri.items() if k != "alim"}
            sonuc = await self.app.supa.rpc("dose_fatura_onizle", **fatura_veri)
            if self.ust is None or self.girdi_surumu != surum:
                raise ValueError("Fatura alanları değişti; yeniden önizleyin.")
            if self.tur == "Alış":
                sonuc["alim"] = await self.app.supa.rpc(
                    "dose_alim_onizle", p_alim=veri["alim"],
                    p_matrah=sonuc["detay"].get("matrah"))
            self.onizleme = sonuc
            self.hazir = veri
            self._ciz()
        await self.app.guvenli(is_, dugme)

    async def _kaydet(self, dugme):
        async def is_():
            if self.hazir is None or self.onizleme is None:
                raise ValueError("Önce güncel faturayı önizleyin.")
            if self._form_verisi() != self.hazir:
                self._degisti()
                raise ValueError("Fatura alanları değişti; yeniden önizleyin.")
            fatura_veri = {k: v for k, v in self.hazir.items() if k != "alim"}
            try:
                if self.tur == "Alış":
                    await self.app.supa.rpc(
                        "dose_alim_hazirla", p_istek=self.istek_id, p_alim=self.hazir["alim"],
                        p_matrah=self.onizleme["detay"].get("matrah"))
                await self.app.supa.rpc("dose_fatura_kaydet", **fatura_veri,
                                        p_imza=self.onizleme["imza"], p_istek=self.istek_id)
            except SupaHata as e:
                if e.kod == "ag" or e.durum in (502, 503, 504):
                    raise SupaHata("Bağlantı kesildi; fatura kaydedilmiş olabilir. Listeyi kontrol edin veya "
                                   "aynı önizlemeyi tekrar gönderin; aynı işlem iki kez kaydedilmez.",
                                   e.durum, e.kod, e.ipucu) from e
                raise
            self.ust = None
            self.kirli = False
            self.onizleme = None
            self.hazir = None
            self._ciz()
            await kayit_sonrasi_yenile(self, "Fatura kaydı ve yevmiye kaydedildi.")
        await self.guvenli_islem(is_, dugme)

    async def _alim_html(self, fatura: dict):
        async def is_():
            try:
                from .belgeler import alim_ozet_html, belge_klasoru
            except ImportError:
                from belgeler import alim_ozet_html, belge_klasoru
            okul = (self.app.ben or {}).get("okul") or {}
            html = alim_ozet_html(okul, fatura, self.veri.get("alim_belgeler") or {})
            yol = belge_klasoru() / f"DOSE_alim_{fatura.get('belge_no') or fatura['id']}.html"
            yol.write_text(html, encoding="utf-8")
            if hasattr(self.app.page, "launch_url"):
                self.app.page.launch_url(yol.as_uri())
            self.app.bildir(f"Alım özeti kaydedildi: {yol.name}")
        await self.app.guvenli(is_)

    def _ters_dialog(self, fatura: dict):
        if self.islemde:
            return
        gerekce = ft.TextField(label="Fatura ters kayıt gerekçesi *", multiline=True, min_lines=2)
        tersle = ft.FilledButton("Faturayı tersle")
        vazgec = ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog())
        istek = str(uuid4())

        async def onay(_):
            async def is_():
                if not (gerekce.value or "").strip():
                    raise ValueError("Ters kayıt gerekçesi zorunludur.")
                try:
                    await self.app.supa.rpc("dose_fatura_tersle", p_fatura=fatura["id"],
                                            p_gerekce=gerekce.value.strip(), p_istek=istek)
                except SupaHata as e:
                    if e.kod == "ag" or e.durum in (502, 503, 504):
                        raise SupaHata("Bağlantı kesildi; ters kayıt oluşmuş olabilir. Listeyi kontrol edin veya "
                                       "aynı işlemi tekrar deneyin.", e.durum, e.kod, e.ipucu) from e
                    raise
                self.app.page.pop_dialog()
                await kayit_sonrasi_yenile(self, "Faturanın gerekçeli ters kaydı oluşturuldu.")
            await self.guvenli_islem(is_, tersle, (gerekce, vazgec))

        tersle.on_click = onay
        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text("Faturayı tersle"),
            content=ft.Column([ft.Text("Bu işlem yalnız DÖSE kaydını tersler; GİB'de e-Fatura iptali yapmaz. "
                                       "Daha yeni bağlı faturalar veya stok hareketleri önce terslenmelidir."),
                               gerekce], tight=True),
            actions=[vazgec, tersle]))

    def _ciz(self):
        kontroller: list[ft.Control] = [
            sayfa_baslik_satiri("Fatura kayıtları", [
                ft.FilledButton("Yeni satış", icon=ft.Icons.ADD, visible=self.yazabilir, disabled=self.ust is not None,
                                on_click=lambda _: self._yeni("Satış")),
                ft.FilledButton("Yeni alış", icon=ft.Icons.ADD, visible=self.yazabilir, disabled=self.ust is not None,
                                on_click=lambda _: self._yeni("Alış")),
                ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile", disabled=self.islemde,
                              on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))],
                              ft.Icons.RECEIPT_LONG),
            ft.Text("Buradaki kayıt GİB'e e-Fatura göndermez. Vergi oranlarını ve hesaplarını sayman doğrular."),
        ]
        if self.ust is not None:
            form: list[ft.Control] = [ft.Text(f"Yeni {self.tur.lower()} faturası", size=18, weight=ft.FontWeight.BOLD)]
            for kontrol in self.ust.values():
                kontrol.disabled = self.islemde
            for s in self.satis_satirlari:
                s["miktar"].disabled = self.islemde
                if s["maliyet"] is not None:
                    s["maliyet"].disabled = self.islemde
                if s["maliyet_hesabi"] is not None:
                    s["maliyet_hesabi"].disabled = self.islemde
                if s["eski_baglanti_onayi"] is not None:
                    s["eski_baglanti_onayi"].disabled = self.islemde
            for s in self.alis_satirlari:
                for kontrol in (s["malzeme"], s["aciklama"], s["miktar"], s["fiyat"], s["kdv"], s["iskonto"]):
                    kontrol.disabled = self.islemde
                s["hesap"].disabled = self.islemde or bool(s["malzeme"].value)
            if self.uzak_uyari:
                form.append(uyari_seridi("Kayıtlar değişti; alanlarınız korundu. Kaydetmeden önce yeniden önizleyin."))
            if self.tur == "Satış":
                ust_alanlar = [self.ust["siparis"], self.ust["belge_no"], self.ust["tarih"],
                               self.ust["tevkifat"], self.ust["stopaj"]]
            else:
                for k in self.alim_isaretleri.values():
                    k.disabled = self.islemde
                ust_alanlar = [self.ust["cari"], self.ust["belge_no"], self.ust["tarih"],
                               self.ust["temin_usulu"], self.ust["gider_turu"], self.ust["belge_turu"],
                               self.ust["tevkifat"], self.ust["stopaj"]]
            form.append(ft.ResponsiveRow([ft.Container(k, col={"xs": 12, "md": 6}) for k in ust_alanlar]))
            if self.tur == "Alış" and self.alim_isaretleri:
                form.append(ft.Text("Alım belgesi kontrol listesi (zorunlular *)", weight=ft.FontWeight.BOLD))
                form.append(ft.Text(
                    "İşaretler, dosyanın fiziksel olarak dosyada bulunduğunu beyan eder. "
                    "Doğrudan teminde yaklaşık maliyet KDV hariç limit kontrolü yapılır (2026: 340.391 TL)."))
                form.extend(self.alim_isaretleri.values())
            if self.tur == "Satış":
                for s in self.satis_satirlari:
                    k = s["kaynak"]
                    form.append(ft.Text(f"{k['aciklama']} · kalan {T.siparis_sayisi_yaz(k['kalan'])} {k.get('birim') or ''}"
                                        f" · stok: {k.get('malzeme_ad') or 'bağlı değil; stok hareketi oluşmaz'}"))
                    alanlar: list[ft.Control] = [s["miktar"]]
                    if s["maliyet"] is not None and s["maliyet_hesabi"] is not None:
                        alanlar.extend([s["maliyet"], s["maliyet_hesabi"]])
                    form.append(ft.ResponsiveRow([ft.Container(k, col={"xs": 12, "md": 6}) for k in alanlar]))
                    if s["eski_baglanti_onayi"] is not None:
                        form.append(s["eski_baglanti_onayi"])
            else:
                for s in self.alis_satirlari:
                    alanlar = [s["malzeme"], s["hesap"], s["aciklama"], s["miktar"], s["fiyat"], s["kdv"], s["iskonto"]]
                    form.append(ft.Card(ft.Container(ft.Column([
                        ft.ResponsiveRow([ft.Container(k, col={"xs": 12, "md": 6}) for k in alanlar]),
                        ft.TextButton("Kalemi kaldır", disabled=self.islemde,
                                      on_click=lambda _, satir=s: self._alis_satiri_sil(satir)),
                    ]), padding=8)))
                form.append(ft.TextButton("Alış kalemi ekle", icon=ft.Icons.ADD, disabled=self.islemde,
                                          on_click=self._alis_satiri_ekle))
            onizle = ft.OutlinedButton("Faturayı önizle", disabled=self.islemde)
            onizle.on_click = lambda _: self.app.page.run_task(self._onizle, onizle)
            islemler: list[ft.Control] = [onizle, ft.TextButton("Vazgeç", disabled=self.islemde, on_click=self._kapat)]
            if self.onizleme is not None:
                detay = self.onizleme["detay"]
                form.append(ft.Text(f"Matrah {para(detay['matrah'])} TL · KDV {para(detay['kdv'])} TL · "
                                    f"Tevkifat {para(detay['tevkif_kdv'])} TL · Stopaj {para(detay['stopaj'])} TL · "
                                    f"Net {para(detay['net_tutar'])} TL", weight=ft.FontWeight.BOLD))
                for k in detay["kalemler"]:
                    form.append(ft.Text(f"{k['aciklama']} · tutar {para(k['tutar'])} TL · "
                                        f"indirim {para(k['iskonto'])} TL · KDV {para(k['kdv'])} TL"))
                if detay["tevkifat_hesabi"] or detay["stopaj_hesabi"]:
                    form.append(ft.Text(f"Tevkifat hesabı: {detay['tevkifat_hesabi'] or '—'} · "
                                        f"Stopaj hesabı: {detay['stopaj_hesabi'] or '—'}"))
                alim = self.onizleme.get("alim") or {}
                for u in alim.get("uyarilar") or []:
                    form.append(uyari_seridi(u))
                kaydet = ft.FilledButton("Faturayı kaydet", icon=ft.Icons.SAVE, disabled=self.islemde)
                kaydet.on_click = lambda _: self.app.page.run_task(self._kaydet, kaydet)
                islemler.insert(1, kaydet)
            form.append(ft.Row(islemler, wrap=True))
            kontroller.append(ft.Card(ft.Container(ft.Column(form, spacing=12), padding=16)))
        kontroller.append(ft.Text("Kayıt geçmişi", size=18, weight=ft.FontWeight.BOLD))
        for f in self.faturalar:
            baslik = f"{f['tur']} · {f['belge_no']} · {f['cari_unvan']}" + (" · Terslendi" if f["iptal"] else "")
            satirlar: list[ft.Control] = [
                ft.Text(baslik, weight=ft.FontWeight.BOLD),
                ft.Text(f"{T.gosterim('tarih', f['tarih'])} · Matrah {para(f['matrah'])} TL · "
                        f"KDV {para(f['kdv'])} TL · Net {para(f['net_tutar'])} TL"),
            ]
            if f.get("temin_usulu") or f.get("gider_turu"):
                satirlar.append(ft.Text(
                    f"Temin: {f.get('temin_usulu') or '—'} · Gider: {f.get('gider_turu') or '—'} · "
                    f"Belge: {f.get('belge_turu') or '—'}"))
            if f["tur"] == "Alış" and not f["iptal"]:
                satirlar.append(ft.TextButton(
                    "Alım belge özeti (HTML)", disabled=self.ust is not None or self.islemde,
                    on_click=lambda _, fatura=f: self.app.page.run_task(self._alim_html, fatura)))
            if not f["iptal"]:
                satirlar.append(ft.Text(f"Ödenen / tahsil edilen {para(f['odenen'])} TL · Kalan {para(f['kalan'])} TL"))
                if self.app.yetki("kasa") and Decimal(f["kalan"]) > 0:
                    satirlar.append(ft.TextButton(
                        "Kasa / Banka ekranını aç", disabled=self.ust is not None or self.islemde,
                        on_click=lambda _: self.app.page.run_task(self.app.sayfa_ac, "kasa")))
            satirlar.extend(ft.Text(f"{k['aciklama']} · {T.siparis_sayisi_yaz(k['miktar'])} {k.get('birim') or ''}"
                                    f" · {para(k['tutar'])} TL") for k in f["kalemler"])
            if f["iptal"]:
                satirlar.append(ft.Text(f"Ters kayıt gerekçesi: {f['ters_gerekce']}"))
            elif self.yazabilir:
                satirlar.append(ft.TextButton("Gerekçeli ters kayıt", disabled=self.ust is not None or self.islemde,
                                              on_click=lambda _, fatura=f: self._ters_dialog(fatura)))
            kontroller.append(ft.Card(ft.Container(ft.Column(satirlar, spacing=5), padding=12)))
        if not self.faturalar:
            kontroller.append(ft.Text("Fatura kaydı yok."))
        self.kontrol.controls = kontroller
        self.guncelle()
