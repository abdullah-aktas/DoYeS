-- Move every school-owned table onto okul_id, replace the legacy username/password tables,
-- and add append-only audit, database-issued numbers and shared selection lists.

DROP TABLE IF EXISTS public.mobil_oturum;
DROP TABLE IF EXISTS public.kullanici;

-- kurum was a single row (id = 1); it becomes one row per school.
ALTER TABLE public.kurum DROP COLUMN IF EXISTS id;

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'ayar', 'kurum', 'parametre', 'islem_log', 'sayac', 'bolum', 'personel', 'ogrenci', 'cari', 'urun',
        'maliyet_kalem', 'fiyat_tespit', 'malzeme', 'stok_hareket', 'siparis', 'siparis_kalem', 'siparis_gorevli',
        'siparis_is_plani', 'fatura', 'fatura_kalem', 'kasa_banka', 'parca_basi', 'parca_basi_satir', 'fazla_calisma',
        'hazine_payi', 'yil_sonu', 'utp_kisi', 'yevmiye', 'yevmiye_satir', 'resmi_yazi', 'denetim', 'denetim_madde',
        'onay_durum', 'onay_kaydi'
    ] LOOP
        EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS okul_id INTEGER NOT NULL '
                       'DEFAULT public.dose_okul() REFERENCES dose_private.okul (id)', t);
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON public.%I (okul_id)', 'ix_' || t || '_okul', t);
    END LOOP;
END;
$$;

ALTER TABLE public.kurum ADD PRIMARY KEY (okul_id);
ALTER TABLE public.ayar DROP CONSTRAINT IF EXISTS ayar_pkey;
ALTER TABLE public.ayar ADD PRIMARY KEY (okul_id, anahtar);
ALTER TABLE public.parametre DROP CONSTRAINT IF EXISTS parametre_pkey;
ALTER TABLE public.parametre ADD PRIMARY KEY (okul_id, yil, anahtar);
ALTER TABLE public.sayac DROP CONSTRAINT IF EXISTS sayac_pkey;
ALTER TABLE public.sayac ADD PRIMARY KEY (okul_id, tur, yil);
ALTER TABLE public.yil_sonu DROP CONSTRAINT IF EXISTS yil_sonu_pkey;
ALTER TABLE public.yil_sonu ADD PRIMARY KEY (okul_id, yil);
ALTER TABLE public.hazine_payi DROP CONSTRAINT IF EXISTS hazine_payi_yil_ay_key;
ALTER TABLE public.hazine_payi ADD CONSTRAINT hazine_payi_okul_yil_ay_key UNIQUE (okul_id, yil, ay);
CREATE INDEX IF NOT EXISTS ix_islem_log_okul_id ON public.islem_log (okul_id, id);

-- Optimistic concurrency columns: a stale surum is rejected and the client reloads the newer version.
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['kurum', 'bolum', 'personel', 'ogrenci', 'cari', 'malzeme', 'urun'] LOOP
        EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS surum INTEGER NOT NULL DEFAULT 1', t);
        EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS guncelleyen TEXT', t);
        EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS guncelleme TEXT', t);
    END LOOP;
END;
$$;

-- ------------------------------------------------------------------ audit log (append-only)
CREATE OR REPLACE FUNCTION dose_private.log(p_okul INTEGER, p_islem TEXT, p_tablo TEXT, p_kayit INTEGER, p_detay TEXT,
                                            p_eski JSONB DEFAULT NULL, p_yeni JSONB DEFAULT NULL)
RETURNS VOID
LANGUAGE sql SET search_path = '' AS $$
    INSERT INTO public.islem_log (okul_id, zaman, kullanici, islem, tablo, kayit_id, detay, rol, ad_soyad, istemci, eski, yeni)
    SELECT p_okul, dose_private.zaman(), auth.uid()::TEXT, p_islem, p_tablo, p_kayit, p_detay, u.rol, u.ad_soyad,
           'Supabase', p_eski::TEXT, p_yeni::TEXT
    FROM (SELECT 1) AS bir
    LEFT JOIN dose_private.uyelik u ON u.auth_user_id = auth.uid()
$$;

CREATE OR REPLACE FUNCTION dose_private.log_degismez() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'İşlem kaydı değiştirilemez veya silinemez.';
END;
$$;
DROP TRIGGER IF EXISTS dose_log_degismez ON public.islem_log;
CREATE TRIGGER dose_log_degismez BEFORE UPDATE OR DELETE ON public.islem_log
    FOR EACH ROW EXECUTE FUNCTION dose_private.log_degismez();

