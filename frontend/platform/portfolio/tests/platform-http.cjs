/* Real HTTP browser integration against QA 8901 synthetic-only data. Never production or live providers. */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const { chromium } = require('playwright');
const origin = process.env.SONGBAN_PLATFORM_HTTP_ORIGIN || 'http://127.0.0.1:8901';
const fixtureUrl = new URL(origin); assert.equal(fixtureUrl.protocol, 'http:'); assert.equal(fixtureUrl.hostname, '127.0.0.1'); assert.ok(!['8894', '8895'].includes(fixtureUrl.port));
const out = process.env.SONGBAN_PLATFORM_HTTP_EVIDENCE || 'E:/松伴/outputs/platform-http-h5';
const title = '虚构演示·校园节水提示页 ' + Date.now();
const results = [], apiErrors = [], pageErrors = [], platformWrites = [], external = [];
let browser, page;
function record(name) { results.push({ name, passed: true }); }
async function login(account = 'family-preview', expectFamily = true) {
  await page.getByLabel('已有账号', { exact: true }).fill(account);
  await page.getByLabel('密码', { exact: true }).fill('studio-synthetic-only-password');
  await page.getByRole('button', { name: '重新认证并进入管理', exact: true }).click();
  if (expectFamily) await page.getByRole('heading', { name: '为孩子准备学习', exact: true }).waitFor();
  else { await primary('作品集'); await page.getByLabel('选择当前已授权的孩子', { exact: true }).waitFor(); }
}
async function primary(name) { await page.getByRole('navigation', { name: '主导航', exact: true }).getByRole('button', { name, exact: true }).click(); }
async function openAccountMenu() { const menu = page.locator('.lp-account-menu'); if (!await menu.evaluate(element => element.open)) await menu.locator(':scope > summary').click(); }
async function enterChild() {
  await page.getByRole('button', { name: '进入孩子学习模式', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '确认进入', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('.lp-account-menu')?.textContent.includes('继续我的作品'));
}
async function main() {
  fs.mkdirSync(out, { recursive: true });
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const cfgResponse = await context.request.get(origin + '/api/platform/v1/config');
  assert.equal(cfgResponse.status(), 200); const cfg = await cfgResponse.json();
  assert.equal(cfg.demo_mode, true); assert.equal(cfg.image_modes.live, false); assert.equal(cfg.image_modes.sample, true);
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin && !['blob:', 'data:'].includes(url.protocol)) { external.push(url.origin); return route.abort(); }
    return route.continue();
  });
  page = await context.newPage(); page.on('pageerror', error => pageErrors.push(error.message));
  page.on('response', response => { const url = new URL(response.url()); if (url.pathname.startsWith('/api/platform/') && response.status() >= 400) apiErrors.push({ path: url.pathname, status: response.status() }); });
  page.on('request', request => { const url = new URL(request.url()); if (url.pathname.startsWith('/api/platform/') && request.method() === 'POST') platformWrites.push({ path: url.pathname, body: request.postDataJSON() }); });
  await page.goto(origin + '/learning-prep#/family'); await login();
  record('Synthetic manager login uses real HTTP session and CSRF');
  await primary('作品集');
  const child = page.getByLabel('选择当前已授权的孩子', { exact: true }); await child.waitFor();
  assert.equal(await child.inputValue(), ''); assert.equal(await page.locator('[data-work-id]').count(), 0);
  await child.selectOption({ label: '小松同学（虚构）' });
  await page.getByRole('heading', { name: /把做过的尝试，.*留给未来的自己看。/ }).waitFor();
  record('Manager explicitly chooses authorized child; no automatic portfolio selection');
  await page.screenshot({ path: path.join(out, 'manager-selected.png'), fullPage: true });
  await page.getByRole('button', { name: '查看家庭与授权', exact: true }).click(); await enterChild();
  await primary('AI 教学大厅');
  await page.getByRole('heading', { name: /先做一件小作品，.*再多学一小步。/ }).waitFor();
  assert.equal(await page.getByRole('navigation', { name: '主导航', exact: true }).getByRole('button').count(), 3);
  assert.equal(await page.getByRole('heading', { level: 1 }).count(), 1);
  record('Learner hall has three primary entries and one page title');
  await primary('黑客松教学大厅'); await page.locator('[data-hackathon-entry]').first().waitFor();
  assert.equal(await page.locator('[data-hackathon-entry]').count(), 2);
  await page.getByRole('button', { name: '先了解黑客松', exact: true }).click(); await page.locator('.ph-story').waitFor();
  assert.equal(await page.locator('.ph-story > li').count(), 5);
  record('Same identity reaches two-card hackathon hall and five-part introduction');
  await primary('作品集');
  await page.getByRole('button', { name: '添加工具作品 ＋', exact: true }).click();
  await page.getByLabel('作品名称', { exact: true }).fill(title);
  await page.getByLabel('这是一个什么作品？', { exact: true }).fill('虚构校园黑客松练习：用一个小页面提醒同学随手关闭水龙头，并展示检查清单。');
  await page.getByLabel('实际作品链接', { exact: true }).fill('https://example.test/fictional-water-project');
  await page.getByLabel('用了哪个工具？', { exact: true }).fill('虚构网页工具');
  await page.getByLabel('我自己做了什么？哪些地方有人帮忙？', { exact: true }).fill('我整理了三条节水提示，修改按钮文案，并检查手机排版；AI 只提供布局建议。');
  await page.getByLabel('AI 帮助情况', { exact: true }).selectOption('assisted');
  const savedResponse = page.waitForResponse(response => response.url().endsWith('/external-works') && response.request().method() === 'POST');
  await page.getByRole('button', { name: '保存到私人作品集', exact: true }).click();
  const saved = await (await savedResponse).json(); assert.equal(saved.visibility, 'private');
  await page.getByRole('button', { name: '修改说明 / 保存新版本', exact: true }).waitFor();
  assert.equal(saved.contribution.includes('我整理'), true);
  record('Learner creates real private external work with contribution and assistance');
  await page.getByRole('button', { name: '松伴 · 陪我走一步', exact: true }).click();
  await page.getByRole('textbox', { name: '想问松伴什么', exact: true }).fill('我已经整理了三条节水提示，下一步怎么检查？');
  const sendButton = page.getByRole('button', { name: '发送，看看提示', exact: true });
  await page.waitForFunction(() => !document.querySelector('.sb-companion-send')?.disabled);
  const replyResponse = page.waitForResponse(response => /\/companion\/sessions\/[^/]+\/messages$/.test(new URL(response.url()).pathname) && response.request().method() === 'POST');
  await sendButton.click(); const reply = await (await replyResponse).json();
  assert.equal(reply.mode, 'static'); assert.equal(reply.status, 'succeeded'); assert.equal(reply.actual_model, null);
  await page.getByRole('textbox', { name: '想问松伴什么', exact: true }).waitFor();
  await page.waitForFunction(() => document.querySelector('.sb-companion-panel textarea')?.value === '');
  await page.getByRole('button', { name: '松伴 · 收起', exact: true }).click();
  record('Same companion uses current-work context and explicit local/static reply without model');
  await page.getByLabel('希望图片表达什么？', { exact: true }).fill('虚构校园的节水提示封面，友善、米白紫色，没有真实姓名或学校。');
  assert.equal(await page.getByLabel('这次使用哪种图片？', { exact: true }).inputValue(), 'sample');
  await page.getByRole('button', { name: '保存本地样例配图', exact: true }).click();
  await page.getByText('已自动保存到这件作品', { exact: true }).waitFor({ timeout: 30000 });
  await page.locator('.lp-image-gallery img').first().waitFor();
  await page.waitForFunction(() => [...document.querySelectorAll('.lp-image-gallery img')].some(img => img.complete && img.naturalWidth));
  assert.equal(platformWrites.filter(write => write.path.endsWith('/image-jobs')).every(write => write.body.mode === 'sample'), true);
  record('Explicit sample image task is polled and automatically archived through authenticated binary read');
  await page.screenshot({ path: path.join(out, 'work-with-sample-image.png'), fullPage: true });
  await page.reload(); await page.getByRole('button', { name: '打开作品：' + title, exact: true }).waitFor();
  const thumbnail = page.locator('[data-work-id="' + saved.id + '"] img'); await thumbnail.waitFor();
  await page.waitForFunction(id => { const image = document.querySelector('[data-work-id="' + id + '"] img'); return image?.complete && image.naturalWidth; }, saved.id);
  await page.setViewportSize({ width: 390, height: 1000 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: path.join(out, 'portfolio-live-http-390.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: '打开作品：' + title, exact: true }).click();
  await page.getByText('已自动保存到这件作品', { exact: true }).waitFor();
  assert.equal(platformWrites.filter(write => write.path.endsWith('/image-jobs')).length, 1);
  record('Refresh recovers saved cover and image job without another generation POST');
  await primary('AI 教学大厅');
  await page.locator('.ph-course-card').first().waitFor();
  const start = page.getByRole('button', { name: '开始这个作品', exact: true });
  if (await start.count()) await start.click(); else await page.getByRole('button', { name: '打开上次的作品', exact: true }).click();
  await page.waitForTimeout(150);
  assert.equal(await page.locator('.sb-companion').count(), 0);
  record('Course entry does not mount a second platform chat beside the original learning flow');
  await primary('作品集');
  await openAccountMenu();
  await page.getByRole('button', { name: '退出当前身份', exact: true }).click();
  await page.getByRole('region', { name: '开始学习', exact: true }).waitFor();
  await openAccountMenu(); await page.getByRole('button', { name: '家长管理', exact: true }).click();
  assert.equal(await page.getByText(title, { exact: true }).count(), 0); assert.equal(await page.locator('.sb-companion-turn').count(), 0);
  record('Logout removes work, asset views and companion private turns');
  await login('family-preview', false);
  await primary('作品集'); const selection = page.getByLabel('选择当前已授权的孩子', { exact: true }); await selection.waitFor();
  assert.equal(await selection.inputValue(), ''); await selection.selectOption({ label: '小松同学（虚构）' });
  await page.getByRole('button', { name: '打开作品：' + title, exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: '添加工具作品 ＋', exact: true }).count(), 0);
  record('Manager reentry requires explicit child selection and exposes read-only work');
  await openAccountMenu();
  await page.getByRole('button', { name: '退出当前身份', exact: true }).click();
  await page.getByRole('region', { name: '开始学习', exact: true }).waitFor();
  await openAccountMenu(); await page.getByRole('button', { name: '家长管理', exact: true }).click();
  await login('other-preview', false); await primary('作品集');
  await page.getByText('当前账号还没有可选择的家庭学习者。请先到家庭与授权准备，不会自动复制比赛成员。', { exact: true }).waitFor();
  assert.equal(await page.getByText(title, { exact: true }).count(), 0);
  assert.equal(await page.getByRole('button', { name: '打开作品：' + title, exact: true }).count(), 0);
  record('A different synthetic account receives no previous family work or child selection');
  assert.equal(platformWrites.filter(write => /\/messages$/.test(write.path)).every(write => write.body.mode === 'static'), true);
  assert.deepEqual(external, []); assert.deepEqual(pageErrors, []); assert.deepEqual(apiErrors, []);
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ origin, syntheticOnly: true, providerCalls: 0, cases: results.length, results, createdWorkId: saved.id, writes: platformWrites.map(write => ({ path: write.path, ...(write.body.mode ? { mode: write.body.mode } : {}) })), apiErrors, pageErrors, external }, null, 2));
  console.log(`PASS ${results.length} actual HTTP browser integration steps; evidence: ${out}`);
}
main().catch(async error => { fs.mkdirSync(out, { recursive: true }); if (page) { await page.screenshot({ path: path.join(out, 'failure.png'), fullPage: true }).catch(() => {}); fs.writeFileSync(path.join(out, 'failure.html'), await page.content().catch(() => '')); } fs.writeFileSync(path.join(out, 'failure.json'), JSON.stringify({ results, apiErrors, pageErrors, external, error: error.stack }, null, 2)); console.error(error); process.exitCode = 1; }).finally(async () => { if (browser) await browser.close(); });
