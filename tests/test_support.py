"""Shared test database setup."""
import os
from pathlib import Path

YIL = 2026


def test_kaynagi(klasor: Path):
    """Use a temporary SQLite file unless DOSE_TEST_PG explicitly selects a test PostgreSQL database."""
    tanim = os.environ.get("DOSE_TEST_PG")
    if not tanim:
        return klasor / "test.db"
    import psycopg
    from dose.baglanti import BaglantiAyari

    sunucu, port, kullanici, vt = tanim.split(":")
    ayar = BaglantiAyari(tur="sunucu", sunucu=sunucu, port=int(port), kullanici=kullanici,
                         veritabani=vt, ssl="disable")
    with psycopg.connect(host=sunucu, port=int(port), user=kullanici, dbname=vt, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE")
        c.execute("CREATE SCHEMA public")
    return ayar
