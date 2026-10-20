"""Mevzuat sabitleri, yıllık parametre varsayılanları, seçim listeleri ve hesap planı.

Dayanaklar:
- 3423 sayılı MEB'e Bağlı Meslekî ve Teknik Öğretim Okulları Döner Sermayesi Hakkında Kanun
- MEB Döner Sermaye İşletmelerinde Üretimi Teşvik Primi Dağıtımı, Parça Başı Üretim,
  Atölye ve Tesislerin Özel Sektörle İşbirliği Yapılarak İşletilmesi Hakkında Yönetmelik
- Muhasebat Genel Müdürlüğü Genel Tebliği (Sıra No: 73) (Döner Sermaye İşlemleri)
- Döner Sermayeli İşletmeler Bütçe ve Muhasebe Yönetmeliği (D.S.İ.B.M.Y.)
- 2828 sayılı Sosyal Hizmetler Kanunu md. 18/1-k
- 193 sayılı GVK md. 94, 103; 488 sayılı Damga Vergisi Kanunu
- 4734 sayılı Kamu İhale Kanunu md. 3/e, 22/d; Döner Sermayeli Kuruluşlar İhale Yönetmeliği
- MEB Destek Hizmetleri Genel Müdürlüğü 15.01.2026 tarihli DÖSE yazısı
"""
import json

# ---------------------------------------------------------------- seçim listeleri
HIZMET_SINIFLARI = [
    "Eğitim ve Öğretim Hizmetleri",
    "Teknik Hizmetler",
    "Genel İdare Hizmetleri",
    "Yardımcı Hizmetler",
    "Diğer (4857 İşçi vb.)",
]

DOSE_GOREVLERI = [
    "Harcama Yetkilisi (Okul Müdürü)",
    "Gerçekleştirme Görevlisi (Teknik Md. Yrd.)",
    "Bölüm/Alan Şefi",
    "Atölye/Laboratuvar Şefi",
    "Sayman",
    "Diğer İdari Personel",
    "Öğretmen",
    "Mühendis/Uzman/Tekniker",
    "Usta/Teknisyen/Ambar Memuru",
    "Diğer Personel",
]

# Yönetmelik md.5/8-c unvan puanları
UNVAN_GRUPLARI = {
    1: "Harcama yetkilisi (50 puan)",
    2: "Müdür yrd., bölüm/alan, atölye, laboratuvar, kısım şefi (45 puan)",
    3: "Öğretmen, mühendis, mimar, sayman, uzman, tekniker (40 puan)",
    4: "Büro şefi, teknisyen, ustabaşı, usta, ambar memuru vb. (35 puan)",
    5: "Diğer personel (30 puan)",
}

GOREV_VARSAYILAN_UNVAN_GRUBU = {
    "Harcama Yetkilisi (Okul Müdürü)": 1,
    "Gerçekleştirme Görevlisi (Teknik Md. Yrd.)": 2,
    "Bölüm/Alan Şefi": 2,
    "Atölye/Laboratuvar Şefi": 2,
    "Sayman": 3,
    "Diğer İdari Personel": 5,
    "Öğretmen": 3,
    "Mühendis/Uzman/Tekniker": 3,
    "Usta/Teknisyen/Ambar Memuru": 4,
    "Diğer Personel": 5,
}

IDARI_GOREVLER = {
    "Harcama Yetkilisi (Okul Müdürü)",
    "Gerçekleştirme Görevlisi (Teknik Md. Yrd.)",
    "Bölüm/Alan Şefi",
    "Atölye/Laboratuvar Şefi",
    "Sayman",
    "Diğer İdari Personel",
}
SEF_GOREVLERI = {"Bölüm/Alan Şefi", "Atölye/Laboratuvar Şefi"}

UCRET_ESASLARI = [
    "Parça Başı Ücret (Yön. md.8)",
    "Fazla Çalışma Ücreti",
    "Özel Sektör İşbirliği (Yön. md.9-11)",
    "Tesis İşletmesi (Yön. md.12)",
]

SIPARIS_DURUMLARI = [
    "Talep Alındı",          # Resmi yazı / müşteri talebi kayda alındı
    "Keşif / İş Planı",     # Yerinde inceleme, bakım-onarım kalemleri belirlendi
    "Teklif",               # Maliyet hesabı ve proforma / fiyat teklifi hazır
    "Proforma İletildi",    # Proforma muhataba gönderildi; kabul bekleniyor
    "Sözleşme İmzalandı",   # Kabul sonrası sözleşme (Yön. md.9/4 — imzasız işe başlanmaz)
    "Üretimde",
    "Tamamlandı (Geçici Kabul)",
    "Faturalandı",
    "Kapandı",
    "İptal",
]

# Onay tamamlanınca sözleşmeye geçebilecek ön aşamalar (proforma henüz vergi belgesi değildir)
SIPARIS_TEKLIF_ASAMALARI = ("Talep Alındı", "Keşif / İş Planı", "Teklif", "Proforma İletildi")

CARI_TURLERI = ["Müşteri", "Tedarikçi", "Çiftçi (Müstahsil)", "Müşteri ve Tedarikçi"]

URUN_TURLERI = ["Mal", "Hizmet"]

