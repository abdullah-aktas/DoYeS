"""DÖSE Yönetim mobil API'si (FastAPI).

Telefon ve web uygulaması veritabanına doğrudan bağlanmaz; bütün işlemler okulun sunucusunda çalışan bu servis üzerinden,
masaüstü programla aynı mevzuat denetimleri, rol yetkileri, bölüm kısıtları ve onay akışıyla yapılır. Her işlem işlem
kaydına kullanıcı, rol, cihaz ve "Mobil" kaynak bilgisiyle yazılır.
"""
from __future__ import annotations

import calendar
import base64
import hashlib
import json
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from dose import SURUM
from dose import ag, db as dbm
from dose import denetim_formu
from dose import gosterge, izleme, kilavuz, lisans, muhasebe, onay, uyum, yetki
from dose import mevzuat as M
from dose.db import KayitCakismasi
from dose.hesap import (GUN_TURU_ADLARI, ay_azami_fazla_calisma, gun_azami_saat, gun_turu, siparis_kaydi_tahsisi,
                        yuvarla)
from dose.islemler import IslemHatasi, fc_hesapla, siparis_taslagi_kaydet
from dose.lisans import SaltOkunurHata, kurum_kodu_normalize

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
    "stok": "Stok Durumu ve Hareketleri",
    "kasa": "Kasa / Banka",
    "satis": "Satış Faturaları",
    "alis": "Alış / Gider Belgeleri",
    "islem": "Yedekleme / İşlem Kaydı",
    "denetim": "Rehberlik ve Denetim Formu",
}
FATURA_SAYFASI = {"Satış": "Satış Faturaları", "Alış": "Alış / Gider Belgeleri"}
GUNLER = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

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


class SifreIstegi(BaseModel):
    eski: str
    yeni: str


class KararIstegi(BaseModel):
    onay: bool
    aciklama: str = ""


class AciklamaIstegi(BaseModel):
    aciklama: str = ""


class SiparisKalemi(BaseModel):
    urun_id: int | None = None
    aciklama: str | None = None
    miktar: float = 1
    birim: str | None = None
    birim_fiyat: float | None = None
    iskonto_orani: float = 0


class SiparisIstegi(BaseModel):
    tarih: str | None = None
    cari_id: int | None = None
    bolum_id: int | None = None
    konu: str = ""
    ucret_esasi: str | None = None
    teslim_tarihi: str | None = None
    aciklama: str = ""
    kalemler: list[SiparisKalemi] = Field(default_factory=list)


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
            return s

    @app.post("/api/siparisler")
    def siparis_ekle(istek: SiparisIstegi, b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["siparis"], yaz=True)
            veri = istek.model_dump()
            sid, no, uyarilar = siparis_taslagi_kaydet(d, veri, bolum_kisiti(b.k))
            return {"id": sid, "siparis_no": no, "uyarilar": uyarilar}

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

    # ------------------------------------------------------------ listeler
    @app.get("/api/stok")
    def stok(b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["stok"])
            bak = d.q("""SELECT m.id, m.kod, m.ad, m.tur, m.birim, m.kritik_stok,
                                COALESCE(SUM(CASE WHEN h.yon = 'Giriş' THEN h.miktar END), 0) giris,
                                COALESCE(SUM(CASE WHEN h.yon = 'Çıkış' THEN h.miktar END), 0) cikis
                         FROM malzeme m LEFT JOIN stok_hareket h ON h.malzeme_id = m.id
                         WHERE m.aktif = 1 GROUP BY m.id ORDER BY m.ad""")
            for r in bak:
                r["kalan"] = yuvarla(r["giris"] - r["cikis"], 3)
                r["ortalama_maliyet"] = muhasebe.ortalama_maliyet(r["id"])
                r["tutar"] = yuvarla(r["kalan"] * r["ortalama_maliyet"])
                r["kritik"] = bool(r["kritik_stok"] and r["kalan"] <= r["kritik_stok"])
            return {"malzemeler": bak, "toplam": yuvarla(sum(r["tutar"] for r in bak))}

    @app.get("/api/kasa")
    def kasa(yil: int = Query(default_factory=lambda: date.today().year), ay: int = Query(0, ge=0, le=12),
             hesap: str = "", b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["kasa"])
            donem = f"{yil}" + (f"-{ay:02d}" if ay else "")
            sql = """SELECT k.id, k.tarih, k.hesap, k.yon, k.tur, k.tutar, k.hasilat_tutari, k.belge_no, k.aciklama,
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
                    "cikis": yuvarla(sum(h["tutar"] for h in hareketler if h["yon"] == "Çıkış"))}

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
                    "acik_bakiye": yuvarla(sum(s["kalan"] or 0 for s in gecerli))}

    # ------------------------------------------------------------ işlem kaydı
    @app.get("/api/islem-kaydi")
    def islem_kaydi(ara: str = "", kullanici_adi: str = "", istemci: str = "", baslangic: str = "", bitis: str = "",
                    sinir: int = Query(200, ge=1, le=1000), b: Baglam = Depends(kullanici)):
        with b as d:
            gerek(b.k, MOBIL_MODULLER["islem"])
            kayitlar = izleme.kayitlar(d, ara, kullanici_adi or None, baslangic or None, bitis or None, istemci or None,
                                       sinir=sinir)
            alanlar = ("id", "zaman", "kullanici", "kim", "rol", "islem", "tablo", "kayit_turu", "kayit_id", "ozet",
                       "istemci", "bilgisayar")
            return {"kayitlar": [{a: r.get(a) for a in alanlar} for r in kayitlar], "kullanicilar": izleme.kullanicilar(d)}

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
