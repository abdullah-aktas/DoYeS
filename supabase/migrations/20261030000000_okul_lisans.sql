-- Multi-school foundation: every school is one workspace inside this Supabase project.
-- The vendor opens a school (license) from the SQL editor and hands a one-time activation code to the principal.

CREATE SCHEMA IF NOT EXISTS dose_private;
REVOKE ALL ON SCHEMA dose_private FROM PUBLIC, anon, authenticated;

CREATE TABLE IF NOT EXISTS dose_private.okul (
    id SERIAL PRIMARY KEY,
    ad TEXT NOT NULL CHECK (length(btrim(ad)) BETWEEN 3 AND 200),
    kurum_kodu TEXT NOT NULL UNIQUE CHECK (kurum_kodu ~ '^[0-9]{5,8}$'),
    lisans_bitis DATE,
    aktif BOOLEAN NOT NULL DEFAULT true,
    olusturma TIMESTAMPTZ NOT NULL DEFAULT now(),
    kod_ozet TEXT CHECK (kod_ozet ~ '^[0-9a-f]{64}$'),
    kod_bitis TIMESTAMPTZ,
    hatali_deneme INTEGER NOT NULL DEFAULT 0 CHECK (hatali_deneme >= 0),
    kod_kullanim TIMESTAMPTZ,
    kod_kullanan UUID
);

