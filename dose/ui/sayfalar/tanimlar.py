"""Bölüm, personel, öğrenci, cari ve malzeme tanım sayfaları."""
from datetime import date

from ... import excel, mevzuat
from ...dogrulama import d_iban, d_tckn, d_vkn_tckn, iban_normalize
from ..ortak import Alan, Kolon, KayitSayfasi, VarlikTanimi, db, fk_secenekleri


def bolumler():
    return fk_secenekleri("bolum", "ad", "aktif = 1")


TCKN_BASLIKLARI = ["kimlik", "tc", "tcno", "tckn", "tc no"]
AD_BASLIKLARI = ["adı soyadı", "adı ve soyadı", "ad soyad", "adsoyad", "isim"]


def _ogrenci_satiri(gorev) -> bool:
    return excel._norm(str(gorev or "")).startswith(("ogrenc", "kursiyer", "stajyer"))


def _iban_temizle(v, _eski):
    if v.get("iban"):
        v["iban"] = iban_normalize(v["iban"])
    return v


def _kullanim_var(sorgular):
    def kontrol(s):
        for sql, mesaj in sorgular:
            if db().deger(sql, (s["id"],), 0):
                return mesaj
        return None
    return kontrol


class BolumSayfasi(KayitSayfasi):
    def __init__(self):
        super().__init__(VarlikTanimi(
            tablo="bolum", baslik="Bölüm / Alan / Atölyeler",
            aciklama="Döner sermaye faaliyeti yürüten bölüm, alan ve atölyeler. ÜTP'nin %70'lik bölüm payı, "
                     "bölümlerin gelire katkı oranına göre ve burada seçilen yöntemle dağıtılır (Yön. md.5/7).",
            alanlar=[
                Alan("kod", "Kod"),
                Alan("ad", "Bölüm / atölye adı", zorunlu=True),
                Alan("alan", "Alan / dal"),
                Alan("utp_yontemi", "ÜTP bölüm içi dağıtım yöntemi", "secim", secenekler=mevzuat.UTP_BOLUM_YONTEMLERI,
                     varsayilan=mevzuat.UTP_BOLUM_YONTEMLERI[0], zorunlu=True),
                Alan("aktif", "Aktif", "bool", varsayilan=1),
                Alan("aciklama", "Açıklama", "cokmetin", tabloda=False),
            ],
            sirala="ad",
            silme_kontrol=_kullanim_var([
                ("SELECT COUNT(*) FROM personel WHERE bolum_id = ?", "Bu bölüme kayıtlı personel var."),
                ("SELECT COUNT(*) FROM siparis WHERE bolum_id = ?", "Bu bölüme ait sipariş var."),
            ]),
        ))


def _personel_dogrula(v, eski):
    h = []
    if v.get("tckn"):
        ayni = db().q1("SELECT id FROM personel WHERE tckn = ? AND id != ?", (v["tckn"], (eski or {}).get("id", 0)))
        if ayni:
            h.append("Bu T.C. kimlik numarası başka bir personelde kayıtlı.")
    gorev = v.get("dose_gorevi")
    if gorev in ("Harcama Yetkilisi (Okul Müdürü)", "Gerçekleştirme Görevlisi (Teknik Md. Yrd.)", "Sayman") and v.get("aktif"):
        ayni = db().q1("SELECT ad_soyad FROM personel WHERE dose_gorevi = ? AND aktif = 1 AND id != ?",
                       (gorev, (eski or {}).get("id", 0)))
        if ayni:
            h.append(f"'{gorev}' görevinde aktif başka personel var: {ayni['ad_soyad']}. "
                     f"Görev değişikliğinde önceki kaydı pasif yapınız.")
    return h


def _personel_kaydet(v, eski):
    v = _iban_temizle(v, eski)
    if not v.get("unvan_grubu"):
        v["unvan_grubu"] = mevzuat.GOREV_VARSAYILAN_UNVAN_GRUBU.get(v.get("dose_gorevi"), 3)
    return v


