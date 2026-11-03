-- Invoice-linked cash and bank movements are immutable and always balanced.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.kasa_banka) THEN
        RAISE EXCEPTION 'Eski kasa/banka hareketleri var; kurulumdan önce kayıtları inceleyin.';
    END IF;
    IF EXISTS (SELECT 1 FROM public.yevmiye_satir WHERE hesap_kodu ~ '^(100|102)(\.|$)') THEN
        RAISE EXCEPTION 'Kasa/banka hesabını kullanan eski yevmiye satırları var; bakiyeleri kurulumdan önce inceleyin.';
    END IF;
END;
$$;

INSERT INTO dose_private.sayfa_yetki (sayfa, baslik, kodlar)
VALUES ('kasa', 'Kasa / Banka', 'gggy--gg')
ON CONFLICT (sayfa) DO UPDATE SET baslik = EXCLUDED.baslik, kodlar = EXCLUDED.kodlar;

ALTER TABLE public.kasa_banka
    ALTER COLUMN tutar TYPE NUMERIC USING tutar::NUMERIC,
    ALTER COLUMN hasilat_tutari TYPE NUMERIC USING hasilat_tutari::NUMERIC,
    ADD COLUMN istek_id UUID,
    ADD COLUMN karsi_hesap TEXT,
    ADD COLUMN olusturan UUID REFERENCES auth.users(id);
CREATE UNIQUE INDEX kasa_istek_tek ON public.kasa_banka(okul_id, istek_id) WHERE istek_id IS NOT NULL;
CREATE UNIQUE INDEX kasa_ters_tek ON public.kasa_banka(okul_id, ters_hareket_id) WHERE ters_hareket_id IS NOT NULL;
CREATE INDEX kasa_fatura_indeks ON public.kasa_banka(okul_id, fatura_id);

CREATE TABLE dose_private.kasa_kilit (
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    hesap TEXT NOT NULL CHECK (hesap IN ('Kasa (100)', 'Banka (102)')),
    PRIMARY KEY (okul_id, hesap)
);
REVOKE ALL ON dose_private.kasa_kilit FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION dose_private.kasa_kaydi_degismez() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE = '42501',
        MESSAGE = 'Kasa/banka hareketi değiştirilemez veya silinemez; gerekçeli ters kayıt oluşturun.';
END;
$$;
CREATE TRIGGER dose_kasa_degismez BEFORE UPDATE OR DELETE ON public.kasa_banka
    FOR EACH ROW EXECUTE FUNCTION dose_private.kasa_kaydi_degismez();

CREATE OR REPLACE FUNCTION dose_private.kasa_yevmiye_kontrol() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF NEW.hesap_kodu ~ '^(100|102)(\.|$)' AND NOT EXISTS (
        SELECT 1 FROM public.yevmiye y WHERE y.okul_id = NEW.okul_id AND y.id = NEW.yevmiye_id
          AND y.kaynak IN ('KasaBanka', 'KasaBanka ters kayıt')
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = '100 ve 102 kasa/banka hesapları yalnız kasa/banka hareketleriyle kullanılabilir.';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER dose_kasa_yevmiye_kontrol BEFORE INSERT ON public.yevmiye_satir
    FOR EACH ROW EXECUTE FUNCTION dose_private.kasa_yevmiye_kontrol();

CREATE OR REPLACE FUNCTION dose_private.kasa_kilitle(p_okul INTEGER, p_hesap TEXT) RETURNS VOID
LANGUAGE plpgsql VOLATILE SET search_path = '' AS $$
BEGIN
    INSERT INTO dose_private.kasa_kilit(okul_id, hesap) VALUES (p_okul, p_hesap)
    ON CONFLICT (okul_id, hesap) DO NOTHING;
    PERFORM 1 FROM dose_private.kasa_kilit WHERE okul_id = p_okul AND hesap = p_hesap FOR UPDATE;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.kasa_bakiye(p_okul INTEGER, p_hesap TEXT) RETURNS NUMERIC
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT coalesce(sum(CASE WHEN yon = 'Giriş' THEN tutar ELSE -tutar END), 0)
    FROM public.kasa_banka WHERE okul_id = p_okul AND hesap = p_hesap
$$;

CREATE OR REPLACE FUNCTION dose_private.fatura_odenen(p_okul INTEGER, p_fatura INTEGER) RETURNS NUMERIC
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT coalesce(sum(CASE WHEN ters_hareket_id IS NULL THEN tutar ELSE -tutar END), 0)
    FROM public.kasa_banka WHERE okul_id = p_okul AND fatura_id = p_fatura
$$;

CREATE OR REPLACE FUNCTION public.dose_kasa_kaydet(
    p_tur TEXT, p_hesap TEXT, p_tarih DATE, p_tutar NUMERIC, p_fatura INTEGER,
    p_karsi_hesap TEXT, p_belge_no TEXT, p_aciklama TEXT, p_istek UUID
) RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); v_fatura public.fatura%ROWTYPE;
    v_aciklama TEXT := nullif(btrim(p_aciklama), ''); v_belge_no TEXT := nullif(btrim(p_belge_no), '');
    v_nakit_hesap TEXT; v_karsi TEXT; v_yon TEXT; v_bakiye NUMERIC; v_kalan NUMERIC;
    v_son_tarih DATE; v_hareket INTEGER; v_fis INTEGER; v_kisit TEXT;
