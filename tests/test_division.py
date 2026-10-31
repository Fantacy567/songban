import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import create_app
from tests import test_team_core as fixtures

class DivisionTests(unittest.TestCase):
    setUp=fixtures.CoreTests.setUp
    tearDown=fixtures.CoreTests.tearDown
    snap=fixtures.CoreTests.snap
    def start(self):
        r=self.client.put(self.base+'/direction',headers=self.h('a'),json={'goal':'完成可演示的首页','rules':'提交可运行链接','rubric':'用户价值与可用性','expected_revision':self.snap()['revision']});self.assertEqual(r.status_code,200,r.text)
    def state(self,user):return self.client.get(self.base+'/division',headers=self.h(user)).json()
    def answers(self,user):
        for text in ['负责自己的模块','基础工作独立做，复杂问题请AI和队友帮忙','3','上传可查看成果，让队友按流程检查']:
            d=self.state(user);r=self.client.post(self.base+'/division/answers',headers=self.h(user),json={'round_id':d['round_id'],'step':d['me']['step'],'answer':text});self.assertEqual(r.status_code,200,r.text)
    def confirm(self,user):
        return self.client.post(self.base+'/division/confirm',headers=self.h(user),json={'round_id':self.state(user)['round_id'],'confirmed':True})
    def test_personalized_questions_resume_and_internal_publication(self):
        self.client.put(self.base+'/profile',headers=self.h('a'),json={'strengths':'界面设计','willingness':'设计草图','hours':3})
        self.client.put(self.base+'/profile',headers=self.h('b'),json={'strengths':'后端开发','willingness':'实现接口','hours':3})
        self.start();self.assertNotEqual(self.state('a')['me']['question'],self.state('b')['me']['question'])
        d=self.state('a');self.client.post(self.base+'/division/answers',headers=self.h('a'),json={'round_id':d['round_id'],'step':0,'answer':'负责首页设计'})
        self.assertIn('负责首页设计',self.state('a')['me']['question'])
        for text in ['能独立画草图','3','上传原型让队友试走']:
            d=self.state('a');self.client.post(self.base+'/division/answers',headers=self.h('a'),json={'round_id':d['round_id'],'step':d['me']['step'],'answer':text})
        self.assertEqual(self.confirm('a').json()['status'],'waiting');self.assertEqual(self.snap()['plan_version'],0)
        self.answers('b');published=self.confirm('b');self.assertEqual(published.status_code,200,published.text)
        self.assertEqual(published.json()['status'],'published');self.assertEqual(self.snap()['plan_version'],1)
        self.confirm('b');self.assertEqual(self.snap()['plan_version'],1)
        history=self.client.get(self.base+'/history',headers=self.h('a')).json();self.assertIn('internal-ai',str(history))
    def test_incomplete_confirmation_and_manual_captain_publish_blocked(self):
        self.start();self.assertEqual(self.confirm('a').status_code,409)
        r=self.client.post(self.base+'/proposals/nonexistent/confirm',headers=self.h('a'),json={'expected_revision':self.snap()['revision']});self.assertEqual(r.status_code,409)
    def test_failure_preserves_confirmations_and_explicit_retry(self):
        self.start();self.answers('a');self.answers('b');self.confirm('a')
        with patch('app.team_core.request_model',side_effect=RuntimeError('network test')):
            with TestClient(create_app(self.path,core_only=True)) as c:
                r=c.post(self.base+'/division/confirm',headers=self.h('b'),json={'round_id':self.state('b')['round_id'],'confirmed':True});self.assertEqual(r.json()['status'],'failed')
        self.assertTrue(self.state('a')['all_confirmed']);self.assertEqual(self.snap()['plan_version'],0)
        r=self.client.post(self.base+'/division/publish',headers=self.h('b'),json={});self.assertEqual(r.json()['status'],'published')
    def test_direction_change_starts_fresh_round_without_destroying_old_answers(self):
        self.start();old=self.state('a')['round_id'];self.answers('a')
        r=self.client.put(self.base+'/direction',headers=self.h('a'),json={'goal':'改为只做一页','expected_revision':self.snap()['revision']});self.assertEqual(r.status_code,200)
        self.assertNotEqual(old,self.state('a')['round_id']);self.assertEqual(self.state('a')['me']['step'],0)
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.path)) as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM division_answers WHERE round_id=?',(old,)).fetchone()[0],1)

    def test_concurrent_confirmation_only_calls_model_once(self):
        import threading
        self.start();self.answers('a');self.answers('b');self.confirm('a')
        started=threading.Event();release=threading.Event();calls=[];results=[]
        def slow(ctx):
            calls.append(ctx);started.set();release.wait(5);return fixtures.plan_for(ctx)
        with TestClient(create_app(self.path,core_only=True,core_model_runner=slow)) as client:
            body={'round_id':self.state('b')['round_id'],'confirmed':True}
            worker=threading.Thread(target=lambda:results.append(client.post(self.base+'/division/confirm',headers=self.h('b'),json=body)))
            worker.start()
            try:
                self.assertTrue(started.wait(3))
                duplicate=client.post(self.base+'/division/confirm',headers=self.h('b'),json=body)
                self.assertEqual(duplicate.json()['status'],'running')
            finally:release.set();worker.join(5)
        self.assertEqual(len(calls),1);self.assertEqual(results[0].json()['status'],'published');self.assertEqual(self.snap()['plan_version'],1)

    def test_ai_omitting_a_confirmed_member_is_rejected(self):
        self.start();self.answers('a');self.answers('b');self.confirm('a')
        def missing(ctx):
            plan=fixtures.plan_for(ctx)
            for task in plan['tasks']:task['owner_id']='a'
            return plan
        with TestClient(create_app(self.path,core_only=True,core_model_runner=missing)) as client:
            result=client.post(self.base+'/division/confirm',headers=self.h('b'),json={'round_id':self.state('b')['round_id'],'confirmed':True})
        self.assertEqual(result.json()['status'],'failed');self.assertEqual(self.snap()['plan_version'],0)
        self.assertIn('遗漏',result.json()['error'])

    def test_interview_resumes_after_restart_and_invalid_empty_state_is_handled(self):
        self.assertEqual(self.client.post(self.base+'/division/confirm',headers=self.h('a'),json={'confirmed':True}).status_code,409)
        self.assertEqual(self.client.post(self.base+'/division/reset',headers=self.h('a'),json={}).status_code,409)
        self.start();self.answers('a');self.confirm('a')
        with TestClient(create_app(self.path,core_only=True,core_model_runner=fixtures.plan_for)) as client:
            result=client.get(self.base+'/division',headers=self.h('a')).json()
        self.assertTrue(result['me']['confirmed']);self.assertEqual(len(result['me']['answers']),4)
        self.assertEqual(self.snap()['workflow']['next_action']['page'],'division')

    def test_old_background_drafting_is_disabled_for_new_coordination(self):
        self.client.put(self.base+'/automation',headers=self.h('a'),json={'enabled':True})
        self.start()
        self.assertFalse(self.snap()['auto_review'])
        self.assertEqual(self.client.put(self.base+'/automation',headers=self.h('a'),json={'enabled':True}).status_code,409)
