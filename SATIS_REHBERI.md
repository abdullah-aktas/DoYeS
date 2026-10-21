# DÖSE Yönetim Sistemi – Satıcı Rehberi

Bu rehber programı paketleyip okullara dağıtan, lisans üreten ve isterse sunucuyu kendisi barındıran **satıcı**
içindir. Okulların kullanacağı kılavuz `KURULUM.md` dosyasıdır.

**Satıcı:** Programı **Derik MTAL Döner Sermaye İşletmesi** geliştirir, satar, işletir ve destekler. Bu ad
`dose\lisans.py` içindeki `SATICI` değişkeninde tanımlıdır. Giriş ekranında, lisans penceresinde, mobil
uygulamanın giriş ve “Hakkında” ekranlarında, kurulum dosyasının yayıncı bilgisinde ve mobil sunucunun
`/api/durum` yanıtında görünür.

### Satışın DÖSE üzerinden yürütülmesi

- Lisans satışı DÖSE'nin kendi satış faturasıyla (e-Arşiv/e-Fatura) yapılır ve programdaki **Satış Faturası**
  sayfasına bir hizmet/ürün kalemi olarak girilir. Lisansı ürün kartında “Yazılım lisansı (1 yıl)” gibi tanımlayıp
  bilişim alanına bağlayın; kâr, faaliyet gideri, öğrenci hakkı ve işçilik payları diğer işlerde olduğu gibi hesaplanır.
- Yazılım lisansı genel orandan KDV'ye tabidir; oranı programdaki ürün kartında güncel mevzuata göre girin.
  Hasılat hazine payı ve yıl sonu dağıtımı hesaplarına kendiliğinden girer.
- Alıcı okulun DÖSE'si veya bir kamu idaresi olduğunda alım, idareler arası alım hükümlerine (4734 s.K. md. 3/e)
  dayanılarak doğrudan yapılabilir. Alıcı idarenin harcama yetkilisi ve muhasebe birimiyle teyit edin.
- Geliştirme ve destek işlerinde çalışan öğretmen ve öğrencilere ödemeler, DÖSE mevzuatındaki parça başı / fazla
  çalışma esaslarıyla yapılır (siparişe bağlı iş emri açın).
- Lisans sözleşmesinde (veya satış faturasının açıklamasında) şunlar yazsın: lisans süresi, kurum kodu, destek
  kanalı, güncelleme hakkı ve verinin okulda kaldığı (DÖSE Mobil Sunucusu dahil, veri satıcıya gönderilmez).

> `satici` klasörü **yalnız sizin bilgisayarınızda** kalır. EXE paketine ve kurulum dosyasına girmez. Okullara bu
> klasörü asla göndermeyin.

## 1. Kurulum dosyasını oluşturma

1. Gerekirse `dose\__init__.py` içindeki `SURUM` değerini artırın (ör. `1.1.0` → `1.2.0`).
2. `exe_olustur.bat` dosyasına çift tıklayın. Betik testleri çalıştırır, EXE'yi oluşturur ve Inno Setup kuruluysa
   kurulum dosyasını da hazırlar:
   - `kurulum_paketi\DOSE_Yonetim_Kurulum_<sürüm>.exe` dosyasını okullara gönderin.
   - Inno Setup yoksa `winget install JRSoftware.InnoSetup` ile kurun veya `dist\DOSE_Yonetim` klasörünü zipleyip gönderin.

Kurulum sihirbazı programı `C:\Program Files\DOSE Yonetim` klasörüne kurar. Masaüstü ve Başlat menüsü kısayolları
oluşturur, `veri` klasörüne tüm Windows kullanıcıları için yazma izni verir.

**Güncelleme:** Yeni sürümün kurulum dosyası eskisinin üzerine kurulur ve `veri` klasörüne dokunmaz. Program
kaldırılsa da veriler silinmez. `kurulum.iss` içindeki `AppId` değerini değiştirmeyin, yoksa güncelleme eski
sürümün üzerine yazılmaz.

