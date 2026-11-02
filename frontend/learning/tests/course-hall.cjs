/* W05 synthetic catalogue UI. No real services, accounts, databases or models. */
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const { chromium } = require('playwright'), esbuild = require('esbuild');
const root = path.resolve(__dirname, '../../..'), out = process.env.SONGBAN_COURSE_HALL_EVIDENCE || path.resolve(root, '../outputs/learning-experience/course-hall');
const COURSE = 'invitation-course@0.1.0';
const results = [], errors = [];
let state;
function reset(patch = {}) {
  state = { enabled: true, learning: true, entitled: true, failHome: false, failCourses: false, brokenImage: false, run: null, runCourse: COURSE, completed: false, wrongLearner: false,
    courses: [{ id: COURSE, title: '班级活动邀请卡（模拟练习）', state: 'published', revision: 1, task_cards: [], tool_cards: [], lesson_version_ids: [] }], reads: [], writes: [], requests: [], ...patch };
}
async function check(name, fn) { await fn(); results.push({ name, passed: true }); }
async function main() {
  fs.mkdirSync(out, { recursive: true });
  await esbuild.build({ stdin: { resolveDir: root, loader: 'jsx', contents: `
    import React,{useCallback,useEffect,useState} from 'react';import{createRoot}from'react-dom/client';import{CourseHallPage}from'./frontend/learning/CourseHallPage';import{ApiError}from'./frontend/learning/api';import'./frontend/learning/learning.css';
    const api={request:async(p,method='GET',b)=>{const r=await fetch('/api'+p,{method,headers:{'Content-Type':'application/json'},body:b===undefined?undefined:JSON.stringify(b)});const data=await r.json();if(!r.ok)throw new ApiError(r.status,data.error.code,'fixture');return data;}};
    window.routes=[];function Fixture(){const[c,set]=useState(null);useEffect(()=>{fetch('/config').then(r=>r.json()).then(set)},[]);const guard=useCallback(()=>{},[]);const navigate=useCallback(async route=>{window.routes.push(route);await new Promise(r=>setTimeout(r,100));return true},[]);return c?<CourseHallPage api={api} learnerId="child-fixture" config={c} setGuard={guard} navigate={navigate}/>:null}createRoot(document.getElementById('host')).render(<Fixture/>);` }, bundle: true, format: 'iife', jsx: 'automatic', outfile: path.join(out, 'fixture.js'), define: { 'process.env.NODE_ENV': '"development"' } });
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } }); page.setDefaultTimeout(5000); page.on('pageerror', e => errors.push(e.message));
  await page.route('**/*', async route => {
    const r = route.request(), p = new URL(r.url()).pathname;
    const json = (obj, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(obj) });
    state.requests.push(r.url());
    if (p === '/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><link rel="stylesheet" href="/fixture.css"><div data-learning-root class="lp-root"><div id="host"></div></div><script src="/fixture.js"></script>' });
    if (p === '/fixture.js' || p === '/fixture.css') return route.fulfill({ contentType: p.endsWith('.js') ? 'text/javascript' : 'text/css', body: fs.readFileSync(path.join(out, p.slice(1))) });
    if (p === '/config') return json({ catalog_enabled: state.enabled, learning_enabled: state.learning, studio_enabled: true, live_enabled: false });
    if (p === '/static/learning/covers/invitation-v1.svg') return state.brokenImage ? route.fulfill({ status: 404, body: '' }) : route.fulfill({ contentType: 'image/svg+xml', body: fs.readFileSync(path.join(root, p.slice(1))) });
    assert.ok(p.startsWith('/api/'), `Untrusted network ${r.url()}`);
    (r.method() === 'GET' ? state.reads : state.writes).push(p);
    if (p === '/api/courses') return state.failCourses ? json({ error: { code: 'course_unavailable' } }, 423) : json({ items: state.courses, next_cursor: null });
    if (p === '/api/learners/child-fixture/home') return state.failHome ? json({ error: { code: 'fixture_network' } }, 503) : json({ learner_id: 'child-fixture', revision: 1, run_id: state.run, progress: [], current_action: {}, entitlements: state.entitled ? [{ id: 'enrollment-fixture', learner_id: 'child-fixture', course_version_id: COURSE, status: 'active' }] : [], allowed_actions: state.entitled ? ['createRun'] : [] });
    if (p === '/api/runs/run-fixture') return json({ id: state.run, learner_id: state.wrongLearner ? 'another-child' : 'child-fixture', course_version_id: state.runCourse, current_artifact_id: state.completed ? 'artifact-fixture' : null, progress: ['clarify', 'create', 'review'].map(stage => ({ stage, state: state.completed ? 'passed' : stage === 'clarify' ? 'in_progress' : 'locked' })) });
    throw Error(`Unexpected fixture path ${p}`);
  });
  let counter = 0; const open = () => page.goto(`http://127.0.0.1:43225/?case=${++counter}`);
  const card = () => page.locator('.lp-course-card');
  const b = name => page.getByRole('button', { name, exact: true });
  try {
    await check('Published supported course has a controlled cover and no invented courses', async () => {
      reset(); state.courses.push({ ...state.courses[0], id: 'draft-course', title: '不应公开的草稿', state: 'draft' }, { ...state.courses[0], id: 'unmapped-course', title: '未接入的小游戏', state: 'published' }); state.courses[0].cover_url = 'https://untrusted.example/private-child-photo';
      await open(); await b('开始这个作品').waitFor(); assert.equal(await card().count(), 1); assert.equal(await page.getByText('不应公开的草稿', { exact: true }).count(), 0); assert.equal(await page.getByText('未接入的小游戏', { exact: true }).count(), 0);
      assert.equal(await card().locator('img').getAttribute('src'), '/static/learning/covers/invitation-v1.svg'); assert.ok((await card().locator('img').getAttribute('alt')).includes('示例')); assert.ok(!state.requests.some(r => r.includes('untrusted.example'))); assert.equal(state.writes.length, 0);
    });
    await check('Starting navigates to first-work once and never creates or generates in the hall', async () => {
      await b('开始这个作品').evaluate(e => { e.click(); e.click(); }); await page.waitForFunction(() => window.routes.length === 1); assert.deepEqual(await page.evaluate(() => window.routes), ['#/learn/first']); assert.equal(state.writes.length, 0);
    });
    await check('A saved invitation run continues its exact ID without claiming completion', async () => {
      reset({ run: 'run-fixture' }); await open(); await b('继续创作').waitFor(); assert.equal(await card().getByText('正在创作', { exact: true }).count(), 1); assert.equal(await card().getByText('已经完成', { exact: true }).count(), 0);
      await b('继续创作').click(); assert.deepEqual(await page.evaluate(() => window.routes), ['#/learn/run?id=run-fixture']); assert.equal(state.writes.length, 0);
    });
    await check('Completion comes from the exact run and opens the saved artifact', async () => {
      reset({ run: 'run-fixture', completed: true }); await open(); await b('看看我的作品').waitFor(); assert.equal(await card().getByText('已经完成', { exact: true }).count(), 1); await b('看看我的作品').click(); assert.deepEqual(await page.evaluate(() => window.routes), ['#/learn/works?id=artifact-fixture']);
    });
    await check('A different course run never supplies this course completion or start state', async () => {
      reset({ run: 'run-fixture', completed: true, runCourse: 'different-course' }); await open(); await page.getByText('先从上方打开已有作品；不同课程的进度不会混在一起。').waitFor(); assert.equal(await card().getByText('已经完成', { exact: true }).count(), 0); assert.equal(await b('开始这个作品').count(), 0);
    });
    await check('No enrollment explains preparation instead of a fake start button', async () => { reset({ entitled: false }); await open(); await b('请家长帮我准备').waitFor(); assert.equal(await b('开始这个作品').count(), 0); await b('请家长帮我准备').click(); assert.deepEqual(await page.evaluate(() => window.routes), ['#/family']); assert.equal(state.writes.length, 0); });
    await check('An empty published directory has an honest empty state', async () => { reset({ courses: [] }); await open(); await page.getByRole('heading', { name: '课程还在准备中' }).waitFor(); assert.equal(await card().count(), 0); });
    await check('Course-directory failure leaves existing work reachable', async () => { reset({ failCourses: true, run: 'run-fixture' }); await open(); await b('打开上次的作品').waitFor(); await b('重新读取课程大厅').waitFor(); await b('打开上次的作品').click(); assert.deepEqual(await page.evaluate(() => window.routes), ['#/learn/run?id=run-fixture']); });
    await check('Missing home state does not pretend enrollment or completion', async () => { reset({ failHome: true }); await open(); await b('重新读取课程大厅').waitFor(); await card().waitFor(); assert.equal(await b('开始这个作品').count(), 0); assert.equal(await b('请家长帮我准备').count(), 0); await page.getByText('读到本人记录后，才能确认从哪一步开始。').waitFor(); });
    await check('A foreign run response is never rendered as this child progress', async () => { reset({ run: 'run-fixture', completed: true, wrongLearner: true }); await open(); await b('重新读取课程大厅').waitFor(); assert.equal(await card().getByText('已经完成', { exact: true }).count(), 0); assert.equal(await b('看看我的作品').count(), 0); });
    await check('Image failure falls back to accessible course text and leaves the action usable', async () => { reset({ brokenImage: true }); await open(); await page.getByRole('img', { name: /示例封面暂时没有加载/ }).waitFor(); assert.equal(await b('开始这个作品').isEnabled(), true); });
    await check('Paused learning does not offer new operations', async () => { reset({ learning: false }); await open(); await page.getByText('学习暂时暂停', { exact: true }).waitFor(); assert.equal(await b('开始这个作品').count(), 0); });
    await check('Closed catalogue does not read catalogue or private progress', async () => { reset({ enabled: false }); await open(); await page.getByRole('heading', { name: '课程大厅还没有开放' }).waitFor(); assert.equal(state.reads.length, 0); });
    await check('Long titles, cover, keyboard details and actions fit 390/768/1440 widths', async () => {
      for (const width of [390, 768, 1440]) {
        reset(); state.courses[0].title = '班级活动邀请卡：把时间地点和你的邀请表达清楚的第一次练习'; await page.setViewportSize({ width, height: 1000 }); await open(); await b('开始这个作品').waitFor();
        await page.getByText('这节课会怎么做？', { exact: true }).focus(); await page.keyboard.press('Enter'); await page.getByText('按自己的节奏练习，完成时间因人而异。', { exact: true }).waitFor();
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)); assert.ok(await b('开始这个作品').isVisible());
        await page.screenshot({ path: path.join(out, `catalog-${width}.png`), fullPage: true });
      }
    });
    assert.deepEqual(errors, []); fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ results, errors, scope: 'Synthetic UI only; no real backend or family data' }, null, 2)); console.log(JSON.stringify({ passed: results.length, evidence: out }));
  } finally { await browser.close(); }
}
main().catch(e => { console.error(e); process.exitCode = 1; });
