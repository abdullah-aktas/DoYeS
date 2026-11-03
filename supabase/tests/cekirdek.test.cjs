const { PGlite } = require('@electric-sql/pglite');
const fs = require('fs');
const assert = require('node:assert/strict');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..', 'migrations') + path.sep;
const uid = n => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`;
const M1 = uid(1), M2 = uid(2), SAY = uid(3), OGR = uid(4), SEF = uid(5), YENI = uid(6), ONAYSIZ = uid(7),
  TMY = uid(8), MERKEZ = uid(9);

async function kur(sonDosya = null) {
  const db = new PGlite();
  await db.exec(`
    CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN;
    CREATE SCHEMA auth; GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
    CREATE TABLE auth.users (id uuid PRIMARY KEY, email text, email_confirmed_at timestamptz, last_sign_in_at timestamptz);
    CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
      $$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
    GRANT EXECUTE ON FUNCTION auth.uid() TO anon, authenticated;
    GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
    INSERT INTO auth.users (id, email, email_confirmed_at) VALUES
      ('${M1}', 'mudur1@okul.k12.tr', now()), ('${M2}', 'mudur2@okul.k12.tr', now()),
      ('${SAY}', 'sayman@okul.k12.tr', now()), ('${OGR}', 'ogretmen@okul.k12.tr', now()),
      ('${SEF}', 'sef@okul.k12.tr', now()), ('${YENI}', 'yeni@okul.k12.tr', now()),
      ('${ONAYSIZ}', 'onaysiz@okul.k12.tr', NULL), ('${TMY}', 'tmy@okul.k12.tr', now()),
      ('${MERKEZ}', 'merkez@ornek.test', now());`);
  for (const f of fs.readdirSync(root).filter(f => f.endsWith('.sql') && (!sonDosya || f <= sonDosya)).sort()) {
    try { await db.exec(fs.readFileSync(root + f, 'utf8')); } catch (e) { e.message = `${f}: ${e.message}`; throw e; }
  }
  const as = async (u, sql, params = [], role = 'authenticated') => {
    await db.exec(`RESET ROLE; SELECT set_config('request.jwt.claim.sub', '${u || ''}', false); SET ROLE ${role};`);
    try { return (await db.query(sql, params)).rows; } finally { await db.exec('RESET ROLE'); }
  };
  const tek = async (u, sql, params) => (await as(u, sql, params))[0];
  const rpc = async (u, sql, params) => (await tek(u, `SELECT ${sql} AS r`, params)).r;
  const kod = async (ad, kurum) => (await db.query('SELECT dose_private.okul_ac($1, $2) k', [ad, kurum])).rows[0].k;
  return { db, as, tek, rpc, kod };
}

const reddet = (p, re) => assert.rejects(p, e => re.test(e.message) || re.test(e.hint || ''));

test('vendor license, activation, lockout and isolation between schools', async () => {
  const { db, as, rpc, kod } = await kur();
  await reddet(as(M1, "SELECT dose_private.okul_ac('Okul', '123456')"), /permission denied/);
  await reddet(as(null, "SELECT public.dose_okul_etkinlestir('x', '123456', 'Ali Veli')", [], 'anon'), /permission denied/);

  const k1 = await kod('Atatürk MTAL', '123456');
  assert.match(k1, /^DOSE(-[0-9A-F]{4}){6}$/);
  const etkin = (u, k, kk = '123456') => rpc(u, 'public.dose_okul_etkinlestir($1, $2, $3)', [k, kk, 'Ayşe Müdür']);

  await reddet(etkin(ONAYSIZ, k1), /doğrulanmadı/);
  await reddet(etkin(M1, k1, '12'), /5-8/);
  assert.equal((await etkin(M1, 'DOSE-YANLIS')).basarili, false);
  assert.equal((await db.query("SELECT hatali_deneme FROM dose_private.okul WHERE kurum_kodu='123456'")).rows[0].hatali_deneme, 1);
  assert.deepEqual(await etkin(M1, k1.toLowerCase().replace(/-/g, ' ')), { basarili: true, rol: 'Okul Müdürü', okul: 'Atatürk MTAL' });
  assert.equal((await etkin(M2, k1)).basarili, false, 'one-time code');
  await reddet(etkin(M1, k1), /zaten bir okula/);

  const ben = await rpc(M1, 'public.dose_ben()');
  assert.equal(ben.rol, 'Okul Müdürü');
  assert.equal(ben.okul.kurum_kodu, '123456');
  assert.equal(ben.yetkiler.kullanici, 'y');
  assert.equal(ben.yetkiler.ogrenci, 'g');
  assert.equal((await as(M1, 'SELECT okul_adi FROM public.kurum'))[0].okul_adi, 'Atatürk MTAL');

  // Lockout after five wrong attempts and expiry.
  const k2 = await kod('Cumhuriyet MTAL', '654321');
  for (let i = 0; i < 5; i++) await etkin(M2, 'DOSE-YANLIS', '654321');
  assert.equal((await etkin(M2, k2, '654321')).basarili, false);
  const k2b = (await db.query("SELECT dose_private.etkinlestirme_kodu('654321', interval '1 hour') k")).rows[0].k;
  await db.exec("UPDATE dose_private.okul SET kod_bitis = now() - interval '1 second' WHERE kurum_kodu = '654321'");
  assert.equal((await etkin(M2, k2b, '654321')).basarili, false);
  const k2c = (await db.query("SELECT dose_private.etkinlestirme_kodu('654321') k")).rows[0].k;
  assert.equal((await etkin(M2, k2c, '654321')).basarili, true);

  // Each school sees only its own rows; okul_id cannot be forged or moved.
  await as(M1, "INSERT INTO public.bolum (ad, utp_yontemi) VALUES ('Bilişim', 'Katkı oranına göre (md.5/7-c)')");
  await as(M2, "INSERT INTO public.bolum (ad, utp_yontemi) VALUES ('Elektrik', 'Katkı oranına göre (md.5/7-c)')");
  assert.deepEqual((await as(M1, 'SELECT ad FROM public.bolum')).map(r => r.ad), ['Bilişim']);
  assert.deepEqual((await as(M2, 'SELECT ad FROM public.kurum k JOIN public.bolum b ON b.okul_id = k.okul_id')).length, 1);
  const okul2 = (await db.query("SELECT id FROM dose_private.okul WHERE kurum_kodu='654321'")).rows[0].id;
  await reddet(as(M1, `INSERT INTO public.bolum (okul_id, ad, utp_yontemi) VALUES (${okul2}, 'X', 'Katkı oranına göre (md.5/7-c)')`), /row-level/);
  assert.equal((await as(M1, "UPDATE public.bolum SET ad='Y' WHERE ad='Elektrik' RETURNING id")).length, 0);
  await reddet(as(M1, `UPDATE public.bolum SET okul_id=${okul2}`), /row-level|değiştirilemez/);
  await reddet(as(M1, "UPDATE public.kurum SET kurum_kodu='999999'"), /permission denied/);

  // License expiry turns the school read-only; deactivation blocks access entirely.
  await db.query("SELECT dose_private.lisans_ayarla('123456', current_date - 1)");
  assert.equal((await rpc(M1, 'public.dose_ben()')).okul.salt_okunur, true);
  assert.equal((await rpc(M1, 'public.dose_ben()')).yetkiler.bolum, 'g');
  await reddet(as(M1, "INSERT INTO public.bolum (ad, utp_yontemi) VALUES ('Z', 'Katkı oranına göre (md.5/7-c)')"), /row-level/);
  assert.equal((await as(M1, 'SELECT ad FROM public.bolum')).length, 1);
  await db.query("SELECT dose_private.lisans_ayarla('123456', NULL, false)");
  assert.equal((await rpc(M1, 'public.dose_ben()')).okul_kapali, true);
  assert.equal((await as(M1, 'SELECT ad FROM public.bolum')).length, 0);
});

test('invitations, roles, workshop restriction and last-manager guard', async () => {
  const { db, as, rpc, kod } = await kur();
  await rpc(M1, 'public.dose_okul_etkinlestir($1, $2, $3)', [await kod('Atatürk MTAL', '123456'), '123456', 'Ayşe Müdür']);
  const yontem = 'Katkı oranına göre (md.5/7-c)';
  const [b1] = await as(M1, `INSERT INTO public.bolum (ad, utp_yontemi) VALUES ('Bilişim', '${yontem}'), ('Elektrik', '${yontem}') RETURNING id`);
  const b2 = (await as(M1, "SELECT id FROM public.bolum WHERE ad='Elektrik'"))[0].id;
  const [p1] = await as(M1, `INSERT INTO public.personel (ad_soyad, hizmet_sinifi, dose_gorevi, bolum_id)
    VALUES ('Can Öğretmen', 'Eğitim ve Öğretim Hizmetleri', 'Öğretmen', ${b1.id}) RETURNING id`);
  await as(M1, `INSERT INTO public.personel (ad_soyad, hizmet_sinifi, dose_gorevi, bolum_id)
    VALUES ('Diğer Bölüm', 'Eğitim ve Öğretim Hizmetleri', 'Öğretmen', ${b2})`);

  const davet = (e, r, b = null, p = null, u = M1) =>
    rpc(u, 'public.dose_kullanici_davet($1, $2, $3, $4, $5)', [e, 'Ad Soyad', r, b, p]);
  await reddet(davet('ogretmen@okul.k12.tr', 'Öğretmen'), /personel kaydına/);
  await reddet(davet('bozuk', 'Sayman'), /E-posta/);
  await davet(' Sayman@Okul.k12.tr ', 'Sayman');
  await davet('ogretmen@okul.k12.tr', 'Öğretmen', null, p1.id);
  await davet('sef@okul.k12.tr', 'Alan Şefi', b1.id);
  await davet('tmy@okul.k12.tr', 'Teknik Müdür Yardımcısı');
  assert.equal((await rpc(M1, 'public.dose_kullanicilar()')).davetler.length, 4);
  await reddet(davet('mudur1@okul.k12.tr', 'Sayman'), /zaten bir okul/);

  // Another school cannot steal a pending invitation.
  await rpc(M2, 'public.dose_okul_etkinlestir($1, $2, $3)', [await kod('Cumhuriyet MTAL', '654321'), '654321', 'Mehmet Müdür']);
  await reddet(davet('sayman@okul.k12.tr', 'Sayman', null, null, M2), /başka bir okuldan/);

  assert.equal((await rpc(SAY, 'public.dose_ben()')).rol, 'Sayman');
  assert.equal((await rpc(OGR, 'public.dose_ben()')).rol, 'Öğretmen');
  assert.equal((await rpc(SEF, 'public.dose_ben()')).rol, 'Alan Şefi');
  assert.equal((await rpc(YENI, 'public.dose_ben()')).uye, false);
  await reddet(as(YENI, "INSERT INTO public.cari (unvan, tur) VALUES ('X', 'Müşteri')"), /üyeliğiniz/);
  await reddet(rpc(SAY, 'public.dose_kullanicilar()'), /yetkiniz yok/);

  // Öğretmen sees only his workshop's students and cannot read personel.
  await rpc(TMY, 'public.dose_ben()');
  await reddet(as(M1, `INSERT INTO public.ogrenci (ad_soyad) VALUES ('Müdür yazamaz')`), /row-level/);
  await as(TMY, `INSERT INTO public.ogrenci (ad_soyad, bolum_id) VALUES ('Öğr A', ${b1.id}), ('Öğr B', ${b2})`);
  assert.deepEqual((await as(OGR, 'SELECT ad_soyad FROM public.ogrenci')).map(r => r.ad_soyad), ['Öğr A']);
  assert.equal((await as(OGR, 'SELECT id FROM public.personel')).length, 0);
  await reddet(as(OGR, `INSERT INTO public.ogrenci (ad_soyad, bolum_id) VALUES ('Öğr C', ${b1.id})`), /row-level/);
  await reddet(as(SEF, `INSERT INTO public.ogrenci (ad_soyad, bolum_id) VALUES ('Öğr C', ${b2})`), /row-level/);
  await as(SEF, `INSERT INTO public.ogrenci (ad_soyad, bolum_id) VALUES ('Öğr C', ${b1.id})`);
  assert.equal((await as(SEF, `UPDATE public.ogrenci SET bolum_id = ${b2}, surum = 1 WHERE ad_soyad = 'Öğr C' RETURNING id`).catch(e => e.message)).toString().includes('row-level'), true);
  assert.deepEqual((await as(SEF, 'SELECT ad_soyad FROM public.personel')).map(r => r.ad_soyad), ['Can Öğretmen']);
  await reddet(as(SAY, "UPDATE public.ogrenci SET notlar = 'x' RETURNING id").then(r => { if (!r.length) throw new Error('row-level'); }), /row-level/);

  // Last-manager guard and self-protection.
  await reddet(rpc(M1, 'public.dose_kullanici_guncelle($1, $2, $3, NULL, NULL, false)', [M1, 'Ayşe Müdür', 'Okul Müdürü']), /Kendi rolünüzü/);
  await rpc(M1, 'public.dose_kullanici_guncelle($1, $2, $3, NULL, NULL, true)', [SAY, 'Yeni Sayman', 'Okul Müdürü']);
  await rpc(SAY, 'public.dose_kullanici_guncelle($1, $2, $3, NULL, NULL, false)', [M1, 'Ayşe Müdür', 'Okul Müdürü']);
  await reddet(rpc(M2, 'public.dose_kullanici_guncelle($1, $2, $3, NULL, NULL, true)', [SAY, 'X Y Z', 'Sayman']), /bulunamadı/);
  assert.equal((await rpc(M1, 'public.dose_ben()')).pasif, true);
  await reddet(rpc(SAY, 'public.dose_kullanici_guncelle($1, $2, $3, NULL, NULL, true)', [SAY, 'Yeni Sayman', 'Sayman']), /Kendi rolünüzü/);
  await rpc(SAY, 'public.dose_kullanici_guncelle($1, $2, $3, NULL, NULL, true)', [M1, 'Ayşe Müdür', 'Okul Müdürü']);
  await rpc(SAY, 'public.dose_kullanici_guncelle($1, $2, $3, NULL, NULL, true)', [SAY, 'Yeni Sayman', 'Okul Müdürü']);
  await rpc(M1, 'public.dose_kullanici_guncelle($1, $2, $3, NULL, NULL, true)', [SAY, 'Yeni Sayman', 'Sayman']);
  await reddet(rpc(SAY, 'public.dose_kullanici_guncelle($1, $2, $3, NULL, NULL, false)', [M1, 'Ayşe Müdür', 'Okul Müdürü']), /yetkiniz yok/);
  await reddet(as(M1, 'SELECT * FROM dose_private.uyelik'), /permission denied/);
  assert.ok((await db.query("SELECT count(*)::int n FROM public.islem_log WHERE islem = 'Kullanıcı güncellendi'")).rows[0].n >= 4);
});

test('validation, version conflict, numbering, delete protection and append-only audit', async () => {
  const { db, as, rpc, kod } = await kur();
  await rpc(M1, 'public.dose_okul_etkinlestir($1, $2, $3)', [await kod('Atatürk MTAL', '123456'), '123456', 'Ayşe Müdür']);
  await rpc(M1, 'public.dose_kullanici_davet($1, $2, $3, NULL, NULL)', ['sayman@okul.k12.tr', 'Sena Sayman', 'Sayman']);
  await rpc(SAY, 'public.dose_ben()');
  await rpc(M1, 'public.dose_kullanici_davet($1, $2, $3, NULL, NULL)', ['tmy@okul.k12.tr', 'Tuna Yardımcı', 'Teknik Müdür Yardımcısı']);
  await rpc(TMY, 'public.dose_ben()');

  // Same vectors the removed Python validator (dose/dogrulama.py) was tested with.
  assert.deepEqual((await db.query(`SELECT dose_private.tckn_gecerli('10000000146') a, dose_private.tckn_gecerli('12345678901') b,
    dose_private.tckn_gecerli('01234567890') c, dose_private.vkn_gecerli('6210312482') d, dose_private.vkn_gecerli('6210312481') e,
    dose_private.vkn_gecerli('621031248') f, dose_private.iban_gecerli('TR02 0000 1001 0000 0350 1540 35') g,
    dose_private.iban_gecerli('TR00 0000 1001 0000 0350 1540 35') h`)).rows[0],
    { a: true, b: false, c: false, d: true, e: false, f: false, g: true, h: false });

  await reddet(as(M1, "INSERT INTO public.bolum (ad, utp_yontemi) VALUES ('  ',  'Katkı oranına göre (md.5/7-c)')"), /zorunludur/);
  await reddet(as(M1, "INSERT INTO public.bolum (ad, utp_yontemi) VALUES ('Bilişim', 'Uydurma')"), /ÜTP/);
  const ekle = (sql, u = /ogrenci|cari|malzeme|urun/.test(sql) ? TMY : M1) => as(u, sql);
  await reddet(ekle("INSERT INTO public.personel (ad_soyad, hizmet_sinifi, dose_gorevi, tckn) VALUES ('A B', 'Teknik Hizmetler', 'Sayman', '12345678901')"), /kimlik/);
  await reddet(ekle("INSERT INTO public.personel (ad_soyad, hizmet_sinifi, dose_gorevi, iban) VALUES ('A B', 'Teknik Hizmetler', 'Sayman', 'TR00')"), /IBAN/);
  const [p] = await ekle(`INSERT INTO public.personel (ad_soyad, hizmet_sinifi, dose_gorevi, tckn, iban)
    VALUES (' Sena Sayman ', 'Teknik Hizmetler', 'Sayman', '10000000146', 'tr33 0006 1005 1978 6457 8413 26') RETURNING *`);
  assert.equal(p.ad_soyad, 'Sena Sayman');
  assert.equal(p.iban, 'TR330006100519786457841326');
  assert.equal(p.surum, 1);
  assert.equal(p.guncelleyen, 'Ayşe Müdür (Okul Müdürü)');
  await reddet(ekle("INSERT INTO public.personel (ad_soyad, hizmet_sinifi, dose_gorevi) VALUES ('İkinci Sayman', 'Teknik Hizmetler', 'Sayman')"), /aktif başka personel/);
  await reddet(ekle("INSERT INTO public.ogrenci (ad_soyad, dogum_tarihi) VALUES ('Öğr', '2010-02-30')"), /Doğum tarihi/);
  await reddet(ekle("INSERT INTO public.ogrenci (ad_soyad, veli_muvafakat) VALUES ('Öğr', 1)"), /muvafakat tarihi/);
  await reddet(ekle("INSERT INTO public.cari (unvan, tur, vkn_tckn) VALUES ('Firma', 'Müşteri', '1234567891')"), /Vergi kimlik/);
  await reddet(ekle("INSERT INTO public.cari (unvan, tur, vkn_tckn) VALUES ('Çiftçi', 'Çiftçi (Müstahsil)', '0010000009')"), /Müstahsil/);
  await reddet(ekle("INSERT INTO public.malzeme (ad, tur, kdv_orani) VALUES ('Vida', 'Ticari Mal', 1.5)"), /aralık dışında/);

  // Database-issued, per-school cari numbers.
  const kodlar = [];
  for (const u of ['Firma A', 'Firma B']) kodlar.push((await ekle(`INSERT INTO public.cari (unvan, tur, vkn_tckn) VALUES ('${u}', 'Müşteri', '0010000009') RETURNING kod`))[0].kod);
  assert.deepEqual(kodlar, ['C0001', 'C0002']);

  // Optimistic concurrency: the second writer with the stale version is rejected and told who changed it.
  await as(SAY, `UPDATE public.personel SET telefon = '555' , surum = 1 WHERE id = ${p.id}`);
  await assert.rejects(as(M1, `UPDATE public.personel SET telefon = '444', surum = 1 WHERE id = ${p.id}`),
    e => e.code === 'P0001' && e.hint === 'surum_cakismasi' && /Sena Sayman \(Sayman\)/.test(e.message));
  const [g] = await as(M1, `UPDATE public.personel SET telefon = '444', surum = 2 WHERE id = ${p.id} RETURNING surum, telefon`);
  assert.deepEqual(g, { surum: 3, telefon: '444' });

  // Delete protection.
  const [m] = await ekle("INSERT INTO public.malzeme (ad, tur) VALUES ('Masa', 'Mamul') RETURNING id");
  await ekle(`INSERT INTO public.urun (ad, tur, mamul_malzeme_id) VALUES ('Masa', 'Mal', ${m.id})`);
  await reddet(ekle(`DELETE FROM public.malzeme WHERE id = ${m.id}`), /pasif yapınız/);
  await reddet(ekle("INSERT INTO public.urun (ad, tur, mamul_malzeme_id) VALUES ('X', 'Mal', 999999)"), /mamul kartı/);

  // Append-only audit with role and name, and the change counter used for live refresh.
  const log = await as(M1, "SELECT islem, tablo, rol, ad_soyad FROM public.islem_log WHERE tablo = 'personel' ORDER BY id");
  assert.deepEqual(log.map(r => [r.islem, r.rol]), [['Ekleme', 'Okul Müdürü'], ['Güncelleme', 'Sayman'], ['Güncelleme', 'Okul Müdürü']]);
  await reddet(as(M1, 'DELETE FROM public.islem_log'), /permission denied/);
  await reddet(db.query('DELETE FROM public.islem_log'), /değiştirilemez/);
  await reddet(db.query("UPDATE public.islem_log SET detay = 'x'"), /değiştirilemez/);
  assert.ok(Number(await rpc(SAY, 'public.dose_son_degisiklik()')) > 0);
  assert.equal(Number(await rpc(YENI, 'public.dose_son_degisiklik()')), 0);
  assert.deepEqual(await as(SAY, 'SELECT * FROM public.siparis'), []);
  assert.ok((await as(SAY, "SELECT deger FROM public.secenek WHERE liste = 'birim'")).length === 17);
});

test('order drafts, section isolation and staged approvals', async () => {
  const { db, as, rpc, kod } = await kur();
  await rpc(M1, 'public.dose_okul_etkinlestir($1, $2, $3)', [await kod('Atatürk MTAL', '123456'), '123456', 'Ayşe Müdür']);
  const [bolum] = await as(M1, `INSERT INTO public.bolum (ad, utp_yontemi)
    VALUES ('Mobilya', 'Katkı oranına göre (md.5/7-c)') RETURNING id`);
  const [personel] = await as(M1, `INSERT INTO public.personel (ad_soyad, hizmet_sinifi, dose_gorevi, bolum_id)
    VALUES ('Öğretmen', 'Eğitim ve Öğretim Hizmetleri', 'Öğretmen', ${bolum.id}) RETURNING id`);

  await rpc(M1, 'public.dose_kullanici_davet($1, $2, $3, $4, $5)',
    ['ogretmen@okul.k12.tr', 'Öğretmen', 'Öğretmen', bolum.id, personel.id]);
  await rpc(M1, 'public.dose_kullanici_davet($1, $2, $3, $4, NULL)',
    ['sef@okul.k12.tr', 'Alan Şefi', 'Alan Şefi', bolum.id]);
  await rpc(M1, 'public.dose_kullanici_davet($1, $2, $3, NULL, NULL)',
    ['tmy@okul.k12.tr', 'Teknik Müdür Yardımcısı', 'Teknik Müdür Yardımcısı']);
  await rpc(OGR, 'public.dose_ben()');
  await rpc(SEF, 'public.dose_ben()');
  await rpc(TMY, 'public.dose_ben()');
  const [cari] = await as(TMY, `INSERT INTO public.cari (unvan, tur) VALUES ('Okul Aile Birliği', 'Müşteri') RETURNING id`);
  const [urun] = await as(TMY, `INSERT INTO public.urun (ad, tur, birim, bolum_id, satis_fiyati)
    VALUES ('Kitaplık', 'Mal', 'Adet', ${bolum.id}, 50) RETURNING id`);

  const meta = await rpc(OGR, 'public.dose_siparis_veri()');
  assert.deepEqual(meta.bolumler.map(b => b.id), [bolum.id]);
  assert.equal(meta.urunler[0].id, urun.id);
  const siparis = await rpc(OGR,
    'public.dose_siparis_kaydet($1, $2, $3, $4)',
    [null, null, { tarih: '2026-10-31', cari_id: cari.id, bolum_id: bolum.id,
      konu: 'Kitaplık üretimi', ucret_esasi: 'Parça Başı Ücret (Yön. md.8)', kdv_orani: 0.2 },
    [{ urun_id: urun.id, miktar: 2, birim_fiyat: 50, iskonto_orani: 0.1 }]]);
  assert.equal(siparis.sozlesme_bedeli, 90);
  assert.equal(siparis.surum, 1);
  await assert.rejects(rpc(OGR, 'public.dose_siparis_kaydet($1, $2, $3, $4)',
    [null, null, { tarih: '2026-10-31', cari_id: cari.id, bolum_id: bolum.id,
      konu: 'Geçersiz sipariş', ucret_esasi: 'Parça Başı Ücret (Yön. md.8)' },
    [{ urun_id: urun.id, miktar: 0, birim_fiyat: 20 }]]), /miktar pozitif/);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.siparis')).rows[0].n, 1,
    'a failed multi-row write leaves no partial order');
  await assert.rejects(rpc(OGR, 'public.dose_siparis_kaydet($1, $2, $3, $4)',
    [siparis.id, 1, { tarih: '2026-10-31', cari_id: cari.id, bolum_id: bolum.id,
      konu: 'Geçersiz güncelleme', ucret_esasi: 'Parça Başı Ücret (Yön. md.8)' },
    [{ urun_id: urun.id, miktar: 0, birim_fiyat: 20 }]]), /miktar pozitif/);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.siparis_kalem WHERE siparis_id = $1', [siparis.id])).rows[0].n, 1,
    'a failed update preserves the previous lines');
  await assert.rejects(rpc(OGR, 'public.dose_siparis_kaydet($1, $2, $3, $4)',
    [siparis.id, 0, { tarih: '2026-10-31', cari_id: cari.id, bolum_id: bolum.id,
      konu: 'Eski sürüm', ucret_esasi: 'Parça Başı Ücret (Yön. md.8)' },
    [{ urun_id: urun.id, miktar: 1, birim_fiyat: 20 }]]),
  e => e.code === 'P0001' && e.hint === 'surum_cakismasi');
  await assert.rejects(as(OGR, `INSERT INTO public.siparis (konu) VALUES ('RLS dışı')`), /permission denied/);

  assert.equal((await rpc(OGR, 'public.dose_siparisler()'))[0].kalemler[0].iskonto, 10);
  const gonderildi = await rpc(OGR, 'public.dose_siparis_gonder($1, $2, $3)', [siparis.id, 'İş talebi', 1]);
  assert.deepEqual(gonderildi, { basarili: true, asama: 1, durum: 'Onay Bekliyor' });
  await assert.rejects(rpc(TMY, 'public.dose_siparis_karar($1, $2, $3, $4)', [siparis.id, true, '', 2]),
    /yalnız Alan Şefi/);
  assert.deepEqual(await rpc(SEF, 'public.dose_siparis_karar($1, $2, $3, $4)', [siparis.id, true, '', 2]), {
    basarili: true, asama: 2, durum: 'Onay Bekliyor'
  });
  await assert.rejects(rpc(TMY, 'public.dose_siparis_karar($1, $2, $3, $4)', [siparis.id, false, '', 3]),
    /İade gerekçesini/);
  assert.deepEqual(await rpc(TMY, 'public.dose_siparis_karar($1, $2, $3, $4)', [siparis.id, false, 'Fiyat teklifi ekleyin.', 3]),
    { basarili: true, durum: 'İade Edildi' });
  assert.equal((await rpc(OGR, 'public.dose_siparisler()'))[0].durum, 'İade Edildi');

  const guncel = await rpc(OGR, 'public.dose_siparis_kaydet($1, $2, $3, $4)',
    [siparis.id, 4, { tarih: '2026-10-31', cari_id: cari.id, bolum_id: bolum.id,
      konu: 'Kitaplık üretimi (güncel)', ucret_esasi: 'Parça Başı Ücret (Yön. md.8)', kdv_orani: 0.2 },
    [{ urun_id: urun.id, miktar: 2, birim_fiyat: 50, iskonto_orani: 0.1 }]]);
  assert.equal(guncel.surum, 5);
  await rpc(OGR, 'public.dose_siparis_gonder($1, $2, $3)', [siparis.id, 'Tekrar gönderildi', 5]);
  await rpc(SEF, 'public.dose_siparis_karar($1, $2, $3, $4)', [siparis.id, true, '', 6]);
  await rpc(TMY, 'public.dose_siparis_karar($1, $2, $3, $4)', [siparis.id, true, 'Kontrol edildi', 7]);
  assert.deepEqual(await rpc(M1, 'public.dose_siparis_karar($1, $2, $3, $4)', [siparis.id, true, '', 8]), {
    basarili: true, durum: 'Onaylandı'
  });
  const son = (await rpc(M1, 'public.dose_siparisler()'))[0];
  assert.equal(son.durum, 'Sözleşme İmzalandı');
  assert.equal(son.gecmis.length, 7);
  assert.equal((await db.query(`SELECT count(*)::int AS n FROM public.yevmiye WHERE kaynak = 'siparis' AND kaynak_id = ${siparis.id}`)).rows[0].n, 0,
    'approval does not post income/expense before a source document');
  await assert.rejects(as(SEF, `UPDATE public.onay_kaydi SET karar = 'Silindi' WHERE belge_id = ${siparis.id}`),
    /permission denied/);
  const otherSchool = await kod('Cumhuriyet MTAL', '654321');
  await rpc(M2, 'public.dose_okul_etkinlestir($1, $2, $3)', [otherSchool, '654321', 'Mehmet Müdür']);
  assert.deepEqual(await rpc(M2, 'public.dose_siparisler()'), []);
});

async function siparisOrtami(sonDosya = null) {
  const ortam = await kur(sonDosya);
  const { as, rpc, kod } = ortam;
  await rpc(M1, 'public.dose_okul_etkinlestir($1, $2, $3)', [await kod('Test Okulu', '111111'), '111111', 'Ayşe Müdür']);
  const [bolum] = await as(M1, `INSERT INTO public.bolum (ad, utp_yontemi)
    VALUES ('Mobilya', 'Katkı oranına göre (md.5/7-c)') RETURNING id`);
  const [personel] = await as(M1, `INSERT INTO public.personel (ad_soyad, hizmet_sinifi, dose_gorevi, bolum_id)
    VALUES ('Öğretmen', 'Eğitim ve Öğretim Hizmetleri', 'Öğretmen', ${bolum.id}) RETURNING id`);
  await rpc(M1, 'public.dose_kullanici_davet($1, $2, $3, $4, $5)',
    ['ogretmen@okul.k12.tr', 'Öğretmen', 'Öğretmen', bolum.id, personel.id]);
  await rpc(M1, 'public.dose_kullanici_davet($1, $2, $3, $4, NULL)',
    ['sef@okul.k12.tr', 'Alan Şefi', 'Alan Şefi', bolum.id]);
  await rpc(M1, 'public.dose_kullanici_davet($1, $2, $3, NULL, NULL)',
    ['tmy@okul.k12.tr', 'Teknik Müdür Yardımcısı', 'Teknik Müdür Yardımcısı']);
  for (const u of [OGR, SEF, TMY]) await rpc(u, 'public.dose_ben()');
  const [cari] = await as(TMY, `INSERT INTO public.cari (unvan, tur)
    VALUES ('Müşteri', 'Müşteri') RETURNING id`);
  const veri = { tarih: '2026-10-31', cari_id: cari.id, bolum_id: bolum.id,
    konu: 'Test işi', ucret_esasi: 'Parça Başı Ücret (Yön. md.8)', kdv_orani: 0.2 };
  const kaydet = (u, kalem = { aciklama: 'İş', miktar: 2, birim_fiyat: 50 }) =>
    rpc(u, 'public.dose_siparis_kaydet($1, $2, $3, $4)', [null, null, veri, [kalem]]);
  const bul = async (u, id) => (await rpc(u, 'public.dose_siparisler()')).find(s => s.id === id);
  const gonder = async (u, id, sur = undefined) =>
    rpc(u, 'public.dose_siparis_gonder($1, $2, $3)', [id, '', sur === undefined ? (await bul(u, id)).surum : sur]);
  const karar = async (u, id, onay, sur = undefined) =>
    rpc(u, 'public.dose_siparis_karar($1, $2, $3, $4)', [id, onay, '', sur === undefined ? (await bul(u, id)).surum : sur]);
  const geriCek = async (u, id, sur = undefined) =>
    rpc(u, 'public.dose_siparis_geri_cek($1, $2, $3)', [id, '', sur === undefined ? (await bul(u, id)).surum : sur]);
  return { ...ortam, veri, kaydet, gonder, karar, geriCek, bul };
}

test('preparer approval only advances when earlier approval stages are complete', async () => {
  const { kaydet, gonder, karar, bul } = await siparisOrtami();
  const managerOrder = await kaydet(M1);
  assert.equal((await gonder(M1, managerOrder.id)).asama, 1, 'manager cannot bypass chief and deputy');
  assert.equal((await bul(M1, managerOrder.id)).durum, 'Onay Bekliyor');
  assert.equal((await karar(SEF, managerOrder.id, true)).asama, 2);
  assert.equal((await karar(TMY, managerOrder.id, true)).durum, 'Onaylandı');
  const managerHistory = (await bul(M1, managerOrder.id)).gecmis;
  assert.deepEqual(managerHistory.map(a => a.asama), [0, 1, 2, 3]);
  assert.equal(managerHistory[3].karar, 'Uygun (hazırlayan)');

  const deputyOrder = await kaydet(TMY);
  assert.equal((await gonder(TMY, deputyOrder.id)).asama, 1, 'deputy cannot bypass chief');
  assert.equal((await karar(SEF, deputyOrder.id, true)).asama, 3, 'deputy stage is recorded after chief');
  assert.equal((await karar(M1, deputyOrder.id, true)).durum, 'Onaylandı');
  assert.deepEqual((await bul(M1, deputyOrder.id)).gecmis.map(a => a.asama), [0, 1, 2, 3]);
});

test('approval requires an explicit decision and a writable license', async () => {
  const { db, kaydet, gonder, karar, geriCek, bul } = await siparisOrtami();
  const siparis = await kaydet(OGR);
  await gonder(OGR, siparis.id);
  await assert.rejects(karar(SEF, siparis.id, null), /onay.*karar|karar.*zorunlu/i);
  assert.equal((await bul(OGR, siparis.id)).onay_asamasi, 1);
  await db.query("SELECT dose_private.lisans_ayarla('111111', '2020-01-01', TRUE)");
  await assert.rejects(karar(SEF, siparis.id, true), /lisans|yetki/i);
  await assert.rejects(geriCek(OGR, siparis.id), /lisans|yetki/i);
  assert.equal((await bul(OGR, siparis.id)).onay_asamasi, 1);
});

test('order discount uses the same rounded gross amount as the client', async () => {
  const { kaydet, bul } = await siparisOrtami();
  const siparis = await kaydet(OGR, { aciklama: 'Kuruş testi', miktar: 1, birim_fiyat: 1.005, iskonto_orani: 0.5 });
  assert.equal(siparis.sozlesme_bedeli, 0.50);
  const kayit = await bul(OGR, siparis.id);
  assert.equal(kayit.kalemler[0].iskonto, 0.51);
});

test('approval transitions invalidate stale draft versions', async () => {
  const { kaydet, gonder, karar, geriCek, bul, rpc, veri } = await siparisOrtami();
  const siparis = await kaydet(OGR);
  await assert.rejects(rpc(OGR, 'public.dose_siparis_gonder($1, $2)', [siparis.id, '']), /güncelleyin/i);
  await gonder(OGR, siparis.id);
  assert.equal((await bul(OGR, siparis.id)).surum, 2);
  await assert.rejects(karar(SEF, siparis.id, true, 1), e => e.hint === 'surum_cakismasi');
  await geriCek(OGR, siparis.id);
  assert.equal((await bul(OGR, siparis.id)).surum, 3);
  await assert.rejects(rpc(OGR, 'public.dose_siparis_kaydet($1, $2, $3, $4)',
    [siparis.id, 1, veri, [{ aciklama: 'Eski taslak', miktar: 1, birim_fiyat: 10 }]]),
  e => e.hint === 'surum_cakismasi');
  await gonder(OGR, siparis.id, 3);
  await assert.rejects(karar(SEF, siparis.id, true, 2), e => e.hint === 'surum_cakismasi');
});

test('section-restricted users cannot mutate orders after reassignment', async () => {
  const { db, as, kaydet, gonder, geriCek, rpc, veri } = await siparisOrtami();
  const taslak = await kaydet(OGR);
  const bekleyen = await kaydet(OGR);
  await gonder(OGR, bekleyen.id);
  const [diger] = await as(M1, `INSERT INTO public.bolum (ad, utp_yontemi)
    VALUES ('Elektrik', 'Katkı oranına göre (md.5/7-c)') RETURNING id`);
  await db.query('UPDATE dose_private.uyelik SET bolum_id = $1 WHERE auth_user_id = $2', [diger.id, OGR]);
  assert.deepEqual(await rpc(OGR, 'public.dose_siparisler()'), []);
  await assert.rejects(gonder(OGR, taslak.id, 1), /bölüm|yetki/i);
  await assert.rejects(rpc(OGR, 'public.dose_siparis_kaydet($1, $2, $3, $4)',
    [taslak.id, 1, { ...veri, bolum_id: diger.id }, [{ aciklama: 'İş', miktar: 1, birim_fiyat: 10 }]]),
  /bölüm|yetki/i);
  await assert.rejects(geriCek(OGR, bekleyen.id, 2), /bölüm|yetki/i);
});

test('order inputs reject non-finite numeric values', async () => {
  const { kaydet, rpc, veri } = await siparisOrtami();
  for (const deger of ['NaN', 'Infinity', '-Infinity']) {
    await assert.rejects(kaydet(OGR, { aciklama: 'İş', miktar: deger, birim_fiyat: 10 }), /geçerli|sonlu/i);
    await assert.rejects(rpc(OGR, 'public.dose_siparis_kaydet($1, $2, $3, $4)',
      [null, null, { ...veri, kdv_orani: deger }, [{ aciklama: 'İş', miktar: 1, birim_fiyat: 10 }]]),
    /KDV|sonlu/i);
  }
});

test('outdated draft totals must be recalculated before submission', async () => {
  const { db, kaydet, gonder, rpc, veri } = await siparisOrtami();
  const siparis = await kaydet(OGR, { aciklama: 'Kuruş testi', miktar: 1, birim_fiyat: 1.005, iskonto_orani: 0.5 });
  await db.query('UPDATE public.siparis_kalem SET iskonto = 0.50 WHERE siparis_id = $1', [siparis.id]);
  await db.query('UPDATE public.siparis SET sozlesme_bedeli = 0.51 WHERE id = $1', [siparis.id]);
  await assert.rejects(gonder(OGR, siparis.id), /taslağı yeniden kaydedin/i);
  await rpc(OGR, 'public.dose_siparis_kaydet($1, $2, $3, $4)',
    [siparis.id, 1, veri, [{ aciklama: 'Kuruş testi', miktar: 1, birim_fiyat: 1.005, iskonto_orani: 0.5 }]]);
  assert.equal((await gonder(OGR, siparis.id)).asama, 1);
});

test('legacy incomplete pending approvals must be withdrawn and resubmitted', async () => {
  const { db, kaydet, rpc, bul } = await siparisOrtami('20261031000000_siparis_onay.sql');
  const siparis = await kaydet(TMY);
  assert.equal((await rpc(TMY, 'public.dose_siparis_gonder($1, $2)', [siparis.id, ''])).asama, 3);
  await db.exec(fs.readFileSync(root + '20261031000100_siparis_guvenligi.sql', 'utf8'));
  await assert.rejects(rpc(M1, 'public.dose_siparis_karar($1, $2, $3, $4)', [siparis.id, true, '', 1]),
    /Önceki onaylar eksik/i);
  await rpc(TMY, 'public.dose_siparis_geri_cek($1, $2, $3)', [siparis.id, '', 1]);
  assert.equal((await rpc(TMY, 'public.dose_siparis_gonder($1, $2, $3)', [siparis.id, '', 2])).asama, 1);
  assert.equal((await bul(TMY, siparis.id)).durum, 'Onay Bekliyor');
});

test('legacy final approvals with missing stages stop the migration', async () => {
  const { db, kaydet, rpc } = await siparisOrtami('20261031000000_siparis_onay.sql');
  const siparis = await kaydet(M1);
  assert.equal((await rpc(M1, 'public.dose_siparis_gonder($1, $2)', [siparis.id, ''])).durum, 'Onaylandı');
  await assert.rejects(db.exec(fs.readFileSync(root + '20261031000100_siparis_guvenligi.sql', 'utf8')),
    /eksik veya sırasız onaylanmış eski siparişler/i);
});

test('legacy approved totals that disagree with the preview stop the migration', async () => {
  const { db, kaydet, rpc } = await siparisOrtami('20261031000000_siparis_onay.sql');
  const siparis = await kaydet(OGR, { aciklama: 'Kuruş testi', miktar: 1, birim_fiyat: 1.005, iskonto_orani: 0.5 });
  await rpc(OGR, 'public.dose_siparis_gonder($1, $2)', [siparis.id, '']);
  await rpc(SEF, 'public.dose_siparis_karar($1, $2, $3)', [siparis.id, true, '']);
  await rpc(TMY, 'public.dose_siparis_karar($1, $2, $3)', [siparis.id, true, '']);
  await rpc(M1, 'public.dose_siparis_karar($1, $2, $3)', [siparis.id, true, '']);
  await assert.rejects(db.exec(fs.readFileSync(root + '20261031000100_siparis_guvenligi.sql', 'utf8')),
    /onaylı siparişlerde tutar uyuşmazlığı/i);
});

test('revoked preparer membership is not auto-approved later', async () => {
  const { db, kaydet, gonder, karar, bul } = await siparisOrtami();
  const siparis = await kaydet(TMY);
  await gonder(TMY, siparis.id);
  await db.query('UPDATE dose_private.uyelik SET aktif = false WHERE auth_user_id = $1', [TMY]);
  assert.equal((await karar(SEF, siparis.id, true)).asama, 2);
  assert.deepEqual((await bul(M1, siparis.id)).gecmis.map(a => a.asama), [0, 1]);
});

async function finansOrtami() {
  const ortam = await kur();
  const { as, rpc, kod } = ortam;
  await rpc(M1, 'public.dose_okul_etkinlestir($1, $2, $3)', [await kod('Finans Okulu', '111111'), '111111', 'Ayşe Müdür']);
  await rpc(M2, 'public.dose_okul_etkinlestir($1, $2, $3)', [await kod('Diğer Okul', '222222'), '222222', 'Mehmet Müdür']);
  await rpc(M1, 'public.dose_kullanici_davet($1, $2, $3, NULL, NULL)', ['sayman@okul.k12.tr', 'Sena Sayman', 'Sayman']);
  await rpc(SAY, 'public.dose_ben()');
  const [malzeme] = await as(SAY, `INSERT INTO public.malzeme (ad, tur, birim)
    VALUES ('Tahta', 'İlk Madde ve Malzeme', 'Adet') RETURNING id`);
  const hareket = (u, yon, miktar, tutar, hesap, istek, malzemeId = malzeme.id) =>
    rpc(u, 'public.dose_stok_kaydet($1, $2, $3, $4, $5, $6, $7, $8)',
      [malzemeId, '2020-01-01', yon, miktar, tutar, hesap, 'Test hareketi', istek]);
  const tersle = (id, istek, u = SAY) =>
    rpc(u, 'public.dose_stok_tersle($1, $2, $3)', [id, 'Kayıt düzeltmesi', istek]);
  return { ...ortam, malzeme, hareket, tersle };
}

test('finance configuration is school-scoped, versioned and writable only by an active treasurer', async () => {
  const { db, rpc } = await finansOrtami();
  await reddet(rpc(M1, 'public.dose_hesap_ekle($1, $2)', ['193', 'Özel hesap']), /sayman/);
  await reddet(rpc(SAY, 'public.dose_hesap_ekle($1, $2)', ['193x', 'Hatalı hesap']), /hesap kodu/);
  await rpc(SAY, 'public.dose_hesap_ekle($1, $2)', ['193', 'Saymanın belirlediği hesap']);
  const ayarla = (tur, hesap, sur) => rpc(SAY, 'public.dose_vergi_hesabi_kaydet($1, $2, $3)', [tur, hesap, sur]);
  const yeni = await ayarla('Satış stopajı', '193', null);
  assert.equal(yeni.surum, 1);
  assert.equal((await ayarla('Satış stopajı', '360', 1)).surum, 2);
  await reddet(ayarla('Satış stopajı', '193', 1), /güncelini yükleyin|surum_cakismasi/);
  await reddet(ayarla('Satış KDV tevkifatı', '999', null), /tanımlı hesap/);
  assert.equal((await rpc(M1, 'public.dose_finans_tanimlari()')).vergi_hesaplari[0].hesap_kodu, '360');
  const diger = await rpc(M2, 'public.dose_finans_tanimlari()');
  assert.deepEqual(diger.vergi_hesaplari, []);
  assert.ok(!diger.hesaplar.some(h => h.kod === '193'));
  await db.query("SELECT dose_private.lisans_ayarla('111111', current_date - 1)");
  await reddet(ayarla('Satış stopajı', '193', 2), /sayman/);
  assert.equal((await rpc(SAY, 'public.dose_finans_tanimlari()')).vergi_hesaplari[0].hesap_kodu, '360');
});

test('stock postings are atomic, balanced, school isolated, precise and treasurer authorized', async () => {
  const { db, as, rpc, malzeme, hareket } = await finansOrtami();
  await reddet(hareket(M1, 'Giriş', '10', '100', '500', uid(101)), /sayman/);
  await reddet(hareket(SAY, 'Giriş', 'NaN', '100', '500', uid(102)), /miktar/);
  await reddet(hareket(SAY, 'Giriş', '10', '100.001', '500', uid(103)), /maliyet/);
  await reddet(hareket(SAY, 'Giriş', '10', '100', '150', uid(104)), /aynı olamaz/);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.stok_hareket')).rows[0].n, 0,
    'a failed journal leaves no stock movement');
  const giris = await hareket(SAY, 'Giriş', '10', '9007199254740993.99', '500', uid(105));
  await reddet(hareket(SAY, 'Giriş', '10', '9007199254740993.99', '500', uid(105)), /daha önce/);
  await reddet(hareket(M2, 'Çıkış', '1', '1', '710', uid(106), malzeme.id), /sayman/);
  await rpc(M2, 'public.dose_kullanici_davet($1, $2, $3, NULL, NULL)', ['yeni@okul.k12.tr', 'Diğer Sayman', 'Sayman']);
  await rpc(YENI, 'public.dose_ben()');
  await reddet(hareket(YENI, 'Çıkış', '1', '1', '710', uid(110), malzeme.id), /stok kartı bulunamadı/);
  await reddet(rpc(SAY, `public.dose_stok_kaydet($1, current_date + 1, 'Giriş', 1, 1, '500', 'Gelecek', $2)`,
    [malzeme.id, uid(111)]), /İleri tarihli/);
  await reddet(hareket(SAY, 'Çıkış', '11', '1', '710', uid(107)), /yetersiz/);
  await reddet(hareket(SAY, 'Çıkış', '10', '1', '710', uid(108)), /kalan stok değerine/);
  const cikis = await hareket(SAY, 'Çıkış', '3', '23.99', '710', uid(109));
  const veri = await rpc(SAY, 'public.dose_stok_veri()');
  assert.equal(veri.kartlar[0].miktar, '7');
  assert.equal(veri.kartlar[0].tutar, '9007199254740970.00');
  assert.deepEqual((await rpc(M2, 'public.dose_stok_veri()')).kartlar, []);
  const yevmiye = await rpc(SAY, 'public.dose_yevmiye_veri()');
  assert.equal(yevmiye.length, 2);
  assert.deepEqual(yevmiye.find(f => f.id === cikis.yevmiye_id).satirlar.map(s => [s.hesap_kodu, s.borc, s.alacak]),
    [['150', '0', '23.99'], ['710', '23.99', '0']]);
  assert.deepEqual(yevmiye.find(f => f.id === giris.yevmiye_id).satirlar.map(s => [s.hesap_kodu, s.borc, s.alacak]),
    [['150', '9007199254740993.99', '0'], ['500', '0', '9007199254740993.99']]);
  const mizan = await rpc(SAY, 'public.dose_mizan_veri()');
  assert.equal(mizan.find(s => s.hesap_kodu === '150').bakiye, '9007199254740970.00');
  assert.deepEqual(await rpc(M2, 'public.dose_mizan_veri()'), []);
  await reddet(as(SAY, 'UPDATE public.stok_hareket SET miktar = 1'), /permission denied/);
  await reddet(db.query('UPDATE public.yevmiye_satir SET borc = 1'), /değiştirilemez/);
  await reddet(as(SAY, 'UPDATE public.malzeme SET tur = $1, surum = surum WHERE id = $2',
    ['Ticari Mal', malzeme.id]), /tür|birim/);
  await reddet(as(SAY, 'UPDATE public.malzeme SET birim = $1, surum = surum WHERE id = $2',
    ['Kg', malzeme.id]), /tür|birim/);
});

test('reversals unwind the latest open stock movements and permit explicit zero cost', async () => {
  const { as, rpc, malzeme, hareket, tersle } = await finansOrtami();
  const giris = await hareket(SAY, 'Giriş', '10', '100', '500', uid(201));
  const cikis = await hareket(SAY, 'Çıkış', '3', '100', '710', uid(202));
  const bedelsiz = await hareket(SAY, 'Çıkış', '2', '0', '710', uid(203));
  assert.equal(bedelsiz.yevmiye_id, null);
  await reddet(tersle(giris.id, uid(204)), /daha yeni/);
  await tersle(bedelsiz.id, uid(205));
  await tersle(cikis.id, uid(206));
  await as(SAY, 'UPDATE public.malzeme SET aktif = 0, surum = surum WHERE id = $1', [malzeme.id]);
  const pasif = (await rpc(SAY, 'public.dose_stok_veri()')).kartlar[0];
  assert.equal(pasif.aktif, 0);
  assert.equal(pasif.miktar, '10');
  await tersle(giris.id, uid(207));
  await reddet(tersle(giris.id, uid(208)), /daha önce/);
  const veri = await rpc(SAY, 'public.dose_stok_veri()');
  assert.equal(veri.hareketler.length, 6);
  const [bakiye] = await as(SAY, 'SELECT id FROM public.malzeme WHERE id = $1', [malzeme.id]);
  assert.equal(bakiye.id, malzeme.id);
  const fisler = await rpc(SAY, 'public.dose_yevmiye_veri()');
  assert.equal(fisler.length, 4, 'zero-cost movements do not create an empty journal');
  for (const fis of fisler) {
    const borc = fis.satirlar.reduce((toplam, s) => toplam + Number(s.borc), 0);
    const alacak = fis.satirlar.reduce((toplam, s) => toplam + Number(s.alacak), 0);
    assert.equal(borc, alacak);
  }
});

async function faturaOrtami() {
  const ortam = await siparisOrtami();
  const { db, rpc, kod } = ortam;
  await rpc(M1, 'public.dose_kullanici_davet($1, $2, $3, NULL, NULL)', ['sayman@okul.k12.tr', 'Sena Sayman', 'Sayman']);
  await rpc(SAY, 'public.dose_ben()');
  await rpc(M2, 'public.dose_okul_etkinlestir($1, $2, $3)', [await kod('Diğer Okul', '222222'), '222222', 'Diğer Müdür']);
  const tarih = (await db.query("SELECT (now() AT TIME ZONE 'Europe/Istanbul')::date::text AS t")).rows[0].t;
  ortam.veri.tarih = tarih;
  const args = p => [p.tur, p.no, p.tarih, p.cari, p.siparis, p.kalemler, p.tevkifat, p.stopaj, p.surumler];
  const onizle = (u, p) => rpc(u, 'public.dose_fatura_onizle($1,$2,$3,$4,$5,$6,$7,$8,$9)', args(p));
  const kaydetFatura = (u, p, imza, istek) =>
    rpc(u, 'public.dose_fatura_kaydet($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)', [...args(p), imza, istek]);
  const tersleFatura = (id, istek, u = SAY) =>
    rpc(u, 'public.dose_fatura_tersle($1,$2,$3)', [id, 'Yanlış kayıt', istek]);
  return { ...ortam, tarih, onizle, kaydetFatura, tersleFatura };
}

test('partial sales allocate cents to the exact order line and stale previews are rejected', async () => {
  const { db, rpc, veri, kaydet, gonder, karar, tarih, onizle, kaydetFatura, tersleFatura } = await faturaOrtami();
  const siparis = await kaydet(SEF, { aciklama: 'İş', miktar: '3', birim_fiyat: '0.03', iskonto_orani: '0.5' });
  const draft = { tur: 'Satış', no: 'S-1', tarih, cari: veri.cari_id, siparis: siparis.id,
    kalemler: [], tevkifat: '0', stopaj: '0', surumler: {} };
  await reddet(onizle(SAY, draft), /kalemleri/);
  const [satir] = (await db.query('SELECT id FROM public.siparis_kalem WHERE siparis_id = $1', [siparis.id])).rows;
  draft.kalemler = [{ siparis_kalem_id: satir.id, miktar: '1', malzeme_id: null }];
  await reddet(onizle(SAY, draft), /onaylanmış sipariş/);
  await gonder(SEF, siparis.id);
  await karar(TMY, siparis.id, true);
  await karar(M1, siparis.id, true);
  await reddet(onizle(M1, draft), /sayman/);
  await reddet(onizle(M2, draft), /sayman/);
  await reddet(onizle(SAY, { ...draft, kalemler: [...draft.kalemler, ...draft.kalemler] }), /yalnız bir kez/);

  const ilk = await onizle(SAY, draft);
  const bayat = await onizle(SAY, { ...draft, no: 'S-2' });
  assert.equal(ilk.detay.matrah, '0.01');
  const f1 = await kaydetFatura(SAY, draft, ilk.imza, uid(301));
  await reddet(kaydetFatura(SAY, draft, ilk.imza, uid(301)), /daha önce/);
  const ayniBelge = await onizle(SAY, { ...draft, no: ' s-1 ' });
  await reddet(kaydetFatura(SAY, { ...draft, no: ' s-1 ' }, ayniBelge.imza, uid(309)), /belge numarası/);
  await reddet(onizle(SAY, { ...draft, tevkifat: 'NaN' }), /vergi oranları/);
  const ikinci = { ...draft, no: 'S-2' };
  await reddet(kaydetFatura(SAY, ikinci, bayat.imza, uid(302)), /yeniden önizleyin|surum_cakismasi/);
  const o2 = await onizle(SAY, ikinci);
  assert.equal(o2.detay.matrah, '0.02');
  const f2 = await kaydetFatura(SAY, ikinci, o2.imza, uid(302));
  const ucuncu = { ...draft, no: 'S-3' };
  const o3 = await onizle(SAY, ucuncu);
  assert.equal(o3.detay.matrah, '0.01');
  const f3 = await kaydetFatura(SAY, ucuncu, o3.imza, uid(303));
  await reddet(onizle(SAY, { ...draft, no: 'S-4' }), /kalanını aşıyor/);
  const [toplam] = (await db.query(`SELECT sum(k.miktar)::text AS miktar, sum(k.tutar)::text AS matrah,
    sum(k.kdv)::text AS kdv FROM public.fatura_kalem k JOIN public.fatura f ON f.id = k.fatura_id
    WHERE f.siparis_id = $1 AND f.iptal = 0`, [siparis.id])).rows;
  assert.deepEqual(toplam, { miktar: '3', matrah: '0.04', kdv: '0.01' });
  assert.deepEqual(await rpc(M2, 'public.dose_faturalar()'), []);
  await reddet(tersleFatura(f1.id, uid(304)), /daha yeni faturalar/);
  await tersleFatura(f3.id, uid(305));
  await tersleFatura(f2.id, uid(306));
  await tersleFatura(f1.id, uid(307));
  await reddet(tersleFatura(f1.id, uid(308)), /daha önce/);
  await reddet(db.query('UPDATE public.fatura SET matrah = 0 WHERE id = $1', [f1.id]), /değiştirilemez/);
  assert.equal((await rpc(SAY, 'public.dose_fatura_secimleri()')).siparisler[0].kalemler[0].kalan, '3');
  const yeniden = { ...draft, no: 'S-5' };
  await kaydetFatura(SAY, yeniden, (await onizle(SAY, yeniden)).imza, uid(310));
  assert.equal((await rpc(SAY, 'public.dose_fatura_secimleri()')).siparisler[0].kalemler[0].kalan, '2');
});

test('purchase invoice posts configured taxes, stock and journal atomically and reverses safely', async () => {
  const { db, as, rpc, tarih, onizle, kaydetFatura, tersleFatura } = await faturaOrtami();
  const [cari] = await as(SAY, "INSERT INTO public.cari (unvan, tur) VALUES ('Tedarikçi A', 'Tedarikçi') RETURNING id");
  const [malzeme] = await as(SAY, `INSERT INTO public.malzeme (ad, tur, birim)
    VALUES ('Tahta', 'İlk Madde ve Malzeme', 'Adet') RETURNING id`);
  const p = { tur: 'Alış', no: 'A-1', tarih, cari: cari.id, siparis: null,
    kalemler: [
      { aciklama: 'Malzeme', malzeme_id: malzeme.id, miktar: '10', birim_fiyat: '10', iskonto_orani: '0.1', kdv_orani: '0.2' },
      { aciklama: 'Hizmet', hesap_kodu: '740', miktar: '2', birim_fiyat: '5', iskonto_orani: '0', kdv_orani: '0.2' },
    ], tevkifat: '0.5', stopaj: '0.1', surumler: {} };
  await rpc(M2, 'public.dose_kullanici_davet($1, $2, $3, NULL, NULL)', ['yeni@okul.k12.tr', 'Diğer Sayman', 'Sayman']);
  await rpc(YENI, 'public.dose_ben()');
  const [digerCari] = await as(YENI, "INSERT INTO public.cari (unvan, tur) VALUES ('Diğer', 'Tedarikçi') RETURNING id");
  await reddet(onizle(YENI, p), /uygun etkin cari/);
  await reddet(onizle(YENI, { ...p, cari: digerCari.id }), /alış stok kartı bulunamadı/);
  await reddet(onizle(SAY, p), /Tevkifat hesabı/);
  await rpc(SAY, 'public.dose_vergi_hesabi_kaydet($1,$2,$3)', ['Alış KDV tevkifatı', '360', null]);
  await rpc(SAY, 'public.dose_vergi_hesabi_kaydet($1,$2,$3)', ['Alış stopajı', '360', null]);
  p.surumler = { 'Alış KDV tevkifatı': 1, 'Alış stopajı': 1 };
  const o = await onizle(SAY, p);
  assert.deepEqual([o.detay.matrah, o.detay.kdv, o.detay.tevkif_kdv, o.detay.stopaj, o.detay.net_tutar],
    ['100.00', '20.00', '10.00', '10.00', '100.00']);
  await rpc(SAY, 'public.dose_vergi_hesabi_kaydet($1,$2,$3)', ['Alış stopajı', '361', 1]);
  await reddet(kaydetFatura(SAY, p, o.imza, uid(401)), /Stopaj hesabı/);
  p.surumler['Alış stopajı'] = 2;
  const yeni = await onizle(SAY, p);
  const sonuc = await kaydetFatura(SAY, p, yeni.imza, uid(401));
  const stok = (await rpc(SAY, 'public.dose_stok_veri()')).kartlar.find(k => k.id === malzeme.id);
  assert.deepEqual([stok.miktar, stok.tutar], ['10', '90.00']);
  const fis = (await rpc(SAY, 'public.dose_yevmiye_veri()')).find(f => f.id === sonuc.yevmiye_id);
  assert.deepEqual(fis.satirlar.map(s => [s.hesap_kodu, s.borc, s.alacak]),
    [['191', '20.00', '0'], ['320', '0', '100.00'], ['360', '0', '10.00'],
      ['361', '0', '10.00'], ['150', '90.00', '0'], ['740', '10.00', '0']]);

  const once = (await db.query('SELECT count(*)::int AS n FROM public.fatura')).rows[0].n;
  const gecmis = { ...p, no: 'A-2', tarih: '2020-01-01' };
  const gecmisOnizleme = await onizle(SAY, gecmis);
  await reddet(kaydetFatura(SAY, gecmis, gecmisOnizleme.imza, uid(402)), /daha eski tarihe/);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.fatura')).rows[0].n, once);
  const manuel = await rpc(SAY, 'public.dose_stok_kaydet($1,$2,$3,$4,$5,$6,$7,$8)',
    [malzeme.id, tarih, 'Çıkış', '1', '9', '710', 'Üretim', uid(403)]);
  await reddet(tersleFatura(sonuc.id, uid(404)), /daha yeni açık hareketler/);
  await rpc(SAY, 'public.dose_stok_tersle($1,$2,$3)', [manuel.id, 'Düzeltme', uid(405)]);
  await tersleFatura(sonuc.id, uid(406));
  const sonraki = (await rpc(SAY, 'public.dose_stok_veri()')).kartlar.find(k => k.id === malzeme.id);
  assert.deepEqual([sonraki.miktar, sonraki.tutar], ['0', '0.00']);
  assert.equal((await rpc(SAY, 'public.dose_faturalar()'))[0].iptal, 1);
});

test('identical products on distinct approved order lines have separate invoice limits', async () => {
  const { db, as, rpc, veri, gonder, karar, tarih, onizle, kaydetFatura } = await faturaOrtami();
  const [urun] = await as(SEF, `INSERT INTO public.urun (ad, tur, birim, bolum_id)
    VALUES ('Aynı ürün', 'Hizmet', 'Adet', $1) RETURNING id`, [veri.bolum_id]);
  const siparis = await rpc(SEF, 'public.dose_siparis_kaydet($1, $2, $3, $4)', [null, null, veri, [
    { urun_id: urun.id, aciklama: 'Birinci', birim: 'Adet', miktar: '1', birim_fiyat: '10' },
    { urun_id: urun.id, aciklama: 'İkinci', birim: 'Adet', miktar: '2', birim_fiyat: '20' },
  ]]);
  await gonder(SEF, siparis.id); await karar(TMY, siparis.id, true); await karar(M1, siparis.id, true);
  const kalemler = (await db.query('SELECT id FROM public.siparis_kalem WHERE siparis_id = $1 ORDER BY id',
    [siparis.id])).rows;
  const p = { tur: 'Satış', no: 'AYNI-1', tarih, cari: veri.cari_id, siparis: siparis.id,
    kalemler: kalemler.map(k => ({ siparis_kalem_id: k.id, malzeme_id: null, miktar: '1' })),
    tevkifat: '0', stopaj: '0', surumler: {} };
  const o = await onizle(SAY, p);
  assert.equal(o.detay.matrah, '30.00');
  await kaydetFatura(SAY, p, o.imza, uid(450));
  const secim = (await rpc(SAY, 'public.dose_fatura_secimleri()')).siparisler[0].kalemler;
  assert.deepEqual(secim.map(k => k.kalan), ['0', '1']);
  await reddet(onizle(SAY, { ...p, no: 'AYNI-2', kalemler: [p.kalemler[0]] }), /kalanını aşıyor/);
  const ikinci = { ...p, no: 'AYNI-2', kalemler: [p.kalemler[1]] };
  await kaydetFatura(SAY, ikinci, (await onizle(SAY, ikinci)).imza, uid(451));
  assert.deepEqual((await rpc(SAY, 'public.dose_fatura_secimleri()')).siparisler[0].kalemler.map(k => k.kalan), ['0', '0']);
});

test('sale stock costs are explicit and a failed issue rolls back the invoice', async () => {
  const { db, as, rpc, veri, kaydet, gonder, karar, tarih, onizle, kaydetFatura, tersleFatura } = await faturaOrtami();
  const [malzeme] = await as(SAY, "INSERT INTO public.malzeme (ad, tur, birim) VALUES ('Sıra', 'Mamul', 'Adet') RETURNING id");
  const [urun] = await as(SEF, `INSERT INTO public.urun (ad, tur, birim, bolum_id, mamul_malzeme_id)
    VALUES ('Okul sırası', 'Mal', 'Adet', $1, $2) RETURNING id`, [veri.bolum_id, malzeme.id]);
  await rpc(SAY, 'public.dose_hesap_ekle($1,$2)', ['620', 'Saymanın seçtiği maliyet hesabı']);
  await rpc(SAY, 'public.dose_stok_kaydet($1,$2,$3,$4,$5,$6,$7,$8)',
    [malzeme.id, tarih, 'Giriş', '2', '200', '500', 'Açılış', uid(501)]);
  const siparis = await kaydet(SEF, { urun_id: urun.id, aciklama: 'Sıra', birim: 'Adet', miktar: '3', birim_fiyat: '100' });
  await gonder(SEF, siparis.id); await karar(TMY, siparis.id, true); await karar(M1, siparis.id, true);
  const [kalem] = (await db.query('SELECT id FROM public.siparis_kalem WHERE siparis_id = $1', [siparis.id])).rows;
  await as(SAY, 'UPDATE public.urun SET mamul_malzeme_id = NULL, surum = surum WHERE id = $1', [urun.id]);
  const secim = (await rpc(SAY, 'public.dose_fatura_secimleri()')).siparisler[0].kalemler[0];
  assert.equal(secim.malzeme_id, malzeme.id, 'approved orders retain their stock link');
  assert.equal(secim.stok_baglanti_kaynagi, 'Sipariş onayı');
  const p = { tur: 'Satış', no: 'ST-1', tarih, cari: veri.cari_id, siparis: siparis.id,
    kalemler: [{ siparis_kalem_id: kalem.id, malzeme_id: malzeme.id, miktar: '3' }],
    tevkifat: '0', stopaj: '0', surumler: {} };
  await reddet(onizle(SAY, p), /maliyetini/);
  p.kalemler[0].stok_maliyeti = '200';
  p.kalemler[0].stok_maliyet_hesabi = '620';
  const fazla = await onizle(SAY, p);
  await reddet(kaydetFatura(SAY, p, fazla.imza, uid(502)), /yetersiz/);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.fatura')).rows[0].n, 0);
  p.kalemler[0].miktar = '2';
  const o = await onizle(SAY, p);
  const fatura = await kaydetFatura(SAY, p, o.imza, uid(503));
  const stok = (await rpc(SAY, 'public.dose_stok_veri()')).kartlar.find(k => k.id === malzeme.id);
  assert.deepEqual([stok.miktar, stok.tutar], ['0', '0']);
  const fis = (await rpc(SAY, 'public.dose_yevmiye_veri()')).find(f => f.id === fatura.yevmiye_id);
  assert.ok(fis.satirlar.some(s => s.hesap_kodu === '620' && s.borc === '200'));
  assert.ok(fis.satirlar.some(s => s.hesap_kodu === '152' && s.alacak === '200'));
  await tersleFatura(fatura.id, uid(504));
  const sonraki = (await rpc(SAY, 'public.dose_stok_veri()')).kartlar.find(k => k.id === malzeme.id);
  assert.deepEqual([sonraki.miktar, sonraki.tutar], ['2', '200']);
});

test('legacy approved orders require an explicit stock-link choice and keep its provenance', async () => {
  const { db, as, rpc, veri, kaydet, gonder, karar } = await siparisOrtami('20261031000200_stok_yevmiye.sql');
  await rpc(M1, 'public.dose_kullanici_davet($1, $2, $3, NULL, NULL)', ['sayman@okul.k12.tr', 'Sena Sayman', 'Sayman']);
  await rpc(SAY, 'public.dose_ben()');
  const tarih = (await db.query("SELECT (now() AT TIME ZONE 'Europe/Istanbul')::date::text AS t")).rows[0].t;
  veri.tarih = tarih;
  const [ilkStok] = await as(SAY, "INSERT INTO public.malzeme (ad, tur, birim) VALUES ('Eski', 'Mamul', 'Adet') RETURNING id");
  const [yeniStok] = await as(SAY, "INSERT INTO public.malzeme (ad, tur, birim) VALUES ('Yeni', 'Mamul', 'Adet') RETURNING id");
  const [urun] = await as(SEF, `INSERT INTO public.urun (ad, tur, birim, bolum_id, mamul_malzeme_id)
    VALUES ('Ürün', 'Mal', 'Adet', $1, $2) RETURNING id`, [veri.bolum_id, ilkStok.id]);
  const siparis = await kaydet(SEF, { urun_id: urun.id, aciklama: 'Ürün', birim: 'Adet', miktar: '2', birim_fiyat: '100' });
  await gonder(SEF, siparis.id); await karar(TMY, siparis.id, true); await karar(M1, siparis.id, true);
  await db.exec(fs.readFileSync(root + '20261031000300_fatura.sql', 'utf8'));
  await as(SAY, 'UPDATE public.urun SET mamul_malzeme_id = $1, surum = surum WHERE id = $2', [yeniStok.id, urun.id]);
  await rpc(SAY, 'public.dose_hesap_ekle($1,$2)', ['620', 'Maliyet']);
  const [kalem] = (await db.query('SELECT id, stok_baglanti_kaynagi FROM public.siparis_kalem WHERE siparis_id = $1',
    [siparis.id])).rows;
  assert.equal(kalem.stok_baglanti_kaynagi, null, 'the migration must not invent an approval-time link');
  const p = ['Satış', 'ESKI-1', tarih, veri.cari_id, siparis.id,
    [{ siparis_kalem_id: kalem.id, malzeme_id: yeniStok.id, miktar: '1', stok_maliyeti: '10', stok_maliyet_hesabi: '620' }],
    '0', '0', {}];
  const onizle = () => rpc(SAY, 'public.dose_fatura_onizle($1,$2,$3,$4,$5,$6,$7,$8,$9)', p);
  const kaydetFatura = (imza, istek) =>
    rpc(SAY, 'public.dose_fatura_kaydet($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)', [...p, imza, istek]);
  await reddet(onizle(), /onay anındaki stok bağlantısı bilinmiyor/);
  p[5][0].eski_baglanti_onayi = true;
  let o = await onizle();
  await reddet(kaydetFatura(o.imza, uid(601)), /yetersiz/);
  assert.equal((await db.query('SELECT stok_baglanti_kaynagi FROM public.siparis_kalem WHERE id = $1', [kalem.id]))
    .rows[0].stok_baglanti_kaynagi, null, 'failed invoices must roll back the choice');
  await rpc(SAY, 'public.dose_stok_kaydet($1,$2,$3,$4,$5,$6,$7,$8)',
    [yeniStok.id, tarih, 'Giriş', '2', '20', '500', 'Açılış', uid(602)]);
  o = await onizle();
  await kaydetFatura(o.imza, uid(603));
  const dogrulanan = (await db.query('SELECT stok_baglanti_kaynagi, stok_malzeme_onay_id FROM public.siparis_kalem WHERE id = $1',
    [kalem.id])).rows[0];
  assert.deepEqual(dogrulanan, { stok_baglanti_kaynagi: 'Sayman doğrulaması', stok_malzeme_onay_id: yeniStok.id });
  await as(SAY, 'UPDATE public.urun SET mamul_malzeme_id = $1, surum = surum WHERE id = $2', [ilkStok.id, urun.id]);
  const secim = (await rpc(SAY, 'public.dose_fatura_secimleri()')).siparisler[0].kalemler[0];
  assert.equal(secim.malzeme_id, yeniStok.id);
  assert.equal(secim.stok_baglanti_kaynagi, 'Sayman doğrulaması');
});

test('cash and bank reject negative balances, enforce invoice limits and reverse atomically', async () => {
  const { db, as, rpc, veri, kaydet, gonder, karar, tarih, onizle, kaydetFatura, tersleFatura } = await faturaOrtami();
  const [tedarikci] = await as(SAY, "INSERT INTO public.cari (unvan, tur) VALUES ('Tedarikçi', 'Tedarikçi') RETURNING id");
  const alis = { tur: 'Alış', no: 'KA-1', tarih, cari: tedarikci.id, siparis: null,
    kalemler: [{ aciklama: 'Hizmet', hesap_kodu: '740', miktar: '1', birim_fiyat: '100', iskonto_orani: '0', kdv_orani: '0' }],
    tevkifat: '0', stopaj: '0', surumler: {} };
  const af = await kaydetFatura(SAY, alis, (await onizle(SAY, alis)).imza, uid(701));
  const siparis = await kaydet(SEF, { aciklama: 'Satış', miktar: '1', birim_fiyat: '100' });
  await gonder(SEF, siparis.id); await karar(TMY, siparis.id, true); await karar(M1, siparis.id, true);
  const [kalem] = (await db.query('SELECT id FROM public.siparis_kalem WHERE siparis_id = $1', [siparis.id])).rows;
  const satis = { tur: 'Satış', no: 'KS-1', tarih, cari: veri.cari_id, siparis: siparis.id,
    kalemler: [{ siparis_kalem_id: kalem.id, malzeme_id: null, miktar: '1' }], tevkifat: '0', stopaj: '0', surumler: {} };
  const sf = await kaydetFatura(SAY, satis, (await onizle(SAY, satis)).imza, uid(702));
  const hareket = (u, tur, hesap, tutar, fatura, karsi, istek, gun = tarih) =>
    rpc(u, 'public.dose_kasa_kaydet($1,$2,$3,$4,$5,$6,$7,$8,$9)',
      [tur, hesap, gun, tutar, fatura, karsi, 'BELGE', 'İşlem açıklaması', istek]);
  const tersle = (id, istek, u = SAY) => rpc(u, 'public.dose_kasa_tersle($1,$2,$3)', [id, 'Düzeltme', istek]);
  const bakiye = async hesap => (await rpc(SAY, 'public.dose_kasa_veri()')).hesaplar.find(h => h.hesap === hesap).bakiye;

  await reddet(hareket(M1, 'Açılış', 'Kasa (100)', '100', null, '500', uid(703)), /sayman/);
  await reddet(hareket(SAY, 'Açılış', 'Kasa (100)', 'NaN', null, '500', uid(704)), /tutar/);
  await reddet(hareket(SAY, 'Açılış', 'Kasa (100)', '1.001', null, '500', uid(705)), /tutar/);
  await reddet(hareket(SAY, 'Açılış', 'Kasa (100)', '100', null, '102', uid(706)), /karşı hesap/);
  const kasaAcilis = await hareket(SAY, 'Açılış', 'Kasa (100)', '100', null, '500', uid(707));
  const bankaAcilis = await hareket(SAY, 'Açılış', 'Banka (102)', '50', null, '500', uid(708));
  await reddet(hareket(SAY, 'Açılış', 'Kasa (100)', '1', null, '500', uid(709)), /ilk açık hareket/);
  await reddet(hareket(SAY, 'Açılış', 'Kasa (100)', '100', null, '500', uid(707)), /daha önce/);
  await reddet(hareket(SAY, 'Ödeme', 'Banka (102)', '51', af.id, null, uid(710)), /yetersiz/);
  assert.equal(await bakiye('Banka (102)'), '50');
  await reddet(hareket(SAY, 'Tahsilat', 'Kasa (100)', '1', af.id, null, uid(711)), /uygun.*fatura/);
  const bankaOdeme = await hareket(SAY, 'Ödeme', 'Banka (102)', '30', af.id, null, uid(712));
  const kasaOdeme = await hareket(SAY, 'Ödeme', 'Kasa (100)', '10', af.id, null, uid(713));
  await reddet(hareket(SAY, 'Ödeme', 'Kasa (100)', '61', af.id, null, uid(714)), /açık bakiyesini/);
  const tahsilat = await hareket(SAY, 'Tahsilat', 'Kasa (100)', '50', sf.id, null, uid(715));
  assert.equal(await bakiye('Kasa (100)'), '140');
  assert.equal(await bakiye('Banka (102)'), '20');
  const ikinciAlis = { ...alis, no: 'KA-2',
    kalemler: [{ ...alis.kalemler[0], birim_fiyat: '200' }] };
  const af2 = await kaydetFatura(SAY, ikinciAlis, (await onizle(SAY, ikinciAlis)).imza, uid(726));
  await reddet(hareket(SAY, 'Ödeme', 'Kasa (100)', '141', af2.id, null, uid(727)), /yetersiz/);
  const yarin = (await db.query("SELECT ((now() AT TIME ZONE 'Europe/Istanbul')::date + 1)::text AS t")).rows[0].t;
  await reddet(hareket(SAY, 'Tahsilat', 'Kasa (100)', '1', sf.id, null, uid(728), yarin), /tarih/);
  await reddet(hareket(SAY, 'Tahsilat', 'Kasa (100)', '1', sf.id, null, uid(729), '2020-01-01'), /fatura tarihinden önce/);
  const veriSon = await rpc(SAY, 'public.dose_kasa_veri()');
  assert.equal(veriSon.faturalar.find(f => f.id === af.id).kalan, '60.00');
  assert.equal(veriSon.faturalar.find(f => f.id === sf.id).kalan, '70.00');
  assert.equal(veriSon.hareketler.find(h => h.id === tahsilat.id).hasilat_tutari, null);
  const fis = (await rpc(SAY, 'public.dose_yevmiye_veri()')).find(f => f.id === bankaOdeme.yevmiye_id);
  assert.deepEqual(fis.satirlar.map(s => [s.hesap_kodu, s.borc, s.alacak]), [['102', '0', '30'], ['320', '30', '0']]);
  await reddet(tersleFatura(af.id, uid(716)), /açık ödeme veya tahsilat/);
  await reddet(tersle(kasaAcilis.id, uid(717)), /daha yeni açık hareketler/);
  await reddet(as(SAY, 'UPDATE public.kasa_banka SET tutar = 0'), /permission denied/);
  await reddet(db.query('UPDATE public.kasa_banka SET tutar = 0 WHERE id = $1', [tahsilat.id]), /değiştirilemez/);

  await rpc(M2, 'public.dose_kullanici_davet($1, $2, $3, NULL, NULL)', ['yeni@okul.k12.tr', 'Diğer Sayman', 'Sayman']);
  await rpc(YENI, 'public.dose_ben()');
  await reddet(hareket(YENI, 'Ödeme', 'Kasa (100)', '1', af.id, null, uid(718)), /uygun.*fatura/);
  await reddet(tersle(tahsilat.id, uid(719), YENI), /bulunamadı/);
  assert.deepEqual((await rpc(YENI, 'public.dose_kasa_veri()')).hareketler, []);
  await db.query("SELECT dose_private.lisans_ayarla('111111', current_date - 1)");
  await reddet(hareket(SAY, 'Tahsilat', 'Kasa (100)', '1', sf.id, null, uid(732)), /sayman/);
  assert.equal((await rpc(SAY, 'public.dose_kasa_veri()')).hareketler.length, 5);
  await db.query("SELECT dose_private.lisans_ayarla('111111', current_date + 1)");

  await tersle(tahsilat.id, uid(720));
  await reddet(tersle(tahsilat.id, uid(720)), /daha önce/);
  await tersle(kasaOdeme.id, uid(721));
  await tersle(bankaOdeme.id, uid(722));
  assert.equal((await rpc(SAY, 'public.dose_kasa_veri()')).faturalar.find(f => f.id === af.id).kalan, '100.00');
  await tersleFatura(af.id, uid(723));
  await tersle(kasaAcilis.id, uid(724));
  await tersle(bankaAcilis.id, uid(725));
  assert.equal(await bakiye('Kasa (100)'), '0');
  assert.equal(await bakiye('Banka (102)'), '0');
  const mizan = await rpc(SAY, 'public.dose_mizan_veri()');
  assert.equal(mizan.find(h => h.hesap_kodu === '100').bakiye, '0');
  assert.equal(mizan.find(h => h.hesap_kodu === '102').bakiye, '0');
});

test('cash and bank accounts cannot be changed through stock or invoice journals', async () => {
  const { db, as, rpc, tarih, onizle, kaydetFatura } = await faturaOrtami();
  const [malzeme] = await as(SAY, "INSERT INTO public.malzeme (ad, tur, birim) VALUES ('Tahta', 'İlk Madde ve Malzeme', 'Adet') RETURNING id");
  await reddet(rpc(SAY, 'public.dose_stok_kaydet($1,$2,$3,$4,$5,$6,$7,$8)',
    [malzeme.id, tarih, 'Giriş', '1', '10', '100', 'Stok', uid(730)]), /Kasa\/banka hesabı/);
  const [cari] = await as(SAY, "INSERT INTO public.cari (unvan, tur) VALUES ('Tedarikçi', 'Tedarikçi') RETURNING id");
  const alis = { tur: 'Alış', no: 'AYKIRI', tarih, cari: cari.id, siparis: null,
    kalemler: [{ aciklama: 'Hizmet', hesap_kodu: '102', miktar: '1', birim_fiyat: '10', iskonto_orani: '0', kdv_orani: '0' }],
    tevkifat: '0', stopaj: '0', surumler: {} };
  await reddet(onizle(SAY, alis), /Kasa\/banka hesabı/);
  const [okul] = (await db.query('SELECT okul_id FROM public.malzeme WHERE id = $1', [malzeme.id])).rows;
  await reddet(db.query(`SELECT dose_private.yevmiye_olustur($1,$2,'Sınama','Stok',1,$3)`,
    [okul.okul_id, tarih, [{ hesap: '100', borc: '10', alacak: '0' }, { hesap: '500', borc: '0', alacak: '10' }]]),
    /yalnız kasa\/banka/);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.stok_hareket')).rows[0].n, 0);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.fatura')).rows[0].n, 0);
});

test('cash balances preserve exact amounts above JavaScript integer precision', async () => {
  const { rpc, tarih } = await faturaOrtami();
  const buyuk = '9007199254740993.99';
  const sonuc = await rpc(SAY, 'public.dose_kasa_kaydet($1,$2,$3,$4,$5,$6,$7,$8,$9)',
    ['Açılış', 'Banka (102)', tarih, buyuk, null, '500', null, 'Banka açılışı', uid(740)]);
  assert.equal(sonuc.bakiye, buyuk);
  const veri = await rpc(SAY, 'public.dose_kasa_veri()');
  assert.equal(veri.hesaplar.find(h => h.hesap === 'Banka (102)').bakiye, buyuk);
  assert.equal((await rpc(SAY, 'public.dose_mizan_veri()')).find(h => h.hesap_kodu === '102').bakiye, buyuk);
});

test('cash migration refuses legacy movements and unrelated cash journal entries', async () => {
  for (const eskiTur of ['hareket', 'yevmiye']) {
    const { db, rpc, kod } = await kur('20261031000300_fatura.sql');
    await rpc(M1, 'public.dose_okul_etkinlestir($1,$2,$3)',
      [await kod('Eski Okul', '123456'), '123456', 'Ayşe Müdür']);
    const [okul] = (await db.query('SELECT id FROM dose_private.okul WHERE kurum_kodu = $1', ['123456'])).rows;
    if (eskiTur === 'hareket') {
      await db.query(`INSERT INTO public.kasa_banka (okul_id, tarih, hesap, yon, tur, tutar)
        VALUES ($1,'2020-01-01','Kasa (100)','Giriş','Tahsilat',10)`, [okul.id]);
    } else {
      await db.query(`SELECT dose_private.yevmiye_olustur($1,'2020-01-01','Eski','Stok',1,$2)`,
        [okul.id, [{ hesap: '100', borc: '10', alacak: '0' }, { hesap: '500', borc: '0', alacak: '10' }]]);
    }
    await assert.rejects(db.exec(fs.readFileSync(root + '20261031000400_kasa_banka.sql', 'utf8')),
      eskiTur === 'hareket' ? /Eski kasa\/banka hareketleri/ : /eski yevmiye satırları/);
  }
});

test('central allocation parameters require independent, versioned school treasurer confirmation', async () => {
  const { db, as, rpc, kod } = await kur();
  const ata = (u, ad, aktif, role = 'service_role') =>
    as(null, 'SELECT dose_private.mevzuat_yoneticisi_ata($1,$2,$3)', [u, ad, aktif], role);
  await reddet(ata(MERKEZ, 'Merkez Yönetici', true, 'authenticated'), /permission denied/);
  await reddet(ata(ONAYSIZ, 'Merkez Yönetici', true), /doğrulanmış/i);
  await ata(MERKEZ, 'Merkez Yönetici', true);
  const merkezBen = await rpc(MERKEZ, 'public.dose_ben()');
  assert.equal(merkezBen.uye, true);
  assert.equal(merkezBen.merkez_mevzuat, true);
  assert.equal(merkezBen.okul, null);
  assert.equal(merkezBen.yetkiler.merkez_mevzuat, 'y');
  assert.deepEqual(await as(MERKEZ, 'SELECT id FROM public.personel'), []);
  await reddet(as(MERKEZ, 'SELECT * FROM dose_private.mevzuat_yayin'), /permission denied/);
  await reddet(rpc(MERKEZ, 'public.dose_ben_okul_baglam()'), /permission denied/);

  await rpc(M1, 'public.dose_okul_etkinlestir($1,$2,$3)',
    [await kod('Birinci Okul', '111111'), '111111', 'Birinci Müdür']);
  await rpc(M2, 'public.dose_okul_etkinlestir($1,$2,$3)',
    [await kod('İkinci Okul', '222222'), '222222', 'İkinci Müdür']);
  await rpc(M1, 'public.dose_kullanici_davet($1,$2,$3,NULL,NULL)',
    ['sayman@okul.k12.tr', 'Birinci Sayman', 'Sayman']);
  await rpc(M2, 'public.dose_kullanici_davet($1,$2,$3,NULL,NULL)',
    ['yeni@okul.k12.tr', 'İkinci Sayman', 'Sayman']);
  await rpc(SAY, 'public.dose_ben()');
  await rpc(YENI, 'public.dose_ben()');
  const okul1 = (await db.query("SELECT id FROM dose_private.okul WHERE kurum_kodu = '111111'")).rows[0].id;
  const okul2 = (await db.query("SELECT id FROM dose_private.okul WHERE kurum_kodu = '222222'")).rows[0].id;
  const degerler = {
    pb_kar_orani: '0.05', pb_faaliyet_orani: '0.25',
    os_kar_orani: '0.10', os_faaliyet_orani: '0.40', os_pesin_orani: '0.25',
    tesis_kar_orani: '0.15', tesis_faaliyet_orani: '0.55', tesis_pesin_orani: '0.25',
    ogrenci_hakki_orani: '0.30', malzeme_azami_orani: '0.60',
  };
  const yayinla = (u, tarih, d, istek) => rpc(u, 'public.dose_mevzuat_yayinla($1,$2,$3,$4)',
    [tarih, 'Yetkili tarafından incelenen kaynak', d, istek]);
  const karar = (u, id, onay, aciklama, istek) => rpc(u, 'public.dose_mevzuat_karar($1,$2,$3,$4)',
    [id, onay, aciklama, istek]);
  const oku = async (okul, tarih) =>
    (await db.query('SELECT dose_private.mevzuat_oku($1,$2) AS r', [okul, tarih])).rows[0].r;

  await reddet(yayinla(SAY, '2026-01-01', degerler, uid(801)), /merkez yöneticisi/);
  await reddet(rpc(SAY, 'public.dose_mevzuat_merkez_veri()'), /yetkiniz/);
  await reddet(rpc(MERKEZ, 'public.dose_mevzuat_okul_veri()'), /yetkiniz/);
  await reddet(yayinla(MERKEZ, '2026-01-01', { ...degerler, pb_kar_orani: 0.05 }, uid(802)), /kesin oran/);
  await reddet(yayinla(MERKEZ, '2026-01-01', { ...degerler, pb_kar_orani: 'NaN' }, uid(803)), /kesin oran/);
  await reddet(yayinla(MERKEZ, '2026-01-01', { ...degerler, pb_kar_orani: '1.1' }, uid(804)), /kesin oran/);
  await reddet(yayinla(MERKEZ, '2026-01-01', { ...degerler, pb_kar_orani: '0.90' }, uid(805)), /toplamı/);
  await reddet(yayinla(MERKEZ, 'infinity', degerler, uid(824)), /Başlangıç/);
  await reddet(yayinla(MERKEZ, '2026-01-01', null, uid(825)), /Parametre değerleri/);
  await reddet(yayinla(MERKEZ, '2026-01-01', { ...degerler, pb_kar_orani: '0.00000000001' }, uid(826)), /10 ondalıklı/);
  const eksik = { ...degerler }; delete eksik.os_pesin_orani;
  await reddet(yayinla(MERKEZ, '2026-01-01', eksik, uid(806)), /eksiksiz/);
  await reddet(yayinla(MERKEZ, '2026-01-01', { ...degerler, bilinmeyen: '0' }, uid(807)), /eksiksiz/);
  const ilk = await yayinla(MERKEZ, '2026-01-01', degerler, uid(808));
  await reddet(yayinla(MERKEZ, '2026-01-01', degerler, uid(808)), /daha önce/);
  assert.equal((await rpc(MERKEZ, 'public.dose_mevzuat_merkez_veri()')).alanlar.length, 10);
  assert.equal((await rpc(SAY, 'public.dose_mevzuat_okul_veri()')).yayinlar[0].onay, false);
  await reddet(oku(okul1, '2026-05-01'), /doğrulanmamış/);
  await reddet(karar(M1, ilk.id, true, 'Kaynak kontrol edildi', uid(809)), /saymanı/);
  await reddet(karar(SAY, ilk.id, null, 'Kaynak kontrol edildi', uid(810)), /Karar/);
  await reddet(karar(SAY, ilk.id, true, '', uid(811)), /açıklama/);
  await db.query("SELECT dose_private.lisans_ayarla('111111', current_date - 1)");
  await reddet(karar(SAY, ilk.id, true, 'Kaynak kontrol edildi', uid(812)), /saymanı/);
  assert.equal((await rpc(SAY, 'public.dose_mevzuat_okul_veri()')).yayinlar.length, 1);
  await db.query("SELECT dose_private.lisans_ayarla('111111', current_date + 1)");

  await karar(SAY, ilk.id, true, 'Birinci okul doğruladı', uid(813));
  assert.equal((await oku(okul1, '2026-05-01')).degerler.pb_kar_orani, '0.05');
  await reddet(oku(okul2, '2026-05-01'), /doğrulanmamış/);
  assert.equal((await rpc(YENI, 'public.dose_mevzuat_okul_veri()')).yayinlar[0].onay_aciklama, null);
  await reddet(karar(SAY, ilk.id, true, 'Birinci okul doğruladı', uid(813)), /daha önce/);
  await reddet(karar(SAY, ilk.id, true, 'Tekrar doğrulandı', uid(814)), /zaten doğrulandı/);
  await karar(YENI, ilk.id, true, 'İkinci okul doğruladı', uid(815));
  await karar(SAY, ilk.id, false, 'Kontrol geri çekildi', uid(816));
  await reddet(oku(okul1, '2026-05-01'), /doğrulanmamış/);
  assert.equal((await oku(okul2, '2026-05-01')).yayin_id, ilk.id);
  await karar(SAY, ilk.id, true, 'Yeniden doğrulandı', uid(817));

  const duzeltme = await yayinla(MERKEZ, '2026-01-01',
    { ...degerler, pb_kar_orani: '0.0600000001' }, uid(818));
  await reddet(oku(okul1, '2026-05-01'), /doğrulanmamış/);
  await reddet(oku(okul2, '2026-05-01'), /doğrulanmamış/);
  await reddet(karar(SAY, ilk.id, true, 'Eski sürüm kontrolü', uid(819)), /güncel değil/);
  await karar(SAY, duzeltme.id, true, 'Düzeltme doğrulandı', uid(820));
  assert.equal((await oku(okul1, '2026-05-01')).degerler.pb_kar_orani, '0.0600000001');
  const ikinciDonem = await yayinla(MERKEZ, '2026-07-01', degerler, uid(821));
  assert.equal((await oku(okul1, '2026-06-30')).yayin_id, duzeltme.id);
  await reddet(oku(okul1, '2026-07-01'), /doğrulanmamış/);
  await karar(SAY, ikinciDonem.id, true, 'Yeni dönem doğrulandı', uid(822));
  assert.equal((await oku(okul1, '2026-07-01')).yayin_id, ikinciDonem.id);
  await reddet(oku(okul1, '2027-01-01'), /bulunamadı/);
  assert.equal((await db.query('SELECT count(*) AS n FROM dose_private.mevzuat_yayin')).rows[0].n, 3);

  await reddet(db.query('UPDATE dose_private.mevzuat_yayin SET kaynak = $1 WHERE id = $2', ['Değişiklik', ilk.id]),
    /değiştirilemez/);
  await reddet(db.query('DELETE FROM dose_private.mevzuat_onay WHERE yayin_id = $1', [ilk.id]), /silinemez/);
  assert.ok((await as(SAY, "SELECT id FROM public.islem_log WHERE tablo = 'mevzuat_onay'")).length >= 5);
  await ata(MERKEZ, 'Merkez Yönetici', false);
  assert.equal((await rpc(MERKEZ, 'public.dose_ben()')).uye, false);
  await reddet(yayinla(MERKEZ, '2027-01-01', degerler, uid(823)), /merkez yöneticisi/);
  await reddet(rpc(MERKEZ, 'public.dose_mevzuat_merkez_veri()'), /yetkiniz/);
});

test('one-month trial opens an isolated school once per verified account', async () => {
  const { db, as, rpc, kod } = await kur();
  const dene = (u, ad, kk, kisi = 'Deneme Müdür') => rpc(u, 'public.dose_deneme_baslat($1, $2, $3)', [ad, kk, kisi]);
  await reddet(as(null, "SELECT public.dose_deneme_baslat('Okul', '123456', 'Ali Veli')", [], 'anon'), /permission denied/);
  await reddet(dene(ONAYSIZ, 'Deneme MTAL', '777777'), /doğrulanmadı/);
  await reddet(dene(M1, 'Deneme MTAL', '12'), /5-8/);
  await reddet(dene(M1, 'X', '777777'), /Okul adı/);

  await kod('Lisanslı Okul', '123456');
  await reddet(dene(M1, 'Başka Ad', '123456'), /zaten var/);
  assert.equal((await db.query('SELECT count(*)::int n FROM dose_private.deneme_kaydi')).rows[0].n, 0, 'failed trial is rolled back');

  const sonuc = await dene(M1, '  Deneme   MTAL ', '777777');
  assert.equal(sonuc.basarili, true);
  const beklenen = (await db.query("SELECT ((now() AT TIME ZONE 'Europe/Istanbul')::date + interval '1 month')::date::text d")).rows[0].d;
  assert.equal(sonuc.lisans_bitis, beklenen);
  const ben = await rpc(M1, 'public.dose_ben()');
  assert.equal(ben.rol, 'Okul Müdürü');
  assert.equal(ben.okul.ad, 'Deneme MTAL');
  assert.equal(ben.okul.deneme, true);
  assert.equal(ben.okul.salt_okunur, false);
  assert.ok(ben.okul.kalan_gun >= 28 && ben.okul.kalan_gun <= 32);
  assert.equal(ben.yetkiler.bolum, 'y');
  await as(M1, "INSERT INTO public.bolum (ad, utp_yontemi) VALUES ('Bilişim', 'Katkı oranına göre (md.5/7-c)')");
  assert.equal((await as(M2, 'SELECT ad FROM public.bolum')).length, 0);
  await reddet(dene(M1, 'İkinci Okul', '888888'), /zaten bir okula/);

  // Trial ends: read-only; leaving the school does not grant a second trial.
  await db.exec("UPDATE dose_private.okul SET lisans_bitis = current_date - 1 WHERE kurum_kodu = '777777'");
  const bitti = await rpc(M1, 'public.dose_ben()');
  assert.equal(bitti.okul.salt_okunur, true);
  assert.equal(bitti.okul.kalan_gun, 0);
  await reddet(as(M1, "INSERT INTO public.bolum (ad, utp_yontemi) VALUES ('Z', 'Katkı oranına göre (md.5/7-c)')"), /row-level/);
  await db.exec(`DELETE FROM dose_private.uyelik WHERE auth_user_id = '${M1}'`);
  await reddet(dene(M1, 'İkinci Okul', '888888'), /daha önce kullanıldı/);

  // Vendor converts the trial into a paid license.
  await db.exec(`INSERT INTO dose_private.uyelik (auth_user_id, okul_id, rol, ad_soyad)
                 SELECT '${M1}', id, 'Okul Müdürü', 'Deneme Müdür' FROM dose_private.okul WHERE kurum_kodu = '777777'`);
  await db.query("SELECT dose_private.lisans_ayarla('777777', current_date + 365)");
  const lisansli = await rpc(M1, 'public.dose_ben()');
  assert.equal(lisansli.okul.deneme, false);
  assert.equal(lisansli.okul.salt_okunur, false);
  await reddet(as(M1, "SELECT dose_private.lisans_ayarla('777777', NULL)"), /permission denied/);
});

test('piece-rate payroll follows the Ek-3 cost sheet, distributes exact cents, approves in order and pays by bank', async () => {
  const { db, as, rpc, veri, kaydet, gonder, karar, tarih } = await faturaOrtami();
  await as(null, 'SELECT dose_private.mevzuat_yoneticisi_ata($1,$2,$3)', [MERKEZ, 'Merkez Yönetici', true], 'service_role');
  const yil = tarih.slice(0, 4);
  const degerler = {
    pb_kar_orani: '0.05', pb_faaliyet_orani: '0.11',
    os_kar_orani: '0.10', os_faaliyet_orani: '0.40', os_pesin_orani: '0.25',
    tesis_kar_orani: '0.15', tesis_faaliyet_orani: '0.55', tesis_pesin_orani: '0.25',
    ogrenci_hakki_orani: '0.30', malzeme_azami_orani: '0.60',
  };
  const yayin = await rpc(MERKEZ, 'public.dose_mevzuat_yayinla($1,$2,$3,$4)', [`${yil}-01-01`, 'Test kaynağı', degerler, uid(901)]);
  await rpc(SAY, 'public.dose_mevzuat_karar($1,$2,$3,$4)', [yayin.id, true, 'Kontrol edildi', uid(902)]);

  const IBAN = 'TR330006100519786457841326';
  const ogretmen = [];
  for (const [ad, hs] of [['Öğretmen A', 'Eğitim ve Öğretim Hizmetleri'], ['Öğretmen B', 'Eğitim ve Öğretim Hizmetleri'], ['Usta C', 'Teknik Hizmetler']]) {
    ogretmen.push((await as(M1, `INSERT INTO public.personel (ad_soyad, hizmet_sinifi, dose_gorevi, bolum_id, iban)
      VALUES ($1, $2, 'Öğretmen', ${veri.bolum_id}, $3) RETURNING id`, [ad, hs, IBAN]))[0].id);
  }
  const ogr = async (ad, sinif, muvafakat = 1, iban = IBAN) => (await as(TMY, `INSERT INTO public.ogrenci
    (ad_soyad, okul_no, sinif, bolum_id, veli_muvafakat, muvafakat_tarihi, iban)
    VALUES ($1, '1', $2, ${veri.bolum_id}, $3, $4, $5) RETURNING id`, [ad, sinif, muvafakat, muvafakat ? tarih : null, iban]))[0].id;
  const s1 = await ogr('Öğrenci Bir', '11-A'), s2 = await ogr('Öğrenci İki', '12-B');
  const dokuzuncu = await ogr('Öğrenci Dokuz', '9-A'), muvafakatsiz = await ogr('Öğrenci Muvafakatsiz', '10-A', 0);

  const siparis = await kaydet(SEF, { aciklama: 'Zeytin hasadı', miktar: '1', birim_fiyat: '50000' });
  await gonder(SEF, siparis.id); await karar(TMY, siparis.id, true); await karar(M1, siparis.id, true);
  const gunSayisi = new Date(Number(yil), Number(tarih.slice(5, 7)), 0).getDate();
  const gun = Number(tarih.slice(8, 10));
  const gunler = adet => Array.from({ length: gunSayisi }, (_, i) => (i + 1 === gun ? String(adet) : '0'));
  const hakedis = {
    siparis_id: siparis.id, baslama: tarih, bitis: tarih, bedel: '39603.96', hizmet_alimi: '0',
    faaliyet_orani: '0.16', kar_orani: '0.05', pesin_orani: '0.01', shcek_orani: '0.01', ogrenci_orani: '0.5',
    dv_orani: '0.00759', asgari_ucret: '33030', urun_aciklama: 'Zeytin üretimi', uretilen_miktar: '1500', birim: 'Kg',
  };
  const malzeme = [{ cins: 'Zeytin', miktar: '1500', birim: 'Kg', birim_fiyat: '15', kdv_orani: '0.01' }];
  const kisiler = [
    { kisi_turu: 'Öğretmen', kisi_id: ogretmen[0], gorev: 'Alan Şefi', gv_orani: '0.27', gunler: gunler(1) },
    { kisi_turu: 'Öğretmen', kisi_id: ogretmen[1], gorev: 'Öğretmen', gv_orani: '0.15', gunler: gunler(1) },
    { kisi_turu: 'Öğretmen', kisi_id: ogretmen[2], gorev: 'Usta', gv_orani: '0.15', gunler: gunler(1) },
    { kisi_turu: 'Öğrenci', kisi_id: s1, gunler: gunler(1) },
    { kisi_turu: 'Öğrenci', kisi_id: s2, gunler: gunler(2) },
  ];
  const pbKaydet = (u, id, sur, v, m, k, istek) =>
    rpc(u, 'public.dose_pb_kaydet($1,$2,$3,$4,$5,$6)', [id, sur, v, m, k, istek]);

  await reddet(pbKaydet(OGR, null, null, hakedis, malzeme, kisiler, uid(903)), /Alan Şefi veya Teknik/);
  await reddet(pbKaydet(SEF, null, null, { ...hakedis, bedel: '1.001' }, malzeme, kisiler, uid(904)), /ondalık/);
  await reddet(pbKaydet(SEF, null, null, hakedis, malzeme, [{ ...kisiler[0], gunler: ['1'] }], uid(905)), /günü için/);
  await reddet(pbKaydet(SEF, null, null, hakedis, malzeme, [kisiler[0], kisiler[0]], uid(906)), /birden fazla/);
  await reddet(pbKaydet(SEF, null, null, hakedis, malzeme, [{ ...kisiler[0], gv_orani: undefined }], uid(907)), /gelir vergisi/);

  const kayit = await pbKaydet(SEF, null, null, hakedis, malzeme, kisiler, uid(908));
  await reddet(pbKaydet(SEF, null, null, hakedis, malzeme, kisiler, uid(908)), /daha önce/);
  const h = kayit.hesap;
  assert.deepEqual(h.hatalar, []);
  assert.equal(h.malzeme, '22500.00');
  assert.equal(h.faaliyet, '6336.63');
  assert.equal(h.kar, '1980.20');
  assert.equal(h.pesin_gelir_vergisi, '396.04');
  assert.equal(h.shcek, '396.04');
  assert.equal(h.iscilik, '7995.05');
  assert.equal(h.ogrenci_havuz, '3997.53');
  assert.equal(h.ogretmen_havuz, '3997.52');
  assert.deepEqual(h.kisiler.map(k => k.brut), ['1332.51', '1332.51', '1332.50', '1332.51', '2665.02']);
  assert.deepEqual(h.kisiler.map(k => k.gelir_vergisi), ['359.78', '199.88', '199.88', '0', '0']);
  assert.deepEqual(h.kisiler.map(k => k.damga_vergisi), ['10.11', '10.11', '10.11', '0.00', '0.00']);
  assert.deepEqual(h.toplam, { brut: '7995.05', gelir_vergisi: '759.54', damga_vergisi: '30.33', net: '7205.18' });

  // Doğrulanmış asgari oranlar kayıtta zorunlu; diğer yasal kontroller gönderimde.
  await reddet(pbKaydet(SEF, kayit.id, kayit.surum,
    { ...hakedis, faaliyet_orani: '0.10', ogrenci_orani: '0.2' }, malzeme, kisiler, uid(909)),
    /Faaliyet gideri oranı doğrulanmış asgari|Öğrenci payı doğrulanmış asgari/);
  const yanlis = await pbKaydet(SEF, kayit.id, kayit.surum, hakedis,
    [{ ...malzeme[0], birim_fiyat: '16' }],
    [...kisiler, { kisi_turu: 'Öğrenci', kisi_id: dokuzuncu, gunler: gunler(1) },
      { kisi_turu: 'Öğrenci', kisi_id: muvafakatsiz, gunler: gunler(1) }], uid(9091));
  const hatalar = yanlis.hesap.hatalar.join('\n');
  for (const re of [/%60/, /9\. sınıf/, /muvafakati/]) assert.match(hatalar, re);
  await reddet(rpc(SEF, 'public.dose_pb_gonder($1,$2)', [kayit.id, yanlis.surum]), /kontrolleri/);
  const duzgun = await pbKaydet(SEF, kayit.id, yanlis.surum, hakedis, malzeme, kisiler, uid(910));
  await assert.rejects(pbKaydet(SEF, kayit.id, yanlis.surum, hakedis, malzeme, kisiler, uid(911)), e => e.hint === 'surum_cakismasi');

  // Approval chain: Alan Şefi -> TMY (uygundur) -> Müdür (olur); return requires a reason.
  const g = await rpc(SEF, 'public.dose_pb_gonder($1,$2)', [kayit.id, duzgun.surum]);
  assert.equal(g.durum, 'TMY Onayında');
  await reddet(rpc(M1, 'public.dose_pb_karar($1,$2,$3,$4)', [kayit.id, g.surum, true, '']), /sıradaki yetkili/);
  await reddet(rpc(TMY, 'public.dose_pb_karar($1,$2,$3,$4)', [kayit.id, g.surum, false, '']), /gerekçe/);
  const iade = await rpc(TMY, 'public.dose_pb_karar($1,$2,$3,$4)', [kayit.id, g.surum, false, 'Puantajı kontrol edin']);
  assert.equal(iade.durum, 'Taslak');
  const g2 = await rpc(SEF, 'public.dose_pb_gonder($1,$2)', [kayit.id, iade.surum]);
  const t = await rpc(TMY, 'public.dose_pb_karar($1,$2,$3,$4)', [kayit.id, g2.surum, true, 'Uygundur']);
  assert.equal(t.durum, 'Müdür Onayında');
  await reddet(pbKaydet(SEF, kayit.id, t.surum, hakedis, malzeme, kisiler, uid(912)), /taslak/);
  const olur = await rpc(M1, 'public.dose_pb_karar($1,$2,$3,$4)', [kayit.id, t.surum, true, 'Olur']);
  assert.equal(olur.durum, 'Onaylandı');
  const fis = (await db.query('SELECT hesap_kodu, borc::text, alacak::text FROM public.yevmiye_satir WHERE yevmiye_id = $1 ORDER BY id',
    [olur.yevmiye_id])).rows;
  assert.deepEqual(fis, [{ hesap_kodu: '720', borc: '7995.05', alacak: '0' }, { hesap_kodu: '335', borc: '0', alacak: '7205.18' },
    { hesap_kodu: '360', borc: '0', alacak: '789.87' }]);

  const liste = await rpc(SEF, 'public.dose_pb_veri()');
  assert.equal(liste.hakedisler[0].onaylar.map(a => a.islem).join(','),
    'Hazırlandı,Onaya gönderildi,İade edildi,Onaya gönderildi,Uygundur,Olur');
  assert.equal(liste.banka_bakiye, null);
  assert.deepEqual((await rpc(M2, 'public.dose_pb_veri()')).hakedisler, [], 'other school sees nothing');
  await reddet(as(SEF, 'SELECT * FROM dose_private.pb_hakedis'), /permission denied/);
  await reddet(as(M1, `DELETE FROM public.personel WHERE id = ${ogretmen[0]}`), /hakedişinde kullanıldığı/);

  // Over-the-order total is rejected for another draft.
  const ikinci = await pbKaydet(SEF, null, null, { ...hakedis, bedel: '20000' }, malzeme, kisiler, uid(913));
  assert.match(ikinci.hesap.hatalar.join('\n'), /sözleşme bedelini/);

  // Bank payment by the treasurer only, never twice, reversible through cash/bank.
  const ode = (u, istek, gunu = tarih) => rpc(u, 'public.dose_pb_ode($1,$2,$3,$4)', [kayit.id, gunu, 'DEKONT-1', istek]);
  await reddet(ode(M1, uid(914)), /sayman/);
  await reddet(ode(SAY, uid(915)), /yetersiz/);
  await rpc(SAY, 'public.dose_kasa_kaydet($1,$2,$3,$4,$5,$6,$7,$8,$9)',
    ['Açılış', 'Banka (102)', tarih, '10000', null, '500', null, 'Açılış', uid(916)]);
  const odeme = await ode(SAY, uid(917));
  assert.equal(odeme.tutar, '7205.18');
  assert.equal(odeme.bakiye, '2794.82');
  await reddet(ode(SAY, uid(918)), /zaten ödendi/);
  await reddet(rpc(M1, 'public.dose_pb_iptal($1,$2,$3)', [kayit.id, olur.surum, 'Hatalı']), /Ödenmiş/);
  await rpc(SAY, 'public.dose_kasa_tersle($1,$2,$3)', [odeme.id, 'Yanlış dekont', uid(919)]);
  assert.equal((await rpc(SAY, 'public.dose_pb_veri()')).hakedisler.find(x => x.id === kayit.id).odeme, null);
  const iptal = await rpc(M1, 'public.dose_pb_iptal($1,$2,$3)', [kayit.id, olur.surum, 'Hatalı hakediş']);
  const mizan = (await db.query(`SELECT hesap_kodu, sum(borc - alacak)::text AS bakiye FROM public.yevmiye_satir
    WHERE hesap_kodu IN ('720', '335', '360') GROUP BY hesap_kodu ORDER BY 1`)).rows;
  assert.deepEqual(mizan.map(r => Number(r.bakiye)), [0, 0, 0]);
  assert.equal(iptal.durum, 'İptal');
});

test('overtime payroll enforces md.9 daily limits, exclusions and the order labour cap, then approves and pays', async () => {
  const { db, as, rpc, veri, kaydet, gonder, karar, tarih } = await faturaOrtami();
  await as(null, 'SELECT dose_private.mevzuat_yoneticisi_ata($1,$2,$3)', [MERKEZ, 'Merkez Yönetici', true], 'service_role');
  const yil = Number(tarih.slice(0, 4)), ay = Number(tarih.slice(5, 7)), gun = Number(tarih.slice(8, 10));
  const yayin = await rpc(MERKEZ, 'public.dose_mevzuat_yayinla($1,$2,$3,$4)', [`${yil}-01-01`, 'Test kaynağı', {
    pb_kar_orani: '0.05', pb_faaliyet_orani: '0.11', os_kar_orani: '0.10', os_faaliyet_orani: '0.40',
    os_pesin_orani: '0.25', tesis_kar_orani: '0.15', tesis_faaliyet_orani: '0.55', tesis_pesin_orani: '0.25',
    ogrenci_hakki_orani: '0.30', malzeme_azami_orani: '0.60' }, uid(951)]);
  await rpc(SAY, 'public.dose_mevzuat_karar($1,$2,$3,$4)', [yayin.id, true, 'Kontrol edildi', uid(952)]);

  const IBAN = 'TR330006100519786457841326';
  const personel = async (ad, hs, unvan = 'Öğretmen') => (await as(M1, `INSERT INTO public.personel
    (ad_soyad, kadro_unvani, hizmet_sinifi, dose_gorevi, bolum_id, iban) VALUES ($1, $2, $3, 'Öğretmen', ${veri.bolum_id}, $4)
    RETURNING id`, [ad, unvan, hs, IBAN]))[0].id;
  const p1 = await personel('Öğretmen A', 'Eğitim ve Öğretim Hizmetleri');
  const p2 = await personel('Usta B', 'Teknik Hizmetler', 'Teknisyen');
  const hizmetli = await personel('Hizmetli C', 'Yardımcı Hizmetler', 'Hizmetli');
  const sofor = await personel('Sürücü D', 'Genel İdare Hizmetleri', 'Şoför');

  const pbSiparis = await kaydet(SEF, { aciklama: 'Parça başı iş', miktar: '1', birim_fiyat: '1000' });
  await gonder(SEF, pbSiparis.id); await karar(TMY, pbSiparis.id, true); await karar(M1, pbSiparis.id, true);
  veri.ucret_esasi = 'Fazla Çalışma Ücreti';
  const siparis = await kaydet(SEF, { aciklama: 'Bahçe düzenleme', miktar: '1', birim_fiyat: '10000' });
  await gonder(SEF, siparis.id); await karar(TMY, siparis.id, true); await karar(M1, siparis.id, true);

  const gunSayisi = (y, a) => new Date(y, a, 0).getDate();
  const bos = (y, a) => Array.from({ length: gunSayisi(y, a) }, () => '0');
  const bordro = (y, a, ek = {}) => ({
    siparis_id: siparis.id, yil: y, ay: a, saat_ucreti: '67.50', azami_ucret: '67.50', ogretim_gunu_saat: '3',
    tatil_gunu_saat: '8', pazar_izinli: true, dv_orani: '0.00759', malzeme_maliyeti: '0', is_tanimi: 'Bahçe düzenleme',
    gun_turleri: Array.from({ length: gunSayisi(y, a) }, (_, i) => (i + 1 === gun && y === yil && a === ay ? 'T' : 'O')),
    ...ek });
  const bugun = saat => { const g = bos(yil, ay); g[gun - 1] = String(saat); return g; };
  const fcKaydet = (u, id, sur, v, k, istek) => rpc(u, 'public.dose_fc_kaydet($1,$2,$3,$4,$5)', [id, sur, v, k, istek]);
  const kisiler = [
    { personel_id: p1, gorev: 'Öğretmen', gv_orani: '0.15', gunler: bugun(5) },
    { personel_id: p2, gorev: 'Usta', gv_orani: '0.20', gunler: bugun(3) },
  ];

  await reddet(fcKaydet(OGR, null, null, bordro(yil, ay), kisiler, uid(953)), /Alan Şefi veya Teknik/);
  await reddet(fcKaydet(SEF, null, null, { ...bordro(yil, ay), siparis_id: pbSiparis.id }, kisiler, uid(954)), /parça başı esaslı olmayan/);
  await reddet(fcKaydet(SEF, null, null, { ...bordro(yil, ay), gun_turleri: ['O'] }, kisiler, uid(955)), /gün türü/);
  await reddet(fcKaydet(SEF, null, null, bordro(yil, ay), [{ ...kisiler[0], gunler: bugun(25) }], uid(956)), /en fazla 24/);
  await reddet(fcKaydet(SEF, null, null, bordro(yil, ay), [kisiler[0], kisiler[0]], uid(957)), /birden fazla/);

  const kayit = await fcKaydet(SEF, null, null, bordro(yil, ay), kisiler, uid(958));
  await reddet(fcKaydet(SEF, null, null, bordro(yil, ay), kisiler, uid(958)), /daha önce/);
  const h = kayit.hesap;
  assert.deepEqual(h.hatalar, []);
  assert.deepEqual(h.kisiler.map(k => [k.saat, k.brut, k.gelir_vergisi, k.damga_vergisi, k.net]),
    [['5', '337.50', '50.63', '2.56', '284.31'], ['3', '202.50', '40.50', '1.54', '160.46']]);
  assert.deepEqual(h.toplam, { saat: '8', brut: '540.00', gelir_vergisi: '91.13', damga_vergisi: '4.10', net: '444.77' });
  assert.equal(h.siparis_iscilik, '8400.00');
  assert.equal(h.gun_sinirlari[gun - 1], '8');

  // Next month: day types, Sunday, bayram, hourly cap, excluded staff, combined bordros and the labour cap.
  const [sy, sa] = ay === 12 ? [yil + 1, 1] : [yil, ay + 1];
  const dow = d => new Date(sy, sa - 1, d).getDay();
  const gunler = [...Array(gunSayisi(sy, sa)).keys()].map(i => i + 1);
  const pazar = gunler.find(d => dow(d) === 0), cumartesi = gunler.find(d => dow(d) === 6);
  const isGunu = gunler.find(d => dow(d) >= 1 && dow(d) <= 5), bayram = gunler.find(d => d !== isGunu && dow(d) >= 1 && dow(d) <= 5);
  const turler = gunler.map(d => (d === bayram ? 'B' : dow(d) === 6 ? 'T' : 'O'));
  const saatler = map => gunler.map(d => String(map[d] || 0));
  const sonraki = bordro(sy, sa, { gun_turleri: turler, pazar_izinli: false, saat_ucreti: '70', malzeme_maliyeti: '8000' });
  const ileri = await fcKaydet(SEF, null, null, sonraki, [
    { personel_id: p1, gv_orani: '0.15', gunler: saatler({ [isGunu]: 4, [pazar]: 2, [bayram]: 1, [cumartesi]: 8 }) },
    { personel_id: hizmetli, gv_orani: '0.15', gunler: saatler({ [cumartesi]: 1 }) },
    { personel_id: sofor, gv_orani: '0.15', gunler: saatler({ [cumartesi]: 1 }) },
  ], uid(959));
  const hata = ileri.hesap.hatalar.join('\n');
  for (const re of [/azami tutarı/, /Yardımcı Hizmetler/, /şoför/, /4 saat yazılmış; o gün için sınır 3/,
    /2 saat yazılmış; o gün için sınır 0/, /1 saat yazılmış; o gün için sınır 0/, /işçilik payını/]) assert.match(hata, re);
  assert.doesNotMatch(hata, /8 saat yazılmış/);
  const ek = await fcKaydet(SEF, null, null, { ...sonraki, saat_ucreti: '60', malzeme_maliyeti: '0' },
    [{ personel_id: p1, gv_orani: '0.15', gunler: saatler({ [cumartesi]: 1 }) }], uid(960));
  assert.match(ek.hesap.hatalar.join('\n'), /1 saat yazılmış \(diğer bordrolarda 8 saat daha\); o gün için sınır 8/);
  await reddet(rpc(SEF, 'public.dose_fc_gonder($1,$2)', [ek.id, ek.surum]), /çalışılmamış/);
  await rpc(SEF, 'public.dose_fc_iptal($1,$2,$3)', [ek.id, ek.surum, 'Mükerrer']);
  await rpc(SEF, 'public.dose_fc_iptal($1,$2,$3)', [ileri.id, ileri.surum, 'Hatalı']);

  // md.8/7 is enforced from the piece-rate side against the new overtime records.
  const pbTanim = (await db.query(`SELECT pg_get_functiondef('dose_private.pb_hesap(integer, integer)'::regprocedure) AS d`)).rows[0].d;
  assert.match(pbTanim, /dose_private\.fc_bordro f WHERE/);
  assert.match(pbTanim, /fc_idari\(p\.dose_gorevi\)/);
  assert.doesNotMatch(pbTanim, /public\.fazla_calisma/);

  // Approval chain, journal and bank payment.
  await assert.rejects(fcKaydet(SEF, kayit.id, kayit.surum + 1, bordro(yil, ay), kisiler, uid(961)), e => e.hint === 'surum_cakismasi');
  const g = await rpc(SEF, 'public.dose_fc_gonder($1,$2)', [kayit.id, kayit.surum]);
  assert.equal(g.durum, 'TMY Onayında');
  await reddet(rpc(M1, 'public.dose_fc_karar($1,$2,$3,$4)', [kayit.id, g.surum, true, '']), /sıradaki onay/);
  await reddet(rpc(TMY, 'public.dose_fc_karar($1,$2,$3,$4)', [kayit.id, g.surum, false, '']), /gerekçe/);
  const t = await rpc(TMY, 'public.dose_fc_karar($1,$2,$3,$4)', [kayit.id, g.surum, true, 'Uygundur']);
  const olur = await rpc(M1, 'public.dose_fc_karar($1,$2,$3,$4)', [kayit.id, t.surum, true, 'Olur']);
  assert.equal(olur.durum, 'Onaylandı');
  const fis = (await db.query('SELECT hesap_kodu, borc::text, alacak::text FROM public.yevmiye_satir WHERE yevmiye_id = $1 ORDER BY id',
    [olur.yevmiye_id])).rows;
  assert.deepEqual(fis, [{ hesap_kodu: '720', borc: '540.00', alacak: '0' }, { hesap_kodu: '335', borc: '0', alacak: '444.77' },
    { hesap_kodu: '360', borc: '0', alacak: '95.23' }]);
  const liste = await rpc(SEF, 'public.dose_fc_veri()');
  assert.equal(liste.bordrolar.find(b => b.id === kayit.id).onaylar.map(a => a.islem).join(','),
    'Hazırlandı,Onaya gönderildi,Uygundur,Olur');
  assert.deepEqual((await rpc(M2, 'public.dose_fc_veri()')).bordrolar, [], 'other school sees nothing');
  await reddet(as(SEF, 'SELECT * FROM dose_private.fc_bordro'), /permission denied/);
  await reddet(as(M1, `DELETE FROM public.personel WHERE id = ${hizmetli}`), /fazla çalışma bordrosunda/);

  const ode = istek => rpc(SAY, 'public.dose_fc_ode($1,$2,$3,$4)', [kayit.id, tarih, 'DEKONT-FC', istek]);
  await reddet(rpc(M1, 'public.dose_fc_ode($1,$2,$3,$4)', [kayit.id, tarih, 'X', uid(962)]), /sayman/);
  await rpc(SAY, 'public.dose_kasa_kaydet($1,$2,$3,$4,$5,$6,$7,$8,$9)',
    ['Açılış', 'Banka (102)', tarih, '1000', null, '500', null, 'Açılış', uid(963)]);
  const odeme = await ode(uid(964));
  assert.deepEqual([odeme.tutar, odeme.bakiye], ['444.77', '555.23']);
  await reddet(ode(uid(965)), /zaten ödendi/);
  await reddet(rpc(M1, 'public.dose_fc_iptal($1,$2,$3)', [kayit.id, olur.surum, 'Hatalı']), /Ödenmiş/);
  await rpc(SAY, 'public.dose_kasa_tersle($1,$2,$3)', [odeme.id, 'Yanlış dekont', uid(966)]);
  const iptal = await rpc(M1, 'public.dose_fc_iptal($1,$2,$3)', [kayit.id, olur.surum, 'Hatalı bordro']);
  assert.equal(iptal.durum, 'İptal');
  const mizan = (await db.query(`SELECT sum(borc - alacak)::text AS bakiye FROM public.yevmiye_satir
    WHERE hesap_kodu IN ('720', '335', '360') GROUP BY hesap_kodu`)).rows;
  assert.ok(mizan.every(r => Number(r.bakiye) === 0));
});

test('treasury share uses collected net sales per month, accrues 770/362, pays by bank and tracks tax deadlines', async () => {
  const { db, as, rpc, veri, kaydet, gonder, karar, tarih, onizle, kaydetFatura } = await faturaOrtami();
  const siparis = await kaydet(SEF, { aciklama: 'Satış', miktar: '1', birim_fiyat: '100' });
  await gonder(SEF, siparis.id); await karar(TMY, siparis.id, true); await karar(M1, siparis.id, true);
  const [kalem] = (await db.query('SELECT id FROM public.siparis_kalem WHERE siparis_id = $1', [siparis.id])).rows;
  const satis = { tur: 'Satış', no: 'HS-1', tarih, cari: veri.cari_id, siparis: siparis.id,
    kalemler: [{ siparis_kalem_id: kalem.id, malzeme_id: null, miktar: '1' }], tevkifat: '0', stopaj: '0', surumler: {} };
  const sf = await kaydetFatura(SAY, satis, (await onizle(SAY, satis)).imza, uid(1001));
  const kasa = (tur, tutar, fatura, karsi, istek) => rpc(SAY, 'public.dose_kasa_kaydet($1,$2,$3,$4,$5,$6,$7,$8,$9)',
    [tur, 'Banka (102)', tarih, tutar, fatura, karsi, null, 'İşlem', istek]);
  await kasa('Açılış', '1000', null, '500', uid(1002));
  await kasa('Tahsilat', '60', sf.id, null, uid(1003));

  // Move the sale and its collection into the previous (completed) month.
  const { gecen } = (await db.query(`SELECT (date_trunc('month', (now() AT TIME ZONE 'Europe/Istanbul')::date)
    - interval '1 month' + interval '14 days')::date::text AS gecen`)).rows[0];
  await db.exec(`SET session_replication_role = replica;
    UPDATE public.kasa_banka SET tarih = '${gecen}'; UPDATE public.fatura SET tarih = '${gecen}';
    UPDATE public.yevmiye SET tarih = '${gecen}' WHERE tarih = '${tarih}';
    SET session_replication_role = DEFAULT;`);
  const py = Number(gecen.slice(0, 4)), pa = Number(gecen.slice(5, 7));
  const ayVeri = async (u = SAY) => (await rpc(u, 'public.dose_hp_veri($1)', [py])).aylar.find(a => a.ay === pa);
  let ay = await ayVeri();
  assert.deepEqual([ay.hasilat, ay.tahmini_tutar, ay.tamamlandi], ['50.00', '0.50', true]);
  assert.ok(['Bildirilecek', 'Gecikmiş'].includes(ay.durum));
  assert.equal(ay.son_odeme, `${tarih.slice(0, 7)}-20`);
  assert.deepEqual([Number(ay.kdv.hesaplanan), Number(ay.kdv.odenecek)], [20, 20]);
  assert.equal(ay.kdv.son_gun, `${tarih.slice(0, 7)}-28`);
  assert.equal(ay.muhtasar.son_gun, `${tarih.slice(0, 7)}-26`);
  assert.equal((await rpc(M1, 'public.dose_hp_veri($1)', [py])).aylar.find(a => a.ay === pa).hasilat, '50.00');
  await reddet(rpc(OGR, 'public.dose_hp_veri()'), /erişim/);

  const bildir = (u, y, a, oran, istek) => rpc(u, 'public.dose_hp_bildir($1,$2,$3,$4,$5)', [y, a, oran, 'Örnek 30', istek]);
  const buYil = Number(tarih.slice(0, 4)), buAy = Number(tarih.slice(5, 7));
  await reddet(bildir(M1, py, pa, '0.01', uid(1004)), /sayman/);
  await reddet(bildir(SAY, buYil, buAy, '0.01', uid(1005)), /tamamlanmış/);
  await reddet(bildir(SAY, py, pa, '0', uid(1006)), /oran/);
  await reddet(bildir(SAY, 2000, 1, '0.01', uid(1007)), /hasılat bulunmadığından/);
  const b = await bildir(SAY, py, pa, '0.01', uid(1008));
  assert.deepEqual([b.hasilat, b.tutar, b.bildirim_no], ['50.00', '0.50', `HP-${py}-001`]);
  await reddet(bildir(SAY, py, pa, '0.01', uid(1009)), /zaten var/);
  await reddet(bildir(SAY, py, pa, '0.01', uid(1008)), /daha önce/);
  const fis = (await db.query('SELECT y.tarih, s.hesap_kodu, s.borc::text, s.alacak::text FROM public.yevmiye_satir s JOIN public.yevmiye y ON y.id = s.yevmiye_id WHERE y.id = $1 ORDER BY s.id',
    [b.yevmiye_id])).rows;
  assert.deepEqual(fis.map(r => [r.hesap_kodu, r.borc, r.alacak]), [['770', '0.50', '0'], ['362', '0', '0.50']]);
  assert.equal(fis[0].tarih.slice(0, 7), gecen.slice(0, 7));
  ay = await ayVeri();
  assert.ok(['Ödenecek', 'Gecikmiş'].includes(ay.durum));
  assert.equal(ay.kayit.hasilat_farki, '0.00');
  assert.equal((await rpc(M2, 'public.dose_hp_veri($1)', [py])).aylar.find(a => a.ay === pa).kayit, null, 'other school');
  await reddet(as(SAY, 'SELECT * FROM dose_private.hp_donem'), /permission denied/);

  const ode = istek => rpc(SAY, 'public.dose_hp_ode($1,$2,$3,$4)', [b.id, tarih, 'DEKONT-HP', istek]);
  await reddet(rpc(M1, 'public.dose_hp_ode($1,$2,$3,$4)', [b.id, tarih, 'X', uid(1010)]), /sayman/);
  const odeme = await ode(uid(1011));
  assert.deepEqual([odeme.tutar, odeme.bakiye], ['0.50', '1059.50']);
  await reddet(ode(uid(1012)), /zaten ödendi/);
  ay = await ayVeri();
  assert.equal(ay.durum, 'Ödendi');
  assert.equal(ay.kayit.odeme.belge_no, 'DEKONT-HP');
  await reddet(rpc(SAY, 'public.dose_hp_iptal($1,$2,$3)', [b.id, 1, 'Hatalı']), /Ödenmiş/);
  await rpc(SAY, 'public.dose_kasa_tersle($1,$2,$3)', [odeme.id, 'Yanlış dekont', uid(1013)]);
  await reddet(rpc(SAY, 'public.dose_hp_iptal($1,$2,$3)', [b.id, 2, 'Hatalı']), /güncelini/);
  await reddet(rpc(SAY, 'public.dose_hp_iptal($1,$2,$3)', [b.id, 1, ' ']), /gerekçesi/);
  const iptal = await rpc(SAY, 'public.dose_hp_iptal($1,$2,$3)', [b.id, 1, 'Hatalı oran']);
  assert.equal(iptal.durum, 'İptal');
  const yeni = await bildir(SAY, py, pa, '0.01', uid(1014));
  assert.equal(yeni.bildirim_no, `HP-${py}-002`);
  const veriSon = await rpc(SAY, 'public.dose_hp_veri($1)', [py]);
  assert.equal(veriSon.iptaller.length, 1);
  const bakiye = (await db.query(`SELECT sum(alacak - borc)::text AS b FROM public.yevmiye_satir WHERE hesap_kodu = '362'`)).rows[0].b;
  assert.equal(Number(bakiye), 0.5);
  assert.equal(Number((await db.query(`SELECT dose_private.hp_gecikme_ay('2026-01-20', '2026-03-21') AS g`)).rows[0].g), 3);
  assert.equal(Number((await db.query(`SELECT dose_private.hp_gecikme_ay('2026-01-20', '2026-01-20') AS g`)).rows[0].g), 0);
});

test('year-end closing splits profit into SHÇEK, ÜTP, capital and central shares to the cent and posts closing entries', async () => {
  const { db, as, rpc, veri, kaydet, gonder, karar, tarih, onizle, kaydetFatura } = await faturaOrtami();
  const siparis = await kaydet(SEF, { aciklama: 'Satış', miktar: '1', birim_fiyat: '100' });
  await gonder(SEF, siparis.id); await karar(TMY, siparis.id, true); await karar(M1, siparis.id, true);
  const [kalem] = (await db.query('SELECT id FROM public.siparis_kalem WHERE siparis_id = $1', [siparis.id])).rows;
  const satis = { tur: 'Satış', no: 'YS-S1', tarih, cari: veri.cari_id, siparis: siparis.id,
    kalemler: [{ siparis_kalem_id: kalem.id, malzeme_id: null, miktar: '1' }], tevkifat: '0', stopaj: '0', surumler: {} };
  const sf = await kaydetFatura(SAY, satis, (await onizle(SAY, satis)).imza, uid(1101));
  const kasa = (tur, tutar, fatura, karsi, istek) => rpc(SAY, 'public.dose_kasa_kaydet($1,$2,$3,$4,$5,$6,$7,$8,$9)',
    [tur, 'Banka (102)', tarih, tutar, fatura, karsi, null, 'İşlem', istek]);
  await kasa('Açılış', '1000', null, '500', uid(1102));
  await kasa('Tahsilat', '120', sf.id, null, uid(1103));
  const buYil = Number(tarih.slice(0, 4)), yil = buYil - 1, gecen = `${yil}-06-15`;
  await db.exec(`SET session_replication_role = replica;
    UPDATE public.kasa_banka SET tarih = '${gecen}'; UPDATE public.fatura SET tarih = '${gecen}';
    UPDATE public.yevmiye SET tarih = '${gecen}' WHERE tarih = '${tarih}';
    SET session_replication_role = DEFAULT;`);
  const iban = 'TR330006100519786457841326';
  const kisi = async (ad, gorev, bolum, ibanVar = true) => (await as(M1, `INSERT INTO public.personel
    (ad_soyad, hizmet_sinifi, dose_gorevi, bolum_id, iban) VALUES ($1, 'Eğitim ve Öğretim Hizmetleri', $2, $3, $4) RETURNING id`,
    [ad, gorev, bolum, ibanVar ? iban : null]))[0].id;
  const mudur = await kisi('Ayşe Müdür', 'Harcama Yetkilisi (Okul Müdürü)', null);
  const sayman = await kisi('Sena Sayman', 'Sayman', null);
  const og1 = await kisi('Ali Usta', 'Öğretmen', veri.bolum_id);
  const og2 = await kisi('Veli Usta', 'Öğretmen', veri.bolum_id, false);

  let v = await rpc(SAY, 'public.dose_ys_veri($1)', [yil]);
  assert.equal(v.tamamlandi, true);
  assert.equal(v.kayit, null);
  assert.deepEqual([v.on_hesap.gelir, v.on_hesap.gider, v.on_hesap.hasilat, v.on_hesap.shcek], ['100.00', '0', '100.00', '1.00']);
  assert.equal(v.bolumler.find(b => b.id === veri.bolum_id).gelir, '100.00');
  await reddet(rpc(OGR, 'public.dose_ys_veri()'), /erişim/);

  const param = { yil, utp_orani: '0.333333', tahsis_sermaye: '10000', odenmis_sermaye: '0', shcek_orani: '0.01',
    dv_orani: '0.00759', yillik_tavan: '396360', yuz_yuze: true, aciklama: 'Örnek kâr dağıtımı' };
  const satir = (personel_id, gorev, ek = {}) => ({ personel_id, gorev, unvan_grubu: 3, bolum_id: null, fiili_gun: '200',
    fc_saat: '0', katki_orani: '0', takdir_orani: '0', haric: false, onceki_utp: '0', gv_orani: '0.15', ...ek });
  const kisiler = [
    satir(mudur, 'Harcama Yetkilisi (Okul Müdürü)', { unvan_grubu: 1 }),
    satir(sayman, 'Sayman'),
    satir(og1, 'Öğretmen', { bolum_id: veri.bolum_id, katki_orani: '1', takdir_orani: '1' }),
    satir(og2, 'Öğretmen', { bolum_id: veri.bolum_id, katki_orani: '2', onceki_utp: '396350' })];
  const kaydetYs = (u, id, surum, p, k, istek) => rpc(u, 'public.dose_ys_kaydet($1,$2,$3,$4,$5)', [id, surum, p, k, istek]);
  await reddet(kaydetYs(M1, null, null, param, kisiler, uid(1104)), /sayman/);
  await reddet(kaydetYs(SAY, null, null, { ...param, utp_orani: '0.5' }, kisiler, uid(1105)), /ÜTP oranı/);
  await reddet(kaydetYs(SAY, null, null, param, [satir(mudur, 'Bilinmeyen')], uid(1106)), /görevini/);
  await reddet(kaydetYs(SAY, null, null, param, [satir(og1, 'Bölüm/Alan Şefi')], uid(1107)), /şefin bölümünü/);
  await reddet(kaydetYs(SAY, null, null, param, [satir(og1, 'Öğretmen', { haric: true })], uid(1108)), /nedenini/);
  await reddet(kaydetYs(SAY, null, null, param, [satir(og1, 'Öğretmen'), satir(og1, 'Öğretmen')], uid(1109)), /birden fazla/);
  const k = await kaydetYs(SAY, null, null, param, kisiler, uid(1110));
  await reddet(kaydetYs(SAY, null, null, param, kisiler, uid(1111)), /zaten var/);
  const h = k.hesap;
  assert.deepEqual([h.kar_oncesi, h.shcek, h.donem_kari, h.utp_azami, h.dagitima_esas, h.sermaye_payi],
    ['100.00', '1.00', '99.00', '33.00', '33.00', '33.00']);
  assert.deepEqual(h.havuzlar, { idari: '8.25', takdir: '1.65', bolum: '23.10' });
  assert.deepEqual(h.kisiler.map(x => [x.hesaplanan, x.brut, x.tavan_asimi, x.net]),
    [['2.64', '2.64', '0.00', '2.22'], ['1.65', '1.65', '0.00', '1.39'], ['9.35', '9.35', '0.00', '7.88'], ['15.40', '10.00', '5.40', '8.42']]);
  assert.deepEqual([h.dagitilan_utp, h.merkez_payi, h.toplam.net], ['23.64', '42.36', '19.91']);
  assert.equal(Number(h.dagitilan_utp) + Number(h.sermaye_payi) + Number(h.merkez_payi), Number(h.donem_kari));
  assert.ok(h.hatalar.some(x => /Veli Usta için IBAN/.test(x)));
  assert.ok(h.uyarilar.some(x => /Gerçekleştirme/.test(x)));
  assert.ok(h.uyarilar.some(x => /tavanı aşan 5.40/.test(x)));
  await reddet(rpc(SAY, 'public.dose_ys_gonder($1,$2)', [k.id, k.surum]), /IBAN/);
  await as(M1, 'UPDATE public.personel SET iban = $1 WHERE id = $2', [iban, og2]);
  await reddet(rpc(SAY, 'public.dose_ys_gonder($1,$2)', [k.id, 99]), /güncelini/);
  await rpc(SAY, 'public.dose_ys_gonder($1,$2)', [k.id, k.surum]);
  await reddet(kaydetYs(SAY, k.id, k.surum + 1, param, kisiler, uid(1112)), /taslak/);
  await reddet(rpc(SAY, 'public.dose_ys_karar($1,$2,$3,$4)', [k.id, k.surum + 1, true, '']), /Okul Müdürü/);
  await reddet(rpc(M1, 'public.dose_ys_karar($1,$2,$3,$4)', [k.id, k.surum + 1, false, ' ']), /gerekçesini/);
  await rpc(M1, 'public.dose_ys_karar($1,$2,$3,$4)', [k.id, k.surum + 1, false, 'Takdir puanlarını kontrol ediniz']);
  v = await rpc(SAY, 'public.dose_ys_veri($1)', [yil]);
  assert.equal(v.kayit.durum, 'Taslak');
  await rpc(SAY, 'public.dose_ys_gonder($1,$2)', [k.id, v.kayit.surum]);
  const onay = await rpc(M1, 'public.dose_ys_karar($1,$2,$3,$4)', [k.id, v.kayit.surum + 1, true, 'Uygundur']);
  assert.equal(onay.durum, 'Onaylandı');
  const fis = async id => (await db.query(`SELECT y.tarih, y.kaynak, s.hesap_kodu, s.borc::text, s.alacak::text
    FROM public.yevmiye_satir s JOIN public.yevmiye y ON y.id = s.yevmiye_id WHERE y.id = $1 ORDER BY s.id`, [id])).rows;
  const shcek = await fis(onay.shcek_yevmiye_id);
  assert.deepEqual(shcek.map(r => [r.hesap_kodu, r.borc, r.alacak]), [['770', '1.00', '0'], ['362', '0', '1.00']]);
  assert.equal(shcek[0].tarih, `${yil}-12-31`);
  const kapanis = await fis(onay.kapanis_yevmiye_id);
  assert.deepEqual(kapanis.map(r => [r.hesap_kodu, r.borc, r.alacak]),
    [['600', '100.00', '0'], ['770', '0', '1.00'], ['590', '0', '99.00']]);
  const dagitim = await fis(onay.dagitim_yevmiye_id);
  assert.deepEqual(dagitim.map(r => [r.hesap_kodu, r.borc, r.alacak]),
    [['590', '99.00', '0'], ['335', '0', '19.91'], ['360', '0', '3.73'], ['362', '0', '42.36'], ['500', '0', '33.00']]);
  const bakiye = async kod => Number((await db.query(`SELECT coalesce(sum(s.alacak - s.borc), 0)::text AS b FROM public.yevmiye_satir s
    JOIN public.yevmiye y ON y.id = s.yevmiye_id WHERE s.hesap_kodu ~ $1 AND y.tarih <= $2`, [kod, `${yil}-12-31`])).rows[0].b);
  assert.equal(await bakiye('^[67]'), 0);
  assert.equal(await bakiye('^590'), 0);
  assert.equal((await rpc(M2, 'public.dose_ys_veri($1)', [yil])).kayit, null, 'other school');
  await reddet(as(SAY, 'SELECT * FROM dose_private.ys_donem'), /permission denied/);
  await reddet(as(M1, 'DELETE FROM public.personel WHERE id = $1', [og1]), /ÜTP dağıtımında/);

  const ode = (kalem, istek, u = SAY) => rpc(u, 'public.dose_ys_ode($1,$2,$3,$4,$5)', [k.id, kalem, tarih, 'DEKONT', istek]);
  await reddet(ode('ÜTP', uid(1113), M1), /sayman/);
  await reddet(ode('Diğer', uid(1114)), /kalemi/);
  const o1 = await ode('ÜTP', uid(1115));
  const o2 = await ode('SHÇEK', uid(1116));
  const o3 = await ode('Merkez payı', uid(1117));
  assert.deepEqual([o1.tutar, o2.tutar, o3.tutar, o3.bakiye], ['19.91', '1.00', '42.36', '1056.73']);
  await reddet(ode('ÜTP', uid(1118)), /zaten yapıldı/);
  v = await rpc(SAY, 'public.dose_ys_veri($1)', [yil]);
  assert.equal(v.kayit.odemeler['ÜTP'].tutar, '19.91');
  assert.equal(v.kayit.hesap.donem_kari, '99.00');
  await reddet(rpc(M1, 'public.dose_ys_iptal($1,$2,$3)', [k.id, v.kayit.surum, 'Hatalı']), /Ödemesi yapılmış/);
  for (const [o, n] of [[o3, 1119], [o2, 1120], [o1, 1121]]) await rpc(SAY, 'public.dose_kasa_tersle($1,$2,$3)', [o.id, 'Yanlış', uid(n)]);
  await reddet(rpc(SAY, 'public.dose_ys_iptal($1,$2,$3)', [k.id, v.kayit.surum, 'Hatalı']), /Okul Müdürü/);
  const iptal = await rpc(M1, 'public.dose_ys_iptal($1,$2,$3)', [k.id, v.kayit.surum, 'Hatalı sermaye tutarı']);
  assert.equal(iptal.ters_yevmiye_idler.length, 3);
  assert.equal(await bakiye('^590'), 0);
  assert.equal(await bakiye('^6'), 100);
  assert.equal(await bakiye('^7'), 0);
  const yeni = await kaydetYs(SAY, null, null, { ...param, odenmis_sermaye: '10000' }, kisiler, uid(1122));
  assert.equal(Number(yeni.hesap.sermaye_payi), 0);
  assert.equal(yeni.hesap.donem_kari, '99.00');
  assert.equal(Number(yeni.hesap.merkez_payi), 75.36);
  v = await rpc(SAY, 'public.dose_ys_veri($1)', [yil]);
  assert.equal(v.iptaller.length, 1);
  assert.equal(v.kayit.belge_no, `YS-${yil}-02`);

  const cari = await kaydetYs(SAY, null, null, { ...param, yil: buYil }, kisiler, uid(1123));
  await reddet(rpc(SAY, 'public.dose_ys_gonder($1,$2)', [cari.id, cari.surum]), /Yıl tamamlanmadan/);
  const dagit = (await db.query(`SELECT dose_private.ys_dagit(0.10, '{"a":1,"b":1,"c":1}') AS d`)).rows[0].d;
  assert.deepEqual(Object.values(dagit).map(Number).sort(), [0.03, 0.03, 0.04]);
});

test('dashboard tasks, verified rates gate payroll, cash transfer and official docs', async () => {
  const { db, as, rpc, veri, kaydet, gonder, karar, tarih } = await faturaOrtami();
  const yil = tarih.slice(0, 4);
  await as(null, 'SELECT dose_private.mevzuat_yoneticisi_ata($1,$2,$3)', [MERKEZ, 'Merkez Yönetici', true], 'service_role');

  await reddet(rpc(SEF, 'public.dose_pb_kaydet($1,$2,$3,$4,$5,$6)',
    [null, null, { siparis_id: 1 }, [], [], uid(1201)]), /doğrulanmış merkez parametre|sipariş/i);

  const degerler = {
    pb_kar_orani: '0.05', pb_faaliyet_orani: '0.11',
    os_kar_orani: '0.10', os_faaliyet_orani: '0.40', os_pesin_orani: '0.25',
    tesis_kar_orani: '0.15', tesis_faaliyet_orani: '0.55', tesis_pesin_orani: '0.25',
    ogrenci_hakki_orani: '0.30', malzeme_azami_orani: '0.60',
  };
  const yayin = await rpc(MERKEZ, 'public.dose_mevzuat_yayinla($1,$2,$3,$4)', [`${yil}-01-01`, 'Test kaynağı', degerler, uid(1202)]);
  const aktifYok = await rpc(SAY, 'public.dose_mevzuat_aktif()');
  assert.equal(aktifYok.var, false);
  await rpc(SAY, 'public.dose_mevzuat_karar($1,$2,$3,$4)', [yayin.id, true, 'Kontrol edildi', uid(1203)]);
  const aktif = await rpc(SAY, 'public.dose_mevzuat_aktif()');
  assert.equal(aktif.var, true);
  assert.equal(aktif.degerler.pb_kar_orani, '0.05');

  const siparis = await kaydet(SEF, { aciklama: 'Görev', miktar: '1', birim_fiyat: '100' });
  await gonder(SEF, siparis.id);
  let gorev = await rpc(TMY, 'public.dose_gorevlerim()');
  assert.ok(gorev.gorevler.some(g => g.tur === 'siparis' && g.sayfa === 'siparis'));
  await karar(TMY, siparis.id, true);
  gorev = await rpc(M1, 'public.dose_gorevlerim()');
  assert.ok(gorev.gorevler.some(g => g.tur === 'siparis'));

  const [urun] = await as(SAY, `INSERT INTO public.urun (ad, tur, birim, satis_fiyati, bolum_id)
    VALUES ('Mamul', 'Mal', 'Adet', 50, ${veri.bolum_id}) RETURNING id`);
  const maliyet = await rpc(SAY, 'public.dose_maliyet_kaydet($1,$2,$3)', [urun.id, [
    { kalem_turu: 'Malzeme', miktar: '2', birim: 'Adet', birim_fiyat: '10' },
    { kalem_turu: 'İşçilik', miktar: '1', birim: 'Saat', birim_fiyat: '5' },
  ], uid(1204)]);
  assert.equal(maliyet.toplam, '25.00');
  assert.equal(maliyet.kalemler.length, 2);

  await rpc(SAY, 'public.dose_kasa_kaydet($1,$2,$3,$4,$5,$6,$7,$8,$9)',
    ['Açılış', 'Kasa (100)', tarih, '200', null, '500', '', 'Açılış', uid(1205)]);
  await rpc(SAY, 'public.dose_kasa_kaydet($1,$2,$3,$4,$5,$6,$7,$8,$9)',
    ['Açılış', 'Banka (102)', tarih, '10', null, '500', '', 'Açılış', uid(1206)]);
  const virman = await rpc(SAY, 'public.dose_kasa_kaydet($1,$2,$3,$4,$5,$6,$7,$8,$9)',
    ['Virman', 'Kasa (100)', tarih, '40', null, null, 'VR-1', 'Kasa bankaya', uid(1207)]);
  assert.ok(virman.yevmiye_id);
  const bakiyeler = (await rpc(SAY, 'public.dose_kasa_veri()')).hesaplar;
  assert.equal(bakiyeler.find(h => h.hesap === 'Kasa (100)').bakiye, '160');
  assert.equal(bakiyeler.find(h => h.hesap === 'Banka (102)').bakiye, '50');
  await rpc(SAY, 'public.dose_kasa_kaydet($1,$2,$3,$4,$5,$6,$7,$8,$9)',
    ['Avans', 'Kasa (100)', tarih, '20', null, '159', 'AV-1', 'Personel avansı', uid(1208)]);
  await rpc(SAY, 'public.dose_kasa_kaydet($1,$2,$3,$4,$5,$6,$7,$8,$9)',
    ['Faturasız gelir', 'Kasa (100)', tarih, '5', null, '649', '', 'Bağış', uid(1209)]);

  const resmi = await rpc(SAY, 'public.dose_resmi_kaydet($1,$2,$3,$4)',
    [null, null, { tarih, konu: 'Bilgi yazısı', muhatap: 'İl Milli Eğitim', govde: 'Resmi yazı metni burada.' }, uid(1210)]);
  assert.equal(resmi.yazilar.length, 1);
  assert.match(resmi.yazilar[0].yazi_no, /^RY-/);

  const denetim = await rpc(SAY, 'public.dose_denetim_kaydet($1,$2,$3,$4)', [null, null, {
    tarih, denetci: 'İç Denetçi', kapsam: 'Kasa ve stok', bulgular: 'Eksik yok.', sonuc: 'Uygun',
  }, uid(1211)]);
  assert.equal(denetim.formlar.length, 1);

  const rapor = await rpc(SAY, 'public.dose_rapor_ozet($1)', [Number(yil)]);
  assert.equal(rapor.yil, Number(yil));
  assert.ok(Number(rapor.siparis) >= 1);
  assert.equal(rapor.kasa_bakiye, '145');

  const pbVeri = await rpc(SEF, 'public.dose_pb_veri()');
  assert.ok(pbVeri.mevzuat && pbVeri.mevzuat.degerler.pb_kar_orani === '0.05');
});