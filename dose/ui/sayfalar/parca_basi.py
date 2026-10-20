"""Parça başı ücret bordrosu (Yönetmelik md.8, md.11)."""
import calendar
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ... import belgeler, excel, mevzuat, onay
from ...denetim import puantaj_coz, puantaj_yaz
from ...hesap import orantili_dagit, para, parca_basi_tavani, siparis_tahsis, tavan_uygula, ucret_kesintileri, yuvarla
from ...pdf import tarih_tr
from ..ortak import (Kolon, MesajKutusu, OranKutusu, Oturum, ParaKutusu, SecimKutusu, VeriTablosu, baslik_etiketi, bilgi,
                     bugun, buton, cikti_yolu, db, dosya_ac, kayit_izle, soru, uyari, yetki_kontrol)
from .onay_sayfa import onay_kaldir, onayla_veya_gonder


def kisi_bilgisi(kisi_turu: str, kisi_id: int) -> dict:
    if kisi_turu == "Personel":
        r = db().q1("SELECT ad_soyad ad, hizmet_sinifi, iban, tckn, 1 muvafakat, NULL sinif FROM personel WHERE id = ?", (kisi_id,))
    else:
        r = db().q1("SELECT ad_soyad ad, NULL hizmet_sinifi, iban, tckn, veli_muvafakat muvafakat, sinif FROM ogrenci WHERE id = ?",
                    (kisi_id,))
    return r or {"ad": "?", "hizmet_sinifi": None, "iban": None, "tckn": None, "muvafakat": 0, "sinif": None}


def ay_ici_diger_brut(yil, ay, kisi_turu, kisi_id, haric_pb_id) -> float:
    return db().deger("""SELECT SUM(r.brut) FROM parca_basi_satir r JOIN parca_basi pb ON pb.id = r.parca_basi_id
                         WHERE pb.yil = ? AND pb.ay = ? AND r.kisi_turu = ? AND r.kisi_id = ? AND pb.id != ?""",
                      (yil, ay, kisi_turu, kisi_id, haric_pb_id or 0), 0.0)


class PuantajDialog(QDialog):
    """Ay içinde kişi kişi, gün gün üretilen parça adedi (ya da çalışılan gün). Toplamlar katkı olarak kullanılır."""

    def __init__(self, parent, yil: int, ay: int, satirlar: list[dict], salt: bool = False, baslik: str | None = None,
                 aciklama: str | None = None, gun_renkleri: dict[int, str] | None = None, yukseklik: int = 620):
        super().__init__(parent)
        self.gun_sayisi = calendar.monthrange(yil, ay)[1]
        self.setWindowTitle(f"{baslik or 'Günlük üretim puantajı'} - {mevzuat.AYLAR[ay - 1]} {yil}")
        self.resize(1300, yukseklik)
        lay = QVBoxLayout(self)
        acik = QLabel(aciklama or (
            "Her kişinin gün gün ürettiği parça adedini (adet esası yoksa çalıştığı gün için 1) giriniz. Satır toplamları "
            "bordrodaki katkı sütununa aktarılır ve işçilik havuzu bu toplamlara göre dağıtılır (Yön. md.8/8). "
            "Hafta sonları gri gösterilir. Puantaj cetveli, parça başı sayfasındaki 'Puantaj cetveli PDF' ile yazdırılır."))
        acik.setWordWrap(True)
        lay.addWidget(acik)
        self.t = QTableWidget(len(satirlar), self.gun_sayisi + 3)
        self.t.setHorizontalHeaderLabels(["Tür", "Adı soyadı"] + [str(g) for g in range(1, self.gun_sayisi + 1)] + ["Toplam"])
        self.t.verticalHeader().setVisible(False)
        if gun_renkleri is None:
            gun_renkleri = {g: "#e6e6e6" for g in range(1, self.gun_sayisi + 1) if date(yil, ay, g).weekday() >= 5}
        self.hafta_sonu = set(gun_renkleri)
        for r, s in enumerate(satirlar):
            for c, metin in ((0, s["tur"]), (1, s["bilgi"]["ad"])):
                it = QTableWidgetItem(metin)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.t.setItem(r, c, it)
            for g in range(1, self.gun_sayisi + 1):
                v = s.get("puantaj", {}).get(g)
                it = QTableWidgetItem("" if not v else (str(int(v)) if float(v).is_integer() else str(v)))
                it.setTextAlignment(Qt.AlignCenter)
                if g in gun_renkleri:
                    it.setBackground(QColor(gun_renkleri[g]))
                if salt:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.t.setItem(r, g + 1, it)
            top = QTableWidgetItem()
            top.setFlags(top.flags() & ~Qt.ItemIsEditable)
            top.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.t.setItem(r, self.gun_sayisi + 2, top)
            self._toplam(r)
        self.t.resizeColumnToContents(0)
        self.t.setColumnWidth(1, 190)
        for g in range(1, self.gun_sayisi + 1):
            self.t.setColumnWidth(g + 1, 34)
        self.t.itemChanged.connect(self._degisti)
        lay.addWidget(self.t)
        bb = QHBoxLayout()
        if not salt:
            bb.addWidget(buton("Tümünü temizle", self._temizle, "tehlike"))
        bb.addStretch()
        if not salt:
            bb.addWidget(buton("Tamam", self.accept, "birincil"))
        bb.addWidget(buton("Kapat" if salt else "İptal", self.reject))
        lay.addLayout(bb)

    @staticmethod
    def _sayi(metin: str) -> float | None:
        metin = (metin or "").strip().replace(",", ".")
        if not metin:
            return 0.0
        try:
            v = float(metin)
            return v if v >= 0 else None
        except ValueError:
            return None

    def _toplam(self, r):
        t = sum(self._sayi(self.t.item(r, g + 1).text()) or 0 for g in range(1, self.gun_sayisi + 1))
        self.t.blockSignals(True)
        self.t.item(r, self.gun_sayisi + 2).setText(f"{t:g}")
        self.t.blockSignals(False)

    def _degisti(self, it: QTableWidgetItem):
        if not 2 <= it.column() <= self.gun_sayisi + 1:
            return
        if self._sayi(it.text()) is None:
            self.t.blockSignals(True)
            it.setText("")
            self.t.blockSignals(False)
        self._toplam(it.row())

    def _temizle(self):
        if soru(self, "Puantajdaki bütün değerler silinsin mi?"):
            self.t.blockSignals(True)
            for r in range(self.t.rowCount()):
                for g in range(1, self.gun_sayisi + 1):
                    self.t.item(r, g + 1).setText("")
            self.t.blockSignals(False)
            for r in range(self.t.rowCount()):
                self._toplam(r)

    def sonuc(self) -> list[dict[int, float]]:
        return [{g: v for g in range(1, self.gun_sayisi + 1) if (v := self._sayi(self.t.item(r, g + 1).text()))}
                for r in range(self.t.rowCount())]


