"""Satıcı lisans aracının imzalı lisans ve satış kaydı üretimi."""
import csv
import contextlib
import io
import sys
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from dose import lisans
from satici import lisans_uret


class LisansUretici(unittest.TestCase):
    def _anahtar_kur(self, klasor: Path) -> str:
        private_key = Ed25519PrivateKey.generate()
        ozel_yol = klasor / "ozel_anahtar.pem"
        ozel_yol.write_bytes(private_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        acik = lisans._b64(private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        return acik

    def test_lisans_uretici_imzali_lisans_ve_satis_kaydi_olusturur(self):
        with tempfile.TemporaryDirectory() as temp:
            klasor = Path(temp)
            acik = self._anahtar_kur(klasor)
            ozel_yol = klasor / "ozel_anahtar.pem"

            with (mock.patch.object(lisans_uret, "OZEL", ozel_yol),
                  mock.patch.object(lisans_uret, "KAYIT", klasor / "lisanslar.csv"),
                  mock.patch.object(lisans_uret, "LIC_KLASORU", klasor / "lisanslar"),
                  mock.patch.object(lisans, "ACIK_ANAHTAR", acik)):
                anahtar, dosya = lisans_uret.lisans_uret(
                    " Derik MTAL ", "765432", "1", date.today() + timedelta(days=365), Decimal("2500"),
                    "F-100", "Satın alma", "test")

                veri = lisans.coz(anahtar)
                self.assertEqual((veri.okul, veri.kurum_kodu, veri.tur), ("Derik MTAL", "765432", "1 yıl"))
                self.assertTrue(dosya.is_file())
                self.assertEqual(dosya.read_text(encoding="utf-8").strip(), anahtar)
                with (klasor / "lisanslar.csv").open(encoding="utf-8-sig", newline="") as f:
                    kayit = next(csv.DictReader(f, delimiter=";"))
                self.assertEqual((kayit["no"], kayit["fatura_no"], kayit["ucret"]),
                                 (veri.no, "F-100", "2500.00"))

    def test_bat_baslaticisi_icin_argsiz_kullanim_interaktiftir(self):
        with tempfile.TemporaryDirectory() as temp:
            klasor = Path(temp)
            acik = self._anahtar_kur(klasor)
            cevaplar = ["Derik MTAL", "765432", "0", "1250", "F-200", "Satın alma", "test"]
            cikti = io.StringIO()
            with (mock.patch.object(lisans_uret, "OZEL", klasor / "ozel_anahtar.pem"),
                  mock.patch.object(lisans_uret, "KAYIT", klasor / "lisanslar.csv"),
                  mock.patch.object(lisans_uret, "LIC_KLASORU", klasor / "lisanslar"),
                  mock.patch.object(lisans, "ACIK_ANAHTAR", acik),
                  mock.patch.object(sys, "argv", ["lisans_uret.py"]),
                  mock.patch("builtins.input", side_effect=cevaplar),
                  contextlib.redirect_stdout(cikti)):
                self.assertEqual(lisans_uret.main(), 0)
            self.assertIn("Lisans üretildi:", cikti.getvalue())
            self.assertTrue((klasor / "lisanslar.csv").is_file())

    def test_yil_ekle_artik_yili_guvenli_hesaplar(self):
        self.assertEqual(lisans_uret.yil_ekle(date(2024, 2, 29), 1), date(2025, 2, 28))


if __name__ == "__main__":
    unittest.main()
