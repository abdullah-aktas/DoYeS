# Masaüstü, web ve mobil

DÖSE Yönetim tek istemcidir. Yetkiler, ekranlar ve kayıt kuralları her cihazda aynıdır; değişen yalnızca
açılış yolu ve ekran düzenidir.

## Masaüstü (Windows)

1. Satıcının verdiği kurulumu çalıştırın **veya** geliştiricide depo kökünden:
   ```powershell
   python main.py
   # sıcak yenileme:
   flet run -a istemci/assets
   ```
2. Pencere başlığında **DÖSE Yönetim** ve logo görünür.
3. Geniş ekranda (≥ ~900 px) listeler ile formlar yan yana açılır; üst menü grupları (Tanımlar, İşlemler,
   Muhasebe, Yönetim) tek satırda durur.
4. Yazdırılabilir belgeler ve HTML/Excel/PDF çıktılar genelde `Belgelerim\DÖSE Belgeler` klasörüne iner
   (ortam değişkeni `DOSE_BELGE_KLASORU` ile değiştirilebilir).

**İpucu:** Çoklu monitörde pencereyi bir ekrana sabitleyin; kaydedilmemiş form varken sayfa değiştirmeyin.

## Web tarayıcı

1. Satıcının verdiği adresi açın (Chrome / Edge önerilir).
2. İlk açılışta site izinleri gerekebilir; bildirim istemez.
3. Oturum tarayıcıda saklanır; gizli pencerede her seferinde yeniden giriş gerekir.
4. Yazdırma için tarayıcının **Yazdır** diyaloğunu kullanın; HTML belge açıldığında «Yazdır» düğmesi de vardır.
5. Dar pencerede mobil düzene benzer: menü kaydırılır, formlar alt alta gelir.

**İpucu:** Okul ortak bilgisayarında çıkış yapmayı unutmayın (`Çıkış` simgesi).

## Android (mobil)

1. Satıcının verdiği APK’yı kurun veya Play Store’dan yükleyin.
2. Uygulama adı: **DÖSE Yönetim**. İnternet izni zorunludur.
3. Telefon dikey kullanımda menü yatay kayar; listeden kayıt seçince form ayrı adımda açılır.
4. Belgeleri paylaşmak için sistem paylaşım / dosya yöneticisini kullanın; çıktılar cihaza kaydedilir.
5. Arka plana alıp dönünce oturum genelde korunur; uzun süre sonra yeniden giriş istenebilir.

**İpucu:** Mobil veri ile büyük rapor/Excel indirmeden önce Wi‑Fi tercih edin.

## Ortak kurallar (üç platform)

| Konu | Davranış |
|---|---|
| Veri | Hepsi aynı Supabase kaydına yazar; okul birbirini görmez |
| Canlı güncelleme | Başkasının kaydı birkaç saniye içinde listenize yansır |
| Çakışma | Siz düzenlerken başkası kaydederse uyarı çıkar; kaydetmek reddedilir |
| Salt okunur | Lisans / deneme bitince yazma kapanır; veri silinmez |
| GİB / banka | Uygulama göndermez; resmi işlemi ayrıca tamamlayın |

Ayrıntılı giriş ve kayıt alışkanlıkları: [ORTAK.md](ORTAK.md).
