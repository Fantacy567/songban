/* Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
 * Real browser/components + intercepted synthetic HTTP. No running service or model calls.
 */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {chromium}=require('playwright'),esbuild=require('esbuild');
const root=path.resolve(__dirname,'../../..'),out=path.resolve(process.env.SONGBAN_COURSE_SERIES_EVIDENCE||path.resolve(root,'../outputs/course-series-c03'));
const catalog=JSON.parse(fs.readFileSync(path.join(root,'curriculum/ai-courses/catalog.json'),'utf8'));
const ids=catalog.courses.map(c=>c.id), results=[],errors=[];
let state,page,browser,visit=0;
const session=(mode='learner',learner='child-a')=>({id:`session-${mode}-${learner}`,revision:1,mode,actor_id:'actor',learner_id:mode==='learner'?learner:null,mode_epoch:1,scopes:mode==='learner'?['learning']:[],expires_at:'2030-01-01T00:00:00Z'});
function reset(patch={}){state={session:session(),demo:false,enabled:true,records:{},requests:[],posts:[],unknown:null,conflict:false,failRead:false,broken:false,delay:0,...patch};}
const empty=id=>({course_id:id,course_version:'1',learner_id:state.session.learner_id,revision:0,answers:{understand:'',try:'',reflect:''},activity:{},project_id:null,status:'not_started',updated_at:null});
const key=id=>state.session.learner_id+':'+id;
const b=name=>page.getByRole('button',{name,exact:true});
const course=id=>catalog.courses.find(c=>c.id===id);
const answer=(id,n=0)=>page.getByLabel(course(id).steps[n].title+'：我的记录',{exact:true});
async function practice(){const panel=page.locator('.wb-tools');if(await panel.count() && !await panel.evaluate(e=>e.open))await panel.locator('summary').click();}
async function open(id='ai-tools'){await page.goto('http://127.0.0.1:43229/learning-prep?case='+(++visit)+'#/learn/course?id='+id);await page.locator('.wb-tools').waitFor();await practice();await page.getByRole('heading',{name:course(id).title,exact:true}).waitFor();if(state.session?.mode==='learner')await answer(id).waitFor({state:'visible'});}
async function ready(id='ai-tools'){await open(id);await page.waitForFunction(()=>document.querySelector('.cs-steps fieldset')?.disabled===false);}
async function saved(revision=1){await page.getByText(new RegExp(`已保存本课记录 · 版本 ${revision}`)).waitFor();}
async function check(name,fn){await fn();results.push({name,passed:true});console.log('PASS '+name);}
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 await esbuild.build({stdin:{resolveDir:root,loader:'tsx',contents:`import {mount} from './frontend/learning';import {parseRoute} from './frontend/learning/routes';window.parseRoute=parseRoute;window.handle=mount(document.getElementById('host'),{initialRoute:location.hash,onRouteChange:r=>history.replaceState(null,'',r)});`},bundle:true,format:'iife',jsx:'automatic',outfile:path.join(out,'fixture.js'),define:{'process.env.NODE_ENV':'"development"'}});
 browser=await chromium.launch({headless:true,channel:'msedge'});page=await browser.newPage({viewport:{width:1440,height:1050}});page.setDefaultTimeout(7000);page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const r=route.request(),url=new URL(r.url()),p=url.pathname;
  assert.equal(url.origin,'http://127.0.0.1:43229','No external network');state.requests.push({p,method:r.method()});
  const json=(data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
  if(p==='/learning-prep')return route.fulfill({contentType:'text/html',body:`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta name="songban-platform" content="1"><meta name="songban-creative-studio" content="1">${state.demo?'<meta name="songban-learning-demo-entry" content="1">':''}<link rel="stylesheet" href="/fixture.css"><div id="host"></div><script src="/fixture.js"></script>`});
  if(p==='/fixture.js'||p==='/fixture.css')return route.fulfill({contentType:p.endsWith('js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(out,p.slice(1)))});
  if(p.startsWith('/static/')){const file=path.join(root,p.slice(1));return fs.existsSync(file)&&!state.broken?route.fulfill({contentType:p.endsWith('.svg')?'image/svg+xml':'image/png',body:fs.readFileSync(file)}):route.fulfill({status:404,body:''});}
  if(p==='/api/learning/v2/session')return state.session?json(state.session):json({error:{code:'no_session'}},401);
  if(p==='/api/learning/v2/session-bootstrap')return json({csrf_token:'fixture-csrf',browser_revision:1});
  if(p==='/api/learning/v2/config')return json({learning_enabled:state.enabled,studio_enabled:false,catalog_enabled:true,live_enabled:false,notice:''});
  if(p.startsWith('/api/platform/v1/learning-workbench/'))return p.endsWith('/teachers')?json({version:'1',teachers:[]}):r.method()==='GET'?json({items:[]}):json({error:{code:'fixture_workbench_unavailable'}},503);
  if(r.method()==='POST'){const body=r.postDataJSON();assert.equal(r.headers()['x-csrf-token'],'fixture-csrf');assert.ok(body.request_id);state.posts.push({p,body});}
  if(p==='/api/demo/learning/start'){assert.equal(state.demo,true);state.session=session();return json(state.session);}
  if(p==='/api/learning/v2/sessions/logout'){state.session=null;return json({});}
  if(p==='/api/learning/v2/families')return json({items:[]});
  if(p==='/api/learning/v2/courses')return json({items:[{id:'invitation-course@0.1.0',title:'旧邀请卡练习',state:'published'}],next_cursor:null});
  if(p.endsWith('/home'))return json({learner_id:state.session.learner_id,run_id:null,entitlements:[],allowed_actions:[]});
  if(p==='/api/platform/v1/studio/projects')return json({items:[],next_cursor:null});
  if(p==='/api/platform/v1/companion/sessions')return json({error:{code:'fixture_companion_disabled'}},423);
  if(p==='/api/platform/v1/learning-catalog')return json(catalog);
  if(p.startsWith('/api/platform/v1/learning-catalog/'))return json(course(p.split('/').at(-1)));
  if(p.endsWith('/progress')){
   assert.equal(state.session.mode,'learner');const id=p.split('/').at(-2),k=key(id);let record=state.records[k]||empty(id);
   if(r.method()==='GET'){if(state.failRead)return json({error:{code:'storage_unavailable'}},503);if(state.delay)await new Promise(resolve=>setTimeout(resolve,state.delay));return json(record);}
   const body=r.postDataJSON();
   if(state.conflict){state.conflict=false;state.records[k]={...record,revision:record.revision+1,answers:{...record.answers,understand:'其他窗口已保存'},status:'saved'};return json({error:{code:'revision_conflict'}},409);}
   assert.equal(body.expected_revision,record.revision);
   if(state.unknown!=='uncommitted'){record={...record,revision:record.revision+1,answers:body.answers,activity:body.activity,project_id:body.project_id,status:'saved',updated_at:'2026-11-03T10:00:00+08:00'};state.records[k]=record;}
   if(state.unknown){state.unknown=null;return json({error:{code:'storage_unavailable'}},503);}return json(record);
  }
  if(p==='/api/platform/v1/learning-courses/api/experiment'){
   const body=r.postDataJSON();if(!body.name.trim())return json({error:{code:'invalid_input'}},422);
   return json({kind:'teaching-api',request:{operation:'greet',name:body.name.trim()},response:{message:`你好，${body.name.trim()}！`},notice:'这是固定规则的教学接口，没有调用大模型。'});
  }
  throw Error('Unexpected fixture endpoint '+p);
 });
 try{
  await check('All seven public courses read catalog, offer distinct three steps, no private requests for anonymous',async()=>{
   reset({session:null});for(const id of ids){await open(id);assert.equal(await page.locator('.cs-steps > li').count(),3);assert.equal(await page.locator('.cs-hero img').getAttribute('src'),`/static/platform/illustrations/course-${id}.svg`);assert.equal(await answer(id).isEnabled(),false);assert.equal(await page.locator('input[type=password]').count(),0);}
   assert.equal(state.requests.some(r=>r.p.endsWith('/progress')),false);assert.equal(state.posts.length,0);
  });
  await check('Demo one-click entry returns to same public course even when old studio flag is false',async()=>{
   reset({session:null,demo:true});await open('imagination');await b('开始体验').click();await page.locator('.wb-tools').waitFor();await page.waitForFunction(()=>!document.querySelector('.wb-tools')?.open);await practice();await page.waitForFunction(()=>document.querySelector('.cs-steps fieldset')?.disabled===false);assert.ok(page.url().endsWith('#/learn/course?id=imagination'));assert.equal(state.posts[0].p,'/api/demo/learning/start');
  });
  await check('Manager/staff may read public course but never request learner progress or gain write permission',async()=>{
   for(const mode of ['manager','staff']){reset({session:session(mode)});await open();assert.equal(await answer('ai-tools').isEnabled(),false);assert.equal(state.requests.some(r=>r.p.endsWith('/progress')),false);assert.equal(state.posts.length,0);if(mode==='staff')assert.equal(await b('开始体验').count(),0);}
  });
  await check('Seven activities operate, save exact independent fields, and restore on reload',async()=>{
   reset();
   for(const id of ids){await ready(id);await answer(id).fill('我在 '+id+' 的独立记录');
    if(id==='ai-tools'){for(const name of ['描述目标','请 AI 生成','运行','检查','亲自修改再试'])await b('加入'+name).click();await b('上移检查').click();await b('下移检查').click();await b('检查我的顺序').click();}
    if(id==='imagination'){for(const label of ['为谁做','想解决什么困难','先做一个功能','怎样检查有用'])await page.getByLabel(label,{exact:true}).fill(label+'的样例');}
    if(id==='first-project'){await page.getByLabel('我亲自改的一处',{exact:true}).fill('按钮文字');await page.getByLabel('运行后观察到了什么',{exact:true}).fill('出现问候');}
    if(id==='plugins'){await page.getByLabel('启用重点高亮扩展').check();assert.equal(await page.locator('.cs-highlight').count(),1);await page.getByLabel('关闭时的观察',{exact:true}).fill('普通卡片');await page.getByLabel('开启后的变化',{exact:true}).fill('重点变绿');}
    if(id==='models'){await page.getByRole('combobox',{name:'选择更符合任务的样例',exact:true}).selectOption('sample-a');await page.getByLabel('我的依据与需要核对的地方',{exact:true}).fill('B添加了没提供的信息');}
    if(id==='api'){await page.getByLabel('请求中的名字').fill('小松');await b('发送教学 API 请求').click();await page.getByLabel('API response').waitFor();assert.ok((await page.getByLabel('API request').innerText()).includes('request_id'));}
    if(id==='model-powered-app'){for(const label of ['应用接收什么输入','模型负责哪一小步','应用期待什么输出','失败时怎样回退'])await page.getByLabel(label,{exact:true}).fill(label+'的样例');await b('用固定规则验证方案').click();await page.getByText(/固定规则模拟：收到/).waitFor();}
    await b('保存本课记录').click();await saved();const expected=JSON.stringify(state.records[key(id)]);await page.reload();await page.locator('.wb-tools').waitFor();await practice();await saved();assert.equal(await answer(id).inputValue(),'我在 '+id+' 的独立记录');assert.equal(JSON.stringify(state.records[key(id)]),expected);
    if(id==='plugins')assert.equal(await page.getByLabel('启用重点高亮扩展').isChecked(),true);
   }
   assert.equal(Object.keys(state.records).length,7);assert.equal(state.posts.filter(r=>r.p.endsWith('/progress')).length,7);
   assert.deepEqual(state.records['child-a:ai-tools'].activity.sequence,['describe','generate','run','check','improve']);
  });
  await check('API empty name really POSTs and exposes server 422, valid correction recovers',async()=>{
   reset();await ready('api');await b('发送教学 API 请求').click();await page.getByText(/HTTP 422/).waitFor();assert.equal(state.posts.at(-1).body.name,'');await page.getByLabel('请求中的名字').fill('森林');await b('发送教学 API 请求').click();await page.getByLabel('API response').waitFor();assert.equal(await page.getByLabel('我记录的响应消息',{exact:true}).inputValue(),'你好，森林！');
  });
  await check('Unknown committed save must reconcile, never automatically repeat POST',async()=>{
   reset({unknown:'committed'});await ready();await answer('ai-tools').fill('结果未确认');await b('保存本课记录').click();await b('核对服务器保存结果').waitFor();assert.equal(await b('使用原请求编号重试保存').isEnabled(),false);assert.equal(state.posts.length,1);await b('核对服务器保存结果').click();await saved();assert.equal(state.posts.length,1);
  });
  await check('Unknown uncommitted save retries only after read with same request id',async()=>{
   reset({unknown:'uncommitted'});await ready();await answer('ai-tools').fill('待确认');await b('保存本课记录').click();await b('核对服务器保存结果').click();await page.getByText(/已核对：服务器尚未保存/).waitFor();await b('使用原请求编号重试保存').click();await saved();assert.equal(state.posts[0].body.request_id,state.posts[1].body.request_id);
  });
  await check('Concurrent revision is shown, input kept, overwriting requires explicit selection and save',async()=>{
   reset({conflict:true});await ready();await answer('ai-tools').fill('我的修改');await b('保存本课记录').click();await b('核对服务器保存结果').click();await page.getByRole('region',{name:'服务器记录核对'}).waitFor();assert.equal(await answer('ai-tools').inputValue(),'我的修改');assert.equal(state.posts.length,1);await b('保留我的输入，稍后保存覆盖').click();await b('保存本课记录').click();await saved(2);assert.equal(state.posts[1].body.expected_revision,1);assert.notEqual(state.posts[0].body.request_id,state.posts[1].body.request_id);
  });
  await check('Unsaved navigation is guarded; save-and-leave works; first-project returns from real studio component',async()=>{
   reset();await ready('first-project');await page.getByLabel('我亲自改的一处',{exact:true}).fill('保留这次修改');await b('进入创作工作台').click();await page.getByRole('dialog').waitFor();await b('留在这里').click();assert.ok(page.url().includes('id=first-project'));await b('进入创作工作台').click();await b('保存后离开').click();await page.getByLabel('我的小想法').waitFor();await b('返回刚才的课程').click();await page.locator('.wb-tools').waitFor();await practice();await saved();assert.equal(await page.getByLabel('我亲自改的一处',{exact:true}).inputValue(),'保留这次修改');
  });
  await check('Read errors recover without blind writes; paused learning disables writes',async()=>{
   reset({failRead:true});await open();await b('重新读取课程记录').waitFor();assert.equal(await answer('ai-tools').isEnabled(),false);state.failRead=false;await b('重新读取课程记录').click();await page.waitForFunction(()=>document.querySelector('.cs-steps fieldset')?.disabled===false);reset({enabled:false});await open();assert.equal(await answer('ai-tools').isEnabled(),false);assert.equal(await b('保存本课记录').isEnabled(),false);
  });
  await check('Identity boundary removes current private draft and isolates second learner',async()=>{
   reset();await ready();await answer('ai-tools').fill('孩子A未保存私密草稿');state.session=session('learner','child-b');await page.evaluate(()=>window.handle.revalidate());await page.locator('.wb-tools').waitFor();await practice();await page.waitForFunction(()=>document.querySelector('.cs-steps fieldset')?.disabled===false);assert.equal(await answer('ai-tools').inputValue(),'');assert.equal(await page.getByText('孩子A未保存私密草稿').count(),0);assert.equal(state.posts.length,0);
  });
  await check('Delayed old-identity progress is fenced and never rendered after session changes',async()=>{
   reset({delay:350});state.records['child-a:ai-tools']={...empty('ai-tools'),revision:1,status:'saved',answers:{understand:'迟到的孩子A记录',try:'',reflect:''}};
   await open();await page.waitForFunction(()=>document.querySelector('.cs-steps fieldset')?.disabled===true);
   state.session=session('learner','child-b');state.delay=0;await page.evaluate(()=>window.handle.revalidate());await page.locator('.wb-tools').waitFor();await practice();await page.waitForFunction(()=>document.querySelector('.cs-steps fieldset')?.disabled===false);
   await page.waitForTimeout(450);assert.equal(await answer('ai-tools').inputValue(),'');assert.equal(state.posts.length,0);
  });
  await check('All seven course activities and stable labels fit mobile width; dirty refresh emits beforeunload protection',async()=>{
   reset();await page.setViewportSize({width:390,height:844});
   for(const id of ids){await ready(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id);assert.equal(await page.locator('.cs-activity [role=group]').count(),1);await answer(id).fill('手机上的记录');assert.equal(await answer(id).getAttribute('aria-label'),course(id).steps[0].title+'：我的记录');assert.equal(await page.evaluate(()=>{const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented;}),true);await page.screenshot({path:path.join(out,`course-${id}-390.png`),fullPage:true});}
   await page.setViewportSize({width:1440,height:1050});
  });
  await check('Hall groups actual catalog 4+3 with seven images/routes, keeps legacy exercises, fits 390px',async()=>{
   reset({session:null});await page.goto('http://127.0.0.1:43229/learning-prep#/learn/courses');await b('开始这门课').first().waitFor();assert.equal(await page.locator('.ph-stage').count(),2);assert.equal(await page.locator('.ph-stage').nth(0).locator('.ph-course-card').count(),4);assert.equal(await page.locator('.ph-stage').nth(1).locator('.ph-course-card').count(),3);
   assert.equal(new Set(await page.locator('.ph-course-card img').evaluateAll(nodes=>nodes.map(n=>n.src))).size,7);for(const id of ids){await page.locator(`[data-course-version="${id}"] button`).click();await page.locator('.wb-tools').waitFor();await practice();await page.getByRole('heading',{name:course(id).title,exact:true}).waitFor();assert.ok(page.url().endsWith('id='+id));await b('返回 AI 教学大厅').last().click();await b('开始这门课').first().waitFor();}
   const toolCards=await page.locator('.ph-stage').nth(0).locator('.ph-course-card').all();const toolBoxes=await Promise.all(toolCards.map(c=>c.boundingBox()));assert.equal(toolBoxes.length,4);assert.ok(toolBoxes.every(box=>Math.abs(box.y-toolBoxes[0].y)<1),'1440px: four tools cards must share one row');for(let i=1;i<4;i++)assert.ok(toolBoxes[i].x>toolBoxes[i-1].x+toolBoxes[i-1].width,'Four separate columns');
   const advancedBoxes=await Promise.all((await page.locator('.ph-stage').nth(1).locator('.ph-course-card').all()).map(c=>c.boundingBox()));assert.ok(advancedBoxes.every(box=>Math.abs(box.width-toolBoxes[0].width)<1),'Advanced cards must preserve four-column width');assert.ok(advancedBoxes.every(box=>Math.abs(box.y-advancedBoxes[0].y)<1));
   const sizes=await b('开始这门课').evaluateAll(nodes=>nodes.map(n=>n.getBoundingClientRect().height));assert.ok(sizes.every(h=>h>=44));
   await page.screenshot({path:path.join(out,'hall-1440.png'),fullPage:true});await page.setViewportSize({width:768,height:1000});const tablet=await Promise.all(toolCards.map(c=>c.boundingBox()));assert.ok(tablet[1].y>tablet[0].y,'768px with the expanded session sidebar: one column inside the narrow hall container');await page.screenshot({path:path.join(out,'hall-768.png'),fullPage:true});
   await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));const mobile=await Promise.all(toolCards.map(c=>c.boundingBox()));assert.ok(mobile[1].y>mobile[0].y&&Math.abs(mobile[1].x-mobile[0].x)<1,'390px: one column');await page.screenshot({path:path.join(out,'hall-390.png'),fullPage:true});
   reset();await ready('plugins');assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:path.join(out,'course-plugins-390.png'),fullPage:true});
   await b('返回 AI 教学大厅').last().click();await page.getByRole('heading',{name:'以前的练习',exact:true}).waitFor();await b('打开以前的练习').waitFor();await b('打开作品集').waitFor();
  });
  await check('Broken illustration has accessible text fallback and still usable course',async()=>{reset({broken:true});await ready();await page.getByRole('img',{name:/教学插画暂未加载/}).waitFor();assert.equal(await answer('ai-tools').isEnabled(),true);});
  await check('Parser, host whitelist and login-return agree for all valid ids and reject query injection/duplicates',async()=>{
   const host=fs.readFileSync(path.join(root,'static/learning-host.js'),'utf8'),start=host.indexOf('  const validRoute ='),end=host.indexOf('  let handle,');
   const hostValid=r=>vm.runInNewContext(host.slice(start,end)+';validRoute(route)',{URLSearchParams,route:r});
   const songban=fs.readFileSync(path.join(root,'static/songban.js'),'utf8'),fn=songban.slice(songban.indexOf('function learningLoginReturn()'),songban.indexOf('function isDemoExperience()'));
   const loginValid=r=>vm.runInNewContext(fn+';learningLoginReturn()',{URLSearchParams,platformEnabled:true,isDemoExperience:()=>false,location:{hash:'#/login?next='+encodeURIComponent('/learning-prep'+r)}});
   for(const id of ids){const r='#/learn/course?id='+id;assert.ok(await page.evaluate(r=>window.parseRoute(r),r));assert.equal(hostValid(r),true);assert.equal(loginValid(r),'/learning-prep'+r);}
   for(const r of ['#/learn/course','#/learn/course?id=other','#/learn/course?id=api&id=plugins','#/learn/course?id=api&role=staff','#/learn/course?id=api?x=1','#/learn/course?id=api%26role%3Dstaff','#/learn/course?id=%2f%2fevil','#/learn/course?id=api#evil','#/learn/course?id=api&%69d=plugins']){assert.equal(await page.evaluate(r=>window.parseRoute(r),r),null);assert.equal(hostValid(r),false);assert.equal(loginValid(r),'');}
  });
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({scope:'Real browser with synthetic intercepted HTTP, not live server integration',results,errors},null,2));console.log(JSON.stringify({passed:results.length,out}));
 }catch(e){await page.screenshot({path:path.join(out,'failure.png'),fullPage:true});fs.writeFileSync(path.join(out,'failure.txt'),await page.locator('body').innerText());throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
