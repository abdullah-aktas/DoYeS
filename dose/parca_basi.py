"""Parça başı bordro verileri ve hesaplama kuralları."""
from __future__ import annotations

import calendar

from .denetim import puantaj_yaz
from .hesap import (orantili_dagit, para, parca_basi_tavani, siparis_kaydi_tahsisi, tavan_uygula,
                    ucret_kesintileri, yuvarla)


def kisi_bilgisi(db, kisi_turu: str, kisi_id: int) -> dict:
    if kisi_turu == "Personel":
        kayit = db.q1(
            """SELECT ad_soyad ad, hizmet_sinifi, iban, tckn, 1 muvafakat, NULL sinif, bolum_id
               FROM personel WHERE id = ?""", (kisi_id,))
    else:
        kayit = db.q1(
            """SELECT ad_soyad ad, NULL hizmet_sinifi, iban, tckn, veli_muvafakat muvafakat, sinif, bolum_id
               FROM ogrenci WHERE id = ?""", (kisi_id,))
    return kayit or {"ad": "?", "hizmet_sinifi": None, "iban": None, "tckn": None,
                     "muvafakat": 0, "sinif": None, "bolum_id": None}


def ay_ici_diger_brut(db, yil: int, ay: int, kisi_turu: str, kisi_id: int,
                      haric_pb_id: int | None) -> float:
    return db.deger(
        """SELECT SUM(r.brut) FROM parca_basi_satir r JOIN parca_basi pb ON pb.id = r.parca_basi_id
           WHERE pb.yil = ? AND pb.ay = ? AND r.kisi_turu = ? AND r.kisi_id = ? AND pb.id != ?""",
        (yil, ay, kisi_turu, kisi_id, haric_pb_id or 0), 0.0)


def onceki_kumulatif(db, yil: int, ay: int, kisi_turu: str, kisi_id: int,
                     haric_pb_id: int | None) -> float:
    pb = db.deger(
        """SELECT SUM(r.brut) FROM parca_basi_satir r JOIN parca_basi p ON p.id = r.parca_basi_id
           WHERE p.yil = ? AND (p.ay < ? OR (p.ay = ? AND p.id < ?))
           AND r.kisi_turu = ? AND r.kisi_id = ? AND p.id != ?""",
        (yil, ay, ay, haric_pb_id or 10**9, kisi_turu, kisi_id, haric_pb_id or 0), 0.0)
    fazla = 0.0
    if kisi_turu == "Personel":
        fazla = db.deger("SELECT SUM(brut) FROM fazla_calisma WHERE yil = ? AND ay < ? AND personel_id = ?",
                         (yil, ay, kisi_id), 0.0)
    return yuvarla((pb or 0.0) + (fazla or 0.0))


