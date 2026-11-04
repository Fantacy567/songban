"""Actual ASGI/database tests; fake Harness transport, zero paid calls."""
import json
import asyncio
import time
import io
from unittest.mock import Mock
import unittest
from unittest.mock import patch
import httpx
from app.creative_studio import register_studio
from app.creative_studio.harness import HarnessRunner, REVISION, CONTRACT
from app.creative_studio.schemas import Edit
from app.creative_studio.service import START
from app.platform_v1.schemas import WorkSummary
try:
    from . import test_platform_http as platform_fixture
    from .test_learning_v2_identity import Fixture
except ImportError:
    import test_platform_http as platform_fixture
    from test_learning_v2_identity import Fixture

PREFIX=platform_fixture.PREFIX

class CreativeStudioTests(Fixture, unittest.TestCase):
    post=platform_fixture.PlatformHttpTests.post
    provider=platform_fixture.PlatformHttpTests.provider
    def setUp(self):
        platform_fixture.PlatformHttpTests.setUp(self)
        self.config={'enabled':True,'model':'synthetic-model','api_key':'fake','max_calls':4,'max_output_tokens':800,'timeout_seconds':20,'revision':1}
        self.executions=[]
        def runner(payload):
            self.executions.append(payload)
            cid=payload['reserve_call']()
            payload['record_call'](cid,{'tokens':2})
            return {'files':START,'text':'点击会调用事件处理函数。请预测更改文字后的结果。','actual_model':'synthetic-model'}
        self.studio=register_studio(self.app,self.app.state.platform_v1,lambda **kw:self.config,runner)

    def create_studio(self):
        return self.post('/studio/projects',{'title':'校园计数器','idea':'点按钮记录阅读次数。'},201)

    def test_files_restore_and_private_archive(self):
        p=self.create_studio(); vid=p['current_version_id']
        self.assertEqual(p['revision'],1)
        files=[dict(f) for f in p['files']]; files[0]['content']='<h1>我的计数器</h1>'
        p=self.post('/studio/projects/'+p['id']+'/files',{'expected_revision':p['revision'],'files':files,'explanation':'我改了标题。'})
        self.assertEqual(p['versions'][0]['actor'],'child')
        p=self.post('/studio/projects/'+p['id']+'/restore',{'expected_revision':p['revision'],'version_id':vid})
        self.assertEqual(p['files'],START)
        p=self.post('/studio/projects/'+p['id']+'/archive',{'expected_revision':p['revision'],'contribution':'我预测点击会改变文本，并点击验证。'})
        self.assertTrue(p['archive'])
        with self.service.store.transaction() as con:
            session={'mode':'learner','learner_id':self.lid,'actor_id':'parent-a'}
            items=self.studio.portfolio_items(con,session,self.lid)
            WorkSummary.model_validate(items[0]); self.assertEqual(items[0]['provenance']['ai_assistance'],'none_reported')
        self.assertFalse(self.executions)

    def test_idempotency_and_revision_conflict(self):
        body={'request_id':'same','title':'小作品','idea':'让按钮回应。'}
        a=self.post('/studio/projects',body,201,raw=True)
        b=self.post('/studio/projects',body,201,raw=True)
        self.assertEqual(a['id'],b['id'])
        self.post('/studio/projects',body|{'idea':'不同的想法'},409,raw=True)
        self.post('/studio/projects/'+a['id']+'/files',{'expected_revision':88,'files':START,'explanation':'改标题'},409)

    def test_foreign_owner_and_session_switch(self):
        p=self.create_studio()
        self.assertEqual(self.b.get(PREFIX+'/studio/projects/'+p['id']).status_code,401)
        self.login(self.b,'parent-b')
        self.assertEqual(self.b.get(PREFIX+'/studio/projects/'+p['id']).status_code,404)

    def test_invalid_paths_and_duplicate_files(self):
        p=self.create_studio()
        for files in ([{'path':'../.env','content':'bad'}],[{'path':'index.html','content':'a'},{'path':'index.html','content':'b'}]):
            self.post('/studio/projects/'+p['id']+'/files',{'expected_revision':1,'files':files,'explanation':'x'},422)

    def test_document_is_version_bound_and_guarded(self):
        p=self.create_studio()
        result=self.a.get(PREFIX+'/studio/projects/'+p['id']+'/preview').json()
        page=self.a.get(result['document_url'])
        self.assertEqual(page.status_code,200)
        self.assertIn('connect-src',page.text)
        self.assertNotIn('allow-same-origin',page.headers.get('content-security-policy',''))
        self.assertEqual(self.b.get(result['document_url']).status_code,401)
        self.assertEqual(self.a.get(result['document_url'].replace(p['current_version_id'],'csv_bad')).status_code,404)

    def test_model_job_runs_once_and_records_ai_changes(self):
        p=self.create_studio(); url='/studio/projects/'+p['id']
        p=self.post(url+'/messages',{'expected_revision':1,'text':'帮我把按钮颜色改一下。'})
        for _ in range(2): self.a.get(PREFIX+url)
        self.assertEqual(self.executions,[])
        self.studio.worker_once(); self.studio.worker_once()
        p=self.a.get(PREFIX+url).json()
        self.assertEqual(len(self.executions),1)
        self.assertEqual(p['jobs'][0]['state'],'succeeded')
        self.assertEqual(p['versions'][0]['actor'],'ai')
        self.assertEqual(self.executions[0]['curriculum']['status'],'draft')
        self.assertEqual(p['messages'][-1]['role'],'assistant')

    def test_unavailable_preserves_current_work(self):
        p=self.create_studio(); self.studio.runner=None
        self.post('/studio/projects/'+p['id']+'/messages',{'expected_revision':1,'text':'改一下'},503)
        self.assertEqual(self.a.get(PREFIX+'/studio/projects/'+p['id']).json()['revision'],1)

    def test_configuration_revocation_before_dispatch(self):
        p=self.create_studio()
        self.post('/studio/projects/'+p['id']+'/messages',{'expected_revision':1,'text':'改一下'})
        self.config['enabled']=False
        self.studio.worker_once()
        p=self.a.get(PREFIX+'/studio/projects/'+p['id']).json()
        self.assertEqual(p['jobs'][0]['state'],'failed'); self.assertFalse(self.executions)

    def test_uncertain_does_not_retry_or_release_budget(self):
        p=self.create_studio()
        def uncertain(payload): payload['reserve_call'](); raise TimeoutError()
        self.studio.runner=uncertain
        self.post('/studio/projects/'+p['id']+'/messages',{'expected_revision':1,'text':'改一下'})
        self.studio.worker_once(); self.studio.worker_once()
        p=self.a.get(PREFIX+'/studio/projects/'+p['id']).json()
        self.assertEqual(p['jobs'][0]['state'],'unknown')
        self.post('/studio/projects/'+p['id']+'/messages',{'expected_revision':p['revision'],'text':'再发一次'},409)
        with self.service.store.transaction() as con: self.assertEqual(con.execute('SELECT COUNT(*) FROM creative_calls').fetchone()[0],1)

    def test_budget_survives_revision_change(self):
        p=self.create_studio(); self.config['max_calls']=1
        self.post('/studio/projects/'+p['id']+'/messages',{'expected_revision':1,'text':'改一下'})
        self.studio.worker_once(); self.config['revision']=2
        p=self.a.get(PREFIX+'/studio/projects/'+p['id']).json()
        self.post('/studio/projects/'+p['id']+'/messages',{'expected_revision':p['revision'],'text':'改一下'},429)

    def test_unknown_allows_manual_work_and_audited_close(self):
        p=self.create_studio(); url='/studio/projects/'+p['id']
        def uncertain(payload): payload['reserve_call'](); raise TimeoutError()
        self.studio.runner=uncertain
        self.post(url+'/messages',{'expected_revision':1,'text':'改一下'})
        self.studio.worker_once(); p=self.a.get(PREFIX+url).json()
        p=self.post(url+'/files',{'expected_revision':p['revision'],'files':START,'explanation':'先自行修改。'})
        jid=p['jobs'][0]['id']
        self.studio.close_unknown(jid,evidence='已检查隔离容器已退出；供应商结果仍未知，保留额度。',authority='synthetic-operator')
        p=self.a.get(PREFIX+url).json(); self.assertEqual(p['jobs'][0]['state'],'failed')
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM creative_calls').fetchone()[0],1)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM creative_reconciliations').fetchone()[0],1)

    def test_zero_model_dispatch_failure_is_retryable(self):
        p=self.create_studio()
        def broken(payload): raise OSError('container launch failed')
        self.studio.runner=broken
        self.post('/studio/projects/'+p['id']+'/messages',{'expected_revision':1,'text':'改一下'})
        self.studio.worker_once(); p=self.a.get(PREFIX+'/studio/projects/'+p['id']).json()
        self.assertEqual(p['jobs'][0]['state'],'failed')
        self.assertEqual(p['jobs'][0]['failure_code'],'runtime_failed_before_model')

    def test_reconcile_in_caller_transaction_rolls_back_with_authorization(self):
        p=self.create_studio()
        def uncertain(payload): payload['reserve_call'](); raise TimeoutError()
        self.studio.runner=uncertain
        self.post('/studio/projects/'+p['id']+'/messages',{'expected_revision':1,'text':'改一下'})
        self.studio.worker_once()
        with self.assertRaisesRegex(RuntimeError,'authorization changed'):
            with self.service.store.transaction() as con:
                jid=con.execute('SELECT id FROM creative_jobs').fetchone()[0]
                self.studio.close_unknown(jid,evidence='已核对进程退出与调用记录，额度保留。',authority='verified-admin',con=con)
                raise RuntimeError('authorization changed')
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute('SELECT state FROM creative_jobs').fetchone()[0],'unknown')
            self.assertEqual(con.execute('SELECT COUNT(*) FROM creative_reconciliations').fetchone()[0],0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM creative_calls').fetchone()[0],1)

    def test_session_revocation_discards_late_result(self):
        p=self.create_studio()
        original=self.studio.runner
        def revoked(payload):
            value=original(payload)
            with self.service.store.transaction() as con:
                con.execute("UPDATE learn_sessions SET revoked=1 WHERE learner_id=?",(self.lid,))
            return value
        self.studio.runner=revoked
        self.post('/studio/projects/'+p['id']+'/messages',{'expected_revision':1,'text':'改一下'})
        self.studio.worker_once()
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM creative_versions').fetchone()[0],1)
            self.assertEqual(con.execute('SELECT state FROM creative_jobs').fetchone()[0],'failed')

    def test_reconcile_requires_evidence_and_unknown_and_keeps_call_ledger(self):
        p=self.create_studio()
        def uncertain(payload): payload['reserve_call'](); raise TimeoutError()
        self.studio.runner=uncertain
        self.post('/studio/projects/'+p['id']+'/messages',{'expected_revision':1,'text':'改一下'})
        self.studio.worker_once()
        with self.service.store.transaction() as con:
            jid=con.execute('SELECT id FROM creative_jobs').fetchone()[0]
            before=[tuple(r) for r in con.execute('SELECT * FROM creative_calls')]
            for evidence,authority in [('', 'verified-admin'),('too short','verified-admin'),('核对记录满足长度但没有授权身份。',' '),('x'*3001,'verified-admin')]:
                with self.assertRaises(ValueError): self.studio.close_unknown(jid,evidence=evidence,authority=authority,con=con)
            self.assertEqual(con.execute('SELECT state FROM creative_jobs').fetchone()[0],'unknown')
            self.studio.close_unknown(jid,evidence='已核对隔离进程退出和调用记录；保留预留额度。',authority='verified-admin',con=con)
            audit=con.execute('SELECT * FROM creative_reconciliations').fetchone()
            self.assertEqual(audit['authority'],'verified-admin')
            self.assertEqual(con.execute('SELECT state FROM creative_jobs').fetchone()[0],'failed')
            self.assertEqual(before,[tuple(r) for r in con.execute('SELECT * FROM creative_calls')])
        from app.learning_v2.protocol import Problem
        with self.assertRaises(Problem):
            self.studio.close_unknown(jid,evidence='已经关闭的任务不能再次关闭或变成成功。',authority='verified-admin')
        self.assertIsNone(self.studio.worker_once())
        self.assertFalse(self.executions)

    def test_runtime_rejects_old_worker_image_even_with_pinned_upstream_revision(self):
        for output,expected in [(REVISION,False),(REVISION+':old',False),(REVISION+':'+CONTRACT,True)]:
            with self.subTest(output=output):
                runner=HarnessRunner(docker='docker')
                with patch('subprocess.run',return_value=Mock(returncode=0,stdout=(output+'\n').encode())):
                    self.assertEqual(runner.available(),expected)

    def test_global_running_limit_serializes_distinct_projects(self):
        first=self.create_studio(); second=self.create_studio()
        for p in (first,second): self.post('/studio/projects/'+p['id']+'/messages',{'expected_revision':1,'text':'改一下'})
        with self.service.store.transaction() as con:
            con.execute("UPDATE creative_jobs SET state='running',lease_until=? WHERE project_id=?",(self.now[0]+300,first['id']))
        self.assertIsNone(self.studio.worker_once()); self.assertFalse(self.executions)

    def test_model_relay_does_not_leak_keys_or_honor_destination(self):
        requests=[]
        def provider(req): requests.append(req);return httpx.Response(200,json={'model':'returned','usage':{'total_tokens':2}})
        runner=HarnessRunner(transport=httpx.MockTransport(provider))
        payload={'config':self.config,'reserve_call':lambda:'test','record_call':lambda *args:None}
        frame={'type':'model_request','id':'m','method':'POST','path':'/v1/chat/completions','body':{'model':'overridden','max_tokens':9999,'messages':[]}}
        result=runner.relay(frame,payload)
        self.assertEqual(str(requests[0].url),'https://api.deepseek.com/chat/completions')
        self.assertEqual(json.loads(requests[0].content)['model'],'synthetic-model')
        self.assertEqual(json.loads(requests[0].content)['max_tokens'],800)
        self.assertNotIn('fake',json.dumps(result))
        with self.assertRaises(ValueError): runner.relay(frame|{'path':'http://localhost/private'},payload)

    def test_container_command_has_no_host_mount_or_network(self):
        command=HarnessRunner(docker='docker').command('test')
        self.assertIn('--read-only',command);self.assertIn('--cap-drop',command)
        self.assertEqual(command[command.index('--network')+1],'none')
        self.assertNotIn('-v',command);self.assertNotIn('--mount',command)

    def test_only_upstream_completed_reason_accepts_files(self):
        payload={'config':self.config,'files':START,'text':'a','idea':'b','history':[],
                 'teaching':'c','curriculum':{},'deadline_seconds':1}
        for reason in ('completed','max-tokens','blocked','interrupted','forked','aborted','error',None,'new-reason'):
            with self.subTest(reason=reason):
                proc=Mock()
                proc.stdin=io.StringIO()
                proc.stdout=io.StringIO(json.dumps({'type':'result','files':START,'text':'观察一下。','finish_reason':reason})+'\n')
                proc.poll.return_value=0
                runner=HarnessRunner(docker='docker')
                with patch.object(runner,'available',return_value=True), patch('subprocess.Popen',return_value=proc), patch('subprocess.run',return_value=Mock(returncode=0)):
                    if reason=='completed': self.assertEqual(runner(payload)['files'],START)
                    else:
                        with self.assertRaisesRegex(RuntimeError,'incomplete'): runner(payload)

    def test_total_deadline_cancels_a_continuously_streaming_response(self):
        closed=[]
        class SlowStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                for _ in range(100):
                    await asyncio.sleep(.02)
                    yield b'data: {}\n'
            async def aclose(self): closed.append(True)
        runner=HarnessRunner(transport=httpx.MockTransport(lambda req:httpx.Response(200,stream=SlowStream())))
        payload={'config':self.config,'reserve_call':lambda:'test','record_call':lambda *a:None,'absolute_deadline':time.monotonic()+.08}
        started=time.monotonic()
        with self.assertRaises(TimeoutError):
            runner.relay({'id':'test','method':'POST','path':'/chat/completions','body':{'messages':[]}},payload)
        self.assertLess(time.monotonic()-started,1)
        self.assertTrue(closed)
