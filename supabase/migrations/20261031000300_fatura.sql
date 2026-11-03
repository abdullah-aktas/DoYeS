-- Invoice records are local accounting documents, not electronic invoice submissions.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.fatura) OR EXISTS (SELECT 1 FROM public.fatura_kalem) THEN
        RAISE EXCEPTION 'Eski fatura kayıtları var; çok okullu finans kurulumu öncesinde kayıtları inceleyin.';
    END IF;
END;
$$;

INSERT INTO dose_private.sayfa_yetki (sayfa, baslik, kodlar)
VALUES ('fatura', 'Alış ve Satış Faturaları', 'gggy--gg')
ON CONFLICT (sayfa) DO UPDATE SET baslik = EXCLUDED.baslik, kodlar = EXCLUDED.kodlar;

ALTER TABLE public.siparis_kalem
    ADD COLUMN stok_malzeme_onay_id INTEGER REFERENCES public.malzeme(id),
    ADD COLUMN stok_baglanti_kaynagi TEXT
        CHECK (stok_baglanti_kaynagi IN ('Sipariş onayı', 'Sayman doğrulaması')),
    ADD CONSTRAINT siparis_stok_baglanti_kaynagi
        CHECK (stok_baglanti_kaynagi IS NOT NULL OR stok_malzeme_onay_id IS NULL);

ALTER TABLE public.kasa_banka
    ADD COLUMN IF NOT EXISTS ters_hareket_id INTEGER REFERENCES public.kasa_banka(id);

CREATE OR REPLACE FUNCTION dose_private.siparis_stok_baglantisini_sakla() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM 1 FROM public.urun u
    WHERE u.okul_id = NEW.okul_id AND EXISTS (
        SELECT 1 FROM public.siparis_kalem k
        WHERE k.okul_id = NEW.okul_id AND k.siparis_id = NEW.belge_id AND k.urun_id = u.id
    ) ORDER BY u.id FOR SHARE;
    UPDATE public.siparis_kalem k SET
        stok_malzeme_onay_id = (SELECT u.mamul_malzeme_id FROM public.urun u
                                WHERE u.okul_id = k.okul_id AND u.id = k.urun_id),
        stok_baglanti_kaynagi = 'Sipariş onayı'
    WHERE k.okul_id = NEW.okul_id AND k.siparis_id = NEW.belge_id;
    RETURN NEW;
END;
$$;
CREATE TRIGGER dose_siparis_stok_baglantisini_sakla
    AFTER UPDATE OF durum ON public.onay_durum
    FOR EACH ROW
    WHEN (NEW.belge_turu = 'Sipariş' AND NEW.durum = 'Onaylandı' AND OLD.durum IS DISTINCT FROM NEW.durum)
    EXECUTE FUNCTION dose_private.siparis_stok_baglantisini_sakla();
REVOKE ALL ON FUNCTION dose_private.siparis_stok_baglantisini_sakla() FROM PUBLIC, anon, authenticated;

ALTER TABLE public.fatura
    ALTER COLUMN matrah TYPE NUMERIC USING matrah::NUMERIC,
    ALTER COLUMN kdv TYPE NUMERIC USING kdv::NUMERIC,
    ALTER COLUMN tevkif_kdv TYPE NUMERIC USING tevkif_kdv::NUMERIC,
    ALTER COLUMN stopaj_orani TYPE NUMERIC USING stopaj_orani::NUMERIC,
    ALTER COLUMN stopaj TYPE NUMERIC USING stopaj::NUMERIC,
    ALTER COLUMN genel_toplam TYPE NUMERIC USING genel_toplam::NUMERIC,
    ALTER COLUMN net_tutar TYPE NUMERIC USING net_tutar::NUMERIC,
    ALTER COLUMN iskonto TYPE NUMERIC USING iskonto::NUMERIC,
    ADD COLUMN tevkifat_orani NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN tevkifat_hesabi TEXT,
    ADD COLUMN stopaj_hesabi TEXT,
    ADD COLUMN istek_id UUID,
    ADD COLUMN olusturan UUID REFERENCES auth.users(id);
ALTER TABLE public.fatura_kalem
    ALTER COLUMN miktar TYPE NUMERIC USING miktar::NUMERIC,
    ALTER COLUMN birim_fiyat TYPE NUMERIC USING birim_fiyat::NUMERIC,
    ALTER COLUMN kdv_orani TYPE NUMERIC USING kdv_orani::NUMERIC,
    ALTER COLUMN tutar TYPE NUMERIC USING tutar::NUMERIC,
    ALTER COLUMN kdv TYPE NUMERIC USING kdv::NUMERIC,
    ALTER COLUMN iskonto TYPE NUMERIC USING iskonto::NUMERIC,
    ALTER COLUMN iskonto_orani TYPE NUMERIC USING iskonto_orani::NUMERIC,
    ADD COLUMN siparis_kalem_id INTEGER REFERENCES public.siparis_kalem(id),
    ADD COLUMN brut NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN hesap_kodu TEXT,
    ADD COLUMN stok_maliyeti NUMERIC,
    ADD COLUMN stok_maliyet_hesabi TEXT;
CREATE UNIQUE INDEX fatura_istek_tek ON public.fatura(okul_id, istek_id) WHERE istek_id IS NOT NULL;
CREATE UNIQUE INDEX fatura_satis_belge_tek ON public.fatura(okul_id, lower(btrim(belge_no))) WHERE tur = 'Satış';
CREATE UNIQUE INDEX fatura_alis_belge_tek ON public.fatura(okul_id, cari_id, lower(btrim(belge_no))) WHERE tur = 'Alış';
CREATE INDEX fatura_kalem_siparis ON public.fatura_kalem(okul_id, siparis_kalem_id);

