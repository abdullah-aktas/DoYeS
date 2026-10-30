"""Lisans doğrulama.

Lisans anahtarı satıcının özel anahtarıyla (Ed25519) imzalanmış bir metindir; program yalnız açık anahtarı içerir,
bu nedenle anahtar değiştirilemez ve yenisi üretilemez. Lisans kurum koduna bağlıdır ve veritabanındaki 'ayar'
tablosunda tutulur; sunucu modunda bir kez girilen lisans okulun bütün bilgisayarlarında geçerli olur.

Lisans yoksa DENEME_GUN boyunca tam sürüm çalışır. Deneme veya lisans süresi bitince program salt okunur olur:
kayıtlar görüntülenir, raporlanır ve yedeklenir; yeni kayıt ve değişiklik yapılamaz.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import date, datetime

ACIK_ANAHTAR = "ZyFB-uGBY2d-UQ6ztQ2ILEHG8y0BY6qDqylFR4Y_Alg"
SATICI = "Derik MTAL Döner Sermaye İşletmesi"
# Flet lisans ekranında gösterilir; ör. "0482 000 00 00 • dose@ornek.meb.k12.tr"
SATICI_ILETISIM = ""
ONEK = "DOSE1"
DENEME_GUN = 30
UYARI_GUN = 30
SUREKLI = "Süresiz"


class LisansHatasi(ValueError):
    pass


class SaltOkunurHata(PermissionError):
    pass


@dataclass
class Lisans:
    no: str
    okul: str
    kurum_kodu: str
    verilis: date
    bitis: date | None
    tur: str = "Yıllık"

    def bitis_metni(self) -> str:
        return self.bitis.strftime("%d.%m.%Y") if self.bitis else SUREKLI


@dataclass
class Durum:
    yazilabilir: bool
    ozet: str
    lisans: Lisans | None = None
    kalan_gun: int | None = None
    uyari: bool = False
    deneme: bool = False


def _b64(veri: bytes) -> str:
    return base64.urlsafe_b64encode(veri).decode("ascii").rstrip("=")


def _b64_coz(metin: str) -> bytes:
    return base64.urlsafe_b64decode(metin + "=" * (-len(metin) % 4))


def kurum_kodu_normalize(kod) -> str:
    return "".join(str(kod or "").split())


# ---------------------------------------------------------------- üretim (yalnız satıcı aracında kullanılır)
def imzala(ozel_anahtar, okul: str, kurum_kodu: str, bitis: date | None, no: str, tur: str) -> str:
    yuk = {"no": no, "okul": okul.strip(), "kod": kurum_kodu_normalize(kurum_kodu), "ver": date.today().isoformat(),
           "bit": bitis.isoformat() if bitis else None, "tur": tur}
    ham = json.dumps(yuk, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"{ONEK}.{_b64(ham)}.{_b64(ozel_anahtar.sign(ham))}"


# ---------------------------------------------------------------- doğrulama
def coz(metin: str, acik_anahtar: str | None = None) -> Lisans:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    metin = "".join((metin or "").split())
    parcalar = metin.split(".")
    if len(parcalar) != 3 or parcalar[0] != ONEK:
        raise LisansHatasi("Lisans anahtarı biçimi hatalı. Anahtarı eksiksiz kopyaladığınızdan emin olun.")
    anahtar = acik_anahtar or ACIK_ANAHTAR
    if not anahtar:
        raise LisansHatasi("Bu sürümde lisans doğrulama anahtarı tanımlı değil.")
    try:
        ham, imza = _b64_coz(parcalar[1]), _b64_coz(parcalar[2])
        Ed25519PublicKey.from_public_bytes(_b64_coz(anahtar)).verify(imza, ham)
        yuk = json.loads(ham.decode("utf-8"))
        return Lisans(no=yuk["no"], okul=yuk["okul"], kurum_kodu=yuk["kod"], verilis=date.fromisoformat(yuk["ver"]),
                      bitis=date.fromisoformat(yuk["bit"]) if yuk.get("bit") else None, tur=yuk.get("tur") or "Yıllık")
    except InvalidSignature:
        raise LisansHatasi("Lisans anahtarı geçersiz (imza doğrulanamadı).") from None
    except (ValueError, KeyError, TypeError):
        raise LisansHatasi("Lisans anahtarı okunamadı. Anahtarı eksiksiz kopyaladığınızdan emin olun.") from None


def _bugun(db) -> date:
    """Sistem saati geri alınmışsa işlem kaydındaki en son tarih esas alınır."""
    bugun = date.today()
    try:
        son = db.deger("SELECT MAX(zaman) FROM islem_log", (), None)
        if son:
            bugun = max(bugun, datetime.strptime(str(son)[:10], "%Y-%m-%d").date())
    except Exception:
        pass
    return bugun


def _deneme_baslangici(db) -> date:
    kayit = db.ayar("deneme_baslangic")
    adaylar = [date.today()]
    if kayit:
        try:
            adaylar.append(date.fromisoformat(kayit))
        except ValueError:
            pass
    try:
        ilk = db.deger("SELECT MIN(zaman) FROM islem_log", (), None)
        if ilk:
            adaylar.append(datetime.strptime(str(ilk)[:10], "%Y-%m-%d").date())
    except Exception:
        pass
    bas = min(adaylar)
    if kayit != bas.isoformat():
        db.ayar_yaz("deneme_baslangic", bas.isoformat())
    return bas


def durum(db) -> Durum:
    bugun = _bugun(db)
    metin = db.ayar("lisans")
    if metin:
        try:
            lis = coz(metin)
        except LisansHatasi as e:
            return Durum(False, f"Kayıtlı lisans geçersiz: {e}")
        kod = kurum_kodu_normalize(db.kurum().get("kurum_kodu"))
        if kod != lis.kurum_kodu:
            return Durum(False, f"Lisans {lis.kurum_kodu} kurum kodlu okula aittir; bu veritabanındaki kurum kodu "
                                f"'{kod or 'boş'}'.", lis)
        if lis.bitis is None:
            return Durum(True, f"Lisanslı: {lis.okul} ({SUREKLI})", lis)
        kalan = (lis.bitis - bugun).days
        if kalan < 0:
            return Durum(False, f"Lisans süresi {lis.bitis_metni()} tarihinde doldu. Program salt okunur çalışıyor.",
                         lis, kalan, True)
        return Durum(True, f"Lisanslı: {lis.okul} (bitiş {lis.bitis_metni()}, {kalan} gün)", lis, kalan,
                     kalan <= UYARI_GUN)
    kalan = DENEME_GUN - (bugun - _deneme_baslangici(db)).days
    if kalan < 0:
        return Durum(False, "Deneme süresi doldu. Program salt okunur çalışıyor; devam etmek için lisans giriniz.",
                     kalan_gun=kalan, uyari=True, deneme=True)
    return Durum(True, f"Deneme sürümü: {kalan} gün kaldı", kalan_gun=kalan, uyari=True, deneme=True)


def uygula(db) -> Durum:
    """Lisans durumunu hesaplar ve veritabanını gerekirse salt okunur yapar."""
    try:
        d = durum(db)
    except Exception as e:
        d = Durum(True, f"Lisans durumu okunamadı: {e}")
    db.salt_okunur = not d.yazilabilir
    return d


def etkinlestir(db, metin: str) -> Lisans:
    lis = coz(metin)
    kurum = db.kurum()
    kod = kurum_kodu_normalize(kurum.get("kurum_kodu"))
    if kod and kod != lis.kurum_kodu:
        raise LisansHatasi(f"Bu lisans {lis.kurum_kodu} kurum kodlu okul ({lis.okul}) içindir. Bu veritabanında "
                           f"kayıtlı kurum kodu {kod}. Kurum kodu hatalıysa önce 'Kurum ve Görevliler' sayfasında düzeltin.")
    if lis.bitis and lis.bitis < date.today():
        raise LisansHatasi(f"Bu lisansın süresi {lis.bitis_metni()} tarihinde dolmuş.")
    kilit, db.salt_okunur = db.salt_okunur, False
    try:
        with db.islem():
            if not kod:
                db.guncelle("kurum", 1, {"kurum_kodu": lis.kurum_kodu}, log=False)
            db.ayar_yaz("lisans", "".join(metin.split()))
            db.log("Lisans etkinleştirme", detay=f"{lis.no} - {lis.okul} - bitiş {lis.bitis_metni()}")
    finally:
        db.salt_okunur = kilit
    uygula(db)
    return lis


def lisansli_mi(db) -> bool:
    try:
        d = durum(db)
    except Exception:
        return False
    return d.lisans is not None and d.yazilabilir
