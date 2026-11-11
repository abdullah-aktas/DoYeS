-- Denetim formuna rehber kontrol listesi (JSONB) + yazma yetkisi sıkılaştırma.

ALTER TABLE dose_private.denetim_form
    ADD COLUMN IF NOT EXISTS kontrol_listesi JSONB NOT NULL DEFAULT '[]'::JSONB;

CREATE OR REPLACE FUNCTION public.dose_denetim_veri() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul();
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('islem_kaydi') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Denetim formu ekranına erişim yetkiniz yok.';
    END IF;
    RETURN jsonb_build_object(
        'formlar', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', d.id, 'form_no', d.form_no, 'tarih', d.tarih, 'denetci', d.denetci, 'kapsam', d.kapsam,
            'bulgular', d.bulgular, 'sonuc', d.sonuc, 'surum', d.surum,
            'kontrol_listesi', coalesce(d.kontrol_listesi, '[]'::JSONB)) ORDER BY d.id DESC)
            FROM dose_private.denetim_form d WHERE d.okul_id = v_okul), '[]'::JSONB),
        -- Okuma: islem_kaydi erişimi. Yazma: yalnız müdür / sistem / sayman / izleyici-denetçi.
        'yazabilir', public.dose_yetki('islem_kaydi') = 'y' OR (
            public.dose_yetki('islem_kaydi') = 'g' AND public.dose_rol() = 'İzleyici / Denetçi'));
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_denetim_kaydet(p_id INTEGER, p_surum INTEGER, p_veri JSONB, p_istek UUID)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); v_id INTEGER; v_no TEXT; v_tarih DATE;
    v_denetci TEXT; v_kapsam TEXT; v_bulgular TEXT; v_sonuc TEXT; v_liste JSONB;
    v_yaz BOOLEAN;
BEGIN
    v_yaz := public.dose_yetki('islem_kaydi') = 'y' OR (
        public.dose_yetki('islem_kaydi') = 'g' AND public.dose_rol() = 'İzleyici / Denetçi');
    IF v_okul IS NULL OR auth.uid() IS NULL OR NOT v_yaz OR public.dose_rol() NOT IN
       ('İzleyici / Denetçi', 'Okul Müdürü', 'Sistem Yöneticisi', 'Sayman') THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Denetim formu yazma yetkiniz yok.';
    END IF;
    v_tarih := (p_veri->>'tarih')::DATE;
    v_denetci := nullif(btrim(p_veri->>'denetci'), '');
    v_kapsam := nullif(btrim(p_veri->>'kapsam'), '');
    v_bulgular := nullif(btrim(p_veri->>'bulgular'), '');
    v_sonuc := nullif(btrim(p_veri->>'sonuc'), '');
    v_liste := coalesce(p_veri->'kontrol_listesi', '[]'::JSONB);
    IF jsonb_typeof(v_liste) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Kontrol listesi geçersiz.';
    END IF;
    IF v_tarih IS NULL OR v_denetci IS NULL OR v_kapsam IS NULL OR v_bulgular IS NULL OR v_sonuc IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Denetim formu alanları eksik.';
    END IF;
    IF p_id IS NULL THEN
        v_no := format('DN-%s-%s', extract(year FROM v_tarih)::INTEGER,
            lpad(dose_private.sira_no(v_okul, 'denetim', extract(year FROM v_tarih)::INTEGER)::TEXT, 4, '0'));
        INSERT INTO dose_private.denetim_form
            (okul_id, form_no, tarih, denetci, kapsam, bulgular, sonuc, kontrol_listesi, olusturan, istek_id)
        VALUES (v_okul, v_no, v_tarih, v_denetci, v_kapsam, v_bulgular, v_sonuc, v_liste, auth.uid(), p_istek)
        RETURNING id INTO v_id;
    ELSE
        UPDATE dose_private.denetim_form SET tarih = v_tarih, denetci = v_denetci, kapsam = v_kapsam,
            bulgular = v_bulgular, sonuc = v_sonuc, kontrol_listesi = v_liste, surum = surum + 1
        WHERE okul_id = v_okul AND id = p_id AND surum = p_surum RETURNING id INTO v_id;
        IF v_id IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Form bulunamadı veya başkası değiştirdi.',
                HINT = 'surum_cakismasi';
        END IF;
    END IF;
    PERFORM dose_private.log(v_okul, 'Denetim formu kaydedildi', 'denetim_form', v_id, v_kapsam);
    RETURN public.dose_denetim_veri();
END;
$$;

REVOKE ALL ON FUNCTION public.dose_denetim_veri(), public.dose_denetim_kaydet(INTEGER, INTEGER, JSONB, UUID)
    FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_denetim_veri(), public.dose_denetim_kaydet(INTEGER, INTEGER, JSONB, UUID)
    TO authenticated;
