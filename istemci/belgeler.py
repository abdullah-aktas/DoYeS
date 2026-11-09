"""Printable piece-rate documents (HTML, A4) built only from the server's frozen/live calculation."""
from __future__ import annotations

import base64
import html
import inspect
import os
import re
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import flet as ft

try:
    from . import tanimlar as T
except ImportError:
    import tanimlar as T

AYLAR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")

BELGELER = [
    ("olur", "Onay (olur) yazısı"),
    ("istek", "Öğretmen görevlendirme / istek yazısı"),
    ("ek3", "Ek-3 ön maliyet ve dağıtım"),
    ("malzeme", "İlk madde ve malzeme listesi"),
    ("teklif", "Piyasa fiyat araştırma tutanağı"),
    ("puantaj", "Toplu puantaj cetveli"),
    ("ogretmen_bordro", "Öğretmen parça başı bordrosu"),
    ("ogrenci_bordro", "Öğrenci parça başı bordrosu"),
    ("muayene", "Muayene ve kabul tutanağı"),
    ("iban", "Banka ödeme (IBAN) listesi"),
]
BELGE_ADI = dict(BELGELER)
FC_BELGELER = [
    ("fc_olur", "Fazla çalışma onay (olur) yazısı"),
    ("fc_gorev", "Fazla çalışma görevlendirme yazısı"),
    ("fc_puantaj", "Fazla çalışma puantaj cetveli"),
    ("fc_bordro", "Fazla çalışma ücret bordrosu"),
    ("fc_iban", "Banka ödeme (IBAN) listesi"),
]
BELGE_ADI.update(FC_BELGELER)
HP_BELGELER = [
    ("hp_bildirim", "Hazine payı bildirim formu (Örnek No:30)"),
    ("hp_ust_yazi", "Hazine payı muhasebe birimi üst yazısı"),
    ("hp_talimat", "Hazine payı banka ödeme talimatı"),
]
BELGE_ADI.update(HP_BELGELER)
YS_BELGELER = [
    ("ys_cetvel", "Yıl sonu kâr dağıtım cetveli"),
    ("ys_utp", "ÜTP ödeme listesi"),
    ("ys_iban", "Banka ödeme (IBAN) listesi"),
]
BELGE_ADI.update(YS_BELGELER)
GUN_TURU_ADI = {"O": "Öğretim günü", "T": "Tatil", "B": "Bayram"}

CSS = """
@page { size: A4; margin: 14mm; }
@page yatay { size: A4 landscape; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt; color: #111; }
h1 { font-size: 14pt; text-align: center; margin: 0 0 4px; }
h2 { font-size: 12pt; text-align: center; margin: 0 0 12px; font-weight: normal; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; }
th, td { border: 1px solid #555; padding: 3px 5px; font-size: 9.5pt; }
th { background: #e8eef5; color: #1f4e79; }
td.s { text-align: right; white-space: nowrap; }
tr.t td { font-weight: bold; background: #f5f5f5; }
.imza { display: flex; justify-content: space-around; margin-top: 36px; text-align: center; }
.imza div { min-width: 170px; }
.kucuk { font-size: 8.5pt; color: #444; }
.marka { display: flex; align-items: center; gap: 8px; margin-top: 18px; color: #1f4e79; font-size: 8.5pt; }
.marka img { width: 28px; height: 28px; border-radius: 6px; }
.yatay { page: yatay; }
@media print { .yazdir { display: none; } }
"""


@lru_cache(maxsize=1)
def marka_img_html(boyut: int = 28) -> str:
    """Embedded app icon for printable HTML footers (works offline)."""
    yol = Path(__file__).resolve().parent / "assets" / "icon.png"
    if not yol.is_file():
        yol = Path(__file__).resolve().parent / "assets" / "ikon.png"
    if not yol.is_file():
        return ""
    veri = base64.b64encode(yol.read_bytes()).decode("ascii")
    return (f"<img src='data:image/png;base64,{veri}' width='{boyut}' height='{boyut}' "
            f"alt='DÖSE' style='width:{boyut}px;height:{boyut}px;border-radius:6px;vertical-align:middle'>")


def e(deger) -> str:
    return html.escape("" if deger is None else str(deger))


def tl(deger) -> str:
    return T.sayi_yaz(Decimal(str(deger or "0")), 2)


def adet(deger) -> str:
    return T.siparis_sayisi_yaz(deger or "0")


def yuzde(deger) -> str:
    return "%" + T.siparis_yuzdesi_yaz(deger or "0")


def tarih(deger) -> str:
    return e(T.gosterim("tarih", deger)) if deger else ""


def belge_no(h: dict) -> str:
    return (h.get("hakedis_no") or h.get("bildirim_no") or h.get("bordro_no")
            or h.get("belge_no") or h.get("yazi_no") or h.get("form_no") or "belge")


