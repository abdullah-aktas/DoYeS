"""Onay bekleyen belgeler ve belge onay penceresi (akış, geçmiş, karar)."""
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QInputDialog, QLabel, QTabWidget, QVBoxLayout, QWidget)

from ... import onay
from ...hesap import para
from ...yetki import AKISLAR, BELGE_SAYFASI, GERI_ALABILEN
from ..ortak import Kolon, Oturum, VeriTablosu, baslik_etiketi, bilgi, buton, db, soru, uyari


def belge_kapsaminda(tur: str, bid: int) -> bool:
    """Alan şefi / öğretmen yalnız kendi bölümünün belgeleri üzerinde işlem yapabilir."""
    bolum = Oturum.bolum_id()
    if not bolum:
        return True
    return onay.KANCALAR[tur]["bolum"](bid) in (None, 0, bolum)


def _hazirlayabilir(tur: str, bid: int) -> bool:
    return Oturum.yazabilir(sayfa=BELGE_SAYFASI[tur]) and belge_kapsaminda(tur, bid)


def _gerekce(parent, baslik: str, zorunlu: bool) -> str | None:
    metin, ok = QInputDialog.getMultiLineText(parent, baslik, "Açıklama / gerekçe" + (" (zorunlu):" if zorunlu else ":"))
    if not ok:
        return None
    if zorunlu and not metin.strip():
        uyari(parent, "Gerekçe yazınız.")
        return None
    return metin.strip()


def _calistir(parent, islev, *args) -> bool:
    try:
        islev(*args)
        return True
    except onay.OnayHatasi as e:
        uyari(parent, str(e))
        return False


def onayla_veya_gonder(parent, tur: str, bid: int, soru_metni: str) -> bool:
    """Onay akışı kapalıysa belgeyi doğrudan onaylar, açıksa onay penceresini açar. Durum değiştiyse True."""
    if not onay.akis_acik():
        if not _hazirlayabilir(tur, bid):
            uyari(parent, "Bu belge üzerinde işlem yetkiniz bulunmuyor.")
            return False
        if onay.durum(tur, bid)["durum"] == onay.ONAYLANDI:
            bilgi(parent, "Belge zaten onaylı.")
            return False
        if not soru(parent, soru_metni):
            return False
        return _calistir(parent, onay.dogrudan_onayla, tur, bid, Oturum.kullanici)
    return bool(OnayDialog(parent, tur, bid).exec())


def onay_kaldir(parent, tur: str, bid: int, soru_metni: str) -> bool:
    if onay.akis_acik() and Oturum.rol() not in GERI_ALABILEN:
        uyari(parent, "Onayı yalnız harcama yetkilisi (okul müdürü) veya sistem yöneticisi kaldırabilir.")
        return False
    if not onay.akis_acik() and not _hazirlayabilir(tur, bid):
        uyari(parent, "Bu belge üzerinde işlem yetkiniz bulunmuyor.")
        return False
    if not soru(parent, soru_metni):
        return False
    return _calistir(parent, onay.geri_al, tur, bid, Oturum.kullanici, "", False)


