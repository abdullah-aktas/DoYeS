"""DÖSE hesaplama motoru (arayüzden bağımsız, test edilebilir saf fonksiyonlar)."""
from __future__ import annotations

import calendar
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from . import mevzuat


def yuvarla(x, basamak: int = 2) -> float:
    return float(Decimal(str(x or 0)).quantize(Decimal(1).scaleb(-basamak), rounding=ROUND_HALF_UP))


def para(x) -> str:
    """1234567.891 -> '1.234.567,89'"""
    s = f"{yuvarla(x):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def oran_yazi(x) -> str:
    return "%" + (f"{(x or 0) * 100:.2f}".rstrip("0").rstrip(".")).replace(".", ",")


# ---------------------------------------------------------------- KDV / stopaj
def kdv_hesapla(matrah: float, oran: float) -> float:
    return yuvarla(matrah * oran)


def kdv_ayir(kdv_dahil: float, oran: float) -> tuple[float, float]:
    matrah = yuvarla(kdv_dahil / (1 + oran))
    return matrah, yuvarla(kdv_dahil - matrah)


@dataclass
class BelgeToplami:
    matrah: float = 0.0
    kdv: float = 0.0
    tevkif_kdv: float = 0.0
    stopaj: float = 0.0
    genel_toplam: float = 0.0
    net_tutar: float = 0.0
    brut: float = 0.0
    iskonto: float = 0.0


def kalem_tutari(k: dict) -> tuple[float, float, float]:
    """(iskontosuz tutar, iskonto, iskonto sonrası tutar). 'iskonto' (TL) verilmemişse 'iskonto_orani'ndan hesaplanır.
    Faturada gösterilen iskonto KDV matrahına dahil edilmez (KDV K. md.25/a)."""
    brut = yuvarla((k.get("miktar") or 0) * (k.get("birim_fiyat") or 0))
    iskonto = k.get("iskonto")
    if iskonto is None:
        iskonto = brut * (k.get("iskonto_orani") or 0)
    iskonto = yuvarla(iskonto)
    return brut, iskonto, yuvarla(brut - iskonto)


def kalem_hatalari(kalemler: list[dict]) -> list[str]:
    """Belgeye kaydedilmesi muhasebe ve stok kayıtlarını bozacak kalem hataları."""
    hatalar = []
    for i, k in enumerate(kalemler, 1):
        brut, iskonto, net = kalem_tutari(k)
        ad = f"{i}. kalem"
        if (k.get("miktar") or 0) <= 0:
            hatalar.append(f"{ad}: miktar sıfırdan büyük olmalıdır. İndirimi eksi satır olarak değil, iskonto sütununa yazınız.")
        if (k.get("birim_fiyat") or 0) < 0:
            hatalar.append(f"{ad}: birim fiyat eksi olamaz. İndirimi iskonto sütununa yazınız.")
        if iskonto < 0 or (k.get("iskonto_orani") or 0) < 0:
            hatalar.append(f"{ad}: iskonto eksi olamaz.")
        elif brut >= 0 and iskonto > brut + 0.005:
            hatalar.append(f"{ad}: iskonto ({para(iskonto)} TL) kalem tutarını ({para(brut)} TL) aşamaz.")
    return hatalar


def iskonto_dagit(kalemler: list[dict], toplam_iskonto: float) -> list[float]:
    """Belge altı (genel) iskontoyu kalemlere tutarları (miktar × birim fiyat) oranında, kuruşu kuruşuna dağıtır."""
    brutler = {i: kalem_tutari(k)[0] for i, k in enumerate(kalemler)}
    pay = orantili_dagit(yuvarla(toplam_iskonto), brutler)
    return [pay.get(i, 0.0) for i in range(len(kalemler))]


def belge_toplami(kalemler: list[dict], tevkifat_orani: float = 0.0, stopaj_orani: float = 0.0) -> BelgeToplami:
    """kalemler: [{'miktar', 'birim_fiyat', 'kdv_orani', 'iskonto' | 'iskonto_orani'}]. KDV ve stopaj iskonto sonrası
    matrah üzerinden hesaplanır. net_tutar: karşı tarafa ödenecek/karşı taraftan tahsil edilecek tutar."""
    t = BelgeToplami()
    for k in kalemler:
        brut, iskonto, tutar = kalem_tutari(k)
        t.brut += brut
        t.iskonto += iskonto
        t.matrah += tutar
        t.kdv += kdv_hesapla(tutar, k.get("kdv_orani") or 0)
    t.brut = yuvarla(t.brut)
    t.iskonto = yuvarla(t.iskonto)
    t.matrah = yuvarla(t.matrah)
    t.kdv = yuvarla(t.kdv)
    t.tevkif_kdv = yuvarla(t.kdv * tevkifat_orani)
    t.stopaj = yuvarla(t.matrah * stopaj_orani)
    t.genel_toplam = yuvarla(t.matrah + t.kdv)
    t.net_tutar = yuvarla(t.genel_toplam - t.tevkif_kdv - t.stopaj)
    return t


