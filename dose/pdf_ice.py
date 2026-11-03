"""PDF tablolarından tanım satırı çıkarma (metin tabanlı PDF; tarama/OCR yok)."""
from __future__ import annotations

from pathlib import Path

from . import excel as X


def pdf_tablolari(yol: Path) -> list[list]:
    """Tüm sayfalardaki tabloları satır listesine birleştirir."""
    try:
        import pdfplumber
    except ImportError as e:
        raise ValueError("PDF okumak için pdfplumber kurulmalı (pip install pdfplumber).") from e
    yol = Path(yol)
    if not yol.is_file():
        raise ValueError("PDF dosyası bulunamadı.")
    satirlar: list[list] = []
    with pdfplumber.open(str(yol)) as pdf:
        if not pdf.pages:
            raise ValueError("PDF boş.")
        for sayfa in pdf.pages:
            tablolar = sayfa.extract_tables() or []
            for tablo in tablolar:
                for satir in tablo or []:
                    if satir and any(hucre not in (None, "") for hucre in satir):
                        satirlar.append([(hucre if hucre is not None else "") for hucre in satir])
            if not tablolar:
                metin = sayfa.extract_text() or ""
                for satir in metin.splitlines():
                    parcalar = [p.strip() for p in satir.split("\t") if p.strip()]
                    if len(parcalar) >= 2:
                        satirlar.append(parcalar)
    if not satirlar:
        raise ValueError(
            "PDF'de tablo bulunamadı. Tarama (görüntü) PDF desteklenmez; Excel şablonu kullanın "
            "veya metin seçilebilir tablo içeren PDF yükleyin.")
    return satirlar


def tanim_oku_pdf(yol: Path, tablo: str) -> list[dict]:
    esler = X.TABLO_ICE_AKTARMA.get(tablo)
    if not esler:
        raise ValueError(f"Bu tablo için PDF içe aktarma yok: {tablo}")
    return X.satir_listesinden_oku(pdf_tablolari(yol), esler)
