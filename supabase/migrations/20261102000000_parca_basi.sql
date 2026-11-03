-- Parça başı hakediş (Yön. md.8): Ek-3 ön maliyet, günlük parça puantajı, kuruş hassas dağıtım,
-- öğretmen/öğrenci bordroları, Alan Şefi -> Teknik Müdür Yardımcısı -> Okul Müdürü onayı,
-- tahakkuk yevmiyesi ve saymanın bankadan ödemesi.

INSERT INTO dose_private.sayfa_yetki (sayfa, baslik, kodlar)
VALUES ('parca_basi', 'Parça Başı Hakediş', 'gyyyyggg')
ON CONFLICT (sayfa) DO UPDATE SET baslik = EXCLUDED.baslik, kodlar = EXCLUDED.kodlar;

CREATE TABLE dose_private.pb_hakedis (
    id SERIAL PRIMARY KEY,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    siparis_id INTEGER NOT NULL REFERENCES public.siparis(id),
    hakedis_no TEXT NOT NULL,
    yil INTEGER NOT NULL CHECK (yil BETWEEN 2000 AND 2100),
    ay INTEGER NOT NULL CHECK (ay BETWEEN 1 AND 12),
    baslama DATE NOT NULL,
    bitis DATE NOT NULL,
    bedel NUMERIC NOT NULL CHECK (bedel > 0 AND bedel = round(bedel, 2)),
    kdv_orani NUMERIC NOT NULL CHECK (kdv_orani BETWEEN 0 AND 1),
    hizmet_alimi NUMERIC NOT NULL DEFAULT 0 CHECK (hizmet_alimi >= 0 AND hizmet_alimi = round(hizmet_alimi, 2)),
    faaliyet_orani NUMERIC NOT NULL CHECK (faaliyet_orani BETWEEN 0 AND 1),
    kar_orani NUMERIC NOT NULL CHECK (kar_orani BETWEEN 0 AND 1),
    pesin_orani NUMERIC NOT NULL CHECK (pesin_orani BETWEEN 0 AND 1),
    shcek_orani NUMERIC NOT NULL CHECK (shcek_orani BETWEEN 0 AND 1),
    ogrenci_orani NUMERIC NOT NULL CHECK (ogrenci_orani BETWEEN 0 AND 1),
    dv_orani NUMERIC NOT NULL CHECK (dv_orani BETWEEN 0 AND 1),
    asgari_ucret NUMERIC NOT NULL CHECK (asgari_ucret > 0 AND asgari_ucret = round(asgari_ucret, 2)),
    urun_aciklama TEXT NOT NULL CHECK (length(urun_aciklama) BETWEEN 2 AND 500),
    uretilen_miktar NUMERIC NOT NULL CHECK (uretilen_miktar > 0),
    birim TEXT NOT NULL CHECK (length(birim) BETWEEN 1 AND 40),
    aciklama TEXT CHECK (length(aciklama) <= 1000),
    durum TEXT NOT NULL DEFAULT 'Taslak'
        CHECK (durum IN ('Taslak', 'TMY Onayında', 'Müdür Onayında', 'Onaylandı', 'İptal')),
    surum INTEGER NOT NULL DEFAULT 1,
    hesap JSONB,
    yevmiye_id INTEGER,
    olusturan UUID NOT NULL REFERENCES auth.users(id),
    olusturan_rol TEXT NOT NULL,
    olusturma TEXT NOT NULL DEFAULT dose_private.zaman(),
    istek_id UUID NOT NULL,
    CONSTRAINT pb_hakedis_tarih CHECK (baslama <= bitis
        AND extract(year FROM baslama) = yil AND extract(month FROM baslama) = ay
        AND extract(year FROM bitis) = yil AND extract(month FROM bitis) = ay),
    CONSTRAINT pb_hakedis_istek_tek UNIQUE (okul_id, istek_id),
    CONSTRAINT pb_hakedis_no_tek UNIQUE (okul_id, hakedis_no)
);
CREATE INDEX pb_hakedis_siparis ON dose_private.pb_hakedis(okul_id, siparis_id);
CREATE INDEX pb_hakedis_donem ON dose_private.pb_hakedis(okul_id, yil, ay);

CREATE TABLE dose_private.pb_malzeme (
    id SERIAL PRIMARY KEY,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    hakedis_id INTEGER NOT NULL REFERENCES dose_private.pb_hakedis(id) ON DELETE CASCADE,
    sira INTEGER NOT NULL,
    cins TEXT NOT NULL CHECK (length(cins) BETWEEN 1 AND 300),
    miktar NUMERIC NOT NULL CHECK (miktar > 0),
    birim TEXT NOT NULL CHECK (length(birim) BETWEEN 1 AND 40),
    birim_fiyat NUMERIC NOT NULL CHECK (birim_fiyat >= 0),
    kdv_orani NUMERIC NOT NULL CHECK (kdv_orani BETWEEN 0 AND 1)
);
CREATE INDEX pb_malzeme_hakedis ON dose_private.pb_malzeme(hakedis_id);

CREATE TABLE dose_private.pb_kisi (
    id SERIAL PRIMARY KEY,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    hakedis_id INTEGER NOT NULL REFERENCES dose_private.pb_hakedis(id) ON DELETE CASCADE,
    sira INTEGER NOT NULL,
    kisi_turu TEXT NOT NULL CHECK (kisi_turu IN ('Öğretmen', 'Öğrenci')),
    kisi_id INTEGER NOT NULL,
    gorev TEXT CHECK (length(gorev) <= 120),
    gv_orani NUMERIC NOT NULL DEFAULT 0 CHECK (gv_orani BETWEEN 0 AND 1),
    gunler NUMERIC[] NOT NULL,
    UNIQUE (hakedis_id, kisi_turu, kisi_id)
);
CREATE INDEX pb_kisi_kisi ON dose_private.pb_kisi(okul_id, kisi_turu, kisi_id);

CREATE TABLE dose_private.pb_onay (
    id SERIAL PRIMARY KEY,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    hakedis_id INTEGER NOT NULL REFERENCES dose_private.pb_hakedis(id),
    islem TEXT NOT NULL,
    rol TEXT NOT NULL,
    ad_soyad TEXT NOT NULL,
    aciklama TEXT,
    kullanici UUID NOT NULL REFERENCES auth.users(id),
    zaman TEXT NOT NULL DEFAULT dose_private.zaman()
);
CREATE INDEX pb_onay_hakedis ON dose_private.pb_onay(hakedis_id);

ALTER TABLE public.kasa_banka ADD COLUMN pb_hakedis_id INTEGER REFERENCES dose_private.pb_hakedis(id);
CREATE INDEX kasa_pb_indeks ON public.kasa_banka(okul_id, pb_hakedis_id) WHERE pb_hakedis_id IS NOT NULL;

ALTER TABLE dose_private.pb_hakedis ENABLE ROW LEVEL SECURITY;
ALTER TABLE dose_private.pb_malzeme ENABLE ROW LEVEL SECURITY;
ALTER TABLE dose_private.pb_kisi ENABLE ROW LEVEL SECURITY;
ALTER TABLE dose_private.pb_onay ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON dose_private.pb_hakedis, dose_private.pb_malzeme, dose_private.pb_kisi, dose_private.pb_onay
    FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION dose_private.pb_onay_degismez() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Hakediş onay geçmişi değiştirilemez.';
END;
$$;
CREATE TRIGGER dose_pb_onay_degismez BEFORE UPDATE OR DELETE ON dose_private.pb_onay
    FOR EACH ROW EXECUTE FUNCTION dose_private.pb_onay_degismez();

-- Kişiler bir hakedişte kullanıldıysa silinemez.
CREATE OR REPLACE FUNCTION dose_private.pb_kisi_silme_kontrol() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM dose_private.pb_kisi k WHERE k.okul_id = OLD.okul_id AND k.kisi_id = OLD.id
               AND k.kisi_turu = CASE TG_TABLE_NAME WHEN 'personel' THEN 'Öğretmen' ELSE 'Öğrenci' END) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = 'Bu kişi parça başı hakedişinde kullanıldığı için silinemez; pasif yapınız.';
    END IF;
    RETURN OLD;
END;
$$;
CREATE TRIGGER dose_pb_personel_silme BEFORE DELETE ON public.personel
    FOR EACH ROW EXECUTE FUNCTION dose_private.pb_kisi_silme_kontrol();
CREATE TRIGGER dose_pb_ogrenci_silme BEFORE DELETE ON public.ogrenci
    FOR EACH ROW EXECUTE FUNCTION dose_private.pb_kisi_silme_kontrol();

