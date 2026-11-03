-- Hazine payı (Döner Sermaye Yönergesi; Tebliğ md.6-7): aylık gayrisafi hasılattan fiilen tahsil edilen tutarın
-- %1'i, izleyen ayın 20'sine kadar bildirim (Örnek No:30) ve banka ödemesi. Süresinde ödenmeyen tutar için her ay
-- %1 gecikme bilgisi verilir. Aynı ekranda aylık KDV (28) ve muhtasar (26) yükümlülükleri yevmiyeden izlenir.

INSERT INTO dose_private.sayfa_yetki (sayfa, baslik, kodlar)
VALUES ('hazine_payi', 'Hazine Payı ve Vergi Takvimi', 'gggy---g')
ON CONFLICT (sayfa) DO UPDATE SET baslik = EXCLUDED.baslik, kodlar = EXCLUDED.kodlar;

CREATE TABLE dose_private.hp_donem (
    id SERIAL PRIMARY KEY,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    bildirim_no TEXT NOT NULL,
    yil INTEGER NOT NULL CHECK (yil BETWEEN 2000 AND 2100),
    ay INTEGER NOT NULL CHECK (ay BETWEEN 1 AND 12),
    hasilat NUMERIC NOT NULL CHECK (hasilat > 0 AND hasilat = round(hasilat, 2)),
    oran NUMERIC NOT NULL CHECK (oran > 0 AND oran <= 0.1),
    tutar NUMERIC NOT NULL CHECK (tutar > 0 AND tutar = round(tutar, 2)),
    bildirim_tarihi DATE NOT NULL,
    son_odeme DATE NOT NULL,
    durum TEXT NOT NULL DEFAULT 'Bildirildi' CHECK (durum IN ('Bildirildi', 'İptal')),
    aciklama TEXT CHECK (length(aciklama) <= 500),
    iptal_gerekcesi TEXT CHECK (length(iptal_gerekcesi) <= 500),
    yevmiye_id INTEGER,
    ters_yevmiye_id INTEGER,
    surum INTEGER NOT NULL DEFAULT 1,
    olusturan UUID NOT NULL REFERENCES auth.users(id),
    olusturma TEXT NOT NULL DEFAULT dose_private.zaman(),
    istek_id UUID NOT NULL,
    CONSTRAINT hp_istek_tek UNIQUE (okul_id, istek_id),
    CONSTRAINT hp_no_tek UNIQUE (okul_id, bildirim_no)
);
CREATE UNIQUE INDEX hp_donem_tek ON dose_private.hp_donem(okul_id, yil, ay) WHERE durum <> 'İptal';
ALTER TABLE dose_private.hp_donem ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON dose_private.hp_donem FROM PUBLIC, anon, authenticated;

ALTER TABLE public.kasa_banka ADD COLUMN hp_donem_id INTEGER REFERENCES dose_private.hp_donem(id);
CREATE INDEX kasa_hp_indeks ON public.kasa_banka(okul_id, hp_donem_id) WHERE hp_donem_id IS NOT NULL;

-- ------------------------------------------------------------------ yardımcılar
-- Satış faturalarından p_son tarihine kadar fiilen tahsil edilen tutarın KDV hariç (matrah) karşılığı. Her fatura
-- için kümülatif tahsilat oranı kuruşa yuvarlanır; böylece fatura tamamen tahsil edildiğinde aylar toplamı matraha eşittir.
CREATE OR REPLACE FUNCTION dose_private.hp_kumulatif(p_okul INTEGER, p_son DATE) RETURNS NUMERIC
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT coalesce(sum(round(t.odenen * f.matrah / f.net_tutar, 2)), 0)
    FROM (SELECT k.fatura_id, sum(CASE WHEN k.ters_hareket_id IS NULL THEN k.tutar ELSE -k.tutar END) AS odenen
          FROM public.kasa_banka k
          WHERE k.okul_id = p_okul AND k.fatura_id IS NOT NULL AND k.tarih::DATE <= p_son
          GROUP BY k.fatura_id) t
    JOIN public.fatura f ON f.okul_id = p_okul AND f.id = t.fatura_id
    WHERE f.tur = 'Satış' AND f.net_tutar > 0
$$;

