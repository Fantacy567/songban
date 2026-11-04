/* Offline UI contract test; backend authorization is covered by test_server_admin.py. */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
(async () => {
  const root = path.resolve(__dirname, '..');
  const out = path.resolve(process.argv[2] || 'artifacts/server-admin-ui');
  fs.mkdirSync(out, {recursive:true});
  const browser = await chromium.launch({headless:true, executablePath:'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'});
  const context = await browser.newContext({viewport:{width:1280,height:900}});
  const page = await context.newPage();
  const failures=[], unexpected=[], saves=[], closures=[];
  page.on('pageerror', error=>failures.push(error.message));
  const state = {authorized:true, studioUnavailable:false, providers:{
    text:{enabled:false,provider:'deepseek',base_url:'https://api.deepseek.com',model:'deepseek-chat',max_calls:0,max_output_tokens:800,timeout_seconds:90,max_concurrency:1,revision:0,key_configured:false,configuration_ready:false,provider_verified:false},
    image:{enabled:false,provider:'doubao',base_url:'https://ark.cn-beijing.volces.com/api/v3',model:'',max_calls:0,max_output_tokens:800,timeout_seconds:120,max_concurrency:1,revision:0,key_configured:false,configuration_ready:false,provider_verified:false,integration_status:'private_images',size:'2K',supports_sequential_generation:true,allowed_response_models:[]}
  }};
  await context.addInitScript(()=>localStorage.setItem('studio-token','synthetic-admin-token'));
  await context.route('**/*', async route=>{
    const req=route.request(), url=new URL(req.url()), pathname=url.pathname;
    const reply=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    if(url.hostname!=='admin.example.test'){unexpected.push(req.url());return route.abort();}
    if(pathname==='/server-admin')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(root,'static/server-admin.html'))});
    if(['/static/server-admin.css','/static/server-admin.js'].includes(pathname))return route.fulfill({contentType:pathname.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(root,pathname))});
    if(pathname.endsWith('/session-bootstrap'))return reply({csrf_token:'fiction-csrf'});
    if(!state.authorized)return reply({error:{message:'此账号没有服务端管理权限。'}},403);
    if(pathname.endsWith('/session'))return reply({administrator:{email:'admin@example.test'},providers:state.providers,runtime:{creative_studio_registered:true,learning_workbench_registered:true,notice:'配置检查不代表真实供应商调用成功。'}});
    if(pathname.endsWith('/studio-jobs'))return state.studioUnavailable ? reply({error:{message:'创作服务尚未注册。'}},503) : reply({items:closures.some(item=>item.domain==='studio')?[]:[{id:'csj_synthetic_unknown_long_identifier_1234567890',state:'unknown',failure_code:'result_uncertain',created_at:'2026-11-03T01:00:00Z'}]});
    if(pathname.endsWith('/workbench-jobs'))return reply({items:closures.some(item=>item.domain==='workbench')?[]:[{id:'uwm_synthetic_unknown_long_identifier_1234567890',state:'unknown',failure_code:'model_result_unknown',created_at:'2026-11-04T01:00:00Z'}]});
    if(pathname.endsWith('/close-unknown')){
      if(req.headers()['x-csrf-token']!=='fiction-csrf')throw Error('missing close CSRF');
      const domain=pathname.includes('/workbench-jobs/')?'workbench':'studio';
      if(!pathname.includes(domain==='workbench'?'/uwm_':'/csj_'))throw Error('wrong domain closure');
      closures.push({domain,body:req.postDataJSON()});
      return reply({state:'failed',usage_refunded:false,notice:'已记录核对证据并关闭未知任务；额度保留，未重试，未认定成功。'});
    }
    if(pathname.includes('/providers/')){
      const kind=pathname.split('/').pop(), body=req.postDataJSON();
      if(req.headers()['x-csrf-token']!=='fiction-csrf')throw Error('missing CSRF');
      saves.push({...body,api_key:body.api_key?'[redacted]':''});
      const {api_key,clear_key,request_id,expected_revision,...plain}=body;
      Object.assign(state.providers[kind],plain,{revision:expected_revision+1,key_configured:!!api_key,configuration_ready:plain.enabled&&!!api_key&&plain.max_calls>0});
      return reply(state.providers[kind]);
    }
    if(pathname.endsWith('/audit'))return reply({items:[{id:1,actor_id:'synthetic-admin',kind:'text',revision:1,changed_fields:['api_key','max_calls'],created_at:'2026-11-02T12:00:00Z'}]});
    unexpected.push(pathname);return route.abort();
  });
  try {
    await page.goto('https://admin.example.test/server-admin');
    await page.getByText('管理员：admin@example.test',{exact:true}).waitFor();
    if(!(await page.locator('#provider-forms').innerText()).includes('课程老师与创作编程共用文字额度'))throw Error('shared text scope missing');
    const form=page.locator('form[data-kind=text]');
    await form.locator('[name=enabled]').check();
    await form.locator('[name=api_key]').fill('synthetic-browser-key');
    await form.locator('[name=max_calls]').fill('3');
    await form.getByRole('button',{name:'保存模型配置'}).click();
    await page.getByText('配置已保存。密钥不会回显；没有发起模型调用。',{exact:true}).waitFor();
    if(await page.locator('form[data-kind=text] [name=api_key]').inputValue()!=='')throw Error('secret remained in field');
    if((await page.locator('body').innerText()).includes('synthetic-browser-key'))throw Error('key leaked');
    const image=page.locator('form[data-kind=image]');
    await image.locator('[name=enabled]').check();
    await image.locator('[name=model]').fill('synthetic-image-model');
    await image.locator('[name=api_key]').fill('synthetic-image-key');
    await image.locator('[name=max_calls]').fill('2');
    await image.locator('[name=size]').selectOption('4K');
    await image.locator('[name=supports_sequential_generation]').uncheck();
    await image.locator('[name=allowed_response_models]').fill('synthetic-response-1, synthetic-response-2');
    await image.getByRole('button',{name:'保存图片配置',exact:true}).click();
    await page.getByText('配置已保存。密钥不会回显；没有发起模型调用。',{exact:true}).waitFor();
    if(saves[1].size!=='4K'||saves[1].supports_sequential_generation!==false||saves[1].allowed_response_models.length!==2)throw Error('image configuration fields not serialized');
    await page.getByRole('button',{name:'配置记录',exact:true}).click();
    await page.getByText(/synthetic-admin · text 版本 1/).waitFor();
    await page.getByRole('button',{name:'模型与额度',exact:true}).click();
    await page.screenshot({path:path.join(out,'admin-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('mobile overflow');
    await page.screenshot({path:path.join(out,'admin-mobile.png'),fullPage:true});
    await page.getByRole('button',{name:'运行状态',exact:true}).click();
    if(!(await page.locator('#runtime').innerText()).includes('课程工作台已注册；文字老师无需 Docker'))throw Error('text runtime incorrectly gated on Docker');
    await page.getByRole('button',{name:'读取待核对任务',exact:true}).click();
    const unknown=page.locator('#unknown-jobs form[data-domain=studio]');await unknown.waitFor();
    const workbench=page.locator('#unknown-jobs form[data-domain=workbench]');await workbench.waitFor();
    state.studioUnavailable=true;
    await page.getByRole('button',{name:'读取待核对任务',exact:true}).click();
    await page.locator('#unknown-jobs').getByText('创作服务尚未注册。',{exact:true}).waitFor();
    await workbench.waitFor();
    state.studioUnavailable=false;
    await page.getByRole('button',{name:'读取待核对任务',exact:true}).click();await unknown.waitFor();
    await unknown.locator('textarea').fill('已检查运行环境退出并核对供应商流水，结果未知，保留额度。');
    await unknown.getByRole('button',{name:'记录证据并关闭任务',exact:true}).click();
    if(closures.length!==0)throw Error('missing acknowledgement permitted closure');
    await unknown.locator('[name=acknowledged]').check();
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('unknown mobile overflow');
    await page.screenshot({path:path.join(out,'unknown-mobile.png'),fullPage:true});
    await unknown.getByRole('button',{name:'记录证据并关闭任务',exact:true}).click();
    await page.getByText('已记录核对证据并关闭未知任务；额度保留，未重试，未认定成功。',{exact:true}).waitFor();
    if(await unknown.count()!==0||closures.length!==1)throw Error('closure UI not reconciled');
    if(await workbench.count()!==1)throw Error('studio closure removed workbench task');
    await workbench.locator('textarea').fill('已核对课程消息派发和供应商流水，无法确认结果，保留调用额度。');
    await workbench.locator('[name=acknowledged]').check();
    await workbench.getByRole('button',{name:'记录证据并关闭任务',exact:true}).click();
    await workbench.waitFor({state:'detached'});
    if(closures.length!==2||closures[1].domain!=='workbench'||closures[1].body.evidence.length<10)throw Error('workbench closure not submitted to its route');
    state.authorized=false;
    await page.getByRole('button',{name:'重新读取',exact:true}).click();
    await page.getByText('此账号没有服务端管理权限。',{exact:true}).waitFor();
    if(await page.locator('#workspace').isVisible())throw Error('revoked user can view admin UI');
    if(failures.length||unexpected.length||saves.length!==2)throw Error(JSON.stringify({failures,unexpected,saves}));
    const checks=['authorized-load','write-csrf','save-config','secret-cleared','image-fields','audit','desktop','mobile-no-overflow','unknown-acknowledgement','unknown-close-csrf','unknown-mobile','revocation-clears-ui','shared-text-scope','workbench-no-docker-dependency','two-unknown-domains','independent-domain-unavailability','workbench-close-correct-route'];
    fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({passed:true,checks,providerCalls:0,failures,unexpected},null,2));
    console.log(`Admin browser contract: ${checks.length} checks passed; providerCalls=0`);
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
