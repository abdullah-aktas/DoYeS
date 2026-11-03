-- Keep the submitter's role so its approval can be recorded only when that stage is reached.
ALTER TABLE public.onay_durum
    ADD COLUMN IF NOT EXISTS hazirlayan_uid UUID REFERENCES auth.users(id),
    ADD COLUMN IF NOT EXISTS hazirlayan_rol TEXT;

WITH son_gonderim AS (
    SELECT DISTINCT ON (okul_id, belge_id) okul_id, belge_id, kullanici, rol
    FROM public.onay_kaydi
    WHERE belge_turu = 'Sipariş' AND karar = 'Onaya gönderildi'
    ORDER BY okul_id, belge_id, id DESC
)
UPDATE public.onay_durum o SET hazirlayan_uid = u.id, hazirlayan_rol = g.rol
FROM son_gonderim g LEFT JOIN auth.users u ON u.id::TEXT = g.kullanici
WHERE o.okul_id = g.okul_id AND o.belge_turu = 'Sipariş' AND o.belge_id = g.belge_id;

-- A previously skipped final approval must be reviewed, not silently treated as valid.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.onay_durum o
        LEFT JOIN LATERAL (
            SELECT max(k.id) AS id FROM public.onay_kaydi k
            WHERE k.okul_id = o.okul_id AND k.belge_turu = 'Sipariş'
              AND k.belge_id = o.belge_id AND k.karar = 'Onaya gönderildi'
        ) g ON true
        LEFT JOIN LATERAL (
            SELECT min(k.id) FILTER (WHERE k.asama = 1 AND k.karar IN ('Uygun', 'Uygun (hazırlayan)')) AS a1,
                   min(k.id) FILTER (WHERE k.asama = 2 AND k.karar IN ('Uygun', 'Uygun (hazırlayan)')) AS a2,
                   min(k.id) FILTER (WHERE k.asama = 3 AND k.karar IN ('Uygun', 'Uygun (hazırlayan)')) AS a3
            FROM public.onay_kaydi k
            WHERE k.okul_id = o.okul_id AND k.belge_turu = 'Sipariş'
              AND k.belge_id = o.belge_id AND k.id > coalesce(g.id, 0)
        ) a ON true
        WHERE o.belge_turu = 'Sipariş' AND o.durum = 'Onaylandı'
          AND (g.id IS NULL OR a.a1 IS NULL OR a.a2 IS NULL OR a.a3 IS NULL
               OR a.a2 <= a.a1 OR a.a3 <= a.a2)
    ) THEN
        RAISE EXCEPTION 'Aşamaları eksik veya sırasız onaylanmış eski siparişler var; kurulumdan önce onay geçmişini inceleyin.';
    END IF;
END;
$$;

ALTER TABLE public.siparis
    ALTER COLUMN sozlesme_bedeli TYPE NUMERIC USING sozlesme_bedeli::NUMERIC,
    ALTER COLUMN kdv_orani TYPE NUMERIC USING kdv_orani::NUMERIC;
