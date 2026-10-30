"""DÖSE Yönetim mobil API'si (FastAPI).

Telefon ve web uygulaması veritabanına doğrudan bağlanmaz; bütün işlemler okulun sunucusunda çalışan bu servis üzerinden,
masaüstü programla aynı mevzuat denetimleri, rol yetkileri, bölüm kısıtları ve onay akışıyla yapılır. Her işlem işlem
kaydına kullanıcı, rol, cihaz ve "Mobil" kaynak bilgisiyle yazılır.
"""
from __future__ import annotations

import calendar
import base64
import binascii
import hashlib
import json
import math
import secrets
import sqlite3
import threading
import tempfile
import time
import zipfile
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from dose import SURUM
from dose import ag, belgeler, db as dbm, parca_basi
from dose import denetim_formu, dogrulama
from dose import (belge_sablonlari, excel, gosterge, izleme, kilavuz, lisans, maliyet, muhasebe, onay, raporlar,
                  uyum, yetki, yukumluluk, yil_sonu)
from dose import mevzuat as M
from dose.denetim import puantaj_coz
from dose.db import KayitCakismasi, sifre_hashle
from dose.hesap import (GUN_TURU_ADLARI, ay_azami_fazla_calisma, belge_toplami, gun_azami_saat, gun_turu,
                        kalem_hatalari, kalem_tutari, siparis_kaydi_tahsisi, esas_kurallari, para, yuvarla)
from dose.islemler import IslemHatasi, fc_hesapla, siparis_taslagi_kaydet
from dose.lisans import SaltOkunurHata, kurum_kodu_normalize
from dose.yollar import YEDEKLER

API_SURUMU = 2
OTURUM_SURESI = timedelta(hours=12)
AZAMI_HATALI_GIRIS, KILIT_SANIYE = 5, 300
LISANS_TAZELEME_SANIYE = 600
ZAMAN = "%Y-%m-%d %H:%M:%S"

# Çok okullu geçitte sunucu_main --coklu ile doldurulur; tek okulda None kalır.
_HAVUZ = None

# Masaüstü programdaki sayfa yetkileri mobil modüllere aynen uygulanır.
MOBIL_MODULLER = {
    "panel": "Gösterge Paneli",
    "onay": "Onay Bekleyenler",
    "siparis": "Siparişler / İş Emirleri",
    "fazla": "Fazla Çalışma Ücreti",
    "parca_basi": "Parça Başı Ücret",
    "stok": "Stok Durumu ve Hareketleri",
    "kasa": "Kasa / Banka",
    "satis": "Satış Faturaları",
    "alis": "Alış / Gider Belgeleri",
    "islem": "Yedekleme / İşlem Kaydı",
    "denetim": "Rehberlik ve Denetim Formu",
    "bolum": "Bölüm / Alan / Atölyeler",
    "personel": "Personel",
    "ogrenci": "Öğrenciler",
    "cari": "Cari Hesaplar",
    "malzeme": "Malzeme / Stok Kartları",
    "urun": "Ürün / Hizmet ve Maliyet",
    "parametre": "Mevzuat Parametreleri",
    "kurum": "Kurum ve Görevliler",
    "muhasebe": "Yevmiye / Mizan",
    "raporlar": "Raporlar",
    "yukumluluk": "Hazine Payı / SHÇEK",
    "vergi": "KDV / Muhtasar Özeti",
    "yapilacaklar": "Bugün Ne Yapmalıyım?",
    "kilavuz": "Nasıl Yaparım? (Adım Adım)",
    "rehber": "Mevzuat Rehberi",
    "uyum": "Mevzuat Uyum Denetimi",
    "kullanicilar": "Kullanıcılar",
    "yil_sonu": "Yıl Sonu Kârı ve ÜTP",
    "belgeler": "Resmi Yazılar / Belgeler",
}
FATURA_SAYFASI = {"Satış": "Satış Faturaları", "Alış": "Alış / Gider Belgeleri"}
GUNLER = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

# Field allowlists are shared with the Flet form API; table names and ordering are never client-controlled.
TANIM_ALANLARI = {
    "bolum": [
        ("kod", "Kod", "metin", False, []), ("ad", "Bölüm / atölye adı", "metin", True, []),
        ("alan", "Alan / dal", "metin", False, []),
        ("utp_yontemi", "ÜTP dağıtım yöntemi", "secim", True, M.UTP_BOLUM_YONTEMLERI),
        ("aktif", "Aktif", "bool", False, []), ("aciklama", "Açıklama", "cokmetin", False, []),
    ],
    "personel": [
        ("sicil_no", "Sicil / kurum no", "metin", False, []), ("tckn", "T.C. kimlik no", "metin", False, []),
        ("ad_soyad", "Adı soyadı", "metin", True, []), ("kadro_unvani", "Kadro unvanı / branş", "metin", False, []),
        ("hizmet_sinifi", "Hizmet sınıfı", "secim", True, M.HIZMET_SINIFLARI),
        ("dose_gorevi", "DÖSE görevi", "secim", True, M.DOSE_GOREVLERI),
        ("unvan_grubu", "Unvan puan grubu", "secim", False, [(k, v) for k, v in M.UNVAN_GRUPLARI.items()]),
        ("bolum_id", "Bölüm / atölye", "fk_bolum", False, []),
        ("istihdam", "İstihdam", "secim", False, ["657 s. DMK", "4857 s. İş Kanunu", "Sözleşmeli"]),
        ("iban", "IBAN", "metin", False, []), ("telefon", "Telefon", "metin", False, []),
        ("eposta", "E-posta", "metin", False, []), ("aktif", "Aktif", "bool", False, []),
        ("notlar", "Notlar", "cokmetin", False, []),
    ],
    "ogrenci": [
        ("okul_no", "Okul no", "metin", False, []), ("tckn", "T.C. kimlik no", "metin", False, []),
        ("ad_soyad", "Adı soyadı", "metin", True, []), ("dogum_tarihi", "Doğum tarihi", "tarih", False, []),
        ("sinif", "Sınıf / şube", "metin", False, []), ("bolum_id", "Alan / bölüm", "fk_bolum", False, []),
        ("veli_adi", "Veli adı soyadı", "metin", False, []), ("veli_telefon", "Veli telefon", "metin", False, []),
        ("veli_muvafakat", "Veli yazılı muvafakati alındı", "bool", False, []),
        ("muvafakat_tarihi", "Muvafakat tarihi", "tarih", False, []), ("iban", "IBAN", "metin", False, []),
        ("aktif", "Aktif", "bool", False, []), ("notlar", "Notlar", "cokmetin", False, []),
    ],
    "cari": [
        ("kod", "Cari kodu", "metin", False, []),
        ("tur", "Türü", "secim", True, M.CARI_TURLERI), ("unvan", "Unvan / adı soyadı", "metin", True, []),
        ("kamu_kurumu", "Kamu kurumu", "bool", False, []), ("vergi_dairesi", "Vergi dairesi", "metin", False, []),
        ("vkn_tckn", "VKN / T.C. kimlik no", "metin", False, []), ("telefon", "Telefon", "metin", False, []),
        ("eposta", "E-posta", "metin", False, []), ("adres", "Adres", "cokmetin", False, []),
        ("iban", "IBAN", "metin", False, []), ("aktif", "Aktif", "bool", False, []),
        ("notlar", "Notlar", "cokmetin", False, []),
    ],
    "malzeme": [
        ("kod", "Stok kodu", "metin", False, []), ("ad", "Malzeme adı", "metin", True, []),
        ("tur", "Türü", "secim", True, M.MALZEME_TURLERI), ("birim", "Birim", "secim", False, M.BIRIMLER),
        ("kdv_orani", "KDV oranı", "oran", False, []), ("kritik_stok", "Kritik stok miktarı", "ondalik", False, []),
        ("aktif", "Aktif", "bool", False, []), ("aciklama", "Açıklama", "cokmetin", False, []),
    ],
    "urun": [
        ("kod", "Kod", "metin", False, []), ("ad", "Ürün / hizmet adı", "metin", True, []),
        ("tur", "Türü", "secim", True, M.URUN_TURLERI), ("birim", "Birim", "secim", False, M.BIRIMLER),
        ("bolum_id", "Bölüm / atölye", "fk_bolum", False, []),
        ("ucret_esasi", "Ücret ödeme esası", "secim", False, M.UCRET_ESASLARI),
        ("kdv_orani", "KDV oranı", "oran", False, []), ("satis_fiyati", "Birim satış fiyatı", "para", False, []),
        ("kar_orani", "Hedef kâr oranı", "oran", False, []),
        ("mamul_malzeme_id", "Stoktaki mamul kartı", "fk_malzeme", False, []),
        ("aktif", "Aktif", "bool", False, []), ("aciklama", "Açıklama", "cokmetin", False, []),
    ],
}
TANIM_SIRALAMA = {"bolum": "ad", "personel": "aktif DESC, ad_soyad", "ogrenci": "aktif DESC, ad_soyad",
                  "cari": "unvan", "malzeme": "ad", "urun": "ad"}

KILIT = threading.RLock()
_hatali_girisler: dict[tuple[str, str], list[float]] = {}
_son_lisans = [0.0]


# ---------------------------------------------------------------- istek gövdeleri
class GirisIstegi(BaseModel):
    kullanici_adi: str
    sifre: str
    cihaz: str = ""
    kurum_kodu: str = ""  # aynı kurum kodu ile her yerden giriş; çok okullu geçitte zorunlu


class KesifIstegi(BaseModel):
    kurum_kodu: str


class LisansEtkinlestirmeIstegi(BaseModel):
    kurum_kodu: str = Field(min_length=5, max_length=8)
    anahtar: str = Field(min_length=20, max_length=8192)


class SifreIstegi(BaseModel):
    eski: str
    yeni: str


class KararIstegi(BaseModel):
    onay: bool
    aciklama: str = ""


class AciklamaIstegi(BaseModel):
    aciklama: str = ""


class TanimKaydiIstegi(BaseModel):
    degerler: dict[str, Any]


class TanimExcelIstegi(BaseModel):
    dosya_adi: str = Field(min_length=1, max_length=200)
    icerik: str = Field(min_length=4, max_length=7_000_000)


class MaliyetKalemiIstegi(BaseModel):
    kalem_turu: str
    aciklama: str = Field(default="", max_length=500)
    malzeme_id: int | None = None
    miktar: float = Field(ge=0, le=999999999999, allow_inf_nan=False)
    birim_fiyat: float = Field(ge=0, le=999999999999, allow_inf_nan=False)


class MaliyetIstegi(BaseModel):
    oto: bool = False
    hedef_fiyat: float = Field(ge=0, le=999999999999, allow_inf_nan=False)
    hedef_dahil: float | None = Field(default=None, ge=0, le=999999999999, allow_inf_nan=False)
    kar_orani: float = Field(ge=0, le=10, allow_inf_nan=False)
    kdv_orani: float = Field(ge=0, le=1, allow_inf_nan=False)
    piyasa: str = Field(default="", max_length=10000)
    kalemler: list[MaliyetKalemiIstegi] = Field(max_length=200)


class MuhasebeSatiri(BaseModel):
    hesap_kodu: str = Field(min_length=1, max_length=40)
    aciklama: str = Field(default="", max_length=500)
    borc: float = Field(default=0, ge=0, le=999999999999)
    alacak: float = Field(default=0, ge=0, le=999999999999)


class MuhasebeFisIstegi(BaseModel):
    tarih: str = Field(min_length=10, max_length=10)
    aciklama: str = Field(min_length=1, max_length=500)
    satirlar: list[MuhasebeSatiri] = Field(min_length=2, max_length=100)


class HesapPlaniIstegi(BaseModel):
    kod: str = Field(min_length=1, max_length=40)
    ad: str = Field(min_length=1, max_length=200)


class HazineHesapIstegi(BaseModel):
    yil: int = Field(ge=2000, le=2200)
    ay: int | None = Field(default=None, ge=1, le=12)


class YukumlulukOdemeIstegi(BaseModel):
    tur: str = Field(pattern="^(hazine|shcek|merkez)$")
    yil: int = Field(ge=2000, le=2200)
    ay: int | None = Field(default=None, ge=1, le=12)


class YilSonuKisiIstegi(BaseModel):
    personel_id: int = Field(gt=0)
    unvan_grubu: int = Field(default=5, ge=1, le=5)
    fiili_gun: float = Field(default=0, ge=0, le=366, allow_inf_nan=False)
    fazla_calisma_saat: float = Field(default=0, ge=0, le=10000, allow_inf_nan=False)
    katki_orani: float = Field(default=0, ge=0, le=100, allow_inf_nan=False)
    takdir_orani: float = Field(default=0, ge=0, le=100, allow_inf_nan=False)
    haric: bool = False
    haric_neden: str = Field(default="", max_length=500)
    diger_isletme_utp: float = Field(default=0, ge=0, le=999999999999, allow_inf_nan=False)
    onceki_kumulatif: float = Field(default=0, ge=0, le=999999999999, allow_inf_nan=False)


class YilSonuIstegi(BaseModel):
    donem_kari: float = Field(ge=-999999999999, le=999999999999, allow_inf_nan=False)
    faiz_duzeltme: float = Field(default=0, ge=0, le=999999999999, allow_inf_nan=False)
    utp_orani: float = Field(ge=0, le=1, allow_inf_nan=False)
    kisiler: list[YilSonuKisiIstegi] = Field(max_length=1000)


class ResmiYaziIstegi(BaseModel):
    tarih: str = Field(min_length=10, max_length=10)
    sayi: str = Field(default="", max_length=100)
    konu: str = Field(min_length=1, max_length=300)
    muhatap: str = Field(default="", max_length=500)
    ilgi: str = Field(default="", max_length=2000)
    metin: str = Field(min_length=1, max_length=20000)
    imza1: str = Field(default="", max_length=500)
    imza2: str = Field(default="", max_length=500)


class MuvafakatIstegi(BaseModel):
    ogrenci_idler: list[int] = Field(min_length=1, max_length=500)


class KullaniciIstegi(BaseModel):
    kullanici_adi: str = Field(min_length=3, max_length=80)
    ad_soyad: str = Field(min_length=1, max_length=120)
    rol: str
    personel_id: int | None = Field(default=None, gt=0)
    bolum_id: int | None = Field(default=None, gt=0)
    sifre: str = Field(min_length=6, max_length=256)


class KullaniciGuncellemeIstegi(BaseModel):
    ad_soyad: str = Field(min_length=1, max_length=120)
    rol: str
    personel_id: int | None = Field(default=None, gt=0)
    bolum_id: int | None = Field(default=None, gt=0)
    aktif: bool


class SifreSifirlamaIstegi(BaseModel):
    sifre: str = Field(min_length=6, max_length=256)


class OnayAkisiIstegi(BaseModel):
    acik: bool


class YedekGeriYukleIstegi(BaseModel):
    dosya_adi: str = Field(min_length=1, max_length=200)
    onay_metni: str = Field(min_length=1, max_length=50)


class YedekYukleIstegi(BaseModel):
    dosya_adi: str = Field(min_length=1, max_length=200)
    icerik: str = Field(min_length=100, max_length=140_000_000)


class SiparisKalemi(BaseModel):
    urun_id: int | None = None
    aciklama: str | None = None
    miktar: float = 1
    birim: str | None = None
    birim_fiyat: float | None = None
    iskonto_orani: float = 0


class SiparisIstegi(BaseModel):
    surum: int | None = Field(default=None, ge=0)
    tarih: str | None = None
    cari_id: int | None = None
    bolum_id: int | None = None
    konu: str = ""
    ucret_esasi: str | None = None
    teslim_tarihi: str | None = None
    aciklama: str = ""
    kalemler: list[SiparisKalemi] = Field(default_factory=list)

class SiparistenFaturaIstegi(BaseModel):
    surum: int = Field(ge=0)
    belge_turu: str = "e-Arşiv Fatura"
    belge_no: str = Field(default="", max_length=100)
    tarih: str = Field(default_factory=lambda: date.today().isoformat(), min_length=10, max_length=10)
    tevkifat: str = "Yok"
    avans_mahsup: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class SiparisStokCikisiIstegi(BaseModel):
    malzeme_id: int = Field(gt=0)
    miktar: float = Field(gt=0, allow_inf_nan=False)
    tarih: str = Field(default_factory=lambda: date.today().isoformat(), min_length=10, max_length=10)
    neden: str = Field(min_length=1, max_length=80)
    aciklama: str = Field(default="", max_length=500)

class FaturaKalemiIstegi(BaseModel):
    urun_id: int | None = Field(default=None, gt=0)
    malzeme_id: int | None = Field(default=None, gt=0)
    aciklama: str = Field(default="", max_length=500)
    miktar: float = Field(gt=0, allow_inf_nan=False)
    birim: str = Field(default="Adet", min_length=1, max_length=40)
    birim_fiyat: float = Field(ge=0, allow_inf_nan=False)
    iskonto_orani: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    iskonto: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    kdv_orani: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)


class FaturaIstegi(BaseModel):
    surum: int | None = Field(default=None, ge=0)
    belge_turu: str
    belge_no: str = Field(default="", max_length=100)
    tarih: str = Field(min_length=10, max_length=10)
    cari_id: int = Field(gt=0)
    siparis_id: int | None = Field(default=None, gt=0)
    aciklama: str = Field(default="", max_length=1000)
    tevkifat: str = "Yok"
    avans_mahsup: float = Field(default=0, ge=0, allow_inf_nan=False)
    stopaj_turu: str = "Yok"
    gider_turu: str = "Doğrudan Üretim Gideri"
    temin_usulu: str = "Doğrudan Temin"
    kontrol_toplam: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    kalemler: list[FaturaKalemiIstegi] = Field(min_length=1, max_length=500)


class FaturaOdemeIstegi(BaseModel):
    tarih: str = Field(min_length=10, max_length=10)
    hesap: str = Field(pattern="^(Banka \\(102\\)|Kasa \\(100\\))$")
    tutar: float = Field(gt=0, allow_inf_nan=False)
    belge_no: str = Field(default="", max_length=100)
    aciklama: str = Field(default="", max_length=500)

class DogrudanTeminKalemiIstegi(BaseModel):
    ad: str = Field(min_length=1, max_length=250)
    miktar: float = Field(gt=0, allow_inf_nan=False)
    birim: str = Field(default="", max_length=40)


class DogrudanTeminTeklifiIstegi(BaseModel):
    ad: str = Field(min_length=1, max_length=200)
    tutar: float = Field(gt=0, allow_inf_nan=False)


class DogrudanTeminIstegi(BaseModel):
    fatura_id: int | None = Field(default=None, gt=0)
    konu: str = Field(min_length=1, max_length=500)
    tarih: str = Field(min_length=10, max_length=10)
    sayi: str = Field(default="", max_length=100)
    gider_turu: str
    kalemler: list[DogrudanTeminKalemiIstegi] = Field(min_length=1, max_length=200)
    firmalar: list[DogrudanTeminTeklifiIstegi] = Field(default_factory=list, max_length=50)
    gorevliler: list[str] = Field(default_factory=list, max_length=20)
    yaklasik_maliyet: float = Field(ge=0, allow_inf_nan=False)
    teslim_yeri: str = Field(default="İşletme atölyesine", max_length=300)

class KasaIstegi(BaseModel):
    surum: int | None = Field(default=None, ge=0)
    tarih: str = Field(min_length=10, max_length=10)
    hesap: str
    yon: str
    tur: str
    tutar: float = Field(gt=0, allow_inf_nan=False)
    hasilat_tutari: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    cari_id: int | None = Field(default=None, gt=0)
    fatura_id: int | None = Field(default=None, gt=0)
    siparis_id: int | None = Field(default=None, gt=0)
    belge_no: str = Field(default="", max_length=100)
    aciklama: str = Field(default="", max_length=500)
    bakiye_uyarisi_onaylandi: bool = False


class StokHareketIstegi(BaseModel):
    tarih: str = Field(min_length=10, max_length=10)
    malzeme_id: int = Field(gt=0)
    yon: str
    neden: str = Field(min_length=1, max_length=80)
    miktar: float = Field(gt=0, allow_inf_nan=False)
    birim_fiyat: float = Field(default=0, ge=0, allow_inf_nan=False)
    siparis_id: int | None = Field(default=None, gt=0)
    aciklama: str = Field(default="", max_length=500)
    sifir_fiyat_onaylandi: bool = False


class FazlaIstegi(BaseModel):
    yil: int
    ay: int = Field(ge=1, le=12)
    personel_id: int | None = None
    siparis_id: int | None = None
    saat: float = 0
    saat_ucreti: float | None = None
    puantaj: dict[str, float] = Field(default_factory=dict)
    aciklama: str = ""
    onizleme: bool = False
    surum: int | None = None


class ParcaBasiSatirIstegi(BaseModel):
    kisi_turu: str = Field(pattern="^(Personel|Öğrenci)$")
    kisi_id: int = Field(gt=0)
    katki: float = Field(default=0, ge=0, le=999999999999, allow_inf_nan=False)
    onceki_kumulatif: float | None = Field(default=None, ge=0, le=999999999999, allow_inf_nan=False)
    puantaj: dict[int, float] = Field(default_factory=dict)


class ParcaBasiIstegi(BaseModel):
    yil: int = Field(ge=2000, le=2200)
    ay: int = Field(ge=1, le=12)
    siparis_id: int = Field(gt=0)
    kabul_edilen_iscilik: float = Field(ge=0, le=999999999999, allow_inf_nan=False)
    ogrenci_orani: float = Field(ge=0, le=1, allow_inf_nan=False)
    aciklama: str = Field(default="", max_length=2000)
    satirlar: list[ParcaBasiSatirIstegi] = Field(min_length=1, max_length=500)
    surum: int | None = None


class ParcaBasiOdemeIstegi(BaseModel):
    tarih: str = Field(min_length=10, max_length=10)
    hesap: str = Field(pattern="^(Banka \\(102\\)|Kasa \\(100\\))$")
    belge_no: str = Field(default="", max_length=100)
    aciklama: str = Field(default="", max_length=500)


class DenetimOlusturIstegi(BaseModel):
    baslik: str = Field(min_length=1, max_length=160)
    bilgiler: dict[str, str] = Field(default_factory=dict)


class DenetimGuncelleIstegi(BaseModel):
    surum: int = Field(ge=1)
    baslik: str = Field(min_length=1, max_length=160)
    durum: str
    bilgiler: dict[str, str] = Field(default_factory=dict)


class DenetimMaddeIstegi(BaseModel):
    surum: int = Field(ge=1)
    durum: str
    aciklama: str = Field(default="", max_length=5000)


