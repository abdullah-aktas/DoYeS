-- Uygulama sürümü ve tüm kullanıcılara görünen güncelleme duyurusu.

CREATE TABLE IF NOT EXISTS dose_private.uygulama (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    surum TEXT NOT NULL CHECK (surum ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
    min_surum TEXT NOT NULL DEFAULT '1.0.0' CHECK (min_surum ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
    duyuru TEXT NOT NULL DEFAULT '',
    duyuru_bitis TIMESTAMPTZ,
    indir_url TEXT,
    windows_url TEXT,
    web_url TEXT,
    android_url TEXT,
    guncelleme TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE dose_private.uygulama ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON dose_private.uygulama FROM PUBLIC, anon, authenticated;

INSERT INTO dose_private.uygulama (
    id, surum, min_surum, duyuru, duyuru_bitis, indir_url, windows_url, web_url, android_url)
VALUES (
    1, '1.8.0', '1.7.0',
    'Yeni sürüm 1.8.0: Okul Müdürü / Sistem Yöneticisi tüm işlemlere yazabilir; '
    'Kullanıcılar ekranından sayfa yetkisi verilebilir; Ana ekranda özet kartları ve grafikler vardır. '
    'Masaüstü, web veya Android paketini güncelleyin.',
    now() + interval '45 days',
    'https://github.com/abdullah-aktas/DoYeS/releases/tag/v1.8.0',
    'https://github.com/abdullah-aktas/DoYeS/releases/tag/v1.8.0',
    'https://github.com/abdullah-aktas/DoYeS/releases/tag/v1.8.0',
    'https://github.com/abdullah-aktas/DoYeS/releases/tag/v1.8.0'
)
ON CONFLICT (id) DO UPDATE SET
    surum = EXCLUDED.surum,
    min_surum = EXCLUDED.min_surum,
    duyuru = EXCLUDED.duyuru,
    duyuru_bitis = EXCLUDED.duyuru_bitis,
    indir_url = EXCLUDED.indir_url,
    windows_url = EXCLUDED.windows_url,
    web_url = EXCLUDED.web_url,
    android_url = EXCLUDED.android_url,
    guncelleme = now();

CREATE OR REPLACE FUNCTION dose_private.uygulama_bilgi() RETURNS JSONB
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT coalesce((
        SELECT jsonb_build_object(
            'surum', u.surum,
            'min_surum', u.min_surum,
            'duyuru', CASE
                WHEN nullif(btrim(u.duyuru), '') IS NOT NULL
                     AND (u.duyuru_bitis IS NULL OR u.duyuru_bitis > now())
                THEN u.duyuru ELSE '' END,
            'aktif', nullif(btrim(u.duyuru), '') IS NOT NULL
                     AND (u.duyuru_bitis IS NULL OR u.duyuru_bitis > now()),
            'indir_url', u.indir_url,
            'windows_url', u.windows_url,
            'web_url', u.web_url,
            'android_url', u.android_url)
        FROM dose_private.uygulama u WHERE u.id = 1
    ), jsonb_build_object('surum', '0.0.0', 'min_surum', '0.0.0', 'duyuru', '', 'aktif', false))
$$;

CREATE OR REPLACE FUNCTION public.dose_uygulama_bilgi() RETURNS JSONB
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT dose_private.uygulama_bilgi()
$$;

-- dose_ben yanıtına uygulama bloğu ekle (mevcut sarmalayıcıyı koru).
CREATE OR REPLACE FUNCTION public.dose_ben() RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_ben JSONB := public.dose_ben_okul_baglam();
    v_ad TEXT;
    v_okul dose_private.okul%ROWTYPE;
    v_uyg JSONB := dose_private.uygulama_bilgi();
BEGIN
    IF jsonb_typeof(v_ben->'okul') = 'object' THEN
        SELECT * INTO v_okul FROM dose_private.okul WHERE id = (v_ben->'okul'->>'id')::INTEGER;
        v_ben := jsonb_set(v_ben, '{okul}', (v_ben->'okul') || jsonb_build_object(
            'deneme', v_okul.deneme,
            'kalan_gun', CASE WHEN v_okul.lisans_bitis IS NULL THEN NULL
                              ELSE greatest(v_okul.lisans_bitis - (now() AT TIME ZONE 'Europe/Istanbul')::DATE + 1, 0) END));
    END IF;
    IF NOT dose_private.mevzuat_merkez_yetkili() THEN
        RETURN v_ben || jsonb_build_object('uygulama', v_uyg);
    END IF;
    SELECT ad_soyad INTO v_ad FROM dose_private.mevzuat_yoneticisi WHERE auth_user_id = auth.uid();
    IF v_ben->>'uye' = 'true' THEN
        RETURN v_ben || jsonb_build_object(
            'merkez_mevzuat', true,
            'yetkiler', coalesce(v_ben->'yetkiler', '{}'::JSONB) || jsonb_build_object('merkez_mevzuat', 'y'),
            'uygulama', v_uyg);
    END IF;
    RETURN jsonb_build_object(
        'uye', true, 'merkez_mevzuat', true, 'rol', 'Merkez Mevzuat Yöneticisi',
        'ad_soyad', v_ad, 'eposta', v_ben->>'eposta',
        'yetkiler', jsonb_build_object('merkez_mevzuat', 'y'), 'okul', NULL,
        'uygulama', v_uyg);
END;
$$;

-- Eski istemcilerde «Bugün ne yapmalıyım?» listesine güncelleme satırı düşer.
CREATE OR REPLACE FUNCTION public.dose_gorevlerim() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_rol TEXT := public.dose_rol();
    v_bolum INTEGER := public.dose_bolum();
    v_liste JSONB := '[]'::JSONB;
    v_yil INTEGER := extract(year FROM now() AT TIME ZONE 'Europe/Istanbul')::INTEGER;
    v_ay INTEGER := extract(month FROM now() AT TIME ZONE 'Europe/Istanbul')::INTEGER;
    v_uyg JSONB := dose_private.uygulama_bilgi();
BEGIN
    IF v_okul IS NULL OR auth.uid() IS NULL THEN
        RETURN jsonb_build_object('gorevler', '[]'::JSONB);
    END IF;

    IF coalesce((v_uyg->>'aktif')::BOOLEAN, false) THEN
        v_liste := v_liste || jsonb_build_array(jsonb_build_object(
            'tur', 'guncelleme', 'sayfa', 'ana',
            'baslik', format('DÖSE %s güncellemesi', v_uyg->>'surum'),
            'ozet', left(coalesce(v_uyg->>'duyuru', 'Yeni sürüm hazır; uygulamayı güncelleyin.'), 220),
            'id', 0));
    END IF;

    IF v_rol IN ('Alan Şefi', 'Teknik Müdür Yardımcısı', 'Okul Müdürü') THEN
        v_liste := v_liste || coalesce((SELECT jsonb_agg(jsonb_build_object(
            'tur', 'siparis', 'sayfa', 'siparis', 'baslik', s.siparis_no || ' · ' || coalesce(s.konu, ''),
            'ozet', 'Sipariş onayı bekliyor', 'id', s.id)
            ORDER BY s.id)
            FROM public.siparis s
            JOIN public.onay_durum o ON o.okul_id = s.okul_id AND o.belge_turu = 'Sipariş' AND o.belge_id = s.id
            WHERE s.okul_id = v_okul AND o.durum = 'Onay Bekliyor'
              AND ((v_rol = 'Alan Şefi' AND o.asama = 1)
                OR (v_rol = 'Teknik Müdür Yardımcısı' AND o.asama = 2)
                OR (v_rol = 'Okul Müdürü' AND o.asama = 3))
              AND (NOT public.dose_bolum_kisitli() OR s.bolum_id IS NOT DISTINCT FROM v_bolum
                   OR v_rol <> 'Alan Şefi')), '[]'::JSONB);
    END IF;

    IF v_rol IN ('Alan Şefi', 'Teknik Müdür Yardımcısı', 'Öğretmen') THEN
        v_liste := v_liste || coalesce((SELECT jsonb_agg(jsonb_build_object(
            'tur', 'parca_basi', 'sayfa', 'parca_basi', 'baslik', h.hakedis_no,
            'ozet', 'Parça başı taslağı tamamlanacak', 'id', h.id) ORDER BY h.id)
            FROM dose_private.pb_hakedis h
            JOIN public.siparis s ON s.okul_id = h.okul_id AND s.id = h.siparis_id
            WHERE h.okul_id = v_okul AND h.durum = 'Taslak'
              AND dose_private.pb_hazirlayabilir(v_okul, h.siparis_id)), '[]'::JSONB);
        v_liste := v_liste || coalesce((SELECT jsonb_agg(jsonb_build_object(
            'tur', 'fazla_calisma', 'sayfa', 'fazla_calisma', 'baslik', b.bordro_no,
            'ozet', 'Fazla çalışma taslağı tamamlanacak', 'id', b.id) ORDER BY b.id)
            FROM dose_private.fc_bordro b
            JOIN public.siparis s ON s.okul_id = b.okul_id AND s.id = b.siparis_id
            WHERE b.okul_id = v_okul AND b.durum = 'Taslak'
              AND dose_private.fc_hazirlayabilir(v_okul, b.siparis_id)), '[]'::JSONB);
    END IF;

    IF v_rol = 'Teknik Müdür Yardımcısı' THEN
        v_liste := v_liste || coalesce((SELECT jsonb_agg(jsonb_build_object(
            'tur', 'parca_basi', 'sayfa', 'parca_basi', 'baslik', h.hakedis_no,
            'ozet', 'Parça başı TMY onayı', 'id', h.id) ORDER BY h.id)
            FROM dose_private.pb_hakedis h WHERE h.okul_id = v_okul AND h.durum = 'TMY Onayında'), '[]'::JSONB);
        v_liste := v_liste || coalesce((SELECT jsonb_agg(jsonb_build_object(
            'tur', 'fazla_calisma', 'sayfa', 'fazla_calisma', 'baslik', b.bordro_no,
            'ozet', 'Fazla çalışma TMY onayı', 'id', b.id) ORDER BY b.id)
            FROM dose_private.fc_bordro b WHERE b.okul_id = v_okul AND b.durum = 'TMY Onayında'), '[]'::JSONB);
    END IF;

    IF v_rol = 'Okul Müdürü' THEN
        v_liste := v_liste || coalesce((SELECT jsonb_agg(jsonb_build_object(
            'tur', 'parca_basi', 'sayfa', 'parca_basi', 'baslik', h.hakedis_no,
            'ozet', 'Parça başı müdür onayı', 'id', h.id) ORDER BY h.id)
            FROM dose_private.pb_hakedis h WHERE h.okul_id = v_okul AND h.durum = 'Müdür Onayında'), '[]'::JSONB);
        v_liste := v_liste || coalesce((SELECT jsonb_agg(jsonb_build_object(
            'tur', 'fazla_calisma', 'sayfa', 'fazla_calisma', 'baslik', b.bordro_no,
            'ozet', 'Fazla çalışma müdür onayı', 'id', b.id) ORDER BY b.id)
            FROM dose_private.fc_bordro b WHERE b.okul_id = v_okul AND b.durum = 'Müdür Onayında'), '[]'::JSONB);
        v_liste := v_liste || coalesce((SELECT jsonb_agg(jsonb_build_object(
            'tur', 'yil_sonu', 'sayfa', 'yil_sonu', 'baslik', d.belge_no,
            'ozet', 'Yıl sonu kâr dağıtımı onayı', 'id', d.id) ORDER BY d.id)
            FROM dose_private.ys_donem d WHERE d.okul_id = v_okul AND d.durum = 'Müdür Onayında'), '[]'::JSONB);
    END IF;

    IF v_rol = 'Sayman' THEN
        v_liste := v_liste || coalesce((SELECT jsonb_agg(jsonb_build_object(
            'tur', 'mevzuat', 'sayfa', 'mevzuat', 'baslik', 'Parametre doğrulama',
            'ozet', 'Doğrulanmamış merkez yayını var — PB/FC ve peşinat buna bağlı', 'id', m.id) ORDER BY m.id)
            FROM dose_private.mevzuat_yayin m
            WHERE extract(year FROM m.baslangic) = v_yil
              AND NOT EXISTS (
                  SELECT 1 FROM dose_private.mevzuat_yayin n
                  WHERE n.baslangic = m.baslangic AND n.id > m.id)
              AND NOT EXISTS (
                  SELECT 1 FROM dose_private.mevzuat_onay o
                  WHERE o.yayin_id = m.id AND o.okul_id = v_okul AND o.karar IS TRUE
                    AND NOT EXISTS (SELECT 1 FROM dose_private.mevzuat_onay x
                                   WHERE x.yayin_id = m.id AND x.okul_id = v_okul AND x.id > o.id))), '[]'::JSONB);

        v_liste := v_liste || coalesce((SELECT jsonb_agg(jsonb_build_object(
            'tur', 'parca_basi', 'sayfa', 'parca_basi', 'baslik', h.hakedis_no,
            'ozet', 'Onaylı parça başı ödemesi bekliyor', 'id', h.id) ORDER BY h.id)
            FROM dose_private.pb_hakedis h
            WHERE h.okul_id = v_okul AND h.durum = 'Onaylandı'
              AND dose_private.pb_odeme(v_okul, h.id) IS NULL), '[]'::JSONB);

        v_liste := v_liste || coalesce((SELECT jsonb_agg(jsonb_build_object(
            'tur', 'fazla_calisma', 'sayfa', 'fazla_calisma', 'baslik', b.bordro_no,
            'ozet', 'Onaylı fazla çalışma ödemesi bekliyor', 'id', b.id) ORDER BY b.id)
            FROM dose_private.fc_bordro b
            WHERE b.okul_id = v_okul AND b.durum = 'Onaylandı'
              AND dose_private.fc_odeme(v_okul, b.id) IS NULL), '[]'::JSONB);

        IF dose_private.hp_hasilat(v_okul, v_yil, v_ay) > 0
           AND NOT EXISTS (
               SELECT 1 FROM dose_private.hp_donem d
               WHERE d.okul_id = v_okul AND d.yil = v_yil AND d.ay = v_ay AND d.durum <> 'İptal'
                 AND (SELECT coalesce(sum(k.tutar), 0) FROM public.kasa_banka k
                      WHERE k.okul_id = v_okul AND k.hp_donem_id = d.id AND k.ters_hareket_id IS NULL
                        AND NOT EXISTS (SELECT 1 FROM public.kasa_banka t
                                       WHERE t.okul_id = k.okul_id AND t.ters_hareket_id = k.id)) >= d.tutar)
        THEN
            v_liste := v_liste || jsonb_build_array(jsonb_build_object(
                'tur', 'hazine_payi', 'sayfa', 'hazine_payi',
                'baslik', format('Hazine payı %s/%s', lpad(v_ay::TEXT, 2, '0'), v_yil),
                'ozet', 'Bildirim veya ödeme tamamlanacak', 'id', v_ay));
        END IF;

        v_liste := v_liste || coalesce((SELECT jsonb_agg(jsonb_build_object(
            'tur', 'yil_sonu', 'sayfa', 'yil_sonu', 'baslik', d.belge_no,
            'ozet', 'Yıl sonu taslağı / ödeme', 'id', d.id) ORDER BY d.id)
            FROM dose_private.ys_donem d
            WHERE d.okul_id = v_okul AND d.durum IN ('Taslak', 'Onaylandı')), '[]'::JSONB);
    END IF;

    RETURN jsonb_build_object('gorevler', coalesce(v_liste, '[]'::JSONB));
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.uygulama_ayarla(
    p_surum TEXT, p_duyuru TEXT, p_gun INTEGER DEFAULT 45,
    p_indir_url TEXT DEFAULT NULL, p_min_surum TEXT DEFAULT NULL)
RETURNS JSONB
LANGUAGE plpgsql VOLATILE SET search_path = '' AS $$
BEGIN
    IF p_surum !~ '^[0-9]+\.[0-9]+\.[0-9]+$' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Sürüm 1.2.3 biçiminde olmalıdır.';
    END IF;
    INSERT INTO dose_private.uygulama (id, surum, min_surum, duyuru, duyuru_bitis, indir_url,
                                       windows_url, web_url, android_url)
    VALUES (1, p_surum, coalesce(nullif(p_min_surum, ''), '1.0.0'), coalesce(p_duyuru, ''),
            CASE WHEN coalesce(p_gun, 0) > 0 THEN now() + make_interval(days => p_gun) ELSE NULL END,
            p_indir_url, p_indir_url, p_indir_url, p_indir_url)
    ON CONFLICT (id) DO UPDATE SET
        surum = EXCLUDED.surum,
        min_surum = EXCLUDED.min_surum,
        duyuru = EXCLUDED.duyuru,
        duyuru_bitis = EXCLUDED.duyuru_bitis,
        indir_url = coalesce(EXCLUDED.indir_url, dose_private.uygulama.indir_url),
        windows_url = coalesce(EXCLUDED.windows_url, dose_private.uygulama.windows_url),
        web_url = coalesce(EXCLUDED.web_url, dose_private.uygulama.web_url),
        android_url = coalesce(EXCLUDED.android_url, dose_private.uygulama.android_url),
        guncelleme = now();
    RETURN dose_private.uygulama_bilgi();
END;
$$;

REVOKE ALL ON FUNCTION public.dose_uygulama_bilgi() FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.dose_ben() FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.dose_gorevlerim() FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION dose_private.uygulama_ayarla(TEXT, TEXT, INTEGER, TEXT, TEXT) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.dose_uygulama_bilgi() TO authenticated;
GRANT EXECUTE ON FUNCTION public.dose_ben() TO authenticated;
GRANT EXECUTE ON FUNCTION public.dose_gorevlerim() TO authenticated;
GRANT EXECUTE ON FUNCTION dose_private.uygulama_ayarla(TEXT, TEXT, INTEGER, TEXT, TEXT) TO service_role;