class PersonelSayfasi(KayitSayfasi):
    def __init__(self):
        super().__init__(VarlikTanimi(
            tablo="personel", baslik="Personel",
            aciklama="Döner sermayede görev alan 657 ve 4857 sayılı kanunlara tabi personel. Hizmet sınıfı parça başı aylık "
                     "tavanını, DÖSE görevi ÜTP idari payını, unvan grubu puan usulü dağıtımı belirler.",
            alanlar=[
                Alan("sicil_no", "Sicil / kurum no"),
                Alan("tckn", "T.C. kimlik no", dogrula=d_tckn),
                Alan("ad_soyad", "Adı soyadı", zorunlu=True),
                Alan("kadro_unvani", "Kadro unvanı / branş"),
                Alan("hizmet_sinifi", "Hizmet sınıfı", "secim", zorunlu=True, secenekler=mevzuat.HIZMET_SINIFLARI,
                     varsayilan=mevzuat.HIZMET_SINIFLARI[0]),
                Alan("dose_gorevi", "DÖSE görevi", "secim", zorunlu=True, secenekler=mevzuat.DOSE_GOREVLERI,
                     varsayilan="Öğretmen"),
                Alan("unvan_grubu", "Unvan puan grubu (md.5/8)", "secim", secenekler=list(mevzuat.UNVAN_GRUPLARI.items()),
                     varsayilan=3, tabloda=False),
                Alan("bolum_id", "Bölüm / atölye", "fk", secenekler=bolumler),
                Alan("istihdam", "İstihdam", "secim", secenekler=["657 s. DMK", "4857 s. İş Kanunu", "Sözleşmeli"],
                     varsayilan="657 s. DMK", tabloda=False),
                Alan("iban", "IBAN", dogrula=d_iban),
                Alan("telefon", "Telefon"),
                Alan("eposta", "E-posta", tabloda=False),
                Alan("aktif", "Aktif", "bool", varsayilan=1),
                Alan("notlar", "Notlar", "cokmetin", tabloda=False),
            ],
            sirala="aktif DESC, ad_soyad",
            on_dogrula=_personel_dogrula,
            on_kaydet=_personel_kaydet,
            silme_kontrol=_kullanim_var([
                ("SELECT COUNT(*) FROM parca_basi_satir WHERE kisi_turu = 'Personel' AND kisi_id = ?",
                 "Personelin parça başı ödeme kaydı var; silmek yerine pasif yapınız."),
                ("SELECT COUNT(*) FROM fazla_calisma WHERE personel_id = ?", "Personelin fazla çalışma kaydı var; pasif yapınız."),
                ("SELECT COUNT(*) FROM utp_kisi WHERE personel_id = ?", "Personelin ÜTP kaydı var; pasif yapınız."),
            ]),
            ice_aktarma={"sicil_no": ["personel no", "sicil", "id"], "tckn": TCKN_BASLIKLARI,
                         "ad_soyad": AD_BASLIKLARI + ["personel adı"],
                         "kadro_unvani": ["unvan", "görevi", "branş"], "iban": ["iban"], "telefon": ["telefon"]},
            ice_aktarma_suzgec=lambda k: not _ogrenci_satiri(k.get("kadro_unvani")),
            renk=lambda s: None if s.get("aktif") else "#eeeeee",
        ))


def _yas(dogum):
    if not dogum:
        return None
    d = date.fromisoformat(str(dogum)[:10])
    b = date.today()
    return b.year - d.year - ((b.month, b.day) < (d.month, d.day))


def _ogrenci_dogrula(v, _eski):
    h = []
    if v.get("veli_muvafakat") and not v.get("muvafakat_tarihi"):
        h.append("Veli muvafakat tarihi giriniz.")
    return h