CREATE TABLE IF NOT EXISTS dose_private.uyelik (
    auth_user_id UUID PRIMARY KEY REFERENCES auth.users (id) ON DELETE RESTRICT,
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul (id),
    rol TEXT NOT NULL CHECK (rol IN (
        'Sistem Yöneticisi', 'Okul Müdürü', 'Teknik Müdür Yardımcısı', 'Sayman',
        'Alan Şefi', 'Öğretmen', 'Memur / Veri Girişi', 'İzleyici / Denetçi'
    )),
    ad_soyad TEXT NOT NULL CHECK (length(btrim(ad_soyad)) BETWEEN 3 AND 120),
    bolum_id INTEGER REFERENCES public.bolum (id),
    personel_id INTEGER REFERENCES public.personel (id),
    aktif BOOLEAN NOT NULL DEFAULT true,
    olusturma TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_uyelik_okul ON dose_private.uyelik (okul_id);

CREATE TABLE IF NOT EXISTS dose_private.davet (
    eposta TEXT PRIMARY KEY CHECK (eposta = lower(btrim(eposta)) AND eposta ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'),
    okul_id INTEGER NOT NULL REFERENCES dose_private.okul (id),
    rol TEXT NOT NULL CHECK (rol IN (
        'Sistem Yöneticisi', 'Okul Müdürü', 'Teknik Müdür Yardımcısı', 'Sayman',
        'Alan Şefi', 'Öğretmen', 'Memur / Veri Girişi', 'İzleyici / Denetçi'
    )),
    ad_soyad TEXT NOT NULL CHECK (length(btrim(ad_soyad)) BETWEEN 3 AND 120),
    bolum_id INTEGER REFERENCES public.bolum (id),
    personel_id INTEGER REFERENCES public.personel (id),
    davet_eden UUID,
    olusturma TIMESTAMPTZ NOT NULL DEFAULT now(),
    bitis TIMESTAMPTZ NOT NULL DEFAULT now() + interval '30 days'
);

-- Page permission matrix (mirrors dose/yetki.py SAYFA_YETKI). Role order:
-- Sistem, Müdür, TMY, Sayman, Alan Şefi, Öğretmen, Memur, İzleyici. y = write, g = read, - = none.
CREATE TABLE IF NOT EXISTS dose_private.sayfa_yetki (
    sayfa TEXT PRIMARY KEY,
    baslik TEXT NOT NULL,
    kodlar TEXT NOT NULL CHECK (kodlar ~ '^[yg-]{8}$')
);
INSERT INTO dose_private.sayfa_yetki (sayfa, baslik, kodlar) VALUES
    ('kurum', 'Kurum ve Görevliler', 'yygy--gg'),
    ('bolum', 'Bölüm / Alan / Atölyeler', 'yyygg-yg'),
    ('personel', 'Personel', 'yyyyg-yg'),
    ('ogrenci', 'Öğrenciler', 'ygygygyg'),
    ('cari', 'Cari Hesaplar', 'ygyyg-yg'),
    ('malzeme', 'Malzeme / Stok Kartları', 'ygyyygyg'),
    ('urun', 'Ürün / Hizmet ve Maliyet', 'ygyyygyg'),
    ('kullanici', 'Kullanıcılar', 'yy------'),
    ('islem_kaydi', 'İşlem Kaydı', 'yg-y---g')
ON CONFLICT (sayfa) DO UPDATE SET baslik = EXCLUDED.baslik, kodlar = EXCLUDED.kodlar;

ALTER TABLE dose_private.okul ENABLE ROW LEVEL SECURITY;
ALTER TABLE dose_private.uyelik ENABLE ROW LEVEL SECURITY;
ALTER TABLE dose_private.davet ENABLE ROW LEVEL SECURITY;
ALTER TABLE dose_private.sayfa_yetki ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA dose_private FROM PUBLIC, anon, authenticated;

-- ------------------------------------------------------------------ caller context
CREATE OR REPLACE FUNCTION public.dose_okul() RETURNS INTEGER
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT u.okul_id FROM dose_private.uyelik u JOIN dose_private.okul o ON o.id = u.okul_id
    WHERE u.auth_user_id = auth.uid() AND u.aktif AND o.aktif
$$;

CREATE OR REPLACE FUNCTION public.dose_rol() RETURNS TEXT
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT u.rol FROM dose_private.uyelik u JOIN dose_private.okul o ON o.id = u.okul_id
    WHERE u.auth_user_id = auth.uid() AND u.aktif AND o.aktif
$$;

CREATE OR REPLACE FUNCTION public.dose_bolum() RETURNS INTEGER
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT coalesce(u.bolum_id, (SELECT p.bolum_id FROM public.personel p WHERE p.id = u.personel_id), -1)
    FROM dose_private.uyelik u WHERE u.auth_user_id = auth.uid() AND u.aktif
$$;

CREATE OR REPLACE FUNCTION public.dose_bolum_kisitli() RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT coalesce(public.dose_rol() IN ('Alan Şefi', 'Öğretmen'), false)
$$;

CREATE OR REPLACE FUNCTION public.dose_lisans_gecerli() RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT coalesce((SELECT o.lisans_bitis IS NULL OR o.lisans_bitis >= (now() AT TIME ZONE 'Europe/Istanbul')::DATE
                     FROM dose_private.okul o WHERE o.id = public.dose_okul()), false)
$$;

-- 'y' write, 'g' read, '' none. An expired license turns every write permission into read-only.
CREATE OR REPLACE FUNCTION public.dose_yetki(p_sayfa TEXT) RETURNS TEXT
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT CASE WHEN y.c = 'y' AND NOT public.dose_lisans_gecerli() THEN 'g' ELSE coalesce(y.c, '') END
    FROM (SELECT (SELECT nullif(substr(s.kodlar, array_position(ARRAY[
            'Sistem Yöneticisi', 'Okul Müdürü', 'Teknik Müdür Yardımcısı', 'Sayman',
            'Alan Şefi', 'Öğretmen', 'Memur / Veri Girişi', 'İzleyici / Denetçi'], public.dose_rol()), 1), '-')
          FROM dose_private.sayfa_yetki s WHERE s.sayfa = p_sayfa) AS c) AS y
$$;

CREATE OR REPLACE FUNCTION dose_private.yetkiler() RETURNS JSONB
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT coalesce(jsonb_object_agg(s.sayfa, public.dose_yetki(s.sayfa)) FILTER (WHERE public.dose_yetki(s.sayfa) <> ''),
                    '{}'::JSONB)
    FROM dose_private.sayfa_yetki s
$$;

CREATE OR REPLACE FUNCTION dose_private.zaman() RETURNS TEXT
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT to_char(now() AT TIME ZONE 'Europe/Istanbul', 'YYYY-MM-DD HH24:MI:SS')
$$;

-- ------------------------------------------------------------------ vendor-side license tools (SQL editor / service_role)
CREATE OR REPLACE FUNCTION dose_private.kod_uret() RETURNS TEXT
LANGUAGE plpgsql VOLATILE SET search_path = '' AS $$
DECLARE
    v_hex TEXT := '';
    v_uuid TEXT;
    v_kod TEXT := 'DOSE';
BEGIN
    WHILE length(v_hex) < 24 LOOP
        v_uuid := replace(gen_random_uuid()::TEXT, '-', '');
        -- Skip the fixed version and variant nibbles of UUIDv4.
        v_hex := v_hex || substr(v_uuid, 1, 12) || substr(v_uuid, 14, 3) || substr(v_uuid, 18, 15);
    END LOOP;
    v_hex := upper(substr(v_hex, 1, 24));
    FOR i IN 0..5 LOOP
        v_kod := v_kod || '-' || substr(v_hex, i * 4 + 1, 4);
    END LOOP;
    RETURN v_kod;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.kod_ozeti(p_kod TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
    SELECT encode(sha256(convert_to(upper(regexp_replace(coalesce(p_kod, ''), '[^0-9A-Za-z]', '', 'g')), 'UTF8')), 'hex')
$$;

CREATE OR REPLACE FUNCTION dose_private.etkinlestirme_kodu(p_kurum_kodu TEXT, p_gecerlilik INTERVAL DEFAULT interval '7 days')
RETURNS TEXT
LANGUAGE plpgsql VOLATILE SET search_path = '' AS $$
DECLARE
    v_kod TEXT := dose_private.kod_uret();
BEGIN
    IF p_gecerlilik IS NULL OR p_gecerlilik < interval '10 minutes' OR p_gecerlilik > interval '30 days' THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Etkinleştirme kodu 10 dakika ile 30 gün arasında geçerli olmalıdır.';
    END IF;
    UPDATE dose_private.okul SET kod_ozet = dose_private.kod_ozeti(v_kod), kod_bitis = now() + p_gecerlilik,
        hatali_deneme = 0, kod_kullanim = NULL, kod_kullanan = NULL
    WHERE kurum_kodu = btrim(p_kurum_kodu);
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Bu kurum koduyla açılmış okul yok.';
    END IF;
    RETURN v_kod;
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.okul_ac(p_ad TEXT, p_kurum_kodu TEXT, p_lisans_bitis DATE DEFAULT NULL,
                                                p_gecerlilik INTERVAL DEFAULT interval '7 days')
RETURNS TEXT
LANGUAGE plpgsql VOLATILE SET search_path = '' AS $$
BEGIN
    INSERT INTO dose_private.okul (ad, kurum_kodu, lisans_bitis)
    VALUES (btrim(regexp_replace(coalesce(p_ad, ''), '\s+', ' ', 'g')), btrim(coalesce(p_kurum_kodu, '')), p_lisans_bitis);
    RETURN dose_private.etkinlestirme_kodu(p_kurum_kodu, p_gecerlilik);
END;
$$;

CREATE OR REPLACE FUNCTION dose_private.lisans_ayarla(p_kurum_kodu TEXT, p_lisans_bitis DATE, p_aktif BOOLEAN DEFAULT true)
RETURNS VOID
LANGUAGE plpgsql VOLATILE SET search_path = '' AS $$
BEGIN
    UPDATE dose_private.okul SET lisans_bitis = p_lisans_bitis, aktif = coalesce(p_aktif, true)
    WHERE kurum_kodu = btrim(p_kurum_kodu);
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Bu kurum koduyla açılmış okul yok.';
    END IF;
END;
$$;
