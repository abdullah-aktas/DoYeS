"""İşlem kaydı (kim, hangi rolle, ne zaman, hangi bilgisayardan, neyi nasıl değiştirdi) sorgulama ve özetleme."""
from __future__ import annotations

import json

from .db import GIZLI_KOLONLAR, TABLO_ADLARI

# Silinen kaydı tanıtmak için bakılan alanlar (ilk dolu olan kullanılır)
TANITICI_ALANLAR = ("belge_no", "siparis_no", "unvan", "ad_soyad", "ad", "konu", "kullanici_adi", "aciklama")


def _coz(metin) -> dict:
    if not metin:
        return {}
    try:
        veri = json.loads(metin)
        return veri if isinstance(veri, dict) else {}
    except (TypeError, ValueError):
        return {}


def _deger(v) -> str:
    if v is None or v == "":
        return "boş"
    if isinstance(v, float):
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(v)


def tablo_adi(tablo: str | None) -> str:
    return TABLO_ADLARI.get(tablo or "", tablo or "")


def degisiklikler(r: dict) -> list[tuple[str, str, str]]:
    """[(alan, eski, yeni)] — güncellemede değişen alanlar, eklemede girilen, silmede silinen değerler."""
    eski, yeni = _coz(r.get("eski")), _coz(r.get("yeni"))
    alanlar = list(dict.fromkeys(list(yeni) + list(eski)))
    return [(a, "***" if a in GIZLI_KOLONLAR else _deger(eski.get(a)) if a in eski else "",
             "***" if a in GIZLI_KOLONLAR else _deger(yeni.get(a)) if a in yeni else "") for a in alanlar]


def ozet(r: dict, sinir: int = 240) -> str:
    islem = r.get("islem") or ""
    if islem == "Silme":
        eski = _coz(r.get("eski"))
        tanitici = next((str(eski[a]) for a in TANITICI_ALANLAR if eski.get(a)), "")
        metin = f"Silinen kayıt: {tanitici}" if tanitici else "Kayıt silindi"
    elif islem == "Ekleme":
        yeni = _coz(r.get("yeni"))
        tanitici = next((str(yeni[a]) for a in TANITICI_ALANLAR if yeni.get(a)), "")
        metin = f"Yeni kayıt: {tanitici}" if tanitici else "Yeni kayıt"
    elif islem == "Güncelleme":
        d = degisiklikler(r)
        metin = "; ".join(f"{a}: {e} → {y}" for a, e, y in d) if d else "Değişiklik yok (alt kalemler güncellendi)"
    else:
        metin = r.get("detay") or ""
    if r.get("detay") and islem in ("Ekleme", "Güncelleme", "Silme"):
        metin = f"{metin} ({r['detay']})"
    return metin if len(metin) <= sinir else metin[: sinir - 1] + "…"


def kayitlar(db, metin: str = "", kullanici: str | None = None, baslangic: str | None = None, bitis: str | None = None,
             istemci: str | None = None, tablo: str | None = None, kayit_id=None, sinir: int = 2000) -> list[dict]:
    kosul, p = [], []
    if metin:
        a = f"%{metin}%"
        kosul.append("(kullanici LIKE ? OR ad_soyad LIKE ? OR rol LIKE ? OR islem LIKE ? OR tablo LIKE ? OR detay LIKE ? "
                     "OR bilgisayar LIKE ? OR yeni LIKE ? OR eski LIKE ?)")
        p += [a] * 9
    if kullanici:
        kosul.append("kullanici = ?")
        p.append(kullanici)
    if baslangic:
        kosul.append("zaman >= ?")
        p.append(baslangic)
    if bitis:
        kosul.append("zaman <= ?")
        p.append(bitis + " 23:59:59")
    if istemci:
        kosul.append("istemci = ?")
        p.append(istemci)
    if tablo:
        kosul.append("tablo = ?")
        p.append(tablo)
    if kayit_id is not None:
        kosul.append("kayit_id = ?")
        p.append(kayit_id)
    where = (" WHERE " + " AND ".join(kosul)) if kosul else ""
    satirlar = db.q(f"SELECT * FROM islem_log{where} ORDER BY id DESC LIMIT ?", (*p, sinir))
    for r in satirlar:
        r["kim"] = r.get("ad_soyad") or r.get("kullanici") or ""
        r["kayit_turu"] = tablo_adi(r.get("tablo"))
        r["ozet"] = ozet(r)
    return satirlar


def kullanicilar(db) -> list[str]:
    return [r["kullanici"] for r in db.q("SELECT DISTINCT kullanici FROM islem_log WHERE kullanici IS NOT NULL ORDER BY kullanici")]
