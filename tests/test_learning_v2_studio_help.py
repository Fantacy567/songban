"""Independent E2 help projection regression tests. Synthetic ASGI/DB only.

The live protocol branch below uses httpx.MockTransport from ModelFixture;
no provider, private environment, or real model allowance is used.
"""
import json
import unittest
from dataclasses import replace

import httpx

try:
    from .test_learning_v2_course import CourseFixture
    from .test_learning_v2_models import ModelFixture
    from .test_learning_v2_identity import BASE
except ImportError:
    from test_learning_v2_course import CourseFixture
    from test_learning_v2_models import ModelFixture
    from test_learning_v2_identity import BASE

from app.learning_v2.protocol import canonical


class HelpTools:
    task_id = 'S1.1'

    def help_url(self):
        return '/runs/' + self.rid_run + '/help'

    def ask(self, question='怎样把活动时间写清楚？', mode='static'):
        return self.post(self.help_url(), dict(expected_revision=self.fresh()['revision'], role_id='guide',
                         help_level=1, mode=mode, question=question, source_ids=[],
                         task_id=self.task_id, task_card_version='0.1.0'), 202)

    def read_after_restart(self, service=None):
        service = service or self.new_service()
        service.migrate()
        client = self.client(self.new_app(service))
        client.cookies.update(self.a.cookies)
        result = self.get(self.help_url(), client=client)
        return result['items'], client

    def add_private_fields(self, event, *, legacy=False):
        with self.service.store.transaction() as con:
            private = self.service.meta(con, event['id'])
            private.update(secret_test_marker='private-only-secret-marker',
                           restricted_output='private-only-restricted-output',
                           source_account='private-only-parent-identity',
                           input_snapshot={'not_for_child': 'private-only-input-snapshot'})
            if legacy:
                private.pop('created_at', None)
                private.pop('question', None)
            con.execute('UPDATE learn_course_objects SET private=? WHERE id=?', (canonical(private), event['id']))

    def assert_no_private(self, value):
        encoded = json.dumps(value, ensure_ascii=False)
        for item in ('private-only-secret-marker', 'private-only-restricted-output',
                     'private-only-parent-identity', 'private-only-input-snapshot',
                     'synthetic-private-key', 'input_snapshot', 'source_account', 'restricted_output'):
            self.assertNotIn(item, encoded)


class StaticHelpProjectionTests(HelpTools, CourseFixture, unittest.TestCase):
    def test_static_post_and_refresh_restore_exact_question_and_creation_time(self):
        event = self.ask()
        self.assertEqual(event['question'], '怎样把活动时间写清楚？')
        self.assertEqual(event['created_at'], self.service.stamp())
        self.now[0] += 30
        items, _ = self.read_after_restart()
        self.assertEqual(items, [event])
        self.assertNotEqual(items[0]['created_at'], self.service.stamp())
        self.assertIsNone(items[0]['model_run_id'])

    def test_legacy_private_fields_are_null_not_fabricated_and_private_extras_stay_private(self):
        event = self.ask()
        self.add_private_fields(event, legacy=True)
        items, _ = self.read_after_restart()
        self.assertIsNone(items[0]['question'])
        self.assertIsNone(items[0]['created_at'])
        self.assertEqual(items[0]['text'], event['text'])
        self.assert_no_private(items)

    def test_projection_extends_old_help_schema_without_requiring_new_fields(self):
        event = self.ask()
        schema = self.service.contract.schemas['Help']
        old = {k: v for k, v in event.items() if k not in ('question', 'created_at')}
        self.assertTrue(self.service.contract.valid(old, schema))
        self.assertTrue(self.service.contract.valid(event, schema))
        self.assertTrue(self.service.contract.valid({**old, 'question': None, 'created_at': None}, schema))
        self.assertFalse(self.service.contract.valid({**event, 'question': {'raw': 'not-text'}}, schema))
        self.assertFalse(self.service.contract.valid({**event, 'created_at': 123}, schema))

    def test_foreign_learner_and_manager_cannot_read_question_or_response(self):
        event = self.ask('仅属于孩子甲的提问')
        other, _ = self.create(self.b, 'parent-b')
        self.enter(self.b, other)
        denied = self.b.get(BASE+self.help_url())
        self.assertEqual(denied.status_code, 404)
        self.assertNotIn(event['question'], denied.text)
        self.login(self.a)
        manager = self.a.get(BASE+self.help_url())
        self.assertEqual(manager.status_code, 403)
        self.assertNotIn(event['question'], manager.text)
        self.assertNotIn(event['text'], manager.text)

    def test_revoked_course_or_relationship_prevents_history_read(self):
        event = self.ask('撤权后不能泄露的提问')
        self.service.revoke_course_access(self.eid, authority='synthetic-test-only')
        denied = self.a.get(BASE+self.help_url())
        self.assertEqual(denied.status_code, 403)
        self.assertNotIn(event['question'], denied.text)
        self.service.revoke_relationship(self.lid, authority='synthetic-test-only')
        denied = self.a.get(BASE+self.help_url())
        self.assertIn(denied.status_code, (401, 403))
        self.assertNotIn(event['question'], denied.text)