MALZEME_TURLERI = ["İlk Madde ve Malzeme", "Ticari Mal", "Mamul", "Yarı Mamul"]

BIRIMLER = ["Adet", "Kg", "Gram", "Litre", "Metre", "m²", "m³", "Paket", "Kutu", "Takım", "Saat", "Gün", "Ton", "Çuval", "Kalıp", "Cihaz", "Hizmet"]

MALIYET_KALEMLERI = [
    "Direkt İlk Madde ve Malzeme",
    "Direkt İşçilik (Personel)",
    "Öğrenci Hakkı",
    "Enerji (Elektrik/Gaz/Su)",
    "Amortisman / Bakım-Onarım",
    "Ambalaj / Etiket",
    "Genel Üretim Gideri",
    "Diğer",
]

SATIS_BELGE_TURLERI = ["e-Fatura", "e-Arşiv Fatura", "Kağıt Fatura", "Perakende Satış Fişi / ÖKC", "Diğer"]
ALIS_BELGE_TURLERI = ["e-Fatura", "e-Arşiv Fatura", "Kağıt Fatura", "Müstahsil Makbuzu (e-MM)",
                      "Serbest Meslek Makbuzu (e-SMM)", "Gider Pusulası", "Perakende Satış Fişi / ÖKC", "Diğer"]

TEMIN_USULLERI = [
    "Doğrudan Temin",
    "Pazarlık Usulü",
    "Belli İstekliler Arasında İhale",
    "Açık İhale",
    "4734 md.3/e Kapsamında Alım",
    "Diğer",
]

GIDER_TURLERI = {
    # ad: (hesap kodu, stoğa girer mi)
    "İlk Madde ve Malzeme (Stoğa)": ("150", True),
    "Ticari Mal (Stoğa)": ("153", True),
    "Doğrudan Üretim Gideri": ("740", False),
    "Enerji / Su / Yakıt": ("740", False),
    "Bakım-Onarım": ("740", False),
    "Hizmet Alımı": ("740", False),
    "Genel Yönetim Gideri": ("770", False),
    "Demirbaş / Makine-Teçhizat": ("255", False),
    "Diğer Gider": ("770", False),
}

STOPAJ_TURLERI = {
    "Yok": 0.0,
    "Zirai Ürün - Bitkisel (%2)": "stopaj_bitkisel",
    "Zirai Ürün - Hayvansal (%1)": "stopaj_hayvansal",
    "Zirai Hizmet (%2)": "stopaj_zirai_hizmet",
    "Serbest Meslek (%20)": "stopaj_serbest_meslek",
}

TEVKIFAT_ORANLARI = {
    "Yok": 0.0,
    "2/10": 0.2,
    "3/10": 0.3,
    "4/10": 0.4,
    "5/10": 0.5,
    "7/10": 0.7,
    "9/10": 0.9,
    "10/10": 1.0,
}

KASA_HESAPLARI = ["Kasa (100)", "Banka (102)"]
KASA_ISLEM_TURLERI = ["Tahsilat", "Ödeme", "Peşinat/Avans Tahsilatı", "Faiz/Diğer Gelir",
                      "Hazine Payı Ödemesi", "SHÇEK Payı Ödemesi", "Vergi Ödemesi",
                      "Personel Ödemesi", "Merkez Saymanlık Kâr Aktarımı", "Sermaye", "Diğer"]
HASILAT_ETKILI_TURLER = {"Tahsilat", "Peşinat/Avans Tahsilatı", "Faiz/Diğer Gelir"}

ROL_SISTEM = "Sistem Yöneticisi"
ROL_MUDUR = "Okul Müdürü"
ROL_TMY = "Teknik Müdür Yardımcısı"
ROL_SAYMAN = "Sayman"
ROL_SEF = "Alan Şefi"
ROL_OGRETMEN = "Öğretmen"
ROL_MEMUR = "Memur / Veri Girişi"
ROL_IZLEYICI = "İzleyici / Denetçi"
ROLLER = [ROL_SISTEM, ROL_MUDUR, ROL_TMY, ROL_SAYMAN, ROL_SEF, ROL_OGRETMEN, ROL_MEMUR, ROL_IZLEYICI]
ESKI_ROLLER = {"Yönetici": ROL_SISTEM, "Veri Girişi": ROL_MEMUR, "İzleyici": ROL_IZLEYICI}

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos",
         "Eylül", "Ekim", "Kasım", "Aralık"]

UTP_BOLUM_YONTEMLERI = [
    "Fazla çalışma saati ile orantılı (md.5/7-a)",
    "Fiilen çalışılan gün ile orantılı (md.5/7-b)",
    "Katkı oranına göre (md.5/7-c)",
]