def hesapla(db, veri: dict, parametreler: dict, pb_id: int | None = None) -> dict:
    yil, ay = veri["yil"], veri["ay"]
    siparis = db.q1("SELECT * FROM siparis WHERE id = ?", (veri.get("siparis_id"),)) if veri.get("siparis_id") else None
    hatalar: list[str] = []
    uyarilar: list[str] = []
    if not siparis:
        hatalar.append("Sipariş seçiniz.")
    elif siparis["durum"] in ("İptal", "Talep Alındı", "Keşif / İş Planı", "Teklif", "Proforma İletildi"):
        hatalar.append("Parça başı bordro için sözleşmesi imzalanmış veya geçici kabulü yapılmış sipariş seçilmelidir.")

    kalan_iscilik = onceki_iscilik = faturalanan_iscilik = tahsil = 0.0
    siparis_bilgisi = None
    if siparis:
        tahsis = siparis_kaydi_tahsisi(dict(siparis), parametreler)
        onceki_iscilik = db.deger(
            "SELECT SUM(kabul_edilen_iscilik) FROM parca_basi WHERE siparis_id = ? AND id != ?",
            (siparis["id"], pb_id or 0), 0.0) or 0.0
        kalan_iscilik = yuvarla(tahsis.iscilik - onceki_iscilik)
        tahsil = db.deger(
            """SELECT SUM(tutar) FROM kasa_banka WHERE yon = 'Giriş' AND
               (siparis_id = ? OR fatura_id IN (SELECT id FROM fatura WHERE siparis_id = ? AND iptal = 0))""",
            (siparis["id"], siparis["id"]), 0.0) or 0.0
        faturalanan = db.deger(
            "SELECT SUM(matrah) FROM fatura WHERE siparis_id = ? AND tur = 'Satış' AND iptal = 0",
            (siparis["id"],), 0.0) or 0.0
        bedel = siparis["sozlesme_bedeli"] or 0
        faturalanan_iscilik = yuvarla(tahsis.iscilik * min(faturalanan / bedel, 1)) if bedel else 0.0
        siparis_bilgisi = {
            "id": siparis["id"], "siparis_no": siparis["siparis_no"], "konu": siparis["konu"],
            "durum": siparis["durum"], "sozlesme_bedeli": bedel,
            "toplam_iscilik": tahsis.iscilik, "onceki_iscilik": onceki_iscilik,
            "kalan_iscilik": kalan_iscilik, "faturalanan": faturalanan,
            "faturalanan_iscilik": faturalanan_iscilik, "tahsil_edilen": tahsil,
            "kabul_tarihi": siparis["kabul_tarihi"],
        }

    kabul = veri["kabul_edilen_iscilik"]
    ogrenci_orani = veri["ogrenci_orani"]
    havuz = {
        "Öğrenci": yuvarla(kabul * ogrenci_orani),
        "Personel": yuvarla(kabul - yuvarla(kabul * ogrenci_orani)),
    }
    gruplar = {
        tur: {i: s["katki"] for i, s in enumerate(veri["satirlar"]) if s["kisi_turu"] == tur}
        for tur in ("Personel", "Öğrenci")
    }
    paylar = {}
    for tur, grup in gruplar.items():
        if grup and not any(grup.values()) and havuz[tur] > 0:
            hatalar.append(f"{tur} katkı oranları girilmemiş.")
        if not grup and havuz[tur] > 0:
            uyarilar.append(f"{tur} bulunmadığından {para(havuz[tur])} TL dağıtılamayacak.")
        paylar.update(orantili_dagit(havuz[tur], grup))

    satir_sonuclari = []
    puantajli = any(s.get("puantaj") for s in veri["satirlar"])
    gun_sayisi = calendar.monthrange(yil, ay)[1]
    kabul_gunu = None
    if siparis and siparis.get("kabul_tarihi") and str(siparis["kabul_tarihi"])[:7] == f"{yil}-{ay:02d}":
        kabul_gunu = int(str(siparis["kabul_tarihi"])[8:10])

    for i, satir in enumerate(veri["satirlar"]):
        tur, kisi_id = satir["kisi_turu"], satir["kisi_id"]
        bilgi = kisi_bilgisi(db, tur, kisi_id)
        if bilgi["ad"] == "?":
            hatalar.append(f"{tur} kaydı bulunamadı (#{kisi_id}).")
            continue
        onceki = satir.get("onceki_kumulatif")
        if onceki is None:
            onceki = onceki_kumulatif(db, yil, ay, tur, kisi_id, pb_id)
        puantaj = {int(g): float(v) for g, v in (satir.get("puantaj") or {}).items() if v}
        if any(g < 1 or g > gun_sayisi for g in puantaj):
            hatalar.append(f"{bilgi['ad']}: puantaj günleri seçilen ayın sınırları içinde olmalıdır.")
        hesaplanan = paylar.get(i, 0.0)
        tavan = parca_basi_tavani(tur, bilgi["hizmet_sinifi"], parametreler)
        diger = ay_ici_diger_brut(db, yil, ay, tur, kisi_id, pb_id)
        brut, asim = tavan_uygula(hesaplanan, diger, tavan)
        kesinti = ucret_kesintileri(brut, onceki, ay, parametreler, ogrenci=tur == "Öğrenci")
        satir_sonucu = {
            "kisi_turu": tur, "kisi_id": kisi_id, "ad_soyad": bilgi["ad"],
            "hizmet_sinifi": bilgi["hizmet_sinifi"], "sinif": bilgi["sinif"],
            "iban": bilgi["iban"], "tckn": bilgi["tckn"], "muvafakat": bool(bilgi["muvafakat"]),
            "katki": satir["katki"], "hesaplanan": hesaplanan, "tavan": tavan,
            "ay_ici_diger": diger, "brut": brut, "tavan_asimi": asim,
            "onceki_kumulatif": onceki, "gelir_vergisi": kesinti.gelir_vergisi,
            "damga_vergisi": kesinti.damga_vergisi, "sgk": kesinti.sgk, "net": kesinti.net,
            "puantaj": puantaj, "puantaj_json": puantaj_yaz(puantaj),
        }
        satir_sonuclari.append(satir_sonucu)

        if tur == "Öğrenci" and not bilgi["muvafakat"]:
            hatalar.append(f"{bilgi['ad']}: veli muvafakatnamesi yok (Yön. md.8/6).")
        if asim > 0:
            uyarilar.append(f"{bilgi['ad']}: aylık tavan ({para(tavan)} TL) aşıldı, {para(asim)} TL ödenmeyecek.")
        if not bilgi["iban"]:
            uyarilar.append(f"{bilgi['ad']}: IBAN bilgisi eksik.")
        if tur == "Öğrenci" and str(bilgi.get("sinif") or "").strip().startswith("9"):
            uyarilar.append(f"{bilgi['ad']}: 9. sınıf öğrencisi; ilk sınıf öğrencilerine ödeme yapılmaz "
                            "(Çalışma Yönergesi md.42/f).")
        if puantajli:
            puantaj_toplami = sum(puantaj.values())
            if abs(puantaj_toplami - satir["katki"]) > 0.0005:
                uyarilar.append(f"{bilgi['ad']}: katkı ({satir['katki']:g}) puantaj toplamından "
                                f"({puantaj_toplami:g}) farklı; dağıtım puantajla belgelenmelidir (Yön. md.8/8).")
            if kabul_gunu and any(g > kabul_gunu for g in puantaj):
                uyarilar.append(f"{bilgi['ad']}: geçici kabul tarihinden ({kabul_gunu}. gün) sonraki günlere üretim "
                                "girilmiş; yalnız kabulü yapılan iş ödenir (Yön. md.8/8-a).")
        if tur == "Personel" and siparis and db.deger(
                "SELECT COUNT(*) FROM fazla_calisma WHERE personel_id = ? AND siparis_id = ?",
                (kisi_id, siparis["id"]), 0):
            hatalar.append(f"{bilgi['ad']}: aynı sipariş için fazla çalışma ücreti kaydı var (Yön. md.8/7).")

    if not veri["satirlar"]:
        hatalar.append("Bordroda en az bir kişi olmalıdır.")
    if ogrenci_orani + 1e-9 < parametreler["ogrenci_hakki_orani"]:
        hatalar.append(f"Öğrenci hakkı işçiliğin en az %{parametreler['ogrenci_hakki_orani'] * 100:.0f}'i olmalıdır "
                       "(Yön. md.8/3).")
    if siparis:
        if kabul > kalan_iscilik + 0.009:
            hatalar.append(f"Kabul edilen işçilik, siparişin dağıtılmamış işçilik tutarını ({para(kalan_iscilik)} TL) aşıyor.")
        if not siparis["kabul_tarihi"] and siparis["durum"] not in (
                "Tamamlandı (Geçici Kabul)", "Faturalandı", "Kapandı"):
            hatalar.append("Siparişin geçici muayene ve kabulü yapılmamış; parça başı ücret yalnız kabulü yapılan işçilikten ödenir.")
        elif siparis["kabul_tarihi"] and str(siparis["kabul_tarihi"])[:7] > f"{yil}-{ay:02d}":
            uyarilar.append(f"Geçici kabul tarihi ({siparis['kabul_tarihi']}) bordro ayından sonra; ödeme kabul ayına alınmalıdır.")
        if kabul > 0 and onceki_iscilik + kabul > faturalanan_iscilik + 0.009:
            uyarilar.append(
                f"Bu bordroyla birlikte dağıtılan işçilik ({para(onceki_iscilik + kabul)} TL), faturalanan kısmın "
                f"işçilik payını ({para(faturalanan_iscilik)} TL) aşıyor; teslim edilen kısım için önce fatura kesiniz.")
        if tahsil + 0.009 < (siparis["sozlesme_bedeli"] or 0) * (1 + (siparis["kdv_orani"] or 0)):
            uyarilar.append("İş bedelinin tamamı henüz tahsil edilmemiş; ödeme planlamasında dikkate alınız.")

    totals = {
        name: yuvarla(sum(s[name] for s in satir_sonuclari))
        for name in ("hesaplanan", "brut", "tavan_asimi", "gelir_vergisi", "damga_vergisi", "sgk", "net")
    }
    return {
        "siparis": siparis_bilgisi,
        "ogrenci_hakki_havuzu": havuz["Öğrenci"],
        "personel_havuzu": havuz["Personel"],
        "satirlar": satir_sonuclari,
        "toplamlar": totals,
        "hatalar": list(dict.fromkeys(hatalar)),
        "uyarilar": list(dict.fromkeys(uyarilar)),
    }
