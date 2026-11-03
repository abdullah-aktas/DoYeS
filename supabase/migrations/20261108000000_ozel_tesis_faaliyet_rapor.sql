-- Özel sektör / tesis peşinat denetimi, üç aylık faaliyet raporu, Bakanlık mizan özeti.

ALTER TABLE public.siparis
    ALTER COLUMN pesinat TYPE NUMERIC USING coalesce(pesinat, 0)::NUMERIC;
ALTER TABLE public.siparis
    ALTER COLUMN pesinat SET DEFAULT 0;

CREATE OR REPLACE FUNCTION dose_private.siparis_esas_oranlari(p_okul INTEGER, p_esas TEXT)
RETURNS JSONB LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE v JSONB := dose_private.mevzuat_okul_oranlari(p_okul);
BEGIN
    IF v IS NULL THEN
        RETURN NULL;
    END IF;
    v := v->'degerler';
    IF p_esas LIKE 'Özel Sektör%' THEN
        RETURN jsonb_build_object(
            'pesin', (v->>'os_pesin_orani')::NUMERIC,
            'kar', (v->>'os_kar_orani')::NUMERIC,
            'faaliyet', (v->>'os_faaliyet_orani')::NUMERIC,
            'etiket', 'Özel sektör işbirliği');
    ELSIF p_esas LIKE 'Tesis%' THEN
        RETURN jsonb_build_object(
            'pesin', (v->>'tesis_pesin_orani')::NUMERIC,
            'kar', (v->>'tesis_kar_orani')::NUMERIC,
            'faaliyet', (v->>'tesis_faaliyet_orani')::NUMERIC,
            'etiket', 'Tesis işletmesi');
    ELSIF p_esas LIKE 'Parça Başı%' THEN
        RETURN jsonb_build_object(
            'pesin', NULL,
            'kar', (v->>'pb_kar_orani')::NUMERIC,
            'faaliyet', (v->>'pb_faaliyet_orani')::NUMERIC,
            'etiket', 'Parça başı');
    END IF;
    RETURN jsonb_build_object('pesin', NULL, 'kar', NULL, 'faaliyet', NULL, 'etiket', p_esas);
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.siparis_pesinat_zorunlu(p_okul INTEGER, p_esas TEXT, p_bedel NUMERIC, p_pesinat NUMERIC)
RETURNS VOID LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE v JSONB; v_asgari NUMERIC;
BEGIN
    IF p_esas IS NULL OR (p_esas NOT LIKE 'Özel Sektör%' AND p_esas NOT LIKE 'Tesis%') THEN
        RETURN;
    END IF;
    v := dose_private.siparis_esas_oranlari(p_okul, p_esas);
    IF v IS NULL OR v->>'pesin' IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = 'Özel sektör / tesis siparişi için doğrulanmış merkez parametre yayını zorunludur.';
    END IF;
    v_asgari := round(p_bedel * (v->>'pesin')::NUMERIC, 2);
    IF p_pesinat IS NULL OR p_pesinat::TEXT IN ('NaN', 'Infinity', '-Infinity')
       OR p_pesinat < 0 OR p_pesinat <> round(p_pesinat, 2) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Peşinat tutarı kuruşlu ve sıfır veya üstü olmalıdır.';
    END IF;
    IF p_pesinat < v_asgari THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = format('%s peşinatı en az %s TL olmalıdır (bedelin %%%s''i).',
                v->>'etiket', v_asgari, trim_scale((v->>'pesin')::NUMERIC * 100));
    END IF;
    IF p_pesinat > p_bedel THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Peşinat sözleşme bedelini aşamaz.';
    END IF;
END;
$$;