-- ------------------------------------------------------------------ yardımcılar
CREATE OR REPLACE FUNCTION dose_private.pb_sayi(p_deger JSONB, p_etiket TEXT, p_ondalik INTEGER, p_azami NUMERIC)
RETURNS NUMERIC LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
DECLARE v TEXT := p_deger #>> '{}'; n NUMERIC;
BEGIN
    IF jsonb_typeof(p_deger) IS NULL OR jsonb_typeof(p_deger) NOT IN ('string', 'number') OR v IS NULL OR v !~ '^[0-9]{1,15}(\.[0-9]{1,20})?$' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s için geçerli, eksi olmayan bir sayı giriniz.', p_etiket);
    END IF;
    n := v::NUMERIC;
    IF n <> round(n, p_ondalik) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s en fazla %s ondalık basamak içerebilir.', p_etiket, p_ondalik);
    END IF;
    IF n > p_azami THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s en fazla %s olabilir.', p_etiket, p_azami);
    END IF;
    RETURN n;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.pb_metin(p_deger TEXT, p_etiket TEXT, p_en_az INTEGER, p_en_cok INTEGER)
RETURNS TEXT LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
DECLARE v TEXT := nullif(btrim(p_deger), '');
BEGIN
    IF coalesce(length(v), 0) < p_en_az OR length(v) > p_en_cok THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = format('%s %s-%s karakter olmalıdır.', p_etiket, p_en_az, p_en_cok);
    END IF;
    RETURN v;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.pb_siparis_uygun(p_okul INTEGER, p_siparis INTEGER) RETURNS BOOLEAN
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.siparis s
        JOIN public.onay_durum o ON o.okul_id = s.okul_id AND o.belge_turu = 'Sipariş' AND o.belge_id = s.id
        WHERE s.okul_id = p_okul AND s.id = p_siparis AND o.durum = 'Onaylandı'
          AND s.ucret_esasi LIKE 'Parça Başı%')
$$;

CREATE OR REPLACE FUNCTION dose_private.pb_odeme(p_okul INTEGER, p_hakedis INTEGER) RETURNS JSONB
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT jsonb_build_object('id', k.id, 'tarih', k.tarih, 'tutar', k.tutar::TEXT, 'belge_no', k.belge_no)
    FROM public.kasa_banka k
    WHERE k.okul_id = p_okul AND k.pb_hakedis_id = p_hakedis AND k.ters_hareket_id IS NULL
      AND NOT EXISTS (SELECT 1 FROM public.kasa_banka t WHERE t.okul_id = k.okul_id AND t.ters_hareket_id = k.id)
    ORDER BY k.id DESC LIMIT 1
$$;

-- Ek-3 ön maliyet, puantaj dağıtımı ve bordrolar. Tüm tutarlar kuruşa yuvarlanır; havuz toplamları
-- en büyük kalan yöntemiyle kuruşu kuruşuna dağıtılır.
CREATE OR REPLACE FUNCTION dose_private.pb_hesap(p_okul INTEGER, p_hakedis INTEGER) RETURNS JSONB
LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE
    h dose_private.pb_hakedis%ROWTYPE;
    s public.siparis%ROWTYPE;
    v_malzeme NUMERIC; v_malzeme_kdv NUMERIC; v_faaliyet NUMERIC; v_kar NUMERIC; v_pesin NUMERIC; v_shcek NUMERIC;
    v_iscilik NUMERIC; v_ogrenci_havuz NUMERIC; v_ogretmen_havuz NUMERIC;
    v_ogretmen_adet NUMERIC; v_ogrenci_adet NUMERIC; v_mevzuat JSONB; v_deg JSONB;
    v_hatalar TEXT[] := ARRAY[]::TEXT[]; v_uyarilar TEXT[] := ARRAY[]::TEXT[];
    v_kisiler JSONB; v_malzemeler JSONB; v_gun_sayisi INTEGER; v_diger_bedel NUMERIC;
    v_top_brut NUMERIC; v_top_gv NUMERIC; v_top_dv NUMERIC; v_top_net NUMERIC;
    v_satir RECORD;
