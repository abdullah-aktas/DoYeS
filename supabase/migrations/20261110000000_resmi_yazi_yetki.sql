-- Resmi yazı menü yetkisini kurumdan ayırır (memur yazabilir; kurum kartı ayrı kalır).

CREATE OR REPLACE FUNCTION public.dose_resmi_veri() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul();
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('resmi_yazi') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Resmi yazı ekranına erişim yetkiniz yok.';
    END IF;
    RETURN jsonb_build_object(
        'yazilar', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', r.id, 'yazi_no', r.yazi_no, 'tarih', r.tarih, 'konu', r.konu, 'muhatap', r.muhatap,
            'govde', r.govde, 'surum', r.surum) ORDER BY r.id DESC)
            FROM dose_private.resmi_yazi r WHERE r.okul_id = v_okul), '[]'::JSONB),
        'yazabilir', public.dose_yetki('resmi_yazi') = 'y');
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_resmi_kaydet(p_id INTEGER, p_surum INTEGER, p_veri JSONB, p_istek UUID)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); v_id INTEGER; v_no TEXT; v_tarih DATE; v_konu TEXT; v_muhatap TEXT; v_govde TEXT;
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('resmi_yazi') <> 'y' OR auth.uid() IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Resmi yazı yazma yetkiniz yok.';
    END IF;
    IF jsonb_typeof(p_veri) IS DISTINCT FROM 'object' OR p_istek IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yazı bilgileri eksik.';
    END IF;
    v_tarih := (p_veri->>'tarih')::DATE;
    v_konu := nullif(btrim(p_veri->>'konu'), '');
    v_muhatap := nullif(btrim(p_veri->>'muhatap'), '');
    v_govde := nullif(btrim(p_veri->>'govde'), '');
    IF v_tarih IS NULL OR v_konu IS NULL OR v_muhatap IS NULL OR v_govde IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Tarih, konu, muhatap ve metin zorunludur.';
    END IF;
    IF p_id IS NULL THEN
        v_no := format('RY-%s-%s', extract(year FROM v_tarih)::INTEGER,
            lpad(dose_private.sira_no(v_okul, 'resmi_yazi', extract(year FROM v_tarih)::INTEGER)::TEXT, 4, '0'));
        INSERT INTO dose_private.resmi_yazi (okul_id, yazi_no, tarih, konu, muhatap, govde, olusturan, istek_id)
        VALUES (v_okul, v_no, v_tarih, v_konu, v_muhatap, v_govde, auth.uid(), p_istek) RETURNING id INTO v_id;
    ELSE
        UPDATE dose_private.resmi_yazi SET tarih = v_tarih, konu = v_konu, muhatap = v_muhatap, govde = v_govde,
            surum = surum + 1
        WHERE okul_id = v_okul AND id = p_id AND surum = p_surum RETURNING id INTO v_id;
        IF v_id IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yazı bulunamadı veya başkası değiştirdi.',
                HINT = 'surum_cakismasi';
        END IF;
    END IF;
    PERFORM dose_private.log(v_okul, 'Resmi yazı kaydedildi', 'resmi_yazi', v_id, v_konu);
    RETURN public.dose_resmi_veri();
END;
$$;

REVOKE ALL ON FUNCTION public.dose_resmi_veri(), public.dose_resmi_kaydet(INTEGER, INTEGER, JSONB, UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_resmi_veri(), public.dose_resmi_kaydet(INTEGER, INTEGER, JSONB, UUID) TO authenticated;
