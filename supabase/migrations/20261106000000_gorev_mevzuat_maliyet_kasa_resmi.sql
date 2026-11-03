-- Ana ekran görevleri, doğrulanmış mevzuat oranları, ürün maliyeti/fiyat, kasa genişletme, resmi yazı ve denetim.

-- ------------------------------------------------------------------ mevzuat: okulun doğruladığı aktif yayın
CREATE OR REPLACE FUNCTION dose_private.mevzuat_okul_oranlari(p_okul INTEGER, p_tarih DATE DEFAULT NULL)
RETURNS JSONB LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE
    v_tarih DATE := coalesce(p_tarih, (now() AT TIME ZONE 'Europe/Istanbul')::DATE);
    v_yayin dose_private.mevzuat_yayin%ROWTYPE;
BEGIN
    SELECT m.* INTO v_yayin
    FROM dose_private.mevzuat_yayin m
    JOIN dose_private.mevzuat_onay o ON o.yayin_id = m.id AND o.okul_id = p_okul AND o.karar IS TRUE
      AND NOT EXISTS (
          SELECT 1 FROM dose_private.mevzuat_onay x
          WHERE x.yayin_id = m.id AND x.okul_id = p_okul AND x.id > o.id)
    WHERE m.baslangic <= v_tarih
      AND extract(year FROM m.baslangic) = extract(year FROM v_tarih)
      AND NOT EXISTS (
          SELECT 1 FROM dose_private.mevzuat_yayin n
          WHERE n.baslangic = m.baslangic AND n.id > m.id)
    ORDER BY m.baslangic DESC, m.id DESC
    LIMIT 1;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    RETURN jsonb_build_object('yayin_id', v_yayin.id, 'baslangic', v_yayin.baslangic,
        'kaynak', v_yayin.kaynak, 'degerler', v_yayin.degerler);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_mevzuat_aktif() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul(); v_oran JSONB;
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('mevzuat') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Mevzuat parametrelerine erişim yetkiniz yok.';
    END IF;
    v_oran := dose_private.mevzuat_okul_oranlari(v_okul);
    IF v_oran IS NULL THEN
        RETURN jsonb_build_object('var', false,
            'mesaj', 'Bu takvim yılı için doğrulanmış merkez parametre yayını yok. Sayman Okul parametre doğrulaması ekranından yayını onaylamalıdır.');
    END IF;
    RETURN jsonb_build_object('var', true) || v_oran;
END;
$$;

REVOKE ALL ON FUNCTION public.dose_mevzuat_aktif() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_mevzuat_aktif() TO authenticated;

-- Parça başı kaydında doğrulanmış oran zorunlu (yoksa hazırlık engellenir)
CREATE OR REPLACE FUNCTION dose_private.pb_mevzuat_zorunlu(p_okul INTEGER) RETURNS JSONB
LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE v JSONB := dose_private.mevzuat_okul_oranlari(p_okul);
BEGIN
    IF v IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = 'Doğrulanmış merkez parametre yayını yok; sayman önce Okul parametre doğrulamasını tamamlamalıdır.';
    END IF;
    RETURN v->'degerler';
END;
$$;

-- ------------------------------------------------------------------ ana ekran: bekleyen görevler
CREATE OR REPLACE FUNCTION public.dose_gorevlerim() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_rol TEXT := public.dose_rol();
    v_bolum INTEGER := public.dose_bolum();
    v_liste JSONB := '[]'::JSONB;
