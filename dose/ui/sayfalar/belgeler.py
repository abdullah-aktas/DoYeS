"""Resmi yazılar (şablonlu) ve toplu belge çıktıları."""
from PySide6.QtWidgets import QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from ... import belgeler as bg
from ...belge_sablonlari import SABLONLAR
from ..ortak import (Alan, FormDialog, Kolon, Oturum, SecimKutusu, VeriTablosu, baslik_etiketi, bugun, buton, cikti_yolu,
                     db, dosya_ac, soru, uyari, yetki_kontrol)

def yazi_alanlari():
    return [Alan("tarih", "Tarih", "tarih", True), Alan("sayi", "Sayı"), Alan("konu", "Konu", zorunlu=True),
            Alan("muhatap", "Muhatap (MAKAMINA / MÜDÜRLÜĞÜNE)"), Alan("ilgi", "İlgi", "cokmetin"),
            Alan("metin", "Metin (paragrafları boş satırla ayırın)", "cokmetin", True),
            Alan("imza1", "1. imza (Ad Soyad ⏎ Unvan)", "cokmetin"), Alan("imza2", "2. imza (Ad Soyad ⏎ Unvan)", "cokmetin")]


class BelgeSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "Resmi Yazılar ve Belgeler",
            "Hazır şablonlarla resmi yazı hazırlama ve toplu belge çıktıları. Sipariş belgeleri (teklif, sözleşme, görevlendirme, muayene "
            "kabul) Siparişler sayfasından; bordrolar ilgili ödeme sayfalarından alınır. Resmi yazılar DYS/DETSİS üzerinden de "
            "kayda alınmalıdır."))
        self.sekme = QTabWidget()
        lay.addWidget(self.sekme)

        w = QWidget()
        v = QVBoxLayout(w)
        u = QHBoxLayout()
        u.addWidget(QLabel("Şablon:"))
        self.sablon = SecimKutusu(secenekler=list(SABLONLAR.keys()))
        self.sablon.setMinimumWidth(320)
        u.addWidget(self.sablon)
        self.b_yeni = buton("＋ Yeni yazı", self.yeni, "birincil")
        u.addWidget(self.b_yeni)
        u.addWidget(buton("Düzenle", self.duzenle))
        u.addWidget(buton("PDF", self.pdf))
        u.addWidget(buton("Sil", self.sil, "tehlike"))
        u.addStretch()
        v.addLayout(u)
        self.t_yazi = VeriTablosu()
        self.t_yazi.satirCiftTiklandi.connect(lambda _s: self.pdf())
        v.addWidget(self.t_yazi)
        self.sekme.addTab(w, "Resmi yazılar")

        w2 = QWidget()
        v2 = QVBoxLayout(w2)
        u2 = QHBoxLayout()
        u2.addWidget(buton("Veli muvafakatnamesi (seçili öğrenciler)", self.muvafakat, "birincil"))
        u2.addWidget(buton("Muvafakati eksik öğrencileri seç", self.eksikleri_sec))
        u2.addWidget(buton("Öğrenci listesi PDF", self.ogrenci_listesi))
        u2.addWidget(buton("Personel listesi PDF", self.personel_listesi))
        u2.addStretch()
        v2.addLayout(u2)
        self.t_ogr = VeriTablosu()
        v2.addWidget(self.t_ogr)
        self.sekme.addTab(w2, "Öğrenci / personel belgeleri")
        self.yenile()

    def yenile(self):
        self.t_yazi.doldur([Kolon("tarih", "Tarih", "tarih"), Kolon("sayi", "Sayı"), Kolon("konu", "Konu"), Kolon("muhatap", "Muhatap")],
                           db().q("SELECT * FROM resmi_yazi ORDER BY tarih DESC, id DESC"))
        self.t_ogr.doldur([Kolon("okul_no", "Okul no"), Kolon("ad_soyad", "Adı soyadı"), Kolon("sinif", "Sınıf"), Kolon("bolum", "Bölüm"),
                           Kolon("veli_adi", "Veli"), Kolon("veli_muvafakat", "Muvafakat", "bool"),
                           Kolon("muvafakat_tarihi", "Muvafakat tarihi", "tarih")],
                          db().q("SELECT o.*, b.ad bolum FROM ogrenci o LEFT JOIN bolum b ON b.id = o.bolum_id WHERE o.aktif = 1 "
                                 "ORDER BY o.sinif, o.ad_soyad"),
                          lambda s: None if s["veli_muvafakat"] else "#fde2e2")
        self.b_yeni.setEnabled(Oturum.yazabilir(self))

    def _varsayilan_imzalar(self):
        k = db().kurum()
        return (f"{k.get('gerceklestirme_gorevlisi') or ''}\nMüdür Yardımcısı",
                f"{k.get('harcama_yetkilisi') or ''}\nOkul Müdürü")

    def yeni(self):
        if not yetki_kontrol(self):
            return
        konu, muhatap, metin = SABLONLAR[self.sablon.deger()]
        yil = Oturum.yil
        imza1, imza2 = self._varsayilan_imzalar()
        kayit = {"tarih": bugun(), "sayi": db().kurum().get("evrak_kodu") or "", "konu": konu, "muhatap": muhatap,
                 "metin": metin.format(yil=yil, ay="........"), "imza1": imza1, "imza2": imza2}
        d = FormDialog(self, "Yeni resmi yazı", yazi_alanlari(), kayit)
        if d.exec():
            v = d.degerler()
            yid = db().ekle("resmi_yazi", v)
            self.yenile()
            if soru(self, "Yazının PDF çıktısı oluşturulsun mu?"):
                dosya_ac(bg.resmi_yazi(cikti_yolu(f"Yazi_{v['konu']}"), dict(v, id=yid)))

    def duzenle(self):
        s = self.t_yazi.secili()
        if not s or not yetki_kontrol(self):
            return
        kayit = db().q1("SELECT * FROM resmi_yazi WHERE id = ?", (s["id"],))
        d = FormDialog(self, "Resmi yazı düzenle", yazi_alanlari(), kayit)
        if d.exec():
            db().guncelle("resmi_yazi", s["id"], d.degerler())
            self.yenile()

    def pdf(self):
        s = self.t_yazi.secili()
        if s:
            yazi = db().q1("SELECT * FROM resmi_yazi WHERE id = ?", (s["id"],))
            dosya_ac(bg.resmi_yazi(cikti_yolu(f"Yazi_{yazi['konu'] or ''}"), yazi))

    def sil(self):
        s = self.t_yazi.secili()
        if s and yetki_kontrol(self) and soru(self, f"'{s['konu']}' yazısı silinsin mi?"):
            db().sil("resmi_yazi", s["id"])
            self.yenile()

    def eksikleri_sec(self):
        self.t_ogr.clearSelection()
        from PySide6.QtWidgets import QAbstractItemView
        mod = self.t_ogr.selectionMode()
        self.t_ogr.setSelectionMode(QAbstractItemView.MultiSelection)
        for r in range(self.t_ogr.rowCount()):
            if not self.t_ogr.satir_verisi(r)["veli_muvafakat"]:
                self.t_ogr.selectRow(r)
        self.t_ogr.setSelectionMode(mod)

    def muvafakat(self):
        secili = self.t_ogr.secililer()
        if not secili:
            uyari(self, "Listeden öğrenci seçiniz (Ctrl/Shift ile çoklu seçim).")
            return
        dosya_ac(bg.veli_muvafakatnamesi(cikti_yolu("Veli_Muvafakatnamesi"), [s["id"] for s in secili]))

    def ogrenci_listesi(self):
        satir = [[s["okul_no"] or "", s["ad_soyad"], s["sinif"] or "", s["bolum"] or "", s["veli_adi"] or "",
                  "Var" if s["veli_muvafakat"] else "YOK"] for s in self.t_ogr.satirlar]
        dosya_ac(bg.genel_liste(cikti_yolu("Ogrenci_Listesi"), "DÖNER SERMAYE ÇALIŞMALARINA KATILAN ÖĞRENCİ LİSTESİ",
                                ["Okul no", "Adı soyadı", "Sınıf", "Bölüm", "Veli", "Muvafakat"], satir, yatay=False))

    def personel_listesi(self):
        rows = db().q("""SELECT p.*, b.ad bolum FROM personel p LEFT JOIN bolum b ON b.id = p.bolum_id WHERE p.aktif = 1
                         ORDER BY p.dose_gorevi, p.ad_soyad""")
        satir = [[r["ad_soyad"], r["kadro_unvani"] or "", r["dose_gorevi"] or "", r["hizmet_sinifi"] or "", r["bolum"] or "",
                  r["unvan_grubu"] or ""] for r in rows]
        dosya_ac(bg.genel_liste(cikti_yolu("Personel_Listesi"), "DÖNER SERMAYE İŞLETMESİ PERSONEL LİSTESİ",
                                ["Adı soyadı", "Kadro unvanı", "DÖSE görevi", "Hizmet sınıfı", "Bölüm", "Unvan grubu"], satir))
