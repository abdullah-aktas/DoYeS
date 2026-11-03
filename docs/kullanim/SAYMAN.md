# Sayman kılavuzu

Muhasebe ve tahsilat/ödeme kayıtlarının sorumlusu sizsiniz. Fatura, kasa, stok, yevmiye, hazine payı, mevzuat
doğrulama ve yıl sonu hazırlığı sizin ekranlarınızdadır.

Platform: [PLATFORM.md](PLATFORM.md) · Ortak: [ORTAK.md](ORTAK.md)

## Başlangıç sırası

1. Merkez parametre yayını varsa **Okul parametre doğrulaması**ndan doğrulayın (yoksa parça başı / FC taslağı açılmaz).
2. **Tanımlar:** bölüm → personel → cari → malzeme → ürün (gerekirse öğrenciler). Toplu giriş için **Şablon** / **Excel/PDF yükle** (bkz. [ORTAK.md](ORTAK.md#tanım-içe-aktarma-excel--pdf)).
3. **Muhasebe hesapları** ve açılış bakiyeleri (**Kasa / Banka → Açılış**).
4. Sonra günlük işlemler: sipariş sonrası fatura, stok, tahsilat/ödeme.

## Fatura

### Satış

- Onaylı siparişe bağlı kalemlerden kısmi fatura kesebilirsiniz.
- Önizle → kontrol → kaydet. Tevkifat / stopaj belge geneline uygulanır.

### Alış (mal / hizmet)

1. Tedarikçi, belge no, tarih, kalemler.
2. **Temin usulü** (ör. Doğrudan Temin), **gider türü**, **alış belge türü** zorunlu.
3. Temine göre zorunlu alım belgelerini işaretleyin (ihtiyaç, yaklaşık maliyet, piyasa tutanağı, onay, muayene…).
4. Doğrudan teminde matrah 2026 limiti (KDV hariç, diğer idareler için yayımlanan tutar) aşılırsa uyarı çıkar.
5. Önizle → kaydet. Özet HTML indirilebilir; GİB gönderimi yoktur.

Hata: gerekçeli **ters kayıt**. Önce bağlı kasa hareketini tersleyin.

## Kasa / Banka

| Tür | Ne zaman |
|---|---|
| Açılış | Dönem başı bakiye |
| Tahsilat / Ödeme | Faturaya bağlı; kalanı aşamaz, bakiye eksiye inemez |
| Avans / Virman / Faturasız | İlgili türlerle |

Gerçek EFT uygulamada yapılmaz; bankada yapılan işlemi buraya işlersiniz.

## Stok ve yevmiye

- Stok giriş/çıkış sayman yetkisiyle; tutar ve hesap seçilir.
- **Yevmiye / mizan** ekranından fiş ve bakiyeleri izleyin.

## Hazine payı

Satış tahsilatının KDV hariç hasılatı aylık hesaplanır. Bildirim → tahakkuk → bankadan ödeme kaydı.
Belgeler menüsünden bildirim / üst yazı / talimat HTML alın.

## Parça başı / fazla çalışma (ödeme tarafı)

Onaylanan bordroyu **Bankadan öde** ile kasaya bağlarsınız. Belge setini ilgili ekrandan üretin.

## Yıl sonu / ÜTP

Taslağı siz hazırlarsınız; müdür olur verir. ÜTP ödemelerini kasa ile kapatırsınız.

## Raporlar

- Yıllık özet (HTML / Excel / PDF)
- Üç aylık faaliyet HTML (md.48)
- Bakanlık aylık mizan HTML (md.47)

## Dikkat

- Önizlemeden sonra formu değiştirirseniz yeniden önizleyin.
- Çakışma uyarısında güncel kaydı yükleyip işlemi tekrarlayın.
- Alış temin belgelerinin asılları arşivde ayrıca durmalıdır.
