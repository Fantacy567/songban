// Actual HTTP/SQLite + local parsers. Server model is a declared protocol fixture.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.SONGBAN_QA_URL||'http://127.0.0.1:8893';
const out=path.resolve('.browser-cache/materials');
const errors=[];
async function api(url,token,body,method){const r=await fetch(base+url,{method:method||(body?'POST':'GET'),headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});const d=await r.json();assert(r.ok,JSON.stringify(d));return d;}
async function idle(page){await page.waitForFunction(()=>!document.querySelector('#materials-host[aria-busy]'));}
async function snap(page,name){await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});}
async function login(page){await page.locator('#auth-phone').fill('18800008893');await page.locator('#auth-password').fill('materials-test-password');await page.locator('#auth-form button[type=submit]').click();await page.locator('#material-generate').waitFor();}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
 const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/#/event');await page.locator('#material-text').waitFor();
 await page.locator('#material-text').fill('活动日期：2026年11月7日至8日。\n支持1至3人组队。\n小李愿意做设计，分工尚未确认。');
 await page.locator('#material-nature').selectOption('sample');
 await page.locator('#material-input button[type=submit]').click();await login(page);
 assert((await page.locator('#material-text').inputValue()).includes('小李'));
 assert.equal(await page.locator('#material-nature').inputValue(),'sample');
 await page.locator('#material-input button[type=submit]').click();await idle(page);
 await page.locator('#material-files').setInputFiles(['screenshot.png','photo.jpg','scan.pdf','rules.pdf','chat.docx','notes.txt','unreadable.pdf'].map(x=>path.join(out,x)));
 await page.locator('#material-input button[type=submit]').click();await idle(page);
 const token=await page.evaluate(()=>localStorage.getItem('studio-token'));
 let s=await api('/api/materials/space',token);
 assert.equal(s.sources.length,8);assert.equal(s.sources.filter(x=>x.status==='failed').length,1);
 assert(s.sources.find(x=>x.metadata.name==='scan.pdf').segments[0].text.includes('3分钟'));
 await page.locator('#material-generate').click();await idle(page);
 await page.locator('#competition-info-title').waitFor();
 assert.equal(await page.locator('.material-groups,.material-item,.material-edit,[data-select]').count(),0);
 assert.equal(await page.getByText('本次变化：',{exact:false}).count(),0);
 assert((await page.locator('[data-competition-field=time]').innerText()).includes('11月7日'));
 assert((await page.locator('[data-competition-field=deadline]').innerText()).includes('待补充'));
 await page.locator('#material-text').fill('支持4至5人组队。\n提交内容：项目说明文档。');await page.locator('#material-input button[type=submit]').click();await idle(page);
 await page.locator('#competition-update').click();await idle(page);
 assert((await page.locator('[data-competition-field=team]').innerText()).includes('存在不同表述'));
 // Compact competition facts remain readable at all supported widths.
 for(const width of [390,768,1440]){
   await page.setViewportSize({width,height:950});
   await page.locator('#main-content').focus();await page.keyboard.press('Tab');assert(await page.evaluate(()=>document.activeElement!==document.body));
   assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)),`overflow ${width}`);
   await snap(page,'materials-event-'+width);
   await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,'materials-intake-'+width+'.png')});
   await page.locator('.competition-info').screenshot({path:path.join(out,'materials-result-'+width+'.png')});
 }
 const beforeFailure=await page.locator('#material-results').innerText();
 await page.route('**/api/materials/spaces/*/generate',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'model_not_configured',message:'浏览器失败状态测试：模型未配置，材料和上一版结果保留。'}})}));
 await page.locator('#material-generate').click();await idle(page);assert((await page.locator('#material-message').innerText()).includes('模型未配置'));
 assert.equal(await page.locator('#material-results').innerText(),beforeFailure);await snap(page,'materials-model-failure-simulated');await page.unroute('**/api/materials/spaces/*/generate');
await page.locator('#material-preview-share').click();await page.locator('[data-draft-kind=direction]').click();await idle(page);
 await page.locator('#material-use-draft').click();await page.locator('#topic-start').waitFor();assert((await page.locator('#topic-start [name=rules]').inputValue()).includes('活动日期'));
 await page.locator('#topic-track').fill('资料入口浏览器验证');await page.locator('#topic-start button[type=submit]').click();await page.getByTestId('topic-confirmed').waitFor();
 await page.goto(base+'/#/materials');await page.locator('#material-generate').waitFor();assert((await page.locator('#material-saved').innerText()).includes('文字 / 聊天摘录'));
 await page.locator('#material-generate').click();await idle(page);await page.locator('#material-preview-share').click();await page.locator('[data-draft-kind=tasks]').click();await idle(page);await page.locator('#material-use-draft').click();await page.locator('#confirmed-tasks').waitFor();
 const me=await api('/api/core/me',token),team=await api('/api/core/teams/'+me.teams[0].id,token);assert(team.reports.some(r=>r.tool==='资料入口行动草稿'));assert.equal(team.active_plan.tasks?.length||0,0);
 await page.goto(base+'/#/materials');await page.locator('#material-generate').waitFor();await snap(page,'materials-team-1440');
 await page.goto(base+'/#/library');await page.locator('#library-notes').waitFor();
 assert.equal(errors.length,0,errors.join('\n'));
 const results={passed:true,widths:[390,768,1440],sources:8,realParsers:['PNG OCR','JPEG OCR','scanned PDF OCR','text PDF','DOCX','TXT'],model:'protocol fixture; no live model validation',checks:['password login and guest draft','partial failure','compact competition facts','missing deadline stays unknown','conflicting team sizes','simulated model failure preserves results','draft sharing','material draft starts collective topic discussion','task discussion without publish','existing library'],browserErrors:errors};
 fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