CREATE TABLE dose_private.fatura_iptal (
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    fatura_id INTEGER NOT NULL REFERENCES public.fatura(id),
    tarih DATE NOT NULL, gerekce TEXT NOT NULL, istek_id UUID NOT NULL,
    olusturan UUID NOT NULL REFERENCES auth.users(id),
    PRIMARY KEY (okul_id, fatura_id), UNIQUE (okul_id, istek_id)
);
REVOKE ALL ON dose_private.fatura_iptal FROM PUBLIC, anon, authenticated;
CREATE TRIGGER dose_fatura_iptal_degismez BEFORE UPDATE OR DELETE ON dose_private.fatura_iptal
    FOR EACH ROW EXECUTE FUNCTION dose_private.finans_kaydi_degismez();

CREATE OR REPLACE FUNCTION dose_private.fatura_degismez() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.iptal = 0 AND NEW.iptal = 1
       AND (to_jsonb(OLD) - 'iptal') = (to_jsonb(NEW) - 'iptal')
       AND EXISTS (SELECT 1 FROM dose_private.fatura_iptal WHERE okul_id = OLD.okul_id AND fatura_id = OLD.id) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Fatura değiştirilemez veya silinemez; gerekçeli ters kayıt oluşturun.';
END;
$$;
CREATE TRIGGER dose_fatura_degismez BEFORE UPDATE OR DELETE ON public.fatura
    FOR EACH ROW EXECUTE FUNCTION dose_private.fatura_degismez();
CREATE TRIGGER dose_fatura_kalem_degismez BEFORE UPDATE OR DELETE ON public.fatura_kalem
    FOR EACH ROW EXECUTE FUNCTION dose_private.finans_kaydi_degismez();
REVOKE ALL ON FUNCTION dose_private.fatura_degismez() FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION dose_private.fatura_hesapla(
    p_tur TEXT, p_belge_no TEXT, p_tarih DATE, p_cari INTEGER, p_siparis INTEGER, p_kalemler JSONB,
    p_tevkifat NUMERIC, p_stopaj NUMERIC, p_vergi_surumleri JSONB
) RETURNS JSONB LANGUAGE plpgsql VOLATILE SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_belge_no TEXT := nullif(btrim(p_belge_no), '');
    v_cari public.cari%ROWTYPE;
    v_siparis public.siparis%ROWTYPE;
    v_siparis_kalem public.siparis_kalem%ROWTYPE;
    v_malzeme public.malzeme%ROWTYPE;
    v_urun public.urun%ROWTYPE;
    v_kalem JSONB;
    v_satirlar JSONB := '[]'::JSONB;
    v_miktar NUMERIC; v_fiyat NUMERIC; v_iskonto_orani NUMERIC; v_kdv_orani NUMERIC;
    v_brut NUMERIC; v_iskonto NUMERIC; v_tutar NUMERIC; v_kdv NUMERIC;
    v_once_miktar NUMERIC; v_once_brut NUMERIC; v_once_iskonto NUMERIC; v_once_tutar NUMERIC; v_once_kdv NUMERIC;
    v_matrah NUMERIC := 0; v_toplam_kdv NUMERIC := 0; v_toplam_iskonto NUMERIC := 0;
    v_tevkif_kdv NUMERIC; v_stopaj NUMERIC;
    v_malzeme_id INTEGER; v_onayli_malzeme_id INTEGER; v_maliyet NUMERIC; v_maliyet_hesabi TEXT; v_hesap TEXT;
    v_tevkifat_turu TEXT; v_stopaj_turu TEXT;
    v_tevkifat_hesap dose_private.vergi_hesap%ROWTYPE; v_stopaj_hesap dose_private.vergi_hesap%ROWTYPE;
    v_sira INTEGER := 0;
