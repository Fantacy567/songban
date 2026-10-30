/* CORE-01 browser acceptance: real Chrome against an isolated TCP service (mirror without .env, temp DB/HOME, synthetic Codex logs). */
const {chromium}=require('/Users/ben/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net'),assert=require('node:assert/strict');
const {spawn,spawnSync}=require('node:child_process');
const repo=path.resolve(__dirname,'..'),py=path.join(repo,'.venv/bin/python'),out=path.join(repo,'docs/reviews/core-01-evidence');
const SESSION_A='synthetic-core01-session-a',FAKE='sk-'+'synthetic'+'0'.repeat(12);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const freePort=()=>new Promise(r=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>r(p));});});
const msg=(role,text,extra={})=>({type:'response_item',payload:{type:'message',role,content:[{type:role==='user'?'input_text':'output_text',text}],...extra}});
function codexTurn(file,id,user,reply,model='synthetic-model-x1'){const items=[{type:'event_msg',payload:{type:'task_started',turn_id:id}}];if(model)items.push({type:'turn_context',payload:{model}});
 items.push(msg('user','<environment_context>\n  <cwd>/synthetic</cwd>\n</environment_context>'),msg('user',user),{type:'event_msg',payload:{type:'user_message',message:user}},{type:'response_item',payload:{type:'reasoning',summary:[{type:'summary_text',text:'思考摘要-不应上传'}]}},msg('assistant','过程说明-不应上传',{phase:'commentary'}),{type:'response_item',payload:{type:'function_call_output',call_id:'c',output:'工具输出-不应上传'}},msg('assistant',reply,{phase:'final_answer'}),{type:'event_msg',payload:{type:'task_complete',turn_id:id,last_agent_message:reply}});
 fs.appendFileSync(file,items.map(x=>JSON.stringify(x)+'\n').join(''));}