# ---------------------------------------------------------------- yıllık parametreler
# (anahtar, etiket, tür, varsayılan, açıklama/dayanak)
PARAMETRELER = [
    ("asgari_ucret_brut", "Aylık brüt asgari ücret (TL)", "para", 33030.00, "2026: 33.030,00 TL (01.01-31.12.2026)"),
    ("asgari_ucret_yillik", "Yıllık en yüksek asgari ücret toplamı (TL)", "para", 396360.00, "ÜTP kişi başı yıllık tavanı (Yön. md.4/1). Yıl içinde değişirse toplamı giriniz."),
    ("asgari_ucret_gv_matrahi", "Asgari ücret GV matrahı (aylık)", "para", 28075.50, "Asgari ücret istisnası hesabı (GVK md.23/1-18)"),
    ("hazine_payi_orani", "Hazine payı oranı", "oran", 0.01, "Aylık gayrisafi hasılattan tahsil edilen tutarın %1'i; izleyen ayın 20'sine kadar (Tebliğ 73 md.6-7)"),
    ("shcek_orani", "SHÇEK (Sosyal Hizmetler) payı oranı", "oran", 0.01, "Yıllık brüt hasılatın %1'i; ertesi yıl Ocak sonuna kadar (2828 s.K. md.18/1-k)"),
    ("kdv_genel", "KDV genel oran", "oran", 0.20, "3065 s. KDV Kanunu"),
    ("kdv_indirimli_1", "KDV indirimli oran (1)", "oran", 0.10, ""),
    ("kdv_indirimli_2", "KDV indirimli oran (2)", "oran", 0.01, ""),
    ("damga_vergisi_orani", "Damga vergisi (ücret) oranı", "oran", 0.00759, "488 s. DVK (1) sayılı tablo IV-1-b: binde 7,59"),
    ("stopaj_bitkisel", "Müstahsil stopajı - bitkisel ürün", "oran", 0.02, "GVK md.94/11; 2009/14592 BKK"),
    ("stopaj_hayvansal", "Müstahsil stopajı - hayvansal ürün", "oran", 0.01, "GVK md.94/11"),
    ("stopaj_zirai_hizmet", "Zirai hizmet stopajı", "oran", 0.02, "GVK md.94/11"),
    ("stopaj_serbest_meslek", "Serbest meslek stopajı", "oran", 0.20, "GVK md.94/2-b"),
    ("gv_tarifesi_ucret", "Gelir vergisi tarifesi (ücret)", "metin",
     json.dumps([[190000, 0.15], [400000, 0.20], [1500000, 0.27], [5300000, 0.35], [None, 0.40]]),
     "GVK md.103 - 2026 ücret tarifesi: [üst sınır, oran] listesi (JSON)"),
    ("memurda_asgari_ucret_istisnasi", "Personele asgari ücret istisnası uygulansın mı? (1/0)", "sayi", 0,
     "İstisna, birden fazla işverende yalnızca bir kez uygulanır; genellikle maaş bordrosunda kullanılır → 0"),
    ("ogrencide_asgari_ucret_istisnasi", "Öğrenciye asgari ücret istisnası uygulansın mı? (1/0)", "sayi", 1,
     "GVK md.23/1-18 ve DVK: asgari ücrete isabet eden GV ve DV istisnası"),
    ("fazla_calisma_saat_ucreti", "Fazla çalışma saat ücreti (TL)", "para", 67.50,
     "Okul müdürünce azami tutarı geçmemek üzere belirlenir (2026 Bütçe K cetveli III-3; Yön. md.13/2 gün hesabında da kullanılır)"),
    ("fazla_calisma_azami_ucret", "Fazla çalışma saat ücreti azami tutarı (TL)", "para", 67.50,
     "2026 Merkezi Yönetim Bütçe Kanunu K cetveli III-3: beher iş saati için 67,50 TL'yi geçemez"),
    ("fc_ogretim_gunu_saat", "Fazla çalışma: öğretim günlerinde günlük azami saat", "sayi", 3,
     "2026 Bütçe K cetveli III-3 (Çalışma Yönergesi md.9: her yıl Bütçe Kanunu limitleri esas alınır)"),
    ("fc_tatil_gunu_saat", "Fazla çalışma: tatillerde günlük azami saat", "sayi", 8,
     "2026 Bütçe K cetveli III-3: resmi ve dini bayram günleri hariç tatillerde günde 8 saat"),
    ("fc_pazar_izinli", "Pazar günü fazla çalışma yapılabilir mi? (1/0)", "sayi", 0,
     "Çalışma Yönergesi md.9/a-12: Pazar günü fazla çalışma yapılmaz (otelcilik-turizm vb. istisna okullarda 1)"),
    ("fc_tatil_donemleri", "Tatil dönemleri (fazla çalışmada tatil sayılan günler)", "metin",
     json.dumps([["2026-01-01", "2026-01-01"], ["2026-01-19", "2026-01-30"], ["2026-03-16", "2026-03-20"],
                 ["2026-05-01", "2026-05-01"], ["2026-06-27", "2026-09-13"], ["2026-07-15", "2026-07-15"],
                 ["2026-11-16", "2026-11-20"], ["2027-01-01", "2027-01-01"], ["2027-01-25", "2027-02-05"],
                 ["2027-03-08", "2027-03-12"], ["2027-05-01", "2027-05-01"], ["2027-06-26", "2027-09-12"],
                 ["2027-07-15", "2027-07-15"]]),
     "[başlangıç, bitiş] listesi (JSON). Yarıyıl, ara tatiller, yaz tatili ve resmi tatiller; MEB çalışma takvimine göre "
     "güncelleyiniz. Cumartesi ve Pazar ayrıca tatil sayılır."),
    ("fc_bayram_gunleri", "Resmi ve dini bayram günleri (fazla çalışma yapılamaz)", "metin",
     json.dumps(["2026-03-20", "2026-03-21", "2026-03-22", "2026-04-23", "2026-05-19", "2026-05-27", "2026-05-28",
                 "2026-05-29", "2026-05-30", "2026-08-30", "2026-10-29", "2027-04-23", "2027-05-19", "2027-08-30",
                 "2027-10-29"]),
     "Tarih listesi (JSON). 2027 Ramazan ve Kurban Bayramı günlerini eklemeyi unutmayınız (K cetveli III-3)."),
    ("pb_tavan_egitim", "Parça başı aylık tavan - Eğitim Öğretim (x asgari ücret)", "sayi", 2.0, "Yön. md.8/5-a"),
    ("pb_tavan_teknik", "Parça başı aylık tavan - Teknik Hizmetler (x asgari ücret)", "sayi", 1.5, "Yön. md.8/5-b"),
    ("pb_tavan_diger", "Parça başı aylık tavan - Diğer sınıflar (x asgari ücret)", "sayi", 1.0, "Yön. md.8/5-c (saymanlar dahil, DHGM 15.01.2026 yazısı m.8)"),
    ("pb_tavan_ogrenci", "Parça başı aylık tavan - Öğrenci/kursiyer (x asgari ücret)", "sayi", 1.0, "Yön. md.8/6"),
    ("pb_kar_orani", "Parça başı: asgari kâr oranı", "oran", 0.05, "Yön. md.8/2"),
    ("pb_faaliyet_orani", "Parça başı: faaliyet gideri oranı", "oran", 0.25, "Yön. md.8/2"),
    ("ogrenci_hakki_orani", "Öğrenci hakkı asgari oranı (işçiliğin)", "oran", 0.30, "Yön. md.8/3, md.11/3"),
    ("malzeme_azami_orani", "İlk madde ve malzemenin sipariş bedeline azami oranı", "oran", 0.60,
     "Ön maliyet formu notu: ilk madde ve malzeme tutarı sipariş bedelinin %60'ını geçemez (0 = denetlenmez)"),
    ("os_kar_orani", "Özel sektör işbirliği: asgari kâr oranı", "oran", 0.10, "Yön. md.10/3"),
    ("os_faaliyet_orani", "Özel sektör işbirliği: faaliyet gideri oranı", "oran", 0.40, "Yön. md.10/3"),
    ("os_pesin_orani", "Özel sektör işbirliği: asgari peşinat oranı", "oran", 0.25, "Yön. md.10/2"),
    ("tesis_kar_orani", "Tesis işletmesi: asgari kâr oranı", "oran", 0.15, "Yön. md.12/1-d"),
    ("tesis_faaliyet_orani", "Tesis işletmesi: faaliyet gideri oranı", "oran", 0.55, "Yön. md.12/1-d"),
    ("tesis_pesin_orani", "Tesis işletmesi: asgari peşinat oranı", "oran", 0.25, "Yön. md.12/1-ç"),
    ("utp_azami_oran", "ÜTP olarak dağıtılabilecek azami kâr oranı", "oran", 1 / 3, "3423 s.K. md.1; Yön. md.4/1 (en çok 1/3)"),
    ("utp_idari", "ÜTP - idari personel payı", "oran", 0.25, "Yön. md.5/2"),
    ("utp_takdir", "ÜTP - çalışmayı teşvik ve takdir payı", "oran", 0.05, "Yön. md.5/2"),
    ("utp_bolum", "ÜTP - bölüm/alan personeli payı", "oran", 0.70, "Yön. md.5/2"),
    ("utp_harcama", "ÜTP idari: harcama yetkilisi", "oran", 0.08, "Yön. md.5/3-a"),
    ("utp_gerceklestirme", "ÜTP idari: gerçekleştirme görevlisi", "oran", 0.05, "Yön. md.5/3-b"),
    ("utp_sef", "ÜTP idari: bölüm/alan (atölye) şefleri", "oran", 0.05, "Yön. md.5/3-c"),
    ("utp_sayman", "ÜTP idari: sayman", "oran", 0.05, "Yön. md.5/3-ç"),
    ("utp_diger_idari", "ÜTP idari: diğer idari personel", "oran", 0.02, "Yön. md.5/3-d"),
    ("puan_1", "Unvan puanı - grup 1", "sayi", 50, "Yön. md.5/8-c"),
    ("puan_2", "Unvan puanı - grup 2", "sayi", 45, ""),
    ("puan_3", "Unvan puanı - grup 3", "sayi", 40, ""),
    ("puan_4", "Unvan puanı - grup 4", "sayi", 35, ""),
    ("puan_5", "Unvan puanı - grup 5", "sayi", 30, ""),
    ("dogrudan_temin_diger", "Doğrudan temin limiti - diğer idareler (TL, KDV hariç)", "para", 340391.0, "4734 md.22/d; 2026/1 KİK Tebliği (01.02.2026-31.01.2027)"),
    ("dogrudan_temin_buyuksehir", "Doğrudan temin limiti - büyükşehir (TL, KDV hariç)", "para", 1021827.0, "4734 md.22/d; 2026/1 KİK Tebliği"),
    ("ogrenci_sgk_orani", "Öğrenci iş kazası-meslek hastalığı prim oranı", "oran", 0.0,
     "5510 s.K. md.5/b uygulamasına göre ödenmesi gerekiyorsa oranı giriniz (0 = hesaplanmaz)"),
]

