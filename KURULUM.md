# DÖSE Yönetim Sistemi – Kurulum ve Kullanım Kılavuzu

## 1. Programı çalıştırma (tek bilgisayar)

**Kurulum dosyasıyla (önerilen):** `DOSE_Yonetim_Kurulum_<sürüm>.exe` dosyasına çift tıklayın ve sihirbazı
izleyin. Program masaüstüne ve Başlat menüsüne eklenir. Windows "bilgisayarınızı korudu" uyarısı verirse
**Ek bilgi → Yine de çalıştır** deyin. Yeni sürüm aynı şekilde eskisinin üzerine kurulur. Veriler korunur;
program kaldırılsa bile `veri` klasörü silinmez.

**Python ile (geliştirme):** `D:\DÖSE` klasöründeki `baslat.bat` dosyasına çift tıklayın. Eksik paketler ilk açılışta kendiliğinden kurulur.
Komut satırından çalıştırmak için:

```powershell
cd D:\DÖSE
python -m pip install -r requirements.txt   # yalnız ilk seferde
python main.py
```

**Taşınabilir klasörle:** `exe_olustur.bat` çalıştırıldığında `dist\DOSE_Yonetim` klasörü oluşur. Bu klasörün
tamamını başka bir bilgisayara kopyalayıp `DOSE_Yonetim.exe` ile de açabilirsiniz.

**İlk giriş:** kullanıcı adı `admin`, şifre `admin`. Girişte yeni şifre belirlemeniz istenir.

**Lisans:** Program ilk 30 gün deneme olarak tam sürüm çalışır. Lisans almak için giriş ekranındaki **Lisans…**
düğmesine basın ve **Bilgileri kopyala** ile okul adını ve kurum kodunu satıcıya gönderin. Size gelen anahtarı
aynı pencereye yapıştırın veya `.lic` dosyasını **Dosyadan yükle…** ile seçip **Etkinleştir** deyin. Sunucu
modunda lisans bir kez girilir ve bütün bilgisayarlarda geçerli olur. Süre dolarsa program salt okunur çalışır:
kayıtlar görüntülenir, raporlanır ve yedeklenir, ancak yeni kayıt yapılamaz. Lisans kurum koduna bağlıdır; lisans
girildikten sonra **Kurum ve Görevliler** sayfasındaki kurum kodu değiştirilemez.

## 2. Birden çok bilgisayarda ortak çalışma (internet üzerinden)

```
 [Müdür PC] ─┐
 [TMY PC]  ──┼── İnternet (SSL şifreli) ──> [Merkezi PostgreSQL sunucusu]
 [Şef PC]  ──┤
 [Öğretmen]──┘
```

Tüm bilgisayarlar aynı merkezi veritabanını kullanır. Bir kullanıcının girdiği kayıt veya onay, diğerlerinin ekranına
anında yansır. Bekleyen onaylar ise en geç 60 saniye içinde 🔔 bildirimiyle görünür.

### 2.1 Sunucu seçimi

| Seçenek | Açıklama |
|---|---|
| **Türkiye'de veri merkezi olan bulut / VPS** (önerilen) | Aylık küçük bir ücretle 1–2 çekirdek, 2 GB RAM yeterlidir. Sabit IP ve kesintisiz erişim sağlar. |
| Yönetilen PostgreSQL hizmeti | Yedekleme ve güncellemeyi sağlayıcı yapar. Sunucunun Türkiye'de olduğundan emin olun. |
| Okulda sabit IP'li bir bilgisayar | Modemde 5432 portu yönlendirilir. Elektrik ve internet kesintisinde sistem durur. VPN önerilir. |

> Personel TCKN, IBAN ve ücret bilgileri kişisel veridir (6698 sayılı KVKK). Cumhurbaşkanlığı'nın 2019/12 sayılı
> Bilgi ve İletişim Güvenliği Tedbirleri Genelgesi uyarınca kamu verisinin **yurt içinde** tutulması gerekir. Yurt
> dışındaki bulut hizmetlerini kullanmayın. Okulunuzun/İl MEM'in bilgi güvenliği politikasına uyun.