def _sayfa(baslik: str, govde: str, okul: dict, h: dict, yatay: bool = False) -> str:
    tur = ("Hakediş" if h.get("hakedis_no") else "Bildirim" if h.get("bildirim_no")
           else "Bordro" if h.get("bordro_no") else "Belge")
    siparis = f" · Sipariş {e(h['siparis_no'])}" if h.get("siparis_no") else ""
    return (f"<!DOCTYPE html><html lang='tr'><head><meta charset='utf-8'><title>{e(baslik)} · {e(belge_no(h))}"
            f"</title><style>{CSS}</style></head><body class='{'yatay' if yatay else ''}'>"
            "<button class='yazdir' onclick='window.print()'>Yazdır</button>"
            f"<h1>T.C.<br>{e(okul.get('ad'))} MÜDÜRLÜĞÜ<br>DÖNER SERMAYE İŞLETMESİ</h1>"
            f"<h2>{e(baslik)}</h2>{govde}"
            f"<div class='marka'>{marka_img_html()}"
            f"<span>{tur} {e(belge_no(h))}{siparis} · Kurum kodu {e(okul.get('kurum_kodu'))} · "
            f"DÖSE Yönetim · {datetime.now():%d.%m.%Y %H:%M}</span></div>"
            "</body></html>")


def _imzalar(*kisiler: tuple[str, str]) -> str:
    return "<div class='imza'>" + "".join(
        f"<div>{e(ad) or '&nbsp;'}<br><b>{e(unvan)}</b><br><br>İmza</div>" for ad, unvan in kisiler) + "</div>"


def _onaylayan(h: dict, rol: str) -> str:
    for a in reversed(h.get("onaylar") or []):
        if a["rol"] == rol and a["islem"] in ("Hazırlandı", "Onaya gönderildi", "Uygundur", "Olur"):
            return a.get("ad_soyad") or ""
    return ""


def _donem(h: dict) -> str:
    return f"{AYLAR[int(h['ay']) - 1]} {h['yil']}"


def _ozet_tablo(h: dict, hs: dict) -> str:
    satirlar = [
        ("Fatura tutarı (KDV dahil)", hs["fatura_tutari"]), (f"KDV ({yuzde(hs['kdv_orani'])})", hs["kdv"]),
        ("Hakediş bedeli (KDV hariç)", hs["bedel"]),
        (f"İlk madde ve malzeme (bedelin {yuzde(hs.get('malzeme_orani'))})", hs["malzeme"]),
        ("Hizmet alımı", hs["hizmet_alimi"]),
        (f"Faaliyet giderleri ({yuzde(h['faaliyet_orani'])})", hs["faaliyet"]),
        (f"Kâr ({yuzde(h['kar_orani'])})", hs["kar"]),
        (f"Peşin gelir vergisi ({yuzde(h['pesin_orani'])})", hs["pesin_gelir_vergisi"]),
        (f"SHÇEK payı ({yuzde(h['shcek_orani'])})", hs["shcek"]),
        ("DAĞITILACAK İŞÇİLİK", hs["iscilik"]),
        (f"Öğrenci payı (işçiliğin {yuzde(h['ogrenci_orani'])})", hs["ogrenci_havuz"]),
        ("Öğretmen payı", hs["ogretmen_havuz"]),
    ]
    return "<table>" + "".join(
        f"<tr{' class=t' if ad.isupper() else ''}><td>{e(ad)}</td><td class=s>{tl(t)} TL</td></tr>"
        for ad, t in satirlar) + "</table>"


def _kisiler(hs: dict, tur: str | None = None) -> list[dict]:
    return [k for k in hs.get("kisiler") or [] if tur is None or k["kisi_turu"] == tur]


def _bordro(h: dict, hs: dict, tur: str) -> str:
    kisiler = _kisiler(hs, tur)
    ek = "<th>Okul no / sınıf</th>" if tur == "Öğrenci" else "<th>Görevi</th><th>GV oranı</th>"
    satirlar = []
    for i, k in enumerate(kisiler, 1):
        ek_hucre = (f"<td>{e(k.get('okul_no'))} / {e(k.get('sinif'))}</td>" if tur == "Öğrenci"
                    else f"<td>{e(k.get('gorev'))}</td><td class=s>{yuzde(k.get('gv_orani'))}</td>")
        satirlar.append(f"<tr><td>{i}</td><td>{e(k.get('ad_soyad'))}</td><td>{e(k.get('tckn'))}</td>{ek_hucre}"
                        f"<td class=s>{adet(k['adet'])}</td><td class=s>{tl(k['brut'])}</td>"
                        f"<td class=s>{tl(k['gelir_vergisi'])}</td><td class=s>{tl(k['damga_vergisi'])}</td>"
                        f"<td class=s>{tl(k['net'])}</td></tr>")
    top = {a: sum((Decimal(k[a]) for k in kisiler), Decimal(0)) for a in ("brut", "gelir_vergisi", "damga_vergisi", "net")}
    adet_top = sum((Decimal(k["adet"]) for k in kisiler), Decimal(0))
    bos = "<td></td>" if tur == "Öğrenci" else "<td></td><td></td>"
    satirlar.append(f"<tr class=t><td></td><td>TOPLAM</td><td></td>{bos}<td class=s>{adet(adet_top)}</td>"
                    f"<td class=s>{tl(top['brut'])}</td><td class=s>{tl(top['gelir_vergisi'])}</td>"
                    f"<td class=s>{tl(top['damga_vergisi'])}</td><td class=s>{tl(top['net'])}</td></tr>")
    havuz = hs["ogrenci_havuz"] if tur == "Öğrenci" else hs["ogretmen_havuz"]
    parca = hs.get("ogrenci_parca_payi" if tur == "Öğrenci" else "ogretmen_parca_payi")
    aciklama = (f"<p>Dönem: {_donem(h)} · Ürün/iş: {e(h['urun_aciklama'])} · {tur} payı: {tl(havuz)} TL"
                + (f" · Parça başına: {e(T.siparis_sayisi_yaz(parca))} TL" if parca else "") + "</p>")
    not_ = ("<p class='kucuk'>Öğrenci ödemeleri gelir vergisinden istisnadır; damga vergisi yalnız asgari ücreti aşan "
            "kısımdan kesilir.</p>" if tur == "Öğrenci" else
            f"<p class='kucuk'>Damga vergisi oranı binde {e(T.siparis_sayisi_yaz(Decimal(h['dv_orani']) * 1000))}. "
            "Gelir vergisi her öğretmenin kümülatif dilimine göre girilen orandır.</p>")
    return (aciklama + f"<table><tr><th>S.No</th><th>Ad soyad</th><th>T.C. kimlik no</th>{ek}<th>Adet</th>"
            "<th>Brüt</th><th>Gelir V.</th><th>Damga V.</th><th>Net ödenecek</th></tr>" + "".join(satirlar)
            + "</table>" + not_)


