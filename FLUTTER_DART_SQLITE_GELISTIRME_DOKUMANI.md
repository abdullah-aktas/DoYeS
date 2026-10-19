# DÖSE — Flutter, Dart ve SQLite Geliştirme Dokümanı

**Doküman sürümü:** 1.2  
**Tarih:** 16 Ekim 2026  
**Durum:** Geliştirme öncesi ürün ve teknik tasarım; uygulanmış sistem değildir.  
**Hedef:** Mevcut DÖSE işlevlerini referans alarak web tabanlı ortak altyapıyla çalışan, işlevsel olarak eşdeğer masaüstü ve mobil uygulamaları sıfırdan geliştirme.

> **Kullanıcının kesinleştirdiği tercihler:** Ön yüz Flutter, arka uç Dart, veritabanı SQLite olacaktır. Mevcut Python sunucusu korunmayacaktır. SQLite yalnız merkezi sunucuda bulunacak; bütün cihazlar aynı veriye Dart API üzerinden erişecektir.
>
> **Ürün sınırı:** Bir web sitesi, tarayıcı uygulaması veya PWA geliştirilmeyecektir. “Web tabanlı”, kurulabilir masaüstü ve mobil uygulamaların internet üzerinden HTTPS/API ile aynı merkezi sisteme bağlanması anlamındadır; WebView içine alınmış bir site anlamına gelmez. Mobil uygulama kısıtlı bir yardımcı uygulama değil, masaüstüyle aynı işlevleri sunan tam istemcidir.
>
> **Göreve göre kullanım:** Farklı kullanıcı tipleri bulunacaktır. Kullanıcının görev, rol, işlem ve veri kapsamı yetkilerini okul yönetimi veya kurumun tam yetkili kullanıcısı verecek, değiştirecek ve kaldıracaktır. Uygulamaların eşdeğerliği herkesin her işlemi yapması değil, aynı kullanıcının iki cihazda da aynı yetkilerle çalışmasıdır.
>
> Bu belge bir uygulama geliştirme şartnamesidir. Mevcut kodun içerdiği mevzuat açıklamaları ve hesaplar güncel hukuki doğruluk garantisi sayılmaz. Canlıya geçmeden önce yetkili mali personel tarafından doğrulanmalıdır.

## İçindekiler

