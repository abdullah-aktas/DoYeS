-- Doğrudan temin: büyükşehir/diğer limit, limit aşımını engelleme, teklif + ihtiyaç alanları.

ALTER TABLE public.fatura
    ADD COLUMN IF NOT EXISTS alim_detay JSONB NOT NULL DEFAULT '{}'::JSONB;

COMMENT ON COLUMN public.fatura.alim_detay IS
    'ihtiyac_ozeti, yaklasik_maliyet, teklifler[] — doğrudan temin dosya özeti';

CREATE OR REPLACE FUNCTION dose_private.dogrudan_temin_limit(p_okul INTEGER)
RETURNS NUMERIC
LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE
    v_buyuk BOOLEAN;
    -- 4734 md.22/d; 2026/1 KİK Tebliği — dose/mevzuat.py ile aynı.
    v_diger CONSTANT NUMERIC := 340391;
    v_buyuksehir CONSTANT NUMERIC := 1021827;
BEGIN
    SELECT coalesce(k.buyuksehir, 0) = 1 INTO v_buyuk
    FROM public.kurum k WHERE k.okul_id = p_okul;
    RETURN CASE WHEN coalesce(v_buyuk, false) THEN v_buyuksehir ELSE v_diger END;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.alim_dogrula(p_tur TEXT, p_alim JSONB, p_matrah NUMERIC,
                                                     p_zorla BOOLEAN DEFAULT TRUE, p_okul INTEGER DEFAULT NULL)
RETURNS JSONB LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE
    v_temin TEXT; v_gider TEXT; v_belge TEXT; v_belgeler JSONB; v_beklenen JSONB; v_b JSONB;
    v_uyari TEXT[] := ARRAY[]::TEXT[]; v_eksik TEXT[] := ARRAY[]::TEXT[];
    v_limit NUMERIC; v_okul INTEGER := coalesce(p_okul, public.dose_okul());
    v_ihtiyac TEXT; v_ym TEXT; v_ym_sayi NUMERIC; v_teklifler JSONB; v_t JSONB;
    v_teklif_sayisi INTEGER := 0; v_secili INTEGER := 0; v_detay JSONB;
