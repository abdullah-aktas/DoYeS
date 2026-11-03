# Memur / Veri Girişi kılavuzu

Tanım ve belge kayıtlarını girersiniz; muhasebe onay zincirinin harcama/onay tarafında değilsiniz.

Platform: [PLATFORM.md](PLATFORM.md) · Ortak: [ORTAK.md](ORTAK.md)

## Tipik ekranlar

- **Kurum, bölüm, personel, öğrenci, cari, malzeme, ürün** — kart açma / güncelleme (yetkiye göre)
- **Resmi yazılar** — şablon metin hazırlama (yazma yetkiniz varsa)
- **Denetim formu** — form kaydı (yetkiye göre)
- Listeleri okuma: sipariş, fatura özeti vb. (çoğu yerde salt görüntü)

## Excel / PDF ile toplu içe aktarma

Yazma yetkiniz olan tanım ekranlarında (**bölüm, personel, öğrenci, cari, malzeme, ürün**):

1. **Şablon** ile boş Excel indirin; başlık satırını bozmadan doldurun.
2. **Excel/PDF yükle** ile dosyayı seçin; önizlemede satırları kontrol edin.
3. **İçe aktar** ile kaydedin. Aynı TCKN / kod / unvan varsa güncellenir, yoksa eklenir.
4. PDF yalnız **metin seçilebilir tablolar** içindir; tarama (görüntü) PDF desteklenmez — Excel kullanın.

Ayrıntı: [ORTAK.md](ORTAK.md#tanım-içe-aktarma-excel--pdf).

## Veri girişi kuralları

1. T.C. / VKN / IBAN hatalıysa kayıt reddedilir; ekrandaki sebebi düzeltin.
2. Cari kodunu boş bırakırsanız sistem numara verir (C0001…).
3. Kullanılan tanımı silmeyin; **Aktif** işaretini kaldırın.
4. Başkası aynı kaydı değiştirdiyse çakışma uyarısına uyun.

## Yapamayacaklarınız

- Fatura / kasa / stok kaydı (sayman)
- Sipariş olur / TMY uygundur (ilgili roller)
- Kullanıcı daveti (müdür / sistem yöneticisi)

Sayman veya müdür size net bir «bugün şunu gir» listesi verdiyse Ana ekran sürelerini de takip edin;
beyan tarihleri hatırlatma amaçlıdır, beyannameyi GİB’e siz bu uygulamadan göndermezsiniz.
