-- Fazla çalışma ücreti (Çalışma Yönergesi md.9, Bütçe Kanunu K cetveli III-3): sipariş ve ay bazında günlük saat
-- puantajı, gün türüne göre günlük saat sınırları, saat ücreti azami tutarı, md.8/7 birlikte ödeme yasağı, sipariş
-- işçilik sınırı, kişi bordrosu, Alan Şefi -> Teknik Müdür Yardımcısı -> Okul Müdürü onayı, tahakkuk ve banka ödemesi.

INSERT INTO dose_private.sayfa_yetki (sayfa, baslik, kodlar)
VALUES ('fazla_calisma', 'Fazla Çalışma', 'gyyyyggg')
ON CONFLICT (sayfa) DO UPDATE SET baslik = EXCLUDED.baslik, kodlar = EXCLUDED.kodlar;

CREATE TABLE dose_private.fc_bordro (
    id SERIAL PRIMARY KEY,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    siparis_id INTEGER NOT NULL REFERENCES public.siparis(id),
    bordro_no TEXT NOT NULL,
    yil INTEGER NOT NULL CHECK (yil BETWEEN 2000 AND 2100),
    ay INTEGER NOT NULL CHECK (ay BETWEEN 1 AND 12),
    saat_ucreti NUMERIC NOT NULL CHECK (saat_ucreti > 0 AND saat_ucreti = round(saat_ucreti, 2)),
    azami_ucret NUMERIC NOT NULL CHECK (azami_ucret > 0 AND azami_ucret = round(azami_ucret, 2)),
    ogretim_gunu_saat NUMERIC NOT NULL CHECK (ogretim_gunu_saat BETWEEN 0 AND 24),
    tatil_gunu_saat NUMERIC NOT NULL CHECK (tatil_gunu_saat BETWEEN 0 AND 24),
    pazar_izinli BOOLEAN NOT NULL DEFAULT false,
    dv_orani NUMERIC NOT NULL CHECK (dv_orani BETWEEN 0 AND 1),
    malzeme_maliyeti NUMERIC NOT NULL DEFAULT 0 CHECK (malzeme_maliyeti >= 0 AND malzeme_maliyeti = round(malzeme_maliyeti, 2)),
    -- Ayın her günü için tür: 'O' öğretim günü, 'T' tatil (Cumartesi, ara/yaz tatili, resmi tatil), 'B' bayram.
    gun_turleri TEXT[] NOT NULL,
    is_tanimi TEXT NOT NULL CHECK (length(is_tanimi) BETWEEN 2 AND 500),
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
    CONSTRAINT fc_bordro_gun_turu CHECK (array_position(gun_turleri, NULL) IS NULL
        AND gun_turleri <@ ARRAY['O', 'T', 'B']::TEXT[]
        AND cardinality(gun_turleri) = extract(day FROM (make_date(yil, ay, 1) + INTERVAL '1 month - 1 day'))),
    CONSTRAINT fc_bordro_istek_tek UNIQUE (okul_id, istek_id),
    CONSTRAINT fc_bordro_no_tek UNIQUE (okul_id, bordro_no)
);
CREATE INDEX fc_bordro_siparis ON dose_private.fc_bordro(okul_id, siparis_id);
CREATE INDEX fc_bordro_donem ON dose_private.fc_bordro(okul_id, yil, ay);

CREATE TABLE dose_private.fc_kisi (
    id SERIAL PRIMARY KEY,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    bordro_id INTEGER NOT NULL REFERENCES dose_private.fc_bordro(id) ON DELETE CASCADE,
    sira INTEGER NOT NULL,
    personel_id INTEGER NOT NULL,
    gorev TEXT CHECK (length(gorev) <= 120),
    gv_orani NUMERIC NOT NULL CHECK (gv_orani BETWEEN 0 AND 1),
    gunler NUMERIC[] NOT NULL,
    UNIQUE (bordro_id, personel_id)
);
CREATE INDEX fc_kisi_personel ON dose_private.fc_kisi(okul_id, personel_id);

CREATE TABLE dose_private.fc_onay (
    id SERIAL PRIMARY KEY,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    bordro_id INTEGER NOT NULL REFERENCES dose_private.fc_bordro(id),
    islem TEXT NOT NULL,
    rol TEXT NOT NULL,
    ad_soyad TEXT NOT NULL,
    aciklama TEXT,
    kullanici UUID NOT NULL REFERENCES auth.users(id),
    zaman TEXT NOT NULL DEFAULT dose_private.zaman()
);
CREATE INDEX fc_onay_bordro ON dose_private.fc_onay(bordro_id);

ALTER TABLE public.kasa_banka ADD COLUMN fc_bordro_id INTEGER REFERENCES dose_private.fc_bordro(id);
CREATE INDEX kasa_fc_indeks ON public.kasa_banka(okul_id, fc_bordro_id) WHERE fc_bordro_id IS NOT NULL;

ALTER TABLE dose_private.fc_bordro ENABLE ROW LEVEL SECURITY;
ALTER TABLE dose_private.fc_kisi ENABLE ROW LEVEL SECURITY;
ALTER TABLE dose_private.fc_onay ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON dose_private.fc_bordro, dose_private.fc_kisi, dose_private.fc_onay FROM PUBLIC, anon, authenticated;

CREATE TRIGGER dose_fc_onay_degismez BEFORE UPDATE OR DELETE ON dose_private.fc_onay
    FOR EACH ROW EXECUTE FUNCTION dose_private.pb_onay_degismez();

CREATE OR REPLACE FUNCTION dose_private.fc_kisi_silme_kontrol() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM dose_private.fc_kisi k WHERE k.okul_id = OLD.okul_id AND k.personel_id = OLD.id) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = 'Bu personel fazla çalışma bordrosunda kullanıldığı için silinemez; pasif yapınız.';
    END IF;
    RETURN OLD;
END;
$$;
CREATE TRIGGER dose_fc_personel_silme BEFORE DELETE ON public.personel
    FOR EACH ROW EXECUTE FUNCTION dose_private.fc_kisi_silme_kontrol();

-- ------------------------------------------------------------------ yardımcılar
CREATE OR REPLACE FUNCTION dose_private.fc_siparis_uygun(p_okul INTEGER, p_siparis INTEGER) RETURNS BOOLEAN
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.siparis s
        JOIN public.onay_durum o ON o.okul_id = s.okul_id AND o.belge_turu = 'Sipariş' AND o.belge_id = s.id
        WHERE s.okul_id = p_okul AND s.id = p_siparis AND o.durum = 'Onaylandı'
          AND coalesce(s.ucret_esasi, '') NOT LIKE 'Parça Başı%')
$$;

CREATE OR REPLACE FUNCTION dose_private.fc_idari(p_gorev TEXT) RETURNS BOOLEAN
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
    SELECT coalesce(p_gorev, '') IN ('Harcama Yetkilisi (Okul Müdürü)', 'Gerçekleştirme Görevlisi (Teknik Md. Yrd.)',
        'Bölüm/Alan Şefi', 'Atölye/Laboratuvar Şefi', 'Sayman', 'Diğer İdari Personel')
$$;

