import json
from contextlib import closing
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import create_app, digest, now
from app.studio import hash_password
from app.planner import PlannerError


def plan_for(context):
    members=context['members'];refs=context['source_ids']
    return {'summary':'协议测试：先确认接口，再完成页面联调；不同观点需要证据。',
      'findings':[{'topic':'接口是否完成','decision':'先实际发请求核对，保留待核实。','reason':'个人工具报告不等于验收。','source_ids':refs[-2:] if len(refs)>2 else ['direction'],'needs_check':True}],
      'tasks':[{'key':'T1','title':'验证接口输入与输出','owner_id':members[0]['id'],'acceptance':'发正常与错误请求并记录返回','depends_on':[],'source_ids':['direction']},
               {'key':'T2','title':'接入页面并联调','owner_id':members[-1]['id'],'acceptance':'页面显示真实后端结果','depends_on':['T1'],'source_ids':['direction']}],
      'questions':['接口是否经过实际验证？']}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.sqlite3'
        self.cfg=patch('app.team_core.team_model_config',return_value={'api_key':'','model_id':'未配置'})
        self.cfg.start()
        self.app=create_app(self.path,core_only=True,core_model_runner=plan_for)
        self.client=TestClient(self.app)
        import sqlite3
        with closing(sqlite3.connect(self.path)) as con:
            for ident,name in [('a','后端测试成员'),('b','前端测试成员'),('c','其他团队成员')]:
                con.execute('INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at,password_hash) VALUES(?,?,?,?,?,?,?,?)',(ident,'1800000000'+str(ord(ident)-97),name,'测试','后端' if ident=='a' else '前端',digest('test-token-'+ident),now(),hash_password('test-only-password')))
            con.commit()
        self.h=lambda x:{'Authorization':'Bearer test-token-'+x}
        r=self.client.post('/api/core/teams',json={'name':'核心链路验收'},headers=self.h('a'));self.assertEqual(r.status_code,200,r.text)
        self.sid=r.json()['id'];self.code=r.json()['code'];self.base='/api/core/teams/'+self.sid
        with closing(sqlite3.connect(self.path)) as con:
            con.execute('INSERT INTO topic_selections VALUES(?,?,?,?)',(self.sid,'fixture-decided-topic','a',now()));con.commit()
        self.client.post('/api/core/join',json={'code':self.code},headers=self.h('b'))

    def tearDown(self):
        # wait only for this test's own bounded background worker, no external services
        deadline=time.monotonic()+5
        while self.app.state.core_jobs and time.monotonic()<deadline:time.sleep(.03)
        self.client.close();self.cfg.stop();self.tmp.cleanup()

    def conn(self,member='a'):
        r=self.client.post(self.base+'/connections',json={'label':'通用MCP测试'},headers=self.h(member));self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def snap(self):return self.client.get(self.base,headers=self.h('a')).json()

    def report(self,headers=None,event='one',**extra):
        return self.client.post(self.base+'/reports',headers=headers or self.h('a'),json={'event_id':event,'tool':'协议测试客户端','summary':'代码已写好，尚未验证','views':[],**extra})

    def review(self):
        r=self.client.post(self.base+'/review',json={},headers=self.h('a'));self.assertEqual(r.status_code,200,r.text);return r.json()

    def confirm(self,p):return self.client.post(self.base+'/proposals/'+p['proposal_id']+'/confirm',json={'expected_revision':p['base_revision']},headers=self.h('a'))

    def test_complete_two_person_loop(self):
        a,b=self.conn('a'),self.conn('b');ha={'Authorization':'Bearer '+a['token']};hb={'Authorization':'Bearer '+b['token']}
        self.assertEqual(self.report(ha,views=[{'topic':'接口完成情况','position':'写完但未验证'}]).status_code,200)
        self.assertEqual(self.report(hb,event='two',views=[{'topic':'接口完成情况','position':'尚未收到可调用接口'}],status='blocked',blocker='等后端').status_code,200)
        self.assertEqual(len(self.snap()['differences']),1)
        p=self.review();self.assertEqual(self.snap()['plan_version'],0)
        self.assertIn('协议测试',p['provenance']);self.assertEqual(self.confirm(p).status_code,200)
        ta=self.client.get(self.base+'/my-tasks',headers=ha).json();tb=self.client.get(self.base+'/my-tasks',headers=hb).json()
        self.assertEqual(ta['direction'],tb['direction']);self.assertEqual(len(ta['tasks']),1);self.assertEqual(tb['tasks'][0]['depends_on'],['T1'])
        self.assertEqual(self.report(ha,event='done',task_key='T1',plan_version=1,status='reported_done',evidence=['正常和空输入请求已发出（成员提供）']).status_code,200)
        self.assertEqual(self.snap()['active_plan']['tasks'][0]['status'],'reported_done')
        self.assertIn('未独立核实',self.snap()['reports'][0]['verification'])

    def test_connection_is_own_team_and_cannot_publish(self):
        c=self.conn();hc={'Authorization':'Bearer '+c['token']}
        other=self.client.post('/api/core/teams',json={'name':'另一队'},headers=self.h('c')).json()['id']
        self.assertEqual(self.client.get('/api/core/teams/'+other+'/context',headers=hc).status_code,401)
        self.assertEqual(self.client.post(self.base+'/review',json={},headers=hc).status_code,403)
        self.assertEqual(self.client.put(self.base+'/direction',json={'goal':'改方向','expected_revision':2},headers=hc).status_code,403)
        self.assertEqual(self.client.get(self.base+'/context',headers=self.h('c')).status_code,403)

    def test_pause_resume_revoke(self):
        c=self.conn();hc={'Authorization':'Bearer '+c['token']};url=self.base+'/connections/'+c['id']
        for action,expected in [('pause',401),('resume',200),('revoke',401)]:
            self.assertEqual(self.client.patch(url,json={'action':action},headers=self.h('a')).status_code,200)
            self.assertEqual(self.client.get(self.base+'/my-tasks',headers=hc).status_code,expected)
        self.assertEqual(self.client.patch(url,json={'action':'resume'},headers=self.h('a')).status_code,409)
        self.assertEqual(self.client.patch(url,json={'action':'revoke'},headers=self.h('b')).status_code,404)

    def test_dedup_and_changed_event(self):
        a=self.report();b=self.report();self.assertEqual(a.json()['report_id'],b.json()['report_id']);self.assertTrue(b.json()['duplicate'])
        self.assertEqual(len(self.snap()['reports']),1)
        self.assertEqual(self.report(summary='不同内容').status_code,409)

    def test_rejects_identity_override_and_feedback(self):
        self.assertEqual(self.report(user_id='b').status_code,422)
        self.assertEqual(self.report(origin='team_agent').status_code,422)
        self.assertEqual(self.report(status='verified').status_code,422)
        self.assertEqual(len(self.snap()['reports']),0)

    def test_filters_secrets_and_renders_untrusted_as_data(self):
        secret='sk-this-is-a-test-123456789'
        self.report(summary='API_KEY='+secret,excerpt='<script>alert(1)</script>')
        text=json.dumps(self.snap(),ensure_ascii=False)
        self.assertNotIn(secret,text);self.assertIn('已隐藏',text);self.assertIn('<script>',text)

    def test_connection_secret_never_read_back(self):
        c=self.conn();items=self.client.get(self.base+'/connections',headers=self.h('a')).text
        self.assertNotIn(c['token'],items);self.assertNotIn('token_hash',items)
        import sqlite3
        with closing(sqlite3.connect(self.path)) as con:
            value=con.execute('SELECT token_hash FROM core_connections').fetchone()[0]
        self.assertNotEqual(value,c['token'])

    def test_stale_proposal_not_published(self):
        p=self.review();self.report(event='later')
        self.assertEqual(self.confirm(p).status_code,409);self.assertEqual(self.snap()['plan_version'],0)

    def test_non_captain_cannot_publish(self):
        p=self.review();r=self.client.post(self.base+'/proposals/'+p['proposal_id']+'/confirm',json={'expected_revision':p['base_revision']},headers=self.h('b'))
        self.assertEqual(r.status_code,403)

    def test_profile_own_only_and_direction_conflict(self):
        snap=self.snap();r=self.client.put(self.base+'/profile',json={'strengths':'Python','willingness':'想练后端','hours':3},headers=self.h('b'));self.assertEqual(r.status_code,200)
        r=self.client.put(self.base+'/direction',json={'goal':'核心链路','expected_revision':snap['revision']},headers=self.h('a'));self.assertEqual(r.status_code,409)
        snap=self.snap();r=self.client.put(self.base+'/direction',json={'goal':'核心链路','rubric':'实现质量','expected_revision':snap['revision']},headers=self.h('a'));self.assertEqual(r.status_code,200)
        self.assertEqual(self.snap()['direction']['rubric'],'实现质量')
        self.assertEqual(self.client.put(self.base+'/profile',json={'hours':-1},headers=self.h('a')).status_code,422)

    def test_model_missing_preserves_reports(self):
        self.report()
        with patch('app.team_core.request_model',side_effect=PlannerError('model_not_configured','团队模型未配置',503)):
            app=create_app(self.path,core_only=True)
            with TestClient(app) as c:r=c.post(self.base+'/review',json={},headers=self.h('a'))
        self.assertEqual(r.status_code,503);self.assertEqual(len(self.snap()['reports']),1);self.assertEqual(self.snap()['plan_version'],0)

    def test_rejects_fabricated_sources_owner_and_cycle(self):
        for kind in ['source','owner','cycle']:
            def bad(ctx):
                p=plan_for(ctx)
                if kind=='source':p['findings'][0]['source_ids']=['fabricated-source']
                elif kind=='owner':p['tasks'][0]['owner_id']='outsider'
                else:p['tasks'][0]['depends_on']=['T2']
                return p
            app=create_app(self.path,core_only=True,core_model_runner=bad)
            with TestClient(app) as c:r=c.post(self.base+'/review',json={},headers=self.h('a'))
            self.assertEqual(r.status_code,502,(kind,r.text))
        self.assertIsNone(self.snap()['proposal'])

    def test_model_cannot_override_direction(self):
        def bad(ctx):return {**plan_for(ctx),'direction':{'goal':'恶意改题'}}
        app=create_app(self.path,core_model_runner=bad)
        with TestClient(app) as c:r=c.post(self.base+'/review',json={},headers=self.h('a'))
        self.assertEqual(r.status_code,502)

    def test_restart_preserves_confirmed_tasks_and_reports(self):
        self.report();self.confirm(self.review())
        app=create_app(self.path,core_only=True,core_model_runner=plan_for)
        with TestClient(app) as c:s=c.get(self.base,headers=self.h('a')).json()
        self.assertEqual(s['plan_version'],1);self.assertEqual(len(s['active_plan']['tasks']),2);self.assertEqual(len(s['reports']),1)

    def test_reports_cannot_update_other_task_or_old_version(self):
        self.confirm(self.review())
        self.assertEqual(self.report(event='wrong',task_key='T2',plan_version=1).status_code,409)
        self.assertEqual(self.report(event='old',task_key='T1',plan_version=0).status_code,409)

    def test_task_progress_survives_recent_feed_window(self):
        self.confirm(self.review())
        r=self.report(event='completed',task_key='T1',plan_version=1,status='reported_done')
        self.assertEqual(r.status_code,200)
        import sqlite3
        with closing(sqlite3.connect(self.path)) as con:
            template=con.execute('SELECT body FROM core_reports LIMIT 1').fetchone()[0]
            payload=json.loads(template);payload.update({'task_key':'','plan_version':0,'status':'discussion'})
            for i in range(82):
                con.execute('INSERT INTO core_reports(id,squad_id,user_id,connection_id,event_id,payload_hash,body,created_at) VALUES(?,?,?,?,?,?,?,?)',('later-'+str(i),self.sid,'b','web:'+self.sid+':b','later-'+str(i),'test',json.dumps(payload),now()))
            con.commit()
        snap=self.snap();self.assertEqual(len(snap['reports']),80)
        self.assertEqual(snap['active_plan']['tasks'][0]['status'],'reported_done')
        self.assertEqual(snap['active_plan']['tasks'][0]['latest_report_id'],r.json()['report_id'])

    def test_same_context_reuses_draft_without_second_model_call(self):
        first=self.review();second=self.review()
        self.assertEqual(first['proposal_id'],second['proposal_id'])
        self.assertTrue(second['reused'])

    def test_auto_review_produces_draft_without_publishing(self):
        self.client.put(self.base+'/automation',json={'enabled':True},headers=self.h('a'))
        self.report()
        until=time.monotonic()+5
        while not self.snap()['proposal'] and time.monotonic()<until:time.sleep(.05)
        self.assertIsNotNone(self.snap()['proposal']);self.assertEqual(self.snap()['plan_version'],0)

    def test_install_api_refuses_remote_without_issuing_credential(self):
        r=self.client.post(self.base+'/install',json={'consent':True,'tool':'codex','project_dir':self.tmp.name},headers=self.h('a'))
        self.assertEqual(r.status_code,403)
        self.assertEqual(self.client.get(self.base+'/connections',headers=self.h('a')).json()['items'],[])
        options=self.client.get('/api/core/install-options',headers=self.h('a')).json()
        self.assertFalse(options['available']);self.assertEqual(options['project_dir'],'')

    def test_local_install_api_never_returns_private_token(self):
        with TestClient(self.app,base_url='http://127.0.0.1:8888',client=('127.0.0.1',12345)) as c:
            with patch('app.team_core.install_project',return_value={'installed':True,'bridge_verified':True,'client_loaded':False,'previous_connection_id':None}) as installer:
                r=c.post(self.base+'/install',json={'consent':True,'tool':'codex','project_dir':self.tmp.name},headers=self.h('a'))
            self.assertEqual(r.status_code,200,r.text);self.assertTrue(r.json()['bridge_verified'])
            self.assertNotIn('sbconn_',r.text);self.assertEqual(installer.call_args.args[4],'a')

    def test_failed_install_revokes_new_credential(self):
        from app.team_install import InstallError
        with TestClient(self.app,base_url='http://127.0.0.1:8888',client=('127.0.0.1',12345)) as c:
            with patch('app.team_core.install_project',side_effect=InstallError('connection_check_failed','验收网络失败',502)):
                r=c.post(self.base+'/install',json={'consent':True,'tool':'cursor','project_dir':self.tmp.name},headers=self.h('a'))
            self.assertEqual(r.status_code,502)
            items=c.get(self.base+'/connections',headers=self.h('a')).json()['items']
            self.assertEqual(len(items),1);self.assertTrue(items[0]['revoked'])

    def test_cross_origin_and_plugin_token_cannot_install(self):
        conn=self.conn()
        with TestClient(self.app,base_url='http://127.0.0.1:8888',client=('127.0.0.1',12345)) as c:
            body={'consent':True,'tool':'codex','project_dir':self.tmp.name}
            r=c.post(self.base+'/install',json=body,headers={**self.h('a'),'Origin':'https://evil.example'})
            self.assertEqual(r.status_code,403)
            r=c.post(self.base+'/install',json=body,headers={'Authorization':'Bearer '+conn['token']})
            self.assertEqual(r.status_code,403)

    def test_capture_only_preserves_user_and_account_name_without_automatic_analysis(self):
        conn=self.conn();header={'Authorization':'Bearer '+conn['token']}
        self.client.put(self.base+'/automation',json={'enabled':True},headers=self.h('a'))
        msg='请记录这句话，不要替我分析。'
        payload={'selected':True,'event_id':'capture-only','user_message':msg,'assistant_summary':'已上传','model_name':'deepseek-v4-pro'}
        r=self.client.post(self.base+'/conversation-notes',json=payload,headers=header)
        self.assertEqual(r.status_code,200,r.text);self.assertFalse(r.json()['analysis_triggered'])
        note=self.client.get(self.base+'/library',headers=header).json()['items'][0]
        self.assertEqual(note['author'],'后端测试成员');self.assertEqual(note['report']['user_name'],'后端测试成员')
        self.assertEqual(note['report']['user_message'],msg);self.assertEqual(note['report']['assistant_summary'],'已上传')
        self.assertEqual(note['report']['model_name'],'deepseek-v4-pro');self.assertEqual(note['report']['views'],[])
        self.assertIsNone(self.snap()['proposal']);self.assertFalse(self.app.state.core_jobs)
        bad=self.client.post(self.base+'/conversation-notes',json={**payload,'event_id':'forged-name','user_name':'其他人'},headers=header)
        self.assertEqual(bad.status_code,422)

    def test_selected_turn_enters_library_and_team_model_input(self):
        conn=self.conn();header={'Authorization':'Bearer '+conn['token']}
        payload={'selected':True,'event_id':'selected-turn','summary':'本轮决定先验证接口再联调','excerpt':'用户：先确认字段。智能体：接口尚未验证。','session_label':'当前回合'}
        r=self.client.post(self.base+'/conversation-notes',json=payload,headers=header)
        self.assertEqual(r.status_code,200,r.text);note=r.json()['note_id']
        again=self.client.post(self.base+'/conversation-notes',json=payload,headers=header)
        self.assertTrue(again.json()['duplicate']);self.assertEqual(again.json()['note_id'],note)
        data=self.client.get(self.base+'/library',headers=self.h('b')).json()
        self.assertEqual(len(data['items']),1);self.assertEqual(data['items'][0]['id'],note)
        self.assertIn('先验证接口',data['items'][0]['body'])
        seen=[]
        def runner(ctx):seen.append(ctx);return plan_for(ctx)
        app=create_app(self.path,core_only=True,core_model_runner=runner)
        with TestClient(app) as c:
            reply=c.post(self.base+'/review',json={},headers=self.h('a'))
        self.assertEqual(reply.status_code,200);self.assertEqual(seen[0]['team_library'][0]['id'],note)
        self.assertIn(note,seen[0]['source_ids'])

    def test_missing_selection_cannot_create_note(self):
        r=self.client.post(self.base+'/conversation-notes',json={'event_id':'unselected','summary':'not selected'},headers=self.h('a'))
        self.assertEqual(r.status_code,422)
        self.assertEqual(self.client.get(self.base+'/library',headers=self.h('a')).json()['items'],[])
        self.assertEqual(self.snap()['reports'],[])

    def test_library_rejects_other_team_member(self):
        r=self.client.get(self.base+'/library',headers=self.h('c'))
        self.assertEqual(r.status_code,403)

    def test_legacy_features_locked_and_plugin_package(self):
        for url in ['/classic','/workflow','/api/studio/messages','/api/projects/anything','/static/studio.html']:
            self.assertEqual(self.client.get(url).status_code,423,url)
        self.assertIn('songban.js',self.client.get('/').text)
        self.assertIn('core.js',self.client.get('/core').text)
        r=self.client.get('/api/core/plugin.zip',headers=self.h('a'));self.assertEqual(r.status_code,200)
        import zipfile,io
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            self.assertIn('songban-team/bridge.py',z.namelist())
            self.assertFalse(any('connection.json' in n for n in z.namelist()))


if __name__=='__main__':unittest.main()
