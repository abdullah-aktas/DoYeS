-- Activation, session context, user management RPCs, grants and row level security policies.

CREATE OR REPLACE FUNCTION dose_private.rol_baglami_dogrula(p_okul INTEGER, p_rol TEXT, p_bolum INTEGER, p_personel INTEGER)
RETURNS VOID
LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE
    v_personel_bolum INTEGER;
BEGIN
    IF p_rol IS NULL OR p_rol NOT IN ('Sistem Yöneticisi', 'Okul Müdürü', 'Teknik Müdür Yardımcısı', 'Sayman',
                                      'Alan Şefi', 'Öğretmen', 'Memur / Veri Girişi', 'İzleyici / Denetçi') THEN
        PERFORM dose_private.hata('Rol geçersiz.');
    END IF;
    IF p_personel IS NOT NULL THEN
        SELECT p.bolum_id INTO v_personel_bolum FROM public.personel p
        WHERE p.id = p_personel AND p.okul_id = p_okul AND p.aktif = 1;
        IF NOT FOUND THEN
            PERFORM dose_private.hata('Seçilen personel bu okulda aktif değil.');
        END IF;
    END IF;
    IF p_bolum IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.bolum b
                                           WHERE b.id = p_bolum AND b.okul_id = p_okul AND b.aktif = 1) THEN
        PERFORM dose_private.hata('Seçilen bölüm bu okulda aktif değil.');
    END IF;
    IF p_rol = 'Öğretmen' AND p_personel IS NULL THEN
        PERFORM dose_private.hata('Öğretmen kullanıcısı personel kaydına bağlanmalıdır.');
    END IF;
    IF p_rol IN ('Alan Şefi', 'Öğretmen') AND coalesce(p_bolum, v_personel_bolum) IS NULL THEN
        PERFORM dose_private.hata('Alan şefi ve öğretmen için bölüm / atölye seçilmelidir.');
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.ad_soyad_kontrol(p TEXT) RETURNS TEXT
LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
DECLARE
    v TEXT := btrim(regexp_replace(coalesce(p, ''), '\s+', ' ', 'g'));
BEGIN
    IF length(v) < 3 OR length(v) > 120 THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Ad soyad 3-120 karakter olmalıdır.';
    END IF;
    RETURN v;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.yonetici_kontrol() RETURNS INTEGER
LANGUAGE plpgsql STABLE SET search_path = '' AS $$
BEGIN
    IF public.dose_yetki('kullanici') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Kullanıcı yönetimi yetkiniz yok.';
    END IF;
    RETURN public.dose_okul();
END;
$$;

-- ------------------------------------------------------------------ first principal: license activation
CREATE OR REPLACE FUNCTION public.dose_okul_etkinlestir(p_kod TEXT, p_kurum_kodu TEXT, p_ad_soyad TEXT)
RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_uid UUID := auth.uid();
    v_eposta TEXT;
    v_onay TIMESTAMPTZ;
    v_ad TEXT;
    v_okul dose_private.okul%ROWTYPE;
    v_genel CONSTANT TEXT := 'Etkinleştirme kodu veya kurum kodu hatalı ya da süresi dolmuş. Yetkili satıcıdan yeni kod isteyin.';