BEGIN
    SELECT * INTO h FROM dose_private.pb_hakedis WHERE okul_id = p_okul AND id = p_hakedis;
    IF NOT FOUND THEN RETURN NULL; END IF;
    SELECT * INTO s FROM public.siparis WHERE okul_id = p_okul AND id = h.siparis_id;
    v_gun_sayisi := extract(day FROM (make_date(h.yil, h.ay, 1) + INTERVAL '1 month - 1 day'))::INTEGER;

    SELECT coalesce(sum(round(m.miktar * m.birim_fiyat, 2)), 0),
           coalesce(sum(round(round(m.miktar * m.birim_fiyat, 2) * m.kdv_orani, 2)), 0),
           coalesce(jsonb_agg(jsonb_build_object('sira', m.sira, 'cins', m.cins, 'miktar', m.miktar::TEXT,
               'birim', m.birim, 'birim_fiyat', m.birim_fiyat::TEXT, 'kdv_orani', m.kdv_orani::TEXT,
               'tutar', round(m.miktar * m.birim_fiyat, 2)::TEXT,
               'kdv', round(round(m.miktar * m.birim_fiyat, 2) * m.kdv_orani, 2)::TEXT) ORDER BY m.sira), '[]'::JSONB)
      INTO v_malzeme, v_malzeme_kdv, v_malzemeler
    FROM dose_private.pb_malzeme m WHERE m.hakedis_id = h.id;

    v_faaliyet := round(h.bedel * h.faaliyet_orani, 2);
    v_kar := round(h.bedel * h.kar_orani, 2);
    v_pesin := round(h.bedel * h.pesin_orani, 2);
    v_shcek := round(h.bedel * h.shcek_orani, 2);
    v_iscilik := h.bedel - v_malzeme - h.hizmet_alimi - v_faaliyet - v_kar - v_pesin - v_shcek;
    v_ogrenci_havuz := CASE WHEN v_iscilik > 0 THEN round(v_iscilik * h.ogrenci_orani, 2) ELSE 0 END;
    v_ogretmen_havuz := CASE WHEN v_iscilik > 0 THEN v_iscilik - v_ogrenci_havuz ELSE 0 END;

    -- Kural kontrolleri (Yön. md.8 ve Ek-3)
    IF NOT dose_private.pb_siparis_uygun(p_okul, h.siparis_id) THEN
        v_hatalar := array_append(v_hatalar, 'Sipariş onaylı ve parça başı ücret esaslı olmalıdır.'::TEXT);
    END IF;
    BEGIN
        v_mevzuat := dose_private.mevzuat_oku(p_okul, h.bitis);
        v_deg := v_mevzuat->'degerler';
    EXCEPTION WHEN raise_exception THEN
        v_hatalar := v_hatalar || ('Merkez parametreleri: ' || SQLERRM);
    END;
    IF v_deg IS NOT NULL THEN
        IF v_malzeme > round(h.bedel * (v_deg->>'malzeme_azami_orani')::NUMERIC, 2) THEN
            v_hatalar := v_hatalar || format('İlk madde ve malzeme (%s TL) sipariş bedelinin %%%s sınırını aşıyor.',
                v_malzeme, trim_scale((v_deg->>'malzeme_azami_orani')::NUMERIC * 100));
        END IF;
        IF h.faaliyet_orani < (v_deg->>'pb_faaliyet_orani')::NUMERIC THEN
            v_hatalar := v_hatalar || format('Faaliyet gideri oranı en az %%%s olmalıdır.',
                trim_scale((v_deg->>'pb_faaliyet_orani')::NUMERIC * 100));
        END IF;
        IF h.kar_orani < (v_deg->>'pb_kar_orani')::NUMERIC THEN
            v_hatalar := v_hatalar || format('Kâr oranı en az %%%s olmalıdır.',
                trim_scale((v_deg->>'pb_kar_orani')::NUMERIC * 100));
        END IF;
        IF h.ogrenci_orani < (v_deg->>'ogrenci_hakki_orani')::NUMERIC THEN
            v_hatalar := v_hatalar || format('Öğrenci payı işçiliğin en az %%%s olmalıdır.',
                trim_scale((v_deg->>'ogrenci_hakki_orani')::NUMERIC * 100));
        END IF;
    END IF;
    IF v_iscilik <= 0 THEN
        v_hatalar := array_append(v_hatalar, 'Kesintilerden sonra dağıtılacak işçilik kalmıyor.'::TEXT);
    END IF;
    SELECT coalesce(sum(x.bedel), 0) INTO v_diger_bedel FROM dose_private.pb_hakedis x
    WHERE x.okul_id = p_okul AND x.siparis_id = h.siparis_id AND x.id <> h.id AND x.durum <> 'İptal';
    IF s.id IS NOT NULL AND v_diger_bedel + h.bedel > s.sozlesme_bedeli THEN
        v_hatalar := v_hatalar || format('Bu siparişteki hakedişlerin toplamı sözleşme bedelini (%s TL) aşıyor; kalan %s TL.',
            s.sozlesme_bedeli, greatest(s.sozlesme_bedeli - v_diger_bedel, 0));
    END IF;
    IF EXISTS (SELECT 1 FROM public.fazla_calisma f WHERE f.okul_id = p_okul AND f.siparis_id = h.siparis_id
               AND coalesce(f.durum, '') <> 'İptal') THEN
        v_hatalar := array_append(v_hatalar, 'Aynı sipariş için fazla çalışma ücreti ödenemez (md.8/7).'::TEXT);
    END IF;

    -- Puantaj ve kişi bazında dağıtım
    WITH k AS (
        SELECT pk.*, (SELECT coalesce(sum(x), 0) FROM unnest(pk.gunler) x) AS adet
        FROM dose_private.pb_kisi pk WHERE pk.hakedis_id = h.id
    ), t AS (
        SELECT kisi_turu, sum(adet) AS toplam FROM k GROUP BY kisi_turu
    ), b AS (
        SELECT k.*, t.toplam,
               CASE k.kisi_turu WHEN 'Öğretmen' THEN v_ogretmen_havuz ELSE v_ogrenci_havuz END AS havuz
        FROM k JOIN t USING (kisi_turu)
    ), c AS (
        SELECT b.*,
               CASE WHEN toplam > 0 THEN floor(havuz * 100 * adet / toplam) ELSE 0 END AS taban,
               CASE WHEN toplam > 0 THEN havuz * 100 * adet / toplam - floor(havuz * 100 * adet / toplam) ELSE 0 END AS artik
        FROM b
    ), d AS (
        SELECT c.*, row_number() OVER (PARTITION BY kisi_turu ORDER BY artik DESC, sira, id) AS kalan_sira,
               CASE WHEN toplam > 0 THEN round(havuz * 100) - sum(taban) OVER (PARTITION BY kisi_turu) ELSE 0 END AS eksik
        FROM c
    ), e AS (
        SELECT d.*, round((taban + CASE WHEN adet > 0 AND kalan_sira <= eksik THEN 1 ELSE 0 END) / 100, 2) AS brut
        FROM d
    ), f AS (
        SELECT e.*,
               CASE WHEN e.kisi_turu = 'Öğretmen' THEN p.ad_soyad ELSE o.ad_soyad END AS ad_soyad,
               CASE WHEN e.kisi_turu = 'Öğretmen' THEN p.tckn ELSE o.tckn END AS tckn,
               CASE WHEN e.kisi_turu = 'Öğretmen' THEN p.iban ELSE o.iban END AS iban,
               CASE WHEN e.kisi_turu = 'Öğretmen' THEN p.aktif ELSE o.aktif END AS aktif,
               p.hizmet_sinifi, p.kadro_unvani, o.okul_no, o.sinif, o.veli_muvafakat,
               (p.id IS NULL AND o.id IS NULL) AS yok,
               CASE WHEN e.kisi_turu = 'Öğretmen' THEN round(e.brut * e.gv_orani, 2) ELSE 0 END AS gv,
               CASE WHEN e.kisi_turu = 'Öğretmen' THEN round(e.brut * h.dv_orani, 2)
                    ELSE round(greatest(e.brut - h.asgari_ucret, 0) * h.dv_orani, 2) END AS dv
        FROM e
        LEFT JOIN public.personel p ON e.kisi_turu = 'Öğretmen' AND p.okul_id = p_okul AND p.id = e.kisi_id
        LEFT JOIN public.ogrenci o ON e.kisi_turu = 'Öğrenci' AND o.okul_id = p_okul AND o.id = e.kisi_id
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'id', f.id, 'sira', f.sira, 'kisi_turu', f.kisi_turu, 'kisi_id', f.kisi_id, 'ad_soyad', f.ad_soyad,
               'tckn', f.tckn, 'iban', f.iban, 'gorev', f.gorev, 'kadro_unvani', f.kadro_unvani,
               'hizmet_sinifi', f.hizmet_sinifi, 'okul_no', f.okul_no, 'sinif', f.sinif,
               'gunler', (SELECT jsonb_agg(g::TEXT ORDER BY i) FROM unnest(f.gunler) WITH ORDINALITY AS u(g, i)),
               'adet', f.adet::TEXT, 'gv_orani', f.gv_orani::TEXT, 'brut', f.brut::TEXT, 'gelir_vergisi', f.gv::TEXT,
               'damga_vergisi', f.dv::TEXT, 'net', (f.brut - f.gv - f.dv)::TEXT,
               'yok', f.yok, 'aktif', f.aktif, 'veli_muvafakat', f.veli_muvafakat)
               ORDER BY CASE f.kisi_turu WHEN 'Öğretmen' THEN 0 ELSE 1 END, f.sira), '[]'::JSONB),
           coalesce(sum(f.brut), 0), coalesce(sum(f.gv), 0), coalesce(sum(f.dv), 0)
      INTO v_kisiler, v_top_brut, v_top_gv, v_top_dv
    FROM f;
    v_top_net := v_top_brut - v_top_gv - v_top_dv;

    SELECT coalesce(sum(x.adet) FILTER (WHERE x.kisi_turu = 'Öğretmen'), 0),
           coalesce(sum(x.adet) FILTER (WHERE x.kisi_turu = 'Öğrenci'), 0)
      INTO v_ogretmen_adet, v_ogrenci_adet
    FROM (SELECT pk.kisi_turu, (SELECT coalesce(sum(g), 0) FROM unnest(pk.gunler) g) AS adet
          FROM dose_private.pb_kisi pk WHERE pk.hakedis_id = h.id) x;

    IF v_ogretmen_havuz > 0 AND v_ogretmen_adet = 0 THEN
        v_hatalar := array_append(v_hatalar, 'Öğretmen payı var ancak öğretmen puantajı boş.'::TEXT);
    END IF;
    IF v_ogrenci_havuz > 0 AND v_ogrenci_adet = 0 THEN
        v_hatalar := array_append(v_hatalar, 'Öğrenci payı var ancak öğrenci puantajı boş.'::TEXT);
    END IF;
    IF v_iscilik > 0 AND v_top_brut <> v_iscilik THEN
        v_hatalar := v_hatalar || format('Dağıtım kontrolü tutmuyor: dağıtılan %s TL, işçilik %s TL.', v_top_brut, v_iscilik);
    END IF;
    FOR v_satir IN SELECT value AS k FROM jsonb_array_elements(v_kisiler) LOOP
        IF (v_satir.k->>'yok')::BOOLEAN THEN
            v_hatalar := v_hatalar || format('%s. satırdaki kişi kaydı bulunamadı.', v_satir.k->>'sira');
            CONTINUE;
        END IF;
        IF (v_satir.k->>'adet')::NUMERIC = 0 THEN
            v_uyarilar := v_uyarilar || format('%s için puantajda üretim yok; ödeme yapılmaz.', v_satir.k->>'ad_soyad');
            CONTINUE;
        END IF;
        IF (v_satir.k->>'aktif')::INTEGER IS DISTINCT FROM 1 THEN
            v_hatalar := v_hatalar || format('%s kaydı pasif.', v_satir.k->>'ad_soyad');
        END IF;
        IF v_satir.k->>'iban' IS NULL THEN
            v_hatalar := v_hatalar || format('%s için IBAN kayıtlı değil; banka ödemesi yapılamaz (md.7).', v_satir.k->>'ad_soyad');
        END IF;
        IF v_satir.k->>'kisi_turu' = 'Öğrenci' THEN
            IF (v_satir.k->>'veli_muvafakat')::INTEGER IS DISTINCT FROM 1 THEN
                v_hatalar := v_hatalar || format('%s için veli yazılı muvafakati yok.', v_satir.k->>'ad_soyad');
            END IF;
            IF coalesce(v_satir.k->>'sinif', '') ~ '^\s*9(\D|$)' THEN
                v_hatalar := v_hatalar || format('%s 9. sınıf öğrencisi; parça başı ödemesi yapılamaz.', v_satir.k->>'ad_soyad');
            END IF;
        END IF;
    END LOOP;
    -- Puantaj günleri iş başlama/bitiş tarihleri içinde olmalıdır.
    IF EXISTS (SELECT 1 FROM dose_private.pb_kisi pk, unnest(pk.gunler) WITH ORDINALITY AS u(g, i)
               WHERE pk.hakedis_id = h.id AND g > 0
                 AND (i < extract(day FROM h.baslama) OR i > extract(day FROM h.bitis))) THEN
        v_hatalar := array_append(v_hatalar, 'Puantajda iş başlama-bitiş tarihleri dışındaki günlere üretim yazılmış.'::TEXT);
    END IF;
    -- Aylık tavan uyarısı: aynı ay içindeki diğer hakedişler dahil (öğretmen 2x, teknik 1,5x, diğer 1x, öğrenci 1x asgari ücret).
    FOR v_satir IN
        SELECT (k->>'kisi_turu') AS tur, (k->>'kisi_id')::INTEGER AS kid, k->>'ad_soyad' AS ad,
               (k->>'brut')::NUMERIC AS brut, k->>'hizmet_sinifi' AS hs
        FROM jsonb_array_elements(v_kisiler) k WHERE NOT (k->>'yok')::BOOLEAN
    LOOP
        DECLARE v_diger NUMERIC; v_tavan NUMERIC;
        BEGIN
            SELECT coalesce(sum((x->>'brut')::NUMERIC), 0) INTO v_diger
            FROM dose_private.pb_hakedis o2, jsonb_array_elements(coalesce(o2.hesap->'kisiler', '[]'::JSONB)) x
            WHERE o2.okul_id = p_okul AND o2.yil = h.yil AND o2.ay = h.ay AND o2.id <> h.id AND o2.durum = 'Onaylandı'
              AND x->>'kisi_turu' = v_satir.tur AND (x->>'kisi_id')::INTEGER = v_satir.kid;
            v_tavan := round(h.asgari_ucret * CASE
                WHEN v_satir.tur = 'Öğrenci' THEN 1
                WHEN coalesce(v_satir.hs, '') LIKE 'Eğitim%' THEN 2
                WHEN coalesce(v_satir.hs, '') LIKE 'Teknik%' THEN 1.5 ELSE 1 END, 2);
            IF v_diger + v_satir.brut > v_tavan THEN
                v_uyarilar := v_uyarilar || format('%s için bu ayki parça başı toplamı (%s TL) aylık tavanı (%s TL) aşıyor.',
                    v_satir.ad, v_diger + v_satir.brut, v_tavan);
            END IF;
        END;
    END LOOP;

    RETURN jsonb_build_object(
        'gun_sayisi', v_gun_sayisi,
        'bedel', h.bedel::TEXT, 'kdv_orani', h.kdv_orani::TEXT,
        'kdv', round(h.bedel * h.kdv_orani, 2)::TEXT,
        'fatura_tutari', (h.bedel + round(h.bedel * h.kdv_orani, 2))::TEXT,
        'malzeme', v_malzeme::TEXT, 'malzeme_kdv', v_malzeme_kdv::TEXT,
        'malzeme_kdv_dahil', (v_malzeme + v_malzeme_kdv)::TEXT, 'malzemeler', v_malzemeler,
        'malzeme_orani', CASE WHEN h.bedel > 0 THEN round(v_malzeme / h.bedel, 6)::TEXT END,
        'hizmet_alimi', h.hizmet_alimi::TEXT, 'faaliyet', v_faaliyet::TEXT, 'kar', v_kar::TEXT,
        'pesin_gelir_vergisi', v_pesin::TEXT, 'shcek', v_shcek::TEXT, 'iscilik', v_iscilik::TEXT,
        'ogrenci_havuz', v_ogrenci_havuz::TEXT, 'ogretmen_havuz', v_ogretmen_havuz::TEXT,
        'ogretmen_adet', v_ogretmen_adet::TEXT, 'ogrenci_adet', v_ogrenci_adet::TEXT,
        'ogretmen_parca_payi', CASE WHEN v_ogretmen_adet > 0 THEN round(v_ogretmen_havuz / v_ogretmen_adet, 6)::TEXT END,
        'ogrenci_parca_payi', CASE WHEN v_ogrenci_adet > 0 THEN round(v_ogrenci_havuz / v_ogrenci_adet, 6)::TEXT END,
        'kisiler', v_kisiler,
        'toplam', jsonb_build_object('brut', v_top_brut::TEXT, 'gelir_vergisi', v_top_gv::TEXT,
                                     'damga_vergisi', v_top_dv::TEXT, 'net', v_top_net::TEXT),
        'mevzuat_yayin_id', v_mevzuat->'yayin_id',
        'siparis_kalan', CASE WHEN s.id IS NULL THEN NULL ELSE (s.sozlesme_bedeli - v_diger_bedel - h.bedel)::TEXT END,
        'hatalar', to_jsonb(v_hatalar), 'uyarilar', to_jsonb(v_uyarilar));
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.pb_onay_ekle(p_okul INTEGER, p_hakedis INTEGER, p_islem TEXT, p_aciklama TEXT)
RETURNS VOID LANGUAGE sql VOLATILE SET search_path = '' AS $$
    INSERT INTO dose_private.pb_onay (okul_id, hakedis_id, islem, rol, ad_soyad, aciklama, kullanici)
    SELECT p_okul, p_hakedis, p_islem, u.rol, u.ad_soyad, p_aciklama, auth.uid()
    FROM dose_private.uyelik u WHERE u.auth_user_id = auth.uid()