# ---------------------------------------------------------------- gelir vergisi / damga vergisi
def tarife_vergisi(matrah: float, dilimler) -> float:
    """dilimler: [[üst sınır, oran], ..., [None, oran]] (kümülatif üst sınırlar)."""
    vergi, alt = 0.0, 0.0
    for ust, oran in dilimler:
        if ust is None or matrah <= ust:
            vergi += (matrah - alt) * oran
            return yuvarla(max(vergi, 0))
        vergi += (ust - alt) * oran
        alt = ust
    return yuvarla(vergi)


def gelir_vergisi(brut: float, onceki_kumulatif: float, dilimler) -> float:
    return yuvarla(tarife_vergisi(onceki_kumulatif + brut, dilimler) - tarife_vergisi(onceki_kumulatif, dilimler))


def asgari_ucret_gv_istisnasi(ay: int, p: dict) -> float:
    """Asgari ücrete isabet eden aylık GV (kümülatif asgari ücret matrahına göre)."""
    m = p["asgari_ucret_gv_matrahi"]
    d = p["gv_tarifesi_ucret"]
    return yuvarla(tarife_vergisi(m * ay, d) - tarife_vergisi(m * (ay - 1), d))


@dataclass
class Kesinti:
    brut: float
    gelir_vergisi: float = 0.0
    damga_vergisi: float = 0.0
    sgk: float = 0.0
    net: float = 0.0


def ucret_kesintileri(brut: float, onceki_kumulatif: float, ay: int, p: dict, ogrenci: bool = False) -> Kesinti:
    brut = yuvarla(brut)
    k = Kesinti(brut=brut)
    if brut <= 0:
        return k
    gv = gelir_vergisi(brut, onceki_kumulatif, p["gv_tarifesi_ucret"])
    dv = yuvarla(brut * p["damga_vergisi_orani"])
    istisna = p["ogrencide_asgari_ucret_istisnasi"] if ogrenci else p["memurda_asgari_ucret_istisnasi"]
    if istisna:
        gv = max(0.0, yuvarla(gv - asgari_ucret_gv_istisnasi(max(1, min(12, ay)), p)))
        dv = max(0.0, yuvarla(dv - p["asgari_ucret_brut"] * p["damga_vergisi_orani"]))
    if ogrenci and p.get("ogrenci_sgk_orani"):
        k.sgk = yuvarla(brut * p["ogrenci_sgk_orani"])
    k.gelir_vergisi, k.damga_vergisi = gv, dv
    k.net = yuvarla(brut - gv - dv)
    return k


# ---------------------------------------------------------------- sipariş tahsis kuralları
def esas_kurallari(ucret_esasi: str, p: dict) -> dict:
    """Ücret esasına göre asgari kâr, faaliyet gideri ve peşinat oranları."""
    e = ucret_esasi or ""
    if e.startswith("Özel Sektör"):
        return {"kar": p["os_kar_orani"], "faaliyet": p["os_faaliyet_orani"], "pesin": p["os_pesin_orani"],
                "dayanak": "Yön. md.10"}
    if e.startswith("Tesis"):
        return {"kar": p["tesis_kar_orani"], "faaliyet": p["tesis_faaliyet_orani"], "pesin": p["tesis_pesin_orani"],
                "dayanak": "Yön. md.12"}
    if e.startswith("Parça"):
        return {"kar": p["pb_kar_orani"], "faaliyet": p["pb_faaliyet_orani"], "pesin": 0.0, "dayanak": "Yön. md.8/2"}
    return {"kar": 0.0, "faaliyet": 0.0, "pesin": 0.0, "dayanak": "Fazla çalışma esası"}


@dataclass
class SiparisTahsis:
    bedel: float
    kar: float = 0.0
    faaliyet: float = 0.0
    malzeme: float = 0.0
    azami_iscilik: float = 0.0
    iscilik: float = 0.0
    ogrenci_hakki: float = 0.0
    personel_iscilik: float = 0.0
    asgari_pesinat: float = 0.0
    hatalar: list = field(default_factory=list)
    uyarilar: list = field(default_factory=list)


