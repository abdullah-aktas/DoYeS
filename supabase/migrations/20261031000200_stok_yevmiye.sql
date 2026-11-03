-- Accounting amounts and stock movements are immutable; corrections append reversing entries.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.stok_hareket)
       OR EXISTS (SELECT 1 FROM public.yevmiye)
       OR EXISTS (SELECT 1 FROM public.yevmiye_satir) THEN
        RAISE EXCEPTION 'Eski stok veya yevmiye kayıtları var; çok okullu finans kurulumu öncesinde kayıtları inceleyin.';
    END IF;
END;
$$;

INSERT INTO dose_private.sayfa_yetki (sayfa, baslik, kodlar) VALUES
    ('stok', 'Stok Durumu ve Hareketleri', 'ygyyygyg'),
    ('yevmiye', 'Yevmiye / Mizan', 'yggy--gg'),
    ('vergi_hesap', 'Muhasebe Hesapları', 'gggy--gg')
ON CONFLICT (sayfa) DO UPDATE SET baslik = EXCLUDED.baslik, kodlar = EXCLUDED.kodlar;

ALTER TABLE public.stok_hareket
    ALTER COLUMN miktar TYPE NUMERIC USING miktar::NUMERIC,
    ALTER COLUMN birim_fiyat TYPE NUMERIC USING birim_fiyat::NUMERIC,
    ADD COLUMN IF NOT EXISTS toplam_tutar NUMERIC,
    ADD COLUMN IF NOT EXISTS istek_id UUID,
    ADD COLUMN IF NOT EXISTS ters_hareket_id INTEGER REFERENCES public.stok_hareket(id),
    ADD COLUMN IF NOT EXISTS olusturan UUID REFERENCES auth.users(id);
CREATE UNIQUE INDEX IF NOT EXISTS stok_hareket_istek_tek ON public.stok_hareket(okul_id, istek_id)
    WHERE istek_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS stok_hareket_ters_tek ON public.stok_hareket(okul_id, ters_hareket_id)
    WHERE ters_hareket_id IS NOT NULL;
ALTER TABLE public.yevmiye ADD COLUMN IF NOT EXISTS olusturan UUID REFERENCES auth.users(id);
ALTER TABLE public.yevmiye_satir
    ALTER COLUMN borc TYPE NUMERIC USING borc::NUMERIC,
    ALTER COLUMN alacak TYPE NUMERIC USING alacak::NUMERIC;

CREATE OR REPLACE FUNCTION dose_private.finans_kaydi_degismez() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Stok hareketi ve yevmiye kaydı değiştirilemez veya silinemez; ters kayıt oluşturun.';
END;
$$;
CREATE TRIGGER dose_stok_degismez BEFORE UPDATE OR DELETE ON public.stok_hareket
    FOR EACH ROW EXECUTE FUNCTION dose_private.finans_kaydi_degismez();
CREATE TRIGGER dose_yevmiye_degismez BEFORE UPDATE OR DELETE ON public.yevmiye
    FOR EACH ROW EXECUTE FUNCTION dose_private.finans_kaydi_degismez();
CREATE TRIGGER dose_yevmiye_satir_degismez BEFORE UPDATE OR DELETE ON public.yevmiye_satir
    FOR EACH ROW EXECUTE FUNCTION dose_private.finans_kaydi_degismez();

CREATE OR REPLACE FUNCTION dose_private.stok_kart_koruma() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF (NEW.tur IS DISTINCT FROM OLD.tur OR NEW.birim IS DISTINCT FROM OLD.birim)
       AND EXISTS (SELECT 1 FROM public.stok_hareket WHERE okul_id = OLD.okul_id AND malzeme_id = OLD.id) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Hareket görmüş stok kartının türü veya birimi değiştirilemez.';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER dose_stok_kart_koruma BEFORE UPDATE OF tur, birim ON public.malzeme
    FOR EACH ROW EXECUTE FUNCTION dose_private.stok_kart_koruma();
