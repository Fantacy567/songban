/* All content and identities are explicitly fictional. In-memory transport only; no real API or model. */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const { chromium } = require('playwright'), esbuild = require('esbuild');
const root = path.resolve(__dirname, '../../../..');
const out = process.env.SONGBAN_PORTFOLIO_EVIDENCE || 'E:/松伴/outputs/platform-portfolio-h2';
const clone = value => JSON.parse(JSON.stringify(value));
const stamp = '2030-05-18T10:00:00Z', learner = 'fictional-child-only';
const textOutput = text => ({ kind: 'text', label: '虚构练习已保存内容', text, url: null });
const urlOutput = url => ({ kind: 'external_link', label: '本人提供的链接（未独立核验）', text: null, url });
function work(id, origin, title, output, overrides = {}) {
  return { id, learner_id: learner, origin, title, summary: '隔离测试中的虚构作品说明。', revision: 1,
    source_ref: { domain: origin, id: origin === 'learning' ? 'fictional-artifact' : id, version: 'fictional-v1' }, current_version: { id: `${id}-v1`, number: 1 }, actual_outputs: [output],
    cover_asset_id: null, contribution: '我修改了按钮文案；AI 帮忙给出过提示。', provenance: { kind: origin === 'learning' ? 'learning_record' : origin === 'competition' ? 'guardian_statement_learner_confirmed' : 'self_reported', ai_assistance: 'assisted', source_label: origin === 'external' ? '虚构网页工具' : '虚构练习来源' }, visibility: 'private', updated_at: stamp,
    available_actions: origin === 'learning' ? ['open_learning'] : origin === 'external' ? ['save_version'] : ['open_competition'], versions: [{ id: `${id}-v1`, number: 1, actual_outputs: [output], created_at: stamp }], ...overrides };
}
const learningWork = work('learning_fictional-artifact', 'learning', '虚构故事会邀请卡', textOutput('标题：松果班故事交换会\n时间：2030年5月18日 14:00\n地点：虚构松果活动室\n准备：带一本愿意分享的故事书\n邀请语：一起分享最想推荐的故事。'));
const externalWork = work('pw_fictional-only', 'external', '虚构校园节水小助手', urlOutput('https://example.test/fictional-water'));
const source = { project_id: 'fictional-project', name: '虚构校园创新队', source_revision: 3, available_refs: [{ ref: 'report:fictional-own', label: '本人进展（虚构）', text: '我调整了页面的按钮切换，并记录一次手机检查。', outputs: [textOutput('我调整了页面的按钮切换。')] }, { ref: 'task:1:fictional-own', label: '本人任务（不代表完成）', text: '负责交互说明；此任务安排不证明实际完成。', outputs: [textOutput('交互说明任务安排。')] }] };
const offered = { id: 'pcl_fictional-only', learner_id: learner, project_id: source.project_id, source_revision: 3, revision: 1, state: 'offered', title: '虚构比赛来源提议', summary: '管理者提出、等待孩子核对的虚构记录。', contribution: '孩子负责按钮演示；这是管理者声明，需孩子核对。', selected_refs: [source.available_refs[0].ref], sources: [source.available_refs[0]], source_label: source.name, created_at: stamp, updated_at: stamp };
function initial(overrides = {}) { const details = Object.fromEntries([learningWork, externalWork].map(w => [w.id, clone(w)])); return { works: clone([learningWork, externalWork]), details, links: [clone(offered)], sources: [clone(source)], ...overrides }; }
const results = [], unexpected = [], pageErrors = [];
let browser, page, serial = 0;
async function test(name, fn) { await fn(); results.push({ name, passed: true }); }
async function reset(data = initial(), mode = 'learner', options = {}) {
  await page.evaluate(({ data, mode, identityKey, options }) => {
    window.fixture = { data, mode, calls: [], replay: {}, ...options };
    window.openedLearning = []; window.openedCompetition = []; window.dirtyEvents = []; window.currentWorkEvents = [];
    window.mountFictionalPortfolio({ transport: window.fictionalTransport, learnerId: 'fictional-child-only', mode, identityKey,
      onOpenLearning: (...args) => window.openedLearning.push(args), onOpenCompetition: id => window.openedCompetition.push(id), onDirty: value => window.dirtyEvents.push(value), onCurrentWork: work => window.currentWorkEvents.push(work?.id || null), renderImageTools: window.fictionalImagePanel, getAssetUrl: id => '/api/platform/v1/fictional-assets/' + id });
  }, { data, mode, identityKey: `synthetic-identity-${++serial}`, options });
  if (!options.delayWorks) await page.getByRole('button', { name: '重新读取作品与来源' }).waitFor();
  if (!options.delayWorks) await page.waitForFunction(() => !document.querySelector('.pf-refresh')?.disabled);
}
async function calls(method) { return page.evaluate(method => window.fixture.calls.filter(call => !method || call.method === method), method); }
async function openExternal() { await page.getByRole('button', { name: `打开作品：${externalWork.title}`, exact: true }).click(); await page.getByRole('button', { name: '修改说明 / 保存新版本' }).waitFor(); }
async function fillExternal(overrides = {}) {
  const fields = { title: '虚构纸桥挑战说明页', summary: '展示纸桥挑战规则、材料和我调整过的按钮。', url: 'https://example.test/fictional-bridge', tool_name: '虚构网页工具', contribution: '我整理规则并修改按钮文字；AI 提供过布局建议。', ...overrides };
  for (const [key, label] of Object.entries({ title: '作品名称', summary: '这是一个什么作品？', url: '实际作品链接', tool_name: '用了哪个工具？', contribution: '我自己做了什么？哪些地方有人帮忙？' })) await page.getByLabel(label, { exact: true }).fill(fields[key]);
  await page.getByLabel('AI 帮助情况', { exact: true }).selectOption('assisted');
}
async function main() {
  fs.mkdirSync(out, { recursive: true });
  const fixtureEntry = `import React from 'react';import {createRoot} from 'react-dom/client';import {PortfolioPage} from './frontend/platform/portfolio/PortfolioPage';let root;window.fictionalImagePanel=work=>React.createElement('p',{'data-image-tools':work.id},'中央图片工具（虚构）');window.mountFictionalPortfolio=(props)=>{root ||= createRoot(document.getElementById('host'));root.render(<PortfolioPage {...props}/>);};window.unmountFictionalPortfolio=()=>{root?.unmount();root=null;};`;
  await esbuild.build({ stdin: { contents: fixtureEntry, resolveDir: root, loader: 'tsx' }, bundle: true, jsx: 'automatic', format: 'iife', outfile: path.join(out, 'portfolio-fixture.js'), define: { 'process.env.NODE_ENV': '"development"' } });
  const js = fs.readFileSync(path.join(out, 'portfolio-fixture.js')), css = fs.readFileSync(path.join(out, 'portfolio-fixture.css'));
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.route('**/*', async route => {
    const u = new URL(route.request().url());
    if (u.origin !== 'http://songban-portfolio.invalid') { unexpected.push(u.href); return route.abort(); }
    if (u.pathname === '/') return route.fulfill({ contentType: 'text/html; charset=utf-8', body: '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>虚构作品集 H2 验收</title><link rel="stylesheet" href="/portfolio.css"><style>body{margin:0;background:#faf9f6;color:#20231c;font-family:Arial,"Microsoft YaHei",sans-serif}header.fixture{padding:20px 5%;font-weight:700;border-bottom:1px solid #e4e1da}#host{padding:0 5%}</style><header class="fixture">松伴 SONGBAN · H2 隔离界面，全部为虚构资料</header><main id="host"></main><script src="/portfolio.js"></script></html>' });
    if (u.pathname === '/portfolio.js') return route.fulfill({ contentType: 'text/javascript', body: js });
    if (u.pathname === '/portfolio.css') return route.fulfill({ contentType: 'text/css', body: css });
    if (!u.pathname.startsWith('/api/platform/v1/fictional-assets/') && u.pathname !== '/favicon.ico') unexpected.push(u.href);
    return route.fulfill({ status: 404, body: '' });
  });
  page = await context.newPage(); page.on('pageerror', e => pageErrors.push(e.message));
  await page.goto('http://songban-portfolio.invalid/');
  await page.evaluate(() => {
    const copy = value => JSON.parse(JSON.stringify(value));
    const failure = (status, code) => Object.assign(new Error(code), { status, code });
    window.fictionalTransport = async (path, method = 'GET', body) => {
      const f = window.fixture, p = path.replace('/learners/fictional-child-only', '');
      const call = { path, method, ...(body === undefined ? {} : { body: copy(body) }) }; f.calls.push(call);
      if (!path.startsWith('/learners/fictional-child-only/')) throw failure(403, 'fictional_scope');
      if (method === 'GET') {
        if (p === '/works') { const value = copy({ items: f.data.works, next_cursor: null }); if (f.delayWorks) await new Promise(r => setTimeout(r, f.delayWorks)); if (f.worksError) throw failure(f.worksError, 'fictional_read_error'); return value; }
        if (p === '/competition-source-links') { if (f.linksError) throw failure(f.linksError, 'fictional_links_error'); return copy({ items: f.data.links }); }
        if (p === '/competition-sources') { if (f.mode !== 'manager') throw failure(403, 'fictional_manager_only'); return copy({ items: f.data.sources }); }
        if (p.startsWith('/works/')) { if (f.detailReadFails) { f.detailReadFails--; throw failure(503, 'fictional_detail_read_failure'); } const detail = f.data.details[decodeURIComponent(p.slice(7))]; if (!detail) throw failure(404, 'fictional_not_found'); return copy(detail); }
        throw failure(404, 'fictional_unexpected_read');
      }
      if (method !== 'POST' || !body.request_id) throw failure(422, 'fictional_invalid_write');
      const replay = f.replay[body.request_id];
      if (replay) { if (JSON.stringify(body) !== replay.body) throw failure(409, 'idempotency_conflict'); return copy(replay.result); }
      if (f.delayPost) await new Promise(r => setTimeout(r, f.delayPost));
      if (f.postConflictCount) {
        f.postConflictCount--;
        const workId = p.match(/^\/external-works\/([^/]+)\/versions$/)?.[1];
        if (workId) { const detail = f.data.details[decodeURIComponent(workId)]; detail.revision++; detail.current_version = { id: `${detail.id}-concurrent`, number: detail.revision }; detail.versions.push({ ...detail.current_version, actual_outputs: copy(detail.actual_outputs), created_at: '2030-05-19T00:00:00Z' }); f.data.works = f.data.works.map(item => item.id === detail.id ? copy(detail) : item); }
        throw failure(409, 'revision_conflict');
      }
      let result;
      if (p === '/external-works' || /^\/external-works\/[^/]+\/versions$/.test(p)) {
        if (f.mode !== 'learner') throw failure(403, 'fictional_learner_only');
        const keys = ['request_id', 'title', 'summary', 'url', 'tool_name', 'contribution', 'ai_assistance'];
        const workId = p.match(/^\/external-works\/([^/]+)\/versions$/)?.[1];
        if (workId) keys.push('expected_revision');
        if (Object.keys(body).sort().join() !== keys.sort().join()) throw failure(422, 'fictional_schema_fields');
        const old = workId ? f.data.details[decodeURIComponent(workId)] : null;
        if (old && old.revision !== body.expected_revision) throw failure(409, 'revision_conflict');
        const id = old?.id || 'pw_fictional-created', rev = old ? old.revision + 1 : 1;
        const outputs = [{ kind: 'external_link', label: '本人提供的链接（未独立核验）', text: null, url: body.url }];
        const version = { id: `${id}-v${rev}`, number: rev, actual_outputs: copy(outputs), created_at: '2030-05-20T00:00:00Z' };
        result = { id, learner_id: 'fictional-child-only', origin: 'external', title: body.title, summary: body.summary, revision: rev, source_ref: { domain: 'external', id, version: version.id }, current_version: { id: version.id, number: rev }, actual_outputs: outputs, cover_asset_id: null, contribution: body.contribution, provenance: { kind: 'self_reported', ai_assistance: body.ai_assistance, source_label: body.tool_name }, visibility: 'private', updated_at: version.created_at, available_actions: ['save_version'], versions: [...(old?.versions || []), version] };
        f.data.details[id] = copy(result); f.data.works = [copy(result), ...f.data.works.filter(w => w.id !== id)];
      } else if (p === '/competition-source-links') {
        if (f.mode !== 'manager') throw failure(403, 'fictional_manager_only');
        const keys = ['request_id', 'project_id', 'expected_source_revision', 'selected_refs', 'contribution', 'title', 'summary'];
        if (Object.keys(body).sort().join() !== keys.sort().join()) throw failure(422, 'fictional_schema_fields');
        const source = f.data.sources.find(s => s.project_id === body.project_id);
        if (source.source_revision !== body.expected_source_revision) throw failure(409, 'source_changed');
        result = { id: 'pcl_fictional-created', learner_id: 'fictional-child-only', project_id: body.project_id, source_revision: body.expected_source_revision, revision: 1, state: 'offered', title: body.title, summary: body.summary, contribution: body.contribution, selected_refs: copy(body.selected_refs), sources: copy(source.available_refs.filter(s => body.selected_refs.includes(s.ref))), source_label: source.name, created_at: '2030-05-20T00:00:00Z', updated_at: '2030-05-20T00:00:00Z' };
        f.data.links.unshift(copy(result));
      } else if (/^\/competition-source-links\/[^/]+\/decision$/.test(p)) {
        if (f.mode !== 'learner') throw failure(403, 'fictional_learner_only');
        if (Object.keys(body).sort().join() !== ['request_id', 'expected_revision', 'decision'].sort().join()) throw failure(422, 'fictional_schema_fields');
        const id = decodeURIComponent(p.split('/')[2]), link = f.data.links.find(item => item.id === id);
        if (link.revision !== body.expected_revision) throw failure(409, 'revision_conflict');
        link.state = { accept: 'accepted', decline: 'declined', revoke: 'revoked' }[body.decision]; link.revision++; result = copy(link);
        const workId = 'competition_' + link.id;
        f.data.works = f.data.works.filter(work => work.id !== workId);
        if (link.state === 'accepted') {
          const outputs = link.sources.flatMap(source => source.outputs), version = { id: `${link.id}:${link.revision}`, number: link.revision, actual_outputs: copy(outputs), created_at: link.updated_at };
          const work = { id: workId, learner_id: link.learner_id, origin: 'competition', title: link.title, summary: link.summary, revision: link.revision, source_ref: { domain: 'competition', id: link.project_id, version: String(link.source_revision) }, current_version: { id: version.id, number: version.number }, actual_outputs: outputs, cover_asset_id: null, contribution: link.contribution, provenance: { kind: 'guardian_statement_learner_confirmed', ai_assistance: 'unknown', source_label: link.source_label }, visibility: 'private', updated_at: link.updated_at, available_actions: ['open_competition'], versions: [version] };
          f.data.works.unshift(copy(work)); f.data.details[workId] = copy(work);
        } else delete f.data.details[workId];
      } else throw failure(404, 'fictional_unexpected_write');
      f.replay[body.request_id] = { body: JSON.stringify(body), result: copy(result) };
      if (f.postUnknownCount) { f.postUnknownCount--; throw failure(0, 'fictional_response_lost'); }
      return copy(result);
    };
  });

  await test('Private borderless gallery presents actual text and separately labeled illustration', async () => {
    await reset();
    assert.equal(await page.locator('[data-work-id]').count(), 2);
    assert.equal(await page.getByText('已保存文字 · 排版预览').count(), 1);
    assert.equal(await page.getByText('松伴示意封面 · 打开链接看实际作品').count(), 1);
    assert.match(await page.locator('.pf-text-preview').textContent(), /松果班故事交换会/);
    const decoration = await page.locator('.pf-work').first().evaluate(e => [getComputedStyle(e).borderWidth, getComputedStyle(e).boxShadow]);
    assert.deepEqual(decoration, ['0px', 'none']);
    assert.equal((await calls('POST')).length, 0);
    assert.equal(await page.getByRole('button', { name: /公开/ }).count(), 0);
  });
  await test('Details expose real saved output, provenance and original learning artifact route', async () => {
    await reset();
    await page.getByRole('button', { name: `打开作品：${learningWork.title}`, exact: true }).click();
    await page.getByRole('button', { name: '回到这节课' }).waitFor();
    assert.match(await page.locator('.pf-text-output').first().textContent(), /虚构松果活动室/);
    assert.match(await page.locator('.pf-provenance').textContent(), /学习检查/);
    await page.getByRole('button', { name: '回到这节课' }).click();
    assert.deepEqual(await page.evaluate(() => window.openedLearning), [[undefined, 'fictional-artifact']]);
  });
  await test('External work submit uses schema fields only and waits for explicit action', async () => {
    await reset(initial({ links: [] }));
    await page.getByRole('button', { name: '添加工具作品 ＋' }).click();
    await fillExternal();
    assert.equal((await calls('POST')).length, 0);
    assert.equal(await page.evaluate(() => window.dirtyEvents.at(-1)), true);
    await page.getByRole('button', { name: '保存到私人作品集' }).click();
    await page.getByRole('button', { name: '修改说明 / 保存新版本' }).waitFor();
    const written = await calls('POST'); assert.equal(written.length, 1);
    assert.match(written[0].body.request_id, /^[A-Za-z0-9_.:@-]+$/);
    assert.equal(written[0].body.ai_assistance, 'assisted');
    assert.equal(written[0].body.contribution, '我整理规则并修改按钮文字；AI 提供过布局建议。');
    assert.equal(await page.evaluate(() => window.fixture.data.details['pw_fictional-created'].visibility), 'private');
    assert.equal(await page.evaluate(() => window.dirtyEvents.at(-1)), false);
  });
  await test('Unsafe external link is rejected locally and never fetched', async () => {
    await reset();
    await page.getByRole('button', { name: '添加工具作品 ＋' }).click();
    await fillExternal({ url: 'https://fictional-user:fictional-password@example.test/item' });
    await page.getByRole('button', { name: '保存到私人作品集' }).click();
    assert.equal((await calls('POST')).length, 0);
    assert.equal(await page.getByText('请填写不含账号密码的 HTTP 或 HTTPS 作品链接。').count(), 1);
  });
  await test('Lost save response preserves same request body and manually reconciles without duplicate creation', async () => {
    await reset(initial({ links: [] }), 'learner', { postUnknownCount: 1 });
    await page.getByRole('button', { name: '添加工具作品 ＋' }).click(); await fillExternal();
    await page.getByRole('button', { name: '保存到私人作品集' }).click();
    await page.getByRole('button', { name: '核对刚才的保存' }).waitFor();
    assert.equal(await page.getByLabel('作品名称', { exact: true }).isDisabled(), true);
    await page.waitForTimeout(120); assert.equal((await calls('POST')).length, 1);
    assert.equal(await page.evaluate(() => window.dirtyEvents.at(-1)), true);
    await page.getByRole('button', { name: '核对刚才的保存' }).click();
    await page.getByRole('button', { name: '修改说明 / 保存新版本' }).waitFor();
    const written = await calls('POST'); assert.equal(written.length, 2); assert.deepEqual(written[0].body, written[1].body);
    assert.equal(await page.evaluate(() => window.fixture.data.works.filter(w => w.id === 'pw_fictional-created').length), 1);
  });
  await test('New external version keeps prior output readable and exposes current-only editing', async () => {
    await reset(); await openExternal(); await page.getByRole('button', { name: '修改说明 / 保存新版本' }).click();
    await fillExternal({ url: 'https://example.test/fictional-water-v2' });
    await page.getByRole('button', { name: '保存为私人新版本' }).click();
    await page.getByLabel('查看哪个版本？', { exact: true }).waitFor();
    assert.equal((await calls('POST'))[0].body.expected_revision, 1);
    await page.getByLabel('查看哪个版本？', { exact: true }).selectOption(`${externalWork.id}-v1`);
    assert.equal(await page.locator('.pf-out-link').first().getAttribute('href'), 'https://example.test/fictional-water');
    assert.equal(await page.getByRole('button', { name: '修改说明 / 保存新版本' }).count(), 0);
    await page.getByLabel('查看哪个版本？', { exact: true }).selectOption(`${externalWork.id}-v2`);
    assert.equal(await page.locator('.pf-out-link').first().getAttribute('href'), 'https://example.test/fictional-water-v2');
  });
  await test('Version conflict reads latest, retains draft and requires explicit revision adoption before saving', async () => {
    await reset(initial(), 'learner', { postConflictCount: 1 }); await openExternal();
    await page.getByRole('button', { name: '修改说明 / 保存新版本' }).click(); await fillExternal({ title: '冲突后仍保留的虚构草稿' });
    await page.getByRole('button', { name: '保存为私人新版本' }).click();
    await page.getByRole('button', { name: '使用当前版本号，保留我的输入' }).waitFor();
    assert.equal(await page.getByLabel('作品名称', { exact: true }).inputValue(), '冲突后仍保留的虚构草稿');
    assert.equal(await page.getByRole('button', { name: '保存为私人新版本' }).isDisabled(), true);
    assert.ok((await calls('GET')).filter(call => call.path.endsWith('/works/' + externalWork.id)).length >= 2);
    await page.getByRole('button', { name: '使用当前版本号，保留我的输入' }).click();
    await page.getByRole('button', { name: '保存为私人新版本' }).click(); await page.getByLabel('查看哪个版本？', { exact: true }).waitFor();
    const written = await calls('POST'); assert.equal(written[1].body.expected_revision, 2); assert.notEqual(written[0].body.request_id, written[1].body.request_id);
  });
  await test('Manager explicitly reads only current-account source candidates and offers without auto-accept', async () => {
    await reset(initial({ links: [] }), 'manager');
    assert.equal(await page.getByRole('button', { name: '添加工具作品 ＋' }).count(), 0);
    assert.equal((await calls('GET')).filter(call => call.path.endsWith('/competition-sources')).length, 0);
    await page.getByRole('button', { name: '读取当前账号可提出的来源' }).click();
    await page.getByRole('button', { name: '选择来源并写贡献' }).click();
    await page.getByRole('checkbox', { name: /本人进展（虚构）/ }).check();
    await page.getByLabel('给这份经历起个名称', { exact: true }).fill('虚构比赛中的按钮演示');
    await page.getByLabel('这份经历包含什么？', { exact: true }).fill('只提出当前账号有权访问的本人进展。');
    await page.getByLabel('孩子具体做了哪部分？帮助情况是什么？', { exact: true }).fill('据我观察孩子修改按钮文字，需孩子核对。');
    assert.equal((await calls('POST')).length, 0);
    await page.getByRole('button', { name: '提出给孩子核对' }).click();
    await page.getByText('已提出来源，等孩子核对；还没有作为孩子作品收录。').waitFor();
    const written = await calls('POST'); assert.equal(written.length, 1); assert.equal(written[0].body.expected_source_revision, 3); assert.deepEqual(written[0].body.selected_refs, ['report:fictional-own']);
    assert.equal(await page.evaluate(() => window.fixture.data.links[0].state), 'offered');
    assert.equal(await page.getByRole('button', { name: '这是我的经历，确认收录' }).count(), 0);
    assert.equal(await page.locator('select').count(), 0, 'No guessed-child selector');
  });
  await test('Learner sees source original and can accept then revoke without changing competition data', async () => {
    await reset();
    await page.getByText('查看来源原文与产物', { exact: true }).click();
    assert.equal(await page.getByText(source.available_refs[0].text, { exact: true }).count(), 1);
    await page.getByRole('button', { name: '这是我的经历，确认收录' }).click();
    await page.getByText('孩子已确认收录', { exact: true }).waitFor();
    await page.getByRole('button', { name: '打开作品：' + offered.title, exact: true }).click();
    await page.getByRole('button', { name: '回到原比赛' }).waitFor();
    await page.getByRole('button', { name: '回到原比赛' }).click();
    assert.deepEqual(await page.evaluate(() => window.openedCompetition), [source.project_id]);
    await page.getByRole('button', { name: '撤回这份来源' }).click();
    await page.getByText('已撤回收录', { exact: true }).waitFor();
    await page.waitForFunction(() => window.fixture.data.links[0].state === 'revoked');
    assert.equal(await page.locator('.pf-detail').count(), 0);
    assert.equal(await page.locator('[data-work-id="competition_' + offered.id + '"]').count(), 0);
    assert.deepEqual(await page.evaluate(() => window.fixture.data.sources), [source]);
    assert.deepEqual((await calls('POST')).map(call => call.body.decision), ['accept', 'revoke']);
  });
  await test('Learner decline does not create an accepted work', async () => {
    await reset(); await page.getByRole('button', { name: '不是 / 暂不收录' }).click();
    await page.getByText('孩子未接受', { exact: true }).waitFor();
    assert.equal(await page.locator('[data-work-id]').count(), 2);
    assert.equal((await calls('POST'))[0].body.decision, 'decline');
  });
  await test('Cover failure and unsafe links preserve readable work without external embeds', async () => {
    const broken = work('pw_broken-image', 'external', '虚构封面缺失作品', urlOutput('javascript:alert(1)'), { cover_asset_id: 'fictional-missing' });
    await reset(initial({ works: [broken], details: { [broken.id]: broken }, links: [] }));
    await page.getByText('封面暂未加载，作品仍保留。').waitFor();
    await page.getByRole('button', { name: '打开作品：' + broken.title, exact: true }).click();
    await page.getByText('这个链接暂时无法安全打开，仍保留作品说明。').waitFor();
    assert.equal(await page.locator('iframe,embed,object').count(), 0);
    assert.equal(await page.locator('.pf-out-link').count(), 0);
  });
  await test('Foreign learner projection is suppressed and authorization error clears private gallery', async () => {
    await reset(initial({ works: [{ ...learningWork, learner_id: 'different-fictional-child', title: '不应显示的其他身份资料' }], links: [] }));
    assert.equal(await page.locator('[data-work-id]').count(), 0);
    assert.equal(await page.getByText('不应显示的其他身份资料').count(), 0);
    await reset(initial(), 'learner', { worksError: 403, linksError: 403 });
    assert.equal(await page.locator('[data-work-id]').count(), 0);
    assert.equal(await page.locator('.pf-detail').count(), 0);
  });
  await test('Identity change discards dirty drafts and ignores prior late responses', async () => {
    await reset(); await page.getByRole('button', { name: '添加工具作品 ＋' }).click(); await fillExternal({ title: '旧身份的未保存草稿' });
    await reset(initial({ works: [], links: [], details: {} }));
    assert.equal(await page.locator('form').count(), 0); assert.equal(await page.getByText('旧身份的未保存草稿').count(), 0);
    await reset(initial({ works: [{ ...learningWork, title: '旧身份的迟到作品' }], links: [] }), 'learner', { delayWorks: 250 });
    await reset(initial({ works: [], links: [], details: {} }));
    await page.waitForTimeout(300);
    assert.equal(await page.getByText('旧身份的迟到作品').count(), 0);
    assert.equal(await page.locator('[data-work-id]').count(), 0);
  });
  await test('Rapid submit dispatches one operation and no private draft is stored in browser storage', async () => {
    await reset(initial({ links: [] }), 'learner', { delayPost: 150 });
    await page.getByRole('button', { name: '添加工具作品 ＋' }).click(); await fillExternal();
    await page.getByRole('button', { name: '保存到私人作品集' }).evaluate(e => { e.click(); e.click(); });
    await page.getByRole('button', { name: '修改说明 / 保存新版本' }).waitFor();
    assert.equal((await calls('POST')).length, 1);
    assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
  });
  await test('Current-work context clears on close and image tools render only in learner details', async () => {
    await reset(); await openExternal();
    assert.equal(await page.evaluate(() => window.currentWorkEvents.at(-1)), externalWork.id);
    assert.equal(await page.locator('[data-image-tools]').count(), 1);
    await page.getByRole('button', { name: '返回我的作品集' }).click();
    assert.equal(await page.evaluate(() => window.currentWorkEvents.at(-1)), null);
    await reset(initial(), 'manager');
    await page.getByRole('button', { name: `打开作品：${externalWork.title}`, exact: true }).click();
    await page.getByLabel('查看哪个版本？', { exact: true }).waitFor();
    assert.equal(await page.locator('[data-image-tools]').count(), 0);
    assert.equal(await page.getByRole('button', { name: '修改说明 / 保存新版本' }).count(), 0);
  });
  await test('390/768/1440 layouts, keyboard and enlarged narrow container remain usable', async () => {
    for (const width of [390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 }); await reset();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${width}px gallery overflow`);
      const workButton = page.getByRole('button', { name: `打开作品：${learningWork.title}`, exact: true });
      await page.keyboard.press('Tab'); await workButton.focus(); assert.notEqual(await workButton.evaluate(e => getComputedStyle(e).outlineStyle), 'none');
      await page.screenshot({ path: path.join(out, `portfolio-${width}.png`), fullPage: true });
      await page.keyboard.press('Enter'); await page.getByRole('button', { name: '回到这节课' }).waitFor();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${width}px detail overflow`);
      await page.screenshot({ path: path.join(out, `detail-${width}.png`), fullPage: true });
      await reset(); await page.getByRole('button', { name: '添加工具作品 ＋' }).click();
      assert.ok(await page.getByLabel('作品名称', { exact: true }).evaluate(e => parseFloat(getComputedStyle(e).fontSize) >= 16));
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${width}px form overflow`);
      await page.screenshot({ path: path.join(out, `editor-${width}.png`), fullPage: true });
    }
    await page.setViewportSize({ width: 768, height: 1000 }); await page.emulateMedia({ reducedMotion: 'reduce' }); await reset();
    await page.evaluate(() => document.body.style.zoom = '2');
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    const positions = await page.locator('[data-work-id]').evaluateAll(es => es.map(e => e.getBoundingClientRect().y));
    assert.ok(positions[1] > positions[0] + 100);
    await page.evaluate(() => document.body.style.zoom = '');
  });
  await page.evaluate(() => window.unmountFictionalPortfolio());
  assert.deepEqual(unexpected, []); assert.deepEqual(pageErrors, []);
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ mode: 'isolated_synthetic_transport', fakeIdentitiesOnly: true, realApiCalls: 0, modelCalls: 0, dbWrites: 0, cases: results.length, results, unexpected, pageErrors }, null, 2));
  console.log(`PASS ${results.length} portfolio scenarios; evidence: ${out}`);
}
main().catch(error => { fs.mkdirSync(out, { recursive: true }); fs.writeFileSync(path.join(out, 'failure.json'), JSON.stringify({ results, unexpected, pageErrors, error: error.stack }, null, 2)); console.error(error); process.exitCode = 1; }).finally(async () => { if (browser) await browser.close(); });
