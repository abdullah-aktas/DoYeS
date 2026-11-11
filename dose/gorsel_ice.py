"""Belge resmi / tarama PDF metin çıkarma ve satır eşleme (OCR isteğe bağlı)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import excel as X
from . import pdf_ice


GORSEL_UZANTILAR = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp")


def gorsel_mi(ad: str | None = None, yol: Path | None = None) -> bool:
    ad_k = (ad or (yol.name if yol else "") or "").lower()
    return any(ad_k.endswith(u) for u in GORSEL_UZANTILAR)


def _uzanti_tahmin(veri: bytes, ad: str = "") -> str:
    ad_k = (ad or "").lower()
    for u in GORSEL_UZANTILAR:
        if ad_k.endswith(u):
            return u
    if veri[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if len(veri) >= 8 and veri[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if veri[:4] == b"RIFF" and b"WEBP" in veri[:16]:
        return ".webp"
    if veri[:2] == b"BM":
        return ".bmp"
    return ".png"


def metin_cikar(yol: Path | None = None, veri: bytes | None = None, ad: str = "") -> str:
    """Görüntüden metin çıkarır. Önce Tesseract (kuruluysa), yoksa anlamlı hata."""
    if not yol and not veri:
        raise ValueError("Görüntü dosyası veya içeriği verilmedi.")
    tmp: Path | None = None
    try:
        if veri is not None:
            if not veri:
                raise ValueError("Görüntü dosyası boş.")
            fd, tmp_yol = tempfile.mkstemp(suffix=_uzanti_tahmin(veri, ad))
            os.close(fd)
            tmp = Path(tmp_yol)
            tmp.write_bytes(veri)
            hedef = tmp
        else:
            hedef = Path(yol)  # type: ignore[arg-type]
            if not hedef.is_file():
                raise ValueError("Görüntü dosyası bulunamadı.")
        return _tesseract_oku(hedef)
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def _tesseract_oku(yol: Path) -> str:
    exe = shutil.which("tesseract")
    if not exe:
        raise ValueError(
            "Belge resminden otomatik okuma için bu cihazda Tesseract OCR kurulu olmalı "
            "(https://github.com/tesseract-ocr/tesseract). "
            "Kurulu değilse «Metin / sesle yaz» ile satırları yapıştırın veya dikte edin.")
    denenen = []
    for dil in ("tur+eng", "eng", None):
        cmd = [exe, str(yol), "stdout"]
        if dil:
            cmd.extend(["-l", dil])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ValueError(f"OCR çalıştırılamadı: {e}") from e
        metin = (r.stdout or "").strip()
        if metin:
            return metin
        denenen.append(dil or "varsayılan")
        if r.returncode != 0 and dil is None:
            err = (r.stderr or "").strip() or f"çıkış kodu {r.returncode}"
            raise ValueError(f"OCR başarısız ({err}). Görüntüyü netleştirip yeniden deneyin.")
    raise ValueError(
        "OCR metin bulamadı. Daha net bir fotoğraf yükleyin veya «Metin / sesle yaz» kullanın.")


def metinden_satirlar(metin: str) -> list[list]:
    """Yapıştırılan / OCR / ses metnini tablo satırlarına böler."""
    satirlar: list[list] = []
    for satir in (metin or "").splitlines():
        parcalar = pdf_ice._metin_satiri_parcala(satir)
        if len(parcalar) >= 2:
            satirlar.append(parcalar)
        elif satir.strip() and "\t" not in satir and "|" not in satir:
            # Tek sütun satırları (başlık listesi) atlanır; virgüllü CSV dene
            if ";" in satir or (satir.count(",") >= 2):
                ayir = ";" if satir.count(";") >= satir.count(",") else ","
                parcalar = [p.strip() for p in satir.split(ayir) if p.strip()]
                if len(parcalar) >= 2:
                    satirlar.append(parcalar)
    return satirlar


def tanim_oku_metin(metin: str, tablo: str) -> list[dict]:
    esler = X.TABLO_ICE_AKTARMA.get(tablo)
    if not esler:
        raise ValueError(f"Bu tablo için metin içe aktarma yok: {tablo}")
    satirlar = metinden_satirlar(metin)
    if not satirlar:
        raise ValueError(
            "Metinde tablo satırı bulunamadı. Başlıkları ve değerleri boşluk/sekme veya "
            f"virgülle ayırın. Örnek: {X.beklenen_basliklar(tablo)}")
    kayitlar = X.satir_listesinden_oku(satirlar, esler)
    if not kayitlar:
        raise ValueError(
            "Metinde eşleşen satır bulunamadı. «Şablon» başlıklarını kullanın. "
            f"Örnek: {X.beklenen_basliklar(tablo)}")
    return kayitlar


def tanim_oku_gorsel(yol: Path | None = None, tablo: str = "", veri: bytes | None = None,
                     ad: str = "") -> list[dict]:
    return tanim_oku_metin(metin_cikar(yol=yol, veri=veri, ad=ad), tablo)


def fatura_alanlari_cikar(metin: str) -> dict[str, str]:
    """Fatura / fiş metninden belge no, tarih ve tutar adaylarını çıkarır."""
    m = metin or ""
    sonuc: dict[str, str] = {}
    for desen in (
        r"(?:fatura|belge|e[-\s]?fatura)\s*(?:no|numara|numarası|nu)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/]{2,})",
        r"\b(?:FT|FTR|GIB|GIBN)[A-Z0-9\-/]{4,}\b",
        r"\b\d{4}[A-Z]{1,3}\d{6,}\b",
    ):
        b = re.search(desen, m, re.I)
        if b:
            sonuc["belge_no"] = (b.group(1) if b.lastindex else b.group(0)).strip()
            break
    t = re.search(r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b", m)
    if t:
        sonuc["tarih"] = t.group(1).replace("-", ".")
    for desen in (
        r"(?:ödenecek\s*tutar|genel\s*toplam|toplam\s*tutar|net\s*tutar)\s*[:]?[\s]*([\d.\s]+,\d{2})",
        r"(?:ödenecek\s*tutar|genel\s*toplam|toplam)\s*[:]?[\s]*([\d,]+(?:\.\d{2})?)",
    ):
        u = re.search(desen, m, re.I)
        if u:
            sonuc["tutar"] = re.sub(r"\s+", "", u.group(1))
            break
    return sonuc
