from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout)

from .. import SURUM, UYGULAMA_ADI, lisans
from .lisans_dialog import LisansDialog, durum_rengi
from .marka import ikon, logo_etiket
from .ortak import Oturum, db, uyari


class GirisDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{UYGULAMA_ADI} - Giriş")
        self.setWindowIcon(ikon())
        self.setMinimumWidth(400)
        lay = QVBoxLayout(self)
        l_logo = logo_etiket(self, 380)
        if l_logo:
            lay.addWidget(l_logo)
            baslik = QLabel(f"<span style='color:#777'>Sürüm {SURUM} • {lisans.SATICI}</span>")
        else:
            baslik = QLabel(f"<h2 style='color:#1f4e79'>{UYGULAMA_ADI}</h2>"
                            f"<p>Mesleki ve Teknik Anadolu Liseleri Döner Sermaye İşletmesi<br>"
                            f"<span style='color:#777'>Sürüm {SURUM} • {lisans.SATICI}</span></p>")
        baslik.setAlignment(Qt.AlignCenter)
        lay.addWidget(baslik)
        form = QFormLayout()
        self.k = QLineEdit()
        self.s = QLineEdit()
        self.s.setEchoMode(QLineEdit.Password)
        form.addRow("Kullanıcı adı:", self.k)
        form.addRow("Şifre:", self.s)
        lay.addLayout(form)
        self.ilk = QLabel("İlk giriş: kullanıcı adı <b>admin</b>, şifre <b>admin</b>. Girişte şifrenizi değiştirmeniz istenecektir.")
        self.ilk.setWordWrap(True)
        self.ilk.setObjectName("uyariKutusu")
        lay.addWidget(self.ilk)
        self.l_baglanti = QLabel()
        self.l_baglanti.setWordWrap(True)
        self.l_baglanti.setStyleSheet("color:#555")
        lay.addWidget(self.l_baglanti)
        self.l_lisans = QLabel()
        self.l_lisans.setWordWrap(True)
        lay.addWidget(self.l_lisans)
        dugmeler = QHBoxLayout()
        b_ayar = QPushButton("Bağlantı ayarları…")
        b_ayar.clicked.connect(self._baglanti_ayarlari)
        b_lisans = QPushButton("Lisans…")
        b_lisans.clicked.connect(self._lisans)
        dugmeler.addWidget(b_ayar)
        dugmeler.addWidget(b_lisans)
        dugmeler.addStretch()
        lay.addLayout(dugmeler)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Giriş")
        bb.button(QDialogButtonBox.Cancel).setText("Çıkış")
        bb.accepted.connect(self._giris)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._bilgi_guncelle()
        self.k.setFocus()

    def _bilgi_guncelle(self):
        self.ilk.setVisible(db().ayar("ilk_giris_yapildi") is None)
        self.l_baglanti.setText("🔌 " + db().aciklama())
        d = lisans.uygula(db())
        self.l_lisans.setText("🔑 " + d.ozet)
        self.l_lisans.setStyleSheet(durum_rengi(d) + "padding:4px; border-radius:3px;")

    def _baglanti_ayarlari(self):
        from .baglanti_dialog import BaglantiDialog
        if BaglantiDialog(self).exec():
            self._bilgi_guncelle()

    def _lisans(self):
        LisansDialog(self).exec()
        self._bilgi_guncelle()

    def _giris(self):
        try:
            k = db().giris_dogrula(self.k.text().strip(), self.s.text())
        except Exception as e:
            uyari(self, f"Veritabanına ulaşılamadı:\n{e}\n\nİnternet bağlantınızı veya bağlantı ayarlarını kontrol ediniz.")
            return
        if not k:
            uyari(self, "Kullanıcı adı veya şifre hatalı.")
            return
        Oturum.kullanici = k
        db().oturum_ac(k)
        db().ex("UPDATE kullanici SET son_giris = ? WHERE id = ?", (datetime.now().strftime("%Y-%m-%d %H:%M"), k["id"]))
        db().log("Oturum açma")
        db().ayar_yaz("ilk_giris_yapildi", "1")
        if k["sifre_degismeli"]:
            d = SifreDialog(self, k["id"], zorunlu=True)
            if not d.exec():
                return
        self.accept()


class SifreDialog(QDialog):
    def __init__(self, parent, kullanici_id: int, zorunlu=False):
        super().__init__(parent)
        self.kid = kullanici_id
        self.setWindowTitle("Şifre Değiştir")
        self.setWindowIcon(ikon())
        lay = QVBoxLayout(self)
        if zorunlu:
            lay.addWidget(QLabel("Güvenliğiniz için yeni bir şifre belirleyiniz (en az 6 karakter)."))
        form = QFormLayout()
        self.s1 = QLineEdit()
        self.s2 = QLineEdit()
        for s in (self.s1, self.s2):
            s.setEchoMode(QLineEdit.Password)
        form.addRow("Yeni şifre:", self.s1)
        form.addRow("Yeni şifre (tekrar):", self.s2)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._kaydet)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _kaydet(self):
        if len(self.s1.text()) < 6:
            uyari(self, "Şifre en az 6 karakter olmalıdır.")
            return
        if self.s1.text() != self.s2.text():
            uyari(self, "Şifreler eşleşmiyor.")
            return
        db().sifre_degistir(self.kid, self.s1.text())
        self.accept()