def siparis_tahsis(bedel: float, ucret_esasi: str, p: dict, malzeme_maliyeti: float = 0.0,
                   iscilik: float | None = None, kar_orani: float | None = None,
                   ogrenci_orani: float | None = None, pesinat: float = 0.0,
                   ogrenci_uygulamasi: bool = True, malzeme_musteriden: bool = False,
                   sure_ay: int = 0, bakanlik_izni: bool = False, esik_deger_2kat: float | None = None) -> SiparisTahsis:
    kural = esas_kurallari(ucret_esasi, p)
    t = SiparisTahsis(bedel=yuvarla(bedel))
    kar_o = max(kar_orani or 0.0, kural["kar"])
    if kar_orani is not None and kar_orani < kural["kar"]:
        t.uyarilar.append(f"Kâr oranı asgari {oran_yazi(kural['kar'])} olmalıdır ({kural['dayanak']}); asgari oran uygulandı.")
    t.kar = yuvarla(bedel * kar_o)
    t.faaliyet = yuvarla(bedel * kural["faaliyet"])
    t.malzeme = 0.0 if malzeme_musteriden else yuvarla(malzeme_maliyeti)
    t.azami_iscilik = yuvarla(bedel - t.kar - t.faaliyet - t.malzeme)
    t.iscilik = t.azami_iscilik if iscilik is None else yuvarla(iscilik)
    malz_o = p.get("malzeme_azami_orani") or 0.0
    if malz_o and bedel > 0 and t.malzeme > yuvarla(bedel * malz_o) + 0.005:
        t.uyarilar.append(f"İlk madde ve malzeme ({para(t.malzeme)}) sipariş bedeline göre sınırı aşıyor "
                          f"(azami {oran_yazi(malz_o)} = {para(yuvarla(bedel * malz_o))}); ön maliyeti ve fiyatı gözden geçiriniz.")
    if t.azami_iscilik < 0:
        t.hatalar.append("Sözleşme bedeli; kâr, faaliyet gideri ve malzeme maliyetini karşılamıyor. Fiyatı yeniden belirleyiniz.")
    if t.iscilik > t.azami_iscilik + 0.005:
        t.hatalar.append(f"İşçilik tutarı ({para(t.iscilik)}) ayrılabilecek azami işçiliği ({para(t.azami_iscilik)}) aşıyor.")
    ogr_o = max(ogrenci_orani or 0.0, p["ogrenci_hakki_orani"])
    if ucret_esasi and not ucret_esasi.startswith("Fazla"):
        if ogrenci_orani is not None and ogrenci_orani < p["ogrenci_hakki_orani"]:
            t.uyarilar.append(f"Öğrenci hakkı işçiliğin en az {oran_yazi(p['ogrenci_hakki_orani'])}'u olmalıdır (Yön. md.8/3); asgari oran uygulandı.")
        t.ogrenci_hakki = yuvarla(max(t.iscilik, 0) * ogr_o)
    t.personel_iscilik = yuvarla(max(t.iscilik, 0) - t.ogrenci_hakki)
    t.asgari_pesinat = yuvarla(bedel * kural["pesin"])
    if kural["pesin"] and pesinat + 0.005 < t.asgari_pesinat:
        t.uyarilar.append(f"Sözleşme bedelinin en az {oran_yazi(kural['pesin'])}'i ({para(t.asgari_pesinat)}) peşin tahsil edilmelidir ({kural['dayanak']}).")
    if not ogrenci_uygulamasi:
        t.hatalar.append("Öğrencinin uygulamaya alınmadığı iş kabul edilemez (DHGM 15.01.2026 tarihli yazı, m.1).")
    if ucret_esasi and (ucret_esasi.startswith("Özel") or ucret_esasi.startswith("Tesis")):
        if sure_ay > 36:
            t.hatalar.append("Özel sektör işbirliği sözleşmesi 36 aydan uzun olamaz (Yön. md.9/2).")
        elif (sure_ay > 12 or (esik_deger_2kat and bedel > esik_deger_2kat)) and not bakanlik_izni:
            t.uyarilar.append("12 ayı veya eşik değerin iki katını aşan işbirliği sözleşmesi için Bakanlıktan yazılı izin alınmalıdır (Yön. md.9/2).")
        if ucret_esasi.startswith("Özel") and not malzeme_musteriden:
            t.uyarilar.append("Özel sektör işbirliğinde mal üretiminde malzeme işi yaptıran tarafça sağlanır (Yön. md.9/3).")
    return t


