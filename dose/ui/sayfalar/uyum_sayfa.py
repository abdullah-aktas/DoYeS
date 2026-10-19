"""Mevzuat uyum denetimi: bütün kayıtların taranması, uyum puanı ve 'ne yapmalıyım?' açıklamaları."""
from html import escape

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSplitter, QTextBrowser, QVBoxLayout, QWidget
from PySide6.QtCore import Qt

from ... import belgeler, kilavuz, uyum
from ..ortak import (Kart, Kolon, Oturum, SecimKutusu, VeriTablosu, baslik_etiketi, bilgi, buton, cikti_yolu, dosya_ac,
                     soru, tablo_excele)

RENK = {uyum.HATA: "#fdecea", uyum.UYARI: "#fff4e5", uyum.BILGI: None}
IKON = {uyum.HATA: "⛔", uyum.UYARI: "⚠", uyum.BILGI: "ℹ"}


def bulgu_html(b: uyum.Bulgu) -> str:
    renk = {uyum.HATA: "#b00020", uyum.UYARI: "#8a5a00", uyum.BILGI: "#1f4e79"}[b.seviye]
    p = [f"<h3 style='color:{renk}; margin:2px 0'>{IKON[b.seviye]} {escape(b.baslik)}</h3>"]
    if b.aciklama:
        p.append(f"<p><b>Sorun nedir?</b><br>{escape(b.aciklama)}</p>")
    if b.cozum:
        p.append(f"<p style='background:#e8f5e9; padding:4px'><b>✅ Ne yapmalısınız?</b><br>{escape(b.cozum)}</p>")
    p.append(f"<p><b>Kim yapar?</b> {escape(', '.join(b.sorumlular))}</p>")
    if b.dayanak:
        p.append(f"<p style='color:#555'><b>Dayanak:</b> {escape(b.dayanak)}</p>")
    if b.rehber and b.rehber in kilavuz.REHBER:
        r = kilavuz.REHBER[b.rehber]
        p.append(f"<p style='color:#555'>Adım adım anlatım: <b>{r.ikon} {escape(r.baslik)}</b> "
                 "('Nasıl yapılır?' düğmesi)</p>")
    return "".join(p)


def bulgu_ac(sayfa_widget, b: uyum.Bulgu | None, rehber=False):
    """Bulgunun sayfasını veya adım adım rehberini ana pencerede açar."""
    ana = getattr(sayfa_widget, "ana_pencere", None)
    if not b or ana is None:
        return
    if rehber and b.rehber:
        ana.rehber_ac(b.rehber)
    elif b.sayfa:
        if not Oturum.sayfa_yetkisi(b.sayfa):
            bilgi(sayfa_widget, f"'{b.sayfa}' sayfasına erişim yetkiniz yok. Bu işi şunlar yapar: {', '.join(b.sorumlular)}.")
            return
        ana.sayfaya_git(b.sayfa)


class UyumSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        self.bulgular: list[uyum.Bulgu] = []
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "Mevzuat Uyum Denetimi",
            "Program bütün kayıtları bir denetçi gözüyle tarar: süresi geçen işler, mevzuata aykırı veya eksik kayıtlar ve "
            "ceza / kamu zararı riski taşıyan durumlar. Bir bulguyu seçince ne yapmanız gerektiği altta yazar."))
        izgara = QGridLayout()
        self.k_puan = Kart("Uyum puanı")
        self.k_hata = Kart("⛔ Acil / riskli")
        self.k_uyari = Kart("⚠ Dikkat edilecek")
        self.k_bilgi = Kart("ℹ Bilgi")
        for i, k in enumerate((self.k_puan, self.k_hata, self.k_uyari, self.k_bilgi)):
            izgara.addWidget(k, 0, i)
        lay.addLayout(izgara)

        ust = QHBoxLayout()
        ust.addWidget(buton("🔍 Denetimi çalıştır", self.yenile, "birincil"))
        ust.addWidget(buton("İlgili sayfaya git", lambda: bulgu_ac(self, self._secili())))
        ust.addWidget(buton("Nasıl yapılır? (adım adım)", lambda: bulgu_ac(self, self._secili(), rehber=True)))
        ust.addWidget(buton("Denetim raporu (PDF)", self.pdf))
        ust.addWidget(buton("Excel'e Aktar", lambda: tablo_excele(self, self.tablo, f"Uyum_Denetimi_{Oturum.yil}")))
        ust.addStretch()
        ust.addWidget(QLabel("Göster:"))
        self.suzgec = SecimKutusu(secenekler=[("hepsi", "Tümü"), (uyum.HATA, "Yalnız acil / riskli"),
                                              (uyum.UYARI, "Yalnız dikkat edilecek"), ("benim", "Yalnız benim yapacaklarım")])
        self.suzgec.currentIndexChanged.connect(self._doldur)
        ust.addWidget(self.suzgec)
        lay.addLayout(ust)

        bol = QSplitter(Qt.Vertical)
        self.tablo = VeriTablosu()
        self.tablo.itemSelectionChanged.connect(self._ayrinti)
        self.tablo.satirCiftTiklandi.connect(lambda _s: bulgu_ac(self, self._secili()))
        self.ayrinti = QTextBrowser()
        bol.addWidget(self.tablo)
        bol.addWidget(self.ayrinti)
        bol.setSizes([420, 220])
        lay.addWidget(bol)
        self.durum = QLabel()
        self.durum.setWordWrap(True)
        lay.addWidget(self.durum)
        self.yenile()

    def yenile(self):
        self.bulgular = uyum.denetle(Oturum.yil, Oturum.bolum_id())
        p = uyum.puan(self.bulgular)
        metin, renk = uyum.puan_durumu(p)
        self.k_puan.ayarla(f"{p} / 100", metin)
        self.k_puan.d.setStyleSheet(f"color:{renk}")
        sayi = {s: sum(1 for b in self.bulgular if b.seviye == s) for s in (uyum.HATA, uyum.UYARI, uyum.BILGI)}
        self.k_hata.ayarla(str(sayi[uyum.HATA]), "Ceza veya kamu zararı riski: hemen düzeltin")
        self.k_uyari.ayarla(str(sayi[uyum.UYARI]), "Eksik veya gecikmiş işler")
        self.k_bilgi.ayarla(str(sayi[uyum.BILGI]), "Hatırlatmalar")
        kapsam = " (yalnız kendi bölümünüz)" if Oturum.bolum_id() else ""
        self.durum.setText(f"{Oturum.yil} yılı{kapsam} için denetim yapıldı. {kilavuz.GENEL_UYARI}")
        self._doldur()

    def _gorunen(self) -> list[uyum.Bulgu]:
        s = self.suzgec.deger()
        if s == "benim":
            return [b for b in self.bulgular if uyum.ilgili_mi(b, Oturum.rol())]
        if s in (uyum.HATA, uyum.UYARI):
            return [b for b in self.bulgular if b.seviye == s]
        return self.bulgular

    def _doldur(self):
        self._liste = self._gorunen()
        satirlar = [{"id": i, "seviye": f"{IKON[b.seviye]} {uyum.SEVIYE_ADI[b.seviye]}", "konu": b.konu, "baslik": b.baslik,
                     "kim": ", ".join(b.sorumlular), "_s": b.seviye} for i, b in enumerate(self._liste)]
        self.tablo.doldur([Kolon("seviye", "Durum", genislik=120), Kolon("konu", "Konu", genislik=140),
                           Kolon("baslik", "Bulgu", genislik=520), Kolon("kim", "Kim yapar")],
                          satirlar, lambda s: RENK[s["_s"]])
        if not satirlar:
            self.ayrinti.setHtml("<h3 style='color:#1b5e20'>✔ Bu görünümde bulgu yok.</h3>"
                                 "<p>Kayıtlarınız denetlenen kurallara uygun görünüyor. Yine de belgelerin asıllarının dosyada "
                                 "imzalı olarak bulunduğundan emin olun.</p>")
        else:
            self.tablo.selectRow(0)

    def _secili(self) -> uyum.Bulgu | None:
        s = self.tablo.secili()
        return self._liste[s["id"]] if s and s["id"] < len(self._liste) else None

    def _ayrinti(self):
        b = self._secili()
        if b:
            self.ayrinti.setHtml(bulgu_html(b))

    def pdf(self):
        if not self.bulgular:
            bilgi(self, "Raporlanacak bulgu yok.")
            return
        p = uyum.puan(self.bulgular)
        satirlar = [[uyum.SEVIYE_ADI[b.seviye], escape(b.konu), escape(b.baslik), escape(b.aciklama), escape(b.cozum),
                     escape(", ".join(b.sorumlular)), escape(b.dayanak)] for b in self.bulgular]
        yol = belgeler.genel_liste(cikti_yolu(f"Uyum_Denetimi_{Oturum.yil}"), f"{Oturum.yil} Yılı Mevzuat Uyum Denetimi Raporu",
                                   ["Durum", "Konu", "Bulgu", "Açıklama", "Ne yapılmalı", "Sorumlu", "Dayanak"], satirlar,
                                   alt_metin=f"Uyum puanı: {p}/100 ({uyum.puan_durumu(p)[0]}). {kilavuz.GENEL_UYARI}")
        if soru(self, f"Rapor oluşturuldu:\n{yol}\n\nŞimdi açılsın mı?"):
            dosya_ac(yol)