BEGIN
    IF v_uid IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Önce giriş yapın.';
    END IF;
    SELECT u.email, u.email_confirmed_at INTO v_eposta, v_onay FROM auth.users u WHERE u.id = v_uid;
    IF v_onay IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'E-posta adresiniz henüz doğrulanmadı.';
    END IF;
    IF EXISTS (SELECT 1 FROM dose_private.uyelik WHERE auth_user_id = v_uid) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Bu hesap zaten bir okula bağlı.';
    END IF;
    IF btrim(coalesce(p_kurum_kodu, '')) !~ '^[0-9]{5,8}$' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Kurum kodu 5-8 haneli sayı olmalıdır.';
    END IF;
    v_ad := dose_private.ad_soyad_kontrol(p_ad_soyad);

    SELECT * INTO v_okul FROM dose_private.okul WHERE kurum_kodu = btrim(p_kurum_kodu) FOR UPDATE;
    IF NOT FOUND OR NOT v_okul.aktif OR v_okul.kod_ozet IS NULL OR v_okul.kod_kullanim IS NOT NULL
       OR v_okul.kod_bitis < now() OR v_okul.hatali_deneme >= 5 THEN
        RETURN jsonb_build_object('basarili', false, 'hata', v_genel);
    END IF;
    IF dose_private.kod_ozeti(p_kod) <> v_okul.kod_ozet THEN
        -- Returning instead of raising keeps the failed-attempt counter committed.
        UPDATE dose_private.okul SET hatali_deneme = hatali_deneme + 1 WHERE id = v_okul.id;
        RETURN jsonb_build_object('basarili', false, 'hata', v_genel);
    END IF;

    INSERT INTO dose_private.uyelik (auth_user_id, okul_id, rol, ad_soyad)
    VALUES (v_uid, v_okul.id, 'Okul Müdürü', v_ad);
    DELETE FROM dose_private.davet WHERE eposta = lower(v_eposta);
    INSERT INTO public.kurum (okul_id, okul_adi, kurum_kodu) VALUES (v_okul.id, v_okul.ad, v_okul.kurum_kodu)
    ON CONFLICT (okul_id) DO NOTHING;
    UPDATE dose_private.okul SET kod_kullanim = now(), kod_kullanan = v_uid, kod_ozet = NULL WHERE id = v_okul.id;
    PERFORM dose_private.log(v_okul.id, 'Okul etkinleştirildi', 'okul', v_okul.id,
                             format('%s ilk Okul Müdürü olarak bağlandı.', v_ad));
    RETURN jsonb_build_object('basarili', true, 'rol', 'Okul Müdürü', 'okul', v_okul.ad);
END;
$$;

-- ------------------------------------------------------------------ who am I (also accepts a pending invitation)
CREATE OR REPLACE FUNCTION public.dose_ben() RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_uid UUID := auth.uid();
    v_eposta TEXT;
    v_onay TIMESTAMPTZ;
    v_davet dose_private.davet%ROWTYPE;
    v_uye dose_private.uyelik%ROWTYPE;
    v_okul dose_private.okul%ROWTYPE;
BEGIN
    IF v_uid IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Önce giriş yapın.';
    END IF;
    SELECT lower(u.email), u.email_confirmed_at INTO v_eposta, v_onay FROM auth.users u WHERE u.id = v_uid;
    SELECT * INTO v_uye FROM dose_private.uyelik WHERE auth_user_id = v_uid;
    IF NOT FOUND AND v_onay IS NOT NULL THEN
        SELECT d.* INTO v_davet FROM dose_private.davet d JOIN dose_private.okul o ON o.id = d.okul_id
        WHERE d.eposta = v_eposta AND d.bitis > now() AND o.aktif
        FOR UPDATE OF d;
        IF FOUND THEN
            INSERT INTO dose_private.uyelik (auth_user_id, okul_id, rol, ad_soyad, bolum_id, personel_id)
            VALUES (v_uid, v_davet.okul_id, v_davet.rol, v_davet.ad_soyad, v_davet.bolum_id, v_davet.personel_id)
            RETURNING * INTO v_uye;
            DELETE FROM dose_private.davet WHERE eposta = v_eposta;
            PERFORM dose_private.log(v_davet.okul_id, 'Davet kabul edildi', 'uyelik', NULL,
                                     format('%s (%s) okula katıldı.', v_davet.ad_soyad, v_davet.rol));
        END IF;
    END IF;
    IF v_uye.auth_user_id IS NULL THEN
        RETURN jsonb_build_object('uye', false, 'eposta', v_eposta, 'eposta_dogrulandi', v_onay IS NOT NULL);
    END IF;
    SELECT * INTO v_okul FROM dose_private.okul WHERE id = v_uye.okul_id;
    IF NOT v_uye.aktif THEN
        RETURN jsonb_build_object('uye', false, 'pasif', true, 'eposta', v_eposta);
    END IF;
    IF NOT v_okul.aktif THEN
        RETURN jsonb_build_object('uye', false, 'okul_kapali', true, 'eposta', v_eposta);
    END IF;
    RETURN jsonb_build_object(
        'uye', true, 'rol', v_uye.rol, 'ad_soyad', v_uye.ad_soyad, 'eposta', v_eposta,
        'bolum_id', v_uye.bolum_id, 'personel_id', v_uye.personel_id, 'yetkiler', dose_private.yetkiler(),
        'okul', jsonb_build_object('id', v_okul.id, 'ad', v_okul.ad, 'kurum_kodu', v_okul.kurum_kodu,
                                   'lisans_bitis', v_okul.lisans_bitis, 'salt_okunur', NOT public.dose_lisans_gecerli()));
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_son_degisiklik() RETURNS BIGINT
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT coalesce(max(l.id), 0) FROM public.islem_log l WHERE l.okul_id = public.dose_okul()
$$;

