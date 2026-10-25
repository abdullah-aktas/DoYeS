"""Veritabanı bağlantı ayarları: yerel dosya (SQLite) veya merkezi sunucu (PostgreSQL).

Ayarlar program klasöründeki veri/baglanti.json dosyasında tutulur. Sunucu şifresi Windows DPAPI ile
bu bilgisayardaki Windows kullanıcısına bağlı olarak şifrelenir; dosya başka bir bilgisayara kopyalansa da çözülemez.
"""
import base64
import ctypes
import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from urllib.parse import parse_qs, unquote, urlsplit

from .yollar import VERI

AYAR_DOSYASI = VERI / "baglanti.json"
SSL_SECENEKLERI = [("require", "Zorunlu (önerilen)"), ("verify-full", "Zorunlu + sertifika doğrulama"),
                   ("prefer", "Mümkünse"), ("disable", "Kapalı (yalnız yerel ağ)")]


@dataclass
class BaglantiAyari:
    tur: str = "yerel"  # "yerel" | "sunucu"
    sunucu: str = ""
    port: int = 5432
    veritabani: str = "dose"
    kullanici: str = ""
    sifre: str = ""
    ssl: str = "require"

    @property
    def sunucu_mu(self) -> bool:
        return self.tur == "sunucu"

    def dsn(self) -> dict:
        return {"host": self.sunucu, "port": int(self.port or 5432), "dbname": self.veritabani, "user": self.kullanici,
                "password": self.sifre, "sslmode": self.ssl or "require", "connect_timeout": 10,
                "application_name": "DOSE_Yonetim", "keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10,
                "keepalives_count": 3}

    def ozet(self) -> str:
        if not self.sunucu_mu:
            return "Yerel veritabanı (bu bilgisayar)"
        return f"Sunucu: {self.kullanici}@{self.sunucu}:{self.port}/{self.veritabani}"


# ---------------------------------------------------------------- DPAPI
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(veri: bytes, koru: bool) -> bytes:
    tampon = ctypes.create_string_buffer(veri, len(veri))
    giris = _Blob(len(veri), ctypes.cast(tampon, ctypes.POINTER(ctypes.c_char)))
    cikis = _Blob()
    crypt32 = ctypes.windll.crypt32
    islev = crypt32.CryptProtectData if koru else crypt32.CryptUnprotectData
    if not islev(ctypes.byref(giris), None, None, None, None, 0x01, ctypes.byref(cikis)):
        raise OSError("Şifre çözülemedi (DPAPI).")
    try:
        return ctypes.string_at(cikis.pbData, cikis.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(cikis.pbData, ctypes.c_void_p))


def sifrele(metin: str) -> str:
    if not metin:
        return ""
    if sys.platform == "win32":
        return "dpapi:" + base64.b64encode(_dpapi(metin.encode("utf-8"), True)).decode("ascii")
    return "b64:" + base64.b64encode(metin.encode("utf-8")).decode("ascii")


def coz(metin: str) -> str:
    if not metin:
        return ""
    try:
        tur, _, veri = metin.partition(":")
        ham = base64.b64decode(veri)
        return (_dpapi(ham, False) if tur == "dpapi" else ham).decode("utf-8")
    except Exception:
        return ""


# ---------------------------------------------------------------- okuma / yazma
def oku() -> BaglantiAyari:
    dsn = os.environ.get("DOSE_DATABASE_URL", "").strip()
    if dsn:
        url = urlsplit(dsn)
        if url.scheme not in ("postgres", "postgresql") or not url.hostname or not url.path.strip("/"):
            raise ValueError("DOSE_DATABASE_URL geçerli bir PostgreSQL bağlantı adresi olmalıdır.")
        query = parse_qs(url.query)
        return BaglantiAyari(
            tur="sunucu",
            sunucu=url.hostname,
            port=url.port or 5432,
            veritabani=unquote(url.path.lstrip("/")),
            kullanici=unquote(url.username or ""),
            sifre=unquote(url.password or ""),
            ssl=query.get("sslmode", ["require"])[0],
        )
    try:
        veri = json.loads(AYAR_DOSYASI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return BaglantiAyari()
    adlar = {f.name for f in fields(BaglantiAyari)}
    ayar = BaglantiAyari(**{k: v for k, v in veri.items() if k in adlar and k != "sifre"})
    ayar.sifre = coz(veri.get("sifre", ""))
    return ayar


def yaz(ayar: BaglantiAyari):
    veri = asdict(ayar)
    veri["sifre"] = sifrele(ayar.sifre)
    AYAR_DOSYASI.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