def fc_belge_html(tur: str, okul: dict, h: dict) -> str:
    """Overtime (fazla çalışma) documents from the server's bordro calculation."""
    hs = h.get("hesap") or {}
    hazirlayan = _onaylayan(h, "Alan Şefi") or _onaylayan(h, h.get("olusturan_rol") or "")
    tmy, mudur = _onaylayan(h, "Teknik Müdür Yardımcısı"), _onaylayan(h, "Okul Müdürü")
    imza3 = _imzalar((hazirlayan, "Alan / Atölye Şefi"), (tmy, "Teknik Müdür Yardımcısı"), (mudur, "Okul Müdürü"))
    kisiler = hs.get("kisiler") or []
    toplam = hs.get("toplam") or {}
    baslik = BELGE_ADI[tur]
    ozet = (f"<p>Dönem: {_donem(h)} · Sipariş: {e(h['siparis_no'])} ({e(h.get('siparis_konu'))}) · Yapılan iş: "
            f"{e(h['is_tanimi'])} · Saat ücreti: {tl(h['saat_ucreti'])} TL (azami {tl(h['azami_ucret'])} TL)</p>")
    if tur == "fc_olur":
        govde = (f"<p>Sayı: {e(h['bordro_no'])}<br>Konu: Fazla çalışma ücreti ödemesi</p>"
                 "<p style='text-align:center'><b>MÜDÜRLÜK MAKAMINA</b></p>"
                 f"<p>Okulumuz {e(h.get('bolum'))} bölümünce {e(h.get('cari'))} adına {e(h['siparis_no'])} numaralı "
                 f"sipariş kapsamında {_donem(h)} döneminde olağan çalışma saatleri dışında fiilen yapılan "
                 f"{adet(toplam.get('saat'))} saat fazla çalışma karşılığı, Döner Sermaye Çalışma Yönergesinin 9. "
                 f"maddesi ve Merkezi Yönetim Bütçe Kanunu (K) cetveli gereğince saat başına {tl(h['saat_ucreti'])} TL "
                 f"üzerinden brüt {tl(toplam.get('brut'))} TL, yasal kesintiler "
                 f"{tl(Decimal(toplam.get('gelir_vergisi') or '0') + Decimal(toplam.get('damga_vergisi') or '0'))} TL, "
                 f"net {tl(toplam.get('net'))} TL fazla çalışma ücretinin ilgililere ödenmesini olurlarınıza arz "
                 "ederim.</p>"
                 + _imzalar((hazirlayan, "Alan / Atölye Şefi"), (tmy, "Uygundur · Teknik Müdür Yardımcısı"))
                 + "<p style='text-align:center;margin-top:28px'><b>OLUR</b></p>" + _imzalar((mudur, "Okul Müdürü")))
    elif tur == "fc_gorev":
        satirlar = "".join(f"<tr><td>{i}</td><td>{e(k.get('ad_soyad'))}</td><td>{e(k.get('kadro_unvani') or '')}</td>"
                           f"<td>{e(k.get('gorev') or '')}</td></tr>" for i, k in enumerate(kisiler, 1))
        govde = (ozet + "<p>Yukarıdaki işin olağan çalışma saatleri dışında yapılması için aşağıdaki personelin fazla "
                 "çalışma ücreti esasına göre görevlendirilmesini arz ederiz. Fazla çalışma; öğretim günlerinde "
                 f"günde {adet(h['ogretim_gunu_saat'])}, tatillerde günde {adet(h['tatil_gunu_saat'])} saati geçemez; "
                 "bayram günlerinde" + ("" if h.get("pazar_izinli") else " ve Pazar günleri") + " yapılamaz.</p>"
                 "<table><tr><th>S.No</th><th>Ad soyad</th><th>Kadro unvanı</th><th>Görevi</th></tr>"
                 f"{satirlar}</table>" + imza3)
    elif tur == "fc_puantaj":
        turler = hs.get("gun_turleri") or h.get("gun_turleri") or []
        gun = int(hs.get("gun_sayisi") or len(turler) or 31)
        bas = "".join(f"<th title='{e(GUN_TURU_ADI.get(turler[g - 1] if g <= len(turler) else '', ''))}'>{g}"
                      f"<br><span class=kucuk>{e(turler[g - 1] if g <= len(turler) else '')}</span></th>"
                      for g in range(1, gun + 1))
        satirlar = ""
        for i, k in enumerate(kisiler, 1):
            gunler = k.get("gunler") or []
            hucreler = "".join(
                f"<td class=s>{adet(gunler[g]) if g < len(gunler) and Decimal(gunler[g]) != 0 else ''}</td>"
                for g in range(gun))
            satirlar += (f"<tr><td>{i}</td><td>{e(k.get('ad_soyad'))}</td>{hucreler}"
                         f"<td class=s>{adet(k['saat'])}</td></tr>")
        govde = (ozet + f"<table><tr><th>S.No</th><th>Ad soyad</th>{bas}<th>Saat</th></tr>{satirlar}</table>"
                 "<p class='kucuk'>O: öğretim günü, T: tatil, B: bayram (fazla çalışma yapılamaz).</p>" + imza3)
        return _sayfa(baslik, govde, okul, h, yatay=True)
    elif tur == "fc_bordro":
        satirlar = "".join(
            f"<tr><td>{i}</td><td>{e(k.get('ad_soyad'))}</td><td>{e(k.get('tckn'))}</td><td>{e(k.get('gorev') or '')}"
            f"</td><td class=s>{adet(k['saat'])}</td><td class=s>{tl(k['saat_ucreti'])}</td><td class=s>"
            f"{tl(k['brut'])}</td><td class=s>{yuzde(k.get('gv_orani'))}</td><td class=s>{tl(k['gelir_vergisi'])}</td>"
            f"<td class=s>{tl(k['damga_vergisi'])}</td><td class=s>{tl(k['net'])}</td></tr>"
            for i, k in enumerate(kisiler, 1))
        satirlar += (f"<tr class=t><td></td><td>TOPLAM</td><td></td><td></td><td class=s>{adet(toplam.get('saat'))}"
                     f"</td><td></td><td class=s>{tl(toplam.get('brut'))}</td><td></td><td class=s>"
                     f"{tl(toplam.get('gelir_vergisi'))}</td><td class=s>{tl(toplam.get('damga_vergisi'))}</td>"
                     f"<td class=s>{tl(toplam.get('net'))}</td></tr>")
        govde = (ozet + "<table><tr><th>S.No</th><th>Ad soyad</th><th>T.C. kimlik no</th><th>Görevi</th><th>Saat</th>"
                 "<th>Saat ücreti</th><th>Brüt</th><th>GV oranı</th><th>Gelir V.</th><th>Damga V.</th>"
                 f"<th>Net ödenecek</th></tr>{satirlar}</table>"
                 f"<p class='kucuk'>Damga vergisi oranı binde {e(T.siparis_sayisi_yaz(Decimal(h['dv_orani']) * 1000))}. "
                 "Gelir vergisi her personelin kümülatif dilimine göre girilen orandır. Ödeme izleyen ayın 10'una "
                 "kadar banka hesabına yapılır (md.9/b).</p>" + imza3)
    elif tur == "fc_iban":
        satirlar = "".join(f"<tr><td>{i}</td><td>{e(k.get('ad_soyad'))}</td><td>{e(k.get('tckn'))}</td>"
                           f"<td>{e(k.get('iban'))}</td><td class=s>{tl(k['net'])}</td></tr>"
                           for i, k in enumerate((k for k in kisiler if Decimal(k["net"]) > 0), 1))
        govde = (f"<p>{e(h['bordro_no'])} numaralı fazla çalışma bordrosu net ödemelerinin aşağıdaki hesaplara "
                 "aktarılmasını rica ederiz.</p><table><tr><th>S.No</th><th>Ad soyad</th><th>T.C. kimlik no</th>"
                 f"<th>IBAN</th><th>Net tutar</th></tr>{satirlar}<tr class=t><td></td><td>TOPLAM</td><td></td><td></td>"
                 f"<td class=s>{tl(toplam.get('net'))}</td></tr></table>"
                 + _imzalar(("", "Sayman"), (mudur, "Okul Müdürü")))
    else:
        raise ValueError(f"Bilinmeyen belge: {tur}")
    return _sayfa(baslik, govde, okul, h)


