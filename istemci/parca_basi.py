"""Piece-rate (parça başı) payroll: Ek-3 cost sheet, daily production sheet, approval chain and bank payment.

All amounts are calculated by the server (dose_pb_kaydet / dose_pb_veri); this screen only collects input and
shows the server's result, so the client can never disagree with the approved, journalled figures.
"""
from __future__ import annotations

import calendar
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

import flet as ft

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

HAZIRLAYAN_ROLLER = ("Alan Şefi", "Teknik Müdür Yardımcısı", "Öğretmen")
VARSAYILAN = {"pesin": "1", "shcek": "1", "ogrenci": "50", "dv": "7,59", "gv": "15"}
DURUM_RENGI = {"Taslak": ft.Colors.GREY_600, "TMY Onayında": ft.Colors.AMBER_800,
               "Müdür Onayında": ft.Colors.ORANGE_800, "Onaylandı": ft.Colors.GREEN_700, "İptal": ft.Colors.RED_700}


def yuzde_yaz(oran: str | None) -> str:
    return T.siparis_yuzdesi_yaz(oran) if oran not in (None, "") else ""


def binde_yaz(oran: str | None) -> str:
    if oran in (None, ""):
        return ""
    metin = format(Decimal(oran) * 1000, "f")
    if "." in metin:
        metin = metin.rstrip("0").rstrip(".")
    return metin.replace(".", ",")


def _sayi(etiket: str, metin: str | None, bos: str | None = None) -> Decimal:
    metin = (metin or "").strip()
    if not metin and bos is not None:
        metin = bos
    try:
        return T.ondalik_coz(metin)
    except ValueError as e:
        raise ValueError(f"{etiket} için geçerli bir sayı giriniz.") from e


def _oran(etiket: str, metin: str | None, bolen: int = 100) -> str:
    deger = _sayi(etiket, metin)
    if deger < 0 or deger > bolen:
        raise ValueError(f"{etiket} 0 ile {bolen} arasında olmalıdır.")
    return format(deger / bolen, "f")


