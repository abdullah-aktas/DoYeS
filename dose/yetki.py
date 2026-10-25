"""Kullanıcı rolleri, sayfa yetkileri ve onay akışları.

Görev dağılımı 5018 s.K. ve DÖSE Yönetmeliği'ne göre kurgulanmıştır: harcama yetkilisi okul müdürü, gerçekleştirme
görevlisi teknik müdür yardımcısı, muhasebe ve ödeme işlemleri sayman; alan şefi atölyesindeki işleri ve parça başı
işçilik dağılımını belirler (Yön. md.8/8), öğretmen kendi alanındaki işleri ve kendi fazla çalışmasını izler.
"""
from . import mevzuat as M

_SIRA = [M.ROL_SISTEM, M.ROL_MUDUR, M.ROL_TMY, M.ROL_SAYMAN, M.ROL_SEF, M.ROL_OGRETMEN, M.ROL_MEMUR, M.ROL_IZLEYICI]

# Her satırdaki 8 karakter _SIRA'daki rollerin yetkisidir: y = görür ve kayıt yapar, g = yalnız görür, - = menüde yok.
#                               Sis Müd TMY Say Şef Öğr Mem İzl
SAYFA_YETKI = {
    "Bugün Ne Yapmalıyım?":       "gggggggg",
    "Nasıl Yaparım? (Adım Adım)": "gggggggg",
    "Mevzuat Uyum Denetimi":      "gggggggg",
    "Rehberlik ve Denetim Formu": "yyyyyyyg",
    "Gösterge Paneli":            "gggggggg",
    "Onay Bekleyenler":           "yyyyyyyg",
    "Mevzuat Rehberi":            "gggggggg",
    "Kurum ve Görevliler":        "yygy--gg",
    "Mevzuat Parametreleri":      "yggy--gg",
    "Bölüm / Alan / Atölyeler":   "yyygg-yg",
    "Personel":                   "yyyyg-yg",
    "Öğrenciler":                 "ygygygyg",
    "Cari Hesaplar":              "ygyyg-yg",
    "Malzeme / Stok Kartları":    "ygyyygyg",
    "Ürün / Hizmet ve Maliyet":   "ygyyygyg",
    "Siparişler / İş Emirleri":   "yyygyyyg",
    "Satış Faturaları":           "ygyy--yg",
    "Alış / Gider Belgeleri":     "ygyy--yg",
    "Kasa / Banka":               "yggy--yg",
    "Stok Durumu ve Hareketleri": "ygyyygyg",
    "Parça Başı Ücret":           "yyyyygyg",
    "Fazla Çalışma Ücreti":       "yyyyyyyg",
    "Yıl Sonu Kârı ve ÜTP":       "yyyy--gg",
    "Hazine Payı / SHÇEK":        "yggy--yg",
    "KDV / Muhtasar Özeti":       "gggg--gg",
    "Yevmiye / Mizan":            "yggy--gg",
    "Raporlar":                   "ggggg-gg",
    "Resmi Yazılar / Belgeler":   "yyyyg-yg",
    "Kullanıcılar":               "y-------",
    "Yedekleme / İşlem Kaydı":    "yg-y---g",
}

YONETICI_ROLLERI = {M.ROL_SISTEM, M.ROL_MUDUR, M.ROL_SAYMAN}
BOLUM_KISITLI_ROLLER = {M.ROL_SEF, M.ROL_OGRETMEN}

ROL_ACIKLAMALARI = {
    M.ROL_SISTEM: "Kullanıcılar, bağlantı, yedekleme ve tüm kayıtlar. Onay aşamalarında imza yetkisi yoktur.",
    M.ROL_MUDUR: "Harcama yetkilisi: siparişleri, bordroları ve yıl sonu dağıtımını son onaylar.",
    M.ROL_TMY: "Gerçekleştirme görevlisi: siparişleri, bordroları ve dağıtımı kontrol eder; tanım ve işlem kayıtlarını yapar.",
    M.ROL_SAYMAN: "Fatura, kasa/banka, muhasebe, vergi ve yasal yükümlülük kayıtları; yıl sonu dağıtımını hazırlar.",
    M.ROL_SEF: "Kendi alanının siparişlerini, parça başı bordrolarını ve fazla çalışmalarını hazırlar, uygun görüş verir.",
    M.ROL_OGRETMEN: "Kendi alanının işlerini izler, iş talebi (sipariş taslağı) ve kendi fazla çalışma kaydını girer.",
    M.ROL_MEMUR: "Tanım, fatura, kasa, stok ve belge kayıtlarını girer; onay yetkisi yoktur.",
    M.ROL_IZLEYICI: "Denetim için bütün kayıtları görür, değişiklik yapamaz.",
}

# Onay akışları: (aşama adı, onaylayacak rol). Belgeyi hazırlayanın rolüne ait aşama kendiliğinden geçilir.
AKISLAR = {
    "Sipariş": [("Alan şefi uygun görüşü", M.ROL_SEF),
                ("Gerçekleştirme görevlisi kontrolü", M.ROL_TMY),
                ("Harcama yetkilisi onayı", M.ROL_MUDUR)],
    "Parça Başı": [("Gerçekleştirme görevlisi kontrolü", M.ROL_TMY),
                   ("Harcama yetkilisi onayı", M.ROL_MUDUR)],
    "Fazla Çalışma": [("Alan şefi uygun görüşü", M.ROL_SEF),
                      ("Gerçekleştirme görevlisi kontrolü", M.ROL_TMY),
                      ("Harcama yetkilisi onayı", M.ROL_MUDUR)],
    "Yıl Sonu": [("Sayman kontrolü", M.ROL_SAYMAN),
                 ("Gerçekleştirme görevlisi kontrolü", M.ROL_TMY),
                 ("Harcama yetkilisi onayı", M.ROL_MUDUR)],
}
BELGE_SAYFASI = {"Sipariş": "Siparişler / İş Emirleri", "Parça Başı": "Parça Başı Ücret",
                 "Fazla Çalışma": "Fazla Çalışma Ücreti", "Yıl Sonu": "Yıl Sonu Kârı ve ÜTP"}
GERI_ALABILEN = {M.ROL_MUDUR, M.ROL_SISTEM}


def sayfa_yetkisi(rol: str, sayfa: str) -> str:
    """'y' (kayıt), 'g' (görüntüleme) veya '' (erişim yok)."""
    satir = SAYFA_YETKI.get(sayfa)
    if satir is None:
        return "y" if rol == M.ROL_SISTEM else "g"
    try:
        c = satir[_SIRA.index(rol)]
    except ValueError:
        return ""
    return "" if c == "-" else c


def yonetici_mi(rol: str) -> bool:
    return rol in YONETICI_ROLLERI


def bolum_kisitli(rol: str) -> bool:
    return rol in BOLUM_KISITLI_ROLLER