def hp_belge_html(tur: str, okul: dict, h: dict) -> str:
    """Treasury-share (hazine payı) documents; `h` is the server's declaration with year/month and payment."""
    donem = _donem(h)
    odeme = h.get("odeme") or {}
    imza = _imzalar(("", "Sayman"), ("", "Okul Müdürü (Harcama Yetkilisi)"))
    if tur == "hp_bildirim":
        satirlar = [
            ("Dönem", donem),
            ("Aylık gayrisafi hasılattan tahsil edilen tutar (KDV hariç)", f"{tl(h['hasilat'])} TL"),
            ("Hazine payı oranı", yuzde(h["oran"])),
            ("Hesaplanan hazine payı", f"{tl(h['tutar'])} TL"),
            ("Bildirim tarihi", tarih(h.get("bildirim_tarihi"))),
            ("Son ödeme tarihi", tarih(h.get("son_odeme"))),
            ("Ödeme tarihi / dekont", f"{tarih(odeme.get('tarih'))} {e(odeme.get('belge_no') or '')}".strip()
             or "Ödenmedi"),
        ]
        if int(h.get("gecikme_ay") or 0) > 0:
            satirlar.append(("Gecikme (ay / %1 aylık tutar)", f"{int(h['gecikme_ay'])} ay · {tl(h['gecikme_tutari'])} TL"))
        govde = ("<p>Muhasebat Genel Müdürlüğü Genel Tebliği (Sıra No: 73) md.6-7 ve Döner Sermaye Yönergesi gereğince "
                 "aylık hazine payı bildirimidir.</p><table>"
                 + "".join(f"<tr><th style='text-align:left'>{e(a)}</th><td class=s>{d}</td></tr>" for a, d in satirlar)
                 + "</table><p class='kucuk'>Hasılat, satış faturalarından ilgili ayda fiilen tahsil edilen net tutarın "
                 "fatura matrahına düşen payıdır; KDV ve tevkifat dahil edilmez. Süresinde ödenmeyen tutar için her ay %1 "
                 "gecikme uygulanır ve sorumlulara yarı yarıya rücu edilir.</p>" + imza)
    elif tur == "hp_ust_yazi":
        govde = (f"<p>Sayı: {e(h['bildirim_no'])}<br>Konu: Hazine payı bildirimi ({e(donem)})</p>"
                 "<p style='text-align:center'><b>İLGİLİ MUHASEBE BİRİMİNE</b></p>"
                 f"<p>Okulumuz Döner Sermaye İşletmesinin {e(donem)} ayında aylık gayrisafi hasılattan tahsil edilen "
                 f"{tl(h['hasilat'])} TL üzerinden {yuzde(h['oran'])} oranında hesaplanan {tl(h['tutar'])} TL hazine "
                 "payı, Muhasebat Genel Müdürlüğü Genel Tebliği (Sıra No: 73) gereğince D.S.İ.B.M.Y. Örnek No: 30 "
                 "bildirim formu ile birlikte ekte sunulmuş olup ilgili tutar muhasebe biriminiz hesabına "
                 + (f"{tarih(odeme.get('tarih'))} tarihinde yatırılmıştır." if odeme else "yatırılacaktır.")
                 + "</p><p>Bilgilerinize arz ederim.</p>" + _imzalar(("", "Okul Müdürü")))
    elif tur == "hp_talimat":
        govde = (f"<p>Sayı: {e(h['bildirim_no'])}</p><p style='text-align:center'><b>BANKA ŞUBE MÜDÜRLÜĞÜNE</b></p>"
                 f"<p>Okulumuz Döner Sermaye İşletmesi hesabından {e(donem)} dönemi hazine payı olan "
                 f"<b>{tl(h['tutar'])} TL</b>'nin ilgili muhasebe birimi hesabına aktarılmasını rica ederiz.</p>"
                 "<p>Alıcı: ........................ Muhasebe Müdürlüğü · IBAN: TR.. .... .... .... .... .... ..</p>"
                 + imza)
    else:
        raise ValueError(f"Bilinmeyen belge: {tur}")
    return _sayfa(BELGE_ADI[tur], govde, okul, h)


