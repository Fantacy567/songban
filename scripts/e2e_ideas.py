"""Chrome two identities + actual native MCP transport, explicit ranking fixture."""
import json,os,subprocess,sys,tempfile,time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8894';OUT=ROOT/'.browser-cache/ideas';OUT.mkdir(parents=True,exist_ok=True)
def api(path,body=None,token='',method=None):
 r=httpx.request(method or ('POST' if body is not None else 'GET'),BASE+path,json=body,headers={'Authorization':'Bearer '+token} if token else {},trust_env=False,timeout=30);assert r.is_success,r.text;return r.json()
def register(name,n):
 phone='189'+str(time.time_ns())[-7:]+str(n);code=api('/api/studio/codes',{'phone':phone})['code'];return api('/api/studio/register',{'phone':phone,'code':code,'password':'ideas-test','name':name,'profile':'合成测试','skills':'页面设计'})['token']
def visit(page,route):page.goto(BASE+'/#/'+route);page.wait_for_load_state('networkidle')
def mcp(name,args,token,team):
 with tempfile.TemporaryDirectory() as tmp:
  binding=Path(tmp)/'binding.json';binding.write_text(json.dumps({'url':BASE,'team_id':team,'token':token}));binding.chmod(0o600)
  request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}}
  result=subprocess.run([sys.executable,str(ROOT/'plugins/songban-native/server.py'),'--binding',str(binding)],input=json.dumps(request,ensure_ascii=False)+'\n',text=True,capture_output=True,timeout=25)
  assert result.returncode==0,result.stderr;response=json.loads(result.stdout)['result'];assert not response.get('isError'),response;return json.loads(response['content'][0]['text'])
ta=register('孔',1);tb=register('林',2);team=api('/api/core/teams',{'name':'选题适配验收'},ta);sid=team['id'];base='/api/core/teams/'+sid;api('/api/core/join',{'code':team['code']},tb)
for token in [ta,tb]:api(base+'/profile',{'strengths':'页面设计与基本编码','willingness':'做简单的工具','hours':3},token,'PUT')
snap=api(base,token=ta);api(base+'/topic/criteria',{'rubric':'用户价值50%，作品可用性50%','rules':'公开规则：两天完成原型','deadline':''},ta,'PUT')
with sync_playwright() as p:
 browser=p.chromium.launch(channel='chrome',headless=True)
 try:
  a,b=[browser.new_page(viewport={'width':1440,'height':1000}) for _ in range(2)];errors=[]
  for page,token in [(a,ta),(b,tb)]:
   page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE);page.evaluate('(token)=>localStorage.setItem("studio-token",token)',token);page.reload();page.wait_for_load_state('networkidle');visit(page,'ideas')
  for page,title in [(a,'校园问题小工具'),(b,'大型通用智能平台')]:
   page.locator('#new-idea').click();page.locator('#idea-title').fill(title);page.locator('#idea-problem').fill('帮助同学找到有用信息');page.locator('#idea-proposal').fill('先做一个能演示的小范围原型，投入3小时试用和改进');page.locator('#idea-form button').click();expect(page.locator('#idea-form')).to_have_count(0)
  expect(a.locator('.practice-tabs a[href="#/work"]')).to_have_count(0);expect(a.locator('.practice-tabs a[href="#/direction"]')).to_have_count(0)
  expect(a.locator('.idea-card')).to_have_count(2,timeout=10000);expect(a.locator('#rank-ideas')).to_be_disabled()
  own=next(idea for idea in api(base+'/ideas',token=ta)['ideas'] if idea['user_id']==api('/api/core/me',token=ta)['person']['id'])
  connection=api(base+'/connections',{'label':'原生选题验收'},ta)
  catalog=mcp('songban_get_topic_ideas',{},connection['token'],sid);assert len(catalog['ideas'])==2
  mcp('songban_sync_selected_turn',{'selected':True,'event_id':'ideas-native-turn','idea_id':own['id'],'conversation_stage':'discussion','user_message':'校园工具用我们三小时能做吗？','assistant_summary':'先做最小查询流程。','assistant_message':'根据页面设计能力，可以先做一个最小的校园查询原型，仍需实际试用。','full_reply_authorized':True,'model_name':'协议测试模型'},connection['token'],sid)
  expect(b.locator('#idea-conversations')).to_contain_text('校园工具用我们三小时能做吗？',timeout=10000)
  expect(b.locator('[data-inline-idea="'+own['id']+'"]')).to_contain_text('校园工具用我们三小时能做吗？')
  a.locator('#confirm-ideas').click();b.locator('#confirm-ideas').click();expect(a.locator('#rank-ideas')).to_be_enabled(timeout=10000)
  before=api(base,token=ta)['direction'];a.locator('#rank-ideas').click();expect(a.locator('.idea-ranked').first).to_contain_text('校园问题小工具',timeout=15000);expect(b.locator('.idea-ranked').first).to_contain_text('校园问题小工具',timeout=10000)
  assert api(base,token=ta)['direction']==before
  a.once('dialog',lambda dialog:dialog.accept());a.locator('[data-confirm-topic="'+own['id']+'"]').first.click();expect(a.locator('#direction-form')).to_be_visible();assert api(base,token=ta)['topic_confirmed']
  b.wait_for_function('()=>state.data?.topic_confirmed===true')
  fp=api(base+'/ideas',token=ta)['fingerprint']
  api(base+'/conversation-notes',{'selected':True,'event_id':'development-only','conversation_stage':'development','user_message':'开发阶段独立内容','assistant_summary':'实现接口'},ta)
  assert api(base+'/ideas',token=ta)['fingerprint']==fp
  visit(b,'library');expect(b.locator('#library-notes')).to_contain_text('开发阶段独立内容');expect(b.locator('#library-notes')).not_to_contain_text('校园工具用我们三小时能做吗？')
  visit(b,'idea-library');expect(b.locator('#library-notes')).to_contain_text('校园工具用我们三小时能做吗？');expect(b.locator('#library-notes')).not_to_contain_text('开发阶段独立内容')
  for width in [390,768,1440]:
   a.set_viewport_size({'width':width,'height':1000})
   for route in ['ideas','idea-library','library']:
    visit(a,route);a.locator('#new-idea' if route=='ideas' else '#library-count').wait_for();assert not a.evaluate('document.documentElement.scrollWidth>innerWidth+1'),(width,route);a.screenshot(path=str(OUT/f'{route}-{width}.png'),full_page=True)
  assert '校园问题小工具' in api(base,token=ta)['direction']['goal']
  assert not errors,errors
  print(json.dumps({'passed':True,'checks':['two-member public idea creation','native MCP idea catalog and associated conversation upload','all-member visibility','confirmation gate','team-fit ranking fixture','ranking never selects direction','discussion/development separation','development update does not stale ranking','draft-only adoption','390/768/1440'],'model':'explicit protocol fixture; no real ranking model call','browser_errors':errors},ensure_ascii=False))
 finally:browser.close()
