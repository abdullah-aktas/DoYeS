"""Yıl sonu kâr bölüşümü ve ÜTP için ortak API/domain işlemleri."""
from __future__ import annotations

from typing import Any

from . import mevzuat, muhasebe, onay
from .hesap import UtpKisi, parca_basi_gun, ucret_kesintileri, utp_dagit, yil_sonu_bolusum, yuvarla


def _aktif_kisiler(db, yil: int) -> list[dict]:
    kayitli = db.q(
        """SELECT p.id, p.ad_soyad, p.dose_gorevi, p.unvan_grubu, p.bolum_id, b.ad bolum,
                  u.fiili_gun, u.fazla_calisma_saat, u.katki_orani, u.takdir_orani, u.haric,
                  u.haric_neden, u.onceki_kumulatif, u.diger_isletme_utp
           FROM utp_kisi u JOIN personel p ON p.id = u.personel_id
           LEFT JOIN bolum b ON b.id = p.bolum_id WHERE u.yil = ?
           ORDER BY p.dose_gorevi, p.ad_soyad""", (yil,))
    var = {r["id"] for r in kayitli}
    yeni = db.q(
        """SELECT p.id, p.ad_soyad, p.dose_gorevi, p.unvan_grubu, p.bolum_id, b.ad bolum
           FROM personel p LEFT JOIN bolum b ON b.id = p.bolum_id
           WHERE p.aktif = 1 ORDER BY p.dose_gorevi, p.ad_soyad""")
    for r in yeni:
        if r["id"] not in var:
            kayitli.append(r)
    kayitli.sort(key=lambda r: (r.get("dose_gorevi") or "", r.get("ad_soyad") or ""))
    for row in kayitli:
        row["unvan_grubu"] = row.get("unvan_grubu") or mevzuat.GOREV_VARSAYILAN_UNVAN_GRUBU.get(
            row.get("dose_gorevi"), 5)
    return kayitli


def _ozet(db, yil: int) -> dict:
    gelir_gider = muhasebe.gelir_tablosu(yil)
    hasilat = muhasebe.yillik_brut_hasilat(yil)
    p = db.parametreler(yil)
    shcek_kayitli = db.deger(
        "SELECT COUNT(*) FROM yevmiye WHERE kaynak = 'SHCEK' AND kaynak_id = ?", (yil,), 0)
    kar_onerilen = yuvarla(gelir_gider["kar"] - (0 if shcek_kayitli else hasilat * p["shcek_orani"]))
    kurum = db.kurum()
    ys = db.q1("SELECT * FROM yil_sonu WHERE yil = ?", (yil,)) or {}
    onay_durumu = onay.durum("Yıl Sonu", yil)
    kilitli = ys.get("durum") == "Onaylandı" or onay_durumu["durum"] == onay.BEKLIYOR
    return {
        "yil": yil, "gelir_gider": gelir_gider, "hasilat": hasilat, "kar_onerilen": kar_onerilen,
        "tahsis_sermaye": kurum.get("tahsis_sermaye") or 0, "odenmis_sermaye": kurum.get("odenmis_sermaye") or 0,
        "yuz_yuze_egitim": bool(kurum.get("yuz_yuze_egitim", 1)), "kayit": ys,
        "onay": {**onay_durumu, "durum_metni": onay.durum_metni(onay_durumu)},
        "kilitli": kilitli, "kisiler": _aktif_kisiler(db, yil),
        "parametreler": p, "odeme_parametreleri": db.parametreler(yil + 1),
        "bolum_yontemleri": {r["id"]: r["utp_yontemi"] for r in db.q("SELECT id, utp_yontemi FROM bolum")},
    }


def yil_sonu_verisi(db, yil: int, yazabilir: bool) -> dict:
    veri = _ozet(db, yil)
    veri["yazabilir"] = yazabilir and not veri["kilitli"]
    return veri


def saat_verilerini_getir(db, yil: int) -> dict[int, float]:
    p = db.parametreler(yil)
    sonuc = {}
    for kisi in _aktif_kisiler(db, yil):
        fc = db.deger(
            "SELECT SUM(saat) FROM fazla_calisma WHERE yil = ? AND personel_id = ? AND durum = 'Onaylandı'",
            (yil, kisi["id"]), 0.0)
        parca_basi = db.deger(
            """SELECT SUM(r.brut) FROM parca_basi_satir r JOIN parca_basi p ON p.id = r.parca_basi_id
               WHERE p.yil = ? AND p.durum = 'Onaylandı' AND r.kisi_turu = 'Personel' AND r.kisi_id = ?""",
            (yil, kisi["id"]), 0.0)
        saat = p["fazla_calisma_saat_ucreti"]
        pb_saat = parca_basi_gun(parca_basi, saat) * 8 if saat else 0.0
        sonuc[kisi["id"]] = yuvarla(fc + pb_saat, 1)
    return sonuc