$$;

CREATE OR REPLACE FUNCTION dose_private.pb_hazirlayabilir(p_okul INTEGER, p_siparis INTEGER) RETURNS BOOLEAN
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT auth.uid() IS NOT NULL AND public.dose_yetki('parca_basi') = 'y'
       AND public.dose_rol() IN ('Alan Şefi', 'Teknik Müdür Yardımcısı')
       AND (public.dose_rol() <> 'Alan Şefi' OR EXISTS (
            SELECT 1 FROM public.siparis s WHERE s.okul_id = p_okul AND s.id = p_siparis
              AND s.bolum_id = public.dose_bolum()))
$$;

-- ------------------------------------------------------------------ okuma
CREATE OR REPLACE FUNCTION public.dose_pb_veri() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_kisitli BOOLEAN := public.dose_bolum_kisitli();
    v_bolum INTEGER := public.dose_bolum();
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('parca_basi') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Parça başı hakediş ekranına erişim yetkiniz yok.';
    END IF;
    RETURN jsonb_build_object(
        'okul', (SELECT jsonb_build_object('ad', o.ad, 'kurum_kodu', o.kurum_kodu) FROM dose_private.okul o WHERE o.id = v_okul),
        'siparisler', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', s.id, 'siparis_no', s.siparis_no, 'konu', s.konu, 'tarih', s.tarih, 'bolum_id', s.bolum_id,
            'bolum', b.ad, 'cari', c.unvan, 'sozlesme_bedeli', s.sozlesme_bedeli::TEXT, 'kdv_orani', s.kdv_orani::TEXT,
            'kullanilan', (SELECT coalesce(sum(x.bedel), 0) FROM dose_private.pb_hakedis x
                           WHERE x.okul_id = v_okul AND x.siparis_id = s.id AND x.durum <> 'İptal')::TEXT)
            ORDER BY s.id DESC)
            FROM public.siparis s
            LEFT JOIN public.bolum b ON b.okul_id = s.okul_id AND b.id = s.bolum_id
            LEFT JOIN public.cari c ON c.okul_id = s.okul_id AND c.id = s.cari_id
            WHERE s.okul_id = v_okul AND dose_private.pb_siparis_uygun(v_okul, s.id)
              AND (NOT v_kisitli OR s.bolum_id = v_bolum)), '[]'::JSONB),
        'personel', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', p.id, 'ad_soyad', p.ad_soyad, 'bolum_id', p.bolum_id, 'kadro_unvani', p.kadro_unvani,
            'hizmet_sinifi', p.hizmet_sinifi, 'iban_var', p.iban IS NOT NULL) ORDER BY p.ad_soyad, p.id)
            FROM public.personel p WHERE p.okul_id = v_okul AND p.aktif = 1
              AND (NOT v_kisitli OR p.bolum_id = v_bolum)), '[]'::JSONB),
        'ogrenciler', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', o.id, 'ad_soyad', o.ad_soyad, 'okul_no', o.okul_no, 'sinif', o.sinif, 'bolum_id', o.bolum_id,
            'veli_muvafakat', o.veli_muvafakat = 1, 'iban_var', o.iban IS NOT NULL) ORDER BY o.sinif, o.okul_no, o.id)
            FROM public.ogrenci o WHERE o.okul_id = v_okul AND o.aktif = 1
              AND (NOT v_kisitli OR o.bolum_id = v_bolum)), '[]'::JSONB),
        'hakedisler', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', h.id, 'hakedis_no', h.hakedis_no, 'siparis_id', h.siparis_id, 'siparis_no', s.siparis_no,
            'siparis_konu', s.konu, 'cari', c.unvan, 'bolum', b.ad, 'yil', h.yil, 'ay', h.ay,
            'baslama', h.baslama, 'bitis', h.bitis, 'bedel', h.bedel::TEXT, 'kdv_orani', h.kdv_orani::TEXT,
            'hizmet_alimi', h.hizmet_alimi::TEXT, 'faaliyet_orani', h.faaliyet_orani::TEXT,
            'kar_orani', h.kar_orani::TEXT, 'pesin_orani', h.pesin_orani::TEXT, 'shcek_orani', h.shcek_orani::TEXT,
            'ogrenci_orani', h.ogrenci_orani::TEXT, 'dv_orani', h.dv_orani::TEXT, 'asgari_ucret', h.asgari_ucret::TEXT,
            'urun_aciklama', h.urun_aciklama, 'uretilen_miktar', h.uretilen_miktar::TEXT, 'birim', h.birim,
            'aciklama', h.aciklama, 'durum', h.durum, 'surum', h.surum, 'olusturan_rol', h.olusturan_rol,
            'olusturma', h.olusturma, 'yevmiye_id', h.yevmiye_id,
            'malzemeler', coalesce((SELECT jsonb_agg(jsonb_build_object('cins', m.cins, 'miktar', m.miktar::TEXT,
                'birim', m.birim, 'birim_fiyat', m.birim_fiyat::TEXT, 'kdv_orani', m.kdv_orani::TEXT) ORDER BY m.sira)
                FROM dose_private.pb_malzeme m WHERE m.hakedis_id = h.id), '[]'::JSONB),
            'kisiler', coalesce((SELECT jsonb_agg(jsonb_build_object('kisi_turu', k.kisi_turu, 'kisi_id', k.kisi_id,
                'gorev', k.gorev, 'gv_orani', k.gv_orani::TEXT,
                'gunler', (SELECT jsonb_agg(g::TEXT ORDER BY i) FROM unnest(k.gunler) WITH ORDINALITY AS u(g, i)))
                ORDER BY k.sira) FROM dose_private.pb_kisi k WHERE k.hakedis_id = h.id), '[]'::JSONB),
            'hesap', CASE WHEN h.durum IN ('Onaylandı', 'İptal') AND h.hesap IS NOT NULL THEN h.hesap
                          ELSE dose_private.pb_hesap(v_okul, h.id) END,
            'onaylar', coalesce((SELECT jsonb_agg(jsonb_build_object('islem', a.islem, 'rol', a.rol,
                'ad_soyad', a.ad_soyad, 'aciklama', a.aciklama, 'zaman', a.zaman) ORDER BY a.id)
                FROM dose_private.pb_onay a WHERE a.hakedis_id = h.id), '[]'::JSONB),
            'odeme', dose_private.pb_odeme(v_okul, h.id))
            ORDER BY h.yil DESC, h.ay DESC, h.id DESC)
            FROM dose_private.pb_hakedis h
            JOIN public.siparis s ON s.okul_id = h.okul_id AND s.id = h.siparis_id
            LEFT JOIN public.cari c ON c.okul_id = s.okul_id AND c.id = s.cari_id
            LEFT JOIN public.bolum b ON b.okul_id = s.okul_id AND b.id = s.bolum_id
            WHERE h.okul_id = v_okul AND (NOT v_kisitli OR s.bolum_id = v_bolum)), '[]'::JSONB),
        'banka_bakiye', CASE WHEN public.dose_rol() = 'Sayman'
                             THEN dose_private.kasa_bakiye(v_okul, 'Banka (102)')::TEXT END);