-- ------------------------------------------------------------------ user management (Okul Müdürü / Sistem Yöneticisi)
CREATE OR REPLACE FUNCTION public.dose_kullanicilar() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := dose_private.yonetici_kontrol();
BEGIN
    RETURN jsonb_build_object(
        'uyeler', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'id', u.auth_user_id, 'eposta', a.email, 'ad_soyad', u.ad_soyad, 'rol', u.rol,
                'bolum_id', u.bolum_id, 'personel_id', u.personel_id, 'aktif', u.aktif,
                'son_giris', a.last_sign_in_at, 'ben', u.auth_user_id = auth.uid()) ORDER BY u.aktif DESC, u.ad_soyad)
            FROM dose_private.uyelik u JOIN auth.users a ON a.id = u.auth_user_id WHERE u.okul_id = v_okul), '[]'::JSONB),
        'davetler', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'eposta', d.eposta, 'ad_soyad', d.ad_soyad, 'rol', d.rol, 'bolum_id', d.bolum_id,
                'personel_id', d.personel_id, 'bitis', d.bitis) ORDER BY d.olusturma DESC)
            FROM dose_private.davet d WHERE d.okul_id = v_okul AND d.bitis > now()), '[]'::JSONB));
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_kullanici_davet(p_eposta TEXT, p_ad_soyad TEXT, p_rol TEXT,
                                                       p_bolum_id INTEGER DEFAULT NULL, p_personel_id INTEGER DEFAULT NULL)
RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := dose_private.yonetici_kontrol();
    v_eposta TEXT := lower(btrim(coalesce(p_eposta, '')));
    v_ad TEXT := dose_private.ad_soyad_kontrol(p_ad_soyad);
BEGIN
    IF v_eposta !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' THEN
        PERFORM dose_private.hata('E-posta adresi geçersiz.');
    END IF;
    PERFORM dose_private.rol_baglami_dogrula(v_okul, p_rol, p_bolum_id, p_personel_id);
    IF EXISTS (SELECT 1 FROM dose_private.uyelik u JOIN auth.users a ON a.id = u.auth_user_id
               WHERE lower(a.email) = v_eposta) THEN
        PERFORM dose_private.hata('Bu e-posta adresi zaten bir okul kullanıcısı.');
    END IF;
    DELETE FROM dose_private.davet WHERE eposta = v_eposta AND bitis <= now();
    IF EXISTS (SELECT 1 FROM dose_private.davet WHERE eposta = v_eposta AND okul_id <> v_okul) THEN
        PERFORM dose_private.hata('Bu e-posta adresine başka bir okuldan bekleyen davet var.');
    END IF;
    INSERT INTO dose_private.davet (eposta, okul_id, rol, ad_soyad, bolum_id, personel_id, davet_eden)
    VALUES (v_eposta, v_okul, p_rol, v_ad, p_bolum_id, p_personel_id, auth.uid())
    ON CONFLICT (eposta) DO UPDATE SET rol = EXCLUDED.rol, ad_soyad = EXCLUDED.ad_soyad, bolum_id = EXCLUDED.bolum_id,
        personel_id = EXCLUDED.personel_id, davet_eden = EXCLUDED.davet_eden, olusturma = now(),
        bitis = now() + interval '30 days';
    PERFORM dose_private.log(v_okul, 'Kullanıcı davet edildi', 'davet', NULL, format('%s - %s (%s)', v_eposta, v_ad, p_rol));
    RETURN jsonb_build_object('basarili', true, 'eposta', v_eposta);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_davet_sil(p_eposta TEXT) RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := dose_private.yonetici_kontrol();
    v_eposta TEXT := lower(btrim(coalesce(p_eposta, '')));
