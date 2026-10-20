"""Mevzuat uyum denetimi: bütün kayıtları tarar, aykırılıkları sade dille ve "ne yapmalıyım?" cevabıyla listeler.

Kayıt ekranları hatalı belgeyi zaten kaydettirmez; bu modül ise
- süresi geçen veya unutulan işleri (fatura kesilmemesi, onaysız üretim, ödenmemiş bordro),
- kayıtlar arasındaki tutarsızlıkları (eksi kasa, IBAN'sız ödeme, eski sürümden kalan hatalı kayıtlar),
- görevler ayrılığı ve güvenlik eksiklerini
yakalar. Sonuç rol ve bölüme göre süzülerek "Bugün Ne Yapmalıyım?" listesine de dönüşür.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta

from . import gosterge, kilavuz, onay, yetki
from . import mevzuat as M
from .db import al
from .hesap import para, siparis_kaydi_tahsisi, takvim_tanimli, yuvarla
from .yonerge_raporlari import idari_masraf_karsiligi

HATA, UYARI, BILGI = "hata", "uyari", "bilgi"
SEVIYE_ADI = {HATA: "Acil / riskli", UYARI: "Dikkat", BILGI: "Bilgi"}
SEVIYE_SIRA = {HATA: 0, UYARI: 1, BILGI: 2}

BASLAMIS = ("Üretimde", "Tamamlandı (Geçici Kabul)", "Faturalandı", "Kapandı")
TESLIM_EDILMIS = ("Tamamlandı (Geçici Kabul)", "Faturalandı", "Kapandı")
FATURA_SURESI_GUN = 7
ALACAK_GUN = 60
LISTE_SINIRI = 8

SAYFA_KONUSU = {
    "Siparişler / İş Emirleri": "Siparişler", "Öğrenciler": "Öğrenciler", "Personel": "Personel",
    "Satış Faturaları": "Satış ve tahsilat", "Alış / Gider Belgeleri": "Satın alma", "Kasa / Banka": "Kasa ve banka",
    "Parça Başı Ücret": "Personel ödemeleri", "Fazla Çalışma Ücreti": "Personel ödemeleri",
    "Yıl Sonu Kârı ve ÜTP": "Yıl sonu", "Hazine Payı / SHÇEK": "Yasal ödemeler", "KDV / Muhtasar Özeti": "Vergiler",
    "Stok Durumu ve Hareketleri": "Stok", "Raporlar": "Raporlar", "Kurum ve Görevliler": "Kurum ve sistem",
    "Mevzuat Parametreleri": "Kurum ve sistem", "Kullanıcılar": "Kurum ve sistem", "Yedekleme / İşlem Kaydı": "Kurum ve sistem",
}

# Gösterge uyarılarının sade "ne yapmalıyım?" karşılıkları (ilgili sayfaya göre)
SAYFA_COZUMU = {
    "Hazine Payı / SHÇEK": "Hazine Payı / SHÇEK sayfasında ilgili ayı seçip 'Seçili ayı hesapla / güncelle', ardından bildirim "
                           "PDF'ini alıp bildirin, ödeyin ve 'Ödeme kaydı oluştur' düğmesine basın.",
    "KDV / Muhtasar Özeti": "KDV / Muhtasar Özeti sayfasındaki tutarlarla beyannameyi süresinde verin ve ödeyin.",
    "Fazla Çalışma Ücreti": "Fazla Çalışma Ücreti sayfasında ayı seçip 'Banka listesi (Excel)' ile ödemeyi yapın, sonra "
                            "'Ödeme kaydı oluştur' düğmesine basın.",
    "Parça Başı Ücret": "Parça Başı Ücret sayfasında bordroyu seçip 'Banka listesi (Excel)' ile ödemeyi yapın, sonra "
                        "'Ödeme kaydı oluştur' düğmesine basın.",
    "Yıl Sonu Kârı ve ÜTP": "Yıl Sonu Kârı ve ÜTP sayfasında dağıtımı hesaplayıp onaya gönderin.",
    "Kurum ve Görevliler": "Kurum ve Görevliler sayfasında eksik bilgileri doldurup 'Kaydet'e basın.",
    "Mevzuat Parametreleri": "Mevzuat Parametreleri sayfasında yılın değerlerini kontrol edip 'Kaydet'e basın.",
    "Alış / Gider Belgeleri": "Alımları inceleyin; aynı ihtiyaç bölünmüşse durumu saymana ve müdüre bildirin, sonraki alımları "
                              "uygun ihale usulüyle yapın.",
    "Stok Durumu ve Hareketleri": "Malzemenin yeniden alınması gerekip gerekmediğini alan şefiyle değerlendirin.",
    "Yedekleme / İşlem Kaydı": "Yedekleme / İşlem Kaydı sayfasında 'Şimdi yedekle', ardından 'Farklı konuma yedekle' ile "
                               "harici diske de kopyalayın.",
}


@dataclass
class Bulgu:
    seviye: str
    konu: str
    baslik: str
    aciklama: str = ""
    cozum: str = ""
    dayanak: str = ""
    sayfa: str | None = None
    rehber: str | None = None

    @property
    def sorumlular(self) -> list[str]:
        return sorumlu_roller(self.sayfa)

    def sozluk(self) -> dict:
        return asdict(self) | {"seviye_adi": SEVIYE_ADI[self.seviye], "sorumlular": self.sorumlular}


def sorumlu_roller(sayfa: str | None) -> list[str]:
    """İşi yapabilecek (sayfada kayıt yetkisi olan) roller; sistem yöneticisi yalnız başka kimse yoksa yazılır."""
    if not sayfa:
        return [M.ROL_SAYMAN, M.ROL_MUDUR]
    roller = [r for r in M.ROLLER if yetki.sayfa_yetkisi(r, sayfa) == "y"]
    asil = [r for r in roller if r not in (M.ROL_SISTEM, M.ROL_MEMUR)]
    return asil or roller


def _rehber(sayfa: str | None) -> str | None:
    y = kilavuz.SAYFA_YARDIMI.get(sayfa or "")
    return y[3] if y else None


def _liste(ogeler: list[str]) -> str:
    ogeler = [o for o in ogeler if o]
    ek = f" ve {len(ogeler) - LISTE_SINIRI} kayıt daha" if len(ogeler) > LISTE_SINIRI else ""
    return ", ".join(ogeler[:LISTE_SINIRI]) + ek


def _norm(s) -> str:
    return " ".join(str(s or "").lower().split())


def _tarih(s) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


class _Denetci:
    def __init__(self, yil: int, bolum_id: int | None, bugun: date):
        self.d = al()
        self.yil, self.bolum_id, self.bugun = yil, bolum_id, bugun
        self.p = self.d.parametreler(yil)
        self.k = self.d.kurum()
        self.bulgular: list[Bulgu] = []

    def ekle(self, seviye, sayfa, baslik, aciklama="", cozum="", dayanak="", konu=None, rehber=None):
        self.bulgular.append(Bulgu(seviye, konu or SAYFA_KONUSU.get(sayfa or "", "Genel"), baslik, aciklama, cozum, dayanak,
                                   sayfa, rehber or _rehber(sayfa)))

    def _bolum_kosulu(self, kolon: str) -> tuple[str, tuple]:
        return (f" AND {kolon} = ?", (self.bolum_id,)) if self.bolum_id else ("", ())

    # ------------------------------------------------------------ kurum ve sistem
    def kurum_ve_sistem(self):
        d, k = self.d, self.k
        hy, gg, sy = _norm(k.get("harcama_yetkilisi")), _norm(k.get("gerceklestirme_gorevlisi")), _norm(k.get("sayman"))
        if hy and hy == sy:
            self.ekle(HATA, "Kurum ve Görevliler", "Harcama yetkilisi ile sayman aynı kişi",
                      "Ödeme talimatını veren (müdür) ile ödemeyi yapan ve kaydeden (sayman) aynı kişi olarak yazılmış. "
                      "Görevler ayrılığı ilkesine aykırıdır; ortaya çıkacak her zarardan bu kişi tek başına sorumlu tutulur.",
                      "Saymanlık görevine müdür dışında bir personeli yazıyla görevlendirin ve Kurum ve Görevliler sayfasını düzeltin.",
                      "DÖSE Yönetmeliği md.3; DHGM 15.01.2026 yazısı m.15")
        if gg and gg == sy:
            self.ekle(UYARI, "Kurum ve Görevliler", "Gerçekleştirme görevlisi ile sayman aynı kişi",
                      "Belgeleri hazırlayıp kontrol eden kişi ile ödemeyi yapan kişi aynı. Kontrol mekanizması işlemez.",
                      "Mümkünse bu iki görevi farklı kişilere verin.", "Görevler ayrılığı ilkesi")
        try:
            varsayilan_sifre = d.giris_dogrula("admin", "admin") is not None
        except Exception:
            varsayilan_sifre = False
        if varsayilan_sifre:
            self.ekle(HATA, "Kullanıcılar", "Yönetici şifresi hâlâ 'admin'",
                      "Programı bilen herkes yönetici olarak girip kayıtları değiştirebilir; yapılan işlemler sizin adınıza "
                      "kaydedilir.", "'admin' ile giriş yapıp üst çubuktaki 'Şifre' düğmesiyle şifreyi değiştirin.")
        aktif = d.q("SELECT rol FROM kullanici WHERE aktif = 1")
        roller = {r["rol"] for r in aktif}
        if len(aktif) > 1 and not onay.akis_acik():
            self.ekle(UYARI, "Kullanıcılar", "Onay akışı kapalı",
                      "Sipariş ve ücret bordroları tek kişi tarafından tek adımda onaylanabiliyor; şef, müdür yardımcısı ve "
                      "müdürün sırayla kontrol etmesi sağlanmıyor.",
                      "Kullanıcılar sayfasında onay akışını açın.", "5018 s.K. md.31-33 (harcama süreci)")
        elif onay.akis_acik():
            eksik = [r for r in (M.ROL_MUDUR, M.ROL_TMY, M.ROL_SAYMAN) if r not in roller]
            if eksik:
                self.ekle(UYARI, "Kullanıcılar", "Onay aşamalarından birinin kullanıcısı yok: " + ", ".join(eksik),
                          "Kullanıcısı olmayan aşama onay akışında kendiliğinden atlanır; o kişinin kontrolü yapılmamış olur.",
                          "Kullanıcılar sayfasında bu görevliler için kendi adlarına kullanıcı açın.")
        if not takvim_tanimli(self.yil, self.p):
            self.ekle(UYARI, "Mevzuat Parametreleri", f"{self.yil} yılı tatil ve bayram günleri tanımlanmamış",
                      "Fazla çalışmada hangi günün tatil, hangisinin bayram olduğu bilinmiyor; günlük 3/8 saat sınırı yanlış "
                      "denetlenebilir.", "Mevzuat Parametreleri sayfasında tatil dönemlerini ve bayram günlerini MEB çalışma "
                      "takvimine göre girin.", "Bütçe Kanunu K cetveli III-3")
        if self.bugun.month == 12 and self.yil == self.bugun.year and \
                not d.deger("SELECT COUNT(*) FROM parametre WHERE yil = ?", (self.yil + 1,), 0):
            self.ekle(BILGI, "Mevzuat Parametreleri", f"{self.yil + 1} yılı parametreleri henüz girilmedi",
                      "Yeni yılda asgari ücret, vergi tarifesi, fazla çalışma ücreti ve doğrudan temin limiti değişir.",
                      "Ocak ayında Resmî Gazete'de yayımlanan değerleri Mevzuat Parametreleri sayfasına girin.")

    # ------------------------------------------------------------ siparişler
    def siparisler(self):
        d = self.d
        bk, bp = self._bolum_kosulu("s.bolum_id")
        siparisler = d.q(f"""SELECT s.*, (SELECT COUNT(*) FROM fatura f WHERE f.siparis_id = s.id AND f.tur = 'Satış' AND f.iptal = 0) fatura_sayisi,
                                    (SELECT COUNT(*) FROM siparis_gorevli g WHERE g.siparis_id = s.id AND g.kisi_turu = 'Öğrenci') ogrenci_sayisi,
                                    (SELECT COUNT(*) FROM siparis_gorevli g WHERE g.siparis_id = s.id AND g.kisi_turu = 'Personel') personel_sayisi
                             FROM siparis s WHERE s.durum != 'İptal'
                             AND (substr(s.tarih, 1, 4) = ? OR s.durum NOT IN ('Faturalandı', 'Kapandı')){bk}
                             ORDER BY s.tarih""", (str(self.yil), *bp))
        akis = onay.akis_acik()
        onaylar = onay.durumlar("Sipariş") if akis else {}
        onaysiz, ogrencisiz, gorevsiz, kabulsuz, faturasiz, bedelsiz, gecikmis, ogr_yok, tahsis = ([] for _ in range(9))
        param = {}
        for s in siparisler:
            no = s["siparis_no"] or f"#{s['id']}"
            durum = s["durum"] or ""
            od = onaylar.get(s["id"])
            if akis and od and od["durum"] != onay.ONAYLANDI and durum in BASLAMIS:
                onaysiz.append(no)
            if durum in BASLAMIS:
                if s["ogrenci_uygulamasi"] and not s["ogrenci_sayisi"]:
                    ogrencisiz.append(no)
                if not s["personel_sayisi"]:
                    gorevsiz.append(no)
            teklif_asama = durum in M.SIPARIS_TEKLIF_ASAMALARI
            if not s["ogrenci_uygulamasi"] and not teklif_asama and durum != "Kapandı":
                ogr_yok.append(no)
            if durum in TESLIM_EDILMIS and not s["kabul_tarihi"]:
                kabulsuz.append(no)
            kabul = _tarih(s["kabul_tarihi"])
            if not s["fatura_sayisi"] and (durum in ("Faturalandı", "Kapandı") or
                                           (kabul and (self.bugun - kabul).days > FATURA_SURESI_GUN)):
                faturasiz.append(f"{no} ({kabul:%d.%m.%Y})" if kabul else no)
            if not teklif_asama and not (s["sozlesme_bedeli"] or 0):
                bedelsiz.append(no)
            teslim = _tarih(s["teslim_tarihi"])
            if durum in ("Sözleşme İmzalandı", "Üretimde") and teslim and teslim < self.bugun:
                gecikmis.append(f"{no} ({teslim:%d.%m.%Y})")
            if not teklif_asama and durum != "Kapandı":
                yil = int((s["tarih"] or str(self.yil))[:4])
                param.setdefault(yil, d.parametreler(yil))
                h = siparis_kaydi_tahsisi(dict(s), param[yil]).hatalar
                if h:
                    tahsis.append(f"{no}: {h[0]}")
        S = "Siparişler / İş Emirleri"
        if onaysiz:
            self.ekle(HATA, S, f"Onaylanmadan üretime geçilmiş {len(onaysiz)} sipariş",
                      f"Bu siparişler onay akışını tamamlamadan 'Üretimde' veya sonraki bir duruma alınmış: {_liste(onaysiz)}.",
                      "Siparişi seçip 'Onay akışı' ile onaya gönderin; müdür onaylamadan işe devam etmeyin.",
                      "Çalışma Yönergesi md.26/d; DÖSE Yönetmeliği md.9/4")
        if faturasiz:
            self.ekle(HATA, S, f"Teslim edildiği hâlde faturası kesilmemiş {len(faturasiz)} sipariş",
                      f"Fatura, işin tesliminden itibaren en geç {FATURA_SURESI_GUN} gün içinde düzenlenmelidir: {_liste(faturasiz)}.",
                      "Siparişi seçip 'Faturalandır' düğmesine basın; faturayı e-Fatura/e-Arşiv olarak düzenleyip numarasını girin.",
                      "VUK md.231/5, md.353 (özel usulsüzlük cezası)")
        if ogr_yok:
            self.ekle(HATA, S, f"Öğrencinin uygulamaya alınmadığı {len(ogr_yok)} iş",
                      f"Öğrencinin çalışmadığı iş döner sermayede kabul edilemez: {_liste(ogr_yok)}.",
                      "Siparişte 'Öğrenciler bu işte uygulamaya alınacak' kutusunu işaretleyip öğrencileri görevlendirin ya da "
                      "işi iptal edin.", "DHGM 15.01.2026 yazısı m.1")
        if tahsis:
            self.ekle(HATA, S, f"Bedel dağılımı mevzuata uymayan {len(tahsis)} sipariş",
                      "Kâr, faaliyet gideri, işçilik veya öğrenci hakkı yasal oranları tutmuyor: " + _liste(tahsis),
                      "Siparişi açıp 'Kalemler ve bedel tahsisi' sekmesindeki kırmızı uyarıları düzeltin.",
                      "DÖSE Yönetmeliği md.8, md.10, md.12")
        if ogrencisiz:
            self.ekle(UYARI, S, f"Uygulama yapan öğrencisi işaretlenmemiş {len(ogrencisiz)} sipariş",
                      f"Öğrencinin uygulamaya alındığı belgelenmemiş: {_liste(ogrencisiz)}.",
                      "Siparişin 'Görevliler' sekmesinde işte çalışan öğrencileri işaretleyin.", "DHGM 15.01.2026 yazısı m.1")
        if gorevsiz:
            self.ekle(UYARI, S, f"Görevli personeli belirlenmemiş {len(gorevsiz)} sipariş",
                      f"Görevlendirme onayı olmadan çalışan personele ücret ödenemez: {_liste(gorevsiz)}.",
                      "'Görevliler' sekmesinde personeli işaretleyip 'Belgeler ▾ → Görevlendirme onayı' çıktısını imzalatın.")
        if kabulsuz:
            self.ekle(UYARI, S, f"Geçici kabul tarihi girilmemiş {len(kabulsuz)} sipariş",
                      f"Tamamlandı olarak işaretlenmiş ama kabul tarihi yok: {_liste(kabulsuz)}. Kabulü yapılmayan işe parça "
                      "başı ücret ödenemez.", "Okul komisyonuna 'Geçici muayene ve kabul tutanağı'nı imzalatıp tarihi siparişe girin.",
                      "DÖSE Yönetmeliği md.8/8-a")
        if gecikmis:
            self.ekle(UYARI, S, f"Teslim tarihi geçmiş {len(gecikmis)} sipariş", _liste(gecikmis) + ".",
                      "İşi hızlandırın veya müşteriyle yazılı olarak yeni teslim tarihi belirleyip siparişe girin.")
        if bedelsiz:
            self.ekle(UYARI, S, f"Sözleşme bedeli sıfır görünen {len(bedelsiz)} sipariş", _liste(bedelsiz) + ".",
                      "Siparişin kalemlerini ve fiyatlarını girin.")

    # ------------------------------------------------------------ satış ve tahsilat
    def satislar(self):
        d, y = self.d, str(self.yil)
        sinir = (self.bugun - timedelta(days=ALACAK_GUN)).isoformat()
        acik = d.q("""SELECT f.belge_no, f.tarih, c.unvan,
                             f.net_tutar - COALESCE(f.avans_mahsup, 0) - COALESCE((SELECT SUM(k.tutar) FROM kasa_banka k
                                                                                  WHERE k.fatura_id = f.id), 0) kalan
                      FROM fatura f LEFT JOIN cari c ON c.id = f.cari_id
                      WHERE f.tur = 'Satış' AND f.iptal = 0 AND f.tarih <= ? ORDER BY f.tarih""", (sinir,))
        acik = [a for a in acik if (a["kalan"] or 0) > 0.009]
        if acik:
            self.ekle(UYARI, "Satış Faturaları", f"{ALACAK_GUN} günden eski tahsil edilmemiş {len(acik)} fatura "
                      f"({para(sum(a['kalan'] for a in acik))} TL)",
                      "Döner sermaye alacağı kamu alacağıdır, takibi zorunludur: "
                      + _liste([f"{a['belge_no'] or '-'} {a['unvan'] or ''}" for a in acik]) + ".",
                      "Müşteriye ödeme hatırlatma yazısı gönderin. Para geldiyse 'Tahsilat gir' ile faturaya bağlayarak kaydedin.",
                      "6183 s.K.; Çalışma Yönergesi")
        nosuz = d.q("SELECT id FROM fatura WHERE iptal = 0 AND COALESCE(TRIM(belge_no), '') = '' AND substr(tarih, 1, 4) = ?", (y,))
        if nosuz:
            self.ekle(UYARI, "Satış Faturaları", f"Belge numarası girilmemiş {len(nosuz)} fatura/belge",
                      "Numarasız belge, aslıyla eşleştirilemez ve denetimde bulunamaz.",
                      "Satış Faturaları ve Alış / Gider Belgeleri sayfalarında boş numaralı belgeleri açıp aslındaki numarayı yazın.")
        cift = d.q("""SELECT belge_no, COUNT(*) n FROM fatura WHERE tur = 'Satış' AND iptal = 0 AND substr(tarih, 1, 4) = ?
                      AND COALESCE(TRIM(belge_no), '') != '' GROUP BY belge_no HAVING COUNT(*) > 1""", (y,))
        if cift:
            self.ekle(HATA, "Satış Faturaları", f"Aynı numarayla birden fazla kaydedilmiş {len(cift)} satış faturası",
                      _liste([c["belge_no"] for c in cift]) + ". Satış iki kez kaydedilmiş olabilir; hasılat, KDV ve hazine payı "
                      "fazla hesaplanır.", "Mükerrer olanı 'İptal et' ile iptal edin.", "Çalışma Yönergesi md.44")
        ileri = d.deger("SELECT COUNT(*) FROM fatura WHERE iptal = 0 AND tarih > ?", (self.bugun.isoformat(),), 0)
        ileri += d.deger("SELECT COUNT(*) FROM kasa_banka WHERE tarih > ?", (self.bugun.isoformat(),), 0)
        if ileri:
            self.ekle(UYARI, "Kasa / Banka", f"İleri tarihli {ileri} kayıt",
                      "Bugünden sonraki bir tarihle girilmiş fatura veya kasa/banka kaydı var; tarih yanlış yazılmış olabilir.",
                      "Kayıtların tarihini belgenin aslıyla karşılaştırın.")

    # ------------------------------------------------------------ satın alma
    def alislar(self):
        d, y = self.d, str(self.yil)
        A = "Alış / Gider Belgeleri"
        alis = d.q("""SELECT f.*, c.unvan FROM fatura f LEFT JOIN cari c ON c.id = f.cari_id
                      WHERE f.tur = 'Alış' AND f.iptal = 0 AND substr(f.tarih, 1, 4) = ?""", (y,))
        etiket = lambda f: f"{f['belge_no'] or '-'} {f['unvan'] or ''}".strip()
        mustahsil = [etiket(f) for f in alis if (f["belge_turu"] or "").startswith("Müstahsil") and not (f["stopaj"] or 0)]
        smm = [etiket(f) for f in alis if (f["belge_turu"] or "").startswith("Serbest Meslek") and not (f["stopaj"] or 0)]
        perakende = [etiket(f) for f in alis if (f["belge_turu"] or "").startswith("Perakende") and (f["kdv"] or 0) > 0]
        usulsuz = [etiket(f) for f in alis if not (f["temin_usulu"] or "").strip()]
        limit = self.p["dogrudan_temin_buyuksehir" if self.k.get("buyuksehir") else "dogrudan_temin_diger"]
        asan = [f"{etiket(f)} ({para(f['matrah'])} TL)" for f in alis
                if f["temin_usulu"] == "Doğrudan Temin" and (f["matrah"] or 0) > limit]
        if mustahsil:
            self.ekle(HATA, A, f"Stopaj kesilmemiş {len(mustahsil)} müstahsil makbuzu",
                      "Çiftçiden alımda gelir vergisi stopajı kesilip muhtasarla ödenmelidir: " + _liste(mustahsil) + ".",
                      "Belgeyi açıp stopaj türünü (bitkisel %2 / hayvansal %1) seçin; kesilen tutarı muhtasar beyannamesine ekleyin.",
                      "GVK md.94/11; VUK md.344 (vergi ziyaı)")
        if smm:
            self.ekle(UYARI, A, f"Stopaj kesilmemiş {len(smm)} serbest meslek makbuzu",
                      "Serbest meslek ödemelerinde %20 stopaj kesilir: " + _liste(smm) + ".",
                      "Belgeyi açıp 'Serbest Meslek (%20)' stopajını seçin; saymanla kontrol edin.", "GVK md.94/2-b")
        if perakende:
            self.ekle(HATA, A, f"KDV'si indirilmiş {len(perakende)} perakende satış fişi",
                      "Perakende satış fişindeki KDV indirilemez: " + _liste(perakende) + ".",
                      "Belgeyi açıp kalemleri KDV dahil tutarla ve KDV oranı %0 olarak düzeltin.",
                      "KDV K. md.34; Çalışma Yönergesi md.46/c")
        if asan:
            self.ekle(HATA, A, f"Doğrudan temin limitini aşan {len(asan)} alım",
                      f"Limit {para(limit)} TL (KDV hariç): " + _liste(asan) + ".",
                      "Bu alımın hangi usulle yapıldığını belgeleyin; temin usulü yanlış girildiyse düzeltin. Limit üstü alımlar "
                      "ihaleyle yapılır.", "4734 s.K. md.22/d")
        if usulsuz:
            self.ekle(UYARI, A, f"Temin usulü seçilmemiş {len(usulsuz)} alış belgesi", _liste(usulsuz) + ".",
                      "Belgeyi açıp temin usulünü (ör. Doğrudan Temin) seçin; doğrudan temin dosyasını tamamlayın.")
        sinir = (self.bugun - timedelta(days=ALACAK_GUN)).isoformat()
        borc = d.q("""SELECT f.net_tutar - COALESCE((SELECT SUM(k.tutar) FROM kasa_banka k WHERE k.fatura_id = f.id), 0) kalan
                      FROM fatura f WHERE f.tur = 'Alış' AND f.iptal = 0 AND f.tarih <= ?""", (sinir,))
        borc = [b["kalan"] for b in borc if (b["kalan"] or 0) > 0.009]
        if borc:
            self.ekle(BILGI, A, f"{ALACAK_GUN} günden eski ödenmemiş {len(borc)} alış belgesi ({para(sum(borc))} TL)",
                      "Tedarikçilere borç görünüyor. Ödendiyse kaydı girilmemiş olabilir.",
                      "Ödendiyse 'Ödeme gir' ile kaydedin; ödenmediyse ödeme planını saymanla belirleyin.")

    # ------------------------------------------------------------ kasa ve banka
    def kasa(self):
        d = self.d
        bakiye: dict[str, float] = {}
        eksi: dict[str, tuple[str, float]] = {}
        for r in d.q("SELECT tarih, hesap, yon, tutar FROM kasa_banka ORDER BY tarih, id"):
            h = r["hesap"] or "Kasa (100)"
            bakiye[h] = yuvarla(bakiye.get(h, 0) + ((r["tutar"] or 0) if r["yon"] == "Giriş" else -(r["tutar"] or 0)))
            if bakiye[h] < -0.009 and h not in eksi:
                eksi[h] = (r["tarih"], bakiye[h])
        for h, (t, b) in eksi.items():
            self.ekle(HATA, "Kasa / Banka", f"{h} bakiyesi eksiye düşmüş",
                      f"{str(t)[:10]} tarihinde bakiye {para(b)} TL'ye düştü. Kasada veya bankada olmayan para harcanamaz; "
                      "genellikle bir tahsilat girilmemiş veya bir ödeme yanlış hesaptan/tarihle girilmiştir. Güncel bakiye: "
                      f"{para(bakiye[h])} TL.",
                      "Kasa / Banka sayfasında o tarihe kadarki kayıtları banka ekstresi ve kasa defteriyle karşılaştırın, eksik "
                      "tahsilatı girin veya yanlış kaydı düzeltin.", "5018 s.K. md.71")
        y = str(self.yil)
        bagsiz = d.deger("""SELECT COUNT(*) FROM kasa_banka WHERE yon = 'Giriş' AND tur = 'Tahsilat' AND fatura_id IS NULL
                            AND siparis_id IS NULL AND substr(tarih, 1, 4) = ?""", (y,), 0)
        if bagsiz:
            self.ekle(UYARI, "Kasa / Banka", f"Hangi faturaya ait olduğu belirtilmemiş {bagsiz} tahsilat",
                      "Fatura bağlanmayan tahsilatta müşterinin borcu kapanmaz ve alacaklar yanlış görünür.",
                      "Tahsilatı açıp 'Fatura / belge' ya da 'Sipariş' kutusunu doldurun.")
        hasilatsiz = d.deger("""SELECT COUNT(*) FROM kasa_banka WHERE yon = 'Giriş' AND tur IN ('Tahsilat', 'Peşinat/Avans Tahsilatı',
                                'Faiz/Diğer Gelir') AND COALESCE(hasilat_tutari, 0) = 0 AND tutar > 0
                                AND substr(tarih, 1, 4) = ?""", (y,), 0)
        if hasilatsiz:
            self.ekle(UYARI, "Kasa / Banka", f"Hasılat tutarı sıfır görünen {hasilatsiz} tahsilat",
                      "Hazine payı 'hasılat tutarı' üzerinden hesaplanır; bu kayıtlar hazine payına hiç girmiyor.",
                      "Tahsilatları açıp 'Hasılat tutarı (KDV hariç)' kutusunu kontrol edin, ardından Hazine Payı sayfasında "
                      "ilgili ayları yeniden hesaplayın.", "Muhasebat Genel Tebliği (Sıra No: 73) md.6")

    # ------------------------------------------------------------ personel ve öğrenci ödemeleri
    def odemeler(self):
        d, yil = self.d, self.yil
        bk, bp = self._bolum_kosulu("p.bolum_id")
        ok, op = self._bolum_kosulu("o.bolum_id")
        iban_yok = d.q(f"""SELECT DISTINCT p.ad_soyad FROM personel p WHERE COALESCE(TRIM(p.iban), '') = ''{bk} AND (
                              EXISTS (SELECT 1 FROM fazla_calisma f WHERE f.personel_id = p.id AND f.yil = ?)
                              OR EXISTS (SELECT 1 FROM parca_basi_satir r JOIN parca_basi b ON b.id = r.parca_basi_id
                                         WHERE r.kisi_turu = 'Personel' AND r.kisi_id = p.id AND b.yil = ?))""", (*bp, yil, yil))
        iban_yok += d.q(f"""SELECT DISTINCT o.ad_soyad FROM ogrenci o WHERE COALESCE(TRIM(o.iban), '') = ''{ok} AND EXISTS (
                              SELECT 1 FROM parca_basi_satir r JOIN parca_basi b ON b.id = r.parca_basi_id
                              WHERE r.kisi_turu = 'Öğrenci' AND r.kisi_id = o.id AND b.yil = ?)""", (*op, yil))
        if iban_yok:
            self.ekle(UYARI, "Personel", f"Ödeme alacağı hâlde IBAN'ı girilmemiş {len(iban_yok)} kişi",
                      _liste([r["ad_soyad"] for r in iban_yok]) + ". Ücret yalnız kişinin kendi adına açılmış hesaba gönderilir.",
                      "Personel ve Öğrenciler sayfalarında kişinin kendi adına açılmış IBAN'ı girin.", konu="Personel ödemeleri")
        eksik = d.q(f"""SELECT p.ad_soyad FROM personel p WHERE p.aktif = 1{bk}
                        AND (COALESCE(p.hizmet_sinifi, '') = '' OR COALESCE(p.dose_gorevi, '') = '')""", bp)
        if eksik:
            self.ekle(UYARI, "Personel", f"Hizmet sınıfı veya DÖSE görevi boş {len(eksik)} personel",
                      _liste([r["ad_soyad"] for r in eksik]) + ". Aylık ücret tavanı ve ÜTP payı bu bilgilere göre hesaplanır.",
                      "Personel kartını açıp hizmet sınıfını ve DÖSE görevini seçin.", "DÖSE Yönetmeliği md.5, md.8/5")
        yasakli = [r for r in d.q(f"""SELECT DISTINCT p.ad_soyad, p.hizmet_sinifi, p.kadro_unvani, p.dose_gorevi
                                      FROM fazla_calisma f JOIN personel p ON p.id = f.personel_id WHERE f.yil = ?{bk}""",
                                   (yil, *bp))
                   if r["hizmet_sinifi"] == "Yardımcı Hizmetler" or any(
                       s in f"{r['kadro_unvani'] or ''} {r['dose_gorevi'] or ''}".replace("Ş", "ş").lower() for s in ("şoför", "sofor"))]
        if yasakli:
            self.ekle(HATA, "Fazla Çalışma Ücreti", f"Fazla çalışma ücreti alamayacak {len(yasakli)} kişiye kayıt yapılmış",
                      _liste([r["ad_soyad"] for r in yasakli]) + ". Yardımcı hizmetler sınıfı ve şoförler döner sermayeden fazla "
                      "çalışma ücreti alamaz.", "Kaydı silin; ödeme yapıldıysa saymanla birlikte geri alınmasını sağlayın.",
                      "Bütçe Kanunu K cetveli III-3")
        cakisan = d.q(f"""SELECT DISTINCT p.ad_soyad FROM fazla_calisma f JOIN personel p ON p.id = f.personel_id
                          JOIN parca_basi b ON b.siparis_id = f.siparis_id
                          JOIN parca_basi_satir r ON r.parca_basi_id = b.id AND r.kisi_turu = 'Personel' AND r.kisi_id = f.personel_id
                          WHERE f.yil = ?{bk}""", (yil, *bp))
        if cakisan:
            self.ekle(HATA, "Fazla Çalışma Ücreti", f"Aynı iş için hem parça başı hem fazla çalışma alan {len(cakisan)} kişi",
                      _liste([r["ad_soyad"] for r in cakisan]) + ".",
                      "Bu kişilerin aynı siparişteki kayıtlarından birini kaldırın; fazla ödenen tutarı saymanla geri alın.",
                      "DÖSE Yönetmeliği md.8/7")
        puantajsiz = d.deger(f"""SELECT COUNT(*) FROM fazla_calisma f JOIN personel p ON p.id = f.personel_id
                                WHERE f.yil = ? AND COALESCE(f.puantaj, '') IN ('', '{{}}'){bk}""", (yil, *bp), 0)
        if puantajsiz:
            self.ekle(UYARI, "Fazla Çalışma Ücreti", f"Günlük puantajı girilmemiş {puantajsiz} fazla çalışma kaydı",
                      "Hangi gün kaç saat çalışıldığı belli değil; öğretim günü 3, tatil 8 saat sınırı ve Pazar/bayram yasağı "
                      "denetlenemiyor. Denetimde mesai çizelgesi istenir.",
                      "Kaydı açıp 'Günlük puantaj…' ile çalışılan günleri girin.", "Çalışma Yönergesi md.9/c-e")
        ay_basi = (self.bugun.year, self.bugun.month)
        taslak_fc = [r for r in d.q(f"""SELECT f.ay, p.ad_soyad FROM fazla_calisma f JOIN personel p ON p.id = f.personel_id
                                       WHERE f.yil = ? AND COALESCE(f.durum, 'Taslak') != 'Onaylandı'{bk}""", (yil, *bp))
                     if (yil, r["ay"]) < ay_basi]
        if taslak_fc:
            self.ekle(UYARI, "Fazla Çalışma Ücreti", f"Ayı geçtiği hâlde onaylanmamış {len(taslak_fc)} fazla çalışma kaydı",
                      _liste([f"{r['ad_soyad']} ({M.AYLAR[r['ay'] - 1]})" for r in taslak_fc]) + ". Ücretler izleyen ayın 10'una "
                      "kadar ödenmelidir.", "Kayıtları onaya gönderin; onay bekleyenler 'Onay Bekleyenler' sayfasındadır.",
                      "Çalışma Yönergesi md.9/b")
        sk, sp = self._bolum_kosulu("s.bolum_id")
        taslak_pb = [r for r in d.q(f"""SELECT b.ay, s.siparis_no FROM parca_basi b LEFT JOIN siparis s ON s.id = b.siparis_id
                                       WHERE b.yil = ? AND COALESCE(b.durum, 'Taslak') != 'Onaylandı'{sk}""", (yil, *sp))
                     if (yil, r["ay"]) < ay_basi]
        if taslak_pb:
            self.ekle(UYARI, "Parça Başı Ücret", f"Ayı geçtiği hâlde onaylanmamış {len(taslak_pb)} parça başı bordrosu",
                      _liste([f"{r['siparis_no'] or '-'} ({M.AYLAR[r['ay'] - 1]})" for r in taslak_pb]) + ". Öğrenci ücretleri "
                      "izleyen ayın 10'una kadar ödenmelidir.", "Bordroları kontrol edip onaya gönderin.",
                      "Çalışma Yönergesi md.42/c")
        muvafakatsiz = d.q(f"""SELECT DISTINCT o.ad_soyad FROM parca_basi_satir r JOIN parca_basi b ON b.id = r.parca_basi_id
                               JOIN ogrenci o ON o.id = r.kisi_id WHERE r.kisi_turu = 'Öğrenci' AND b.yil = ?
                               AND COALESCE(o.veli_muvafakat, 0) = 0{ok}""", (yil, *op))
        if muvafakatsiz:
            self.ekle(HATA, "Öğrenciler", f"Veli muvafakatnamesi olmadan ücret bordrosuna girmiş {len(muvafakatsiz)} öğrenci",
                      _liste([r["ad_soyad"] for r in muvafakatsiz]) + ".",
                      "Muvafakatnameyi hemen imzalatıp öğrenci kartına işleyin; alınamıyorsa öğrenciyi bordrodan çıkarın.",
                      "DÖSE Yönetmeliği md.8/1")

    # ------------------------------------------------------------ öğrenciler
    def ogrenciler(self):
        d = self.d
        sk, sp = self._bolum_kosulu("s.bolum_id")
        aktif = d.q(f"""SELECT DISTINCT o.ad_soyad, s.siparis_no FROM siparis_gorevli g JOIN ogrenci o ON o.id = g.kisi_id
                        JOIN siparis s ON s.id = g.siparis_id WHERE g.kisi_turu = 'Öğrenci' AND COALESCE(o.veli_muvafakat, 0) = 0
                        AND s.durum NOT IN ('İptal', 'Kapandı'){sk}""", sp)
        if aktif:
            self.ekle(HATA, "Öğrenciler", f"Veli muvafakatnamesi olmadan işte görevlendirilmiş {len(aktif)} öğrenci",
                      _liste([f"{r['ad_soyad']} ({r['siparis_no']})" for r in aktif]) + ".",
                      "Resmi Yazılar / Belgeler sayfasından muvafakatnameyi alıp veliye imzalatın, öğrenci kartında "
                      "'veli muvafakat' kutusunu işaretleyin. İmza gelene kadar öğrenciyi çalıştırmayın.", "DÖSE Yönetmeliği md.8/1")
        ok, op = self._bolum_kosulu("o.bolum_id")
        tarihsiz = d.deger(f"""SELECT COUNT(*) FROM ogrenci o WHERE o.aktif = 1 AND o.veli_muvafakat = 1
                              AND COALESCE(o.muvafakat_tarihi, '') = ''{ok}""", op, 0)
        if tarihsiz:
            self.ekle(BILGI, "Öğrenciler", f"Muvafakat tarihi girilmemiş {tarihsiz} öğrenci",
                      "Muvafakatnamenin işe başlamadan önce alındığı denetimde tarihle gösterilir.",
                      "Öğrenci kartında muvafakatname tarihini girin.")

    # ------------------------------------------------------------ idari masraf karşılığı
    def idari_masraf(self):
        if self.yil > self.bugun.year:
            return
        son_ay = 12 if self.yil < self.bugun.year else self.bugun.month
        asim = [r for r in idari_masraf_karsiligi(self.d, self.yil)[:son_ay] if r["durum"] == "KARŞILIK AŞILDI"]
        if asim:
            r = asim[-1]
            self.ekle(HATA, "Raporlar", "İdari masraflar faaliyet gideri karşılığını aşmış",
                      f"{_liste([a['ay'] for a in asim])} aylarında genel giderler satışlardan ayrılan faaliyet gideri payından "
                      f"fazla (son durum {r['ay']}: {para(r['kalan'])} TL). Karşılıkta para yoksa harcama yapılamaz.",
                      "Zorunlu olmayan genel giderleri erteleyin; Raporlar sayfasında 'İdari masraf karşılığı' raporunu izleyin.",
                      "Çalışma Yönergesi md.11")

    # ------------------------------------------------------------ gösterge uyarıları
    def gosterge_uyarilari(self):
        kendi = {"Siparişler / İş Emirleri", "Öğrenciler"}
        for metin, seviye, sayfa in gosterge.uyarilar(self.yil):
            # yaklaşan son gün hatırlatmaları 'Bugün Ne Yapmalıyım?' takviminde ayrıca gösterilir
            if sayfa in kendi or "gün kaldı)" in metin:
                continue
            self.ekle(seviye, sayfa, metin, "", SAYFA_COZUMU.get(sayfa or "", f"'{sayfa}' sayfasını açıp işlemi tamamlayın."
                                                                 if sayfa else ""))

    def calistir(self) -> list[Bulgu]:
        for adim in (self.kurum_ve_sistem, self.gosterge_uyarilari, self.siparisler, self.satislar, self.alislar, self.kasa,
                     self.odemeler, self.ogrenciler, self.idari_masraf):
            try:
                adim()
            except Exception as e:  # tek bir denetimin hatası bütün raporu engellemesin
                self.ekle(BILGI, None, f"Bir denetim adımı çalıştırılamadı ({adim.__name__})", str(e), konu="Genel")
        return sorted(self.bulgular, key=lambda b: (SEVIYE_SIRA[b.seviye], b.konu))


def denetle(yil: int, bolum_id: int | None = None, bugun: date | None = None) -> list[Bulgu]:
    return _Denetci(yil, bolum_id, bugun or date.today()).calistir()


def puan(bulgular: list[Bulgu]) -> int:
    ceza = sum(10 if b.seviye == HATA else 3 if b.seviye == UYARI else 0 for b in bulgular)
    return max(0, 100 - ceza)


def puan_durumu(p: int) -> tuple[str, str]:
    """(metin, renk)"""
    if p >= 85:
        return "İyi", "#1b5e20"
    if p >= 60:
        return "Dikkat gerekiyor", "#8a5a00"
    return "Riskli", "#b00020"


def ilgili_mi(b: Bulgu, rol: str) -> bool:
    """Bulgu bu rolün yapılacaklar listesine girer mi? Müdür ve denetçi bütün önemli bulguları görür."""
    if rol in (M.ROL_MUDUR, M.ROL_IZLEYICI) and b.seviye != BILGI:
        return True
    if not b.sayfa:
        return rol in (M.ROL_SAYMAN, M.ROL_SISTEM, M.ROL_MUDUR)
    return yetki.sayfa_yetkisi(rol, b.sayfa) == "y"


def yapilacaklar(yil: int, rol: str, bolum_id: int | None = None, bugun: date | None = None) -> list[Bulgu]:
    return [b for b in denetle(yil, bolum_id, bugun) if ilgili_mi(b, rol)]


def sure_tamam(s: kilavuz.Sure) -> bool:
    """Kayıtlardan işin yapıldığı anlaşılabiliyorsa True (beyannameler program dışında verildiği için hep gösterilir)."""
    d = al()
    if not s.donem:
        return False
    y, a = s.donem
    if s.kod == "hazine":
        h = d.q1("SELECT id FROM hazine_payi WHERE yil = ? AND ay = ?", (y, a))
        return bool(h and d.q1("SELECT 1 x FROM kasa_banka WHERE kaynak = 'HazinePayi' AND kaynak_id = ?", (h["id"],)))
    if s.kod == "ucret":
        fc_var = d.deger("SELECT COUNT(*) FROM fazla_calisma WHERE yil = ? AND ay = ?", (y, a), 0)
        fc_odendi = d.q1("SELECT 1 x FROM kasa_banka WHERE kaynak = 'FazlaCalisma' AND kaynak_id = ?", (y * 100 + a,))
        pb_odenmemis = d.deger("""SELECT COUNT(*) FROM parca_basi b WHERE b.yil = ? AND b.ay = ? AND NOT EXISTS
                                  (SELECT 1 FROM kasa_banka k WHERE k.kaynak = 'ParcaBasi' AND k.kaynak_id = b.id)""", (y, a), 0)
        return (not fc_var or bool(fc_odendi)) and not pb_odenmemis
    if s.kod in ("shcek", "merkez"):
        kaynak = "SHCEK" if s.kod == "shcek" else "MerkezKar"
        return bool(d.q1("SELECT 1 x FROM kasa_banka WHERE kaynak = ? AND kaynak_id = ?", (kaynak, y)))
    if s.kod == "parametre":
        return bool(d.deger("SELECT COUNT(*) FROM parametre WHERE yil = ?", (y,), 0))
    return False


def rol_sureleri(rol: str, bugun: date | None = None, gun: int = 40) -> list[kilavuz.Sure]:
    """Rolü ilgilendiren, henüz yapıldığı görülmeyen yaklaşan yasal son tarihler."""
    return [s for s in kilavuz.yaklasan_sureler(bugun, gun)
            if (rol in s.roller or rol in (M.ROL_SISTEM, M.ROL_IZLEYICI)) and not sure_tamam(s)]