BEGIN
    IF v_okul IS NULL OR auth.uid() IS NULL THEN
        RETURN jsonb_build_object('gorevler', '[]'::JSONB);
    END IF;
    -- Sipariş onay (asama 1=Alan Şefi, 2=TMY, 3=Müdür)
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
            'tur', 'mevzuat', 'sayfa', 'mevzuat', 'baslik', 'Parametere doğrulama',
            'ozet', 'Doğrulanmamış merkez yayını var', 'id', m.id) ORDER BY m.id)
            FROM dose_private.mevzuat_yayin m
            WHERE extract(year FROM m.baslangic) = extract(year FROM now() AT TIME ZONE 'Europe/Istanbul')
              AND NOT EXISTS (
                  SELECT 1 FROM dose_private.mevzuat_yayin n
                  WHERE n.baslangic = m.baslangic AND n.id > m.id)
              AND NOT EXISTS (
                  SELECT 1 FROM dose_private.mevzuat_onay o
                  WHERE o.yayin_id = m.id AND o.okul_id = v_okul AND o.karar IS TRUE
                    AND NOT EXISTS (SELECT 1 FROM dose_private.mevzuat_onay x
                                   WHERE x.yayin_id = m.id AND x.okul_id = v_okul AND x.id > o.id))), '[]'::JSONB);
    END IF;
    RETURN jsonb_build_object('gorevler', coalesce(v_liste, '[]'::JSONB));
END;
$$;

REVOKE ALL ON FUNCTION public.dose_gorevlerim() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_gorevlerim() TO authenticated;

-- ------------------------------------------------------------------ ürün maliyeti / fiyat tespit
CREATE TABLE IF NOT EXISTS dose_private.urun_maliyet (
    id SERIAL PRIMARY KEY,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    urun_id INTEGER NOT NULL REFERENCES public.urun(id) ON DELETE CASCADE,
    kalem_turu TEXT NOT NULL CHECK (length(btrim(kalem_turu)) BETWEEN 2 AND 80),
    aciklama TEXT CHECK (length(aciklama) <= 500),
    miktar NUMERIC NOT NULL CHECK (miktar > 0),
    birim TEXT NOT NULL CHECK (length(btrim(birim)) BETWEEN 1 AND 20),
    birim_fiyat NUMERIC NOT NULL CHECK (birim_fiyat >= 0),
    tutar NUMERIC NOT NULL CHECK (tutar = round(miktar * birim_fiyat, 2)),
    surum INTEGER NOT NULL DEFAULT 1,
    olusturan UUID NOT NULL REFERENCES auth.users(id),
    olusturma TEXT NOT NULL DEFAULT dose_private.zaman()
);
CREATE INDEX IF NOT EXISTS urun_maliyet_urun ON dose_private.urun_maliyet(okul_id, urun_id);
ALTER TABLE dose_private.urun_maliyet ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON dose_private.urun_maliyet FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.dose_maliyet_veri(p_urun INTEGER DEFAULT NULL) RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul();
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('urun') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Maliyet ekranına erişim yetkiniz yok.';
    END IF;
    RETURN jsonb_build_object(
        'urunler', coalesce((SELECT jsonb_agg(jsonb_build_object('id', u.id, 'ad', u.ad, 'birim', u.birim,
            'satis_fiyati', u.satis_fiyati::TEXT, 'aktif', u.aktif = 1) ORDER BY u.ad)
            FROM public.urun u WHERE u.okul_id = v_okul
              AND (NOT public.dose_bolum_kisitli() OR u.bolum_id = public.dose_bolum())), '[]'::JSONB),
        'kalemler', CASE WHEN p_urun IS NULL THEN '[]'::JSONB ELSE coalesce((
            SELECT jsonb_agg(jsonb_build_object('id', m.id, 'kalem_turu', m.kalem_turu, 'aciklama', m.aciklama,
                'miktar', m.miktar::TEXT, 'birim', m.birim, 'birim_fiyat', m.birim_fiyat::TEXT,
                'tutar', m.tutar::TEXT) ORDER BY m.id)
            FROM dose_private.urun_maliyet m WHERE m.okul_id = v_okul AND m.urun_id = p_urun), '[]'::JSONB) END,
        'toplam', CASE WHEN p_urun IS NULL THEN NULL ELSE (
            SELECT coalesce(sum(m.tutar), 0)::TEXT FROM dose_private.urun_maliyet m
            WHERE m.okul_id = v_okul AND m.urun_id = p_urun) END,
        'yazabilir', public.dose_yetki('urun') = 'y');
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_maliyet_kaydet(p_urun INTEGER, p_kalemler JSONB, p_istek UUID)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); v_k JSONB; v_sira INTEGER := 0; v_miktar NUMERIC; v_fiyat NUMERIC;
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('urun') <> 'y' OR auth.uid() IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Maliyet kalemlerini yalnız yetkili kullanıcı kaydedebilir.';
    END IF;
    IF p_urun IS NULL OR p_istek IS NULL OR jsonb_typeof(p_kalemler) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ürün ve maliyet kalemleri gereklidir.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.urun WHERE okul_id = v_okul AND id = p_urun) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ürün bulunamadı.';
    END IF;
    DELETE FROM dose_private.urun_maliyet WHERE okul_id = v_okul AND urun_id = p_urun;
    FOR v_k IN SELECT value FROM jsonb_array_elements(p_kalemler) LOOP
        v_sira := v_sira + 1;
        v_miktar := (v_k->>'miktar')::NUMERIC;
        v_fiyat := (v_k->>'birim_fiyat')::NUMERIC;
        IF v_miktar IS NULL OR v_fiyat IS NULL OR v_miktar <= 0 OR v_fiyat < 0
           OR nullif(btrim(v_k->>'kalem_turu'), '') IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. maliyet kalemi geçersiz.', v_sira);
        END IF;
        INSERT INTO dose_private.urun_maliyet (okul_id, urun_id, kalem_turu, aciklama, miktar, birim, birim_fiyat, tutar, olusturan)
        VALUES (v_okul, p_urun, btrim(v_k->>'kalem_turu'), nullif(btrim(v_k->>'aciklama'), ''),
                v_miktar, coalesce(nullif(btrim(v_k->>'birim'), ''), 'Adet'), v_fiyat, round(v_miktar * v_fiyat, 2), auth.uid());
    END LOOP;
    PERFORM dose_private.log(v_okul, 'Ürün maliyet kalemleri kaydedildi', 'urun', p_urun, NULL, NULL,
        jsonb_build_object('kalem', v_sira, 'istek', p_istek::TEXT));
    RETURN public.dose_maliyet_veri(p_urun);