ALTER TABLE public.siparis_kalem
    ALTER COLUMN miktar TYPE NUMERIC USING miktar::NUMERIC,
    ALTER COLUMN birim_fiyat TYPE NUMERIC USING birim_fiyat::NUMERIC,
    ALTER COLUMN iskonto_orani TYPE NUMERIC USING iskonto_orani::NUMERIC,
    ALTER COLUMN iskonto TYPE NUMERIC USING iskonto::NUMERIC;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.onay_durum o
        JOIN public.siparis s ON s.id = o.belge_id AND s.okul_id = o.okul_id
        WHERE o.belge_turu = 'Sipariş' AND o.durum = 'Onaylandı'
          AND (s.sozlesme_bedeli IS NULL OR s.sozlesme_bedeli::TEXT IN ('NaN', 'Infinity', '-Infinity')
               OR s.sozlesme_bedeli <= 0
               OR EXISTS (
                   SELECT 1 FROM public.siparis_kalem k WHERE k.okul_id = s.okul_id AND k.siparis_id = s.id
                     AND (k.miktar IS NULL OR k.birim_fiyat IS NULL OR k.iskonto_orani IS NULL OR k.iskonto IS NULL
                          OR k.miktar::TEXT IN ('NaN', 'Infinity', '-Infinity')
                          OR k.birim_fiyat::TEXT IN ('NaN', 'Infinity', '-Infinity')
                          OR k.iskonto_orani::TEXT IN ('NaN', 'Infinity', '-Infinity')
                          OR k.iskonto::TEXT IN ('NaN', 'Infinity', '-Infinity')
                          OR k.miktar <= 0 OR k.birim_fiyat < 0 OR k.iskonto_orani NOT BETWEEN 0 AND 1)
               ))
    ) THEN
        RAISE EXCEPTION 'Eski onaylı siparişlerde geçersiz tutar var; kurulumdan önce kayıtları inceleyin.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.onay_durum o
        JOIN public.siparis s ON s.id = o.belge_id AND s.okul_id = o.okul_id
        WHERE o.belge_turu = 'Sipariş' AND o.durum = 'Onaylandı'
          AND (s.sozlesme_bedeli IS DISTINCT FROM (
                   SELECT sum(round(k.miktar * k.birim_fiyat, 2)
                              - round(round(k.miktar * k.birim_fiyat, 2) * k.iskonto_orani, 2))
                   FROM public.siparis_kalem k WHERE k.okul_id = s.okul_id AND k.siparis_id = s.id)
               OR EXISTS (
                   SELECT 1 FROM public.siparis_kalem k WHERE k.okul_id = s.okul_id AND k.siparis_id = s.id
                     AND k.iskonto IS DISTINCT FROM round(round(k.miktar * k.birim_fiyat, 2) * k.iskonto_orani, 2)
               ))
    ) THEN
        RAISE EXCEPTION 'Eski onaylı siparişlerde tutar uyuşmazlığı var; kurulumdan önce kayıtları inceleyin.';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_siparisler() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_bolum INTEGER := public.dose_bolum();
    v_kisitli BOOLEAN := public.dose_bolum_kisitli();
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('siparis') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Sipariş ekranına erişim yetkiniz yok.';
    END IF;
    RETURN coalesce((
        SELECT jsonb_agg(jsonb_build_object(
            'id', s.id, 'siparis_no', s.siparis_no, 'tarih', s.tarih, 'cari_id', s.cari_id,
            'cari_unvan', c.unvan, 'bolum_id', s.bolum_id, 'bolum_ad', b.ad, 'konu', s.konu,
            'ucret_esasi', s.ucret_esasi, 'sozlesme_bedeli', s.sozlesme_bedeli,
            'sozlesme_bedeli_kesin', s.sozlesme_bedeli::TEXT,
            'kdv_orani', s.kdv_orani, 'kdv_orani_kesin', s.kdv_orani::TEXT,
            'durum', s.durum, 'surum', s.surum, 'aciklama', s.aciklama,
            'olusturan', s.olusturan, 'benim', s.olusturan = auth.uid(),
            'onay_asamasi', coalesce(o.asama, 0), 'onay_durumu', coalesce(o.durum, s.durum),
            'bekleyen_rol', CASE o.asama WHEN 1 THEN 'Alan Şefi' WHEN 2 THEN 'Teknik Müdür Yardımcısı'
                                          WHEN 3 THEN 'Okul Müdürü' END,
            'kalemler', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'id', k.id, 'urun_id', k.urun_id, 'aciklama', k.aciklama,
                'miktar', k.miktar, 'miktar_kesin', k.miktar::TEXT, 'birim', k.birim,
                'birim_fiyat', k.birim_fiyat, 'birim_fiyat_kesin', k.birim_fiyat::TEXT,
                'iskonto_orani', k.iskonto_orani, 'iskonto_orani_kesin', k.iskonto_orani::TEXT,
                'iskonto', k.iskonto) ORDER BY k.id)
                FROM public.siparis_kalem k WHERE k.siparis_id = s.id AND k.okul_id = v_okul), '[]'::JSONB),
            'gecmis', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'asama', a.asama, 'asama_adi', a.asama_adi, 'karar', a.karar,
                'ad_soyad', a.ad_soyad, 'rol', a.rol, 'zaman', a.zaman, 'aciklama', a.aciklama) ORDER BY a.id)
                FROM public.onay_kaydi a WHERE a.okul_id = v_okul AND a.belge_turu = 'Sipariş' AND a.belge_id = s.id),
                '[]'::JSONB)) ORDER BY s.tarih DESC, s.id DESC)
        FROM public.siparis s
        LEFT JOIN public.cari c ON c.okul_id = v_okul AND c.id = s.cari_id
        LEFT JOIN public.bolum b ON b.okul_id = v_okul AND b.id = s.bolum_id
        LEFT JOIN public.onay_durum o ON o.okul_id = v_okul AND o.belge_turu = 'Sipariş' AND o.belge_id = s.id
        WHERE s.okul_id = v_okul AND (NOT v_kisitli OR s.bolum_id = v_bolum)
    ), '[]'::JSONB);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_siparis_kaydet(
    p_siparis_id INTEGER, p_sur INTEGER, p_siparis JSONB, p_kalemler JSONB
) RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_uid UUID := auth.uid();
    v_okul INTEGER := public.dose_okul();
    v_rol TEXT := public.dose_rol();
    v_bolum_kisit INTEGER := public.dose_bolum();
    v_siparis public.siparis%ROWTYPE;
    v_cari INTEGER;
    v_bolum INTEGER;
    v_tarih DATE;
    v_konu TEXT;
    v_esas TEXT;
    v_kdv NUMERIC;
    v_toplam NUMERIC := 0;
    v_kalem JSONB;
    v_urun INTEGER;
    v_miktar NUMERIC;
    v_fiyat NUMERIC;
    v_iskonto_orani NUMERIC;
    v_brut NUMERIC;
    v_iskonto NUMERIC;
    v_birim TEXT;
    v_aciklama TEXT;
    v_sira INTEGER := 0;
    v_ad TEXT;
