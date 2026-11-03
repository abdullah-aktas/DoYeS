# Sistem Yöneticisi kılavuzu

Okul içi **tanım ve kullanıcı** yönetimine odaklanır. Harcama olur zincirinin müdür rolünden farklıdır;
okulda aktif müdür veya sistem yöneticisinden en az biri kalmalıdır.

Platform: [PLATFORM.md](PLATFORM.md) · Ortak: [ORTAK.md](ORTAK.md)

## Yetkiler

- **Kullanıcılar:** davet, rol/bölüm güncelleme, pasifleştirme (müdürle aynı yönetim RPC’leri)
- Tanım ekranlarında geniş yazma yetkisi (kurum, bölüm, personel…)
- İşlem kaydını izleme

## Merkez yöneticisi ile karıştırmayın

**Merkez parametre yayını** ayrı bir yetkidir; satıcı SQL ile `mevzuat_yoneticisi_ata` yapar. Okul Sistem
Yöneticisi bu yetkiyi kendine veremez. Ayrıntı: [KURULUM.md](../KURULUM.md) §8.

## İyi uygulamalar

- Ayrılan hesabı silmeyin; pasif yapın.
- Öğretmen davetinde personel kartı + bölüm seçin.
- Alan şefinde bölüm zorunludur.
- Kendi rolünüzü düşürüp okulu yöneticisiz bırakamazsınız.