END;
$$;

REVOKE ALL ON FUNCTION public.dose_maliyet_veri(INTEGER), public.dose_maliyet_kaydet(INTEGER, JSONB, UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_maliyet_veri(INTEGER), public.dose_maliyet_kaydet(INTEGER, JSONB, UUID) TO authenticated;

-- ------------------------------------------------------------------ kasa: avans, virman, faturasız (dose_kasa_kaydet genişletilir)
CREATE OR REPLACE FUNCTION public.dose_kasa_kaydet(
    p_tur TEXT, p_hesap TEXT, p_tarih DATE, p_tutar NUMERIC, p_fatura INTEGER,
    p_karsi_hesap TEXT, p_belge_no TEXT, p_aciklama TEXT, p_istek UUID
) RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); v_fatura public.fatura%ROWTYPE;
    v_aciklama TEXT := nullif(btrim(p_aciklama), ''); v_belge_no TEXT := nullif(btrim(p_belge_no), '');
    v_nakit_hesap TEXT; v_karsi TEXT; v_yon TEXT; v_bakiye NUMERIC; v_kalan NUMERIC;
    v_son_tarih DATE; v_hareket INTEGER; v_fis INTEGER; v_kisit TEXT; v_ozel BOOLEAN;
    v_hedef TEXT; v_hedef_kod TEXT; v_karsi_hareket INTEGER;
