"""Ağ / uzak erişim ayarları: kurum koduyla her yerden bağlanma.

Kurum kodu lisans ve barındırma kimliğidir. Mobil istemci ve masaüstü, bilinen bir geçit
adresi veya okulun kendi mobil sunucusu üzerinden aynı kurum kodu + kullanıcı + şifre ile
giriş yapar. Veritabanı adı barındırmada 'okul_<kurumkodu>' biçimindedir.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields

from .lisans import kurum_kodu_normalize
from .yollar import VERI

AYAR_DOSYASI = VERI / "ag.json"
OKULLAR_DOSYASI = VERI / "okullar.json"

# Satıcı paketlemeden önce buraya kalıcı geçit adresini yazabilir (ör. https://mobil.ornek.meb.k12.tr).
# Boş bırakılırsa ortam değişkeni DOSE_GECIT veya ag.json kullanılır.
VARSAYILAN_GECIT = ""


@dataclass
class AgAyar:
    """Okul veya satıcı geçit ayarı."""
    gecit_adresi: str = ""          # Mobil API kökü (https://mobil.ornek... veya boş)
    pg_sunucu: str = ""             # Masaüstü için PostgreSQL host (barındırma)
    pg_port: int = 5432
    pg_ssl: str = "require"


def oku() -> AgAyar:
    ayar = AgAyar(gecit_adresi=VARSAYILAN_GECIT or os.environ.get("DOSE_GECIT", "").strip())
    try:
        veri = json.loads(AYAR_DOSYASI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ayar
    adlar = {f.name for f in fields(AgAyar)}
    for k, v in veri.items():
        if k in adlar and v not in (None, ""):
            setattr(ayar, k, v)
    if not ayar.gecit_adresi:
        ayar.gecit_adresi = VARSAYILAN_GECIT or os.environ.get("DOSE_GECIT", "").strip()
    return ayar


def yaz(ayar: AgAyar):
    AYAR_DOSYASI.write_text(json.dumps(asdict(ayar), ensure_ascii=False, indent=2), encoding="utf-8")


def kurum_db_adi(kurum_kodu: str) -> str:
    kod = kurum_kodu_normalize(kurum_kodu)
    if not kod.isdigit() or not (5 <= len(kod) <= 8):
        raise ValueError("Kurum kodu 5–8 rakam olmalıdır.")
    return f"okul_{kod}"


def kurum_kodu_gecerli(kod: str) -> bool:
    k = kurum_kodu_normalize(kod)
    return k.isdigit() and 5 <= len(k) <= 8


def mobil_adres_coz(kurum_kodu: str = "", sunucu_adresi: str = "", gecit: str | None = None) -> str:
    """Mobil istemcinin bağlanacağı API kök adresini seçer.

    Öncelik: elle yazılan sunucu adresi > geçit (ag.json / varsayılan) > boş (hata).
    Kurum kodu adresi seçmez; sunucuda kimlik doğrulama için kullanılır.
    """
    adres = (sunucu_adresi or "").strip()
    if adres:
        return adres
    g = (gecit if gecit is not None else oku().gecit_adresi or "").strip()
    if g:
        return g
    raise ValueError(
        "Sunucu adresi veya kurum geçidi tanımlı değil. Okul Wi-Fi'sinde mobil sunucu IP'sini yazın "
        "veya bilişim sorumlusundan geçit adresini alın. Kurum kodu: "
        f"{kurum_kodu_normalize(kurum_kodu) or '(girilmedi)'}."
    )


def okullar_oku() -> dict:
    """Çok okullu geçit: {sunucu, port, ssl, kullanici_sablonu, okullar: {kod: {sifre, ad}}}."""
    try:
        return json.loads(OKULLAR_DOSYASI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def okullar_yaz(veri: dict):
    OKULLAR_DOSYASI.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
