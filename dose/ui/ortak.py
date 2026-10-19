"""Ortak arayüz bileşenleri: oturum, giriş kutuları, tablo, genel form ve kayıt listesi sayfası."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QDate, QItemSelectionModel, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import excel, mevzuat, yetki
from ..db import KayitCakismasi, al
from ..hesap import para, yuvarla
from ..yollar import CIKTILAR


# ---------------------------------------------------------------- oturum
SALT_OKUNURDA_ACIK = "Yedekleme / İşlem Kaydı"


def sayfa_adi(w=None) -> str | None:
    """Widget'ın bağlı olduğu menü sayfası; bulunamazsa açık olan sayfa."""
    while w is not None:
        ad = getattr(w, "sayfa_adi", None)
        if ad:
            return ad
        w = w.parentWidget() if hasattr(w, "parentWidget") else None
    return Oturum.aktif_sayfa


class Oturum:
    kullanici: dict = {}
    yil: int = date.today().year
    aktif_sayfa: str | None = None

    @classmethod
    def temizle(cls):
        """Güvenli çıkışta bellek üzerindeki oturum bilgisini siler."""
        cls.kullanici = {}
        cls.aktif_sayfa = None
        cls.yil = date.today().year

    @classmethod
    def rol(cls) -> str:
        return cls.kullanici.get("rol", mevzuat.ROL_IZLEYICI)

    @classmethod
    def sayfa_yetkisi(cls, sayfa: str | None) -> str:
        if not sayfa:
            y = "g" if cls.rol() == mevzuat.ROL_IZLEYICI else "y"
        else:
            y = yetki.sayfa_yetkisi(cls.rol(), sayfa)
        if y == "y" and sayfa != SALT_OKUNURDA_ACIK and al().salt_okunur:
            return "g"
        return y

    @classmethod
    def yazabilir(cls, w=None, sayfa: str | None = None) -> bool:
        return cls.sayfa_yetkisi(sayfa or sayfa_adi(w)) == "y"

    @classmethod
    def yonetici(cls) -> bool:
        return yetki.yonetici_mi(cls.rol())

    @classmethod
    def bolum_id(cls) -> int | None:
        """Alan şefi ve öğretmen için kayıtların sınırlandığı bölüm; diğer roller için None."""
        if not yetki.bolum_kisitli(cls.rol()):
            return None
        from ..onay import kullanici_bolumu
        return kullanici_bolumu(cls.kullanici) or -1

    @classmethod
    def personel_id(cls) -> int | None:
        return cls.kullanici.get("personel_id")

    @classmethod
    def ogretmen(cls) -> bool:
        return cls.rol() == mevzuat.ROL_OGRETMEN


def db():
    return al()


def kayit_izle(pencere: QDialog, tablo: str, kayit_id):
    """Düzenleme penceresi açık kaldığı sürece kaydı izler; kaydederken başkası değiştirmişse kayıt engellenir."""
    if kayit_id is None:
        return
    al().kayit_ac(tablo, kayit_id)
    pencere.finished.connect(lambda *_: al().kayit_birak(tablo, kayit_id))


def bugun() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------- mesajlar
def bilgi(parent, metin, baslik="Bilgi"):
    QMessageBox.information(parent, baslik, metin)


def uyari(parent, metin, baslik="Uyarı"):
    QMessageBox.warning(parent, baslik, metin)


def hata(parent, metin, baslik="Hata"):
    QMessageBox.critical(parent, baslik, metin)


def soru(parent, metin, baslik="Onay") -> bool:
    return QMessageBox.question(parent, baslik, metin, QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) == QMessageBox.Yes


def yetki_kontrol(parent, yonetici=False, sayfa: str | None = None) -> bool:
    """Kullanıcının bulunduğu (veya verilen) sayfada kayıt yetkisi; yonetici=True ise ayrıca yönetici rolü aranır."""
    ok = Oturum.yazabilir(parent, sayfa) and (not yonetici or Oturum.yonetici())
    if not ok:
        if al().salt_okunur:
            uyari(parent, "Lisans veya deneme süresi dolduğu için program salt okunur çalışıyor. Kayıtları görüntüleyebilir, "
                          "rapor alabilir ve yedekleyebilirsiniz; yeni kayıt için lisans giriniz.")
        else:
            uyari(parent, f"Bu işlem için yetkiniz bulunmuyor ({Oturum.rol()}).")
    return ok


