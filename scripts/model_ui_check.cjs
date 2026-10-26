/* Model settings UI + real backend, with explicitly simulated upstream protocol. */
const {chromium,request}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),net=require('node:net'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),out=path.join(root,'artifacts'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'collab-model-ui-'));
let server,browser,context;const results=[];const fake='FAKE_TEST_ONLY';
const fullId='mock/vendor-complete-model-id-2026-10-26-protocol-only';
function pass(name){results.push({name,result:'通过'});console.log('PASS',name);}
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function port(){return new Promise(resolve=>{const socket=net.createServer();socket.listen(0,'127.0.0.1',()=>{const p=socket.address().port;socket.close(()=>resolve(p));});});}
(async()=>{
 const n=await port(),base=`http://127.0.0.1:${n}`;
 server=spawn(path.join(root,'.venv/bin/python'),['-m','uvicorn','scripts.model_fixture:app','--host','127.0.0.1','--port',String(n)],{cwd:root,env:{...process.env,DATABASE_PATH:path.join(temp,'model-ui-fixture.sqlite3'),DEEPSEEK_API_KEY:'',MODEL_API_KEY:'',MODEL_BASE_URL:'',MODEL_NAME:''},stdio:'ignore'});
 for(let i=0;i<100;i++){try{if((await fetch(base+'/health')).ok)break;}catch{}if(i===99)throw Error('模拟服务启动失败');await pause(100);}
 const http=await request.newContext({baseURL:base});
 const created=await(await http.post('/api/projects',{data:{name:'模型协议联调（非真实模型）',deadline:new Date(Date.now()+86400000).toISOString(),members:[{name:'队长测试',role:'后端',skills:'Python',available_hours:4},{name:'前端测试',role:'前端',skills:'JavaScript',available_hours:4}]}})).json();
 const pid=created.project_id,headers={Authorization:'Bearer '+created.invites[0].access_token};
 browser=await chromium.launch({channel:'chrome',headless:true});context=await browser.newContext({viewport:{width:1440,height:1000}});context.setDefaultTimeout(15000);
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 await page.goto(`${base}/#project=${pid}&token=${created.invites[0].access_token}`);await page.locator('[data-tab="model"]').click();
 await page.getByRole('heading',{name:'选择这次协作的模型'}).waitFor();
 assert.ok((await page.locator('#content').innerText()).includes('deepseek-v4-pro'));
 pass('F11：默认模型页显示 DeepSeek-V4-Pro 与完整 ID，清楚标记未配置');
 await page.locator('#model-key').fill(fake);
 const discovered=page.waitForResponse(r=>r.url().endsWith('/model/discover'));
 await page.locator('#discover-models').click();assert.equal((await discovered).status(),200);
 await page.locator('#discovered-model').waitFor();assert.equal(await page.locator('#discovered-model').inputValue(),fullId);
 assert.equal(await page.locator('#model-key').inputValue(),'');
 assert.ok((await page.locator('#model-full-id').innerText()).includes(fullId));
 pass('F11：从明确的模拟服务读取名称与完整 ID，成功后清空密钥输入框');
 const selection=page.waitForResponse(r=>r.url().endsWith('/model')&&r.request().method()==='PUT');
 await page.locator('#save-model').click();assert.equal((await selection).status(),200);
 await page.locator('#notice').filter({hasText:'模型选择已保存'}).waitFor();
 assert.ok((await page.locator('#content').innerText()).includes(fullId));
 const leaked=await page.evaluate(k=>JSON.stringify(localStorage).includes(k),fake);assert.equal(leaked,false);
 const state=await(await http.get(`/api/projects/${pid}`,{headers})).json();assert.equal(state.current_model.model_id,fullId);assert.ok(!JSON.stringify(state).includes(fake));
 pass('F11：所选完整 ID 用于后端配置，响应与浏览器 localStorage 均不含 key');
 for(const kind of ['rules','discussion'])await http.post(`/api/projects/${pid}/sources`,{headers,data:{kind,title:'协议模拟原文',body:'目标：验证模型协议，不代表真实 AI 质量测试。'}});
 await page.locator('[data-tab="plan"]').click();await page.locator('#generate-model').waitFor();
 const generation=page.waitForResponse(r=>r.url().endsWith('/proposals')&&r.request().method()==='POST');await page.locator('#generate-model').click();assert.equal((await generation).status(),201);
 await page.locator('#draft-goal').waitFor();
 assert.ok((await page.locator('#content').innerText()).includes(fullId+'-response'));
 const generated=await(await http.get(`/api/projects/${pid}`,{headers})).json();assert.equal(generated.proposals[0].model_id,fullId);assert.equal(generated.proposals[0].response_model_id,fullId+'-response');
 pass('F11：模拟协议生成草案，分别保留请求 ID 和服务响应完整 ID');
 await page.locator('[data-tab="model"]').click();await page.locator('#use-builtin').click();await page.locator('#notice').filter({hasText:'已切回服务端基础模型'}).waitFor();
 const reset=await(await http.get(`/api/projects/${pid}`,{headers})).json();assert.equal(reset.current_model.mode,'builtin');assert.equal(reset.model_configured,false);assert.deepEqual(errors,[]);
 pass('F11：切回内置清除暂存配置，页面全程无未处理 JS 异常');
 await http.dispose();
 fs.writeFileSync(path.join(out,'model-ui-results.json'),JSON.stringify({success:true,real_model_tested:false,upstream:'httpx.MockTransport 明确的协议模拟；未向真实服务发送密钥或团队资料',steps:results},null,2));
})().catch(e=>{console.error(e.message.replace(/token=[^\s]+/g,'token=[REDACTED]').replaceAll(fake,'[REDACTED]'));process.exitCode=1;}).finally(async()=>{if(context)await context.close();if(browser)await browser.close();if(server){server.kill('SIGTERM');await new Promise(r=>server.once('exit',r));}fs.rmSync(temp,{recursive:true,force:true});});
