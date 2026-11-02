/* Isolated browser fixture. All requests intercepted; no HTTP service, DB, model or SMS. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '../../..');
const out = process.env.SONGBAN_LEARNING_EVIDENCE || 'E:/松伴/outputs/learning-p1-20261102/S05';
const contract = JSON.parse(fs.readFileSync(path.join(root, 'docs/planning/learning-roadmap/p0/contracts/openapi.proposed.json')));
const topics = ['age_band', 'experience', 'interests', 'help_preference', 'mini_attempt_text', 'chosen_start'];
const clone = x => JSON.parse(JSON.stringify(x));
const now = '2026-11-02T06:00:00Z';
function valid(s, value) {
  if (s.$ref) return valid(contract.components.schemas[s.$ref.split('/').pop()], value);
  if (s.oneOf) return s.oneOf.filter(x => valid(x, value)).length === 1;
  if (s.anyOf) return s.anyOf.some(x => valid(x, value));
  if ('const' in s && JSON.stringify(value) !== JSON.stringify(s.const)) return false;
  if (s.enum && !s.enum.includes(value)) return false;
  if (s.type === 'null') return value === null;
  if (s.type === 'object') {
    if (!value || Array.isArray(value) || typeof value !== 'object') return false;
    if (s.required?.some(k => !(k in value))) return false;
    if (s.additionalProperties === false && Object.keys(value).some(k => !(k in (s.properties || {})))) return false;
    if (Object.entries(s.properties || {}).some(([k, v]) => k in value && !valid(v, value[k]))) return false;
  }
  if (s.type === 'array' && (!Array.isArray(value) || value.some(v => !valid(s.items, v)))) return false;
  if (s.type === 'string' && (typeof value !== 'string' || value.length < (s.minLength || 0) || value.length > (s.maxLength || Infinity) || (s.pattern && !new RegExp(s.pattern).test(value)))) return false;
  if (s.type === 'integer' && (!Number.isInteger(value) || value < (s.minimum ?? -Infinity))) return false;
  if (s.type === 'boolean' && typeof value !== 'boolean') return false;
  return true;
}
function start(id) { return project({ id: `start-${id}`, revision: 0, learner_id: id, answers: Object.fromEntries(topics.map(t => [t, { state: 'unanswered', value: null }])), saved_at: null }); }
function project(s) {
  const missing = topics.filter(t => s.answers[t].state === 'unanswered'), skips = topics.filter(t => s.answers[t].state === 'skipped');
  const rules = s.answers.experience.state === 'answered' && s.answers.mini_attempt_text.state === 'answered';
  const choice = s.answers.chosen_start;
  return { ...s, completion_status: missing.length === 6 ? 'not_started' : missing.length ? 'draft' : skips.length ? 'completed_with_skips' : 'completed', mini_attempt_status: s.answers.mini_attempt_text.state === 'answered' ? 'answered' : s.answers.mini_attempt_text.state === 'skipped' ? 'skipped' : 'not_attempted', recommendation: rules ? 'try_first' : 'guided', recommendation_basis: rules ? 'rules' : 'insufficient_evidence', recommendation_revision: s.revision, recommendation_rule_version: 'fixture-rule-1', recommendation_source_fields: rules ? ['experience', 'mini_attempt_text'] : [], missing_fields: missing, skipped_fields: skips, effective_start: choice.value || 'guided', effective_start_source: choice.state === 'answered' ? 'learner_choice' : choice.state === 'accepted_default' ? 'accepted_default' : 'conservative_fallback' };
}
function text(approved = false, version = 'fixture-consent-1') {
  const content = { locale: 'zh-CN', title: '隔离测试授权文本', text: '仅为浏览器协议夹具，不用于真实家庭授权。', scope_purposes: [{ scope: 'learning', purpose: '保存虚构学习记录（测试）' }, { scope: 'parent_summary', purpose: '读取虚构家长摘要（测试）' }] };
  return { ...content, consent_version: version, text_sha256: crypto.createHash('sha256').update(JSON.stringify(content)).digest('hex'), approval_status: approved ? 'approved_for_pilot' : 'draft', approved_at: approved ? now : null, acceptance_enabled: approved, notice: '虚构测试数据；批准状态只在 fixture 内模拟。' };
}
const state = { session: null, epoch: 0, family: null, consents: [], approved: false, tamperText: false, starts: {}, failFamilies: false, dropSave: false, conflict: false, failSave: 0, delayStart: null, delayFamily: null, expire: false, learning: true, writes: [], calls: [], replay: new Map() };
function session(mode, id = null) { state.session = { id: `session-${++state.epoch}`, revision: 1, mode, actor_id: 'fixture-parent', learner_id: id, mode_epoch: state.epoch, scopes: [], expires_at: '2099-01-01T00:00:00Z' }; return state.session; }
function learner(id = 'fixture-child') { return { id, revision: 1, family_id: 'fixture-family', display_name: id === 'fixture-other' ? '另一位虚构学习者' : '小松（虚构）', age_band: null, guardian_link: { id: `link-${id}`, revision: 1, learner_id: id, status: 'pending', declared_relationship: '父母', verification_method: null } }; }
const results = [], errors = [];
const record = (name, detail = '') => results.push({ name, result: 'passed', detail });
async function main() {
  fs.mkdirSync(out, { recursive: true });
  await esbuild.build({ entryPoints: [path.join(root, 'frontend/learning/index.tsx')], bundle: true, jsx: 'automatic', format: 'iife', globalName: 'SongbanLearning', target: 'es2022', outfile: path.join(out, 'learning.js'), define: { 'process.env.NODE_ENV': '"production"' } });
  fs.writeFileSync(path.join(out, 'fixture-inputs.json'), JSON.stringify({ notice: 'Isolated synthetic browser fixture, not backend evidence', config: { contract_version: '0.2.1' }, draft: text(), approved: text(true), emptyStart: start('fixture-child') }, null, 2));
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, serviceWorkers: 'block' });
  await context.addInitScript(() => { const original = window.fetch; window.fetch = (input, options) => { if (String(input).startsWith('/api/learning/v2')) { if (options.credentials !== 'same-origin' || options.cache !== 'no-store' || options.redirect !== 'error') throw new Error('Unsafe request options'); } return original(input, options); }; });
  await context.route('**/*', async route => {
    const req = route.request(), u = new URL(req.url()), p = u.pathname.replace('/api/learning/v2', ''), method = req.method();
    const json = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    const fail = (status, code) => json({ error: { code, message: 'fixture error', retryable: false, recovery: 'reload', current_revision: null } }, status);
    if (u.pathname === '/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/learning.css"><body style="margin:0"><div id="host"></div><script src="/learning.js"></script><script>window.events=[];window.handle=SongbanLearning.mount(document.getElementById("host"),{initialRoute:"#/family",onIdentityBoundary:r=>events.push(r),onRouteChange:r=>events.push(r),onUnmount:()=>events.push("unmounted")});</script></body></html>' });
    if (u.pathname === '/learning.js' || u.pathname === '/learning.css') return route.fulfill({ path: path.join(out, u.pathname.slice(1)), contentType: u.pathname.endsWith('.js') ? 'text/javascript' : 'text/css' });
    if (u.pathname === '/static/design/pine-mascot.png') return route.fulfill({ path: path.join(root, u.pathname), contentType: 'image/png' });
    assert.ok(u.pathname.startsWith('/api/learning/v2/'), `Unexpected network ${u.pathname}`);
    assert.equal(req.headers().authorization, undefined);
    state.calls.push({ path: p, method });
    const body = req.postDataJSON();
    if (method !== 'GET') {
      assert.equal(req.headers()['x-csrf-token'], 'fixture-csrf');
      assert.ok(body.request_id.length >= 8);
      const op = Object.entries(contract.paths).find(([template, verbs]) => verbs[method.toLowerCase()] && new RegExp('^' + template.replace(/\{[^}]+\}/g, '[^/]+') + '$').test(p));
      assert.ok(op, `Missing contract ${method} ${p}`);
      const schema = op[1][method.toLowerCase()].requestBody.content['application/json'].schema;
      assert.ok(valid(schema, body), `Request violates contract ${p}: ${JSON.stringify(body)}`);
      state.writes.push({ path: p, body: clone(body) });
    }
    if (p === '/session-bootstrap') return json({ csrf_token: 'fixture-csrf', browser_revision: state.epoch });
    if (p === '/config') return json({ contract_version: '0.2.1', learning_enabled: state.learning, live_enabled: false, publication_enabled: false, age_band_options: ['6–8岁（测试）', '9–12岁（测试）', '13–17岁（测试）'], consent_version: 'fixture-consent-1', notice: '隔离浏览器 fixture，不是真实家庭服务。' });
    if (p === '/session') return state.session ? json(state.session) : fail(401, 'session_expired');
    if (p === '/sessions/authenticate') { assert.equal(body.method, 'password'); assert.equal(body.browser_revision, state.epoch); return json(session('manager')); }
    if (p === '/sessions/logout') { state.session = null; return json({ logged_out: true }); }
    if (!state.session) return fail(401, 'session_expired');
    if (p === '/families' && method === 'GET') {
      if (state.failFamilies) return fail(503, 'fixture_down');
      const data = { items: state.family ? [clone(state.family)] : [], next_cursor: null };
      if (state.delayFamily) { const release = state.delayFamily; state.delayFamily = null; await release; }
      return json(data);
    }
    if (p === '/families' && method === 'POST') { if (state.family) return fail(409, 'family_exists'); state.family = { id: 'fixture-family', revision: 1, learners: [] }; return json(state.family, 201); }
    if (p === '/families/fixture-family' && method === 'GET') return json(state.family);
    if (p === '/families/fixture-family/learners') { assert.equal(body.expected_revision, state.family.revision); const l = learner(); l.display_name = body.display_name; state.family.learners = [l]; state.family.revision++; return json(l, 201); }
    if (p.startsWith('/consent-texts/')) {
      const t = text(state.approved, decodeURIComponent(p.split('/').pop()));
      // Match backend storage: object keys may be sorted, array order is retained.
      return json({ ...t, scope_purposes: t.scope_purposes.map(p => ({ purpose: p.purpose, scope: p.scope })), ...(state.tamperText ? { text: 'incorrect fixture content' } : {}) });
    }
    if (/\/consents$/.test(p) && method === 'GET') return json({ learner_id: 'fixture-child', relationship_status: state.family.learners[0].guardian_link.status, visibility: 'own_submissions', items: state.consents, next_cursor: null });
    if (/\/consents$/.test(p) && method === 'POST') {
      assert.ok(state.approved); assert.equal(state.family.learners[0].guardian_link.status, 'verified');
      assert.equal(body.expected_revision, state.family.learners[0].revision);
      const c = { id: 'fixture-consent', revision: 1, learner_id: 'fixture-child', consent_version: body.consent_version, scopes: body.scopes, status: 'active', recorded_at: now, text_sha256: text(true).text_sha256, effective_scopes: body.scopes };
      state.consents = [c, ...state.consents]; state.family.learners[0].revision++; return json(c, 201);
    }
    if (/\/revoke$/.test(p)) { state.consents[0] = { ...state.consents[0], status: 'revoked', effective_scopes: [], revision: 2 }; return json(state.consents[0]); }
    if (p === '/sessions/enter-learner') { assert.equal(body.expected_revision, state.session.revision); assert.equal(state.session.mode, 'manager'); return json(session('learner', body.learner_id)); }
    const match = p.match(/^\/learners\/([^/]+)\/(start|profile)$/);
    if (match) {
      if (state.expire) { state.expire = false; state.session = null; return fail(401, 'session_expired'); }
      const id = match[1];
      if (state.session.mode !== 'learner' || state.session.learner_id !== id) return fail(404, 'resource_not_found');
      if (match[2] === 'profile') { const l = learner(id); return json({ id, revision: 1, display_name: l.display_name, age_band: null }); }
      state.starts[id] ||= start(id);
      if (method === 'GET') {
        const value = clone(state.starts[id]);
        if (state.delayStart) { const release = state.delayStart; state.delayStart = null; await release; }
        return json(value);
      }
      assert.equal(Object.keys(body.answers).length, 1, 'Only current topic sent');
      if (state.failSave) { const code = state.failSave; state.failSave = 0; return fail(code, code === 422 ? 'invalid_input' : 'fixture_down'); }
      if (state.replay.has(body.request_id)) return json(state.replay.get(body.request_id));
      if (state.conflict) { state.conflict = false; state.starts[id] = project({ ...state.starts[id], revision: state.starts[id].revision + 1, answers: { ...state.starts[id].answers, mini_attempt_text: { state: 'answered', value: '另一处保存的虚构回答' } } }); }
      if (body.expected_revision !== state.starts[id].revision) return fail(409, 'revision_conflict');
      if (body.answers.chosen_start?.state === 'accepted_default') { assert.equal(body.answers.chosen_start.recommendation_revision, body.expected_revision); assert.equal(body.answers.chosen_start.value, state.starts[id].recommendation); }
      state.starts[id] = project({ ...state.starts[id], revision: state.starts[id].revision + 1, answers: { ...state.starts[id].answers, ...body.answers }, saved_at: now });
      state.replay.set(body.request_id, clone(state.starts[id]));
      if (state.dropSave) { state.dropSave = false; return route.abort('failed'); }
      return json(state.starts[id]);
    }
    return fail(404, 'fixture_unimplemented');
  });
  const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
  page.setDefaultTimeout(8000);
  const button = name => page.getByRole('button', { name, exact: true });
  async function visible(text) { await page.getByText(text, { exact: true }).first().waitFor(); }
  async function login() { await page.getByLabel('已有账号', { exact: true }).fill('synthetic-parent'); await page.getByLabel('密码', { exact: true }).fill('synthetic-proof'); await button('重新认证并进入管理').click(); }
  async function shot(name) { await page.screenshot({ path: path.join(out, name + '.png'), fullPage: true }); }
  try {
    await page.goto('https://learning.fixture.invalid/'); await login();
    await button('建立本人家庭').click(); await page.getByLabel('学习称呼（避免使用实名）').fill('小松（虚构）'); await page.getByLabel('声明与孩子的关系').selectOption('父母'); await button('保存孩子档案').click();
    await visible('关系已声明，待按试点流程确认'); assert.equal(await button('确认本次授权').count(), 0); assert.equal(await button('进入孩子学习模式').count(), 0);
    record('fresh-auth-create-pending-no-self-verification');
    for (const width of [390, 768, 1440]) { await page.setViewportSize({ width, height: 1050 }); await shot(`family-${width}`); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)); }
    record('family-responsive-390-768-1440');
    const created = state.writes.filter(w => w.path === '/families').length;
    state.consents = [{ id: 'old-fixture-consent', revision: 2, learner_id: 'fixture-child', consent_version: 'fixture-consent-old', scopes: ['learning'], status: 'revoked', recorded_at: now, text_sha256: text().text_sha256, effective_scopes: [] }];
    await page.reload(); await visible('关系已声明，待按试点流程确认'); assert.equal(state.writes.filter(w => w.path === '/families').length, created); record('family-reload-server-discovery');
    await page.getByText('查看当时的授权原文（fixture-consent-old）', { exact: true }).waitFor(); assert.ok(state.calls.some(c => c.path === '/consent-texts/fixture-consent-old')); record('historical-consent-reads-exact-version');
    state.tamperText = true; await page.reload(); await visible('暂时没读到完整家庭或授权内容，尚不能确认当前状态。'); assert.equal(await button('确认本次授权').count(), 0); state.tamperText = false; await button('重新读取家庭与授权').click(); await visible('关系已声明，待按试点流程确认'); record('consent-content-hash-mismatch-blocked');
    state.failFamilies = true; await page.reload(); await visible('暂时没读到完整家庭或授权内容，尚不能确认当前状态。'); assert.equal(await button('建立本人家庭').count(), 0);
    state.failFamilies = false; await button('重新读取家庭与授权').click(); await visible('关系已声明，待按试点流程确认'); record('family-read-failure-not-empty');
    // Only the synthetic backend changes verification; no UI self-verification exists.
    state.family.learners[0].guardian_link.status = 'verified'; state.approved = true;
    await page.reload(); await page.getByLabel('保存虚构学习记录（测试）', { exact: true }).check(); await page.getByLabel('我已阅读以上版本的授权内容和用途').check(); await button('确认本次授权').click();
    await button('进入孩子学习模式').click(); await button('确认进入').click(); await visible('小松（虚构） · 孩子学习模式');
    assert.equal(await page.getByText('已有授权记录', { exact: true }).count(), 0); record('approved-consent-explicit-enter-clears-manager');
    await visible('课程状态暂时未确认，起点仍可填写。');
    await page.getByRole('heading', { name: '先选适合你的帮助方式', exact: true }).waitFor();
    await button('开始回答').click(); await page.getByLabel('6–8岁（测试）', { exact: true }).check(); await button('保存并继续').click(); await visible('用过 AI 做什么');
    assert.deepEqual(Object.keys(state.writes.at(-1).body.answers), ['age_band']);
    await page.reload(); await page.evaluate(() => window.handle.navigate('#/learn/start')); await visible('用过 AI 做什么');
    await button('我的学习起点').click(); await page.getByRole('heading', { name: '先选适合你的帮助方式', exact: true }).waitFor(); await button('调整我的起点').click(); await visible('用过 AI 做什么');
    assert.equal(state.starts['fixture-child'].answers.help_preference.state, 'unanswered'); record('topic-patch-refresh-omitted-preserved');
    await page.getByLabel('自己改过提示和结果', { exact: true }).check(); await button('保存并继续').click(); await page.getByLabel('暂无兴趣选项', { exact: true }).check(); await button('保存并继续').click();
    await button('暂时跳过').click(); await visible('读一张小资料卡'); assert.equal(state.starts['fixture-child'].answers.help_preference.state, 'skipped'); record('explicit-empty-interest-and-skip');
    const mini = page.getByLabel('这张邀请卡是给谁的？同学几点到哪里？');
    await mini.fill('我的未保存回答'); await button('家长管理').click(); await page.getByRole('dialog').waitFor();
    await button('放弃本次修改').focus(); await page.keyboard.press('Tab'); assert.ok(await page.getByRole('dialog').evaluate(d => d.contains(document.activeElement)));
    await page.keyboard.press('Escape'); assert.equal(await mini.inputValue(), '我的未保存回答'); assert.ok(await button('家长管理').evaluate(el => el === document.activeElement)); record('dialog-focus-loop-and-restore');
    record('unsaved-leave-escape-preserves-input');
    state.failSave = 422; await button('保存并继续').click(); await visible('这些内容还不能保存，请检查选择和填写内容。'); assert.equal(await mini.inputValue(), '我的未保存回答'); record('known-save-failure-preserves-input');
    state.dropSave = true; await button('保存并继续').click(); await button('核对并重试原保存').waitFor(); const unknown = clone(state.writes.at(-1)); await button('核对并重试原保存').click(); await visible('这题已保存。'); assert.deepEqual(state.writes.at(-1), unknown); record('lost-receipt-explicit-same-id-retry');
    await mini.fill('我在这里改的虚构答案'); state.conflict = true; await button('保存并继续').click(); await visible('核对两份内容'); assert.equal(await mini.inputValue(), '我在这里改的虚构答案'); await shot('start-conflict'); const writes = state.writes.length;
    await button('以最新版本继续编辑，稍后再保存').click(); assert.equal(state.writes.length, writes); await button('保存并继续').click(); await visible('选择开始方式'); await button('采用当前建议').click(); await visible('这题已保存。');
    const accepted = state.writes.at(-1).body; assert.deepEqual(Object.keys(accepted.answers), ['chosen_start']); assert.equal(accepted.answers.chosen_start.recommendation_revision, accepted.expected_revision); record('conflict-explicit-review-no-overwrite-recommendation-bound');
    const afterAcceptance = state.writes.length; await button('保存我的选择').click(); assert.equal(state.writes.length, afterAcceptance); record('revisit-accepted-default-no-stale-resubmission');
    await button('我的学习起点').click(); await page.getByRole('heading', { name: '这是你的学习起点', exact: true }).waitFor(); await button('调整我的起点').click(); await visible('选择开始方式');
    for (const width of [390, 768, 1440]) { await page.setViewportSize({ width, height: 1050 }); await shot(`start-${width}`); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)); }
    record('start-responsive-390-768-1440');
    await page.setViewportSize({ width: 390, height: 844 }); await page.evaluate(() => document.documentElement.style.zoom = '2'); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)); await shot('start-200-percent'); await page.evaluate(() => document.documentElement.style.zoom = ''); record('200-percent-zoom-no-horizontal-overflow');
    // Same-identity visibility recheck retains unsaved edits, unlike a changed epoch.
    await button('上一题').click(); await mini.fill('同身份仍在编辑'); await page.evaluate(() => window.handle.revalidate()); assert.equal(await mini.inputValue(), '同身份仍在编辑');
    await page.evaluate(() => dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }))); await mini.waitFor(); assert.equal(await mini.inputValue(), '同身份仍在编辑'); record('same-identity-and-pageshow-revalidation-keeps-draft');
    await button('家长管理').click(); await button('放弃本次修改').click(); await page.getByLabel('已有账号', { exact: true }).waitFor(); assert.equal(await page.getByText('已有授权记录', { exact: true }).count(), 0); await login(); await visible('已有授权记录'); record('return-manager-fresh-password-required');
    const second = await context.newPage(); second.on('pageerror', e => errors.push(e.message)); await second.goto('https://learning.fixture.invalid/'); await second.getByText('已有授权记录', { exact: true }).waitFor();
    await button('进入孩子学习模式').click(); await button('确认进入').click(); await visible('小松（虚构） · 孩子学习模式'); await second.getByRole('heading', { name: '请家长重新认证' }).waitFor(); assert.equal(await second.getByText('已有授权记录', { exact: true }).count(), 0); record('broadcast-other-tab-manager-cleared'); await second.close();
    // In-flight old-child payload, with no broadcast: completion must recheck /session.
    let release; state.delayStart = new Promise(r => release = r);
    const before = state.calls.filter(c => c.path.endsWith('/start')).length;
    await page.evaluate(() => { void window.handle.navigate('#/learn/start'); });
    await page.waitForFunction(() => document.body.textContent.includes('正在读取上次的学习起点'));
    while (state.calls.filter(c => c.path.endsWith('/start')).length <= before) await new Promise(r => setTimeout(r, 10));
    session('learner', 'fixture-other'); release();
    await page.getByRole('heading', { name: '年龄段', exact: true }).waitFor(); assert.equal(await page.getByText('我在这里改的虚构答案', { exact: true }).count(), 0); record('late-response-dropped-server-epoch-no-broadcast');
    state.expire = true; await page.getByLabel('6–8岁（测试）', { exact: true }).check(); await button('保存并继续').click(); await page.getByRole('heading', { name: '请家长重新认证' }).waitFor(); assert.equal(await page.getByLabel('6–8岁（测试）', { exact: true }).count(), 0); record('401-clears-private-state');
    await login(); await visible('已有授权记录');
    state.learning = false; await page.evaluate(() => window.handle.revalidate()); await visible('学习入口暂未开放，已保存的记录可在授权范围内查看。'); assert.equal(await button('进入孩子学习模式').count(), 0); record('disabled-config-no-learning-entry');
    await button('撤回这条授权').click(); await page.getByLabel('撤回原因').fill('虚构测试：停止授权'); await button('确认撤回').click(); await page.getByRole('dialog').waitFor({ state: 'detached' }); assert.equal(state.consents[0].status, 'revoked'); record('revoke-with-record-revision-while-entry-disabled');
    await button('退出当前身份').click(); await page.getByRole('heading', { name: '请家长重新认证' }).waitFor(); assert.equal(state.session, null); record('logout-no-old-manager-restoration');
    assert.deepEqual(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length })), { local: 0, session: 0 }); record('no-persistent-private-state-or-bearer');
    await page.evaluate(() => { window.handle.unmount(); window.handle.unmount(); }); assert.equal(await page.locator('#host').textContent(), ''); record('idempotent-unmount');
    assert.deepEqual(errors, []); record('no-browser-runtime-errors');
  } catch (e) {
    await shot('failure'); console.error(await page.locator('body').innerText()); throw e;
  } finally {
    fs.writeFileSync(path.join(out, 'browser-results.json'), JSON.stringify({ date: '2026-11-02', scope: 'Isolated synthetic browser fixture ONLY; no backend/G1 acceptance', results, errors, requestCount: state.calls.length, mutationCount: state.writes.length, operations: [...new Set(state.calls.map(c => c.method + ' ' + c.path.replace(/fixture-[^/]+/g, '{fixture-id}')))] }, null, 2));
    await browser.close();
  }
  console.log(JSON.stringify({ passed: results.length, evidence: out }));
}
main().catch(e => { console.error(e); process.exitCode = 1; });
