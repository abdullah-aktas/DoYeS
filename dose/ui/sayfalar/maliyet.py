"""Ürün / hizmet kartları, birim maliyet analizi ve fiyat tespiti."""
from PySide6.QtWidgets import (QCheckBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit,
                               QTableWidget, QVBoxLayout)

from ... import belgeler, maliyet, mevzuat
from ...hesap import para, yuvarla
from ...muhasebe import ortalama_maliyet
from ..ortak import (Alan, KayitSayfasi, MesajKutusu, OranKutusu, Oturum, ParaKutusu, SecimKutusu, VarlikTanimi,
                     bilgi, buton, bugun, cikti_yolu, db, dosya_ac, fk_secenekleri, kayit_izle, satir_odagini_izle, soru,
                     yetki_kontrol)

MALZEME_UNSURLARI = maliyet.MALZEME_UNSURLARI
ISCILIK, OGRENCI, GENEL = maliyet.ISCILIK, maliyet.OGRENCI, maliyet.GENEL
OTO_ACIKLAMA = maliyet.OTO_ACIKLAMA
from .tanimlar import bolumler


class UrunSayfasi(KayitSayfasi):
    def __init__(self):
        super().__init__(VarlikTanimi(
            tablo="urun", baslik="Ürün / Hizmet Kartları ve Maliyet",
            aciklama="Üretilen mal ve hizmetler. 'Maliyet Analizi' ile birim maliyet unsurları girilir, kâr eklenerek satış "
                     "fiyatı belirlenir ve Yön. md.10'a göre fiyat tespit tutanağı düzenlenir.",
            alanlar=[
                Alan("kod", "Kod"),
                Alan("ad", "Ürün / hizmet adı", zorunlu=True),
                Alan("tur", "Türü", "secim", zorunlu=True, secenekler=mevzuat.URUN_TURLERI, varsayilan="Mal"),
                Alan("birim", "Birim", "secim", secenekler=mevzuat.BIRIMLER, varsayilan="Adet", duzenlenebilir=True),
                Alan("bolum_id", "Bölüm / atölye", "fk", secenekler=bolumler),
                Alan("ucret_esasi", "Ücret ödeme esası", "secim", secenekler=mevzuat.UCRET_ESASLARI,
                     varsayilan=mevzuat.UCRET_ESASLARI[0]),
                Alan("kdv_orani", "KDV oranı", "oran", varsayilan=0.20),
                Alan("satis_fiyati", "Birim satış fiyatı (KDV hariç)", "para"),
                Alan("kar_orani", "Hedef kâr oranı", "oran", varsayilan=0.10, tabloda=False),
                Alan("mamul_malzeme_id", "Stoktaki mamul kartı (varsa)", "fk",
                     secenekler=lambda: fk_secenekleri("malzeme", "ad", "tur IN ('Mamul', 'Ticari Mal')"), tabloda=False,
                     ipucu="Satış faturasında stoktan otomatik düşülecek mamul/ticari mal"),
                Alan("aktif", "Aktif", "bool", varsayilan=1, tabloda=False),
                Alan("aciklama", "Açıklama", "cokmetin", tabloda=False),
            ],
            sirala="ad",
            silme_kontrol=lambda s: "Ürün faturalarda kullanılmış." if db().deger(
                "SELECT COUNT(*) FROM fatura_kalem WHERE urun_id = ?", (s["id"],)) else None,
        ))
        self.ek_butonlar.addWidget(buton("Maliyet Analizi / Fiyat Tespiti", self.maliyet, "birincil"))

    def veriler(self):
        satirlar = super().veriler()
        for s in satirlar:
            s["kdv_dahil"] = yuvarla((s.get("satis_fiyati") or 0) * (1 + (s.get("kdv_orani") or 0)))
        return satirlar

    def kolonlar(self):
        from ..ortak import Kolon
        return super().kolonlar() + [Kolon("kdv_dahil", "KDV dahil fiyat", "para")]

    def maliyet(self):
        s = self.tablo.secili()
        if not s:
            bilgi(self, "Önce listeden bir ürün/hizmet seçiniz.")
            return
        MaliyetDialog(self, s["id"]).exec()
        self.yenile()


