# Sistem Yöneticisi kılavuzu

Okul içi **tam yönetici** rolüdür; Okul Müdürü ile aynı yazma yetkisine sahiptir. Harcama olur zincirinde
müdürün yerini almaz (olur müdürdedir) ama tüm ekranları kullanabilir ve kullanıcılara yetki verebilir.
Okulda aktif müdür veya sistem yöneticisinden en az biri kalmalıdır.

Platform: [PLATFORM.md](PLATFORM.md) · Ortak: [ORTAK.md](ORTAK.md)

## Yetkiler

- **Kullanıcılar:** davet, rol/bölüm, sayfa yetkisi (yazma / okuma / kapalı), pasifleştirme
- Tüm okul sayfalarında yazma yetkisi (müdürle aynı matris)
- İşlem kaydını izleme · Ana ekran özet grafikleri

## Merkez yöneticisi ile karıştırmayın

**Merkez parametre yayını** ayrı bir yetkidir; satıcı SQL ile `mevzuat_yoneticisi_ata` yapar. Okul Sistem
Yöneticisi bu yetkiyi kendine veremez. Ayrıntı: [KURULUM.md](../KURULUM.md) §8.

## İyi uygulamalar

- Ayrılan hesabı silmeyin; pasif yapın.
- Öğretmen davetinde personel kartı + bölüm seçin.
- Alan şefinde bölüm zorunludur.
- Kendi rolünüzü düşürüp okulu yöneticisiz bırakamazsınız.
