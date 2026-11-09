-- Okul Müdürü / Sistem Yöneticisi: tüm okul sayfalarında yazma + kullanıcıya özel yetki.
-- Ana ekran özeti (grafik / KPI) için dose_ana_ozet.

ALTER TABLE dose_private.uyelik
    ADD COLUMN IF NOT EXISTS yetki_ozel JSONB NOT NULL DEFAULT '{}'::JSONB
    CONSTRAINT uyelik_yetki_ozel_obj CHECK (jsonb_typeof(yetki_ozel) = 'object');

COMMENT ON COLUMN dose_private.uyelik.yetki_ozel IS
    'Sayfa → y|g|- override. Anahtar yoksa rol matrisi (sayfa_yetki) kullanılır.';

-- Sistem (1) ve Okul Müdürü (2) her sayfada yazma.
UPDATE dose_private.sayfa_yetki
SET kodlar = 'yy' || substr(kodlar, 3)
WHERE length(kodlar) = 8 AND substr(kodlar, 1, 2) IS DISTINCT FROM 'yy';

CREATE OR REPLACE FUNCTION dose_private.yetki_ozel_dogrula(p JSONB) RETURNS JSONB
LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE
    v_key TEXT;
    v_val TEXT;
    v_out JSONB := '{}'::JSONB;
BEGIN
    IF p IS NULL OR p = 'null'::JSONB THEN
        RETURN '{}'::JSONB;
    END IF;
    IF jsonb_typeof(p) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Yetki listesi geçersiz.';
    END IF;
    FOR v_key, v_val IN SELECT key, value #>> '{}' FROM jsonb_each(p)
    LOOP
        IF v_key IS NULL OR v_key = '' THEN
            CONTINUE;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM dose_private.sayfa_yetki s WHERE s.sayfa = v_key) THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = format('Bilinmeyen sayfa yetkisi: %s', v_key);
        END IF;
        IF v_val IS NULL OR v_val NOT IN ('y', 'g', '-') THEN
            RAISE EXCEPTION USING ERRCODE = '22023',
                MESSAGE = format('Yetki değeri y, g veya - olmalıdır (%s).', v_key);
        END IF;
        IF v_val = '-' THEN
            v_out := v_out || jsonb_build_object(v_key, '-');
        ELSE
            v_out := v_out || jsonb_build_object(v_key, v_val);
        END IF;
    END LOOP;
    RETURN v_out;
END;
$$;

-- Rol matrisi + üye override. '-' override erişimi kapatır.
CREATE OR REPLACE FUNCTION public.dose_yetki(p_sayfa TEXT) RETURNS TEXT
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT CASE
        WHEN y.c = 'y' AND NOT public.dose_lisans_gecerli() THEN 'g'
        ELSE coalesce(y.c, '')
    END
    FROM (
        SELECT CASE
            WHEN u.yetki_ozel ? p_sayfa THEN
                CASE u.yetki_ozel ->> p_sayfa
                    WHEN 'y' THEN 'y'
                    WHEN 'g' THEN 'g'
                    ELSE ''
                END
            ELSE (
                SELECT nullif(substr(s.kodlar, array_position(ARRAY[
                    'Sistem Yöneticisi', 'Okul Müdürü', 'Teknik Müdür Yardımcısı', 'Sayman',
                    'Alan Şefi', 'Öğretmen', 'Memur / Veri Girişi', 'İzleyici / Denetçi'],
                    u.rol), 1), '-')
                FROM dose_private.sayfa_yetki s WHERE s.sayfa = p_sayfa
            )
        END AS c
        FROM dose_private.uyelik u
        WHERE u.auth_user_id = auth.uid() AND u.aktif
        LIMIT 1
    ) AS y
$$;

CREATE OR REPLACE FUNCTION public.dose_sayfa_yetki_listesi() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := dose_private.yonetici_kontrol();
BEGIN
    RETURN jsonb_build_object(
        'sayfalar', coalesce((
            SELECT jsonb_agg(jsonb_build_object('sayfa', s.sayfa, 'baslik', s.baslik)
                             ORDER BY s.baslik)
            FROM dose_private.sayfa_yetki s
        ), '[]'::JSONB),
        'okul_id', v_okul);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_kullanicilar() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := dose_private.yonetici_kontrol();
