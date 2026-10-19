"""Lisans durumu ve lisans anahtarı girişi."""
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton, QVBoxLayout)

from .. import lisans
from ..db import al as db
from .ortak import bilgi, hata

RENKLER = {"iyi": "background:#e8f5e9; color:#1b5e20;", "uyari": "background:#fff8e1; color:#8a5a00;",
           "kotu": "background:#fdecea; color:#a61b1b;"}


def durum_rengi(d: lisans.Durum) -> str:
    if not d.yazilabilir:
        return RENKLER["kotu"]
    return RENKLER["uyari"] if d.uyari else RENKLER["iyi"]


class LisansDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lisans")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        self.l_durum = QLabel()
        self.l_durum.setWordWrap(True)
        lay.addWidget(self.l_durum)

        g = QGroupBox("Bu kurumun bilgileri (lisans talebinde satıcıya iletin)")
        f = QFormLayout(g)
        self.l_okul = QLabel()
        self.l_kod = QLabel()
        f.addRow("Okul adı:", self.l_okul)
        f.addRow("Kurum kodu:", self.l_kod)
        b_kopyala = QPushButton("Bilgileri kopyala")
        b_kopyala.clicked.connect(self._bilgi_kopyala)
        f.addRow("", b_kopyala)
        lay.addWidget(g)

        self.g_lisans = QGroupBox("Kayıtlı lisans")
        self.f_lisans = QFormLayout(self.g_lisans)
        lay.addWidget(self.g_lisans)

        lay.addWidget(QLabel("Lisans anahtarı:"))
        self.anahtar = QPlainTextEdit()
        self.anahtar.setPlaceholderText("Size gönderilen DOSE1.… ile başlayan anahtarı buraya yapıştırın veya .lic dosyasını yükleyin.")
        self.anahtar.setMaximumHeight(90)
        lay.addWidget(self.anahtar)
        n = QLabel(f"Program sahibi, lisans ve destek: <b>{lisans.SATICI}</b>"
                   + (f"<br>{lisans.SATICI_ILETISIM}" if lisans.SATICI_ILETISIM else ""))
        n.setStyleSheet("color:#555")
        n.setWordWrap(True)
        lay.addWidget(n)

        u = QHBoxLayout()
        b_dosya = QPushButton("Dosyadan yükle…")
        b_dosya.clicked.connect(self._dosyadan)
        b_etkin = QPushButton("Etkinleştir")
        b_etkin.setObjectName("birincil")
        b_etkin.clicked.connect(self._etkinlestir)
        b_kapat = QPushButton("Kapat")
        b_kapat.clicked.connect(self.accept)
        u.addWidget(b_dosya)
        u.addStretch()
        u.addWidget(b_etkin)
        u.addWidget(b_kapat)
        lay.addLayout(u)
        self._guncelle()

    def _guncelle(self):
        d = lisans.uygula(db())
        self.l_durum.setText(f"<b>{d.ozet}</b>")
        self.l_durum.setStyleSheet(durum_rengi(d) + "padding:8px; border-radius:4px;")
        k = db().kurum()
        self.l_okul.setText(k.get("okul_adi") or "-")
        kod = lisans.kurum_kodu_normalize(k.get("kurum_kodu"))
        self.l_kod.setText(kod or "<i>girilmemiş — lisans ilk etkinleştirmede kurum koduna bağlanır</i>")
        while self.f_lisans.rowCount():
            self.f_lisans.removeRow(0)
        lis = d.lisans
        self.g_lisans.setVisible(lis is not None)
        if lis:
            for etiket, deger in (("Lisans no:", lis.no), ("Okul:", lis.okul), ("Kurum kodu:", lis.kurum_kodu),
                                  ("Tür:", lis.tur), ("Veriliş:", lis.verilis.strftime("%d.%m.%Y")),
                                  ("Bitiş:", lis.bitis_metni())):
                self.f_lisans.addRow(etiket, QLabel(deger))

    def _bilgi_kopyala(self):
        k = db().kurum()
        QApplication.clipboard().setText(f"Okul adı: {k.get('okul_adi') or ''}\n"
                                         f"Kurum kodu: {lisans.kurum_kodu_normalize(k.get('kurum_kodu'))}\n"
                                         f"İl / İlçe: {k.get('il') or ''} / {k.get('ilce') or ''}")
        bilgi(self, "Bilgiler panoya kopyalandı; e-posta veya mesaja yapıştırabilirsiniz.")

    def _dosyadan(self):
        yol, _ = QFileDialog.getOpenFileName(self, "Lisans dosyası", "", "Lisans dosyası (*.lic *.txt);;Tüm dosyalar (*)")
        if yol:
            try:
                with open(yol, encoding="utf-8-sig") as f:
                    self.anahtar.setPlainText(f.read().strip())
            except OSError as e:
                hata(self, f"Dosya okunamadı:\n{e}")

    def _etkinlestir(self):
        metin = self.anahtar.toPlainText().strip()
        if not metin:
            hata(self, "Lisans anahtarını yapıştırın veya dosyadan yükleyin.")
            return
        try:
            lis = lisans.etkinlestir(db(), metin)
        except lisans.LisansHatasi as e:
            hata(self, str(e))
            return
        except Exception as e:
            hata(self, f"Lisans kaydedilemedi:\n{e}")
            return
        self.anahtar.clear()
        self._guncelle()
        bilgi(self, f"Lisans etkinleştirildi.\n\n{lis.okul}\nBitiş: {lis.bitis_metni()}")