-- Gün türüne göre günlük azami saat (K cetveli III-3; Çalışma Yönergesi md.9/a-12).
CREATE OR REPLACE FUNCTION dose_private.fc_gun_siniri(b dose_private.fc_bordro, p_gun INTEGER) RETURNS NUMERIC
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT CASE
        WHEN b.gun_turleri[p_gun] = 'B' THEN 0
        WHEN extract(dow FROM make_date(b.yil, b.ay, p_gun)) = 0 THEN CASE WHEN b.pazar_izinli THEN b.tatil_gunu_saat ELSE 0 END
        WHEN b.gun_turleri[p_gun] = 'T' THEN b.tatil_gunu_saat
        ELSE b.ogretim_gunu_saat END
$$;

CREATE OR REPLACE FUNCTION dose_private.fc_odeme(p_okul INTEGER, p_bordro INTEGER) RETURNS JSONB
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT jsonb_build_object('id', k.id, 'tarih', k.tarih, 'tutar', k.tutar::TEXT, 'belge_no', k.belge_no)
    FROM public.kasa_banka k
    WHERE k.okul_id = p_okul AND k.fc_bordro_id = p_bordro AND k.ters_hareket_id IS NULL
      AND NOT EXISTS (SELECT 1 FROM public.kasa_banka t WHERE t.okul_id = k.okul_id AND t.ters_hareket_id = k.id)
    ORDER BY k.id DESC LIMIT 1
$$;

CREATE OR REPLACE FUNCTION dose_private.fc_onay_ekle(p_okul INTEGER, p_bordro INTEGER, p_islem TEXT, p_aciklama TEXT)
RETURNS VOID LANGUAGE sql VOLATILE SET search_path = '' AS $$
    INSERT INTO dose_private.fc_onay (okul_id, bordro_id, islem, rol, ad_soyad, aciklama, kullanici)
    SELECT p_okul, p_bordro, p_islem, u.rol, u.ad_soyad, p_aciklama, auth.uid()
    FROM dose_private.uyelik u WHERE u.auth_user_id = auth.uid()
$$;

CREATE OR REPLACE FUNCTION dose_private.fc_hazirlayabilir(p_okul INTEGER, p_siparis INTEGER) RETURNS BOOLEAN
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT auth.uid() IS NOT NULL AND public.dose_yetki('fazla_calisma') = 'y'
       AND public.dose_rol() IN ('Alan Şefi', 'Teknik Müdür Yardımcısı')
       AND (public.dose_rol() <> 'Alan Şefi' OR EXISTS (
            SELECT 1 FROM public.siparis s WHERE s.okul_id = p_okul AND s.id = p_siparis
              AND s.bolum_id = public.dose_bolum()))
$$;

-- Puantaj kontrolleri ve bordro. Tutarlar kuruşa yuvarlanır.
CREATE OR REPLACE FUNCTION dose_private.fc_hesap(p_okul INTEGER, p_bordro INTEGER) RETURNS JSONB
LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE
    b dose_private.fc_bordro%ROWTYPE;
    s public.siparis%ROWTYPE;
    v_gun_sayisi INTEGER; v_mevzuat JSONB; v_deg JSONB;
    v_hatalar TEXT[] := ARRAY[]::TEXT[]; v_uyarilar TEXT[] := ARRAY[]::TEXT[];
    v_kisiler JSONB; v_top_saat NUMERIC; v_top_brut NUMERIC; v_top_gv NUMERIC; v_top_dv NUMERIC;
    v_sinirlar JSONB; v_iscilik NUMERIC; v_diger_brut NUMERIC; v_satir RECORD; v_ilk DATE;