def dosya_ac(yol):
    try:
        os.startfile(str(yol))  # type: ignore[attr-defined]
    except Exception:
        pass


def cikti_yolu(ad: str, uzanti: str = "pdf") -> Path:
    temiz = "".join(c if c.isalnum() or c in "-_ " else "_" for c in ad).strip().replace(" ", "_")
    return CIKTILAR / f"{temiz}_{datetime.now():%Y%m%d_%H%M%S}.{uzanti}"


# ---------------------------------------------------------------- giriş kutuları
class ParaKutusu(QDoubleSpinBox):
    def __init__(self, parent=None, ondalik=2, azami=1e12, onek=""):
        super().__init__(parent)
        self.setDecimals(ondalik)
        self.setRange(-azami, azami)
        self.setGroupSeparatorShown(True)
        self.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.setAlignment(Qt.AlignRight)
        if onek:
            self.setSuffix(" " + onek)
        self.setMinimumWidth(120)

    def wheelEvent(self, e):
        e.ignore()

    def deger(self) -> float:
        return yuvarla(self.value(), self.decimals())

    def ayarla(self, v):
        self.setValue(float(v or 0))


class OranKutusu(QDoubleSpinBox):
    """Yüzde olarak gösterir, oran (0-1) olarak saklar."""

    def __init__(self, parent=None, azami=100.0):
        super().__init__(parent)
        self.setDecimals(3)
        self.setRange(0, azami)
        self.setSuffix(" %")
        self.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.setAlignment(Qt.AlignRight)
        self.setMinimumWidth(90)

    def wheelEvent(self, e):
        e.ignore()

    def deger(self) -> float:
        return round(self.value() / 100.0, max(6, self.decimals() + 2))

    def ayarla(self, v):
        self.setValue(float(v or 0) * 100.0)


class TarihKutusu(QDateEdit):
    def __init__(self, parent=None, bos_olabilir=False):
        super().__init__(parent)
        self.setCalendarPopup(True)
        self.setDisplayFormat("dd.MM.yyyy")
        self.bos_olabilir = bos_olabilir
        if bos_olabilir:
            self.setSpecialValueText(" ")
            self.setMinimumDate(QDate(1900, 1, 1))
        self.setDate(QDate.currentDate())

    def wheelEvent(self, e):
        e.ignore()

    def deger(self) -> str | None:
        if self.bos_olabilir and self.date() == self.minimumDate():
            return None
        return self.date().toString("yyyy-MM-dd")

    def ayarla(self, v):
        if not v:
            self.setDate(self.minimumDate() if self.bos_olabilir else QDate.currentDate())
            return
        d = QDate.fromString(str(v)[:10], "yyyy-MM-dd")
        if d.isValid():
            self.setDate(d)


class SecimKutusu(QComboBox):
    """Görünen metin ile saklanan değeri ayrı tutan açılır liste."""

    def __init__(self, parent=None, secenekler=None, bos=False, duzenlenebilir=False):
        super().__init__(parent)
        self.setEditable(duzenlenebilir)
        self.bos = bos
        if duzenlenebilir:
            self.setInsertPolicy(QComboBox.NoInsert)
        self.doldur(secenekler or [])

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()

    def doldur(self, secenekler):
        mevcut = self.deger()
        self.blockSignals(True)
        self.clear()
        if self.bos:
            self.addItem("", None)
        for s in secenekler:
            if isinstance(s, (tuple, list)):
                self.addItem(str(s[1]), s[0])
            else:
                self.addItem(str(s), s)
        self.blockSignals(False)
        if mevcut is not None:
            self.ayarla(mevcut)

    def deger(self):
        if self.isEditable():
            i = self.findText(self.currentText())
            if i < 0:
                return self.currentText() or None
            return self.itemData(i)
        return self.currentData()

    def ayarla(self, v):
        for i in range(self.count()):
            if self.itemData(i) == v:
                self.setCurrentIndex(i)
                return
        if self.isEditable() and v is not None:
            self.setEditText(str(v))
        elif self.count():
            self.setCurrentIndex(0)


