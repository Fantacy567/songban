/* H1 integration: real local HTTP with synthetic data; no provider or remote calls. */
const {chromium}=require('playwright');
const fs=require('node:fs'); const path=require('node:path'); const assert=require('node:assert/strict');
const base=process.env.SONGBAN_PLATFORM_QA_URL||'http://127.0.0.1:8901';
const url=new URL(base); if(!['127.0.0.1','localhost'].includes(url.hostname)||['8894','8895'].includes(url.port))throw Error('Use an isolated QA origin');
const out=process.env.SONGBAN_QA_OUTPUT||'E:/松伴/outputs/platform-integration-20261102/halls'; fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[],results=[];
 page.on('pageerror',e=>errors.push(e.message));
 async function test(name,fn){await fn();results.push({name,passed:true});}
 try {
  await test('native hall has exactly three primary entries and two illustrated cards',async()=>{
   await page.goto(base+'/#/hackathon');await page.getByRole('heading',{name:'认识黑客松',exact:true}).waitFor();
   assert.equal(await page.getByRole('navigation',{name:'主导航',exact:true}).getByRole('link').count(),3);
   assert.equal(await page.locator('.ph-hackathon-grid article').count(),2);
   assert.equal(await page.locator('#content img').count(),2);
   await page.screenshot({path:path.join(out,'hackathon-1440.png'),fullPage:true});
  });
  await test('recognition explains first and returns to same practice entry',async()=>{
   await page.getByRole('button',{name:/先了解黑客松/}).click();
   await page.waitForURL('**/#/hackathon/intro');
   await page.getByRole('button',{name:/我想试一试|继续上次的实践/}).waitFor();
   assert.match(await page.locator('body').innerText(),/示例/);
  });
  await test('one native companion keeps the hall conversation while navigating',async()=>{
   await page.getByRole('button',{name:'松伴 · 陪我走一步'}).click();
   await page.getByRole('textbox',{name:'想问松伴什么'}).fill('黑客松里第一步做什么？');
   await page.getByRole('button',{name:'发送，看看提示',exact:true}).click();
   await page.getByText('本地指引 · 不是实时AI回复',{exact:true}).first().waitFor();
   await page.getByRole('button',{name:/返回黑客松教学大厅/}).click();
   await page.getByRole('heading',{name:'认识黑客松',exact:true}).waitFor();
   assert.equal(await page.getByRole('complementary',{name:'松伴陪你做',exact:true}).count(),1);
   assert.match(await page.getByRole('region',{name:'和松伴聊',exact:true}).innerText(),/黑客松里第一步做什么/);
  });
  await test('learning hall is public without granting child access',async()=>{
   await page.goto(base+'/learning-prep#/learn/courses');
   await page.locator('.ph-course-card').first().waitFor();
   assert.equal(await page.getByRole('navigation',{name:'主导航',exact:true}).getByRole('button').count(),3);
   assert.match(await page.locator('body').innerText(),/班级活动邀请卡/);
   const response=await context.request.get(base+'/api/platform/v1/learners/unknown/works');assert.equal(response.status(),401);
  });
  await test('child-safe hackathon teaching route stays in learning shell',async()=>{
   await page.getByRole('navigation',{name:'主导航',exact:true}).getByRole('button',{name:'黑客松教学大厅',exact:true}).click();
   await page.getByRole('heading',{name:'认识黑客松',exact:true}).waitFor();
   assert.match(page.url(),/learning-prep#\/hackathon$/);
  });
  for(const width of [390,768])await test('hall responsive '+width,async()=>{
   await page.setViewportSize({width,height:900});await page.goto(base+'/#/hackathon');
   await page.getByRole('heading',{name:'认识黑客松',exact:true}).waitFor();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
   await page.screenshot({path:path.join(out,`hackathon-${width}.png`),fullPage:true});
  });
  assert.deepEqual(errors,[]);
 } finally {fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({results,errors},null,2));await browser.close();}
 console.log(JSON.stringify({passed:results.length,errors,output:out}));
})().catch(e=>{console.error(e);process.exitCode=1;});
