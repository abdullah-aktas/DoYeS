"""Resmi belge ve formların PDF olarak üretilmesi."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from . import mevzuat
from .db import al
from .hesap import kalem_tutari, oran_yazi, para, yuvarla
from .pdf import (P, S_ALT_BASLIK, S_BASLIK, S_KUCUK, S_METIN, S_NORMAL, S_ORTA, S_ORTA_B, PageBreak, Spacer, antet,
                  bilgi_tablosu, imza_blogu, mm, olustur, tablo, tarih_tr)


def _kurum():
    return al().kurum()


def _imzalar_standart(k: dict, sef: str | None = None, sayman=False, sef_unvan="Bölüm/Atölye Şefi"):
    liste = []
    if sef is not None:
        liste.append((sef_unvan, sef))
    liste.append(("Gerçekleştirme Görevlisi", k.get("gerceklestirme_gorevlisi")))
    if sayman:
        liste.append(("Sayman", k.get("sayman")))
    liste.append(("Harcama Yetkilisi\nOkul Müdürü", k.get("harcama_yetkilisi")))
    return [(u.replace("\n", "<br/>"), a) for u, a in liste]


def _sef(bolum_id) -> str | None:
    if not bolum_id:
        return None
    r = al().q1("SELECT ad_soyad FROM personel WHERE bolum_id = ? AND aktif = 1 AND dose_gorevi IN "
                "('Bölüm/Alan Şefi', 'Atölye/Laboratuvar Şefi') ORDER BY dose_gorevi LIMIT 1", (bolum_id,))
    return r["ad_soyad"] if r else None


# ---------------------------------------------------------------- fiyat tespit
def fiyat_tespit_tutanagi(yol: Path, urun: dict, kalemler: list[dict], ozet: dict, piyasa: str = "") -> Path:
    k = _kurum()
    parca = antet(k)
    parca += [P("MAL / HİZMET MALİYET VE SATIŞ FİYATI TESPİT TUTANAĞI", S_BASLIK),
              bilgi_tablosu([
                  ("Ürün / hizmet", f"{urun.get('kod') or ''} {urun['ad']}"),
                  ("Birim", urun.get("birim") or ""),
                  ("Bölüm / atölye", urun.get("bolum_ad") or ""),
                  ("Ücret ödeme esası", urun.get("ucret_esasi") or ""),
                  ("Tespit tarihi", tarih_tr(date.today())),
              ]), Spacer(1, 4 * mm), P("1. Birim Maliyet Unsurları", S_ALT_BASLIK)]
    satirlar = [[i + 1, kl["kalem_turu"], kl.get("aciklama") or "", kl["miktar"], kl["birim_fiyat"],
                 yuvarla(kl["miktar"] * kl["birim_fiyat"])] for i, kl in enumerate(kalemler)]
    parca.append(tablo(["S.No", "Maliyet unsuru", "Açıklama", "Miktar", "Birim fiyat", "Tutar (TL)"], satirlar,
                       [12 * mm, 45 * mm, 50 * mm, 18 * mm, 22 * mm, 25 * mm], {3, 4, 5},
                       ["", "", "BİRİM MALİYET TOPLAMI", "", "", ozet["birim_maliyet"]]))
    parca += [Spacer(1, 4 * mm), P("2. Satış Fiyatının Belirlenmesi", S_ALT_BASLIK),
              bilgi_tablosu([
                  ("Birim maliyet", para(ozet["birim_maliyet"]) + " TL"),
                  ("Kâr oranı / tutarı", f"{oran_yazi(ozet['kar_orani'])}  /  {para(ozet['kar'])} TL"),
                  ("KDV hariç birim satış fiyatı", para(ozet["satis_fiyati"]) + " TL"),
                  ("KDV oranı / tutarı", f"{oran_yazi(ozet['kdv_orani'])}  /  {para(ozet['kdv'])} TL"),
                  ("KDV dahil birim satış fiyatı", f"<b>{para(ozet['kdv_dahil'])} TL</b>"),
              ])]
    if piyasa:
        parca += [Spacer(1, 3 * mm), P("3. Piyasa Araştırması / Değerlendirme", S_ALT_BASLIK), P(piyasa, S_METIN)]
    parca += [Spacer(1, 4 * mm), P(
        "Yukarıda maliyet unsurları gösterilen mal/hizmetin birim satış fiyatı; üretilecek mal veya hizmetin özelliği, "
        "miktarı ve süresi ile üretimde kullanılacak makine, teçhizat, demirbaş, elektrik, gaz, su, işçilik, öğrenci hakkı "
        "ve benzeri giderler ile piyasa şartları göz önünde bulundurularak belirlenmiş olup, MEB Döner Sermaye "
        "İşletmelerinde Üretimi Teşvik Primi Dağıtımı, Parça Başı Üretim, Atölye ve Tesislerin Özel Sektörle İşbirliği "
        "Yapılarak İşletilmesi Hakkında Yönetmeliğin 10 uncu maddesi gereğince gerçekleştirme görevlisinin teklifi ve "
        "harcama yetkilisinin onayı ile kesinleşir.", S_METIN)]
    parca.append(imza_blogu([("Tespit Eden<br/>Bölüm/Atölye Şefi", _sef(urun.get("bolum_id"))),
                             ("Teklif Eden<br/>Gerçekleştirme Görevlisi", k.get("gerceklestirme_gorevlisi")),
                             ("ONAY<br/>Harcama Yetkilisi", k.get("harcama_yetkilisi"))], 3, True))
    return olustur(yol, parca, baslik="Fiyat Tespit Tutanağı")


# ---------------------------------------------------------------- sipariş belgeleri
def _siparis_bilgi(s_id: int):
    db = al()
    s = db.q1("""SELECT s.*, c.unvan, c.vergi_dairesi, c.vkn_tckn, c.adres, c.telefon, c.kamu_kurumu, b.ad bolum_ad
                 FROM siparis s LEFT JOIN cari c ON c.id = s.cari_id LEFT JOIN bolum b ON b.id = s.bolum_id
                 WHERE s.id = ?""", (s_id,))
    kalemler = db.q("SELECT k.*, u.ad urun_ad FROM siparis_kalem k LEFT JOIN urun u ON u.id = k.urun_id "
                    "WHERE k.siparis_id = ?", (s_id,))
    return s, kalemler


def _kalem_tablosu(kalemler, kdv_orani):
    satirlar, toplam, brut_toplam, iskonto_toplam = [], 0.0, 0.0, 0.0
    for i, kl in enumerate(kalemler):
        brut, iskonto, t = kalem_tutari(kl)
        toplam += t
        brut_toplam += brut
        iskonto_toplam += iskonto
        satirlar.append([i + 1, kl.get("urun_ad") or "", kl.get("aciklama") or "", kl["miktar"], kl.get("birim") or "",
                         kl["birim_fiyat"], iskonto, t])
    toplam, kdv = yuvarla(toplam), yuvarla(toplam * kdv_orani)
    if iskonto_toplam:
        t = tablo(["S.No", "Mal / hizmet", "Açıklama", "Miktar", "Birim", "Birim fiyat", "İskonto", "Tutar"], satirlar,
                  [10 * mm, 36 * mm, 38 * mm, 15 * mm, 13 * mm, 20 * mm, 18 * mm, 22 * mm], {3, 5, 6, 7})
        ust = [("Ara toplam (iskontosuz)", para(brut_toplam) + " TL"), ("İskonto", para(iskonto_toplam) + " TL")]
    else:
        t = tablo(["S.No", "Mal / hizmet", "Açıklama", "Miktar", "Birim", "Birim fiyat", "Tutar"],
                  [s[:6] + s[7:] for s in satirlar], [11 * mm, 40 * mm, 45 * mm, 17 * mm, 15 * mm, 20 * mm, 24 * mm], {3, 5, 6})
        ust = []
    ozet = bilgi_tablosu(ust + [("Toplam (KDV hariç)", para(toplam) + " TL"), (f"KDV ({oran_yazi(kdv_orani)})", para(kdv) + " TL"),
                                ("Genel toplam (KDV dahil)", f"<b>{para(toplam + kdv)} TL</b>")], (125 * mm, 45 * mm))
    return t, ozet, toplam, kdv


def teklif_mektubu(yol: Path, s_id: int) -> Path:
    s, kalemler = _siparis_bilgi(s_id)
    k = _kurum()
    parca = antet(k, f"{k.get('evrak_kodu') or ''}", "Fiyat Teklifi", s["tarih"])
    parca += [P(f"<b>{s['unvan'] or ''}</b>"), Spacer(1, 4 * mm),
              P(f"Tarafınızca talep edilen \"{s['konu'] or ''}\" işine ilişkin, okulumuz Döner Sermaye İşletmesince öğrencilerimizin "
                f"uygulamalı eğitimi kapsamında üretilecek mal/hizmetin fiyat teklifimiz aşağıda sunulmuştur.", S_METIN),
              Spacer(1, 3 * mm)]
    t, ozet, _, _ = _kalem_tablosu(kalemler, s["kdv_orani"] or 0)
    parca += [t, Spacer(1, 2 * mm), ozet, Spacer(1, 4 * mm)]
    if s.get("kamu_kurumu"):
        parca.append(P("İdareniz, 4734 sayılı Kamu İhale Kanununun 3 üncü maddesinin (e) bendi gereğince Bakanlığımıza bağlı "
                       "döner sermaye işletmelerinden mal ve hizmet alımlarını ihale yapmaksızın gerçekleştirebilir. İşin, "
                       "işletmemizce bizzat üretileceğini taahhüt ederiz.", S_METIN))
    parca.append(P(f"Teslim süresi: {tarih_tr(s['teslim_tarihi']) or 'sözleşmede belirtilecektir'}. Teklifimiz 30 gün geçerlidir.", S_METIN))
    parca.append(imza_blogu([("Harcama Yetkilisi<br/>Okul Müdürü", k.get("harcama_yetkilisi"))], 1))
    return olustur(yol, parca, baslik="Fiyat Teklifi")


def siparis_sozlesmesi(yol: Path, s_id: int, tahsis) -> Path:
    s, kalemler = _siparis_bilgi(s_id)
    k = _kurum()
    parca = antet(k)
    parca += [P("MAL / HİZMET ÜRETİM SÖZLEŞMESİ", S_BASLIK), P(f"Sözleşme No: {s['siparis_no']}", S_ORTA), Spacer(1, 3 * mm)]
    parca.append(P("<b>Madde 1 - Taraflar</b>"))
    parca.append(bilgi_tablosu([
        ("İşletme", f"{k.get('okul_adi') or ''} {k.get('isletme_adi') or ''}<br/>VKN: {k.get('vkn') or ''} - {k.get('vergi_dairesi') or ''}<br/>{k.get('adres') or ''}"),
        ("İşi yaptıran", f"{s['unvan'] or ''}<br/>VKN/TCKN: {s['vkn_tckn'] or ''} - {s['vergi_dairesi'] or ''}<br/>{s['adres'] or ''}"),
    ]))
    parca += [Spacer(1, 3 * mm), P("<b>Madde 2 - İşin konusu ve bedeli</b>"),
              P(f"{s['konu'] or ''} (Bölüm/atölye: {s['bolum_ad'] or ''}; ücret esası: {s['ucret_esasi'] or ''})", S_NORMAL),
              Spacer(1, 2 * mm)]
    t, ozet, _, _ = _kalem_tablosu(kalemler, s["kdv_orani"] or 0)
    parca += [t, Spacer(1, 2 * mm), ozet, Spacer(1, 3 * mm)]
    maddeler = [
        f"<b>Madde 3 - Süre:</b> İşe {tarih_tr(s['baslama_tarihi']) or 'sözleşme tarihinde'} başlanır, "
        f"{tarih_tr(s['teslim_tarihi']) or '....'} tarihinde teslim edilir. Sözleşme imzalanmadan işe başlanmaz (Yön. md.9/4).",
        f"<b>Madde 4 - Ödeme:</b> Peşinat {para(s['pesinat'] or 0)} TL olup kalan bedel mal/hizmet teslim edildikçe fatura "
        f"karşılığı işletmenin {k.get('banka') or ''} {k.get('iban') or ''} IBAN numaralı hesabına ödenir."
        + (f" Sözleşme bedelinin en az {oran_yazi(tahsis['pesin_orani'])}'i peşin tahsil edilir." if tahsis.get("pesin_orani") else ""),
        "<b>Madde 5 - Uygulamalı eğitim:</b> İş, okulun öğrenci/kursiyerlerinin beceri eğitimi kapsamında, işletme "
        "atölyelerinde bizzat üretilir.",
        "<b>Madde 6 - Muayene ve kabul:</b> Teslim edilen mal/hizmet işi yaptıran tarafça muayene edilerek tutanakla kabul edilir.",
    ]
    if s["ucret_esasi"] and s["ucret_esasi"].startswith(("Özel", "Tesis")):
        maddeler += [
            "<b>Madde 7 - Malzeme:</b> Mal üretiminde kullanılacak ilk madde, malzeme, yarı mamul, proje, kalıp ve benzeri her türlü "
            "malzeme işi yaptıran tarafça sağlanır; işletme yalnızca atölye, makine parkı, elektrik, gaz, su, avadanlık ve işçiliği "
            "karşılar. Getirilen malzeme zimmetle teslim alınır, mamul hâline getirildikten sonra zimmetle teslim edilir (Yön. md.9/3, 11/6).",
            "<b>Madde 8 - Kira yasağı:</b> Bu işbirliği hiçbir şekilde kira uygulaması şeklinde olamaz; büro, depo ve benzeri amaçlarla "
            "yer tahsisi yapılamaz (Yön. md.9/1, 9/3).",
            "<b>Madde 9 - Zarar:</b> Teslim alınan malzemenin zarar görmesi hâlinde zarar sebebiyet verene tazmin ettirilir (Yön. md.11/7).",
        ]
    maddeler.append("<b>Son madde - Uyuşmazlık:</b> Bu sözleşmeden doğan uyuşmazlıklarda işletmenin bulunduğu yer mahkemeleri ve "
                    "icra daireleri yetkilidir. İşbu sözleşme iki nüsha olarak düzenlenip taraflarca imzalanmıştır.")
    for m in maddeler:
        parca += [P(m, S_METIN), Spacer(1, 1.5 * mm)]
    parca.append(imza_blogu([("İşi Yaptıran", s["unvan"]), ("Gerçekleştirme Görevlisi", k.get("gerceklestirme_gorevlisi")),
                             ("Harcama Yetkilisi", k.get("harcama_yetkilisi"))], 3, True))
    return olustur(yol, parca, baslik="Sözleşme")


def gorevlendirme_onayi(yol: Path, s_id: int) -> Path:
    db = al()
    s, _ = _siparis_bilgi(s_id)
    k = _kurum()
    gorevliler = db.q("""SELECT g.*, CASE WHEN g.kisi_turu = 'Personel' THEN p.ad_soyad ELSE o.ad_soyad END ad,
                                CASE WHEN g.kisi_turu = 'Personel' THEN p.kadro_unvani ELSE o.sinif END unvan
                         FROM siparis_gorevli g LEFT JOIN personel p ON g.kisi_turu = 'Personel' AND p.id = g.kisi_id
                         LEFT JOIN ogrenci o ON g.kisi_turu = 'Öğrenci' AND o.id = g.kisi_id
                         WHERE g.siparis_id = ? ORDER BY g.kisi_turu DESC, ad""", (s_id,))
    parca = antet(k, f"{k.get('evrak_kodu') or ''}", "DÖSE Üretim Görevlendirmesi", s["tarih"])
    parca += [P("MÜDÜRLÜK MAKAMINA", S_ORTA), Spacer(1, 4 * mm),
              P(f"Okulumuz Döner Sermaye İşletmesince {s['unvan'] or ''} için {s['siparis_no']} numaralı \"{s['konu'] or ''}\" "
                f"işi {s['ucret_esasi'] or ''} esasına göre üretilecektir. Söz konusu işin üretiminde aşağıda adı yazılı personel "
                f"ve beceri eğitimi kapsamında öğrencilerin görevlendirilmesi hususunu olurlarınıza arz ederim.", S_METIN),
              Spacer(1, 4 * mm)]
    satirlar = [[i + 1, g["kisi_turu"], g["ad"] or "", g["unvan"] or "", g["gorev"] or ""] for i, g in enumerate(gorevliler)]
    parca.append(tablo(["S.No", "Tür", "Adı soyadı", "Unvan / sınıf", "Görevi"], satirlar,
                       [12 * mm, 22 * mm, 50 * mm, 40 * mm, 48 * mm]))
    parca += [Spacer(1, 3 * mm), P("Öğrencilerin parça başı ücretli işlerde çalıştırılmasında velilerinin yazılı muvafakati "
                                   "alınmıştır (Yön. md.8/1).", S_KUCUK)]
    parca.append(imza_blogu([("Gerçekleştirme Görevlisi", k.get("gerceklestirme_gorevlisi"))], 1))
    parca += [Spacer(1, 6 * mm), P("<b>OLUR</b>", S_ORTA), P(tarih_tr(date.today()), S_ORTA)]
    parca.append(imza_blogu([("Harcama Yetkilisi<br/>Okul Müdürü", k.get("harcama_yetkilisi"))], 1))
    return olustur(yol, parca, baslik="Görevlendirme Onayı")


def muayene_kabul_tutanagi(yol: Path, s_id: int) -> Path:
    s, kalemler = _siparis_bilgi(s_id)
    k = _kurum()
    parca = antet(k)
    parca += [P("MUAYENE VE KABUL (TESLİM) TUTANAĞI", S_BASLIK),
              bilgi_tablosu([("Sipariş / sözleşme no", s["siparis_no"]), ("İşi yaptıran", s["unvan"] or ""),
                             ("İşin konusu", s["konu"] or ""), ("Bölüm / atölye", s["bolum_ad"] or ""),
                             ("Kabul tarihi", tarih_tr(s["kabul_tarihi"] or date.today()))]), Spacer(1, 4 * mm)]
    t, ozet, _, _ = _kalem_tablosu(kalemler, s["kdv_orani"] or 0)
    parca += [t, Spacer(1, 2 * mm), ozet, Spacer(1, 4 * mm),
              P("Yukarıda cinsi ve miktarı belirtilen mal/hizmet, sözleşme ve eklerinde belirtilen şartlara uygun olarak "
                "üretilmiş, yapılan muayenesi sonucunda eksiksiz ve kusursuz olduğu görülerek teslim alınmıştır. Bu işe ait "
                "işçilik; geçici muayene ve kabulü yapılan iş üzerinden hak sahiplerine ödenecektir (Yön. md.8/8-a).", S_METIN)]
    parca.append(imza_blogu([("Teslim Eden<br/>Bölüm/Atölye Şefi", _sef(s["bolum_id"])),
                             ("Teslim Eden<br/>Gerçekleştirme Görevlisi", k.get("gerceklestirme_gorevlisi")),
                             ("Teslim Alan", s["unvan"])], 3, True))
    return olustur(yol, parca, baslik="Muayene Kabul Tutanağı")


def on_maliyet_cizelgesi(yol: Path, s_id: int, t, p: dict) -> Path:
    """Sözleşme bedelinin kâr, faaliyet gideri, malzeme, işçilik ve öğrenci hakkına tahsisi ile görevli başına tahmini
    payların gösterildiği ön maliyet (işçilik tespit) çizelgesi. t: hesap.SiparisTahsis"""
    from .hesap import esas_kurallari, parca_basi_tavani
    db = al()
    s, kalemler = _siparis_bilgi(s_id)
    k = _kurum()
    kural = esas_kurallari(s["ucret_esasi"], p)
    bedel, kdv_o = t.bedel, s["kdv_orani"] or 0
    kdv = yuvarla(bedel * kdv_o)
    oran = lambda x: oran_yazi(x / bedel) if bedel else ""
    malz_o = p.get("malzeme_azami_orani") or 0
    parca = antet(k)
    parca += [P("SİPARİŞ ÖN MALİYET VE İŞÇİLİK TESPİT ÇİZELGESİ", S_BASLIK),
              bilgi_tablosu([("Sipariş / sözleşme no", s["siparis_no"] or ""), ("Tarih", tarih_tr(s["tarih"])),
                             ("İşi yaptıran", s["unvan"] or ""), ("İşin konusu", s["konu"] or ""),
                             ("Bölüm / atölye", s["bolum_ad"] or ""), ("Ücret ödeme esası", s["ucret_esasi"] or "")]),
              Spacer(1, 4 * mm)]
    no = 1
    if kalemler:
        tb, _, _, _ = _kalem_tablosu(kalemler, kdv_o)
        parca += [P(f"{no}. Sipariş Kalemleri", S_ALT_BASLIK), tb, Spacer(1, 4 * mm)]
        no += 1
    ogr_pay = oran_yazi(t.ogrenci_hakki / t.iscilik) if t.iscilik else ""
    satirlar = [
        ["Sözleşme bedeli (KDV hariç)", "%100", bedel, ""],
        ["Kâr", oran(t.kar), t.kar, f"En az {oran_yazi(kural['kar'])} ({kural['dayanak']})" if kural["kar"] else ""],
        ["Faaliyet gideri", oran(t.faaliyet), t.faaliyet,
         f"{oran_yazi(kural['faaliyet'])} ({kural['dayanak']})" if kural["faaliyet"] else ""],
        ["İlk madde ve malzeme", oran(t.malzeme), t.malzeme,
         "İşi yaptırandan sağlanır" if s["malzeme_musteriden"] else (f"En çok {oran_yazi(malz_o)}" if malz_o else "")],
        ["Ayrılabilecek azami işçilik", oran(t.azami_iscilik), t.azami_iscilik, "Bedel - kâr - faaliyet gideri - malzeme"],
        ["İşçilik (ödemeye esas)", oran(t.iscilik), t.iscilik, "Şartnamedeki tutarı aşamaz (Yön. md.8/4)"],
        ["     Öğrenci hakkı", oran(t.ogrenci_hakki), t.ogrenci_hakki,
         f"İşçiliğin {ogr_pay}'i; en az {oran_yazi(p['ogrenci_hakki_orani'])} (Yön. md.8/3)" if t.ogrenci_hakki else ""],
        ["     Personel işçilik payı", oran(t.personel_iscilik), t.personel_iscilik, ""],
        [f"KDV ({oran_yazi(kdv_o)})", "", kdv, ""],
    ]
    parca += [P(f"{no}. Bedelin Tahsisi", S_ALT_BASLIK),
              tablo(["Kalem", "Bedele oranı", "Tutar (TL)", "Açıklama / dayanak"], satirlar,
                    [55 * mm, 22 * mm, 28 * mm, 65 * mm], {2},
                    ["Fatura tutarı (KDV dahil)", "", yuvarla(bedel + kdv), ""]),
              Spacer(1, 1.5 * mm),
              P(f"Aylık tahsilatın %{p['hazine_payi_orani'] * 100:g}'i olan hazine payı (genel bütçeye aktarılan pay) faaliyet "
                f"gideri payından karşılanır (Yön. md.10/4, md.12/1-e). SHÇEK payı, yıl sonunda yıllık brüt hasılatın "
                f"%{p['shcek_orani'] * 100:g}'i olarak işletmece ödenir (2828 s.K. md.18/1-k). Bu paylar işçilikten ayrıca "
                f"düşülmez; Yönetmelik sipariş bedelinden kâr, faaliyet gideri ve malzeme dışında pay ayrılmasını öngörmez.",
                S_KUCUK),
              Spacer(1, 4 * mm)]
    no += 1
    gorevliler = db.q("""SELECT g.kisi_turu, CASE WHEN g.kisi_turu = 'Personel' THEN p.ad_soyad ELSE o.ad_soyad END ad,
                                CASE WHEN g.kisi_turu = 'Personel' THEN p.hizmet_sinifi ELSE o.sinif END sinif
                         FROM siparis_gorevli g LEFT JOIN personel p ON g.kisi_turu = 'Personel' AND p.id = g.kisi_id
                         LEFT JOIN ogrenci o ON g.kisi_turu = 'Öğrenci' AND o.id = g.kisi_id
                         WHERE g.siparis_id = ? ORDER BY CASE WHEN g.kisi_turu = 'Personel' THEN 0 ELSE 1 END, ad""",
                      (s_id,))
    if s["ucret_esasi"] and not s["ucret_esasi"].startswith("Fazla"):
        parca.append(P(f"{no}. Görevli Başına Tahmini Pay (eşit katkı varsayımıyla)", S_ALT_BASLIK))
        n_per = sum(1 for g in gorevliler if g["kisi_turu"] == "Personel")
        n_ogr = sum(1 for g in gorevliler if g["kisi_turu"] == "Öğrenci")
        if gorevliler:
            veri = []
            for i, g in enumerate(gorevliler):
                ogrenci = g["kisi_turu"] == "Öğrenci"
                pay = yuvarla((t.ogrenci_hakki / n_ogr) if ogrenci else (t.personel_iscilik / n_per))
                tavan = parca_basi_tavani(g["kisi_turu"], None if ogrenci else g["sinif"], p)
                veri.append([i + 1, g["kisi_turu"], g["ad"] or "", g["sinif"] or "", pay, tavan,
                             "AŞIYOR" if pay > tavan + 0.005 else ""])
            parca.append(tablo(["No", "Tür", "Adı soyadı", "Hizmet sınıfı / sınıf", "Tahmini brüt", "Aylık tavan", "Tavan"],
                               veri, [10 * mm, 17 * mm, 38 * mm, 49 * mm, 21 * mm, 21 * mm, 14 * mm], {4, 5}, yazi_boyu=7.5))
        else:
            parca.append(P("Siparişe henüz görevli personel/öğrenci eklenmemiştir.", S_METIN))
        parca += [Spacer(1, 2 * mm), P(
            "Kesin dağılım; ay içinde bitirilen ve geçici muayene ve kabulü yapılan iş üzerinden, personel ve öğrencilerin "
            "üretime katkıları (parça adedi) oranında yapılır (Yön. md.8/8). Aylık tavan, aynı ay içinde diğer siparişlerden "
            "alınan parça başı ücretlerle birlikte uygulanır (Yön. md.8/5-6).", S_KUCUK), Spacer(1, 3 * mm)]
        no += 1
    parca.append(P(f"{no}. Mevzuat Kontrolü", S_ALT_BASLIK))
    if t.hatalar or t.uyarilar:
        parca += [P(f"<b>HATA:</b> {h}", S_METIN) for h in t.hatalar]
        parca += [P(f"<b>Uyarı:</b> {u}", S_METIN) for u in t.uyarilar]
    else:
        parca.append(P("Bedelin tahsisi Yönetmelikte öngörülen oranlara uygundur.", S_METIN))
    parca.append(imza_blogu([("Hazırlayan<br/>Bölüm/Atölye Şefi", _sef(s["bolum_id"])),
                             ("Gerçekleştirme Görevlisi", k.get("gerceklestirme_gorevlisi")),
                             ("Sayman", k.get("sayman"))], 3, True))
    parca += [Spacer(1, 4 * mm), P("<b>UYGUNDUR</b>", S_ORTA), P(tarih_tr(date.today()), S_ORTA),
              imza_blogu([("Harcama Yetkilisi<br/>Okul Müdürü", k.get("harcama_yetkilisi"))], 1)]
    return olustur(yol, parca, baslik="Ön Maliyet Çizelgesi")


def _komisyon(s_id: int, bolum_id) -> list[tuple[str, str]]:
    """Geçici muayene ve kabul komisyonu: bölüm şefi ve siparişte görevli personel (en çok 3 kişi)."""
    db = al()
    uyeler, gorulen = [], set()
    sef = db.q1("SELECT id, ad_soyad, COALESCE(kadro_unvani, dose_gorevi) unvan FROM personel WHERE bolum_id = ? AND aktif = 1 "
                "AND dose_gorevi IN ('Bölüm/Alan Şefi', 'Atölye/Laboratuvar Şefi') ORDER BY dose_gorevi LIMIT 1", (bolum_id or 0,))
    adaylar = ([sef] if sef else []) + db.q(
        """SELECT p.id, p.ad_soyad, COALESCE(p.kadro_unvani, p.dose_gorevi) unvan FROM siparis_gorevli g
           JOIN personel p ON p.id = g.kisi_id WHERE g.siparis_id = ? AND g.kisi_turu = 'Personel' ORDER BY p.ad_soyad""", (s_id,))
    for a in adaylar:
        if a["id"] not in gorulen and len(uyeler) < 3:
            gorulen.add(a["id"])
            uyeler.append((("Başkan" if not uyeler else "Üye") + f"<br/>{a['unvan'] or ''}", a["ad_soyad"]))
    while len(uyeler) < 3:
        uyeler.append(("Başkan" if not uyeler else "Üye", None))
    return uyeler


def gecici_kabul_tutanagi(yol: Path, s_id: int) -> Path:
    """Okul komisyonunca düzenlenen geçici muayene ve kabul tutanağı; parça başı ödemesinin dayanağıdır (Yön. md.8/8-a)."""
    s, kalemler = _siparis_bilgi(s_id)
    k = _kurum()
    bitis = s["kabul_tarihi"] or s["teslim_tarihi"]
    kabul_edildi = bool(s["kabul_tarihi"])
    parca = antet(k)
    parca += [P("GEÇİCİ MUAYENE VE KABUL TUTANAĞI", S_BASLIK), P(f"({s['bolum_ad'] or ''})", S_ORTA), Spacer(1, 2 * mm),
              bilgi_tablosu([("Sipariş / sözleşme no", s["siparis_no"] or ""), ("İşi yaptıran", s["unvan"] or ""),
                             ("İşin adı", s["konu"] or ""), ("Ücret ödeme esası", s["ucret_esasi"] or ""),
                             ("İşe başlama tarihi", tarih_tr(s["baslama_tarihi"]) or "..../..../20...."),
                             ("İşin bitirilme tarihi", tarih_tr(bitis) or "..../..../20....")]),
              Spacer(1, 3 * mm), P("Üretimi Tamamlanan İş", S_ALT_BASLIK)]
    veri = [[i + 1, kl.get("urun_ad") or kl.get("aciklama") or "", kl.get("aciklama") if kl.get("urun_ad") else "",
             kl.get("birim") or "", kl["miktar"], kl["miktar"] if kabul_edildi else ""] for i, kl in enumerate(kalemler)]
    veri += [[len(veri) + i + 1, "", "", "", "", ""] for i in range(max(0, 3 - len(veri)))]
    parca.append(tablo(["S.No", "Mal / hizmet", "Açıklama", "Birim", "Sipariş miktarı", "Kabul edilen miktar"], veri,
                       [11 * mm, 50 * mm, 45 * mm, 16 * mm, 24 * mm, 24 * mm], {4, 5}))
    parca += [Spacer(1, 3 * mm), P(
        f"Okulumuz Döner Sermaye İşletmesince siparişi alınan yukarıda cinsi ve miktarı belirtilen işin imalatına "
        f"{tarih_tr(s['baslama_tarihi']) or '..../..../20....'} tarihinde başlanmış, {tarih_tr(bitis) or '..../..../20....'} "
        f"tarihinde bitirilmiştir. İmalatı tamamlanan işin komisyonumuzca muayenesi yapılmış; sözleşme ve eklerine uygun, sağlam "
        f"ve noksansız olduğu görülerek geçici kabulü yapılmıştır. Bu işe ait işçilik bedeli, geçici muayene ve kabulü yapılan iş "
        f"üzerinden hak sahiplerine ödenecektir (Yön. md.8/8-a).", S_METIN),
        P("GEÇİCİ MUAYENE VE KABUL KOMİSYONU", S_ORTA_B)]
    parca.append(imza_blogu(_komisyon(s_id, s["bolum_id"]), 3, True))
    parca += [Spacer(1, 4 * mm), P("<b>ONAY</b>", S_ORTA), P("..../..../20....", S_ORTA),
              imza_blogu([("Harcama Yetkilisi<br/>Okul Müdürü", k.get("harcama_yetkilisi"))], 1),
              Spacer(1, 3 * mm),
              P("Not: Tutanak her sipariş (kısmi teslimlerde her teslim) için üç nüsha düzenlenir; onaylı bir nüshası parça başı "
                "ücret bordrosu ve puantaj cetveline eklenir.", S_KUCUK)]
    return olustur(yol, parca, baslik="Geçici Muayene ve Kabul Tutanağı")


def siparis_malzeme_listesi(yol: Path, s_id: int, p: dict) -> Path:
    """Siparişe stoktan çıkışı yapılan ilk madde ve malzeme listesi; ön maliyetteki tutar ve azami oranla karşılaştırılır."""
    db = al()
    s, _ = _siparis_bilgi(s_id)
    k = _kurum()
    hareketler = db.q("""SELECT h.tarih, h.miktar, h.birim_fiyat, h.aciklama, m.ad, m.birim, m.kdv_orani
                         FROM stok_hareket h JOIN malzeme m ON m.id = h.malzeme_id
                         WHERE h.siparis_id = ? AND h.yon = 'Çıkış' AND COALESCE(h.kaynak, '') != 'Fatura'
                         ORDER BY h.tarih, h.id""", (s_id,))
    veri, toplam, kdv_top = [], 0.0, 0.0
    for i, h in enumerate(hareketler):
        tutar = yuvarla(h["miktar"] * (h["birim_fiyat"] or 0))
        kdv = yuvarla(tutar * (h["kdv_orani"] or 0))
        toplam, kdv_top = toplam + tutar, kdv_top + kdv
        veri.append([i + 1, tarih_tr(h["tarih"]), h["ad"] + (f" ({h['aciklama']})" if h["aciklama"] else ""), h["miktar"],
                     h["birim"] or "", h["birim_fiyat"] or 0, oran_yazi(h["kdv_orani"] or 0), kdv, tutar])
    toplam, kdv_top = yuvarla(toplam), yuvarla(kdv_top)
    bedel = s["sozlesme_bedeli"] or 0
    malz_o = p.get("malzeme_azami_orani") or 0
    parca = antet(k)
    parca += [P("SİPARİŞTE KULLANILAN İLK MADDE VE MALZEME LİSTESİ", S_BASLIK),
              bilgi_tablosu([("Sipariş / sözleşme no", s["siparis_no"] or ""), ("İşi yaptıran", s["unvan"] or ""),
                             ("İşin konusu", s["konu"] or ""), ("Bölüm / atölye", s["bolum_ad"] or "")]),
              Spacer(1, 3 * mm)]
    if veri:
        parca.append(tablo(["No", "Tarih", "Cinsi ve özellikleri", "Miktar", "Birim", "Birim fiyat", "KDV %", "KDV", "Tutar"],
                           veri, [10 * mm, 18 * mm, 50 * mm, 15 * mm, 12 * mm, 18 * mm, 13 * mm, 15 * mm, 19 * mm],
                           {3, 5, 7, 8}, ["", "", "TOPLAM (KDV hariç tutar / KDV)", "", "", "", "", kdv_top, toplam], 7.5))
    else:
        parca.append(P("Bu siparişe stoktan malzeme çıkışı kaydedilmemiştir (Stok ekranı → Çıkış, sipariş seçilerek).", S_METIN))
    satirlar = [("Stoktan çıkan malzeme (KDV hariç)", para(toplam) + " TL"),
                ("Ön maliyette öngörülen malzeme", para(s["malzeme_maliyeti"] or 0) + " TL"),
                ("Sipariş bedeli (KDV hariç)", para(bedel) + " TL")]
    if malz_o and bedel:
        sinir = yuvarla(bedel * malz_o)
        durum = "UYGUN" if toplam <= sinir + 0.005 else "SINIR AŞILDI"
        satirlar.append((f"Üst sınır ({oran_yazi(malz_o)})", f"{para(sinir)} TL - <b>{durum}</b>"))
    parca += [Spacer(1, 3 * mm), bilgi_tablosu(satirlar, (80 * mm, 90 * mm))]
    if s["malzeme_maliyeti"] and toplam > (s["malzeme_maliyeti"] or 0) + 0.005:
        parca.append(P("Kullanılan malzeme ön maliyette öngörülen tutarı aşmıştır; işçilik ve kâr payları buna göre "
                       "gözden geçirilmelidir.", S_KUCUK))
    parca.append(imza_blogu([("Düzenleyen<br/>Bölüm/Atölye Şefi", _sef(s["bolum_id"])),
                             ("Gerçekleştirme Görevlisi", k.get("gerceklestirme_gorevlisi")),
                             ("UYGUNDUR<br/>Harcama Yetkilisi", k.get("harcama_yetkilisi"))], 3, True))
    return olustur(yol, parca, baslik="Malzeme Listesi")


def dogrudan_temin_dosyasi(yol: Path, d: dict) -> Path:
    """4734 md.22/d doğrudan temin dosyası: firmalara piyasa fiyat teklif mektubu (boş), piyasa fiyat araştırma tutanağı ve
    onay belgesi. d: konu, tarih, sayi, gider_turu, kalemler [{ad, miktar, birim}], firmalar [{ad, tutar}],
    gorevliler [ad], yaklasik_maliyet, teslim_yeri, teslim_suresi"""
    k = _kurum()
    okul = f"{k.get('okul_adi') or ''} Döner Sermaye İşletmesi"
    kalemler = [x for x in d["kalemler"] if (x.get("ad") or "").strip()]
    firmalar = [f for f in d["firmalar"] if (f.get("ad") or "").strip()]
    teklifli = [f for f in firmalar if f.get("tutar")]
    secilen = min(teklifli, key=lambda f: f["tutar"]) if teklifli else None
    gorevliler = [g for g in d.get("gorevliler", []) if g] or [None, None]
    tarih = tarih_tr(d.get("tarih")) or "..../..../20...."
    kalem_veri = lambda bos: [[i + 1, x["ad"], x.get("miktar") or "", x.get("birim") or ""] + (["", ""] if bos else [])
                              for i, x in enumerate(kalemler)]
    parca = []

    for f in firmalar or [{"ad": ""}]:
        parca += [P(okul, S_ORTA_B), P("PİYASA FİYAT TEKLİF MEKTUBU", S_BASLIK),
                  P(f"Sayın: <b>{f['ad'] or '..............................................'}</b>", S_NORMAL), Spacer(1, 3 * mm),
                  P(f"İşletmemizin ihtiyacı olan ve aşağıda cinsi ve miktarı belirtilen mal/hizmet, 4734 sayılı Kamu İhale "
                    f"Kanununun 22 nci maddesinin (d) bendi uyarınca doğrudan temin usulüyle satın alınacaktır. KDV hariç birim ve "
                    f"toplam fiyatlarınızı yazarak kaşeleyip imzaladığınız teklifinizi en geç ..../..../20.... tarihine kadar "
                    f"İşletmemize teslim etmenizi rica ederiz.", S_METIN), Spacer(1, 3 * mm),
                  tablo(["S.No", "Mal / hizmetin adı ve özellikleri", "Miktar", "Birim", "Birim fiyat (KDV hariç)", "Toplam (TL)"],
                        kalem_veri(True) or [[1, "", "", "", "", ""]],
                        [11 * mm, 69 * mm, 18 * mm, 16 * mm, 28 * mm, 28 * mm], {2}, ["", "TOPLAM (KDV hariç)", "", "", "", ""]),
                  Spacer(1, 3 * mm),
                  P("<b>Şartlar:</b> 1) Fiyatlar KDV hariç TL olarak verilecektir. 2) Mal/hizmet "
                    f"{d.get('teslim_yeri') or 'İşletme atölyesine'} teslim edilecek, taşıma ve indirme gideri teklif sahibine "
                    f"ait olacaktır. 3) Teslim süresi {d.get('teslim_suresi') or 'siparişten itibaren 7 gündür'}. 4) Kusurlu veya "
                    "şartlara uymayan mal derhal yenisiyle değiştirilecektir. 5) Teklif en az 30 gün geçerli olacaktır. "
                    "6) Kamu ihalelerine katılmaktan yasaklı olmadığımızı beyan ederiz.", S_KUCUK),
                  Spacer(1, 3 * mm),
                  bilgi_tablosu([("Teklif sahibinin adı soyadı / unvanı", ""), ("T.C. kimlik / vergi kimlik no - vergi dairesi", ""),
                                 ("Adres", ""), ("Telefon / e-posta", ""),
                                 ("Toplam teklif (KDV hariç, rakam ve yazıyla)", "")]),
                  imza_blogu([("Kaşe / İmza", f["ad"] or "")], 1, True), PageBreak()]

    veri = [[i + 1, f["ad"], f.get("tutar") or "", "EN UYGUN" if f is secilen else ""] for i, f in enumerate(firmalar)]
    parca += [P(okul, S_ORTA_B), P("PİYASA FİYAT ARAŞTIRMA TUTANAĞI", S_BASLIK),
              bilgi_tablosu([("İşin adı", d.get("konu") or ""), ("Alım usulü", "Doğrudan temin (4734 s.K. md.22/d)"),
                             ("Gider türü", d.get("gider_turu") or ""), ("Tutanak tarihi", tarih)]),
              Spacer(1, 3 * mm), P("Alınacak mal / hizmet", S_ALT_BASLIK),
              tablo(["S.No", "Mal / hizmetin adı ve özellikleri", "Miktar", "Birim"], kalem_veri(False) or [[1, "", "", ""]],
                    [12 * mm, 110 * mm, 24 * mm, 24 * mm]),
              Spacer(1, 3 * mm), P("Alınan teklifler", S_ALT_BASLIK),
              tablo(["S.No", "Firma / kişi", "Toplam teklif (KDV hariç, TL)", "Değerlendirme"], veri or [[1, "", "", ""]],
                    [12 * mm, 90 * mm, 38 * mm, 30 * mm], {2}),
              Spacer(1, 3 * mm),
              P("Yukarıda belirtilen mal/hizmet için piyasada faaliyet gösteren firmalardan fiyat teklifi alınmış ve teklifler "
                "incelenmiştir." + (f" Şartlara uygun en uygun teklifin <b>{secilen['ad']}</b> tarafından verilen "
                                    f"<b>{para(secilen['tutar'])} TL</b> (KDV hariç) olduğu tespit edilmiştir." if secilen else "")
                + " Firmanın kamu ihalelerine katılmaktan yasaklı olup olmadığı EKAP üzerinden ..../..../20.... tarihinde "
                  "teyit edilmiştir. İşbu tutanak tarafımızca düzenlenip imza altına alınmıştır.", S_METIN),
              imza_blogu([("Piyasa Araştırması Görevlisi", g) for g in gorevliler], min(3, len(gorevliler)), True),
              PageBreak()]

    yaklasik = d.get("yaklasik_maliyet") or (secilen["tutar"] if secilen else 0)
    parca += antet(k, d.get("sayi") or "", "Doğrudan Temin Onay Belgesi", d.get("tarih"))
    parca += [P("ONAY BELGESİ", S_BASLIK),
              bilgi_tablosu([("İdarenin adı", okul), ("Belge tarih ve sayısı", f"{tarih} - {d.get('sayi') or ''}"),
                             ("İşin tanımı / niteliği", d.get("konu") or ""),
                             ("İşin miktarı", "; ".join(f"{x['ad']} {x.get('miktar') or ''} {x.get('birim') or ''}".strip()
                                                        for x in kalemler)),
                             ("Yaklaşık maliyet (KDV hariç)", f"{para(yaklasik)} TL" if yaklasik else ""),
                             ("Kullanılabilir ödenek / bütçe", "Döner sermaye işletmesi bütçesi"),
                             ("Alım usulü", "Doğrudan temin - 4734 sayılı Kanun md.22/d"),
                             ("Avans / fiyat farkı", "Verilmeyecek / ödenmeyecek"),
                             ("Piyasa araştırması görevlileri", ", ".join(g for g in gorevliler if g) or "")]),
              Spacer(1, 4 * mm),
              P("Yukarıda belirtilen mal/hizmetin 4734 sayılı Kamu İhale Kanununun 22 nci maddesinin (d) bendi uyarınca doğrudan "
                "temin usulüyle satın alınması hususunu olurlarınıza arz ederim.", S_METIN),
              imza_blogu([("Gerçekleştirme Görevlisi", k.get("gerceklestirme_gorevlisi"))], 1, True),
              Spacer(1, 4 * mm), P("<b>OLUR</b>", S_ORTA), P(tarih, S_ORTA),
              imza_blogu([("Harcama Yetkilisi<br/>Okul Müdürü", k.get("harcama_yetkilisi"))], 1)]
    return olustur(yol, parca, baslik="Doğrudan Temin Dosyası")


def calisma_istek_listesi(yol: Path, s_id: int, bos_satir: int = 5) -> Path:
    """Parça başı ücretli işte çalışmak isteyen personelin tespiti (Yön. md.8/1)."""
    db = al()
    s, _ = _siparis_bilgi(s_id)
    k = _kurum()
    kisiler = db.q("""SELECT ad_soyad, COALESCE(kadro_unvani, dose_gorevi) unvan, hizmet_sinifi FROM personel
                      WHERE aktif = 1 AND (bolum_id = ? OR id IN (SELECT kisi_id FROM siparis_gorevli
                                                                   WHERE siparis_id = ? AND kisi_turu = 'Personel'))
                      ORDER BY ad_soyad""", (s["bolum_id"] or 0, s_id))
    if not kisiler:
        kisiler = db.q("SELECT ad_soyad, COALESCE(kadro_unvani, dose_gorevi) unvan, hizmet_sinifi FROM personel "
                       "WHERE aktif = 1 ORDER BY ad_soyad")
    parca = antet(k)
    parca += [P("PARÇA BAŞI ÜCRETLİ ÇALIŞMA İSTEK LİSTESİ", S_BASLIK),
              bilgi_tablosu([("Sipariş / sözleşme no", s["siparis_no"] or ""), ("İşi yaptıran", s["unvan"] or ""),
                             ("İşin konusu", s["konu"] or ""), ("Bölüm / atölye", s["bolum_ad"] or ""),
                             ("Ücret ödeme esası", s["ucret_esasi"] or "")]),
              Spacer(1, 4 * mm),
              P("Yukarıda belirtilen işin parça başı ücret esasına göre üretiminde çalışmak isteyen personel, MEB Döner Sermaye "
                "İşletmelerinde Üretimi Teşvik Primi Dağıtımı, Parça Başı Üretim, Atölye ve Tesislerin Özel Sektörle İşbirliği "
                "Yapılarak İşletilmesi Hakkında Yönetmeliğin 8 inci maddesinin birinci fıkrası gereğince aşağıda belirlenmiştir. "
                "Aylık parça başı ücret, hizmet sınıfına göre Yönetmeliğin 8 inci maddesinin beşinci fıkrasındaki tavanları aşamaz.",
                S_METIN), Spacer(1, 3 * mm)]
    veri = [[i + 1, x["ad_soyad"], x["unvan"] or "", x["hizmet_sinifi"] or "", "Evet  /  Hayır", ""]
            for i, x in enumerate(kisiler)]
    veri += [[len(veri) + i + 1, "", "", "", "Evet  /  Hayır", ""] for i in range(bos_satir)]
    parca.append(tablo(["No", "Adı soyadı", "Unvan / branş", "Hizmet sınıfı", "Çalışmak istiyor mu?", "İmza"], veri,
                       [10 * mm, 43 * mm, 30 * mm, 43 * mm, 24 * mm, 20 * mm], yazi_boyu=8.5))
    parca += [Spacer(1, 2 * mm), P("Öğrencilerin çalıştırılması için ayrıca velilerinin yazılı muvafakati alınır (Yön. md.8/1).",
                                   S_KUCUK)]
    parca.append(imza_blogu([("Düzenleyen<br/>Bölüm/Atölye Şefi", _sef(s["bolum_id"])),
                             ("Gerçekleştirme Görevlisi", k.get("gerceklestirme_gorevlisi"))], 2, True))
    parca += [Spacer(1, 4 * mm), P("<b>OLUR</b>", S_ORTA), P(tarih_tr(date.today()), S_ORTA),
              imza_blogu([("Harcama Yetkilisi<br/>Okul Müdürü", k.get("harcama_yetkilisi"))], 1)]
    return olustur(yol, parca, baslik="Çalışma İstek Listesi")


def veli_muvafakatnamesi(yol: Path, ogrenci_idler: list[int]) -> Path:
    db = al()
    k = _kurum()
    parca = []
    for i, oid in enumerate(ogrenci_idler):
        o = db.q1("SELECT o.*, b.ad bolum_ad FROM ogrenci o LEFT JOIN bolum b ON b.id = o.bolum_id WHERE o.id = ?", (oid,))
        if not o:
            continue
        if i:
            parca.append(PageBreak())
        parca += antet(k)
        parca += [P("VELİ MUVAFAKATNAMESİ", S_BASLIK), P("(DÖSE Parça Başı Ücretli Üretimde Beceri Eğitimi)", S_ORTA),
                  Spacer(1, 5 * mm),
                  bilgi_tablosu([("Öğrencinin adı soyadı", o["ad_soyad"]), ("T.C. kimlik no", o["tckn"] or ""),
                                 ("Okul no / sınıf", f"{o['okul_no'] or ''} / {o['sinif'] or ''}"),
                                 ("Alan / bölüm", o["bolum_ad"] or ""), ("Veli adı soyadı", o["veli_adi"] or ""),
                                 ("Veli telefon", o["veli_telefon"] or "")]),
                  Spacer(1, 6 * mm),
                  P(f"Velisi bulunduğum yukarıda kimlik bilgileri yazılı öğrencinin, {k.get('okul_adi') or ''} Döner Sermaye "
                    f"İşletmesinde parça başı ücret ödenmek suretiyle gerçekleştirilen mal ve hizmet üretimi üzerinde beceri "
                    f"eğitimi yapmasına ve bu kapsamda kendisine ilgili mevzuat çerçevesinde ücret ödenmesine, MEB Döner Sermaye "
                    f"İşletmelerinde Üretimi Teşvik Primi Dağıtımı, Parça Başı Üretim, Atölye ve Tesislerin Özel Sektörle "
                    f"İşbirliği Yapılarak İşletilmesi Hakkında Yönetmeliğin 8 inci maddesinin birinci fıkrası gereğince "
                    f"muvafakat ediyorum.", S_METIN),
                  Spacer(1, 4 * mm),
                  P("Ödemelerin öğrenci adına açılmış aşağıdaki banka hesabına yapılmasını talep ederim.", S_METIN),
                  bilgi_tablosu([("IBAN", o["iban"] or "TR.. .... .... .... .... .... ..")]),
                  imza_blogu([("Veli", o["veli_adi"])], 1, True)]
    return olustur(yol, parca, baslik="Veli Muvafakatnamesi")


# ---------------------------------------------------------------- ödeme belgeleri
def parca_basi_bordrosu(yol: Path, pb_id: int) -> Path:
    db = al()
    k = _kurum()
    pb = db.q1("""SELECT pb.*, s.siparis_no, s.konu, s.bolum_id, s.iscilik_tutari, c.unvan
                  FROM parca_basi pb LEFT JOIN siparis s ON s.id = pb.siparis_id LEFT JOIN cari c ON c.id = s.cari_id
                  WHERE pb.id = ?""", (pb_id,))
    satirlar = db.q("""SELECT r.*, CASE WHEN r.kisi_turu = 'Personel' THEN p.ad_soyad ELSE o.ad_soyad END ad,
                              CASE WHEN r.kisi_turu = 'Personel' THEN p.tckn ELSE o.tckn END tckn,
                              CASE WHEN r.kisi_turu = 'Personel' THEN COALESCE(p.kadro_unvani, p.dose_gorevi) ELSE 'Öğrenci ' || COALESCE(o.sinif, '') END unvan,
                              CASE WHEN r.kisi_turu = 'Personel' THEN p.iban ELSE o.iban END iban
                       FROM parca_basi_satir r LEFT JOIN personel p ON r.kisi_turu = 'Personel' AND p.id = r.kisi_id
                       LEFT JOIN ogrenci o ON r.kisi_turu = 'Öğrenci' AND o.id = r.kisi_id
                       WHERE r.parca_basi_id = ? ORDER BY r.kisi_turu DESC, ad""", (pb_id,))
    donem = f"{mevzuat.AYLAR[pb['ay'] - 1]} {pb['yil']}"
    ogr = yuvarla(sum(s["hesaplanan"] for s in satirlar if s["kisi_turu"] == "Öğrenci"))
    per = yuvarla(sum(s["hesaplanan"] for s in satirlar if s["kisi_turu"] == "Personel"))
    parca = antet(k)
    parca += [P("PARÇA BAŞI ÜCRET DAĞITIM TUTANAĞI", S_BASLIK),
              bilgi_tablosu([("Dönem", donem), ("Sipariş no / konu", f"{pb['siparis_no'] or ''} - {pb['konu'] or ''}"),
                             ("İşi yaptıran", pb["unvan"] or ""),
                             ("Ay içinde geçici kabulü yapılan işçilik", para(pb["kabul_edilen_iscilik"]) + " TL"),
                             (f"Öğrenci hakkı ({oran_yazi(pb['ogrenci_orani'])})", para(ogr) + " TL"),
                             ("Personel işçilik payı", para(per) + " TL")]),
              Spacer(1, 4 * mm),
              P("Yukarıda belirtilen sipariş kapsamında ay içinde bitirilen ve geçici muayene ve kabulü yapılan mal/hizmetin "
                "işçilik bedeli; personel ve öğrencilerin üretime katkıları oranında bölüm/atölye şefince belirlenmiş olup "
                "(Yön. md.8/8), aylık tavanları aşan kısımlar ödenmemiştir (Yön. md.8/5-6).", S_METIN),
              imza_blogu([("Belirleyen<br/>Bölüm/Atölye Şefi", _sef(pb["bolum_id"])),
                          ("Gerçekleştirme Görevlisi", k.get("gerceklestirme_gorevlisi")),
                          ("ONAY<br/>Harcama Yetkilisi", k.get("harcama_yetkilisi"))], 3, True),
              PageBreak()]
    parca += [P(f"PARÇA BAŞI ÜCRET BORDROSU - {donem}", S_BASLIK), P(f"{pb['siparis_no'] or ''} {pb['konu'] or ''}", S_ORTA),
              Spacer(1, 3 * mm)]
    veri = [[i + 1, s["ad"], s["tckn"] or "", s["unvan"] or "", s["katki"], s["hesaplanan"], s["tavan_asimi"], s["brut"],
             s["gelir_vergisi"], s["damga_vergisi"], s["net"], s["iban"] or ""] for i, s in enumerate(satirlar)]
    top = lambda a: yuvarla(sum(s[a] for s in satirlar))
    parca.append(tablo(["No", "Adı soyadı", "T.C. kimlik", "Unvan", "Katkı (%/adet)", "Hesaplanan", "Tavan aşımı", "Brüt",
                        "Gelir v.", "Damga v.", "Net ödenecek", "IBAN"], veri,
                       [9 * mm, 38 * mm, 22 * mm, 30 * mm, 14 * mm, 21 * mm, 19 * mm, 21 * mm, 18 * mm, 16 * mm, 22 * mm, 48 * mm],
                       {4, 5, 6, 7, 8, 9, 10},
                       ["", "TOPLAM", "", "", "", top("hesaplanan"), top("tavan_asimi"), top("brut"), top("gelir_vergisi"),
                        top("damga_vergisi"), top("net"), ""], 7))
    parca.append(imza_blogu([("Düzenleyen<br/>Sayman", k.get("sayman")),
                             ("Gerçekleştirme Görevlisi", k.get("gerceklestirme_gorevlisi")),
                             ("Harcama Yetkilisi", k.get("harcama_yetkilisi"))], 3))
    return olustur(yol, parca, yatay=True, baslik="Parça Başı Bordrosu")


def parca_basi_puantaj(yol: Path, pb_id: int) -> Path:
    """Gün gün üretilen parça adedi, toplam adet, ödenen brüt ücret ve imza sütunlu puantaj cetveli (Yön. md.8/8).
    Puantaj girilmemişse elle doldurulacak boş cetvel üretir."""
    import calendar
    import json

    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    from . import pdf as _pdf
    db = al()
    k = _kurum()
    pb = db.q1("""SELECT pb.*, s.siparis_no, s.konu, s.bolum_id, b.ad bolum_ad FROM parca_basi pb
                  LEFT JOIN siparis s ON s.id = pb.siparis_id LEFT JOIN bolum b ON b.id = s.bolum_id WHERE pb.id = ?""", (pb_id,))
    satirlar = db.q("""SELECT r.*, CASE WHEN r.kisi_turu = 'Personel' THEN p.ad_soyad ELSE o.ad_soyad END ad,
                              CASE WHEN r.kisi_turu = 'Personel' THEN COALESCE(p.kadro_unvani, p.dose_gorevi)
                                   ELSE TRIM(COALESCE(o.okul_no, '') || ' ' || COALESCE(o.sinif, '')) END unvan
                       FROM parca_basi_satir r LEFT JOIN personel p ON r.kisi_turu = 'Personel' AND p.id = r.kisi_id
                       LEFT JOIN ogrenci o ON r.kisi_turu = 'Öğrenci' AND o.id = r.kisi_id
                       WHERE r.parca_basi_id = ?
                       ORDER BY CASE WHEN r.kisi_turu = 'Personel' THEN 0 ELSE 1 END, ad""", (pb_id,))
    yil, ay = pb["yil"], pb["ay"]
    n = calendar.monthrange(yil, ay)[1]
    hafta_sonu = {g for g in range(1, n + 1) if date(yil, ay, g).weekday() >= 5}
    gun_w = (261 - 97) / n * mm
    ad_stil = _pdf.ParagraphStyle("pad", parent=_pdf.S_HUCRE, fontSize=6.5, leading=7.5)
    sayi = lambda v: "" if not v else (f"{v:g}".replace(".", ","))
    veri = [["No", "Adı soyadı / unvan"] + [str(g) for g in range(1, n + 1)] + ["Adet", "Brüt ücret", "İmza"]]
    stil = [("FONTNAME", (0, 0), (-1, -1), _pdf._FONT), ("FONTSIZE", (0, 0), (-1, -1), 6.5),
            ("FONTNAME", (0, 0), (-1, 0), _pdf._FONT_B), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe7f2")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (2, 0), (-1, -1), "CENTER"), ("ALIGN", (n + 2, 1), (n + 3, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 1.5), ("RIGHTPADDING", (0, 0), (-1, -1), 1.5)]
    for g in hafta_sonu:
        stil.append(("BACKGROUND", (g + 1, 1), (g + 1, -1), colors.HexColor("#ececec")))
    yukseklik = [None]
    for tur, baslik in (("Personel", "PERSONEL"), ("Öğrenci", "ÖĞRENCİLER")):
        grup = [s for s in satirlar if s["kisi_turu"] == tur]
        if not grup:
            continue
        r0 = len(veri)
        veri.append([baslik] + [""] * (n + 4))
        stil += [("SPAN", (0, r0), (-1, r0)), ("FONTNAME", (0, r0), (-1, r0), _pdf._FONT_B),
                 ("ALIGN", (0, r0), (-1, r0), "LEFT"), ("BACKGROUND", (0, r0), (-1, r0), colors.HexColor("#f5f5f5"))]
        yukseklik.append(None)
        for i, s in enumerate(grup):
            try:
                p = {int(g): float(v) for g, v in json.loads(s.get("puantaj") or "{}").items()}
            except (TypeError, ValueError):
                p = {}
            ad = f"{s['ad'] or ''}" + (f"<br/><font size=5.5>{s['unvan']}</font>" if s["unvan"] else "")
            veri.append([i + 1, _pdf.P(ad, ad_stil)] + [sayi(p.get(g)) for g in range(1, n + 1)]
                        + [sayi(sum(p.values())), para(s["brut"]), ""])
            yukseklik.append(6.2 * mm)
        r1 = len(veri)
        veri.append(["", f"{baslik} TOPLAMI"] + [sayi(sum(json.loads(s.get("puantaj") or "{}").get(str(g), 0) for s in grup))
                                                for g in range(1, n + 1)]
                    + [sayi(sum(sum(json.loads(s.get("puantaj") or "{}").values()) for s in grup)),
                       para(yuvarla(sum(s["brut"] for s in grup))), ""])
        stil += [("FONTNAME", (0, r1), (-1, r1), _pdf._FONT_B), ("BACKGROUND", (0, r1), (-1, r1), colors.HexColor("#f0f0f0"))]
        yukseklik.append(None)
    t = Table(veri, colWidths=[7 * mm, 42 * mm] + [gun_w] * n + [12 * mm, 18 * mm, 18 * mm], rowHeights=yukseklik, repeatRows=1)
    t.setStyle(TableStyle(stil))
    donem = f"{mevzuat.AYLAR[ay - 1]} {yil}"
    parca = [P(f"{k.get('okul_adi') or ''} Döner Sermaye İşletmesi Müdürlüğü", S_ORTA),
             P(f"PARÇA BAŞI ÜRETİM PUANTAJ CETVELİ - {donem}", S_BASLIK),
             P(f"Sipariş: {pb['siparis_no'] or ''} - {pb['konu'] or ''}  •  Bölüm / atölye: {pb['bolum_ad'] or ''}", S_ORTA),
             Spacer(1, 3 * mm), t, Spacer(1, 2 * mm),
             P("Gün sütunları kişinin o gün ürettiği parça adedini (adet esası uygulanmıyorsa çalıştığı günü) gösterir. Ücret, "
               "ay içinde geçici kabulü yapılan işin işçilik bedelinden öğrenci hakkı ayrıldıktan sonra her grubun havuzunun adet "
               "toplamına oranlanmasıyla hesaplanmış; aylık tavanı aşan kısım ödenmemiştir (Yön. md.8/3, 8/5-6, 8/8).", S_KUCUK),
             imza_blogu([("Düzenleyen<br/>Bölüm/Atölye Şefi", _sef(pb["bolum_id"])),
                         ("Gerçekleştirme Görevlisi", k.get("gerceklestirme_gorevlisi")),
                         ("OLUR<br/>Harcama Yetkilisi", k.get("harcama_yetkilisi"))], 3)]
    return olustur(yol, parca, yatay=True, baslik="Puantaj Cetveli")


def fazla_calisma_puantaj(yol: Path, yil: int, ay: int) -> Path:
    """Aylık fazla çalışma puantajı (mesai çizelgesi): gün türleri renkli, şef/TMY/sayman imzalı, müdür onaylı (Yön. md.9/c-e)."""
    import calendar

    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    from . import pdf as _pdf
    from .denetim import puantaj_coz
    from .hesap import gun_turu
    db = al()
    k = _kurum()
    p = db.parametreler(yil)
    kayitlar = db.q("""SELECT f.*, p.ad_soyad, COALESCE(p.kadro_unvani, p.dose_gorevi) unvan, p.bolum_id, s.siparis_no
                       FROM fazla_calisma f JOIN personel p ON p.id = f.personel_id LEFT JOIN siparis s ON s.id = f.siparis_id
                       WHERE f.yil = ? AND f.ay = ? ORDER BY p.ad_soyad, f.id""", (yil, ay))
    kisiler: dict[int, dict] = {}
    for r in kayitlar:
        x = kisiler.setdefault(r["personel_id"], {"ad": r["ad_soyad"], "unvan": r["unvan"], "bolum_id": r["bolum_id"],
                                                  "gun": {}, "saat": 0.0, "brut": 0.0, "ucret": set(), "siparis": []})
        for g, v in puantaj_coz(r["puantaj"]).items():
            x["gun"][g] = x["gun"].get(g, 0) + v
        x["saat"] += r["saat"] or 0
        x["brut"] += r["brut"] or 0
        x["ucret"].add(r["saat_ucreti"] or 0)
        if r["siparis_no"] and r["siparis_no"] not in x["siparis"]:
            x["siparis"].append(r["siparis_no"])
    n = calendar.monthrange(yil, ay)[1]
    turler = {g: gun_turu(date(yil, ay, g), p) for g in range(1, n + 1)}
    renk = {"tatil": "#dbe9f7", "pazar": "#cfcfcf", "bayram": "#f4c7c3"}
    gun_w = (261 - 113) / n * mm
    ad_stil = _pdf.ParagraphStyle("fad", parent=_pdf.S_HUCRE, fontSize=6.5, leading=7.5)
    sayi = lambda v: "" if not v else (f"{v:g}".replace(".", ","))
    veri = [["No", "Adı soyadı / unvan / sipariş"] + [str(g) for g in range(1, n + 1)] + ["Saat", "Saat ücr.", "Brüt", "İmza"]]
    stil = [("FONTNAME", (0, 0), (-1, -1), _pdf._FONT), ("FONTSIZE", (0, 0), (-1, -1), 6.5),
            ("FONTNAME", (0, 0), (-1, 0), _pdf._FONT_B), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe7f2")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (2, 0), (-1, -1), "CENTER"), ("ALIGN", (n + 2, 1), (n + 4, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 1.5), ("RIGHTPADDING", (0, 0), (-1, -1), 1.5)]
    for g, t in turler.items():
        if t in renk:
            stil.append(("BACKGROUND", (g + 1, 1), (g + 1, -1), colors.HexColor(renk[t])))
    yukseklik = [None]
    for i, x in enumerate(kisiler.values()):
        alt = " • ".join(a for a in (x["unvan"], ", ".join(x["siparis"])) if a)
        ad = f"{x['ad'] or ''}" + (f"<br/><font size=5.5>{alt}</font>" if alt else "")
        ucret = "/".join(para(u) for u in sorted(x["ucret"]))
        veri.append([i + 1, _pdf.P(ad, ad_stil)] + [sayi(x["gun"].get(g)) for g in range(1, n + 1)]
                    + [sayi(x["saat"]), ucret, para(x["brut"]), ""])
        yukseklik.append(7 * mm)
    for _ in range(max(0, 3 - len(kisiler))):
        veri.append([""] * (n + 6))
        yukseklik.append(7 * mm)
    r1 = len(veri)
    veri.append(["", "TOPLAM"] + [sayi(sum(x["gun"].get(g, 0) for x in kisiler.values())) for g in range(1, n + 1)]
                + [sayi(sum(x["saat"] for x in kisiler.values())), "", para(yuvarla(sum(x["brut"] for x in kisiler.values()))), ""])
    stil += [("FONTNAME", (0, r1), (-1, r1), _pdf._FONT_B), ("BACKGROUND", (0, r1), (-1, r1), colors.HexColor("#f0f0f0"))]
    yukseklik.append(None)
    t = Table(veri, colWidths=[7 * mm, 42 * mm] + [gun_w] * n + [12 * mm, 16 * mm, 18 * mm, 18 * mm], rowHeights=yukseklik,
              repeatRows=1)
    t.setStyle(TableStyle(stil))
    bolumler = {x["bolum_id"] for x in kisiler.values()}
    sef = _sef(next(iter(bolumler))) if len(bolumler) == 1 else None
    puantajsiz = [x["ad"] for x in kisiler.values() if not x["gun"] and x["saat"]]
    donem = f"{mevzuat.AYLAR[ay - 1]} {yil}"
    parca = [P(f"{k.get('okul_adi') or ''} Döner Sermaye İşletmesi Müdürlüğü", S_ORTA),
             P(f"DÖNER SERMAYE FAZLA ÇALIŞMA PUANTAJI (MESAİ ÇİZELGESİ) - {donem}", S_BASLIK), Spacer(1, 3 * mm), t,
             Spacer(1, 2 * mm),
             P(f"Gün sütunları olağan çalışma saatleri dışında fiilen çalışılan saati gösterir. Mavi: tatil (Cumartesi, yarıyıl/ara/yaz "
               f"tatili, resmi tatil; günde en çok {p['fc_tatil_gunu_saat']:g} saat); gri: Pazar"
               + ("" if p.get("fc_pazar_izinli") else " (fazla çalışma yapılmaz, Yön. md.9/a-12)")
               + f"; kırmızı: resmi/dini bayram (fazla çalışma yapılmaz); beyaz: öğretim günü (en çok {p['fc_ogretim_gunu_saat']:g} saat). "
               f"Saat ücreti {para(p.get('fazla_calisma_azami_ucret') or 0)} TL'yi geçemez (2026 Bütçe K cetveli III-3). Fiilen "
               "çalışmadığı hâlde ödeme yapılan personelden ödenen tutar bir katı fazlasıyla geri alınır; bu tutarın yarısı çizelgeyi "
               "onaylayan yetkiliden tahsil edilir (K cetveli III-4). Çizelge atölye/bölüm şefince düzenlenir, gerçekleştirme görevlisi "
               "ve saymanca imzalanır, müdürce onaylanır (Çalışma Yönergesi md.9/c-e).", S_KUCUK)]
    if puantajsiz:
        parca.append(P("Günlük puantajı girilmemiş personel (gün sütunları elle doldurulmalıdır): " + ", ".join(puantajsiz), S_KUCUK))
    parca.append(imza_blogu([("Düzenleyen<br/>Atölye/Bölüm Şefi", sef),
                             ("Gerçekleştirme Görevlisi", k.get("gerceklestirme_gorevlisi")),
                             ("Sayman", k.get("sayman")),
                             ("OLUR<br/>Harcama Yetkilisi (Okul Müdürü)", k.get("harcama_yetkilisi"))], 4))
    return olustur(yol, parca, yatay=True, baslik="Fazla Çalışma Puantajı")


def fazla_calisma_bordrosu(yol: Path, yil: int, ay: int) -> Path:
    db = al()
    k = _kurum()
    satirlar = db.q("""SELECT f.*, p.ad_soyad, p.tckn, COALESCE(p.kadro_unvani, p.dose_gorevi) unvan, p.iban, s.siparis_no
                       FROM fazla_calisma f JOIN personel p ON p.id = f.personel_id LEFT JOIN siparis s ON s.id = f.siparis_id
                       WHERE f.yil = ? AND f.ay = ? ORDER BY p.ad_soyad""", (yil, ay))
    donem = f"{mevzuat.AYLAR[ay - 1]} {yil}"
    veri = [[i + 1, s["ad_soyad"], s["tckn"] or "", s["unvan"] or "", s["siparis_no"] or "", s["saat"], s["saat_ucreti"],
             s["brut"], s["gelir_vergisi"], s["damga_vergisi"], s["net"], s["iban"] or ""] for i, s in enumerate(satirlar)]
    top = lambda a: yuvarla(sum(s[a] for s in satirlar))
    parca = antet(k) + [P(f"DÖNER SERMAYE FAZLA ÇALIŞMA ÜCRETİ BORDROSU - {donem}", S_BASLIK), Spacer(1, 3 * mm),
                        tablo(["S.No", "Adı soyadı", "T.C. kimlik", "Unvan", "Sipariş", "Saat", "Saat ücreti", "Brüt",
                               "Gelir v.", "Damga v.", "Net", "IBAN"], veri,
                              [9 * mm, 38 * mm, 22 * mm, 30 * mm, 22 * mm, 13 * mm, 18 * mm, 21 * mm, 18 * mm, 16 * mm, 21 * mm, 48 * mm],
                              {5, 6, 7, 8, 9, 10},
                              ["", "TOPLAM", "", "", "", top("saat"), "", top("brut"), top("gelir_vergisi"), top("damga_vergisi"),
                               top("net"), ""], 7),
                        imza_blogu([("Düzenleyen<br/>Sayman", k.get("sayman")),
                                    ("Gerçekleştirme Görevlisi", k.get("gerceklestirme_gorevlisi")),
                                    ("Harcama Yetkilisi", k.get("harcama_yetkilisi"))], 3)]
    return olustur(yol, parca, yatay=True, baslik="Fazla Çalışma Bordrosu")


def hazine_payi_bildirimi(yol: Path, hp_id: int) -> Path:
    db = al()
    k = _kurum()
    h = db.q1("SELECT * FROM hazine_payi WHERE id = ?", (hp_id,))
    donem = f"{mevzuat.AYLAR[h['ay'] - 1]} {h['yil']}"
    parca = [P("D.S.İ.B.M.Y. Örnek No: 30", S_KUCUK), Spacer(1, 2 * mm),
             P("AYLIK GAYRİSAFİ HASILATTAN TAHSİL EDİLEN TUTARA İLİŞKİN BİLDİRİM", S_BASLIK), Spacer(1, 4 * mm),
             bilgi_tablosu([
                 ("Döner sermayeli işletmenin adı", f"{k.get('okul_adi') or ''} {k.get('isletme_adi') or ''}"),
                 ("Vergi kimlik numarası", k.get("vkn") or ""),
                 ("Bağlı olduğu idare", "Millî Eğitim Bakanlığı"),
                 ("Kuruluş kanunu", "3423 sayılı Kanun"),
                 ("Bildirim dönemi", donem),
             ]), Spacer(1, 5 * mm),
             tablo(["Açıklama", "Tutar (TL)"], [
                 ["Ay içinde aylık gayrisafi hasılattan tahsil edilen tutar", h["tahsil_edilen"]],
                 ["Uygulanan oran", oran_yazi(h["oran"])],
                 ["Genel bütçeye aktarılacak tutar (Hazine payı)", h["tutar"]],
             ], [120 * mm, 50 * mm], {1}),
             Spacer(1, 4 * mm),
             P("Yukarıda belirtilen tutar, Muhasebat Genel Müdürlüğü Genel Tebliği (Sıra No: 73) gereğince takip eden ayın "
               "20'sine kadar ilgili muhasebe biriminin hesabına yatırılacaktır. Döner sermaye faaliyetlerinden bir ay içinde "
               "tahsil edilen tutar bulunmasa bile bildirim verilir.", S_METIN),
             imza_blogu([("Muhasebe Yetkilisi<br/>Sayman", k.get("sayman")),
                         ("Harcama Yetkilisi", k.get("harcama_yetkilisi"))], 2, True)]
    return olustur(yol, parca, baslik="Hazine Payı Bildirimi")


def utp_cetveli(yol: Path, yil: int) -> Path:
    db = al()
    k = _kurum()
    ys = db.q1("SELECT * FROM yil_sonu WHERE yil = ?", (yil,)) or {}
    satirlar = db.q("""SELECT u.*, p.ad_soyad, p.tckn, p.dose_gorevi, p.iban, b.ad bolum
                       FROM utp_kisi u JOIN personel p ON p.id = u.personel_id LEFT JOIN bolum b ON b.id = p.bolum_id
                       WHERE u.yil = ? ORDER BY u.haric, p.dose_gorevi, p.ad_soyad""", (yil,))
    parca = antet(k) + [P(f"{yil} YILI KÂR DAĞITIMI VE ÜRETİMİ TEŞVİK PRİMİ DAĞITIM CETVELİ", S_BASLIK)]
    parca.append(tablo(["Açıklama", "Tutar (TL)"], [
        ["Toplam gelir", ys.get("toplam_gelir") or 0], ["Toplam gider", ys.get("toplam_gider") or 0],
        ["Mali yıl sonu bilanço kârı", ys.get("donem_kari") or 0],
        [f"ÜTP dağıtım oranı ({oran_yazi(ys.get('utp_orani') or 0)}) - dağıtıma esas kâr", ys.get("dagitima_esas") or 0],
        ["Dağıtılan ÜTP", ys.get("dagitilan_utp") or 0],
        ["Sermayeye eklenen", ys.get("sermaye_payi") or 0],
        [f"MEB Merkez Saymanlık hesabına ({mevzuat.MERKEZ_SAYMANLIK['iban']})", ys.get("merkez_payi") or 0],
        ["SHÇEK payı (yıllık brüt hasılatın %1'i)", ys.get("shcek") or 0],
    ], [180 * mm, 50 * mm], {1}))
    parca += [Spacer(1, 4 * mm), P(f"Dağıtım usulü: {ys.get('yontem') or ''}", S_NORMAL), Spacer(1, 2 * mm)]
    veri = [[i + 1, s["ad_soyad"], s["dose_gorevi"] or "", s["bolum"] or "", f"{s['fiili_gun'] or 0:g}", f"{s['fazla_calisma_saat'] or 0:g}",
             s["idari_pay"], s["takdir_pay"], s["bolum_pay"], s["tavan_asimi"], s["brut"], s["gelir_vergisi"], s["damga_vergisi"],
             s["net"], ("HARİÇ: " + (s["haric_neden"] or "")) if s["haric"] else ""] for i, s in enumerate(satirlar)]
    top = lambda a: yuvarla(sum(s[a] or 0 for s in satirlar))
    parca.append(tablo(["No", "Adı soyadı", "DÖSE görevi", "Bölüm", "Gün", "F.Ç. saat", "İdari pay", "Takdir", "Bölüm payı",
                        "Tavan aşımı", "Brüt ÜTP", "Gelir v.", "Damga v.", "Net", "Not"], veri,
                       [8 * mm, 32 * mm, 32 * mm, 22 * mm, 11 * mm, 13 * mm, 18 * mm, 16 * mm, 18 * mm, 17 * mm, 19 * mm,
                        16 * mm, 14 * mm, 19 * mm, 20 * mm], {4, 5, 6, 7, 8, 9, 10, 11, 12, 13},
                       ["", "TOPLAM", "", "", "", "", top("idari_pay"), top("takdir_pay"), top("bolum_pay"), top("tavan_asimi"),
                        top("brut"), top("gelir_vergisi"), top("damga_vergisi"), top("net"), ""], 6.5))
    parca.append(imza_blogu([("Düzenleyen<br/>Sayman", k.get("sayman")),
                             ("Gerçekleştirme Görevlisi", k.get("gerceklestirme_gorevlisi")),
                             ("Harcama Yetkilisi", k.get("harcama_yetkilisi"))], 3))
    # takdir komisyon kararı
    takdir = [s for s in satirlar if (s["takdir_pay"] or 0) > 0]
    parca += [PageBreak()] + antet(k) + [
        P("ÇALIŞMAYI TEŞVİK VE ÇALIŞANI TAKDİR PAYI KOMİSYON KARARI", S_BASLIK),
        P(f"Karar tarihi: {tarih_tr(date.today())}", S_ORTA), Spacer(1, 4 * mm),
        P(f"{yil} yılı dağıtıma esas kârının %5'i olarak ayrılan çalışmayı teşvik ve çalışanı takdir payı; harcama yetkilisi, "
          "gerçekleştirme görevlisi ve ilgili bölüm/alan veya atölye şeflerinden oluşan komisyonumuzca, işletmede çalışan personel "
          "arasında takdire lâyık görülenlere aşağıdaki oranlarda dağıtılmasına karar verilmiştir. Komisyon üyeleri bu paydan "
          "faydalanamaz; karar kesindir (Yön. md.5/6).", S_METIN), Spacer(1, 3 * mm),
        P("<b>Gerekçe:</b> ..................................................................................................."
          "...................................................................................................", S_NORMAL),
        Spacer(1, 3 * mm),
        tablo(["S.No", "Adı soyadı", "Görevi", "Takdir oranı", "Takdir payı (TL)"],
              [[i + 1, s["ad_soyad"], s["dose_gorevi"] or "", oran_yazi(s["takdir_orani"] or 0), s["takdir_pay"]]
               for i, s in enumerate(takdir)], [12 * mm, 55 * mm, 55 * mm, 22 * mm, 26 * mm], {4}),
    ]
    uyeler = db.q("SELECT ad_soyad, dose_gorevi FROM personel WHERE aktif = 1 AND dose_gorevi IN "
                  "('Harcama Yetkilisi (Okul Müdürü)', 'Gerçekleştirme Görevlisi (Teknik Md. Yrd.)', 'Bölüm/Alan Şefi', "
                  "'Atölye/Laboratuvar Şefi') ORDER BY dose_gorevi")
    parca.append(imza_blogu([(("Başkan" if i == 0 else "Üye") + "<br/>" + u["dose_gorevi"].split(" (")[0], u["ad_soyad"])
                             for i, u in enumerate(uyeler)] or [("Başkan", "")], 3))
    return olustur(yol, parca, yatay=True, baslik="ÜTP Dağıtım Cetveli")


def resmi_yazi(yol: Path, yazi: dict) -> Path:
    k = _kurum()
    parca = antet(k, yazi.get("sayi") or "", yazi.get("konu") or "", yazi.get("tarih"))
    if yazi.get("muhatap"):
        parca += [P(f"<b>{yazi['muhatap']}</b>", S_ORTA), Spacer(1, 4 * mm)]
    if yazi.get("ilgi"):
        parca += [P(f"İlgi: {yazi['ilgi']}"), Spacer(1, 3 * mm)]
    for paragraf in (yazi.get("metin") or "").split("\n\n"):
        parca += [P(paragraf.strip(), S_METIN), Spacer(1, 2 * mm)]
    imzalar = [x for x in [yazi.get("imza1"), yazi.get("imza2")] if x]
    if imzalar:
        cift = []
        for x in imzalar:
            satir = x.split("\n", 1)
            cift.append((satir[1].replace("\n", "<br/>") if len(satir) > 1 else "", satir[0]))
        parca.append(imza_blogu(cift, len(cift)))
    return olustur(yol, parca, baslik=yazi.get("konu") or "Resmi Yazı")


def muhasebe_islem_fisi(yol: Path, yevmiye_id: int) -> Path:
    db = al()
    k = _kurum()
    y = db.q1("SELECT * FROM yevmiye WHERE id = ?", (yevmiye_id,))
    satirlar = db.q("SELECT s.*, h.ad FROM yevmiye_satir s LEFT JOIN hesap_plani h ON h.kod = s.hesap_kodu "
                    "WHERE s.yevmiye_id = ? ORDER BY s.borc DESC, s.id", (yevmiye_id,))
    parca = antet(k) + [P("MUHASEBE İŞLEM FİŞİ (YARDIMCI KAYIT)", S_BASLIK),
                        bilgi_tablosu([("Fiş no", y["fis_no"]), ("Tarih", tarih_tr(y["tarih"])), ("Açıklama", y["aciklama"] or ""),
                                       ("Kaynak", f"{y['kaynak']} #{y['kaynak_id'] or ''}")]), Spacer(1, 4 * mm),
                        tablo(["Hesap kodu", "Hesap adı", "Açıklama", "Borç", "Alacak"],
                              [[s["hesap_kodu"], s["ad"] or "", s["aciklama"] or "", s["borc"], s["alacak"]] for s in satirlar],
                              [22 * mm, 48 * mm, 50 * mm, 25 * mm, 25 * mm], {3, 4},
                              ["", "TOPLAM", "", yuvarla(sum(s["borc"] for s in satirlar)), yuvarla(sum(s["alacak"] for s in satirlar))]),
                        Spacer(1, 3 * mm),
                        P("Ekli kanıtlayıcı belgeler harcama yetkilisince incelenerek doğruluğu görüldükten sonra imzalanır.", S_KUCUK),
                        imza_blogu([("Düzenleyen<br/>Sayman", k.get("sayman")),
                                    ("Harcama Yetkilisi", k.get("harcama_yetkilisi"))], 2)]
    return olustur(yol, parca, baslik="Muhasebe İşlem Fişi")


def genel_liste(yol: Path, baslik: str, basliklar: list, satirlar: list, sayisal: set | None = None,
                toplam_satiri: list | None = None, alt_metin: str = "", yatay: bool = True) -> Path:
    k = _kurum()
    parca = antet(k) + [P(baslik, S_BASLIK), Spacer(1, 2 * mm),
                        tablo(basliklar, satirlar, None, sayisal or set(), toplam_satiri, 7.5)]
    if alt_metin:
        parca += [Spacer(1, 3 * mm), P(alt_metin, S_KUCUK)]
    return olustur(yol, parca, yatay=yatay, baslik=baslik)