def fk_secenekleri(tablo: str, gorunen: str, kosul: str = "", sirala: str | None = None) -> list[tuple]:
    sql = f"SELECT id, {gorunen} AS ad FROM {tablo}"
    if kosul:
        sql += f" WHERE {kosul}"
    sql += f" ORDER BY {sirala or gorunen}"
    return [(r["id"], r["ad"]) for r in db().q(sql)]


# ---------------------------------------------------------------- tablo
class _SayiItem(QTableWidgetItem):
    def __lt__(self, other):
        a = self.data(Qt.UserRole + 1)
        b = other.data(Qt.UserRole + 1)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a < b
        return super().__lt__(other)


@dataclass
class Kolon:
    anahtar: str
    baslik: str
    tur: str = "metin"  # metin, para, oran, tarih, sayi, bool
    genislik: int | None = None


def bicimle(v, tur: str) -> str:
    if v is None or v == "":
        return ""
    if tur == "para":
        return para(v)
    if tur == "oran":
        return f"%{float(v) * 100:.2f}".replace(".", ",")
    if tur == "tarih":
        s = str(v)[:10]
        return f"{s[8:10]}.{s[5:7]}.{s[0:4]}" if len(s) == 10 and s[4] == "-" else s
    if tur == "bool":
        return "Evet" if v else "Hayır"
    if tur == "sayi":
        f = float(v)
        return (f"{f:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")).rstrip("0").rstrip(",") if f % 1 else f"{int(f):,}".replace(",", ".")
    return str(v)


class VeriTablosu(QTableWidget):
    satirCiftTiklandi = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kolonlar: list[Kolon] = []
        self.satirlar: list[dict] = []
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setStretchLastSection(True)
        self.setSortingEnabled(True)
        self.cellDoubleClicked.connect(self._cift)

    def _cift(self, r, _c):
        s = self.satir_verisi(r)
        if s is not None:
            self.satirCiftTiklandi.emit(s)

    def doldur(self, kolonlar: list[Kolon], satirlar: list[dict], renk: Callable[[dict], str | None] | None = None):
        secili_idler = {s.get("id") for s in self.secililer() if s and s.get("id") is not None} if self.satirlar else set()
        kaydirma = self.verticalScrollBar().value()
        self.kolonlar, self.satirlar = kolonlar, satirlar
        self.setSortingEnabled(False)
        self.clear()
        self.setColumnCount(len(kolonlar))
        self.setRowCount(len(satirlar))
        self.setHorizontalHeaderLabels([k.baslik for k in kolonlar])
        for i, s in enumerate(satirlar):
            arka = QColor(renk(s)) if renk and renk(s) else None
            for j, k in enumerate(kolonlar):
                v = s.get(k.anahtar)
                it = _SayiItem(bicimle(v, k.tur))
                it.setData(Qt.UserRole, i)
                it.setData(Qt.UserRole + 1, v if isinstance(v, (int, float)) else str(v or ""))
                if k.tur in ("para", "oran", "sayi"):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if arka:
                    it.setBackground(arka)
                self.setItem(i, j, it)
        self.setSortingEnabled(True)
        self.resizeColumnsToContents()
        for j, k in enumerate(kolonlar):
            if k.genislik:
                self.setColumnWidth(j, k.genislik)
            elif self.columnWidth(j) > 320:
                self.setColumnWidth(j, 320)
        if secili_idler:
            ilk = True
            for r in range(self.rowCount()):
                s = self.satir_verisi(r)
                if s and s.get("id") in secili_idler:
                    if ilk:
                        self.selectRow(r)
                        ilk = False
                    else:
                        self.selectionModel().select(self.model().index(r, 0),
                                                     QItemSelectionModel.Select | QItemSelectionModel.Rows)
            self.verticalScrollBar().setValue(kaydirma)

    def satir_verisi(self, gorsel_satir: int) -> dict | None:
        it = self.item(gorsel_satir, 0)
        if it is None:
            return None
        return self.satirlar[it.data(Qt.UserRole)]

    def secili(self) -> dict | None:
        r = self.currentRow()
        if r < 0 or not self.selectionModel().selectedRows():
            return None
        return self.satir_verisi(r)

    def secililer(self) -> list[dict]:
        return [self.satir_verisi(ix.row()) for ix in self.selectionModel().selectedRows()]

    def excel_satirlari(self) -> tuple[list, list]:
        basliklar = [k.baslik for k in self.kolonlar]
        satirlar = []
        for r in range(self.rowCount()):
            s = self.satir_verisi(r)
            satir = []
            for k in self.kolonlar:
                v = s.get(k.anahtar)
                if k.tur == "para" and v is not None:
                    satir.append(float(v))
                elif k.tur in ("tarih", "bool", "oran"):
                    satir.append(bicimle(v, k.tur))
                else:
                    satir.append(v)
            satirlar.append(satir)
        return basliklar, satirlar


