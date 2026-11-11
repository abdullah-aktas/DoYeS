"""Invoice record screens. These records do not submit e-invoices to GİB."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
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
        self.alim_ihtiyac: ft.TextField | None = None
        self.alim_yaklasik: ft.TextField | None = None
        self.teklif_satirlari: list[dict] = []
        self.satir_sayaci = 0
        self.kirli = False
        self.uzak_uyari = False
        self.girdi_surumu = 0
        self.onizleme: dict | None = None
        self.hazir: dict | None = None
        self.istek_id = ""
        self.islemde = False
        self._picker: ft.FilePicker | None = None
        self._kapatilan_uyarilar: set[str] = set()

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
            self.alim_ihtiyac = ft.TextField(
                label="İhtiyaç / talep özeti *", min_lines=2, max_lines=4,
                hint_text="Ne alınacak, neden gerekli (doğrudan temin)", on_change=self._degisti)
            self.alim_yaklasik = ft.TextField(
                label="Yaklaşık maliyet (KDV hariç, TL) *", hint_text="örn. 12500,00",
                on_change=self._degisti)
            self.teklif_satirlari = []
            self._teklif_ekle()
            self._temin_degisti()
            self._alis_satiri_ekle()
        self.kirli = False
        self.uzak_uyari = False
        self.girdi_surumu += 1
        self.onizleme = None
        self.hazir = None
        self.istek_id = str(uuid4())
        self._kapatilan_uyarilar = set()
        self._ciz()

    def _uyari_kapat(self, metin: str, _=None):
        self._kapatilan_uyarilar.add(metin)
        self._ciz()

    def _picker_hazirla(self):
        if self._picker is None:
            self._picker = ft.FilePicker()
            self.app.page.services.append(self._picker)
            self.app.page.update()

    def _belge_medya_doldur(self, metin: str):
        from dose import gorsel_ice
        alanlar = gorsel_ice.fatura_alanlari_cikar(metin)
        if not alanlar:
            raise ValueError(
                "Belge no / tarih okunamadı. Metni düzenleyip yeniden deneyin veya alanları elle girin.")
        if self.ust is None:
            return
        if alanlar.get("belge_no"):
            self.ust["belge_no"].value = alanlar["belge_no"]
        if alanlar.get("tarih"):
            self.ust["tarih"].value = alanlar["tarih"]
        self._degisti()
        self._ciz()
        ozet = ", ".join(f"{k}={v}" for k, v in alanlar.items())
        self.app.bildir(f"Belgeden dolduruldu: {ozet}")

    def _belge_resim_ac(self, _=None):
        self.app.page.run_task(self._belge_resim_sec)

    async def _belge_resim_sec(self):
        self._picker_hazirla()
        dosyalar = await self._picker.pick_files(
            dialog_title="Fatura / fiş görüntüsü veya PDF seçin",
            allowed_extensions=["png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp", "pdf"],
            with_data=True)
        if not dosyalar:
            return
        dosya = dosyalar[0]

        async def is_():
            from dose import gorsel_ice
            ad = (dosya.name or "").lower()
            veri = dosya.bytes
            yol = Path(dosya.path) if dosya.path else None
            if ad.endswith(".pdf") or (yol and yol.suffix.lower() == ".pdf"):
                # Metin PDF dene; olmazsa OCR yok — kullanıcıya görüntü öner
                try:
                    import pdfplumber
                    from io import BytesIO
                    kaynak = BytesIO(veri) if veri is not None else str(yol)
                    with pdfplumber.open(kaynak) as pdf:
                        metin = "\n".join((s.extract_text() or "") for s in pdf.pages)
                except Exception as e:
                    raise ValueError(f"PDF okunamadı: {e}") from e
                if not (metin or "").strip():
                    raise ValueError(
                        "PDF’de seçilebilir metin yok (tarama). Sayfayı PNG/JPG kaydedip yükleyin "
                        "veya «Belge metni / ses» kullanın.")
            else:
                metin = gorsel_ice.metin_cikar(yol=yol, veri=veri, ad=ad)
            self._belge_medya_doldur(metin)

        await self.app.guvenli(is_)

    def _belge_metin_ac(self, _=None):
        try:
            from . import medya
        except ImportError:
            import medya

        async def tamam(metin: str):
            async def is_():
                self._belge_medya_doldur(metin)

            await self.app.guvenli(is_)

        medya.ses_veya_metin_dialog(
            self.app,
            baslik="Fatura metni / sesle yaz",
            ipucu="Belge no ve tarihi içeren metni yapıştırın veya dikte edin (Win+H / Mikrofon).",
            on_tamam=tamam)

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
        if temin == "Doğrudan Temin" and not self.teklif_satirlari:
            self._teklif_ekle()
        self._degisti()
        self._ciz()

    def _teklif_ekle(self, _=None):
        n = len(self.teklif_satirlari) + 1
        self.teklif_satirlari.append({
            "firma": ft.TextField(label=f"{n}. teklif firma / kişi *", on_change=self._degisti),
            "tutar": ft.TextField(label=f"{n}. teklif tutarı (KDV hariç) *", on_change=self._degisti),
            "secildi": ft.Checkbox(label="Seçildi", value=False, on_change=self._teklif_secildi),
        })
        self._degisti()
        if self.ust is not None:
            self._ciz()

    def _teklif_secildi(self, e):
        if e.control.value:
            for t in self.teklif_satirlari:
                if t["secildi"] is not e.control:
                    t["secildi"].value = False
        self._degisti()
        self.guncelle()

    def _teklif_sil(self, satir: dict):
        if len(self.teklif_satirlari) <= 1:
            self.app.bildir("En az bir teklif satırı kalmalı.", hata=True)
            return
        self.teklif_satirlari = [t for t in self.teklif_satirlari if t is not satir]
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
            teklifler = []
            for t in self.teklif_satirlari:
                firma = (t["firma"].value or "").strip()
                tutar = (t["tutar"].value or "").strip()
                if firma or tutar or t["secildi"].value:
                    teklifler.append({
                        "firma": firma, "tutar": tutar, "secildi": bool(t["secildi"].value)})
            veri["alim"] = {
                "temin_usulu": ust["temin_usulu"].value,
                "gider_turu": ust["gider_turu"].value,
                "belge_turu": ust["belge_turu"].value,
                "belgeler": {k: bool(c.value) for k, c in self.alim_isaretleri.items()},
                "ihtiyac_ozeti": (self.alim_ihtiyac.value or "").strip() if self.alim_ihtiyac else "",
                "yaklasik_maliyet": (self.alim_yaklasik.value or "").strip() if self.alim_yaklasik else "",
                "teklifler": teklifler,
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
        kompakt = not self.app.genis
        kontroller: list[ft.Control] = [
            sayfa_baslik_satiri("Fatura kayıtları", [
                ft.FilledButton("Satış", icon=ft.Icons.ADD, visible=self.yazabilir, disabled=self.ust is not None,
                                on_click=lambda _: self._yeni("Satış")),
                ft.FilledButton("Alış", icon=ft.Icons.ADD, visible=self.yazabilir, disabled=self.ust is not None,
                                on_click=lambda _: self._yeni("Alış")),
                ft.IconButton(ft.Icons.REFRESH, tooltip="Yenile", disabled=self.islemde,
                              on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))],
                              ft.Icons.RECEIPT_LONG, kompakt=kompakt),
            ft.Text("GİB’e e-Fatura göndermez; yerel kayıt ve çıktıdır.",
                    size=12, visible=not kompakt or self.ust is None),
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
            form.append(ft.Row([
                ft.OutlinedButton("Belge resmi oku", icon=ft.Icons.IMAGE_SEARCH,
                                  disabled=self.islemde, on_click=self._belge_resim_ac),
                ft.OutlinedButton("Belge metni / ses", icon=ft.Icons.MIC,
                                  disabled=self.islemde, on_click=self._belge_metin_ac),
            ], wrap=True))
            if self.tur == "Alış" and self.alim_isaretleri:
                limit = self.veri.get("dogrudan_temin_limit") or "340391"
                limit_uyari = (
                    f"Doğrudan temin limiti (KDV hariç): {para(limit)} TL. "
                    f"Diğer idareler {para(self.veri.get('dogrudan_temin_limit_diger') or '340391')} · "
                    f"Büyükşehir {para(self.veri.get('dogrudan_temin_limit_buyuksehir') or '1021827')}. "
                    "Kurum kartındaki büyükşehir işareti hangi limitin uygulanacağını seçer. Limit aşımı kaydı engeller.")
                if limit_uyari not in self._kapatilan_uyarilar:
                    form.append(uyari_seridi(
                        limit_uyari,
                        on_kapat=lambda _, m=limit_uyari: self._uyari_kapat(m)))
                temin = (self.ust.get("temin_usulu").value if self.ust else None) or ""
                if temin == "Doğrudan Temin" and self.alim_ihtiyac and self.alim_yaklasik:
                    self.alim_ihtiyac.disabled = self.islemde
                    self.alim_yaklasik.disabled = self.islemde
                    form.append(ft.Text("Doğrudan temin dosyası", weight=ft.FontWeight.BOLD))
                    form.append(self.alim_ihtiyac)
                    form.append(self.alim_yaklasik)
                    form.append(ft.Text("Piyasa fiyat teklifleri (en az 1; önerilen 3)", weight=ft.FontWeight.BOLD))
                    for t in self.teklif_satirlari:
                        t["firma"].disabled = t["tutar"].disabled = t["secildi"].disabled = self.islemde
                        form.append(ft.ResponsiveRow([
                            ft.Container(t["firma"], col={"xs": 12, "md": 5}),
                            ft.Container(t["tutar"], col={"xs": 12, "md": 4}),
                            ft.Container(t["secildi"], col={"xs": 8, "md": 2}),
                            ft.Container(ft.TextButton("Sil", disabled=self.islemde,
                                                       on_click=lambda _, s=t: self._teklif_sil(s)),
                                         col={"xs": 4, "md": 1}),
                        ]))
                    form.append(ft.TextButton("Teklif ekle", icon=ft.Icons.ADD, disabled=self.islemde,
                                              on_click=self._teklif_ekle))
                form.append(ft.Text("Alım belgesi kontrol listesi (zorunlular *)", weight=ft.FontWeight.BOLD))
                form.append(ft.Text(
                    "İşaretler, belgenin fiziksel dosyada bulunduğunu beyan eder. "
                    "Uygulama belge dosyası saklamaz; asıl evrakı klasörleyin.", size=12))
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
                    if u in self._kapatilan_uyarilar:
                        continue
                    form.append(uyari_seridi(
                        u, on_kapat=lambda _, m=u: self._uyari_kapat(m),
                        kapat_ipucu="Anladım — bir daha gösterme"))
                kaydet = ft.FilledButton("Faturayı kaydet", icon=ft.Icons.SAVE, disabled=self.islemde)
                kaydet.on_click = lambda _: self.app.page.run_task(self._kaydet, kaydet)
                islemler.insert(1, kaydet)
            form.append(ft.Row(islemler, wrap=True))
            kontroller.append(ft.Card(ft.Container(ft.Column(form, spacing=10 if kompakt else 12),
                                                   padding=12 if kompakt else 16)))
        # Mobilde form açıkken geçmişi gizle — tek işe odaklan
        if self.ust is None or self.app.genis:
            kontroller.append(ft.Text("Kayıt geçmişi", size=16 if kompakt else 18, weight=ft.FontWeight.BOLD))
            for f in self.faturalar:
                baslik = f"{f['tur']} · {f['belge_no']} · {f['cari_unvan']}" + (" · Terslendi" if f["iptal"] else "")
                satirlar: list[ft.Control] = [
                    ft.Text(baslik, weight=ft.FontWeight.BOLD,
                            max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(f"{T.gosterim('tarih', f['tarih'])} · Net {para(f['net_tutar'])} TL"
                            + ("" if kompakt else f" · Matrah {para(f['matrah'])} · KDV {para(f['kdv'])}")),
                ]
                if not kompakt and (f.get("temin_usulu") or f.get("gider_turu")):
                    satirlar.append(ft.Text(
                        f"Temin: {f.get('temin_usulu') or '—'} · Gider: {f.get('gider_turu') or '—'} · "
                        f"Belge: {f.get('belge_turu') or '—'}"))
                if f["tur"] == "Alış" and not f["iptal"]:
                    satirlar.append(ft.TextButton(
                        "Alım belge özeti", disabled=self.ust is not None or self.islemde,
                        on_click=lambda _, fatura=f: self.app.page.run_task(self._alim_html, fatura)))
                if not f["iptal"]:
                    satirlar.append(ft.Text(f"Kalan {para(f['kalan'])} TL"
                                            + ("" if kompakt else f" · Ödenen {para(f['odenen'])} TL")))
                    if self.app.yetki("kasa") and Decimal(f["kalan"]) > 0:
                        satirlar.append(ft.TextButton(
                            "Kasaya git", disabled=self.ust is not None or self.islemde,
                            on_click=lambda _: self.app.page.run_task(self.app.sayfa_ac, "kasa")))
                if not kompakt:
                    satirlar.extend(
                        ft.Text(f"{k['aciklama']} · {T.siparis_sayisi_yaz(k['miktar'])} {k.get('birim') or ''}"
                                f" · {para(k['tutar'])} TL") for k in f["kalemler"])
                elif f.get("kalemler"):
                    satirlar.append(ft.Text(f"{len(f['kalemler'])} kalem", size=12, color=ft.Colors.ON_SURFACE_VARIANT))
                if f["iptal"]:
                    satirlar.append(ft.Text(f"Ters kayıt: {f['ters_gerekce']}"))
                elif self.yazabilir:
                    satirlar.append(ft.TextButton("Ters kayıt", disabled=self.ust is not None or self.islemde,
                                                  on_click=lambda _, fatura=f: self._ters_dialog(fatura)))
                kontroller.append(ft.Card(ft.Container(ft.Column(satirlar, spacing=4), padding=10 if kompakt else 12)))
            if not self.faturalar:
                kontroller.append(ft.Text("Fatura kaydı yok."))
        self.kontrol.controls = kontroller
        self.guncelle()
