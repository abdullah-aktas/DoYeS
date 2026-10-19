"""Döner sermaye fazla çalışma ücreti bordrosu."""
import calendar
from datetime import date

from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ... import belgeler, excel, mevzuat, onay
from ...denetim import fazla_calisma_denetimi, puantaj_coz, puantaj_yaz
from ...hesap import gun_turu, para, ucret_kesintileri, yuvarla
from ...islemler import fc_onceki_kumulatif
from ..ortak import (Kolon, MesajKutusu, Oturum, ParaKutusu, SecimKutusu, VeriTablosu, baslik_etiketi, bilgi, bugun, buton,
                     cikti_yolu, db, dosya_ac, fk_secenekleri, kayit_izle, soru, uyari, yetki_kontrol)
from .onay_sayfa import OnayDialog, onay_kaldir
from .parca_basi import PuantajDialog

TUR = "Fazla Çalışma"


class FazlaCalismaSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "Fazla Çalışma Ücreti",
            "Olağan çalışma saatleri dışında fiilen çalışılan saatler için ödenir: öğretim günlerinde günde en çok 3, bayram dışındaki "
            "tatillerde 8 saat; saat ücreti 67,50 TL'yi geçemez, yardımcı hizmetler sınıfı ve şoförler yararlanamaz (2026 Bütçe K cetveli "
            "III-3). Pazar günü çalışılmaz (Yön. md.9/a-12). Aynı iş için parça başı alana ödenmez (Yön. md.8/7). Ödeme izleyen ayın "
            "10'una kadar yapılır (Yön. md.9/b)."))
        ust = QHBoxLayout()
        ust.addWidget(QLabel("Ay:"))
        self.ay = SecimKutusu(secenekler=[(i + 1, a) for i, a in enumerate(mevzuat.AYLAR)])
        self.ay.ayarla(int(bugun()[5:7]))
        self.ay.currentIndexChanged.connect(self.yenile)
        ust.addWidget(self.ay)
        self.b_yeni = buton("＋ Kayıt ekle", self.yeni, "birincil")
        ust.addWidget(self.b_yeni)
        ust.addWidget(buton("Düzenle", self.duzenle))
        ust.addWidget(buton("Sil", self.sil, "tehlike"))
        self.b_onay = buton("Ayı onayla", self.onayla)
        ust.addWidget(self.b_onay)
        ust.addWidget(buton("Onay akışı", self.onay_akisi, ipucu="Seçili kaydın onay aşamaları ve geçmişi"))
        ust.addWidget(buton("Onayı kaldır", self.onay_kaldir))
        ust.addWidget(buton("Bordro PDF", self.pdf))
        ust.addWidget(buton("Puantaj (mesai çizelgesi) PDF", self.puantaj_pdf,
                            ipucu="Şef, gerçekleştirme görevlisi ve sayman imzalı, müdür onaylı aylık fazla çalışma çizelgesi"))
        ust.addWidget(buton("Banka listesi (Excel)", self.banka))
        ust.addWidget(buton("Ödeme kaydı oluştur", self.odeme))
        ust.addStretch()
        lay.addLayout(ust)
        self.tablo = VeriTablosu()
        self.tablo.satirCiftTiklandi.connect(lambda _s: self.duzenle())
        lay.addWidget(self.tablo)
        self.ozet = QLabel()
        lay.addWidget(self.ozet)
        self.yenile()

    def _kosul(self):
        kosul, prm = "f.yil = ? AND f.ay = ?", [Oturum.yil, self.ay.deger()]
        if Oturum.ogretmen():
            kosul += " AND f.personel_id = ?"
            prm.append(Oturum.personel_id() or -1)
        elif Oturum.bolum_id():
            kosul += " AND COALESCE(s.bolum_id, p.bolum_id) = ?"
            prm.append(Oturum.bolum_id())
        return kosul, prm

    def yenile(self):
        kosul, prm = self._kosul()
        self.satirlar = db().q(f"""SELECT f.*, p.ad_soyad, p.dose_gorevi, p.iban, p.tckn, s.siparis_no
                                   FROM fazla_calisma f JOIN personel p ON p.id = f.personel_id LEFT JOIN siparis s ON s.id = f.siparis_id
                                   WHERE {kosul} ORDER BY p.ad_soyad""", prm)
        durumlar = onay.durumlar(TUR)
        for s in self.satirlar:
            s["onay"] = onay.durum_metni(durumlar[s["id"]]) if s["id"] in durumlar else (
                onay.ONAYLANDI if s["durum"] == "Onaylandı" else onay.HAZIRLANIYOR)
        self.tablo.doldur(
            [Kolon("ad_soyad", "Adı soyadı"), Kolon("dose_gorevi", "Görevi"), Kolon("siparis_no", "Sipariş"), Kolon("saat", "Saat", "sayi"),
             Kolon("saat_ucreti", "Saat ücreti", "para"), Kolon("brut", "Brüt", "para"), Kolon("onceki_kumulatif", "Önceki kümülatif", "para"),
             Kolon("gelir_vergisi", "Gelir v.", "para"), Kolon("damga_vergisi", "Damga v.", "para"), Kolon("net", "Net", "para"),
             Kolon("onay", "Onay durumu")],
            self.satirlar, lambda s: "#eef6ee" if s["durum"] == "Onaylandı" else ("#fff4e5" if s["onay"].startswith("Bekliyor") else None))
        self.ozet.setText(f"{len(self.satirlar)} kayıt • Toplam saat: {sum(s['saat'] for s in self.satirlar):g} • Brüt: "
                          f"{para(sum(s['brut'] for s in self.satirlar))} TL • Net: {para(sum(s['net'] for s in self.satirlar))} TL")
        self.b_yeni.setEnabled(Oturum.yazabilir(self))
        self.b_onay.setText("Ayın kayıtlarını onaya gönder" if onay.akis_acik() else "Ayı onayla")

    def _anahtar(self):
        return Oturum.yil * 100 + self.ay.deger()

    def _odeme_var(self) -> bool:
        return bool(db().deger("SELECT COUNT(*) FROM kasa_banka WHERE kaynak = 'FazlaCalisma' AND kaynak_id = ?", (self._anahtar(),)))

    def _degistirilebilir(self, s) -> bool:
        if s["durum"] == "Onaylandı":
            uyari(self, "Onaylı kayıt değiştirilemez; önce onayı kaldırınız.")
            return False
        if onay.durum(TUR, s["id"])["durum"] == onay.BEKLIYOR:
            uyari(self, "Onay sürecindeki kayıt değiştirilemez; önce 'Onay akışı' penceresinden geri çekiniz.")
            return False
        return yetki_kontrol(self)

    def yeni(self):
        if not yetki_kontrol(self):
            return
        if self._odeme_var():
            uyari(self, "Bu ayın fazla çalışma ödeme kaydı oluşturulmuş; yeni kayıt eklenemez.")
            return
        if FazlaCalismaDialog(self, Oturum.yil, self.ay.deger()).exec():
            self.yenile()

    def duzenle(self):
        s = self.tablo.secili()
        if s and self._degistirilebilir(s) and FazlaCalismaDialog(self, s["yil"], s["ay"], s["id"]).exec():
            self.yenile()

    def sil(self):
        s = self.tablo.secili()
        if not s or not self._degistirilebilir(s):
            return
        if soru(self, f"{s['ad_soyad']} kaydı silinsin mi?"):
            with db().islem():
                db().sil("fazla_calisma", s["id"])
                onay.sil(TUR, s["id"])
            self.yenile()

    def onayla(self):
        if not yetki_kontrol(self) or not self.satirlar:
            return
        adaylar = [s for s in self.satirlar if s["durum"] != "Onaylandı"
                   and onay.durum(TUR, s["id"])["durum"] in (onay.HAZIRLANIYOR, onay.IADE)]
        if not adaylar:
            bilgi(self, "Onaylanacak veya onaya gönderilecek kayıt yok.")
            return
        donem = f"{mevzuat.AYLAR[self.ay.deger() - 1]} {Oturum.yil}"
        if onay.akis_acik():
            if not soru(self, f"{donem}: {len(adaylar)} fazla çalışma kaydı onaya gönderilsin mi?"):
                return
            islev = lambda bid: onay.gonder(TUR, bid, Oturum.kullanici)
        else:
            if not soru(self, f"{donem} fazla çalışma bordrosu onaylansın mı?"):
                return
            islev = lambda bid: onay.dogrudan_onayla(TUR, bid, Oturum.kullanici)
        hatalar = []
        for s in adaylar:
            try:
                islev(s["id"])
            except onay.OnayHatasi as e:
                hatalar.append(f"{s['ad_soyad']}: {e}")
        if hatalar:
            uyari(self, "\n\n".join(hatalar))
        self.yenile()

    def onay_akisi(self):
        s = self.tablo.secili()
        if not s:
            bilgi(self, "Önce bir kayıt seçiniz.")
            return
        if OnayDialog(self, TUR, s["id"]).exec():
            self.yenile()

    def onay_kaldir(self):
        if onay.akis_acik():
            s = self.tablo.secili()
            if s and s["durum"] == "Onaylandı" and onay_kaldir(self, TUR, s["id"], f"{s['ad_soyad']} kaydının onayı kaldırılsın mı?"):
                self.yenile()
            return
        onayli = [s for s in self.satirlar if s["durum"] == "Onaylandı"]
        if not yetki_kontrol(self) or not onayli:
            return
        if self._odeme_var():
            uyari(self, "Bu aya ait ödeme kaydı var; önce kasa/banka kaydını siliniz.")
            return
        if soru(self, "Ayın onayı kaldırılsın mı?"):
            with db().islem():
                for s in onayli:
                    onay.geri_al(TUR, s["id"], Oturum.kullanici, "Ayın onayı kaldırıldı", yetki_denetle=False)
            self.yenile()

    def pdf(self):
        if self.satirlar:
            dosya_ac(belgeler.fazla_calisma_bordrosu(cikti_yolu(f"FazlaCalisma_{Oturum.yil}_{self.ay.deger():02d}"),
                                                     Oturum.yil, self.ay.deger()))

    def puantaj_pdf(self):
        if self.satirlar:
            dosya_ac(belgeler.fazla_calisma_puantaj(cikti_yolu(f"FazlaCalisma_Puantaj_{Oturum.yil}_{self.ay.deger():02d}"),
                                                    Oturum.yil, self.ay.deger()))

    def banka(self):
        if not self.satirlar:
            return
        donem = f"{mevzuat.AYLAR[self.ay.deger() - 1]} {Oturum.yil}"
        satir = [[s["ad_soyad"], s["tckn"] or "", s["iban"] or "", s["net"], f"{donem} fazla çalışma ücreti"] for s in self.satirlar]
        yol = cikti_yolu(f"Banka_FazlaCalisma_{Oturum.yil}_{self.ay.deger():02d}", "xlsx")
        excel.disa_aktar(yol, [("Banka listesi", ["Adı soyadı", "T.C. kimlik no", "IBAN", "Net tutar", "Açıklama"], satir)],
                         "Fazla çalışma ücreti banka ödeme listesi")
        dosya_ac(yol)

    def odeme(self):
        if not yetki_kontrol(self, sayfa="Kasa / Banka"):
            return
        tum = db().q("SELECT durum, net FROM fazla_calisma WHERE yil = ? AND ay = ?", (Oturum.yil, self.ay.deger()))
        if not tum:
            return
        if any(r["durum"] != "Onaylandı" for r in tum):
            uyari(self, "Ayın bütün fazla çalışma kayıtları onaylanmadan ödeme kaydı oluşturulamaz.")
            return
        if self._odeme_var():
            uyari(self, "Bu ay için ödeme kaydı zaten var.")
            return
        from .kasa import KasaDialog
        KasaDialog(self, on_deger={"yon": "Çıkış", "tur": "Personel Ödemesi", "hesap": "Banka (102)",
                                   "tutar": yuvarla(sum(r["net"] for r in tum)),
                                   "aciklama": f"{mevzuat.AYLAR[self.ay.deger() - 1]} {Oturum.yil} fazla çalışma ücreti",
                                   "kaynak": "FazlaCalisma", "kaynak_id": self._anahtar()}).exec()


