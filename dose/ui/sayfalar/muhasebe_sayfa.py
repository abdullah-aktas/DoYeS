"""Yardımcı muhasebe: yevmiye, manuel fiş, mizan, gelir tablosu, hesap planı."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QSplitter, QTableWidget, QTabWidget, QVBoxLayout,
                               QWidget)

from ... import belgeler, muhasebe
from ...hesap import para, yuvarla
from ..ortak import (Alan, FormDialog, Kolon, Oturum, ParaKutusu, SecimKutusu, TarihKutusu, VeriTablosu, baslik_etiketi,
                     bilgi, buton, cikti_yolu, db, dosya_ac, soru, tablo_excele, uyari, yetki_kontrol)


def hesap_secenekleri():
    return [(r["kod"], f"{r['kod']} - {r['ad']}") for r in db().q("SELECT kod, ad FROM hesap_plani ORDER BY kod")]


class MuhasebeSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "Muhasebe (Yardımcı Defter)",
            "İşlemlerden otomatik üretilen yardımcı yevmiye kayıtları, mizan ve gelir tablosu. Resmi kayıtlar D.S.İ.B.M.Y. gereğince "
            "BKMYBS'de tutulur; bu ekran mutabakat ve kontrol içindir."))
        self.sekme = QTabWidget()
        lay.addWidget(self.sekme)

        # yevmiye
        w = QWidget()
        v = QVBoxLayout(w)
        ust = QHBoxLayout()
        ust.addWidget(QLabel("Tarih:"))
        self.bas = TarihKutusu()
        self.bit = TarihKutusu()
        ust.addWidget(self.bas)
        ust.addWidget(QLabel("-"))
        ust.addWidget(self.bit)
        ust.addWidget(buton("Listele", self.yenile))
        self.b_manuel = buton("＋ Manuel fiş", self.manuel, "birincil")
        ust.addWidget(self.b_manuel)
        ust.addWidget(buton("Fişi sil (manuel)", self.fis_sil, "tehlike"))
        ust.addWidget(buton("Muhasebe işlem fişi PDF", self.fis_pdf))
        ust.addWidget(buton("Kayıtları yeniden üret", self.yeniden_uret,
                            ipucu="Manuel fişler dışındaki tüm kayıtları kaynak işlemlerden yeniden oluşturur."))
        ust.addWidget(buton("Excel", lambda: tablo_excele(self, self.t_fis, "Yevmiye")))
        ust.addStretch()
        v.addLayout(ust)
        sp = QSplitter(Qt.Vertical)
        self.t_fis = VeriTablosu()
        self.t_fis.itemSelectionChanged.connect(self.satirlari_goster)
        self.t_satir = VeriTablosu()
        sp.addWidget(self.t_fis)
        sp.addWidget(self.t_satir)
        sp.setSizes([400, 220])
        v.addWidget(sp)
        self.sekme.addTab(w, "Yevmiye")

        # mizan
        w2 = QWidget()
        v2 = QVBoxLayout(w2)
        u2 = QHBoxLayout()
        u2.addWidget(buton("Mizanı hesapla", self.mizan_yenile, "birincil"))
        u2.addWidget(buton("PDF", self.mizan_pdf))
        u2.addWidget(buton("Excel", lambda: tablo_excele(self, self.t_mizan, "Mizan")))
        u2.addStretch()
        self.l_mizan = QLabel()
        u2.addWidget(self.l_mizan)
        v2.addLayout(u2)
        self.t_mizan = VeriTablosu()
        v2.addWidget(self.t_mizan)
        self.sekme.addTab(w2, "Mizan")

        # gelir tablosu
        w3 = QWidget()
        v3 = QVBoxLayout(w3)
        u3 = QHBoxLayout()
        u3.addWidget(buton("PDF", self.gt_pdf))
        u3.addStretch()
        v3.addLayout(u3)
        self.t_gt = VeriTablosu()
        v3.addWidget(self.t_gt)
        self.l_gt = QLabel()
        v3.addWidget(self.l_gt)
        self.sekme.addTab(w3, "Gelir tablosu")

        # hesap planı
        w4 = QWidget()
        v4 = QVBoxLayout(w4)
        u4 = QHBoxLayout()
        u4.addWidget(buton("＋ Hesap ekle", self.hesap_ekle))
        u4.addWidget(buton("Hesabı sil", self.hesap_sil, "tehlike"))
        u4.addStretch()
        v4.addLayout(u4)
        self.t_hp = VeriTablosu()
        v4.addWidget(self.t_hp)
        self.sekme.addTab(w4, "Hesap planı")
        self.yenile()

    def yenile(self):
        yil = Oturum.yil
        if self.bas.deger()[:4] != str(yil) or self.bit.deger()[:4] != str(yil):
            self.bas.ayarla(f"{yil}-01-01")
            self.bit.ayarla(f"{yil}-12-31")
        fisler = db().q("""SELECT y.*, SUM(s.borc) borc, SUM(s.alacak) alacak FROM yevmiye y
                           LEFT JOIN yevmiye_satir s ON s.yevmiye_id = y.id WHERE y.tarih BETWEEN ? AND ?
                           GROUP BY y.id ORDER BY y.tarih, y.id""", (self.bas.deger(), self.bit.deger()))
        self.t_fis.doldur([Kolon("fis_no", "Fiş no"), Kolon("tarih", "Tarih", "tarih"), Kolon("aciklama", "Açıklama"),
                           Kolon("kaynak", "Kaynak"), Kolon("borc", "Borç", "para"), Kolon("alacak", "Alacak", "para")], fisler,
                          lambda f: "#fde2e2" if abs((f["borc"] or 0) - (f["alacak"] or 0)) > 0.01 else None)
        self.t_satir.doldur([], [])
        self.mizan_yenile()
        self.gt_yenile()
        self.t_hp.doldur([Kolon("kod", "Kod"), Kolon("ad", "Hesap adı")], db().q("SELECT * FROM hesap_plani ORDER BY kod"))
        self.b_manuel.setEnabled(Oturum.yazabilir(self))

    def satirlari_goster(self):
        f = self.t_fis.secili()
        if not f:
            return
        satirlar = db().q("""SELECT s.*, h.ad FROM yevmiye_satir s LEFT JOIN hesap_plani h ON h.kod = s.hesap_kodu
                             WHERE s.yevmiye_id = ? ORDER BY s.borc DESC, s.id""", (f["id"],))
        self.t_satir.doldur([Kolon("hesap_kodu", "Hesap"), Kolon("ad", "Hesap adı"), Kolon("aciklama", "Açıklama"),
                             Kolon("borc", "Borç", "para"), Kolon("alacak", "Alacak", "para")], satirlar)

    def manuel(self):
        if yetki_kontrol(self) and ManuelFisDialog(self).exec():
            self.yenile()

    def fis_sil(self):
        f = self.t_fis.secili()
        if not f or not yetki_kontrol(self):
            return
        if f["kaynak"] != "Manuel":
            uyari(self, "Otomatik fişler kaynak işlemden yönetilir; yalnız manuel fişler silinebilir.")
            return
        if soru(self, f"{f['fis_no']} numaralı fiş silinsin mi?"):
            db().ex("DELETE FROM yevmiye_satir WHERE yevmiye_id = ?", (f["id"],))
            db().sil("yevmiye", f["id"])
            self.yenile()

    def fis_pdf(self):
        f = self.t_fis.secili()
        if f:
            dosya_ac(belgeler.muhasebe_islem_fisi(cikti_yolu(f"MIF_{f['fis_no']}"), f["id"]))

    def yeniden_uret(self):
        if not yetki_kontrol(self, yonetici=True):
            return
        if soru(self, "Manuel fişler dışındaki tüm yardımcı yevmiye kayıtları silinip kaynak işlemlerden yeniden üretilecek. "
                      "Fiş numaraları değişebilir. Devam edilsin mi?"):
            n = muhasebe.tum_kayitlari_yeniden_uret()
            bilgi(self, f"Yevmiye yeniden üretildi. Toplam fiş: {n}")
            self.yenile()

    def mizan_yenile(self):
        m = muhasebe.mizan(self.bas.deger(), self.bit.deger())
        self._mizan = m
        self.t_mizan.doldur([Kolon("kod", "Hesap"), Kolon("ad", "Hesap adı"), Kolon("borc", "Borç toplamı", "para"),
                             Kolon("alacak", "Alacak toplamı", "para"), Kolon("borc_bakiye", "Borç bakiyesi", "para"),
                             Kolon("alacak_bakiye", "Alacak bakiyesi", "para")], m)
        tb, ta = yuvarla(sum(r["borc"] for r in m)), yuvarla(sum(r["alacak"] for r in m))
        durum = "<span style='color:green'>Denk</span>" if abs(tb - ta) < 0.01 else "<span style='color:#b00'>DENGESİZ</span>"
        self.l_mizan.setText(f"Borç: {para(tb)} • Alacak: {para(ta)} • {durum}")

    def mizan_pdf(self):
        m = self._mizan
        satir = [[r["kod"], r["ad"], r["borc"], r["alacak"], r["borc_bakiye"], r["alacak_bakiye"]] for r in m]
        top = ["", "TOPLAM"] + [yuvarla(sum(r[a] for r in m)) for a in ("borc", "alacak", "borc_bakiye", "alacak_bakiye")]
        dosya_ac(belgeler.genel_liste(cikti_yolu("Mizan"), f"GENEL GEÇİCİ MİZAN ({self.bas.deger()} / {self.bit.deger()})",
                                      ["Hesap", "Hesap adı", "Borç", "Alacak", "Borç bakiye", "Alacak bakiye"], satir, {2, 3, 4, 5}, top,
                                      "Yardımcı defter kayıtlarından üretilmiştir; resmi mizan BKMYBS'den alınır."))

    def gt_yenile(self):
        gt = muhasebe.gelir_tablosu(Oturum.yil)
        self._gt = gt
        satir = [dict(g, grup="Gelir") for g in gt["gelirler"]] + [dict(g, grup="Gider") for g in gt["giderler"]]
        self.t_gt.doldur([Kolon("grup", "Grup"), Kolon("kod", "Hesap"), Kolon("ad", "Hesap adı"), Kolon("tutar", "Tutar", "para")], satir)
        self.l_gt.setText(f"<b>Toplam gelir:</b> {para(gt['toplam_gelir'])} TL • <b>Toplam gider:</b> {para(gt['toplam_gider'])} TL • "
                          f"<b>Dönem {'kârı' if gt['kar'] >= 0 else 'zararı'}:</b> {para(abs(gt['kar']))} TL")

    def gt_pdf(self):
        gt = self._gt
        satir = [["Gelir", g["kod"], g["ad"], g["tutar"]] for g in gt["gelirler"]] + \
                [["Gider", g["kod"], g["ad"], g["tutar"]] for g in gt["giderler"]]
        satir += [["", "", "TOPLAM GELİR", gt["toplam_gelir"]], ["", "", "TOPLAM GİDER", gt["toplam_gider"]]]
        dosya_ac(belgeler.genel_liste(cikti_yolu(f"Gelir_Tablosu_{Oturum.yil}"), f"{Oturum.yil} YILI GELİR TABLOSU (YARDIMCI)",
                                      ["Grup", "Hesap", "Hesap adı", "Tutar"], satir, {3}, ["", "", "DÖNEM KÂRI / ZARARI", gt["kar"]]))

    def hesap_ekle(self):
        if not yetki_kontrol(self):
            return
        d = FormDialog(self, "Hesap ekle", [Alan("kod", "Hesap kodu", zorunlu=True), Alan("ad", "Hesap adı", zorunlu=True)])
        if d.exec():
            v = d.degerler()
            if db().q1("SELECT 1 FROM hesap_plani WHERE kod = ?", (v["kod"],)):
                uyari(self, "Bu kod zaten var.")
                return
            db().ex("INSERT INTO hesap_plani (kod, ad) VALUES (?, ?)", (v["kod"], v["ad"]))
            self.yenile()

    def hesap_sil(self):
        h = self.t_hp.secili()
        if not h or not yetki_kontrol(self, yonetici=True):
            return
        if db().deger("SELECT COUNT(*) FROM yevmiye_satir WHERE hesap_kodu = ?", (h["kod"],)):
            uyari(self, "Hareket gören hesap silinemez.")
            return
        if soru(self, f"{h['kod']} - {h['ad']} silinsin mi?"):
            db().ex("DELETE FROM hesap_plani WHERE kod = ?", (h["kod"],))
            self.yenile()


class ManuelFisDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Manuel muhasebe fişi")
        self.resize(900, 520)
        v = QVBoxLayout(self)
        u = QHBoxLayout()
        self.tarih = TarihKutusu()
        self.aciklama = QLineEdit()
        u.addWidget(QLabel("Tarih:"))
        u.addWidget(self.tarih)
        u.addWidget(QLabel("Açıklama:"))
        u.addWidget(self.aciklama, 1)
        v.addLayout(u)
        b = QHBoxLayout()
        b.addWidget(buton("＋ Satır", self.satir_ekle))
        b.addWidget(buton("Satırı sil", self.satir_sil))
        b.addStretch()
        self.denge = QLabel()
        b.addWidget(self.denge)
        v.addLayout(b)
        self.t = QTableWidget(0, 4)
        self.t.setHorizontalHeaderLabels(["Hesap", "Açıklama", "Borç", "Alacak"])
        self.t.horizontalHeader().setStretchLastSection(True)
        self.t.setColumnWidth(0, 300)
        self.t.setColumnWidth(1, 260)
        v.addWidget(self.t)
        bb = QHBoxLayout()
        bb.addStretch()
        bb.addWidget(buton("Kaydet", self.kaydet, "birincil"))
        bb.addWidget(buton("Vazgeç", self.reject))
        v.addLayout(bb)
        self.secenekler = hesap_secenekleri()
        self.satir_ekle()
        self.satir_ekle()

    def satir_ekle(self):
        r = self.t.rowCount()
        self.t.insertRow(r)
        h = SecimKutusu(secenekler=self.secenekler, bos=True)
        a = QLineEdit()
        bo, al_ = ParaKutusu(), ParaKutusu()
        for c, w in enumerate((h, a, bo, al_)):
            self.t.setCellWidget(r, c, w)
        bo.valueChanged.connect(self.kontrol)
        al_.valueChanged.connect(self.kontrol)
        self.kontrol()

    def satir_sil(self):
        r = self.t.currentRow()
        if r >= 0:
            self.t.removeRow(r)
            self.kontrol()

    def satirlar(self):
        s = []
        for r in range(self.t.rowCount()):
            h, a, b, c = (self.t.cellWidget(r, i) for i in range(4))
            if h.deger() and (b.deger() or c.deger()):
                s.append((h.deger(), a.text().strip() or self.aciklama.text().strip(), b.deger(), c.deger()))
        return s

    def kontrol(self):
        s = self.satirlar()
        tb, ta = yuvarla(sum(x[2] for x in s)), yuvarla(sum(x[3] for x in s))
        self.denge.setText(f"Borç: {para(tb)} • Alacak: {para(ta)} • " + ("Denk" if abs(tb - ta) < 0.01 and tb else "Denk değil"))
        return tb, ta

    def kaydet(self):
        s = self.satirlar()
        tb, ta = self.kontrol()
        if not s or abs(tb - ta) > 0.009 or not tb:
            uyari(self, "Fiş borç ve alacak toplamları eşit ve sıfırdan büyük olmalıdır.")
            return
        if not self.aciklama.text().strip():
            uyari(self, "Açıklama giriniz.")
            return
        muhasebe.fis_olustur(self.tarih.deger(), self.aciklama.text().strip(), "Manuel", None, s)
        db().log("Manuel fiş", "yevmiye", None, self.aciklama.text().strip())
        self.accept()