DO $$
DECLARE v TEXT;
BEGIN
    -- dose_siparis_kaydet: peşinat yaz + özel/tesis asgari peşinat
    v := pg_get_functiondef('public.dose_siparis_kaydet(integer, integer, jsonb, jsonb)'::regprocedure);
    IF position('siparis_pesinat_zorunlu' IN v) = 0 THEN
        v := replace(v,
            $q$v_kdv := coalesce(nullif(p_siparis->>'kdv_orani', '')::NUMERIC, 0.20);$q$,
            $q$v_kdv := coalesce(nullif(p_siparis->>'kdv_orani', '')::NUMERIC, 0.20);
    -- peşinat alan adı aşağıdaki INSERT/UPDATE yamalarında kullanılır$q$);
        -- INSERT kolonlarına pesinat ekle
        v := replace(v,
            $q$INSERT INTO public.siparis (
            okul_id, siparis_no, tarih, cari_id, bolum_id, konu, ucret_esasi, kdv_orani,
            durum, aciklama, olusturan, guncelleyen
        ) VALUES (
            v_okul, format('SIP-%s-%s', to_char(v_tarih, 'YYYY'), lpad(dose_private.sira_no(v_okul, 'siparis', extract(year FROM v_tarih)::INTEGER)::TEXT, 5, '0')),
            v_tarih::TEXT, v_cari, v_bolum, v_konu, v_esas, v_kdv, 'Taslak',
            nullif(btrim(p_siparis->>'aciklama'), ''), v_uid, v_ad
        ) RETURNING * INTO v_siparis;$q$,
            $q$INSERT INTO public.siparis (
            okul_id, siparis_no, tarih, cari_id, bolum_id, konu, ucret_esasi, kdv_orani, pesinat,
            durum, aciklama, olusturan, guncelleyen
        ) VALUES (
            v_okul, format('SIP-%s-%s', to_char(v_tarih, 'YYYY'), lpad(dose_private.sira_no(v_okul, 'siparis', extract(year FROM v_tarih)::INTEGER)::TEXT, 5, '0')),
            v_tarih::TEXT, v_cari, v_bolum, v_konu, v_esas, v_kdv,
            coalesce(nullif(p_siparis->>'pesinat', '')::NUMERIC, 0), 'Taslak',
            nullif(btrim(p_siparis->>'aciklama'), ''), v_uid, v_ad
        ) RETURNING * INTO v_siparis;$q$);
        v := replace(v,
            $q$UPDATE public.siparis SET
            tarih = v_tarih::TEXT, cari_id = v_cari, bolum_id = v_bolum, konu = v_konu,
            ucret_esasi = v_esas, kdv_orani = v_kdv, durum = 'Taslak',
            aciklama = nullif(btrim(p_siparis->>'aciklama'), ''),
            surum = surum + 1, guncelleyen = v_ad
        WHERE id = p_siparis_id AND okul_id = v_okul RETURNING * INTO v_siparis;$q$,
            $q$UPDATE public.siparis SET
            tarih = v_tarih::TEXT, cari_id = v_cari, bolum_id = v_bolum, konu = v_konu,
            ucret_esasi = v_esas, kdv_orani = v_kdv,
            pesinat = coalesce(nullif(p_siparis->>'pesinat', '')::NUMERIC, 0), durum = 'Taslak',
            aciklama = nullif(btrim(p_siparis->>'aciklama'), ''),
            surum = surum + 1, guncelleyen = v_ad
        WHERE id = p_siparis_id AND okul_id = v_okul RETURNING * INTO v_siparis;$q$);
        -- bedel güncellendikten sonra peşinat denetimi
        IF position('sozlesme_bedeli = v_toplam, malzeme_maliyeti = 0, iscilik_tutari = 0' IN v) > 0
           AND position('siparis_pesinat_zorunlu' IN v) = 0 THEN
            v := replace(v,
                $q$UPDATE public.siparis SET sozlesme_bedeli = v_toplam, malzeme_maliyeti = 0, iscilik_tutari = 0$q$,
                $q$PERFORM dose_private.siparis_pesinat_zorunlu(v_okul, v_esas, v_toplam,
        coalesce(nullif(p_siparis->>'pesinat', '')::NUMERIC, 0));
    UPDATE public.siparis SET sozlesme_bedeli = v_toplam, malzeme_maliyeti = 0, iscilik_tutari = 0$q$);
        END IF;
        IF position('siparis_pesinat_zorunlu' IN v) = 0 THEN
            RAISE EXCEPTION 'dose_siparis_kaydet peşinat bağlanamadı';
        END IF;
        EXECUTE v;
    END IF;

    -- dose_siparisler: pesinat alanını döndür
    v := pg_get_functiondef('public.dose_siparisler()'::regprocedure);
    IF position('''pesinat''' IN v) = 0 AND position('pesinat::TEXT' IN v) = 0 THEN
        v := replace(v,
            $q$'ucret_esasi', s.ucret_esasi, 'sozlesme_bedeli', s.sozlesme_bedeli,
            'sozlesme_bedeli_kesin', s.sozlesme_bedeli::TEXT,$q$,
            $q$'ucret_esasi', s.ucret_esasi, 'pesinat', coalesce(s.pesinat, 0)::TEXT,
            'sozlesme_bedeli', s.sozlesme_bedeli,
            'sozlesme_bedeli_kesin', s.sozlesme_bedeli::TEXT,$q$);
        IF position('pesinat' IN v) = 0 THEN
            RAISE EXCEPTION 'dose_siparisler peşinat alanı eklenemedi';
        END IF;
        EXECUTE v;
    END IF;
