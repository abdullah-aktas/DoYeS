# DÖSE Yönetim Sistemi (DoYeS)

Mesleki ve Teknik Anadolu Liseleri **Döner Sermaye İşletmesi** için masaüstü + mobil yönetim yazılımı.

**Sürüm:** bakınız [`surum.json`](surum.json) · **Kaynak / güncelleme:** [github.com/abdullah-aktas/DoYeS](https://github.com/abdullah-aktas/DoYeS)

## Ne işe yarar?

- Sipariş / iş emri, onay akışı, fatura, kasa-banka, stok  
- Fazla çalışma ve parça başı, yıl sonu ÜTP, hazine payı / KDV özetleri  
- Muhasebe (yevmiye/mizan), raporlar, resmi yazılar  
- **Mobil:** onay, iş talebi, fazla çalışma, özet listeler (kurum kodu ile)

## Hızlı başlangıç (geliştirme)

```powershell
cd D:\DÖSE
python -m pip install -r requirements.txt
python main.py
```

İlk giriş: `admin` / `admin` (şifre değiştirmeniz istenir).

Kurulum paketini üretmek: `exe_olustur.bat` → `kurulum_paketi\DOSE_Yonetim_Kurulum_<sürüm>.exe`

Ayrıntılı kurulum: [`KURULUM.md`](KURULUM.md) · Teknik servis / programcı: [`TEKNIK_SERVIS_KILAVUZU.md`](TEKNIK_SERVIS_KILAVUZU.md) · Satış / barındırma: [`SATIS_REHBERI.md`](SATIS_REHBERI.md)

## Geçit adresi zorunlu mu?

**Hayır.** Mobil girişte çoğu zaman yalnız **kurum kodu + kullanıcı + şifre** yeterlidir.

| Yol | Ne zaman |
|-----|----------|
| **LAN keşif** | Telefon ile Mobil Sunucu aynı Wi-Fi’de; adres otomatik bulunur |
| **GitHub `surum.json` → `gecit`** | Satıcı barındırmasında geçit URL’si buraya yazılır; kullanıcı adres yazmaz |
| **Gelişmiş ayar** | Otomatik bulunamazsa elle sunucu adresi |

Satıcı geçidini yayınlamak için `surum.json` içinde:

```json
"gecit": "https://mobil.sizin-alaniniz.tr"
```

## Güncellemeler (kullanıcılar)

1. Yeni sürümü bu repoya / [Releases](https://github.com/abdullah-aktas/DoYeS/releases) altına koyun.  
2. `surum.json` içindeki `"surum"` ve `"notlar"` alanlarını güncelleyin.  
3. Masaüstü ve mobil açılışta **güncelleme uyarısı** gösterir; “GitHub’da aç” ile indirme sayfasına gider.

Kurulum EXE eskisinin üzerine kurulur; `veri` klasörü korunur.

## Marka (logo / ikon)

Tüm arayüzler ortak dosyaları kullanır:

- `dose/gorsel/logo.png` — giriş ve marka  
- `dose/gorsel/ikon.png` / `ikon.ico` — pencere ve uygulama ikonu  
- Mobil kopya: `mobil/assets/` (APK derlemesinde aynı görseller)

## Klasör özeti

| Klasör | İçerik |
|--------|--------|
| `dose/` | Masaüstü iş kuralları + PySide6 arayüz |
| `mobil/` | Flet Android / web istemci |
| `sunucu/` | FastAPI mobil API (+ `--coklu` geçit) |
| `satici/` | Lisans üretimi (okullara göndermeyin) |
| `tests/` | Birim testleri |

## Lisans anahtarı

Program lisansı kurum koduna bağlıdır. Satıcı araçları `satici/` altındadır; gizli anahtar GitHub’a **konmaz**.