1. [Amaç ve kapsam](#1-amaç-ve-kapsam)
2. [Mevcut projenin referans envanteri](#2-mevcut-projenin-referans-envanteri)
3. [Kararlar ve kapsam sınırları](#3-kararlar-ve-kapsam-sınırları)
4. [Hedef sistem mimarisi](#4-hedef-sistem-mimarisi)
5. [Teknoloji ve paket seçimi](#5-teknoloji-ve-paket-seçimi)
6. [Depo ve kod organizasyonu](#6-depo-ve-kod-organizasyonu)
7. [Roller ve yetkilendirme](#7-roller-ve-yetkilendirme)
8. [Modül gereksinimleri](#8-modül-gereksinimleri)
9. [Temel iş akışları](#9-temel-iş-akışları)
10. [Veri modeli](#10-veri-modeli)
11. [Para, oran ve hesaplama kuralları](#11-para-oran-ve-hesaplama-kuralları)
12. [SQLite işletim ve eşzamanlılık tasarımı](#12-sqlite-işletim-ve-eşzamanlılık-tasarımı)
13. [API sözleşmesi](#13-api-sözleşmesi)
14. [Kimlik doğrulama ve güvenlik](#14-kimlik-doğrulama-ve-güvenlik)
15. [Flutter uygulama tasarımı](#15-flutter-uygulama-tasarımı)
16. [Platform davranışları](#16-platform-davranışları)
17. [Bildirim ve bağlantı yönetimi](#17-bildirim-ve-bağlantı-yönetimi)
18. [Raporlama ve belgeler](#18-raporlama-ve-belgeler)
19. [Eski sistemden veri ve kural aktarımı](#19-eski-sistemden-veri-ve-kural-aktarımı)
20. [Test ve kabul ölçütleri](#20-test-ve-kabul-ölçütleri)
21. [Dağıtım ve işletim](#21-dağıtım-ve-işletim)
22. [Yedekleme ve felaket kurtarma](#22-yedekleme-ve-felaket-kurtarma)
23. [Geliştirme aşamaları](#23-geliştirme-aşamaları)
24. [Riskler ve açık kararlar](#24-riskler-ve-açık-kararlar)
25. [İlk geliştirme iş listesi ve tamamlanma tanımı](#25-ilk-geliştirme-iş-listesi-ve-tamamlanma-tanımı)
26. [Kaynaklar](#26-kaynaklar)

## 1. Amaç ve kapsam

DÖSE; mesleki ve teknik eğitim kurumlarının döner sermaye işletmelerinde sipariş, üretim, maliyet, stok, fatura, tahsilat, ücret, onay, muhasebe ve yasal yükümlülük süreçlerini birlikte yönetir.

Yeni sistemin amacı yalnız mevcut ekranları Flutter ile yeniden çizmek değildir. Amaç:

- Bir kaydı telefon, tablet ve masaüstünde aynı yetkiler ve iş kurallarıyla yönetmek.
- Finansal hesaplamaları merkezi ve izlenebilir yapmak.
- Rol, bölüm ve kişi kapsamını bütün API işlemlerinde uygulamak.
- Onay geçmişini, hesaplama dayanaklarını ve muhasebe izini korumak.
- Veriyi kullanıcı cihazlarındaki ayrı dosyalara dağıtmadan ortak çalışmayı sağlamak.
- Eski sistemin verisini mutabakatlı biçimde taşıyabilmek.

### 1.1 Hedef platformlar

| Platform | Ürün biçimi | İşlev kapsamı |
|---|---|---|
| Windows | Kurulabilir Flutter masaüstü uygulaması | Yetkiye bağlı bütün modüller ve işlemler |
| Android | Kurulabilir Flutter mobil/tablet uygulaması | Masaüstüyle aynı modüller ve işlemler; dokunmatik uyumlu sunum |
| iOS | Kurulabilir Flutter mobil/tablet uygulaması | Aynı tam işlev kapsamı; macOS derleme altyapısı gerekir |
| macOS / Linux | İsteğe bağlı yerel masaüstü | İlk sürüm zorunluluğu değildir; paket uyumluluğu ayrıca doğrulanır |

**Önemli ayrım:** Kullanıcı bilgisayarına veya telefonuna uygulamayı kurar; işlemleri tarayıcıdan yapması gerekmez. Flutter arayüzleri cihazda çalışır; veri ve yetkili iş kuralları merkezi Dart sunucusundadır. Web sitesi, Flutter Web çıktısı ve PWA dağıtımı kapsam dışıdır.

### 1.2 Başarı tanımı

Yetkili kullanıcı bir siparişi masaüstünden veya mobilden oluşturabilmeli, diğer cihazdan düzenleyip süreci sürdürebilmelidir. Fatura, tahsilat, muhasebe, bordro, yıl sonu ve yönetim işlemleri de aynı yetkiyle her iki uygulamada tamamlanabilmelidir. Bu zincirde veri kopyalama, manuel dosya paylaşımı ve farklı hesaplama sonucu olmamalıdır.

### 1.3 İşlevsel eşdeğerlik sözleşmesi

- Aynı kurum, rol, kişi/bölüm kapsamı, lisans ve kayıt durumu için masaüstü ile mobilde aynı iş eylemleri sunulur.
- Mobilde yalnız onay, puantaj ve özet ekranları sunmak yeterli değildir; bölüm 8'deki bütün modüller iki istemcide de uygulanır.
- Yetki kısıtı kullanıcıya bağlıdır; cihaz türü mali işlem veya yönetim yetkisini daraltmaz.
- Ekran yerleşimi, veri giriş yöntemi, dosya seçici, paylaşım ve yazıcı erişimi cihaza göre uyarlanabilir. Bunlar işlev eksiltme gerekçesi değildir.
- Aynı girdi ve kayıt sürümü aynı hesap sonucunu, onay geçişini, rapor içeriğini ve işlem izini üretir.
- Eşdeğerlik, bölüm 20'deki çapraz platform kabul matrisiyle doğrulanır; yalnız ortak API veya ortak kod kullanmak yeterli sayılmaz.

## 2. Mevcut projenin referans envanteri

Aşağıdaki gözlemler mevcut kaynak dosyalarına dayanmaktadır; yeni sistemin gerçekleşmiş özellikleri değildir.

| Mevcut yüzey | Gözlenen yapı | Yeni sistem açısından karşılığı |
|---|---|---|
| [Bağımlılıklar](requirements.txt) | PySide6, FastAPI, Flet, SQLite/PostgreSQL erişimi, PDF ve Excel araçları | Flutter + Dart sunucusuna yeniden uygulama |
| [Masaüstü ekranları](dose/ui/sayfalar) | Tanımlar, maliyet, sipariş, fatura, kasa, stok, ücretler, yıl sonu, raporlar | Modül ve ekran envanteri |
| [Hesap motoru](dose/hesap.py) | Vergi, iskonto, tahsis, kesinti, dağıtım ve tavan işlemleri | Dart domain paketinin davranış referansı |
| [Mevzuat ve parametreler](dose/mevzuat.py) | Yıllık parametreler, görevler, listeler ve hesap planı | Sürümlü kural/parametre modeli |
| [Yetkiler](dose/yetki.py) | Sekiz rol, ekran yetkileri, bölüm kısıtları ve onay zincirleri | Açık izin kodları + kaynak kapsamı |
| [Onay motoru](dose/onay.py) | Gönderme, uygun görüş, onay, iade, geri çekme ve geri alma | Durum makinesi ve işlem kuralları |
| [Veritabanı](dose/db.py) | Kurum, personel, öğrenci, sipariş, fatura, stok, bordro, muhasebe ve işlem kayıtları | Yeni, kısıtları belirgin SQLite şeması |
| [Mobil API](sunucu/api.py) | Oturum, panel, onay, sipariş, fazla çalışma, stok, kasa ve fatura listeleri | Daha kapsamlı ve sürümlü yeni API |
| [Mobil uygulama](mobil/uygulama.py) | Flet tabanlı mobil/web istemcisi | Flutter istemcisine yeniden uygulama |
| [Kurulum rehberi](KURULUM.md) | Yerel ve merkezi çalışma, ortak veri, lisans, mobil kullanım | İşletim ve geçiş gereksinimleri |
| [Satıcı rehberi](SATIS_REHBERI.md) | Kurum lisansı, deneme, salt okunur kullanım ve dağıtım | Yeni lisans/işletim tasarımı |
| [Testler](tests) | Hesap, onay, mevzuat, eşzamanlılık, API, mobil ve yıl senaryoları | Yeni testlerin giriş/çıkış örnekleri |

### 2.1 Korunacak ürün davranışları

- Kurum, mali yıl, bölüm/alan ve personel ilişkileri.
- Öğretmenin kendi kayıtları; alan şefinin kendi bölümü ile sınırlı işlemleri.
- Sipariş → üretim → kabul → fatura → tahsilat ilişkisi.
- Ücret ve yıl sonu hesaplarında onay ve hesaplama geçmişi.
- Çakışan düzenlemelerde sessiz üzerine yazmama.
- Kullanıcı, zaman, kaynak cihaz ve değişiklik alanlarını izleme.
- Lisans sonrasında mevcut veriye erişim, rapor ve dışa aktarımın korunması.

### 2.2 Aynen kopyalanmayacak teknik davranışlar

- İstemciye veritabanı bağlantı bilgisi verme veya doğrudan veritabanına bağlanma.
- Eski tablolardaki `REAL` parasal alanlarını yeni şemaya aynı tipte taşıma.
- Ekran adını yetki anahtarı yapmak.
- Onay zincirinde görevli bulunmayınca aşamayı otomatik atlamak.
- Geçmiş hesapları güncel parametrelerle kendiliğinden yeniden hesaplamak.
- Kesinleşmiş finansal kayıtları fiziksel olarak silmek.

Bu değişiklikler bilinçli hedef tasarım farklarıdır. Özellikle onay aşaması atlama ve geri alma davranışı mali süreç sorumlularıyla pilot öncesinde yazılı olarak onaylanmalıdır.

## 3. Kararlar ve kapsam sınırları

### 3.1 Kesinleşmiş mimari kararlar

| Karar | Sonuç |
|---|---|
| Tek Flutter istemci kod tabanı | Ortak özellikler ve platforma uygun sunum |
| Kurulabilir masaüstü ve mobil ürünler | Web sitesi, tarayıcı istemcisi ve PWA yok |
| İşlevsel eşdeğerlik | Aynı yetkiyle her iki istemcide aynı modüller ve iş eylemleri |
| Sıfırdan Dart arka uç | Eski Python çalışma zamanına canlı bağımlılık yok |
| Sunucuda merkezi SQLite | Verinin tek yetkili kaynağı sunucudur |
| HTTPS üzerinden API | Hiçbir cihaz veritabanı dosyasını açmaz |
| Merkezi iş kuralları | İstemcinin gönderdiği toplam/onay/yetki bilgisine güvenilmez |

### 3.2 Bu belgenin önerdiği başlangıç kapsamı

- İlk pilot tek kurum ve bir merkezi sunucudur.
- Şema kurum ayrımına hazırlanır; çok kurumlu ticari hizmet ayrı kabul kapısıdır.
- İlk üretim hattı Windows + Android'dir; iOS aynı tam işlev kapsamıyla, ayrı derleme ve mağaza takvimiyle sunulur. iOS'un ilk yayına dahil olup olmadığı açık karardır.
- Modüller aşamalı geliştirilir; her teslim edilen modül masaüstü ve mobilde birlikte tamamlanır.
- İnternet olmadan finansal kayıt, onay veya ödeme işlemi yapılmaz.
- İlk sürümde Redis, mikroservis, Kubernetes ve dağıtık veritabanı zorunlu değildir.
- GİB, MEB, banka veya e-imza ile doğrudan entegrasyon ilk sürümün varsayılan parçası değildir.
- Sunucuya bağlı istemci yaklaşımı, uygulamanın telefona kurulsa bile sunucuya ihtiyaç duyduğu anlamına gelir.

### 3.3 İlk sürüm dışında tutulacaklar

Web sitesi, tarayıcı istemcisi ve PWA ürün kapsamı dışındadır. Ayrıca tam çevrimdışı muhasebe, çift yönlü veri senkronizasyonu, cihazlar arası SQLite birleştirme, aktif-aktif sunucu kümesi, otomatik banka ödeme emri ve doğrulanmamış resmî servis entegrasyonları ilk sürüm dışında tutulur.

## 4. Hedef sistem mimarisi

```text
Flutter masaüstü ──────────┐
                          ├── HTTPS ── Ters vekil / TLS
Flutter mobil/tablet ──────┘                 │
                                      Dart API sunucusu
                                            │
                                     Uygulama servisleri
                                            │
                                  İş kuralları + yetki + onay
                                            │
                                   Drift / SQLite erişimi
                                            │
                                      Merkezi SQLite

Sunucuya bağlı ek hizmetler:
Belge deposu • rapor işleri • işlem izi • bildirim kutusu • yedekleme
```

### 4.1 Katman sorumlulukları

1. **Sunum:** Flutter ekranı, form durumu, erişilebilirlik ve kullanıcı etkileşimi.
2. **İstemci veri katmanı:** API çağrısı, DTO dönüşümü, oturum ve geçici önbellek.
3. **HTTP katmanı:** İstek doğrulama, kimlik, hız sınırı, hata sözleşmesi ve izleme kimliği.
4. **Uygulama servisi:** Bir kullanım senaryosunun yetki, işlem ve yan etki sınırı.
5. **Domain:** Para, vergi, maliyet, onay geçişi ve hesaplama kuralları.
6. **Veri erişimi:** Sorgular, şema, indeksler, migration ve transaction.
7. **Altyapı:** Dosya, PDF, e-posta/push adaptörü, zamanlanmış işler ve yedekleme.

**Tercih:** Modüler monolit. Tek sunucu uygulaması içinde açık modül sınırları; dağıtık işlem karmaşıklığı yok.

### 4.2 Merkezi tutarlılık ilkesi

Bir satış belgesinin kesinleştirilmesi sırasında gereken belge durumu, stok hareketi, muhasebe fişi, işlem izi ve bildirim kutusu kaydı aynı veritabanı transaction'ında oluşur. PDF üretimi ve dış bildirim gönderimi transaction dışında yapılır.

İşlemin ardından telefon bildirim alamasa bile finansal kayıt geri alınmaz. Bildirim işi yeniden denenir; başarısızlığı görünür olur.

## 5. Teknoloji ve paket seçimi

Aşağıdaki liste hedef seçimdir; uyumlu sürümler ilk teknik denemede belirlenip kilitlenmelidir. Burada güncelliği doğrulanmamış sürüm numarası verilmez.

| Alan | Öneri | Kullanım ve sınır |
|---|---|---|
| İstemci | Flutter stable + Dart | Sürüm CI ve geliştirici makinelerinde aynı |
| Görsel sistem | Material 3 | Ortak tema ve responsive bileşenler |
| Durum yönetimi | `flutter_riverpod` | Oturum, filtreler ve asenkron ekran durumları |
| Yönlendirme | `go_router` | Uygulama içi rotalar, derin bağlantı ve erişim yönlendirmesi |
| HTTP istemcisi | `dio` | Zaman aşımı, iptal, standart hata dönüşümü |
| Model üretimi | `json_serializable`; gerekirse `freezed` | Açık JSON sözleşmeleri; gereksiz üretim katmanı yok |
| Yerelleştirme | Flutter `gen_l10n`, `intl` | Türkçe metin, tarih ve para gösterimi |
| Sunucu HTTP | `shelf`, `shelf_router` | Basit Dart HTTP ve middleware hattı |
| SQLite katmanı | `drift` + `sqlite3` | Yalnız sunucuda; tipli sorgular ve migration |
| Kimlik saklama | Native güvenli depo adaptörü | Platform desteği ve anahtar kasası davranışı ayrı test edilir |
| PDF | Dart `pdf`; istemcide `printing` değerlendirmesi | Yetkili belge sunucuda üretilir; çıktı platformda test edilir |
| Excel | Bakımı ve lisansı doğrulanmış Dart XLSX paketi | Büyük veri, formül enjeksiyonu ve Türkçe karakter testi zorunlu |
| Test | Dart `test`, Flutter test araçları, `integration_test` | Domain, API, widget ve uçtan uca test |
| Sözleşme | OpenAPI 3.x | İstek/yanıt, yetki ve hata dokümantasyonu |

`shelf` kendi başına kimlik sağlayıcısı, ORM, iş kuyruğu veya güvenlik paketi değildir. Bu sorumluluklar açık servisler ve bakımı doğrulanmış kütüphanelerle tamamlanır.

`sqflite` istemcilere merkezi veritabanı erişimi sağlamak için kullanılmaz. Masaüstü ve mobil aynı merkezi SQLite dosyasını doğrudan açmaz; Dart API'ye bağlanır. İlk sürümde istemci tarafı SQLite gerekmemektedir.

## 6. Depo ve kod organizasyonu

Önerilen yeni depo yapısı:

```text
dose_yeni\
  apps\
    dose_app\
      lib\
        app\
        core\
        shared\
        features\
          auth\
          dashboard\
          definitions\
          orders\
          inventory\
          invoices\
          cash_bank\
          payroll\
          approvals\
          year_end\
          accounting\
          reports\
          administration\
      test\
      integration_test\
  server\
    bin\
    lib\
      http\
      application\
      domain\
      infrastructure\
      database\
      jobs\
    test\
  packages\
    dose_contracts\
    dose_finance\
  docs\
    api\
    operations\
  tools\
    migration\
```

### 6.1 Paylaşılan paketler

- `dose_contracts`: DTO, enum, hata kodu ve serileştirme; Flutter bağımlılığı içermez.
- `dose_finance`: Saf Dart para/değer nesneleri ve hesaplama fonksiyonları; veritabanı veya HTTP içermez.
- İstemci hesapları anlık önizleme için kullanabilir; sunucu her kayıtta yeniden hesaplar.
- Paylaşılan paket, sunucu erişim anahtarı veya yalnız sunucuya ait yetkilendirme verisi içermez.
- Veritabanı entity'leri doğrudan API modeli olarak yayımlanmaz.

Feature içinde sunum, durum ve API deposu ayrılır. Her küçük ekran için gereksiz interface/use-case dosyaları üretmek yerine modül büyüklüğüyle orantılı yapı kurulur.

## 7. Roller ve yetkilendirme

Yetkilendirme modeli **rol + görev + işlem izni + veri kapsamı** birleşimine dayanır. Hazır kullanıcı tipleri başlangıç şablonlarıdır; okul yönetimi veya kurumun tam yetkili kullanıcısı kişilere uygun görevleri atar. Kullanıcı kendi rolünü seçerek veya unvanını değiştirerek yetki kazanamaz. Atanmamış izin varsayılan olarak reddedilir.

### 7.1 Rol matrisi

| Rol | Ana görev | Kaynak kapsamı | Finansal/onay sınırı |
|---|---|---|---|
| Tam yetkili kurum kullanıcısı | Kurumdaki kullanıcıları, rol şablonlarını ve yetki verme yetkisini yönetir | Yalnız yetkili olduğu kurum | Tam uygulama yönetimi mali görev/imza atamasının yerine geçmez |
| Okul yönetimi / yetki yöneticisi | Kendisine verilen sınırlar içinde kullanıcı, görev ve işlem yetkisi atar | Kendi kurumu ve devredilen kapsam | Yetki yönetimi izni tek başına mali onay hakkı vermez |
| Sistem yöneticisi | Kullanıcı, kurum, bağlantı, işletim ve yedek | Yetkili kurum | Teknik yönetici olması mali imza yetkisi vermez |
| Okul müdürü | Harcama yetkilisi ve son onay | Kurum | Tanımlı akışlarda son onay |
| Teknik müdür yardımcısı | Gerçekleştirme kontrolü ve hazırlık | Kurum | Kontrol aşaması; ödeme yetkisi ayrıca tanımlanır |
| Sayman | Fatura, kasa, muhasebe, vergi ve yıl sonu hazırlığı | Kurum | Mali kayıt ve yetkili ödeme işaretleme |
| Alan şefi | İş ve ücret hazırlığı, uygun görüş | Atandığı bölüm/alan | Başka bölümün kaydını değiştiremez |
| Öğretmen | İş talebi ve kendi puantajı | Kendi kayıtları + izin verilen bölüm işleri | Başkasının ücretine ve mali kimlik verisine erişemez |
| Memur / veri girişi | Yetkilendirilmiş tanım ve belge girişi | Atanan işlem alanı | Mali onay yetkisi yok |
| İzleyici / denetçi | Rapor ve kayıt inceleme | Verilen denetim kapsamı | Değişiklik yapamaz; kişisel veri yetkisi ayrıdır |

### 7.2 Uygulama kuralları

- İzinler `orders.create`, `orders.submit`, `approvals.decide`, `invoices.post`, `payments.record`, `reports.export` gibi sabit kodlarla tanımlanır.
- Kontrol sırası: oturum → kurum → izin → bölüm/kişi kapsamı → kayıt durumu → lisans → dönem kilidi.
- Butonu gizlemek güvenlik değildir; her kontrol API'de yeniden yapılır.
- Liste, detay, toplam, dosya indirme ve dışa aktarım aynı kaynak kapsamını uygular.
- Kullanıcının birden fazla görevi varsa izin bileşimi ve mali görev ayrılığı birlikte değerlendirilir.
- Vekâlet başlangıç/bitiş tarihi, kapsam ve atayan kişiyle kaydedilir.
- Öğrenci ve personel TCKN/IBAN alanları ayrı izin olmadan maskelenir.
- Sistem yöneticisinin onay kaldırma gibi eski ayrıcalıkları otomatik devralınmaz; hedef politikada açık izin ve gerekçe gerekir.

### 7.3 Yetki verme ve devretme modeli

- İlk kurum kurulumunda kimliği doğrulanan bir tam yetkili kurum kullanıcısı atanır. Bu kullanıcı okul müdürü olabilir; teknik servis hesabı kendiliğinden bu statüyü kazanmaz.
- Tam yetkili kullanıcı okul yönetiminden belirlenen kişilere `authorization.manage` izni ve hangi rol/izinleri hangi kapsamda verebileceklerini tanımlar.
- Okul yönetimi adına yetki verecek kişi açıkça atanır. “Müdür yardımcısı” gibi görünen unvanlar tek başına yetki yönetimine erişim sağlamaz.
- Bir işlemi yapabilmek ile o işlem için başkasına yetki verebilmek ayrıdır. Örneğin ödeme kaydı yapabilen sayman, ayrıca yetkilendirilmedikçe başkasına ödeme izni veremez.
- Yetki yöneticisi yalnız kendisine devredilmiş rol/izinleri, kurum/bölüm kapsamını ve süre sınırını aşmadan atama yapabilir. Kendi erişimi değişse bile devredilebilir izin sınırı ayrıca denetlenir.
- Tam yetkili statüsünü atama/devretme ayrı `authorization.owner.assign` izni gerektirir; normal yetki yöneticisi kendisini veya başka bir kullanıcıyı bu statüye yükseltemez.
- Son aktif tam yetkili kullanıcının kaldırılması, pasife alınması veya atamasının sona erdirilmesi, doğrulanmış bir halef olmadan engellenir.
- Kullanıcı kendi yetkisini artıramaz. Tam yetkili kullanıcı da kayıt durumu, dönem kilidi, lisans ve mali görev ayrılığı kurallarını atlayamaz.
- Rol tanımını düzenlemek de yetki verme işlemidir. Role yeni izin ekleme, mevcut bütün üyelerdeki etkisi gösterilerek aynı devretme sınırlarına tabi tutulur.
- Mali onay için uygulama iznine ek olarak geçerli görevlendirme ve ilgili onay aşaması gerekir. İşlem izni vermek, hukuken bulunmayan bir imza yetkisi oluşturmaz.

### 7.4 Yetki yönetimi ekranı ve atama akışı

Masaüstü ve mobilde aynı kapsamda **Kullanıcılar ve Yetkiler** ekranı bulunur:

1. Yetkili yönetici kullanıcıyı oluşturur veya mevcut kurum üyesini seçer; personel bağlantısını belirler.
2. Hazır rol seçer: sayman, alan şefi, öğretmen, memur, denetçi gibi. Gerekiyorsa yetki sınırları içinde kuruma özel rol şablonu tanımlar.
3. Görevi, bölüm/alan veya yalnız kendi kayıtları kapsamını, başlangıç/bitiş tarihini ve varsa vekâleti belirler.
4. Modül bazında görüntüleme, oluşturma, düzenleme, onaya gönderme, onay/iade, kesinleştirme/ödeme ve rapor/dışa aktarım izinlerini inceler.
5. İzin ekleme veya kişiye özel kısıtlama yaparsa gerekçe girer. Ekran kayıt öncesinde kullanıcının fiilî yetkilerini ve önceki durumdan farkını gösterir.
6. Sunucu atayanın yetkisini ve devretme sınırını yeniden kontrol eder; atama, yetki sürümü ve işlem izini tek transaction'da kaydeder.
7. Kullanıcı bilgilendirilir; açık istemciler menü ve izinlerini yeniler. Yetkiyi kaybeden kullanıcı eski ekran açık olsa da işlem yapamaz.

Atama geçmişinde kim, kime, hangi rol/izin/kapsamı, hangi süre ve gerekçeyle verdi veya kaldırdı bilgisi tutulur. Geçmiş kayıtlar yeni atamayla silinmez.

### 7.5 Etkin yetki hesaplama ve güncelleme

- Rol izinleri, yalnız o rol atamasının kapsamı ve geçerlilik süresi içinde etkilidir. Bir rolün kurum kapsamı başka bir rolün yalnız kişisel iznini genişletmez.
- Geçerli rol izinleri ve açık ek izinler birleştirilir; kişiye özel açık yasak, pasif üyelik, süre bitimi ve zorunlu görev ayrılığı kısıtları önceliklidir.
- Açık ek izinler de rol atamasıyla aynı yetki devretme, süre, kapsam ve işlem izi kurallarına tabidir.
- Her API isteği güncel üyelik ve yetki sürümünü denetler. Eski token içindeki rol bilgisine tek başına güvenilmez; sunucu yetki önbelleği değişiklikte geçersizleştirilir.
- Kritik yazmada yetki, kayıt sürümü ve görev durumu transaction içinde tekrar kontrol edilir. Yetki kaldırma tamamlandıktan sonra başlayan işlem eski izinle tamamlanamaz.
- Görevden ayrılma, geçici vekâletin sona ermesi ve bölüm değişikliği erişime otomatik yansır. Bölüm değişikliği geçmiş onay/işlem kayıtlarını değiştirmez.
- Rol şablonu değişimi etkilenen kullanıcıların yetki sürümlerini de geçersizleştirir; tarihsel kararlar o tarihteki görev ve yetki bilgisiyle korunur.

### 7.6 Örnek görev dağılımı

| Atayan | Kullanıcı | Verilen görev ve kapsam | Kullanıcının yapamayacağı işlem |
|---|---|---|---|
| Tam yetkili kullanıcı | Okul yönetimindeki yetki sorumlusu | Kurumda tanımlı personel rollerini atama; tam yetkili atama hariç | Kendisini tam yetkili yapmak |
| Yetkili okul yönetimi | Gıda alan şefi | Gıda bölümü siparişleri ve uygun görüş | Başka bölümün siparişini onaylamak |
| Yetkili okul yönetimi | Öğretmen | Kendi puantajı, iş talebi ve izinli bölüm kayıtlarını görüntüleme | Başka öğretmenin bordrosunu değiştirmek |
| Tam yetkili kullanıcı veya yetkili okul yönetimi | Sayman | Kurumun fatura, kasa, muhasebe ve tanımlı ücret işlemleri | Ayrı yetki olmadan kullanıcıya rol vermek |
| Yetkili okul yönetimi | Denetçi | Süreli, maskelenmiş rapor/kayıt erişimi | Kayıt oluşturmak, ödeme veya onay vermek |

## 8. Modül gereksinimleri

Bu tablodaki bütün modüller masaüstü ve mobil için ortak gereksinimdir. Mobilde fatura, kasa, muhasebe, bordro, yıl sonu, rapor veya yönetim ekranları kapsam dışında bırakılamaz. Erişim, platformla değil bölüm 7'deki yetkilerle belirlenir.

| Modül | Temel işlevler | Asgari kabul |
|---|---|---|
| Kurum ve görevliler | Kurum kodu, adres, mali yıl, görevlendirme, banka bilgileri | Kurum kodu ve görev değişikliği işlem izine girer |
| Kullanıcı ve oturum | Kullanıcı, rol, görev, bölüm, personel bağlantısı, oturum kapatma | Pasif kullanıcı yeni işlem yapamaz |
| Kullanıcılar ve Yetkiler | Okul yönetimi/tam yetkili kullanıcı tarafından rol, işlem, kapsam, süre ve vekâlet atama/kaldırma | Yetkisiz atama veya kendini yükseltme yok; değişiklik iki istemcide geçerli |
| Bölüm/alan/atölye | Organizasyon, sorumlu ve dağıtım yöntemi | Kullanımdaki bölüm fiziksel silinmez |
| Personel | Sicil, hizmet sınıfı, görev, unvan grubu, IBAN | Aynı kurumda kimlik tekrarları kontrol edilir |
| Öğrenci | Okul no, bölüm, veli muvafakati, katılım ve ödeme bilgileri | Eksik muvafakat ilgili işlemde açık engel/uyarı üretir |
| Cari hesap | Müşteri, tedarikçi, çiftçi, kamu kurumu, bakiye | Cari hareketleri kaynak belgeye bağlanır |
| Malzeme ve stok | Kart, giriş, çıkış, üretime sevk, kritik seviye | Hareket toplamı stok bakiyesiyle tutarlıdır |
| Ürün/hizmet ve maliyet | Reçete, işçilik, gider, öğrenci hakkı, fiyat tespit | Fiyat hesabının parametre ve maliyet sürümü saklanır |
| Sipariş/iş emri | Talep, teklif, sözleşme, görevli, üretim, kabul | Geçersiz durum geçişi reddedilir |
| Satış belgeleri | Satır, iskonto, KDV, tevkifat, sipariş ilişkisi | Toplamı sunucu hesaplar; iptal izi korunur |
| Alış/gider belgeleri | Gider türü, temin usulü, stok ve kesinti | Stok ve muhasebe etkisi tek transaction |
| Kasa/banka | Tahsilat, ödeme, peşinat, mahsup, hesap transferi | Çift kayıt/mükerrer ödeme engellenir |
| Parça başı ücret | İşçilik havuzu, katkı, öğrenci payı, tavan ve kesinti | Dağıtılan toplam havuzla kuruşu kuruşuna tutar |
| Fazla çalışma | Günlük puantaj, saat, ücret, kesinti, onay | Gün/saat sınırı ve çakışma kontrol edilir |
| Yıl sonu ve ÜTP | Kâr, dağıtıma esas tutar, bölüm/kişi payı, tavan | Tekrar hesaplama yeni sürüm üretir |
| Hazine/SHÇEK | Dönemsel matrah, oran, bildirim ve ödeme takibi | Aynı dönem yükümlülüğü mükerrer oluşmaz |
| Vergi özeti | KDV, stopaj, ücret kesintileri ve dönem dökümü | Dayanak belgelerden toplam doğrulanır |
| Muhasebe | Hesap planı, fiş, yevmiye, mizan, dönem kilidi | Kesinleşmiş fişte borç = alacak |
| Onay merkezi | Bekleyenler, detay, uygun görüş, onay, iade, geçmiş | Yalnız mevcut aşamanın yetkilisi karar verir |
| Rapor ve resmî belgeler | PDF, Excel, yazı şablonu, arşiv | Yetki, sürüm ve Türkçe çıktı doğrulanır |
| Yapılacaklar/rehber | İş listesi, tarih uyarısı, adım adım yardım | Görevler role ve kayıt durumuna bağlıdır |
| Mevzuat uyum denetimi | Eksik belge, tavan, oran, süre ve kontrol raporu | Sonuç kaynak kayıt ve kural sürümünü gösterir |
| Lisans ve sistem | Deneme, aktivasyon, salt okunur mod, yedek ve işlem izi | Süre dolsa da veri okunur ve dışa aktarılır |

### 8.1 İlk kullanılabilir sürüm ile tam kapsam ayrımı

İlk dikey sürüm: giriş → kurum/bölüm → personel/cari/ürün → sipariş → onay → işlem izi. Bu sürüm tek başına eski uygulamanın tam yerine geçmez.

Fatura, kasa, stok ve muhasebe mutabakatı tamamlanmadan mali üretim kullanımına geçilmez. Ücret, yıl sonu ve yasal yükümlülük modülleri tamamlanmadan “mevcut DÖSE ile tam işlev eşdeğerliği” iddia edilmez.

## 9. Temel iş akışları

### 9.1 Siparişten tahsilata

```text
Talep/Taslak → Teklif → Sözleşme → Üretim → Geçici kabul
                                                │
                                           Satış belgesi
                                                │
                                             Tahsilat
                                                │
                                              Kapanış
```

Onay durumu ile işin operasyonel durumu ayrı alanlardır. Örneğin siparişin “Üretimde” olması mevcut son değişiklik sürümünün onaylandığını tek başına kanıtlamaz.

1. Kullanıcı taslağı oluşturur; sunucu fiyat ve tahsis önizlemesi döner.
2. Onaya göndermede zorunlu alanlar, mali kurallar ve görevliler doğrulanır.
3. Alan şefi uygun görüşü → teknik müdür yardımcısı kontrolü → müdür onayı uygulanır.
4. Kabul/faturalama için gereken kayıtlar tamamlanır.
5. Fatura kesinleştirilir; ilgili muhasebe ve gerekiyorsa stok etkisi üretilir.
6. Tahsilat faturaya bağlanır; avans mahsup ve kalan borç hesaplanır.
7. Kapatmada kalan alacak, açık üretim ve ilişkili ücret işlemleri kontrol edilir.

### 9.2 Ücret ve yıl sonu onay zincirleri

| Belge | Hedef zincir |
|---|---|
| Sipariş | Alan şefi → teknik müdür yardımcısı → müdür |
| Parça başı bordro | Teknik müdür yardımcısı → müdür |
| Fazla çalışma | Alan şefi → teknik müdür yardımcısı → müdür |
| Yıl sonu dağıtımı | Sayman → teknik müdür yardımcısı → müdür |

Her zincir yayımlanmış bir akış sürümüne bağlıdır. Başlamış süreç, yönetici ayarı değişti diye sessizce farklı zincire geçirilmez.

### 9.3 Onay durum makinesi

```text
Taslak → Onay bekliyor → Onaylandı/Kesinleşti
  ↑           │
  └── İade ───┘

Onay bekliyor → Geri çekildi → Taslak
Kesinleşti → Yetkili düzeltme/ters kayıt süreci
```

- İade için gerekçe zorunludur.
- Atanmış onaylayıcı yoksa süreç durur; eksik görevlendirme açıkça bildirilir.
- Hazırlayanın kendi rolündeki aşamayı otomatik geçmesi varsayılan değildir.
- Onay kararında kayıt sürümü ve beklenen aşama birlikte kontrol edilir.
- Son onayda mali kurallar ve lisans tekrar doğrulanır.
- Kesinleşmiş finansal belge düzenlenmez; gerekçeli düzeltme/ters kayıt ve yeni sürüm oluşturulur.
- Ödenmiş bordroda onay geri alma, ödeme düzeltmesi çözülmeden yapılamaz.
- Uygulama içi onay, nitelikli elektronik imza yerine geçiyor gibi sunulmaz.

## 10. Veri modeli

### 10.1 Ortak alanlar ve kurallar

- Kimlikler: API'de metin olarak taşınan UUID; eski sayısal kimlikler aktarım eşleme tablosunda korunur.
- Kuruma ait her iş tablosunda `kurum_id` bulunur. İlk pilot tek kurum olsa da bu sınır kaldırılmaz.
- Değişebilen ana kayıtlarda `version`, `created_at`, `updated_at`, `created_by`, `updated_by` bulunur.
- İş tarihi `YYYY-MM-DD`; olay zamanı UTC RFC 3339; kullanıcıya gösterim `Europe/Istanbul` ile yapılır.
- Yalnız yerel saat metnini saklayıp zaman dilimini tahmin etme yaklaşımı kullanılmaz.
- Referanslı tanımlar `aktif=false` ile pasife alınır.
- Finansal kayıtlar iptal/ters kayıt ile korunur; genel amaçlı fiziksel silme yoktur.
- `FOREIGN KEY`, `NOT NULL`, `UNIQUE` ve `CHECK` kısıtları iş kurallarını destekler.

### 10.2 Tablo grupları

| Grup | Önerilen tablolar | Kritik ilişkiler/kısıtlar |
|---|---|---|
| Kurum ve kimlik | `kurum`, `kullanici`, `kurum_uyeligi`, `oturum`, `vekalet` | Üyelikte güncel `yetki_surumu`; kurum üyeliği olmadan iş verisine erişim yok |
| Yetki yönetimi | `rol`, `izin`, `rol_izin`, `rol_atama`, `kullanici_izin`, `yetki_devri` | Atayan, kapsam, başlangıç/bitiş, gerekçe, iptal bilgisi; devirde verilebilir izin/rol sınırı |
| Organizasyon | `bolum`, `personel`, `ogrenci`, `gorevlendirme`, `muvafakat` | Kurum/bölüm/personel eşleşmesi |
| Parametre | `parametre_seti`, `parametre_degeri`, `kural_surumu` | Kurum + yıl + sürüm; yayımlanmış sürüm değişmez |
| Ticari tanım | `cari`, `urun`, `malzeme`, `maliyet_kalem`, `fiyat_tespit` | Kurum içinde kart kodu tekilliği |
| Sipariş | `siparis`, `siparis_kalem`, `siparis_gorevli`, `kabul_kaydi` | Kurum + yıl + sipariş no tekilliği |
| Stok | `stok_hareket`, `stok_rezervasyon` | Kaynak işlem + etki türü tekilliği |
| Fatura | `fatura`, `fatura_kalem`, `fatura_duzeltme` | Tür + kurum + seri/yıl + belge no |
| Kasa/banka | `finans_hesabi`, `kasa_banka`, `odeme_eslestirme`, `hesap_transferi` | Ödeme ile belge eşleştirmesi; transferin iki bacağı |
| Ücret | `parca_basi`, `parca_basi_satir`, `fazla_calisma`, `puantaj_gun`, `ucret_kumulatif` | Kişi/dönem/kaynak tekrar kontrolü |
| Yıl sonu | `yil_sonu`, `utp_bolum`, `utp_kisi`, `yukumluluk` | Kurum + mali yıl + sürüm |
| Muhasebe | `hesap_plani`, `yevmiye`, `yevmiye_satir`, `donem_kilidi` | Kaynak olay için tek fiş; borç/alacak doğrulaması |
| Onay | `onay_akis_surumu`, `onay_sureci`, `onay_adimi`, `onay_karari` | Belge + sürüm başına tanımlı süreç |
| Belgeler | `belge`, `rapor_isi`, `resmi_yazi`, `belge_sablonu` | Hash, boyut, MIME, kurum ve yetki |
| İşletim | `islem_log`, `idempotency_kaydi`, `outbox`, `sayac`, `sema_surumu`, `lisans` | Değişiklik ve iş tekrarı kontrolü |

### 10.3 Kurumlar arası ilişki güvenliği

`kurum_id` alanının bulunması tek başına izolasyon sağlamaz. Aynı kurumda olma zorunluluğu bileşik anahtarlarla desteklenir:

```sql
UNIQUE (kurum_id, id)
FOREIGN KEY (kurum_id, cari_id) REFERENCES cari(kurum_id, id)
UNIQUE (kurum_id, mali_yil, siparis_no)
CHECK (version > 0)
```

Tablo başına hangi alanların ortak, hangilerinin kuruma özgü olduğu şema tasarımında yazılı olmalıdır. SQLite üzerinde PostgreSQL benzeri yerleşik satır düzeyi erişim politikası varsayılmaz; sunucu sorguları ve testleri bu sorumluluğu taşır.

### 10.4 Ana ilişki özeti

```text
Kurum → Bölüm → Personel / Öğrenci
Kurum → Cari → Sipariş → Sipariş kalemleri
Sipariş → Kabul → Fatura → Tahsilat eşleştirmeleri
Sipariş → Stok hareketleri
Sipariş → Parça başı / Fazla çalışma → Ödeme
Finansal kaynak olay → Yevmiye → Yevmiye satırları
Belge sürümü → Onay süreci → Adımlar → Kararlar
Mali yıl + Parametre sürümü → Hesap sonucu → Yıl sonu / ÜTP
```

## 11. Para, oran ve hesaplama kuralları

### 11.1 Sayısal temsil

| Değer | Saklama/API yaklaşımı |
|---|---|
| Kesinleşmiş TRY tutarı | SQLite `INTEGER` kuruş; API'de `"125000"` gibi tamsayı metni |
| Birim fiyat / miktar | Açık ölçekli decimal metni veya ölçekli tamsayı; `double` değil |
| Oran | `"0.20"` gibi canonical decimal metni; yüzde ile kesir karıştırılmaz |
| Hassas ara hesap | Saf Dart decimal/rasyonel uygulama; gerektiğinde `BigInt` tabanlı ölçek |
| Kullanıcı gösterimi | `1.250,00 TL`; gösterim biçimi veri sözleşmesi değildir |

Masaüstü, mobil ve sunucuda parasal serileştirme ve taşma kuralları aynı sözleşmeye bağlıdır. Kimlikler ve büyük parasal sayılar JSON number yerine metin olarak taşınır. Veri tabanına yazmadan önce 64 bit tamsayı aralığı ve ürünün iş sınırları doğrulanır.

### 11.2 Yuvarlama ve dağıtım

- Kurala göre, açıkça tanımlı aşamada iki hane ve half-up yuvarlama uygulanır.
- Her ara işlemi gelişigüzel iki haneye indirmek yasaktır; satır, belge ve bordro yuvarlama noktaları ayrı tanımlanır.
- Belge toplamı yuvarlanmış satır toplamlarıyla mutabık olmalıdır.
- Oransal dağıtımda kalan kuruşlar deterministik en büyük kalan yöntemiyle paylaştırılır; eşitlikte sabit kişi/satır sırası kullanılır.
- Kişi paylarının toplamı dağıtılabilir havuza tam eşit olmalıdır.
- Negatif değerlerin hangi belge türlerinde yasal olduğu açıkça tanımlanır; standart satışta eksi satırla iskonto taklidi yapılmaz.

### 11.3 Hesap motoru kapsamı

KDV, KDV ayırma, iskonto dağıtımı, tevkifat, stopaj, kümülatif gelir vergisi, damga vergisi, uygun SGK etkisi, asgari ücret istisnaları, sipariş tahsisleri, öğrenci payı, işçilik tavanı, fazla çalışma, yıl sonu kârı ve ÜTP.

**Tarihsel hesap kaydı:** Her kesinleşen hesap; girdiler, parametre seti kimliği, kural sürümü, sonuç kalemleri, tarih ve onaylanan belge sürümüyle saklanır. Yeni parametre yayımlamak eski bordroyu değiştirmez.

### 11.4 İlk altın test örnekleri

Aşağıdaki örnekler eski testlerden taşınabilecek davranış örnekleridir; mevzuat doğrulamasının yerine geçmez.

| Senaryo | Girdi | Beklenen sonuç |
|---|---|---|
| KDV + tevkifat | 10 × 100 TL; KDV %20; KDV tevkifatı 1/2 | Matrah 1.000; KDV 200; tevkifat 100; net 1.100 TL |
| Stopaj | 5.000 TL matrah; %2 stopaj | Stopaj 100; net 4.900 TL |
| Satır iskontosu | 275 × 15 TL; %20 iskonto | Brüt 4.125; iskonto 825; matrah 3.300 TL |
| Genel iskonto | Üç eşit 100 TL satır; toplam 100 TL indirim | Toplam tam 100 TL; paylar 33,33/33,34 |

Tüm hesap grupları için normal, sınır, sıfır, geçersiz giriş, dilim geçişi ve tavan aşımı örnekleri hazırlanır.

## 12. SQLite işletim ve eşzamanlılık tasarımı

### 12.1 Dosya yerleşimi

- Veritabanı sunucunun yerel kalıcı diskindedir; SMB/NFS veya kullanıcıların ortak klasöründe değildir.
- Veritabanı, WAL ve SHM dosyalarına yalnız servis hesabı erişir.
- Veritabanı ve yedekler HTTP üzerinden doğrudan sunulmaz; yalnız korunan sunucu veri dizininde tutulur.
- Uygulama yeniden dağıtıldığında veri diski silinmez.
- İlk sürüm aynı dosyaya çok makineden bağlanan sunucu replikaları çalıştırmaz.

### 12.2 Başlangıç ayarları

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = FULL;
```

Bunlar başlangıç önerileridir; sürüm ve sürücüyle doğrulanmalıdır. Bağlantı başına geçerli ayarlar her bağlantıda uygulanır. WAL modu açıldı diye sınırsız eşzamanlı yazma elde edilmez: aynı anda tek yazar vardır.

### 12.3 Yazma stratejisi

- Bir sunucu süreci ve kontrollü yazma erişimiyle başlanır.
- Drift/SQLite erişimi ayrı isolate üzerinde çalıştırılarak HTTP event loop'unun uzun senkron sorgularla bloke olması önlenir.
- Hesaplamanın saf kısmı transaction öncesinde yapılır; transaction içinde güncel durum ve sürüm tekrar doğrulanır.
- İşlemler kısa tutulur; ağ, PDF veya kullanıcı bekleme transaction içinde yapılmaz.
- Yazma kuyruğunun uzunluğu sınırlıdır; aşımda açık geçici yoğunluk yanıtı verilir.
- `SQLITE_BUSY` sınırlı bekleme/yeniden deneme sonunda `503` ve `Retry-After` ile bildirilir; başarı yanıtı verilmez.
- Geçici lock hatası, veri çakışması ve iş kuralı hatası ayrı sınıflandırılır.
- Uzun raporlar salt okunur snapshot üzerinden yürütülür; WAL büyüklüğü ve checkpoint süresi izlenir.
- Migration yalnız kontrollü bakım adımında tek yürütücüyle yapılır.

### 12.4 İyimser kilitleme

Güncelleme örüntüsü:

```sql
UPDATE siparis
SET konu = ?, version = version + 1, updated_at = ?
WHERE kurum_id = ? AND id = ? AND version = ?;
```

Etkilenen satır yoksa yetki/kayıt varlığı kapsam içinde kontrol edilir; sürüm çakışmasıysa `409 RECORD_VERSION_CONFLICT` döner. Başka kullanıcının değişikliği üzerine yazılmaz. Kullanıcı güncel kayıt ile kendi değişikliğini karşılaştırabilir.

### 12.5 İdempotency ve sıra numarası

- Tahsilat, ödeme, fatura kesinleştirme ve onay kararları `Idempotency-Key` alır.
- Anahtar kurum + kullanıcı + işlem türü kapsamında tekildir.
- İstek özeti, kaynak sonucu ve anahtar kaydı aynı transaction'da saklanır.
- Aynı anahtar/farklı içerik `409 IDEMPOTENCY_KEY_REUSED` üretir.
- Tekrar gelen istek yeni ödeme/fiş/karar oluşturmaz; ilk sonucu döndürür.
- Kayıt saklama süresi ve süre sonrası davranış belgelenir; temel mükerrerlik kısıtları anahtar temizlense de kalır.
- Belge numarası `MAX(no)+1` ile değil, transaction içindeki sayaçla üretilir.

### 12.6 Büyüme sınırı

SQLite için “şu kadar kullanıcıyı kesin kaldırır” garantisi verilmez. Yazma sıklığı, sorgu biçimi, rapor boyutu ve disk gecikmesi belirleyicidir.

Çok kurumlu yoğun kullanım, sürekli yazma kuyruğu veya yüksek erişilebilirlik gereksinimi oluşursa mimari yeniden değerlendirilir. PostgreSQL'e geçiş olası gelecek kararıdır; bu belgenin uygulanmış ya da zorunlu ilk sürüm tercihi değildir.

## 13. API sözleşmesi

### 13.1 Genel kurallar

- Sürüm öneki: `/api/v1`.
- JSON alanları tutarlı `snake_case`; enum değerleri sabit makine kodlarıdır.
- Kurum bağlamı yetkili üyelikten türetilir; gövdedeki `kurum_id` tek başına yetki sağlamaz.
- Liste isteği: `page_size`, `cursor`, izinli filtre ve sıralama alanları.
- Varsayılan 25, en çok 100 kayıt; büyük veri için rapor işi kullanılır.
- Liste yanıtı `items`, `next_cursor`, `has_more`; `total` yalnız gerektiğinde hesaplanır.
- Filtreli tarih aralıklarının dahil/dışarı sınırı sözleşmede belirtilir.
- Güncellemede `expected_version` zorunludur; kritik POST işlemleri idempotency kullanır.

### 13.2 Uç nokta envanteri

| Alan | Örnek uç noktalar |
|---|---|
| Sağlık | `GET /health/live`, `GET /health/ready` |
| Oturum | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /me` |
| Şifre/cihaz | `POST /auth/change-password`, `GET /sessions`, `DELETE /sessions/{id}` |
| Kurum/parametre | `GET /institution`, `PATCH /institution`, `GET /parameter-sets`, `POST /parameter-sets/{id}/publish` |
| Tanımlar | `/departments`, `/personnel`, `/students`, `/accounts`, `/products`, `/materials` |
| Sipariş | `GET/POST /orders`, `GET/PATCH /orders/{id}`, `POST /orders/{id}/submit` |
| Üretim/kabul | `POST /orders/{id}/start-production`, `POST /orders/{id}/acceptance` |
| Onay | `GET /approvals/pending`, `GET /approvals/{id}`, `POST /approvals/{id}/decisions` |
| Stok | `GET /inventory/balances`, `GET/POST /inventory/movements` |
| Fatura | `GET/POST /invoices`, `POST /invoices/{id}/post`, `POST /invoices/{id}/reverse` |
| Kasa/banka | `GET /cash-bank`, `POST /receipts`, `POST /payments`, `POST /transfers` |
| Ücret | `/piecework-payrolls`, `/overtime`, `/timesheets`, `/payroll-calculations` |
| Yıl sonu | `/year-end-calculations`, `/incentive-distributions`, `/obligations` |
| Muhasebe | `/journal-entries`, `/trial-balance`, `/period-locks` |
| Rapor | `POST /report-jobs`, `GET /report-jobs/{id}`, `GET /documents/{id}/download` |
| Yönetim | `/users`, `/roles`, `/permissions`, `/role-assignments`, `/permission-overrides`, `/authorization-delegations`, `/audit-events`, `/licenses` |
| Etkin yetki | `GET /me/permissions`, `GET /users/{id}/effective-permissions` |
| Bildirim | `GET /notifications`, `POST /notifications/{id}/read` |

Tanım kaynaklarında liste/oluşturma/detay/güncelleme/pasife alma eylemleri ayrı sözleşmelendirilir. Bu envanter mevcut API adresleriyle geriye uyumluluk vaadi değildir; yeni sözleşmedir.

Rol/izin atama ve kaldırma uçları `authorization.manage` ile devredilebilir izin/kapsam sınırını birlikte denetler. Tam yetkili atama ayrıca `authorization.owner.assign` gerektirir. Başkasının etkin yetkisini inceleme ayrı yönetim iznine tabidir. Atama/rol güncellemeleri sürüm kontrollüdür; gerekçesiz veya yetki sınırını aşan istek reddedilir ve denetim kaydına alınır.

### 13.3 Sipariş oluşturma örneği

```http
POST /api/v1/orders
Content-Type: application/json
Idempotency-Key: <istemcinin-urettigi-benzersiz-anahtar>
```

```json
{
  "cari_id": "ee5c07e3-3427-43c6-aef5-445450a58bb1",
  "bolum_id": "3dbd14a8-557a-45de-b7dd-201542bd58d3",
  "is_tarihi": "2026-10-16",
  "ucret_esasi": "piecework",
  "kalemler": [
    {
      "urun_id": "d8aa970f-0fd7-463d-b134-2e28231b1471",
      "miktar": "10.000",
      "birim_fiyat": "100.00",
      "kdv_orani": "0.20"
    }
  ]
}
```

Sunucu `201` ile kimlik, `version`, hesaplanmış toplamlar ve izin verilen sonraki eylemleri döndürür. İstemcinin bir toplam göndermesi, o toplamın kabul edileceği anlamına gelmez.

### 13.4 Hata modeli

```json
{
  "error": {
    "code": "RECORD_VERSION_CONFLICT",
    "message": "Kayıt başka bir kullanıcı tarafından değiştirildi.",
    "field_errors": [],
    "trace_id": "6a94e25b7b00408a"
  }
}
```

| HTTP | Anlam |
|---|---|
| 400 | Bozuk JSON / geçersiz protokol kullanımı |
| 401 | Oturum yok veya süresi dolmuş |
| 403 | Yetki yok; lisans salt okunur gibi açık hata kodları |
| 404 | Kayıt yok veya güvenlik gereği kapsam dışında |
| 409 | Sürüm, aşama veya idempotency çakışması |
| 422 | Alan doğrulaması veya iş kuralı ihlali |
| 429 | Hız sınırı |
| 500 | Beklenmeyen hata; ayrıntı yalnız sunucu logunda |
| 503 | Geçici yoğunluk / veritabanı erişim sorunu |

Sunucu stack trace, SQL veya dosya yolunu kullanıcıya açmaz. Hata logu ile kullanıcı mesajı `trace_id` üzerinden ilişkilendirilir.

## 14. Kimlik doğrulama ve güvenlik

### 14.1 Oturum yaklaşımı

- İlk kurulumda tek kullanımlık yönetici oluşturma süreci; varsayılan ortak şifre yoktur.
- Parolalar bakımı doğrulanmış Argon2id uygulamasıyla; hedef sunucuda ölçülmüş maliyetle hashlenir.
- Kendi kriptografi algoritması veya özel parola hash yöntemi yazılmaz.
- Sunucu tarafında iptal edilebilir oturum ve yüksek entropili rastgele token yaklaşımı kullanılabilir; JWT zorunlu değildir.
- Veritabanında token'ın kendisi değil özeti tutulur.
- Başlangıç politikası: kısa ömürlü erişim oturumu ve döndürülen yenileme token'ı; kesin süreler kurum güvenlik politikasıyla belirlenir.
- Yenileme token'ı tekrar kullanımı saptanırsa ilgili oturum zinciri iptal edilir.
- Çıkış, parola değişimi ve kullanıcı pasife alma mevcut oturumları geçersizleştirir.

### 14.2 Masaüstü ve mobil oturum güvenliği

**Her iki istemci:** Erişim token'ı bellekte, yenileme token'ı işletim sisteminin güvenli deposunda tutulur. API isteklerinde erişim token'ı `Authorization: Bearer` başlığında gönderilir. Desteklenmeyen ortamda düz metin dosyaya sessiz geri dönüş yapılmaz.

**Cihaz bazlı oturum:** Aynı kullanıcı farklı cihazlarda oturum açabilir; her oturum bağımsız izlenir ve iptal edilebilir. İşlem izi cihaz/kaynak bilgisini saklar; cihaz türü ek iş yetkisi sağlamaz.

**Taşıma güvenliği:** TLS sertifika doğrulaması kapatılmaz. Tarayıcı istemcisi bulunmadığından cookie/CORS tabanlı web oturumu tasarlanmaz; CORS API erişim güvenliğinin yerine geçmez. Parola, token ve TCKN uygulama loguna yazılmaz.

### 14.3 Sunucu ve veri güvenliği

- Girişte IP ve hesap bazlı hız sınırı, ölçülü gecikme ve yönetici uyarıları.
- Yönetici/son onay rolleri için MFA üretim öncesi değerlendirilir.
- SQLite varsayılan olarak dosya şifrelemesi sağlamaz; disk/yedek şifrelemesi ayrıca kurulur.
- Dosya yüklemede boyut, izinli tür, içerik kontrolü, rastgele depolama adı ve yetkili indirme.
- Kullanıcı yüklemesi çalıştırılabilir statik içerik olarak servis edilmez.
- Yedek indirme ve geri yükleme normal kullanıcı işlemi değildir; güçlü yönetim kontrolü gerekir.
- İşlem izi uygulama açısından append-only olur. Aynı sunucu/veritabanı yöneticisine karşı tek başına değiştirilemezlik kanıtı sayılmaz.
- Daha güçlü denetim gerekiyorsa imzalı dış arşiv veya bağımsız log deposu ayrıca tasarlanır.

### 14.4 KVKK ve kamu kurumu gereksinimleri

Veri sorumlusu, işleyen, saklama süresi, yetki matrisi, erişim kayıtları, öğrenci verisi ve veri ihlali süreci yazılılaştırılır. Barındırma, yedek, log, destek erişimi ve bildirim sağlayıcısı birlikte değerlendirilir.

Türkiye'de barındırma hedefi mevcut proje rehberleriyle uyumlu bir başlangıç tercihidir; tek başına hukuki uyum belgesi değildir. Güncel mevzuat ve kurumun bilgi güvenliği politikası yetkili kişilerce teyit edilmelidir. Üçüncü taraf push/e-posta hizmetlerine finansal veya kişisel veri içeren bildirim gönderilmez.

### 14.5 Lisans

- Kurum koduna bağlı lisans; imzalı lisans doğrulama veya merkezi lisans kaydı.
- İmzalı modelde özel imza anahtarı istemciye ve normal dağıtım paketine girmez.
- Bitişte yeni iş verisi yazma, onay ve finansal kesinleştirme durur.
- Okuma, raporlama, dışa aktarım, yedek ve güvenli çıkış devam eder.
- Güvenlik yönetimi, oturum iptali ve yedekleme gibi idari yazmalar lisans engelinden bilinçli olarak ayrılır.
- Deneme süresi eski üründeki 30 günü referans alır; ticari koşullar ayrıca onaylanır.

## 15. Flutter uygulama tasarımı

### 15.1 Navigasyon ve responsive yapı

Önerilen başlangıç kırılımları:

| Genişlik | Yerleşim |
|---|---|
| 600 mantıksal piksel altı | Alt navigasyon + kart/listeler + tam ekran form |
| 600–1023 | Navigation rail + seçilebilir detay görünümü |
| 1024 ve üstü | Sol menü + çalışma alanı + uygun sayfalarda sağ detay |

Bu değerler ürün kuralı değil tasarım başlangıcıdır. Yatay telefon, tablet, yüksek metin ölçeği ve dar pencere ayrıca test edilir.

### 15.2 Ana menü

Özet / Yapılacaklar; İşler ve Üretim; Stok; Finans; Ücretler; Onaylar; Muhasebe; Raporlar; Kurum ve Sistem.

Kullanıcının erişemediği modül gösterilmez. Ana menünün modül ve eylem kapsamı masaüstü ve mobilde aynıdır. Başlangıç ekranı cihaz türüne göre değil kullanıcının rolüne ve tercihine göre düzenlenir. Mobilde kart ve adımlı formlar, masaüstünde tablo ve çok panelli görünüm kullanılabilir; hiçbir modül bu nedenle kaldırılmaz.

### 15.3 Liste ve form standartları

- Sunucu taraflı arama, filtre, sıralama ve sayfalama.
- Mobilde tablonun yatay küçültülmüş kopyası yerine önceliklendirilmiş kartlar.
- Masaüstünde klavye ile dolaşım, mantıklı tab sırası ve uygun kısayollar.
- Finansal formda tutarlı decimal giriş, Türkçe virgül desteği ve alan bazlı açıklama.
- Kaydet düğmesinde işleniyor durumu; arka arkaya tıklamaya ve zaman aşımına karşı idempotency.
- Kaydedilmemiş değişiklikte sayfadan ayrılma uyarısı.
- Onay penceresinde belge, tutar, aşama ve kararın etkisi açık görünür.
- Ağ hatası, boş sonuç, yetkisizlik ve ilk yükleme birbirinden farklı ekran durumlarıdır.
- Eski önbellek gösteriliyorsa son güncelleme zamanı ve bağlantı durumu belirtilir.

### 15.4 Erişilebilirlik ve yerelleştirme

Türkçe ilk dil; metinler localization kaynaklarında tutulur. Görünen Türkçe etiketler sunucu enum kodu yapılmaz. Klavye erişimi, ekran okuyucu etiketleri, kontrast, renk dışında durum işaretleri ve büyük yazı desteği kabul kapsamındadır.

### 15.5 Ekran rotaları

Örnek rotalar: `/dashboard`, `/orders`, `/orders/:id`, `/approvals`, `/invoices`, `/inventory`, `/overtime`, `/reports`, `/settings/users`.

Bunlar web sayfası adresleri değil uygulama içi navigasyon rotalarıdır. Bildirim veya desteklenen derin bağlantıdan detay ekranına geçişte oturum ve kayıt yetkisi doğrulanır. Oturum dönüşünde yalnız izinli uygulama içi hedef rotaya dönülür; dış adrese açık yönlendirme yapılmaz.

## 16. Platform davranışları

| Konu | Masaüstü | Mobil |
|---|---|---|
| İşlev kapsamı | Yetkiye bağlı bütün modüller | Aynı yetkiyle aynı modüller ve eylemler |
| Dosya alma | Yerel dosya seçici | Sistem dosya seçimi |
| PDF / Excel | Üretme, görüntüleme, dışa aktarma | Aynı içerikle üretme, görüntüleme, dışa aktarma/paylaşma |
| Yazdırma | İşletim sistemi yazdırma arayüzü | Desteklenen sistem yazdırma arayüzü; yoksa PDF dışa aktarma |
| Bildirim | Uygulama içi; yerel bildirim opsiyonel | Uygulama içi; push ayrı aşama |
| Oturum | Güvenli depo + token | Güvenli depo + token |
| Güncelleme | İmzalı kurulum/güncelleme | Mağaza veya izinli kurumsal dağıtım |
| Ağ yok | Açık bağlantı uyarısı; yazma kapalı | Aynı |

- Eşdeğerlik aynı piksel yerleşimi veya aynı fiziksel yazıcı desteği değil, aynı iş sonucuna cihazdan ulaşılabilmesidir.
- Dosya, rapor ve yönetim işlemleri mobilde de tamamlanabilmelidir; “masaüstünden devam edin” zorunluluğu kabul edilmez.
- Android derlemeleri imzalanır; iOS için Apple hesapları, macOS/Xcode ve cihaz testi gerekir.
- Windows paketinde kod imzası ve yükseltme/geri dönüş senaryosu planlanır.
- Her platformun minimum işletim sistemi seviyesi seçilen Flutter sürümünün resmî destek tablosuna göre sabitlenir.

## 17. Bildirim ve bağlantı yönetimi

### 17.1 İlk sürüm

Uygulama açıkken 30–60 saniyelik kontrollü sorgulama yeterli başlangıçtır. Uygulama arka plandayken sürekli sorgulama varsayılmaz. İşlem sonrası ilgili ekran verisi hemen yenilenir.

İhtiyaç oluşursa SSE/WebSocket eklenebilir. Bildirim “veri değişti” sinyali taşır; yetkili güncel veri API'den yeniden okunur. Bağlantı kopmasında son olay kimliği veya tam yenileme ile toparlanılır.

### 17.2 Outbox

Finansal işlem ile `outbox` olayı aynı transaction'da yazılır. İşleyici olayları sahiplenir; başarısız denemeleri gecikmeli ve üst sınırla tekrarlar. İşleyici gönderimden sonra çökerse tekrar gönderim oluşabileceğinden tüketici/kanal mümkün olduğunca olay kimliğiyle mükerrerliği önler.

Son deneme, hata, deneme sayısı ve kalıcı başarısız işler yönetici ekranında görünür. “Bildirim gönderilemedi” durumu mali işlemi başarısızmış gibi göstermemelidir.

### 17.3 Çevrimdışı sınır

İlk sürüm çevrimdışı çalışma sunmaz. Bağlantı koparken form bellekte tutulabilir; bu, sunucuya kaydedilmiş veri değildir. Yeniden bağlanınca sürüm kontrolü yapılmadan yazma tekrarlanmaz. Oturum kapanınca kullanıcıya özel önbellek temizlenir.

## 18. Raporlama ve belgeler

### 18.1 Rapor envanteri

Sipariş maliyeti ve kârlılık; cari ekstre; stok bakiye ve hareket; satış/alış; kasa/banka; KDV/stopaj özeti; parça başı bordro; fazla çalışma bordro; puantaj; yıl sonu ÜTP; Hazine/SHÇEK; yevmiye; mizan; onay geçmişi; mevzuat uyum raporu ve işlem izi.

### 18.2 Üretim ilkeleri

- Resmî veya mali çıktı sunucuda yetkili veriden üretilir.
- Kısa rapor doğrudan; uzun rapor `rapor_isi` ile asenkron hazırlanır.
- Rapor işi kullanıcı/kurum kapsamını ve kullanılan parametre sürümünü kaydeder.
- Sıra, hazırlanıyor, tamamlandı, başarısız ve süresi doldu durumları görünürdür.
- İndirmede güncel yetki tekrar kontrol edilir; tahmin edilebilir açık dosya URL'si yoktur.
- Kesinleşmiş belgenin PDF'si ve hash'i arşivlenebilir; yeni şablon eski belgeyi değiştirmez.
- Türkçe fontlar uygun dağıtım lisansıyla gömülür.
- Excel/CSV dışa aktarımlarında `=`, `+`, `-`, `@` ile başlayan kullanıcı metinleri formül enjeksiyonuna karşı güvenli yazılır.
- Rapor, muhasebe kaydı veya e-Fatura/e-Arşiv resmî gönderimiyle karıştırılmaz.

## 19. Eski sistemden veri ve kural aktarımı

### 19.1 Yaklaşım

Eski şemayı olduğu gibi yeni uygulamaya bağlamak yerine kontrollü ETL yapılır. Kaynak SQLite veya eski merkezi PostgreSQL olabilir. Eski Python paketleri yeni üretim sistemine taşınmaz; yalnız karşılaştırmalı test ve aktarım hazırlığında referans olabilir.

### 19.2 Aktarım adımları

1. Kaynağın tutarlı yedeğini al; çalışma kopyası üzerinde keşif yap.
2. Kaynak sürüm, tablo sayıları, tarih aralıkları ve veri kalitesi raporu çıkar.
3. Eski ID → yeni UUID ve kurum eşleme tablosunu oluştur.
4. Kurum, mali yıl, bölüm ve tanımları taşı.
5. Sipariş, belge, stok, kasa ve ilişkileri taşı.
6. Bordro, kümülatif matrah, yıl sonu ve muhasebe kayıtlarını taşı.
7. Onay ve işlem geçmişini kaynak kimlikleriyle arşivle.
8. Sayım, toplam ve ilişki mutabakatını çalıştır.
9. Yetkili mali kullanıcıyla örnek belge ve yıllık rapor doğrula.
10. Üretim geçişinde eski sisteme yazmayı kapat; son yedeği al ve son aktarımı yap.

### 19.3 Veri dönüşümü kuralları

- `REAL` tutarlar, belgelenmiş decimal dönüştürme/yuvarlama kuralıyla kuruşa çevrilir.
- Kaynak float hataları sessizce düzeltilmez; kaynak, hedef ve fark raporlanır.
- Eski tarihsel sonuç yeniden hesaplanmış gibi sunulmaz; kaynak sonuç ve hesaplama kökeni korunur.
- Eksik/yetim ilişkiler karantinaya alınır; başarılı aktarım sayımına katılmaz.
- Rol eşlemeleri ve yeni onay davranışları açık onay gerektirir.
- Eski parola hash'i uyumlu ve yeterli değilse zorunlu parola yenileme uygulanır.
- Eski oturum token'ları yeni sisteme taşınmaz.
- Şifreleme/lisans özel anahtarları normal veri aktarımına dahil edilmez.

### 19.4 Mutabakat kapısı

| Kontrol | Kabul |
|---|---|
| Ana tablo kayıt sayıları | Dışlanan/karantinadaki her kayıt açıklanmış |
| Cari bakiyeler | Belgelenmiş dönüşüm dışında fark yok |
| Stok miktarı/değeri | Malzeme ve dönem bazında mutabakat |
| Fatura ve kasa toplamları | Dönem ve belge türü bazında fark yok |
| Bordro brüt/kesinti/net | Kişi/dönem bazında fark yok |
| Yevmiye borç/alacak | Her fiş ve toplam düzeyinde denk |
| İlişkiler | Açıklanmamış yetim kayıt yok |
| İkinci çalıştırma | Aynı kaynak için mükerrer kayıt yok |

Kaynak-hedef farkları için gerekçeli kabul belgesi olmadan geçiş onaylanmaz. Eski sistem bir süre salt okunur arşiv olarak saklanır. İki sisteme eşzamanlı canlı yazma yapılmaz.

## 20. Test ve kabul ölçütleri

### 20.1 Test katmanları

| Katman | Kapsam |
|---|---|
| Domain | Para, vergi dilimi, iskonto, tahsis, tavan, dağıtım, puantaj |
| Veritabanı | Kısıtlar, kurum ilişkileri, transaction, migration, kilit ve rollback |
| API | Kimlik, kapsam, hata şekli, sayfalama, sürüm ve idempotency |
| Flutter widget | Doğrulama, loading/error/empty, erişilebilirlik ve responsive görünüm |
| Uçtan uca | Masaüstünde başlat → mobilde sürdür; aynı akışı ters yönde de tamamla |
| Platform | Dosya, yazdırma, güvenli depo, derin bağlantı ve güncelleme |
| Operasyon | Yedekten dönme, disk dolması, servis çökmesi ve log |

### 20.2 Zorunlu senaryolar

- Öğretmen başka öğretmenin fazla çalışma kaydına erişemez.
- Alan şefi farklı bölümün kararını veremez.
- Normal kullanıcı, API isteğini elle gönderse de rol/izin atayamaz veya kendi yetkisini artıramaz.
- Yetkili okul yönetimi kendi kurumunda devredilen sınırla görev atar; başka kurumda veya sınır dışı izinle atama yapamaz.
- İşlem yapma izni tek başına o izni başkasına verme hakkı sağlamaz.
- Rol tanımını değiştirerek devretme sınırı veya tam yetkili atama kontrolü aşılamaz.
- Son aktif tam yetkili kullanıcı halef olmadan kaldırılamaz.
- Yetki kaldırma ve süreli vekâlet bitişi, oturum açık olsa da sonraki API isteğinde uygulanır.
- Birden çok rolün izin ve kapsamı yanlış birleştirilerek kişisel izin kurum geneline genişletilemez.
- Aynı kullanıcının güncel görev ve yetki sınırları masaüstü ve mobilde aynı sonuç verir.
- Başka kurum kimliği göndererek kayıt bağlanamaz veya rapor indirilemez.
- İki kullanıcı aynı sürümü değiştirince yalnız biri başarılı olur.
- Aynı ödeme isteği on kez gelince tek ödeme ve tek muhasebe etkisi oluşur.
- Aynı onay aşamasına eşzamanlı kararlar tek geçerli karar üretir.
- Son onay ile ödeme arasında belge esaslı değiştirilemez.
- Transaction ortasında hata olunca yarım stok/fiş kaydı kalmaz.
- Önceki yılın parametresi değişse bile arşiv bordrosu değişmez.
- Lisans bitince okuma/dışa aktarım sürer, yeni mali yazma reddedilir.
- Rapor işi ve outbox yeniden başlatmada kaybolmaz veya sessizce başarılı sayılmaz.
- Masaüstü veya mobilde oturum kapatınca önceki kullanıcının hassas verisi görünmez.
- Türkçe karakterler ve 360 piksel genişlikte temel akışlar çalışır.
- Aynı yetkili kullanıcı fatura, tahsilat, bordro, muhasebe, yıl sonu ve yönetim işlemlerini yalnız mobil uygulamayla da tamamlar.
- Masaüstünde oluşturulan kayıt mobilde, mobilde oluşturulan kayıt masaüstünde aynı sürüm ve toplamlarla görünür.

#### Çapraz platform eşdeğerlik matrisi

Her modül için iş eylemleri listelenir; her eylem aynı rol, veri, parametre ve kayıt sürümüyle masaüstünde ve desteklenen her mobil platformda ayrı test edilir.

| Kontrol | Kabul koşulu |
|---|---|
| Modül ve eylem erişimi | Yetkili bütün eylemler iki istemcide de erişilebilir |
| Oluşturma/düzenleme | Aynı geçerli giriş aynı kayıt ve hesap sonucunu üretir |
| Onay/ödeme/kesinleştirme | Aynı durum geçişi, tek yan etki ve aynı işlem izi |
| Hata ve yetki reddi | Aynı kural aynı hata kodunu üretir; mobilde atlanamaz |
| Rapor/dışa aktarım | Aynı filtre ve snapshot aynı mali içeriği üretir |
| Cihazlar arası devam | Kayıt diğer cihazda görülür; eski sürüm sessizce üzerine yazılmaz |
| Cihaz yetenekleri | Yazıcı gibi donanım yoksa aynı belge dosya olarak alınabilir |

Bir modül yalnız masaüstünde tamamlandıysa eşdeğer teslim sayılmaz. API testi yanında her istemcinin ekranından eylemin tamamlanması doğrulanır.

### 20.3 Finansal doğruluk kapısı

Hesap motorunun yayımlanmadan önce bütün altın örnekleri geçmesi gerekir. Sadece toplam kod kapsamı yeterli kabul değildir. Parasal testlerde toleranslı `double` karşılaştırması yerine kuruş/decimal düzeyinde tam eşitlik kullanılır.

Eski testler iş beklentisi için başlangıçtır; eski uygulamadaki bir hata yeni sistemde doğru kabul edilmez. Farklar mali uzman kararıyla sınıflandırılır.

### 20.4 Başlangıç performans hedefleri

Henüz ölçülmüş kapasite değil, pilotta doğrulanacak kabul hedefidir:

- Referans veri: tek kurumda 100.000 sipariş ve 1.000.000 ilişkili hareket satırı.
- Referans sunucu: yerel SSD, 4 vCPU, 8 GB RAM; test raporunda gerçek donanım yazılır.
- Yük: 50 oturum; saniyede yaklaşık 10 liste/detay okuma ve 2 finansal yazma, 30 dakika.
- Sunucu API p95: standart liste/detay 500 ms altında; kısa yazma 1 saniye altında.
- Yetki/kural reddi hariç beklenmeyen hata oranı %0,5 altında.
- Veri kaybı, mükerrer ödeme ve muhasebe dengesizliği sıfır.
- Uzun rapor 2 saniye içinde iş kimliği döndürür; rapor tamamlanma hedefi veri boyutuyla ayrıca belirlenir.

Bu eşikler sağlanmazsa indeks, sorgu planı, transaction uzunluğu ve disk ölçülür. SQLite'a yatay ölçekleniyormuş gibi ikinci yazıcı sunucu eklenmez.

## 21. Dağıtım ve işletim

### 21.1 Ortamlar

Geliştirme, test/staging ve üretim ayrı veri dosyaları, dosya depoları ve anahtarlara sahip olur. Üretim verisi geliştirici cihazına açık biçimde kopyalanmaz; anonimleştirilmiş örnek kullanılır.

### 21.2 Üretim yerleşimi

- Kullanıcılara imzalı masaüstü kurulum paketi ve mobil uygulama dağıtılır; sunucuda web sitesi veya Flutter Web çıktısı yayımlanmaz.
- Dart API iç ağ/loopback üzerinden servis edilir; dışa yalnız HTTPS açılır.
- Linux servis yöneticisi veya Windows hizmetiyle otomatik başlatma ve kontrollü yeniden başlatma.
- SQLite kalıcı yerel veri dizininde, belgeler ayrı korunan dizinde.
- Konfigürasyon ve gizli anahtarlar kaynak kodun dışında.
- OS güvenlik güncellemesi, sertifika yenileme, disk ve yedek izleme sorumluları atanır.

### 21.3 CI/CD kapıları

1. Biçim/lint ve statik analiz.
2. Saf Dart finans ve API testleri.
3. Flutter widget ve hedefli entegrasyon testleri.
4. Migration ve sözleşme uyumluluğu testi.
5. Hedef platform derlemeleri ve imza.
6. Staging yayını ve kritik akış smoke testi.
7. Üretim öncesi yedek ve onay.
8. Kontrollü yayın; sağlık ve hata oranı kontrolü.

### 21.4 Sürüm uyumluluğu

Masaüstü ve mobil uygulamalar farklı zamanlarda güncellenebilir. API değişiklikleri geçiş dönemiyle yapılır. Sunucu istemci sürüm bilgisini alır; destek dışı sürüme açık güncelleme uyarısı verir. Yeni işlevler desteklenen masaüstü ve mobil sürümlerde birlikte hazır olduğunda açılır; eski istemci için gerekiyorsa güncelleme zorunlu tutulur. Onaysız kırıcı şema değişikliğiyle eski istemci sessizce bozulmaz.

### 21.5 İzlenecek metrikler

İstek süresi/hata oranı, aktif oturum, yazma kuyruğu, `SQLITE_BUSY`, transaction süresi, WAL boyutu, disk boşluğu, rapor kuyruğu, outbox başarısızlığı, son başarılı yedek ve son geri yükleme testi.

`/health/live` sürecin yaşadığını; `/health/ready` veritabanı/şema hazırlığını ölçer. Sağlık uçları kişisel veri, bağlantı sırrı ve ayrıntılı hata açmaz.

## 22. Yedekleme ve felaket kurtarma

### 22.1 Yedek yöntemi

- Çalışan WAL veritabanında yalnız ana `.db` dosyasını kopyalamak güvenilir yöntem değildir.
- SQLite Online Backup API veya doğrulanmış `VACUUM INTO` yöntemi kullanılır.
- Seçilen Dart SQLite bağlayıcısının backup desteği teknik denemede doğrulanır.
- Migration öncesi ayrıca tam yedek alınır.
- Yedek tamamlandıktan sonra bütünlük, okunabilirlik ve temel iş toplamları kontrol edilir.
- Belgeler ve veritabanının tutarlı eşleşmesi için backup manifest'i tutulur.
- Dosyalar değişmez kimlikle saklanır; yedek snapshot'ının referans verdiği dosyalar kopyalama bitmeden temizlenmez.

### 22.2 Başlangıç politikası

| Konu | Önerilen hedef |
|---|---|
| Veritabanı yedeği | Saatlik otomatik; ayrıca günlük saklama noktası |
| RPO | En çok 1 saat; ancak başarılı yedek izleme ve dosya politikasıyla doğrulanır |
| RTO | En çok 4 saat; geri yükleme tatbikatıyla doğrulanır |
| Saklama | 24 saatlik, 30 günlük ve 12 aylık döngü; hukuk/politikayla netleştirilir |
| Konum | Bir yerel hızlı kopya + aynı sunucu dışında şifreli kopya |
| Test | Aylık izole geri yükleme; büyük güncellemede ek tatbikat |

Bu politikalar mevzuat saklama süresinin yerine geçmez. Tek makinede tutulan yedek, o makinenin kaybına karşı koruma sağlamaz.

### 22.3 Geri yükleme prosedürü

1. Bakım moduna geç; yeni yazmayı durdur.
2. Sorunlu mevcut durumu adli/teknik inceleme için koru.
3. Seçilen yedeği izole dizine geri yükle.
4. Bütünlük, şema, dosya manifest'i, mizan ve örnek bakiyeleri doğrula.
5. Servisi yeni veri konumuyla başlat; oturum ve son işlem sınırını kontrol et.
6. Yetkili mali kullanıcı onayı sonrası yazmayı aç.
7. Kurtarma süresi, kayıp aralık ve etkilenen işlemleri raporla.

Canlı işlem başladıktan sonra eski sisteme dönmek basitçe eski yedeği açmak değildir; yeni işlemlerin nasıl korunacağı veya mutabakatla yeniden işleneceği ayrıca planlanmalıdır.

## 23. Geliştirme aşamaları

Süreler bütçe taahhüdü değildir. Bir deneyimli tam zamanlı geliştirici ve düzenli mali uzman desteği varsayımıyla kaba plan aşağıdadır. Mağaza onayları ve kurum içi izinler ek takvim gerektirebilir.

| Aşama | Çıktı | Tahmini süre | Çıkış kapısı |
|---|---|---|---|
| 0. Analiz | Ekran/veri/kural envanteri, açık kararlar, örnek çıktılar | 1–2 hafta | Ürün ve mali süreç onayı |
| 1. Teknik temel | Flutter kabuk, Dart API, SQLite, CI, oturum, migration | 2–3 hafta | Hedef platformlarda API bağlantısı ve yedek denemesi |
| 2. İlk dikey akış | Tanımlar, sipariş, onay, işlem izi | 3–4 hafta | Windows ↔ Android akışı ve iki istemcide aynı eylemler |
| 3. Mali çekirdek | Fatura, stok, kasa, tahsilat ve muhasebe | 4–6 hafta | Belge/stok/mizan mutabakatı |
| 4. Ücretler | Parça başı, fazla çalışma, puantaj, kesintiler | 3–5 hafta | Altın hesap ve onay testleri |
| 5. Yıl sonu/rapor | ÜTP, yükümlülük, rapor ve resmî belgeler | 3–5 hafta | Örnek mali yıl uçtan uca doğrulama |
| 6. Geçiş ve sertleştirme | ETL, güvenlik kontrolleri, yük ve kurtarma testleri | 2–4 hafta | Pilot geçiş kapısı |
| 7. Pilot/yayın | Kurum pilotu, eğitim, imza/mağaza ve işletim | 2–4 hafta | Kritik hata yok; işletim teslimi |

**Toplam kaba aralık:** 20–33 hafta başlangıç tahminidir; tam mobil işlev kapsamının eforu analiz aşamasında yeniden hesaplanmalıdır. Veri kalitesi, resmî çıktı sayısı, platform testleri ve ekip deneyimiyle değişir. İlk dikey prototip daha erken görülebilir; tam mali sistemle eşdeğer değildir. Her aşamanın kabulüne masaüstü/mobil eşdeğerlik testi dahildir.

### 23.1 Öncelik sırası

Önce para ve transaction temeli; sonra sipariş/onay; ardından stok/fatura/kasa/muhasebe; sonrasında bordro/yıl sonu. Görsel paneli bitirip finansal kuralları sona bırakmak uygun değildir.

## 24. Riskler ve açık kararlar

| Risk | Etki | Önlem / karar kapısı |
|---|---|---|
| SQLite tek yazar sınırı | Yoğun işlemlerde bekleme | Kısa transaction, ölçüm, sınırlı kuyruk ve kapasite testi |
| Tek merkezi sunucu | Kesintide tüm istemciler etkilenir | İzleme, hızlı geri yükleme, açık RTO |
| `double` ile para hesabı | Kuruş farkı ve hatalı dağıtım | Ölçekli değerler ve tam eşitlik testleri |
| Eski mevzuat varsayımları | Yanlış ücret/yükümlülük | Mali uzman doğrulaması ve sürümlü parametre |
| Onay davranışı değişimi | İş akışı şaşkınlığı | Politika onayı, eğitim ve pilot |
| Çok kurumlu izolasyon | Veri sızıntısı | Kapsamlı yetki testleri; ayrı üretim kapısı |
| Hatalı backup | Veri kaybı | Online backup ve düzenli geri yükleme tatbikatı |
| Flutter paket farkları | Bir platformda çalışmayan özellik | Dosya, baskı ve güvenli depo teknik denemesi |
| Mevcut veri sorunları | Eksik/yanlış aktarım | Karantina ve kayıt bazlı mutabakat |
| Fazla geniş ilk sürüm | Takvim ve kalite riski | Dikey teslim ve mali kullanıma ayrı kabul |

### 24.1 Geliştirme öncesi netleştirilecekler

- İlk yayında iOS zorunlu mu, yoksa Windows/Android sonrası mı? Yayın tarihi değişse de işlev kapsamı daraltılmaz.
- Barındırmayı kim işletecek; destek erişiminin sınırı ne olacak?
- İlk kurum için gerçek kayıt hacmi, eşzamanlı kullanıcı ve yazma yoğunluğu nedir?
- Çok kurumlu ticari hizmet ne zaman açılacak; tek dosya mı kurum başına dosya mı ayrıca değerlendirilecek?
- Uygulama içi onayda vekâlet, görev ayrılığı ve geri alma politikası nedir?
- Stok değerleme ve negatif stok politikası nedir?
- Şablonları yetkili kişilerce onaylanmış hangi resmî belgeler üretilecek?
- GİB/e-belge, banka veya e-imza entegrasyonu gerçekten kapsamda mı?
- Deneme, ücretlendirme, destek ve veri saklama sözleşmesi nasıl olacak?
- MFA, yedek saklama ve erişim logu süreleri hangi kurum politikasıyla belirlenecek?

Bu sorular kullanıcı tarafından henüz kesinleştirilmiş tercih sayılmaz. Belgedeki öneriler, ilgili fazın başlangıcında onaylanmalıdır.

## 25. İlk geliştirme iş listesi ve tamamlanma tanımı

### 25.1 İlk sprint

- [ ] Flutter ve Dart sürümlerini sabitle; hedef platformlarda boş uygulama derle.
- [ ] Monorepo, analiz kuralları ve test hattını kur.
- [ ] `dose_contracts` ve `dose_finance` paketlerini oluştur.
- [ ] Para, miktar ve oran tiplerini; ilk dört altın testi uygula.
- [ ] Dart `shelf` API ve standart hata middleware'ini kur.
- [ ] Drift/SQLite üzerinde kurum, kullanıcı, oturum ve migration temelini kur.
- [ ] WAL/foreign key ayarları ile backup/restore teknik denemesini tamamla.
- [ ] İlk yönetici oluşturma, giriş/çıkış ve platforma uygun oturum saklamayı uygula.
- [ ] Responsive ana kabuk ve etkin yetkilere göre menüyü oluştur.
- [ ] Okul yönetimi/tam yetkili kullanıcı için görev, rol, kapsam ve süre atama akışını iki istemcide uygula; devretme sınırı ve yetki kaldırma testlerini ekle.
- [ ] Sipariş için sürüm kontrollü ilk uçtan uca kayıt akışını masaüstü ve mobilde aynı eylemlerle kur.

### 25.2 Bir modülün tamamlanmış sayılması

Ekranın açılması yeterli değildir. Modül; API, veri kısıtları, izinler, bölüm/kişi kapsamı, işlem izi, hata durumları, eşzamanlılık, testler, rapor etkisi ve ilgili kullanım açıklamasıyla tamamlanmış sayılır. Aynı modülün bütün yetkili iş eylemleri masaüstü ve mobilde tamamlanıp eşdeğerlik matrisi geçmeden teslim bitmiş sayılmaz.

### 25.3 Üretim yayın kontrol listesi

- [ ] Finansal altın testler ve uçtan uca mali yıl senaryosu geçti.
- [ ] Açıklanmamış kaynak-hedef veri farkı yok.
- [ ] Yetki/kurum/bölüm ve hassas alan testleri geçti.
- [ ] Okul yönetimi ve tam yetkili kullanıcının atama/kaldırma, yetki devri ve kendi yetkisini artırmayı önleme testleri geçti.
- [ ] Çakışma, idempotency ve rollback testleri geçti.
- [ ] Yük testi hedefleri gerçek ölçüm raporuyla doğrulandı.
- [ ] Yedek ve geri yükleme hedefleri tatbikatla doğrulandı.
- [ ] Windows ve hedef mobil platformlarda bütün modüllerin yetkili iş eylemleri eşdeğerlik matrisiyle doğrulandı.
- [ ] TLS, güvenli oturum, imzalama ve sır yönetimi hazır.
- [ ] Mevzuat parametreleri ve belge şablonları yetkili mali personelce onaylandı.
- [ ] Kullanıcı eğitimi, destek sorumlusu ve olay müdahale prosedürü hazır.
- [ ] Eski sistemi salt okunura alma ve başarısız geçiş planı onaylandı.

**Sonuç:** Hedef ürün web sitesi değil; web tabanlı ortak altyapıya bağlanan, aynı yetkiyle aynı işlevleri sunan kurulabilir masaüstü ve mobil uygulamalardır. Flutter ile ortak istemci kod tabanı, Dart ile merkezi iş kuralı katmanı kullanılır. SQLite yalnız sunucuda çalışır. Sistemin güvenilirliği; doğru finansal temsil, kısa ve atomik transaction, açık yetkilendirme, sürümlü onay/hesap, mutabakatlı aktarım, çapraz platform eşdeğerlik ve denenmiş yedekleme üzerine kurulmalıdır.

## 26. Kaynaklar

### 26.1 Proje içi kaynaklar

- [Kurulum ve kullanım rehberi](KURULUM.md)
- [Satıcı ve lisans rehberi](SATIS_REHBERI.md)
- [Mevcut veri modeli](dose/db.py)
- [Hesaplama motoru](dose/hesap.py)
- [Mevzuat ve parametreler](dose/mevzuat.py)
- [Rol ve yetki tanımları](dose/yetki.py)
- [Onay işleyişi](dose/onay.py)
- [Mobil sunucu API'si](sunucu/api.py)
- [Masaüstü modülleri](dose/ui/sayfalar)
- [Hesap testleri](tests/test_hesap.py)
- [Mali yıl senaryosu](tests/test_senaryo.py)

### 26.2 Resmî ve birincil teknik kaynaklar

Aşağıdaki kaynaklar mimari sınırları ve paket kullanımını doğrulamak içindir. Sürüm uyumluluğu geliştirme başlangıcında yeniden kontrol edilmelidir.

- [Flutter — Supported deployment platforms](https://docs.flutter.dev/reference/supported-platforms)
- [Dart Shelf — Paket ve middleware modeli](https://pub.dev/packages/shelf)
- [Drift — Desteklenen platformlar ve native SQLite erişimi](https://drift.simonbinder.eu/platforms/)
- [SQLite — Write-Ahead Logging](https://www.sqlite.org/wal.html)
- [SQLite — Online Backup API](https://www.sqlite.org/backup.html)

SQLite WAL belgesi aynı makine gereksinimi, ağ dosya sistemi kısıtı ve eşzamanlılık sınırları açısından; backup belgesi canlı verinin tutarlı yedeklenmesi açısından özellikle dikkate alınmıştır.
