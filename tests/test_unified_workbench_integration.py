"""U期 full application paths: synthetic identity, real SQLite, no provider I/O."""
from dataclasses import replace
import unittest

from tests import test_platform_http as baseline
from tests.test_learning_v2_identity import Fixture

P = '/api/platform/v1/learning-workbench'


class UnifiedWorkbenchIntegrationTests(Fixture, unittest.TestCase):
    post = baseline.PlatformHttpTests.post
    provider = baseline.PlatformHttpTests.provider

    def setUp(self):
        baseline.PlatformHttpTests.setUp(self)
        self.app = self.factory(self.path, core_only=True,
            learning_settings=replace(self.settings, navigation_enabled=True,
                studio_enabled=True, catalog_enabled=True, course_enabled=True),
            platform_settings=replace(self.platform_settings,
                navigation_enabled=True, creative_studio_enabled=True))
        self.service = self.app.state.learning_v2
        self.service.clock = lambda: self.now[0]
        self.a, self.b = self.client(), self.client()
        self.login(self.a, 'parent-a')
        self.enter(self.a, self.lid)

    def mutation(self, session, path, **body):
        return self.post('/learning-workbench/sessions/' + session['id'] + path,
                         dict(expected_revision=session['revision'], **body))

    def test_public_teachers_are_course_specific_and_private_history_is_protected(self):
        response = self.b.get(P + '/teachers')
        self.assertEqual(response.status_code, 200, response.text)
        teachers = response.json()['teachers']
        self.assertEqual(len(teachers), 7)
        self.assertEqual(len({t['opening'] for t in teachers}), 7)
        self.assertNotIn('system_prompt', response.text)
        self.assertEqual(self.b.get(P + '/sessions').status_code, 401)
        self.assertEqual(self.b.get(P + '/records').status_code, 401)
        session = self.post('/learning-workbench/sessions', {'course_id': 'ai-tools'})
        self.assertEqual(session['teacher']['course_id'], 'ai-tools')
        self.assertTrue(session['capabilities']['mock'])
        self.assertFalse(session['capabilities']['live'])
        self.assertEqual(self.a.get('/api/platform/v1/learning-courses/ai-tools/progress').status_code, 200)
        self.assertEqual(self.a.get('/api/learning/v2/courses').status_code, 200)

    def test_actual_app_saves_versions_confirms_record_and_restores_original_course(self):
        session = self.post('/learning-workbench/sessions', {'course_id': 'ai-tools'})
        session = self.mutation(session, '/messages', content='帮我介绍一个喜欢植物的机器人。', mode='mock')
        self.app.state.learning_workbench.worker_once()
        session = self.a.get(P + '/sessions/' + session['id']).json()
        message = session['messages'][-1]
        self.assertEqual(message['status'], 'succeeded', session)
        self.assertIsNone(message['actual_model'])
        session = self.mutation(session, '/artifacts', title='我的植物机器人',
            content='我决定让它帮助植物找到阳光。', source_message_id=message['id'])
        first = session['selected_artifact_id']
        session = self.mutation(session, '/artifacts', title='我的植物机器人',
            content='我把它改成了胆小但愿意帮助植物的机器人。', source_message_id=message['id'])
        self.assertEqual(len(session['artifact_versions']), 2)
        session = self.mutation(session, '/select-artifact', version_id=first)
        self.assertEqual(session['selected_artifact_id'], first)
        session = self.mutation(session, '/record-draft')
        self.assertEqual(self.a.get(P + '/records').json()['items'], [])
        session = self.mutation(session, '/record-confirm', title='我的第一次 AI 尝试',
            summary='我提出了植物机器人的想法，比较两个版本后保留第一版。', next_step='下次想做一个按钮。')
        record_id = session['record']['id']
        records = self.a.get(P + '/records').json()['items']
        self.assertEqual(records[0]['id'], record_id)
        self.assertEqual(records[0]['artifact_version_id'], first)
        self.post('/learning-workbench/sessions', {'course_id': 'imagination'})
        restored = self.post('/learning-workbench/sessions', {'course_id': 'ai-tools'})
        self.assertEqual(restored['id'], session['id'])
        self.assertEqual(restored['record']['id'], record_id)
        self.assertEqual(len(restored['artifact_versions']), 2)
        self.assertEqual(len(self.a.get(P + '/sessions').json()['items']), 2)


if __name__ == '__main__':
    unittest.main()
