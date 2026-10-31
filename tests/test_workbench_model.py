"""Offline HTTP transport tests of the production adapter, not model quality tests."""
import json
import unittest
from unittest.mock import patch

import httpx

from app.planner import PlannerError
from app.workbench_model import SYSTEM, clean_data, request_workbench_model, safe_actions


class WorkbenchModelTests(unittest.TestCase):
    def test_redaction_preserves_structural_strings_and_reference_lists(self):
        opaque = 'a13800000000f'
        when = '2026-11-02T12:00:00.13800000000+08:00'
        original = {'id': opaque, 'fingerprint': opaque, 'owner_id': opaque,
                    'context_fingerprint': opaque, 'created_at': when,
                    'direction': {'deadline': when, 'goal': '联系13800000000'},
                    'scope': 'personal', 'status': 'partial', 'nature': 'sample',
                    'history': [{'role': 'user', 'text': '示例联系号码13800000000'}],
                    'my_tasks': [{'key': opaque, 'depends_on': [opaque], 'title': '联系13800000000'}],
                    'coverage': {'truncated_source_ids': [opaque]},
                    'segments': [{'id': opaque, 'method': 'ocr', 'text': 'API_KEY=sk-testsecret123456789'}]}
        result = clean_data(original)
        for key in ('id', 'fingerprint', 'owner_id', 'context_fingerprint', 'created_at', 'scope', 'status', 'nature'):
            self.assertEqual(result[key], original[key])
        self.assertEqual(result['direction']['deadline'], when)
        action = safe_actions([{'type': 'prepare_direction', 'label': '核对截止时间', 'fields': {'deadline': when}}])[0]
        self.assertEqual(action['fields']['deadline'], when)
        self.assertEqual(result['my_tasks'][0]['depends_on'], [opaque])
        self.assertEqual(result['coverage']['truncated_source_ids'], [opaque])
        self.assertEqual(result['segments'][0]['id'], opaque)
        self.assertNotIn('13800000000', result['history'][0]['text'])
        self.assertNotIn('13800000000', result['direction']['goal'])
        self.assertNotIn('13800000000', result['my_tasks'][0]['title'])
        self.assertNotIn('sk-testsecret123456789', result['segments'][0]['text'])

    def test_unknown_fields_and_malformed_structural_containers_are_redacted(self):
        text = 'Bearer credential-test-123456; 手机13800000000'
        result = clean_data({'new_field': text, 'future_secret_id': text,
                             'id': {'notes': text}, 'fingerprint': [text],
                             'depends_on': [{'comment': text}]})
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertNotIn('credential-test-123456', encoded)
        self.assertNotIn('13800000000', encoded)

    def invoke(self, handler):
        real_client = httpx.Client
        config = {'api_key': 'test-only-no-real-key', 'model_id': 'requested-test-model', 'base_url': 'https://api.openai.com/v1'}
        def client(**kwargs):
            return real_client(transport=httpx.MockTransport(handler), **kwargs)
        with patch('app.workbench_model.team_model_config', return_value=config), patch('app.workbench_model.httpx.Client', client):
            return request_workbench_model({'role': {'id': 'direction'}, 'text': '协议输入', 'sources': [], 'history': []})

    def test_independent_prompt_and_actual_response_model(self):
        seen = []
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200, json={'model': 'actual-response-model', 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'text': 'mocked network protocol result', 'actions': []})}}]})
        result = self.invoke(handler)
        self.assertEqual(result['requested_model'], 'requested-test-model')
        self.assertEqual(result['actual_model'], 'actual-response-model')
        self.assertEqual(result['mode'], 'live')  # Adapter branch; HTTP transport is still a test mock.
        self.assertEqual(seen[0]['messages'][0]['content'], SYSTEM)
        self.assertIn('项目工作台', SYSTEM)
        self.assertNotIn('test-only-no-real-key', json.dumps(seen))

    def test_missing_actual_model_never_inherits_requested_model(self):
        result = self.invoke(lambda r: httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '{"text":"mocked result"}'}}]}))
        self.assertIsNone(result['actual_model'])
        self.assertEqual(result['requested_model'], 'requested-test-model')

    def test_timeout_and_connection_failure_are_unknown(self):
        for exception, expected in ((httpx.ReadTimeout('test timeout'), 'model_timeout'), (httpx.ReadError('test disconnect'), 'model_result_unknown')):
            calls = []
            def handler(request):
                calls.append(1)
                raise exception
            with self.assertRaises(PlannerError) as raised:
                self.invoke(handler)
            self.assertEqual(raised.exception.code, expected)
            self.assertEqual(len(calls), 1)

    def test_invalid_refusal_incomplete_and_oversized_output(self):
        for payload in (
            {'choices': [{'finish_reason': 'length', 'message': {'content': '{"text":"cut off"}'}}]},
            {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"text":"no"}', 'refusal': 'no'}}]},
            {'choices': [{'finish_reason': 'stop', 'message': {'content': 'not json'}}]},
            {'choices': [{'finish_reason': 'stop', 'message': {'content': 'x' * 170000}}]},
        ):
            with self.subTest(payload=str(payload)[:100]), self.assertRaises(PlannerError) as raised:
                self.invoke(lambda r: httpx.Response(200, json=payload))
            self.assertEqual(raised.exception.code, 'model_invalid_output')

    def test_provider_failures_do_not_return_fixture(self):
        for status, code in ((402, 'model_insufficient_balance'), (401, 'model_auth_failed'), (429, 'model_rate_limited'), (500, 'model_unavailable')):
            with self.assertRaises(PlannerError) as raised:
                self.invoke(lambda r: httpx.Response(status, text='test provider failure'))
            self.assertEqual(raised.exception.code, code)

    def test_untrusted_host_rejected_before_network(self):
        config = {'api_key': 'test-only', 'model_id': 'test', 'base_url': 'http://127.0.0.1:1'}
        with patch('app.workbench_model.team_model_config', return_value=config), patch('app.workbench_model.httpx.Client') as client:
            with self.assertRaises(PlannerError):
                request_workbench_model({})
            client.assert_not_called()

    def test_timezone_and_unknown_action_fields(self):
        actions = [
            {'type': 'prepare_direction', 'label': '有时区', 'fields': {'deadline': '2026-11-02T12:00:00+08:00', 'hidden': 'discard'}},
            {'type': 'prepare_direction', 'label': '无时区', 'fields': {'deadline': '2026-11-02T12:00:00'}},
            {'type': 'open_page', 'label': '对象页码', 'page': {'bad': True}},
            {'type': 'share_turn', 'label': 'x' * 121},
        ]
        self.assertEqual(safe_actions(actions), [{'type': 'prepare_direction', 'label': '有时区', 'fields': {'deadline': '2026-11-02T12:00:00+08:00'}}])


if __name__ == '__main__':
    unittest.main()
