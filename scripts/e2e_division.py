"""Two members, personalized questions, internal fixture publication and task claiming."""
import json,time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
BASE='http://127.0.0.1:8894';OUT=Path(__file__).resolve().parents[1]/'.browser-cache/division';OUT.mkdir(parents=True,exist_ok=True)
def api(path,body=None,token='',method=None):
 r=httpx.request(method or ('POST' if body is not None else 'GET'),BASE+path,json=body,headers={'Authorization':'Bearer '+token} if token else {},trust_env=False,timeout=30);assert r.is_success,r.text;return r.json()
def reg(name,n):
 phone='189'+str(time.time_ns())[-7:]+str(n);code=api('/api/studio/codes',{'phone':phone})['code'];return api('/api/studio/register',{'phone':phone,'code':code,'password':'division-test','name':name,'profile':'合成测试','skills':'设计'})['token']
def visit(page,route):page.goto(BASE+'/#/'+route);page.wait_for_load_state('networkidle')
ta=reg('设计同伴',1);tb=reg('开发同伴',2);team=api('/api/core/teams',{'name':'精简流程验收'},ta);base='/api/core/teams/'+team['id'];api('/api/core/join',{'code':team['code']},tb)
for token,skill in [(ta,'界面设计'),(tb,'后端开发')]:api(base+'/profile',{'strengths':skill,'willingness':skill,'hours':3},token,'PUT')
idea=api(base+'/ideas',{'title':'校园查询工具','problem':'帮同学查询信息','proposal':'先做一页原型'},ta);api(base+'/topic/confirm',{'idea_id':idea['id'],'confirmed':True},ta)
with sync_playwright() as p:
 browser=p.chromium.launch(channel='chrome',headless=True)
 try:
  a,b=[browser.new_page(viewport={'width':1440,'height':1000}) for _ in range(2)];errors=[]
  for page,token in [(a,ta),(b,tb)]:
   page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE);page.evaluate('(t)=>localStorage.setItem("studio-token",t)',token);page.reload();page.wait_for_load_state('networkidle')
  visit(a,'direction');a.locator('#direction-form [name=goal]').fill('完成一个可演示首页');a.locator('#direction-form button[type=submit]').click();expect(a.locator('#division-answer')).to_be_visible()
  visit(b,'division');expect(b.locator('#division-answer')).to_be_visible();assert a.locator('#division-answer h2').inner_text()!=b.locator('#division-answer h2').inner_text()
  visit(b,'delivery');expect(b.locator('#division-answer')).to_be_visible();assert b.url.endswith('/division')
  a.screenshot(path=str(OUT/'question-1440.png'),full_page=True)
  a.set_viewport_size({'width':390,'height':1000});a.screenshot(path=str(OUT/'question-390.png'),full_page=True);a.set_viewport_size({'width':1440,'height':1000})
  def answer(page):
   for index,text in enumerate(['负责自己的模块','基础工作独立做，复杂部分请队友帮助','3','上传可查看成果，让队友按流程检查']):
    field=page.locator('#division-text');field.fill(text);page.locator('#division-answer button[type=submit]').click()
    if index<3:expect(page.locator('#division-answer .eyebrow')).to_contain_text(str(index+2)+' / 4')
   expect(page.locator('#division-confirm')).to_be_visible()
  answer(a);a.locator('#division-confirm').click();expect(a.locator('#content')).to_contain_text('等待其他成员');assert api(base,token=ta)['plan_version']==0
  b.reload();expect(b.locator('#division-answer')).to_be_visible();answer(b);b.locator('#division-confirm').click();expect(b.locator('#confirmed-tasks')).to_be_visible(timeout=15000)
  assert api(base,token=ta)['plan_version']==1
  a.locator('a[href="#/work"]').first.wait_for();visit(a,'work');expect(a.locator('[data-start-task=T1]')).to_be_enabled();a.locator('[data-start-task=T1]').click();expect(a.locator('#task-T1')).to_contain_text('进行中')
  assert a.get_by_role('button',name='确认并发布',exact=False).count()==0
  assert a.locator('.practice-tabs').inner_text().split()==['选题','方向','分工','任务','提交','复盘']
  for width in [390,768,1440]:
   a.set_viewport_size({'width':width,'height':1000})
   for route in ['direction','division','work','team-work','delivery','review']:
    visit(a,route);assert not a.evaluate('document.documentElement.scrollWidth>innerWidth+1'),(width,route)
    if route in ['division','work']:a.screenshot(path=str(OUT/f'{route}-{width}.png'),full_page=True)
  assert not errors,errors
  print(json.dumps({'passed':True,'checks':['direction save enters coordination','personalized questions','one question at a time and resume','all-member consent gate','AI publishes without captain click','task claim','direct stage gate','six-stage navigation','390/768/1440','completion and review routes retained'],'browser_errors':errors},ensure_ascii=False))
 finally:browser.close()