BEGIN
    IF auth.uid() IS NULL OR public.dose_rol() <> 'Sayman' OR public.dose_yetki('kasa') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Kasa/banka işlemlerini yalnız yetkili sayman kaydedebilir.';
    END IF;
    IF p_tur IS NULL OR p_tur NOT IN ('Açılış', 'Tahsilat', 'Ödeme')
       OR p_hesap IS NULL OR p_hesap NOT IN ('Kasa (100)', 'Banka (102)')
       OR p_tarih IS NULL OR p_tarih > (now() AT TIME ZONE 'Europe/Istanbul')::DATE
       OR p_tutar IS NULL OR p_tutar::TEXT IN ('NaN', 'Infinity', '-Infinity')
       OR p_tutar <= 0 OR p_tutar <> round(p_tutar, 2)
       OR v_aciklama IS NULL OR length(v_aciklama) > 500 OR length(v_belge_no) > 100 OR p_istek IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Geçerli hesap, tarih, pozitif kuruşlu tutar ve açıklama gereklidir.';
    END IF;
    IF EXISTS (SELECT 1 FROM public.kasa_banka WHERE okul_id = v_okul AND istek_id = p_istek) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu kasa/banka işlemi daha önce kaydedildi; listeyi yenileyin.';
    END IF;
    v_nakit_hesap := CASE p_hesap WHEN 'Kasa (100)' THEN '100' ELSE '102' END;
    IF p_tur = 'Açılış' THEN
        IF p_fatura IS NOT NULL OR p_karsi_hesap IS NULL OR NOT dose_private.hesap_var(v_okul, p_karsi_hesap)
           OR p_karsi_hesap ~ '^(100|102)(\.|$)' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Açılış için kasa/banka dışında tanımlı bir karşı hesap seçiniz.';
        END IF;
        v_yon := 'Giriş';
        v_karsi := p_karsi_hesap;
    ELSE
        SELECT * INTO v_fatura FROM public.fatura WHERE okul_id = v_okul AND id = p_fatura FOR UPDATE;
        IF NOT FOUND OR v_fatura.iptal <> 0 OR (p_tur = 'Tahsilat' AND v_fatura.tur <> 'Satış')
           OR (p_tur = 'Ödeme' AND v_fatura.tur <> 'Alış') OR p_karsi_hesap IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İşlem türüne uygun, açık bir fatura seçiniz.';
        END IF;
        IF p_tarih < v_fatura.tarih::DATE THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ödeme veya tahsilat tarihi fatura tarihinden önce olamaz.';
        END IF;
        v_kalan := v_fatura.net_tutar - dose_private.fatura_odenen(v_okul, v_fatura.id);
        IF p_tutar > v_kalan THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('Tutar, faturanın açık bakiyesini (%s TL) aşamaz.', v_kalan);
        END IF;
        v_yon := CASE WHEN p_tur = 'Tahsilat' THEN 'Giriş' ELSE 'Çıkış' END;
        v_karsi := CASE WHEN p_tur = 'Tahsilat' THEN '120' ELSE '320' END;
    END IF;
    PERFORM dose_private.kasa_kilitle(v_okul, p_hesap);
    SELECT max(tarih::DATE) INTO v_son_tarih FROM public.kasa_banka WHERE okul_id = v_okul AND hesap = p_hesap;
    IF v_son_tarih IS NOT NULL AND p_tarih < v_son_tarih THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Son kasa/banka hareketinden daha eski tarihe kayıt yapılamaz.';
    END IF;
    IF p_tur = 'Açılış' AND EXISTS (
        SELECT 1 FROM public.kasa_banka k WHERE k.okul_id = v_okul AND k.hesap = p_hesap
          AND k.ters_hareket_id IS NULL
          AND NOT EXISTS (SELECT 1 FROM public.kasa_banka t WHERE t.okul_id = k.okul_id AND t.ters_hareket_id = k.id)
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Açılış bakiyesi yalnız hesabın ilk açık hareketi olarak kaydedilebilir.';
    END IF;
    v_bakiye := dose_private.kasa_bakiye(v_okul, p_hesap);
    IF v_yon = 'Çıkış' AND p_tutar > v_bakiye THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s bakiyesi yetersiz (%s TL); eksi bakiyeye izin verilmez.', p_hesap, v_bakiye);
    END IF;
    BEGIN
        INSERT INTO public.kasa_banka (
            okul_id, tarih, hesap, yon, tur, tutar, hasilat_tutari, cari_id, fatura_id, siparis_id,
            belge_no, aciklama, kaynak, karsi_hesap, istek_id, olusturan)
        VALUES (v_okul, p_tarih::TEXT, p_hesap, v_yon, p_tur, p_tutar,
            CASE WHEN p_tur = 'Tahsilat' THEN NULL ELSE 0 END,
            v_fatura.cari_id, v_fatura.id, v_fatura.siparis_id, v_belge_no, v_aciklama,
            'KasaBanka', v_karsi, p_istek, auth.uid()) RETURNING id INTO v_hareket;
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS v_kisit = CONSTRAINT_NAME;
        IF v_kisit = 'kasa_istek_tek' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu kasa/banka işlemi daha önce kaydedildi; listeyi yenileyin.';
        END IF;
        RAISE;
    END;
    v_fis := dose_private.yevmiye_olustur(v_okul, p_tarih, v_aciklama, 'KasaBanka', v_hareket,
        jsonb_build_array(
            jsonb_build_object('hesap', v_nakit_hesap, 'borc', CASE WHEN v_yon = 'Giriş' THEN p_tutar ELSE 0 END,
                               'alacak', CASE WHEN v_yon = 'Çıkış' THEN p_tutar ELSE 0 END),
            jsonb_build_object('hesap', v_karsi, 'borc', CASE WHEN v_yon = 'Çıkış' THEN p_tutar ELSE 0 END,
                               'alacak', CASE WHEN v_yon = 'Giriş' THEN p_tutar ELSE 0 END)));
    PERFORM dose_private.log(v_okul, 'Kasa/banka hareketi kaydedildi', 'kasa_banka', v_hareket, v_aciklama, NULL,
        jsonb_build_object('tur', p_tur, 'hesap', p_hesap, 'tutar', p_tutar::TEXT, 'fatura_id', p_fatura, 'yevmiye_id', v_fis));
    RETURN jsonb_build_object('id', v_hareket, 'yevmiye_id', v_fis,
        'bakiye', (v_bakiye + CASE WHEN v_yon = 'Giriş' THEN p_tutar ELSE -p_tutar END)::TEXT,
        'fatura_kalan', CASE WHEN v_kalan IS NULL THEN NULL ELSE (v_kalan - p_tutar)::TEXT END);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_kasa_tersle(p_hareket INTEGER, p_gerekce TEXT, p_istek UUID)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); v_eski public.kasa_banka%ROWTYPE; v_fis public.yevmiye%ROWTYPE;
    v_neden TEXT := nullif(btrim(p_gerekce), ''); v_tarih DATE := (now() AT TIME ZONE 'Europe/Istanbul')::DATE;
    v_bakiye NUMERIC; v_hareket INTEGER; v_yeni_fis INTEGER; v_satirlar JSONB; v_kisit TEXT;