BEGIN
    DELETE FROM dose_private.davet WHERE eposta = v_eposta AND okul_id = v_okul;
    IF NOT FOUND THEN
        PERFORM dose_private.hata('Davet bulunamadı.');
    END IF;
    PERFORM dose_private.log(v_okul, 'Davet iptal edildi', 'davet', NULL, v_eposta);
    RETURN jsonb_build_object('basarili', true);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_kullanici_guncelle(p_kullanici UUID, p_ad_soyad TEXT, p_rol TEXT,
                                                          p_bolum_id INTEGER, p_personel_id INTEGER, p_aktif BOOLEAN)
RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := dose_private.yonetici_kontrol();
    v_ad TEXT := dose_private.ad_soyad_kontrol(p_ad_soyad);
    v_eski dose_private.uyelik%ROWTYPE;
BEGIN
    -- Serialises concurrent role changes so the "last manager" guard cannot be bypassed.
    LOCK TABLE dose_private.uyelik IN SHARE ROW EXCLUSIVE MODE;
    SELECT * INTO v_eski FROM dose_private.uyelik WHERE auth_user_id = p_kullanici AND okul_id = v_okul;
    IF NOT FOUND THEN
        PERFORM dose_private.hata('Kullanıcı bulunamadı.');
    END IF;
    IF p_kullanici = auth.uid() AND (p_rol IS DISTINCT FROM v_eski.rol OR NOT coalesce(p_aktif, false)) THEN
        PERFORM dose_private.hata('Kendi rolünüzü değiştiremez veya kendinizi pasif yapamazsınız.');
    END IF;
    PERFORM dose_private.rol_baglami_dogrula(v_okul, p_rol, p_bolum_id, p_personel_id);
    UPDATE dose_private.uyelik SET ad_soyad = v_ad, rol = p_rol, bolum_id = p_bolum_id, personel_id = p_personel_id,
        aktif = coalesce(p_aktif, false)
    WHERE auth_user_id = p_kullanici;
    IF NOT EXISTS (SELECT 1 FROM dose_private.uyelik WHERE okul_id = v_okul AND aktif
                   AND rol IN ('Okul Müdürü', 'Sistem Yöneticisi')) THEN
        PERFORM dose_private.hata('Okulda en az bir aktif Okul Müdürü veya Sistem Yöneticisi kalmalıdır.');
    END IF;
    PERFORM dose_private.log(v_okul, 'Kullanıcı güncellendi', 'uyelik', NULL,
        format('%s: %s -> %s, %s', v_ad, v_eski.rol, p_rol, CASE WHEN coalesce(p_aktif, false) THEN 'aktif' ELSE 'pasif' END),
        to_jsonb(v_eski) - 'auth_user_id',
        jsonb_build_object('rol', p_rol, 'ad_soyad', v_ad, 'bolum_id', p_bolum_id, 'personel_id', p_personel_id,
                           'aktif', coalesce(p_aktif, false)));
    RETURN jsonb_build_object('basarili', true);
END;
$$;

-- ------------------------------------------------------------------ grants
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA dose_private FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC, anon;
GRANT USAGE ON SCHEMA dose_private TO service_role;
GRANT EXECUTE ON FUNCTION dose_private.okul_ac(TEXT, TEXT, DATE, INTERVAL) TO service_role;
GRANT EXECUTE ON FUNCTION dose_private.etkinlestirme_kodu(TEXT, INTERVAL) TO service_role;
GRANT EXECUTE ON FUNCTION dose_private.lisans_ayarla(TEXT, DATE, BOOLEAN) TO service_role;

