"""Kasa ve banka hareketleri (tahsilat, ödeme, avans, yükümlülük ödemeleri)."""
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ... import mevzuat, muhasebe
from ...hesap import para, yuvarla
from ..ortak import (Kart, Kolon, Oturum, ParaKutusu, SecimKutusu, TarihKutusu, VeriTablosu, baslik_etiketi, buton, db,
                     fk_secenekleri, kayit_izle, soru, tablo_excele, uyari, yetki_kontrol)

GIRIS_TURLERI = ["Tahsilat", "Peşinat/Avans Tahsilatı", "Faiz/Diğer Gelir", "Sermaye", "Diğer"]
CIKIS_TURLERI = ["Ödeme", "Hazine Payı Ödemesi", "SHÇEK Payı Ödemesi", "Vergi Ödemesi", "Personel Ödemesi",
                 "Merkez Saymanlık Kâr Aktarımı", "Diğer"]


def hesap_bakiyesi(hesap: str, tarihe_kadar: str | None = None, haric_id: int | None = None) -> float:
    sql = "SELECT SUM(CASE WHEN yon = 'Giriş' THEN tutar ELSE -tutar END) FROM kasa_banka WHERE hesap = ?"
    prm = [hesap]
    if tarihe_kadar:
        sql += " AND tarih <= ?"
        prm.append(tarihe_kadar)
    if haric_id:
        sql += " AND id != ?"
        prm.append(haric_id)
    return yuvarla(db().deger(sql, prm, 0.0))


class KasaSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "Kasa / Banka",
            "Tahsilat ve ödemeler. Tahsilatlarda KDV hariç hasılat payı otomatik hesaplanır ve aylık hazine payı (%1) bu tutar üzerinden "
            "bulunur. Her hareket için yardımcı yevmiye kaydı oluşturulur."))
        kartlar = QHBoxLayout()
        self.k_kasa = Kart("Kasa (100) bakiyesi")
        self.k_banka = Kart("Banka (102) bakiyesi")
        self.k_giris = Kart("Dönem girişleri")
        self.k_cikis = Kart("Dönem çıkışları")
        for k in (self.k_kasa, self.k_banka, self.k_giris, self.k_cikis):
            kartlar.addWidget(k)
        lay.addLayout(kartlar)
        ust = QHBoxLayout()
        self.b_giris = buton("＋ Giriş (tahsilat)", lambda: self.yeni("Giriş"), "birincil")
        self.b_cikis = buton("－ Çıkış (ödeme)", lambda: self.yeni("Çıkış"))
        ust.addWidget(self.b_giris)
        ust.addWidget(self.b_cikis)
        ust.addWidget(buton("Düzenle", self.duzenle))
        ust.addWidget(buton("Sil", self.sil, "tehlike"))
        ust.addWidget(buton("Excel'e Aktar", lambda: tablo_excele(self, self.tablo, "Kasa_Banka")))
        ust.addStretch()
        ust.addWidget(QLabel("Hesap:"))
        self.hesap = SecimKutusu(secenekler=[(None, "Tümü")] + mevzuat.KASA_HESAPLARI)
        self.hesap.currentIndexChanged.connect(self.yenile)
        ust.addWidget(self.hesap)
        ust.addWidget(QLabel("Ay:"))
        self.ay = SecimKutusu(secenekler=[(0, "Tüm yıl")] + [(i + 1, a) for i, a in enumerate(mevzuat.AYLAR)])
        self.ay.currentIndexChanged.connect(self.yenile)
        ust.addWidget(self.ay)
        lay.addLayout(ust)
        self.tablo = VeriTablosu()
        self.tablo.satirCiftTiklandi.connect(lambda _s: self.duzenle())
        lay.addWidget(self.tablo)
        self.yenile()

    def yenile(self):
        donem = f"{Oturum.yil}" + (f"-{self.ay.deger():02d}" if self.ay.deger() else "")
        sql = """SELECT k.*, c.unvan, f.belge_no fatura_no, s.siparis_no,
                        CASE WHEN k.yon = 'Giriş' THEN k.tutar END giris, CASE WHEN k.yon = 'Çıkış' THEN k.tutar END cikis
                 FROM kasa_banka k LEFT JOIN cari c ON c.id = k.cari_id LEFT JOIN fatura f ON f.id = k.fatura_id
                 LEFT JOIN siparis s ON s.id = k.siparis_id WHERE k.tarih LIKE ?"""
        prm = [donem + "%"]
        if self.hesap.deger():
            sql += " AND k.hesap = ?"
            prm.append(self.hesap.deger())
        satirlar = db().q(sql + " ORDER BY k.tarih DESC, k.id DESC", prm)
        self.tablo.doldur(
            [Kolon("tarih", "Tarih", "tarih"), Kolon("hesap", "Hesap"), Kolon("tur", "İşlem türü"), Kolon("unvan", "Cari"),
             Kolon("fatura_no", "Belge"), Kolon("siparis_no", "Sipariş"), Kolon("belge_no", "Dekont/Makbuz"),
             Kolon("giris", "Giriş", "para"), Kolon("cikis", "Çıkış", "para"), Kolon("hasilat_tutari", "Hasılat (KDV hariç)", "para"),
             Kolon("aciklama", "Açıklama")],
            satirlar, lambda s: "#eef6ee" if s["yon"] == "Giriş" else None)
        self.k_kasa.ayarla(para(hesap_bakiyesi("Kasa (100)")) + " TL")
        self.k_banka.ayarla(para(hesap_bakiyesi("Banka (102)")) + " TL")
        self.k_giris.ayarla(para(sum(s["giris"] or 0 for s in satirlar)) + " TL",
                            f"Hasılat: {para(sum(s['hasilat_tutari'] or 0 for s in satirlar))} TL")
        self.k_cikis.ayarla(para(sum(s["cikis"] or 0 for s in satirlar)) + " TL")
        self.b_giris.setEnabled(Oturum.yazabilir(self))
        self.b_cikis.setEnabled(Oturum.yazabilir(self))

    def yeni(self, yon):
        if yetki_kontrol(self) and KasaDialog(self, on_deger={"yon": yon}).exec():
            self.yenile()

    def duzenle(self):
        s = self.tablo.secili()
        if not s:
            return
        if s["kaynak"]:
            uyari(self, f"Bu kayıt '{s['kaynak']}' modülünden oluşturuldu; ilgili sayfadan değiştiriniz.")
            return
        if KasaDialog(self, kayit_id=s["id"]).exec():
            self.yenile()

    def sil(self):
        s = self.tablo.secili()
        if not s or not yetki_kontrol(self):
            return
        if s["kaynak"] and not soru(self, f"Bu kayıt '{s['kaynak']}' modülüne bağlı. Yine de silinsin mi?"):
            return
        if soru(self, f"{para(s['tutar'])} TL tutarlı '{s['tur']}' kaydı silinsin mi?"):
            db().sil("kasa_banka", s["id"])
            muhasebe.fis_sil("KasaBanka", s["id"])
            self.yenile()