BEGIN
    IF p_tur <> 'Alış' THEN
        RETURN jsonb_build_object('temin_usulu', NULL, 'gider_turu', NULL, 'belge_turu', 'Fatura',
            'belgeler', '{}'::JSONB, 'detay', '{}'::JSONB, 'uyarilar', '[]'::JSONB,
            'dogrudan_temin_limit', NULL);
    END IF;
    IF jsonb_typeof(p_alim) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Alış faturasında temin usulü ve alım bilgileri zorunludur.';
    END IF;
    v_temin := nullif(btrim(p_alim->>'temin_usulu'), '');
    v_gider := nullif(btrim(p_alim->>'gider_turu'), '');
    v_belge := coalesce(nullif(btrim(p_alim->>'belge_turu'), ''), 'e-Fatura');
    IF v_temin IS NULL OR NOT EXISTS (SELECT 1 FROM public.secenek WHERE liste = 'temin_usulu' AND deger = v_temin) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Geçerli bir temin usulü seçiniz.';
    END IF;
    IF v_gider IS NULL OR NOT EXISTS (SELECT 1 FROM public.secenek WHERE liste = 'gider_turu' AND deger = v_gider) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Geçerli bir gider türü seçiniz.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.secenek WHERE liste = 'alis_belge_turu' AND deger = v_belge) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Geçerli bir alış belge türü seçiniz.';
    END IF;
    v_belgeler := coalesce(p_alim->'belgeler', '{}'::JSONB);
    IF jsonb_typeof(v_belgeler) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Alım belge kontrol listesi geçersiz.';
    END IF;
    v_beklenen := dose_private.alim_belge_listesi(v_temin);
    FOR v_b IN SELECT value FROM jsonb_array_elements(v_beklenen) LOOP
        IF (v_b->>'zorunlu')::BOOLEAN AND coalesce((v_belgeler->>(v_b->>'anahtar'))::BOOLEAN, false) IS NOT TRUE THEN
            v_eksik := array_append(v_eksik, v_b->>'etiket');
        END IF;
    END LOOP;
    IF p_zorla AND array_length(v_eksik, 1) IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = format('Zorunlu alım belgeleri işaretlenmedi: %s', array_to_string(v_eksik, ', '));
    ELSIF array_length(v_eksik, 1) IS NOT NULL THEN
        v_uyari := array_append(v_uyari, format('Eksik zorunlu belgeler: %s', array_to_string(v_eksik, ', ')));
    END IF;

    v_limit := dose_private.dogrudan_temin_limit(v_okul);
    v_ihtiyac := nullif(btrim(coalesce(p_alim->>'ihtiyac_ozeti', '')), '');
    v_ym := nullif(btrim(coalesce(p_alim->>'yaklasik_maliyet', '')), '');
    v_teklifler := coalesce(p_alim->'teklifler', '[]'::JSONB);
    IF jsonb_typeof(v_teklifler) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Teklif listesi geçersiz.';
    END IF;

    IF v_temin = 'Doğrudan Temin' THEN
        IF v_ihtiyac IS NULL OR length(v_ihtiyac) < 10 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001',
                MESSAGE = 'Doğrudan teminde ihtiyaç / talep özeti en az 10 karakter olmalıdır.';
        END IF;
        BEGIN
            v_ym_sayi := replace(replace(v_ym, '.', ''), ',', '.')::NUMERIC;
        EXCEPTION WHEN others THEN
            v_ym_sayi := NULL;
        END;
        IF v_ym_sayi IS NULL OR v_ym_sayi <= 0 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001',
                MESSAGE = 'Doğrudan teminde yaklaşık maliyet (KDV hariç, pozitif tutar) zorunludur.';
        END IF;
        FOR v_t IN SELECT value FROM jsonb_array_elements(v_teklifler) LOOP
            IF nullif(btrim(coalesce(v_t->>'firma', '')), '') IS NOT NULL
               AND nullif(btrim(coalesce(v_t->>'tutar', '')), '') IS NOT NULL THEN
                v_teklif_sayisi := v_teklif_sayisi + 1;
                IF coalesce((v_t->>'secildi')::BOOLEAN, false) THEN
                    v_secili := v_secili + 1;
                END IF;
            END IF;
        END LOOP;
        IF v_teklif_sayisi < 1 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001',
                MESSAGE = 'Doğrudan teminde en az bir piyasa fiyat teklifi (firma + tutar) giriniz.';
        END IF;
        IF v_teklif_sayisi < 3 THEN
            v_uyari := array_append(v_uyari,
                format('Yalnız %s teklif girildi; piyasa araştırmasında mümkünse en az 3 teklif alın.', v_teklif_sayisi));
        END IF;
        IF v_secili <> 1 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001',
                MESSAGE = 'Doğrudan teminde tekliflerden tam olarak birini «seçildi» olarak işaretleyin.';
        END IF;
        IF p_matrah IS NOT NULL AND p_matrah > v_limit THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001',
                MESSAGE = format(
                    'Matrah (%s TL) doğrudan temin limitini (%s TL, KDV hariç) aşıyor. '
                    'Usulü değiştirin (pazarlık/ihale) veya alımı bölmeden mevzuata uygun süreç seçin.',
                    trim_scale(p_matrah), trim_scale(v_limit));
        END IF;
        IF v_ym_sayi > v_limit THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001',
                MESSAGE = format(
                    'Yaklaşık maliyet (%s TL) doğrudan temin limitini (%s TL) aşıyor.',
                    trim_scale(v_ym_sayi), trim_scale(v_limit));
        END IF;
    END IF;

    v_detay := jsonb_build_object(
        'ihtiyac_ozeti', coalesce(v_ihtiyac, ''),
        'yaklasik_maliyet', coalesce(v_ym, ''),
        'teklifler', v_teklifler);

    RETURN jsonb_build_object(
        'temin_usulu', v_temin, 'gider_turu', v_gider, 'belge_turu', v_belge,
        'belgeler', v_belgeler, 'detay', v_detay,
        'uyarilar', to_jsonb(coalesce(v_uyari, ARRAY[]::TEXT[])),
        'dogrudan_temin_limit', to_jsonb(v_limit));
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_alim_onizle(p_alim JSONB, p_matrah NUMERIC DEFAULT NULL)
RETURNS JSONB LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF public.dose_okul() IS NULL OR public.dose_yetki('fatura') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Fatura ekranına erişim yetkiniz yok.';
    END IF;
    RETURN dose_private.alim_dogrula('Alış', p_alim, p_matrah, FALSE, public.dose_okul());
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_alim_hazirla(p_istek UUID, p_alim JSONB, p_matrah NUMERIC DEFAULT NULL)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_alim JSONB;
BEGIN
    IF v_okul IS NULL OR auth.uid() IS NULL OR public.dose_yetki('fatura') <> 'y' OR public.dose_rol() <> 'Sayman' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Alım bilgisini yalnız yetkili sayman hazırlayabilir.';
    END IF;
    IF p_istek IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İşlem kimliği zorunludur.';
    END IF;
    v_alim := dose_private.alim_dogrula('Alış', p_alim, p_matrah, TRUE, v_okul);
    INSERT INTO dose_private.alim_istek (istek_id, okul_id, alim, olusturan)
    VALUES (p_istek, v_okul, v_alim, auth.uid())
    ON CONFLICT (istek_id) DO UPDATE SET alim = EXCLUDED.alim, olusturma = now()
    WHERE dose_private.alim_istek.olusturan = auth.uid() AND dose_private.alim_istek.okul_id = v_okul;
    RETURN v_alim;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.fatura_alim_before() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_alim JSONB;
