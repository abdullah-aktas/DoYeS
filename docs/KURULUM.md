# DÖSE Yönetim — Okul İçin Kurulum ve Kullanım

Okulda kurulacak sunucu, veritabanı veya açık bırakılacak bilgisayar yoktur. Kayıtlar Supabase'te durur. Okulun
bilgisayarı kapalı olsa ya da bozulsa da iş yürür ve veri kaybolmaz.

Rol ve platform (masaüstü / web / mobil) kullanım adımları: **[KULLANIM.md](KULLANIM.md)**.
Satıcının kuruma paket verme sırası: **[SATIS_VE_TESLIM.md](SATIS_VE_TESLIM.md)**.

## 0. Satıcı / teknik: Supabase projesini ilk kez kurmak

Bu bölüm **okul müdürüne değil**, uygulamayı hazırlayan kişiye yöneliktir. Bir kez yapılır.

1. [supabase.com](https://supabase.com) hesabı açın → **New project**. Bölgeyi okulunuzun KVKK / veri yerleşimi
   politikasına göre seçin (tercihen AB veya Türkiye'de barındırılan çözüm; yurt dışı riskini yönetimle teyit edin).
2. **Project Settings → API:** Project URL ve **anon / publishable** anahtarı kopyalayın.
3. **Project Settings → Database:** veritabanı şifresini güvenli yere kaydedin. **service_role** anahtarını APK'ya,
   Flet istemcisine veya sohbete koymayın.
4. Bilgisayarda depo kökünden:

```powershell
cd D:\DÖSE\supabase
npm install
npx supabase login
npx supabase link --project-ref PROJE_REF
npx supabase db push
```

`PROJE_REF`, Dashboard URL'sindeki proje kimliğidir (ör. `bzirnfsgdswcwwutmwdi`).

5. **Authentication → Providers → Email** açık olsun; e-posta doğrulaması açık kalsın.
6. İstemci ayarı: `istemci/ayar.py` içindeki varsayılan URL/anahtar veya ortam değişkenleri
   `DOSE_SUPABASE_URL` / `DOSE_SUPABASE_ANAHTAR`.
7. İlk okulu açmak (SQL Editor, **service_role** / Dashboard SQL; istemci değil):

```sql
SELECT dose_private.okul_ac('Okul Adı', 'KURUM_KODU', date '2027-08-31', interval '7 days');
-- Dönen etkinleştirme kodunu müdüre verin (tek kullanımlık). Bitiş NULL = süresiz.
```

Müdür uygulamada hesap açar, e-postayı doğrular, kod + kurum kodu ile okulu etkinleştirir; ardından diğer rolleri
**Kullanıcılar → Davet et** ile ekler.

Yerel şema testi (geliştirici): `cd supabase && npm test`.

## 1. Uygulamayı açmak

| Cihaz | Nasıl |
|---|---|
| Windows | Satıcının verdiği masaüstü paketini çalıştırın veya geliştiricide `python main.py` / `flet run -a istemci/assets`. |
| Android | Satıcının verdiği APK’yı kurun (veya Play Store). |
| Tarayıcı | Satıcının verdiği web adresini açın. |

Hepsi aynı uygulamadır; telefonda eksik sürüm yoktur. Geniş ekranda liste ile form yan yana, telefonda sırayla
görünür.

## 2. Okulun ilk açılışı (Okul Müdürü)

1. Satıcıdan **etkinleştirme kodunu** alın (`DOSE-XXXX-…`). Kod tek kullanımlıktır ve süresi vardır.
2. Uygulamada **Hesap aç** ile kendi e-postanızı ve şifrenizi girin.
3. E-postanıza gelen doğrulama bağlantısına tıklayın.
4. Giriş yapın. «Okula bağlanın» ekranında kodu, okulunuzun **MEB kurum kodunu** ve adınızı soyadınızı girin.
5. Okulun ilk **Okul Müdürü** siz olursunuz. Kodu 5 kez yanlış girerseniz kod kilitlenir; satıcıdan yenisini isteyin.

**Kodunuz yoksa — 1 ay ücretsiz deneme:** Giriş ekranındaki **1 ay ücretsiz dene** ile hesap açın, e-postanızı
doğrulayıp giriş yapın. «Okula bağlanın» ekranında adınızı soyadınızı, MEB kurum kodunu ve okulun adını girip
**1 ay ücretsiz denemeyi başlat**'a basın. Okul hemen açılır ve bir ay boyunca tüm özellikler kullanılabilir;
üst başlıkta kalan gün görünür. Her hesap yalnız bir kez deneme açabilir ve aynı kurum koduyla ikinci okul açılamaz.

## 3. Kullanıcıları eklemek

**Kullanıcılar** ekranında **Davet et**'e basın. Kişinin e-postasını, adını, rolünü ve gerekiyorsa bölümünü seçin.

| Rol | Yasal görevi |
|---|---|
| Okul Müdürü | Harcama yetkilisi: onaylar, kullanıcıları yönetir |
| Teknik Müdür Yardımcısı | Gerçekleştirme görevlisi: işi ve puantajı kontrol edip imzalar |
| Sayman | Fatura ve muhasebe kayıtlarını hazırlar; tamamlanan işlem kapsamı aşağıda açıklanır |
| Alan Şefi | Atölyenin işini yürütür, puantajı imzalar (yalnız kendi bölümü) |
| Öğretmen | Atölyede yapılan işin puantajını yazar (yalnız kendi bölümü) |
| Memur / Veri Girişi | Tanım ve belge kayıtlarını girer |
| İzleyici / Denetçi | Değiştirmeden inceler |
| Sistem Yöneticisi | Tanımları ve kullanıcıları yönetir |

Davet edilen kişi **aynı e-postayla** hesap açar ve doğrular. İlk girişte okula kendiliğinden bağlanır. Okulda en az
bir aktif Okul Müdürü kalmak zorundadır. Ayrılan kişiyi silmeyin, **pasif** yapın; geçmiş kayıtlarındaki izi kalır.

## 4. İlk tanımlar

Sırasıyla: **Kurum bilgileri** → **Bölüm / atölye** → **Personel** → **Cariler** → **Malzeme** → **Ürün / hizmet**
→ **Öğrenciler**.

- T.C. kimlik no, VKN ve IBAN girildiğinde doğrulanır. Hatalıysa kayıt reddedilir ve sebebi yazılır.
- Cari kodunu boş bırakırsanız sıradaki numara (C0001, C0002…) verilir.
- Tutarları Türkçe yazın: `1.250.000` veya `1.234,56`. Oranları yüzde olarak girin: `20`.
- Başka kayıtlarda kullanılan tanım silinmez; **Aktif** işaretini kaldırın.

## 5. Birlikte çalışma

- Biri kaydettiğinde diğerlerinin açık ekranı birkaç saniye içinde güncellenir.
- Siz bir kaydı düzenlerken başkası değiştirirse ekranın üstünde uyarı çıkar. Kaydetmeye çalışırsanız kayıt
  reddedilir, kimin ne zaman değiştirdiği yazılır ve güncel hali yüklenir. Değişikliğinizi güncel kayıt üzerinde
  yeniden yapın.
- **İşlem kaydı** ekranı kimin, hangi rolde, neyi, ne zaman yaptığını gösterir. Teftişte ayrı dosya aranmaz.
- Yalnız sunucunun kabul ettiği kayıt geçerlidir. Bağlantı kaydın sonucunu göstermeden kesilirse işlem
  gerçekleşmiş olabilir: listeyi kontrol edin veya aynı formu tekrar gönderin; aynı işlem iki kez kaydedilmez.

## 6. Fatura kayıtları

Sayman **Fatura kayıtları** ekranında alış faturası veya onaylı siparişe bağlı kısmi satış faturası açar.
Vergi oranlarını, gerekiyorsa okulun vergi hesaplarını ve stok çıkış maliyetini kendisi doğrular.
Önizlemedeki tutarlar kontrol edildikten sonra kayıt yapılır; hata için gerekçeli ters kayıt kullanılır.
Eski siparişin onay anındaki stok bağlantısı bilinmiyorsa mevcut bağlantıyla işlem yapılması ayrıca onaylanır.

Bu ekran GİB'e e-Fatura göndermez; ters kayıt da GİB'de iptal yapmaz. Tevkifat ve stopaj oranları belge geneline
uygulanır, farklı kalemlerde farklı istisna veya tevkifat oranları desteklenmez. Mali ve mevzuat uygunluğunu
yetkili sayman ayrıca değerlendirmelidir.

## 7. Kasa / Banka

Sayman önce gerekiyorsa **Açılış bakiyesi** girer ve uygun karşı hesabı seçer. Gerçekleşen fatura tahsilatı veya
ödemesi için hesabı ve faturayı seçer; tutar fatura kalanını aşamaz ve kasa veya banka bakiyesi eksiye düşemez.
Düzeltme için aynı hesaptaki en yeni açık hareketten başlayarak gerekçeli ters kayıt oluşturulur.

Bu ekran gerçek banka transferi yapmaz; gerçekleşmiş hareketi kaydeder. Fatura tahsilatının KDV hariç hasılatı
**Hazine payı** ekranında aylık hesaplanır. Avans, hesaplar arası virman ve faturasız gelir/gider hareketleri
kasa türleriyle kaydedilebilir.

## 8. Merkez parametre yayını ve okul doğrulaması

Merkez, sipariş maliyet / işçilik tahsis oranlarını yayımlar. Okul saymanı doğruladıktan sonra parça başı ve
ilgili hesaplar bu oranları kullanır; doğrulanmamış yayında bordro hazırlığı engellenir.

Merkez yöneticisi önce normal Supabase Auth hesabını açıp e-postasını doğrular. Proje yetkilisi, Supabase
Dashboard **Authentication → Users** bölümünden bu hesabın UUID'sini bulur ve **SQL Editor** üzerinden
şu işlemi yapar; yer tutucuyu gerçek, doğrulanmış hesabın UUID'siyle değiştirin:

```sql
SELECT dose_private.mevzuat_yoneticisi_ata(
    'DOGRULANMIS_AUTH_KULLANICI_UUID'::uuid, 'Merkez Yöneticisinin Adı Soyadı', true);
```

Bu yetki okulun Sistem Yöneticisi rolünden ayrıdır. Okul müdürü veya okul kullanıcısı bu yetkiyi veremez.
Merkez yöneticisi bir okula üye olmadan Flet'e giriş yapabilir; yalnız merkez yayın ekranını görür.
Yetkiyi kapatmak için aynı işlevi `false` ile çalıştırın. İşlemlerde `service_role` anahtarını istemciye
koymayın ve sohbette paylaşmayın.

1. Merkez yöneticisi **Merkez parametre yayını → Yeni yayın** üzerinden başlangıç tarihini, incelenen
   resmî dayanağı ve tüm oranları girer. Değerler yüzde olarak girilir; otomatik mevzuat doğrulaması yapılmaz.
2. Yayın ilgili takvim yılında, başlangıç tarihinden varsa daha sonraki başlangıç tarihine kadar geçerlidir.
   Aynı başlangıç tarihindeki son sürüm esas alınır; yeni yıl için önceki yılın değerleri kullanılmaz.
3. Her okulun saymanı **Okul parametre doğrulaması** ekranından yayını ve kaynağını kontrol edip açıklamayla
   doğrular. Diğer roller okuyabilir, doğrulayamaz. Merkez yayını okul için kendiliğinden onaylanmaz.
4. Aynı başlangıç tarihine yeni sürüm yayımlanırsa o sürüm ayrıca doğrulanır. Önceki sürümün onayı yeni
   sürüme aktarılmaz. Yanlış doğrulama gerekçeli geri çekilir; yayın ve karar geçmişi silinmez.

## 9. Roller ve sınırlar

| Rol | Tipik iş |
|---|---|
| Okul Müdürü | Onaylar, kullanıcı daveti, yıl sonu son onay |
| Teknik Müdür Yardımcısı | Sipariş / parça başı / fazla çalışma kontrol |
| Sayman | Fatura, kasa (avans-virman dahil), stok, yevmiye, hazine payı, mevzuat doğrulama, ÜTP ödemesi |
| Alan Şefi / Öğretmen | Sipariş taslağı, parça başı / fazla çalışma hazırlık (bölüm kısıtı) |
| Memur / İzleyici | Tanım girişi / salt okuma |
| Merkez | Parametre yayını |

Ana ekranda «Bugün ne yapmalıyım?» bekleyen onayları listeler; yasal süreler (hazine, muhtasar, KDV, Bakanlık
aylık mizan, üç aylık faaliyet) de burada görünür. Doğrulanmamış merkez parametresi varken parça başı / fazla
çalışma taslağı açılamaz. **Raporlar** ekranı yıllık özet ile üç aylık faaliyet ve Bakanlık mizan HTML çıktısı
üretir; **Resmi yazılar** şablonlarla üst yazı metni hazırlar. Özel sektör / tesis siparişlerinde asgari peşinat
zorunludur.

**Bu sürümde yoktur:** GİB e-Fatura gönderimi ve gerçek banka EFT/havale API’si. Uygulama muhasebe kaydı ve
yazdırılabilir / Excel-PDF çıktı üretir; GİB veya banka işlemi elle tamamlanır.

## 10. Lisans

Ana ekranın altında lisans bitişi yazar. Süre dolarsa kayıtlar silinmez, **salt okunur** olur. Satıcı lisansı
uzattığında kaldığınız yerden devam edersiniz.

Deneme süresi bittiğinde de aynı kural geçerlidir. Satıcı denemeyi ücretli lisansa SQL editöründen çevirir:

```sql
SELECT dose_private.lisans_ayarla('KURUM_KODU', date '2028-08-31', true);
```

Kurum kodu haksız yere denemeye açıldıysa satıcı `lisans_ayarla('KURUM_KODU', NULL, false)` ile okulu kapatır.

## 11. Sık karşılaşılanlar

| Mesaj | Ne yapmalı |
|---|---|
| E-posta adresiniz doğrulanmamış | Gelen kutusu ve gereksiz klasöründeki bağlantıya tıklayın; girişte «yeniden gönder» |
| Hesap … henüz bir okula bağlı değil | Müdür sizi davet etmeli; sonra **Yenile** |
| Hesabınız pasif | Müdür hesabınızı yeniden aktif yapmalı |
| Bu işlem için yetkiniz yok | Rolünüz bu işi yapamaz; müdürden rol isteyin |
| İnternet bağlantısı kurulamadı | İşlem sonuçlanmış olabilir; listeyi kontrol edin veya aynı formu tekrar deneyin |
| Veritabanı kurulumu tamamlanmamış | Satıcıya/teknik servise bildirin |
