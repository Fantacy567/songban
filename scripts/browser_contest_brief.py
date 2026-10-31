from pathlib import Path
from playwright.sync_api import sync_playwright,expect
import json,os
BASE=os.environ.get('SONGBAN_TEST_BASE','http://127.0.0.1:8890/demo');OUT=Path('.browser-cache/contest-brief');OUT.mkdir(parents=True,exist_ok=True)
expect.set_options(timeout=30000)
with sync_playwright() as p:
 b=p.chromium.launch(channel='chrome',headless=True);page=b.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
 page.goto(BASE+'/');page.locator('#iv-start').click()
 for i in range(3):
  expect(page.locator('#journey-answer')).to_be_visible();page.locator('#journey-answer button[type=submit]').click()
  if i<2:expect(page.locator('#journey-answer>p').first).to_contain_text('第 '+str(i+2)+' 问')
 expect(page.locator('#iv-confirm')).to_be_visible();page.locator('#iv-confirm').click();expect(page.locator('#journey-contest')).to_be_visible();page.locator('#journey-contest button[type=submit]').click();expect(page.locator('#brief-extract')).to_be_enabled()
 assert page.url.endswith('/contest-materials')
 page.locator('#brief-extract').click();expect(page.locator('#brief-confirm')).to_be_visible()
 prize=page.locator('.brief-fact').filter(has=page.get_by_role('heading',name='奖金',exact=True));expect(prize).to_contain_text('未找到')
 page.locator('#material-files').set_input_files({'name':'主办方补充通知.txt','mimeType':'text/plain','buffer':'赛道：校园创意网页\n奖金：一等奖人民币2000元\n办赛理念：鼓励学生观察和解决身边的真实问题\n地点：校园礼堂（补充通知）'.encode()})
 page.locator('#material-input button[type=submit]').click();expect(page.locator('#material-saved')).to_contain_text('主办方补充通知.txt');expect(page.locator('#material-message')).to_contain_text('已保存');expect(page.locator('#contest-brief-results')).to_contain_text('资料已变化')
 page.locator('#brief-extract').click();expect(prize).to_contain_text('一等奖人民币2000元');expect(page.locator('#contest-brief-results')).to_contain_text('鼓励学生观察');expect(page.locator('#contest-brief-results')).to_contain_text('校园创意网页')
 for width in [390,768,1440]:
  page.set_viewport_size({'width':width,'height':1000});assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1');page.screenshot(path=str(OUT/f'facts-{width}.png'),full_page=True)
 page.reload();expect(page.locator('#contest-brief-results')).to_contain_text('一等奖人民币2000元');page.locator('#brief-confirm').click();expect(page.locator('#create-team')).to_be_visible();assert not errors,errors
 print(json.dumps({'passed':True,'checks':['contest then source import','explicit missing prize','TXT source upload','stale result','quoted amount and philosophy','refresh persistence','team continuation','390/768/1440'],'errors':errors},ensure_ascii=False));b.close()
