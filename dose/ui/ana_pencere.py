import importlib
import traceback
from datetime import date, datetime

from html import escape

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QMainWindow, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget)

from .. import SURUM, UYGULAMA_ADI, izleme, kilavuz, lisans, onay
from ..yollar import YEDEKLER
from .giris import SifreDialog
from .lisans_dialog import LisansDialog, durum_rengi
from .marka import ikon
from .ortak import Oturum, bilgi, buton, db, hata
from .yan_menu import YanMenu

# (grup, menü adı, modül, sınıf)
SAYFALAR = [
    ("GENEL", "Bugün Ne Yapmalıyım?", "yapilacaklar", "YapilacaklarSayfasi"),
    ("GENEL", "Gösterge Paneli", "panel", "PanelSayfasi"),
    ("GENEL", "Onay Bekleyenler", "onay_sayfa", "OnaySayfasi"),
    ("YARDIM VE DENETİM", "Nasıl Yaparım? (Adım Adım)", "kilavuz_sayfa", "KilavuzSayfasi"),
    ("YARDIM VE DENETİM", "Mevzuat Uyum Denetimi", "uyum_sayfa", "UyumSayfasi"),
    ("YARDIM VE DENETİM", "Mevzuat Rehberi", "rehber", "RehberSayfasi"),
    ("TANIMLAR", "Kurum ve Görevliler", "kurum", "KurumSayfasi"),
    ("TANIMLAR", "Mevzuat Parametreleri", "parametreler", "ParametreSayfasi"),
    ("TANIMLAR", "Bölüm / Alan / Atölyeler", "tanimlar", "BolumSayfasi"),
    ("TANIMLAR", "Personel", "tanimlar", "PersonelSayfasi"),
    ("TANIMLAR", "Öğrenciler", "tanimlar", "OgrenciSayfasi"),
    ("TANIMLAR", "Cari Hesaplar", "tanimlar", "CariSayfasi"),
    ("TANIMLAR", "Malzeme / Stok Kartları", "tanimlar", "MalzemeSayfasi"),
    ("TANIMLAR", "Ürün / Hizmet ve Maliyet", "maliyet", "UrunSayfasi"),
    ("ÜRETİM VE TİCARET", "Siparişler / İş Emirleri", "siparis", "SiparisSayfasi"),
    ("ÜRETİM VE TİCARET", "Satış Faturaları", "fatura", "SatisSayfasi"),
    ("ÜRETİM VE TİCARET", "Alış / Gider Belgeleri", "fatura", "AlisSayfasi"),
    ("ÜRETİM VE TİCARET", "Kasa / Banka", "kasa", "KasaSayfasi"),
    ("ÜRETİM VE TİCARET", "Stok Durumu ve Hareketleri", "stok", "StokSayfasi"),
    ("PERSONEL ÖDEMELERİ", "Parça Başı Ücret", "parca_basi", "ParcaBasiSayfasi"),
    ("PERSONEL ÖDEMELERİ", "Fazla Çalışma Ücreti", "fazla_calisma", "FazlaCalismaSayfasi"),
    ("PERSONEL ÖDEMELERİ", "Yıl Sonu Kârı ve ÜTP", "yil_sonu", "YilSonuSayfasi"),
    ("YASAL YÜKÜMLÜLÜKLER", "Hazine Payı / SHÇEK", "yukumluluk", "HazinePayiSayfasi"),
    ("YASAL YÜKÜMLÜLÜKLER", "KDV / Muhtasar Özeti", "yukumluluk", "VergiSayfasi"),
    ("MUHASEBE VE RAPORLAR", "Yevmiye / Mizan", "muhasebe_sayfa", "MuhasebeSayfasi"),
    ("MUHASEBE VE RAPORLAR", "Raporlar", "raporlar", "RaporSayfasi"),
    ("MUHASEBE VE RAPORLAR", "Resmi Yazılar / Belgeler", "belgeler", "BelgeSayfasi"),
    ("SİSTEM", "Kullanıcılar", "sistem", "KullaniciSayfasi"),
    ("SİSTEM", "Yedekleme / İşlem Kaydı", "sistem", "YedekSayfasi"),
]