### 2.2 Sunucuya PostgreSQL kurulumu (Ubuntu 22.04 / 24.04 örneği)

```bash
sudo apt update && sudo apt install -y postgresql
sudo -u postgres psql
```

```sql
CREATE USER dose_app WITH PASSWORD 'Uzun-ve-Guclu-Bir-Sifre!';
CREATE DATABASE dose OWNER dose_app ENCODING 'UTF8' TEMPLATE template0;
\q
```

`/etc/postgresql/<sürüm>/main/postgresql.conf` dosyasında:

```
listen_addresses = '*'
ssl = on
password_encryption = scram-sha-256
```

`/etc/postgresql/<sürüm>/main/pg_hba.conf` dosyasının sonuna şu satırı ekleyin. Mümkünse `0.0.0.0/0` yerine okulun
sabit IP adresini (ör. `85.100.10.20/32`) yazın:

```
hostssl  dose  dose_app  0.0.0.0/0  scram-sha-256
```

```bash
sudo systemctl restart postgresql
sudo ufw allow OpenSSH
sudo ufw allow from 85.100.10.20 to any port 5432 proto tcp   # yalnız okul IP'si
sudo ufw enable
```

Ubuntu'da PostgreSQL hazır bir SSL sertifikasıyla gelir. Bu sertifikayla bağlantı ayarında “Zorunlu (önerilen)”
seçeneği çalışır. Alan adınız varsa Let's Encrypt sertifikası ile “Zorunlu + sertifika doğrulama” kullanılabilir.

**Sunucu yedeği (her gece 02:00):**

```bash
sudo mkdir -p /var/backups/dose && sudo chown postgres /var/backups/dose
sudo -u postgres crontab -e
# şu satırı ekleyin:
0 2 * * * pg_dump -Fc dose > /var/backups/dose/dose_$(date +\%F).dump && find /var/backups/dose -mtime +60 -delete
```

Programdaki **Yedekleme → Şimdi yedekle** düğmesi de sunucudaki verinin tam kopyasını bilgisayara indirir.

#### Supabase ile PostgreSQL (yeni kurulum)

Supabase, DÖSE uygulamasının kullandığı PostgreSQL veritabanını barındırabilir. Bu depo veritabanı şemasını
`supabase/migrations/` altında sağlar; mobil ve masaüstü istemciler Supabase'e doğrudan bağlanmaz, mevcut FastAPI
sunucusu üzerinden oturum ve rol denetiminden geçer.

1. Supabase projesini kurumunuzun bilgi güvenliği ve veri yerleşimi kurallarına uygun bir bölgede oluşturun.
   Personel/öğrenci kimlik, IBAN ve ücret verilerini yüklemeden önce okul/İl MEM veri sorumlusundan onay alın.
   Supabase'in seçtiğiniz bölgesinin Türkiye'de olduğunu doğrulayamıyorsanız gerçek kişisel veri kullanmayın.
2. Geliştirme bilgisayarında Supabase CLI ile projeyi bağlayıp ilk şemayı uygulayın:

   ```powershell
   supabase login
   supabase link --project-ref <PROJECT_REF>
   supabase db push
   ```

3. Mobil API'yi çalıştıran sunucuda `DOSE_DATABASE_URL` ortam değişkenini Supabase PostgreSQL bağlantı adresine
   ayarlayın. Örnek (gerçek parolayı kaynak koda, istemciye veya sohbete koymayın):

   ```powershell
   $env:DOSE_DATABASE_URL = "postgresql://postgres:<DB_PASSWORD>@db.<PROJECT_REF>.supabase.co:5432/postgres?sslmode=require"
   python sunucu_main.py
   ```

   Supabase bağlantı havuzu kullanılıyorsa proje panelindeki bağlantı adresi, kullanıcı ve portu aynen kullanın.
   Paroladaki URL özel karakterleri yüzde-kodlu olmalıdır. `DOSE_DATABASE_URL` yalnızca sunucu sürecinde tanımlanır;
   `service_role` anahtarı, veritabanı parolası veya bağlantı adresi Flet uygulamasına eklenmez.
