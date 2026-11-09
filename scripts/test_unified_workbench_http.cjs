/* Actual HTTP and SQLite, fictional disposable demo only; no API interception. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const origin=process.env.SONGBAN_WORKBENCH_TEST_ORIGIN;
assert.equal(process.env.SONGBAN_WORKBENCH_SYNTHETIC,'1');
const endpoint=new URL(origin);assert.equal(endpoint.hostname,'127.0.0.1');assert.equal(endpoint.protocol,'http:');
assert.ok(!['8894','8895'].includes(endpoint.port));
const out=path.resolve(process.env.SONGBAN_WORKBENCH_TEST_OUTPUT||'../outputs/workbench-http');
const results=[],errors=[],external=[],writes=[];let browser,page;
async function check(name,fn){await fn();results.push({name,passed:true});console.log('PASS '+name);}
(async()=>{fs.mkdirSync(out,{recursive:true});try{
 browser=await chromium.launch({headless:true,channel:'msedge'});
 const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
 page=await context.newPage();page.setDefaultTimeout(20000);
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{const u=new URL(r.url());if(['http:','https:'].includes(u.protocol)&&u.origin!==origin)external.push(u.href);if(!['GET','HEAD'].includes(r.method()))writes.push({path:u.pathname,body:r.postDataJSON()});});
 const button=name=>page.getByRole('button',{name,exact:true});
 const field=name=>page.getByLabel(name,{exact:true});
 const read=async p=>{const r=await context.request.get(origin+p);assert.equal(r.status(),200,p);return r.json();};
 const course=id=>origin+'/learning-prep#/learn/course?id='+id;
 const message=()=>field('告诉老师你想试什么，也可以随时改主意');
 const wb='/api/platform/v1/learning-workbench';
 const teachers=(await read(wb+'/teachers')).teachers;
 const snapshot=async()=>{const sessions=(await read(wb+'/sessions')).items;const item=sessions.find(s=>s.course_id==='ai-tools');assert.ok(item);return read(wb+'/sessions/'+item.id);};
 const save=async(content)=>{await field('成果内容').fill(content);const response=page.waitForResponse(r=>r.url().endsWith('/artifacts')&&r.request().method()==='POST');await button('保存成果版本').click();assert.equal((await response).status(),200);await page.getByText('当前成果版本已保存',{exact:true}).waitFor();};
 await check('public-seven-teachers-and-direct-start-without-interview',async()=>{
   assert.equal(teachers.length,7);assert.equal(new Set(teachers.map(t=>t.name)).size,7);assert.ok(teachers.every(t=>!t.system_prompt));
   await page.goto(course('ai-tools'));await button('开始体验').click();await message().waitFor();
   assert.equal(await page.locator('input[type=password]').count(),0);assert.equal(await field('回应方式').inputValue(),'mock');
 });
 await check('real-worker-response-and-editable-artifact',async()=>{
   await message().fill('我第一次用AI，请给一只会潜水的小狐狸写三行角色介绍：名字、爱好、本领。');
   await button('发送给老师').click();await button('编辑这份成果').waitFor();
   const session=await snapshot();assert.equal(session.messages.length,1);assert.equal(session.messages[0].status,'succeeded');assert.equal(session.messages[0].mode,'mock');
   await button('编辑这份成果').click();assert.ok((await field('成果内容').inputValue()).length>10);
 });
 let firstVersion;
 await check('two-immutable-versions-and-restore-survive-refresh',async()=>{
   await field('成果标题').fill('我的潜水狐狸');await save('名字：泡泡狐\n爱好：收集会唱歌的小贝壳\n本领：潜水帮助迷路小鱼');firstVersion=(await snapshot()).selected_artifact_id;
   await save('名字：泡泡狐\n爱好：收集会唱歌的小贝壳\n本领：给海星讲笑话');
   await page.getByText('已保存的版本（2）',{exact:true}).click();await button('选回版本 1').click();
   await page.waitForFunction(()=>document.querySelector('[aria-label="成果内容"]')?.value.includes('迷路小鱼'));
   assert.equal((await snapshot()).selected_artifact_id,firstVersion);
   await page.reload();await message().waitFor();assert.match(await field('成果内容').inputValue(),/迷路小鱼/);
 });
 await check('draft-not-public-until-child-edits-and-confirms',async()=>{
   await button('生成探索记录草稿').click();await field('记录标题').waitFor();assert.equal((await read(wb+'/records')).items.length,0);
   await field('记录标题').fill('我第一次指挥AI修改角色');await field('这次我试了什么').fill('我让AI写一只潜水狐狸，自己改过本领，又选回了第一个版本。我发现保留名字、只改一处，结果更容易检查。');await field('下次想试').fill('让狐狸住进会飞的学校');
   await button('确认记录，存入作品集').click();await page.getByText('已确认保存，可从作品集继续这次探索。',{exact:true}).waitFor();
   const records=(await read(wb+'/records')).items;assert.equal(records.length,1);assert.equal(records[0].artifact_version_id,firstVersion);
   await button('打开作品集').click();await page.getByRole('heading',{name:'我第一次指挥AI修改角色',exact:true}).waitFor();
   await page.reload();await button('继续这次探索').click();await message().waitFor();assert.equal((await snapshot()).messages.length,1);
 });
 await check('all-seven-teachers-recover-their-own-course',async()=>{
   for(const t of teachers){await page.goto(course(t.course_id));await message().waitFor();await page.getByRole('heading',{name:t.name,exact:true}).waitFor();assert.equal(await page.locator('.wb-turn').count(),t.course_id==='ai-tools'?1:0);}
   assert.equal((await read(wb+'/sessions')).items.length,7);
 });
 await check('desktop-workspace-and-mobile-switch-fit-screen',async()=>{
   await page.goto(course('ai-tools'));await message().waitFor();
   const rail=await page.locator('.lp-platform-sidebar').boundingBox(), area=await page.locator('.wb-layout').boundingBox();assert.equal(Math.round(rail.width),240);assert.ok(area.x>=rail.width);
   await page.screenshot({path:path.join(out,'workbench-desktop.png'),fullPage:true});
   await page.setViewportSize({width:390,height:844});await button('成果与记录').click();await field('成果标题').waitFor();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await page.screenshot({path:path.join(out,'workbench-mobile-result.png'),fullPage:true});await button('对话').click();await message().waitFor();
   const chatBox=await page.locator('.wb-messages').boundingBox();assert.ok(chatBox.height>=180,'Mobile conversation needs readable space, not just a non-overflowing layout');
   await page.screenshot({path:path.join(out,'workbench-mobile-chat.png'),fullPage:true});
 });
 await check('hall-four-cards-and-existing-hackathon-route',async()=>{
   await page.setViewportSize({width:1440,height:1000});await page.locator('.wb-heading').getByRole('button',{name:'返回 AI 教学大厅',exact:true}).click();await page.locator('[data-course-version="model-powered-app"]').waitFor();
   // A signed-in learner may also see an earlier saved course alongside the seven new courses.
   for(const t of teachers)assert.equal(await page.locator(`[data-course-version="${t.course_id}"]`).count(),1);
   const boxes=await Promise.all(['ai-tools','imagination','first-project','plugins'].map(id=>page.locator(`[data-course-version="${id}"]`).boundingBox()));assert.ok(boxes.every(b=>Math.abs(b.y-boxes[0].y)<2));
   await page.screenshot({path:path.join(out,'courses-desktop.png'),fullPage:true});
   await button('黑客松教学大厅').click();await page.getByRole('heading',{name:'认识黑客松',exact:true}).waitFor();assert.equal(await page.locator('.ph-hackathon-grid article').count(),2);
   await page.goto(origin+'/#/events');await page.getByRole('heading',{name:'继续你的学习',exact:true}).waitFor();
   // The learning identity must not silently become an authorized team identity.
   const teamContext=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
   try {const team=await teamContext.newPage();team.on('pageerror',e=>errors.push(e.message));await team.goto(origin+'/#/events');await team.getByRole('heading',{name:'这几场，也许适合你。',exact:true}).waitFor();assert.equal(await team.locator('.sb-workbench-shell .sp-primary-nav a').count(),3);await team.screenshot({path:path.join(out,'legacy-competition.png'),fullPage:true});}finally{await teamContext.close();}
 });
 await check('no-browser-errors-no-external-dispatch-and-no-private-leak-after-logout',async()=>{
   await page.goto(course('ai-tools'));await message().waitFor();await page.locator('.lp-account-menu > summary').click();
   const loggedOut=page.waitForResponse(r=>r.url().endsWith('/sessions/logout')&&r.request().method()==='POST');
   await button('退出当前身份').click();assert.equal((await loggedOut).status(),200);await button('开始体验').waitFor();
   const r=await context.request.get(origin+wb+'/sessions');assert.equal(r.status(),401);assert.equal(await page.locator('.wb-turn').count(),0);
   assert.deepEqual(errors,[]);assert.deepEqual(external,[]);assert.ok(writes.filter(w=>w.path.endsWith('/messages')).every(w=>w.body.mode==='mock'));
 });
 console.log(JSON.stringify({passed:results.length,out}));
}catch(e){await page?.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});fs.writeFileSync(path.join(out,'failure.txt'),await page?.locator('body').innerText().catch(()=>''));throw e;}
finally{fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({origin,results,errors,external,scope:'actual HTTP, synthetic identities and mock teachers'},null,2));await browser?.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
