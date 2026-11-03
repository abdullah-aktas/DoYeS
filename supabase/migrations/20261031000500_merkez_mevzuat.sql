-- Central publications are immutable; every school independently confirms the exact version.
CREATE TABLE dose_private.mevzuat_yoneticisi (
    auth_user_id UUID PRIMARY KEY REFERENCES auth.users(id),
    ad_soyad TEXT NOT NULL CHECK (length(btrim(ad_soyad)) BETWEEN 3 AND 120),
    aktif BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE dose_private.mevzuat_yonetici_gecmis (
    id SERIAL PRIMARY KEY,
    auth_user_id UUID NOT NULL REFERENCES auth.users(id),
    ad_soyad TEXT NOT NULL,
    aktif BOOLEAN NOT NULL,
    islem_zamani TIMESTAMPTZ NOT NULL DEFAULT now(),
    islem_yapan UUID
);

CREATE TABLE dose_private.mevzuat_alani (
    anahtar TEXT PRIMARY KEY,
    etiket TEXT NOT NULL,
    aciklama TEXT NOT NULL,
    sira INTEGER NOT NULL UNIQUE
);

INSERT INTO dose_private.mevzuat_alani (anahtar, etiket, aciklama, sira) VALUES
    ('pb_kar_orani', 'Parça başı asgari kâr', 'Sipariş bedeline oranı.', 1),
    ('pb_faaliyet_orani', 'Parça başı asgari faaliyet gideri', 'Sipariş bedeline oranı.', 2),
    ('os_kar_orani', 'Özel sektör işbirliği asgari kâr', 'Sipariş bedeline oranı.', 3),
    ('os_faaliyet_orani', 'Özel sektör işbirliği asgari faaliyet gideri', 'Sipariş bedeline oranı.', 4),
    ('os_pesin_orani', 'Özel sektör işbirliği asgari peşinat', 'Sipariş bedeline oranı.', 5),
    ('tesis_kar_orani', 'Tesis işletmesi asgari kâr', 'Sipariş bedeline oranı.', 6),
    ('tesis_faaliyet_orani', 'Tesis işletmesi asgari faaliyet gideri', 'Sipariş bedeline oranı.', 7),
    ('tesis_pesin_orani', 'Tesis işletmesi asgari peşinat', 'Sipariş bedeline oranı.', 8),
    ('ogrenci_hakki_orani', 'Asgari öğrenci hakkı', 'İşçilik tutarına oranı.', 9),
    ('malzeme_azami_orani', 'Azami malzeme maliyeti', 'Sipariş bedeline oranı; sınır yoksa %100 girin.', 10);

CREATE TABLE dose_private.mevzuat_kilit (
    baslangic DATE PRIMARY KEY
);

CREATE TABLE dose_private.mevzuat_yayin (
    id SERIAL PRIMARY KEY,
    baslangic DATE NOT NULL,
    kaynak TEXT NOT NULL CHECK (length(btrim(kaynak)) BETWEEN 5 AND 1000),
    degerler JSONB NOT NULL,
    yayinlayan UUID NOT NULL REFERENCES auth.users(id),
    yayin_zamani TIMESTAMPTZ NOT NULL DEFAULT now(),
    istek_id UUID NOT NULL CONSTRAINT mevzuat_yayin_istek_tek UNIQUE
);
CREATE INDEX mevzuat_yayin_tarih_indeks ON dose_private.mevzuat_yayin (baslangic, id DESC);

CREATE TABLE dose_private.mevzuat_onay (
    id SERIAL PRIMARY KEY,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    yayin_id INTEGER NOT NULL REFERENCES dose_private.mevzuat_yayin(id),
    karar BOOLEAN NOT NULL,
    aciklama TEXT NOT NULL CHECK (length(btrim(aciklama)) BETWEEN 5 AND 500),
    kullanici UUID NOT NULL REFERENCES auth.users(id),
    zaman TIMESTAMPTZ NOT NULL DEFAULT now(),
    istek_id UUID NOT NULL,
    CONSTRAINT mevzuat_onay_istek_tek UNIQUE (okul_id, istek_id)
);
CREATE INDEX mevzuat_onay_son_indeks ON dose_private.mevzuat_onay (okul_id, yayin_id, id DESC);

REVOKE ALL ON dose_private.mevzuat_yoneticisi, dose_private.mevzuat_yonetici_gecmis,
    dose_private.mevzuat_alani, dose_private.mevzuat_kilit, dose_private.mevzuat_yayin,
    dose_private.mevzuat_onay FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION dose_private.mevzuat_degismez() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE = '42501',
        MESSAGE = 'Mevzuat yayını veya onay geçmişi değiştirilemez veya silinemez.';
END;
$$;
CREATE TRIGGER dose_mevzuat_yayin_degismez BEFORE UPDATE OR DELETE ON dose_private.mevzuat_yayin
    FOR EACH ROW EXECUTE FUNCTION dose_private.mevzuat_degismez();
CREATE TRIGGER dose_mevzuat_onay_degismez BEFORE UPDATE OR DELETE ON dose_private.mevzuat_onay
    FOR EACH ROW EXECUTE FUNCTION dose_private.mevzuat_degismez();
CREATE TRIGGER dose_mevzuat_yonetici_gecmis_degismez BEFORE UPDATE OR DELETE ON dose_private.mevzuat_yonetici_gecmis
    FOR EACH ROW EXECUTE FUNCTION dose_private.mevzuat_degismez();

CREATE OR REPLACE FUNCTION dose_private.mevzuat_yoneticisi_ata(p_kullanici UUID, p_ad_soyad TEXT, p_aktif BOOLEAN)
RETURNS VOID LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_ad TEXT := nullif(btrim(p_ad_soyad), '');
BEGIN
    IF p_kullanici IS NULL OR p_aktif IS NULL OR v_ad IS NULL OR length(v_ad) NOT BETWEEN 3 AND 120
       OR NOT EXISTS (SELECT 1 FROM auth.users WHERE id = p_kullanici AND email_confirmed_at IS NOT NULL) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = 'Doğrulanmış Auth kullanıcısı, ad soyad ve aktiflik durumu gereklidir.';
    END IF;
    INSERT INTO dose_private.mevzuat_yoneticisi (auth_user_id, ad_soyad, aktif)
    VALUES (p_kullanici, v_ad, p_aktif)
    ON CONFLICT (auth_user_id) DO UPDATE SET ad_soyad = EXCLUDED.ad_soyad, aktif = EXCLUDED.aktif;
    INSERT INTO dose_private.mevzuat_yonetici_gecmis (auth_user_id, ad_soyad, aktif, islem_yapan)
    VALUES (p_kullanici, v_ad, p_aktif, auth.uid());
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.mevzuat_merkez_yetkili() RETURNS BOOLEAN
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT EXISTS (
        SELECT 1 FROM dose_private.mevzuat_yoneticisi m JOIN auth.users u ON u.id = m.auth_user_id
        WHERE m.auth_user_id = auth.uid() AND m.aktif AND u.email_confirmed_at IS NOT NULL)
$$;

-- A central administrator may use the publication screen without joining any school.
ALTER FUNCTION public.dose_ben() RENAME TO dose_ben_okul_baglam;
REVOKE ALL ON FUNCTION public.dose_ben_okul_baglam() FROM PUBLIC, anon, authenticated;
CREATE FUNCTION public.dose_ben() RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_ben JSONB := public.dose_ben_okul_baglam();
    v_ad TEXT;
BEGIN
    IF NOT dose_private.mevzuat_merkez_yetkili() THEN
        RETURN v_ben;
    END IF;
    SELECT ad_soyad INTO v_ad FROM dose_private.mevzuat_yoneticisi WHERE auth_user_id = auth.uid();
    IF v_ben->>'uye' = 'true' THEN
        RETURN v_ben || jsonb_build_object('merkez_mevzuat', true,
            'yetkiler', coalesce(v_ben->'yetkiler', '{}'::JSONB) || jsonb_build_object('merkez_mevzuat', 'y'));
    END IF;
    RETURN jsonb_build_object(
        'uye', true, 'merkez_mevzuat', true, 'rol', 'Merkez Mevzuat Yöneticisi',
        'ad_soyad', v_ad, 'eposta', v_ben->>'eposta',
        'yetkiler', jsonb_build_object('merkez_mevzuat', 'y'), 'okul', NULL);
END;
$$;

INSERT INTO dose_private.sayfa_yetki (sayfa, baslik, kodlar)
VALUES ('mevzuat', 'Merkez parametrelerini doğrulama', 'gggygggg')
ON CONFLICT (sayfa) DO UPDATE SET baslik = EXCLUDED.baslik, kodlar = EXCLUDED.kodlar;

CREATE OR REPLACE FUNCTION dose_private.mevzuat_kilitle(p_baslangic DATE) RETURNS VOID
LANGUAGE plpgsql VOLATILE SET search_path = '' AS $$
BEGIN
    INSERT INTO dose_private.mevzuat_kilit (baslangic) VALUES (p_baslangic)
    ON CONFLICT (baslangic) DO NOTHING;
    PERFORM 1 FROM dose_private.mevzuat_kilit WHERE baslangic = p_baslangic FOR UPDATE;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.mevzuat_alanlari() RETURNS JSONB
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'anahtar', anahtar, 'etiket', etiket, 'aciklama', aciklama) ORDER BY sira), '[]'::JSONB)
    FROM dose_private.mevzuat_alani
