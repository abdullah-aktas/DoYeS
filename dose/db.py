"""Veritabanı katmanı: yerel SQLite dosyası veya merkezi PostgreSQL sunucusu (çok kullanıcılı)."""
import contextlib
import functools
import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path

from . import baglanti, mevzuat
from .yollar import VERITABANI, YEDEKLER

SEMA = """
CREATE TABLE IF NOT EXISTS ayar (
    anahtar TEXT PRIMARY KEY,
    deger TEXT
);
CREATE TABLE IF NOT EXISTS kurum (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    okul_adi TEXT, isletme_adi TEXT, il TEXT, ilce TEXT, adres TEXT, telefon TEXT, eposta TEXT,
    kurum_kodu TEXT, vergi_dairesi TEXT, vkn TEXT, banka TEXT, iban TEXT,
    harcama_yetkilisi TEXT, gerceklestirme_gorevlisi TEXT, sayman TEXT,
    buyuksehir INTEGER DEFAULT 0, tahsis_sermaye REAL DEFAULT 0, odenmis_sermaye REAL DEFAULT 0,
    yuz_yuze_egitim INTEGER DEFAULT 1, evrak_kodu TEXT
);
CREATE TABLE IF NOT EXISTS parametre (
    yil INTEGER, anahtar TEXT, deger TEXT,
    PRIMARY KEY (yil, anahtar)
);
CREATE TABLE IF NOT EXISTS kullanici (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kullanici_adi TEXT UNIQUE NOT NULL, ad_soyad TEXT, rol TEXT NOT NULL,
    sifre_hash TEXT NOT NULL, tuz TEXT NOT NULL, aktif INTEGER DEFAULT 1, sifre_degismeli INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS islem_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zaman TEXT, kullanici TEXT, islem TEXT, tablo TEXT, kayit_id INTEGER, detay TEXT
);
CREATE TABLE IF NOT EXISTS mobil_oturum (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_ozet TEXT UNIQUE NOT NULL, kullanici_id INTEGER NOT NULL, cihaz TEXT, ip TEXT,
    olusturma TEXT, son_kullanim TEXT, bitis TEXT, aktif INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sayac (
    tur TEXT, yil INTEGER, son INTEGER DEFAULT 0, PRIMARY KEY (tur, yil)
);
CREATE TABLE IF NOT EXISTS bolum (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kod TEXT, ad TEXT NOT NULL, alan TEXT, utp_yontemi TEXT, aktif INTEGER DEFAULT 1, aciklama TEXT
);
CREATE TABLE IF NOT EXISTS personel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sicil_no TEXT, tckn TEXT, ad_soyad TEXT NOT NULL, kadro_unvani TEXT,
    hizmet_sinifi TEXT, dose_gorevi TEXT, unvan_grubu INTEGER DEFAULT 3, bolum_id INTEGER,
    istihdam TEXT DEFAULT '657 s. DMK', iban TEXT, telefon TEXT, eposta TEXT,
    aktif INTEGER DEFAULT 1, notlar TEXT
);
CREATE TABLE IF NOT EXISTS ogrenci (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    okul_no TEXT, tckn TEXT, ad_soyad TEXT NOT NULL, dogum_tarihi TEXT, sinif TEXT, bolum_id INTEGER,
    veli_adi TEXT, veli_telefon TEXT, veli_muvafakat INTEGER DEFAULT 0, muvafakat_tarihi TEXT,
    iban TEXT, aktif INTEGER DEFAULT 1, notlar TEXT
);
CREATE TABLE IF NOT EXISTS cari (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kod TEXT, tur TEXT, unvan TEXT NOT NULL, kamu_kurumu INTEGER DEFAULT 0,
    vergi_dairesi TEXT, vkn_tckn TEXT, telefon TEXT, eposta TEXT, adres TEXT, iban TEXT, notlar TEXT,
    aktif INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS urun (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kod TEXT, ad TEXT NOT NULL, tur TEXT, birim TEXT, bolum_id INTEGER, kdv_orani REAL DEFAULT 0.20,
    satis_fiyati REAL DEFAULT 0, kar_orani REAL DEFAULT 0.10, ucret_esasi TEXT, mamul_malzeme_id INTEGER,
    aktif INTEGER DEFAULT 1, aciklama TEXT
);
CREATE TABLE IF NOT EXISTS maliyet_kalem (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    urun_id INTEGER NOT NULL, kalem_turu TEXT, aciklama TEXT, malzeme_id INTEGER,
    miktar REAL DEFAULT 1, birim_fiyat REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS fiyat_tespit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    urun_id INTEGER, tarih TEXT, birim_maliyet REAL, kar_orani REAL, satis_fiyati REAL, kdv_orani REAL,
    kdv_dahil_fiyat REAL, piyasa_arastirmasi TEXT, karar_no TEXT, aciklama TEXT
);
CREATE TABLE IF NOT EXISTS malzeme (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kod TEXT, ad TEXT NOT NULL, tur TEXT, birim TEXT, kdv_orani REAL DEFAULT 0.20,
    kritik_stok REAL DEFAULT 0, aktif INTEGER DEFAULT 1, aciklama TEXT
);
CREATE TABLE IF NOT EXISTS stok_hareket (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarih TEXT, malzeme_id INTEGER, yon TEXT, miktar REAL, birim_fiyat REAL DEFAULT 0,
    kaynak TEXT, kaynak_id INTEGER, siparis_id INTEGER, aciklama TEXT
);
CREATE TABLE IF NOT EXISTS siparis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    siparis_no TEXT, tarih TEXT, cari_id INTEGER, bolum_id INTEGER, konu TEXT, ucret_esasi TEXT,
    sozlesme_bedeli REAL DEFAULT 0, kdv_orani REAL DEFAULT 0.20, pesinat REAL DEFAULT 0,
    baslama_tarihi TEXT, teslim_tarihi TEXT, kabul_tarihi TEXT, durum TEXT,
    ogrenci_uygulamasi INTEGER DEFAULT 1, malzeme_musteriden INTEGER DEFAULT 0,
    kar_orani REAL, faaliyet_orani REAL, malzeme_maliyeti REAL DEFAULT 0,
    iscilik_tutari REAL DEFAULT 0, ogrenci_hakki_orani REAL,
    sozlesme_suresi_ay INTEGER DEFAULT 0, bakanlik_izni INTEGER DEFAULT 0, aciklama TEXT
);
CREATE TABLE IF NOT EXISTS siparis_kalem (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    siparis_id INTEGER NOT NULL, urun_id INTEGER, aciklama TEXT, miktar REAL DEFAULT 1, birim TEXT,
    birim_fiyat REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS siparis_gorevli (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    siparis_id INTEGER NOT NULL, kisi_turu TEXT, kisi_id INTEGER, gorev TEXT
);
CREATE TABLE IF NOT EXISTS siparis_is_plani (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    siparis_id INTEGER NOT NULL, sira INTEGER DEFAULT 1,
    kalem TEXT NOT NULL, aciklama TEXT, birim TEXT, miktar REAL DEFAULT 1,
    tahmini_saat REAL DEFAULT 0, notlar TEXT
);
CREATE TABLE IF NOT EXISTS fatura (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tur TEXT NOT NULL, belge_turu TEXT, belge_no TEXT, tarih TEXT, cari_id INTEGER, siparis_id INTEGER,
    aciklama TEXT, matrah REAL DEFAULT 0, kdv REAL DEFAULT 0, tevkifat TEXT DEFAULT 'Yok',
    tevkif_kdv REAL DEFAULT 0, stopaj_turu TEXT DEFAULT 'Yok', stopaj_orani REAL DEFAULT 0, stopaj REAL DEFAULT 0,
    genel_toplam REAL DEFAULT 0, net_tutar REAL DEFAULT 0, temin_usulu TEXT, gider_turu TEXT,
    avans_mahsup REAL DEFAULT 0, iptal INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS fatura_kalem (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fatura_id INTEGER NOT NULL, urun_id INTEGER, malzeme_id INTEGER, aciklama TEXT,
    miktar REAL DEFAULT 1, birim TEXT, birim_fiyat REAL DEFAULT 0, kdv_orani REAL DEFAULT 0.20,
    tutar REAL DEFAULT 0, kdv REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS kasa_banka (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarih TEXT, hesap TEXT, yon TEXT, tur TEXT, tutar REAL DEFAULT 0, hasilat_tutari REAL DEFAULT 0,
    cari_id INTEGER, fatura_id INTEGER, siparis_id INTEGER, belge_no TEXT, aciklama TEXT,
    kaynak TEXT, kaynak_id INTEGER
);
CREATE TABLE IF NOT EXISTS parca_basi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yil INTEGER, ay INTEGER, siparis_id INTEGER, kabul_edilen_iscilik REAL DEFAULT 0,
    ogrenci_orani REAL DEFAULT 0.30, durum TEXT DEFAULT 'Taslak', onay_tarihi TEXT, aciklama TEXT
);
CREATE TABLE IF NOT EXISTS parca_basi_satir (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parca_basi_id INTEGER NOT NULL, kisi_turu TEXT, kisi_id INTEGER, katki REAL DEFAULT 0,
    hesaplanan REAL DEFAULT 0, brut REAL DEFAULT 0, tavan_asimi REAL DEFAULT 0,
    onceki_kumulatif REAL DEFAULT 0, gelir_vergisi REAL DEFAULT 0, damga_vergisi REAL DEFAULT 0,
    sgk REAL DEFAULT 0, net REAL DEFAULT 0, puantaj TEXT
);
CREATE TABLE IF NOT EXISTS fazla_calisma (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yil INTEGER, ay INTEGER, personel_id INTEGER, siparis_id INTEGER, saat REAL DEFAULT 0,
    saat_ucreti REAL DEFAULT 0, brut REAL DEFAULT 0, onceki_kumulatif REAL DEFAULT 0,
    gelir_vergisi REAL DEFAULT 0, damga_vergisi REAL DEFAULT 0, net REAL DEFAULT 0,
    durum TEXT DEFAULT 'Taslak', aciklama TEXT, puantaj TEXT
);
CREATE TABLE IF NOT EXISTS hazine_payi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yil INTEGER, ay INTEGER, tahsil_edilen REAL DEFAULT 0, oran REAL, tutar REAL DEFAULT 0,
    bildirim_tarihi TEXT, odeme_tarihi TEXT, durum TEXT DEFAULT 'Hesaplandı', aciklama TEXT,
    UNIQUE (yil, ay)
);
CREATE TABLE IF NOT EXISTS yil_sonu (
    yil INTEGER PRIMARY KEY,
    toplam_gelir REAL, toplam_gider REAL, donem_kari REAL, faiz_duzeltme REAL DEFAULT 0,
    utp_orani REAL, dagitima_esas REAL, dagitilan_utp REAL, sermaye_payi REAL, merkez_payi REAL,
    shcek REAL, yontem TEXT, durum TEXT DEFAULT 'Taslak', aciklama TEXT
);
CREATE TABLE IF NOT EXISTS utp_kisi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yil INTEGER, personel_id INTEGER, fiili_gun REAL DEFAULT 0, fazla_calisma_saat REAL DEFAULT 0,
    katki_orani REAL DEFAULT 0, takdir_orani REAL DEFAULT 0, haric INTEGER DEFAULT 0, haric_neden TEXT,
    idari_pay REAL DEFAULT 0, takdir_pay REAL DEFAULT 0, bolum_pay REAL DEFAULT 0, hesaplanan REAL DEFAULT 0,
    tavan_asimi REAL DEFAULT 0, brut REAL DEFAULT 0, onceki_kumulatif REAL DEFAULT 0,
    gelir_vergisi REAL DEFAULT 0, damga_vergisi REAL DEFAULT 0, net REAL DEFAULT 0,
    diger_isletme_utp REAL DEFAULT 0,
    UNIQUE (yil, personel_id)
);
CREATE TABLE IF NOT EXISTS hesap_plani (
    kod TEXT PRIMARY KEY, ad TEXT
);
CREATE TABLE IF NOT EXISTS yevmiye (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fis_no TEXT, tarih TEXT, aciklama TEXT, kaynak TEXT, kaynak_id INTEGER
);
CREATE TABLE IF NOT EXISTS yevmiye_satir (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yevmiye_id INTEGER NOT NULL, hesap_kodu TEXT, aciklama TEXT, borc REAL DEFAULT 0, alacak REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS resmi_yazi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarih TEXT, sayi TEXT, konu TEXT, muhatap TEXT, ilgi TEXT, metin TEXT, imza1 TEXT, imza2 TEXT
);
CREATE TABLE IF NOT EXISTS onay_durum (
    belge_turu TEXT NOT NULL, belge_id INTEGER NOT NULL, asama INTEGER DEFAULT 0, durum TEXT DEFAULT 'Hazırlanıyor',
    bolum_id INTEGER, hazirlayan TEXT, guncelleme TEXT,
    PRIMARY KEY (belge_turu, belge_id)
);
CREATE TABLE IF NOT EXISTS onay_kaydi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    belge_turu TEXT, belge_id INTEGER, asama INTEGER, asama_adi TEXT, karar TEXT,
    kullanici TEXT, ad_soyad TEXT, rol TEXT, zaman TEXT, aciklama TEXT
);
CREATE INDEX IF NOT EXISTS ix_onay_kaydi ON onay_kaydi(belge_turu, belge_id);
CREATE INDEX IF NOT EXISTS ix_fatura_tarih ON fatura(tarih);
CREATE INDEX IF NOT EXISTS ix_kasa_tarih ON kasa_banka(tarih);
CREATE INDEX IF NOT EXISTS ix_yev_kaynak ON yevmiye(kaynak, kaynak_id);
CREATE INDEX IF NOT EXISTS ix_stok_malzeme ON stok_hareket(malzeme_id);
CREATE INDEX IF NOT EXISTS ix_islem_log_kayit ON islem_log(tablo, kayit_id);
"""

