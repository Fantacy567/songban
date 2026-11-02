/* Targeted engineering accessibility checks; not an actual phone IME/screen-reader certification. */
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const { chromium } = require('playwright'), esbuild = require('esbuild');
const root = path.resolve(__dirname, '../../..'), out = process.env.SONGBAN_ACCESSIBILITY_EVIDENCE || path.resolve(root, '../outputs/learning-experience/accessibility');
const results = [], errors = [], readings = [];
const COURSE = 'invitation-course@0.1.0', MAT = 'MAT_A@0.1.0';
let state;
const facts = { event_name: '虚构故事交换会', audience: '松果班同学', date: '2030-05-18', start_time: '14:00', end_time: '15:00', place: '松果活动室', preparation: '带一本故事书' };
const course = { id: COURSE, revision: 1, title: '班级活动邀请卡（模拟练习）', state: 'published', lesson_version_ids: ['lesson-fixture'], task_cards: [{ id: 'S1.1', version: '1', stage: 'clarify', goal: '读读资料，找出邀请谁、何时、在哪里。', instructions: [], material_version_ids: [MAT], tool_card_ids: [], rubric_version_id: 'rubric-fixture', help_levels: ['找一行', '试一步', '看看局部例子'] }], tool_cards: [] };
function reset() { state = { revision: 1, helps: [], writes: [], models: {}, failCourses: false, brokenImage: false }; }
function run() { return { id: 'run-fixture', revision: state.revision, learner_id: 'child-fixture', enrollment_id: 'enrollment-fixture', course_version_id: COURSE, progress: ['clarify', 'create', 'review'].map((stage, i) => ({ stage, state: i ? 'locked' : 'in_progress', lesson_version_id: 'lesson-fixture', check_id: null })), current_action: { label: '读读资料，先表达一个想法。' }, current_requirements_ref: null, current_attempt_ref: null, current_transfer_attempt_ref: null, current_artifact_id: null, current_self_check_ref: null, current_reflection_ref: null, active_model_run_id: null, allowed_actions: ['help', 'askHuman', 'saveRequirements', 'checkArtifact'] }; }
async function check(name, fn) { try { await fn(); results.push({ name, passed: true }); } catch (e) { results.push({ name, passed: false, error: String(e.stack || e) }); } }
async function main() {
  fs.mkdirSync(out, { recursive: true });
  await esbuild.build({ stdin: { resolveDir: root, loader: 'jsx', contents: `
    import React,{useCallback}from'react';import{createRoot}from'react-dom/client';import{RunPage}from'./frontend/learning/RunPage';import{CourseHallPage}from'./frontend/learning/CourseHallPage';import{ApiError}from'./frontend/learning/api';import'./frontend/learning/learning.css';
    const api={request:async(p,method='GET',body)=>{const response=await fetch('/api'+p,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const d=await response.json();if(!response.ok)throw new ApiError(response.status,d.error.code,'fixture');return d;},snapshot:()=>({session:null})};
    function Fixture(){const setGuard=useCallback(()=>{},[]),navigate=useCallback(async r=>{window.routes.push(r);return true},[]),canLeave=useCallback(async()=>true,[]);const props={api,learnerId:'child-fixture',config:{learning_enabled:true,studio_enabled:true,catalog_enabled:true,live_enabled:true},setGuard,navigate};return new URLSearchParams(location.search).get('view')==='catalog'?<CourseHallPage {...props}/>:<RunPage {...props} id="run-fixture" review={false} canLeave={canLeave}/>};window.routes=[];createRoot(document.getElementById('host')).render(<Fixture/>);` }, bundle: true, format: 'iife', jsx: 'automatic', outfile: path.join(out, 'fixture.js'), define: { 'process.env.NODE_ENV': '"development"' } });
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }); page.setDefaultTimeout(5000); page.on('pageerror', e => errors.push(e.message));
  await page.route('**/*', async route => {
    const request = route.request(), p = decodeURIComponent(new URL(request.url()).pathname);
    const json = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    if (p === '/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>松伴隔离可访问性验证</title><link rel="stylesheet" href="/fixture.css"></head><body style="margin:0"><main data-learning-root class="lp-root lp-studio-page"><h1>松伴学习</h1><div id="host"></div></main></body></html>' });
    if (p === '/fixture.js' || p === '/fixture.css') return route.fulfill({ contentType: p.endsWith('.js') ? 'text/javascript' : 'text/css', body: fs.readFileSync(path.join(out, p.slice(1))) });
    if (p === '/static/design/pine-mascot.png') return route.fulfill({ contentType: 'image/png', body: fs.readFileSync(path.join(root, p.slice(1))) });
    if (p === '/static/learning/covers/invitation-v1.svg') return state.brokenImage ? route.fulfill({ status: 404, body: '' }) : route.fulfill({ contentType: 'image/svg+xml', body: fs.readFileSync(path.join(root, p.slice(1))) });
    assert.ok(p.startsWith('/api/'), `Unexpected network ${p}`);
    const method = request.method(), b = request.postDataJSON();
    if (method !== 'GET') state.writes.push({ path: p, body: b });
    if (p === '/api/runs/run-fixture') return json(run());
    if (p === '/api/courses') return state.failCourses ? json({ error: { code: 'course_unavailable' } }, 503) : json({ items: [course], next_cursor: null });
    if (p === '/api/courses/' + COURSE) return json(course);
    if (p.includes('/materials/')) return json({ id: 'MAT_A', version: '0.1.0', notice: '虚构活动资料。', facts, source_locators: Object.keys(facts).map(key => `${MAT}#${key}`) });
    if (p === '/api/learners/child-fixture/home') return json({ learner_id: 'child-fixture', revision: 1, run_id: null, progress: [], entitlements: [{ id: 'enrollment-fixture', learner_id: 'child-fixture', course_version_id: COURSE, status: 'active' }], allowed_actions: ['createRun'] });
    if (p === '/api/cases') return json({ items: [], next_cursor: null });
    if (p === '/api/runs/run-fixture/help') {
      if (method === 'GET') return json({ items: state.helps, next_cursor: null });
      assert.equal(b.expected_revision, state.revision);
      const id = `help-${state.helps.length + 1}`, model = b.mode === 'live' ? `model-${id}` : null;
      const h = { id, revision: 1, run_id: 'run-fixture', role_id: b.role_id, help_level: b.help_level, question: b.question, mode: b.mode, text: model ? null : '先找资料里的地点，再想想怎样告诉同学。', model_run_id: model, parent_revision: ++state.revision, task_id: 'S1.1', task_card_version: '1', prompt_version: 'fixture', sources: [], actions: [] };
      if (model) state.models[model] = { id: model, help_event_id: id, status: 'succeeded', visibility: 'normal', actual_model: 'fixture-only', output_text: JSON.stringify({ text: '你可以先读出地点，再试着把它放在邀请语附近。' }) };
      state.helps.push(h); return json(h);
    }
    if (p.startsWith('/api/model-runs/')) return json(state.models[p.split('/').pop()]);
    throw Error(`Unimplemented fixture request ${method} ${p}`);
  });
  let opened = 0;
  async function open(view = 'studio') { await page.goto(`http://127.0.0.1:43229/?view=${view}&case=${++opened}`); await page.addScriptTag({ url: '/fixture.js' }); await page.getByRole('heading', { name: view === 'catalog' ? '下一个小作品，从这里开始。' : '和松伴聊', exact: true }).waitFor(); }
  async function keyboardReachAll() {
    const targets = await page.evaluate(() => {
      const nodes = [...document.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,a[href],[tabindex="0"]')].filter(e => e.checkVisibility() && e.tabIndex >= 0);
      nodes.forEach((e, i) => e.setAttribute('data-a11y-control', String(i))); document.body.tabIndex = -1; document.body.focus(); return nodes.map(e => e.getAttribute('data-a11y-control'));
    });
    const reached = new Set();
    for (let i = 0; i < targets.length + 3; i++) { await page.keyboard.press('Tab'); const id = await page.evaluate(() => document.activeElement?.getAttribute('data-a11y-control')); if (id) reached.add(id); }
    assert.deepEqual([...reached].sort(), [...targets].sort()); return targets.length;
  }
  async function semanticAudit() {
    const problems = await page.evaluate(() => {
      const visible = e => e.checkVisibility(); const problems = [];
      const ids = [...document.querySelectorAll('[id]')].map(e => e.id); for (const id of new Set(ids)) if (ids.filter(v => v === id).length > 1) problems.push('duplicate id ' + id);
      for (const e of document.querySelectorAll('[aria-labelledby],[aria-describedby],[aria-controls]')) for (const attr of ['aria-labelledby', 'aria-describedby', 'aria-controls']) for (const id of (e.getAttribute(attr) || '').split(/\s+/).filter(Boolean)) if (!document.getElementById(id)) problems.push('missing ' + attr + ' ' + id);
      for (const e of document.querySelectorAll('button,input,select,textarea')) if (visible(e)) { const name = e.getAttribute('aria-label') || (e.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join('') || (e.labels ? [...e.labels].map(l => l.textContent).join('') : '') || (e.tagName === 'BUTTON' ? e.textContent : ''); if (!name.trim()) problems.push('unnamed ' + e.outerHTML.slice(0, 100)); }
      for (const e of document.querySelectorAll('img')) if (!e.hasAttribute('alt')) problems.push('image missing alt');
      return problems;
    }); assert.deepEqual(problems, []);
  }
  try {
    await check('Studio control names, image alternatives and ID references are valid', async () => { reset(); await open(); await semanticAudit(); const ax = await page.locator('main').ariaSnapshot(); fs.writeFileSync(path.join(out, 'studio-aria.txt'), ax); assert.match(ax, /region "和松伴聊"|tabpanel "和松伴聊"/); assert.match(ax, /textbox "想问松伴什么"/); });
    await check('Every visible enabled studio control is reachable using Tab', async () => { readings.push({ scenario: 'studio keyboard targets', count: await keyboardReachAll() }); });
    await check('Keyboard focus has a visible outline', async () => { await page.getByRole('button', { name: '给我一点提示', exact: true }).focus(); const focus = await page.evaluate(() => { const s = getComputedStyle(document.activeElement); return { style: s.outlineStyle, width: parseFloat(s.outlineWidth) }; }); assert.notEqual(focus.style, 'none'); assert.ok(focus.width >= 2); });
    await check('Current task details and grouped fields remain keyboard usable', async () => {
      await page.locator('.lp-studio-task > summary').focus(); await page.keyboard.press('Enter'); await page.getByRole('textbox', { name: '活动名称', exact: true }).waitFor();
      await page.getByRole('textbox', { name: '活动名称', exact: true }).fill('虚构中文活动'); await page.getByRole('button', { name: '接着：想怎样邀请', exact: true }).focus(); await page.keyboard.press('Enter'); await page.getByLabel('邀请目的', { exact: true }).waitFor();
      await page.getByRole('button', { name: '看前一小步', exact: true }).focus(); await page.keyboard.press('Enter'); assert.equal(await page.getByRole('textbox', { name: '活动名称', exact: true }).inputValue(), '虚构中文活动'); await semanticAudit();
      await page.locator('.lp-studio-task > summary').focus(); await page.keyboard.press('Enter');
    });
    await check('Simulated Chinese composition and plain Enter do not submit a chat', async () => {
      const input = page.getByLabel('想问松伴什么', { exact: true }); await input.focus(); await input.dispatchEvent('compositionstart', { data: '' }); await input.fill('我想做一张邀请卡'); await input.dispatchEvent('compositionupdate', { data: '邀请卡' });
      await input.dispatchEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 229, which: 229, isComposing: true }); await input.dispatchEvent('compositionend', { data: '邀请卡' });
      await page.keyboard.press('Enter'); await page.keyboard.insertText('地点怎么写才清楚'); assert.equal(state.writes.length, 0); assert.equal(await input.inputValue(), '我想做一张邀请卡\n地点怎么写才清楚');
      await page.getByRole('button', { name: '发送，看看本步提示', exact: true }).focus(); await page.keyboard.press('Space'); await page.getByText('先找资料里的地点，再想想怎样告诉同学。', { exact: true }).waitFor(); assert.equal(state.writes.length, 1); assert.equal(state.writes[0].body.question, '我想做一张邀请卡\n地点怎么写才清楚');
    });
    await check('Asynchronous conversation output has a named polite log', async () => { const log = page.getByRole('log', { name: '与松伴的对话更新', exact: true }); await log.waitFor(); assert.equal(await log.getAttribute('aria-live'), 'polite'); assert.equal(await log.getAttribute('aria-relevant'), 'additions text'); assert.equal(await log.getByRole('list', { name: '与松伴的对话', exact: true }).count(), 1); });
    await check('Phone tabs expose controlled panels and work with arrows/Home/End', async () => {
      await page.setViewportSize({ width: 390, height: 844 }); const chat = page.getByRole('tab', { name: '和松伴聊', exact: true }), preview = page.getByRole('tab', { name: '看我的作品', exact: true }); await chat.focus();
      await page.getByLabel('想问松伴什么', { exact: true }).fill('切换后保留这段草稿'); await chat.focus(); await page.keyboard.press('ArrowRight'); assert.equal(await preview.getAttribute('aria-selected'), 'true'); assert.equal(await preview.evaluate(e => e === document.activeElement), true);
      const panelId = await preview.getAttribute('aria-controls'); const panel = page.locator('#' + panelId); assert.equal(await panel.getAttribute('role'), 'tabpanel'); assert.equal(await panel.getAttribute('aria-labelledby'), await preview.getAttribute('id')); assert.ok(await panel.isVisible()); assert.ok(!(await page.locator('#lp-studio-pane-chat').isVisible()));
      await page.keyboard.press('Home'); assert.equal(await chat.getAttribute('aria-selected'), 'true'); assert.equal(await page.getByLabel('想问松伴什么', { exact: true }).inputValue(), '切换后保留这段草稿'); await page.keyboard.press('End'); assert.equal(await preview.getAttribute('aria-selected'), 'true'); await page.keyboard.press('ArrowLeft'); assert.equal(await chat.getAttribute('aria-selected'), 'true'); await semanticAudit();
    });
    await check('Reduced-motion mode leaves keyboard chat and preview controls usable', async () => {
      await page.emulateMedia({ reducedMotion: 'reduce' }); assert.equal(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches), true);
      const movement = await page.locator('.lp-companion').evaluate(e => { const s = getComputedStyle(e); return { animation: s.animationName, transition: s.transitionDuration, scroll: s.scrollBehavior }; }); assert.equal(movement.animation, 'none'); assert.equal(movement.transition, '0s'); assert.equal(movement.scroll, 'auto'); readings.push(movement);
      await page.getByRole('tab', { name: '看我的作品', exact: true }).focus(); await page.keyboard.press('Space'); assert.ok(await page.getByRole('heading', { name: '看我的作品', exact: true }).isVisible()); await page.getByRole('tab', { name: '和松伴聊', exact: true }).focus(); await page.keyboard.press('Space'); assert.ok(await page.getByLabel('想问松伴什么', { exact: true }).isVisible());
    });
    await check('200% CSS magnification and narrow-viewport reflow preserve inputs and actions', async () => {
      await page.setViewportSize({ width: 768, height: 1100 }); await page.evaluate(() => document.body.style.zoom = '2');
      await page.getByLabel('想问松伴什么', { exact: true }).fill('放大后的中文草稿'); await page.getByRole('button', { name: '发送，看看本步提示', exact: true }).scrollIntoViewIfNeeded(); assert.ok(await page.getByRole('button', { name: '发送，看看本步提示', exact: true }).isVisible()); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: path.join(out, 'studio-css-200.png'), fullPage: true }); await page.evaluate(() => document.body.style.zoom = '1'); await page.setViewportSize({ width: 390, height: 844 }); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    });
    await check('Course catalogue names, image alternatives and all controls are keyboard reachable', async () => { reset(); await page.setViewportSize({ width: 1440, height: 1000 }); await open('catalog'); await page.getByRole('button', { name: '开始这个作品', exact: true }).waitFor(); await semanticAudit(); readings.push({ scenario: 'catalog keyboard targets', count: await keyboardReachAll() }); await page.getByText('这节课会怎么做？', { exact: true }).focus(); await page.keyboard.press('Space'); await page.getByText('按自己的节奏练习，完成时间因人而异。', { exact: true }).waitFor(); });
    await check('Catalogue at 200% with a broken image retains a named fallback and start action', async () => { reset(); state.brokenImage = true; await page.setViewportSize({ width: 768, height: 1100 }); await open('catalog'); await page.evaluate(() => document.body.style.zoom = '2'); await page.getByRole('img', { name: /示例封面暂时没有加载/ }).waitFor(); await semanticAudit(); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)); await page.getByRole('button', { name: '开始这个作品', exact: true }).focus(); await page.keyboard.press('Enter'); assert.deepEqual(await page.evaluate(() => window.routes), ['#/learn/first']); await page.screenshot({ path: path.join(out, 'catalog-css-200.png'), fullPage: true }); });
    await check('Catalogue failures expose an alert and reachable recovery control', async () => { reset(); state.failCourses = true; await open('catalog'); await page.getByRole('alert').waitFor(); await page.getByRole('button', { name: '重新读取课程大厅', exact: true }).focus(); state.failCourses = false; await page.keyboard.press('Enter'); await page.getByRole('button', { name: '开始这个作品', exact: true }).waitFor(); assert.equal(await page.getByRole('alert').count(), 0); });
  } finally { await browser.close(); }
  const failed = results.filter(r => !r.passed); fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ results, errors, readings, limits: ['DOM and accessibility-tree semantics are checked, not an actual screen-reader session.', 'Composition events are simulated; real phone IME has not been tested.', '200% is CSS magnification plus narrow reflow, not a native browser-zoom certification.', 'No new dependencies or comprehensive automated accessibility engine used.'] }, null, 2)); console.log(JSON.stringify({ passed: results.length - failed.length, failed, errors, evidence: out }, null, 2)); if (failed.length || errors.length) process.exitCode = 1;
}
reset(); main().catch(e => { console.error(e); process.exitCode = 1; });
