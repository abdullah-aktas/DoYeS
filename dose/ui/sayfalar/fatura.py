"""Satış faturaları ve alış / gider belgeleri."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QRadioButton, QTableWidget, QVBoxLayout, QWidget)

from ... import mevzuat, muhasebe
from ...hesap import belge_toplami, iskonto_dagit, kalem_hatalari, kalem_tutari, oran_yazi, para, yuvarla
from ..ortak import (Kolon, MesajKutusu, OranKutusu, Oturum, ParaKutusu, SecimKutusu, TarihKutusu, VeriTablosu,
                     baslik_etiketi, bilgi, buton, db, fk_secenekleri, hata, kayit_izle, satir_odagini_izle, soru,
                     tablo_excele, uyari, yetki_kontrol)


class FaturaSayfasi(QWidget):
    TUR = "Satış"

    def __init__(self):
        super().__init__()
        satis = self.TUR == "Satış"
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "Satış Faturaları" if satis else "Alış / Gider Belgeleri",
            "Mal ve hizmet satışları. İskonto, hesaplanan KDV, KDV tevkifatı ve sipariş avansı mahsubu otomatik hesaplanır; yardımcı "
            "yevmiye kaydı üretilir. e-Fatura/e-Arşiv düzenlemesi GİB/entegratör portalında yapılır, belge numarası buraya işlenir."
            if satis else
            "Fatura, müstahsil makbuzu ve serbest meslek makbuzu ile yapılan alımlar. İskontolu faturalarda birim fiyatı iskontosuz "
            "girip iskontoyu ilgili sütuna yazın. Stopaj (GVK md.94), KDV tevkifatı ve doğrudan temin limiti kontrol edilir; stoklu "
            "malzemeler iskonto sonrası maliyetle otomatik olarak stoğa girer."))
        ust = QHBoxLayout()
        self.b_yeni = buton("＋ Yeni " + ("Satış Faturası" if satis else "Alış Belgesi"), self.yeni, "birincil")
        ust.addWidget(self.b_yeni)
        ust.addWidget(buton("Düzenle", self.duzenle))
        ust.addWidget(buton("İptal et", self.iptal, "tehlike"))
        ust.addWidget(buton("Tahsilat gir" if satis else "Ödeme gir", self.odeme))
        ust.addWidget(buton("Excel'e Aktar", lambda: tablo_excele(self, self.tablo, "Satislar" if satis else "Alislar")))
        if not satis:
            ust.addWidget(buton("Doğrudan temin belgeleri…", self.dogrudan_temin,
                                ipucu="Firmalara piyasa fiyat teklif mektubu, piyasa fiyat araştırma tutanağı ve onay belgesi "
                                      "(4734 md.22/d). Seçili alış belgesi varsa kalemleri oradan alınır."))
        ust.addStretch()
        ust.addWidget(QLabel("Ay:"))
        self.ay = SecimKutusu(secenekler=[(0, "Tüm yıl")] + [(i + 1, a) for i, a in enumerate(mevzuat.AYLAR)])
        self.ay.currentIndexChanged.connect(self.yenile)
        ust.addWidget(self.ay)
        lay.addLayout(ust)
        self.tablo = VeriTablosu()
        self.tablo.satirCiftTiklandi.connect(lambda _s: self.duzenle())
        lay.addWidget(self.tablo)
        self.ozet = QLabel()
        lay.addWidget(self.ozet)
        self.yenile()

    def yenile(self):
        donem = f"{Oturum.yil}" + (f"-{self.ay.deger():02d}" if self.ay.deger() else "")
        satirlar = db().q(
            """SELECT f.*, c.unvan, s.siparis_no,
                      f.net_tutar - COALESCE(f.avans_mahsup, 0) - COALESCE((SELECT SUM(tutar) FROM kasa_banka k WHERE k.fatura_id = f.id), 0) kalan
               FROM fatura f LEFT JOIN cari c ON c.id = f.cari_id LEFT JOIN siparis s ON s.id = f.siparis_id
               WHERE f.tur = ? AND f.tarih LIKE ? ORDER BY f.tarih DESC, f.id DESC""", (self.TUR, donem + "%"))
        for s in satirlar:
            s["durum"] = "İPTAL" if s["iptal"] else ("Kapandı" if abs(s["kalan"]) < 0.01 else "Açık")
        kolonlar = [Kolon("tarih", "Tarih", "tarih"), Kolon("belge_turu", "Belge türü"), Kolon("belge_no", "Belge no"),
                    Kolon("unvan", "Cari"), Kolon("siparis_no", "Sipariş"), Kolon("iskonto", "İskonto", "para"),
                    Kolon("matrah", "Matrah", "para"),
                    Kolon("kdv", "KDV", "para"), Kolon("tevkif_kdv", "Tevkif KDV", "para")]
        if self.TUR == "Alış":
            kolonlar += [Kolon("stopaj", "Stopaj", "para"), Kolon("gider_turu", "Gider türü"), Kolon("temin_usulu", "Temin usulü")]
        else:
            kolonlar += [Kolon("avans_mahsup", "Avans mahsubu", "para")]
        kolonlar += [Kolon("genel_toplam", "Genel toplam", "para"), Kolon("net_tutar", "Net tutar", "para"),
                     Kolon("kalan", "Kalan", "para"), Kolon("durum", "Durum")]
        self.tablo.doldur(kolonlar, satirlar, lambda s: "#eeeeee" if s["iptal"] else None)
        gecerli = [s for s in satirlar if not s["iptal"]]
        self.ozet.setText(f"{len(gecerli)} belge • Matrah: {para(sum(s['matrah'] for s in gecerli))} TL • KDV: "
                          f"{para(sum(s['kdv'] for s in gecerli))} TL • Açık bakiye: {para(sum(s['kalan'] for s in gecerli))} TL")
        self.b_yeni.setEnabled(Oturum.yazabilir(self))

    def yeni(self):
        if yetki_kontrol(self) and FaturaDialog(self, self.TUR).exec():
            self.yenile()

    def duzenle(self):
        s = self.tablo.secili()
        if not s:
            return
        if s["iptal"]:
            uyari(self, "İptal edilmiş belge düzenlenemez.")
            return
        if FaturaDialog(self, self.TUR, s["id"]).exec():
            self.yenile()

    def iptal(self):
        s = self.tablo.secili()
        if not s or s["iptal"] or not yetki_kontrol(self):
            return
        if db().deger("SELECT COUNT(*) FROM kasa_banka WHERE fatura_id = ?", (s["id"],)):
            uyari(self, "Belgeye bağlı tahsilat/ödeme kaydı var. Önce o kayıtları siliniz.")
            return
        if soru(self, f"{s['belge_no'] or ''} numaralı belge iptal edilsin mi? Stok hareketleri ve yevmiye kaydı geri alınır."):
            db().guncelle("fatura", s["id"], {"iptal": 1})
            db().ex("DELETE FROM stok_hareket WHERE kaynak = 'Fatura' AND kaynak_id = ?", (s["id"],))
            muhasebe.fatura_kaydi(s["id"])
            self.yenile()

    def odeme(self):
        s = self.tablo.secili()
        if not s or s["iptal"] or not yetki_kontrol(self):
            return
        from .kasa import KasaDialog
        kalan = muhasebe.fatura_kalan(s["id"])
        if kalan <= 0.009:
            bilgi(self, "Belgenin açık bakiyesi yok.")
            return
        on = {"yon": "Giriş" if self.TUR == "Satış" else "Çıkış", "tur": "Tahsilat" if self.TUR == "Satış" else "Ödeme",
              "tutar": kalan, "cari_id": s["cari_id"], "fatura_id": s["id"], "siparis_id": s["siparis_id"],
              "aciklama": f"{s['belge_no'] or ''} nolu belge"}
        if KasaDialog(self, on_deger=on).exec():
            self.yenile()


    def dogrudan_temin(self):
        DogrudanTeminDialog(self, self.tablo.secili()).exec()


class DogrudanTeminDialog(QDialog):
    def __init__(self, parent, fatura: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Doğrudan temin belgeleri (4734 md.22/d)")
        self.resize(820, 640)
        lay = QVBoxLayout(self)
        acik = QLabel("Piyasa araştırmasında teklif istenen firmaları ve verdikleri toplam teklifleri (KDV hariç) girin. En düşük teklif "
                      "tutanakta 'en uygun' olarak işaretlenir ve yaklaşık maliyet olarak önerilir. Tek PDF içinde firmalara "
                      "gönderilecek boş teklif mektupları, piyasa fiyat araştırma tutanağı ve onay belgesi üretilir.")
        acik.setWordWrap(True)
        lay.addWidget(acik)
        f = QFormLayout()
        self.konu = QLineEdit(((fatura or {}).get("aciklama") or "") if fatura else "")
        self.tarih = TarihKutusu()
        self.sayi = QLineEdit()
        self.gider = SecimKutusu(secenekler=list(mevzuat.GIDER_TURLERI.keys()))
        self.gorevliler = QLineEdit()
        self.gorevliler.setPlaceholderText("Ör. Ümit Zirek, Ramazan Adsoy")
        self.teslim_yeri = QLineEdit("İşletme atölyesine")
        self.yaklasik = ParaKutusu()
        f.addRow("İşin adı *:", self.konu)
        f.addRow("Tarih:", self.tarih)
        f.addRow("Onay belgesi sayısı:", self.sayi)
        f.addRow("Gider türü:", self.gider)
        f.addRow("Piyasa araştırması görevlileri:", self.gorevliler)
        f.addRow("Teslim yeri:", self.teslim_yeri)
        f.addRow("Yaklaşık maliyet (KDV hariç):", self.yaklasik)
        lay.addLayout(f)
        lay.addWidget(QLabel("<b>Alınacak mal / hizmet</b>"))
        self.kt = QTableWidget(0, 3)
        self.kt.setHorizontalHeaderLabels(["Adı ve özellikleri", "Miktar", "Birim"])
        self.kt.horizontalHeader().setStretchLastSection(False)
        self.kt.setColumnWidth(0, 480)
        self.kt.verticalHeader().setVisible(False)
        lay.addWidget(self.kt)
        kb = QHBoxLayout()
        kb.addWidget(buton("＋ Satır", lambda: self._satir(self.kt, ["", "", ""])))
        kb.addWidget(buton("Satırı sil", lambda: self.kt.removeRow(self.kt.currentRow()) if self.kt.currentRow() >= 0 else None))
        kb.addStretch()
        lay.addLayout(kb)
        lay.addWidget(QLabel("<b>Teklif alınan firmalar</b> (en az üç firmadan teklif alınması önerilir)"))
        self.ft = QTableWidget(0, 2)
        self.ft.setHorizontalHeaderLabels(["Firma / kişi", "Toplam teklif (KDV hariç, TL)"])
        self.ft.setColumnWidth(0, 480)
        self.ft.verticalHeader().setVisible(False)
        self.ft.setMaximumHeight(150)
        lay.addWidget(self.ft)
        self.ft.itemChanged.connect(lambda _it: self._en_dusuk())
        self.mesaj = QLabel()
        self.mesaj.setWordWrap(True)
        lay.addWidget(self.mesaj)
        bb = QHBoxLayout()
        bb.addStretch()
        bb.addWidget(buton("PDF oluştur", self.olustur, "birincil"))
        bb.addWidget(buton("Kapat", self.reject))
        lay.addLayout(bb)

        if fatura and not fatura.get("iptal"):
            self.tarih.ayarla(fatura.get("tarih"))
            self.gider.ayarla(fatura.get("gider_turu"))
            for k in db().q("""SELECT k.aciklama, k.miktar, k.birim, m.ad FROM fatura_kalem k LEFT JOIN malzeme m ON m.id = k.malzeme_id
                               WHERE k.fatura_id = ? ORDER BY k.id""", (fatura["id"],)):
                self._satir(self.kt, [" - ".join(x for x in (k["ad"], k["aciklama"]) if x), f"{k['miktar']:g}", k["birim"] or ""])
            if not self.konu.text():
                self.konu.setText(", ".join(self.kt.item(r, 0).text() for r in range(self.kt.rowCount()))[:120])
            self._satir(self.ft, [fatura.get("unvan") or "", f"{fatura.get('matrah') or 0:.2f}"])
        while self.kt.rowCount() < 1:
            self._satir(self.kt, ["", "", ""])
        while self.ft.rowCount() < 3:
            self._satir(self.ft, ["", ""])
        self._en_dusuk()

    @staticmethod
    def _satir(t: QTableWidget, degerler):
        from PySide6.QtWidgets import QTableWidgetItem
        t.blockSignals(True)
        r = t.rowCount()
        t.insertRow(r)
        for c, v in enumerate(degerler):
            t.setItem(r, c, QTableWidgetItem(str(v)))
        t.blockSignals(False)

    @staticmethod
    def _sayi(metin) -> float:
        try:
            return float(str(metin or "").replace(".", "").replace(",", ".") if "," in str(metin or "") else str(metin or 0))
        except ValueError:
            return 0.0

    def _firmalar(self):
        sonuc = []
        for r in range(self.ft.rowCount()):
            ad = (self.ft.item(r, 0).text() if self.ft.item(r, 0) else "").strip()
            if ad:
                sonuc.append({"ad": ad, "tutar": self._sayi(self.ft.item(r, 1).text() if self.ft.item(r, 1) else "")})
        return sonuc

    def _en_dusuk(self):
        teklifler = [f for f in self._firmalar() if f["tutar"] > 0]
        p = db().parametreler(Oturum.yil)
        limit = p["dogrudan_temin_buyuksehir" if db().kurum().get("buyuksehir") else "dogrudan_temin_diger"]
        notlar = []
        if teklifler:
            en = min(teklifler, key=lambda f: f["tutar"])
            self.yaklasik.ayarla(en["tutar"])
            notlar.append(f"En uygun teklif: {en['ad']} - {para(en['tutar'])} TL.")
            if en["tutar"] > limit:
                notlar.append(f"⛔ Tutar doğrudan temin limitini ({para(limit)} TL) aşıyor (4734 md.22/d); ihale usulü gerekir.")
        if len(self._firmalar()) < 3:
            notlar.append("⚠ Piyasa araştırmasında en az üç firmadan teklif alınması önerilir.")
        self.mesaj.setText("  ".join(notlar))

    def olustur(self):
        if not self.konu.text().strip():
            uyari(self, "İşin adını giriniz.")
            return
        from ... import belgeler
        from ..ortak import cikti_yolu, dosya_ac
        kalemler = [{"ad": self.kt.item(r, 0).text() if self.kt.item(r, 0) else "",
                     "miktar": self.kt.item(r, 1).text() if self.kt.item(r, 1) else "",
                     "birim": self.kt.item(r, 2).text() if self.kt.item(r, 2) else ""} for r in range(self.kt.rowCount())]
        d = {"konu": self.konu.text().strip(), "tarih": self.tarih.deger(), "sayi": self.sayi.text().strip(),
             "gider_turu": self.gider.deger(), "kalemler": kalemler, "firmalar": self._firmalar(),
             "gorevliler": [g.strip() for g in self.gorevliler.text().split(",") if g.strip()],
             "yaklasik_maliyet": self.yaklasik.deger(), "teslim_yeri": self.teslim_yeri.text().strip()}
        dosya_ac(belgeler.dogrudan_temin_dosyasi(cikti_yolu(f"Dogrudan_Temin_{self.tarih.deger() or ''}"), d))


class SatisSayfasi(FaturaSayfasi):
    TUR = "Satış"


class AlisSayfasi(FaturaSayfasi):
    TUR = "Alış"


class FaturaDialog(QDialog):
    KOLONLAR = ["Ürün / hizmet", "Açıklama", "Miktar", "Birim", "Birim fiyat (KDV hariç, iskontosuz)", "İsk. %", "İsk. TL",
                "KDV", "Tutar (KDV dahil)"]
    K_KDV, K_TUTAR = 7, 8

    def __init__(self, parent, tur: str, fatura_id: int | None = None, siparis_id: int | None = None):
        super().__init__(parent)
        kayit_izle(self, "fatura", fatura_id)
        self.tur, self.fid = tur, fatura_id
        self.satis = tur == "Satış"
        self.f = db().q1("SELECT * FROM fatura WHERE id = ?", (fatura_id,)) if fatura_id else {}
        self.p = db().parametreler(int((self.f.get("tarih") or str(Oturum.yil))[:4]))
        self.kurum = db().kurum()
        self.setWindowTitle(("Satış faturası" if self.satis else "Alış / gider belgesi") + (f" - {self.f.get('belge_no') or ''}" if fatura_id else ""))
        self.resize(1150, 720)
        lay = QVBoxLayout(self)

        g = QGridLayout()
        self.belge_turu = SecimKutusu(secenekler=mevzuat.SATIS_BELGE_TURLERI if self.satis else mevzuat.ALIS_BELGE_TURLERI)
        self.no = QLineEdit()
        self.tarih = TarihKutusu()
        kosul = "aktif = 1 AND tur != 'Tedarikçi' AND tur != 'Çiftçi (Müstahsil)'" if self.satis else "aktif = 1 AND tur != 'Müşteri'"
        self.cari = SecimKutusu(secenekler=fk_secenekleri("cari", "unvan", kosul), bos=True)
        self.siparis = SecimKutusu(secenekler=fk_secenekleri("siparis", "siparis_no || ' - ' || COALESCE(konu, '')",
                                                             "durum != 'İptal'", "id DESC"), bos=True)
        self.aciklama = QLineEdit()
        self.tevkifat = SecimKutusu(secenekler=list(mevzuat.TEVKIFAT_ORANLARI.keys()))
        g.addWidget(QLabel("Belge türü:"), 0, 0)
        g.addWidget(self.belge_turu, 0, 1)
        g.addWidget(QLabel("Belge no:"), 0, 2)
        g.addWidget(self.no, 0, 3)
        g.addWidget(QLabel("Tarih:"), 0, 4)
        g.addWidget(self.tarih, 0, 5)
        g.addWidget(QLabel("Cari *:"), 1, 0)
        g.addWidget(self.cari, 1, 1, 1, 3)
        g.addWidget(QLabel("Sipariş:"), 1, 4)
        g.addWidget(self.siparis, 1, 5)
        g.addWidget(QLabel("Açıklama:"), 2, 0)
        g.addWidget(self.aciklama, 2, 1, 1, 3)
        g.addWidget(QLabel("KDV tevkifatı:"), 2, 4)
        g.addWidget(self.tevkifat, 2, 5)
        if self.satis:
            self.avans = ParaKutusu()
            g.addWidget(QLabel("Sipariş avansı mahsubu:"), 3, 0)
            g.addWidget(self.avans, 3, 1)
            self.avans_bilgi = QLabel()
            g.addWidget(self.avans_bilgi, 3, 2, 1, 4)
        else:
            self.gider = SecimKutusu(secenekler=list(mevzuat.GIDER_TURLERI.keys()))
            self.temin = SecimKutusu(secenekler=mevzuat.TEMIN_USULLERI)
            self.stopaj = SecimKutusu(secenekler=list(mevzuat.STOPAJ_TURLERI.keys()))
            g.addWidget(QLabel("Gider türü:"), 3, 0)
            g.addWidget(self.gider, 3, 1)
            g.addWidget(QLabel("Temin usulü:"), 3, 2)
            g.addWidget(self.temin, 3, 3)
            g.addWidget(QLabel("Stopaj:"), 3, 4)
            g.addWidget(self.stopaj, 3, 5)
        lay.addLayout(g)

        ust = QHBoxLayout()
        ust.addWidget(buton("＋ Kalem", lambda: self.kalem_ekle()))
        ust.addWidget(buton("Kalemi sil", self.kalem_sil))
        if self.satis:
            ust.addWidget(buton("Sipariş kalemlerini getir", self.siparisten))
        ust.addWidget(buton("Genel iskonto…", self.genel_iskonto,
                            ipucu="Belgenin altında toplu gösterilen iskontoyu (tutar veya yüzde) kalemlere tutarları oranında dağıtır."))
        ust.addStretch()
        lay.addLayout(ust)
        ipucu = QLabel("💡 İskontolu belgede birim fiyatı <b>iskontosuz</b> (liste fiyatı) yazın; iskontoyu <b>İsk. %</b> ya da "
                       "<b>İsk. TL</b> sütununa girin, diğeri kendiliğinden hesaplanır. Belgenin altında toplu iskonto varsa "
                       "<b>Genel iskonto…</b> düğmesini kullanın. KDV" + ("" if self.satis else " ve stopaj") +
                       " iskonto sonrası tutardan hesaplanır (KDV K. md.25/a). İndirimi eksi satır olarak girmeyin.")
        ipucu.setWordWrap(True)
        ipucu.setObjectName("sayfaAciklama")
        lay.addWidget(ipucu)
        self.kt = QTableWidget(0, len(self.KOLONLAR))
        self.kt.setHorizontalHeaderLabels(["Ürün / hizmet" if self.satis else "Stok malzemesi"] + self.KOLONLAR[1:])
        self.kt.horizontalHeaderItem(5).setToolTip("Kalem iskonto oranı (%). Girince iskonto tutarı hesaplanır.")
        self.kt.horizontalHeaderItem(6).setToolTip("Kalem iskonto tutarı (TL). Girince iskonto oranı hesaplanır.")
        self.kt.horizontalHeader().setStretchLastSection(True)
        self.kt.verticalHeader().setVisible(False)
        satir_odagini_izle(self.kt)
        lay.addWidget(self.kt)
        if self.satis:
            self.secenek_kaynak = db().q("SELECT id, ad, birim, satis_fiyati fiyat, kdv_orani FROM urun WHERE aktif = 1 ORDER BY ad")
        else:
            self.secenek_kaynak = db().q("SELECT id, ad, birim, 0 fiyat, kdv_orani FROM malzeme WHERE aktif = 1 ORDER BY ad")

        alt = QHBoxLayout()
        self.mesaj = MesajKutusu()
        alt.addWidget(self.mesaj, 1)
        gt = QGroupBox("Toplamlar")
        ft = QFormLayout(gt)
        self.lbl = {}
        for a, e in [("brut", "Ara toplam (iskontosuz)"), ("iskonto", "İskonto"), ("matrah", "Matrah"), ("kdv", "KDV"),
                     ("tevkif_kdv", "Tevkif edilen KDV"), ("stopaj", "Stopaj"), ("genel_toplam", "Genel toplam"),
                     ("net_tutar", "Net " + ("tahsil edilecek" if self.satis else "ödenecek"))]:
            self.lbl[a] = QLabel()
            self.lbl[a].setAlignment(Qt.AlignRight)
            ft.addRow(e + ":", self.lbl[a])
        self.kontrol_toplam = ParaKutusu()
        self.kontrol_toplam.setToolTip("Kâğıt/e-belgedeki KDV dahil genel toplamı yazın. Program hesapladığı genel toplamla "
                                       "karşılaştırır; fark varsa kaydetmeye izin vermez. Boş (0) bırakılırsa karşılaştırma yapılmaz.")
        ft.addRow("Belgedeki genel toplam (kontrol):", self.kontrol_toplam)
        alt.addWidget(gt)
        lay.addLayout(alt)
        bb = QHBoxLayout()
        bb.addStretch()
        bb.addWidget(buton("Kaydet", self.kaydet, "birincil"))
        bb.addWidget(buton("Vazgeç", self.reject))
        lay.addLayout(bb)

        self._doldur(siparis_id)
        self.belge_turu.currentIndexChanged.connect(self._belge_turu_degisti)
        self.tevkifat.currentIndexChanged.connect(self.hesapla)
        self.kontrol_toplam.valueChanged.connect(self.hesapla)
        self.cari.currentIndexChanged.connect(self.hesapla)
        self.no.textChanged.connect(self.hesapla)
        self.tarih.dateChanged.connect(self.hesapla)
        self.siparis.currentIndexChanged.connect(self._siparis_degisti)
        if not self.satis:
            self.stopaj.currentIndexChanged.connect(self.hesapla)
            self.gider.currentIndexChanged.connect(self.hesapla)
            self.temin.currentIndexChanged.connect(self.hesapla)
        else:
            self.avans.valueChanged.connect(self.hesapla)
        self.hesapla()

    # ------------------------------------------------------------
    def _doldur(self, siparis_id):
        f = self.f
        self.belge_turu.ayarla(f.get("belge_turu") or ("e-Arşiv Fatura" if self.satis else "e-Fatura"))
        self.no.setText(f.get("belge_no") or "")
        self.tarih.ayarla(f.get("tarih"))
        self.aciklama.setText(f.get("aciklama") or "")
        self.tevkifat.ayarla(f.get("tevkifat") or "Yok")
        sid = f.get("siparis_id") or siparis_id
        self.siparis.ayarla(sid)
        if self.satis:
            self.avans.ayarla(f.get("avans_mahsup"))
        else:
            self.gider.ayarla(f.get("gider_turu") or list(mevzuat.GIDER_TURLERI.keys())[0])
            self.temin.ayarla(f.get("temin_usulu") or "Doğrudan Temin")
            self.stopaj.ayarla(f.get("stopaj_turu") or "Yok")
        if f.get("cari_id"):
            self.cari.ayarla(f["cari_id"])
        for k in db().q("SELECT * FROM fatura_kalem WHERE fatura_id = ? ORDER BY id", (self.fid or 0,)):
            self.kalem_ekle(k)
        if not self.fid and sid:
            s = db().q1("SELECT * FROM siparis WHERE id = ?", (sid,))
            if s:
                self.cari.ayarla(s["cari_id"])
                if self.satis:
                    self.siparisten()
                    self._avans_oner(sid)

    def _avans_oner(self, sid):
        if not self.satis or not sid:
            return
        alinan = db().deger("SELECT SUM(tutar) FROM kasa_banka WHERE siparis_id = ? AND tur = 'Peşinat/Avans Tahsilatı'", (sid,), 0.0)
        mahsup = db().deger("SELECT SUM(avans_mahsup) FROM fatura WHERE siparis_id = ? AND iptal = 0 AND id != ?", (sid, self.fid or 0), 0.0)
        kalan = yuvarla(alinan - mahsup)
        self.avans_bilgi.setText(f"Siparişe tahsil edilen avans: {para(alinan)} TL, mahsup edilmemiş: {para(kalan)} TL")
        if not self.fid and kalan > 0:
            self.avans.ayarla(kalan)
        self._avans_kalan = kalan + (self.f.get("avans_mahsup") or 0)

    def _siparis_degisti(self):
        sid = self.siparis.deger()
        if sid:
            s = db().q1("SELECT cari_id FROM siparis WHERE id = ?", (sid,))
            if s and not self.cari.deger():
                self.cari.ayarla(s["cari_id"])
            self._avans_oner(sid)

    def _belge_turu_degisti(self):
        if self.satis:
            return
        bt = self.belge_turu.deger()
        if bt.startswith("Müstahsil"):
            self.stopaj.ayarla("Zirai Ürün - Bitkisel (%2)")
            for r in range(self.kt.rowCount()):
                self.kt.cellWidget(r, self.K_KDV).ayarla(0)
        elif bt.startswith("Serbest"):
            self.stopaj.ayarla("Serbest Meslek (%20)")
            self.gider.ayarla("Hizmet Alımı")
        else:
            self.stopaj.ayarla("Yok")
        self.hesapla()

    def siparisten(self):
        sid = self.siparis.deger()
        if not sid:
            uyari(self, "Önce sipariş seçiniz.")
            return
        s = db().q1("SELECT kdv_orani FROM siparis WHERE id = ?", (sid,))
        faturalanan = db().q("SELECT k.urun_id, SUM(k.miktar) m FROM fatura_kalem k JOIN fatura f ON f.id = k.fatura_id "
                             "WHERE f.siparis_id = ? AND f.iptal = 0 AND f.id != ? GROUP BY k.urun_id", (sid, self.fid or 0))
        onceki = {r["urun_id"]: r["m"] for r in faturalanan}
        while self.kt.rowCount():
            self.kt.removeRow(0)
        for kl in db().q("SELECT * FROM siparis_kalem WHERE siparis_id = ?", (sid,)):
            kalan = yuvarla(kl["miktar"] - onceki.get(kl["urun_id"], 0), 3)
            if kalan > 0:
                self.kalem_ekle({"urun_id": kl["urun_id"], "aciklama": kl["aciklama"], "miktar": kalan, "birim": kl["birim"],
                                 "birim_fiyat": kl["birim_fiyat"], "iskonto_orani": kl.get("iskonto_orani") or 0,
                                 "kdv_orani": s["kdv_orani"]})
        self.hesapla()

    def kalem_ekle(self, kl=None):
        kl = kl or {}
        r = self.kt.rowCount()
        self.kt.insertRow(r)
        sec = SecimKutusu(secenekler=[(x["id"], x["ad"]) for x in self.secenek_kaynak], bos=True)
        sec.ayarla(kl.get("urun_id") if self.satis else kl.get("malzeme_id"))
        ack = QLineEdit(kl.get("aciklama") or "")
        mik = ParaKutusu(ondalik=3)
        mik.ayarla(kl.get("miktar") if kl else 1)
        birim = SecimKutusu(secenekler=mevzuat.BIRIMLER, duzenlenebilir=True)
        birim.ayarla(kl.get("birim") or "Adet")
        bf = ParaKutusu(ondalik=4)
        bf.ayarla(kl.get("birim_fiyat"))
        isk_o = OranKutusu()
        isk_t = ParaKutusu()
        kdv = OranKutusu()
        kdv.ayarla(kl.get("kdv_orani") if kl.get("kdv_orani") is not None else
                   (0 if (not self.satis and self.belge_turu.deger().startswith(("Müstahsil", "Gider"))) else self.p["kdv_genel"]))
        tutar = QLabel()
        tutar.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        for c, w in enumerate((sec, ack, mik, birim, bf, isk_o, isk_t, kdv, tutar)):
            self.kt.setCellWidget(r, c, w)

        # Kullanıcının en son yazdığı iskonto alanı (oran / tutar) esas alınır, diğeri ondan hesaplanır.
        durum = {"esas": "tutar" if kl.get("iskonto") is not None else "oran"}

        def brut():
            return yuvarla(mik.deger() * bf.deger())

        def ayarla_sessiz(kutu, deger):
            kutu.blockSignals(True)
            kutu.ayarla(deger)
            kutu.blockSignals(False)

        def esitle():
            if durum["esas"] == "oran":
                ayarla_sessiz(isk_t, yuvarla(brut() * isk_o.deger()))
            else:
                ayarla_sessiz(isk_o, min(max(isk_t.deger() / brut(), 0.0), 1.0) if brut() else 0.0)
            self.hesapla()

        def oran_girildi():
            durum["esas"] = "oran"
            esitle()

        def tutar_girildi():
            durum["esas"] = "tutar"
            esitle()

        if kl.get("iskonto") is not None:
            ayarla_sessiz(isk_t, kl["iskonto"])
            ayarla_sessiz(isk_o, kl.get("iskonto_orani") or 0)
        else:
            ayarla_sessiz(isk_o, kl.get("iskonto_orani") or 0)
            ayarla_sessiz(isk_t, yuvarla(brut() * isk_o.deger()))
        isk_o.valueChanged.connect(oran_girildi)
        isk_t.valueChanged.connect(tutar_girildi)

        def secildi():
            x = next((y for y in self.secenek_kaynak if y["id"] == sec.deger()), None)
            if x:
                if x["fiyat"]:
                    bf.ayarla(x["fiyat"])
                birim.ayarla(x["birim"])
                if not (not self.satis and self.belge_turu.deger().startswith("Müstahsil")):
                    kdv.ayarla(x["kdv_orani"])
                if not ack.text():
                    ack.setText(x["ad"])
        sec.currentIndexChanged.connect(secildi)
        for w in (mik, bf):
            w.valueChanged.connect(esitle)
        kdv.valueChanged.connect(self.hesapla)
        self.kt.setColumnWidth(0, 200)
        self.kt.setColumnWidth(1, 200)
        self.kt.setColumnWidth(5, 70)
        self.kt.setColumnWidth(6, 95)
        self.hesapla()

    def kalem_sil(self):
        r = self.kt.currentRow()
        if r < 0:
            uyari(self, "Silinecek kalemin herhangi bir kutusuna tıklayıp yeniden deneyiniz.")
            return
        self.kt.removeRow(r)
        self.hesapla()

    def kalemler(self):
        sonuc = []
        for r in range(self.kt.rowCount()):
            w = [self.kt.cellWidget(r, c) for c in range(len(self.KOLONLAR))]
            k = {"aciklama": w[1].text().strip() or None, "miktar": w[2].deger(), "birim": w[3].deger(),
                 "birim_fiyat": w[4].deger(), "iskonto_orani": w[5].deger(), "iskonto": w[6].deger(),
                 "kdv_orani": w[self.K_KDV].deger()}
            k["urun_id" if self.satis else "malzeme_id"] = w[0].deger()
            k["tutar"] = kalem_tutari(k)[2]
            k["kdv"] = yuvarla(k["tutar"] * k["kdv_orani"])
            sonuc.append(k)
        return sonuc

    def genel_iskonto(self):
        kalemler = self.kalemler()
        net = yuvarla(sum(k["tutar"] for k in kalemler))
        if not kalemler or net <= 0:
            uyari(self, "Önce kalemleri miktar ve birim fiyatlarıyla giriniz.")
            return
        d = QDialog(self)
        d.setWindowTitle("Genel (belge altı) iskonto")
        v = QVBoxLayout(d)
        acik = QLabel(f"Kalemlerin iskonto sonrası toplamı: <b>{para(net)} TL</b>.<br>Belgenin altındaki toplu iskontoyu yazın; "
                      "kalemlere tutarları oranında, kuruşu kuruşuna dağıtılır ve her kalemin mevcut iskontosuna eklenir.")
        acik.setWordWrap(True)
        v.addWidget(acik)
        grup = QButtonGroup(d)
        r_tutar, r_oran = QRadioButton("Tutar (TL)"), QRadioButton("Oran (%)")
        r_tutar.setChecked(True)
        h = QHBoxLayout()
        for rb in (r_tutar, r_oran):
            grup.addButton(rb)
            h.addWidget(rb)
        v.addLayout(h)
        deger = ParaKutusu(ondalik=3)
        v.addWidget(deger)
        sonuc = QLabel()
        v.addWidget(sonuc)

        def toplam():
            return yuvarla(net * deger.deger() / 100) if r_oran.isChecked() else yuvarla(deger.deger())

        def goster():
            t = toplam()
            sonuc.setText(f"Dağıtılacak iskonto: <b>{para(t)} TL</b>" + (
                "  ⛔ Toplamı aşamaz / eksi olamaz." if t < 0 or t > net or (r_oran.isChecked() and deger.deger() > 100) else ""))
        deger.valueChanged.connect(goster)
        r_oran.toggled.connect(goster)
        bb = QHBoxLayout()
        bb.addStretch()
        bb.addWidget(buton("Uygula", d.accept, "birincil"))
        bb.addWidget(buton("Vazgeç", d.reject))
        v.addLayout(bb)
        goster()
        if not d.exec():
            return
        t = toplam()
        if t <= 0 or t > net + 0.005:
            uyari(self, f"İskonto sıfırdan büyük ve kalemler toplamından ({para(net)} TL) küçük olmalıdır.")
            return
        paylar = iskonto_dagit([{"miktar": 1, "birim_fiyat": k["tutar"]} for k in kalemler], t)
        for r, pay in enumerate(paylar):
            kutu = self.kt.cellWidget(r, 6)
            kutu.ayarla(yuvarla(kutu.deger() + pay))
        self.hesapla()

    def stopaj_orani(self) -> float:
        if self.satis:
            return 0.0
        v = mevzuat.STOPAJ_TURLERI.get(self.stopaj.deger(), 0.0)
        return self.p[v] if isinstance(v, str) else float(v)

    def hesapla(self):
        if not hasattr(self, "lbl"):
            return None
        kalemler = self.kalemler()
        for r, k in enumerate(kalemler):
            self.kt.cellWidget(r, self.K_TUTAR).setText(para(k["tutar"] + k["kdv"]))
        t = belge_toplami(kalemler, mevzuat.TEVKIFAT_ORANLARI.get(self.tevkifat.deger(), 0.0), self.stopaj_orani())
        for a, l in self.lbl.items():
            l.setText(para(getattr(t, a)))
        # onayli: kaydederken kullanıcıdan ayrıca onay istenen (hata olasılığı yüksek) uyarılar
        hatalar, uyarilar, onayli = kalem_hatalari(kalemler), [], []
        for i, k in enumerate(kalemler, 1):
            if k["miktar"] > 0 and k["birim_fiyat"] > 0 and k["tutar"] <= 0 and k["iskonto"] > 0:
                onayli.append(f"{i}. kalem %100 iskontolu (bedelsiz). Bedelsiz teslimlerde KDV emsal bedel üzerinden hesaplanır "
                              "(KDV K. md.27); belgeyi kontrol ediniz.")
        kontrol = self.kontrol_toplam.deger()
        if kontrol and abs(kontrol - t.genel_toplam) > 0.01:
            hatalar.append(f"Hesaplanan genel toplam ({para(t.genel_toplam)} TL) belgedeki genel toplamdan ({para(kontrol)} TL) "
                           f"{para(abs(kontrol - t.genel_toplam))} TL farklı. Birim fiyatları (iskontosuz), iskontoları ve KDV "
                           "oranlarını belgeyle karşılaştırınız.")
        no = self.no.text().strip()
        if no:
            cift = db().q1(
                "SELECT tarih FROM fatura WHERE tur = ? AND belge_no = ? AND iptal = 0 AND id != ?" +
                (" AND substr(tarih, 1, 4) = ?" if self.satis else " AND cari_id = ?"),
                (self.tur, no, self.fid or 0, (self.tarih.deger() or "")[:4] if self.satis else (self.cari.deger() or 0)))
            if cift:
                hatalar.append(f"{no} numaralı belge {cift['tarih'][8:10]}.{cift['tarih'][5:7]}.{cift['tarih'][:4]} tarihinde "
                               "zaten kaydedilmiş. Aynı belge iki kez kaydedilemez.")
        if (self.tarih.deger() or "")[:4] != str(Oturum.yil):
            onayli.append(f"Belge tarihi çalışılan yılın ({Oturum.yil}) dışında.")
        if self.satis:
            if self.avans.deger() > t.net_tutar + 0.005:
                hatalar.append("Avans mahsubu faturanın net tutarını aşamaz.")
            if self.avans.deger() > getattr(self, "_avans_kalan", 0) + 0.005:
                onayli.append("Mahsup tutarı, siparişe tahsil edilmiş ve mahsup edilmemiş avansı aşıyor.")
            cari = db().q1("SELECT kamu_kurumu FROM cari WHERE id = ?", (self.cari.deger() or 0,))
            if cari and cari["kamu_kurumu"] and self.tevkifat.deger() == "Yok":
                uyarilar.append("Kamu kurumlarına yapılan bazı teslimlerde KDV tevkifatı uygulanır; işin niteliğine göre kontrol ediniz.")
            for k in kalemler:
                u = db().q1("SELECT ad, satis_fiyati FROM urun WHERE id = ?", (k["urun_id"],)) if k.get("urun_id") else None
                net_fiyat = yuvarla(k["tutar"] / k["miktar"], 4) if k["miktar"] else 0
                if u and (u["satis_fiyati"] or 0) > 0 and net_fiyat + 0.005 < u["satis_fiyati"]:
                    onayli.append(f"'{u['ad']}' iskonto sonrası {para(net_fiyat)} TL ile tespit edilen satış fiyatının "
                                  f"({para(u['satis_fiyati'])} TL) altında satılıyor. Fiyat komisyonca tespit edilen (tarım/hayvan "
                                  "ürünlerinde bölge rayiç) fiyattır; işletme aleyhine müşteri lehine indirim yapılamaz (Çalışma "
                                  "Yönergesi md.26/g, md.29/a). Fiyat yeniden tespit edildiyse önce ürün kartındaki 'Maliyet Analizi "
                                  "/ Fiyat Tespiti' ile fiyatı güncelleyiniz.")
            if self.belge_turu.deger() == "Diğer":
                uyarilar.append("Satışlar fatura (veya nihai tüketiciye ÖKC fişi) ile belgelendirilir (VUK md.229-233, Yönerge md.44).")
        else:
            limit = self.p["dogrudan_temin_buyuksehir" if self.kurum.get("buyuksehir") else "dogrudan_temin_diger"]
            if self.temin.deger() == "Doğrudan Temin" and t.matrah > limit:
                hatalar.append(f"Matrah ({para(t.matrah)} TL) doğrudan temin limitini ({para(limit)} TL) aşıyor (4734 md.22/d). "
                               "Başka bir temin usulü seçiniz.")
            if self.temin.deger() == "Doğrudan Temin":
                uyarilar.append("Doğrudan temin: onay belgesi, piyasa fiyat araştırması tutanağı ve yasaklılık teyidi dosyada bulunmalıdır; "
                                "ihtiyaçlar limit altında kalacak şekilde bölünemez.")
            bt = self.belge_turu.deger()
            cari = db().q1("SELECT tur, vkn_tckn FROM cari WHERE id = ?", (self.cari.deger() or 0,))
            if bt.startswith("Müstahsil"):
                if cari and cari["tur"] != "Çiftçi (Müstahsil)":
                    uyarilar.append("Müstahsil makbuzu yalnızca vergiden muaf çiftçiden yapılan alımlarda düzenlenir.")
                if t.kdv:
                    uyarilar.append("Müstahsil makbuzunda KDV hesaplanmaz.")
                if not self.stopaj_orani():
                    hatalar.append("Müstahsil makbuzunda gelir vergisi stopajı (GVK md.94/11) seçilmelidir.")
            elif bt.startswith("Perakende"):
                uyarilar.append("Alımlar fatura ile belgelendirilir; perakende satış fişi yalnızca fatura düzenleme sınırının (VUK md.232) "
                                "altındaki küçük alımlarda kabul edilebilir (Çalışma Yönergesi md.46).")
                if t.kdv:
                    hatalar.append("Perakende satış fişindeki KDV indirim konusu yapılamaz (Yönerge md.46/c, KDV md.34). Kalemleri KDV "
                                   "dahil tutarla ve KDV oranı %0 olarak giriniz.")
            elif bt == "Diğer":
                uyarilar.append("Harcamalarda yalnızca VUK md.228-238'de sayılan belgeler (fatura, müstahsil makbuzu, gider pusulası, "
                                "serbest meslek makbuzu vb.) kabul edilir (Çalışma Yönergesi md.46).")
            gider_stok = mevzuat.GIDER_TURLERI.get(self.gider.deger(), ("", False))[1]
            if gider_stok and any(not k["malzeme_id"] for k in kalemler):
                onayli.append("Stoğa girecek gider türünde stok malzemesi seçilmeyen kalem var; bu kalemler stoğa girmez.")
        if not self.cari.deger():
            hatalar.append("Cari seçiniz.")
        if not kalemler:
            hatalar.append("En az bir kalem giriniz.")
        if t.iskonto:
            uyarilar.append(f"Toplam iskonto {para(t.iskonto)} TL ({oran_yazi(t.iskonto / t.brut) if t.brut else ''}); "
                            "KDV" + ("" if self.satis else ", stopaj ve stok maliyeti") + " iskonto sonrası tutardan hesaplandı.")
        self.mesaj.goster(hatalar, onayli + uyarilar, "Belge kontrolleri tamam.")
        self._hatalar, self._uyarilar, self._onayli = hatalar, uyarilar, onayli
        return t

    def kaydet(self):
        if not yetki_kontrol(self):
            return
        t = self.hesapla()
        if self._hatalar:
            uyari(self, "Belge kaydedilemedi; aşağıdakileri düzeltiniz:\n\n" + "\n\n".join("• " + h for h in self._hatalar))
            return
        if self._onayli and not soru(self, "Lütfen kontrol ediniz:\n\n" + "\n\n".join("• " + u for u in self._onayli) +
                                     "\n\nYine de kaydedilsin mi?"):
            return
        kalemler = self.kalemler()
        v = {"tur": self.tur, "belge_turu": self.belge_turu.deger(), "belge_no": self.no.text().strip() or None,
             "tarih": self.tarih.deger(), "cari_id": self.cari.deger(), "siparis_id": self.siparis.deger(),
             "aciklama": self.aciklama.text().strip() or None, "iskonto": t.iskonto, "matrah": t.matrah, "kdv": t.kdv,
             "tevkifat": self.tevkifat.deger(), "tevkif_kdv": t.tevkif_kdv, "stopaj": t.stopaj, "stopaj_orani": self.stopaj_orani(),
             "genel_toplam": t.genel_toplam, "net_tutar": t.net_tutar}
        if self.satis:
            v["avans_mahsup"] = self.avans.deger()
        else:
            v.update({"stopaj_turu": self.stopaj.deger(), "gider_turu": self.gider.deger(), "temin_usulu": self.temin.deger()})
        from ...muhasebe import ortalama_maliyet
        yeni = not self.fid
        try:
            self._yaz(v, kalemler, ortalama_maliyet)
        except Exception as e:
            if yeni:
                self.fid = None
            hata(self, f"Belge kaydedilemedi; veritabanında hiçbir değişiklik yapılmadı.\n\n{e}")
            return
        self.accept()

    def _yaz(self, v: dict, kalemler: list[dict], ortalama_maliyet):
        with db().islem():
            if not v["belge_no"]:
                v["belge_no"] = db().sonraki_no("satis" if self.satis else "alis", int(v["tarih"][:4]), "SF" if self.satis else "AF")
            if self.fid:
                db().guncelle("fatura", self.fid, v)
            else:
                self.fid = db().ekle("fatura", v)
            db().ex("DELETE FROM fatura_kalem WHERE fatura_id = ?", (self.fid,))
            db().ex("DELETE FROM stok_hareket WHERE kaynak = 'Fatura' AND kaynak_id = ?", (self.fid,))
            for k in kalemler:
                k["fatura_id"] = self.fid
                db().ekle("fatura_kalem", k, log=False)
                if self.satis and k.get("urun_id"):
                    mamul = db().deger("SELECT mamul_malzeme_id FROM urun WHERE id = ?", (k["urun_id"],), None)
                    if mamul:
                        db().ekle("stok_hareket", {"tarih": v["tarih"], "malzeme_id": mamul, "yon": "Çıkış", "miktar": k["miktar"],
                                                   "birim_fiyat": ortalama_maliyet(mamul), "kaynak": "Fatura", "kaynak_id": self.fid,
                                                   "siparis_id": v["siparis_id"], "aciklama": f"Satış {v['belge_no']}"}, log=False)
                elif not self.satis and k.get("malzeme_id") and mevzuat.GIDER_TURLERI.get(v["gider_turu"], ("", False))[1]:
                    # stok maliyeti iskonto sonrası birim maliyettir (VUK md.262)
                    db().ekle("stok_hareket", {"tarih": v["tarih"], "malzeme_id": k["malzeme_id"], "yon": "Giriş",
                                               "miktar": k["miktar"], "birim_fiyat": yuvarla(k["tutar"] / k["miktar"], 4),
                                               "kaynak": "Fatura", "kaynak_id": self.fid, "siparis_id": v["siparis_id"],
                                               "aciklama": f"Alış {v['belge_no']}"}, log=False)
            muhasebe.fatura_kaydi(self.fid)
