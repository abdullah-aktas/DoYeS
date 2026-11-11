"""PDF tablolarından tanım satırı çıkarma (metin tabanlı PDF; tarama/OCR yok)."""
from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from . import excel as X


def _pdf_ac(yol: Path | None = None, veri: bytes | None = None):
    try:
        import pdfplumber
    except ImportError as e:
        raise ValueError("PDF okumak için pdfplumber kurulmalı (pip install pdfplumber).") from e
    if veri is not None:
        if not veri:
            raise ValueError("PDF dosyası boş.")
        return pdfplumber.open(BytesIO(veri))
    if yol is None:
        raise ValueError("PDF dosyası veya içeriği verilmedi.")
    yol = Path(yol)
    if not yol.is_file():
        raise ValueError("PDF dosyası bulunamadı.")
    return pdfplumber.open(str(yol))


def _metin_satiri_parcala(satir: str) -> list[str]:
    satir = (satir or "").strip()
    if not satir:
        return []
    if "\t" in satir:
        return [p.strip() for p in satir.split("\t") if p.strip()]
    if "|" in satir:
        return [p.strip() for p in satir.split("|") if p.strip()]
    # İki veya daha fazla boşlukla hizalanmış sütunlar
    parcalar = [p.strip() for p in re.split(r"\s{2,}", satir) if p.strip()]
    if len(parcalar) >= 2:
        return parcalar
    return []


def pdf_tablolari(yol: Path | None = None, veri: bytes | None = None) -> list[list]:
    """Tüm sayfalardaki tabloları satır listesine birleştirir."""
    satirlar: list[list] = []
    with _pdf_ac(yol=yol, veri=veri) as pdf:
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
                    parcalar = _metin_satiri_parcala(satir)
                    if len(parcalar) >= 2:
                        satirlar.append(parcalar)
    if not satirlar:
        raise ValueError(
            "PDF'de tablo bulunamadı. Tarama (görüntü) PDF için sayfayı PNG/JPG olarak kaydedip "
            "yükleyin, «Metin / sesle yaz» kullanın veya metin seçilebilir tablo / Excel şablonu yükleyin.")
    return satirlar


def tanim_oku_pdf(yol: Path | None = None, tablo: str = "", veri: bytes | None = None) -> list[dict]:
    esler = X.TABLO_ICE_AKTARMA.get(tablo)
    if not esler:
        raise ValueError(f"Bu tablo için PDF içe aktarma yok: {tablo}")
    kayitlar = X.satir_listesinden_oku(pdf_tablolari(yol=yol, veri=veri), esler)
    if not kayitlar:
        raise ValueError(
            "PDF'de eşleşen satır bulunamadı. «Şablon» başlıklarını kullanın. "
            f"Örnek: {X.beklenen_basliklar(tablo)}")
    return kayitlar