def ys_belge_html(tur: str, okul: dict, h: dict) -> str:
    """Year-end profit distribution documents from server snapshot."""
    hs = h.get("hesap") or {}
    kisiler = hs.get("kisiler") or []
    imza = _imzalar(("", "Sayman"), ("", "Okul Müdürü (Harcama Yetkilisi)"))
    if tur == "ys_cetvel":
        satirlar = "".join(
            f"<tr><td>{i}</td><td>{e(k.get('ad_soyad'))}</td><td>{e(k.get('gorev'))}</td>"
            f"<td class=s>{tl(k.get('brut'))}</td><td class=s>{tl(k.get('gelir_vergisi'))}</td>"
            f"<td class=s>{tl(k.get('damga_vergisi'))}</td><td class=s>{tl(k.get('net'))}</td></tr>"
            for i, k in enumerate(kisiler, 1))
        govde = (f"<p>{e(h.get('belge_no'))} numaralı {e(h.get('yil'))} yılı kâr dağıtım cetveli.</p>"
                 f"<p>Dönem kârı {tl(hs.get('donem_kari'))} TL · SHÇEK {tl(hs.get('shcek'))} TL · "
                 f"ÜTP {tl(hs.get('dagitilan_utp'))} TL · Merkez payı {tl(hs.get('merkez_payi'))} TL.</p>"
                 "<table><tr><th>S.No</th><th>Ad soyad</th><th>Görev</th><th>Brüt</th><th>GV</th><th>DV</th>"
                 f"<th>Net</th></tr>{satirlar}</table>" + imza)
    elif tur == "ys_utp":
        satirlar = "".join(
            f"<tr><td>{i}</td><td>{e(k.get('ad_soyad'))}</td><td class=s>{tl(k.get('net'))}</td></tr>"
            for i, k in enumerate((k for k in kisiler if Decimal(str(k.get('net') or 0)) > 0), 1))
        govde = (f"<p>{e(h.get('yil'))} yılı ÜTP net ödeme listesi.</p>"
                 f"<table><tr><th>S.No</th><th>Ad soyad</th><th>Net</th></tr>{satirlar}</table>" + imza)
    elif tur == "ys_iban":
        satirlar = "".join(
            f"<tr><td>{i}</td><td>{e(k.get('ad_soyad'))}</td><td>{e(k.get('iban'))}</td>"
            f"<td class=s>{tl(k.get('net'))}</td></tr>"
            for i, k in enumerate((k for k in kisiler if Decimal(str(k.get('net') or 0)) > 0), 1))
        govde = (f"<p>{e(h.get('belge_no'))} ÜTP banka ödeme listesi.</p>"
                 "<table><tr><th>S.No</th><th>Ad soyad</th><th>IBAN</th><th>Net</th></tr>"
                 f"{satirlar}</table>" + imza)
    else:
        raise ValueError(f"Bilinmeyen belge: {tur}")
    return _sayfa(BELGE_ADI[tur], govde, okul, h)