CREATE OR REPLACE FUNCTION dose_private.hp_hasilat(p_okul INTEGER, p_yil INTEGER, p_ay INTEGER) RETURNS NUMERIC
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT dose_private.hp_kumulatif(p_okul, (make_date(p_yil, p_ay, 1) + INTERVAL '1 month - 1 day')::DATE)
         - dose_private.hp_kumulatif(p_okul, (make_date(p_yil, p_ay, 1) - 1))
$$;

-- p_hesap kodlu (ve alt) hesapların ay içindeki alacak - borç farkı.
CREATE OR REPLACE FUNCTION dose_private.hp_hesap_net(p_okul INTEGER, p_yil INTEGER, p_ay INTEGER, p_hesap TEXT)
RETURNS NUMERIC LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT coalesce(sum(s.alacak - s.borc), 0)
    FROM public.yevmiye_satir s
    JOIN public.yevmiye y ON y.okul_id = s.okul_id AND y.id = s.yevmiye_id
    WHERE s.okul_id = p_okul AND (s.hesap_kodu = p_hesap OR s.hesap_kodu LIKE p_hesap || '.%')
      AND y.tarih::DATE BETWEEN make_date(p_yil, p_ay, 1) AND (make_date(p_yil, p_ay, 1) + INTERVAL '1 month - 1 day')::DATE
$$;

CREATE OR REPLACE FUNCTION dose_private.hp_odeme(p_okul INTEGER, p_donem INTEGER) RETURNS JSONB
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT jsonb_build_object('id', k.id, 'tarih', k.tarih, 'tutar', k.tutar::TEXT, 'belge_no', k.belge_no)
    FROM public.kasa_banka k
    WHERE k.okul_id = p_okul AND k.hp_donem_id = p_donem AND k.ters_hareket_id IS NULL
      AND NOT EXISTS (SELECT 1 FROM public.kasa_banka t WHERE t.okul_id = k.okul_id AND t.ters_hareket_id = k.id)
    ORDER BY k.id DESC LIMIT 1
$$;

-- Son ödeme tarihinden sonra başlayan her ay için %1 gecikme (bilgi amaçlı; sorumlulara yarı yarıya rücu edilir).
CREATE OR REPLACE FUNCTION dose_private.hp_gecikme_ay(p_son DATE, p_tarih DATE) RETURNS INTEGER
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
    SELECT CASE WHEN p_tarih <= p_son THEN 0 ELSE
        (extract(year FROM age(p_tarih, p_son)) * 12 + extract(month FROM age(p_tarih, p_son))
         + CASE WHEN extract(day FROM age(p_tarih, p_son)) > 0 THEN 1 ELSE 0 END)::INTEGER END
$$;