GRANT EXECUTE ON FUNCTION public.dose_okul(), public.dose_rol(), public.dose_bolum(), public.dose_bolum_kisitli(),
    public.dose_lisans_gecerli(), public.dose_yetki(TEXT), public.dose_okul_etkinlestir(TEXT, TEXT, TEXT),
    public.dose_ben(), public.dose_son_degisiklik(), public.dose_kullanicilar(),
    public.dose_kullanici_davet(TEXT, TEXT, TEXT, INTEGER, INTEGER), public.dose_davet_sil(TEXT),
    public.dose_kullanici_guncelle(UUID, TEXT, TEXT, INTEGER, INTEGER, BOOLEAN) TO authenticated;

GRANT SELECT ON public.secenek TO authenticated;
GRANT SELECT ON public.islem_log TO authenticated;
GRANT SELECT ON public.kurum TO authenticated;
GRANT UPDATE (okul_adi, isletme_adi, il, ilce, adres, telefon, eposta, vergi_dairesi, vkn, banka, iban,
              harcama_yetkilisi, gerceklestirme_gorevlisi, sayman, buyuksehir, tahsis_sermaye, odenmis_sermaye,
              yuz_yuze_egitim, evrak_kodu, surum) ON public.kurum TO authenticated;

-- ------------------------------------------------------------------ policies
DROP POLICY IF EXISTS secenek_okuma ON public.secenek;
CREATE POLICY secenek_okuma ON public.secenek FOR SELECT TO authenticated
    USING ((SELECT public.dose_okul()) IS NOT NULL);

DROP POLICY IF EXISTS islem_log_okuma ON public.islem_log;
CREATE POLICY islem_log_okuma ON public.islem_log FOR SELECT TO authenticated
    USING (okul_id = (SELECT public.dose_okul()) AND (SELECT public.dose_yetki('islem_kaydi')) <> '');

DROP POLICY IF EXISTS kurum_okuma ON public.kurum;
CREATE POLICY kurum_okuma ON public.kurum FOR SELECT TO authenticated
    USING (okul_id = (SELECT public.dose_okul()) AND (SELECT public.dose_yetki('kurum')) <> '');
DROP POLICY IF EXISTS kurum_guncelleme ON public.kurum;
CREATE POLICY kurum_guncelleme ON public.kurum FOR UPDATE TO authenticated
    USING (okul_id = (SELECT public.dose_okul()) AND (SELECT public.dose_yetki('kurum')) = 'y')
    WITH CHECK (okul_id = (SELECT public.dose_okul()) AND (SELECT public.dose_yetki('kurum')) = 'y');

DO $$
DECLARE
    t TEXT;
    v_bolum TEXT;
    v_oku TEXT;
    v_yaz TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['bolum', 'personel', 'ogrenci', 'cari', 'malzeme', 'urun'] LOOP
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO authenticated', t);
        EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE public.%I TO authenticated', t || '_id_seq');
        -- Alan şefi and öğretmen only see their own workshop on tables that carry bolum_id.
        v_bolum := CASE WHEN t IN ('personel', 'ogrenci', 'urun')
                        THEN ' AND (NOT (SELECT public.dose_bolum_kisitli()) OR bolum_id = (SELECT public.dose_bolum()))'
                        ELSE '' END;
        v_oku := format('okul_id = (SELECT public.dose_okul()) AND (SELECT public.dose_yetki(%L)) <> %L', t, '') || v_bolum;
        v_yaz := format('okul_id = (SELECT public.dose_okul()) AND (SELECT public.dose_yetki(%L)) = %L', t, 'y') || v_bolum;
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || '_okuma', t);
        EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (%s)', t || '_okuma', t, v_oku);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || '_ekleme', t);
        EXECUTE format('CREATE POLICY %I ON public.%I FOR INSERT TO authenticated WITH CHECK (%s)', t || '_ekleme', t, v_yaz);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || '_guncelleme', t);
        EXECUTE format('CREATE POLICY %I ON public.%I FOR UPDATE TO authenticated USING (%s) WITH CHECK (%s)',
                       t || '_guncelleme', t, v_yaz, v_yaz);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || '_silme', t);
        EXECUTE format('CREATE POLICY %I ON public.%I FOR DELETE TO authenticated USING (%s)', t || '_silme', t, v_yaz);
    END LOOP;
END;
$$;
