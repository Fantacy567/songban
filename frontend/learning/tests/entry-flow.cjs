/* W06 independent synthetic browser + legacy route checks. All network is intercepted. */
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), vm = require('node:vm');
const { chromium } = require('playwright'), esbuild = require('esbuild');
const root = path.resolve(__dirname, '../../..');
const out = process.env.SONGBAN_ENTRY_EVIDENCE || path.resolve(root, '../outputs/learning-experience/entry-flow');
const results = [], errors = [];
async function check(name, action) { try { await action(); results.push({ name, passed: true }); } catch (e) { results.push({ name, passed: false, error: String(e.stack || e) }); } }
const consentContent = { locale: 'zh-CN', title: '测试授权', text: '仅供合成测试，不用于真实家庭。', scope_purposes: [{ scope: 'learning', purpose: '测试学习记录' }] };
const consentText = { ...consentContent, consent_version: 'fixture-consent', text_sha256: crypto.createHash('sha256').update(JSON.stringify(consentContent)).digest('hex'), approval_status: 'approved_for_pilot', approved_at: '2026-11-02T00:00:00Z', acceptance_enabled: true, notice: '合成fixture' };
const course = { id: 'invitation-course@0.1.0', state: 'published', title: '邀请卡', revision: 1, task_cards: [], tool_cards: [], lesson_version_ids: [] };
const enrollment = { id: 'enrollment-fixture', revision: 1, learner_id: 'child-fixture', course_version_id: course.id, entitlement_id: 'grant-fixture', status: 'active', parent_revision: 1 };
let state;
function reset(overrides = {}) {
  state = { mode: 'learner', actor: 'parent-fixture', epoch: 1, run: null, entitlement: true, failCourses: false, failEntry: false, delayCreate: false, writes: [], reads: [], creates: 0,
    entry: { id: 'entry-fixture', learner_id: 'child-fixture', revision: 7, status: 'none', goals: ['想做一张活动邀请卡'], experiences: ['用过提示词'], source_version: 11, candidate: null }, ...overrides };
}
function childId() { return state.actor === 'parent-other' ? 'child-other' : 'child-fixture'; }
function familyId() { return state.actor === 'parent-other' ? 'family-other' : 'family-fixture'; }
function currentRun() { return state.runs && Object.hasOwn(state.runs, childId()) ? state.runs[childId()] : state.run; }
function currentSession() { return { id: `session-${state.epoch}`, revision: 1, mode: state.mode, actor_id: state.actor, learner_id: state.mode === 'learner' ? childId() : null, mode_epoch: state.epoch, scopes: ['learning'], expires_at: '2099-01-01T00:00:00Z' }; }
function home() { const run = currentRun(); return { learner_id: childId(), revision: 1, run_id: run, current_action: { type: run ? 'continue_run' : 'start_run', label: '开始一小步', resource_id: run }, entitlements: state.entitlement ? [{ ...enrollment, learner_id: childId() }] : [], progress: [], allowed_actions: state.entitlement ? ['createRun'] : [], missing_fields: [] }; }
function family() { return { id: familyId(), revision: 1, learners: [{ id: childId(), revision: 1, family_id: familyId(), display_name: state.actor === 'parent-other' ? '小杉' : '小松', age_band: null, guardian_link: { id: `link-${childId()}`, revision: 1, learner_id: childId(), status: 'verified', declared_relationship: '父母', verification_method: 'fixture' } }] }; }
async function browserChecks() {
  const fixture = `
    import React, {useCallback} from 'react';import {createRoot} from 'react-dom/client';
    import './frontend/learning/index';import {LegacyFirstWorkPage as FirstWorkPage} from './frontend/learning/FirstWorkPage';import {EntryTransfer} from './frontend/learning/EntrySummary';import {ApiError} from './frontend/learning/api';import './frontend/learning/learning.css';
    const api={request:async(p,method='GET',b)=>{const r=await fetch('/api/learning/v2'+p,{method,headers:{'Content-Type':'application/json'},body:b===undefined?undefined:JSON.stringify(b)});const data=await r.json();if(!r.ok)throw new ApiError(r.status,data.error.code,'fixture');return data;}};
    window.routes=[];const config={studio_enabled:true,learning_enabled:true,live_enabled:false};
    function Direct(){const guard=useCallback(()=>{},[]);const navigate=useCallback(async r=>{window.routes.push(r);history.replaceState(null,'',r);return true;},[]);return new URLSearchParams(location.search).get('view')==='transfer'?<EntryTransfer api={api} learnerId="child-fixture" learnerName="小松" onDirty={guard}/>:<FirstWorkPage api={api} learnerId="child-fixture" config={config} setGuard={guard} navigate={navigate}/>;}
    if(new URLSearchParams(location.search).get('view')==='app'){window.handle=window.SongbanLearning.mount(document.getElementById('host'),{initialRoute:location.hash,onRouteChange:r=>{window.routes.push(r);history.replaceState(null,'',r);}});}else{createRoot(document.getElementById('host')).render(<Direct/>);}`;
  await esbuild.build({ stdin: { contents: fixture, resolveDir: root, loader: 'jsx' }, bundle: true, jsx: 'automatic', format: 'iife', outfile: path.join(out, 'fixture.js'), define: { 'process.env.NODE_ENV': '"development"' } });
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1280, height: 960 } });
  const page = await context.newPage(); page.setDefaultTimeout(5000); page.on('pageerror', e => errors.push(e.message));
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), p = decodeURIComponent(url.pathname.replace('/api/learning/v2', ''));
    const json = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    const fail = (status, code) => json({ error: { code } }, status);
    if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><link rel="stylesheet" href="/fixture.css"><div id="host"></div><script src="/fixture.js"></script>' });
    if (url.pathname === '/fixture.js' || url.pathname === '/fixture.css') return route.fulfill({ contentType: url.pathname.endsWith('.js') ? 'text/javascript' : 'text/css', body: fs.readFileSync(path.join(out, url.pathname.slice(1))) });
    if (url.pathname === '/static/design/pine-mascot.png') return route.fulfill({ contentType: 'image/png', body: fs.readFileSync(path.join(root, url.pathname.slice(1))) });
    assert.ok(url.pathname.startsWith('/api/learning/v2/'), `Unexpected network ${url}`);
    const method = request.method(), body = request.postDataJSON();
    (method === 'GET' ? state.reads : state.writes).push({ path: p, method, body });
    if (p === '/config') return json({ contract_version: 'fixture', learning_enabled: true, live_enabled: false, studio_enabled: true, publication_enabled: false, age_band_options: [], consent_version: consentText.consent_version, notice: '' });
    if (p === '/session') return json(currentSession());
    if (p === '/session-bootstrap') return json({ csrf_token: 'fixture-csrf', browser_revision: state.epoch });
    if (p === '/families') return json({ items: [family()], next_cursor: null });
    if (p === `/families/${familyId()}`) return json(family());
    if (p === `/learners/${childId()}/consents`) return json({ learner_id: childId(), relationship_status: 'verified', visibility: 'own_submissions', items: [{ id: 'consent-fixture', revision: 1, learner_id: childId(), consent_version: consentText.consent_version, scopes: ['learning'], effective_scopes: ['learning'], status: 'active', recorded_at: '2026-11-02T00:00:00Z', text_sha256: consentText.text_sha256 }], next_cursor: null });
    if (p.startsWith('/consent-texts/')) return json(consentText);
    if (p === '/sessions/authenticate') { assert.ok(['parent-fixture', 'parent-other'].includes(body.account)); assert.equal(body.proof, 'synthetic-password'); state.actor = body.account; state.mode = 'manager'; state.epoch++; return json(currentSession()); }
    if (p === '/sessions/enter-learner') { assert.equal(body.learner_id, childId()); state.mode = 'learner'; state.epoch++; return json(currentSession()); }
    if (p === `/learners/${childId()}/home`) return json(home());
    if (p === '/courses') return state.failCourses ? fail(423, 'course_unavailable') : json({ items: [course], next_cursor: null });
    if (p === `/learners/${childId()}/entry`) {
      if (state.failEntry) return fail(503, 'entry_unavailable');
      if (method === 'POST') { assert.equal(body.expected_revision, state.entry.revision); assert.equal(body.source_version, 11); assert.equal(body.subject_confirmed, true); state.entry = { ...state.entry, status: 'offered', revision: state.entry.revision + 1 }; }
      return json({ ...state.entry, learner_id: childId() });
    }
    if (p === '/learners/child-fixture/entry/confirm') { assert.equal(body.expected_revision, state.entry.revision); assert.ok(['accept', 'decline'].includes(body.decision)); state.entry = { ...state.entry, revision: state.entry.revision + 1, status: body.decision === 'accept' ? 'confirmed' : 'declined' }; return json(state.entry); }
    if (p === '/learners/child-fixture/runs') { if (state.delayCreate) await new Promise(r => setTimeout(r, 150)); if (!state.run) { state.run = 'run-created'; state.creates++; } return json({ id: state.run }); }
    if (p.startsWith('/runs/')) return fail(404, 'fixture_run_not_loaded');
    return fail(404, 'unexpected_fixture_request');
  });
  let pageNumber = 0;
  const open = (view = 'first', hash = '#/learn/first') => page.goto(`http://127.0.0.1:43221/?view=${view}&fixture=${++pageNumber}${hash}`);
  const button = name => page.getByRole('button', { name, exact: true });
  const routeIs = r => page.waitForFunction(expected => location.hash === expected, r);
  try {
    await check('Existing work resumes by read-only navigation', async () => { reset({ run: 'run-old' }); await open(); await routeIs('#/learn/run?id=run-old'); assert.equal(state.writes.length, 0); });
    await check('A new enrollment starts once despite rapid clicks; refresh resumes without creation', async () => {
      reset({ delayCreate: true }); await open(); await button('开始我的第一个作品').waitFor();
      await button('开始我的第一个作品').evaluate(e => { e.click(); e.click(); }); await routeIs('#/learn/run?id=run-created');
      assert.equal(state.writes.length, 1); assert.equal(state.creates, 1); assert.equal(state.writes[0].body.enrollment_id, enrollment.id);
      await open(); await routeIs('#/learn/run?id=run-created'); assert.equal(state.writes.length, 1);
    });
    await check('No enrollment gives preparation guidance without a repeated questionnaire', async () => { reset({ entitlement: false }); await open(); await button('请家长帮我准备').waitFor(); assert.equal(await page.locator('textarea').count(), 0); assert.equal(await button('开始我的第一个作品').count(), 0); assert.equal(state.writes.length, 0); assert.ok(!state.reads.some(r => r.path.endsWith('/start'))); });
    for (const decision of ['accept', 'decline']) await check(`Offered summary requires explicit ${decision} with revision and never advances the course`, async () => {
      reset(); state.entry.status = 'offered'; await open(); await button('这是我的想法，继续').waitFor(); assert.equal(state.writes.length, 0); assert.equal(await button('开始我的第一个作品').count(), 0);
      await button(decision === 'accept' ? '这是我的想法，继续' : '暂不采用，从简单提示开始').click(); await button('开始我的第一个作品').waitFor();
      assert.equal(state.writes.length, 1); assert.equal(state.writes[0].body.expected_revision, 7); assert.equal(state.writes[0].body.decision, decision); assert.equal(state.creates, 0); assert.ok(!state.writes.some(w => /checks|start|consents/.test(w.path)));
    });
    await check('Manager transfer requires selected fields and the child-subject assertion', async () => {
      reset({ mode: 'manager' }); state.entry.candidate = { source_version: 11, goals: ['想做邀请卡'], experiences: ['修改过提示'] }; await open('transfer'); await page.getByText('将已确认的访谈带给小松（选填）', { exact: true }).click();
      assert.equal(await button('提供给孩子确认').isDisabled(), true);
      await page.getByRole('checkbox', { name: '想做的事', exact: true }).check(); assert.equal(await button('提供给孩子确认').isDisabled(), true);
      await page.getByRole('checkbox', { name: '我确认这份访谈描述的是小松', exact: true }).check(); await button('提供给孩子确认').click();
      await page.getByText('摘要已保存，等待孩子本人确认。', { exact: true }).waitFor();
      assert.equal(state.writes.length, 1); assert.equal(state.writes[0].body.source_version, 11); assert.deepEqual(state.writes[0].body.selected_fields, ['goals']); assert.equal(state.writes[0].body.subject_confirmed, true); assert.equal(state.entry.status, 'offered'); assert.equal(state.creates, 0);
    });
    for (const target of ['#/learn/first', '#/learn/run?id=deep-link']) await check(`Manager-to-child keeps the original target ${target}`, async () => {
      reset({ mode: 'manager', entitlement: false }); await open('app', target); await button('进入孩子学习模式').click(); await button('确认进入').click();
      await page.waitForFunction(expected => window.routes.includes(expected), target); await routeIs(target);
      assert.equal(state.writes.length, 1); assert.equal(state.writes[0].path, '/sessions/enter-learner'); assert.equal(state.creates, 0);
    });
    for (const otherFamily of [false, true]) await check(otherFamily ? 'Child A to another parent account to child B resets the bound run target' : 'Child A to its parent account to child A preserves the bound run target', async () => {
      reset({ runs: { 'child-fixture': 'run-child-a', 'child-other': null } });
      const original = '#/learn/run?id=run-child-a';
      await open('app', original); await button('家长管理').click();
      await page.getByLabel('已有账号', { exact: true }).fill(otherFamily ? 'parent-other' : 'parent-fixture');
      await page.getByLabel('密码', { exact: true }).fill('synthetic-password');
      await button('重新认证并进入管理').click();
      await page.getByRole('heading', { name: otherFamily ? '小杉' : '小松', exact: true }).waitFor();
      await button('进入孩子学习模式').click();
      const readOffset = state.reads.length;
      await button('确认进入').click();
      await routeIs(otherFamily ? '#/learn/first' : original);
      if (otherFamily) {
        await button('和老师试用 AI').waitFor();
        await page.getByText('以前的邀请卡与访谈记录', { exact: true }).click();
        await button('开始我的第一个作品').waitFor();
        assert.ok(state.reads.slice(readOffset).some(r => r.path === '/learners/child-other/home'));
        assert.ok(!state.reads.slice(readOffset).some(r => r.path.includes('run-child-a') || r.path.includes('/learners/child-fixture/')));
      } else await page.waitForFunction(() => location.hash === '#/learn/run?id=run-child-a');
      assert.deepEqual(state.writes.map(w => w.path), ['/sessions/authenticate', '/sessions/enter-learner']);
      assert.equal(state.writes[1].body.learner_id, otherFamily ? 'child-other' : 'child-fixture');
      assert.equal(state.creates, 0);
    });
    await check('Pausing the course directory does not strand an already authorized work', async () => { reset({ run: 'run-existing', failCourses: true }); await open(); await routeIs('#/learn/run?id=run-existing'); assert.equal(state.writes.length, 0); });
    await page.screenshot({ path: path.join(out, 'entry-final.png'), fullPage: true });
  } finally { await browser.close(); }
}
async function legacyChecks() {
  const shell = fs.readFileSync(path.join(root, 'static/songban.js'), 'utf8');
  const journey = fs.readFileSync(path.join(root, 'static/songban-journey.js'), 'utf8');
  const wants = shell.slice(shell.indexOf('function wantsLearning('), shell.indexOf('function learningStageNavigation('));
  const routes = shell.slice(shell.indexOf('function routeFromHash('), shell.indexOf("document.addEventListener('DOMContentLoaded'"));
  const routeMap = shell.match(/const routePages = (\{[^;]+\});/)[0];
  async function simulate(hash, stale = false) {
    const memory = new Map(stale ? [['songban-learning-intent', 'learn']] : []), button = {}, host = { innerHTML: '', isConnected: true, insertAdjacentHTML(_p, html) { this.innerHTML += html; } };
    const c = { URLSearchParams, crypto, console, learningNavigationEnabled: true, usesIdeaWorkflow: () => true, state: { page: 'login', me: { id: 'fixture' }, flow: { strict: true, stage: 'interview' } }, window: {}, location: { hash, assign: target => { c.destination = target; } }, sessionStorage: { getItem: k => memory.get(k) || null, setItem: (k, v) => memory.set(k, v), removeItem: k => memory.delete(k) }, $: selector => selector === '#content' ? host : button, head: () => '', esc: s => String(s), load: async () => {}, go: target => { c.destination = target; }, toast: text => { throw Error(text); }, api: async (_url, body) => body ? { confirmed: true } : { status: 'pending_confirmation', version: 4, profile: { draft: { goals: [{ text: '虚构想法' }] } } } };
    vm.createContext(c); vm.runInContext(routeMap + wants + routes + journey, c); vm.runInContext('routeFromHash()', c); c.intentBeforeGate = vm.runInContext('wantsLearning()', c); vm.runInContext('gateJourney()', c); await vm.runInContext('interviewPage()', c); await button.onclick(); return c;
  }
  await check('Legacy learning interview confirmation enters first work preparation', async () => { const c = await simulate('#/interview?entry=learn'); assert.equal(c.destination, '/learning-prep#/learn/first'); });
  await check('Legacy competition confirmation keeps contest destination', async () => { const c = await simulate('#/interview'); assert.equal(c.destination, 'contest'); });
  await check('Explicit competition entry clears stale learning intent before its journey guard', async () => { const c = await simulate('#/events', true); assert.equal(c.intentBeforeGate, false); assert.equal(c.destination, 'contest'); });
  await check('An explicit old interview bookmark is not stolen by stale learning intent', async () => { const c = await simulate('#/interview', true); assert.equal(c.intentBeforeGate, false); assert.equal(c.destination, 'contest'); });
}
(async () => { fs.mkdirSync(out, { recursive: true }); reset(); await browserChecks(); await legacyChecks(); const failed = results.filter(r => !r.passed); fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ results, errors, scope: 'synthetic browser/VM, not backend or real family evidence' }, null, 2)); console.log(JSON.stringify({ passed: results.length - failed.length, failed, errors, evidence: out }, null, 2)); if (failed.length || errors.length) process.exitCode = 1; })().catch(e => { console.error(e); process.exitCode = 1; });
