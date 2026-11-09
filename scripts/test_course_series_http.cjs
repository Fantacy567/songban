/* Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
 * Actual HTTP/UI acceptance on an isolated fictional demo, never paid providers.
 * Legacy activities remain explicit tools inside the course teacher workbench.
 */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const origin=process.env.SONGBAN_COURSE_TEST_ORIGIN;
assert.equal(process.env.SONGBAN_COURSE_SYNTHETIC,'1');
assert.ok(origin,'Set isolated synthetic fixture origin');
const url=new URL(origin);assert.ok(['127.0.0.1','localhost'].includes(url.hostname));assert.ok(!['8894','8895'].includes(url.port));
const out=path.resolve(process.env.SONGBAN_COURSE_TEST_OUTPUT||'../outputs/course-series-http-'+Date.now());
const results=[],errors=[],external=[],writes=[];let browser,page;
async function check(name,fn){await fn();results.push({name,passed:true});console.log('PASS '+name);}
(async()=>{fs.mkdirSync(out,{recursive:true});try{
 browser=await chromium.launch({headless:true,channel:'msedge'});
 const context=await browser.newContext({viewport:{width:1440,height:960},reducedMotion:'reduce'});
 page=await context.newPage();page.setDefaultTimeout(20000);
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{const u=new URL(r.url());if(['http:','https:'].includes(u.protocol)&&u.origin!==origin)external.push(u.href);if(!['GET','HEAD'].includes(r.method()))writes.push(u.pathname);});
 const button=name=>(name==='返回 AI 教学大厅'?page.locator('.cs-page'):page).getByRole('button',{name,exact:true});
 const read=async p=>{const r=await context.request.get(origin+p);assert.equal(r.status(),200,p);return r.json();};
 const catalog=await read('/api/platform/v1/learning-catalog');assert.equal(catalog.courses.length,7);
 const practice=async c=>{
   const panel=page.locator('.wb-tools');await panel.waitFor();
   if(!await panel.evaluate(element=>element.open))await panel.locator('summary').click();
   await page.locator('.cs-page').getByRole('heading',{name:c.title,exact:true}).waitFor();
 };
 const open=async c=>{await page.goto(origin+'/learning-prep#/learn/course?id='+c.id);await page.getByRole('region',{name:'课程老师工作台',exact:true}).waitFor();await practice(c);};
 const field=(c,i)=>page.getByLabel(c.steps[i].title+'：我的记录');
 const waitEditable=async c=>{
   // Identity entry remounts the workbench, so reopen its optional tools only after the private view is ready.
   await page.getByRole('log',{name:'对话内容',exact:true}).waitFor();await practice(c);
   await field(c,0).waitFor();await page.waitForFunction(()=>document.querySelector('.cs-steps fieldset')?.disabled===false);
 };
 await check('public-two-chapters-seven-unique-loaded-covers',async()=>{
   await page.goto(origin+'/learning-prep#/learn/courses');await page.locator('[data-course-version="model-powered-app"]').waitFor();
   assert.equal(await page.locator('.ph-course-card').count(),7);
   for(const name of ['AI 工具篇','进阶篇'])await page.getByRole('heading',{name,exact:true}).waitFor();
   const srcs=[];for(const c of catalog.courses){const img=page.locator(`[data-course-version="${c.id}"] img`);await img.scrollIntoViewIfNeeded();await img.evaluate(img=>img.decode());srcs.push(await img.getAttribute('src'));assert.ok(await img.getAttribute('alt'));}
   assert.equal(new Set(srcs).size,7);
   const boxes=await Promise.all(catalog.courses.slice(0,4).map(c=>page.locator(`[data-course-version="${c.id}"]`).boundingBox()));
   assert.ok(boxes.every(b=>Math.abs(b.y-boxes[0].y)<2),'The four tool courses must share one desktop row');
   assert.ok(boxes.every(b=>b.width<310),'Course cards must stay compact');
   await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,'hall-desktop.png'),fullPage:true});
 });
 await check('each-card-opens-its-own-public-course-without-parent-password',async()=>{
   for(const c of catalog.courses){await page.locator(`[data-course-version="${c.id}"]`).getByRole('button',{name:/开始这门课/}).click();await page.getByRole('region',{name:'课程老师工作台',exact:true}).waitFor();assert.equal(await page.locator('.cs-steps').count(),0,'Old forms are not the default course view');await practice(c);assert.ok(page.url().endsWith('#/learn/course?id='+c.id));assert.equal(await page.locator('input[type=password]').count(),0);assert.equal(await field(c,0).isDisabled(),true);await button('返回 AI 教学大厅').click();await page.locator(`[data-course-version="${c.id}"]`).waitFor();}
 });
 await check('demo-start-retains-selected-course-and-uses-existing-learning-entry',async()=>{
   const c=catalog.courses[0];await open(c);await button('开始体验').click();await waitEditable(c);assert.ok(page.url().endsWith('#/learn/course?id='+c.id));assert.equal((await read('/api/learning/v2/session')).mode,'learner');assert.equal(await page.locator('input[type=password]').count(),0);
 });
 for(const c of catalog.courses)await check('real-save-refresh-independent-course-'+c.id,async()=>{
   await open(c);await waitEditable(c);
   for(let i=0;i<3;i++)await field(c,i).fill(`${c.id}：虚构练习记录 ${i+1}，我亲自观察并写下一处修改。`);
   if(c.id==='ai-tools'){for(const n of ['描述目标','请 AI 生成','运行','检查','亲自修改再试'])await button('加入'+n).click();await button('检查我的顺序').click();await page.getByText('这是一种可用的起步顺序。修改以后，还要再次运行与检查。',{exact:true}).waitFor();}
   if(c.id==='imagination'){for(const [name,value]of[['为谁做','读书会同学'],['想解决什么困难','忘了带哪本书'],['先做一个功能','带书清单'],['怎样检查有用','请同学试勾选一本书']])await page.getByLabel(name,{exact:true}).fill(value);}
   if(c.id==='first-project'){await page.getByLabel('我亲自改的一处',{exact:true}).fill('把按钮问候改成向森林问好。');await page.getByLabel('运行后观察到了什么',{exact:true}).fill('先记录预测，创作完成后回来更新观察。');}
   if(c.id==='plugins'){await page.getByLabel('启用重点高亮扩展',{exact:true}).check();assert.equal(await page.locator('.cs-plugin-canvas.cs-highlight').count(),1);await page.getByLabel('关闭时的观察',{exact:true}).fill('文字没有重点底色。');await page.getByLabel('开启后的变化',{exact:true}).fill('带书提醒有了绿色高亮。');}
   if(c.id==='models'){await page.locator('.cs-page').getByRole('combobox').selectOption('sample-a');await page.getByLabel('我的依据与需要核对的地方',{exact:true}).fill('样例A时间地点与材料一致，B改了星期、地点并编造奖品。');}
   if(c.id==='api'){
     const invalid=page.waitForResponse(r=>r.url().endsWith('/api/experiment')&&r.request().method()==='POST');await button('发送教学 API 请求').click();assert.equal((await invalid).status(),422);await page.getByText(/HTTP 422/).waitFor();
     await page.getByLabel('请求中的名字',{exact:true}).fill('虚构小松');const valid=page.waitForResponse(r=>r.url().endsWith('/api/experiment')&&r.request().method()==='POST');await button('发送教学 API 请求').click();const r=await valid;assert.equal(r.status(),200);const body=await r.json();assert.equal(body.kind,'teaching-api');assert.equal(body.response.message,'你好，虚构小松！');await page.getByLabel('API response').waitFor();assert.equal(await page.getByLabel('我记录的响应消息',{exact:true}).inputValue(),'你好，虚构小松！');
   }
   if(c.id==='model-powered-app'){for(const [name,value]of[['应用接收什么输入','活动的时间地点'],['模型负责哪一小步','整理一句不添加事实的提醒'],['应用期待什么输出','让我检查的草稿'],['失败时怎样回退','显示原始信息，手动填写']])await page.getByLabel(name,{exact:true}).fill(value);await button('用固定规则验证方案').click();await page.getByText(/固定规则模拟：收到/).waitFor();}
   const saved=page.waitForResponse(r=>r.url().endsWith(`/learning-courses/${c.id}/progress`)&&r.request().method()==='POST');await button('保存本课记录').click();assert.equal((await saved).status(),200);await page.getByText(/已保存本课记录 · 版本 1/).waitFor();
   const p=await read(`/api/platform/v1/learning-courses/${c.id}/progress`);assert.equal(p.status,'saved');assert.equal(p.course_id,c.id);assert.ok(Object.keys(p.activity).length>0);assert.equal(p.answers.understand,`${c.id}：虚构练习记录 1，我亲自观察并写下一处修改。`);
   await page.reload();await waitEditable(c);assert.equal(await field(c,0).inputValue(),p.answers.understand);assert.equal(await field(c,2).inputValue(),p.answers.reflect);
 });
 await check('dirty-navigation-retains-or-discards-only-current-unsaved-input',async()=>{
   const c=catalog.courses[1];await open(c);await waitEditable(c);await field(c,0).fill('还没保存的想法');await button('返回 AI 教学大厅').click();await page.getByRole('dialog').waitFor();await button('留在这里').click();assert.equal(await field(c,0).inputValue(),'还没保存的想法');await button('返回 AI 教学大厅').click();await button('放弃本次修改').click();await page.locator('[data-course-version="imagination"]').waitFor();await open(c);await waitEditable(c);assert.match(await field(c,0).inputValue(),/^imagination：/);
 });
 await check('course-project-entry-creates-runnable-project-and-course-record-survives',async()=>{
   const c=catalog.courses[2];await open(c);await waitEditable(c);await button('进入创作工作台').click();await page.getByLabel('我的小想法').fill('七课验收虚构作品：点击按钮向森林问好');await button('保存想法，开始创作').click();await page.getByLabel('告诉松伴，你想试哪一步').waitFor();await page.frameLocator('iframe').getByRole('button',{name:'试着点我',exact:true}).click();await page.frameLocator('iframe').getByText('这是我触发的第一次变化！',{exact:true}).waitFor();assert.equal(await button('发送给松伴').isDisabled(),true);
   await button('AI 教学大厅').click();await page.locator('[data-course-version="first-project"]').getByRole('button',{name:/开始这门课/}).click();await waitEditable(c);assert.match(await page.getByLabel('我亲自改的一处',{exact:true}).inputValue(),/森林/);
 });
 await check('mobile-course-and-hall-have-no-horizontal-overflow',async()=>{
   await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'course-mobile.png'),fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await button('返回 AI 教学大厅').click();await page.locator('[data-course-version="model-powered-app"]').waitFor();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.screenshot({path:path.join(out,'hall-mobile.png'),fullPage:true});
 });
 await check('old-course-hackathon-and-portfolio-navigation-remain-available',async()=>{
   await button('打开以前的练习').click();await button('和老师试用 AI').waitFor();assert.ok(page.url().endsWith('#/learn/first'));await page.getByText('以前的邀请卡与访谈记录',{exact:true}).click();await page.locator('.lp-first-work').filter({has:page.getByRole('heading',{name:'从我的想法开始',exact:true})}).waitFor();await button('黑客松教学大厅').click();await page.getByRole('heading',{name:'认识黑客松',exact:true}).waitFor();assert.equal(await page.locator('.ph-hackathon-grid article').count(),2);await button('作品集').click();assert.ok(page.url().endsWith('#/portfolio'));assert.equal(await page.locator('input[type=password]').count(),0);
 });
 await check('logout-clears-private-course-state-and-does-not-call-providers',async()=>{
   await page.locator('.lp-account-menu > summary').click();await button('退出当前身份').click();await open(catalog.courses[0]);assert.equal(await field(catalog.courses[0],0).inputValue(),'');assert.equal(await field(catalog.courses[0],0).isDisabled(),true);const r=await context.request.get(origin+'/api/platform/v1/learning-courses/ai-tools/progress');assert.ok([401,403].includes(r.status()));assert.deepEqual(errors,[]);assert.deepEqual(external,[]);assert.equal(writes.some(p=>p.endsWith('/messages')||/image-jobs|email-codes/.test(p)),false);
 });
 console.log(JSON.stringify({passed:results.length,out}));
}catch(e){await page?.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});fs.writeFileSync(path.join(out,'failure.txt'),await page?.locator('body').innerText().catch(()=>''));throw e;}finally{fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({origin,results,errors,external,writes,scope:'synthetic actual HTTP; no provider calls'},null,2));await browser?.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
