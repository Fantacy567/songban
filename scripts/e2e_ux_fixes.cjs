'use strict';
// Full UI journey on scripts/ux_review_server.py only. No real SMS/model requests.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.SONGBAN_UX_URL || 'http://127.0.0.1:8901';
const folder = path.resolve(process.env.SONGBAN_UX_OUTPUT || '.browser-cache/ux-fixes-20261031/desktop');
const mobile = process.env.SONGBAN_UX_MOBILE === '1';
const suffix = process.env.SONGBAN_UX_PHONE_SUFFIX || '11';
const phoneA = '188901000' + suffix, phoneB = '188902000' + suffix;
const password = 'synthetic-ux-password';
const results = [], errors = [];
let browser, a, b, team1, team2, code1, privateSession;
fs.mkdirSync(folder, { recursive: true });
const check = async (name, run) => {
  try { await run(); results.push({ name, passed: true }); console.log('PASS ' + name); }
  catch (error) { results.push({ name, passed: false, error: error.stack }); throw error; }
  finally { fs.writeFileSync(path.join(folder, 'results.json'), JSON.stringify({ base, mobile, sms: 'fixture', model: 'fixture', results, errors }, null, 2)); }
};
const shot = (page, name) => page.screenshot({ path: path.join(folder, name + '.png'), fullPage: true });
const nav = async (page, route) => { await page.locator(`a[href="#/${route}"]:visible`).first().click(); await page.locator(`[data-route="${route}"]`).waitFor(); };
const textHas = async (page, value) => { await page.getByText(value, { exact: false }).first().waitFor(); };
async function userPage() {
  const context = await browser.newContext({ viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 }, isMobile: mobile, hasTouch: mobile, acceptDownloads: true, reducedMotion: 'reduce' });
  const page = await context.newPage(); page.setDefaultTimeout(12000);
  page.on('pageerror', error => errors.push(error.message));
  page.on('dialog', dialog => dialog.type() === 'beforeunload' ? dialog.dismiss() : dialog.accept());
  await page.goto(base + '/#/events'); await page.locator('.event-row').first().waitFor();
  return page;
}
async function register(page, phone, name) {
  await page.locator('[data-auth]').first().click(); await page.locator('[data-register]').click();
  await page.locator('#auth-phone').fill(phone); await page.locator('#send-code').click();
  await page.waitForFunction(() => /\d{6}/.test(document.querySelector('#code-notice')?.textContent || ''));
  const code = (await page.locator('#code-notice').innerText()).match(/\d{6}/)[0];
  await page.locator('#auth-code').fill(code); await page.locator('#auth-password').fill(password);
  await page.locator('#auth-name').fill(name); await page.locator('#auth-skills').fill('整理文字、核对流程');
  await page.locator('#auth-profile').fill('准备可核对的一页说明'); await page.locator('#auth-form button[type=submit]').click();
  await page.locator('#logout').waitFor();
}
async function login(page, phone) {
  await page.locator('[data-auth]').first().click(); await page.locator('#auth-phone').fill(phone);
  await page.locator('#auth-password').fill(password); await page.locator('#auth-form button[type=submit]').click();
  await page.locator('#logout').waitFor(); await page.locator('.sbw').waitFor();
}
async function send(page, value) {
  await page.getByLabel('这次想一起想清楚什么？').fill(value);
  await page.locator('.sbw-composerWrap button[type=submit]').click();
  await textHas(page, '回答已保存到本人的会话');
}
async function newSession(page) {
  const before = await page.getByLabel('本人会话历史').inputValue();
  await page.getByRole('button', { name: '＋ 新会话', exact: true }).click();
  await page.waitForFunction(previous => {
    const select = document.querySelector('[aria-label="本人会话历史"]');
    return select && select.value && select.value !== previous && !select.disabled;
  }, before);
  await page.locator('.sbw-thread[aria-busy=false]').waitFor();
}
async function personal(page) {
  await nav(page, 'work'); await page.getByRole('button', { name: '继续我的个人讨论 ↗' }).click();
  await page.waitForFunction(() => state.personal && !state.team);
  await page.getByLabel('本人会话历史').selectOption(privateSession);
  await page.getByRole('button', { name: '选择内容共享', exact: true }).first().waitFor();
}
async function shareTo(page, teamId, summary) {
  await page.getByRole('button', { name: '选择内容共享', exact: true }).first().click();
  await page.getByLabel('共享到哪个团队？').selectOption(teamId);
  await page.getByLabel('本人编辑摘要').fill(summary);
  await page.getByRole('button', { name: '预览共享内容', exact: true }).click();
  await page.getByRole('button', { name: '确认共享到团队', exact: true }).click();
  await page.getByRole('button', { name: '查看团队记录 ↗' }).click();
  await page.waitForFunction(id => state.team === id && state.page === 'library', teamId);
  await textHas(page, summary);
  await page.waitForFunction(() => document.activeElement?.id.startsWith('library-'));
}
async function complete(page, task, summary) {
  await nav(page, 'tasks');
  await page.locator(`[data-report-task="${task}"]`).click();
  const form = page.locator('#manual-report');
  await form.locator('[name=summary]').fill(summary); await form.locator('[name=status]').selectOption('reported_done');
  await form.locator('[name=evidence_text]').fill('本条正文是实际编写的体验文字成果，可逐项阅读核对。\n未制作外部软件，未向主办方提交。');
  await form.locator('button[type=submit]').click();
  const taskCard = page.locator(`#task-${task}`);
  await taskCard.getByText(summary, { exact: true }).waitFor({ state: 'attached' });
  await taskCard.getByText('查看当前成果依据', { exact: true }).click();
  await textHas(page, summary);
}
async function peerCheck(page, task) {
  await nav(page, 'tasks');
  // The route itself must fetch the other user's new report; no manual refresh.
  await page.locator(`[data-check-task="${task}"]`).click();
  await page.locator('#check-verdict').selectOption('accepted');
  await page.locator('#check-note').fill('已逐项阅读本条文字，目标、步骤和限制均存在；只认可体验文本，不认定软件已制作。');
  await page.locator('#check-form button[type=submit]').click(); await page.locator('#check-form').waitFor({ state: 'detached' });
}
(async () => {
  const marker = await fetch(base + '/api/ux-review').then(r => r.json());
  assert.equal(marker.sms, 'fixture'); assert.equal(marker.model, 'fixture');
  browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  a = await userPage(); b = await userPage();
  await check('Register via UI with explicit test SMS', async () => {
    await a.locator('.event-row').first().click(); await register(a, phoneA, '修复验收队长');
    await register(b, phoneB, '修复验收同伴');
  });
  await check('Material draft survives refresh and navigation, then saves', async () => {
    await a.getByLabel('文字或聊天记录').fill('【合成草稿】校园失物招领：发布、查找、核验；仅编写说明。');
    await a.getByLabel('原作者 / 发言者（选填）').fill('合成体验'); await a.getByLabel('材料性质').selectOption('sample');
    await a.reload(); await a.getByLabel('文字或聊天记录').waitFor();
    assert.match(await a.getByLabel('文字或聊天记录').inputValue(), /合成草稿/);
    assert.equal(await a.getByLabel('材料性质').inputValue(), 'sample');
    const attachment = { name: '合成说明.txt', mimeType: 'text/plain', buffer: Buffer.from('合成附件：只做文字流程，未制作软件。') };
    await a.locator('#material-files').setInputFiles(attachment);
    await nav(a, 'work'); await nav(a, 'events'); await a.locator('.event-row').first().click();
    assert.match(await a.getByLabel('文字或聊天记录').inputValue(), /合成草稿/);
    await textHas(a, '合成说明.txt');
    a.removeAllListeners('dialog'); a.once('dialog', dialog => dialog.accept());
    await a.reload();
    a.removeAllListeners('dialog'); a.on('dialog', dialog => dialog.type() === 'beforeunload' ? dialog.dismiss() : dialog.accept());
    await textHas(a, '附件需重新选择');
    assert.match(await a.getByLabel('文字或聊天记录').inputValue(), /合成草稿/);
    await a.locator('#material-files').setInputFiles(attachment);
    await shot(a, 'material-draft-restored'); await a.getByRole('button', { name: '保存并读取材料', exact: true }).click();
    await textHas(a, '已读取'); await a.getByRole('button', { name: '帮我整理', exact: true }).click();
    await textHas(a, '整理结果已保存');
  });
  await check('Private history uses first question and supports durable rename', async () => {
    await nav(a, 'work'); await a.getByRole('button', { name: '开始一段讨论', exact: true }).click();
    await send(a, '校园失物招领如何整理项目思路？');
    await a.waitForFunction(() => document.querySelector('[aria-label="本人会话历史"]')?.selectedOptions[0].textContent.includes('校园失物招领'));
    privateSession = await a.getByLabel('本人会话历史').inputValue();
    assert(privateSession);
    await newSession(a);
    await a.waitForFunction(() => document.querySelector('[aria-label="本人会话历史"]')?.selectedOptions[0].textContent.includes('未开始的讨论'));
    await a.getByLabel('本人会话历史').selectOption(privateSession);
    await a.getByRole('button', { name: '重命名当前会话' }).click(); await a.getByLabel('会话名称', { exact: true }).fill('认领流程和隐私范围');
    await a.getByRole('button', { name: '保存名称', exact: true }).click();
    await a.getByRole('button', { name: '保存名称', exact: true }).waitFor({ state: 'detached' }); await a.reload();
    await a.waitForFunction(() => document.querySelector('[aria-label="本人会话历史"]')?.selectedOptions[0].textContent.includes('认领流程和隐私范围'));
  });
  await check('Timeout recovery displays actual checked state, then explicit retry', async () => {
    await newSession(a);
    await a.getByLabel('这次想一起想清楚什么？').fill('[UX_TIMEOUT] 核对保存状态');
    await a.locator('.sbw-composerWrap button[type=submit]').click(); await textHas(a, '上一次请求结果尚未确定');
    await a.reload(); await a.getByRole('button', { name: '核对保存状态' }).click();
    await textHas(a, '刚刚核对'); await textHas(a, '尚未找到回答');
    await a.getByLabel('我已核对，明确发起一次新尝试').check(); await send(a, '核对后重新整理目标');
  });
  await check('Create two teams and join companion, with immediate invite guidance', async () => {
    await a.getByRole('button', { name: '创建或加入小队 ↗' }).click();
    await a.locator('#team-name').fill('完整流程验收一队'); await a.locator('#create-team button').click();
    await a.locator('.invite-line code').waitFor(); code1 = await a.locator('.invite-line code').innerText();
    team1 = await a.locator('#team-switch').inputValue(); assert.match(await a.locator('#content').innerText(), /确认方向/);
    await a.locator('#new-team').click(); await a.locator('#team-name').fill('共享目标验收二队'); await a.locator('#create-team button').click();
    await a.locator('.invite-line code').waitFor(); team2 = await a.locator('#team-switch').inputValue(); assert.notEqual(team1, team2);
    await nav(b, 'work'); await b.getByRole('button', { name: '创建或加入小队 ↗' }).click();
    await b.locator('#team-code').fill(code1); await b.locator('#join-team button').click(); await b.locator('.sbw').waitFor();
  });
  await check('Personal share navigates to each selected team and labels edited summary', async () => {
    await personal(a); await shareTo(a, team1, '人工编辑的项目说明：只做文字流程，队友逐项核对。');
    await textHas(a, '修复验收队长编辑的共享摘要'); await textHas(a, '原回复模型来源');
    await shot(a, 'shared-team-record');
    await personal(a); await newSession(a);
    await send(a, '第二团队的独立项目讨论'); await shareTo(a, team2, '第二团队专用摘要');
    await nav(a, 'work'); await a.getByRole('button', { name: '继续我的个人讨论 ↗' }).click();
    await a.getByRole('button', { name: '查看已共享记录 ↗' }).click(); await textHas(a, '查看已共享的团队记录');
    await a.locator(`[data-library-team="${team1}"]`).click(); await textHas(a, '人工编辑的项目说明');
    assert(!(await a.locator('#content').innerText()).includes('第二团队专用摘要'));
  });
  await check('Direction uses Beijing date input and truthful first-plan guidance', async () => {
    await nav(a, 'direction'); await a.locator('[name=goal]').fill('【合成验收】准备一页说明与演示讲稿，未制作软件。');
    await a.locator('[name=rules]').fill('未知，未取得主办方原文'); await a.locator('[name=rubric]').fill('未知，待确认');
    await a.locator('[name=non_goals]').fill('不声称已制作软件或正式提交'); await a.locator('[name=deadline]').fill('2026-11-07T18:00');
    await a.locator('#direction-form button[type=submit]').click(); await textHas(a, '共同方向已保存');
    await a.reload(); await a.locator('#direction-form').waitFor(); assert.equal(await a.locator('[name=deadline]').inputValue(), '2026-11-07T18:00');
    assert(!(await a.locator('#content').innerText()).includes('已有草案需要'));
    await a.getByRole('link', { name: '前往任务与统筹', exact: true }).click();
    await a.locator('#review').click(); await a.locator('#confirm-plan').click(); await a.locator('#task-T1').waitFor();
    await textHas(a, '没有前置依赖'); await shot(a, 'confirmed-tasks');
  });
  await check('Two actual text reports and peer checks update on navigation', async () => {
    await nav(b, 'members');
    await complete(a, 'T1', '【实际体验文本】目标用户：参赛新人。问题：如何协作。范围：文字流程。三步：放材料、讨论、交付检查。');
    await peerCheck(b, 'T1'); await nav(a, 'members');
    await complete(b, 'T2', '【实际讲稿文字】开场：介绍协作目标。演示：资料、讨论、检查三步。限制：仅文字未录制。分工：队长说明，同伴核对。清单：说明与讲稿。');
    await peerCheck(a, 'T2');
  });
  await check('Handoff export and retrospective complete without claiming external submission', async () => {
    await nav(a, 'delivery'); await textHas(a, '2/2');
    const checklist = a.locator('.delivery-check');
    if (await checklist.count() && !(await checklist.evaluate(el => el.open))) await checklist.locator('summary').click();
    await textHas(a, '已填写赛事要求与评分说明');
    assert(!(await a.locator('#content').innerText()).includes('已保存原文和评分依据'));
    const downloadEvent = a.waitForEvent('download'); await a.locator('#export-handoff').click(); const download = await downloadEvent;
    const file = path.join(folder, 'handoff.md'); await download.saveAs(file); assert.match(fs.readFileSync(file, 'utf8'), /实际体验文本/);
    await nav(a, 'review'); await a.locator('[name=summary]').fill('【真实操作复盘】完整走过讨论、共享、两人成果互查和导出；未正式提交。');
    await a.locator('#reflection-form button').click(); await textHas(a, '复盘已保存');
  });
  await check('Relogin shows current stage, old history, and no private-cache carryover', async () => {
    await a.locator('#logout').click();
    assert.equal(await a.evaluate(() => Object.keys(sessionStorage).filter(k => k.startsWith('songban:workbench:') || k.startsWith('songban:materials:')).length), 0);
    await login(a, phoneA); await a.locator('#team-switch').selectOption(team1); await a.locator('[aria-label="项目当前进度"]').waitFor();
    await textHas(a, '核对本次交接与正式提交要求'); await textHas(a, '2 项成果有同伴检查记录');
    await shot(a, 'resume-project-stage'); await a.getByRole('button', { name: '继续我的个人讨论 ↗' }).click();
    await a.getByLabel('本人会话历史').selectOption(privateSession); await send(a, '重登后继续原来的项目思路');
    await nav(a, 'materials'); await a.getByLabel('文字或聊天记录').fill('不得进入下一账号的私人草稿');
    await a.locator('#logout').click(); await login(a, phoneB); await nav(a, 'events'); await a.locator('.event-row').first().click();
    assert.equal(await a.getByLabel('文字或聊天记录').inputValue(), '');
    assert.equal(await a.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  });
  await check('No uncaught browser errors', async () => assert.deepEqual(errors, []));
})().catch(async error => {
  console.error(error.stack); if (a) await shot(a, 'failure-a').catch(() => {}); if (b) await shot(b, 'failure-b').catch(() => {}); process.exitCode = 1;
}).finally(async () => { if (browser) await browser.close(); });
