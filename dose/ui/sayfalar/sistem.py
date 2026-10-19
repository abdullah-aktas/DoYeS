"""Kullanıcı yönetimi, rol / yetki tablosu, onay akışı ayarı, yedekleme / geri yükleme ve işlem kaydı."""
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QTabWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ... import izleme, mevzuat, onay, yetki
from ...db import sifre_hashle
from ...yollar import CIKTILAR, VERI, VERITABANI, YEDEKLER
from ..ortak import (Alan, FormDialog, Kolon, Oturum, SecimKutusu, TarihKutusu, VeriTablosu, baslik_etiketi, bilgi, buton,
                     db, hata, soru, tablo_excele, uyari, yetki_kontrol)


class IslemAyrintiDialog(QDialog):
    def __init__(self, parent, r: dict):
        super().__init__(parent)
        self.setWindowTitle("İşlem ayrıntısı")
        self.resize(760, 520)
        lay = QVBoxLayout(self)
        bilgi_satiri = (f"<b>{r.get('zaman') or ''}</b> &nbsp; {r.get('kim') or ''}"
                        + (f" ({r['rol']})" if r.get("rol") else "")
                        + f"<br>İşlem: <b>{r.get('islem') or ''}</b> &nbsp; {r.get('kayit_turu') or ''}"
                        + (f" #{r['kayit_id']}" if r.get("kayit_id") is not None else "")
                        + f"<br>Kaynak: {r.get('istemci') or '-'} &nbsp; Bilgisayar/cihaz: {r.get('bilgisayar') or '-'}"
                        + (f"<br>Açıklama: {r['detay']}" if r.get("detay") else ""))
        lay.addWidget(QLabel(bilgi_satiri))
        d = izleme.degisiklikler(r)
        t = QTableWidget(len(d), 3)
        t.setHorizontalHeaderLabels(["Alan", "Eski değer", "Yeni değer"])
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        for i, satir in enumerate(d):
            for j, v in enumerate(satir):
                t.setItem(i, j, QTableWidgetItem(v))
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(t)
        lay.addWidget(buton("Kapat", self.accept))


def _sifre_kontrol(s):
    if not s or len(s) < 6:
        return "Şifre en az 6 karakter olmalıdır."
    return None


def _personeller():
    return [(r["id"], r["ad_soyad"]) for r in db().q("SELECT id, ad_soyad FROM personel WHERE aktif = 1 ORDER BY ad_soyad")]


def _bolumler():
    return [(r["id"], r["ad"]) for r in db().q("SELECT id, ad FROM bolum WHERE aktif = 1 ORDER BY ad")]


def _rol_ipucu():
    return "\n".join(f"{r}: {yetki.ROL_ACIKLAMALARI[r]}" for r in mevzuat.ROLLER)


class YetkiTablosuDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Rollere göre sayfa yetkileri")
        self.resize(1100, 720)
        lay = QVBoxLayout(self)
        n = QLabel("✎ = görür ve kayıt yapar, 👁 = yalnız görür, boş = menüde görünmez. Alan şefi ve öğretmen yalnızca kendi "
                   "bölümünün kayıtlarını görür; öğretmen fazla çalışma ve parça başı bordrosunda yalnız kendi satırını görür.")
        n.setWordWrap(True)
        lay.addWidget(n)
        roller = mevzuat.ROLLER
        t = QTableWidget(len(yetki.SAYFA_YETKI), len(roller))
        t.setHorizontalHeaderLabels([r.replace(" (", "\n(") for r in roller])
        t.setVerticalHeaderLabels(list(yetki.SAYFA_YETKI))
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        for i, sayfa in enumerate(yetki.SAYFA_YETKI):
            for j, rol in enumerate(roller):
                y = yetki.sayfa_yetkisi(rol, sayfa)
                it = QTableWidgetItem({"y": "✎", "g": "👁"}.get(y, ""))
                it.setTextAlignment(Qt.AlignCenter)
                t.setItem(i, j, it)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(t)
        akis = QLabel("<b>Onay akışları</b> (etkinse):<br>" + "<br>".join(
            f"{tur}: hazırlayan → " + " → ".join(a for a, _ in asamalar) for tur, asamalar in yetki.AKISLAR.items()) +
            "<br>Hazırlayanın kendi rolüne ait aşama kendiliğinden geçilir; o rolde aktif kullanıcı yoksa aşama atlanır ve kayda geçer.")
        akis.setWordWrap(True)
        lay.addWidget(akis)


class KullaniciSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "Kullanıcılar ve Roller",
            "Her kullanıcıya bir rol verilir; rol, menüde görünen sayfaları ve onay aşamalarındaki imza yetkisini belirler. Alan şefi "
            "ve öğretmen kullanıcıları personel kaydına ve bölüme bağlanmalıdır. Şifreler PBKDF2 ile şifrelenmiş olarak saklanır."))
        u = QHBoxLayout()
        u.addWidget(buton("＋ Yeni kullanıcı", self.yeni, "birincil"))
        u.addWidget(buton("Düzenle", self.duzenle))
        u.addWidget(buton("Şifre sıfırla", self.sifirla))
        u.addWidget(buton("Sil", self.sil, "tehlike"))
        u.addWidget(buton("Rol / yetki tablosu", lambda: YetkiTablosuDialog(self).exec()))
        u.addStretch()
        self.c_akis = QCheckBox("Onay akışı etkin (öğretmen/şef → teknik müdür yardımcısı → müdür)")
        self.c_akis.setToolTip("Kapalıyken yetkili kullanıcı belgeleri tek adımda onaylar. Açıkken sipariş, parça başı bordrosu, "
                               "fazla çalışma ve yıl sonu dağıtımı sırasıyla ilgili rollerin onayından geçer.")
        self.c_akis.toggled.connect(self._akis_degisti)
        u.addWidget(self.c_akis)
        lay.addLayout(u)
        self.tablo = VeriTablosu()
        lay.addWidget(self.tablo)
        self.yenile()

    def yenile(self):
        self.c_akis.blockSignals(True)
        self.c_akis.setChecked(onay.akis_acik())
        self.c_akis.setEnabled(Oturum.yazabilir(self))
        self.c_akis.blockSignals(False)
        self.tablo.doldur(
            [Kolon("kullanici_adi", "Kullanıcı adı"), Kolon("ad_soyad", "Ad soyad"), Kolon("rol", "Rol"),
             Kolon("personel_ad", "Bağlı personel"), Kolon("bolum_ad", "Bölüm"), Kolon("aktif", "Aktif", "bool"),
             Kolon("sifre_degismeli", "Şifre değişmeli", "bool"), Kolon("son_giris", "Son giriş")],
            db().q("SELECT k.id, k.kullanici_adi, k.ad_soyad, k.rol, k.personel_id, k.bolum_id, k.aktif, k.sifre_degismeli, "
                   "k.son_giris, p.ad_soyad AS personel_ad, COALESCE(b.ad, pb.ad) AS bolum_ad "
                   "FROM kullanici k LEFT JOIN personel p ON p.id = k.personel_id LEFT JOIN bolum b ON b.id = k.bolum_id "
                   "LEFT JOIN bolum pb ON pb.id = p.bolum_id ORDER BY k.kullanici_adi"))

    def _akis_degisti(self, acik):
        if not yetki_kontrol(self, yonetici=True):
            self.yenile()
            return
        if not acik and onay.bekleyenler():
            if not soru(self, "Onay sürecinde bekleyen belgeler var. Akış kapatılırsa bu belgeler yetkili kullanıcı tarafından tek "
                              "adımda onaylanabilir hâle gelir. Devam edilsin mi?"):
                self.yenile()
                return
        onay.akis_ayarla(acik)
        db().log("Onay akışı " + ("açıldı" if acik else "kapatıldı"))
        bilgi(self, "Onay akışı " + ("AÇILDI. Belgeler artık rol sırasıyla onaylanacak; bekleyen işler "
                                     "'Onay Bekleyenler' sayfasında görünür." if acik else "KAPATILDI."))

    def _yonetici_sayisi(self, haric=None):
        return db().deger("SELECT COUNT(*) FROM kullanici WHERE rol = ? AND aktif = 1 AND id != ?",
                          (mevzuat.ROL_SISTEM, haric or 0), 0)

    def _alanlar(self, yeni: bool):
        a = []
        if yeni:
            a.append(Alan("kullanici_adi", "Kullanıcı adı", zorunlu=True))
        a += [Alan("ad_soyad", "Ad soyad", zorunlu=True),
              Alan("rol", "Rol", "secim", True, mevzuat.ROLLER, mevzuat.ROL_MEMUR, ipucu=_rol_ipucu()),
              Alan("personel_id", "Bağlı personel", "fk", secenekler=_personeller,
                   ipucu="Öğretmen ve alan şefi için zorunlu. Fazla çalışma ve bordrolarda kişinin kendi kayıtlarını belirler."),
              Alan("bolum_id", "Bölüm / alan", "fk", secenekler=_bolumler,
                   ipucu="Boş bırakılırsa personel kartındaki bölüm kullanılır.")]
        if yeni:
            a.append(Alan("sifre", "Geçici şifre", zorunlu=True, dogrula=_sifre_kontrol))
        else:
            a.append(Alan("aktif", "Aktif", "bool"))
        return a

    @staticmethod
    def _rol_dogrula(v) -> list[str]:
        h = []
        if v["rol"] == mevzuat.ROL_OGRETMEN and not v.get("personel_id"):
            h.append("Öğretmen kullanıcısı bir personel kaydına bağlanmalıdır.")
        if yetki.bolum_kisitli(v["rol"]) and not onay.kullanici_bolumu(v):
            h.append(f"{v['rol']} için bölüm seçilmeli veya personel kartında bölüm tanımlı olmalıdır.")
        return h

    def yeni(self):
        if not yetki_kontrol(self, yonetici=True):
            return

        def dogrula(v):
            h = self._rol_dogrula(v)
            if db().q1("SELECT 1 FROM kullanici WHERE kullanici_adi = ?", (v["kullanici_adi"],)):
                h.append("Bu kullanıcı adı zaten var.")
            return h
        d = FormDialog(self, "Yeni kullanıcı", self._alanlar(True), None, dogrula,
                       "Kullanıcı ilk girişte şifresini değiştirmek zorunda olacaktır.\n\n" + _rol_ipucu())
        if d.exec():
            v = d.degerler()
            h, tuz = sifre_hashle(v.pop("sifre"))
            db().ekle("kullanici", dict(v, sifre_hash=h, tuz=tuz, sifre_degismeli=1, aktif=1))
            self.yenile()

    def duzenle(self):
        s = self.tablo.secili()
        if not s or not yetki_kontrol(self, yonetici=True):
            return

        def dogrula(v):
            h = self._rol_dogrula(v)
            if s["rol"] == mevzuat.ROL_SISTEM and (v["rol"] != mevzuat.ROL_SISTEM or not v["aktif"]) \
                    and not self._yonetici_sayisi(s["id"]):
                h.append("Sistemde en az bir aktif Sistem Yöneticisi kalmalıdır.")
            return h
        d = FormDialog(self, f"Kullanıcı düzenle - {s['kullanici_adi']}", self._alanlar(False), s, dogrula, _rol_ipucu())
        if d.exec():
            db().guncelle("kullanici", s["id"], d.degerler())
            if s["id"] == Oturum.kullanici.get("id"):
                Oturum.kullanici.update(d.degerler())
            self.yenile()

    def sifirla(self):
        s = self.tablo.secili()
        if not s or not yetki_kontrol(self, yonetici=True):
            return
        d = FormDialog(self, f"Şifre sıfırla - {s['kullanici_adi']}", [Alan("sifre", "Yeni geçici şifre", zorunlu=True, dogrula=_sifre_kontrol)])
        if d.exec():
            h, tuz = sifre_hashle(d.degerler()["sifre"])
            db().guncelle("kullanici", s["id"], {"sifre_hash": h, "tuz": tuz, "sifre_degismeli": 1})
            bilgi(self, "Şifre sıfırlandı. Kullanıcı ilk girişte şifresini değiştirecek.")
            self.yenile()

    def sil(self):
        s = self.tablo.secili()
        if not s or not yetki_kontrol(self, yonetici=True):
            return
        if s["id"] == Oturum.kullanici.get("id"):
            uyari(self, "Kendi hesabınızı silemezsiniz.")
            return
        if s["rol"] == mevzuat.ROL_SISTEM and not self._yonetici_sayisi(s["id"]):
            uyari(self, "Son Sistem Yöneticisi silinemez.")
            return
        if db().q1("SELECT 1 FROM onay_kaydi WHERE kullanici = ?", (s["kullanici_adi"],)):
            uyari(self, "Bu kullanıcının onay kayıtları bulunduğundan silinemez; iz kaybolmaması için 'Aktif' işaretini kaldırınız.")
            return
        if soru(self, f"{s['kullanici_adi']} kullanıcısı silinsin mi?"):
            db().sil("kullanici", s["id"])
            self.yenile()


class YedekSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        if db().sunucu_mu:
            aciklama = (f"{db().aciklama()}. Veriler merkezi sunucuda tutulur; 'Şimdi yedekle' sunucudaki verinin tam kopyasını bu "
                        "bilgisayara SQLite dosyası olarak indirir. Sunucu tarafında da düzenli yedek (pg_dump) alınmalıdır.")
        else:
            aciklama = (f"{db().aciklama()}. Yedekleri düzenli olarak harici bir diske veya ağ klasörüne de kopyalayınız. "
                        "Uygulama kapanırken günlük otomatik yedek alınır.")
        lay.addWidget(baslik_etiketi("Yedekleme ve İşlem Kaydı", aciklama))
        self.sekme = QTabWidget()
        lay.addWidget(self.sekme)

        w = QWidget()
        v = QVBoxLayout(w)
        u = QHBoxLayout()
        u.addWidget(buton("Şimdi yedekle", self.yedekle, "birincil"))
        u.addWidget(buton("Farklı konuma yedekle", self.farkli_yedekle))
        u.addWidget(buton("Seçili yedekten geri yükle", self.geri_yukle, "tehlike"))
        u.addWidget(buton("Dosyadan geri yükle", self.dosyadan_geri_yukle, "tehlike"))
        if db().sunucu_mu:
            u.addWidget(buton("Bu bilgisayardaki yerel verileri sunucuya aktar", self.sunucuya_aktar, "tehlike"))
        u.addWidget(buton("Yedek klasörünü aç", lambda: os.startfile(str(YEDEKLER))))
        u.addWidget(buton("Çıktı klasörünü aç", lambda: os.startfile(str(CIKTILAR))))
        u.addStretch()
        v.addLayout(u)
        self.t_yedek = VeriTablosu()
        v.addWidget(self.t_yedek)
        self.sekme.addTab(w, "Yedekler")

        w2 = QWidget()
        v2 = QVBoxLayout(w2)
        n = QLabel("Her ekleme, değişiklik, silme, onay ve oturum açma; kullanıcının adı, rolü, bilgisayarı, masaüstü/mobil "
                   "bilgisi ve sunucu saatiyle kaydedilir. Değişikliklerde alanların eski ve yeni değerleri tutulur. "
                   "Ayrıntı için satıra çift tıklayınız.")
        n.setWordWrap(True)
        v2.addWidget(n)
        u2 = QHBoxLayout()
        self.ara = QLineEdit()
        self.ara.setPlaceholderText("Ara: kullanıcı, rol, işlem, belge no, değer...")
        self.ara.returnPressed.connect(self.log_yenile)
        u2.addWidget(self.ara, 2)
        self.f_kullanici = SecimKutusu(bos=True)
        self.f_kullanici.setToolTip("Kullanıcı")
        u2.addWidget(QLabel("Kullanıcı:"))
        u2.addWidget(self.f_kullanici, 1)
        self.f_istemci = SecimKutusu(secenekler=["Masaüstü", "Mobil"], bos=True)
        u2.addWidget(QLabel("Kaynak:"))
        u2.addWidget(self.f_istemci)
        self.f_bas = TarihKutusu(bos_olabilir=True)
        self.f_bit = TarihKutusu(bos_olabilir=True)
        self.f_bas.ayarla(None)
        self.f_bit.ayarla(None)
        u2.addWidget(QLabel("Tarih:"))
        u2.addWidget(self.f_bas)
        u2.addWidget(QLabel("–"))
        u2.addWidget(self.f_bit)
        u2.addWidget(buton("Süz", self.log_yenile, "birincil"))
        u2.addWidget(buton("Excel'e aktar", lambda: tablo_excele(self, self.t_log, "Islem_kaydi", "İşlem Kaydı")))
        v2.addLayout(u2)
        self.t_log = VeriTablosu()
        self.t_log.satirCiftTiklandi.connect(lambda r: IslemAyrintiDialog(self, r).exec())
        v2.addWidget(self.t_log)
        self.l_log = QLabel()
        v2.addWidget(self.l_log)
        self.sekme.addTab(w2, "İşlem kaydı (kim, ne zaman, ne yaptı)")
        self.yenile()

    def yenile(self):
        dosyalar = sorted(YEDEKLER.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        from datetime import datetime
        self.t_yedek.doldur([Kolon("ad", "Dosya"), Kolon("tarih", "Tarih"), Kolon("boyut", "Boyut (KB)", "sayi")],
                            [{"id": i, "ad": p.name, "yol": str(p), "tarih": datetime.fromtimestamp(p.stat().st_mtime).strftime("%d.%m.%Y %H:%M"),
                              "boyut": round(p.stat().st_size / 1024)} for i, p in enumerate(dosyalar)])
        self.log_yenile()

    def log_yenile(self):
        self.f_kullanici.doldur(izleme.kullanicilar(db()))
        satirlar = izleme.kayitlar(db(), self.ara.text().strip(), self.f_kullanici.deger(), self.f_bas.deger(),
                                   self.f_bit.deger(), self.f_istemci.deger())
        self.t_log.doldur([Kolon("zaman", "Zaman", genislik=130), Kolon("kim", "Kullanıcı"), Kolon("rol", "Rol"),
                           Kolon("islem", "İşlem"), Kolon("kayit_turu", "Kayıt türü"), Kolon("kayit_id", "Kayıt no"),
                           Kolon("ozet", "Yapılan değişiklik", genislik=420), Kolon("istemci", "Kaynak"),
                           Kolon("bilgisayar", "Bilgisayar / cihaz")], satirlar)
        self.l_log.setText(f"{len(satirlar)} işlem" + (" (en yeni 2000 işlem gösteriliyor; süzgeç kullanınız)"
                                                      if len(satirlar) >= 2000 else ""))

    def yedekle(self):
        try:
            yol = db().yedekle()
        except Exception as e:
            hata(self, f"Yedek alınamadı:\n{e}")
            return
        bilgi(self, f"Yedek alındı:\n{yol}")
        self.yenile()

    def farkli_yedekle(self):
        from datetime import datetime
        yol, _ = QFileDialog.getSaveFileName(self, "Yedek dosyası", f"dose_yedek_{datetime.now():%Y%m%d_%H%M}.db", "Veritabanı (*.db)")
        if yol:
            try:
                db().yedekle(Path(yol))
            except Exception as e:
                hata(self, f"Yedek alınamadı:\n{e}")
                return
            bilgi(self, f"Yedek alındı:\n{yol}")

    def _geri_yukle(self, yol, metin=None):
        if not yetki_kontrol(self, yonetici=True):
            return
        if not soru(self, metin or f"Mevcut veriler, seçilen yedekteki verilerle değiştirilecek:\n{yol}\n\nİşlemden önce mevcut "
                                   "verinin otomatik yedeği alınır. Devam edilsin mi?"):
            return
        try:
            db().geri_yukle(Path(yol))
        except Exception as e:
            hata(self, f"İşlem başarısız:\n{e}")
            return
        bilgi(self, "İşlem tamamlandı. Açık sayfaların güncel veriyi göstermesi için uygulamayı yeniden başlatmanız önerilir.")
        self.yenile()

    def geri_yukle(self):
        s = self.t_yedek.secili()
        if s:
            self._geri_yukle(s["yol"])

    def dosyadan_geri_yukle(self):
        yol, _ = QFileDialog.getOpenFileName(self, "Yedek dosyası seç", str(VERI), "Veritabanı (*.db)")
        if yol:
            self._geri_yukle(yol)

    def sunucuya_aktar(self):
        if not VERITABANI.exists():
            uyari(self, f"Bu bilgisayarda yerel veritabanı bulunamadı:\n{VERITABANI}")
            return
        self._geri_yukle(VERITABANI, f"Bu bilgisayarda yerel modda girilmiş veriler ({VERITABANI}) sunucuya aktarılacak. SUNUCUDAKİ "
                                     "MEVCUT VERİLER SİLİNİP yerel verilerle değiştirilecektir (öncesinde sunucu verisinin yedeği bu "
                                     "bilgisayara alınır).\n\nBu işlem genellikle ilk geçişte bir kez yapılır. Devam edilsin mi?")
