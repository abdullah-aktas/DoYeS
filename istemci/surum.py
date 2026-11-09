"""İstemci sürüm sabiti — pyproject.toml ile aynı tutulur."""
from __future__ import annotations

SURUM = "1.8.0"


def surum_parcala(metin: str | None) -> tuple[int, int, int]:
    try:
        a, b, c = (metin or "0.0.0").strip().split(".")[:3]
        return int(a), int(b), int(c)
    except (TypeError, ValueError):
        return 0, 0, 0


def surum_eski(yerel: str | None, uzak: str | None) -> bool:
    """True if yerel < uzak."""
    return surum_parcala(yerel) < surum_parcala(uzak)
