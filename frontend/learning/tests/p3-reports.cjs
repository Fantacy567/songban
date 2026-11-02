/* Offline browser contract fixture. No real children, model calls or operational staff. */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const { chromium } = require('playwright'), esbuild = require('esbuild');
const root = path.resolve(__dirname, '../../..');
const out = process.env.SONGBAN_P3_REPORT_EVIDENCE || 'E:/松伴/outputs/learning-p3-20261102/S09';
const contract = require(path.join(root, 'docs/planning/learning-roadmap/p0/contracts/openapi.proposed.json'));
const clone = x => JSON.parse(JSON.stringify(x));
function valid(s, v) {
  if (s.$ref) return valid(contract.components.schemas[s.$ref.split('/').pop()], v);
  if (s.anyOf && !s.anyOf.some(x => valid(x, v))) return false;
  if (s.allOf && !s.allOf.every(x => valid(x, v))) return false;
  if (s.if && !valid(valid(s.if, v) ? s.then || {} : s.else || {}, v)) return false;
  if ('const' in s && JSON.stringify(v) !== JSON.stringify(s.const)) return false;
  if (s.enum && !s.enum.includes(v)) return false;
  if (s.type === 'null') return v === null;
  if (s.type === 'object' && (!v || typeof v !== 'object' || Array.isArray(v))) return false;
  if (s.properties && v && typeof v === 'object') {
    if (s.required?.some(k => !(k in v))) return false;
    if (s.additionalProperties === false && Object.keys(v).some(k => !(k in s.properties))) return false;
    if (Object.entries(s.properties).some(([k, x]) => k in v && !valid(x, v[k]))) return false;
  }
  if (s.type === 'array' && (!Array.isArray(v) || v.length < (s.minItems || 0) || v.length > (s.maxItems ?? Infinity) || s.items && v.some(x => !valid(s.items, x)))) return false;
  if (s.type === 'string' && (typeof v !== 'string' || v.length < (s.minLength || 0) || v.length > (s.maxLength ?? Infinity))) return false;
  if (s.type === 'integer' && (!Number.isInteger(v) || v < (s.minimum ?? -Infinity) || v > (s.maximum ?? Infinity))) return false;
  if (s.type === 'boolean' && typeof v !== 'boolean') return false;
  return true;
}
const act = { type: 'wait_review', resource_id: 'run-fixture', label: '等待复核' };
const ref = id => ({ id, revision: 1 });
const run = { id: 'run-fixture', revision: 9, learner_id: 'learner-fixture', enrollment_id: 'enrollment', course_version_id: 'course', progress: ['clarify', 'create', 'review'].map(stage => ({ stage, lesson_version_id: 'lesson', state: 'passed', artifact_version_id: 'version-fixture', check_id: 'check-fixture', recheck_required: false })), current_action: act, parent_revision: 1, current_attempt_ref: ref('attempt'), current_requirements_ref: ref('requirements'), current_self_check_ref: ref('self'), current_reflection_ref: ref('reflection-fixture'), current_transfer_attempt_ref: ref('transfer'), current_artifact_id: 'artifact-fixture', active_model_run_id: null, allowed_actions: ['createReport'] };
const help = { kind: 'unknown', note: '', child_confirmed: false, example_source_ids: [] };
const artifact = { id: 'artifact-fixture', revision: 2, learner_id: run.learner_id, run_id: run.id, check_status: 'passed', parent_revision: 9, allowed_actions: [], saved_at: '2026-11-02T08:00:00Z', current_version: { id: 'version-fixture', artifact_id: 'artifact-fixture', version: 2, content: { title: '虚构活动', audience: '同学', date: '2030年', start_time: '14:00', end_time: '15:00', place: '活动室', preparation: '故事书', invitation_line: '一起分享吧' }, attempt_id: 'attempt', attempt_revision: 1, model_run_id: 'model', template_version_id: 'template', help_event_ids: [], authorship: 'ai_candidate_edited', created_at: '2026-11-02T08:00:00Z', help_disclosure: help } };
const freshReport = () => ({ id: 'report-fixture', revision: 2, learner_id: run.learner_id, run_id: run.id, status: 'draft', generation_status: 'succeeded', source_snapshot_id: 'snapshot-fixture', source_hash: 'sha256-fixture', observations: [{ text: '核对过保存作品的地点。<script>window.injected=true</script>', source_ids: ['reflection-fixture'], nature: 'ai_suggestion' }], limitations: ['模拟（mock）整理，没有调用真实供应商。', '尚不能证明独立完成或外部工具掌握。'], evidence_changed: false, review_id: null, publication_id: null, parent_revision: 10, allowed_actions: [] });
const newCase = (kind, id) => ({ id, revision: 1, kind, target_id: kind === 'report_review' ? 'report-fixture' : 'check-fixture', status: 'open', owner_display_name: '合成复核员', due_at: '2026-11-03T08:00:00Z', feedback: null, next_action: act, parent_revision: 1, allowed_actions: ['claimCase'], support_contact_label: '隔离测试支持', learner_id: run.learner_id });
const state = { role: 'learner', report: null, cases: [], writes: [], requests: new Map(), fail: null, drop: null, live: false, reports: true, denyReports: false, enabled: true };
const results = [], errors = [];
const record = name => results.push({ name, passed: true });
function projection() {
  const r = clone(state.report);
  if (state.role === 'manager') r.allowed_actions = r.status === 'published' ? ['revokeReport'] : [];
  else if (state.role === 'learner') r.allowed_actions = r.generation_status !== 'succeeded' ? [] : r.status === 'draft' ? ['disputeReport', 'submitReport'] : ['disputeReport'];
  else r.allowed_actions = state.cases.find(c => c.target_id === r.id)?.status === 'claimed' ? (r.review_id ? ['reviewReport', 'publishReport'] : ['reviewReport']) : r.status === 'published' ? ['revokeReport'] : [];
  return r;
}
async function main() {
  fs.mkdirSync(out, { recursive: true });
  await esbuild.build({ stdin: { contents: `import React from 'react'; import {createRoot} from 'react-dom/client'; import {LearningApi} from './frontend/learning/api'; import {ReportsPanel,ParentReports} from './frontend/learning/ReportsPanel'; import {ReviewAdmin} from './frontend/learning/ReviewAdmin'; import './frontend/learning/learning.css';
const api=new LearningApi({initialRoute:'#/learn'});window.api=api;const root=createRoot(document.getElementById('host'));window.unmount=()=>{root.unmount();api.dispose();}; api.revalidate().then(()=>{const session=api.snapshot().session;root.render(React.createElement(session.mode==='staff'?ReviewAdmin:session.mode==='manager'?ParentReports:ReportsPanel,{api,session,learnerId:'learner-fixture',run:${JSON.stringify(run)},onDirty:(v)=>window.dirty=v}));});`, resolveDir: root, loader: 'tsx' }, bundle: true, jsx: 'automatic', format: 'iife', outfile: path.join(out, 'report-fixture.js'), define: { 'process.env.NODE_ENV': '"development"' } });
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
  await context.route('**/*', async route => {
    const req = route.request(), u = new URL(req.url()), method = req.method();
    if (u.pathname === '/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><link rel="stylesheet" href="/fixture.css"><div id="host" data-learning-root></div><script src="/fixture.js"></script>' });
    if (u.pathname === '/fixture.js') return route.fulfill({ contentType: 'text/javascript', body: fs.readFileSync(path.join(out, 'report-fixture.js')) });
    if (u.pathname === '/fixture.css') return route.fulfill({ contentType: 'text/css', body: fs.readFileSync(path.join(out, 'report-fixture.css')) });
    if (!u.pathname.startsWith('/api/learning/v2')) return route.fulfill({ status: 404 });
    const p = u.pathname.slice('/api/learning/v2'.length), body = req.postDataJSON();
    const op = Object.entries(contract.paths).find(([template, ops]) => ops[method.toLowerCase()] && new RegExp('^'+template.replace(/\{[^}]+\}/g, '[^/]+')+'$').test(p))?.[1][method.toLowerCase()];
    assert.ok(op, `${method} ${p} is frozen`);
    const fail = (status, code) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ error: { code, message: code, retryable: status >= 500, recovery: 'reload', current_revision: null } }) });
    async function reply(value, status = 200) {
      const schema = op.responses[status]?.content?.['application/json'].schema;
      if (schema && p !== '/config') assert.ok(valid(schema, value), `Response violates ${p}: ${JSON.stringify(value)}`);
      if (method !== 'GET') state.requests.set(body.request_id, { body: clone(body), value: clone(value), status });
      if (state.drop === p && method !== 'GET') { state.drop = null; return route.abort('failed'); }
      return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    }
    if (method !== 'GET') {
      assert.ok(valid(op.requestBody.content['application/json'].schema, body), `Request violates ${p}: ${JSON.stringify(body)}`);
      assert.equal(req.headers()['x-csrf-token'], 'fixture-csrf');
      state.writes.push({ p, body: clone(body) });
      if (state.requests.has(body.request_id)) { const cached = state.requests.get(body.request_id); assert.deepEqual(body, cached.body); return reply(cached.value, cached.status); }
      if (state.fail?.path === p) { const failure = state.fail; state.fail = null; return fail(failure.status, failure.code); }
    }
    if (p === '/session') return reply({ id: 'session-'+state.role, revision: 1, mode: state.role, actor_id: state.role, learner_id: state.role === 'learner' ? run.learner_id : null, mode_epoch: 1, scopes: [state.role === 'staff' ? 'report_review' : state.role === 'manager' ? 'family_manage' : 'learning'], expires_at: '2030-01-01T08:00:00Z' });
    if (p === '/session-bootstrap') return reply({ csrf_token: 'fixture-csrf', browser_revision: 1 });
    if (p === '/config') return reply({ contract_version: '0.2.2', learning_enabled: state.enabled, live_enabled: state.live, mock_enabled: true, reports_enabled: state.reports, publication_enabled: true, age_band_options: [], consent_version: 'fixture', notice: '隔离测试' });
    if (p === '/runs/run-fixture') return reply(run);
    if (p === '/artifacts/artifact-fixture') return reply(artifact);
    if (state.denyReports && p.endsWith('/reports') && method === 'GET') return fail(404, 'resource_not_found');
    if (p.endsWith('/reports') && method === 'GET') return reply({ items: state.report && (state.role !== 'manager' || state.report.status === 'published') && state.report.status !== 'revoked' ? [projection()] : [], next_cursor: null });
    if (p === '/runs/run-fixture/reports') { assert.equal(body.mode, 'mock'); assert.equal(body.check_id, 'check-fixture'); assert.equal(body.artifact_version_id, 'version-fixture'); state.report = freshReport(); return reply(projection(), 202); }
    if (p === '/reports/report-fixture' && method === 'GET') return reply(projection());
    if (p.endsWith('/disputes')) { state.report.revision++; state.report.review_id = null; return reply({ id: 'dispute-fixture', revision: 1, report_id: state.report.id, status: 'open', parent_revision: state.report.revision }, 201); }
    if (p.endsWith('/submit-review')) { state.report.status = 'pending_review'; state.report.revision++; state.cases = [newCase('report_review', 'case-report')]; return reply(projection()); }
    if (p === '/cases') return reply({ items: state.cases, next_cursor: null });
    const c = state.cases.find(c => p.startsWith('/cases/'+c.id));
    if (c) {
      if (p.endsWith('/evidence')) return reply({ case_id: c.id, target_revision: c.parent_revision, sources: [{ ref: { source_id: 'reflection-fixture', source_version: '1', source_domain: 'learning_v2', nature: 'child_statement' }, redacted_text: '虚构本人说明：得到操作帮助。<script>window.injected=true</script>', visibility: 'assigned_reviewer_only' }] });
      if (p.endsWith('/claim')) { c.status = 'claimed'; c.revision++; c.allowed_actions = ['resolveCase', 'appendCase', 'transferCase', 'extendCase']; return reply(c); }
      if (p.endsWith('/resolve')) { c.status = body.decision === 'needs_information' ? 'claimed' : 'resolved'; c.feedback = body.note; c.revision++; return reply(c); }
      if (p.endsWith('/messages')) { c.revision++; return reply(c); }
      if (method === 'GET') return reply(c);
    }
    if (p.endsWith('/reviews')) { state.report.revision++; state.report.review_id = 'review-'+state.report.revision; state.report.observations = clone(body.corrected_observations); if (body.decision === 'changes_requested') state.report.status = 'draft'; return reply(projection()); }
    if (p.endsWith('/publications')) { assert.equal(body.review_id, state.report.review_id); assert.equal(body.expected_revision, state.report.revision); state.report.status = 'published'; state.report.revision++; state.report.publication_id = 'publication'; state.cases.find(c => c.kind === 'report_review').status = 'resolved'; return reply({ id: 'publication', revision: 1, report_id: state.report.id, published_revision: state.report.revision, published_at: '2026-11-02T08:00:00Z', parent_revision: state.report.revision }, 201); }
    if (p.endsWith('/revocations')) { state.report.status = 'revoked'; state.report.revision++; return reply(state.report); }
    throw new Error('Unhandled '+method+' '+p);
  });
  async function reload(role) { state.role = role; await page.goto('https://report.example.test/'); await page.getByRole('heading', { name: role === 'staff' ? '人工复核待办' : role === 'manager' ? '孩子的学习报告' : '看看这次练习的记录', exact: true }).waitFor(); }
  try {
    await reload('learner'); await page.getByText('还没有报告。', { exact: false }).waitFor();
    assert.equal(state.writes.length, 0); record('mount reads only; no automatic report or child answers');
    assert.equal(await page.getByLabel('报告整理方式').inputValue(), 'mock');
    assert.equal(await page.locator('option[value=live]').evaluate(el => el.disabled), true); record('explicit mock default; unavailable live cannot be chosen');
    state.drop = '/runs/run-fixture/reports'; await page.getByRole('button', { name: '整理一份新报告' }).click();
    await page.getByRole('button', { name: '核对并重试原操作' }).waitFor();
    const firstCreate = clone(state.writes.at(-1)); await page.getByRole('button', { name: '核对并重试原操作' }).click();
    await page.getByRole('heading', { name: '请核对事实', exact: true }).waitFor();
    assert.deepEqual(state.writes.at(-1), firstCreate); record('lost create receipt uses exact body and request_id');
    assert.equal(await page.evaluate(() => window.injected), undefined); record('report text is escaped; AI observations remain marked');
    assert.equal(await page.getByRole('button', { name: '请老师复核这份报告' }).isDisabled(), true); record('fact confirmation is never prefilled');
    await page.getByText('有事实不准确', { exact: true }).click(); await page.getByLabel('哪一处需要改正？').fill('我得到了操作帮助，请记录。');
    state.fail = { path: '/reports/report-fixture/disputes', status: 422, code: 'invalid_sources' }; await page.getByRole('button', { name: '保存事实异议' }).click();
    await page.getByRole('alert').waitFor(); assert.equal(await page.getByLabel('哪一处需要改正？').inputValue(), '我得到了操作帮助，请记录。'); record('known failure preserves child dispute input');
    await page.getByRole('button', { name: '保存事实异议' }).click(); await page.waitForFunction(() => !window.dirty);
    await page.getByLabel('我已经核对这些事实，需要改正的地方已提交异议').check();
    state.fail = { path: '/reports/report-fixture/submit-review', status: 503, code: 'support_unavailable' }; await page.getByRole('button', { name: '请老师复核这份报告' }).click();
    await page.getByRole('alert').waitFor(); assert.equal(state.report.status, 'draft'); record('no staff queue never becomes sent or online promise');
    state.drop = '/reports/report-fixture/submit-review'; await page.getByRole('button', { name: '请老师复核这份报告' }).click();
    await page.getByRole('button', { name: '核对并重试原操作' }).waitFor(); const firstSubmit = clone(state.writes.at(-1));
    await page.getByRole('button', { name: '核对并重试原操作' }).click(); await page.getByRole('heading', { name: '已送报告复核', exact: true }).waitFor(); assert.deepEqual(state.writes.at(-1), firstSubmit); record('unknown submit reads then retries original request');
    await reload('manager'); await page.getByText('目前还没有已发布的报告。').waitFor(); assert.equal(await page.getByRole('article').count(), 0); record('manager cannot see drafts or pending reviews');
    state.cases.push(newCase('learning_review', 'case-learning'));
    await reload('staff'); await page.getByRole('button', { name: /学习报告复核 · 待认领/ }).click(); await page.getByRole('button', { name: '认领这项复核' }).click();
    await page.getByRole('button', { name: '确认本版本复核通过' }).waitFor(); assert.equal(await page.getByRole('button', { name: '确认本版本复核通过' }).isDisabled(), true); record('teacher must claim; no auto approval or prefilled feedback');
    await page.getByText(/孩子自己的说明 · reflection-fixture/).click(); assert.equal(await page.evaluate(() => window.injected), undefined); record('assigned evidence displayed as text with source version');
    await page.getByLabel('观察 1', { exact: true }).fill('已记录帮助与本人解释，不能据此推断完全独立。'); await page.getByLabel('给孩子的具体反馈').fill('已核对本人保存事实和帮助。');
    state.fail = { path: '/reports/report-fixture/reviews', status: 409, code: 'revision_conflict' }; await page.getByRole('button', { name: '确认本版本复核通过' }).click();
    await page.getByRole('button', { name: '读取最新记录，保留我的输入' }).click(); assert.equal(await page.getByLabel('观察 1', { exact: true }).inputValue(), '已记录帮助与本人解释，不能据此推断完全独立。'); record('revision conflict keeps teacher correction; no automatic overwrite');
    state.report.revision++;
    await page.getByRole('button', { name: '重新读取待办' }).click();
    await page.getByRole('button', { name: '已核对最新版本，保留我的修改' }).waitFor();
    assert.equal(await page.getByRole('button', { name: '确认本版本复核通过' }).isDisabled(), true);
    await page.getByRole('button', { name: '已核对最新版本，保留我的修改' }).click(); record('changed report revision requires explicit reconciliation of teacher edits');
    await page.getByRole('button', { name: '确认本版本复核通过' }).click(); await page.getByRole('button', { name: '发布已批准的这一版给家长' }).waitFor();
    assert.equal(state.report.observations[0].nature, 'human_review'); record('teacher edits are distinct from model suggestions');
    const approved = clone(state.report); state.drop = '/reports/report-fixture/publications'; await page.getByRole('button', { name: '发布已批准的这一版给家长' }).click();
    await page.getByRole('button', { name: '核对并重试原操作' }).click(); await page.getByRole('heading', { name: '已发布给家长', exact: true }).waitFor();
    const publishWrites = state.writes.filter(w => w.p.endsWith('/publications')); assert.deepEqual(publishWrites[0], publishWrites[1]); assert.equal(publishWrites[0].body.expected_revision, approved.revision); record('publish binds exact approval; lost receipt never changes ID');
    await page.getByRole('button', { name: /学习作品复核 · 待认领/ }).click(); await page.getByRole('button', { name: '认领这项复核' }).click();
    await page.getByLabel('人工处理结论').waitFor(); assert.equal(await page.getByLabel('人工处理结论').inputValue(), 'needs_information');
    assert.equal(await page.getByLabel('M1 判断').inputValue(), 'unclear'); await page.getByLabel('给孩子的具体反馈').fill('请补充判断依据。');
    await page.getByRole('checkbox', { name: 'reflection-fixture', exact: true }).check();
    for (const m of ['M1', 'M2', 'M3', 'M4']) await page.getByLabel(m+' 依据说明').fill('尚需要本人说明与材料核对。');
    await page.getByRole('button', { name: '保存人工反馈' }).click(); await page.getByText('请补充判断依据。', { exact: true }).waitFor();
    assert.equal(state.writes.at(-1).body.decision, 'needs_information'); assert.ok(state.writes.at(-1).body.manual_findings.every(f => f.verdict === 'unclear')); record('learning review preserves explicit M1–M4 and manual feedback');
    await reload('manager'); await page.getByRole('button', { name: /查看报告/ }).click(); await page.getByRole('heading', { name: '已发布给家长', exact: true }).waitFor(); record('parent reads only published snapshot with limitations');
    for (const width of [390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1));
      await page.screenshot({ path: path.join(out, `parent-report-${width}.png`), fullPage: true });
    } record('390/768/1440 published report has no horizontal overflow');
    await page.setViewportSize({ width: 768, height: 1000 }); await page.evaluate(() => document.documentElement.style.zoom = '2');
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)); await page.screenshot({ path: path.join(out, 'parent-report-200percent.png'), fullPage: true });
    await page.evaluate(() => document.documentElement.style.zoom = '1'); record('200 percent report zoom stays usable without horizontal overflow');
    state.denyReports = true; await page.getByRole('button', { name: '重新读取报告' }).click(); await page.getByRole('alert').waitFor();
    assert.equal(await page.getByRole('article').count(), 0); record('authorization denial removes previously visible report contents');
    state.denyReports = false; await page.getByRole('button', { name: '重新读取报告' }).click(); await page.getByRole('heading', { name: '已发布给家长', exact: true }).waitFor();
    await page.getByText('撤回这份报告', { exact: true }).click(); await page.getByLabel('撤回原因').fill('停止展示这一版。');
    await page.getByRole('button', { name: '确认撤回报告' }).click(); await page.getByText('目前还没有已发布的报告。').waitFor(); record('parent revocation removes visible publication');
    state.report = freshReport(); state.report.generation_status = 'unknown'; state.report.observations = [];
    await reload('learner'); await page.getByRole('button', { name: /查看报告/ }).click(); await page.getByText('结果还在核对，请勿重复生成').waitFor();
    assert.equal(await page.getByRole('button', { name: '整理一份新报告' }).isDisabled(), true); record('unknown generation blocks duplicate create');
    state.report.generation_status = 'succeeded'; await page.getByRole('button', { name: '重新读取报告' }).click();
    await page.getByText('有事实不准确', { exact: true }).click(); await page.getByLabel('哪一处需要改正？').fill('尚未保存的异议'); await page.waitForFunction(() => window.dirty === true);
    await page.evaluate(() => window.unmount()); await page.waitForFunction(() => window.dirty === false); record('dirty state propagates and resets on unmount');
    state.enabled = false; await reload('learner'); await page.getByRole('button', { name: /查看报告/ }).click();
    await page.getByLabel('我已经核对这些事实，需要改正的地方已提交异议').check();
    assert.equal(await page.getByRole('button', { name: '请老师复核这份报告' }).isDisabled(), true);
    assert.equal(await page.getByRole('button', { name: '整理一份新报告' }).isDisabled(), true); record('paused learning keeps history readable and blocks new child writes');
    assert.deepEqual(errors, []); record('no browser exceptions');
    fs.writeFileSync(path.join(out, 'browser-results.json'), JSON.stringify({ fixture: true, real_model: false, results, errors }, null, 2));
    console.log(JSON.stringify({ passed: results.length, output: out }));
  } catch (e) { await page.screenshot({ path: path.join(out, 'browser-failure.png'), fullPage: true }); fs.writeFileSync(path.join(out, 'browser-failure.json'), JSON.stringify({ message: e.message, results, errors }, null, 2)); throw e; }
  finally { await browser.close(); }
}
main().catch(e => { console.error(e); process.exitCode = 1; });
