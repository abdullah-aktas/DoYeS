"""Yıllık özet, üç aylık faaliyet ve Bakanlık mizan raporları."""
from __future__ import annotations

import flet as ft

try:
    from . import takvim
    from .belgeler import belge_klasoru, marka_img_html
    from .ekranlar import Ekran, uyari_seridi
    from .finans import para
except ImportError:
    import takvim
    from belgeler import belge_klasoru, marka_img_html
    from ekranlar import Ekran, uyari_seridi
    from finans import para


def _rapor_altlik() -> str:
    return (f"<p style='margin-top:24px;color:#1f4e79;font-size:12px'>{marka_img_html(24)} "
            "DÖSE Yönetim · iç kayıt çıktısı</p>")


class RaporlarEkrani(Ekran):
    def __init__(self, app):
        super().__init__(app)
        bugun = takvim.bugun_istanbul()
        self.yil = bugun.year
        self.ay = bugun.month
        self.veri: dict = {}
        self.faaliyet: dict = {}
        self.mizan: dict = {}

    async def yukle(self):
        self.veri = await self.app.supa.rpc("dose_rapor_ozet", p_yil=self.yil)
        self.yil = int(self.veri.get("yil") or self.yil)
        try:
            self.faaliyet = await self.app.supa.rpc("dose_faaliyet_rapor", p_yil=self.yil)
        except Exception:
            self.faaliyet = {"donemler": [], "yil": self.yil}
        try:
            self.mizan = await self.app.supa.rpc("dose_mizan_bakanlik", p_yil=self.yil, p_ay=self.ay)
        except Exception:
            self.mizan = {"satirlar": [], "yil": self.yil, "ay": self.ay}
        self._ciz()

    def duzen(self):
        self._ciz()

    def _yil_degisti(self, e):
        try:
            self.yil = int(e.control.value)
        except (TypeError, ValueError):
            return
        self.app.page.run_task(self.app.guvenli, self.yukle)

    def _ay_degisti(self, e):
        try:
            self.ay = int(e.control.value)
        except (TypeError, ValueError):
            return
        self.app.page.run_task(self.app.guvenli, self.yukle)

    def _html(self) -> str:
        return self._ozet_html()

    def _ozet_html(self) -> str:
        okul = (self.app.ben or {}).get("okul") or {}
        v = self.veri
        return (
            "<!DOCTYPE html><html lang='tr'><head><meta charset='utf-8'>"
            f"<title>DÖSE rapor {self.yil}</title>"
            "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:24px}"
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:8px;text-align:left}"
            "th{background:#1f4e79;color:#fff}</style></head><body>"
            f"<h1>{okul.get('ad') or 'Okul'} · {self.yil} özet</h1>"
            "<p>Bu çıktı DÖSE iç kaydıdır; GİB e-Fatura veya banka API’si değildir.</p>"
            "<table><tr><th>Kalem</th><th>Değer</th></tr>"
            f"<tr><td>Sipariş sayısı</td><td>{v.get('siparis', 0)}</td></tr>"
            f"<tr><td>Satış faturaları (net)</td><td>{para(v.get('fatura_satis'))} TL</td></tr>"
            f"<tr><td>Alış faturaları (net)</td><td>{para(v.get('fatura_alis'))} TL</td></tr>"
            f"<tr><td>Kasa bakiyesi</td><td>{para(v.get('kasa_bakiye'))} TL</td></tr>"
            f"<tr><td>Banka bakiyesi</td><td>{para(v.get('banka_bakiye'))} TL</td></tr>"
            f"<tr><td>Hazine payı hasılat (ay)</td><td>{para(v.get('hp_hasilat'))} TL</td></tr>"
            f"</table>{_rapor_altlik()}</body></html>"
        )

    def _faaliyet_html(self) -> str:
        okul = (self.app.ben or {}).get("okul") or {}
        satirlar = "".join(
            f"<tr><td>{d.get('donem')}</td><td>{d.get('son_gun')}</td><td>{d.get('siparis')}</td>"
            f"<td>{para(d.get('satis'))}</td><td>{para(d.get('alis'))}</td>"
            f"<td>{para(d.get('tahsilat'))}</td><td>{para(d.get('parca_basi'))}</td>"
            f"<td>{para(d.get('fazla_calisma'))}</td><td>{para(d.get('hazine'))}</td></tr>"
            for d in self.faaliyet.get("donemler") or [])
        return (
            "<!DOCTYPE html><html lang='tr'><head><meta charset='utf-8'>"
            f"<title>Üç aylık faaliyet {self.yil}</title>"
            "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:24px}"
            "table{border-collapse:collapse;width:100%;font-size:13px}"
            "td,th{border:1px solid #ccc;padding:6px}th{background:#1f4e79;color:#fff}</style></head><body>"
            f"<h1>{okul.get('ad') or 'Okul'} · {self.yil} üç aylık faaliyet raporu</h1>"
            f"<p>{self.faaliyet.get('not') or 'Yönerge md.48.'}</p>"
            "<table><tr><th>Dönem</th><th>Son gönderim</th><th>Sipariş</th><th>Satış</th><th>Alış</th>"
            "<th>Tahsilat</th><th>Parça başı</th><th>Fazla çalışma</th><th>Hazine</th></tr>"
            f"{satirlar}</table>"
            "<p>Üst yazı ile Destek Hizmetleri Genel Müdürlüğü / İşletmeler Daire Başkanlığına gönderilir.</p>"
            f"{_rapor_altlik()}</body></html>"
        )

    def _mizan_html(self) -> str:
        okul = (self.app.ben or {}).get("okul") or {}
        satirlar = "".join(
            f"<tr><td>{s.get('hesap_kodu') or s.get('hesap')}</td>"
            f"<td>{para(s.get('borc'))}</td><td>{para(s.get('alacak'))}</td>"
            f"<td>{para(s.get('bakiye'))}</td></tr>"
            for s in self.mizan.get("satirlar") or [])
        return (
            "<!DOCTYPE html><html lang='tr'><head><meta charset='utf-8'>"
            f"<title>Aylık mizan {self.yil}-{self.ay:02d}</title>"
            "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:24px}"
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:6px}"
            "th{background:#1f4e79;color:#fff}</style></head><body>"
            f"<h1>{okul.get('ad') or 'Okul'} · {self.ay:02d}/{self.yil} aylık mizan</h1>"
            f"<p>Son gönderim: {self.mizan.get('son_gun')}. {self.mizan.get('not') or ''}</p>"
            "<table><tr><th>Hesap</th><th>Borç</th><th>Alacak</th><th>Bakiye</th></tr>"
            f"{satirlar or '<tr><td colspan=4>Satır yok</td></tr>'}</table>{_rapor_altlik()}</body></html>"
        )

    async def _aktar(self, dugme, tur: str, icerik: str = "ozet"):
        async def is_():
            klasor = belge_klasoru()
            okul = (self.app.ben or {}).get("okul") or {}
            if icerik == "faaliyet":
                ad, html = f"DOSE_faaliyet_{self.yil}", self._faaliyet_html()
            elif icerik == "mizan":
                ad, html = f"DOSE_mizan_{self.yil}_{self.ay:02d}", self._mizan_html()
            else:
                ad, html = f"DOSE_rapor_{self.yil}", self._ozet_html()
            ad = f"{ad}_{okul.get('kurum_kodu') or 'okul'}"
            if tur == "html" or icerik != "ozet":
                yol = klasor / f"{ad}.html"
                yol.write_text(html, encoding="utf-8")
            elif tur == "xlsx":
                from dose.excel import disa_aktar
                yol = klasor / f"{ad}.xlsx"
                v = self.veri
                disa_aktar(yol, [("Özet", ["Kalem", "Değer"], [
                    ["Sipariş sayısı", v.get("siparis", 0)],
                    ["Satış faturaları (net)", float(v.get("fatura_satis") or 0)],
                    ["Alış faturaları (net)", float(v.get("fatura_alis") or 0)],
                    ["Kasa bakiyesi", float(v.get("kasa_bakiye") or 0)],
                    ["Banka bakiyesi", float(v.get("banka_bakiye") or 0)],
                    ["Hazine payı hasılat (ay)", float(v.get("hp_hasilat") or 0)],
                ])], baslik=f"DÖSE {self.yil} özet")
            else:
                from dose.pdf import S_BASLIK, S_NORMAL, olustur, tablo
                from reportlab.platypus import Paragraph, Spacer
                yol = klasor / f"{ad}.pdf"
                v = self.veri
                olustur(yol, [
                    Paragraph(f"{okul.get('ad') or 'Okul'} · {self.yil} özet", S_BASLIK),
                    Spacer(1, 8),
                    Paragraph("DÖSE iç kayıt özeti (GİB/banka API’si değildir).", S_NORMAL),
                    Spacer(1, 12),
                    tablo(["Kalem", "Değer"], [
                        ["Sipariş sayısı", str(v.get("siparis", 0))],
                        ["Satış faturaları (net)", f"{para(v.get('fatura_satis'))} TL"],
                        ["Alış faturaları (net)", f"{para(v.get('fatura_alis'))} TL"],
                        ["Kasa bakiyesi", f"{para(v.get('kasa_bakiye'))} TL"],
                        ["Banka bakiyesi", f"{para(v.get('banka_bakiye'))} TL"],
                        ["Hazine payı hasılat (ay)", f"{para(v.get('hp_hasilat'))} TL"],
                    ]),
                ], baslik=f"DÖSE {self.yil}")
            if hasattr(self.app.page, "launch_url"):
                self.app.page.launch_url(yol.as_uri())
            self.app.bildir(f"Rapor kaydedildi: {yol.name}")
        await self.guvenli_islem(is_, dugme)

    def _ciz(self):
        yillar = [(str(y), str(y)) for y in range(self.yil, self.yil - 6, -1)]
        aylar = [(str(a), f"{a:02d}") for a in range(1, 13)]
        v = self.veri
        html_d = ft.FilledButton("Özet HTML", icon=ft.Icons.HTML, disabled=self.islemde)
        xlsx_d = ft.FilledButton("Özet Excel", icon=ft.Icons.TABLE_VIEW, disabled=self.islemde)
        pdf_d = ft.FilledButton("Özet PDF", icon=ft.Icons.PICTURE_AS_PDF, disabled=self.islemde)
        faal_d = ft.FilledButton("Üç aylık faaliyet HTML", icon=ft.Icons.DATE_RANGE, disabled=self.islemde)
        mizan_d = ft.FilledButton("Bakanlık mizan HTML", icon=ft.Icons.ACCOUNT_BALANCE, disabled=self.islemde)
        html_d.on_click = lambda _: self.app.page.run_task(self._aktar, html_d, "html", "ozet")
        xlsx_d.on_click = lambda _: self.app.page.run_task(self._aktar, xlsx_d, "xlsx", "ozet")
        pdf_d.on_click = lambda _: self.app.page.run_task(self._aktar, pdf_d, "pdf", "ozet")
        faal_d.on_click = lambda _: self.app.page.run_task(self._aktar, faal_d, "html", "faaliyet")
        mizan_d.on_click = lambda _: self.app.page.run_task(self._aktar, mizan_d, "html", "mizan")
        donem_satir = [
            ft.ListTile(
                title=ft.Text(d.get("donem") or ""),
                subtitle=ft.Text(
                    f"Son gün {d.get('son_gun')} · Sipariş {d.get('siparis')} · "
                    f"Satış {para(d.get('satis'))} · PB {para(d.get('parca_basi'))} · "
                    f"FC {para(d.get('fazla_calisma'))} · Hazine {para(d.get('hazine'))}"))
            for d in self.faaliyet.get("donemler") or []
        ]
        try:
            from .tema import sayfa_baslik_satiri
        except ImportError:
            from tema import sayfa_baslik_satiri
        self.kontrol.controls = [
            sayfa_baslik_satiri("Raporlar", ikon=ft.Icons.ASSESSMENT),
            ft.Text("Yıllık özet, üç aylık faaliyet (md.48) ve Bakanlık aylık mizan (md.47). GİB gönderimi yoktur."),
            ft.Row([
                ft.Dropdown(label="Yıl", options=[ft.dropdown.Option(k, t) for k, t in yillar],
                            value=str(self.yil), on_select=self._yil_degisti, width=120),
                ft.Dropdown(label="Mizan ayı", options=[ft.dropdown.Option(k, t) for k, t in aylar],
                            value=str(self.ay), on_select=self._ay_degisti, width=120),
            ], wrap=True),
            ft.Card(ft.Container(ft.Column([
                ft.Text(f"{self.yil} özeti", weight=ft.FontWeight.BOLD),
                ft.Text(f"Sipariş: {v.get('siparis', 0)}"),
                ft.Text(f"Satış: {para(v.get('fatura_satis'))} TL · Alış: {para(v.get('fatura_alis'))} TL"),
                ft.Text(f"Kasa: {para(v.get('kasa_bakiye'))} TL · Banka: {para(v.get('banka_bakiye'))} TL"),
            ], spacing=6), padding=16)),
            ft.Text("Üç aylık faaliyet", weight=ft.FontWeight.BOLD),
            *(donem_satir or [ft.Text("Dönem verisi yok.")]),
            ft.Row([html_d, xlsx_d, pdf_d, faal_d, mizan_d], wrap=True),
            uyari_seridi("Excel/PDF masaüstü/web’de openpyxl/reportlab ister; APK’da HTML kullanın. "
                         "Yıl sonu Sayıştay paketini Yıl sonu / ÜTP ve Resmi yazı şablonlarından tamamlayın."),
        ]
        self.guncelle()
