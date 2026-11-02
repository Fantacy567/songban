/* Opt-in loopback check against S00's synthetic P1 backend. Never starts/stops it. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { pathToFileURL } = require('node:url');
const { request, chromium } = require('playwright');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '../../..');
const out = 'E:/松伴/outputs/learning-p1-20261102/S05/integration';
const origin = 'http://127.0.0.1:8897';
const prefix = '/api/learning/v2';
async function main() {
  assert.equal(process.argv[2], '--synthetic-8897', 'Explicit synthetic backend opt-in required');
  fs.mkdirSync(out, { recursive: true });
  const client = await request.newContext({ baseURL: origin, extraHTTPHeaders: { Origin: origin } });
  const result = { backend: origin, syntheticOnly: true, mutations: ['sessions/authenticate only'], checks: [] };
  let browser;
  try {
    async function get(p) { const r = await client.get(prefix + p); assert.equal(r.status(), 200, `GET ${p}`); return r.json(); }
    const boot = await get('/session-bootstrap');
    const auth = await client.post(prefix + '/sessions/authenticate', { headers: { 'X-CSRF-Token': boot.csrf_token }, data: { request_id: crypto.randomUUID(), browser_revision: boot.browser_revision, method: 'password', account: 'family-demo', proof: 'p1-fixture-password' } });
    assert.equal(auth.status(), 200); result.checks.push('synthetic-password-authenticated');
    const config = await get('/config'), families = await get('/families');
    assert.ok(Array.isArray(families.items)); assert.equal(families.next_cursor, null);
    result.checks.push('families-items-envelope-compatible');
    const consents = [];
    for (const f of families.items) {
      const family = await get('/families/' + encodeURIComponent(f.id));
      for (const l of family.learners) consents.push(await get(`/learners/${encodeURIComponent(l.id)}/consents`));
    }
    const texts = [];
    for (const v of new Set([config.consent_version, ...consents.flatMap(c => c.items.map(i => i.consent_version))])) texts.push(await get('/consent-texts/' + encodeURIComponent(v)));
    result.familyCount = families.items.length;
    result.consentKeyOrder = texts.map(t => ({ version: t.consent_version, purposeKeys: t.scope_purposes.map(p => Object.keys(p)) }));
    result.legacyConsumerHashesMatch = texts.map(t => crypto.createHash('sha256').update(JSON.stringify({ locale: t.locale, title: t.title, text: t.text, scope_purposes: t.scope_purposes })).digest('hex') === t.text_sha256);
    fs.writeFileSync(path.join(out, 'synthetic-responses.json'), JSON.stringify({ config, families, consents, texts }, null, 2));
    await esbuild.build({ entryPoints: [path.join(root, 'frontend/learning/consent.ts')], bundle: true, platform: 'node', format: 'esm', outfile: path.join(out, 'consent.mjs') });
    const { verifyConsentText } = await import(pathToFileURL(path.join(out, 'consent.mjs')).href);
    for (const t of texts) await verifyConsentText(t, t.consent_version);
    result.checks.push('actual-backend-texts-pass-consumer-hash');
    await esbuild.build({ entryPoints: [path.join(root, 'frontend/learning/index.tsx')], bundle: true, jsx: 'automatic', format: 'iife', target: 'es2022', outfile: path.join(out, 'learning.js'), define: { 'process.env.NODE_ENV': '"production"' } });
    browser = await chromium.launch({ headless: true, channel: 'msedge' });
    // Independent headless context, not S00's CUA/browser session.
    const context = await browser.newContext({ viewport: { width: 1280, height: 1000 }, storageState: await client.storageState(), serviceWorkers: 'block' });
    const unexpectedWrites = [], errors = [], apiStatuses = [];
    await context.route('**/*', route => {
      const req = route.request(), u = new URL(req.url());
      if (u.origin !== origin) return route.abort();
      if (u.pathname === '/static/learning/learning.js') return route.fulfill({ path: path.join(out, 'learning.js'), contentType: 'text/javascript' });
      if (u.pathname === '/static/learning/learning.css') return route.fulfill({ path: path.join(out, 'learning.css'), contentType: 'text/css' });
      if (req.method() !== 'GET') { unexpectedWrites.push(req.method() + ' ' + u.pathname); return route.abort(); }
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('response', r => { const u = new URL(r.url()); if (u.pathname.startsWith(prefix)) apiStatuses.push({ path: u.pathname, status: r.status() }); });
    await page.goto(origin + '/learning-prep#/family');
    const ready = families.items.length ? page.getByRole('heading', { name: families.items[0].learners[0]?.display_name || '填写孩子资料', exact: true }) : page.getByRole('button', { name: '建立本人家庭', exact: true });
    if (families.items.length && !families.items[0].learners.length) await page.getByRole('group', { name: '填写孩子资料' }).waitFor(); else await ready.waitFor();
    assert.equal(await page.getByText('暂时没读到完整家庭或授权内容，尚不能确认当前状态。', { exact: true }).count(), 0);
    await page.screenshot({ path: path.join(out, 'family-live-backend.png'), fullPage: true });
    await page.reload();
    if (families.items.length && !families.items[0].learners.length) await page.getByRole('group', { name: '填写孩子资料' }).waitFor(); else await ready.waitFor();
    assert.deepEqual(unexpectedWrites, []); assert.deepEqual(errors, []);
    result.checks.push('independent-browser-family-renders', 'independent-browser-refresh-recovers', 'no-domain-writes-or-runtime-errors');
    result.apiStatuses = apiStatuses;
  } finally {
    await browser?.close(); await client.dispose();
    fs.writeFileSync(path.join(out, 'integration-results.json'), JSON.stringify(result, null, 2));
  }
  console.log(JSON.stringify(result));
}
main().catch(e => { console.error(e); process.exitCode = 1; });