BEGIN
    IF auth.uid() IS NULL OR public.dose_yetki('fatura') <> 'y' OR public.dose_rol() <> 'Sayman' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Faturayı yalnız etkin ve yetkili sayman kaydedebilir.';
    END IF;
    IF p_tur IS NULL OR p_tur NOT IN ('Satış', 'Alış') OR v_belge_no IS NULL OR length(v_belge_no) > 100
       OR p_tarih IS NULL OR p_tarih > (now() AT TIME ZONE 'Europe/Istanbul')::DATE
       OR jsonb_typeof(p_kalemler) IS DISTINCT FROM 'array'
       OR jsonb_array_length(p_kalemler) NOT BETWEEN 1 AND 100
       OR jsonb_typeof(p_vergi_surumleri) IS DISTINCT FROM 'object'
       OR p_tevkifat IS NULL OR p_stopaj IS NULL
       OR p_tevkifat::TEXT IN ('NaN', 'Infinity', '-Infinity')
       OR p_stopaj::TEXT IN ('NaN', 'Infinity', '-Infinity')
       OR p_tevkifat NOT BETWEEN 0 AND 1 OR p_stopaj NOT BETWEEN 0 AND 1 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Belge türü, numarası, tarihi, kalemleri ve geçerli vergi oranları gereklidir.';
    END IF;
    SELECT * INTO v_cari FROM public.cari WHERE okul_id = v_okul AND id = p_cari AND aktif = 1 FOR SHARE;
    IF NOT FOUND OR (p_tur = 'Satış' AND v_cari.tur NOT IN ('Müşteri', 'Müşteri ve Tedarikçi'))
       OR (p_tur = 'Alış' AND v_cari.tur NOT IN ('Tedarikçi', 'Müşteri ve Tedarikçi')) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Belge türüne uygun etkin cari seçiniz.';
    END IF;
    IF p_tur = 'Satış' THEN
        SELECT * INTO v_siparis FROM public.siparis WHERE okul_id = v_okul AND id = p_siparis FOR UPDATE;
        IF NOT FOUND OR v_siparis.cari_id IS DISTINCT FROM p_cari OR v_siparis.durum <> 'Sözleşme İmzalandı'
           OR NOT EXISTS (SELECT 1 FROM public.onay_durum WHERE okul_id = v_okul AND belge_turu = 'Sipariş'
                          AND belge_id = p_siparis AND durum = 'Onaylandı' AND asama > 3) THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu cariye ait, tüm aşamaları onaylanmış sipariş seçiniz.';
        END IF;
        IF p_tarih < v_siparis.tarih::DATE THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Fatura tarihi sipariş tarihinden önce olamaz.';
        END IF;
        IF (SELECT count(*) FROM jsonb_array_elements(p_kalemler)) <>
           (SELECT count(DISTINCT value->>'siparis_kalem_id') FROM jsonb_array_elements(p_kalemler)) THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Her sipariş kalemi faturada yalnız bir kez seçilebilir.';
        END IF;
    ELSIF p_siparis IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Alış belgesi satış siparişine bağlanamaz.';
    END IF;

    FOR v_kalem IN SELECT value FROM jsonb_array_elements(p_kalemler) LOOP
        v_sira := v_sira + 1;
        v_miktar := nullif(v_kalem->>'miktar', '')::NUMERIC;
        IF jsonb_typeof(v_kalem) IS DISTINCT FROM 'object' OR v_miktar IS NULL
           OR v_miktar::TEXT IN ('NaN', 'Infinity', '-Infinity') OR v_miktar <= 0 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. kalem için pozitif miktar gereklidir.', v_sira);
        END IF;
        v_malzeme_id := nullif(v_kalem->>'malzeme_id', '')::INTEGER;
        v_maliyet := NULL; v_maliyet_hesabi := NULL; v_hesap := NULL;
        IF p_tur = 'Satış' THEN
            SELECT * INTO v_siparis_kalem FROM public.siparis_kalem
            WHERE okul_id = v_okul AND siparis_id = v_siparis.id
              AND id = nullif(v_kalem->>'siparis_kalem_id', '')::INTEGER;
            IF NOT FOUND THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. sipariş kalemi bulunamadı.', v_sira);
            END IF;
            SELECT coalesce(sum(k.miktar), 0), coalesce(sum(k.brut), 0), coalesce(sum(k.iskonto), 0),
                   coalesce(sum(k.tutar), 0), coalesce(sum(k.kdv), 0)
              INTO v_once_miktar, v_once_brut, v_once_iskonto, v_once_tutar, v_once_kdv
            FROM public.fatura_kalem k JOIN public.fatura f ON f.okul_id = k.okul_id AND f.id = k.fatura_id
            WHERE k.okul_id = v_okul AND k.siparis_kalem_id = v_siparis_kalem.id AND f.iptal = 0;
            IF v_once_miktar + v_miktar > v_siparis_kalem.miktar THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. kalemde fatura miktarı siparişin kalanını aşıyor.', v_sira);
            END IF;
            v_fiyat := v_siparis_kalem.birim_fiyat;
            v_iskonto_orani := v_siparis_kalem.iskonto_orani;
            v_kdv_orani := v_siparis.kdv_orani;
            v_brut := round((v_once_miktar + v_miktar) * v_fiyat, 2) - v_once_brut;
            v_iskonto := round(round((v_once_miktar + v_miktar) * v_fiyat, 2) * v_iskonto_orani, 2) - v_once_iskonto;
            v_tutar := v_brut - v_iskonto;
            v_kdv := round((v_once_tutar + v_tutar) * v_kdv_orani, 2) - v_once_kdv;
            IF v_brut < 0 OR v_iskonto < 0 OR v_tutar < 0 OR v_kdv < 0 THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Önceki fatura yuvarlamaları tutarsız; kayıtları inceleyin.';
            END IF;
            IF v_siparis_kalem.urun_id IS NOT NULL THEN
                SELECT * INTO v_urun FROM public.urun WHERE okul_id = v_okul AND id = v_siparis_kalem.urun_id FOR SHARE;
                IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Siparişteki ürün bulunamadı.'; END IF;
            ELSE
                v_urun := NULL;
            END IF;
            IF v_siparis_kalem.stok_baglanti_kaynagi IS NULL THEN
                IF v_kalem->'eski_baglanti_onayi' IS DISTINCT FROM 'true'::JSONB THEN
                    RAISE EXCEPTION USING ERRCODE = 'P0001',
                        MESSAGE = 'Eski siparişin onay anındaki stok bağlantısı bilinmiyor; güncel bağlantıyı sayman doğrulamalıdır.';
                END IF;
                v_onayli_malzeme_id := v_urun.mamul_malzeme_id;
            ELSE
                v_onayli_malzeme_id := v_siparis_kalem.stok_malzeme_onay_id;
            END IF;
            IF v_malzeme_id IS DISTINCT FROM v_onayli_malzeme_id THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Siparişin stok bağlantısı değişti; faturayı yeniden hazırlayın.',
                    HINT = 'surum_cakismasi';
            END IF;
            IF v_malzeme_id IS NOT NULL THEN
                SELECT * INTO v_malzeme FROM public.malzeme WHERE okul_id = v_okul AND id = v_malzeme_id AND aktif = 1;
                IF NOT FOUND OR nullif(btrim(v_malzeme.birim), '') IS DISTINCT FROM nullif(btrim(v_siparis_kalem.birim), '') THEN
                    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Etkin stok kartının birimi sipariş kalemiyle eşleşmelidir.';
                END IF;
                v_maliyet := nullif(v_kalem->>'stok_maliyeti', '')::NUMERIC;
                v_maliyet_hesabi := nullif(btrim(v_kalem->>'stok_maliyet_hesabi'), '');
                v_hesap := CASE v_malzeme.tur WHEN 'İlk Madde ve Malzeme' THEN '150'
                           WHEN 'Yarı Mamul' THEN '151' WHEN 'Mamul' THEN '152' WHEN 'Ticari Mal' THEN '153' END;
                IF v_maliyet IS NULL OR v_maliyet::TEXT IN ('NaN', 'Infinity', '-Infinity')
                   OR v_maliyet < 0 OR v_maliyet <> round(v_maliyet, 2) OR v_hesap IS NULL
                   OR v_maliyet_hesabi IS NULL OR NOT dose_private.hesap_var(v_okul, v_maliyet_hesabi)
                   OR v_maliyet_hesabi = v_hesap THEN
                    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sayman stok maliyetini ve farklı, tanımlı maliyet hesabını seçmelidir.';
                END IF;
                IF v_maliyet_hesabi ~ '^(100|102)(\.|$)' THEN
                    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Kasa/banka hesabı stok maliyet hesabı olarak seçilemez.';
                END IF;
            END IF;
            v_satirlar := v_satirlar || jsonb_build_array(jsonb_build_object(
                'siparis_kalem_id', v_siparis_kalem.id, 'urun_id', v_siparis_kalem.urun_id,
                'stok_baglanti_kaynagi', coalesce(v_siparis_kalem.stok_baglanti_kaynagi, 'Sayman doğrulaması'),
                'malzeme_id', v_malzeme_id, 'aciklama', v_siparis_kalem.aciklama, 'birim', v_siparis_kalem.birim,
                'miktar', v_miktar::TEXT, 'birim_fiyat', v_fiyat::TEXT, 'iskonto_orani', v_iskonto_orani::TEXT,
                'kdv_orani', v_kdv_orani::TEXT, 'brut', v_brut::TEXT, 'iskonto', v_iskonto::TEXT,
                'tutar', v_tutar::TEXT, 'kdv', v_kdv::TEXT, 'hesap_kodu', v_hesap,
                'stok_maliyeti', v_maliyet::TEXT, 'stok_maliyet_hesabi', v_maliyet_hesabi));
        ELSE
            v_fiyat := nullif(v_kalem->>'birim_fiyat', '')::NUMERIC;
            v_iskonto_orani := nullif(v_kalem->>'iskonto_orani', '')::NUMERIC;
            v_kdv_orani := nullif(v_kalem->>'kdv_orani', '')::NUMERIC;
            IF nullif(btrim(v_kalem->>'aciklama'), '') IS NULL OR v_fiyat IS NULL OR v_iskonto_orani IS NULL
               OR v_kdv_orani IS NULL OR v_fiyat::TEXT IN ('NaN', 'Infinity', '-Infinity')
               OR v_iskonto_orani::TEXT IN ('NaN', 'Infinity', '-Infinity')
               OR v_kdv_orani::TEXT IN ('NaN', 'Infinity', '-Infinity')
               OR v_fiyat < 0 OR v_iskonto_orani NOT BETWEEN 0 AND 1 OR v_kdv_orani NOT BETWEEN 0 AND 1 THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. alış kaleminin açıklaması, fiyatı ve oranları geçersiz.', v_sira);
            END IF;
            v_brut := round(v_miktar * v_fiyat, 2);
            v_iskonto := round(v_brut * v_iskonto_orani, 2);
            v_tutar := v_brut - v_iskonto;
            v_kdv := round(v_tutar * v_kdv_orani, 2);
            IF v_malzeme_id IS NOT NULL THEN
                SELECT * INTO v_malzeme FROM public.malzeme WHERE okul_id = v_okul AND id = v_malzeme_id AND aktif = 1;
                IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Etkin alış stok kartı bulunamadı.'; END IF;
                v_hesap := CASE v_malzeme.tur WHEN 'İlk Madde ve Malzeme' THEN '150'
                           WHEN 'Yarı Mamul' THEN '151' WHEN 'Mamul' THEN '152' WHEN 'Ticari Mal' THEN '153' END;
                IF v_hesap IS NULL OR nullif(btrim(v_kalem->>'hesap_kodu'), '') IS NOT NULL THEN
                    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Stoklu alışta gider hesabı ayrıca seçilemez.';
                END IF;
            ELSE
                v_hesap := nullif(btrim(v_kalem->>'hesap_kodu'), '');
                IF v_hesap IS NULL OR NOT dose_private.hesap_var(v_okul, v_hesap)
                   OR v_hesap IN ('150', '151', '152', '153') THEN
                    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Stoksuz alış için tanımlı gider veya varlık hesabı seçiniz.';
                END IF;
                IF v_hesap ~ '^(100|102)(\.|$)' THEN
                    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Kasa/banka hesabı alış gideri veya varlık hesabı olarak seçilemez.';
                END IF;
            END IF;
            v_satirlar := v_satirlar || jsonb_build_array(jsonb_build_object(
                'siparis_kalem_id', NULL, 'urun_id', NULL, 'malzeme_id', v_malzeme_id,
                'aciklama', btrim(v_kalem->>'aciklama'),
                'birim', CASE WHEN v_malzeme_id IS NOT NULL THEN v_malzeme.birim ELSE nullif(btrim(v_kalem->>'birim'), '') END,
                'miktar', v_miktar::TEXT, 'birim_fiyat', v_fiyat::TEXT, 'iskonto_orani', v_iskonto_orani::TEXT,
                'kdv_orani', v_kdv_orani::TEXT, 'brut', v_brut::TEXT, 'iskonto', v_iskonto::TEXT,
                'tutar', v_tutar::TEXT, 'kdv', v_kdv::TEXT, 'hesap_kodu', v_hesap,
                'stok_maliyeti', NULL, 'stok_maliyet_hesabi', NULL));
        END IF;
        v_matrah := v_matrah + v_tutar;
        v_toplam_kdv := v_toplam_kdv + v_kdv;
        v_toplam_iskonto := v_toplam_iskonto + v_iskonto;
    END LOOP;
    IF v_matrah <= 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Fatura matrahı sıfırdan büyük olmalıdır.';
    END IF;
    v_tevkif_kdv := round(v_toplam_kdv * p_tevkifat, 2);
    v_stopaj := round(v_matrah * p_stopaj, 2);
    v_tevkifat_turu := p_tur || ' KDV tevkifatı';
    v_stopaj_turu := p_tur || ' stopajı';
    IF p_tevkifat > 0 THEN
        SELECT * INTO v_tevkifat_hesap FROM dose_private.vergi_hesap
        WHERE okul_id = v_okul AND tur = v_tevkifat_turu FOR SHARE;
        IF NOT FOUND OR (p_vergi_surumleri->>v_tevkifat_turu)::INTEGER IS DISTINCT FROM v_tevkifat_hesap.surum THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Tevkifat hesabı tanımlı değil veya değişti; güncel hesabı kontrol edin.',
                HINT = 'surum_cakismasi';
        END IF;
    END IF;
    IF p_stopaj > 0 THEN
        SELECT * INTO v_stopaj_hesap FROM dose_private.vergi_hesap
        WHERE okul_id = v_okul AND tur = v_stopaj_turu FOR SHARE;
        IF NOT FOUND OR (p_vergi_surumleri->>v_stopaj_turu)::INTEGER IS DISTINCT FROM v_stopaj_hesap.surum THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Stopaj hesabı tanımlı değil veya değişti; güncel hesabı kontrol edin.',
                HINT = 'surum_cakismasi';
        END IF;
    END IF;
    RETURN jsonb_build_object(
        'tur', p_tur, 'belge_no', v_belge_no, 'tarih', p_tarih::TEXT, 'cari_id', p_cari, 'cari_unvan', v_cari.unvan,
        'siparis_id', p_siparis, 'kalemler', v_satirlar, 'matrah', v_matrah::TEXT,
        'iskonto', v_toplam_iskonto::TEXT, 'kdv', v_toplam_kdv::TEXT,
        'tevkifat_orani', p_tevkifat::TEXT, 'tevkif_kdv', v_tevkif_kdv::TEXT,
        'tevkifat_hesabi', v_tevkifat_hesap.hesap_kodu, 'tevkifat_surumu', v_tevkifat_hesap.surum,
        'stopaj_orani', p_stopaj::TEXT, 'stopaj', v_stopaj::TEXT, 'stopaj_hesabi', v_stopaj_hesap.hesap_kodu,
        'stopaj_surumu', v_stopaj_hesap.surum, 'genel_toplam', (v_matrah + v_toplam_kdv)::TEXT,
        'net_tutar', (v_matrah + v_toplam_kdv - v_tevkif_kdv - v_stopaj)::TEXT);