**Windows uyarısı:** EXE imzasız olduğu için ilk açılışta "Windows bilgisayarınızı korudu" uyarısı çıkabilir.
Kullanıcı **Ek bilgi → Yine de çalıştır** der. Bu uyarıyı kaldırmak için bir kod imzalama sertifikası (OV/EV)
alıp `signtool` ile hem `DOSE_Yonetim.exe` dosyasını hem kurulum dosyasını imzalamanız gerekir.

## 2. Lisans sistemi

### Nasıl çalışır

- Program ilk kurulduğunda **30 gün deneme** olarak tam sürüm çalışır.
- Deneme veya lisans süresi bitince program **salt okunur** olur. Kayıtlar görüntülenebilir, rapor ve PDF
  alınabilir, yedeklenebilir. Yeni kayıt, değişiklik ve onay yapılamaz. Okulun verisi hiçbir zaman kilitlenmez.
- Bitişe 30 gün kala giriş ekranında ve üst çubukta sarı uyarı görünür.
- Lisans okulun **MEB kurum koduna** bağlıdır ve veritabanında saklanır. Sunucu modunda bir kez girilen lisans
  okulun bütün bilgisayarlarında geçerli olur, bilgisayar başına lisans gerekmez.
- Lisans anahtarı sizin gizli anahtarınızla dijital olarak imzalanır. Tek harfi değiştirilen anahtar çalışmaz ve
  gizli anahtar olmadan yeni anahtar üretilemez.

### Gizli anahtar (çok önemli)

`satici\ozel_anahtar.pem` lisans üretmenin tek yoludur.

- **Hemen yedekleyin:** şifreli bir USB belleğe ve kişisel, güvenli bir bulut klasörüne koyun.
- Kaybederseniz yeni lisans üretemezsiniz. Yeni anahtar oluşturursanız, sattığınız tüm lisanslar ancak yeniden
  üretilip yeni sürüm kurulursa çalışır.
- Başkasının eline geçerse o kişi de lisans üretebilir. Kimseyle paylaşmayın, e-postayla göndermeyin.

### Lisans verme adımları

1. Okul programda **Lisans… → Bilgileri kopyala** düğmesine basar ve okul adıyla kurum kodunu size gönderir.
2. `satici\lisans_uret.bat` dosyasını açın. Okul adını, kurum kodunu ve süreyi (1/2/3 yıl, süresiz veya özel
   tarih) girin. Ücret ve fatura numarası da yazılırsa satış kaydınız tutulur. **Lisans üret** düğmesine basın.
3. Oluşan anahtarı **Anahtarı kopyala** ile e-postaya yapıştırın veya `satici\lisanslar\<kurumkodu>_<no>.lic`
   dosyasını gönderin.
4. Okul **Lisans…** penceresinde anahtarı yapıştırır veya **Dosyadan yükle…** ile dosyayı seçer, sonra
   **Etkinleştir** der.

Yenileme için aynı okula yeni bitiş tarihli bir lisans üretip gönderin. Eski lisansın yerine geçer.
Tüm satışlar `satici\lisanslar.csv` dosyasında tutulur. Bu dosya Excel'de açılabilir, onu da yedekleyin.

**İletişim bilginiz:** `dose\lisans.py` içindeki `SATICI_ILETISIM = ""` satırına adınızı, telefonunuzu ve
e-postanızı yazın. Bu bilgi okulların lisans penceresinde görünür. Değiştirdikten sonra paketi yeniden oluşturun.

### Korumanın sınırları

Yerel (SQLite) modda veritabanı dosyası okulun bilgisayarındadır. Bilgili biri dosyayı elle düzenleyerek deneme
süresini sıfırlayabilir veya kurum kodunu değiştirebilir. Program bunu zorlaştırır: deneme başlangıcı işlem
kaydından da hesaplanır ve saat geri alınırsa son işlem tarihi esas alınır. Tam koruma sağlamaz. En güçlü koruma,
sunucuyu sizin barındırdığınız modeldir (bölüm 3), çünkü o modelde veritabanı sizin kontrolünüzdedir.

