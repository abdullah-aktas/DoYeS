"""Supabase project endpoint. The publishable key is public by design; every rule is enforced by RLS and RPCs."""
import os

SUPABASE_URL = os.environ.get("DOSE_SUPABASE_URL", "https://bzirnfsgdswcwwutmwdi.supabase.co").rstrip("/")
SUPABASE_ANAHTAR = os.environ.get("DOSE_SUPABASE_ANAHTAR", "sb_publishable_CSADmKJ3hXm-9jCT7BIfZg_pecVOO5Y")
# E-posta doğrulama / şifre sıfırlama dönüşü (GitHub Pages; kendi domain gerekmez)
AUTH_DONUS = os.environ.get("DOSE_AUTH_DONUS", "https://abdullah-aktas.github.io/DoYeS/").rstrip("/") + "/"
YENILEME_ARALIGI = 5