class MaliyetDialog(QDialog):
    KOLONLAR = ["Maliyet unsuru", "Açıklama", "Malzeme (stok)", "Miktar", "Birim fiyat", "Tutar"]

    def __init__(self, parent, urun_id: int):
        super().__init__(parent)
        kayit_izle(self, "urun", urun_id)
        urun = db().q1("SELECT u.*, b.ad bolum_ad FROM urun u LEFT JOIN bolum b ON b.id = u.bolum_id WHERE u.id = ?", (urun_id,))
        if urun is None:
            raise ValueError("Maliyet analizi yapılacak ürün / hizmet kaydı bulunamadı.")
        self.urun = urun
        self.p = db().parametreler(Oturum.yil)
        self.setWindowTitle(f"Maliyet Analizi - {self.urun['ad']}")
        self.resize(1000, 680)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>{self.urun['ad']}</b> — birim: {self.urun.get('birim') or ''} — ücret esası: "
                             f"{self.urun.get('ucret_esasi') or ''}. Değerler <b>1 birim</b> içindir."))
        ust = QHBoxLayout()
        ust.addWidget(buton("＋ Satır", self.satir_ekle))
        ust.addWidget(buton("Satırı sil", self.satir_sil))
        ust.addStretch()
        lay.addLayout(ust)
        self.t = QTableWidget(0, len(self.KOLONLAR))
        self.t.setHorizontalHeaderLabels(self.KOLONLAR)
        self.t.horizontalHeader().setStretchLastSection(True)
        self.t.verticalHeader().setVisible(False)
        satir_odagini_izle(self.t)
        lay.addWidget(self.t)
        self.malzemeler = fk_secenekleri("malzeme", "ad", "aktif = 1")

        oto_kutu = QGroupBox("İşçilik ve diğer giderler: yasal üst sınır")
        ov = QHBoxLayout(oto_kutu)
        self.oto = QCheckBox("Otomatik hesapla")
        self.oto.setToolTip("Malzemeyi ve bildiğiniz giderleri (enerji, bakım vb.) girin; işçilik, öğrenci hakkı, genel gider ve "
                            "kâr oranı hedef fiyattan yasal sınırlarla kendiliğinden hesaplanır.")
        self.hedef_fiyat = ParaKutusu(ondalik=4)
        self.hedef_fiyat.ayarla(self.urun.get("satis_fiyati"))
        acik = QLabel("Hedef birim satış fiyatı (KDV hariç):")
        ov.addWidget(self.oto)
        ov.addWidget(acik)
        ov.addWidget(self.hedef_fiyat)
        self.oto_bilgi = QLabel()
        self.oto_bilgi.setWordWrap(True)
        ov.addWidget(self.oto_bilgi, 1)
        lay.addWidget(oto_kutu)

        alt = QHBoxLayout()
        g = QGroupBox("Fiyat hesabı")
        f = QFormLayout(g)
        self.l_maliyet = QLabel()
        self.kar = OranKutusu(azami=1000)
        self.kar.setDecimals(6)
        self.kar.ayarla(self.urun.get("kar_orani") or 0.10)
        self.kar.valueChanged.connect(self.hesapla)
        self.kdv = OranKutusu()
        self.kdv.ayarla(self.urun.get("kdv_orani") or 0.20)
        self.kdv.valueChanged.connect(self.hesapla)
        self.hedef = ParaKutusu()
        self.l_satis = QLabel()
        self.l_kdvdahil = QLabel()
        f.addRow("Birim maliyet:", self.l_maliyet)
        f.addRow("Kâr oranı:", self.kar)
        f.addRow("KDV oranı:", self.kdv)
        f.addRow("KDV hariç satış fiyatı:", self.l_satis)
        f.addRow("KDV dahil satış fiyatı:", self.l_kdvdahil)
        h = QHBoxLayout()
        h.addWidget(self.hedef)
        h.addWidget(buton("Kâr oranını hesapla", self.hedeften))
        f.addRow("Hedef KDV dahil fiyat:", h)
        alt.addWidget(g)
        g2 = QGroupBox("Piyasa araştırması / değerlendirme (tutanağa yazılır)")
        v2 = QVBoxLayout(g2)
        self.piyasa = QPlainTextEdit()
        v2.addWidget(self.piyasa)
        self.mesaj = MesajKutusu()
        v2.addWidget(self.mesaj)
        alt.addWidget(g2)
        lay.addLayout(alt)

        bb = QHBoxLayout()
        bb.addStretch()
        bb.addWidget(buton("Kaydet", self.kaydet))
        bb.addWidget(buton("Fiyatı ürün kartına işle", self.fiyat_isle))
        bb.addWidget(buton("Fiyat Tespit Tutanağı (PDF)", self.tutanak, "birincil"))
        bb.addWidget(buton("Kapat", self.reject))
        lay.addLayout(bb)

        self._oto_calisiyor = False
        kayitli = db().q("SELECT * FROM maliyet_kalem WHERE urun_id = ? ORDER BY id", (urun_id,))
        for k in kayitli:
            self.satir_ekle(k)
        if not self.t.rowCount():
            for kalem in ("Direkt İlk Madde ve Malzeme", ISCILIK, OGRENCI, "Enerji (Elektrik/Gaz/Su)", "Amortisman / Bakım-Onarım"):
                self.satir_ekle({"kalem_turu": kalem, "miktar": 1, "birim_fiyat": 0})
        self.oto.setChecked(not kayitli or any(k.get("aciklama") in OTO_ACIKLAMA.values() for k in kayitli))
        self.oto.toggled.connect(self.hesapla)
        self.hedef_fiyat.valueChanged.connect(self.hesapla)
        self.hesapla()

    def satir_ekle(self, k=None):
        k = k if isinstance(k, dict) else {"kalem_turu": mevzuat.MALIYET_KALEMLERI[0], "miktar": 1, "birim_fiyat": 0}
        r = self.t.rowCount()
        self.t.insertRow(r)
        tur = SecimKutusu(secenekler=mevzuat.MALIYET_KALEMLERI)
        tur.ayarla(k.get("kalem_turu"))
        from PySide6.QtWidgets import QLineEdit
        ack = QLineEdit(k.get("aciklama") or "")
        mlz = SecimKutusu(secenekler=self.malzemeler, bos=True)
        mlz.ayarla(k.get("malzeme_id"))
        mik = ParaKutusu(ondalik=4)
        mik.ayarla(k.get("miktar") or 0)
        bf = ParaKutusu(ondalik=4)
        bf.ayarla(k.get("birim_fiyat") or 0)
        tutar = QLabel()
        for c, w in enumerate((tur, ack, mlz, mik, bf, tutar)):
            self.t.setCellWidget(r, c, w)
        mik.valueChanged.connect(self.hesapla)
        bf.valueChanged.connect(self.hesapla)
        tur.currentIndexChanged.connect(self.hesapla)

        def malzeme_secildi():
            malzeme_id = mlz.deger()
            if malzeme_id:
                bf.ayarla(ortalama_maliyet(malzeme_id))
                if not ack.text():
                    ack.setText(mlz.currentText())
        mlz.currentIndexChanged.connect(malzeme_secildi)
        self.t.resizeColumnsToContents()
        self.t.setColumnWidth(1, 200)
        self.hesapla()

    def satir_sil(self):
        r = self.t.currentRow()
        if r >= 0:
            self.t.removeRow(r)
            self.hesapla()

    def kalemler(self):
        sonuc = []
        for r in range(self.t.rowCount()):
            w = [self.t.cellWidget(r, c) for c in range(6)]
            sonuc.append({"kalem_turu": w[0].deger(), "aciklama": w[1].text().strip() or None, "malzeme_id": w[2].deger(),
                          "miktar": w[3].deger(), "birim_fiyat": w[4].deger()})
        return sonuc

    def ozet(self):
        kalemler = self.kalemler()
        hesap = maliyet.hesapla(self.urun, self.p, kalemler, False, 0,
                                self.kar.deger(), self.kdv.deger())
        return hesap["ozet"], hesap["kalemler"]

    @staticmethod
    def _sessiz(kutu, deger):
        kutu.blockSignals(True)
        kutu.ayarla(deger)
        kutu.blockSignals(False)

    def _oto_satir(self, r: int) -> bool:
        tur, ack = self.t.cellWidget(r, 0).deger(), self.t.cellWidget(r, 1).text()
        return tur in (ISCILIK, OGRENCI) or (tur == GENEL and ack == OTO_ACIKLAMA[GENEL])

    def _kilitle(self):
        oto = self.oto.isChecked()
        self.kar.setEnabled(not oto)
        for r in range(self.t.rowCount()):
            kilit = oto and self._oto_satir(r)
            for c in (0, 2, 3, 4):
                self.t.cellWidget(r, c).setEnabled(not kilit)
            self.t.cellWidget(r, 1).setReadOnly(kilit)

    def hesapla(self):
        if not hasattr(self, "mesaj") or getattr(self, "_oto_calisiyor", True):
            return
        kalemler = self.kalemler()
        hesap = maliyet.hesapla(self.urun, self.p, kalemler, self.oto.isChecked(),
                                self.hedef_fiyat.deger(), self.kar.deger(), self.kdv.deger())
        if self.oto.isChecked():
            if not hesap["hatalar"]:
                self._oto_calisiyor = True
                try:
                    self.t.setRowCount(0)
                    for kalem in hesap["kalemler"]:
                        self.satir_ekle(kalem)
                    self._sessiz(self.kar, hesap["kar_orani"])
                finally:
                    self._oto_calisiyor = False
            self.oto_bilgi.setText("" if hesap["hatalar"] else hesap["oto_bilgi"])
        else:
            self.oto_bilgi.setText(hesap["oto_bilgi"])
        self._kilitle()
        for r in range(self.t.rowCount()):
            mik, bf, lbl = self.t.cellWidget(r, 3), self.t.cellWidget(r, 4), self.t.cellWidget(r, 5)
            if mik and bf and lbl:
                lbl.setText(para(mik.deger() * bf.deger()))
        o, kalemler = hesap["ozet"], hesap["kalemler"]
        self.l_maliyet.setText(para(o["birim_maliyet"]) + " TL")
        self.l_satis.setText(para(o["satis_fiyati"]) + " TL")
        self.l_kdvdahil.setText(f"<b>{para(o['kdv_dahil'])} TL</b>")
        self.mesaj.goster(
            hesap["hatalar"], hesap["uyarilar"],
            "Maliyet unsurları mevzuat oranlarıyla uyumlu; işçilik ve giderler yasal üst sınırda."
            if self.oto.isChecked() else "Maliyet unsurları mevzuat oranlarıyla uyumlu.")

    def hedeften(self):
        if self.oto.isChecked():
            self.hedef_fiyat.ayarla(yuvarla(self.hedef.deger() / (1 + self.kdv.deger()), 4))
            return
        o, _ = self.ozet()
        if o["birim_maliyet"] <= 0:
            return
        kdvsiz = self.hedef.deger() / (1 + self.kdv.deger())
        self.kar.ayarla(max(0.0, kdvsiz / o["birim_maliyet"] - 1))
        self.hesapla()

    def kaydet(self, sessiz=False):
        if not yetki_kontrol(self):
            return False
        db().ex("DELETE FROM maliyet_kalem WHERE urun_id = ?", (self.urun["id"],))
        for k in self.kalemler():
            k["urun_id"] = self.urun["id"]
            db().ekle("maliyet_kalem", k, log=False)
        db().guncelle("urun", self.urun["id"], {"kar_orani": self.kar.deger(), "kdv_orani": self.kdv.deger()})
        if not sessiz:
            bilgi(self, "Maliyet analizi kaydedildi.")
        return True

    def fiyat_isle(self):
        if not self.kaydet(sessiz=True):
            return
        o, _ = self.ozet()
        if soru(self, f"Ürün kartındaki KDV hariç satış fiyatı {para(o['satis_fiyati'])} TL olarak güncellensin mi?"):
            db().guncelle("urun", self.urun["id"], {"satis_fiyati": o["satis_fiyati"]})
            bilgi(self, "Satış fiyatı güncellendi.")

    def tutanak(self):
        if not self.kaydet(sessiz=True):
            return
        o, kalemler = self.ozet()
        db().ekle("fiyat_tespit", {"urun_id": self.urun["id"], "tarih": bugun(), "birim_maliyet": o["birim_maliyet"],
                                   "kar_orani": o["kar_orani"], "satis_fiyati": o["satis_fiyati"], "kdv_orani": o["kdv_orani"],
                                   "kdv_dahil_fiyat": o["kdv_dahil"], "piyasa_arastirmasi": self.piyasa.toPlainText()})
        yol = belgeler.fiyat_tespit_tutanagi(cikti_yolu(f"Fiyat_Tespit_{self.urun['ad']}"), self.urun, kalemler, o,
                                             self.piyasa.toPlainText())
        dosya_ac(yol)
