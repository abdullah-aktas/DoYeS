"""Resmi yazı şablonları ve denetim formu kayıtları."""
from __future__ import annotations

from uuid import uuid4

import flet as ft

from dose.belge_sablonlari import SABLONLAR
from dose.denetim_rehber import KARARLAR, madde_listesi, ozet_bulgular

try:
    from . import takvim, tanimlar as T
    from .ekranlar import Ekran, secim_kutusu
    from .finans import kayit_sonrasi_yenile
except ImportError:
    import takvim
    import tanimlar as T
    from ekranlar import Ekran, secim_kutusu
    from finans import kayit_sonrasi_yenile


class ResmiYaziEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        self.veri: dict = {"yazilar": [], "yazabilir": False}
        self.form: dict | None = None
        self.kayit_id: int | None = None
        self.surum: int | None = None
        self.istek_id = ""
        self.kirli = False
        self.sablon_adi = "Serbest yazı"

    @property
    def yazabilir(self) -> bool:
        return bool(self.veri.get("yazabilir"))

    def kaydedilmemis(self) -> bool:
        return self.form is not None and self.kirli

    def _degisti(self, _=None):
        self.kirli = True

    async def yukle(self):
        self.veri = await self.app.supa.rpc("dose_resmi_veri")
        self._ciz()

    def duzen(self):
        self._ciz()

    def _sablon_doldur(self, ad: str | None = None):
        if not self.form:
            return
        ad = ad or self.sablon_adi or "Serbest yazı"
        self.sablon_adi = ad
        konu, muhatap, govde = SABLONLAR.get(ad, ("", "", ""))
        yil = takvim.bugun_istanbul().year
        ay = f"{takvim.bugun_istanbul().month:02d}"
        donem = "I"
        konu = konu.replace("{yil}", str(yil)).replace("{ay}", ay).replace("{donem}", donem)
        muhatap = muhatap.replace("{yil}", str(yil)).replace("{ay}", ay).replace("{donem}", donem)
        govde = govde.replace("{yil}", str(yil)).replace("{ay}", ay).replace("{donem}", donem)
        if konu:
            self.form["konu"].value = konu
        if muhatap:
            self.form["muhatap"].value = muhatap
        if govde:
            self.form["govde"].value = govde
        self.kirli = True
        self.guncelle()

    def _sablon_sec(self, e):
        self._sablon_doldur(e.control.value)

    def _ac(self, y: dict | None = None):
        if self.form is not None or self.islemde or not self.yazabilir:
            return
        y = y or {}
        self.kayit_id = y.get("id")
        self.surum = y.get("surum")
        self.sablon_adi = "Serbest yazı"
        self.form = {
            "sablon": secim_kutusu("Şablon", [(k, k) for k in SABLONLAR], "Serbest yazı",
                                   bos=False, on_select=self._sablon_sec),
            "tarih": ft.TextField(label="Tarih *", value=T.gosterim("tarih", y["tarih"]) if y.get("tarih")
                                  else takvim.bugun_istanbul().strftime("%d.%m.%Y"),
                                  hint_text="GG.AA.YYYY", on_change=self._degisti),
            "konu": ft.TextField(label="Konu *", value=y.get("konu") or "", on_change=self._degisti),
            "muhatap": ft.TextField(label="Muhatap *", value=y.get("muhatap") or "", on_change=self._degisti),
            "govde": ft.TextField(label="Metin *", value=y.get("govde") or "", multiline=True, min_lines=8,
                                  on_change=self._degisti),
        }
        self.istek_id = str(uuid4())
        self.kirli = False
        self._ciz()

    def _kapat(self, _=None):
        if self.kaydedilmemis():
            self.app.onayla("Kaydedilmemiş yazı bırakılacak.", "Bırak", self._kapat_uygula)
        else:
            self.form = None
            self._ciz()

    async def _kapat_uygula(self):
        self.form = None
        self.kirli = False
        self._ciz()

    async def _kaydet(self, dugme):
        async def is_():
            f = self.form
            if f is None:
                raise ValueError("Form açık değil.")
            try:
                tarih = T.tarih_coz(f["tarih"].value or "")
            except ValueError as e:
                raise ValueError("Geçerli tarih giriniz (GG.AA.YYYY).") from e
            veri = {"tarih": tarih, "konu": (f["konu"].value or "").strip(),
                    "muhatap": (f["muhatap"].value or "").strip(), "govde": (f["govde"].value or "").strip()}
            if not all(veri.values()):
                raise ValueError("Tarih, konu, muhatap ve metin zorunludur.")
            self.veri = await self.app.supa.rpc(
                "dose_resmi_kaydet", p_id=self.kayit_id, p_surum=self.surum, p_veri=veri, p_istek=self.istek_id)
            self.form = None
            self.kirli = False
            await kayit_sonrasi_yenile(self, "Resmi yazı kaydedildi.")
            self._ciz()
        await self.guvenli_islem(is_, dugme)

    def _ciz(self):
        try:
            from .tema import sayfa_baslik_satiri
        except ImportError:
            from tema import sayfa_baslik_satiri
        c: list[ft.Control] = [
            sayfa_baslik_satiri("Resmi yazılar", [
                ft.FilledButton("Yeni yazı", icon=ft.Icons.ADD, visible=self.yazabilir,
                                disabled=self.form is not None or self.islemde,
                                on_click=lambda _: self._ac()),
                ft.IconButton(ft.Icons.REFRESH, disabled=self.islemde,
                              on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))],
                              ft.Icons.DESCRIPTION),
            ft.Text("Okul içi resmi yazı kaydı ve şablon metni (Bakanlık faaliyet/mizan, Sayıştay üst yazısı dahil). "
                    "Dış e-imza / EBYS / GİB entegrasyonu yoktur."),
        ]
        if self.form is not None:
            kaydet = ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, disabled=self.islemde)
            kaydet.on_click = lambda _: self.app.page.run_task(self._kaydet, kaydet)
            c.append(ft.Card(ft.Container(ft.Column([
                self.form["sablon"], self.form["tarih"], self.form["konu"], self.form["muhatap"], self.form["govde"],
                ft.Row([kaydet, ft.TextButton("Vazgeç", on_click=self._kapat)])], spacing=10), padding=16)))
        for y in self.veri.get("yazilar") or []:
            c.append(ft.ListTile(
                title=ft.Text(f"{y['yazi_no']} · {y['konu']}"),
                subtitle=ft.Text(f"{T.gosterim('tarih', y['tarih'])} · {y['muhatap']}"),
                trailing=ft.IconButton(ft.Icons.EDIT, visible=self.yazabilir, disabled=self.form is not None,
                                       on_click=lambda _, yy=y: self._ac(yy)) if self.yazabilir else None))
        if not (self.veri.get("yazilar") or []):
            c.append(ft.Text("Kayıtlı resmi yazı yok."))
        self.kontrol.controls = c
        self.guncelle()


class DenetimEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        self.veri: dict = {"formlar": [], "yazabilir": False}
        self.form: dict | None = None
        self.kontrol_satirlari: list[dict] = []
        self.kayit_id: int | None = None
        self.surum: int | None = None
        self.istek_id = ""
        self.kirli = False

    @property
    def yazabilir(self) -> bool:
        return bool(self.veri.get("yazabilir"))

    def kaydedilmemis(self) -> bool:
        return self.form is not None and self.kirli

    def _degisti(self, _=None):
        self.kirli = True

    async def yukle(self):
        self.veri = await self.app.supa.rpc("dose_denetim_veri")
        self._ciz()

    def duzen(self):
        self._ciz()

    def _kontrol_kur(self, kayitli: list | None = None):
        onceki = {str(k.get("kod")): k for k in (kayitli or []) if isinstance(k, dict)}
        self.kontrol_satirlari = []
        for m in madde_listesi():
            eski = onceki.get(m["kod"]) or {}
            karar = eski.get("karar") if eski.get("karar") in KARARLAR else "İncelenmedi"
            self.kontrol_satirlari.append({
                "kod": m["kod"], "bolum": m["bolum"], "metin": m["metin"],
                "karar": secim_kutusu(f"{m['kod']} · karar", [(k, k) for k in KARARLAR], karar, bos=False,
                                      on_select=self._degisti),
                "not": ft.TextField(label=f"{m['kod']} not", value=eski.get("not") or "",
                                    dense=True, on_change=self._degisti),
            })

    def _ac(self, d: dict | None = None):
        if self.form is not None or self.islemde or not self.yazabilir:
            return
        d = d or {}
        self.kayit_id = d.get("id")
        self.surum = d.get("surum")
        self.form = {
            "tarih": ft.TextField(label="Tarih *", value=T.gosterim("tarih", d["tarih"]) if d.get("tarih")
                                  else takvim.bugun_istanbul().strftime("%d.%m.%Y"),
                                  hint_text="GG.AA.YYYY", on_change=self._degisti),
            "denetci": ft.TextField(label="Denetçi *", value=d.get("denetci") or "", on_change=self._degisti),
            "kapsam": ft.TextField(label="Kapsam *", value=d.get("kapsam") or "Mali iş ve işlemler (§5)",
                                   on_change=self._degisti),
            "bulgular": ft.TextField(label="Bulgular *", value=d.get("bulgular") or "", multiline=True, min_lines=4,
                                     hint_text="Boş bırakılırsa uygunsuz maddelerden özet üretilir",
                                     on_change=self._degisti),
            "sonuc": ft.TextField(label="Sonuç / öneriler *", value=d.get("sonuc") or "", multiline=True, min_lines=3,
                                  on_change=self._degisti),
        }
        self._kontrol_kur(d.get("kontrol_listesi"))
        self.istek_id = str(uuid4())
        self.kirli = False
        self._ciz()

    def _kapat(self, _=None):
        if self.kaydedilmemis():
            self.app.onayla("Kaydedilmemiş form bırakılacak.", "Bırak", self._kapat_uygula)
        else:
            self.form = None
            self.kontrol_satirlari = []
            self._ciz()

    async def _kapat_uygula(self):
        self.form = None
        self.kontrol_satirlari = []
        self.kirli = False
        self._ciz()

    def _kontrol_verisi(self) -> list[dict]:
        return [{
            "kod": s["kod"], "bolum": s["bolum"], "metin": s["metin"],
            "karar": s["karar"].value or "İncelenmedi",
            "not": (s["not"].value or "").strip(),
        } for s in self.kontrol_satirlari]

    async def _kaydet(self, dugme):
        async def is_():
            f = self.form
            if f is None:
                raise ValueError("Form açık değil.")
            try:
                tarih = T.tarih_coz(f["tarih"].value or "")
            except ValueError as e:
                raise ValueError("Geçerli tarih giriniz (GG.AA.YYYY).") from e
            liste = self._kontrol_verisi()
            bulgular = (f["bulgular"].value or "").strip() or ozet_bulgular(liste)
            veri = {"tarih": tarih, "denetci": (f["denetci"].value or "").strip(),
                    "kapsam": (f["kapsam"].value or "").strip(),
                    "bulgular": bulgular, "sonuc": (f["sonuc"].value or "").strip(),
                    "kontrol_listesi": liste}
            if not all([veri["denetci"], veri["kapsam"], veri["bulgular"], veri["sonuc"]]):
                raise ValueError("Denetçi, kapsam, bulgular ve sonuç zorunludur.")
            self.veri = await self.app.supa.rpc(
                "dose_denetim_kaydet", p_id=self.kayit_id, p_surum=self.surum, p_veri=veri, p_istek=self.istek_id)
            self.form = None
            self.kontrol_satirlari = []
            self.kirli = False
            await kayit_sonrasi_yenile(self, "Denetim formu kaydedildi.")
            self._ciz()
        await self.guvenli_islem(is_, dugme)

    def _ciz(self):
        try:
            from .tema import sayfa_baslik_satiri, METIN_IKINCIL
        except ImportError:
            from tema import sayfa_baslik_satiri, METIN_IKINCIL
        c: list[ft.Control] = [
            sayfa_baslik_satiri("Denetim formu", [
                ft.FilledButton("Yeni form", icon=ft.Icons.ADD, visible=self.yazabilir,
                                disabled=self.form is not None or self.islemde,
                                on_click=lambda _: self._ac()),
                ft.IconButton(ft.Icons.REFRESH, disabled=self.islemde,
                              on_click=lambda _: self.app.page.run_task(self.app.guvenli, self.yukle))],
                              ft.Icons.FACT_CHECK),
            ft.Text("MEB Teftiş Kurulu rehberinden seçilmiş mali kontrol maddeleri. "
                    "Resmî teftiş / Sayıştay formu değildir; okul içi hazırlık ve izleme içindir.",
                    size=12, color=METIN_IKINCIL),
        ]
        if self.form is not None:
            kaydet = ft.FilledButton("Kaydet", icon=ft.Icons.SAVE, disabled=self.islemde)
            kaydet.on_click = lambda _: self.app.page.run_task(self._kaydet, kaydet)
            maddeler: list[ft.Control] = [
                ft.Text("Rehber kontrol listesi (§5 odaklı)", weight=ft.FontWeight.BOLD)]
            onceki_bolum = None
            for s in self.kontrol_satirlari:
                if s["bolum"] != onceki_bolum:
                    onceki_bolum = s["bolum"]
                    maddeler.append(ft.Text(onceki_bolum, weight=ft.FontWeight.W_600))
                s["karar"].disabled = s["not"].disabled = self.islemde
                maddeler.append(ft.Text(f"{s['kod']}. {s['metin']}", size=12))
                maddeler.append(ft.ResponsiveRow([
                    ft.Container(s["karar"], col={"xs": 12, "md": 4}),
                    ft.Container(s["not"], col={"xs": 12, "md": 8}),
                ]))
            c.append(ft.Card(ft.Container(ft.Column([
                self.form["tarih"], self.form["denetci"], self.form["kapsam"],
                *maddeler,
                self.form["bulgular"], self.form["sonuc"],
                ft.Row([kaydet, ft.TextButton("Vazgeç", on_click=self._kapat)])], spacing=10,
                scroll=ft.ScrollMode.AUTO), padding=16)))
        for d in self.veri.get("formlar") or []:
            n = len(d.get("kontrol_listesi") or [])
            c.append(ft.ListTile(
                title=ft.Text(f"{d['form_no']} · {d['kapsam']}"),
                subtitle=ft.Text(f"{T.gosterim('tarih', d['tarih'])} · {d['denetci']} · "
                                 f"{n} madde · {(d.get('sonuc') or '')[:60]}"),
                trailing=ft.IconButton(ft.Icons.EDIT, visible=self.yazabilir, disabled=self.form is not None,
                                       on_click=lambda _, dd=d: self._ac(dd)) if self.yazabilir else None))
        if not (self.veri.get("formlar") or []):
            c.append(ft.Text("Kayıtlı denetim formu yok."))
        self.kontrol.controls = c
        self.guncelle()