## 3. Çok okullu barındırma (sunucuyu siz işletirsiniz)

Tek bir PostgreSQL sunucusunda her okula **ayrı veritabanı ve ayrı kullanıcı** açılır. Okullar birbirinin
verisini göremez. Okul yalnız kurulum dosyasını kurar ve kendisine verdiğiniz bağlantı bilgisini girer.

### 3.1 Sunucu

- **Türkiye'de veri merkezi olan** bir VPS kullanın. KVKK ve 2019/12 sayılı Genelge nedeniyle yurt dışı bulut
  kullanmayın.
- Boyut için kaba ölçü: 30 okula kadar 2 çekirdek, 4 GB RAM ve 80 GB SSD yeterlidir.
- Kurulum `KURULUM.md` bölüm 2.2'deki gibidir. Tek fark `pg_hba.conf` satırıdır. Her kullanıcı yalnız kendi
  adındaki veritabanına bağlanabilsin diye şu satırı kullanın:

```
hostssl  sameuser  all  0.0.0.0/0  scram-sha-256
```

- `postgresql.conf` içinde `max_connections` değerini okul sayısına göre artırın. Her açık program bir bağlantı
  kullanır; 30 okul ve okul başına 5 bilgisayar için `max_connections = 200` yeterlidir.
- Mümkünse alan adı alıp Let's Encrypt sertifikası kurun. Böylece okullar “Zorunlu + sertifika doğrulama”
  seçeneğini kullanabilir.

### 3.2 Yeni okul ekleme

`satici\sunucu` klasöründeki betikleri sunucuya kopyalayın (ör. `/opt/dose`), sonra:

```bash
sudo chmod +x /opt/dose/*.sh
sudo /opt/dose/okul_ekle.sh 765432
```

Betik `okul_765432` adında bir veritabanı ve kullanıcı açar. Rastgele bir şifre üretir ve okula vereceğiniz
bağlantı bilgilerini ekrana yazar.

### 3.3 Yedekleme

```bash
sudo mkdir -p /var/backups/dose && sudo chown postgres /var/backups/dose
sudo -u postgres crontab -e
# şu satırı ekleyin:
0 2 * * * /opt/dose/yedek_al.sh
```

Yedekleri haftada bir sunucu dışına da kopyalayın, örneğin Türkiye'de ikinci bir depolama alanına.

### 3.4 KVKK yükümlülükleri

Bu modelde okul **veri sorumlusu**, siz **veri işleyen** olursunuz, çünkü personel TCKN, IBAN ve ücret bilgileri
sizin sunucunuzda durur. Bu yüzden:

- Her okulla yazılı bir **veri işleme sözleşmesi** yapın. Sözleşmede şunlar yer almalı: verinin nerede tutulduğu,
  kimlerin eriştiği, yedekleme ve silme süreleri, ihlal bildirimi.
- Sunucuya erişimi sınırlayın. SSH anahtarı kullanın, şifreyle girişi kapatın, güvenlik duvarında yalnız 22 ve
  5432 portları açık kalsın.
- Sözleşme bittiğinde okulun verisini teslim edin (`pg_dump`), sonra veritabanını silin
  (`DROP DATABASE okul_<kod>; DROP ROLE okul_<kod>;`).

## 4. Mobil uygulama ve her yerden erişim (kurum kodu)

Sürüm **1.7.0** ile mobil giriş **kurum kodu + kullanıcı + şifre** ile yapılır. Aynı kod masaüstü lisansına ve
(barındırmada) `okul_<kod>` veritabanına bağlıdır; okul içi veya dışı fark etmez.

### 4.1 İki dağıtım modeli

