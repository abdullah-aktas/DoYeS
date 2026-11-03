-- Öğretmen puantaj yazımı; memur resmi yazı; ana ekran görevlerini her role yay.

-- Sistem, Müdür, TMY, Sayman, Alan Şefi, Öğretmen, Memur, İzleyici
UPDATE dose_private.sayfa_yetki SET kodlar = 'gyyyyygg', baslik = 'Parça Başı Hakediş'
 WHERE sayfa = 'parca_basi';
UPDATE dose_private.sayfa_yetki SET kodlar = 'gyyyyygg', baslik = 'Fazla Çalışma'
 WHERE sayfa = 'fazla_calisma';

INSERT INTO dose_private.sayfa_yetki (sayfa, baslik, kodlar)
VALUES ('resmi_yazi', 'Resmi Yazılar', 'yygy--yg')
ON CONFLICT (sayfa) DO UPDATE SET baslik = EXCLUDED.baslik, kodlar = EXCLUDED.kodlar;

CREATE OR REPLACE FUNCTION dose_private.pb_hazirlayabilir(p_okul INTEGER, p_siparis INTEGER) RETURNS BOOLEAN
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT auth.uid() IS NOT NULL AND public.dose_yetki('parca_basi') = 'y'
       AND public.dose_rol() IN ('Alan Şefi', 'Teknik Müdür Yardımcısı', 'Öğretmen')
       AND (public.dose_rol() NOT IN ('Alan Şefi', 'Öğretmen') OR EXISTS (
            SELECT 1 FROM public.siparis s WHERE s.okul_id = p_okul AND s.id = p_siparis
              AND s.bolum_id = public.dose_bolum()))
$$;

CREATE OR REPLACE FUNCTION dose_private.fc_hazirlayabilir(p_okul INTEGER, p_siparis INTEGER) RETURNS BOOLEAN
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT auth.uid() IS NOT NULL AND public.dose_yetki('fazla_calisma') = 'y'
       AND public.dose_rol() IN ('Alan Şefi', 'Teknik Müdür Yardımcısı', 'Öğretmen')
       AND (public.dose_rol() NOT IN ('Alan Şefi', 'Öğretmen') OR EXISTS (
            SELECT 1 FROM public.siparis s WHERE s.okul_id = p_okul AND s.id = p_siparis
              AND s.bolum_id = public.dose_bolum()))
$$;

CREATE OR REPLACE FUNCTION public.dose_gorevlerim() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_rol TEXT := public.dose_rol();
    v_bolum INTEGER := public.dose_bolum();
    v_liste JSONB := '[]'::JSONB;
    v_yil INTEGER := extract(year FROM now() AT TIME ZONE 'Europe/Istanbul')::INTEGER;
    v_ay INTEGER := extract(month FROM now() AT TIME ZONE 'Europe/Istanbul')::INTEGER;
BEGIN
    IF v_okul IS NULL OR auth.uid() IS NULL THEN
        RETURN jsonb_build_object('gorevler', '[]'::JSONB);
    END IF;

    -- Sipariş onay (1=Alan Şefi, 2=TMY, 3=Müdür)
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

    -- Hazırlayan: taslak PB/FC (iade edilenler de Taslak'a döner)
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

        -- Hazine: bu ay hasılatı var ve tam ödeme yoksa hatırlat
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

REVOKE ALL ON FUNCTION public.dose_gorevlerim() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_gorevlerim() TO authenticated;
