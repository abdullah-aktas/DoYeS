"""Stok (ambar) takibi: malzeme bakiyeleri, giriş/çıkış hareketleri."""
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QTabWidget, QVBoxLayout, QWidget

from ... import muhasebe
from ...hesap import para, yuvarla
from ..ortak import (Kolon, Oturum, ParaKutusu, SecimKutusu, TarihKutusu, VeriTablosu, baslik_etiketi, buton, db,
                     fk_secenekleri, soru, tablo_excele, uyari, yetki_kontrol)

GIRIS_NEDENLERI = ["Devir / Açılış", "Üretimden Mamul Girişi", "Sayım Fazlası", "Bağış / Hibe", "İade (Üretimden)", "Diğer"]
CIKIS_NEDENLERI = ["Üretime Sevk", "Sayım Noksanı / Fire", "Bozulma / Hurda", "Diğer"]


class StokSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "Stok / Ambar",
            "Stoklu alış belgeleri otomatik giriş, mamul satışları otomatik çıkış yapar. Üretime sevkler ağırlıklı ortalama maliyetle "
            "çıkılır ve siparişe bağlanabilir. Taşınır kayıtları için resmi defterler ayrıca tutulmalıdır."))
        ust = QHBoxLayout()
        self.b_giris = buton("＋ Stok girişi", lambda: self.hareket("Giriş"), "birincil")
        self.b_cikis = buton("－ Stok çıkışı", lambda: self.hareket("Çıkış"))
        ust.addWidget(self.b_giris)
        ust.addWidget(self.b_cikis)
        ust.addWidget(buton("Hareketi sil", self.sil, "tehlike"))
        ust.addWidget(buton("Excel'e Aktar", self.excel))
        ust.addStretch()
        lay.addLayout(ust)
        self.sekme = QTabWidget()
        self.t_bakiye = VeriTablosu()
        self.t_hareket = VeriTablosu()
        self.sekme.addTab(self.t_bakiye, "Stok bakiyeleri")
        self.sekme.addTab(self.t_hareket, "Hareketler")
        lay.addWidget(self.sekme)
        self.ozet = QLabel()
        lay.addWidget(self.ozet)
        self.yenile()

    def yenile(self):
        bak = db().q("""SELECT m.id, m.kod, m.ad, m.tur, m.birim, m.kritik_stok,
                               COALESCE(SUM(CASE WHEN h.yon = 'Giriş' THEN h.miktar END), 0) giris,
                               COALESCE(SUM(CASE WHEN h.yon = 'Çıkış' THEN h.miktar END), 0) cikis
                        FROM malzeme m LEFT JOIN stok_hareket h ON h.malzeme_id = m.id
                        WHERE m.aktif = 1 GROUP BY m.id ORDER BY m.ad""")
        for b in bak:
            b["kalan"] = yuvarla(b["giris"] - b["cikis"], 3)
            b["ort"] = muhasebe.ortalama_maliyet(b["id"])
            b["tutar"] = yuvarla(b["kalan"] * b["ort"])
        self.t_bakiye.doldur(
            [Kolon("kod", "Kod"), Kolon("ad", "Malzeme"), Kolon("tur", "Tür"), Kolon("birim", "Birim"),
             Kolon("giris", "Giriş", "sayi"), Kolon("cikis", "Çıkış", "sayi"), Kolon("kalan", "Kalan", "sayi"),
             Kolon("kritik_stok", "Kritik seviye", "sayi"), Kolon("ort", "Ort. maliyet", "para"), Kolon("tutar", "Stok değeri", "para")],
            bak, lambda b: "#fde2e2" if b["kalan"] < 0 else ("#fff4d6" if b["kritik_stok"] and b["kalan"] <= b["kritik_stok"] else None))
        har = db().q("""SELECT h.*, m.ad malzeme, m.birim, s.siparis_no, h.miktar * h.birim_fiyat tutar
                        FROM stok_hareket h JOIN malzeme m ON m.id = h.malzeme_id LEFT JOIN siparis s ON s.id = h.siparis_id
                        WHERE substr(h.tarih, 1, 4) = ? ORDER BY h.tarih DESC, h.id DESC""", (str(Oturum.yil),))
        self.t_hareket.doldur(
            [Kolon("tarih", "Tarih", "tarih"), Kolon("malzeme", "Malzeme"), Kolon("yon", "Yön"), Kolon("miktar", "Miktar", "sayi"),
             Kolon("birim", "Birim"), Kolon("birim_fiyat", "Birim fiyat", "para"), Kolon("tutar", "Tutar", "para"),
             Kolon("kaynak", "Kaynak"), Kolon("siparis_no", "Sipariş"), Kolon("aciklama", "Açıklama")],
            har, lambda h: "#eef6ee" if h["yon"] == "Giriş" else None)
        self.ozet.setText(f"Toplam stok değeri: {para(sum(b['tutar'] for b in bak))} TL • "
                          f"Kritik seviyede: {sum(1 for b in bak if b['kritik_stok'] and b['kalan'] <= b['kritik_stok'])} kalem")
        self.b_giris.setEnabled(Oturum.yazabilir(self))
        self.b_cikis.setEnabled(Oturum.yazabilir(self))

    def hareket(self, yon):
        if yetki_kontrol(self) and StokHareketDialog(self, yon).exec():
            self.yenile()

    def sil(self):
        if not yetki_kontrol(self):
            return
        self.sekme.setCurrentIndex(1)
        h = self.t_hareket.secili()
        if not h:
            uyari(self, "Hareketler sekmesinden bir kayıt seçiniz.")
            return
        if h["kaynak"] == "Fatura":
            uyari(self, "Faturadan oluşan hareket ancak ilgili belge düzenlenerek veya iptal edilerek değiştirilebilir.")
            return
        if soru(self, "Seçili stok hareketi silinsin mi?"):
            db().sil("stok_hareket", h["id"])
            muhasebe.fis_sil("Stok", h["id"])
            self.yenile()

    def excel(self):
        t = self.t_bakiye if self.sekme.currentIndex() == 0 else self.t_hareket
        tablo_excele(self, t, "Stok_bakiye" if t is self.t_bakiye else "Stok_hareket")


