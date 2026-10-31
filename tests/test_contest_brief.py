import base64,sqlite3,tempfile,unittest,uuid
from pathlib import Path
from contextlib import closing
from unittest.mock import Mock
from fastapi.testclient import TestClient
from app.main import create_app,digest,now
from app import demo_scenario
from app.contest_brief import demo_extract
from app.planner import PlannerError

class ContestBriefTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.sqlite3';self.start()
  with closing(sqlite3.connect(self.path)) as c:
   for user in ['a','b']:c.execute('INSERT INTO people(id,name,phone,token_hash,created_at) VALUES(?,?,?,?,?)',(user,user,'synthetic-'+user,digest(user),now()))
   c.commit()
  self.h={'Authorization':'Bearer a'}
  iv=self.call('/api/core/interview/start',{})
  for answer in ['做小工具','会设计','6小时']:iv=self.call('/api/core/interview/answer',{'version':iv['version'],'question_id':iv['current_question']['id'],'request_id':uuid.uuid4().hex,'text':answer})
  self.call('/api/core/interview/confirm',{'version':iv['version'],'request_id':uuid.uuid4().hex})
  self.call('/api/journey/contest',{'name':'虚构赛','event_time':'两天','location':'线上','rubric':'完成度','requirements':'网页','deadline':'2026-11-02T18:00:00+08:00','source_text':'时间：11月1日开始\n地点：线上\n评分：完成度\n提交材料：网页'})
 def start(self):
  self.app=create_app(self.path,core_only=True,enforce_journey=True,interview_runner=demo_scenario.interview);self.app.state.contest_brief_runner=Mock(side_effect=lambda c:demo_extract(c['sources']));self.c=TestClient(self.app)
 def tearDown(self):self.c.close();self.tmp.cleanup()
 def call(self,path,body=None,status=200):
  r=self.c.request('POST' if body is not None else 'GET',path,json=body,headers=self.h);self.assertEqual(r.status_code,status,r.text);return r.json()
 def brief(self):return self.call('/api/journey/contest-materials')
 def extract(self,status=200,request_id=None):return self.call('/api/journey/contest-materials/extract',{'request_id':request_id or uuid.uuid4().hex,'expected_revision':self.brief()['revision']},status)
 def add(self,text,name='补充.txt',kind='text'):
  space=self.brief()['space_id'];r=self.call('/api/materials/spaces/'+space+'/sources',{'request_id':uuid.uuid4().hex,'kind':kind,'name':name,'nature':'organizer_notice','content':base64.b64encode(text.encode()).decode() if kind=='file' else text})
  self.call('/api/materials/spaces/'+space+'/sources/'+r['source']['id']+'/parse',{'expected_revision':self.brief()['revision']});return r['source']['id']
 def test_gate_missing_fields_quotes_idempotency_and_confirmation(self):
  self.assertEqual(self.call('/api/journey')['stage'],'contest_materials');self.call('/api/core/teams',{'name':'越级'},409);self.call('/api/core/join',{'code':'early'},409)
  key=uuid.uuid4().hex;result=self.extract(request_id=key)['result'];self.extract(request_id=key);self.assertEqual(self.app.state.contest_brief_runner.call_count,1)
  for field in ['tracks','prizes','philosophy']:self.assertEqual(result['fields'][field]['status'],'not_found')
  self.assertEqual(result['fields']['time']['citations'][0]['quote'],'时间：11月1日开始')
  self.call('/api/journey/contest-materials/confirm',{'confirmed':True,'expected_revision':self.brief()['revision']});self.assertEqual(self.call('/api/journey')['stage'],'team');self.call('/api/core/teams',{'name':'新队伍'})
 def test_fragment_file_conflicting_locations_and_restart(self):
  self.add('赛道：创意网页\n奖金：一等奖人民币2000元\n办赛理念：鼓励学生观察真实问题\n地点：校园礼堂','补充.txt','file')
  result=self.extract()['result'];self.assertEqual(result['fields']['prizes']['citations'][0]['quote'],'奖金：一等奖人民币2000元');self.assertEqual(len(result['fields']['location']['citations']),2)
  self.c.close();self.start();self.assertEqual(self.brief()['result'],result)
 def test_fabrication_rejected_previous_result_preserved_and_stale_blocks(self):
  previous=self.extract()['result'];self.add('新的通知：待补充')
  self.app.state.contest_brief_runner=Mock(return_value={'fields':{'prizes':[{'source_id':'S1','segment_id':'announcement-1','quote':'奖金一百万元'}]}})
  self.extract(502);self.assertEqual(self.brief()['result'],previous);self.assertTrue(self.brief()['stale']);self.call('/api/journey/contest-materials/confirm',{'confirmed':True,'expected_revision':self.brief()['revision']},409)
 def test_model_failure_is_not_empty_success(self):
  previous=self.extract()['result'];self.app.state.contest_brief_runner=Mock(side_effect=PlannerError('model_unavailable','服务不可用',503));self.extract(503);self.assertEqual(self.brief()['result'],previous);self.assertEqual(self.brief()['latest_run']['status'],'failed')
 def test_sources_changed_during_call_are_not_adopted(self):
  def runner(context):self.add('时间：11月3日延期');return demo_extract(context['sources'])
  self.app.state.contest_brief_runner=runner;self.extract(409);self.assertEqual(self.brief()['result'],{})
 def test_private_contest_and_no_readable_source(self):
  b=self.brief();self.assertEqual(self.c.get('/api/materials/spaces/'+b['space_id'],headers={'Authorization':'Bearer b'}).status_code,403)
  self.assertEqual(self.c.get('/api/journey/contest-materials',headers={'Authorization':'Bearer b'}).status_code,409)
  space=self.call('/api/materials/spaces/'+b['space_id']);source=space['sources'][0]
  self.call('/api/materials/spaces/'+b['space_id']+'/sources/'+source['id']+'/withdraw',{'expected_revision':b['revision']});self.extract(422)
