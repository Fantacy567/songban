import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.conversation_sync import Reader, Manager, sessions
from app.main import Problem, create_app, digest, now
from app.studio import hash_password


def write(path, *items):
    with path.open('ab') as f:
        for item in items:
            f.write((json.dumps(item,ensure_ascii=False)+'\n').encode())


def message(role, text, **extra):
    return {'type':'response_item','payload':{'type':'message','role':role,
            'content':[{'type':'input_text' if role=='user' else 'output_text','text':text}],**extra}}


FAKE_CREDENTIAL='sk-'+'synthetic'+'0'*12  # assembled at runtime; not a real key


def turn(path, ident='turn1', user='把接口接起来', reply='已完成。请检查。'):
    write(path, {'type':'event_msg','payload':{'type':'task_started','turn_id':ident}},
          {'type':'turn_context','payload':{'model':'test-model-exact'}},
          message('user',user),message('assistant','私有思考，不能上传',phase='analysis'),
          message('assistant',reply,phase='final'),
          {'type':'event_msg','payload':{'type':'task_complete','turn_id':ident}})


def codex_turn(path, ident, user, reply, model='gpt-synthetic-exact'):
    """Shape of a current Codex rollout turn (phase names checked against the installed CLI binary)."""
    write(path, {'type':'event_msg','payload':{'type':'task_started','turn_id':ident}},
          {'type':'turn_context','payload':{'model':model}},
          message('user','<environment_context>\n  <cwd>/synthetic</cwd>\n</environment_context>'),
          message('user',user),{'type':'event_msg','payload':{'type':'user_message','message':user}},
          message('user','<skill>\n注入的技能说明，不是用户原话\n</skill>'),
          {'type':'response_item','payload':{'type':'reasoning','summary':[{'type':'summary_text','text':'加密思考摘要'}]}},
          message('assistant','进行中的说明，不上传',phase='commentary'),
          {'type':'response_item','payload':{'type':'function_call','name':'shell','arguments':'{}','call_id':'c1'}},
          {'type':'response_item','payload':{'type':'function_call_output','call_id':'c1','output':'工具输出不上传'}},
          message('assistant',reply,phase='final_answer'),
          {'type':'event_msg','payload':{'type':'task_complete','turn_id':ident,'last_agent_message':reply}})


