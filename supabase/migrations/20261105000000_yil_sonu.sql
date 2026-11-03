-- Yıl sonu kâr dağıtımı ve Ürün Teşvik Primi (3423 s.K. md.1; Döner Sermaye Yönergesi md.4-6; DHGM 15.01.2026 m.16;
-- 2828 s.K. md.18/1-k). Dönem kârı yevmiyeden çıkarılır; SHÇEK payı (%1, Ocak sonu), ÜTP (kârın en çok 1/3'ü, vadeli
-- faizin 1/3'ü düşülerek), sermaye payı (tahsis edilen sermaye tamamlanana kadar kârın 1/3'ü) ve Merkez Saymanlık payı
-- (Şubat sonu) hesaplanır. ÜTP; idari %25 (harcama %8, gerçekleştirme %5, şefler %5, sayman %5, diğer idari %2), takdir
-- %5 ve bölüm %70 olarak kuruşu kuruşuna dağıtılır; kişi başı yıllık tavanı aşan kısım Merkez payına eklenir.
-- Sayman hazırlar, Okul Müdürü onaylar; onayda SHÇEK tahakkuku, gelir-gider kapanışı ve kâr dağıtım fişleri kesilir.

INSERT INTO dose_private.sayfa_yetki (sayfa, baslik, kodlar)
VALUES ('yil_sonu', 'Yıl Sonu Kâr Dağıtımı ve ÜTP', 'gygy---g')
ON CONFLICT (sayfa) DO UPDATE SET baslik = EXCLUDED.baslik, kodlar = EXCLUDED.kodlar;

CREATE TABLE dose_private.ys_donem (
    id SERIAL PRIMARY KEY,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    belge_no TEXT NOT NULL,
    yil INTEGER NOT NULL CHECK (yil BETWEEN 2000 AND 2100),
    utp_orani NUMERIC NOT NULL CHECK (utp_orani >= 0 AND utp_orani <= 0.3334),
    tahsis_sermaye NUMERIC NOT NULL DEFAULT 0 CHECK (tahsis_sermaye >= 0 AND tahsis_sermaye = round(tahsis_sermaye, 2)),
    odenmis_sermaye NUMERIC NOT NULL DEFAULT 0 CHECK (odenmis_sermaye >= 0 AND odenmis_sermaye = round(odenmis_sermaye, 2)),
    shcek_orani NUMERIC NOT NULL DEFAULT 0.01 CHECK (shcek_orani >= 0 AND shcek_orani <= 0.1),
    dv_orani NUMERIC NOT NULL DEFAULT 0.00759 CHECK (dv_orani >= 0 AND dv_orani <= 0.1),
    yillik_tavan NUMERIC NOT NULL CHECK (yillik_tavan > 0 AND yillik_tavan = round(yillik_tavan, 2)),
    yuz_yuze BOOLEAN NOT NULL DEFAULT true,
    aciklama TEXT CHECK (length(aciklama) <= 1000),
    durum TEXT NOT NULL DEFAULT 'Taslak' CHECK (durum IN ('Taslak', 'Müdür Onayında', 'Onaylandı', 'İptal')),
    surum INTEGER NOT NULL DEFAULT 1,
    hesap JSONB,
    shcek_yevmiye_id INTEGER,
    kapanis_yevmiye_id INTEGER,
    dagitim_yevmiye_id INTEGER,
    ters_yevmiye_idler INTEGER[],
    iptal_gerekcesi TEXT CHECK (length(iptal_gerekcesi) <= 500),
    olusturan UUID NOT NULL REFERENCES auth.users(id),
    olusturma TEXT NOT NULL DEFAULT dose_private.zaman(),
    istek_id UUID NOT NULL,
    CONSTRAINT ys_istek_tek UNIQUE (okul_id, istek_id),
    CONSTRAINT ys_no_tek UNIQUE (okul_id, belge_no)
);
CREATE UNIQUE INDEX ys_donem_tek ON dose_private.ys_donem(okul_id, yil) WHERE durum <> 'İptal';

CREATE TABLE dose_private.ys_kisi (
    id SERIAL PRIMARY KEY,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    donem_id INTEGER NOT NULL REFERENCES dose_private.ys_donem(id) ON DELETE CASCADE,
    sira INTEGER NOT NULL,
    personel_id INTEGER NOT NULL,
    gorev TEXT NOT NULL,
    unvan_grubu INTEGER NOT NULL CHECK (unvan_grubu BETWEEN 1 AND 5),
    bolum_id INTEGER,
    fiili_gun NUMERIC NOT NULL DEFAULT 0 CHECK (fiili_gun BETWEEN 0 AND 366),
    fc_saat NUMERIC NOT NULL DEFAULT 0 CHECK (fc_saat >= 0),
    katki_orani NUMERIC NOT NULL DEFAULT 0 CHECK (katki_orani >= 0),
    takdir_orani NUMERIC NOT NULL DEFAULT 0 CHECK (takdir_orani >= 0),
    haric BOOLEAN NOT NULL DEFAULT false,
    haric_neden TEXT CHECK (length(haric_neden) <= 300),
    onceki_utp NUMERIC NOT NULL DEFAULT 0 CHECK (onceki_utp >= 0 AND onceki_utp = round(onceki_utp, 2)),
    gv_orani NUMERIC NOT NULL CHECK (gv_orani BETWEEN 0 AND 1),
    UNIQUE (donem_id, personel_id)
);
CREATE INDEX ys_kisi_personel ON dose_private.ys_kisi(okul_id, personel_id);

CREATE TABLE dose_private.ys_onay (
    id SERIAL PRIMARY KEY,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul(id),
    donem_id INTEGER NOT NULL REFERENCES dose_private.ys_donem(id),
    islem TEXT NOT NULL,
    rol TEXT NOT NULL,
    ad_soyad TEXT NOT NULL,
    aciklama TEXT,
    kullanici UUID NOT NULL REFERENCES auth.users(id),
    zaman TEXT NOT NULL DEFAULT dose_private.zaman()
);
CREATE INDEX ys_onay_donem ON dose_private.ys_onay(donem_id);

ALTER TABLE public.kasa_banka ADD COLUMN ys_donem_id INTEGER REFERENCES dose_private.ys_donem(id);
ALTER TABLE public.kasa_banka ADD COLUMN ys_kalem TEXT CHECK (ys_kalem IN ('SHÇEK', 'Merkez payı', 'ÜTP'));
CREATE INDEX kasa_ys_indeks ON public.kasa_banka(okul_id, ys_donem_id) WHERE ys_donem_id IS NOT NULL;

ALTER TABLE dose_private.ys_donem ENABLE ROW LEVEL SECURITY;
ALTER TABLE dose_private.ys_kisi ENABLE ROW LEVEL SECURITY;
ALTER TABLE dose_private.ys_onay ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON dose_private.ys_donem, dose_private.ys_kisi, dose_private.ys_onay FROM PUBLIC, anon, authenticated;

CREATE TRIGGER dose_ys_onay_degismez BEFORE UPDATE OR DELETE ON dose_private.ys_onay
    FOR EACH ROW EXECUTE FUNCTION dose_private.pb_onay_degismez();

CREATE OR REPLACE FUNCTION dose_private.ys_kisi_silme_kontrol() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM dose_private.ys_kisi k WHERE k.okul_id = OLD.okul_id AND k.personel_id = OLD.id) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = 'Bu personel ÜTP dağıtımında kullanıldığı için silinemez; pasif yapınız.';
    END IF;
    RETURN OLD;
END;
$$;
CREATE TRIGGER dose_ys_personel_silme BEFORE DELETE ON public.personel
    FOR EACH ROW EXECUTE FUNCTION dose_private.ys_kisi_silme_kontrol();