$$;

CREATE OR REPLACE FUNCTION public.dose_mevzuat_yayinla(
    p_baslangic DATE, p_kaynak TEXT, p_degerler JSONB, p_istek UUID
) RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_kaynak TEXT := nullif(btrim(p_kaynak), '');
    v_alan dose_private.mevzuat_alani%ROWTYPE;
    v_deger TEXT;
    v_id INTEGER;
    v_kisit TEXT;
BEGIN
    IF auth.uid() IS NULL OR NOT dose_private.mevzuat_merkez_yetkili() THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Yalnız yetkili merkez yöneticisi yayın yapabilir.';
    END IF;
    PERFORM 1 FROM dose_private.mevzuat_yoneticisi WHERE auth_user_id = auth.uid() AND aktif FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Merkez yöneticisi yetkisi kapatılmış.';
    END IF;
    IF p_baslangic IS NULL OR p_baslangic NOT BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'
       OR p_istek IS NULL OR v_kaynak IS NULL OR length(v_kaynak) NOT BETWEEN 5 AND 1000 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Başlangıç tarihi, kaynak ve işlem kimliği gereklidir.';
    END IF;
    IF jsonb_typeof(p_degerler) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Parametre değerleri eksik veya geçersiz.';
    END IF;
    IF (SELECT count(*) FROM jsonb_object_keys(p_degerler)) <> (SELECT count(*) FROM dose_private.mevzuat_alani) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Tüm parametreler eksiksiz ve yalnız bir kez girilmelidir.';
    END IF;
    FOR v_alan IN SELECT * FROM dose_private.mevzuat_alani ORDER BY sira LOOP
        v_deger := p_degerler->>v_alan.anahtar;
        IF jsonb_typeof(p_degerler->v_alan.anahtar) IS DISTINCT FROM 'string'
           OR v_deger !~ '^(0|1)(\.[0-9]{1,10})?$' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001',
                MESSAGE = format('%s için 0 ile 1 arasında, en fazla 10 ondalıklı kesin oran giriniz.', v_alan.etiket);
        END IF;
        IF v_deger::NUMERIC > 1 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001',
                MESSAGE = format('%s için 0 ile 1 arasında, en fazla 10 ondalıklı kesin oran giriniz.', v_alan.etiket);
        END IF;
    END LOOP;
    IF (p_degerler->>'pb_kar_orani')::NUMERIC + (p_degerler->>'pb_faaliyet_orani')::NUMERIC > 1
       OR (p_degerler->>'os_kar_orani')::NUMERIC + (p_degerler->>'os_faaliyet_orani')::NUMERIC > 1
       OR (p_degerler->>'tesis_kar_orani')::NUMERIC + (p_degerler->>'tesis_faaliyet_orani')::NUMERIC > 1 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Kâr ve faaliyet oranlarının toplamı %100''ü aşamaz.';
    END IF;
    PERFORM dose_private.mevzuat_kilitle(p_baslangic);
    IF EXISTS (SELECT 1 FROM dose_private.mevzuat_yayin WHERE istek_id = p_istek) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu yayın isteği daha önce kaydedildi; listeyi yenileyin.';
    END IF;
    BEGIN
        INSERT INTO dose_private.mevzuat_yayin (baslangic, kaynak, degerler, yayinlayan, istek_id)
        VALUES (p_baslangic, v_kaynak, p_degerler, auth.uid(), p_istek) RETURNING id INTO v_id;
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS v_kisit = CONSTRAINT_NAME;
        IF v_kisit = 'mevzuat_yayin_istek_tek' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu yayın isteği daha önce kaydedildi; listeyi yenileyin.';
        END IF;
        RAISE;
    END;
    RETURN jsonb_build_object('id', v_id, 'baslangic', p_baslangic);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_mevzuat_merkez_veri() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF auth.uid() IS NULL OR NOT dose_private.mevzuat_merkez_yetkili() THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Merkez parametrelerine erişim yetkiniz yok.';
    END IF;
    RETURN jsonb_build_object('alanlar', dose_private.mevzuat_alanlari(),
        'yayinlar', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', m.id, 'baslangic', m.baslangic, 'kaynak', m.kaynak, 'degerler', m.degerler,
            'yayinlayan', m.yayinlayan, 'yayin_zamani', m.yayin_zamani,
            'son_surum', NOT EXISTS (SELECT 1 FROM dose_private.mevzuat_yayin x
                                     WHERE x.baslangic = m.baslangic AND x.id > m.id))
            ORDER BY m.baslangic DESC, m.id DESC) FROM dose_private.mevzuat_yayin m), '[]'::JSONB));
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_mevzuat_okul_veri() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('mevzuat') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Okul parametrelerine erişim yetkiniz yok.';
    END IF;
    RETURN jsonb_build_object('alanlar', dose_private.mevzuat_alanlari(),
        'yayinlar', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', m.id, 'baslangic', m.baslangic, 'kaynak', m.kaynak, 'degerler', m.degerler,
            'yayinlayan', m.yayinlayan, 'yayin_zamani', m.yayin_zamani,
            'son_surum', NOT EXISTS (SELECT 1 FROM dose_private.mevzuat_yayin x
                                     WHERE x.baslangic = m.baslangic AND x.id > m.id),
            'onay', coalesce(o.karar, false), 'onay_aciklama', o.aciklama,
            'onaylayan', o.kullanici, 'onay_zamani', o.zaman)
            ORDER BY m.baslangic DESC, m.id DESC)
            FROM dose_private.mevzuat_yayin m
            LEFT JOIN LATERAL (
                SELECT karar, aciklama, kullanici, zaman FROM dose_private.mevzuat_onay
                WHERE okul_id = v_okul AND yayin_id = m.id ORDER BY id DESC LIMIT 1
            ) o ON true), '[]'::JSONB));
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_mevzuat_karar(
    p_yayin INTEGER, p_onay BOOLEAN, p_aciklama TEXT, p_istek UUID
) RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_yayin dose_private.mevzuat_yayin%ROWTYPE;
    v_aciklama TEXT := nullif(btrim(p_aciklama), '');
    v_eski BOOLEAN;
    v_id INTEGER;
    v_kisit TEXT;