-- ------------------------------------------------------------------ veri
CREATE OR REPLACE FUNCTION public.dose_hp_veri(p_yil INTEGER DEFAULT NULL) RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); v_bugun DATE := (now() AT TIME ZONE 'Europe/Istanbul')::DATE;
    v_yil INTEGER; v_son_ay INTEGER; v_aylar JSONB := '[]'::JSONB; v_ay INTEGER; v_kayit dose_private.hp_donem%ROWTYPE;
    v_odeme JSONB; v_hasilat NUMERIC; v_son DATE; v_gecikme INTEGER; v_kdv NUMERIC; v_durum TEXT; v_tamam BOOLEAN;
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('hazine_payi') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Hazine payı ekranına erişim yetkiniz yok.';
    END IF;
    v_yil := coalesce(p_yil, extract(year FROM v_bugun)::INTEGER);
    IF v_yil < 2000 OR v_yil > extract(year FROM v_bugun) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Geçerli bir yıl seçiniz.';
    END IF;
    v_son_ay := CASE WHEN v_yil = extract(year FROM v_bugun) THEN extract(month FROM v_bugun)::INTEGER ELSE 12 END;
    FOR v_ay IN 1..v_son_ay LOOP
        v_kayit := NULL; v_odeme := NULL;
        SELECT * INTO v_kayit FROM dose_private.hp_donem
        WHERE okul_id = v_okul AND yil = v_yil AND ay = v_ay AND durum <> 'İptal';
        IF v_kayit.id IS NOT NULL THEN v_odeme := dose_private.hp_odeme(v_okul, v_kayit.id); END IF;
        v_hasilat := dose_private.hp_hasilat(v_okul, v_yil, v_ay);
        v_son := (make_date(v_yil, v_ay, 1) + INTERVAL '1 month 19 days')::DATE;
        v_tamam := make_date(v_yil, v_ay, 1) + INTERVAL '1 month' <= v_bugun;
        v_gecikme := CASE
            WHEN v_kayit.id IS NULL THEN dose_private.hp_gecikme_ay(v_son, v_bugun)
            WHEN v_odeme IS NULL THEN dose_private.hp_gecikme_ay(v_son, v_bugun)
            ELSE dose_private.hp_gecikme_ay(v_son, (v_odeme->>'tarih')::DATE) END;
        v_durum := CASE
            WHEN NOT v_tamam THEN 'Ay devam ediyor'
            WHEN v_kayit.id IS NULL AND v_hasilat <= 0 THEN 'Hasılat yok'
            WHEN v_kayit.id IS NULL THEN CASE WHEN v_gecikme > 0 THEN 'Gecikmiş' ELSE 'Bildirilecek' END
            WHEN v_odeme IS NULL THEN CASE WHEN v_gecikme > 0 THEN 'Gecikmiş' ELSE 'Ödenecek' END
            ELSE 'Ödendi' END;
        v_kdv := dose_private.hp_hesap_net(v_okul, v_yil, v_ay, '391') + dose_private.hp_hesap_net(v_okul, v_yil, v_ay, '191');
        v_aylar := v_aylar || jsonb_build_object(
            'yil', v_yil, 'ay', v_ay, 'tamamlandi', v_tamam, 'durum', v_durum,
            'hasilat', v_hasilat::TEXT,
            'tahmini_tutar', round(greatest(v_hasilat, 0) * 0.01, 2)::TEXT,
            'son_odeme', v_son, 'gecikme_ay', v_gecikme,
            'gecikme_tutari', round(coalesce(v_kayit.tutar, round(greatest(v_hasilat, 0) * 0.01, 2)) * 0.01 * v_gecikme, 2)::TEXT,
            'kayit', CASE WHEN v_kayit.id IS NULL THEN NULL ELSE jsonb_build_object(
                'id', v_kayit.id, 'bildirim_no', v_kayit.bildirim_no, 'hasilat', v_kayit.hasilat::TEXT,
                'oran', v_kayit.oran::TEXT, 'tutar', v_kayit.tutar::TEXT, 'bildirim_tarihi', v_kayit.bildirim_tarihi,
                'son_odeme', v_kayit.son_odeme, 'aciklama', v_kayit.aciklama, 'surum', v_kayit.surum,
                'yevmiye_id', v_kayit.yevmiye_id, 'hasilat_farki', (v_hasilat - v_kayit.hasilat)::TEXT,
                'odeme', v_odeme) END,
            'kdv', jsonb_build_object(
                'hesaplanan', dose_private.hp_hesap_net(v_okul, v_yil, v_ay, '391')::TEXT,
                'indirilecek', (-dose_private.hp_hesap_net(v_okul, v_yil, v_ay, '191'))::TEXT,
                'odenecek', greatest(v_kdv, 0)::TEXT, 'devreden', greatest(-v_kdv, 0)::TEXT,
                'son_gun', (make_date(v_yil, v_ay, 1) + INTERVAL '1 month 27 days')::DATE),
            'muhtasar', jsonb_build_object(
                'kesinti', dose_private.hp_hesap_net(v_okul, v_yil, v_ay, '360')::TEXT,
                'son_gun', (make_date(v_yil, v_ay, 1) + INTERVAL '1 month 25 days')::DATE));
    END LOOP;
    RETURN jsonb_build_object(
        'okul', (SELECT jsonb_build_object('ad', o.ad, 'kurum_kodu', o.kurum_kodu) FROM dose_private.okul o WHERE o.id = v_okul),
        'yil', v_yil, 'bugun', v_bugun, 'varsayilan_oran', '0.01', 'aylar', v_aylar,
        'iptaller', coalesce((SELECT jsonb_agg(jsonb_build_object('id', h.id, 'bildirim_no', h.bildirim_no, 'ay', h.ay,
            'tutar', h.tutar::TEXT, 'gerekce', h.iptal_gerekcesi) ORDER BY h.id)
            FROM dose_private.hp_donem h WHERE h.okul_id = v_okul AND h.yil = v_yil AND h.durum = 'İptal'), '[]'::JSONB),
        'banka_bakiye', dose_private.kasa_bakiye(v_okul, 'Banka (102)')::TEXT);
