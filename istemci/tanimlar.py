"""Screen metadata for the core phase and pure value conversions between form text and database values."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, DecimalException, InvalidOperation, ROUND_HALF_UP, localcontext

# (alan, etiket, tür, zorunlu, seçenek listesi). Choice lists come from public.secenek at runtime.
TANIM_ALANLARI: dict[str, list[tuple[str, str, str, bool, str | None]]] = {
    "bolum": [
        ("kod", "Kod", "metin", False, None), ("ad", "Bölüm / atölye adı", "metin", True, None),
        ("alan", "Alan / dal", "metin", False, None),
        ("utp_yontemi", "ÜTP dağıtım yöntemi", "secim", True, "utp_yontemi"),
        ("aktif", "Aktif", "bool", False, None), ("aciklama", "Açıklama", "cokmetin", False, None),
    ],
    "personel": [
        ("sicil_no", "Sicil / kurum no", "metin", False, None), ("tckn", "T.C. kimlik no", "metin", False, None),
        ("ad_soyad", "Adı soyadı", "metin", True, None), ("kadro_unvani", "Kadro unvanı / branş", "metin", False, None),
        ("hizmet_sinifi", "Hizmet sınıfı", "secim", True, "hizmet_sinifi"),
        ("dose_gorevi", "DÖSE görevi", "secim", True, "dose_gorevi"),
        ("unvan_grubu", "Unvan puan grubu", "secim_sayi", False, "unvan_grubu"),
        ("bolum_id", "Bölüm / atölye", "fk_bolum", False, None),
        ("istihdam", "İstihdam", "secim", False, "istihdam"),
        ("iban", "IBAN", "metin", False, None), ("telefon", "Telefon", "metin", False, None),
        ("eposta", "E-posta", "metin", False, None), ("aktif", "Aktif", "bool", False, None),
        ("notlar", "Notlar", "cokmetin", False, None),
    ],
    "ogrenci": [
        ("okul_no", "Okul no", "metin", False, None), ("tckn", "T.C. kimlik no", "metin", False, None),
        ("ad_soyad", "Adı soyadı", "metin", True, None), ("dogum_tarihi", "Doğum tarihi", "tarih", False, None),
        ("sinif", "Sınıf / şube", "metin", False, None), ("bolum_id", "Alan / bölüm", "fk_bolum", False, None),
        ("veli_adi", "Veli adı soyadı", "metin", False, None), ("veli_telefon", "Veli telefon", "metin", False, None),
        ("veli_muvafakat", "Veli yazılı muvafakati alındı", "bool", False, None),
        ("muvafakat_tarihi", "Muvafakat tarihi", "tarih", False, None), ("iban", "IBAN", "metin", False, None),
        ("aktif", "Aktif", "bool", False, None), ("notlar", "Notlar", "cokmetin", False, None),
    ],
    "cari": [
        ("kod", "Cari kodu (boş bırakılırsa otomatik)", "metin", False, None),
        ("tur", "Türü", "secim", True, "cari_tur"), ("unvan", "Unvan / adı soyadı", "metin", True, None),
        ("kamu_kurumu", "Kamu kurumu", "bool", False, None), ("vergi_dairesi", "Vergi dairesi", "metin", False, None),
        ("vkn_tckn", "VKN / T.C. kimlik no", "metin", False, None), ("telefon", "Telefon", "metin", False, None),
        ("eposta", "E-posta", "metin", False, None), ("adres", "Adres", "cokmetin", False, None),
        ("iban", "IBAN", "metin", False, None), ("aktif", "Aktif", "bool", False, None),
        ("notlar", "Notlar", "cokmetin", False, None),
    ],
    "malzeme": [
        ("kod", "Stok kodu", "metin", False, None), ("ad", "Malzeme adı", "metin", True, None),
        ("tur", "Türü", "secim", True, "malzeme_tur"), ("birim", "Birim", "secim", False, "birim"),
        ("kdv_orani", "KDV oranı (%)", "oran", False, None), ("kritik_stok", "Kritik stok miktarı", "ondalik", False, None),
        ("aktif", "Aktif", "bool", False, None), ("aciklama", "Açıklama", "cokmetin", False, None),
    ],
    "urun": [
        ("kod", "Kod", "metin", False, None), ("ad", "Ürün / hizmet adı", "metin", True, None),
        ("tur", "Türü", "secim", True, "urun_tur"), ("birim", "Birim", "secim", False, "birim"),
        ("bolum_id", "Bölüm / atölye", "fk_bolum", False, None),
        ("ucret_esasi", "Ücret ödeme esası", "secim", False, "ucret_esasi"),
        ("kdv_orani", "KDV oranı (%)", "oran", False, None), ("satis_fiyati", "Birim satış fiyatı (TL)", "para", False, None),
        ("kar_orani", "Hedef kâr oranı (%)", "oran", False, None),
        ("mamul_malzeme_id", "Stoktaki mamul kartı", "fk_malzeme", False, None),
        ("aktif", "Aktif", "bool", False, None), ("aciklama", "Açıklama", "cokmetin", False, None),
    ],
}

KURUM_ALANLARI: list[tuple[str, str, str, bool, str | None]] = [
    ("okul_adi", "Okul adı", "metin", True, None), ("isletme_adi", "İşletme adı", "metin", False, None),
    ("kurum_kodu", "Kurum kodu (lisansa bağlı)", "salt", False, None),
    ("il", "İl", "metin", False, None), ("ilce", "İlçe", "metin", False, None),
    ("adres", "Adres", "cokmetin", False, None), ("telefon", "Telefon", "metin", False, None),
    ("eposta", "E-posta", "metin", False, None), ("evrak_kodu", "Evrak kodu", "metin", False, None),
    ("vergi_dairesi", "Vergi dairesi", "metin", False, None), ("vkn", "Vergi kimlik no", "metin", False, None),
    ("banka", "Banka", "metin", False, None), ("iban", "IBAN", "metin", False, None),
    ("harcama_yetkilisi", "Harcama yetkilisi", "metin", False, None),
    ("gerceklestirme_gorevlisi", "Gerçekleştirme görevlisi", "metin", False, None),
    ("sayman", "Sayman", "metin", False, None),
    ("buyuksehir", "Büyükşehir belediyesi sınırında", "bool", False, None),
    ("yuz_yuze_egitim", "Yüz yüze eğitim yapılıyor", "bool", False, None),
    ("tahsis_sermaye", "Tahsis edilen sermaye (TL)", "para", False, None),
    ("odenmis_sermaye", "Ödenmiş sermaye (TL)", "para", False, None),
]

TANIM_SIRALAMA = {"bolum": "ad", "personel": "aktif.desc,ad_soyad", "ogrenci": "aktif.desc,ad_soyad",
                  "cari": "unvan", "malzeme": "ad", "urun": "ad"}
TANIM_BASLIK_ALANI = {"bolum": "ad", "personel": "ad_soyad", "ogrenci": "ad_soyad", "cari": "unvan",
                      "malzeme": "ad", "urun": "ad"}
TANIM_ALT_ALANLAR = {"bolum": ("alan", "kod"), "personel": ("dose_gorevi", "kadro_unvani"),
                     "ogrenci": ("sinif", "okul_no"), "cari": ("kod", "tur"), "malzeme": ("kod", "tur"),
                     "urun": ("kod", "tur")}

ROLLER = ["Sistem Yöneticisi", "Okul Müdürü", "Teknik Müdür Yardımcısı", "Sayman", "Alan Şefi", "Öğretmen",
          "Memur / Veri Girişi", "İzleyici / Denetçi"]


def ondalik_coz(metin: str) -> Decimal:
    s = metin.strip().replace(" ", "").replace("₺", "").replace("TL", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?[1-9]\d{0,2}(\.\d{3})+", s):
        # Turkish thousands separator without decimals: 10.000 / 1.250.000
        s = s.replace(".", "")
    try:
        deger = Decimal(s)
    except InvalidOperation as e:
        raise ValueError("sayı") from e
    if not deger.is_finite():
        raise ValueError("sayı")
    return deger


def sayi_coz(metin: str) -> float:
    deger = float(ondalik_coz(metin))
    if deger in (float("inf"), float("-inf")):
        raise ValueError("sayı")
    return deger


def tarih_coz(metin: str) -> str:
    s = metin.strip()
    try:
        if "." in s or "/" in s:
            g, a, y = s.replace("/", ".").split(".")
            return date(int(y), int(a), int(g)).isoformat()
        return date.fromisoformat(s).isoformat()
    except ValueError as e:
        raise ValueError("tarih") from e


def sayi_yaz(deger: Decimal | float, basamak: int = 2) -> str:
    metin = f"{deger:,.{basamak}f}"
    return metin.replace(",", "\0").replace(".", ",").replace("\0", ".")


def siparis_sayisi_yaz(deger) -> str:
    return "" if deger is None else str(deger).replace(".", ",")


def siparis_yuzdesi_yaz(deger) -> str:
    if deger is None:
        return ""
    oran = Decimal(str(deger))
    with localcontext() as baglam:
        baglam.prec = max(28, len(oran.as_tuple().digits) + 2)
        metin = format(oran * 100, "f")
    if "." in metin:
        metin = metin.rstrip("0").rstrip(".")
    return metin.replace(".", ",")


def siparis_yuzdesi_orana(yuzde: Decimal) -> Decimal:
    with localcontext() as baglam:
        baglam.prec = max(28, len(yuzde.as_tuple().digits) + 2)
        return yuzde / 100


def siparis_kalem_ondalik_tutari(
    miktar: Decimal | float, birim_fiyat: Decimal | float, iskonto_yuzde: Decimal | float = 0
) -> tuple[Decimal, Decimal, Decimal]:
    m, f, o = Decimal(str(miktar)), Decimal(str(birim_fiyat)), Decimal(str(iskonto_yuzde))
    if not all(d.is_finite() for d in (m, f, o)) or m <= 0 or f < 0 or o < 0 or o > 100:
        raise ValueError("Miktar pozitif, birim fiyat sıfır veya üstü ve indirim %0-%100 olmalıdır.")
    kuruş = Decimal("0.01")
    basamak = max(0, m.adjusted() + f.adjusted())
    try:
        with localcontext() as baglam:
            baglam.prec = max(28, sum(len(d.as_tuple().digits) for d in (m, f, o)) + 4,
                              basamak + len(o.as_tuple().digits) + 8)
            brut = (m * f).quantize(kuruş, rounding=ROUND_HALF_UP)
            iskonto = (brut * o / 100).quantize(kuruş, rounding=ROUND_HALF_UP)
            net = brut - iskonto
    except DecimalException as e:
        raise ValueError("Sipariş tutarı hesaplanabilir sayı aralığında olmalıdır.") from e
    return brut, iskonto, net


def siparis_kalem_tutari(
    miktar: Decimal | float, birim_fiyat: Decimal | float, iskonto_yuzde: Decimal | float = 0
) -> tuple[float, float, float]:
    """Return rounded gross, discount, and net amounts for one order line."""
    brut, iskonto, net = siparis_kalem_ondalik_tutari(miktar, birim_fiyat, iskonto_yuzde)
    return float(brut), float(iskonto), float(net)


def girdiden(tur: str, etiket: str, deger) -> object:
    """Converts a widget value to the database value; raises ValueError with a user-facing message."""
    if tur == "bool":
        return 1 if deger else 0
    metin = "" if deger is None else str(deger).strip()
    if not metin:
        return None
    try:
        if tur in ("fk_bolum", "fk_malzeme", "secim_sayi"):
            return int(metin)
        if tur == "oran":
            return round(sayi_coz(metin) / 100, 6)
        if tur in ("para", "ondalik"):
            return sayi_coz(metin)
        if tur == "tarih":
            return tarih_coz(metin)
    except ValueError:
        if tur == "tarih":
            raise ValueError(f"'{etiket}' geçerli bir tarih olmalıdır (GG.AA.YYYY).") from None
        raise ValueError(f"'{etiket}' geçerli bir sayı olmalıdır.") from None
    return metin


def gosterim(tur: str, deger) -> object:
    """Converts a database value to what the form widget shows."""
    if tur == "bool":
        return bool(deger)
    if deger is None:
        return ""
    if tur == "oran":
        return f"{float(deger) * 100:g}".replace(".", ",")
    if tur == "para":
        return sayi_yaz(float(deger))
    if tur == "ondalik":
        return f"{float(deger):g}".replace(".", ",")
    if tur == "tarih":
        try:
            return date.fromisoformat(str(deger)).strftime("%d.%m.%Y")
        except ValueError:
            return str(deger)
    return str(deger)


def form_verisi(alanlar, degerler: dict) -> dict:
    """Builds the row payload from {alan: widget value}; read-only fields are never sent."""
    veri = {}
    for alan, etiket, tur, zorunlu, _ in alanlar:
        if tur == "salt" or alan not in degerler:
            continue
        deger = girdiden(tur, etiket, degerler[alan])
        if zorunlu and deger is None:
            raise ValueError(f"'{etiket}' alanı zorunludur.")
        veri[alan] = deger
    return veri


def eslesir(kayit: dict, arama: str, tablo: str) -> bool:
    if not arama:
        return True
    a = arama.casefold()
    alanlar = (TANIM_BASLIK_ALANI[tablo],) + TANIM_ALT_ALANLAR[tablo] + ("tckn", "vkn_tckn")
    return any(a in str(kayit.get(k) or "").casefold() for k in alanlar)
