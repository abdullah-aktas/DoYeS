-- Supabase-backed order drafts and a server-enforced, append-only approval trail.
-- Orders are operational commitments, not accounting events; journals are created with invoices/payments.

INSERT INTO dose_private.sayfa_yetki (sayfa, baslik, kodlar)
VALUES ('siparis', 'Siparişler / İş Emirleri', 'yyygyyyg')
ON CONFLICT (sayfa) DO UPDATE SET baslik = EXCLUDED.baslik, kodlar = EXCLUDED.kodlar;

ALTER TABLE public.siparis
    ADD COLUMN IF NOT EXISTS olusturan UUID REFERENCES auth.users(id),
    ADD COLUMN IF NOT EXISTS guncelleyen TEXT,
    ADD COLUMN IF NOT EXISTS surum INTEGER NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS ix_siparis_okul_bolum_tarih ON public.siparis (okul_id, bolum_id, tarih DESC);
CREATE INDEX IF NOT EXISTS ix_onay_kaydi_okul_tur_belge ON public.onay_kaydi (okul_id, belge_turu, belge_id, id);

CREATE OR REPLACE FUNCTION dose_private.onay_kaydi_degismez() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Onay geçmişi değiştirilemez veya silinemez.';
END;
$$;

DROP TRIGGER IF EXISTS dose_onay_kaydi_degismez ON public.onay_kaydi;
CREATE TRIGGER dose_onay_kaydi_degismez BEFORE UPDATE OR DELETE ON public.onay_kaydi
    FOR EACH ROW EXECUTE FUNCTION dose_private.onay_kaydi_degismez();

REVOKE ALL ON public.siparis, public.siparis_kalem, public.onay_durum, public.onay_kaydi
    FROM anon, authenticated;
GRANT SELECT ON public.siparis, public.siparis_kalem, public.onay_durum, public.onay_kaydi TO authenticated;

DROP POLICY IF EXISTS siparis_okuma ON public.siparis;
CREATE POLICY siparis_okuma ON public.siparis FOR SELECT TO authenticated
    USING (okul_id = (SELECT public.dose_okul())
           AND (SELECT public.dose_yetki('siparis')) <> ''
           AND (NOT (SELECT public.dose_bolum_kisitli()) OR bolum_id = (SELECT public.dose_bolum())));

DROP POLICY IF EXISTS siparis_kalem_okuma ON public.siparis_kalem;
CREATE POLICY siparis_kalem_okuma ON public.siparis_kalem FOR SELECT TO authenticated
    USING (okul_id = (SELECT public.dose_okul())
           AND EXISTS (SELECT 1 FROM public.siparis s
                       WHERE s.id = siparis_kalem.siparis_id AND s.okul_id = public.dose_okul()
                         AND (NOT public.dose_bolum_kisitli() OR s.bolum_id = public.dose_bolum())));

DROP POLICY IF EXISTS onay_durum_okuma ON public.onay_durum;
CREATE POLICY onay_durum_okuma ON public.onay_durum FOR SELECT TO authenticated
    USING (okul_id = (SELECT public.dose_okul())
           AND belge_turu = 'Sipariş'
           AND (SELECT public.dose_yetki('siparis')) <> ''
           AND (NOT (SELECT public.dose_bolum_kisitli()) OR bolum_id = (SELECT public.dose_bolum())));

DROP POLICY IF EXISTS onay_kaydi_okuma ON public.onay_kaydi;
CREATE POLICY onay_kaydi_okuma ON public.onay_kaydi FOR SELECT TO authenticated
    USING (okul_id = (SELECT public.dose_okul())
           AND belge_turu = 'Sipariş'
           AND (SELECT public.dose_yetki('siparis')) <> ''
           AND EXISTS (SELECT 1 FROM public.siparis s
                       WHERE s.id = onay_kaydi.belge_id AND s.okul_id = public.dose_okul()
                         AND (NOT public.dose_bolum_kisitli() OR s.bolum_id = public.dose_bolum())));