def tablo_excele(parent, tablo: VeriTablosu, ad: str, baslik: str | None = None):
    varsayilan = str(cikti_yolu(ad, "xlsx"))
    yol, _ = QFileDialog.getSaveFileName(parent, "Excel'e aktar", varsayilan, "Excel (*.xlsx)")
    if not yol:
        return
    b, s = tablo.excel_satirlari()
    excel.disa_aktar(Path(yol), [(ad, b, s)], baslik or ad)
    if soru(parent, f"Dosya kaydedildi:\n{yol}\n\nŞimdi açılsın mı?"):
        dosya_ac(yol)


def satir_odagini_izle(tablo: QTableWidget):
    """Hücre içindeki kutuya tıklanınca o satırı geçerli satır yapar; 'Satırı sil' doğru satırı siler."""
    from PySide6.QtWidgets import QApplication

    def odak(_eski, yeni):
        try:
            vp = tablo.viewport()
        except RuntimeError:
            return
        w = yeni
        while w is not None and w.parentWidget() is not vp:
            w = w.parentWidget()
        if w is not None:
            ix = tablo.indexAt(w.geometry().center())
            if ix.isValid() and ix.row() != tablo.currentRow():
                tablo.setCurrentCell(ix.row(), ix.column())

    uygulama = QApplication.instance()
    uygulama.focusChanged.connect(odak)
    tablo.destroyed.connect(lambda *_: uygulama.focusChanged.disconnect(odak))


# ---------------------------------------------------------------- küçük bileşenler
def baslik_etiketi(metin: str, aciklama: str = "") -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    b = QLabel(metin)
    b.setObjectName("sayfaBaslik")
    lay.addWidget(b)
    if aciklama:
        a = QLabel(aciklama)
        a.setObjectName("sayfaAciklama")
        a.setWordWrap(True)
        lay.addWidget(a)
    return w


def buton(metin: str, tiklama=None, stil: str | None = None, ipucu: str = "") -> QPushButton:
    b = QPushButton(metin)
    if stil:
        b.setObjectName(stil)
    if tiklama:
        b.clicked.connect(tiklama)
    if ipucu:
        b.setToolTip(ipucu)
    return b


class MesajKutusu(QLabel):
    def __init__(self):
        super().__init__()
        self.setWordWrap(True)
        self.setTextFormat(Qt.RichText)
        self.hide()

    def goster(self, hatalar: list, uyarilar: list, ok_metni: str = ""):
        if hatalar:
            self.setObjectName("hataKutusu")
            self.setText("<br>".join("⛔ " + h for h in hatalar + uyarilar))
        elif uyarilar:
            self.setObjectName("uyariKutusu")
            self.setText("<br>".join("⚠ " + u for u in uyarilar))
        elif ok_metni:
            self.setObjectName("okKutusu")
            self.setText("✔ " + ok_metni)
        else:
            self.hide()
            return
        self.style().unpolish(self)
        self.style().polish(self)
        self.show()


class Kart(QFrame):
    def __init__(self, baslik: str, deger: str = "-", alt: str = ""):
        super().__init__()
        self.setObjectName("kart")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self.b = QLabel(baslik)
        self.b.setObjectName("kartBaslik")
        self.d = QLabel(deger)
        self.d.setObjectName("kartDeger")
        self.a = QLabel(alt)
        self.a.setObjectName("kartBaslik")
        self.a.setWordWrap(True)
        lay.addWidget(self.b)
        lay.addWidget(self.d)
        lay.addWidget(self.a)

    def ayarla(self, deger: str, alt: str | None = None):
        self.d.setText(deger)
        if alt is not None:
            self.a.setText(alt)