4. İlk açılışta `admin / admin` hesabı oluşur; ilk girişte parolayı değiştirin. Veritabanı tablolarında RLS açıktır
   ve `anon`/`authenticated` için istemci politikası tanımlı değildir. Uygulama API'si sunucu tarafındaki PostgreSQL
   bağlantısını kullanır; kullanıcı/rol yetkileri DÖSE API'sinde ayrıca denetlenir.

Mobil Flet istemcileri `/api/senkron` üzerinden diğer oturumların işlem izini beş saniyede bir kontrol eder ve açık ana
ekrandaki listeyi yeniler. Denetim formunda her madde ayrı sürümlendiğinden farklı roller farklı maddeleri eşzamanlı
doldurabilir; aynı maddenin çakışan kaydı diğer kullanıcının verisini ezmez.

### 2.3 Her bilgisayarda (istemci) yapılacaklar

1. Programı kurulum dosyasıyla kurun (veya `dist\DOSE_Yonetim` klasörünü kopyalayın).
2. Programı açın. Giriş ekranında **Bağlantı ayarları…** düğmesine basın.
3. **Merkezi sunucu** seçeneğini işaretleyip bilgileri girin:
   - Sunucu adresi: sunucunun IP'si veya alan adı
   - Port: `5432`
   - Veritabanı: `dose`
   - Kullanıcı: `dose_app`
   - Şifre: veritabanı şifresi
   - SSL: “Zorunlu”
4. **Bağlantıyı sına** ile kontrol edin, ardından **Kaydet ve bağlan** deyin.
5. Kendi kullanıcı adınız ve şifrenizle giriş yapın.

- Bağlantı şifresi Windows hesabınıza bağlı olarak şifrelenip `veri\baglanti.json` dosyasında saklanır. Bu dosya
  başka bilgisayara kopyalanırsa şifrenin orada yeniden girilmesi gerekir.
- Boş sunucu veritabanına **ilk** bağlanışta tablolar kurulur ve `admin / admin` kullanıcısı oluşur. Hemen giriş
  yapıp şifreyi değiştirin.
- Sunucuya ulaşılamazsa program açılışta bağlantı ayarları ekranını gösterir.

### 2.4 Daha önce yerel modda girilmiş verileri sunucuya taşıma

Veriler bir bilgisayarda yerel modda girildiyse o bilgisayarda şu adımları izleyin:

1. Bağlantı ayarlarından sunucuya geçin.
2. `admin` (Sistem Yöneticisi) ile giriş yapın.
3. **Yedekleme / İşlem Kaydı → Bu bilgisayardaki yerel verileri sunucuya aktar** düğmesine basın.

Bu işlem sunucudaki mevcut verilerin yerine yerel verileri yazar. İşlemden önce sunucu verisinin yedeği alınır. Genellikle
yalnız ilk geçişte bir kez yapılır.

### 2.5 Aynı anda çalışma ve işlem izi

- Başka bir bilgisayarda veya telefonda yapılan kayıt, açık olan ekranlara birkaç saniye içinde kendiliğinden yansır.
- İki kişi aynı kaydı aynı anda düzenlerse, ikinci kaydeden kişinin değişikliği **üzerine yazılmaz**. Program
  “Bu kayıt siz düzenlerken … tarafından değiştirildi” uyarısı verir ve kaydın güncel hâlini yükler.
- Her işlem **İşlem Kaydı**na yazılır: kullanıcı, ad soyad, rol, tarih-saat, bilgisayar veya telefon adı, kaynak
  (Masaüstü / Mobil) ve değişen alanların eski ile yeni değerleri. Kayıt kullanıcı, kaynak ve tarihe göre süzülebilir.

## 3. Telefon, tablet ve web tarayıcı (DÖSE Mobil)