CREATE OR REPLACE FUNCTION public.dose_siparis_veri() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_bolum INTEGER := public.dose_bolum();
    v_kisitli BOOLEAN := public.dose_bolum_kisitli();
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('siparis') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Sipariş ekranına erişim yetkiniz yok.';
    END IF;
    RETURN jsonb_build_object(
        'cariler', coalesce((SELECT jsonb_agg(jsonb_build_object('id', c.id, 'kod', c.kod, 'unvan', c.unvan, 'tur', c.tur)
                                               ORDER BY c.unvan)
                            FROM public.cari c
                            WHERE c.okul_id = v_okul AND c.aktif = 1
                              AND c.tur IN ('Müşteri', 'Müşteri ve Tedarikçi')), '[]'::JSONB),
        'bolumler', coalesce((SELECT jsonb_agg(jsonb_build_object('id', b.id, 'kod', b.kod, 'ad', b.ad)
                                                ORDER BY b.ad)
                              FROM public.bolum b
                              WHERE b.okul_id = v_okul AND b.aktif = 1
                                AND (NOT v_kisitli OR b.id = v_bolum)), '[]'::JSONB),
        'urunler', coalesce((SELECT jsonb_agg(jsonb_build_object('id', u.id, 'kod', u.kod, 'ad', u.ad, 'birim', u.birim,
                                                                  'satis_fiyati', u.satis_fiyati, 'kdv_orani', u.kdv_orani,
                                                                  'bolum_id', u.bolum_id)
                                              ORDER BY u.ad)
                             FROM public.urun u
                             WHERE u.okul_id = v_okul AND u.aktif = 1
                               AND (NOT v_kisitli OR u.bolum_id IS NULL OR u.bolum_id = v_bolum)), '[]'::JSONB));
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
        SELECT jsonb_agg(
            jsonb_build_object(
                'id', s.id, 'siparis_no', s.siparis_no, 'tarih', s.tarih, 'cari_id', s.cari_id,
                'cari_unvan', c.unvan, 'bolum_id', s.bolum_id, 'bolum_ad', b.ad, 'konu', s.konu,
                'ucret_esasi', s.ucret_esasi, 'sozlesme_bedeli', s.sozlesme_bedeli, 'kdv_orani', s.kdv_orani,
                'durum', s.durum, 'surum', s.surum, 'aciklama', s.aciklama,
                'olusturan', s.olusturan, 'benim', s.olusturan = auth.uid(),
                'onay_asamasi', coalesce(o.asama, 0), 'onay_durumu', coalesce(o.durum, s.durum),
                'bekleyen_rol', CASE o.asama WHEN 1 THEN 'Alan Şefi' WHEN 2 THEN 'Teknik Müdür Yardımcısı'
                                              WHEN 3 THEN 'Okul Müdürü' END,
                'kalemler', coalesce((SELECT jsonb_agg(jsonb_build_object(
                                          'id', k.id, 'urun_id', k.urun_id, 'aciklama', k.aciklama,
                                          'miktar', k.miktar, 'birim', k.birim, 'birim_fiyat', k.birim_fiyat,
                                          'iskonto_orani', k.iskonto_orani, 'iskonto', k.iskonto)
                                          ORDER BY k.id)
                                      FROM public.siparis_kalem k
                                      WHERE k.siparis_id = s.id AND k.okul_id = v_okul), '[]'::JSONB),
                'gecmis', coalesce((SELECT jsonb_agg(jsonb_build_object(
                                         'asama', a.asama, 'asama_adi', a.asama_adi, 'karar', a.karar,
                                         'ad_soyad', a.ad_soyad, 'rol', a.rol, 'zaman', a.zaman,
                                         'aciklama', a.aciklama) ORDER BY a.id)
                                     FROM public.onay_kaydi a
                                     WHERE a.okul_id = v_okul AND a.belge_turu = 'Sipariş' AND a.belge_id = s.id),
                                    '[]'::JSONB))
            ORDER BY s.tarih DESC, s.id DESC)
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
    v_iskonto NUMERIC;
    v_birim TEXT;
    v_aciklama TEXT;
    v_sira INTEGER := 0;
    v_ad TEXT;
    v_id INTEGER;