def yasal_ust_sinir_iscilik(s: dict, p: dict) -> float:
    """Siparişte ödemeye esas işçiliğin yasal üst sınırı: bedel - asgari kâr - faaliyet gideri - malzeme (Yön. md.8/2-4).
    Fazla çalışma esasında Yönetmelik oran öngörmediğinden kâr ve faaliyet gideri için parça başı oranları esas alınır."""
    bedel = s.get("sozlesme_bedeli") or 0
    if not (s.get("ucret_esasi") or "").startswith("Fazla"):
        return max(0.0, siparis_kaydi_tahsisi(dict(s, iscilik_tutari=None), p).azami_iscilik)
    malzeme = 0.0 if s.get("malzeme_musteriden") else (s.get("malzeme_maliyeti") or 0)
    kar = yuvarla(bedel * max(s.get("kar_orani") or 0, p["pb_kar_orani"]))
    return max(0.0, yuvarla(bedel - kar - yuvarla(bedel * p["pb_faaliyet_orani"]) - malzeme))


@dataclass
class YasalMaliyet:
    satis_fiyati: float
    malzeme: float
    diger: float = 0.0  # kullanıcının girdiği diğer giderler (enerji, bakım vb.)
    kar: float = 0.0
    faaliyet: float = 0.0
    genel_gider: float = 0.0  # faaliyet gideri üst sınırının diğer giderlerden artan kısmı
    iscilik: float = 0.0
    ogrenci_hakki: float = 0.0
    personel_iscilik: float = 0.0
    kar_orani: float = 0.0  # maliyet üzerine eklenen kâr oranı (maliyet + kâr = satış fiyatı)
    hatalar: list = field(default_factory=list)
    notlar: list = field(default_factory=list)


def yasal_maliyet_dagilimi(satis_fiyati: float, malzeme: float, ucret_esasi: str, p: dict,
                           diger: float = 0.0) -> YasalMaliyet:
    """Birim satış fiyatının yasal üst sınırlarla dağılımı: kâr asgari oranda; diğer giderler (enerji, bakım, genel
    giderler) faaliyet gideri oranına kadar (girilen giderler ayrılır, artanı genel gidere yazılır); işçilik kalan
    tutarın tamamı yani ayrılabilecek azami tutar; öğrenci hakkı işçiliğin asgari oranıdır."""
    m = YasalMaliyet(satis_fiyati=yuvarla(satis_fiyati, 4), malzeme=yuvarla(malzeme, 4), diger=yuvarla(diger, 4))
    kural = esas_kurallari(ucret_esasi, p)
    kar_o, faaliyet_o = kural["kar"], kural["faaliyet"]
    if not kar_o and not faaliyet_o:
        kar_o, faaliyet_o = p["pb_kar_orani"], p["pb_faaliyet_orani"]
        m.notlar.append("Fazla çalışma esasında Yönetmelik kâr ve faaliyet gideri oranı öngörmediğinden parça başı oranları "
                        f"(kâr {oran_yazi(kar_o)}, faaliyet gideri {oran_yazi(faaliyet_o)}; Yön. md.8/2) esas alındı.")
    if m.satis_fiyati <= 0:
        m.hatalar.append("Önce hedef birim satış fiyatını (KDV hariç) giriniz. Fiyat; piyasa araştırması ve benzer işlerin "
                         "fiyatları dikkate alınarak belirlenir (Yön. md.10).")
        return m
    m.kar = yuvarla(m.satis_fiyati * kar_o, 4)
    m.faaliyet = yuvarla(m.satis_fiyati * faaliyet_o, 4)
    m.genel_gider = yuvarla(max(m.faaliyet - m.diger, 0.0), 4)
    if m.diger > m.faaliyet + 0.00005:
        m.notlar.append(f"Girilen diğer giderler ({para(m.diger)} TL) faaliyet gideri karşılığını ({para(m.faaliyet)} TL) aşıyor; "
                        "aşan kısım işçilikten düşüldü. İşletme ve idari masraflar faaliyet gideri karşılığını aşamaz "
                        "(Çalışma Yönergesi md.11).")
    m.iscilik = yuvarla(m.satis_fiyati - m.kar - max(m.faaliyet, m.diger) - m.malzeme, 4)
    if m.iscilik < 0:
        asgari = yuvarla(max(m.malzeme / (1 - kar_o - faaliyet_o), (m.malzeme + m.diger) / (1 - kar_o))) \
            if kar_o + faaliyet_o < 1 else 0
        m.hatalar.append(f"Satış fiyatı malzeme, kâr ve giderleri karşılamıyor; birim fiyat en az {para(asgari)} TL olmalıdır.")
        m.iscilik = 0.0
    malz_o = p.get("malzeme_azami_orani") or 0.0
    if malz_o and m.malzeme > m.satis_fiyati * malz_o + 0.00005:
        m.notlar.append(f"Malzeme birim satış fiyatının {oran_yazi(malz_o)}'ini aşıyor; fiyatı gözden geçiriniz.")
    ogr_o = 0.0 if (ucret_esasi or "").startswith("Fazla") else p["ogrenci_hakki_orani"]
    m.ogrenci_hakki = yuvarla(m.iscilik * ogr_o, 4)
    m.personel_iscilik = yuvarla(m.iscilik - m.ogrenci_hakki, 4)
    maliyet = m.satis_fiyati - m.kar
    m.kar_orani = m.kar / maliyet if maliyet > 0 else 0.0
    return m