REVOKE ALL ON FUNCTION dose_private.stok_kart_koruma() FROM PUBLIC, anon, authenticated;

CREATE TABLE dose_private.hesap_standart (kod TEXT PRIMARY KEY, ad TEXT NOT NULL);
INSERT INTO dose_private.hesap_standart (kod, ad) VALUES
    ('100', 'Kasa Hesabı'), ('102', 'Banka Hesabı'), ('103', 'Verilen Çekler ve Gönderme Emirleri Hesabı'),
    ('120', 'Alıcılar Hesabı'), ('126', 'Verilen Depozito ve Teminatlar Hesabı'),
    ('150', 'İlk Madde ve Malzeme Hesabı'), ('151', 'Yarı Mamuller Hesabı'), ('152', 'Mamuller Hesabı'),
    ('153', 'Ticari Mallar Hesabı'), ('159', 'Verilen Sipariş Avansları Hesabı'),
    ('191', 'İndirilecek KDV Hesabı'), ('255', 'Demirbaşlar Hesabı'), ('320', 'Satıcılar Hesabı'),
    ('335', 'Personele Borçlar Hesabı'), ('340', 'Alınan Sipariş Avansları Hesabı'),
    ('360', 'Ödenecek Vergi ve Fonlar Hesabı'), ('361', 'Ödenecek Sosyal Güvenlik Kesintileri Hesabı'),
    ('362', 'Ödenecek Döner Sermaye Yükümlülükleri Hesabı'), ('391', 'Hesaplanan KDV Hesabı'),
    ('500', 'Sermaye Hesabı'), ('501', 'Ödenmemiş Sermaye Hesabı (-)'), ('570', 'Geçmiş Yıllar Kârları Hesabı'),
    ('590', 'Dönem Net Kârı Hesabı'), ('591', 'Dönem Net Zararı Hesabı (-)'),
    ('600', 'Yurtiçi Satışlar Hesabı'), ('610', 'Satıştan İadeler Hesabı (-)'),
    ('642', 'Faiz Gelirleri Hesabı'), ('649', 'Diğer Olağan Gelir ve Kârlar Hesabı'),
    ('710', 'Direkt İlk Madde ve Malzeme Giderleri Hesabı'), ('720', 'Direkt İşçilik Giderleri Hesabı'),
    ('730', 'Genel Üretim Giderleri Hesabı'), ('740', 'Hizmet Üretim Maliyeti Hesabı'),
    ('770', 'Genel Yönetim Giderleri Hesabı'), ('780', 'Finansman Giderleri Hesabı');
CREATE TABLE dose_private.hesap_ozel (
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    kod TEXT NOT NULL, ad TEXT NOT NULL, olusturan UUID NOT NULL REFERENCES auth.users(id),
    PRIMARY KEY (okul_id, kod)
);
CREATE TABLE dose_private.vergi_hesap (
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    tur TEXT NOT NULL CHECK (tur IN ('Satış KDV tevkifatı', 'Satış stopajı', 'Alış KDV tevkifatı', 'Alış stopajı')),
    hesap_kodu TEXT NOT NULL, surum INTEGER NOT NULL DEFAULT 1,
    guncelleyen UUID NOT NULL REFERENCES auth.users(id),
    PRIMARY KEY (okul_id, tur)
);
REVOKE ALL ON dose_private.hesap_standart, dose_private.hesap_ozel, dose_private.vergi_hesap
    FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION dose_private.hesap_var(p_okul INTEGER, p_kod TEXT) RETURNS BOOLEAN
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT EXISTS (SELECT 1 FROM dose_private.hesap_standart WHERE kod = p_kod)
        OR EXISTS (SELECT 1 FROM dose_private.hesap_ozel WHERE okul_id = p_okul AND kod = p_kod)
$$;

