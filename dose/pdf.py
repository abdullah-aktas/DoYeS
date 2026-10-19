"""reportlab tabanlı PDF belge altyapısı (Türkçe karakter destekli)."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from . import UYGULAMA_ADI
from .hesap import para

_FONT = "Helvetica"
_FONT_B = "Helvetica-Bold"


def _font_kaydet():
    global _FONT, _FONT_B
    klasor = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    adaylar = [("arial.ttf", "arialbd.ttf"), ("calibri.ttf", "calibrib.ttf"), ("tahoma.ttf", "tahomabd.ttf"),
               ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")]
    ekstra = [Path("/usr/share/fonts/truetype/dejavu")]
    for normal, kalin in adaylar:
        for k in [klasor] + ekstra:
            if (k / normal).exists() and (k / kalin).exists():
                try:
                    pdfmetrics.registerFont(TTFont("TRFont", str(k / normal)))
                    pdfmetrics.registerFont(TTFont("TRFont-Bold", str(k / kalin)))
                    pdfmetrics.registerFontFamily("TRFont", normal="TRFont", bold="TRFont-Bold",
                                                  italic="TRFont", boldItalic="TRFont-Bold")
                    _FONT, _FONT_B = "TRFont", "TRFont-Bold"
                    return
                except Exception:
                    continue


_font_kaydet()

_ss = getSampleStyleSheet()
S_NORMAL = ParagraphStyle("n", parent=_ss["Normal"], fontName=_FONT, fontSize=10, leading=13)
S_KUCUK = ParagraphStyle("k", parent=S_NORMAL, fontSize=8, leading=10)
S_METIN = ParagraphStyle("m", parent=S_NORMAL, alignment=TA_JUSTIFY, firstLineIndent=12 * mm, leading=15)
S_ORTA = ParagraphStyle("o", parent=S_NORMAL, alignment=TA_CENTER)
S_ORTA_B = ParagraphStyle("ob", parent=S_ORTA, fontName=_FONT_B)
S_SAG = ParagraphStyle("s", parent=S_NORMAL, alignment=TA_RIGHT)
S_BASLIK = ParagraphStyle("b", parent=S_NORMAL, fontName=_FONT_B, fontSize=12, alignment=TA_CENTER,
                          spaceBefore=6, spaceAfter=6, leading=15)
S_ALT_BASLIK = ParagraphStyle("ab", parent=S_NORMAL, fontName=_FONT_B, fontSize=10, spaceBefore=6, spaceAfter=3)
S_HUCRE = ParagraphStyle("h", parent=S_NORMAL, fontSize=8, leading=9.5)
S_HUCRE_B = ParagraphStyle("hb", parent=S_HUCRE, fontName=_FONT_B)
S_HUCRE_SAG = ParagraphStyle("hs", parent=S_HUCRE, alignment=TA_RIGHT)


def tarih_tr(t) -> str:
    if not t:
        return ""
    if isinstance(t, date):
        return t.strftime("%d.%m.%Y")
    s = str(t)[:10]
    if len(s) == 10 and s[4] == "-":
        return f"{s[8:10]}.{s[5:7]}.{s[0:4]}"
    return s


def P(metin, stil=S_NORMAL):
    return Paragraph(str(metin if metin is not None else "").replace("\n", "<br/>"), stil)


def tr_buyuk(s: str) -> str:
    return (s or "").replace("i", "İ").replace("ı", "I").upper()


def antet(kurum: dict, sayi: str = "", konu: str = "", tarih=None) -> list:
    il = tr_buyuk(kurum.get("il") or "")
    ilce = tr_buyuk(kurum.get("ilce") or "")
    satirlar = ["T.C."]
    if ilce and ilce not in ("MERKEZ", "MERKEZİ"):
        satirlar.append(f"{ilce} KAYMAKAMLIĞI")
    elif il:
        satirlar.append(f"{il} VALİLİĞİ")
    satirlar.append(tr_buyuk(kurum.get("okul_adi") or "") + " MÜDÜRLÜĞÜ")
    satirlar.append(kurum.get("isletme_adi") or "Döner Sermaye İşletmesi")
    parca = [P("<br/>".join(satirlar), S_ORTA_B), Spacer(1, 4 * mm)]
    if sayi or konu:
        t = Table([[P(f"Sayı : {sayi}"), P(tarih_tr(tarih or date.today()), S_SAG)],
                   [P(f"Konu : {konu}"), ""]], colWidths=[120 * mm, 50 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        parca += [t, Spacer(1, 5 * mm)]
    return parca


def tablo(basliklar: list, satirlar: list, genislikler: list | None = None, sayisal: set | None = None,
          toplam_satiri: list | None = None, yazi_boyu: float = 8) -> Table:
    """sayisal: sağa hizalanacak ve para biçimlenecek kolon indeksleri."""
    sayisal = sayisal or set()
    stil_h = ParagraphStyle("th", parent=S_HUCRE_B, fontSize=yazi_boyu, alignment=TA_CENTER)
    stil_n = ParagraphStyle("tn", parent=S_HUCRE, fontSize=yazi_boyu)
    stil_s = ParagraphStyle("ts", parent=S_HUCRE_SAG, fontSize=yazi_boyu)
    veri = [[Paragraph(str(b), stil_h) for b in basliklar]]

    def hucre(i, v, kalin=False):
        if i in sayisal and isinstance(v, (int, float)):
            v = para(v)
        st = stil_s if i in sayisal else stil_n
        if kalin:
            st = ParagraphStyle("tk", parent=st, fontName=_FONT_B)
        return Paragraph("" if v is None else str(v), st)

    for s in satirlar:
        veri.append([hucre(i, v) for i, v in enumerate(s)])
    if toplam_satiri:
        veri.append([hucre(i, v, True) for i, v in enumerate(toplam_satiri)])
    t = Table(veri, colWidths=genislikler, repeatRows=1)
    stil = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe7f2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if toplam_satiri:
        stil.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0f0f0")))
    t.setStyle(TableStyle(stil))
    return t


def bilgi_tablosu(ciftler: list[tuple], genislik=(55 * mm, 115 * mm)) -> Table:
    veri = [[P(f"<b>{a}</b>", S_HUCRE), P(b, S_HUCRE)] for a, b in ciftler]
    t = Table(veri, colWidths=list(genislik))
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f5f9")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return t


def imza_blogu(imzalar: list[tuple], sutun: int = 3, tarihli: bool = False) -> KeepTogether:
    """imzalar: [(unvan, ad_soyad)]"""
    satirlar, satir = [], []
    for unvan, ad in imzalar:
        metin = f"{'..../..../20....<br/>' if tarihli else ''}<br/><br/><b>{ad or '....................'}</b><br/>{unvan}"
        satir.append(P(metin, S_ORTA))
        if len(satir) == sutun:
            satirlar.append(satir)
            satir = []
    if satir:
        satir += [""] * (sutun - len(satir))
        satirlar.append(satir)
    t = Table(satirlar, colWidths=[170 * mm / sutun] * sutun)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 10)]))
    return KeepTogether([Spacer(1, 6 * mm), t])


def olustur(yol: Path, parcalar: list, yatay: bool = False, baslik: str = "DÖSE Belgesi") -> Path:
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    boyut = landscape(A4) if yatay else A4

    def alt_bilgi(canvas, doc):
        canvas.saveState()
        canvas.setFont(_FONT, 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(15 * mm, 8 * mm, f"{UYGULAMA_ADI} - {date.today():%d.%m.%Y}")
        canvas.drawRightString(boyut[0] - 15 * mm, 8 * mm, f"Sayfa {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(yol), pagesize=boyut, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm, title=baslik, author=UYGULAMA_ADI)
    doc.build(parcalar, onFirstPage=alt_bilgi, onLaterPages=alt_bilgi)
    return yol


__all__ = ["P", "S_NORMAL", "S_KUCUK", "S_METIN", "S_ORTA", "S_ORTA_B", "S_SAG", "S_BASLIK", "S_ALT_BASLIK",
           "antet", "tablo", "bilgi_tablosu", "imza_blogu", "olustur", "tarih_tr", "Spacer", "PageBreak", "mm"]