class ModelHelpProjectionTests(HelpTools, ModelFixture, unittest.TestCase):
    task_id = 'S2.1'

    def live_help(self):
        def response(request):
            result = self.response()
            result['choices'][0]['message']['content'] = canonical({
                'text': '这条模型帮助仅可由仍获授权的本人读取。', 'actions': ['open_tool_card'], 'source_ids': []})
            return httpx.Response(200, json=result, request=request)
        self.response_hook = response
        event = self.ask(mode='live')
        self.assertIsNone(event['text'])
        self.service.process_model_jobs()
        item = self.get(self.help_url())['items'][0]
        self.assertEqual(item['text'], '这条模型帮助仅可由仍获授权的本人读取。')
        return item

    def test_mock_help_restores_user_question_without_any_transport_call(self):
        event = self.ask('我想让邀请文字更友好', 'mock')
        self.assertEqual(event['question'], '我想让邀请文字更友好')
        self.assertEqual(event['created_at'], self.service.stamp())
        self.assertIsNotNone(event['text'])
        self.add_private_fields(event)
        items, _ = self.read_after_restart()
        self.assertEqual(items, [event])
        self.assert_no_private(items)
        self.assertEqual(self.calls, [])

    def test_live_protocol_completion_keeps_question_timestamp_and_filters_private_metadata(self):
        event = self.live_help()
        self.add_private_fields(event)
        items, _ = self.read_after_restart()
        self.assertEqual(items[0]['question'], '怎样把活动时间写清楚？')
        self.assertEqual(items[0]['created_at'], event['created_at'])
        self.assertEqual(items[0]['text'], event['text'])
        self.assert_no_private(items)
        self.assertEqual(len(self.calls), 1)

    def test_live_revocation_redacts_response_and_actions_but_keeps_own_question(self):
        event = self.live_help()
        self.revoke_live()
        items, _ = self.read_after_restart()
        self.assertEqual(items[0]['question'], event['question'])
        self.assertEqual(items[0]['created_at'], event['created_at'])
        self.assertIsNone(items[0]['text'])
        self.assertEqual(items[0]['actions'], [])
        self.assertNotIn(event['text'], json.dumps(items, ensure_ascii=False))

    def test_pausing_then_revoking_live_consent_cannot_reveal_archived_answer(self):
        event = self.live_help()
        self.revoke_live()
        paused = self.new_service(replace(self.service.settings, enabled=False, course_enabled=False,
                                         models_enabled=False, model_settings=None, studio_enabled=False))
        items, _ = self.read_after_restart(paused)
        self.assertEqual(items[0]['question'], event['question'])
        self.assertIsNone(items[0]['text'])
        self.assertEqual(items[0]['actions'], [])
        self.assertNotIn(event['text'], json.dumps(items, ensure_ascii=False))

    def test_pause_preserves_only_authorized_history_and_rejects_new_help(self):
        event = self.live_help()
        paused = self.new_service(replace(self.service.settings, enabled=False, course_enabled=False,
                                         models_enabled=False, model_settings=None, studio_enabled=False))
        items, client = self.read_after_restart(paused)
        self.assertEqual(items[0]['text'], event['text'])
        self.assert_no_private(items)
        response = self.write(client, self.help_url(), dict(request_id=self.rid(), expected_revision=self.fresh()['revision'],
                   role_id='guide', help_level=1, mode='live', question='暂停不能再调用', source_ids=[],
                   task_id=self.task_id, task_card_version='0.1.0'), expected=None)
        # Disabled course operations may be unregistered (503); a retained
        # write route instead returns the existing learning_paused guard (423).
        self.assertIn((response.status_code, response.json()['error']['code']),
                      ((423, 'learning_paused'), (503, 'operation_unavailable')))
        self.assertEqual(len(self.calls), 1)


if __name__ == '__main__':
    unittest.main()