# ---------------------------------------------------------------- fazla çalışma günleri (Bütçe K cetveli, Çalışma Yönergesi md.9)
def _json_liste(deger) -> list:
    if isinstance(deger, str):
        try:
            deger = json.loads(deger)
        except ValueError:
            return []
    return deger if isinstance(deger, list) else []


def tatil_takvimi(p: dict) -> tuple[list[tuple[str, str]], set[str]]:
    donemler = [(str(a), str(b)) for a, b in (x for x in _json_liste(p.get("fc_tatil_donemleri"))
                                                   if isinstance(x, list) and len(x) == 2)]
    return donemler, {str(g) for g in _json_liste(p.get("fc_bayram_gunleri"))}


def takvim_tanimli(yil: int, p: dict) -> bool:
    donemler, bayramlar = tatil_takvimi(p)
    y = str(yil)
    return any(a[:4] == y or b[:4] == y for a, b in donemler) or any(g[:4] == y for g in bayramlar)


GUN_TURU_ADLARI = {"ogretim": "öğretim günü", "tatil": "tatil", "pazar": "Pazar", "bayram": "bayram"}


def gun_turu(t: date, p: dict) -> str:
    """'bayram' | 'pazar' | 'tatil' | 'ogretim'"""
    donemler, bayramlar = tatil_takvimi(p)
    s = t.isoformat()
    if s in bayramlar:
        return "bayram"
    if t.weekday() == 6:
        return "pazar"
    if t.weekday() == 5 or any(a <= s <= b for a, b in donemler):
        return "tatil"
    return "ogretim"


def gun_azami_saat(tur: str, p: dict) -> float:
    if tur == "bayram":
        return 0.0
    if tur == "pazar":
        return float(p["fc_tatil_gunu_saat"]) if p.get("fc_pazar_izinli") else 0.0
    return float(p["fc_tatil_gunu_saat"] if tur == "tatil" else p["fc_ogretim_gunu_saat"])


def fazla_calisma_gun_hatalari(yil: int, ay: int, gunluk: dict, p: dict) -> list[str]:
    """Günlük fazla çalışma saatlerini (gün -> saat) gün türüne göre azami sürelerle karşılaştırır."""
    hatalar = []
    son_gun = calendar.monthrange(yil, ay)[1]
    for g in sorted(gunluk):
        saat = gunluk[g] or 0
        if saat <= 0:
            continue
        if not 1 <= g <= son_gun:
            hatalar.append(f"{g}. gün seçilen ayda yok.")
            continue
        t = date(yil, ay, g)
        tur = gun_turu(t, p)
        azami = gun_azami_saat(tur, p)
        if saat > azami + 1e-9:
            if tur == "bayram":
                neden = "resmi/dini bayram gününde fazla çalışma yapılamaz (Bütçe K cetveli III-3)"
            elif tur == "pazar" and not p.get("fc_pazar_izinli"):
                neden = "Pazar günü fazla çalışma yapılamaz (Çalışma Yönergesi md.9/a-12)"
            else:
                neden = f"{GUN_TURU_ADLARI[tur]} için günlük azami {azami:g} saat (Bütçe K cetveli III-3)"
            hatalar.append(f"{t.strftime('%d.%m.%Y')}: {saat:g} saat; {neden}.")
    return hatalar


def ay_azami_fazla_calisma(yil: int, ay: int, p: dict) -> float:
    return sum(gun_azami_saat(gun_turu(date(yil, ay, g), p), p) for g in range(1, calendar.monthrange(yil, ay)[1] + 1))


# ---------------------------------------------------------------- parça başı tavanları ve dağıtım
def parca_basi_tavani(kisi_turu: str, hizmet_sinifi: str | None, p: dict) -> float:
    au = p["asgari_ucret_brut"]
    if kisi_turu == "Öğrenci":
        return yuvarla(au * p["pb_tavan_ogrenci"])
    hs = hizmet_sinifi or ""
    if hs.startswith("Eğitim"):
        return yuvarla(au * p["pb_tavan_egitim"])
    if hs.startswith("Teknik"):
        return yuvarla(au * p["pb_tavan_teknik"])
    return yuvarla(au * p["pb_tavan_diger"])


