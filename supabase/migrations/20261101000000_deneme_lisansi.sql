-- One-month free trial: a verified user who is not yet in any school may open their own school once.
-- The trial school is a normal, isolated workspace whose license ends one month later; after that it is read-only
-- until the vendor extends it with dose_private.lisans_ayarla (which also ends the trial status).

ALTER TABLE dose_private.okul ADD COLUMN IF NOT EXISTS deneme BOOLEAN NOT NULL DEFAULT false;

-- One trial per account, kept even if the membership or school is later closed.
CREATE TABLE IF NOT EXISTS dose_private.deneme_kaydi (
    auth_user_id UUID PRIMARY KEY REFERENCES auth.users (id) ON DELETE RESTRICT,
    okul_id INTEGER NOT NULL UNIQUE REFERENCES dose_private.okul (id),
    olusturma TIMESTAMPTZ NOT NULL DEFAULT now()
);
REVOKE ALL ON dose_private.deneme_kaydi FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.dose_deneme_baslat(p_okul_adi TEXT, p_kurum_kodu TEXT, p_ad_soyad TEXT)
RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_uid UUID := auth.uid();
    v_onay TIMESTAMPTZ;
    v_eposta TEXT;
    v_ad TEXT;
    v_okul_adi TEXT := btrim(regexp_replace(coalesce(p_okul_adi, ''), '\s+', ' ', 'g'));
    v_kurum TEXT := btrim(coalesce(p_kurum_kodu, ''));
    v_bitis DATE := ((now() AT TIME ZONE 'Europe/Istanbul')::DATE + interval '1 month')::DATE;
    v_okul_id INTEGER;
BEGIN
    IF v_uid IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Önce giriş yapın.';
    END IF;
    SELECT u.email, u.email_confirmed_at INTO v_eposta, v_onay FROM auth.users u WHERE u.id = v_uid;
    IF v_onay IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'E-posta adresiniz henüz doğrulanmadı.';
    END IF;
    -- Serializes concurrent requests of the same account.
    PERFORM pg_advisory_xact_lock(hashtext('dose_deneme:' || v_uid::TEXT));
    IF EXISTS (SELECT 1 FROM dose_private.uyelik WHERE auth_user_id = v_uid) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Bu hesap zaten bir okula bağlı.';
    END IF;
    IF EXISTS (SELECT 1 FROM dose_private.deneme_kaydi WHERE auth_user_id = v_uid) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Bu hesapla deneme süresi daha önce kullanıldı. Yetkili satıcıdan lisans isteyin.';
    END IF;
    IF v_kurum !~ '^[0-9]{5,8}$' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Kurum kodu 5-8 haneli sayı olmalıdır.';
    END IF;
    IF length(v_okul_adi) NOT BETWEEN 3 AND 200 THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Okul adı 3-200 karakter olmalıdır.';
    END IF;
    v_ad := dose_private.ad_soyad_kontrol(p_ad_soyad);

    INSERT INTO dose_private.okul (ad, kurum_kodu, lisans_bitis, deneme)
    VALUES (v_okul_adi, v_kurum, v_bitis, true)
    ON CONFLICT (kurum_kodu) DO NOTHING
    RETURNING id INTO v_okul_id;
    IF v_okul_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '22023',
            MESSAGE = 'Bu kurum koduyla açılmış bir okul zaten var. Okul müdürünüzden davet isteyin.';
    END IF;

    INSERT INTO dose_private.deneme_kaydi (auth_user_id, okul_id) VALUES (v_uid, v_okul_id);
    INSERT INTO dose_private.uyelik (auth_user_id, okul_id, rol, ad_soyad) VALUES (v_uid, v_okul_id, 'Okul Müdürü', v_ad);
    DELETE FROM dose_private.davet WHERE eposta = lower(v_eposta);
    INSERT INTO public.kurum (okul_id, okul_adi, kurum_kodu) VALUES (v_okul_id, v_okul_adi, v_kurum)
    ON CONFLICT (okul_id) DO NOTHING;
    PERFORM dose_private.log(v_okul_id, 'Deneme başlatıldı', 'okul', v_okul_id,
                             format('%s bir aylık denemeyi başlattı; bitiş %s.', v_ad, to_char(v_bitis, 'DD.MM.YYYY')));
    RETURN jsonb_build_object('basarili', true, 'rol', 'Okul Müdürü', 'okul', v_okul_adi, 'lisans_bitis', v_bitis);
END;
$$;

-- Extending or closing a license from the vendor side ends the trial status.
CREATE OR REPLACE FUNCTION dose_private.lisans_ayarla(p_kurum_kodu TEXT, p_lisans_bitis DATE, p_aktif BOOLEAN DEFAULT true)
RETURNS VOID
LANGUAGE plpgsql VOLATILE SET search_path = '' AS $$
BEGIN
    UPDATE dose_private.okul SET lisans_bitis = p_lisans_bitis, aktif = coalesce(p_aktif, true), deneme = false
    WHERE kurum_kodu = btrim(p_kurum_kodu);
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Bu kurum koduyla açılmış okul yok.';
    END IF;
END;
$$;

-- dose_ben also reports the trial status and remaining days of the active school.
CREATE OR REPLACE FUNCTION public.dose_ben() RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_ben JSONB := public.dose_ben_okul_baglam();
    v_ad TEXT;
    v_okul dose_private.okul%ROWTYPE;
BEGIN
    IF jsonb_typeof(v_ben->'okul') = 'object' THEN
        SELECT * INTO v_okul FROM dose_private.okul WHERE id = (v_ben->'okul'->>'id')::INTEGER;
        v_ben := jsonb_set(v_ben, '{okul}', (v_ben->'okul') || jsonb_build_object(
            'deneme', v_okul.deneme,
            'kalan_gun', CASE WHEN v_okul.lisans_bitis IS NULL THEN NULL
                              ELSE greatest(v_okul.lisans_bitis - (now() AT TIME ZONE 'Europe/Istanbul')::DATE + 1, 0) END));
    END IF;
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

REVOKE ALL ON FUNCTION dose_private.lisans_ayarla(TEXT, DATE, BOOLEAN) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION dose_private.lisans_ayarla(TEXT, DATE, BOOLEAN) TO service_role;
REVOKE ALL ON FUNCTION public.dose_deneme_baslat(TEXT, TEXT, TEXT), public.dose_ben() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_deneme_baslat(TEXT, TEXT, TEXT), public.dose_ben() TO authenticated;