GOCLER = [
    ("utp_kisi", "diger_isletme_utp", "REAL DEFAULT 0"),
    ("fatura", "avans_mahsup", "REAL DEFAULT 0"),
    ("kullanici", "personel_id", "INTEGER"),
    ("kullanici", "bolum_id", "INTEGER"),
    ("kullanici", "son_giris", "TEXT"),
    ("parca_basi_satir", "puantaj", "TEXT"),
    ("fazla_calisma", "puantaj", "TEXT"),
    ("fatura", "iskonto", "REAL DEFAULT 0"),
    ("fatura_kalem", "iskonto_orani", "REAL DEFAULT 0"),
    ("fatura_kalem", "iskonto", "REAL DEFAULT 0"),
    ("siparis_kalem", "iskonto_orani", "REAL DEFAULT 0"),
    ("siparis_kalem", "iskonto", "REAL DEFAULT 0"),
    ("siparis", "talep_sayi", "TEXT"),
    ("siparis", "talep_tarih", "TEXT"),
    ("siparis", "talep_kurum", "TEXT"),
    ("siparis", "talep_ilgi", "TEXT"),
    ("siparis", "kesif_tarih", "TEXT"),
    ("siparis", "kesif_ozet", "TEXT"),
    ("siparis", "proforma_no", "TEXT"),
    ("siparis", "proforma_tarih", "TEXT"),
    ("siparis", "proforma_gecerlilik_gun", "INTEGER DEFAULT 30"),
    ("islem_log", "rol", "TEXT"),
    ("islem_log", "ad_soyad", "TEXT"),
    ("islem_log", "bilgisayar", "TEXT"),
    ("islem_log", "istemci", "TEXT"),
    ("islem_log", "oturum", "TEXT"),
    ("islem_log", "eski", "TEXT"),
    ("islem_log", "yeni", "TEXT"),
]