CREATE OR REPLACE FUNCTION public.dose_finans_tanimlari() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul();
BEGIN
    IF v_okul IS NULL OR (public.dose_yetki('vergi_hesap') = '' AND public.dose_yetki('stok') = ''
                           AND public.dose_yetki('yevmiye') = '') THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Muhasebe hesaplarını görme yetkiniz yok.';
    END IF;
    RETURN jsonb_build_object(
        'hesaplar', coalesce((SELECT jsonb_agg(jsonb_build_object('kod', h.kod, 'ad', h.ad) ORDER BY h.kod)
                              FROM (SELECT kod, ad FROM dose_private.hesap_standart
                                    UNION ALL SELECT kod, ad FROM dose_private.hesap_ozel WHERE okul_id = v_okul) h), '[]'::JSONB),
        'vergi_hesaplari', coalesce((SELECT jsonb_agg(jsonb_build_object('tur', v.tur, 'hesap_kodu', v.hesap_kodu,
                                                                          'surum', v.surum) ORDER BY v.tur)
                                     FROM dose_private.vergi_hesap v WHERE v.okul_id = v_okul), '[]'::JSONB));
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_hesap_ekle(p_kod TEXT, p_ad TEXT) RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul(); v_kod TEXT := btrim(p_kod); v_ad TEXT := nullif(btrim(p_ad), '');
BEGIN
    IF auth.uid() IS NULL OR public.dose_yetki('vergi_hesap') <> 'y' OR public.dose_rol() <> 'Sayman' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Muhasebe hesabını yalnız yetkili sayman tanımlayabilir.';
    END IF;
    IF v_kod IS NULL OR v_kod !~ '^[0-9]{3}(\.[0-9]{1,6})*$' OR length(v_kod) > 32 OR v_ad IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Geçerli hesap kodu ve hesap adı giriniz.';
    END IF;
    IF dose_private.hesap_var(v_okul, v_kod) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu hesap kodu zaten tanımlı.';
    END IF;
    INSERT INTO dose_private.hesap_ozel (okul_id, kod, ad, olusturan) VALUES (v_okul, v_kod, v_ad, auth.uid());
    PERFORM dose_private.log(v_okul, 'Muhasebe hesabı tanımlandı', 'hesap', NULL, v_kod || ' · ' || v_ad);
    RETURN jsonb_build_object('kod', v_kod, 'ad', v_ad);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_vergi_hesabi_kaydet(p_tur TEXT, p_hesap_kodu TEXT, p_sur INTEGER)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_eski dose_private.vergi_hesap%ROWTYPE;
    v_yeni dose_private.vergi_hesap%ROWTYPE;
