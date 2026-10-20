"""Muhasebe ve mevzuat bilgisi olmayan kullanıcılar için sade dilli kılavuz (arayüzden bağımsız).

- ROL_REHBERI: her rolün DÖSE'deki görevi, şahsi sorumluluğu ve dikkat etmesi gerekenler
- IS_REHBERLERI: "Ne yapmak istiyorsunuz?" sorusuna adım adım cevaplar (hangi sayfada, hangi düğme, kim yapar)
- SAYFA_YARDIMI: her menü sayfası için "Bu sayfa ne işe yarar?" yardımı
- SOZLUK: terimlerin günlük dille açıklaması
- CEZA_RISKLERI: sık yapılan hatalar, sonuçları ve programın önlemi
- yaklasan_sureler(): yasal takvimin somut tarihlere dökülmüş hâli
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import mevzuat as M


@dataclass(frozen=True)
class Adim:
    metin: str
    sayfa: str | None = None
    kim: str = ""


@dataclass(frozen=True)
class IsRehberi:
    kod: str
    ikon: str
    baslik: str
    ozet: str
    roller: tuple[str, ...]
    adimlar: tuple[Adim, ...]
    yasaklar: tuple[str, ...] = ()
    risk: str = ""
    dayanak: str = ""


TUM_ROLLER = tuple(M.ROLLER)
YONETIM = (M.ROL_MUDUR, M.ROL_TMY, M.ROL_SAYMAN)

# ---------------------------------------------------------------- roller
ROL_REHBERI = {
    M.ROL_MUDUR: {
        "unvan": "Harcama yetkilisi",
        "ozet": "Okul müdürü olarak döner sermayenin harcama yetkilisisiniz. Siparişler, ücret bordroları, satın almalar ve "
                "yıl sonu kâr dağıtımı sizin son onayınızla kesinleşir; ödemeler sizin imzanızla yapılır.",
        "gorevler": [
            "Siparişleri, parça başı ve fazla çalışma bordrolarını, yıl sonu dağıtımını son onaylamak",
            "Satın almalarda onay belgesini imzalamak, muayene ve kabul komisyonlarını görevlendirmek",
            "Muhasebe işlem fişi eklerini inceleyip imzalamak",
            "İnternet bankacılığında tek kullanımlık şifreyi (onay şifresi) yalnız kendinizde tutmak",
            "Fiyat tespit, takdir payı ve muayene-kabul komisyonlarını kurmak",
        ],
        "dikkat": [
            "Programda kırmızı (⛔) uyarı görünen belgeyi onaylamayın; önce hazırlayana düzelttirin.",
            "Okumadan, eki görmeden imza atmayın: mevzuata aykırı ödemeden harcama yetkilisi olarak şahsen sorumlusunuz.",
            "Hazine payı geç ödenirse gecikme zammı sizden ve saymandan yarı yarıya alınır.",
            "Banka şifrelerinin ikisi (sizinki ve saymanınki) asla tek kişide toplanmamalıdır.",
        ],
        "rehberler": ["siparis", "satin_alma", "parca_basi", "fazla_calisma", "ay_sonu", "yil_sonu", "denetim"],
    },
    M.ROL_TMY: {
        "unvan": "Gerçekleştirme görevlisi",
        "ozet": "Teknik müdür yardımcısı olarak gerçekleştirme görevlisisiniz. İşlerin yapılmasını, belgelerin hazırlanmasını ve "
                "müdüre gitmeden önce kontrol edilmesini sağlarsınız.",
        "gorevler": [
            "Siparişlerin, bordroların ve puantajların doğruluğunu kontrol etmek (onay akışında 2. aşama)",
            "Satın almalarda piyasa araştırması ve yaklaşık maliyet işlerini yürütmek",
            "Atölyelerdeki üretimi, malzeme kullanımını ve teslim tarihlerini izlemek",
            "Tanım kayıtlarını (bölüm, personel, cari, ürün) güncel tutmak",
        ],
        "dikkat": [
            "Kontrol ettiğiniz puantajdaki saatlerin gerçekten çalışılmış olduğundan emin olun; fiilen çalışılmayan saat için "
            "ödenen ücretin yarısı onaylayandan geri alınır.",
            "Geçici muayene ve kabulü yapılmamış işe parça başı ücret ödenmez.",
            "Gerçekleştirme görevlisi ile sayman (muhasebe yetkilisi) görevleri aynı kişide birleşmemelidir.",
        ],
        "rehberler": ["siparis", "parca_basi", "fazla_calisma", "satin_alma", "fiyat", "denetim"],
    },
    M.ROL_SAYMAN: {
        "unvan": "Sayman (muhasebe yetkilisi)",
        "ozet": "Döner sermayenin parası, muhasebesi, vergileri ve yasal ödemeleri sizin sorumluluğunuzdadır. Sayıştay'a hesabı "
                "siz verirsiniz.",
        "gorevler": [
            "Satış faturalarını, alış belgelerini, tahsilat ve ödemeleri kaydetmek",
            "Hazine payını her ayın 20'sine, muhtasarı 26'sına, KDV'yi 28'ine kadar bildirip ödemek",
            "Fazla çalışma ve öğrenci ücretlerini izleyen ayın 10'una kadar ödemek",
            "SHÇEK payını Ocak sonuna, Merkez Saymanlık kâr payını Şubat sonuna kadar yatırmak",
            "Resmi kayıtları BKMYBS'ye işlemek, kasa ve bankayı her ay ekstreyle karşılaştırmak",
        ],
        "dikkat": [
            "Ödeme belgesi (onaylı bordro / fatura / onay belgesi) eksiksiz olmadan ödeme yapmayın.",
            "Beyanname ve ödeme sürelerini kaçırmayın; 'Bugün Ne Yapmalıyım?' sayfası her gün hatırlatır.",
            "İnternet bankacılığında yalnız interaktif şifre sizde olmalı; onay şifresi müdürdedir.",
            "Kasada para bekletmeyin, kişisel hesap kullanmayın.",
        ],
        "rehberler": ["ay_sonu", "satis", "kasa", "satin_alma", "yil_sonu", "denetim"],
    },
    M.ROL_SEF: {
        "unvan": "Alan / atölye şefi",
        "ozet": "Atölyenize gelen işleri planlar, kimin ne kadar çalıştığını belirler ve belgelere ilk uygun görüşü verirsiniz.",
        "gorevler": [
            "Alanınıza gelen siparişleri kaydetmek ve görevli personel ile öğrencileri belirlemek",
            "Parça başı bordroda her kişinin katkı payını gerçek çalışmaya göre belirlemek",
            "Fazla çalışma puantajını (mesai çizelgesi) düzenlemek",
            "İş bitince okul komisyonuyla geçici muayene ve kabulü yaptırmak",
            "Ürünlerin maliyetini çıkarıp fiyat tespitine hazırlamak",
        ],
        "dikkat": [
            "Veli muvafakatnamesi olmayan öğrenciyi çalıştırmayın.",
            "Puantaj ve katkı paylarını gerçek çalışmaya göre yazın; bu belgeleri düzenleyen sizsiniz.",
            "Sözleşmesi imzalanmamış işe başlamayın; ücret esasını (parça başı / fazla çalışma) iş ortasında değiştirmeyin.",
        ],
        "rehberler": ["siparis", "ogrenci", "parca_basi", "fazla_calisma", "fiyat"],
    },
    M.ROL_OGRETMEN: {
        "unvan": "Öğretmen",
        "ozet": "Alanınızdaki işlerde görev alır, öğrencileri uygulamaya katar ve kendi fazla çalışmanızı kaydedersiniz.",
        "gorevler": [
            "Alanınıza gelen iş taleplerini sipariş taslağı olarak girmek",
            "Ders dışında yaptığınız fazla çalışmayı gün gün kaydetmek",
            "Öğrencilerin veli muvafakatnamelerini toplamak",
        ],
        "dikkat": [
            "Yalnız fiilen ve olağan ders/mesai saatleri dışında çalıştığınız saatleri yazın.",
            "Öğretim günlerinde günde en çok 3 saat, tatillerde en çok 8 saat fazla çalışma yazılabilir; Pazar ve bayramda yazılamaz.",
            "Aynı iş için hem parça başı hem fazla çalışma ücreti alınamaz.",
        ],
        "rehberler": ["fazla_calisma", "ogrenci", "siparis"],
    },
    M.ROL_MEMUR: {
        "unvan": "Veri giriş görevlisi",
        "ozet": "Belgeleri programa girer, çıktıları hazırlarsınız. Onay yetkiniz yoktur.",
        "gorevler": [
            "Fatura, alış belgesi, tahsilat/ödeme ve stok hareketlerini aslından birebir girmek",
            "Personel, öğrenci, cari ve malzeme kartlarını güncel tutmak",
            "Resmi yazı ve belge çıktılarını hazırlamak",
        ],
        "dikkat": [
            "Belge numarası, tarih ve tutarı belgenin aslıyla karşılaştırın; 'Belgedeki genel toplam (kontrol)' kutusunu doldurun.",
            "Kesilmiş bir faturayı silmeyin, 'İptal et' kullanın.",
        ],
        "rehberler": ["satis", "satin_alma", "kasa", "ogrenci"],
    },
    M.ROL_SISTEM: {
        "unvan": "Sistem yöneticisi",
        "ozet": "Programın kurulumu, kullanıcılar ve yedekler sizdedir. Onay ve imza yetkiniz yoktur.",
        "gorevler": [
            "Her görevliye kendi rolünde ayrı kullanıcı açmak",
            "Onay akışını açık tutmak",
            "Düzenli yedek almak ve yedeği başka bir ortamda saklamak",
            "Yeni yılda mevzuat parametrelerinin güncellenmesini sağlamak",
        ],
        "dikkat": [
            "'admin' kullanıcısının ilk şifresini değiştirin; şifreleri kimseyle paylaşmayın.",
            "Ortak kullanıcı açmayın: işlem kayıtları kimin ne yaptığını göstermelidir.",
        ],
        "rehberler": ["ilk_kurulum", "yil_sonu", "denetim"],
    },
    M.ROL_IZLEYICI: {
        "unvan": "İzleyici / denetçi",
        "ozet": "Bütün kayıtları görebilir, rapor alabilirsiniz; değişiklik yapamazsınız.",
        "gorevler": ["Kayıtları, raporları ve işlem geçmişini incelemek"],
        "dikkat": ["'Mevzuat Uyum Denetimi' sayfası işletmenin genel uyum durumunu tek ekranda gösterir."],
        "rehberler": ["denetim"],
    },
}

# ---------------------------------------------------------------- adım adım iş rehberleri
IS_REHBERLERI: list[IsRehberi] = [
    IsRehberi(
        "siparis", "🧾", "Okula bir iş (sipariş) geldi",
        "Müşteriden gelen bir işi kabul etmekten faturasını kesmeye kadar izlenecek yol.",
        (M.ROL_SEF, M.ROL_OGRETMEN, M.ROL_TMY, M.ROL_MUDUR, M.ROL_MEMUR, M.ROL_SISTEM),
        (
            Adim("Müşteriyi kaydedin. Müşteri bir kamu kurumuysa 'Kamu kurumu' kutusunu işaretleyin.",
                 "Cari Hesaplar", "Veri girişi / şef"),
            Adim("Ürünün veya hizmetin satış fiyatı daha önce belirlenmediyse önce fiyat tespiti yapın "
                 "('Ürünümün satış fiyatını belirleyeceğim' rehberi). Fiyatı komisyon belirler.",
                 "Ürün / Hizmet ve Maliyet", "Alan şefi"),
            Adim("'＋ Yeni Sipariş' düğmesine basın. Durumu 'Talep Alındı' bırakın. Müşteri, bölüm, işin konusu ve ücret esasını "
                 "seçin. Ücret esası iş bitene kadar değiştirilemez. 'Öğrenciler bu işte uygulamaya alınacak' kutusu işaretli "
                 "kalmalıdır.", "Siparişler / İş Emirleri", "Alan şefi / öğretmen"),
            Adim("Resmi yazı (ilçe MEM vb.) geldiyse 'Talep ve iş planı' sekmesine talep sayısı, tarihi, ilgiyi yazın; "
                 "yerinde inceleme sonrası keşif özeti ve iş planı kalemlerini girin. Durumu 'Keşif / İş Planı' yapın.",
                 "Siparişler / İş Emirleri", "Alan şefi / teknik personel"),
            Adim("'Kalemler ve bedel tahsisi' sekmesinde malzeme/işçilik kalemlerini girin. Program kâr, faaliyet gideri, "
                 "malzeme, işçilik ve öğrenci hakkını hesaplar. Durumu 'Teklif' yapın. Altta kırmızı uyarı varsa düzeltin.",
                 "Siparişler / İş Emirleri", "Alan şefi"),
            Adim("'Görevliler' sekmesinde işte çalışacak personeli ve öğrencileri işaretleyin. Yanında ⚠ işareti olan "
                 "öğrencinin veli muvafakatnamesi yoktur; önce muvafakat alın.", "Siparişler / İş Emirleri", "Alan şefi"),
            Adim("'Belgeler ▾' → 'Keşif ve iş planı' ve 'Proforma fatura' çıktılarını alın; resmi yazılar sayfasındaki "
                 "'İlçe MEM / okul talebine keşif-proforma cevabı' şablonuyla üst yazı ekleyin. Proforma vergi faturası "
                 "değildir. Durumu 'Proforma İletildi' yapın.", "Siparişler / İş Emirleri", "Alan şefi / sayman"),
            Adim("Muhatap kabul edince 'Onay akışı' ile onaya gönderin (şef → TMY → müdür). Onayda durum 'Sözleşme İmzalandı' "
                 "olur; 'Sözleşme / protokol' PDF'ini imzalayın. Sözleşme imzalanmadan işe başlanmaz. Peşinat varsa "
                 "'Kasa / Banka' → 'Peşinat/Avans Tahsilatı'.", "Onay Bekleyenler", "Şef → TMY → Müdür"),
            Adim("'Belgeler ▾' → 'Görevlendirme onayı' çıktısını müdüre imzalatın, siparişin durumunu 'Üretimde' yapın. "
                 "Stoktan malzeme kullanılacaksa 'Malzeme çıkışı' düğmesini kullanın.", "Siparişler / İş Emirleri", "Alan şefi"),
            Adim("İş bitince okul komisyonu 'Geçici muayene ve kabul tutanağı'nı imzalar; siparişteki 'Geçici kabul tarihi' "
                 "kutusunu doldurun. Bu tarih girilmeden parça başı ücret ödenemez.", "Siparişler / İş Emirleri", "Komisyon / şef"),
            Adim("Teslimden sonra en geç 7 gün içinde 'Faturalandır' düğmesiyle satış faturasını oluşturun, ardından "
                 "tahsilatı izleyin ('Ürün sattım / fatura keseceğim' rehberi).", "Siparişler / İş Emirleri", "Sayman"),
        ),
        (
            "Öğrencinin uygulamaya alınmadığı iş kabul edilmez.",
            "Sözleşme imzalanmadan işe başlanmaz.",
            "İşi dışarıda yaptırıp okulun faturasıyla satmak yasaktır; iş okulda, öğrenciyle birlikte bizzat üretilir.",
            "Ücret esası (parça başı / fazla çalışma) iş ortasında değiştirilmez.",
            "Komisyonun belirlediği fiyatın altında satış yapılmaz, müşteri lehine indirim yapılmaz.",
        ),
        "Mevzuata aykırı kabul edilen işten yapılan ücret ödemeleri kamu zararı sayılır; tutar kanuni faiziyle birlikte "
        "onaylayan görevlilerden geri istenebilir.",
        "3423 s.K.; DÖSE Yönetmeliği md.7-9; Çalışma Yönergesi md.26; DHGM 15.01.2026 yazısı m.1; 5018 s.K. md.71",
    ),
    IsRehberi(
        "fiyat", "🏷️", "Ürünümün satış fiyatını belirleyeceğim",
        "Maliyet çıkarıp fiyat tespit tutanağı hazırlama.",
        (M.ROL_SEF, M.ROL_OGRETMEN, M.ROL_TMY, M.ROL_MUDUR, M.ROL_SAYMAN, M.ROL_SISTEM),
        (
            Adim("Üründe kullanılan malzemelerin kartları tanımlı olsun (yoksa '＋ Yeni' ile ekleyin).",
                 "Malzeme / Stok Kartları", "Alan şefi"),
            Adim("Ürünü '＋ Yeni' ile kaydedin, ardından 'Maliyet Analizi / Fiyat Tespiti' düğmesine basın.",
                 "Ürün / Hizmet ve Maliyet", "Alan şefi"),
            Adim("Malzeme, işçilik, öğrenci hakkı, enerji gibi satırları girin. 'Otomatik hesapla' işaretliyken program "
                 "yasal asgari kâr ve faaliyet gideri oranlarını kendisi uygular.", "Ürün / Hizmet ve Maliyet", "Alan şefi"),
            Adim("Piyasada benzer ürünlerin fiyatını araştırıp 'piyasa araştırması' kutusuna yazın.",
                 "Ürün / Hizmet ve Maliyet", "Alan şefi"),
            Adim("'Fiyat Tespit Tutanağı (PDF)' çıktısını komisyona imzalatın, sonra 'Fiyatı ürün kartına işle' düğmesine basın.",
                 "Ürün / Hizmet ve Maliyet", "Komisyon"),
        ),
        (
            "Komisyon kararı olmadan fiyat belirlenmez veya indirim yapılmaz.",
            "Tarım ve hayvan ürünleri bölge rayicinin altında satılmaz.",
            "Maliyetin altında satış yapılmaz.",
        ),
        "Tespit edilen fiyatın altında yapılan satışta aradaki fark kamu zararı olarak sorumlulardan istenebilir.",
        "Çalışma Yönergesi md.26/g, md.29/a; DÖSE Yönetmeliği md.8/2",
    ),
    IsRehberi(
        "ogrenci", "🎓", "Öğrenciyi üretime katacağım",
        "Öğrencinin işte çalışabilmesi ve ücret alabilmesi için gerekenler.",
        (M.ROL_SEF, M.ROL_OGRETMEN, M.ROL_TMY, M.ROL_MEMUR, M.ROL_MUDUR),
        (
            Adim("Öğrenciyi kaydedin: T.C. kimlik no, sınıf, bölüm ve ücret alacaksa kendi adına açılmış IBAN.",
                 "Öğrenciler", "Öğretmen / veri girişi"),
            Adim("'Veli muvafakatnamesi (seçili öğrenciler)' çıktısını alın ve veliye imzalatın.",
                 "Resmi Yazılar / Belgeler", "Öğretmen"),
            Adim("İmzalı belge gelince öğrenci kartında 'veli muvafakat' kutusunu işaretleyip tarihini girin; aslını dosyalayın.",
                 "Öğrenciler", "Öğretmen / veri girişi"),
            Adim("Siparişin 'Görevliler' sekmesinde öğrenciyi işaretleyin.", "Siparişler / İş Emirleri", "Alan şefi"),
            Adim("Öğrenci ücreti parça başı bordrosunda öğrenci hakkından ödenir; aylık en çok 1 asgari ücret. Ödeme izleyen "
                 "ayın 10'una kadar yapılır.", "Parça Başı Ücret", "Şef / sayman"),
        ),
        (
            "Veli muvafakatnamesi olmayan öğrenci çalıştırılmaz ve ona ücret ödenmez.",
            "İş sağlığı ve güvenliği önlemleri alınmadan öğrenci makine başında çalıştırılmaz.",
            "Öğrenci ücreti başkasının (veli, öğretmen) hesabına gönderilmez.",
        ),
        "Muvafakatsiz çalıştırılan öğrenciye yapılan ödeme mevzuata aykırıdır; bir iş kazasında okul yönetimi için idari ve "
        "cezai sorumluluk doğar.",
        "DÖSE Yönetmeliği md.8/1, md.8/6; Çalışma Yönergesi md.42/c",
    ),
    IsRehberi(
        "parca_basi", "⚙️", "Parça başı ücret dağıtacağım",
        "Biten bir işin işçiliğini çalışan personel ve öğrencilere dağıtma.",
        (M.ROL_SEF, M.ROL_TMY, M.ROL_MUDUR, M.ROL_SAYMAN, M.ROL_SISTEM),
        (
            Adim("Yalnız bitmiş ve geçici kabulü yapılmış işler için bordro yapılır: siparişte 'Geçici kabul tarihi' dolu olmalı.",
                 "Siparişler / İş Emirleri", "Alan şefi"),
            Adim("'＋ Yeni bordro' ile yıl, ay ve siparişi seçin; kabul edilen işçilik tutarı siparişten gelir.",
                 "Parça Başı Ücret", "Alan şefi"),
            Adim("'Siparişteki görevlileri getir' ile kişileri listeleyin, her kişinin katkı payını gerçek çalışmaya göre yazın. "
                 "'Günlük puantaj…' ile çalıştıkları günleri işaretleyin.", "Parça Başı Ücret", "Alan şefi"),
            Adim("Program aylık tavanları (eğitim-öğretim 2, teknik hizmetler 1,5, diğer sınıflar 1, öğrenci 1 asgari ücret), "
                 "en az %30 öğrenci hakkını, gelir ve damga vergisini kendisi hesaplar. Kırmızı uyarıları düzeltin ve kaydedin.",
                 "Parça Başı Ücret", "Alan şefi"),
            Adim("Bordroyu onaya gönderin: teknik müdür yardımcısı kontrol eder, müdür onaylar.", "Onay Bekleyenler", "TMY → Müdür"),
            Adim("Onaydan sonra 'Bordro PDF' ve 'Puantaj cetveli PDF' çıktılarını imzalatın.", "Parça Başı Ücret", "Şef / TMY / müdür"),
            Adim("'Banka listesi (Excel)' ile bankaya ödeme talimatı verin, ödeme yapılınca 'Ödeme kaydı oluştur' düğmesine "
                 "basın. Öğrenci ücretleri izleyen ayın 10'una kadar ödenir.", "Parça Başı Ücret", "Sayman"),
            Adim("Kesilen gelir vergisi ve damga vergisi izleyen ayın 26'sına kadar muhtasar beyannameyle ödenir.",
                 "KDV / Muhtasar Özeti", "Sayman"),
        ),
        (
            "Aynı iş için hem parça başı hem fazla çalışma ücreti ödenmez.",
            "İdari görevliye (müdür, müdür yardımcısı, şef, sayman) aynı ay içinde ikisi birden ödenmez.",
            "Dağıtılan toplam, siparişin şartnamedeki işçiliğini aşamaz.",
            "İşte fiilen çalışmayan kişiye pay verilmez.",
        ),
        "Tavanı aşan, hak etmeyene yapılan veya belgesiz ödemeler kamu zararıdır; kanuni faiziyle birlikte bordroyu "
        "düzenleyen ve onaylayanlardan geri istenir.",
        "DÖSE Yönetmeliği md.8; Çalışma Yönergesi md.42; 5018 s.K. md.71",
    ),
    IsRehberi(
        "fazla_calisma", "⏰", "Fazla çalışma yaptım / ücreti ödenecek",
        "Ders ve mesai dışında yapılan döner sermaye çalışmasının ücretlendirilmesi.",
        (M.ROL_OGRETMEN, M.ROL_SEF, M.ROL_TMY, M.ROL_MUDUR, M.ROL_SAYMAN, M.ROL_SISTEM),
        (
            Adim("Önce görevlendirilmiş olmalısınız: siparişin 'Görevliler' sekmesinde adınız işaretli olmalı.",
                 "Siparişler / İş Emirleri", "Alan şefi"),
            Adim("'＋ Kayıt ekle' ile personeli, siparişi ve ayı seçin. 'Günlük puantaj…' ile her günü ayrı girin: öğretim "
                 "günlerinde en çok 3 saat, tatillerde en çok 8 saat. Pazar ve bayram günleri yazılamaz.",
                 "Fazla Çalışma Ücreti", "Öğretmen / şef"),
            Adim("Saat ücreti Mevzuat Parametreleri'nden gelir (Bütçe Kanunu'ndaki azami tutarı geçemez).",
                 "Fazla Çalışma Ücreti", ""),
            Adim("Kayıt onay akışından geçer: alan şefi → teknik müdür yardımcısı → okul müdürü.",
                 "Onay Bekleyenler", "Şef → TMY → Müdür"),
            Adim("'Puantaj (mesai çizelgesi) PDF' çıktısını şef düzenler, TMY ve sayman imzalar, müdür onaylar. "
                 "'Bordro PDF' ile ödeme bordrosunu alın.", "Fazla Çalışma Ücreti", "Şef / TMY / sayman / müdür"),
            Adim("Ödeme izleyen ayın 10'una kadar yapılır: 'Banka listesi (Excel)' → banka; ardından 'Ödeme kaydı oluştur'.",
                 "Fazla Çalışma Ücreti", "Sayman"),
        ),
        (
            "Fiilen çalışılmayan saat yazılmaz; ders saati veya normal mesai fazla çalışma sayılmaz.",
            "Yardımcı hizmetler sınıfı personel ve şoförler döner sermayeden fazla çalışma ücreti alamaz.",
            "Aynı iş için parça başı ücret alan kişiye fazla çalışma ücreti ödenmez.",
            "Bir siparişte ödenen fazla çalışma ve öğrenci hakkı toplamı sipariş işçiliğini aşamaz.",
        ),
        "Fiilen çalışmadığı hâlde ödenen ücret bir katı fazlasıyla geri alınır ve bunun yarısı mesai çizelgesini onaylayan "
        "yetkiliden tahsil edilir.",
        "Merkezi Yönetim Bütçe Kanunu (K) cetveli III-3, III-4; Çalışma Yönergesi md.9; DÖSE Yönetmeliği md.8/7",
    ),
    IsRehberi(
        "satin_alma", "🛒", "Malzeme veya hizmet satın alacağım",
        "İhtiyacın belirlenmesinden faturanın kaydına ve ödemeye kadar.",
        (M.ROL_MUDUR, M.ROL_TMY, M.ROL_SAYMAN, M.ROL_MEMUR, M.ROL_SEF, M.ROL_SISTEM),
        (
            Adim("İhtiyacı yazılı olarak belirleyin (alan şefinin talep yazısı). Tedarikçi firmayı kaydedin.",
                 "Cari Hesaplar", "Alan şefi / veri girişi"),
            Adim("Tutar (KDV hariç) doğrudan temin limitinin altındaysa 'Doğrudan temin belgeleri…' düğmesiyle onay belgesi, "
                 "piyasa araştırma tutanağı ve yaklaşık maliyet cetvelini hazırlayıp imzalatın. Limit Mevzuat Parametreleri'nde "
                 "yazılıdır; limit üstündeki alımlar ihaleyle yapılır.", "Alış / Gider Belgeleri", "TMY / müdür"),
            Adim("Mümkünse en az üç firmadan yazılı teklif alın ve en uygun teklifi seçin.", None, "Piyasa araştırma görevlileri"),
            Adim("Mal veya hizmet teslim alınınca muayene ve kabul yapılır. Fatura döner sermaye işletmesi adına (işletmenin "
                 "VKN'si ile) kesilmiş olmalıdır.", None, "Muayene kabul komisyonu"),
            Adim("'＋ Yeni Alış Belgesi' ile belge türü, numara, tarih, tedarikçi, temin usulü ve gider türünü seçip kalemleri "
                 "girin. Belgedeki genel toplamı 'Belgedeki genel toplam (kontrol)' kutusuna yazın; tutmazsa program uyarır.",
                 "Alış / Gider Belgeleri", "Sayman / veri girişi"),
            Adim("Çiftçiden alımda belge türü 'Müstahsil Makbuzu (e-MM)' ve stopaj seçilir; serbest meslek erbabından alımda "
                 "'Serbest Meslek (%20)' stopajı seçilir. Kesilen stopaj muhtasarla ödenir.", "Alış / Gider Belgeleri", "Sayman"),
            Adim("Ödemeyi bankadan yapın ve 'Ödeme gir' ile faturaya bağlayın.", "Alış / Gider Belgeleri", "Sayman"),
        ),
        (
            "İhtiyaç, limitin altında kalsın diye parçalara bölünemez.",
            "Faturası veya yasal belgesi olmayan harcama yapılmaz (yalnız fatura, müstahsil makbuzu, gider pusulası, "
            "serbest meslek makbuzu vb.).",
            "Perakende satış fişindeki KDV indirilemez.",
            "Faaliyet gideri karşılığında para yoksa idari harcama yapılamaz.",
            "Döner sermaye parası, işletmenin üretim ve işletme giderleri dışındaki okul ihtiyaçlarına harcanmaz; "
            "tereddütte saymana danışın.",
        ),
        "İhtiyacı bölerek doğrudan temin yapmak ve belgesiz harcama denetimde kamu zararı ve disiplin sorumluluğu doğurur.",
        "4734 s.K. md.22/d; Döner Sermayeli Kuruluşlar İhale Yönetmeliği; VUK md.228-238; Çalışma Yönergesi md.11, md.46",
    ),
    IsRehberi(
        "satis", "💰", "Ürün sattım / fatura keseceğim",
        "Satışın faturalanması ve paranın tahsili.",
        (M.ROL_SAYMAN, M.ROL_MEMUR, M.ROL_TMY, M.ROL_MUDUR, M.ROL_SISTEM),
        (
            Adim("Satılan ürünün fiyatı komisyonca belirlenmiş olmalı.", "Ürün / Hizmet ve Maliyet", "Komisyon"),
            Adim("Siparişe bağlı işte 'Faturalandır' düğmesini kullanın; peşin satışta 'Satış Faturaları' sayfasında "
                 "'＋ Yeni Satış Faturası'na basın.", "Siparişler / İş Emirleri", "Sayman / veri girişi"),
            Adim("Belge türünü seçin: alıcı e-fatura kullanıyorsa e-Fatura, kullanmıyorsa e-Arşiv Fatura. Faturayı GİB "
                 "portalından veya entegratörden düzenleyip numarasını programa yazın.", "Satış Faturaları", "Sayman"),
            Adim("Kamu kurumlarına yapılan bazı satışlarda KDV tevkifatı uygulanır; emin değilseniz saymana sorun.",
                 "Satış Faturaları", "Sayman"),
            Adim("Para hesaba geçince 'Tahsilat gir' ile dekont numarasıyla kaydedin. Hazine payı tahsil edilen tutardan "
                 "hesaplandığından tahsilatı aynı gün girin.", "Satış Faturaları", "Sayman"),
        ),
        (
            "Faturasız satış yapılmaz; fatura teslimden itibaren en geç 7 gün içinde düzenlenir.",
            "Fatura numaraları her yıl 1'den başlar ve atlanmaz.",
            "Kesilmiş fatura silinmez; gerekiyorsa iptal edilir ve iptal nedeni yazılır.",
            "Komisyon fiyatının altına inilmez.",
        ),
        "Fatura düzenlenmemesi veya geç düzenlenmesi Vergi Usul Kanunu'na göre özel usulsüzlük cezası gerektirir; "
        "tahsilat eksik girilirse hazine payı eksik bildirilir ve gecikme zammı doğar.",
        "VUK md.229-233, md.353; Çalışma Yönergesi md.44",
    ),
    IsRehberi(
        "kasa", "🏦", "Para tahsil ettim / ödeme yapacağım",
        "Kasa ve banka hareketlerinin doğru kaydı.",
        (M.ROL_SAYMAN, M.ROL_MEMUR, M.ROL_MUDUR, M.ROL_SISTEM),
        (
            Adim("Tahsilat ve ödemeleri mümkün olduğunca bankadan yapın. Elden alınan parayı aynı gün veya ertesi iş günü "
                 "bankaya yatırın.", None, "Sayman"),
            Adim("Gelen para için '＋ Giriş (tahsilat)'. İşlem türünü doğru seçin: fatura tahsilatı 'Tahsilat', sipariş "
                 "peşinatı 'Peşinat/Avans Tahsilatı', banka faizi 'Faiz/Diğer Gelir'. Fatura veya siparişi mutlaka bağlayın.",
                 "Kasa / Banka", "Sayman"),
            Adim("Personel, öğrenci, hazine payı ve SHÇEK ödemelerini kendi sayfalarındaki 'Ödeme kaydı oluştur' düğmesiyle "
                 "yapın; program tutarı ve bağlantıyı doğru kurar.", "Kasa / Banka", "Sayman"),
            Adim("İnternet bankacılığında onay (tek kullanımlık) şifresi müdürde, interaktif şifre saymanda olmalıdır.",
                 None, "Müdür / sayman"),
            Adim("Her ay sonunda programdaki banka bakiyesini banka ekstresiyle karşılaştırın, kasadaki parayı sayın.",
                 "Kasa / Banka", "Sayman"),
        ),
        (
            "Kasa bakiyesi hiçbir zaman eksiye düşmez; düşüyorsa bir tahsilat girilmemiş veya ödeme yanlış girilmiştir.",
            "Döner sermaye parası kişisel hesaba alınmaz, kişisel hesaptan ödenmez.",
            "Banka şifrelerinin ikisi tek kişide toplanmaz.",
        ),
        "Kasa ve banka noksanından sayman ve harcama yetkilisi şahsen sorumludur; kişisel hesap kullanımı zimmet "
        "şüphesi doğurur.",
        "DHGM 15.01.2026 yazısı m.15; 5018 s.K. md.71; TCK md.247",
    ),
    IsRehberi(
        "ay_sonu", "📅", "Ay sonu / ay başı yapılacaklar",
        "Her ay tekrarlanan yasal yükümlülükler ve son günleri.",
        (M.ROL_SAYMAN, M.ROL_MUDUR, M.ROL_TMY, M.ROL_MEMUR, M.ROL_SISTEM),
        (
            Adim("Ayın bütün satış, alış, tahsilat ve ödeme belgelerinin girildiğini kontrol edin; banka bakiyesini ekstreyle "
                 "karşılaştırın.", "Kasa / Banka", "Sayman"),
            Adim("Ayın 10'una kadar: önceki ayın fazla çalışma ve öğrenci ücretlerini ödeyin.",
                 "Fazla Çalışma Ücreti", "Sayman"),
            Adim("Ayın 20'sine kadar: 'Seçili ayı hesapla / güncelle' → 'Bildirim (Örnek 30) PDF' → bildirin ve ödeyin → "
                 "'Bildirildi olarak işaretle' ve 'Ödeme kaydı oluştur'. Hiç tahsilat olmasa da bildirim verilir.",
                 "Hazine Payı / SHÇEK", "Sayman"),
            Adim("Ayın 26'sına kadar: 'Seçili ayın muhtasar detayı' ile personel ve öğrenci ücretlerinden kesilen gelir ve "
                 "damga vergisini, müstahsil ve serbest meslek stopajını muhtasar beyannamesiyle beyan edip ödeyin.",
                 "KDV / Muhtasar Özeti", "Sayman"),
            Adim("Ayın 28'ine kadar: KDV beyannamesini verin (hesaplanan KDV − indirilecek KDV). O ay hiç işlem olmasa da "
                 "KDV beyannamesi verilir.", "KDV / Muhtasar Özeti", "Sayman"),
            Adim("Üç ayda bir (5 Nisan, 5 Temmuz, 5 Ekim, 5 Ocak): üç aylık faaliyet raporunu gönderin.", "Raporlar", "Sayman / TMY"),
            Adim("'Mevzuat Uyum Denetimi' sayfasında kırmızı bulgu kalmadığını kontrol edin ve yedek alın.",
                 "Mevzuat Uyum Denetimi", "Sayman / müdür"),
        ),
        (
            "Son güne bırakmayın: son gün hafta sonuna veya tatile denk gelse bile işi önceki iş gününde bitirin.",
            "Ödenecek tutar sıfır olsa da KDV beyannamesi ve hazine payı bildirimi verilir.",
        ),
        "Beyannamenin geç verilmesi usulsüzlük cezası, verginin geç ödenmesi gecikme zammı, eksik beyan vergi ziyaı cezası "
        "doğurur. Hazine payı gecikirse aylık %1 zam harcama yetkilisi ve saymandan yarı yarıya alınır.",
        "VUK md.344, md.352; 6183 s.K. md.51; Muhasebat Genel Tebliği (Sıra No: 73) md.6-7",
    ),
    IsRehberi(
        "yil_sonu", "🏁", "Yıl sonu ve yeni yıl işleri",
        "Kâr dağıtımı, ÜTP, SHÇEK, Merkez Saymanlık payı ve yeni yıl hazırlığı.",
        (M.ROL_SAYMAN, M.ROL_MUDUR, M.ROL_TMY, M.ROL_SISTEM),
        (
            Adim("Aralık sonunda bütün belgelerin girildiğinden emin olun, stok sayımı yapıp farkları işleyin.",
                 "Stok Durumu ve Hareketleri", "Sayman / TMY"),
            Adim("Ocak başında yeni yılın asgari ücretini, gelir vergisi tarifesini, fazla çalışma ücretini, doğrudan temin "
                 "limitini, tatil ve bayram günlerini girin ('Mevzuat varsayılanlarını yükle' ile başlayıp kontrol edin).",
                 "Mevzuat Parametreleri", "Sayman / sistem yöneticisi"),
            Adim("31 Ocak'a kadar: önceki yılın brüt hasılatının %1'i SHÇEK payı olarak yatırılır ('SHÇEK ödeme kaydı').",
                 "Hazine Payı / SHÇEK", "Sayman"),
            Adim("'Yardımcı defterden al' → 'Personeli yükle' → 'Saat verilerini getir' → 'Hesapla' → 'Kaydet (taslak)'. "
                 "Yıl içinde 30 günden fazla okul dışında görevlendirilenler ve fiilen çalışmayanlar hariç tutulur.",
                 "Yıl Sonu Kârı ve ÜTP", "Sayman"),
            Adim("Takdir payı komisyon kararını gerekçeli olarak yazın. Dağıtım sayman → TMY → müdür onayından geçer "
                 "('Kesinleştir').", "Yıl Sonu Kârı ve ÜTP", "Sayman → TMY → Müdür"),
            Adim("Şubat sonuna kadar: Merkez Saymanlık kâr payını yatırın ('Merkez Saymanlık yazısı', 'Merkez Saymanlık "
                 "ödeme kaydı').", "Hazine Payı / SHÇEK", "Sayman"),
            Adim("ÜTP bilanço tarihinden itibaren 2 ay içinde ödenir: 'ÜTP dağıtım cetveli (PDF)' ve 'Banka listesi (Excel)'.",
                 "Yıl Sonu Kârı ve ÜTP", "Sayman"),
            Adim("Mart sonuna kadar: kâr ve SHÇEK dekontlarını MEBBİS Döner Sermaye Takip Modülüne yükleyin.", None, "Sayman"),
        ),
        (
            "Kişi başı yıllık ÜTP, yıllık asgari ücret toplamını geçemez.",
            "Takdir payı komisyonu üyeleri takdir payından yararlanamaz.",
            "Kârın 1/3'ünden fazlası ÜTP olarak dağıtılamaz.",
        ),
        "Tavanı aşan veya hak etmeyene ödenen ÜTP kamu zararıdır; Merkez Saymanlık ve SHÇEK paylarının yatırılmaması "
        "denetimde tespit edilir ve sorumlulardan istenir.",
        "3423 s.K. md.1; DÖSE Yönetmeliği md.4-6; 2828 s.K. md.18/1-k; DHGM 15.01.2026 yazısı m.9",
    ),
    IsRehberi(
        "denetim", "🔍", "Denetime (müfettiş / Sayıştay) hazırlanıyorum",
        "Denetimde istenecek dosyalar ve son kontroller.",
        (M.ROL_MUDUR, M.ROL_TMY, M.ROL_SAYMAN, M.ROL_SISTEM, M.ROL_IZLEYICI),
        (
            Adim("'Mevzuat Uyum Denetimi' sayfasındaki kırmızı ve sarı bulguları giderin.", "Mevzuat Uyum Denetimi", "Herkes"),
            Adim("Her sipariş için dosya: fiyat teklifi, sözleşme, ön maliyet çizelgesi, görevlendirme onayı, geçici kabul ve "
                 "muayene kabul tutanakları, fatura ve tahsilat dekontu.", "Siparişler / İş Emirleri", "Şef / TMY"),
            Adim("Her ücret ödemesi için: onaylı bordro, puantaj, banka listesi ve dekont.", "Parça Başı Ücret", "Sayman"),
            Adim("Muhasebe işlem fişlerini ('Muhasebe işlem fişi PDF') eklerini inceleyerek müdüre imzalatın.",
                 "Yevmiye / Mizan", "Sayman / müdür"),
            Adim("Satın almalar için doğrudan temin dosyası: onay belgesi, piyasa araştırma tutanağı, teklifler, muayene kabul.",
                 "Alış / Gider Belgeleri", "TMY"),
            Adim("Veli muvafakatnameleri, fiyat tespit tutanakları ve komisyon kararlarını dosyalayın.",
                 "Resmi Yazılar / Belgeler", "Şef / TMY"),
            Adim("Hazine payı bildirimleri ile KDV ve muhtasar tahakkuk ve dekontlarını dosyalayın.",
                 "Hazine Payı / SHÇEK", "Sayman"),
            Adim("Programdaki mizanın BKMYBS kayıtlarıyla tuttuğunu kontrol edin. İşlem kaydı kimin ne yaptığını gösterir.",
                 "Yevmiye / Mizan", "Sayman"),
        ),
        (),
        "Eksik belge, belgesiz ödeme veya mevzuata aykırı ödeme Sayıştay yargılamasında tazmin hükmüne konu olur.",
        "5018 s.K. md.71; 6085 s.K. (Sayıştay Kanunu)",
    ),
    IsRehberi(
        "ilk_kurulum", "🛠️", "Programı ilk kez kuruyorum",
        "Kurum, görevliler, kullanıcılar ve yıllık ayarların yapılması.",
        (M.ROL_SISTEM, M.ROL_MUDUR, M.ROL_SAYMAN),
        (
            Adim("Okul adı, işletme VKN'si, banka ve IBAN, harcama yetkilisi, gerçekleştirme görevlisi, sayman ve tahsis "
                 "edilen sermayeyi girin.", "Kurum ve Görevliler", "Sistem yöneticisi / müdür"),
            Adim("Yılın mevzuat parametrelerini kontrol edip kaydedin.", "Mevzuat Parametreleri", "Sayman"),
            Adim("Bölüm, alan ve atölyeleri tanımlayın.", "Bölüm / Alan / Atölyeler", "TMY"),
            Adim("Personeli kaydedin. Hizmet sınıfı ve DÖSE görevi doğru seçilmelidir: ücret tavanları ve ÜTP payları buna göre "
                 "hesaplanır.", "Personel", "TMY / veri girişi"),
            Adim("Her görevliye kendi rolünde ayrı kullanıcı açın, onay akışını açın, 'admin' şifresini değiştirin.",
                 "Kullanıcılar", "Sistem yöneticisi"),
            Adim("İlk yedeği alın; yedekleri düzenli olarak başka bir diske de kopyalayın.",
                 "Yedekleme / İşlem Kaydı", "Sistem yöneticisi"),
        ),
        (
            "Harcama yetkilisi ile sayman aynı kişi olamaz.",
            "Ortak kullanıcı ve ortak şifre kullanılmaz.",
        ),
        "",
        "DÖSE Yönetmeliği md.3; DHGM 15.01.2026 yazısı m.15",
    ),
]

REHBER = {r.kod: r for r in IS_REHBERLERI}


def rol_rehberleri(rol: str) -> list[IsRehberi]:
    """Rolün önce kendi öncelikli rehberleri, sonra kendisini ilgilendiren diğerleri."""
    oncelik = ROL_REHBERI.get(rol, {}).get("rehberler", [])
    sirali = [REHBER[k] for k in oncelik if k in REHBER]
    return sirali + [r for r in IS_REHBERLERI if r not in sirali and rol in r.roller]


# ---------------------------------------------------------------- sayfa yardımları
# sayfa: (ne işe yarar, nasıl kullanılır, dikkat, ilgili rehber)
SAYFA_YARDIMI: dict[str, tuple[str, list[str], list[str], str | None]] = {
    "Bugün Ne Yapmalıyım?": (
        "Size özel yapılacaklar listesi: süresi geçmiş veya yaklaşan yasal işler, onayınızı bekleyen belgeler ve "
        "rolünüzün sorumlulukları.",
        ["Kırmızı satırlar acildir, önce onları yapın.", "Bir satıra çift tıklayınca ilgili sayfa açılır.",
         "'Nasıl yapılır?' düğmesi o işin adım adım anlatımını açar."],
        ["Liste her açılışta yeniden hesaplanır; işi bitirince satır kendiliğinden kaybolur."], None),
    "Nasıl Yaparım? (Adım Adım)": (
        "Sık yapılan işlerin hangi sayfada, hangi düğmeyle ve kim tarafından yapılacağını sırasıyla anlatır.",
        ["Soldan yapmak istediğiniz işi seçin.", "Adımın yanındaki 'Git' düğmesi ilgili sayfayı açar."],
        ["'Asla yapmayın' bölümündekiler denetimde en sık ceza konusu olan hatalardır."], None),
    "Mevzuat Uyum Denetimi": (
        "Bütün kayıtları tarar; mevzuata aykırı, eksik veya riskli durumları sade dille, ne yapılması gerektiğiyle birlikte "
        "listeler. Uyum puanı işletmenin genel durumunu gösterir.",
        ["'Denetimi çalıştır' ile tarayın.", "Bir bulguyu seçince altta ne yapmanız gerektiği görünür.",
         "'İlgili sayfaya git' ile düzeltmeyi yapın, sonra denetimi yeniden çalıştırın."],
        ["Kırmızı bulgular ceza veya kamu zararı riski taşır; sarılar eksiklik veya dikkat gerektiren durumlardır."],
        "denetim"),
    "Gösterge Paneli": (
        "İşletmenin satış, tahsilat, nakit, alacak ve kâr durumunu tek bakışta gösterir.",
        ["Üstteki çalışma yılını değiştirerek önceki yılları görebilirsiniz.", "Uyarı satırına çift tıklayınca ilgili sayfa açılır."],
        ["'Yardımcı defter kârı' resmi kâr değildir; resmi kayıtlar BKMYBS'dedir."], None),
    "Onay Bekleyenler": (
        "Sizin kararınızı bekleyen sipariş, bordro ve dağıtım belgeleri.",
        ["Belgeyi seçip 'Akış ve geçmiş' ile inceleyin.", "Uygunsa 'Seçilenleri onayla / uygun gör', değilse gerekçe yazarak "
         "'İade et'."],
        ["Kırmızı uyarılı belgeyi onaylamayın. Onay, ödeme sorumluluğunu üstlenmek demektir."], None),
    "Mevzuat Rehberi": (
        "Programdaki hesapların yasal dayanakları, yasal takvim, yılın parametreleri, terimler sözlüğü ve sık yapılan "
        "hataların cezaları.", ["Sekmeler arasında gezinin."], [], None),
    "Kurum ve Görevliler": (
        "Okulun, döner sermaye işletmesinin ve imza yetkililerinin bilgileri. Bütün belgelerdeki başlık ve imzalar buradan gelir.",
        ["Bilgileri doldurup 'Kaydet'e basın.", "'Personel kayıtlarından görevlileri doldur' isimleri personel kartlarından alır."],
        ["Harcama yetkilisi ile sayman aynı kişi olamaz.", "VKN ve IBAN döner sermaye işletmesine ait olmalıdır."], "ilk_kurulum"),
    "Mevzuat Parametreleri": (
        "Asgari ücret, vergi oranları, tavanlar, fazla çalışma ücreti, doğrudan temin limiti ve tatil günleri gibi her yıl "
        "değişen değerler.",
        ["Yeni yılda 'Mevzuat varsayılanlarını yükle' ile başlayın, değerleri Resmî Gazete ve Bakanlık yazılarıyla "
         "karşılaştırıp 'Kaydet'e basın."],
        ["Yanlış parametre bütün bordro ve vergi hesaplarını bozar; tereddütte saymana danışın."], "yil_sonu"),
    "Bölüm / Alan / Atölyeler": (
        "Döner sermaye çalışması yapan bölümler. Siparişler, personel ve ÜTP dağıtımı bölüme göre izlenir.",
        ["'＋ Yeni' ile bölüm ekleyin; ÜTP dağıtım yöntemini seçin."], [], "ilk_kurulum"),
    "Personel": (
        "Döner sermaye çalışmalarına katılan personelin kartları.",
        ["'＋ Yeni' ile ekleyin ya da 'Excel'den İçe Aktar' kullanın."],
        ["Hizmet sınıfı ve DÖSE görevi doğru seçilmelidir: aylık ücret tavanı ve ÜTP payı buna göre hesaplanır.",
         "Ödeme alacak kişinin kendi adına IBAN'ı girilmelidir."], "ilk_kurulum"),
    "Öğrenciler": (
        "Üretime katılan öğrencilerin kartları ve veli muvafakat durumları.",
        ["'＋ Yeni' ile öğrenci ekleyin.", "Veli muvafakatnamesi imzalanınca 'veli muvafakat' kutusunu işaretleyip tarihini girin."],
        ["Muvafakatnamesi olmayan öğrenci çalıştırılmaz, ona ücret ödenmez."], "ogrenci"),
    "Cari Hesaplar": (
        "Müşteriler (alıcılar) ve tedarikçiler (satıcılar). 'Cari' alışveriş yapılan kişi veya kurum demektir.",
        ["'＋ Yeni' ile ekleyin; vergi numarasını ve kamu kurumu olup olmadığını girin."],
        ["Çiftçiden alım yapılacaksa türünü 'Çiftçi (Müstahsil)' seçin."], "siparis"),
    "Malzeme / Stok Kartları": (
        "Üretimde kullanılan malzemelerin ve satılan malların kartları.",
        ["'＋ Yeni' ile malzeme ekleyin; kritik stok miktarı girerseniz azaldığında uyarı alırsınız."], [], "fiyat"),
    "Ürün / Hizmet ve Maliyet": (
        "Satılan ürün ve hizmetler, maliyet analizi ve fiyat tespiti.",
        ["Ürünü seçip 'Maliyet Analizi / Fiyat Tespiti' düğmesine basın.", "'Fiyat Tespit Tutanağı (PDF)'yi komisyona imzalatın."],
        ["Fiyatı komisyon belirler; komisyon fiyatının altında satış yapılamaz."], "fiyat"),
    "Siparişler / İş Emirleri": (
        "Talep → keşif/iş planı → proforma → sözleşme → üretim; bedelin yasal paylara bölünmesi.",
        ["'＋ Yeni Sipariş' ile başlayın; resmi yazıyı 'Talep ve iş planı' sekmesine işleyin.",
         "'Belgeler ▾' menüsünden keşif tutanağı, proforma, sözleşme, görevlendirme ve kabul alın.",
         "'Onay akışı' ile onaya gönderin.", "İş bitince 'Faturalandır'."],
        ["Proforma e-Fatura değildir.", "Sözleşmesiz işe başlanmaz.", "Öğrencinin çalışmadığı iş kabul edilmez.",
         "Geçici kabul tarihi girilmeden parça başı ödenmez."], "siparis"),
    "Satış Faturaları": (
        "Satışların faturaları ve tahsilatları.",
        ["'＋ Yeni Satış Faturası' ile ekleyin; para gelince 'Tahsilat gir'."],
        ["Fatura teslimden itibaren 7 gün içinde düzenlenir.", "Kesilmiş fatura silinmez, 'İptal et' kullanılır."], "satis"),
    "Alış / Gider Belgeleri": (
        "Satın alınan malzeme ve hizmetlerin faturaları ile diğer gider belgeleri.",
        ["'＋ Yeni Alış Belgesi' ile ekleyin.", "Doğrudan temin dosyası için 'Doğrudan temin belgeleri…'."],
        ["Belgedeki genel toplamı kontrol kutusuna yazın.", "İhtiyaç limit altında kalsın diye bölünmez."], "satin_alma"),
    "Kasa / Banka": (
        "Döner sermayeye giren ve çıkan bütün paralar.",
        ["Gelen para için '＋ Giriş (tahsilat)', giden para için '－ Çıkış (ödeme)'.", "İşlem türünü ve bağlı faturayı seçin."],
        ["Kasa eksiye düşemez.", "Hazine payı tahsilatlardan hesaplanır; tahsilatı eksiksiz ve zamanında girin."], "kasa"),
    "Stok Durumu ve Hareketleri": (
        "Malzemelerin eldeki miktarı ve giriş-çıkışları.",
        ["Alış faturası stoğa kendiliğinden girer; siparişe malzeme çıkışı 'Malzeme çıkışı' ile yapılır.",
         "Sayım farkı için '＋ Stok girişi' / '－ Stok çıkışı'."],
        ["Yıl sonunda fiili sayım yapılmalıdır."], "yil_sonu"),
    "Parça Başı Ücret": (
        "Biten işlerin işçiliğinin çalışan personel ve öğrencilere katkı payına göre dağıtılması.",
        ["'＋ Yeni bordro' → 'Siparişteki görevlileri getir' → katkı payları → 'Kaydet' → onay.",
         "Onaydan sonra 'Bordro PDF', 'Banka listesi (Excel)', 'Ödeme kaydı oluştur'."],
        ["Geçici kabulü yapılmamış işe bordro yapılmaz.", "Öğrenci hakkı en az %30'dur."], "parca_basi"),
    "Fazla Çalışma Ücreti": (
        "Ders ve mesai dışında yapılan döner sermaye çalışmasının saat ücretiyle ödenmesi.",
        ["'＋ Kayıt ekle' → 'Günlük puantaj…' ile günleri girin → onay.", "Ödeme için 'Banka listesi (Excel)' ve 'Ödeme kaydı oluştur'."],
        ["Öğretim günü en çok 3, tatil günü en çok 8 saat; Pazar ve bayramda yazılmaz.",
         "Fiilen çalışılmayan saat için ödenen ücret bir katı fazlasıyla geri alınır."], "fazla_calisma"),
    "Yıl Sonu Kârı ve ÜTP": (
        "Yıl sonu kârının ÜTP, sermaye ve Merkez Saymanlık paylarına bölünmesi ve ÜTP'nin kişilere dağıtılması.",
        ["'Yardımcı defterden al' → 'Personeli yükle' → 'Saat verilerini getir' → 'Hesapla' → 'Kaydet (taslak)' → onay."],
        ["Kişi başı ÜTP yıllık asgari ücret toplamını geçemez.", "30 günden fazla okul dışında görevlendirilen ÜTP alamaz."],
        "yil_sonu"),
    "Hazine Payı / SHÇEK": (
        "Her ay tahsil edilen hasılatın %1'i hazine payı ve yıllık hasılatın %1'i SHÇEK payı.",
        ["Her ay: 'Seçili ayı hesapla / güncelle' → 'Bildirim (Örnek 30) PDF' → 'Bildirildi olarak işaretle' → "
         "'Ödeme kaydı oluştur'."],
        ["Son gün izleyen ayın 20'sidir; tahsilat olmasa da bildirim verilir.", "Gecikme zammı müdür ve saymandan alınır."],
        "ay_sonu"),
    "KDV / Muhtasar Özeti": (
        "Aylık KDV ve muhtasar beyannamelerine esas tutarlar.",
        ["Ayı seçip 'Seçili ayın muhtasar detayı' ile kesintileri görün; beyannameyi bu tutarlarla verin."],
        ["Muhtasar son günü 26, KDV son günü 28'idir."], "ay_sonu"),
    "Yevmiye / Mizan": (
        "İşlemlerden kendiliğinden oluşan muhasebe kayıtları (yardımcı kayıt) ve mizan.",
        ["Normalde elle kayıt gerekmez.", "'Muhasebe işlem fişi PDF' ödeme belgelerine eklenir."],
        ["Resmi muhasebe BKMYBS'de tutulur; buradaki kayıtlar kontrol amaçlıdır."], "denetim"),
    "Raporlar": (
        "Dönemsel raporlar: üç aylık faaliyet raporu, idari masraf karşılığı, cari ve sipariş raporları.",
        ["Raporu seçin; 'Excel'e Aktar' veya 'PDF'."], ["Üç aylık faaliyet raporu dönemi izleyen ayın 5'ine kadar gönderilir."],
        "ay_sonu"),
    "Resmi Yazılar / Belgeler": (
        "Resmi yazılar, veli muvafakatnameleri ve personel/öğrenci listeleri.",
        ["Öğrencileri seçip 'Veli muvafakatnamesi (seçili öğrenciler)'.", "'Muvafakati eksik öğrencileri seç' eksikleri bulur."],
        [], "ogrenci"),
    "Kullanıcılar": (
        "Programa giriş yapan kullanıcılar, rolleri ve onay akışı.",
        ["Her görevliye kendi rolünde ayrı kullanıcı açın.", "'Rol / yetki tablosu' kimin neyi yapabileceğini gösterir."],
        ["Ortak kullanıcı açmayın.", "Onay akışı kapalıyken belgeler tek kişi tarafından onaylanabilir."], "ilk_kurulum"),
    "Yedekleme / İşlem Kaydı": (
        "Verilerin yedeklenmesi ve kimin ne zaman ne yaptığının kaydı.",
        ["'Şimdi yedekle' ile yedek alın; 'Farklı konuma yedekle' ile harici diske de kopyalayın."],
        ["Bilgisayar arızasında yedeği olmayan veriler geri gelmez."], "ilk_kurulum"),
}

# ---------------------------------------------------------------- sözlük
SOZLUK: list[tuple[str, str]] = [
    ("Döner sermaye (DÖSE)", "Okulun atölyelerinde öğrencilerle birlikte mal üretip hizmet satarak gelir elde eden, kendi bütçesi, "
     "vergi numarası ve banka hesabı olan işletme."),
    ("Harcama yetkilisi", "Harcama talimatı veren ve ödemeyi onaylayan kişi: okul müdürü."),
    ("Gerçekleştirme görevlisi", "İşin yapılmasını, belgelerin hazırlanmasını ve kontrolünü sağlayan kişi: teknik müdür yardımcısı."),
    ("Sayman", "Döner sermayenin muhasebe yetkilisi; parayı, kayıtları ve vergileri yönetir, Sayıştay'a hesap verir."),
    ("Cari hesap", "Alışveriş yaptığınız kişi veya kurumun hesabı. Müşteri (alıcı) veya tedarikçi (satıcı) olabilir."),
    ("Sipariş / iş emri", "Bir müşterinin okula yaptırdığı işin kaydı."),
    ("Proforma fatura", "Fiyat ve iş kapsamı teklifi. Vergi faturası (e-Fatura/e-Arşiv) değildir; kabul ve sözleşme sonrası "
     "asıl fatura kesilir."),
    ("Keşif / iş planı", "Yerinde inceleme sonucu ihtiyaç duyulan kontrol, bakım ve onarım adımlarının listesi."),
    ("Sözleşme bedeli", "İşin KDV hariç toplam fiyatı."),
    ("Ücret esası", "Çalışanlara ödemenin nasıl yapılacağı: parça başı ücret veya fazla çalışma ücreti. İş başında seçilir, değişmez."),
    ("Faaliyet gideri", "Sipariş bedelinden işletmenin genel masrafları (elektrik, bakım, kırtasiye vb.) için ayrılan pay."),
    ("İşçilik", "Sipariş bedelinden çalışanların ücreti için ayrılan pay."),
    ("Öğrenci hakkı", "İşçiliğin en az %30'u; işte çalışan öğrencilere ödenir."),
    ("Parça başı ücret", "Biten işin işçiliğinin, işte çalışanlara katkı paylarına göre bölünerek ödenmesi."),
    ("Fazla çalışma ücreti", "Ders ve mesai saatleri dışında yapılan döner sermaye çalışmasına saat başına ödenen ücret."),
    ("Puantaj (mesai çizelgesi)", "Kimin hangi gün kaç saat çalıştığını gösteren çizelge."),
    ("Tavan", "Bir kişiye bir ayda ödenebilecek en yüksek tutar (asgari ücretin katı olarak)."),
    ("Geçici muayene ve kabul", "Bitirilen işin okul komisyonunca kontrol edilip uygun bulunması. Parça başı ücret bundan sonra ödenir."),
    ("Veli muvafakatnamesi", "Velinin, öğrencinin döner sermaye işinde çalışmasına izin verdiğini gösteren imzalı belge."),
    ("Fiyat tespit komisyonu", "Ürün ve hizmetlerin satış fiyatını maliyet ve piyasa araştırmasına göre belirleyen komisyon."),
    ("KDV", "Katma değer vergisi. Satışta müşteriden alınır (hesaplanan KDV), alışta firmaya ödenir (indirilecek KDV); "
     "aradaki fark her ay devlete ödenir."),
    ("Matrah", "Verginin hesaplandığı tutar. Faturada KDV hariç tutar."),
    ("KDV tevkifatı", "Bazı satışlarda KDV'nin bir kısmını satıcı yerine alıcının doğrudan devlete ödemesi."),
    ("Stopaj (kesinti)", "Ödeme yapılırken karşı tarafın vergisinin ödemeyi yapan tarafından kesilip devlete yatırılması."),
    ("Müstahsil makbuzu", "Vergiden muaf çiftçiden ürün alırken düzenlenen belge; üzerinden stopaj kesilir."),
    ("Serbest meslek makbuzu", "Avukat, mühendis gibi serbest meslek sahiplerinin düzenlediği belge; %20 stopaj kesilir."),
    ("Gider pusulası", "Vergi mükellefi olmayan kişiden yapılan alım veya hizmet için düzenlenen belge."),
    ("Muhtasar beyanname", "Kesilen gelir vergisi, damga vergisi ve stopajların her ay devlete bildirildiği beyanname (son gün 26)."),
    ("Kümülatif matrah", "Kişinin yıl başından beri vergiye tabi kazancının toplamı; gelir vergisi dilimi buna göre belirlenir."),
    ("Damga vergisi", "Ücret ödemelerinden binde 7,59 oranında kesilen vergi."),
    ("Hazine payı", "Her ay tahsil edilen hasılatın %1'inin izleyen ayın 20'sine kadar devlete ödenmesi."),
    ("SHÇEK payı", "Yıllık brüt hasılatın %1'i; ertesi yılın Ocak sonuna kadar yatırılır."),
    ("Hasılat", "Satışlardan ve diğer gelirlerden elde edilen tutar (KDV hariç)."),
    ("ÜTP (Üretimi Teşvik Primi)", "Yıl sonu kârının en çok 1/3'ünün çalışanlara prim olarak dağıtılması."),
    ("Takdir payı", "ÜTP'nin %5'i; komisyon kararıyla özel gayret gösterenlere verilir."),
    ("Tahsis edilen sermaye", "İşletmeye ayrılan sermaye tutarı. Kârın bir kısmı buna ulaşıncaya kadar sermayeye eklenir."),
    ("Doğrudan temin", "Belirli bir tutarın altındaki alımların ihale yapılmadan, piyasa araştırmasıyla yapılması."),
    ("Yaklaşık maliyet", "Alımdan önce piyasa araştırmasıyla belirlenen tahmini tutar."),
    ("Peşinat / avans", "İşe başlamadan önce müşteriden alınan para; fatura kesilince faturadan düşülür."),
    ("e-Fatura / e-Arşiv", "Elektronik fatura. Alıcı e-fatura kullanıyorsa e-Fatura, kullanmıyorsa e-Arşiv düzenlenir."),
    ("Bordro", "Kişilere yapılacak ödemelerin brüt tutarını, kesintilerini ve net tutarını gösteren liste."),
    ("Yevmiye", "Muhasebe kayıtlarının tarih sırasıyla tutulduğu defter."),
    ("Mizan", "Bütün muhasebe hesaplarının borç, alacak ve bakiyelerini gösteren kontrol tablosu."),
    ("Muhasebe işlem fişi", "Her ödeme veya tahsilatın muhasebe kaydını gösteren, eklerle birlikte imzalanan belge."),
    ("BKMYBS", "Bakanlığın resmi döner sermaye muhasebe sistemi; resmi kayıtlar burada tutulur."),
    ("Kamu zararı", "Mevzuata aykırı bir işlem nedeniyle kamunun parasının azalması. Sorumlulardan kanuni faiziyle geri alınır."),
]

# ---------------------------------------------------------------- sık yapılan hatalar ve sonuçları
# (hata, sonucu, programın önlemi, dayanak)
CEZA_RISKLERI: list[tuple[str, str, str, str]] = [
    ("Hazine payının 20'sine kadar bildirilmemesi veya ödenmemesi",
     "Aylık %1 gecikme zammı; harcama yetkilisi ve saymandan yarı yarıya alınır.",
     "Her ay hesaplar, Örnek 30 bildirimini hazırlar, süre yaklaşınca ve geçince uyarır.",
     "Muhasebat Genel Tebliği (Sıra No: 73) md.6-7"),
    ("KDV veya muhtasar beyannamesinin geç verilmesi",
     "Usulsüzlük cezası ve geç ödenen vergi için gecikme zammı.",
     "KDV / Muhtasar özetini hazırlar, son günleri 'Bugün Ne Yapmalıyım?' sayfasında hatırlatır.",
     "VUK md.352; 6183 s.K. md.51"),
    ("Verginin eksik hesaplanması veya beyan edilmemesi (stopaj, gelir ve damga vergisi)",
     "Vergi ziyaı cezası ve gecikme faizi.",
     "Gelir vergisi, damga vergisi ve stopajı kendisi hesaplar; müstahsil makbuzunda stopaj seçilmeden kaydetmez.",
     "VUK md.344; GVK md.94"),
    ("Faturanın hiç ya da geç düzenlenmesi",
     "Özel usulsüzlük cezası.",
     "Geçici kabulü yapıldığı hâlde 7 günde faturalanmamış siparişleri uyum denetiminde gösterir.",
     "VUK md.231/5, md.353"),
    ("Fiilen çalışılmayan saat için fazla çalışma ücreti ödenmesi",
     "Ödenen tutar bir katı fazlasıyla geri alınır; yarısı çizelgeyi onaylayandan tahsil edilir.",
     "Günlük puantajı gün gün denetler, 3/8 saat ve Pazar/bayram yasağına uymayan kaydı engeller.",
     "Bütçe Kanunu K cetveli III-3, III-4"),
    ("Ücret tavanlarının, işçilik tutarının veya ÜTP tavanının aşılması",
     "Fazla ödeme kamu zararıdır; kanuni faiziyle birlikte sorumlulardan geri alınır.",
     "Tavanları ve sipariş işçiliğini otomatik uygular, aşan kaydı onaya göndermez.",
     "DÖSE Yönetmeliği md.4/1, md.8; 5018 s.K. md.71"),
    ("Veli muvafakatnamesi olmayan öğrencinin çalıştırılması",
     "Ödeme mevzuata aykırı olur; iş kazasında idari ve cezai sorumluluk doğar.",
     "Muvafakatsiz öğrencili bordroyu onaylatmaz, siparişte ⚠ ile gösterir.",
     "DÖSE Yönetmeliği md.8/1"),
    ("Sözleşme yapılmadan veya onay alınmadan işe başlanması",
     "Disiplin sorumluluğu; bu işten yapılan ödemeler sorgulanır.",
     "Onay akışı ve uyum denetimi, onaylanmadan üretime geçen siparişi gösterir.",
     "Çalışma Yönergesi md.26/d; DÖSE Yönetmeliği md.9/4"),
    ("İhtiyacın bölünerek doğrudan temin yapılması veya limitin aşılması",
     "Kamu zararı ve disiplin sorumluluğu.",
     "Tek belgede limit aşımını engeller, aynı gider türünde yıllık toplam limiti aşınca uyarır.",
     "4734 s.K. md.22/d"),
    ("Belgesiz harcama, perakende fişteki KDV'nin indirilmesi",
     "Harcama kabul edilmez; indirilen KDV için vergi ziyaı cezası.",
     "Belge türünü denetler, perakende fişte KDV girilmesini engeller.",
     "VUK md.228-238; KDV K. md.34; Çalışma Yönergesi md.46"),
    ("Komisyon fiyatının altında satış veya müşteri lehine indirim",
     "Aradaki fark kamu zararı olarak sorumlulardan istenir.",
     "Tespit edilen fiyatın altında satışta kayıttan önce açıkça onay ister.",
     "Çalışma Yönergesi md.26/g, md.29/a"),
    ("SHÇEK payının Ocak sonuna, Merkez Saymanlık payının Şubat sonuna kadar yatırılmaması",
     "Denetimde tespit edilir ve sorumlulardan istenir.",
     "Yıl sonunda tutarları hesaplar, ödeme kaydı yoksa uyarır.",
     "2828 s.K. md.18/1-k; DHGM 15.01.2026 yazısı m.9"),
    ("Fazla çalışma ve öğrenci ücretlerinin izleyen ayın 10'unu geçmesi",
     "Yönerge ihlali; hak sahiplerinin mağduriyeti.",
     "Ödenmemiş bordroları süre geçince kırmızı uyarıyla gösterir.",
     "Çalışma Yönergesi md.9/b, md.42/c"),
    ("Kasa/banka noksanı, kişisel hesap kullanımı",
     "Sayman ve harcama yetkilisinin şahsi sorumluluğu; zimmet soruşturması.",
     "Kasanın eksiye düştüğü günleri uyum denetiminde gösterir.",
     "5018 s.K. md.71; TCK md.247"),
    ("Banka şifrelerinin veya harcama yetkilisi ile sayman görevlerinin tek kişide toplanması",
     "Görevler ayrılığı ilkesine aykırılık; ortaya çıkacak zarardan şahsi sorumluluk.",
     "Kurum bilgilerinde aynı kişi yazılmışsa ve onay akışı kapalıysa uyarır.",
     "DHGM 15.01.2026 yazısı m.15"),
]

GENEL_UYARI = ("Bu kılavuz uygulamayı kolaylaştırmak için hazırlanmış sade bir özettir. Oran, tutar ve süreler her yıl "
               "değişebilir; tereddüt hâlinde yürürlükteki mevzuat, Bakanlık yazıları ve saymanınızın görüşü esastır.")


# ---------------------------------------------------------------- somut yasal takvim
@dataclass(order=True)
class Sure:
    tarih: date
    ad: str = field(compare=False)
    aciklama: str = field(compare=False, default="")
    sayfa: str | None = field(compare=False, default=None)
    rehber: str | None = field(compare=False, default=None)
    roller: tuple[str, ...] = field(compare=False, default=(M.ROL_SAYMAN, M.ROL_MUDUR))
    kod: str = field(compare=False, default="")
    donem: tuple[int, int] | None = field(compare=False, default=None)  # (yıl, ay); yıllık işlerde ay = 0


def _ay_kaydir(yil: int, ay: int, fark: int) -> tuple[int, int]:
    t = yil * 12 + (ay - 1) + fark
    return t // 12, t % 12 + 1


def yaklasan_sureler(bugun: date | None = None, gun: int = 40) -> list[Sure]:
    """Bugünden itibaren 'gun' gün içindeki yasal son tarihler (tarih sırasıyla)."""
    bugun = bugun or date.today()
    bitis = bugun + timedelta(days=gun)
    sonuc: list[Sure] = []
    for fark in (-1, 0, 1, 2):
        y, a = _ay_kaydir(bugun.year, bugun.month, fark)
        oy, oa = _ay_kaydir(y, a, -1)
        donem = f"{M.AYLAR[oa - 1]} {oy}"
        son = calendar.monthrange(y, a)[1]
        sonuc += [
            Sure(date(y, a, 10), "Fazla çalışma ve öğrenci ücretlerinin ödenmesi", f"{donem} dönemi",
                 "Fazla Çalışma Ücreti", "fazla_calisma", (M.ROL_SAYMAN, M.ROL_MUDUR, M.ROL_TMY, M.ROL_SEF), "ucret", (oy, oa)),
            Sure(date(y, a, 20), "Hazine payı bildirimi ve ödemesi", f"{donem} tahsilatlarının %1'i",
                 "Hazine Payı / SHÇEK", "ay_sonu", kod="hazine", donem=(oy, oa)),
            Sure(date(y, a, min(26, son)), "Muhtasar beyannamesi ve ödemesi", f"{donem} kesintileri",
                 "KDV / Muhtasar Özeti", "ay_sonu", kod="muhtasar", donem=(oy, oa)),
            Sure(date(y, a, min(28, son)), "KDV beyannamesi ve ödemesi", f"{donem} dönemi",
                 "KDV / Muhtasar Özeti", "ay_sonu", kod="kdv", donem=(oy, oa)),
        ]
        if a in (1, 4, 7, 10):
            sonuc.append(Sure(date(y, a, 5), "Üç aylık faaliyet raporunun gönderilmesi", "Önceki üç aylık dönem",
                              "Raporlar", "ay_sonu", (M.ROL_SAYMAN, M.ROL_MUDUR, M.ROL_TMY), "rapor", (oy, oa)))
        if a == 1:
            sonuc.append(Sure(date(y, 1, 31), "SHÇEK payının yatırılması", f"{y - 1} yılı brüt hasılatının %1'i",
                              "Hazine Payı / SHÇEK", "yil_sonu", kod="shcek", donem=(y - 1, 0)))
            sonuc.append(Sure(date(y, 1, 15), "Yeni yıl mevzuat parametrelerinin girilmesi",
                              "Asgari ücret, vergi tarifesi, fazla çalışma ücreti, tatil günleri", "Mevzuat Parametreleri",
                              "yil_sonu", (M.ROL_SAYMAN, M.ROL_SISTEM), "parametre", (y, 0)))
        if a == 2:
            sonuc.append(Sure(date(y, 2, calendar.monthrange(y, 2)[1]), "Merkez Saymanlık kâr payının yatırılması",
                              f"{y - 1} yılı kârından", "Hazine Payı / SHÇEK", "yil_sonu", kod="merkez", donem=(y - 1, 0)))
        if a == 3:
            sonuc.append(Sure(date(y, 3, 31), "Kâr ve SHÇEK dekontlarının MEBBİS'e yüklenmesi", "Döner Sermaye Takip Modülü",
                              None, "yil_sonu", kod="mebbis", donem=(y - 1, 0)))
    return sorted(s for s in sonuc if bugun <= s.tarih <= bitis)
