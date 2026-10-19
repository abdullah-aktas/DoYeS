"""Satıcı lisans üretme aracı (yalnız satıcının bilgisayarında çalışır, programla dağıtılmaz).

Okul adı ve MEB kurum kodu girilerek imzalı lisans anahtarı üretilir. Anahtar metin olarak kopyalanabilir veya .lic
dosyası olarak kaydedilip okula gönderilebilir. Üretilen her lisans lisanslar.csv satış kaydına eklenir.
"""
import csv
import os
import sys
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QApplication, QComboBox, QDateEdit, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR.parent))

from dose import lisans  # noqa: E402

OZEL = KLASOR / "ozel_anahtar.pem"
KAYIT = KLASOR / "lisanslar.csv"
LIC_KLASORU = KLASOR / "lisanslar"
KOLONLAR = ["no", "tarih", "okul", "kurum_kodu", "tur", "bitis", "ucret", "fatura_no", "iletisim", "not", "anahtar"]
SURELER = [("1 yıl", 1), ("2 yıl", 2), ("3 yıl", 3), ("Süresiz", 0), ("Özel tarih", -1)]
SUREKLI = lisans.SUREKLI


def yil_ekle(t: date, n: int) -> date:
    try:
        return t.replace(year=t.year + n)
    except ValueError:
        return t.replace(year=t.year + n, day=28)


