"""Adım adım iş rehberleri: 'Ne yapmak istiyorsunuz?' sorusuna hangi sayfada, hangi düğmeyle, kimin yapacağı cevabı."""
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QScrollArea, QSplitter,
                               QVBoxLayout, QWidget)

from ... import kilavuz
from ..ortak import Oturum, baslik_etiketi, buton


def _etiket(metin: str, nesne: str | None = None, stil: str = "") -> QLabel:
    e = QLabel(metin)
    e.setWordWrap(True)
    e.setTextFormat(Qt.RichText)
    if nesne:
        e.setObjectName(nesne)
    if stil:
        e.setStyleSheet(stil)
    return e


class KilavuzSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "Nasıl Yaparım? (Adım Adım)",
            "Yapmak istediğiniz işi soldan seçin. Her adımda hangi sayfaya gidip hangi düğmeye basacağınız ve işi kimin "
            "yapacağı yazar; 'Git' düğmesi ilgili sayfayı açar."))
        bol = QSplitter(Qt.Horizontal)
        sol = QWidget()
        sl = QVBoxLayout(sol)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(QLabel("<b>Ne yapmak istiyorsunuz?</b>"))
        self.liste = QListWidget()
        self.liste.setStyleSheet("QListWidget::item { padding: 8px 4px; }")
        self.liste.currentItemChanged.connect(lambda it, _o: self.goster(it.data(Qt.UserRole)) if it else None)
        sl.addWidget(self.liste)
        self.tumu = QCheckBox("Diğer rollerin rehberlerini de göster")
        self.tumu.toggled.connect(self._listele)
        sl.addWidget(self.tumu)
        bol.addWidget(sol)
        self.kaydir = QScrollArea()
        self.kaydir.setWidgetResizable(True)
        self.kaydir.setFrameShape(QFrame.NoFrame)
        bol.addWidget(self.kaydir)
        bol.setSizes([300, 900])
        lay.addWidget(bol)
        self._listele()

    def _listele(self):
        secili = self.liste.currentItem().data(Qt.UserRole) if self.liste.currentItem() else None
        rehberler = kilavuz.rol_rehberleri(Oturum.rol())
        if self.tumu.isChecked():
            rehberler += [r for r in kilavuz.IS_REHBERLERI if r not in rehberler]
        self.liste.blockSignals(True)
        self.liste.clear()
        for r in rehberler:
            it = QListWidgetItem(f"{r.ikon}  {r.baslik}")
            it.setData(Qt.UserRole, r.kod)
            it.setToolTip(r.ozet)
            self.liste.addItem(it)
        self.liste.blockSignals(False)
        if not self._sec_satir(secili) and rehberler:
            self._sec_satir(rehberler[0].kod)

    def _sec_satir(self, kod: str | None) -> bool:
        for i in range(self.liste.count()):
            if kod and self.liste.item(i).data(Qt.UserRole) == kod:
                self.liste.setCurrentRow(i)
                return True
        return False

    def sec(self, kod: str | None):
        """Rehberi açar; rolün listesinde yoksa diğer rollerin rehberlerini de gösterir."""
        if self._sec_satir(kod) or kod not in kilavuz.REHBER or self.tumu.isChecked():
            return
        self.tumu.setChecked(True)
        self._sec_satir(kod)

    def goster(self, kod: str):
        r = kilavuz.REHBER.get(kod)
        if not r:
            return
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 4, 12, 12)
        v.addWidget(_etiket(f"<span style='font-size:16pt; font-weight:600; color:#1f4e79'>{r.ikon} {escape(r.baslik)}</span>"))
        v.addWidget(_etiket(escape(r.ozet), stil="color:#555"))
        v.addWidget(_etiket("<b>Kimler için:</b> " + escape(", ".join(r.roller))))
        if Oturum.rol() not in r.roller:
            v.addWidget(_etiket("Bu iş sizin rolünüzün doğrudan görevi değildir; bilgi amaçlı gösteriliyor.", "uyariKutusu"))
        v.addWidget(_etiket("<b>Adımlar</b>", stil="font-size:12pt; color:#1f4e79; margin-top:8px"))
        for i, a in enumerate(r.adimlar, 1):
            kutu = QFrame()
            kutu.setObjectName("kart")
            h = QHBoxLayout(kutu)
            h.setContentsMargins(8, 6, 8, 6)
            no = _etiket(f"<span style='font-size:14pt; font-weight:700; color:#2e75b6'>{i}</span>")
            no.setFixedWidth(28)
            no.setAlignment(Qt.AlignTop)
            h.addWidget(no)
            ek = []
            if a.sayfa:
                ek.append(f"📍 {escape(a.sayfa)}")
            if a.kim:
                ek.append(f"👤 {escape(a.kim)}")
            h.addWidget(_etiket(escape(a.metin) + (f"<br><span style='color:#5a6675; font-size:9pt'>{'   '.join(ek)}</span>"
                                                   if ek else "")), 1)
            if a.sayfa and Oturum.sayfa_yetkisi(a.sayfa):
                h.addWidget(buton("Git →", lambda _=False, s=a.sayfa: self._git(s), ipucu=f"'{a.sayfa}' sayfasını açar"),
                            0, Qt.AlignTop)
            v.addWidget(kutu)
        if r.yasaklar:
            v.addWidget(_etiket("<b>⛔ Asla yapmayın</b><br>" + "<br>".join("• " + escape(y) for y in r.yasaklar), "hataKutusu"))
        if r.risk:
            v.addWidget(_etiket("<b>⚖ Yanlış yapılırsa ne olur?</b><br>" + escape(r.risk), "uyariKutusu"))
        if r.dayanak:
            v.addWidget(_etiket("<b>Dayanak:</b> " + escape(r.dayanak), stil="color:#555"))
        v.addWidget(_etiket(f"<i>{escape(kilavuz.GENEL_UYARI)}</i>", stil="color:#777; font-size:9pt"))
        v.addStretch()
        self.kaydir.setWidget(w)

    def _git(self, sayfa: str):
        ana = getattr(self, "ana_pencere", None)
        if ana is not None:
            ana.sayfaya_git(sayfa)