BEGIN
    SELECT * INTO b FROM dose_private.fc_bordro WHERE okul_id = p_okul AND id = p_bordro;
    IF NOT FOUND THEN RETURN NULL; END IF;
    SELECT * INTO s FROM public.siparis WHERE okul_id = p_okul AND id = b.siparis_id;
    v_gun_sayisi := cardinality(b.gun_turleri);
    SELECT jsonb_agg(dose_private.fc_gun_siniri(b, g)::TEXT ORDER BY g) INTO v_sinirlar
    FROM generate_series(1, v_gun_sayisi) g;

    IF NOT dose_private.fc_siparis_uygun(p_okul, b.siparis_id) THEN
        v_hatalar := array_append(v_hatalar,
            'Sipariş onaylı olmalı; parça başı esaslı siparişte fazla çalışma ödenmez (md.7/3, md.8/7).'::TEXT);
    ELSIF coalesce(s.ucret_esasi, '') NOT LIKE 'Fazla%' THEN
        v_uyarilar := v_uyarilar || format('Siparişin ücret esası "%s"; fazla çalışma ücreti esaslı değil (md.7/3).',
            coalesce(s.ucret_esasi, '-'));
    END IF;
    IF b.saat_ucreti > b.azami_ucret THEN
        v_hatalar := v_hatalar || format('Saat ücreti (%s TL) azami tutarı (%s TL) aşamaz (K cetveli III-3).',
            b.saat_ucreti, b.azami_ucret);
    END IF;
    IF EXISTS (SELECT 1 FROM dose_private.pb_hakedis x WHERE x.okul_id = p_okul AND x.siparis_id = b.siparis_id
               AND x.durum <> 'İptal') THEN
        v_hatalar := array_append(v_hatalar, 'Bu siparişte parça başı hakediş var; aynı iş için fazla çalışma ödenmez (md.8/7).'::TEXT);
    END IF;

    WITH k AS (
        SELECT fk.*, (SELECT coalesce(sum(x), 0) FROM unnest(fk.gunler) x) AS saat
        FROM dose_private.fc_kisi fk WHERE fk.bordro_id = b.id
    ), f AS (
        SELECT k.*, round(k.saat * b.saat_ucreti, 2) AS brut, p.ad_soyad, p.tckn, p.iban, p.aktif, p.kadro_unvani,
               p.hizmet_sinifi, p.dose_gorevi, p.id IS NULL AS yok
        FROM k LEFT JOIN public.personel p ON p.okul_id = p_okul AND p.id = k.personel_id
    ), g AS (
        SELECT f.*, round(f.brut * f.gv_orani, 2) AS gv, round(f.brut * b.dv_orani, 2) AS dv FROM f
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'id', g.id, 'sira', g.sira, 'personel_id', g.personel_id, 'ad_soyad', g.ad_soyad, 'tckn', g.tckn,
               'iban', g.iban, 'gorev', g.gorev, 'kadro_unvani', g.kadro_unvani, 'hizmet_sinifi', g.hizmet_sinifi,
               'dose_gorevi', g.dose_gorevi,
               'gunler', (SELECT jsonb_agg(x::TEXT ORDER BY i) FROM unnest(g.gunler) WITH ORDINALITY AS u(x, i)),
               'saat', g.saat::TEXT, 'saat_ucreti', b.saat_ucreti::TEXT, 'gv_orani', g.gv_orani::TEXT,
               'brut', g.brut::TEXT, 'gelir_vergisi', g.gv::TEXT, 'damga_vergisi', g.dv::TEXT,
               'net', (g.brut - g.gv - g.dv)::TEXT, 'yok', g.yok, 'aktif', g.aktif) ORDER BY g.sira), '[]'::JSONB),
           coalesce(sum(g.saat), 0), coalesce(sum(g.brut), 0), coalesce(sum(g.gv), 0), coalesce(sum(g.dv), 0)
      INTO v_kisiler, v_top_saat, v_top_brut, v_top_gv, v_top_dv
    FROM g;

    IF jsonb_array_length(v_kisiler) = 0 OR v_top_saat = 0 THEN
        v_hatalar := array_append(v_hatalar, 'Puantajda fazla çalışma saati yok.'::TEXT);
    END IF;

    FOR v_satir IN SELECT value AS k FROM jsonb_array_elements(v_kisiler) LOOP
        IF (v_satir.k->>'yok')::BOOLEAN THEN
            v_hatalar := v_hatalar || format('%s. satırdaki personel kaydı bulunamadı.', v_satir.k->>'sira');
            CONTINUE;
        END IF;
        IF (v_satir.k->>'saat')::NUMERIC = 0 THEN
            v_uyarilar := v_uyarilar || format('%s için puantajda saat yok; ödeme yapılmaz.', v_satir.k->>'ad_soyad');
            CONTINUE;
        END IF;
        IF (v_satir.k->>'aktif')::INTEGER IS DISTINCT FROM 1 THEN
            v_hatalar := v_hatalar || format('%s kaydı pasif.', v_satir.k->>'ad_soyad');
        END IF;
        IF v_satir.k->>'iban' IS NULL THEN
            v_hatalar := v_hatalar || format('%s için IBAN kayıtlı değil; banka ödemesi yapılamaz (md.7).', v_satir.k->>'ad_soyad');
        END IF;
        IF coalesce(v_satir.k->>'hizmet_sinifi', '') LIKE 'Yardımcı%' THEN
            v_hatalar := v_hatalar || format('%s Yardımcı Hizmetler sınıfında; fazla çalışma ücreti ödenmez (md.9).',
                v_satir.k->>'ad_soyad');
        END IF;
        IF coalesce(v_satir.k->>'kadro_unvani', '') || ' ' || coalesce(v_satir.k->>'dose_gorevi', '')
           ~* '[şŞsS][oO][fF][öÖoO][rR]' THEN
            v_hatalar := v_hatalar || format('%s şoför; fazla çalışma ücreti ödenmez (md.9).', v_satir.k->>'ad_soyad');
        END IF;
        IF EXISTS (SELECT 1 FROM dose_private.pb_kisi pk JOIN dose_private.pb_hakedis h ON h.id = pk.hakedis_id
                   WHERE pk.okul_id = p_okul AND pk.kisi_turu = 'Öğretmen'
                     AND pk.kisi_id = (v_satir.k->>'personel_id')::INTEGER
                     AND h.yil = b.yil AND h.ay = b.ay AND h.durum <> 'İptal'
                     AND (SELECT coalesce(sum(x), 0) FROM unnest(pk.gunler) x) > 0) THEN
            IF dose_private.fc_idari(v_satir.k->>'dose_gorevi') THEN
                v_hatalar := v_hatalar || format('%s idari görevli; aynı ay parça başı aldığı için fazla çalışma ödenmez (md.8/7).',
                    v_satir.k->>'ad_soyad');
            ELSE
                v_uyarilar := v_uyarilar || format('%s bu ay başka işte parça başı da alıyor; aynı iş olmadığını kontrol ediniz (md.8/7).',
                    v_satir.k->>'ad_soyad');
            END IF;
        END IF;
    END LOOP;

    -- Günlük sınırlar: kişinin aynı ay diğer fazla çalışma bordroları ile birlikte.
    FOR v_satir IN
        WITH bu AS (
            SELECT fk.personel_id, u.i::INTEGER AS gun, u.x AS saat
            FROM dose_private.fc_kisi fk, unnest(fk.gunler) WITH ORDINALITY AS u(x, i)
            WHERE fk.bordro_id = b.id AND u.x > 0
        ), diger AS (
            SELECT fk.personel_id, u.i::INTEGER AS gun, sum(u.x) AS saat
            FROM dose_private.fc_kisi fk JOIN dose_private.fc_bordro o ON o.id = fk.bordro_id,
                 unnest(fk.gunler) WITH ORDINALITY AS u(x, i)
            WHERE o.okul_id = p_okul AND o.yil = b.yil AND o.ay = b.ay AND o.id <> b.id AND o.durum <> 'İptal'
            GROUP BY fk.personel_id, u.i
        )
        SELECT bu.personel_id, bu.gun, bu.saat, coalesce(d.saat, 0) AS diger, dose_private.fc_gun_siniri(b, bu.gun) AS sinir,
               (SELECT p.ad_soyad FROM public.personel p WHERE p.okul_id = p_okul AND p.id = bu.personel_id) AS ad
        FROM bu LEFT JOIN diger d ON d.personel_id = bu.personel_id AND d.gun = bu.gun
        WHERE bu.saat + coalesce(d.saat, 0) > dose_private.fc_gun_siniri(b, bu.gun)
        ORDER BY bu.gun, bu.personel_id
    LOOP
        v_hatalar := v_hatalar || format('%s: %s günü %s saat yazılmış%s; o gün için sınır %s saat.',
            v_satir.ad, to_char(make_date(b.yil, b.ay, v_satir.gun), 'DD.MM.YYYY'), trim_scale(v_satir.saat),
            CASE WHEN v_satir.diger > 0 THEN format(' (diğer bordrolarda %s saat daha)', trim_scale(v_satir.diger)) ELSE '' END,
            trim_scale(v_satir.sinir));
    END LOOP;

    BEGIN
        v_ilk := s.tarih::DATE;
    EXCEPTION WHEN OTHERS THEN
        v_ilk := NULL;
    END;
    IF v_ilk IS NOT NULL AND EXISTS (
        SELECT 1 FROM dose_private.fc_kisi fk, unnest(fk.gunler) WITH ORDINALITY AS u(x, i)
        WHERE fk.bordro_id = b.id AND u.x > 0 AND make_date(b.yil, b.ay, u.i::INTEGER) < v_ilk) THEN
        v_hatalar := array_append(v_hatalar, 'Puantajda sipariş tarihinden önceki günlere saat yazılmış.'::TEXT);
    END IF;

    -- Sipariş işçilik sınırı (md.9/b, md.42/e): fazla çalışma esasında kâr ve faaliyet gideri parça başı oranlarıyla ayrılır.
    BEGIN
        v_mevzuat := dose_private.mevzuat_oku(p_okul, make_date(b.yil, b.ay, v_gun_sayisi));
        v_deg := v_mevzuat->'degerler';
    EXCEPTION WHEN raise_exception THEN
        v_hatalar := v_hatalar || ('Merkez parametreleri: ' || SQLERRM);
    END;
    SELECT coalesce(sum((x->>'brut')::NUMERIC), 0) INTO v_diger_brut
    FROM dose_private.fc_bordro o, jsonb_array_elements(coalesce(o.hesap->'kisiler', '[]'::JSONB)) x
    WHERE o.okul_id = p_okul AND o.siparis_id = b.siparis_id AND o.id <> b.id AND o.durum = 'Onaylandı';
    SELECT v_diger_brut + coalesce(sum(round(
               (SELECT coalesce(sum(x), 0) FROM unnest(fk.gunler) x) * o.saat_ucreti, 2)), 0)
      INTO v_diger_brut
    FROM dose_private.fc_bordro o JOIN dose_private.fc_kisi fk ON fk.bordro_id = o.id
    WHERE o.okul_id = p_okul AND o.siparis_id = b.siparis_id AND o.id <> b.id
      AND o.durum IN ('TMY Onayında', 'Müdür Onayında');
    IF v_deg IS NOT NULL AND s.id IS NOT NULL THEN
        v_iscilik := s.sozlesme_bedeli - round(s.sozlesme_bedeli * (v_deg->>'pb_kar_orani')::NUMERIC, 2)
            - round(s.sozlesme_bedeli * (v_deg->>'pb_faaliyet_orani')::NUMERIC, 2) - b.malzeme_maliyeti;
        IF v_diger_brut + v_top_brut > v_iscilik THEN
            v_hatalar := v_hatalar || format('Siparişteki fazla çalışma toplamı (%s TL) siparişin işçilik payını (%s TL) aşıyor (md.9/b).',
                v_diger_brut + v_top_brut, greatest(v_iscilik, 0));
        END IF;
    END IF;

    RETURN jsonb_build_object(
        'gun_sayisi', v_gun_sayisi, 'gun_turleri', to_jsonb(b.gun_turleri), 'gun_sinirlari', v_sinirlar,
        'aylik_sinir', (SELECT sum((x)::NUMERIC) FROM jsonb_array_elements_text(v_sinirlar) x)::TEXT,
        'saat_ucreti', b.saat_ucreti::TEXT, 'azami_ucret', b.azami_ucret::TEXT, 'dv_orani', b.dv_orani::TEXT,
        'kisiler', v_kisiler,
        'toplam', jsonb_build_object('saat', v_top_saat::TEXT, 'brut', v_top_brut::TEXT, 'gelir_vergisi', v_top_gv::TEXT,
                                     'damga_vergisi', v_top_dv::TEXT, 'net', (v_top_brut - v_top_gv - v_top_dv)::TEXT),
        'siparis_iscilik', CASE WHEN v_iscilik IS NULL THEN NULL ELSE greatest(v_iscilik, 0)::TEXT END,
        'siparis_diger_fc', v_diger_brut::TEXT,
        'siparis_kalan', CASE WHEN v_iscilik IS NULL THEN NULL ELSE (v_iscilik - v_diger_brut - v_top_brut)::TEXT END,
        'mevzuat_yayin_id', v_mevzuat->'yayin_id',
        'hatalar', to_jsonb(v_hatalar), 'uyarilar', to_jsonb(v_uyarilar));