# ---------------------------------------------------------------- oturum ve yetki
def _ozet(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _simdi() -> str:
    return datetime.now().strftime(ZAMAN)


def _lisans_tazele(d):
    if time.monotonic() - _son_lisans[0] > LISANS_TAZELEME_SANIYE:
        lisans.uygula(d)
        _son_lisans[0] = time.monotonic()


class Baglam:
    """Doğrulanmış mobil oturum. 'with b as d:' bloğu veritabanını bu kullanıcı adına kilitli kullanır."""

    def __init__(self, k: dict, token_ozet: str, cihaz: str | None, kurum_kodu: str | None = None):
        self.k = k
        self.token_ozet = token_ozet
        self.oturum = "m" + token_ozet[:15]
        self.cihaz = cihaz or "Mobil cihaz"
        self.kurum_kodu = kurum_kodu_normalize(kurum_kodu) if kurum_kodu else None
        if _HAVUZ and self.kurum_kodu:
            self._kilit = _HAVUZ.kilit(self.kurum_kodu)
        else:
            self._kilit = None if dbm.al().sunucu_mu else KILIT
        self._istek_db = False
        self._veritabani = None

    def __enter__(self):
        if self._kilit:
            self._kilit.acquire()
        try:
            if _HAVUZ and self.kurum_kodu:
                d = _HAVUZ.al(self.kurum_kodu)
            else:
                kaynak = dbm.al()
                d = dbm.istek_baglantisi(kaynak)
                self._istek_db = d is not kaynak
            self._veritabani = d
            dbm.baglam_ayarla(d)
            _lisans_tazele(d)
            d.oturum_ac(self.k, istemci="Mobil", bilgisayar=self.cihaz, oturum=self.oturum)
            return d
        except BaseException:
            dbm.baglam_ayarla(None)
            if self._istek_db and self._veritabani:
                self._veritabani.kapat()
            if self._kilit:
                self._kilit.release()
            raise

    def __exit__(self, *_):
        dbm.baglam_ayarla(None)
        if self._istek_db and self._veritabani:
            self._veritabani.kapat()
        if self._kilit:
            self._kilit.release()


def _kurum_dogrula(d, istenen: str):
    """Tek okullu sunucuda girilen kurum kodunun bu veritabanına ait olduğunu doğrular."""
    istenen = kurum_kodu_normalize(istenen)
    if not istenen:
        return
    if not ag.kurum_kodu_gecerli(istenen):
        raise HTTPException(400, "Kurum kodu 5–8 rakam olmalıdır.")
    mevcut = kurum_kodu_normalize(d.kurum().get("kurum_kodu"))
    if mevcut and mevcut != istenen:
        raise HTTPException(403, f"Bu sunucu {mevcut} kurum koduna aittir; girdiğiniz kod ({istenen}) eşleşmiyor.")
    if not mevcut:
        raise HTTPException(
            403,
            "Bu veritabanında henüz kurum kodu tanımlı değil. Masaüstünden Kurum ve Görevliler sayfasında "
            "kurum kodunu girip lisansı etkinleştiriniz.",
        )


def _istemci_ip(request: Request) -> str:
    ip = request.client.host if request.client else ""
    if ip in ("127.0.0.1", "::1") and request.headers.get("x-istemci-ip"):
        return request.headers["x-istemci-ip"][:45]  # sunucuda çalışan web arayüzünün bildirdiği tarayıcı adresi
    return ip


def oturum(request: Request, authorization: str | None = Header(None)) -> Baglam:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Oturum açmanız gerekiyor.")
    ozet = _ozet(authorization[7:].strip())
    kod = _HAVUZ.oturumlar.get(ozet) if _HAVUZ else None
    kilit = _HAVUZ.kilit(kod) if (_HAVUZ and kod) else KILIT
    with kilit:
        if _HAVUZ:
            if not kod:
                raise HTTPException(401, "Oturum süresi doldu; yeniden giriş yapınız.")
            d = _HAVUZ.al(kod)
            dbm.baglam_ayarla(d)
        else:
            d = dbm.al()
        try:
            r = d.q1("SELECT * FROM mobil_oturum WHERE token_ozet = ? AND aktif = 1", (ozet,))
            simdi = datetime.now()
            if not r or (r["bitis"] or "") < simdi.strftime(ZAMAN):
                if _HAVUZ:
                    _HAVUZ.oturumlar.pop(ozet, None)
                raise HTTPException(401, "Oturum süresi doldu; yeniden giriş yapınız.")
            k = d.q1("SELECT * FROM kullanici WHERE id = ? AND aktif = 1", (r["kullanici_id"],))
            if not k:
                d.ex("UPDATE mobil_oturum SET aktif = 0 WHERE id = ?", (r["id"],))
                if _HAVUZ:
                    _HAVUZ.oturumlar.pop(ozet, None)
                raise HTTPException(401, "Kullanıcı hesabınız pasif; sistem yöneticisine başvurunuz.")
            son = datetime.strptime(r["son_kullanim"], ZAMAN) if r["son_kullanim"] else simdi - timedelta(days=1)
            if (simdi - son).total_seconds() > 60:
                d.ex("UPDATE mobil_oturum SET son_kullanim = ?, bitis = ?, ip = ? WHERE id = ?",
                     (simdi.strftime(ZAMAN), (simdi + OTURUM_SURESI).strftime(ZAMAN), _istemci_ip(request), r["id"]))
        finally:
            if _HAVUZ:
                dbm.baglam_ayarla(None)
    return Baglam(k, ozet, r["cihaz"], kod)


def _yil(yil: int = Query(0, ge=0, le=2200)) -> int:
    return yil or date.today().year


def _ay(ay: int = Query(0, ge=0, le=12)) -> int:
    return ay or date.today().month


def kullanici(b: Baglam = Depends(oturum)) -> Baglam:
    if b.k.get("sifre_degismeli"):
        raise HTTPException(403, "Güvenliğiniz için önce şifrenizi değiştiriniz.")
    return b


def etkin_yetki(k: dict, sayfa: str) -> str:
    y = yetki.sayfa_yetkisi(k["rol"], sayfa)
    return "g" if y == "y" and dbm.al().salt_okunur else y


def gerek(k: dict, sayfa: str, yaz: bool = False):
    y = yetki.sayfa_yetkisi(k["rol"], sayfa)
    if not y:
        raise HTTPException(403, f"'{sayfa}' bölümüne erişim yetkiniz bulunmuyor.")
    if yaz and y != "y":
        raise HTTPException(403, f"'{sayfa}' bölümünde yalnız görüntüleme yetkiniz var; kayıt yapamazsınız.")
    if yaz and dbm.al().salt_okunur:
        raise SaltOkunurHata(lisans.durum(dbm.al()).ozet)


def bolum_kisiti(k: dict) -> int | None:
    """Alan şefi ve öğretmen için kayıtların sınırlandığı bölüm."""
    if not yetki.bolum_kisitli(k["rol"]):
        return None
    return onay.kullanici_bolumu(k) or -1


def kapsamda(k: dict, tur: str, bid: int) -> bool:
    b = bolum_kisiti(k)
    return not b or onay.KANCALAR[tur]["bolum"](bid) in (None, 0, b)


def _tur(tur: str) -> str:
    if tur not in yetki.AKISLAR:
        raise HTTPException(404, "Belge türü bulunamadı.")
    return tur


def _kullanici_bilgisi(k: dict) -> dict:
    return {"id": k["id"], "kullanici_adi": k["kullanici_adi"], "ad_soyad": k.get("ad_soyad"), "rol": k["rol"],
            "rol_aciklamasi": yetki.ROL_ACIKLAMALARI.get(k["rol"], ""), "personel_id": k.get("personel_id"),
            "bolum_id": bolum_kisiti(k), "sifre_degismeli": bool(k.get("sifre_degismeli"))}


def _onay_metni(durumlar: dict, bid: int, onayli: bool) -> str:
    if bid in durumlar:
        return onay.durum_metni(durumlar[bid])
    return onay.ONAYLANDI if onayli else onay.HAZIRLANIYOR


# ---------------------------------------------------------------- uygulama
def uygulama_olustur(kaynak=None, web_adresi: str | None = None, havuz=None) -> FastAPI:
    """kaynak: None (programın bağlantı ayarı), SQLite dosya yolu veya BaglantiAyari.
    havuz: OkulHavuzu (çok okullu geçit); verilirse kaynak yok sayılır ve kurum kodu zorunludur.
    web_adresi verilirse Flet web arayüzü '/' adresinden sunulur ve API'ye bu adresten bağlanır."""
    global _HAVUZ
    _HAVUZ = havuz
    if havuz is None:
        dbm.baslat(kaynak)
    _son_lisans[0] = time.monotonic()

    @asynccontextmanager
    async def yasam(_):
        if web_adresi:
            import flet_web.fastapi as flet_fastapi
            await flet_fastapi.app_manager.start()
        yield
        if web_adresi:
            await flet_fastapi.app_manager.shutdown()
        if havuz is not None:
            havuz.kapat()

    app = FastAPI(title="DÖSE Yönetim Mobil API", version=SURUM, docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=yasam)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def _hata(kod: int, mesaj: str) -> JSONResponse:
        return JSONResponse({"hata": mesaj}, status_code=kod)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_, e):
        return _hata(e.status_code, str(e.detail))

    @app.exception_handler(RequestValidationError)
    async def _dogrulama(_, e):
        alanlar = ", ".join(str(h["loc"][-1]) for h in e.errors())
        return _hata(422, f"Gönderilen bilgiler eksik veya hatalı: {alanlar}")

    @app.exception_handler(onay.OnayHatasi)
    async def _onay(_, e):
        return _hata(400, str(e))

    @app.exception_handler(IslemHatasi)
    async def _islem(_, e):
        return _hata(400, str(e))

    @app.exception_handler(SaltOkunurHata)
    async def _salt(_, e):
        return _hata(403, str(e))

    @app.exception_handler(KayitCakismasi)
    async def _cakisma(_, e):
        return _hata(409, str(e))

    # ------------------------------------------------------------ genel
    @app.get("/api/durum")
    def durum(kurum_kodu: str = Query("")):
        if _HAVUZ:
            kod = kurum_kodu_normalize(kurum_kodu)
            if not kod:
                return {"uygulama": "DÖSE Yönetim", "surum": SURUM, "api": API_SURUMU, "coklu": True,
                        "kurum": None, "kurum_kodu": None, "satici": lisans.SATICI,
                        "satici_iletisim": lisans.SATICI_ILETISIM,
                        "aciklama": "Çok okullu geçit. Girişte kurum kodu zorunludur."}
            try:
                with _HAVUZ.kilit(kod):
                    d = _HAVUZ.al(kod)
                    dbm.baglam_ayarla(d)
                    try:
                        ld = lisans.durum(d)
                        return {"uygulama": "DÖSE Yönetim", "surum": SURUM, "api": API_SURUMU, "coklu": True,
                                "kurum": d.kurum().get("okul_adi"), "kurum_kodu": kod,
                                "lisans": ld.ozet, "salt_okunur": not ld.yazilabilir, "satici": lisans.SATICI,
                                "satici_iletisim": lisans.SATICI_ILETISIM}
                    finally:
                        dbm.baglam_ayarla(None)
            except (ValueError, KeyError, RuntimeError) as e:
                raise HTTPException(404, str(e)) from None
        with KILIT:
            d = dbm.al()
            ld = lisans.durum(d)
            return {"uygulama": "DÖSE Yönetim", "surum": SURUM, "api": API_SURUMU, "coklu": False,
                    "kurum": d.kurum().get("okul_adi"),
                    "kurum_kodu": kurum_kodu_normalize(d.kurum().get("kurum_kodu")),
                    "lisans": ld.ozet, "salt_okunur": not ld.yazilabilir, "satici": lisans.SATICI,
                    "satici_iletisim": lisans.SATICI_ILETISIM}

    @app.post("/api/lisans/etkinlestir")
    def lisans_etkinlestir(istek: LisansEtkinlestirmeIstegi):
        kod = kurum_kodu_normalize(istek.kurum_kodu)
        if not ag.kurum_kodu_gecerli(kod):
            raise HTTPException(400, "Kurum kodu 5–8 rakam olmalıdır.")

        def _etkinlestir(d):
            try:
                aktif_lisans = lisans.etkinlestir(d, istek.anahtar)
            except lisans.LisansHatasi as exc:
                raise HTTPException(400, str(exc)) from exc
            _son_lisans[0] = 0.0
            return {"lisans": aktif_lisans.no, "okul": aktif_lisans.okul,
                    "bitis": aktif_lisans.bitis_metni(), "durum": lisans.durum(d).ozet}

        if _HAVUZ:
            if not _HAVUZ.kayitli_mi(kod):
                raise HTTPException(404, "Bu kurum kodu geçitte tanımlı değil.")
            with _HAVUZ.kilit(kod):
                d = _HAVUZ.al(kod)
                dbm.baglam_ayarla(d)
                try:
                    return _etkinlestir(d)
                finally:
                    dbm.baglam_ayarla(None)

        with KILIT:
            d = dbm.al()
            mevcut = kurum_kodu_normalize(d.kurum().get("kurum_kodu"))
            if mevcut and mevcut != kod:
                raise HTTPException(403, f"Bu sunucu {mevcut} kurum koduna aittir.")
            return _etkinlestir(d)

    @app.post("/api/kesif")
    def kesif(istek: KesifIstegi):
        """Kurum kodunun bu geçitte / sunucuda tanımlı olup olmadığını kontrol eder (şifre istemez)."""
        kod = kurum_kodu_normalize(istek.kurum_kodu)
        if not ag.kurum_kodu_gecerli(kod):
            raise HTTPException(400, "Kurum kodu 5–8 rakam olmalıdır.")
        if _HAVUZ:
            if not _HAVUZ.kayitli_mi(kod):
                raise HTTPException(404, "Bu kurum kodu geçitte tanımlı değil.")
            return {"kurum_kodu": kod, "kurum": _HAVUZ.okul_adi(kod), "coklu": True, "uygun": True}
        with KILIT:
            d = dbm.al()
            mevcut = kurum_kodu_normalize(d.kurum().get("kurum_kodu"))
            if mevcut and mevcut != kod:
                raise HTTPException(404, "Bu sunucu farklı bir kurum koduna aittir.")
            if not mevcut:
                raise HTTPException(404, "Bu sunucuda henüz kurum kodu tanımlı değil.")
            return {"kurum_kodu": kod, "kurum": d.kurum().get("okul_adi"), "coklu": False, "uygun": True}

    @app.post("/api/giris")
    def giris(istek: GirisIstegi, request: Request):
        ad = istek.kullanici_adi.strip()
        kod = kurum_kodu_normalize(istek.kurum_kodu)
        anahtar = (_istemci_ip(request), f"{kod}:{ad.lower()}" if kod else ad.lower())
        simdi = time.monotonic()
        denemeler = [t for t in _hatali_girisler.get(anahtar, []) if simdi - t < KILIT_SANIYE]
        if len(denemeler) >= AZAMI_HATALI_GIRIS:
            kalan = int(KILIT_SANIYE - (simdi - denemeler[0])) // 60 + 1
            raise HTTPException(429, f"Çok sayıda hatalı giriş denemesi. {kalan} dakika sonra yeniden deneyiniz.")
        cihaz = (istek.cihaz or "Mobil cihaz").strip()[:80]
        if _HAVUZ and not kod:
            raise HTTPException(400, "Kurum kodu zorunludur (çok okullu geçit).")

        def _basarisiz(d, mesaj="Kullanıcı adı veya şifre hatalı."):
            denemeler.append(simdi)
            _hatali_girisler[anahtar] = denemeler
            d.oturum_ac({"kullanici_adi": ad or "?"}, istemci="Mobil", bilgisayar=cihaz, oturum="giris")
            d.log("Başarısız giriş", detay=f"IP {anahtar[0]}" + (f" kurum {kod}" if kod else ""))
            raise HTTPException(401, mesaj)

        if _HAVUZ:
            try:
                kilit = _HAVUZ.kilit(kod)
            except ValueError as e:
                raise HTTPException(400, str(e)) from None
            with kilit:
                try:
                    d = _HAVUZ.al(kod)
                except KeyError as e:
                    raise HTTPException(404, str(e)) from None
                except Exception as e:
                    raise HTTPException(503, f"Kurum veritabanına bağlanılamadı: {e}") from None
                dbm.baglam_ayarla(d)
                try:
                    _kurum_dogrula(d, kod)
                    k = d.giris_dogrula(ad, istek.sifre)
                    if not k:
                        _basarisiz(d)
                    _hatali_girisler.pop(anahtar, None)
                    token = secrets.token_urlsafe(32)
                    ozet = _ozet(token)
                    zaman = datetime.now()
                    d.ex("UPDATE mobil_oturum SET aktif = 0 WHERE bitis < ?", (zaman.strftime(ZAMAN),))
                    d.ex("INSERT INTO mobil_oturum (token_ozet, kullanici_id, cihaz, ip, olusturma, son_kullanim, bitis) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (ozet, k["id"], cihaz, anahtar[0], zaman.strftime(ZAMAN), zaman.strftime(ZAMAN),
                          (zaman + OTURUM_SURESI).strftime(ZAMAN)))
                    d.oturum_ac(k, istemci="Mobil", bilgisayar=cihaz, oturum="m" + ozet[:15])
                    d.log("Oturum açma", detay=f"Mobil giriş - kurum {kod} - IP {anahtar[0]}")
                    _HAVUZ.oturumlar[ozet] = kod
                    return {"token": token, "kullanici": _kullanici_bilgisi(k),
                            "kurum_kodu": kod, "kurum": d.kurum().get("okul_adi"),
                            "sure_saat": OTURUM_SURESI.total_seconds() / 3600}
                finally:
                    dbm.baglam_ayarla(None)

        with KILIT:
            d = dbm.al()
            if kod:
                _kurum_dogrula(d, kod)
            elif kurum_kodu_normalize(d.kurum().get("kurum_kodu")):
                # Kurum kodu tanımlıysa mobilde de istenmesini teşvik et (zorunlu değil — eski uygulamalar)
                pass
            k = d.giris_dogrula(ad, istek.sifre)
            if not k:
                _basarisiz(d)
            _hatali_girisler.pop(anahtar, None)
            token = secrets.token_urlsafe(32)
            ozet = _ozet(token)
            zaman = datetime.now()
            d.ex("UPDATE mobil_oturum SET aktif = 0 WHERE bitis < ?", (zaman.strftime(ZAMAN),))
            d.ex("INSERT INTO mobil_oturum (token_ozet, kullanici_id, cihaz, ip, olusturma, son_kullanim, bitis) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?)", (ozet, k["id"], cihaz, anahtar[0], zaman.strftime(ZAMAN),
                                                  zaman.strftime(ZAMAN), (zaman + OTURUM_SURESI).strftime(ZAMAN)))
            d.oturum_ac(k, istemci="Mobil", bilgisayar=cihaz, oturum="m" + ozet[:15])
            d.log("Oturum açma", detay=f"Mobil giriş - IP {anahtar[0]}"
                  + (f" kurum {kod}" if kod else ""))
            kk = kod or kurum_kodu_normalize(d.kurum().get("kurum_kodu"))
            return {"token": token, "kullanici": _kullanici_bilgisi(k),
                    "kurum_kodu": kk, "kurum": d.kurum().get("okul_adi"),
                    "sure_saat": OTURUM_SURESI.total_seconds() / 3600}

    @app.post("/api/cikis")
    def cikis(b: Baglam = Depends(oturum)):
        with b as d:
            d.ex("UPDATE mobil_oturum SET aktif = 0 WHERE token_ozet = ?", (b.token_ozet,))
            d.log("Oturum kapatma", detay="Mobil çıkış")
        if _HAVUZ:
            _HAVUZ.oturumlar.pop(b.token_ozet, None)
        return {"tamam": True}

    @app.post("/api/sifre")
    def sifre(istek: SifreIstegi, b: Baglam = Depends(oturum)):
        if len(istek.yeni) < 6:
            raise HTTPException(400, "Şifre en az 6 karakter olmalıdır.")
        if istek.yeni == istek.eski:
            raise HTTPException(400, "Yeni şifre eskisinden farklı olmalıdır.")
        with b as d:
            if not d.giris_dogrula(b.k["kullanici_adi"], istek.eski):
                raise HTTPException(400, "Mevcut şifreniz hatalı.")
            d.sifre_degistir(b.k["id"], istek.yeni)
            d.ex("UPDATE mobil_oturum SET aktif = 0 WHERE kullanici_id = ? AND token_ozet != ?", (b.k["id"], b.token_ozet))
        return {"tamam": True}

    @app.get("/api/ben")
    def ben(b: Baglam = Depends(oturum)):
        with b as d:
            k = b.k
            return {"kullanici": _kullanici_bilgisi(k), "kurum": d.kurum().get("okul_adi"),
                    "kurum_kodu": kurum_kodu_normalize(d.kurum().get("kurum_kodu")) or b.kurum_kodu,
                    "moduller": {m: etkin_yetki(k, s) for m, s in MOBIL_MODULLER.items()},
                    "sayfa_modulleri": {s: m for m, s in MOBIL_MODULLER.items()},
                    "yedekleme_yetkisi": k["rol"] in (M.ROL_SISTEM, M.ROL_MUDUR, M.ROL_SAYMAN),
                    "bekleyen_onay": onay.bekleyen_sayisi(k), "onay_akisi": onay.akis_acik(),
                    "lisans": lisans.durum(d).ozet, "salt_okunur": d.salt_okunur, "yil": date.today().year}

    # ------------------------------------------------------------ rehberlik ve denetim formu
    def _denetim(d, denetim_id: int) -> dict:
        kayit = d.q1("SELECT * FROM denetim WHERE id = ?", (denetim_id,))
        if not kayit:
            raise HTTPException(404, "Denetim formu bulunamadı.")
        try:
            bilgiler = json.loads(kayit.get("bilgiler") or "{}")
        except (TypeError, ValueError):
            raise HTTPException(500, "Denetim formunun bilgileri okunamadı.") from None
        if not isinstance(bilgiler, dict):
            raise HTTPException(500, "Denetim formunun bilgileri beklenen biçimde değil.")
        kayit["bilgiler"] = bilgiler
        return kayit

    def _denetim_maddeleri(d, denetim_id: int, rol: str) -> list[dict]:
        cevaplar = {x["madde_kodu"]: x for x in d.q(
            "SELECT * FROM denetim_madde WHERE denetim_id = ?", (denetim_id,))}
        sonuc = []
        for madde in denetim_formu.MADDELER:
            tumunu_gorur = rol in (M.ROL_SISTEM, M.ROL_MUDUR, M.ROL_TMY, M.ROL_IZLEYICI)
            rol_yetkili = rol == M.ROL_SISTEM or rol in denetim_formu.BOLUM_YETKILERI[madde["bolum"]]
            if not tumunu_gorur and not rol_yetkili:
                continue
            cevap = cevaplar.get(madde["kod"], {})
            sonuc.append({**madde, "durum": cevap.get("durum") or "Değerlendirilmedi",
                          "aciklama": cevap.get("aciklama") or "", "surum": cevap.get("surum") or 1,
                          "guncelleme": cevap.get("guncelleme"), "guncelleyen": cevap.get("guncelleyen"),
                          "yazabilir": rol_yetkili})
        return sonuc

    @app.get("/api/denetimler")
    def denetimler(b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["denetim"])
            return {"denetimler": d.q(
                """SELECT d.id, d.baslik, d.durum, d.surum, d.guncelleme, d.guncelleyen,
                          COUNT(m.id) madde_sayisi,
                          SUM(CASE WHEN m.durum != 'Değerlendirilmedi' THEN 1 ELSE 0 END) degerlendirilen
                   FROM denetim d LEFT JOIN denetim_madde m ON m.denetim_id = d.id
                   GROUP BY d.id ORDER BY d.id DESC LIMIT 100""")}

    @app.post("/api/denetimler")
    def denetim_olustur(istek: DenetimOlusturIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["denetim"], yaz=True)
            if b.k["rol"] not in (M.ROL_SISTEM, M.ROL_MUDUR, M.ROL_TMY):
                raise HTTPException(403, "Yeni denetim formunu yalnızca okul yöneticileri başlatabilir.")
            bilgiler = {k: v.strip() for k, v in istek.bilgiler.items() if k in denetim_formu.BILGI_ALANLARI}
            simdi = _simdi()
            with d.islem():
                denetim_id = d.ekle("denetim", {"baslik": istek.baslik.strip(), "durum": "Taslak",
                                                 "bilgiler": json.dumps(bilgiler, ensure_ascii=False),
                                                 "surum": 1, "olusturma": simdi, "guncelleme": simdi,
                                                 "olusturan": b.k["kullanici_adi"], "guncelleyen": b.k["kullanici_adi"]})
                d.m.coklu("INSERT INTO denetim_madde (denetim_id, madde_kodu, durum, aciklama, surum) "
                          "VALUES (?, ?, ?, ?, ?)",
                          [(denetim_id, x["kod"], "Değerlendirilmedi", "", 1) for x in denetim_formu.MADDELER])
                d.log("Denetim formu oluşturma", "denetim", denetim_id, yeni={"baslik": istek.baslik.strip()})
            return {"id": denetim_id}

    @app.get("/api/denetimler/{denetim_id}")
    def denetim_detay(denetim_id: int, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["denetim"])
            kayit = _denetim(d, denetim_id)
            if b.k["rol"] in (M.ROL_SEF, M.ROL_OGRETMEN, M.ROL_MEMUR):
                gorulebilir = {"il", "ilce", "okul_adi", "kurum_kodu", "faaliyet_alani",
                               "denetim_baslangic", "denetim_bitis"}
                kayit["bilgiler"] = {k: v for k, v in kayit["bilgiler"].items() if k in gorulebilir}
            maddeler = _denetim_maddeleri(d, denetim_id, b.k["rol"])
            kayit["maddeler"] = maddeler
            kayit["bilgi_yazabilir"] = b.k["rol"] in (M.ROL_SISTEM, M.ROL_MUDUR, M.ROL_TMY)
            kayit["rapor_goruntuleyebilir"] = b.k["rol"] in (
                M.ROL_SISTEM, M.ROL_MUDUR, M.ROL_TMY, M.ROL_IZLEYICI)
            return kayit

    @app.put("/api/denetimler/{denetim_id}")
    def denetim_guncelle(denetim_id: int, istek: DenetimGuncelleIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["denetim"], yaz=True)
            if b.k["rol"] not in (M.ROL_SISTEM, M.ROL_MUDUR, M.ROL_TMY):
                raise HTTPException(403, "Denetim rapor bilgilerini güncelleme yetkiniz yok.")
            mevcut = _denetim(d, denetim_id)
            if istek.durum not in ("Taslak", "Tamamlandı"):
                raise HTTPException(400, "Denetim durumu Taslak veya Tamamlandı olmalıdır.")
            if istek.durum == "Tamamlandı" and d.deger(
                    "SELECT COUNT(*) FROM denetim_madde WHERE denetim_id = ? AND durum = 'Değerlendirilmedi'",
                    (denetim_id,), 0):
                raise HTTPException(400, "Tamamlamadan önce tüm kontrol maddelerini değerlendirin.")
            bilgiler = dict(mevcut["bilgiler"])
            bilgiler.update({k: v.strip() for k, v in istek.bilgiler.items()
                             if k in denetim_formu.BILGI_ALANLARI})
            if istek.durum == "Tamamlandı":
                bos_alanlar = [alan for alan in denetim_formu.ZORUNLU_RAPOR_ALANLARI
                               if not (bilgiler.get(alan) or "").strip()]
                if bos_alanlar:
                    eksikler = ", ".join(alan.replace("_", " ") for alan in bos_alanlar)
                    raise HTTPException(400, "Tamamlamadan önce rapordaki tüm alanları doldurun; uygulanamayan "
                                             f"alanlara 'Yok' veya 'Uygulanamaz' yazın. Eksik alanlar: {eksikler}.")
            with d.islem():
                cur = d.ex("""UPDATE denetim SET baslik = ?, durum = ?, bilgiler = ?, surum = surum + 1,
                              guncelleme = ?, guncelleyen = ? WHERE id = ? AND surum = ?""",
                            (istek.baslik.strip(), istek.durum, json.dumps(bilgiler, ensure_ascii=False),
                             _simdi(), b.k["kullanici_adi"], denetim_id, istek.surum))
                if cur.rowcount != 1:
                    raise HTTPException(409, "Form siz düzenlerken başka bir kullanıcı tarafından güncellendi. "
                                             "Güncel formu yeniden açıp tekrar deneyin.")
                d.log("Güncelleme", "denetim", denetim_id, yeni={"baslik": istek.baslik.strip(),
                                                                 "durum": istek.durum})
            return {"tamam": True, "surum": istek.surum + 1}

    @app.put("/api/denetimler/{denetim_id}/maddeler/{madde_kodu}")
    def denetim_madde_guncelle(denetim_id: int, madde_kodu: str, istek: DenetimMaddeIstegi,
                               b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["denetim"], yaz=True)
            _denetim(d, denetim_id)
            madde = next((x for x in denetim_formu.MADDELER if x["kod"] == madde_kodu), None)
            if not madde:
                raise HTTPException(404, "Denetim kontrol maddesi bulunamadı.")
            if b.k["rol"] != M.ROL_SISTEM and b.k["rol"] not in denetim_formu.BOLUM_YETKILERI[madde["bolum"]]:
                raise HTTPException(403, "Bu kontrol maddesini güncelleme yetkiniz yok.")
            if istek.durum not in ("Değerlendirilmedi", "Uygun", "Eksik", "Uygulanamaz"):
                raise HTTPException(400, "Sonuç Uygun, Eksik, Uygulanamaz veya Değerlendirilmedi olmalıdır.")
            if istek.durum == "Eksik" and not istek.aciklama.strip():
                raise HTTPException(400, "Eksik sonucu için bulgu ve kanıt açıklaması giriniz.")
            kayit = d.q1("SELECT id, surum FROM denetim_madde WHERE denetim_id = ? AND madde_kodu = ?",
                         (denetim_id, madde_kodu))
            if not kayit:
                raise HTTPException(404, "Kontrol maddesi bu formda bulunamadı.")
            with d.islem():
                cur = d.ex("""UPDATE denetim_madde SET durum = ?, aciklama = ?, surum = surum + 1,
                              guncelleme = ?, guncelleyen = ? WHERE id = ? AND surum = ?""",
                            (istek.durum, istek.aciklama.strip(), _simdi(), b.k["kullanici_adi"],
                             kayit["id"], istek.surum))
                if cur.rowcount != 1:
                    raise HTTPException(409, "Bu maddeyi başka bir kullanıcı güncelledi. Güncel sonucu yeniden açın.")
                d.log("Güncelleme", "denetim_madde", kayit["id"], yeni={"denetim_id": denetim_id,
                                                                         "madde_kodu": madde_kodu,
                                                                         "durum": istek.durum})
            return {"tamam": True, "surum": istek.surum + 1}

    @app.get("/api/denetimler/{denetim_id}/rapor")
    def denetim_raporu(denetim_id: int, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["denetim"])
            if b.k["rol"] not in (M.ROL_SISTEM, M.ROL_MUDUR, M.ROL_TMY, M.ROL_IZLEYICI):
                raise HTTPException(403, "Denetim PDF raporunu görüntüleme yetkiniz yok.")
            kayit = _denetim(d, denetim_id)
            maddeler = _denetim_maddeleri(d, denetim_id, b.k["rol"])
            data = denetim_formu.rapor_pdf(d.kurum(), kayit, maddeler)
            d.log("PDF raporu", "denetim", denetim_id)
            return {"dosya_adi": f"denetim_raporu_{denetim_id}.pdf",
                    "icerik": base64.b64encode(data).decode("ascii")}

    @app.get("/api/senkron")
    def senkron(son_no: int = Query(0, ge=0), b: Baglam = Depends(kullanici)):
        """Başka oturumlardaki kayıtları hafif bir değişiklik akışıyla Flet istemcilerine bildirir."""
        with b as d:
            degisiklikler = d.degisiklikler(son_no, sinir=100)
            if etkin_yetki(b.k, MOBIL_MODULLER["islem"]):
                gorunen = degisiklikler
            else:
                gorunen = [{"id": x["id"]} for x in degisiklikler]
            return {"degisiklikler": gorunen, "son_no": d.son_islem_no()}

    # ------------------------------------------------------------ gösterge paneli
    @app.get("/api/panel")
    def panel(yil: int = Query(default_factory=lambda: date.today().year), b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["panel"])
            bugun = date.today()
            rol = b.k["rol"]
            sureler = uyum.rol_sureleri(rol, bugun) if yil == bugun.year else []
            return {"yil": yil, "ozet": gosterge.ozet(yil), "bekleyen_onay": onay.bekleyen_sayisi(b.k),
                    "rol_unvani": kilavuz.ROL_REHBERI.get(rol, {}).get("unvan", rol),
                    "uyarilar": [{"metin": x.baslik, "seviye": x.seviye, "sayfa": x.sayfa, "cozum": x.cozum,
                                  "sorumlular": x.sorumlular}
                                 for x in uyum.yapilacaklar(yil, rol, bolum_kisiti(b.k), bugun)],
                    "sureler": [{"tarih": s.tarih.isoformat(), "ad": s.ad, "aciklama": s.aciklama,
                                 "kalan_gun": (s.tarih - bugun).days} for s in sureler]}

    @app.get("/api/yapilacaklar")
    def yapilacaklar(yil: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200),
                     b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["yapilacaklar"])
            bugun = date.today()
            rol = b.k["rol"]
            sureler = uyum.rol_sureleri(rol, bugun, 40) if yil == bugun.year else []
            return {
                "yil": yil,
                "rol_unvani": kilavuz.ROL_REHBERI.get(rol, {}).get("unvan", rol),
                "rol_ozeti": kilavuz.ROL_REHBERI.get(rol, {}).get("ozet", ""),
                "bulgular": [x.sozluk() for x in uyum.yapilacaklar(yil, rol, bolum_kisiti(b.k), bugun)],
                "sureler": [{"tarih": s.tarih.isoformat(), "ad": s.ad, "aciklama": s.aciklama,
                             "kalan_gun": (s.tarih - bugun).days} for s in sureler],
                "bekleyen_onay": onay.bekleyen_sayisi(b.k),
            }

    @app.get("/api/uyum")
    def uyum_denetimi(yil: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200),
                      b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["uyum"])
            bulgular = uyum.denetle(yil, bolum_kisiti(b.k))
            puan = uyum.puan(bulgular)
            return {
                "yil": yil,
                "bolum_kisitli": bolum_kisiti(b.k) is not None,
                "puan": puan,
                "puan_durumu": uyum.puan_durumu(puan)[0],
                "sayilar": {seviye: sum(x.seviye == seviye for x in bulgular)
                            for seviye in (uyum.HATA, uyum.UYARI, uyum.BILGI)},
                "bulgular": [x.sozluk() | {"ilgili": uyum.ilgili_mi(x, b.k["rol"])} for x in bulgular],
                "genel_uyari": kilavuz.GENEL_UYARI,
            }

    @app.get("/api/rehber")
    def mevzuat_rehberi(yil: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200),
                        b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["rehber"])
            parametreler = d.parametreler(yil)
            parametre_satirlari = []
            for anahtar, etiket, tur, _varsayilan, dayanak in M.PARAMETRELER:
                deger = parametreler[anahtar]
                if tur == "para":
                    gorunen = para(deger) + " TL"
                elif tur == "oran":
                    gorunen = f"%{float(deger) * 100:.3f}".rstrip("0").rstrip(".,").replace(".", ",")
                elif anahtar == "gv_tarifesi_ucret":
                    gorunen = "\n".join(f"{para(ust_sinir) if ust_sinir else 'üzeri'}: %{oran * 100:g}"
                                        for ust_sinir, oran in deger)
                else:
                    gorunen = f"{deger:g}" if isinstance(deger, float) else str(deger)
                parametre_satirlari.append({
                    "etiket": etiket, "deger": gorunen, "dayanak": dayanak,
                })
            bugun = date.today()
            return {
                "yil": yil,
                "mevzuat_html": M.MEVZUAT_REHBERI_HTML,
                "sozluk": [{"terim": terim, "aciklama": aciklama}
                           for terim, aciklama in sorted(kilavuz.SOZLUK)],
                "riskler": [{
                    "hata": hata, "sonuc": sonuc, "koruma": koruma, "dayanak": dayanak,
                } for hata, sonuc, koruma, dayanak in kilavuz.CEZA_RISKLERI],
                "roller": [{
                    "rol": rol, "unvan": bilgi["unvan"], "ozet": bilgi["ozet"],
                    "gorevler": bilgi["gorevler"], "dikkat": bilgi["dikkat"],
                } for rol, bilgi in kilavuz.ROL_REHBERI.items()],
                "yaklasan_sureler": [{
                    "tarih": sure.tarih.isoformat(), "ad": sure.ad, "aciklama": sure.aciklama,
                    "kalan_gun": (sure.tarih - bugun).days,
                } for sure in kilavuz.yaklasan_sureler(bugun=bugun, gun=60)],
                "yasal_takvim": [{"zaman": zaman, "aciklama": aciklama} for zaman, aciklama in M.YASAL_TAKVIM],
                "merkez_saymanlik": M.MERKEZ_SAYMANLIK,
                "parametreler": parametre_satirlari,
                "genel_uyari": kilavuz.GENEL_UYARI,
            }

    @app.get("/api/kilavuz")
    def is_rehberi(tumu: bool = False, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["kilavuz"])
            rol = b.k["rol"]
            rehberler = kilavuz.IS_REHBERLERI if tumu else kilavuz.rol_rehberleri(rol)
            rol_bilgisi = kilavuz.ROL_REHBERI.get(rol, {})
            return {
                "rol": rol,
                "rol_bilgisi": {k: rol_bilgisi.get(k) for k in ("unvan", "ozet", "gorevler", "dikkat")},
                "genel_uyari": kilavuz.GENEL_UYARI,
                "rehberler": [{
                    "kod": r.kod, "ikon": r.ikon, "baslik": r.baslik, "ozet": r.ozet,
                    "roller": list(r.roller),
                    "adimlar": [{"metin": a.metin, "sayfa": a.sayfa, "kim": a.kim} for a in r.adimlar],
                    "yasaklar": list(r.yasaklar), "risk": r.risk, "dayanak": r.dayanak,
                } for r in rehberler],
            }

    @app.get("/api/kilavuz/sayfa")
    def sayfa_yardimi(ad: str = Query(min_length=1, max_length=100), b: Baglam = Depends(kullanici)):
        with b:
            yardim = kilavuz.SAYFA_YARDIMI.get(ad)
            if not yardim:
                raise HTTPException(404, "Bu sayfa için bağlamsal yardım bulunamadı.")
            ne, nasil, dikkat, rehber_kodu = yardim
            rehber = kilavuz.REHBER.get(rehber_kodu) if rehber_kodu else None
            return {
                "ad": ad, "ne": ne, "nasil": nasil, "dikkat": dikkat,
                "rehber": ({"kod": rehber.kod, "baslik": rehber.baslik, "ikon": rehber.ikon}
                           if rehber else None),
            }

    # ------------------------------------------------------------ kullanıcı yönetimi
    def _kullanici_yonetim_izni(k: dict, yaz: bool = False):
        gerek(k, "Kullanıcılar", yaz=yaz)
        if k["rol"] != M.ROL_SISTEM:
            raise HTTPException(403, "Kullanıcı yönetimini yalnızca Sistem Yöneticisi yapabilir.")

    def _kullanici_rol_dogrula(d, istek):
        if istek.rol not in M.ROLLER:
            raise HTTPException(400, "Geçersiz kullanıcı rolü.")
        if istek.personel_id is not None and not d.q1(
                "SELECT id FROM personel WHERE id = ? AND aktif = 1", (istek.personel_id,)):
            raise HTTPException(400, "Bağlı personel kaydı bulunamadı veya aktif değil.")
        if istek.bolum_id is not None and not d.q1(
                "SELECT id FROM bolum WHERE id = ? AND aktif = 1", (istek.bolum_id,)):
            raise HTTPException(400, "Bölüm kaydı bulunamadı veya aktif değil.")
        aday = {"rol": istek.rol, "personel_id": istek.personel_id, "bolum_id": istek.bolum_id}
        if istek.rol == M.ROL_OGRETMEN and not istek.personel_id:
            raise HTTPException(400, "Öğretmen kullanıcısı bir personel kaydına bağlanmalıdır.")
        if yetki.bolum_kisitli(istek.rol) and not onay.kullanici_bolumu(aday):
            raise HTTPException(400, f"{istek.rol} için bölüm seçilmeli veya bağlı personelin bölümünü tanımlayınız.")
        return aday

    def _yonetici_islemi_izni(k: dict):
        if not yetki.yonetici_mi(k["rol"]):
            raise HTTPException(403, "Bu işlem için yönetici rolü gerekir.")

    def _yedekleme_yonetici_izni(k: dict):
        if k["rol"] not in (M.ROL_SISTEM, M.ROL_MUDUR, M.ROL_SAYMAN):
            raise HTTPException(403, "Yedek dosyalarına yalnız Sistem Yöneticisi, Müdür veya Sayman erişebilir.")

    def _yedek_dosyasi(dosya_adi: str) -> Path:
        ad = (dosya_adi or "").strip()
        if not ad.lower().endswith(".db"):
            raise HTTPException(400, "Yedek dosyası .db uzantılı olmalıdır.")
        yol = (YEDEKLER / ad).resolve()
        if yol.parent != YEDEKLER.resolve():
            raise HTTPException(400, "Geçersiz yedek dosyası adı.")
        if not yol.exists():
            raise HTTPException(404, "Yedek dosyası bulunamadı.")
        return yol

    @app.get("/api/kullanicilar")
    def kullanici_listesi(b: Baglam = Depends(kullanici)):
        with b as d:
            _kullanici_yonetim_izni(b.k)
            kisiler = d.q(
                """SELECT k.id, k.kullanici_adi, k.ad_soyad, k.rol, k.personel_id, k.bolum_id,
                          k.aktif, k.sifre_degismeli, k.son_giris, p.ad_soyad personel_ad,
                          COALESCE(b.ad, pb.ad) bolum_ad
                   FROM kullanici k LEFT JOIN personel p ON p.id = k.personel_id
                   LEFT JOIN bolum b ON b.id = k.bolum_id LEFT JOIN bolum pb ON pb.id = p.bolum_id
                   ORDER BY k.kullanici_adi""")
            for kayit in kisiler:
                kayit["aktif"] = bool(kayit["aktif"])
                kayit["sifre_degismeli"] = bool(kayit["sifre_degismeli"])
            return {
                "kullanicilar": kisiler, "roller": M.ROLLER,
                "yetki_tablosu": [
                    {"sayfa": sayfa, "roller": {
                        rol: yetki.sayfa_yetkisi(rol, sayfa) for rol in M.ROLLER
                    }}
                    for sayfa in yetki.SAYFA_YETKI
                ],
                "personeller": d.q("SELECT id, ad_soyad FROM personel WHERE aktif = 1 ORDER BY ad_soyad"),
                "bolumler": d.q("SELECT id, ad FROM bolum WHERE aktif = 1 ORDER BY ad"),
                "akis_acik": onay.akis_acik(),
            }

    @app.post("/api/kullanicilar")
    def kullanici_ekle(istek: KullaniciIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            _kullanici_yonetim_izni(b.k, yaz=True)
            kullanici_adi = istek.kullanici_adi.strip()
            ad_soyad = istek.ad_soyad.strip()
            if not kullanici_adi or not ad_soyad:
                raise HTTPException(400, "Kullanıcı adı ve ad soyad zorunludur.")
            if d.q1("SELECT id FROM kullanici WHERE lower(kullanici_adi) = lower(?)", (kullanici_adi,)):
                raise HTTPException(409, "Bu kullanıcı adı zaten kullanılıyor.")
            _kullanici_rol_dogrula(d, istek)
            sifre_hashi, tuz = sifre_hashle(istek.sifre)
            with d.islem():
                kullanici_id = d.ekle("kullanici", {
                    "kullanici_adi": kullanici_adi, "ad_soyad": ad_soyad, "rol": istek.rol,
                    "personel_id": istek.personel_id, "bolum_id": istek.bolum_id,
                    "sifre_hash": sifre_hashi, "tuz": tuz, "sifre_degismeli": 1, "aktif": 1,
                })
            return {"id": kullanici_id}

    @app.put("/api/kullanicilar/{kullanici_id}")
    def kullanici_guncelle(kullanici_id: int, istek: KullaniciGuncellemeIstegi,
                           b: Baglam = Depends(kullanici)):
        with b as d:
            _kullanici_yonetim_izni(b.k, yaz=True)
            mevcut = d.q1("SELECT * FROM kullanici WHERE id = ?", (kullanici_id,))
            if not mevcut:
                raise HTTPException(404, "Kullanıcı bulunamadı.")
            if kullanici_id == b.k["id"] and (istek.rol != M.ROL_SISTEM or not istek.aktif):
                raise HTTPException(409, "Kendi Sistem Yöneticisi hesabınızı devre dışı bırakamaz veya rolünü değiştiremezsiniz.")
            _kullanici_rol_dogrula(d, istek)
            if mevcut["rol"] == M.ROL_SISTEM and (istek.rol != M.ROL_SISTEM or not istek.aktif):
                diger = d.deger(
                    "SELECT COUNT(*) FROM kullanici WHERE rol = ? AND aktif = 1 AND id != ?",
                    (M.ROL_SISTEM, kullanici_id), 0)
                if not diger:
                    raise HTTPException(409, "Sistemde en az bir aktif Sistem Yöneticisi kalmalıdır.")
            degerler = {
                "ad_soyad": istek.ad_soyad.strip(), "rol": istek.rol,
                "personel_id": istek.personel_id, "bolum_id": istek.bolum_id,
                "aktif": int(istek.aktif),
            }
            if not degerler["ad_soyad"]:
                raise HTTPException(400, "Ad soyad zorunludur.")
            d.guncelle("kullanici", kullanici_id, degerler)
            return {"tamam": True}

    @app.post("/api/kullanicilar/{kullanici_id}/sifre")
    def kullanici_sifre_sifirla(kullanici_id: int, istek: SifreSifirlamaIstegi,
                                b: Baglam = Depends(kullanici)):
        with b as d:
            _kullanici_yonetim_izni(b.k, yaz=True)
            if not d.q1("SELECT id FROM kullanici WHERE id = ?", (kullanici_id,)):
                raise HTTPException(404, "Kullanıcı bulunamadı.")
            sifre_hashi, tuz = sifre_hashle(istek.sifre)
            d.guncelle("kullanici", kullanici_id, {
                "sifre_hash": sifre_hashi, "tuz": tuz, "sifre_degismeli": 1,
            })
            d.ex("UPDATE mobil_oturum SET aktif = 0 WHERE kullanici_id = ?", (kullanici_id,))
            return {"tamam": True}

    @app.delete("/api/kullanicilar/{kullanici_id}")
    def kullanici_sil(kullanici_id: int, b: Baglam = Depends(kullanici)):
        with b as d:
            _kullanici_yonetim_izni(b.k, yaz=True)
            mevcut = d.q1("SELECT * FROM kullanici WHERE id = ?", (kullanici_id,))
            if not mevcut:
                raise HTTPException(404, "Kullanıcı bulunamadı.")
            if kullanici_id == b.k["id"]:
                raise HTTPException(409, "Kendi hesabınızı silemezsiniz.")
            if mevcut["rol"] == M.ROL_SISTEM and mevcut["aktif"]:
                diger = d.deger(
                    "SELECT COUNT(*) FROM kullanici WHERE rol = ? AND aktif = 1 AND id != ?",
                    (M.ROL_SISTEM, kullanici_id), 0)
                if not diger:
                    raise HTTPException(409, "Son aktif Sistem Yöneticisi silinemez.")
            if d.q1("SELECT id FROM onay_kaydi WHERE kullanici = ? LIMIT 1", (mevcut["kullanici_adi"],)):
                raise HTTPException(409, "Onay geçmişi bulunan kullanıcı silinemez; hesabını pasifleştiriniz.")
            with d.islem():
                d.ex("DELETE FROM mobil_oturum WHERE kullanici_id = ?", (kullanici_id,))
                d.sil("kullanici", kullanici_id)
            return {"tamam": True}

    @app.put("/api/kullanicilar/onay-akisi")
    def onay_akisi_ayarla(istek: OnayAkisiIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            _kullanici_yonetim_izni(b.k, yaz=True)
            if not istek.acik and onay.bekleyenler():
                raise HTTPException(
                    409, "Onay sürecinde bekleyen belgeler var. Önce bu belgeleri sonuçlandırınız.")
            onay.akis_ayarla(istek.acik)
            d.log("Onay akışı " + ("açıldı" if istek.acik else "kapatıldı"))
            return {"tamam": True, "akis_acik": onay.akis_acik()}

    # ------------------------------------------------------------ yedekleme
    @app.get("/api/yedekler")
    def yedekler(b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["islem"])
            _yedekleme_yonetici_izni(b.k)
            kayitlar = []
            for p in sorted(YEDEKLER.glob("*.db"), key=lambda x: x.stat().st_mtime, reverse=True):
                s = p.stat()
                kayitlar.append({
                    "dosya_adi": p.name,
                    "tarih": datetime.fromtimestamp(s.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "boyut_kb": round(s.st_size / 1024),
                })
            return {"yedekler": kayitlar, "yonetici": yetki.yonetici_mi(b.k["rol"])}

    @app.post("/api/yedekler")
    def yedek_olustur(b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["islem"])
            _yedekleme_yonetici_izni(b.k)
            yol = d.yedekle()
            s = yol.stat()
            return {"dosya_adi": yol.name,
                    "tarih": datetime.fromtimestamp(s.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "boyut_kb": round(s.st_size / 1024)}

    @app.get("/api/yedekler/{dosya_adi}")
    def yedek_indir(dosya_adi: str, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["islem"])
            _yedekleme_yonetici_izni(b.k)
            yol = _yedek_dosyasi(dosya_adi)
            return {"dosya_adi": yol.name, "icerik": base64.b64encode(yol.read_bytes()).decode("ascii")}

    @app.post("/api/yedekler/yukle")
    def yedek_yukle(istek: YedekYukleIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["islem"], yaz=True)
            _yonetici_islemi_izni(b.k)
            if not istek.dosya_adi.lower().endswith(".db"):
                raise HTTPException(400, "Yalnız .db veritabanı yedek dosyaları yüklenebilir.")
            try:
                icerik = base64.b64decode(istek.icerik, validate=True)
            except (ValueError, binascii.Error):
                raise HTTPException(400, "Yedek dosyasının içeriği geçerli Base64 değil.") from None
            if len(icerik) > 100 * 1024 * 1024:
                raise HTTPException(413, "Yedek dosyası 100 MB sınırını aşıyor.")
            if not icerik.startswith(b"SQLite format 3\x00"):
                raise HTTPException(400, "Dosya geçerli bir SQLite veritabanı değil.")
            YEDEKLER.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix=".dose-yedek-kontrol-", suffix=".db",
                                             dir=YEDEKLER, delete=False) as gecici:
                gecici_yolu = Path(gecici.name)
                gecici.write(icerik)
            try:
                try:
                    kontrol = sqlite3.connect(f"{gecici_yolu.resolve().as_uri()}?mode=ro", uri=True)
                    try:
                        saglik = kontrol.execute("PRAGMA integrity_check").fetchone()
                        tablolar = {r[0] for r in kontrol.execute(
                            "SELECT name FROM sqlite_master WHERE type = 'table'")}
                    finally:
                        kontrol.close()
                except sqlite3.DatabaseError:
                    raise HTTPException(400, "Yedek dosyası okunamıyor veya bozuk.") from None
                if not saglik or saglik[0] != "ok":
                    raise HTTPException(400, "Yedek veritabanının bütünlük denetimi başarısız.")
                gerekli = {"kurum", "kullanici", "bolum", "personel", "islem_log"}
                if not gerekli.issubset(tablolar):
                    raise HTTPException(400, "Dosya bu uygulamaya ait uyumlu bir veritabanı yedeği değil.")
                ad = f"dose_yedek_yuklenen_{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(4)}.db"
                yol = YEDEKLER / ad
                yol.write_bytes(icerik)
            finally:
                gecici_yolu.unlink(missing_ok=True)
            d.log("Yedek dosyası yükleme", detay=f"{istek.dosya_adi} → {ad}")
            return {"dosya_adi": ad, "boyut_kb": round(len(icerik) / 1024)}

    @app.post("/api/yedekler/geri-yukle")
    def yedek_geri_yukle(istek: YedekGeriYukleIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["islem"], yaz=True)
            _yonetici_islemi_izni(b.k)
            if istek.onay_metni.strip().upper().replace(" ", "") != "GERIYUKLE":
                raise HTTPException(400, "Geri yükleme için onay metni olarak 'GERI YUKLE' yazılmalıdır.")
            yol = _yedek_dosyasi(istek.dosya_adi)
            d.geri_yukle(yol)
            return {"tamam": True, "dosya_adi": yol.name}

    # ------------------------------------------------------------ onaylar
    @app.get("/api/onay")
    def onaylar(b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["onay"])
            bana = onay.bekleyenler(b.k)
            benim = {(x["belge_turu"], x["belge_id"]) for x in bana}
            diger = [x for x in onay.bekleyenler() if (x["belge_turu"], x["belge_id"]) not in benim
                     and kapsamda(b.k, x["belge_turu"], x["belge_id"])]
            return {"akis_acik": onay.akis_acik(), "bana_bekleyen": bana, "diger_bekleyen": diger}

    def _belge_detayi(d, tur: str, bid: int) -> dict:
        if tur == "Sipariş":
            return _siparis_detayi(d, bid)
        if tur == "Fazla Çalışma":
            return d.q1("""SELECT f.*, p.ad_soyad, p.dose_gorevi, s.siparis_no FROM fazla_calisma f
                           JOIN personel p ON p.id = f.personel_id LEFT JOIN siparis s ON s.id = f.siparis_id
                           WHERE f.id = ?""", (bid,)) or {}
        if tur == "Parça Başı":
            pb = d.q1("""SELECT pb.*, s.siparis_no, s.konu FROM parca_basi pb LEFT JOIN siparis s ON s.id = pb.siparis_id
                         WHERE pb.id = ?""", (bid,)) or {}
            pb["satirlar"] = d.q("""SELECT r.kisi_turu, COALESCE(p.ad_soyad, o.ad_soyad) ad_soyad, r.brut, r.gelir_vergisi,
                                           r.damga_vergisi, r.sgk, r.net
                                    FROM parca_basi_satir r
                                    LEFT JOIN personel p ON r.kisi_turu = 'Personel' AND p.id = r.kisi_id
                                    LEFT JOIN ogrenci o ON r.kisi_turu = 'Öğrenci' AND o.id = r.kisi_id
                                    WHERE r.parca_basi_id = ? ORDER BY r.kisi_turu, ad_soyad""", (bid,))
            return pb
        return d.q1("SELECT * FROM yil_sonu WHERE yil = ?", (bid,)) or {}

    def _hazirlayabilir(k, tur, bid) -> bool:
        return etkin_yetki(k, yetki.BELGE_SAYFASI[tur]) == "y" and kapsamda(k, tur, bid)

    @app.get("/api/onay/{tur}/{bid}")
    def onay_belgesi(tur: str, bid: int, b: Baglam = Depends(kullanici)):
        tur = _tur(tur)
        with b as d:
            if not etkin_yetki(b.k, yetki.BELGE_SAYFASI[tur]) and not yetki.sayfa_yetkisi(b.k["rol"], MOBIL_MODULLER["onay"]):
                raise HTTPException(403, "Bu belgeyi görme yetkiniz bulunmuyor.")
            if not kapsamda(b.k, tur, bid):
                raise HTTPException(403, "Bu belge bölümünüzün kapsamı dışında.")
            dr = onay.durum(tur, bid)
            akis = onay.akis_acik()
            hazir = _hazirlayabilir(b.k, tur, bid)
            onayli = dr["durum"] == onay.ONAYLANDI or onay.KANCALAR[tur]["onayli"](bid)
            return {"tur": tur, "id": bid, "ozet": onay.ozet(tur, bid), "durum": dr, "durum_metni": onay.durum_metni(dr),
                    "asamalar": [{"ad": a, "rol": r} for a, r in yetki.AKISLAR[tur]], "gecmis": onay.gecmis(tur, bid),
                    "kontrol_hatalari": onay.KANCALAR[tur]["kontrol"](bid), "detay": _belge_detayi(d, tur, bid),
                    "akis_acik": akis,
                    "islemler": {"karar": not d.salt_okunur and onay.yetkili_mi(dr, b.k),
                                 "gonder": akis and hazir and dr["durum"] in (onay.HAZIRLANIYOR, onay.IADE) and not onayli,
                                 "geri_cek": akis and hazir and dr["durum"] == onay.BEKLIYOR,
                                 "dogrudan_onay": not akis and hazir and not onayli}}

    @app.post("/api/onay/{tur}/{bid}/karar")
    def onay_karar(tur: str, bid: int, istek: KararIstegi, b: Baglam = Depends(kullanici)):
        tur = _tur(tur)
        with b as d:
            gerek(b.k, MOBIL_MODULLER["onay"], yaz=True)
            if not kapsamda(b.k, tur, bid):
                raise HTTPException(403, "Bu belge bölümünüzün kapsamı dışında.")
            onay.karar_ver(tur, bid, b.k, istek.onay, istek.aciklama.strip())
            return {"durum_metni": onay.durum_metni(onay.durum(tur, bid))}

    def _hazirlama_islemi(tur, bid, b: Baglam, islev, *args):
        tur = _tur(tur)
        with b as d:
            gerek(b.k, yetki.BELGE_SAYFASI[tur], yaz=True)
            if not kapsamda(b.k, tur, bid):
                raise HTTPException(403, "Bu belge bölümünüzün kapsamı dışında.")
            islev(tur, bid, b.k, *args)
            return {"durum_metni": onay.durum_metni(onay.durum(tur, bid))}

    @app.post("/api/onay/{tur}/{bid}/gonder")
    def onay_gonder(tur: str, bid: int, istek: AciklamaIstegi, b: Baglam = Depends(kullanici)):
        if not onay.akis_acik():
            raise HTTPException(400, "Onay akışı kapalı; belgeyi doğrudan onaylayabilirsiniz.")
        return _hazirlama_islemi(tur, bid, b, onay.gonder, istek.aciklama.strip())

    @app.post("/api/onay/{tur}/{bid}/geri-cek")
    def onay_geri_cek(tur: str, bid: int, istek: AciklamaIstegi, b: Baglam = Depends(kullanici)):
        return _hazirlama_islemi(tur, bid, b, onay.geri_cek, istek.aciklama.strip())

    @app.post("/api/onay/{tur}/{bid}/dogrudan")
    def onay_dogrudan(tur: str, bid: int, b: Baglam = Depends(kullanici)):
        if onay.akis_acik():
            raise HTTPException(400, "Onay akışı açık; belgeyi onaya gönderiniz.")
        return _hazirlama_islemi(tur, bid, b, onay.dogrudan_onayla)

    # ------------------------------------------------------------ siparişler
    def _siparis_detayi(d, sid: int) -> dict:
        s = d.q1("""SELECT s.*, c.unvan, b.ad bolum_ad,
                           (SELECT COALESCE(SUM(matrah), 0) FROM fatura f WHERE f.siparis_id = s.id AND f.tur = 'Satış'
                            AND f.iptal = 0) faturalanan
                    FROM siparis s LEFT JOIN cari c ON c.id = s.cari_id LEFT JOIN bolum b ON b.id = s.bolum_id
                    WHERE s.id = ?""", (sid,))
        if not s:
            raise HTTPException(404, "Sipariş bulunamadı (silinmiş olabilir).")
        s["kalemler"] = d.q("""SELECT k.*, u.ad urun_ad FROM siparis_kalem k LEFT JOIN urun u ON u.id = k.urun_id
                               WHERE k.siparis_id = ? ORDER BY k.id""", (sid,))
        t = siparis_kaydi_tahsisi(s, d.parametreler(int((s["tarih"] or str(date.today().year))[:4])))
        s["tahsis"] = {"kar": t.kar, "faaliyet": t.faaliyet, "malzeme": t.malzeme, "azami_iscilik": t.azami_iscilik,
                       "iscilik": t.iscilik, "ogrenci_hakki": t.ogrenci_hakki, "personel_iscilik": t.personel_iscilik,
                       "asgari_pesinat": t.asgari_pesinat, "hatalar": t.hatalar, "uyarilar": t.uyarilar}
        s["surum"] = d.son_islem_no()
        return s

    @app.get("/api/secenekler/siparis")
    def siparis_secenekleri(b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["siparis"])
            kisit = bolum_kisiti(b.k)
            bolumler = d.q("SELECT id, ad FROM bolum WHERE aktif = 1" + (" AND id = ?" if kisit else "") + " ORDER BY ad",
                           (kisit,) if kisit else ())
            return {"cariler": d.q("SELECT id, unvan, kamu_kurumu FROM cari WHERE aktif = 1 ORDER BY unvan"),
                    "bolumler": bolumler,
                    "urunler": d.q("SELECT id, kod, ad, birim, satis_fiyati, kdv_orani, bolum_id, ucret_esasi FROM urun "
                                   "WHERE aktif = 1" + (" AND (bolum_id = ? OR bolum_id IS NULL)" if kisit else "") +
                                   " ORDER BY ad", (kisit,) if kisit else ()),
                    "ucret_esaslari": M.UCRET_ESASLARI,
                    "yazabilir": etkin_yetki(b.k, MOBIL_MODULLER["siparis"]) == "y"}

    @app.get("/api/siparisler")
    def siparisler(yil: int = Query(default_factory=lambda: date.today().year), durum: str = "acik", ara: str = "",
                   b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["siparis"])
            sql = """SELECT s.id, s.siparis_no, s.tarih, s.konu, s.durum, s.ucret_esasi, s.sozlesme_bedeli, s.teslim_tarihi,
                            s.bolum_id, c.unvan, b.ad bolum_ad
                     FROM siparis s LEFT JOIN cari c ON c.id = s.cari_id LEFT JOIN bolum b ON b.id = s.bolum_id
                     WHERE substr(s.tarih, 1, 4) = ?"""
            prm: list = [str(yil)]
            kisit = bolum_kisiti(b.k)
            if kisit:
                sql += " AND s.bolum_id = ?"
                prm.append(kisit)
            if durum == "acik":
                sql += " AND s.durum NOT IN ('Kapandı', 'İptal', 'Faturalandı')"
            elif durum and durum != "tumu":
                sql += " AND s.durum = ?"
                prm.append(durum)
            if ara.strip():
                sql += " AND (LOWER(s.siparis_no) LIKE ? OR LOWER(s.konu) LIKE ? OR LOWER(c.unvan) LIKE ?)"
                prm += [f"%{ara.strip().lower()}%"] * 3
            satirlar = d.q(sql + " ORDER BY s.tarih DESC, s.id DESC LIMIT 300", prm)
            durumlar = onay.durumlar("Sipariş")
            for s in satirlar:
                s["onay"] = _onay_metni(durumlar, s["id"], s["durum"] not in ("Teklif", "İptal"))
            return {"siparisler": satirlar, "toplam": yuvarla(sum(s["sozlesme_bedeli"] or 0 for s in satirlar)),
                    "yazabilir": etkin_yetki(b.k, MOBIL_MODULLER["siparis"]) == "y"}

    @app.get("/api/siparisler/disa-aktar")
    def siparisleri_disa_aktar(yil: int = Query(default_factory=lambda: date.today().year), durum: str = "acik",
                               ara: str = "", b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["siparis"])
            sql = """SELECT s.siparis_no, s.tarih, c.unvan, b.ad bolum, s.konu, s.ucret_esasi, s.durum,
                            s.sozlesme_bedeli, s.pesinat, s.iscilik_tutari, s.teslim_tarihi,
                            (SELECT COALESCE(SUM(matrah), 0) FROM fatura f
                             WHERE f.siparis_id = s.id AND f.tur = 'Satış' AND f.iptal = 0) faturalanan
                     FROM siparis s LEFT JOIN cari c ON c.id = s.cari_id LEFT JOIN bolum b ON b.id = s.bolum_id
                     WHERE substr(s.tarih, 1, 4) = ?"""
            prm: list[Any] = [str(yil)]
            kisit = bolum_kisiti(b.k)
            if kisit:
                sql += " AND s.bolum_id = ?"
                prm.append(kisit)
            if durum == "acik":
                sql += " AND s.durum NOT IN ('Kapandı', 'İptal', 'Faturalandı')"
            elif durum not in ("tumu", ""):
                sql += " AND s.durum = ?"
                prm.append(durum)
            if ara.strip():
                sql += " AND (LOWER(s.siparis_no) LIKE ? OR LOWER(s.konu) LIKE ? OR LOWER(c.unvan) LIKE ?)"
                prm.extend([f"%{ara.strip().lower()}%"] * 3)
            rows = d.q(sql + " ORDER BY s.tarih DESC, s.id DESC LIMIT 300", prm)
            with tempfile.TemporaryDirectory(prefix="dose-siparis-") as dizin:
                yol = excel.disa_aktar(
                    Path(dizin) / f"Siparisler_{yil}.xlsx",
                    [("Siparişler", ["Sipariş No", "Tarih", "Müşteri", "Bölüm", "Konu", "Ücret Esası", "Durum",
                                     "Bedel (KDV hariç)", "Peşinat", "İşçilik", "Teslim Tarihi", "Faturalanan"],
                      [[r["siparis_no"], r["tarih"], r["unvan"] or "", r["bolum"] or "", r["konu"] or "",
                        r["ucret_esasi"] or "", r["durum"] or "", r["sozlesme_bedeli"] or 0, r["pesinat"] or 0,
                        r["iscilik_tutari"] or 0, r["teslim_tarihi"] or "", r["faturalanan"] or 0] for r in rows])])
                icerik = yol.read_bytes()
            d.log("Sipariş dışa aktarma", "siparis", detay=str(yil))
            return {"dosya_adi": yol.name, "icerik": base64.b64encode(icerik).decode("ascii")}

    @app.get("/api/siparisler/{sid}")
    def siparis(sid: int, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["siparis"])
            s = _siparis_detayi(d, sid)
            kisit = bolum_kisiti(b.k)
            if kisit and s["bolum_id"] != kisit:
                raise HTTPException(403, "Bu sipariş bölümünüzün kapsamı dışında.")
            dr = d.q1("SELECT * FROM onay_durum WHERE belge_turu = 'Sipariş' AND belge_id = ?", (sid,))
            s["onay"] = _onay_metni({sid: dr} if dr else {}, sid, s["durum"] not in ("Teklif", "İptal"))
            s["onay_gecmisi"] = onay.gecmis("Sipariş", sid)
            yazabilir = etkin_yetki(b.k, MOBIL_MODULLER["siparis"]) == "y"
            s["duzenlenebilir"] = (yazabilir
                                   and s["durum"] == "Teklif"
                                   and (not dr or dr["durum"] not in (onay.BEKLIYOR, onay.ONAYLANDI)))
            s["faturalandirabilir"] = (etkin_yetki(b.k, FATURA_SAYFASI["Satış"]) == "y"
                                       and (not onay.akis_acik() or (dr and dr["durum"] == onay.ONAYLANDI)))
            s["stok_cikisi_yapabilir"] = (etkin_yetki(b.k, MOBIL_MODULLER["stok"]) == "y")
            s["satis_belge_turleri"] = M.SATIS_BELGE_TURLERI
            s["tevkifat_turleri"] = list(M.TEVKIFAT_ORANLARI)
            s["avans_kalan"] = yuvarla(
                (d.deger("SELECT SUM(tutar) FROM kasa_banka WHERE siparis_id = ? AND tur = 'Peşinat/Avans Tahsilatı'",
                         (sid,), 0.0) or 0)
                - (d.deger("SELECT SUM(avans_mahsup) FROM fatura WHERE siparis_id = ? AND iptal = 0", (sid,), 0.0) or 0))
            onay_yonetici = b.k["rol"] in yetki.GERI_ALABILEN
            onay_engeli = dr and dr["durum"] in (onay.BEKLIYOR, onay.ONAYLANDI) and not onay_yonetici
            s["silinebilir"] = (yazabilir and s["durum"] == "Teklif" and not onay_engeli
                                and not d.deger("SELECT COUNT(*) FROM fatura WHERE siparis_id = ?", (sid,))
                                and not d.deger("SELECT COUNT(*) FROM parca_basi WHERE siparis_id = ?", (sid,)))
            return s

    @app.post("/api/siparisler")
    def siparis_ekle(istek: SiparisIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["siparis"], yaz=True)
            veri = istek.model_dump(exclude={"surum"})
            sid, no, uyarilar = siparis_taslagi_kaydet(d, veri, bolum_kisiti(b.k))
            return {"id": sid, "siparis_no": no, "uyarilar": uyarilar}

    @app.put("/api/siparisler/{sid}")
    def siparis_guncelle(sid: int, istek: SiparisIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["siparis"], yaz=True)
            if istek.surum is None:
                raise HTTPException(400, "Sipariş sürümü gereklidir; kaydı yeniden açıp tekrar deneyiniz.")
            s = _siparis_detayi(d, sid)
            kisit = bolum_kisiti(b.k)
            if kisit and s["bolum_id"] != kisit:
                raise HTTPException(403, "Bu sipariş bölümünüzün kapsamı dışında.")
            if s["durum"] != "Teklif":
                raise HTTPException(400, "Yalnız teklif aşamasındaki iş talepleri bu ekrandan değiştirilebilir.")
            durum = onay.durum("Sipariş", sid)["durum"]
            if durum in (onay.BEKLIYOR, onay.ONAYLANDI):
                raise HTTPException(400, "Onay sürecindeki veya onaylanmış sipariş değiştirilemez.")
            d.cakisma_denetle("siparis", sid, istek.surum)
            veri = istek.model_dump(exclude={"surum"})
            _, no, uyarilar = siparis_taslagi_kaydet(d, veri, kisit, siparis_id=sid)
            return {"id": sid, "siparis_no": no, "uyarilar": uyarilar,
                    "surum": d.son_islem_no()}

    @app.delete("/api/siparisler/{sid}")
    def siparis_sil(sid: int, surum: int = Query(..., ge=0), b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["siparis"], yaz=True)
            s = _siparis_detayi(d, sid)
            kisit = bolum_kisiti(b.k)
            if kisit and s["bolum_id"] != kisit:
                raise HTTPException(403, "Bu sipariş bölümünüzün kapsamı dışında.")
            d.cakisma_denetle("siparis", sid, surum)
            if s["durum"] != "Teklif":
                raise HTTPException(400, "Yalnız teklif aşamasındaki iş talepleri silinebilir.")
            durum = onay.durum("Sipariş", sid)["durum"]
            if durum in (onay.BEKLIYOR, onay.ONAYLANDI) and b.k["rol"] not in yetki.GERI_ALABILEN:
                raise HTTPException(400, "Onay sürecindeki veya onaylanmış sipariş silinemez; durumunu iptal ediniz.")
            iliskili = any(d.deger(f"SELECT COUNT(*) FROM {tablo} WHERE siparis_id = ?", (sid,))
                           for tablo in ("fatura", "parca_basi"))
            if iliskili:
                raise HTTPException(400, "Siparişe bağlı fatura veya parça başı kaydı var; silinemez.")
            with d.islem():
                for tablo in ("siparis_kalem", "siparis_gorevli", "siparis_is_plani"):
                    d.ex(f"DELETE FROM {tablo} WHERE siparis_id = ?", (sid,))
                onay.sil("Sipariş", sid)
                d.sil("siparis", sid)
            return {"tamam": True}

    @app.post("/api/siparisler/{sid}/faturala")
    def siparis_faturalandir(sid: int, istek: SiparistenFaturaIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["siparis"])
            gerek(b.k, FATURA_SAYFASI["Satış"], yaz=True)
            s = _siparis_detayi(d, sid)
            kisit = bolum_kisiti(b.k)
            if kisit and s["bolum_id"] != kisit:
                raise HTTPException(403, "Bu sipariş bölümünüzün kapsamı dışında.")
            if onay.akis_acik() and onay.durum("Sipariş", sid)["durum"] != onay.ONAYLANDI:
                raise HTTPException(400, "Onay akışı açık; onaylanmamış sipariş faturalandırılamaz.")
            try:
                tarih = date.fromisoformat(istek.tarih)
            except ValueError:
                raise HTTPException(400, "Fatura tarihi YYYY-AA-GG biçiminde olmalıdır.") from None
            if tarih.isoformat() != istek.tarih:
                raise HTTPException(400, "Fatura tarihi YYYY-AA-GG biçiminde olmalıdır.")
            if istek.belge_turu not in M.SATIS_BELGE_TURLERI:
                raise HTTPException(400, "Satış belgesi türü geçersiz.")
            if istek.tevkifat not in M.TEVKIFAT_ORANLARI:
                raise HTTPException(400, "KDV tevkifat türü geçersiz.")
            if istek.belge_no.strip() and d.q1(
                    "SELECT id FROM fatura WHERE tur = 'Satış' AND belge_no = ? AND iptal = 0 AND substr(tarih, 1, 4) = ?",
                    (istek.belge_no.strip(), istek.tarih[:4])):
                raise HTTPException(400, "Bu belge numarası aynı yıl içinde zaten kayıtlı.")

            faturalama = d.q("""SELECT k.urun_id, SUM(k.miktar) miktar
                                FROM fatura_kalem k JOIN fatura f ON f.id = k.fatura_id
                                WHERE f.siparis_id = ? AND f.tur = 'Satış' AND f.iptal = 0 AND k.urun_id IS NOT NULL
                                GROUP BY k.urun_id""", (sid,))
            onceki = {r["urun_id"]: r["miktar"] or 0 for r in faturalama}
            kalemler, onceki_kalan = [], dict(onceki)
            for kl in s["kalemler"]:
                if not kl.get("urun_id"):
                    raise HTTPException(400, "Ürün seçilmemiş sipariş kalemleri otomatik faturalandırılamaz.")
                onceki_miktar = onceki_kalan.get(kl["urun_id"], 0)
                siparis_miktari = kl.get("miktar") or 0
                if onceki_miktar >= siparis_miktari:
                    onceki_kalan[kl["urun_id"]] = yuvarla(onceki_miktar - siparis_miktari, 3)
                    continue
                kalan = yuvarla(siparis_miktari - onceki_miktar, 3)
                if kalan <= 0:
                    continue
                onceki_kalan[kl["urun_id"]] = 0
                urun = d.q1("SELECT kdv_orani FROM urun WHERE id = ?", (kl["urun_id"],))
                kalem = {"urun_id": kl["urun_id"], "malzeme_id": None, "aciklama": kl.get("aciklama"),
                         "miktar": kalan, "birim": kl.get("birim") or "Adet",
                         "birim_fiyat": kl.get("birim_fiyat") or 0, "kdv_orani": s["kdv_orani"] or 0,
                         "iskonto_orani": kl.get("iskonto_orani") or 0}
                if urun:
                    kalem["kdv_orani"] = s["kdv_orani"] if s.get("kdv_orani") is not None else urun["kdv_orani"]
                kalem["iskonto"] = yuvarla(kalem_tutari(kalem)[0] * kalem["iskonto_orani"])
                kalem["tutar"] = kalem_tutari(kalem)[2]
                kalem["kdv"] = yuvarla(kalem["tutar"] * kalem["kdv_orani"])
                kalemler.append(kalem)
            if not kalemler:
                raise HTTPException(400, "Faturalandırılacak kalan sipariş miktarı bulunmuyor.")
            hatalar = kalem_hatalari(kalemler)
            if hatalar:
                raise HTTPException(400, "\n".join(hatalar))
            toplam = belge_toplami(kalemler, M.TEVKIFAT_ORANLARI[istek.tevkifat])
            avans_alinan = d.deger(
                "SELECT SUM(tutar) FROM kasa_banka WHERE siparis_id = ? AND tur = 'Peşinat/Avans Tahsilatı'", (sid,), 0.0) or 0
            avans_mahsup = d.deger(
                "SELECT SUM(avans_mahsup) FROM fatura WHERE siparis_id = ? AND iptal = 0", (sid,), 0.0) or 0
            avans_kalan = yuvarla(avans_alinan - avans_mahsup)
            mahsup = min(avans_kalan, toplam.net_tutar) if istek.avans_mahsup is None else istek.avans_mahsup
            if mahsup > toplam.net_tutar + 0.005:
                raise HTTPException(400, "Avans mahsubu faturanın net tutarını aşamaz.")
            if mahsup > avans_kalan + 0.005:
                raise HTTPException(400, "Mahsup tutarı tahsil edilmiş ve kullanılmamış avansı aşamaz.")
            belge_no = istek.belge_no.strip() or d.sonraki_no("satis", tarih.year, "SF")
            with d.islem():
                fatura_id = d.ekle("fatura", {
                    "tur": "Satış", "belge_turu": istek.belge_turu, "belge_no": belge_no, "tarih": istek.tarih,
                    "cari_id": s["cari_id"], "siparis_id": sid, "aciklama": s.get("konu"), "iskonto": toplam.iskonto,
                    "matrah": toplam.matrah, "kdv": toplam.kdv, "tevkifat": istek.tevkifat,
                    "tevkif_kdv": toplam.tevkif_kdv, "stopaj_turu": "Yok", "stopaj_orani": 0, "stopaj": 0,
                    "genel_toplam": toplam.genel_toplam, "net_tutar": toplam.net_tutar,
                    "avans_mahsup": mahsup,
                })
                for kalem in kalemler:
                    kalem["fatura_id"] = fatura_id
                    d.ekle("fatura_kalem", kalem, log=False)
                    mamul = d.deger("SELECT mamul_malzeme_id FROM urun WHERE id = ?", (kalem["urun_id"],), None)
                    if mamul:
                        d.ekle("stok_hareket", {
                            "tarih": istek.tarih, "malzeme_id": mamul, "yon": "Çıkış", "miktar": kalem["miktar"],
                            "birim_fiyat": muhasebe.ortalama_maliyet(mamul, istek.tarih), "kaynak": "Fatura",
                            "kaynak_id": fatura_id, "siparis_id": sid, "aciklama": f"Satış {belge_no}",
                        }, log=False)
                muhasebe.fatura_kaydi(fatura_id)
            d.log("Siparişten satış faturası oluşturma", "siparis", sid, detay=belge_no)
            return {"id": fatura_id, "belge_no": belge_no, "matrah": toplam.matrah,
                    "genel_toplam": toplam.genel_toplam, "net_tutar": yuvarla(toplam.net_tutar - mahsup),
                    "avans_mahsup": mahsup, "faturalanan_kalem_sayisi": len(kalemler)}

    @app.post("/api/siparisler/{sid}/stok-cikisi")
    def siparis_stok_cikisi(sid: int, istek: SiparisStokCikisiIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["siparis"])
            gerek(b.k, MOBIL_MODULLER["stok"], yaz=True)
            s = _siparis_detayi(d, sid)
            kisit = bolum_kisiti(b.k)
            if kisit and s["bolum_id"] != kisit:
                raise HTTPException(403, "Bu sipariş bölümünüzün kapsamı dışında.")
            try:
                tarih = date.fromisoformat(istek.tarih)
            except ValueError:
                raise HTTPException(400, "Stok hareketi tarihi YYYY-AA-GG biçiminde olmalıdır.") from None
            if tarih.isoformat() != istek.tarih:
                raise HTTPException(400, "Stok hareketi tarihi YYYY-AA-GG biçiminde olmalıdır.")
            nedenler = ["Üretime Sevk", "Sayım Noksanı / Fire", "Bozulma / Hurda", "Diğer"]
            if istek.neden not in nedenler:
                raise HTTPException(400, "Stok çıkış nedeni geçersiz.")
            malzeme = d.q1("SELECT id FROM malzeme WHERE id = ? AND aktif = 1", (istek.malzeme_id,))
            if not malzeme:
                raise HTTPException(404, "Malzeme bulunamadı veya pasif.")
            with d.islem():
                kalan = muhasebe.stok_miktari(istek.malzeme_id)
                if istek.miktar > kalan + 1e-9:
                    raise HTTPException(400, f"Yetersiz stok. Mevcut: {kalan:g}")
                fiyat = muhasebe.ortalama_maliyet(istek.malzeme_id, istek.tarih)
                aciklama = istek.neden + (f" - {istek.aciklama.strip()}" if istek.aciklama.strip() else "")
                hareket_id = d.ekle("stok_hareket", {
                    "tarih": istek.tarih, "malzeme_id": istek.malzeme_id, "yon": "Çıkış",
                    "miktar": istek.miktar, "birim_fiyat": fiyat, "kaynak": "Manuel",
                    "siparis_id": sid, "aciklama": aciklama,
                })
                muhasebe.stok_cikis_kaydi(hareket_id)
            return {"id": hareket_id, "birim_fiyat": fiyat,
                    "tutar": yuvarla(istek.miktar * fiyat)}

    @app.get("/api/siparisler/{sid}/belge/{tur}")
    def siparis_belgesi(sid: int, tur: str, b: Baglam = Depends(kullanici)):
        belge_fonksiyonlari = {
            "kesif": ("Kesif_Is_Plani", belgeler.kesif_is_plani),
            "proforma": ("Proforma", belgeler.proforma_fatura),
            "teklif": ("Teklif", belgeler.teklif_mektubu),
            "sozlesme": ("Sozlesme", belgeler.siparis_sozlesmesi),
            "maliyet": ("On_Maliyet", belgeler.on_maliyet_cizelgesi),
            "malzeme": ("Malzeme_Listesi", belgeler.siparis_malzeme_listesi),
            "gecici": ("Gecici_Kabul", belgeler.gecici_kabul_tutanagi),
            "istek": ("Calisma_Istek", belgeler.calisma_istek_listesi),
            "gorev": ("Gorevlendirme", belgeler.gorevlendirme_onayi),
            "kabul": ("Muayene_Kabul", belgeler.muayene_kabul_tutanagi),
        }
        if tur not in belge_fonksiyonlari:
            raise HTTPException(404, "Sipariş belge türü bulunamadı.")
        with b as d:
            gerek(b.k, MOBIL_MODULLER["siparis"])
            s = _siparis_detayi(d, sid)
            kisit = bolum_kisiti(b.k)
            if kisit and s["bolum_id"] != kisit:
                raise HTTPException(403, "Bu sipariş bölümünüzün kapsamı dışında.")
            if tur == "proforma":
                gerek(b.k, MOBIL_MODULLER["siparis"], yaz=True)
                guncel = {}
                if not s.get("proforma_no"):
                    guncel["proforma_no"] = d.sonraki_no("proforma", int((s.get("tarih") or str(date.today()))[:4]), "PRF")
                if not s.get("proforma_tarih"):
                    guncel["proforma_tarih"] = date.today().isoformat()
                if s.get("proforma_gecerlilik_gun") in (None, ""):
                    guncel["proforma_gecerlilik_gun"] = 30
                if guncel:
                    d.guncelle("siparis", sid, guncel)
                    s.update(guncel)
            prefix, fonksiyon = belge_fonksiyonlari[tur]
            p = d.parametreler(int((s.get("tarih") or str(date.today()))[:4]))
            with tempfile.TemporaryDirectory() as gecici:
                yol = Path(gecici) / f"{prefix}_{s.get('siparis_no') or sid}.pdf"
                if tur == "sozlesme":
                    fonksiyon(yol, sid, esas_kurallari(s.get("ucret_esasi"), p))
                elif tur == "maliyet":
                    fonksiyon(yol, sid, siparis_kaydi_tahsisi(s, p), p)
                elif tur == "malzeme":
                    fonksiyon(yol, sid, p)
                else:
                    fonksiyon(yol, sid)
                icerik = yol.read_bytes()
                dosya_adi = yol.name
            d.log("Sipariş belgesi oluşturma", "siparis", sid, detay=tur)
            return {"dosya_adi": dosya_adi, "icerik": base64.b64encode(icerik).decode("ascii")}

    # ------------------------------------------------------------ fazla çalışma
    def _fc_kosul(k: dict) -> tuple[str, list]:
        if k["rol"] == M.ROL_OGRETMEN:
            return " AND f.personel_id = ?", [k.get("personel_id") or -1]
        kisit = bolum_kisiti(k)
        if kisit:
            return " AND COALESCE(s.bolum_id, p.bolum_id) = ?", [kisit]
        return "", []

    def _fc_personel_denetle(d, k: dict, istek: FazlaIstegi) -> FazlaIstegi:
        if k["rol"] == M.ROL_OGRETMEN:
            if not k.get("personel_id"):
                raise IslemHatasi("Kullanıcı hesabınız bir personel kaydına bağlı değil; sistem yöneticisine başvurunuz.")
            istek.personel_id = k["personel_id"]
        kisit = bolum_kisiti(k)
        if kisit and k["rol"] != M.ROL_OGRETMEN and istek.personel_id and \
                d.deger("SELECT bolum_id FROM personel WHERE id = ?", (istek.personel_id,), None) != kisit:
            raise HTTPException(403, "Yalnız kendi bölümünüzün personeli için kayıt girebilirsiniz.")
        if kisit and istek.siparis_id and d.deger("SELECT bolum_id FROM siparis WHERE id = ?", (istek.siparis_id,), None) != kisit:
            raise HTTPException(403, "Seçilen sipariş bölümünüze ait değil.")
        return istek

    def _fc_kaydi(d, k: dict, fid: int) -> dict:
        f = d.q1("""SELECT f.*, p.bolum_id personel_bolum, s.bolum_id siparis_bolum FROM fazla_calisma f
                    JOIN personel p ON p.id = f.personel_id LEFT JOIN siparis s ON s.id = f.siparis_id WHERE f.id = ?""", (fid,))
        if not f:
            raise HTTPException(404, "Fazla çalışma kaydı bulunamadı (silinmiş olabilir).")
        if k["rol"] == M.ROL_OGRETMEN and f["personel_id"] != k.get("personel_id"):
            raise HTTPException(403, "Yalnız kendi fazla çalışma kayıtlarınızı görebilirsiniz.")
        kisit = bolum_kisiti(k)
        if kisit and k["rol"] != M.ROL_OGRETMEN and (f["siparis_bolum"] or f["personel_bolum"]) != kisit:
            raise HTTPException(403, "Bu kayıt bölümünüzün kapsamı dışında.")
        return f

    def _fc_degistirilebilir(f: dict):
        if f["durum"] == "Onaylandı":
            raise IslemHatasi("Onaylanmış kayıt değiştirilemez veya silinemez; önce onayın kaldırılması gerekir.")
        if onay.durum("Fazla Çalışma", f["id"])["durum"] == onay.BEKLIYOR:
            raise IslemHatasi("Onay sürecindeki kayıt değiştirilemez; önce geri çekiniz.")

    @app.get("/api/fazla-calisma")
    def fazla_liste(yil: int = Query(default_factory=lambda: date.today().year),
                    ay: int = Query(default_factory=lambda: date.today().month, ge=1, le=12), b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["fazla"])
            ek, prm = _fc_kosul(b.k)
            satirlar = d.q(f"""SELECT f.*, p.ad_soyad, p.dose_gorevi, s.siparis_no FROM fazla_calisma f
                               JOIN personel p ON p.id = f.personel_id LEFT JOIN siparis s ON s.id = f.siparis_id
                               WHERE f.yil = ? AND f.ay = ?{ek} ORDER BY p.ad_soyad""", [yil, ay, *prm])
            durumlar = onay.durumlar("Fazla Çalışma")
            for s in satirlar:
                s["onay"] = _onay_metni(durumlar, s["id"], s["durum"] == "Onaylandı")
            return {"kayitlar": satirlar, "surum": d.son_islem_no(),
                    "toplam": {a: yuvarla(sum(s[a] or 0 for s in satirlar)) for a in ("saat", "brut", "net")},
                    "yazabilir": etkin_yetki(b.k, MOBIL_MODULLER["fazla"]) == "y"}

    @app.get("/api/fazla-calisma/secenekler")
    def fazla_secenekleri(yil: int = Query(default_factory=lambda: date.today().year),
                          ay: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
                          b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["fazla"])
            kisit = bolum_kisiti(b.k)
            if b.k["rol"] == M.ROL_OGRETMEN:
                per = d.q("SELECT id, ad_soyad, dose_gorevi FROM personel WHERE id = ?", (b.k.get("personel_id") or -1,))
            elif kisit:
                per = d.q("SELECT id, ad_soyad, dose_gorevi FROM personel WHERE aktif = 1 AND bolum_id = ? ORDER BY ad_soyad", (kisit,))
            else:
                per = d.q("SELECT id, ad_soyad, dose_gorevi FROM personel WHERE aktif = 1 ORDER BY ad_soyad")
            sip = d.q("SELECT id, siparis_no, konu FROM siparis WHERE durum != 'İptal'" + (" AND bolum_id = ?" if kisit else "")
                      + " ORDER BY id DESC LIMIT 200", (kisit,) if kisit else ())
            p = d.parametreler(yil)
            gunler = []
            for g in range(1, calendar.monthrange(yil, ay)[1] + 1):
                t = date(yil, ay, g)
                tur = gun_turu(t, p)
                gunler.append({"gun": g, "hafta_gunu": GUNLER[t.weekday()], "tur": tur, "tur_adi": GUN_TURU_ADLARI[tur],
                               "azami": gun_azami_saat(tur, p)})
            return {"personeller": per, "siparisler": sip, "saat_ucreti": p["fazla_calisma_saat_ucreti"],
                    "azami_aylik_saat": ay_azami_fazla_calisma(yil, ay, p), "gunler": gunler}

    @app.post("/api/fazla-calisma")
    def fazla_ekle(istek: FazlaIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            if not istek.onizleme:
                gerek(b.k, MOBIL_MODULLER["fazla"], yaz=True)
            else:
                gerek(b.k, MOBIL_MODULLER["fazla"])
            istek = _fc_personel_denetle(d, b.k, istek)
            kayit, hatalar, uyarilar = fc_hesapla(d, istek.model_dump())
            if istek.onizleme:
                return {"kayit": kayit, "hatalar": hatalar, "uyarilar": uyarilar}
            if hatalar:
                raise IslemHatasi("Kayıt yapılamadı:\n\n" + "\n".join(hatalar))
            fid = d.ekle("fazla_calisma", kayit)
            return {"id": fid, "kayit": kayit, "uyarilar": uyarilar}

    @app.put("/api/fazla-calisma/{fid}")
    def fazla_guncelle(fid: int, istek: FazlaIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["fazla"], yaz=not istek.onizleme)
            f = _fc_kaydi(d, b.k, fid)
            _fc_degistirilebilir(f)
            istek = _fc_personel_denetle(d, b.k, istek)
            veri = istek.model_dump()
            if istek.personel_id == f["personel_id"] and (istek.yil, istek.ay) == (f["yil"], f["ay"]):
                veri["onceki_kumulatif"] = f["onceki_kumulatif"]
            kayit, hatalar, uyarilar = fc_hesapla(d, veri, kid=fid)
            if istek.onizleme:
                return {"kayit": kayit, "hatalar": hatalar, "uyarilar": uyarilar}
            if istek.surum is not None:
                d.cakisma_denetle("fazla_calisma", fid, istek.surum)
            if hatalar:
                raise IslemHatasi("Kayıt yapılamadı:\n\n" + "\n".join(hatalar))
            kayit.pop("durum")
            d.guncelle("fazla_calisma", fid, kayit)
            return {"id": fid, "kayit": kayit, "uyarilar": uyarilar}

    @app.delete("/api/fazla-calisma/{fid}")
    def fazla_sil(fid: int, surum: int | None = None, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["fazla"], yaz=True)
            f = _fc_kaydi(d, b.k, fid)
            _fc_degistirilebilir(f)
            if surum is not None:
                d.cakisma_denetle("fazla_calisma", fid, surum)
            with d.islem():
                d.sil("fazla_calisma", fid)
                onay.sil("Fazla Çalışma", fid)
            return {"tamam": True}

    # ------------------------------------------------------------ parça başı
    def _pb_kaydi(d, k: dict, pb_id: int) -> dict:
        kayit = d.q1(
            """SELECT pb.*, s.siparis_no, s.konu, s.bolum_id siparis_bolum, s.durum siparis_durumu,
                      s.kabul_tarihi, s.sozlesme_bedeli
               FROM parca_basi pb LEFT JOIN siparis s ON s.id = pb.siparis_id WHERE pb.id = ?""", (pb_id,))
        if not kayit:
            raise HTTPException(404, "Parça başı bordrosu bulunamadı.")
        if k["rol"] == M.ROL_OGRETMEN:
            pid = k.get("personel_id") or -1
            if not d.deger(
                    "SELECT COUNT(*) FROM parca_basi_satir WHERE parca_basi_id = ? AND kisi_turu = 'Personel' AND kisi_id = ?",
                    (pb_id, pid), 0):
                raise HTTPException(403, "Yalnız size ait parça başı kayıtlarını görebilirsiniz.")
        else:
            kisit = bolum_kisiti(k)
            if kisit and kayit["siparis_bolum"] not in (None, 0, kisit):
                raise HTTPException(403, "Bu bordro bölümünüzün kapsamı dışında.")
        return kayit

    def _pb_degistirilebilir(d, kayit: dict, k: dict):
        if k["rol"] == M.ROL_OGRETMEN:
            raise HTTPException(403, "Öğretmen hesabıyla parça başı bordro düzenlenemez.")
        if kayit["durum"] == "Onaylandı":
            raise IslemHatasi("Onaylanmış bordro değiştirilemez veya silinemez; önce onay kaldırılmalıdır.")
        if onay.durum("Parça Başı", kayit["id"])["durum"] == onay.BEKLIYOR:
            raise IslemHatasi("Onay sürecindeki bordro değiştirilemez; önce geri çekilmelidir.")

    def _pb_hazirla(d, k: dict, istek: ParcaBasiIstegi, pb_id: int | None = None) -> tuple[dict, dict]:
        veri = istek.model_dump()
        siparis = d.q1("SELECT * FROM siparis WHERE id = ?", (istek.siparis_id,))
        if not siparis:
            raise HTTPException(404, "Seçilen sipariş bulunamadı.")
        if (siparis["ucret_esasi"] or "").startswith("Fazla") or siparis["durum"] in (
                "İptal", "Talep Alındı", "Keşif / İş Planı", "Teklif", "Proforma İletildi"):
            raise IslemHatasi("Parça başı bordro için uygun, sözleşmesi imzalanmış veya geçici kabulü yapılmış sipariş seçilmelidir.")
        kisit = bolum_kisiti(k)
        if kisit and siparis["bolum_id"] not in (None, 0, kisit):
            raise HTTPException(403, "Seçilen sipariş bölümünüzün kapsamı dışında.")
        seen = set()
        for satir in veri["satirlar"]:
            key = satir["kisi_turu"], satir["kisi_id"]
            if key in seen:
                raise IslemHatasi("Aynı kişi bordroda birden fazla kez bulunamaz.")
            seen.add(key)
            tablo = "personel" if satir["kisi_turu"] == "Personel" else "ogrenci"
            kisi = d.q1(f"SELECT aktif, bolum_id FROM {tablo} WHERE id = ?", (satir["kisi_id"],))
            if not kisi:
                raise HTTPException(404, f"{satir['kisi_turu']} kaydı bulunamadı (#{satir['kisi_id']}).")
            if not kisi["aktif"]:
                raise IslemHatasi(f"Pasif {satir['kisi_turu'].lower()} bordroya eklenemez.")
            if kisit and k["rol"] != M.ROL_OGRETMEN and kisi["bolum_id"] not in (None, 0, kisit):
                raise HTTPException(403, f"Seçilen kişi bölümünüzün kapsamı dışında.")
            puantaj = satir.get("puantaj") or {}
            if any(float(v) < 0 or not math.isfinite(float(v)) for v in puantaj.values()):
                raise HTTPException(422, "Puantaj değerleri sonlu ve negatif olmayan sayılar olmalıdır.")
        if pb_id is not None:
            d.cakisma_denetle("parca_basi", pb_id, istek.surum)
        p = d.parametreler(istek.yil)
        hesap = parca_basi.hesapla(d, veri, p, pb_id)
        if not veri["satirlar"]:
            raise IslemHatasi("Bordroda en az bir kişi bulunmalıdır.")
        return veri, hesap

    def _pb_ozet(d, kayit: dict, k: dict, ayrinti: bool = True) -> dict:
        satirlar = d.q("SELECT * FROM parca_basi_satir WHERE parca_basi_id = ? ORDER BY kisi_turu DESC, id",
                       (kayit["id"],))
        if k["rol"] == M.ROL_OGRETMEN:
            satirlar = [r for r in satirlar if r["kisi_turu"] == "Personel" and
                        r["kisi_id"] == (k.get("personel_id") or -1)]
        for row in satirlar:
            row.update(parca_basi.kisi_bilgisi(d, row["kisi_turu"], row["kisi_id"]))
            row["puantaj"] = puantaj_coz(row.get("puantaj"))
        sonuc = dict(kayit)
        sonuc["satirlar"] = satirlar
        sonuc["onay"] = _onay_metni(onay.durumlar("Parça Başı"), kayit["id"], kayit["durum"] == "Onaylandı")
        if ayrinti:
            sonuc["onay_gecmisi"] = onay.gecmis("Parça Başı", kayit["id"])
        if k["rol"] == M.ROL_OGRETMEN:
            sonuc["toplamlar"] = {ad: yuvarla(sum(r.get(ad) or 0 for r in satirlar))
                                  for ad in ("brut", "net")}
        else:
            sonuc["toplamlar"] = {
                ad: yuvarla(sum(r.get(ad) or 0 for r in satirlar))
                for ad in ("hesaplanan", "brut", "tavan_asimi", "gelir_vergisi", "damga_vergisi", "sgk", "net")
            }
        return sonuc

    @app.get("/api/parca-basi")
    def parca_basi_liste(yil: int = Query(default_factory=lambda: date.today().year),
                         ay: int | None = Query(default=None, ge=1, le=12), b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["parca_basi"])
            sql = """SELECT pb.*, s.siparis_no, s.konu, COUNT(r.id) kisi, SUM(r.brut) brut, SUM(r.tavan_asimi) asim,
                            SUM(r.gelir_vergisi + r.damga_vergisi) vergi, SUM(r.net) net
                     FROM parca_basi pb LEFT JOIN siparis s ON s.id = pb.siparis_id
                     LEFT JOIN parca_basi_satir r ON r.parca_basi_id = pb.id"""
            prm: list = [yil]
            where = ["pb.yil = ?"]
            kisit = bolum_kisiti(b.k)
            if kisit:
                where.append("s.bolum_id = ?")
                prm.append(kisit)
            if b.k["rol"] == M.ROL_OGRETMEN:
                where.append("r.kisi_turu = 'Personel' AND r.kisi_id = ?")
                prm.append(b.k.get("personel_id") or -1)
            if ay:
                where.append("pb.ay = ?")
                prm.append(ay)
            kayitlar = d.q(sql + " WHERE " + " AND ".join(where) +
                           " GROUP BY pb.id, s.siparis_no, s.konu ORDER BY pb.ay DESC, pb.id DESC", prm)
            durumlar = onay.durumlar("Parça Başı")
            for kayit in kayitlar:
                kayit["onay"] = _onay_metni(durumlar, kayit["id"], kayit["durum"] == "Onaylandı")
            return {"kayitlar": kayitlar, "yazabilir": etkin_yetki(b.k, MOBIL_MODULLER["parca_basi"]) == "y",
                    "toplamlar": {ad: yuvarla(sum(r.get(ad) or 0 for r in kayitlar))
                                  for ad in ("brut", "net")}}

    @app.get("/api/parca-basi/secenekler")
    def parca_basi_secenekler(yil: int = Query(default_factory=lambda: date.today().year),
                              b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["parca_basi"])
            kisit = bolum_kisiti(b.k)
            kosul = "ucret_esasi NOT LIKE 'Fazla%' AND durum NOT IN " \
                    "('İptal', 'Talep Alındı', 'Keşif / İş Planı', 'Teklif', 'Proforma İletildi')"
            if kisit:
                kosul += " AND bolum_id = ?"
            prm = (kisit,) if kisit else ()
            siparisler = d.q(
                f"SELECT id, siparis_no, konu, durum, bolum_id, kabul_tarihi FROM siparis WHERE {kosul} "
                "ORDER BY id DESC LIMIT 500", prm)
            personeller = d.q("SELECT id, ad_soyad, hizmet_sinifi, bolum_id FROM personel WHERE aktif = 1 "
                              + ("AND bolum_id = ? " if kisit else "") + "ORDER BY ad_soyad",
                              (kisit,) if kisit else ())
            ogrenciler = d.q("SELECT id, ad_soyad, sinif, bolum_id, veli_muvafakat FROM ogrenci WHERE aktif = 1 "
                             + ("AND bolum_id = ? " if kisit else "") + "ORDER BY ad_soyad",
                             (kisit,) if kisit else ())
            p = d.parametreler(yil)
            return {"siparisler": siparisler, "personeller": personeller, "ogrenciler": ogrenciler,
                    "ogrenci_hakki_orani": p["ogrenci_hakki_orani"],
                    "yazabilir": etkin_yetki(b.k, MOBIL_MODULLER["parca_basi"]) == "y"}

    @app.get("/api/parca-basi/{pb_id}")
    def parca_basi_detay(pb_id: int, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["parca_basi"])
            kayit = _pb_kaydi(d, b.k, pb_id)
            return _pb_ozet(d, kayit, b.k)

    @app.post("/api/parca-basi/hesapla")
    def parca_basi_onizle(istek: ParcaBasiIstegi, pb_id: int | None = None, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["parca_basi"])
            if pb_id is not None:
                kayit = _pb_kaydi(d, b.k, pb_id)
                _pb_degistirilebilir(d, kayit, b.k)
            veri, hesap = _pb_hazirla(d, b.k, istek, pb_id)
            return {"hesap": hesap, "yazabilir": etkin_yetki(b.k, MOBIL_MODULLER["parca_basi"]) == "y"}

    @app.post("/api/parca-basi")
    def parca_basi_ekle(istek: ParcaBasiIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["parca_basi"], yaz=True)
            veri, hesap = _pb_hazirla(d, b.k, istek)
            with d.islem():
                pb_id = d.ekle("parca_basi", {
                    "yil": veri["yil"], "ay": veri["ay"], "siparis_id": veri["siparis_id"],
                    "kabul_edilen_iscilik": veri["kabul_edilen_iscilik"], "ogrenci_orani": veri["ogrenci_orani"],
                    "durum": "Taslak", "aciklama": veri["aciklama"] or None,
                })
                for row in hesap["satirlar"]:
                    d.ekle("parca_basi_satir", {
                        "parca_basi_id": pb_id, "kisi_turu": row["kisi_turu"], "kisi_id": row["kisi_id"],
                        "katki": row["katki"], "hesaplanan": row["hesaplanan"], "brut": row["brut"],
                        "tavan_asimi": row["tavan_asimi"], "onceki_kumulatif": row["onceki_kumulatif"],
                        "gelir_vergisi": row["gelir_vergisi"], "damga_vergisi": row["damga_vergisi"],
                        "sgk": row["sgk"], "net": row["net"], "puantaj": row["puantaj_json"],
                    }, log=False)
            return {"id": pb_id, "hesap": hesap}

    @app.put("/api/parca-basi/{pb_id}")
    def parca_basi_guncelle(pb_id: int, istek: ParcaBasiIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["parca_basi"], yaz=True)
            kayit = _pb_kaydi(d, b.k, pb_id)
            _pb_degistirilebilir(d, kayit, b.k)
            veri, hesap = _pb_hazirla(d, b.k, istek, pb_id)
            with d.islem():
                d.guncelle("parca_basi", pb_id, {
                    "yil": veri["yil"], "ay": veri["ay"], "siparis_id": veri["siparis_id"],
                    "kabul_edilen_iscilik": veri["kabul_edilen_iscilik"], "ogrenci_orani": veri["ogrenci_orani"],
                    "aciklama": veri["aciklama"] or None,
                })
                d.ex("DELETE FROM parca_basi_satir WHERE parca_basi_id = ?", (pb_id,))
                for row in hesap["satirlar"]:
                    d.ekle("parca_basi_satir", {
                        "parca_basi_id": pb_id, "kisi_turu": row["kisi_turu"], "kisi_id": row["kisi_id"],
                        "katki": row["katki"], "hesaplanan": row["hesaplanan"], "brut": row["brut"],
                        "tavan_asimi": row["tavan_asimi"], "onceki_kumulatif": row["onceki_kumulatif"],
                        "gelir_vergisi": row["gelir_vergisi"], "damga_vergisi": row["damga_vergisi"],
                        "sgk": row["sgk"], "net": row["net"], "puantaj": row["puantaj_json"],
                    }, log=False)
            return {"id": pb_id, "hesap": hesap}

    @app.delete("/api/parca-basi/{pb_id}")
    def parca_basi_sil(pb_id: int, surum: int | None = None, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["parca_basi"], yaz=True)
            kayit = _pb_kaydi(d, b.k, pb_id)
            _pb_degistirilebilir(d, kayit, b.k)
            if surum is not None:
                d.cakisma_denetle("parca_basi", pb_id, surum)
            if d.deger("SELECT COUNT(*) FROM kasa_banka WHERE kaynak = 'ParcaBasi' AND kaynak_id = ?",
                       (pb_id,), 0):
                raise IslemHatasi("Ödeme kaydı bulunan bordro silinemez.")
            with d.islem():
                d.ex("DELETE FROM parca_basi_satir WHERE parca_basi_id = ?", (pb_id,))
                d.sil("parca_basi", pb_id)
                onay.sil("Parça Başı", pb_id)
            return {"tamam": True}

    @app.post("/api/parca-basi/{pb_id}/odeme")
    def parca_basi_odeme(pb_id: int, istek: ParcaBasiOdemeIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["parca_basi"], yaz=True)
            kayit = _pb_kaydi(d, b.k, pb_id)
            if kayit["durum"] != "Onaylandı" or onay.durum("Parça Başı", pb_id)["durum"] != onay.ONAYLANDI:
                raise IslemHatasi("Ödeme kaydı için bordronun onaylanmış olması gerekir.")
            try:
                datetime.strptime(istek.tarih, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(400, "Ödeme tarihi YYYY-AA-GG biçiminde olmalıdır.") from None
            if d.deger("SELECT COUNT(*) FROM kasa_banka WHERE kaynak = 'ParcaBasi' AND kaynak_id = ?",
                       (pb_id,), 0):
                raise IslemHatasi("Bu bordro için ödeme kaydı zaten oluşturulmuş.")
            net = d.deger("SELECT SUM(net) FROM parca_basi_satir WHERE parca_basi_id = ?", (pb_id,), 0.0) or 0.0
            hareket_id = d.ekle("kasa_banka", {
                "tarih": istek.tarih, "hesap": istek.hesap, "yon": "Çıkış", "tur": "Personel Ödemesi",
                "tutar": net, "siparis_id": kayit["siparis_id"], "belge_no": istek.belge_no or None,
                "aciklama": istek.aciklama or
                f"{M.AYLAR[kayit['ay'] - 1]} {kayit['yil']} parça başı ücret ({kayit['siparis_no']})",
                "kaynak": "ParcaBasi", "kaynak_id": pb_id,
            })
            return {"id": hareket_id, "tutar": net}

    @app.get("/api/parca-basi/{pb_id}/belge/{tur}")
    def parca_basi_belge(pb_id: int, tur: str, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["parca_basi"])
            kayit = _pb_kaydi(d, b.k, pb_id)
            if b.k["rol"] == M.ROL_OGRETMEN:
                raise HTTPException(403, "Bordro belgelerine erişim yetkiniz bulunmuyor.")
            if tur not in ("bordro", "puantaj", "banka"):
                raise HTTPException(404, "Belge türü bulunamadı.")
            if tur == "banka":
                headers = ["Adı soyadı", "T.C. kimlik no", "IBAN", "Net tutar", "Açıklama"]
                rows = []
                for row in d.q("SELECT * FROM parca_basi_satir WHERE parca_basi_id = ? AND net > 0", (pb_id,)):
                    kisi = parca_basi.kisi_bilgisi(d, row["kisi_turu"], row["kisi_id"])
                    rows.append([kisi["ad"], kisi["tckn"] or "", kisi["iban"] or "", row["net"],
                                 f"{M.AYLAR[kayit['ay'] - 1]} {kayit['yil']} parça başı ücret"])
                with tempfile.TemporaryDirectory() as gecici:
                    yol = Path(gecici) / f"Banka_ParcaBasi_{kayit['siparis_no']}_{kayit['ay']:02d}.xlsx"
                    excel.disa_aktar(yol, [("Banka listesi", headers, rows)])
                    icerik = yol.read_bytes()
                dosya_adi = yol.name
            else:
                with tempfile.TemporaryDirectory() as gecici:
                    fonksiyon = belgeler.parca_basi_bordrosu if tur == "bordro" else belgeler.parca_basi_puantaj
                    yol = fonksiyon(Path(gecici) / f"ParcaBasi_{pb_id}", pb_id)
                    icerik = yol.read_bytes()
                dosya_adi = yol.name
            return {"dosya_adi": dosya_adi, "icerik": base64.b64encode(icerik).decode("ascii")}

    # ------------------------------------------------------------ ortak tanım kayıtları
    @app.get("/api/kurum")
    def kurum_bilgisi(b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["kurum"])
            kayit = d.kurum()
            return {"kayit": kayit, "yazabilir": yetki.yonetici_mi(b.k["rol"]) and
                    etkin_yetki(b.k, MOBIL_MODULLER["kurum"]) == "y",
                    "kurum_kodu_kilitli": lisans.lisansli_mi(d)}

    @app.put("/api/kurum")
    def kurum_guncelle(istek: TanimKaydiIstegi, b: Baglam = Depends(kullanici)):
        alanlar = {"okul_adi", "isletme_adi", "kurum_kodu", "il", "ilce", "adres", "telefon", "eposta",
                   "vergi_dairesi", "vkn", "banka", "iban", "harcama_yetkilisi", "gerceklestirme_gorevlisi",
                   "sayman", "tahsis_sermaye", "odenmis_sermaye", "buyuksehir", "yuz_yuze_egitim", "evrak_kodu"}
        with b as d:
            gerek(b.k, MOBIL_MODULLER["kurum"], yaz=True)
            if not yetki.yonetici_mi(b.k["rol"]):
                raise HTTPException(403, "Kurum bilgilerini yalnızca yetkili yöneticiler değiştirebilir.")
            if set(istek.degerler) - alanlar:
                raise HTTPException(400, "Kurum bilgisi alanları desteklenmiyor.")
            values = dict(istek.degerler)
            if "okul_adi" in values and not str(values["okul_adi"] or "").strip():
                raise HTTPException(400, "Okul adı zorunludur.")
            if values.get("vkn") and not dogrulama.vkn_veya_tckn_gecerli(str(values["vkn"])):
                raise HTTPException(400, "Vergi kimlik numarası geçersiz.")
            if values.get("iban"):
                iban = dogrulama.iban_normalize(str(values["iban"]))
                if not dogrulama.iban_gecerli(iban):
                    raise HTTPException(400, "IBAN geçersiz.")
                values["iban"] = iban
            for key in ("tahsis_sermaye", "odenmis_sermaye"):
                if key in values:
                    try:
                        tutar = float(values[key])
                    except (TypeError, ValueError):
                        raise HTTPException(400, f"'{key}' sayısal olmalıdır.") from None
                    if not math.isfinite(tutar) or tutar < 0:
                        raise HTTPException(400, f"'{key}' sıfır veya daha büyük olmalıdır.")
                    values[key] = tutar
            for key in ("buyuksehir", "yuz_yuze_egitim"):
                if key in values:
                    if values[key] not in (True, False, 0, 1):
                        raise HTTPException(400, f"'{key}' doğru/yanlış olmalıdır.")
                    values[key] = int(bool(values[key]))
            if lisans.lisansli_mi(d):
                values["kurum_kodu"] = d.kurum().get("kurum_kodu")
            with d.islem():
                d.guncelle("kurum", 1, values)
            return {"tamam": True}

    @app.get("/api/parametreler")
    def parametre_listesi(yil: int = Query(default_factory=lambda: date.today().year),
                          b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["parametre"])
            values = d.parametreler(yil)
            return {"yil": yil, "yazabilir": yetki.yonetici_mi(b.k["rol"]) and etkin_yetki(
                b.k, MOBIL_MODULLER["parametre"]) == "y",
                "parametreler": [{"anahtar": key, "etiket": label, "tur": tip, "deger": values[key],
                                  "aciklama": aciklama}
                                 for key, label, tip, _default, aciklama in M.PARAMETRELER]}

    @app.put("/api/parametreler")
    def parametre_guncelle(istek: TanimKaydiIstegi, yil: int = Query(..., ge=2000, le=2200),
                           b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["parametre"], yaz=True)
            if not yetki.yonetici_mi(b.k["rol"]):
                raise HTTPException(403, "Mevzuat parametrelerini yalnızca yetkili yöneticiler değiştirebilir.")
            izinli = {key: tip for key, _label, tip, _default, _aciklama in M.PARAMETRELER}
            if set(istek.degerler) != set(izinli):
                raise HTTPException(400, "Tüm mevzuat parametreleri birlikte gönderilmelidir.")
            kaydedilecek = {}
            for key, tip in izinli.items():
                value = istek.degerler[key]
                if tip == "metin":
                    try:
                        tarife = json.loads(value) if isinstance(value, str) else value
                    except (TypeError, ValueError):
                        raise HTTPException(400, f"'{key}' geçerli JSON olmalıdır.") from None
                    if key == "gv_tarifesi_ucret" and (
                            not isinstance(tarife, list) or not tarife or
                            not all(isinstance(satir, list) and len(satir) == 2 for satir in tarife) or
                            tarife[-1][0] is not None):
                        raise HTTPException(400, f"'{key}' vergi tarifesi biçimi geçersiz.")
                    if key == "fc_tatil_donemleri" and (
                            not isinstance(tarife, list) or
                            not all(isinstance(donem, list) and len(donem) == 2 and
                                    all(isinstance(tarih_, str) for tarih_ in donem) for donem in tarife)):
                        raise HTTPException(400, f"'{key}' tatil dönemleri biçimi geçersiz.")
                    if key == "fc_bayram_gunleri" and (
                            not isinstance(tarife, list) or
                            not all(isinstance(tarih_, str) for tarih_ in tarife)):
                        raise HTTPException(400, f"'{key}' bayram günleri biçimi geçersiz.")
                    kaydedilecek[key] = json.dumps(tarife, ensure_ascii=False)
                elif tip in ("oran", "para", "sayi"):
                    try:
                        kaydedilecek[key] = float(value)
                    except (TypeError, ValueError):
                        raise HTTPException(400, f"'{key}' sayısal olmalıdır.") from None
                else:
                    kaydedilecek[key] = str(value)
            with d.islem():
                for key, value in kaydedilecek.items():
                    d.parametre_yaz(yil, key, value)
                d.log("Parametre güncelleme", "parametre", yil)
            return {"tamam": True, "yil": yil}

    def _maliyet_urun(d, urun_id: int, k: dict) -> dict:
        urun = d.q1("""SELECT u.*, b.ad bolum_ad FROM urun u
                       LEFT JOIN bolum b ON b.id = u.bolum_id WHERE u.id = ?""", (urun_id,))
        if not urun:
            raise HTTPException(404, "Ürün / hizmet kaydı bulunamadı.")
        bolum = bolum_kisiti(k)
        if bolum is not None and urun["bolum_id"] not in (None, 0, bolum):
            raise HTTPException(403, "Bu ürün bölümünüzün kapsamı dışında.")
        return urun

    def _maliyet_hazirla(d, urun: dict, istek: MaliyetIstegi) -> dict:
        kalemler = [satir.model_dump() for satir in istek.kalemler]
        for satir in kalemler:
            if satir["kalem_turu"] not in M.MALIYET_KALEMLERI:
                raise HTTPException(400, "Geçersiz maliyet unsuru.")
            if satir["malzeme_id"] is not None:
                malzeme = d.q1("SELECT ad, aktif FROM malzeme WHERE id = ?", (satir["malzeme_id"],))
                if not malzeme or not malzeme["aktif"]:
                    raise HTTPException(400, "Maliyet satırındaki stok kartı bulunamadı veya pasif.")
                satir["malzeme_ad"] = malzeme["ad"]
        return maliyet.hesapla(urun, d.parametreler(date.today().year), kalemler, istek.oto,
                               istek.hedef_fiyat, istek.kar_orani, istek.kdv_orani, istek.hedef_dahil)

    def _maliyet_kaydet(d, urun: dict, sonuc: dict):
        d.ex("DELETE FROM maliyet_kalem WHERE urun_id = ?", (urun["id"],))
        for satir in sonuc["kalemler"]:
            d.ekle("maliyet_kalem", {
                "urun_id": urun["id"], "kalem_turu": satir["kalem_turu"],
                "aciklama": satir.get("aciklama") or None, "malzeme_id": satir.get("malzeme_id"),
                "miktar": satir["miktar"], "birim_fiyat": satir["birim_fiyat"],
            }, log=False)
        d.guncelle("urun", urun["id"], {
            "kar_orani": sonuc["kar_orani"], "kdv_orani": sonuc["kdv_orani"],
        }, log=False)
        d.log("Maliyet analizi kaydetme", "urun", urun["id"],
              yeni={"kalem_sayisi": len(sonuc["kalemler"]), "birim_maliyet": sonuc["ozet"]["birim_maliyet"]})

    @app.get("/api/urun/{urun_id}/maliyet")
    def maliyet_analizi(urun_id: int, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["urun"])
            urun = _maliyet_urun(d, urun_id, b.k)
            kalemler = d.q("""SELECT k.*, m.ad malzeme_ad FROM maliyet_kalem k
                              LEFT JOIN malzeme m ON m.id = k.malzeme_id
                              WHERE k.urun_id = ? ORDER BY k.id""", (urun_id,))
            malzemeler = d.q("SELECT id, ad, birim FROM malzeme WHERE aktif = 1 ORDER BY ad")
            for malzeme_kaydi in malzemeler:
                malzeme_kaydi["ortalama_maliyet"] = muhasebe.ortalama_maliyet(malzeme_kaydi["id"])
            return {
                "urun": urun, "kalemler": kalemler,
                "malzemeler": malzemeler,
                "kalem_turleri": M.MALIYET_KALEMLERI, "parametreler": d.parametreler(date.today().year),
                "yazabilir": etkin_yetki(b.k, MOBIL_MODULLER["urun"]) == "y",
            }

    @app.post("/api/urun/{urun_id}/maliyet/hesapla")
    def maliyet_analizi_hesapla(urun_id: int, istek: MaliyetIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["urun"])
            urun = _maliyet_urun(d, urun_id, b.k)
            return _maliyet_hazirla(d, urun, istek)

    @app.put("/api/urun/{urun_id}/maliyet")
    def maliyet_analizi_kaydet(urun_id: int, istek: MaliyetIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["urun"], yaz=True)
            urun = _maliyet_urun(d, urun_id, b.k)
            sonuc = _maliyet_hazirla(d, urun, istek)
            with d.islem():
                _maliyet_kaydet(d, urun, sonuc)
            return sonuc

    @app.post("/api/urun/{urun_id}/maliyet/fiyat")
    def maliyet_fiyat_isle(urun_id: int, istek: MaliyetIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["urun"], yaz=True)
            urun = _maliyet_urun(d, urun_id, b.k)
            sonuc = _maliyet_hazirla(d, urun, istek)
            with d.islem():
                _maliyet_kaydet(d, urun, sonuc)
                d.guncelle("urun", urun_id, {"satis_fiyati": sonuc["ozet"]["satis_fiyati"]})
            return {"tamam": True, "satis_fiyati": sonuc["ozet"]["satis_fiyati"]}

    @app.post("/api/urun/{urun_id}/maliyet/tutanak")
    def maliyet_tutanak(urun_id: int, istek: MaliyetIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["urun"], yaz=True)
            urun = _maliyet_urun(d, urun_id, b.k)
            sonuc = _maliyet_hazirla(d, urun, istek)
            bugun = date.today().isoformat()
            with tempfile.TemporaryDirectory() as gecici:
                yol = belgeler.fiyat_tespit_tutanagi(Path(gecici) / f"Fiyat_Tespit_{urun_id}.pdf",
                                                     urun, sonuc["kalemler"], sonuc["ozet"], istek.piyasa)
                icerik = yol.read_bytes()
            with d.islem():
                _maliyet_kaydet(d, urun, sonuc)
                fiyat_tespit_id = d.ekle("fiyat_tespit", {
                    "urun_id": urun_id, "tarih": bugun, "birim_maliyet": sonuc["ozet"]["birim_maliyet"],
                    "kar_orani": sonuc["ozet"]["kar_orani"], "satis_fiyati": sonuc["ozet"]["satis_fiyati"],
                    "kdv_orani": sonuc["ozet"]["kdv_orani"], "kdv_dahil_fiyat": sonuc["ozet"]["kdv_dahil"],
                    "piyasa_arastirmasi": istek.piyasa,
                }, log=False)
                d.log("Fiyat tespit tutanağı oluşturma", "fiyat_tespit", fiyat_tespit_id)
            return {"dosya_adi": f"Fiyat_Tespit_{urun_id}_{bugun}.pdf",
                    "icerik": base64.b64encode(icerik).decode("ascii")}

    @app.get("/api/tanimlar/{tur}")
    def tanim_listesi(tur: str, ara: str = "", b: Baglam = Depends(kullanici)):
        if tur not in TANIM_ALANLARI:
            raise HTTPException(404, "Bu tanım türü desteklenmiyor.")
        with b as d:
            gerek(b.k, MOBIL_MODULLER[tur])
            alanlar = TANIM_ALANLARI[tur]
            secim = ", ".join(["id"] + [alan[0] for alan in alanlar])
            sql = f"SELECT {secim} FROM {tur}"
            kosullar, parametreler = [], []
            bolum = bolum_kisiti(b.k)
            if bolum is not None and any(alan[0] == "bolum_id" for alan in alanlar):
                kosullar.append("bolum_id = ?")
                parametreler.append(bolum)
            arama_alanlari = [alan[0] for alan in alanlar if alan[2] == "metin"]
            if ara.strip() and arama_alanlari:
                kosullar.append("(" + " OR ".join(f"COALESCE({alan}, '') LIKE ?" for alan in arama_alanlari) + ")")
                parametreler.extend([f"%{ara.strip()}%"] * len(arama_alanlari))
            if kosullar:
                sql += " WHERE " + " AND ".join(kosullar)
            kayitlar = d.q(sql + f" ORDER BY {TANIM_SIRALAMA[tur]} LIMIT 1000", parametreler)
            alan_meta = []
            for anahtar, etiket, tip, zorunlu, secenekler in alanlar:
                secenek_listesi = secenekler
                if tip == "fk_bolum":
                    secenek_listesi = [(r["id"], r["ad"]) for r in d.q(
                        "SELECT id, ad FROM bolum WHERE aktif = 1 ORDER BY ad")]
                elif tip == "fk_malzeme":
                    secenek_listesi = [(r["id"], r["ad"]) for r in d.q(
                        "SELECT id, ad FROM malzeme WHERE aktif = 1 AND tur IN ('Mamul', 'Ticari Mal') ORDER BY ad")]
                alan_meta.append({"anahtar": anahtar, "etiket": etiket,
                                  "tur": "fk" if tip.startswith("fk_") else tip,
                                  "zorunlu": zorunlu,
                                  "secenekler": [{"deger": x[0], "etiket": x[1]} if isinstance(x, tuple)
                                                 else {"deger": x, "etiket": str(x)} for x in secenek_listesi]})
            return {"baslik": MOBIL_MODULLER[tur], "yazabilir": etkin_yetki(b.k, MOBIL_MODULLER[tur]) == "y",
                    "alanlar": alan_meta, "kayitlar": kayitlar}

    def _tanim_degerlerini_dogrula(d, tur: str, values: dict, kayit_id: int | None = None) -> dict:
        izinli = {alan[0] for alan in TANIM_ALANLARI[tur]}
        if not values or set(values) - izinli:
            raise HTTPException(400, "Tanım alanları eksik veya desteklenmiyor.")
        onceki = d.q1(f"SELECT * FROM {tur} WHERE id = ?", (kayit_id,)) if kayit_id is not None else {}
        temiz = {}
        for alan in TANIM_ALANLARI[tur]:
            key, label, tip, zorunlu, secenekler = alan
            if key not in values:
                continue
            value = values[key]
            if isinstance(value, str):
                value = value.strip() or None
            if zorunlu and value in (None, ""):
                raise HTTPException(400, f"'{label}' alanı zorunludur.")
            if value is None:
                temiz[key] = None
            elif tip == "bool":
                if value not in (True, False, 0, 1):
                    raise HTTPException(400, f"'{label}' alanı doğru/yanlış olmalıdır.")
                temiz[key] = int(bool(value))
            elif tip in ("para", "oran", "ondalik"):
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    raise HTTPException(400, f"'{label}' sayısal olmalıdır.") from None
                if not math.isfinite(number) or number < 0 or (tip == "oran" and number > 1):
                    raise HTTPException(400, f"'{label}' aralık dışında.")
                temiz[key] = number
            elif tip in ("fk_bolum", "fk_malzeme"):
                try:
                    foreign_id = int(value)
                except (TypeError, ValueError):
                    raise HTTPException(400, f"'{label}' seçimi geçersiz.") from None
                hedef = "bolum" if tip == "fk_bolum" else "malzeme"
                if not d.q1(f"SELECT id FROM {hedef} WHERE id = ? AND aktif = 1", (foreign_id,)):
                    raise HTTPException(400, f"'{label}' seçimi artık kullanılamıyor.")
                temiz[key] = foreign_id
            elif tip == "secim":
                allowed = {str(item[0] if isinstance(item, tuple) else item) for item in secenekler}
                if str(value) not in allowed:
                    raise HTTPException(400, f"'{label}' seçimi geçersiz.")
                temiz[key] = value
            else:
                temiz[key] = str(value)
                if tip == "tarih":
                    try:
                        date.fromisoformat(temiz[key])
                    except ValueError:
                        raise HTTPException(400, f"'{label}' geçerli bir tarih olmalıdır.") from None
        denetlenecek = {**(onceki or {}), **temiz}
        tckn = denetlenecek.get("tckn")
        if tur in ("personel", "ogrenci") and tckn and not dogrulama.tckn_gecerli(tckn):
            raise HTTPException(400, "T.C. kimlik numarası geçersiz.")
        if tur in ("personel", "ogrenci") and tckn:
            sql = f"SELECT id FROM {tur} WHERE tckn = ?"
            params: list = [tckn]
            if kayit_id is not None:
                sql += " AND id != ?"
                params.append(kayit_id)
            if d.q1(sql, params):
                raise HTTPException(400, "Bu T.C. kimlik numarası başka bir kayıtta kullanılıyor.")
        if tur == "cari" and denetlenecek.get("vkn_tckn") and not dogrulama.vkn_veya_tckn_gecerli(
                denetlenecek["vkn_tckn"]):
            raise HTTPException(400, "Vergi kimlik / T.C. kimlik numarası geçersiz.")
        if denetlenecek.get("iban"):
            iban = dogrulama.iban_normalize(denetlenecek["iban"])
            if not dogrulama.iban_gecerli(iban):
                raise HTTPException(400, "IBAN geçersiz.")
            if "iban" in temiz:
                temiz["iban"] = iban
        if tur == "ogrenci" and denetlenecek.get("veli_muvafakat") and not denetlenecek.get("muvafakat_tarihi"):
            raise HTTPException(400, "Veli muvafakat tarihi giriniz.")
        if tur == "cari" and denetlenecek.get("tur") == "Çiftçi (Müstahsil)" and denetlenecek.get("vkn_tckn"):
            if len(denetlenecek["vkn_tckn"]) != 11:
                raise HTTPException(400, "Müstahsil makbuzu için çiftçinin T.C. kimlik numarası girilmelidir.")
        if tur == "personel" and denetlenecek.get("aktif"):
            gorev = denetlenecek.get("dose_gorevi")
            if gorev in ("Harcama Yetkilisi (Okul Müdürü)", "Gerçekleştirme Görevlisi (Teknik Md. Yrd.)", "Sayman"):
                sql = "SELECT ad_soyad FROM personel WHERE dose_gorevi = ? AND aktif = 1"
                params: list = [gorev]
                if kayit_id:
                    sql += " AND id != ?"
                    params.append(kayit_id)
                if d.q1(sql, params):
                    raise HTTPException(400, f"'{gorev}' görevinde aktif başka personel var; önceki kaydı pasif yapınız.")
        if tur == "cari" and not temiz.get("kod") and kayit_id is None:
            sonraki = d.deger("SELECT MAX(id) FROM cari", (), 0) or 0
            temiz["kod"] = f"C{sonraki + 1:04d}"
        return temiz

    def _tanim_excel_satirlarini_hazirla(d, tur: str, satirlar: list[dict], k):
        alanlar = set(excel.PERSONEL_ICE_AKTARMA if tur == "personel" else excel.OGRENCI_ICE_AKTARMA)
        alanlar.discard("_gorev")
        bolum = bolum_kisiti(k)
        gorulen_tckn: set[str] = set()
        gorulen_gorevler: set[str] = set()
        hazir, onizleme, notlar = [], [], []
        elenen = eksik = mevcut = sorunlu = 0
        gorunen_alanlar = set()
        for raw in satirlar:
            gorev = raw.get("kadro_unvani") if tur == "personel" else raw.get("_gorev")
            uygun = (not excel.ogrenci_satiri(gorev) if tur == "personel"
                     else gorev in (None, "") or excel.ogrenci_satiri(gorev))
            if not uygun:
                elenen += 1
                continue
            temiz = {}
            for alan in alanlar:
                if alan not in raw:
                    continue
                deger = raw[alan]
                if isinstance(deger, str):
                    deger = deger.strip() or None
                elif isinstance(deger, float) and deger.is_integer():
                    deger = str(int(deger))
                elif deger is not None:
                    deger = str(deger).strip()
                temiz[alan] = deger
                gorunen_alanlar.add(alan)

            ad = str(temiz.get("ad_soyad") or "").strip()
            if not ad:
                eksik += 1
                onizleme.append({"ad": "?", "durum": "Atlandı", "neden": "Adı soyadı zorunlu."})
                continue
            if tur == "personel":
                gorev = temiz.get("kadro_unvani")
                dose_gorevi = "Öğretmen"
                temiz.update({
                    "hizmet_sinifi": M.HIZMET_SINIFLARI[0], "dose_gorevi": dose_gorevi,
                    "unvan_grubu": M.GOREV_VARSAYILAN_UNVAN_GRUBU.get(dose_gorevi, 3),
                    "istihdam": "657 s. DMK", "aktif": 1,
                })
            else:
                temiz.update({"aktif": 1, "veli_muvafakat": 0})
            if bolum is not None:
                temiz["bolum_id"] = bolum

            tckn = temiz.get("tckn")
            if tckn and not dogrulama.tckn_gecerli(tckn):
                notlar.append(f"{ad}: geçersiz T.C. kimlik no alınmadı.")
                temiz["tckn"] = None
                tckn = None
            if tckn and (tckn in gorulen_tckn or d.q1(f"SELECT id FROM {tur} WHERE tckn = ?", (tckn,))):
                mevcut += 1
                onizleme.append({"ad": ad, "durum": "Atlandı", "neden": "T.C. kimlik no zaten kayıtlı."})
                continue
            iban = temiz.get("iban")
            if iban:
                iban = dogrulama.iban_normalize(iban)
                if not dogrulama.iban_gecerli(iban):
                    notlar.append(f"{ad}: geçersiz IBAN alınmadı.")
                    temiz["iban"] = None
                else:
                    temiz["iban"] = iban
            if tur == "personel":
                gorev_adi = temiz["dose_gorevi"]
                if temiz["aktif"] and gorev_adi in (
                    "Harcama Yetkilisi (Okul Müdürü)", "Gerçekleştirme Görevlisi (Teknik Md. Yrd.)", "Sayman"
                ):
                    if gorev_adi in gorulen_gorevler or d.q1(
                        "SELECT id FROM personel WHERE dose_gorevi = ? AND aktif = 1", (gorev_adi,)
                    ):
                        sorunlu += 1
                        onizleme.append({"ad": ad, "durum": "Atlandı", "neden": "Aynı görevde aktif personel var."})
                        continue
            try:
                temiz = _tanim_degerlerini_dogrula(d, tur, temiz)
            except HTTPException as h:
                sorunlu += 1
                aciklama = str(h.detail)
                notlar.append(f"{ad}: aktarılmadı - {aciklama}")
                onizleme.append({"ad": ad, "durum": "Atlandı", "neden": aciklama})
                continue
            hazir.append(temiz)
            if tckn:
                gorulen_tckn.add(tckn)
            if tur == "personel" and temiz.get("aktif"):
                gorulen_gorevler.add(temiz.get("dose_gorevi"))
            onizleme.append({"ad": ad, "durum": "Aktarılacak"})
        return {
            "satirlar": hazir,
            "ozet": {
                "dosyadaki_kayit": len(satirlar), "aktarilacak": len(hazir), "elenen": elenen,
                "mevcut": mevcut, "eksik": eksik, "sorunlu": sorunlu,
                "eslesen_alanlar": sorted(gorunen_alanlar),
                "onizleme": onizleme[:20], "notlar": notlar[:20],
            },
        }

    def _tanim_excel_oku(istek: TanimExcelIstegi, tur: str):
        uzanti = Path(istek.dosya_adi).suffix.lower()
        if uzanti not in (".xlsx", ".xlsm"):
            raise HTTPException(400, "Yalnızca .xlsx veya .xlsm dosyası seçiniz.")
        try:
            icerik = base64.b64decode(istek.icerik, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(400, "Excel dosyası Base64 içerik olarak okunamadı.") from None
        if len(icerik) > 5 * 1024 * 1024:
            raise HTTPException(413, "Excel dosyası en fazla 5 MB olabilir.")
        try:
            with zipfile.ZipFile(BytesIO(icerik)) as paket:
                bilgiler = paket.infolist()
                if len(bilgiler) > 2000 or sum(x.file_size for x in bilgiler) > 50 * 1024 * 1024:
                    raise HTTPException(413, "Excel dosyasının açılmış boyutu veya içerik sayısı sınırı aşıyor.")
        except zipfile.BadZipFile:
            raise HTTPException(400, "Seçilen dosya geçerli bir Excel çalışma kitabı değil.") from None
        alan_esleri = excel.PERSONEL_ICE_AKTARMA if tur == "personel" else excel.OGRENCI_ICE_AKTARMA
        try:
            with tempfile.TemporaryDirectory(prefix="dose-excel-ice-aktar-") as dizin:
                yol = Path(dizin) / f"aktar{uzanti}"
                yol.write_bytes(icerik)
                satirlar, sayfa = excel.tablo_bul(yol, alan_esleri)
        except (InvalidFileException, OSError, TypeError, ValueError, KeyError, zipfile.BadZipFile) as h:
            raise HTTPException(400, f"Excel dosyası okunamadı: {h}") from None
        if not sayfa or not satirlar:
            raise HTTPException(400, "Dosyada eşleşen başlık satırı veya aktarılabilecek kayıt bulunamadı.")
        if len(satirlar) > 5000:
            raise HTTPException(413, "Bir Excel dosyasında en fazla 5.000 satır aktarılabilir.")
        return satirlar, sayfa

    @app.post("/api/tanimlar/{tur}/excel-onizle")
    def tanim_excel_onizle(tur: str, istek: TanimExcelIstegi, b: Baglam = Depends(kullanici)):
        if tur not in ("personel", "ogrenci"):
            raise HTTPException(404, "Excel içe aktarma yalnız personel ve öğrenci kayıtları içindir.")
        with b as d:
            gerek(b.k, MOBIL_MODULLER[tur])
            satirlar, sayfa = _tanim_excel_oku(istek, tur)
            plan = _tanim_excel_satirlarini_hazirla(d, tur, satirlar, b.k)
            return {"sayfa": sayfa, "ozet": plan["ozet"], "yazabilir": etkin_yetki(b.k, MOBIL_MODULLER[tur]) == "y"}

    @app.post("/api/tanimlar/{tur}/excel-aktar")
    def tanim_excel_aktar(tur: str, istek: TanimExcelIstegi, b: Baglam = Depends(kullanici)):
        if tur not in ("personel", "ogrenci"):
            raise HTTPException(404, "Excel içe aktarma yalnız personel ve öğrenci kayıtları içindir.")
        with b as d:
            gerek(b.k, MOBIL_MODULLER[tur], yaz=True)
            with d.islem():
                satirlar, sayfa = _tanim_excel_oku(istek, tur)
                plan = _tanim_excel_satirlarini_hazirla(d, tur, satirlar, b.k)
                for values in plan["satirlar"]:
                    d.ekle(tur, values, log=False)
                d.log("Excel içe aktarma", tur, None, f"{len(plan['satirlar'])} kayıt ({sayfa})")
            return {"sayfa": sayfa, "ozet": plan["ozet"], "eklenen": len(plan["satirlar"])}

    @app.post("/api/tanimlar/{tur}")
    def tanim_ekle(tur: str, istek: TanimKaydiIstegi, b: Baglam = Depends(kullanici)):
        if tur not in TANIM_ALANLARI:
            raise HTTPException(404, "Bu tanım türü desteklenmiyor.")
        with b as d:
            gerek(b.k, MOBIL_MODULLER[tur], yaz=True)
            values = _tanim_degerlerini_dogrula(d, tur, istek.degerler)
            bolum = bolum_kisiti(b.k)
            if bolum is not None and values.get("bolum_id", bolum) != bolum:
                raise HTTPException(403, "Yalnızca kendi bölümünüz için kayıt girebilirsiniz.")
            with d.islem():
                kayit_id = d.ekle(tur, values)
            return {"id": kayit_id, "tamam": True}

    @app.put("/api/tanimlar/{tur}/{kayit_id}")
    def tanim_guncelle(tur: str, kayit_id: int, istek: TanimKaydiIstegi, b: Baglam = Depends(kullanici)):
        if tur not in TANIM_ALANLARI:
            raise HTTPException(404, "Bu tanım türü desteklenmiyor.")
        with b as d:
            gerek(b.k, MOBIL_MODULLER[tur], yaz=True)
            eski = d.q1(f"SELECT * FROM {tur} WHERE id = ?", (kayit_id,))
            if not eski:
                raise HTTPException(404, "Tanım kaydı bulunamadı.")
            bolum = bolum_kisiti(b.k)
            if bolum is not None and eski.get("bolum_id") != bolum:
                raise HTTPException(403, "Bu kayıt kendi bölümünüz dışında.")
            values = _tanim_degerlerini_dogrula(d, tur, istek.degerler, kayit_id)
            if bolum is not None and values.get("bolum_id", bolum) != bolum:
                raise HTTPException(403, "Yalnızca kendi bölümünüz için kayıt girebilirsiniz.")
            with d.islem():
                d.guncelle(tur, kayit_id, values)
            return {"id": kayit_id, "tamam": True}

    @app.delete("/api/tanimlar/{tur}/{kayit_id}")
    def tanim_sil(tur: str, kayit_id: int, b: Baglam = Depends(kullanici)):
        if tur not in TANIM_ALANLARI:
            raise HTTPException(404, "Bu tanım türü desteklenmiyor.")
        baglar = {
            "bolum": [("personel", "bolum_id"), ("ogrenci", "bolum_id"), ("siparis", "bolum_id")],
            "personel": [("parca_basi_satir", "kisi_id"), ("fazla_calisma", "personel_id"), ("utp_kisi", "personel_id")],
            "ogrenci": [("parca_basi_satir", "kisi_id")],
            "cari": [("fatura", "cari_id"), ("siparis", "cari_id")],
            "malzeme": [("stok_hareket", "malzeme_id"), ("fatura_kalem", "malzeme_id"), ("maliyet_kalem", "malzeme_id")],
            "urun": [("fatura_kalem", "urun_id"), ("siparis_kalem", "urun_id"), ("maliyet_kalem", "urun_id")],
        }
        with b as d:
            gerek(b.k, MOBIL_MODULLER[tur], yaz=True)
            mevcut = d.q1(f"SELECT * FROM {tur} WHERE id = ?", (kayit_id,))
            if not mevcut:
                raise HTTPException(404, "Tanım kaydı bulunamadı.")
            bolum = bolum_kisiti(b.k)
            if bolum is not None and mevcut.get("bolum_id") != bolum:
                raise HTTPException(403, "Bu kayıt kendi bölümünüz dışında.")
            for tablo, alan in baglar[tur]:
                if d.deger(f"SELECT COUNT(*) FROM {tablo} WHERE {alan} = ?", (kayit_id,), 0):
                    raise HTTPException(409, "Bu kayıt başka işlemlerde kullanılıyor; silmek yerine pasif yapınız.")
            with d.islem():
                d.sil(tur, kayit_id)
            return {"tamam": True}

    @app.get("/api/muhasebe")
    def muhasebe_ozeti(baslangic: str = "", bitis: str = "",
                       yil: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200),
                       b: Baglam = Depends(kullanici)):
        baslangic = baslangic or f"{yil}-01-01"
        bitis = bitis or f"{yil}-12-31"
        try:
            bas = date.fromisoformat(baslangic)
            bit = date.fromisoformat(bitis)
        except ValueError:
            raise HTTPException(400, "Başlangıç ve bitiş tarihleri YYYY-AA-GG biçiminde olmalıdır.") from None
        if bas > bit:
            raise HTTPException(400, "Başlangıç tarihi bitiş tarihinden sonra olamaz.")
        with b as d:
            gerek(b.k, MOBIL_MODULLER["muhasebe"])
            fisler = d.q("""SELECT y.id, y.fis_no, y.tarih, y.aciklama, y.kaynak,
                                   COALESCE(SUM(s.borc), 0) borc, COALESCE(SUM(s.alacak), 0) alacak
                            FROM yevmiye y LEFT JOIN yevmiye_satir s ON s.yevmiye_id = y.id
                            WHERE y.tarih BETWEEN ? AND ? GROUP BY y.id ORDER BY y.tarih, y.id""",
                         (baslangic, bitis))
            mizan = muhasebe.mizan(baslangic, bitis)
            gelir = muhasebe.gelir_tablosu(yil)
            return {"baslangic": baslangic, "bitis": bitis, "yil": yil,
                    "yazabilir": etkin_yetki(b.k, MOBIL_MODULLER["muhasebe"]) == "y",
                    "hesap_silebilir": yetki.yonetici_mi(b.k["rol"]),
                    "yeniden_uretebilir": yetki.yonetici_mi(b.k["rol"]),
                    "fisler": fisler, "mizan": mizan, "gelir_tablosu": gelir,
                    "hesap_plani": d.q("SELECT kod, ad FROM hesap_plani ORDER BY kod")}

    @app.get("/api/muhasebe/yevmiye/{fis_id}")
    def muhasebe_fis_detayi(fis_id: int, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["muhasebe"])
            fis = d.q1("SELECT * FROM yevmiye WHERE id = ?", (fis_id,))
            if not fis:
                raise HTTPException(404, "Yevmiye fişi bulunamadı.")
            fis["satirlar"] = d.q("""SELECT s.hesap_kodu, h.ad hesap_adi, s.aciklama, s.borc, s.alacak
                                      FROM yevmiye_satir s LEFT JOIN hesap_plani h ON h.kod = s.hesap_kodu
                                      WHERE s.yevmiye_id = ? ORDER BY s.borc DESC, s.id""", (fis_id,))
            fis["yazabilir"] = etkin_yetki(b.k, MOBIL_MODULLER["muhasebe"]) == "y"
            return fis

    @app.post("/api/muhasebe/yevmiye")
    def muhasebe_fis_olustur(istek: MuhasebeFisIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["muhasebe"], yaz=True)
            try:
                date.fromisoformat(istek.tarih)
            except ValueError:
                raise HTTPException(400, "Fiş tarihi YYYY-AA-GG biçiminde olmalıdır.") from None
            aciklama = istek.aciklama.strip()
            if not aciklama:
                raise HTTPException(400, "Fiş açıklaması zorunludur.")
            satirlar = []
            for satir in istek.satirlar:
                kod = satir.hesap_kodu.strip()
                borc, alacak = yuvarla(satir.borc), yuvarla(satir.alacak)
                if not kod or bool(borc) == bool(alacak):
                    raise HTTPException(400, "Her satırda hesap seçilmeli ve yalnız borç veya alacak girilmelidir.")
                if not d.q1("SELECT 1 FROM hesap_plani WHERE kod = ?", (kod,)):
                    raise HTTPException(400, f"{kod} hesap planında bulunamadı.")
                satirlar.append((kod, satir.aciklama.strip() or aciklama, borc, alacak))
            toplam_borc = yuvarla(sum(s[2] for s in satirlar))
            toplam_alacak = yuvarla(sum(s[3] for s in satirlar))
            if toplam_borc <= 0 or abs(toplam_borc - toplam_alacak) > 0.009:
                raise HTTPException(400, "Fiş borç ve alacak toplamları eşit ve sıfırdan büyük olmalıdır.")
            try:
                fis_id = muhasebe.fis_olustur(istek.tarih, aciklama, "Manuel", None, satirlar)
            except ValueError as hata:
                raise HTTPException(400, str(hata)) from None
            if fis_id is None:
                raise HTTPException(400, "Fiş satırları kaydedilemedi.")
            d.log("Manuel fiş oluşturma", "yevmiye", fis_id, yeni={"aciklama": aciklama, "satir_sayisi": len(satirlar)})
            return {"tamam": True, "id": fis_id}

    @app.delete("/api/muhasebe/yevmiye/{fis_id}")
    def muhasebe_fis_sil(fis_id: int, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["muhasebe"], yaz=True)
            fis = d.q1("SELECT * FROM yevmiye WHERE id = ?", (fis_id,))
            if not fis:
                raise HTTPException(404, "Yevmiye fişi bulunamadı.")
            if fis["kaynak"] != "Manuel":
                raise HTTPException(409, "Otomatik fişler kaynak işlemden yönetilir.")
            with d.islem():
                d.ex("DELETE FROM yevmiye_satir WHERE yevmiye_id = ?", (fis_id,))
                d.sil("yevmiye", fis_id)
                d.log("Manuel fiş silme", "yevmiye", fis_id, eski={"fis_no": fis["fis_no"]})
            return {"tamam": True}

    @app.post("/api/muhasebe/hesap-plani")
    def muhasebe_hesap_ekle(istek: HesapPlaniIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
                gerek(b.k, MOBIL_MODULLER["muhasebe"], yaz=True)
                kod, ad = istek.kod.strip(), istek.ad.strip()
                if not kod or not ad:
                    raise HTTPException(400, "Hesap kodu ve adı zorunludur.")
                if d.q1("SELECT 1 FROM hesap_plani WHERE kod = ?", (kod,)):
                    raise HTTPException(409, "Bu hesap kodu zaten kullanılıyor.")
                with d.islem():
                    d.ex("INSERT INTO hesap_plani (kod, ad) VALUES (?, ?)", (kod, ad))
                    d.log("Hesap planına hesap ekleme", "hesap_plani", kod, yeni={"ad": ad})
                return {"tamam": True, "kod": kod}

    @app.delete("/api/muhasebe/hesap-plani/{kod}")
    def muhasebe_hesap_sil(kod: str, b: Baglam = Depends(kullanici)):
        with b as d:
                gerek(b.k, MOBIL_MODULLER["muhasebe"], yaz=True)
                if not yetki.yonetici_mi(b.k["rol"]):
                    raise HTTPException(403, "Hesap planı kayıtlarını silme yetkiniz bulunmuyor.")
                hesap = d.q1("SELECT * FROM hesap_plani WHERE kod = ?", (kod,))
                if not hesap:
                    raise HTTPException(404, "Hesap planında kayıt bulunamadı.")
                if d.deger("SELECT COUNT(*) FROM yevmiye_satir WHERE hesap_kodu = ?", (kod,), 0):
                    raise HTTPException(409, "Yevmiye hareketi bulunan hesap silinemez.")
                with d.islem():
                    d.ex("DELETE FROM hesap_plani WHERE kod = ?", (kod,))
                    d.log("Hesap planından hesap silme", "hesap_plani", kod, eski=hesap)
                return {"tamam": True}

    @app.post("/api/muhasebe/yeniden-uret")
    def muhasebe_kayitlarini_yeniden_uret(b: Baglam = Depends(kullanici)):
        with b as d:
                gerek(b.k, MOBIL_MODULLER["muhasebe"], yaz=True)
                if not yetki.yonetici_mi(b.k["rol"]):
                    raise HTTPException(403, "Yevmiye kayıtlarını yeniden üretme yetkiniz bulunmuyor.")
                sayi = muhasebe.tum_kayitlari_yeniden_uret()
                d.log("Yevmiye kayıtlarını yeniden üretme", "yevmiye", detay=f"Toplam fiş: {sayi}")
                return {"tamam": True, "fis_sayisi": sayi}

    # ------------------------------------------------------------ yıl sonu kârı ve ÜTP
    @app.get("/api/yil-sonu")
    def yil_sonu_ozeti(yil: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2199),
                       b: Baglam = Depends(kullanici)):
        with b as d:
            sayfa = MOBIL_MODULLER["yil_sonu"]
            gerek(b.k, sayfa)
            veri = yil_sonu.yil_sonu_verisi(d, yil, etkin_yetki(b.k, sayfa) == "y")
            veri["geri_alabilir"] = (
                yetki.yonetici_mi(b.k["rol"]) and veri["kayit"].get("durum") == "Onaylandı"
                and (not onay.akis_acik() or b.k["rol"] in yetki.GERI_ALABILEN))
            return veri

    @app.post("/api/yil-sonu/{yil}/saat")
    def yil_sonu_saatleri(yil: int, b: Baglam = Depends(kullanici)):
        if not 2000 <= yil <= 2199:
            raise HTTPException(400, "Yıl geçersiz.")
        with b as d:
            gerek(b.k, MOBIL_MODULLER["yil_sonu"], yaz=True)
            veri = yil_sonu.yil_sonu_verisi(d, yil, True)
            if veri["kilitli"]:
                raise HTTPException(409, "Onay bekleyen veya kesinleşmiş yıl sonu dağıtımı düzenlenemez.")
            return {"saatler": yil_sonu.saat_verilerini_getir(d, yil)}

    @app.post("/api/yil-sonu/{yil}/hesapla")
    def yil_sonu_hesapla(yil: int, istek: YilSonuIstegi, b: Baglam = Depends(kullanici)):
        if not 2000 <= yil <= 2199:
            raise HTTPException(400, "Yıl geçersiz.")
        with b as d:
            gerek(b.k, MOBIL_MODULLER["yil_sonu"], yaz=True)
            try:
                sonuc = yil_sonu.hesapla(d, yil, istek.model_dump())
            except ValueError as exc:
                raise HTTPException(409 if "düzenlenemez" in str(exc) else 400, str(exc)) from None
            sonuc.pop("_kayitlar", None)
            return sonuc

    @app.post("/api/yil-sonu/{yil}")
    def yil_sonu_kaydet(yil: int, istek: YilSonuIstegi, b: Baglam = Depends(kullanici)):
        if not 2000 <= yil <= 2199:
            raise HTTPException(400, "Yıl geçersiz.")
        with b as d:
            gerek(b.k, MOBIL_MODULLER["yil_sonu"], yaz=True)
            try:
                sonuc = yil_sonu.hesapla(d, yil, istek.model_dump())
                if sonuc["hatalar"]:
                    raise HTTPException(400, "\n".join(sonuc["hatalar"]))
                yil_sonu.kaydet(d, yil, sonuc)
            except ValueError as exc:
                raise HTTPException(409 if "düzenlenemez" in str(exc) else 400, str(exc)) from None
            return {"tamam": True, "ozet": sonuc["ozet"], "kisiler": sonuc["kisiler"],
                    "hatalar": sonuc["hatalar"], "uyarilar": sonuc["uyarilar"]}

    @app.get("/api/yil-sonu/{yil}/disa-aktar")
    def yil_sonu_disa_aktar(yil: int, tur: str = Query(
            "cetvel", pattern="^(cetvel|banka|merkez-yazisi|shcek-yazisi)$"),
                            b: Baglam = Depends(kullanici)):
        if not 2000 <= yil <= 2199:
            raise HTTPException(400, "Yıl geçersiz.")
        with b as d:
            gerek(b.k, MOBIL_MODULLER["yil_sonu"])
            kayit = d.q1("SELECT * FROM yil_sonu WHERE yil = ?", (yil,))
            if not kayit:
                raise HTTPException(404, "Önce yıl sonu dağıtımını kaydediniz.")
            from pathlib import Path
            import tempfile
            if tur == "cetvel":
                with tempfile.TemporaryDirectory(prefix="dose-utp-") as dizin:
                    yol = belgeler.utp_cetveli(Path(dizin) / f"UTP_Cetveli_{yil}.pdf", yil)
                    icerik = yol.read_bytes()
                dosya_adi = f"UTP_Cetveli_{yil}.pdf"
            elif tur == "banka":
                from dose import excel
                satirlar = d.q(
                    """SELECT p.ad_soyad, p.tckn, p.iban, u.net FROM utp_kisi u JOIN personel p ON p.id = u.personel_id
                       WHERE u.yil = ? AND u.net > 0 ORDER BY p.ad_soyad""", (yil,))
                with tempfile.TemporaryDirectory(prefix="dose-utp-") as dizin:
                    yol = Path(dizin) / f"Banka_UTP_{yil}.xlsx"
                    excel.disa_aktar(
                        yol,
                        [("Banka listesi", ["Adı soyadı", "T.C. kimlik no", "IBAN", "Net tutar", "Açıklama"],
                          [[s["ad_soyad"], s["tckn"] or "", s["iban"] or "", s["net"], f"{yil} yılı ÜTP"]
                           for s in satirlar])],
                        f"{yil} yılı üretimi teşvik primi banka ödeme listesi")
                    icerik = yol.read_bytes()
                dosya_adi = f"Banka_UTP_{yil}.xlsx"
            else:
                from dose.hesap import para
                from dose.pdf import tr_buyuk

                kurum = d.kurum()
                ilce = (kurum.get("ilce") or "").strip()
                muhatap = (f"{tr_buyuk(ilce)} İLÇE MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE"
                           if ilce and tr_buyuk(ilce) != "MERKEZ"
                           else f"{tr_buyuk(kurum.get('il') or '')} İL MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE")
                if tur == "merkez-yazisi":
                    merkez = M.MERKEZ_SAYMANLIK
                    metin = (
                        f"Okulumuz Döner Sermaye İşletmesinin {yil} yılı bilanço kârı "
                        f"{para(kayit.get('donem_kari'))} TL olup, 3423 sayılı Kanun ve ilgi yazı gereğince "
                        f"kârın {para(kayit.get('dagitilan_utp'))} TL'si üretimi teşvik primi olarak dağıtılmış, "
                        f"{para(kayit.get('sermaye_payi'))} TL'si sermayeye eklenmiş, "
                        f"{para(kayit.get('merkez_payi'))} TL'si ise {merkez['ad']} (VKN: {merkez['vkn']}) "
                        f"{merkez['iban']} IBAN numaralı hesabına ...../...../{yil + 1} tarihinde yatırılmıştır. "
                        f"Ayrıca yıllık brüt hasılatın %1'i olan {para(kayit.get('shcek'))} TL SHÇEK payı ilgili hesaba yatırılmıştır.\n\n"
                        "Dekontlar MEBBİS Döner Sermaye Takip Modülüne yüklenmiş olup ekte sunulmuştur.\n\n"
                        "Bilgilerinize arz ederim.")
                    konu, yazi_muhatap, ad = f"{yil} Yılı Kâr Payı Aktarımı", muhatap, f"Kar_Aktarimi_Yazisi_{yil}.pdf"
                else:
                    hasilat = muhasebe.yillik_brut_hasilat(yil)
                    metin = (
                        f"Okulumuz Döner Sermaye İşletmesinin {yil} yılı brüt hasılatı {para(hasilat)} TL olup, "
                        f"2828 sayılı Sosyal Hizmetler Kanununun 18 inci maddesinin (1) numaralı fıkrasının (k) "
                        f"bendi gereğince hesaplanan {para(kayit.get('shcek'))} TL SHÇEK payı ...../01/{yil + 1} "
                        "tarihinde ilgili hesaba yatırılmıştır.\n\nBilgilerinize arz ederim.")
                    konu, yazi_muhatap, ad = f"{yil} Yılı SHÇEK Payı", "İLGİLİ MAKAMA", f"SHCEK_Yazisi_{yil}.pdf"
                yazi = {
                    "sayi": kurum.get("evrak_kodu") or "", "konu": konu, "tarih": date.today().isoformat(),
                    "muhatap": yazi_muhatap,
                    "ilgi": "Millî Eğitim Bakanlığı Destek Hizmetleri Genel Müdürlüğünün 15.01.2026 tarihli DÖSE konulu yazısı.",
                    "metin": metin, "imza1": f"{kurum.get('sayman') or ''}\nSayman",
                    "imza2": f"{kurum.get('harcama_yetkilisi') or ''}\nOkul Müdürü / Harcama Yetkilisi",
                }
                d.ekle("resmi_yazi", {alan: yazi[alan] for alan in (
                    "tarih", "sayi", "konu", "muhatap", "ilgi", "metin", "imza1", "imza2")})
                with tempfile.TemporaryDirectory(prefix="dose-yil-sonu-yazi-") as dizin:
                    yol = belgeler.resmi_yazi(Path(dizin) / ad, yazi)
                    icerik = yol.read_bytes()
                dosya_adi = ad
            d.log("Yıl sonu dışa aktarma", "yil_sonu", yil, detay=tur)
            return {"dosya_adi": dosya_adi, "icerik": base64.b64encode(icerik).decode("ascii")}

    @app.post("/api/yil-sonu/{yil}/geri-al")
    def yil_sonu_geri_al(yil: int, b: Baglam = Depends(kullanici)):
        if not 2000 <= yil <= 2199:
            raise HTTPException(400, "Yıl geçersiz.")
        with b as d:
            sayfa = MOBIL_MODULLER["yil_sonu"]
            gerek(b.k, sayfa, yaz=True)
            if not yetki.yonetici_mi(b.k["rol"]):
                raise HTTPException(403, "Kesinleştirmeyi kaldırma yetkiniz bulunmuyor.")
            try:
                onay.geri_al("Yıl Sonu", yil, b.k, yetki_denetle=True)
            except onay.OnayHatasi as exc:
                raise HTTPException(409, str(exc)) from None
            d.log("Yıl sonu kesinleştirme kaldırma", "yil_sonu", yil)
            return {"tamam": True, "durum_metni": onay.durum_metni(onay.durum("Yıl Sonu", yil))}

    @app.get("/api/raporlar")
    def rapor_verisi(rapor: str = "siparis",
                         yil: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200),
                         b: Baglam = Depends(kullanici)):
        with b as d:
                gerek(b.k, MOBIL_MODULLER["raporlar"])
                try:
                    veri = raporlar.olustur(d, yil, rapor)
                except KeyError:
                    raise HTTPException(404, "Rapor bulunamadı.") from None
                veri["ozet"] = raporlar.ozet(veri)
                return veri

    @app.get("/api/raporlar/{rapor}/disa-aktar")
    def rapor_disa_aktar(rapor: str, bicim: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
                             yil: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200),
                             b: Baglam = Depends(kullanici)):
        with b as d:
                gerek(b.k, MOBIL_MODULLER["raporlar"])
                if rapor not in raporlar.RAPORLAR:
                    raise HTTPException(404, "Rapor bulunamadı.")
                dosya_adi, icerik = raporlar.disari_aktar(d, yil, rapor, bicim)
                d.log("Rapor dışa aktarma", "rapor", rapor, detay=f"{yil} {bicim}")
                return {"dosya_adi": dosya_adi, "icerik": base64.b64encode(icerik).decode("ascii")}

    @app.get("/api/yukumluluk/hazine")
    def hazine_ozeti(yil: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200),
                         b: Baglam = Depends(kullanici)):
        with b as d:
                gerek(b.k, MOBIL_MODULLER["yukumluluk"])
                veri = yukumluluk.hazine_yukumlulukleri(d, yil)
                veri["yazabilir"] = etkin_yetki(b.k, MOBIL_MODULLER["yukumluluk"]) == "y"
                return veri

    @app.get("/api/yukumluluk/hazine/{yil}/{ay}/pdf")
    def hazine_bildirim_pdf(yil: int, ay: int, b: Baglam = Depends(kullanici)):
        if not 2000 <= yil <= 2200 or not 1 <= ay <= 12:
                raise HTTPException(400, "Yıl veya ay geçersiz.")
        with b as d:
                gerek(b.k, MOBIL_MODULLER["yukumluluk"])
                kayit = d.q1("SELECT id FROM hazine_payi WHERE yil = ? AND ay = ?", (yil, ay))
                if not kayit:
                    raise HTTPException(404, "Önce seçili ayın hazine payını hesaplayınız.")
                from pathlib import Path
                import tempfile
                with tempfile.TemporaryDirectory(prefix="dose-hazine-") as dizin:
                    yol = belgeler.hazine_payi_bildirimi(Path(dizin) / f"hazine_{yil}_{ay:02d}.pdf", kayit["id"])
                    icerik = yol.read_bytes()
                return {"dosya_adi": f"Hazine_Payi_{yil}_{ay:02d}.pdf",
                        "icerik": base64.b64encode(icerik).decode("ascii")}

    @app.get("/api/yukumluluk/hazine/disa-aktar")
    def hazine_disari_aktar(bicim: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
                                yil: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200),
                                b: Baglam = Depends(kullanici)):
        with b as d:
                gerek(b.k, MOBIL_MODULLER["yukumluluk"])
                veri = yukumluluk.hazine_yukumlulukleri(d, yil)
                kolonlar = [{"anahtar": anahtar, "baslik": baslik, "tur": tur}
                            for anahtar, baslik, tur in yukumluluk.HAZINE_KOLONLARI]
                ad, icerik = yukumluluk.tablo_disa_aktar(
                    f"{yil} Hazine Payı Yıllık Özeti", f"Hazine_Payi_{yil}",
                    kolonlar, veri["aylik"], bicim)
                d.log("Hazine payı dışa aktarma", "hazine_payi", yil, detay=bicim)
                return {"dosya_adi": ad, "icerik": base64.b64encode(icerik).decode("ascii")}

    @app.post("/api/yukumluluk/hazine/hesapla")
    def hazine_hesapla(istek: HazineHesapIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
                gerek(b.k, MOBIL_MODULLER["yukumluluk"], yaz=True)
                bugun = date.today()
                aylar = [istek.ay] if istek.ay else [
                    ay for ay in range(1, 13)
                    if date(istek.yil, ay, 1) < date(bugun.year, bugun.month, 1)
                ]
                hesaplanan = []
                with d.islem():
                    for ay in aylar:
                        tahsil = muhasebe.aylik_tahsil_edilen_hasilat(istek.yil, ay)
                        parametreler = d.parametreler(istek.yil)
                        degerler = {"yil": istek.yil, "ay": ay, "tahsil_edilen": tahsil,
                                    "oran": parametreler["hazine_payi_orani"],
                                    "tutar": yuvarla(tahsil * parametreler["hazine_payi_orani"])}
                        kayit = d.q1("SELECT id FROM hazine_payi WHERE yil = ? AND ay = ?", (istek.yil, ay))
                        if kayit:
                            odeme = d.q1("SELECT id FROM kasa_banka WHERE kaynak = ? AND kaynak_id = ? LIMIT 1",
                                         ("HazinePayi", kayit["id"]))
                            if odeme:
                                continue
                            d.guncelle("hazine_payi", kayit["id"], degerler)
                            hazine_id = kayit["id"]
                        else:
                            degerler["durum"] = "Hesaplandı"
                            hazine_id = d.ekle("hazine_payi", degerler)
                        muhasebe.hazine_payi_kaydi(hazine_id)
                        hesaplanan.append(ay)
                    d.log("Hazine payı hesaplama", "hazine_payi", detay=f"{istek.yil}: {hesaplanan}")
                return {"tamam": True, "hesaplanan_aylar": hesaplanan}

    @app.post("/api/yukumluluk/hazine/bildir")
    def hazine_bildir(istek: HazineHesapIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
                gerek(b.k, MOBIL_MODULLER["yukumluluk"], yaz=True)
                if not istek.ay:
                    raise HTTPException(400, "Bildirim için ay seçilmelidir.")
                kayit = d.q1("SELECT * FROM hazine_payi WHERE yil = ? AND ay = ?", (istek.yil, istek.ay))
                if not kayit:
                    raise HTTPException(404, "Önce seçili ayın hazine payını hesaplayınız.")
                if d.q1("SELECT id FROM kasa_banka WHERE kaynak = ? AND kaynak_id = ? LIMIT 1",
                        ("HazinePayi", kayit["id"])):
                    raise HTTPException(409, "Ödemesi yapılmış ayın bildirim kaydı değiştirilemez.")
                bugun = date.today().isoformat()
                with d.islem():
                    d.guncelle("hazine_payi", kayit["id"],
                               {"bildirim_tarihi": bugun, "durum": "Bildirildi"})
                    d.log("Hazine payı bildirildi", "hazine_payi", kayit["id"])
                return {"tamam": True}

    @app.post("/api/yukumluluk/odeme")
    def yukumluluk_odeme(istek: YukumlulukOdemeIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
                gerek(b.k, MOBIL_MODULLER["yukumluluk"], yaz=True)
                kaynaklar = {"hazine": ("HazinePayi", "Hazine Payı Ödemesi"),
                             "shcek": ("SHCEK", "SHÇEK Payı Ödemesi"),
                             "merkez": ("MerkezKar", "Merkez Saymanlık Kâr Aktarımı")}
                kaynak, islem_turu = kaynaklar[istek.tur]
                kaynak_id: int
                if istek.tur == "hazine":
                    if not istek.ay:
                        raise HTTPException(400, "Hazine payı ödemesi için ay seçilmelidir.")
                    kayit = d.q1("SELECT * FROM hazine_payi WHERE yil = ? AND ay = ?", (istek.yil, istek.ay))
                    if not kayit:
                        raise HTTPException(404, "Önce hazine payını hesaplayınız.")
                    kaynak_id = kayit["id"]
                    tutar = kayit["tutar"] or 0
                    aciklama = f"{M.AYLAR[istek.ay - 1]} {istek.yil} hazine payı"
                elif istek.tur == "shcek":
                    kaynak_id = istek.yil
                    parametreler = d.parametreler(istek.yil)
                    tutar = yuvarla(muhasebe.yillik_brut_hasilat(istek.yil) * parametreler["shcek_orani"])
                    aciklama = f"{istek.yil} yılı SHÇEK payı (2828 s.K. md.18/1-k)"
                else:
                    if istek.ay:
                        raise HTTPException(400, "Merkez Saymanlık aktarımı yıllık yapılır.")
                    kaynak_id = istek.yil
                    dagitim = d.q1("SELECT * FROM yil_sonu WHERE yil = ?", (istek.yil,))
                    if not dagitim:
                        raise HTTPException(400, "Önce yıl sonu kâr dağıtımını yapınız.")
                    tutar = dagitim["merkez_payi"] or 0
                    aciklama = f"{istek.yil} yılı kâr payı - {M.MERKEZ_SAYMANLIK['iban']}"
                if tutar <= 0:
                    raise HTTPException(400, "Ödenecek tutar sıfırdan büyük olmalıdır.")
                if d.q1("SELECT id FROM kasa_banka WHERE kaynak = ? AND kaynak_id = ? LIMIT 1",
                        (kaynak, kaynak_id)):
                    raise HTTPException(409, "Bu yükümlülük için ödeme kaydı zaten var.")
                with d.islem():
                    hareket_id = d.ekle("kasa_banka", {
                        "tarih": date.today().isoformat(), "hesap": "Banka (102)", "yon": "Çıkış",
                        "tur": islem_turu, "tutar": tutar, "hasilat_tutari": 0,
                        "aciklama": aciklama, "kaynak": kaynak, "kaynak_id": kaynak_id,
                    })
                    muhasebe.kasa_kaydi(hareket_id)
                    if istek.tur == "hazine":
                        d.guncelle("hazine_payi", kaynak_id,
                                   {"durum": "Ödendi", "odeme_tarihi": date.today().isoformat()})
                return {"tamam": True, "tutar": tutar}

    @app.get("/api/vergi")
    def vergi_ozeti(yil: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200),
                        b: Baglam = Depends(kullanici)):
        with b as d:
                gerek(b.k, MOBIL_MODULLER["vergi"])
                return {"yil": yil, "aylar": yukumluluk.kdv_muhtasar_ozeti(d, yil)}

    @app.get("/api/vergi/disa-aktar")
    def vergi_disari_aktar(bicim: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
                               yil: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200),
                               b: Baglam = Depends(kullanici)):
        with b as d:
                gerek(b.k, MOBIL_MODULLER["vergi"])
                satirlar = yukumluluk.kdv_muhtasar_ozeti(d, yil)
                kolonlar = [{"anahtar": anahtar, "baslik": baslik, "tur": tur}
                            for anahtar, baslik, tur in yukumluluk.VERGI_KOLONLARI]
                ad, icerik = yukumluluk.tablo_disa_aktar(
                    f"{yil} KDV ve Muhtasar Özeti", f"KDV_Muhtasar_{yil}",
                    kolonlar, satirlar, bicim)
                d.log("KDV ve muhtasar özeti dışa aktarma", "vergi", yil, detay=bicim)
                return {"dosya_adi": ad, "icerik": base64.b64encode(icerik).decode("ascii")}

    @app.get("/api/vergi/{yil}/{ay}/muhtasar")
    def vergi_muhtasar_detayi(yil: int, ay: int, b: Baglam = Depends(kullanici)):
        if not 2000 <= yil <= 2200 or not 1 <= ay <= 12:
                raise HTTPException(400, "Yıl veya ay geçersiz.")
        with b as d:
                gerek(b.k, MOBIL_MODULLER["vergi"])
                return {"yil": yil, "ay": ay, "detay": yukumluluk.muhtasar_detayi(d, yil, ay)}

    # ------------------------------------------------------------ listeler
    def _stok_bakiyeleri(d):
        bakiyeler = d.q("""SELECT m.id, m.kod, m.ad, m.tur, m.birim, m.kritik_stok,
                                  COALESCE(SUM(CASE WHEN h.yon = 'Giriş' THEN h.miktar END), 0) giris,
                                  COALESCE(SUM(CASE WHEN h.yon = 'Çıkış' THEN h.miktar END), 0) cikis
                           FROM malzeme m LEFT JOIN stok_hareket h ON h.malzeme_id = m.id
                           WHERE m.aktif = 1 GROUP BY m.id ORDER BY m.ad""")
        for r in bakiyeler:
            r["kalan"] = yuvarla(r["giris"] - r["cikis"], 3)
            r["ortalama_maliyet"] = muhasebe.ortalama_maliyet(r["id"])
            r["tutar"] = yuvarla(r["kalan"] * r["ortalama_maliyet"])
            r["kritik"] = bool(r["kritik_stok"] and r["kalan"] <= r["kritik_stok"])
        return bakiyeler

    @app.get("/api/stok")
    def stok(yil: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200),
             b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["stok"])
            bakiyeler = _stok_bakiyeleri(d)
            hareketler = d.q("""SELECT h.id, h.tarih, h.malzeme_id, m.ad malzeme, m.birim, h.yon, h.miktar,
                                       h.birim_fiyat, h.miktar * h.birim_fiyat tutar, h.kaynak, h.kaynak_id,
                                       h.siparis_id, s.siparis_no, h.aciklama
                                FROM stok_hareket h JOIN malzeme m ON m.id = h.malzeme_id
                                LEFT JOIN siparis s ON s.id = h.siparis_id
                                WHERE substr(h.tarih, 1, 4) = ? ORDER BY h.tarih DESC, h.id DESC LIMIT 2000""",
                               (str(yil),))
            for h in hareketler:
                h["silinebilir"] = h["kaynak"] != "Fatura" and etkin_yetki(b.k, MOBIL_MODULLER["stok"]) == "y"
            return {"malzemeler": bakiyeler, "hareketler": hareketler,
                    "toplam": yuvarla(sum(r["tutar"] for r in bakiyeler)),
                    "yazabilir": etkin_yetki(b.k, MOBIL_MODULLER["stok"]) == "y",
                    "surum": d.son_islem_no(),
                    "giris_nedenleri": M.STOK_GIRIS_NEDENLERI, "cikis_nedenleri": M.STOK_CIKIS_NEDENLERI,
                    "malzeme_secenekleri": [m for m in bakiyeler if m["id"]],
                    "siparisler": d.q("""SELECT id, siparis_no, konu FROM siparis
                                          WHERE durum NOT IN ('İptal', 'Kapandı') ORDER BY id DESC LIMIT 500""")}

    @app.post("/api/stok/hareketler")
    def stok_hareket_ekle(istek: StokHareketIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["stok"], yaz=True)
            if istek.yon not in ("Giriş", "Çıkış"):
                raise HTTPException(400, "Stok hareket yönü 'Giriş' veya 'Çıkış' olmalıdır.")
            nedenler = M.STOK_GIRIS_NEDENLERI if istek.yon == "Giriş" else M.STOK_CIKIS_NEDENLERI
            if istek.neden not in nedenler:
                raise HTTPException(400, "Stok hareket nedeni seçilen yöne uygun değil.")
            try:
                hareket_tarihi = date.fromisoformat(istek.tarih)
            except ValueError:
                raise HTTPException(400, "Stok hareketi tarihi YYYY-AA-GG biçiminde olmalıdır.") from None
            if hareket_tarihi.isoformat() != istek.tarih:
                raise HTTPException(400, "Stok hareketi tarihi YYYY-AA-GG biçiminde olmalıdır.")
            malzeme = d.q1("SELECT id FROM malzeme WHERE id = ? AND aktif = 1", (istek.malzeme_id,))
            if not malzeme:
                raise HTTPException(404, "Malzeme bulunamadı veya pasif.")
            if istek.yon == "Giriş" and istek.birim_fiyat == 0 and not istek.sifir_fiyat_onaylandi:
                raise HTTPException(400, "Sıfır birim fiyatlı stok girişi için açık onay veriniz.")
            if istek.siparis_id and not d.q1(
                    "SELECT id FROM siparis WHERE id = ? AND durum NOT IN ('İptal', 'Kapandı')",
                    (istek.siparis_id,)):
                raise HTTPException(400, "Sipariş bulunamadı, iptal edildi veya kapandı.")
            with d.islem():
                fiyat = istek.birim_fiyat
                if istek.yon == "Çıkış":
                    kalan = muhasebe.stok_miktari(istek.malzeme_id)
                    if istek.miktar > kalan + 1e-9:
                        raise HTTPException(400, f"Yetersiz stok. Mevcut: {kalan:g}")
                    fiyat = muhasebe.ortalama_maliyet(istek.malzeme_id, istek.tarih)
                aciklama = istek.neden + (f" - {istek.aciklama.strip()}" if istek.aciklama.strip() else "")
                hareket_id = d.ekle("stok_hareket", {
                    "tarih": istek.tarih, "malzeme_id": istek.malzeme_id, "yon": istek.yon,
                    "miktar": istek.miktar, "birim_fiyat": fiyat, "kaynak": "Manuel",
                    "siparis_id": istek.siparis_id, "aciklama": aciklama,
                })
                if istek.yon == "Çıkış":
                    muhasebe.stok_cikis_kaydi(hareket_id)
            d.log("Manuel stok hareketi oluşturma", "stok_hareket", hareket_id,
                  detay=f"{istek.yon} / {istek.miktar:g} / {istek.neden}")
            return {"id": hareket_id, "birim_fiyat": fiyat, "tutar": yuvarla(istek.miktar * fiyat),
                    "surum": d.son_islem_no()}

    @app.delete("/api/stok/hareketler/{hareket_id:int}")
    def stok_hareket_sil(hareket_id: int, surum: int = Query(..., ge=0), b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["stok"], yaz=True)
            with d.islem():
                hareket = d.q1("SELECT * FROM stok_hareket WHERE id = ?", (hareket_id,))
                if not hareket:
                    raise HTTPException(404, "Stok hareketi bulunamadı.")
                if hareket["kaynak"] == "Fatura":
                    raise HTTPException(400, "Faturadan oluşan hareket ilgili belge düzenlenerek veya iptal edilerek değiştirilmelidir.")
                d.cakisma_denetle("stok_hareket", hareket_id, surum)
                d.sil("stok_hareket", hareket_id)
                muhasebe.fis_sil("Stok", hareket_id)
            return {"tamam": True}

    @app.get("/api/stok/disa-aktar")
    def stok_disa_aktar(yil: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200),
                        b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["stok"])
            bakiyeler = _stok_bakiyeleri(d)
            hareketler = d.q("""SELECT h.tarih, h.yon, m.kod, m.ad malzeme, h.miktar, m.birim,
                                       h.birim_fiyat, h.miktar * h.birim_fiyat tutar, h.kaynak,
                                       s.siparis_no, h.aciklama
                                FROM stok_hareket h JOIN malzeme m ON m.id = h.malzeme_id
                                LEFT JOIN siparis s ON s.id = h.siparis_id
                                WHERE substr(h.tarih, 1, 4) = ? ORDER BY h.tarih DESC, h.id DESC LIMIT 5000""",
                               (str(yil),))
            with tempfile.TemporaryDirectory(prefix="dose-stok-") as dizin:
                yol = excel.disa_aktar(
                    Path(dizin) / f"Stok_{yil}.xlsx",
                    [("Stok bakiyeleri", ["Kod", "Malzeme", "Tür", "Birim", "Giriş", "Çıkış", "Kalan",
                                           "Kritik seviye", "Ort. maliyet", "Stok değeri"],
                      [[r["kod"] or "", r["ad"], r["tur"] or "", r["birim"] or "", r["giris"], r["cikis"],
                        r["kalan"], r["kritik_stok"] or 0, r["ortalama_maliyet"], r["tutar"]] for r in bakiyeler]),
                     ("Stok hareketleri", ["Tarih", "Yön", "Kod", "Malzeme", "Miktar", "Birim",
                                           "Birim fiyat", "Tutar", "Kaynak", "Sipariş", "Açıklama"],
                      [[r["tarih"], r["yon"], r["kod"] or "", r["malzeme"], r["miktar"], r["birim"] or "",
                        r["birim_fiyat"] or 0, r["tutar"] or 0, r["kaynak"] or "", r["siparis_no"] or "",
                        r["aciklama"] or ""] for r in hareketler])])
                icerik = yol.read_bytes()
            d.log("Stok bakiyesi ve hareketlerini dışa aktarma", "stok_hareket", detay=str(yil))
            return {"dosya_adi": yol.name, "icerik": base64.b64encode(icerik).decode("ascii")}

    @app.get("/api/kasa")
    def kasa(yil: int = Query(default_factory=lambda: date.today().year), ay: int = Query(0, ge=0, le=12),
             hesap: str = "", b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["kasa"])
            donem = f"{yil}" + (f"-{ay:02d}" if ay else "")
            sql = """SELECT k.id, k.tarih, k.hesap, k.yon, k.tur, k.tutar, k.hasilat_tutari, k.belge_no, k.aciklama,
                            k.kaynak, k.kaynak_id, k.cari_id, k.fatura_id, k.siparis_id,
                            c.unvan, f.belge_no fatura_no, s.siparis_no
                     FROM kasa_banka k LEFT JOIN cari c ON c.id = k.cari_id LEFT JOIN fatura f ON f.id = k.fatura_id
                     LEFT JOIN siparis s ON s.id = k.siparis_id WHERE k.tarih LIKE ?"""
            prm: list = [donem + "%"]
            if hesap:
                sql += " AND k.hesap = ?"
                prm.append(hesap)
            hareketler = d.q(sql + " ORDER BY k.tarih DESC, k.id DESC LIMIT 500", prm)
            bakiye = lambda h: yuvarla(d.deger("SELECT SUM(CASE WHEN yon = 'Giriş' THEN tutar ELSE -tutar END) FROM kasa_banka "
                                               "WHERE hesap = ?", (h,), 0.0))
            return {"kasa": bakiye("Kasa (100)"), "banka": bakiye("Banka (102)"), "hareketler": hareketler,
                    "giris": yuvarla(sum(h["tutar"] for h in hareketler if h["yon"] == "Giriş")),
                    "cikis": yuvarla(sum(h["tutar"] for h in hareketler if h["yon"] == "Çıkış")),
                    "yazabilir": etkin_yetki(b.k, MOBIL_MODULLER["kasa"]) == "y",
                    "surum": d.son_islem_no(), "hesaplar": M.KASA_HESAPLARI,
                    "giris_turleri": ["Tahsilat", "Peşinat/Avans Tahsilatı", "Faiz/Diğer Gelir", "Sermaye", "Diğer"],
                    "cikis_turleri": ["Ödeme", "Hazine Payı Ödemesi", "SHÇEK Payı Ödemesi", "Vergi Ödemesi",
                                      "Personel Ödemesi", "Merkez Saymanlık Kâr Aktarımı", "Diğer"],
                    "cariler": d.q("SELECT id, unvan FROM cari WHERE aktif = 1 ORDER BY unvan"),
                    "faturalar": (d.q("""SELECT f.id, f.tur, f.belge_no, f.tarih, f.cari_id, f.siparis_id, c.unvan,
                                                f.net_tutar - COALESCE(f.avans_mahsup, 0) -
                                                COALESCE((SELECT SUM(tutar) FROM kasa_banka k WHERE k.fatura_id = f.id), 0) kalan
                                         FROM fatura f LEFT JOIN cari c ON c.id = f.cari_id
                                         WHERE f.iptal = 0 ORDER BY f.tarih DESC, f.id DESC LIMIT 500""")
                                  if any(etkin_yetki(b.k, modul) for modul in FATURA_SAYFASI.values()) else []),
                    "siparisler": d.q("SELECT id, siparis_no, konu FROM siparis WHERE durum != 'İptal' ORDER BY id DESC LIMIT 500")}

    @app.get("/api/kasa/disa-aktar")
    def kasa_disa_aktar(yil: int = Query(default_factory=lambda: date.today().year),
                        ay: int = Query(0, ge=0, le=12), hesap: str = "", b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["kasa"])
            donem = f"{yil}" + (f"-{ay:02d}" if ay else "")
            sql = """SELECT k.tarih, k.hesap, k.yon, k.tur, c.unvan, f.belge_no fatura_no, s.siparis_no,
                            k.belge_no, k.tutar, k.hasilat_tutari, k.aciklama, k.kaynak
                     FROM kasa_banka k LEFT JOIN cari c ON c.id = k.cari_id
                     LEFT JOIN fatura f ON f.id = k.fatura_id LEFT JOIN siparis s ON s.id = k.siparis_id
                     WHERE k.tarih LIKE ?"""
            prm: list[Any] = [donem + "%"]
            if hesap:
                if hesap not in M.KASA_HESAPLARI:
                    raise HTTPException(400, "Kasa/banka hesabı geçersiz.")
                sql += " AND k.hesap = ?"
                prm.append(hesap)
            rows = d.q(sql + " ORDER BY k.tarih DESC, k.id DESC LIMIT 5000", prm)
            with tempfile.TemporaryDirectory(prefix="dose-kasa-") as dizin:
                yol = excel.disa_aktar(
                    Path(dizin) / f"Kasa_Banka_{donem}.xlsx",
                    [("Kasa ve Banka", ["Tarih", "Hesap", "Yön", "İşlem türü", "Cari", "Fatura", "Sipariş",
                                        "Dekont / makbuz", "Tutar", "Hasılat", "Açıklama", "Kaynak"],
                      [[r["tarih"], r["hesap"], r["yon"], r["tur"], r["unvan"] or "", r["fatura_no"] or "",
                        r["siparis_no"] or "", r["belge_no"] or "", r["tutar"] or 0, r["hasilat_tutari"] or 0,
                        r["aciklama"] or "", r["kaynak"] or ""] for r in rows])])
                icerik = yol.read_bytes()
            d.log("Kasa/banka dışa aktarma", "kasa_banka", detay=donem)
            return {"dosya_adi": yol.name, "icerik": base64.b64encode(icerik).decode("ascii")}

    def _kasa_hasilati(d, istek: KasaIstegi) -> float:
        if istek.yon != "Giriş" or istek.tur not in M.HASILAT_ETKILI_TURLER:
            return 0.0
        if istek.hasilat_tutari is not None:
            return yuvarla(istek.hasilat_tutari)
        if istek.tur == "Tahsilat" and istek.fatura_id:
            f = d.q1("SELECT matrah, net_tutar FROM fatura WHERE id = ?", (istek.fatura_id,))
            return yuvarla(istek.tutar * f["matrah"] / f["net_tutar"]) if f and f["net_tutar"] else istek.tutar
        if istek.tur == "Peşinat/Avans Tahsilatı" and istek.siparis_id:
            kdv = d.deger("SELECT kdv_orani FROM siparis WHERE id = ?", (istek.siparis_id,), 0.0) or 0
            return yuvarla(istek.tutar / (1 + kdv))
        if istek.tur == "Tahsilat":
            kdv = d.parametreler(int(istek.tarih[:4]))["kdv_genel"]
            return yuvarla(istek.tutar / (1 + kdv))
        return yuvarla(istek.tutar)

    def _kasa_hareketini_kaydet(d, istek: KasaIstegi, hareket_id: int | None = None):
        if istek.hesap not in M.KASA_HESAPLARI or istek.yon not in ("Giriş", "Çıkış"):
            raise HTTPException(400, "Kasa/banka hesabı veya hareket yönü geçersiz.")
        turler = ({"Tahsilat", "Peşinat/Avans Tahsilatı", "Faiz/Diğer Gelir", "Sermaye", "Diğer"}
                  if istek.yon == "Giriş" else
                  {"Ödeme", "Hazine Payı Ödemesi", "SHÇEK Payı Ödemesi", "Vergi Ödemesi",
                   "Personel Ödemesi", "Merkez Saymanlık Kâr Aktarımı", "Diğer"})
        if istek.tur not in turler:
            raise HTTPException(400, "Hareket türü seçilen yönle uyumlu değil.")
        try:
            hareket_tarihi = date.fromisoformat(istek.tarih)
        except ValueError:
            raise HTTPException(400, "Hareket tarihi YYYY-AA-GG biçiminde olmalıdır.") from None
        if hareket_tarihi.isoformat() != istek.tarih:
            raise HTTPException(400, "Hareket tarihi YYYY-AA-GG biçiminde olmalıdır.")
        eski = d.q1("SELECT * FROM kasa_banka WHERE id = ?", (hareket_id,)) if hareket_id else None
        if hareket_id and not eski:
            raise HTTPException(404, "Kasa/banka hareketi bulunamadı.")
        if eski and eski.get("kaynak"):
            raise HTTPException(400, f"Bu kayıt '{eski['kaynak']}' modülünden oluşturuldu; ilgili modülden değiştiriniz.")
        fatura = d.q1("SELECT * FROM fatura WHERE id = ? AND iptal = 0", (istek.fatura_id,)) if istek.fatura_id else None
        if istek.fatura_id and not fatura:
            raise HTTPException(400, "Fatura bulunamadı veya iptal edilmiş.")
        if istek.tur in ("Tahsilat", "Ödeme"):
            beklenen = "Satış" if istek.tur == "Tahsilat" else "Alış"
            if not fatura or fatura["tur"] != beklenen:
                if istek.fatura_id:
                    raise HTTPException(400, f"{istek.tur} için {beklenen.lower()} faturası seçilmelidir.")
            if not istek.cari_id:
                raise HTTPException(400, "Tahsilat/ödeme için cari seçiniz.")
        elif fatura:
            raise HTTPException(400, "Yalnız fatura tahsilatı veya ödemesi faturaya bağlanabilir.")
        if fatura and istek.cari_id != fatura["cari_id"]:
            raise HTTPException(400, "Seçilen cari, faturanın carisiyle eşleşmiyor.")
        siparis = d.q1("SELECT id FROM siparis WHERE id = ? AND durum != 'İptal'", (istek.siparis_id,)) if istek.siparis_id else None
        if istek.siparis_id and not siparis:
            raise HTTPException(400, "Sipariş bulunamadı veya iptal edilmiş.")
        if fatura and fatura["siparis_id"] and istek.siparis_id not in (None, fatura["siparis_id"]):
            raise HTTPException(400, "Ödeme/tahsilat sipariş bağlantısı faturayla uyuşmuyor.")
        siparis_id = fatura["siparis_id"] if fatura and fatura["siparis_id"] else istek.siparis_id
        if istek.tur == "Peşinat/Avans Tahsilatı" and (istek.yon != "Giriş" or not siparis_id):
            raise HTTPException(400, "Sipariş avansı giriş yönünde bir siparişe bağlanmalıdır.")
        if istek.tur in ("Tahsilat", "Ödeme") and not istek.cari_id:
            raise HTTPException(400, "Tahsilat/ödeme için cari seçiniz.")
        if fatura:
            odenen = d.deger("SELECT SUM(tutar) FROM kasa_banka WHERE fatura_id = ? AND id != ?",
                             (fatura["id"], hareket_id or 0), 0.0) or 0
            kalan = yuvarla(fatura["net_tutar"] - (fatura["avans_mahsup"] or 0) - odenen)
            if istek.tutar > kalan + 0.009:
                raise HTTPException(400, f"Tutar, belgenin açık bakiyesini ({para(kalan)} TL) aşıyor.")
        if istek.yon == "Çıkış":
            bakiye = d.deger("SELECT SUM(CASE WHEN yon = 'Giriş' THEN tutar ELSE -tutar END) FROM kasa_banka "
                             "WHERE hesap = ? AND id != ?", (istek.hesap, hareket_id or 0), 0.0) or 0
            if istek.tutar > bakiye + 0.009 and not istek.bakiye_uyarisi_onaylandi:
                raise HTTPException(409, f"{istek.hesap} bakiye {para(bakiye)} TL; yine de kaydetmek için onaylayınız.")
        veri = {
            "tarih": istek.tarih, "hesap": istek.hesap, "yon": istek.yon, "tur": istek.tur,
            "tutar": istek.tutar, "hasilat_tutari": _kasa_hasilati(d, istek),
            "cari_id": istek.cari_id, "fatura_id": istek.fatura_id, "siparis_id": siparis_id,
            "belge_no": istek.belge_no.strip() or None, "aciklama": istek.aciklama.strip() or None,
            "kaynak": None, "kaynak_id": None,
        }
        with d.islem():
            if hareket_id:
                if istek.surum is None:
                    raise HTTPException(400, "Hareket sürümü gereklidir; kaydı yeniden açıp tekrar deneyiniz.")
                d.cakisma_denetle("kasa_banka", hareket_id, istek.surum)
                d.guncelle("kasa_banka", hareket_id, veri)
            else:
                hareket_id = d.ekle("kasa_banka", veri)
            muhasebe.kasa_kaydi(hareket_id)
        return {"id": hareket_id, "surum": d.son_islem_no(), "hasilat_tutari": veri["hasilat_tutari"]}

    def _kasa_fatura_yetkisi(d, k, fatura_id: int | None):
        if not fatura_id:
            return
        fatura = d.q1("SELECT tur FROM fatura WHERE id = ?", (fatura_id,))
        if fatura:
            gerek(k, FATURA_SAYFASI[fatura["tur"]], yaz=True)

    @app.get("/api/kasa/{hareket_id:int}")
    def kasa_hareket_detayi(hareket_id: int, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["kasa"])
            hareket = d.q1("""SELECT k.*, c.unvan, f.belge_no fatura_no, s.siparis_no
                              FROM kasa_banka k LEFT JOIN cari c ON c.id = k.cari_id
                              LEFT JOIN fatura f ON f.id = k.fatura_id LEFT JOIN siparis s ON s.id = k.siparis_id
                              WHERE k.id = ?""", (hareket_id,))
            if not hareket:
                raise HTTPException(404, "Kasa/banka hareketi bulunamadı.")
            hareket["surum"] = d.son_islem_no()
            kasa_yazabilir = etkin_yetki(b.k, MOBIL_MODULLER["kasa"]) == "y"
            fatura = d.q1("SELECT tur FROM fatura WHERE id = ?", (hareket["fatura_id"],)) if hareket["fatura_id"] else None
            fatura_yazabilir = not fatura or etkin_yetki(b.k, FATURA_SAYFASI[fatura["tur"]]) == "y"
            hareket["duzenlenebilir"] = not hareket["kaynak"] and kasa_yazabilir and fatura_yazabilir
            hareket["silinebilir"] = hareket["duzenlenebilir"]
            return hareket

    @app.post("/api/kasa")
    def kasa_hareket_ekle(istek: KasaIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["kasa"], yaz=True)
            with d.islem():
                _kasa_fatura_yetkisi(d, b.k, istek.fatura_id)
                return _kasa_hareketini_kaydet(d, istek)

    @app.put("/api/kasa/{hareket_id:int}")
    def kasa_hareket_guncelle(hareket_id: int, istek: KasaIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["kasa"], yaz=True)
            with d.islem():
                onceki = d.q1("SELECT fatura_id FROM kasa_banka WHERE id = ?", (hareket_id,))
                if onceki:
                    _kasa_fatura_yetkisi(d, b.k, onceki["fatura_id"])
                _kasa_fatura_yetkisi(d, b.k, istek.fatura_id)
                return _kasa_hareketini_kaydet(d, istek, hareket_id)

    @app.delete("/api/kasa/{hareket_id:int}")
    def kasa_hareket_sil(hareket_id: int, surum: int = Query(..., ge=0), b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["kasa"], yaz=True)
            with d.islem():
                hareket = d.q1("SELECT * FROM kasa_banka WHERE id = ?", (hareket_id,))
                if not hareket:
                    raise HTTPException(404, "Kasa/banka hareketi bulunamadı.")
                if hareket["kaynak"]:
                    raise HTTPException(400, f"Bu kayıt '{hareket['kaynak']}' modülünden oluşturuldu; ilgili modülden siliniz.")
                _kasa_fatura_yetkisi(d, b.k, hareket["fatura_id"])
                d.cakisma_denetle("kasa_banka", hareket_id, surum)
                d.sil("kasa_banka", hareket_id)
                muhasebe.fis_sil("KasaBanka", hareket_id)
            return {"tamam": True}

    @app.get("/api/faturalar")
    def faturalar(tur: str = "Satış", yil: int = Query(default_factory=lambda: date.today().year),
                  ay: int = Query(0, ge=0, le=12), b: Baglam = Depends(kullanici)):
        if tur not in FATURA_SAYFASI:
            raise HTTPException(400, "Fatura türü 'Satış' veya 'Alış' olmalıdır.")
        with b as d:
            gerek(b.k, FATURA_SAYFASI[tur])
            donem = f"{yil}" + (f"-{ay:02d}" if ay else "")
            satirlar = d.q("""SELECT f.id, f.tarih, f.belge_turu, f.belge_no, f.matrah, f.kdv, f.genel_toplam, f.net_tutar,
                                     f.iptal, f.gider_turu, f.temin_usulu, c.unvan, s.siparis_no,
                                     f.net_tutar - COALESCE(f.avans_mahsup, 0) - COALESCE((SELECT SUM(tutar) FROM kasa_banka k
                                     WHERE k.fatura_id = f.id), 0) kalan
                              FROM fatura f LEFT JOIN cari c ON c.id = f.cari_id LEFT JOIN siparis s ON s.id = f.siparis_id
                              WHERE f.tur = ? AND f.tarih LIKE ? ORDER BY f.tarih DESC, f.id DESC LIMIT 500""",
                           (tur, donem + "%"))
            for s in satirlar:
                s["durum"] = "İPTAL" if s["iptal"] else ("Kapandı" if abs(s["kalan"] or 0) < 0.01 else "Açık")
            gecerli = [s for s in satirlar if not s["iptal"]]
            return {"faturalar": satirlar, "matrah": yuvarla(sum(s["matrah"] or 0 for s in gecerli)),
                    "kdv": yuvarla(sum(s["kdv"] or 0 for s in gecerli)),
                    "acik_bakiye": yuvarla(sum(s["kalan"] or 0 for s in gecerli)),
                    "yazabilir": etkin_yetki(b.k, FATURA_SAYFASI[tur]) == "y"}

    @app.get("/api/secenekler/fatura")
    def fatura_secenekleri(tur: str = "Satış", b: Baglam = Depends(kullanici)):
        if tur not in FATURA_SAYFASI:
            raise HTTPException(400, "Fatura türü 'Satış' veya 'Alış' olmalıdır.")
        with b as d:
            gerek(b.k, FATURA_SAYFASI[tur])
            if tur == "Satış":
                cariler = d.q("SELECT id, unvan FROM cari WHERE aktif = 1 AND tur NOT IN ('Tedarikçi', 'Çiftçi (Müstahsil)') ORDER BY unvan")
                kalemler = d.q("SELECT id, ad, birim, satis_fiyati fiyat, kdv_orani FROM urun WHERE aktif = 1 ORDER BY ad")
            else:
                cariler = d.q("SELECT id, unvan FROM cari WHERE aktif = 1 AND tur != 'Müşteri' ORDER BY unvan")
                kalemler = d.q("SELECT id, ad, birim, 0 fiyat, kdv_orani FROM malzeme WHERE aktif = 1 ORDER BY ad")
            return {
                "cariler": cariler, "kalemler": kalemler,
                "siparisler": d.q("SELECT id, siparis_no, cari_id, konu FROM siparis WHERE durum != 'İptal' ORDER BY id DESC LIMIT 500"),
                "belge_turleri": M.SATIS_BELGE_TURLERI if tur == "Satış" else M.ALIS_BELGE_TURLERI,
                "tevkifat_turleri": list(M.TEVKIFAT_ORANLARI),
                "gider_turleri": list(M.GIDER_TURLERI),
                "temin_usulleri": M.TEMIN_USULLERI,
                "stopaj_turleri": list(M.STOPAJ_TURLERI),
                "yazabilir": etkin_yetki(b.k, FATURA_SAYFASI[tur]) == "y",
            }

    def _fatura_kaydet(d, tur: str, istek: FaturaIstegi, fatura_id: int | None = None):
        belge_turleri = M.SATIS_BELGE_TURLERI if tur == "Satış" else M.ALIS_BELGE_TURLERI
        if istek.belge_turu not in belge_turleri:
            raise HTTPException(400, "Belge türü geçersiz.")
        if istek.tevkifat not in M.TEVKIFAT_ORANLARI:
            raise HTTPException(400, "KDV tevkifat türü geçersiz.")
        try:
            parsed_tarih = date.fromisoformat(istek.tarih)
        except ValueError:
            raise HTTPException(400, "Belge tarihi YYYY-AA-GG biçiminde olmalıdır.") from None
        if istek.tarih != parsed_tarih.isoformat():
            raise HTTPException(400, "Belge tarihi YYYY-AA-GG biçiminde olmalıdır.")
        if tur == "Alış":
            if istek.gider_turu not in M.GIDER_TURLERI or istek.temin_usulu not in M.TEMIN_USULLERI:
                raise HTTPException(400, "Gider türü veya temin usulü geçersiz.")
            if istek.stopaj_turu not in M.STOPAJ_TURLERI:
                raise HTTPException(400, "Stopaj türü geçersiz.")
            stopaj_ref = M.STOPAJ_TURLERI[istek.stopaj_turu]
            stopaj_orani = d.parametreler(int(istek.tarih[:4])).get(stopaj_ref, 0) if isinstance(stopaj_ref, str) else stopaj_ref
        else:
            stopaj_orani = 0
        cari = d.q1("SELECT * FROM cari WHERE id = ? AND aktif = 1", (istek.cari_id,))
        if not cari:
            raise HTTPException(400, "Cari bulunamadı veya pasif.")
        if tur == "Satış" and cari["tur"] in ("Tedarikçi", "Çiftçi (Müstahsil)"):
            raise HTTPException(400, "Satış belgesi için müşteri türünde cari seçiniz.")
        if tur == "Alış" and cari["tur"] == "Müşteri":
            raise HTTPException(400, "Alış belgesi için tedarikçi veya üretici türünde cari seçiniz.")
        siparis = d.q1("SELECT * FROM siparis WHERE id = ? AND durum != 'İptal'", (istek.siparis_id,)) if istek.siparis_id else None
        if istek.siparis_id and not siparis:
            raise HTTPException(400, "Sipariş bulunamadı veya iptal edilmiş.")
        if siparis and siparis["cari_id"] != istek.cari_id:
            raise HTTPException(400, "Fatura carisi sipariş carisiyle aynı olmalıdır.")
        mevcut = d.q1("SELECT * FROM fatura WHERE id = ?", (fatura_id,)) if fatura_id else None
        if fatura_id and not mevcut:
            raise HTTPException(404, "Fatura bulunamadı.")
        if mevcut and mevcut["iptal"]:
            raise HTTPException(400, "İptal edilmiş belge düzenlenemez.")
        if mevcut and d.deger("SELECT COUNT(*) FROM kasa_banka WHERE fatura_id = ?", (fatura_id,)):
            raise HTTPException(400, "Belgeye bağlı tahsilat/ödeme kaydı var. Önce o kayıtları siliniz.")
        no = istek.belge_no.strip() or None
        if no:
            tekrar_sql = ("SELECT id FROM fatura WHERE tur = ? AND belge_no = ? AND iptal = 0 AND id != ? "
                          "AND substr(tarih, 1, 4) = ?") if tur == "Satış" else (
                          "SELECT id FROM fatura WHERE tur = ? AND belge_no = ? AND iptal = 0 AND id != ? AND cari_id = ?")
            tekrar_parametreleri = ((tur, no, fatura_id or 0, istek.tarih[:4]) if tur == "Satış"
                                    else (tur, no, fatura_id or 0, istek.cari_id))
            if d.q1(tekrar_sql, tekrar_parametreleri):
                raise HTTPException(400, "Bu belge numarası bu cari/yıl için zaten kayıtlı.")

        p = d.parametreler(int(istek.tarih[:4]))
        kalemler = []
        for i, giris in enumerate(istek.kalemler, 1):
            kalem = giris.model_dump()
            kalem["aciklama"] = kalem["aciklama"].strip() or None
            if tur == "Satış":
                if kalem["malzeme_id"] is not None:
                    raise HTTPException(400, f"{i}. satış kaleminde stok malzemesi seçilemez.")
                if kalem["urun_id"] and not d.q1("SELECT id FROM urun WHERE id = ? AND aktif = 1", (kalem["urun_id"],)):
                    raise HTTPException(400, f"{i}. kalemde ürün bulunamadı veya pasif.")
                kalem["malzeme_id"] = None
            else:
                if kalem["urun_id"] is not None:
                    raise HTTPException(400, f"{i}. alış kaleminde ürün seçilemez.")
                if kalem["malzeme_id"] and not d.q1("SELECT id FROM malzeme WHERE id = ? AND aktif = 1",
                                                      (kalem["malzeme_id"],)):
                    raise HTTPException(400, f"{i}. kalemde malzeme bulunamadı veya pasif.")
                kalem["urun_id"] = None
            kalem["iskonto"] = (yuvarla(kalem["iskonto"]) if kalem["iskonto"] is not None else
                                yuvarla(kalem["miktar"] * kalem["birim_fiyat"] * kalem["iskonto_orani"]))
            kalem["tutar"] = kalem_tutari(kalem)[2]
            kalem["kdv"] = yuvarla(kalem["tutar"] * kalem["kdv_orani"])
            kalemler.append(kalem)
        hatalar = kalem_hatalari(kalemler)
        if hatalar:
            raise HTTPException(400, "\n".join(hatalar))
        toplam = belge_toplami(kalemler, M.TEVKIFAT_ORANLARI[istek.tevkifat], stopaj_orani)
        if istek.kontrol_toplam is not None and abs(istek.kontrol_toplam - toplam.genel_toplam) > 0.01:
            raise HTTPException(400, f"Hesaplanan genel toplam ({para(toplam.genel_toplam)} TL) kontrol tutarından "
                                      f"({para(istek.kontrol_toplam)} TL) farklı.")
        kurum = d.kurum()
        uyarilar = []
        if tur == "Alış" and istek.temin_usulu == "Doğrudan Temin":
            limit = p["dogrudan_temin_buyuksehir" if kurum.get("buyuksehir") else "dogrudan_temin_diger"]
            if toplam.matrah > limit:
                raise HTTPException(400, f"Matrah doğrudan temin limitini ({para(limit)} TL) aşıyor; başka temin usulü seçiniz.")
            uyarilar.append("Doğrudan temin dosyasında onay belgesi, piyasa fiyat araştırma tutanağı ve yasaklılık teyidi bulunmalıdır.")
        if tur == "Satış":
            if cari.get("kamu_kurumu") and istek.tevkifat == "Yok":
                uyarilar.append("Kamu kurumlarına yapılan bazı teslimlerde KDV tevkifatı uygulanır; işin niteliğini kontrol ediniz.")
            for kalem in kalemler:
                urun = d.q1("SELECT ad, satis_fiyati FROM urun WHERE id = ?", (kalem["urun_id"],)) if kalem["urun_id"] else None
                net_birim = yuvarla(kalem["tutar"] / kalem["miktar"], 4) if kalem["miktar"] else 0
                if urun and (urun["satis_fiyati"] or 0) > 0 and net_birim + 0.005 < urun["satis_fiyati"]:
                    uyarilar.append(f"'{urun['ad']}' iskonto sonrası fiyatı tespit edilen satış fiyatının altında.")
            if istek.belge_turu == "Diğer":
                uyarilar.append("Satışlar fatura veya nihai tüketiciye ÖKC fişiyle belgelendirilmelidir.")
        else:
            if istek.belge_turu.startswith("Müstahsil"):
                if cari["tur"] != "Çiftçi (Müstahsil)":
                    uyarilar.append("Müstahsil makbuzu yalnızca vergiden muaf çiftçilerden yapılan alımlarda düzenlenir.")
                if toplam.kdv:
                    uyarilar.append("Müstahsil makbuzunda KDV hesaplanmamalıdır.")
                if not stopaj_orani:
                    raise HTTPException(400, "Müstahsil makbuzunda gelir vergisi stopaj türü seçilmelidir.")
            elif istek.belge_turu.startswith("Perakende"):
                if toplam.kdv:
                    raise HTTPException(400, "Perakende satış fişindeki KDV indirim konusu yapılamaz; kalem KDV oranını sıfır giriniz.")
                uyarilar.append("Perakende satış fişi yalnızca fatura düzenleme sınırının altındaki küçük alımlarda kabul edilebilir.")
            elif istek.belge_turu == "Diğer":
                uyarilar.append("Alım belgelerinin VUK md.228-238'de sayılan belgelerden olduğunu doğrulayınız.")
            if M.GIDER_TURLERI[istek.gider_turu][1] and any(not kalem["malzeme_id"] for kalem in kalemler):
                uyarilar.append("Stoğa alınacak gider türünde stok kartı seçilmeyen kalemler stoğa eklenmez.")
        avans = 0.0
        if tur == "Satış" and istek.avans_mahsup:
            if not siparis:
                raise HTTPException(400, "Sipariş avansı mahsubu için sipariş seçilmelidir.")
            alinan = d.deger("SELECT SUM(tutar) FROM kasa_banka WHERE siparis_id = ? AND tur = 'Peşinat/Avans Tahsilatı'",
                             (siparis["id"],), 0.0) or 0
            onceki = d.deger("SELECT SUM(avans_mahsup) FROM fatura WHERE siparis_id = ? AND iptal = 0 AND id != ?",
                             (siparis["id"], fatura_id or 0), 0.0) or 0
            if istek.avans_mahsup > yuvarla(alinan - onceki) + 0.005:
                raise HTTPException(400, "Mahsup tutarı sipariş için tahsil edilmiş ve kullanılmamış avansı aşıyor.")
            if istek.avans_mahsup > toplam.net_tutar + 0.005:
                raise HTTPException(400, "Avans mahsubu faturanın net tutarını aşamaz.")
            avans = istek.avans_mahsup
        if tur == "Alış" and istek.avans_mahsup:
            raise HTTPException(400, "Avans mahsubu yalnızca satış faturalarında kullanılabilir.")

        if no is None:
            no = d.sonraki_no("satis" if tur == "Satış" else "alis", int(istek.tarih[:4]),
                              "SF" if tur == "Satış" else "AF")
        veri = {
            "tur": tur, "belge_turu": istek.belge_turu, "belge_no": no, "tarih": istek.tarih,
            "cari_id": istek.cari_id, "siparis_id": istek.siparis_id,
            "aciklama": istek.aciklama.strip() or None, "iskonto": toplam.iskonto, "matrah": toplam.matrah,
            "kdv": toplam.kdv, "tevkifat": istek.tevkifat, "tevkif_kdv": toplam.tevkif_kdv,
            "stopaj_turu": istek.stopaj_turu if tur == "Alış" else "Yok",
            "stopaj_orani": stopaj_orani, "stopaj": toplam.stopaj,
            "genel_toplam": toplam.genel_toplam, "net_tutar": toplam.net_tutar,
            "avans_mahsup": avans, "gider_turu": istek.gider_turu if tur == "Alış" else None,
            "temin_usulu": istek.temin_usulu if tur == "Alış" else None,
        }
        with d.islem():
            if fatura_id:
                if istek.surum is None:
                    raise HTTPException(400, "Fatura sürümü gereklidir; kaydı yeniden açıp tekrar deneyiniz.")
                d.cakisma_denetle("fatura", fatura_id, istek.surum)
                d.guncelle("fatura", fatura_id, veri)
            else:
                fatura_id = d.ekle("fatura", veri)
            d.ex("DELETE FROM fatura_kalem WHERE fatura_id = ?", (fatura_id,))
            d.ex("DELETE FROM stok_hareket WHERE kaynak = 'Fatura' AND kaynak_id = ?", (fatura_id,))
            for kalem in kalemler:
                kalem["fatura_id"] = fatura_id
                d.ekle("fatura_kalem", kalem, log=False)
                if tur == "Satış" and kalem.get("urun_id"):
                    mamul = d.deger("SELECT mamul_malzeme_id FROM urun WHERE id = ?", (kalem["urun_id"],), None)
                    if mamul:
                        d.ekle("stok_hareket", {
                            "tarih": istek.tarih, "malzeme_id": mamul, "yon": "Çıkış", "miktar": kalem["miktar"],
                            "birim_fiyat": muhasebe.ortalama_maliyet(mamul, istek.tarih), "kaynak": "Fatura",
                            "kaynak_id": fatura_id, "siparis_id": istek.siparis_id, "aciklama": f"Satış {no}",
                        }, log=False)
                elif tur == "Alış" and kalem.get("malzeme_id") and M.GIDER_TURLERI[istek.gider_turu][1]:
                    d.ekle("stok_hareket", {
                        "tarih": istek.tarih, "malzeme_id": kalem["malzeme_id"], "yon": "Giriş",
                        "miktar": kalem["miktar"], "birim_fiyat": yuvarla(kalem["tutar"] / kalem["miktar"], 4),
                        "kaynak": "Fatura", "kaynak_id": fatura_id, "siparis_id": istek.siparis_id,
                        "aciklama": f"Alış {no}",
                    }, log=False)
            muhasebe.fatura_kaydi(fatura_id)
        return {"id": fatura_id, "belge_no": no, "matrah": toplam.matrah, "kdv": toplam.kdv,
                "genel_toplam": toplam.genel_toplam, "net_tutar": yuvarla(toplam.net_tutar - avans),
                "surum": d.son_islem_no(), "uyarilar": uyarilar}

    @app.get("/api/faturalar/{fatura_id:int}")
    def fatura_detayi(fatura_id: int, b: Baglam = Depends(kullanici)):
        with b as d:
            f = d.q1("""SELECT f.*, c.unvan, s.siparis_no,
                                f.net_tutar - COALESCE(f.avans_mahsup, 0) -
                                COALESCE((SELECT SUM(tutar) FROM kasa_banka k WHERE k.fatura_id = f.id), 0) kalan
                         FROM fatura f LEFT JOIN cari c ON c.id = f.cari_id
                         LEFT JOIN siparis s ON s.id = f.siparis_id WHERE f.id = ?""", (fatura_id,))
            if not f:
                raise HTTPException(404, "Fatura bulunamadı.")
            gerek(b.k, FATURA_SAYFASI[f["tur"]])
            f["kalemler"] = d.q("SELECT * FROM fatura_kalem WHERE fatura_id = ? ORDER BY id", (fatura_id,))
            f["odemeler"] = d.q("SELECT id, tarih, hesap, tutar, belge_no, aciklama FROM kasa_banka WHERE fatura_id = ? "
                                "ORDER BY tarih, id", (fatura_id,))
            f["surum"] = d.son_islem_no()
            f["duzenlenebilir"] = (not f["iptal"] and not f["odemeler"]
                                   and etkin_yetki(b.k, FATURA_SAYFASI[f["tur"]]) == "y")
            f["iptal_edilebilir"] = (not f["iptal"] and not f["odemeler"]
                                     and etkin_yetki(b.k, FATURA_SAYFASI[f["tur"]]) == "y")
            f["odeme_yapilabilir"] = (not f["iptal"] and f["kalan"] > 0.009
                                      and etkin_yetki(b.k, FATURA_SAYFASI[f["tur"]]) == "y"
                                      and etkin_yetki(b.k, MOBIL_MODULLER["kasa"]) == "y")
            f["dogrudan_temin_belgesi"] = (f["tur"] == "Alış" and f["temin_usulu"] == "Doğrudan Temin")
            return f

    @app.get("/api/faturalar/{fatura_id:int}/dogrudan-temin")
    def dogrudan_temin_onbilgisi(fatura_id: int, b: Baglam = Depends(kullanici)):
        with b as d:
            f = d.q1("""SELECT f.*, c.unvan FROM fatura f LEFT JOIN cari c ON c.id = f.cari_id
                        WHERE f.id = ?""", (fatura_id,))
            if not f:
                raise HTTPException(404, "Alış belgesi bulunamadı.")
            gerek(b.k, FATURA_SAYFASI[f["tur"]])
            if f["tur"] != "Alış" or f["temin_usulu"] != "Doğrudan Temin" or f["iptal"]:
                raise HTTPException(400, "Yalnız aktif doğrudan temin alış belgeleri için paket hazırlanabilir.")
            kalemler = d.q("""SELECT k.aciklama, k.miktar, k.birim, m.ad FROM fatura_kalem k
                              LEFT JOIN malzeme m ON m.id = k.malzeme_id WHERE k.fatura_id = ? ORDER BY k.id""",
                           (fatura_id,))
            return {
                "fatura_id": fatura_id, "konu": f["aciklama"] or "",
                "tarih": f["tarih"], "sayi": f["belge_no"] or "", "gider_turu": f["gider_turu"],
                "kalemler": [{"ad": " - ".join(x for x in (r["ad"], r["aciklama"]) if x) or "Mal / hizmet",
                              "miktar": r["miktar"] or 1, "birim": r["birim"] or ""} for r in kalemler],
                "firmalar": [{"ad": f["unvan"] or "", "tutar": f["matrah"] or 0}],
                "yaklasik_maliyet": f["matrah"] or 0, "teslim_yeri": "İşletme atölyesine",
                "gider_turleri": list(M.GIDER_TURLERI),
            }

    @app.post("/api/belgeler/dogrudan-temin")
    def dogrudan_temin_belgeleri(istek: DogrudanTeminIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, FATURA_SAYFASI["Alış"], yaz=True)
            try:
                tarih = date.fromisoformat(istek.tarih)
            except ValueError:
                raise HTTPException(400, "Belge tarihi YYYY-AA-GG biçiminde olmalıdır.") from None
            if tarih.isoformat() != istek.tarih:
                raise HTTPException(400, "Belge tarihi YYYY-AA-GG biçiminde olmalıdır.")
            if istek.gider_turu not in M.GIDER_TURLERI:
                raise HTTPException(400, "Gider türü geçersiz.")
            if istek.fatura_id:
                f = d.q1("SELECT tur, temin_usulu, iptal FROM fatura WHERE id = ?", (istek.fatura_id,))
                if not f or f["tur"] != "Alış" or f["temin_usulu"] != "Doğrudan Temin" or f["iptal"]:
                    raise HTTPException(400, "Seçilen alış belgesi aktif bir doğrudan temin kaydı değil.")
            p = d.parametreler(tarih.year)
            limit = p["dogrudan_temin_buyuksehir" if d.kurum().get("buyuksehir") else "dogrudan_temin_diger"]
            firmalar = [x.model_dump() | {"ad": x.ad.strip()} for x in istek.firmalar]
            if any(not x["ad"] for x in firmalar):
                raise HTTPException(400, "Firma adları boş bırakılamaz.")
            en_uygun = min((x["tutar"] for x in firmalar), default=istek.yaklasik_maliyet)
            uyarilar = []
            if len(firmalar) < 3:
                uyarilar.append("Piyasa araştırmasında en az üç firmadan teklif alınması önerilir.")
            if max(en_uygun, istek.yaklasik_maliyet) > limit:
                uyarilar.append(f"Yaklaşık maliyet doğrudan temin limitini ({para(limit)} TL) aşıyor; ihale usulü gerekir.")
            veri = {
                "konu": istek.konu.strip(), "tarih": istek.tarih, "sayi": istek.sayi.strip(),
                "gider_turu": istek.gider_turu,
                "kalemler": [x.model_dump() for x in istek.kalemler],
                "firmalar": firmalar, "gorevliler": [x.strip() for x in istek.gorevliler if x.strip()],
                "yaklasik_maliyet": istek.yaklasik_maliyet, "teslim_yeri": istek.teslim_yeri.strip(),
            }
            with tempfile.TemporaryDirectory(prefix="dose-dogrudan-temin-") as dizin:
                yol = belgeler.dogrudan_temin_dosyasi(
                    Path(dizin) / f"Dogrudan_Temin_{istek.tarih}.pdf", veri)
                icerik = yol.read_bytes()
                dosya_adi = yol.name
            d.log("Doğrudan temin belge paketi oluşturma", "fatura", istek.fatura_id,
                  detay=f"{istek.tarih} / {istek.konu}")
            return {"dosya_adi": dosya_adi, "icerik": base64.b64encode(icerik).decode("ascii"),
                    "uyarilar": uyarilar}

    @app.post("/api/faturalar")
    def fatura_ekle(istek: FaturaIstegi, tur: str = Query("Satış"), b: Baglam = Depends(kullanici)):
        if tur not in FATURA_SAYFASI:
            raise HTTPException(400, "Fatura türü 'Satış' veya 'Alış' olmalıdır.")
        with b as d:
            gerek(b.k, FATURA_SAYFASI[tur], yaz=True)
            return _fatura_kaydet(d, tur, istek)

    @app.put("/api/faturalar/{fatura_id:int}")
    def fatura_guncelle(fatura_id: int, istek: FaturaIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            f = d.q1("SELECT tur FROM fatura WHERE id = ?", (fatura_id,))
            if not f:
                raise HTTPException(404, "Fatura bulunamadı.")
            gerek(b.k, FATURA_SAYFASI[f["tur"]], yaz=True)
            return _fatura_kaydet(d, f["tur"], istek, fatura_id)

    @app.delete("/api/faturalar/{fatura_id:int}")
    def fatura_iptal(fatura_id: int, surum: int = Query(..., ge=0), b: Baglam = Depends(kullanici)):
        with b as d:
            f = d.q1("SELECT * FROM fatura WHERE id = ?", (fatura_id,))
            if not f:
                raise HTTPException(404, "Fatura bulunamadı.")
            gerek(b.k, FATURA_SAYFASI[f["tur"]], yaz=True)
            if f["iptal"]:
                raise HTTPException(400, "Fatura zaten iptal edilmiş.")
            if d.deger("SELECT COUNT(*) FROM kasa_banka WHERE fatura_id = ?", (fatura_id,)):
                raise HTTPException(400, "Belgeye bağlı tahsilat/ödeme kaydı var. Önce o kayıtları siliniz.")
            d.cakisma_denetle("fatura", fatura_id, surum)
            with d.islem():
                d.guncelle("fatura", fatura_id, {"iptal": 1})
                d.ex("DELETE FROM stok_hareket WHERE kaynak = 'Fatura' AND kaynak_id = ?", (fatura_id,))
                muhasebe.fatura_kaydi(fatura_id)
            return {"tamam": True}

    @app.post("/api/faturalar/{fatura_id}/odeme")
    def fatura_odeme(fatura_id: int, istek: FaturaOdemeIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            f = d.q1("SELECT * FROM fatura WHERE id = ?", (fatura_id,))
            if not f:
                raise HTTPException(404, "Fatura bulunamadı.")
            gerek(b.k, FATURA_SAYFASI[f["tur"]], yaz=True)
            gerek(b.k, MOBIL_MODULLER["kasa"], yaz=True)
            if f["iptal"]:
                raise HTTPException(400, "İptal edilmiş faturaya ödeme/tahsilat kaydedilemez.")
            try:
                tarih = date.fromisoformat(istek.tarih)
            except ValueError:
                raise HTTPException(400, "Ödeme tarihi YYYY-AA-GG biçiminde olmalıdır.") from None
            if tarih.isoformat() != istek.tarih:
                raise HTTPException(400, "Ödeme tarihi YYYY-AA-GG biçiminde olmalıdır.")
            kalan = muhasebe.fatura_kalan(fatura_id)
            if istek.tutar > kalan + 0.005:
                raise HTTPException(400, f"Ödeme/tahsilat açık bakiyeyi ({para(kalan)} TL) aşamaz.")
            with d.islem():
                hareket_id = d.ekle("kasa_banka", {
                    "tarih": istek.tarih, "hesap": istek.hesap,
                    "yon": "Giriş" if f["tur"] == "Satış" else "Çıkış",
                    "tur": "Tahsilat" if f["tur"] == "Satış" else "Ödeme",
                    "tutar": istek.tutar,
                    "hasilat_tutari": (yuvarla(istek.tutar * f["matrah"] / f["net_tutar"])
                                       if f["tur"] == "Satış" and f["net_tutar"] else 0),
                    "cari_id": f["cari_id"], "fatura_id": fatura_id,
                    "siparis_id": f["siparis_id"], "belge_no": istek.belge_no.strip() or None,
                    "aciklama": istek.aciklama.strip() or f"{f['belge_no'] or ''} nolu belge",
                })
                muhasebe.kasa_kaydi(hareket_id)
            return {"id": hareket_id, "kalan": yuvarla(kalan - istek.tutar)}

    @app.get("/api/faturalar/disa-aktar")
    def faturalari_disa_aktar(tur: str = Query("Satış"), yil: int = Query(default_factory=lambda: date.today().year),
                              ay: int = Query(0, ge=0, le=12), b: Baglam = Depends(kullanici)):
        if tur not in FATURA_SAYFASI:
            raise HTTPException(400, "Fatura türü 'Satış' veya 'Alış' olmalıdır.")
        with b as d:
            gerek(b.k, FATURA_SAYFASI[tur])
            donem = f"{yil}" + (f"-{ay:02d}" if ay else "")
            rows = d.q("""SELECT f.tarih, f.belge_turu, f.belge_no, c.unvan, s.siparis_no, f.iskonto, f.matrah, f.kdv,
                                 f.tevkif_kdv, f.stopaj, f.genel_toplam, f.avans_mahsup, f.net_tutar, f.iptal
                          FROM fatura f LEFT JOIN cari c ON c.id = f.cari_id LEFT JOIN siparis s ON s.id = f.siparis_id
                          WHERE f.tur = ? AND f.tarih LIKE ? ORDER BY f.tarih DESC, f.id DESC LIMIT 2000""",
                         (tur, donem + "%"))
            with tempfile.TemporaryDirectory(prefix="dose-fatura-") as dizin:
                yol = excel.disa_aktar(
                    Path(dizin) / f"{'Satis' if tur == 'Satış' else 'Alis'}_{donem}.xlsx",
                    [(tur + " faturaları", ["Tarih", "Belge Türü", "Belge No", "Cari", "Sipariş", "İskonto", "Matrah",
                                            "KDV", "Tevkif KDV", "Stopaj", "Genel Toplam", "Avans Mahsubu", "Net Tutar", "İptal"],
                      [[r["tarih"], r["belge_turu"], r["belge_no"] or "", r["unvan"] or "", r["siparis_no"] or "",
                        r["iskonto"] or 0, r["matrah"] or 0, r["kdv"] or 0, r["tevkif_kdv"] or 0, r["stopaj"] or 0,
                        r["genel_toplam"] or 0, r["avans_mahsup"] or 0, r["net_tutar"] or 0,
                        "Evet" if r["iptal"] else "Hayır"] for r in rows])])
                icerik = yol.read_bytes()
            d.log("Fatura dışa aktarma", "fatura", detay=f"{tur} {donem}")
            return {"dosya_adi": yol.name, "icerik": base64.b64encode(icerik).decode("ascii")}

    # ------------------------------------------------------------ resmi yazılar ve toplu belgeler
    @app.get("/api/belgeler")
    def belgeler_ozeti(b: Baglam = Depends(kullanici)):
        with b as d:
            sayfa = MOBIL_MODULLER["belgeler"]
            gerek(b.k, sayfa)
            kurum = d.kurum()
            return {
                "yazilar": d.q("SELECT id, tarih, sayi, konu, muhatap FROM resmi_yazi ORDER BY tarih DESC, id DESC LIMIT 500"),
                "ogrenciler": d.q(
                    """SELECT o.id, o.okul_no, o.ad_soyad, o.sinif, o.veli_adi, o.veli_telefon, o.iban,
                              o.veli_muvafakat, o.muvafakat_tarihi, b.ad bolum
                       FROM ogrenci o LEFT JOIN bolum b ON b.id = o.bolum_id
                       WHERE o.aktif = 1 ORDER BY o.sinif, o.ad_soyad"""),
                "personel_sayisi": d.deger("SELECT COUNT(*) FROM personel WHERE aktif = 1", (), 0),
                "sablonlar": belge_sablonlari.SABLONLAR,
                "kurum": {"evrak_kodu": kurum.get("evrak_kodu"),
                          "gerceklestirme_gorevlisi": kurum.get("gerceklestirme_gorevlisi"),
                          "harcama_yetkilisi": kurum.get("harcama_yetkilisi")},
                "yazabilir": etkin_yetki(b.k, sayfa) == "y",
            }

    @app.post("/api/belgeler/yazilar")
    def belge_yazi_ekle(istek: ResmiYaziIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["belgeler"], yaz=True)
            try:
                date.fromisoformat(istek.tarih)
            except ValueError:
                raise HTTPException(400, "Tarih YYYY-AA-GG biçiminde olmalıdır.") from None
            veri = istek.model_dump()
            veri = {alan: (deger.strip() if isinstance(deger, str) else deger) for alan, deger in veri.items()}
            if not veri["konu"] or not veri["metin"]:
                raise HTTPException(400, "Konu ve metin zorunludur.")
            with d.islem():
                yazi_id = d.ekle("resmi_yazi", veri)
            return {"id": yazi_id}

    @app.put("/api/belgeler/yazilar/{yazi_id}")
    def belge_yazi_guncelle(yazi_id: int, istek: ResmiYaziIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["belgeler"], yaz=True)
            if not d.q1("SELECT id FROM resmi_yazi WHERE id = ?", (yazi_id,)):
                raise HTTPException(404, "Resmi yazı bulunamadı.")
            try:
                date.fromisoformat(istek.tarih)
            except ValueError:
                raise HTTPException(400, "Tarih YYYY-AA-GG biçiminde olmalıdır.") from None
            veri = istek.model_dump()
            veri = {alan: (deger.strip() if isinstance(deger, str) else deger) for alan, deger in veri.items()}
            if not veri["konu"] or not veri["metin"]:
                raise HTTPException(400, "Konu ve metin zorunludur.")
            d.guncelle("resmi_yazi", yazi_id, veri)
            return {"tamam": True}

    @app.get("/api/belgeler/yazilar/{yazi_id}")
    def belge_yazi_detayi(yazi_id: int, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["belgeler"])
            yazi = d.q1("SELECT * FROM resmi_yazi WHERE id = ?", (yazi_id,))
            if not yazi:
                raise HTTPException(404, "Resmi yazı bulunamadı.")
            return yazi

    @app.delete("/api/belgeler/yazilar/{yazi_id}")
    def belge_yazi_sil(yazi_id: int, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["belgeler"], yaz=True)
            if not d.q1("SELECT id FROM resmi_yazi WHERE id = ?", (yazi_id,)):
                raise HTTPException(404, "Resmi yazı bulunamadı.")
            d.sil("resmi_yazi", yazi_id)
            return {"tamam": True}

    @app.get("/api/belgeler/yazilar/{yazi_id}/pdf")
    def belge_yazi_pdf(yazi_id: int, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["belgeler"])
            yazi = d.q1("SELECT * FROM resmi_yazi WHERE id = ?", (yazi_id,))
            if not yazi:
                raise HTTPException(404, "Resmi yazı bulunamadı.")
            from pathlib import Path
            import tempfile
            with tempfile.TemporaryDirectory(prefix="dose-resmi-yazi-") as dizin:
                yol = belgeler.resmi_yazi(Path(dizin) / f"Yazi_{yazi_id}.pdf", yazi)
                icerik = yol.read_bytes()
            return {"dosya_adi": f"Yazi_{yazi_id}.pdf",
                    "icerik": base64.b64encode(icerik).decode("ascii")}

    @app.post("/api/belgeler/muvafakatname")
    def belge_muvafakatname(istek: MuvafakatIstegi, b: Baglam = Depends(kullanici)):
        if len(istek.ogrenci_idler) != len(set(istek.ogrenci_idler)):
            raise HTTPException(400, "Öğrenci listesinde tekrar eden kayıt bulunuyor.")
        with b as d:
            gerek(b.k, MOBIL_MODULLER["belgeler"])
            mevcut = {r["id"] for r in d.q(
                f"SELECT id FROM ogrenci WHERE aktif = 1 AND id IN ({', '.join('?' for _ in istek.ogrenci_idler)})",
                istek.ogrenci_idler)}
            if mevcut != set(istek.ogrenci_idler):
                raise HTTPException(404, "Seçilen öğrencilerden biri bulunamadı veya aktif değil.")
            from pathlib import Path
            import tempfile
            with tempfile.TemporaryDirectory(prefix="dose-muvafakat-") as dizin:
                yol = belgeler.veli_muvafakatnamesi(
                    Path(dizin) / "Veli_Muvafakatnamesi.pdf", istek.ogrenci_idler)
                icerik = yol.read_bytes()
            d.log("Veli muvafakatnamesi oluşturma", "ogrenci", detay=f"Öğrenci sayısı: {len(mevcut)}")
            return {"dosya_adi": "Veli_Muvafakatnamesi.pdf",
                    "icerik": base64.b64encode(icerik).decode("ascii")}

    @app.get("/api/belgeler/ogrenci-listesi")
    def belge_ogrenci_listesi(b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["belgeler"])
            rows = d.q(
                """SELECT o.okul_no, o.ad_soyad, o.sinif, b.ad bolum, o.veli_adi, o.veli_muvafakat
                   FROM ogrenci o LEFT JOIN bolum b ON b.id = o.bolum_id
                   WHERE o.aktif = 1 ORDER BY o.sinif, o.ad_soyad""")
            from pathlib import Path
            import tempfile
            with tempfile.TemporaryDirectory(prefix="dose-ogrenci-listesi-") as dizin:
                yol = belgeler.genel_liste(
                    Path(dizin) / "Ogrenci_Listesi.pdf", "DÖNER SERMAYE ÇALIŞMALARINA KATILAN ÖĞRENCİ LİSTESİ",
                    ["Okul no", "Adı soyadı", "Sınıf", "Bölüm", "Veli", "Muvafakat"],
                    [[r["okul_no"] or "", r["ad_soyad"], r["sinif"] or "", r["bolum"] or "",
                      r["veli_adi"] or "", "Var" if r["veli_muvafakat"] else "YOK"] for r in rows],
                    yatay=False)
                icerik = yol.read_bytes()
            return {"dosya_adi": "Ogrenci_Listesi.pdf",
                    "icerik": base64.b64encode(icerik).decode("ascii")}

    @app.get("/api/belgeler/personel-listesi")
    def belge_personel_listesi(b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["belgeler"])
            rows = d.q(
                """SELECT p.ad_soyad, p.kadro_unvani, p.dose_gorevi, p.hizmet_sinifi, b.ad bolum, p.unvan_grubu
                   FROM personel p LEFT JOIN bolum b ON b.id = p.bolum_id
                   WHERE p.aktif = 1 ORDER BY p.dose_gorevi, p.ad_soyad""")
            from pathlib import Path
            import tempfile
            with tempfile.TemporaryDirectory(prefix="dose-personel-listesi-") as dizin:
                yol = belgeler.genel_liste(
                    Path(dizin) / "Personel_Listesi.pdf", "DÖNER SERMAYE İŞLETMESİ PERSONEL LİSTESİ",
                    ["Adı soyadı", "Kadro unvanı", "DÖSE görevi", "Hizmet sınıfı", "Bölüm", "Unvan grubu"],
                    [[r["ad_soyad"], r["kadro_unvani"] or "", r["dose_gorevi"] or "", r["hizmet_sinifi"] or "",
                      r["bolum"] or "", r["unvan_grubu"] or ""] for r in rows])
                icerik = yol.read_bytes()
            return {"dosya_adi": "Personel_Listesi.pdf",
                    "icerik": base64.b64encode(icerik).decode("ascii")}

    # ------------------------------------------------------------ işlem kaydı
    def _islem_kaydi_filtrele(d, k, ara, kullanici_adi, baslangic, bitis, istemci, sinir):
        gerek(k, MOBIL_MODULLER["islem"])
        for etiket, deger in (("Başlangıç", baslangic), ("Bitiş", bitis)):
            if deger:
                try:
                    if date.fromisoformat(deger).isoformat() != deger:
                        raise ValueError
                except ValueError:
                    raise HTTPException(400, f"{etiket} tarihi YYYY-AA-GG biçiminde olmalıdır.") from None
        if baslangic and bitis and baslangic > bitis:
            raise HTTPException(400, "Başlangıç tarihi bitiş tarihinden sonra olamaz.")
        return izleme.kayitlar(d, ara, kullanici_adi or None, baslangic or None, bitis or None,
                               istemci or None, sinir=sinir)

    @app.get("/api/islem-kaydi")
    def islem_kaydi(ara: str = "", kullanici_adi: str = "", istemci: str = "", baslangic: str = "", bitis: str = "",
                    sinir: int = Query(200, ge=1, le=1000), b: Baglam = Depends(kullanici)):
        with b as d:
            kayitlar = _islem_kaydi_filtrele(d, b.k, ara, kullanici_adi, baslangic, bitis, istemci, sinir)
            alanlar = ("id", "zaman", "kullanici", "kim", "rol", "islem", "tablo", "kayit_turu", "kayit_id", "ozet",
                       "istemci", "bilgisayar")
            return {"kayitlar": [{a: r.get(a) for a in alanlar} for r in kayitlar], "kullanicilar": izleme.kullanicilar(d)}

    @app.get("/api/islem-kaydi/excel")
    def islem_kaydi_excel(ara: str = "", kullanici_adi: str = "", istemci: str = "",
                          baslangic: str = "", bitis: str = "", b: Baglam = Depends(kullanici)):
        with b as d:
            kayitlar = _islem_kaydi_filtrele(d, b.k, ara, kullanici_adi, baslangic, bitis, istemci, 2000)
            with tempfile.TemporaryDirectory(prefix="dose-islem-kaydi-") as dizin:
                yol = excel.disa_aktar(
                    Path(dizin) / "Islem_Kaydi.xlsx",
                    [("İşlem Kaydı",
                      ["Zaman", "Kullanıcı", "Ad soyad", "Rol", "İşlem", "Kayıt türü", "Kayıt no",
                       "Yapılan değişiklik", "Kaynak", "Bilgisayar / cihaz"],
                      [[r.get("zaman"), r.get("kullanici"), r.get("kim"), r.get("rol"), r.get("islem"),
                        r.get("kayit_turu"), r.get("kayit_id"), r.get("ozet"), r.get("istemci"),
                        r.get("bilgisayar")] for r in kayitlar])],
                    "İşlem Kaydı",
                )
                icerik = yol.read_bytes()
            return {"dosya_adi": "Islem_Kaydi.xlsx", "icerik": base64.b64encode(icerik).decode("ascii")}

    @app.get("/api/islem-kaydi/{kid}")
    def islem_ayrinti(kid: int, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["islem"])
            r = d.q1("SELECT * FROM islem_log WHERE id = ?", (kid,))
            if not r:
                raise HTTPException(404, "Kayıt bulunamadı.")
            r["kayit_turu"] = izleme.tablo_adi(r.get("tablo"))
            r["degisiklikler"] = [{"alan": a, "eski": e, "yeni": y} for a, e, y in izleme.degisiklikler(r)]
            r.pop("eski", None)
            r.pop("yeni", None)
            return r

    if web_adresi:
        import flet_web.fastapi as flet_fastapi

        from mobil.uygulama import calistir
        app.mount("/", flet_fastapi.app(calistir(web_adresi), app_name="DÖSE Mobil", app_short_name="DÖSE",
                                        app_description="DÖSE Yönetim mobil erişim", no_cdn=True))
    return app
