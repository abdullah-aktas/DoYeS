"""T.C. kimlik no, vergi kimlik no ve IBAN doğrulama."""
import re


def tckn_gecerli(tckn: str) -> bool:
    t = (tckn or "").strip()
    if not re.fullmatch(r"[1-9]\d{10}", t):
        return False
    d = [int(c) for c in t]
    if ((sum(d[0:9:2]) * 7) - sum(d[1:8:2])) % 10 != d[9]:
        return False
    return sum(d[:10]) % 10 == d[10]


def vkn_gecerli(vkn: str) -> bool:
    v = (vkn or "").strip()
    if not re.fullmatch(r"\d{10}", v):
        return False
    d = [int(c) for c in v]
    toplam = 0
    for i in range(9):
        tmp = (d[i] + 10 - (i + 1)) % 10
        if tmp == 9:
            toplam += 9
        else:
            toplam += (tmp * (2 ** (10 - (i + 1)))) % 9
    return (10 - (toplam % 10)) % 10 == d[9]


def vkn_veya_tckn_gecerli(no: str) -> bool:
    no = (no or "").strip()
    return tckn_gecerli(no) if len(no) == 11 else vkn_gecerli(no)


def iban_normalize(iban: str) -> str:
    return re.sub(r"\s+", "", (iban or "")).upper()


def iban_gecerli(iban: str) -> bool:
    i = iban_normalize(iban)
    if not re.fullmatch(r"TR\d{24}", i):
        return False
    yeniden = i[4:] + i[:4]
    sayisal = "".join(str(int(c, 36)) for c in yeniden)
    return int(sayisal) % 97 == 1


def iban_bicimle(iban: str) -> str:
    i = iban_normalize(iban)
    return " ".join(i[k:k + 4] for k in range(0, len(i), 4))


# Form alanlarında kullanılacak doğrulayıcılar: hata mesajı ya da None döndürür.
def d_tckn(deger):
    if deger and not tckn_gecerli(str(deger)):
        return "T.C. kimlik numarası geçersiz."
    return None


def d_vkn_tckn(deger):
    if deger and not vkn_veya_tckn_gecerli(str(deger)):
        return "Vergi kimlik / T.C. kimlik numarası geçersiz."
    return None


def d_iban(deger):
    if deger and not iban_gecerli(str(deger)):
        return "IBAN geçersiz (TR ile başlayan 26 karakter olmalı)."
    return None