END;
$$;

-- Parça başı tarafındaki md.8/7 kontrolü artık yeni fazla çalışma bordrosuna bakar; idari görevlinin aynı ay
-- fazla çalışma ücreti de engellenir.
DO $$
DECLARE v_tanim TEXT; v_yeni TEXT;
BEGIN
    v_tanim := pg_get_functiondef('dose_private.pb_hesap(integer, integer)'::regprocedure);
    v_yeni := regexp_replace(v_tanim,
        'public\.fazla_calisma f WHERE f\.okul_id = p_okul AND f\.siparis_id = h\.siparis_id\s+AND coalesce\(f\.durum, ''''\) <> ''İptal''',
        'dose_private.fc_bordro f WHERE f.okul_id = p_okul AND f.siparis_id = h.siparis_id AND f.durum <> ''İptal''');
    v_yeni := regexp_replace(v_yeni,
        '(''Aynı sipariş için fazla çalışma ücreti ödenemez \(md\.8/7\)\.''::TEXT\);\s+END IF;)',
        E'\\1\n    FOR v_satir IN SELECT p.ad_soyad FROM dose_private.pb_kisi pk\n'
        '        JOIN public.personel p ON p.okul_id = p_okul AND p.id = pk.kisi_id\n'
        '        WHERE pk.hakedis_id = h.id AND pk.kisi_turu = ''Öğretmen'' AND dose_private.fc_idari(p.dose_gorevi)\n'
        '          AND EXISTS (SELECT 1 FROM dose_private.fc_kisi fk JOIN dose_private.fc_bordro fb ON fb.id = fk.bordro_id\n'
        '                      WHERE fk.okul_id = p_okul AND fk.personel_id = pk.kisi_id AND fb.yil = h.yil AND fb.ay = h.ay\n'
        '                        AND fb.durum <> ''İptal'' AND (SELECT coalesce(sum(x), 0) FROM unnest(fk.gunler) x) > 0)\n'
        '    LOOP\n'
        '        v_hatalar := v_hatalar || format(''%s idari görevli; aynı ay fazla çalışma ücreti aldığı için parça başı ödenmez (md.8/7).'', v_satir.ad_soyad);\n'
        '    END LOOP;');
    IF v_yeni = v_tanim OR position('dose_private.fc_bordro' IN v_yeni) = 0 OR position('fc_idari' IN v_yeni) = 0 THEN
        RAISE EXCEPTION 'pb_hesap md.8/7 kontrolü güncellenemedi';
    END IF;
    EXECUTE v_yeni;
END;
$$;

-- ------------------------------------------------------------------ okuma
CREATE OR REPLACE FUNCTION public.dose_fc_veri() RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_kisitli BOOLEAN := public.dose_bolum_kisitli();
    v_bolum INTEGER := public.dose_bolum();
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('fazla_calisma') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Fazla çalışma ekranına erişim yetkiniz yok.';
    END IF;
    RETURN jsonb_build_object(
        'okul', (SELECT jsonb_build_object('ad', o.ad, 'kurum_kodu', o.kurum_kodu) FROM dose_private.okul o WHERE o.id = v_okul),
        'siparisler', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', s.id, 'siparis_no', s.siparis_no, 'konu', s.konu, 'tarih', s.tarih, 'bolum_id', s.bolum_id,
            'bolum', b.ad, 'cari', c.unvan, 'ucret_esasi', s.ucret_esasi, 'sozlesme_bedeli', s.sozlesme_bedeli::TEXT)
            ORDER BY s.id DESC)
            FROM public.siparis s
            LEFT JOIN public.bolum b ON b.okul_id = s.okul_id AND b.id = s.bolum_id
            LEFT JOIN public.cari c ON c.okul_id = s.okul_id AND c.id = s.cari_id
            WHERE s.okul_id = v_okul AND dose_private.fc_siparis_uygun(v_okul, s.id)
              AND (NOT v_kisitli OR s.bolum_id = v_bolum)), '[]'::JSONB),
        'personel', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', p.id, 'ad_soyad', p.ad_soyad, 'bolum_id', p.bolum_id, 'kadro_unvani', p.kadro_unvani,
            'hizmet_sinifi', p.hizmet_sinifi, 'dose_gorevi', p.dose_gorevi, 'iban_var', p.iban IS NOT NULL)
            ORDER BY p.ad_soyad, p.id)
            FROM public.personel p WHERE p.okul_id = v_okul AND p.aktif = 1
              AND (NOT v_kisitli OR p.bolum_id = v_bolum)), '[]'::JSONB),
        'bordrolar', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'id', f.id, 'bordro_no', f.bordro_no, 'siparis_id', f.siparis_id, 'siparis_no', s.siparis_no,
            'siparis_konu', s.konu, 'cari', c.unvan, 'bolum', b.ad, 'yil', f.yil, 'ay', f.ay,
            'saat_ucreti', f.saat_ucreti::TEXT, 'azami_ucret', f.azami_ucret::TEXT,
            'ogretim_gunu_saat', f.ogretim_gunu_saat::TEXT, 'tatil_gunu_saat', f.tatil_gunu_saat::TEXT,
            'pazar_izinli', f.pazar_izinli, 'dv_orani', f.dv_orani::TEXT, 'malzeme_maliyeti', f.malzeme_maliyeti::TEXT,
            'gun_turleri', to_jsonb(f.gun_turleri), 'is_tanimi', f.is_tanimi, 'aciklama', f.aciklama,
            'durum', f.durum, 'surum', f.surum, 'olusturan_rol', f.olusturan_rol, 'olusturma', f.olusturma,
            'yevmiye_id', f.yevmiye_id,
            'kisiler', coalesce((SELECT jsonb_agg(jsonb_build_object('personel_id', k.personel_id, 'gorev', k.gorev,
                'gv_orani', k.gv_orani::TEXT,
                'gunler', (SELECT jsonb_agg(g::TEXT ORDER BY i) FROM unnest(k.gunler) WITH ORDINALITY AS u(g, i)))
                ORDER BY k.sira) FROM dose_private.fc_kisi k WHERE k.bordro_id = f.id), '[]'::JSONB),
            'hesap', CASE WHEN f.durum IN ('Onaylandı', 'İptal') AND f.hesap IS NOT NULL THEN f.hesap
                          ELSE dose_private.fc_hesap(v_okul, f.id) END,
            'onaylar', coalesce((SELECT jsonb_agg(jsonb_build_object('islem', a.islem, 'rol', a.rol,
                'ad_soyad', a.ad_soyad, 'aciklama', a.aciklama, 'zaman', a.zaman) ORDER BY a.id)
                FROM dose_private.fc_onay a WHERE a.bordro_id = f.id), '[]'::JSONB),
            'odeme', dose_private.fc_odeme(v_okul, f.id))
            ORDER BY f.yil DESC, f.ay DESC, f.id DESC)
            FROM dose_private.fc_bordro f
            JOIN public.siparis s ON s.okul_id = f.okul_id AND s.id = f.siparis_id
            LEFT JOIN public.cari c ON c.okul_id = s.okul_id AND c.id = s.cari_id
            LEFT JOIN public.bolum b ON b.okul_id = s.okul_id AND b.id = s.bolum_id
            WHERE f.okul_id = v_okul AND (NOT v_kisitli OR s.bolum_id = v_bolum)), '[]'::JSONB),
        'banka_bakiye', CASE WHEN public.dose_rol() = 'Sayman'
                             THEN dose_private.kasa_bakiye(v_okul, 'Banka (102)')::TEXT END);
