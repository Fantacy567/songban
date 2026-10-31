"""Strict production gates; unlike legacy suites these never disable the lifecycle."""
import sqlite3,tempfile,uuid,unittest,json
from pathlib import Path
from contextlib import closing
from fastapi.testclient import TestClient
from app.main import create_app,digest,now
from app import demo_scenario
class UnifiedTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'test.sqlite3';self.start()
  with closing(sqlite3.connect(self.path)) as con:
   for key in ['a','b']:con.execute('INSERT INTO people(id,name,phone,skills,token_hash,created_at) VALUES(?,?,?,?,?,?)',(key,key,'test-'+key,'设计',digest('token-'+key),now()))
   con.commit()
  self.user='a'
 def start(self):self.app=create_app(self.path,core_only=True,enforce_journey=True,interview_runner=demo_scenario.interview,core_model_runner=demo_scenario.plan,idea_model_runner=demo_scenario.ranking,recap_model_runner=demo_scenario.recap);self.c=TestClient(self.app)
 def tearDown(self):self.c.close();self.temp.cleanup()
 def call(self,path,body=None,method=None,status=200):
  r=self.c.request(method or ('POST' if body is not None else 'GET'),path,headers={'Authorization':'Bearer token-'+self.user},json=body);self.assertEqual(r.status_code,status,r.text);return r.json()
 def onboard(self):
  d=self.call('/api/core/interview/start',{})
  for text in ['做校园小工具','画草图，开发请队友帮助','6小时']:
   d=self.call('/api/core/interview/answer',{'version':d['version'],'question_id':d['current_question']['id'],'request_id':uuid.uuid4().hex,'text':text})
  self.call('/api/core/interview/confirm',{'version':d['version'],'request_id':uuid.uuid4().hex})
 def contest(self):return self.call('/api/journey/contest',{'name':'虚构赛','event_time':'两天','location':'线上','rubric':'价值与完成度','requirements':'代码和演示','deadline':'2026-11-02T18:00:00+08:00','source_text':'虚构公告'})
 def test_real_mode_gate_and_no_demo_endpoint(self):
  self.call('/api/core/teams',{'name':'绕过访谈'},status=409);self.call('/api/core/join',{'code':'bad'},status=409)
  self.call('/api/demo/bootstrap',{},status=404)
  self.assertFalse(self.call('/api/journey')['demo']);self.onboard();self.call('/api/core/teams',{'name':'绕过赛事'},status=409)
  self.call('/api/journey/contest',{'name':'未填写'},status=422);self.contest();team=self.call('/api/core/teams',{'name':'队伍'});base='/api/core/teams/'+team['id']
  for suffix in ['/division','/recap','/my-tasks']:self.call(base+suffix,status=409)
  self.call(base+'/direction',{'goal':'绕过选题','expected_revision':1},'PUT',409)
  self.call(base+'/proposals/fake/confirm',{},status=409)
 def test_restart_preserves_stage_and_profile_is_private(self):
  self.onboard();self.contest();self.c.close();self.start();self.assertEqual(self.call('/api/journey')['stage'],'team')
  self.user='b';self.assertEqual(self.call('/api/core/interview')['status'],'not_started');self.assertEqual(self.call('/api/journey')['stage'],'interview')
 def test_unconfirmed_and_stale_member_ideas_cannot_select(self):
  self.onboard();self.contest();team=self.call('/api/core/teams',{'name':'队伍'});base='/api/core/teams/'+team['id']
  self.user='b';self.onboard();self.call('/api/core/join',{'code':team['code']});self.call(base+'/ideas/ready',{'confirmed':True})
  self.user='a';idea=self.call(base+'/ideas',{'title':'小工具','problem':'问题','proposal':'方案'});self.call(base+'/topic/confirm',{'idea_id':idea['id'],'confirmed':True},status=409)
  self.call(base+'/ideas/ready',{'confirmed':True});self.user='b';self.call(base+'/ideas',{'title':'新想法','problem':'新问题','proposal':'新方案'})
  self.user='a';self.call(base+'/topic/confirm',{'idea_id':idea['id'],'confirmed':True},status=409)
 def test_submission_cannot_bypass_checks(self):
  self.onboard();self.contest();team=self.call('/api/core/teams',{'name':'队伍'});base='/api/core/teams/'+team['id']
  self.call('/api/journey/teams/'+team['id']+'/submission',{'receipt':'fake','materials':'fake','confirmed':True},status=409)
  self.call(base+'/recap',{'expected_version':0,'feelings':'提前复盘','result':'fake'},'PUT',409)
