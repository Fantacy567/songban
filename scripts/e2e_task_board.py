"""Real Chrome: two identities, completion, peer review, live updates and reload."""
import json,time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
BASE='http://127.0.0.1:8894'
OUT=Path(__file__).resolve().parents[1]/'.browser-cache/task-board'
OUT.mkdir(parents=True,exist_ok=True)
def api(path,body=None,token=None,method=None):
    r=httpx.request(method or ('POST' if body is not None else 'GET'),BASE+path,json=body,headers={'Authorization':'Bearer '+token} if token else {},timeout=30,trust_env=False)
    assert r.is_success,r.text
    return r.json()
def register(name,n):
    phone='189'+str(time.time_ns())[-7:]+str(n)
    code=api('/api/studio/codes',{'phone':phone})['code']
    return api('/api/studio/register',{'phone':phone,'code':code,'password':'task-board-test','name':name,'profile':'合成测试','skills':'设计'})['token']
def visit(page,route):
    page.goto(BASE+'/#/'+route);page.wait_for_load_state('networkidle')
def member_card(page,name):return page.get_by_role('button',name='查看'+name+'的任务',exact=True)
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    try:
        ta=register('孔',1);tb=register('林',2)
        team=api('/api/core/teams',{'name':'任务双页验收'},ta);sid=team['id'];base='/api/core/teams/'+sid
        api('/api/core/join',{'code':team['code']},tb)
        snapshot=api(base,token=ta)
        api(base+'/direction',{'goal':'完成一个首页','rules':'提交可运行作品','rubric':'展示核心流程','non_goals':'不做支付','deadline':'','expected_revision':snapshot['revision']},ta,'PUT')
        plan=api(base+'/review',{},ta);api(base+'/proposals/'+plan['proposal_id']+'/confirm',{'expected_revision':plan['base_revision']},ta)
        contexts=[browser.new_context(viewport={'width':1440,'height':1000}) for _ in range(2)]
        a,b=[context.new_page() for context in contexts];errors=[]
        for page,token in [(a,ta),(b,tb)]:
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(BASE);page.evaluate('(token)=>localStorage.setItem("studio-token",token)',token);page.reload();page.wait_for_load_state('networkidle')
        visit(a,'work');visit(b,'team-work')
        expect(a.locator('.personal-task')).to_have_count(2)
        expect(a.locator('.personal-progress progress')).to_have_attribute('value','0')
        expect(member_card(b,'孔').locator('progress')).to_have_attribute('value','0')
        a.locator('[data-start-task=T1]').click()
        expect(member_card(b,'孔').locator('.task-current')).to_have_text('正在做：画出首页草图',timeout=10000)
        a.locator('#task-T1 textarea').fill('草图已完成：包含输入、结果和返回路径')
        a.locator('#task-T1 button[type=submit]').click()
        expect(a.locator('.personal-progress progress')).to_have_attribute('value','50')
        expect(member_card(b,'孔').locator('progress')).to_have_attribute('value','50',timeout=10000)
        expect(a.locator('#my-task-accepted')).to_have_text('其中 0 项已通过同伴检查')
        member_card(b,'孔').click();b.locator('[data-check-task=T1]').click()
        b.locator('#check-verdict').select_option('accepted');b.locator('#check-note').fill('已查看草图，核心操作有去有回');b.locator('#check-form button[type=submit]').click()
        expect(a.locator('#my-task-accepted')).to_have_text('其中 1 项已通过同伴检查',timeout=10000)
        # A second tab sees a completed task without manual refresh.
        team_tab=contexts[0].new_page();visit(team_tab,'team-work')
        a.locator('[data-start-task=T2]').click();expect(member_card(b,'孔').locator('.task-current')).to_have_text('正在做：完成交互说明',timeout=10000)
        a.locator('#task-T2 textarea').fill('说明按钮点击后的校验、加载和返回结果')
        a.route('**/reports',lambda route:route.fulfill(status=503,content_type='application/json',body=json.dumps({'error':{'message':'测试网络中断'}})))
        a.locator('#task-T2 button[type=submit]').click();expect(a.locator('#finish-task-1 .error')).to_contain_text('测试网络中断')
        expect(a.locator('.personal-progress progress')).to_have_attribute('value','50')
        expect(a.locator('#task-T2 textarea')).to_have_value('说明按钮点击后的校验、加载和返回结果')
        a.unroute('**/reports');a.locator('#task-T2 button[type=submit]').click()
        expect(a.locator('.personal-progress progress')).to_have_attribute('value','100')
        expect(member_card(b,'孔').locator('progress')).to_have_attribute('value','100',timeout=10000)
        expect(member_card(team_tab,'孔').locator('progress')).to_have_attribute('value','100',timeout=10000)
        a.reload();expect(a.locator('.personal-progress progress')).to_have_attribute('value','100')
        # Only personal tasks appear; dependent task becomes actionable after peer acceptance.
        visit(b,'work');expect(b.locator('.personal-task')).to_have_count(1);expect(b.locator('[data-start-task=T3]')).to_be_enabled()
        visit(b,'team-work');member_card(b,'孔').click();b.locator('[data-check-task=T2]').click();b.locator('#check-note').fill('补充异常状态的交互说明');b.locator('#check-form button[type=submit]').click()
        expect(a.locator('.personal-progress progress')).to_have_attribute('value','50',timeout=10000)
        expect(a.locator('#task-T2')).to_contain_text('退回修改')
        for width in [390,768,1440]:
            a.set_viewport_size({'width':width,'height':1000})
            for route in ['work','team-work']:
                visit(a,route);assert not a.evaluate('document.documentElement.scrollWidth>innerWidth+1'),(width,route)
                a.screenshot(path=str(OUT/f'{route}-{width}.png'),full_page=True)
        assert not errors,errors
        result={'passed':True,'checks':['personal task isolation','0→50→100 progress','two identities and cross-tab live synchronization','current task broadcast','peer acceptance distinct from self-completion','failed save preserves progress and input','reload persistence','returned task reduces progress','dependency gate','390/768/1440 responsive'],'browser_errors':errors}
        (OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
    finally:browser.close()