END $$;

-- ------------------------------------------------------------------ üç aylık faaliyet raporu (Yön. md.48)
CREATE OR REPLACE FUNCTION public.dose_faaliyet_rapor(p_yil INTEGER DEFAULT NULL) RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_yil INTEGER := coalesce(p_yil, extract(year FROM now() AT TIME ZONE 'Europe/Istanbul')::INTEGER);
    v_donemler JSONB := '[]'::JSONB;
    v_ad TEXT; v_aylar INTEGER[]; v_son TEXT; v_i INTEGER; v_ay INTEGER;
    v_siparis INTEGER; v_satis NUMERIC; v_alis NUMERIC; v_tahsilat NUMERIC;
    v_pb NUMERIC; v_fc NUMERIC; v_hp NUMERIC;
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('yevmiye') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Faaliyet raporuna erişim yetkiniz yok.';
    END IF;
    FOR v_i IN 1..4 LOOP
        v_aylar := CASE v_i
            WHEN 1 THEN ARRAY[1,2,3]
            WHEN 2 THEN ARRAY[4,5,6]
            WHEN 3 THEN ARRAY[7,8,9]
            ELSE ARRAY[10,11,12] END;
        v_ad := CASE v_i
            WHEN 1 THEN 'I. Dönem (Ocak-Mart)'
            WHEN 2 THEN 'II. Dönem (Nisan-Haziran)'
            WHEN 3 THEN 'III. Dönem (Temmuz-Eylül)'
            ELSE 'IV. Dönem (Ekim-Aralık)' END;
        v_son := CASE v_i
            WHEN 1 THEN format('%s-04-05', v_yil)
            WHEN 2 THEN format('%s-07-05', v_yil)
            WHEN 3 THEN format('%s-10-05', v_yil)
            ELSE format('%s-01-05', v_yil + 1) END;
        SELECT count(*) INTO v_siparis FROM public.siparis s
        WHERE s.okul_id = v_okul AND extract(year FROM s.tarih::DATE) = v_yil
          AND extract(month FROM s.tarih::DATE)::INTEGER = ANY (v_aylar);
        SELECT coalesce(sum(net_tutar), 0) INTO v_satis FROM public.fatura f
        WHERE f.okul_id = v_okul AND f.tur = 'Satış' AND f.iptal = 0
          AND extract(year FROM f.tarih::DATE) = v_yil
          AND extract(month FROM f.tarih::DATE)::INTEGER = ANY (v_aylar);
        SELECT coalesce(sum(net_tutar), 0) INTO v_alis FROM public.fatura f
        WHERE f.okul_id = v_okul AND f.tur = 'Alış' AND f.iptal = 0
          AND extract(year FROM f.tarih::DATE) = v_yil
          AND extract(month FROM f.tarih::DATE)::INTEGER = ANY (v_aylar);
        SELECT coalesce(sum(tutar), 0) INTO v_tahsilat FROM public.kasa_banka k
        WHERE k.okul_id = v_okul AND k.yon = 'Giriş' AND k.ters_hareket_id IS NULL
          AND extract(year FROM k.tarih::DATE) = v_yil
          AND extract(month FROM k.tarih::DATE)::INTEGER = ANY (v_aylar)
          AND NOT EXISTS (SELECT 1 FROM public.kasa_banka t WHERE t.okul_id = k.okul_id AND t.ters_hareket_id = k.id);
        SELECT coalesce(sum((h.hesap->'toplam'->>'brut')::NUMERIC), 0) INTO v_pb
        FROM dose_private.pb_hakedis h
        WHERE h.okul_id = v_okul AND h.durum = 'Onaylandı' AND h.yil = v_yil AND h.ay = ANY (v_aylar);
        SELECT coalesce(sum((b.hesap->'toplam'->>'brut')::NUMERIC), 0) INTO v_fc
        FROM dose_private.fc_bordro b
        WHERE b.okul_id = v_okul AND b.durum = 'Onaylandı' AND b.yil = v_yil AND b.ay = ANY (v_aylar);
        SELECT coalesce(sum(d.hasilat * 0.01), 0) INTO v_hp
        FROM dose_private.hp_donem d
        WHERE d.okul_id = v_okul AND d.durum <> 'İptal' AND d.yil = v_yil AND d.ay = ANY (v_aylar);
        v_donemler := v_donemler || jsonb_build_array(jsonb_build_object(
            'donem', v_ad, 'son_gun', v_son, 'siparis', v_siparis,
            'satis', v_satis::TEXT, 'alis', v_alis::TEXT, 'tahsilat', v_tahsilat::TEXT,
            'parca_basi', v_pb::TEXT, 'fazla_calisma', v_fc::TEXT, 'hazine', round(v_hp, 2)::TEXT));
    END LOOP;
    RETURN jsonb_build_object('yil', v_yil, 'donemler', v_donemler,
        'not', 'Yönerge md.48: dönemi izleyen ayın 5''ine kadar Bakanlığa gönderilir. Bu çıktı GİB belgesi değildir.');