BEGIN
    IF v_uid IS NULL OR v_okul IS NULL OR public.dose_yetki('siparis') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Sipariş kaydetme yetkiniz yok.';
    END IF;
    IF jsonb_typeof(p_siparis) IS DISTINCT FROM 'object' OR jsonb_typeof(p_kalemler) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş bilgileri veya kalem listesi geçersiz.';
    END IF;
    IF jsonb_array_length(p_kalemler) NOT BETWEEN 1 AND 100 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Siparişte 1 ile 100 arasında kalem bulunmalıdır.';
    END IF;
    v_cari := nullif(p_siparis->>'cari_id', '')::INTEGER;
    v_bolum := nullif(p_siparis->>'bolum_id', '')::INTEGER;
    v_tarih := coalesce(nullif(p_siparis->>'tarih', '')::DATE, current_date);
    v_konu := nullif(btrim(p_siparis->>'konu'), '');
    v_esas := nullif(btrim(p_siparis->>'ucret_esasi'), '');
    v_kdv := coalesce(nullif(p_siparis->>'kdv_orani', '')::NUMERIC, 0.20);
    IF v_cari IS NULL OR NOT EXISTS (
        SELECT 1 FROM public.cari c WHERE c.id = v_cari AND c.okul_id = v_okul AND c.aktif = 1
          AND c.tur IN ('Müşteri', 'Müşteri ve Tedarikçi')) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Aktif bir müşteri seçiniz.';
    END IF;
    IF v_bolum IS NULL OR NOT EXISTS (
        SELECT 1 FROM public.bolum b WHERE b.id = v_bolum AND b.okul_id = v_okul AND b.aktif = 1) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Aktif bir bölüm / atölye seçiniz.';
    END IF;
    IF public.dose_bolum_kisitli() AND v_bolum IS DISTINCT FROM v_bolum_kisit THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Yalnız atandığınız bölüm için sipariş girebilirsiniz.';
    END IF;
    IF v_konu IS NULL OR v_esas IS NULL OR NOT EXISTS (
        SELECT 1 FROM public.secenek WHERE liste = 'ucret_esasi' AND deger = v_esas) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İşin konusu ve geçerli ücret esası zorunludur.';
    END IF;
    IF v_kdv::TEXT IN ('NaN', 'Infinity', '-Infinity') OR v_kdv < 0 OR v_kdv > 1 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'KDV oranı sonlu ve %0 ile %100 arasında olmalıdır.';
    END IF;
    SELECT ad_soyad INTO v_ad FROM dose_private.uyelik WHERE auth_user_id = v_uid AND okul_id = v_okul AND aktif;
    IF v_ad IS NULL THEN RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Aktif okul üyeliği bulunamadı.'; END IF;

    IF p_siparis_id IS NULL THEN
        INSERT INTO public.siparis (
            okul_id, siparis_no, tarih, cari_id, bolum_id, konu, ucret_esasi, kdv_orani,
            durum, aciklama, olusturan, guncelleyen
        ) VALUES (
            v_okul, format('SIP-%s-%s', to_char(v_tarih, 'YYYY'), lpad(dose_private.sira_no(v_okul, 'siparis', extract(year FROM v_tarih)::INTEGER)::TEXT, 5, '0')),
            v_tarih::TEXT, v_cari, v_bolum, v_konu, v_esas, v_kdv, 'Taslak',
            nullif(btrim(p_siparis->>'aciklama'), ''), v_uid, v_ad
        ) RETURNING * INTO v_siparis;
    ELSE
        SELECT * INTO v_siparis FROM public.siparis
        WHERE id = p_siparis_id AND okul_id = v_okul FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş bulunamadı.'; END IF;
        IF public.dose_bolum_kisitli() AND v_siparis.bolum_id IS DISTINCT FROM v_bolum_kisit THEN
            RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Bu bölümdeki siparişi düzenleme yetkiniz yok.';
        END IF;
        IF p_sur IS DISTINCT FROM v_siparis.surum THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş başka bir kullanıcı tarafından değiştirildi; güncelini yükleyin.',
                HINT = 'surum_cakismasi';
        END IF;
        IF v_siparis.durum NOT IN ('Taslak', 'İade Edildi') THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Onay sürecindeki veya imzalanmış sipariş değiştirilemez.';
        END IF;
        IF v_rol IN ('Alan Şefi', 'Öğretmen') AND v_siparis.olusturan IS DISTINCT FROM v_uid THEN
            RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Yalnız kendi oluşturduğunuz taslağı düzenleyebilirsiniz.';
        END IF;
        UPDATE public.siparis SET
            tarih = v_tarih::TEXT, cari_id = v_cari, bolum_id = v_bolum, konu = v_konu,
            ucret_esasi = v_esas, kdv_orani = v_kdv, durum = 'Taslak',
            aciklama = nullif(btrim(p_siparis->>'aciklama'), ''),
            surum = surum + 1, guncelleyen = v_ad
        WHERE id = p_siparis_id AND okul_id = v_okul RETURNING * INTO v_siparis;
        DELETE FROM public.siparis_kalem WHERE siparis_id = v_siparis.id AND okul_id = v_okul;
    END IF;

    FOR v_kalem IN SELECT value FROM jsonb_array_elements(p_kalemler) LOOP
        v_sira := v_sira + 1;
        v_urun := nullif(v_kalem->>'urun_id', '')::INTEGER;
        v_miktar := coalesce(nullif(v_kalem->>'miktar', '')::NUMERIC, 0);
        v_fiyat := coalesce(nullif(v_kalem->>'birim_fiyat', '')::NUMERIC, 0);
        v_iskonto_orani := coalesce(nullif(v_kalem->>'iskonto_orani', '')::NUMERIC, 0);
        v_aciklama := nullif(btrim(v_kalem->>'aciklama'), '');
        IF v_urun IS NOT NULL THEN
            SELECT u.ad, coalesce(nullif(v_kalem->>'birim', ''), u.birim),
                   coalesce(nullif(v_kalem->>'birim_fiyat', '')::NUMERIC, u.satis_fiyati, 0)
              INTO v_ad, v_birim, v_fiyat
            FROM public.urun u
            WHERE u.id = v_urun AND u.okul_id = v_okul AND u.aktif = 1
              AND (u.bolum_id IS NULL OR u.bolum_id = v_bolum);
            IF NOT FOUND THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. kalem: ürün bulunamadı veya bu bölümde kullanılamaz.', v_sira);
            END IF;
            v_aciklama := coalesce(v_aciklama, v_ad);
        ELSE
            v_birim := nullif(btrim(v_kalem->>'birim'), '');
        END IF;
        IF v_miktar::TEXT IN ('NaN', 'Infinity', '-Infinity')
           OR v_fiyat::TEXT IN ('NaN', 'Infinity', '-Infinity')
           OR v_iskonto_orani::TEXT IN ('NaN', 'Infinity', '-Infinity')
           OR v_miktar <= 0 OR v_fiyat < 0 OR v_iskonto_orani < 0 OR v_iskonto_orani > 1 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001',
                MESSAGE = format('%s. kalem: miktar pozitif, fiyat sıfır veya üstü ve indirim oranı 0 ile 1 arasında sonlu sayılar olmalıdır.', v_sira);
        END IF;
        IF v_aciklama IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. kalem için ürün veya açıklama giriniz.', v_sira);
        END IF;
        v_brut := round(v_miktar * v_fiyat, 2);
        v_iskonto := round(v_brut * v_iskonto_orani, 2);
        v_toplam := v_toplam + v_brut - v_iskonto;
        INSERT INTO public.siparis_kalem (
            okul_id, siparis_id, urun_id, aciklama, miktar, birim, birim_fiyat, iskonto_orani, iskonto
        ) VALUES (
            v_okul, v_siparis.id, v_urun, v_aciklama, v_miktar, coalesce(v_birim, 'Adet'),
            v_fiyat, v_iskonto_orani, v_iskonto
        );
    END LOOP;
    IF v_toplam <= 0 THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İndirim sonrası sipariş bedeli sıfırdan büyük olmalıdır.'; END IF;
    UPDATE public.siparis SET sozlesme_bedeli = v_toplam, malzeme_maliyeti = 0, iscilik_tutari = 0
    WHERE id = v_siparis.id AND okul_id = v_okul RETURNING * INTO v_siparis;
    PERFORM dose_private.log(v_okul, CASE WHEN p_siparis_id IS NULL THEN 'Sipariş taslağı oluşturuldu' ELSE 'Sipariş taslağı güncellendi' END,
                             'siparis', v_siparis.id,
                             format('%s · %s · %s TL', v_siparis.siparis_no, v_siparis.konu, round(v_toplam, 2)::TEXT));
    RETURN jsonb_build_object('id', v_siparis.id, 'siparis_no', v_siparis.siparis_no,
                              'surum', v_siparis.surum, 'sozlesme_bedeli', v_toplam);
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.siparis_asamasini_ilerlet(
    p_okul INTEGER, p_siparis_id INTEGER, p_asama INTEGER
) RETURNS INTEGER
LANGUAGE plpgsql VOLATILE SET search_path = '' AS $$
DECLARE
    v_onay public.onay_durum%ROWTYPE;
    v_asama INTEGER := p_asama;
    v_rol TEXT;
    v_asama_adi TEXT;
