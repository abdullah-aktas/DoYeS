"""Mevzuat rehberi, yasal takvim, yılın parametre özeti, sözlük, sık yapılan hatalar ve görev dağılımı."""
from html import escape

from PySide6.QtWidgets import QTabWidget, QTextBrowser, QVBoxLayout, QWidget

from ... import kilavuz, mevzuat
from ...hesap import para
from ..ortak import Oturum, baslik_etiketi, db


def _sozluk_html() -> str:
    satir = "".join(f"<tr><td style='padding:4px 10px; white-space:nowrap'><b>{escape(t)}</b></td>"
                    f"<td style='padding:4px 10px'>{escape(a)}</td></tr>" for t, a in sorted(kilavuz.SOZLUK))
    return ("<h2>Terimler Sözlüğü</h2><p>Programda ve mevzuatta geçen kavramların günlük dille karşılıkları.</p>"
            f"<table border='1' cellspacing='0'>{satir}</table>")


def _ceza_html() -> str:
    satir = "".join(f"<tr><td style='padding:4px 8px'><b>{escape(h)}</b></td>"
                    f"<td style='padding:4px 8px; color:#8a1c12'>{escape(s)}</td>"
                    f"<td style='padding:4px 8px; color:#1b5e20'>{escape(o)}</td>"
                    f"<td style='padding:4px 8px; color:#555'>{escape(d)}</td></tr>" for h, s, o, d in kilavuz.CEZA_RISKLERI)
    return ("<h2>Sık Yapılan Hatalar ve Sonuçları</h2>"
            "<p>Denetimlerde en çok rastlanan aykırılıklar, bunların ceza veya kamu zararı sonuçları ve programın sizi nasıl "
            "koruduğu. Mevzuata aykırı ödemelerde <b>kamu zararı</b>, ödemeyi onaylayan ve yapan görevlilerden "
            "<b>kanuni faiziyle birlikte</b> geri istenir (5018 s.K. md.71); bu yüzden programdaki kırmızı uyarıları "
            "atlamayın.</p>"
            "<table border='1' cellspacing='0'><tr style='background:#e8edf3'><th>Hata</th><th>Sonucu</th>"
            f"<th>Program nasıl korur?</th><th>Dayanak</th></tr>{satir}</table>"
            f"<p><i>{escape(kilavuz.GENEL_UYARI)}</i></p>")


def _gorev_html() -> str:
    parca = ["<h2>Kim Ne Yapar?</h2><p>Döner sermayede görev ve sorumlulukların dağılımı. Görevler ayrılığı ilkesi gereği "
             "belgeyi hazırlayan, kontrol eden, onaylayan ve ödeyen farklı kişiler olmalıdır.</p>"]
    for rol, b in kilavuz.ROL_REHBERI.items():
        parca.append(f"<h3 style='color:#1f4e79'>{escape(rol)} — {escape(b['unvan'])}</h3><p>{escape(b['ozet'])}</p>"
                     "<ul>" + "".join(f"<li>{escape(g)}</li>" for g in b["gorevler"]) + "</ul>"
                     "<p style='color:#b00020'><b>Dikkat:</b></p><ul>"
                     + "".join(f"<li>{escape(g)}</li>" for g in b["dikkat"]) + "</ul>")
    return "".join(parca)


class RehberSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi("Mevzuat Rehberi", "Uygulamadaki hesap ve kontrollerin dayanakları, yasal takvim, yılın "
                                                        "parametreleri, terimler sözlüğü ve sık yapılan hatalar."))
        self.sekme = QTabWidget()
        self.rehber = QTextBrowser()
        self.rehber.setOpenExternalLinks(True)
        self.takvim = QTextBrowser()
        self.param = QTextBrowser()
        self.sozluk = QTextBrowser()
        self.cezalar = QTextBrowser()
        self.gorevler = QTextBrowser()
        self.sekme.addTab(self.cezalar, "Sık yapılan hatalar ve cezaları")
        self.sekme.addTab(self.sozluk, "Terimler sözlüğü")
        self.sekme.addTab(self.gorevler, "Kim ne yapar?")
        self.sekme.addTab(self.takvim, "Yasal takvim")
        self.sekme.addTab(self.rehber, "Mevzuat özeti")
        self.sekme.addTab(self.param, "Yılın parametreleri")
        lay.addWidget(self.sekme)
        self.yenile()

    def yenile(self):
        self.rehber.setHtml(mevzuat.MEVZUAT_REHBERI_HTML)
        self.sozluk.setHtml(_sozluk_html())
        self.cezalar.setHtml(_ceza_html())
        self.gorevler.setHtml(_gorev_html())
        satir = "".join(f"<tr><td style='padding:4px 10px'><b>{z}</b></td><td style='padding:4px 10px'>{a}</td></tr>"
                        for z, a in mevzuat.YASAL_TAKVIM)
        yakin = "".join(f"<tr><td style='padding:4px 10px'><b>{s.tarih:%d.%m.%Y}</b></td><td style='padding:4px 10px'>"
                        f"{escape(s.ad)}</td><td style='padding:4px 10px; color:#555'>{escape(s.aciklama)}</td></tr>"
                        for s in kilavuz.yaklasan_sureler(gun=60))
        ms = mevzuat.MERKEZ_SAYMANLIK
        self.takvim.setHtml(f"<h2>Önümüzdeki 60 Gün</h2><table border='1' cellspacing='0'>{yakin}</table>"
                            "<p><i>Son gün hafta sonuna veya tatile denk gelse bile işi önceki iş gününde bitirmeniz önerilir.</i></p>"
                            f"<h2>Yasal Takvim</h2><table border='1' cellspacing='0'>{satir}</table>"
                            f"<h3>MEB Merkez Saymanlık Hesabı</h3><p>{ms['ad']}<br>VKN: {ms['vkn']}<br>IBAN: {ms['iban']}</p>")
        p = db().parametreler(Oturum.yil)
        satirlar = []
        for anahtar, etiket, tur, _v, dayanak in mevzuat.PARAMETRELER:
            v = p.get(anahtar)
            if tur == "para":
                g = para(v) + " TL"
            elif tur == "oran":
                g = f"%{float(v) * 100:.3f}".rstrip("0").rstrip(".,").replace(".", ",")
            elif anahtar == "gv_tarifesi_ucret":
                g = "<br>".join(f"{para(u) if u else 'üzeri'}: %{o * 100:g}" for u, o in v)
            else:
                g = f"{v:g}" if isinstance(v, float) else str(v)
            satirlar.append(f"<tr><td style='padding:3px 8px'>{etiket}</td><td style='padding:3px 8px' align='right'><b>{g}</b></td>"
                            f"<td style='padding:3px 8px; color:#555'>{dayanak}</td></tr>")
        self.param.setHtml(f"<h2>{Oturum.yil} Yılı Mevzuat Parametreleri</h2><table border='1' cellspacing='0'>{''.join(satirlar)}</table>"
                           "<p><i>Değerleri 'Mevzuat Parametreleri' sayfasından güncelleyebilirsiniz.</i></p>")