class OnayDialog(QDialog):
    def __init__(self, parent, tur: str, bid: int):
        super().__init__(parent)
        self.tur, self.bid = tur, bid
        oz = onay.ozet(tur, bid)
        self.setWindowTitle(f"Onay akışı - {tur}: {oz.get('no') or bid}")
        self.resize(820, 560)
        lay = QVBoxLayout(self)
        self.bilgi = QLabel()
        self.bilgi.setWordWrap(True)
        lay.addWidget(self.bilgi)
        self.asamalar = VeriTablosu()
        self.asamalar.setMaximumHeight(170)
        lay.addWidget(QLabel("<b>Onay aşamaları</b>"))
        lay.addWidget(self.asamalar)
        lay.addWidget(QLabel("<b>İşlem geçmişi</b>"))
        self.gecmis = VeriTablosu()
        lay.addWidget(self.gecmis)
        self.butonlar = QHBoxLayout()
        lay.addLayout(self.butonlar)
        self.degisti = False
        self.yenile()

    def yenile(self):
        tur, bid = self.tur, self.bid
        d = onay.durum(tur, bid)
        oz = onay.ozet(tur, bid)
        akis = onay.akis_acik()
        self.bilgi.setText(
            f"<b>{tur}</b> • {oz.get('no') or ''} • {oz.get('konu') or ''}"
            + (f" • {para(oz['tutar'])} TL" if oz.get("tutar") else "")
            + (f" • Bölüm: {oz['bolum_ad']}" if oz.get("bolum_ad") else "")
            + f"<br><b>Durum:</b> {onay.durum_metni(d)}"
            + ("" if akis else "<br><i>Onay akışı kapalı: belge tek adımda onaylanır (Kullanıcılar ekranından açılabilir).</i>"))
        gecmis = onay.gecmis(tur, bid)
        satirlar = []
        for i, (ad, rol) in enumerate(AKISLAR[tur], start=1):
            son = next((g for g in reversed(gecmis) if g["asama"] == i and g["karar"] not in ("İade edildi",)), None)
            if d["durum"] == onay.ONAYLANDI or (d["durum"] == onay.BEKLIYOR and i < d["asama"]):
                durum_ = "✔ " + (son["karar"] if son else "Tamam")
            elif d["durum"] == onay.BEKLIYOR and i == d["asama"]:
                durum_ = "⏳ Bekliyor"
            else:
                durum_ = "—"
            satirlar.append({"sira": i, "ad": ad, "rol": rol, "durum": durum_,
                             "kisi": (son or {}).get("ad_soyad") if durum_.startswith("✔") else "",
                             "zaman": (son or {}).get("zaman") if durum_.startswith("✔") else ""})
        self.asamalar.doldur([Kolon("sira", "#", "sayi"), Kolon("ad", "Aşama"), Kolon("rol", "Yetkili rol"),
                              Kolon("durum", "Durum"), Kolon("kisi", "Karar veren"), Kolon("zaman", "Zaman")], satirlar,
                             lambda s: "#eef6ee" if s["durum"].startswith("✔") else ("#fff4e5" if s["durum"].startswith("⏳") else None))
        self.gecmis.doldur([Kolon("zaman", "Zaman"), Kolon("asama_adi", "Aşama"), Kolon("karar", "Karar"),
                            Kolon("ad_soyad", "Kişi"), Kolon("rol", "Rol"), Kolon("aciklama", "Açıklama", genislik=260)],
                           list(reversed(gecmis)),
                           lambda s: "#fdecea" if s["karar"] in ("İade edildi", "Onay kaldırıldı") else None)
        while self.butonlar.count():
            w = self.butonlar.takeAt(0).widget()
            if w:
                w.deleteLater()
        k = Oturum.kullanici
        if d["durum"] in (onay.HAZIRLANIYOR, onay.IADE) and _hazirlayabilir(tur, bid):
            if akis:
                self.butonlar.addWidget(buton("Onaya gönder", self.gonder, "birincil"))
            else:
                self.butonlar.addWidget(buton("Onayla", self.dogrudan, "birincil"))
        if d["durum"] == onay.BEKLIYOR:
            if onay.yetkili_mi(d, k):
                son = d["asama"] == len(AKISLAR[tur])
                self.butonlar.addWidget(buton("Onayla" if son else "Uygun gör", self.uygun, "birincil"))
                self.butonlar.addWidget(buton("İade et", self.iade, "tehlike"))
            if _hazirlayabilir(tur, bid):
                self.butonlar.addWidget(buton("Geri çek (düzeltme için)", self.geri_cek))
        if d["durum"] == onay.ONAYLANDI and (k.get("rol") in GERI_ALABILEN if akis else _hazirlayabilir(tur, bid)):
            self.butonlar.addWidget(buton("Onayı kaldır", self.kaldir, "tehlike"))
        self.butonlar.addStretch()
        self.butonlar.addWidget(buton("Kapat", self._kapat))

    def _sonra(self, ok: bool):
        if ok:
            self.degisti = True
            self.yenile()
            ana = getattr(self.parent(), "window", lambda: None)()
            if hasattr(ana, "bildirim_guncelle"):
                ana.bildirim_guncelle()

    def gonder(self):
        a = _gerekce(self, "Onaya gönder", False)
        if a is not None:
            self._sonra(_calistir(self, onay.gonder, self.tur, self.bid, Oturum.kullanici, a))

    def dogrudan(self):
        if soru(self, "Belge onaylansın mı?"):
            self._sonra(_calistir(self, onay.dogrudan_onayla, self.tur, self.bid, Oturum.kullanici))

    def uygun(self):
        a = _gerekce(self, "Uygun görüş / onay", False)
        if a is not None:
            self._sonra(_calistir(self, onay.karar_ver, self.tur, self.bid, Oturum.kullanici, True, a))

    def iade(self):
        a = _gerekce(self, "İade", True)
        if a is not None:
            self._sonra(_calistir(self, onay.karar_ver, self.tur, self.bid, Oturum.kullanici, False, a))

    def geri_cek(self):
        if soru(self, "Belge onay sürecinden geri çekilsin mi?"):
            self._sonra(_calistir(self, onay.geri_cek, self.tur, self.bid, Oturum.kullanici, ""))

    def kaldir(self):
        a = _gerekce(self, "Onayı kaldır", True)
        if a is not None:
            self._sonra(_calistir(self, onay.geri_al, self.tur, self.bid, Oturum.kullanici, a))

    def _kapat(self):
        self.done(1 if self.degisti else 0)

    def reject(self):
        self._kapat()