END;
$$;
REVOKE ALL ON FUNCTION dose_private.fatura_hesapla(TEXT, TEXT, DATE, INTEGER, INTEGER, JSONB, NUMERIC, NUMERIC, JSONB)
    FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION dose_private.fatura_fis_satiri(p_satirlar JSONB, p_hesap TEXT, p_borc NUMERIC, p_alacak NUMERIC)
RETURNS JSONB LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
BEGIN
    IF p_borc IS NULL OR p_alacak IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yevmiye satır tutarı eksik.';
    END IF;
    IF p_borc = 0 AND p_alacak = 0 THEN RETURN p_satirlar; END IF;
    RETURN p_satirlar || jsonb_build_array(jsonb_build_object('hesap', p_hesap, 'borc', p_borc, 'alacak', p_alacak));
END;
$$;
REVOKE ALL ON FUNCTION dose_private.fatura_fis_satiri(JSONB, TEXT, NUMERIC, NUMERIC) FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.dose_fatura_onizle(
    p_tur TEXT, p_belge_no TEXT, p_tarih DATE, p_cari INTEGER, p_siparis INTEGER, p_kalemler JSONB,
    p_tevkifat NUMERIC, p_stopaj NUMERIC, p_vergi_surumleri JSONB
) RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_veri JSONB;
BEGIN
    v_veri := dose_private.fatura_hesapla(p_tur, p_belge_no, p_tarih, p_cari, p_siparis, p_kalemler,
                                          p_tevkifat, p_stopaj, p_vergi_surumleri);
    RETURN jsonb_build_object('detay', v_veri, 'imza', md5(v_veri::TEXT));
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_fatura_kaydet(
    p_tur TEXT, p_belge_no TEXT, p_tarih DATE, p_cari INTEGER, p_siparis INTEGER, p_kalemler JSONB,
    p_tevkifat NUMERIC, p_stopaj NUMERIC, p_vergi_surumleri JSONB, p_imza TEXT, p_istek UUID
) RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_veri JSONB; v_kalem JSONB; v_stok JSONB; v_fis_satirlar JSONB := '[]'::JSONB;
    v_fatura INTEGER; v_fis INTEGER; v_malzeme INTEGER; v_sira INTEGER := 0;
    v_matrah NUMERIC; v_kdv NUMERIC; v_tevkif_kdv NUMERIC; v_stopaj NUMERIC; v_net NUMERIC;
    v_tutar NUMERIC; v_maliyet NUMERIC; v_aciklama TEXT; v_kisit TEXT;
