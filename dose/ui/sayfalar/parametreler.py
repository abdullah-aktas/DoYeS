import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ... import mevzuat
from ..ortak import OranKutusu, Oturum, ParaKutusu, baslik_etiketi, bilgi, buton, db, soru, uyari, yetki_kontrol


class ParametreSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "Mevzuat Parametreleri",
            "Yıllık oran ve tutarlar. Hesaplamalar işlemin yılına ait parametrelerle yapılır; bir yıl için girilmeyen "
            "değer en yakın önceki yıldan alınır. Asgari ücret, vergi tarifesi ve fazla çalışma ücretini her yıl güncelleyiniz."))
        ust = QHBoxLayout()
        self.yil_etiket = QLabel()
        self.yil_etiket.setStyleSheet("font-weight:600")
        ust.addWidget(self.yil_etiket)
        ust.addStretch()
        ust.addWidget(buton("Mevzuat varsayılanlarını yükle", self.varsayilan))
        ust.addWidget(buton("Kaydet", self.kaydet, "birincil"))
        lay.addLayout(ust)
        self.tablo = QTableWidget()
        self.tablo.setColumnCount(3)
        self.tablo.setHorizontalHeaderLabels(["Parametre", "Değer", "Dayanak / açıklama"])
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.tablo)
        self.yenile()

    def yenile(self):
        yil = Oturum.yil
        self.yil_etiket.setText(f"{yil} yılı parametreleri")
        p = db().parametreler(yil)
        self.tablo.setRowCount(len(mevzuat.PARAMETRELER))
        self.kutular = {}
        for i, (anahtar, etiket, tur, _v, aciklama) in enumerate(mevzuat.PARAMETRELER):
            it = QTableWidgetItem(etiket)
            it.setFlags(Qt.ItemIsEnabled)
            self.tablo.setItem(i, 0, it)
            if tur == "oran":
                w = OranKutusu()
                w.ayarla(p[anahtar])
            elif tur in ("para", "sayi"):
                w = ParaKutusu(ondalik=2 if tur == "para" else 3)
                w.ayarla(p[anahtar])
            else:
                w = QLineEdit(json.dumps(p[anahtar]) if not isinstance(p[anahtar], str) else p[anahtar])
            self.kutular[anahtar] = (w, tur)
            self.tablo.setCellWidget(i, 1, w)
            a = QTableWidgetItem(aciklama)
            a.setFlags(Qt.ItemIsEnabled)
            a.setToolTip(aciklama)
            self.tablo.setItem(i, 2, a)
        self.tablo.resizeColumnToContents(0)
        self.tablo.setColumnWidth(1, 200)

    def varsayilan(self):
        if not soru(self, "Ekrandaki değerler uygulamadaki 2026 mevzuat varsayılanları ile değiştirilecek (kaydetmeden önce kontrol edebilirsiniz). Devam edilsin mi?"):
            return
        for anahtar, (w, tur) in self.kutular.items():
            v = mevzuat.PARAMETRE_SOZLUK[anahtar][3]
            if tur in ("oran", "para", "sayi"):
                w.ayarla(v)
            else:
                w.setText(v)

    def kaydet(self):
        if not yetki_kontrol(self, yonetici=True):
            return
        yil = Oturum.yil
        for anahtar, (w, tur) in self.kutular.items():
            if tur == "metin":
                try:
                    dilimler = json.loads(w.text())
                    assert isinstance(dilimler, list) and dilimler[-1][0] is None
                except Exception:
                    uyari(self, "Gelir vergisi tarifesi geçersiz. Biçim: [[190000, 0.15], [400000, 0.20], ..., [null, 0.40]]")
                    return
                deger = w.text()
            else:
                deger = w.deger()
            db().parametre_yaz(yil, anahtar, deger)
        db().log("Parametre güncelleme", "parametre", yil)
        bilgi(self, f"{yil} yılı parametreleri kaydedildi.")
