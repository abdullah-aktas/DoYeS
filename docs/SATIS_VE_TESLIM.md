# Satışa hazırlık ve kuruma teslim

Bu belge **sizin** (ürünü satan / dağıtan tarafın) yapacağı işleri sırayla anlatır: ürünü satışa hazırlamak, paketi çıkarmak, okulu / kurumu açmak ve teslim etmek. Lisans SQL ayrıntıları [SATIS_REHBERI.md](SATIS_REHBERI.md); okul tarafındaki kurulum [KURULUM.md](KURULUM.md).

**Hedef:** Kurumda sunucu kurulmaz. Siz Supabase’i işletirsiniz; kuruma uygulama + etkinleştirme kodu + kısa kullanım yolu verirsiniz.

---

## 0. Ne satıyorsunuz?

| Teslim edilen | Açıklama |
|---|---|
| Yazılım lisansı (okula ait) | Süre + kurum kodu; bilgisayara bağlı değil |
| İstemci | Windows paketi ve/veya Android APK ve/veya web adresi |
| Etkinleştirme kodu | Tek kullanımlık `DOSE-…` (müdür ilk Okul Müdürü olur) |
| Destek kanalı | Telefon / e-posta / uzaktan yardım |
| Kullanım kılavuzu linki | [KULLANIM.md](KULLANIM.md) |

GİB e-Fatura gönderimi ve gerçek banka EFT API’si **ürün kapsamında değildir**; sözleşmede ve satış konuşmasında bunu net söyleyin.

---

## 1. Bir kez: altyapıyı hazırlayın

Bunlar her satışta değil, projeyi ilk kurarken (veya yeni Supabase projesinde) yapılır.

1. Supabase projesi oluşturun; bölgeyi KVKK / yönetim kararına göre seçin.
2. `npx supabase login` → `link` → `db push` ([KURULUM.md](KURULUM.md) §0).
3. Auth: e-posta doğrulama açık; Site URL + SMTP (doğrulama maili gelsin).
4. İstemci URL / anon anahtar: `istemci/ayar.py` veya `DOSE_SUPABASE_URL` / `DOSE_SUPABASE_ANAHTAR`.
5. **service_role** ve DB şifresi yalnız sizde; istemciye / sohbete / APK’ya koymayın.
6. İki aşamalı doğrulama (Supabase hesabı) açık olsun.
7. Veri işleme sözleşmesi taslağı hazır olsun ([SATIS_REHBERI.md](SATIS_REHBERI.md) §4).

Kontrol:

```powershell
cd supabase
npm install
npm test
cd ..
python -m pytest tests -q
```

Hepsi yeşil olmadan canlıya paket çıkarmayın.

---

## 2. Her sürüm / satış öncesi: ürünü kilitleyin

1. `istemci/pyproject.toml` → `version` numarasını güncelleyin (ör. `1.7.5`).
2. Son migration’lar canlıda: `cd supabase && npx supabase db push`.
3. Testleri tekrar çalıştırın (§1 sonu).
4. Deneme okulunda uçtan uca duman testi:
   - Hesap aç → e-posta doğrula → kodla okul aç **veya** 1 ay deneme
   - Kullanıcı davet → davetli giriş
   - Bir tanım kaydı (personel / cari)
   - İsteğe bağlı: sipariş taslağı, fatura önizleme (GİB yok), işlem kaydında iz
5. Satış ürün kartı (kendi DÖSE’nizde): «Yazılım lisansı (1 yıl)» vb.; KDV oranını güncel mevzuata göre girin ([SATIS_REHBERI.md](SATIS_REHBERI.md) giriş).

---

## 3. Dağıtım paketlerini üretin

Depo kökü: `D:\DÖSE` (veya klonunuz).

### Windows masaüstü

```powershell
cd istemci
flet build windows
```

Çıktı: `istemci/build/windows` (klasörü zip’leyip kuruma verin veya kurulum sihirbazı ile paketleyin).

Geliştirme / hızlı kontrol:

```powershell
pip install -r requirements.txt
python main.py
# veya
flet run -a istemci/assets
```

### Android (APK / Play AAB)

1. `istemci/android/signing.env.example` → `signing.env` (imza bilgileri; git’e eklemeyin).
2. Flutter / Android SDK / JAVA yolları `apk_aab_olustur.bat` içinde veya ortamda tanımlı olsun.
3. Çalıştırın:

```powershell
cd istemci
.\apk_aab_olustur.bat
```

APK’yı kurum içi yan yükleme için; AAB’yi Play Console için kullanın.

### Web

```powershell
cd istemci
flet build web
```

Çıktıyı HTTPS’li bir host’a koyun; kuruma **sadece URL** verin. Site URL’yi Supabase Auth’ta da tanımlayın.

### Paket içeriği kontrolü

- [ ] Logo / ikon görünüyor (`istemci/assets`)
- [ ] Giriş ve hesap açma çalışıyor
- [ ] Yanlış URL/anahtar yok (doğru Supabase projesi)

