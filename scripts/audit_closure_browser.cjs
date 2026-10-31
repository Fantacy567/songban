// Reproduce gaps without modifying product code; run only against the isolated fixture server.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const base=process.env.SONGBAN_QA_URL||'http://127.0.0.1:8894';
const output=path.resolve(process.env.SONGBAN_AUDIT_OUTPUT||'.browser-cache/materials/fixes-20261031');
const evidence=output;
async function api(url,token,body,method){const r=await fetch(base+url,{method:method||(body?'POST':'GET'),headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},...(body?{body:JSON.stringify(body)}:{})});const data=await r.json();assert(r.ok,JSON.stringify(data));return data;}
(async()=>{
 const marker=await api('/api/audit-fixture','');
 assert(marker.isolated_audit&&marker.sms==='fixture','Refusing to test registration without the isolated SMS fixture.');
 fs.mkdirSync(output,{recursive:true});
 const phone='187'+String(Date.now()).slice(-8),code=await api('/api/studio/codes','',{phone});
 assert(code.code,'This audit requires the explicitly isolated SMS fixture server.');
 const account=await api('/api/studio/register','',{phone,code:code.code,password:'audit-only-password',name:'闭环界面核对',profile:'仅合成测试',skills:'核对'}),token=account.token;
 const team=await api('/api/core/teams',token,{name:'界面缺口复现小队'});
 let space=await api('/api/materials/space',token),url='/api/materials/spaces/'+encodeURIComponent(space.id);
 const source=(await api(url+'/sources',token,{request_id:crypto.randomUUID(),kind:'text',name:'共享规则测试',content:'必须提交作品链接。',nature:'sample'})).source;
 space=await api('/api/materials/space',token);await api(url+'/sources/'+source.id+'/parse',token,{expected_revision:space.revision});
 space=await api('/api/materials/space',token);await api(url+'/generate',token,{expected_revision:space.revision,request_id:crypto.randomUUID()});
 space=await api('/api/materials/space',token);
 await api(url+'/drafts',token,{expected_revision:space.revision,request_id:crypto.randomUUID(),team_id:team.id,item_ids:[space.result.items[0].id],kind:'direction',share_sources:true});
 const shared=await api('/api/materials/space?team_id='+team.id,token);
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(({token,team})=>{localStorage.setItem('studio-token',token);localStorage.setItem('studio-squad',team);},{token,team:team.id});
  await page.goto(base+'/#/materials');await page.locator('#material-generate').waitFor();
  const result={shared_draft_visibility:{api_draft_count:shared.drafts.length,api_has_result:!!shared.result.items,visible_draft_buttons:await page.locator('[data-open-draft]').count(),visible_draft_heading:await page.getByRole('heading',{name:'已保存的团队草稿'}).count()}};
  assert.equal(result.shared_draft_visibility.visible_draft_buttons,1);assert.equal(result.shared_draft_visibility.visible_draft_heading,1);
  await page.locator('details:has([data-open-draft]) > summary').click();
  await page.screenshot({path:path.join(output,'shared-draft-visible.png'),fullPage:true});
  await page.locator('[data-open-draft]').click();await page.locator('#material-use-draft').click();await page.locator('#direction-form').waitFor();assert((await page.locator('#direction-form [name=rules]').inputValue()).includes(shared.drafts[0].body.text));result.shared_draft_visibility.continue_to_direction=true;await page.locator('#direction-form [name=goal]').fill('核对共享草稿接续');const saved=page.waitForResponse(r=>r.url().endsWith('/direction')&&r.request().method()==='PUT');await page.locator('#direction-form button[type=submit]').click();assert.equal((await saved).status(),200);
  const events=await api('/api/learning/v1/events',token);await page.goto(base+'/#/event?id='+events.items[1].id);await page.locator('#material-text').waitFor();
  await page.getByRole('link',{name:'创建或加入小队 →',exact:true}).click();await page.getByRole('heading',{name:'我们的创作小队'}).waitFor();
  result.event_team_transition={selected_event:events.items[1].id,keeps_previous_team:await page.evaluate(team=>state.team===team,team.id),create_team_forms:await page.locator('#create-team').count(),route:await page.evaluate(()=>location.hash)};
  await page.screenshot({path:path.join(output,'new-event-existing-team.png'),fullPage:true});
  await page.locator('#new-team').click();await page.locator('#create-team').waitFor();
  result.event_team_transition.can_open_new_team_form=true;
  result.event_team_transition.note='Existing-team landing is not a hard block; a second click opens creation. Event linkage is not established.';
  // Complete a two-task plan to test the final next-step navigation in the actual UI.
  let snap=await api('/api/core/teams/'+team.id,token);
  await api('/api/core/teams/'+team.id+'/direction',token,{goal:'检验最终跳转',rules:'合成规则',expected_revision:snap.revision},'PUT');
  const phoneB='186'+String(Date.now()).slice(-8),codeB=await api('/api/studio/codes','',{phone:phoneB});
  const other=await api('/api/studio/register','',{phone:phoneB,code:codeB.code,password:'audit-only-password',name:'合成检查队友',profile:'仅测试',skills:'核验'});
  await api('/api/core/join',other.token,{code:team.code});const tb='/api/core/teams/'+team.id;
  const proposal=await api(tb+'/review',token,{});await api(tb+'/proposals/'+proposal.proposal_id+'/confirm',token,{expected_revision:proposal.base_revision});
  for(const [task,owner,reviewer]of [['T1',token,other.token],['T2',other.token,token]]){
   await api(tb+'/reports',owner,{event_id:crypto.randomUUID(),task_key:task,plan_version:1,status:'reported_done',summary:'合成完成记录',evidence:['合成核验依据']});snap=await api(tb,token);const row=snap.active_plan.tasks.find(t=>t.key===task);
   await api(tb+'/tasks/'+task+'/check',reviewer,{expected_revision:snap.revision,plan_version:1,report_id:row.latest_report_id,verdict:'accepted',note:'核对合成测试输入'});
  }
  await page.goto(base+'/#/work');await page.reload();await page.locator('#confirmed-tasks').waitFor();
  assert(await page.evaluate(()=>state.data.workflow.all_handoffs_checked));
  const before=await page.evaluate(()=>({route:location.hash,next:state.data.workflow.next_action}));
  await page.locator('#next-action').click();
  result.delivery_navigation={before,after_route:await page.evaluate(()=>location.hash)};assert.equal(result.delivery_navigation.after_route,'#/delivery');assert.equal(before.next.page,'delivery');
  await page.screenshot({path:path.join(output,'delivery-next-action.png'),fullPage:true});
  await page.goto(base+'/#/delivery');await page.locator('#content').waitFor();result.delivery_controls={file_upload_inputs:await page.locator('#content input[type=file]').count(),forms:await page.locator('#content form').count()};
  await page.goto(base+'/#/review');await page.locator('#reflection-form').waitFor();result.review_controls={form:'reflection-form',saved_as:'POST /api/core/teams/{id}/reports'};
  result.browser_errors=errors;fs.mkdirSync(evidence,{recursive:true});fs.writeFileSync(path.join(evidence,'browser-gaps.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
