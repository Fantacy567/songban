"""Real Chrome, isolated SQLite and explicit synthetic model; no real SMS/model calls."""
import json,time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
BASE='http://127.0.0.1:8894'
OUT=Path(__file__).resolve().parents[1]/'.browser-cache/recap';OUT.mkdir(parents=True,exist_ok=True)
def api(path,body=None,token=''):
 r=httpx.request('POST' if body is not None else 'GET',BASE+path,json=body,headers={'Authorization':'Bearer '+token} if token else {},trust_env=False);r.raise_for_status();return r.json()
phone='189'+str(time.time_ns())[-8:];code=api('/api/studio/codes',{'phone':phone})['code']
token=api('/api/studio/register',{'phone':phone,'code':code,'password':'recap-test','name':'复盘测试同伴','profile':'合成验收','skills':'设计'})['token']
api('/api/core/teams',{'name':'复盘二维码验收'},token)
with sync_playwright() as p:
 b=p.chromium.launch(channel='chrome',headless=True)
 try:
  page=b.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE);page.evaluate('(token)=>localStorage.setItem("studio-token",token)',token);page.goto(BASE+'/#/review');page.reload();page.wait_for_load_state('networkidle')
  expect(page.locator('#generate-recap')).to_be_disabled()
  page.locator('#recap-feelings').fill('我发现沟通比写代码更难。');page.locator('#recap-ideas').fill('下次想先访谈用户。');page.locator('#recap-result').fill('完成展示，名次还未公布。');page.locator('#personal-recap button').click()
  expect(page.locator('#generate-recap')).to_be_enabled();page.reload();expect(page.locator('#recap-feelings')).to_have_value('我发现沟通比写代码更难。')
  page.locator('#generate-recap').click();expect(page.locator('#recap-preview')).to_contain_text('愿意反思合作')
  page.locator('#share-recap').click();expect(page.locator('#share-message')).to_contain_text('勾选')
  page.locator('#confirm-parent-share').check();page.locator('#share-recap').click();expect(page.locator('#parent-qr img')).to_be_visible()
  src=page.locator('#parent-qr img').get_attribute('src');assert httpx.get(BASE+src,trust_env=False).status_code==200
  url=page.get_by_role('link',name='打开家长报告',exact=True).get_attribute('href');path=url.replace('http://10.10.10.10:8894','')
  parent=b.new_page(viewport={'width':390,'height':844});parent.goto(BASE+path);parent.wait_for_load_state('networkidle');expect(parent.locator('h1')).to_contain_text('复盘测试同伴');expect(parent.locator('body')).to_contain_text('愿意反思合作');assert parent.locator('input,textarea,button').count()==0
  parent.screenshot(path=str(OUT/'parent-phone.png'),full_page=True)
  for width in [390,768,1440]:
   page.set_viewport_size({'width':width,'height':1000});assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1');page.screenshot(path=str(OUT/f'review-{width}.png'),full_page=True)
  page.locator('#revoke-recap').click();expect(page.locator('#parent-qr img')).to_have_count(0)
  assert httpx.get(BASE+path,trust_env=False).status_code==404
  assert not errors,errors
  print(json.dumps({'passed':True,'checks':['private reflection saved and reloaded','AI draft preview','explicit sharing confirmation','actual QR SVG served','parent report without login or editing','share revocation','390/768/1440 layout'],'model':'explicit fixture, no real model call','browser_errors':errors},ensure_ascii=False))
 finally:b.close()
