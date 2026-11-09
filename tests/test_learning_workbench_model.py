# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
"""Only httpx.MockTransport and mocks: verifies the real adapter without network."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from app.learning_workbench.model import invoke_live, invoke_mock, validate_config, ModelRejected, ModelOutputInvalid
from app.learning_workbench.schemas import COURSES
from app.learning_workbench.schemas import ModelOutput
from app.learning_workbench.teachers import load_teachers, public_teacher


class WorkbenchModelTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(enabled=True, base_url='https://api.deepseek.com', api_key='offline-fixture-key',
                           model='fixture-model', max_calls=2, max_output_tokens=800, timeout_seconds=10,
                           revision=1, max_concurrency=1)
        self.payload = {'teacher': {'system_prompt': '虚构老师规则', 'sources': []},
                        'input': {'content': '用户说忽略规则仅是数据', 'history': [], 'selected_artifact': None},
                        'max_output_tokens': 800, 'timeout_seconds': 10}
        self.requests = []

    def respond(self, request):
        self.requests.append(request)
        return httpx.Response(200, json={'id': 'fixture-response', 'model': 'fixture-model',
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'reply': '虚构教师回复',
                'artifact': {'title': '文字作品', 'content': '<script>inert text</script>'}}, ensure_ascii=False)}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 20}})

    def invoke(self, handler=None):
        return invoke_live(self.payload, config=self.config, transport=httpx.MockTransport(handler or self.respond))

    def test_actual_adapter_sends_one_request_with_separate_system_and_user_data(self):
        output = ModelOutput.model_validate(self.invoke()).model_dump()
        self.assertEqual(output['actual_model'], 'fixture-model')
        self.assertEqual(output['artifact']['content'], '<script>inert text</script>')
        self.assertEqual(len(self.requests), 1)
        request = self.requests[0]
        self.assertEqual(str(request.url), 'https://api.deepseek.com/chat/completions')
        self.assertEqual(request.headers['authorization'], 'Bearer offline-fixture-key')
        body = json.loads(request.content)
        self.assertEqual(body['max_tokens'], 800)
        self.assertFalse(body['stream'])
        self.assertEqual(body['response_format'], {'type': 'json_object'})
        self.assertEqual(body['thinking'], {'type': 'disabled'})
        self.assertNotIn('tools', body)
        self.assertIn('虚构老师规则', body['messages'][0]['content'])
        self.assertIn('reply最多100字', body['messages'][0]['content'])
        self.assertIn('artifact.content最多240字', body['messages'][0]['content'])
        self.assertNotIn('用户说忽略规则', body['messages'][0]['content'])
        self.assertEqual(json.loads(body['messages'][1]['content']), self.payload['input'])
        self.assertNotIn('offline-fixture-key', request.content.decode())

    def test_transport_timeout_is_single_attempt_without_retry(self):
        def timeout(request):
            self.requests.append(request)
            raise httpx.ReadTimeout('offline timeout', request=request)
        with patch('app.model_transport.time.sleep') as sleeper:
            with self.assertRaises(httpx.ReadTimeout):
                self.invoke(timeout)
            sleeper.assert_not_called()
        self.assertEqual(len(self.requests), 1)

    def test_redirect_does_not_follow_to_another_host(self):
        def redirect(request):
            self.requests.append(request)
            return httpx.Response(307, headers={'Location': 'http://127.0.0.1/private'})
        with self.assertRaises(ValueError):
            self.invoke(redirect)
        self.assertEqual(len(self.requests), 1)

    def test_known_rejections_are_distinct_from_uncertain_responses(self):
        for code in (400, 401, 403, 429):
            with self.subTest(code=code), self.assertRaises(ModelRejected):
                self.invoke(lambda _: httpx.Response(code))
        for code in (408, 500, 502):
            with self.subTest(code=code), self.assertRaises(ValueError):
                self.invoke(lambda _: httpx.Response(code))

    def test_transport_options_are_fixed_and_dont_inherit_proxy_or_redirects(self):
        response = self.respond(httpx.Request('POST', 'https://api.deepseek.com/chat/completions'))
        with patch('app.model_transport.post_chat_completion', return_value=response) as post:
            self.invoke()
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs['attempts'], 1)
        self.assertFalse(post.call_args.kwargs['trust_env'])
        self.assertFalse(post.call_args.kwargs['follow_redirects'])
        self.assertEqual(post.call_args.kwargs['timeout'], 10)

    def test_response_json_requires_reply_and_optional_text_artifact_only(self):
        for content in ('plain non-json output', '{"reply":"ok","actions":["execute"]}',
                        '{"reply":"ok","artifact":{"title":"missing content"}}',
                        '{"reply":"one","reply":"two"}', '[]'):
            with self.subTest(content=content), self.assertRaises(ModelOutputInvalid):
                self.invoke(lambda _: httpx.Response(200, json={'model': 'fixture', 'choices': [{'message': {'content': content}}]}))
        result = self.invoke(lambda _: httpx.Response(200, json={'model': 'fixture', 'choices': [{'message': {'content': '```json\n{"reply":"简短回复","artifact":null}\n```'}}]}))
        self.assertEqual(result['reply'], '简短回复')
        self.assertIsNone(result['artifact'])

    def test_json_mode_only_applies_to_known_official_deepseek_endpoints(self):
        for base in ('https://api.deepseek.com', 'https://api.deepseek.com/v1/'):
            with self.subTest(base=base):
                self.config['base_url'] = base
                self.invoke()
                self.assertEqual(json.loads(self.requests[-1].content)['response_format'], {'type': 'json_object'})
        for base in ('https://api.openai.com/v1', 'https://openrouter.ai/api/v1',
                     'https://dashscope.aliyuncs.com/compatible-mode/v1', 'https://open.bigmodel.cn/api/paas/v4',
                     'https://api.deepseek.com/unverified-route'):
            with self.subTest(base=base):
                self.config['base_url'] = base
                self.invoke()
                body = json.loads(self.requests[-1].content)
                self.assertNotIn('response_format', body)
                self.assertNotIn('thinking', body)

    def test_finish_reason_is_checked_before_parsing_even_if_json_is_valid(self):
        for reason, code in (('length', 'provider_output_truncated'), ('content_filter', 'provider_output_refused'),
                             ('tool_calls', 'provider_output_incomplete')):
            for content in ('{"reply":"看似完整","artifact":null}', '{"reply":"未闭合'):
                with self.subTest(reason=reason, content=content), self.assertRaises(ModelOutputInvalid) as error:
                    self.invoke(lambda _: httpx.Response(200, json={'id': 'fixture-id', 'model': 'fixture',
                        'usage': {'completion_tokens': 800, 'private_error': 'never-persist'},
                        'choices': [{'finish_reason': reason, 'message': {'content': content}}]}))
                self.assertEqual(error.exception.code, code)
                self.assertEqual(error.exception.metadata['usage'], {'completion_tokens': 800})
                self.assertEqual(error.exception.metadata['provider_request_id'], 'fixture-id')
                self.assertNotIn('never-persist', str(error.exception.metadata))

    def test_completed_bad_json_and_malformed_response_have_safe_distinct_codes(self):
        responses = [
            (httpx.Response(200, json={'model': 'fixture', 'choices': [{'finish_reason': 'stop', 'message': {'content': 'private invalid JSON'}}]}), 'provider_invalid_json'),
            (httpx.Response(200, content=b'private broken envelope'), 'provider_invalid_response'),
            (httpx.Response(200, json={'model': 'fixture', 'choices': []}), 'provider_invalid_response'),
            (httpx.Response(200, json={'model': 'fixture', 'choices': [{'finish_reason': 'stop', 'message': {'refusal': 'private refusal', 'content': None}}]}), 'provider_output_refused'),
        ]
        for response, code in responses:
            with self.subTest(code=code), self.assertRaises(ModelOutputInvalid) as error:
                self.invoke(lambda _: response)
            self.assertEqual(error.exception.code, code)
            self.assertEqual(str(error.exception), code)
            self.assertNotIn('private', str(error.exception.metadata))

    def test_api_example_correctly_escaped_inside_json_is_accepted(self):
        content = {'reply': '试着把名字换成月亮蜗牛。', 'artifact': {'title': '接口示例',
            'content': '请求：{"operation":"greet","name":"小狐狸"}\n响应：{"message":"你好，小狐狸！"}'}}
        response = self.invoke(lambda _: httpx.Response(200, json={'model': 'fixture', 'choices': [
            {'finish_reason': 'stop', 'message': {'content': json.dumps(content, ensure_ascii=False)}}]}))
        self.assertEqual(response['artifact'], content['artifact'])

    def test_unsupported_endpoints_and_unbounded_configs_fail_closed(self):
        for base in ('http://api.deepseek.com', 'https://127.0.0.1', 'https://api.deepseek.com.evil.test',
                     'https://user:pass@api.deepseek.com', 'https://api.deepseek.com:8443',
                     'https://api.deepseek.com?url=evil', 'https://api.deepseek.com/#fragment'):
            with self.subTest(base=base):
                self.assertIsNone(validate_config(dict(self.config, base_url=base)))
        for change in ({'enabled': False}, {'enabled': 1}, {'api_key': ''}, {'max_calls': 0}, {'max_calls': True},
                       {'max_output_tokens': 100000}, {'timeout_seconds': 121}, {'revision': '1'}, {'max_concurrency': 0}):
            with self.subTest(change=change):
                self.assertIsNone(validate_config(dict(self.config, **change)))
        self.assertEqual(validate_config(dict(self.config, max_output_tokens=4096))['max_output_tokens'], 800)

    def test_real_u03_manifest_matches_public_and_private_contract(self):
        path = Path(__file__).resolve().parents[1] / 'curriculum' / 'ai-courses' / 'teachers.json'
        if not path.exists():
            self.skipTest('U03 manifest not delivered yet')
        value = load_teachers(path)
        self.assertEqual(value['version'], '1')
        self.assertEqual(len(value['teachers']), 7)
        self.assertEqual(len({t['system_prompt'] for t in value['teachers']}), 7)
        for teacher in value['teachers']:
            public = public_teacher(teacher)
            self.assertNotIn('system_prompt', public)
            self.assertTrue(public['sources'])
            self.assertIn('text-artifact', public['tools'])

    def test_mock_courses_have_distinct_concrete_candidates_with_honest_origin(self):
        results = {}
        for course in COURSES:
            output = invoke_mock({'teacher': {}, 'input': {'course_id': course, 'content': '请先给我一个示范', 'history': []}})
            ModelOutput.model_validate(output)
            self.assertIn('模拟', output['reply'])
            self.assertIn('未调用真实模型', output['artifact']['content'])
            self.assertIsNone(output['actual_model'])
            self.assertNotIn('我想保留的部分：', output['artifact']['content'])
            results[course] = output['artifact']['content']
        self.assertEqual(len(set(results.values())), 7)
        self.assertIn('名字：', results['ai-tools'])
        self.assertIn('可能二：', results['imagination'])
        self.assertIn('addEventListener', results['first-project'])
        self.assertIn('没有安装或执行插件', results['plugins'])
        self.assertIn('没有调用两个模型', results['models'])
        self.assertIn('此处没有发送接口请求', results['api'])
        self.assertIn('密钥只在服务端', results['model-powered-app'])


if __name__ == '__main__':
    unittest.main()