let server,browser,dir;const errors=[],result={date:new Date().toISOString(),scope:'真实Chrome + 隔离TCP服务 + 临时数据库/HOME合成Codex日志；未连接8886、未读取.env、未调用模型',checks:{}};
async function login(context,who){const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));await page.goto(base());await page.locator('#phone').fill(who.phone);await page.locator('#password').fill(who.password);await page.locator('#auth-form button[type=submit]').click();return page;}
let port;const base=()=>'http://127.0.0.1:'+port;
async function records(page){return page.locator('#library-notes article.report').evaluateAll(list=>list.map(a=>{const [first,second]=a.querySelectorAll('p');return {first:first.textContent,firstBold:Boolean(first.querySelector('strong'))&&first.querySelector('strong').textContent===first.textContent,second:second.textContent,secondBold:Boolean(second.querySelector('strong,b'))&&getComputedStyle(second).fontWeight>=600,lines:a.querySelectorAll('p').length};}));}
(async()=>{try{
 dir=fs.mkdtempSync(path.join(os.tmpdir(),'songban-core01-ui-'));fs.mkdirSync(out,{recursive:true});
 const staged=spawnSync(py,[path.join(repo,'scripts/continuous_sync_acceptance.py'),'stage','--dir',dir],{encoding:'utf8'});assert.equal(staged.status,0,staged.stderr);
 assert(!fs.existsSync(path.join(dir,'src/.env')));
 const fx=Object.fromEntries(JSON.parse(fs.readFileSync(path.join(dir,'fixture.json'),'utf8')).map(m=>[m.id,m]));const A=fx['core01-a'],B=fx['core01-b'];
 const logA=path.join(dir,'home/.codex/sessions/2026/10/29/rollout-2026-10-29T22-00-00-'+SESSION_A+'.jsonl');
 port=await freePort();result.port=port;
 server=spawn(py,[path.join(dir,'src/scripts/continuous_sync_acceptance.py'),'serve','--dir',dir,'--port',String(port)],{cwd:path.join(dir,'src'),env:{HOME:path.join(dir,'home'),PATH:process.env.PATH,PYTHONDONTWRITEBYTECODE:'1'},stdio:'ignore'});
 for(let i=0;i<100;i++){try{if((await fetch(base()+'/health')).ok)break;}catch{}await sleep(200);}
 browser=await chromium.launch({channel:'chrome',headless:true});
 const ctxA=await browser.newContext({viewport:{width:1440,height:1000}}),ctxB=await browser.newContext({viewport:{width:1440,height:1000}});
 const page=await login(ctxA,A);await page.locator('#team-name').fill('CORE-01 浏览器合成团队');await page.locator('#create-team button[type=submit]').click();await page.locator('#direction-form').waitFor();
 const token=await page.evaluate(()=>localStorage.getItem('studio-token'));const me=await (await fetch(base()+'/api/core/me',{headers:{Authorization:'Bearer '+token}})).json();
 const joined=await fetch(base()+'/api/core/join',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+B.token},body:JSON.stringify({code:me.teams[0].code})});assert.equal(joined.status,200);

 await page.locator('[data-tab=plugin]').click();await page.waitForFunction(()=>{const s=document.querySelector('#continuous-thread');return s&&!s.disabled;});
 const optionText=await page.locator('#continuous-thread option[value="'+SESSION_A+'"]').textContent();result.checks.session_option_metadata_only=!/旧历史|合成说明/.test(optionText);assert(result.checks.session_option_metadata_only);
 await page.locator('#continuous-thread').selectOption(SESSION_A);await page.locator('#continuous-start').click();await sleep(800);
 result.checks.no_consent_blocked=(await page.locator('#continuous-status').textContent()).includes('未连接')||(await page.locator('#continuous-status').textContent()).includes('尚未连接');assert(result.checks.no_consent_blocked);
 await page.locator('#continuous-form input[name=consent]').check();await page.locator('#continuous-start').click();
 await page.locator('#continuous-status').filter({hasText:'持续同步中'}).waitFor({timeout:8000});result.checks.ui_connected=true;
 await page.locator('#continuous-card').screenshot({path:path.join(out,'ui_connected.png')});

 const u1='浏览器第一轮：把注册页接到接口。API_KEY='+FAKE,r1='注册页已接好。\n要点：提交后返回200并跳转。';
 codexTurn(logA,'ui-1',u1,r1);
 await page.locator('[data-tab=library]').click();
 await page.locator('#library-notes article.report').first().waitFor({timeout:12000}).catch(async()=>{await sleep(3000);await page.locator('#library-refresh').click();await page.locator('#library-notes article.report').first().waitFor({timeout:8000});});
 const u2='浏览器第二轮：资料库停留时自动刷新。',r2='已确认停留页面会自动出现新记录。';
 codexTurn(logA,'ui-2',u2,r2,'');
 await page.waitForFunction(()=>document.querySelectorAll('#library-notes article.report').length>=2,null,{timeout:15000});result.checks.library_auto_refresh_without_click=true;
 let rows=await records(page);result.library_rows_ui=rows.map(r=>[r.first,r.second]);
 const first=rows.find(r=>r.first.startsWith('甲·合成成员：浏览器第一轮')),second=rows.find(r=>r.first.startsWith('甲·合成成员：浏览器第二轮'));
 result.checks.two_lines_bold_then_plain=rows.every(r=>r.lines===2&&r.firstBold&&!r.secondBold);
 result.checks.name_text_model_correct=Boolean(first&&second)&&first.first.includes('[已隐藏]')&&first.second.startsWith('synthetic-model-x1：注册页已接好。')&&second.second==='模型名未获取：'+r2;
 const pageText=await page.locator('body').innerText();result.checks.no_secret_thinking_tool_history=![FAKE,'思考摘要','过程说明','工具输出','environment_context','旧历史'].some(x=>pageText.includes(x));
 assert(result.checks.two_lines_bold_then_plain&&result.checks.name_text_model_correct&&result.checks.no_secret_thinking_tool_history,JSON.stringify(rows));
 await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(out,'ui_library_two_lines.png'),fullPage:true});

 const pageB=await login(ctxB,B);await pageB.locator('[data-tab=library]').waitFor();await pageB.locator('[data-tab=library]').click();await pageB.waitForFunction(()=>document.querySelectorAll('#library-notes article.report').length>=2,null,{timeout:10000});
 result.checks.second_account_same_team_sees=(await records(pageB)).length===2;assert(result.checks.second_account_same_team_sees);
 await pageB.screenshot({path:path.join(out,'ui_teammate_library.png'),fullPage:true});

 await page.locator('[data-tab=plugin]').click();await page.locator('#continuous-stop').waitFor();await page.locator('#continuous-status').filter({hasText:'持续同步中'}).waitFor({timeout:8000});await page.locator('#continuous-stop').click();
 await page.locator('#continuous-status').filter({hasText:'已停止'}).waitFor({timeout:8000});result.checks.ui_stopped=true;
 await page.locator('#continuous-card').screenshot({path:path.join(out,'ui_stopped.png')});
 codexTurn(logA,'ui-3','浏览器第三轮：停止后-不应上传','不应上传');await sleep(6000);
 await page.locator('[data-tab=library]').click();await page.locator('#library-notes article.report').first().waitFor();
 result.checks.after_stop_not_uploaded=(await records(page)).length===2&&!(await page.locator('body').innerText()).includes('不应上传');assert(result.checks.after_stop_not_uploaded);
 result.pageerrors=errors;assert.deepEqual(errors,[]);
 const text=JSON.stringify(result,null,2);assert(!text.includes(FAKE));fs.writeFileSync(path.join(out,'ui_acceptance.json'),text+'\n');
 console.log('浏览器实测通过：选择/授权/连接/两行资料库/自动刷新/队友可见/停止后不上传。');
}finally{if(browser)await browser.close();if(server){server.kill('SIGTERM');await sleep(800);}if(dir)fs.rmSync(dir,{recursive:true,force:true});}})().catch(e=>{console.error(e.message);process.exitCode=1;});
