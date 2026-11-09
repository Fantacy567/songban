# Copyright (c) 2026 2292576833. Joint project ownership: COPYRIGHT.md.
"""Real Workbench + admin ASGI routes, synthetic identities and a timeout runner."""
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from app.learning_workbench.budget import text_used_calls, text_inflight
from app.server_admin import AdminSettings, register_server_admin
from tests.test_learning_workbench import WorkbenchFixture
from tests.test_learning_v2_identity import ORIGIN

PREFIX = '/api/server-admin/v1'
EVIDENCE = '已核对消息派发和供应商流水，无法确认结果；保留已占额度，不重试。'


class AdminWorkbenchUnknownTests(WorkbenchFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.live()
        self.executions = []
        def uncertain(payload):
            self.executions.append(payload['mode'])
            raise TimeoutError('synthetic provider uncertainty')
        self.workbench.runner = uncertain
        self.chat = self.saved(self.open())
        self.chat = self.finish(self.mutate(self.chat, 'messages', mode='live', content='孩子的私密聊天不能进入管理列表'))
        self.job_id = self.chat['messages'][0]['id']
        self.assertEqual(self.chat['messages'][0]['status'], 'unknown')
        self.admin = register_server_admin(self.app, self.service,
            AdminSettings(allowed_emails=('parent-a@example.test',), secret_dir=Path(self.tmp.name)/'admin-private'))
        self.manager = self.client()
        self.login(self.manager, 'parent-a')
        self.url = PREFIX+'/workbench-jobs/'+self.job_id+'/close-unknown'

    def close(self, *, client=None, body=None, headers=None, url=None):
        client = client or self.manager
        if headers is None:
            headers = {'Origin': ORIGIN, 'X-CSRF-Token': self.bootstrap(client)['csrf_token']}
        return client.post(url or self.url, json=body or {'evidence': EVIDENCE}, headers=headers)

    def durable_usage(self):
        with self.service.store.transaction() as con:
            job = con.execute('SELECT counted,usage,dispatched_at,provider_request_id FROM learning_workbench_jobs WHERE message_id=?', (self.job_id,)).fetchone()
            artifacts = [tuple(row) for row in con.execute('SELECT * FROM learning_workbench_artifacts')]
            return tuple(job), artifacts, text_used_calls(con)

    def test_list_and_close_use_workbench_keep_budget_and_never_redispatch(self):
        # A legacy studio object must not capture every route carrying job_id.
        studio = Mock()
        self.app.state.creative_studio = studio
        result = self.manager.get(PREFIX+'/workbench-jobs')
        self.assertEqual(result.status_code, 200)
        self.assertIn('no-store', result.headers['cache-control'])
        self.assertEqual(set(result.json()['items'][0]), {'id', 'state', 'failure_code', 'created_at'})
        self.assertEqual(result.json()['items'][0]['id'], self.job_id)
        for value in ('孩子的私密聊天', 'fictional-secret', self.chat['id'], 'auth_snapshot', 'input_snapshot'):
            self.assertNotIn(value, result.text)
        before = self.durable_usage()
        with self.service.store.transaction() as con:
            self.assertEqual(text_inflight(con), 1)
        response = self.close()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['state'], 'failed')
        self.assertFalse(response.json()['usage_refunded'])
        self.assertEqual(self.durable_usage(), before)
        studio.close_unknown.assert_not_called()
        with self.service.store.transaction() as con:
            self.assertEqual(text_inflight(con), 0)
            self.assertEqual(con.execute('SELECT status FROM learning_workbench_messages WHERE id=?', (self.job_id,)).fetchone()[0], 'failed')
            evidence = con.execute('SELECT * FROM learning_workbench_reconciliations WHERE message_id=?', (self.job_id,)).fetchone()
            self.assertEqual(evidence['evidence'], EVIDENCE)
            self.assertEqual(evidence['authority'], 'parent-a')
            self.assertTrue(evidence['created_at'])
        audit = self.manager.get(PREFIX+'/audit').json()['items']
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]['kind'], 'workbench_job')
        self.assertEqual(audit[0]['action'], 'unknown_job_closed')
        self.assertEqual(audit[0]['changed_fields'], ['job:'+self.job_id])
        self.assertEqual(self.close().status_code, 409)
        self.assertEqual(len(self.manager.get(PREFIX+'/audit').json()['items']), 1)
        self.assertEqual(self.manager.get(PREFIX+'/workbench-jobs').json()['items'], [])
        self.assertIsNone(self.workbench.worker_once())
        self.assertEqual(self.executions, ['live'])

    def test_anonymous_child_ordinary_and_unverified_email_are_denied(self):
        self.assertEqual(self.b.get(PREFIX+'/workbench-jobs').status_code, 401)
        self.assertEqual(self.close(client=self.b).status_code, 401)
        self.assertEqual(self.a.get(PREFIX+'/workbench-jobs').status_code, 403)
        self.assertEqual(self.close(client=self.a).status_code, 403)
        self.login(self.b, 'parent-b')
        self.assertEqual(self.b.get(PREFIX+'/workbench-jobs', headers={'X-Admin-Email': 'parent-a@example.test'}).status_code, 403)
        self.assertEqual(self.close(client=self.b).status_code, 403)
        # An unverified email is not present in people.email; client assertions
        # cannot replace the existing verified binding flow.
        with self.service.store.transaction() as con:
            con.execute("UPDATE people SET email=NULL WHERE id='parent-a'")
        self.assertEqual(self.manager.get(PREFIX+'/workbench-jobs', headers={'X-Admin-Email': 'parent-a@example.test'}).status_code, 403)
        self.assertEqual(self.close().status_code, 403)

    def test_csrf_origin_evidence_and_client_authority_are_rejected(self):
        self.assertEqual(self.close(headers={'Origin': ORIGIN}).status_code, 403)
        self.assertEqual(self.close(headers={'Origin': 'https://foreign.example.test',
            'X-CSRF-Token': self.bootstrap(self.manager)['csrf_token']}).status_code, 403)
        for evidence in (' ', 'short', ' '*20, 'x'*3001):
            self.assertEqual(self.close(body={'evidence': evidence}).status_code, 422)
        for extra in ({'authority': 'parent-a'}, {'refund': True}, {'email': 'parent-a@example.test'}):
            self.assertEqual(self.close(body={'evidence': EVIDENCE, **extra}).status_code, 422)
        self.assertEqual(self.close(url=self.url+'?refund=true').status_code, 422)
        self.assertEqual(self.manager.get(PREFIX+'/workbench-jobs').json()['items'][0]['state'], 'unknown')

    def test_final_identity_recheck_rolls_back_state_revision_evidence_and_audits(self):
        original = self.workbench.close_unknown
        with self.service.store.transaction() as con:
            tables = ('learning_workbench_jobs', 'learning_workbench_messages', 'learning_workbench_sessions',
                      'learning_workbench_reconciliations', 'server_admin_audit', 'learn_audit')
            before = {name: [tuple(row) for row in con.execute('SELECT * FROM '+name)] for name in tables}
        def revoke(*args, **kwargs):
            self.assertIsNotNone(kwargs.get('con'))
            original(*args, **kwargs)
            kwargs['con'].execute("UPDATE people SET email=NULL WHERE id='parent-a'")
        with patch.object(self.workbench, 'close_unknown', side_effect=revoke):
            self.assertEqual(self.close().status_code, 403)
        with self.service.store.transaction() as con:
            after = {name: [tuple(row) for row in con.execute('SELECT * FROM '+name)] for name in tables}
        self.assertEqual(before, after)
        self.assertEqual(self.executions, ['live'])

    def test_registration_does_not_depend_on_studio_or_docker_and_missing_jobs_fail(self):
        self.assertFalse(hasattr(self.app.state, 'creative_studio'))
        status = self.manager.get(PREFIX+'/session').json()['runtime']
        self.assertTrue(status['learning_workbench_registered'])
        self.assertFalse(status['creative_studio_registered'])
        self.assertEqual(self.close(url=PREFIX+'/workbench-jobs/missing/close-unknown').status_code, 404)
        self.assertEqual(self.manager.get(PREFIX+'/studio-jobs').status_code, 503)
        with patch.object(self.app.state, 'learning_workbench', None):
            self.assertEqual(self.manager.get(PREFIX+'/workbench-jobs').status_code, 503)
            self.assertEqual(self.close().status_code, 503)
            self.assertFalse(self.manager.get(PREFIX+'/session').json()['runtime']['learning_workbench_registered'])
        self.assertEqual(self.executions, ['live'])

    def test_saving_configuration_does_not_call_model_or_close_unknown(self):
        body = dict(request_id=self.rid(), expected_revision=0, enabled=False, model='fixture-model',
                    max_calls=0, max_output_tokens=800, timeout_seconds=30, max_concurrency=1,
                    api_key='', clear_key=False)
        headers = {'Origin': ORIGIN, 'X-CSRF-Token': self.bootstrap(self.manager)['csrf_token']}
        result = self.manager.put(PREFIX+'/providers/text', json=body, headers=headers)
        self.assertEqual(result.status_code, 200, result.text)
        result = self.manager.put(PREFIX+'/providers/workbench-jobs', json=body, headers=headers)
        self.assertEqual(result.status_code, 404)
        self.assertEqual(self.manager.get(PREFIX+'/workbench-jobs').json()['items'][0]['state'], 'unknown')
        self.assertEqual(self.executions, ['live'])


if __name__ == '__main__':
    unittest.main()
