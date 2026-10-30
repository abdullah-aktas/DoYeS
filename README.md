# DÖSE Yönetim Sistemi (DoYeS)

Mesleki ve Teknik Anadolu Liseleri **Döner Sermaye İşletmesi** için Flet tabanlı masaüstü, mobil ve web yönetim yazılımı.

**Sürüm:** bakınız [`surum.json`](surum.json) · **Kaynak / güncelleme:** [github.com/abdullah-aktas/DoYeS](https://github.com/abdullah-aktas/DoYeS)

## Ne işe yarar?

- Sipariş / iş emri, onay akışı, fatura, kasa-banka, stok  
- Fazla çalışma ve parça başı, yıl sonu ÜTP, hazine payı / KDV özetleri  
- Muhasebe (yevmiye/mizan), raporlar, resmi yazılar  
- **Flet masaüstü / mobil / web:** tüm yönetim modülleri, rol bazlı gezinme ve aynı FastAPI iş akışları
- **Eş zamanlı çalışma:** rol ve bölüm yetkileri, işlem günlüğü, çakışma koruması ve otomatik ekran eşitleme

## Hızlı başlangıç (geliştirme)

```powershell
cd D:\DÖSE
python -m pip install -r requirements.txt
```

Bir terminalde API sunucusunu başlatın:

```powershell
python sunucu_main.py
```

İkinci terminalde Flet masaüstü istemcisini açın:

```powershell
python main.py
```

İlk giriş `admin` / `admin`; ilk girişte şifre değiştirilir. Sunucu aynı bilgisayardaysa istemci LAN keşfiyle bulur. Uzak sunucu için giriş ekranındaki **Gelişmiş: sunucu adresi…** alanına API adresi girilir. Web sürümü, API sunucusu açıkken sunucu adresini tarayıcıda açarak çalışır; Android istemcisi `mobil\` altındadır. Masaüstü, mobil ve web istemcileri aynı Flet arayüzünü ve FastAPI/Supabase veri katmanını kullanır.

Uygulama; sipariş ve onay akışları, fatura, kasa/banka, stok, personel ödemeleri, muhasebe, raporlar, yasal yükümlülükler, yıl sonu ÜTP, resmi belgeler, yedekleme, Excel içe/dışa aktarma, kullanıcı yönetimi, mevzuat ve sayfa yardımı işlevlerini içerir. İşlemler sunucu tarafında rol/bölüm yetkisi, doğrulama ve işlem kaydı denetimlerinden geçer.

Kurulum paketini üretmek: `exe_olustur.bat` → `kurulum_paketi\DOSE_Yonetim_Kurulum_<sürüm>.exe`

Ayrıntılı kurulum: [`KURULUM.md`](KURULUM.md) · Teknik servis / programcı: [`TEKNIK_SERVIS_KILAVUZU.md`](TEKNIK_SERVIS_KILAVUZU.md) · Satış / barındırma: [`SATIS_REHBERI.md`](SATIS_REHBERI.md)

## Supabase / merkezi PostgreSQL

Supabase şema geçişleri `supabase/migrations/` altında tutulur. Flet istemcileri Supabase'e doğrudan değil,
kimlik doğrulama ve mevcut rol denetimlerini uygulayan FastAPI sunucusuna bağlanır. Sunucuya yalnızca
`DOSE_DATABASE_URL` verilir; veritabanı parolası veya Supabase `service_role` anahtarı istemciye eklenmez.
Kurulum ve KVKK/veri bölgesi uyarıları için [`KURULUM.md`](KURULUM.md) içindeki Supabase bölümüne bakın.

## Geçit adresi zorunlu mu?

**Hayır.** Aynı Wi-Fi'de çoğu zaman yalnız **kurum kodu + kullanıcı + şifre** yeterlidir.

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
3. Flet masaüstü ve mobil açılışta **güncelleme uyarısı** gösterir; “GitHub’da aç” ile indirme sayfasına gider.

Kurulum EXE eskisinin üzerine kurulur; `veri` klasörü korunur.

## Marka (logo / ikon)

Flet istemcisi aşağıdaki görsel kaynaklarını kullanır:

- `mobil/assets/logo.png` — giriş ekranı markası
- `mobil/assets/ikon.png` — Android/iOS uygulama ikonu
- `dose/gorsel/ikon.ico` — Windows EXE ve kurulum ikonu
- `dose/gorsel/kurulum_buyuk.bmp` / `kurulum_kucuk.bmp` — kurulum sihirbazı görselleri
- `mobil/assets/store/icon-512.png` / `icon-1024.png` — mağaza listeleme görselleri

## Klasör özeti

| Klasör | İçerik |
|--------|--------|
| `dose/` | Paylaşılan iş kuralları, muhasebe, veri erişimi ve belgeler |
| `mobil/` | Flet masaüstü / Android / web istemcisi |
| `sunucu/` | FastAPI API ve web sunucusu (+ `--coklu` geçit) |
| `satici/` | Lisans üretimi (okullara göndermeyin) |
| `tests/` | Birim testleri |

## Lisans anahtarı

Program lisansı kurum koduna bağlıdır. Satıcı araçları `satici/` altındadır; gizli anahtar GitHub’a **konmaz**.