BEGIN
    SELECT * INTO STRICT v_onay FROM public.onay_durum
    WHERE okul_id = p_okul AND belge_turu = 'Sipariş' AND belge_id = p_siparis_id FOR UPDATE;
    v_rol := CASE v_asama WHEN 1 THEN 'Alan Şefi' WHEN 2 THEN 'Teknik Müdür Yardımcısı'
                          WHEN 3 THEN 'Okul Müdürü' END;
    IF v_rol IS NOT NULL AND v_onay.hazirlayan_rol = v_rol AND EXISTS (
        SELECT 1 FROM dose_private.uyelik u
        WHERE u.okul_id = p_okul AND u.auth_user_id = v_onay.hazirlayan_uid AND u.aktif
          AND u.rol = v_rol AND (v_asama <> 1 OR u.bolum_id = v_onay.bolum_id)
    ) THEN
        v_asama_adi := CASE v_asama WHEN 1 THEN 'Alan şefi uygun görüşü'
                                    WHEN 2 THEN 'Gerçekleştirme görevlisi kontrolü'
                                    WHEN 3 THEN 'Harcama yetkilisi onayı' END;
        INSERT INTO public.onay_kaydi (okul_id, belge_turu, belge_id, asama, asama_adi, karar, kullanici, ad_soyad, rol, zaman, aciklama)
        VALUES (p_okul, 'Sipariş', p_siparis_id, v_asama, v_asama_adi, 'Uygun (hazırlayan)',
                v_onay.hazirlayan_uid::TEXT, v_onay.hazirlayan, v_rol, dose_private.zaman(),
                'Siparişi hazırlayan kişinin kendi aşamasındaki uygun görüşü.');
        v_asama := v_asama + 1;
    END IF;
    UPDATE public.onay_durum SET asama = v_asama,
        durum = CASE WHEN v_asama > 3 THEN 'Onaylandı' ELSE 'Onay Bekliyor' END,
        guncelleme = dose_private.zaman()
    WHERE okul_id = p_okul AND belge_turu = 'Sipariş' AND belge_id = p_siparis_id;
    IF v_asama > 3 THEN
        UPDATE public.siparis SET durum = 'Sözleşme İmzalandı' WHERE id = p_siparis_id AND okul_id = p_okul;
    END IF;
    RETURN v_asama;
