"""Kullanıcıya özel başlangıç sayfası: rolüne göre acil işler, onay bekleyenler, yaklaşan yasal süreler ve görev özeti."""
from datetime import date
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QGridLayout, QGroupBox, QHBoxLayout, QPushButton, QSplitter, QTextBrowser, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ... import kilavuz, onay, uyum
from ..ortak import Kart, Oturum, baslik_etiketi, buton
from .uyum_sayfa import bulgu_ac, bulgu_html

RENK = {uyum.HATA: "#b00020", uyum.UYARI: "#8a5a00", uyum.BILGI: "#1f4e79"}
SURE_GUN = 40


def sure_bulgusu(s: kilavuz.Sure, bugun: date) -> uyum.Bulgu:
    kalan = (s.tarih - bugun).days
    seviye = uyum.HATA if kalan <= 3 else uyum.UYARI if kalan <= 10 else uyum.BILGI
    ne_zaman = "bugün son gün" if kalan == 0 else f"{kalan} gün kaldı"
    return uyum.Bulgu(seviye, "Yasal süre", f"{s.ad} — son gün {s.tarih:%d.%m.%Y} ({ne_zaman})", s.aciklama,
                      uyum.SAYFA_COZUMU.get(s.sayfa or "", "Saymanınızla birlikte işi son günden önce tamamlayın.") +
                      " Son gün hafta sonuna veya tatile denk gelse bile işi önceki iş gününde bitirin.",
                      "", s.sayfa, s.rehber)


class YapilacaklarSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        k = Oturum.kullanici
        rol = Oturum.rol()
        bilgi_ = kilavuz.ROL_REHBERI.get(rol, {})
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "Bugün Ne Yapmalıyım?",
            f"Hoş geldiniz {k.get('ad_soyad') or k.get('kullanici_adi') or ''}. Rolünüz: {rol}"
            + (f" ({bilgi_['unvan']}). {bilgi_['ozet']}" if bilgi_ else ".")))

        izgara = QGridLayout()
        self.k_acil = Kart("⛔ Acil işler")
        self.k_dikkat = Kart("⚠ Dikkat edilecekler")
        self.k_onay = Kart("🔔 Onayınızı bekleyen")
        self.k_sure = Kart(f"📅 {SURE_GUN} gün içindeki son tarihler")
        for i, kart in enumerate((self.k_acil, self.k_dikkat, self.k_onay, self.k_sure)):
            izgara.addWidget(kart, 0, i)
        lay.addLayout(izgara)

        bol = QSplitter(Qt.Horizontal)
        sol = QWidget()
        sl = QVBoxLayout(sol)
        sl.setContentsMargins(0, 0, 0, 0)
        self.agac = QTreeWidget()
        self.agac.setHeaderLabels(["Yapılacak iş", "Kim yapar"])
        self.agac.setColumnWidth(0, 560)
        self.agac.setWordWrap(True)
        self.agac.currentItemChanged.connect(lambda *_: self._ayrinti())
        self.agac.itemDoubleClicked.connect(lambda *_: self._git())
        sl.addWidget(self.agac, 3)
        self.ayrinti = QTextBrowser()
        sl.addWidget(self.ayrinti, 2)
        dug = QHBoxLayout()
        dug.addWidget(buton("İlgili sayfaya git", self._git, "birincil"))
        dug.addWidget(buton("Nasıl yapılır? (adım adım)", lambda: self._git(rehber=True)))
        dug.addWidget(buton("Yenile", self.yenile))
        dug.addStretch()
        sl.addLayout(dug)
        bol.addWidget(sol)

        sag = QWidget()
        sg = QVBoxLayout(sag)
        sg.setContentsMargins(0, 0, 0, 0)
        kutu = QGroupBox("Ne yapmak istiyorsunuz?")
        kv = QVBoxLayout(kutu)
        for r in kilavuz.rol_rehberleri(rol)[:8]:
            b = QPushButton(f"{r.ikon}  {r.baslik}")
            b.setStyleSheet("text-align:left; padding:8px 10px; font-size:10.5pt;")
            b.setToolTip(r.ozet)
            b.clicked.connect(lambda _=False, kod=r.kod: self._rehber(kod))
            kv.addWidget(b)
        kv.addWidget(buton("Diğer işler…", lambda: self._rehber(None)))
        sg.addWidget(kutu)
        gorev = QGroupBox("Sizin göreviniz ve sorumluluğunuz")
        gv = QVBoxLayout(gorev)
        t = QTextBrowser()
        t.setHtml(self._gorev_html(bilgi_))
        gv.addWidget(t)
        sg.addWidget(gorev, 1)
        bol.addWidget(sag)
        bol.setSizes([820, 380])
        lay.addWidget(bol)
        self.yenile()

    @staticmethod
    def _gorev_html(b: dict) -> str:
        if not b:
            return ""
        return ("<b>Görevleriniz</b><ul>" + "".join(f"<li>{escape(g)}</li>" for g in b["gorevler"]) + "</ul>"
                "<b style='color:#b00020'>Dikkat etmeniz gerekenler</b><ul>"
                + "".join(f"<li>{escape(g)}</li>" for g in b["dikkat"]) + "</ul>"
                f"<p style='color:#777; font-size:9pt'><i>{escape(kilavuz.GENEL_UYARI)}</i></p>")

    def yenile(self):
        bugun = date.today()
        rol = Oturum.rol()
        yil = Oturum.yil
        bulgular = uyum.yapilacaklar(yil, rol, Oturum.bolum_id())
        sureler = [sure_bulgusu(s, bugun) for s in uyum.rol_sureleri(rol, bugun, SURE_GUN)] if yil == bugun.year else []
        try:
            n_onay = onay.bekleyen_sayisi(Oturum.kullanici) if onay.akis_acik() else 0
        except Exception:
            n_onay = 0
        acil = [b for b in bulgular if b.seviye == uyum.HATA]
        dikkat = [b for b in bulgular if b.seviye == uyum.UYARI]
        bilgiler = [b for b in bulgular if b.seviye == uyum.BILGI]
        self.k_acil.ayarla(str(len(acil)), "Ceza veya kamu zararı riski" if acil else "Acil iş yok")
        self.k_dikkat.ayarla(str(len(dikkat)))
        self.k_onay.ayarla(str(n_onay), "Onay Bekleyenler sayfasında" if n_onay else "")
        self.k_sure.ayarla(str(len(sureler)), next((b.baslik.split(" — ")[0] for b in sureler), ""))
        for kart, n, renk in ((self.k_acil, len(acil), "#b00020"), (self.k_onay, n_onay, "#8a5a00")):
            kart.d.setStyleSheet(f"color:{renk}" if n else "color:#1b5e20")

        self._kayitlar: list[uyum.Bulgu] = []
        self.agac.clear()
        if n_onay:
            self._grup("🔔 Onayınızı bekleyen belgeler", [uyum.Bulgu(
                uyum.UYARI, "Onay", f"{n_onay} belge kararınızı bekliyor",
                "Sipariş, bordro veya yıl sonu dağıtımı sizin aşamanızda bekliyor; siz karar vermeden süreç ilerlemez.",
                "Onay Bekleyenler sayfasında belgeyi inceleyin. Kırmızı uyarı yoksa onaylayın, varsa gerekçe yazarak iade edin.",
                sayfa="Onay Bekleyenler")], True)
        self._grup("⛔ Önce bunları yapın (acil)", acil, True)
        self._grup("📅 Yaklaşan yasal son tarihler", sureler, True)
        self._grup("⚠ Dikkat edilecekler", dikkat, len(acil) + len(sureler) < 6)
        self._grup("ℹ Bilgi ve hatırlatmalar", bilgiler, False)
        if not self._kayitlar:
            it = QTreeWidgetItem(["✔ Şu anda sizin yapmanız gereken acil bir iş görünmüyor.", ""])
            it.setForeground(0, QColor("#1b5e20"))
            self.agac.addTopLevelItem(it)
            self.ayrinti.setHtml("<h3 style='color:#1b5e20'>Her şey yolunda görünüyor.</h3><p>Yeni bir işe başlayacaksanız "
                                 "sağdaki 'Ne yapmak istiyorsunuz?' bölümünden ilgili rehberi açın.</p>")
        else:
            ilk = self.agac.topLevelItem(0)
            if ilk and ilk.childCount():
                self.agac.setCurrentItem(ilk.child(0))

    def _grup(self, baslik: str, bulgular: list[uyum.Bulgu], acik: bool):
        if not bulgular:
            return
        g = QTreeWidgetItem([f"{baslik}  ({len(bulgular)})", ""])
        f = QFont()
        f.setBold(True)
        g.setFont(0, f)
        self.agac.addTopLevelItem(g)
        for b in bulgular:
            it = QTreeWidgetItem([b.baslik, ", ".join(b.sorumlular)])
            it.setForeground(0, QColor(RENK[b.seviye]))
            it.setToolTip(0, b.cozum or b.aciklama)
            it.setData(0, Qt.UserRole, len(self._kayitlar))
            self._kayitlar.append(b)
            g.addChild(it)
        g.setExpanded(acik)

    def _secili(self) -> uyum.Bulgu | None:
        it = self.agac.currentItem()
        i = it.data(0, Qt.UserRole) if it else None
        return self._kayitlar[i] if i is not None and i < len(self._kayitlar) else None

    def _ayrinti(self):
        b = self._secili()
        if b:
            self.ayrinti.setHtml(bulgu_html(b))

    def _git(self, rehber=False):
        bulgu_ac(self, self._secili(), rehber)

    def _rehber(self, kod: str | None):
        ana = getattr(self, "ana_pencere", None)
        if ana is not None:
            ana.rehber_ac(kod)
