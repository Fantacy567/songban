/* Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
 * Real browser with synthetic HTTP fixtures. No server, real identity, or model invocation.
 */
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const { chromium } = require('playwright'), esbuild = require('esbuild');
const root = path.resolve(__dirname, '../../..'), out = path.resolve(process.env.SONGBAN_U02_EVIDENCE || path.join(root, '../outputs/u02-workbench'));
const catalog = JSON.parse(fs.readFileSync(path.join(root, 'curriculum/ai-courses/catalog.json'), 'utf8'));
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'curriculum/ai-courses/teachers.json'), 'utf8'));
const ids = catalog.courses.map(c => c.id), results = [], errors = [], origin = 'http://127.0.0.1:43237';
const teacher = id => {
  if (state.realTeacher) { const { course_id, name, goal, opening, suggestions, sources, tools } = manifest.teachers.find(t => t.course_id === id); return { course_id, name, goal, opening, suggestions, sources, tools }; }
  return { course_id: id, name: `${id} 课程老师`, goal: '提要求、看结果、追问修改、检查保存', opening: '我们先一起试一试。想做什么都可以告诉我。', suggestions: ['帮我写一句读书会邀请', '我想换个主题'], sources: [], tools: ['text-artifact', 'creative-studio'] };
};
let state, page, browser, visit = 0;
const identity = () => ({ id: `identity-${state.child}`, mode: state.mode, actor_id: 'fixture-actor', learner_id: state.mode === 'learner' ? state.child : null, revision: 1, mode_epoch: state.epoch, scopes: ['learning'], expires_at: '2030-01-01' });
function reset(patch = {}) { state = { child: 'a', epoch: 1, mode: 'learner', enabled: true, views: {}, jobs: {}, writes: [], reads: [], conflict: false, unknown: false, async: false, failed: false, delay: 0, pollHold: 0, ...patch }; }
function view(id) { const key = state.child + ':' + id; return state.views[key] ||= { id: `session-${state.child}-${id}`, course_id: id, title: `${id} 的探索`, revision: 0, updated_at: '2026-11-04', teacher: teacher(id), capabilities: { mock: true, live: false, reason: '在线模型未配置' }, messages: [], artifact_versions: [], selected_artifact_id: null, record: null }; }
const b = name => page.getByRole('button', { name, exact: true });
const field = name => page.getByLabel(name, { exact: true });
const message = () => field('告诉老师你想试什么，也可以随时改主意');
const posts = action => state.writes.filter(r => r.path.endsWith('/' + action));
async function open(route = '#/learn/course?id=ai-tools') { await page.goto(origin + '/fixture?visit=' + (++visit) + route); if (route.includes('/course?')) await message().waitFor(); }
async function send(content = '我想写一条读书会邀请') { await message().fill(content); await b('发送给老师').click(); await page.locator('.wb-turn').last().waitFor(); await page.waitForFunction(() => document.querySelector('#wb-message')?.value === ''); }
async function check(name, action) { await action(); results.push({ name, passed: true }); console.log('PASS ' + name); }
(async () => {
  fs.mkdirSync(out, { recursive: true });
  await esbuild.build({ stdin: { resolveDir: root, loader: 'tsx', contents: `import {mount} from './frontend/learning';window.handle=mount(document.getElementById('host'),{initialRoute:location.hash,onRouteChange:r=>history.replaceState(null,'',r)});` }, bundle: true, format: 'iife', jsx: 'automatic', outfile: path.join(out, 'fixture.js'), define: { 'process.env.NODE_ENV': '"development"' } });
  browser = await chromium.launch({ headless: true, channel: 'msedge' }); page = await browser.newPage({ viewport: { width: 1440, height: 1050 } }); page.setDefaultTimeout(7000); page.on('pageerror', e => errors.push(e.message));
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), p = url.pathname, method = request.method(), body = request.postDataJSON();
    assert.equal(url.origin, origin, 'All requests are synthetic and local');
    const json = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    if (p === '/fixture') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta name="songban-platform" content="1"><meta name="songban-creative-studio" content="1"><style>body{margin:0}</style><link rel="stylesheet" href="/static/platform-shell.css"><link rel="stylesheet" href="/fixture.css"><div id="learning-prep-root"><div id="host"></div></div><script src="/fixture.js"></script>' });
    if (/^\/fixture\.(js|css)$/.test(p)) return route.fulfill({ contentType: p.endsWith('js') ? 'text/javascript' : 'text/css', body: fs.readFileSync(path.join(out, p.slice(1))) });
    if (p.startsWith('/static/')) { const file = path.join(root, p.slice(1)); return fs.existsSync(file) ? route.fulfill({ body: fs.readFileSync(file), contentType: p.endsWith('.css') ? 'text/css' : p.endsWith('.svg') ? 'image/svg+xml' : 'image/png' }) : route.fulfill({ status: 404, body: '' }); }
    if (p.endsWith('/session')) return json(identity());
    if (p.endsWith('/session-bootstrap')) return json({ csrf_token: 'fixture-csrf', browser_revision: 1 });
    if (p.endsWith('/config')) return json({ learning_enabled: state.enabled, studio_enabled: true, catalog_enabled: true, live_enabled: false, notice: '' });
    if (p === '/api/platform/v1/learning-catalog') return json(catalog);
    if (p.startsWith('/api/platform/v1/learning-catalog/')) return json(catalog.courses.find(c => c.id === p.split('/').at(-1)));
    if (p.endsWith('/home')) return json({ learner_id: state.child, run_id: null, entitlements: [], allowed_actions: [] });
    if (p === '/api/learning/v2/courses') return json({ items: [], next_cursor: null });
    const prefix = '/api/platform/v1/learning-workbench';
    if (!p.startsWith(prefix)) return json({ error: { code: 'fixture_unavailable' } }, 404);
    const target = p.slice(prefix.length); state.reads.push(target);
    if (target === '/teachers') return json({ version: '1', teachers: ids.map(teacher) });
    if (method === 'POST') { assert.equal(request.headers()['x-csrf-token'], 'fixture-csrf'); assert.ok(body.request_id); state.writes.push({ path: target, body }); }
    if (target === '/records') return json({ items: Object.values(state.views).filter(v => v.id.startsWith(`session-${state.child}-`) && v.confirmed_record?.status === 'confirmed').map(v => v.confirmed_record) });
    if (target === '/sessions') {
      if (method === 'GET') return json({ items: Object.values(state.views).filter(v => v.id.startsWith(`session-${state.child}-`)).map(v => ({ id: v.id, course_id: v.course_id, title: v.title, revision: v.revision, updated_at: v.updated_at })) });
      return json(view(body.course_id));
    }
    const [, , sessionId, action] = target.split('/'), current = Object.values(state.views).find(v => v.id === sessionId);
    assert.ok(current, target); assert.ok(current.id.startsWith(`session-${state.child}-`));
    if (method === 'GET') {
      if (state.delay) { const snapshot = structuredClone(current), delay = state.delay; state.delay = 0; await new Promise(resolve => setTimeout(resolve, delay)); return json(snapshot); }
      if (state.async && state.pollHold-- <= 0) { state.async = false; current.messages.at(-1).status = 'succeeded'; current.messages.at(-1).assistant_text = '异步回应已完成'; current.revision++; }
      return json(current);
    }
    if (state.jobs[body.request_id]) return json(state.jobs[body.request_id]);
    if (state.conflict) { state.conflict = false; current.revision++; return json({ error: { code: 'revision_conflict' } }, 409); }
    assert.equal(body.expected_revision, current.revision);
    if (state.failed) { state.failed = false; return json({ error: { code: 'bad_input' } }, 422); }
    if (action === 'messages') current.messages.push({ id: 'message-' + current.messages.length, user_text: body.content, assistant_text: state.async ? null : '先看看这份文字，再按你的想法改一处。', mode: body.mode, status: state.async ? 'pending' : 'succeeded', actual_model: null, artifact: { title: '读书会邀请', content: '<script>window.injected=true</script>\n周五来图书角分享一本书。' }, created_at: '2026-11-04' });
    if (action === 'artifacts') { const artifact = { id: 'version-' + (current.artifact_versions.length + 1), title: body.title, content: body.content, source_message_id: body.source_message_id, created_at: '2026-11-04' }; current.artifact_versions.push(artifact); current.selected_artifact_id = artifact.id; }
    if (action === 'select-artifact') current.selected_artifact_id = body.version_id;
    if (action === 'record-draft') current.record = { id: 'record-' + current.id, session_id: current.id, course_id: current.course_id, title: '一次小尝试', summary: '我向老师提要求并修改了文字。', next_step: '再换一种说法', method: 'evidence', status: 'draft', source_message_ids: current.messages.map(m => m.id), artifact_version_id: current.selected_artifact_id, updated_at: '2026-11-04' };
    if (action === 'record-confirm') current.record = { ...current.record, title: body.title, summary: body.summary, next_step: body.next_step, status: 'confirmed' };
    if (action === 'record-confirm') current.confirmed_record = structuredClone(current.record);
    current.revision++; state.jobs[body.request_id] = structuredClone(current);
    if (state.unknown) { state.unknown = false; return json({ error: { code: 'network_unknown' } }, 503); }
    return json(current);
  });
  try {
    await check('First AI entry is immediate, without interview or legacy reads', async () => {
      reset(); await open('#/learn/first'); await b('和老师试用 AI').waitFor(); assert.equal(state.writes.length, 0); assert.equal(await page.locator('textarea').count(), 0); await b('和老师试用 AI').click(); await message().waitFor(); assert.ok(page.url().endsWith('id=ai-tools')); assert.equal(state.reads.some(p => p.includes('start') || p.includes('entry')), false);
    });
    await check('All seven courses open directly into distinct teachers; tools are optional; three business entries', async () => {
      for (const id of ids) { reset(); await open('#/learn/course?id=' + id); await page.getByRole('heading', { name: `${id} 课程老师`, exact: true }).waitFor(); assert.equal(await page.locator('.cs-steps').count(), 0); assert.equal(await page.locator('.sp-primary-nav button').count(), 3); assert.equal(posts('messages').length, 0); }
      assert.equal(await page.locator('[data-platform-companion]').count(), 0); assert.equal(await page.locator('.lp-platform-sidebar').evaluate(e => e.getBoundingClientRect().width), 240);
    });
    await check('Suggestions never send; mock labels and capability controls are explicit', async () => {
      reset(); await open(); await b('帮我写一句读书会邀请').click(); assert.equal(posts('messages').length, 0); assert.equal(await field('回应方式').locator('option[value=live]').evaluate(e => e.disabled), true); await b('发送给老师').click(); await page.getByText('模拟示范 · 非实时模型', { exact: true }).waitFor(); assert.equal(posts('messages')[0].body.mode, 'mock'); assert.equal(await page.evaluate(() => window.injected), undefined);
    });
    await check('Candidate edited into immutable versions; prior version can be selected and reload restores it', async () => {
      await b('编辑这份成果').click(); await field('成果内容').fill('孩子亲手改过的邀请'); await b('保存成果版本').click(); await page.getByText('当前成果版本已保存', { exact: true }).waitFor(); await field('成果内容').fill('第二版邀请'); await b('保存成果版本').click(); await page.getByText('已保存的版本（2）', { exact: true }).click(); await b('选回版本 1').click(); await page.waitForFunction(() => document.querySelector('.wb-results textarea')?.value === '孩子亲手改过的邀请'); assert.equal(view('ai-tools').artifact_versions.length, 2); await open(); assert.equal(await field('成果内容').inputValue(), '孩子亲手改过的邀请'); assert.equal(view('ai-tools').selected_artifact_id, 'version-1');
    });
    await check('Record draft is editable, requires confirmation, appears in portfolio and restores the corresponding course', async () => {
      await b('生成探索记录草稿').click(); await field('记录标题').waitFor(); assert.equal(view('ai-tools').record.status, 'draft'); await field('这次我试了什么').fill('我把地点改成图书角，并检查了时间。'); await b('确认记录，存入作品集').click(); await page.getByText('已确认保存，可从作品集继续这次探索。', { exact: true }).waitFor(); await b('打开作品集').click(); await b('继续这次探索').waitFor(); assert.equal(await page.getByText('我把地点改成图书角，并检查了时间。', { exact: true }).count(), 1); await b('继续这次探索').click(); await message().waitFor(); assert.equal(await field('这次我试了什么').inputValue(), '我把地点改成图书角，并检查了时间。'); assert.equal(posts('record-confirm').length, 1);
    });
    await check('A new draft preserves the previously confirmed record in the portfolio', async () => {
      assert.equal(await field('这次我试了什么').isDisabled(), true); const recordId = view('ai-tools').record.id; await b('根据新尝试生成记录草稿').click(); await page.getByText('上次确认的记录仍保留在作品集', { exact: true }).waitFor(); assert.equal(view('ai-tools').record.id, recordId); await b('打开作品集').click(); await page.getByText('我把地点改成图书角，并检查了时间。', { exact: true }).waitFor(); await b('继续这次探索').click(); await message().waitFor(); assert.equal(await field('这次我试了什么').isEnabled(), true);
    });
    await check('Failed sends retain input; unknown committed result does not replay until explicit read and same-id reconciliation', async () => {
      reset(); await open(); state.failed = true; await message().fill('这次发送失败仍保留'); await b('发送给老师').click(); await page.getByRole('alert').waitFor(); assert.equal(await message().inputValue(), '这次发送失败仍保留'); state.unknown = true; await b('发送给老师').click(); await b('核对服务器结果').waitFor(); assert.equal(posts('messages').length, 2); assert.equal(await b('使用原请求编号核对操作').count(), 0); await b('核对服务器结果').click(); await b('使用原请求编号核对操作').click(); await page.waitForFunction(() => document.querySelector('#wb-message')?.value === ''); assert.equal(posts('messages').length, 3); assert.equal(posts('messages')[1].body.request_id, posts('messages')[2].body.request_id); assert.equal(view('ai-tools').messages.length, 1);
    });
    await check('Unknown worker status never resends automatically and pauses new model messages', async () => {
      reset(); await open(); await send(); view('ai-tools').messages[0].status = 'unknown'; await open(); await b('核对老师回应').waitFor(); await message().fill('先保留下一次想法'); assert.equal(await b('发送给老师').isDisabled(), true); const count = posts('messages').length; await b('核对老师回应').click(); assert.equal(posts('messages').length, count); assert.equal(await message().inputValue(), '先保留下一次想法');
    });
    await check('Paused learning restores existing sessions through GET and disables editing', async () => {
      reset(); await open(); await send(); state.enabled = false; const writes = state.writes.length; await open(); await page.locator('.wb-turn').waitFor(); assert.equal(state.writes.length, writes); assert.equal(await field('成果标题').isDisabled(), true); assert.equal(await b('发送给老师').isDisabled(), true);
    });
    await check('Revision conflicts preserve edits and require explicit acknowledgement of refreshed server revision', async () => {
      reset(); await open(); await send(); state.conflict = true; await field('成果标题').fill('我写的标题'); await field('成果内容').fill('冲突时保留的文字'); await b('保存成果版本').click(); await b('核对服务器结果').click(); await b('已核对，继续编辑').click(); assert.equal(await field('成果内容').inputValue(), '冲突时保留的文字'); await b('保存成果版本').click(); await page.getByText('当前成果版本已保存', { exact: true }).waitFor(); assert.equal(posts('artifacts').at(-1).body.expected_revision, 2);
    });
    await check('Async pending messages poll GET only and preserve ongoing result edits', async () => {
      reset(); await open(); state.async = true; state.pollHold = 1; await send(); await field('成果标题').fill('等待时自己改'); await field('成果内容').fill('这份修改不能被轮询覆盖'); await page.getByText('异步回应已完成', { exact: true }).waitFor({timeout:10000}); assert.equal(await field('成果内容').inputValue(), '这份修改不能被轮询覆盖'); assert.equal(posts('messages').length, 1); assert.ok(state.reads.filter(p => p === '/sessions/session-a-ai-tools').length);
    });
    await check('Unsaved input guards navigation and page close, while identity switch drops old private edits and messages', async () => {
      await message().fill('孩子A私密输入'); await b('返回 AI 教学大厅').last().click(); await page.getByRole('dialog').waitFor(); await b('留在这里').click(); assert.equal(await page.evaluate(() => { const event = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(event); return event.defaultPrevented; }), true); state.child = 'b'; state.epoch++; await page.evaluate(() => window.handle.revalidate()); await message().waitFor(); assert.equal(await message().inputValue(), ''); assert.equal(await field('成果内容').inputValue(), ''); assert.equal(await page.locator('.wb-turn').count(), 0);
    });
    await check('Late old-identity poll is fenced after identity boundary', async () => {
      reset(); await open(); state.async = true; state.delay = 2800; await send('孩子A的延迟回应'); await page.waitForTimeout(2000); state.child = 'b'; state.epoch++; await page.evaluate(() => window.handle.revalidate()); await message().waitFor(); await page.waitForTimeout(3000); assert.equal(await page.locator('.wb-turn').count(), 0); assert.equal(await page.getByText('孩子A的延迟回应', { exact: true }).count(), 0);
    });
    await check('Desktop results and composer fit; mobile toggles chat/results without horizontal overflow and preserves versions', async () => {
      reset(); await open(); await send(); await page.screenshot({ path: path.join(out, 'workbench-1440.png'), fullPage: true }); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true); assert.ok(await page.locator('.wb-composer').evaluate(e => e.getBoundingClientRect().bottom <= innerHeight));
      await page.setViewportSize({ width: 390, height: 844 }); await open(); assert.equal(await page.locator('.wb-chat').isVisible(), true); assert.equal(await page.locator('.wb-results').isVisible(), false); await b('成果与记录').click(); assert.equal(await page.locator('.wb-results').isVisible(), true); assert.equal(await page.locator('.wb-chat').isVisible(), false); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true); await page.screenshot({ path: path.join(out, 'workbench-results-390.png'), fullPage: true }); await b('对话').click(); assert.ok(await page.locator('.wb-composer').evaluate(e => e.getBoundingClientRect().bottom <= innerHeight - 70)); await page.screenshot({ path: path.join(out, 'workbench-chat-390.png'), fullPage: true }); await page.setViewportSize({ width: 1440, height: 1050 });
    });
    await check('Hall retains four columns and seven distinct course covers/routes', async () => {
      reset(); await open('#/learn/courses'); await b('开始这门课').first().waitFor(); assert.equal(await page.locator('.ph-course-card').count(), 7); const boxes = await Promise.all((await page.locator('.ph-stage').first().locator('.ph-course-card').all()).map(c => c.boundingBox())); assert.equal(boxes.length, 4); assert.ok(boxes.every(box => Math.abs(box.y - boxes[0].y) < 1)); await page.screenshot({ path: path.join(out, 'hall-1440.png'), fullPage: true });
    });
    await check('Real teacher copy at 390x844 leaves at least 180px of visible scrollable messages before and after a reply', async () => {
      reset({ realTeacher: true }); await page.setViewportSize({ width: 390, height: 844 }); await open();
      const sizes = async () => page.evaluate(() => {
        const messages = document.querySelector('.wb-messages'), chat = messages.getBoundingClientRect(), composer = document.querySelector('.wb-composer').getBoundingClientRect();
        const controls = [...document.querySelectorAll('.wb-composer textarea,.wb-composer select,.wb-composer button,.wb-composer summary,.wb-view-switch button,.wb-heading > button')].filter(e => e.checkVisibility());
        return { messageHeight: chat.height, visibleMessages: Math.min(chat.bottom, innerHeight - 84) - Math.max(chat.top, 0), composerHeight: composer.height, composerBottom: composer.bottom, scrollHeight: messages.scrollHeight, controls: controls.map(e => e.getBoundingClientRect().height) };
      });
      const verify = size => { assert.ok(size.messageHeight >= 180, JSON.stringify(size)); assert.ok(size.visibleMessages >= 180, JSON.stringify(size)); assert.ok(size.composerHeight <= 210, JSON.stringify(size)); assert.ok(size.composerBottom <= 760, JSON.stringify(size)); assert.ok(size.controls.every(height => height >= 44), JSON.stringify(size)); };
      const first = await sizes(); verify(first); assert.equal(await page.locator('.wb-composer .wb-suggestions').count(), 0); assert.equal(await page.locator('.wb-messages .wb-suggestions button').count(), teacher('ai-tools').suggestions.length); await page.screenshot({ path: path.join(out, 'real-teacher-mobile-first-390.png') });
      await page.locator('.wb-goal summary').click(); assert.equal(await page.locator('.wb-goal p').innerText(), teacher('ai-tools').goal); verify(await sizes()); await page.locator('.wb-goal summary').click();
      await page.locator('.wb-mode-info summary').click(); await page.getByText(/模拟示范不会调用真实模型。在线模型未配置/).waitFor(); verify(await sizes()); assert.ok(await page.locator('.wb-mode-info > p').evaluate(e => { const box=e.getBoundingClientRect(), chat=e.closest('.wb-chat').getBoundingClientRect(); return box.left>=chat.left && box.right<=chat.right; })); await page.locator('.wb-mode-info summary').click();
      await send('我想写一段介绍自己的文字，请给我一个可以改的例子。'); const replied = await sizes(); verify(replied); assert.ok(replied.scrollHeight > replied.messageHeight); await message().fill('我想把最后一句换一种说法，保留我的草稿。');
      await b('成果与记录').click(); await b('对话').click(); assert.equal(await message().inputValue(), '我想把最后一句换一种说法，保留我的草稿。'); verify(await sizes());
      await page.locator('.lp-account-menu summary').click(); await b('退出当前身份').waitFor(); verify(await sizes()); await page.locator('.lp-account-menu summary').click();
      await page.screenshot({ path: path.join(out, 'real-teacher-mobile-chat-390.png') }); fs.writeFileSync(path.join(out, 'mobile-geometry.json'), JSON.stringify({ viewport: { width: 390, height: 844 }, first, replied }, null, 2));
      await page.setViewportSize({ width: 1440, height: 1050 }); await page.screenshot({ path: path.join(out, 'real-teacher-desktop-1440.png') });
    });
    await check('Keyboard input supports line breaks without sending and conversation changes have a named polite log', async () => {
      reset(); await open(); await message().fill('我的第一行'); await message().press('Enter'); await message().pressSequentially('第二行'); assert.equal(await message().inputValue(), '我的第一行\n第二行'); assert.equal(posts('messages').length, 0); assert.equal(await page.getByRole('log', { name: '对话内容' }).getAttribute('aria-live'), 'polite'); await b('发送给老师').focus(); await page.keyboard.press('Space'); await page.locator('.wb-turn').waitFor(); assert.equal(posts('messages').length, 1);
    });
    assert.deepEqual(errors, []); fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ scope: 'Real browser + synthetic HTTP; no live model or production service', results, errors }, null, 2)); console.log(JSON.stringify({ passed: results.length, out }));
  } catch (error) { await page.screenshot({ path: path.join(out, 'failure.png'), fullPage: true }); fs.writeFileSync(path.join(out, 'failure.txt'), await page.locator('body').innerText()); throw error; }
  finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