PARAMETRE_SOZLUK = {p[0]: p for p in PARAMETRELER}


def varsayilan_parametreler() -> dict:
    return {p[0]: p[3] for p in PARAMETRELER}


# ---------------------------------------------------------------- hesap planı (D.S.İ.B.M.Y. uyumlu temel hesaplar)
HESAP_PLANI = [
    ("100", "Kasa Hesabı"),
    ("102", "Banka Hesabı"),
    ("103", "Verilen Çekler ve Gönderme Emirleri Hesabı"),
    ("120", "Alıcılar Hesabı"),
    ("126", "Verilen Depozito ve Teminatlar Hesabı"),
    ("150", "İlk Madde ve Malzeme Hesabı"),
    ("151", "Yarı Mamuller Hesabı"),
    ("152", "Mamuller Hesabı"),
    ("153", "Ticari Mallar Hesabı"),
    ("159", "Verilen Sipariş Avansları Hesabı"),
    ("191", "İndirilecek KDV Hesabı"),
    ("255", "Demirbaşlar Hesabı"),
    ("320", "Satıcılar Hesabı"),
    ("335", "Personele Borçlar Hesabı"),
    ("340", "Alınan Sipariş Avansları Hesabı"),
    ("360", "Ödenecek Vergi ve Fonlar Hesabı"),
    ("361", "Ödenecek Sosyal Güvenlik Kesintileri Hesabı"),
    ("362", "Ödenecek Döner Sermaye Yükümlülükleri Hesabı"),
    ("391", "Hesaplanan KDV Hesabı"),
    ("500", "Sermaye Hesabı"),
    ("501", "Ödenmemiş Sermaye Hesabı (-)"),
    ("570", "Geçmiş Yıllar Kârları Hesabı"),
    ("590", "Dönem Net Kârı Hesabı"),
    ("591", "Dönem Net Zararı Hesabı (-)"),
    ("600", "Yurtiçi Satışlar Hesabı"),
    ("610", "Satıştan İadeler Hesabı (-)"),
    ("642", "Faiz Gelirleri Hesabı"),
    ("649", "Diğer Olağan Gelir ve Kârlar Hesabı"),
    ("710", "Direkt İlk Madde ve Malzeme Giderleri Hesabı"),
    ("720", "Direkt İşçilik Giderleri Hesabı"),
    ("730", "Genel Üretim Giderleri Hesabı"),
    ("740", "Hizmet Üretim Maliyeti Hesabı"),
    ("770", "Genel Yönetim Giderleri Hesabı"),
    ("780", "Finansman Giderleri Hesabı"),
]
GELIR_HESAPLARI = ("600", "642", "649")
GIDER_HESAPLARI = ("610", "710", "720", "730", "740", "770", "780")