END;
$$;

-- ------------------------------------------------------------------ taslak kaydı
CREATE OR REPLACE FUNCTION public.dose_pb_kaydet(
    p_id INTEGER, p_surum INTEGER, p_veri JSONB, p_malzemeler JSONB, p_kisiler JSONB, p_istek UUID
) RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_eski dose_private.pb_hakedis%ROWTYPE;
    v_siparis public.siparis%ROWTYPE;
    v_id INTEGER; v_surum INTEGER; v_kisit TEXT;
    v_yil INTEGER; v_ay INTEGER; v_baslama DATE; v_bitis DATE; v_gun_sayisi INTEGER;
    v_bedel NUMERIC; v_hizmet NUMERIC; v_faaliyet NUMERIC; v_kar NUMERIC; v_pesin NUMERIC; v_shcek NUMERIC;
    v_ogrenci NUMERIC; v_dv NUMERIC; v_asgari NUMERIC; v_miktar NUMERIC;
    v_urun TEXT; v_birim TEXT; v_aciklama TEXT;
    v_m JSONB; v_k JSONB; v_sira INTEGER := 0; v_gunler NUMERIC[]; v_g JSONB; v_tur TEXT; v_kisi INTEGER;
BEGIN
    IF v_okul IS NULL OR auth.uid() IS NULL OR public.dose_yetki('parca_basi') <> 'y'
       OR public.dose_rol() NOT IN ('Alan Şefi', 'Teknik Müdür Yardımcısı') THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'Parça başı hakedişini yalnız yetkili Alan Şefi veya Teknik Müdür Yardımcısı hazırlayabilir.';
    END IF;
    IF jsonb_typeof(p_veri) IS DISTINCT FROM 'object' OR jsonb_typeof(p_malzemeler) IS DISTINCT FROM 'array'
       OR jsonb_typeof(p_kisiler) IS DISTINCT FROM 'array' OR p_istek IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Hakediş bilgileri, malzeme ve puantaj listeleri gereklidir.';
    END IF;
    IF p_id IS NOT NULL THEN
        SELECT * INTO v_eski FROM dose_private.pb_hakedis WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Hakediş bulunamadı.';
        END IF;
        IF v_eski.durum <> 'Taslak' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yalnız taslak durumundaki hakediş değiştirilebilir.';
        END IF;
        IF p_surum IS DISTINCT FROM v_eski.surum THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Hakediş başka biri tarafından değiştirildi; güncelini yükleyin.',
                HINT = 'surum_cakismasi';
        END IF;
        IF NOT dose_private.pb_hazirlayabilir(v_okul, v_eski.siparis_id) THEN
            RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Bu hakedişi değiştirme yetkiniz yok.';
        END IF;
    ELSIF EXISTS (SELECT 1 FROM dose_private.pb_hakedis WHERE okul_id = v_okul AND istek_id = p_istek) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu hakediş daha önce kaydedildi; listeyi yenileyin.';
    END IF;

    IF jsonb_typeof(p_veri->'siparis_id') IS DISTINCT FROM 'number' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Onaylı parça başı siparişi seçiniz.';
    END IF;
    SELECT * INTO v_siparis FROM public.siparis WHERE okul_id = v_okul AND id = (p_veri->>'siparis_id')::INTEGER FOR SHARE;
    IF NOT FOUND OR NOT dose_private.pb_siparis_uygun(v_okul, v_siparis.id) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Onaylı parça başı siparişi seçiniz.';
    END IF;
    IF p_id IS NOT NULL AND v_siparis.id <> v_eski.siparis_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Kaydedilmiş hakedişin siparişi değiştirilemez.';
    END IF;
    IF NOT dose_private.pb_hazirlayabilir(v_okul, v_siparis.id) THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Yalnız kendi bölümünüzün siparişi için hakediş hazırlayabilirsiniz.';
    END IF;

    BEGIN
        v_baslama := (p_veri->>'baslama')::DATE;
        v_bitis := (p_veri->>'bitis')::DATE;
    EXCEPTION WHEN OTHERS THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İş başlama ve bitiş tarihlerini geçerli giriniz.';
    END;
    IF v_baslama IS NULL OR v_bitis IS NULL OR v_baslama > v_bitis
       OR date_trunc('month', v_baslama) <> date_trunc('month', v_bitis)
       OR v_baslama < DATE '2000-01-01' OR v_bitis > DATE '2100-12-31' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = 'İş başlama ve bitiş tarihleri aynı ay içinde olmalı; bitiş başlamadan önce olamaz.';
    END IF;
    IF v_baslama < v_siparis.tarih::DATE THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Puantaj dönemi sipariş tarihinden önce başlayamaz.';
    END IF;
    v_yil := extract(year FROM v_baslama); v_ay := extract(month FROM v_baslama);
    v_gun_sayisi := extract(day FROM (date_trunc('month', v_baslama) + INTERVAL '1 month - 1 day'))::INTEGER;

    v_bedel := dose_private.pb_sayi(p_veri->'bedel', 'Hakediş bedeli (KDV hariç)', 2, 999999999999);
    IF v_bedel <= 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Hakediş bedeli sıfırdan büyük olmalıdır.';
    END IF;
    v_hizmet := dose_private.pb_sayi(coalesce(p_veri->'hizmet_alimi', '"0"'), 'Hizmet alımı', 2, 999999999999);
    v_faaliyet := dose_private.pb_sayi(p_veri->'faaliyet_orani', 'Faaliyet gideri oranı', 10, 1);
    v_kar := dose_private.pb_sayi(p_veri->'kar_orani', 'Kâr oranı', 10, 1);
    v_pesin := dose_private.pb_sayi(p_veri->'pesin_orani', 'Peşin gelir vergisi oranı', 10, 1);
    v_shcek := dose_private.pb_sayi(p_veri->'shcek_orani', 'SHÇEK payı oranı', 10, 1);
    v_ogrenci := dose_private.pb_sayi(p_veri->'ogrenci_orani', 'Öğrenci payı oranı', 10, 1);
    v_dv := dose_private.pb_sayi(p_veri->'dv_orani', 'Damga vergisi oranı', 10, 1);
    v_asgari := dose_private.pb_sayi(p_veri->'asgari_ucret', 'Aylık brüt asgari ücret', 2, 999999999);
    v_miktar := dose_private.pb_sayi(p_veri->'uretilen_miktar', 'Üretilen miktar', 3, 999999999999);
    IF v_asgari <= 0 OR v_miktar <= 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Asgari ücret ve üretilen miktar sıfırdan büyük olmalıdır.';
    END IF;
    v_urun := dose_private.pb_metin(p_veri->>'urun_aciklama', 'Üretilen ürün/hizmet', 2, 500);
    v_birim := dose_private.pb_metin(p_veri->>'birim', 'Birim', 1, 40);
    v_aciklama := nullif(btrim(p_veri->>'aciklama'), '');
    IF length(v_aciklama) > 1000 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Açıklama en fazla 1000 karakter olabilir.';
    END IF;
    IF jsonb_array_length(p_malzemeler) > 200 OR jsonb_array_length(p_kisiler) > 500 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Malzeme veya puantaj satırı sayısı çok fazla.';
    END IF;
    IF jsonb_array_length(p_kisiler) = 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Puantaja en az bir kişi ekleyiniz.';
    END IF;

    IF p_id IS NULL THEN
        BEGIN
            INSERT INTO dose_private.pb_hakedis (okul_id, siparis_id, hakedis_no, yil, ay, baslama, bitis, bedel,
                kdv_orani, hizmet_alimi, faaliyet_orani, kar_orani, pesin_orani, shcek_orani, ogrenci_orani, dv_orani,
                asgari_ucret, urun_aciklama, uretilen_miktar, birim, aciklama, olusturan, olusturan_rol, istek_id)
            VALUES (v_okul, v_siparis.id,
                format('PB-%s-%s', v_yil, lpad(dose_private.sira_no(v_okul, 'parca_basi', v_yil)::TEXT, 4, '0')),
                v_yil, v_ay, v_baslama, v_bitis, v_bedel, v_siparis.kdv_orani, v_hizmet, v_faaliyet, v_kar, v_pesin,
                v_shcek, v_ogrenci, v_dv, v_asgari, v_urun, v_miktar, v_birim, v_aciklama, auth.uid(),
                public.dose_rol(), p_istek)
            RETURNING id, surum INTO v_id, v_surum;
        EXCEPTION WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS v_kisit = CONSTRAINT_NAME;
            IF v_kisit = 'pb_hakedis_istek_tek' THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu hakediş daha önce kaydedildi; listeyi yenileyin.';
            END IF;
            RAISE;
        END;
        PERFORM dose_private.pb_onay_ekle(v_okul, v_id, 'Hazırlandı', NULL);
    ELSE
        UPDATE dose_private.pb_hakedis SET yil = v_yil, ay = v_ay, baslama = v_baslama, bitis = v_bitis,
            bedel = v_bedel, kdv_orani = v_siparis.kdv_orani, hizmet_alimi = v_hizmet, faaliyet_orani = v_faaliyet,
            kar_orani = v_kar, pesin_orani = v_pesin, shcek_orani = v_shcek, ogrenci_orani = v_ogrenci,
            dv_orani = v_dv, asgari_ucret = v_asgari, urun_aciklama = v_urun, uretilen_miktar = v_miktar,
            birim = v_birim, aciklama = v_aciklama, surum = surum + 1
        WHERE id = p_id RETURNING id, surum INTO v_id, v_surum;
        DELETE FROM dose_private.pb_malzeme WHERE hakedis_id = v_id;
        DELETE FROM dose_private.pb_kisi WHERE hakedis_id = v_id;
    END IF;

    FOR v_m IN SELECT value FROM jsonb_array_elements(p_malzemeler) LOOP
        v_sira := v_sira + 1;
        IF jsonb_typeof(v_m) IS DISTINCT FROM 'object' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. malzeme satırı geçersiz.', v_sira);
        END IF;
        v_miktar := dose_private.pb_sayi(v_m->'miktar', format('%s. malzemenin miktarı', v_sira), 3, 999999999999);
        IF v_miktar <= 0 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. malzemenin miktarı sıfırdan büyük olmalıdır.', v_sira);
        END IF;
        INSERT INTO dose_private.pb_malzeme (okul_id, hakedis_id, sira, cins, miktar, birim, birim_fiyat, kdv_orani)
        VALUES (v_okul, v_id, v_sira,
            dose_private.pb_metin(v_m->>'cins', format('%s. malzemenin cinsi', v_sira), 1, 300),
            v_miktar,
            dose_private.pb_metin(v_m->>'birim', format('%s. malzemenin birimi', v_sira), 1, 40),
            dose_private.pb_sayi(v_m->'birim_fiyat', format('%s. malzemenin birim fiyatı', v_sira), 4, 999999999999),
            dose_private.pb_sayi(v_m->'kdv_orani', format('%s. malzemenin KDV oranı', v_sira), 4, 1));
    END LOOP;

    v_sira := 0;
    FOR v_k IN SELECT value FROM jsonb_array_elements(p_kisiler) LOOP
        v_sira := v_sira + 1;
        v_tur := v_k->>'kisi_turu';
        IF jsonb_typeof(v_k) IS DISTINCT FROM 'object' OR v_tur IS NULL OR v_tur NOT IN ('Öğretmen', 'Öğrenci')
           OR jsonb_typeof(v_k->'kisi_id') IS DISTINCT FROM 'number'
           OR jsonb_typeof(v_k->'gunler') IS DISTINCT FROM 'array' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. puantaj satırı geçersiz.', v_sira);
        END IF;
        v_kisi := (v_k->>'kisi_id')::INTEGER;
        IF v_tur = 'Öğretmen' AND NOT EXISTS (SELECT 1 FROM public.personel WHERE okul_id = v_okul AND id = v_kisi AND aktif = 1)
           OR v_tur = 'Öğrenci' AND NOT EXISTS (SELECT 1 FROM public.ogrenci WHERE okul_id = v_okul AND id = v_kisi AND aktif = 1) THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. puantaj satırındaki kişi aktif değil veya bulunamadı.', v_sira);
        END IF;
        IF jsonb_array_length(v_k->'gunler') <> v_gun_sayisi THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001',
                MESSAGE = format('%s. puantaj satırında ayın %s günü için değer olmalıdır.', v_sira, v_gun_sayisi);
        END IF;
        v_gunler := ARRAY[]::NUMERIC[];
        FOR v_g IN SELECT value FROM jsonb_array_elements(v_k->'gunler') LOOP
            v_gunler := v_gunler || dose_private.pb_sayi(CASE WHEN v_g = '""'::JSONB OR v_g = 'null'::JSONB THEN '"0"'::JSONB ELSE v_g END,
                format('%s. puantaj satırındaki üretim miktarı', v_sira), 3, 999999999);
        END LOOP;
        BEGIN
            INSERT INTO dose_private.pb_kisi (okul_id, hakedis_id, sira, kisi_turu, kisi_id, gorev, gv_orani, gunler)
            VALUES (v_okul, v_id, v_sira, v_tur, v_kisi, nullif(btrim(v_k->>'gorev'), ''),
                CASE WHEN v_tur = 'Öğretmen'
                     THEN dose_private.pb_sayi(coalesce(v_k->'gv_orani', 'null'::JSONB), format('%s. satırdaki gelir vergisi oranı', v_sira), 4, 1)
                     ELSE 0 END,
                v_gunler);
        EXCEPTION WHEN unique_violation THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. puantaj satırındaki kişi listede birden fazla kez var.', v_sira);
        WHEN check_violation THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. puantaj satırındaki görev en fazla 120 karakter olabilir.', v_sira);
        END;
    END LOOP;

    PERFORM dose_private.log(v_okul, CASE WHEN p_id IS NULL THEN 'Parça başı hakediş hazırlandı' ELSE 'Parça başı hakediş güncellendi' END,
        'pb_hakedis', v_id, v_urun, to_jsonb(v_eski), NULL);
    RETURN jsonb_build_object('id', v_id, 'surum', v_surum, 'hesap', dose_private.pb_hesap(v_okul, v_id));
