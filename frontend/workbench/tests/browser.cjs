/* Explicit browser protocol fixture. No real model, SMS, database or user data. */
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.SONGBAN_PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../../..');
const artifacts = path.join(__dirname, 'artifacts');
fs.mkdirSync(artifacts, { recursive: true });
const now = () => new Date().toISOString();
let seq = 0, turnCalls = [], shareCalls = [], createCalls = [], failShare = false, revoked = false, sourceWithdrawn = false;
const sessions = [], messages = [], requests = [], shares = new Map();
const context = teamId => ({ roles: [], team: teamId ? { id: teamId, name: '校园共创小队', is_captain: true, revision: 1, plan_version: 1 } : null, direction: teamId ? { goal: '用一周做出能帮助同学找回物品的小工具', rules: '', rubric: '', non_goals: '不收集无关的个人信息', deadline: '' } : null, my_tasks: teamId ? [{ title: '整理三个真实使用场景' }] : [], sources: [{ id: 'source-1', name: '比赛说明与校园访谈记录（样例材料）', scope: 'personal', version: 3, nature: 'sample' }], model: { configured: true, requested_model: 'configured-fixture' } });
function json(res, data, status = 200) { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(data)); }
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname === '/') {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    return res.end(`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/static/songban.css"><link rel="stylesheet" href="/static/workbench/workbench.css"><body><main style="max-width:1060px;margin:auto;padding:24px 16px"><div id="host"></div></main><script src="/static/workbench/workbench.js"></script><script>window.sharedCount=0;window.nav=[];window.mountAs=(person='alice',teamId='team-1')=>{window.handle?.unmount();window.handle=SongbanWorkbench.mount(document.getElementById('host'),{token:'fixture-'+person,identityKey:person,teamId,onNavigate:p=>window.nav.push(p),onPrepareDirection:f=>window.directionDraft=f,onShared:()=>window.sharedCount++,onUnauthorized:()=>window.unauthorized=true})};mountAs();</script></body></html>`);
  }
  if (url.pathname.startsWith('/static/')) {
    const file = path.join(root, url.pathname);
    res.setHeader('Content-Type', file.endsWith('.css') ? 'text/css' : 'text/javascript');
    return res.end(fs.readFileSync(file));
  }
  const owner = (req.headers.authorization || '').replace('Bearer fixture-', '');
  if (revoked) return json(res, { error: { code: 'forbidden', message: '团队权限已撤销' } }, 403);
  let body = null;
  if (req.method === 'POST') { let text = ''; for await (const chunk of req) text += chunk; body = JSON.parse(text); }
  const teamId = url.searchParams.get('team_id');
  if (url.pathname === '/api/core/me') return json(res, { teams: [{ id: 'team-1', name: '校园共创小队' }] });
  if (url.pathname === '/api/workbench/context') return json(res, { ...context(teamId), ...(sourceWithdrawn ? { sources: [] } : {}) });
  if (url.pathname === '/api/workbench/sessions' && req.method === 'GET') return json(res, { sessions: sessions.filter(s => s.owner === owner && s.team_id === teamId).slice().reverse() });
  if (url.pathname === '/api/workbench/sessions' && req.method === 'POST') {
    createCalls.push(body);
    let session = sessions.find(s => s.owner === owner && s.request_id === body.request_id);
    if (!session) { session = { id: `session-${++seq}`, title: body.title, team_id: body.team_id, created_at: now(), updated_at: now(), owner, request_id: body.request_id }; sessions.push(session); }
    return json(res, { session });
  }
  const match = url.pathname.match(/^\/api\/workbench\/sessions\/([^/]+)(?:\/(turns|share))?$/);
  if (!match) return json(res, { error: { code: 'not_found', message: url.pathname } }, 404);
  const session = sessions.find(s => s.id === match[1] && s.owner === owner);
  if (!session) return json(res, { error: { code: 'not_found', message: '无权查看' } }, 404);
  if (!match[2]) return json(res, { session, messages: messages.filter(m => m.session_id === session.id), requests: requests.filter(r => r.session_id === session.id) });
  if (match[2] === 'share') {
    shareCalls.push(body);
    const receipt = shares.get(body.request_id) || { note_id: `note-${++seq}`, report_id: `report-${seq}`, duplicate: false, analysis_triggered: false, notice: '已保存。本次没有触发团队统筹。' };
    const duplicate = shares.has(body.request_id); shares.set(body.request_id, receipt);
    if (failShare) { failShare = false; return json(res, { error: { code: 'share_unavailable', message: '测试共享回执中断' } }, 503); }
    return json(res, { ...receipt, duplicate });
  }
  if (sourceWithdrawn && body.source_ids.length) return json(res, { error: { code: 'source_unavailable', message: '所选来源已撤回' } }, 403);
  turnCalls.push(body);
  const request = { id: `request-${++seq}`, request_id: body.request_id, session_id: session.id, status: 'running', error: null, created_at: now(), updated_at: now(), message_id: null };
  requests.push(request);
  messages.push({ id: `message-${++seq}`, session_id: session.id, request_id: body.request_id, role: 'user', text: body.text, created_at: now(), role_id: body.role_id, actions: [], sources: [], requested_model: null, actual_model: null, mode: 'fixture' });
  await new Promise(resolve => setTimeout(resolve, body.text.includes('DELAY') ? 1600 : 250));
  if (body.text.includes('UNKNOWN')) { request.status = 'unknown'; request.updated_at = now(); return json(res, { request, message: null }); }
  const message = { id: `message-${++seq}`, session_id: session.id, request_id: body.request_id, role: 'assistant', text: `已梳理你的问题：${body.text}\n先确认一个可以交付的小成果，再列出需要核对的信息。`, created_at: now(), role_id: body.role_id, actions: [{ type: 'prepare_direction', label: '核对方向草稿', fields: { goal: '完成一个可演示的校园工具' } }, { type: 'open_page', label: '查看任务', page: 'tasks' }, { type: 'open_page', label: '恶意跳转夹具', page: 'https://example.invalid' }], sources: body.source_ids.map(id => ({ ...context(teamId).sources.find(s => s.id === id), status: 'partial', truncated: true, warnings: ['OCR 文字需要核对'] })), requested_model: 'configured-fixture', actual_model: null, mode: 'fixture', coverage: { truncated_source_ids: body.source_ids, history_limited: true, source_selection_only: true } };
  messages.push(message); request.status = 'succeeded'; request.message_id = message.id; request.updated_at = now(); session.updated_at = now();
  return json(res, { request, message });
});

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true, ...(process.env.SONGBAN_CHROMIUM_EXECUTABLE ? { executablePath: process.env.SONGBAN_CHROMIUM_EXECUTABLE } : {}) });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  const url = `http://127.0.0.1:${server.address().port}`;
  const input = () => page.getByLabel('这次想一起想清楚什么？');
  const send = () => page.getByRole('button', { name: '发送', exact: true });
  async function ready() { await page.getByRole('button', { name: '＋ 新会话', exact: true }).waitFor(); await page.waitForFunction(() => !document.querySelector('.sbw-sessionBar button').disabled); }
  try {
    await page.goto(url); await ready();
    await page.getByRole('button', { name: '开始一段讨论', exact: true }).click();
    await input().waitFor();
    await page.getByRole('checkbox', { name: /比赛说明/ }).check();
    await page.getByRole('button', { name: '理资料', exact: true }).last().click();
    await input().fill('DELAY 帮我看这份材料 <img src=x onerror="window.injected=true">');
    await send().click(); await input().fill('下一轮草稿不会丢失');
    await page.getByText('回答已保存到本人的会话。', { exact: true }).waitFor();
    assert.equal(await input().inputValue(), '下一轮草稿不会丢失');
    assert.deepEqual(turnCalls[0].source_ids, ['source-1']); assert.equal(turnCalls[0].role_id, 'materials');
    assert.equal(await page.evaluate(() => window.injected), undefined);
    await page.getByText('本轮来源与模型 · 模拟测试', { exact: true }).click();
    assert.match(await page.locator('.sbw-aiBubble').innerText(), /实际模型：未知/);
    assert.match(await page.locator('.sbw-aiBubble').innerText(), /已截断，未完整读取/);
    assert.match(await page.locator('.sbw-aiBubble').innerText(), /部分解析，请核对原文/);
    assert.match(await page.locator('.sbw-aiBubble').innerText(), /OCR 文字需要核对/);
    assert.match(await page.locator('.sbw-aiBubble').innerText(), /本轮只采用部分历史/);
    await page.getByRole('button', { name: '核对方向草稿' }).click();
    assert.equal(await page.evaluate(() => window.directionDraft.goal), '完成一个可演示的校园工具');
    assert.equal(await page.getByRole('button', { name: '恶意跳转夹具' }).count(), 0); assert.deepEqual(await page.evaluate(() => window.nav), []);
    await page.getByRole('button', { name: '选择内容共享' }).click();
    await page.getByLabel('本人编辑摘要').fill('先核对需求，再做最小原型。');
    await page.getByRole('button', { name: '预览共享内容' }).click(); assert.equal(shareCalls.length, 0);
    assert.match(await page.locator('.sbw-preview').innerText(), /本轮原提问（也会共享）/);
    assert.match(await page.locator('.sbw-preview').innerText(), /先核对需求，再做最小原型/);
    assert.match(await page.locator('.sbw-preview').innerText(), /实际模型：未知/);
    assert.ok(!(await page.locator('.sbw-preview').innerText()).includes('先确认一个可以交付的小成果'));
    await page.screenshot({ path: path.join(artifacts, 'share-preview.png'), fullPage: true });
    failShare = true;
    await page.getByRole('button', { name: '确认共享到团队', exact: true }).click();
    await page.getByRole('button', { name: '核对这次共享', exact: true }).waitFor();
    await page.waitForTimeout(350); assert.equal(shareCalls.length, 1);
    await page.getByRole('button', { name: '核对这次共享', exact: true }).click();
    await page.getByText('已保存到团队记录', { exact: true }).waitFor();
    assert.deepEqual(shareCalls[0], shareCalls[1]); assert.equal(shares.size, 1); assert.equal(await page.evaluate(() => window.sharedCount), 1);
    await page.getByRole('button', { name: '收起', exact: true }).click();
    await page.reload(); await input().waitFor(); assert.equal(await input().inputValue(), '下一轮草稿不会丢失');
    assert.equal(await page.locator('.sbw-aiBubble').count(), 1);
    for (const width of [390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1100 });
      await page.waitForFunction(open => document.querySelector('.sbw-supportCard').open === open, width > 900);
      if (width <= 900) {
        const materials = page.locator('.sbw-supportCard').first();
        await materials.locator('summary').click();
        assert.equal(await materials.evaluate(el => el.open), true);
        assert.match(await materials.innerText(), /个人材料 · v3 · 样例/);
        await materials.locator('summary').click();
      }
      await page.screenshot({ path: path.join(artifacts, `workbench-${width}.png`), fullPage: true });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `horizontal overflow at ${width}`);
      assert.ok(await page.locator('.sbw-main').evaluate(el => el.scrollWidth <= el.clientWidth), `panel overflow at ${width}`);
    }
    await input().fill('UNKNOWN 请帮我确认下一步'); await send().click();
    await page.getByText('上一次请求结果尚未确定。请先核对保存状态；新尝试可能重复生成。', { exact: true }).waitFor();
    const unknownCount = turnCalls.length;
    await page.reload(); await input().waitFor(); await page.waitForTimeout(3200); assert.equal(turnCalls.length, unknownCount);
    assert.equal(await page.getByRole('button', { name: '确认新尝试', exact: true }).isDisabled(), true);
    await page.getByRole('checkbox', { name: '我已核对，明确发起一次新尝试' }).check();
    await input().fill('现在明确开始新尝试'); await page.getByRole('button', { name: '确认新尝试', exact: true }).click();
    await page.getByText('回答已保存到本人的会话。', { exact: true }).waitFor(); assert.equal(turnCalls.length, unknownCount + 1);
    assert.notEqual(turnCalls.at(-1).request_id, turnCalls.at(-2).request_id);
    await input().fill('DELAY 刷新后找回回答'); await send().click();
    await page.waitForTimeout(100); await page.reload(); await input().waitFor();
    await page.getByText('已梳理你的问题：DELAY 刷新后找回回答', { exact: false }).waitFor({ timeout: 10000 });
    const beforeIdentity = turnCalls.length;
    await input().fill('DELAY Alice 私人资料'); await send().click(); await page.waitForTimeout(100);
    await page.evaluate(() => window.mountAs('bob', null)); await ready();
    await page.waitForTimeout(1900); assert.equal(await page.getByText(/Alice 私人资料/).count(), 0); assert.equal(turnCalls.length, beforeIdentity + 1);
    await page.getByRole('button', { name: '开始一段讨论', exact: true }).click(); await input().waitFor();
    await input().fill('个人想法'); await send().click(); await page.getByRole('button', { name: '选择内容共享' }).waitFor();
    await page.getByRole('button', { name: '选择内容共享' }).click();
    await page.getByLabel('共享到哪个团队？').selectOption('team-1');
    assert.equal(await page.getByRole('button', { name: '预览共享内容' }).isEnabled(), true);
    await page.getByRole('button', { name: '收起', exact: true }).click();
    await page.getByRole('checkbox', { name: /比赛说明/ }).check();
    sourceWithdrawn = true;
    await input().fill('来源刚撤回，保留这份草稿'); await send().click();
    await page.getByRole('button', { name: '移除失效选择', exact: true }).waitFor();
    assert.equal(await input().inputValue(), '来源刚撤回，保留这份草稿');
    assert.equal(await page.locator('.sbw-aiBubble').count(), 1);
    await page.getByRole('button', { name: '移除失效选择', exact: true }).click();
    assert.equal(await send().isEnabled(), true);
    revoked = true; await page.getByRole('button', { name: '核对保存状态', exact: true }).click();
    await page.getByText(/登录或团队权限已变化，私人内容已收起/).waitFor();
    assert.equal(await page.locator('.sbw-messageText').count(), 0);
    assert.deepEqual(errors, []);
    const report = { fixture: true, passed: ['plain-text rendering', 'selected sources and roles', 'preserve edited draft while pending', 'safe actions', 'explicit share preview and original-question disclosure', 'share uncertain recovery with same key', 'history and draft reload', '390/768/1440 overflow', 'responsive material collapse and Chinese nature labels', 'source warnings, partial status and truncation', 'unknown never replays POST', 'explicit new attempt', 'running request reload', 'identity switch ignores late reply', 'personal share team selection', 'source withdrawal preserves session and draft', 'revocation clears private UI'], turnPosts: turnCalls.length, sharePosts: shareCalls.length, createPosts: createCalls.length };
    fs.writeFileSync(path.join(artifacts, 'result.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  } catch (error) {
    await page.screenshot({ path: path.join(artifacts, 'failure.png'), fullPage: true });
    console.error(await page.locator('body').innerText());
    console.error({ turnPosts: turnCalls.length, sharePosts: shareCalls.length });
    throw error;
  } finally { await browser.close(); server.close(); }
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
