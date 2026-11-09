/* Real HTTP + isolated synthetic SQLite; no API interception, provider calls or email. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),vm=require('node:vm');
const {chromium}=require('playwright');
const origin=process.env.SONGBAN_ENTRY_HTTP_ORIGIN,mode=process.env.SONGBAN_ENTRY_HTTP_MODE;
assert.equal(process.env.SONGBAN_ENTRY_SYNTHETIC,'1');assert.ok(['demo','account'].includes(mode));
const url=new URL(origin);assert.equal(url.protocol,'http:');assert.equal(url.hostname,'127.0.0.1');assert.ok(!['8894','8895'].includes(url.port));
const out=path.resolve(process.env.SONGBAN_ENTRY_HTTP_EVIDENCE),results=[],errors=[],external=[],writes=[];
let browser,page;
async function check(name,fn){await fn();results.push({name,passed:true});console.log('PASS '+name);}
(async()=>{fs.mkdirSync(out,{recursive:true});try{
 browser=await chromium.launch({headless:true,channel:'msedge'});
 const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
 page=await context.newPage();page.setDefaultTimeout(15000);
 page.on('pageerror',e=>errors.push(e.message));context.on('request',r=>{const u=new URL(r.url());if(['http:','https:'].includes(u.protocol)&&u.origin!==origin)external.push(u.origin);if(!['GET','HEAD'].includes(r.method()))writes.push(u.pathname);});
 const button=name=>page.getByRole('button',{name,exact:true});
 const session=async()=>{const r=await context.request.get(origin+'/api/learning/v2/session');assert.equal(r.status(),200);return r.json();};
 const noParent=async()=>{assert.equal(await page.getByLabel('已有账号',{exact:true}).count(),0);assert.equal(await page.locator('input[type=password]').count(),0);assert.equal(await page.getByText('请家长重新认证',{exact:true}).count(),0);};
 await check('hall-to-idea-has-no-parent-form-or-demo-password-tip',async()=>{
   await page.goto(origin+'/learning-prep#/learn/courses');await button('从我的想法开始').click();await page.getByRole('region',{name:'开始学习',exact:true}).waitFor();await noParent();
   const html=await (await context.request.get(origin+'/learning-prep')).text();assert.ok(!/SongbanLearningDemo=|manager_account|staff_account/.test(html));
   await page.screenshot({path:path.join(out,'entry.png'),fullPage:true});
 });
 if(mode==='demo'){
   await check('one-explicit-click-establishes-only-existing-learner',async()=>{
     assert.equal(writes.length,0);await button('开始体验').click();await page.getByLabel('我的小想法').waitFor();
     const current=await session();assert.equal(current.mode,'learner');assert.deepEqual(current.scopes,['learning']);
     assert.deepEqual(writes,['/api/demo/learning/start']);await noParent();
   });
   await check('save-idea-opens-studio-and-reload-restores-project',async()=>{
     await page.getByLabel('我的小想法').fill('虚构入口验证：点一下按钮，显示一句欢迎。');await button('保存想法，开始创作').click();
     await page.getByLabel('告诉松伴，你想试哪一步').waitFor();await page.waitForURL(/#\/learn\/create\?id=/);
     await page.reload();await page.getByLabel('告诉松伴，你想试哪一步').waitFor();await noParent();
     await page.screenshot({path:path.join(out,'studio.png'),fullPage:true});
   });
   await check('learner-cannot-read-family-or-admin-even-with-demo-bearer',async()=>{
     const bootText=await (await context.request.get(origin+'/demo/bootstrap.js')).text();const demo=JSON.parse(bootText.split('=',2)[1].split(';\n',1)[0]);
     for(const endpoint of ['/api/learning/v2/families','/api/server-admin/v1/session','/api/core/me']){
       const r=await context.request.get(origin+endpoint,{headers:{Authorization:'Bearer '+demo.users[0].token}});assert.ok([401,403].includes(r.status()),endpoint+': '+r.status());
     }
     await page.locator('.lp-account-menu > summary').click();assert.equal(await button('家长管理').count(),0);assert.equal(await button('家庭资料').count(),0);
     await page.goto(origin+'/learning-prep#/family');await page.waitForURL(/#\/learn\/create$/);await page.getByLabel('我的小想法').waitFor();await noParent();
   });
   await check('cross-tab-logout-removes-project-and-old-csrf-cannot-restart',async()=>{
     await button('AI 教学大厅').click();await button('从我的想法开始').click();await page.getByLabel('我的小想法').waitFor();
     const tab=await context.newPage();await tab.goto(origin+'/learning-prep#/learn/create');await tab.getByLabel('我的小想法').waitFor();
     const boot=await (await context.request.get(origin+'/api/learning/v2/session-bootstrap')).json();
     await tab.locator('.lp-account-menu > summary').click();await tab.getByRole('button',{name:'退出当前身份',exact:true}).click();
     await button('开始体验').waitFor();assert.equal(await page.locator('iframe').count(),0);assert.equal(await page.getByLabel('我的小想法').count(),0);
     const r=await context.request.post(origin+'/api/demo/learning/start',{headers:{Origin:origin,'X-CSRF-Token':boot.csrf_token},data:{request_id:'stale-browser-http',browser_revision:boot.browser_revision}});assert.equal(r.status(),403);
     await tab.close();
   });
   await check('http-rejects-cross-origin-missing-csrf-and-stale-revision',async()=>{
     const boot=await (await context.request.get(origin+'/api/learning/v2/session-bootstrap')).json();
     const data={request_id:'entry-rejected-http',browser_revision:boot.browser_revision};
     for(const [headers,body,status] of [[{Origin:origin},data,403],[{Origin:'https://outside.invalid','X-CSRF-Token':boot.csrf_token},data,403],[{Origin:origin,'X-CSRF-Token':boot.csrf_token},{...data,browser_revision:999999},409]]){
       assert.equal((await context.request.post(origin+'/api/demo/learning/start',{headers,data:body})).status(),status);
     }
   });
 }else{
   await check('anonymous-uses-unified-login-with-controlled-return',async()=>{
     const href=await page.getByRole('link',{name:'登录并继续',exact:true}).getAttribute('href');assert.equal(new URLSearchParams(href.split('?')[1]).get('next'),'/learning-prep#/learn/create');
     await page.getByRole('link',{name:'登录并继续',exact:true}).click();await page.locator('[data-auth]').click();
     await page.getByLabel('手机号或邮箱',{exact:true}).fill('parent-a');await page.getByLabel('密码',{exact:true}).fill('fictional-password-only');
     await page.locator('#auth-form button[type=submit]').click();await page.waitForURL(origin+'/learning-prep#/learn/create');
     await page.getByText('账号已登录，还需要确认这次使用的学习身份。请家长完成一次学习准备，之后可以继续这里的作品。',{exact:true}).waitFor();
     assert.equal(await page.getByRole('link',{name:'登录并继续',exact:true}).count(),0);await noParent();
     await page.reload();await button('完成学习准备').waitFor();assert.equal(page.url(),origin+'/learning-prep#/learn/create');
   });
   await check('explicit-learning-preparation-returns-to-original-idea-target',async()=>{
     await button('完成学习准备').click();await page.getByLabel('已有账号',{exact:true}).fill('parent-a');await page.getByLabel('密码',{exact:true}).fill('fictional-password-only');
     await button('重新认证并进入管理').click();await button('进入孩子学习模式').click();await button('确认进入').click();
     await page.getByLabel('我的小想法').waitFor();assert.equal(page.url(),origin+'/learning-prep#/learn/create');assert.equal((await session()).mode,'learner');await noParent();
     assert.equal((await context.request.post(origin+'/api/demo/learning/start',{data:{}})).status(),403);
     const anonymous=await browser.newContext();assert.equal((await anonymous.request.post(origin+'/api/demo/learning/start',{data:{}})).status(),404);await anonymous.close();
   });
   await check('login-return-allowlist-rejects-external-admin-and-ambiguous-targets',async()=>{
     const source=fs.readFileSync(path.resolve(__dirname,'../../../static/songban.js'),'utf8');const fn=source.slice(source.indexOf('function learningLoginReturn()'),source.indexOf('function isDemoExperience()'));
     const run=target=>vm.runInNewContext(fn+';learningLoginReturn()', {URLSearchParams,platformEnabled:true,isDemoExperience:()=>false,location:{hash:'#/login?next='+encodeURIComponent(target)}});
     for(const target of ['/learning-prep#/learn/create?id=cs_123','/learning-prep#/learn/run?id=run-1&view=review','/learning-prep#/portfolio'])assert.equal(run(target),target);
     for(const target of ['https://outside.invalid/','//outside.invalid','/server-admin','/learning-prep#/family','/learning-prep#/learn/create?id=a&id=b','/learning-prep#/learn/create?id=%2F%2Fevil','/learning-prep#/learn/create?role=admin'])assert.equal(run(target),'');
   });
 }
 await check('no-model-request-no-external-network-no-browser-errors',async()=>{assert.equal(writes.some(p=>p.endsWith('/messages')||/email-codes|login-email|image-jobs/.test(p)),false);assert.deepEqual(external,[]);assert.deepEqual(errors,[]);});
 console.log(JSON.stringify({passed:results.length,out}));
}catch(e){await page?.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});fs.writeFileSync(path.join(out,'failure.txt'),await page?.locator('body').innerText().catch(()=>''));throw e;
}finally{fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({scope:'real HTTP / synthetic only / zero provider calls',mode,origin,results,errors,external,writes},null,2));await browser?.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