def belge_html(tur: str, okul: dict, h: dict) -> str:
    if tur.startswith("fc_"):
        return fc_belge_html(tur, okul, h)
    if tur.startswith("hp_"):
        return hp_belge_html(tur, okul, h)
    if tur.startswith("ys_"):
        return ys_belge_html(tur, okul, h)
    hs = h.get("hesap") or {}
    sef = _onaylayan(h, "Alan Şefi") or _onaylayan(h, h.get("olusturan_rol") or "")
    tmy, mudur = _onaylayan(h, "Teknik Müdür Yardımcısı"), _onaylayan(h, "Okul Müdürü")
    imza3 = _imzalar((sef, "Alan / Atölye Şefi"), (tmy, "Teknik Müdür Yardımcısı"), (mudur, "Okul Müdürü"))
    baslik = BELGE_ADI[tur]
    if tur == "olur":
        govde = (f"<p>Sayı: {e(h['hakedis_no'])}<br>Konu: Parça başı ücret ödemesi</p>"
                 "<p style='text-align:center'><b>MÜDÜRLÜK MAKAMINA</b></p>"
                 f"<p>Okulumuz {e(h.get('bolum'))} bölümünce {e(h.get('cari'))} adına {e(h['siparis_no'])} numaralı "
                 f"sipariş kapsamında {tarih(h['baslama'])} – {tarih(h['bitis'])} tarihleri arasında "
                 f"{adet(h['uretilen_miktar'])} {e(h['birim'])} {e(h['urun_aciklama'])} üretilmiştir. Döner Sermaye "
                 "Yönergesinin 8. maddesi gereğince işçilik payının aşağıdaki şekilde parça başı ücret olarak görevli "
                 "öğretmen ve öğrencilere ödenmesi hususunu olurlarınıza arz ederim.</p>"
                 + _ozet_tablo(h, hs)
                 + f"<p>Brüt toplam {tl(hs['toplam']['brut'])} TL, yasal kesintiler "
                 f"{tl(Decimal(hs['toplam']['gelir_vergisi']) + Decimal(hs['toplam']['damga_vergisi']))} TL, net "
                 f"ödenecek {tl(hs['toplam']['net'])} TL'dir.</p>"
                 + _imzalar((sef, "Alan / Atölye Şefi"), (tmy, "Uygundur · Teknik Müdür Yardımcısı"))
                 + "<p style='text-align:center;margin-top:28px'><b>OLUR</b></p>"
                 + _imzalar((mudur, "Okul Müdürü")))
    elif tur == "istek":
        satirlar = "".join(f"<tr><td>{i}</td><td>{e(k.get('ad_soyad'))}</td><td>{e(k.get('kadro_unvani') or '')}"
                           f"</td><td>{e(k.get('gorev'))}</td></tr>"
                           for i, k in enumerate(_kisiler(hs, "Öğretmen"), 1))
        govde = (f"<p>{e(h['siparis_no'])} numaralı sipariş ({e(h.get('siparis_konu'))}) kapsamındaki işin "
                 f"{tarih(h['baslama'])} – {tarih(h['bitis'])} tarihleri arasında ders dışı zamanlarda yapılması için "
                 "aşağıda bilgileri bulunan öğretmenlerin parça başı ücret esasına göre görevlendirilmesini arz ederiz."
                 "</p><table><tr><th>S.No</th><th>Ad soyad</th><th>Kadro unvanı</th><th>Görevi</th></tr>"
                 f"{satirlar}</table>" + imza3)
    elif tur == "ek3":
        govde = (f"<p>Dönem: {_donem(h)} · Ürün/iş: {e(h['urun_aciklama'])} · Miktar: {adet(h['uretilen_miktar'])} "
                 f"{e(h['birim'])}</p>" + _ozet_tablo(h, hs)
                 + f"<p>Öğretmen toplam adet: {adet(hs.get('ogretmen_adet'))} · Öğrenci toplam adet: "
                 f"{adet(hs.get('ogrenci_adet'))}</p>" + imza3)
    elif tur in ("malzeme", "teklif"):
        malzemeler = hs.get("malzemeler") or []
        if tur == "malzeme":
            satirlar = "".join(
                f"<tr><td>{m['sira']}</td><td>{e(m['cins'])}</td><td class=s>{adet(m['miktar'])}</td><td>"
                f"{e(m['birim'])}</td><td class=s>{tl(m['birim_fiyat'])}</td><td class=s>{tl(m['tutar'])}</td>"
                f"<td class=s>{yuzde(m['kdv_orani'])}</td><td class=s>{tl(m['kdv'])}</td></tr>" for m in malzemeler)
            satirlar += (f"<tr class=t><td></td><td>TOPLAM</td><td></td><td></td><td></td><td class=s>"
                         f"{tl(hs['malzeme'])}</td><td></td><td class=s>{tl(hs['malzeme_kdv'])}</td></tr>")
            govde = ("<table><tr><th>S.No</th><th>Cinsi</th><th>Miktar</th><th>Birim</th><th>Birim fiyat</th>"
                     f"<th>Tutar</th><th>KDV %</th><th>KDV</th></tr>{satirlar}</table>"
                     f"<p>Malzeme, KDV hariç hakediş bedelinin {yuzde(hs.get('malzeme_orani'))} kadarıdır.</p>" + imza3)
        else:
            satirlar = "".join(f"<tr><td>{m['sira']}</td><td>{e(m['cins'])}</td><td class=s>{adet(m['miktar'])} "
                               f"{e(m['birim'])}</td><td></td><td></td><td></td></tr>" for m in malzemeler)
            govde = ("<p>Aşağıdaki malzemeler için piyasada yapılan fiyat araştırması sonucu alınan teklifler:</p>"
                     "<table><tr><th>S.No</th><th>Cinsi</th><th>Miktar</th><th>1. firma</th><th>2. firma</th>"
                     f"<th>3. firma</th></tr>{satirlar}</table>"
                     + _imzalar(("", "Komisyon Başkanı"), ("", "Üye"), ("", "Üye")))
    elif tur == "puantaj":
        gun = int(hs.get("gun_sayisi") or 31)
        bas = "".join(f"<th>{g}</th>" for g in range(1, gun + 1))
        satirlar = ""
        for i, k in enumerate(_kisiler(hs), 1):
            gunler = k.get("gunler") or []
            hucreler = "".join(
                f"<td class=s>{adet(gunler[g]) if g < len(gunler) and Decimal(gunler[g]) != 0 else ''}</td>"
                for g in range(gun))
            satirlar += (f"<tr><td>{i}</td><td>{e(k.get('ad_soyad'))}</td><td>{e(k['kisi_turu'])}</td>{hucreler}"
                         f"<td class=s>{adet(k['adet'])}</td></tr>")
        govde = (f"<p>Dönem: {_donem(h)} · Ürün/iş: {e(h['urun_aciklama'])}</p><table><tr><th>S.No</th><th>Ad soyad"
                 f"</th><th>Tür</th>{bas}<th>Toplam</th></tr>{satirlar}</table>" + imza3)
        return _sayfa(baslik, govde, okul, h, yatay=True)
    elif tur == "ogretmen_bordro":
        govde = _bordro(h, hs, "Öğretmen") + imza3
    elif tur == "ogrenci_bordro":
        govde = _bordro(h, hs, "Öğrenci") + imza3
    elif tur == "muayene":
        govde = (f"<p>{e(h.get('cari'))} adına {e(h['siparis_no'])} numaralı sipariş kapsamında üretilen "
                 f"{adet(h['uretilen_miktar'])} {e(h['birim'])} {e(h['urun_aciklama'])} komisyonumuzca "
                 f"{tarih(h['bitis'])} tarihinde muayene edilmiş, siparişe ve teknik şartlara uygun olduğu "
                 "görülerek kabul edilmiştir.</p><p>İşbu tutanak birlikte imza altına alınmıştır.</p>"
                 + _imzalar(("", "Muayene Komisyonu Başkanı"), ("", "Üye"), ("", "Üye")))
    elif tur == "iban":
        satirlar = "".join(f"<tr><td>{i}</td><td>{e(k.get('ad_soyad'))}</td><td>{e(k.get('tckn'))}</td>"
                           f"<td>{e(k.get('iban'))}</td><td class=s>{tl(k['net'])}</td></tr>"
                           for i, k in enumerate((k for k in _kisiler(hs) if Decimal(k["net"]) > 0), 1))
        govde = (f"<p>{e(h['hakedis_no'])} numaralı hakediş net ödemelerinin aşağıdaki hesaplara aktarılmasını "
                 "rica ederiz.</p><table><tr><th>S.No</th><th>Ad soyad</th><th>T.C. kimlik no</th><th>IBAN</th>"
                 f"<th>Net tutar</th></tr>{satirlar}<tr class=t><td></td><td>TOPLAM</td><td></td><td></td>"
                 f"<td class=s>{tl(hs['toplam']['net'])}</td></tr></table>"
                 + _imzalar(("", "Sayman"), (mudur, "Okul Müdürü")))
    else:
        raise ValueError(f"Bilinmeyen belge: {tur}")
    return _sayfa(baslik, govde, okul, h)