BEGIN
    IF auth.uid() IS NULL OR public.dose_rol() IS DISTINCT FROM 'Sayman'
       OR public.dose_yetki('mevzuat') IS DISTINCT FROM 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Parametreleri yalnız yetkili okul saymanı doğrulayabilir.';
    END IF;
    IF p_onay IS NULL OR p_istek IS NULL OR v_aciklama IS NULL OR length(v_aciklama) NOT BETWEEN 5 AND 500 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Karar, açıklama ve işlem kimliği zorunludur.';
    END IF;
    SELECT * INTO v_yayin FROM dose_private.mevzuat_yayin WHERE id = p_yayin;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Merkez yayını bulunamadı.';
    END IF;
    PERFORM dose_private.mevzuat_kilitle(v_yayin.baslangic);
    IF EXISTS (SELECT 1 FROM dose_private.mevzuat_onay WHERE okul_id = v_okul AND istek_id = p_istek) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu karar daha önce kaydedildi; listeyi yenileyin.';
    END IF;
    IF p_onay AND EXISTS (SELECT 1 FROM dose_private.mevzuat_yayin
                           WHERE baslangic = v_yayin.baslangic AND id > v_yayin.id) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu yayın güncel değil; son sürümü kontrol edin.';
    END IF;
    SELECT karar INTO v_eski FROM dose_private.mevzuat_onay
    WHERE okul_id = v_okul AND yayin_id = v_yayin.id ORDER BY id DESC LIMIT 1;
    IF coalesce(v_eski, false) = p_onay THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = CASE WHEN p_onay THEN 'Bu yayın zaten doğrulandı.'
                           ELSE 'Geri çekilecek etkin doğrulama bulunamadı.' END;
    END IF;
    BEGIN
        INSERT INTO dose_private.mevzuat_onay (okul_id, yayin_id, karar, aciklama, kullanici, istek_id)
        VALUES (v_okul, p_yayin, p_onay, v_aciklama, auth.uid(), p_istek) RETURNING id INTO v_id;
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS v_kisit = CONSTRAINT_NAME;
        IF v_kisit = 'mevzuat_onay_istek_tek' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu karar daha önce kaydedildi; listeyi yenileyin.';
        END IF;
        RAISE;
    END;
    PERFORM dose_private.log(v_okul, CASE WHEN p_onay THEN 'Merkez parametreleri doğrulandı'
                                          ELSE 'Merkez parametre doğrulaması geri çekildi' END,
        'mevzuat_onay', v_id, v_aciklama, NULL,
        jsonb_build_object('yayin_id', p_yayin, 'baslangic', v_yayin.baslangic, 'karar', p_onay));
    RETURN jsonb_build_object('id', v_id, 'yayin_id', p_yayin, 'onay', p_onay);
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.mevzuat_oku(p_okul INTEGER, p_tarih DATE) RETURNS JSONB
LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE
    v_yayin dose_private.mevzuat_yayin%ROWTYPE;
    v_onay dose_private.mevzuat_onay%ROWTYPE;
