'use strict';
// Real HTTP/SQLite and Edge UI. Only model responses and identities are synthetic.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.SONGBAN_QA_URL || 'http://127.0.0.1:8896';
const folder = path.resolve(process.env.SONGBAN_E2E_OUTPUT || '.browser-cache/workbench/current');
const manifest = JSON.parse(fs.readFileSync(path.join(folder, 'manifest.json'), 'utf8'));
const { users, sources, team, other_team: otherTeam } = manifest;
const results = [], browserErrors = [];
const reportFile = process.env.SONGBAN_QA_SNAPSHOT ? 'restart-' + process.env.SONGBAN_QA_SNAPSHOT + '-results.json' : process.env.SONGBAN_QA_IDENTITY_ONLY ? 'identity-results.json' : 'results.json';
let browser, personalSession, teamSession, personalTurn, teamTurn;
const unique = label => label + '-' + Date.now() + '-' + Math.random().toString(16).slice(2);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function api(url, body, user = 'captain', status = 200, method) {
  const response = await fetch(base + url, { method: method || (body ? 'POST' : 'GET'), headers: {
    'Content-Type': 'application/json', ...(user ? { Authorization: 'Bearer ' + (users[user]?.token || user) } : {}),
  }, ...(body ? { body: JSON.stringify(body) } : {}) });
  const data = await response.json();
  assert.equal(response.status, status, `${method || (body ? 'POST' : 'GET')} ${url}: ${JSON.stringify(data)}`);
  return data;
}
async function test(name, action) {
  const started = Date.now();
  try { const detail = await action(); results.push({ name, status: 'passed', milliseconds: Date.now() - started, detail }); console.log('PASS ' + name); }
  catch (error) {
    results.push({ name, status: 'failed', milliseconds: Date.now() - started, error: error.stack }); console.error('FAIL ' + name + '\n' + error.stack);
    if (browser) for (const [i, context] of browser.contexts().entries()) {
      const page = context.pages()[0]; if (page) await shot(page, `failure-${results.length}-${i}`).catch(() => {});
    }
  }
  fs.writeFileSync(path.join(folder, reportFile), JSON.stringify({ ok: results.every(r => r.status === 'passed'), base, db: manifest.db, model: manifest.model, sms: manifest.sms, results, browserErrors }, null, 2));
}
const create = async (user, teamId, title = '隔离验收会话') => (await api('/api/workbench/sessions', { request_id: unique('create'), title, team_id: teamId }, user)).session;
const turn = (session, user, text, selected = [], requestId = unique('turn'), status = 200) => api('/api/workbench/sessions/' + session.id + '/turns', { request_id: requestId, text, role_id: 'materials', source_ids: selected }, user, status);
const detail = (session, user = 'captain') => api('/api/workbench/sessions/' + session.id, null, user);
const core = (user = 'captain') => api('/api/core/teams/' + team.id, null, user);
function modelCalls() { return JSON.parse(fs.readFileSync(path.join(folder, 'model-calls.json'), 'utf8')); }
async function openUser(user, teamId) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  await context.addInitScript(({ token, teamId }) => {
    if (sessionStorage.getItem('qa-workbench-seeded')) return;
    sessionStorage.setItem('qa-workbench-seeded', '1');
    localStorage.setItem('studio-token', token);
    if (teamId) localStorage.setItem('studio-squad', teamId); else localStorage.removeItem('studio-squad');
    if (!teamId) sessionStorage.setItem('songban-personal', '1');
  }, { token: users[user].token, teamId });
  const page = await context.newPage();
  page.on('pageerror', error => browserErrors.push(error.message));
  page.setDefaultTimeout(10000);
  await page.goto(base + '/#/work');
  await page.locator('[data-route=work]').waitFor();
  return { context, page };
}
async function shot(page, name) { await page.screenshot({ path: path.join(folder, name + '.png'), fullPage: true }); }
async function logoutDifferentAccount() {
  const { context, page } = await openUser('personal', null);
  await page.getByLabel('这次想一起想清楚什么？').fill('QA_LOGOUT_PRIVATE_DRAFT');
  assert((await page.evaluate(() => Object.keys(sessionStorage).filter(k => k.startsWith('songban:workbench:')))).length > 0);
  await page.locator('#logout').click();
  assert.equal(await page.evaluate(() => Object.keys(sessionStorage).filter(k => k.startsWith('songban:workbench:')).length), 0);
  await page.getByRole('button', { name: /^登录/ }).click();
  await page.locator('#auth-phone').fill(users.member.phone); await page.locator('#auth-password').fill('workbench-test-password');
  await page.locator('#auth-form button[type=submit]').click();
  await page.waitForFunction(() => state.me?.person.id === 'qa-workbench-member');
  await page.locator('.sbw').waitFor();
  users.member.token = await page.evaluate(() => localStorage.getItem('studio-token'));
  fs.writeFileSync(path.join(folder, 'manifest.json'), JSON.stringify(manifest, null, 2));
  assert(!(await page.locator('.sbw').innerText()).includes('QA_LOGOUT_PRIVATE_DRAFT'));
  assert(!(await page.locator('.sbw').innerText()).includes('个人验收会话'));
  assert.equal(await page.evaluate(id => Object.keys(sessionStorage).filter(k => k.startsWith('songban:workbench:') && k.includes(id)).length, users.personal.id), 0);
  await shot(page, 'logout-different-account'); await context.close();
}

