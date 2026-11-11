# Geliştirici kılavuzu

Bu belge, DÖSE Yönetim kod tabanında **özellik geliştiren veya teknik düzeltme yapan yazılımcılar** içindir. Satış/teslim [SATIS_VE_TESLIM.md](SATIS_VE_TESLIM.md); canlı servis teşhisi [TEKNIK_SERVIS_KILAVUZU.md](TEKNIK_SERVIS_KILAVUZU.md).

Okuyun → ortamı kurun → küçük bir değişiklikle test edin → migration kuralına uyun → PR / teslim.

---

## 1. Ürün özeti (30 saniye)

- **İstemci:** Flet 1.0.x (`istemci/`) — Windows, Android, web aynı kod.
- **Çekirdek:** `dose/` — hesap, mevzuat sabitleri, Excel/PDF (saf Python; UI yok).
- **Sunucu:** Tek Supabase projesi, çok okul (`okul_id` + RLS). İş kuralları SQL tetikleyici ve `SECURITY DEFINER` RPC’lerde.
- **Sır yok istemcide:** Yalnız anon/publishable anahtar. `service_role` asla istemciye veya sohbete konmaz.

Kapsam dışı (bilinçli): GİB e-Fatura gönderimi, banka EFT API’si. Belge resmi OCR için isteğe bağlı Tesseract; yoksa metin/ses yolu kullanılır.

---

## 2. Ortam kurulumu

Önkoşul: Python 3.10+, Node (Supabase testleri), Git. Windows PowerShell örnekleri.

```powershell
cd D:\DÖSE
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

cd supabase
npm install
cd ..
```

İstemci hedefi (geliştirme):

```powershell
# Logo için assets şart:
flet run -a istemci/assets
# veya
python main.py
```

Supabase uç noktası: `istemci/ayar.py` varsayılanları veya:

```powershell
$env:DOSE_SUPABASE_URL = "https://....supabase.co"
$env:DOSE_SUPABASE_ANAHTAR = "sb_publishable_..."
```

Canlı şemayı kendi makinenize çekmek (yetkili geliştirici; proje ref’i paylaşılan gizli bilgi):

```powershell
cd supabase
npx supabase login
npx supabase link --project-ref <PROJE_REF>
# Şema değişikliği varsa: npx supabase db push   (dikkat: tüm okullara uygulanır)
```

Yerel migration doğrulama (PGlite; canlı yerine geçmez):

```powershell
cd supabase
npm test
```

---

## 3. Depo haritası

| Yol | Ne işe yarar | Dokunurken |
|---|---|---|
| `main.py` | Masaüstü giriş + assets | Nadiren |
| `istemci/uygulama.py` | Oturum, kabuk, menü, canlı yenileme | Kabuk / tema / navigasyon |
| `istemci/tema.py` | Marka renkleri, kart / başlık bileşenleri | UI tutarlılığı |
| `istemci/ekranlar.py` | Ana, kurum, tanımlar (+ Excel/PDF içe aktarma), sipariş, kullanıcılar | Büyük dosya; dikkatli patch |
| `istemci/faturalar.py`, `kasa.py`, `finans.py` | Fatura, kasa, stok/yevmiye | RPC sözleşmesine uy |
| `istemci/parca_basi.py`, `fazla_calisma.py`, `hazine_payi.py`, `yil_sonu.py` | Bordro / hazine / ÜTP | Mevzuat RPC’leri |
| `istemci/supa.py` | Auth + REST + RPC istemcisi | Hata çevirisi, Prefer başlıkları |
| `istemci/tanimlar.py` | Form alanları, roller, sayı/tarih yazımı | Tanım içe aktarma alan listeleri |
| `dose/excel.py`, `pdf_ice.py` | Tanım Excel/PDF parse | Başlık eşleme |
| `dose/hesap.py`, `mevzuat.py` | Saf hesap | Birim test kolay |
| `supabase/migrations/` | Şema, RLS, RPC | **Yalnız sona yeni dosya ekle** |
| `supabase/tests/` | JS / PGlite | SQL davranışı |
| `tests/` | Python (pytest) | İstemci + dose |
| `docs/` | Kullanıcı / satıcı / teknik | Davranış değişince güncelle |

Sürüm numarası: `istemci/pyproject.toml` → `version`.

---

## 4. Mimari kurallar (bozmayın)

1. **Okul izolasyonu:** Her iş satırında `okul_id`; istemci filtreyi «güven»mez, RLS keser.
2. **Yazma yolu:** Kritik işlemler doğrudan `INSERT/UPDATE` ile değil, `dose_*` RPC ile (fatura, kasa, stok, sipariş onay, bordro…).
3. **Sürüm:** Güncellemede istemci okuduğu `surum`’u gönderir; çakışmada `P0001` + `hint = surum_cakismasi`.
4. **İdempotent kayıt:** Kritik formlarda işlem kimliği / UUID; çift tıklamada çift kayıt olmasın.
5. **Silme yok:** Çoğu yerde gerekçeli **ters kayıt**; `islem_log` değiştirilemez.
6. **Yetki:** `dose_private.sayfa_yetki` — rol × sayfa → `y` / `g`. Lisans bitince yazma düşer.
7. **Para / oran:** Sunucuda NUMERIC; istemcide Türkçe giriş (`1.250,50`, oran `20`) → `tanimlar` yardımcıları.
8. **UI-only değişiklik** RPC imzasını değiştirmez; şema değişikliği migration ister.