def onceki_kumulatif(yil, ay, kisi_turu, kisi_id, haric_pb_id) -> float:
    """Aynı yıl içinde DÖSE'den daha önce ödenen ücretlerin toplamı (GV kümülatif matrahı için varsayılan)."""
    pb = db().deger("""SELECT SUM(r.brut) FROM parca_basi_satir r JOIN parca_basi p ON p.id = r.parca_basi_id
                       WHERE p.yil = ? AND (p.ay < ? OR (p.ay = ? AND p.id < ?)) AND r.kisi_turu = ? AND r.kisi_id = ?
                       AND p.id != ?""", (yil, ay, ay, haric_pb_id or 10 ** 9, kisi_turu, kisi_id, haric_pb_id or 0), 0.0)
    fc = 0.0
    if kisi_turu == "Personel":
        fc = db().deger("SELECT SUM(brut) FROM fazla_calisma WHERE yil = ? AND ay < ? AND personel_id = ?", (yil, ay, kisi_id), 0.0)
    return yuvarla(pb + fc)


class ParcaBasiSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "Parça Başı Ücret Bordrosu",
            "Ay içinde geçici kabulü yapılan işlerin işçilik bedeli, öğrenci hakkı (en az %30) ayrıldıktan sonra personel ve öğrencilere "
            "katkıları oranında dağıtılır. Aylık tavanlar (eğitim-öğretim 2x, teknik 1,5x, diğer 1x, öğrenci 1x asgari ücret) bütün "
            "siparişler toplamında uygulanır; aynı iş için fazla çalışma ücreti ödenemez (Yön. md.8)."))
        ust = QHBoxLayout()
        self.b_yeni = buton("＋ Yeni bordro", self.yeni, "birincil")
        ust.addWidget(self.b_yeni)
        ust.addWidget(buton("Aç / Düzenle", self.duzenle))
        ust.addWidget(buton("Onayla", self.onayla))
        ust.addWidget(buton("Onayı kaldır", self.onay_kaldir))
        ust.addWidget(buton("Sil", self.sil, "tehlike"))
        ust.addWidget(buton("Bordro PDF", self.pdf))
        ust.addWidget(buton("Puantaj cetveli PDF", self.puantaj_pdf,
                            ipucu="Gün gün parça adedi, toplam adet, brüt ücret ve imza sütunlu cetvel. Puantaj girilmemişse "
                                  "ay boyunca elle doldurulacak boş cetvel yazdırılır."))
        ust.addWidget(buton("Banka listesi (Excel)", self.banka_listesi))
        ust.addWidget(buton("Ödeme kaydı oluştur", self.odeme_kaydi,
                            ipucu="Net tutar için kasa/banka 'Personel Ödemesi' çıkışı oluşturur."))
        ust.addStretch()
        lay.addLayout(ust)
        self.tablo = VeriTablosu()
        self.tablo.satirCiftTiklandi.connect(lambda _s: self.duzenle())
        lay.addWidget(self.tablo)
        self.ozet = QLabel()
        lay.addWidget(self.ozet)
        self.yenile()

    def yenile(self):
        kosul, prm = "pb.yil = ?", [Oturum.yil]
        if Oturum.bolum_id():
            kosul += " AND s.bolum_id = ?"
            prm.append(Oturum.bolum_id())
        if Oturum.ogretmen():
            kosul += " AND r.kisi_turu = 'Personel' AND r.kisi_id = ?"
            prm.append(Oturum.personel_id() or -1)
        satirlar = db().q(f"""SELECT pb.*, s.siparis_no, s.konu, COUNT(r.id) kisi, SUM(r.brut) brut, SUM(r.tavan_asimi) asim,
                                     SUM(r.gelir_vergisi + r.damga_vergisi) vergi, SUM(r.net) net
                              FROM parca_basi pb LEFT JOIN siparis s ON s.id = pb.siparis_id
                              LEFT JOIN parca_basi_satir r ON r.parca_basi_id = pb.id
                              WHERE {kosul} GROUP BY pb.id, s.siparis_no, s.konu ORDER BY pb.ay DESC, pb.id DESC""", prm)
        durumlar = onay.durumlar("Parça Başı")
        for s in satirlar:
            s["ay_ad"] = mevzuat.AYLAR[s["ay"] - 1]
            s["onay"] = onay.durum_metni(durumlar[s["id"]]) if s["id"] in durumlar else (
                onay.ONAYLANDI if s["durum"] == "Onaylandı" else onay.HAZIRLANIYOR)
        self.tablo.doldur(
            [Kolon("ay_ad", "Ay"), Kolon("siparis_no", "Sipariş"), Kolon("konu", "Konu"),
             Kolon("kabul_edilen_iscilik", "Kabul edilen işçilik", "para"), Kolon("ogrenci_orani", "Öğrenci oranı", "oran"),
             Kolon("kisi", "Kişi", "sayi"), Kolon("brut", "Brüt", "para"), Kolon("asim", "Tavan aşımı", "para"),
             Kolon("vergi", "GV + DV", "para"), Kolon("net", "Net", "para"), Kolon("onay", "Onay durumu"),
             Kolon("onay_tarihi", "Onay tarihi", "tarih")],
            satirlar, lambda s: "#eef6ee" if s["durum"] == "Onaylandı" else ("#fff4e5" if s["onay"].startswith("Bekliyor") else None))
        self.ozet.setText(f"{Oturum.yil} toplam brüt: {para(sum(s['brut'] or 0 for s in satirlar))} TL • Net: "
                          f"{para(sum(s['net'] or 0 for s in satirlar))} TL" + ("  (yalnız size ait tutarlar)" if Oturum.ogretmen() else ""))
        self.b_yeni.setEnabled(Oturum.yazabilir(self))

    def yeni(self):
        if yetki_kontrol(self) and ParcaBasiDialog(self).exec():
            self.yenile()

    def duzenle(self):
        s = self.tablo.secili()
        if not s:
            return
        if Oturum.ogretmen():
            bilgi(self, "Bordrodaki size ait tutarlar listede gösterilmektedir.")
            return
        if ParcaBasiDialog(self, s["id"]).exec():
            self.yenile()

    def onayla(self):
        s = self.tablo.secili()
        if not s:
            return
        if onayla_veya_gonder(self, "Parça Başı", s["id"],
                              "Bordro onaylansın mı? Onaydan sonra yardımcı yevmiye kaydı (720 / 360-361-335) oluşturulur."):
            self.yenile()

    def onay_kaldir(self):
        s = self.tablo.secili()
        if s and s["durum"] == "Onaylandı" and onay_kaldir(self, "Parça Başı", s["id"], "Onay kaldırılsın mı? Yevmiye kaydı silinir."):
            self.yenile()

    def sil(self):
        s = self.tablo.secili()
        if not s or not yetki_kontrol(self):
            return
        if s["durum"] == "Onaylandı":
            uyari(self, "Onaylı bordro silinemez; önce onayı kaldırınız.")
            return
        if onay.durum("Parça Başı", s["id"])["durum"] == onay.BEKLIYOR:
            uyari(self, "Onay sürecindeki bordro silinemez; önce geri çekiniz.")
            return
        if soru(self, "Taslak bordro silinsin mi?"):
            with db().islem():
                db().ex("DELETE FROM parca_basi_satir WHERE parca_basi_id = ?", (s["id"],))
                db().sil("parca_basi", s["id"])
                onay.sil("Parça Başı", s["id"])
            self.yenile()

    def pdf(self):
        s = self.tablo.secili()
        if s and not Oturum.ogretmen():
            dosya_ac(belgeler.parca_basi_bordrosu(cikti_yolu(f"ParcaBasi_{s['siparis_no']}_{s['yil']}_{s['ay']:02d}"), s["id"]))

    def puantaj_pdf(self):
        s = self.tablo.secili()
        if s and not Oturum.ogretmen():
            dosya_ac(belgeler.parca_basi_puantaj(cikti_yolu(f"Puantaj_{s['siparis_no']}_{s['yil']}_{s['ay']:02d}"), s["id"]))

    def banka_listesi(self):
        s = self.tablo.secili()
        if not s or Oturum.ogretmen():
            return
        satirlar = []
        for r in db().q("SELECT * FROM parca_basi_satir WHERE parca_basi_id = ? AND net > 0", (s["id"],)):
            k = kisi_bilgisi(r["kisi_turu"], r["kisi_id"])
            satirlar.append([k["ad"], k["tckn"] or "", k["iban"] or "", r["net"],
                             f"{mevzuat.AYLAR[s['ay'] - 1]} {s['yil']} parça başı ücret"])
        yol = cikti_yolu(f"Banka_ParcaBasi_{s['siparis_no']}_{s['ay']:02d}", "xlsx")
        excel.disa_aktar(yol, [("Banka listesi", ["Adı soyadı", "T.C. kimlik no", "IBAN", "Net tutar", "Açıklama"], satirlar)],
                         "Parça başı ücret banka ödeme listesi")
        eksik = [x[0] for x in satirlar if not x[2]]
        if eksik:
            uyari(self, "IBAN bilgisi eksik kişiler:\n" + "\n".join(eksik))
        dosya_ac(yol)

    def odeme_kaydi(self):
        s = self.tablo.secili()
        if not s or not yetki_kontrol(self, sayfa="Kasa / Banka"):
            return
        if s["durum"] != "Onaylandı":
            uyari(self, "Önce bordroyu onaylayınız.")
            return
        if db().deger("SELECT COUNT(*) FROM kasa_banka WHERE kaynak = 'ParcaBasi' AND kaynak_id = ?", (s["id"],)):
            uyari(self, "Bu bordro için ödeme kaydı zaten var.")
            return
        from .kasa import KasaDialog
        on = {"yon": "Çıkış", "tur": "Personel Ödemesi", "tutar": s["net"], "hesap": "Banka (102)", "siparis_id": s["siparis_id"],
              "aciklama": f"{mevzuat.AYLAR[s['ay'] - 1]} {s['yil']} parça başı ücret ({s['siparis_no']})",
              "kaynak": "ParcaBasi", "kaynak_id": s["id"]}
        KasaDialog(self, on_deger=on).exec()


