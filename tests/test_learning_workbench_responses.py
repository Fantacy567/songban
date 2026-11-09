# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
"""Received-but-invalid text results never become unknown or trigger a retry."""
import json
import unittest

import httpx

from app.learning_workbench import WorkbenchService
from app.learning_workbench.model import invoke_live
from tests.test_learning_workbench import WorkbenchFixture


class WorkbenchResponseTests(WorkbenchFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.live()
        self.requests = []
        self.response = httpx.Response(200, json=self.envelope())
        self.workbench.runner = lambda payload: invoke_live(payload, config=self.cfg, transport=httpx.MockTransport(self.respond))

    def envelope(self, content=None, reason='stop'):
        return {'id': 'fixture-receipt', 'model': 'fixture-model', 'usage': {'prompt_tokens': 30, 'completion_tokens': 800},
            'choices': [{'finish_reason': reason, 'message': {'content': content if content is not None else
                json.dumps({'reply': '试着换一个虚构名字。', 'artifact': {'title': '接口示例', 'content': '{"name":"小狐狸"}'}})}}]}

    def respond(self, request):
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    def assert_receipt(self, mid):
        with self.service.store.transaction() as con:
            job = con.execute('SELECT * FROM learning_workbench_jobs WHERE message_id=?', (mid,)).fetchone()
            self.assertEqual(job['counted'], 1)
            self.assertEqual(job['provider_request_id'], 'fixture-receipt')
            self.assertEqual(json.loads(job['usage'])['completion_tokens'], 800)

    def test_truncation_is_failed_billed_and_not_redispatched_by_replay_or_restart(self):
        self.response = httpx.Response(200, json=self.envelope('{"reply":"partial private response', 'length'))
        chat, rid = self.open('api'), self.rid()
        final = self.finish(self.send(chat, mode='live', request_id=rid))
        message = final['messages'][0]
        self.assertEqual(message['status'], 'failed')
        self.assertEqual(message['failure_code'], 'provider_output_truncated')
        self.assertIsNone(message['assistant_text'])
        self.assertIsNone(message['artifact'])
        self.assertNotIn('partial private response', json.dumps(final))
        self.assert_receipt(message['id'])
        self.send(chat, mode='live', request_id=rid)
        self.assertIsNone(WorkbenchService(self.platform, self.provider, self.workbench.runner).worker_once())
        self.assertEqual(len(self.requests), 1)

    def test_received_bad_json_fails_without_changing_previous_artifact(self):
        self.response = httpx.Response(200, json=self.envelope('{"reply":"secret-detail", "artifact":{"content":"{"name":"fox"}"}}'))
        saved = self.saved(self.open('api'))
        final = self.finish(self.send(saved, mode='live'))
        self.assertEqual(final['messages'][0]['status'], 'failed')
        self.assertEqual(final['messages'][0]['failure_code'], 'provider_invalid_json')
        self.assertEqual(final['artifact_versions'], saved['artifact_versions'])
        self.assertEqual(final['selected_artifact_id'], saved['selected_artifact_id'])
        self.assertNotIn('secret-detail', json.dumps(final))
        self.assert_receipt(final['messages'][0]['id'])
        self.assertIsNone(self.workbench.worker_once())
        self.assertEqual(len(self.requests), 1)

    def test_correct_completed_json_succeeds_once(self):
        final = self.finish(self.send(self.open('api'), mode='live'))
        self.assertEqual(final['messages'][0]['status'], 'succeeded')
        self.assertEqual(final['messages'][0]['artifact']['content'], '{"name":"小狐狸"}')
        self.assert_receipt(final['messages'][0]['id'])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(json.loads(self.requests[0].content)['response_format'], {'type': 'json_object'})

    def test_network_timeout_still_unknown_and_never_retried(self):
        self.response = httpx.ReadTimeout('private transport detail')
        final = self.finish(self.send(self.open('api'), mode='live'))
        self.assertEqual(final['messages'][0]['status'], 'unknown')
        self.assertEqual(final['messages'][0]['failure_code'], 'result_uncertain')
        self.send(final, mode='live', expected=409)
        self.assertIsNone(self.workbench.worker_once())
        self.assertEqual(len(self.requests), 1)
        with self.service.store.transaction() as con:
            self.assertEqual(self.workbench.used_calls(con), 1)

    def test_received_invalid_response_uses_final_budget_without_refund(self):
        self.cfg['max_calls'] = 1
        self.response = httpx.Response(200, content=b'private malformed outer JSON')
        final = self.finish(self.send(self.open('api'), mode='live'))
        self.assertEqual(final['messages'][0]['status'], 'failed')
        self.assertEqual(final['messages'][0]['failure_code'], 'provider_invalid_response')
        self.assertFalse(final['capabilities']['live'])
        self.send(final, mode='live', expected=429)
        self.assertEqual(len(self.requests), 1)
        self.assertNotIn('private malformed', json.dumps(final))


if __name__ == '__main__':
    unittest.main()
