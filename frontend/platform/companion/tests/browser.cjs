/* Component fixtures only. No HTTP server, real user, database or provider. */
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const assert = require('node:assert/strict');
const esbuild = require('esbuild');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../../../..');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'songban-companion-ui-'));
const bundle = path.join(temporary, 'fixture.js');
const results = [];
let browser;
const fixture = `
import {mountCompanion} from ${JSON.stringify(path.join(root, 'frontend/platform/companion/index.tsx').replaceAll('\\', '/'))};
const conversations=new Map(); let serial=0;
window.sent=0;window.actions=[];window.adapters=[];window.behavior='normal';window.identity='child-a';window.holdInitialRead=true;window.dirty=false;
const capabilities={static_available:true,mock_available:true,live_available:false,notice:'准备好的本地指引，不是实时AI回复。'};
window.enableLive=()=>{capabilities.live_available=true;};window.liveReads=0;
const transport={
 async open(body){if(window.holdInitialRead)await new Promise(resolve=>{window.releaseInitialRead=()=>{window.holdInitialRead=false;resolve();};});const key=window.identity+JSON.stringify(body.context);if(!conversations.has(key))conversations.set(key,{id:'chat-'+(++serial),revision:1,context:body.context,adapter:body.context.domain==='learning'?{kind:'learning_run',run_id:body.context.resource_id}:null,capabilities,messages:[],has_earlier:false});return structuredClone(conversations.get(key));},
 async read(id){return structuredClone([...conversations.values()].find(c=>c.id===id));},
 async readMessage(cid,mid){const chat=[...conversations.values()].find(c=>c.id===cid);const turn=chat.messages.find(t=>t.id===mid);if(turn.mode==='live'&&['pending','running'].includes(turn.status)){window.liveReads++;turn.status=window.liveReads>1?'succeeded':'running';turn.text=turn.status==='succeeded'?'隔离协议回应，先试一小步':null;turn.actual_model=turn.status==='succeeded'?'fixture-only-model':null;turn.parent_revision=++chat.revision;}return structuredClone(turn);},
 async send(cid,body){window.sent++;const chat=[...conversations.values()].find(c=>c.id===cid);const unknown=window.behavior==='unknown',live=body.mode==='live';const turn={id:'turn-'+window.sent,request_id:body.request_id,conversation_id:cid,question:body.question,text:unknown||live?null:'先选一张课程卡，再试眼前的一小步。',role_id:'guide',mode:body.mode,status:unknown?'unknown':live?'pending':'succeeded',prompt_version:'fixture',actual_model:null,sources:[{source_id:'ai',source_version:'1',source_domain:'platform_guide',nature:'system_record'}],actions:unknown?[]:[{kind:'open_course_hall',label:'看看课程',resource_id:null},{kind:'write_vote',label:'不得显示的业务动作',resource_id:null}],created_at:'2030-01-01T00:00:00Z',parent_revision:++chat.revision};chat.messages.push(turn);if(window.behavior==='network')throw new Error('synthetic response loss');return structuredClone(turn);}
};
let props={identityKey:window.identity,context:{domain:'hall',resource_id:'ai'},transport,onAction:a=>window.actions.push(a),onLearningAdapter:a=>window.adapters.push(a),onDirty:value=>{window.dirty=value;}};
window.update=(patch)=>{props={...props,...patch};if(patch.identityKey)window.identity=patch.identityKey;window.handle.update(props);};
window.handle=mountCompanion(document.getElementById('host'),props);
window.remount=()=>{window.handle=mountCompanion(document.getElementById('host'),props);};
`;
async function record(name, run) { await run(); results.push({ name, passed: true }); console.log('PASS ' + name); }
(async () => {
  try {
    await esbuild.build({ stdin: { contents: fixture, resolveDir: root, loader: 'jsx' }, bundle: true, jsx: 'automatic', format: 'iife', outfile: bundle, logLevel: 'silent' });
    browser = await chromium.launch({ headless: true, channel: process.env.SONGBAN_BROWSER_CHANNEL || 'msedge' });
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on('pageerror', e => { errors.push(e.message); console.error('BROWSER ' + e.message); });
    await page.route('http://**/*', route => route.abort());
    await page.route('https://**/*', route => route.abort());
    await page.route('http://127.0.0.1/component-fixture', route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><meta charset="utf-8"><div id="host"></div>' }));
    await page.goto('http://127.0.0.1/component-fixture');
    await page.addStyleTag({ path: path.join(temporary, 'fixture.css') });
    await page.addScriptTag({ path: bundle });
    await page.getByRole('button', { name: '松伴 · 陪我走一步', exact: true }).click();
    const input = page.getByRole('textbox', { name: '想问松伴什么', exact: true });
    const send = page.getByRole('button', { name: '发送，看看提示', exact: true });
    await record('initial-delayed-read-without-input-does-not-block-navigation', async () => {
      await page.waitForFunction(() => typeof window.releaseInitialRead === 'function');
      assert.equal(await input.isDisabled(), true, 'The initial read is still pending');
      assert.equal(await page.evaluate(() => window.dirty), false, 'A read is not an unsaved edit');
      assert.equal(await page.evaluate(() => !window.dirty), true, 'The host leave guard may allow navigation');
      await page.evaluate(() => window.releaseInitialRead());
      await page.waitForFunction(() => !document.querySelector('textarea')?.disabled);
    });
    await record('static-truthful-label-and-explicit-send', async () => {
      await input.fill('<script>window.injection=true</script>'); await send.click();
      await page.getByText('先选一张课程卡，再试眼前的一小步。', { exact: true }).waitFor();
      assert.equal(await page.evaluate(() => window.sent), 1);
      assert.equal(await page.evaluate(() => window.injection), undefined);
      await page.getByText('本地指引 · 不是实时AI回复', { exact: true }).waitFor();
    });
    await record('only-whitelisted-navigation-actions', async () => {
      assert.equal(await page.getByText('不得显示的业务动作', { exact: true }).count(), 0);
      await page.getByRole('button', { name: '看看课程', exact: true }).click();
      assert.equal(await page.evaluate(() => window.actions[0].kind), 'open_course_hall');
    });
    await record('draft-retained-only-within-identity-and-context', async () => {
      await input.fill('这个草稿还没有发送');
      await page.evaluate(() => window.update({ context: { domain: 'hall', resource_id: 'hackathon' } }));
      await page.waitForFunction(() => document.querySelector('textarea')?.value === '');
      await page.evaluate(() => window.update({ context: { domain: 'hall', resource_id: 'ai' } }));
      await page.waitForFunction(() => document.querySelector('textarea')?.value === '这个草稿还没有发送');
    });
    await record('lost-response-query-original-without-mutation-replay', async () => {
      await page.evaluate(() => { window.behavior = 'network'; }); await send.click();
      await page.getByRole('button', { name: '核对原回应', exact: true }).waitFor();
      assert.equal(await input.isDisabled(), true);
      assert.equal(await page.evaluate(() => window.dirty), true, 'An unresolved send still protects input');
      await page.getByRole('button', { name: '核对原回应', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('textarea')?.value === '');
      assert.equal(await page.evaluate(() => window.sent), 2);
    });
    await record('new-identity-clears-old-private-history-and-draft', async () => {
      await input.fill('第一位孩子的未发送私聊');
      await page.evaluate(() => window.update({ identityKey: 'child-b' }));
      await page.getByRole('button', { name: '松伴 · 陪我走一步', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('textarea')?.value === '');
      assert.equal(await page.getByText('第一位孩子的未发送私聊', { exact: true }).count(), 0);
      assert.equal(await page.locator('.sb-companion-turn').count(), 0);
    });
    await record('unknown-preserves-input-and-does-not-resend', async () => {
      await page.evaluate(() => { window.behavior = 'unknown'; });
      await input.fill('这次结果未知'); await send.click();
      await page.getByRole('button', { name: '核对原回应', exact: true }).click();
      await page.getByText('原回应仍待核对，不会自动重新发送。', { exact: true }).waitFor();
      assert.equal(await input.inputValue(), '这次结果未知');
      assert.equal(await input.isDisabled(), true);
      assert.equal(await page.evaluate(() => window.sent), 3);
    });
    await record('unknown-recovered-from-durable-history-after-remount', async () => {
      await page.evaluate(() => window.remount());
      await page.getByRole('button', { name: '松伴 · 陪我走一步', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('textarea')?.value === '这次结果未知');
      assert.equal(await input.isDisabled(), true);
      assert.equal(await page.evaluate(() => window.sent), 3);
    });
    await record('learning-hides-platform-dialog-and-returns-adapter', async () => {
      await page.evaluate(() => window.update({ context: { domain: 'learning', resource_id: 'authorized-run' } }));
      await page.waitForFunction(() => window.adapters.some(a => a.run_id === 'authorized-run'));
      assert.equal(await page.locator('.sb-companion').count(), 0);
      assert.equal(await page.evaluate(() => window.sent), 3);
    });
    await record('singleton-mount-and-mobile-layout', async () => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.evaluate(() => window.update({ identityKey: 'child-c', context: { domain: 'hall', resource_id: 'ai' } }));
      await page.getByRole('button', { name: '松伴 · 陪我走一步', exact: true }).click();
      await input.waitFor();
      assert.equal(await page.locator('.sb-companion').count(), 1);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    });
    await record('live-capability-explicit-send-polls-only-original-message', async () => {
      await page.evaluate(() => { window.behavior='normal';window.enableLive();window.update({context:{domain:'hall',resource_id:'hackathon'}}); });
      await page.getByLabel('这次怎样提示', {exact:true}).selectOption('live');
      await input.fill('这个问题走隔离live协议');await send.click();
      await page.getByText('隔离协议回应，先试一小步', {exact:true}).waitFor();
      await page.getByText('· 实际模型：fixture-only-model', {exact:true}).waitFor();
      assert.equal(await input.inputValue(),'');
      assert.equal(await page.evaluate(()=>window.sent),4);
      assert.equal(await page.evaluate(()=>window.liveReads),2);
    });
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ scope: 'Isolated component fixture; no server/provider/real identity.', results, errors }, null, 2));
  } finally {
    if (browser) await browser.close();
    fs.rmSync(temporary, { recursive: true, force: true });
  }
})().catch(e => { console.error(e.stack); process.exitCode = 1; });
