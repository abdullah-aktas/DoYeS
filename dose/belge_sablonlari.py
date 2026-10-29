"""Flet ve masaüstü tarafından ortak kullanılan resmi yazı şablonları."""

SABLONLAR = {
    "Serbest yazı": ("", "", ""),
    "Hazine payı ödemesi bildirimi": (
        "Hazine Payı Bildirimi",
        "İLGİLİ MUHASEBE BİRİMİNE",
        "Okulumuz Döner Sermaye İşletmesinin {ay} ayında aylık gayrisafi hasılattan tahsil edilen tutarı üzerinden hesaplanan hazine "
        "payı, Muhasebat Genel Müdürlüğü Genel Tebliği (Sıra No: 73) gereğince D.S.İ.B.M.Y. Örnek No: 30 bildirim formu ile birlikte "
        "ekte sunulmuş olup ilgili tutar muhasebe biriminiz hesabına yatırılmıştır.\n\nBilgilerinize arz ederim."),
    "Kamu kurumuna teklif üst yazısı (4734 md.3/e)": (
        "Fiyat Teklifi",
        "................................................ MÜDÜRLÜĞÜNE",
        "İlgi yazınız ile talep edilen mal/hizmete ilişkin fiyat teklifimiz ekte sunulmuştur. Söz konusu iş okulumuz atölye ve "
        "laboratuvarlarında öğrencilerimizin de katılımıyla bizzat üretilecek olup 4734 sayılı Kamu İhale Kanununun 3 üncü maddesinin "
        "(e) bendi kapsamında değerlendirilebilecektir.\n\nBilgilerinize arz ederim."),
    "İlçe MEM / okul talebine keşif-proforma cevabı": (
        "Keşif, Maliyet ve Proforma",
        "................................................ İLÇE MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE",
        "İlgi: a) ....../....../...... tarihli ve ............ sayılı yazınız.\n"
        "      b) ....../....../...... tarihli keşif / iş planı tutanağımız.\n\n"
        "İlgi (a) yazınız ile talep edilen işe ilişkin yerinde inceleme yapılmış; ihtiyaç duyulan kontrol, bakım ve onarım "
        "kalemleri iş planına bağlanmıştır. Malzeme ve işçilik giderlerini içeren maliyet hesabı ile proforma fatura ekte "
        "sunulmuştur.\n\n"
        "Proforma fatura vergi mevzuatı bakımından fatura değildir; yalnızca fiyat ve iş kapsamı teklifidir. Teklifinizin "
        "uygun bulunması hâlinde iş ve işlemler okulumuz Döner Sermaye İşletmesi üzerinden sözleşme imzalanarak "
        "yürütülecek, teslimde e-Fatura / e-Arşiv fatura düzenlenecektir (DÖSE Yönetmeliği md.9/4; 4734 sayılı Kanun md.3/e).\n\n"
        "Bilgilerinizi ve gereğini arz ederim."),
    "Proforma kabulü sonrası sözleşme daveti": (
        "Sözleşme",
        "................................................ MÜDÜRLÜĞÜNE / SAYIN ........",
        "İlgi: ....../....../...... tarihli ve ............ sayılı proforma / fiyat teklifimiz.\n\n"
        "İlgi teklifimizin uygun bulunduğu bildirilmiş olup, işin yürütülmesi için DÖSE Yönetmeliği md.9/4 gereği "
        "mal / hizmet üretim sözleşmesinin imzalanması gerekmektedir. Sözleşme imzalanmadan işe başlanamayacaktır.\n\n"
        "Ekte sunulan sözleşmenin imzalanarak okulumuz Döner Sermaye İşletmesine iletilmesini rica ederim."),
    "Döner sermaye çalışmaları görevlendirme oluru": (
        "Döner Sermaye Görevlendirmesi",
        "MÜDÜRLÜK MAKAMINA",
        "Okulumuz Döner Sermaye İşletmesinde {yil} yılında yürütülecek üretim ve hizmet çalışmalarında, 3423 sayılı Kanun ve Millî "
        "Eğitim Bakanlığı Döner Sermaye İşletmelerinde Üretimi Teşvik Primi Dağıtımı, Parça Başı Üretim, Atölye ve Tesislerin Özel "
        "Sektörle İşbirliği Yapılarak İşletilmesi Hakkında Yönetmelik hükümleri doğrultusunda ekli listede adı geçen personelin "
        "görevlendirilmesini olurlarınıza arz ederim.\n\nOLUR\n...../...../{yil}"),
    "Takdir komisyonu oluşturulması oluru": (
        "Çalışmayı Teşvik ve Takdir Komisyonu",
        "MÜDÜRLÜK MAKAMINA",
        "{yil} yılı üretimi teşvik priminin %5'lik çalışmayı teşvik ve çalışanı takdir payının dağıtımı için Yönetmeliğin 5 inci "
        "maddesinin altıncı fıkrası gereğince harcama yetkilisi, gerçekleştirme görevlisi ve ilgili bölüm/alan ile atölye "
        "şeflerinden oluşan komisyonun kurulmasını olurlarınıza arz ederim."),
    "Yıl sonu sayım kurulu oluru": (
        "Yıl Sonu Sayım Kurulu",
        "MÜDÜRLÜK MAKAMINA",
        "Okulumuz Döner Sermaye İşletmesinin 31.12.{yil} tarihli stok, kasa ve demirbaş sayımlarının yapılması için aşağıda adı "
        "geçen personelden sayım kurulu oluşturulmasını olurlarınıza arz ederim.\n\n1- ........................ (Başkan)\n"
        "2- ........................ (Üye)\n3- ........................ (Üye)"),
    "Muayene ve kabul komisyonu oluru": (
        "Muayene ve Kabul Komisyonu",
        "MÜDÜRLÜK MAKAMINA",
        "Okulumuz Döner Sermaye İşletmesince {yil} yılında satın alınacak mal ve hizmetler ile üretilen işlerin muayene ve kabul "
        "işlemlerini yürütmek üzere aşağıda adı geçen personelden muayene ve kabul komisyonu oluşturulmasını olurlarınıza arz ederim."
        "\n\n1- ........................ (Başkan)\n2- ........................ (Üye)\n3- ........................ (Üye)"),
    "Öğrenci velisine muvafakat talebi": (
        "Veli Muvafakati",
        "SAYIN VELİ",
        "Okulumuz Döner Sermaye İşletmesi bünyesinde yürütülen üretim çalışmalarına öğrencinizin katılabilmesi ve parça başı ücret "
        "ödenebilmesi için Yönetmeliğin 8 inci maddesi gereğince yazılı muvafakatinizin alınması gerekmektedir. Ekte sunulan "
        "muvafakatnamenin doldurularak okul müdürlüğüne teslim edilmesini rica ederim."),
}