END;
$$;

-- ------------------------------------------------------------------ taslak kaydı
CREATE OR REPLACE FUNCTION public.dose_fc_kaydet(
    p_id INTEGER, p_surum INTEGER, p_veri JSONB, p_kisiler JSONB, p_istek UUID
) RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul();
    v_eski dose_private.fc_bordro%ROWTYPE;
    v_siparis public.siparis%ROWTYPE;
    v_id INTEGER; v_surum INTEGER; v_kisit TEXT;
    v_yil INTEGER; v_ay INTEGER; v_gun_sayisi INTEGER;
    v_saat NUMERIC; v_azami NUMERIC; v_ogretim NUMERIC; v_tatil NUMERIC; v_dv NUMERIC; v_malzeme NUMERIC;
    v_pazar BOOLEAN; v_turler TEXT[]; v_is TEXT; v_aciklama TEXT;
    v_k JSONB; v_sira INTEGER := 0; v_gunler NUMERIC[]; v_g JSONB; v_kisi INTEGER;
BEGIN
    IF v_okul IS NULL OR auth.uid() IS NULL OR public.dose_yetki('fazla_calisma') <> 'y'
       OR public.dose_rol() NOT IN ('Alan Şefi', 'Teknik Müdür Yardımcısı') THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'Fazla çalışma bordrosunu yalnız yetkili Alan Şefi veya Teknik Müdür Yardımcısı hazırlayabilir.';
    END IF;
    IF jsonb_typeof(p_veri) IS DISTINCT FROM 'object' OR jsonb_typeof(p_kisiler) IS DISTINCT FROM 'array'
       OR p_istek IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bordro bilgileri eksik.';
    END IF;
    IF p_id IS NOT NULL THEN
        SELECT * INTO v_eski FROM dose_private.fc_bordro WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bordro bulunamadı.';
        END IF;
        IF v_eski.durum <> 'Taslak' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yalnız taslak durumundaki bordro değiştirilebilir.';
        END IF;
        IF p_surum IS DISTINCT FROM v_eski.surum THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bordro başka biri tarafından değiştirildi; güncelini yükleyin.',
                HINT = 'surum_cakismasi';
        END IF;
        IF NOT dose_private.fc_hazirlayabilir(v_okul, v_eski.siparis_id) THEN
            RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Bu bordroyu değiştirme yetkiniz yok.';
        END IF;
    ELSIF EXISTS (SELECT 1 FROM dose_private.fc_bordro WHERE okul_id = v_okul AND istek_id = p_istek) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu bordro daha önce kaydedildi; listeyi yenileyin.';
    END IF;

    IF jsonb_typeof(p_veri->'siparis_id') IS DISTINCT FROM 'number' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Onaylı siparişi seçiniz.';
    END IF;
    SELECT * INTO v_siparis FROM public.siparis WHERE okul_id = v_okul AND id = (p_veri->>'siparis_id')::INTEGER FOR SHARE;
    IF NOT FOUND OR NOT dose_private.fc_siparis_uygun(v_okul, v_siparis.id) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = 'Onaylı ve parça başı esaslı olmayan bir sipariş seçiniz (md.7/3).';
    END IF;
    IF p_id IS NOT NULL AND v_siparis.id <> v_eski.siparis_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Kaydedilmiş bordronun siparişi değiştirilemez.';
    END IF;
    IF NOT dose_private.fc_hazirlayabilir(v_okul, v_siparis.id) THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Yalnız kendi bölümünüzün siparişi için bordro hazırlayabilirsiniz.';
    END IF;

    IF jsonb_typeof(p_veri->'yil') IS DISTINCT FROM 'number' OR jsonb_typeof(p_veri->'ay') IS DISTINCT FROM 'number'
       OR (p_veri->>'yil') !~ '^[0-9]{4}$' OR (p_veri->>'ay') !~ '^[0-9]{1,2}$'
       OR (p_veri->>'yil')::INTEGER NOT BETWEEN 2000 AND 2100 OR (p_veri->>'ay')::INTEGER NOT BETWEEN 1 AND 12 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bordro yılı ve ayını geçerli giriniz.';
    END IF;
    v_yil := (p_veri->>'yil')::INTEGER; v_ay := (p_veri->>'ay')::INTEGER;
    v_gun_sayisi := extract(day FROM (make_date(v_yil, v_ay, 1) + INTERVAL '1 month - 1 day'))::INTEGER;
    IF make_date(v_yil, v_ay, 1) + INTERVAL '1 month - 1 day' < date_trunc('month', v_siparis.tarih::DATE) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bordro ayı sipariş tarihinden önce olamaz.';
    END IF;
    IF p_id IS NOT NULL AND (v_yil <> v_eski.yil OR v_ay <> v_eski.ay) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Kaydedilmiş bordronun dönemi değiştirilemez.';
    END IF;

    v_saat := dose_private.pb_sayi(p_veri->'saat_ucreti', 'Saat ücreti', 2, 99999);
    v_azami := dose_private.pb_sayi(p_veri->'azami_ucret', 'Saat ücreti azami tutarı', 2, 99999);
    IF v_saat <= 0 OR v_azami <= 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Saat ücreti ve azami tutar sıfırdan büyük olmalıdır.';
    END IF;
    v_ogretim := dose_private.pb_sayi(p_veri->'ogretim_gunu_saat', 'Öğretim günü azami saati', 2, 24);
    v_tatil := dose_private.pb_sayi(p_veri->'tatil_gunu_saat', 'Tatil günü azami saati', 2, 24);
    v_dv := dose_private.pb_sayi(p_veri->'dv_orani', 'Damga vergisi oranı', 10, 1);
    v_malzeme := dose_private.pb_sayi(coalesce(p_veri->'malzeme_maliyeti', '"0"'), 'Siparişin malzeme maliyeti', 2, 999999999999);
    IF jsonb_typeof(p_veri->'pazar_izinli') IS DISTINCT FROM 'boolean' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Pazar günü çalışma izni seçilmelidir.';
    END IF;
    v_pazar := (p_veri->>'pazar_izinli')::BOOLEAN;
    IF jsonb_typeof(p_veri->'gun_turleri') IS DISTINCT FROM 'array'
       OR jsonb_array_length(p_veri->'gun_turleri') <> v_gun_sayisi
       OR EXISTS (SELECT 1 FROM jsonb_array_elements(p_veri->'gun_turleri') t
                  WHERE jsonb_typeof(t) IS DISTINCT FROM 'string' OR t #>> '{}' NOT IN ('O', 'T', 'B')) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = format('Ayın %s günü için gün türü (öğretim/tatil/bayram) belirtilmelidir.', v_gun_sayisi);
    END IF;
    SELECT array_agg(t ORDER BY i) INTO v_turler FROM jsonb_array_elements_text(p_veri->'gun_turleri') WITH ORDINALITY AS u(t, i);
    v_is := dose_private.pb_metin(p_veri->>'is_tanimi', 'Yapılan iş', 2, 500);
    v_aciklama := nullif(btrim(p_veri->>'aciklama'), '');
    IF length(v_aciklama) > 1000 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Açıklama en fazla 1000 karakter olabilir.';
    END IF;
    IF jsonb_array_length(p_kisiler) = 0 OR jsonb_array_length(p_kisiler) > 300 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Puantaja 1-300 personel ekleyiniz.';
    END IF;

    IF p_id IS NULL THEN
        BEGIN
            INSERT INTO dose_private.fc_bordro (okul_id, siparis_id, bordro_no, yil, ay, saat_ucreti, azami_ucret,
                ogretim_gunu_saat, tatil_gunu_saat, pazar_izinli, dv_orani, malzeme_maliyeti, gun_turleri, is_tanimi,
                aciklama, olusturan, olusturan_rol, istek_id)
            VALUES (v_okul, v_siparis.id,
                format('FC-%s-%s', v_yil, lpad(dose_private.sira_no(v_okul, 'fazla_calisma', v_yil)::TEXT, 4, '0')),
                v_yil, v_ay, v_saat, v_azami, v_ogretim, v_tatil, v_pazar, v_dv, v_malzeme, v_turler, v_is,
                v_aciklama, auth.uid(), public.dose_rol(), p_istek)
            RETURNING id, surum INTO v_id, v_surum;
        EXCEPTION WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS v_kisit = CONSTRAINT_NAME;
            IF v_kisit = 'fc_bordro_istek_tek' THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu bordro daha önce kaydedildi; listeyi yenileyin.';
            END IF;
            RAISE;
        END;
        PERFORM dose_private.fc_onay_ekle(v_okul, v_id, 'Hazırlandı', NULL);
    ELSE
        UPDATE dose_private.fc_bordro SET saat_ucreti = v_saat, azami_ucret = v_azami, ogretim_gunu_saat = v_ogretim,
            tatil_gunu_saat = v_tatil, pazar_izinli = v_pazar, dv_orani = v_dv, malzeme_maliyeti = v_malzeme,
            gun_turleri = v_turler, is_tanimi = v_is, aciklama = v_aciklama, surum = surum + 1
        WHERE id = p_id RETURNING id, surum INTO v_id, v_surum;
        DELETE FROM dose_private.fc_kisi WHERE bordro_id = v_id;
    END IF;

    FOR v_k IN SELECT value FROM jsonb_array_elements(p_kisiler) LOOP
        v_sira := v_sira + 1;
        IF jsonb_typeof(v_k) IS DISTINCT FROM 'object' OR jsonb_typeof(v_k->'personel_id') IS DISTINCT FROM 'number'
           OR jsonb_typeof(v_k->'gunler') IS DISTINCT FROM 'array' OR (v_k->>'personel_id') !~ '^[0-9]{1,9}$' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. puantaj satırı geçersiz.', v_sira);
        END IF;
        v_kisi := (v_k->>'personel_id')::INTEGER;
        IF NOT EXISTS (SELECT 1 FROM public.personel WHERE okul_id = v_okul AND id = v_kisi AND aktif = 1) THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. puantaj satırındaki personel aktif değil veya bulunamadı.', v_sira);
        END IF;
        IF jsonb_array_length(v_k->'gunler') <> v_gun_sayisi THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001',
                MESSAGE = format('%s. puantaj satırında ayın %s günü için değer olmalıdır.', v_sira, v_gun_sayisi);
        END IF;
        v_gunler := ARRAY[]::NUMERIC[];
        FOR v_g IN SELECT value FROM jsonb_array_elements(v_k->'gunler') LOOP
            v_gunler := array_append(v_gunler, dose_private.pb_sayi(
                CASE WHEN v_g = '""'::JSONB OR v_g = 'null'::JSONB THEN '"0"'::JSONB ELSE v_g END,
                format('%s. puantaj satırındaki saat', v_sira), 2, 24));
        END LOOP;
        BEGIN
            INSERT INTO dose_private.fc_kisi (okul_id, bordro_id, sira, personel_id, gorev, gv_orani, gunler)
            VALUES (v_okul, v_id, v_sira, v_kisi, nullif(btrim(v_k->>'gorev'), ''),
                dose_private.pb_sayi(coalesce(v_k->'gv_orani', 'null'::JSONB), format('%s. satırdaki gelir vergisi oranı', v_sira), 4, 1),
                v_gunler);
        EXCEPTION WHEN unique_violation THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. puantaj satırındaki personel listede birden fazla kez var.', v_sira);
        WHEN check_violation THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. puantaj satırındaki görev en fazla 120 karakter olabilir.', v_sira);
        END;
    END LOOP;

    PERFORM dose_private.log(v_okul, CASE WHEN p_id IS NULL THEN 'Fazla çalışma bordrosu hazırlandı' ELSE 'Fazla çalışma bordrosu güncellendi' END,
        'fc_bordro', v_id, v_is, to_jsonb(v_eski), NULL);
    RETURN jsonb_build_object('id', v_id, 'surum', v_surum, 'hesap', dose_private.fc_hesap(v_okul, v_id));
END;
$$;

-- ------------------------------------------------------------------ onay zinciri
CREATE OR REPLACE FUNCTION public.dose_fc_gonder(p_id INTEGER, p_surum INTEGER) RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); b dose_private.fc_bordro%ROWTYPE; v_hesap JSONB; v_durum TEXT; v_son INTEGER;
BEGIN
    SELECT * INTO b FROM dose_private.fc_bordro WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
    IF NOT FOUND OR NOT dose_private.fc_hazirlayabilir(v_okul, b.siparis_id) THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Bu bordroyu onaya gönderme yetkiniz yok.';
    END IF;
    IF b.durum <> 'Taslak' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yalnız taslak bordro onaya gönderilebilir.';
    END IF;
    IF p_surum IS DISTINCT FROM b.surum THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bordro değiştirildi; güncelini yükleyin.', HINT = 'surum_cakismasi';
    END IF;
    SELECT max(u.i) INTO v_son FROM dose_private.fc_kisi fk, unnest(fk.gunler) WITH ORDINALITY AS u(x, i)
    WHERE fk.bordro_id = b.id AND u.x > 0;
    IF v_son IS NOT NULL AND make_date(b.yil, b.ay, v_son) > (now() AT TIME ZONE 'Europe/Istanbul')::DATE THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Henüz çalışılmamış günlere saat yazılan bordro onaya gönderilemez.';
    END IF;
    -- Aynı siparişin bordroları sırayla denetlensin.
    PERFORM 1 FROM public.siparis WHERE okul_id = v_okul AND id = b.siparis_id FOR UPDATE;
    v_hesap := dose_private.fc_hesap(v_okul, b.id);
    IF jsonb_array_length(v_hesap->'hatalar') > 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bordro kontrolleri tamamlanmadı: ' || (v_hesap->'hatalar'->>0);
    END IF;
    v_durum := CASE WHEN public.dose_rol() = 'Teknik Müdür Yardımcısı' THEN 'Müdür Onayında' ELSE 'TMY Onayında' END;
    UPDATE dose_private.fc_bordro SET durum = v_durum, surum = surum + 1 WHERE id = b.id;
    PERFORM dose_private.fc_onay_ekle(v_okul, b.id, 'Onaya gönderildi', NULL);
    IF v_durum = 'Müdür Onayında' THEN
        PERFORM dose_private.fc_onay_ekle(v_okul, b.id, 'Uygundur', 'Hazırlayan Teknik Müdür Yardımcısı');
    END IF;
    PERFORM dose_private.log(v_okul, 'Fazla çalışma bordrosu onaya gönderildi', 'fc_bordro', b.id, b.bordro_no);
    RETURN jsonb_build_object('id', b.id, 'durum', v_durum, 'surum', b.surum + 1);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_fc_karar(p_id INTEGER, p_surum INTEGER, p_onay BOOLEAN, p_aciklama TEXT)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); b dose_private.fc_bordro%ROWTYPE; v_hesap JSONB;
    v_rol TEXT := public.dose_rol(); v_aciklama TEXT := nullif(btrim(p_aciklama), '');
    v_fis INTEGER; v_satirlar JSONB; v_vergi NUMERIC; v_tarih DATE := (now() AT TIME ZONE 'Europe/Istanbul')::DATE;
