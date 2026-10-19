"""Çok okullu mobil geçit: kurum koduna göre okul_<kod> PostgreSQL veritabanına bağlanır.

Satıcı barındırmasında tek bir DÖSE Mobil Sunucu süreci bütün okullara hizmet verir.
Telefonda yalnız kurum kodu + kullanıcı + şifre yeterlidir; veritabanı şifresi telefona gitmez.
"""
from __future__ import annotations

import threading
from pathlib import Path

from dose import ag, baglanti, db as dbm
from dose.baglanti import BaglantiAyari
from dose.lisans import kurum_kodu_normalize


class OkulHavuzu:
    """Kurum kodu → açık Veritabani bağlantısı. Aynı anda birden çok okul oturumu taşır."""

    def __init__(self, yapilandirma: dict | None = None):
        self.cfg = yapilandirma if yapilandirma is not None else ag.okullar_oku()
        if not self.cfg.get("sunucu"):
            raise RuntimeError(
                f"Çok okullu geçit için {ag.OKULLAR_DOSYASI} içinde 'sunucu' adresi olmalıdır. "
                "bkz. SATIS_REHBERI.md §3 ve §4."
            )
        self._db: dict[str, dbm.Veritabani] = {}
        self._kilitler: dict[str, threading.RLock] = {}
        self._genel = threading.RLock()
        # token_ozet → kurum_kodu (süreç belleği; yeniden başlatınca kullanıcılar yeniden girer)
        self.oturumlar: dict[str, str] = {}

    def kod_normalize(self, kod: str) -> str:
        k = kurum_kodu_normalize(kod)
        if not ag.kurum_kodu_gecerli(k):
            raise ValueError("Kurum kodu 5–8 rakam olmalıdır.")
        return k

    def ayar(self, kod: str) -> BaglantiAyari:
        kod = self.kod_normalize(kod)
        okullar = self.cfg.get("okullar") or {}
        bilgi = okullar.get(kod) or okullar.get(str(int(kod)))  # baştaki sıfır farkı
        if not bilgi or not bilgi.get("sifre"):
            raise KeyError(f"Kurum kodu {kod} geçitte tanımlı değil. Satıcıya başvurunuz.")
        vt = ag.kurum_db_adi(kod)
        kullanici = bilgi.get("kullanici") or vt
        return BaglantiAyari(
            tur="sunucu",
            sunucu=self.cfg["sunucu"],
            port=int(self.cfg.get("port") or 5432),
            veritabani=vt,
            kullanici=kullanici,
            sifre=bilgi["sifre"],
            ssl=self.cfg.get("ssl") or "require",
        )

    def kilit(self, kod: str) -> threading.RLock:
        kod = self.kod_normalize(kod)
        with self._genel:
            if kod not in self._kilitler:
                self._kilitler[kod] = threading.RLock()
            return self._kilitler[kod]

    def al(self, kod: str) -> dbm.Veritabani:
        kod = self.kod_normalize(kod)
        with self._genel:
            if kod in self._db:
                return self._db[kod]
        a = self.ayar(kod)
        # İlk açılışı okul kilidi altında yap (çift oluşturmayı önle)
        with self.kilit(kod):
            with self._genel:
                if kod in self._db:
                    return self._db[kod]
            vt = dbm.Veritabani(a)
            from dose import lisans
            lisans.uygula(vt)
            with self._genel:
                self._db[kod] = vt
            return vt

    def kayitli_mi(self, kod: str) -> bool:
        try:
            kod = self.kod_normalize(kod)
        except ValueError:
            return False
        okullar = self.cfg.get("okullar") or {}
        return kod in okullar or str(int(kod)) in okullar if kod.isdigit() else kod in okullar

    def okul_adi(self, kod: str) -> str:
        kod = self.kod_normalize(kod)
        okullar = self.cfg.get("okullar") or {}
        bilgi = okullar.get(kod) or okullar.get(str(int(kod)), {})
        return (bilgi or {}).get("ad") or f"Kurum {kod}"

    def kapat(self):
        with self._genel:
            for vt in self._db.values():
                try:
                    vt.kapat()
                except Exception:
                    pass
            self._db.clear()
            self.oturumlar.clear()


def okullar_ornek_yaz(hedef: Path | None = None):
    """İlk kurulum için örnek okullar.json şablonu."""
    yol = hedef or ag.OKULLAR_DOSYASI
    if yol.exists():
        return
    ornek = {
        "sunucu": "db.ornek.meb.k12.tr",
        "port": 5432,
        "ssl": "require",
        "okullar": {
            "765432": {"ad": "Örnek MTAL", "sifre": "okul_ekle.sh çıktısındaki şifre", "kullanici": "okul_765432"}
        },
    }
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(__import__("json").dumps(ornek, ensure_ascii=False, indent=2), encoding="utf-8")