# İşlem kaydında değeri yazılmayan kolonlar
GIZLI_KOLONLAR = {"sifre_hash", "tuz"}
# Başka bilgisayardaki ekranların yenilenmesini gerektirmeyen işlem kaydı türleri
YENILEME_GEREKTIRMEYEN = ("Oturum açma", "Oturum kapatma", "Hata", "Yedekleme", "Başarısız giriş")

TABLO_ADLARI = {
    "kurum": "kurum bilgileri", "parametre": "parametreler", "kullanici": "kullanıcı", "bolum": "bölüm",
    "personel": "personel", "ogrenci": "öğrenci", "cari": "cari hesap", "urun": "ürün", "maliyet_kalem": "maliyet",
    "fiyat_tespit": "fiyat tespiti", "malzeme": "malzeme", "stok_hareket": "stok hareketi",     "siparis": "sipariş", "siparis_is_plani": "iş planı",
    "fatura": "fatura", "kasa_banka": "kasa/banka", "parca_basi": "parça başı bordrosu",
    "fazla_calisma": "fazla çalışma", "hazine_payi": "hazine payı", "yil_sonu": "yıl sonu dağıtımı",
    "utp_kisi": "ÜTP", "yevmiye": "yevmiye", "resmi_yazi": "resmi yazı", "onay_durum": "onay",
}