BEGIN
    RETURN jsonb_build_object(
        'uyeler', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'id', u.auth_user_id, 'eposta', a.email, 'ad_soyad', u.ad_soyad, 'rol', u.rol,
                'bolum_id', u.bolum_id, 'personel_id', u.personel_id, 'aktif', u.aktif,
                'yetki_ozel', coalesce(u.yetki_ozel, '{}'::JSONB),
                'son_giris', a.last_sign_in_at, 'ben', u.auth_user_id = auth.uid())
            ORDER BY u.aktif DESC, u.ad_soyad)
            FROM dose_private.uyelik u JOIN auth.users a ON a.id = u.auth_user_id
            WHERE u.okul_id = v_okul), '[]'::JSONB),
        'davetler', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'eposta', d.eposta, 'ad_soyad', d.ad_soyad, 'rol', d.rol, 'bolum_id', d.bolum_id,
                'personel_id', d.personel_id, 'bitis', d.bitis) ORDER BY d.olusturma DESC)
            FROM dose_private.davet d WHERE d.okul_id = v_okul AND d.bitis > now()), '[]'::JSONB),
        'sayfalar', coalesce((
            SELECT jsonb_agg(jsonb_build_object('sayfa', s.sayfa, 'baslik', s.baslik)
                             ORDER BY s.baslik)
            FROM dose_private.sayfa_yetki s
        ), '[]'::JSONB));
END;
$$;

DROP FUNCTION IF EXISTS public.dose_kullanici_guncelle(UUID, TEXT, TEXT, INTEGER, INTEGER, BOOLEAN);

CREATE OR REPLACE FUNCTION public.dose_kullanici_guncelle(
    p_kullanici UUID, p_ad_soyad TEXT, p_rol TEXT,
    p_bolum_id INTEGER, p_personel_id INTEGER, p_aktif BOOLEAN,
    p_yetki_ozel JSONB DEFAULT NULL)
RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := dose_private.yonetici_kontrol();
    v_ad TEXT := dose_private.ad_soyad_kontrol(p_ad_soyad);
    v_eski dose_private.uyelik%ROWTYPE;
    v_ozel JSONB;
BEGIN
    LOCK TABLE dose_private.uyelik IN SHARE ROW EXCLUSIVE MODE;
    SELECT * INTO v_eski FROM dose_private.uyelik WHERE auth_user_id = p_kullanici AND okul_id = v_okul;
    IF NOT FOUND THEN
        PERFORM dose_private.hata('Kullanıcı bulunamadı.');
    END IF;
    IF p_kullanici = auth.uid() AND (p_rol IS DISTINCT FROM v_eski.rol OR NOT coalesce(p_aktif, false)) THEN
        PERFORM dose_private.hata('Kendi rolünüzü değiştiremez veya kendinizi pasif yapamazsınız.');
    END IF;
    PERFORM dose_private.rol_baglami_dogrula(v_okul, p_rol, p_bolum_id, p_personel_id);

    IF p_yetki_ozel IS NULL THEN
        v_ozel := v_eski.yetki_ozel;
    ELSIF p_kullanici = auth.uid() THEN
        -- Kendi özel yetkisini değiştirmeyi engelle (kendini kilitlemesin).
        v_ozel := v_eski.yetki_ozel;
    ELSE
        v_ozel := dose_private.yetki_ozel_dogrula(p_yetki_ozel);
    END IF;

    -- Tam yönetici rollerinde özel yetki gerekmez; temiz tut.
    IF p_rol IN ('Okul Müdürü', 'Sistem Yöneticisi') THEN
        v_ozel := '{}'::JSONB;
    END IF;

    UPDATE dose_private.uyelik SET ad_soyad = v_ad, rol = p_rol, bolum_id = p_bolum_id,
        personel_id = p_personel_id, aktif = coalesce(p_aktif, false), yetki_ozel = v_ozel
    WHERE auth_user_id = p_kullanici;

    IF NOT EXISTS (SELECT 1 FROM dose_private.uyelik WHERE okul_id = v_okul AND aktif
                   AND rol IN ('Okul Müdürü', 'Sistem Yöneticisi')) THEN
        PERFORM dose_private.hata('Okulda en az bir aktif Okul Müdürü veya Sistem Yöneticisi kalmalıdır.');
    END IF;

    PERFORM dose_private.log(v_okul, 'Kullanıcı güncellendi', 'uyelik', NULL,
        format('%s: %s -> %s, %s', v_ad, v_eski.rol, p_rol,
               CASE WHEN coalesce(p_aktif, false) THEN 'aktif' ELSE 'pasif' END),
        to_jsonb(v_eski) - 'auth_user_id',
        jsonb_build_object('rol', p_rol, 'ad_soyad', v_ad, 'bolum_id', p_bolum_id,
                           'personel_id', p_personel_id, 'aktif', coalesce(p_aktif, false),
                           'yetki_ozel', v_ozel));
    RETURN jsonb_build_object('basarili', true);