| Model | Mobil sunucu nerede? | Kullanıcı ne yazar? | Veri kimin sunucusunda? |
|---|---|---|---|
| **A – Okul kendi sunucusu** | Okul PC: `DOSE_Mobil_Sunucu.exe` | Kurum kodu + kullanıcı + şifre + okul IP/HTTPS | Okulda (SQLite veya okul PG) |
| **B – Satıcı barındırması (önerilen “her yerden”)** | Sizin VPS: `DOSE_Mobil_Sunucu.exe --coklu` | Kurum kodu + kullanıcı + şifre + sizin HTTPS geçit adresi | Sizin TR VPS (`okul_<kod>`) |

Model B'de telefon asla okul Wi-Fi'sine bağlı olmak zorunda değildir; masaüstü de aynı PostgreSQL'e internetten bağlanır
(Bağlantı ayarları → kurum kodundan doldur).

### 4.2 Çok okullu mobil geçit (Model B)

1. Bölüm 3'teki gibi PostgreSQL'i kurun; `okul_ekle.sh <kurumkodu> ["Okul Adı"]` her okul için DB + kullanıcı açar ve
   `/opt/dose/okullar.json` dosyasını günceller.
2. VPS'te (veya Windows sunucuda) program klasörünü koyun; `veri\okullar.json` dosyasının `okul_ekle.sh` çıktısıyla
   aynı okulları içermesini sağlayın (`DOSE_OKULLAR_JSON` veya dosyayı kopyalayın). Örnek:

```json
{
  "sunucu": "db.sizin-alaniniz.tr",
  "port": 5432,
  "ssl": "require",
  "okullar": {
    "765432": {"ad": "Derik MTAL", "sifre": "...", "kullanici": "okul_765432"}
  }
}
```

3. Let's Encrypt ile HTTPS alın. Geçidi başlatın:

```bash
# Linux örneği (systemd veya screen içinde)
export DOSE_KOK=/opt/dose/program
./DOSE_Mobil_Sunucu --coklu --host 0.0.0.0 --port 8765 \
  --sertifika /etc/letsencrypt/live/mobil.sizin-alaniniz.tr/fullchain.pem \
  --anahtar /etc/letsencrypt/live/mobil.sizin-alaniniz.tr/privkey.pem
```

4. Okula iletin:
   - Masaüstü: kurulum EXE + PG bağlantı (kurum kodu, sunucu, `okul_<kod>`, şifre, SSL zorunlu)
   - Mobil: geçit adresi `https://mobil.sizin-alaniniz.tr`, kurum kodu, kendi kullanıcı/şifreleri
5. İsteğe bağlı: `dose\ag.py` içindeki `VARSAYILAN_GECIT` veya `mobil\uygulama.py` içindeki `VARSAYILAN_GECIT`
   alanına geçit URL'sini yazıp APK'yı yeniden derleyin; kullanıcı adresi elle yazmak zorunda kalmaz.
   Masaüstü için `veri\ag.json` içinde `pg_sunucu` da verilebilir.

### 4.3 Derleme

```powershell
# Mobil sunucu: exe_olustur.bat masaüstü programla birlikte mobil sunucuyu da üretir,
# dist\DOSE_Yonetim\MobilSunucu klasörüne koyar ve kurulum dosyasına ekler (Başlat menüsünde kısayolu olur).

# İmzalı APK + Google Play AAB (önerilen)
# Önce: mobil\android\signing.env.example → signing.env (şifreler) ve upload-keystore.p12
cd D:\DÖSE\mobil
apk_aab_olustur.bat
# Çıktı:
#   mobil\DOSE_Mobil.apk              → yan yükleme / kurulum paketi
#   mobil\store\DOSE_Mobil_<sürüm>.apk
#   mobil\store\DOSE_Mobil_<sürüm>.aab → Play Console «Üretim» yüklemesi
```