END;
$$;

-- ------------------------------------------------------------------ bildirim ve tahakkuk (770 / 362)
CREATE OR REPLACE FUNCTION public.dose_hp_bildir(p_yil INTEGER, p_ay INTEGER, p_oran NUMERIC, p_aciklama TEXT, p_istek UUID)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); v_bugun DATE := (now() AT TIME ZONE 'Europe/Istanbul')::DATE;
    v_aciklama TEXT := nullif(btrim(p_aciklama), ''); v_hasilat NUMERIC; v_tutar NUMERIC; v_id INTEGER;
    v_no TEXT; v_fis INTEGER; v_ay_sonu DATE; v_kisit TEXT;
BEGIN
    IF auth.uid() IS NULL OR public.dose_rol() <> 'Sayman' OR public.dose_yetki('hazine_payi') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Hazine payı bildirimini yalnız yetkili sayman yapabilir.';
    END IF;
    IF p_yil IS NULL OR p_ay IS NULL OR p_ay NOT BETWEEN 1 AND 12 OR p_yil NOT BETWEEN 2000 AND 2100
       OR p_oran IS NULL OR p_oran::TEXT IN ('NaN', 'Infinity', '-Infinity') OR p_oran <= 0 OR p_oran > 0.1
       OR length(v_aciklama) > 500 OR p_istek IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Geçerli dönem, oran (0-%10) ve işlem kimliği gereklidir.';
    END IF;
    v_ay_sonu := (make_date(p_yil, p_ay, 1) + INTERVAL '1 month - 1 day')::DATE;
    IF v_ay_sonu >= v_bugun THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yalnız tamamlanmış aylar için hazine payı bildirilebilir.';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtext('dose_hp'), v_okul);
    IF EXISTS (SELECT 1 FROM dose_private.hp_donem WHERE okul_id = v_okul AND istek_id = p_istek) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu bildirim daha önce kaydedildi; listeyi yenileyin.';
    END IF;
    IF EXISTS (SELECT 1 FROM dose_private.hp_donem WHERE okul_id = v_okul AND yil = p_yil AND ay = p_ay AND durum <> 'İptal') THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu ay için geçerli bir hazine payı bildirimi zaten var.';
    END IF;
    v_hasilat := dose_private.hp_hasilat(v_okul, p_yil, p_ay);
    v_tutar := round(v_hasilat * p_oran, 2);
    IF v_hasilat <= 0 OR v_tutar <= 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu ay tahsil edilen hasılat bulunmadığından bildirim gerekmez.';
    END IF;
    v_no := format('HP-%s-%s', p_yil, lpad(dose_private.sira_no(v_okul, 'hazine_payi', p_yil)::TEXT, 3, '0'));
    BEGIN
        INSERT INTO dose_private.hp_donem (okul_id, bildirim_no, yil, ay, hasilat, oran, tutar, bildirim_tarihi,
            son_odeme, aciklama, olusturan, istek_id)
        VALUES (v_okul, v_no, p_yil, p_ay, v_hasilat, p_oran, v_tutar, v_bugun,
            (make_date(p_yil, p_ay, 1) + INTERVAL '1 month 19 days')::DATE, v_aciklama, auth.uid(), p_istek)
        RETURNING id INTO v_id;
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS v_kisit = CONSTRAINT_NAME;
        IF v_kisit = 'hp_istek_tek' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu bildirim daha önce kaydedildi; listeyi yenileyin.';
        END IF;
        RAISE;
    END;
    v_fis := dose_private.yevmiye_olustur(v_okul, v_ay_sonu,
        format('%s %s/%s hazine payı tahakkuku (hasılat %s TL x %s)', v_no, lpad(p_ay::TEXT, 2, '0'), p_yil, v_hasilat, p_oran),
        'HazinePayi', v_id, jsonb_build_array(
            jsonb_build_object('hesap', '770', 'borc', v_tutar, 'alacak', 0),
            jsonb_build_object('hesap', '362', 'borc', 0, 'alacak', v_tutar)));
    UPDATE dose_private.hp_donem SET yevmiye_id = v_fis WHERE id = v_id;
    PERFORM dose_private.log(v_okul, 'Hazine payı bildirildi', 'hp_donem', v_id, v_no, NULL,
        jsonb_build_object('hasilat', v_hasilat::TEXT, 'oran', p_oran::TEXT, 'tutar', v_tutar::TEXT, 'yevmiye_id', v_fis));
    RETURN jsonb_build_object('id', v_id, 'bildirim_no', v_no, 'hasilat', v_hasilat::TEXT, 'tutar', v_tutar::TEXT,
        'yevmiye_id', v_fis, 'surum', 1);