def kdv_haric(fatura_tutari: Decimal, kdv_orani: Decimal) -> Decimal:
    """KDV-inclusive invoice amount → order base (Excel: 40.000 / 1,01 = 39.603,96)."""
    return (fatura_tutari / (1 + kdv_orani)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ay_gun_sayisi(iso_tarih: str) -> int:
    yil, ay, _ = (int(p) for p in iso_tarih.split("-"))
    return calendar.monthrange(yil, ay)[1]


class PuantajSatiri:
    def __init__(self, tur: str, kisi_id: int, ad: str, gorev: str, gv: str, gunler: list[str], degisti):
        self.tur = tur
        self.kisi_id = kisi_id
        self.ad = ad
        self.degisti = degisti
        self.gorev = ft.TextField(label="Görevi", value=gorev, dense=True, width=150, on_change=degisti)
        self.gv = ft.TextField(label="GV %", value=gv, dense=True, width=80, visible=tur == "Öğretmen",
                               keyboard_type=ft.KeyboardType.NUMBER, on_change=degisti)
        self.gunler: list[ft.TextField] = []
        self.boyutla(len(gunler) or 31, gunler)

    def boyutla(self, gun_sayisi: int, degerler: list[str] | None = None):
        eski = degerler if degerler is not None else [g.value or "" for g in self.gunler]
        self.gunler = [ft.TextField(value=(eski[i] if i < len(eski) and eski[i] not in ("0", None) else ""),
                                    label=str(i + 1), dense=True, width=54, text_size=12,
                                    keyboard_type=ft.KeyboardType.NUMBER, on_change=self.degisti)
                       for i in range(gun_sayisi)]

    def veri(self) -> dict:
        gunler = []
        for i, alan in enumerate(self.gunler, 1):
            deger = _sayi(f"{self.ad} {i}. gün üretimi", alan.value, "0")
            if deger < 0:
                raise ValueError(f"{self.ad} {i}. gün üretimi eksi olamaz.")
            gunler.append(format(deger, "f"))
        kayit = {"kisi_turu": self.tur, "kisi_id": self.kisi_id, "gorev": (self.gorev.value or "").strip(),
                 "gunler": gunler}
        if self.tur == "Öğretmen":
            kayit["gv_orani"] = _oran(f"{self.ad} gelir vergisi oranı", self.gv.value)
        return kayit


class ParcaBasiEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        self.veri: dict = {"siparisler": [], "personel": [], "ogrenciler": [], "hakedisler": [], "banka_bakiye": None}
        self.form: dict | None = None
        self.malzemeler: list[dict[str, ft.TextField]] = []
        self.puantaj: list[PuantajSatiri] = []
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
        return self.app.yetki("parca_basi") == "y" and self.rol in HAZIRLAYAN_ROLLER

    def karar_verebilir(self, h: dict) -> bool:
        return self.app.yetki("parca_basi") == "y" and (
            (h["durum"] == "TMY Onayında" and self.rol == "Teknik Müdür Yardımcısı")
            or (h["durum"] == "Müdür Onayında" and self.rol == "Okul Müdürü"))

    def odeyebilir(self, h: dict) -> bool:
        return (h["durum"] == "Onaylandı" and not h.get("odeme") and self.rol == "Sayman"
                and self.app.yetki("parca_basi") == "y" and self.app.yetki("kasa") == "y")

    def iptal_edebilir(self, h: dict) -> bool:
        if self.app.yetki("parca_basi") != "y":
            return False
        if h["durum"] == "Taslak":
            return self.rol in HAZIRLAYAN_ROLLER
        return h["durum"] == "Onaylandı" and not h.get("odeme") and self.rol == "Okul Müdürü"

    # ------------------------------------------------------------------ yaşam döngüsü
    def kaydedilmemis(self) -> bool:
        return self.form is not None and self.kirli

    def _degisti(self, _=None):
        self.kirli = True

    async def yukle(self):
        self.veri = await self.app.supa.rpc("dose_pb_veri")
        self._ciz()

    async def uzaktan_degisti(self):
        if self.form is not None:
            self.uzak_uyari = True
            self.veri = await self.app.supa.rpc("dose_pb_veri")
            self._ciz()
            return
        await self.yukle()

    def duzen(self):
        self._ciz()

    def _siparis(self, siparis_id) -> dict | None:
        return next((s for s in self.veri["siparisler"] if str(s["id"]) == str(siparis_id)), None)

    def _mevzuat_yuzde(self, anahtar: str) -> str:
        deg = (self.veri.get("mevzuat") or {}).get("degerler") or {}
        return yuzde_yaz(deg.get(anahtar)) if deg.get(anahtar) not in (None, "") else ""

    # ------------------------------------------------------------------ form
    def _ac(self, h: dict | None = None):
        if self.form is not None or self.islemde or not self.hazirlayabilir:
            return
        if not h and not self.veri.get("mevzuat"):
            self.app.bildir("Doğrulanmış merkez parametre yayını yok. Sayman önce Okul parametre "
                            "doğrulamasını tamamlamalıdır.", hata=True)
            return
        bugun = takvim.bugun_istanbul()
        ilk = bugun.replace(day=1).strftime("%d.%m.%Y")
        h = h or {}
        siparisler = [(str(s["id"]), f"{s['siparis_no']} · {s['konu']} · {s.get('cari') or ''}")
                      for s in self.veri["siparisler"]]
        if h and str(h["siparis_id"]) not in {k for k, _ in siparisler}:
            siparisler.append((str(h["siparis_id"]), f"{h['siparis_no']} · {h['siparis_konu']}"))

        def alan(etiket, deger="", **ek):
            return ft.TextField(label=etiket, value=deger, on_change=self._degisti, **ek)

        sayi = {"keyboard_type": ft.KeyboardType.NUMBER}
        self.form = {
            "siparis": secim_kutusu("Onaylı parça başı siparişi *", siparisler, h.get("siparis_id"),
                                    disabled=bool(h), on_select=self._siparis_secildi),
            "baslama": alan("İş başlama *", T.gosterim("tarih", h["baslama"]) if h else ilk, hint_text="GG.AA.YYYY",
                            on_blur=self._donem_degisti),
            "bitis": alan("İş bitiş *", T.gosterim("tarih", h["bitis"]) if h else bugun.strftime("%d.%m.%Y"),
                          hint_text="GG.AA.YYYY"),
            "fatura_tutari": alan("KDV dahil fatura tutarı (yardımcı)", **sayi),
            "bedel": alan("Hakediş bedeli, KDV hariç (TL) *", T.siparis_sayisi_yaz(h.get("bedel")), **sayi),
            "hizmet_alimi": alan("Hizmet alımı (TL)", T.siparis_sayisi_yaz(h.get("hizmet_alimi") or "0"), **sayi),
            "faaliyet": alan("Faaliyet gideri %*", yuzde_yaz(h.get("faaliyet_orani")) or self._mevzuat_yuzde("pb_faaliyet_orani"),
                             **sayi),
            "kar": alan("Kâr %*", yuzde_yaz(h.get("kar_orani")) or self._mevzuat_yuzde("pb_kar_orani"), **sayi),
            "pesin": alan("Peşin gelir vergisi %*", yuzde_yaz(h.get("pesin_orani")) or VARSAYILAN["pesin"], **sayi),
            "shcek": alan("SHÇEK payı %*", yuzde_yaz(h.get("shcek_orani")) or VARSAYILAN["shcek"], **sayi),
            "ogrenci": alan("Öğrenci payı (işçiliğin) %*",
                            yuzde_yaz(h.get("ogrenci_orani")) or self._mevzuat_yuzde("ogrenci_hakki_orani")
                            or VARSAYILAN["ogrenci"], **sayi),
            "dv": alan("Damga vergisi (binde) *", binde_yaz(h.get("dv_orani")) or VARSAYILAN["dv"], **sayi),
            "asgari": alan("Aylık brüt asgari ücret (TL) *", T.siparis_sayisi_yaz(h.get("asgari_ucret")), **sayi),
            "urun": alan("Üretilen ürün / yapılan iş *", h.get("urun_aciklama") or ""),
            "miktar": alan("Üretilen miktar *", T.siparis_sayisi_yaz(h.get("uretilen_miktar")), **sayi),
            "birim": alan("Birim *", h.get("birim") or "Adet"),
            "aciklama": alan("Açıklama", h.get("aciklama") or "", multiline=True, min_lines=2),
        }
        self.form["fatura_tutari"].on_change = self._fatura_tutari_degisti
        self.malzemeler = [self._malzeme_satiri(m) for m in h.get("malzemeler", [])]
        kisiler = {("Öğretmen", p["id"]): p["ad_soyad"] for p in self.veri["personel"]}
        kisiler.update({("Öğrenci", o["id"]): o["ad_soyad"] for o in self.veri["ogrenciler"]})
        adlar = {(k["kisi_turu"], k["kisi_id"]): k.get("ad_soyad")
                 for k in (h.get("hesap") or {}).get("kisiler", [])}
        self.puantaj = [PuantajSatiri(k["kisi_turu"], k["kisi_id"],
                                      kisiler.get((k["kisi_turu"], k["kisi_id"]))
                                      or adlar.get((k["kisi_turu"], k["kisi_id"])) or f"#{k['kisi_id']}",
                                      k.get("gorev") or "", yuzde_yaz(k.get("gv_orani")), k.get("gunler") or [],
                                      self._degisti)
                        for k in h.get("kisiler", [])]
        self.kayit_id = h.get("id")
        self.surum = h.get("surum")
        self.hesap = h.get("hesap")
        self.istek_id = str(uuid4())
        self.kirli = False
        self.uzak_uyari = False
        if not h:
            self._donem_degisti()
        self._ciz()

    def _malzeme_satiri(self, m: dict | None = None) -> dict[str, ft.TextField]:
        m = m or {}
        sayi = {"keyboard_type": ft.KeyboardType.NUMBER, "dense": True, "on_change": self._degisti}
        return {"cins": ft.TextField(label="Malzeme cinsi", value=m.get("cins", ""), dense=True, expand=True,
                                     on_change=self._degisti),
                "miktar": ft.TextField(label="Miktar", value=T.siparis_sayisi_yaz(m.get("miktar")), width=100, **sayi),
                "birim": ft.TextField(label="Birim", value=m.get("birim", "Adet"), width=90, dense=True,
                                      on_change=self._degisti),
                "birim_fiyat": ft.TextField(label="Birim fiyat", value=T.siparis_sayisi_yaz(m.get("birim_fiyat")),
                                            width=120, **sayi),
                "kdv": ft.TextField(label="KDV %", value=yuzde_yaz(m.get("kdv_orani")) or "20", width=80, **sayi)}

    def _siparis_secildi(self, _=None):
        self._degisti()
        self._fatura_tutari_degisti()

    def _fatura_tutari_degisti(self, _=None):
        self._degisti()
        if self.form is None:
            return
        siparis = self._siparis(self.form["siparis"].value)
        metin = (self.form["fatura_tutari"].value or "").strip()
        if not siparis or not metin:
            return
        try:
            self.form["bedel"].value = T.siparis_sayisi_yaz(
                format(kdv_haric(T.ondalik_coz(metin), Decimal(siparis["kdv_orani"])), "f"))
        except (ValueError, ArithmeticError):
            return
        self.guncelle()

    def _gun_sayisi(self) -> int:
        try:
            return ay_gun_sayisi(T.tarih_coz(self.form["baslama"].value or "")) if self.form else 31
        except ValueError:
            return 31

    def _donem_degisti(self, _=None):
        if self.form is None:
            return
        gun = self._gun_sayisi()
        for satir in self.puantaj:
            if len(satir.gunler) != gun:
                satir.boyutla(gun)
        self._degisti()
        self._ciz()

    def _malzeme_ekle(self, _=None):
        self.malzemeler.append(self._malzeme_satiri())
        self._degisti()
        self._ciz()

    def _malzeme_sil(self, i: int):
        del self.malzemeler[i]
        self._degisti()
        self._ciz()

    def _kisi_ekle(self, tur: str, secim: ft.Dropdown):
        if not secim.value:
            self.app.bildir("Eklenecek kişiyi seçiniz.", hata=True)
            return
        kisi_id = int(secim.value)
        if any(s.tur == tur and s.kisi_id == kisi_id for s in self.puantaj):
            self.app.bildir("Bu kişi puantajda zaten var.", hata=True)
            return
        kaynak = self.veri["personel"] if tur == "Öğretmen" else self.veri["ogrenciler"]
        kisi = next(k for k in kaynak if k["id"] == kisi_id)
        gorev = (kisi.get("kadro_unvani") or "Öğretmen") if tur == "Öğretmen" else f"Öğrenci {kisi.get('sinif') or ''}"
        satir = PuantajSatiri(tur, kisi_id, kisi["ad_soyad"], gorev.strip(), VARSAYILAN["gv"] if tur == "Öğretmen" else "",
                              [], self._degisti)
        satir.boyutla(self._gun_sayisi(), [])
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
            self.app.onayla("Kaydedilmemiş hakediş değişiklikleri bırakılacak.", "Değişiklikleri bırak",
                            self._kapat_uygula)
        else:
            self.form = None
            self._ciz()

    async def _kapat_uygula(self):
        self.form = None
        self.kirli = False
        self._ciz()

    def form_verisi(self) -> tuple[dict, list[dict], list[dict]]:
        f = self.form
        if f is None:
            raise ValueError("Önce hakediş formunu açın.")
        if not f["siparis"].value:
            raise ValueError("Onaylı parça başı siparişi seçiniz.")
        try:
            baslama, bitis = T.tarih_coz(f["baslama"].value or ""), T.tarih_coz(f["bitis"].value or "")
        except ValueError as e:
            raise ValueError("İş başlama ve bitiş tarihlerini GG.AA.YYYY biçiminde giriniz.") from e
        veri = {
            "siparis_id": int(f["siparis"].value), "baslama": baslama, "bitis": bitis,
            "bedel": format(_sayi("Hakediş bedeli", f["bedel"].value), "f"),
            "hizmet_alimi": format(_sayi("Hizmet alımı", f["hizmet_alimi"].value, "0"), "f"),
            "faaliyet_orani": _oran("Faaliyet gideri oranı", f["faaliyet"].value),
            "kar_orani": _oran("Kâr oranı", f["kar"].value),
            "pesin_orani": _oran("Peşin gelir vergisi oranı", f["pesin"].value),
            "shcek_orani": _oran("SHÇEK payı oranı", f["shcek"].value),
            "ogrenci_orani": _oran("Öğrenci payı oranı", f["ogrenci"].value),
            "dv_orani": _oran("Damga vergisi oranı", f["dv"].value, 1000),
            "asgari_ucret": format(_sayi("Asgari ücret", f["asgari"].value), "f"),
            "urun_aciklama": (f["urun"].value or "").strip(),
            "uretilen_miktar": format(_sayi("Üretilen miktar", f["miktar"].value), "f"),
            "birim": (f["birim"].value or "").strip(), "aciklama": (f["aciklama"].value or "").strip(),
        }
        malzemeler = []
        for i, m in enumerate(self.malzemeler, 1):
            if not (m["cins"].value or "").strip():
                raise ValueError(f"{i}. malzemenin cinsini yazınız veya satırı silin.")
            malzemeler.append({"cins": m["cins"].value.strip(),
                               "miktar": format(_sayi(f"{i}. malzeme miktarı", m["miktar"].value), "f"),
                               "birim": (m["birim"].value or "").strip(),
                               "birim_fiyat": format(_sayi(f"{i}. malzeme birim fiyatı", m["birim_fiyat"].value), "f"),
                               "kdv_orani": _oran(f"{i}. malzeme KDV oranı", m["kdv"].value)})
        if not self.puantaj:
            raise ValueError("Puantaja en az bir öğretmen veya öğrenci ekleyiniz.")
        gun = ay_gun_sayisi(baslama)
        for satir in self.puantaj:
            if len(satir.gunler) != gun:
                satir.boyutla(gun)
        return veri, malzemeler, [s.veri() for s in self.puantaj]

    async def _kaydet(self, dugme):
        async def is_():
            veri, malzemeler, kisiler = self.form_verisi()
            try:
                sonuc = await self.app.supa.rpc(
                    "dose_pb_kaydet", p_id=self.kayit_id, p_surum=self.surum, p_veri=veri,
                    p_malzemeler=malzemeler, p_kisiler=kisiler, p_istek=self.istek_id)
            except SupaHata as e:
                if e.kod == "ag" or e.durum in (502, 503, 504):
                    raise SupaHata("Bağlantı kesildi; taslak kaydedilmiş olabilir. Listeyi yenileyip kontrol edin; "
                                   "aynı yeni taslak iki kez oluşturulmaz.", e.durum, e.kod, e.ipucu) from e
                raise
            self.kayit_id, self.surum, self.hesap = sonuc["id"], sonuc["surum"], sonuc["hesap"]
            self.istek_id = str(uuid4())
            self.kirli = False
            self.veri = await self.app.supa.rpc("dose_pb_veri")
            self._ciz()
            hatalar = len(self.hesap.get("hatalar") or [])
            self.app.bildir("Taslak kaydedildi ve hesaplandı." if not hatalar else
                            f"Taslak kaydedildi; onaya göndermeden önce {hatalar} kontrolü düzeltin.", hata=bool(hatalar))
        await self.guvenli_islem(is_, dugme)

    # ------------------------------------------------------------------ iş akışı
    async def _gonder(self, h: dict, dugme):
        async def is_():
            sonuc = await self.app.supa.rpc("dose_pb_gonder", p_id=h["id"], p_surum=h["surum"])
            if self.form is not None and self.kayit_id == h["id"]:
                self.form = None
                self.kirli = False
            await kayit_sonrasi_yenile(self, f"Hakediş onaya gönderildi: {sonuc['durum']}.")
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

    def _karar_dialog(self, h: dict, onay: bool):
        etiket = ("Uygundur notu" if self.rol == "Teknik Müdür Yardımcısı" else "Olur notu") if onay else "İade gerekçesi"

        async def islem(metin):
            sonuc = await self.app.supa.rpc("dose_pb_karar", p_id=h["id"], p_surum=h["surum"], p_onay=onay,
                                            p_aciklama=metin)
            await kayit_sonrasi_yenile(self, f"Hakediş durumu: {sonuc['durum']}.")

        baslik = ("Uygundur" if self.rol == "Teknik Müdür Yardımcısı" else "Olur") if onay else "Düzeltmeye iade et"
        self._gerekce_dialog(f"{h['hakedis_no']} · {baslik}", etiket, not onay, baslik, islem)

    def _iptal_dialog(self, h: dict):
        async def islem(metin):
            await self.app.supa.rpc("dose_pb_iptal", p_id=h["id"], p_surum=h["surum"], p_gerekce=metin)
            await kayit_sonrasi_yenile(self, "Hakediş iptal edildi." + (" Ters yevmiye kaydı oluşturuldu."
                                                                        if h["durum"] == "Onaylandı" else ""))
        self._gerekce_dialog(f"{h['hakedis_no']} iptali", "İptal gerekçesi", True, "İptal et", islem)

    def _ode_dialog(self, h: dict):
        tarih = ft.TextField(label="Ödeme (dekont) tarihi *", value=takvim.bugun_istanbul().strftime("%d.%m.%Y"),
                             hint_text="GG.AA.YYYY")
        belge = ft.TextField(label="Dekont / talimat no *")
        ode = ft.FilledButton("Ödemeyi kaydet", icon=ft.Icons.PAYMENTS)
        vazgec = ft.TextButton("Vazgeç", on_click=lambda _: self.app.page.pop_dialog())
        istek = str(uuid4())
        net = (h.get("hesap") or {}).get("toplam", {}).get("net", "0")

        async def onay(_):
            async def is_():
                try:
                    gun = T.tarih_coz(tarih.value or "")
                except ValueError as e:
                    raise ValueError("Geçerli ödeme tarihi giriniz (GG.AA.YYYY).") from e
                if not (belge.value or "").strip():
                    raise ValueError("Dekont veya ödeme talimatı numarası zorunludur.")
                try:
                    await self.app.supa.rpc("dose_pb_ode", p_id=h["id"], p_tarih=gun,
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
            modal=True, title=ft.Text(f"{h['hakedis_no']} banka ödemesi"),
            content=ft.Column([
                ft.Text(f"Net ödenecek: {para(net)} TL (IBAN'lara toplu ödeme)."),
                ft.Text(f"Banka (102) bakiyesi: {para(bakiye)} TL" if bakiye is not None else ""),
                ft.Text("Bu ekran banka transferi yapmaz; gerçekleşen toplu ödemeyi kaydeder.", size=12),
                tarih, belge], tight=True),
            actions=[vazgec, ode]))

    def _belgeler(self, h: dict):
        try:
            from . import belgeler as B
        except ImportError:
            import belgeler as B
        B.belge_menusu(self.app, self.veri.get("okul") or {}, h)

    # ------------------------------------------------------------------ çizim
    def _hesap_ozeti(self, hesap: dict | None) -> list[ft.Control]:
        if not hesap:
            return [ft.Text("Hesap için taslağı kaydedin.", italic=True)]
        satirlar = [
            ("Hakediş bedeli (KDV hariç)", hesap["bedel"]), ("İlk madde ve malzeme", hesap["malzeme"]),
            ("Hizmet alımı", hesap["hizmet_alimi"]), ("Faaliyet giderleri", hesap["faaliyet"]),
            ("Kâr", hesap["kar"]), ("Peşin gelir vergisi", hesap["pesin_gelir_vergisi"]),
            ("SHÇEK payı", hesap["shcek"]), ("Dağıtılacak işçilik", hesap["iscilik"]),
            ("Öğretmen havuzu", hesap["ogretmen_havuz"]), ("Öğrenci havuzu", hesap["ogrenci_havuz"]),
        ]
        kontroller: list[ft.Control] = [
            ft.ResponsiveRow([ft.Container(ft.Column([ft.Text(e, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                                                      ft.Text(f"{para(t)} TL", weight=ft.FontWeight.BOLD)],
                                                     spacing=0), col={"xs": 6, "md": 3})
                              for e, t in satirlar])]
        for hata in hesap.get("hatalar") or []:
            kontroller.append(uyari_seridi(hata))
        for uyari in hesap.get("uyarilar") or []:
            kontroller.append(ft.Container(ft.Row([ft.Icon(ft.Icons.INFO_OUTLINE, color=ft.Colors.AMBER_900),
                                                   ft.Text(uyari, expand=True)]),
                                           bgcolor=ft.Colors.AMBER_50, padding=8, border_radius=8))
        if hesap.get("kisiler"):
            kontroller.append(ft.Row([ft.DataTable(
                columns=[ft.DataColumn(ft.Text(b)) for b in
                         ("Ad soyad", "Tür", "Adet", "Brüt", "Gelir V.", "Damga V.", "Net")],
                rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(str(v))) for v in (
                    k.get("ad_soyad") or "?", k["kisi_turu"], T.siparis_sayisi_yaz(k["adet"]), para(k["brut"]),
                    para(k["gelir_vergisi"]), para(k["damga_vergisi"]), para(k["net"]))])
                      for k in hesap["kisiler"]]
                + [ft.DataRow(cells=[ft.DataCell(ft.Text(v, weight=ft.FontWeight.BOLD)) for v in (
                    "TOPLAM", "", "", para(hesap["toplam"]["brut"]), para(hesap["toplam"]["gelir_vergisi"]),
                    para(hesap["toplam"]["damga_vergisi"]), para(hesap["toplam"]["net"]))])])],
                scroll=ft.ScrollMode.AUTO))
        return kontroller

    def _form_karti(self) -> ft.Control:
        f = self.form
        assert f is not None
        for k in f.values():
            k.disabled = self.islemde or (k is f["siparis"] and self.kayit_id is not None)
        ust = ft.ResponsiveRow([ft.Container(f[a], col={"xs": 12, "md": 6 if a in ("siparis", "urun", "aciklama") else 3})
                                for a in ("siparis", "baslama", "bitis", "fatura_tutari", "bedel", "hizmet_alimi",
                                          "faaliyet", "kar", "pesin", "shcek", "ogrenci", "dv", "asgari", "urun",
                                          "miktar", "birim", "aciklama")])
        malzeme_satirlari: list[ft.Control] = []
        for i, m in enumerate(self.malzemeler):
            malzeme_satirlari.append(ft.Row([*m.values(), ft.IconButton(
                ft.Icons.DELETE_OUTLINE, tooltip="Satırı sil", disabled=self.islemde,
                on_click=lambda _, i=i: self._malzeme_sil(i))], wrap=True))
        ogretmen_sec = secim_kutusu("Öğretmen / usta", [(str(p["id"]), p["ad_soyad"] + ("" if p["iban_var"] else
                                                                                      " (IBAN yok)"))
                                                        for p in self.veri["personel"]], None)
        ogrenci_sec = secim_kutusu("Öğrenci", [(str(o["id"]), f"{o['ad_soyad']} · {o.get('sinif') or ''}"
                                               + ("" if o["veli_muvafakat"] else " (muvafakat yok)"))
                                              for o in self.veri["ogrenciler"]], None)
        puantaj: list[ft.Control] = []
        for i, s in enumerate(self.puantaj):
            for alan in (s.gorev, s.gv, *s.gunler):
                alan.disabled = self.islemde
            puantaj.append(ft.Column([
                ft.Row([ft.Icon(ft.Icons.PERSON if s.tur == "Öğretmen" else ft.Icons.SCHOOL, size=18),
                        ft.Text(f"{s.ad} · {s.tur}", weight=ft.FontWeight.BOLD, expand=True), s.gorev, s.gv,
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Puantajdan çıkar", disabled=self.islemde,
                                      on_click=lambda _, i=i: self._kisi_sil(i))], wrap=True),
                ft.Row(s.gunler, scroll=ft.ScrollMode.AUTO, spacing=4)], spacing=4))
        kaydet = ft.FilledButton("Kaydet ve hesapla", icon=ft.Icons.CALCULATE, disabled=self.islemde)
        kaydet.on_click = lambda _: self.app.page.run_task(self._kaydet, kaydet)
        gonderilebilir = (self.kayit_id is not None and not self.kirli and self.hesap is not None
                          and not self.hesap.get("hatalar"))
        gonder = ft.OutlinedButton("Onaya gönder", icon=ft.Icons.SEND, disabled=self.islemde or not gonderilebilir)
        gonder.on_click = lambda _: self.app.page.run_task(
            self._gonder, {"id": self.kayit_id, "surum": self.surum}, gonder)
        return ft.Card(ft.Container(ft.Column([
            ft.Text("Parça başı hakediş" + (f" · {self._no()}" if self.kayit_id else " · yeni taslak"),
                    size=18, weight=ft.FontWeight.BOLD),
            *([uyari_seridi("Kayıtlar başka bir kullanıcı tarafından değişti; formunuz korundu.")]
              if self.uzak_uyari else []),
            ft.Text("Oranlar yüzde olarak girilir; faaliyet, kâr, öğrenci payı ve malzeme sınırı merkezde yayımlanan "
                    "değerlere göre sunucuda denetlenir. Tutarlar sunucuda kuruşu kuruşuna hesaplanır.", size=12),
            ust,
            ft.Row([ft.Text("İlk madde ve malzeme", size=16, weight=ft.FontWeight.BOLD, expand=True),
                    ft.TextButton("Malzeme ekle", icon=ft.Icons.ADD, disabled=self.islemde,
                                  on_click=self._malzeme_ekle)]),
            *malzeme_satirlari,
            ft.Text("Puantaj (günlük üretim adedi)", size=16, weight=ft.FontWeight.BOLD),
            ft.ResponsiveRow([
                ft.Container(ft.Row([ogretmen_sec, ft.IconButton(ft.Icons.PERSON_ADD, tooltip="Öğretmen ekle",
                                                                 disabled=self.islemde,
                                                                 on_click=lambda _: self._kisi_ekle("Öğretmen",
                                                                                                    ogretmen_sec))]),
                             col={"xs": 12, "md": 6}),
                ft.Container(ft.Row([ogrenci_sec, ft.IconButton(ft.Icons.PERSON_ADD, tooltip="Öğrenci ekle",
                                                                disabled=self.islemde,
                                                                on_click=lambda _: self._kisi_ekle("Öğrenci",
                                                                                                   ogrenci_sec))]),
                             col={"xs": 12, "md": 6})]),
            *puantaj,
            ft.Row([kaydet, gonder, ft.TextButton("Kapat", disabled=self.islemde, on_click=self._kapat)], wrap=True),
            ft.Divider(),
            ft.Text("Sunucu hesabı (Ek-3 ön maliyet ve bordro)", size=16, weight=ft.FontWeight.BOLD),
            *self._hesap_ozeti(self.hesap),
        ], spacing=12), padding=16))

    def _no(self) -> str:
        return next((h["hakedis_no"] for h in self.veri["hakedisler"] if h["id"] == self.kayit_id), f"#{self.kayit_id}")

    def _hakedis_karti(self, h: dict, engelli: bool) -> ft.Control:
        hesap = h.get("hesap") or {}
        toplam = hesap.get("toplam") or {}
        dugmeler: list[ft.Control] = []
        if h["durum"] == "Taslak" and self.hazirlayabilir:
            dugmeler.append(ft.TextButton("Düzenle", icon=ft.Icons.EDIT, disabled=engelli,
                                          on_click=lambda _: self._ac(h)))
            gonder = ft.TextButton("Onaya gönder", icon=ft.Icons.SEND,
                                   disabled=engelli or bool(hesap.get("hatalar")))
            gonder.on_click = lambda _: self.app.page.run_task(self._gonder, h, gonder)
            dugmeler.append(gonder)
        if self.karar_verebilir(h):
            dugmeler += [ft.TextButton("Uygundur" if h["durum"] == "TMY Onayında" else "Olur", icon=ft.Icons.CHECK,
                                       disabled=engelli, on_click=lambda _: self._karar_dialog(h, True)),
                         ft.TextButton("İade et", icon=ft.Icons.UNDO, disabled=engelli,
                                       on_click=lambda _: self._karar_dialog(h, False))]
        if self.odeyebilir(h):
            dugmeler.append(ft.TextButton("Bankadan öde", icon=ft.Icons.PAYMENTS, disabled=engelli,
                                          on_click=lambda _: self._ode_dialog(h)))
        if self.iptal_edebilir(h):
            dugmeler.append(ft.TextButton("İptal", icon=ft.Icons.CANCEL, disabled=engelli,
                                          on_click=lambda _: self._iptal_dialog(h)))
        dugmeler.append(ft.TextButton("Belgeler", icon=ft.Icons.PRINT, disabled=engelli,
                                      on_click=lambda _: self._belgeler(h)))
        odeme = h.get("odeme")
        gecmis = " → ".join(f"{a['islem']} ({a['rol']})" for a in h.get("onaylar") or [])
        return ft.Card(ft.Container(ft.Column([
            ft.Row([ft.Text(f"{h['hakedis_no']} · {h['siparis_no']} · {h['siparis_konu']}",
                            weight=ft.FontWeight.BOLD, expand=True),
                    ft.Container(ft.Text(h["durum"], color=ft.Colors.WHITE, size=12),
                                 bgcolor=DURUM_RENGI.get(h["durum"], ft.Colors.GREY), padding=ft.Padding(8, 2, 8, 2),
                                 border_radius=10)], wrap=True),
            ft.Text(f"{T.gosterim('tarih', h['baslama'])} – {T.gosterim('tarih', h['bitis'])} · {h.get('bolum') or ''}"
                    f" · Bedel {para(h['bedel'])} TL · Brüt {para(toplam.get('brut', '0'))} TL · "
                    f"Net {para(toplam.get('net', '0'))} TL"),
            *([ft.Text(f"Ödendi: {T.gosterim('tarih', odeme['tarih'])} · {odeme['belge_no']} · "
                       f"{para(odeme['tutar'])} TL", color=ft.Colors.GREEN_800)] if odeme else []),
            *([ft.Text(f"{len(hesap['hatalar'])} kontrol düzeltilmeli.", color=ft.Colors.RED_700)]
              if h["durum"] == "Taslak" and hesap.get("hatalar") else []),
            *([ft.Text(gecmis, size=12, color=ft.Colors.ON_SURFACE_VARIANT)] if gecmis else []),
            ft.Row(dugmeler, wrap=True),
        ], spacing=6), padding=12))

    def _ciz(self):
        engelli = self.form is not None or self.islemde
        kontroller: list[ft.Control] = [
            ft.Row([ft.Text("Parça başı hakediş (Yön. md.8)", size=20, weight=ft.FontWeight.BOLD, expand=True),
                    ft.FilledButton("Yeni hakediş", icon=ft.Icons.ADD, visible=self.hazirlayabilir,
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
            kontroller.append(ft.Text("Hakediş için onaylanmış, ücret esası parça başı olan sipariş yok.",
                                      color=ft.Colors.ON_SURFACE_VARIANT))
        if self.form is not None:
            kontroller.append(self._form_karti())
        for h in self.veri["hakedisler"]:
            kontroller.append(self._hakedis_karti(h, engelli))
        if not self.veri["hakedisler"]:
            kontroller.append(ft.Text("Henüz parça başı hakediş yok."))
        self.kontrol.controls = kontroller
        self.guncelle()