BEGIN
    IF v_uid IS NULL OR v_okul IS NULL OR public.dose_yetki('siparis') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Sipariş kaydetme yetkiniz yok.';
    END IF;
    IF jsonb_typeof(p_siparis) <> 'object' OR jsonb_typeof(p_kalemler) <> 'array'
       OR jsonb_array_length(p_kalemler) < 1 OR jsonb_array_length(p_kalemler) > 100 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş bilgileri veya kalem listesi geçersiz.';
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
    IF public.dose_bolum_kisitli() AND v_bolum <> v_bolum_kisit THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Yalnız atandığınız bölüm için sipariş girebilirsiniz.';
    END IF;
    IF v_konu IS NULL OR v_esas IS NULL OR NOT EXISTS (
        SELECT 1 FROM public.secenek WHERE liste = 'ucret_esasi' AND deger = v_esas) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İşin konusu ve geçerli ücret esası zorunludur.';
    END IF;
    IF v_kdv < 0 OR v_kdv > 1 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'KDV oranı %0 ile %100 arasında olmalıdır.';
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
        IF p_sur IS DISTINCT FROM v_siparis.surum THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş başka bir kullanıcı tarafından değiştirildi; güncelini yükleyin.',
                HINT = 'surum_cakismasi';
        END IF;
        IF v_siparis.durum NOT IN ('Taslak', 'İade Edildi') THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Onay sürecindeki veya imzalanmış sipariş değiştirilemez.';
        END IF;
        IF v_rol IN ('Alan Şefi', 'Öğretmen') AND v_siparis.olusturan <> v_uid THEN
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
        IF v_miktar <= 0 OR v_fiyat < 0 OR v_iskonto_orani < 0 OR v_iskonto_orani > 1 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001',
                MESSAGE = format('%s. kalem: miktar pozitif, fiyat sıfır veya üstü ve indirim oranı 0 ile 1 arasında olmalıdır.', v_sira);
        END IF;
        IF v_aciklama IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. kalem için ürün veya açıklama giriniz.', v_sira);
        END IF;
        v_iskonto := round(v_miktar * v_fiyat * v_iskonto_orani, 2);
        v_toplam := v_toplam + round(v_miktar * v_fiyat, 2) - v_iskonto;
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

CREATE OR REPLACE FUNCTION public.dose_siparis_gonder(p_siparis_id INTEGER, p_aciklama TEXT DEFAULT '') RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_uid UUID := auth.uid();
    v_rol TEXT := public.dose_rol();
    v_ad TEXT;
    v_siparis public.siparis%ROWTYPE;
    v_asama INTEGER := 1;
    v_asama_adi TEXT;
    v_kendisi BOOLEAN := FALSE;
