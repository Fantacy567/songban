/* Isolated UI projection tests. No server, account, model or real learning/team data. */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const { chromium } = require('playwright'), esbuild = require('esbuild');
const root = path.resolve(__dirname, '../../../..');
const out = process.env.SONGBAN_HALLS_EVIDENCE || 'E:/松伴/outputs/platform-halls-h1';
const results = [], unexpected = [], pageErrors = [];
const course = (id, overrides = {}) => ({ id, state: 'published', title: '班级活动邀请卡', goal: '做一张让同学看懂的活动邀请卡。', stage: { id: 'first-work', title: '从第一个作品开始', description: '先试一试，再解释自己的修改。', order: 1 }, experience: '没用过 AI 也可以尝试。', preparation: '准备一段虚构活动资料。', steps: ['读资料，说出要做什么', '保存候选，并自己修改', '检查后解释一次修改'], statusLabel: '可以开始', action: { label: '开始我的作品', action: { type: 'start-course', courseId: id } }, ...overrides });
const learning = overrides => ({ page: 'ai', status: 'ready', courses: [course('published-fixture-2026')], ...overrides });
const hackathon = overrides => ({ page: 'hackathon', status: 'ready', ...overrides });
const practice = { teamId: 'team-synthetic-only', title: '松果小队的周末实践', stageLabel: '选题讨论 · 等待本人确认' };
let page, browser, context;
async function render(state, settings = {}) {
  await page.evaluate(({ state, settings }) => window.renderHall(state, settings), { state, settings });
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}
async function actions() { return page.evaluate(() => window.hallActions); }
async function test(name, fn) { await fn(); results.push({ name, passed: true }); }
async function main() {
  fs.mkdirSync(out, { recursive: true });
  await esbuild.build({ entryPoints: [path.join(root, 'frontend/platform/halls/index.tsx')], bundle: true, jsx: 'automatic', format: 'iife', outfile: path.join(out, 'halls-fixture.js'), define: { 'process.env.NODE_ENV': '"development"' } });
  const js = fs.readFileSync(path.join(out, 'halls-fixture.js')), css = fs.readFileSync(path.join(out, 'halls-fixture.css'));
  const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>松伴 H1 大厅隔离验收</title><link rel="stylesheet" href="/halls.css"><style>body{margin:0;background:#faf9f6;color:#20231c;font-family:Arial,"Microsoft YaHei",sans-serif}.fixture-brand{padding:20px 5%;border-bottom:1px solid #e5e1d8;font-size:19px;font-weight:700}.fixture-brand span{color:#786e8c;font-size:13px;font-weight:400;margin-left:16px}.fixture-shell{padding:0 5%;}#legacy-probe{position:absolute;top:-1000px;}</style></head><body><header class="fixture-brand">松伴 SONGBAN<span>H1 隔离界面 · 虚构内容</span></header><button id="legacy-probe">原页面按钮</button><main class="fixture-shell" id="host"></main><script src="/halls.js"></script><script>
    window.hallActions=[];window.hallSettings={};window.renderHall=function(state,settings){window.hallActions=[];window.hallSettings=settings||{};const options={contextKey:settings?.contextKey||'fixture-identity',state,onAction:async function(action){window.hallActions.push(action);if(window.hallSettings.delay)await new Promise(r=>setTimeout(r,window.hallSettings.delay));if(window.hallSettings.fail)throw new Error('fixture failure');return !window.hallSettings.cancel;}};if(window.hallHandle)window.hallHandle.update(options);else window.hallHandle=SongbanHalls.mount(document.getElementById('host'),options);};
  </script></body></html>`;
  browser = await chromium.launch({ headless: true, channel: 'msedge' });
  context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.route('**/*', async route => {
    const u = new URL(route.request().url());
    if (u.origin !== 'http://songban-halls.invalid') { unexpected.push(u.href); return route.abort(); }
    if (u.pathname === '/') return route.fulfill({ contentType: 'text/html; charset=utf-8', body: html });
    if (u.pathname === '/halls.js') return route.fulfill({ contentType: 'text/javascript', body: js });
    if (u.pathname === '/halls.css') return route.fulfill({ contentType: 'text/css', body: css });
    if (/^\/static\/platform\/illustrations\/[a-z-]+\.svg$/.test(u.pathname)) {
      const p = path.join(root, u.pathname);
      return fs.existsSync(p) ? route.fulfill({ contentType: 'image/svg+xml', body: fs.readFileSync(p) }) : route.fulfill({ status: 404, body: '' });
    }
    if (u.pathname !== '/favicon.ico') unexpected.push(u.href);
    return route.fulfill({ status: 404, body: '' });
  });
  page = await context.newPage(); page.on('pageerror', e => pageErrors.push(e.message));
  await page.goto('http://songban-halls.invalid/');
  const legacyStyle = await page.locator('#legacy-probe').evaluate(e => [getComputedStyle(e).borderRadius, getComputedStyle(e).color, getComputedStyle(e).minHeight]);

  await test('Hackathon hall has exactly two ordered illustrated entry cards', async () => {
    await render(hackathon());
    assert.equal(await page.locator('[data-hackathon-entry]').count(), 2);
    assert.deepEqual(await page.locator('[data-hackathon-entry] h2').allTextContents(), ['认识黑客松', '跟松伴开始一次实践']);
    assert.equal(await page.locator('[data-hackathon-entry] img').count(), 2);
    await page.getByRole('button', { name: '先了解黑客松' }).click();
    assert.deepEqual(await actions(), [{ type: 'hackathon-intro' }]);
  });
  await test('First practice and resume emit intent without creating a team or changing route', async () => {
    await render(hackathon());
    await page.getByRole('button', { name: '开始我的第一次实践' }).click();
    assert.deepEqual(await actions(), [{ type: 'begin-practice' }]);
    await render(hackathon({ practice }));
    assert.equal(await page.locator('[data-hackathon-entry]').count(), 2);
    await page.getByRole('button', { name: '继续上次的实践' }).click();
    assert.deepEqual(await actions(), [{ type: 'resume-practice', teamId: practice.teamId }]);
    assert.equal(new URL(page.url()).hash, '');
    assert.equal(await page.locator('.ph-current-practice').textContent(), practice.title + '当前：' + practice.stageLabel);
  });
  await test('Unknown/load failure blocks practice but keeps introduction and retry available', async () => {
    await render(hackathon({ status: 'loading', practice }));
    assert.equal(await page.getByRole('button', { name: '继续上次的实践' }).isDisabled(), true);
    assert.equal(await page.getByRole('button', { name: '先了解黑客松' }).isEnabled(), true);
    await render(hackathon({ status: 'error', error: '暂时无法核对记录' }));
    assert.equal(await page.getByRole('button', { name: '开始我的第一次实践' }).isDisabled(), true);
    await page.getByRole('button', { name: '重新读取实践记录' }).click();
    assert.deepEqual(await actions(), [{ type: 'retry', page: 'hackathon' }]);
    await render(hackathon({ practice, practiceEnabled: false }));
    assert.equal(await page.getByRole('button', { name: '继续上次的实践' }).isDisabled(), true);
  });
  await test('Introduction teaches five steps and reuses practice action without completion claims', async () => {
    await render({ page: 'hackathon-intro' });
    assert.equal(await page.locator('.ph-story > li').count(), 5);
    assert.equal(await page.getByText('教学示例 · 不是真实活动记录').count(), 1);
    await page.getByRole('button', { name: '我想试一试' }).click();
    assert.deepEqual(await actions(), [{ type: 'begin-practice' }]);
    await render({ page: 'hackathon-intro', practice });
    await page.getByRole('button', { name: '继续上次的实践' }).click();
    assert.deepEqual(await actions(), [{ type: 'resume-practice', teamId: practice.teamId }]);
    await render({ page: 'hackathon-intro' });
    await page.getByRole('button', { name: '返回黑客松教学大厅' }).click();
    assert.deepEqual(await actions(), [{ type: 'hackathon-hall' }]);
  });
  await test('Only server-published course projections display; IDs are not hardcoded', async () => {
    const next = course('another-authorized-version', { title: '另一门已发布的测试课程', stage: { id: 'next', title: '下一段已发布内容', order: 2 } });
    await render(learning({ courses: [next, course('archived-fixture', { state: 'archived', title: '归档不可开课' }), course('published-fixture-2026')] }));
    assert.deepEqual(await page.locator('[data-course-version]').evaluateAll(es => es.map(e => e.getAttribute('data-course-version'))), ['published-fixture-2026', 'another-authorized-version']);
    assert.equal(await page.getByText('归档不可开课').count(), 0);
    await page.locator('[data-course-version="another-authorized-version"] button').click();
    assert.deepEqual(await actions(), [{ type: 'start-course', courseId: 'another-authorized-version' }]);
  });
  await test('Empty catalog creates no fake courses; missing preparation has a clear exit', async () => {
    await render(learning({ courses: [] }));
    assert.equal(await page.locator('[data-course-version]').count(), 0);
    assert.equal(await page.getByRole('heading', { name: '课程还在准备中。' }).count(), 1);
    await page.getByRole('button', { name: '请家长帮我准备' }).click();
    assert.deepEqual(await actions(), [{ type: 'prepare-learning' }]);
    await render(learning({ courses: [course('unknown-prep', { action: undefined, unavailableReason: '请先准备学习身份与课程授权。' })] }));
    assert.equal(await page.locator('[data-course-version] button').count(), 0);
    assert.equal(await page.getByText('请先准备学习身份与课程授权。').count(), 1);
  });
  await test('Existing authorized work remains available when directory fails; stale starts are hidden', async () => {
    const resume = { title: '我的邀请卡草稿', description: '接着核对地点和要带的东西。', action: { label: '继续我的作品', action: { type: 'continue-learning', runId: 'run-synthetic' } } };
    await render(learning({ status: 'error', resume }));
    assert.equal(await page.locator('[data-course-version]').count(), 0);
    await page.getByRole('button', { name: '继续我的作品' }).click();
    assert.deepEqual(await actions(), [{ type: 'continue-learning', runId: 'run-synthetic' }]);
    await render(learning({ status: 'loading', resume }));
    assert.equal(await page.locator('[data-course-version]').count(), 0);
    assert.equal(await page.getByRole('button', { name: '继续我的作品' }).isEnabled(), true);
  });
  await test('Course details expose preparation and steps with native keyboard behavior', async () => {
    await render(learning());
    await page.locator('summary').focus(); await page.keyboard.press('Enter');
    assert.equal(await page.locator('details').getAttribute('open'), '');
    assert.equal(await page.locator('details ol li').count(), 3);
    assert.match(await page.locator('details').textContent(), /准备一段虚构活动资料/);
    const summaryHeight = await page.locator('summary').evaluate(e => e.getBoundingClientRect().height);
    assert.ok(summaryHeight >= 44);
    const outline = await page.locator('summary').evaluate(e => getComputedStyle(e).outlineStyle);
    assert.notEqual(outline, 'none');
  });
  await test('External cover input cannot trigger remote fetch; broken local image has readable fallback', async () => {
    await render(learning({ courses: [course('unsafe-cover', { cover: { src: 'https://untrusted.invalid/child.svg', alt: '不可信封面' } })] }));
    assert.match(await page.locator('.ph-cover img').getAttribute('src'), /^\/static\/platform\/illustrations\//);
    await render(learning({ courses: [course('missing-cover', { cover: { src: '/static/platform/illustrations/missing.svg', alt: '缺失封面' } })] }));
    await page.getByRole('img', { name: '班级活动邀请卡：示意图暂时没有加载' }).waitFor();
    assert.equal(await page.getByText('图片暂未加载，仍可继续查看。').count(), 1);
    assert.equal(await page.getByRole('button', { name: '开始我的作品' }).isEnabled(), true);
  });
  await test('Server text is rendered as text and scoped styles leave legacy controls unchanged', async () => {
    await render(learning({ courses: [course('text-fixture', { title: '<img src=x onerror=alert(1)>' })] }));
    assert.equal(await page.locator('.ph-card-body h3').textContent(), '<img src=x onerror=alert(1)>');
    assert.equal(await page.locator('.ph-card-body h3 img').count(), 0);
    const after = await page.locator('#legacy-probe').evaluate(e => [getComputedStyle(e).borderRadius, getComputedStyle(e).color, getComputedStyle(e).minHeight]);
    assert.deepEqual(after, legacyStyle);
    assert.equal(await page.locator('textarea,[role="textbox"]').count(), 0);
  });
  await test('Repeated clicks dispatch once, cancellation stays quiet, failure remains retryable', async () => {
    await render(hackathon(), { delay: 200 });
    await page.getByRole('button', { name: '先了解黑客松' }).evaluate(e => { e.click(); e.click(); e.click(); });
    assert.equal((await actions()).length, 1);
    await page.getByRole('button', { name: '先了解黑客松' }).waitFor({ state: 'visible' });
    await page.waitForFunction(() => !document.querySelector('[data-hackathon-entry="intro"] button').disabled);
    await render(hackathon(), { cancel: true });
    await page.getByRole('button', { name: '先了解黑客松' }).click();
    assert.equal(await page.getByRole('alert').count(), 0);
    await render(hackathon(), { fail: true });
    await page.getByRole('button', { name: '先了解黑客松' }).click();
    await page.getByRole('alert').waitFor();
    assert.equal(await page.getByRole('button', { name: '先了解黑客松' }).isEnabled(), true);
    await render(hackathon(), { contextKey: 'second-authorized-identity' });
    assert.equal(await page.getByRole('alert').count(), 0);
  });
  await test('390/768/1440 layouts keep cards, keyboard actions and images usable without horizontal scrolling', async () => {
    for (const width of [390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      await render(hackathon({ practice }));
      await page.locator('[data-hackathon-entry] img').last().scrollIntoViewIfNeeded();
      await page.waitForFunction(() => [...document.querySelectorAll('[data-hackathon-entry] img')].every(e => e.complete && e.naturalWidth > 0));
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${width}px hackathon overflow`);
      const cards = await page.locator('[data-hackathon-entry]').evaluateAll(es => es.map(e => ({ x: e.getBoundingClientRect().x, y: e.getBoundingClientRect().y, w: e.getBoundingClientRect().width })));
      if (width === 390) assert.ok(cards[1].y > cards[0].y + 100);
      else assert.ok(Math.abs(cards[1].y - cards[0].y) < 2);
      await page.getByRole('button', { name: '先了解黑客松' }).focus();
      await page.keyboard.press('Enter'); assert.deepEqual(await actions(), [{ type: 'hackathon-intro' }]);
      await page.screenshot({ path: path.join(out, `hackathon-${width}.png`), fullPage: true });
      await render(learning());
      await page.locator('.ph-cover img').scrollIntoViewIfNeeded();
      await page.waitForFunction(() => document.querySelector('.ph-cover img').complete);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${width}px learning overflow`);
      assert.ok(await page.locator('.ph-course-card button').evaluate(e => e.getBoundingClientRect().height >= 44));
      await page.screenshot({ path: path.join(out, `learning-${width}.png`), fullPage: true });
      await render({ page: 'hackathon-intro' });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${width}px intro overflow`);
      await page.screenshot({ path: path.join(out, `intro-${width}.png`), fullPage: true });
    }
  });
  await test('200% layout zoom and reduced motion preserve readable actions', async () => {
    await page.setViewportSize({ width: 768, height: 1000 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await render(hackathon());
    await page.evaluate(() => document.body.style.zoom = '2');
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    const cards = await page.locator('[data-hackathon-entry]').evaluateAll(es => es.map(e => e.getBoundingClientRect().y));
    assert.ok(cards[1] > cards[0] + 100, 'Zoomed narrow container must stack cards');
    assert.equal(await page.locator('.ph-button').first().evaluate(e => getComputedStyle(e).animationName), 'none');
    await page.screenshot({ path: path.join(out, 'hackathon-zoom200.png'), fullPage: true });
    await page.evaluate(() => document.body.style.zoom = '');
  });
  await test('Bridge updates and unmounts cleanly without storing private state or making API calls', async () => {
    await page.evaluate(() => { window.hallHandle.unmount(); window.hallHandle.unmount(); });
    assert.equal(await page.locator('[data-platform-halls]').count(), 0);
    await page.evaluate(() => { window.hallHandle = undefined; });
    await render(learning({ courses: [] }), { contextKey: 'new-session' });
    assert.equal(await page.locator('[data-platform-halls]').count(), 1);
    assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
    assert.deepEqual(unexpected, []);
    assert.deepEqual(pageErrors, []);
  });
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ mode: 'isolated_browser_fixture', modelCalls: 0, dbWrites: 0, cases: results.length, results, unexpected, pageErrors }, null, 2));
  console.log(`PASS ${results.length} hall UI scenarios; evidence: ${out}`);
}
main().catch(error => { fs.mkdirSync(out, { recursive: true }); fs.writeFileSync(path.join(out, 'failure.json'), JSON.stringify({ results, unexpected, pageErrors, error: error.stack }, null, 2)); console.error(error); process.exitCode = 1; }).finally(async () => { if (browser) await browser.close(); });