def hesapla(db, yil: int, istek: dict[str, Any]) -> dict:
    """Masaüstünün ortak hesap fonksiyonlarıyla doğrula ve dağıtım sonucunu üret."""
    veri = _ozet(db, yil)
    if veri["kilitli"]:
        raise ValueError("Onay bekleyen veya kesinleşmiş yıl sonu dağıtımı düzenlenemez.")
    bilanco_kari = yuvarla(istek["donem_kari"])
    faiz = yuvarla(istek["faiz_duzeltme"])
    oran = 1 / 3 if abs(istek["utp_orani"] - 1 / 3) < 1e-4 else istek["utp_orani"]
    p = veri["parametreler"]
    once = yil_sonu_bolusum(bilanco_kari, veri["tahsis_sermaye"], veri["odenmis_sermaye"], oran, p, None, faiz)
    aktif = {k["id"]: k for k in veri["kisiler"]}
    girdiler = istek["kisiler"]
    ids = [k["personel_id"] for k in girdiler]
    if len(ids) != len(set(ids)):
        raise ValueError("Aynı personel dağıtım listesinde birden fazla kez bulunamaz.")
    if set(ids) != set(aktif):
        raise ValueError("Personel listesi güncel değil; ekranı yenileyip tekrar deneyiniz.")

    kisiler = []
    girisler = {k["personel_id"]: k for k in girdiler}
    for pid, row in girisler.items():
        per = aktif[pid]
        gorev = per.get("dose_gorevi") or ""
        if gorev != "Sayman" and row["diger_isletme_utp"]:
            raise ValueError(f"{per['ad_soyad']}: diğer işletme ÜTP tutarı yalnız Sayman için girilebilir.")
        varsayilan_unvan = mevzuat.GOREV_VARSAYILAN_UNVAN_GRUBU.get(gorev, 5)
        kisiler.append(UtpKisi(
            id=pid, ad=per["ad_soyad"], gorev=gorev,
            unvan_grubu=row["unvan_grubu"] or per.get("unvan_grubu") or varsayilan_unvan,
            bolum_id=per.get("bolum_id"), fiili_gun=row["fiili_gun"],
            fazla_calisma_saat=row["fazla_calisma_saat"], katki_orani=row["katki_orani"],
            takdir_orani=row["takdir_orani"] / 100, haric=row["haric"],
            onceki_utp=row["diger_isletme_utp"]))
    dagitim = utp_dagit(once.dagitima_esas, kisiler, muhasebe.bolum_gelirleri(yil),
                        veri["bolum_yontemleri"], p, veri["yuz_yuze_egitim"])
    bolusum = yil_sonu_bolusum(
        bilanco_kari, veri["tahsis_sermaye"], veri["odenmis_sermaye"], oran, p,
        dagitim.toplam_odenecek, faiz)
    hatalar, uyarilar = [], list(bolusum.notlar) + list(dagitim.notlar)
    if bilanco_kari <= 0:
        hatalar.append("Bilanço kârı yok; ÜTP dağıtılamaz.")
    if oran > p["utp_azami_oran"] + 1e-9:
        hatalar.append("ÜTP oranı 1/3'ü aşamaz.")
    for row in girdiler:
        per = aktif[row["personel_id"]]
        if row["haric"] and not row["haric_neden"].strip():
            uyarilar.append(f"{per['ad_soyad']}: hariç tutma nedeni yazılmalıdır (md.6).")
    komisyon = [k.ad for k in kisiler if k.takdir_orani > 0 and
                (k.gorev in mevzuat.SEF_GOREVLERI or k.gorev.startswith(("Harcama", "Gerçekleştirme")))]
    if komisyon:
        uyarilar.append("Takdir komisyonu üyeleri takdir payından yararlanamaz (md.5/6): " + ", ".join(komisyon))
    if abs(bilanco_kari - veri["kar_onerilen"]) > 1 and veri["gelir_gider"]["toplam_gelir"]:
        uyarilar.append("Esas alınan bilanço kârı yardımcı defterdeki kârdan farklı; BKMYBS bilançosunu esas alınız.")
    uyarilar.append("Yıl içinde 30 günden fazla okul dışında görevlendirilenler ve DÖSE çalışmalarına fiilen katılmayanlar "
                    "hariç tutulmalıdır (md.6).")
    kisiler_sonuc = []
    kayitlar = []
    for k in kisiler:
        row = girisler[k.id]
        kesinti = ucret_kesintileri(k.odenecek, row["onceki_kumulatif"], 2, veri["odeme_parametreleri"])
        kisiler_sonuc.append({
            "personel_id": k.id, "ad_soyad": k.ad, "gorev": k.gorev, "bolum_id": k.bolum_id,
            "unvan_grubu": k.unvan_grubu, "idari_pay": k.idari, "takdir_pay": k.takdir,
            "bolum_pay": k.bolum, "hesaplanan": k.hesaplanan, "tavan_asimi": k.tavan_asimi,
            "brut": k.odenecek, "gelir_vergisi": kesinti.gelir_vergisi,
            "damga_vergisi": kesinti.damga_vergisi, "net": kesinti.net,
        })
        kayitlar.append((row, k, kesinti))
    return {
        "ozet": {
            "donem_kari": bilanco_kari, "faiz_duzeltme": faiz, "utp_orani": oran,
            "utp_azami": bolusum.utp_azami, "dagitima_esas": bolusum.dagitima_esas,
            "dagitilan_utp": bolusum.dagitilan_utp, "sermaye_payi": bolusum.sermaye_payi,
            "merkez_payi": bolusum.merkez_payi,
            "shcek": yuvarla(veri["hasilat"] * p["shcek_orani"]),
            "yontem": "Yön. md.5/2-7" if veri["yuz_yuze_egitim"] else "Yön. md.5/8",
            "toplam_gelir": veri["gelir_gider"]["toplam_gelir"],
            "toplam_gider": veri["gelir_gider"]["toplam_gider"],
        },
        "kisiler": kisiler_sonuc, "hatalar": hatalar, "uyarilar": uyarilar,
        "_kayitlar": kayitlar,
    }