BEGIN
    IF auth.uid() IS NULL OR public.dose_yetki('vergi_hesap') <> 'y' OR public.dose_rol() <> 'Sayman' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Vergi hesaplarını yalnız yetkili sayman tanımlayabilir.';
    END IF;
    IF p_tur IS NULL OR p_tur NOT IN ('Satış KDV tevkifatı', 'Satış stopajı', 'Alış KDV tevkifatı', 'Alış stopajı')
       OR p_hesap_kodu IS NULL OR NOT dose_private.hesap_var(v_okul, p_hesap_kodu) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Geçerli vergi türü ve tanımlı hesap seçiniz.';
    END IF;
    IF p_hesap_kodu ~ '^(100|102)(\.|$)' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Kasa/banka hesabı vergi karşı hesabı olarak seçilemez.';
    END IF;
    SELECT * INTO v_eski FROM dose_private.vergi_hesap WHERE okul_id = v_okul AND tur = p_tur FOR UPDATE;
    IF FOUND THEN
        IF p_sur IS DISTINCT FROM v_eski.surum THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Vergi hesabı değiştirildi; güncelini yükleyin.', HINT = 'surum_cakismasi';
        END IF;
        UPDATE dose_private.vergi_hesap SET hesap_kodu = p_hesap_kodu, surum = surum + 1, guncelleyen = auth.uid()
        WHERE okul_id = v_okul AND tur = p_tur RETURNING * INTO v_yeni;
    ELSE
        IF p_sur IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Vergi hesabı değiştirildi; güncelini yükleyin.', HINT = 'surum_cakismasi';
        END IF;
        INSERT INTO dose_private.vergi_hesap (okul_id, tur, hesap_kodu, guncelleyen)
        VALUES (v_okul, p_tur, p_hesap_kodu, auth.uid()) RETURNING * INTO v_yeni;
    END IF;
    PERFORM dose_private.log(v_okul, 'Vergi hesabı belirlendi', 'vergi_hesap', NULL, p_tur || ' · ' || p_hesap_kodu,
                             to_jsonb(v_eski), to_jsonb(v_yeni));
    RETURN jsonb_build_object('tur', v_yeni.tur, 'hesap_kodu', v_yeni.hesap_kodu, 'surum', v_yeni.surum);
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.stok_isle(
    p_okul INTEGER, p_malzeme INTEGER, p_tarih DATE, p_yon TEXT, p_miktar NUMERIC, p_tutar NUMERIC,
    p_kaynak TEXT, p_aciklama TEXT, p_istek UUID, p_ters INTEGER DEFAULT NULL, p_kaynak_id INTEGER DEFAULT NULL
) RETURNS JSONB LANGUAGE plpgsql VOLATILE SET search_path = '' AS $$
DECLARE
    v_malzeme public.malzeme%ROWTYPE;
    v_hesap TEXT;
    v_miktar NUMERIC;
    v_deger NUMERIC;
    v_son_tarih DATE;
    v_id INTEGER;
BEGIN
    IF p_tarih IS NULL OR p_yon IS NULL OR p_yon NOT IN ('Giriş', 'Çıkış') OR p_istek IS NULL
       OR p_miktar IS NULL OR p_tutar IS NULL
       OR p_miktar::TEXT IN ('NaN', 'Infinity', '-Infinity')
       OR p_tutar::TEXT IN ('NaN', 'Infinity', '-Infinity')
       OR p_miktar <= 0 OR p_tutar < 0 OR p_tutar <> round(p_tutar, 2) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Tarih, yön, pozitif miktar ve sıfır veya pozitif kuruşlu maliyet tutarı gereklidir.';
    END IF;
    IF p_tarih > (now() AT TIME ZONE 'Europe/Istanbul')::DATE THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İleri tarihli stok hareketi kaydedilemez.';
    END IF;
    SELECT * INTO v_malzeme FROM public.malzeme
    WHERE okul_id = p_okul AND id = p_malzeme AND (aktif = 1 OR p_ters IS NOT NULL) FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Aktif stok kartı bulunamadı.'; END IF;
    v_hesap := CASE v_malzeme.tur WHEN 'İlk Madde ve Malzeme' THEN '150'
               WHEN 'Yarı Mamul' THEN '151' WHEN 'Mamul' THEN '152' WHEN 'Ticari Mal' THEN '153' END;
    IF v_hesap IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Stok kartının muhasebe türü geçersiz.';
    END IF;
    IF EXISTS (SELECT 1 FROM public.stok_hareket WHERE okul_id = p_okul AND istek_id = p_istek) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu işlem daha önce kaydedildi; stok listesini yenileyin.';
    END IF;
    SELECT coalesce(sum(CASE WHEN yon = 'Giriş' THEN miktar ELSE -miktar END), 0),
           coalesce(sum(CASE WHEN yon = 'Giriş' THEN toplam_tutar ELSE -toplam_tutar END), 0),
           max(tarih::DATE)
      INTO v_miktar, v_deger, v_son_tarih
    FROM public.stok_hareket WHERE okul_id = p_okul AND malzeme_id = p_malzeme;
    IF v_son_tarih IS NOT NULL AND p_tarih < v_son_tarih THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Son stok hareketinden daha eski tarihe kayıt yapılamaz.';
    END IF;
    IF p_yon = 'Çıkış' THEN
        IF p_miktar > v_miktar OR p_tutar > v_deger THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Stok miktarı veya kayıtlı maliyet yetersiz.';
        END IF;
        IF p_miktar = v_miktar AND p_tutar <> v_deger THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Son stok çıkışının maliyeti kalan stok değerine eşit olmalıdır.';
        END IF;
    END IF;
    INSERT INTO public.stok_hareket (okul_id, tarih, malzeme_id, yon, miktar, birim_fiyat, toplam_tutar,
                                     kaynak, kaynak_id, aciklama, istek_id, ters_hareket_id, olusturan)
    VALUES (p_okul, p_tarih::TEXT, p_malzeme, p_yon, p_miktar, p_tutar / p_miktar, p_tutar,
            p_kaynak, p_kaynak_id, p_aciklama, p_istek, p_ters, auth.uid()) RETURNING id INTO v_id;
    RETURN jsonb_build_object('id', v_id, 'hesap_kodu', v_hesap, 'ad', v_malzeme.ad);
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.yevmiye_olustur(
    p_okul INTEGER, p_tarih DATE, p_aciklama TEXT, p_kaynak TEXT, p_kaynak_id INTEGER, p_satirlar JSONB
) RETURNS INTEGER LANGUAGE plpgsql VOLATILE SET search_path = '' AS $$
DECLARE
    v_satir JSONB; v_kod TEXT; v_borc NUMERIC; v_alacak NUMERIC;
    v_toplam_borc NUMERIC := 0; v_toplam_alacak NUMERIC := 0; v_fis INTEGER; v_say INTEGER := 0;
