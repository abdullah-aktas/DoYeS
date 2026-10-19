"""Ortak logo ve ikon: tüm pencerelerde aynı görseller (`dose/gorsel`)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QLabel

from ..yollar import GORSEL

LOGO = GORSEL / "logo.png"
IKON = GORSEL / "ikon.png"
IKON_ICO = GORSEL / "ikon.ico"


def ikon() -> QIcon:
    for yol in (IKON_ICO, IKON, LOGO):
        if yol.exists():
            return QIcon(str(yol))
    return QIcon()


def logo_pixmap(genislik: int = 380) -> QPixmap:
    pm = QPixmap(str(LOGO)) if LOGO.exists() else QPixmap()
    if pm.isNull() and IKON.exists():
        pm = QPixmap(str(IKON))
    if not pm.isNull() and genislik > 0 and pm.width() > genislik:
        pm = pm.scaledToWidth(genislik, Qt.SmoothTransformation)
    return pm


def logo_etiket(parent=None, genislik: int = 380) -> QLabel | None:
    pm = logo_pixmap(genislik)
    if pm.isNull():
        return None
    et = QLabel(parent)
    et.setPixmap(pm)
    et.setAlignment(Qt.AlignCenter)
    et.setMinimumHeight(pm.height() + 4)
    et.setObjectName("markaLogo")
    return et


def kucuk_logo(genislik: int = 36) -> QPixmap:
    pm = QPixmap(str(IKON if IKON.exists() else LOGO))
    if pm.isNull():
        return pm
    return pm.scaled(genislik, genislik, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def gorsel_yolu(ad: str = "logo.png") -> Path:
    return GORSEL / ad