# ---------------------------------------------------------------- yasal takvim
YASAL_TAKVIM = [
    ("Her ay 10'u", "Önceki ayın fazla çalışma ücretleri ile öğrenci ücretlerinin ödenmesi (Çalışma Yönergesi md.9/b, md.42/c)"),
    ("5 Nisan / 5 Temmuz / 5 Ekim / 5 Ocak", "Üç aylık faaliyet raporunun gönderilmesi (Çalışma Yönergesi md.48)"),
    ("Her ay 20'si", "Hazine payı bildirimi ve ödemesi (Örnek No:30) - önceki ayın tahsil edilen hasılatının %1'i"),
    ("Her ay 26'sı", "Muhtasar ve Prim Hizmet Beyannamesi (stopaj, gelir vergisi, damga vergisi)"),
    ("Her ay 28'i", "KDV beyannamesi ve ödemesi"),
    ("Ocak sonu", "SHÇEK payı (önceki yılın yıllık brüt hasılatının %1'i) - 2828 s.K. md.18"),
    ("Şubat sonu", "Yıl sonu kârından MEB Merkez Saymanlık payının yatırılması"),
    ("Mart sonu", "Kâr ve SHÇEK dekontlarının MEBBİS Döner Sermaye Takip Modülüne yüklenmesi"),
    ("Bilanço + 2 ay", "Üretimi teşvik priminin hak sahiplerine ödenmesi (Yön. md.4/2)"),
    ("Ocak-Şubat", "Tesislerin özel sektörle işletilmesine ilişkin kamuoyu duyurusu (Yön. md.12/1-b)"),
]

MERKEZ_SAYMANLIK = {
    "ad": "Millî Eğitim Bakanlığı Merkez Saymanlık Müdürlüğü",
    "vkn": "6210312482",
    "iban": "TR02 0000 1001 0000 0350 1540 35",
}

