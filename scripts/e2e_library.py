"""Real Chrome + native/portable MCP -> HTTP -> SQLite archive, with synthetic data only."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('SONGBAN_QA_URL','http://127.0.0.1:8892');ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.browser-cache/library';OUT.mkdir(parents=True,exist_ok=True)
checks=[];errors=[]
def note(text):checks.append(text);print(text,flush=True)
def api(path,body=None,token=None):
 r=httpx.request('POST' if body is not None else 'GET',BASE+path,json=body,headers={'Authorization':'Bearer '+token} if token else {},trust_env=False);assert r.is_success,r.text;return r.json()
def register(name,number):
 phone='189'+str(time.time_ns())[-7:]+str(number);code=api('/api/studio/codes',{'phone':phone})['code'];result=api('/api/studio/register',{'phone':phone,'code':code,'password':'library-test-password','name':name,'profile':'合成验收账号','skills':'设计'});return phone,result['token']
def login(page,phone):
 page.goto(BASE+'/#/login');page.wait_for_load_state('networkidle');page.get_by_role('button',name='登录 ↗').click();page.locator('#auth-phone').fill(phone);page.locator('#auth-password').fill('library-test-password');page.locator('#auth-form button[type=submit]').click();page.wait_for_function('()=>state.me!==null')
def route(page,path):
 page.goto(BASE+'/#/'+path);page.wait_for_load_state('networkidle')
def mcp_call(script,name,args,token,team,native=False):
 with tempfile.TemporaryDirectory() as temp:
  env={**os.environ,'SONGBAN_URL':BASE,'SONGBAN_TEAM_ID':team,'SONGBAN_TOKEN':token}
  binding=Path(temp)/'binding.json';binding.write_text(json.dumps({'url':BASE,'team_id':team,'token':token}));binding.chmod(0o600)
  cmd=[sys.executable,str(ROOT/script)]+(['--binding',str(binding)] if native else ['mcp'])
  message={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}}
  run=subprocess.run(cmd,input=json.dumps(message,ensure_ascii=False)+'\n',text=True,capture_output=True,env=env,cwd=temp,timeout=25)
  assert run.returncode==0,run.stderr;result=json.loads(run.stdout.strip())['result'];assert not result.get('isError'),result;return json.loads(result['content'][0]['text'])
with sync_playwright() as p:
 browser=p.chromium.launch(channel='chrome',headless=True)
 try:
  phone_a,_=register('孔',1);phone_b,_=register('林',2)
  ca=browser.new_context(viewport={'width':1440,'height':1000});cb=browser.new_context(viewport={'width':1440,'height':1000});a=ca.new_page();b=cb.new_page()
  for page in [a,b]:page.on('pageerror',lambda e:errors.append(str(e)))
  login(a,phone_a);route(a,'team');a.locator('#team-name').fill('对话资料库验收队');a.locator('#create-team button').click();expect(a.locator('[data-share-conversation=discussion]')).to_be_visible();a.screenshot(path=str(OUT/'discussion.png'),full_page=True)
  token_a=a.evaluate('state.token');team=a.evaluate('state.team');code=a.evaluate('state.data.team.code');login(b,phone_b);route(b,'team');b.locator('#team-code').fill(code);b.locator('#join-team button').click();expect(b.locator('#confirmed-tasks')).to_be_visible();token_b=b.evaluate('state.token')
  a.locator('[data-share-conversation]').click();f=a.locator('#share-conversation');f.locator('[name=user_message]').fill('我是设计师');f.locator('[name=model_name]').fill('GPT-6.1sol');f.locator('[name=assistant_message]').fill('好的，您是设计师。我们先画一张首页草图。');f.locator('[name=consent]').check();f.locator('button[type=submit]').click();expect(a.locator('#share-conversation')).to_have_count(0)
  route(a,'idea-library');expect(a.locator('.conversation-user')).to_contain_text('孔：我是设计师');expect(a.locator('.conversation-model')).to_contain_text('GPT-6.1sol：好的，您是设计师。')
  native_token=api('/api/core/teams/'+team+'/connections',{'label':'native fixture'},token_b)['token'];portable_token=api('/api/core/teams/'+team+'/connections',{'label':'portable fixture'},token_a)['token']
  long_reply='我建议先保留一个主要操作。\n'*250+'完整回复末尾：水獭线索。';args={'selected':True,'event_id':'native-long','user_message':'请帮我检查选题。<img src=x onerror=alert(1)>','assistant_summary':'先只保留一个主操作','assistant_message':long_reply,'full_reply_authorized':True,'model_name':'协议测试模型','conversation_stage':'discussion'}
  receipt=mcp_call('plugins/songban-native/server.py','songban_sync_selected_turn',args,native_token,team,True)
  duplicate=mcp_call('plugins/songban-native/server.py','songban_sync_selected_turn',args,native_token,team,True);assert duplicate['duplicate'] and receipt['note_id']==duplicate['note_id']
  a.locator('#library-refresh').click();expect(a.locator('.conversation-record')).to_have_count(2);a.locator('[data-expand-record]').click();expect(a.locator('.conversation-model').first).to_contain_text('完整回复末尾：水獭线索。');assert a.locator('.conversation-user img').count()==0
  assert a.locator('.conversation-record').nth(0).evaluate('(e)=>getComputedStyle(e).borderLeftColor')!=a.locator('.conversation-record').nth(1).evaluate('(e)=>getComputedStyle(e).borderLeftColor')
  note('PASS topic entry, exact two-line identity/model format, stable distinct member colors, native MCP full reply, dedup, long expansion, XSS escaping')
  f=a.locator('#library-filters');f.locator('[name=query]').fill('水獭');f.locator('button').click();expect(a.locator('.conversation-record')).to_have_count(1)
  a.screenshot(path=str(OUT/'library-desktop.png'),full_page=True)
  search=mcp_call('plugins/songban-team/bridge.py','songban_search_team_library',{'query':'水獭'},portable_token,team);assert search['total']==1
  detail=mcp_call('plugins/songban-team/bridge.py','songban_read_library_record',{'record_id':receipt['note_id']},portable_token,team);assert detail['report']['assistant_message']==long_reply
  mcp_call('plugins/songban-team/bridge.py','songban_sync_selected_turn',{'selected':True,'event_id':'portable-summary','user_message':'我来做页面','assistant_summary':'先做可点击原型','model_name':'','conversation_stage':'development'},portable_token,team)
  note('PASS portable MCP scoped search, cited record read, and selected-turn archive')
  route(a,'library');expect(a.locator('.conversation-record')).to_have_count(1);expect(a.locator('.conversation-model').first).to_contain_text('模型名未获取');expect(a.locator('.conversation-record').first).to_contain_text('仅有回复要点')
  for i in range(21):api('/api/core/teams/'+team+'/conversation-notes',{'selected':True,'event_id':'page-'+str(i),'user_message':'交接记录'+str(i),'assistant_summary':'真实记录保留','model_name':'fixture','conversation_stage':'development'},token_a)
  a.locator('#library-refresh').click();expect(a.locator('.conversation-record')).to_have_count(20);a.locator('#library-more').click();expect(a.locator('.conversation-record')).to_have_count(22)
  a.locator('#library-filters [name=author]').select_option(b.evaluate('state.me.person.id'));a.locator('#library-filters button').click();expect(a.locator('.conversation-record')).to_have_count(0)
  a.locator('#library-filters [name=stage]').select_option('recap');a.locator('#library-filters button').click();expect(a.locator('.library-empty')).to_be_visible()
  a.locator('#library-filters [name=author]').select_option('');a.locator('#library-filters [name=stage]').select_option('');a.locator('#library-filters button').click();expect(a.locator('.conversation-record')).to_have_count(20)
  for width in [390,768,1440]:
   a.set_viewport_size({'width':width,'height':950});a.wait_for_timeout(150);assert a.evaluate('document.documentElement.scrollWidth<=innerWidth+1');a.evaluate('scrollTo(0,0)');a.screenshot(path=str(OUT/f'library-{width}.png'),full_page=True)
  note('PASS keyword/member/stage filters, unknown model, legacy summary, paging, 390/768/1440 responsive library')
  # Real API error response, then user-driven recovery.
  a.route('**/api/core/teams/*/library?*',lambda r:r.fulfill(status=503,content_type='application/json',body='{"error":{"message":"测试断网"}}'));a.locator('#library-refresh').click();expect(a.locator('#library-error')).to_contain_text('测试断网');a.unroute('**/api/core/teams/*/library?*');a.locator('#library-refresh').click();expect(a.locator('#library-error')).to_have_count(0)
  # Publish a fixture plan; chatting about a linked task must not report it done.
  route(a,'direction');a.locator('[name=goal]').fill('完成一个演示页面');a.locator('[name=rules]').fill('可演示的小作品');a.locator('#direction-form button').click();route(a,'collaboration');a.locator('#review').click();expect(a.locator('#confirm-plan')).to_be_visible();a.once('dialog',lambda dialog:dialog.accept());a.locator('#confirm-plan').click();a.wait_for_function('()=>state.data.plan_version===1')
  before=api('/api/core/teams/'+team,token=token_a)['active_plan']['tasks'][0]['status'];a.locator('[data-share-conversation=development]').click();f=a.locator('#share-conversation');f.locator('[name=user_message]').fill('任务实现中发现了一个问题');f.locator('[name=assistant_message]').fill('先验证空输入，再继续页面联调。');f.locator('[name=task_key]').select_option('T1');f.locator('[name=consent]').check();f.locator('button[type=submit]').click();expect(a.locator('#share-conversation')).to_have_count(0)
  after=api('/api/core/teams/'+team,token=token_a);assert after['active_plan']['tasks'][0]['status']==before
  route(a,'library');a.locator('#library-filters [name=task]').fill('T1');a.locator('#library-filters button').click();expect(a.locator('.conversation-record')).to_have_count(1);expect(a.locator('.conversation-meta')).to_contain_text('任务执行')
  a.reload();expect(a.locator('.conversation-record')).to_have_count(20);a.locator('#library-filters [name=task]').fill('T1');a.locator('#library-filters button').click();expect(a.locator('.conversation-record')).to_have_count(1);note('PASS error recovery, task-context shared dialogue without changing task status, refresh restores archive')
  assert not errors,errors;note('PASS no browser runtime errors')
 except Exception:
  if 'a' in locals():a.screenshot(path=str(OUT/'failure.png'),full_page=True)
  raise
 finally:browser.close()
(OUT/'results.json').write_text(json.dumps({'checks':checks,'browser_errors':errors,'data':'synthetic; no real SMS/model calls; native and portable MCP processes used'},ensure_ascii=False,indent=2))