class KasaDialog(QDialog):
    def __init__(self, parent, kayit_id: int | None = None, on_deger: dict | None = None):
        super().__init__(parent)
        kayit_izle(self, "kasa_banka", kayit_id)
        self.kid = kayit_id
        k = db().q1("SELECT * FROM kasa_banka WHERE id = ?", (kayit_id,)) if kayit_id else dict(on_deger or {})
        self.setWindowTitle("Kasa / banka hareketi")
        self.resize(620, 520)
        f = QFormLayout(self)
        self.tarih = TarihKutusu()
        self.hesap_k = SecimKutusu(secenekler=mevzuat.KASA_HESAPLARI)
        self.yon = SecimKutusu(secenekler=["Giriş", "Çıkış"])
        self.tur = SecimKutusu()
        self.cari = SecimKutusu(secenekler=fk_secenekleri("cari", "unvan", "aktif = 1"), bos=True)
        self.fatura = SecimKutusu(bos=True)
        self.siparis = SecimKutusu(secenekler=fk_secenekleri("siparis", "siparis_no || ' - ' || COALESCE(konu, '')", "", "id DESC"), bos=True)
        self.tutar = ParaKutusu()
        self.hasilat = ParaKutusu()
        self.belge = QLineEdit()
        self.aciklama = QLineEdit()
        self.bilgi = QLabel()
        self.bilgi.setWordWrap(True)
        f.addRow("Tarih:", self.tarih)
        f.addRow("Hesap:", self.hesap_k)
        f.addRow("Yön:", self.yon)
        f.addRow("İşlem türü:", self.tur)
        f.addRow("Cari:", self.cari)
        f.addRow("Fatura / belge:", self.fatura)
        f.addRow("Sipariş:", self.siparis)
        f.addRow("Tutar *:", self.tutar)
        f.addRow("Hasılat tutarı (KDV hariç):", self.hasilat)
        f.addRow("Dekont / makbuz no:", self.belge)
        f.addRow("Açıklama:", self.aciklama)
        f.addRow(self.bilgi)
        bb = QHBoxLayout()
        bb.addStretch()
        bb.addWidget(buton("Kaydet", self.kaydet, "birincil"))
        bb.addWidget(buton("Vazgeç", self.reject))
        f.addRow(bb)

        self.tarih.ayarla(k.get("tarih"))
        self.hesap_k.ayarla(k.get("hesap") or "Banka (102)")
        self.yon.ayarla(k.get("yon") or "Giriş")
        self._turleri_doldur()
        self.tur.ayarla(k.get("tur"))
        self.cari.ayarla(k.get("cari_id"))
        self._faturalari_doldur()
        self.fatura.ayarla(k.get("fatura_id"))
        self.siparis.ayarla(k.get("siparis_id"))
        self.tutar.ayarla(k.get("tutar"))
        self.belge.setText(k.get("belge_no") or "")
        self.aciklama.setText(k.get("aciklama") or "")
        self._kaynak = (k.get("kaynak"), k.get("kaynak_id"))
        if kayit_id:
            self.hasilat.ayarla(k.get("hasilat_tutari"))
        else:
            self.hasilat_hesapla()

        self.yon.currentIndexChanged.connect(self._yon_degisti)
        self.tur.currentIndexChanged.connect(self._tur_degisti)
        self.cari.currentIndexChanged.connect(self._faturalari_doldur)
        self.fatura.currentIndexChanged.connect(self._fatura_degisti)
        self.siparis.currentIndexChanged.connect(self.hasilat_hesapla)
        self.tutar.valueChanged.connect(self.hasilat_hesapla)
        self.hesap_k.currentIndexChanged.connect(self.bilgi_guncelle)
        self.bilgi_guncelle()

    def _turleri_doldur(self):
        self.tur.doldur(GIRIS_TURLERI if self.yon.deger() == "Giriş" else CIKIS_TURLERI)

    def _yon_degisti(self):
        self._turleri_doldur()
        self._faturalari_doldur()
        self.hasilat_hesapla()

    def _tur_degisti(self):
        self._faturalari_doldur()
        self.hasilat_hesapla()

    def _faturalari_doldur(self):
        tur = {"Tahsilat": "Satış", "Ödeme": "Alış"}.get(self.tur.deger())
        if not tur:
            self.fatura.doldur([])
            return
        kosul = "f.iptal = 0 AND f.tur = ?"
        prm = [tur]
        if self.cari.deger():
            kosul += " AND f.cari_id = ?"
            prm.append(self.cari.deger())
        satirlar = db().q(f"""SELECT f.id, f.belge_no, f.tarih, f.net_tutar - COALESCE(f.avans_mahsup, 0)
                                     - COALESCE((SELECT SUM(tutar) FROM kasa_banka k WHERE k.fatura_id = f.id AND k.id != ?), 0) kalan
                              FROM fatura f WHERE {kosul} ORDER BY f.tarih DESC""", [self.kid or 0] + prm)
        self.fatura.doldur([(s["id"], f"{s['belge_no'] or '-'} ({s['tarih']}) kalan: {para(s['kalan'])}")
                            for s in satirlar if s["kalan"] > 0.009 or s["id"] == self.fatura.deger()])

    def _fatura_degisti(self):
        fid = self.fatura.deger()
        if fid:
            f = db().q1("SELECT cari_id, siparis_id, belge_no FROM fatura WHERE id = ?", (fid,))
            if not self.kid:
                kalan = db().deger("SELECT f.net_tutar - COALESCE(f.avans_mahsup, 0) - COALESCE((SELECT SUM(tutar) FROM kasa_banka k "
                                   "WHERE k.fatura_id = f.id), 0) FROM fatura f WHERE f.id = ?", (fid,), 0.0)
                self.tutar.ayarla(max(kalan, 0))
            if f["siparis_id"]:
                self.siparis.ayarla(f["siparis_id"])
            if not self.aciklama.text():
                self.aciklama.setText(f"{f['belge_no'] or ''} nolu belge")
        self.hasilat_hesapla()

    def hasilat_hesapla(self):
        tur, tutar = self.tur.deger(), self.tutar.deger()
        if self.yon.deger() != "Giriş" or tur not in mevzuat.HASILAT_ETKILI_TURLER:
            h = 0.0
        elif tur == "Tahsilat" and self.fatura.deger():
            f = db().q1("SELECT matrah, net_tutar FROM fatura WHERE id = ?", (self.fatura.deger(),))
            h = tutar * f["matrah"] / f["net_tutar"] if f and f["net_tutar"] else tutar
        elif tur == "Peşinat/Avans Tahsilatı" and self.siparis.deger():
            kdv = db().deger("SELECT kdv_orani FROM siparis WHERE id = ?", (self.siparis.deger(),), 0.0)
            h = tutar / (1 + kdv)
        elif tur == "Tahsilat":
            h = tutar / (1 + db().parametreler(Oturum.yil)["kdv_genel"])
        else:
            h = tutar
        self.hasilat.ayarla(yuvarla(h))
        self.bilgi_guncelle()

    def bilgi_guncelle(self):
        metin = []
        if self.yon.deger() == "Çıkış":
            bakiye = hesap_bakiyesi(self.hesap_k.deger(), haric_id=self.kid)
            metin.append(f"{self.hesap_k.deger()} güncel bakiyesi: {para(bakiye)} TL")
        if self.tur.deger() == "Tahsilat" and not self.fatura.deger():
            metin.append("Faturası seçilmeyen tahsilatta hasılat tutarı genel KDV oranıyla ayrıştırılır; gerekirse düzeltiniz.")
        if self.tur.deger() in mevzuat.HASILAT_ETKILI_TURLER and self.yon.deger() == "Giriş":
            metin.append("Hasılat tutarı aylık hazine payı (%1) matrahına girer (Tebliğ 73).")
        self.bilgi.setText("\n".join(metin))

    def kaydet(self):
        if not yetki_kontrol(self):
            return
        tutar = self.tutar.deger()
        if tutar <= 0:
            uyari(self, "Tutar sıfırdan büyük olmalıdır.")
            return
        fid = self.fatura.deger()
        if fid:
            kalan = db().deger("SELECT f.net_tutar - COALESCE(f.avans_mahsup, 0) - COALESCE((SELECT SUM(tutar) FROM kasa_banka k "
                               "WHERE k.fatura_id = f.id AND k.id != ?), 0) FROM fatura f WHERE f.id = ?", (self.kid or 0, fid), 0.0)
            if tutar > kalan + 0.009:
                uyari(self, f"Tutar, belgenin açık bakiyesini ({para(kalan)} TL) aşıyor.")
                return
        if self.yon.deger() == "Çıkış":
            bakiye = hesap_bakiyesi(self.hesap_k.deger(), haric_id=self.kid)
            if tutar > bakiye + 0.009 and not soru(self, f"Hesap bakiyesi ({para(bakiye)} TL) yetersiz görünüyor. Yine de kaydedilsin mi?"):
                return
        if self.tur.deger() in ("Tahsilat", "Ödeme") and not self.cari.deger():
            uyari(self, "Tahsilat/ödeme için cari seçiniz.")
            return
        v = {"tarih": self.tarih.deger(), "hesap": self.hesap_k.deger(), "yon": self.yon.deger(), "tur": self.tur.deger(),
             "tutar": tutar, "hasilat_tutari": self.hasilat.deger(), "cari_id": self.cari.deger(), "fatura_id": fid,
             "siparis_id": self.siparis.deger(), "belge_no": self.belge.text().strip() or None,
             "aciklama": self.aciklama.text().strip() or None, "kaynak": self._kaynak[0], "kaynak_id": self._kaynak[1]}
        if self.kid:
            db().guncelle("kasa_banka", self.kid, v)
        else:
            self.kid = db().ekle("kasa_banka", v)
        muhasebe.kasa_kaydi(self.kid)
        self.accept()