BEGIN
    IF jsonb_typeof(p_satirlar) IS DISTINCT FROM 'array' OR jsonb_array_length(p_satirlar) < 2 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yevmiye fişi en az iki satır içermelidir.';
    END IF;
    FOR v_satir IN SELECT value FROM jsonb_array_elements(p_satirlar) LOOP
        v_kod := v_satir->>'hesap'; v_borc := (v_satir->>'borc')::NUMERIC; v_alacak := (v_satir->>'alacak')::NUMERIC;
        IF NOT dose_private.hesap_var(p_okul, v_kod) OR v_borc IS NULL OR v_alacak IS NULL
           OR v_borc::TEXT IN ('NaN', 'Infinity', '-Infinity') OR v_alacak::TEXT IN ('NaN', 'Infinity', '-Infinity')
           OR v_borc < 0 OR v_alacak < 0 OR (v_borc > 0) = (v_alacak > 0)
           OR v_borc <> round(v_borc, 2) OR v_alacak <> round(v_alacak, 2) THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yevmiye satırında tanımlı hesap ve tek yönlü geçerli tutar gereklidir.';
        END IF;
        v_toplam_borc := v_toplam_borc + v_borc; v_toplam_alacak := v_toplam_alacak + v_alacak;
        v_say := v_say + 1;
    END LOOP;
    IF v_say < 2 OR v_toplam_borc <= 0 OR v_toplam_borc <> v_toplam_alacak THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yevmiye fişi borç ve alacak toplamları eşit ve pozitif olmalıdır.';
    END IF;
    INSERT INTO public.yevmiye (okul_id, fis_no, tarih, aciklama, kaynak, kaynak_id, olusturan)
    VALUES (p_okul, format('YEV-%s-%s', to_char(p_tarih, 'YYYY'),
            lpad(dose_private.sira_no(p_okul, 'yevmiye', extract(year FROM p_tarih)::INTEGER)::TEXT, 5, '0')),
            p_tarih::TEXT, p_aciklama, p_kaynak, p_kaynak_id, auth.uid()) RETURNING id INTO v_fis;
    FOR v_satir IN SELECT value FROM jsonb_array_elements(p_satirlar) LOOP
        INSERT INTO public.yevmiye_satir (okul_id, yevmiye_id, hesap_kodu, aciklama, borc, alacak)
        VALUES (p_okul, v_fis, v_satir->>'hesap', p_aciklama, (v_satir->>'borc')::NUMERIC, (v_satir->>'alacak')::NUMERIC);
    END LOOP;
    RETURN v_fis;