# ---------------------------------------------------------------- mevzuat rehberi metni (HTML)
MEVZUAT_REHBERI_HTML = """
<h2>DÖSE İşlemleri Mevzuat Rehberi</h2>
<p><i>Bu özet uygulamadaki hesaplamaların dayanağını gösterir. Oran ve tutarlar "Mevzuat Parametreleri"
ekranından yıllık olarak güncellenebilir. Tereddüt hâlinde yürürlükteki mevzuat metni ve Bakanlık yazıları esastır.</i></p>

<h3>1. Kuruluş ve Görevliler</h3>
<ul>
<li><b>3423 sayılı Kanun</b>: Meslekî ve teknik öğretim okullarında döner sermaye işletmesi.</li>
<li><b>Harcama yetkilisi</b>: Okul/kurum müdürü. <b>Gerçekleştirme görevlisi</b>: Teknik müdür yardımcısı.
<b>Sayman</b>: Mali ve muhasebe işlemlerini yürüten, Sayıştay'a hesap veren kişi (Yön. md.3).</li>
<li>İnternet bankacılığında tek kullanımlık şifre harcama yetkilisinde, interaktif şifre saymanda bulunur; iki şifre tek kişide olamaz (DHGM 15.01.2026, m.15).</li>
</ul>

<h3>2. Sipariş Kabulü</h3>
<ul>
<li>Öğrenci/kursiyerin uygulamaya alınmadığı hiçbir iş kabul edilmez (DHGM 15.01.2026, m.1).</li>
<li>Kamu kurumları 4734 md.3/e kapsamında ihalesiz alım yapabilir; ancak işin <b>bizzat üretilmesi</b> şarttır.</li>
<li>Siparişe hangi ücret esasıyla (parça başı / fazla çalışma) başlandıysa aynı esasla bitirilir (Yön. md.7/3).</li>
<li>Her iş için sözleşme yapılır, sözleşme imzalanmadan işe başlanmaz (Yön. md.9/4).</li>
<li>İlçe MEM / okul vb. resmi talep yazılarında tipik sıra: <b>talep kaydı → keşif / iş planı → maliyet → proforma
iletimi → kabul → sözleşme → üretim → e-Fatura</b>. Proforma fatura VUK ve e-Belge bakımından vergi belgesi değildir;
yalnızca teklif niteliğindedir. Asıl fatura teslim / kabul sonrası kesilir.</li>
</ul>

<h3>3. Parça Başı Üretim (Yön. md.8)</h3>
<ul>
<li>Sipariş bedelinin en az <b>%5'i kâr</b>, <b>%25'i faaliyet gideri</b> olarak ayrılır.</li>
<li>Personele ayrılan işçiliğin en az <b>%30'u öğrenci hakkı</b>dır.</li>
<li>Aylık tavanlar: Eğitim-öğretim hizmetleri sınıfı <b>2 asgari ücret</b>; teknik hizmetler <b>1,5</b>; diğer sınıflar (sayman dahil) <b>1</b>; öğrenci/kursiyer yaşına uygun <b>1 asgari ücret</b>.</li>
<li>Aynı iş için parça başı ve fazla çalışma ücreti birlikte ödenmez; idari personele aynı ayda ikisi birden ödenmez (md.8/7).</li>
<li>Öğrencinin çalışabilmesi için <b>velinin yazılı muvafakati</b> gerekir (md.8/1).</li>
<li>Aylık işçilik; ay içinde bitirilen ve geçici kabulü yapılan işler üzerinden, katkı oranında şef tarafından belirlenir, harcama yetkilisince onaylanır (md.8/8).</li>
</ul>

<h3>4. Özel Sektörle İşbirliği ve Tesisler (Yön. md.9-12)</h3>
<ul>
<li>Kira şeklinde olamaz. 12 ayı veya eşik değerin 2 katını aşan sözleşmelerde Bakanlık izni; 36 aydan uzun sözleşme yapılamaz.</li>
<li>Atölye/makine parkı: en az <b>%25 peşin</b>; bedelin en az <b>%10'u kâr, %40'ı faaliyet gideri</b>.</li>
<li>Tesisler: en az %25 peşin; en az <b>%15 kâr, %55 faaliyet gideri</b>.</li>
</ul>

<h3>5. Hazine Payı ve SHÇEK Payı</h3>
<ul>
<li>Aylık gayrisafi hasılattan <b>tahsil edilen</b> tutarın <b>%1'i</b> (MEB mesleki okullar için indirilmiş oran) izleyen ayın <b>20'sine</b> kadar Örnek No:30 ile bildirilir ve ödenir. Tahsilat olmasa da bildirim verilir. Gecikmede aylık %1 zam, harcama yetkilisi ve saymandan yarı yarıya alınır.</li>
<li>Kayıt: 770 Genel Yönetim Giderleri (B) / 362 Ödenecek Döner Sermaye Yükümlülükleri (A).</li>
<li>SHÇEK payı: yıllık brüt hasılatın <b>%1'i</b>, Aralık sonunda hesaplanır, en geç <b>Ocak sonuna</b> kadar yatırılır (2828 s.K. md.18/1-k).</li>
</ul>

<h3>6. Yıl Sonu Kârı ve Üretimi Teşvik Primi (ÜTP)</h3>
<ul>
<li>Kârın <b>1/3'ü ÜTP</b>, <b>1/3'ü</b> tahsis edilen sermayeye ulaşıncaya kadar <b>sermayeye</b>, <b>1/3'ü MEB Merkez Saymanlık</b> hesabına; sermayesi tamamlanan işletmelerde 2/3 Merkez Saymanlığa (DHGM 15.01.2026, m.9). Merkez Saymanlık payı Şubat sonuna kadar yatırılır.</li>
<li>Dağıtıma esas kârın %25'i idari personel (harcama yetkilisi %8, gerçekleştirme görevlisi %5, bölüm/alan şefleri %5, sayman %5, diğer idari %2), %5'i takdir payı, %70'i bölüm/alan personeli (Yön. md.5).</li>
<li>Bölüm payı, bölümlerin gelirinin işletme toplam gelirine oranına göre ayrılır; bölüm içinde fazla çalışma saati / çalışılan gün / katkı oranına göre dağıtılır. İdari pay alan harcama yetkilisi, gerçekleştirme görevlisi, sayman ve diğer idari personel bölüm payına dahil edilmez; bölüm/atölye şefleri bölüm personeli olarak dahildir.</li>
<li>Öğrenci ile yüz yüze eğitim yapmayan işletmelerde %5 takdir + %95 unvan puanı × fiilen çalışılan gün usulü uygulanır (md.5/8).</li>
<li>Kişi başı yıllık ÜTP, o yılın <b>en yüksek asgari ücretinin yıllık tutarını</b> geçemez (md.4/1). ÜTP bilanço tarihini izleyen 2 ay içinde ödenir.</li>
<li>Yıl içinde 30 günden fazla okul dışında görevlendirilenler ve döner sermaye çalışmalarına fiilen katılmayanlar ÜTP alamaz (md.6).</li>
<li>Takdir payı komisyonu: harcama yetkilisi, gerçekleştirme görevlisi ve ilgili şefler; üyeler bu paydan yararlanamaz, karar gerekçeli yazılır.</li>
</ul>

<h3>7. Vergiler</h3>
<ul>
<li>KDV: Satışlarda hesaplanan KDV, alışlarda indirilecek KDV; beyan izleyen ayın 28'i.</li>
<li>Muhtasar: çiftçiden alımlarda müstahsil stopajı (bitkisel %2, hayvansal %1), serbest meslek %20, personel ödemelerinde gelir vergisi ve damga vergisi (binde 7,59); beyan izleyen ayın 26'sı.</li>
<li>Asgari ücret istisnası birden fazla işverende tek kez uygulanır; personelin DÖSE ödemelerinde genellikle kümülatif matraha göre tarife uygulanır.</li>
</ul>

<h3>8. Satın Alma</h3>
<ul>
<li>Döner Sermayeli Kuruluşlar İhale Yönetmeliği ve 4734 sayılı Kanun parasal limitleri esas alınır.
2026 doğrudan temin (22/d) limiti: diğer idareler <b>340.391 TL</b>, büyükşehir <b>1.021.827 TL</b> (KDV hariç). İhtiyaçlar limit altında kalacak şekilde bölünemez.</li>
</ul>

<h3>8a. İskontolu Alış ve Satışlar</h3>
<ul>
<li>Faturada gösterilen iskonto KDV matrahına dahil edilmez (KDV K. md.25/a); KDV, stopaj ve muhasebe kaydı iskonto sonrası
tutardan hesaplanır. Fatura ve sipariş ekranlarında birim fiyat <b>iskontosuz</b> (liste fiyatı) yazılır, iskonto
<b>İsk. %</b> veya <b>İsk. TL</b> sütununa girilir; belge altındaki toplu iskonto için <b>Genel iskonto…</b> düğmesi kullanılır.
İndirim eksi satır olarak girilmez.</li>
<li>İskontolu alımda stoğa giren malzemenin maliyeti iskonto sonrası birim maliyettir (VUK md.262).</li>
<li>Satışta iskonto sonrası fiyat, komisyonca tespit edilen fiyatın altına düşemez; işletme aleyhine müşteri lehine indirim yapılamaz
(Çalışma Yönergesi md.26/g, md.29/a). Program bu durumda kayıttan önce açıkça onay ister.</li>
<li>"Belgedeki genel toplam (kontrol)" kutusuna kâğıt/e-belgedeki genel toplam yazılırsa program hesapladığı tutarla karşılaştırır,
fark varsa kaydetmez. Aynı belge numarası aynı cariye (satışta aynı yıl içinde) ikinci kez kaydedilemez.</li>
</ul>

<h3>8b. İşçilik ve Diğer Giderlerin Yasal Üst Sınırdan Hesaplanması</h3>
<ul>
<li><b>Sipariş</b>: "Yasal üst sınır (otomatik)" işaretliyken işçilik = sözleşme bedeli − asgari kâr − faaliyet gideri − malzeme
olarak kendiliğinden hesaplanır (Yön. md.8/2-4, md.10/3, md.12/1-d). Malzeme, ürünlerin maliyet kartından otomatik alınır.</li>
<li><b>Maliyet analizi</b>: "Otomatik hesapla" işaretliyken hedef birim satış fiyatından kâr asgari oranda, diğer giderler faaliyet
gideri oranına kadar (girilen enerji, bakım vb. giderler ayrılır, kalanı genel gidere yazılır), işçilik kalan tutarın tamamı,
öğrenci hakkı işçiliğin asgari %30'u olarak doldurulur.</li>
<li>Fazla çalışma esasında Yönetmelik kâr ve faaliyet gideri oranı öngörmediğinden bu hesaplarda parça başı oranları esas alınır.
Fazla çalışma saat ücreti, Parametreler'deki azami tutardan (Bütçe K cetveli III-3) gelir.</li>
</ul>

<h3>9. Muhasebe</h3>
<ul>
<li>Resmi muhasebe kayıtları D.S.İ.B.M.Y. hükümlerine göre BKMYBS üzerinden yürütülür. Bu uygulamadaki yevmiye ve mizan,
işlemlerden otomatik üretilen <b>yardımcı kayıt ve kontrol</b> amaçlıdır.</li>
<li>Muhasebe işlem fişi ekindeki belgeler harcama yetkilisince incelenerek imzalanır (DHGM 15.01.2026, m.14).</li>
<li>Promosyon ve faiz gelirleri döner sermaye hesabına gelir kaydedilir; vadeli hesap faizinin 1/3'ü dağıtılacak kârdan düşülür (m.16).</li>
</ul>

<h3>10. Döner Sermaye İşletmeleri Çalışma Yönergesi ve Bütçe Kanunu (uygulamada denetlenen hükümler)</h3>
<p><i>Yönergenin sonraki mevzuatla değişen sayısal sınırları yerine güncel hükümler uygulanır; örneğin yönergedeki aylık 60 saat
fazla çalışma sınırı yerine her yıl Merkezi Yönetim Bütçe Kanunu (K) cetvelindeki günlük sınırlar esas alınır.</i></p>
<ul>
<li><b>Fazla çalışma (2026 K cetveli III-3)</b>: olağan çalışma saatleri dışında, işin gereği olarak fiilen çalışanlara; öğretim
günlerinde günde en çok <b>3 saat</b>, resmi ve dini bayramlar dışındaki tatillerde günde en çok <b>8 saat</b>; saat ücreti
<b>67,50 TL</b>'yi geçmemek üzere müdürce üretime katkı ve işçilik payına göre belirlenir. Yardımcı hizmetler sınıfı ile şoförler
yararlanamaz. Bayram günlerinde fazla çalışma yapılamaz.</li>
<li><b>K cetveli III-4</b>: fiilen çalışmadığı hâlde ödeme yapılırsa ödenen tutar bir katı fazlasıyla geri alınır; bunun yarısı
mesai çizelgesini onaylayan yetkiliden tahsil edilir.</li>
<li><b>Pazar günü</b> fazla çalışma yapılmaz; otelcilik-turizm gibi istisna okullar Parametreler'den izin verebilir (Yön. md.9/a-12).</li>
<li><b>Puantaj (mesai çizelgesi)</b> atölye/bölüm şefince düzenlenir, gerçekleştirme görevlisi ve saymanca imzalanır, müdürce
onaylanır (Yön. md.9/c-e). Fazla çalışma sayfasındaki "Günlük puantaj" ve "Puantaj (mesai çizelgesi) PDF" bu amaçla kullanılır.</li>
<li>Fazla çalışma ve öğrenci ücretleri <b>izleyen ayın 10'una kadar</b> ödenir (Yön. md.9/b, md.42/c). Bir siparişte ödenen fazla
çalışma ve öğrenci hakkı toplamı, sipariş şartnamesi/maliyet çizelgesindeki işçiliği aşamaz (Yön. md.9/b, md.42/e).</li>
<li>Aynı iş için hem parça başı hem fazla çalışma ödenmez; idari görevliler aynı ayda ikisini birden alamaz (Yön. md.8/7).</li>
<li>Parça başı ücret, yalnızca bitirilip geçici kabulü yapılan iş için ödenir (Yön. md.8/8-a); dağıtılan işçilik, şartnamedeki
işçiliği aşamaz (Yön. md.8/4).</li>
<li>Sözleşme yapılmadan işe başlanmaz (Yön. md.26/d). Ürünler komisyonca tespit edilen fiyattan, tarım ve hayvan ürünleri bölge
rayicinden satılır; işletme aleyhine müşteri lehine indirim yapılamaz (Yön. md.26/g, md.29/a).</li>
<li>Faturalar her yıl 1'den başlayarak numaralanır (Yön. md.44). Harcamalarda yalnızca VUK md.228-238'deki belgeler kabul edilir;
perakende satış fişindeki KDV indirilemez (Yön. md.46).</li>
<li>İşletme ve idari masraflar, satışlardan ayrılan faaliyet gideri karşılığını aşamaz: "karşılıkta para yoksa harcama yapılamaz"
(Yön. md.11). Raporlar sayfasında aylık izlenir.</li>
<li><b>Üç aylık faaliyet raporu</b> dönemi izleyen ayın 5'ine kadar gönderilir (Yön. md.48); Raporlar sayfasından alınır.</li>
<li>Hazine payı ve SHÇEK payı işçilikten değil faaliyet giderinden/kârdan karşılanır (Yön. md.10/4, md.12/1-e; 2828 s.K. md.18).</li>
</ul>
"""
