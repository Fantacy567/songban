if(!process.env.SONGBAN_QA_DIR){require('./run_core_e2e.cjs').run(__filename).catch(e=>{console.error(e.message);process.exitCode=1;});return;}
/* Actual UI + two independent MCP subprocesses + file watcher. Model reply is labelled substitute. */
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const readline=require('node:readline');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const base=process.env.CORE_TEST_BASE||'http://127.0.0.1:8888';
const privateDir=process.env.SONGBAN_QA_DIR;
const out=path.resolve(process.env.SONGBAN_E2E_OUTPUT);fs.mkdirSync(out,{recursive:true});
const fixture=JSON.parse(fs.readFileSync(privateDir+'/private-fixture.json','utf8'));
const bridge=path.resolve(__dirname,'../plugins/songban-team/bridge.py');
const children=[],errors=[],steps=[];let browser;
function step(s){steps.push(s);console.log(s);}
function agent(token,sid,suffix){
 const cwd=privateDir+'/agent-'+suffix;fs.mkdirSync(cwd,{recursive:true});
 const env={...process.env,SONGBAN_URL:base,SONGBAN_TEAM_ID:sid,SONGBAN_TOKEN:token};
 const p=spawn(process.env.SONGBAN_QA_PYTHON,[bridge,'mcp'],{cwd,env,stdio:['pipe','pipe','pipe']});children.push(p);
 let n=0;const pending=new Map();const lines=readline.createInterface({input:p.stdout});
 lines.on('line',l=>{let r;try{r=JSON.parse(l);}catch{return;}const cb=pending.get(r.id);if(cb){pending.delete(r.id);cb(r);}});
 p.stderr.on('data',()=>{});
 return {env,cwd,p,async rpc(method,params={}){const id=++n;const r=await new Promise((resolve,reject)=>{pending.set(id,resolve);p.stdin.write(JSON.stringify({jsonrpc:'2.0',id,method,params})+'\n');setTimeout(()=>{if(pending.has(id)){pending.delete(id);reject(Error('MCP request timeout'));}},12000).unref();});assert(!r.error,JSON.stringify(r.error));return r.result;},async tool(name,args={}){const r=await this.rpc('tools/call',{name,arguments:args});return {...r,data:r.isError?null:JSON.parse(r.content[0].text)};}};
}
(async()=>{
 try{
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{})});
  const a=await browser.newContext({viewport:{width:1440,height:1050}}),b=await browser.newContext({viewport:{width:1280,height:900}});
  const pa=await a.newPage(),pb=await b.newPage();for(const p of [pa,pb])p.on('pageerror',e=>errors.push(e.message));
  for(const [p,f] of [[pa,fixture[0]],[pb,fixture[1]]]){await p.goto(base+'/core');await p.locator('#phone').fill(f.phone);await p.locator('#password').fill(f.password);await p.locator('#auth-form button[type=submit]').click();await p.locator('#team-switch').waitFor();}
  await pa.locator('#team-switch').selectOption('__new');await pa.locator('#team-name').fill('双工具协作 · 隔离验收');await pa.locator('#create-team button').click();await pa.locator('#direction-form').waitFor();
  const tokenA=await pa.evaluate(()=>localStorage.getItem('studio-token'));let sid=await pa.evaluate(()=>localStorage.getItem('studio-squad'));
  const authA={Authorization:'Bearer '+tokenA};const first=await a.request.get(base+'/api/core/teams/'+sid,{headers:authA}).then(r=>r.json());
  await pb.locator('#team-switch').selectOption('__new');await pb.locator('#team-code').fill(first.team.code);await pb.locator('#join-team button').click();await pb.locator('#direction-form').waitFor();
  await pa.locator('[data-tab=direction]').click();await pa.locator('[name=goal]').fill('做通个人智能体同步、团队统筹、确认与任务回传');await pa.locator('[name=rules]').fill('验收输入，非赛事公告：交付可操作的两人协作演示。');await pa.locator('[name=rubric]').fill('本轮验收关注：实现完整、来源清楚、不伪造成功。');await pa.locator('[name=non_goals]').fill('暂不开发找比赛、素材库和赛后培训。');await pa.locator('#direction-form button').click();await pa.getByRole('status').filter({hasText:'共同方向已更新'}).waitFor();
  step('通过真实页面登录、建队、加入、确认共同方向');
  const tokenB=await pb.evaluate(()=>localStorage.getItem('studio-token'));const authB={Authorization:'Bearer '+tokenB};
  const connections=[];
  for(const [p,label] of [[pa,'个人工具A · MCP协议验收'],[pb,'个人工具B · MCP与文件验收']]){
    await p.locator('[data-tab=plugin]').click();await p.locator('#connection-form input').fill(label);
    const res=p.waitForResponse(r=>r.url().endsWith('/connections')&&r.request().method()==='POST');await p.locator('#connection-form button').click();connections.push(await(await res).json());
  }
  const aa=agent(connections[0].token,sid,'a'),bb=agent(connections[1].token,sid,'b');
  await aa.rpc('initialize',{protocolVersion:'2024-11-05',capabilities:{},clientInfo:{name:'acceptance-a',version:'1'}});await bb.rpc('initialize',{protocolVersion:'2024-11-05',capabilities:{},clientInfo:{name:'acceptance-b',version:'1'}});
  assert.equal((await aa.rpc('tools/list')).tools.length,3);
  const ca=await aa.tool('songban_get_team_context');assert.equal(ca.data.direction.goal,'做通个人智能体同步、团队统筹、确认与任务回传');
  await pa.locator('[data-tab=members]').click();await pa.locator('#auto-review').check();await pa.locator('#auto-notice').filter({hasText:'自动生成草案'}).waitFor();
  const reportA={event_id:'mcp-a-'+Date.now(),tool:'MCP客户端A（协议验收）',summary:'登录接口代码已经写好，但还没有实际请求验证。',status:'in_progress',views:[{topic:'登录接口是否可用',position:'代码已写好，待实际验证'}],evidence:['验收场景的个人报告，非真实项目运行证据'],excerpt:'成员：先确认接口输入字段。个人智能体：代码已写好，尚未验证。'};
  const r=await aa.tool('songban_sync_progress',reportA);assert.equal(r.isError,false);
  const r2=await aa.tool('songban_sync_progress',reportA);assert.equal(r2.data.results[0].duplicate,true);
  step('两个独立MCP进程连接同队；读取统一方向，工具A上传真实请求并验证重复去重');
  const watcher=spawn(process.env.SONGBAN_QA_PYTHON,[bridge,'watch','--interval','1'],{cwd:bb.cwd,env:bb.env,stdio:['ignore','pipe','pipe']});children.push(watcher);let watchOutput='';watcher.stdout.on('data',x=>watchOutput+=x.toString());watcher.stderr.on('data',()=>{});
  const reportB={event_id:'watch-b-'+Date.now(),tool:'通用共享文件监听（协议验收）',summary:'页面已经准备好，仍在等待可调用的登录接口。',status:'blocked',blocker:'等待后端提供实际调用结果',views:[{topic:'登录接口是否可用',position:'前端尚未收到可调用接口，需要先联调'}]};
  fs.writeFileSync(path.join(bb.cwd,'songban-update.json'),JSON.stringify(reportB));
  let snap;for(let i=0;i<24;i++){await new Promise(r=>setTimeout(r,500));snap=await a.request.get(base+'/api/core/teams/'+sid,{headers:authA}).then(r=>r.json());if(snap.reports.length===2&&snap.proposal&&!snap.proposal.stale)break;}
  assert.equal(snap.reports.length,2);assert(snap.proposal&&!snap.proposal.stale);assert.equal(snap.plan_version,0);assert.equal(snap.differences.length,1);assert.match(watchOutput,/sent/);
  step('文件监听自动上传工具B进展；团队发现不同观点并自动生成有来源的待确认草案');
  await pa.locator('[data-tab=overview]').click();await pa.locator('[data-report]').first().waitFor();await pa.getByText('先别急着选一边').waitFor();await pa.waitForTimeout(350);await pa.screenshot({path:path.join(out,'team_sources_and_proposal.png'),fullPage:true});
  pa.once('dialog',d=>d.accept());await pa.locator('#confirm-plan').click();await pa.getByText('v1',{exact:true}).waitFor();
  const ta=await aa.tool('songban_get_my_tasks'),tb=await bb.tool('songban_get_my_tasks');assert.equal(ta.data.plan_version,1);assert.equal(tb.data.plan_version,1);assert.equal(ta.data.tasks.length,1);assert.equal(tb.data.tasks.length,1);assert.notEqual(ta.data.tasks[0].owner_id,tb.data.tasks[0].owner_id);
  let localState;for(let i=0;i<16;i++){await new Promise(r=>setTimeout(r,500));try{localState=JSON.parse(fs.readFileSync(path.join(bb.cwd,'.songban/team-state.json'),'utf8'));}catch{}if(localState?.plan_version===1)break;}assert.equal(localState.plan_version,1);assert.equal(localState.tasks.length,1);
  step('队长确认后，两端MCP读回各自任务；文件监听也自动取回统一方向和本人任务，依赖保留');
  await a.request.put(base+'/api/core/teams/'+sid+'/automation',{headers:authA,data:{enabled:false}});
  const done=await aa.tool('songban_sync_progress',{event_id:'done-'+Date.now(),tool:'MCP客户端A（协议验收）',summary:'已按任务检查方法完成本轮接口验证报告（隔离验收输入）。',status:'reported_done',task_key:'T1',plan_version:1,evidence:['本轮自动化请求返回记录，仍需成员核对']});assert(!done.isError);
  await pa.locator('#refresh').click();await pa.getByText('本人报告完成',{exact:true}).first().waitFor();await pa.waitForTimeout(350);await pa.screenshot({path:path.join(out,'confirmed_tasks_and_progress.png'),fullPage:true});
  await pa.locator('[data-tab=plugin]').click();await pa.locator(`[data-conn="${connections[0].id}"][data-action=revoke]`).click();await pa.getByText('已撤销',{exact:true}).waitFor();assert.equal((await aa.tool('songban_get_my_tasks')).isError,true);
  step('新进展更新已确认任务状态；网页撤销连接后原MCP立即被拒绝');
  const mobile=await browser.newContext({viewport:{width:390,height:844}});const pm=await mobile.newPage();await pm.goto(base+'/core');await pm.evaluate(t=>localStorage.setItem('studio-token',t),tokenA);await pm.reload();await pm.locator('[data-tab=overview]').waitFor();await pm.waitForTimeout(350);await pm.screenshot({path:path.join(out,'mobile_team_space.png'),fullPage:true});assert.equal(await pm.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[]);step('移动端无横向溢出，浏览器无未处理异常');
  fs.writeFileSync(path.join(out,'acceptance.json'),JSON.stringify({date:new Date().toISOString(),model:'明确标注的协议测试替身，非真实模型；实际网页、HTTP、MCP子进程和文件监听均真实执行',steps,errors},null,2));
 }finally{for(const p of children)p.kill('SIGTERM');if(browser)await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
