"""Yasal yükümlülükler: hazine payı, SHÇEK payı, Merkez Saymanlık kâr aktarımı, KDV ve muhtasar özetleri."""
from datetime import date

from PySide6.QtWidgets import QGridLayout, QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ... import belgeler, mevzuat, muhasebe
from ...hesap import para, son_odeme_tarihleri, yuvarla
from ..ortak import (Kolon, Oturum, VeriTablosu, baslik_etiketi, bilgi, bugun, buton, cikti_yolu, db, dosya_ac, soru,
                     tablo_excele, uyari, yetki_kontrol)


def _odeme_var(kaynak: str, kaynak_id: int) -> dict | None:
    return db().q1("SELECT * FROM kasa_banka WHERE kaynak = ? AND kaynak_id = ? ORDER BY tarih LIMIT 1", (kaynak, kaynak_id))


class HazinePayiSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "Hazine Payı / SHÇEK / Kâr Aktarımı",
            "Aylık gayrisafi hasılattan tahsil edilen tutarın %1'i izleyen ayın 20'sine kadar Örnek No:30 ile bildirilip ödenir; tahsilat "
            "olmayan aylarda da bildirim verilir (Tebliğ 73). SHÇEK payı Ocak sonuna, Merkez Saymanlık kâr payı Şubat sonuna kadar yatırılır."))
        ust = QHBoxLayout()
        self.b_hesap = buton("Seçili ayı hesapla / güncelle", self.hesapla, "birincil")
        self.b_tum = buton("Geçmiş ayların tümünü hesapla", self.tumunu_hesapla)
        ust.addWidget(self.b_hesap)
        ust.addWidget(self.b_tum)
        ust.addWidget(buton("Bildirim (Örnek 30) PDF", self.pdf))
        ust.addWidget(buton("Bildirildi olarak işaretle", self.bildirildi))
        ust.addWidget(buton("Ödeme kaydı oluştur", self.odeme))
        ust.addWidget(buton("Excel'e Aktar", lambda: tablo_excele(self, self.tablo, f"Hazine_Payi_{Oturum.yil}")))
        ust.addStretch()
        lay.addLayout(ust)
        self.tablo = VeriTablosu()
        lay.addWidget(self.tablo)

        g = QGroupBox("Yıllık yükümlülükler")
        gl = QGridLayout(g)
        self.l_shcek = QLabel()
        self.l_merkez = QLabel()
        self.l_shcek.setWordWrap(True)
        self.l_merkez.setWordWrap(True)
        gl.addWidget(self.l_shcek, 0, 0)
        gl.addWidget(buton("SHÇEK ödeme kaydı", self.shcek_odeme), 0, 1)
        gl.addWidget(self.l_merkez, 1, 0)
        gl.addWidget(buton("Merkez Saymanlık ödeme kaydı", self.merkez_odeme), 1, 1)
        gl.setColumnStretch(0, 1)
        lay.addWidget(g)
        self.yenile()

    def yenile(self):
        yil = Oturum.yil
        kayit = {r["ay"]: r for r in db().q("SELECT * FROM hazine_payi WHERE yil = ?", (yil,))}
        p = db().parametreler(yil)
        bugun_ = date.today()
        satirlar = []
        for ay in range(1, 13):
            r = kayit.get(ay, {})
            son = son_odeme_tarihleri(yil, ay)["Hazine payı"]
            guncel = muhasebe.aylik_tahsil_edilen_hasilat(yil, ay)
            odeme = _odeme_var("HazinePayi", r["id"]) if r else None
            sifir_bildirim = bool(r) and not r.get("tutar") and bool(r.get("bildirim_tarihi"))
            durum = "Ödendi" if odeme else ("Bildirildi (tutar yok)" if sifir_bildirim else
                                            (r.get("durum") or ("Hesaplanmadı" if date(yil, ay, 1) <= bugun_ else "-")))
            gecikme = ""
            if not odeme and not sifir_bildirim and son < bugun_ and date(yil, ay, 1) <= bugun_:
                gecikme = f"{(bugun_ - son).days} gün gecikti"
            elif odeme and odeme["tarih"] > son.isoformat():
                gecikme = f"{(date.fromisoformat(odeme['tarih']) - son).days} gün geç ödendi"
            fark = r and abs((r.get("tahsil_edilen") or 0) - guncel) > 0.009
            satirlar.append({"id": r.get("id"), "ay": ay, "ay_ad": mevzuat.AYLAR[ay - 1], "guncel": guncel,
                             "tahsil_edilen": r.get("tahsil_edilen"), "oran": r.get("oran") or p["hazine_payi_orani"],
                             "tutar": r.get("tutar") if r else yuvarla(guncel * p["hazine_payi_orani"]),
                             "son": son.isoformat(), "bildirim_tarihi": r.get("bildirim_tarihi"),
                             "odeme_tarihi": odeme["tarih"] if odeme else r.get("odeme_tarihi"), "durum": durum,
                             "gecikme": gecikme, "fark": "Tahsilat değişti, yeniden hesaplayın" if fark else ""})
        self.satirlar = satirlar

        def renk(s):
            if s["gecikme"] and "gecikti" in s["gecikme"]:
                return "#fde2e2"
            if s["fark"]:
                return "#fff4d6"
            return "#eef6ee" if s["durum"].startswith(("Ödendi", "Bildirildi (")) else None
        self.tablo.doldur(
            [Kolon("ay_ad", "Ay"), Kolon("guncel", "Tahsil edilen hasılat (güncel)", "para"),
             Kolon("tahsil_edilen", "Bildirilen matrah", "para"), Kolon("oran", "Oran", "oran"), Kolon("tutar", "Hazine payı", "para"),
             Kolon("son", "Son gün", "tarih"), Kolon("bildirim_tarihi", "Bildirim", "tarih"), Kolon("odeme_tarihi", "Ödeme", "tarih"),
             Kolon("durum", "Durum"), Kolon("gecikme", "Gecikme"), Kolon("fark", "Uyarı")], satirlar, renk)

        hasilat = muhasebe.yillik_brut_hasilat(yil)
        shcek = yuvarla(hasilat * p["shcek_orani"])
        s_odeme = _odeme_var("SHCEK", yil)
        self._shcek = shcek
        self.l_shcek.setText(f"<b>SHÇEK payı ({yil}):</b> yıllık brüt hasılat {para(hasilat)} TL × %{p['shcek_orani'] * 100:g} = "
                             f"<b>{para(shcek)} TL</b> • Son gün: 31.01.{yil + 1} • "
                             + (f"<span style='color:green'>Ödendi ({s_odeme['tarih']})</span>" if s_odeme else
                                "<span style='color:#b00'>Ödenmedi</span>"))
        ys = db().q1("SELECT * FROM yil_sonu WHERE yil = ?", (yil,))
        self._ys = ys
        m_odeme = _odeme_var("MerkezKar", yil)
        ms = mevzuat.MERKEZ_SAYMANLIK
        if ys:
            self.l_merkez.setText(f"<b>MEB Merkez Saymanlık kâr payı ({yil}):</b> <b>{para(ys['merkez_payi'])} TL</b> • "
                                  f"{ms['ad']} VKN {ms['vkn']} • IBAN {ms['iban']} • Son gün: Şubat {yil + 1} sonu • "
                                  + (f"<span style='color:green'>Ödendi ({m_odeme['tarih']})</span>" if m_odeme else
                                     "<span style='color:#b00'>Ödenmedi</span>"))
        else:
            self.l_merkez.setText(f"<b>MEB Merkez Saymanlık kâr payı ({yil}):</b> yıl sonu dağıtımı henüz yapılmadı.")
        self.b_hesap.setEnabled(Oturum.yazabilir(self))
        self.b_tum.setEnabled(Oturum.yazabilir(self))

    def _hesapla_ay(self, ay):
        yil = Oturum.yil
        p = db().parametreler(yil)
        tahsil = muhasebe.aylik_tahsil_edilen_hasilat(yil, ay)
        v = {"yil": yil, "ay": ay, "tahsil_edilen": tahsil, "oran": p["hazine_payi_orani"],
             "tutar": yuvarla(tahsil * p["hazine_payi_orani"])}
        r = db().q1("SELECT id, durum FROM hazine_payi WHERE yil = ? AND ay = ?", (yil, ay))
        if r:
            if _odeme_var("HazinePayi", r["id"]):
                return False
            db().guncelle("hazine_payi", r["id"], v)
            hid = r["id"]
        else:
            v["durum"] = "Hesaplandı"
            hid = db().ekle("hazine_payi", v)
        muhasebe.hazine_payi_kaydi(hid)
        return True

    def hesapla(self):
        s = self.tablo.secili()
        if not s or not yetki_kontrol(self):
            return
        if not self._hesapla_ay(s["ay"]):
            uyari(self, "Ödemesi yapılmış ay yeniden hesaplanamaz. Önce ödeme kaydını siliniz.")
        self.yenile()

    def tumunu_hesapla(self):
        if not yetki_kontrol(self):
            return
        bugun_ = date.today()
        for ay in range(1, 13):
            if date(Oturum.yil, ay, 1) < date(bugun_.year, bugun_.month, 1):
                self._hesapla_ay(ay)
        self.yenile()

    def pdf(self):
        s = self.tablo.secili()
        if not s:
            return
        if not s["id"]:
            uyari(self, "Önce ayı hesaplayınız.")
            return
        dosya_ac(belgeler.hazine_payi_bildirimi(cikti_yolu(f"Hazine_Payi_{Oturum.yil}_{s['ay']:02d}"), s["id"]))

    def bildirildi(self):
        s = self.tablo.secili()
        if s and s["id"] and yetki_kontrol(self):
            db().guncelle("hazine_payi", s["id"], {"bildirim_tarihi": bugun(), "durum": "Bildirildi"})
            self.yenile()

    def odeme(self):
        s = self.tablo.secili()
        if not s or not yetki_kontrol(self):
            return
        if not s["id"]:
            uyari(self, "Önce ayı hesaplayınız.")
            return
        if s["durum"] == "Ödendi":
            bilgi(self, "Bu ayın ödeme kaydı var.")
            return
        if not s["tutar"]:
            bilgi(self, "Ödenecek tutar yok (bildirim yine de verilmelidir).")
            return
        from .kasa import KasaDialog
        if KasaDialog(self, on_deger={"yon": "Çıkış", "tur": "Hazine Payı Ödemesi", "tutar": s["tutar"], "hesap": "Banka (102)",
                                      "aciklama": f"{s['ay_ad']} {Oturum.yil} hazine payı", "kaynak": "HazinePayi",
                                      "kaynak_id": s["id"]}).exec():
            db().guncelle("hazine_payi", s["id"], {"durum": "Ödendi", "odeme_tarihi": bugun()})
            self.yenile()

    def shcek_odeme(self):
        if not yetki_kontrol(self):
            return
        if _odeme_var("SHCEK", Oturum.yil):
            bilgi(self, "SHÇEK ödeme kaydı zaten var.")
            return
        if not self._ys or self._ys.get("durum") != "Onaylandı":
            if not soru(self, "Yıl sonu dağıtımı kesinleşmemiş; SHÇEK tahakkuk kaydı oluşmamış olabilir. Devam edilsin mi?"):
                return
        from .kasa import KasaDialog
        if KasaDialog(self, on_deger={"yon": "Çıkış", "tur": "SHÇEK Payı Ödemesi", "tutar": self._shcek, "hesap": "Banka (102)",
                                      "tarih": f"{Oturum.yil + 1}-01-31" if date.today().year > Oturum.yil else None,
                                      "aciklama": f"{Oturum.yil} yılı SHÇEK payı (2828 s.K. md.18/1-k)",
                                      "kaynak": "SHCEK", "kaynak_id": Oturum.yil}).exec():
            self.yenile()

    def merkez_odeme(self):
        if not yetki_kontrol(self):
            return
        if not self._ys:
            uyari(self, "Önce yıl sonu kâr dağıtımını yapınız.")
            return
        if _odeme_var("MerkezKar", Oturum.yil):
            bilgi(self, "Merkez Saymanlık ödeme kaydı zaten var.")
            return
        from .kasa import KasaDialog
        if KasaDialog(self, on_deger={"yon": "Çıkış", "tur": "Merkez Saymanlık Kâr Aktarımı", "tutar": self._ys["merkez_payi"],
                                      "hesap": "Banka (102)", "aciklama": f"{Oturum.yil} yılı kâr payı - {mevzuat.MERKEZ_SAYMANLIK['iban']}",
                                      "kaynak": "MerkezKar", "kaynak_id": Oturum.yil}).exec():
            self.yenile()


class VergiSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(baslik_etiketi(
            "KDV ve Muhtasar Özeti",
            "Beyanname hazırlığı için aylık özet. KDV beyannamesi izleyen ayın 28'ine, muhtasar ve prim hizmet beyannamesi 26'sına kadar "
            "verilir. Tutarları GİB e-Beyanname üzerinden beyan ediniz; bu ekran kontrol amaçlıdır."))
        ust = QHBoxLayout()
        ust.addWidget(buton("Excel'e Aktar", lambda: tablo_excele(self, self.tablo, f"KDV_Muhtasar_{Oturum.yil}")))
        ust.addWidget(buton("Seçili ayın muhtasar detayı", self.detay))
        ust.addStretch()
        lay.addLayout(ust)
        self.tablo = VeriTablosu()
        lay.addWidget(self.tablo)
        self.t_detay = VeriTablosu()
        self.t_detay.setMaximumHeight(260)
        lay.addWidget(QLabel("<b>Muhtasar detay (seçili ay)</b>"))
        lay.addWidget(self.t_detay)
        self.yenile()

    def _ay_verisi(self, yil, ay):
        d = f"{yil}-{ay:02d}"
        q = lambda sql: db().deger(sql, (d,), 0.0)
        satis_kdv = q("SELECT SUM(kdv - tevkif_kdv) FROM fatura WHERE tur = 'Satış' AND iptal = 0 AND substr(tarih, 1, 7) = ?")
        alis_kdv = q("SELECT SUM(kdv) FROM fatura WHERE tur = 'Alış' AND iptal = 0 AND substr(tarih, 1, 7) = ?")
        tevkif = q("SELECT SUM(tevkif_kdv) FROM fatura WHERE tur = 'Alış' AND iptal = 0 AND substr(tarih, 1, 7) = ?")
        stopaj = q("SELECT SUM(stopaj) FROM fatura WHERE tur = 'Alış' AND iptal = 0 AND substr(tarih, 1, 7) = ?")
        pb = db().q1("""SELECT SUM(r.gelir_vergisi) gv, SUM(r.damga_vergisi) dv, SUM(r.brut) b FROM parca_basi_satir r
                        JOIN parca_basi p ON p.id = r.parca_basi_id WHERE p.durum = 'Onaylandı' AND p.yil = ? AND p.ay = ?""", (yil, ay))
        fc = db().q1("SELECT SUM(gelir_vergisi) gv, SUM(damga_vergisi) dv, SUM(brut) b FROM fazla_calisma "
                     "WHERE durum = 'Onaylandı' AND yil = ? AND ay = ?", (yil, ay))
        satis_matrah = q("SELECT SUM(matrah) FROM fatura WHERE tur = 'Satış' AND iptal = 0 AND substr(tarih, 1, 7) = ?")
        return {"satis_matrah": satis_matrah, "hesaplanan": yuvarla(satis_kdv), "indirilecek": yuvarla(alis_kdv),
                "tevkifat": yuvarla(tevkif), "stopaj": yuvarla(stopaj),
                "ucret_brut": yuvarla((pb["b"] or 0) + (fc["b"] or 0)),
                "ucret_gv": yuvarla((pb["gv"] or 0) + (fc["gv"] or 0)), "ucret_dv": yuvarla((pb["dv"] or 0) + (fc["dv"] or 0))}

    def yenile(self):
        yil = Oturum.yil
        devreden = 0.0
        satirlar = []
        for ay in range(1, 13):
            v = self._ay_verisi(yil, ay)
            fark = yuvarla(v["hesaplanan"] - v["indirilecek"] - devreden)
            odenecek_kdv = max(fark, 0.0)
            devreden = max(-fark, 0.0)
            son = son_odeme_tarihleri(yil, ay)
            v.update({"ay": ay, "ay_ad": mevzuat.AYLAR[ay - 1], "odenecek_kdv": odenecek_kdv, "devreden": yuvarla(devreden),
                      "muhtasar": yuvarla(v["stopaj"] + v["ucret_gv"] + v["ucret_dv"]),
                      "kdv_son": son["KDV beyan"].isoformat(), "muhtasar_son": son["Muhtasar beyan"].isoformat()})
            satirlar.append(v)
        self.satirlar = satirlar
        self.tablo.doldur(
            [Kolon("ay_ad", "Ay"), Kolon("satis_matrah", "Satış matrahı", "para"), Kolon("hesaplanan", "Hesaplanan KDV", "para"),
             Kolon("indirilecek", "İndirilecek KDV", "para"), Kolon("odenecek_kdv", "Ödenecek KDV (1 No.)", "para"),
             Kolon("devreden", "Devreden KDV", "para"), Kolon("tevkifat", "Sorumlu sıfatıyla KDV (2 No.)", "para"),
             Kolon("kdv_son", "KDV son gün", "tarih"), Kolon("stopaj", "Stopaj (müstahsil/SM)", "para"),
             Kolon("ucret_gv", "Ücret GV", "para"), Kolon("ucret_dv", "Ücret DV", "para"), Kolon("muhtasar", "Muhtasar toplam", "para"),
             Kolon("muhtasar_son", "Muhtasar son gün", "tarih")], satirlar)

    def detay(self):
        s = self.tablo.secili()
        if not s:
            return
        d = f"{Oturum.yil}-{s['ay']:02d}"
        satirlar = db().q("""SELECT f.tarih, f.belge_turu, f.belge_no, c.unvan, c.vkn_tckn, f.stopaj_turu tur, f.matrah, f.stopaj tutar
                             FROM fatura f LEFT JOIN cari c ON c.id = f.cari_id
                             WHERE f.tur = 'Alış' AND f.iptal = 0 AND f.stopaj > 0 AND substr(f.tarih, 1, 7) = ?""", (d,))
        for r in db().q("""SELECT pb.id, s.siparis_no, SUM(r.brut) b, SUM(r.gelir_vergisi) gv, SUM(r.damga_vergisi) dv
                           FROM parca_basi pb JOIN parca_basi_satir r ON r.parca_basi_id = pb.id LEFT JOIN siparis s ON s.id = pb.siparis_id
                           WHERE pb.durum = 'Onaylandı' AND pb.yil = ? AND pb.ay = ? GROUP BY pb.id, s.siparis_no""", (Oturum.yil, s["ay"])):
            satirlar.append({"tarih": d + "-28", "belge_turu": "Parça başı bordro", "belge_no": r["siparis_no"], "unvan": "Personel/öğrenci",
                             "vkn_tckn": "", "tur": "Ücret GV + DV", "matrah": r["b"], "tutar": yuvarla((r["gv"] or 0) + (r["dv"] or 0))})
        fc = db().q1("SELECT SUM(brut) b, SUM(gelir_vergisi) gv, SUM(damga_vergisi) dv FROM fazla_calisma WHERE durum = 'Onaylandı' "
                     "AND yil = ? AND ay = ?", (Oturum.yil, s["ay"]))
        if fc and fc["b"]:
            satirlar.append({"tarih": d + "-28", "belge_turu": "Fazla çalışma bordrosu", "belge_no": "", "unvan": "Personel",
                             "vkn_tckn": "", "tur": "Ücret GV + DV", "matrah": fc["b"], "tutar": yuvarla((fc["gv"] or 0) + (fc["dv"] or 0))})
        self.t_detay.doldur([Kolon("tarih", "Tarih", "tarih"), Kolon("belge_turu", "Belge"), Kolon("belge_no", "No"),
                             Kolon("unvan", "Ünvan"), Kolon("vkn_tckn", "VKN/TCKN"), Kolon("tur", "Tür"),
                             Kolon("matrah", "Matrah", "para"), Kolon("tutar", "Kesinti", "para")], satirlar)