def orantili_dagit(havuz: float, agirliklar: dict) -> dict:
    """Havuzu ağırlıklara göre kuruşu kuruşuna dağıtır (yuvarlama farkı en büyük paya eklenir)."""
    toplam = sum(v for v in agirliklar.values() if v and v > 0)
    if havuz <= 0 or toplam <= 0:
        return {k: 0.0 for k in agirliklar}
    sonuc = {k: yuvarla(havuz * (v if v and v > 0 else 0) / toplam) for k, v in agirliklar.items()}
    fark = yuvarla(havuz - sum(sonuc.values()))
    if fark:
        en_buyuk = max(agirliklar, key=lambda k: agirliklar[k] or 0)
        sonuc[en_buyuk] = yuvarla(sonuc[en_buyuk] + fark)
    return sonuc


def tavan_uygula(hesaplanan: float, ay_ici_diger: float, tavan: float) -> tuple[float, float]:
    """Ay içinde başka siparişlerden alınanlar dahil tavanı aşan kısım ödenmez. (ödenecek, aşım)"""
    kalan = max(0.0, tavan - ay_ici_diger)
    odenecek = yuvarla(min(hesaplanan, kalan))
    return odenecek, yuvarla(hesaplanan - odenecek)


def parca_basi_gun(yillik_parca_basi: float, fazla_calisma_saat_ucreti: float) -> float:
    """Yön. md.13/2: parça başı ücret / fazla çalışma saat ücreti = saat; saat / 8 = gün."""
    if not fazla_calisma_saat_ucreti:
        return 0.0
    return yuvarla(yillik_parca_basi / fazla_calisma_saat_ucreti / 8, 2)


# ---------------------------------------------------------------- yıl sonu kâr bölüşümü
@dataclass
class YilSonuBolusum:
    donem_kari: float
    dagitilabilir_kar: float = 0.0
    utp_azami: float = 0.0
    dagitima_esas: float = 0.0
    dagitilan_utp: float = 0.0
    dagitilamayan_utp: float = 0.0
    sermaye_payi: float = 0.0
    merkez_payi: float = 0.0
    notlar: list = field(default_factory=list)


def yil_sonu_bolusum(donem_kari: float, tahsis_sermaye: float, odenmis_sermaye: float,
                     utp_orani: float, p: dict, dagitilan_utp: float | None = None,
                     faiz_duzeltme: float = 0.0) -> YilSonuBolusum:
    b = YilSonuBolusum(donem_kari=yuvarla(donem_kari))
    if donem_kari <= 0:
        b.notlar.append("Dönem kârı bulunmadığından dağıtım yapılamaz.")
        return b
    b.dagitilabilir_kar = yuvarla(donem_kari)
    ucte_bir = yuvarla(donem_kari / 3)
    azami_oran = p["utp_azami_oran"]
    oran = min(utp_orani, azami_oran)
    if utp_orani > azami_oran + 1e-9:
        b.notlar.append("ÜTP oranı kârın en çok 1/3'ü olabilir (3423 s.K. md.1); azami oran uygulandı.")
    b.utp_azami = yuvarla(donem_kari * oran)
    # vadeli hesap faizinin 1/3'ü dağıtılacak kârdan düşülür (DHGM 15.01.2026, m.16)
    b.dagitima_esas = yuvarla(max(0.0, b.utp_azami - faiz_duzeltme / 3))
    b.dagitilan_utp = b.dagitima_esas if dagitilan_utp is None else yuvarla(min(dagitilan_utp, b.dagitima_esas))
    b.dagitilamayan_utp = yuvarla(b.utp_azami - b.dagitilan_utp)
    eksik_sermaye = max(0.0, (tahsis_sermaye or 0) - (odenmis_sermaye or 0))
    b.sermaye_payi = yuvarla(min(ucte_bir, eksik_sermaye))
    if eksik_sermaye <= 0:
        b.notlar.append("Tahsis edilen sermaye tamamen ödenmiş: kârın 2/3'ü Merkez Saymanlığa aktarılır.")
    elif b.sermaye_payi < ucte_bir:
        b.notlar.append("Sermaye payının tahsis tutarını aşan kısmı Merkez Saymanlığa aktarılır.")
    b.merkez_payi = yuvarla(donem_kari - b.dagitilan_utp - b.sermaye_payi)
    if b.dagitilamayan_utp > 0:
        b.notlar.append(f"Dağıtılamayan ÜTP ({para(b.dagitilamayan_utp)}) Merkez Saymanlık payına eklenmiştir.")
    return b