BEGIN
    IF p_okul IS NULL OR p_tarih IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Parametre seçimi için okul ve tarih gereklidir.';
    END IF;
    SELECT * INTO v_yayin FROM dose_private.mevzuat_yayin
    WHERE baslangic <= p_tarih AND extract(year FROM baslangic) = extract(year FROM p_tarih)
    ORDER BY baslangic DESC, id DESC LIMIT 1;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu tarih için merkez parametre yayını bulunamadı.';
    END IF;
    SELECT * INTO v_onay FROM dose_private.mevzuat_onay
    WHERE okul_id = p_okul AND yayin_id = v_yayin.id ORDER BY id DESC LIMIT 1;
    IF NOT FOUND OR NOT v_onay.karar THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = 'Bu tarih için güncel merkez parametreleri okul saymanı tarafından doğrulanmamış.';
    END IF;
    RETURN jsonb_build_object('yayin_id', v_yayin.id, 'onay_id', v_onay.id,
        'baslangic', v_yayin.baslangic, 'kaynak', v_yayin.kaynak, 'degerler', v_yayin.degerler);
END;
$$;

REVOKE ALL ON FUNCTION dose_private.mevzuat_degismez(),
    dose_private.mevzuat_yoneticisi_ata(UUID, TEXT, BOOLEAN),
    dose_private.mevzuat_merkez_yetkili(), dose_private.mevzuat_kilitle(DATE),
    dose_private.mevzuat_alanlari(), dose_private.mevzuat_oku(INTEGER, DATE) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION dose_private.mevzuat_yoneticisi_ata(UUID, TEXT, BOOLEAN) TO service_role;
REVOKE ALL ON FUNCTION public.dose_ben(), public.dose_mevzuat_yayinla(DATE, TEXT, JSONB, UUID),
    public.dose_mevzuat_merkez_veri(), public.dose_mevzuat_okul_veri(),
    public.dose_mevzuat_karar(INTEGER, BOOLEAN, TEXT, UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_ben(), public.dose_mevzuat_yayinla(DATE, TEXT, JSONB, UUID),
    public.dose_mevzuat_merkez_veri(), public.dose_mevzuat_okul_veri(),
    public.dose_mevzuat_karar(INTEGER, BOOLEAN, TEXT, UUID) TO authenticated;
