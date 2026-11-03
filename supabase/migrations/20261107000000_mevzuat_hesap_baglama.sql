-- Doğrulanmış merkez oranlarını PB/FC kaydına bağla; UI için dose_*_veri yanıtına mevzuat ekle.

CREATE OR REPLACE FUNCTION dose_private.pb_oran_asgari(p_okul INTEGER, p_faaliyet NUMERIC, p_kar NUMERIC, p_ogrenci NUMERIC)
RETURNS VOID LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE v JSONB := dose_private.pb_mevzuat_zorunlu(p_okul);
BEGIN
    IF p_faaliyet < (v->>'pb_faaliyet_orani')::NUMERIC THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = format('Faaliyet gideri oranı doğrulanmış asgari %%%s altına inemez.',
                trim_scale((v->>'pb_faaliyet_orani')::NUMERIC * 100));
    END IF;
    IF p_kar < (v->>'pb_kar_orani')::NUMERIC THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = format('Kâr oranı doğrulanmış asgari %%%s altına inemez.',
                trim_scale((v->>'pb_kar_orani')::NUMERIC * 100));
    END IF;
    IF p_ogrenci < (v->>'ogrenci_hakki_orani')::NUMERIC THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = format('Öğrenci payı doğrulanmış asgari %%%s altına inemez.',
                trim_scale((v->>'ogrenci_hakki_orani')::NUMERIC * 100));
    END IF;
END;
$$;

DO $$
DECLARE
    v TEXT;
BEGIN
    -- dose_pb_kaydet: doğrulanmış yayın + asgari oran
    v := pg_get_functiondef('public.dose_pb_kaydet(integer, integer, jsonb, jsonb, jsonb, uuid)'::regprocedure);
    IF position('pb_mevzuat_zorunlu' IN v) = 0 THEN
        v := replace(v,
            $q$MESSAGE = 'Parça başı hakedişini yalnız yetkili Alan Şefi veya Teknik Müdür Yardımcısı hazırlayabilir.';
    END IF;$q$,
            $q$MESSAGE = 'Parça başı hakedişini yalnız yetkili Alan Şefi veya Teknik Müdür Yardımcısı hazırlayabilir.';
    END IF;
    PERFORM dose_private.pb_mevzuat_zorunlu(v_okul);$q$);
    END IF;
    IF position('pb_oran_asgari' IN v) = 0 THEN
        v := replace(v,
            $q$v_ogrenci := dose_private.pb_sayi(p_veri->'ogrenci_orani', 'Öğrenci payı oranı', 10, 1);
    v_dv := dose_private.pb_sayi(p_veri->'dv_orani', 'Damga vergisi oranı', 10, 1);$q$,
            $q$v_ogrenci := dose_private.pb_sayi(p_veri->'ogrenci_orani', 'Öğrenci payı oranı', 10, 1);
    PERFORM dose_private.pb_oran_asgari(v_okul, v_faaliyet, v_kar, v_ogrenci);
    v_dv := dose_private.pb_sayi(p_veri->'dv_orani', 'Damga vergisi oranı', 10, 1);$q$);
    END IF;
    IF position('pb_mevzuat_zorunlu' IN v) = 0 OR position('pb_oran_asgari' IN v) = 0 THEN
        RAISE EXCEPTION 'dose_pb_kaydet mevzuat bağlanamadı';
    END IF;
    EXECUTE v;

    -- dose_fc_kaydet: doğrulanmış yayın zorunlu
    v := pg_get_functiondef('public.dose_fc_kaydet(integer, integer, jsonb, jsonb, uuid)'::regprocedure);
    IF position('pb_mevzuat_zorunlu' IN v) = 0 THEN
        v := replace(v,
            $q$MESSAGE = 'Fazla çalışma bordrosunu yalnız yetkili Alan Şefi veya Teknik Müdür Yardımcısı hazırlayabilir.';
    END IF;$q$,
            $q$MESSAGE = 'Fazla çalışma bordrosunu yalnız yetkili Alan Şefi veya Teknik Müdür Yardımcısı hazırlayabilir.';
    END IF;
    PERFORM dose_private.pb_mevzuat_zorunlu(v_okul);$q$);
        IF position('pb_mevzuat_zorunlu' IN v) = 0 THEN
            RAISE EXCEPTION 'dose_fc_kaydet mevzuat bağlanamadı';
        END IF;
        EXECUTE v;
    END IF;

    -- dose_pb_veri: aktif oranları istemciye ver
    v := pg_get_functiondef('public.dose_pb_veri()'::regprocedure);
    IF position('''mevzuat''' IN v) = 0 AND position('mevzuat_okul_oranlari' IN v) = 0 THEN
        v := replace(v,
            $q$'banka_bakiye', CASE WHEN public.dose_rol() = 'Sayman'
                             THEN dose_private.kasa_bakiye(v_okul, 'Banka (102)')::TEXT END);$q$,
            $q$'mevzuat', dose_private.mevzuat_okul_oranlari(v_okul),
        'banka_bakiye', CASE WHEN public.dose_rol() = 'Sayman'
                             THEN dose_private.kasa_bakiye(v_okul, 'Banka (102)')::TEXT END);$q$);
        IF position('mevzuat_okul_oranlari' IN v) = 0 THEN
            RAISE EXCEPTION 'dose_pb_veri mevzuat alanı eklenemedi';
        END IF;
        EXECUTE v;
    END IF;

    -- dose_fc_veri: aktif oranları istemciye ver
    v := pg_get_functiondef('public.dose_fc_veri()'::regprocedure);
    IF position('mevzuat_okul_oranlari' IN v) = 0 THEN
        -- fc_veri sonunda banka_bakiye veya benzeri kapanış; dosyadan bilinen kalıp
        IF position('''banka_bakiye''' IN v) > 0 THEN
            v := replace(v,
                $q$'banka_bakiye', CASE WHEN public.dose_rol() = 'Sayman'
                             THEN dose_private.kasa_bakiye(v_okul, 'Banka (102)')::TEXT END);$q$,
                $q$'mevzuat', dose_private.mevzuat_okul_oranlari(v_okul),
        'banka_bakiye', CASE WHEN public.dose_rol() = 'Sayman'
                             THEN dose_private.kasa_bakiye(v_okul, 'Banka (102)')::TEXT END);$q$);
        END IF;
        IF position('mevzuat_okul_oranlari' IN v) = 0 THEN
            RAISE EXCEPTION 'dose_fc_veri mevzuat alanı eklenemedi';
        END IF;
        EXECUTE v;
    END IF;
END $$;
