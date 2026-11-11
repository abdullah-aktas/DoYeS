"""Excel dışa ve içe aktarma."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path


def _ox():
    try:
        from openpyxl import Workbook, load_workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError as e:
        raise ImportError("Excel için openpyxl gerekir (pip install openpyxl).") from e
    return Workbook, load_workbook, Alignment, Border, Font, PatternFill, Side, get_column_letter


def _xls_uyari(ad: str | None = None):
    uzanti = Path(ad or "").suffix.lower()
    if uzanti == ".xls":
        raise ValueError(
            "Eski .xls biçimi desteklenmez. Excel'de «Farklı Kaydet → Excel Çalışma Kitabı (*.xlsx)» "
            "yapın veya uygulamadan Şablon indirip doldurun.")


def disa_aktar(yol: Path, sayfalar: list[tuple[str, list, list]], baslik: str | None = None) -> Path:
    """sayfalar: [(sayfa_adı, başlıklar, satırlar)]"""
    Workbook, _, Alignment, Border, Font, PatternFill, Side, get_column_letter = _ox()
    _INCE = Side(style="thin", color="B7C3D0")
    wb = Workbook()
    wb.remove(wb.active)
    for ad, basliklar, satirlar in sayfalar:
        ws = wb.create_sheet(title=_sayfa_adi(ad))
        r0 = 1
        if baslik:
            ws.cell(row=1, column=1, value=baslik).font = Font(bold=True, size=12, color="1F4E79")
            r0 = 3
        for j, b in enumerate(basliklar, 1):
            c = ws.cell(row=r0, column=j, value=b)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F4E79")
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            c.border = Border(left=_INCE, right=_INCE, top=_INCE, bottom=_INCE)
        for i, s in enumerate(satirlar, r0 + 1):
            for j, v in enumerate(s, 1):
                c = ws.cell(row=i, column=j, value=v)
                c.border = Border(left=_INCE, right=_INCE, top=_INCE, bottom=_INCE)
                if isinstance(v, float):
                    c.number_format = '#,##0.00'
        for j, b in enumerate(basliklar, 1):
            uzunluk = max([len(str(b))] + [len(str(s[j - 1])) for s in satirlar[:300] if j - 1 < len(s) and s[j - 1] is not None])
            ws.column_dimensions[get_column_letter(j)].width = min(max(10, uzunluk + 2), 60)
        ws.freeze_panes = ws.cell(row=r0 + 1, column=1)
    yol = Path(yol)
    wb.save(str(yol))
    return yol


def _sayfa_adi(ad: str) -> str:
    for ch in '[]:*?/\\':
        ad = ad.replace(ch, " ")
    return ad[:31] or "Sayfa"


def oku(yol: Path | None = None, veri: bytes | None = None, ad: str | None = None) -> dict[str, list[list]]:
    """Tüm sayfaları hücre değerleri (hesaplanmış) olarak döndürür. yol veya veri (bytes) verin."""
    _xls_uyari(ad or (str(yol) if yol else None))
    _, load_workbook, *_ = _ox()
    if veri is not None:
        if not veri:
            raise ValueError("Excel dosyası boş.")
        kaynak = BytesIO(veri)
    elif yol is not None:
        yol = Path(yol)
        if not yol.is_file():
            raise ValueError("Excel dosyası bulunamadı.")
        _xls_uyari(yol.name)
        kaynak = str(yol)
    else:
        raise ValueError("Excel dosyası veya içeriği verilmedi.")
    wb = load_workbook(kaynak, data_only=True, read_only=True)
    sonuc = {}
    for ws in wb.worksheets:
        sonuc[ws.title] = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    return sonuc


def _norm(s) -> str:
    tablo = str.maketrans("ÇĞİIÖŞÜçğıöşü", "CGIIOSUcgiosu")
    return "".join(ch for ch in str(s or "").translate(tablo).lower() if ch.isalnum())


def _eslesir(hn: str, aday: str) -> bool:
    """Kısa adaylar ('no', 'tc' gibi) yalnız tam eşleşir; 'S.No' sütunu 'Okul no' sanılmasın."""
    an = _norm(aday)
    return hn == an or (len(an) >= 4 and an in hn)


TCKN_BASLIKLARI = ["kimlik", "tc", "tcno", "tckn", "tc no"]
AD_BASLIKLARI = ["adı soyadı", "adı ve soyadı", "ad soyad", "adsoyad", "isim"]
PERSONEL_ICE_AKTARMA = {
    "sicil_no": ["personel no", "sicil", "id"], "tckn": TCKN_BASLIKLARI,
    "ad_soyad": AD_BASLIKLARI + ["personel adı"],
    "kadro_unvani": ["unvan", "görevi", "branş", "kadro"], "iban": ["iban"], "telefon": ["telefon"],
    "eposta": ["eposta", "e-posta", "email"], "hizmet_sinifi": ["hizmet sınıfı", "hizmet sinifi"],
    "dose_gorevi": ["dose görevi", "döse görevi", "görev"],
}
OGRENCI_ICE_AKTARMA = {
    "okul_no": ["okul no", "okul numarası", "öğrenci no", "numara", "no"], "tckn": TCKN_BASLIKLARI,
    "ad_soyad": AD_BASLIKLARI + ["öğrenci adı"], "sinif": ["sınıf", "şube"],
    "iban": ["iban"], "_gorev": ["görevi", "unvan"],
}
CARI_ICE_AKTARMA = {
    "kod": ["cari kod", "kod", "cari no", "cari kodu"], "unvan": ["unvan", "adı soyadı", "ad soyad", "firma", "ünvan", "unvan / adı soyadı"] + AD_BASLIKLARI,
    "tur": ["tür", "tur", "cari türü", "turu"], "vkn_tckn": ["vkn", "vergi no", "vergi kimlik", "vkn / t"] + TCKN_BASLIKLARI,
    "vergi_dairesi": ["vergi dairesi"], "telefon": ["telefon", "tel"], "eposta": ["eposta", "e-posta", "email"],
    "adres": ["adres"], "iban": ["iban"],
}
MALZEME_ICE_AKTARMA = {
    "kod": ["stok kod", "malzeme kod", "kod", "stok kodu"], "ad": ["malzeme adı", "malzeme", "ad", "ürün adı"],
    "tur": ["tür", "tur", "turu"], "birim": ["birim"], "kdv_orani": ["kdv", "kdv oranı", "kdv orani"],
    "kritik_stok": ["kritik stok", "min stok", "kritik stok miktarı"],
}
URUN_ICE_AKTARMA = {
    "kod": ["ürün kod", "urun kod", "kod"], "ad": ["ürün adı", "urun adi", "ad", "hizmet"],
    "tur": ["tür", "tur"], "birim": ["birim"], "kdv_orani": ["kdv", "kdv oranı"],
    "satis_fiyati": ["satış fiyatı", "fiyat", "birim fiyat"],
}
BOLUM_ICE_AKTARMA = {
    "kod": ["bölüm kod", "kod"], "ad": ["bölüm", "atölye", "ad", "bölüm adı"],
    "alan": ["alan", "dal"], "utp_yontemi": ["ütp", "utp", "dağıtım"],
}

TABLO_ICE_AKTARMA = {
    "personel": PERSONEL_ICE_AKTARMA, "ogrenci": OGRENCI_ICE_AKTARMA, "cari": CARI_ICE_AKTARMA,
    "malzeme": MALZEME_ICE_AKTARMA, "urun": URUN_ICE_AKTARMA, "bolum": BOLUM_ICE_AKTARMA,
}

SABLON_BASLIKLARI = {
    "bolum": ["Kod", "Bölüm / atölye adı", "Alan / dal", "ÜTP dağıtım yöntemi"],
    "personel": ["Sicil / kurum no", "T.C. kimlik no", "Adı soyadı", "Kadro unvanı / branş",
                 "Hizmet sınıfı", "DÖSE görevi", "IBAN", "Telefon", "E-posta"],
    "ogrenci": ["Okul no", "T.C. kimlik no", "Adı soyadı", "Sınıf / şube", "IBAN"],
    "cari": ["Cari kodu", "Türü", "Unvan / adı soyadı", "VKN / T.C. kimlik no", "Vergi dairesi",
             "Telefon", "E-posta", "Adres", "IBAN"],
    "malzeme": ["Stok kodu", "Malzeme adı", "Türü", "Birim", "KDV oranı (%)", "Kritik stok miktarı"],
    "urun": ["Kod", "Ürün / hizmet adı", "Türü", "Birim", "KDV oranı (%)", "Birim satış fiyatı (TL)"],
}


def ogrenci_satiri(gorev) -> bool:
    return _norm(str(gorev or "")).startswith(("ogrenc", "kursiyer", "stajyer"))


def _baslik_eslesmesi(satir, alan_esleri) -> dict[str, int]:
    eslesme = {}
    for j, h in enumerate(satir):
        hn = _norm(h) if isinstance(h, str) else ""
        if not hn:
            continue
        for alan, adaylar in alan_esleri.items():
            if alan not in eslesme and any(_eslesir(hn, a) for a in adaylar):
                eslesme[alan] = j
                break
    return eslesme


AD_ALANLARI = ("ad_soyad", "unvan", "ad")


def tablo_bul(yol: Path | None = None, alan_esleri: dict[str, list[str]] | None = None,
              ad_alani: str | None = None, tarama: int = 200, veri: bytes | None = None,
              ad: str | None = None) -> tuple[list[dict], str | None]:
    """Başlık satırını otomatik bulur; alan_esleri: {alan: [olası başlık parçaları]}. Tüm sayfalarda en çok alanın
    eşleştiği (ad alanını da içeren) başlık seçilir. Aynı sayfada alt alta birden çok tablo olabileceği için okuma
    TOPLAM satırında, yeni bir başlık satırında veya art arda iki adsız satırda durur. (kayıtlar, sayfa adı)"""
    if alan_esleri is None:
        raise ValueError("alan_esleri zorunlu.")
    ad_alani = ad_alani or next((a for a in AD_ALANLARI if a in alan_esleri), "")
    sayfalar = oku(yol=yol, veri=veri, ad=ad)
    en_iyi = (0, None, None, None)
    for ad, satirlar in sayfalar.items():
        for i, satir in enumerate(satirlar[:tarama]):
            eslesme = _baslik_eslesmesi(satir, alan_esleri)
            if ad_alani in alan_esleri and ad_alani not in eslesme:
                continue
            if len(eslesme) > en_iyi[0]:
                en_iyi = (len(eslesme), ad, i, eslesme)
    if not en_iyi[1]:
        return [], None
    _, ad, bas, eslesme = en_iyi
    sol, sag = max(0, min(eslesme.values()) - 2), max(eslesme.values()) + 1
    kayitlar, bos = [], 0
    for s in sayfalar[ad][bas + 1:]:
        k = {alan: (s[j] if j < len(s) else None) for alan, j in eslesme.items()}
        aralik = list(s[sol:sag])
        if any(_norm(v).startswith(("toplam", "geneltoplam")) for v in aralik if isinstance(v, str)):
            break
        if len(_baslik_eslesmesi(aralik, alan_esleri)) >= 2:
            break
        isim = k.get(ad_alani) if ad_alani in eslesme else next((v for v in k.values() if v not in (None, "")), None)
        if isim in (None, "") or (isinstance(isim, str) and not isim.strip()):
            bos += 1
            if kayitlar and bos >= 2:
                break
            continue
        bos = 0
        if all(not (isinstance(v, str) and v.startswith("=")) for v in k.values()):
            kayitlar.append(k)
    return kayitlar, ad


def eslestir_ve_oku(yol: Path | None = None, alan_esleri: dict[str, list[str]] | None = None,
                    veri: bytes | None = None, ad: str | None = None) -> list[dict]:
    return tablo_bul(yol=yol, alan_esleri=alan_esleri, veri=veri, ad=ad)[0]


def beklenen_basliklar(tablo: str) -> str:
    basliklar = SABLON_BASLIKLARI.get(tablo) or []
    return ", ".join(basliklar[:5]) + ("…" if len(basliklar) > 5 else "")


def tanim_oku(yol: Path | None = None, tablo: str = "", veri: bytes | None = None,
              ad: str | None = None) -> list[dict]:
    """Tanım tablosu için başlık eşlemesiyle satırları okur. yol veya veri (bytes) verin."""
    esler = TABLO_ICE_AKTARMA.get(tablo)
    if not esler:
        raise ValueError(f"Bu tablo için Excel içe aktarma yok: {tablo}")
    kayitlar = eslestir_ve_oku(yol=Path(yol) if yol else None, alan_esleri=esler, veri=veri, ad=ad)
    if not kayitlar:
        raise ValueError(
            "Dosyada eşleşen satır bulunamadı. «Şablon» ile indirdiğiniz başlıkları kullanın. "
            f"Örnek başlıklar: {beklenen_basliklar(tablo)}")
    return kayitlar


def sablon_yaz(tablo: str, yol: Path) -> Path:
    """Boş Excel şablonu (tek başlık satırı)."""
    basliklar = SABLON_BASLIKLARI.get(tablo)
    if not basliklar:
        raise ValueError(f"Bu tablo için şablon yok: {tablo}")
    etiket = {"bolum": "Bölüm", "personel": "Personel", "ogrenci": "Öğrenci", "cari": "Cari",
              "malzeme": "Malzeme", "urun": "Ürün"}[tablo]
    return disa_aktar(Path(yol), [(etiket, basliklar, [])], baslik=f"DÖSE {etiket} içe aktarma şablonu")


def satir_listesinden_oku(satirlar: list[list], alan_esleri: dict[str, list[str]],
                          ad_alani: str | None = None) -> list[dict]:
    """PDF vb. kaynaklardan gelen ham satır matrisini aynı başlık eşlemesiyle çözer."""
    ad_alani = ad_alani or next((a for a in AD_ALANLARI if a in alan_esleri), "")
    en_iyi = (0, None, None)
    for i, satir in enumerate(satirlar[:200]):
        eslesme = _baslik_eslesmesi(satir, alan_esleri)
        if ad_alani in alan_esleri and ad_alani not in eslesme:
            continue
        if len(eslesme) > en_iyi[0]:
            en_iyi = (len(eslesme), i, eslesme)
    if not en_iyi[2]:
        return []
    _, bas, eslesme = en_iyi
    kayitlar, bos = [], 0
    for s in satirlar[bas + 1:]:
        k = {alan: (s[j] if j < len(s) else None) for alan, j in eslesme.items()}
        isim = k.get(ad_alani) if ad_alani in eslesme else next((v for v in k.values() if v not in (None, "")), None)
        if isim in (None, "") or (isinstance(isim, str) and not str(isim).strip()):
            bos += 1
            if kayitlar and bos >= 2:
                break
            continue
        bos = 0
        kayitlar.append(k)
    return kayitlar