END;
$$;

REVOKE ALL ON FUNCTION public.dose_faaliyet_rapor(INTEGER) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_faaliyet_rapor(INTEGER) TO authenticated;

-- ------------------------------------------------------------------ Bakanlık aylık mizan özeti (Ek-9 tarzı)
CREATE OR REPLACE FUNCTION public.dose_mizan_bakanlik(p_yil INTEGER DEFAULT NULL, p_ay INTEGER DEFAULT NULL)
RETURNS JSONB LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_yil INTEGER := coalesce(p_yil, extract(year FROM now() AT TIME ZONE 'Europe/Istanbul')::INTEGER);
    v_ay INTEGER := coalesce(p_ay, extract(month FROM now() AT TIME ZONE 'Europe/Istanbul')::INTEGER);
    v_mizan JSONB;
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('yevmiye') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Mizan raporuna erişim yetkiniz yok.';
    END IF;
    IF v_ay NOT BETWEEN 1 AND 12 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ay 1-12 arasında olmalıdır.';
    END IF;
    v_mizan := public.dose_mizan_veri();
    RETURN jsonb_build_object(
        'yil', v_yil, 'ay', v_ay,
        'son_gun', make_date(
            CASE WHEN v_ay = 12 THEN v_yil + 1 ELSE v_yil END,
            CASE WHEN v_ay = 12 THEN 1 ELSE v_ay + 1 END, 5),
        'satirlar', coalesce(v_mizan, '[]'::JSONB),
        'not', 'Aylık mizan ertesi ayın 5''ine kadar Bakanlığa gönderilir (Yön. md.47). Bu çıktı GİB belgesi değildir.');
END;
$$;

REVOKE ALL ON FUNCTION public.dose_mizan_bakanlik(INTEGER, INTEGER) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_mizan_bakanlik(INTEGER, INTEGER) TO authenticated;
