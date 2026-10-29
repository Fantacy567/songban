/* One-click UI installation in disposable projects; does not configure real clients. */
const {chromium}=require('/Users/ben/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs');const path=require('node:path');const os=require('node:os');const crypto=require('node:crypto');const assert=require('node:assert/strict');const {spawnSync}=require('node:child_process');
const base='http://127.0.0.1:8888';const temp='/private/tmp/songban-oneclick-acceptance-20261028';const output=path.resolve(__dirname,'../docs/core-collaboration/evidence');fs.mkdirSync(output,{recursive:true});
const credential=JSON.parse(fs.readFileSync(temp+'/private-fixture.json','utf8'))[0];const globals=path.join(os.homedir(),'.codex/config.toml');const fingerprint=()=>fs.existsSync(globals)?crypto.createHash('sha256').update(fs.readFileSync(globals)).digest('hex'):'';const before=fingerprint();
let browser;const steps=[],errors=[];
(async()=>{try{
 browser=await chromium.launch({channel:'chrome',headless:true});const context=await browser.newContext({viewport:{width:1440,height:1080}});const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base);await page.locator('#phone').fill(credential.phone);await page.locator('#password').fill(credential.password);await page.locator('#auth-form button[type=submit]').click();await page.locator('#team-switch').waitFor();
 await page.locator('#team-switch').selectOption('__new');await page.locator('#team-name').fill('一键安装 · 隔离验收');await page.locator('#create-team button').click();await page.locator('#direction-form').waitFor();await page.locator('[name=goal]').fill('验证一键安装能保留配置并真实取回团队方向');await page.locator('#direction-form button').click();await page.getByRole('status').filter({hasText:'共同方向已更新'}).waitFor();
 await page.locator('[data-tab=plugin]').click();await page.locator('#quick-install-button').waitFor();await page.waitForFunction(()=>!document.querySelector('#quick-install-button').disabled);
 const results=[];
 for(const tool of ['codex','workbuddy','cursor']){
  const project=path.join(temp,'project-'+tool+'-'+Date.now());fs.mkdirSync(project,{recursive:true});
  const original=tool==='codex'?'# existing config\nmodel = "keep-original-model"\nmodel_provider = "keep-original-provider"\n[mcp_servers.keep]\ncommand = "keep-existing"\n':JSON.stringify({mcpServers:{keep:{command:'keep-existing'}},keep:true});
  const rel=tool==='codex'?'.codex/config.toml':'.'+tool+'/mcp.json';fs.mkdirSync(path.dirname(path.join(project,rel)),{recursive:true});fs.writeFileSync(path.join(project,rel),original);
  await page.locator('#quick-tool').selectOption(tool);await page.locator('#quick-project').fill(project);
  const saved=page.waitForResponse(r=>r.url().endsWith('/install')&&r.request().method()==='POST');await page.locator('#quick-install-button').click();const response=await saved;assert.equal(response.status(),200,await response.text());const result=await response.json();assert(result.installed&&result.bridge_verified);assert.equal(result.client_loaded,false);
  await page.locator('#install-result').getByText('插件已安装，团队连接已验证。',{exact:true}).waitFor();
  const changed=fs.readFileSync(path.join(project,rel),'utf8');assert(changed.includes('keep-existing'));if(tool==='codex'){assert(changed.includes('keep-original-model'));assert(changed.includes('keep-original-provider'));}
  assert(!changed.includes('sbconn_'));assert.equal(fs.statSync(path.join(project,'.songban/connection.json')).mode&0o777,0o600);
  const lines=[{jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2024-11-05',capabilities:{},clientInfo:{name:'installed-plugin-acceptance',version:'1'}}},{jsonrpc:'2.0',id:2,method:'tools/call',params:{name:'songban_get_my_tasks',arguments:{}}}];
  // Start from a different directory to prove project pinning works.
  const run=spawnSync('python3',[path.join(project,'.songban/plugin/bridge.py'),'mcp'],{cwd:temp,env:{...process.env,SONGBAN_CONFIG:path.join(project,'.songban/connection.json'),SONGBAN_PROJECT_ROOT:project},input:lines.map(x=>JSON.stringify(x)).join('\n')+'\n',encoding:'utf8',timeout:10000});assert.equal(run.status,0);const reply=run.stdout.trim().split('\n').map(x=>JSON.parse(x)).find(r=>r.id===2).result;assert.equal(reply.isError,false);assert.equal(JSON.parse(reply.content[0].text).direction.goal,'验证一键安装能保留配置并真实取回团队方向');
  results.push({tool,installed:true,existing_settings_preserved:true,bridge_verified:true,client_loaded:false,real_task_readback:true});console.log(tool+'：按钮安装、保留原配置、桥接取回任务均通过');
 }
 await page.evaluate(()=>window.scrollTo(0,0));await page.waitForTimeout(350);await page.screenshot({path:path.join(output,'one_click_install.png'),fullPage:true});
 assert.equal(fingerprint(),before);assert.deepEqual(errors,[]);steps.push('三类项目配置由真实页面按钮写入，并实际运行安装后的MCP脚本取回团队方向。','未改动用户全局Codex配置；未在实际客户端点击信任或重载。');fs.writeFileSync(path.join(output,'one_click_install.json'),JSON.stringify({date:new Date().toISOString(),results,steps,global_codex_config_unchanged:true,errors},null,2));
}finally{if(browser)await browser.close();}})().catch(e=>{console.error(e.message);process.exitCode=1;});
