/* Synthetic contract browser fixture only. No HTTP server, model, real DB or identities. */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const { chromium } = require('playwright'), esbuild = require('esbuild');
const root = path.resolve(__dirname, '../../..');
const out = path.resolve(process.env.SONGBAN_STUDIO_EVIDENCE || path.join(root, '../outputs/learning-experience/studio'));
const contract = require(path.join(root, 'docs/planning/learning-roadmap/p0/contracts/openapi.proposed.json'));
contract.components.schemas.Config.properties.studio_enabled = {type:'boolean'};
const clone = x => JSON.parse(JSON.stringify(x)), now = '2026-11-02T08:00:00Z';
function valid(s, v) {
  if (s.$ref) return valid(contract.components.schemas[s.$ref.split('/').pop()], v);
  if (s.anyOf && !s.anyOf.some(x => valid(x, v))) return false;
  if (s.oneOf && s.oneOf.filter(x => valid(x, v)).length !== 1) return false;
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
  if (s.type === 'array' && (!Array.isArray(v) || v.length < (s.minItems || 0) || v.length > (s.maxItems || Infinity) || v.some(x => !valid(s.items, x)))) return false;
  if (s.type === 'string' && (typeof v !== 'string' || v.length < (s.minLength || 0) || v.length > (s.maxLength || Infinity))) return false;
  if (s.type === 'integer' && (!Number.isInteger(v) || v < (s.minimum ?? -Infinity) || v > (s.maximum ?? Infinity))) return false;
  if (s.type === 'boolean' && typeof v !== 'boolean') return false;
  return true;
}
const help = { kind: 'unknown', note: '', child_confirmed: false, example_source_ids: [] };
const A = { event_name: '松果班故事交换会', audience: '松果班同学', date: '2030-05-18', start_time: '14:00', end_time: '15:00', place: '松果活动室', preparation: '带一本愿意分享的故事书' };
const B = { event_name: '星叶班纸桥挑战', audience: '星叶班同学', date: '2030-05-25', start_time: '10:00', end_time: '11:00', place: '星叶活动室', preparation: '带两张废旧A4纸' };
const labels = { event_name: '活动名称', audience: '邀请谁', date: '日期', start_time: '开始时间', end_time: '结束时间', place: '地点', preparation: '准备物品' };
const material = (id, facts) => ({ id, version: '0.1.0', source_type: 'fictional_course_material', facts, notice: '这是练习用的虚构活动，不是真实通知。', source_locators: Object.keys(facts).map(k => `${id}@0.1.0#${k}`) });
const course = { id: 'course-fixture', revision: 1, title: '班级活动邀请卡（模拟）', state: 'published', lesson_version_ids: ['lesson-fixture'], task_cards: ['S1.1', 'S1.2', 'S2.1', 'S2.2', 'S3.1', 'S3.2', 'S3.3', 'S3.4'].map(id => ({ id, version: '0.1.0', stage: id[1] === '1' ? 'clarify' : id[1] === '2' ? 'create' : 'review', goal: '独立完成本步', instructions: ['先读材料，再操作。'], material_version_ids: [id === 'S3.3' ? 'MAT_B@0.1.0' : 'MAT_A@0.1.0'], tool_card_ids: ['tool-fixture'], rubric_version_id: 'invitation-rubric@0.1.0', help_levels: ['H1', 'H2', 'H3'] })), tool_cards: [{ id: 'tool-fixture', version: '0.1.0', steps: ['核对要求', '开始模拟', '保存候选'], prompt_template: '只使用已确认要求', checks: ['核对活动事实'], notice: '模拟工具，不调用真实 AI' }] };
const allActions = ['saveRequirements', 'createAttempt', 'createModelRun', 'createArtifact', 'versionArtifact', 'checkArtifact', 'saveSelfCheck', 'reflect', 'help', 'askHuman'];
const state = { calls: [], writes: [], replay: new Map(), seq: 0, receipts: {}, versions: {}, checks: {}, helps: [], cases: [], req: null, attempt: null, transfer: null, artifact: null, self: null, reflection: null, model: null, run: null, drop: null, conflict: false, support: false, nextModel: 'succeeded', homeUnavailable: false, expire: false, delay: null };
const session = { id: 'session-fixture', revision: 1, mode: 'learner', actor_id: 'actor-fixture', learner_id: 'child-fixture', mode_epoch: 1, scopes: ['learning'], expires_at: '2099-01-01T00:00:00Z' };
const ref = v => v ? { id: v.id, revision: v.revision } : null;
const action = type => ({ type, resource_id: state.run?.id || null, label: '按当前任务做一步，再保存。' });
const enrollment = { id: 'enrollment-fixture', revision: 1, learner_id: session.learner_id, course_version_id: course.id, entitlement_id: 'grant-fixture', status: 'active', parent_revision: 1 };
function newRun() { return { id: 'run-fixture', revision: 1, learner_id: session.learner_id, enrollment_id: enrollment.id, course_version_id: course.id, progress: ['clarify', 'create', 'review'].map((stage, i) => ({ lesson_version_id: 'lesson-fixture', stage, state: i ? 'locked' : 'in_progress', artifact_version_id: null, check_id: null, recheck_required: false })), current_action: action('continue_run'), parent_revision: 1, current_attempt_ref: null, current_requirements_ref: null, current_self_check_ref: null, current_reflection_ref: null, current_transfer_attempt_ref: null, current_artifact_id: null, active_model_run_id: null, allowed_actions: allActions }; }
const results = [], errors = [];
const record = name => results.push({ name, passed: true });
async function main() {
  fs.mkdirSync(out, { recursive: true });
  await esbuild.build({ entryPoints: [path.join(root, 'frontend/learning/index.tsx')], bundle: true, jsx: 'automatic', format: 'iife', outfile: path.join(out, 'fixture.js'), define: { 'process.env.NODE_ENV': '"development"' } });
  const js = fs.readFileSync(path.join(out, 'fixture.js')), css = fs.readFileSync(path.join(out, 'fixture.css'));
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.route('**/*', async route => {
    const req = route.request(), url = new URL(req.url());
    if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><link rel="stylesheet" href="/fixture.css"><div id="host"></div><script src="/fixture.js"></script><script>window.handle=SongbanLearning.mount(document.getElementById("host"),{initialRoute:location.hash||"#/learn",onRouteChange:r=>history.replaceState(null,"",r)});</script>' });
    if (url.pathname === '/fixture.js') return route.fulfill({ contentType: 'text/javascript', body: js });
    if (url.pathname === '/fixture.css') return route.fulfill({ contentType: 'text/css', body: css });
    if (url.pathname === '/static/design/pine-mascot.png') return route.fulfill({ contentType: 'image/png', body: fs.readFileSync(path.join(root, 'static/design/pine-mascot.png')) });
    if (!url.pathname.startsWith('/api/learning/v2')) return route.fulfill({ status: 404, body: '' });
    const p = decodeURIComponent(url.pathname.slice('/api/learning/v2'.length)), method = req.method(), body = req.postDataJSON();
    state.calls.push({ p, method });
    const operation = Object.entries(contract.paths).find(([template, ops]) => ops[method.toLowerCase()] && new RegExp('^' + template.replace(/\{[^}]+\}/g, '[^/]+') + '$').test(p))?.[1][method.toLowerCase()];
    assert.ok(operation, `${method} ${p} must have frozen contract`);
    const fail = (status, code) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ error: { code, message: code, retryable: status >= 500, details: [] }, request_id: 'fixture-error' }) });
    async function reply(value, status = 200) {
      const schema = operation.responses[status]?.content?.['application/json'].schema || operation.responses[200]?.content?.['application/json'].schema;
      if (schema) assert.ok(valid(schema, value), `Response violates contract ${p}: ${JSON.stringify(value)}`);
      if (method !== 'GET') state.replay.set(body.request_id, { body: clone(body), value: clone(value), status });
      if (state.drop === p && method !== 'GET') { state.drop = null; return route.abort('failed'); }
      return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    }
    if (method !== 'GET') {
      assert.equal(req.headers()['x-csrf-token'], 'fixture-csrf');
      assert.ok(valid(operation.requestBody.content['application/json'].schema, body), `Invalid request ${p}: ${JSON.stringify(body)}`);
      state.writes.push({ p, method, body: clone(body) });
      if (state.replay.has(body.request_id)) { const prev = state.replay.get(body.request_id); if (JSON.stringify(prev.body) !== JSON.stringify(body)) return fail(409, 'idempotency_conflict'); return reply(prev.value, prev.status); }
    }
    if (p === '/session') return state.expire ? fail(401, 'session_expired') : reply(session);
    if (p === '/session-bootstrap') return reply({ csrf_token: 'fixture-csrf', browser_revision: 1 });
    if (p === '/config') return reply({ contract_version: '0.2.1', studio_enabled: true, learning_enabled: true, live_enabled: false, publication_enabled: false, age_band_options: [], consent_version: 'fixture-consent', notice: '隔离测试，仅使用虚构记录。' });
    if (state.expire) return fail(401, 'session_expired');
    if (p.endsWith('/home')) return state.homeUnavailable ? fail(503, 'operation_unavailable') : reply({ learner_id: session.learner_id, revision: 1, current_action: action(state.run ? 'continue_run' : 'start_run'), run_id: state.run?.id || null, progress: state.run?.progress || [], entitlements: [enrollment], allowed_actions: ['createRun'], missing_fields: [] });
    if (p === '/courses') return reply({ items: [course], next_cursor: null });
    if (p === '/courses/' + course.id) return reply(course);
    if (p.includes('/materials/')) { const id = p.split('/').pop(); return reply(material(id.startsWith('MAT_A') ? 'MAT_A' : 'MAT_B', id.startsWith('MAT_A') ? A : B)); }
    if (p === '/learners/child-fixture/runs') { assert.equal(body.expected_revision, 1); state.run = newRun(); return reply(state.run, 201); }
    if (p === '/runs/run-fixture' && method === 'GET') { if (state.delay) { const delayed = clone(state.run), wait = state.delay; state.delay = null; await wait; return reply(delayed); } return reply(state.run); }
    if (p === '/cases') return reply({ items: state.cases, next_cursor: null });
    if (p === '/runs/run-fixture/help' && method === 'GET') return reply({ items: state.helps, next_cursor: null });
    if (p === '/runs/run-fixture/help') { assert.equal(body.expected_revision, state.run.revision); const h = { id: 'help-' + ++state.seq, revision: 1, run_id: state.run.id, role_id: body.role_id, prompt_version: 'static-fixture', help_level: body.help_level, mode: body.mode, text: '先找到对象这一行，再自己决定怎样填写。', sources: [], actions: [], model_run_id: null, parent_revision: ++state.run.revision, task_id: body.task_id, task_card_version: body.task_card_version }; state.helps.push(h); return reply(h, 202); }
    if (p.endsWith('/requirements')) {
      if (method === 'GET') return state.req ? reply(state.req) : fail(404, 'resource_not_found');
      if (state.conflict) { state.conflict = false; state.req = { ...state.req, revision: state.req.revision + 1, purpose: '另一标签页保存的目的', parent_revision: ++state.run.revision }; state.run.current_requirements_ref = ref(state.req); return fail(409, 'revision_conflict'); }
      if (body.expected_revision !== (state.req?.revision || 0)) return fail(409, 'revision_conflict');
      const { request_id, expected_revision, ...fields } = body;
      state.req = { id: 'requirements-fixture', revision: expected_revision + 1, run_id: state.run.id, ...fields, parent_revision: ++state.run.revision, saved_at: now }; state.run.current_requirements_ref = ref(state.req); return reply(state.req);
    }
    if (p === '/runs/run-fixture/attempts') {
      assert.equal(body.expected_revision, state.run.revision);
      const { request_id, expected_revision, ...fields } = body;
      const attempt = { id: body.kind + '-fixture', revision: 1, run_id: state.run.id, ...fields, help_event_ids: state.helps.map(h => h.id), parent_revision: ++state.run.revision, allowed_actions: ['saveAttempt', 'createModelRun'], saved_at: now };
      if (body.kind === 'transfer') { state.transfer = attempt; state.run.current_transfer_attempt_ref = ref(attempt); } else { state.attempt = attempt; state.run.current_attempt_ref = ref(attempt); }
      return reply(attempt, 201);
    }
    if (/^\/attempts\/[^/]+$/.test(p)) {
      const attempt = p.includes('transfer') ? state.transfer : state.attempt;
      if (method === 'PATCH') { assert.equal(body.expected_revision, attempt.revision); const { request_id, expected_revision, ...fields } = body; Object.assign(attempt, fields, { revision: attempt.revision + 1, parent_revision: ++state.run.revision }); state.run.current_transfer_attempt_ref = ref(attempt); }
      return reply(attempt);
    }
    if (p.endsWith('/model-runs')) {
      assert.equal(body.mode, 'mock'); assert.equal(body.expected_revision, state.attempt.revision);
      const { event_name, ...facts } = state.req.facts;
      state.model = { id: 'model-fixture', revision: 1, attempt_id: state.attempt.id, report_id: null, help_event_id: null, mode: 'mock', status: state.nextModel, requested_model: null, actual_model: null, config_version: body.config_version, input_revision: state.attempt.revision, output_text: state.nextModel === 'succeeded' ? JSON.stringify({ title: '故事交换邀请卡', ...facts, invitation_line: '欢迎来参加活动。' }) : null, reservation_id: null, usage: { status: 'available', notice: '模拟不计真实调用' }, reconciliation_case_id: null, visibility: 'normal', parent_revision: ++state.run.revision };
      state.run.active_model_run_id = state.model.id; return reply(state.model, 202);
    }
    if (p === '/model-runs/model-fixture') return reply(state.model);
    if (p === '/runs/run-fixture/artifacts' || p === '/artifacts/artifact-fixture/versions') {
      assert.equal(body.expected_revision, state.artifact?.revision || state.run.revision);
      const version = (state.artifact?.current_version.version || 0) + 1;
      const v = { id: 'version-' + version, artifact_id: 'artifact-fixture', version, content: body.content, attempt_id: body.attempt_id, model_run_id: body.model_run_id, help_event_ids: body.help_event_ids, authorship: body.authorship, created_at: now, attempt_revision: body.attempt_revision, template_version_id: body.template_version_id, help_disclosure: body.help_disclosure };
      state.versions[v.id] = clone(v); state.artifact = { id: 'artifact-fixture', revision: (state.artifact?.revision || 0) + 1, learner_id: session.learner_id, run_id: state.run.id, current_version: v, check_status: version > 1 ? 'recheck_required' : 'unchecked', parent_revision: ++state.run.revision, allowed_actions: ['versionArtifact', 'readbackArtifact'], saved_at: now }; state.run.current_artifact_id = state.artifact.id; if (version > 1) Object.assign(state.run.progress[2], { state: 'in_progress', recheck_required: true, check_id: null }); return reply(state.artifact, 201);
    }
    if (p === '/artifacts/artifact-fixture') return reply(state.artifact);
    if (p === '/learners/child-fixture/artifacts') return reply({ items: state.artifact ? [state.artifact] : [], next_cursor: null });
    if (p.startsWith('/artifacts/artifact-fixture/versions/')) { const version = p.split('/').pop(); const receipt = 'receipt-' + ++state.seq; state.receipts[receipt] = version; return reply({ artifact_version: state.versions[version], read_receipt_id: receipt, artifact_revision: state.artifact.revision }); }
    if (p.endsWith('/readbacks')) { assert.equal(body.expected_revision, state.artifact.revision); return reply({ id: 'readback-' + ++state.seq, revision: 1, artifact_version_id: state.receipts[body.read_receipt_id], receipt_id: body.read_receipt_id, received_at: now, parent_revision: ++state.run.revision }, 201); }
    if (p.endsWith('/self-checks')) { assert.equal(body.expected_revision, state.run.revision); const { request_id, expected_revision, ...fields } = body; state.self = { id: 'self-fixture', revision: (state.self?.revision || 0) + 1, run_id: state.run.id, ...fields, parent_revision: ++state.run.revision, saved_at: now }; state.run.current_self_check_ref = ref(state.self); return reply(state.self, 201); }
    if (p === '/self-checks/self-fixture') return reply(state.self);
    if (p.endsWith('/reflections')) { assert.equal(body.expected_revision, state.run.revision); assert.deepEqual(body.self_check_ref, ref(state.self)); assert.equal(body.transfer_attempt_revision, state.transfer.revision); const { request_id, expected_revision, ...fields } = body; state.reflection = { id: 'reflection-fixture', revision: (state.reflection?.revision || 0) + 1, run_id: state.run.id, ...fields, parent_revision: ++state.run.revision, saved_at: now }; state.run.current_reflection_ref = ref(state.reflection); return reply(state.reflection, 201); }
    if (p === '/reflections/reflection-fixture') return reply(state.reflection);
    if (p.endsWith('/checks')) {
      assert.equal(body.expected_revision, state.run.revision);
      const { request_id, expected_revision, ...fields } = body;
      const c = { id: 'check-' + ++state.seq, revision: 1, run_id: state.run.id, learner_id: session.learner_id, ...fields, rule_result: 'pass', human_result: null, missing_evidence: [], feedback: ['已核对保存记录。'], case_id: null, evidence_hash: 'synthetic-hash', stale: false, parent_revision: ++state.run.revision, allowed_actions: [], evidence_complete: true, model_state: body.stage === 'clarify' ? 'none' : 'succeeded', reviewer_available: null, progress_effect: 'none', outcome: 'feedback_only' };
      if (body.purpose === 'advance') { if (body.stage === 'create') { assert.ok(body.readback_ref); assert.equal(body.artifact_version_id, state.artifact.current_version.id); } c.outcome = 'advanced'; c.progress_effect = 'passed_and_unlocked'; const i = state.run.progress.findIndex(p => p.stage === body.stage); state.run.progress[i].state = 'passed'; state.run.progress[i + 1].state = 'in_progress'; }
      if (body.purpose === 'submit_review') { c.reviewer_available = state.support; c.outcome = state.support ? 'awaiting_review' : 'blocked_support'; c.progress_effect = state.support ? 'pending_review' : 'none'; if (state.support) { c.case_id = 'case-fixture'; state.run.progress[2].state = 'pending_review'; state.cases = [{ id: c.case_id, revision: 1, kind: 'learning_review', target_id: c.id, status: 'open', owner_display_name: '值班老师（虚构）', due_at: '2030-05-18T12:00:00Z', feedback: null, next_action: action('wait_review'), parent_revision: state.run.revision, allowed_actions: ['appendCase'], support_contact_label: '请家长联系试点老师（虚构）', learner_id: session.learner_id }]; } }
      state.checks[c.id] = c;
      // Match the service: feedback-only preflight and blocked submissions do
      // not replace a stage's progress pointer or mark an artifact as passed.
      if (c.progress_effect !== 'none') { const p = state.run.progress.find(p => p.stage === body.stage); p.check_id = c.id; p.artifact_version_id = body.artifact_version_id; }
      return reply(c, 201);
    }
    if (p.startsWith('/checks/')) return reply(state.checks[p.split('/').pop()]);
    if (p.endsWith('/messages')) { const c = state.cases[0]; assert.equal(body.expected_revision, c.revision); c.revision++; return reply(c); }
    if (p === '/runs/run-fixture/cases') return fail(503, 'support_unavailable');
    if (p.endsWith('/profile')) return reply({ id: session.learner_id, revision: 1, display_name: '小松（虚构）', age_band: null });
    if (p.endsWith('/start')) { const topics = ['age_band', 'experience', 'interests', 'help_preference', 'mini_attempt_text', 'chosen_start']; return reply({ id: 'start-fixture', revision: 1, learner_id: session.learner_id, answers: Object.fromEntries(topics.map(t => [t, { state: 'unanswered', value: null }])), completion_status: 'not_started', mini_attempt_status: 'not_attempted', recommendation: 'guided', recommendation_basis: 'insufficient_evidence', recommendation_revision: 1, recommendation_rule_version: 'rule-fixture', recommendation_source_fields: [], missing_fields: topics, skipped_fields: [], effective_start: 'guided', effective_start_source: 'conservative_fallback', saved_at: null }); }
    return fail(404, 'resource_not_found');
  });
  const page = await context.newPage(); page.setDefaultTimeout(10000); page.on('pageerror', e => errors.push(e.message));
  const button = name => page.getByRole('button', { name, exact: true });
  const visible = text => page.getByText(text, { exact: true }).first().waitFor();
  const checkedHelp = async () => { await page.getByLabel('帮助情况', { exact: true }).selectOption('none_reported'); await page.getByLabel('我确认这一步的内容和帮助情况', { exact: true }).check(); };
  const settle = async () => { await page.waitForFunction(() => !document.body.textContent.includes('正在保存并核对最新任务')); };
  const shot = name => page.screenshot({ path: path.join(out, name + '.png'), fullPage: true });
  async function fillFacts(facts) { for (const [k, v] of Object.entries(facts)) await page.getByRole('textbox', { name: labels[k], exact: true }).fill(v); }
  try {
    state.run = newRun(); await page.goto('https://p2.fixture.invalid/#/learn/run?id=run-fixture');
    await page.locator('.lp-studio-task > summary').waitFor();
    assert.equal(await page.getByLabel('找谁帮忙',{exact:true}).count(),0);
    assert.equal(state.writes.length,0);
    const rects=await page.locator('.lp-studio-steps,.lp-studio-chat,.lp-studio-preview-pane').evaluateAll(ns=>ns.map(n=>({x:n.getBoundingClientRect().x,w:n.getBoundingClientRect().width})));
    assert.ok(rects[0].x < rects[1].x && rects[1].x < rects[2].x); await shot('studio-first-desktop'); record('three-areas-no-auto-mutation-no-role-selector'); await page.locator('.lp-studio-task > summary').click(); await page.getByRole('heading',{name:'说清这张卡的要求',exact:true}).waitFor();
    await page.getByRole('textbox',{name:'邀请谁',exact:true}).fill('我自己写的未保存邀请对象');
    for (const width of [390,768]) {
      await page.setViewportSize({width,height:900});
      await page.getByRole('tab',{name:'看我的作品',exact:true}).click();
      await page.getByText('你的想法，会在这里长出来',{exact:true}).waitFor();
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      await shot('studio-preview-'+width);
      await page.getByRole('tab',{name:'和松伴聊',exact:true}).click();
      assert.equal(await page.getByRole('textbox',{name:'邀请谁',exact:true}).inputValue(),'我自己写的未保存邀请对象');
    } record('mobile-preview-switch-preserves-draft-at-two-widths');
    await page.evaluate(()=>document.documentElement.style.zoom='2');
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.evaluate(()=>document.documentElement.style.zoom='');
    await page.setViewportSize({width:1440,height:1000});
    await fillFacts(A); await button('2. 想怎样邀请').click(); await page.getByLabel('邀请目的',{exact:true}).fill('告诉同学活动安排'); await page.getByLabel('表达偏好',{exact:true}).fill('友好简短');
    await button('3. 核对与帮助').click(); for(const label of Object.values(labels)) await page.getByRole('checkbox',{name:label,exact:true}).check(); await checkedHelp();
    await button('确认我的要求').click(); await button('检查要求并进入第二关').waitFor(); assert.equal(state.run.progress[1].state,'locked'); record('grouped-requirements-explicit-confirm-does-not-auto-pass');
    await button('检查要求并进入第二关').click(); await button('保存这次工具输入').click(); await button('开始模拟生成').click(); await button('保存这张作品').waitFor();
    await page.getByRole('article',{name:'模拟工具候选 · 尚未保存 · 虚构活动'}).count();
    assert.equal(state.artifact,null); await shot('studio-candidate'); record('generated-candidate-preview-is-not-saved-work');
    await checkedHelp(); await button('保存这张作品').click(); await button('打开已保存的作品').click(); assert.equal(state.writes.filter(w=>w.p.endsWith('/readbacks')).length,0); await button('我已打开并看过这一版').click(); await button('检查保存记录并进入第三关').click();
    await page.getByLabel('我要核对的作品字段').selectOption('start_time'); await page.getByLabel('我对照的材料位置',{exact:true}).selectOption('MAT_A@0.1.0#start_time'); await page.getByLabel('我的判断',{exact:true}).selectOption('matches'); await page.getByLabel('我这样判断的理由').fill('两处开始时间都是14:00。'); await checkedHelp(); await button('保存我的自查').click();
    await page.getByRole('heading',{name:'亲手改进一处',exact:true}).waitFor(); await page.getByLabel('我想改哪里、想解决什么').fill('把邀请语写具体'); await page.getByLabel('修改邀请语').fill('带上你喜欢的故事书，一起交换故事！');
    await page.getByRole('article',{name:'我的修改草稿 · 尚未保存',exact:true}).waitFor(); assert.equal(state.artifact.current_version.version,1); assert.equal(state.artifact.current_version.content.invitation_line,'欢迎来参加活动。'); await shot('studio-edit-draft');
    await page.setViewportSize({width:390,height:844}); await page.getByRole('tab',{name:'看我的作品',exact:true}).click(); await page.getByRole('article',{name:'我的修改草稿 · 尚未保存',exact:true}).waitFor(); await page.getByRole('tab',{name:'和松伴聊',exact:true}).click(); assert.equal(await page.getByLabel('修改邀请语').inputValue(),'带上你喜欢的故事书，一起交换故事！'); record('live-draft-preview-keeps-saved-version-and-mobile-input');
    await page.setViewportSize({width:1440,height:1000}); await page.getByLabel('我把什么改成什么，为什么').fill('把参加活动改成交换故事，让同学知道要做什么。'); await checkedHelp(); await button('保存改进为新版本').click(); await page.getByRole('heading',{name:'换张材料，自己再试',exact:true}).waitFor(); assert.equal(state.artifact.current_version.version,2); assert.equal(state.artifact.check_status,'recheck_required'); record('saved-edit-new-version-requires-recheck');
    await fillFacts(B); await button('2. 我的新邀请').click(); await page.getByLabel('这次的邀请目的').fill('告诉同学纸桥活动安排'); await page.getByLabel('这次的表达偏好').fill('简短清楚'); await page.getByLabel('我的新邀请语').fill('来一起试试做纸桥吧！'); await button('3. 发现两处不同').click();
    const fields=page.getByLabel('变化的字段',{exact:true}); await fields.nth(0).selectOption('place'); await fields.nth(1).selectOption('preparation'); await page.getByLabel('第 1 处为什么要重新写').fill('地点换成星叶活动室，不能走错。'); await page.getByLabel('第 2 处为什么要重新写').fill('要带纸而不是书。'); await page.getByLabel('第 1 处材料位置').selectOption('MAT_B@0.1.0#place'); await page.getByLabel('第 2 处材料位置').selectOption('MAT_B@0.1.0#preparation'); await checkedHelp(); await button('保存换材料尝试').click();
    await page.getByLabel('回顾：我改了什么，为什么').fill('我把邀请语改得具体。'); await page.getByLabel('回顾：我怎样核对，新材料有什么不同').fill('我对照时间，新材料的地点和准备物品不同。'); await checkedHelp(); await button('保存我的复盘').click(); await button('打开已保存的作品').click(); await button('我已打开并看过这一版').click(); await button('预检已保存的记录').click(); await button('交给老师看看').waitFor(); assert.equal(state.cases.length,0); record('grouped-transfer-reflection-preflight-complete-without-auto-submit');
    state.support=true; await button('交给老师看看').click(); await visible('负责人：值班老师（虚构）'); await shot('studio-waiting-teacher'); await page.reload(); await visible('负责人：值班老师（虚构）'); record('teacher-case-and-work-restored-after-refresh');
    state.expire=true; await page.evaluate(()=>window.handle.revalidate()); await page.getByRole('heading',{name:'请家长重新认证'}).waitFor(); assert.equal(await page.locator('.lp-studio').count(),0); record('identity-loss-clears-studio');
    assert.deepEqual(errors,[]); record('no-browser-runtime-errors');
  } catch (e) { await shot('failure'); console.error(await page.locator('body').innerText()); throw e; }
  finally { fs.writeFileSync(path.join(out, 'studio-results.json'), JSON.stringify({ date: '2026-11-02', scope: 'Isolated synthetic studio UI fixture. Old P0 contract with studio_enabled configuration extension; no real backend, model or child-learning acceptance.', results, errors, mutationCount: state.writes.length, operations: [...new Set(state.calls.map(c => c.method + ' ' + c.p))] }, null, 2)); await browser.close(); }
  console.log(JSON.stringify({ passed: results.length, evidence: out }));
}
main().catch(e => { console.error(e); process.exitCode = 1; });