# ---------------------------------------------------------------- ÜTP dağıtımı
@dataclass
class UtpKisi:
    id: int
    ad: str
    gorev: str
    unvan_grubu: int = 3
    bolum_id: int | None = None
    fiili_gun: float = 0.0
    fazla_calisma_saat: float = 0.0
    katki_orani: float = 0.0
    takdir_orani: float = 0.0
    haric: bool = False
    onceki_utp: float = 0.0  # aynı yıl için başka işletmeden alınan (saymanlar, md.5/9)
    idari: float = 0.0
    takdir: float = 0.0
    bolum: float = 0.0
    hesaplanan: float = 0.0
    tavan_asimi: float = 0.0
    odenecek: float = 0.0


@dataclass
class UtpSonuc:
    kisiler: list
    dagitima_esas: float
    idari_havuz: float = 0.0
    takdir_havuz: float = 0.0
    bolum_havuz: float = 0.0
    toplam_odenecek: float = 0.0
    dagitilamayan: float = 0.0
    notlar: list = field(default_factory=list)


def utp_dagit(dagitima_esas: float, kisiler: list[UtpKisi], bolum_gelirleri: dict, bolum_yontemleri: dict,
              p: dict, yuz_yuze_egitim: bool = True) -> UtpSonuc:
    s = UtpSonuc(kisiler=kisiler, dagitima_esas=yuvarla(dagitima_esas))
    aday = [k for k in kisiler if not k.haric]
    dagitilan = 0.0

    komisyon = {k.id for k in aday if k.gorev in (
        "Harcama Yetkilisi (Okul Müdürü)", "Gerçekleştirme Görevlisi (Teknik Md. Yrd.)") or k.gorev in mevzuat.SEF_GOREVLERI}

    def takdir_dagit(havuz):
        nonlocal dagitilan
        uygun = {k.id: k.takdir_orani for k in aday if k.id not in komisyon and k.takdir_orani > 0}
        pay = orantili_dagit(havuz, uygun)
        for k in aday:
            k.takdir = pay.get(k.id, 0.0)
        dagitilan += sum(pay.values())
        if not uygun and havuz > 0:
            s.notlar.append("Takdir payı için komisyonca belirlenmiş personel yok; takdir payı dağıtılmadı.")

    if not yuz_yuze_egitim:
        # md.5/8: %5 takdir, %95 unvan puanı x fiilen çalışılan gün
        s.takdir_havuz = yuvarla(dagitima_esas * p["utp_takdir"])
        kalan = yuvarla(dagitima_esas - s.takdir_havuz)
        takdir_dagit(s.takdir_havuz)
        puanlar = {k.id: p[f"puan_{int(k.unvan_grubu or 5)}"] * k.fiili_gun for k in aday}
        pay = orantili_dagit(kalan, puanlar)
        for k in aday:
            k.bolum = pay.get(k.id, 0.0)
        dagitilan += sum(pay.values())
        s.bolum_havuz = kalan
    else:
        s.idari_havuz = yuvarla(dagitima_esas * p["utp_idari"])
        s.takdir_havuz = yuvarla(dagitima_esas * p["utp_takdir"])
        s.bolum_havuz = yuvarla(dagitima_esas - s.idari_havuz - s.takdir_havuz)

        # idari personel (md.5/3-5)
        gruplar = [
            ("Harcama Yetkilisi (Okul Müdürü)", p["utp_harcama"]),
            ("Gerçekleştirme Görevlisi (Teknik Md. Yrd.)", p["utp_gerceklestirme"]),
            ("Sayman", p["utp_sayman"]),
            ("Diğer İdari Personel", p["utp_diger_idari"]),
        ]
        for gorev, oran in gruplar:
            havuz = yuvarla(dagitima_esas * oran)
            grup = [k for k in aday if k.gorev == gorev]
            if not grup:
                if havuz > 0:
                    s.notlar.append(f"'{gorev}' görevinde personel yok; {para(havuz)} dağıtılamadı.")
                continue
            pay = orantili_dagit(havuz, {k.id: (k.fiili_gun or 1) for k in grup})
            for k in grup:
                k.idari += pay[k.id]
            dagitilan += sum(pay.values())

        # şefler: bölümlerin gelire katkı oranına göre (md.5/4)
        sef_havuz = yuvarla(dagitima_esas * p["utp_sef"])
        sefler = [k for k in aday if k.gorev in mevzuat.SEF_GOREVLERI]
        if sefler:
            sef_bolumleri = {k.bolum_id for k in sefler}
            b_pay = orantili_dagit(sef_havuz, {b: bolum_gelirleri.get(b, 0) for b in sef_bolumleri})
            if not any(b_pay.values()):
                b_pay = orantili_dagit(sef_havuz, {b: 1 for b in sef_bolumleri})
            for b, tutar in b_pay.items():
                grup = [k for k in sefler if k.bolum_id == b]
                pay = orantili_dagit(tutar, {k.id: (k.fiili_gun or 1) for k in grup})
                for k in grup:
                    k.idari += pay[k.id]
                dagitilan += sum(pay.values())
        elif sef_havuz > 0:
            s.notlar.append(f"Bölüm/alan şefi yok; şef payı {para(sef_havuz)} dağıtılamadı.")

        takdir_dagit(s.takdir_havuz)

        # bölüm/alan personeli: bölüm gelir oranı, bölüm içinde seçilen yönteme göre (md.5/7)
        gelirli = {b: g for b, g in bolum_gelirleri.items() if g and g > 0}
        b_pay = orantili_dagit(s.bolum_havuz, gelirli)
        for b, tutar in b_pay.items():
            grup = [k for k in aday if k.bolum_id == b and (k.gorev not in mevzuat.IDARI_GOREVLER or k.gorev in mevzuat.SEF_GOREVLERI)]
            if not grup:
                if tutar > 0:
                    s.notlar.append(f"Bölüm (id={b}) payı {para(tutar)}: bölümde ÜTP'ye esas personel yok.")
                continue
            yontem = bolum_yontemleri.get(b) or mevzuat.UTP_BOLUM_YONTEMLERI[0]
            if yontem.startswith("Fazla"):
                agirlik = {k.id: k.fazla_calisma_saat for k in grup}
            elif yontem.startswith("Fiilen"):
                agirlik = {k.id: k.fiili_gun for k in grup}
            else:
                agirlik = {k.id: k.katki_orani for k in grup}
            pay = orantili_dagit(tutar, agirlik)
            if not any(pay.values()) and tutar > 0:
                s.notlar.append(f"Bölüm (id={b}) içinde dağıtım ölçütü (saat/gün/katkı) girilmemiş.")
            for k in grup:
                k.bolum += pay.get(k.id, 0.0)
            dagitilan += sum(pay.values())
        if not gelirli and s.bolum_havuz > 0:
            s.notlar.append("Bölüm gelirleri bulunamadı; bölüm payı dağıtılamadı.")

    # yıllık tavan (md.4/1, md.5/9)
    tavan = p["asgari_ucret_yillik"]
    for k in kisiler:
        k.hesaplanan = yuvarla(k.idari + k.takdir + k.bolum)
        k.odenecek, k.tavan_asimi = tavan_uygula(k.hesaplanan, k.onceki_utp, tavan)
    s.toplam_odenecek = yuvarla(sum(k.odenecek for k in kisiler))
    s.dagitilamayan = yuvarla(dagitima_esas - s.toplam_odenecek)
    if any(k.tavan_asimi > 0 for k in kisiler):
        s.notlar.append("Yıllık asgari ücret tavanını aşan tutarlar ödenmez; Merkez Saymanlık payına eklenir.")
    return s


