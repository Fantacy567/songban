/* Real local HTTP + both MCP transports + two independent browser identities.
   Model output is an explicit fixture; no Codex/Cursor/WorkBuddy GUI claims. */
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),net=require('node:net');
const {spawn,spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const python=process.env.SONGBAN_QA_PYTHON||path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const outputRoot=process.env.SONGBAN_QA_OUTPUT||path.join(root,'.browser-cache','topics');fs.mkdirSync(outputRoot,{recursive:true});
const folder=fs.mkdtempSync(path.join(outputRoot,'run-'));
const errors=[];let server,browser;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function port(){return new Promise(resolve=>{const socket=net.createServer().listen(0,'127.0.0.1',()=>{const p=socket.address().port;socket.close(()=>resolve(p));});});}
function callMcp(who,args){
  const native=who==='a';
  const script=path.join(root,'plugins',native?'songban-native/server.py':'songban-team/bridge.py');
  const binding=path.join(folder,'binding-'+who+'.json');
  const rpc={jsonrpc:'2.0',id:1,method:'tools/call',params:{name:'songban_share_topic_turn',arguments:args}};
  const env={...process.env,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8',SONGBAN_CONFIG:binding};
  delete env.SONGBAN_TOKEN;delete env.SONGBAN_URL;delete env.SONGBAN_TEAM_ID;
  const run=spawnSync(python,[script,...(native?['--binding',binding]:['mcp'])],{cwd:folder,env,windowsHide:true,input:JSON.stringify(rpc)+'\n',encoding:'utf8',timeout:15000});
  assert.equal(run.status,0,run.stderr);return JSON.parse(run.stdout).result;
}
(async()=>{try{
  const p=await port(),base='http://127.0.0.1:'+p;
  server=spawn(python,['scripts/qa_topic_server.py',folder,String(p)],{cwd:root,windowsHide:true,env:{...process.env,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'}});
  let serverLog='';server.stderr.on('data',d=>serverLog+=d.toString());
  let started=false;for(let i=0;i<100;i++){try{if((await fetch(base+'/health')).ok){started=true;break;}}catch{}await pause(100);}
  assert(started,serverLog);
  const fixture=JSON.parse(fs.readFileSync(path.join(folder,'fixture.json'),'utf8'));
  const sid=fixture.team.id;
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{})});
  const pages={};
  for(const user of fixture.users){
    const context=await browser.newContext({viewport:{width:user.id==='a'?1440:390,height:1000}});
    await context.addInitScript(({token,sid})=>{localStorage.setItem('studio-token',token);localStorage.setItem('studio-squad',sid);}, {token:user.token,sid});
    const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('dialog',dialog=>dialog.accept());
    pages[user.id]=page;await page.goto(base+'/#/direction');
  }
  const a=pages.a,b=pages.b;
  await a.locator('#topic-track').fill('校园 AI 应用');
  await a.locator('#topic-start [name=rules]').fill('必须有可操作的原型');
  await a.locator('#topic-start [name=rubric]').fill('实用性、创新性与实现质量');
  await a.getByRole('button',{name:'开启选题讨论',exact:true}).click();
  await a.getByTestId('topic-confirmed').filter({hasText:'0/2'}).waitFor();
  await b.reload();await b.getByTestId('topic-confirmed').waitFor();
  const getRound=async()=>fetch(base+'/api/core/teams/'+sid+'/topic-selection',{headers:{Authorization:'Bearer '+fixture.users[0].token}}).then(r=>r.json()).then(r=>r.round);
  let round=await getRound();
  const turns={};
  for(const who of 'ab'){
    turns[who]={round_id:round.id,event_id:'browser-topic-'+who,selected:true,topic_title:who==='a'?'校园排队助手':'校园互助地图',user_message:'这是我的选题想法 <script>window.topicXss=true</script>',assistant_message:'先访谈真实用户，再做最小原型。\n未知优势需要验证，不能虚构。',model_name:'合成测试回复 · 非真实模型'};
    assert.equal(callMcp(who,{...turns[who],selected:false}).isError,true);
    const answer=callMcp(who,turns[who]);assert.equal(answer.isError,false,JSON.stringify(answer));
    const receipt=JSON.parse(answer.content[0].text);assert(receipt.synced&&receipt.note_id);
    assert.equal(JSON.parse(callMcp(who,turns[who]).content[0].text).duplicate,true);
  }
  await a.reload();await a.locator('.topic-source').first().click();
  assert.equal(await a.evaluate(()=>!!window.topicXss),false);
  await a.getByRole('button',{name:'确认进入排名',exact:true}).click();
  await a.getByTestId('topic-confirmed').filter({hasText:'1/2'}).waitFor();
  await b.reload();await b.getByRole('button',{name:'确认进入排名',exact:true}).click();
  await b.locator('.topic-ranking').waitFor({timeout:20000});await a.reload();await a.locator('.topic-ranking').waitFor();
  round=await getRound();assert.equal(round.ranking.items.length,2);
  assert.equal(callMcp('a',{...turns.a,event_id:'too-late-upload'}).isError,true);
  const [first,second]=round.eligible;
  await a.locator('[data-candidate="'+first+'"]').click();
  await a.getByTestId('topic-voted').filter({hasText:'1/2'}).waitFor();
  await b.reload();await b.locator('[data-candidate="'+second+'"]').click();
  await b.getByTestId('topic-voted').filter({hasText:'第 2 轮'}).waitFor();
  await a.reload();await a.locator('[data-candidate="'+first+'"]').click();
  await a.getByTestId('topic-voted').filter({hasText:'1/2'}).waitFor();
  await b.reload();await b.locator('[data-candidate="'+first+'"]').click();
  await b.getByRole('heading',{name:'全员已投票，等待队长确认'}).waitFor();
  assert.equal(await b.locator('[data-topic-action=select]').count(),0);
  await a.reload();await a.locator('[data-topic-action=select]').click();
  await a.getByRole('heading',{name:'主方向已确认',exact:true}).waitFor();
  await a.screenshot({path:path.join(folder,'selected-desktop.png'),fullPage:true});
  await b.reload();await b.getByRole('heading',{name:'主方向已确认',exact:true}).waitFor();
  assert(await b.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Mobile page overflow');
  await b.screenshot({path:path.join(folder,'selected-mobile.png'),fullPage:true});
  await a.getByRole('link',{name:'去生成任务清单',exact:true}).click();
  await a.locator('#review').click();await a.locator('#confirm-plan').waitFor();
  await a.locator('#confirm-plan').click();await a.locator('[data-claim-task=T1]').waitFor();
  await b.goto(base+'/#/tasks');await b.locator('[data-claim-task=T1]').click();
  await b.waitForFunction(()=>state.data?.active_plan.tasks[0]?.owner_id==='b');
  assert.equal(await b.locator('[data-claim-task=T1]').count(),0);
  const snap=await fetch(base+'/api/core/teams/'+sid,{headers:{Authorization:'Bearer '+fixture.users[1].token}}).then(r=>r.json());
  assert.equal(snap.workflow.my_tasks[0].key,'T1');
  await a.goto(base+'/#/materials');await a.locator('#material-generate').waitFor();
  assert.equal(await a.locator('.material-result-heading').count(),0);
  assert.equal(await a.getByText('演示资料要点',{exact:true}).count(),0);
  assert.equal(await a.getByText('【模拟整理】活动要求、团队想法和交付清单已经放在一起。',{exact:true}).count(),0);
  assert.equal(await a.getByText('本次变化：',{exact:false}).count(),0);
  await a.locator('#competition-info-title').waitFor();
  assert.equal(await a.locator('[data-competition-field]').count(),8);
  assert.equal(await a.locator('.material-groups,.material-item,.material-edit,[data-select]').count(),0);
  assert.equal(await a.locator('.material-source-row').count(),1);
  await a.screenshot({path:path.join(folder,'materials-cleaned.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(folder,'acceptance.json'),JSON.stringify({passed:true,users:2,mcp_transports:['native','portable'],real_client_gui_tested:false,paid_model_called:false,checks:['explicit selection','full visible turn upload','deduplication','XSS escaping','all-ready gate','ranking','secret incomplete tallies','tie revote','captain selection','task publish and self claim','mobile overflow','screenshot mock summary, changes and demo cards removed'],errors},null,2));
  console.log('PASS: full topic-selection browser + MCP flow. Artifacts: '+folder);
}finally{if(browser)await browser.close();if(server)server.kill();}})().catch(e=>{console.error(e.stack);process.exitCode=1;});