# ---------------------------------------------------------------- genel form
@dataclass
class Alan:
    ad: str
    etiket: str
    tur: str = "metin"  # metin, cokmetin, tamsayi, ondalik, para, oran, tarih, secim, fk, bool
    zorunlu: bool = False
    secenekler: Any = None  # liste ya da çağrılabilir
    varsayilan: Any = None
    dogrula: Callable[[Any], str | None] | None = None
    tabloda: bool = True
    ipucu: str = ""
    salt_okunur: bool = False
    duzenlenebilir: bool = False


def alan_kutusu(a: Alan) -> QWidget:
    if a.tur == "cokmetin":
        w = QPlainTextEdit()
        w.setMaximumHeight(80)
    elif a.tur == "tamsayi":
        w = QSpinBox()
        w.setRange(-10**9, 10**9)
        w.setButtonSymbols(QSpinBox.NoButtons)
    elif a.tur == "ondalik":
        w = ParaKutusu(ondalik=3)
    elif a.tur == "para":
        w = ParaKutusu()
    elif a.tur == "oran":
        w = OranKutusu()
    elif a.tur == "tarih":
        w = TarihKutusu(bos_olabilir=not a.zorunlu)
    elif a.tur in ("secim", "fk"):
        secenek = a.secenekler() if callable(a.secenekler) else (a.secenekler or [])
        w = SecimKutusu(secenekler=secenek, bos=not a.zorunlu or a.tur == "fk", duzenlenebilir=a.duzenlenebilir)
    elif a.tur == "bool":
        w = QCheckBox()
    else:
        w = QLineEdit()
    if a.ipucu:
        w.setToolTip(a.ipucu)
    if a.salt_okunur:
        w.setEnabled(False)
    return w


def kutu_deger(w: QWidget, a: Alan):
    if isinstance(w, QPlainTextEdit):
        return w.toPlainText().strip() or None
    if isinstance(w, QSpinBox):
        return w.value()
    if isinstance(w, (ParaKutusu, OranKutusu, TarihKutusu, SecimKutusu)):
        return w.deger()
    if isinstance(w, QCheckBox):
        return 1 if w.isChecked() else 0
    return w.text().strip() or None


def kutu_ayarla(w: QWidget, v):
    if isinstance(w, QPlainTextEdit):
        w.setPlainText(v or "")
    elif isinstance(w, QSpinBox):
        w.setValue(int(v or 0))
    elif isinstance(w, (ParaKutusu, OranKutusu, TarihKutusu, SecimKutusu)):
        w.ayarla(v)
    elif isinstance(w, QCheckBox):
        w.setChecked(bool(v))
    else:
        w.setText("" if v is None else str(v))


class FormDialog(QDialog):
    def __init__(self, parent, baslik: str, alanlar: list[Alan], kayit: dict | None = None,
                 on_dogrula: Callable[[dict], list[str]] | None = None, not_metni: str = ""):
        super().__init__(parent)
        self.setWindowTitle(baslik)
        self.alanlar = alanlar
        self.on_dogrula = on_dogrula
        self.kutular: dict[str, QWidget] = {}
        self.setMinimumWidth(520)
        ana = QVBoxLayout(self)
        if not_metni:
            n = QLabel(not_metni)
            n.setWordWrap(True)
            n.setObjectName("uyariKutusu")
            ana.addWidget(n)
        alan_w = QWidget()
        form = QFormLayout(alan_w)
        form.setLabelAlignment(Qt.AlignRight)
        for a in alanlar:
            w = alan_kutusu(a)
            self.kutular[a.ad] = w
            deger = a.varsayilan if kayit is None else kayit.get(a.ad)
            kutu_ayarla(w, deger)
            form.addRow(a.etiket + (" *" if a.zorunlu else "") + ":", w)
        if len(alanlar) > 14:
            kaydir = QScrollArea()
            kaydir.setWidgetResizable(True)
            kaydir.setWidget(alan_w)
            kaydir.setMinimumHeight(520)
            ana.addWidget(kaydir)
        else:
            ana.addWidget(alan_w)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("Kaydet")
        bb.button(QDialogButtonBox.Cancel).setText("Vazgeç")
        bb.accepted.connect(self._kaydet)
        bb.rejected.connect(self.reject)
        ana.addWidget(bb)

    def degerler(self) -> dict:
        return {a.ad: kutu_deger(self.kutular[a.ad], a) for a in self.alanlar if not a.salt_okunur}

    def _kaydet(self):
        v = self.degerler()
        hatalar = []
        for a in self.alanlar:
            if a.salt_okunur:
                continue
            if a.zorunlu and v.get(a.ad) in (None, ""):
                hatalar.append(f"'{a.etiket}' zorunludur.")
            if a.dogrula:
                h = a.dogrula(v.get(a.ad))
                if h:
                    hatalar.append(f"{a.etiket}: {h}")
        if self.on_dogrula:
            hatalar += self.on_dogrula(v) or []
        if hatalar:
            uyari(self, "\n".join(hatalar))
            return
        self.accept()