BEGIN
    SELECT * INTO b FROM dose_private.fc_bordro WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
    IF NOT FOUND OR auth.uid() IS NULL OR public.dose_yetki('fazla_calisma') <> 'y'
       OR NOT (b.durum = 'TMY Onayında' AND v_rol = 'Teknik Müdür Yardımcısı'
               OR b.durum = 'Müdür Onayında' AND v_rol = 'Okul Müdürü') THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'Bu aşamadaki bordro kararını yalnız sıradaki onay makamı verebilir.';
    END IF;
    IF p_surum IS DISTINCT FROM b.surum THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bordro değiştirildi; güncelini yükleyin.', HINT = 'surum_cakismasi';
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
        UPDATE dose_private.fc_bordro SET durum = 'Taslak', surum = surum + 1 WHERE id = b.id;
        PERFORM dose_private.fc_onay_ekle(v_okul, b.id, 'İade edildi', v_aciklama);
        PERFORM dose_private.log(v_okul, 'Fazla çalışma bordrosu iade edildi', 'fc_bordro', b.id, v_aciklama);
        RETURN jsonb_build_object('id', b.id, 'durum', 'Taslak', 'surum', b.surum + 1);
    END IF;
    IF v_rol = 'Teknik Müdür Yardımcısı' THEN
        UPDATE dose_private.fc_bordro SET durum = 'Müdür Onayında', surum = surum + 1 WHERE id = b.id;
        PERFORM dose_private.fc_onay_ekle(v_okul, b.id, 'Uygundur', v_aciklama);
        PERFORM dose_private.log(v_okul, 'Fazla çalışma bordrosu uygun görüldü', 'fc_bordro', b.id, b.bordro_no);
        RETURN jsonb_build_object('id', b.id, 'durum', 'Müdür Onayında', 'surum', b.surum + 1);
    END IF;

    PERFORM 1 FROM public.siparis WHERE okul_id = v_okul AND id = b.siparis_id FOR UPDATE;
    v_hesap := dose_private.fc_hesap(v_okul, b.id);
    IF jsonb_array_length(v_hesap->'hatalar') > 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bordro kontrolleri geçmiyor: ' || (v_hesap->'hatalar'->>0);
    END IF;
    v_vergi := (v_hesap->'toplam'->>'gelir_vergisi')::NUMERIC + (v_hesap->'toplam'->>'damga_vergisi')::NUMERIC;
    v_satirlar := jsonb_build_array(
        jsonb_build_object('hesap', '720', 'borc', (v_hesap->'toplam'->>'brut')::NUMERIC, 'alacak', 0),
        jsonb_build_object('hesap', '335', 'borc', 0, 'alacak', (v_hesap->'toplam'->>'net')::NUMERIC));
    IF v_vergi > 0 THEN
        v_satirlar := v_satirlar || jsonb_build_array(jsonb_build_object('hesap', '360', 'borc', 0, 'alacak', v_vergi));
    END IF;
    v_fis := dose_private.yevmiye_olustur(v_okul, v_tarih, format('%s fazla çalışma ücreti tahakkuku', b.bordro_no),
        'FazlaCalisma', b.id, v_satirlar);
    UPDATE dose_private.fc_bordro SET durum = 'Onaylandı', surum = surum + 1, hesap = v_hesap, yevmiye_id = v_fis
    WHERE id = b.id;
    PERFORM dose_private.fc_onay_ekle(v_okul, b.id, 'Olur', v_aciklama);
    PERFORM dose_private.log(v_okul, 'Fazla çalışma bordrosu onaylandı', 'fc_bordro', b.id, b.bordro_no, NULL,
        jsonb_build_object('yevmiye_id', v_fis, 'brut', v_hesap->'toplam'->>'brut', 'net', v_hesap->'toplam'->>'net'));
    RETURN jsonb_build_object('id', b.id, 'durum', 'Onaylandı', 'surum', b.surum + 1, 'yevmiye_id', v_fis);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_fc_iptal(p_id INTEGER, p_surum INTEGER, p_gerekce TEXT) RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); b dose_private.fc_bordro%ROWTYPE; v_rol TEXT := public.dose_rol();
    v_gerekce TEXT := nullif(btrim(p_gerekce), ''); v_satirlar JSONB; v_fis INTEGER;
