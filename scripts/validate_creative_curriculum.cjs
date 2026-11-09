/* Run the exact draft examples in a browser. This checks code, not learning. */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const directory = path.join(root, 'curriculum/creative-studio');
const curriculum = JSON.parse(fs.readFileSync(path.join(directory, 'first-web-v1.json'), 'utf8'));
const cases = [
  {id:'events', lesson:'events'},
  {id:'state', lesson:'state'},
  {id:'state-step-two', lesson:'state', from:'const step = 1;', to:'const step = 2;'},
  {id:'state-start-five', lesson:'state', from:'let count = 0;', to:'let count = 5;'},
  {id:'state-no-render', lesson:'state', from:'  output.textContent = String(count);', to:'  // 本实验只改变量，暂不更新显示。'},
  {id:'conditions', lesson:'conditions'},
  {id:'conditions-strict', lesson:'conditions', from:'count >= target', to:'count > target'},
  {id:'conditions-equal', lesson:'conditions', from:'count >= target', to:'count === target'},
  {id:'conditions-target-five', lesson:'conditions', from:'const target = 3;', to:'const target = 5;'},
];
const assets = new Map(), hashes = {};
for (const item of cases) {
  for (const filename of ['index.html', 'script.js']) {
    const relative = `examples/${item.lesson}/${filename}`;
    let data = fs.readFileSync(path.join(directory, relative), 'utf8');
    hashes[relative] = crypto.createHash('sha256').update(data).digest('hex');
    if (item.from && filename === 'script.js') {
      assert.equal(data.split(item.from).length, 2, 'Each variant changes exactly one documented expression');
      data = data.replace(item.from, item.to);
    }
    assets.set(`/${item.id}/${filename}`, data);
  }
}
const server = http.createServer((req, res) => {
  const data = assets.get(req.url);
  res.writeHead(data ? 200 : 404, {
    'Content-Type': req.url.endsWith('.js') ? 'text/javascript; charset=utf-8' : 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
    'Content-Security-Policy': "default-src 'none'; script-src 'self'; connect-src 'none'; base-uri 'none'; form-action 'none'",
  });
  res.end(data || 'Not found');
});
const checks = [], errors = [], outside = [];
let browser;
const out = process.env.SONGBAN_CURRICULUM_EVIDENCE || path.resolve(root, '../outputs/curriculum-technical-' + Date.now());
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  try {
    browser = await chromium.launch({headless:true, channel:'msedge'});
    const context = await browser.newContext();
    await context.route('**/*', route => {
      const u = new URL(route.request().url());
      if (u.origin === origin) return route.continue();
      outside.push(u.origin); return route.abort();
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    const open = async id => { await page.goto(`${origin}/${id}/index.html`); };
    const click = async n => { for (let i=0; i<n; i++) await page.locator('#add').click(); };
    const value = () => page.locator('#count').textContent();
    const check = async (id, fn) => { await fn(); checks.push({id, passed:true}); console.log('PASS ' + id); };
    await check('event-is-triggered-by-click-and-reset-has-distinct-behavior', async () => {
      await open('events'); assert.equal(await page.locator('#result').textContent(), '');
      await page.locator('#hello').click(); assert.equal(await page.locator('#result').textContent(), '你好，这是我想说的话！');
      await page.locator('#reset').click(); assert.equal(await page.locator('#result').textContent(), '');
    });
    await check('changing-button-label-does-not-change-handler', async () => {
      await page.locator('#hello').evaluate(button => {button.textContent = '我改了按钮名字';});
      await page.locator('#hello').click(); assert.equal(await page.locator('#result').textContent(), '你好，这是我想说的话！');
    });
    await check('state-start-zero-three-clicks-and-reload', async () => {
      await open('state'); assert.equal(await value(), '0'); await click(3); assert.equal(await value(), '3');
      await page.reload(); assert.equal(await value(), '0');
    });
    await check('state-transfer-increment-two', async () => {
      await open('state-step-two'); await click(3); assert.equal(await value(), '6');
    });
    await check('state-transfer-initial-five', async () => {
      await open('state-start-five'); await click(2); assert.equal(await value(), '7');
    });
    await check('variable-update-does-not-automatically-render', async () => {
      await open('state-no-render'); await click(3); assert.equal(await value(), '0');
      assert.equal(await page.evaluate(() => count), 3);
    });
    for (const [id, values, messages] of [
      ['conditions',[2,3,4],['还没达到目标','达到目标了','达到目标了']],
      ['conditions-strict',[2,3,4],['还没达到目标','还没达到目标','达到目标了']],
      ['conditions-equal',[2,3,4],['还没达到目标','达到目标了','还没达到目标']],
      ['conditions-target-five',[4,5,6],['还没达到目标','达到目标了','达到目标了']],
    ]) await check(id+'-below-equal-above', async () => {
      await open(id); let prior = 0;
      for (let i=0; i<values.length; i++) {
        await click(values[i]-prior); prior=values[i];
        assert.equal(await value(), String(values[i]));
        assert.equal(await page.locator('#result').textContent(), messages[i]);
      }
    });
    await check('sources-and-review-boundary', async () => {
      const known = new Set(curriculum.sources.map(s => s.id));
      for (const lesson of curriculum.lessons) {
        assert.ok(lesson.source_ids.length && lesson.source_ids.every(s => known.has(s)));
        assert.ok(assets.has(`/${lesson.id}/index.html`));
      }
      assert.equal(curriculum.status, 'draft');
      assert.equal(curriculum.education_review, null);
      assert.deepEqual(curriculum.pilot_evidence, []);
      assert.deepEqual(errors, []); assert.deepEqual(outside, []);
    });
  } finally {
    fs.mkdirSync(out, {recursive:true});
    fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({
      scope:'Exact curriculum examples and explicit expression variants; technical checks only, no child outcomes or human review',
      curriculum:curriculum.id, version:curriculum.version, checked_at:new Date().toISOString(),
      browser:browser?.version(), source_sha256:hashes, checks, errors, outside,
    }, null, 2));
    await browser?.close(); await new Promise(resolve => server.close(resolve));
  }
  console.log(JSON.stringify({passed:checks.length, evidence:out}));
})().catch(error => { console.error(error); process.exitCode=1; });
