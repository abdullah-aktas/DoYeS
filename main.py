"""DÖSE Yönetim Sistemi - başlangıç noktası."""
import sys
import traceback

from PySide6.QtCore import QEventLoop, QLocale
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from dose import UYGULAMA_ADI, db
from dose.lisans import SaltOkunurHata
from dose.yollar import GORSEL
from dose.ui.tema import STIL


def _hata_yakala(tur, deger, iz):
    if isinstance(deger, SaltOkunurHata):
        QMessageBox.warning(None, "Salt okunur", str(deger))
        return
    if isinstance(deger, db.KayitCakismasi):
        QMessageBox.warning(None, "Kayıt başka kullanıcı tarafından değiştirildi", str(deger))
        return
    metin = "".join(traceback.format_exception(tur, deger, iz))
    try:
        db.al().log("Hata", detay=metin[-1500:])
    except Exception:
        pass
    QMessageBox.critical(None, "Beklenmeyen hata", metin[-3000:])


def _veritabani_ac() -> bool:
    """Kayıtlı bağlantıyla veritabanını açar; sunucuya ulaşılamazsa bağlantı ayarları ekranını gösterir."""
    try:
        db.baslat()
        return True
    except Exception as e:
        from dose.ui.baglanti_dialog import BaglantiDialog
        return bool(BaglantiDialog(None, str(e).strip() or type(e).__name__).exec())


def main():
    QLocale.setDefault(QLocale(QLocale.Turkish, QLocale.Turkey))
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DOSE.Yonetim")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(UYGULAMA_ADI)
    app.setWindowIcon(QIcon(str(GORSEL / "ikon.ico")))
    app.setStyle("Fusion")
    app.setStyleSheet(STIL)
    # Güvenli çıkışta pencere kapanınca uygulama hemen bitmesin; giriş ekranına dönülebilsin.
    app.setQuitOnLastWindowClosed(False)
    if not _veritabani_ac():
        return 0
    sys.excepthook = _hata_yakala

    from dose.ui.giris import GirisDialog
    from dose.ui.ana_pencere import AnaPencere

    while True:
        if not GirisDialog().exec():
            return 0
        pencere = AnaPencere()
        dongu = QEventLoop()
        yeniden = [False]

        def _bitti(girise_don: bool):
            yeniden[0] = girise_don
            dongu.quit()

        pencere.oturum_sonu.connect(_bitti)
        pencere.showMaximized()
        dongu.exec()
        if not yeniden[0]:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
