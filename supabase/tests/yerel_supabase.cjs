// Local stand-in for a Supabase project, used only by the end-to-end test (tests/test_uctan_uca.py).
// Loads every migration into PGlite and serves the Auth / PostgREST subset the Flet client uses, executing
// each request as the anon or authenticated role so the real RLS policies, triggers and grants apply.
// Usage: node yerel_supabase.cjs <port>   (prints "HAZIR <port>" when ready; listens on 127.0.0.1 only)
const { PGlite } = require('@electric-sql/pglite');
const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const KOK = path.join(__dirname, '..', 'migrations');
const KIMLIK = /^[a-z_][a-z0-9_]*$/;

const kullanicilar = new Map(); // email -> {id, sifre}
const belirtecler = new Map(); // access token -> uid
const yenilemeler = new Map(); // refresh token -> uid

let sira = Promise.resolve();
const kuyruk = is => (sira = sira.then(is, is));

async function kur() {
  const db = new PGlite();
  await db.exec(`
    CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN;
    CREATE SCHEMA auth; GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
    CREATE TABLE auth.users (id uuid PRIMARY KEY, email text, email_confirmed_at timestamptz, last_sign_in_at timestamptz);
    CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
      $$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
    GRANT EXECUTE ON FUNCTION auth.uid() TO anon, authenticated;
    GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;`);
  for (const f of fs.readdirSync(KOK).filter(f => f.endsWith('.sql')).sort()) {
    try { await db.exec(fs.readFileSync(path.join(KOK, f), 'utf8')); } catch (e) { e.message = `${f}: ${e.message}`; throw e; }
  }
  return db;
}

class Yanit extends Error {
  constructor(durum, govde) { super(JSON.stringify(govde)); this.durum = durum; this.govde = govde; }
}

const kimlik = ad => { if (!KIMLIK.test(ad)) throw new Yanit(400, { code: 'PGRST100', message: `bad identifier ${ad}` }); return `"${ad}"`; };

function oturumAc(uid, email) {
  const access = 'erisim-' + crypto.randomUUID(), refresh = 'yenile-' + crypto.randomUUID();
  belirtecler.set(access, uid);
  yenilemeler.set(refresh, uid);
  return { access_token: access, refresh_token: refresh, token_type: 'bearer', expires_in: 3600, user: { id: uid, email } };
}

// Runs one request in its own transaction with PostgREST's role switching; maps errors to PostgREST JSON.
async function calistir(db, uid, sql, params) {
  return kuyruk(() => db.transaction(async tx => {
    await tx.query("SELECT set_config('request.jwt.claim.sub', $1, true)", [uid || '']);
    await tx.exec(`SET LOCAL ROLE ${uid ? 'authenticated' : 'anon'}`);
    return (await tx.query(sql, params)).rows;
  })).catch(e => {
    if (e instanceof Yanit) throw e;
    if (!e.code) throw e;
    const durum = e.code === '42501' ? (uid ? 403 : 401) : e.code === '23505' ? 409 : e.code === '42883' ? 404 : 400;
    throw new Yanit(durum, { code: e.code, message: e.message, details: e.detail || null, hint: e.hint || null });
  });
}

function filtreler(sorgu, params) {
  const kosul = [];
  for (const [k, v] of sorgu) {
    if (['select', 'order', 'limit'].includes(k)) continue;
    const [op, ...geri] = v.split('.');
    const deger = geri.join('.');
    if (op === 'eq') { params.push(deger); kosul.push(`${kimlik(k)} = $${params.length}`); }
    else if (op === 'is' && ['null', 'true', 'false'].includes(deger)) kosul.push(`${kimlik(k)} IS ${deger.toUpperCase()}`);
    else throw new Yanit(400, { code: 'PGRST100', message: `unsupported filter ${k}=${v}` });
  }
  return kosul.length ? ' WHERE ' + kosul.join(' AND ') : '';
}

const jsonDeger = v => (v !== null && typeof v === 'object') ? JSON.stringify(v) : v;

async function rest(db, uid, yontem, tablo, sorgu, govde) {
  const params = [];
  const t = `public.${kimlik(tablo)}`;
  if (yontem === 'GET') {
    const secim = (sorgu.get('select') || '*') === '*' ? '*' : sorgu.get('select').split(',').map(kimlik).join(', ');
    let sql = `SELECT ${secim} FROM ${t}${filtreler(sorgu, params)}`;
    if (sorgu.get('order')) {
      sql += ' ORDER BY ' + sorgu.get('order').split(',').map(p => {
        const [ad, yon] = p.split('.');
        return kimlik(ad) + (yon === 'desc' ? ' DESC' : yon === 'asc' || !yon ? ' ASC' : (() => { throw new Yanit(400, {}); })());
      }).join(', ');
    }
    if (sorgu.get('limit')) sql += ` LIMIT ${parseInt(sorgu.get('limit'), 10)}`;
    return (await calistir(db, uid, `SELECT coalesce(json_agg(x), '[]'::json) AS j FROM (${sql}) x`, params))[0].j;
  }
  let sql;
  if (yontem === 'POST') {
    const alanlar = Object.keys(govde);
    const degerler = alanlar.map(a => { params.push(jsonDeger(govde[a])); return `$${params.length}`; });
    sql = `INSERT INTO ${t} (${alanlar.map(kimlik).join(', ')}) VALUES (${degerler.join(', ')}) RETURNING *`;
  } else if (yontem === 'PATCH') {
    const atama = Object.keys(govde).map(a => { params.push(jsonDeger(govde[a])); return `${kimlik(a)} = $${params.length}`; });
    sql = `UPDATE ${t} SET ${atama.join(', ')}${filtreler(sorgu, params)} RETURNING *`;
  } else if (yontem === 'DELETE') {
    sql = `DELETE FROM ${t}${filtreler(sorgu, params)} RETURNING *`;
  } else throw new Yanit(405, { message: 'method' });
  return (await calistir(db, uid, `WITH x AS (${sql}) SELECT coalesce(json_agg(x), '[]'::json) AS j FROM x`, params))[0].j;
}

