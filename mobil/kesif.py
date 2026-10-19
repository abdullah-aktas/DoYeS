"""Mobil istemci: LAN keşif + GitHub surum.json geçidi (dose paketinden bağımsız)."""
from __future__ import annotations

import json
import socket
import time
import urllib.request

KESIF_PORT = 8766
ONEK = "DOSE1"
SURUM_URL = "https://raw.githubusercontent.com/abdullah-aktas/DoYeS/main/surum.json"


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
    kod = "".join(str(kurum_kodu or "").split())
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
            if kod and y.get("kurum_kodu") and "".join(str(y["kurum_kodu"]).split()) != kod:
                continue
            port = int(y.get("port") or 8765)
            sema = "https" if y.get("https") else "http"
            host = y.get("host") or adres[0]
            return f"{sema}://{host}:{port}"
    finally:
        sock.close()
    return None


def github_gecit() -> str:
    try:
        req = urllib.request.Request(SURUM_URL, headers={"User-Agent": "DOSE-Mobil", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=6) as y:
            veri = json.loads(y.read().decode("utf-8"))
        return str(veri.get("gecit") or "").strip()
    except Exception:
        return ""


def github_surum() -> dict | None:
    try:
        req = urllib.request.Request(SURUM_URL, headers={"User-Agent": "DOSE-Mobil", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=6) as y:
            return json.loads(y.read().decode("utf-8"))
    except Exception:
        return None


def adres_coz(kurum_kodu: str = "", sunucu_adresi: str = "", varsayilan_gecit: str = "") -> str:
    if (sunucu_adresi or "").strip():
        return sunucu_adresi.strip()
    if (varsayilan_gecit or "").strip():
        return varsayilan_gecit.strip()
    lan = lan_kesfet(kurum_kodu)
    if lan:
        return lan
    g = github_gecit()
    if g:
        return g
    raise ValueError(
        "Sunucu otomatik bulunamadı. Mobil Sunucu aynı Wi-Fi'de açık olsun "
        "veya Gelişmiş ayarlardan adresi yazın."
    )