---

## 4. Kurumu (okulu) açın

Supabase **SQL Editor** (Dashboard; istemciden değil):

```sql
select dose_private.okul_ac(
  'Kurumun resmi adı',
  'MEB_KURUM_KODU',
  date '2027-08-31',   -- lisans bitişi; NULL = süresiz
  interval '7 days'    -- kodun geçerlilik süresi
);
```

Dönen `DOSE-…` kodunu **güvenli kanalla** (yüz yüze, imzalı e-posta, KEP vb.) iletin. Kod tek kullanımlıktır; 5 yanlış denemede kilitlenir.

Kayıp / kilit / süre dolumu:

```sql
select dose_private.etkinlestirme_kodu('MEB_KURUM_KODU', interval '3 days');
```

Lisans uzatma / kapatma: [SATIS_REHBERI.md](SATIS_REHBERI.md) §2.

**Alternatif:** Kurum müdürü uygulamadan **1 ay ücretsiz deneme** açabilir; ücretliye çevirirken `lisans_ayarla` kullanın.

---

## 5. Kuruma teslim dosyası (checklist)

Kuruma şu paketi verin:

| Madde | Var mı? |
|---|---|
| Windows zip / kurulum **veya** web URL **veya** APK | ☐ |
| MEB kurum kodu (onların bildiği) + etkinleştirme kodu | ☐ |
| Lisans bitiş tarihi yazılı (fatura / sözleşme) | ☐ |
| Kısa «ilk gün» notu (aşağıdaki §6) | ☐ |
| Destek iletişim (telefon / e-posta / çalışma saati) | ☐ |
| Link: [KULLANIM.md](KULLANIM.md) + [KURULUM.md](KURULUM.md) | ☐ |
| Veri işleme / lisans sözleşmesi imzalı | ☐ |
| Fatura / ödeme belgesi | ☐ |

Sözleşmede mutlaka: lisans süresi, kurum kodu, destek, güncelleme hakkı, verinin sizin Supabase projenizde tutulduğu, KVKK veri işleme şartları.

---

## 6. Kuruma söyleyeceğiniz «ilk gün» sırası

Müdüre (veya görevlendirdiği kişiye) şu sırayı yazın / söyleyin:

1. Uygulamayı açın (Windows / web / Android).
2. **Hesap aç** → e-postayı doğrulayın → **Giriş yap**.
3. Etkinleştirme kodu + MEB kurum kodu + ad soyad ile okulu bağlayın.
4. **Kurum bilgileri**ni doldurun.
5. **Kullanıcılar → Davet et** (sayman, TMY, alan şefi…).
6. **Tanımlar:** bölüm → personel → cari → malzeme → ürün (Excel şablonu ile toplu giriş mümkün).
7. Sayman: hesap planı / açılış bakiyesi; gerekirse merkez parametre doğrulaması.

Ayrıntılı adımlar: [KURULUM.md](KURULUM.md).

---

## 7. Teslim sonrası destek

| İstek | Sizin işiniz |
|---|---|
| Kod kayboldu / kilitlendi | `etkinlestirme_kodu` |
| Lisans uzatma | `lisans_ayarla` + fatura |
| «E-posta gelmiyor» | SMTP / spam / Site URL |
| «Salt okunur» | Lisans bitişi kontrol |
| Uygulama güncellemesi | Yeni Windows/APK/web + gerekirse `db push` |
| Veri silme / sözleşme sonu | Veriyi teslim → lisansı kapat → satırları sil (KVKK) |

Teknik teşhis: [TEKNIK_SERVIS_KILAVUZU.md](TEKNIK_SERVIS_KILAVUZU.md) §7.

---

## 8. Satış konuşması — kısa metin

> DÖSE Yönetim, döner sermaye işletmesi kayıtlarını bilgisayar, telefon ve tarayıcıda tek yerde tutar. Okulda sunucu kurulmaz; lisans okula aittir. Fatura ve kasa kayıtları yerel tutulur; GİB’e otomatik gönderim ve banka API’si yoktur — bu işlemler mevcut usulle yapılır. İlk günde müdür hesap açar, verdiğimiz kodla okulu etkinleştirir ve kullanıcıları davet eder.

---

## İlgili belgeler

| Belge | Ne zaman |
|---|---|
| [SATIS_REHBERI.md](SATIS_REHBERI.md) | SQL lisans, KVKK, fatura usulü |
| [KURULUM.md](KURULUM.md) | Okul tarafı kurulum |
| [KULLANIM.md](KULLANIM.md) | Kullanıcı rolleri |
| [GELISTIRICI.md](GELISTIRICI.md) | Kod / düzeltme (başka yazılımcılar) |
| [TEKNIK_SERVIS_KILAVUZU.md](TEKNIK_SERVIS_KILAVUZU.md) | Mimari, migration listesi, derleme |
