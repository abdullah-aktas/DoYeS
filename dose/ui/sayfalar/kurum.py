from PySide6.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ... import lisans
from ...dogrulama import d_iban, d_vkn_tckn, iban_normalize
from ..ortak import Alan, alan_kutusu, baslik_etiketi, bilgi, buton, db, kutu_ayarla, kutu_deger, uyari, yetki_kontrol

GRUPLAR = [
    ("Okul / İşletme Bilgileri", [
        Alan("okul_adi", "Okul adı", zorunlu=True),
        Alan("isletme_adi", "İşletme adı"),
        Alan("kurum_kodu", "Kurum kodu"),
        Alan("il", "İl"),
        Alan("ilce", "İlçe"),
        Alan("adres", "Adres", "cokmetin"),
        Alan("telefon", "Telefon"),
        Alan("eposta", "E-posta"),
        Alan("evrak_kodu", "Evrak sayı öneki", ipucu="Örn: E-12345678-841.99"),
    ]),
    ("Vergi ve Banka", [
        Alan("vergi_dairesi", "Vergi dairesi"),
        Alan("vkn", "Vergi kimlik no", dogrula=d_vkn_tckn),
        Alan("banka", "Banka / şube"),
        Alan("iban", "IBAN", dogrula=d_iban),
    ]),
    ("Görevliler (Yön. md.3)", [
        Alan("harcama_yetkilisi", "Harcama yetkilisi (Okul Müdürü)"),
        Alan("gerceklestirme_gorevlisi", "Gerçekleştirme görevlisi (Teknik Md. Yrd.)"),
        Alan("sayman", "Sayman"),
    ]),
    ("Sermaye ve Dağıtım Usulü", [
        Alan("tahsis_sermaye", "Tahsis edilen sermaye (TL)", "para",
             ipucu="DHGM Ek-5 listesinde işletmeye tahsis edilen sermaye"),
        Alan("odenmis_sermaye", "Ödenmiş sermaye (TL)", "para"),
        Alan("buyuksehir", "Büyükşehir belediyesi sınırları içinde", "bool",
             ipucu="Doğrudan temin limiti seçimi için"),
        Alan("yuz_yuze_egitim", "Öğrenci ile yüz yüze eğitim yapan işletme", "bool",
             ipucu="İşaretli değilse ÜTP, Yön. md.5/8 puan usulüyle dağıtılır"),
    ]),
]


class KurumSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi("Kurum ve Görevliler",
                                     "Belgelerin antetinde, imza bloklarında ve yıl sonu kâr bölüşümünde kullanılır."))
        kaydir = QScrollArea()
        kaydir.setWidgetResizable(True)
        ic = QWidget()
        ic_lay = QVBoxLayout(ic)
        self.kutular = {}
        for baslik, alanlar in GRUPLAR:
            g = QGroupBox(baslik)
            f = QFormLayout(g)
            for a in alanlar:
                w = alan_kutusu(a)
                self.kutular[a.ad] = (w, a)
                f.addRow(a.etiket + ":", w)
            ic_lay.addWidget(g)
        ic_lay.addStretch()
        kaydir.setWidget(ic)
        lay.addWidget(kaydir)
        alt = QHBoxLayout()
        alt.addWidget(buton("Personel kayıtlarından görevlileri doldur", self.personelden))
        alt.addStretch()
        alt.addWidget(buton("Kaydet", self.kaydet, "birincil"))
        lay.addLayout(alt)
        self.yenile()

    def yenile(self):
        k = db().kurum()
        for ad, (w, _a) in self.kutular.items():
            kutu_ayarla(w, k.get(ad))
        kod = self.kutular["kurum_kodu"][0]
        kilitli = lisans.lisansli_mi(db())
        kod.setReadOnly(kilitli)
        kod.setToolTip("Lisans bu kurum koduna bağlıdır; değiştirilemez." if kilitli else "")

    def personelden(self):
        for gorev, alan in [("Harcama Yetkilisi (Okul Müdürü)", "harcama_yetkilisi"),
                            ("Gerçekleştirme Görevlisi (Teknik Md. Yrd.)", "gerceklestirme_gorevlisi"),
                            ("Sayman", "sayman")]:
            p = db().q1("SELECT ad_soyad FROM personel WHERE dose_gorevi = ? AND aktif = 1", (gorev,))
            if p:
                kutu_ayarla(self.kutular[alan][0], p["ad_soyad"])

    def kaydet(self):
        if not yetki_kontrol(self, yonetici=True):
            return
        v, hatalar = {}, []
        for ad, (w, a) in self.kutular.items():
            v[ad] = kutu_deger(w, a)
            if a.zorunlu and not v[ad]:
                hatalar.append(f"'{a.etiket}' zorunludur.")
            if a.dogrula and a.dogrula(v[ad]):
                hatalar.append(f"{a.etiket}: {a.dogrula(v[ad])}")
        if hatalar:
            uyari(self, "\n".join(hatalar))
            return
        if v.get("iban"):
            v["iban"] = iban_normalize(v["iban"])
        if lisans.lisansli_mi(db()):
            v["kurum_kodu"] = db().kurum().get("kurum_kodu")
        db().guncelle("kurum", 1, v)
        if hasattr(self, "ana_pencere"):
            self.ana_pencere.okul_guncelle()
        bilgi(self, "Kurum bilgileri kaydedildi.")