END;
$$;

-- ------------------------------------------------------------------ iptal (ödenmemiş bildirim, ters yevmiye)
CREATE OR REPLACE FUNCTION public.dose_hp_iptal(p_id INTEGER, p_surum INTEGER, p_gerekce TEXT) RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); h dose_private.hp_donem%ROWTYPE;
    v_gerekce TEXT := nullif(btrim(p_gerekce), ''); v_satirlar JSONB; v_fis INTEGER;
BEGIN
    IF auth.uid() IS NULL OR public.dose_rol() <> 'Sayman' OR public.dose_yetki('hazine_payi') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Hazine payı bildirimini yalnız yetkili sayman iptal edebilir.';
    END IF;
    SELECT * INTO h FROM dose_private.hp_donem WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
    IF NOT FOUND OR h.durum <> 'Bildirildi' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İptal edilebilir hazine payı bildirimi bulunamadı.';
    END IF;
    IF p_surum IS DISTINCT FROM h.surum THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bildirim değiştirildi; güncelini yükleyin.', HINT = 'surum_cakismasi';
    END IF;
    IF v_gerekce IS NULL OR length(v_gerekce) > 500 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İptal gerekçesi zorunludur (en fazla 500 karakter).';
    END IF;
    PERFORM dose_private.kasa_kilitle(v_okul, 'Banka (102)');
    IF dose_private.hp_odeme(v_okul, h.id) IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ödenmiş bildirim iptal edilemez; önce ödemeyi tersleyin.';
    END IF;
    SELECT jsonb_agg(jsonb_build_object('hesap', hesap_kodu, 'borc', alacak, 'alacak', borc) ORDER BY id)
      INTO v_satirlar FROM public.yevmiye_satir WHERE okul_id = v_okul AND yevmiye_id = h.yevmiye_id;
    v_fis := dose_private.yevmiye_olustur(v_okul, (now() AT TIME ZONE 'Europe/Istanbul')::DATE,
        format('%s hazine payı bildirimi iptali: %s', h.bildirim_no, v_gerekce), 'HazinePayi ters kayıt', h.id, v_satirlar);
    UPDATE dose_private.hp_donem SET durum = 'İptal', iptal_gerekcesi = v_gerekce, ters_yevmiye_id = v_fis,
        surum = surum + 1 WHERE id = h.id;
    PERFORM dose_private.log(v_okul, 'Hazine payı bildirimi iptal edildi', 'hp_donem', h.id, v_gerekce, NULL,
        jsonb_build_object('ters_yevmiye_id', v_fis));
    RETURN jsonb_build_object('id', h.id, 'durum', 'İptal', 'surum', h.surum + 1, 'yevmiye_id', v_fis);
END;
$$;

-- ------------------------------------------------------------------ banka ödemesi (362 / 102)
CREATE OR REPLACE FUNCTION public.dose_hp_ode(p_id INTEGER, p_tarih DATE, p_belge_no TEXT, p_istek UUID)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); h dose_private.hp_donem%ROWTYPE; v_bakiye NUMERIC; v_son DATE;
    v_hareket INTEGER; v_fis INTEGER; v_kisit TEXT; v_belge TEXT := nullif(btrim(p_belge_no), ''); v_aciklama TEXT;