BEGIN
    IF NEW.tur = 'Alış' THEN
        SELECT a.alim INTO v_alim FROM dose_private.alim_istek a
        WHERE a.istek_id = NEW.istek_id AND a.okul_id = NEW.okul_id AND a.olusturan = auth.uid();
        IF v_alim IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001',
                MESSAGE = 'Alış faturası için önce temin usulü ve alım belgelerini kaydedin.';
        END IF;
        NEW.temin_usulu := v_alim->>'temin_usulu';
        NEW.gider_turu := v_alim->>'gider_turu';
        NEW.belge_turu := coalesce(v_alim->>'belge_turu', NEW.belge_turu, 'e-Fatura');
        NEW.alim_belgeler := coalesce(v_alim->'belgeler', '{}'::JSONB);
        NEW.alim_detay := coalesce(v_alim->'detay', '{}'::JSONB);
        DELETE FROM dose_private.alim_istek WHERE istek_id = NEW.istek_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_fatura_secimleri() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul(); v_tanimlar JSONB; v_taban JSONB; v_limit NUMERIC;
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('fatura') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Fatura ekranına erişim yetkiniz yok.';
    END IF;
    v_tanimlar := public.dose_finans_tanimlari();
    v_limit := dose_private.dogrudan_temin_limit(v_okul);
    v_taban := jsonb_build_object(
        'cariler', coalesce((SELECT jsonb_agg(jsonb_build_object('id', c.id, 'unvan', c.unvan, 'tur', c.tur)
                                             ORDER BY c.unvan)
                             FROM public.cari c WHERE c.okul_id = v_okul AND c.aktif = 1), '[]'::JSONB),
        'stoklar', coalesce((SELECT jsonb_agg(jsonb_build_object('id', m.id, 'ad', m.ad, 'tur', m.tur, 'birim', m.birim)
                                             ORDER BY m.ad)
                             FROM public.malzeme m WHERE m.okul_id = v_okul AND m.aktif = 1), '[]'::JSONB),
        'hesaplar', v_tanimlar->'hesaplar', 'vergi_hesaplari', v_tanimlar->'vergi_hesaplari',
        'siparisler', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', s.id, 'siparis_no', s.siparis_no, 'tarih', s.tarih, 'cari_id', s.cari_id, 'konu', s.konu,
            'kdv_orani', s.kdv_orani::TEXT,
            'kalemler', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'id', k.id, 'urun_id', k.urun_id, 'aciklama', k.aciklama, 'birim', k.birim,
                'miktar', k.miktar::TEXT, 'birim_fiyat', k.birim_fiyat::TEXT, 'iskonto_orani', k.iskonto_orani::TEXT,
                'kalan', (k.miktar - coalesce((SELECT sum(fk.miktar) FROM public.fatura_kalem fk
                    JOIN public.fatura f ON f.okul_id = fk.okul_id AND f.id = fk.fatura_id
                    WHERE fk.okul_id = v_okul AND fk.siparis_kalem_id = k.id AND f.iptal = 0), 0))::TEXT,
                'stok_baglanti_kaynagi', k.stok_baglanti_kaynagi,
                'malzeme_id', CASE WHEN k.stok_baglanti_kaynagi IS NULL THEN u.mamul_malzeme_id
                                   ELSE k.stok_malzeme_onay_id END,
                'malzeme_ad', m.ad) ORDER BY k.id)
                FROM public.siparis_kalem k LEFT JOIN public.urun u ON u.okul_id = k.okul_id AND u.id = k.urun_id
                LEFT JOIN public.malzeme m ON m.okul_id = k.okul_id
                  AND m.id = CASE WHEN k.stok_baglanti_kaynagi IS NULL THEN u.mamul_malzeme_id
                                  ELSE k.stok_malzeme_onay_id END
                WHERE k.okul_id = v_okul AND k.siparis_id = s.id), '[]'::JSONB))
            ORDER BY s.id DESC)
            FROM public.siparis s WHERE s.okul_id = v_okul AND s.durum = 'Sözleşme İmzalandı'
              AND EXISTS (SELECT 1 FROM public.onay_durum o WHERE o.okul_id = v_okul AND o.belge_turu = 'Sipariş'
                          AND o.belge_id = s.id AND o.durum = 'Onaylandı' AND o.asama > 3)), '[]'::JSONB));
    RETURN v_taban || jsonb_build_object(
        'temin_usulleri', coalesce((SELECT jsonb_agg(jsonb_build_object('deger', deger, 'etiket', etiket) ORDER BY sira)
            FROM public.secenek WHERE liste = 'temin_usulu'), '[]'::JSONB),
        'gider_turleri', coalesce((SELECT jsonb_agg(jsonb_build_object('deger', deger, 'etiket', etiket) ORDER BY sira)
            FROM public.secenek WHERE liste = 'gider_turu'), '[]'::JSONB),
        'alis_belge_turleri', coalesce((SELECT jsonb_agg(jsonb_build_object('deger', deger, 'etiket', etiket) ORDER BY sira)
            FROM public.secenek WHERE liste = 'alis_belge_turu'), '[]'::JSONB),
        'alim_belgeler', jsonb_build_object(
            'Doğrudan Temin', dose_private.alim_belge_listesi('Doğrudan Temin'),
            'Pazarlık Usulü', dose_private.alim_belge_listesi('Pazarlık Usulü'),
            'Belli İstekliler Arasında İhale', dose_private.alim_belge_listesi('Belli İstekliler Arasında İhale'),
            'Açık İhale', dose_private.alim_belge_listesi('Açık İhale'),
            '4734 md.3/e Kapsamında Alım', dose_private.alim_belge_listesi('4734 md.3/e Kapsamında Alım'),
            'Diğer', dose_private.alim_belge_listesi('Diğer')),
        'dogrudan_temin_limit', v_limit::TEXT,
        'dogrudan_temin_limit_diger', '340391',
        'dogrudan_temin_limit_buyuksehir', '1021827');
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_faturalar() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul();
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('fatura') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Fatura ekranına erişim yetkiniz yok.';
    END IF;
    RETURN coalesce((SELECT jsonb_agg(jsonb_build_object(
        'id', f.id, 'tur', f.tur, 'belge_no', f.belge_no, 'belge_turu', f.belge_turu, 'tarih', f.tarih,
        'cari_id', f.cari_id, 'cari_unvan', c.unvan, 'siparis_id', f.siparis_id, 'iptal', f.iptal,
        'temin_usulu', f.temin_usulu, 'gider_turu', f.gider_turu,
        'alim_belgeler', coalesce(f.alim_belgeler, '{}'::JSONB),
        'alim_detay', coalesce(f.alim_detay, '{}'::JSONB),
        'matrah', f.matrah::TEXT, 'iskonto', f.iskonto::TEXT, 'kdv', f.kdv::TEXT,
        'tevkifat_orani', f.tevkifat_orani::TEXT, 'tevkif_kdv', f.tevkif_kdv::TEXT, 'tevkifat_hesabi', f.tevkifat_hesabi,
        'stopaj_orani', f.stopaj_orani::TEXT, 'stopaj', f.stopaj::TEXT, 'stopaj_hesabi', f.stopaj_hesabi,
        'genel_toplam', f.genel_toplam::TEXT, 'net_tutar', f.net_tutar::TEXT,
        'odenen', o.tutar::TEXT, 'kalan', (f.net_tutar - o.tutar)::TEXT,
        'ters_gerekce', (SELECT i.gerekce FROM dose_private.fatura_iptal i WHERE i.okul_id = v_okul AND i.fatura_id = f.id),
        'kalemler', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', k.id, 'siparis_kalem_id', k.siparis_kalem_id, 'malzeme_id', k.malzeme_id,
            'aciklama', k.aciklama, 'birim', k.birim, 'miktar', k.miktar::TEXT, 'birim_fiyat', k.birim_fiyat::TEXT,
            'brut', k.brut::TEXT, 'iskonto', k.iskonto::TEXT, 'tutar', k.tutar::TEXT, 'kdv', k.kdv::TEXT,
            'hesap_kodu', k.hesap_kodu, 'stok_maliyeti', k.stok_maliyeti::TEXT,
            'stok_maliyet_hesabi', k.stok_maliyet_hesabi) ORDER BY k.id)
            FROM public.fatura_kalem k WHERE k.okul_id = v_okul AND k.fatura_id = f.id), '[]'::JSONB))
        ORDER BY f.id DESC)
        FROM public.fatura f JOIN public.cari c ON c.okul_id = f.okul_id AND c.id = f.cari_id
        LEFT JOIN LATERAL (
            SELECT coalesce(sum(CASE WHEN k.ters_hareket_id IS NULL THEN k.tutar::NUMERIC ELSE -k.tutar::NUMERIC END), 0) AS tutar
            FROM public.kasa_banka k WHERE k.okul_id = f.okul_id AND k.fatura_id = f.id
        ) o ON true
        WHERE f.okul_id = v_okul), '[]'::JSONB);
END;
$$;

REVOKE ALL ON FUNCTION public.dose_alim_onizle(JSONB, NUMERIC) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.dose_alim_hazirla(UUID, JSONB, NUMERIC) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.dose_fatura_secimleri() FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.dose_faturalar() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_alim_onizle(JSONB, NUMERIC) TO authenticated;
GRANT EXECUTE ON FUNCTION public.dose_alim_hazirla(UUID, JSONB, NUMERIC) TO authenticated;
GRANT EXECUTE ON FUNCTION public.dose_fatura_secimleri() TO authenticated;
GRANT EXECUTE ON FUNCTION public.dose_faturalar() TO authenticated;