```
 [Telefon / tablet]  ─┐
 [Tarayıcı]          ─┼── kurum kodu + kullanıcı + şifre ──> [DÖSE Mobil Sunucu veya Geçit]
                      │         (okul PC'si veya satıcı VPS)
                      └──────────────────────────────────> [Aynı kurum veritabanı]
 [Masaüstü PCler] ──── PostgreSQL / yerel DB ─────────────>┘
```

Telefonlar veritabanına doğrudan bağlanmaz. **Kurum kodu + kullanıcı adı + şifre** ile giriş yapılır; veritabanı
şifresi telefona hiç girmez. Aynı kurum kodu okul Wi-Fi'sinden, evden veya sahadan (geçit / VPN / HTTPS) kullanılır.
Her işlem masaüstündeki yetki, bölüm kısıtı, onay akışı ve mevzuat denetimlerinin aynısından geçer; işlem kaydına
“Mobil” ve cihaz adıyla yazılır.

**Önkoşul:** Masaüstünde **Kurum ve Görevliler** sayfasında MEB kurum kodu girilmiş olmalıdır (lisans da bu koda bağlıdır).

**Mobilde yapılabilenler:** özet panel ve uyarılar; onay bekleyen belgeleri inceleme, uygun görme, onaylama, iade
etme; iş talebi (sipariş taslağı) girme ve siparişleri izleme; öğretmenin kendi fazla çalışmasını günlük puantajla
girip onaya göndermesi; stok, kasa/banka, satış ve alış belgeleri listeleri; işlem kaydı. Muhasebe fişi, fatura
kesme, bordro ödeme ve tanım işleri masaüstünde yapılır.

### 3.1 Sunucuyu başlatma (okul kendi sunucusu)

1. Veritabanına erişebilen ve sürekli açık kalan bir bilgisayar seçin (yerel modda verinin durduğu bilgisayar,
   sunucu modunda okuldaki herhangi bir bilgisayar).
2. Başlat menüsündeki **DÖSE Mobil Sunucu** kısayolunu (program klasöründe `MobilSunucu\DOSE_Mobil_Sunucu.exe`)
   çalıştırın. Pencerede telefonlara yazılacak adres ve kurum kodu görünür, ör.
   `http://192.168.1.10:8765`. Pencere açık kaldığı sürece mobil erişim çalışır.
3. İlk çalıştırmada Windows Güvenlik Duvarı izin isterse **Özel ağlar** için izin verin. Elle açmak için yönetici
   PowerShell'de:

```powershell
New-NetFirewallRule -DisplayName "DOSE Mobil" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private
```

4. Bilgisayar açıldığında kendiliğinden başlasın isterseniz **DÖSE Mobil Sunucu** kısayolunu
   `shell:startup` klasörüne kopyalayın.

Seçenekler: `--port 8765`, `--veritabani <yol>`, `--web-kapali`, `--sertifika` / `--anahtar` (HTTPS),
`--coklu` (satıcı barındırması; bkz. SATIS_REHBERI.md). Sunucu modunda bağlantı `veri\baglanti.json` dosyasından okunur.

### 3.2 Telefona kurulum ve giriş

- **Android:** `DOSE_Mobil.apk` dosyasını telefona gönderin ve açın. “Bilinmeyen kaynaklardan yükleme” izni
  istenirse verin.
