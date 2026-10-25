"""Rehberlik ve denetim formu için kontrol maddeleri ve PDF raporu."""
from __future__ import annotations

import html
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import mevzuat as M
from . import pdf


MADDELER = [
    ("2.1", "İşletmenin temel bilgileri, fiziki ortamı ve yeterliliği", [
        "Okulun eğitim geçmişi, bina/blok yapısı, program türü ve öğretim alanları güncel biçimde tanıtılmış mı?",
        "İşletmenin kuruluş tarihi, faaliyet alanları, bölüm/atölye/laboratuvarları ve donatımı kayıtlı mı?",
        "Öğrenci uygulaması ve sipariş üretiminde atölye kapasitesi, nitelikli insan gücü ve makineler etkin kullanılıyor mu?",
        "Yapılan işler eğitim programlarına ve işletmenin kapasitesine uygun seçiliyor mu?",
        "Atölye ve tesislerin özel sektörle birlikte kullanımı için gerekli izin ve düzenlemeler mevcut mu?",
        "Fiziki alanlar, makine ve teçhizat üretim, eğitim ve hizmet ihtiyaçlarını karşılıyor mu?",
        "Alan/atölye şefleri taşınırları koruyor, bakımlarını yaptırıyor ve kullanıma hazır tutuyor mu?",
        "Yerleşim planları, bölüm tabelaları ve isimlikler görünür ve güncel mi?",
        "Faaliyet alanlarında projeye aykırı değişiklikler için gerekli izinler alınmış mı?",
    ]),
    ("2.2", "Güvenlik önlemleri", [
        "Yangın, elektrik, ısınma, su ve gaz tesisatı yetkili kuruluşlara düzenli olarak kontrol ettiriliyor mu?",
        "Depremde devrilebilecek ağır ve yüksek eşyalar sabitlenmiş mi?",
        "İş ekipmanlarının periyodik kontrolleri ve güvenli kullanım çalışmaları kayıt altına alınıyor mu?",
        "Okul ve işletme alanları engelli bireylerin erişimine uygun mu?",
    ]),
    ("3.1", "Döner sermaye kapsamındaki eğitim-öğretim faaliyetleri", [
        "Sipariş ve üretim çalışmaları öğrenci ve kursiyerlerin uygulamalı eğitimini destekliyor mu?",
        "Alınan siparişler okulun mevcut alanları ve müfredat programıyla uyumlu mu?",
        "Alan öğretmenleri döner sermaye işlerini öğretim programlarına uygun planlıyor ve yaptırıyor mu?",
        "Uygulamalarda kullanılan araç-gereç listeleri ilgililere veriliyor mu?",
        "Üretim, temrin ve hizmetler şeflerle birlikte planlanıyor; öğrencilere proje rehberliği sağlanıyor mu?",
        "Yürütülen projeler ve kurum/kuruluş iş birlikleri kayıtlı ve amaçlarla uyumlu mu?",
    ]),
    ("3.2", "Eğitim-öğretim faaliyetlerinin sonuçları", [
        "Döner sermaye işleri alan becerilerinin ve öğrenci kazanımlarının gelişimine katkı sağlıyor mu?",
        "Öğrencilerin sipariş ve üretim süreçlerine fiilî katılımı izleniyor ve belgelendiriliyor mu?",
        "Uygulamalı çalışmaların sonuçları, hedefler ve eğitim programlarıyla karşılaştırılıyor mu?",
    ]),
    ("4.1", "İnsan kaynakları iş ve işlemleri", [
        "Görevli yönetici, öğretmen ve personel sayıları ile görev dağılımları yeterli ve güncel mi?",
        "Görevlendirmeler, çalışma planları ve sorumluluklar mevzuata uygun kayıt altına alınmış mı?",
        "Personel puantajları fiilî çalışmayı gösteriyor, yetkili kişilerce kontrol edilip onaya sunuluyor mu?",
        "Ek çalışma ve üretim karşılığı ödemeler hak sahipliği, puantaj ve mevzuata göre hesaplanıyor mu?",
        "Aynı çalışma için mükerrer ödeme riski önleniyor ve kayıtlar karşılaştırılıyor mu?",
        "Teknik müdür yardımcısı sipariş, piyasa, malzeme ve teslim süreçlerini düzenli izliyor mu?",
        "Alan şefleri üretimi şartname/standartlara göre planlıyor ve kalite kontrolünü sağlıyor mu?",
        "Görevli öğretmen ve yöneticiler nöbet ve gözetim sorumluluklarını yerine getiriyor mu?",
    ]),
    ("4.2", "İş sağlığı ve güvenliği", [
        "İSG işlemleri ile risk değerlendirmeleri güncel, izlenebilir ve işletme alanlarını kapsıyor mu?",
        "İşletmede yeterli sayıda geçerli ilk yardım eğitimi almış personel bulunuyor mu?",
        "Okul sağlığı ekibinin işletmeye yönelik çalışmaları planlanmış ve kayıt altına alınmış mı?",
    ]),
    ("4.3", "Yönetim faaliyetlerinin sonuçları", [
        "Yönetici, öğretmen ve atölye/alan sorumlularının sayısı iş yükü ve faaliyetler için yeterli mi?",
        "Yönetim, eğitim ve üretim hedefleri ölçülebilir sonuçlarla izleniyor mu?",
        "İnsan kaynağı ve görev dağılımı işletme faaliyetlerinin verimliliğini destekliyor mu?",
    ]),
    ("5.1", "Muhasebe, vergi, mali ve sosyal yükümlülükler", [
        "Tek düzen hesap planı, muhasebe sistemi ve gerekli Bakanlık muhasebe uygulamaları kullanılıyor mu?",
        "İdari, mali ve muhasebe işlemleri ilgili döner sermaye mevzuatına göre yürütülüyor mu?",
        "Önceki yıldan devreden hesaplar için açılış kayıtları ve mutabakatlar yapılmış mı?",
        "Vergi mevzuatına uygun belgeler düzenleniyor, teslim alınıyor ve saklanıyor mu?",
        "Gelir ve gider kayıtları dayanak belgeleriyle eşleştiriliyor ve zamanında işleniyor mu?",
        "Vergi, SGK ve diğer mali/sosyal yükümlülükler süresinde yerine getiriliyor mu?",
        "Kasa ve banka hareketleri, tahsilatlar ve ödemeler belgelerle doğrulanabiliyor mu?",
        "Dönem sonu ve yıl sonu hesapları, beyanlar ve mali tablolar kontrol ediliyor mu?",
        "Sayman görev ve sorumluluklarını, yetki ayrılığı ve kontrol ilkelerine uygun yerine getiriyor mu?",
        "Nakit, stok ve duran varlık işlemleri zamanında ve düzenli yürütülüyor mu?",
        "Ödeme emri belgeleri eksiksiz hazırlanıyor ve gerekli kontrollerden geçiriliyor mu?",
        "Kayıt ve personel özlük/ücret belgeleri yasal saklama sürelerine göre korunuyor mu?",
    ]),
    ("5.2", "Satın alma iş ve işlemleri", [
        "Mal ve hizmet alımları yürürlükteki ihale mevzuatına uygun yöntemle yürütülüyor mu?",
        "İhtiyaç, ödenek, yaklaşık maliyet ve teknik şartname önceden belirlenip belgelendiriliyor mu?",
        "Piyasa araştırması, teklif değerlendirmesi ve alım kararı izlenebilir mi?",
        "Muayene/kabul, teslim ve fatura kontrolleri görev ayrılığı içinde yapılıyor mu?",
        "Satın alma dosyaları, sözleşmeler ve ödeme belgeleri bütünlük içinde saklanıyor mu?",
    ]),
    ("5.3", "Üretimi teşvik primi ve parça başı ödemeler", [
        "Üretim ve ödeme usulleri yetkili onay, görev dağılımı ve mevzuat sınırları içinde belirlenmiş mi?",
        "Sipariş gelirinden kâr ve faaliyet gideri payları güncel mevzuata göre ayrılıyor mu?",
        "İşçilik payının öğrenci hakkı için ayrılması ve hak sahiplerine dağıtımı belgeli mi?",
        "Parça başı ücret hesabı fiilî katkı, üretim miktarı ve onaylı dağıtım ölçütlerine dayanıyor mu?",
        "Öğrenci/kursiyer ödemeleri için muvafakat, yaş sınırı, tavan ve ödeme kayıtları kontrol ediliyor mu?",
        "İdarî personel ödemeleri fiilen çalışılan gün ve mevzuattaki şartlarla uyumlu mu?",
        "Aynı iş ve dönem için parça başı ile fazla çalışma ödemesi çakışması engelleniyor mu?",
        "Yıl sonu dağıtımı, bilanço sonrası süreler ve hak sahibi listeleri kontrol ediliyor mu?",
    ]),
    ("5.4", "Üretilen mal ve hizmetlerin fiyatı ve satış işlemleri", [
        "Mal/hizmet satış bedelleri maliyetin altında kalmayacak şekilde belirlenip kayıt altına alınmış mı?",
        "Siparişlerde peşinat, tahsilat ve teslim şartları sözleşme/izin hükümlerine uygun mu?",
        "Fiyat tespitinde malzeme, işçilik, öğrenci hakkı ve diğer maliyet unsurları dikkate alınmış mı?",
        "Satış, fatura, teslim ve tahsilat kayıtları birbirleriyle tutarlı mı?",
        "Teknik şartnameye uygun üretim ve teslim kontrolleri yapılıyor mu?",
        "Muayene ve kabul işlemleri yetkili, yeterli sayıda üyeden oluşan heyetçe belgelendiriliyor mu?",
    ]),
    ("5.5", "Taşınır mal iş ve işlemleri", [
        "Üretime yönelik duran varlık alımları izin, bütçe ve tasarruf tedbirleri yönünden uygun mu?",
        "Taşınırların giriş, zimmet, kullanım, sayım ve kayıt işlemleri zamanında yürütülüyor mu?",
        "Duran varlıkların devir, düşüm ve amortisman işlemleri dayanaklarıyla yapılmış mı?",
        "Fizikî sayımlar ve muhasebe/taşınır kayıtları arasında mutabakat sağlanıyor mu?",
    ]),
    ("5.6", "Mali iş ve işlemlerinin sonuçları", [
        "Mali sonuçlar hedef, bütçe ve önceki dönemlerle karşılaştırılarak değerlendiriliyor mu?",
        "Tespit edilen sapma, kamu zararı ve kontrol riskleri için sorumlu ve takvim belirlenmiş mi?",
    ]),
]