BEGIN
    IF auth.uid() IS NULL OR public.dose_rol() <> 'Sayman' OR public.dose_yetki('kasa') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Kasa/banka işlemlerini yalnız yetkili sayman kaydedebilir.';
    END IF;
    v_ozel := p_tur IN ('Avans', 'Virman', 'Faturasız gelir', 'Faturasız gider');
    IF p_tur IS NULL OR p_tur NOT IN ('Açılış', 'Tahsilat', 'Ödeme', 'Avans', 'Virman', 'Faturasız gelir', 'Faturasız gider')
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
    IF p_tur = 'Virman' THEN
        IF p_fatura IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Virman faturaya bağlanamaz.';
        END IF;
        v_hedef := CASE p_hesap WHEN 'Kasa (100)' THEN 'Banka (102)' ELSE 'Kasa (100)' END;
        v_hedef_kod := CASE v_hedef WHEN 'Kasa (100)' THEN '100' ELSE '102' END;
        v_yon := 'Çıkış';
        v_karsi := v_hedef_kod;
    ELSIF p_tur = 'Açılış' OR v_ozel THEN
        IF p_fatura IS NOT NULL OR p_karsi_hesap IS NULL OR NOT dose_private.hesap_var(v_okul, p_karsi_hesap)
           OR p_karsi_hesap ~ '^(100|102)(\.|$)' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu hareket için kasa/banka dışında tanımlı bir karşı hesap seçiniz.';
        END IF;
        v_yon := CASE WHEN p_tur IN ('Faturasız gider', 'Avans') THEN 'Çıkış' ELSE 'Giriş' END;
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
    IF p_tur = 'Virman' THEN
        PERFORM dose_private.kasa_kilitle(v_okul, v_hedef);
    END IF;
    SELECT max(tarih::DATE) INTO v_son_tarih FROM public.kasa_banka WHERE okul_id = v_okul AND hesap = p_hesap;
    IF v_son_tarih IS NOT NULL AND p_tarih < v_son_tarih THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Son kasa/banka hareketinden daha eski tarihe kayıt yapılamaz.';
    END IF;
    IF p_tur = 'Virman' THEN
        SELECT max(tarih::DATE) INTO v_son_tarih FROM public.kasa_banka WHERE okul_id = v_okul AND hesap = v_hedef;
        IF v_son_tarih IS NOT NULL AND p_tarih < v_son_tarih THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Hedef hesabın son hareketinden daha eski tarihe virman yapılamaz.';
        END IF;
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
    IF p_tur = 'Virman' THEN
        INSERT INTO public.kasa_banka (
            okul_id, tarih, hesap, yon, tur, tutar, hasilat_tutari, belge_no, aciklama, kaynak,
            karsi_hesap, istek_id, olusturan)
        VALUES (v_okul, p_tarih::TEXT, v_hedef, 'Giriş', 'Virman', p_tutar, 0, v_belge_no, v_aciklama,
            'KasaBanka', v_nakit_hesap, gen_random_uuid(), auth.uid()) RETURNING id INTO v_karsi_hareket;
        v_fis := dose_private.yevmiye_olustur(v_okul, p_tarih, v_aciklama, 'KasaBanka', v_hareket,
            jsonb_build_array(
                jsonb_build_object('hesap', v_hedef_kod, 'borc', p_tutar, 'alacak', 0),
                jsonb_build_object('hesap', v_nakit_hesap, 'borc', 0, 'alacak', p_tutar)));
    ELSE
        v_fis := dose_private.yevmiye_olustur(v_okul, p_tarih, v_aciklama, 'KasaBanka', v_hareket,
            jsonb_build_array(
                jsonb_build_object('hesap', v_nakit_hesap, 'borc', CASE WHEN v_yon = 'Giriş' THEN p_tutar ELSE 0 END,
                                   'alacak', CASE WHEN v_yon = 'Çıkış' THEN p_tutar ELSE 0 END),
                jsonb_build_object('hesap', v_karsi, 'borc', CASE WHEN v_yon = 'Çıkış' THEN p_tutar ELSE 0 END,
                                   'alacak', CASE WHEN v_yon = 'Giriş' THEN p_tutar ELSE 0 END)));
    END IF;
    PERFORM dose_private.log(v_okul, 'Kasa/banka hareketi kaydedildi', 'kasa_banka', v_hareket, v_aciklama, NULL,
        jsonb_build_object('tur', p_tur, 'hesap', p_hesap, 'tutar', p_tutar::TEXT, 'fatura_id', p_fatura,
            'yevmiye_id', v_fis, 'karsi_hareket_id', v_karsi_hareket));
    RETURN jsonb_build_object('id', v_hareket, 'yevmiye_id', v_fis,
        'bakiye', (v_bakiye + CASE WHEN v_yon = 'Giriş' THEN p_tutar ELSE -p_tutar END)::TEXT,
        'fatura_kalan', CASE WHEN v_kalan IS NULL THEN NULL ELSE (v_kalan - p_tutar)::TEXT END);
