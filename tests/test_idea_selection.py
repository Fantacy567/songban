import unittest
from fastapi.testclient import TestClient
from app.main import create_app
from tests import test_team_core as fixtures

class IdeaSelectionTests(unittest.TestCase):
    tearDown=fixtures.CoreTests.tearDown
    def setUp(self):
        fixtures.CoreTests.setUp(self);self.client.close();self.calls=[];self.invalid=False
        def model(context):
            self.calls.append(context);items=[]
            for source in context['sources']:
                if source['kind']!='idea':continue
                good='校园' in source['title']
                items.append({'idea_id':source['id'],'capability':90 if good else 30,'time':95 if good else 20,'rubric':80 if good else 95,'reasons':{'capability':'按本队已填写能力判断','time':'按本人可投入小时和方案范围判断','rubric':'按公开评分维度判断'},'risks':['尚需实际验证'],'source_ids':[source['id'],'M1','missing' if self.invalid else 'R']})
            return {'assessments':items}
        self.app=create_app(self.path,core_only=True,idea_model_runner=model);self.client=TestClient(self.app)
        self.a=self.idea('a','大型通用平台');self.b=self.idea('b','校园问题小工具')
    def idea(self,user,title):
        r=self.client.post(self.base+'/ideas',headers=self.h(user),json={'title':title,'problem':'帮同学解决问题','proposal':'先做一个可演示的小原型，验证使用流程'})
        self.assertEqual(r.status_code,200,r.text);return r.json()['id']
    def board(self):return self.client.get(self.base+'/ideas',headers=self.h('a')).json()
    def prepare(self):
        for user in ['a','b']:
            r=self.client.put(self.base+'/profile',headers=self.h(user),json={'strengths':'页面设计与基本编码','willingness':'一起做小工具','hours':3});self.assertEqual(r.status_code,200,r.text)
        snap=self.client.get(self.base,headers=self.h('a')).json()
        self.client.put(self.base+'/direction',headers=self.h('a'),json={'expected_revision':snap['revision'],'goal':'先讨论','rubric':'用户价值50%，作品可用性50%','rules':'公开通知：两天内提交演示','non_goals':'','deadline':''})
        for user in ['a','b']:self.client.post(self.base+'/ideas/ready',headers=self.h(user),json={'confirmed':True})
    def rank(self,key='rank-request-1',user='a'):
        return self.client.post(self.base+'/ideas/rank',headers=self.h(user),json={'request_id':key,'expected_fingerprint':self.board()['fingerprint']})
    def note(self,user,stage,idea=None):
        payload={'selected':True,'event_id':user+stage,'user_message':stage+'验证问题','assistant_summary':stage+'验证回复','conversation_stage':stage}
        if idea:payload['idea_id']=idea
        return self.client.post(self.base+'/conversation-notes',headers=self.h(user),json=payload)
    def test_team_visible_ideas_and_owner_edit_only(self):
        self.assertEqual(len(self.client.get(self.base+'/ideas',headers=self.h('b')).json()['ideas']),2)
        r=self.client.put(self.base+'/ideas/'+self.a,headers=self.h('b'),json={'title':'其他人修改','problem':'问题','proposal':'方案','expected_version':1});self.assertEqual(r.status_code,404)
    def test_scope_separation_and_connector_idea_binding(self):
        self.assertEqual(self.note('a','discussion',self.a).status_code,200)
        self.assertEqual(self.note('a','development').status_code,200)
        self.assertEqual(self.note('b','discussion',self.a).status_code,409)
        discussion=self.client.get(self.base+'/library?scope=discussion&idea_id='+self.a,headers=self.h('b')).json()
        project=self.client.get(self.base+'/library?scope=project',headers=self.h('b')).json()
        self.assertEqual(discussion['total'],1);self.assertEqual(discussion['items'][0]['idea_id'],self.a)
        self.assertEqual(project['total'],1);self.assertEqual(project['items'][0]['stage'],'development')
        self.prepare();self.assertEqual(self.rank().status_code,200)
        context=str(self.calls[0]);self.assertIn('discussion验证回复',context);self.assertNotIn('development验证回复',context)
    def test_missing_inputs_and_all_member_confirmation_gate(self):
        r=self.rank();self.assertEqual(r.status_code,409);self.assertEqual(self.calls,[])
        self.prepare();self.idea('b','另一个idea')
        self.assertEqual(self.rank().status_code,409);self.assertFalse(next(m for m in self.board()['readiness'] if m['user_id']=='b')['confirmed'])
    def test_team_fit_ranking_does_not_select_or_publish_and_is_idempotent(self):
        self.prepare();before=self.client.get(self.base,headers=self.h('a')).json()
        self.assertEqual(self.rank().status_code,200);self.assertEqual(self.rank().status_code,200);self.assertEqual(len(self.calls),1)
        ranking=self.board()['ranking'];self.assertFalse(ranking['stale']);self.assertEqual(ranking['body']['rankings'][0]['idea_id'],self.b)
        after=self.client.get(self.base,headers=self.h('a')).json();self.assertEqual(before['direction'],after['direction']);self.assertEqual(before['active_plan'],after['active_plan'])
        self.assertEqual(self.rank('other-request','b').status_code,403)
        self.assertEqual(self.note('a','discussion',self.a).status_code,200)
        self.assertTrue(self.board()['ranking']['stale']);self.assertEqual(self.rank('new-analysis').status_code,409)
    def test_invalid_model_citations_fail_without_fake_order(self):
        self.prepare();self.invalid=True;self.assertEqual(self.rank().status_code,200)
        ranking=self.board()['ranking'];self.assertEqual(ranking['status'],'failed');self.assertEqual(ranking['body'],{})
        self.assertEqual(len(self.board()['ideas']),2)

    def test_new_team_blocks_direction_and_review_until_explicit_topic_choice(self):
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.path)) as con:con.execute('DELETE FROM topic_selections WHERE squad_id=?',(self.sid,));con.commit()
        snap=self.client.get(self.base,headers=self.h('a')).json();self.assertFalse(snap['topic_confirmed'])
        r=self.client.put(self.base+'/direction',headers=self.h('a'),json={'goal':'提前开发','expected_revision':snap['revision']});self.assertEqual(r.status_code,409)
        r=self.client.post(self.base+'/review',headers=self.h('a'),json={});self.assertEqual(r.status_code,409)
        r=self.client.post(self.base+'/topic/confirm',headers=self.h('a'),json={'idea_id':self.a,'confirmed':True});self.assertEqual(r.status_code,200,r.text)
        self.assertTrue(self.client.get(self.base,headers=self.h('a')).json()['topic_confirmed'])
    def test_first_selected_turn_appears_under_own_idea_automatically(self):
        r=self.client.post(self.base+'/conversation-notes',headers=self.h('a'),json={'selected':True,'event_id':'auto-public-turn','user_message':'我的校园工具设想','assistant_summary':'先验证页面流程','conversation_stage':'discussion'})
        self.assertEqual(r.status_code,200,r.text)
        items=self.client.get(self.base+'/library?scope=discussion',headers=self.h('b')).json()['items']
        self.assertEqual(items[0]['idea_id'],self.a)