BEGIN
    IF auth.uid() IS NULL OR public.dose_yetki('fatura') <> 'y' OR public.dose_rol() <> 'Sayman' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Faturayı yalnız etkin ve yetkili sayman kaydedebilir.';
    END IF;
    IF p_istek IS NULL OR p_imza IS NULL OR p_imza !~ '^[0-9a-f]{32}$' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Önce faturayı önizleyin ve işlem kimliğini gönderin.';
    END IF;
    IF EXISTS (SELECT 1 FROM public.fatura WHERE okul_id = v_okul AND istek_id = p_istek) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu fatura daha önce kaydedildi; listeyi yenileyin.';
    END IF;
    v_veri := dose_private.fatura_hesapla(p_tur, p_belge_no, p_tarih, p_cari, p_siparis, p_kalemler,
                                          p_tevkifat, p_stopaj, p_vergi_surumleri);
    FOR v_malzeme IN
        SELECT DISTINCT (value->>'malzeme_id')::INTEGER AS id
        FROM jsonb_array_elements(v_veri->'kalemler') WHERE value->>'malzeme_id' IS NOT NULL ORDER BY id
    LOOP
        PERFORM 1 FROM public.malzeme WHERE okul_id = v_okul AND id = v_malzeme FOR UPDATE;
    END LOOP;
    v_veri := dose_private.fatura_hesapla(p_tur, p_belge_no, p_tarih, p_cari, p_siparis, p_kalemler,
                                          p_tevkifat, p_stopaj, p_vergi_surumleri);
    IF md5(v_veri::TEXT) <> p_imza THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Fatura verileri değişti; yeniden önizleyin.',
            HINT = 'surum_cakismasi';
    END IF;
    v_matrah := (v_veri->>'matrah')::NUMERIC;
    v_kdv := (v_veri->>'kdv')::NUMERIC;
    v_tevkif_kdv := (v_veri->>'tevkif_kdv')::NUMERIC;
    v_stopaj := (v_veri->>'stopaj')::NUMERIC;
    v_net := (v_veri->>'net_tutar')::NUMERIC;
    v_aciklama := format('%s faturası %s · %s', p_tur, v_veri->>'belge_no', v_veri->>'cari_unvan');
    BEGIN
        INSERT INTO public.fatura (
            okul_id, tur, belge_turu, belge_no, tarih, cari_id, siparis_id, aciklama, matrah, iskonto, kdv,
            tevkifat, tevkifat_orani, tevkif_kdv, tevkifat_hesabi, stopaj_turu, stopaj_orani, stopaj,
            stopaj_hesabi, genel_toplam, net_tutar, iptal, istek_id, olusturan)
        VALUES (v_okul, p_tur, 'Fatura', v_veri->>'belge_no', p_tarih::TEXT, p_cari, p_siparis, v_aciklama,
            v_matrah, (v_veri->>'iskonto')::NUMERIC, v_kdv,
            CASE WHEN p_tevkifat = 0 THEN 'Yok' ELSE 'Manuel oran' END, p_tevkifat, v_tevkif_kdv,
            v_veri->>'tevkifat_hesabi', CASE WHEN p_stopaj = 0 THEN 'Yok' ELSE 'Manuel oran' END,
            p_stopaj, v_stopaj, v_veri->>'stopaj_hesabi', (v_veri->>'genel_toplam')::NUMERIC, v_net, 0, p_istek, auth.uid())
        RETURNING id INTO v_fatura;
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS v_kisit = CONSTRAINT_NAME;
        IF v_kisit = 'fatura_istek_tek' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu fatura daha önce kaydedildi; listeyi yenileyin.';
        ELSIF v_kisit IN ('fatura_satis_belge_tek', 'fatura_alis_belge_tek') THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu belge numarası daha önce kullanıldı.';
        END IF;
        RAISE;
    END;
    IF p_tur = 'Satış' THEN
        v_fis_satirlar := dose_private.fatura_fis_satiri(v_fis_satirlar, '120', v_net, 0);
        v_fis_satirlar := dose_private.fatura_fis_satiri(v_fis_satirlar, '600', 0, v_matrah);
        v_fis_satirlar := dose_private.fatura_fis_satiri(v_fis_satirlar, '391', 0, v_kdv);
        v_fis_satirlar := dose_private.fatura_fis_satiri(v_fis_satirlar, v_veri->>'tevkifat_hesabi', v_tevkif_kdv, 0);
        v_fis_satirlar := dose_private.fatura_fis_satiri(v_fis_satirlar, v_veri->>'stopaj_hesabi', v_stopaj, 0);
    ELSE
        v_fis_satirlar := dose_private.fatura_fis_satiri(v_fis_satirlar, '191', v_kdv, 0);
        v_fis_satirlar := dose_private.fatura_fis_satiri(v_fis_satirlar, '320', 0, v_net);
        v_fis_satirlar := dose_private.fatura_fis_satiri(v_fis_satirlar, v_veri->>'tevkifat_hesabi', 0, v_tevkif_kdv);
        v_fis_satirlar := dose_private.fatura_fis_satiri(v_fis_satirlar, v_veri->>'stopaj_hesabi', 0, v_stopaj);
    END IF;
    FOR v_kalem IN SELECT value FROM jsonb_array_elements(v_veri->'kalemler') LOOP
        v_sira := v_sira + 1;
        v_tutar := (v_kalem->>'tutar')::NUMERIC;
        v_maliyet := (v_kalem->>'stok_maliyeti')::NUMERIC;
        IF p_tur = 'Satış' THEN
            UPDATE public.siparis_kalem SET stok_malzeme_onay_id = (v_kalem->>'malzeme_id')::INTEGER,
                stok_baglanti_kaynagi = 'Sayman doğrulaması'
            WHERE okul_id = v_okul AND id = (v_kalem->>'siparis_kalem_id')::INTEGER
              AND stok_baglanti_kaynagi IS NULL;
            IF FOUND THEN
                PERFORM dose_private.log(v_okul, 'Eski sipariş stok bağlantısı doğrulandı', 'siparis',
                    p_siparis, 'Onay anındaki bağlantı bilinmiyor; sayman güncel bağlantıyla faturalamayı doğruladı.',
                    NULL, jsonb_build_object('siparis_kalem_id', v_kalem->'siparis_kalem_id',
                                             'malzeme_id', v_kalem->'malzeme_id'));
            END IF;
        END IF;
        INSERT INTO public.fatura_kalem (
            okul_id, fatura_id, siparis_kalem_id, urun_id, malzeme_id, aciklama, miktar, birim, birim_fiyat,
            iskonto_orani, brut, iskonto, kdv_orani, tutar, kdv, hesap_kodu, stok_maliyeti, stok_maliyet_hesabi)
        VALUES (v_okul, v_fatura, (v_kalem->>'siparis_kalem_id')::INTEGER, (v_kalem->>'urun_id')::INTEGER,
            (v_kalem->>'malzeme_id')::INTEGER, v_kalem->>'aciklama', (v_kalem->>'miktar')::NUMERIC,
            v_kalem->>'birim', (v_kalem->>'birim_fiyat')::NUMERIC, (v_kalem->>'iskonto_orani')::NUMERIC,
            (v_kalem->>'brut')::NUMERIC, (v_kalem->>'iskonto')::NUMERIC, (v_kalem->>'kdv_orani')::NUMERIC,
            v_tutar, (v_kalem->>'kdv')::NUMERIC, v_kalem->>'hesap_kodu', v_maliyet, v_kalem->>'stok_maliyet_hesabi');
        IF p_tur = 'Alış' THEN
            v_fis_satirlar := dose_private.fatura_fis_satiri(v_fis_satirlar, v_kalem->>'hesap_kodu', v_tutar, 0);
        END IF;
        IF v_kalem->>'malzeme_id' IS NOT NULL THEN
            v_stok := dose_private.stok_isle(v_okul, (v_kalem->>'malzeme_id')::INTEGER, p_tarih,
                CASE WHEN p_tur = 'Satış' THEN 'Çıkış' ELSE 'Giriş' END,
                (v_kalem->>'miktar')::NUMERIC, CASE WHEN p_tur = 'Satış' THEN v_maliyet ELSE v_tutar END,
                'Fatura', v_aciklama, md5('fatura:' || p_istek::TEXT || ':' || v_sira::TEXT)::UUID, NULL, v_fatura);
            IF v_stok->>'hesap_kodu' IS DISTINCT FROM v_kalem->>'hesap_kodu' THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Stok hesabı değişti; faturayı yeniden hazırlayın.';
            END IF;
            IF p_tur = 'Satış' THEN
                v_fis_satirlar := dose_private.fatura_fis_satiri(v_fis_satirlar, v_kalem->>'stok_maliyet_hesabi', v_maliyet, 0);
                v_fis_satirlar := dose_private.fatura_fis_satiri(v_fis_satirlar, v_kalem->>'hesap_kodu', 0, v_maliyet);
            END IF;
        END IF;
    END LOOP;
    v_fis := dose_private.yevmiye_olustur(v_okul, p_tarih, v_aciklama, 'Fatura', v_fatura, v_fis_satirlar);
    PERFORM dose_private.log(v_okul, 'Fatura kaydedildi', 'fatura', v_fatura, v_aciklama, NULL,
                             jsonb_build_object('matrah', v_matrah, 'kdv', v_kdv, 'net_tutar', v_net, 'yevmiye_id', v_fis));
    RETURN jsonb_build_object('id', v_fatura, 'yevmiye_id', v_fis);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_fatura_secimleri() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul(); v_tanimlar JSONB;
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('fatura') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Fatura ekranına erişim yetkiniz yok.';
    END IF;
    v_tanimlar := public.dose_finans_tanimlari();
    RETURN jsonb_build_object(
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
        'id', f.id, 'tur', f.tur, 'belge_no', f.belge_no, 'tarih', f.tarih, 'cari_id', f.cari_id,
        'cari_unvan', c.unvan, 'siparis_id', f.siparis_id, 'iptal', f.iptal,
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

CREATE OR REPLACE FUNCTION public.dose_fatura_tersle(p_fatura INTEGER, p_gerekce TEXT, p_istek UUID)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); v_fatura public.fatura%ROWTYPE; v_hareket public.stok_hareket%ROWTYPE;
    v_fis public.yevmiye%ROWTYPE; v_yeni_fis INTEGER; v_satirlar JSONB; v_malzeme INTEGER;
    v_neden TEXT := nullif(btrim(p_gerekce), ''); v_tarih DATE := (now() AT TIME ZONE 'Europe/Istanbul')::DATE;
