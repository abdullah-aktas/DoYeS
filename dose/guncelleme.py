"""GitHub üzerinden sürüm kontrolü ve güncelleme uyarısı.

Kaynak: https://raw.githubusercontent.com/abdullah-aktas/DoYeS/main/surum.json
Kullanıcılar yeni sürümü Releases / repo üzerinden indirir; program açılışta uyarır.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import SURUM

GITHUB_REPO = "abdullah-aktas/DoYeS"
SURUM_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/surum.json"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
REPO_URL = f"https://github.com/{GITHUB_REPO}"
ZAMAN_ASIMI = 8


@dataclass
class SurumBilgi:
    surum: str
    notlar: str = ""
    indir: str = RELEASES_URL
    repo: str = REPO_URL
    gecit: str = ""
    tarih: str = ""

    @property
    def yeni_var(self) -> bool:
        return _karsilastir(self.surum, SURUM) > 0


def _karsilastir(a: str, b: str) -> int:
    """a > b → 1; eşit → 0; a < b → -1."""
    def parcala(s):
        out = []
        for p in str(s or "0").strip().split("."):
            try:
                out.append(int("".join(c for c in p if c.isdigit()) or "0"))
            except ValueError:
                out.append(0)
        return out
    pa, pb = parcala(a), parcala(b)
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    return (pa > pb) - (pa < pb)


def uzak_surum(url: str = SURUM_URL) -> SurumBilgi | None:
    """GitHub'daki surum.json dosyasını okur; ağ yoksa None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"DOSE-Yonetim/{SURUM}", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=ZAMAN_ASIMI) as y:
            veri = json.loads(y.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None
    if not isinstance(veri, dict) or not veri.get("surum"):
        return None
    return SurumBilgi(
        surum=str(veri["surum"]).strip(),
        notlar=str(veri.get("notlar") or "").strip(),
        indir=str(veri.get("indir") or RELEASES_URL).strip(),
        repo=str(veri.get("repo") or REPO_URL).strip(),
        gecit=str(veri.get("gecit") or "").strip(),
        tarih=str(veri.get("tarih") or "").strip(),
    )


def kontrol_et() -> SurumBilgi | None:
    """Yeni sürüm varsa SurumBilgi, yoksa veya ağ hatasında None (güncel ise de None)."""
    b = uzak_surum()
    if b and b.yeni_var:
        return b
    return None
