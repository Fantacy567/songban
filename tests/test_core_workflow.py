"""Current core loop: actual SQLite/auth/reports/checks; model is an explicit fixture."""
import copy
import unittest
from fastapi.testclient import TestClient
from app.main import create_app
from app.core_workflow import build_workflow
from tests import test_team_core as core


class WorkflowTests(unittest.TestCase):
    setUp=core.CoreTests.setUp
    tearDown=core.CoreTests.tearDown
    snap=core.CoreTests.snap
    conn=core.CoreTests.conn
    report=core.CoreTests.report
    review=core.CoreTests.review
    confirm=core.CoreTests.confirm

    def plan(self):
        s=self.snap()
        self.assertEqual(self.client.put(self.base+'/direction',headers=self.h('a'),json={'goal':'完成可用演示，计划第'+str(self.snap()['plan_version']+1)+'版','rules':'提交代码与演示','rubric':'协作与可用性','expected_revision':s['revision']}).status_code,200)
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.path)) as con:
            users=[r[0] for r in con.execute('SELECT user_id FROM squad_members WHERE squad_id=?',(self.sid,))]
        for user in users:
            for answer in ['负责自己的模块','独立做基础工作，复杂问题请队友帮忙','3','提供可查看成果并由队友检查']:
                state=self.client.get(self.base+'/division',headers=self.h(user)).json()
                result=self.client.post(self.base+'/division/answers',headers=self.h(user),json={'round_id':state['round_id'],'step':state['me']['step'],'answer':answer})
                self.assertEqual(result.status_code,200,result.text)
            result=self.client.post(self.base+'/division/confirm',headers=self.h(user),json={'round_id':state['round_id'],'confirmed':True})
            self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['status'],'published')

    def done(self,task='T1',member='a',event='done',evidence=None):
        r=self.report(self.h(member),event=event,task_key=task,plan_version=self.snap()['plan_version'],status='reported_done',evidence=['接口真实返回正常与失败结果（测试用文字）'] if evidence is None else evidence)
        self.assertEqual(r.status_code,200,r.text)
        return r.json()['report_id']

    def check(self,task='T1',member='b',**overrides):
        s=self.snap();t=next(t for t in s['active_plan']['tasks'] if t['key']==task)
        body={'expected_revision':s['revision'],'plan_version':s['plan_version'],'report_id':t['latest_report_id'],'verdict':'accepted','note':'按检查方法核对正常与失败返回。',**overrides}
        return self.client.post(self.base+'/tasks/'+task+'/check',headers=self.h(member),json=body)

    def test_next_action_is_personal_and_changes_after_peer_check(self):
        self.plan()
        a=self.snap();b=self.client.get(self.base,headers=self.h('b')).json()
        self.assertEqual(a['workflow']['next_action']['kind'],'start')
        self.assertEqual(b['workflow']['next_action']['kind'],'dependency')
        self.done()
        self.assertEqual(self.client.get(self.base,headers=self.h('b')).json()['workflow']['next_action']['kind'],'check')
        self.assertEqual(self.check().status_code,200)
        b=self.client.get(self.base+'/my-tasks',headers=self.h('b')).json()
        self.assertEqual(b['tasks'][0]['waiting_on'],[])
        self.assertEqual(b['next_action']['kind'],'start')
        t=self.snap()['active_plan']['tasks'][0]
        self.assertEqual(t['status'],'reported_done')
        self.assertEqual(t['handoff_state'],'accepted')

    def test_check_rejects_owner_plugin_and_outsider(self):
        self.plan();self.done()
        self.assertEqual(self.check(member='a').status_code,403)
        self.assertEqual(self.check(member='c').status_code,403)
        token=self.conn('b')['token'];s=self.snap();t=s['active_plan']['tasks'][0]
        r=self.client.post(self.base+'/tasks/T1/check',headers={'Authorization':'Bearer '+token},json={'expected_revision':s['revision'],'plan_version':1,'report_id':t['latest_report_id'],'verdict':'accepted','note':'工具不能替人检查'})
        self.assertEqual(r.status_code,403)

    def test_missing_evidence_can_return_but_cannot_accept(self):
        self.plan();self.done(evidence=[])
        self.assertEqual(self.check().status_code,422)
        self.assertEqual(self.check(verdict='changes_requested',note='请附可访问成果和验证结果。').status_code,200)
        self.assertEqual(self.snap()['workflow']['next_action']['kind'],'revise')
        self.assertEqual(self.check().status_code,409)
        self.done(event='revised')
        self.assertEqual(self.check().status_code,200)

    def test_stale_revision_report_plan_and_repeat_rejected(self):
        self.plan();old=self.done()
        self.report(event='new-discussion')
        self.assertEqual(self.check(expected_revision=1).status_code,409)
        self.done(event='new-outcome')
        self.assertEqual(self.check(report_id=old).status_code,409)
        self.assertEqual(self.check(plan_version=0).status_code,409)
        self.assertEqual(self.check().status_code,200)
        self.assertEqual(self.check().status_code,409)

    def test_check_requires_report_done_and_nonempty_note(self):
        self.plan()
        self.report(event='working',task_key='T1',plan_version=1,status='in_progress')
        self.assertEqual(self.check().status_code,409)
        self.done()
        self.assertEqual(self.check(note='  ').status_code,422)
        self.assertEqual(self.check(verdict='auto_verified').status_code,422)
        self.assertEqual(self.check(user_id='b').status_code,422)

    def test_dependencies_and_upstream_new_report_invalidate_downstream(self):
        self.plan();self.done('T2','b')
        self.assertEqual(self.check('T2','a').status_code,409)
        self.done();self.assertEqual(self.check().status_code,200)
        self.assertEqual(self.check('T2','a').status_code,200)
        self.assertTrue(self.snap()['workflow']['all_handoffs_checked'])
        self.done(event='upstream-modified')
        s=self.snap()
        self.assertFalse(s['workflow']['all_handoffs_checked'])
        self.assertEqual(s['active_plan']['tasks'][1]['handoff_state'],'dependency_changed')
        self.assertEqual(self.check().status_code,200)
        self.assertEqual(self.snap()['active_plan']['tasks'][1]['handoff_state'],'dependency_changed')
        self.done('T2','b',event='rechecked-against-current-upstream')
        self.assertEqual(self.check('T2','a').status_code,200)
        self.assertTrue(self.snap()['workflow']['all_handoffs_checked'])

    def test_new_plan_does_not_reuse_checks(self):
        self.plan();self.done();self.check()
        self.plan()
        s=self.snap()
        self.assertEqual(s['plan_version'],2)
        self.assertEqual(s['workflow']['accepted_tasks'],0)
        self.assertIsNone(s['active_plan']['tasks'][0]['handoff'])

    def test_completed_plan_points_to_delivery(self):
        self.plan();self.done();self.check()
        self.done('T2','b');self.check('T2','a')
        action=self.snap()['workflow']['next_action']
        self.assertEqual(action['kind'],'delivery')
        self.assertEqual(action['page'],'delivery')

    def test_single_member_has_reviewer_invitation_exit(self):
        self.plan();self.done()
        snap=self.snap();snap['members']=[m for m in snap['members'] if m['id']=='a']
        action=build_workflow(snap,'2026-10-31T00:00:00Z')['next_action']
        self.assertEqual(action['kind'],'invite_reviewer')
        self.assertEqual(action['page'],'team')
        self.assertEqual(self.check(member='a').status_code,403)

    def test_restart_preserves_check_and_export_has_truthful_limits(self):
        self.plan();self.done();check=self.check().json()
        with TestClient(create_app(self.path,core_only=True,core_model_runner=core.plan_for)) as c:
            s=c.get(self.base,headers=self.h('b')).json()
            self.assertEqual(s['active_plan']['tasks'][0]['handoff']['id'],check['check_id'])
            r=c.get(self.base+'/handoff.md',headers=self.h('b'))
        self.assertEqual(r.status_code,200)
        self.assertIn('v1',r.text);self.assertIn('同伴检查通过',r.text)
        self.assertIn('没有读取主办方收件状态',r.text)
        self.assertNotIn('test-token',r.text);self.assertNotIn('token_hash',r.text)
        self.assertEqual(self.client.get(self.base+'/handoff.md',headers=self.h('c')).status_code,403)

    def test_team_model_receives_only_sourced_human_check(self):
        self.plan();self.done();check=self.check().json();seen=[]
        def capture(ctx):seen.append(ctx);return core.plan_for(ctx)
        with TestClient(create_app(self.path,core_only=True,core_model_runner=capture)) as c:
            r=c.post(self.base+'/review',headers=self.h('a'),json={})
        self.assertEqual(r.status_code,200)
        self.assertIn(check['check_id'],seen[0]['source_ids'])
        self.assertEqual(seen[0]['active_plan']['tasks'][0]['handoff']['reviewer_id'],'b')

    def test_unknown_facts_empty_plan_and_deadline_are_not_completion(self):
        s=self.snap();w=s['workflow']
        self.assertEqual(w['next_action']['kind'],'direction')
        self.assertFalse(w['all_handoffs_checked'])
        self.assertEqual(w['deadline']['state'],'unknown')
        s['direction']={'goal':'演示','rules':'提交','rubric':'可用','deadline':'2026-10-29T18:00:00+08:00'}
        s['plan_version']=1
        w=build_workflow(s,'2026-10-29T09:00:00Z')
        self.assertEqual(w['next_action']['kind'],'empty_plan')
        self.assertEqual(w['deadline']['state'],'soon')
        self.assertFalse(w['all_handoffs_checked'])
        self.assertEqual(build_workflow(s,'2026-10-30T00:00:00Z')['deadline']['state'],'past_due')
        s['direction']['deadline']='2026-10-29T18:00:00'
        self.assertEqual(build_workflow(s,'2026-10-29T09:00:00Z')['deadline']['state'],'unknown')


if __name__=='__main__':unittest.main()