class ParcaBasiDialog(QDialog):
    KOLONLAR = ["Tür", "Adı soyadı", "Katkı (% / adet)", "Hesaplanan", "Aylık tavan", "Ay içi diğer", "Brüt", "Tavan aşımı",
                "Önceki kümülatif", "Gelir v.", "Damga v.", "SGK (işveren)", "Net"]

    def __init__(self, parent, pb_id: int | None = None):
        super().__init__(parent)
        kayit_izle(self, "parca_basi", pb_id)
        self.pb_id = pb_id
        self.pb = db().q1("SELECT * FROM parca_basi WHERE id = ?", (pb_id,)) if pb_id else {}
        self.yil = self.pb.get("yil") or Oturum.yil
        self.p = db().parametreler(self.yil)
        surecte = bool(pb_id) and onay.durum("Parça Başı", pb_id)["durum"] == onay.BEKLIYOR
        self.salt = self.pb.get("durum") == "Onaylandı" or surecte
        self.setWindowTitle(f"Parça başı bordrosu - {self.yil}" + (
            " (ONAYLI - salt okunur)" if self.pb.get("durum") == "Onaylandı" else " (ONAY SÜRECİNDE - salt okunur)" if surecte else ""))
        self.resize(1250, 760)
        lay = QVBoxLayout(self)
        g = QGridLayout()
        self.ay = SecimKutusu(secenekler=[(i + 1, a) for i, a in enumerate(mevzuat.AYLAR)])
        kisit = Oturum.bolum_id()
        self.siparis = SecimKutusu(secenekler=[(r["id"], f"{r['siparis_no']} - {r['konu'] or ''} ({r['durum']})") for r in db().q(
            "SELECT id, siparis_no, konu, durum FROM siparis WHERE ucret_esasi NOT LIKE 'Fazla%' AND durum NOT IN "
            "('İptal', 'Talep Alındı', 'Keşif / İş Planı', 'Teklif', 'Proforma İletildi') "
            + ("AND bolum_id = ? " if kisit else "") + "ORDER BY id DESC", (kisit,) if kisit else ())], bos=True)
        self.kabul = ParaKutusu()
        self.ogr = OranKutusu()
        self.aciklama = QLineEdit()
        self.sip_bilgi = QLabel()
        self.sip_bilgi.setWordWrap(True)
        g.addWidget(QLabel("Ay:"), 0, 0)
        g.addWidget(self.ay, 0, 1)
        g.addWidget(QLabel("Sipariş *:"), 0, 2)
        g.addWidget(self.siparis, 0, 3, 1, 3)
        g.addWidget(QLabel("Ay içinde kabul edilen işçilik:"), 1, 0)
        g.addWidget(self.kabul, 1, 1)
        g.addWidget(QLabel("Öğrenci hakkı oranı:"), 1, 2)
        g.addWidget(self.ogr, 1, 3)
        g.addWidget(QLabel("Açıklama:"), 1, 4)
        g.addWidget(self.aciklama, 1, 5)
        g.addWidget(self.sip_bilgi, 2, 0, 1, 6)
        lay.addLayout(g)

        ust = QHBoxLayout()
        self.b_getir = buton("Siparişteki görevlileri getir", self.gorevlileri_getir, "birincil")
        self.b_ekle = buton("＋ Kişi ekle", self.kisi_ekle)
        self.b_sil = buton("Satırı sil", self.satir_sil)
        self.b_esit = buton("Katkıları eşitle", self.esitle, ipucu="Her grupta katkı oranlarını eşit dağıtır.")
        self.b_puantaj = buton("Günlük puantaj…", self.puantaj,
                               ipucu="Kişi kişi, gün gün üretilen parça adedini girin; toplamlar katkı olarak kullanılır.")
        for b in (self.b_getir, self.b_ekle, self.b_sil, self.b_esit, self.b_puantaj):
            ust.addWidget(b)
        ust.addStretch()
        lay.addLayout(ust)
        self.t = QTableWidget(0, len(self.KOLONLAR))
        self.t.setHorizontalHeaderLabels(self.KOLONLAR)
        self.t.horizontalHeaderItem(2).setToolTip(
            "Katkı oranı (%) ya da kişinin ürettiği parça adedi girilebilir. Havuz, her grupta (personel / öğrenci) "
            "girilen değerlerin toplamına oranlanarak dağıtılır; toplamın 100 olması gerekmez.")
        self.t.verticalHeader().setVisible(False)
        self.t.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        lay.addWidget(self.t)
        alt = QHBoxLayout()
        self.mesaj = MesajKutusu()
        alt.addWidget(self.mesaj, 1)
        self.toplam = QLabel()
        self.toplam.setAlignment(Qt.AlignRight | Qt.AlignTop)
        alt.addWidget(self.toplam)
        lay.addLayout(alt)
        bb = QHBoxLayout()
        bb.addStretch()
        self.b_kaydet = buton("Kaydet", self.kaydet, "birincil")
        bb.addWidget(self.b_kaydet)
        bb.addWidget(buton("Kapat", self.reject))
        lay.addLayout(bb)

        self.satirlar: list[dict] = []
        self.ay.ayarla(self.pb.get("ay") or (int(bugun()[5:7]) if int(bugun()[:4]) == self.yil else 12))
        self.siparis.ayarla(self.pb.get("siparis_id"))
        self.kabul.ayarla(self.pb.get("kabul_edilen_iscilik"))
        self.ogr.ayarla(self.pb.get("ogrenci_orani") or self.p["ogrenci_hakki_orani"])
        self.aciklama.setText(self.pb.get("aciklama") or "")
        for r in db().q("SELECT * FROM parca_basi_satir WHERE parca_basi_id = ? ORDER BY kisi_turu DESC, id", (pb_id or 0,)):
            self._satir_ekle(r["kisi_turu"], r["kisi_id"], r["katki"], r["onceki_kumulatif"], puantaj_coz(r.get("puantaj")))
        self._siparis_bilgisi(ilk=True)
        self.siparis.currentIndexChanged.connect(lambda: self._siparis_bilgisi())
        self.ay.currentIndexChanged.connect(self.yeniden_hesapla)
        self.kabul.valueChanged.connect(self.hesapla)
        self.ogr.valueChanged.connect(self.hesapla)
        if self.salt:
            for w in (self.b_getir, self.b_ekle, self.b_sil, self.b_esit, self.b_kaydet, self.ay, self.siparis, self.kabul, self.ogr):
                w.setEnabled(False)
        self.hesapla()

    # ------------------------------------------------------------ sipariş
    def _siparis_bilgisi(self, ilk=False):
        sid = self.siparis.deger()
        if not sid:
            self.sip_bilgi.setText("")
            self.tahsis = None
            return
        s = db().q1("SELECT * FROM siparis WHERE id = ?", (sid,))
        t = siparis_tahsis(s["sozlesme_bedeli"] or 0, s["ucret_esasi"], self.p, s["malzeme_maliyeti"] or 0,
                           s["iscilik_tutari"] or None, s["kar_orani"], s["ogrenci_hakki_orani"], s["pesinat"] or 0,
                           bool(s["ogrenci_uygulamasi"]), bool(s["malzeme_musteriden"]))
        self.tahsis = t
        onceki = db().deger("SELECT SUM(kabul_edilen_iscilik) FROM parca_basi WHERE siparis_id = ? AND id != ?", (sid, self.pb_id or 0), 0.0)
        kalan = yuvarla(t.iscilik - onceki)
        tahsil = db().deger("""SELECT SUM(tutar) FROM kasa_banka WHERE yon = 'Giriş' AND (siparis_id = ? OR fatura_id IN
                               (SELECT id FROM fatura WHERE siparis_id = ? AND iptal = 0))""", (sid, sid), 0.0)
        faturalanan = db().deger("SELECT SUM(matrah) FROM fatura WHERE siparis_id = ? AND tur = 'Satış' AND iptal = 0",
                                 (sid,), 0.0) or 0.0
        bedel = s["sozlesme_bedeli"] or 0
        self._siparis = s
        self._kalan_iscilik = kalan
        self._tahsil = tahsil
        self._onceki_iscilik = onceki or 0.0
        self._faturalanan = faturalanan
        self._faturalanan_iscilik = yuvarla(t.iscilik * min(faturalanan / bedel, 1)) if bedel else 0.0
        self.sip_bilgi.setText(
            f"Sözleşme bedeli: {para(bedel)} TL • Toplam işçilik: {para(t.iscilik)} TL • Önceki bordrolarda dağıtılan: "
            f"{para(onceki)} TL • Kalan: {para(kalan)} TL • Faturalanan: {para(faturalanan)} TL (işçilik payı "
            f"{para(self._faturalanan_iscilik)} TL) • Tahsil edilen: {para(tahsil)} TL • Durum: {s['durum']}")
        if not ilk:
            self.kabul.ayarla(max(kalan, 0))
            self.ogr.ayarla(max(s["ogrenci_hakki_orani"] or 0, self.p["ogrenci_hakki_orani"]))
        self.hesapla()

    def gorevlileri_getir(self):
        sid = self.siparis.deger()
        if not sid:
            uyari(self, "Önce sipariş seçiniz.")
            return
        mevcut = {(r["tur"], r["id"]) for r in self.satirlar}
        for g in db().q("SELECT kisi_turu, kisi_id FROM siparis_gorevli WHERE siparis_id = ?", (sid,)):
            if (g["kisi_turu"], g["kisi_id"]) not in mevcut:
                self._satir_ekle(g["kisi_turu"], g["kisi_id"], 0, None)
        self.esitle()

    def kisi_ekle(self):
        d = QDialog(self)
        d.setWindowTitle("Kişi ekle")
        d.resize(420, 520)
        v = QVBoxLayout(d)
        tur = SecimKutusu(secenekler=["Personel", "Öğrenci"])
        v.addWidget(tur)
        liste = QListWidget()
        v.addWidget(liste)

        def doldur():
            liste.clear()
            if tur.deger() == "Personel":
                rows = db().q("SELECT id, ad_soyad ad, dose_gorevi ek FROM personel WHERE aktif = 1 ORDER BY ad_soyad")
            else:
                rows = db().q("SELECT id, ad_soyad ad, COALESCE(sinif, '') || CASE WHEN veli_muvafakat = 1 THEN '' ELSE ' - MUVAFAKAT YOK' END ek "
                              "FROM ogrenci WHERE aktif = 1 ORDER BY ad_soyad")
            for r in rows:
                it = QListWidgetItem(f"{r['ad']} ({r['ek'] or ''})")
                it.setData(Qt.UserRole, r["id"])
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Unchecked)
                liste.addItem(it)
        tur.currentIndexChanged.connect(doldur)
        doldur()
        v.addWidget(buton("Ekle", d.accept, "birincil"))
        if d.exec():
            mevcut = {(r["tur"], r["id"]) for r in self.satirlar}
            for i in range(liste.count()):
                it = liste.item(i)
                kid = it.data(Qt.UserRole)
                if it.checkState() == Qt.Checked and (tur.deger(), kid) not in mevcut:
                    self._satir_ekle(tur.deger(), kid, 0, None)
            self.hesapla()

    # ------------------------------------------------------------ tablo
    def _satir_ekle(self, tur, kid, katki, onceki, puantaj=None):
        bilgi_ = kisi_bilgisi(tur, kid)
        r = self.t.rowCount()
        self.t.insertRow(r)
        k_katki = ParaKutusu(ondalik=3, azami=100000)
        k_katki.ayarla(katki)
        k_onceki = ParaKutusu()
        if onceki is None:
            onceki = onceki_kumulatif(self.yil, self.ay.deger(), tur, kid, self.pb_id)
        k_onceki.ayarla(onceki)
        k_onceki.setToolTip("GV kümülatif matrahı. Kişinin maaş bordrosundaki yıl içi kümülatif matrah esas alınacaksa buraya giriniz.")
        self.t.setItem(r, 0, QTableWidgetItem(tur))
        self.t.setItem(r, 1, QTableWidgetItem(bilgi_["ad"]))
        self.t.setCellWidget(r, 2, k_katki)
        self.t.setCellWidget(r, 8, k_onceki)
        for c in (3, 4, 5, 6, 7, 9, 10, 11, 12):
            it = QTableWidgetItem()
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.t.setItem(r, c, it)
        self.satirlar.append({"tur": tur, "id": kid, "katki_k": k_katki, "onceki_k": k_onceki, "bilgi": bilgi_,
                              "puantaj": puantaj or {}})
        k_katki.valueChanged.connect(self.hesapla)
        k_onceki.valueChanged.connect(self.hesapla)
        if self.salt:
            k_katki.setEnabled(False)
            k_onceki.setEnabled(False)

    def satir_sil(self):
        r = self.t.currentRow()
        if r >= 0:
            self.t.removeRow(r)
            del self.satirlar[r]
            self.hesapla()

    def esitle(self):
        for tur in ("Personel", "Öğrenci"):
            grup = [s for s in self.satirlar if s["tur"] == tur]
            for s in grup:
                s["katki_k"].blockSignals(True)
                s["katki_k"].ayarla(round(100 / len(grup), 3))
                s["katki_k"].blockSignals(False)
        self.hesapla()

    def puantaj(self):
        if not self.satirlar:
            uyari(self, "Önce bordroya kişi ekleyiniz (ör. 'Siparişteki görevlileri getir').")
            return
        d = PuantajDialog(self, self.yil, self.ay.deger(), self.satirlar, self.salt)
        if not d.exec() or self.salt:
            return
        sonuc = d.sonuc()
        for s, p in zip(self.satirlar, sonuc):
            s["puantaj"] = p
        if any(sonuc):
            for s in self.satirlar:
                s["katki_k"].blockSignals(True)
                s["katki_k"].ayarla(sum(s["puantaj"].values()))
                s["katki_k"].blockSignals(False)
        self.hesapla()

    def yeniden_hesapla(self):
        for s in self.satirlar:
            s["onceki_k"].blockSignals(True)
            s["onceki_k"].ayarla(onceki_kumulatif(self.yil, self.ay.deger(), s["tur"], s["id"], self.pb_id))
            s["onceki_k"].blockSignals(False)
        self.hesapla()

    def hesapla(self):
        if not hasattr(self, "toplam"):
            return
        ay = self.ay.deger()
        kabul = self.kabul.deger()
        ogr_oran = self.ogr.deger()
        havuz = {"Öğrenci": yuvarla(kabul * ogr_oran), "Personel": yuvarla(kabul - yuvarla(kabul * ogr_oran))}
        hatalar, uyarilar = [], []
        paylar = {}
        for tur in ("Personel", "Öğrenci"):
            grup = {i: s["katki_k"].deger() for i, s in enumerate(self.satirlar) if s["tur"] == tur}
            if grup and not any(grup.values()) and havuz[tur] > 0:
                hatalar.append(f"{tur} katkı oranları girilmemiş.")
            if not grup and havuz[tur] > 0:
                uyarilar.append(f"{tur} bulunmadığından {para(havuz[tur])} TL dağıtılamayacak.")
            paylar.update(orantili_dagit(havuz[tur], grup))
        puantajli = any(s["puantaj"] for s in self.satirlar)
        gun_sayisi = calendar.monthrange(self.yil, ay)[1]
        kabul_gunu = None
        sip = getattr(self, "_siparis", None) if self.siparis.deger() else None
        if sip and sip.get("kabul_tarihi") and str(sip["kabul_tarihi"])[:7] == f"{self.yil}-{ay:02d}":
            kabul_gunu = int(str(sip["kabul_tarihi"])[8:10])
        self.sonuclar = []
        for i, s in enumerate(self.satirlar):
            hes = paylar.get(i, 0.0)
            tavan = parca_basi_tavani(s["tur"], s["bilgi"]["hizmet_sinifi"], self.p)
            diger = ay_ici_diger_brut(self.yil, ay, s["tur"], s["id"], self.pb_id)
            brut, asim = tavan_uygula(hes, diger, tavan)
            k = ucret_kesintileri(brut, s["onceki_k"].deger(), ay, self.p, ogrenci=s["tur"] == "Öğrenci")
            sonuc = {"kisi_turu": s["tur"], "kisi_id": s["id"], "katki": s["katki_k"].deger(), "hesaplanan": hes, "brut": brut,
                     "tavan_asimi": asim, "onceki_kumulatif": s["onceki_k"].deger(), "gelir_vergisi": k.gelir_vergisi,
                     "damga_vergisi": k.damga_vergisi, "sgk": k.sgk, "net": k.net, "puantaj": puantaj_yaz(s["puantaj"])}
            self.sonuclar.append(sonuc)
            for c, v in ((3, hes), (4, tavan), (5, diger), (6, brut), (7, asim), (9, k.gelir_vergisi), (10, k.damga_vergisi),
                         (11, k.sgk), (12, k.net)):
                self.t.item(i, c).setText(para(v))
            renk = Qt.white
            if s["tur"] == "Öğrenci" and not s["bilgi"]["muvafakat"]:
                hatalar.append(f"{s['bilgi']['ad']}: veli muvafakatnamesi yok (Yön. md.8/6).")
                renk = Qt.red
            elif asim > 0:
                renk = Qt.yellow
            self.t.item(i, 1).setBackground(renk)
            if asim > 0:
                uyarilar.append(f"{s['bilgi']['ad']}: aylık tavan ({para(tavan)} TL) aşıldı, {para(asim)} TL ödenmeyecek.")
            if not s["bilgi"]["iban"]:
                uyarilar.append(f"{s['bilgi']['ad']}: IBAN bilgisi eksik.")
            if s["tur"] == "Öğrenci" and str(s["bilgi"].get("sinif") or "").strip().startswith("9"):
                uyarilar.append(f"{s['bilgi']['ad']}: 9. sınıf öğrencisi. Döner sermayeden ücret, üretimde fiilen çalışan alan/dal "
                                "öğrencilerine ödenir (Çalışma Yönergesi md.42/f: ilk sınıf öğrencilerine ödeme yapılmaz).")
            if puantajli:
                pt = sum(s["puantaj"].values())
                if abs(pt - s["katki_k"].deger()) > 0.0005:
                    uyarilar.append(f"{s['bilgi']['ad']}: katkı ({s['katki_k'].deger():g}) puantaj toplamından ({pt:g}) farklı; "
                                    f"dağıtım puantajla belgelenmelidir (Yön. md.8/8).")
                if any(g > gun_sayisi for g in s["puantaj"]):
                    uyarilar.append(f"{s['bilgi']['ad']}: puantajda seçilen ayda olmayan günler var.")
                if kabul_gunu and any(g > kabul_gunu for g in s["puantaj"]):
                    uyarilar.append(f"{s['bilgi']['ad']}: geçici kabul tarihinden ({kabul_gunu}. gün) sonraki günlere üretim "
                                    f"girilmiş; yalnız kabulü yapılan iş ödenir (Yön. md.8/8-a).")
            if s["tur"] == "Personel" and self.siparis.deger() and db().deger(
                    "SELECT COUNT(*) FROM fazla_calisma WHERE personel_id = ? AND siparis_id = ?", (s["id"], self.siparis.deger())):
                hatalar.append(f"{s['bilgi']['ad']}: aynı sipariş için fazla çalışma ücreti kaydı var (Yön. md.8/7).")
        if not self.siparis.deger():
            hatalar.append("Sipariş seçiniz.")
        else:
            if ogr_oran + 1e-9 < self.p["ogrenci_hakki_orani"]:
                hatalar.append(f"Öğrenci hakkı işçiliğin en az %{self.p['ogrenci_hakki_orani'] * 100:.0f}'i olmalıdır (Yön. md.8/3).")
            if kabul > getattr(self, "_kalan_iscilik", 0) + 0.009:
                hatalar.append(f"Kabul edilen işçilik, siparişin dağıtılmamış işçilik tutarını ({para(self._kalan_iscilik)} TL) aşıyor.")
            sip = getattr(self, "_siparis", None)
            if sip and not sip["kabul_tarihi"] and sip["durum"] not in ("Tamamlandı (Geçici Kabul)", "Faturalandı", "Kapandı"):
                hatalar.append("Siparişin geçici muayene ve kabulü yapılmamış; parça başı ücret yalnız ay içinde bitirilen ve geçici "
                               "muayene ve kabulü yapılan işin işçiliğinden ödenir (Yön. md.8/8-a).")
            elif sip and sip["kabul_tarihi"] and str(sip["kabul_tarihi"])[:7] > f"{self.yil}-{ay:02d}":
                uyarilar.append(f"Geçici kabul tarihi ({tarih_tr(sip['kabul_tarihi'])}) bordro ayından sonra; bordro ayı içinde "
                                f"bitirilip kabulü yapılan kısım yoksa ödeme kabul ayının bordrosuna alınmalıdır (Yön. md.8/8-a).")
            if sip and kabul > 0:
                dagitilan = yuvarla(getattr(self, "_onceki_iscilik", 0) + kabul)
                fi = getattr(self, "_faturalanan_iscilik", 0)
                if dagitilan > fi + 0.009:
                    uyarilar.append(
                        f"Bu bordroyla birlikte dağıtılan işçilik ({para(dagitilan)} TL), faturalanan kısmın işçilik payını "
                        f"({para(fi)} TL) aşıyor. Teslim edilen iş için fatura teslimden itibaren 7 gün içinde düzenlenir "
                        f"(VUK md.231/5); teslim edilen kısım için önce fatura kesiniz ya da kabul edilen işçiliği faturalanan "
                        f"kısımla sınırlayınız. İşin tamamı teslim edilmediyse yalnız teslim edilip kabulü yapılan kısmın "
                        f"işçiliği ödenir (Yön. md.8/8-a).")
            if sip and getattr(self, "_tahsil", 0) + 0.009 < (sip["sozlesme_bedeli"] or 0) * (1 + (sip["kdv_orani"] or 0)):
                uyarilar.append("İş bedelinin tamamı henüz tahsil edilmemiş; ödeme planlamasında dikkate alınız.")
        top = lambda a: yuvarla(sum(x[a] for x in self.sonuclar))
        self.toplam.setText(f"<b>Hesaplanan:</b> {para(top('hesaplanan'))}<br><b>Brüt:</b> {para(top('brut'))}<br>"
                            f"<b>Tavan aşımı:</b> {para(top('tavan_asimi'))}<br><b>GV + DV:</b> "
                            f"{para(top('gelir_vergisi') + top('damga_vergisi'))}<br><b>Net:</b> {para(top('net'))}")
        self.mesaj.goster(list(dict.fromkeys(hatalar)), list(dict.fromkeys(uyarilar)), "Bordro mevzuat kontrolleri tamam.")
        self._hatalar = hatalar

    def kaydet(self):
        if not yetki_kontrol(self):
            return
        self.hesapla()
        if not self.siparis.deger() or not self.satirlar:
            uyari(self, "Sipariş ve en az bir kişi gereklidir.")
            return
        if self._hatalar and not soru(self, "Mevzuat hataları var (onay aşamasında engellenecek). Taslak olarak kaydedilsin mi?\n\n"
                                      + "\n".join(dict.fromkeys(self._hatalar))):
            return
        v = {"yil": self.yil, "ay": self.ay.deger(), "siparis_id": self.siparis.deger(), "kabul_edilen_iscilik": self.kabul.deger(),
             "ogrenci_orani": self.ogr.deger(), "aciklama": self.aciklama.text().strip() or None, "durum": "Taslak"}
        if self.salt:
            uyari(self, "Onaylı veya onay sürecindeki bordro değiştirilemez.")
            return
        with db().islem():
            if self.pb_id:
                db().guncelle("parca_basi", self.pb_id, v)
            else:
                self.pb_id = db().ekle("parca_basi", v)
            db().ex("DELETE FROM parca_basi_satir WHERE parca_basi_id = ?", (self.pb_id,))
            for s in self.sonuclar:
                db().ekle("parca_basi_satir", dict(s, parca_basi_id=self.pb_id), log=False)
        self.accept()