- **Güncel APK:** [DÖSE Mobil 1.7.3 — GitHub Releases](https://github.com/abdullah-aktas/DoYeS/releases/tag/mobile-v1.7.3).
- **iPhone ve diğer cihazlar:** Tarayıcıda sunucu / geçit adresini açın; **Ana ekrana ekle** ile kısayol yapılabilir.
- Giriş alanları:
  1. **Kurum kodu** (zorunlu) — masaüstündekiyle aynı MEB kodu
  2. **Kullanıcı adı** ve **şifre** — masaüstündeki hesap
  3. **Sunucu / geçit adresi** — okul Wi-Fi'sinde ör. `192.168.1.10:8765`; internette satıcının verdiği
     `https://mobil....` adresi. Bir kez kaydedilir.
- İlk girişte şifre değiştirmesi istenen kullanıcı mobilde de önce şifresini değiştirir.

### 3.3 Okul dışından / her yerden erişim

Aynı kurum kodu ile okul dışından işlem için üç yol vardır (öncelik sırasıyla):

| Yol | Ne yapılır | Not |
|---|---|---|
| **Satıcı geçidi** (önerilen, barındırma) | Satıcı `--coklu` mobil geçidi ve HTTPS alan adı verir. Telefona yalnız kurum kodu + kullanıcı + şifre + geçit adresi. | Veri satıcı VPS'te (TR); masaüstü de aynı PG'ye bağlanır. |
| **VPN** | Okul/MEM VPN'ine bağlanıp okul içi mobil sunucu IP'sini kullanın. | Sunucu internete açılmaz. |
| **HTTPS + port yönlendirme** | Modemde 8765→mobil sunucu; `--sertifika` / `--anahtar` ile HTTPS. | İmzasız sertifikada uygulamada “imzasız sertifikaya güven” kutusunu işaretleyin. |

Güvenlik: 5 hatalı girişte 5 dk kilit; oturum 12 saat idle sonrası kapanır; şifre değişince diğer cihaz oturumları düşer;
pasif kullanıcı erişimini kaybeder; kurum kodu eşleşmezse giriş reddedilir.

## 4. Kullanıcı rolleri

Önce **Personel** kartlarını bölümleriyle birlikte girin. Ardından **Kullanıcılar → Yeni kullanıcı** ile her kişiye
rol verin. Öğretmen kullanıcıları personel kaydına bağlanmalı, alan şefi kullanıcıları ise bir bölüme bağlanmalıdır.
Hangi rolün hangi sayfayı görüp değiştirebileceğini **Rol / yetki tablosu** düğmesi gösterir.

| Rol | Görevi (5018 s.K. ve DÖSE Yönetmeliği) | Kapsam |
|---|---|---|
| Sistem Yöneticisi | Kullanıcılar, bağlantı, yedekleme. Onay aşamalarında imza yetkisi yoktur. | Tümü |
| Okul Müdürü (Harcama Yetkilisi) | Sipariş, bordro ve yıl sonu dağıtımına **son onay**; onay kaldırma | Tümü |
| Teknik Müdür Yardımcısı (Gerçekleştirme Görevlisi) | Belgelerin kontrolü, tanım ve işlem kayıtları | Tümü |
| Sayman | Fatura, kasa/banka, muhasebe, vergi ve yükümlülükler; yıl sonu dağıtımını hazırlar | Tümü |
| Alan Şefi | Alanının siparişlerini, parça başı bordrolarını, fazla çalışmalarını hazırlar; **uygun görüş** verir | Yalnız kendi bölümü |
| Öğretmen | İş talebi (sipariş taslağı) ve kendi fazla çalışma kaydını girer, alanının işlerini izler | Kendi bölümü, kendi kayıtları |
| Memur / Veri Girişi | Tanım, fatura, kasa, stok ve belge kayıtları; onay yetkisi yok | Tümü |
| İzleyici / Denetçi | Tüm kayıtları görür, değişiklik yapamaz | Tümü (salt okunur) |

## 4. Onay akışı

**Kullanıcılar** sayfasındaki **“Onay akışı etkin”** kutusu işaretlendiğinde belgeler aşağıdaki sırayla onaylanır.
Kapalıyken yetkili kullanıcı belgeyi tek adımda onaylar. Her iki durumda da onay geçmişi saklanır.

| Belge | Hazırlayan | 1. aşama | 2. aşama | Son onay |
|---|---|---|---|---|
| Sipariş / iş emri | Öğretmen, şef veya TMY | Alan şefi uygun görüşü | TMY kontrolü | Müdür onayı |
| Parça başı ücret bordrosu | Alan şefi veya TMY | TMY kontrolü | – | Müdür onayı |
| Fazla çalışma (kişi-ay) | Öğretmen veya şef | Alan şefi uygun görüşü | TMY kontrolü | Müdür onayı |
| Yıl sonu kâr dağıtımı / ÜTP | Sayman veya TMY | Sayman kontrolü | TMY kontrolü | Müdür onayı |

**Kurallar:**

- **Hazırlayanın aşaması:** Hazırlayanın kendi rolüne ait aşama kendiliğinden geçilir. Örneğin şefin hazırladığı
  sipariş doğrudan TMY'ye gider.
- **Kullanıcısı olmayan aşama:** O rolde (şef için o bölümde) aktif kullanıcı yoksa aşama atlanır ve geçmişe “Atlandı”
  olarak yazılır.
- **İade:** Onaylayan kişi belgeyi gerekçe yazarak iade edebilir. Hazırlayan belgeyi düzeltip yeniden gönderir.
- **Geri çekme:** Onay bekleyen belge, düzeltme için hazırlayan tarafından geri çekilebilir.
- **Kayıt kilidi:** Onay sürecindeki belge değiştirilemez. Onaylı siparişte esaslı alanlar (bedel, müşteri, bölüm,
  ücret esası vb.) değiştirilirse akış başa döner.
- **Muhasebe kayıtları:** Son onayla birlikte oluşur. Fazla çalışma ve parça başı bordroları için 720/360/335
  yevmiyesi, yıl sonu için ÜTP ve SHÇEK kayıtları üretilir.
- **Onay kaldırma:** Onayı yalnız Okul Müdürü veya Sistem Yöneticisi kaldırabilir. Bağlı fatura, bordro veya ödeme
  varsa kaldırılamaz.
- **Ödeme ve fatura şartı:** Bir ayın fazla çalışma ödemesi, o aydaki tüm kayıtlar onaylanmadan yapılamaz. Akış
  açıkken siparişe fatura kesmek için siparişin onaylanmış olması gerekir.
- **Takip:** Kararınızı bekleyen belgeler üst çubuktaki **🔔** düğmesinde ve **Onay Bekleyenler** sayfasında listelenir.
  Bu sayfadan toplu onay, iade ve geçmiş görüntüleme yapılabilir.

## 5. Güvenlik önerileri

- Her kişiye ayrı kullanıcı verin; ortak hesap kullanmayın. Ayrılan personelin hesabını silmek yerine
  **Aktif** işaretini kaldırın. Böylece onay izleri korunur.
- Veritabanı şifresini yalnız bilişim sorumlusu ve Sistem Yöneticisi bilmelidir.
- Sunucuda SSL'i kapatmayın. 5432 portunu yalnız okul IP'sine açın veya VPN kullanın.
- **Yedekleme / İşlem Kaydı** sayfasındaki log, kimin ne zaman hangi işlemi yaptığını gösterir.

## 6. Sorun giderme

| Hata | Çözüm |
|---|---|
| `connection timeout` / `could not connect` | İnternet bağlantısı, sunucu güvenlik duvarı (ufw, bulut güvenlik grubu), `listen_addresses` ayarı |
| `password authentication failed` | Veritabanı kullanıcı adı/şifresi hatalı |
| `no pg_hba.conf entry` | `pg_hba.conf` satırı eksik veya IP adresi izinli değil |
| `server does not support SSL` | Sunucuda `ssl = on` yapın (yalnız yerel ağda “Kapalı” seçilebilir) |
| `psycopg kurulu değil` | `python -m pip install -r requirements.txt` |
| `Lisans anahtarı biçimi hatalı` | Anahtarın tamamını (`DOSE1.` ile başlar) kopyalayın veya `.lic` dosyasını yükleyin |
| `Bu lisans … kurum kodlu okul içindir` | Kurum ve Görevliler sayfasındaki kurum kodu yanlış girilmiş; düzeltip yeniden deneyin veya satıcıya doğru kodu bildirin |
| `salt okunur çalışıyor` | Deneme veya lisans süresi doldu; Lisans… penceresinden yeni lisans girin |