BEGIN
    IF auth.uid() IS NULL OR public.dose_rol() <> 'Sayman' OR public.dose_yetki('kasa') <> 'y'
       OR public.dose_yetki('hazine_payi') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Hazine payı ödemesini yalnız yetkili sayman yapabilir.';
    END IF;
    IF p_tarih IS NULL OR p_tarih > (now() AT TIME ZONE 'Europe/Istanbul')::DATE OR p_istek IS NULL
       OR length(v_belge) > 100 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Geçerli ödeme tarihi ve işlem kimliği gereklidir.';
    END IF;
    SELECT * INTO h FROM dose_private.hp_donem WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
    IF NOT FOUND OR h.durum <> 'Bildirildi' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yalnız geçerli bir hazine payı bildirimi ödenebilir.';
    END IF;
    PERFORM dose_private.kasa_kilitle(v_okul, 'Banka (102)');
    IF EXISTS (SELECT 1 FROM public.kasa_banka WHERE okul_id = v_okul AND istek_id = p_istek) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu ödeme daha önce kaydedildi; listeyi yenileyin.';
    END IF;
    IF dose_private.hp_odeme(v_okul, h.id) IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu hazine payı zaten ödendi.';
    END IF;
    IF p_tarih < h.bildirim_tarihi THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ödeme tarihi bildirim tarihinden önce olamaz.';
    END IF;
    SELECT max(tarih::DATE) INTO v_son FROM public.kasa_banka WHERE okul_id = v_okul AND hesap = 'Banka (102)';
    IF v_son IS NOT NULL AND p_tarih < v_son THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Son banka hareketinden daha eski tarihe kayıt yapılamaz.';
    END IF;
    v_bakiye := dose_private.kasa_bakiye(v_okul, 'Banka (102)');
    IF h.tutar > v_bakiye THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('Banka bakiyesi yetersiz (%s TL).', v_bakiye);
    END IF;
    v_aciklama := format('%s %s/%s hazine payı ödemesi', h.bildirim_no, lpad(h.ay::TEXT, 2, '0'), h.yil);
    BEGIN
        INSERT INTO public.kasa_banka (okul_id, tarih, hesap, yon, tur, tutar, hasilat_tutari, belge_no,
            aciklama, kaynak, karsi_hesap, istek_id, olusturan, hp_donem_id)
        VALUES (v_okul, p_tarih::TEXT, 'Banka (102)', 'Çıkış', 'Ödeme', h.tutar, 0, v_belge,
            v_aciklama, 'KasaBanka', '362', p_istek, auth.uid(), h.id) RETURNING id INTO v_hareket;
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS v_kisit = CONSTRAINT_NAME;
        IF v_kisit = 'kasa_istek_tek' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu ödeme daha önce kaydedildi; listeyi yenileyin.';
        END IF;
        RAISE;
    END;
    v_fis := dose_private.yevmiye_olustur(v_okul, p_tarih, v_aciklama, 'KasaBanka', v_hareket, jsonb_build_array(
        jsonb_build_object('hesap', '362', 'borc', h.tutar, 'alacak', 0),
        jsonb_build_object('hesap', '102', 'borc', 0, 'alacak', h.tutar)));
    PERFORM dose_private.log(v_okul, 'Hazine payı ödendi', 'kasa_banka', v_hareket, v_aciklama, NULL,
        jsonb_build_object('hp_donem_id', h.id, 'tutar', h.tutar::TEXT, 'yevmiye_id', v_fis,
            'gecikme_ay', dose_private.hp_gecikme_ay(h.son_odeme, p_tarih)));
    RETURN jsonb_build_object('id', v_hareket, 'yevmiye_id', v_fis, 'tutar', h.tutar::TEXT,
        'bakiye', (v_bakiye - h.tutar)::TEXT, 'gecikme_ay', dose_private.hp_gecikme_ay(h.son_odeme, p_tarih));
END;
$$;

REVOKE ALL ON FUNCTION dose_private.hp_kumulatif(INTEGER, DATE), dose_private.hp_hasilat(INTEGER, INTEGER, INTEGER),
    dose_private.hp_hesap_net(INTEGER, INTEGER, INTEGER, TEXT), dose_private.hp_odeme(INTEGER, INTEGER),
    dose_private.hp_gecikme_ay(DATE, DATE) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.dose_hp_veri(INTEGER), public.dose_hp_bildir(INTEGER, INTEGER, NUMERIC, TEXT, UUID),
    public.dose_hp_iptal(INTEGER, INTEGER, TEXT), public.dose_hp_ode(INTEGER, DATE, TEXT, UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_hp_veri(INTEGER), public.dose_hp_bildir(INTEGER, INTEGER, NUMERIC, TEXT, UUID),
    public.dose_hp_iptal(INTEGER, INTEGER, TEXT), public.dose_hp_ode(INTEGER, DATE, TEXT, UUID) TO authenticated;