END;
$$;
REVOKE ALL ON FUNCTION dose_private.siparis_asamasini_ilerlet(INTEGER, INTEGER, INTEGER) FROM PUBLIC, anon, authenticated;

DROP FUNCTION public.dose_siparis_gonder(INTEGER, TEXT);
CREATE FUNCTION public.dose_siparis_gonder(
    p_siparis_id INTEGER, p_aciklama TEXT DEFAULT '', p_sur INTEGER DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_uid UUID := auth.uid();
    v_rol TEXT := public.dose_rol();
    v_ad TEXT;
    v_siparis public.siparis%ROWTYPE;
    v_asama INTEGER;
    v_tutar NUMERIC;
BEGIN
    IF v_uid IS NULL OR public.dose_yetki('siparis') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Siparişi onaya gönderme yetkiniz yok.';
    END IF;
    SELECT ad_soyad INTO v_ad FROM dose_private.uyelik
    WHERE auth_user_id = v_uid AND okul_id = v_okul AND aktif;
    SELECT * INTO v_siparis FROM public.siparis WHERE id = p_siparis_id AND okul_id = v_okul FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş bulunamadı.'; END IF;
    IF public.dose_bolum_kisitli() AND v_siparis.bolum_id IS DISTINCT FROM public.dose_bolum() THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Bu bölümdeki siparişi gönderme yetkiniz yok.';
    END IF;
    IF p_sur IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş sürümü gerekli; uygulamanızı güncelleyin.';
    END IF;
    IF p_sur IS DISTINCT FROM v_siparis.surum THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş değiştirildi; göndermeden önce güncelini inceleyin.', HINT = 'surum_cakismasi';
    END IF;
    IF v_siparis.durum NOT IN ('Taslak', 'İade Edildi') THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yalnız taslak veya iade edilmiş sipariş onaya gönderilebilir.';
    END IF;
    IF v_rol IN ('Alan Şefi', 'Öğretmen') AND v_siparis.olusturan IS DISTINCT FROM v_uid THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Yalnız kendi oluşturduğunuz siparişi gönderebilirsiniz.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.siparis_kalem WHERE siparis_id = v_siparis.id AND okul_id = v_okul)
       OR v_siparis.sozlesme_bedeli <= 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Onaya göndermek için geçerli en az bir sipariş kalemi gerekir.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.siparis_kalem k WHERE k.siparis_id = v_siparis.id AND k.okul_id = v_okul
          AND (k.miktar IS NULL OR k.birim_fiyat IS NULL OR k.iskonto_orani IS NULL OR k.iskonto IS NULL
               OR k.miktar::TEXT IN ('NaN', 'Infinity', '-Infinity')
               OR k.birim_fiyat::TEXT IN ('NaN', 'Infinity', '-Infinity')
               OR k.iskonto_orani::TEXT IN ('NaN', 'Infinity', '-Infinity')
               OR k.iskonto::TEXT IN ('NaN', 'Infinity', '-Infinity')
               OR k.miktar <= 0 OR k.birim_fiyat < 0 OR k.iskonto_orani NOT BETWEEN 0 AND 1)
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş kalemleri geçersiz; taslağı yeniden kaydedin.';
    END IF;
    SELECT sum(round(k.miktar::NUMERIC * k.birim_fiyat::NUMERIC, 2)
               - round(round(k.miktar::NUMERIC * k.birim_fiyat::NUMERIC, 2) * k.iskonto_orani::NUMERIC, 2))
    INTO v_tutar FROM public.siparis_kalem k WHERE k.siparis_id = v_siparis.id AND k.okul_id = v_okul;
    IF v_siparis.sozlesme_bedeli::TEXT IN ('NaN', 'Infinity', '-Infinity') OR v_tutar <= 0
       OR v_siparis.sozlesme_bedeli::NUMERIC IS DISTINCT FROM v_tutar OR EXISTS (
        SELECT 1 FROM public.siparis_kalem k WHERE k.siparis_id = v_siparis.id AND k.okul_id = v_okul
          AND k.iskonto::NUMERIC IS DISTINCT FROM
              round(round(k.miktar::NUMERIC * k.birim_fiyat::NUMERIC, 2) * k.iskonto_orani::NUMERIC, 2)
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş tutarları güncel hesapla uyuşmuyor; taslağı yeniden kaydedin.';
    END IF;
    INSERT INTO public.onay_durum (okul_id, belge_turu, belge_id, asama, durum, bolum_id, hazirlayan, hazirlayan_uid, hazirlayan_rol, guncelleme)
    VALUES (v_okul, 'Sipariş', v_siparis.id, 1, 'Onay Bekliyor', v_siparis.bolum_id, v_ad, v_uid, v_rol, dose_private.zaman())
    ON CONFLICT (belge_turu, belge_id) DO UPDATE SET
        okul_id = EXCLUDED.okul_id, asama = 1, durum = 'Onay Bekliyor', bolum_id = EXCLUDED.bolum_id,
        hazirlayan = EXCLUDED.hazirlayan, hazirlayan_uid = EXCLUDED.hazirlayan_uid,
        hazirlayan_rol = EXCLUDED.hazirlayan_rol, guncelleme = EXCLUDED.guncelleme;
    UPDATE public.siparis SET durum = 'Onay Bekliyor', surum = surum + 1, guncelleyen = v_ad
    WHERE id = v_siparis.id AND okul_id = v_okul;
    INSERT INTO public.onay_kaydi (okul_id, belge_turu, belge_id, asama, asama_adi, karar, kullanici, ad_soyad, rol, zaman, aciklama)
    VALUES (v_okul, 'Sipariş', v_siparis.id, 0, 'Hazırlama', 'Onaya gönderildi', v_uid::TEXT, v_ad, v_rol,
            dose_private.zaman(), nullif(btrim(p_aciklama), ''));
    v_asama := dose_private.siparis_asamasini_ilerlet(v_okul, v_siparis.id, 1);
    PERFORM dose_private.log(v_okul, 'Sipariş onaya gönderildi', 'siparis', v_siparis.id,
                             format('%s · bekleyen aşama: %s', v_siparis.siparis_no, v_asama));
    RETURN jsonb_build_object('basarili', true, 'asama', v_asama, 'durum', 'Onay Bekliyor');
END;
$$;

DROP FUNCTION public.dose_siparis_karar(INTEGER, BOOLEAN, TEXT);
CREATE FUNCTION public.dose_siparis_karar(
    p_siparis_id INTEGER, p_onayla BOOLEAN, p_aciklama TEXT DEFAULT '', p_sur INTEGER DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_uid UUID := auth.uid();
    v_rol TEXT := public.dose_rol();
    v_ad TEXT;
    v_siparis public.siparis%ROWTYPE;
    v_onay public.onay_durum%ROWTYPE;
    v_asama_adi TEXT;
    v_beklenen_rol TEXT;
    v_son_kayit INTEGER;
    v_asama INTEGER;
    i INTEGER;
BEGIN
    IF v_uid IS NULL OR public.dose_yetki('siparis') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Sipariş için karar verme yetkiniz yok.';
    END IF;
    IF p_onayla IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Onay kararı zorunludur.';
    END IF;
    SELECT ad_soyad INTO v_ad FROM dose_private.uyelik WHERE auth_user_id = v_uid AND okul_id = v_okul AND aktif;
    SELECT * INTO v_siparis FROM public.siparis WHERE id = p_siparis_id AND okul_id = v_okul FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş bulunamadı.'; END IF;
    IF public.dose_bolum_kisitli() AND v_siparis.bolum_id IS DISTINCT FROM public.dose_bolum() THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Bu bölümdeki siparişe karar verme yetkiniz yok.';
    END IF;
    IF p_sur IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş sürümü gerekli; uygulamanızı güncelleyin.';
    END IF;
    IF p_sur IS DISTINCT FROM v_siparis.surum THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş değiştirildi; karar vermeden önce güncelini inceleyin.', HINT = 'surum_cakismasi';
    END IF;
    SELECT * INTO v_onay FROM public.onay_durum
    WHERE okul_id = v_okul AND belge_turu = 'Sipariş' AND belge_id = v_siparis.id FOR UPDATE;
    IF NOT FOUND OR v_onay.durum <> 'Onay Bekliyor' OR v_onay.asama NOT BETWEEN 1 AND 3
       OR v_siparis.durum <> 'Onay Bekliyor' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu sipariş için bekleyen bir onay aşaması yok.';
    END IF;
    v_beklenen_rol := CASE v_onay.asama WHEN 1 THEN 'Alan Şefi'
                                        WHEN 2 THEN 'Teknik Müdür Yardımcısı'
                                        WHEN 3 THEN 'Okul Müdürü' END;
    IF v_rol IS DISTINCT FROM v_beklenen_rol
       OR (v_onay.asama = 1 AND public.dose_bolum() IS DISTINCT FROM v_siparis.bolum_id) THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = format('Bu aşamada yalnız %s karar verebilir.', v_beklenen_rol);
    END IF;
    IF v_siparis.olusturan = v_uid THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Siparişi hazırlayan kişi kendi siparişini onaylayamaz.';
    END IF;
    IF NOT p_onayla AND nullif(btrim(p_aciklama), '') IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İade gerekçesini yazınız.';
    END IF;
    SELECT max(id) INTO v_son_kayit FROM public.onay_kaydi
    WHERE okul_id = v_okul AND belge_turu = 'Sipariş' AND belge_id = v_siparis.id AND karar = 'Onaya gönderildi';
    IF v_son_kayit IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Gönderim geçmişi eksik; siparişi geri çekip yeniden gönderin.';
    END IF;
    FOR i IN 1..(v_onay.asama - 1) LOOP
        SELECT min(id) INTO v_son_kayit FROM public.onay_kaydi
        WHERE okul_id = v_okul AND belge_turu = 'Sipariş' AND belge_id = v_siparis.id
          AND asama = i AND karar IN ('Uygun', 'Uygun (hazırlayan)') AND id > v_son_kayit;
        IF v_son_kayit IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Önceki onaylar eksik veya sırasız; siparişi geri çekip yeniden gönderin.';
        END IF;
    END LOOP;
    v_asama_adi := CASE v_onay.asama WHEN 1 THEN 'Alan şefi uygun görüşü'
                                     WHEN 2 THEN 'Gerçekleştirme görevlisi kontrolü'
                                     WHEN 3 THEN 'Harcama yetkilisi onayı' END;
    INSERT INTO public.onay_kaydi (okul_id, belge_turu, belge_id, asama, asama_adi, karar, kullanici, ad_soyad, rol, zaman, aciklama)
    VALUES (v_okul, 'Sipariş', v_siparis.id, v_onay.asama, v_asama_adi,
            CASE WHEN p_onayla THEN 'Uygun' ELSE 'İade edildi' END, v_uid::TEXT, v_ad, v_rol,
            dose_private.zaman(), nullif(btrim(p_aciklama), ''));
    UPDATE public.siparis SET surum = surum + 1, guncelleyen = v_ad WHERE id = v_siparis.id AND okul_id = v_okul;
    IF NOT p_onayla THEN
        UPDATE public.onay_durum SET asama = 0, durum = 'İade Edildi', guncelleme = dose_private.zaman()
        WHERE okul_id = v_okul AND belge_turu = 'Sipariş' AND belge_id = v_siparis.id;
        UPDATE public.siparis SET durum = 'İade Edildi' WHERE id = v_siparis.id AND okul_id = v_okul;
        PERFORM dose_private.log(v_okul, 'Sipariş iade edildi', 'siparis', v_siparis.id,
                                 format('%s · %s', v_siparis.siparis_no, btrim(p_aciklama)));
        RETURN jsonb_build_object('basarili', true, 'durum', 'İade Edildi');
    END IF;
    v_asama := dose_private.siparis_asamasini_ilerlet(v_okul, v_siparis.id, v_onay.asama + 1);
    IF v_asama > 3 THEN
        PERFORM dose_private.log(v_okul, 'Sipariş onaylandı', 'siparis', v_siparis.id, v_siparis.siparis_no);
        RETURN jsonb_build_object('basarili', true, 'durum', 'Onaylandı');
    END IF;
    PERFORM dose_private.log(v_okul, 'Sipariş onay aşaması tamamlandı', 'siparis', v_siparis.id,
                             format('%s · %s', v_siparis.siparis_no, v_asama_adi));
    RETURN jsonb_build_object('basarili', true, 'asama', v_asama, 'durum', 'Onay Bekliyor');
END;
$$;

DROP FUNCTION public.dose_siparis_geri_cek(INTEGER, TEXT);
CREATE FUNCTION public.dose_siparis_geri_cek(
    p_siparis_id INTEGER, p_aciklama TEXT DEFAULT '', p_sur INTEGER DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_uid UUID := auth.uid();
    v_rol TEXT := public.dose_rol();
    v_ad TEXT;
    v_siparis public.siparis%ROWTYPE;
    v_onay public.onay_durum%ROWTYPE;
BEGIN
    IF v_uid IS NULL OR public.dose_yetki('siparis') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Siparişi geri çekme yetkiniz yok.';
    END IF;
    SELECT ad_soyad INTO v_ad FROM dose_private.uyelik WHERE auth_user_id = v_uid AND okul_id = v_okul AND aktif;
    SELECT * INTO v_siparis FROM public.siparis WHERE id = p_siparis_id AND okul_id = v_okul FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş bulunamadı.'; END IF;
    IF public.dose_bolum_kisitli() AND v_siparis.bolum_id IS DISTINCT FROM public.dose_bolum() THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Bu bölümdeki siparişi geri çekme yetkiniz yok.';
    END IF;
    IF p_sur IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş sürümü gerekli; uygulamanızı güncelleyin.';
    END IF;
    IF p_sur IS DISTINCT FROM v_siparis.surum THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş değiştirildi; geri çekmeden önce güncelini inceleyin.', HINT = 'surum_cakismasi';
    END IF;
    SELECT * INTO v_onay FROM public.onay_durum
    WHERE okul_id = v_okul AND belge_turu = 'Sipariş' AND belge_id = v_siparis.id FOR UPDATE;
    IF NOT FOUND OR v_onay.durum <> 'Onay Bekliyor' OR v_siparis.durum <> 'Onay Bekliyor' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yalnız onay bekleyen sipariş geri çekilebilir.';
    END IF;
    IF v_siparis.olusturan IS DISTINCT FROM v_uid AND v_rol NOT IN ('Okul Müdürü', 'Sistem Yöneticisi') THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Siparişi yalnız hazırlayan kişi veya Okul Müdürü geri çekebilir.';
    END IF;
    INSERT INTO public.onay_kaydi (okul_id, belge_turu, belge_id, asama, asama_adi, karar, kullanici, ad_soyad, rol, zaman, aciklama)
    VALUES (v_okul, 'Sipariş', v_siparis.id, v_onay.asama, 'Onay süreci', 'Geri çekildi',
            v_uid::TEXT, v_ad, v_rol, dose_private.zaman(), nullif(btrim(p_aciklama), ''));
    UPDATE public.onay_durum SET asama = 0, durum = 'Geri Çekildi', guncelleme = dose_private.zaman()
    WHERE okul_id = v_okul AND belge_turu = 'Sipariş' AND belge_id = v_siparis.id;
    UPDATE public.siparis SET durum = 'Taslak', surum = surum + 1, guncelleyen = v_ad
    WHERE id = v_siparis.id AND okul_id = v_okul;
    PERFORM dose_private.log(v_okul, 'Sipariş onaydan geri çekildi', 'siparis', v_siparis.id, v_siparis.siparis_no);
    RETURN jsonb_build_object('basarili', true, 'durum', 'Taslak');
END;
$$;

REVOKE ALL ON FUNCTION public.dose_siparis_gonder(INTEGER, TEXT, INTEGER),
    public.dose_siparis_karar(INTEGER, BOOLEAN, TEXT, INTEGER),
    public.dose_siparis_geri_cek(INTEGER, TEXT, INTEGER) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_siparis_gonder(INTEGER, TEXT, INTEGER),
    public.dose_siparis_karar(INTEGER, BOOLEAN, TEXT, INTEGER),
    public.dose_siparis_geri_cek(INTEGER, TEXT, INTEGER) TO authenticated;
