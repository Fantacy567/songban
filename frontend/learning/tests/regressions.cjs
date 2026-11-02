/* Offline regressions for the 8897 integration findings; no backend required. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '../../..');
const out = process.env.SONGBAN_LEARNING_REGRESSION_EVIDENCE || 'E:/松伴/outputs/learning-p1-20261102/S05/regressions';
const results = [];
async function main() {
  fs.mkdirSync(out, { recursive: true });
  await esbuild.build({ entryPoints: [path.join(root, 'frontend/learning/consent.ts')], bundle: true, platform: 'node', format: 'esm', outfile: path.join(out, 'consent.mjs') });
  const { verifyConsentText } = await import(pathToFileURL(path.join(out, 'consent.mjs')).href);
  // Independent vector observed from S00's synthetic backend, not a hash computed
  // by the consumer under test. Transport keys are recursively alphabetized.
  const vector = { acceptance_enabled: true, approval_status: 'approved_for_pilot', approved_at: '2026-11-02T00:00:00+00:00', consent_version: 'fiction-only-v1', locale: 'zh-CN', notice: '仅本次临时虚构数据库，禁止用于真实家庭', scope_purposes: [{ purpose: '虚构起点保存', scope: 'learning' }, { purpose: '虚构过程摘要', scope: 'parent_summary' }], text: '仅用于自动化联调，不是真实监护授权，不用于真实儿童服务。', text_sha256: '39eb178cebdd47bfd1024f146fdba5d135fd7c814ead2a2846a11721bced81b6', title: '虚构隔离测试授权' };
  const verify = t => verifyConsentText(t, vector.consent_version);
  await verify(vector); results.push('backend-sorted-json-vector-accepted');
  await verify({ ...vector, scope_purposes: vector.scope_purposes.map(p => ({ scope: p.scope, purpose: p.purpose })) }); results.push('member-order-independent');
  const mismatch = e => e.code === 'consent_text_mismatch';
  await assert.rejects(verify({ ...vector, text: vector.text + '改动' }), mismatch); results.push('modified-body-rejected');
  await assert.rejects(verify({ ...vector, scope_purposes: [{ ...vector.scope_purposes[0], purpose: '改动用途' }, vector.scope_purposes[1]] }), mismatch); results.push('modified-purpose-rejected');
  await assert.rejects(verify({ ...vector, scope_purposes: [...vector.scope_purposes].reverse() }), mismatch); results.push('purpose-array-order-preserved');
  await assert.rejects(verifyConsentText(vector, 'wrong-version'), mismatch); results.push('wrong-version-rejected');
  await verify({ ...vector, approval_status: 'withdrawn', acceptance_enabled: false }); results.push('approval-metadata-not-rehashed');
  await esbuild.build({ entryPoints: [path.join(root, 'frontend/learning/tests/family-lifecycle.tsx')], bundle: true, jsx: 'automatic', format: 'iife', outfile: path.join(out, 'family-lifecycle.js'), define: { 'process.env.NODE_ENV': '"development"' } });
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    const page = await browser.newPage(); const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/*', route => route.request().url().endsWith('/harness.js') ? route.fulfill({ path: path.join(out, 'family-lifecycle.js'), contentType: 'text/javascript' }) : route.fulfill({ contentType: 'text/html', body: '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><div id="host"></div><script src="/harness.js"></script></html>' }));
    await page.goto('https://family-lifecycle.fixture.invalid/');
    await page.evaluate(() => { familyHarness.hold('old'); familyHarness.render('old'); });
    await page.getByText('正在读取本人家庭和授权记录…', { exact: true }).waitFor();
    await page.evaluate(() => familyHarness.render('new'));
    await page.getByText('文本 new', { exact: true }).waitFor(); results.push('config-version-effect-restart-recovers');
    await page.evaluate(() => familyHarness.release('old'));
    await page.waitForFunction(() => familyHarness.completed.includes('old'));
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await page.getByText('文本 old', { exact: true }).count(), 0);
    assert.ok(await page.getByText('文本 new', { exact: true }).isVisible()); results.push('older-read-cannot-overwrite-new-config');
    await page.evaluate(() => { familyHarness.empty(); familyHarness.render('strict', true); });
    await page.getByRole('button', { name: '建立本人家庭', exact: true }).click();
    await page.getByRole('group', { name: '填写孩子资料', exact: true }).waitFor();
    results.push('strict-effect-replay-and-mutation-reload');
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ scope: 'offline integration regression; synthetic inputs only', passed: results.length, results }, null, 2));
  console.log(JSON.stringify({ passed: results.length, results }));
}
main().catch(e => { console.error(e); process.exitCode = 1; });
