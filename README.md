# DÖSE Yönetim Sistemi (DoYeS)

Mesleki ve Teknik Anadolu Liseleri **Döner Sermaye İşletmesi** için masaüstü + mobil yönetim yazılımı.

**Sürüm:** bakınız [`surum.json`](surum.json) · **Kaynak / güncelleme:** [github.com/abdullah-aktas/DoYeS](https://github.com/abdullah-aktas/DoYeS)

## Ne işe yarar?

- Sipariş / iş emri, onay akışı, fatura, kasa-banka, stok  
- Fazla çalışma ve parça başı, yıl sonu ÜTP, hazine payı / KDV özetleri  
- Muhasebe (yevmiye/mizan), raporlar, resmi yazılar  
- **Mobil:** onay, iş talebi, fazla çalışma, denetim kontrol listesi, kişiye özel yapılacaklar, adım adım kılavuz ve mevzuat uyum denetimi (kurum kodu ile)
- **Eş zamanlı çalışma:** rol ve bölüm yetkileri, işlem günlüğü, çakışma koruması ve otomatik ekran eşitleme

## Hızlı başlangıç (geliştirme)

```powershell
cd D:\DÖSE
python -m pip install -r requirements.txt
python main.py
```

İlk giriş: `admin` / `admin` (şifre değiştirmeniz istenir).

Flet arayüzünü masaüstünde denemek için `python mobil\main.py` çalıştırın. Geniş ekranda yetkili olduğunuz panel, onay, iş emri, fazla çalışma, stok, kasa/banka, satış/alış belgesi, denetim, işlem kaydı, kurum, mevzuat parametreleri, mevzuat rehberi, bölüm, personel, öğrenci, cari, malzeme, ürün, muhasebe, rapor, yıl sonu kârı/ÜTP, resmi yazılar/belgeler ve yasal yükümlülük ekranları yan menüde gösterilir; dar ekranda mobil gezinme kullanılır. “Diğer” menüsünde rol bazlı yapılacaklar ve yasal süreler, adım adım iş kılavuzu, mevzuat özeti, riskler, terimler, görev ve sorumluluklar, yasal takvim ve seçili yılın parametrelerini sunan mevzuat rehberi ile bölüm kapsamını koruyan mevzuat uyum denetimi de bulunur; Sistem Yöneticisi kullanıcı hesaplarını, geçici şifreleri, onay akışını ve rol/yetki tablosunu yönetebilir. İşlem kaydı ekranında kullanıcı/kaynak/tarih filtreleri ile Excel dışa aktarımı; yedekleme ekranında anlık yedek alma, dosya indirme ve onay metniyle güvenli geri yükleme yapılabilir. Muhasebe ekranı yevmiye, fiş ayrıntısı, mizan, gelir tablosu ve hesap planını gösterir; yetkili kullanıcılar dengeli manuel fiş ve hesap planı kayıtlarını yönetebilir. Raporlar ekranı sipariş, ürün, bölüm, aylık nakit akışı, cari, personel, öğrenci, satın alma, hazine payı ve mevzuat dönem raporlarını Excel/PDF olarak dışa aktarır. Yıl sonu ekranı BKMYBS bilanço kârı, faiz düzeltmesi ve personel bazlı ÜTP girdilerini ortak hesaplama kurallarıyla işler; taslak kaydı, onay/kesinleştirme, yetkili geri alma, dağıtım cetveli, banka listesi ve resmî yazıları sunar. Resmi yazılar ekranı ortak şablonlarla yazı oluşturma/düzenleme/silme ve PDF çıktısını; öğrenci muvafakatnamelerini ve öğrenci/personel listelerini PDF olarak sunar. Hazine/SHÇEK ekranı aylık tahakkuk, bildirim, ödeme ve Örnek 30 PDF’sini; KDV/Muhtasar ekranı devreden KDV ile beyan hazırlık özetini ve muhtasar ayrıntısını sunar. Tanım, kurum, parametre, muhasebe, yıl sonu, resmi yazı ve yükümlülük yazımları rol/yazma yetkisi, doğrulama ve işlem kaydı denetimlerinden geçerek FastAPI üzerinden yapılır. Masaüstündeki diğer işlevler taşınıp doğrulanana kadar eski masaüstü uygulaması korunur.

Ürün / hizmet tanımında yetkili kullanıcılar birim maliyet kalemlerini kaydedebilir, mevzuat sınırlarına göre otomatik işçilik ve gider dağılımı yapabilir, hedef fiyattan kâr oranı hesaplayabilir, satış fiyatını ürüne aktarabilir ve fiyat tespit tutanağını PDF olarak alabilir.

Kurulum paketini üretmek: `exe_olustur.bat` → `kurulum_paketi\DOSE_Yonetim_Kurulum_<sürüm>.exe`

Ayrıntılı kurulum: [`KURULUM.md`](KURULUM.md) · Teknik servis / programcı: [`TEKNIK_SERVIS_KILAVUZU.md`](TEKNIK_SERVIS_KILAVUZU.md) · Satış / barındırma: [`SATIS_REHBERI.md`](SATIS_REHBERI.md)

## Supabase / merkezi PostgreSQL

Supabase şema geçişleri `supabase/migrations/` altında tutulur. Mobil/masaüstü istemciler Supabase'e doğrudan değil,
kimlik doğrulama ve mevcut rol denetimlerini uygulayan FastAPI sunucusuna bağlanır. Sunucuya yalnızca
`DOSE_DATABASE_URL` verilir; veritabanı parolası veya Supabase `service_role` anahtarı istemciye eklenmez.
Kurulum ve KVKK/veri bölgesi uyarıları için [`KURULUM.md`](KURULUM.md) içindeki Supabase bölümüne bakın.

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