class KayitCakismasi(RuntimeError):
    """Kayıt ekranda açıkken başka bir kullanıcı tarafından değiştirildi veya silindi."""


def _json(veri: dict | None) -> str | None:
    if not veri:
        return None
    return json.dumps({k: ("***" if k in GIZLI_KOLONLAR else v) for k, v in veri.items()}, ensure_ascii=False, default=str)


def _esit(a, b) -> bool:
    if a == b:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) < 1e-9
    return (a in (None, "")) and (b in (None, ""))


def sifre_hashle(sifre: str, tuz: str | None = None) -> tuple[str, str]:
    tuz = tuz or os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", sifre.encode("utf-8"), bytes.fromhex(tuz), 120_000).hex()
    return h, tuz


TABLOLAR = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SEMA)
ID_OLMAYAN = {"ayar", "parametre", "sayac", "hesap_plani", "yil_sonu", "onay_durum"}
BENZERSIZ = {"ayar": ["anahtar"], "parametre": ["yil", "anahtar"], "sayac": ["tur", "yil"], "hesap_plani": ["kod"],
             "yil_sonu": ["yil"], "hazine_payi": ["yil", "ay"], "utp_kisi": ["yil", "personel_id"],
             "onay_durum": ["belge_turu", "belge_id"], "kurum": ["id"]}


def _duz(params):
    return list(params) if params else []


# Lisans süresi bitince (salt okunur) de yazılabilen tablolar: oturum, şifre, lisans ve işlem kaydı
SERBEST_TABLOLAR = {"ayar", "islem_log", "kullanici", "mobil_oturum"}


@functools.lru_cache(maxsize=4096)
def _yazilan_tablo(sql: str) -> str | None:
    m = re.match(r"\s*(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|UPDATE|DELETE\s+FROM)\s+(\w+)", sql, re.I)
    if m:
        return m.group(1).lower()
    if re.match(r"\s*(?:CREATE|ALTER|DROP)\b", sql, re.I):
        return "?"
    return None


def _yazma_denetle(motor, sql: str):
    if motor.salt_okunur:
        tablo = _yazilan_tablo(sql)
        if tablo is not None and tablo not in SERBEST_TABLOLAR:
            from .lisans import SaltOkunurHata
            raise SaltOkunurHata("Lisans veya deneme süresi dolduğu için program salt okunur çalışıyor; kayıt eklenemez "
                                 "ve değiştirilemez. Lisans girmek için giriş ekranındaki 'Lisans…' düğmesini kullanın.")


