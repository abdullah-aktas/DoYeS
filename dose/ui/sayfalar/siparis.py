"""Sipariş / iş emri yönetimi ve mevzuata göre sipariş bedeli tahsisi."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit, QSpinBox, QTableWidget,
                               QTabWidget, QVBoxLayout, QWidget)

from ... import belgeler, mevzuat, onay
from ...hesap import kalem_hatalari, kalem_tutari, para, siparis_kaydi_tahsisi, yasal_ust_sinir_iscilik, yuvarla
from ...islemler import kart_malzemesi
from ..ortak import (Kolon, MesajKutusu, OranKutusu, Oturum, ParaKutusu, SecimKutusu, TarihKutusu, VeriTablosu,
                     baslik_etiketi, bilgi, buton, cikti_yolu, db, dosya_ac, fk_secenekleri, kayit_izle, satir_odagini_izle,
                     soru, tablo_excele, uyari, yetki_kontrol)


tahsis_hesapla = siparis_kaydi_tahsisi


class SiparisSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "Siparişler / İş Emirleri",
            "Resmi talep → keşif / iş planı → maliyet → proforma → sözleşme akışı. Bedel; ücret esasına göre kâr, faaliyet "
            "gideri, malzeme, işçilik ve öğrenci hakkı olarak tahsis edilir. Proforma vergi faturası değildir; kabul sonrası "
            "sözleşme (Yön. md.9/4) ve teslimde e-Fatura/e-Arşiv kesilir."))
        ust = QHBoxLayout()
        self.b_yeni = buton("＋ Yeni Sipariş", self.yeni, "birincil")
        ust.addWidget(self.b_yeni)
        ust.addWidget(buton("Düzenle", self.duzenle))
        ust.addWidget(buton("Sil", self.sil, "tehlike"))
        ust.addWidget(buton("Onay akışı", self.onay_akisi, ipucu="Alan şefi → teknik müdür yardımcısı → okul müdürü onayı"))
        bb = buton("Belgeler ▾")
        m = QMenu(bb)
        m.addAction("Keşif ve iş planı tutanağı", lambda: self.belge("kesif"))
        m.addAction("Ön maliyet ve işçilik tespit çizelgesi", lambda: self.belge("maliyet"))
        m.addAction("Proforma fatura (teklif — vergi belgesi değildir)", lambda: self.belge("proforma"))
        m.addAction("Fiyat teklifi (mektup)", lambda: self.belge("teklif"))
        m.addAction("Sözleşme / protokol", lambda: self.belge("sozlesme"))
        m.addSeparator()
        m.addAction("Parça başı çalışma istek listesi (md.8/1)", lambda: self.belge("istek"))
        m.addAction("Görevlendirme onayı (personel + öğrenci)", lambda: self.belge("gorev"))
        m.addAction("Siparişte kullanılan malzeme listesi", lambda: self.belge("malzeme"))
        m.addAction("Geçici muayene ve kabul tutanağı (okul komisyonu)", lambda: self.belge("gecici"))
        m.addAction("Muayene ve kabul (teslim) tutanağı - işi yaptıranla", lambda: self.belge("kabul"))
        bb.setMenu(m)
        ust.addWidget(bb)
        ust.addWidget(buton("Faturalandır", self.faturalandir, ipucu="Siparişten satış faturası oluşturur"))
        ust.addWidget(buton("Malzeme çıkışı", self.malzeme_cikisi, ipucu="Stoktan bu siparişe malzeme çıkışı"))
        ust.addWidget(buton("Excel'e Aktar", lambda: tablo_excele(self, self.tablo, "Siparisler")))
        ust.addStretch()
        ust.addWidget(QLabel("Durum:"))
        self.f_durum = SecimKutusu(secenekler=["Tümü", "Açık işler"] + mevzuat.SIPARIS_DURUMLARI)
        self.f_durum.currentIndexChanged.connect(self.yenile)
        ust.addWidget(self.f_durum)
        lay.addLayout(ust)
        self.tablo = VeriTablosu()
        self.tablo.satirCiftTiklandi.connect(lambda _s: self.duzenle())
        lay.addWidget(self.tablo)
        self.ozet = QLabel()
        lay.addWidget(self.ozet)
        self.yenile()

    def yenile(self):
        yil = str(Oturum.yil)
        sql = """SELECT s.*, c.unvan, b.ad bolum_ad,
                        (SELECT COALESCE(SUM(matrah), 0) FROM fatura f WHERE f.siparis_id = s.id AND f.tur = 'Satış' AND f.iptal = 0) faturalanan
                 FROM siparis s LEFT JOIN cari c ON c.id = s.cari_id LEFT JOIN bolum b ON b.id = s.bolum_id
                 WHERE substr(s.tarih, 1, 4) = ?"""
        prm = [yil]
        if Oturum.bolum_id():
            sql += " AND s.bolum_id = ?"
            prm.append(Oturum.bolum_id())
        d = self.f_durum.deger()
        if d == "Açık işler":
            sql += " AND s.durum NOT IN ('Kapandı', 'İptal', 'Faturalandı')"
        elif d and d != "Tümü":
            sql += " AND s.durum = ?"
            prm.append(d)
        satirlar = db().q(sql + " ORDER BY s.tarih DESC, s.id DESC", prm)
        p = db().parametreler(Oturum.yil)
        durumlar = onay.durumlar("Sipariş")
        for s in satirlar:
            t = tahsis_hesapla(s, p)
            s["ogrenci_hakki"] = t.ogrenci_hakki
            s["kontrol"] = "⛔ " + t.hatalar[0] if t.hatalar else ("⚠ " + t.uyarilar[0] if t.uyarilar else "✔ Uygun")
            s["onay"] = onay.durum_metni(durumlar[s["id"]]) if s["id"] in durumlar else (
                onay.ONAYLANDI if s["durum"] not in (*mevzuat.SIPARIS_TEKLIF_ASAMALARI, "İptal") else onay.HAZIRLANIYOR)
        self.tablo.doldur([
            Kolon("siparis_no", "Sipariş no"), Kolon("tarih", "Tarih", "tarih"), Kolon("unvan", "Müşteri"),
            Kolon("konu", "Konu"), Kolon("bolum_ad", "Bölüm"), Kolon("ucret_esasi", "Ücret esası"),
            Kolon("sozlesme_bedeli", "Bedel (KDV hariç)", "para"), Kolon("pesinat", "Peşinat", "para"),
            Kolon("iscilik_tutari", "İşçilik", "para"), Kolon("ogrenci_hakki", "Öğrenci hakkı", "para"),
            Kolon("faturalanan", "Faturalanan", "para"), Kolon("teslim_tarihi", "Teslim", "tarih"),
            Kolon("durum", "Durum"), Kolon("onay", "Onay"), Kolon("kontrol", "Mevzuat kontrolü", genislik=380)], satirlar,
            lambda s: "#fdecea" if s["kontrol"].startswith("⛔") else ("#fff4e5" if s["kontrol"].startswith("⚠") else None))
        self.ozet.setText(f"{len(satirlar)} sipariş • Toplam bedel: {para(sum(s['sozlesme_bedeli'] or 0 for s in satirlar))} TL")
        self.b_yeni.setEnabled(Oturum.yazabilir(self))

    def yeni(self):
        if yetki_kontrol(self) and SiparisDialog(self).exec():
            self.yenile()

    def duzenle(self):
        s = self.tablo.secili()
        if s and SiparisDialog(self, s["id"]).exec():
            self.yenile()

    def onay_akisi(self):
        s = self.tablo.secili()
        if not s:
            bilgi(self, "Önce bir sipariş seçiniz.")
            return
        from .onay_sayfa import OnayDialog
        if OnayDialog(self, "Sipariş", s["id"]).exec():
            self.yenile()

    def sil(self):
        s = self.tablo.secili()
        if not s or not yetki_kontrol(self):
            return
        if db().deger("SELECT COUNT(*) FROM fatura WHERE siparis_id = ?", (s["id"],)) or \
                db().deger("SELECT COUNT(*) FROM parca_basi WHERE siparis_id = ?", (s["id"],)):
            uyari(self, "Siparişe bağlı fatura veya parça başı kaydı var; silmek yerine durumunu 'İptal' yapınız.")
            return
        if onay.durum("Sipariş", s["id"])["durum"] in (onay.BEKLIYOR, onay.ONAYLANDI) and not Oturum.yonetici():
            uyari(self, "Onay sürecindeki veya onaylanmış sipariş silinemez; durumunu 'İptal' yapınız.")
            return
        if soru(self, f"{s['siparis_no']} numaralı sipariş silinsin mi?"):
            with db().islem():
                for t in ("siparis_kalem", "siparis_gorevli", "siparis_is_plani"):
                    db().ex(f"DELETE FROM {t} WHERE siparis_id = ?", (s["id"],))
                db().sil("siparis", s["id"])
                onay.sil("Sipariş", s["id"])
            self.yenile()

    def belge(self, tur):
        s = self.tablo.secili()
        if not s:
            bilgi(self, "Önce bir sipariş seçiniz.")
            return
        p = db().parametreler(Oturum.yil)
        if tur == "kesif":
            yol = belgeler.kesif_is_plani(cikti_yolu(f"Kesif_Is_Plani_{s['siparis_no']}"), s["id"])
        elif tur == "proforma":
            self._proforma_hazirla(s)
            yol = belgeler.proforma_fatura(cikti_yolu(f"Proforma_{s.get('proforma_no') or s['siparis_no']}"), s["id"])
            if s.get("durum") in ("Talep Alındı", "Keşif / İş Planı", "Teklif") and \
                    soru(self, "Proforma oluşturuldu. Sipariş durumu 'Proforma İletildi' yapılsın mı?\n\n"
                               "(Muhataba ilettikten sonra kabul gelince onay akışı / sözleşme adımına geçiniz.)"):
                db().guncelle("siparis", s["id"], {"durum": "Proforma İletildi"})
                self.yenile()
        elif tur == "teklif":
            yol = belgeler.teklif_mektubu(cikti_yolu(f"Teklif_{s['siparis_no']}"), s["id"])
        elif tur == "sozlesme":
            from ...hesap import esas_kurallari
            k = esas_kurallari(s["ucret_esasi"], p)
            yol = belgeler.siparis_sozlesmesi(cikti_yolu(f"Sozlesme_{s['siparis_no']}"), s["id"], {"pesin_orani": k["pesin"]})
        elif tur == "maliyet":
            yol = belgeler.on_maliyet_cizelgesi(cikti_yolu(f"On_Maliyet_{s['siparis_no']}"), s["id"],
                                                tahsis_hesapla(s, p), p)
        elif tur == "malzeme":
            yol = belgeler.siparis_malzeme_listesi(cikti_yolu(f"Malzeme_Listesi_{s['siparis_no']}"), s["id"], p)
        elif tur == "gecici":
            yol = belgeler.gecici_kabul_tutanagi(cikti_yolu(f"Gecici_Kabul_{s['siparis_no']}"), s["id"])
        elif tur == "istek":
            yol = belgeler.calisma_istek_listesi(cikti_yolu(f"Calisma_Istek_{s['siparis_no']}"), s["id"])
        elif tur == "gorev":
            yol = belgeler.gorevlendirme_onayi(cikti_yolu(f"Gorevlendirme_{s['siparis_no']}"), s["id"])
        else:
            yol = belgeler.muayene_kabul_tutanagi(cikti_yolu(f"Muayene_Kabul_{s['siparis_no']}"), s["id"])
        dosya_ac(yol)

    @staticmethod
    def _proforma_hazirla(s: dict):
        """Proforma no/tarih yoksa otomatik verir (e-Fatura numarası değildir)."""
        from datetime import date as _date
        guncel = {}
        if not s.get("proforma_no"):
            guncel["proforma_no"] = db().sonraki_no("proforma", Oturum.yil, "PRF")
        if not s.get("proforma_tarih"):
            guncel["proforma_tarih"] = _date.today().isoformat()
        if s.get("proforma_gecerlilik_gun") in (None, ""):
            guncel["proforma_gecerlilik_gun"] = 30
        if guncel:
            db().guncelle("siparis", s["id"], guncel)
            s.update(guncel)

    def faturalandir(self):
        s = self.tablo.secili()
        if not s or not yetki_kontrol(self, sayfa="Satış Faturaları"):
            return
        if onay.akis_acik() and onay.durum("Sipariş", s["id"])["durum"] != onay.ONAYLANDI:
            uyari(self, "Harcama yetkilisince onaylanmamış sipariş faturalandırılamaz.")
            return
        from .fatura import FaturaDialog
        if FaturaDialog(self, "Satış", siparis_id=s["id"]).exec():
            if soru(self, "Sipariş durumu 'Faturalandı' olarak güncellensin mi?"):
                db().guncelle("siparis", s["id"], {"durum": "Faturalandı"})
            self.yenile()

    def malzeme_cikisi(self):
        s = self.tablo.secili()
        if not s or not yetki_kontrol(self, sayfa="Stok Durumu ve Hareketleri"):
            return
        from .stok import StokHareketDialog
        if StokHareketDialog(self, "Çıkış", siparis_id=s["id"]).exec():
            self.yenile()


class SiparisDialog(QDialog):
    def __init__(self, parent, siparis_id: int | None = None):
        super().__init__(parent)
        kayit_izle(self, "siparis", siparis_id)
        self.sid = siparis_id
        self.s = db().q1("SELECT * FROM siparis WHERE id = ?", (siparis_id,)) if siparis_id else {}
        self.p = db().parametreler(int((self.s.get("tarih") or str(Oturum.yil))[:4]))
        self.setWindowTitle(f"Sipariş / İş Emri {self.s.get('siparis_no') or '(yeni)'}")
        self.resize(1100, 760)
        lay = QVBoxLayout(self)
        sekmeler = QTabWidget()
        lay.addWidget(sekmeler)

        # --- genel
        g = QWidget()
        f = QGridLayout(g)
        self.no = QLineEdit(self.s.get("siparis_no") or "")
        self.no.setPlaceholderText("Kaydedince otomatik verilir")
        self.tarih = TarihKutusu()
        self.cari = SecimKutusu(secenekler=fk_secenekleri("cari", "unvan", "aktif = 1 AND tur != 'Tedarikçi'"), bos=True)
        kisit = Oturum.bolum_id()
        self.bolum = SecimKutusu(secenekler=fk_secenekleri("bolum", "ad", "aktif = 1" + (f" AND id = {int(kisit)}" if kisit else "")),
                                 bos=not kisit)
        self.konu = QLineEdit()
        self.esas = SecimKutusu(secenekler=mevzuat.UCRET_ESASLARI)
        self.kdv = OranKutusu()
        self.pesinat = ParaKutusu()
        self.baslama = TarihKutusu(bos_olabilir=True)
        self.teslim = TarihKutusu(bos_olabilir=True)
        self.kabul = TarihKutusu(bos_olabilir=True)
        self.durum = SecimKutusu(secenekler=mevzuat.SIPARIS_DURUMLARI)
        self.ogr = QCheckBox("Öğrenciler bu işte uygulamaya alınacak (zorunlu)")
        self.mus_malz = QCheckBox("Malzeme işi yaptıran tarafından sağlanıyor")
        self.sure = QSpinBox()
        self.sure.setRange(0, 120)
        self.sure.setSuffix(" ay")
        self.izin = QCheckBox("Bakanlık yazılı izni alındı (md.9/2)")
        self.aciklama = QPlainTextEdit()
        self.aciklama.setMaximumHeight(70)
        alanlar = [("Sipariş no", self.no), ("Tarih", self.tarih), ("Müşteri *", self.cari), ("Bölüm / atölye *", self.bolum),
                   ("İşin konusu *", self.konu), ("Ücret esası *", self.esas), ("KDV oranı", self.kdv), ("Tahsil edilen peşinat", self.pesinat),
                   ("İşe başlama", self.baslama), ("Teslim tarihi", self.teslim), ("Geçici kabul tarihi", self.kabul),
                   ("Durum", self.durum), ("Sözleşme süresi", self.sure)]
        for i, (e, w) in enumerate(alanlar):
            f.addWidget(QLabel(e + ":"), i % 7, (i // 7) * 2)
            f.addWidget(w, i % 7, (i // 7) * 2 + 1)
        f.addWidget(self.ogr, 7, 0, 1, 2)
        f.addWidget(self.mus_malz, 7, 2, 1, 2)
        f.addWidget(self.izin, 8, 2, 1, 2)
        f.addWidget(QLabel("Açıklama:"), 9, 0)
        f.addWidget(self.aciklama, 9, 1, 1, 3)
        sekmeler.addTab(g, "Genel bilgiler")

        # --- talep / keşif / iş planı / proforma (İlçe MEM vb. resmi yazı akışı)
        tp = QWidget()
        tl = QVBoxLayout(tp)
        tl.addWidget(QLabel(
            "Resmi yazı ile gelen taleplerde (ör. ilçe MEM, okul müdürlüğü): talep bilgilerini girin → keşif ve iş planı "
            "kalemlerini yazın → kalemler sekmesinde maliyet → Belgeler menüsünden proforma ve sözleşme üretin. "
            "Proforma e-Fatura değildir."))
        tf = QGridLayout()
        self.talep_kurum = QLineEdit()
        self.talep_sayi = QLineEdit()
        self.talep_tarih = TarihKutusu(bos_olabilir=True)
        self.talep_ilgi = QLineEdit()
        self.kesif_tarih = TarihKutusu(bos_olabilir=True)
        self.proforma_no = QLineEdit()
        self.proforma_no.setPlaceholderText("Boş bırakılırsa proforma PDF alınırken otomatik verilir")
        self.proforma_tarih = TarihKutusu(bos_olabilir=True)
        self.proforma_gun = QSpinBox()
        self.proforma_gun.setRange(1, 180)
        self.proforma_gun.setValue(30)
        self.proforma_gun.setSuffix(" gün")
        self.kesif_ozet = QPlainTextEdit()
        self.kesif_ozet.setMaximumHeight(80)
        self.kesif_ozet.setPlaceholderText("Yerinde inceleme tespitleri, periyodik kontrol kapsamı, bakım-onarım ihtiyacı…")
        for i, (etiket, w) in enumerate([
            ("Talep eden kurum / makam", self.talep_kurum), ("Talep yazı sayısı", self.talep_sayi),
            ("Talep tarihi", self.talep_tarih), ("İlgi (önceki yazı)", self.talep_ilgi),
            ("Keşif / inceleme tarihi", self.kesif_tarih), ("Proforma no", self.proforma_no),
            ("Proforma tarihi", self.proforma_tarih), ("Proforma geçerlilik", self.proforma_gun),
        ]):
            tf.addWidget(QLabel(etiket + ":"), i % 4, (i // 4) * 2)
            tf.addWidget(w, i % 4, (i // 4) * 2 + 1)
        tl.addLayout(tf)
        tl.addWidget(QLabel("Keşif / tespit özeti:"))
        tl.addWidget(self.kesif_ozet)
        tl.addWidget(QLabel("İş planı kalemleri (kontrol, bakım, onarım adımları — maliyet kalemlerinden ayrıdır):"))
        pu = QHBoxLayout()
        pu.addWidget(buton("＋ İş kalemi", lambda: self.plan_ekle()))
        pu.addWidget(buton("Kalemi sil", self.plan_sil))
        pu.addStretch()
        tl.addLayout(pu)
        self.pt = QTableWidget(0, 6)
        self.pt.setHorizontalHeaderLabels(["Sıra", "İş kalemi", "Açıklama / kapsam", "Miktar", "Birim", "Tahmini saat"])
        self.pt.horizontalHeader().setStretchLastSection(True)
        self.pt.verticalHeader().setVisible(False)
        self.pt.setMaximumHeight(200)
        satir_odagini_izle(self.pt)
        tl.addWidget(self.pt)
        sekmeler.addTab(tp, "Talep ve iş planı")

        # --- kalemler ve tahsis
        k = QWidget()
        kl = QVBoxLayout(k)
        ust = QHBoxLayout()
        ust.addWidget(buton("＋ Kalem", lambda: self.kalem_ekle()))
        ust.addWidget(buton("Kalemi sil", self.kalem_sil))
        ust.addStretch()
        kl.addLayout(ust)
        self.kt = QTableWidget(0, 7)
        self.kt.setHorizontalHeaderLabels(["Ürün / hizmet", "Açıklama", "Miktar", "Birim", "Birim fiyat (KDV hariç, iskontosuz)",
                                           "İsk. %", "Tutar (iskonto sonrası)"])
        self.kt.horizontalHeaderItem(5).setToolTip("Müşteriye yapılan kalem iskontosu (%). Sözleşme bedeli iskonto sonrası tutardır.")
        self.kt.horizontalHeader().setStretchLastSection(True)
        self.kt.verticalHeader().setVisible(False)
        self.kt.setMaximumHeight(210)
        satir_odagini_izle(self.kt)
        kl.addWidget(self.kt)
        self.urunler = db().q("SELECT id, ad, birim, satis_fiyati, kdv_orani FROM urun WHERE aktif = 1 ORDER BY ad")

        th = QHBoxLayout()
        gi = QGroupBox("Tahsis girdileri")
        fi = QFormLayout(gi)
        self.kar = OranKutusu()
        self.malz = ParaKutusu()
        self.iscilik = ParaKutusu()
        self.ogr_oran = OranKutusu()
        self.oto_malz = QCheckBox("Maliyet kartından (otomatik)")
        self.oto_malz.setToolTip("Seçilen ürünlerin maliyet kartındaki malzeme ve ambalaj giderleri × miktar. Elle girmek için "
                                 "işareti kaldırın.")
        self.oto_iscilik = QCheckBox("Yasal üst sınır (otomatik)")
        self.oto_iscilik.setToolTip("İşçilik = sözleşme bedeli − asgari kâr − faaliyet gideri − malzeme (Yön. md.8/2-4). "
                                    "Daha düşük bir tutar yazmak için işareti kaldırın.")
        fi.addRow("Kâr oranı (asgari):", self.kar)
        h = QHBoxLayout()
        h.addWidget(self.malz)
        h.addWidget(self.oto_malz)
        fi.addRow("Malzeme maliyeti (DÖSE karşılar):", h)
        h2 = QHBoxLayout()
        h2.addWidget(self.iscilik)
        h2.addWidget(self.oto_iscilik)
        fi.addRow("İşçilik tutarı (şartnamedeki):", h2)
        fi.addRow("Öğrenci hakkı oranı (asgari):", self.ogr_oran)
        th.addWidget(gi)
        gs = QGroupBox("Mevzuata göre tahsis")
        self.fs = QFormLayout(gs)
        self.lbl = {}
        for anahtar, etiket in [("bedel", "Sözleşme bedeli (KDV hariç)"), ("kar", "Kâr"), ("faaliyet", "Faaliyet gideri"),
                                ("malzeme", "Malzeme"), ("azami_iscilik", "Ayrılabilecek azami işçilik"),
                                ("iscilik", "İşçilik"), ("ogrenci_hakki", "Öğrenci hakkı"), ("personel_iscilik", "Personel işçiliği"),
                                ("asgari_pesinat", "Asgari peşinat"), ("kdvli", "KDV dahil sözleşme bedeli")]:
            self.lbl[anahtar] = QLabel()
            self.lbl[anahtar].setAlignment(Qt.AlignRight)
            self.fs.addRow(etiket + ":", self.lbl[anahtar])
        th.addWidget(gs)
        kl.addLayout(th)
        self.mesaj = MesajKutusu()
        kl.addWidget(self.mesaj)
        sekmeler.addTab(k, "Kalemler ve bedel tahsisi")

        # --- görevliler
        gv = QWidget()
        gl = QHBoxLayout(gv)
        self.l_per = QListWidget()
        self.l_ogr = QListWidget()
        secili = {(r["kisi_turu"], r["kisi_id"]) for r in db().q("SELECT * FROM siparis_gorevli WHERE siparis_id = ?", (siparis_id or 0,))}
        for p in db().q("SELECT id, ad_soyad, dose_gorevi FROM personel WHERE aktif = 1 ORDER BY ad_soyad"):
            it = QListWidgetItem(f"{p['ad_soyad']} — {p['dose_gorevi']}")
            it.setData(Qt.UserRole, p["id"])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if ("Personel", p["id"]) in secili else Qt.Unchecked)
            self.l_per.addItem(it)
        for o in db().q("SELECT id, ad_soyad, sinif, veli_muvafakat FROM ogrenci WHERE aktif = 1 ORDER BY ad_soyad"):
            it = QListWidgetItem(f"{o['ad_soyad']} ({o['sinif'] or ''})" + ("" if o["veli_muvafakat"] else "  ⚠ veli muvafakati yok"))
            it.setData(Qt.UserRole, o["id"])
            it.setData(Qt.UserRole + 1, o["veli_muvafakat"])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if ("Öğrenci", o["id"]) in secili else Qt.Unchecked)
            self.l_ogr.addItem(it)
        for baslik, liste in (("Görevli personel", self.l_per), ("Uygulama yapacak öğrenciler", self.l_ogr)):
            kutu = QGroupBox(baslik)
            v = QVBoxLayout(kutu)
            v.addWidget(liste)
            gl.addWidget(kutu)
        sekmeler.addTab(gv, "Görevliler")

        alt = QHBoxLayout()
        alt.addStretch()
        alt.addWidget(buton("Kaydet", self.kaydet, "birincil"))
        alt.addWidget(buton("Vazgeç", self.reject))
        lay.addLayout(alt)

        self._doldur()
        self._otomatik_durumlari()
        for w in (self.kar, self.malz, self.iscilik, self.ogr_oran, self.kdv, self.pesinat):
            w.valueChanged.connect(self.hesapla)
        self.esas.currentIndexChanged.connect(self._esas_degisti)
        for w in (self.ogr, self.mus_malz, self.izin, self.oto_malz, self.oto_iscilik):
            w.toggled.connect(self.hesapla)
        self.sure.valueChanged.connect(self.hesapla)
        self.hesapla()

    def _otomatik_durumlari(self):
        """Yeni siparişte ve kayıtlı değerleri otomatik hesapla örtüşen siparişte otomatik hesaplama açık gelir."""
        v = self.degerler()
        kart = self._kart_malzemesi()
        self.oto_malz.setChecked(not self.sid or (kart > 0 and abs(v["malzeme_maliyeti"] - kart) < 0.01))
        if self.oto_malz.isChecked():
            v["malzeme_maliyeti"] = kart
        ust = yasal_ust_sinir_iscilik(v, self.p)
        self.oto_iscilik.setChecked(not self.sid or not v["iscilik_tutari"] or abs(v["iscilik_tutari"] - ust) < 0.01)

    def _doldur(self):
        s = self.s
        self.tarih.ayarla(s.get("tarih"))
        self.cari.ayarla(s.get("cari_id"))
        self.bolum.ayarla(s.get("bolum_id"))
        self.konu.setText(s.get("konu") or "")
        self.esas.ayarla(s.get("ucret_esasi") or mevzuat.UCRET_ESASLARI[0])
        self.kdv.ayarla(s.get("kdv_orani") if s else self.p["kdv_genel"])
        self.pesinat.ayarla(s.get("pesinat"))
        self.baslama.ayarla(s.get("baslama_tarihi"))
        self.teslim.ayarla(s.get("teslim_tarihi"))
        self.kabul.ayarla(s.get("kabul_tarihi"))
        self.durum.ayarla(s.get("durum") or "Talep Alındı")
        self.ogr.setChecked(bool(s.get("ogrenci_uygulamasi", 1)))
        self.mus_malz.setChecked(bool(s.get("malzeme_musteriden")))
        self.sure.setValue(s.get("sozlesme_suresi_ay") or 0)
        self.izin.setChecked(bool(s.get("bakanlik_izni")))
        self.aciklama.setPlainText(s.get("aciklama") or "")
        self.talep_kurum.setText(s.get("talep_kurum") or "")
        self.talep_sayi.setText(s.get("talep_sayi") or "")
        self.talep_tarih.ayarla(s.get("talep_tarih"))
        self.talep_ilgi.setText(s.get("talep_ilgi") or "")
        self.kesif_tarih.ayarla(s.get("kesif_tarih"))
        self.kesif_ozet.setPlainText(s.get("kesif_ozet") or "")
        self.proforma_no.setText(s.get("proforma_no") or "")
        self.proforma_tarih.ayarla(s.get("proforma_tarih"))
        self.proforma_gun.setValue(int(s.get("proforma_gecerlilik_gun") or 30))
        from ...hesap import esas_kurallari
        kural = esas_kurallari(self.esas.deger(), self.p)
        self.kar.ayarla(s.get("kar_orani") if s.get("kar_orani") is not None else kural["kar"])
        self.malz.ayarla(s.get("malzeme_maliyeti"))
        self.iscilik.ayarla(s.get("iscilik_tutari"))
        self.ogr_oran.ayarla(s.get("ogrenci_hakki_orani") if s.get("ogrenci_hakki_orani") is not None else self.p["ogrenci_hakki_orani"])
        for kl in db().q("SELECT * FROM siparis_kalem WHERE siparis_id = ? ORDER BY id", (self.sid or 0,)):
            self.kalem_ekle(kl)
        for pl in db().q("SELECT * FROM siparis_is_plani WHERE siparis_id = ? ORDER BY sira, id", (self.sid or 0,)):
            self.plan_ekle(pl)

    def _esas_degisti(self):
        from ...hesap import esas_kurallari
        kural = esas_kurallari(self.esas.deger(), self.p)
        if self.kar.deger() < kural["kar"]:
            self.kar.ayarla(kural["kar"])
        if self.esas.deger().startswith(("Özel", "Tesis")):
            self.mus_malz.setChecked(True)
        self.hesapla()

    def kalem_ekle(self, kl=None):
        kl = kl or {}
        r = self.kt.rowCount()
        self.kt.insertRow(r)
        urun = SecimKutusu(secenekler=[(u["id"], u["ad"]) for u in self.urunler], bos=True)
        urun.ayarla(kl.get("urun_id"))
        ack = QLineEdit(kl.get("aciklama") or "")
        mik = ParaKutusu(ondalik=3)
        mik.ayarla(kl.get("miktar") if kl else 1)
        birim = SecimKutusu(secenekler=mevzuat.BIRIMLER, duzenlenebilir=True)
        birim.ayarla(kl.get("birim") or "Adet")
        bf = ParaKutusu(ondalik=4)
        bf.ayarla(kl.get("birim_fiyat"))
        isk = OranKutusu()
        isk.ayarla(kl.get("iskonto_orani"))
        tutar = QLabel()
        tutar.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        for c, w in enumerate((urun, ack, mik, birim, bf, isk, tutar)):
            self.kt.setCellWidget(r, c, w)

        def urun_secildi():
            u = next((x for x in self.urunler if x["id"] == urun.deger()), None)
            if u:
                bf.ayarla(u["satis_fiyati"])
                birim.ayarla(u["birim"])
                if not self.konu.text():
                    self.konu.setText(u["ad"])
            self.hesapla()
        urun.currentIndexChanged.connect(urun_secildi)
        for w in (mik, bf, isk):
            w.valueChanged.connect(self.hesapla)
        self.kt.setColumnWidth(0, 220)
        self.kt.setColumnWidth(1, 200)
        self.kt.setColumnWidth(5, 70)
        self.hesapla()

    def kalem_sil(self):
        r = self.kt.currentRow()
        if r < 0:
            uyari(self, "Silinecek kalemin herhangi bir kutusuna tıklayıp yeniden deneyiniz.")
            return
        self.kt.removeRow(r)
        self.hesapla()

    def plan_ekle(self, pl=None):
        pl = pl or {}
        r = self.pt.rowCount()
        self.pt.insertRow(r)
        sira = QSpinBox()
        sira.setRange(1, 999)
        sira.setValue(int(pl.get("sira") or r + 1))
        kalem = QLineEdit(pl.get("kalem") or "")
        ack = QLineEdit(pl.get("aciklama") or "")
        mik = ParaKutusu(ondalik=3)
        mik.ayarla(pl.get("miktar") if pl.get("miktar") is not None else 1)
        birim = SecimKutusu(secenekler=mevzuat.BIRIMLER, duzenlenebilir=True)
        birim.ayarla(pl.get("birim") or "Adet")
        saat = ParaKutusu(ondalik=2)
        saat.ayarla(pl.get("tahmini_saat"))
        for c, w in enumerate((sira, kalem, ack, mik, birim, saat)):
            self.pt.setCellWidget(r, c, w)
        self.pt.setColumnWidth(1, 180)
        self.pt.setColumnWidth(2, 220)

    def plan_sil(self):
        r = self.pt.currentRow()
        if r < 0:
            uyari(self, "Silinecek iş planı satırına tıklayıp yeniden deneyiniz.")
            return
        self.pt.removeRow(r)

    def plan_kalemleri(self):
        sonuc = []
        for r in range(self.pt.rowCount()):
            w = [self.pt.cellWidget(r, c) for c in range(6)]
            kalem = w[1].text().strip()
            if not kalem:
                continue
            sonuc.append({"sira": w[0].value(), "kalem": kalem, "aciklama": w[2].text().strip() or None,
                          "miktar": w[3].deger(), "birim": w[4].deger(), "tahmini_saat": w[5].deger()})
        return sonuc

    def kalemler(self):
        sonuc = []
        for r in range(self.kt.rowCount()):
            w = [self.kt.cellWidget(r, c) for c in range(7)]
            k = {"urun_id": w[0].deger(), "aciklama": w[1].text().strip() or None, "miktar": w[2].deger(),
                 "birim": w[3].deger(), "birim_fiyat": w[4].deger(), "iskonto_orani": w[5].deger()}
            k["iskonto"] = kalem_tutari(k)[1]
            sonuc.append(k)
        return sonuc

    def degerler(self) -> dict:
        kalemler = self.kalemler()
        bedel = yuvarla(sum(kalem_tutari(k)[2] for k in kalemler))
        return {
            "tarih": self.tarih.deger(), "cari_id": self.cari.deger(), "bolum_id": self.bolum.deger(),
            "konu": self.konu.text().strip() or None, "ucret_esasi": self.esas.deger(), "sozlesme_bedeli": bedel,
            "kdv_orani": self.kdv.deger(), "pesinat": self.pesinat.deger(), "baslama_tarihi": self.baslama.deger(),
            "teslim_tarihi": self.teslim.deger(), "kabul_tarihi": self.kabul.deger(), "durum": self.durum.deger(),
            "ogrenci_uygulamasi": 1 if self.ogr.isChecked() else 0, "malzeme_musteriden": 1 if self.mus_malz.isChecked() else 0,
            "kar_orani": self.kar.deger(), "faaliyet_orani": None, "malzeme_maliyeti": self.malz.deger(),
            "iscilik_tutari": self.iscilik.deger(), "ogrenci_hakki_orani": self.ogr_oran.deger(),
            "sozlesme_suresi_ay": self.sure.value(), "bakanlik_izni": 1 if self.izin.isChecked() else 0,
            "aciklama": self.aciklama.toPlainText().strip() or None,
            "talep_kurum": self.talep_kurum.text().strip() or None,
            "talep_sayi": self.talep_sayi.text().strip() or None,
            "talep_tarih": self.talep_tarih.deger(),
            "talep_ilgi": self.talep_ilgi.text().strip() or None,
            "kesif_tarih": self.kesif_tarih.deger(),
            "kesif_ozet": self.kesif_ozet.toPlainText().strip() or None,
            "proforma_no": self.proforma_no.text().strip() or None,
            "proforma_tarih": self.proforma_tarih.deger(),
            "proforma_gecerlilik_gun": self.proforma_gun.value(),
        }

    @staticmethod
    def _sessiz_ayarla(kutu, deger):
        kutu.blockSignals(True)
        kutu.ayarla(deger)
        kutu.blockSignals(False)

    def hesapla(self):
        if not hasattr(self, "mesaj"):
            return
        kalemler = self.kalemler()
        for r, k in enumerate(kalemler):
            lbl = self.kt.cellWidget(r, 6)
            if lbl:
                lbl.setText(para(kalem_tutari(k)[2]))
        self.malz.setReadOnly(self.oto_malz.isChecked())
        self.iscilik.setReadOnly(self.oto_iscilik.isChecked())
        kart = self._kart_malzemesi()
        if self.oto_malz.isChecked():
            self._sessiz_ayarla(self.malz, kart)
        if self.oto_iscilik.isChecked():
            self._sessiz_ayarla(self.iscilik, yasal_ust_sinir_iscilik(self.degerler(), self.p))
        v = self.degerler()
        t = tahsis_hesapla(v, self.p)
        for anahtar in self.lbl:
            if anahtar == "kdvli":
                self.lbl[anahtar].setText(para(t.bedel * (1 + v["kdv_orani"])))
            else:
                self.lbl[anahtar].setText(para(getattr(t, anahtar)))
        hatalar, uyarilar = kalem_hatalari(kalemler) + t.hatalar, list(t.uyarilar)
        if self.oto_malz.isChecked() and not kart and not v["malzeme_musteriden"] and kalemler:
            uyarilar.append("Ürünlerin maliyet kartında malzeme yok, malzeme maliyeti 0 alındı. Ürün kartında 'Maliyet Analizi'ni "
                            "doldurun ya da 'Maliyet kartından' işaretini kaldırıp malzeme tutarını yazın; aksi hâlde işçilik "
                            "olduğundan yüksek hesaplanır.")
        if v["ucret_esasi"].startswith("Fazla") and self.oto_iscilik.isChecked():
            uyarilar.append(f"Fazla çalışma esasında Yönetmelik oran öngörmediğinden işçilik üst sınırında kâr "
                            f"(%{self.p['pb_kar_orani'] * 100:g}) ve faaliyet gideri (%{self.p['pb_faaliyet_orani'] * 100:g}) için "
                            "parça başı oranları (Yön. md.8/2) esas alındı.")
        for k in kalemler:
            u = next((x for x in self.urunler if x["id"] == k["urun_id"]), None)
            net_fiyat = yuvarla(kalem_tutari(k)[2] / k["miktar"], 4) if k["miktar"] else 0
            if u and (u["satis_fiyati"] or 0) > 0 and net_fiyat + 0.005 < u["satis_fiyati"]:
                uyarilar.append(f"'{u['ad']}' birim fiyatı ({para(net_fiyat)} TL) tespit edilen satış fiyatının "
                                f"({para(u['satis_fiyati'])} TL) altında; işletme aleyhine müşteri lehine indirim yapılamaz "
                                "(Çalışma Yönergesi md.26/g, md.29/a).")
        self.mesaj.goster(hatalar, uyarilar, "Sipariş bedeli tahsisi Yönetmelik oranlarına uygun; işçilik yasal üst sınırda."
                          if self.oto_iscilik.isChecked() else "Sipariş bedeli tahsisi Yönetmelik oranlarına uygun.")
        self._hatalar, self._uyarilar = hatalar, uyarilar
        return t

    def _kart_malzemesi(self) -> float:
        return kart_malzemesi(db(), self.kalemler())

    ESASLI_ALANLAR = ("cari_id", "bolum_id", "ucret_esasi", "sozlesme_bedeli", "kdv_orani", "kar_orani", "malzeme_maliyeti",
                      "iscilik_tutari", "ogrenci_hakki_orani", "ogrenci_uygulamasi", "sozlesme_suresi_ay")

    def _onay_denetimi(self, v: dict) -> bool:
        """Onay akışı açıkken: süreçteki sipariş değiştirilemez, onaysız sipariş teklif aşamalarını geçemez,
        onaylı siparişte esaslı değişiklik akışı başa döndürür."""
        if Oturum.bolum_id() and self.sid and self.s.get("bolum_id") not in (None, Oturum.bolum_id()):
            uyari(self, "Yalnız kendi bölümünüzün siparişlerini değiştirebilirsiniz.")
            return False
        if not onay.akis_acik():
            return True
        d = onay.durum("Sipariş", self.sid) if self.sid else {"durum": onay.HAZIRLANIYOR}
        if d["durum"] == onay.BEKLIYOR:
            uyari(self, "Sipariş onay sürecinde; değiştirmek için önce 'Onay akışı' penceresinden geri çekiniz.")
            return False
        if d["durum"] == onay.ONAYLANDI:
            if Oturum.ogretmen():
                uyari(self, "Onaylanmış siparişte değişikliği alan şefi veya teknik müdür yardımcısı yapabilir.")
                return False
            degisen = [a for a in self.ESASLI_ALANLAR if (self.s.get(a) or 0) != (v.get(a) or 0)]
            if degisen:
                if not soru(self, "Sipariş bedeli, tahsisi veya tarafları değişti. Onaylanmış siparişte esaslı değişiklik "
                                  "onay akışını başa döndürür ve durum 'Teklif' olur. Devam edilsin mi?"):
                    return False
                onay.sifirla("Sipariş", self.sid, Oturum.kullanici, "Esaslı değişiklik: " + ", ".join(degisen))
                v["durum"] = "Teklif"
            return True
        if v["durum"] not in (*mevzuat.SIPARIS_TEKLIF_ASAMALARI, "İptal"):
            uyari(self, f"Sipariş harcama yetkilisince onaylanmadan durumu '{v['durum']}' yapılamaz. "
                        "Kaydedip 'Onay akışı' ile onaya gönderiniz.")
            return False
        return True

    def kaydet(self):
        if not yetki_kontrol(self):
            return
        self.hesapla()
        v = self.degerler()
        eksik = [e for e, a in (("Müşteri", "cari_id"), ("Bölüm", "bolum_id"), ("İşin konusu", "konu")) if not v[a]]
        if eksik:
            uyari(self, "Zorunlu alanlar: " + ", ".join(eksik))
            return
        erken = v["durum"] in ("Talep Alındı", "Keşif / İş Planı")
        if not self.kalemler() and not erken:
            uyari(self, "En az bir kalem giriniz. (Talep / keşif aşamasında kalemsiz kaydedilebilir.)")
            return
        if self.kalemler():
            k_hata = kalem_hatalari(self.kalemler())
            if k_hata:
                uyari(self, "Kalemleri düzeltiniz:\n\n" + "\n".join(k_hata))
                return
        if not self._onay_denetimi(v):
            return
        t = tahsis_hesapla(v, self.p) if self.kalemler() else None
        if t and t.hatalar and v["durum"] not in (*mevzuat.SIPARIS_TEKLIF_ASAMALARI, "İptal"):
            uyari(self, "Mevzuata aykırılık giderilmeden sipariş kabul edilemez:\n\n" + "\n".join(t.hatalar))
            return
        if t and not v["iscilik_tutari"] and not v["ucret_esasi"].startswith("Fazla"):
            v["iscilik_tutari"] = max(0.0, t.azami_iscilik)
        ogr_muvafakatsiz = [self.l_ogr.item(i).text() for i in range(self.l_ogr.count())
                            if self.l_ogr.item(i).checkState() == Qt.Checked and not self.l_ogr.item(i).data(Qt.UserRole + 1)]
        if ogr_muvafakatsiz and v["ucret_esasi"].startswith(("Parça", "Özel", "Tesis")):
            if not soru(self, "Veli muvafakati alınmamış öğrenci seçildi (Yön. md.8/1):\n" + "\n".join(ogr_muvafakatsiz) +
                        "\n\nYine de kaydedilsin mi?"):
                return
        if self._uyarilar and not soru(self, "Uyarılar:\n\n" + "\n\n".join("• " + u for u in self._uyarilar) +
                                       "\n\nKaydetmeye devam edilsin mi?"):
            return
        with db().islem():
            if self.sid:
                db().guncelle("siparis", self.sid, v)
            else:
                v["siparis_no"] = self.no.text().strip() or db().sonraki_no("siparis", int(v["tarih"][:4]), "SIP")
                self.sid = db().ekle("siparis", v)
            db().ex("DELETE FROM siparis_kalem WHERE siparis_id = ?", (self.sid,))
            for k in self.kalemler():
                k["siparis_id"] = self.sid
                db().ekle("siparis_kalem", k, log=False)
            db().ex("DELETE FROM siparis_is_plani WHERE siparis_id = ?", (self.sid,))
            for pl in self.plan_kalemleri():
                pl["siparis_id"] = self.sid
                db().ekle("siparis_is_plani", pl, log=False)
            db().ex("DELETE FROM siparis_gorevli WHERE siparis_id = ?", (self.sid,))
            for tur, liste, gorev in (("Personel", self.l_per, "Üretim / danışmanlık"), ("Öğrenci", self.l_ogr, "Beceri eğitimi")):
                for i in range(liste.count()):
                    it = liste.item(i)
                    if it.checkState() == Qt.Checked:
                        db().ekle("siparis_gorevli", {"siparis_id": self.sid, "kisi_turu": tur, "kisi_id": it.data(Qt.UserRole),
                                                      "gorev": gorev}, log=False)
        self.accept()