END;
$$;

-- ------------------------------------------------------------------ onay zinciri
CREATE OR REPLACE FUNCTION public.dose_pb_gonder(p_id INTEGER, p_surum INTEGER) RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); h dose_private.pb_hakedis%ROWTYPE; v_hesap JSONB; v_durum TEXT;
BEGIN
    SELECT * INTO h FROM dose_private.pb_hakedis WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
    IF NOT FOUND OR NOT dose_private.pb_hazirlayabilir(v_okul, h.siparis_id) THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Bu hakedişi onaya gönderme yetkiniz yok.';
    END IF;
    IF h.durum <> 'Taslak' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yalnız taslak hakediş onaya gönderilebilir.';
    END IF;
    IF p_surum IS DISTINCT FROM h.surum THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Hakediş değiştirildi; güncelini yükleyin.', HINT = 'surum_cakismasi';
    END IF;
    IF h.bitis > (now() AT TIME ZONE 'Europe/Istanbul')::DATE THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İş bitiş tarihi gelmeden hakediş onaya gönderilemez.';
    END IF;
    PERFORM 1 FROM public.siparis WHERE okul_id = v_okul AND id = h.siparis_id FOR UPDATE;
    v_hesap := dose_private.pb_hesap(v_okul, h.id);
    IF jsonb_array_length(v_hesap->'hatalar') > 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Hakediş kontrolleri tamamlanmadı: ' || (v_hesap->'hatalar'->>0);
    END IF;
    v_durum := CASE WHEN public.dose_rol() = 'Teknik Müdür Yardımcısı' THEN 'Müdür Onayında' ELSE 'TMY Onayında' END;
    UPDATE dose_private.pb_hakedis SET durum = v_durum, surum = surum + 1 WHERE id = h.id;
    PERFORM dose_private.pb_onay_ekle(v_okul, h.id, 'Onaya gönderildi', NULL);
    IF v_durum = 'Müdür Onayında' THEN
        PERFORM dose_private.pb_onay_ekle(v_okul, h.id, 'Uygundur', 'Hazırlayan Teknik Müdür Yardımcısı');
    END IF;
    PERFORM dose_private.log(v_okul, 'Parça başı hakediş onaya gönderildi', 'pb_hakedis', h.id, h.hakedis_no);
    RETURN jsonb_build_object('id', h.id, 'durum', v_durum, 'surum', h.surum + 1);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_pb_karar(p_id INTEGER, p_surum INTEGER, p_onay BOOLEAN, p_aciklama TEXT)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); h dose_private.pb_hakedis%ROWTYPE; v_hesap JSONB;
    v_rol TEXT := public.dose_rol(); v_aciklama TEXT := nullif(btrim(p_aciklama), ''); v_durum TEXT;
    v_fis INTEGER; v_satirlar JSONB; v_vergi NUMERIC; v_tarih DATE := (now() AT TIME ZONE 'Europe/Istanbul')::DATE;