END;
$$;

-- ------------------------------------------------------------------ resmi yazı
CREATE TABLE IF NOT EXISTS dose_private.resmi_yazi (
    id SERIAL PRIMARY KEY,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    yazi_no TEXT NOT NULL,
    tarih DATE NOT NULL,
    konu TEXT NOT NULL CHECK (length(btrim(konu)) BETWEEN 3 AND 200),
    muhatap TEXT NOT NULL CHECK (length(btrim(muhatap)) BETWEEN 3 AND 200),
    govde TEXT NOT NULL CHECK (length(btrim(govde)) BETWEEN 10 AND 20000),
    surum INTEGER NOT NULL DEFAULT 1,
    olusturan UUID NOT NULL REFERENCES auth.users(id),
    olusturma TEXT NOT NULL DEFAULT dose_private.zaman(),
    istek_id UUID NOT NULL,
    CONSTRAINT resmi_yazi_istek UNIQUE (okul_id, istek_id),
    CONSTRAINT resmi_yazi_no UNIQUE (okul_id, yazi_no)
);
ALTER TABLE dose_private.resmi_yazi ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON dose_private.resmi_yazi FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.dose_resmi_veri() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul();
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('kurum') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Resmi yazı ekranına erişim yetkiniz yok.';
    END IF;
    RETURN jsonb_build_object(
        'yazilar', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', r.id, 'yazi_no', r.yazi_no, 'tarih', r.tarih, 'konu', r.konu, 'muhatap', r.muhatap,
            'govde', r.govde, 'surum', r.surum) ORDER BY r.id DESC)
            FROM dose_private.resmi_yazi r WHERE r.okul_id = v_okul), '[]'::JSONB),
        'yazabilir', public.dose_yetki('kurum') = 'y');
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_resmi_kaydet(p_id INTEGER, p_surum INTEGER, p_veri JSONB, p_istek UUID)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); v_id INTEGER; v_no TEXT; v_tarih DATE; v_konu TEXT; v_muhatap TEXT; v_govde TEXT;
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('kurum') <> 'y' OR auth.uid() IS NULL THEN
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

-- ------------------------------------------------------------------ denetim formu
CREATE TABLE IF NOT EXISTS dose_private.denetim_form (
    id SERIAL PRIMARY KEY,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    form_no TEXT NOT NULL,
    tarih DATE NOT NULL,
    denetci TEXT NOT NULL CHECK (length(btrim(denetci)) BETWEEN 3 AND 120),
    kapsam TEXT NOT NULL CHECK (length(btrim(kapsam)) BETWEEN 3 AND 500),
    bulgular TEXT NOT NULL CHECK (length(btrim(bulgular)) BETWEEN 3 AND 20000),
    sonuc TEXT NOT NULL CHECK (length(btrim(sonuc)) BETWEEN 3 AND 2000),
    surum INTEGER NOT NULL DEFAULT 1,
    olusturan UUID NOT NULL REFERENCES auth.users(id),
    olusturma TEXT NOT NULL DEFAULT dose_private.zaman(),
    istek_id UUID NOT NULL,
    CONSTRAINT denetim_istek UNIQUE (okul_id, istek_id),
    CONSTRAINT denetim_no UNIQUE (okul_id, form_no)
);
ALTER TABLE dose_private.denetim_form ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON dose_private.denetim_form FROM PUBLIC, anon, authenticated;

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
            'bulgular', d.bulgular, 'sonuc', d.sonuc, 'surum', d.surum) ORDER BY d.id DESC)
            FROM dose_private.denetim_form d WHERE d.okul_id = v_okul), '[]'::JSONB),
        'yazabilir', public.dose_yetki('islem_kaydi') IN ('y', 'g') AND public.dose_rol() IN
            ('İzleyici / Denetçi', 'Okul Müdürü', 'Sistem Yöneticisi', 'Sayman'));
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_denetim_kaydet(p_id INTEGER, p_surum INTEGER, p_veri JSONB, p_istek UUID)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); v_id INTEGER; v_no TEXT; v_tarih DATE;
    v_denetci TEXT; v_kapsam TEXT; v_bulgular TEXT; v_sonuc TEXT;