-- ------------------------------------------------------------------ database-issued numbers
CREATE OR REPLACE FUNCTION dose_private.sira_no(p_okul INTEGER, p_tur TEXT, p_yil INTEGER DEFAULT 0)
RETURNS INTEGER
LANGUAGE sql VOLATILE SET search_path = '' AS $$
    INSERT INTO public.sayac AS s (okul_id, tur, yil, son) VALUES (p_okul, p_tur, p_yil, 1)
    ON CONFLICT (okul_id, tur, yil) DO UPDATE SET son = coalesce(s.son, 0) + 1
    RETURNING son
$$;

-- ------------------------------------------------------------------ selection lists (mirror dose/mevzuat.py)
CREATE TABLE IF NOT EXISTS public.secenek (
    liste TEXT NOT NULL,
    sira INTEGER NOT NULL,
    deger TEXT NOT NULL,
    etiket TEXT NOT NULL,
    PRIMARY KEY (liste, deger)
);
DELETE FROM public.secenek;
INSERT INTO public.secenek (liste, sira, deger, etiket)
SELECT l.liste, v.sira, v.deger, coalesce(v.etiket, v.deger)
FROM (VALUES
    ('utp_yontemi', ARRAY['Fazla çalışma saati ile orantılı (md.5/7-a)', 'Fiilen çalışılan gün ile orantılı (md.5/7-b)',
                          'Katkı oranına göre (md.5/7-c)'], NULL::TEXT[]),
    ('hizmet_sinifi', ARRAY['Eğitim ve Öğretim Hizmetleri', 'Teknik Hizmetler', 'Genel İdare Hizmetleri',
                            'Yardımcı Hizmetler', 'Diğer (4857 İşçi vb.)'], NULL),
    ('dose_gorevi', ARRAY['Harcama Yetkilisi (Okul Müdürü)', 'Gerçekleştirme Görevlisi (Teknik Md. Yrd.)',
                          'Bölüm/Alan Şefi', 'Atölye/Laboratuvar Şefi', 'Sayman', 'Diğer İdari Personel', 'Öğretmen',
                          'Mühendis/Uzman/Tekniker', 'Usta/Teknisyen/Ambar Memuru', 'Diğer Personel'], NULL),
    ('unvan_grubu', ARRAY['1', '2', '3', '4', '5'],
                    ARRAY['Harcama yetkilisi (50 puan)',
                          'Müdür yrd., bölüm/alan, atölye, laboratuvar, kısım şefi (45 puan)',
                          'Öğretmen, mühendis, mimar, sayman, uzman, tekniker (40 puan)',
                          'Büro şefi, teknisyen, ustabaşı, usta, ambar memuru vb. (35 puan)',
                          'Diğer personel (30 puan)']),
    ('istihdam', ARRAY['657 s. DMK', '4857 s. İş Kanunu', 'Sözleşmeli'], NULL),
    ('cari_tur', ARRAY['Müşteri', 'Tedarikçi', 'Çiftçi (Müstahsil)', 'Müşteri ve Tedarikçi'], NULL),
    ('malzeme_tur', ARRAY['İlk Madde ve Malzeme', 'Ticari Mal', 'Mamul', 'Yarı Mamul'], NULL),
    ('urun_tur', ARRAY['Mal', 'Hizmet'], NULL),
    ('birim', ARRAY['Adet', 'Kg', 'Gram', 'Litre', 'Metre', 'm²', 'm³', 'Paket', 'Kutu', 'Takım', 'Saat', 'Gün',
                    'Ton', 'Çuval', 'Kalıp', 'Cihaz', 'Hizmet'], NULL),
    ('ucret_esasi', ARRAY['Parça Başı Ücret (Yön. md.8)', 'Fazla Çalışma Ücreti',
                          'Özel Sektör İşbirliği (Yön. md.9-11)', 'Tesis İşletmesi (Yön. md.12)'], NULL)
) AS l (liste, degerler, etiketler)
CROSS JOIN LATERAL (
    SELECT i AS sira, l.degerler[i] AS deger, l.etiketler[i] AS etiket
    FROM generate_subscripts(l.degerler, 1) AS i
) AS v;
ALTER TABLE public.secenek ENABLE ROW LEVEL SECURITY;

-- Realtime clients receive only rows their RLS policies allow (Supabase hosted projects).
DO $$
DECLARE
    t TEXT;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
        FOREACH t IN ARRAY ARRAY['kurum', 'bolum', 'personel', 'ogrenci', 'cari', 'malzeme', 'urun'] LOOP
            IF NOT EXISTS (SELECT 1 FROM pg_publication_tables
                           WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = t) THEN
                EXECUTE format('ALTER PUBLICATION supabase_realtime ADD TABLE public.%I', t);
            END IF;
        END LOOP;
    END IF;
END;
$$;