# ---------------------------------------------------------------- genel kayıt listesi sayfası
@dataclass
class VarlikTanimi:
    tablo: str
    baslik: str
    aciklama: str
    alanlar: list[Alan]
    liste_sql: str | None = None  # tablo görünümü için özel sorgu (id kolonu içermeli)
    ek_kolonlar: list[Kolon] = field(default_factory=list)
    sirala: str = "id DESC"
    arama: list[str] = field(default_factory=list)
    on_dogrula: Callable[[dict, dict | None], list[str]] | None = None
    on_kaydet: Callable[[dict, dict | None], dict] | None = None
    sonra_kaydet: Callable[[int], None] | None = None
    silme_kontrol: Callable[[dict], str | None] | None = None
    ice_aktarma: dict | None = None  # {alan: [başlık adayları]}; "_" ile başlayan alanlar yalnız süzgeç içindir
    ice_aktarma_suzgec: Callable[[dict], bool] | None = None  # False dönen satır bu listeye ait değildir
    form_notu: str = ""
    renk: Callable[[dict], str | None] | None = None
    bolum_kolonu: str | None = None  # alan şefi / öğretmen yalnız kendi bölümünün kayıtlarını görür


def _alan_kolon_turu(a: Alan) -> str:
    return {"para": "para", "oran": "oran", "tarih": "tarih", "bool": "bool", "tamsayi": "sayi",
            "ondalik": "sayi"}.get(a.tur, "metin")


