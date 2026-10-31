import json
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import create_app, digest, now
from app.planner import PlannerError
from app.topic_selection import DIMENSIONS


def ranking_for(context):
    return {'summary': '协议测试排名，非真实模型判断', 'items': [
        {'candidate_id': c['id'], 'dimensions': {k: '根据成员自述，需要验证' for k in DIMENSIONS},
         'advantages': ['具备讨论依据'], 'risks': ['能力尚未实际验证'],
         'verification': ['验证最小原型'], 'source_ids': [c['turns'][0]['id'], 'track']}
        for c in context['candidates']]}


def plan_for(context):
    return {'summary': '按主方向生成任务', 'findings': [], 'questions': [], 'tasks': [
        {'key': 'T1', 'title': '验证最小原型', 'owner_id': context['members'][0]['id'],
         'acceptance': '正常和错误输入均有结果', 'depends_on': [], 'source_ids': ['direction']}]}


class TopicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'topics.sqlite3'
        self.calls = []
        self.failure = None
        def runner(context):
            self.calls.append(context)
            if self.failure:
                raise self.failure
            return ranking_for(context)
        self.app = create_app(self.path, core_only=True, topic_model_runner=runner, core_model_runner=plan_for)
        self.client = TestClient(self.app)
        with closing(sqlite3.connect(self.path)) as con:
            for i in 'abcde':
                con.execute('INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at) VALUES(?,?,?,?,?,?,?)',
                            (i, '1800000000'+str(ord(i)-97), '成员'+i, '测试', '设计', digest('topic-test-'+i), now()))
            con.commit()
        self.h = lambda who: {'Authorization': 'Bearer topic-test-'+who}
        team = self.client.post('/api/core/teams', json={'name':'选题测试'}, headers=self.h('a')).json()
        self.base = '/api/core/teams/' + team['id']
        self.code = team['code']
        self.url = self.base + '/topic-selection'
        self.join('b')

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def join(self, who):
        self.assertEqual(self.client.post('/api/core/join', json={'code': self.code}, headers=self.h(who)).status_code, 200)

    def snap(self, who='a'):
        return self.client.get(self.base, headers=self.h(who)).json()

    def current(self, who='a'):
        return self.client.get(self.url, headers=self.h(who)).json()['round']

    def send(self, action, who='a', status=200, **extra):
        version = self.snap()['revision'] if action=='rounds' else self.current()['revision']
        body = {'expected_revision': version, 'request_id': str(uuid.uuid4()), **extra}
        r = self.client.post(self.url+'/'+action, json=body, headers=self.h(who))
        self.assertEqual(r.status_code, status, r.text)
        return r.json(), body

    def start(self):
        return self.send('rounds', track='AI 应用', rules='可演示原型', rubric='实用性与创新性')[0]['round']

    def upload(self, who='a', **extra):
        data = {'round_id':self.current()['id'], 'event_id':'turn-'+str(uuid.uuid4()), 'selected':True,
                'topic_title':'选题'+who, 'user_message':'我想解决排队问题', 'assistant_message':'先验证用户需求和原型', **extra}
        return self.client.post(self.url+'/turns', json=data, headers=self.h(who)), data

    def ready(self):
        self.start()
        for who in 'ab':
            r, _ = self.upload(who);self.assertEqual(r.status_code,200,r.text)
            self.send('ready', who, complete=True)
        return self.current()

    def choose(self):
        cur = self.ready(); winner = cur['eligible'][0]
        for who in 'ab':self.send('votes',who,candidate_id=winner,ballot=1)
        self.send('select',candidate_id=winner)
        return winner

    def test_full_loop_tie_then_claim_and_report(self):
        cur = self.ready();first,second = cur['eligible']
        self.assertEqual(len(self.calls),1)
        self.assertEqual(cur['ranking']['mode'],'fixture')
        self.send('votes',candidate_id=first,ballot=1)
        self.assertIsNone(self.current('b')['tallies'])
        self.assertIsNone(self.current('b')['my_vote'])
        self.send('votes','a',409,candidate_id=second,ballot=1)
        self.send('select',status=409,candidate_id=first)
        self.send('votes','b',candidate_id=second,ballot=1)
        cur=self.current();self.assertEqual(cur['ballot'],2);self.assertEqual(cur['votes_count'],0)
        for who in 'ab':self.send('votes',who,candidate_id=first,ballot=2)
        self.send('select','b',403,candidate_id=first)
        self.send('select',status=409,candidate_id=second)
        self.send('select',candidate_id=first)
        self.assertEqual(self.snap()['direction']['goal'],'选题a')
        p=self.client.post(self.base+'/review',json={},headers=self.h('a')).json()
        r=self.client.post(self.base+'/proposals/'+p['proposal_id']+'/confirm',json={'expected_revision':p['base_revision']},headers=self.h('a'))
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.snap()['active_plan']['tasks'][0]['owner_id'],'')
        body={'request_id':str(uuid.uuid4()),'expected_revision':self.snap()['revision']}
        url=self.base+'/tasks/T1/claim'
        for _ in range(2):self.assertEqual(self.client.post(url,json=body,headers=self.h('b')).status_code,200)
        body.update(request_id=str(uuid.uuid4()),expected_revision=self.snap()['revision'])
        self.assertEqual(self.client.post(url,json=body,headers=self.h('a')).status_code,409)
        self.assertEqual(self.snap('b')['workflow']['my_tasks'][0]['key'],'T1')
        report=self.client.post(self.base+'/reports',json={'event_id':'after-claim','tool':'测试','summary':'完成原型','task_key':'T1','plan_version':1,'status':'reported_done','evidence':['测试记录']},headers=self.h('b'))
        self.assertEqual(report.status_code,200,report.text)
        self.assertEqual(self.snap()['active_plan']['tasks'][0]['status'],'reported_done')

    def test_five_member_progress_new_turn_resets_own_confirmation(self):
        for who in 'cde':self.join(who)
        self.start()
        for who in 'abcde':self.assertEqual(self.upload(who)[0].status_code,200)
        self.send('ready',complete=True)
        self.upload('a')
        self.assertEqual(self.current()['confirmed_count'],0)
        for i,who in enumerate('abcd',1):
            self.send('ready',who,complete=True)
            self.assertEqual(self.current()['confirmed_count'],i)
            self.assertEqual(self.current()['member_count'],5)
            self.assertEqual(len(self.calls),0)
        _,body=self.send('ready','e',complete=True)
        self.assertEqual(len(self.calls),1)
        r=self.client.post(self.url+'/ready',json=body,headers=self.h('e'))
        self.assertTrue(r.json()['duplicate']);self.assertEqual(len(self.calls),1)

    def test_permissions_upload_idempotency_and_scrubbing(self):
        self.send('rounds','b',403,track='AI')
        self.start()
        self.send('ready',status=409,complete=True)
        self.assertEqual(self.client.post(self.base+'/review',json={},headers=self.h('a')).status_code,409)
        token=self.client.post(self.base+'/connections',json={'label':'连接器测试'},headers=self.h('b')).json()['token']
        r,body=self.upload(assistant_message='API_KEY=sk-test-abcdefghijklmnop <script>alert(1)</script>')
        self.assertEqual(r.status_code,200,r.text)
        self.assertNotIn('sk-test-',json.dumps(self.current()))
        self.assertEqual(self.client.post(self.url+'/turns',json=body,headers=self.h('a')).json()['note_id'],r.json()['note_id'])
        self.assertEqual(self.client.post(self.url+'/turns',json={**body,'assistant_message':'改变'},headers=self.h('a')).status_code,409)
        self.assertEqual(self.upload(selected=False)[0].status_code,422)
        self.assertEqual(self.client.get(self.url,headers=self.h('c')).status_code,403)
        self.assertEqual(self.client.post(self.url+'/ready',json={'request_id':'connector-ready','expected_revision':self.current()['revision'],'complete':True},headers={'Authorization':'Bearer '+token}).status_code,403)
        body.update(event_id='from-mcp-123',topic_title='连接器选题')
        self.assertEqual(self.client.post(self.url+'/turns',json=body,headers={'Authorization':'Bearer '+token}).status_code,200)
        self.assertEqual(self.client.get(self.base+'/context',headers={'Authorization':'Bearer '+token}).json()['topic_selection']['id'],body['round_id'])

    def test_timeout_unknown_explicit_retry_and_bad_ranking(self):
        self.failure=PlannerError('model_timeout','测试超时',504)
        self.ready();self.assertEqual(self.current()['phase'],'unknown')
        self.send('retry',status=422)
        self.assertEqual(len(self.calls),1)
        self.failure=None
        self.send('retry',acknowledge_unknown=True)
        self.assertEqual(self.current()['phase'],'voting')
        self.assertEqual(len(self.calls),2)

    def test_roster_change_requires_reconfirm_and_old_votes_do_not_return(self):
        cur=self.ready();self.send('votes',candidate_id=cur['eligible'][0],ballot=1)
        self.client.put(self.base+'/profile',json={'strengths':'新版能力','willingness':'验证','hours':2},headers=self.h('b'))
        self.assertTrue(self.current()['roster_changed'])
        self.send('votes','b',409,candidate_id=cur['eligible'][0],ballot=1)
        self.send('reopen',minutes=20)
        self.assertEqual(self.current()['confirmed_count'],0)
        for who in 'ab':self.send('ready',who,complete=True)
        self.assertEqual(self.current()['ballot'],2)
        self.assertEqual(self.current()['votes_count'],0)
        self.assertIsNone(self.current()['my_vote'])

    def test_deadline_upload_blocked_and_confirm_still_possible(self):
        self.start();self.upload()
        with closing(sqlite3.connect(self.path)) as con:
            row=con.execute('SELECT body FROM core_topic_rounds').fetchone()
            data=json.loads(row[0]);data['deadline']='2000-01-01T00:00:00+00:00'
            con.execute('UPDATE core_topic_rounds SET body=?',(json.dumps(data),));con.commit()
        self.assertEqual(self.upload('b')[0].status_code,409)
        self.send('ready',complete=True)
        self.send('reopen',minutes=10)
        self.assertEqual(self.upload('b')[0].status_code,200)

    def test_locked_direction_and_no_reopen_after_choice(self):
        self.choose()
        self.send('reopen',status=409)
        self.assertEqual(self.client.put(self.base+'/direction',json={'goal':'越过投票','expected_revision':self.snap()['revision']},headers=self.h('a')).status_code,409)

    def test_malformed_ranking_does_not_become_vote(self):
        with patch(__name__+'.ranking_for',return_value={'summary':'缺少完整评估','items':[]}):
            self.ready()
        self.assertEqual(self.current()['phase'],'failed')
        self.assertEqual(len(self.current()['candidates']),2)

    def test_full_turn_whitespace_and_no_identity_override(self):
        self.start()
        raw='  保留原始换行\n\n并保留空格  '
        response,body=self.upload(user_message=raw,assistant_message=raw)
        self.assertEqual(response.status_code,200)
        turn=self.current()['candidates'][0]['turns'][0]
        self.assertEqual(turn['user_message'],raw);self.assertEqual(turn['assistant_message'],raw)
        self.assertEqual(self.client.post(self.url+'/turns',json={**body,'user_id':'b'},headers=self.h('a')).status_code,422)

    def test_duplicate_upload_after_ranking_keeps_receipt(self):
        self.start();r,body=self.upload();self.upload('b')
        for who in 'ab':self.send('ready',who,complete=True)
        duplicate=self.client.post(self.url+'/turns',json=body,headers=self.h('a'))
        self.assertEqual(duplicate.status_code,200)
        self.assertEqual(duplicate.json()['note_id'],r.json()['note_id'])
        self.assertEqual(self.upload()[0].status_code,409)
        self.assertEqual(len(self.calls),1)

    def test_round_and_vote_survive_restart_without_new_model_call(self):
        cur=self.ready();self.send('votes',candidate_id=cur['eligible'][0],ballot=1)
        calls=[]
        restarted=create_app(self.path,core_only=True,topic_model_runner=lambda c:calls.append(c))
        with TestClient(restarted) as client:
            restored=client.get(self.url,headers=self.h('a')).json()['round']
        self.assertEqual(restored['phase'],'voting');self.assertEqual(restored['votes_count'],1)
        self.assertEqual(restored['my_vote'],cur['eligible'][0]);self.assertEqual(calls,[])

    def test_removed_and_added_members_require_current_roster_confirmation(self):
        self.ready();self.join('c')
        self.assertTrue(self.current()['roster_changed'])
        self.send('reopen',minutes=10)
        for who in 'ab':self.send('ready',who,complete=True)
        self.assertEqual(self.current()['phase'],'discussion')
        self.upload('c');self.send('ready','c',complete=True)
        self.assertEqual(self.current()['member_count'],3);self.assertEqual(len(self.calls),2)

    def test_tie_revote_excludes_lower_ranked_in_vote_count(self):
        self.join('c');self.join('d');self.start()
        for who in 'abcd':self.upload(who);self.send('ready',who,complete=True)
        ids=self.current()['eligible']
        for who,candidate in zip('abcd',[ids[0],ids[0],ids[1],ids[1]]):self.send('votes',who,candidate_id=candidate,ballot=1)
        self.assertEqual(set(self.current()['eligible']),set(ids[:2]))
        self.send('votes',status=409,candidate_id=ids[2],ballot=2)

    def test_expired_attempt_is_unknown_and_late_result_not_applied(self):
        original=ranking_for
        def expire(context):
            with closing(sqlite3.connect(self.path)) as con:
                con.execute("UPDATE core_topic_rounds SET lease_until='2000-01-01T00:00:00+00:00'");con.commit()
            return original(context)
        with patch(__name__+'.ranking_for',side_effect=expire):self.ready()
        self.assertEqual(self.current()['phase'],'unknown')
        self.assertIsNone(self.current()['ranking'])
        self.send('retry',acknowledge_unknown=True)
        self.assertEqual(self.current()['phase'],'voting')

    def test_new_attempt_ignores_return_of_cancelled_ranker(self):
        original=ranking_for
        def reopen_during_request(context):
            self.send('reopen',minutes=10)
            return original(context)
        with patch(__name__+'.ranking_for',side_effect=reopen_during_request):self.ready()
        self.assertEqual(self.current()['phase'],'discussion')
        self.assertIsNone(self.current()['ranking'])
        self.assertEqual(self.current()['confirmed_count'],0)

    def test_plan_receives_winning_discussion_and_claim_survives_restart(self):
        self.choose()
        contexts=[]
        def capture(context):contexts.append(context);return plan_for(context)
        restarted=create_app(self.path,core_only=True,core_model_runner=capture)
        with TestClient(restarted) as client:
            result=client.post(self.base+'/review',json={},headers=self.h('a'))
            self.assertEqual(result.status_code,200,result.text)
            proposal=result.json()
            confirmed=client.post(self.base+'/proposals/'+proposal['proposal_id']+'/confirm',json={'expected_revision':proposal['base_revision']},headers=self.h('a'))
            self.assertEqual(confirmed.status_code,200,confirmed.text)
            revision=client.get(self.base,headers=self.h('b')).json()['revision']
            claim=client.post(self.base+'/tasks/T1/claim',json={'request_id':'claim-before-restart','expected_revision':revision},headers=self.h('b'))
            self.assertEqual(claim.status_code,200,claim.text)
        self.assertEqual(result.status_code,200,result.text)
        selected=contexts[0]['selected_topic']
        self.assertEqual(selected['title'],'选题a')
        self.assertIn('先验证',selected['shared_turns'][0]['assistant_message'])
        self.assertTrue(selected['assessment']['risks'])
        with TestClient(create_app(self.path,core_only=True)) as client:
            tasks=client.get(self.base+'/my-tasks',headers=self.h('b')).json()['tasks']
            self.assertEqual(tasks[0]['key'],'T1')


if __name__=='__main__':unittest.main()