BEGIN
    SELECT * INTO h FROM dose_private.pb_hakedis WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
    IF NOT FOUND OR auth.uid() IS NULL OR public.dose_yetki('parca_basi') <> 'y'
       OR NOT (h.durum = 'TMY Onayında' AND v_rol = 'Teknik Müdür Yardımcısı'
               OR h.durum = 'Müdür Onayında' AND v_rol = 'Okul Müdürü') THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'Bu aşamadaki hakediş kararını yalnız sıradaki yetkili verebilir (TMY: uygundur, Müdür: olur).';
    END IF;
    IF p_surum IS DISTINCT FROM h.surum THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Hakediş değiştirildi; güncelini yükleyin.', HINT = 'surum_cakismasi';
    END IF;
    IF p_onay IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Karar seçiniz.';
    END IF;
    IF length(v_aciklama) > 500 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Açıklama en fazla 500 karakter olabilir.';
    END IF;
    IF NOT p_onay THEN
        IF v_aciklama IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İade gerekçesini yazınız.';
        END IF;
        UPDATE dose_private.pb_hakedis SET durum = 'Taslak', surum = surum + 1 WHERE id = h.id;
        PERFORM dose_private.pb_onay_ekle(v_okul, h.id, 'İade edildi', v_aciklama);
        PERFORM dose_private.log(v_okul, 'Parça başı hakediş iade edildi', 'pb_hakedis', h.id, v_aciklama);
        RETURN jsonb_build_object('id', h.id, 'durum', 'Taslak', 'surum', h.surum + 1);
    END IF;
    IF v_rol = 'Teknik Müdür Yardımcısı' THEN
        UPDATE dose_private.pb_hakedis SET durum = 'Müdür Onayında', surum = surum + 1 WHERE id = h.id;
        PERFORM dose_private.pb_onay_ekle(v_okul, h.id, 'Uygundur', v_aciklama);
        PERFORM dose_private.log(v_okul, 'Parça başı hakediş uygun görüldü', 'pb_hakedis', h.id, h.hakedis_no);
        RETURN jsonb_build_object('id', h.id, 'durum', 'Müdür Onayında', 'surum', h.surum + 1);
    END IF;

    PERFORM 1 FROM public.siparis WHERE okul_id = v_okul AND id = h.siparis_id FOR UPDATE;
    v_hesap := dose_private.pb_hesap(v_okul, h.id);
    IF jsonb_array_length(v_hesap->'hatalar') > 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Hakediş kontrolleri geçmiyor: ' || (v_hesap->'hatalar'->>0);
    END IF;
    v_vergi := (v_hesap->'toplam'->>'gelir_vergisi')::NUMERIC + (v_hesap->'toplam'->>'damga_vergisi')::NUMERIC;
    v_satirlar := jsonb_build_array(
        jsonb_build_object('hesap', '720', 'borc', (v_hesap->'toplam'->>'brut')::NUMERIC, 'alacak', 0),
        jsonb_build_object('hesap', '335', 'borc', 0, 'alacak', (v_hesap->'toplam'->>'net')::NUMERIC));
    IF v_vergi > 0 THEN
        v_satirlar := v_satirlar || jsonb_build_array(jsonb_build_object('hesap', '360', 'borc', 0, 'alacak', v_vergi));
    END IF;
    v_fis := dose_private.yevmiye_olustur(v_okul, v_tarih, format('%s parça başı hakediş tahakkuku', h.hakedis_no),
        'ParcaBasi', h.id, v_satirlar);
    UPDATE dose_private.pb_hakedis SET durum = 'Onaylandı', surum = surum + 1, hesap = v_hesap, yevmiye_id = v_fis
    WHERE id = h.id;
    PERFORM dose_private.pb_onay_ekle(v_okul, h.id, 'Olur', v_aciklama);
    PERFORM dose_private.log(v_okul, 'Parça başı hakediş onaylandı', 'pb_hakedis', h.id, h.hakedis_no, NULL,
        jsonb_build_object('yevmiye_id', v_fis, 'brut', v_hesap->'toplam'->>'brut', 'net', v_hesap->'toplam'->>'net'));
    RETURN jsonb_build_object('id', h.id, 'durum', 'Onaylandı', 'surum', h.surum + 1, 'yevmiye_id', v_fis);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_pb_iptal(p_id INTEGER, p_surum INTEGER, p_gerekce TEXT) RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); h dose_private.pb_hakedis%ROWTYPE; v_rol TEXT := public.dose_rol();
    v_gerekce TEXT := nullif(btrim(p_gerekce), ''); v_satirlar JSONB; v_fis INTEGER;