END;
$$;

-- Ana ekran KPI / grafik; finans alanları yetkiye bağlı.
CREATE OR REPLACE FUNCTION public.dose_ana_ozet(p_yil INTEGER DEFAULT NULL) RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_yil INTEGER := coalesce(p_yil, extract(year FROM now() AT TIME ZONE 'Europe/Istanbul')::INTEGER);
    v_finans BOOLEAN := public.dose_yetki('yevmiye') <> '' OR public.dose_yetki('fatura') <> ''
                        OR public.dose_yetki('kasa') <> '';
    v_siparis BOOLEAN := public.dose_yetki('siparis') <> '';
BEGIN
    IF v_okul IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Okul üyeliği yok.';
    END IF;
    RETURN jsonb_build_object(
        'yil', v_yil,
        'finans_gorunur', v_finans,
        'siparis_gorunur', v_siparis,
        'siparis', CASE WHEN v_siparis THEN
            (SELECT count(*) FROM public.siparis WHERE okul_id = v_okul
             AND extract(year FROM tarih::DATE) = v_yil) ELSE 0 END,
        'siparis_durum', CASE WHEN v_siparis THEN coalesce((
            SELECT jsonb_object_agg(d.durum, d.adet) FROM (
                SELECT durum, count(*)::INTEGER AS adet FROM public.siparis
                WHERE okul_id = v_okul AND extract(year FROM tarih::DATE) = v_yil
                GROUP BY durum) d), '{}'::JSONB) ELSE '{}'::JSONB END,
        'fatura_satis', CASE WHEN v_finans THEN coalesce((
            SELECT sum(net_tutar) FROM public.fatura
            WHERE okul_id = v_okul AND tur = 'Satış'
              AND extract(year FROM tarih::DATE) = v_yil), 0)::TEXT ELSE NULL END,
        'fatura_alis', CASE WHEN v_finans THEN coalesce((
            SELECT sum(net_tutar) FROM public.fatura
            WHERE okul_id = v_okul AND tur = 'Alış'
              AND extract(year FROM tarih::DATE) = v_yil), 0)::TEXT ELSE NULL END,
        'kasa_bakiye', CASE WHEN v_finans THEN dose_private.kasa_bakiye(v_okul, 'Kasa (100)')::TEXT ELSE NULL END,
        'banka_bakiye', CASE WHEN v_finans THEN dose_private.kasa_bakiye(v_okul, 'Banka (102)')::TEXT ELSE NULL END,
        'hp_hasilat', CASE WHEN v_finans AND public.dose_yetki('hazine_payi') <> '' THEN
            dose_private.hp_hasilat(v_okul, v_yil,
                extract(month FROM now() AT TIME ZONE 'Europe/Istanbul')::INTEGER)::TEXT
            ELSE NULL END);
END;
$$;

REVOKE ALL ON FUNCTION public.dose_yetki(TEXT) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.dose_sayfa_yetki_listesi() FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.dose_kullanicilar() FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.dose_kullanici_guncelle(UUID, TEXT, TEXT, INTEGER, INTEGER, BOOLEAN, JSONB)
    FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.dose_ana_ozet(INTEGER) FROM PUBLIC, anon;

GRANT EXECUTE ON FUNCTION public.dose_yetki(TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.dose_sayfa_yetki_listesi() TO authenticated;
GRANT EXECUTE ON FUNCTION public.dose_kullanicilar() TO authenticated;
GRANT EXECUTE ON FUNCTION public.dose_kullanici_guncelle(UUID, TEXT, TEXT, INTEGER, INTEGER, BOOLEAN, JSONB)
    TO authenticated;
GRANT EXECUTE ON FUNCTION public.dose_ana_ozet(INTEGER) TO authenticated;
