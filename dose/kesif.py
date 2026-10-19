"""Sunucu adresi olmadan bağlanma: LAN keşif + GitHub geçit + yerel kayıt.

Öncelik:
  1) Elle yazılan adres
  2) Okul Wi-Fi'sinde UDP keşif (mobil sunucu yayınlar)
  3) GitHub surum.json içindeki 'gecit'
  4) ag.json / VARSAYILAN_GECIT / DOSE_GECIT
"""
from __future__ import annotations

import json
import socket
import threading
import time

from . import ag
from .lisans import kurum_kodu_normalize

KESIF_PORT = 8766
ONEK = "DOSE1"
YAYIN_ARALIK = 3.0


def _paket(veri: dict) -> bytes:
    return (ONEK + "|" + json.dumps(veri, ensure_ascii=False, separators=(",", ":"))).encode("utf-8")


def _coz(ham: bytes) -> dict | None:
    try:
        metin = ham.decode("utf-8", errors="ignore").strip()
        if not metin.startswith(ONEK + "|"):
            return None
        return json.loads(metin[len(ONEK) + 1:])
    except (ValueError, json.JSONDecodeError):
        return None


def lan_kesfet(kurum_kodu: str = "", sure: float = 2.0) -> str | None:
    """Yerel ağdaki DÖSE Mobil Sunucu'yu bulur; bulunursa http(s)://ip:port döner."""
    kod = kurum_kodu_normalize(kurum_kodu)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.4)
    try:
        sock.bind(("", 0))
        bitis = time.monotonic() + sure
        istek = _paket({"sorgu": True, "kurum_kodu": kod})
        while time.monotonic() < bitis:
            try:
                sock.sendto(istek, ("255.255.255.255", KESIF_PORT))
            except OSError:
                pass
            try:
                veri, adres = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            y = _coz(veri)
            if not y or y.get("sorgu") or y.get("uygulama") != "DOSE":
                continue
            if kod and y.get("kurum_kodu") and kurum_kodu_normalize(y["kurum_kodu"]) != kod:
                continue
            port = int(y.get("port") or 8765)
            sema = "https" if y.get("https") else "http"
            host = y.get("host") or adres[0]
            return f"{sema}://{host}:{port}"
    finally:
        sock.close()
    return None


class Yayinci:
    """Mobil sunucu sürecinde yerel ağa periyodik keşif yanıtı yayınlar."""

    def __init__(self, port: int = 8765, https: bool = False, kurum_kodu: str = "", okul: str = ""):
        self.port = port
        self.https = https
        self.kurum_kodu = kurum_kodu_normalize(kurum_kodu)
        self.okul = okul or ""
        self._dur = threading.Event()
        self._t: threading.Thread | None = None

    def baslat(self):
        if self._t and self._t.is_alive():
            return
        self._dur.clear()
        self._t = threading.Thread(target=self._dongu, name="dose-kesif", daemon=True)
        self._t.start()

    def durdur(self):
        self._dur.set()

    def _yanit(self) -> dict:
        return {"uygulama": "DOSE", "port": self.port, "https": self.https,
                "kurum_kodu": self.kurum_kodu, "ad": self.okul}

    def _dongu(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("0.0.0.0", KESIF_PORT))
            sock.settimeout(1.0)
        except OSError:
            sock.close()
            return
        son_yayin = 0.0
        try:
            while not self._dur.is_set():
                simdi = time.monotonic()
                if simdi - son_yayin >= YAYIN_ARALIK:
                    try:
                        sock.sendto(_paket(self._yanit()), ("255.255.255.255", KESIF_PORT))
                    except OSError:
                        pass
                    son_yayin = simdi
                try:
                    veri, adres = sock.recvfrom(2048)
                except socket.timeout:
                    continue
                except OSError:
                    break
                y = _coz(veri)
                if y and y.get("sorgu"):
                    try:
                        sock.sendto(_paket(self._yanit()), adres)
                    except OSError:
                        pass
        finally:
            sock.close()


def adres_coz(kurum_kodu: str = "", sunucu_adresi: str = "", lan: bool = True) -> str:
    """Kullanıcıya sunucu adresi sordurmadan mümkün olduğunca adresi bulur."""
    elle = (sunucu_adresi or "").strip()
    if elle:
        return elle
    if lan:
        bulunan = lan_kesfet(kurum_kodu)
        if bulunan:
            return bulunan
    try:
        from . import guncelleme
        uzak = guncelleme.uzak_surum()
        if uzak and uzak.gecit:
            return uzak.gecit.strip()
    except Exception:
        pass
    try:
        return ag.mobil_adres_coz(kurum_kodu=kurum_kodu, sunucu_adresi="")
    except ValueError:
        pass
    raise ValueError(
        "Sunucu otomatik bulunamadı. Aynı Wi-Fi'de DÖSE Mobil Sunucu açık olsun "
        "veya Gelişmiş ayarlardan adresi yazın. Barındırmada satıcı GitHub surum.json "
        "içine 'gecit' adresini koyabilir; böylece adres yazmanız gerekmez."
    )