(async () => {
  if (process.env.SONGBAN_QA_IDENTITY_ONLY) {
    browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
    await test('UI: logout clears private caches; different account never sees old draft/history', logoutDifferentAccount);
    return;
  }
  if (process.env.SONGBAN_QA_SNAPSHOT) {
    await test('Restart: durable sessions/messages/unknown requests/core notes and zero automatic model replay', async () => {
      const snapshot = { users: {}, modelCalls: modelCalls().length };
      for (const key of Object.keys(users)) {
        const me = await api('/api/core/me', null, key);
        const scopes = [null, ...me.teams.map(t => t.id)]; snapshot.users[key] = [];
        for (const teamId of scopes) {
          const list = await api('/api/workbench/sessions' + (teamId ? '?team_id=' + teamId : ''), null, key);
          const records = [];
          for (const session of list.sessions) records.push(await detail(session, key));
          snapshot.users[key].push({ teamId, records });
        }
      }
      snapshot.team = await core();
      const destination = path.join(folder, 'restart-snapshot.json');
      if (process.env.SONGBAN_QA_SNAPSHOT === 'before') fs.writeFileSync(destination, JSON.stringify(snapshot, null, 2));
      else assert.deepEqual(snapshot, JSON.parse(fs.readFileSync(destination, 'utf8')));
    });
    return;
  }
  await test('API: OpenAPI exposes all workbench routes', async () => {
    const schema = await api('/api/openapi.json', null, null);
    for (const route of ['/context', '/sessions', '/sessions/{session_id}', '/sessions/{session_id}/turns', '/sessions/{session_id}/share', '/requests/{request_id}']) {
      assert(Object.keys(schema.paths).some(p => p.replace(/\{[^}]+\}/g, '{}') === ('/api/workbench' + route).replace(/\{[^}]+\}/g, '{}')), route);
    }
  });
  await test('API: personal/team source catalog and authentication boundaries', async () => {
    await api('/api/workbench/context', null, null, 401);
    const personal = await api('/api/workbench/context', null, 'personal');
    assert.equal(personal.team, null); assert.deepEqual(personal.roles.map(r => r.id), ['materials', 'direction', 'next_step']);
    assert.deepEqual(personal.sources.map(s => s.id), [sources.personal.id]);
    const ctx = await api('/api/workbench/context?team_id=' + team.id);
    assert.equal(ctx.team.is_captain, true);
    assert.deepEqual(new Set(ctx.sources.map(s => s.id)), new Set([sources.captain_private.id, sources.team.id]));
    await api('/api/workbench/context?team_id=' + team.id, null, 'outsider', 403);
    await api('/api/workbench/context?team_id=' + otherTeam.id, null, 'captain', 403);
    const connection = await api('/api/core/teams/' + team.id + '/connections', { label: '工作台验收连接器' });
    const response = await fetch(base + '/api/workbench/context', { headers: { Authorization: 'Bearer ' + connection.token } });
    assert([401, 403].includes(response.status), 'Connector must not access private sessions');
  });
  await test('API: session creation idempotency, mismatch conflict and scoped history', async () => {
    const body = { request_id: unique('new-personal'), team_id: null, title: '个人验收会话' };
    personalSession = (await api('/api/workbench/sessions', body, 'personal')).session;
    assert.equal((await api('/api/workbench/sessions', body, 'personal')).session.id, personalSession.id);
    await api('/api/workbench/sessions', { ...body, title: '异正文' }, 'personal', 409);
    teamSession = await create('captain', team.id, '团队验收会话');
    const listed = await api('/api/workbench/sessions?team_id=' + team.id);
    assert(listed.sessions.some(s => s.id === teamSession.id));
    assert.equal((await api('/api/workbench/sessions?team_id=' + team.id, null, 'member')).sessions.length, 0);
    for (const user of ['member', 'outsider']) {
      const r = await fetch(base + '/api/workbench/sessions/' + teamSession.id, { headers: { Authorization: 'Bearer ' + users[user].token } });
      assert([403, 404].includes(r.status), `${user}: ${r.status}`);
    }
  });
  await test('API: persistent personal turn, selected sources only, safe actions and truthful model fields', async () => {
    assert(personalSession);
    personalTurn = await turn(personalSession, 'personal', '个人夹具测试', [sources.personal.id]);
    assert.equal(personalTurn.request.status, 'succeeded');
    assert.equal(personalTurn.message.mode, 'fixture');
    assert.equal(personalTurn.message.actual_model, 'workbench-protocol-fixture-v1');
    assert.equal(personalTurn.message.requested_model, 'qa-requested-model');
    assert.equal(personalTurn.message.sources[0].id || personalTurn.message.sources[0].source_id, sources.personal.id);
    assert(personalTurn.message.actions.every(a => ['prepare_direction', 'share_turn', 'request_team_review', 'open_page'].includes(a.type)));
    assert(!personalTurn.message.actions.some(a => a.page?.startsWith('javascript:')));
    const saved = await detail(personalSession, 'personal');
    assert.equal(saved.messages.length, 2); assert.equal(saved.messages[1].id, personalTurn.message.id);
    assert.equal(saved.messages[0].actual_model, null);
    const serialized = JSON.stringify(modelCalls().at(-1));
    assert(serialized.includes(sources.personal.id)); assert(!serialized.includes(sources.team.id));
    for (const u of Object.values(users)) { assert(!serialized.includes(u.token)); assert(!serialized.includes(u.phone)); }
  });
  await test('API: repeat turn calls fixture once, changed payload returns 409', async () => {
    const id = unique('dedup'); const count = modelCalls().length;
    teamTurn = await turn(teamSession, 'captain', '只读选中的团队来源', [sources.team.id], id);
    const repeated = await turn(teamSession, 'captain', '只读选中的团队来源', [sources.team.id], id);
    assert.equal(repeated.message.id, teamTurn.message.id); assert.equal(modelCalls().length, count + 1);
    await turn(teamSession, 'captain', '不同正文', [sources.team.id], id, 409);
    const last = modelCalls().at(-1); assert.deepEqual(last.sources.map(s => s.id), [sources.team.id]);
  });
  await test('API: inaccessible source rejected before model invocation', async () => {
    const count = modelCalls().length;
    for (const source of [sources.member_private, sources.other_team]) {
      const response = await fetch(base + '/api/workbench/sessions/' + teamSession.id + '/turns', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + users.captain.token }, body: JSON.stringify({ request_id: unique('denied'), text: '越权不得调用', role_id: 'materials', source_ids: [source.id] }) });
      assert([403, 404, 422].includes(response.status), `${response.status}: ${await response.text()}`);
    }
    assert.equal(modelCalls().length, count);
  });
  await test('API: shared summary creates real core note, deduplicates and never auto-reviews', async () => {
    const before = await core();
    const body = { request_id: unique('share'), message_id: teamTurn.message.id, team_id: team.id, summary: '用户编辑后的必要摘要', selected: true };
    const url = '/api/workbench/sessions/' + teamSession.id + '/share';
    await api(url, { ...body, selected: false }, 'captain', 422);
    const shared = await api(url, body); const again = await api(url, body);
    assert.equal(shared.analysis_triggered, false); assert.equal(shared.note_id, again.note_id); assert.equal(again.duplicate, true);
    await api(url, { ...body, summary: '同 ID 异正文' }, 'captain', 409);
    const after = await core();
    const record = after.reports.find(r => r.id === shared.report_id); assert(record); assert.equal(record.capture_only, true);
    assert.equal(record.tool, '松伴项目工作台'); assert.equal(record.model_name, 'workbench-protocol-fixture-v1');
    assert.equal(after.reports.length, before.reports.length + 1);
    const note = after.team_library.find(n => n.id === shared.note_id); assert(note.body.includes(body.summary));
    assert(teamTurn.message.text.includes('QA_PRIVATE_ASSISTANT_ONLY_MARKER'));
    assert(!JSON.stringify(record).includes('QA_PRIVATE_ASSISTANT_ONLY_MARKER'));
    assert(!note.body.includes('QA_PRIVATE_ASSISTANT_ONLY_MARKER'));
    assert(record.excerpt.includes('fixture'));
    assert.deepEqual(after.direction, before.direction); assert.deepEqual(after.active_plan, before.active_plan); assert.deepEqual(after.proposal, before.proposal);
    assert.equal(after.review_running, false);
  });
  await test('API: one running turn per session; polling is read-only', async () => {
    const session = await create('member', team.id); const requestId = unique('slow');
    const count = modelCalls().length;
    const pending = turn(session, 'member', '[QA_SLOW] 并发验收', [], requestId);
    await sleep(400);
    await turn(session, 'member', '第二个并发请求', [], unique('concurrent'), 409);
    const state = await detail(session, 'member'); const request = state.requests.find(r => r.request_id === requestId); assert(request);
    await api('/api/workbench/requests/' + request.id, null, 'member');
    const completed = await pending; assert.equal(completed.request.status, 'succeeded'); assert.equal(modelCalls().length, count + 1);
  });
  await test('API: timeout is unknown; duplicate and polling never rerun it', async () => {
    const session = await create('outsider', otherTeam.id); const requestId = unique('unknown');
    const body = { request_id: requestId, text: '[QA_TIMEOUT] 超时验收', role_id: 'materials', source_ids: [] };
    const count = modelCalls().length;
    const response = await fetch(base + '/api/workbench/sessions/' + session.id + '/turns', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + users.outsider.token }, body: JSON.stringify(body) });
    assert([200, 504].includes(response.status));
    const state = await detail(session, 'outsider'); const request = state.requests.find(r => r.request_id === requestId);
    assert.equal(request.status, 'unknown'); assert.equal(state.messages.filter(m => m.role === 'assistant').length, 0);
    await api('/api/workbench/requests/' + request.id, null, 'outsider');
    await turn(session, 'outsider', body.text, [], requestId);
    assert.equal(modelCalls().length, count + 1);
    return 'Explicit user retry with new ID remains a separate action; no automatic replay tested.';
  });

  if (process.env.SONGBAN_QA_API_ONLY === '1') return;
  browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  // UI selectors are intentionally based on accessible roles, labels and component hooks.
  const personal = await openUser('personal', null), captain = await openUser('captain', team.id);
  const a = personal.page, b = captain.page;
  await test('UI: no-team workspace is usable; history restores and HTML stays text', async () => {
    await a.getByLabel('本人会话历史').selectOption(personalSession.id);
    await a.getByText('个人夹具测试', { exact: true }).first().waitFor();
    assert.equal(await a.evaluate(() => window.__workbenchXSS), undefined);
    assert.equal(await a.locator('.sbw script, .sbw img[src=x]').count(), 0);
    await a.reload(); await a.getByText('个人夹具测试', { exact: true }).first().waitFor();
    await shot(a, 'personal-history');
  });
  await test('UI: selected source send and unsaved input survives five-second refresh', async () => {
    await b.getByLabel('本人会话历史').selectOption(teamSession.id);
    const input = b.locator('textarea').first();
    await input.fill('浏览器待发送中文草稿'); await b.waitForTimeout(5600);
    assert.equal(await input.inputValue(), '浏览器待发送中文草稿');
    await b.getByLabel(/夹具来源-team/).check();
    await b.getByRole('button', { name: '理资料', exact: true }).click();
    await b.getByRole('button', { name: '发送', exact: true }).click();
    await b.getByText('回答已保存到本人的会话。', { exact: true }).waitFor();
    const last = modelCalls().at(-1); assert.deepEqual(last.sources.map(s => s.id), [sources.team.id]);
    assert.equal(last.role.id, 'materials');
    await input.fill('共享之后也不应清除的输入');
    await shot(b, 'team-draft');
  });
  await test('UI: edited share preview writes only after confirmation and preserves composer', async () => {
    const before = await core();
    await b.getByRole('button', { name: '选择内容共享', exact: true }).last().click();
    await b.getByLabel('本人编辑摘要').fill('浏览器人工编辑后的共享摘要');
    await b.getByRole('button', { name: '预览共享内容', exact: true }).click();
    await b.getByRole('heading', { name: '本轮原提问（也会共享）', exact: true }).waitFor();
    assert((await b.locator('.sbw-sharePanel').innerText()).includes('原助手回复不会随摘要自动共享'));
    assert(!(await b.locator('.sbw-preview').innerText()).includes('QA_PRIVATE_ASSISTANT_ONLY_MARKER'));
    assert.equal((await core()).reports.length, before.reports.length);
    await shot(b, 'share-preview');
    await b.getByRole('button', { name: '确认共享到团队', exact: true }).click();
    await b.getByRole('heading', { name: '已保存到团队记录' }).waitFor();
    const after = await core();
    assert.equal(after.reports.length, before.reports.length + 1);
    assert.equal(after.reports[0].capture_only, true);
    assert.equal(after.reports[0].summary, '浏览器人工编辑后的共享摘要');
    assert(!JSON.stringify(after.reports[0]).includes('QA_PRIVATE_ASSISTANT_ONLY_MARKER'));
    assert(!after.team_library.find(n => n.id === after.reports[0].id).body.includes('QA_PRIVATE_ASSISTANT_ONLY_MARKER'));
    assert.deepEqual(after.proposal, before.proposal); assert.deepEqual(after.active_plan, before.active_plan);
    assert.equal(await b.getByLabel('这次想一起想清楚什么？').inputValue(), '共享之后也不应清除的输入');
    await shot(b, 'share-receipt');
    await b.getByRole('button', { name: '收起', exact: true }).click();
  });
  await test('UI: failed new-session request preserves current conversation and input', async () => {
    await b.route('**/api/workbench/sessions', async route => route.request().method() === 'POST' ? route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'qa_create_failed', message: '验收模拟创建失败' } }) }) : route.continue());
    try {
      await b.getByRole('button', { name: '＋ 新会话', exact: true }).click();
      await b.getByText(/验收模拟创建失败/).waitFor();
      assert.equal(await b.getByLabel('本人会话历史').inputValue(), teamSession.id);
      assert.equal(await b.getByLabel('这次想一起想清楚什么？').inputValue(), '共享之后也不应清除的输入');
      assert(await b.locator('.sbw-aiBubble').count() >= 2);
    } finally { await b.unroute('**/api/workbench/sessions'); }
  });
  await test('UI: original tasks, direction and captain confirmation remain reachable', async () => {
    await b.getByRole('link', { name: '任务', exact: true }).click();
    await b.locator('#confirmed-tasks').waitFor(); await b.locator('#review').waitFor();
    await b.getByRole('link', { name: '方向', exact: true }).click(); await b.locator('#direction-form').waitFor();
    await b.getByRole('link', { name: '工作台', exact: true }).click();
    await b.getByLabel('本人会话历史').selectOption(teamSession.id);
    const before = await core();
    await b.getByRole('button', { name: '核对方向草稿', exact: true }).first().click();
    await b.locator('#direction-form').waitFor();
    assert.equal(await b.locator('[name=goal]').inputValue(), '夹具建议：校园失物招领助手');
    assert.deepEqual((await core()).direction, before.direction);
    await b.locator('#direction-form button[type=submit]').click();
    await b.getByText('共同方向已保存。', { exact: false }).waitFor();
    assert.equal((await core()).direction.goal, '夹具建议：校园失物招领助手');
    await shot(b, 'direction-confirmed');
    await b.getByRole('link', { name: '任务', exact: true }).click(); await b.locator('#review').click();
    await b.locator('#confirm-plan').waitFor();
    assert.equal((await core()).plan_version, 0);
    b.once('dialog', dialog => dialog.accept()); await b.locator('#confirm-plan').click();
    await b.locator('[data-report-task=T1]').waitFor(); assert.equal((await core()).plan_version, 1);
  });
  await test('UI: late turn cannot render into another scope; returning restores persisted reply', async () => {
    await b.goto(base + '/#/work'); await b.getByLabel('本人会话历史').selectOption(teamSession.id);
    await b.getByLabel('这次想一起想清楚什么？').fill('[QA_SLOW] 队长私有迟到标记');
    const sent = b.waitForRequest(r => r.url().endsWith('/turns') && r.method() === 'POST');
    await b.getByRole('button', { name: '发送', exact: true }).click(); await sent;
    await b.getByLabel('切换团队').selectOption('__personal');
    await b.getByText('个人空间 · 本人可见', { exact: true }).waitFor(); await b.waitForTimeout(3600);
    assert(!(await b.locator('.sbw').innerText()).includes('队长私有迟到标记'));
    await b.getByLabel('切换团队').selectOption(team.id); await b.getByLabel('本人会话历史').selectOption(teamSession.id);
    await b.locator('.sbw-aiBubble').filter({ hasText: '队长私有迟到标记' }).waitFor();
  });
  await test('UI: cross-tab identity switch discards late response and private UI', async () => {
    await b.getByLabel('这次想一起想清楚什么？').fill('[QA_SLOW] 身份切换秘密');
    const sent = b.waitForRequest(r => r.url().endsWith('/turns') && r.method() === 'POST');
    await b.getByRole('button', { name: '发送', exact: true }).click(); await sent;
    const tab = await captain.context.newPage(); await tab.goto(base + '/#/events');
    await tab.evaluate(token => localStorage.setItem('studio-token', token), users.member.token);
    await b.waitForFunction(() => state.me?.person.id === 'qa-workbench-member'); await b.waitForTimeout(3600);
    assert(!(await b.locator('.sbw').innerText()).includes('身份切换秘密'));
    assert(!(await b.locator('.sbw').innerText()).includes('团队验收会话'));
    await tab.evaluate(token => localStorage.setItem('studio-token', token), users.captain.token);
    await b.waitForFunction(() => state.me?.person.id === 'qa-workbench-captain');
    await b.getByLabel('本人会话历史').selectOption(teamSession.id); await tab.close();
  });
  await test('UI: unknown result keeps input and requires explicit new-attempt confirmation', async () => {
    const oldSession = await a.getByLabel('本人会话历史').inputValue();
    await a.getByRole('button', { name: '＋ 新会话', exact: true }).click();
    await a.waitForFunction(old => document.querySelector('[aria-label="本人会话历史"]')?.value !== old, oldSession);
    await a.locator('[aria-label="会话消息"][aria-busy="false"]').waitFor();
    await a.getByLabel('这次想一起想清楚什么？').fill('[QA_TIMEOUT] 浏览器超时');
    await a.getByRole('button', { name: '发送', exact: true }).click();
    await a.getByLabel('我已核对，明确发起一次新尝试').waitFor();
    assert.equal(await a.getByLabel('这次想一起想清楚什么？').inputValue(), '[QA_TIMEOUT] 浏览器超时');
    const count = modelCalls().length;
    await a.reload(); await a.getByLabel('我已核对，明确发起一次新尝试').waitFor();
    assert(await a.getByRole('button', { name: '确认新尝试', exact: true }).isDisabled());
    await a.waitForTimeout(3200); assert.equal(modelCalls().length, count);
    await shot(a, 'unknown-input-preserved');
  });
  await test('UI: draft survives reload after real password login', async () => {
    await a.locator('#logout').click();
    assert.equal(await a.evaluate(() => Object.keys(sessionStorage).filter(k => k.startsWith('songban:workbench:')).length), 0);
    await a.getByRole('button', { name: /^登录/ }).click();
    await a.locator('#auth-phone').fill(users.personal.phone); await a.locator('#auth-password').fill('workbench-test-password');
    await a.locator('#auth-form button[type=submit]').click(); await a.locator('.event-row').first().waitFor();
    users.personal.token = await a.evaluate(() => localStorage.getItem('studio-token'));
    fs.writeFileSync(path.join(folder, 'manifest.json'), JSON.stringify(manifest, null, 2));
    await a.getByRole('link', { name: '实践', exact: true }).click();
    await a.getByLabel('本人会话历史').selectOption(personalSession.id);
    await a.locator('[aria-label="会话消息"][aria-busy="false"]').waitFor();
    await a.getByLabel('这次想一起想清楚什么？').fill('真实登录后刷新必须保留的草稿');
    await a.reload(); await a.getByLabel('这次想一起想清楚什么？').waitFor();
    assert.equal(await a.getByLabel('本人会话历史').inputValue(), personalSession.id);
    assert.equal(await a.getByLabel('这次想一起想清楚什么？').inputValue(), '真实登录后刷新必须保留的草稿');
  });
  await test('UI: team-switch draft survives reload and remains isolated from personal scope', async () => {
    await b.getByLabel('切换团队').selectOption('__personal');
    await b.getByText('个人空间 · 本人可见', { exact: true }).waitFor();
    await b.getByLabel('切换团队').selectOption(team.id);
    await b.getByLabel('本人会话历史').selectOption(teamSession.id);
    await b.locator('[aria-label="会话消息"][aria-busy="false"]').waitFor();
    await b.getByLabel('这次想一起想清楚什么？').fill('切团队后刷新的隔离草稿');
    await b.reload(); await b.getByLabel('这次想一起想清楚什么？').waitFor();
    assert.equal(await b.getByLabel('这次想一起想清楚什么？').inputValue(), '切团队后刷新的隔离草稿');
    await b.getByLabel('切换团队').selectOption('__personal');
    await b.getByText('个人空间 · 本人可见', { exact: true }).waitFor();
    assert(!(await b.locator('.sbw').innerText()).includes('切团队后刷新的隔离草稿'));
    await b.getByLabel('切换团队').selectOption(team.id);
  });
  await test('UI: 390/768/1440 workspace layout has no horizontal overflow', async () => {
    for (const width of [390, 768, 1440]) {
      await b.setViewportSize({ width, height: 950 }); await b.goto(base + '/#/work');
      await b.getByLabel('本人会话历史').selectOption(teamSession.id);
      await b.waitForTimeout(150);
      const dimensions = await b.evaluate(() => ({ scroll: document.documentElement.scrollWidth, viewport: innerWidth }));
      assert(dimensions.scroll <= width + 1, JSON.stringify(dimensions));
      await shot(b, 'workbench-' + width);
    }
  });
  await test('UI: compatibility collaboration route mounts workbench', async () => {
    await b.goto(base + '/#/collaboration'); await b.getByLabel('本人会话历史').waitFor();
  });
  await test('UI: logout clears private caches; different account never sees old draft/history', logoutDifferentAccount);
  await test('UI: no browser runtime exceptions', async () => assert.deepEqual(browserErrors, []));
})().catch(error => { results.push({ name: 'Harness/runtime', status: 'failed', error: error.stack }); console.error(error.stack); }).finally(async () => {
  if (browser) await browser.close();
  const report = { ok: results.length > 0 && results.every(r => r.status === 'passed'), base, db: manifest.db, model: manifest.model, sms: manifest.sms, results, browserErrors };
  fs.writeFileSync(path.join(folder, reportFile), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ passed: results.filter(r => r.status === 'passed').length, failed: results.filter(r => r.status === 'failed').length, output: folder }));
  process.exitCode = report.ok ? 0 : 1;
});
