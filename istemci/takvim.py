"""Legal deadline calendar shown on the home screen. Dates are never shifted later; warning early is the safe side."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

AYLIK = [
    ("Hazine payı", 20, "Gecikmede aylık %1 zam; yarısı müdürden, yarısı saymandan."),
    ("Muhtasar beyan", 26, "Beyan gecikir; vergi ziyaı ve usulsüzlük cezası doğar."),
    ("KDV beyan ve ödeme", 28, "Beyan ve ödeme gecikir; gecikme zammı işler."),
]
# Aylık mizan: izleyen ayın 5'i (Yön. md.47)
MIZAN_GUN = 5
YILLIK = [
    ("SHÇEK payı", 1, None, "Yıllık pay kaçırılır."),
    ("Merkez payı", 2, None, "Yıl sonu kapanışı eksik kalır."),
]
# Üç aylık faaliyet: dönemi izleyen ayın 5'i (Yön. md.48)
FAALIYET = [
    (1, "I. dönem faaliyet raporu (Ocak-Mart)"),
    (4, "II. dönem faaliyet raporu (Nisan-Haziran)"),
    (7, "III. dönem faaliyet raporu (Temmuz-Eylül)"),
    (10, "IV. dönem faaliyet raporu (Ekim-Aralık)"),
]


def _ay_sonu(yil: int, ay: int) -> date:
    return date(yil, ay, calendar.monthrange(yil, ay)[1])


def _sonraki_aylik(bugun: date, gun: int) -> date:
    hedef = date(bugun.year, bugun.month, gun)
    if hedef >= bugun:
        return hedef
    yil, ay = (bugun.year + 1, 1) if bugun.month == 12 else (bugun.year, bugun.month + 1)
    return date(yil, ay, gun)


def _sonraki_yillik(bugun: date, ay: int) -> date:
    hedef = _ay_sonu(bugun.year, ay)
    return hedef if hedef >= bugun else _ay_sonu(bugun.year + 1, ay)


def _sonraki_faaliyet(bugun: date) -> date:
    """Dönemi izleyen ayın 5'i: Nisan/Temmuz/Ekim/Ocak."""
    adaylar = [
        date(bugun.year, 4, 5), date(bugun.year, 7, 5), date(bugun.year, 10, 5),
        date(bugun.year + 1, 1, 5),
    ]
    for d in adaylar:
        if d >= bugun:
            return d
    return date(bugun.year + 1, 4, 5)


def _sonraki_mizan(bugun: date) -> date:
    """Bir önceki ayın mizanı izleyen ayın 5'ine kadar."""
    hedef = date(bugun.year, bugun.month, MIZAN_GUN)
    if hedef >= bugun:
        return hedef
    yil, ay = (bugun.year + 1, 1) if bugun.month == 12 else (bugun.year, bugun.month + 1)
    return date(yil, ay, MIZAN_GUN)


def yaklasan_sureler(bugun: date) -> list[dict]:
    """Next due date of every recurring legal deadline, nearest first."""
    sonuc = []
    for ad, gun, gecikme in AYLIK:
        son = _sonraki_aylik(bugun, gun)
        sonuc.append({"ad": ad, "son_gun": son, "kalan": (son - bugun).days, "gecikme": gecikme})
    for ad, ay, _, gecikme in YILLIK:
        son = _sonraki_yillik(bugun, ay)
        sonuc.append({"ad": ad, "son_gun": son, "kalan": (son - bugun).days, "gecikme": gecikme})
    mizan = _sonraki_mizan(bugun)
    sonuc.append({
        "ad": "Bakanlık aylık mizan", "son_gun": mizan, "kalan": (mizan - bugun).days,
        "gecikme": "Yönerge md.47: ertesi ayın 5'ine kadar gönderilmezse Bakanlık takibi doğar.",
    })
    faaliyet = _sonraki_faaliyet(bugun)
    sonuc.append({
        "ad": "Üç aylık faaliyet raporu", "son_gun": faaliyet, "kalan": (faaliyet - bugun).days,
        "gecikme": "Yönerge md.48: dönemi izleyen ayın 5'ine kadar Bakanlığa gönderilmezse gecikme oluşur.",
    })
    return sorted(sonuc, key=lambda s: s["kalan"])


def sure_cumlesi(sure: dict) -> str:
    if sure["kalan"] == 0:
        return f"{sure['ad']} için son gün bugün."
    if sure["kalan"] == 1:
        return f"{sure['ad']} için son gün yarın."
    if sure["ad"].endswith("payı"):
        return f"{sure['ad']}na {sure['kalan']} gün var."
    return f"{sure['ad']} için {sure['kalan']} gün var."


def bugun_istanbul() -> date:
    from datetime import datetime, timezone
    return (datetime.now(timezone.utc) + timedelta(hours=3)).date()
