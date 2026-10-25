"""Supabase PostgreSQL kurulumu ve bağlantı yapılandırması."""
import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dose import baglanti  # noqa: E402
from dose.db import TABLOLAR  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class SupabaseAltyapisi(unittest.TestCase):
    def test_migration_tum_tablolari_ve_rls_kilidini_iceriyor(self):
        migration = (ROOT / "supabase" / "migrations" / "20261025000000_dose_schema.sql").read_text(
            encoding="utf-8")
        tablolar = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", migration))
        self.assertEqual(tablolar, set(TABLOLAR))
        self.assertIn("ENABLE ROW LEVEL SECURITY", migration)
        self.assertNotRegex(migration, r"CREATE POLICY\s+\w+\s+ON\s+public\.")

    def test_database_url_supabase_baglanti_ayarina_donusuyor(self):
        url = "postgresql://postgres.proje:guclu%40parola@aws-0-eu.pooler.supabase.com:5432/postgres?sslmode=require"
        with patch.dict(os.environ, {"DOSE_DATABASE_URL": url}):
            ayar = baglanti.oku()
        self.assertEqual((ayar.tur, ayar.sunucu, ayar.port, ayar.veritabani, ayar.kullanici),
                         ("sunucu", "aws-0-eu.pooler.supabase.com", 5432, "postgres",
                          "postgres.proje"))
        self.assertEqual((ayar.sifre, ayar.ssl), ("guclu@parola", "require"))

    def test_gecersiz_database_url_acik_hata_veriyor(self):
        with patch.dict(os.environ, {"DOSE_DATABASE_URL": "https://example.invalid"}):
            with self.assertRaisesRegex(ValueError, "PostgreSQL"):
                baglanti.oku()


if __name__ == "__main__":
    unittest.main()