CANLI_ARALIK_MS = 4000
# Kaydedilmemiş form girişleri içerebilen sayfalar başka kullanıcının değişikliğiyle kendiliğinden yenilenmez
ELLE_YENILENEN = {"Kurum ve Görevliler", "Mevzuat Parametreleri", "Yıl Sonu Kârı ve ÜTP", "Mevzuat Rehberi",
                  "Resmi Yazılar / Belgeler"}
YARDIM_SAYFASI = "Nasıl Yaparım? (Adım Adım)"


class GuvenliCikisDialog(QDialog):
    """Onay + isteğe bağlı tüm cihazlardaki mobil oturumları kapatma."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Güvenli çıkış")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "<b>Oturumu kapatmak istediğinize emin misiniz?</b><br><br>"
            "Bu bilgisayardaki oturum sonlanır; giriş ekranına dönersiniz.<br>"
            "Kaydedilmemiş form alanları kaybolabilir."
        ))
        self.c_mobil = QCheckBox("Bu hesaba ait tüm mobil / web oturumlarını da kapat")
        self.c_mobil.setChecked(True)
        self.c_mobil.setToolTip("Telefondaki ve tarayıcıdaki DÖSE Mobil oturumları geçersiz olur; yeniden giriş gerekir.")
        lay.addWidget(self.c_mobil)
        bb = QDialogButtonBox(QDialogButtonBox.Yes | QDialogButtonBox.No)
        bb.button(QDialogButtonBox.Yes).setText("Çıkış yap")
        bb.button(QDialogButtonBox.Yes).setObjectName("tehlike")
        bb.button(QDialogButtonBox.No).setText("Vazgeç")
        bb.button(QDialogButtonBox.No).setDefault(True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    @property
    def mobil_kapat(self) -> bool:
        return self.c_mobil.isChecked()


class AnaPencere(QMainWindow):
    """oturum_sonu(True) → giriş ekranına dön; oturum_sonu(False) → uygulamadan çık."""
    oturum_sonu = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{UYGULAMA_ADI} {SURUM}")
        self.setWindowIcon(ikon())
        self.resize(1360, 820)
        self.sayfalar: dict[int, QWidget] = {}
        self._ad_indeks = {ad: i for i, (_g, ad, _m, _s) in enumerate(SAYFALAR)}
        self._oturum_sonu_yollandi = False
        self.yeniden_giris = False

        merkez = QWidget()
        yatay = QHBoxLayout(merkez)
        yatay.setContentsMargins(0, 0, 0, 0)
        yatay.setSpacing(0)

        self.yan = YanMenu()
        self.yan.doldur(SAYFALAR, Oturum.sayfa_yetkisi)
        self.yan.sayfa_secildi.connect(self._sayfa_ac_ad)
        yatay.addWidget(self.yan)

        sag = QWidget()
        sag_lay = QVBoxLayout(sag)
        sag_lay.setContentsMargins(0, 0, 0, 0)
        ust = QWidget()
        ust.setObjectName("ustBar")
        ust_lay = QHBoxLayout(ust)
        ust_lay.setContentsMargins(12, 6, 12, 6)
        self.okul = QLabel()
        self.okul.setStyleSheet("font-weight:600; color:#1f4e79;")
        ust_lay.addWidget(self.okul)
        ust_lay.addStretch()
        ust_lay.addWidget(QLabel("Çalışma yılı:"))
        self.yil = QComboBox()
        bu_yil = date.today().year
        for y in range(bu_yil + 1, bu_yil - 10, -1):
            self.yil.addItem(str(y), y)
        self.yil.setCurrentIndex(1)
        self.yil.currentIndexChanged.connect(self._yil_degisti)
        ust_lay.addWidget(self.yil)
        self.b_onay = buton("", lambda: self.sayfaya_git("Onay Bekleyenler"), ipucu="Kararınızı bekleyen belgeler")
        self.b_onay.setVisible(False)
        ust_lay.addWidget(self.b_onay)
        self.b_lisans = buton("", self._lisans, ipucu="Lisans durumu ve lisans girişi")
        ust_lay.addWidget(self.b_lisans)
        self.b_yardim = buton("❓ Bu sayfa nedir? (F1)", self.sayfa_yardimi,
                              ipucu="Açık sayfanın ne işe yaradığını, nasıl kullanılacağını ve nelere dikkat edileceğini anlatır")
        ust_lay.addWidget(self.b_yardim)
        QShortcut(QKeySequence(Qt.Key_F1), self).activated.connect(self.sayfa_yardimi)
        k = Oturum.kullanici
        ust_lay.addWidget(QLabel(f"   👤 {k.get('ad_soyad') or k.get('kullanici_adi')} ({k.get('rol')})"))
        ust_lay.addWidget(buton("Şifre", lambda: SifreDialog(self, k["id"]).exec()))
        self.b_cikis = buton("Çıkış", self.guvenli_cikis, "tehlike",
                             ipucu="Oturumu güvenli kapatır; giriş ekranına döner (Ctrl+Shift+Q)")
        ust_lay.addWidget(self.b_cikis)
        QShortcut(QKeySequence("Ctrl+Shift+Q"), self).activated.connect(self.guvenli_cikis)
        sag_lay.addWidget(ust)
        self.yigin = QStackedWidget()
        icerik = QWidget()
        ic_lay = QVBoxLayout(icerik)
        ic_lay.setContentsMargins(14, 10, 14, 10)
        ic_lay.addWidget(self.yigin)
        sag_lay.addWidget(icerik)
        yatay.addWidget(sag)
        self.setCentralWidget(merkez)

        self.okul_guncelle()
        self.lisans_guncelle()
        ilk = next((ad for _g, ad, _m, _s in SAYFALAR if Oturum.sayfa_yetkisi(ad)), None)
        if ilk:
            self.yan.sec(ilk)
            self._sayfa_ac_ad(ilk)
        self.zamanlayici = QTimer(self)
        self.zamanlayici.timeout.connect(self.bildirim_guncelle)
        self.zamanlayici.start(60_000)
        self.bildirim_guncelle()

        self.l_canli = QLabel()
        self.statusBar().addPermanentWidget(self.l_canli)
        self._son_islem = db().son_islem_no()
        self._yenileme_bekliyor = False
        self.canli = QTimer(self)
        self.canli.timeout.connect(self._degisiklik_denetle)
        self.canli.start(CANLI_ARALIK_MS)
        QTimer.singleShot(2500, self._guncelleme_kontrol)

    def _guncelleme_kontrol(self):
        """GitHub surum.json ile karşılaştırır; yeni sürüm varsa uyarır."""
        try:
            from .. import guncelleme
            bil = guncelleme.kontrol_et()
        except Exception:
            return
        if not bil:
            return
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        from PySide6.QtWidgets import QMessageBox
        kutu = QMessageBox(self)
        kutu.setWindowTitle("Güncelleme var")
        kutu.setWindowIcon(ikon())
        kutu.setIcon(QMessageBox.Information)
        kutu.setText(f"Yeni sürüm yayınlandı: <b>{bil.surum}</b> (sizin sürümünüz: {SURUM})")
        kutu.setInformativeText((bil.notlar or "İyileştirmeler ve düzeltmeler içerir.") +
                                "\n\nGitHub Releases sayfasından indirip kurulum dosyasını çalıştırın; verileriniz korunur.")
        indir = kutu.addButton("İndir / GitHub", QMessageBox.AcceptRole)
        kutu.addButton("Sonra", QMessageBox.RejectRole)
        kutu.exec()
        if kutu.clickedButton() == indir:
            QDesktopServices.openUrl(QUrl(bil.indir or guncelleme.RELEASES_URL))

    def _degisiklik_denetle(self):
        """Başka bilgisayar veya mobil cihazlarda yapılan değişiklikleri açık sayfaya yansıtır."""
        try:
            yeni = db().degisiklikler(self._son_islem)
        except Exception:
            self.l_canli.setText("⚠ Sunucuya ulaşılamıyor; yeniden deneniyor…")
            return
        if yeni:
            self._son_islem = yeni[-1]["id"]
            self._yenileme_bekliyor = True
            r = yeni[-1]
            kim = r.get("ad_soyad") or r.get("kullanici") or ""
            rol = f" ({r['rol']})" if r.get("rol") else ""
            cihaz = " 📱" if r.get("istemci") == "Mobil" else ""
            ek = f"  +{len(yeni) - 1} işlem daha" if len(yeni) > 1 else ""
            self.l_canli.setText(f"🔄 {str(r.get('zaman') or '')[11:16]} {kim}{rol}{cihaz}: "
                                 f"{izleme.tablo_adi(r.get('tablo')) or r.get('tablo') or ''} {str(r.get('islem') or '').lower()}{ek}")
            self.l_canli.setToolTip("\n".join(f"{x['zaman']}  {x.get('ad_soyad') or x['kullanici']}  {x['islem']}  "
                                              f"{izleme.tablo_adi(x.get('tablo'))} #{x.get('kayit_id') or ''}" for x in yeni[-15:]))
            self.bildirim_guncelle()
        if not self._yenileme_bekliyor or QApplication.activeModalWidget() is not None or QApplication.activePopupWidget():
            return
        self._yenileme_bekliyor = False
        w = self.yigin.currentWidget()
        if w is None or not hasattr(w, "yenile"):
            return
        if getattr(w, "sayfa_adi", "") in ELLE_YENILENEN:
            self.statusBar().showMessage("Başka kullanıcılar değişiklik yaptı. Bu sayfadaki kaydedilmemiş girişleriniz "
                                         "silinmesin diye sayfa yenilenmedi; güncel veriler için sayfayı yeniden açınız.", 15_000)
            return
        try:
            w.yenile()
        except Exception:
            traceback.print_exc()

    def bildirim_guncelle(self):
        try:
            n = onay.bekleyen_sayisi(Oturum.kullanici) if onay.akis_acik() else 0
        except Exception:
            traceback.print_exc()
            return
        self.b_onay.setText(f"🔔 Onayınızı bekleyen: {n}")
        self.b_onay.setVisible(n > 0)

    def lisans_guncelle(self):
        d = lisans.uygula(db())
        self.b_lisans.setText(("⚠ " if d.uyari or not d.yazilabilir else "🔑 ") +
                              (d.ozet if d.uyari or not d.yazilabilir else "Lisanslı"))
        self.b_lisans.setStyleSheet(durum_rengi(d))
        self.statusBar().showMessage(f"{db().aciklama()}  •  Rol: {Oturum.rol()}  •  {d.ozet}")

    def _lisans(self):
        onceki = db().salt_okunur
        LisansDialog(self).exec()
        self.lisans_guncelle()
        if onceki != db().salt_okunur:
            bilgi(self, "Lisans durumu değişti. Düzenleme düğmelerinin güncellenmesi için programı kapatıp yeniden açın.")

    def okul_guncelle(self):
        k = db().kurum()
        self.okul.setText(f"{k.get('okul_adi') or ''}  •  {k.get('isletme_adi') or ''}")

    def _sayfa_ac_ad(self, ad: str):
        i = self._ad_indeks.get(ad)
        if i is None:
            return
        Oturum.aktif_sayfa = ad
        if i not in self.sayfalar:
            _g, _ad, modul, sinif = SAYFALAR[i]
            try:
                m = importlib.import_module(f"dose.ui.sayfalar.{modul}")
                w = getattr(m, sinif)()
            except Exception:
                hata(self, f"'{ad}' sayfası açılamadı:\n\n{traceback.format_exc()}")
                return
            w.ana_pencere = self
            w.sayfa_adi = ad
            self.sayfalar[i] = w
            self.yigin.addWidget(w)
        w = self.sayfalar[i]
        self.yigin.setCurrentWidget(w)
        if hasattr(w, "yenile") and getattr(w, "_ilk_acilis_yapildi", False):
            try:
                w.yenile()
            except Exception:
                hata(self, traceback.format_exc())
        w._ilk_acilis_yapildi = True

    def _yil_degisti(self):
        Oturum.yil = self.yil.currentData()
        w = self.yigin.currentWidget()
        if w is not None and hasattr(w, "yenile"):
            w.yenile()

    # ------------------------------------------------------------ güvenli çıkış
    def guvenli_cikis(self):
        d = GuvenliCikisDialog(self)
        if not d.exec():
            return
        self._oturumu_sonlandir(neden="Güvenli çıkış", mobil_kapat=d.mobil_kapat, yeniden_giris=True)

    def _oturumu_sonlandir(self, neden: str, mobil_kapat: bool = False, yeniden_giris: bool = False):
        self.yeniden_giris = yeniden_giris
        try:
            self.canli.stop()
            self.zamanlayici.stop()
        except Exception:
            pass
        kid = Oturum.kullanici.get("id")
        try:
            if mobil_kapat and kid:
                cur = db().ex("UPDATE mobil_oturum SET aktif = 0 WHERE kullanici_id = ? AND aktif = 1", (kid,))
                n = getattr(cur, "rowcount", None) or 0
                db().log("Oturum kapatma", detay=f"{neden}; mobil oturumlar kapatıldı ({n})")
            else:
                db().log("Oturum kapatma", detay=neden)
        except Exception:
            traceback.print_exc()
        try:
            self._yedek_kapanis()
        except Exception:
            traceback.print_exc()
        Oturum.temizle()
        self._oturum_sonu_yollandi = True
        self.oturum_sonu.emit(yeniden_giris)
        self.close()

    def _yedek_kapanis(self):
        son = db().ayar("son_yedek")
        yedek_alir = Oturum.sayfa_yetkisi("Yedekleme / İşlem Kaydı") == "y" or not db().sunucu_mu
        # Oturum.temizle öncesi yetki kontrolü — çağıran sıraya dikkat
        if yedek_alir and (not son or (datetime.now() - datetime.fromisoformat(son)).days >= 1):
            db().yedekle()
        yedekler = sorted(YEDEKLER.glob("dose_yedek_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for eski in yedekler[30:]:
            eski.unlink(missing_ok=True)

    def closeEvent(self, e):
        if self._oturum_sonu_yollandi:
            e.accept()
            return
        # Pencere X ile kapatılıyor → uygulamadan çık (yeniden giriş yok)
        try:
            self.canli.stop()
            self.zamanlayici.stop()
        except Exception:
            pass
        try:
            self._yedek_kapanis()
        except Exception:
            traceback.print_exc()
        try:
            db().log("Oturum kapatma", detay="Pencere kapatıldı")
        except Exception:
            pass
        Oturum.temizle()
        self._oturum_sonu_yollandi = True
        self.oturum_sonu.emit(False)
        e.accept()

    def sayfaya_git(self, menu_adi: str) -> bool:
        if self.yan.sec(menu_adi):
            self._sayfa_ac_ad(menu_adi)
            return True
        return False

    def rehber_ac(self, kod: str | None):
        """Adım adım rehber sayfasını açar ve verilen rehberi seçer."""
        if self.sayfaya_git(YARDIM_SAYFASI) and kod:
            w = self.yigin.currentWidget()
            if hasattr(w, "sec"):
                w.sec(kod)

    def sayfa_yardimi(self):
        ad = getattr(self.yigin.currentWidget(), "sayfa_adi", None) or Oturum.aktif_sayfa or ""
        ne, nasil, dikkat, rehber = kilavuz.SAYFA_YARDIMI.get(
            ad, ("Bu sayfa için ayrıca yardım metni yok.", [], [], None))
        html = [f"<h2 style='color:#1f4e79'>{escape(ad)}</h2>", f"<p><b>Bu sayfa ne işe yarar?</b><br>{escape(ne)}</p>"]
        if nasil:
            html.append("<p><b>Nasıl kullanılır?</b></p><ol>" + "".join(f"<li>{escape(x)}</li>" for x in nasil) + "</ol>")
        if dikkat:
            html.append("<p style='color:#b00020'><b>⚠ Dikkat</b></p><ul>" + "".join(f"<li>{escape(x)}</li>" for x in dikkat)
                        + "</ul>")
        yetki_ = Oturum.sayfa_yetkisi(ad)
        if yetki_ == "g":
            html.append("<p style='color:#555'><i>Bu sayfada yalnız görüntüleme yetkiniz var.</i></p>")
        d = QDialog(self)
        d.setWindowTitle(f"Yardım — {ad}")
        d.resize(620, 480)
        v = QVBoxLayout(d)
        t = QTextBrowser()
        t.setHtml("".join(html))
        v.addWidget(t)
        alt = QHBoxLayout()
        if rehber and rehber in kilavuz.REHBER:
            r = kilavuz.REHBER[rehber]
            alt.addWidget(buton(f"{r.ikon} Adım adım: {r.baslik}", lambda: (d.accept(), self.rehber_ac(rehber)), "birincil"))
        alt.addWidget(buton("Tüm rehberler", lambda: (d.accept(), self.rehber_ac(None))))
        alt.addStretch()
        alt.addWidget(buton("Kapat", d.accept))
        v.addLayout(alt)
        d.exec()
