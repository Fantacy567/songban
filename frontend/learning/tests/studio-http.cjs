/* Actual app/SQLite, synthetic preview only. No API interception or real model calls.
 * Start scripts/serve_learning_preview.py with a fresh output directory first.
 * Family relationships, consent, enrollment and staff assignment are synthetic fixture setup;
 * child work, reviewer feedback and report publication below are actual UI operations.
 */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../../..');
const metadataPath = path.resolve(process.env.SONGBAN_STUDIO_METADATA || path.join(root, '../outputs/learning-experience/preview/preview-metadata.json'));
const out = path.resolve(process.env.SONGBAN_STUDIO_HTTP_EVIDENCE || path.join(root, '../outputs/learning-experience/studio-http'));
const metadata = JSON.parse(fs.readFileSync(metadataPath, 'utf8').replace(/^\uFEFF/, ''));
assert.equal(metadata.synthetic, true, 'This test requires explicit synthetic preview metadata');
assert.equal(metadata.scope, 'synthetic-only-no-real-providers');
const origin = process.env.SONGBAN_STUDIO_ORIGIN || metadata.origin;
const parsed = new URL(origin);
assert.ok(['127.0.0.1', 'localhost'].includes(parsed.hostname) && parsed.protocol === 'http:');
assert.ok(!['8894', '8895'].includes(parsed.port), 'Never target existing account/demo services');
assert.equal(origin, metadata.origin, 'Origin must match the fixture metadata');
for (const key of ['manager_account', 'staff_account', 'password', 'learner_id']) assert.ok(metadata[key], `Missing synthetic ${key}`);
const factsA = { event_name: '松果班故事交换会', audience: '松果班同学', date: '2030-05-18', start_time: '14:00', end_time: '15:00', place: '松果活动室', preparation: '带一本愿意分享的故事书' };
const factsB = { event_name: '星叶班纸桥挑战', audience: '星叶班同学', date: '2030-05-25', start_time: '10:00', end_time: '11:00', place: '星叶活动室', preparation: '带两张废旧A4纸' };
const labels = { event_name: '活动名称', audience: '邀请谁', date: '日期', start_time: '开始时间', end_time: '结束时间', place: '地点', preparation: '准备物品' };

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(process.env.SONGBAN_BROWSER_CHANNEL === 'chromium' ? {} : { channel: process.env.SONGBAN_BROWSER_CHANNEL || 'msedge' }) });
  const childContext = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  const staffContext = await browser.newContext(), parentContext = await browser.newContext();
  const page = await childContext.newPage(), staff = await staffContext.newPage(), parent = await parentContext.newPage();
  const results = [], errors = [];
  for (const p of [page, staff, parent]) { p.setDefaultTimeout(20000); p.on('pageerror', e => errors.push(e.message)); }
  const button = name => page.getByRole('button', { name, exact: true });
  const heading = name => page.getByRole('heading', { name, exact: true });
  const sb = name => staff.getByRole('button', { name, exact: true });
  const record = name => { results.push({ name, passed: true }); console.log('PASS ' + name); };
  const settle = () => page.waitForFunction(() => !document.querySelector('[aria-busy="true"]') && !document.body.textContent.includes('正在保存并核对最新任务…'));
  const shot = name => page.screenshot({ path: path.join(out, name + '.png'), fullPage: true });
  async function read(context, suffix) { const response = await context.request.get(origin + '/api/learning/v2' + suffix); assert.equal(response.status(), 200, `${suffix} must remain readable`); return response.json(); }
  async function login(p, account, route) {
    await p.goto(origin + '/learning-prep' + route);
    await p.getByLabel('已有账号', { exact: true }).fill(account);
    await p.getByLabel('密码', { exact: true }).fill(metadata.password);
    await p.getByRole('button', { name: '重新认证并进入管理', exact: true }).click();
  }
  async function task() { const panel = page.locator('.lp-studio-task'); await panel.waitFor(); if (!(await panel.getAttribute('open')) && !(await panel.evaluate(e => e.open))) await panel.locator(':scope > summary').click(); }
  async function fillFacts(facts) { for (const [key, value] of Object.entries(facts)) await page.getByRole('textbox', { name: labels[key], exact: true }).fill(value); }
  async function help() { await page.getByLabel('帮助情况', { exact: true }).selectOption('none_reported'); await page.getByLabel('我确认这一步的内容和帮助情况', { exact: true }).check(); }
  let runId = null, artifactId = null;
  try {
    const config = await read(childContext, '/config');
    assert.equal(config.studio_enabled, true); assert.equal(config.mock_enabled, true); assert.equal(config.live_enabled, false);
    assert.equal(config.reports_enabled, true); assert.equal(config.publication_enabled, true);
    await login(page, metadata.manager_account, '#/learn/first');
    await page.locator('.lp-entry-transfer > summary').click();
    await page.getByRole('checkbox', { name: '想做的事', exact: true }).check();
    await page.getByRole('checkbox', { name: '已有经历', exact: true }).check();
    await page.getByRole('checkbox', { name: /^我确认这份访谈描述的是/ }).check();
    await button('提供给孩子确认').click(); await page.getByText('摘要已保存，等待孩子本人确认。', { exact: true }).waitFor();
    assert.equal((await read(childContext, `/learners/${metadata.learner_id}/entry`)).status, 'offered');
    record('manager-explicit-subject-mapping-still-requires-child-acceptance');
    await button('进入孩子学习模式').click(); await button('确认进入').click();
    // A supplied prior interview is offered for explicit confirmation, never silently imported.
    await page.waitForFunction(() => ['这是我的想法，继续', '开始我的第一个作品'].some(t => [...document.querySelectorAll('button')].some(b => b.textContent === t)));
    if (await button('这是我的想法，继续').count()) await button('这是我的想法，继续').click();
    await button('开始我的第一个作品').click(); await page.locator('.lp-studio').waitFor();
    runId = new URLSearchParams(page.url().split('?')[1]).get('id'); assert.ok(runId);
    const home = await read(childContext, `/learners/${metadata.learner_id}/home`); assert.equal(home.run_id, runId);
    const start = await read(childContext, `/learners/${metadata.learner_id}/start`);
    assert.equal(start.answers.mini_attempt_text.state, 'unanswered', 'Opening the studio must not fabricate questionnaire evidence');
    assert.equal(await page.getByLabel('找谁帮忙', { exact: true }).count(), 0);
    await shot('first-work'); record('first-entry-no-second-questionnaire-no-fake-mini-attempt');

    const question = '我想让同学一眼看懂邀请卡，先要核对什么？';
    await page.getByLabel('想问松伴什么', { exact: true }).fill(question); await button('发送，看看本步提示').click();
    await page.locator('.lp-message-user').getByText(question, { exact: true }).waitFor();
    const helps = await read(childContext, `/runs/${encodeURIComponent(runId)}/help`);
    assert.equal(helps.items.at(-1).question, question); assert.equal(helps.items.at(-1).mode, 'static');
    await page.reload(); await page.locator('.lp-message-user').getByText(question, { exact: true }).waitFor();
    record('static-help-question-and-response-persist-real-backend');

    await task(); await heading('说清这张卡的要求').waitFor();
    await page.getByRole('textbox', { name: '邀请谁', exact: true }).fill('还没保存的邀请对象');
    for (const width of [390, 768]) {
      await page.setViewportSize({ width, height: 900 });
      await page.getByRole('tab', { name: '看我的作品', exact: true }).click();
      await page.getByText('你的想法，会在这里长出来', { exact: true }).waitFor();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)); await shot('preview-' + width);
      await page.getByRole('tab', { name: '和松伴聊', exact: true }).click();
      assert.equal(await page.getByRole('textbox', { name: '邀请谁', exact: true }).inputValue(), '还没保存的邀请对象');
    }
    await page.setViewportSize({ width: 1440, height: 1000 }); record('actual-host-mobile-tabs-preserve-unsaved-input');
    await fillFacts(factsA); await button('2. 想怎样邀请').click();
    await page.getByLabel('邀请目的', { exact: true }).fill('邀请同学分享自己喜欢的故事。'); await page.getByLabel('表达偏好', { exact: true }).fill('友好、简短、清楚');
    await button('3. 核对与帮助').click(); for (const label of Object.values(labels)) await page.getByRole('checkbox', { name: label, exact: true }).check();
    await help(); await button('保存要求草稿').click(); await settle(); await page.reload(); await task();
    assert.equal(await page.getByRole('textbox', { name: '邀请谁', exact: true }).inputValue(), factsA.audience);
    await button('确认我的要求').click(); await button('检查要求并进入第二关').waitFor();
    assert.equal((await read(childContext, `/runs/${runId}`)).progress[1].state, 'locked');
    await button('检查要求并进入第二关').click(); await heading('操作工具，留下作品').waitFor(); record('grouped-requirements-save-refresh-confirm-explicit-advance');

    await button('保存这次工具输入').click(); await button('开始模拟生成').click(); await button('保存这张作品').waitFor();
    let run = await read(childContext, `/runs/${runId}`); assert.equal(run.current_artifact_id, null);
    const model = await read(childContext, `/model-runs/${run.active_model_run_id}`); assert.equal(model.mode, 'mock');
    await shot('generated-candidate'); await help(); await button('保存这张作品').click(); await button('打开已保存的作品').click();
    await button('我已打开并看过这一版').click(); await button('检查保存记录并进入第三关').click(); await heading('先做一次自己的检查').waitFor();
    run = await read(childContext, `/runs/${runId}`); artifactId = run.current_artifact_id;
    const original = await read(childContext, `/artifacts/${artifactId}`); record('explicit-mock-candidate-save-open-confirm-no-auto-pass');
    await page.getByLabel('我要核对的作品字段').selectOption('start_time'); await page.getByLabel('我对照的材料位置', { exact: true }).selectOption('MAT_A@0.1.0#start_time');
    await page.getByLabel('我的判断', { exact: true }).selectOption('matches'); await page.getByLabel('我这样判断的理由').fill('资料和邀请卡都写14:00开始，所以这一项相同。');
    await help(); await button('保存我的自查').click(); await heading('亲手改进一处').waitFor();
    await page.getByLabel('我想改哪里、想解决什么').fill('让邀请语更清楚，知道来做什么'); await page.getByLabel('修改邀请语').fill('带上喜欢的故事书，和同学一起分享你发现的有趣故事吧！');
    await page.getByRole('article', { name: '我的修改草稿 · 尚未保存', exact: true }).waitFor();
    assert.equal((await read(childContext, `/artifacts/${artifactId}`)).current_version.id, original.current_version.id);
    await page.getByLabel('我把什么改成什么，为什么').fill('我把欢迎参加改为带书分享故事，让同学知道活动内容。'); await help(); await button('保存改进为新版本').click();
    await heading('换张材料，自己再试').waitFor();
    const edited = await read(childContext, `/artifacts/${artifactId}`); assert.equal(edited.current_version.version, 2); assert.equal(edited.check_status, 'recheck_required');
    const oldVersion = await read(childContext, `/artifacts/${artifactId}/versions/${original.current_version.id}`); assert.deepEqual(oldVersion.artifact_version.content, original.current_version.content);
    record('self-check-edit-preview-new-version-old-version-retained');

    assert.equal(await page.getByRole('textbox', { name: '邀请谁', exact: true }).inputValue(), '');
    await fillFacts(factsB); await button('2. 我的新邀请').click(); await page.getByLabel('这次的邀请目的').fill('邀请同学一起搭纸桥'); await page.getByLabel('这次的表达偏好').fill('简短清楚'); await page.getByLabel('我的新邀请语').fill('带上旧A4纸，和同学一起挑战纸桥吧！');
    await button('3. 发现两处不同').click(); await page.getByLabel('变化的字段', { exact: true }).nth(0).selectOption('place'); await page.getByLabel('变化的字段', { exact: true }).nth(1).selectOption('preparation');
    await page.getByLabel('第 1 处为什么要重新写').fill('活动室变成星叶，不能再写松果。'); await page.getByLabel('第 2 处为什么要重新写').fill('搭纸桥要准备纸张，不能再带故事书。');
    await page.getByLabel('第 1 处材料位置').selectOption('MAT_B@0.1.0#place'); await page.getByLabel('第 2 处材料位置').selectOption('MAT_B@0.1.0#preparation'); await help(); await button('保存换材料尝试').click();
    await heading('说说你的判断和改进').waitFor(); await page.getByLabel('回顾：我改了什么，为什么').fill('我把邀请语改得更具体，别人能看懂要分享故事。');
    await page.getByLabel('回顾：我怎样核对，新材料有什么不同').fill('我核对了开始时间；新材料地点和准备物品都变了。生成只是候选，保存后要重新打开才能找到作品。');
    await help(); await button('保存我的复盘').click(); await button('打开已保存的作品').click(); await button('我已打开并看过这一版').click(); await settle();
    await button('预检已保存的记录').click(); await button('交给老师看看').waitFor();
    assert.equal((await read(childContext, `/runs/${runId}`)).progress[2].state, 'in_progress');
    await button('交给老师看看').click(); await heading('作品已交老师，等待反馈').waitFor(); await page.reload(); await task(); await heading('作品已交老师，等待反馈').waitFor();
    record('transfer-reflection-preflight-explicit-review-and-refresh');

    await login(staff, metadata.staff_account, '#/learning-admin');
    await staff.getByRole('button', { name: /学习作品复核 · 待认领/ }).click(); await sb('认领这项复核').click();
    await staff.getByLabel('给孩子的具体反馈', { exact: true }).fill('仅核对合成测试的来源、修改、迁移和复盘；不代表真人学习效果判断。'); await staff.getByLabel('人工处理结论', { exact: true }).selectOption('passed');
    for (const i of [1, 2, 3, 4]) { await staff.getByLabel(`M${i} 判断`, { exact: true }).selectOption('supported'); await staff.getByLabel(`M${i} 依据说明`, { exact: true }).fill('对照本次合成作品、本人说明、修改和换材料尝试。'); }
    for (const box of await staff.getByRole('group', { name: '本次反馈引用的材料', exact: true }).getByRole('checkbox').all()) await box.check();
    await sb('保存人工反馈').click(); await staff.getByText('学习作品复核 · 已完成', { exact: false }).first().waitFor();
    await button('重新读取当前任务').click(); await heading('这次练习已完成').waitFor(); record('staff-ui-four-findings-advance-synthetic-child');

    await button('整理一份新报告').click(); await heading('请核对事实').waitFor(); await page.getByLabel('我已经核对这些事实，需要改正的地方已提交异议', { exact: true }).check();
    await button('请老师复核这份报告').click(); await heading('已送报告复核').waitFor();
    await login(parent, metadata.manager_account, '#/family'); await parent.getByText('目前还没有已发布的报告。', { exact: true }).waitFor(); record('mock-report-child-confirmed-parent-cannot-see-draft');
    await staff.reload(); await staff.getByRole('button', { name: /学习报告复核 · 待认领/ }).click(); await sb('认领这项复核').click();
    await staff.getByLabel('给孩子的具体反馈', { exact: true }).fill('已核对模拟模式与全部引用，只报告这次合成练习事实。'); await sb('确认本版本复核通过').click(); await sb('发布已批准的这一版给家长').waitFor();
    await parent.getByRole('button', { name: '重新读取报告', exact: true }).click(); await parent.getByText('目前还没有已发布的报告。', { exact: true }).waitFor();
    await sb('发布已批准的这一版给家长').click(); await staff.getByRole('heading', { name: '已发布给家长', exact: true }).waitFor();
    await parent.getByRole('button', { name: '重新读取报告', exact: true }).click(); await parent.getByRole('button', { name: /查看报告 · 已发布给家长/ }).click(); await parent.getByRole('heading', { name: '已发布给家长', exact: true }).waitFor();
    assert.equal(await parent.getByLabel('观察 1', { exact: true }).count(), 0); record('review-approval-separate-publication-parent-readonly');
    for (const width of [390, 768, 1440]) { await parent.setViewportSize({ width, height: 1000 }); assert.ok(await parent.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)); await parent.screenshot({ path: path.join(out, `report-${width}.png`), fullPage: true }); }
    await parent.setViewportSize({ width: 720, height: 600 }); await parent.evaluate(() => document.documentElement.style.zoom = '2'); assert.ok(await parent.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)); record('published-report-three-widths-and-200-percent');
    assert.deepEqual(errors, []); record('no-browser-runtime-errors');
  } catch (error) {
    for (const [name, p] of [['child', page], ['staff', staff], ['parent', parent]]) {
      await p.screenshot({ path: path.join(out, `failure-${name}.png`), fullPage: true }).catch(() => {});
      fs.writeFileSync(path.join(out, `failure-${name}.txt`), await p.locator('body').innerText().catch(() => ''));
    }
    throw error;
  } finally {
    fs.writeFileSync(path.join(out, 'studio-http-results.json'), JSON.stringify({ scope: 'Actual app/SQLite synthetic fixture, no API interception. UI operations for learning and review. Mock generation, static teaching, synthetic staff feedback; no real model, real family or teaching effectiveness acceptance.', origin, runId, artifactId, results, errors }, null, 2));
    await browser.close();
  }
  console.log(JSON.stringify({ passed: results.length, evidence: out }));
})().catch(error => { console.error(error); process.exitCode = 1; });