class FazlaCalismaDialog(QDialog):
    def __init__(self, parent, yil, ay, kayit_id=None):
        super().__init__(parent)
        kayit_izle(self, "fazla_calisma", kayit_id)
        self.yil, self.ay, self.kid = yil, ay, kayit_id
        self.p = db().parametreler(yil)
        k = db().q1("SELECT * FROM fazla_calisma WHERE id = ?", (kayit_id,)) if kayit_id else {}
        self.setWindowTitle(f"Fazla çalışma - {mevzuat.AYLAR[ay - 1]} {yil}")
        self.resize(560, 420)
        f = QFormLayout(self)
        kisit = Oturum.bolum_id()
        if Oturum.ogretmen():
            per_kosul = f"id = {int(Oturum.personel_id() or -1)}"
        elif kisit:
            per_kosul = f"aktif = 1 AND bolum_id = {int(kisit)}"
        else:
            per_kosul = "aktif = 1"
        self.personel = SecimKutusu(secenekler=fk_secenekleri("personel", "ad_soyad", per_kosul), bos=not Oturum.ogretmen())
        self.siparis = SecimKutusu(secenekler=fk_secenekleri("siparis", "siparis_no || ' - ' || COALESCE(konu, '')",
                                                             "durum != 'İptal'" + (f" AND bolum_id = {int(kisit)}" if kisit else ""),
                                                             "id DESC"), bos=True)
        self.saat = ParaKutusu(ondalik=1, azami=1000)
        self.ucret = ParaKutusu()
        self.onceki = ParaKutusu()
        self.aciklama = QLineEdit()
        self.sonuc = QLabel()
        self.mesaj = MesajKutusu()
        self.puantaj = puantaj_coz(k.get("puantaj"))
        self.puantaj_bilgi = QLabel()
        self.puantaj_bilgi.setWordWrap(True)
        f.addRow("Personel *:", self.personel)
        f.addRow("Sipariş:", self.siparis)
        saat_satir = QHBoxLayout()
        saat_satir.addWidget(self.saat, 1)
        saat_satir.addWidget(buton("Günlük puantaj…", self.puantaj_ac,
                                   ipucu="Gün gün çalışılan saatler; öğretim günü / tatil / bayram sınırları gün bazında denetlenir"))
        f.addRow("Fiilen çalışılan saat *:", saat_satir)
        f.addRow("", self.puantaj_bilgi)
        f.addRow("Saat ücreti (brüt):", self.ucret)
        f.addRow("Önceki kümülatif matrah:", self.onceki)
        f.addRow("Açıklama:", self.aciklama)
        f.addRow(self.sonuc)
        f.addRow(self.mesaj)
        bb = QHBoxLayout()
        bb.addStretch()
        bb.addWidget(buton("Kaydet", self.kaydet, "birincil"))
        bb.addWidget(buton("Vazgeç", self.reject))
        f.addRow(bb)
        self.personel.ayarla(k.get("personel_id") or (Oturum.personel_id() if Oturum.ogretmen() else None))
        self.siparis.ayarla(k.get("siparis_id"))
        self.saat.ayarla(k.get("saat"))
        self.ucret.ayarla(k.get("saat_ucreti") or self.p["fazla_calisma_saat_ucreti"])
        self.onceki.ayarla(k.get("onceki_kumulatif"))
        self.aciklama.setText(k.get("aciklama") or "")
        self.personel.currentIndexChanged.connect(self._personel_degisti)
        for w in (self.siparis,):
            w.currentIndexChanged.connect(self.hesapla)
        for w in (self.saat, self.ucret, self.onceki):
            w.valueChanged.connect(self.hesapla)
        if not self.kid:
            self._personel_degisti()
        self._puantaj_goster()
        self.hesapla()

    def gun_renkleri(self) -> dict[int, str]:
        renk = {"tatil": "#dbe9f7", "pazar": "#cfcfcf", "bayram": "#f4c7c3"}
        return {g: renk[t] for g in range(1, calendar.monthrange(self.yil, self.ay)[1] + 1)
                if (t := gun_turu(date(self.yil, self.ay, g), self.p)) in renk}

    def puantaj_ac(self):
        ad = self.personel.currentText() or "Personel"
        p = self.p
        acik = (f"Personelin olağan çalışma saatleri dışında fiilen çalıştığı saatleri gün gün giriniz. Öğretim günlerinde en çok "
                f"{p['fc_ogretim_gunu_saat']:g}, tatillerde (mavi: Cumartesi, yarıyıl, ara ve yaz tatili, resmi tatil) en çok "
                f"{p['fc_tatil_gunu_saat']:g} saat yazılabilir; kırmızı günler resmi/dini bayramdır, fazla çalışma yapılamaz "
                f"(2026 Bütçe K cetveli III-3). Koyu gri Pazar günleridir"
                + ("." if p.get("fc_pazar_izinli") else "; Pazar günü fazla çalışma yapılmaz (Çalışma Yönergesi md.9/a-12).")
                + " Puantaj; atölye/bölüm şefince düzenlenir, gerçekleştirme görevlisi ve saymanca imzalanır, müdürce onaylanır "
                "(Yön. md.9/c-e).")
        d = PuantajDialog(self, self.yil, self.ay, [{"tur": "Personel", "bilgi": {"ad": ad}, "puantaj": self.puantaj}],
                          baslik="Fazla çalışma puantajı", aciklama=acik, gun_renkleri=self.gun_renkleri(), yukseklik=260)
        if d.exec():
            self.puantaj = d.sonuc()[0]
            self._puantaj_goster()
            self.hesapla()

    def _puantaj_goster(self):
        if self.puantaj:
            toplam = sum(self.puantaj.values())
            self.saat.ayarla(toplam)
            self.saat.setEnabled(False)
            gunler = ", ".join(f"{g}:{v:g}" for g, v in sorted(self.puantaj.items()))
            self.puantaj_bilgi.setText(f"<small>Puantajdan: {len(self.puantaj)} gün, {toplam:g} saat ({gunler})</small>")
        else:
            self.saat.setEnabled(True)
            self.puantaj_bilgi.setText("<small>Günlük puantaj girilmemiş.</small>")

    def _personel_degisti(self):
        pid = self.personel.deger()
        if pid and not self.kid:
            self.onceki.ayarla(fc_onceki_kumulatif(db(), self.yil, self.ay, pid))
        self.hesapla()

    def hesapla(self):
        if not hasattr(self, "mesaj"):
            return None
        brut = yuvarla(self.saat.deger() * self.ucret.deger())
        k = ucret_kesintileri(brut, self.onceki.deger(), self.ay, self.p)
        self.sonuc.setText(f"Brüt: {para(brut)} TL • GV: {para(k.gelir_vergisi)} • DV: {para(k.damga_vergisi)} • <b>Net: {para(k.net)} TL</b>")
        pid = self.personel.deger()
        hatalar = []
        if not pid:
            hatalar.append("Personel seçiniz." if not Oturum.ogretmen() else
                           "Kullanıcı hesabınız bir personel kaydına bağlı değil; sistem yöneticisine başvurunuz.")
        if not self.ucret.deger():
            hatalar.append("Saat ücreti girilmemiş. Parametreler sayfasında güncel fazla çalışma saat ücretini tanımlayınız.")
        h, uyarilar = fazla_calisma_denetimi(db(), self._degerler(), self.kid, self.p)
        hatalar += h
        uyarilar.append("Fazla çalışma; görevlendirme onayı ve müdürce onaylı puantaj (mesai çizelgesi) ile belgelendirilir. Fiilen "
                        "çalışmayana ödeme yapılırsa bir katı fazlasıyla geri alınır, yarısı çizelgeyi onaylayandan tahsil edilir "
                        "(Bütçe K cetveli III-4).")
        self.mesaj.goster(hatalar, uyarilar)
        self._hatalar = hatalar
        return brut, k

    def _degerler(self) -> dict:
        return {"yil": self.yil, "ay": self.ay, "personel_id": self.personel.deger(), "siparis_id": self.siparis.deger(),
                "saat": self.saat.deger(), "saat_ucreti": self.ucret.deger(), "puantaj": puantaj_yaz(self.puantaj)}

    def kaydet(self):
        brut, k = self.hesapla()
        if self._hatalar:
            uyari(self, "\n".join(self._hatalar))
            return
        v = {**self._degerler(), "brut": brut, "onceki_kumulatif": self.onceki.deger(),
             "gelir_vergisi": k.gelir_vergisi, "damga_vergisi": k.damga_vergisi, "net": k.net,
             "aciklama": self.aciklama.text().strip() or None, "durum": "Taslak"}
        if self.kid:
            db().guncelle("fazla_calisma", self.kid, v)
        else:
            db().ekle("fazla_calisma", v)
        self.accept()
