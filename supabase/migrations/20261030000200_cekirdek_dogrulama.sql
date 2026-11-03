-- Server-side validation, optimistic concurrency, delete protection and audit for kurum and definitions.

CREATE OR REPLACE FUNCTION dose_private.bos(p TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$ SELECT nullif(btrim(p), '') $$;

CREATE OR REPLACE FUNCTION dose_private.hata(p_mesaj TEXT) RETURNS VOID
LANGUAGE plpgsql VOLATILE SET search_path = '' AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = p_mesaj;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.tckn_gecerli(p TEXT) RETURNS BOOLEAN
LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
DECLARE
    t TEXT := btrim(coalesce(p, ''));
    d INTEGER[];
BEGIN
    IF t !~ '^[1-9][0-9]{10}$' THEN
        RETURN false;
    END IF;
    SELECT array_agg(substr(t, g, 1)::INTEGER ORDER BY g) INTO d FROM generate_series(1, 11) AS g;
    IF ((((d[1] + d[3] + d[5] + d[7] + d[9]) * 7 - (d[2] + d[4] + d[6] + d[8])) % 10) + 10) % 10 <> d[10] THEN
        RETURN false;
    END IF;
    RETURN (d[1] + d[2] + d[3] + d[4] + d[5] + d[6] + d[7] + d[8] + d[9] + d[10]) % 10 = d[11];
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.vkn_gecerli(p TEXT) RETURNS BOOLEAN
LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
DECLARE
    v TEXT := btrim(coalesce(p, ''));
    toplam INTEGER := 0;
    tmp INTEGER;
BEGIN
    IF v !~ '^[0-9]{10}$' THEN
        RETURN false;
    END IF;
    FOR i IN 1..9 LOOP
        tmp := (substr(v, i, 1)::INTEGER + 10 - i) % 10;
        IF tmp = 9 THEN
            toplam := toplam + 9;
        ELSE
            toplam := toplam + (tmp * (1 << (10 - i))) % 9;
        END IF;
    END LOOP;
    RETURN (10 - (toplam % 10)) % 10 = substr(v, 10, 1)::INTEGER;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.vkn_veya_tckn_gecerli(p TEXT) RETURNS BOOLEAN
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
    SELECT CASE WHEN length(btrim(coalesce(p, ''))) = 11 THEN dose_private.tckn_gecerli(p)
                ELSE dose_private.vkn_gecerli(p) END
$$;

CREATE OR REPLACE FUNCTION dose_private.iban_normalize(p TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
    SELECT upper(regexp_replace(coalesce(p, ''), '[[:space:]]+', '', 'g'))
$$;

CREATE OR REPLACE FUNCTION dose_private.iban_gecerli(p TEXT) RETURNS BOOLEAN
LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
DECLARE
    i TEXT := dose_private.iban_normalize(p);
    yeniden TEXT;
    sayisal TEXT := '';
    c TEXT;
    kalan INTEGER := 0;
BEGIN
    IF i !~ '^TR[0-9]{24}$' THEN
        RETURN false;
    END IF;
    yeniden := substr(i, 5) || substr(i, 1, 4);
    FOR k IN 1..length(yeniden) LOOP
        c := substr(yeniden, k, 1);
        sayisal := sayisal || CASE WHEN c ~ '[0-9]' THEN c ELSE (ascii(c) - 55)::TEXT END;
    END LOOP;
    FOR k IN 1..length(sayisal) LOOP
        kalan := (kalan * 10 + substr(sayisal, k, 1)::INTEGER) % 97;
    END LOOP;
    RETURN kalan = 1;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.iban_kontrol(p_iban TEXT) RETURNS TEXT
LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
BEGIN
    IF dose_private.bos(p_iban) IS NULL THEN
        RETURN NULL;
    END IF;
    IF NOT dose_private.iban_gecerli(p_iban) THEN
        PERFORM dose_private.hata('IBAN geçersiz (TR ile başlayan 26 karakter olmalı).');
    END IF;
    RETURN dose_private.iban_normalize(p_iban);
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.tarih_gecerli(p TEXT) RETURNS BOOLEAN
LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
BEGIN
    IF p IS NULL THEN
        RETURN true;
    END IF;
    IF p !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
        RETURN false;
    END IF;
    RETURN to_char(p::DATE, 'YYYY-MM-DD') = p;
EXCEPTION WHEN others THEN
    RETURN false;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.secenekte(p_liste TEXT, p_deger TEXT) RETURNS BOOLEAN
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT p_deger IS NULL OR EXISTS (SELECT 1 FROM public.secenek s WHERE s.liste = p_liste AND s.deger = p_deger)
$$;

CREATE OR REPLACE FUNCTION dose_private.sayi_kontrol(p_deger DOUBLE PRECISION, p_etiket TEXT, p_oran BOOLEAN DEFAULT false)
RETURNS VOID
LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
BEGIN
    IF p_deger IS NOT NULL AND (p_deger IN ('NaN'::DOUBLE PRECISION, 'Infinity'::DOUBLE PRECISION, '-Infinity'::DOUBLE PRECISION)
                                OR p_deger < 0 OR (p_oran AND p_deger > 1)) THEN
        PERFORM dose_private.hata(format('''%s'' aralık dışında.', p_etiket));
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.bolum_aktif_kontrol(p_okul INTEGER, p_yeni INTEGER, p_eski INTEGER, p_etiket TEXT)
RETURNS VOID
LANGUAGE plpgsql STABLE SET search_path = '' AS $$
BEGIN
    IF p_yeni IS NOT NULL AND p_yeni IS DISTINCT FROM p_eski
       AND NOT EXISTS (SELECT 1 FROM public.bolum b WHERE b.id = p_yeni AND b.okul_id = p_okul AND b.aktif = 1) THEN
        PERFORM dose_private.hata(format('''%s'' seçimi artık kullanılamıyor.', p_etiket));
    END IF;
END;
$$;

-- ------------------------------------------------------------------ optimistic concurrency
CREATE OR REPLACE FUNCTION dose_private.surum_isle() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_kim TEXT;
BEGIN
    SELECT u.ad_soyad || ' (' || u.rol || ')' INTO v_kim FROM dose_private.uyelik u WHERE u.auth_user_id = auth.uid();
    IF TG_OP = 'UPDATE' THEN
        IF NEW.okul_id IS DISTINCT FROM OLD.okul_id THEN
            PERFORM dose_private.hata('Kaydın okulu değiştirilemez.');
        END IF;
        IF NEW.surum IS DISTINCT FROM OLD.surum THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', HINT = 'surum_cakismasi',
                MESSAGE = format('Bu kaydı siz düzenlerken %s değiştirdi (%s). Güncel hali yüklendi; değişikliğinizi yeniden yapın.',
                                 coalesce(OLD.guncelleyen, 'başka bir kullanıcı'), coalesce(OLD.guncelleme, '-'));
        END IF;
        NEW.surum := OLD.surum + 1;
    ELSE
        NEW.surum := 1;
    END IF;
    NEW.guncelleyen := coalesce(v_kim, 'Sistem');
    NEW.guncelleme := dose_private.zaman();
    RETURN NEW;
END;
$$;

-- ------------------------------------------------------------------ definition validation
CREATE OR REPLACE FUNCTION dose_private.tanim_dogrula() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_eski_bolum INTEGER;
    v_eski_malzeme INTEGER;
    v_ad TEXT;
BEGIN
    IF NEW.okul_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Bu işlem için aktif bir okul üyeliğiniz olmalıdır.';
    END IF;
    IF TG_TABLE_NAME <> 'kurum' THEN
        NEW.aktif := coalesce(NEW.aktif, 1);
        IF NEW.aktif NOT IN (0, 1) THEN
            PERFORM dose_private.hata('''Aktif'' alanı doğru/yanlış olmalıdır.');
        END IF;
    END IF;

    IF TG_TABLE_NAME = 'bolum' THEN
        NEW.kod := dose_private.bos(NEW.kod);
        NEW.ad := dose_private.bos(NEW.ad);
        NEW.alan := dose_private.bos(NEW.alan);
        NEW.aciklama := dose_private.bos(NEW.aciklama);
        IF NEW.ad IS NULL THEN
            PERFORM dose_private.hata('''Bölüm / atölye adı'' alanı zorunludur.');
        END IF;
        IF NEW.utp_yontemi IS NULL OR NOT dose_private.secenekte('utp_yontemi', NEW.utp_yontemi) THEN
            PERFORM dose_private.hata('''ÜTP dağıtım yöntemi'' seçimi geçersiz.');
        END IF;

    ELSIF TG_TABLE_NAME = 'personel' THEN
        IF TG_OP = 'UPDATE' THEN
            v_eski_bolum := OLD.bolum_id;
        END IF;
        NEW.sicil_no := dose_private.bos(NEW.sicil_no);
        NEW.tckn := dose_private.bos(NEW.tckn);
        NEW.ad_soyad := dose_private.bos(NEW.ad_soyad);
        NEW.kadro_unvani := dose_private.bos(NEW.kadro_unvani);
        NEW.telefon := dose_private.bos(NEW.telefon);
        NEW.eposta := dose_private.bos(NEW.eposta);
        NEW.notlar := dose_private.bos(NEW.notlar);
        IF NEW.ad_soyad IS NULL THEN
            PERFORM dose_private.hata('''Adı soyadı'' alanı zorunludur.');
        END IF;
        IF NEW.hizmet_sinifi IS NULL OR NOT dose_private.secenekte('hizmet_sinifi', NEW.hizmet_sinifi) THEN
            PERFORM dose_private.hata('''Hizmet sınıfı'' seçimi geçersiz.');
        END IF;
        IF NEW.dose_gorevi IS NULL OR NOT dose_private.secenekte('dose_gorevi', NEW.dose_gorevi) THEN
            PERFORM dose_private.hata('''DÖSE görevi'' seçimi geçersiz.');
        END IF;
        IF NOT dose_private.secenekte('unvan_grubu', NEW.unvan_grubu::TEXT) THEN
            PERFORM dose_private.hata('''Unvan puan grubu'' seçimi geçersiz.');
        END IF;
        IF NOT dose_private.secenekte('istihdam', NEW.istihdam) THEN
            PERFORM dose_private.hata('''İstihdam'' seçimi geçersiz.');
        END IF;
        PERFORM dose_private.bolum_aktif_kontrol(NEW.okul_id, NEW.bolum_id, v_eski_bolum, 'Bölüm / atölye');
        NEW.iban := dose_private.iban_kontrol(NEW.iban);
        IF NEW.tckn IS NOT NULL AND NOT dose_private.tckn_gecerli(NEW.tckn) THEN
            PERFORM dose_private.hata('T.C. kimlik numarası geçersiz.');
        END IF;
        IF NEW.tckn IS NOT NULL AND EXISTS (SELECT 1 FROM public.personel p
                                            WHERE p.okul_id = NEW.okul_id AND p.tckn = NEW.tckn AND p.id <> NEW.id) THEN
            PERFORM dose_private.hata('Bu T.C. kimlik numarası başka bir kayıtta kullanılıyor.');
        END IF;
        IF NEW.aktif = 1 AND NEW.dose_gorevi IN ('Harcama Yetkilisi (Okul Müdürü)',
                                                 'Gerçekleştirme Görevlisi (Teknik Md. Yrd.)', 'Sayman') THEN
            SELECT p.ad_soyad INTO v_ad FROM public.personel p
            WHERE p.okul_id = NEW.okul_id AND p.dose_gorevi = NEW.dose_gorevi AND p.aktif = 1 AND p.id <> NEW.id LIMIT 1;
            IF FOUND THEN
                PERFORM dose_private.hata(format('''%s'' görevinde aktif başka personel var (%s); önceki kaydı pasif yapınız.',
                                                 NEW.dose_gorevi, v_ad));
            END IF;
        END IF;

    ELSIF TG_TABLE_NAME = 'ogrenci' THEN
        IF TG_OP = 'UPDATE' THEN
            v_eski_bolum := OLD.bolum_id;
        END IF;
        NEW.okul_no := dose_private.bos(NEW.okul_no);
        NEW.tckn := dose_private.bos(NEW.tckn);
        NEW.ad_soyad := dose_private.bos(NEW.ad_soyad);
        NEW.dogum_tarihi := dose_private.bos(NEW.dogum_tarihi);
        NEW.muvafakat_tarihi := dose_private.bos(NEW.muvafakat_tarihi);
        NEW.sinif := dose_private.bos(NEW.sinif);
        NEW.veli_adi := dose_private.bos(NEW.veli_adi);
        NEW.veli_telefon := dose_private.bos(NEW.veli_telefon);
        NEW.notlar := dose_private.bos(NEW.notlar);
        NEW.veli_muvafakat := coalesce(NEW.veli_muvafakat, 0);
        IF NEW.ad_soyad IS NULL THEN
            PERFORM dose_private.hata('''Adı soyadı'' alanı zorunludur.');
        END IF;
        IF NEW.veli_muvafakat NOT IN (0, 1) THEN
            PERFORM dose_private.hata('''Veli yazılı muvafakati'' alanı doğru/yanlış olmalıdır.');
        END IF;
        IF NOT dose_private.tarih_gecerli(NEW.dogum_tarihi) THEN
            PERFORM dose_private.hata('''Doğum tarihi'' geçerli bir tarih olmalıdır (YYYY-AA-GG).');
        END IF;
        IF NOT dose_private.tarih_gecerli(NEW.muvafakat_tarihi) THEN
            PERFORM dose_private.hata('''Muvafakat tarihi'' geçerli bir tarih olmalıdır (YYYY-AA-GG).');
        END IF;
        PERFORM dose_private.bolum_aktif_kontrol(NEW.okul_id, NEW.bolum_id, v_eski_bolum, 'Alan / bölüm');
        NEW.iban := dose_private.iban_kontrol(NEW.iban);
        IF NEW.tckn IS NOT NULL AND NOT dose_private.tckn_gecerli(NEW.tckn) THEN
            PERFORM dose_private.hata('T.C. kimlik numarası geçersiz.');
        END IF;
        IF NEW.tckn IS NOT NULL AND EXISTS (SELECT 1 FROM public.ogrenci o
                                            WHERE o.okul_id = NEW.okul_id AND o.tckn = NEW.tckn AND o.id <> NEW.id) THEN
            PERFORM dose_private.hata('Bu T.C. kimlik numarası başka bir kayıtta kullanılıyor.');
        END IF;
        IF NEW.veli_muvafakat = 1 AND NEW.muvafakat_tarihi IS NULL THEN
            PERFORM dose_private.hata('Veli muvafakat tarihi giriniz.');
        END IF;

    ELSIF TG_TABLE_NAME = 'cari' THEN
        NEW.kod := dose_private.bos(NEW.kod);
        NEW.unvan := dose_private.bos(NEW.unvan);
        NEW.vkn_tckn := dose_private.bos(NEW.vkn_tckn);
        NEW.vergi_dairesi := dose_private.bos(NEW.vergi_dairesi);
        NEW.telefon := dose_private.bos(NEW.telefon);
        NEW.eposta := dose_private.bos(NEW.eposta);
        NEW.adres := dose_private.bos(NEW.adres);
        NEW.notlar := dose_private.bos(NEW.notlar);
        NEW.kamu_kurumu := coalesce(NEW.kamu_kurumu, 0);
        IF NEW.unvan IS NULL THEN
            PERFORM dose_private.hata('''Unvan / adı soyadı'' alanı zorunludur.');
        END IF;
        IF NEW.tur IS NULL OR NOT dose_private.secenekte('cari_tur', NEW.tur) THEN
            PERFORM dose_private.hata('''Türü'' seçimi geçersiz.');
        END IF;
        IF NEW.kamu_kurumu NOT IN (0, 1) THEN
            PERFORM dose_private.hata('''Kamu kurumu'' alanı doğru/yanlış olmalıdır.');
        END IF;
        IF NEW.vkn_tckn IS NOT NULL AND NOT dose_private.vkn_veya_tckn_gecerli(NEW.vkn_tckn) THEN
            PERFORM dose_private.hata('Vergi kimlik / T.C. kimlik numarası geçersiz.');
        END IF;
        IF NEW.tur = 'Çiftçi (Müstahsil)' AND NEW.vkn_tckn IS NOT NULL AND length(NEW.vkn_tckn) <> 11 THEN
            PERFORM dose_private.hata('Müstahsil makbuzu için çiftçinin T.C. kimlik numarası girilmelidir.');
        END IF;
        NEW.iban := dose_private.iban_kontrol(NEW.iban);
        IF TG_OP = 'INSERT' AND NEW.kod IS NULL THEN
            NEW.kod := 'C' || lpad(dose_private.sira_no(NEW.okul_id, 'cari')::TEXT, 4, '0');
        END IF;

    ELSIF TG_TABLE_NAME = 'malzeme' THEN
        NEW.kod := dose_private.bos(NEW.kod);
        NEW.ad := dose_private.bos(NEW.ad);
        NEW.aciklama := dose_private.bos(NEW.aciklama);
        IF NEW.ad IS NULL THEN
            PERFORM dose_private.hata('''Malzeme adı'' alanı zorunludur.');
        END IF;
        IF NEW.tur IS NULL OR NOT dose_private.secenekte('malzeme_tur', NEW.tur) THEN
            PERFORM dose_private.hata('''Türü'' seçimi geçersiz.');
        END IF;
        IF NOT dose_private.secenekte('birim', NEW.birim) THEN
            PERFORM dose_private.hata('''Birim'' seçimi geçersiz.');
        END IF;
        PERFORM dose_private.sayi_kontrol(NEW.kdv_orani, 'KDV oranı', true);
        PERFORM dose_private.sayi_kontrol(NEW.kritik_stok, 'Kritik stok miktarı');

    ELSIF TG_TABLE_NAME = 'urun' THEN
        IF TG_OP = 'UPDATE' THEN
            v_eski_bolum := OLD.bolum_id;
            v_eski_malzeme := OLD.mamul_malzeme_id;
        END IF;
        NEW.kod := dose_private.bos(NEW.kod);
        NEW.ad := dose_private.bos(NEW.ad);
        NEW.aciklama := dose_private.bos(NEW.aciklama);
        IF NEW.ad IS NULL THEN
            PERFORM dose_private.hata('''Ürün / hizmet adı'' alanı zorunludur.');
        END IF;
        IF NEW.tur IS NULL OR NOT dose_private.secenekte('urun_tur', NEW.tur) THEN
            PERFORM dose_private.hata('''Türü'' seçimi geçersiz.');
        END IF;
        IF NOT dose_private.secenekte('birim', NEW.birim) THEN
            PERFORM dose_private.hata('''Birim'' seçimi geçersiz.');
        END IF;
        IF NOT dose_private.secenekte('ucret_esasi', NEW.ucret_esasi) THEN
            PERFORM dose_private.hata('''Ücret ödeme esası'' seçimi geçersiz.');
        END IF;
        PERFORM dose_private.bolum_aktif_kontrol(NEW.okul_id, NEW.bolum_id, v_eski_bolum, 'Bölüm / atölye');
        PERFORM dose_private.sayi_kontrol(NEW.kdv_orani, 'KDV oranı', true);
        PERFORM dose_private.sayi_kontrol(NEW.kar_orani, 'Hedef kâr oranı', true);
        PERFORM dose_private.sayi_kontrol(NEW.satis_fiyati, 'Birim satış fiyatı');
        IF NEW.mamul_malzeme_id IS NOT NULL AND NEW.mamul_malzeme_id IS DISTINCT FROM v_eski_malzeme
           AND NOT EXISTS (SELECT 1 FROM public.malzeme m WHERE m.id = NEW.mamul_malzeme_id AND m.okul_id = NEW.okul_id
                           AND m.aktif = 1 AND m.tur IN ('Mamul', 'Ticari Mal')) THEN
            PERFORM dose_private.hata('''Stoktaki mamul kartı'' seçimi artık kullanılamıyor.');
        END IF;

    ELSIF TG_TABLE_NAME = 'kurum' THEN
        NEW.okul_adi := dose_private.bos(NEW.okul_adi);
        NEW.vkn := dose_private.bos(NEW.vkn);
        IF NEW.okul_adi IS NULL THEN
            PERFORM dose_private.hata('Okul adı zorunludur.');
        END IF;
        IF NEW.vkn IS NOT NULL AND NOT dose_private.vkn_veya_tckn_gecerli(NEW.vkn) THEN
            PERFORM dose_private.hata('Vergi kimlik numarası geçersiz.');
        END IF;
        NEW.iban := dose_private.iban_kontrol(NEW.iban);
        PERFORM dose_private.sayi_kontrol(NEW.tahsis_sermaye, 'Tahsis edilen sermaye');
        PERFORM dose_private.sayi_kontrol(NEW.odenmis_sermaye, 'Ödenmiş sermaye');
        IF coalesce(NEW.buyuksehir, 0) NOT IN (0, 1) OR coalesce(NEW.yuz_yuze_egitim, 1) NOT IN (0, 1) THEN
            PERFORM dose_private.hata('Kurum doğru/yanlış alanları 0 veya 1 olmalıdır.');
        END IF;
        IF TG_OP = 'UPDATE' AND NEW.kurum_kodu IS DISTINCT FROM OLD.kurum_kodu THEN
            PERFORM dose_private.hata('Kurum kodu lisansa bağlıdır; değiştirilemez.');
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

-- ------------------------------------------------------------------ delete protection
CREATE OR REPLACE FUNCTION dose_private.silme_koruma() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_kullanilan BOOLEAN := false;
BEGIN
    IF TG_TABLE_NAME = 'bolum' THEN
        v_kullanilan := EXISTS (SELECT 1 FROM public.personel WHERE bolum_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.ogrenci WHERE bolum_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.urun WHERE bolum_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.siparis WHERE bolum_id = OLD.id)
            OR EXISTS (SELECT 1 FROM dose_private.uyelik WHERE bolum_id = OLD.id)
            OR EXISTS (SELECT 1 FROM dose_private.davet WHERE bolum_id = OLD.id);
    ELSIF TG_TABLE_NAME = 'personel' THEN
        v_kullanilan := EXISTS (SELECT 1 FROM public.parca_basi_satir WHERE kisi_turu = 'Personel' AND kisi_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.siparis_gorevli WHERE kisi_turu = 'Personel' AND kisi_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.fazla_calisma WHERE personel_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.utp_kisi WHERE personel_id = OLD.id)
            OR EXISTS (SELECT 1 FROM dose_private.uyelik WHERE personel_id = OLD.id)
            OR EXISTS (SELECT 1 FROM dose_private.davet WHERE personel_id = OLD.id);
    ELSIF TG_TABLE_NAME = 'ogrenci' THEN
        v_kullanilan := EXISTS (SELECT 1 FROM public.parca_basi_satir WHERE kisi_turu = 'Öğrenci' AND kisi_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.siparis_gorevli WHERE kisi_turu = 'Öğrenci' AND kisi_id = OLD.id);
    ELSIF TG_TABLE_NAME = 'cari' THEN
        v_kullanilan := EXISTS (SELECT 1 FROM public.fatura WHERE cari_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.siparis WHERE cari_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.kasa_banka WHERE cari_id = OLD.id);
    ELSIF TG_TABLE_NAME = 'malzeme' THEN
        v_kullanilan := EXISTS (SELECT 1 FROM public.stok_hareket WHERE malzeme_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.fatura_kalem WHERE malzeme_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.maliyet_kalem WHERE malzeme_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.urun WHERE mamul_malzeme_id = OLD.id);
    ELSIF TG_TABLE_NAME = 'urun' THEN
        v_kullanilan := EXISTS (SELECT 1 FROM public.fatura_kalem WHERE urun_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.siparis_kalem WHERE urun_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.maliyet_kalem WHERE urun_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.fiyat_tespit WHERE urun_id = OLD.id);
    END IF;
    IF v_kullanilan THEN
        RAISE EXCEPTION USING ERRCODE = '23503',
            MESSAGE = 'Bu kayıt başka işlemlerde kullanılıyor; silmek yerine pasif yapınız.';
    END IF;
    RETURN OLD;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.degisiklik_kaydi() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_eski JSONB := CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END;
    v_yeni JSONB := CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END;
    v_satir JSONB := coalesce(v_yeni, v_eski);
BEGIN
    PERFORM dose_private.log((v_satir ->> 'okul_id')::INTEGER,
        CASE TG_OP WHEN 'INSERT' THEN 'Ekleme' WHEN 'UPDATE' THEN 'Güncelleme' ELSE 'Silme' END,
        TG_TABLE_NAME, (v_satir ->> 'id')::INTEGER, NULL, v_eski, v_yeni);
    RETURN NULL;
END;
$$;

DROP INDEX IF EXISTS public.ux_personel_tckn;
CREATE UNIQUE INDEX ux_personel_tckn ON public.personel (okul_id, tckn) WHERE tckn IS NOT NULL;
DROP INDEX IF EXISTS public.ux_ogrenci_tckn;
CREATE UNIQUE INDEX ux_ogrenci_tckn ON public.ogrenci (okul_id, tckn) WHERE tckn IS NOT NULL;
DROP INDEX IF EXISTS public.ux_personel_dose_gorevi;
CREATE UNIQUE INDEX ux_personel_dose_gorevi ON public.personel (okul_id, dose_gorevi)
    WHERE aktif = 1 AND dose_gorevi IN ('Harcama Yetkilisi (Okul Müdürü)',
                                        'Gerçekleştirme Görevlisi (Teknik Md. Yrd.)', 'Sayman');

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['kurum', 'bolum', 'personel', 'ogrenci', 'cari', 'malzeme', 'urun'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS dose_a_surum ON public.%I', t);
        EXECUTE format('CREATE TRIGGER dose_a_surum BEFORE INSERT OR UPDATE ON public.%I '
                       'FOR EACH ROW EXECUTE FUNCTION dose_private.surum_isle()', t);
        EXECUTE format('DROP TRIGGER IF EXISTS dose_b_dogrula ON public.%I', t);
        EXECUTE format('CREATE TRIGGER dose_b_dogrula BEFORE INSERT OR UPDATE ON public.%I '
                       'FOR EACH ROW EXECUTE FUNCTION dose_private.tanim_dogrula()', t);
        EXECUTE format('DROP TRIGGER IF EXISTS dose_kayit ON public.%I', t);
        EXECUTE format('CREATE TRIGGER dose_kayit AFTER INSERT OR UPDATE OR DELETE ON public.%I '
                       'FOR EACH ROW EXECUTE FUNCTION dose_private.degisiklik_kaydi()', t);
        IF t <> 'kurum' THEN
            EXECUTE format('DROP TRIGGER IF EXISTS dose_silme ON public.%I', t);
            EXECUTE format('CREATE TRIGGER dose_silme BEFORE DELETE ON public.%I '
                           'FOR EACH ROW EXECUTE FUNCTION dose_private.silme_koruma()', t);
        END IF;
    END LOOP;
END;
$$;