BEGIN
    IF auth.uid() IS NULL OR public.dose_rol() <> 'Sayman' OR public.dose_yetki('kasa') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Kasa/banka hareketini yalnız yetkili sayman tersleyebilir.';
    END IF;
    IF v_neden IS NULL OR length(v_neden) > 500 OR p_istek IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ters kayıt gerekçesi ve işlem kimliği zorunludur.';
    END IF;
    SELECT * INTO v_eski FROM public.kasa_banka WHERE okul_id = v_okul AND id = p_hareket;
    IF NOT FOUND OR v_eski.kaynak <> 'KasaBanka' OR v_eski.ters_hareket_id IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Terslenebilir kasa/banka hareketi bulunamadı.';
    END IF;
    IF v_eski.fatura_id IS NOT NULL THEN
        PERFORM 1 FROM public.fatura WHERE okul_id = v_okul AND id = v_eski.fatura_id FOR UPDATE;
    END IF;
    PERFORM dose_private.kasa_kilitle(v_okul, v_eski.hesap);
    IF EXISTS (SELECT 1 FROM public.kasa_banka WHERE okul_id = v_okul AND istek_id = p_istek) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu işlem daha önce kaydedildi; listeyi yenileyin.';
    END IF;
    IF EXISTS (SELECT 1 FROM public.kasa_banka WHERE okul_id = v_okul AND ters_hareket_id = v_eski.id) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu kasa/banka hareketi daha önce terslendi.';
    END IF;
    IF EXISTS (SELECT 1 FROM public.kasa_banka k
               WHERE k.okul_id = v_okul AND k.hesap = v_eski.hesap AND k.id > v_eski.id
                 AND k.ters_hareket_id IS NULL
                 AND NOT EXISTS (SELECT 1 FROM public.kasa_banka t WHERE t.okul_id = k.okul_id AND t.ters_hareket_id = k.id)) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu hesapta daha yeni açık hareketler var; önce onları tersleyin.';
    END IF;
    v_bakiye := dose_private.kasa_bakiye(v_okul, v_eski.hesap);
    IF v_eski.yon = 'Giriş' AND v_eski.tutar > v_bakiye THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ters kayıt hesabı eksiye düşürür; önce bakiyeyi inceleyin.';
    END IF;
    SELECT * INTO v_fis FROM public.yevmiye
    WHERE okul_id = v_okul AND kaynak = 'KasaBanka' AND kaynak_id = v_eski.id;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Hareketin yevmiye fişi bulunamadı.'; END IF;
    BEGIN
        INSERT INTO public.kasa_banka (
            okul_id, tarih, hesap, yon, tur, tutar, hasilat_tutari, cari_id, fatura_id, siparis_id,
            aciklama, kaynak, kaynak_id, karsi_hesap, istek_id, ters_hareket_id, olusturan)
        VALUES (v_okul, v_tarih::TEXT, v_eski.hesap, CASE WHEN v_eski.yon = 'Giriş' THEN 'Çıkış' ELSE 'Giriş' END,
            'Ters kayıt', v_eski.tutar, CASE WHEN v_eski.hasilat_tutari IS NULL THEN NULL ELSE 0 END,
            v_eski.cari_id, v_eski.fatura_id, v_eski.siparis_id, v_neden, 'KasaBanka ters kayıt',
            v_eski.id, v_eski.karsi_hesap, p_istek, v_eski.id, auth.uid()) RETURNING id INTO v_hareket;
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS v_kisit = CONSTRAINT_NAME;
        IF v_kisit = 'kasa_istek_tek' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu işlem daha önce kaydedildi; listeyi yenileyin.';
        ELSIF v_kisit = 'kasa_ters_tek' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu kasa/banka hareketi daha önce terslendi.';
        END IF;
        RAISE;
    END;
    SELECT jsonb_agg(jsonb_build_object('hesap', hesap_kodu, 'borc', alacak, 'alacak', borc) ORDER BY id)
      INTO v_satirlar FROM public.yevmiye_satir WHERE okul_id = v_okul AND yevmiye_id = v_fis.id;
    v_yeni_fis := dose_private.yevmiye_olustur(v_okul, v_tarih, v_neden, 'KasaBanka ters kayıt', v_hareket, v_satirlar);
    PERFORM dose_private.log(v_okul, 'Kasa/banka hareketi terslendi', 'kasa_banka', v_hareket, v_neden, NULL,
        jsonb_build_object('ters_hareket_id', v_eski.id, 'yevmiye_id', v_yeni_fis));
    RETURN jsonb_build_object('id', v_hareket, 'yevmiye_id', v_yeni_fis);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_kasa_veri() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul();
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('kasa') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Kasa/banka ekranına erişim yetkiniz yok.';
    END IF;
    RETURN jsonb_build_object(
        'hesaplar', jsonb_build_array(
            jsonb_build_object('hesap', 'Kasa (100)', 'bakiye', dose_private.kasa_bakiye(v_okul, 'Kasa (100)')::TEXT),
            jsonb_build_object('hesap', 'Banka (102)', 'bakiye', dose_private.kasa_bakiye(v_okul, 'Banka (102)')::TEXT)),
        'hesap_plani', coalesce((SELECT jsonb_agg(jsonb_build_object('kod', h.kod, 'ad', h.ad) ORDER BY h.kod)
            FROM (SELECT kod, ad FROM dose_private.hesap_standart UNION ALL
                  SELECT kod, ad FROM dose_private.hesap_ozel WHERE okul_id = v_okul) h
            WHERE h.kod !~ '^(100|102)(\.|$)'), '[]'::JSONB),
        'faturalar', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', f.id, 'tur', f.tur, 'belge_no', f.belge_no, 'tarih', f.tarih, 'cari_unvan', c.unvan,
            'net_tutar', f.net_tutar::TEXT, 'kalan', (f.net_tutar - dose_private.fatura_odenen(v_okul, f.id))::TEXT)
            ORDER BY f.id DESC)
            FROM public.fatura f JOIN public.cari c ON c.okul_id = f.okul_id AND c.id = f.cari_id
            WHERE f.okul_id = v_okul AND f.iptal = 0), '[]'::JSONB),
        'hareketler', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', k.id, 'tarih', k.tarih, 'hesap', k.hesap, 'yon', k.yon, 'tur', k.tur,
            'tutar', k.tutar::TEXT, 'hasilat_tutari', k.hasilat_tutari::TEXT,
            'fatura_id', k.fatura_id, 'fatura_no', f.belge_no, 'cari_unvan', c.unvan,
            'belge_no', k.belge_no, 'aciklama', k.aciklama, 'karsi_hesap', k.karsi_hesap,
            'ters_hareket_id', k.ters_hareket_id,
            'terslendi', EXISTS (SELECT 1 FROM public.kasa_banka t WHERE t.okul_id = k.okul_id AND t.ters_hareket_id = k.id))
            ORDER BY k.id DESC)
            FROM public.kasa_banka k LEFT JOIN public.fatura f ON f.okul_id = k.okul_id AND f.id = k.fatura_id
            LEFT JOIN public.cari c ON c.okul_id = k.okul_id AND c.id = k.cari_id
            WHERE k.okul_id = v_okul), '[]'::JSONB));
END;
$$;

REVOKE ALL ON FUNCTION dose_private.kasa_kaydi_degismez(), dose_private.kasa_yevmiye_kontrol(),
    dose_private.kasa_kilitle(INTEGER, TEXT), dose_private.kasa_bakiye(INTEGER, TEXT),
    dose_private.fatura_odenen(INTEGER, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.dose_kasa_kaydet(TEXT, TEXT, DATE, NUMERIC, INTEGER, TEXT, TEXT, TEXT, UUID),
    public.dose_kasa_tersle(INTEGER, TEXT, UUID), public.dose_kasa_veri() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_kasa_kaydet(TEXT, TEXT, DATE, NUMERIC, INTEGER, TEXT, TEXT, TEXT, UUID),
    public.dose_kasa_tersle(INTEGER, TEXT, UUID), public.dose_kasa_veri() TO authenticated;