class StokHareketDialog(QDialog):
    def __init__(self, parent, yon: str, siparis_id: int | None = None):
        super().__init__(parent)
        self.yon = yon
        self.setWindowTitle(f"Stok {yon.lower()}i")
        self.resize(560, 360)
        f = QFormLayout(self)
        self.tarih = TarihKutusu()
        self.malzeme = SecimKutusu(secenekler=fk_secenekleri("malzeme", "ad || ' (' || COALESCE(birim, '') || ')'", "aktif = 1", "ad"), bos=True)
        self.miktar = ParaKutusu(ondalik=3)
        self.fiyat = ParaKutusu(ondalik=4)
        self.neden = SecimKutusu(secenekler=GIRIS_NEDENLERI if yon == "Giriş" else CIKIS_NEDENLERI)
        self.siparis = SecimKutusu(secenekler=fk_secenekleri("siparis", "siparis_no || ' - ' || COALESCE(konu, '')",
                                                             "durum NOT IN ('İptal', 'Kapandı')", "id DESC"), bos=True)
        self.siparis.ayarla(siparis_id)
        self.aciklama = QLineEdit()
        self.bilgi = QLabel()
        self.bilgi.setWordWrap(True)
        f.addRow("Tarih:", self.tarih)
        f.addRow("Malzeme *:", self.malzeme)
        f.addRow("Neden:", self.neden)
        f.addRow("Miktar *:", self.miktar)
        f.addRow("Birim fiyat (KDV hariç):", self.fiyat)
        f.addRow("Sipariş:", self.siparis)
        f.addRow("Açıklama:", self.aciklama)
        f.addRow(self.bilgi)
        if yon == "Çıkış":
            self.fiyat.setReadOnly(True)
            self.fiyat.setToolTip("Çıkışlar ağırlıklı ortalama maliyetle yapılır.")
        self.malzeme.currentIndexChanged.connect(self.guncelle)
        self.tarih.dateChanged.connect(self.guncelle)
        bb = QHBoxLayout()
        bb.addStretch()
        bb.addWidget(buton("Kaydet", self.kaydet, "birincil"))
        bb.addWidget(buton("Vazgeç", self.reject))
        f.addRow(bb)
        self.guncelle()

    def guncelle(self):
        mid = self.malzeme.deger()
        if not mid:
            self.bilgi.setText("")
            return
        kalan = muhasebe.stok_miktari(mid)
        ort = muhasebe.ortalama_maliyet(mid, self.tarih.deger())
        if self.yon == "Çıkış":
            self.fiyat.ayarla(ort)
        self.bilgi.setText(f"Mevcut stok: {kalan:g} • Ağırlıklı ortalama maliyet: {para(ort)} TL"
                           + ("\nÇıkış, yardımcı defterde 710/740 borç – 150/151/152/153 alacak olarak kaydedilir."
                              if self.yon == "Çıkış" else "\nElle girişler yevmiyeye kaydedilmez (alış belgesinden gelen girişler kaydedilir)."))

    def kaydet(self):
        mid = self.malzeme.deger()
        if not mid or self.miktar.deger() <= 0:
            uyari(self, "Malzeme ve miktar zorunludur.")
            return
        if self.yon == "Çıkış":
            kalan = muhasebe.stok_miktari(mid)
            if self.miktar.deger() > kalan + 1e-9:
                uyari(self, f"Yetersiz stok. Mevcut: {kalan:g}")
                return
        elif self.fiyat.deger() <= 0 and not soru(self, "Birim fiyat sıfır. Yine de kaydedilsin mi?"):
            return
        aciklama = self.neden.deger() + (f" - {self.aciklama.text().strip()}" if self.aciklama.text().strip() else "")
        hid = db().ekle("stok_hareket", {"tarih": self.tarih.deger(), "malzeme_id": mid, "yon": self.yon,
                                         "miktar": self.miktar.deger(), "birim_fiyat": self.fiyat.deger(), "kaynak": "Manuel",
                                         "siparis_id": self.siparis.deger(), "aciklama": aciklama})
        if self.yon == "Çıkış":
            muhasebe.stok_cikis_kaydi(hid)
        self.accept()
