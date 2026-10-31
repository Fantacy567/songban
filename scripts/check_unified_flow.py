import uuid,json,os
import httpx
BASE=os.environ.get('SONGBAN_TEST_BASE','http://127.0.0.1:8890/demo');headers={'X-Songban-Demo':str(uuid.uuid4())}
c=httpx.Client(base_url=BASE,headers=headers,trust_env=False,timeout=60)
def call(path,body=None,method=None,expected=200):
 r=c.request(method or ('POST' if body is not None else 'GET'),path,json=body);assert r.status_code==expected,(path,r.status_code,r.text);return r.json()
token=call('/api/demo/bootstrap',{})['token'];c.headers['Authorization']='Bearer '+token
call('/api/core/teams',{'name':'越级'},expected=409)
iv=call('/api/core/interview/start',{})
for text in ['想做作业时间工具','我会设计和流程说明','6小时']:
 iv=call('/api/core/interview/answer',{'version':iv['version'],'question_id':iv['current_question']['id'],'request_id':uuid.uuid4().hex,'text':text})
assert iv['status']=='pending_confirmation',iv
call('/api/core/teams',{'name':'越级'},expected=409)
call('/api/core/interview/confirm',{'version':iv['version'],'request_id':uuid.uuid4().hex})
assert call('/api/journey')['stage']=='contest'
call('/api/core/teams',{'name':'越级'},expected=409)
contest={'name':'虚构赛','event_time':'两天','location':'线上','rubric':'完成度40%，价值40%，协作20%','requirements':'代码与演示','source_text':'虚构公告','deadline':'2026-11-02T18:00:00+08:00'}
call('/api/journey/contest',contest)
team=call('/api/core/teams',{'name':'演示团队'});base='/api/core/teams/'+team['id'];flow=lambda:call('/api/journey?team_id='+team['id'])
call(base+'/recap',expected=409)
call('/api/demo/peer',{})
idea=call(base+'/ideas',{'title':'作业小工具','problem':'不清楚顺序','proposal':'一页安排'})
call(base+'/topic/confirm',{'idea_id':idea['id'],'confirmed':True},expected=409)
call(base+'/ideas/ready',{'confirmed':True});board=call(base+'/ideas')
rank=call(base+'/ideas/rank',{'request_id':uuid.uuid4().hex,'expected_fingerprint':board['fingerprint']});assert rank['status']=='ready',rank
call(base+'/topic/confirm',{'idea_id':idea['id'],'confirmed':True});snap=call(base)
call(base+'/direction',{**snap['direction'],'expected_revision':snap['revision']},'PUT')
call('/api/demo/peer',{})
d=call(base+'/division')
for answer in ['设计草图','可独立做基础设计，开发求助','6','提交图片，检查三步操作']:
 d=call(base+'/division/answers',{'round_id':d['round_id'],'step':d['me']['step'],'answer':answer})
pub=call(base+'/division/confirm',{'round_id':d['round_id'],'confirmed':True});assert pub['status']=='published',pub
snap=call(base);mine=next(t for t in snap['active_plan']['tasks'] if t['owner_id']==snap['me']['id'])
call('/api/journey/teams/'+team['id']+'/submission',{'confirmed':True,'materials':'模拟','receipt':'模拟'},expected=409)
call(base+'/reports',{'event_id':uuid.uuid4().hex,'tool':'演示网页','origin':'human','summary':'完成了草图','evidence':['虚构演示成果：三个步骤'],'task_key':mine['key'],'plan_version':snap['plan_version'],'status':'reported_done'})
call('/api/demo/peer',{});snap=call(base)
peer=next(t for t in snap['active_plan']['tasks'] if t['owner_id']!=snap['me']['id'])
call(base+'/tasks/'+peer['key']+'/check',{'expected_revision':snap['revision'],'plan_version':snap['plan_version'],'report_id':peer['latest_report_id'],'verdict':'accepted','note':'虚构演示：逐步检查通过'})
assert flow()['stage']=='delivery',flow()
call(base+'/recap',expected=409)
call('/api/journey/teams/'+team['id']+'/submission',{'confirmed':True,'materials':'模拟网页与说明','receipt':'DEMO-01虚构回执'})
assert flow()['stage']=='review'
call(base+'/recap',{'expected_version':0,'feelings':'先画流程减少返工','ideas':'下次早点试用','result':'虚构比赛展示完成'},'PUT')
report=call(base+'/recap/reports',{'request_id':uuid.uuid4().hex,'expected_version':1});assert report['status']=='ready',report
share=call(base+'/recap/reports/'+report['id']+'/share',{'confirmed':True})
print(json.dumps({'passed':True,'checks':['interview gate','contest gate','team readiness','ranking output','internal AI publication','peer acceptance','receipt gate','recap report'],'demo':True,'report_id':report['id']},ensure_ascii=False))