# ---------------------------------------------------------------- SQLite
class SqliteMotor:
    tur = "yerel"
    salt_okunur = False

    def __init__(self, yol: Path):
        self.yol = Path(yol)
        self.con = sqlite3.connect(str(self.yol), timeout=20, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")

    def calistir(self, sql, params=()):
        _yazma_denetle(self, sql)
        return self.con.execute(sql, _duz(params))

    def coklu(self, sql, satirlar):
        _yazma_denetle(self, sql)
        self.con.executemany(sql, satirlar)

    def sema_kur(self, sema: str):
        self.con.executescript(sema)

    def ekle_id(self, sql, params) -> int:
        return self.calistir(sql, params).lastrowid

    def commit(self):
        self.con.commit()

    def rollback(self):
        self.con.rollback()

    def kapat(self):
        self.con.close()

    def kolonlar(self, tablo) -> list[str]:
        return [r[1] for r in self.con.execute(f"PRAGMA table_info({tablo})")]

    def sayaclari_esitle(self):
        pass

    def aciklama(self) -> str:
        return f"Yerel veritabanı: {self.yol}"


# ---------------------------------------------------------------- PostgreSQL
def _pg_sema(sql: str) -> str:
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    return re.sub(r"\bREAL\b", "DOUBLE PRECISION", sql)


@functools.lru_cache(maxsize=4096)
def pg_cevir(sql: str) -> str:
    """SQLite sözdizimindeki sorguyu PostgreSQL'e uyarlar (yer tutucular, INSERT OR ..., LIKE)."""
    m = re.match(r"\s*INSERT\s+OR\s+(IGNORE|REPLACE)\s+INTO\s+(\w+)\s*\(([^)]*)\)", sql, re.I)
    ek = ""
    if m:
        tur, tablo, kolon = m.group(1).upper(), m.group(2), m.group(3)
        sql = f"INSERT INTO {tablo} ({kolon})" + sql[m.end():]
        if tur == "IGNORE":
            ek = " ON CONFLICT DO NOTHING"
        else:
            anahtar = BENZERSIZ[tablo]
            guncel = [k.strip() for k in kolon.split(",") if k.strip() not in anahtar]
            ek = f" ON CONFLICT ({', '.join(anahtar)}) DO " + (
                "UPDATE SET " + ", ".join(f"{k} = EXCLUDED.{k}" for k in guncel) if guncel else "NOTHING")
    sql = re.sub(r"\bIFNULL\(", "COALESCE(", sql, flags=re.I)
    sql = re.sub(r"\bLIKE\b", "ILIKE", sql)
    cikti, tirnak = [], False
    for ch in sql:
        if ch == "'":
            tirnak = not tirnak
            cikti.append(ch)
        elif ch == "%":
            cikti.append("%%")
        elif ch == "?" and not tirnak:
            cikti.append("%s")
        else:
            cikti.append(ch)
    return "".join(cikti).rstrip().rstrip(";") + ek


def _ilk_kazanir(cursor):
    """Aynı adlı kolonlarda SQLite gibi ilk değeri tutan sözlük satır üreticisi."""
    adlar = [c.name for c in cursor.description] if cursor.description else []

    def yap(degerler):
        d = {}
        for a, v in zip(adlar, degerler):
            if a not in d:
                d[a] = v
        return d
    return yap


class PostgresMotor:
    tur = "sunucu"
    salt_okunur = False

    def __init__(self, ayar):
        self.ayar = ayar
        self._baglan()

    def _baglan(self):
        import psycopg
        from psycopg.adapt import Dumper
        from psycopg.types.numeric import FloatLoader

        class SerbestTamsayi(Dumper):
            oid = 0  # tip belirtilmez; PostgreSQL bağlamdan çıkarır (SQLite'taki esnekliğe yakın)

            def dump(self, obj):
                return str(int(obj)).encode()

        class SerbestMantiksal(Dumper):
            oid = 0

            def dump(self, obj):
                return b"1" if obj else b"0"

        self._psycopg = psycopg
        self.con = psycopg.connect(**self.ayar.dsn(), autocommit=True, row_factory=_ilk_kazanir)
        self.con.adapters.register_dumper(int, SerbestTamsayi)
        self.con.adapters.register_dumper(bool, SerbestMantiksal)
        self.con.adapters.register_loader("numeric", FloatLoader)
        self.con.execute("SET TIME ZONE 'Europe/Istanbul'")
        self._islemde = False

    def calistir(self, sql, params=()):
        _yazma_denetle(self, sql)
        q = pg_cevir(sql)
        try:
            return self.con.execute(q, _duz(params))
        except self._psycopg.OperationalError:
            if not self._islemde and (self.con.closed or self.con.broken):
                self._baglan()
                return self.con.execute(q, _duz(params))
            raise

    def coklu(self, sql, satirlar):
        _yazma_denetle(self, sql)
        with self.con.cursor() as cur:
            cur.executemany(pg_cevir(sql), satirlar)

    def sema_kur(self, sema: str):
        for ifade in _pg_sema(sema).split(";"):
            if ifade.strip():
                self.con.execute(ifade)

    def ekle_id(self, sql, params) -> int:
        r = self.calistir(sql + " RETURNING id", params).fetchone()
        return r["id"]

    def commit(self):
        pass

    def rollback(self):
        pass

    def kapat(self):
        self.con.close()

    def kolonlar(self, tablo) -> list[str]:
        return [r["column_name"] for r in self.con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = %s "
            "ORDER BY ordinal_position", [tablo])]

    def sayaclari_esitle(self):
        for t in TABLOLAR:
            if t not in ID_OLMAYAN and t != "kurum":
                self.con.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE((SELECT MAX(id) FROM {t}), 0) + 1, false)")

    def aciklama(self) -> str:
        return f"Sunucu: {self.ayar.kullanici}@{self.ayar.sunucu}:{self.ayar.port}/{self.ayar.veritabani}"


