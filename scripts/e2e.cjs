/* Real browser workflow; all records are labelled development acceptance inputs. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:8886';
const output = path.resolve(__dirname, '../artifacts');
const videoTemp = path.join(output, 'video-temp');
const steps = [], errors = [], secrets = [];
fs.mkdirSync(videoTemp, {recursive:true});
let browser, captain, teammate, mobile, captainPage, video, success = false;
function step(name){steps.push({name,result:'通过'}); console.log('PASS',name);}
function redact(value){let text=String(value); for(const secret of secrets)text=text.split(secret).join('[REDACTED]');return text;}
async function refreshed(page){const response=page.waitForResponse(r=>r.url()===`${base}/api/projects/${projectId}`&&r.request().method()==='GET');await page.locator('#refresh').click();await response;}
async function navigate(page,tab){await page.locator(`[data-tab="${tab}"]`).click();await page.locator('#content').waitFor();}
let projectId;
async function action(page,key,kind,note=''){
  console.log('ACTION',key,kind);
  const card=page.locator(`[data-task-card="${key}"]`);
  const promise=page.waitForResponse(r=>r.url().includes('/tasks/')&&r.url().endsWith('/actions')&&r.request().method()==='POST');
  await card.locator(`[data-action="${kind}"]`).click();
  if(!['start','resume'].includes(kind)){
    await page.locator('#action-dialog').waitFor({state:'visible'});
    await page.locator('#action-note').fill(note);
    await page.locator('#confirm-action').click();
  }
  const response=await promise;
  assert.equal(response.status(),200,`任务操作 ${key}/${kind} 应成功`);
  const map={start:'in_progress',block:'blocked',resume:'in_progress',submit:'review',accept:'accepted',return:'in_progress'};
  await page.locator(`[data-task-card="${key}"][data-status="${map[kind]}"]`).waitFor();
  if(!['start','resume'].includes(kind))await page.locator('#action-dialog').waitFor({state:'hidden'});
  return map[kind];
}

(async()=>{
  browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'chrome',headless:true,slowMo:95});
  captain=await browser.newContext({viewport:{width:1440,height:1000},recordVideo:{dir:videoTemp,size:{width:1440,height:1000}},permissions:['clipboard-write','clipboard-read']});
  teammate=await browser.newContext({viewport:{width:1360,height:960}});
  captain.setDefaultTimeout(15000);teammate.setDefaultTimeout(15000);
  captainPage=await captain.newPage();
  const other=await teammate.newPage();
  for(const p of [captainPage,other])p.on('pageerror',e=>errors.push(e.message));
  captainPage.on('dialog',dialog=>dialog.accept());other.on('dialog',dialog=>dialog.accept());
  video=captainPage.video();
  await captainPage.goto(base);
  await captainPage.getByRole('heading',{name:'创建团队工作区'}).waitFor();
  await captainPage.screenshot({path:path.join(output,'01_create_workspace.png'),fullPage:true});
  await captainPage.locator('#project-name').fill('赛内协作助手 · 本轮开发验收');
  await captainPage.locator('#member-name-0').fill('队长测试会话');
  await captainPage.locator('#member-role-0').fill('产品 / 后端');
  await captainPage.locator('#member-skills-0').fill('Python、接口实现与测试');
  await captainPage.locator('#member-name-1').fill('前端测试会话');
  await captainPage.locator('#member-role-1').fill('前端 / 设计');
  await captainPage.locator('#member-skills-1').fill('JavaScript、页面联调');
  const creation=captainPage.waitForResponse(r=>r.url()===base+'/api/projects'&&r.request().method()==='POST');
  await captainPage.locator('#create-project').click();
  const created=await(await creation).json();projectId=created.project_id;secrets.push(...created.invites.map(i=>i.access_token));
  await captainPage.locator('#entry-dialog').waitFor({state:'visible'});
  await captainPage.locator('#close-dialog').click();
  step('F01：通过页面创建两人项目，保存独立成员身份');
  const sourceEntries=[
    {kind:'rules',title:'本轮开发验收要求（非赛事公告）',body:'本轮开发验收要求：交付需求文档、业务流程图、后端接口和可操作的协作页面。使用两名测试成员走通确认、执行、交叉验收与复盘；真实模型尚未配置时必须如实标注，不能把协议模拟测试写成真实模型测试。'},
    {kind:'discussion',title:'开发计划原文（验收演练）',body:'说明：这是本轮开发验收输入，不是实时录音或真实队友发言。\n目标：让两名成员共同推进一个有原文依据、能交叉验收的核心流程。\n决定：先实现后端接口与前端页面，再联调、复核文档和交付。\n待确认：对照生成任务核实负责人和工时。'},
  ];
  for(const source of sourceEntries){
    await captainPage.locator('#source-kind').selectOption(source.kind);
    await captainPage.locator('#source-title').fill(source.title);
    await captainPage.locator('#source-body').fill(source.body);
    const saved=captainPage.waitForResponse(r=>r.url().endsWith('/sources')&&r.request().method()==='POST');
    await captainPage.getByRole('button',{name:'保存原文',exact:true}).click();assert.equal((await saved).status(),201);
    await captainPage.getByRole('heading',{name:source.title,exact:true}).waitFor();
  }
  step('F02：通过页面录入两份真实开发验收原文，未冒充赛事或录音');
  await navigate(captainPage,'plan');
  const currentWorkspace=await captain.request.get(`${base}/api/projects/${projectId}`,{headers:{Authorization:`Bearer ${created.invites[0].access_token}`}}).then(r=>r.json());
  if(!currentWorkspace.model_configured){
  const missing=captainPage.waitForResponse(r=>r.url().endsWith('/proposals')&&r.request().method()==='POST');
  await captainPage.locator('#generate-model').click();
  assert.equal((await missing).status(),503);
  await captainPage.locator('#notice').filter({hasText:'真实模型尚未配置'}).waitFor();
  step('F02：未配置模型时显示错误，保留原文，未伪装模型成功');
  }else{steps.push({name:'未配置模型分支',result:'跳过：已有真实配置，自动化不调用付费服务'});}
  const generation=captainPage.waitForResponse(r=>r.url().endsWith('/proposals')&&r.request().method()==='POST');
  await captainPage.locator('#generate-rules').click();assert.equal((await generation).status(),201);
  await captainPage.locator('#draft-goal').waitFor();
  assert.match(await captainPage.locator('#content').innerText(),/本地规则演练.*非大模型/);
  await captainPage.locator('#draft-goal').fill('完成可共享、可交叉验收的赛内协作闭环');
  await captainPage.locator('[data-draft-task="T1"] [data-field="title"]').fill('交付后端接口与状态机');
  const saved=captainPage.waitForResponse(r=>r.request().method()==='PUT'&&r.url().includes('/proposals/'));
  await captainPage.locator('#save-draft').click();assert.equal((await saved).status(),200);
  await captainPage.locator('#notice').filter({hasText:'草案已保存'}).waitFor();
  await captainPage.locator('#notice').waitFor({state:'hidden'});
  await captainPage.screenshot({path:path.join(output,'02_review_plan.png'),fullPage:true});
  step('F03：明确标注规则草案，队长实际修改目标和任务并保存');
  const confirmation=captainPage.waitForResponse(r=>r.url().endsWith('/confirm')&&r.request().method()==='POST');
  await captainPage.locator('#confirm-plan').click();assert.equal((await confirmation).status(),200);
  await captainPage.locator('[data-task-card="T1"]').waitFor();
  const invite=created.invites[1];
  await other.goto(`${base}/#project=${projectId}&token=${encodeURIComponent(invite.access_token)}`);
  await other.locator('.identity').filter({hasText:'前端测试会话'}).waitFor();
  await navigate(other,'tasks');
  assert.equal(await captainPage.locator('[data-task-card]').count(),4);
  assert.equal(await other.locator('[data-task-card]').count(),4);
  assert.equal(await captainPage.locator('[data-task-card="T3"] [data-action="start"]').isDisabled(),true);
  step('F04/F05/F07：队长确认生成任务；第二独立会话读取同一任务，未验收依赖不能开始');
  await action(captainPage,'T1','start');
  await action(captainPage,'T1','block','验收演练：发现接口交接文档尚需补齐失败示例，先记录并核对。');
  await action(captainPage,'T1','resume');
  await action(captainPage,'T1','submit','后端已实现，接口测试通过；需复核接口交接文档。成果：app/main.py、tests/test_workflow.py。');
  await captainPage.locator('[data-task-card="T1"]').getByText('等待另一位成员验收').waitFor();
  assert.equal(await captainPage.locator('[data-task-card="T1"] [data-action="accept"]').count(),0);
  const state=await captain.request.get(`${base}/api/projects/${projectId}`,{headers:{Authorization:`Bearer ${created.invites[0].access_token}`}}).then(r=>r.json());
  const t1=state.tasks.find(t=>t.task_key==='T1');
  const selfReview=await captain.request.post(`${base}/api/projects/${projectId}/tasks/${t1.id}/actions`,{headers:{Authorization:`Bearer ${created.invites[0].access_token}`},data:{expected_version:t1.version,action:'accept',note:''}});
  assert.equal(selfReview.status(),403);
  await refreshed(other);
  await action(other,'T1','return','请把失败响应、跨成员验收和版本冲突的验证证据一起写入交接材料。');
  await refreshed(captainPage);
  await action(captainPage,'T1','submit','已补齐接口交接和本轮验收说明；成功、失败、权限与冲突路径均有测试记录。');
  await refreshed(other);await action(other,'T1','accept','已对照代码、接口测试和交接文档核对。');
  step('F05/F06：记录与解除阻塞，提交成果，后端拒绝自验；另一成员退回后重新提交并通过');
  await action(other,'T2','start');
  await action(other,'T2','submit','操作页面已实现，能输入资料、编辑草案和显示真实后端任务；成果：static/app.js、static/style.css。');
  await refreshed(captainPage);await action(captainPage,'T2','accept','已实际操作页面并核对共享数据。');
  await action(captainPage,'T3','start');
  await action(captainPage,'T3','submit','两独立会话走通创建、确认、提交、退回与交叉验收，依赖解锁符合流程。');
  await refreshed(other);await action(other,'T3','accept','本测试会话能读取并更新同一项目，操作结果一致。');
  await action(other,'T4','start');
  await action(other,'T4','submit','需求、业务流程、接口交接与测试证据已整理；本次流程使用规则演练，真实模型结果另列，不以此证明模型质量。');
  await refreshed(captainPage);await action(captainPage,'T4','accept','已对照本轮开发要求核对交付，规则流程与真实模型验收范围已分别列明。');
  step('F05/F06：前置任务验收后解锁后置任务，四项任务由不同成员交叉通过');
  await captainPage.locator('#notice').waitFor({state:'hidden'});
  await captainPage.screenshot({path:path.join(output,'03_shared_tasks_accepted.png'),fullPage:true});
  await navigate(captainPage,'recap');
  await captainPage.getByRole('heading',{name:'核心成果，已通过验收。'}).waitFor();
  const report=await captain.request.get(`${base}/api/projects/${projectId}/recap`,{headers:{Authorization:`Bearer ${created.invites[0].access_token}`}}).then(r=>r.json());
  assert.equal(report.ready,true);assert.equal(report.stats.must_accepted,4);assert.equal(report.stats.block_events,1);assert.equal(report.stats.return_events,1);
  await captainPage.locator('#notice').waitFor({state:'hidden'});
  await captainPage.screenshot({path:path.join(output,'04_delivery_recap.png'),fullPage:true});
  const download=captainPage.waitForEvent('download');await captainPage.locator('#export').click();const downloaded=await download;await downloaded.saveAs(path.join(output,'acceptance_recap.md'));
  const exported=fs.readFileSync(path.join(output,'acceptance_recap.md'),'utf8');assert.ok(exported.includes('过程记录'));assert.ok(secrets.every(s=>!exported.includes(s)));
  step('F08：必须任务全部验收后可交付，复盘准确显示一次阻塞和一次退回，成功导出');
  mobile=await browser.newContext({viewport:{width:390,height:844},isMobile:true,deviceScaleFactor:1});
  const small=await mobile.newPage();small.on('pageerror',e=>errors.push(e.message));
  await small.goto(`${base}/#project=${projectId}&token=${encodeURIComponent(created.invites[0].access_token)}`);
  await navigate(small,'model');await small.getByRole('heading',{name:'选择这次协作的模型'}).waitFor();
  assert.equal(await small.locator('[data-tab="model"]').evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;}),true);
  step('F10：390px 导航可横向滚动，隐藏的模型接入入口可点击');
  await navigate(small,'tasks');await small.locator('[data-task-card="T4"]').waitFor();
  assert.equal(await small.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await small.screenshot({path:path.join(output,'05_mobile_tasks.png'),fullPage:true});
  step('F10：390px 窄屏无页面横向溢出，关键任务可见');
  assert.deepEqual(errors,[]);step('F10：完整流程无未处理 JavaScript 异常');
  success=true;
})().catch(error=>{console.error(redact(error.stack));process.exitCode=1;}).finally(async()=>{
  if(mobile)await mobile.close();if(teammate)await teammate.close();if(captain)await captain.close();
  if(success&&video){const source=await video.path();fs.copyFileSync(source,path.join(output,'workflow_walkthrough.webm'));}
  if(browser)await browser.close();
  fs.rmSync(videoTemp,{recursive:true,force:true});
  fs.writeFileSync(path.join(output,'browser-results.json'),JSON.stringify({success,base_url:base,steps,unhandled_errors:errors.map(redact),actual_model_tested:false,note:'双成员由自动化控制的独立测试会话扮演，不代表真实队友已使用；视频中为明确标注的本轮开发验收输入。'},null,2));
});
