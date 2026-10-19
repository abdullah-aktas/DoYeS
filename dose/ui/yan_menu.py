"""Açılır-kapanır (accordion) yan menü: grup başlıkları genişler/daralır; daraltılmış kipte yalnız ikon şeridi."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

GENISLIK_ACIK = 268
GENISLIK_KAPALI = 56

# Grup kısa ikonları (daraltılmış menüde)
GRUP_IKON = {
    "GENEL": "🏠",
    "YARDIM VE DENETİM": "📘",
    "TANIMLAR": "📋",
    "ÜRETİM VE TİCARET": "🏭",
    "PERSONEL ÖDEMELERİ": "👥",
    "YASAL YÜKÜMLÜLÜKLER": "⚖",
    "MUHASEBE VE RAPORLAR": "📊",
    "SİSTEM": "⚙",
}


class YanMenu(QWidget):
    """Gruplu açılır-kapanır menü. sayfa_secildi(menu_adi) yayar."""

    sayfa_secildi = Signal(str)
    genislik_degisti = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("yanPanel")
        self._acik = True
        self._gruplar: dict[str, QTreeWidgetItem] = {}
        self._sayfa_satir: dict[str, QTreeWidgetItem] = {}
        self._sayfa_grup: dict[str, str] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        baslik = QFrame()
        baslik.setObjectName("menuBaslik")
        b_lay = QHBoxLayout(baslik)
        b_lay.setContentsMargins(10, 10, 6, 10)
        self.l_baslik = QLabel("DÖSE\nYönetim")
        self.l_baslik.setObjectName("menuBaslikYazi")
        self.l_baslik.setWordWrap(True)
        b_lay.addWidget(self.l_baslik, 1)
        self.b_daralt = QPushButton("«")
        self.b_daralt.setObjectName("menuDaralt")
        self.b_daralt.setFixedSize(28, 28)
        self.b_daralt.setToolTip("Menüyü daralt / genişlet")
        self.b_daralt.clicked.connect(self.toggle)
        b_lay.addWidget(self.b_daralt, 0, Qt.AlignTop)
        lay.addWidget(baslik)

        self.agac = QTreeWidget()
        self.agac.setObjectName("yanMenu")
        self.agac.setHeaderHidden(True)
        self.agac.setIndentation(14)
        self.agac.setRootIsDecorated(True)
        self.agac.setAnimated(True)
        self.agac.setExpandsOnDoubleClick(False)
        self.agac.setFocusPolicy(Qt.NoFocus)
        self.agac.itemClicked.connect(self._tiklandi)
        self.agac.itemActivated.connect(self._tiklandi)
        lay.addWidget(self.agac, 1)

        self.setFixedWidth(GENISLIK_ACIK)

    def doldur(self, sayfalar: list[tuple], yetki_fn):
        """sayfalar: [(grup, ad, modul, sinif), ...]; yetki_fn(ad) truthy ise menüde gösterilir."""
        self.agac.clear()
        self._gruplar.clear()
        self._sayfa_satir.clear()
        self._sayfa_grup.clear()
        grup_adi = None
        grup_item = None
        for g, ad, _m, _s in sayfalar:
            if not yetki_fn(ad):
                continue
            if g != grup_adi:
                grup_adi = g
                ikon = GRUP_IKON.get(g, "▸")
                grup_item = QTreeWidgetItem([f"{ikon}  {g}"])
                grup_item.setData(0, Qt.UserRole, ("grup", g))
                f = QFont(grup_item.font(0))
                f.setBold(True)
                f.setPointSize(8)
                grup_item.setFont(0, f)
                grup_item.setFlags(Qt.ItemIsEnabled)
                self.agac.addTopLevelItem(grup_item)
                self._gruplar[g] = grup_item
                # İlk grup (GENEL) açık; diğerleri kapalı — daha sade görünüm
                grup_item.setExpanded(g == "GENEL")
            sayfa = QTreeWidgetItem([ad])
            sayfa.setData(0, Qt.UserRole, ("sayfa", ad))
            sayfa.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            grup_item.addChild(sayfa)
            self._sayfa_satir[ad] = sayfa
            self._sayfa_grup[ad] = g
        self._gorunum_guncelle()

    def _tiklandi(self, item: QTreeWidgetItem, _sutun: int = 0):
        if item is None:
            return
        veri = item.data(0, Qt.UserRole) or (None, None)
        tur, deger = veri[0], veri[1]
        if tur == "grup":
            item.setExpanded(not item.isExpanded())
            return
        if tur == "sayfa":
            self.agac.setCurrentItem(item)
            self.sayfa_secildi.emit(deger)

    def sec(self, menu_adi: str) -> bool:
        it = self._sayfa_satir.get(menu_adi)
        if not it:
            return False
        g = self._sayfa_grup.get(menu_adi)
        if g and g in self._gruplar:
            self._gruplar[g].setExpanded(True)
        self.agac.setCurrentItem(it)
        it.setSelected(True)
        return True

    def aktif_sayfa(self) -> str | None:
        it = self.agac.currentItem()
        if not it:
            return None
        veri = it.data(0, Qt.UserRole) or (None, None)
        return veri[1] if veri[0] == "sayfa" else None

    def toggle(self):
        self._acik = not self._acik
        self._gorunum_guncelle()
        self.genislik_degisti.emit(self.width())

    def _gorunum_guncelle(self):
        w = GENISLIK_ACIK if self._acik else GENISLIK_KAPALI
        self.setFixedWidth(w)
        self.l_baslik.setVisible(self._acik)
        self.b_daralt.setText("«" if self._acik else "»")
        self.agac.setRootIsDecorated(self._acik)
        # Daraltılmışken grup metnini kısalt
        for g, item in self._gruplar.items():
            ikon = GRUP_IKON.get(g, "▸")
            item.setText(0, f"{ikon}  {g}" if self._acik else ikon)
            item.setToolTip(0, g)
            for i in range(item.childCount()):
                ch = item.child(i)
                ch.setHidden(not self._acik)
        if not self._acik:
            for item in self._gruplar.values():
                item.setExpanded(False)
