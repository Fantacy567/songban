/* CORE-02 browser acceptance: real Chrome against an isolated TCP service (mirror without .env, temp DB, synthetic accounts, protocol substitute — not a real model). */
const {chromium}=require('/Users/ben/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net'),assert=require('node:assert/strict');
const {spawn,spawnSync}=require('node:child_process');
const repo=path.resolve(__dirname,'..'),py=path.join(repo,'.venv/bin/python'),out=path.join(repo,'docs/reviews/core-02-evidence');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const freePort=()=>new Promise(r=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>r(p));});});
const T1_PROMPT_START='目标：验证姓名接口对正常姓名和空姓名的实际返回。';
let server,browser,dir,port;const errors=[],alerts=[],result={date:new Date().toISOString(),scope:'真实Chrome + 隔离TCP服务 + 无.env镜像/临时数据库/合成账号；草案来自协议替身，不代表真实模型质量',checks:{}};
const base=()=>'http://127.0.0.1:'+port;
const call=(method,p,token,body)=>fetch(base()+p,{method,headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:body?JSON.stringify(body):undefined}).then(r=>r.json());
async function login(context,who){const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>{if(d.type()==='confirm')d.accept();else{alerts.push(d.message());d.dismiss();}});
 await page.goto(base());await page.locator('#phone').fill(who.phone);await page.locator('#password').fill(who.password);await page.locator('#auth-form button[type=submit]').click();return page;}