BEGIN
    IF auth.uid() IS NULL OR public.dose_yetki('fatura') <> 'y' OR public.dose_rol() <> 'Sayman' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Faturayı yalnız etkin ve yetkili sayman tersleyebilir.';
    END IF;
    IF v_neden IS NULL OR p_istek IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ters kayıt gerekçesi ve işlem kimliği zorunludur.';
    END IF;
    SELECT * INTO v_fatura FROM public.fatura WHERE okul_id = v_okul AND id = p_fatura FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Fatura bulunamadı.'; END IF;
    IF v_fatura.iptal <> 0 THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Fatura daha önce terslendi.'; END IF;
    IF EXISTS (SELECT 1 FROM public.kasa_banka k
               WHERE k.okul_id = v_okul AND k.fatura_id = v_fatura.id AND k.ters_hareket_id IS NULL
                 AND NOT EXISTS (SELECT 1 FROM public.kasa_banka t
                                 WHERE t.okul_id = k.okul_id AND t.ters_hareket_id = k.id)) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Faturaya bağlı açık ödeme veya tahsilat var; önce onları tersleyin.';
    END IF;
    IF v_fatura.siparis_id IS NOT NULL THEN
        PERFORM 1 FROM public.siparis WHERE okul_id = v_okul AND id = v_fatura.siparis_id FOR UPDATE;
        IF EXISTS (
            SELECT 1 FROM public.fatura_kalem k JOIN public.fatura_kalem yeni
              ON yeni.okul_id = k.okul_id AND yeni.siparis_kalem_id = k.siparis_kalem_id
            JOIN public.fatura f ON f.okul_id = yeni.okul_id AND f.id = yeni.fatura_id
            WHERE k.okul_id = v_okul AND k.fatura_id = v_fatura.id AND k.siparis_kalem_id IS NOT NULL
              AND f.id > v_fatura.id AND f.iptal = 0
        ) THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Aynı sipariş kaleminde daha yeni faturalar var; önce onları tersleyin.';
        END IF;
    END IF;
    FOR v_malzeme IN SELECT DISTINCT malzeme_id FROM public.stok_hareket
        WHERE okul_id = v_okul AND kaynak = 'Fatura' AND kaynak_id = v_fatura.id ORDER BY malzeme_id
    LOOP
        PERFORM 1 FROM public.malzeme WHERE okul_id = v_okul AND id = v_malzeme FOR UPDATE;
    END LOOP;
    FOR v_hareket IN SELECT * FROM public.stok_hareket
        WHERE okul_id = v_okul AND kaynak = 'Fatura' AND kaynak_id = v_fatura.id ORDER BY malzeme_id, id DESC
    LOOP
        IF EXISTS (SELECT 1 FROM public.stok_hareket s
                   WHERE s.okul_id = v_okul AND s.malzeme_id = v_hareket.malzeme_id AND s.id > v_hareket.id
                     AND s.ters_hareket_id IS NULL
                     AND NOT EXISTS (SELECT 1 FROM public.stok_hareket t
                                     WHERE t.okul_id = v_okul AND t.ters_hareket_id = s.id)) THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Fatura stok kartında daha yeni açık hareketler var; önce onları tersleyin.';
        END IF;
        PERFORM dose_private.stok_isle(v_okul, v_hareket.malzeme_id, v_tarih,
            CASE v_hareket.yon WHEN 'Giriş' THEN 'Çıkış' ELSE 'Giriş' END,
            v_hareket.miktar, v_hareket.toplam_tutar, 'Fatura ters kayıt', v_neden,
            md5('fatura-ters:' || p_istek::TEXT || ':' || v_hareket.id::TEXT)::UUID, v_hareket.id, v_fatura.id);
    END LOOP;
    SELECT * INTO v_fis FROM public.yevmiye WHERE okul_id = v_okul AND kaynak = 'Fatura' AND kaynak_id = v_fatura.id;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Faturanın yevmiye fişi bulunamadı.'; END IF;
    SELECT jsonb_agg(jsonb_build_object('hesap', hesap_kodu, 'borc', alacak, 'alacak', borc) ORDER BY id)
      INTO v_satirlar FROM public.yevmiye_satir WHERE okul_id = v_okul AND yevmiye_id = v_fis.id;
    v_yeni_fis := dose_private.yevmiye_olustur(v_okul, v_tarih, v_neden, 'Fatura ters kayıt', v_fatura.id, v_satirlar);
    INSERT INTO dose_private.fatura_iptal (okul_id, fatura_id, tarih, gerekce, istek_id, olusturan)
    VALUES (v_okul, v_fatura.id, v_tarih, v_neden, p_istek, auth.uid());
    UPDATE public.fatura SET iptal = 1 WHERE okul_id = v_okul AND id = v_fatura.id;
    PERFORM dose_private.log(v_okul, 'Fatura terslendi', 'fatura', v_fatura.id, v_neden, NULL,
                             jsonb_build_object('yevmiye_id', v_yeni_fis, 'tarih', v_tarih));
    RETURN jsonb_build_object('id', v_fatura.id, 'yevmiye_id', v_yeni_fis);
END;
$$;

REVOKE ALL ON FUNCTION public.dose_fatura_onizle(TEXT, TEXT, DATE, INTEGER, INTEGER, JSONB, NUMERIC, NUMERIC, JSONB),
    public.dose_fatura_kaydet(TEXT, TEXT, DATE, INTEGER, INTEGER, JSONB, NUMERIC, NUMERIC, JSONB, TEXT, UUID),
    public.dose_fatura_tersle(INTEGER, TEXT, UUID), public.dose_fatura_secimleri(), public.dose_faturalar()
    FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_fatura_onizle(TEXT, TEXT, DATE, INTEGER, INTEGER, JSONB, NUMERIC, NUMERIC, JSONB),
    public.dose_fatura_kaydet(TEXT, TEXT, DATE, INTEGER, INTEGER, JSONB, NUMERIC, NUMERIC, JSONB, TEXT, UUID),
    public.dose_fatura_tersle(INTEGER, TEXT, UUID), public.dose_fatura_secimleri(), public.dose_faturalar()
    TO authenticated;
