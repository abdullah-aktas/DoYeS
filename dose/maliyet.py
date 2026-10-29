"""Ürün maliyet analizi ve mevzuata uygun fiyat tespiti."""
from __future__ import annotations

from typing import Any

from .hesap import (esas_kurallari, oran_yazi, para, yasal_maliyet_dagilimi, yuvarla)

MALZEME_UNSURLARI = ("Direkt İlk Madde ve Malzeme", "Ambalaj / Etiket")
ISCILIK = "Direkt İşçilik (Personel)"
OGRENCI = "Öğrenci Hakkı"
GENEL = "Genel Üretim Gideri"
OTO_ACIKLAMA = {
    ISCILIK: "Yasal üst sınır (otomatik)",
    OGRENCI: "İşçiliğin asgari payı (otomatik)",
    GENEL: "Faaliyet gideri payının kalanı (otomatik)",
}


def _oto_satir(kalem: dict) -> bool:
    return kalem["kalem_turu"] in (ISCILIK, OGRENCI) or (
        kalem["kalem_turu"] == GENEL and kalem.get("aciklama") == OTO_ACIKLAMA[GENEL])


def hesapla(urun: dict, parametreler: dict, kalemler: list[dict], oto: bool,
            hedef_fiyat: float, kar_orani: float, kdv_orani: float,
            hedef_dahil: float | None = None) -> dict:
    satirlar: list[dict[str, Any]] = [
        dict(k, miktar=float(k.get("miktar") or 0), birim_fiyat=float(k.get("birim_fiyat") or 0))
        for k in kalemler
    ]
    hatalar: list[str] = []
    uyarilar: list[str] = []
    oto_bilgi = "Kapalı: işçilik ve giderleri elle giriniz."
    esas = urun.get("ucret_esasi") or ""

    if not oto and hedef_dahil is not None:
        maliyet_mevcut = sum(k["miktar"] * k["birim_fiyat"] for k in satirlar)
        if maliyet_mevcut > 0:
            kdvsiz_hedef = hedef_dahil / (1 + kdv_orani)
            kar_orani = max(0.0, kdvsiz_hedef / maliyet_mevcut - 1)

    if oto:
        malzeme = sum(k["miktar"] * k["birim_fiyat"] for k in satirlar
                      if k["kalem_turu"] in MALZEME_UNSURLARI)
        diger = sum(k["miktar"] * k["birim_fiyat"] for k in satirlar
                    if k["kalem_turu"] not in MALZEME_UNSURLARI and not _oto_satir(k))
        dagilim_fiyati = hedef_dahil / (1 + kdv_orani) if hedef_dahil is not None else hedef_fiyat
        dagilim = yasal_maliyet_dagilimi(dagilim_fiyati, malzeme, esas, parametreler, diger)
        hatalar.extend(dagilim.hatalar)
        uyarilar.extend(dagilim.notlar)
        if not dagilim.hatalar:
            for tur, tutar in ((ISCILIK, dagilim.personel_iscilik),
                               (OGRENCI, dagilim.ogrenci_hakki),
                               (GENEL, dagilim.genel_gider)):
                otomatik_satirlar = [k for k in satirlar if k["kalem_turu"] == tur and _oto_satir(k)]
                if not otomatik_satirlar and tutar:
                    otomatik_satirlar = [{
                        "kalem_turu": tur, "aciklama": OTO_ACIKLAMA[tur],
                        "malzeme_id": None, "miktar": 1.0, "birim_fiyat": 0.0,
                    }]
                    satirlar.append(otomatik_satirlar[0])
                for i, kalem in enumerate(otomatik_satirlar):
                    kalem["aciklama"] = OTO_ACIKLAMA[tur]
                    kalem["miktar"] = 1.0
                    kalem["birim_fiyat"] = tutar if i == 0 else 0.0
            kar_orani = dagilim.kar_orani
            oto_bilgi = (f"İşçilik {para(dagilim.iscilik)} TL (personel {para(dagilim.personel_iscilik)} + "
                         f"öğrenci {para(dagilim.ogrenci_hakki)}) • Faaliyet gideri {para(dagilim.faaliyet)} • "
                         f"Kâr {para(dagilim.kar)} TL")

    birim_maliyet = yuvarla(sum(k["miktar"] * k["birim_fiyat"] for k in satirlar), 4)
    kar = yuvarla(birim_maliyet * kar_orani, 4)
    satis_fiyati = yuvarla(birim_maliyet + kar)
    kdv = yuvarla(satis_fiyati * kdv_orani)
    ozet = {
        "birim_maliyet": yuvarla(birim_maliyet), "kar_orani": kar_orani, "kar": yuvarla(kar),
        "satis_fiyati": satis_fiyati, "kdv_orani": kdv_orani, "kdv": kdv,
        "kdv_dahil": yuvarla(satis_fiyati + kdv),
    }

    iscilik = sum(k["miktar"] * k["birim_fiyat"] for k in satirlar if k["kalem_turu"] in (ISCILIK, OGRENCI))
    ogrenci = sum(k["miktar"] * k["birim_fiyat"] for k in satirlar if k["kalem_turu"] == OGRENCI)
    if iscilik > 0 and not esas.startswith("Fazla") and ogrenci + 0.0001 < iscilik * parametreler["ogrenci_hakki_orani"]:
        mevcut = oran_yazi(ogrenci / iscilik)
        gerekli = oran_yazi(parametreler["ogrenci_hakki_orani"])
        uyarilar.append(f"Öğrenci hakkı işçiliğin en az {gerekli}'u olmalıdır "
                        f"(şu an {mevcut}; Yön. md.8/3).")
    kural = esas_kurallari(esas, parametreler)
    if satis_fiyati > 0 and kural["kar"]:
        kar_payi = kar / satis_fiyati
        if kar + 0.01 < kural["kar"] * satis_fiyati:
            uyarilar.append(f"Satış bedelinin en az {oran_yazi(kural['kar'])}'i kâr olarak ayrılmalıdır "
                            f"({kural['dayanak']}); mevcut kâr payı {oran_yazi(kar_payi)}.")
        faaliyet = sum(k["miktar"] * k["birim_fiyat"] for k in satirlar
                       if k["kalem_turu"] not in MALZEME_UNSURLARI + (ISCILIK, OGRENCI))
        if kural["faaliyet"] and faaliyet + 0.01 < kural["faaliyet"] * satis_fiyati:
            uyarilar.append(f"Siparişte bedelin {oran_yazi(kural['faaliyet'])}'i faaliyet gideri olarak ayrılacaktır; "
                            f"maliyet kartındaki genel giderler şu an {oran_yazi(faaliyet / satis_fiyati)}. "
                            "'Otomatik hesapla' işaretlenirse giderler yasal üst sınırdan doldurulur.")
    if not oto and satis_fiyati > 0 and kural["faaliyet"]:
        malzeme = sum(k["miktar"] * k["birim_fiyat"] for k in satirlar
                      if k["kalem_turu"] in MALZEME_UNSURLARI)
        ust = satis_fiyati * (1 - kural["kar"] - kural["faaliyet"]) - malzeme
        if iscilik + 0.01 < ust:
            uyarilar.append(f"İşçilik ({para(iscilik)} TL) yasal üst sınırın ({para(ust)} TL) altında; "
                            "'Otomatik hesapla' ile üst sınırdan doldurabilirsiniz.")

    for kalem in satirlar:
        kalem["tutar"] = yuvarla(kalem["miktar"] * kalem["birim_fiyat"], 4)
    return {
        "ozet": ozet, "kalemler": satirlar, "hatalar": list(dict.fromkeys(hatalar)),
        "uyarilar": list(dict.fromkeys(uyarilar)), "oto_bilgi": oto_bilgi,
        "kar_orani": kar_orani, "kdv_orani": kdv_orani,
    }
