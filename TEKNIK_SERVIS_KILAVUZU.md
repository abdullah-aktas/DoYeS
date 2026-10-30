# DÖSE Yönetim Sistemi — Teknik Servis ve Programcı Kılavuzu

Bu belge **başka bir programcı** veya **teknik servis elemanı** için yazılmıştır.  
Okul son kullanıcısı için: [`KURULUM.md`](KURULUM.md) · Satış / lisans / çok okullu barındırma: [`SATIS_REHBERI.md`](SATIS_REHBERI.md).

**Hedef senaryo (bu okul):** Tek okul, tek veritabanı, birden fazla kullanıcı ve farklı roller (müdür, TMY, sayman, alan şefi, öğretmen…). Mobil erişim okul Wi‑Fi’sinde ve mümkünse okul dışından.

**Sürüm kaynağı:** [`surum.json`](surum.json) · Depo: [github.com/abdullah-aktas/DoYeS](https://github.com/abdullah-aktas/DoYeS)

---

## 1. Mimari (ne neye bağlanır)

```
 [Flet masaüstü] ─┐
 [Android / web] ─┼── HTTP(S) API :8765 ──> [FastAPI sunucusu]
 [Tablet] ────────┘                              │
                                      SQLite / PostgreSQL / Supabase
```

| Bileşen | Ne işe yarar | Nerede |
|--------|----------------|--------|
| `DOSE_Yonetim.exe` | Flet masaüstü istemcisi | `C:\Program Files\DOSE Yonetim\` |
| `MobilSunucu\DOSE_Mobil_Sunucu.exe` | Tüm istemcilere API + web | Aynı klasör altında; **pencere açık kalmalı** |
| `veri\` | SQLite DB, `baglanti.json`, yedekler | Kurulum klasöründe; kaldırmada **silinmez** |
| `DOSE_Mobil.apk` | Android istemci | Kurulumda `mobil\` veya ayrı dağıtım |
| `satici\` | Lisans üretimi | **Yalnız geliştirici PC’sinde; okula gitmez** |

Hiçbir istemci **doğrudan veritabanına bağlanmaz**. Flet istemcileri kurum kodu + kullanıcı + şifre ile API sunucusuna bağlanır.

**Portlar**

| Port | Protokol | Amaç |
|------|----------|------|
| **8765** | TCP | Mobil API + web arayüzü |
| **8766** | UDP | Aynı Wi‑Fi’de otomatik sunucu keşfi |
| **5432** | TCP | PostgreSQL (yalnız merkezi sunucu modunda) |

---

## 2. Kaynak kod ve klasörler

| Klasör / dosya | İçerik |
|----------------|--------|
| `dose/` | Paylaşılan iş kuralları, DB, lisans ve belgeler |
| `mobil/` | Flet masaüstü / Android / web istemcisi |
| `sunucu/` | FastAPI ve web API |
| `tests/` | Birim testleri — paketlemeden önce geçmeli |
| `main.py` | Masaüstü giriş noktası |
| `sunucu_main.py` | Mobil sunucu giriş noktası |
| `exe_olustur.bat` | Test + PyInstaller + Inno Setup |
| `mobil/apk_aab_olustur.bat` | İmzalı APK + Play AAB |
| `kurulum.iss` | Windows kurulum betiği (`AppId` **değiştirilmez**) |

Geliştirme ortamı (Windows):

```powershell
cd D:\DÖSE
python -m pip install -r requirements.txt
python -m unittest discover -s tests
```

Bir terminalde `python sunucu_main.py`, ikincisinde `python main.py` çalıştırın. İlk giriş `admin / admin` →
şifre değiştirme zorunlu.

Python **3.10+** (paketleme için 3.11 kullanıldı). Mobil APK için ayrıca Flutter 3.41.x, Android SDK, JDK 17 gerekir; proje yolunda Türkçe karakter sorunu çıkarsa kaynak `C:\dose_mobil` gibi ASCII bir klasöre kopyalanıp derlenir.

---

## 3. Tek okul kurulum sırası (teknik servis)

### 3.1 Flet istemcisi

1. `DOSE_Yonetim_Kurulum_<sürüm>.exe` kur.
2. API sunucusunu başlat, ardından Flet istemcisini aç → `admin` / `admin` → yeni şifre.
3. **Kurum ve Görevliler:** okul adı + **MEB kurum kodu** (5–8 rakam).
4. Lisans gerekiyorsa giriş ekranındaki **Lisansı görüntüle / etkinleştir** düğmesini kullan.
5. **Personel** kartlarını gir → **Kullanıcılar** ile her kişiye rol ver.
6. Öğretmenleri personel kaydına, alan şeflerini bölüme bağla.
7. Gerekirse **Onay akışı etkin** ayarını aç.

### 3.2 Veri modeli seçimi

| Mod | Ne zaman | Not |
|-----|----------|-----|
| **Yerel (SQLite)** | Tek okul sunucusu | Varsayılan; `veri\dose.db` |
| **PostgreSQL / Supabase** | Birden çok istemci veya barındırma | `DOSE_DATABASE_URL` yalnız API sunucusunda; SSL ve veri konumu kurallarına uyun |

Flet masaüstü, web ve Android istemcileri aynı API sunucusunu ve aynı veritabanını kullanır.

### 3.3 API sunucusu (tüm istemciler için zorunlu)

1. Başlat → **DÖSE Mobil Sunucu** (veya `MobilSunucu\DOSE_Mobil_Sunucu.exe`).
2. Pencerede görünen adresi not et: örn. `http://192.168.1.10:8765` ve kurum kodu.
3. Windows Güvenlik Duvarı sorarsa **Özel ağlar** için izin ver.
4. Elle kural (yönetici PowerShell):

```powershell
New-NetFirewallRule -DisplayName "DOSE Mobil" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private
New-NetFirewallRule -DisplayName "DOSE Mobil Kesif" -Direction Inbound -Protocol UDP -LocalPort 8766 -Action Allow -Profile Private
```

5. Bilgisayar açılınca başlasın: kısayolu `shell:startup` klasörüne kopyala.
6. Bu PC’nin uyku / kapanma politikasını kapatın; sunucu kapalıysa mobil çalışmaz.

### 3.4 Android

1. `DOSE_Mobil.apk` yükle (bilinmeyen kaynak izni).
2. Giriş: **kurum kodu** + kullanıcı + şifre.
3. Aynı Wi‑Fi’de sunucu açıksa adres çoğu zaman **otomatik** bulunur.
4. Bulunamazsa **Gelişmiş: sunucu adresi…** → Mobil Sunucu penceresindeki adres → kaydet.

iPhone: tarayıcıda aynı adresi aç → Ana ekrana ekle (PWA benzeri web).

---

## 4. Okul dışından mobil (ev / sahadan)

Aynı Wi‑Fi’de değilseniz LAN keşif **çalışmaz**. Bu hata değildir. Tek okul için seçenekler:

### Seçenek A — Modem port yönlendirme (sık kullanılan)

1. Okulda Mobil Sunucu’nun çalıştığı PC’ye sabit yerel IP verin.
2. Modemde **TCP 8765** → o PC’ye yönlendirin.
3. Mümkünse HTTPS:

```text
DOSE_Mobil_Sunucu.exe --sertifika sunucu.crt --anahtar sunucu.key --port 8765
```

4. Telefonda Gelişmiş adres: `https://<sabit-ip-veya-alan-adı>:8765`  
   İmzasız sertifikada: **imzasız sertifikaya güven** kutusunu işaretleyin.
5. Personelin her birine bu adresi bir kez kaydettirin.

**Güvenlik:** Okul PC’sini internete açmak risklidir. En azından güçlü kullanıcı şifreleri, güncel Windows, mümkünse VPN veya HTTPS kullanın. 8765’i gereksiz yere dünyaya açmayın; sabit IP kısıtı / fail2ban benzeri önlemler düşünün.

### Seçenek B — VPN

Personel okul/MEM VPN’ine bağlanır → okul içi IP (`192.168…`) ile giriş. Sunucu internete açılmaz. Kurumsal güvenlik için tercih edilir.

### Seçenek C — Küçük VPS (TR)

Veri + Mobil Sunucu Türkiye’deki VPS’te; masaüstü de PostgreSQL’e bağlanır. Okul PC’sinin 7/24 açık olması gerekmez. KVKK / yurt içi veri saklama kurallarına uyun. Çok okullu `--coklu` geçidi **bu tek okul senaryosunda gerekmez**.

---

## 5. Kullanıcılar ve roller (destek için)

| Rol | Tipik görev |
|-----|-------------|
| Sistem Yöneticisi | Kullanıcı, bağlantı, yedek; onay imzası yok |
| Okul Müdürü | Son onay |
| Teknik Müdür Yardımcısı | Kontrol, tanım, işlem |
| Sayman | Fatura, kasa, muhasebe, yıl sonu |
| Alan Şefi | Bölüm siparişleri, uygun görüş |
| Öğretmen | İş talebi, kendi fazla çalışması |
| Memur / İzleyici | Veri girişi veya salt okunur |

**Destek ipuçları**

- Ortak hesap kullanmayın; ayrılan personelde hesabı silmek yerine **Aktif** kaldırın.
- Öğretmen mobilde işlem göremiyorsa: personel bağlantısı, bölüm, rol ve onay akışını kontrol edin.
- “Salt okunur” → lisans / deneme süresi dolmuş olabilir.
- Kurum kodu mobilde masaüstüyle **aynı** olmalı.

---

## 6. Sık sorunlar ve çözümler

| Belirti | Olası neden | Ne yapılır |
|---------|-------------|------------|
| Mobil: “Sunucu otomatik bulunamadı” | Farklı ağ / Mobil Sunucu kapalı | Sunucuyu aç; Wi‑Fi aynı mı bak; Gelişmiş’ten adres yaz |
| Mobil bağlanıyor ama giriş reddediliyor | Yanlış kurum kodu / şifre / pasif kullanıcı | Masaüstünden kullanıcıyı doğrula |
| Okul Wi‑Fi’de bile bulunamıyor | Güvenlik duvarı, misafir Wi‑Fi izolasyonu | TCP 8765 + UDP 8766; “AP izolasyonu” kapalı olsun |
| Masaüstü sunucuya bağlanamıyor | PG firewall, SSL, şifre | `KURULUM.md` §6 tablo |
| Kurulumda Windows uyarısı | İmzasız EXE | Ek bilgi → Yine de çalıştır |
| Güncelleme sonrası veri yok | Yanlış klasöre kurulum / AppId değişmiş | `veri` yedeğini kontrol et; `kurulum.iss` AppId’ye dokunma |
| İki kişi aynı kaydı bozuyor | Eşzamanlı düzenleme | Program üzerine yazmaz; güncel kaydı yeniden yükle |

**Hızlı teşhis (Mobil Sunucu PC’sinde)**

```powershell
# Dinleme
netstat -an | findstr 8765
# Yerel API (sunucu açıksa)
curl http://127.0.0.1:8765/api/durum
```

Telefonda tarayıcıdan `http://<okul-pc-ip>:8765` açılıyorsa ağ tamam; sorun APK adres/keşif tarafındadır.

---

## 7. Yedekleme ve güncelleme

### Yedek

- Program içinden: **Yedekleme / İşlem Kaydı → Şimdi yedekle**.
- Yerel modda kritik dosya: `veri\dose.db` (+ `baglanti.json` varsa).
- PostgreSQL: `pg_dump` (gece cron örneği `KURULUM.md` içinde).
- Yedeği okul dışında / ikinci diskte tutun.

### Güncelleme

1. Yeni `DOSE_Yonetim_Kurulum_<sürüm>.exe` kur (üzerine yazar; `veri` korunur).
2. Mobil APK değiştiyse telefona yeni APK verin.
3. Mobil Sunucu’yu kapatıp yeniden açın.
4. Kullanıcılara sürüm notunu iletin (`surum.json` → `notlar`).

---

## 8. Programcı: paketleme ve mobil derleme

### Sürüm numarası (üç yer aynı olsun)

1. `dose/__init__.py` → `SURUM`
2. `mobil/uygulama.py` → `SURUM`
3. `mobil/pyproject.toml` → `version`  
İsteğe bağlı: `surum.json` (`surum`, `notlar`, `tarih`, gerekirse `gecit`)

### Windows kurulum paketi

```text
exe_olustur.bat
→ testler
→ dist\DOSE_Yonetim\  (masaüstü + MobilSunucu + varsa mobil\DOSE_Mobil.apk)
→ kurulum_paketi\DOSE_Yonetim_Kurulum_<sürüm>.exe
```

Gereksinim: Python paketleri, PyInstaller, Inno Setup 6.

### Android APK / Play AAB

```text
mobil\android\signing.env.example → signing.env   (şifreler; Git'e girmez)
mobil\apk_aab_olustur.bat
→ mobil\DOSE_Mobil.apk
→ mobil\store\DOSE_Mobil_<sürüm>.apk
→ mobil\store\DOSE_Mobil_<sürüm>.aab   ← Play Console
```

- Keystore: `mobil/android/upload-keystore.p12` — **mutlaka yedekleyin**; kaybolursa Play güncellemesi yapılamaz.
- Bundle id: `tr.k12.meb.derikmtal.dosemobil`
- **iOS IPA yalnız macOS + Xcode** ile: `flet build ipa` (`[tool.flet.ios]`). Windows’ta üretilmez.

### Dokunulmaması gerekenler

| Öğe | Neden |
|-----|--------|
| `kurulum.iss` → `AppId` | Değişirse Windows güncelleme yeni kurulum sayar |
| `satici/ozel_anahtar.pem` | Lisans üretmenin tek yolu; okula / GitHub’a koyma |
| Okul `veri\` klasörü | Canlı veri; testte üzerine yazmayın |
| Play keystore / `signing.env` | Mağaza imzası |

---

## 9. Lisans (destek seviyesi)

- Deneme: 30 gün tam özellik.
- Süre bitince: **salt okunur** (veri silinmez; yeni kayıt/onay yok).
- Lisans **kurum koduna** bağlıdır; sunucu modunda bir kez girilir, tüm PC’lerde geçerli olur.
- Yenileme / yeni anahtar: satıcı tarafında `satici\lisans_uret.bat` (`SATIS_REHBERI.md`).
- Teknik servis okula anahtar **üretmez**; okul “Bilgileri kopyala” ile satıcıya iletir, gelen anahtarı etkinleştirir.

---

## 10. Teslim / devir kontrol listesi

Okulu veya projeyi başka teknisyene bırakırken:

- [ ] Kurulum EXE sürümü ve kurulduğu yol not edildi  
- [ ] Kurum kodu, okul adı doğrulandı  
- [ ] Lisans durumu (deneme / bitiş tarihi)  
- [ ] Yerel mi PostgreSQL mi; PG host/port/DB adı (şifre güvenli kanalda)  
- [ ] Mobil Sunucu hangi PC’de, sabit IP, startup’ta mı  
- [ ] Güvenlik duvarı 8765 (ve gerekirse 8766)  
- [ ] Okul dışı erişim: yok / port yönlendirme / VPN / VPS — adres yazılı  
- [ ] Admin şifresi teslim edildi; varsayılan `admin` değiştirildi  
- [ ] En az bir müdür + bir öğretmen hesabı test edildi (masaüstü + mobil)  
- [ ] Son yedek alındı ve nerede olduğu yazıldı  
- [ ] APK sürümü telefonlarla uyumlu  
- [ ] Bu kılavuz + `KURULUM.md` okul bilişim sorumlusuna verildi  

**Okula asla verilmez:** `satici\` klasörü, `ozel_anahtar.pem`, Play `signing.env` / keystore, geliştirici `.env` dosyaları.

---

## 11. Destek iletişimi ve sınır

- Son kullanıcı ekran adımları → `KURULUM.md`  
- Lisans satışı / çok okul VPS → `SATIS_REHBERI.md`  
- Kaynak / sürüm notları → GitHub Releases + `surum.json`  

Yazılım mevzuat ve muhasebe kurallarını uygular; **hukuki / mali nihai karar** okulun harcama yetkilisi ve muhasebe birimindedir. Teknik servis veri kaybını önlemek için işlem öncesi yedek almayı alışkanlık edinmelidir.

---

*Belge sürümü: DÖSE 1.7.2 ile uyumlu · Tek okul + çok kullanıcılı kurulum odaklı*
