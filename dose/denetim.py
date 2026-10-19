"""Veritabanına bakan mevzuat denetimleri (kayıt ekranları ile onay akışı aynı kuralları kullanır)."""
from __future__ import annotations

import json

from . import mevzuat as M
from .hesap import (ay_azami_fazla_calisma, fazla_calisma_gun_hatalari, para, siparis_kaydi_tahsisi, takvim_tanimli,
                    yuvarla)


def puantaj_coz(metin) -> dict[int, float]:
    if isinstance(metin, dict):
        return {int(g): float(v) for g, v in metin.items() if v}
    try:
        return {int(g): float(v) for g, v in json.loads(metin or "{}").items() if v}
    except (TypeError, ValueError, AttributeError):
        return {}


def puantaj_yaz(puantaj: dict[int, float]) -> str | None:
    p = {str(g): v for g, v in sorted(puantaj.items()) if v}
    return json.dumps(p) if p else None


def siparis_iscilik_kullanimi(db, siparis_id: int, haric_fc_id: int | None = None) -> float:
    """Siparişin işçiliğinden fazla çalışma ve parça başı (öğrenci hakkı dahil) olarak dağıtılan brüt toplam."""
    fc = db.deger("SELECT SUM(brut) FROM fazla_calisma WHERE siparis_id = ? AND id != ?", (siparis_id, haric_fc_id or 0), 0.0)
    pb = db.deger("""SELECT SUM(r.brut) FROM parca_basi_satir r JOIN parca_basi p ON p.id = r.parca_basi_id
                     WHERE p.siparis_id = ?""", (siparis_id,), 0.0)
    return yuvarla((fc or 0) + (pb or 0))


def fazla_calisma_denetimi(db, v: dict, kid: int | None = None, p: dict | None = None) -> tuple[list[str], list[str]]:
    """v: yil, ay, personel_id, siparis_id, saat, saat_ucreti, puantaj. (hatalar, uyarılar) döndürür."""
    yil, ay = int(v["yil"]), int(v["ay"])
    p = p or db.parametreler(yil)
    hatalar, uyarilar = [], []
    pid, sid = v.get("personel_id"), v.get("siparis_id")
    saat, ucret = float(v.get("saat") or 0), float(v.get("saat_ucreti") or 0)
    brut = yuvarla(saat * ucret)
    if saat <= 0:
        hatalar.append("Fiilen çalışılan saat girilmemiş.")
    azami_ucret = float(p.get("fazla_calisma_azami_ucret") or 0)
    if azami_ucret and ucret > azami_ucret + 1e-9:
        hatalar.append(f"Saat ücreti ({para(ucret)} TL) azami tutarı ({para(azami_ucret)} TL) aşıyor (Bütçe K cetveli III-3).")

    per = db.q1("SELECT * FROM personel WHERE id = ?", (pid,)) if pid else None
    if per:
        if (per.get("hizmet_sinifi") or "") == "Yardımcı Hizmetler":
            hatalar.append("Yardımcı hizmetler sınıfı personele döner sermayeden fazla çalışma ücreti ödenemez (Bütçe K cetveli III-3).")
        unvan = ((per.get("kadro_unvani") or "") + " " + (per.get("dose_gorevi") or "")).lower()
        if "şoför" in unvan or "sofor" in unvan:
            hatalar.append("Şoförlere döner sermayeden fazla çalışma ücreti ödenemez (Bütçe K cetveli III-3).")
        if sid and db.deger("""SELECT COUNT(*) FROM parca_basi_satir r JOIN parca_basi b ON b.id = r.parca_basi_id
                               WHERE b.siparis_id = ? AND r.kisi_turu = 'Personel' AND r.kisi_id = ?""", (sid, pid), 0):
            hatalar.append("Bu personele aynı sipariş için parça başı ücret ödenmiş; fazla çalışma ücreti ödenemez (Yön. md.8/7).")
        elif db.deger("""SELECT COUNT(*) FROM parca_basi_satir r JOIN parca_basi b ON b.id = r.parca_basi_id
                         WHERE b.yil = ? AND b.ay = ? AND r.kisi_turu = 'Personel' AND r.kisi_id = ?""", (yil, ay, pid), 0):
            if (per.get("dose_gorevi") or "") in M.IDARI_GOREVLER:
                hatalar.append("İdari görevli personele aynı ay içinde hem parça başı hem fazla çalışma ücreti ödenemez (Yön. md.8/7).")
            else:
                uyarilar.append("Personel bu ay parça başı ücret de alıyor; fazla çalışmanın farklı bir iş için ve olağan çalışma saatleri "
                                "dışında yapıldığından emin olunuz (Yön. md.8/7).")

    puantaj = puantaj_coz(v.get("puantaj"))
    diger = db.q("SELECT saat, puantaj FROM fazla_calisma WHERE yil = ? AND ay = ? AND personel_id = ? AND id != ?",
                 (yil, ay, pid or -1, kid or 0)) if pid else []
    diger_saat = sum(r["saat"] or 0 for r in diger)
    if puantaj:
        if abs(sum(puantaj.values()) - saat) > 0.01:
            hatalar.append(f"Puantaj toplamı ({sum(puantaj.values()):g} saat) çalışılan saatle ({saat:g}) uyuşmuyor.")
        gunluk = dict(puantaj)
        for r in diger:
            for g, s in puantaj_coz(r["puantaj"]).items():
                gunluk[g] = gunluk.get(g, 0) + s
        hatalar += [(h[:-1] + " — personelin bu aydaki bütün kayıtları birlikte." if diger else h)
                    for h in fazla_calisma_gun_hatalari(yil, ay, gunluk, p)]
    elif saat > 0:
        azami = ay_azami_fazla_calisma(yil, ay, p)
        if saat + diger_saat > azami + 1e-9:
            hatalar.append(f"Personelin bu ayki fazla çalışması ({saat + diger_saat:g} saat), ayın gün türlerine göre yapılabilecek "
                           f"azami süreyi ({azami:g} saat) aşıyor (Bütçe K cetveli III-3).")
        uyarilar.append("Günlük puantaj girilmemiş; öğretim günü 3 saat / tatil 8 saat sınırı gün gün denetlenemedi. "
                        "'Günlük puantaj' ile çalışılan günleri giriniz (Yön. md.9/c-e).")
    if not takvim_tanimli(yil, p):
        uyarilar.append(f"Parametrelerde {yil} yılı tatil dönemleri ve bayram günleri tanımlanmamış; hafta içi günler öğretim günü sayıldı.")

    if sid:
        s = db.q1("SELECT * FROM siparis WHERE id = ?", (sid,))
        if s:
            if s.get("ucret_esasi") and not s["ucret_esasi"].startswith("Fazla"):
                uyarilar.append(f"Siparişin ücret esası '{s['ucret_esasi']}'. Fazla çalışma ücreti, fazla çalışma esaslı işler için ödenir.")
            iscilik = siparis_kaydi_tahsisi(dict(s), p).iscilik
            kullanilan = siparis_iscilik_kullanimi(db, sid, kid) + brut
            if iscilik <= 0:
                uyarilar.append("Siparişin maliyet tahsisinde işçilik payı kalmıyor; fazla çalışma ücreti sipariş işçiliğinden "
                                "karşılanamaz (Yön. md.9/b).")
            elif kullanilan > iscilik + 0.009:
                hatalar.append(f"Siparişte fazla çalışma ve öğrenci hakkı toplamı ({para(kullanilan)} TL) sipariş işçiliğini "
                               f"({para(iscilik)} TL) aşıyor (Yön. md.9/b, md.42/e).")
    return hatalar, uyarilar