class KayitSayfasi(QWidget):
    def __init__(self, tanim: VarlikTanimi, parent=None):
        super().__init__(parent)
        self.t = tanim
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(tanim.baslik, tanim.aciklama))
        ust = QHBoxLayout()
        self.b_yeni = buton("＋ Yeni", self.yeni, "birincil")
        self.b_duzenle = buton("Düzenle", self.duzenle)
        self.b_sil = buton("Sil", self.sil, "tehlike")
        ust.addWidget(self.b_yeni)
        ust.addWidget(self.b_duzenle)
        ust.addWidget(self.b_sil)
        if tanim.ice_aktarma:
            ust.addWidget(buton("Excel'den İçe Aktar", self.ice_aktar))
        ust.addWidget(buton("Excel'e Aktar", lambda: tablo_excele(self, self.tablo, tanim.baslik)))
        self.ek_butonlar = QHBoxLayout()
        ust.addLayout(self.ek_butonlar)
        ust.addStretch()
        self.arama = QLineEdit()
        self.arama.setPlaceholderText("Ara...")
        self.arama.setMaximumWidth(260)
        self.arama.textChanged.connect(self._filtrele)
        ust.addWidget(self.arama)
        lay.addLayout(ust)
        self.tablo = VeriTablosu()
        self.tablo.satirCiftTiklandi.connect(lambda _s: self.duzenle())
        lay.addWidget(self.tablo)
        self.durum = QLabel()
        lay.addWidget(self.durum)
        self.yenile()

    def kolonlar(self) -> list[Kolon]:
        k = [Kolon(a.ad if a.tur != "fk" else a.ad + "_ad", a.etiket, _alan_kolon_turu(a))
             for a in self.t.alanlar if a.tabloda]
        return k + self.t.ek_kolonlar

    def veriler(self) -> list[dict]:
        if self.t.liste_sql:
            return db().q(self.t.liste_sql)
        satirlar = db().q(f"SELECT * FROM {self.t.tablo} ORDER BY {self.t.sirala}")
        bolum = Oturum.bolum_id()
        if self.t.bolum_kolonu and bolum:
            satirlar = [s for s in satirlar if s.get(self.t.bolum_kolonu) == bolum]
        fk_alanlar = [a for a in self.t.alanlar if a.tur == "fk"]
        if fk_alanlar:
            haritalar = {}
            for a in fk_alanlar:
                secenek = a.secenekler() if callable(a.secenekler) else a.secenekler
                haritalar[a.ad] = dict(secenek or [])
            for s in satirlar:
                for a in fk_alanlar:
                    s[a.ad + "_ad"] = haritalar[a.ad].get(s.get(a.ad), "")
        secim_alanlar = [a for a in self.t.alanlar if a.tur == "secim" and a.secenekler and
                         not callable(a.secenekler) and a.secenekler and isinstance(a.secenekler[0], (tuple, list))]
        for a in secim_alanlar:
            h = dict(a.secenekler)
            for s in satirlar:
                s[a.ad] = h.get(s.get(a.ad), s.get(a.ad))
        return satirlar

    def yenile(self):
        self._tum = self.veriler()
        self._filtrele()
        yaz = Oturum.yazabilir(self)
        for b in (self.b_yeni, self.b_duzenle, self.b_sil):
            b.setEnabled(yaz)

    def _filtrele(self):
        metin = self.arama.text().strip().lower()
        if metin:
            satirlar = [s for s in self._tum if any(metin in str(v).lower() for v in s.values() if v is not None)]
        else:
            satirlar = self._tum
        self.tablo.doldur(self.kolonlar(), satirlar, self.t.renk)
        self.durum.setText(f"{len(satirlar)} kayıt")

    def _dogrula(self, kayit):
        def f(v):
            return self.t.on_dogrula(v, kayit) if self.t.on_dogrula else []
        return f

    def yeni(self):
        if not yetki_kontrol(self):
            return
        d = FormDialog(self, f"{self.t.baslik} - Yeni Kayıt", self.t.alanlar, None, self._dogrula(None), self.t.form_notu)
        if d.exec():
            v = d.degerler()
            if self.t.on_kaydet:
                v = self.t.on_kaydet(v, None)
            yid = db().ekle(self.t.tablo, v)
            if self.t.sonra_kaydet:
                self.t.sonra_kaydet(yid)
            self.yenile()

    def duzenle(self):
        s = self.tablo.secili()
        if not s:
            return
        if not yetki_kontrol(self):
            return
        with db().kayit_duzenleme(self.t.tablo, s["id"]):
            kayit = db().q1(f"SELECT * FROM {self.t.tablo} WHERE id = ?", (s["id"],))
            if not kayit:
                uyari(self, "Bu kayıt başka bir kullanıcı tarafından silinmiş.")
                self.yenile()
                return
            d = FormDialog(self, f"{self.t.baslik} - Düzenle", self.t.alanlar, kayit, self._dogrula(kayit), self.t.form_notu)
            if not d.exec():
                return
            v = d.degerler()
            if self.t.on_kaydet:
                v = self.t.on_kaydet(v, kayit)
            try:
                db().guncelle(self.t.tablo, s["id"], v)
            except KayitCakismasi as e:
                uyari(self, str(e))
                self.yenile()
                return
        if self.t.sonra_kaydet:
            self.t.sonra_kaydet(s["id"])
        self.yenile()

    def sil(self):
        secili = self.tablo.secililer()
        if not secili or not yetki_kontrol(self):
            return
        for s in secili:
            if self.t.silme_kontrol:
                h = self.t.silme_kontrol(s)
                if h:
                    uyari(self, h)
                    return
        if not soru(self, f"{len(secili)} kayıt silinecek. Emin misiniz?"):
            return
        for s in secili:
            db().sil(self.t.tablo, s["id"])
        self.yenile()

    def ice_aktar(self):
        if not yetki_kontrol(self):
            return
        yol, _ = QFileDialog.getOpenFileName(self, "Excel dosyası seç", "", "Excel (*.xlsx *.xlsm)")
        if not yol:
            return
        try:
            kayitlar, sayfa = excel.tablo_bul(Path(yol), self.t.ice_aktarma)
        except Exception as e:
            hata(self, f"Dosya okunamadı:\n{e}")
            return
        elenen = 0
        if self.t.ice_aktarma_suzgec:
            uygun = [k for k in kayitlar if self.t.ice_aktarma_suzgec(k)]
            elenen, kayitlar = len(kayitlar) - len(uygun), uygun
        if not kayitlar:
            uyari(self, "Dosyada eşleşen başlık satırı ya da aktarılacak kayıt bulunamadı.")
            return
        alanlar = {a.ad: a for a in self.t.alanlar}
        ad_alani = next((a for a in excel.AD_ALANLARI if a in self.t.ice_aktarma), None)
        ornek = ", ".join(str(k.get(ad_alani) or "").strip() for k in kayitlar[:5]) + ("…" if len(kayitlar) > 5 else "")
        sutunlar = ", ".join(alanlar[a].etiket for a in kayitlar[0] if a in alanlar)
        if not soru(self, f"'{sayfa}' sayfasında {len(kayitlar)} kayıt bulundu"
                          + (f" ({elenen} satır bu listeye ait olmadığı için elendi)" if elenen else "")
                          + f".\n\nİlk kayıtlar: {ornek}\nEşleşen sütunlar: {sutunlar}\n\nİçe aktarılsın mı?"):
            return
        zorunlu = [a.ad for a in self.t.alanlar if a.zorunlu]
        tekil = next((a for a in ("tckn", "vkn_tckn") if a in alanlar), None)
        eklenen, eksik, mevcut, notlar = 0, 0, 0, []
        with db().islem():
            for k in kayitlar:
                temiz = {a: (str(v).strip() if isinstance(v, str) else v) for a, v in k.items()
                         if a in alanlar and not a.startswith("_")}
                for a in self.t.alanlar:
                    v = temiz.get(a.ad)
                    if a.ad in temiz and a.tur in ("para", "ondalik", "oran") and v not in (None, ""):
                        try:
                            temiz[a.ad] = float(str(v).replace(",", "."))
                        except ValueError:
                            temiz[a.ad] = None
                    elif a.ad in temiz and a.tur == "metin" and v is not None:
                        temiz[a.ad] = str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)
                    if temiz.get(a.ad) == "":
                        temiz[a.ad] = None
                    if a.ad not in temiz and a.varsayilan is not None:
                        temiz[a.ad] = a.varsayilan
                ad = temiz.get(ad_alani) or "?"
                if any(temiz.get(z) in (None, "") for z in zorunlu):
                    eksik += 1
                    continue
                if tekil and temiz.get(tekil) and db().q1(f"SELECT id FROM {self.t.tablo} WHERE {tekil} = ?",
                                                          (temiz[tekil],)):
                    mevcut += 1
                    continue
                for a in self.t.alanlar:
                    if a.dogrula and temiz.get(a.ad) not in (None, ""):
                        h = a.dogrula(temiz[a.ad])
                        if h:
                            notlar.append(f"{ad}: {a.etiket} alınmadı - {h}")
                            temiz[a.ad] = None
                if self.t.on_dogrula:
                    h = self.t.on_dogrula(temiz, None)
                    if h:
                        notlar.append(f"{ad}: aktarılmadı ({'; '.join(h)})")
                        continue
                if self.t.on_kaydet:
                    temiz = self.t.on_kaydet(temiz, None)
                db().ekle(self.t.tablo, temiz, log=False)
                eklenen += 1
            db().log("Excel içe aktarma", self.t.tablo, None, f"{eklenen} kayıt ({sayfa}): {yol}")
        self.yenile()
        mesaj = f"{eklenen} kayıt eklendi."
        if mevcut:
            mesaj += f"\n{mevcut} kayıt zaten kayıtlı olduğu için atlandı."
        if eksik:
            mesaj += f"\n{eksik} satır zorunlu alan eksik olduğu için atlandı."
        if notlar:
            mesaj += "\n\n" + "\n".join(notlar[:12]) + (f"\n… ve {len(notlar) - 12} not daha" if len(notlar) > 12 else "")
        bilgi(self, mesaj)
