/* Opt-in, single bounded real call. Never part of automatic test suites. */
if(!process.argv.includes('--run-live'))throw Error('真实调用需要显式 --run-live；可能消耗模型服务额度。');
const {chromium,request}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const key=process.env.DEEPSEEK_API_KEY;
if(!key)throw Error('环境未提供 DEEPSEEK_API_KEY，不读取其他配置文件中的凭据。');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:8886',out=path.resolve(__dirname,'../artifacts');
let http,browser,context;const secrets=[key];const result={success:false,real_model_tested:true,calls:0,note:'仅验证一次真实连接与草案生成，不代表已系统验证分工质量或节时效果。'};
function redact(s){for(const v of secrets)s=String(s).split(v).join('[REDACTED]');return String(s).replace(/token=[^\s]+/g,'token=[REDACTED]');}
(async()=>{
 http=await request.newContext({baseURL:base,timeout:60000});
 const response=await http.post('/api/projects',{data:{name:'DeepSeek 真实调用 · 开发验收',deadline:new Date(Date.now()+86400000).toISOString(),members:[{name:'后端测试成员',role:'队长、产品与后端',skills:'Python、接口开发',available_hours:4},{name:'前端测试成员',role:'前端与设计',skills:'JavaScript、页面实现',available_hours:4}]}});
 assert.equal(response.status(),201);const created=await response.json(),pid=created.project_id;secrets.push(...created.invites.map(i=>i.access_token));
 const headers={Authorization:'Bearer '+created.invites[0].access_token};
 const discoveryResponse=await http.post(`/api/projects/${pid}/model/discover`,{headers,data:{base_url:'https://api.deepseek.com',api_key:key}});
 result.discovery_status=discoveryResponse.status();
 if(discoveryResponse.status()!==200){const error=await discoveryResponse.json();throw Error(error.error?.message||'真实服务模型列表读取失败');}
 const discovery=await discoveryResponse.json();
 const selected=discovery.models.find(m=>m.id==='deepseek-v4-pro');assert.ok(selected,'官方服务列表应包含 deepseek-v4-pro');
 result.listed_model={id:selected.id,name:selected.name};
 await http.put(`/api/projects/${pid}/model`,{headers,data:{mode:'builtin',expected_version:0}});
 for(const source of [
  {kind:'rules',title:'真实模型接口验收要求（非赛事公告）',body:'这是公开的开发验收输入，不是参赛调研或真实会议。交付：能运行的协作后端、前端操作页、需求和接口文档、功能测试证据。必须通过至少一次双成员交叉验收。总任务估时每人不超过其填写的4小时。'},
  {kind:'discussion',title:'开发验收计划（明确的测试资料）',body:'目标：用一条完整流程帮助小队明确分工并完成验收。\n决定：首版包括资料录入、分工确认、共享任务、提交与交叉验收、基于记录的复盘。\n决定：模型仅提出建议，正式分工由队长确认。\n待确认：前后端请求字段和联调时间。请为两名测试成员提出简短任务、原文依据和验收标准，不增加新功能。'}
 ]){const saved=await http.post(`/api/projects/${pid}/sources`,{headers,data:source});assert.equal(saved.status(),201);}
 browser=await chromium.launch({channel:'chrome',headless:true});context=await browser.newContext({viewport:{width:1440,height:1000}});context.setDefaultTimeout(60000);
 const page=await context.newPage();page.on('dialog',d=>d.accept());
 await page.goto(`${base}/#project=${pid}&token=${created.invites[0].access_token}`);await page.locator('[data-tab="plan"]').click();await page.locator('#generate-model').waitFor();
 const started=Date.now();const generation=page.waitForResponse(r=>r.url().endsWith('/proposals')&&r.request().method()==='POST',{timeout:60000});
 result.calls=1;await page.locator('#generate-model').click();const generatedResponse=await generation;result.generation_status=generatedResponse.status();result.elapsed_seconds=Number(((Date.now()-started)/1000).toFixed(2));
 if(generatedResponse.status()!==201){await page.locator('#notice.error').waitFor();throw Error(await page.locator('#notice').innerText());}
 await page.locator('#draft-goal').waitFor();
 const workspace=await(await http.get(`/api/projects/${pid}`,{headers})).json(),draft=workspace.proposals[0];
 assert.equal(draft.mode,'model');assert.equal(draft.model_id,'deepseek-v4-pro');assert.ok(draft.content.tasks.length>0);assert.equal(workspace.tasks.length,0);
 assert.equal(draft.capacity_warnings.length,0);
 result.request_model_id=draft.model_id;result.response_model_id=draft.response_model_id;result.tasks=draft.content.tasks.length;result.formal_tasks_created=workspace.tasks.length;
 await page.screenshot({path:path.join(out,'06_live_deepseek_proposal.png'),fullPage:true});
 result.success=true;console.log('PASS 真实 DeepSeek 模型列表与一次草案生成，结构/引用/预算/依赖均通过服务端校验；正式任务仍待人工确认。');
})().catch(e=>{result.error=redact(e.message);console.error(result.error);process.exitCode=1;}).finally(async()=>{if(context)await context.close();if(browser)await browser.close();if(http)await http.dispose();fs.writeFileSync(path.join(out,'live-model-results.json'),JSON.stringify(result,null,2));});