def alim_ozet_html(okul: dict, fatura: dict, belgeler_katalog: dict | None = None) -> str:
    """Alış faturasına bağlı temin usulü ve belge kontrol özeti (GİB belgesi değildir)."""
    temin = fatura.get("temin_usulu") or "—"
    katalog = (belgeler_katalog or {}).get(temin) or []
    isaret = fatura.get("alim_belgeler") or {}
    if not katalog and isinstance(isaret, dict):
        katalog = [{"anahtar": k, "etiket": k, "zorunlu": False} for k in isaret]
    satirlar = "".join(
        f"<tr><td>{e(b.get('etiket'))}</td>"
        f"<td>{'Zorunlu' if b.get('zorunlu') else 'İsteğe bağlı'}</td>"
        f"<td>{'Var' if isaret.get(b.get('anahtar')) else 'Yok'}</td></tr>"
        for b in katalog)
    kalemler = "".join(
        f"<tr><td>{e(k.get('aciklama'))}</td><td class=s>{adet(k.get('miktar'))}</td>"
        f"<td class=s>{tl(k.get('tutar'))}</td></tr>"
        for k in fatura.get("kalemler") or [])
    govde = (
        f"<p><b>Temin usulü:</b> {e(temin)} · <b>Gider türü:</b> {e(fatura.get('gider_turu'))} · "
        f"<b>Belge türü:</b> {e(fatura.get('belge_turu'))}</p>"
        f"<p><b>Tedarikçi:</b> {e(fatura.get('cari_unvan'))} · <b>Belge no:</b> {e(fatura.get('belge_no'))} · "
        f"<b>Tarih:</b> {tarih(fatura.get('tarih'))}</p>"
        f"<p><b>Matrah:</b> {tl(fatura.get('matrah'))} TL · <b>KDV:</b> {tl(fatura.get('kdv'))} TL · "
        f"<b>Net:</b> {tl(fatura.get('net_tutar'))} TL</p>"
        "<h3>Kalemler</h3><table><tr><th>Açıklama</th><th>Miktar</th><th>Tutar</th></tr>"
        f"{kalemler or '<tr><td colspan=3>Kalem yok</td></tr>'}</table>"
        "<h3>Alım belge kontrol listesi</h3>"
        "<table><tr><th>Belge</th><th>Zorunluluk</th><th>Dosyada</th></tr>"
        f"{satirlar or '<tr><td colspan=3>Liste yok</td></tr>'}</table>"
        "<p class='kucuk'>Bu özet DÖSE iç kaydıdır; ihale dosyasının asılları ayrıca saklanır. "
        "GİB e-Fatura gönderimi değildir.</p>"
        + _imzalar(("", "Sayman"), ("", "Gerçekleştirme Görevlisi"), ("", "Harcama Yetkilisi"))
    )
    return _sayfa("Mal / hizmet alım belge özeti", govde, okul, fatura)