class OgrenciSayfasi(KayitSayfasi):
    def __init__(self):
        super().__init__(VarlikTanimi(
            tablo="ogrenci", baslik="Öğrenciler / Kursiyerler",
            aciklama="Beceri eğitimini DÖSE işleri üzerinde yapan öğrenciler. Parça başı ücret ödenebilmesi için velinin "
                     "yazılı muvafakati zorunludur (Yön. md.8/1). Muvafakatnameyi 'Resmi Yazılar / Belgeler' ekranından yazdırabilirsiniz.",
            alanlar=[
                Alan("okul_no", "Okul no"),
                Alan("tckn", "T.C. kimlik no", dogrula=d_tckn),
                Alan("ad_soyad", "Adı soyadı", zorunlu=True),
                Alan("dogum_tarihi", "Doğum tarihi", "tarih"),
                Alan("sinif", "Sınıf / şube"),
                Alan("bolum_id", "Alan / bölüm", "fk", secenekler=bolumler),
                Alan("veli_adi", "Veli adı soyadı"),
                Alan("veli_telefon", "Veli telefon", tabloda=False),
                Alan("veli_muvafakat", "Veli yazılı muvafakati alındı", "bool"),
                Alan("muvafakat_tarihi", "Muvafakat tarihi", "tarih"),
                Alan("iban", "IBAN (öğrenci adına)", dogrula=d_iban),
                Alan("aktif", "Aktif", "bool", varsayilan=1),
                Alan("notlar", "Notlar", "cokmetin", tabloda=False),
            ],
            sirala="aktif DESC, ad_soyad",
            on_dogrula=_ogrenci_dogrula,
            on_kaydet=_iban_temizle,
            silme_kontrol=_kullanim_var([
                ("SELECT COUNT(*) FROM parca_basi_satir WHERE kisi_turu = 'Öğrenci' AND kisi_id = ?",
                 "Öğrencinin ödeme kaydı var; silmek yerine pasif yapınız."),
            ]),
            ice_aktarma={"okul_no": ["okul no", "okul numarası", "öğrenci no", "numara", "no"], "tckn": TCKN_BASLIKLARI,
                         "ad_soyad": AD_BASLIKLARI + ["öğrenci adı"], "sinif": ["sınıf", "şube"],
                         "iban": ["iban"], "_gorev": ["görevi", "unvan"]},
            ice_aktarma_suzgec=lambda k: k.get("_gorev") in (None, "") or _ogrenci_satiri(k.get("_gorev")),
            renk=lambda s: "#fdecea" if s.get("aktif") and not s.get("veli_muvafakat") else (None if s.get("aktif") else "#eeeeee"),
            bolum_kolonu="bolum_id",
        ))


def _cari_dogrula(v, _eski):
    h = []
    if v.get("tur") == "Çiftçi (Müstahsil)" and v.get("vkn_tckn") and len(str(v["vkn_tckn"])) != 11:
        h.append("Müstahsil makbuzu için çiftçinin T.C. kimlik numarası girilmelidir.")
    return h


def _cari_kaydet(v, eski):
    v = _iban_temizle(v, eski)
    if not v.get("kod"):
        v["kod"] = f"C{(db().deger('SELECT MAX(id) FROM cari', (), 0) or 0) + 1:04d}"
    return v


