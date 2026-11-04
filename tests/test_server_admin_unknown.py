"""Administrator reconciliation through registered HTTP routes; no external I/O."""
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from app.creative_studio import register_studio
from app.server_admin import AdminSettings, register_server_admin
from tests.test_learning_v2_identity import Fixture, ORIGIN
from tests import test_platform_http as platform_fixture

PREFIX = '/api/server-admin/v1'
EVIDENCE = '已核对隔离容器退出及供应商记录；结果仍无法确定，保留已占额度。'


class AdminUnknownTests(Fixture, unittest.TestCase):
    post = platform_fixture.PlatformHttpTests.post
    provider = platform_fixture.PlatformHttpTests.provider

    def setUp(self):
        platform_fixture.PlatformHttpTests.setUp(self)
        self.config = dict(enabled=True, model='synthetic-model', api_key='synthetic-only',
                           max_calls=4, max_output_tokens=800, timeout_seconds=20, revision=1)
        self.executions = []
        def uncertain(payload):
            self.executions.append(True)
            payload['reserve_call']()
            raise TimeoutError('synthetic uncertainty')
        self.studio = register_studio(self.app, self.app.state.platform_v1,
                                      lambda **kw: self.config, uncertain)
        project = self.post('/studio/projects', {'title':'虚构项目', 'idea':'只供权限测试'}, 201)
        project = self.post('/studio/projects/'+project['id']+'/messages',
                            {'expected_revision':1, 'text':'不能出现在管理列表的孩子聊天'})
        self.job_id = project['jobs'][0]['id']
        self.studio.worker_once()
        self.admin = register_server_admin(self.app, self.service,
            AdminSettings(allowed_emails=('parent-a@example.test',), secret_dir=Path(self.tmp.name)/'admin-private'))
        self.manager = self.client()
        self.login(self.manager, 'parent-a')
        self.url = PREFIX+'/studio-jobs/'+self.job_id+'/close-unknown'

    def close(self, *, client=None, body=None, headers=None):
        client = client or self.manager
        if headers is None:
            headers = {'Origin':ORIGIN, 'X-CSRF-Token':self.bootstrap(client)['csrf_token']}
        return client.post(self.url, json=body or {'evidence':EVIDENCE}, headers=headers)

    def snapshot(self):
        with self.service.store.transaction() as con:
            return {table: [tuple(row) for row in con.execute('SELECT * FROM '+table)]
                    for table in ('creative_calls', 'creative_versions')}

    def test_listing_is_minimal_and_closure_retains_usage_and_audits_evidence(self):
        response = self.manager.get(PREFIX+'/studio-jobs')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response.headers['cache-control'])
        self.assertEqual(set(response.json()['items'][0]), {'id','state','failure_code','created_at'})
        self.assertNotIn('孩子聊天', response.text)
        before = self.snapshot()
        response = self.close()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()['usage_refunded'])
        self.assertEqual(response.json()['state'], 'failed')
        self.assertEqual(self.snapshot(), before)
        with self.service.store.transaction() as con:
            row = con.execute('SELECT * FROM creative_reconciliations WHERE job_id=?', (self.job_id,)).fetchone()
            self.assertIn(EVIDENCE, tuple(row))
            self.assertIn('parent-a', tuple(row))
        audit = self.manager.get(PREFIX+'/audit').json()['items'][0]
        self.assertEqual(audit['action'], 'unknown_job_closed')
        self.assertIn('job:'+self.job_id, audit['changed_fields'])
        self.assertEqual(self.close().status_code, 409)
        self.assertEqual(self.manager.get(PREFIX+'/studio-jobs').json()['items'], [])
        self.studio.worker_once()
        self.assertEqual(self.executions, [True])

    def test_anonymous_ordinary_child_and_forged_admin_denied(self):
        self.assertEqual(self.b.get(PREFIX+'/studio-jobs').status_code, 401)
        self.assertEqual(self.close(client=self.b).status_code, 401)
        self.login(self.b, 'parent-b')
        self.assertEqual(self.b.get(PREFIX+'/studio-jobs', headers={'X-Admin-Email':'parent-a@example.test'}).status_code, 403)
        self.assertEqual(self.close(client=self.b).status_code, 403)
        self.enter(self.manager, self.lid)
        self.assertEqual(self.manager.get(PREFIX+'/studio-jobs', headers={'Authorization':'Bearer old-parent-a'}).status_code, 403)
        self.assertEqual(self.close().status_code, 403)

    def test_csrf_origin_evidence_and_revocation_are_enforced(self):
        self.assertEqual(self.close(headers={'Origin':ORIGIN}).status_code, 403)
        self.assertEqual(self.close(headers={'Origin':'https://foreign.example.test',
            'X-CSRF-Token':self.bootstrap(self.manager)['csrf_token']}).status_code, 403)
        for evidence in (' ', 'short', ' '*20, 'x'*3001):
            self.assertEqual(self.close(body={'evidence':evidence}).status_code, 422)
        self.assertEqual(self.close(body={'evidence':EVIDENCE, 'refund':True}).status_code, 422)
        self.admin.settings = replace(self.admin.settings, allowed_emails=())
        self.assertEqual(self.close().status_code, 403)
        self.assertEqual(self.manager.get(PREFIX+'/studio-jobs').status_code, 403)

    def test_final_identity_recheck_rolls_back_closure_and_both_audits(self):
        original = self.studio.close_unknown
        def revoke(*args, **kwargs):
            original(*args, **kwargs)
            kwargs['con'].execute("UPDATE people SET email='revoked@example.test' WHERE id='parent-a'")
        with patch.object(self.studio, 'close_unknown', side_effect=revoke):
            self.assertEqual(self.close().status_code, 403)
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute('SELECT state FROM creative_jobs WHERE id=?',(self.job_id,)).fetchone()[0], 'unknown')
            self.assertEqual(con.execute('SELECT COUNT(*) FROM creative_reconciliations').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM server_admin_audit').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