def kayitlari_oku() -> list[dict]:
    if not KAYIT.exists():
        return []
    with KAYIT.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def kayit_ekle(satir: dict):
    yeni = not KAYIT.exists()
    with KAYIT.open("a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KOLONLAR, delimiter=";")
        if yeni:
            w.writeheader()
        w.writerow(satir)


def sonraki_no() -> str:
    yil = date.today().year
    onek = f"L-{yil}-"
    sayilar = [int(k["no"][len(onek):]) for k in kayitlari_oku() if k.get("no", "").startswith(onek)
               and k["no"][len(onek):].isdigit()]
    return f"{onek}{max(sayilar, default=0) + 1:04d}"


class Pencere(QWidget):
    def __init__(self, ozel):
        super().__init__()
        self.ozel = ozel
        self.acik = lisans._b64(ozel.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        self.setWindowTitle("DÖSE Yönetim Sistemi - Lisans Üretici (satıcı)")
        self.resize(1000, 720)
        lay = QVBoxLayout(self)
        if self.acik != lisans.ACIK_ANAHTAR:
            u = QLabel("⚠ Bu özel anahtar, dose/lisans.py içindeki açık anahtarla eşleşmiyor. Üreteceğiniz lisanslar "
                       "mevcut EXE'de çalışmaz. 'python satici/anahtar_olustur.py' çalıştırıp EXE'yi yeniden oluşturun.")
            u.setWordWrap(True)
            u.setStyleSheet("background:#fdecea; color:#a61b1b; padding:8px;")
            lay.addWidget(u)

        g = QGroupBox("Yeni lisans")
        f = QFormLayout(g)
        self.okul = QLineEdit()
        self.okul.setPlaceholderText("Örn: Atatürk Mesleki ve Teknik Anadolu Lisesi")
        self.kod = QLineEdit()
        self.kod.setPlaceholderText("MEB kurum kodu (okulun programda 'Kurum ve Görevliler' sayfasındaki kod)")
        self.sure = QComboBox()
        for ad, n in SURELER:
            self.sure.addItem(ad, n)
        self.bitis = QDateEdit(QDate.currentDate().addYears(1))
        self.bitis.setCalendarPopup(True)
        self.bitis.setDisplayFormat("dd.MM.yyyy")
        self.sure.currentIndexChanged.connect(self._sure_degisti)
        sure_lay = QHBoxLayout()
        sure_lay.addWidget(self.sure)
        sure_lay.addWidget(QLabel("Bitiş:"))
        sure_lay.addWidget(self.bitis)
        sure_lay.addStretch()
        self.ucret = QDoubleSpinBox()
        self.ucret.setRange(0, 1e9)
        self.ucret.setDecimals(2)
        self.ucret.setSuffix(" TL")
        self.fatura = QLineEdit()
        self.iletisim = QLineEdit()
        self.iletisim.setPlaceholderText("Yetkili adı, telefon, e-posta")
        self.notlar = QLineEdit()
        f.addRow("Okul adı:", self.okul)
        f.addRow("Kurum kodu:", self.kod)
        f.addRow("Süre:", sure_lay)
        f.addRow("Ücret:", self.ucret)
        f.addRow("Fatura no:", self.fatura)
        f.addRow("İletişim:", self.iletisim)
        f.addRow("Not:", self.notlar)
        lay.addWidget(g)

        b = QHBoxLayout()
        b_uret = QPushButton("Lisans üret")
        b_uret.setStyleSheet("font-weight:bold; padding:6px 18px;")
        b_uret.clicked.connect(self.uret)
        b_kopyala = QPushButton("Anahtarı kopyala")
        b_kopyala.clicked.connect(self.kopyala)
        b_klasor = QPushButton("Lisans dosyaları klasörü")
        b_klasor.clicked.connect(lambda: (LIC_KLASORU.mkdir(exist_ok=True), os.startfile(str(LIC_KLASORU))))
        for w in (b_uret, b_kopyala, b_klasor):
            b.addWidget(w)
        b.addStretch()
        lay.addLayout(b)

        self.cikti = QPlainTextEdit()
        self.cikti.setReadOnly(True)
        self.cikti.setMaximumHeight(110)
        self.cikti.setPlaceholderText("Üretilen lisans anahtarı burada görünür.")
        lay.addWidget(self.cikti)

        lay.addWidget(QLabel("<b>Satış kaydı</b> (lisanslar.csv — çift tıklayınca anahtar yukarıda gösterilir)"))
        self.tablo = QTableWidget(0, 8)
        self.tablo.setHorizontalHeaderLabels(["No", "Tarih", "Okul", "Kurum kodu", "Tür", "Bitiş", "Ücret", "Fatura no"])
        self.tablo.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tablo.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tablo.setSelectionBehavior(QTableWidget.SelectRows)
        self.tablo.cellDoubleClicked.connect(self._satir_sec)
        lay.addWidget(self.tablo)
        self._sure_degisti()
        self._tablo_doldur()

    def _sure_degisti(self):
        n = self.sure.currentData()
        self.bitis.setEnabled(n == -1)
        self.bitis.setVisible(n != 0)
        if n and n > 0:
            b = yil_ekle(date.today(), n)
            self.bitis.setDate(QDate(b.year, b.month, b.day))

    def _tablo_doldur(self):
        self.kayitlar = list(reversed(kayitlari_oku()))
        self.tablo.setRowCount(len(self.kayitlar))
        for i, k in enumerate(self.kayitlar):
            for j, ad in enumerate(["no", "tarih", "okul", "kurum_kodu", "tur", "bitis", "ucret", "fatura_no"]):
                self.tablo.setItem(i, j, QTableWidgetItem(k.get(ad, "")))

    def _satir_sec(self, satir, _kolon):
        self.cikti.setPlainText(self.kayitlar[satir].get("anahtar", ""))

    def uret(self):
        okul, kod = self.okul.text().strip(), lisans.kurum_kodu_normalize(self.kod.text())
        if not okul or not kod:
            QMessageBox.warning(self, "Eksik bilgi", "Okul adı ve kurum kodu zorunludur.")
            return
        n = self.sure.currentData()
        bitis = None if n == 0 else self.bitis.date().toPython()
        if bitis and bitis <= date.today():
            QMessageBox.warning(self, "Hatalı tarih", "Bitiş tarihi bugünden sonra olmalıdır.")
            return
        tur = SUREKLI if n == 0 else self.sure.currentText()
        no = sonraki_no()
        anahtar = lisans.imzala(self.ozel, okul, kod, bitis, no, tur)
        lisans.coz(anahtar, self.acik)
        LIC_KLASORU.mkdir(exist_ok=True)
        dosya = LIC_KLASORU / f"{kod}_{no}.lic"
        dosya.write_text(anahtar + "\n", encoding="utf-8")
        kayit_ekle({"no": no, "tarih": date.today().strftime("%d.%m.%Y"), "okul": okul, "kurum_kodu": kod, "tur": tur,
                    "bitis": bitis.strftime("%d.%m.%Y") if bitis else SUREKLI, "ucret": f"{self.ucret.value():.2f}",
                    "fatura_no": self.fatura.text().strip(), "iletisim": self.iletisim.text().strip(),
                    "not": self.notlar.text().strip(), "anahtar": anahtar})
        self.cikti.setPlainText(anahtar)
        self._tablo_doldur()
        QMessageBox.information(self, "Lisans üretildi",
                                f"{no} numaralı lisans üretildi.\n\nDosya: {dosya}\n\nAnahtarı kopyalayıp e-postayla "
                                "gönderebilir veya .lic dosyasını iletebilirsiniz. Okul, programda 'Lisans…' düğmesiyle "
                                "etkinleştirir.")

    def kopyala(self):
        if self.cikti.toPlainText():
            QApplication.clipboard().setText(self.cikti.toPlainText())


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if not OZEL.exists():
        QMessageBox.critical(None, "Özel anahtar yok",
                             f"{OZEL} bulunamadı.\n\nÖnce 'python satici/anahtar_olustur.py' komutunu bir kez çalıştırın.")
        return 1
    ozel = serialization.load_pem_private_key(OZEL.read_bytes(), password=None)
    p = Pencere(ozel)
    p.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