async function rpc(db, uid, ad, govde) {
  const params = [], args = [];
  for (const [k, v] of Object.entries(govde || {})) { params.push(jsonDeger(v)); args.push(`${kimlik(k)} => $${params.length}`); }
  const varmi = await kuyruk(() => db.query(
    "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'public' AND p.proname = $1", [ad]));
  if (!varmi.rows.length) throw new Yanit(404, { code: 'PGRST202', message: `Could not find the function public.${ad}` });
  return (await calistir(db, uid, `SELECT to_json(public.${kimlik(ad)}(${args.join(', ')})) AS j`, params))[0].j;
}

async function auth(db, yontem, yol, sorgu, govde, uid) {
  const email = (govde && govde.email || '').toLowerCase();
  if (yol === '/auth/v1/signup') {
    if (kullanicilar.has(email)) throw new Yanit(422, { code: 422, error_code: 'user_already_exists', msg: 'User already registered' });
    if (!govde.password || govde.password.length < 6) throw new Yanit(422, { code: 422, error_code: 'weak_password', msg: 'weak' });
    const id = crypto.randomUUID();
    kullanicilar.set(email, { id, sifre: govde.password });
    await kuyruk(() => db.query('INSERT INTO auth.users (id, email) VALUES ($1, $2)', [id, email]));
    return { id, email, confirmation_sent_at: new Date().toISOString() }; // mailer_autoconfirm = false
  }
  if (yol === '/auth/v1/token' && sorgu.get('grant_type') === 'password') {
    const k = kullanicilar.get(email);
    if (!k || k.sifre !== govde.password) throw new Yanit(400, { code: 400, error_code: 'invalid_credentials', msg: 'Invalid login credentials' });
    const r = await kuyruk(() => db.query('UPDATE auth.users SET last_sign_in_at = now() WHERE id = $1 RETURNING email_confirmed_at', [k.id]));
    if (!r.rows[0].email_confirmed_at) throw new Yanit(400, { code: 400, error_code: 'email_not_confirmed', msg: 'Email not confirmed' });
    return oturumAc(k.id, email);
  }
  if (yol === '/auth/v1/token' && sorgu.get('grant_type') === 'refresh_token') {
    const u = yenilemeler.get(govde.refresh_token);
    if (!u) throw new Yanit(400, { code: 400, error_code: 'refresh_token_not_found', msg: 'Invalid Refresh Token' });
    yenilemeler.delete(govde.refresh_token);
    return oturumAc(u, null);
  }
  if (yol === '/auth/v1/logout') {
    for (const [b, u] of belirtecler) if (u === uid) belirtecler.delete(b);
    return null;
  }
  if (yol === '/auth/v1/recover' || yol === '/auth/v1/resend') return {};
  throw new Yanit(404, { message: 'not emulated: ' + yol });
}

// Test-only control endpoints (the vendor's SQL editor and the "click the link in the e-mail" step).
async function kontrol(db, yol, govde) {
  if (yol === '/_test/sql') return (await kuyruk(() => db.query(govde.sql, govde.params || []))).rows;
  if (yol === '/_test/onayla') {
    await kuyruk(() => db.query('UPDATE auth.users SET email_confirmed_at = now() WHERE email = $1', [govde.email.toLowerCase()]));
    return {};
  }
  throw new Yanit(404, { message: 'yok' });
}

async function main() {
  const db = await kur();
  const sunucu = http.createServer((istek, cevap) => {
    let parca = '';
    istek.setEncoding('utf8');
    istek.on('data', d => { parca += d; });
    istek.on('end', async () => {
      const url = new URL(istek.url, 'http://yerel');
      const yol = url.pathname;
      try {
        const govde = parca ? JSON.parse(parca) : null;
        if (!istek.headers.apikey) throw new Yanit(401, { message: 'No API key found in request' });
        let uid = null;
        const yetki = istek.headers.authorization || '';
        if (yetki.startsWith('Bearer ')) {
          uid = belirtecler.get(yetki.slice(7));
          if (!uid) throw new Yanit(401, { code: 'PGRST301', message: 'JWT expired' });
        }
        let sonuc;
        if (yol.startsWith('/_test/')) sonuc = await kontrol(db, yol, govde);
        else if (yol.startsWith('/auth/v1/')) sonuc = await auth(db, istek.method, yol, url.searchParams, govde, uid);
        else if (yol.startsWith('/rest/v1/rpc/')) sonuc = await rpc(db, uid, yol.slice(13), govde);
        else if (yol.startsWith('/rest/v1/')) sonuc = await rest(db, uid, istek.method, yol.slice(9), url.searchParams, govde);
        else throw new Yanit(404, { message: 'yok' });
        if (sonuc === null || sonuc === undefined) { cevap.writeHead(204); cevap.end(); return; }
        cevap.writeHead(200, { 'Content-Type': 'application/json' });
        cevap.end(JSON.stringify(sonuc));
      } catch (e) {
        const y = e instanceof Yanit ? e : new Yanit(500, { message: String(e && e.message || e) });
        cevap.writeHead(y.durum, { 'Content-Type': 'application/json' });
        cevap.end(JSON.stringify(y.govde));
      }
    });
  });
  const port = parseInt(process.argv[2] || '0', 10);
  sunucu.listen(port, '127.0.0.1', () => console.log(`HAZIR ${sunucu.address().port}`));
}

main().catch(e => { console.error(e); process.exit(1); });
