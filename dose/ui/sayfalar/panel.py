"""Gösterge paneli: özet göstergeler, yasal süre ve mevzuat uyarıları."""
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget
from PySide6.QtGui import QColor

from ... import gosterge
from ...hesap import para
from ..ortak import Kart, Oturum, baslik_etiketi, buton


class PanelSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi("Gösterge Paneli", "Çalışma yılına ait özet göstergeler, yaklaşan yasal süreler ve mevzuat uyarıları."))
        izgara = QGridLayout()
        self.kartlar = {}
        for i, (a, e) in enumerate([("satis", "Satış (KDV hariç)"), ("tahsilat", "Tahsilat"), ("nakit", "Kasa + Banka"),
                                    ("alacak", "Açık alacaklar"), ("siparis", "Açık siparişler"), ("kar", "Yardımcı defter kârı"),
                                    ("stok", "Stok değeri"), ("hazine", "Ödenmemiş hazine payı")]):
            self.kartlar[a] = Kart(e)
            izgara.addWidget(self.kartlar[a], i // 4, i % 4)
        lay.addLayout(izgara)
        hizli = QHBoxLayout()
        for ad in ("Siparişler / İş Emirleri", "Satış Faturaları", "Alış / Gider Belgeleri", "Kasa / Banka", "Parça Başı Ücret",
                   "Hazine Payı / SHÇEK"):
            hizli.addWidget(buton(ad, lambda _=False, a=ad: self._git(a)))
        hizli.addStretch()
        lay.addLayout(hizli)
        lay.addWidget(QLabel("<b>Uyarılar ve yaklaşan yükümlülükler</b> (çift tıklayarak ilgili sayfaya gidebilirsiniz)"))
        self.liste = QListWidget()
        self.liste.itemDoubleClicked.connect(lambda it: self._git(it.data(256)) if it.data(256) else None)
        lay.addWidget(self.liste)
        self.yenile()

    def _git(self, ad):
        if hasattr(self, "ana_pencere"):
            self.ana_pencere.sayfaya_git(ad)

    def _uyari(self, metin, seviye="bilgi", sayfa=None):
        it = QListWidgetItem(("⛔ " if seviye == "hata" else "⚠ " if seviye == "uyari" else "ℹ ") + metin)
        it.setForeground(QColor({"hata": "#b00020", "uyari": "#8a5a00", "bilgi": "#1f4e79"}[seviye]))
        if sayfa:
            it.setData(256, sayfa)
        self.liste.addItem(it)

    def yenile(self):
        yil = Oturum.yil
        o = gosterge.ozet(yil)
        self.kartlar["satis"].ayarla(para(o["satis"]) + " TL", f"{yil}")
        self.kartlar["tahsilat"].ayarla(para(o["tahsilat"]) + " TL", f"{yil}")
        self.kartlar["nakit"].ayarla(para(o["nakit"]) + " TL", "tüm zamanlar")
        self.kartlar["alacak"].ayarla(para(o["alacak"]) + " TL")
        self.kartlar["siparis"].ayarla(str(o["acik_siparis"]))
        self.kartlar["kar"].ayarla(para(o["kar"]) + " TL", f"Gelir {para(o['toplam_gelir'])} / Gider {para(o['toplam_gider'])}")
        self.kartlar["stok"].ayarla(para(o["stok"]) + " TL")
        self.kartlar["hazine"].ayarla(para(o["hazine_odenmemis"]) + " TL")
        self.liste.clear()
        for metin, seviye, sayfa in gosterge.uyarilar(yil):
            self._uyari(metin, seviye, sayfa)
        if self.liste.count() == 0:
            self._uyari("Bekleyen uyarı yok.")