MADDELER = [
    {"kod": f"{bolum}.{no:02d}", "bolum": bolum, "baslik": baslik, "soru": soru}
    for bolum, baslik, sorular in MADDELER
    for no, soru in enumerate(sorular, 1)
]

BOLUM_YETKILERI = {
    "2.1": {M.ROL_MUDUR, M.ROL_TMY, M.ROL_SEF},
    "2.2": {M.ROL_MUDUR, M.ROL_TMY, M.ROL_SEF},
    "3.1": {M.ROL_MUDUR, M.ROL_TMY, M.ROL_SEF, M.ROL_OGRETMEN},
    "3.2": {M.ROL_MUDUR, M.ROL_TMY, M.ROL_SEF, M.ROL_OGRETMEN},
    "4.1": {M.ROL_MUDUR, M.ROL_TMY, M.ROL_SEF, M.ROL_OGRETMEN},
    "4.2": {M.ROL_MUDUR, M.ROL_TMY, M.ROL_SEF},
    "4.3": {M.ROL_MUDUR, M.ROL_TMY},
    "5.1": {M.ROL_MUDUR, M.ROL_TMY, M.ROL_SAYMAN},
    "5.2": {M.ROL_MUDUR, M.ROL_TMY, M.ROL_MEMUR},
    "5.3": {M.ROL_MUDUR, M.ROL_TMY, M.ROL_SAYMAN, M.ROL_SEF},
    "5.4": {M.ROL_MUDUR, M.ROL_TMY, M.ROL_SAYMAN, M.ROL_MEMUR},
    "5.5": {M.ROL_MUDUR, M.ROL_TMY, M.ROL_SAYMAN, M.ROL_MEMUR},
    "5.6": {M.ROL_MUDUR, M.ROL_TMY, M.ROL_SAYMAN},
}