async function openAll(page,scope){await page.locator(scope+' details').evaluateAll(list=>list.forEach(d=>d.open=true));}
(async()=>{try{
 dir=fs.mkdtempSync(path.join(os.tmpdir(),'songban-core02-ui-'));fs.mkdirSync(out,{recursive:true});
 const staged=spawnSync(py,[path.join(repo,'scripts/continuous_sync_acceptance.py'),'stage','--dir',dir],{encoding:'utf8'});assert.equal(staged.status,0,staged.stderr);
 assert(!fs.existsSync(path.join(dir,'src/.env')));
 const fx=Object.fromEntries(JSON.parse(fs.readFileSync(path.join(dir,'fixture.json'),'utf8')).map(m=>[m.id,m]));const A=fx['core01-a'],B=fx['core01-b'];
 port=await freePort();result.port=port;fs.writeFileSync(path.join(dir,'mode'),'good');
 server=spawn(py,[path.join(dir,'src/scripts/executable_tasks_acceptance.py'),'serve','--dir',dir,'--port',String(port)],{cwd:path.join(dir,'src'),env:{HOME:path.join(dir,'home'),PATH:process.env.PATH,PYTHONDONTWRITEBYTECODE:'1'},stdio:'ignore'});
 for(let i=0;i<100;i++){try{if((await fetch(base()+'/health')).ok)break;}catch{}await sleep(200);}
 browser=await chromium.launch({channel:'chrome',headless:true});
 const ctxA=await browser.newContext({viewport:{width:1440,height:1000}}),ctxB=await browser.newContext({viewport:{width:1440,height:1000}});
 await ctxA.grantPermissions(['clipboard-read','clipboard-write'],{origin:base()});
 const page=await login(ctxA,A);await page.locator('#team-name').fill('CORE-02 浏览器合成团队');await page.locator('#create-team button[type=submit]').click();await page.locator('#direction-form').waitFor();
 const token=await page.evaluate(()=>localStorage.getItem('studio-token'));const me=await call('GET','/api/core/me',token);const sid=me.teams[0].id,teamPath='/api/core/teams/'+sid;
 await call('POST','/api/core/join',B.token,{code:me.teams[0].code});
 const rev=(await call('GET',teamPath,token)).revision;await call('PUT',teamPath+'/direction',token,{goal:'做出可演示的姓名登记页',rules:'合成主办方原文：提交可运行演示与30秒录屏。',rubric:'合成评分：功能可用、演示清楚。',non_goals:'',deadline:'',expected_revision:rev});

 await page.locator('[data-tab=overview]').click();await page.locator('#review').click();await page.locator('#confirm-plan').waitFor({timeout:10000});
 await openAll(page,'.card.accent');
 const draft=page.locator('.card.accent .execution').first();
 const draftText=await draft.innerText();
 result.checks.draft_shows_all_fields=['照做说明 · 终端','按团队已有启动说明启动后端','保存两次实际返回','要交的成果：两次请求的实际返回原文','卡住时：写明卡在哪一步','检查方法：正常姓名与空姓名各请求一次','依据：direction'].every(x=>draftText.includes(x));
 result.checks.draft_steps_ordered=(await draft.locator('ol li').allInnerTexts()).join('|')==='按团队已有启动说明启动后端|发一次正常姓名请求|发一次空姓名请求|保存两次实际返回';
 result.checks.draft_non_ai_label=(await page.locator('.card.accent .execution').nth(1).innerText()).includes('不需要AI指令');
 const prompt=await draft.locator('textarea.ai-prompt').inputValue();result.checks.prompt_complete_readonly=prompt.startsWith(T1_PROMPT_START)&&await draft.locator('textarea.ai-prompt').evaluate(t=>t.readOnly);
 await draft.locator('[data-copy-prompt]').click();await page.locator('#toast').filter({hasText:'没有执行任何操作'}).waitFor();
 result.checks.copy_puts_exact_prompt_on_clipboard=(await page.evaluate(()=>navigator.clipboard.readText()))===prompt;
 assert(Object.values(result.checks).every(Boolean),JSON.stringify(result.checks));
 await page.screenshot({path:path.join(out,'ui_draft_execution.png'),fullPage:true});

 await page.locator('#confirm-plan').click();await page.locator('#confirmed-tasks .execution').first().waitFor({timeout:8000});await openAll(page,'#confirmed-tasks');
 const confirmedText=await page.locator('#confirmed-tasks').innerText();
 result.checks.confirmed_task_keeps_execution=['照做说明 · 终端','保存两次实际返回','照做说明 · 浏览器与系统录屏','不需要AI指令'].every(x=>confirmedText.includes(x));
 await page.reload();await page.locator('#confirmed-tasks .execution').first().waitFor();await openAll(page,'#confirmed-tasks');
 result.checks.after_reload_still_there=(await page.locator('#confirmed-tasks').innerText()).includes('保存两次实际返回');
 await page.locator('#confirmed-tasks').screenshot({path:path.join(out,'ui_confirmed_execution.png')});
 const pageB=await login(ctxB,B);await pageB.locator('#confirmed-tasks .execution').first().waitFor({timeout:8000});await openAll(pageB,'#confirmed-tasks');
 const textB=await pageB.locator('#confirmed-tasks').innerText();result.checks.teammate_reads_execution=textB.includes('一段约30秒的录屏')&&textB.includes('保存两次实际返回');
 result.checks.teammate_cannot_publish=(await pageB.locator('#confirm-plan').count())===0;

 const firstExec='#confirmed-tasks .execution';
 async function unrelatedUpdate(strengths){await page.locator(firstExec).first().evaluate(d=>d.dataset.stale='1');await call('PUT',teamPath+'/profile',B.token,{strengths,willingness:'',hours:3});
  await page.waitForFunction(s=>{const d=document.querySelector(s);return d&&!d.dataset.stale;},firstExec,{timeout:12000});}
 await page.locator(firstExec).evaluateAll(list=>list.forEach(d=>d.open=false));await page.locator(firstExec+' > summary').first().click();
 await unrelatedUpdate('合成：前端与录屏');
 result.checks.open_survives_unrelated_revision=await page.locator(firstExec).first().evaluate(d=>d.open)&&(await page.locator(firstExec).first().innerText()).includes('保存两次实际返回');
 await page.locator(firstExec+' > summary').first().click();await unrelatedUpdate('合成：前端');
 result.checks.collapse_survives_unrelated_revision=!(await page.locator(firstExec).first().evaluate(d=>d.open));
 await page.locator(firstExec+' > summary').first().click();const reportCount=async()=>Number(await page.locator('.stat strong').nth(1).innerText());const before=await reportCount();
 await page.locator(firstExec+' textarea.ai-prompt').first().click();await page.locator(firstExec).first().evaluate(d=>d.dataset.stale='1');
 await call('POST',teamPath+'/reports',B.token,{event_id:'core02-r2-'+Date.now(),tool:'网页本人补充',origin:'human',summary:'合成：与任务无关的进展',status:'discussion'});await sleep(11000);
 result.checks.prompt_focus_holds_redraw=await page.locator(firstExec).first().evaluate(d=>d.dataset.stale==='1')&&await reportCount()===before;
 await page.locator('.hero h1').click();await page.waitForFunction(s=>{const d=document.querySelector(s);return d&&!d.dataset.stale;},firstExec,{timeout:12000});
 result.checks.blur_catches_up_same_revision=await reportCount()===before+1&&await page.locator(firstExec).first().evaluate(d=>d.open);

 fs.writeFileSync(path.join(dir,'mode'),'hostile');await call('PUT',teamPath+'/profile',B.token,{strengths:'前端',willingness:'',hours:2});
 await page.locator('#review').click();await page.locator('#confirm-plan').waitFor({timeout:10000});await openAll(page,'.card.accent');await sleep(500);
 const hostileBox=page.locator('.card.accent .execution').first();
 result.checks.hostile_shown_as_text=(await hostileBox.innerText()).includes('<img src=x onerror="alert(1)">')&&await hostileBox.locator('img,script').count()===0&&(await hostileBox.locator('textarea').count())===1;
 result.checks.no_alert_or_page_error=alerts.length===0&&errors.length===0;
 await hostileBox.screenshot({path:path.join(out,'ui_hostile_text.png')});
 result.alerts=alerts;result.pageerrors=errors;
 assert(Object.values(result.checks).every(Boolean),JSON.stringify(result.checks));
 fs.writeFileSync(path.join(out,'ui_acceptance.json'),JSON.stringify(result,null,2)+'\n');
 console.log('浏览器实测通过：草案/确认任务展开完整说明、复制指令、刷新保留、队友可读、恶意文字只显示为文本。');
}finally{if(browser)await browser.close();if(server){server.kill('SIGTERM');await sleep(800);}if(dir)fs.rmSync(dir,{recursive:true,force:true});}})().catch(e=>{console.error(e.message);process.exitCode=1;});