BEGIN
    IF v_uid IS NULL OR public.dose_yetki('siparis') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Siparişi onaya gönderme yetkiniz yok.';
    END IF;
    SELECT ad_soyad INTO v_ad FROM dose_private.uyelik
    WHERE auth_user_id = v_uid AND okul_id = v_okul AND aktif;
    SELECT * INTO v_siparis FROM public.siparis
    WHERE id = p_siparis_id AND okul_id = v_okul FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş bulunamadı.'; END IF;
    IF v_siparis.durum NOT IN ('Taslak', 'İade Edildi') THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yalnız taslak veya iade edilmiş sipariş onaya gönderilebilir.';
    END IF;
    IF v_rol IN ('Alan Şefi', 'Öğretmen') AND v_siparis.olusturan <> v_uid THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Yalnız kendi oluşturduğunuz siparişi gönderebilirsiniz.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.siparis_kalem WHERE siparis_id = v_siparis.id AND okul_id = v_okul)
       OR v_siparis.sozlesme_bedeli <= 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Onaya göndermek için geçerli en az bir sipariş kalemi gerekir.';
    END IF;

    INSERT INTO public.onay_durum (okul_id, belge_turu, belge_id, asama, durum, bolum_id, hazirlayan, guncelleme)
    VALUES (v_okul, 'Sipariş', v_siparis.id, 1, 'Onay Bekliyor', v_siparis.bolum_id, v_ad, dose_private.zaman())
    ON CONFLICT (belge_turu, belge_id) DO UPDATE SET
        okul_id = EXCLUDED.okul_id, asama = 1, durum = 'Onay Bekliyor',
        bolum_id = EXCLUDED.bolum_id, hazirlayan = EXCLUDED.hazirlayan, guncelleme = EXCLUDED.guncelleme;
    UPDATE public.siparis SET durum = 'Onay Bekliyor' WHERE id = v_siparis.id AND okul_id = v_okul;
    INSERT INTO public.onay_kaydi (okul_id, belge_turu, belge_id, asama, asama_adi, karar, kullanici, ad_soyad, rol, zaman, aciklama)
    VALUES (v_okul, 'Sipariş', v_siparis.id, 0, 'Hazırlama', 'Onaya gönderildi', v_uid::TEXT, v_ad, v_rol,
            dose_private.zaman(), nullif(btrim(p_aciklama), ''));

    v_kendisi := v_rol = 'Alan Şefi' AND v_siparis.bolum_id = public.dose_bolum();
    IF v_kendisi THEN
        INSERT INTO public.onay_kaydi (okul_id, belge_turu, belge_id, asama, asama_adi, karar, kullanici, ad_soyad, rol, zaman, aciklama)
        VALUES (v_okul, 'Sipariş', v_siparis.id, 1, 'Alan şefi uygun görüşü', 'Uygun (hazırlayan)',
                v_uid::TEXT, v_ad, v_rol, dose_private.zaman(), 'Siparişi hazırlayan alan şefinin uygun görüşü.');
        v_asama := 2;
    ELSIF v_rol = 'Teknik Müdür Yardımcısı' THEN
        INSERT INTO public.onay_kaydi (okul_id, belge_turu, belge_id, asama, asama_adi, karar, kullanici, ad_soyad, rol, zaman, aciklama)
        VALUES (v_okul, 'Sipariş', v_siparis.id, 2, 'Gerçekleştirme görevlisi kontrolü', 'Uygun (hazırlayan)',
                v_uid::TEXT, v_ad, v_rol, dose_private.zaman(), 'Siparişi hazırlayan gerçekleştirme görevlisinin kontrolü.');
        v_asama := 3;
    ELSIF v_rol = 'Okul Müdürü' THEN
        INSERT INTO public.onay_kaydi (okul_id, belge_turu, belge_id, asama, asama_adi, karar, kullanici, ad_soyad, rol, zaman, aciklama)
        VALUES (v_okul, 'Sipariş', v_siparis.id, 3, 'Harcama yetkilisi onayı', 'Uygun (hazırlayan)',
                v_uid::TEXT, v_ad, v_rol, dose_private.zaman(), 'Siparişi hazırlayan harcama yetkilisinin onayı.');
        v_asama := 4;
    END IF;
    IF v_asama > 3 THEN
        UPDATE public.onay_durum SET asama = 4, durum = 'Onaylandı', guncelleme = dose_private.zaman()
        WHERE okul_id = v_okul AND belge_turu = 'Sipariş' AND belge_id = v_siparis.id;
        UPDATE public.siparis SET durum = 'Sözleşme İmzalandı'
        WHERE id = v_siparis.id AND okul_id = v_okul;
    ELSE
        UPDATE public.onay_durum SET asama = v_asama, guncelleme = dose_private.zaman()
        WHERE okul_id = v_okul AND belge_turu = 'Sipariş' AND belge_id = v_siparis.id;
    END IF;
    SELECT CASE v_asama WHEN 1 THEN 'Alan şefi uygun görüşü'
                        WHEN 2 THEN 'Gerçekleştirme görevlisi kontrolü'
                        WHEN 3 THEN 'Harcama yetkilisi onayı' ELSE 'Tamamlandı' END INTO v_asama_adi;
    PERFORM dose_private.log(v_okul, 'Sipariş onaya gönderildi', 'siparis', v_siparis.id,
                             format('%s · bekleyen aşama: %s', v_siparis.siparis_no, v_asama_adi));
    RETURN jsonb_build_object('basarili', true, 'asama', v_asama, 'durum', CASE WHEN v_asama > 3 THEN 'Onaylandı' ELSE 'Onay Bekliyor' END);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_siparis_karar(
    p_siparis_id INTEGER, p_onayla BOOLEAN, p_aciklama TEXT DEFAULT ''
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
BEGIN
    IF v_uid IS NULL THEN RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Önce giriş yapın.'; END IF;
    SELECT ad_soyad INTO v_ad FROM dose_private.uyelik
    WHERE auth_user_id = v_uid AND okul_id = v_okul AND aktif;
    SELECT * INTO v_siparis FROM public.siparis
    WHERE id = p_siparis_id AND okul_id = v_okul FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş bulunamadı.'; END IF;
    SELECT * INTO v_onay FROM public.onay_durum
    WHERE okul_id = v_okul AND belge_turu = 'Sipariş' AND belge_id = v_siparis.id FOR UPDATE;
    IF NOT FOUND OR v_onay.durum <> 'Onay Bekliyor' OR v_onay.asama NOT BETWEEN 1 AND 3 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu sipariş için bekleyen bir onay aşaması yok.';
    END IF;
    v_beklenen_rol := CASE v_onay.asama WHEN 1 THEN 'Alan Şefi'
                                        WHEN 2 THEN 'Teknik Müdür Yardımcısı'
                                        WHEN 3 THEN 'Okul Müdürü' END;
    IF v_rol <> v_beklenen_rol
       OR (v_onay.asama = 1 AND public.dose_bolum() IS DISTINCT FROM v_siparis.bolum_id) THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = format('Bu aşamada yalnız %s karar verebilir.', v_beklenen_rol);
    END IF;
    IF v_siparis.olusturan = v_uid THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Siparişi hazırlayan kişi kendi siparişini onaylayamaz.';
    END IF;
    IF NOT p_onayla AND nullif(btrim(p_aciklama), '') IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İade gerekçesini yazınız.';
    END IF;
    v_asama_adi := CASE v_onay.asama WHEN 1 THEN 'Alan şefi uygun görüşü'
                                     WHEN 2 THEN 'Gerçekleştirme görevlisi kontrolü'
                                     WHEN 3 THEN 'Harcama yetkilisi onayı' END;
    INSERT INTO public.onay_kaydi (okul_id, belge_turu, belge_id, asama, asama_adi, karar, kullanici, ad_soyad, rol, zaman, aciklama)
    VALUES (v_okul, 'Sipariş', v_siparis.id, v_onay.asama, v_asama_adi,
            CASE WHEN p_onayla THEN 'Uygun' ELSE 'İade edildi' END, v_uid::TEXT, v_ad, v_rol,
            dose_private.zaman(), nullif(btrim(p_aciklama), ''));
    IF NOT p_onayla THEN
        UPDATE public.onay_durum SET asama = 0, durum = 'İade Edildi', guncelleme = dose_private.zaman()
        WHERE okul_id = v_okul AND belge_turu = 'Sipariş' AND belge_id = v_siparis.id;
        UPDATE public.siparis SET durum = 'İade Edildi' WHERE id = v_siparis.id AND okul_id = v_okul;
        PERFORM dose_private.log(v_okul, 'Sipariş iade edildi', 'siparis', v_siparis.id,
                                 format('%s · %s', v_siparis.siparis_no, btrim(p_aciklama)));
        RETURN jsonb_build_object('basarili', true, 'durum', 'İade Edildi');
    END IF;
    IF v_onay.asama = 3 THEN
        UPDATE public.onay_durum SET asama = 4, durum = 'Onaylandı', guncelleme = dose_private.zaman()
        WHERE okul_id = v_okul AND belge_turu = 'Sipariş' AND belge_id = v_siparis.id;
        UPDATE public.siparis SET durum = 'Sözleşme İmzalandı' WHERE id = v_siparis.id AND okul_id = v_okul;
        PERFORM dose_private.log(v_okul, 'Sipariş onaylandı', 'siparis', v_siparis.id, v_siparis.siparis_no);
        RETURN jsonb_build_object('basarili', true, 'durum', 'Onaylandı');
    END IF;
    UPDATE public.onay_durum SET asama = v_onay.asama + 1, guncelleme = dose_private.zaman()
    WHERE okul_id = v_okul AND belge_turu = 'Sipariş' AND belge_id = v_siparis.id;
    PERFORM dose_private.log(v_okul, 'Sipariş onay aşaması tamamlandı', 'siparis', v_siparis.id,
                             format('%s · %s', v_siparis.siparis_no, v_asama_adi));
    RETURN jsonb_build_object('basarili', true, 'asama', v_onay.asama + 1, 'durum', 'Onay Bekliyor');
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_siparis_geri_cek(p_siparis_id INTEGER, p_aciklama TEXT DEFAULT '') RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_uid UUID := auth.uid();
    v_rol TEXT := public.dose_rol();
    v_ad TEXT;
    v_siparis public.siparis%ROWTYPE;
    v_onay public.onay_durum%ROWTYPE;
BEGIN
    IF v_uid IS NULL THEN RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Önce giriş yapın.'; END IF;
    SELECT ad_soyad INTO v_ad FROM dose_private.uyelik
    WHERE auth_user_id = v_uid AND okul_id = v_okul AND aktif;
    SELECT * INTO v_siparis FROM public.siparis
    WHERE id = p_siparis_id AND okul_id = v_okul FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Sipariş bulunamadı.'; END IF;
    SELECT * INTO v_onay FROM public.onay_durum
    WHERE okul_id = v_okul AND belge_turu = 'Sipariş' AND belge_id = v_siparis.id FOR UPDATE;
    IF NOT FOUND OR v_onay.durum <> 'Onay Bekliyor' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yalnız onay bekleyen sipariş geri çekilebilir.';
    END IF;
    IF v_siparis.olusturan <> v_uid AND v_rol NOT IN ('Okul Müdürü', 'Sistem Yöneticisi') THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Siparişi yalnız hazırlayan kişi veya Okul Müdürü geri çekebilir.';
    END IF;
    INSERT INTO public.onay_kaydi (okul_id, belge_turu, belge_id, asama, asama_adi, karar, kullanici, ad_soyad, rol, zaman, aciklama)
    VALUES (v_okul, 'Sipariş', v_siparis.id, v_onay.asama, 'Onay süreci', 'Geri çekildi',
            v_uid::TEXT, v_ad, v_rol, dose_private.zaman(), nullif(btrim(p_aciklama), ''));
    UPDATE public.onay_durum SET asama = 0, durum = 'Geri Çekildi', guncelleme = dose_private.zaman()
    WHERE okul_id = v_okul AND belge_turu = 'Sipariş' AND belge_id = v_siparis.id;
    UPDATE public.siparis SET durum = 'Taslak' WHERE id = v_siparis.id AND okul_id = v_okul;
    PERFORM dose_private.log(v_okul, 'Sipariş onaydan geri çekildi', 'siparis', v_siparis.id, v_siparis.siparis_no);
    RETURN jsonb_build_object('basarili', true, 'durum', 'Taslak');
END;
$$;

REVOKE ALL ON FUNCTION public.dose_siparis_veri(), public.dose_siparisler(),
    public.dose_siparis_kaydet(INTEGER, INTEGER, JSONB, JSONB),
    public.dose_siparis_gonder(INTEGER, TEXT), public.dose_siparis_karar(INTEGER, BOOLEAN, TEXT),
    public.dose_siparis_geri_cek(INTEGER, TEXT) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_siparis_veri(), public.dose_siparisler(),
    public.dose_siparis_kaydet(INTEGER, INTEGER, JSONB, JSONB),
    public.dose_siparis_gonder(INTEGER, TEXT), public.dose_siparis_karar(INTEGER, BOOLEAN, TEXT),
    public.dose_siparis_geri_cek(INTEGER, TEXT) TO authenticated;