class ReaderTests(unittest.TestCase):
    def test_future_only_completed_rounds_and_incomplete_append(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'chat.jsonl';p.touch();turn(p,'past',user='不要上传的历史')
            r=Reader(p,'session-test')
            self.assertEqual(r.poll(),[])
            turn(p)
            got=r.poll();self.assertEqual(len(got),1)
            self.assertEqual(got[0]['user_message'],'把接口接起来')
            self.assertEqual(got[0]['assistant_summary'],'已完成。请检查。')
            self.assertEqual(got[0]['model_name'],'test-model-exact')
            self.assertNotIn('私有思考',json.dumps(got,ensure_ascii=False))
            self.assertEqual(r.poll(),[])
            turn(p)  # same turn/event identity is idempotent
            self.assertEqual(r.poll(),[])
            raw=json.dumps(message('user','写入中的一句'),ensure_ascii=False).encode()
            with p.open('ab') as f:f.write(raw[:10])
            self.assertEqual(r.poll(),[])
            with p.open('ab') as f:f.write(raw[10:]+b'\n')
            self.assertEqual(r.poll(),[])
            write(p,message('assistant','完成',phase='final'),{'type':'event_msg','payload':{'type':'task_complete','turn_id':'turn2'}})
            got=r.poll();self.assertEqual(got[0]['user_message'],'写入中的一句');self.assertEqual(got[0]['model_name'],'')

    def test_current_codex_shape_keeps_typed_words_only(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'chat.jsonl';p.touch();r=Reader(p,'session-test')
            codex_turn(p,'t1','请把登录接口接好','接口已接好，测试通过。')
            got=r.poll();self.assertEqual(len(got),1)
            self.assertEqual(got[0]['user_message'],'请把登录接口接好')
            self.assertEqual(got[0]['assistant_summary'],'接口已接好，测试通过。')
            self.assertEqual(got[0]['model_name'],'gpt-synthetic-exact')
            raw=json.dumps(got,ensure_ascii=False)
            for hidden in ('environment_context','注入的技能','加密思考','进行中的说明','工具输出'):
                self.assertNotIn(hidden,raw)
            write(p,{'type':'event_msg','payload':{'type':'task_started','turn_id':'t2'}},
                  message('user','没有模型上下文的一轮'),message('assistant','完成',phase='final_answer'),
                  {'type':'event_msg','payload':{'type':'task_complete','turn_id':'t2'}})
            self.assertEqual(r.poll()[0]['model_name'],'')

    def test_metadata_only_and_no_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'rollout-test.jsonl'
            write(p,{'type':'session_meta','payload':{'id':'session-test','cwd':'/project','timestamp':'2026-10-29'}},message('user','绝不出现在列表的正文'))
            rows=sessions(root);self.assertEqual(len(rows),1)
            self.assertNotIn('正文',str(rows));self.assertEqual(rows[0]['id'],'session-test')
            (root/'rollout-link.jsonl').symlink_to(p)
            self.assertEqual(len(sessions(root)),1)

    def test_failed_upload_retries_then_stop_discards_unsent(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'chat.jsonl';p.touch();m=Manager();received=[]
            def send(x):
                received.append(x)
                if len(received)==1:raise RuntimeError('模拟断线')
                return {'note_id':'saved'}
            m.start('member',Reader(p,'session-test'),send,lambda:None,'connection',background=False)
            turn(p);m.tick(m.jobs['member']);self.assertEqual(m.status('member')['status'],'retrying')
            m.tick(m.jobs['member']);self.assertEqual(m.status('member')['sent'],1)
            self.assertEqual(received[0]['event_id'],received[1]['event_id'])
            m.stop('member');turn(p,'next');m.tick(m.jobs['member']);self.assertEqual(len(received),2)
            m.start('member',Reader(p,'session-test'),send,lambda:None,'new',background=False)
            m.tick(m.jobs['member']);self.assertEqual(m.status('member')['sent'],0)
            def busy():raise RuntimeError('database is locked')
            m.jobs['member']['check']=busy;turn(p,'blocked');m.tick(m.jobs['member'])
            self.assertEqual(m.status('member')['status'],'retrying');self.assertEqual(len(received),2)
            def denied():raise Problem(401,'connection_invalid','x')
            m.jobs['member']['check']=denied;m.tick(m.jobs['member'])
            self.assertEqual(m.status('member')['status'],'stopped');self.assertEqual(len(received),2)

    def test_rejected_payload_stops_instead_of_looping(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'chat.jsonl';p.touch();m=Manager();calls=[]
            def send(x):calls.append(x);raise Problem(409,'event_conflict','x')
            m.start('member',Reader(p,'session-test'),send,lambda:None,'connection',background=False)
            turn(p);m.tick(m.jobs['member']);m.tick(m.jobs['member'])
            self.assertEqual(m.status('member')['status'],'stopped');self.assertEqual(len(calls),1)
            self.assertEqual(m.close(),[('member','connection')])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name);self.log=root/'rollout-current.jsonl'
        write(self.log,{'type':'session_meta','payload':{'id':'session-current','cwd':'/synthetic-project','timestamp':now()}},message('user','旧历史不得上传'))
        self.path=root/'db.sqlite3';self.app=create_app(self.path,core_only=True)
        self.client=TestClient(self.app,base_url='http://127.0.0.1:8886',client=('127.0.0.1',55555))
        with sqlite3.connect(self.path) as con:
            for uid in ('a','b'):
                con.execute('INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at,password_hash) VALUES(?,?,?,?,?,?,?,?)',
                    (uid,'1800000000'+('1' if uid=='a' else '2'),'注册姓名'+uid,'','',digest('token-'+uid),now(),hash_password('synthetic-only')))
        self.h={'Authorization':'Bearer token-a'}
        self.sid=self.client.post('/api/core/teams',json={'name':'合成持续同步测试'},headers=self.h).json()['id']
        self.base='/api/core/teams/'+self.sid
        self.scope=patch('app.conversation_sync.session_root',return_value=root);self.scope.start()
    def tearDown(self):
        self.app.state.continuous_sync.close();self.client.close();self.scope.stop();self.tmp.cleanup()
    def test_start_complete_round_library_and_stop_real_routes(self):
        listing=self.client.get('/api/core/continuous-sessions',headers=self.h)
        self.assertEqual(listing.status_code,200);self.assertNotIn('旧历史',listing.text);self.assertNotIn('_path',listing.text)
        r=self.client.post(self.base+'/continuous-sync',json={'thread_id':'session-current','consent':True},headers=self.h)
        self.assertEqual(r.status_code,200,r.text)
        key=(self.sid,'a');manager=self.app.state.continuous_sync
        turn(self.log,user='这是本轮，API_KEY='+FAKE_CREDENTIAL)
        manager.tick(manager.jobs[key])
        records=self.client.get(self.base+'/library',headers=self.h).json()
        raw=json.dumps(records,ensure_ascii=False)
        self.assertIn('注册姓名a',raw);self.assertIn('这是本轮',raw);self.assertIn('test-model-exact',raw)
        self.assertNotIn('旧历史',raw);self.assertNotIn('私有思考',raw);self.assertNotIn(FAKE_CREDENTIAL,raw)
        self.assertEqual(manager.status(key)['sent'],1)
        snap=self.client.get(self.base,headers=self.h).json();self.assertFalse(snap['proposal'])
        stopped=self.client.delete(self.base+'/continuous-sync',headers=self.h)
        self.assertEqual(stopped.status_code,200)
        turn(self.log,'after-stop',user='停止后不上传');manager.tick(manager.jobs[key])
        self.assertNotIn('停止后不上传',self.client.get(self.base+'/library',headers=self.h).text)
    def test_pause_or_revoke_in_connection_list_stops_at_once_and_shutdown_revokes(self):
        manager=self.app.state.continuous_sync;key=(self.sid,'a')
        for action in ('pause','revoke'):
            started=self.client.post(self.base+'/continuous-sync',json={'thread_id':'session-current','consent':True},headers=self.h).json()
            cid=started['connection_id']
            self.assertEqual(self.client.patch(self.base+'/connections/'+cid,json={'action':action},headers=self.h).status_code,200)
            self.assertEqual(manager.status(key)['status'],'stopped')
            if action=='pause':
                self.client.patch(self.base+'/connections/'+cid,json={'action':'resume'},headers=self.h)
            turn(self.log,'after-'+action,user='暂停撤销后不上传'+action);manager.tick(manager.jobs[key])
            self.assertNotIn('暂停撤销后不上传',self.client.get(self.base+'/library',headers=self.h).text)
        cid=self.client.post(self.base+'/continuous-sync',json={'thread_id':'session-current','consent':True},headers=self.h).json()['connection_id']
        for handler in self.app.router.on_shutdown:handler()
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute('SELECT revoked FROM core_connections WHERE id=?',(cid,)).fetchone()[0],1)
        self.assertEqual(manager.status(key)['status'],'stopped')
    def test_consent_remote_credential_and_arbitrary_path_rejected(self):
        self.assertEqual(self.client.post(self.base+'/continuous-sync',json={'thread_id':'session-current'},headers=self.h).status_code,422)
        self.assertEqual(self.client.post(self.base+'/continuous-sync',json={'thread_id':'../../private','consent':True},headers=self.h).status_code,404)
        self.assertEqual(self.client.get('/api/core/continuous-sessions').status_code,401)
        remote=TestClient(self.app,base_url='http://remote.example',client=('203.0.113.3',5555))
        self.assertEqual(remote.get('/api/core/continuous-sessions',headers=self.h).status_code,403);remote.close()
        c=self.client.post(self.base+'/connections',json={'label':'test'},headers=self.h).json()
        self.assertEqual(self.client.post(self.base+'/continuous-sync',headers={'Authorization':'Bearer '+c['token']},json={'thread_id':'session-current','consent':True}).status_code,403)

if __name__=='__main__':unittest.main()