END;
$$;
REVOKE ALL ON FUNCTION dose_private.hesap_var(INTEGER, TEXT),
    dose_private.stok_isle(INTEGER, INTEGER, DATE, TEXT, NUMERIC, NUMERIC, TEXT, TEXT, UUID, INTEGER, INTEGER),
    dose_private.yevmiye_olustur(INTEGER, DATE, TEXT, TEXT, INTEGER, JSONB) FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.dose_stok_kaydet(
    p_malzeme INTEGER, p_tarih DATE, p_yon TEXT, p_miktar NUMERIC, p_tutar NUMERIC,
    p_karsi_hesap TEXT, p_aciklama TEXT, p_istek UUID
) RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul(); v_stok JSONB; v_fis INTEGER; v_adi TEXT := nullif(btrim(p_aciklama), '');
BEGIN
    IF auth.uid() IS NULL OR public.dose_rol() <> 'Sayman' OR public.dose_yetki('stok') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Stok maliyetini ve hareketini yalnız yetkili sayman kaydedebilir.';
    END IF;
    IF v_adi IS NULL OR p_karsi_hesap IS NULL OR NOT dose_private.hesap_var(v_okul, p_karsi_hesap) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Hareket gerekçesi ve tanımlı karşı hesap seçiniz.';
    END IF;
    IF p_karsi_hesap ~ '^(100|102)(\.|$)' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Kasa/banka hesabı stok karşı hesabı olarak seçilemez.';
    END IF;
    v_stok := dose_private.stok_isle(v_okul, p_malzeme, p_tarih, p_yon, p_miktar, p_tutar, 'Manuel', v_adi, p_istek, NULL);
    IF p_karsi_hesap = v_stok->>'hesap_kodu' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Karşı hesap stok hesabıyla aynı olamaz.';
    END IF;
    IF p_tutar > 0 THEN
        v_fis := dose_private.yevmiye_olustur(v_okul, p_tarih, v_adi, 'Stok', (v_stok->>'id')::INTEGER,
            jsonb_build_array(
                jsonb_build_object('hesap', v_stok->>'hesap_kodu', 'borc', CASE WHEN p_yon = 'Giriş' THEN p_tutar ELSE 0 END,
                                   'alacak', CASE WHEN p_yon = 'Çıkış' THEN p_tutar ELSE 0 END),
                jsonb_build_object('hesap', p_karsi_hesap, 'borc', CASE WHEN p_yon = 'Çıkış' THEN p_tutar ELSE 0 END,
                                   'alacak', CASE WHEN p_yon = 'Giriş' THEN p_tutar ELSE 0 END)));
    END IF;
    PERFORM dose_private.log(v_okul, 'Stok hareketi kaydedildi', 'stok_hareket', (v_stok->>'id')::INTEGER,
                             format('%s · %s · %s', p_yon, v_stok->>'ad', v_adi), NULL,
                             jsonb_build_object('miktar', p_miktar, 'toplam_tutar', p_tutar, 'karsi_hesap', p_karsi_hesap,
                                                'yevmiye_id', v_fis));
    RETURN jsonb_build_object('id', (v_stok->>'id')::INTEGER, 'yevmiye_id', v_fis);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_stok_tersle(p_hareket INTEGER, p_gerekce TEXT, p_istek UUID)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); v_eski public.stok_hareket%ROWTYPE; v_fis public.yevmiye%ROWTYPE;
    v_stok JSONB; v_yeni_fis INTEGER; v_satirlar JSONB; v_neden TEXT := nullif(btrim(p_gerekce), '');
    v_tarih DATE := (now() AT TIME ZONE 'Europe/Istanbul')::DATE;