# ---------------------------------------------------------------- ortak arayüz
class Veritabani:
    def __init__(self, kaynak=None):
        """kaynak: SQLite dosya yolu veya BaglantiAyari. Boşsa baglanti.json ayarları kullanılır."""
        if kaynak is None:
            kaynak = baglanti.oku()
        self.kaynak = kaynak
        self.kullanici = "sistem"
        self.rol = ""
        self.ad_soyad = ""
        self.istemci = "Masaüstü"
        self.bilgisayar = socket.gethostname()
        self.oturum = uuid.uuid4().hex[:16]
        self._acik_kayitlar: dict[tuple[str, object], int] = {}
        self._derinlik = 0
        self._salt_okunur = False
        self.baglan()

    def oturum_ac(self, k: dict, istemci: str | None = None, bilgisayar: str | None = None, oturum: str | None = None):
        """İşlem kaydına yazılacak kullanıcı kimliğini belirler."""
        self.kullanici = k.get("kullanici_adi") or "sistem"
        self.rol = k.get("rol") or ""
        self.ad_soyad = k.get("ad_soyad") or ""
        if istemci:
            self.istemci = istemci
        if bilgisayar:
            self.bilgisayar = bilgisayar
        if oturum:
            self.oturum = oturum

    @property
    def sunucu_mu(self) -> bool:
        return self.m.tur == "sunucu"

    @property
    def salt_okunur(self) -> bool:
        return self._salt_okunur

    @salt_okunur.setter
    def salt_okunur(self, deger: bool):
        self._salt_okunur = self.m.salt_okunur = bool(deger)

    @property
    def yol(self) -> Path | None:
        return getattr(self.m, "yol", None)

    def baglan(self):
        k = self.kaynak
        if isinstance(k, baglanti.BaglantiAyari):
            self.m = PostgresMotor(k) if k.sunucu_mu else SqliteMotor(VERITABANI)
        else:
            self.m = SqliteMotor(Path(k))
        self.m.sema_kur(SEMA)
        self._goc()
        self._ilk_kurulum()
        self.m.commit()
        self.m.salt_okunur = self._salt_okunur

    def kapat(self):
        self.m.kapat()

    def aciklama(self) -> str:
        return self.m.aciklama()

    def _goc(self):
        """Eski sürüm veritabanlarına sonradan eklenen kolonları ekler; eski rol adlarını günceller."""
        onbellek = {}
        for tablo, kolon, tanim in GOCLER:
            mevcut = onbellek.setdefault(tablo, set(self.m.kolonlar(tablo)))
            if kolon not in mevcut:
                tanim = _pg_sema(tanim) if self.sunucu_mu else tanim
                self.m.calistir(f"ALTER TABLE {tablo} ADD COLUMN {kolon} {tanim}")
        for eski, yeni in mevzuat.ESKI_ROLLER.items():
            self.m.calistir("UPDATE kullanici SET rol = ? WHERE rol = ?", (yeni, eski))

    # ------------------------------------------------------------ işlem (transaction)
    @contextlib.contextmanager
    def islem(self):
        """İç içe kullanılabilir; en dıştaki blok bitince toplu olarak kaydedilir, hata olursa geri alınır."""
        if self._derinlik:
            self._derinlik += 1
            try:
                yield
            finally:
                self._derinlik -= 1
            return
        self._derinlik = 1
        try:
            if self.sunucu_mu:
                self.m._islemde = True
                with self.m.con.transaction():
                    yield
            else:
                try:
                    yield
                    self.m.commit()
                except BaseException:
                    self.m.rollback()
                    raise
        finally:
            self._derinlik = 0
            if self.sunucu_mu:
                self.m._islemde = False

    def _commit(self):
        if not self._derinlik:
            self.m.commit()

    # ------------------------------------------------------------ temel sorgular
    def q(self, sql: str, params=()) -> list[dict]:
        return [dict(r) for r in self.m.calistir(sql, params).fetchall()]

    def q1(self, sql: str, params=()) -> dict | None:
        r = self.m.calistir(sql, params).fetchone()
        return dict(r) if r else None

    def deger(self, sql: str, params=(), varsayilan=0):
        r = self.m.calistir(sql, params).fetchone()
        if not r:
            return varsayilan
        v = next(iter(dict(r).values()), None)
        return varsayilan if v is None else v

    def ex(self, sql: str, params=()):
        cur = self.m.calistir(sql, params)
        self._commit()
        return cur

    def ekle(self, tablo: str, veri: dict, log=True) -> int:
        kolonlar = ", ".join(veri.keys())
        soru = ", ".join("?" for _ in veri)
        sql = f"INSERT INTO {tablo} ({kolonlar}) VALUES ({soru})"
        if self.sunucu_mu and tablo in ID_OLMAYAN:
            self.m.calistir(sql, list(veri.values()))
            yid = None
        else:
            yid = self.m.ekle_id(sql, list(veri.values()))
        self._commit()
        if log:
            self.log("Ekleme", tablo, yid, yeni=veri)
        return yid

    def guncelle(self, tablo: str, kayit_id, veri: dict, anahtar="id", log=True):
        if not veri:
            return
        self.cakisma_denetle(tablo, kayit_id)
        eski = self.q1(f"SELECT * FROM {tablo} WHERE {anahtar} = ?", (kayit_id,)) if log else None
        atama = ", ".join(f"{k} = ?" for k in veri)
        self.m.calistir(f"UPDATE {tablo} SET {atama} WHERE {anahtar} = ?", list(veri.values()) + [kayit_id])
        self._commit()
        if log:
            degisen = {k: v for k, v in veri.items() if eski is None or not _esit(eski.get(k), v)}
            self.log("Güncelleme", tablo, kayit_id, eski={k: eski.get(k) for k in degisen} if eski else None, yeni=degisen)

    def sil(self, tablo: str, kayit_id, anahtar="id", log=True):
        self.cakisma_denetle(tablo, kayit_id)
        eski = self.q1(f"SELECT * FROM {tablo} WHERE {anahtar} = ?", (kayit_id,)) if log else None
        self.m.calistir(f"DELETE FROM {tablo} WHERE {anahtar} = ?", (kayit_id,))
        self._commit()
        if log:
            self.log("Silme", tablo, kayit_id, eski=eski)

    def log(self, islem, tablo="", kayit_id=None, detay="", eski: dict | None = None, yeni: dict | None = None) -> None:
        zaman = "to_char(LOCALTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')" if self.sunucu_mu else "?"
        degerler = [self.kullanici, self.rol or None, self.ad_soyad or None, self.bilgisayar, self.istemci, self.oturum,
                    islem, tablo, kayit_id, detay, _json(eski), _json(yeni)]
        if not self.sunucu_mu:
            degerler.insert(0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.m.calistir(
            "INSERT INTO islem_log (zaman, kullanici, rol, ad_soyad, bilgisayar, istemci, oturum, islem, tablo, kayit_id, "
            f"detay, eski, yeni) VALUES ({zaman},?,?,?,?,?,?,?,?,?,?,?,?)", degerler)
        self._commit()

    # ------------------------------------------------------------ eşzamanlı çalışma
    def son_islem_no(self) -> int:
        return int(self.deger("SELECT MAX(id) FROM islem_log", (), 0) or 0)

    def kayit_ac(self, tablo: str, kayit_id):
        """Düzenleme ekranında açılan kaydı izlemeye alır; kaydederken başkası değiştirmişse KayitCakismasi verilir."""
        if kayit_id is not None:
            self._acik_kayitlar[(tablo, kayit_id)] = self.son_islem_no()

    def kayit_birak(self, tablo: str, kayit_id):
        self._acik_kayitlar.pop((tablo, kayit_id), None)

    @contextlib.contextmanager
    def kayit_duzenleme(self, tablo: str, kayit_id):
        self.kayit_ac(tablo, kayit_id)
        try:
            yield
        finally:
            self.kayit_birak(tablo, kayit_id)

    def baska_degisiklik(self, tablo: str, kayit_id, surum: int) -> dict | None:
        """surum numaralı işlemden sonra kayıtta başka bir oturumun yaptığı son değişiklik."""
        return self.q1("SELECT * FROM islem_log WHERE tablo = ? AND kayit_id = ? AND id > ? "
                       "AND (oturum IS NULL OR oturum != ?) ORDER BY id DESC LIMIT 1", (tablo, kayit_id, surum, self.oturum))

    def cakisma_denetle(self, tablo: str, kayit_id, surum: int | None = None):
        if surum is None:
            surum = self._acik_kayitlar.get((tablo, kayit_id))
        if surum is None:
            return
        r = self.baska_degisiklik(tablo, kayit_id, surum)
        if r:
            kim = r.get("ad_soyad") or r.get("kullanici") or "başka bir kullanıcı"
            rol = f" ({r['rol']})" if r.get("rol") else ""
            yer = f", {r['istemci'] or ''} {r['bilgisayar'] or ''}".rstrip() if r.get("bilgisayar") else ""
            ne = "silindi" if r.get("islem") == "Silme" else "değiştirildi"
            raise KayitCakismasi(
                f"Bu {TABLO_ADLARI.get(tablo, 'kayıt')} kaydı siz düzenlerken {kim}{rol} tarafından {r.get('zaman')} "
                f"tarihinde {ne}{yer}.\n\nOnun yaptığı değişikliğin üzerine yazılmaması için sizin değişikliğiniz "
                "kaydedilmedi. Pencereyi kapatıp kaydı yeniden açınız; güncel hâlini görerek değişikliğinizi tekrar yapınız.")

    def degisiklikler(self, son_no: int, sinir: int = 200) -> list[dict]:
        """son_no'dan sonra başka oturumlarda yapılan ve ekranların yenilenmesini gerektiren işlemler."""
        yer = ", ".join("?" for _ in YENILEME_GEREKTIRMEYEN)
        return self.q(f"SELECT id, zaman, kullanici, ad_soyad, rol, istemci, bilgisayar, islem, tablo, kayit_id FROM islem_log "
                      f"WHERE id > ? AND (oturum IS NULL OR oturum != ?) AND islem NOT IN ({yer}) ORDER BY id LIMIT ?",
                      (son_no, self.oturum, *YENILEME_GEREKTIRMEYEN, sinir))

    # ------------------------------------------------------------ ayarlar / parametreler
    def ayar(self, anahtar, varsayilan=None):
        r = self.q1("SELECT deger FROM ayar WHERE anahtar = ?", (anahtar,))
        return r["deger"] if r else varsayilan

    def ayar_yaz(self, anahtar, deger):
        self.ex("INSERT OR REPLACE INTO ayar (anahtar, deger) VALUES (?, ?)", (anahtar, str(deger)))

    def parametreler(self, yil: int) -> dict:
        """Yılın parametreleri; eksik olanlar en yakın önceki yıldan, o da yoksa varsayılandan alınır."""
        sonuc = mevzuat.varsayilan_parametreler()
        satirlar = self.q("SELECT yil, anahtar, deger FROM parametre WHERE yil <= ? ORDER BY yil", (yil,))
        if not satirlar:
            satirlar = self.q("SELECT yil, anahtar, deger FROM parametre ORDER BY yil")
        for s in satirlar:
            sonuc[s["anahtar"]] = s["deger"]
        for k, tanim in mevzuat.PARAMETRE_SOZLUK.items():
            tur = tanim[2]
            if tur in ("para", "oran", "sayi"):
                try:
                    sonuc[k] = float(sonuc[k])
                except (TypeError, ValueError):
                    sonuc[k] = float(tanim[3])
        try:
            sonuc["gv_tarifesi_ucret"] = json.loads(sonuc["gv_tarifesi_ucret"]) if isinstance(
                sonuc["gv_tarifesi_ucret"], str) else sonuc["gv_tarifesi_ucret"]
        except (TypeError, ValueError):
            sonuc["gv_tarifesi_ucret"] = json.loads(mevzuat.PARAMETRE_SOZLUK["gv_tarifesi_ucret"][3])
        return sonuc

    def parametre_yaz(self, yil: int, anahtar: str, deger):
        self.ex("INSERT OR REPLACE INTO parametre (yil, anahtar, deger) VALUES (?, ?, ?)", (yil, anahtar, str(deger)))

    # ------------------------------------------------------------ numaralandırma
    def sonraki_no(self, tur: str, yil: int, onek: str) -> str:
        with self.islem():
            self.m.calistir("INSERT OR IGNORE INTO sayac (tur, yil, son) VALUES (?, ?, 0)", (tur, yil))
            son = self.deger("UPDATE sayac SET son = son + 1 WHERE tur = ? AND yil = ? RETURNING son", (tur, yil))
        return f"{onek}-{yil}-{int(son):04d}"

    # ------------------------------------------------------------ kurum
    def kurum(self) -> dict:
        return self.q1("SELECT * FROM kurum WHERE id = 1") or {}

    # ------------------------------------------------------------ kullanıcılar
    def giris_dogrula(self, kullanici_adi: str, sifre: str) -> dict | None:
        k = self.q1("SELECT * FROM kullanici WHERE kullanici_adi = ? AND aktif = 1", (kullanici_adi,))
        if not k:
            return None
        h, _ = sifre_hashle(sifre, k["tuz"])
        return k if h == k["sifre_hash"] else None

    def sifre_degistir(self, kullanici_id: int, yeni: str):
        h, tuz = sifre_hashle(yeni)
        self.guncelle("kullanici", kullanici_id, {"sifre_hash": h, "tuz": tuz, "sifre_degismeli": 0})

    # ------------------------------------------------------------ ilk kurulum
    def _ilk_kurulum(self):
        with self.islem():
            if not self.q1("SELECT 1 x FROM kurum WHERE id = 1"):
                self.m.calistir("INSERT INTO kurum (id, okul_adi, isletme_adi) VALUES (1, ?, ?)",
                                ("............ Mesleki ve Teknik Anadolu Lisesi", "Döner Sermaye İşletmesi Müdürlüğü"))
            if not self.q1("SELECT 1 x FROM kullanici"):
                h, tuz = sifre_hashle("admin")
                self.m.calistir("INSERT INTO kullanici (kullanici_adi, ad_soyad, rol, sifre_hash, tuz, sifre_degismeli) "
                                "VALUES ('admin', 'Sistem Yöneticisi', ?, ?, ?, 1)", (mevzuat.ROL_SISTEM, h, tuz))
            mevcut = {r["kod"] for r in self.q("SELECT kod FROM hesap_plani")}
            eksik = [(kod, ad) for kod, ad in mevzuat.HESAP_PLANI if kod not in mevcut]
            if eksik:
                self.m.coklu("INSERT OR IGNORE INTO hesap_plani (kod, ad) VALUES (?, ?)", eksik)
            if not self.q1("SELECT 1 x FROM parametre"):
                yil = datetime.now().year
                self.m.coklu("INSERT OR IGNORE INTO parametre (yil, anahtar, deger) VALUES (?, ?, ?)",
                             [(yil, k, str(v)) for k, v in mevzuat.varsayilan_parametreler().items()])

    # ------------------------------------------------------------ yedekleme / aktarım
    def yedekle(self, hedef: Path | None = None) -> Path:
        """Veritabanının SQLite dosyası olarak yedeğini alır (sunucu kullanılıyorsa da yedek bu bilgisayara iner)."""
        hedef = Path(hedef) if hedef else YEDEKLER / f"dose_yedek_{datetime.now():%Y%m%d_%H%M%S}.db"
        if self.sunucu_mu:
            hedef.unlink(missing_ok=True)
            yedek = Veritabani(hedef)
            try:
                veri_kopyala(self, yedek)
            finally:
                yedek.kapat()
        else:
            yedek_con = sqlite3.connect(str(hedef))
            with yedek_con:
                self.m.con.backup(yedek_con)
            yedek_con.close()
        self.ayar_yaz("son_yedek", datetime.now().isoformat(timespec="seconds"))
        self.log("Yedekleme", detay=str(hedef))
        return hedef

    def geri_yukle(self, kaynak: Path):
        """SQLite yedek dosyasındaki verileri geri yükler. Sunucuda iken yerel verileri sunucuya aktarmak için de kullanılır."""
        kaynak = Path(kaynak)
        self.yedekle()
        if self.sunucu_mu:
            with tempfile.TemporaryDirectory() as gd:
                gecici = Path(gd) / "aktarim.db"
                shutil.copyfile(str(kaynak), str(gecici))
                kdb = Veritabani(gecici)
                try:
                    veri_kopyala(kdb, self)
                finally:
                    kdb.kapat()
        else:
            self.m.kapat()
            shutil.copyfile(str(kaynak), str(self.m.yol))
            self.baglan()
        self.log("Geri yükleme", detay=str(kaynak))


def _temizle(deger, tur: str | None):
    if tur in ("integer", "double precision", "bigint", "smallint", "numeric", "real"):
        if isinstance(deger, str):
            deger = deger.strip().replace(",", ".")
            if not deger:
                return None
            try:
                return float(deger) if tur not in ("integer", "bigint", "smallint") else int(float(deger))
            except ValueError:
                return None
    return deger


def veri_kopyala(kaynak: Veritabani, hedef: Veritabani):
    """Bütün tabloları kaynaktan hedefe kopyalar; hedefteki mevcut kayıtlar silinir."""
    with hedef.islem():
        for t in TABLOLAR:
            if hedef.sunucu_mu:
                turler = {r["column_name"]: r["data_type"] for r in hedef.q(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = ?", (t,))}
            else:
                turler = {}
            kk = set(kaynak.m.kolonlar(t))
            ortak = [k for k in hedef.m.kolonlar(t) if k in kk]
            hedef.m.calistir(f"DELETE FROM {t}")
            satirlar = kaynak.q(f"SELECT {', '.join(ortak)} FROM {t}")
            if satirlar:
                hedef.m.coklu(f"INSERT INTO {t} ({', '.join(ortak)}) VALUES ({', '.join('?' * len(ortak))})",
                              [[_temizle(s[k], turler.get(k)) for k in ortak] for s in satirlar])
        hedef.m.sayaclari_esitle()


def baglanti_dene(ayar: baglanti.BaglantiAyari) -> str | None:
    """Bağlantıyı dener; sorun yoksa None, varsa anlaşılır hata metni döner."""
    try:
        import psycopg
    except ImportError:
        return "PostgreSQL sürücüsü (psycopg) kurulu değil: pip install \"psycopg[binary]\""
    try:
        with psycopg.connect(**ayar.dsn()) as c:
            c.execute("SELECT 1")
        return None
    except Exception as e:
        return str(e).strip() or type(e).__name__


db: Veritabani | None = None
_tls = threading.local()


def baslat(kaynak=None) -> Veritabani:
    """kaynak: None (baglanti.json ayarı), SQLite dosya yolu veya BaglantiAyari."""
    global db
    from . import lisans
    yeni = Veritabani(kaynak)
    lisans.uygula(yeni)
    if db is not None:
        try:
            db.kapat()
        except Exception:
            pass
    db = yeni
    return db


def baglam_ayarla(veritabani: Veritabani | None):
    """İstek/iş parçacığı için geçici aktif veritabanı (çok okullu mobil geçit)."""
    _tls.db = veritabani


def al() -> Veritabani:
    aktif = getattr(_tls, "db", None)
    if aktif is not None:
        return aktif
    if db is None:
        return baslat()
    return db