BEGIN
    SELECT * INTO b FROM dose_private.fc_bordro WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
    IF NOT FOUND OR public.dose_yetki('fazla_calisma') <> 'y'
       OR NOT (b.durum = 'Taslak' AND dose_private.fc_hazirlayabilir(v_okul, b.siparis_id)
               OR b.durum = 'Onaylandı' AND v_rol = 'Okul Müdürü') THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'Taslağı hazırlayan, onaylı bordroyu yalnız Okul Müdürü iptal edebilir.';
    END IF;
    IF p_surum IS DISTINCT FROM b.surum THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bordro değiştirildi; güncelini yükleyin.', HINT = 'surum_cakismasi';
    END IF;
    IF v_gerekce IS NULL OR length(v_gerekce) > 500 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İptal gerekçesi zorunludur (en fazla 500 karakter).';
    END IF;
    IF b.durum = 'Onaylandı' THEN
        PERFORM dose_private.kasa_kilitle(v_okul, 'Banka (102)');
        IF dose_private.fc_odeme(v_okul, b.id) IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ödenmiş bordro iptal edilemez; önce ödemeyi tersleyin.';
        END IF;
        SELECT jsonb_agg(jsonb_build_object('hesap', hesap_kodu, 'borc', alacak, 'alacak', borc) ORDER BY id)
          INTO v_satirlar FROM public.yevmiye_satir WHERE okul_id = v_okul AND yevmiye_id = b.yevmiye_id;
        v_fis := dose_private.yevmiye_olustur(v_okul, (now() AT TIME ZONE 'Europe/Istanbul')::DATE,
            format('%s fazla çalışma iptali: %s', b.bordro_no, v_gerekce), 'FazlaCalisma ters kayıt', b.id, v_satirlar);
    END IF;
    UPDATE dose_private.fc_bordro SET durum = 'İptal', surum = surum + 1 WHERE id = b.id;
    PERFORM dose_private.fc_onay_ekle(v_okul, b.id, 'İptal edildi', v_gerekce);
    PERFORM dose_private.log(v_okul, 'Fazla çalışma bordrosu iptal edildi', 'fc_bordro', b.id, v_gerekce, NULL,
        jsonb_build_object('ters_yevmiye_id', v_fis));
    RETURN jsonb_build_object('id', b.id, 'durum', 'İptal', 'surum', b.surum + 1, 'yevmiye_id', v_fis);
