import os
import sys
from pathlib import Path


def _kok() -> Path:
    if os.environ.get("DOSE_KOK"):
        return Path(os.environ["DOSE_KOK"]).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


KOK = _kok()
GORSEL = Path(__file__).resolve().parent / "gorsel"


def veri_klasoru() -> Path:
    """Veritabanı, yedek ve çıktılar program klasöründeki 'veri' altında tutulur;
    yazma izni yoksa kullanıcının AppData klasörüne düşülür."""
    aday = KOK / "veri"
    try:
        aday.mkdir(parents=True, exist_ok=True)
        deneme = aday / ".yazma_testi"
        deneme.write_text("ok", encoding="utf-8")
        deneme.unlink()
        return aday
    except OSError:
        taban = Path(os.environ.get("APPDATA", str(Path.home())))
        eski = taban / "MEB_DOSE"
        alt = eski if eski.exists() else taban / "DOSE_Yonetim"
        alt.mkdir(parents=True, exist_ok=True)
        return alt


VERI = veri_klasoru()
VERITABANI = VERI / "dose.db"
YEDEKLER = VERI / "yedekler"
CIKTILAR = VERI / "ciktilar"

for _k in (YEDEKLER, CIKTILAR):
    _k.mkdir(parents=True, exist_ok=True)