BEGIN
    IF auth.uid() IS NULL OR public.dose_rol() <> 'Sayman' OR public.dose_yetki('stok') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Stok hareketini yalnız yetkili sayman tersleyebilir.';
    END IF;
    IF v_neden IS NULL THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ters kayıt gerekçesi zorunludur.'; END IF;
    SELECT * INTO v_eski FROM public.stok_hareket WHERE okul_id = v_okul AND id = p_hareket FOR UPDATE;
    IF NOT FOUND OR v_eski.kaynak <> 'Manuel' OR v_eski.ters_hareket_id IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Terslenebilir manuel stok hareketi bulunamadı.';
    END IF;
    PERFORM 1 FROM public.malzeme WHERE okul_id = v_okul AND id = v_eski.malzeme_id FOR UPDATE;
    IF EXISTS (SELECT 1 FROM public.stok_hareket WHERE okul_id = v_okul AND ters_hareket_id = v_eski.id) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu stok hareketi daha önce terslendi.';
    END IF;
    IF EXISTS (SELECT 1 FROM public.stok_hareket s
               WHERE s.okul_id = v_okul AND s.malzeme_id = v_eski.malzeme_id AND s.id > v_eski.id
                 AND s.ters_hareket_id IS NULL
                 AND NOT EXISTS (SELECT 1 FROM public.stok_hareket t
                                 WHERE t.okul_id = v_okul AND t.ters_hareket_id = s.id)) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu stok kartında daha yeni hareketler var; önce onları inceleyin.';
    END IF;
    IF v_eski.toplam_tutar > 0 THEN
        SELECT * INTO v_fis FROM public.yevmiye WHERE okul_id = v_okul AND kaynak = 'Stok' AND kaynak_id = v_eski.id;
        IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Stok hareketinin yevmiye fişi bulunamadı.'; END IF;
        SELECT jsonb_agg(jsonb_build_object('hesap', hesap_kodu, 'borc', alacak, 'alacak', borc) ORDER BY id)
          INTO v_satirlar FROM public.yevmiye_satir WHERE okul_id = v_okul AND yevmiye_id = v_fis.id;
    END IF;
    v_stok := dose_private.stok_isle(v_okul, v_eski.malzeme_id, v_tarih,
        CASE v_eski.yon WHEN 'Giriş' THEN 'Çıkış' ELSE 'Giriş' END,
        v_eski.miktar, v_eski.toplam_tutar, 'Manuel ters kayıt', v_neden, p_istek, v_eski.id);
    IF v_eski.toplam_tutar > 0 THEN
        v_yeni_fis := dose_private.yevmiye_olustur(v_okul, v_tarih, v_neden, 'Stok ters kayıt', v_eski.id, v_satirlar);
    END IF;
    PERFORM dose_private.log(v_okul, 'Stok hareketi terslendi', 'stok_hareket', v_eski.id, v_neden, NULL,
                             jsonb_build_object('ters_hareket_id', (v_stok->>'id')::INTEGER, 'yevmiye_id', v_yeni_fis));
    RETURN jsonb_build_object('id', (v_stok->>'id')::INTEGER, 'yevmiye_id', v_yeni_fis);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_stok_veri() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul();
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('stok') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Stok ekranına erişim yetkiniz yok.';
    END IF;
    RETURN jsonb_build_object(
        'kartlar', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', m.id, 'ad', m.ad, 'kod', m.kod, 'tur', m.tur, 'birim', m.birim, 'aktif', m.aktif,
            'miktar', coalesce(h.miktar, 0)::TEXT, 'tutar', coalesce(h.tutar, 0)::TEXT) ORDER BY m.ad)
            FROM public.malzeme m LEFT JOIN LATERAL (
                SELECT sum(CASE WHEN s.yon = 'Giriş' THEN s.miktar ELSE -s.miktar END) AS miktar,
                       sum(CASE WHEN s.yon = 'Giriş' THEN s.toplam_tutar ELSE -s.toplam_tutar END) AS tutar
                FROM public.stok_hareket s WHERE s.okul_id = m.okul_id AND s.malzeme_id = m.id
            ) h ON true WHERE m.okul_id = v_okul), '[]'::JSONB),
        'hareketler', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', s.id, 'tarih', s.tarih, 'malzeme_id', s.malzeme_id, 'malzeme', m.ad,
            'yon', s.yon, 'miktar', s.miktar::TEXT, 'tutar', s.toplam_tutar::TEXT,
            'kaynak', s.kaynak, 'aciklama', s.aciklama, 'ters_hareket_id', s.ters_hareket_id,
            'terslendi', EXISTS (SELECT 1 FROM public.stok_hareket t WHERE t.okul_id = v_okul AND t.ters_hareket_id = s.id))
            ORDER BY s.id DESC) FROM public.stok_hareket s
            JOIN public.malzeme m ON m.okul_id = s.okul_id AND m.id = s.malzeme_id WHERE s.okul_id = v_okul), '[]'::JSONB));
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_yevmiye_veri() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul();
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('yevmiye') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Yevmiye ekranına erişim yetkiniz yok.';
    END IF;
    RETURN coalesce((SELECT jsonb_agg(jsonb_build_object(
        'id', y.id, 'fis_no', y.fis_no, 'tarih', y.tarih, 'aciklama', y.aciklama, 'kaynak', y.kaynak,
        'satirlar', coalesce((SELECT jsonb_agg(jsonb_build_object('hesap_kodu', s.hesap_kodu,
                                      'borc', s.borc::TEXT, 'alacak', s.alacak::TEXT) ORDER BY s.id)
                              FROM public.yevmiye_satir s WHERE s.okul_id = v_okul AND s.yevmiye_id = y.id), '[]'::JSONB))
        ORDER BY y.id DESC) FROM public.yevmiye y WHERE y.okul_id = v_okul), '[]'::JSONB);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_mizan_veri() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul();
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('yevmiye') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Mizan ekranına erişim yetkiniz yok.';
    END IF;
    RETURN coalesce((SELECT jsonb_agg(jsonb_build_object(
        'hesap_kodu', hesap_kodu, 'borc', borc::TEXT, 'alacak', alacak::TEXT, 'bakiye', (borc - alacak)::TEXT)
        ORDER BY hesap_kodu)
        FROM (SELECT hesap_kodu, sum(borc) AS borc, sum(alacak) AS alacak
              FROM public.yevmiye_satir WHERE okul_id = v_okul GROUP BY hesap_kodu) t), '[]'::JSONB);
END;
$$;

REVOKE ALL ON FUNCTION public.dose_finans_tanimlari(), public.dose_hesap_ekle(TEXT, TEXT),
    public.dose_vergi_hesabi_kaydet(TEXT, TEXT, INTEGER), public.dose_stok_kaydet(INTEGER, DATE, TEXT, NUMERIC, NUMERIC, TEXT, TEXT, UUID),
    public.dose_stok_tersle(INTEGER, TEXT, UUID), public.dose_stok_veri(), public.dose_yevmiye_veri(),
    public.dose_mizan_veri() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_finans_tanimlari(), public.dose_hesap_ekle(TEXT, TEXT),
    public.dose_vergi_hesabi_kaydet(TEXT, TEXT, INTEGER), public.dose_stok_kaydet(INTEGER, DATE, TEXT, NUMERIC, NUMERIC, TEXT, TEXT, UUID),
    public.dose_stok_tersle(INTEGER, TEXT, UUID), public.dose_stok_veri(), public.dose_yevmiye_veri(),
    public.dose_mizan_veri() TO authenticated;