BEGIN
    IF v_okul IS NULL OR auth.uid() IS NULL OR public.dose_rol() NOT IN
       ('İzleyici / Denetçi', 'Okul Müdürü', 'Sistem Yöneticisi', 'Sayman') THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Denetim formu yazma yetkiniz yok.';
    END IF;
    v_tarih := (p_veri->>'tarih')::DATE;
    v_denetci := nullif(btrim(p_veri->>'denetci'), '');
    v_kapsam := nullif(btrim(p_veri->>'kapsam'), '');
    v_bulgular := nullif(btrim(p_veri->>'bulgular'), '');
    v_sonuc := nullif(btrim(p_veri->>'sonuc'), '');
    IF v_tarih IS NULL OR v_denetci IS NULL OR v_kapsam IS NULL OR v_bulgular IS NULL OR v_sonuc IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Denetim formu alanları eksik.';
    END IF;
    IF p_id IS NULL THEN
        v_no := format('DN-%s-%s', extract(year FROM v_tarih)::INTEGER,
            lpad(dose_private.sira_no(v_okul, 'denetim', extract(year FROM v_tarih)::INTEGER)::TEXT, 4, '0'));
        INSERT INTO dose_private.denetim_form (okul_id, form_no, tarih, denetci, kapsam, bulgular, sonuc, olusturan, istek_id)
        VALUES (v_okul, v_no, v_tarih, v_denetci, v_kapsam, v_bulgular, v_sonuc, auth.uid(), p_istek) RETURNING id INTO v_id;
    ELSE
        UPDATE dose_private.denetim_form SET tarih = v_tarih, denetci = v_denetci, kapsam = v_kapsam,
            bulgular = v_bulgular, sonuc = v_sonuc, surum = surum + 1
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

REVOKE ALL ON FUNCTION public.dose_denetim_veri(), public.dose_denetim_kaydet(INTEGER, INTEGER, JSONB, UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_denetim_veri(), public.dose_denetim_kaydet(INTEGER, INTEGER, JSONB, UUID) TO authenticated;

-- ------------------------------------------------------------------ rapor özeti
CREATE OR REPLACE FUNCTION public.dose_rapor_ozet(p_yil INTEGER DEFAULT NULL) RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_yil INTEGER := coalesce(p_yil, extract(year FROM now() AT TIME ZONE 'Europe/Istanbul')::INTEGER);
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('yevmiye') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Rapor ekranına erişim yetkiniz yok.';
    END IF;
    RETURN jsonb_build_object(
        'yil', v_yil,
        'siparis', (SELECT count(*) FROM public.siparis WHERE okul_id = v_okul
                    AND extract(year FROM tarih::DATE) = v_yil),
        'fatura_satis', coalesce((SELECT sum(net_tutar) FROM public.fatura
            WHERE okul_id = v_okul AND tur = 'Satış' AND extract(year FROM tarih::DATE) = v_yil), 0)::TEXT,
        'fatura_alis', coalesce((SELECT sum(net_tutar) FROM public.fatura
            WHERE okul_id = v_okul AND tur = 'Alış' AND extract(year FROM tarih::DATE) = v_yil), 0)::TEXT,
        'kasa_bakiye', dose_private.kasa_bakiye(v_okul, 'Kasa (100)')::TEXT,
        'banka_bakiye', dose_private.kasa_bakiye(v_okul, 'Banka (102)')::TEXT,
        'hp_hasilat', dose_private.hp_hasilat(v_okul, v_yil, extract(month FROM now() AT TIME ZONE 'Europe/Istanbul')::INTEGER)::TEXT);
END;
$$;

REVOKE ALL ON FUNCTION public.dose_rapor_ozet(INTEGER) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_rapor_ozet(INTEGER) TO authenticated;