- Sürüm: `mobil\pyproject.toml`, `mobil\uygulama.py` (`SURUM`) ve `dose\__init__.py` (`SURUM`) aynı tutulmalıdır.
- Play ikonu: `mobil\assets\ikon.png` ve mağaza listesi için `mobil\assets\store\icon-512.png` / `icon-1024.png`.
- **iOS / App Store:** IPA yalnız **macOS + Xcode + Apple Developer** ile üretilir (`flet build ipa`). Windows’ta derlenemez. Bundle id: `tr.k12.meb.derikmtal.dosemobil` (`[tool.flet.ios]`).
- Keystore (`upload-keystore.p12`) ve `signing.env` Git’e **konmaz**; yedeklerini güvenli saklayın — kaybolursa Play güncellemesi yapılamaz.

### 4.4 Lisans ve mobil

Mobil sunucu / geçit okulun (veya `okul_<kod>` DB'sinin) lisansını kullanır; ayrı mobil lisans yoktur.
Lisans süresi dolunca mobilde de yalnız görüntüleme yapılır.

## 5. Satış ve kurulum – uçtan uca

### 5.1 Satış öncesi (sizin taraf)

1. `SURUM` değerini güncelleyin → `exe_olustur.bat` → `kurulum_paketi\DOSE_Yonetim_Kurulum_<sürüm>.exe`
2. APK üretip `mobil\DOSE_Mobil.apk` olarak koyun; betiği yeniden çalıştırın (pakete girer).
3. Barındırma satıyorsanız: VPS + PG + geçit HTTPS + `okul_ekle.sh` + veri işleme sözleşmesi.
4. DÖSE satış faturası / ürün kartı (yazılım lisansı) hazır.

### 5.2 Okula teslim

| Teslim | İçerik |
|---|---|
| Kurulum | `DOSE_Yonetim_Kurulum_<sürüm>.exe` |
| Lisans | Kurum koduna bağlı anahtar veya `.lic` |
| Barındırma varsa | PG host, port, `okul_<kod>`, kullanıcı, şifre, SSL; mobil geçit URL |
| Barındırma yoksa | Okul kendi mobil sunucusunu Wi-Fi / VPN / HTTPS ile açar (`KURULUM.md` §3) |
| APK | `DOSE_Mobil.apk` veya kurulum klasöründeki `mobil\` |

### 5.3 Okulda kurulum sırası

1. Kurulum EXE → ilk giriş `admin` / `admin` → şifre değiştir.
2. **Kurum ve Görevliler:** okul adı + kurum kodu.
3. **Lisans…** etkinleştir.
4. Barındırma: **Bağlantı ayarları → Merkezi sunucu → Kurum kodundan doldur** → şifreyi yapıştır → kaydet.
   (Yerel tek PC ise bu adım yok.)
5. Kullanıcılar / personel / bölümler.
6. Mobil: sunucu veya geçidi aç → telefonda kurum kodu + kullanıcı + şifre (+ adres) → onay / fazla çalışma dene.
7. İşlem kaydında kaynağın “Mobil” olduğunu doğrula.

### 5.4 Güncelleme

Yeni sürüm kurulum dosyası eskisinin üzerine kurulur; `veri` klasörüne dokunulmaz. Barındırmada geçit EXE'sini de
yenileyin. APK değiştiyse telefona yeni APK verin (Play Store kullanıyorsanız aab güncellemesi).

## 6. Satıştan önce kontrol listesi

- [ ] `ozel_anahtar.pem` ve `lisanslar.csv` yedeklendi.
- [ ] `SATICI_ILETISIM` dolduruldu, paketler yeniden oluşturuldu.
- [ ] Kurulum dosyası temiz PC'de denendi: kurulum, giriş, lisans, kaldırma/yeniden kurulumda veri korunması.
- [ ] Mobil: kurum kodu ile giriş, onay, fazla çalışma, işlem kaydında “Mobil” (Wi-Fi ve mümkünse internet/geçit).
- [ ] Barındırma: `okul_ekle.sh`, `okullar.json`, `--coklu` HTTPS geçit, masaüstü “kurum kodundan doldur”.
- [ ] Satış faturası / ürün kartı ve KDV; okul yönetimi ile usul net.
- [ ] Barındırmada veri işleme sözleşmesi taslağı hazır.
