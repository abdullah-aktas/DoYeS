"""Yıl sonu kâr bölüşümü, SHÇEK payı ve üretimi teşvik primi (ÜTP) dağıtımı."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QScrollArea,
                               QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ... import belgeler, excel, mevzuat, muhasebe, onay
from ...hesap import UtpKisi, para, parca_basi_gun, ucret_kesintileri, utp_dagit, yil_sonu_bolusum, yuvarla
from ...pdf import tr_buyuk
from ..ortak import (MesajKutusu, OranKutusu, Oturum, ParaKutusu, baslik_etiketi, bilgi, bugun, buton, cikti_yolu, db,
                     dosya_ac, soru, uyari, yetki_kontrol)
from .onay_sayfa import OnayDialog, onay_kaldir

K_AD, K_GOREV, K_BOLUM, K_UNVAN, K_GUN, K_SAAT, K_KATKI, K_TAKDIR, K_HARIC, K_NEDEN, K_DIGER, K_ONCEKI = range(12)
CIKTI_KOLONLARI = ["İdari pay", "Takdir payı", "Bölüm payı", "Hesaplanan", "Tavan aşımı", "Brüt ÜTP", "Gelir v.", "Damga v.", "Net"]
BASLIKLAR = ["Adı soyadı", "DÖSE görevi", "Bölüm", "Unvan grubu", "Fiili gün", "F.Ç. saat", "Katkı (%)", "Takdir (%)", "Hariç",
             "Hariç nedeni (md.6)", "Diğer işletme ÜTP", "Önceki küm. matrah"] + CIKTI_KOLONLARI


class YilSonuSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        dis = QVBoxLayout(self)
        dis.setContentsMargins(0, 0, 0, 0)
        kaydir = QScrollArea()
        kaydir.setWidgetResizable(True)
        dis.addWidget(kaydir)
        ic = QWidget()
        kaydir.setWidget(ic)
        lay = QVBoxLayout(ic)
        lay.addWidget(baslik_etiketi(
            "Yıl Sonu Kâr Dağıtımı ve ÜTP",
            "Kârın en çok 1/3'ü ÜTP, 1/3'ü tahsis tutarına kadar sermaye, kalanı MEB Merkez Saymanlık payıdır (3423 s.K. md.1; DHGM "
            "15.01.2026 yazısı). ÜTP, Yönetmelik md.5'e göre dağıtılır, kişi başı yıllık asgari ücret tavanı uygulanır ve bilanço "
            "tarihini izleyen 2 ay içinde ödenir. Merkez Saymanlık payı Şubat sonuna, SHÇEK payı Ocak sonuna kadar yatırılır."))

        g1 = QGroupBox("1. Dönem kârı ve bölüşüm")
        gl = QGridLayout(g1)
        self.l_gelir, self.l_gider, self.l_kar, self.l_sermaye, self.l_hasilat, self.l_usul = (QLabel() for _ in range(6))
        self.kar = ParaKutusu(azami=1e12)
        self.kar.setMinimum(-1e12)
        self.faiz = ParaKutusu()
        self.oran = OranKutusu()
        self.b_kar_al = buton("Yardımcı defterden al", self.kar_al)
        gl.addWidget(QLabel("Toplam gelir (yardımcı defter):"), 0, 0)
        gl.addWidget(self.l_gelir, 0, 1)
        gl.addWidget(QLabel("Toplam gider:"), 0, 2)
        gl.addWidget(self.l_gider, 0, 3)
        gl.addWidget(QLabel("Hesaplanan kâr:"), 0, 4)
        gl.addWidget(self.l_kar, 0, 5)
        gl.addWidget(QLabel("<b>Bilanço kârı (BKMYBS) *:</b>"), 1, 0)
        gl.addWidget(self.kar, 1, 1)
        gl.addWidget(self.b_kar_al, 1, 2)
        gl.addWidget(QLabel("Vadeli hesap faiz geliri:"), 1, 3)
        gl.addWidget(self.faiz, 1, 4)
        gl.addWidget(QLabel("ÜTP oranı (≤ 1/3):"), 2, 0)
        gl.addWidget(self.oran, 2, 1)
        gl.addWidget(self.l_sermaye, 2, 2, 1, 4)
        gl.addWidget(self.l_hasilat, 3, 0, 1, 3)
        gl.addWidget(self.l_usul, 3, 3, 1, 3)
        lay.addWidget(g1)

        self.g_sonuc = QGroupBox("Bölüşüm sonucu")
        sl = QGridLayout(self.g_sonuc)
        self.s = {}
        for i, (a, e) in enumerate([("utp_azami", "ÜTP'ye ayrılabilecek"), ("dagitima_esas", "Dağıtıma esas ÜTP"),
                                    ("dagitilan_utp", "Dağıtılan (ödenecek) ÜTP"), ("sermaye_payi", "Sermayeye eklenecek"),
                                    ("merkez_payi", "MEB Merkez Saymanlık payı"), ("shcek", "SHÇEK payı")]):
            sl.addWidget(QLabel(e + ":"), i // 3, (i % 3) * 2)
            self.s[a] = QLabel("-")
            self.s[a].setStyleSheet("font-weight: bold;")
            sl.addWidget(self.s[a], i // 3, (i % 3) * 2 + 1)
        lay.addWidget(self.g_sonuc)

        g2 = QGroupBox("2. ÜTP kişi bazında dağıtım")
        v2 = QVBoxLayout(g2)
        ust = QHBoxLayout()
        self.b_yukle = buton("Personeli yükle", self.personel_yukle, "birincil")
        self.b_saat = buton("Saat verilerini getir", self.saat_getir,
                            ipucu="Fazla çalışma saatleri + parça başı ücret / saat ücreti (Yön. md.13/2)")
        self.b_hesap = buton("Hesapla", self.hesapla)
        ust.addWidget(self.b_yukle)
        ust.addWidget(self.b_saat)
        ust.addWidget(self.b_hesap)
        ust.addStretch()
        v2.addLayout(ust)
        self.t = QTableWidget(0, len(BASLIKLAR))
        self.t.setHorizontalHeaderLabels(BASLIKLAR)
        self.t.verticalHeader().setVisible(False)
        self.t.horizontalHeader().setSectionResizeMode(K_AD, QHeaderView.ResizeToContents)
        self.t.setMinimumHeight(380)
        v2.addWidget(self.t)
        self.mesaj = MesajKutusu()
        v2.addWidget(self.mesaj)
        lay.addWidget(g2)

        alt = QHBoxLayout()
        self.b_kaydet = buton("Kaydet (taslak)", self.kaydet, "birincil")
        self.b_kesin = buton("Kesinleştir", self.kesinlestir)
        self.b_geri = buton("Kesinleştirmeyi kaldır", self.geri_al)
        for b in (self.b_kaydet, self.b_kesin, self.b_geri, buton("ÜTP dağıtım cetveli (PDF)", self.cetvel),
                  buton("Banka listesi (Excel)", self.banka), buton("Merkez Saymanlık yazısı", self.merkez_yazisi),
                  buton("SHÇEK yazısı", self.shcek_yazisi)):
            alt.addWidget(b)
        alt.addStretch()
        self.l_durum = QLabel()
        alt.addWidget(self.l_durum)
        lay.addLayout(alt)

        self.kar.valueChanged.connect(self.hesapla)
        self.faiz.valueChanged.connect(self.hesapla)
        self.oran.valueChanged.connect(self.hesapla)
        self.yenile()

    # ------------------------------------------------------------ yükleme
    def yenile(self):
        self.yil = Oturum.yil
        self.p = db().parametreler(self.yil)
        self.p_odeme = db().parametreler(self.yil + 1)
        self.kurum = db().kurum()
        self.gt = muhasebe.gelir_tablosu(self.yil)
        self.hasilat = muhasebe.yillik_brut_hasilat(self.yil)
        self.ys = db().q1("SELECT * FROM yil_sonu WHERE yil = ?", (self.yil,)) or {}
        self.onay_durumu = onay.durum("Yıl Sonu", self.yil)
        self.kesin = self.ys.get("durum") == "Onaylandı" or self.onay_durumu["durum"] == onay.BEKLIYOR
        self.l_gelir.setText(para(self.gt["toplam_gelir"]) + " TL")
        self.l_gider.setText(para(self.gt["toplam_gider"]) + " TL")
        shcek_kayitli = db().deger("SELECT COUNT(*) FROM yevmiye WHERE kaynak = 'SHCEK' AND kaynak_id = ?", (self.yil,), 0)
        self.kar_onerilen = yuvarla(self.gt["kar"] - (0 if shcek_kayitli else self.hasilat * self.p["shcek_orani"]))
        self.l_kar.setText(para(self.kar_onerilen) + " TL (SHÇEK sonrası)")
        self.l_sermaye.setText(f"Tahsis edilen sermaye: {para(self.kurum.get('tahsis_sermaye'))} TL • Ödenmiş sermaye: "
                               f"{para(self.kurum.get('odenmis_sermaye'))} TL")
        self.l_hasilat.setText(f"Yıllık brüt hasılat: {para(self.hasilat)} TL (SHÇEK matrahı)")
        self.yuz_yuze = bool(self.kurum.get("yuz_yuze_egitim", 1))
        self.l_usul.setText("Dağıtım usulü: " + ("md.5/2 (idari %25, takdir %5, bölüm %70)" if self.yuz_yuze
                                                  else "md.5/8 (takdir %5, unvan puanı x gün %95)"))
        for w in (self.kar, self.faiz, self.oran):
            w.blockSignals(True)
        self.kar.ayarla(self.ys.get("donem_kari") if self.ys else self.kar_onerilen)
        self.faiz.ayarla(self.ys.get("faiz_duzeltme"))
        self.oran.ayarla(self.ys.get("utp_orani") if self.ys.get("utp_orani") is not None else self.p["utp_azami_oran"])
        for w in (self.kar, self.faiz, self.oran):
            w.blockSignals(False)
        self.t.setRowCount(0)
        self.satirlar = []
        kayitlar = db().q("SELECT * FROM utp_kisi WHERE yil = ?", (self.yil,))
        for k in kayitlar:
            self._satir_ekle(k["personel_id"], k)
        if not kayitlar:
            self.personel_yukle(sessiz=True)
        yaz = Oturum.yazabilir(self)
        for w in (self.b_yukle, self.b_saat, self.b_hesap, self.b_kaydet, self.kar, self.faiz, self.oran, self.b_kar_al):
            w.setEnabled(not self.kesin and yaz)
        self.b_kesin.setText("Onaya gönder / onay akışı" if onay.akis_acik() else "Kesinleştir")
        self.b_kesin.setEnabled(yaz or (onay.akis_acik() and onay.yetkili_mi(self.onay_durumu, Oturum.kullanici)))
        self.b_geri.setEnabled(self.ys.get("durum") == "Onaylandı" and yaz)
        if self.ys.get("durum") == "Onaylandı":
            durum = "KESİNLEŞTİ"
        elif self.onay_durumu["durum"] in (onay.BEKLIYOR, onay.IADE):
            durum = onay.durum_metni(self.onay_durumu).upper()
        else:
            durum = self.ys.get("durum") or "Kaydedilmedi"
        self.l_durum.setText(f"<b>Durum:</b> {durum}")
        self.hesapla()

    def kar_al(self):
        self.kar.ayarla(self.kar_onerilen)

    def _oran(self) -> float:
        o = self.oran.deger()
        return 1 / 3 if abs(o - 1 / 3) < 1e-4 else o

    def personel_yukle(self, sessiz=False):
        mevcut = {s["id"] for s in self.satirlar}
        for p in db().q("SELECT id FROM personel WHERE aktif = 1 ORDER BY dose_gorevi, ad_soyad"):
            if p["id"] not in mevcut:
                self._satir_ekle(p["id"], None)
        if not sessiz:
            self.hesapla()

    def _satir_ekle(self, pid, k):
        per = db().q1("SELECT p.*, b.ad bolum FROM personel p LEFT JOIN bolum b ON b.id = p.bolum_id WHERE p.id = ?", (pid,))
        if not per:
            return
        k = k or {}
        r = self.t.rowCount()
        self.t.insertRow(r)
        for c, v in ((K_AD, per["ad_soyad"]), (K_GOREV, per["dose_gorevi"] or ""), (K_BOLUM, per["bolum"] or "")):
            it = QTableWidgetItem(v)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.t.setItem(r, c, it)
        unvan = QSpinBox()
        unvan.setRange(1, 5)
        unvan.setValue(int(per["unvan_grubu"] or mevzuat.GOREV_VARSAYILAN_UNVAN_GRUBU.get(per["dose_gorevi"], 5)))
        gun = ParaKutusu(ondalik=1, azami=366)
        gun.ayarla(k.get("fiili_gun"))
        saat = ParaKutusu(ondalik=1, azami=10000)
        saat.ayarla(k.get("fazla_calisma_saat"))
        katki = ParaKutusu(ondalik=3, azami=100)
        katki.ayarla(k.get("katki_orani"))
        takdir = ParaKutusu(ondalik=3, azami=100)
        takdir.ayarla((k.get("takdir_orani") or 0) * 100)
        haric = QCheckBox()
        haric.setChecked(bool(k.get("haric")))
        neden = QLineEdit(k.get("haric_neden") or "")
        diger = ParaKutusu()
        diger.ayarla(k.get("diger_isletme_utp"))
        diger.setEnabled(per["dose_gorevi"] == "Sayman")
        diger.setToolTip("Birden fazla işletmede görev yapan saymanlar için diğer işletmelerden alınan ÜTP (md.5/9)")
        onceki = ParaKutusu()
        onceki.ayarla(k.get("onceki_kumulatif"))
        onceki.setToolTip("Ödeme yılındaki GV kümülatif matrahı (maaş bordrosundaki matrah esas alınabilir)")
        w = {"unvan": unvan, "gun": gun, "saat": saat, "katki": katki, "takdir": takdir, "haric": haric, "neden": neden,
             "diger": diger, "onceki": onceki}
        for c, x in ((K_UNVAN, unvan), (K_GUN, gun), (K_SAAT, saat), (K_KATKI, katki), (K_TAKDIR, takdir), (K_HARIC, haric),
                     (K_NEDEN, neden), (K_DIGER, diger), (K_ONCEKI, onceki)):
            self.t.setCellWidget(r, c, x)
            if self.kesin:
                x.setEnabled(False)
        for c in range(len(BASLIKLAR) - len(CIKTI_KOLONLARI), len(BASLIKLAR)):
            it = QTableWidgetItem()
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.t.setItem(r, c, it)
        self.satirlar.append({"id": pid, "per": per, "w": w})

    def saat_getir(self):
        saat_ucreti = self.p["fazla_calisma_saat_ucreti"]
        if not saat_ucreti:
            uyari(self, "Parametrelerde fazla çalışma saat ücreti tanımlı değil; parça başı ücretler saate çevrilemedi.")
        for s in self.satirlar:
            fc = db().deger("SELECT SUM(saat) FROM fazla_calisma WHERE yil = ? AND personel_id = ? AND durum = 'Onaylandı'",
                            (self.yil, s["id"]), 0.0)
            pb = db().deger("""SELECT SUM(r.brut) FROM parca_basi_satir r JOIN parca_basi p ON p.id = r.parca_basi_id
                               WHERE p.yil = ? AND p.durum = 'Onaylandı' AND r.kisi_turu = 'Personel' AND r.kisi_id = ?""",
                            (self.yil, s["id"]), 0.0)
            pb_saat = parca_basi_gun(pb, saat_ucreti) * 8 if saat_ucreti else 0.0
            s["w"]["saat"].ayarla(yuvarla(fc + pb_saat, 1))
        self.hesapla()

    # ------------------------------------------------------------ hesap
    def hesapla(self):
        if not hasattr(self, "satirlar"):
            return
        b0 = yil_sonu_bolusum(self.kar.deger(), self.kurum.get("tahsis_sermaye") or 0, self.kurum.get("odenmis_sermaye") or 0,
                              self._oran(), self.p, None, self.faiz.deger())
        kisiler = []
        for s in self.satirlar:
            w = s["w"]
            kisiler.append(UtpKisi(id=s["id"], ad=s["per"]["ad_soyad"], gorev=s["per"]["dose_gorevi"] or "",
                                   unvan_grubu=w["unvan"].value(), bolum_id=s["per"]["bolum_id"], fiili_gun=w["gun"].deger(),
                                   fazla_calisma_saat=w["saat"].deger(), katki_orani=w["katki"].deger(),
                                   takdir_orani=w["takdir"].deger(), haric=w["haric"].isChecked(), onceki_utp=w["diger"].deger()))
        bolum_gel = muhasebe.bolum_gelirleri(self.yil)
        yontem = {r["id"]: r["utp_yontemi"] for r in db().q("SELECT id, utp_yontemi FROM bolum")}
        sonuc = utp_dagit(b0.dagitima_esas, kisiler, bolum_gel, yontem, self.p, self.yuz_yuze)
        b = yil_sonu_bolusum(self.kar.deger(), self.kurum.get("tahsis_sermaye") or 0, self.kurum.get("odenmis_sermaye") or 0,
                             self._oran(), self.p, sonuc.toplam_odenecek, self.faiz.deger())
        self.shcek = yuvarla(self.hasilat * self.p["shcek_orani"])
        self.bolusum, self.sonuc = b, sonuc
        for a in ("utp_azami", "dagitima_esas", "dagitilan_utp", "sermaye_payi", "merkez_payi"):
            self.s[a].setText(para(getattr(b, a)) + " TL")
        self.s["shcek"].setText(para(self.shcek) + " TL")
        self.hesaplananlar = {}
        for i, (s, k) in enumerate(zip(self.satirlar, kisiler)):
            kes = ucret_kesintileri(k.odenecek, s["w"]["onceki"].deger(), 2, self.p_odeme)
            self.hesaplananlar[s["id"]] = (k, kes)
            ilk = len(BASLIKLAR) - len(CIKTI_KOLONLARI)
            for j, v in enumerate((k.idari, k.takdir, k.bolum, k.hesaplanan, k.tavan_asimi, k.odenecek, kes.gelir_vergisi,
                                   kes.damga_vergisi, kes.net)):
                self.t.item(i, ilk + j).setText(para(v))
        hatalar, uyarilar = [], list(b.notlar) + list(sonuc.notlar)
        if self.kar.deger() <= 0:
            hatalar.append("Bilanço kârı yok; ÜTP dağıtılamaz.")
        if self._oran() > self.p["utp_azami_oran"] + 1e-9:
            hatalar.append("ÜTP oranı 1/3'ü aşamaz.")
        for s in self.satirlar:
            w = s["w"]
            if w["haric"].isChecked() and not w["neden"].text().strip():
                uyarilar.append(f"{s['per']['ad_soyad']}: hariç tutma nedeni yazılmalıdır (md.6).")
        komisyon_takdir = [s["per"]["ad_soyad"] for s in self.satirlar if s["w"]["takdir"].deger() > 0 and (
            s["per"]["dose_gorevi"] in mevzuat.SEF_GOREVLERI or (s["per"]["dose_gorevi"] or "").startswith(("Harcama", "Gerçekleştirme")))]
        if komisyon_takdir:
            uyarilar.append("Takdir komisyonu üyeleri takdir payından yararlanamaz (md.5/6): " + ", ".join(komisyon_takdir))
        if abs(self.kar.deger() - self.kar_onerilen) > 1 and self.gt["toplam_gelir"]:
            uyarilar.append("Esas alınan bilanço kârı yardımcı defterdeki kârdan farklı; BKMYBS bilançosunu esas alınız.")
        uyarilar.append("Yıl içinde 30 günden fazla okul dışında görevlendirilenler ve DÖSE çalışmalarına fiilen katılmayanlar "
                        "hariç tutulmalıdır (md.6).")
        self.mesaj.goster(hatalar, uyarilar)
        self._hatalar = hatalar

    # ------------------------------------------------------------ kayıt
    def kaydet(self, sessiz=False):
        if not yetki_kontrol(self):
            return False
        self.hesapla()
        b = self.bolusum
        v = {"yil": self.yil, "toplam_gelir": self.gt["toplam_gelir"], "toplam_gider": self.gt["toplam_gider"],
             "donem_kari": self.kar.deger(), "faiz_duzeltme": self.faiz.deger(), "utp_orani": self._oran(),
             "dagitima_esas": b.dagitima_esas, "dagitilan_utp": b.dagitilan_utp, "sermaye_payi": b.sermaye_payi,
             "merkez_payi": b.merkez_payi, "shcek": self.shcek,
             "yontem": "Yön. md.5/2-7" if self.yuz_yuze else "Yön. md.5/8", "durum": self.ys.get("durum") or "Taslak"}
        db().ex("INSERT OR REPLACE INTO yil_sonu (" + ", ".join(v) + ") VALUES (" + ", ".join("?" * len(v)) + ")", list(v.values()))
        db().ex("DELETE FROM utp_kisi WHERE yil = ?", (self.yil,))
        for s in self.satirlar:
            k, kes = self.hesaplananlar[s["id"]]
            w = s["w"]
            db().ekle("utp_kisi", {
                "yil": self.yil, "personel_id": s["id"], "fiili_gun": w["gun"].deger(), "fazla_calisma_saat": w["saat"].deger(),
                "katki_orani": w["katki"].deger(), "takdir_orani": w["takdir"].deger() / 100, "haric": int(w["haric"].isChecked()),
                "haric_neden": w["neden"].text().strip() or None, "idari_pay": k.idari, "takdir_pay": k.takdir, "bolum_pay": k.bolum,
                "hesaplanan": k.hesaplanan, "tavan_asimi": k.tavan_asimi, "brut": k.odenecek, "onceki_kumulatif": w["onceki"].deger(),
                "gelir_vergisi": kes.gelir_vergisi, "damga_vergisi": kes.damga_vergisi, "net": kes.net,
                "diger_isletme_utp": w["diger"].deger()}, log=False)
            db().guncelle("personel", s["id"], {"unvan_grubu": w["unvan"].value()}, log=False)
        db().log("Yıl sonu kaydı", "yil_sonu", self.yil)
        if not sessiz:
            bilgi(self, "Yıl sonu dağıtımı kaydedildi.")
        self.ys = db().q1("SELECT * FROM yil_sonu WHERE yil = ?", (self.yil,)) or {}
        return True

    def kesinlestir(self):
        if onay.akis_acik():
            if self.onay_durumu["durum"] in (onay.HAZIRLANIYOR, onay.IADE) and not self.kesin:
                self.hesapla()
                if self._hatalar:
                    uyari(self, "\n".join(self._hatalar))
                    return
                if not self.kaydet(sessiz=True):
                    return
            if OnayDialog(self, "Yıl Sonu", self.yil).exec():
                self.yenile()
            return
        self.hesapla()
        if self._hatalar:
            uyari(self, "\n".join(self._hatalar))
            return
        if not soru(self, "Dağıtım kesinleştirilsin mi? ÜTP tahakkuku (570 / 360-335) ve SHÇEK payı (770 / 362) yardımcı yevmiyeye "
                          "kaydedilecek ve tablo kilitlenecek."):
            return
        if not self.kaydet(sessiz=True):
            return
        try:
            onay.dogrudan_onayla("Yıl Sonu", self.yil, Oturum.kullanici)
        except onay.OnayHatasi as e:
            uyari(self, str(e))
        self.yenile()

    def geri_al(self):
        if not yetki_kontrol(self, yonetici=True):
            return
        if onay_kaldir(self, "Yıl Sonu", self.yil, "Kesinleştirme kaldırılsın mı? ÜTP ve SHÇEK yevmiye kayıtları silinecek."):
            self.yenile()

    # ------------------------------------------------------------ çıktılar
    def _kayitli_mi(self):
        if not self.ys:
            uyari(self, "Önce dağıtımı kaydediniz.")
            return False
        return True

    def cetvel(self):
        if self._kayitli_mi():
            dosya_ac(belgeler.utp_cetveli(cikti_yolu(f"UTP_Cetveli_{self.yil}"), self.yil))

    def banka(self):
        if not self._kayitli_mi():
            return
        satirlar = db().q("""SELECT p.ad_soyad, p.tckn, p.iban, u.net FROM utp_kisi u JOIN personel p ON p.id = u.personel_id
                             WHERE u.yil = ? AND u.net > 0 ORDER BY p.ad_soyad""", (self.yil,))
        yol = cikti_yolu(f"Banka_UTP_{self.yil}", "xlsx")
        excel.disa_aktar(yol, [("Banka listesi", ["Adı soyadı", "T.C. kimlik no", "IBAN", "Net tutar", "Açıklama"],
                                [[s["ad_soyad"], s["tckn"] or "", s["iban"] or "", s["net"], f"{self.yil} yılı ÜTP"] for s in satirlar])],
                         f"{self.yil} yılı üretimi teşvik primi banka ödeme listesi")
        dosya_ac(yol)

    def _yazi(self, ad, konu, muhatap, metin):
        k = self.kurum
        imza1 = f"{k.get('sayman') or ''}\nSayman"
        imza2 = f"{k.get('harcama_yetkilisi') or ''}\nOkul Müdürü / Harcama Yetkilisi"
        yazi = {"sayi": f"{k.get('evrak_kodu') or ''}", "konu": konu, "tarih": bugun(), "muhatap": muhatap,
                "ilgi": "Millî Eğitim Bakanlığı Destek Hizmetleri Genel Müdürlüğünün 15.01.2026 tarihli DÖSE konulu yazısı.",
                "metin": metin, "imza1": imza1, "imza2": imza2}
        db().ekle("resmi_yazi", {x: yazi[x] for x in ("tarih", "sayi", "konu", "muhatap", "ilgi", "metin", "imza1", "imza2")})
        dosya_ac(belgeler.resmi_yazi(cikti_yolu(ad), yazi))

    def merkez_yazisi(self):
        if not self._kayitli_mi():
            return
        ms = mevzuat.MERKEZ_SAYMANLIK
        ilce = (self.kurum.get("ilce") or "").strip()
        muhatap = f"{tr_buyuk(ilce)} İLÇE MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE" if ilce and tr_buyuk(ilce) != "MERKEZ" else \
            f"{tr_buyuk(self.kurum.get('il') or '')} İL MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE"
        metin = (f"Okulumuz Döner Sermaye İşletmesinin {self.yil} yılı bilanço kârı {para(self.ys['donem_kari'])} TL olup, 3423 sayılı "
                 f"Kanun ve ilgi yazı gereğince kârın {para(self.ys['dagitilan_utp'])} TL'si üretimi teşvik primi olarak dağıtılmış, "
                 f"{para(self.ys['sermaye_payi'])} TL'si sermayeye eklenmiş, {para(self.ys['merkez_payi'])} TL'si ise {ms['ad']} "
                 f"(VKN: {ms['vkn']}) {ms['iban']} IBAN numaralı hesabına ...../...../{self.yil + 1} tarihinde yatırılmıştır. "
                 f"Ayrıca yıllık brüt hasılatın %1'i olan {para(self.ys['shcek'])} TL SHÇEK payı ilgili hesaba yatırılmıştır.\n\n"
                 "Dekontlar MEBBİS Döner Sermaye Takip Modülüne yüklenmiş olup ekte sunulmuştur.\n\nBilgilerinize arz ederim.")
        self._yazi(f"Kar_Aktarimi_Yazisi_{self.yil}", f"{self.yil} Yılı Kâr Payı Aktarımı", muhatap, metin)

    def shcek_yazisi(self):
        if not self._kayitli_mi():
            return
        metin = (f"Okulumuz Döner Sermaye İşletmesinin {self.yil} yılı brüt hasılatı {para(self.hasilat)} TL olup, 2828 sayılı "
                 f"Sosyal Hizmetler Kanununun 18 inci maddesinin (1) numaralı fıkrasının (k) bendi gereğince hesaplanan "
                 f"{para(self.ys['shcek'])} TL SHÇEK payı ...../01/{self.yil + 1} tarihinde ilgili hesaba yatırılmıştır.\n\n"
                 "Bilgilerinize arz ederim.")
        self._yazi(f"SHCEK_Yazisi_{self.yil}", f"{self.yil} Yılı SHÇEK Payı", "İLGİLİ MAKAMA", metin)
