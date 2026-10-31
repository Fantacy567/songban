from pathlib import Path
from playwright.sync_api import sync_playwright,expect
import json,re,os,time
expect.set_options(timeout=30000)
BASE=os.environ.get('SONGBAN_TEST_BASE','http://127.0.0.1:8890/demo');OUT=Path('.browser-cache/unified');OUT.mkdir(parents=True,exist_ok=True)
def delay_profile(route):
 time.sleep(.35);route.continue_()
with sync_playwright() as p:
 browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
 page.goto(BASE+'/');expect(page.locator('#iv-start')).to_be_visible();page.locator('#iv-start').click()
 for _ in range(3):
  expect(page.locator('#onboard-answer')).to_be_visible();assert page.locator('#onboard-answer').input_value();page.locator('#journey-answer button[type=submit]').click()
  page.wait_for_timeout(250)
 expect(page.locator('#iv-confirm')).to_be_visible();page.locator('#iv-confirm').click();expect(page.locator('#journey-contest')).to_be_visible()
 page.locator('#contest-read').click();expect(page.locator('#contest-note')).to_contain_text('演示')
 page.screenshot(path=str(OUT/'contest.png'),full_page=True)
 page.locator('#journey-contest button[type=submit]').click();expect(page.locator('#create-team')).to_be_visible();page.locator('#create-team button[type=submit]').click();expect(page.locator('#new-idea')).to_be_visible()
 page.locator('#demo-peer').click();expect(page.locator('#demo-peer')).to_be_enabled();page.locator('#new-idea').click();expect(page.locator('#idea-title')).to_have_value('作业时间小助手');page.locator('#idea-form button[type=submit]').click();expect(page.locator('#confirm-ideas')).to_be_visible();page.locator('#confirm-ideas').click();expect(page.locator('#rank-ideas')).to_be_enabled();page.locator('#rank-ideas').click();expect(page.locator('#idea-ranking')).to_contain_text('团队适配参考分')
 page.locator('[data-confirm-topic]').first.click();expect(page.locator('#direction-form')).to_be_visible();page.locator('#direction-form button[type=submit]').click();expect(page.locator('#division-answer')).to_be_visible()
 page.goto(BASE+'/#/delivery');expect(page).to_have_url(re.compile('/division$'));expect(page.locator('#division-answer')).to_be_visible()
 page.locator('#demo-peer').click();expect(page.locator('#demo-peer')).to_be_enabled()
 for index in range(4):
  expect(page.locator('#division-text')).to_be_visible();assert page.locator('#division-text').input_value();page.locator('#division-answer button[type=submit]').click()
  if index<3:expect(page.locator('#division-answer .eyebrow')).to_contain_text(str(index+2)+' / 4')
  else:expect(page.locator('#division-confirm')).to_be_visible()
 expect(page.locator('#division-confirm')).to_be_visible();page.locator('#division-confirm').click();expect(page.locator('#confirmed-tasks')).to_be_visible()
 page.screenshot(path=str(OUT/'work.png'),full_page=True)
 page.locator('.finish-task-form button[type=submit]').first.click();expect(page.locator('.finish-task-form')).to_have_count(0);page.locator('#demo-peer').click();expect(page.locator('#demo-peer')).to_be_enabled()
 page.goto(BASE+'/#/team-work');page.get_by_role('button',name='查看小林（模拟队友）的任务').click();expect(page.locator('[data-check-task]')).to_be_visible();page.locator('[data-check-task]').first.click();page.locator('#check-form [name=verdict]').select_option('accepted');page.locator('#check-form button[type=submit]').click();expect(page.locator('#check-form')).to_have_count(0)
 page.route('**/api/core/me',delay_profile);page.evaluate("location.hash='#/delivery';setTimeout(()=>render(),50)");expect(page.locator('#journey-submit')).to_be_visible();page.unroute('**/api/core/me',delay_profile);page.locator('#journey-submit [name=confirmed]').check();page.locator('#journey-submit button[type=submit]').click();expect(page.locator('#personal-recap')).to_be_visible();assert page.locator('#recap-feelings').input_value();page.locator('#personal-recap button[type=submit]').click();expect(page.locator('#personal-recap button[type=submit]')).to_be_enabled();page.locator('#generate-recap').click();expect(page.locator('#recap-preview')).to_be_visible();page.locator('#confirm-parent-share').check();page.locator('#share-recap').click();expect(page.locator('#parent-qr img')).to_be_visible()
 for width in [390,768,1440]:
  page.set_viewport_size({'width':width,'height':1000});assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1');page.screenshot(path=str(OUT/f'review-{width}.png'),full_page=True)
 assert not errors,errors
 print(json.dumps({'passed':True,'checks':['prefilled fields','interview','contest extraction','team','idea ranking','route gate','slow navigation preserves requested route','division','task publication','peer review','receipt','recap and QR'],'errors':errors},ensure_ascii=False));browser.close()
