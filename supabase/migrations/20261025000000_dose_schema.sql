-- Canonical D?SE schema for the application PostgreSQL backend.

-- Public client access is intentionally blocked: no anon/authenticated RLS policies are defined.

CREATE TABLE IF NOT EXISTS ayar (
    anahtar TEXT PRIMARY KEY,
    deger TEXT
);
CREATE TABLE IF NOT EXISTS kurum (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    okul_adi TEXT, isletme_adi TEXT, il TEXT, ilce TEXT, adres TEXT, telefon TEXT, eposta TEXT,
    kurum_kodu TEXT, vergi_dairesi TEXT, vkn TEXT, banka TEXT, iban TEXT,
    harcama_yetkilisi TEXT, gerceklestirme_gorevlisi TEXT, sayman TEXT,
    buyuksehir INTEGER DEFAULT 0, tahsis_sermaye DOUBLE PRECISION DEFAULT 0, odenmis_sermaye DOUBLE PRECISION DEFAULT 0,
    yuz_yuze_egitim INTEGER DEFAULT 1, evrak_kodu TEXT
);
CREATE TABLE IF NOT EXISTS parametre (
    yil INTEGER, anahtar TEXT, deger TEXT,
    PRIMARY KEY (yil, anahtar)
);
CREATE TABLE IF NOT EXISTS kullanici (
    id SERIAL PRIMARY KEY,
    kullanici_adi TEXT UNIQUE NOT NULL, ad_soyad TEXT, rol TEXT NOT NULL,
    sifre_hash TEXT NOT NULL, tuz TEXT NOT NULL, aktif INTEGER DEFAULT 1, sifre_degismeli INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS islem_log (
    id SERIAL PRIMARY KEY,
    zaman TEXT, kullanici TEXT, islem TEXT, tablo TEXT, kayit_id INTEGER, detay TEXT
);
CREATE TABLE IF NOT EXISTS mobil_oturum (
    id SERIAL PRIMARY KEY,
    token_ozet TEXT UNIQUE NOT NULL, kullanici_id INTEGER NOT NULL, cihaz TEXT, ip TEXT,
    olusturma TEXT, son_kullanim TEXT, bitis TEXT, aktif INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sayac (
    tur TEXT, yil INTEGER, son INTEGER DEFAULT 0, PRIMARY KEY (tur, yil)
);
CREATE TABLE IF NOT EXISTS bolum (
    id SERIAL PRIMARY KEY,
    kod TEXT, ad TEXT NOT NULL, alan TEXT, utp_yontemi TEXT, aktif INTEGER DEFAULT 1, aciklama TEXT
);
CREATE TABLE IF NOT EXISTS personel (
    id SERIAL PRIMARY KEY,
    sicil_no TEXT, tckn TEXT, ad_soyad TEXT NOT NULL, kadro_unvani TEXT,
    hizmet_sinifi TEXT, dose_gorevi TEXT, unvan_grubu INTEGER DEFAULT 3, bolum_id INTEGER,
    istihdam TEXT DEFAULT '657 s. DMK', iban TEXT, telefon TEXT, eposta TEXT,
    aktif INTEGER DEFAULT 1, notlar TEXT
);
CREATE TABLE IF NOT EXISTS ogrenci (
    id SERIAL PRIMARY KEY,
    okul_no TEXT, tckn TEXT, ad_soyad TEXT NOT NULL, dogum_tarihi TEXT, sinif TEXT, bolum_id INTEGER,
    veli_adi TEXT, veli_telefon TEXT, veli_muvafakat INTEGER DEFAULT 0, muvafakat_tarihi TEXT,
    iban TEXT, aktif INTEGER DEFAULT 1, notlar TEXT
);
CREATE TABLE IF NOT EXISTS cari (
    id SERIAL PRIMARY KEY,
    kod TEXT, tur TEXT, unvan TEXT NOT NULL, kamu_kurumu INTEGER DEFAULT 0,
    vergi_dairesi TEXT, vkn_tckn TEXT, telefon TEXT, eposta TEXT, adres TEXT, iban TEXT, notlar TEXT,
    aktif INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS urun (
    id SERIAL PRIMARY KEY,
    kod TEXT, ad TEXT NOT NULL, tur TEXT, birim TEXT, bolum_id INTEGER, kdv_orani DOUBLE PRECISION DEFAULT 0.20,
    satis_fiyati DOUBLE PRECISION DEFAULT 0, kar_orani DOUBLE PRECISION DEFAULT 0.10, ucret_esasi TEXT, mamul_malzeme_id INTEGER,
    aktif INTEGER DEFAULT 1, aciklama TEXT
);
CREATE TABLE IF NOT EXISTS maliyet_kalem (
    id SERIAL PRIMARY KEY,
    urun_id INTEGER NOT NULL, kalem_turu TEXT, aciklama TEXT, malzeme_id INTEGER,
    miktar DOUBLE PRECISION DEFAULT 1, birim_fiyat DOUBLE PRECISION DEFAULT 0
);
CREATE TABLE IF NOT EXISTS fiyat_tespit (
    id SERIAL PRIMARY KEY,
    urun_id INTEGER, tarih TEXT, birim_maliyet DOUBLE PRECISION, kar_orani DOUBLE PRECISION, satis_fiyati DOUBLE PRECISION, kdv_orani DOUBLE PRECISION,
    kdv_dahil_fiyat DOUBLE PRECISION, piyasa_arastirmasi TEXT, karar_no TEXT, aciklama TEXT
);
CREATE TABLE IF NOT EXISTS malzeme (
    id SERIAL PRIMARY KEY,
    kod TEXT, ad TEXT NOT NULL, tur TEXT, birim TEXT, kdv_orani DOUBLE PRECISION DEFAULT 0.20,
    kritik_stok DOUBLE PRECISION DEFAULT 0, aktif INTEGER DEFAULT 1, aciklama TEXT
);
CREATE TABLE IF NOT EXISTS stok_hareket (
    id SERIAL PRIMARY KEY,
    tarih TEXT, malzeme_id INTEGER, yon TEXT, miktar DOUBLE PRECISION, birim_fiyat DOUBLE PRECISION DEFAULT 0,
    kaynak TEXT, kaynak_id INTEGER, siparis_id INTEGER, aciklama TEXT
);
CREATE TABLE IF NOT EXISTS siparis (
    id SERIAL PRIMARY KEY,
    siparis_no TEXT, tarih TEXT, cari_id INTEGER, bolum_id INTEGER, konu TEXT, ucret_esasi TEXT,
    sozlesme_bedeli DOUBLE PRECISION DEFAULT 0, kdv_orani DOUBLE PRECISION DEFAULT 0.20, pesinat DOUBLE PRECISION DEFAULT 0,
    baslama_tarihi TEXT, teslim_tarihi TEXT, kabul_tarihi TEXT, durum TEXT,
    ogrenci_uygulamasi INTEGER DEFAULT 1, malzeme_musteriden INTEGER DEFAULT 0,
    kar_orani DOUBLE PRECISION, faaliyet_orani DOUBLE PRECISION, malzeme_maliyeti DOUBLE PRECISION DEFAULT 0,
    iscilik_tutari DOUBLE PRECISION DEFAULT 0, ogrenci_hakki_orani DOUBLE PRECISION,
    sozlesme_suresi_ay INTEGER DEFAULT 0, bakanlik_izni INTEGER DEFAULT 0, aciklama TEXT
);
CREATE TABLE IF NOT EXISTS siparis_kalem (
    id SERIAL PRIMARY KEY,
    siparis_id INTEGER NOT NULL, urun_id INTEGER, aciklama TEXT, miktar DOUBLE PRECISION DEFAULT 1, birim TEXT,
    birim_fiyat DOUBLE PRECISION DEFAULT 0
);
CREATE TABLE IF NOT EXISTS siparis_gorevli (
    id SERIAL PRIMARY KEY,
    siparis_id INTEGER NOT NULL, kisi_turu TEXT, kisi_id INTEGER, gorev TEXT
);
CREATE TABLE IF NOT EXISTS siparis_is_plani (
    id SERIAL PRIMARY KEY,
    siparis_id INTEGER NOT NULL, sira INTEGER DEFAULT 1,
    kalem TEXT NOT NULL, aciklama TEXT, birim TEXT, miktar DOUBLE PRECISION DEFAULT 1,
    tahmini_saat DOUBLE PRECISION DEFAULT 0, notlar TEXT
);
CREATE TABLE IF NOT EXISTS fatura (
    id SERIAL PRIMARY KEY,
    tur TEXT NOT NULL, belge_turu TEXT, belge_no TEXT, tarih TEXT, cari_id INTEGER, siparis_id INTEGER,
    aciklama TEXT, matrah DOUBLE PRECISION DEFAULT 0, kdv DOUBLE PRECISION DEFAULT 0, tevkifat TEXT DEFAULT 'Yok',
    tevkif_kdv DOUBLE PRECISION DEFAULT 0, stopaj_turu TEXT DEFAULT 'Yok', stopaj_orani DOUBLE PRECISION DEFAULT 0, stopaj DOUBLE PRECISION DEFAULT 0,
    genel_toplam DOUBLE PRECISION DEFAULT 0, net_tutar DOUBLE PRECISION DEFAULT 0, temin_usulu TEXT, gider_turu TEXT,
    avans_mahsup DOUBLE PRECISION DEFAULT 0, iptal INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS fatura_kalem (
    id SERIAL PRIMARY KEY,
    fatura_id INTEGER NOT NULL, urun_id INTEGER, malzeme_id INTEGER, aciklama TEXT,
    miktar DOUBLE PRECISION DEFAULT 1, birim TEXT, birim_fiyat DOUBLE PRECISION DEFAULT 0, kdv_orani DOUBLE PRECISION DEFAULT 0.20,
    tutar DOUBLE PRECISION DEFAULT 0, kdv DOUBLE PRECISION DEFAULT 0
);
CREATE TABLE IF NOT EXISTS kasa_banka (
    id SERIAL PRIMARY KEY,
    tarih TEXT, hesap TEXT, yon TEXT, tur TEXT, tutar DOUBLE PRECISION DEFAULT 0, hasilat_tutari DOUBLE PRECISION DEFAULT 0,
    cari_id INTEGER, fatura_id INTEGER, siparis_id INTEGER, belge_no TEXT, aciklama TEXT,
    kaynak TEXT, kaynak_id INTEGER
);
CREATE TABLE IF NOT EXISTS parca_basi (
    id SERIAL PRIMARY KEY,
    yil INTEGER, ay INTEGER, siparis_id INTEGER, kabul_edilen_iscilik DOUBLE PRECISION DEFAULT 0,
    ogrenci_orani DOUBLE PRECISION DEFAULT 0.30, durum TEXT DEFAULT 'Taslak', onay_tarihi TEXT, aciklama TEXT
);
CREATE TABLE IF NOT EXISTS parca_basi_satir (
    id SERIAL PRIMARY KEY,
    parca_basi_id INTEGER NOT NULL, kisi_turu TEXT, kisi_id INTEGER, katki DOUBLE PRECISION DEFAULT 0,
    hesaplanan DOUBLE PRECISION DEFAULT 0, brut DOUBLE PRECISION DEFAULT 0, tavan_asimi DOUBLE PRECISION DEFAULT 0,
    onceki_kumulatif DOUBLE PRECISION DEFAULT 0, gelir_vergisi DOUBLE PRECISION DEFAULT 0, damga_vergisi DOUBLE PRECISION DEFAULT 0,
    sgk DOUBLE PRECISION DEFAULT 0, net DOUBLE PRECISION DEFAULT 0, puantaj TEXT
);
CREATE TABLE IF NOT EXISTS fazla_calisma (
    id SERIAL PRIMARY KEY,
    yil INTEGER, ay INTEGER, personel_id INTEGER, siparis_id INTEGER, saat DOUBLE PRECISION DEFAULT 0,
    saat_ucreti DOUBLE PRECISION DEFAULT 0, brut DOUBLE PRECISION DEFAULT 0, onceki_kumulatif DOUBLE PRECISION DEFAULT 0,
    gelir_vergisi DOUBLE PRECISION DEFAULT 0, damga_vergisi DOUBLE PRECISION DEFAULT 0, net DOUBLE PRECISION DEFAULT 0,
    durum TEXT DEFAULT 'Taslak', aciklama TEXT, puantaj TEXT
);
CREATE TABLE IF NOT EXISTS hazine_payi (
    id SERIAL PRIMARY KEY,
    yil INTEGER, ay INTEGER, tahsil_edilen DOUBLE PRECISION DEFAULT 0, oran DOUBLE PRECISION, tutar DOUBLE PRECISION DEFAULT 0,
    bildirim_tarihi TEXT, odeme_tarihi TEXT, durum TEXT DEFAULT 'Hesaplandı', aciklama TEXT,
    UNIQUE (yil, ay)
);
CREATE TABLE IF NOT EXISTS yil_sonu (
    yil INTEGER PRIMARY KEY,
    toplam_gelir DOUBLE PRECISION, toplam_gider DOUBLE PRECISION, donem_kari DOUBLE PRECISION, faiz_duzeltme DOUBLE PRECISION DEFAULT 0,
    utp_orani DOUBLE PRECISION, dagitima_esas DOUBLE PRECISION, dagitilan_utp DOUBLE PRECISION, sermaye_payi DOUBLE PRECISION, merkez_payi DOUBLE PRECISION,
    shcek DOUBLE PRECISION, yontem TEXT, durum TEXT DEFAULT 'Taslak', aciklama TEXT
);
CREATE TABLE IF NOT EXISTS utp_kisi (
    id SERIAL PRIMARY KEY,
    yil INTEGER, personel_id INTEGER, fiili_gun DOUBLE PRECISION DEFAULT 0, fazla_calisma_saat DOUBLE PRECISION DEFAULT 0,
    katki_orani DOUBLE PRECISION DEFAULT 0, takdir_orani DOUBLE PRECISION DEFAULT 0, haric INTEGER DEFAULT 0, haric_neden TEXT,
    idari_pay DOUBLE PRECISION DEFAULT 0, takdir_pay DOUBLE PRECISION DEFAULT 0, bolum_pay DOUBLE PRECISION DEFAULT 0, hesaplanan DOUBLE PRECISION DEFAULT 0,
    tavan_asimi DOUBLE PRECISION DEFAULT 0, brut DOUBLE PRECISION DEFAULT 0, onceki_kumulatif DOUBLE PRECISION DEFAULT 0,
    gelir_vergisi DOUBLE PRECISION DEFAULT 0, damga_vergisi DOUBLE PRECISION DEFAULT 0, net DOUBLE PRECISION DEFAULT 0,
    diger_isletme_utp DOUBLE PRECISION DEFAULT 0,
    UNIQUE (yil, personel_id)
);
CREATE TABLE IF NOT EXISTS hesap_plani (
    kod TEXT PRIMARY KEY, ad TEXT
);
CREATE TABLE IF NOT EXISTS yevmiye (
    id SERIAL PRIMARY KEY,
    fis_no TEXT, tarih TEXT, aciklama TEXT, kaynak TEXT, kaynak_id INTEGER
);
CREATE TABLE IF NOT EXISTS yevmiye_satir (
    id SERIAL PRIMARY KEY,
    yevmiye_id INTEGER NOT NULL, hesap_kodu TEXT, aciklama TEXT, borc DOUBLE PRECISION DEFAULT 0, alacak DOUBLE PRECISION DEFAULT 0
);
CREATE TABLE IF NOT EXISTS resmi_yazi (
    id SERIAL PRIMARY KEY,
    tarih TEXT, sayi TEXT, konu TEXT, muhatap TEXT, ilgi TEXT, metin TEXT, imza1 TEXT, imza2 TEXT
);
CREATE TABLE IF NOT EXISTS denetim (
    id SERIAL PRIMARY KEY,
    baslik TEXT NOT NULL, durum TEXT DEFAULT 'Taslak', bilgiler TEXT,
    surum INTEGER DEFAULT 1, olusturma TEXT, guncelleme TEXT,
    olusturan TEXT, guncelleyen TEXT
);
CREATE TABLE IF NOT EXISTS denetim_madde (
    id SERIAL PRIMARY KEY,
    denetim_id INTEGER NOT NULL, madde_kodu TEXT NOT NULL,
    durum TEXT DEFAULT 'Değerlendirilmedi', aciklama TEXT, surum INTEGER DEFAULT 1,
    guncelleme TEXT, guncelleyen TEXT, UNIQUE (denetim_id, madde_kodu)
);
CREATE TABLE IF NOT EXISTS onay_durum (
    belge_turu TEXT NOT NULL, belge_id INTEGER NOT NULL, asama INTEGER DEFAULT 0, durum TEXT DEFAULT 'Hazırlanıyor',
    bolum_id INTEGER, hazirlayan TEXT, guncelleme TEXT,
    PRIMARY KEY (belge_turu, belge_id)
);
CREATE TABLE IF NOT EXISTS onay_kaydi (
    id SERIAL PRIMARY KEY,
    belge_turu TEXT, belge_id INTEGER, asama INTEGER, asama_adi TEXT, karar TEXT,
    kullanici TEXT, ad_soyad TEXT, rol TEXT, zaman TEXT, aciklama TEXT
);
CREATE INDEX IF NOT EXISTS ix_onay_kaydi ON onay_kaydi(belge_turu, belge_id);
CREATE INDEX IF NOT EXISTS ix_fatura_tarih ON fatura(tarih);
CREATE INDEX IF NOT EXISTS ix_kasa_tarih ON kasa_banka(tarih);
CREATE INDEX IF NOT EXISTS ix_yev_kaynak ON yevmiye(kaynak, kaynak_id);
CREATE INDEX IF NOT EXISTS ix_stok_malzeme ON stok_hareket(malzeme_id);
CREATE INDEX IF NOT EXISTS ix_islem_log_kayit ON islem_log(tablo, kayit_id);
CREATE INDEX IF NOT EXISTS ix_denetim_madde_denetim ON denetim_madde(denetim_id);

ALTER TABLE utp_kisi ADD COLUMN IF NOT EXISTS diger_isletme_utp DOUBLE PRECISION DEFAULT 0;

ALTER TABLE fatura ADD COLUMN IF NOT EXISTS avans_mahsup DOUBLE PRECISION DEFAULT 0;

ALTER TABLE kullanici ADD COLUMN IF NOT EXISTS personel_id INTEGER;

ALTER TABLE kullanici ADD COLUMN IF NOT EXISTS bolum_id INTEGER;

ALTER TABLE kullanici ADD COLUMN IF NOT EXISTS son_giris TEXT;

ALTER TABLE parca_basi_satir ADD COLUMN IF NOT EXISTS puantaj TEXT;

ALTER TABLE fazla_calisma ADD COLUMN IF NOT EXISTS puantaj TEXT;

ALTER TABLE fatura ADD COLUMN IF NOT EXISTS iskonto DOUBLE PRECISION DEFAULT 0;

ALTER TABLE fatura_kalem ADD COLUMN IF NOT EXISTS iskonto_orani DOUBLE PRECISION DEFAULT 0;

ALTER TABLE fatura_kalem ADD COLUMN IF NOT EXISTS iskonto DOUBLE PRECISION DEFAULT 0;

ALTER TABLE siparis_kalem ADD COLUMN IF NOT EXISTS iskonto_orani DOUBLE PRECISION DEFAULT 0;

ALTER TABLE siparis_kalem ADD COLUMN IF NOT EXISTS iskonto DOUBLE PRECISION DEFAULT 0;

ALTER TABLE siparis ADD COLUMN IF NOT EXISTS talep_sayi TEXT;

ALTER TABLE siparis ADD COLUMN IF NOT EXISTS talep_tarih TEXT;

ALTER TABLE siparis ADD COLUMN IF NOT EXISTS talep_kurum TEXT;

ALTER TABLE siparis ADD COLUMN IF NOT EXISTS talep_ilgi TEXT;

ALTER TABLE siparis ADD COLUMN IF NOT EXISTS kesif_tarih TEXT;

ALTER TABLE siparis ADD COLUMN IF NOT EXISTS kesif_ozet TEXT;

ALTER TABLE siparis ADD COLUMN IF NOT EXISTS proforma_no TEXT;

ALTER TABLE siparis ADD COLUMN IF NOT EXISTS proforma_tarih TEXT;

ALTER TABLE siparis ADD COLUMN IF NOT EXISTS proforma_gecerlilik_gun INTEGER DEFAULT 30;

ALTER TABLE denetim ADD COLUMN IF NOT EXISTS bilgiler TEXT;

ALTER TABLE denetim ADD COLUMN IF NOT EXISTS surum INTEGER DEFAULT 1;

ALTER TABLE denetim ADD COLUMN IF NOT EXISTS olusturma TEXT;

ALTER TABLE denetim ADD COLUMN IF NOT EXISTS guncelleme TEXT;

ALTER TABLE denetim ADD COLUMN IF NOT EXISTS olusturan TEXT;

ALTER TABLE denetim ADD COLUMN IF NOT EXISTS guncelleyen TEXT;

ALTER TABLE denetim_madde ADD COLUMN IF NOT EXISTS durum TEXT DEFAULT 'Değerlendirilmedi';

ALTER TABLE denetim_madde ADD COLUMN IF NOT EXISTS aciklama TEXT;

ALTER TABLE denetim_madde ADD COLUMN IF NOT EXISTS surum INTEGER DEFAULT 1;

ALTER TABLE denetim_madde ADD COLUMN IF NOT EXISTS guncelleme TEXT;

ALTER TABLE denetim_madde ADD COLUMN IF NOT EXISTS guncelleyen TEXT;

ALTER TABLE islem_log ADD COLUMN IF NOT EXISTS rol TEXT;

ALTER TABLE islem_log ADD COLUMN IF NOT EXISTS ad_soyad TEXT;

ALTER TABLE islem_log ADD COLUMN IF NOT EXISTS bilgisayar TEXT;

ALTER TABLE islem_log ADD COLUMN IF NOT EXISTS istemci TEXT;

ALTER TABLE islem_log ADD COLUMN IF NOT EXISTS oturum TEXT;

ALTER TABLE islem_log ADD COLUMN IF NOT EXISTS eski TEXT;

ALTER TABLE islem_log ADD COLUMN IF NOT EXISTS yeni TEXT;

DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['ayar', 'kurum', 'parametre', 'kullanici', 'islem_log', 'mobil_oturum', 'sayac', 'bolum', 'personel', 'ogrenci', 'cari', 'urun', 'maliyet_kalem', 'fiyat_tespit', 'malzeme', 'stok_hareket', 'siparis', 'siparis_kalem', 'siparis_gorevli', 'siparis_is_plani', 'fatura', 'fatura_kalem', 'kasa_banka', 'parca_basi', 'parca_basi_satir', 'fazla_calisma', 'hazine_payi', 'yil_sonu', 'utp_kisi', 'hesap_plani', 'yevmiye', 'yevmiye_satir', 'resmi_yazi', 'denetim', 'denetim_madde', 'onay_durum', 'onay_kaydi'] LOOP EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t); END LOOP; END $$;
