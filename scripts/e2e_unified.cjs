const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('fs');
const path=require('node:path');
const base=process.env.SONGBAN_QA_URL||'http://127.0.0.1:8892';
const output=path.resolve(process.env.SONGBAN_E2E_OUTPUT||'.browser-cache/unified');fs.mkdirSync(output,{recursive:true});
const errors=[];
async function request(path,body,token,method){const r=await fetch(base+path,{method:method||(body?'POST':'GET'),headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},...(body?{body:JSON.stringify(body)}:{})});const d=await r.json();assert(r.ok,JSON.stringify(d));return d;}
async function screenshot(page,name){await page.screenshot({path:path.join(output,name+'.png'),fullPage:true});}
async function codeFromUI(page){await page.locator('#send-code').click();await page.locator('#code-notice').filter({hasText:'测试码'}).waitFor();return (await page.locator('#code-notice').innerText()).match(/\d{6}/)[0];}
async function route(page,path){await page.goto(base+'/#/'+path);await page.locator('[data-route]').waitFor();}
(async()=>{
  const browser=await chromium.launch({...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{}),headless:true});
  const ctxA=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'}),ctxB=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  const a=await ctxA.newPage(),b=await ctxB.newPage();
  for(const page of [a,b])page.on('pageerror',e=>errors.push(e.message));
  await route(a,'login');await a.getByRole('button',{name:/^登录/}).waitFor();await screenshot(a,'unified-landing');
  await a.getByRole('link',{name:'找到适合我的黑客松'}).click();await a.locator('.event-row').first().waitFor();
  await a.locator('.event-row').first().click();await a.locator('#material-text').waitFor();await screenshot(a,'unified-event');
  await a.getByRole('link',{name:'创建或加入小队 →',exact:true}).click();await a.locator('[data-auth-required]').click();
  await a.locator('[data-register]').click();
  const stamp=String(Date.now()).slice(-7),phoneA='1881'+stamp,phoneB='1882'+stamp;
  await a.locator('#auth-phone').fill(phoneA);await a.locator('#auth-code').fill(await codeFromUI(a));
  await a.locator('#auth-password').fill('test-password');await a.locator('#auth-name').fill('测试·设计同伴');
  await a.locator('#auth-skills').fill('页面设计');await a.locator('#auth-profile').fill('完成第一件作品');
  await a.locator('#auth-form button[type=submit]').click();await a.locator('#create-team').waitFor();
  await a.locator('#team-name').fill('联调验证小队 '+stamp);await a.locator('#create-team button[type=submit]').click();
  await a.getByRole('link',{name:/讨论后填写共同方向/}).click();
  await a.locator('#direction-form').waitFor();await a.locator('[name=rules]').fill('协议测试规则：提交可运行的教育作品与说明。');
  await a.locator('[name=goal]').fill('完成一个可以演示的知识闯关小助手');
  await a.locator('#direction-form button[type=submit]').click();await a.getByText('共同方向已更新。',{exact:false}).waitFor();
  const tokenA=await a.evaluate(()=>localStorage.getItem('studio-token'));const team=(await request('/api/core/me',null,tokenA)).teams[0];
  const code=await request('/api/studio/codes',{phone:phoneB});await request('/api/studio/register',{phone:phoneB,code:code.code,password:'test-password',name:'测试·开发同伴',skills:'接口开发',profile:'一起完成作品'});
  await route(b,'login');await b.getByRole('button',{name:/^登录/}).click();await b.locator('[data-mode=sms]').click();
  await b.locator('#auth-phone').fill(phoneB);await b.locator('#auth-code').fill(await codeFromUI(b));await b.locator('#auth-form button[type=submit]').click();
  await b.locator('.event-row').first().waitFor();await b.getByRole('link',{name:'实践',exact:true}).click();
  await b.locator('#team-code').fill(team.code);await b.locator('#join-team button[type=submit]').click();await b.locator('#confirmed-tasks').waitFor();
  await route(a,'collaboration');await a.locator('#review').click();await a.locator('#confirm-plan').waitFor();
  a.once('dialog',d=>d.accept());await a.locator('#confirm-plan').click();await a.locator('[data-report-task=T1]').waitFor();
  await a.locator('[data-report-task=T1]').click();await a.locator('#manual-report [name=summary]').fill('已完成页面草图，并检查正常与空输入');
  await a.locator('#manual-report [name=status]').selectOption('reported_done');await a.locator('#manual-report [name=evidence_text]').fill('联调证据：正常请求返回200，空输入被拒绝');
  await a.locator('#manual-report button[type=submit]').click();await a.getByText('本人进展已保存。',{exact:true}).waitFor();
  await route(b,'collaboration');await b.locator('[data-check-task=T1]').click();await b.locator('#check-verdict').selectOption('accepted');await b.locator('#check-note').fill('测试成员按约定核对正常输入与错误输入。');
  await b.locator('#check-form button[type=submit]').click();await b.getByText('同伴检查已保存',{exact:false}).waitFor();
  await a.reload();await a.locator('#confirmed-tasks').waitFor();assert((await a.locator('#confirmed-tasks').innerText()).includes('同伴检查通过'));await screenshot(a,'unified-work');
  console.log('PASS real API flow: registration, SMS login, team join, direction, fixture plan, report, peer check, reload');
  await route(a,'members');await a.locator('#logout').click();await a.getByRole('button',{name:/^登录/}).click();
  await a.locator('#auth-phone').fill(phoneA);await a.locator('#auth-password').fill('test-password');await a.locator('#auth-form button[type=submit]').click();await a.locator('#confirmed-tasks').waitFor();
  assert.equal((await request('/api/core/me',null,await a.evaluate(()=>localStorage.getItem('studio-token')))).teams[0].id,team.id);
  console.log('PASS password login preserves the same team');
  for(const width of [390,768,1440]){
    await a.setViewportSize({width,height:950});
    for(const name of ['events','event','team','direction','work','team-work','tools','library','members','delivery','review']){
      await route(a,name);await a.waitForTimeout(150);
      const overflow=await a.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1);
      assert(!overflow,`${name} overflows at ${width}`);
      if(['event','work','team'].includes(name))await screenshot(a,`unified-${name}-${width}`);
    }
  }
  console.log('PASS 30 responsive route checks at 390/768/1440');
  await route(a,'direction');await a.locator('[name=goal]').fill('未保存的长中文草稿，离开页面也应保留');
  await a.getByRole('link',{name:'个人任务',exact:true}).first().click();await a.getByRole('link',{name:'方向',exact:true}).click();
  assert.equal(await a.locator('[name=goal]').inputValue(),'未保存的长中文草稿，离开页面也应保留');
  await a.route('**/api/core/teams/*/direction',r=>r.fulfill({status:409,contentType:'application/json',body:JSON.stringify({error:{code:'stale_context',message:'资料已变化，请核对后重试。'}})}));
  await a.locator('#direction-form button[type=submit]').click();await a.getByRole('button',{name:'读取最新版本，保留我的输入'}).click();
  assert.equal(await a.locator('[name=goal]').inputValue(),'未保存的长中文草稿，离开页面也应保留');await a.unroute('**/api/core/teams/*/direction');
  console.log('PASS conflict recovery retains unsaved form input');
  await a.locator('#direction-form button[type=submit]').click();
  await a.waitForFunction(()=>document.querySelector('#direction-form')?.dataset.dirty==='false');
  assert.equal(await a.locator('#direction-form [data-draft-notice]').count(),0);
  assert.equal(await a.locator('[name=goal]').inputValue(),'未保存的长中文草稿，离开页面也应保留');
  console.log('PASS saving a recovered draft clears the unsaved indicator');
  // Two tabs share one identity without bouncing storage events or reviving it.
  const tab=await ctxA.newPage();tab.on('pageerror',e=>errors.push(e.message));
  await route(tab,'work');await tab.locator('#confirmed-tasks').waitFor();
  await a.locator('#logout').click();await tab.getByRole('button',{name:/^登录/}).waitFor();
  assert.equal(await tab.evaluate(()=>localStorage.getItem('studio-token')),null);
  await a.getByRole('button',{name:/^登录/}).click();
  await a.locator('#auth-phone').fill(phoneA);await a.locator('#auth-password').fill('test-password');
  await a.locator('#auth-form button[type=submit]').click();await a.locator('#confirmed-tasks').waitFor();
  await tab.waitForFunction(()=>state.me?.teams.length>0);
  assert.equal(await a.evaluate(()=>state.token),await tab.evaluate(()=>state.token));
  await tab.close();console.log('PASS cross-tab login/logout synchronization');
  const fresh=await browser.newPage({viewport:{width:390,height:844}});
  await route(fresh,'login');const trigger=fresh.getByRole('button',{name:/^登录/});
  await trigger.click();await fresh.locator('#auth-phone').waitFor();await fresh.keyboard.press('Escape');
  assert(await trigger.evaluate(el=>el===document.activeElement));
  await trigger.click();await fresh.locator('[data-mode=sms]').click();
  assert.equal(await fresh.locator('#auth-password').count(),0);
  await screenshot(fresh,'unified-sms-login-390');
  await fresh.locator('[data-mode=password]').click();await fresh.locator('#auth-password').waitFor();
  await screenshot(fresh,'unified-password-login-390');await fresh.close();
  console.log('PASS modal focus restore and both login modes on mobile');
  assert.deepEqual(errors,[]);console.log('PASS no browser runtime errors');
  fs.writeFileSync(path.join(output,'unified-qa.json'),JSON.stringify({ok:true,widths:[390,768,1440],routes:10,browserErrors:errors,model:'explicit fixture, not a real model',sms:'simulated in isolated loopback QA server'},null,2));
  await browser.close();
})().catch(e=>{console.error(e.stack);process.exit(1)});