def kaydet(db, yil: int, sonuc: dict) -> None:
    ozet = sonuc["ozet"]
    with db.islem():
        eski = db.q1("SELECT durum FROM yil_sonu WHERE yil = ?", (yil,)) or {}
        if eski.get("durum") == "Onaylandı" or onay.durum("Yıl Sonu", yil)["durum"] == onay.BEKLIYOR:
            raise ValueError("Onay bekleyen veya kesinleşmiş yıl sonu dağıtımı düzenlenemez.")
        db.ex(
            """INSERT INTO yil_sonu
               (yil, toplam_gelir, toplam_gider, donem_kari, faiz_duzeltme, utp_orani, dagitima_esas,
                dagitilan_utp, sermaye_payi, merkez_payi, shcek, yontem, durum)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(yil) DO UPDATE SET toplam_gelir=excluded.toplam_gelir,
               toplam_gider=excluded.toplam_gider, donem_kari=excluded.donem_kari,
               faiz_duzeltme=excluded.faiz_duzeltme, utp_orani=excluded.utp_orani,
               dagitima_esas=excluded.dagitima_esas, dagitilan_utp=excluded.dagitilan_utp,
               sermaye_payi=excluded.sermaye_payi, merkez_payi=excluded.merkez_payi,
               shcek=excluded.shcek, yontem=excluded.yontem, durum=excluded.durum""",
            (yil, ozet["toplam_gelir"], ozet["toplam_gider"], ozet["donem_kari"], ozet["faiz_duzeltme"],
             ozet["utp_orani"], ozet["dagitima_esas"], ozet["dagitilan_utp"], ozet["sermaye_payi"],
             ozet["merkez_payi"], ozet["shcek"], ozet["yontem"], eski.get("durum") or "Taslak"))
        db.ex("DELETE FROM utp_kisi WHERE yil = ?", (yil,))
        for row, k, kesinti in sonuc["_kayitlar"]:
            db.ekle("utp_kisi", {
                "yil": yil, "personel_id": k.id, "fiili_gun": row["fiili_gun"],
                "fazla_calisma_saat": row["fazla_calisma_saat"], "katki_orani": row["katki_orani"],
                "takdir_orani": row["takdir_orani"] / 100, "haric": int(row["haric"]),
                "haric_neden": row["haric_neden"].strip() or None, "idari_pay": k.idari, "takdir_pay": k.takdir,
                "bolum_pay": k.bolum, "hesaplanan": k.hesaplanan, "tavan_asimi": k.tavan_asimi,
                "brut": k.odenecek, "onceki_kumulatif": row["onceki_kumulatif"],
                "gelir_vergisi": kesinti.gelir_vergisi, "damga_vergisi": kesinti.damga_vergisi,
                "net": kesinti.net, "diger_isletme_utp": row["diger_isletme_utp"],
            }, log=False)
            db.guncelle("personel", k.id, {"unvan_grubu": k.unvan_grubu}, log=False)
        db.log("Yıl sonu kaydı", "yil_sonu", yil)
    sonuc.pop("_kayitlar", None)