def son_odeme_tarihleri(yil: int, ay: int) -> dict:
    """Ay (yil, ay) işlemleri için yasal son tarihler."""
    import calendar
    from datetime import date
    sy, sa = (yil + 1, 1) if ay == 12 else (yil, ay + 1)
    son_gun = calendar.monthrange(sy, sa)[1]
    return {
        "Hazine payı": date(sy, sa, 20),
        "Muhtasar beyan": date(sy, sa, min(26, son_gun)),
        "KDV beyan": date(sy, sa, min(28, son_gun)),
    }


def siparis_kaydi_tahsisi(s: dict, p: dict) -> SiparisTahsis:
    """Veritabanındaki sipariş kaydından (veya aynı alanları taşıyan sözlükten) bedel tahsisi."""
    return siparis_tahsis(
        s.get("sozlesme_bedeli") or 0, s.get("ucret_esasi") or "", p, s.get("malzeme_maliyeti") or 0,
        s.get("iscilik_tutari") if s.get("iscilik_tutari") else None, s.get("kar_orani"), s.get("ogrenci_hakki_orani"),
        s.get("pesinat") or 0, bool(s.get("ogrenci_uygulamasi", 1)), bool(s.get("malzeme_musteriden")),
        s.get("sozlesme_suresi_ay") or 0, bool(s.get("bakanlik_izni")), None)