BEGIN
    SELECT * INTO h FROM dose_private.pb_hakedis WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
    IF NOT FOUND OR public.dose_yetki('parca_basi') <> 'y'
       OR NOT (h.durum = 'Taslak' AND dose_private.pb_hazirlayabilir(v_okul, h.siparis_id)
               OR h.durum = 'Onaylandı' AND v_rol = 'Okul Müdürü') THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'Taslağı hazırlayan, onaylı hakedişi yalnız Okul Müdürü iptal edebilir.';
    END IF;
    IF p_surum IS DISTINCT FROM h.surum THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Hakediş değiştirildi; güncelini yükleyin.', HINT = 'surum_cakismasi';
    END IF;
    IF v_gerekce IS NULL OR length(v_gerekce) > 500 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İptal gerekçesi zorunludur (en fazla 500 karakter).';
    END IF;
    IF h.durum = 'Onaylandı' THEN
        PERFORM dose_private.kasa_kilitle(v_okul, 'Banka (102)');
        IF dose_private.pb_odeme(v_okul, h.id) IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ödenmiş hakediş iptal edilemez; önce ödemeyi tersleyin.';
        END IF;
        SELECT jsonb_agg(jsonb_build_object('hesap', hesap_kodu, 'borc', alacak, 'alacak', borc) ORDER BY id)
          INTO v_satirlar FROM public.yevmiye_satir WHERE okul_id = v_okul AND yevmiye_id = h.yevmiye_id;
        v_fis := dose_private.yevmiye_olustur(v_okul, (now() AT TIME ZONE 'Europe/Istanbul')::DATE,
            format('%s parça başı hakediş iptali: %s', h.hakedis_no, v_gerekce), 'ParcaBasi ters kayıt', h.id, v_satirlar);
    END IF;
    UPDATE dose_private.pb_hakedis SET durum = 'İptal', surum = surum + 1 WHERE id = h.id;
    PERFORM dose_private.pb_onay_ekle(v_okul, h.id, 'İptal edildi', v_gerekce);
    PERFORM dose_private.log(v_okul, 'Parça başı hakediş iptal edildi', 'pb_hakedis', h.id, v_gerekce, NULL,
        jsonb_build_object('ters_yevmiye_id', v_fis));
    RETURN jsonb_build_object('id', h.id, 'durum', 'İptal', 'surum', h.surum + 1, 'yevmiye_id', v_fis);
END;
$$;

-- ------------------------------------------------------------------ banka ödemesi (md.7)
CREATE OR REPLACE FUNCTION public.dose_pb_ode(p_id INTEGER, p_tarih DATE, p_belge_no TEXT, p_istek UUID)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); h dose_private.pb_hakedis%ROWTYPE; v_net NUMERIC;
    v_bakiye NUMERIC; v_son DATE; v_hareket INTEGER; v_fis INTEGER; v_kisit TEXT;
    v_belge TEXT := nullif(btrim(p_belge_no), ''); v_aciklama TEXT;
BEGIN
    IF auth.uid() IS NULL OR public.dose_rol() <> 'Sayman' OR public.dose_yetki('kasa') <> 'y'
       OR public.dose_yetki('parca_basi') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Hakediş ödemesini yalnız yetkili sayman yapabilir.';
    END IF;
    IF p_tarih IS NULL OR p_tarih > (now() AT TIME ZONE 'Europe/Istanbul')::DATE OR p_istek IS NULL
       OR length(v_belge) > 100 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Geçerli ödeme tarihi ve işlem kimliği gereklidir.';
    END IF;
    SELECT * INTO h FROM dose_private.pb_hakedis WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
    IF NOT FOUND OR h.durum <> 'Onaylandı' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yalnız Okul Müdürünce onaylanmış hakediş ödenebilir.';
    END IF;
    PERFORM dose_private.kasa_kilitle(v_okul, 'Banka (102)');
    IF EXISTS (SELECT 1 FROM public.kasa_banka WHERE okul_id = v_okul AND istek_id = p_istek) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu ödeme daha önce kaydedildi; listeyi yenileyin.';
    END IF;
    IF dose_private.pb_odeme(v_okul, h.id) IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu hakediş zaten ödendi.';
    END IF;
    IF p_tarih < (SELECT min(zaman)::DATE FROM dose_private.pb_onay WHERE hakedis_id = h.id AND islem = 'Olur') THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ödeme tarihi müdür onayından önce olamaz.';
    END IF;
    SELECT max(tarih::DATE) INTO v_son FROM public.kasa_banka WHERE okul_id = v_okul AND hesap = 'Banka (102)';
    IF v_son IS NOT NULL AND p_tarih < v_son THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Son banka hareketinden daha eski tarihe kayıt yapılamaz.';
    END IF;
    v_net := (h.hesap->'toplam'->>'net')::NUMERIC;
    v_bakiye := dose_private.kasa_bakiye(v_okul, 'Banka (102)');
    IF v_net > v_bakiye THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('Banka bakiyesi yetersiz (%s TL).', v_bakiye);
    END IF;
    v_aciklama := format('%s parça başı hakediş ödemesi (%s kişi)', h.hakedis_no,
        (SELECT count(*) FROM jsonb_array_elements(h.hesap->'kisiler') k WHERE (k->>'net')::NUMERIC > 0));
    BEGIN
        INSERT INTO public.kasa_banka (okul_id, tarih, hesap, yon, tur, tutar, hasilat_tutari, siparis_id, belge_no,
            aciklama, kaynak, karsi_hesap, istek_id, olusturan, pb_hakedis_id)
        VALUES (v_okul, p_tarih::TEXT, 'Banka (102)', 'Çıkış', 'Ödeme', v_net, 0, h.siparis_id, v_belge,
            v_aciklama, 'KasaBanka', '335', p_istek, auth.uid(), h.id) RETURNING id INTO v_hareket;
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS v_kisit = CONSTRAINT_NAME;
        IF v_kisit = 'kasa_istek_tek' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu ödeme daha önce kaydedildi; listeyi yenileyin.';
        END IF;
        RAISE;
    END;
    v_fis := dose_private.yevmiye_olustur(v_okul, p_tarih, v_aciklama, 'KasaBanka', v_hareket, jsonb_build_array(
        jsonb_build_object('hesap', '335', 'borc', v_net, 'alacak', 0),
        jsonb_build_object('hesap', '102', 'borc', 0, 'alacak', v_net)));
    PERFORM dose_private.pb_onay_ekle(v_okul, h.id, 'Ödendi', v_belge);
    PERFORM dose_private.log(v_okul, 'Parça başı hakediş ödendi', 'kasa_banka', v_hareket, v_aciklama, NULL,
        jsonb_build_object('hakedis_id', h.id, 'tutar', v_net::TEXT, 'yevmiye_id', v_fis));
    RETURN jsonb_build_object('id', v_hareket, 'yevmiye_id', v_fis, 'tutar', v_net::TEXT,
        'bakiye', (v_bakiye - v_net)::TEXT);
END;
$$;

REVOKE ALL ON FUNCTION dose_private.pb_sayi(JSONB, TEXT, INTEGER, NUMERIC), dose_private.pb_metin(TEXT, TEXT, INTEGER, INTEGER),
    dose_private.pb_siparis_uygun(INTEGER, INTEGER), dose_private.pb_odeme(INTEGER, INTEGER),
    dose_private.pb_hesap(INTEGER, INTEGER), dose_private.pb_onay_ekle(INTEGER, INTEGER, TEXT, TEXT),
    dose_private.pb_hazirlayabilir(INTEGER, INTEGER), dose_private.pb_kisi_silme_kontrol(),
    dose_private.pb_onay_degismez() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.dose_pb_veri(), public.dose_pb_kaydet(INTEGER, INTEGER, JSONB, JSONB, JSONB, UUID),
    public.dose_pb_gonder(INTEGER, INTEGER), public.dose_pb_karar(INTEGER, INTEGER, BOOLEAN, TEXT),
    public.dose_pb_iptal(INTEGER, INTEGER, TEXT), public.dose_pb_ode(INTEGER, DATE, TEXT, UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_pb_veri(), public.dose_pb_kaydet(INTEGER, INTEGER, JSONB, JSONB, JSONB, UUID),
    public.dose_pb_gonder(INTEGER, INTEGER), public.dose_pb_karar(INTEGER, INTEGER, BOOLEAN, TEXT),
    public.dose_pb_iptal(INTEGER, INTEGER, TEXT), public.dose_pb_ode(INTEGER, DATE, TEXT, UUID) TO authenticated;
