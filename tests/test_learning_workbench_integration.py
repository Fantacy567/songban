# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
"""Verify the main application's registration with temporary DB and injected runner."""
import unittest
from dataclasses import replace

from tests import test_platform_http as baseline
from tests.test_learning_v2_identity import Fixture


class WorkbenchIntegrationTests(Fixture, unittest.TestCase):
    post = baseline.PlatformHttpTests.post
    provider = baseline.PlatformHttpTests.provider

    def setUp(self):
        baseline.PlatformHttpTests.setUp(self)

    def test_main_registers_once_and_mock_artifact_record_survives_factory_restart(self):
        workbench = self.app.state.learning_workbench
        teachers = self.b.get('/api/platform/v1/learning-workbench/teachers')
        self.assertEqual(teachers.status_code, 200, teachers.text)
        self.assertEqual(len(teachers.json()['teachers']), 7)
        chat = self.post('/learning-workbench/sessions', {'course_id': 'ai-tools'})
        path = '/learning-workbench/sessions/' + chat['id']
        queued = self.post(path + '/messages', {'expected_revision': chat['revision'], 'content': '做一个虚构的星星角色卡', 'mode': 'mock'})
        self.assertEqual(queued['messages'][0]['status'], 'pending')
        workbench.worker_once()
        done = self.a.get('/api/platform/v1' + path).json()
        candidate = done['messages'][0]['artifact']
        saved = self.post(path + '/artifacts', {'expected_revision': done['revision'], **candidate, 'source_message_id': done['messages'][0]['id']})
        draft = self.post(path + '/record-draft', {'expected_revision': saved['revision']})
        confirmed = self.post(path + '/record-confirm', {'expected_revision': draft['revision'], 'title': '虚构探索记录', 'summary': '我提出要求并修改保存了文字草稿。', 'next_step': '检查文字是否表达我的意思'})
        app2 = self.factory(self.path, learning_settings=self.settings, platform_settings=self.platform_settings)
        app2.state.learning_v2.clock = lambda: self.now[0]
        other = self.client(app2)
        other.cookies.update(self.a.cookies)
        restored = other.get('/api/platform/v1' + path)
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()['record'], confirmed['record'])
        self.assertEqual(restored.json()['artifact_versions'], confirmed['artifact_versions'])
        self.assertEqual(other.get('/api/platform/v1/learning-workbench/records').json()['items'], [confirmed['record']])
        self.assertEqual(self.calls, [])

    def test_main_injected_live_runner_works_without_harness_or_private_config(self):
        calls = []
        config = dict(enabled=True, model='fixture-model', base_url='https://api.deepseek.com', api_key='fake-key',
                      max_calls=1, max_output_tokens=800, timeout_seconds=10, revision=1)
        app = self.factory(self.path, learning_settings=self.settings,
            platform_settings=replace(self.platform_settings, demo_mode=False, creative_studio_enabled=False),
            learning_workbench_settings_provider=lambda *, con=None: config,
            learning_workbench_runner=lambda payload: calls.append(payload) or {'reply': '虚构老师回复', 'actual_model': 'fixture-model'})
        app.state.learning_v2.clock = lambda: self.now[0]
        client = self.client(app)
        client.cookies.update(self.a.cookies)
        chat = self.post('/learning-workbench/sessions', {'course_id': 'imagination'}, client=client)
        self.post('/learning-workbench/sessions/' + chat['id'] + '/messages', {'expected_revision': chat['revision'], 'content': '想一个虚构世界', 'mode': 'live'}, client=client)
        app.state.learning_workbench.worker_once()
        final = client.get('/api/platform/v1/learning-workbench/sessions/' + chat['id']).json()
        self.assertEqual(final['messages'][0]['status'], 'succeeded')
        self.assertEqual(len(calls), 1)
        self.assertFalse(hasattr(app.state, 'creative_studio'))
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