class OnaySayfasi(QWidget):
    KOLONLAR = [Kolon("belge_turu", "Belge türü"), Kolon("no", "Belge"), Kolon("konu", "Konu", genislik=240),
                Kolon("bolum_ad", "Bölüm"), Kolon("tutar", "Tutar", "para"), Kolon("asama_adi", "Bekleyen aşama"),
                Kolon("bekleyen_rol", "Yetkili"), Kolon("hazirlayan", "Hazırlayan"), Kolon("guncelleme", "Son işlem")]

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "Onay Bekleyenler",
            "Siparişler (iş emirleri), parça başı ve fazla çalışma bordroları ile yıl sonu kâr dağıtımı; alan şefi uygun görüşü, "
            "gerçekleştirme görevlisi (teknik müdür yardımcısı) kontrolü ve harcama yetkilisi (okul müdürü) onayından geçer. "
            "Son onayla birlikte yardımcı muhasebe kayıtları oluşur."))
        self.durum = QLabel()
        self.durum.setWordWrap(True)
        lay.addWidget(self.durum)
        self.sekme = QTabWidget()
        lay.addWidget(self.sekme)

        w1 = QWidget()
        l1 = QVBoxLayout(w1)
        u1 = QHBoxLayout()
        u1.addWidget(buton("Seçilenleri onayla / uygun gör", self.toplu_onay, "birincil"))
        u1.addWidget(buton("İade et", self.iade, "tehlike"))
        u1.addWidget(buton("Akış ve geçmiş", lambda: self.ac(self.t_bana)))
        u1.addWidget(buton("Belgenin sayfasına git", lambda: self.git(self.t_bana)))
        u1.addStretch()
        u1.addWidget(buton("Yenile", self.yenile))
        l1.addLayout(u1)
        self.t_bana = VeriTablosu()
        self.t_bana.satirCiftTiklandi.connect(lambda _s: self.ac(self.t_bana))
        l1.addWidget(self.t_bana)
        self.sekme.addTab(w1, "Kararımı bekleyenler")

        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        u2 = QHBoxLayout()
        u2.addWidget(buton("Akış ve geçmiş", lambda: self.ac(self.t_tum)))
        u2.addWidget(buton("Belgenin sayfasına git", lambda: self.git(self.t_tum)))
        u2.addStretch()
        l2.addLayout(u2)
        self.t_tum = VeriTablosu()
        self.t_tum.satirCiftTiklandi.connect(lambda _s: self.ac(self.t_tum))
        l2.addWidget(self.t_tum)
        self.sekme.addTab(w2, "Süreçteki / iade edilen belgeler")

        w3 = QWidget()
        l3 = QVBoxLayout(w3)
        self.t_gecmis = VeriTablosu()
        l3.addWidget(self.t_gecmis)
        self.sekme.addTab(w3, "Son onay işlemleri")
        self.yenile()

    def yenile(self):
        acik = onay.akis_acik()
        self.durum.setText(
            "✔ Onay akışı <b>açık</b>." if acik else
            "ℹ Onay akışı <b>kapalı</b>: belgeler ilgili sayfalardan tek adımda onaylanır. Sistem yöneticisi "
            "<b>Kullanıcılar</b> ekranından akışı açabilir.")
        k = Oturum.kullanici
        self.t_bana.doldur(self.KOLONLAR, onay.bekleyenler(k) if acik else [])
        bolum = Oturum.bolum_id()
        tum = []
        for d in db().q("SELECT * FROM onay_durum WHERE durum IN (?, ?) ORDER BY guncelleme DESC",
                        (onay.BEKLIYOR, onay.IADE)):
            if d["belge_turu"] not in AKISLAR or (bolum and d.get("bolum_id") not in (None, 0, bolum)):
                continue
            d.update(onay.ozet(d["belge_turu"], d["belge_id"]))
            b = onay.asama_bilgisi(d["belge_turu"], d["asama"])
            d["asama_adi"], d["bekleyen_rol"] = b if b else ("İade edildi — hazırlayanda", "")
            tum.append(d)
        self.t_tum.doldur(self.KOLONLAR, tum, lambda s: "#fdecea" if s["durum"] == onay.IADE else None)
        gecmis = db().q("SELECT * FROM onay_kaydi ORDER BY id DESC LIMIT 300")
        if bolum:
            izinli = {(d["belge_turu"], d["belge_id"]) for d in db().q("SELECT belge_turu, belge_id, bolum_id FROM onay_durum")
                      if d["bolum_id"] in (None, 0, bolum)}
            gecmis = [g for g in gecmis if (g["belge_turu"], g["belge_id"]) in izinli]
        for g in gecmis:
            g["belge"] = onay.ozet(g["belge_turu"], g["belge_id"]).get("no")
        self.t_gecmis.doldur([Kolon("zaman", "Zaman"), Kolon("belge_turu", "Belge türü"), Kolon("belge", "Belge"),
                              Kolon("asama_adi", "Aşama"), Kolon("karar", "Karar"), Kolon("ad_soyad", "Kişi"),
                              Kolon("rol", "Rol"), Kolon("aciklama", "Açıklama", genislik=260)], gecmis)
        ana = self.window()
        if hasattr(ana, "bildirim_guncelle"):
            ana.bildirim_guncelle()

    def ac(self, tablo):
        s = tablo.secili()
        if s and OnayDialog(self, s["belge_turu"], s["belge_id"]).exec():
            self.yenile()

    def git(self, tablo):
        s = tablo.secili()
        ana = getattr(self, "ana_pencere", None)
        if s and ana:
            ana.sayfaya_git(BELGE_SAYFASI[s["belge_turu"]])

    def toplu_onay(self):
        secili = self.t_bana.secililer()
        if not secili:
            bilgi(self, "Listeden belge seçiniz (Ctrl / Shift ile birden fazla).")
            return
        if not soru(self, f"{len(secili)} belge için uygun görüş / onay verilsin mi?"):
            return
        hatalar = []
        for s in secili:
            try:
                onay.karar_ver(s["belge_turu"], s["belge_id"], Oturum.kullanici, True)
            except onay.OnayHatasi as e:
                hatalar.append(f"{s['belge_turu']} {s.get('no')}: {e}")
        if hatalar:
            uyari(self, "\n\n".join(hatalar))
        self.yenile()

    def iade(self):
        s = self.t_bana.secili()
        if not s:
            return
        a = _gerekce(self, "İade", True)
        if a is not None and _calistir(self, onay.karar_ver, s["belge_turu"], s["belge_id"], Oturum.kullanici, False, a):
            self.yenile()