Ayrıntılı migration listesi: [TEKNIK_SERVIS_KILAVUZU.md](TEKNIK_SERVIS_KILAVUZU.md) §2.

---

## 5. Tipik iş akışları

### A) Salt arayüz / metin düzeltmesi

1. İlgili `istemci/*.py` dosyasını düzenleyin.
2. Ortak görünüm için `istemci/tema.py` bileşenlerini kullanın (`sayfa_baslik_satiri`, `yuzey_kart`, …).
3. `flet run -a istemci/assets` ile kontrol.
4. Gerekirse `docs/kullanim/*.md` güncelleyin.
5. `python -m pytest tests/test_istemci.py -q` (ilgili sınıflar).

### B) Hesap / Excel mantığı (`dose/`)

1. Saf fonksiyon yazın; Flet import etmeyin.
2. `tests/` altına birim test ekleyin.
3. İstemci yalnız sonucu göstersin.

### C) Veritabanı / iş kuralı değişikliği

1. **Mevcut migration dosyasını düzenlemeyin** (canlıda uygulanmış olabilir).
2. `supabase/migrations/YYYYMMDDHHMMSS_kisa_ad.sql` yeni dosya ekleyin.
3. RLS, yetki, tetikleyici ve RPC’yi aynı dosyada veya tutarlı sırayla düşünün.
4. `cd supabase && npm test`.
5. İstemci RPC parametre / dönüş şeklini güncelleyin.
6. Yetkili ortamda `npx supabase db push` (üretim = bütün okullar).
7. Satış/kullanım dokümanında davranış değiştiyse güncelleyin.

### D) Yeni ekran / menü maddesi

1. SQL’de sayfa anahtarı + `sayfa_yetki` satırları.
2. `istemci/uygulama.py` menü haritası.
3. Yeni modül veya mevcut ekran sınıfı; `Ekran` tabanı + `yukle` / `_ciz`.
4. Yazma yetkisi `app.yetki(...)` ile.

### E) Android / Windows paket

[TEKNIK_SERVIS_KILAVUZU.md](TEKNIK_SERVIS_KILAVUZU.md) §6 ve [SATIS_VE_TESLIM.md](SATIS_VE_TESLIM.md) §3. İmza dosyaları (`signing.env`) repoya girmez.

---

## 6. Test komutları

```powershell
# SQL / PGlite
cd supabase
npm test
cd ..

# Python (klasör adındaki Türkçe karakter yüzünden unittest discover yerine pytest)
python -m pytest tests -q

# Daraltılmış
python -m pytest tests/test_istemci.py::ExcelIceAktarmaTest -q
```

`tests/test_uctan_uca.py` yerel taklit sunucuya bağlanır; **canlı `db push` yerine geçmez**.

---

## 7. Kod stili (bu depo)

- Türkçe kullanıcı metinleri; kod kimlikleri çoğunlukla Türkçe (`yukle`, `kaydet`, `okul_id`).
- Mevcut import düzeni: `try: from .x` / `except: import x` (paket ve düz çalıştırma).
- Gereksiz bağımlılık eklemeyin; Flet sürümü `requirements.txt` / `pyproject.toml` ile kilitli (`flet==1.0.5`).
- Büyük “refactor her şeyi” PR’larından kaçının; davranış + test + kısa doküman.
- Gizli anahtar, `signing.env`, service_role commit edilmez.

---

## 8. Hata ayıklama ipuçları

| Belirti | Bakılacak yer |
|---|---|
| Logo yok | `flet run` için `-a istemci/assets` |
| 401 / oturum | `supa.py` refresh; Auth SMTP |
| «yetkiniz yok» / boş PATCH | RLS veya rol; RPC mi tablo mu |
| Sürüm çakışması | Başka oturum kaydetti; yenile |
| «Veritabanı kurulumu tamamlanmamış» | Eksik migration / `db push` |
| PDF içe aktarma boş | Tarama PDF → PNG/JPG veya metin/ses; `dose/gorsel_ice.py` |
| Para yuvarlama | Sunucu NUMERIC vs istemci `Decimal` |

Canlı log: Supabase Dashboard → Logs (API / Postgres).

---

## 9. Güvenlik kontrol listesi (her PR)

- [ ] İstemciye service_role / DB şifresi eklenmedi
- [ ] Yeni tablo / RPC’de `okul_id` ve RLS düşünüldü
- [ ] Yazma yolu yetki kontrolünden geçiyor
- [ ] Migration geriye dönük uyumlu veya bilinçli kırılma dokümante
- [ ] Test eklendi veya mevcut test güncellendi

---

## 10. Teslim / iş birliği

1. Değişikliği kendi dalınızda yapın; `main`’e doğrudan zorlamayın (ekip kuralına göre).
2. PR / iş notunda: **neden**, etkilenen ekran/RPC, migration adı, manuel test adımları.
3. Satışa çıkacak sürümde [SATIS_VE_TESLIM.md](SATIS_VE_TESLIM.md) §2 kontrol listesini işletici uygular.

Sorular için önce bu dosya + [TEKNIK_SERVIS_KILAVUZU.md](TEKNIK_SERVIS_KILAVUZU.md); kullanıcı davranışı için [KULLANIM.md](KULLANIM.md).

---

## Hızlı komut özeti

```powershell
pip install -r requirements.txt
flet run -a istemci/assets
cd supabase; npm test; cd ..
python -m pytest tests -q
cd istemci; flet build windows
```