class CariSayfasi(KayitSayfasi):
    def __init__(self):
        super().__init__(VarlikTanimi(
            tablo="cari", baslik="Cari Hesaplar (Müşteri / Tedarikçi / Çiftçi)",
            aciklama="Mal ve hizmet satılan müşteriler, alım yapılan firmalar ve müstahsil makbuzu düzenlenen çiftçiler. "
                     "Kamu kurumları 4734 md.3/e kapsamında DÖSE'den ihalesiz alım yapabilir.",
            alanlar=[
                Alan("kod", "Cari kodu"),
                Alan("tur", "Türü", "secim", zorunlu=True, secenekler=mevzuat.CARI_TURLERI, varsayilan="Müşteri"),
                Alan("unvan", "Unvan / adı soyadı", zorunlu=True),
                Alan("kamu_kurumu", "Kamu kurumu", "bool"),
                Alan("vergi_dairesi", "Vergi dairesi"),
                Alan("vkn_tckn", "VKN / T.C. kimlik no", dogrula=d_vkn_tckn),
                Alan("telefon", "Telefon"),
                Alan("eposta", "E-posta", tabloda=False),
                Alan("adres", "Adres", "cokmetin", tabloda=False),
                Alan("iban", "IBAN", dogrula=d_iban, tabloda=False),
                Alan("aktif", "Aktif", "bool", varsayilan=1, tabloda=False),
                Alan("notlar", "Notlar", "cokmetin", tabloda=False),
            ],
            liste_sql=None, sirala="unvan",
            on_dogrula=_cari_dogrula, on_kaydet=_cari_kaydet,
            ek_kolonlar=[Kolon("bakiye", "Bakiye (+alacak / -borç)", "para")],
            silme_kontrol=_kullanim_var([
                ("SELECT COUNT(*) FROM fatura WHERE cari_id = ?", "Bu cariye ait fatura var."),
                ("SELECT COUNT(*) FROM siparis WHERE cari_id = ?", "Bu cariye ait sipariş var."),
            ]),
            ice_aktarma={"kod": ["müşteri kod", "müşteri no", "kod"], "unvan": ["unvan", "firma", "adı soyadı", "müşteri adı"],
                         "vkn_tckn": ["vergi no", "vergi kimlik", "vkn"] + TCKN_BASLIKLARI, "vergi_dairesi": ["vergi dairesi"], "telefon": ["telefon"],
                         "eposta": ["e-posta", "eposta", "mail"], "adres": ["adres"]},
        ))

    def veriler(self):
        from ...muhasebe import cari_bakiye
        satirlar = super().veriler()
        for s in satirlar:
            s["bakiye"] = cari_bakiye(s["id"])
        return satirlar


class MalzemeSayfasi(KayitSayfasi):
    def __init__(self):
        super().__init__(VarlikTanimi(
            tablo="malzeme", baslik="Malzeme / Stok Kartları",
            aciklama="Üretimde kullanılan ilk madde ve malzemeler, ticari mallar ve mamuller. Mevcut miktar ve ortalama maliyet "
                     "alış faturaları ile stok hareketlerinden hesaplanır.",
            alanlar=[
                Alan("kod", "Stok kodu"),
                Alan("ad", "Malzeme adı", zorunlu=True),
                Alan("tur", "Türü", "secim", zorunlu=True, secenekler=mevzuat.MALZEME_TURLERI, varsayilan=mevzuat.MALZEME_TURLERI[0]),
                Alan("birim", "Birim", "secim", secenekler=mevzuat.BIRIMLER, varsayilan="Kg", duzenlenebilir=True),
                Alan("kdv_orani", "KDV oranı", "oran", varsayilan=0.20),
                Alan("kritik_stok", "Kritik stok miktarı", "ondalik"),
                Alan("aktif", "Aktif", "bool", varsayilan=1, tabloda=False),
                Alan("aciklama", "Açıklama", "cokmetin", tabloda=False),
            ],
            sirala="ad",
            ek_kolonlar=[Kolon("mevcut", "Mevcut miktar", "sayi"), Kolon("ort_maliyet", "Ort. birim maliyet", "para")],
            silme_kontrol=_kullanim_var([("SELECT COUNT(*) FROM stok_hareket WHERE malzeme_id = ?", "Malzemenin stok hareketi var.")]),
            renk=lambda s: "#fff4e5" if s.get("kritik_stok") and (s.get("mevcut") or 0) <= s["kritik_stok"] else None,
        ))

    def veriler(self):
        from ...muhasebe import ortalama_maliyet, stok_miktari
        satirlar = super().veriler()
        for s in satirlar:
            s["mevcut"] = stok_miktari(s["id"])
            s["ort_maliyet"] = ortalama_maliyet(s["id"])
        return satirlar
