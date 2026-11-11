"""MEB Teftiş Kurulu DÖSE Rehberlik ve Denetim Rehberi — seçilmiş kontrol maddeleri.

Kaynak: Döner Sermaye İşletmesi Rehberlik ve Denetim Rehberi (özellikle §5 Mali iş ve işlemler).
Bu liste resmi teftiş raporunun yerine geçmez; okul içi hazırlık / izleme içindir.
"""
from __future__ import annotations

# (kod, bolum, metin)
DENETIM_MADDELERI: list[tuple[str, str, str]] = [
    ("5.1.1", "5.1 Muhasebe", "Muhasebe iş ve işlemleri VUK / döner sermaye mevzuatına uygun yürütülüyor mu?"),
    ("5.1.4", "5.1 Muhasebe", "Önceki yıldan devreden hesaplar için açılış kayıtları yapılmış mı?"),
    ("5.1.6", "5.1 Muhasebe", "Aylık Bakanlık mizan / raporları süresi içinde gönderiliyor mu?"),
    ("5.1.7", "5.1 Muhasebe", "Yıl sonu idare hesapları dosyası hazırlanıyor mu?"),
    ("5.1.10", "5.1 Muhasebe", "Sayman görev ve sorumluluklarını yerine getiriyor mu?"),
    ("5.1.14", "5.1 Muhasebe", "Fazla çalışma işlemleri Bütçe Kanunu K Cetveli sınırlarına uygun mu?"),
    ("5.1.15", "5.1 Muhasebe", "Mal/hizmet alımlarında eşik değer ve parasal limitler gözetiliyor mu?"),
    ("5.1.17", "5.1 Muhasebe", "Vergi beyannameleri zamanında veriliyor mu?"),
    ("5.1.19", "5.1 Muhasebe", "SHÇEK / sosyal hizmet payı (%1) hesaplanıp ödeniyor mu?"),
    ("5.1.20", "5.1 Muhasebe", "Hazine / merkez payı (gayrisafi hasılatın %15'i) işleniyor mu?"),
    ("5.2.1", "5.2 Satın alma", "Alımlarda Döner Sermayeli Kuruluşlar İhale Yönetmeliği uygulanıyor mu?"),
    ("5.2.2", "5.2 Satın alma", "Doğrudan temin / ihale süreci mali mevzuata uygun ve belgelenmiş mi?"),
    ("5.2.3", "5.2 Satın alma", "Ambar / depo yönetimi ve stok kayıtları düzenli mi?"),
    ("5.3.1", "5.3 Parça başı", "Parça başı ücret ödenen alanlar Bakanlıkça belirlenen alanlara uygun mu?"),
    ("5.3.5", "5.3 Parça başı", "Aynı iş için hem parça başı hem fazla çalışma ücreti ödenmiyor mu?"),
    ("5.3.6", "5.3 Parça başı", "Parça başı üretimde sipariş / onay / ödeme zinciri tamam mı?"),
    ("5.4.3", "5.4 Satış", "Siparişte peşinat (en az %10) alınıyor mu?"),
    ("5.4.6", "5.4 Satış", "İş alımında ön maliyet ve satış fiyatı belirleniyor mu?"),
    ("5.4.10", "5.4 Satış", "Teslimde muayene ve kabul işlemleri yapılıyor mu?"),
    ("5.5.1", "5.5 Taşınır", "Üretime yönelik taşınır alımları yönetmeliğe uygun mu?"),
]

KARARLAR = ("İncelenmedi", "Uygun", "Uygunsuz", "Uygulanamaz")


def madde_listesi() -> list[dict]:
    return [{"kod": k, "bolum": b, "metin": m} for k, b, m in DENETIM_MADDELERI]


def ozet_bulgular(kontroller: list[dict]) -> str:
    uygunsuz = [c for c in kontroller if c.get("karar") == "Uygunsuz"]
    if not uygunsuz:
        return "Kontrol listesinde uygunsuz madde işaretlenmedi."
    satirlar = [f"- {c.get('kod')}: {c.get('metin')}" + (f" ({c['not']})" if c.get("not") else "")
                for c in uygunsuz]
    return "Uygunsuz bulunan maddeler:\n" + "\n".join(satirlar)
