# DÖSE Yönetim Sistemi – Satıcı Rehberi

Bu rehber okulları açan, lisanslarını yöneten ve Supabase projesini işleten **satıcı** içindir.
**Adım adım satışa hazırlık ve kuruma teslim:** [SATIS_VE_TESLIM.md](SATIS_VE_TESLIM.md).
Okul kullanıcı kılavuzları [KULLANIM.md](KULLANIM.md); kurulum [KURULUM.md](KURULUM.md); teknik
[TEKNIK_SERVIS_KILAVUZU.md](TEKNIK_SERVIS_KILAVUZU.md); kod [GELISTIRICI.md](GELISTIRICI.md).

**Satıcı:** Programı **Derik MTAL Döner Sermaye İşletmesi** geliştirir, satar, işletir ve destekler.

### Satışın DÖSE üzerinden yürütülmesi

- Lisans satışı DÖSE'nin kendi satış faturasıyla (e-Arşiv/e-Fatura) yapılır. Lisansı ürün kartında «Yazılım
  lisansı (1 yıl)» gibi tanımlayıp bilişim alanına bağlayın.
- Yazılım lisansı genel orandan KDV'ye tabidir; oranı ürün kartında güncel mevzuata göre girin.
- Alıcı okulun DÖSE'si veya bir kamu idaresi olduğunda alım, idareler arası alım hükümlerine (4734 s.K. md. 3/e)
  dayanılarak doğrudan yapılabilir. Alıcı idarenin harcama yetkilisi ve muhasebe birimiyle teyit edin.
- Geliştirme ve destek işlerinde çalışan öğretmen ve öğrencilere ödemeler, DÖSE mevzuatındaki parça başı / fazla
  çalışma esaslarıyla yapılır.
- Lisans sözleşmesinde şunlar yazsın: lisans süresi, kurum kodu, destek kanalı, güncelleme hakkı, verinin
  Supabase'te (satıcının işlettiği projede) tutulduğu ve veri işleme şartları (§4).

## 1. Model

Tek Supabase projesinde bütün okullar vardır. Lisans okula aittir, bilgisayara değil. Okul açıldığında o okula ait
tek çalışma alanı oluşur; kullanıcılar kendi e-postalarıyla girer ve yalnız kendi okullarını görür.

## 2. Okul açma ve lisans

Supabase panelinde **SQL Editor**'ü açın (bu fonksiyonlar istemciden çağrılamaz).

**Yeni okul** — ad, MEB kurum kodu, lisans bitişi (`NULL` = süresiz), kodun geçerlilik süresi:

```sql
select dose_private.okul_ac('Derik Mesleki ve Teknik Anadolu Lisesi', '123456', date '2027-08-31', interval '7 days');
```

Dönen `DOSE-XXXX-…` kodunu müdüre güvenli yoldan iletin. Kod tek kullanımlıktır; 5 yanlış denemede kilitlenir.
Veritabanında yalnız özeti saklanır; kodu kaybederseniz yenisini üretin.

**Kodu yenilemek** (kayıp, süre doldu, kilitlendi; 10 dakika – 30 gün):

```sql
select dose_private.etkinlestirme_kodu('123456', interval '3 days');
```

**Lisansı uzatmak / kapatmak / denemeyi ücretliye çevirmek:**

```sql
select dose_private.lisans_ayarla('123456', date '2028-08-31', true);   -- uzat (deneme işaretini de kaldırır)
select dose_private.lisans_ayarla('123456', null, false);               -- kapat (veri silinmez)
```

Süresi dolan okul salt okunur olur; kapatılan okulun kullanıcıları hiçbir şey göremez. Okullar uygulamadan
**1 ay ücretsiz deneme** de açabilir; her hesap bir kez, her kurum kodu bir kez.

## 3. Teslim

| Teslim | İçerik |
|---|---|
| Etkinleştirme kodu | `okul_ac` çıktısı + kurum kodu |
| Windows | `cd istemci` → `flet build windows` (`istemci/build/windows`) |
| Android | `istemci\apk_aab_olustur.bat` → APK / Play AAB |
| Web | `flet build web` çıktısının yayınlandığı adres |

Okulda sıra: müdür hesap açar → e-postayı doğrular → kodu (veya denemeyi) girer → kurum bilgileri → kullanıcı daveti
→ tanımlar. Ayrıntı [KURULUM.md](KURULUM.md). Derleme: [TEKNIK_SERVIS_KILAVUZU.md](TEKNIK_SERVIS_KILAVUZU.md) §6.

## 4. KVKK yükümlülükleri

Okul **veri sorumlusu**, siz **veri işleyen** olursunuz; personel TCKN, IBAN ve ücret bilgileri sizin işlettiğiniz
Supabase projesinde durur. Bu yüzden:

- Her okulla yazılı bir **veri işleme sözleşmesi** yapın: verinin nerede (Supabase bölgesi) tutulduğu, kimlerin
  eriştiği, yedekleme ve silme süreleri, ihlal bildirimi. Yurt dışı aktarım hükümlerini değerlendirin.
- Supabase hesabında iki aşamalı doğrulama açık olsun. **service_role** anahtarı ve veritabanı şifresi yalnız sizde
  kalsın; hiçbir istemciye, e-postaya veya sohbete yazılmasın.
- Sözleşme bittiğinde okulun verisini teslim edin, sonra lisansı kapatın ve okulun satırlarını silin.

## 5. Güncelleme

Veritabanı değişiklikleri `supabase/migrations/` altına yeni dosya olarak eklenir ve `npx supabase db push` ile
bütün okullara bir anda uygulanır. İstemci için yeni Windows paketi / APK / web çıktısı dağıtılır.

## 6. Satıştan önce kontrol listesi

- [ ] `npx supabase db push` yapıldı; `cd supabase && npm test` ve `python -m pytest tests -q` geçti.
- [ ] Auth: e-posta doğrulama açık, Site URL ve SMTP tanımlı.
- [ ] Deneme okulunda: hesap aç → doğrula → kodla etkinleştir → kullanıcı davet et → davetli girişi → tanım kaydı →
      iki cihazda aynı kayıtta çakışma uyarısı → işlem kaydında iz.
- [ ] Satış faturası / ürün kartı ve KDV; okul yönetimi ile usul net.
- [ ] Veri işleme sözleşmesi taslağı hazır.
