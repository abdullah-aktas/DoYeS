"""Veritabanı bağlantı ayarları: bu bilgisayarda yerel dosya veya internet üzerinden merkezi PostgreSQL sunucusu."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QButtonGroup, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QRadioButton, QSpinBox, QVBoxLayout)

from .. import ag, baglanti, db as dbmod
from ..lisans import kurum_kodu_normalize
from .marka import ikon
from .ortak import SecimKutusu, bilgi, hata


class BaglantiDialog(QDialog):
    def __init__(self, parent=None, hata_metni: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Bağlantı ayarları")
        self.setWindowIcon(ikon())
        self.setMinimumWidth(520)
        ayar = baglanti.oku()
        ag_ayar = ag.oku()
        lay = QVBoxLayout(self)
        if hata_metni:
            n = QLabel(f"<b>Veritabanına bağlanılamadı:</b><br>{hata_metni}")
            n.setWordWrap(True)
            n.setObjectName("uyariKutusu")
            lay.addWidget(n)

        self.r_yerel = QRadioButton("Yerel: veriler yalnız bu bilgisayarda (tek kullanıcı)")
        self.r_sunucu = QRadioButton("Merkezi sunucu: birden çok bilgisayar internet üzerinden aynı verilerle çalışır")
        grup = QButtonGroup(self)
        for r in (self.r_yerel, self.r_sunucu):
            grup.addButton(r)
            lay.addWidget(r)

        self.kutu = QGroupBox("PostgreSQL sunucu bilgileri")
        f = QFormLayout(self.kutu)
        self.kurum_kodu = QLineEdit()
        self.kurum_kodu.setPlaceholderText("MEB kurum kodu (5–8 rakam)")
        b_kurum = QPushButton("Kurum kodundan doldur")
        b_kurum.setToolTip("Barındırma sunucusunda okul_<kod> veritabanı adını ve kullanıcıyı doldurur.")
        b_kurum.clicked.connect(self._kurumdan_doldur)
        kurum_satir = QHBoxLayout()
        kurum_satir.addWidget(self.kurum_kodu)
        kurum_satir.addWidget(b_kurum)
        self.sunucu = QLineEdit(ayar.sunucu or ag_ayar.pg_sunucu)
        self.sunucu.setPlaceholderText("ör. dose.okulum.k12.tr veya 185.10.20.30")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(ayar.port or ag_ayar.pg_port or 5432))
        self.vt = QLineEdit(ayar.veritabani or "dose")
        self.kullanici = QLineEdit(ayar.kullanici)
        self.sifre = QLineEdit(ayar.sifre)
        self.sifre.setEchoMode(QLineEdit.Password)
        self.ssl = SecimKutusu(secenekler=baglanti.SSL_SECENEKLERI)
        self.ssl.ayarla(ayar.ssl or ag_ayar.pg_ssl or "require")
        f.addRow("Kurum kodu:", kurum_satir)
        f.addRow("Sunucu adresi:", self.sunucu)
        f.addRow("Port:", self.port)
        f.addRow("Veritabanı adı:", self.vt)
        f.addRow("Veritabanı kullanıcısı:", self.kullanici)
        f.addRow("Şifre:", self.sifre)
        f.addRow("SSL şifreleme:", self.ssl)
        lay.addWidget(self.kutu)
        n = QLabel("Aynı kurum kodu ile her bilgisayardan ve mobilden çalışırsınız. Barındırmada «Kurum kodundan doldur» "
                   "veritabanı adını okul_… biçiminde yazar. Sunucu bilgilerini bilişim sorumlusu verir (bkz. KURULUM.md). "
                   "Şifre bu bilgisayarda Windows hesabınıza bağlı olarak şifrelenir. İnternet üzerinden SSL kapatılmamalıdır.")
        n.setWordWrap(True)
        n.setStyleSheet("color:#555")
        lay.addWidget(n)

        u = QHBoxLayout()
        b_dene = QPushButton("Bağlantıyı sına")
        b_dene.clicked.connect(self.dene)
        b_kaydet = QPushButton("Kaydet ve bağlan")
        b_kaydet.setObjectName("birincil")
        b_kaydet.setDefault(True)
        b_kaydet.clicked.connect(self.kaydet)
        b_vazgec = QPushButton("Vazgeç")
        b_vazgec.clicked.connect(self.reject)
        u.addWidget(b_dene)
        u.addStretch()
        u.addWidget(b_kaydet)
        u.addWidget(b_vazgec)
        lay.addLayout(u)

        (self.r_sunucu if ayar.sunucu_mu else self.r_yerel).setChecked(True)
        self.r_sunucu.toggled.connect(self._tur_degisti)
        self._tur_degisti()

    def _tur_degisti(self):
        self.kutu.setEnabled(self.r_sunucu.isChecked())

    def _kurumdan_doldur(self):
        kod = kurum_kodu_normalize(self.kurum_kodu.text())
        if not ag.kurum_kodu_gecerli(kod):
            hata(self, "Kurum kodu 5–8 rakam olmalıdır.")
            return
        try:
            vt = ag.kurum_db_adi(kod)
        except ValueError as e:
            hata(self, str(e))
            return
        ag_ayar = ag.oku()
        if ag_ayar.pg_sunucu and not self.sunucu.text().strip():
            self.sunucu.setText(ag_ayar.pg_sunucu)
            self.port.setValue(int(ag_ayar.pg_port or 5432))
            self.ssl.ayarla(ag_ayar.pg_ssl or "require")
        self.vt.setText(vt)
        self.kullanici.setText(vt)
        self.r_sunucu.setChecked(True)
        bilgi(self, f"Veritabanı ve kullanıcı «{vt}» olarak dolduruldu. Satıcının verdiği şifreyi girip kaydediniz.")

    def ayar(self) -> baglanti.BaglantiAyari:
        return baglanti.BaglantiAyari(
            tur="sunucu" if self.r_sunucu.isChecked() else "yerel", sunucu=self.sunucu.text().strip(), port=self.port.value(),
            veritabani=self.vt.text().strip() or "dose", kullanici=self.kullanici.text().strip(), sifre=self.sifre.text(),
            ssl=self.ssl.deger() or "require")

    def _sina(self, a) -> str | None:
        if not a.sunucu_mu:
            return None
        if not a.sunucu or not a.kullanici:
            return "Sunucu adresi ve veritabanı kullanıcısı zorunludur."
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            return dbmod.baglanti_dene(a)
        finally:
            QApplication.restoreOverrideCursor()

    def dene(self):
        a = self.ayar()
        if not a.sunucu_mu:
            bilgi(self, "Yerel modda bağlantı gerekmez.")
            return
        h = self._sina(a)
        if h:
            hata(self, f"Bağlantı kurulamadı:\n\n{h}")
        else:
            bilgi(self, "Bağlantı başarılı.")

    def kaydet(self):
        a = self.ayar()
        h = self._sina(a)
        if h:
            hata(self, f"Bağlantı kurulamadı, ayarlar kaydedilmedi:\n\n{h}")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            dbmod.baslat(a)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            hata(self, f"Veritabanı açılamadı:\n\n{e}")
            return
        QApplication.restoreOverrideCursor()
        baglanti.yaz(a)
        self.accept()