BILGI_ALANLARI = (
    "il", "ilce", "okul_adi", "kurum_kodu", "telefon_faks", "alan_dallar", "isletme_acilis_tarihi",
    "faaliyet_alani", "makine_techizat", "son_denetim_tarihi", "denetim_baslangic", "denetim_bitis",
    "yonetici_kadin", "yonetici_erkek", "sef_kadin", "sef_erkek", "ogretmen_kadin", "ogretmen_erkek",
    "diger_personel_kadin", "diger_personel_erkek", "ogrenci_kadin", "ogrenci_erkek",
    "giris", "hizmet_ortami_bulgulari", "hizmet_ortami_onerileri", "egitim_bulgulari", "egitim_onerileri",
    "yonetim_bulgulari", "yonetim_onerileri", "mali_bulgular", "mali_oneriler",
    "il_mudurlugune_oneriler", "sonuc_ve_genel_oneriler", "yonetici_bilgileri",
)
ZORUNLU_RAPOR_ALANLARI = BILGI_ALANLARI


def rapor_pdf(kurum: dict, denetim: dict, maddeler: list[dict]) -> bytes:
    """Denetim bilgileri ve değerlendirmeleriyle paylaşılabilir PDF raporu üretir."""
    stream = io.BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=15 * mm, bottomMargin=17 * mm, title="DÖSE Rehberlik ve Denetim Raporu")
    normal = ParagraphStyle("denetim_normal", parent=pdf.S_NORMAL, fontSize=9, leading=12)
    centered = ParagraphStyle("denetim_center", parent=normal, alignment=TA_CENTER)
    title = ParagraphStyle("denetim_title", parent=pdf.S_BASLIK, fontSize=14, leading=18)
    heading = ParagraphStyle("denetim_heading", parent=pdf.S_ALT_BASLIK, fontSize=10)
    esc = lambda value: html.escape(str(value or "")).replace("\n", "<br/>")
    info = denetim.get("bilgiler") or {}
    story = [
        Paragraph("T.C.<br/>MİLLÎ EĞİTİM BAKANLIĞI<br/>TEFTİŞ KURULU BAŞKANLIĞI", centered),
        Spacer(1, 5 * mm),
        Paragraph("DÖNER SERMAYE İŞLETMESİ<br/>REHBERLİK VE DENETİM RAPORU", title),
        Spacer(1, 4 * mm),
    ]
    fields = [
        ("İl / İlçe", f"{info.get('il', '')} / {info.get('ilce', '')}"),
        ("Okul", info.get("okul_adi") or kurum.get("okul_adi")),
        ("Kurum kodu", info.get("kurum_kodu") or kurum.get("kurum_kodu")),
        ("Telefon / faks", info.get("telefon_faks")),
        ("Öğretim alan ve dalları", info.get("alan_dallar")),
        ("İşletme açılış tarihi", info.get("isletme_acilis_tarihi")),
        ("Faaliyet alanı", info.get("faaliyet_alani")),
        ("Makine ve teçhizat", info.get("makine_techizat")),
        ("Son denetim", info.get("son_denetim_tarihi")),
        ("Denetim tarihleri", f"{info.get('denetim_baslangic', '')} - {info.get('denetim_bitis', '')}"),
    ]
    for baslik, anahtar in (("Yönetici", "yonetici"), ("Alan/atölye şefi", "sef"),
                            ("Öğretmen", "ogretmen"), ("Diğer personel", "diger_personel"),
                            ("Öğrenci", "ogrenci")):
        kadin, erkek = info.get(f"{anahtar}_kadin", ""), info.get(f"{anahtar}_erkek", "")
        fields.append((f"{baslik} sayısı (K/E/Toplam)",
                       f"{kadin} / {erkek} / {int(kadin or 0) + int(erkek or 0)}"
                       if str(kadin or "").isdecimal() and str(erkek or "").isdecimal() else ""))
    sayilar = [info.get(f"{anahtar}_{cinsiyet}", "") for anahtar in
               ("yonetici", "sef", "ogretmen", "diger_personel", "ogrenci") for cinsiyet in ("kadin", "erkek")]
    if all(str(sayi or "").isdecimal() for sayi in sayilar):
        fields.append(("Genel toplam (K/E/Toplam)",
                       f"{sum(int(sayilar[i]) for i in range(0, len(sayilar), 2))} / "
                       f"{sum(int(sayilar[i]) for i in range(1, len(sayilar), 2))} / {sum(map(int, sayilar))}"))
    table = Table([[Paragraph(f"<b>{esc(label)}</b>", normal), Paragraph(esc(value), normal)] for label, value in fields],
                  colWidths=[48 * mm, 122 * mm])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
                               ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf2f7")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(table)
    for heading_text, key in (
        ("1. Giriş", "giris"),
        ("2. Hizmet ortamları — bulgular", "hizmet_ortami_bulgulari"),
        ("2. Hizmet ortamları — çözüm önerileri", "hizmet_ortami_onerileri"),
        ("3. Eğitim-öğretim faaliyetleri — bulgular", "egitim_bulgulari"),
        ("3. Eğitim-öğretim faaliyetleri — çözüm önerileri", "egitim_onerileri"),
        ("4. Yönetim faaliyetleri — bulgular", "yonetim_bulgulari"),
        ("4. Yönetim faaliyetleri — çözüm önerileri", "yonetim_onerileri"),
        ("5. Mali iş ve işlemler — bulgular", "mali_bulgular"),
        ("5. Mali iş ve işlemler — çözüm önerileri", "mali_oneriler"),
        ("6. İl/ilçe millî eğitim müdürlüğü tarafından yapılması gereken çalışmalar",
         "il_mudurlugune_oneriler"),
        ("7. Sonuç ve genel öneriler", "sonuc_ve_genel_oneriler"),
        ("8. Değerlendirilen yöneticiler", "yonetici_bilgileri"),
    ):
        story.extend([Spacer(1, 3 * mm), Paragraph(esc(heading_text), heading),
                      Paragraph(esc(info.get(key)) or "Bilgi girilmemiştir.", normal)])
    story.extend([Spacer(1, 4 * mm), Paragraph("Kontrol listesi değerlendirmeleri", heading)])
    for madde in maddeler:
        durum = madde.get("durum") or "Değerlendirilmedi"
        story.append(Paragraph(f"<b>{esc(madde.get('kod'))} — {esc(madde.get('soru'))}</b><br/>"
                               f"Sonuç: {esc(durum)}"
                               + (f"<br/>Açıklama / kanıt: {esc(madde.get('aciklama'))}" if madde.get("aciklama") else ""),
                               normal))
        story.append(Spacer(1, 2 * mm))
    story.extend([Spacer(1, 6 * mm), Paragraph("Rapor tarihi: " + date.today().strftime("%d.%m.%Y"), normal),
                  Spacer(1, 7 * mm),
                  Paragraph("Denetim görevlileri / imzalar: _______________________________________________", normal)])
    doc.build(story)
    return stream.getvalue()