-- ------------------------------------------------------------------ yardımcılar
-- Havuzu ağırlıklara göre en büyük kalan yöntemiyle kuruşu kuruşuna dağıtır. Ağırlıkların hepsi sıfırsa dağıtmaz.
CREATE OR REPLACE FUNCTION dose_private.ys_dagit(p_havuz NUMERIC, p_agirlik JSONB) RETURNS JSONB
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
    WITH a AS (
        SELECT key, greatest(coalesce((value #>> '{}')::NUMERIC, 0), 0) AS w FROM jsonb_each(coalesce(p_agirlik, '{}'::JSONB))
    ), t AS (
        SELECT coalesce(sum(w), 0) AS top, round(greatest(coalesce(p_havuz, 0), 0) * 100) AS kurus FROM a
    ), b AS (
        SELECT a.key, a.w,
               CASE WHEN t.top > 0 THEN floor(t.kurus * a.w / t.top) ELSE 0 END AS taban,
               CASE WHEN t.top > 0 THEN t.kurus * a.w / t.top - floor(t.kurus * a.w / t.top) ELSE 0 END AS kesir
        FROM a, t
    ), c AS (
        SELECT b.*, row_number() OVER (ORDER BY b.kesir DESC, b.w DESC, b.key) AS rn,
               (SELECT t.kurus FROM t) - sum(b.taban) OVER () AS artan, (SELECT t.top FROM t) AS top
        FROM b
    )
    SELECT coalesce(jsonb_object_agg(c.key,
        round((c.taban + CASE WHEN c.top > 0 AND c.w > 0 AND c.rn <= c.artan THEN 1 ELSE 0 END) / 100, 2)), '{}'::JSONB)
    FROM c
$$;

CREATE OR REPLACE FUNCTION dose_private.ys_topla(p_a JSONB, p_b JSONB) RETURNS JSONB
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
    SELECT coalesce(jsonb_object_agg(key, toplam), '{}'::JSONB) FROM (
        SELECT key, sum((value #>> '{}')::NUMERIC) AS toplam
        FROM (SELECT * FROM jsonb_each(coalesce(p_a, '{}'::JSONB))
              UNION ALL SELECT * FROM jsonb_each(coalesce(p_b, '{}'::JSONB))) u
        GROUP BY key) s
$$;

-- Yılın gelir (6xx), gider (7xx), brüt hasılat (600/610) ve faiz geliri (642) tutarları; yıl sonu fişleri hariç.
CREATE OR REPLACE FUNCTION dose_private.ys_tutarlar(p_okul INTEGER, p_yil INTEGER) RETURNS JSONB
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT jsonb_build_object(
        'gelir', coalesce(sum(s.alacak - s.borc) FILTER (WHERE s.hesap_kodu LIKE '6%'), 0),
        'gider', coalesce(sum(s.borc - s.alacak) FILTER (WHERE s.hesap_kodu LIKE '7%'), 0),
        'hasilat', coalesce(sum(s.alacak - s.borc) FILTER (WHERE s.hesap_kodu ~ '^(600|610)(\.|$)'), 0),
        'faiz', coalesce(sum(s.alacak - s.borc) FILTER (WHERE s.hesap_kodu ~ '^642(\.|$)'), 0))
    FROM public.yevmiye_satir s
    JOIN public.yevmiye y ON y.okul_id = s.okul_id AND y.id = s.yevmiye_id
    WHERE s.okul_id = p_okul AND y.tarih::DATE BETWEEN make_date(p_yil, 1, 1) AND make_date(p_yil, 12, 31)
      AND coalesce(y.kaynak, '') NOT LIKE 'YilSonu%'
$$;

-- Bölümlerin yıl içindeki satış (KDV hariç) gelirleri; ÜTP bölüm ve şef paylarının dağıtım ölçütü (md.5/4, md.5/7).
CREATE OR REPLACE FUNCTION dose_private.ys_bolum_gelir(p_okul INTEGER, p_yil INTEGER) RETURNS JSONB
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT coalesce(jsonb_object_agg(x.bolum_id::TEXT, x.gelir), '{}'::JSONB) FROM (
        SELECT s.bolum_id, sum(f.matrah::NUMERIC) AS gelir
        FROM public.fatura f JOIN public.siparis s ON s.okul_id = f.okul_id AND s.id = f.siparis_id
        WHERE f.okul_id = p_okul AND f.tur = 'Satış' AND f.iptal = 0 AND s.bolum_id IS NOT NULL
          AND f.tarih::DATE BETWEEN make_date(p_yil, 1, 1) AND make_date(p_yil, 12, 31)
        GROUP BY s.bolum_id) x
$$;

CREATE OR REPLACE FUNCTION dose_private.ys_odeme(p_okul INTEGER, p_donem INTEGER, p_kalem TEXT) RETURNS JSONB
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT jsonb_build_object('id', k.id, 'tarih', k.tarih, 'tutar', k.tutar::TEXT, 'belge_no', k.belge_no)
    FROM public.kasa_banka k
    WHERE k.okul_id = p_okul AND k.ys_donem_id = p_donem AND k.ys_kalem = p_kalem AND k.ters_hareket_id IS NULL
      AND NOT EXISTS (SELECT 1 FROM public.kasa_banka t WHERE t.okul_id = k.okul_id AND t.ters_hareket_id = k.id)
    ORDER BY k.id DESC LIMIT 1
$$;

CREATE OR REPLACE FUNCTION dose_private.ys_onay_ekle(p_okul INTEGER, p_donem INTEGER, p_islem TEXT, p_aciklama TEXT)
RETURNS VOID LANGUAGE sql VOLATILE SET search_path = '' AS $$
    INSERT INTO dose_private.ys_onay (okul_id, donem_id, islem, rol, ad_soyad, aciklama, kullanici)
    SELECT p_okul, p_donem, p_islem, u.rol, u.ad_soyad, p_aciklama, auth.uid()
    FROM dose_private.uyelik u WHERE u.auth_user_id = auth.uid()
$$;

CREATE OR REPLACE FUNCTION dose_private.ys_gorev_gecerli(p_gorev TEXT) RETURNS BOOLEAN
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
    SELECT coalesce(p_gorev, '') IN ('Harcama Yetkilisi (Okul Müdürü)', 'Gerçekleştirme Görevlisi (Teknik Md. Yrd.)',
        'Bölüm/Alan Şefi', 'Atölye/Laboratuvar Şefi', 'Sayman', 'Diğer İdari Personel', 'Öğretmen',
        'Mühendis/Uzman/Tekniker', 'Usta/Teknisyen/Ambar Memuru', 'Diğer Personel')
$$;

-- Kâr bölüşümü ve kişi bazında ÜTP. Tüm havuzlar kuruşa yuvarlanır ve ys_dagit ile tam dağıtılır.
CREATE OR REPLACE FUNCTION dose_private.ys_hesap(p_okul INTEGER, p_donem INTEGER) RETURNS JSONB
LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE
    d dose_private.ys_donem%ROWTYPE; t JSONB; v_gelirler JSONB;
    v_hatalar TEXT[] := ARRAY[]::TEXT[]; v_uyarilar TEXT[] := ARRAY[]::TEXT[];
    v_kar_oncesi NUMERIC; v_shcek NUMERIC; v_kar NUMERIC; v_faiz NUMERIC; v_oran NUMERIC := 0;
    v_utp_azami NUMERIC := 0; v_esas NUMERIC := 0; v_ucte_bir NUMERIC := 0; v_eksik NUMERIC := 0;
    v_sermaye NUMERIC := 0; v_merkez NUMERIC := 0; v_dagitilan NUMERIC := 0;
    v_idari_h NUMERIC := 0; v_takdir_h NUMERIC := 0; v_bolum_h NUMERIC := 0; v_havuz NUMERIC;
    v_idari JSONB := '{}'::JSONB; v_takdir JSONB := '{}'::JSONB; v_bolum JSONB := '{}'::JSONB;
    v_pay JSONB; v_bpay JSONB; v_w JSONB; v_g RECORD; v_b RECORD; v_yontem TEXT; v_bolum_ad TEXT;
    v_kisiler JSONB; v_toplam JSONB; v_satir RECORD; v_idari_gorevler TEXT[]; v_sefler TEXT[]; v_komisyon TEXT[];
    v_bolumler JSONB;
BEGIN
    SELECT * INTO d FROM dose_private.ys_donem WHERE okul_id = p_okul AND id = p_donem;
    IF NOT FOUND THEN RETURN NULL; END IF;
    v_sefler := ARRAY['Bölüm/Alan Şefi', 'Atölye/Laboratuvar Şefi'];
    v_idari_gorevler := ARRAY['Harcama Yetkilisi (Okul Müdürü)', 'Gerçekleştirme Görevlisi (Teknik Md. Yrd.)',
        'Bölüm/Alan Şefi', 'Atölye/Laboratuvar Şefi', 'Sayman', 'Diğer İdari Personel'];
    v_komisyon := ARRAY['Harcama Yetkilisi (Okul Müdürü)', 'Gerçekleştirme Görevlisi (Teknik Md. Yrd.)',
        'Bölüm/Alan Şefi', 'Atölye/Laboratuvar Şefi'];
    t := dose_private.ys_tutarlar(p_okul, d.yil);
    v_gelirler := dose_private.ys_bolum_gelir(p_okul, d.yil);
    v_kar_oncesi := (t->>'gelir')::NUMERIC - (t->>'gider')::NUMERIC;
    v_shcek := round(greatest((t->>'hasilat')::NUMERIC, 0) * d.shcek_orani, 2);
    v_kar := v_kar_oncesi - v_shcek;
    v_faiz := greatest((t->>'faiz')::NUMERIC, 0);

    IF make_date(d.yil, 12, 31) >= (now() AT TIME ZONE 'Europe/Istanbul')::DATE THEN
        v_hatalar := array_append(v_hatalar, 'Yıl tamamlanmadan kâr dağıtımı onaya gönderilemez.'::TEXT);
    END IF;
    IF v_kar <= 0 THEN
        v_uyarilar := array_append(v_uyarilar,
            'Dönem kârı bulunmadığından ÜTP, sermaye payı ve Merkez Saymanlık payı dağıtılmaz.'::TEXT);
    ELSE
        IF d.utp_orani >= 0.3333 THEN v_oran := 1::NUMERIC / 3; ELSE v_oran := d.utp_orani; END IF;
        v_utp_azami := round(v_kar * v_oran, 2);
        v_esas := greatest(0, round(v_utp_azami - v_faiz / 3, 2));
        IF v_faiz > 0 THEN
            v_uyarilar := v_uyarilar || format('Vadeli hesap faiz gelirinin 1/3''ü (%s TL) ÜTP''den düşüldü (DHGM 15.01.2026 m.16).',
                round(v_faiz / 3, 2));
        END IF;
        v_ucte_bir := round(v_kar / 3, 2);
        v_eksik := greatest(0, d.tahsis_sermaye - d.odenmis_sermaye);
        v_sermaye := least(v_ucte_bir, v_eksik);
        IF v_eksik <= 0 THEN
            v_uyarilar := array_append(v_uyarilar,
                'Tahsis edilen sermaye tamamlanmış: sermaye payı ayrılmaz, kalan kâr Merkez Saymanlığa aktarılır.'::TEXT);
        ELSIF v_sermaye < v_ucte_bir THEN
            v_uyarilar := array_append(v_uyarilar,
                'Sermaye payının eksik sermayeyi aşan kısmı Merkez Saymanlık payına eklendi.'::TEXT);
        END IF;
    END IF;

    IF v_esas > 0 AND NOT EXISTS (SELECT 1 FROM dose_private.ys_kisi k WHERE k.donem_id = d.id AND NOT k.haric) THEN
        v_uyarilar := array_append(v_uyarilar, 'ÜTP dağıtım listesinde personel yok; ÜTP Merkez payına eklenir.'::TEXT);
    ELSIF v_esas > 0 THEN
        IF d.yuz_yuze THEN
            v_idari_h := round(v_esas * 0.25, 2);
            v_takdir_h := round(v_esas * 0.05, 2);
            v_bolum_h := v_esas - v_idari_h - v_takdir_h;
            FOR v_g IN SELECT * FROM (VALUES ('Harcama Yetkilisi (Okul Müdürü)', 0.08::NUMERIC),
                ('Gerçekleştirme Görevlisi (Teknik Md. Yrd.)', 0.05), ('Sayman', 0.05), ('Diğer İdari Personel', 0.02)) x(gorev, oran)
            LOOP
                v_havuz := round(v_esas * v_g.oran, 2);
                SELECT jsonb_object_agg(k.id::TEXT, CASE WHEN k.fiili_gun > 0 THEN k.fiili_gun ELSE 1 END) INTO v_w
                FROM dose_private.ys_kisi k WHERE k.donem_id = d.id AND NOT k.haric AND k.gorev = v_g.gorev;
                IF v_w IS NULL THEN
                    v_uyarilar := v_uyarilar || format('"%s" görevinde personel yok; %s TL Merkez payına eklendi.', v_g.gorev, v_havuz);
                    CONTINUE;
                END IF;
                v_idari := dose_private.ys_topla(v_idari, dose_private.ys_dagit(v_havuz, v_w));
            END LOOP;

            -- Şefler: bölümlerin gelire katkısına göre, bölüm içinde fiilen çalışılan güne göre (md.5/4).
            v_havuz := round(v_esas * 0.05, 2);
            SELECT jsonb_object_agg(x.b, coalesce((v_gelirler->>x.b)::NUMERIC, 0)) INTO v_w
            FROM (SELECT DISTINCT coalesce(k.bolum_id, 0)::TEXT AS b FROM dose_private.ys_kisi k
                  WHERE k.donem_id = d.id AND NOT k.haric AND k.gorev = ANY (v_sefler)) x;
            IF v_w IS NULL THEN
                v_uyarilar := v_uyarilar || format('Bölüm/alan şefi yok; şef payı %s TL Merkez payına eklendi.', v_havuz);
            ELSE
                v_bpay := dose_private.ys_dagit(v_havuz, v_w);
                IF NOT EXISTS (SELECT 1 FROM jsonb_each(v_bpay) WHERE (value #>> '{}')::NUMERIC > 0) THEN
                    v_bpay := dose_private.ys_dagit(v_havuz, (SELECT jsonb_object_agg(key, 1) FROM jsonb_each(v_w)));
                END IF;
                FOR v_b IN SELECT key, (value #>> '{}')::NUMERIC AS tutar FROM jsonb_each(v_bpay) LOOP
                    SELECT jsonb_object_agg(k.id::TEXT, CASE WHEN k.fiili_gun > 0 THEN k.fiili_gun ELSE 1 END) INTO v_w
                    FROM dose_private.ys_kisi k WHERE k.donem_id = d.id AND NOT k.haric AND k.gorev = ANY (v_sefler)
                      AND coalesce(k.bolum_id, 0)::TEXT = v_b.key;
                    v_idari := dose_private.ys_topla(v_idari, dose_private.ys_dagit(v_b.tutar, v_w));
                END LOOP;
            END IF;

            -- Bölüm/alan personeli: bölüm gelir oranı; bölüm içinde bölümün ÜTP yöntemine göre (md.5/7).
            SELECT jsonb_object_agg(key, value) INTO v_w FROM jsonb_each(v_gelirler) WHERE (value #>> '{}')::NUMERIC > 0;
            IF v_w IS NULL THEN
                v_uyarilar := v_uyarilar || format('Bölüm satış geliri bulunamadı; bölüm payı %s TL Merkez payına eklendi.', v_bolum_h);
            ELSE
                v_bpay := dose_private.ys_dagit(v_bolum_h, v_w);
                FOR v_b IN SELECT key, (value #>> '{}')::NUMERIC AS tutar FROM jsonb_each(v_bpay) ORDER BY key LOOP
                    SELECT coalesce(b.utp_yontemi, ''), b.ad INTO v_yontem, v_bolum_ad
                    FROM public.bolum b WHERE b.okul_id = p_okul AND b.id = v_b.key::INTEGER;
                    v_yontem := coalesce(v_yontem, '');
                    SELECT jsonb_object_agg(k.id::TEXT, CASE WHEN v_yontem LIKE 'Fiilen%' THEN k.fiili_gun
                        WHEN v_yontem LIKE 'Katkı%' THEN k.katki_orani ELSE k.fc_saat END) INTO v_w
                    FROM dose_private.ys_kisi k WHERE k.donem_id = d.id AND NOT k.haric AND k.bolum_id = v_b.key::INTEGER
                      AND (k.gorev <> ALL (v_idari_gorevler) OR k.gorev = ANY (v_sefler));
                    IF v_w IS NULL THEN
                        v_uyarilar := v_uyarilar || format('%s bölümünün payı (%s TL): bölümde ÜTP''ye esas personel yok.',
                            coalesce(v_bolum_ad, v_b.key), v_b.tutar);
                        CONTINUE;
                    END IF;
                    v_pay := dose_private.ys_dagit(v_b.tutar, v_w);
                    IF v_b.tutar > 0 AND NOT EXISTS (SELECT 1 FROM jsonb_each(v_pay) WHERE (value #>> '{}')::NUMERIC > 0) THEN
                        v_uyarilar := v_uyarilar || format('%s bölümünde dağıtım ölçütü (%s) girilmemiş.',
                            coalesce(v_bolum_ad, v_b.key), CASE WHEN v_yontem LIKE 'Fiilen%' THEN 'fiilen çalışılan gün'
                                WHEN v_yontem LIKE 'Katkı%' THEN 'katkı oranı' ELSE 'fazla çalışma saati' END);
                    END IF;
                    v_bolum := dose_private.ys_topla(v_bolum, v_pay);
                END LOOP;
            END IF;
        ELSE
            -- Yüz yüze eğitim yapılmayan dönem (md.5/8): %5 takdir, %95 unvan puanı x fiilen çalışılan gün.
            v_takdir_h := round(v_esas * 0.05, 2);
            v_bolum_h := v_esas - v_takdir_h;
            SELECT jsonb_object_agg(k.id::TEXT, (CASE k.unvan_grubu WHEN 1 THEN 50 WHEN 2 THEN 45 WHEN 3 THEN 40
                WHEN 4 THEN 35 ELSE 30 END) * k.fiili_gun) INTO v_w
            FROM dose_private.ys_kisi k WHERE k.donem_id = d.id AND NOT k.haric;
            v_bolum := dose_private.ys_dagit(v_bolum_h, v_w);
        END IF;

        -- Çalışmayı teşvik ve takdir payı: komisyon üyeleri (müdür, müdür yrd., şefler) hariç (md.5/6).
        SELECT jsonb_object_agg(k.id::TEXT, k.takdir_orani) INTO v_w
        FROM dose_private.ys_kisi k WHERE k.donem_id = d.id AND NOT k.haric AND k.takdir_orani > 0
          AND k.gorev <> ALL (v_komisyon);
        IF v_w IS NULL THEN
            IF v_takdir_h > 0 THEN
                v_uyarilar := v_uyarilar || format('Takdir payı için komisyonca puan verilmemiş; %s TL Merkez payına eklendi.', v_takdir_h);
            END IF;
        ELSE
            v_takdir := dose_private.ys_dagit(v_takdir_h, v_w);
        END IF;
    END IF;

    WITH k AS (
        SELECT k.*, p.ad_soyad, p.tckn, p.iban, p.aktif, p.kadro_unvani, p.id IS NULL AS yok, b.ad AS bolum,
               coalesce((v_idari->>k.id::TEXT)::NUMERIC, 0) AS idari,
               coalesce((v_takdir->>k.id::TEXT)::NUMERIC, 0) AS takdir,
               coalesce((v_bolum->>k.id::TEXT)::NUMERIC, 0) AS bolum_pay
        FROM dose_private.ys_kisi k
        LEFT JOIN public.personel p ON p.okul_id = p_okul AND p.id = k.personel_id
        LEFT JOIN public.bolum b ON b.okul_id = p_okul AND b.id = k.bolum_id
        WHERE k.donem_id = d.id
    ), h AS (
        SELECT k.*, k.idari + k.takdir + k.bolum_pay AS hesaplanan, greatest(d.yillik_tavan - k.onceki_utp, 0) AS kalan FROM k
    ), o AS (
        SELECT h.*, round(least(h.hesaplanan, h.kalan), 2) AS odenecek FROM h
    ), v AS (
        SELECT o.*, round(o.odenecek * o.gv_orani, 2) AS gv, round(o.odenecek * d.dv_orani, 2) AS dv FROM o
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'id', v.id, 'sira', v.sira, 'personel_id', v.personel_id, 'ad_soyad', v.ad_soyad, 'tckn', v.tckn,
               'iban', v.iban, 'kadro_unvani', v.kadro_unvani, 'gorev', v.gorev, 'unvan_grubu', v.unvan_grubu,
               'bolum_id', v.bolum_id, 'bolum', v.bolum, 'fiili_gun', v.fiili_gun::TEXT, 'fc_saat', v.fc_saat::TEXT,
               'katki_orani', v.katki_orani::TEXT, 'takdir_orani', v.takdir_orani::TEXT, 'haric', v.haric,
               'haric_neden', v.haric_neden, 'onceki_utp', v.onceki_utp::TEXT, 'gv_orani', v.gv_orani::TEXT,
               'idari', v.idari::TEXT, 'takdir', v.takdir::TEXT, 'bolum_pay', v.bolum_pay::TEXT,
               'hesaplanan', v.hesaplanan::TEXT, 'tavan_asimi', (v.hesaplanan - v.odenecek)::TEXT,
               'brut', v.odenecek::TEXT, 'gelir_vergisi', v.gv::TEXT, 'damga_vergisi', v.dv::TEXT,
               'net', (v.odenecek - v.gv - v.dv)::TEXT, 'yok', v.yok, 'aktif', v.aktif) ORDER BY v.sira), '[]'::JSONB),
           jsonb_build_object('hesaplanan', coalesce(sum(v.hesaplanan), 0)::TEXT,
               'tavan_asimi', coalesce(sum(v.hesaplanan - v.odenecek), 0)::TEXT,
               'brut', coalesce(sum(v.odenecek), 0)::TEXT, 'gelir_vergisi', coalesce(sum(v.gv), 0)::TEXT,
               'damga_vergisi', coalesce(sum(v.dv), 0)::TEXT, 'net', coalesce(sum(v.odenecek - v.gv - v.dv), 0)::TEXT),
           coalesce(sum(v.odenecek), 0)
      INTO v_kisiler, v_toplam, v_dagitilan
    FROM v;

    FOR v_satir IN SELECT value AS k FROM jsonb_array_elements(v_kisiler) LOOP
        IF (v_satir.k->>'yok')::BOOLEAN THEN
            v_hatalar := v_hatalar || format('%s. satırdaki personel kaydı bulunamadı.', v_satir.k->>'sira');
            CONTINUE;
        END IF;
        IF (v_satir.k->>'aktif')::INTEGER IS DISTINCT FROM 1 THEN
            v_uyarilar := v_uyarilar || format('%s kaydı pasif; yıl içinde fiilen çalıştığını kontrol ediniz.', v_satir.k->>'ad_soyad');
        END IF;
        IF (v_satir.k->>'brut')::NUMERIC > 0 AND nullif(btrim(v_satir.k->>'iban'), '') IS NULL THEN
            v_hatalar := v_hatalar || format('%s için IBAN kayıtlı değil; ÜTP bankadan ödenemez.', v_satir.k->>'ad_soyad');
        END IF;
        IF (v_satir.k->>'tavan_asimi')::NUMERIC > 0 THEN
            v_uyarilar := v_uyarilar || format('%s: yıllık tavanı aşan %s TL ödenmez, Merkez payına eklendi (md.4/1).',
                v_satir.k->>'ad_soyad', v_satir.k->>'tavan_asimi');
        END IF;
    END LOOP;

    IF v_kar > 0 THEN
        v_merkez := v_kar - v_dagitilan - v_sermaye;
    END IF;

    SELECT coalesce(jsonb_agg(jsonb_build_object('bolum_id', b.id, 'ad', b.ad,
               'yontem', coalesce(b.utp_yontemi, 'Fazla çalışma saati ile orantılı (md.5/7-a)'),
               'gelir', coalesce((v_gelirler->>b.id::TEXT)::NUMERIC, 0)::TEXT) ORDER BY b.ad, b.id), '[]'::JSONB)
      INTO v_bolumler FROM public.bolum b WHERE b.okul_id = p_okul;

    RETURN jsonb_build_object(
        'yil', d.yil,
        'tutarlar', jsonb_build_object('gelir', (t->>'gelir')::NUMERIC::TEXT, 'gider', (t->>'gider')::NUMERIC::TEXT,
            'hasilat', (t->>'hasilat')::NUMERIC::TEXT, 'faiz', (t->>'faiz')::NUMERIC::TEXT),
        'kar_oncesi', v_kar_oncesi::TEXT, 'shcek', v_shcek::TEXT, 'donem_kari', v_kar::TEXT,
        'utp_orani', round(v_oran, 6)::TEXT, 'utp_azami', v_utp_azami::TEXT,
        'faiz_kesintisi', CASE WHEN v_kar > 0 THEN round(v_faiz / 3, 2) ELSE 0 END::TEXT,
        'dagitima_esas', v_esas::TEXT,
        'havuzlar', jsonb_build_object('idari', v_idari_h::TEXT, 'takdir', v_takdir_h::TEXT, 'bolum', v_bolum_h::TEXT),
        'dagitilan_utp', v_dagitilan::TEXT, 'dagitilamayan_utp', (v_utp_azami - v_dagitilan)::TEXT,
        'sermaye_payi', round(v_sermaye, 2)::TEXT, 'merkez_payi', round(v_merkez, 2)::TEXT,
        'kisiler', v_kisiler, 'toplam', v_toplam, 'bolumler', v_bolumler,
        'son_tarihler', jsonb_build_object('shcek', make_date(d.yil + 1, 1, 31),
            'merkez', (make_date(d.yil + 1, 3, 1) - 1), 'mebbis', make_date(d.yil + 1, 3, 31)),
        'hatalar', to_jsonb(v_hatalar), 'uyarilar', to_jsonb(v_uyarilar));
END;
$$;

-- ------------------------------------------------------------------ ekran verisi
CREATE OR REPLACE FUNCTION public.dose_ys_veri(p_yil INTEGER DEFAULT NULL) RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); v_bugun DATE := (now() AT TIME ZONE 'Europe/Istanbul')::DATE;
    v_yil INTEGER; d dose_private.ys_donem%ROWTYPE; v_kayit JSONB; t JSONB; v_onhesap JSONB;
BEGIN
    IF v_okul IS NULL OR public.dose_yetki('yil_sonu') = '' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Yıl sonu kâr dağıtımı ekranına erişim yetkiniz yok.';
    END IF;
    v_yil := coalesce(p_yil, extract(year FROM v_bugun)::INTEGER - 1);
    IF v_yil < 2000 OR v_yil > extract(year FROM v_bugun) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Geçerli bir yıl seçiniz.';
    END IF;
    SELECT * INTO d FROM dose_private.ys_donem WHERE okul_id = v_okul AND yil = v_yil AND durum <> 'İptal';
    IF d.id IS NOT NULL THEN
        v_kayit := jsonb_build_object(
            'id', d.id, 'belge_no', d.belge_no, 'yil', d.yil, 'utp_orani', d.utp_orani::TEXT,
            'tahsis_sermaye', d.tahsis_sermaye::TEXT, 'odenmis_sermaye', d.odenmis_sermaye::TEXT,
            'shcek_orani', d.shcek_orani::TEXT, 'dv_orani', d.dv_orani::TEXT, 'yillik_tavan', d.yillik_tavan::TEXT,
            'yuz_yuze', d.yuz_yuze, 'aciklama', d.aciklama, 'durum', d.durum, 'surum', d.surum,
            'olusturma', d.olusturma, 'shcek_yevmiye_id', d.shcek_yevmiye_id,
            'kapanis_yevmiye_id', d.kapanis_yevmiye_id, 'dagitim_yevmiye_id', d.dagitim_yevmiye_id,
            'hesap', CASE WHEN d.durum = 'Onaylandı' AND d.hesap IS NOT NULL THEN d.hesap
                          ELSE dose_private.ys_hesap(v_okul, d.id) END,
            'onaylar', coalesce((SELECT jsonb_agg(jsonb_build_object('islem', o.islem, 'rol', o.rol, 'ad_soyad', o.ad_soyad,
                'aciklama', o.aciklama, 'zaman', o.zaman) ORDER BY o.id)
                FROM dose_private.ys_onay o WHERE o.donem_id = d.id), '[]'::JSONB),
            'odemeler', jsonb_build_object('SHÇEK', dose_private.ys_odeme(v_okul, d.id, 'SHÇEK'),
                'Merkez payı', dose_private.ys_odeme(v_okul, d.id, 'Merkez payı'),
                'ÜTP', dose_private.ys_odeme(v_okul, d.id, 'ÜTP')));
    ELSE
        t := dose_private.ys_tutarlar(v_okul, v_yil);
        v_onhesap := jsonb_build_object(
            'gelir', (t->>'gelir')::NUMERIC::TEXT, 'gider', (t->>'gider')::NUMERIC::TEXT,
            'hasilat', (t->>'hasilat')::NUMERIC::TEXT, 'faiz', (t->>'faiz')::NUMERIC::TEXT,
            'kar_oncesi', ((t->>'gelir')::NUMERIC - (t->>'gider')::NUMERIC)::TEXT,
            'shcek', round(greatest((t->>'hasilat')::NUMERIC, 0) * 0.01, 2)::TEXT);
    END IF;
    RETURN jsonb_build_object(
        'okul', (SELECT jsonb_build_object('ad', o.ad, 'kurum_kodu', o.kurum_kodu) FROM dose_private.okul o WHERE o.id = v_okul),
        'yil', v_yil, 'bugun', v_bugun, 'tamamlandi', make_date(v_yil, 12, 31) < v_bugun,
        'kayit', v_kayit, 'on_hesap', v_onhesap,
        'varsayilan', jsonb_build_object('utp_orani', '0.333333', 'shcek_orani', '0.01', 'dv_orani', '0.00759',
            'yillik_tavan', '396360.00', 'gv_orani', '0.15'),
        'kisiler', CASE WHEN d.id IS NULL THEN '[]'::JSONB ELSE coalesce((SELECT jsonb_agg(jsonb_build_object(
            'personel_id', k.personel_id, 'gorev', k.gorev, 'unvan_grubu', k.unvan_grubu, 'bolum_id', k.bolum_id,
            'fiili_gun', k.fiili_gun::TEXT, 'fc_saat', k.fc_saat::TEXT, 'katki_orani', k.katki_orani::TEXT,
            'takdir_orani', k.takdir_orani::TEXT, 'haric', k.haric, 'haric_neden', k.haric_neden,
            'onceki_utp', k.onceki_utp::TEXT, 'gv_orani', k.gv_orani::TEXT) ORDER BY k.sira)
            FROM dose_private.ys_kisi k WHERE k.donem_id = d.id), '[]'::JSONB) END,
        'personel', coalesce((SELECT jsonb_agg(jsonb_build_object('id', p.id, 'ad_soyad', p.ad_soyad,
            'kadro_unvani', p.kadro_unvani, 'dose_gorevi', p.dose_gorevi, 'unvan_grubu', coalesce(p.unvan_grubu, 3),
            'bolum_id', p.bolum_id, 'iban_var', nullif(btrim(p.iban), '') IS NOT NULL, 'aktif', p.aktif = 1,
            'fc_saat', coalesce((SELECT sum(x) FROM dose_private.fc_kisi fk
                JOIN dose_private.fc_bordro fb ON fb.id = fk.bordro_id, unnest(fk.gunler) x
                WHERE fk.okul_id = v_okul AND fk.personel_id = p.id AND fb.yil = v_yil AND fb.durum = 'Onaylandı'), 0)::TEXT)
            ORDER BY p.ad_soyad, p.id)
            FROM public.personel p WHERE p.okul_id = v_okul
              AND (p.aktif = 1 OR EXISTS (SELECT 1 FROM dose_private.ys_kisi k WHERE k.donem_id = d.id AND k.personel_id = p.id))),
            '[]'::JSONB),
        'bolumler', coalesce((SELECT jsonb_agg(jsonb_build_object('id', b.id, 'ad', b.ad,
            'yontem', coalesce(b.utp_yontemi, 'Fazla çalışma saati ile orantılı (md.5/7-a)'),
            'gelir', coalesce((dose_private.ys_bolum_gelir(v_okul, v_yil)->>b.id::TEXT)::NUMERIC, 0)::TEXT) ORDER BY b.ad, b.id)
            FROM public.bolum b WHERE b.okul_id = v_okul), '[]'::JSONB),
        'iptaller', coalesce((SELECT jsonb_agg(jsonb_build_object('id', x.id, 'belge_no', x.belge_no,
            'gerekce', x.iptal_gerekcesi) ORDER BY x.id)
            FROM dose_private.ys_donem x WHERE x.okul_id = v_okul AND x.yil = v_yil AND x.durum = 'İptal'), '[]'::JSONB),
        'banka_bakiye', CASE WHEN public.dose_rol() = 'Sayman'
            THEN dose_private.kasa_bakiye(v_okul, 'Banka (102)')::TEXT END);
END;
$$;

-- ------------------------------------------------------------------ taslak kaydı (sayman)
CREATE OR REPLACE FUNCTION public.dose_ys_kaydet(p_id INTEGER, p_surum INTEGER, p_veri JSONB, p_kisiler JSONB, p_istek UUID)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); v_eski dose_private.ys_donem%ROWTYPE; v_id INTEGER; v_surum INTEGER;
    v_kisit TEXT; v_yil INTEGER; v_utp NUMERIC; v_tahsis NUMERIC; v_odenmis NUMERIC; v_shcek NUMERIC; v_dv NUMERIC;
    v_tavan NUMERIC; v_yuz BOOLEAN; v_aciklama TEXT; v_k JSONB; v_sira INTEGER := 0; v_kisi INTEGER; v_gorev TEXT;
    v_bolum INTEGER; v_grup INTEGER; v_haric BOOLEAN; v_neden TEXT;
BEGIN
    IF v_okul IS NULL OR auth.uid() IS NULL OR public.dose_rol() <> 'Sayman' OR public.dose_yetki('yil_sonu') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Kâr dağıtım cetvelini yalnız yetkili sayman hazırlayabilir.';
    END IF;
    IF jsonb_typeof(p_veri) IS DISTINCT FROM 'object' OR jsonb_typeof(p_kisiler) IS DISTINCT FROM 'array' OR p_istek IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Kâr dağıtım bilgileri eksik.';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtext('dose_ys'), v_okul);
    IF p_id IS NOT NULL THEN
        SELECT * INTO v_eski FROM dose_private.ys_donem WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Kâr dağıtım kaydı bulunamadı.';
        END IF;
        IF v_eski.durum <> 'Taslak' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yalnız taslak durumundaki cetvel değiştirilebilir.';
        END IF;
        IF p_surum IS DISTINCT FROM v_eski.surum THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Cetvel başka biri tarafından değiştirildi; güncelini yükleyin.',
                HINT = 'surum_cakismasi';
        END IF;
    ELSIF EXISTS (SELECT 1 FROM dose_private.ys_donem WHERE okul_id = v_okul AND istek_id = p_istek) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu cetvel daha önce kaydedildi; listeyi yenileyin.';
    END IF;

    IF jsonb_typeof(p_veri->'yil') IS DISTINCT FROM 'number' OR (p_veri->>'yil') !~ '^[0-9]{4}$'
       OR (p_veri->>'yil')::INTEGER NOT BETWEEN 2000 AND extract(year FROM now() AT TIME ZONE 'Europe/Istanbul')::INTEGER THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Kâr dağıtım yılını geçerli giriniz.';
    END IF;
    v_yil := (p_veri->>'yil')::INTEGER;
    IF p_id IS NOT NULL AND v_yil <> v_eski.yil THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Kaydedilmiş cetvelin yılı değiştirilemez.';
    END IF;
    IF p_id IS NULL AND EXISTS (SELECT 1 FROM dose_private.ys_donem WHERE okul_id = v_okul AND yil = v_yil AND durum <> 'İptal') THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu yıl için kâr dağıtım cetveli zaten var.';
    END IF;
    v_utp := dose_private.pb_sayi(p_veri->'utp_orani', 'ÜTP oranı', 6, 0.3334);
    v_tahsis := dose_private.pb_sayi(coalesce(p_veri->'tahsis_sermaye', '"0"'), 'Tahsis edilen sermaye', 2, 999999999999);
    v_odenmis := dose_private.pb_sayi(coalesce(p_veri->'odenmis_sermaye', '"0"'), 'Ödenmiş sermaye', 2, 999999999999);
    v_shcek := dose_private.pb_sayi(p_veri->'shcek_orani', 'SHÇEK oranı', 6, 0.1);
    v_dv := dose_private.pb_sayi(p_veri->'dv_orani', 'Damga vergisi oranı', 10, 0.1);
    v_tavan := dose_private.pb_sayi(p_veri->'yillik_tavan', 'Kişi başı yıllık ÜTP tavanı', 2, 999999999);
    IF v_tavan <= 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Kişi başı yıllık ÜTP tavanı sıfırdan büyük olmalıdır.';
    END IF;
    IF jsonb_typeof(p_veri->'yuz_yuze') IS DISTINCT FROM 'boolean' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yüz yüze eğitim yapılıp yapılmadığı seçilmelidir.';
    END IF;
    v_yuz := (p_veri->>'yuz_yuze')::BOOLEAN;
    v_aciklama := nullif(btrim(p_veri->>'aciklama'), '');
    IF length(v_aciklama) > 1000 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Açıklama en fazla 1000 karakter olabilir.';
    END IF;
    IF jsonb_array_length(p_kisiler) > 500 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Dağıtım listesine en fazla 500 personel eklenebilir.';
    END IF;

    IF p_id IS NULL THEN
        BEGIN
            INSERT INTO dose_private.ys_donem (okul_id, belge_no, yil, utp_orani, tahsis_sermaye, odenmis_sermaye,
                shcek_orani, dv_orani, yillik_tavan, yuz_yuze, aciklama, olusturan, istek_id)
            VALUES (v_okul, format('YS-%s-%s', v_yil, lpad(dose_private.sira_no(v_okul, 'yil_sonu', v_yil)::TEXT, 2, '0')),
                v_yil, v_utp, v_tahsis, v_odenmis, v_shcek, v_dv, v_tavan, v_yuz, v_aciklama, auth.uid(), p_istek)
            RETURNING id, surum INTO v_id, v_surum;
        EXCEPTION WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS v_kisit = CONSTRAINT_NAME;
            IF v_kisit = 'ys_istek_tek' THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu cetvel daha önce kaydedildi; listeyi yenileyin.';
            END IF;
            RAISE;
        END;
        PERFORM dose_private.ys_onay_ekle(v_okul, v_id, 'Hazırlandı', NULL);
    ELSE
        UPDATE dose_private.ys_donem SET utp_orani = v_utp, tahsis_sermaye = v_tahsis, odenmis_sermaye = v_odenmis,
            shcek_orani = v_shcek, dv_orani = v_dv, yillik_tavan = v_tavan, yuz_yuze = v_yuz, aciklama = v_aciklama,
            surum = surum + 1
        WHERE id = p_id RETURNING id, surum INTO v_id, v_surum;
        DELETE FROM dose_private.ys_kisi WHERE donem_id = v_id;
    END IF;

    FOR v_k IN SELECT value FROM jsonb_array_elements(p_kisiler) LOOP
        v_sira := v_sira + 1;
        IF jsonb_typeof(v_k) IS DISTINCT FROM 'object' OR jsonb_typeof(v_k->'personel_id') IS DISTINCT FROM 'number'
           OR (v_k->>'personel_id') !~ '^[0-9]{1,9}$' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. dağıtım satırı geçersiz.', v_sira);
        END IF;
        v_kisi := (v_k->>'personel_id')::INTEGER;
        IF NOT EXISTS (SELECT 1 FROM public.personel WHERE okul_id = v_okul AND id = v_kisi) THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. satırdaki personel bulunamadı.', v_sira);
        END IF;
        v_gorev := v_k->>'gorev';
        IF jsonb_typeof(v_k->'gorev') IS DISTINCT FROM 'string' OR NOT dose_private.ys_gorev_gecerli(v_gorev) THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. satırda döner sermaye görevini seçiniz.', v_sira);
        END IF;
        IF jsonb_typeof(v_k->'unvan_grubu') IS DISTINCT FROM 'number' OR (v_k->>'unvan_grubu') !~ '^[1-5]$' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. satırda unvan grubu 1-5 olmalıdır.', v_sira);
        END IF;
        v_grup := (v_k->>'unvan_grubu')::INTEGER;
        v_bolum := NULL;
        IF jsonb_typeof(v_k->'bolum_id') = 'number' AND (v_k->>'bolum_id') ~ '^[0-9]{1,9}$' THEN
            v_bolum := (v_k->>'bolum_id')::INTEGER;
            IF NOT EXISTS (SELECT 1 FROM public.bolum WHERE okul_id = v_okul AND id = v_bolum) THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. satırdaki bölüm bulunamadı.', v_sira);
            END IF;
        ELSIF jsonb_typeof(v_k->'bolum_id') IS NOT NULL AND jsonb_typeof(v_k->'bolum_id') <> 'null' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. satırdaki bölüm geçersiz.', v_sira);
        END IF;
        IF v_gorev IN ('Bölüm/Alan Şefi', 'Atölye/Laboratuvar Şefi') AND v_bolum IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. satırdaki şefin bölümünü seçiniz.', v_sira);
        END IF;
        v_haric := coalesce(jsonb_typeof(v_k->'haric') = 'boolean' AND (v_k->>'haric')::BOOLEAN, false);
        v_neden := nullif(btrim(v_k->>'haric_neden'), '');
        IF v_haric AND v_neden IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. satırda dağıtım dışı bırakma nedenini yazınız (md.6).', v_sira);
        END IF;
        BEGIN
            INSERT INTO dose_private.ys_kisi (okul_id, donem_id, sira, personel_id, gorev, unvan_grubu, bolum_id, fiili_gun,
                fc_saat, katki_orani, takdir_orani, haric, haric_neden, onceki_utp, gv_orani)
            VALUES (v_okul, v_id, v_sira, v_kisi, v_gorev, v_grup, v_bolum,
                dose_private.pb_sayi(coalesce(v_k->'fiili_gun', '"0"'), format('%s. satırdaki fiilen çalışılan gün', v_sira), 2, 366),
                dose_private.pb_sayi(coalesce(v_k->'fc_saat', '"0"'), format('%s. satırdaki fazla çalışma saati', v_sira), 2, 99999),
                dose_private.pb_sayi(coalesce(v_k->'katki_orani', '"0"'), format('%s. satırdaki katkı oranı', v_sira), 4, 100000),
                dose_private.pb_sayi(coalesce(v_k->'takdir_orani', '"0"'), format('%s. satırdaki takdir puanı', v_sira), 4, 100000),
                v_haric, v_neden,
                dose_private.pb_sayi(coalesce(v_k->'onceki_utp', '"0"'), format('%s. satırdaki yıl içi ödenmiş ÜTP', v_sira), 2, 999999999),
                dose_private.pb_sayi(coalesce(v_k->'gv_orani', 'null'::JSONB), format('%s. satırdaki gelir vergisi oranı', v_sira), 4, 1));
        EXCEPTION WHEN unique_violation THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. satırdaki personel listede birden fazla kez var.', v_sira);
        WHEN check_violation THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s. satırdaki değerler geçersiz.', v_sira);
        END;
    END LOOP;

    PERFORM dose_private.log(v_okul, CASE WHEN p_id IS NULL THEN 'Kâr dağıtım cetveli hazırlandı' ELSE 'Kâr dağıtım cetveli güncellendi' END,
        'ys_donem', v_id, v_yil::TEXT, CASE WHEN p_id IS NULL THEN NULL ELSE to_jsonb(v_eski) END, NULL);
    RETURN jsonb_build_object('id', v_id, 'surum', v_surum, 'hesap', dose_private.ys_hesap(v_okul, v_id));
END;
$$;

-- ------------------------------------------------------------------ onay zinciri (sayman -> okul müdürü)
CREATE OR REPLACE FUNCTION public.dose_ys_gonder(p_id INTEGER, p_surum INTEGER) RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_okul INTEGER := public.dose_okul(); d dose_private.ys_donem%ROWTYPE; v_hesap JSONB;
BEGIN
    IF v_okul IS NULL OR auth.uid() IS NULL OR public.dose_rol() <> 'Sayman' OR public.dose_yetki('yil_sonu') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Kâr dağıtım cetvelini yalnız yetkili sayman onaya gönderebilir.';
    END IF;
    SELECT * INTO d FROM dose_private.ys_donem WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
    IF NOT FOUND OR d.durum <> 'Taslak' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yalnız taslak cetvel onaya gönderilebilir.';
    END IF;
    IF p_surum IS DISTINCT FROM d.surum THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Cetvel değiştirildi; güncelini yükleyin.', HINT = 'surum_cakismasi';
    END IF;
    v_hesap := dose_private.ys_hesap(v_okul, d.id);
    IF jsonb_array_length(v_hesap->'hatalar') > 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Cetvel kontrolleri tamamlanmadı: ' || (v_hesap->'hatalar'->>0);
    END IF;
    UPDATE dose_private.ys_donem SET durum = 'Müdür Onayında', surum = surum + 1 WHERE id = d.id;
    PERFORM dose_private.ys_onay_ekle(v_okul, d.id, 'Onaya gönderildi', NULL);
    PERFORM dose_private.log(v_okul, 'Kâr dağıtım cetveli onaya gönderildi', 'ys_donem', d.id, d.belge_no);
    RETURN jsonb_build_object('id', d.id, 'durum', 'Müdür Onayında', 'surum', d.surum + 1);
END;
$$;

CREATE OR REPLACE FUNCTION public.dose_ys_karar(p_id INTEGER, p_surum INTEGER, p_onay BOOLEAN, p_aciklama TEXT)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); d dose_private.ys_donem%ROWTYPE; v_hesap JSONB;
    v_aciklama TEXT := nullif(btrim(p_aciklama), ''); v_tarih DATE; v_kar NUMERIC; v_shcek NUMERIC;
    v_satirlar JSONB; v_net NUMERIC; v_kapanis_kar NUMERIC; v_fis_shcek INTEGER; v_fis_kapanis INTEGER;
    v_fis_dagitim INTEGER; v_kesinti NUMERIC; v_merkez NUMERIC; v_sermaye NUMERIC;
BEGIN
    IF v_okul IS NULL OR auth.uid() IS NULL OR public.dose_rol() <> 'Okul Müdürü' OR public.dose_yetki('yil_sonu') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Kâr dağıtımını yalnız harcama yetkilisi (Okul Müdürü) onaylayabilir.';
    END IF;
    IF p_onay IS NULL OR length(v_aciklama) > 500 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Karar ve en fazla 500 karakterlik açıklama gereklidir.';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtext('dose_ys'), v_okul);
    SELECT * INTO d FROM dose_private.ys_donem WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
    IF NOT FOUND OR d.durum <> 'Müdür Onayında' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Onay bekleyen kâr dağıtım cetveli bulunamadı.';
    END IF;
    IF p_surum IS DISTINCT FROM d.surum THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Cetvel değiştirildi; güncelini yükleyin.', HINT = 'surum_cakismasi';
    END IF;
    IF NOT p_onay THEN
        IF v_aciklama IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İade gerekçesini yazınız.';
        END IF;
        UPDATE dose_private.ys_donem SET durum = 'Taslak', surum = surum + 1 WHERE id = d.id;
        PERFORM dose_private.ys_onay_ekle(v_okul, d.id, 'İade edildi', v_aciklama);
        PERFORM dose_private.log(v_okul, 'Kâr dağıtım cetveli iade edildi', 'ys_donem', d.id, v_aciklama);
        RETURN jsonb_build_object('id', d.id, 'durum', 'Taslak', 'surum', d.surum + 1);
    END IF;

    v_hesap := dose_private.ys_hesap(v_okul, d.id);
    IF jsonb_array_length(v_hesap->'hatalar') > 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Cetvel kontrolleri tamamlanmadı: ' || (v_hesap->'hatalar'->>0);
    END IF;
    v_tarih := make_date(d.yil, 12, 31);
    v_shcek := (v_hesap->>'shcek')::NUMERIC;
    v_kar := (v_hesap->>'donem_kari')::NUMERIC;

    -- 1) SHÇEK payı tahakkuku (2828 s.K. md.18/1-k): brüt hasılatın %1'i.
    IF v_shcek > 0 THEN
        v_fis_shcek := dose_private.yevmiye_olustur(v_okul, v_tarih,
            format('%s %s yılı SHÇEK payı tahakkuku', d.belge_no, d.yil), 'YilSonu', d.id, jsonb_build_array(
                jsonb_build_object('hesap', '770', 'borc', v_shcek, 'alacak', 0),
                jsonb_build_object('hesap', '362', 'borc', 0, 'alacak', v_shcek)));
    END IF;

    -- 2) Gelir ve gider hesaplarının kapatılması (590 dönem net kârı / 591 dönem net zararı).
    WITH b AS (
        SELECT s.hesap_kodu, sum(s.alacak - s.borc) AS net
        FROM public.yevmiye_satir s JOIN public.yevmiye y ON y.okul_id = s.okul_id AND y.id = s.yevmiye_id
        WHERE s.okul_id = v_okul AND y.tarih::DATE BETWEEN make_date(d.yil, 1, 1) AND v_tarih
          AND s.hesap_kodu ~ '^[67]'
        GROUP BY s.hesap_kodu HAVING sum(s.alacak - s.borc) <> 0
    )
    SELECT jsonb_agg(jsonb_build_object('hesap', b.hesap_kodu, 'borc', greatest(b.net, 0), 'alacak', greatest(-b.net, 0))
               ORDER BY b.hesap_kodu), coalesce(sum(b.net), 0)
      INTO v_satirlar, v_kapanis_kar FROM b;
    IF v_kapanis_kar <> v_kar THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = format('Gelir-gider hesaplarının bakiyesi (%s TL) hesaplanan dönem kârıyla (%s TL) uyuşmuyor; yevmiyeyi kontrol ediniz.',
                v_kapanis_kar, v_kar);
    END IF;
    IF v_satirlar IS NOT NULL AND v_kar <> 0 THEN
        v_satirlar := v_satirlar || jsonb_build_array(CASE WHEN v_kar > 0
            THEN jsonb_build_object('hesap', '590', 'borc', 0, 'alacak', v_kar)
            ELSE jsonb_build_object('hesap', '591', 'borc', -v_kar, 'alacak', 0) END);
        v_fis_kapanis := dose_private.yevmiye_olustur(v_okul, v_tarih,
            format('%s %s yılı gelir ve gider hesaplarının kapanışı', d.belge_no, d.yil), 'YilSonu kapanış', d.id, v_satirlar);
    END IF;

    -- 3) Kâr dağıtımı: ÜTP (net 335, kesintiler 360), Merkez Saymanlık payı (362), sermaye (500).
    IF v_kar > 0 THEN
        v_net := ((v_hesap->'toplam')->>'net')::NUMERIC;
        v_kesinti := ((v_hesap->'toplam')->>'gelir_vergisi')::NUMERIC + ((v_hesap->'toplam')->>'damga_vergisi')::NUMERIC;
        v_merkez := (v_hesap->>'merkez_payi')::NUMERIC;
        v_sermaye := (v_hesap->>'sermaye_payi')::NUMERIC;
        SELECT jsonb_agg(x) INTO v_satirlar FROM (
            SELECT jsonb_build_object('hesap', '590', 'borc', v_kar, 'alacak', 0) AS x
            UNION ALL SELECT jsonb_build_object('hesap', '335', 'borc', 0, 'alacak', v_net) WHERE v_net > 0
            UNION ALL SELECT jsonb_build_object('hesap', '360', 'borc', 0, 'alacak', v_kesinti) WHERE v_kesinti > 0
            UNION ALL SELECT jsonb_build_object('hesap', '362', 'borc', 0, 'alacak', v_merkez) WHERE v_merkez > 0
            UNION ALL SELECT jsonb_build_object('hesap', '500', 'borc', 0, 'alacak', v_sermaye) WHERE v_sermaye > 0) s;
        v_fis_dagitim := dose_private.yevmiye_olustur(v_okul, v_tarih,
            format('%s %s yılı kâr dağıtımı (ÜTP, Merkez Saymanlık ve sermaye payları)', d.belge_no, d.yil),
            'YilSonu dağıtım', d.id, v_satirlar);
    END IF;

    UPDATE dose_private.ys_donem SET durum = 'Onaylandı', hesap = v_hesap, shcek_yevmiye_id = v_fis_shcek,
        kapanis_yevmiye_id = v_fis_kapanis, dagitim_yevmiye_id = v_fis_dagitim, surum = surum + 1
    WHERE id = d.id;
    PERFORM dose_private.ys_onay_ekle(v_okul, d.id, 'Onaylandı', v_aciklama);
    PERFORM dose_private.log(v_okul, 'Kâr dağıtımı onaylandı', 'ys_donem', d.id, d.belge_no, NULL,
        jsonb_build_object('donem_kari', v_kar::TEXT, 'shcek', v_shcek::TEXT, 'utp', v_hesap->>'dagitilan_utp',
            'merkez', v_hesap->>'merkez_payi', 'sermaye', v_hesap->>'sermaye_payi',
            'yevmiyeler', jsonb_build_array(v_fis_shcek, v_fis_kapanis, v_fis_dagitim)));
    RETURN jsonb_build_object('id', d.id, 'durum', 'Onaylandı', 'surum', d.surum + 1, 'hesap', v_hesap,
        'shcek_yevmiye_id', v_fis_shcek, 'kapanis_yevmiye_id', v_fis_kapanis, 'dagitim_yevmiye_id', v_fis_dagitim);
END;
$$;

-- ------------------------------------------------------------------ iptal
CREATE OR REPLACE FUNCTION public.dose_ys_iptal(p_id INTEGER, p_surum INTEGER, p_gerekce TEXT) RETURNS JSONB
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); d dose_private.ys_donem%ROWTYPE; v_rol TEXT := public.dose_rol();
    v_gerekce TEXT := nullif(btrim(p_gerekce), ''); v_fis INTEGER; v_ters INTEGER[] := ARRAY[]::INTEGER[];
    v_satirlar JSONB;
BEGIN
    IF v_okul IS NULL OR auth.uid() IS NULL OR public.dose_yetki('yil_sonu') <> 'y'
       OR v_rol NOT IN ('Sayman', 'Okul Müdürü') THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Kâr dağıtım cetvelini iptal etme yetkiniz yok.';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtext('dose_ys'), v_okul);
    SELECT * INTO d FROM dose_private.ys_donem WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
    IF NOT FOUND OR d.durum NOT IN ('Taslak', 'Onaylandı') THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İptal edilebilir kâr dağıtım cetveli bulunamadı.';
    END IF;
    IF p_surum IS DISTINCT FROM d.surum THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Cetvel değiştirildi; güncelini yükleyin.', HINT = 'surum_cakismasi';
    END IF;
    IF v_gerekce IS NULL OR length(v_gerekce) > 500 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'İptal gerekçesi zorunludur (en fazla 500 karakter).';
    END IF;
    IF d.durum = 'Taslak' AND v_rol <> 'Sayman' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Taslak cetveli yalnız sayman iptal edebilir.';
    END IF;
    IF d.durum = 'Onaylandı' THEN
        IF v_rol <> 'Okul Müdürü' THEN
            RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Onaylanmış kâr dağıtımını yalnız Okul Müdürü iptal edebilir.';
        END IF;
        PERFORM dose_private.kasa_kilitle(v_okul, 'Banka (102)');
        IF dose_private.ys_odeme(v_okul, d.id, 'SHÇEK') IS NOT NULL OR dose_private.ys_odeme(v_okul, d.id, 'Merkez payı') IS NOT NULL
           OR dose_private.ys_odeme(v_okul, d.id, 'ÜTP') IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ödemesi yapılmış kâr dağıtımı iptal edilemez; önce ödemeleri tersleyin.';
        END IF;
        -- Ters kayıtlar aynı yılın 31 Aralık tarihiyle atılır; böylece yeniden kapanış doğru bakiyeyle yapılır.
        FOR v_fis IN SELECT x FROM unnest(ARRAY[d.dagitim_yevmiye_id, d.kapanis_yevmiye_id, d.shcek_yevmiye_id]) x WHERE x IS NOT NULL LOOP
            SELECT jsonb_agg(jsonb_build_object('hesap', hesap_kodu, 'borc', alacak, 'alacak', borc) ORDER BY id)
              INTO v_satirlar FROM public.yevmiye_satir WHERE okul_id = v_okul AND yevmiye_id = v_fis;
            v_ters := array_append(v_ters, dose_private.yevmiye_olustur(v_okul, make_date(d.yil, 12, 31),
                format('%s kâr dağıtımı iptali: %s', d.belge_no, v_gerekce), 'YilSonu ters kayıt', d.id, v_satirlar));
        END LOOP;
    END IF;
    UPDATE dose_private.ys_donem SET durum = 'İptal', iptal_gerekcesi = v_gerekce, ters_yevmiye_idler = v_ters,
        surum = surum + 1 WHERE id = d.id;
    PERFORM dose_private.ys_onay_ekle(v_okul, d.id, 'İptal edildi', v_gerekce);
    PERFORM dose_private.log(v_okul, 'Kâr dağıtım cetveli iptal edildi', 'ys_donem', d.id, v_gerekce, NULL,
        jsonb_build_object('ters_yevmiye_idler', to_jsonb(v_ters)));
    RETURN jsonb_build_object('id', d.id, 'durum', 'İptal', 'surum', d.surum + 1, 'ters_yevmiye_idler', to_jsonb(v_ters));
END;
$$;

-- ------------------------------------------------------------------ banka ödemeleri (362 / 335 -> 102)
CREATE OR REPLACE FUNCTION public.dose_ys_ode(p_id INTEGER, p_kalem TEXT, p_tarih DATE, p_belge_no TEXT, p_istek UUID)
RETURNS JSONB LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_okul INTEGER := public.dose_okul(); d dose_private.ys_donem%ROWTYPE; v_bakiye NUMERIC; v_son DATE;
    v_tutar NUMERIC; v_karsi TEXT; v_hareket INTEGER; v_fis INTEGER; v_kisit TEXT;
    v_belge TEXT := nullif(btrim(p_belge_no), ''); v_aciklama TEXT;
BEGIN
    IF auth.uid() IS NULL OR public.dose_rol() <> 'Sayman' OR public.dose_yetki('kasa') <> 'y'
       OR public.dose_yetki('yil_sonu') <> 'y' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Kâr dağıtım ödemelerini yalnız yetkili sayman yapabilir.';
    END IF;
    IF p_kalem IS NULL OR p_kalem NOT IN ('SHÇEK', 'Merkez payı', 'ÜTP') OR p_tarih IS NULL
       OR p_tarih > (now() AT TIME ZONE 'Europe/Istanbul')::DATE OR p_istek IS NULL OR length(v_belge) > 100 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Geçerli ödeme kalemi, tarih ve işlem kimliği gereklidir.';
    END IF;
    SELECT * INTO d FROM dose_private.ys_donem WHERE okul_id = v_okul AND id = p_id FOR UPDATE;
    IF NOT FOUND OR d.durum <> 'Onaylandı' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Yalnız onaylanmış kâr dağıtımının ödemesi yapılabilir.';
    END IF;
    v_tutar := CASE p_kalem WHEN 'SHÇEK' THEN (d.hesap->>'shcek')::NUMERIC
        WHEN 'Merkez payı' THEN (d.hesap->>'merkez_payi')::NUMERIC ELSE ((d.hesap->'toplam')->>'net')::NUMERIC END;
    v_karsi := CASE WHEN p_kalem = 'ÜTP' THEN '335' ELSE '362' END;
    IF coalesce(v_tutar, 0) <= 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('Bu dönem için ödenecek %s tutarı yok.', p_kalem);
    END IF;
    IF p_tarih <= make_date(d.yil, 12, 31) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Ödeme tarihi dağıtım yılının sonundan sonra olmalıdır.';
    END IF;
    PERFORM dose_private.kasa_kilitle(v_okul, 'Banka (102)');
    IF EXISTS (SELECT 1 FROM public.kasa_banka WHERE okul_id = v_okul AND istek_id = p_istek) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu ödeme daha önce kaydedildi; listeyi yenileyin.';
    END IF;
    IF dose_private.ys_odeme(v_okul, d.id, p_kalem) IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('%s ödemesi zaten yapıldı.', p_kalem);
    END IF;
    SELECT max(tarih::DATE) INTO v_son FROM public.kasa_banka WHERE okul_id = v_okul AND hesap = 'Banka (102)';
    IF v_son IS NOT NULL AND p_tarih < v_son THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Son banka hareketinden daha eski tarihe kayıt yapılamaz.';
    END IF;
    v_bakiye := dose_private.kasa_bakiye(v_okul, 'Banka (102)');
    IF v_tutar > v_bakiye THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format('Banka bakiyesi yetersiz (%s TL).', v_bakiye);
    END IF;
    v_aciklama := format('%s %s yılı %s ödemesi', d.belge_no, d.yil,
        CASE p_kalem WHEN 'SHÇEK' THEN 'SHÇEK payı' WHEN 'Merkez payı' THEN 'Merkez Saymanlık payı' ELSE 'ÜTP (net)' END);
    BEGIN
        INSERT INTO public.kasa_banka (okul_id, tarih, hesap, yon, tur, tutar, hasilat_tutari, belge_no,
            aciklama, kaynak, karsi_hesap, istek_id, olusturan, ys_donem_id, ys_kalem)
        VALUES (v_okul, p_tarih::TEXT, 'Banka (102)', 'Çıkış', 'Ödeme', v_tutar, 0, v_belge,
            v_aciklama, 'KasaBanka', v_karsi, p_istek, auth.uid(), d.id, p_kalem) RETURNING id INTO v_hareket;
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS v_kisit = CONSTRAINT_NAME;
        IF v_kisit = 'kasa_istek_tek' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Bu ödeme daha önce kaydedildi; listeyi yenileyin.';
        END IF;
        RAISE;
    END;
    v_fis := dose_private.yevmiye_olustur(v_okul, p_tarih, v_aciklama, 'KasaBanka', v_hareket, jsonb_build_array(
        jsonb_build_object('hesap', v_karsi, 'borc', v_tutar, 'alacak', 0),
        jsonb_build_object('hesap', '102', 'borc', 0, 'alacak', v_tutar)));
    PERFORM dose_private.log(v_okul, 'Kâr dağıtım ödemesi yapıldı', 'kasa_banka', v_hareket, v_aciklama, NULL,
        jsonb_build_object('ys_donem_id', d.id, 'kalem', p_kalem, 'tutar', v_tutar::TEXT, 'yevmiye_id', v_fis));
    RETURN jsonb_build_object('id', v_hareket, 'yevmiye_id', v_fis, 'tutar', v_tutar::TEXT, 'bakiye', (v_bakiye - v_tutar)::TEXT);
END;
$$;

REVOKE ALL ON FUNCTION dose_private.ys_dagit(NUMERIC, JSONB), dose_private.ys_topla(JSONB, JSONB),
    dose_private.ys_tutarlar(INTEGER, INTEGER), dose_private.ys_bolum_gelir(INTEGER, INTEGER),
    dose_private.ys_odeme(INTEGER, INTEGER, TEXT), dose_private.ys_onay_ekle(INTEGER, INTEGER, TEXT, TEXT),
    dose_private.ys_gorev_gecerli(TEXT), dose_private.ys_hesap(INTEGER, INTEGER),
    dose_private.ys_kisi_silme_kontrol() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.dose_ys_veri(INTEGER), public.dose_ys_kaydet(INTEGER, INTEGER, JSONB, JSONB, UUID),
    public.dose_ys_gonder(INTEGER, INTEGER), public.dose_ys_karar(INTEGER, INTEGER, BOOLEAN, TEXT),
    public.dose_ys_iptal(INTEGER, INTEGER, TEXT), public.dose_ys_ode(INTEGER, TEXT, DATE, TEXT, UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dose_ys_veri(INTEGER), public.dose_ys_kaydet(INTEGER, INTEGER, JSONB, JSONB, UUID),
    public.dose_ys_gonder(INTEGER, INTEGER), public.dose_ys_karar(INTEGER, INTEGER, BOOLEAN, TEXT),
    public.dose_ys_iptal(INTEGER, INTEGER, TEXT), public.dose_ys_ode(INTEGER, TEXT, DATE, TEXT, UUID) TO authenticated;