def belge_klasoru() -> Path:
    kok = Path(os.environ.get("DOSE_BELGE_KLASORU") or Path.home() / "Documents" / "DÖSE Belgeler")
    kok.mkdir(parents=True, exist_ok=True)
    return kok


def belge_kaydet(tur: str, okul: dict, h: dict, klasor: Path | None = None) -> Path:
    yol = (klasor or belge_klasoru()) / f"{re.sub(r'[^A-Za-z0-9_-]', '_', belge_no(h))}_{tur}.html"
    yol.write_text(belge_html(tur, okul, h), encoding="utf-8")
    return yol


def belge_menusu(app, okul: dict, h: dict, liste: list[tuple[str, str]] | None = None):
    async def ac(tur: str):
        try:
            yol = belge_kaydet(tur, okul, h)
        except (OSError, KeyError, ValueError, ArithmeticError) as hata:
            app.bildir(f"Belge oluşturulamadı: {hata}", hata=True)
            return
        try:
            sonuc = ft.UrlLauncher().launch_url(yol.as_uri())
            if inspect.isawaitable(sonuc):
                await sonuc
            app.bildir(f"{BELGE_ADI[tur]} açıldı: {yol}")
        except Exception:  # noqa: BLE001 - opening is best effort; the file is already saved
            app.bildir(f"{BELGE_ADI[tur]} kaydedildi: {yol}")

    app.page.show_dialog(ft.AlertDialog(
        title=ft.Text(f"{belge_no(h)} belgeleri"),
        content=ft.Column([ft.Text("Belgeler tarayıcıda açılır; oradan yazdırabilir veya PDF olarak kaydedebilirsiniz.",
                                   size=12)]
                          + [ft.TextButton(ad, icon=ft.Icons.DESCRIPTION,
                                           on_click=lambda _, t=tur: app.page.run_task(ac, t))
                             for tur, ad in (liste or BELGELER)], tight=True, scroll=ft.ScrollMode.AUTO),
        actions=[ft.TextButton("Kapat", on_click=lambda _: app.page.pop_dialog())]))
