"""Çalışma Yönergesinin istediği dönemsel raporlar (arayüzden bağımsız)."""
from __future__ import annotations

from . import mevzuat as M
from .hesap import esas_kurallari, yuvarla

CEYREKLER = [("I. Dönem (Ocak-Mart)", (1, 2, 3), "04-05"), ("II. Dönem (Nisan-Haziran)", (4, 5, 6), "07-05"),
             ("III. Dönem (Temmuz-Eylül)", (7, 8, 9), "10-05"), ("IV. Dönem (Ekim-Aralık)", (10, 11, 12), "01-05")]
IDARI_GIDERLER = ("Enerji / Su / Yakıt", "Bakım-Onarım", "Hizmet Alımı", "Genel Yönetim Gideri", "Diğer Gider",
                  "Doğrudan Üretim Gideri")


def _aylar(yil: int, aylar) -> list[str]:
    return [f"{yil}-{a:02d}" for a in aylar]


def uc_aylik_faaliyet(db, yil: int) -> list[dict]:
    """Yönerge md.48: her üç aylık dönemin faaliyet özeti; rapor izleyen ayın 5'ine kadar gönderilir."""
    satirlar = []
    for ad, aylar, son in CEYREKLER:
        donem = _aylar(yil, aylar)
        yer = ",".join("?" * len(aylar))
        tarihli = lambda sql: db.deger(sql.format(yer=yer), donem, 0.0) or 0.0
        aylik = lambda sql: db.deger(sql.format(yer=yer), (yil, *aylar), 0.0) or 0.0
        pb = """SELECT SUM(r.brut) FROM parca_basi_satir r JOIN parca_basi b ON b.id = r.parca_basi_id
                WHERE r.kisi_turu = '{tur}' AND b.yil = ? AND b.ay IN ({{yer}})"""
        satirlar.append({
            "donem": ad, "son_gun": f"{yil + 1 if son.startswith('01') else yil}-{son}",
            "siparis": tarihli("SELECT COUNT(*) FROM siparis WHERE durum != 'İptal' AND substr(tarih, 1, 7) IN ({yer})"),
            "tamamlanan": tarihli("SELECT COUNT(*) FROM siparis WHERE substr(kabul_tarihi, 1, 7) IN ({yer})"),
            "satis": tarihli("SELECT SUM(matrah) FROM fatura WHERE tur = 'Satış' AND iptal = 0 AND substr(tarih, 1, 7) IN ({yer})"),
            "tahsilat": tarihli("SELECT SUM(tutar) FROM kasa_banka WHERE yon = 'Giriş' AND substr(tarih, 1, 7) IN ({yer})"),
            "alis": tarihli("SELECT SUM(matrah) FROM fatura WHERE tur = 'Alış' AND iptal = 0 AND substr(tarih, 1, 7) IN ({yer})"),
            "parca_basi": aylik(pb.format(tur="Personel")),
            "ogrenci": aylik(pb.format(tur="Öğrenci")),
            "fazla": aylik("SELECT SUM(brut) FROM fazla_calisma WHERE yil = ? AND ay IN ({yer})"),
            "hazine": aylik("SELECT SUM(tutar) FROM hazine_payi WHERE yil = ? AND ay IN ({yer})"),
        })
    return satirlar


def idari_masraf_karsiligi(db, yil: int) -> list[dict]:
    """Yönerge md.11: işletme ve idari masraflar, satışlardan ayrılan faaliyet gideri karşılığını aşamaz
    ("karşılıkta para yoksa harcama yapılamaz")."""
    p = db.parametreler(yil)
    satirlar, kumulatif = [], 0.0
    for ay in range(1, 13):
        d = f"{yil}-{ay:02d}"
        karsilik = 0.0
        for k in db.q("""SELECT k.tutar, s.ucret_esasi s_esas, u.ucret_esasi u_esas
                         FROM fatura_kalem k JOIN fatura f ON f.id = k.fatura_id LEFT JOIN siparis s ON s.id = f.siparis_id
                         LEFT JOIN urun u ON u.id = k.urun_id
                         WHERE f.tur = 'Satış' AND f.iptal = 0 AND substr(f.tarih, 1, 7) = ?""", (d,)):
            esas = k["s_esas"] or k["u_esas"] or M.UCRET_ESASLARI[0]
            karsilik += (k["tutar"] or 0) * esas_kurallari(esas, p)["faaliyet"]
        karsilik = yuvarla(karsilik)
        yer = ",".join("?" * len(IDARI_GIDERLER))
        gider = db.deger(f"""SELECT SUM(matrah) FROM fatura WHERE tur = 'Alış' AND iptal = 0 AND siparis_id IS NULL
                             AND gider_turu IN ({yer}) AND substr(tarih, 1, 7) = ?""", (*IDARI_GIDERLER, d), 0.0) or 0.0
        hazine = db.deger("SELECT SUM(tutar) FROM hazine_payi WHERE yil = ? AND ay = ?", (yil, ay), 0.0) or 0.0
        harcama = yuvarla(gider + hazine)
        kumulatif = yuvarla(kumulatif + karsilik - harcama)
        satirlar.append({"ay": M.AYLAR[ay - 1], "karsilik": karsilik, "gider": yuvarla(gider), "hazine": yuvarla(hazine),
                         "harcama": harcama, "kalan": kumulatif,
                         "durum": "KARŞILIK AŞILDI" if kumulatif < -0.009 else ("" if karsilik or harcama else "-")})
    return satirlar