END;
$$;

-- ------------------------------------------------------------------ banka ödemesi (md.7, md.9/b)
CREATE OR REPLACE FUNCTION public.dose_fc_ode(p_id INTEGER, p_tarih DATE, p_belge_no TEXT, p_istek UUID)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); b dose_private.fc_bordro%ROWTYPE; v_net NUMERIC;
    v_bakiye NUMERIC; v_son DATE; v_hareket INTEGER; v_fis INTEGER; v_kisit TEXT;
    v_belge TEXT := nullif(btrim(p_belge_no), ''); v_aciklama TEXT;
BEGIN
    IF auth.uid() IS NULL OR public.dose_rol() <> 'Sayman' OR public.dose_yetki('kasa') <> 'y'
       OR public.dose_yetki('fazla_calisma') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Fazla çalışma ödemesini yalnız yetkili sayman yapabilir.';
    END IF;
    IF p_tarih IS NULL OR p_tarih > (now() AT TIME ZONE 'Europe/Istanbul')::DATE OR p_istek IS NULL
       OR length(v_belge) > 100 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Geçerli ödeme tarihi ve işlem kimliği gereklidir.';
    END IF;
    SELECT * INTO b FROM dose_private.fc_bordro WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
    IF NOT FOUND OR b.durum <> 'Onaylandı' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yalnız Okul Müdürünce onaylanmış bordro ödenebilir.';
    END IF;
    PERFORM dose_private.kasa_kilitle(v_okul, 'Banka (102)');
    IF EXISTS (SELECT 1 FROM public.kasa_banka WHERE okul_id = v_okul AND istek_id = p_istek) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu ödeme daha önce kaydedildi; listeyi yenileyin.';
    END IF;
    IF dose_private.fc_odeme(v_okul, b.id) IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu bordro zaten ödendi.';
    END IF;
    IF p_tarih < (SELECT min(zaman)::DATE FROM dose_private.fc_onay WHERE bordro_id = b.id AND islem = 'Olur') THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ödeme tarihi müdür onayından önce olamaz.';
    END IF;
    SELECT max(tarih::DATE) INTO v_son FROM public.kasa_banka WHERE okul_id = v_okul AND hesap = 'Banka (102)';
    IF v_son IS NOT NULL AND p_tarih < v_son THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Son banka hareketinden daha eski tarihe kayıt yapılamaz.';
    END IF;
    v_net := (b.hesap->'toplam'->>'net')::NUMERIC;
    v_bakiye := dose_private.kasa_bakiye(v_okul, 'Banka (102)');
    IF v_net > v_bakiye THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('Banka bakiyesi yetersiz (%s TL).', v_bakiye);
    END IF;
    v_aciklama := format('%s fazla çalışma ücreti ödemesi (%s/%s, %s kişi)', b.bordro_no, lpad(b.ay::TEXT, 2, '0'), b.yil,
        (SELECT count(*) FROM jsonb_array_elements(b.hesap->'kisiler') k WHERE (k->>'net')::NUMERIC > 0));
    BEGIN
        INSERT INTO public.kasa_banka (okul_id, tarih, hesap, yon, tur, tutar, hasilat_tutari, siparis_id, belge_no,
            aciklama, kaynak, karsi_hesap, istek_id, olusturan, fc_bordro_id)
        VALUES (v_okul, p_tarih::TEXT, 'Banka (102)', 'Çıkış', 'Ödeme', v_net, 0, b.siparis_id, v_belge,
            v_aciklama, 'KasaBanka', '335', p_istek, auth.uid(), b.id) RETURNING id INTO v_hareket;
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
    PERFORM dose_private.fc_onay_ekle(v_okul, b.id, 'Ödendi', v_belge);
    PERFORM dose_private.log(v_okul, 'Fazla çalışma ücreti ödendi', 'kasa_banka', v_hareket, v_aciklama, NULL,
        jsonb_build_object('bordro_id', b.id, 'tutar', v_net::TEXT, 'yevmiye_id', v_fis));
    RETURN jsonb_build_object('id', v_hareket, 'yevmiye_id', v_fis, 'tutar', v_net::TEXT,
        'bakiye', (v_bakiye - v_net)::TEXT);
END;
$$;

REVOKE ALL ON FUNCTION dose_private.fc_siparis_uygun(INTEGER, INTEGER), dose_private.fc_idari(TEXT),
    dose_private.fc_gun_siniri(dose_private.fc_bordro, INTEGER), dose_private.fc_odeme(INTEGER, INTEGER),
    dose_private.fc_onay_ekle(INTEGER, INTEGER, TEXT, TEXT), dose_private.fc_hazirlayabilir(INTEGER, INTEGER),
    dose_private.fc_hesap(INTEGER, INTEGER), dose_private.fc_kisi_silme_kontrol() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.dose_fc_veri(), public.dose_fc_kaydet(INTEGER, INTEGER, JSONB, JSONB, UUID),
    public.dose_fc_gonder(INTEGER, INTEGER), public.dose_fc_karar(INTEGER, INTEGER, BOOLEAN, TEXT),
    public.dose_fc_iptal(INTEGER, INTEGER, TEXT), public.dose_fc_ode(INTEGER, DATE, TEXT, UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_fc_veri(), public.dose_fc_kaydet(INTEGER, INTEGER, JSONB, JSONB, UUID),
    public.dose_fc_gonder(INTEGER, INTEGER), public.dose_fc_karar(INTEGER, INTEGER, BOOLEAN, TEXT),
    public.dose_fc_iptal(INTEGER, INTEGER, TEXT), public.dose_fc_ode(INTEGER, DATE, TEXT, UUID) TO authenticated;
