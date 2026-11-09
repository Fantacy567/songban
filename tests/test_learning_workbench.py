# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
"""Synthetic users, disposable SQLite and in-process HTTP; no live provider calls."""
import hashlib
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from tests.test_learning_v2_identity import Fixture, BASE, ORIGIN
from app.learning_workbench import register_workbench, WorkbenchService
from app.learning_workbench.schemas import COURSES
from app.learning_workbench.model import ModelRejected
from app.platform_v1 import PlatformService, PlatformSettings

PREFIX = '/api/platform/v1/learning-workbench'


class WorkbenchFixture(Fixture):
    def make_text(self, *args, **kwargs):
        value = super().make_text(*args, **kwargs)
        value['scope_purposes'].append({'scope': 'live_model', 'purpose': '虚构离线教学'})
        content = {k: value[k] for k in ('locale', 'title', 'text', 'scope_purposes')}
        value['text_sha256'] = hashlib.sha256(json.dumps(content, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        return value

    def setUp(self):
        super().setUp()
        self.manifest = Path(self.tmp.name) / 'teachers.json'
        self.manifest.write_text(json.dumps({'version': '1', 'teachers': [dict(course_id=course,
            name='虚构老师 ' + course, opening='先提出一个具体要求，然后修改检查保存。', suggestions=['写下要求'],
            goal='虚构课程目标', sources=[{'title': '隔离材料', 'url': 'https://example.test/reference'}], tools=['text-artifact'],
            system_prompt='只使用虚构测试资料', help_strategy=['先示范再由本人选择'], artifact_instruction='文字候选',
            knowledge_points=['修改与检查'], misconceptions=['生成不等于掌握'], review={'status': 'unreviewed'}) for course in COURSES]}, ensure_ascii=False), encoding='utf-8')
        guard = patch('app.learning_workbench.teachers.MANIFEST', self.manifest)
        guard.start()
        self.addCleanup(guard.stop)
        self.platform = PlatformService(self.service, PlatformSettings(enabled=True, demo_mode=True))
        self.platform.migrate()
        self.cfg = dict(enabled=True, base_url='https://api.deepseek.com', api_key='fictional-secret', model='fixture-model',
                        max_calls=10, max_output_tokens=800, timeout_seconds=15, max_concurrency=1, revision=1)
        self.provider_connections = []
        self.calls = []
        self.workbench = register_workbench(self.app, self.platform, self.provider, self.runner)
        self.lid, self.fid = self.create(self.a)
        profile = self.a.get(BASE + '/learners/' + self.lid + '/profile').json()
        self.write(self.a, '/learners/' + self.lid + '/consents', {'request_id': self.rid(),
            'expected_revision': profile['revision'], 'consent_version': 'fiction-v1',
            'scopes': ['learning', 'live_model'], 'acknowledged': True}, expected=201)
        self.enter(self.a, self.lid)

    def provider(self, kind='text', *, con=None):
        self.assertEqual(kind, 'text')
        self.assertIsNotNone(con)
        self.provider_connections.append(con)
        return dict(self.cfg)

    def runner(self, payload):
        self.calls.append(payload)
        # Dispatch occurs only after a committed running marker, outside a transaction.
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute("SELECT state FROM learning_workbench_jobs ORDER BY rowid DESC LIMIT 1").fetchone()[0], 'running')
        return {'reply': '这是虚构回复。可以继续修改并检查。',
                'artifact': {'title': '虚构文字成果', 'content': '<script>never executed</script>'},
                'actual_model': 'fixture-model', 'usage': {'prompt_tokens': 11, 'completion_tokens': 9}}

    def live(self):
        self.platform.settings = replace(self.platform.settings, demo_mode=False)

    def post_w(self, path, body=None, *, client=None, expected=200):
        client = client or self.a
        csrf = self.bootstrap(client)['csrf_token']
        result = client.post(PREFIX + path, json={'request_id': self.rid(), **(body or {})},
                             headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf})
        self.assertEqual(result.status_code, expected, result.text)
        return result.json()

    def open(self, course='ai-tools', **kwargs):
        return self.post_w('/sessions', {'course_id': course}, **kwargs)

    def read_w(self, chat, *, client=None, expected=200):
        result = (client or self.a).get(PREFIX + '/sessions/' + chat['id'])
        self.assertEqual(result.status_code, expected, result.text)
        return result.json()

    def mutate(self, chat, action, **body):
        expected = body.pop('expected', 200)
        return self.post_w('/sessions/' + chat['id'] + '/' + action,
            {'expected_revision': chat['revision'], **body}, expected=expected)

    def send(self, chat, *, mode='mock', **body):
        return self.mutate(chat, 'messages', content='做一张虚构星球名片', mode=mode, **body)

    def saved(self, chat, **body):
        return self.mutate(chat, 'artifacts', title='我写的草稿', content='由本人保存的纯文字', **body)

    def finish(self, chat):
        self.workbench.worker_once()
        return self.read_w(chat)


class WorkbenchTests(WorkbenchFixture, unittest.TestCase):
    def test_seven_teachers_public_projection_and_stable_private_sessions(self):
        response = self.b.get(PREFIX + '/teachers')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()['teachers']), 7)
        self.assertNotIn('system_prompt', response.text)
        self.assertNotIn('help_strategy', response.text)
        chats = [self.open(course) for course in COURSES]
        self.assertEqual(len({c['id'] for c in chats}), 7)
        self.assertEqual(self.open()['id'], chats[0]['id'])
        self.assertEqual(len(self.a.get(PREFIX + '/sessions').json()['items']), 7)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.b.get(PREFIX + '/sessions').status_code, 401)

    def test_missing_or_invalid_teacher_manifest_fails_clearly_without_creating_session(self):
        self.manifest.write_text('{}', encoding='utf-8')
        result = self.b.get(PREFIX + '/teachers')
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json()['error']['code'], 'teachers_unavailable')
        self.open(expected=503)
        self.assertEqual(self.a.get(PREFIX + '/sessions').json()['items'], [])

    def test_mock_is_explicit_and_durable_and_never_saves_candidate_as_artifact(self):
        self.workbench.runner = None
        chat = self.send(self.open())
        self.assertEqual(chat['messages'][0]['status'], 'pending')
        self.assertEqual(chat['artifact_versions'], [])
        final = self.finish(chat)
        message = final['messages'][0]
        self.assertIn('模拟', message['assistant_text'])
        self.assertEqual(message['mode'], 'mock')
        self.assertIsNone(message['actual_model'])
        self.assertIsNotNone(message['artifact'])
        self.assertEqual(final['artifact_versions'], [])
        self.assertGreater(final['revision'], chat['revision'])
        self.assertEqual(self.calls, [])

    def test_mock_character_demo_keeps_name_and_hobby_across_followup_and_selected_version(self):
        self.workbench.runner = None
        opened = self.open()
        first = self.finish(self.mutate(opened, 'messages', content='请给会潜水的小狐狸写三行角色介绍卡', mode='mock'))
        original = first['messages'][-1]['artifact']['content']
        self.assertIn('名字：会潜水的小狐狸', original)
        self.assertIn('爱好：寻找海底的彩色贝壳', original)
        second = self.finish(self.mutate(first, 'messages', content='保留名字爱好，把本领改成给海星讲笑话', mode='mock'))
        changed = second['messages'][-1]['artifact']['content']
        self.assertIn('名字：会潜水的小狐狸', changed)
        self.assertIn('爱好：寻找海底的彩色贝壳', changed)
        self.assertIn('本领：给海星讲笑话', changed)
        saved = self.mutate(second, 'artifacts', title='我自己改过的角色', content='名字：蓝尾狐狸\n爱好：画海底地图\n本领：和鲸鱼聊天')
        third = self.finish(self.mutate(saved, 'messages', content='保留名字和爱好，把本领改成点亮贝壳灯', mode='mock'))
        self.assertIn('名字：蓝尾狐狸\n爱好：画海底地图\n本领：点亮贝壳灯', third['messages'][-1]['artifact']['content'])
        self.assertEqual(len(third['artifact_versions']), 1)
        self.assertEqual(self.calls, [])

    def test_owner_parent_and_other_learner_cannot_read_or_mutate_child_chat(self):
        child = self.saved(self.open())
        self.login(self.b, 'parent-a')
        self.read_w(child, client=self.b, expected=404)
        personal = self.open(client=self.b)
        self.assertNotEqual(personal['id'], child['id'])
        lid2, _ = self.create(self.b, 'parent-b')
        self.enter(self.b, lid2)
        self.read_w(child, client=self.b, expected=404)
        self.post_w('/sessions/' + child['id'] + '/record-draft', {'expected_revision': child['revision']}, client=self.b, expected=404)
        self.assertEqual(self.b.get(PREFIX + '/records').json()['items'], [])

    def test_csrf_origin_and_client_owner_hints_rejected(self):
        chat = self.open()
        body = {'request_id': self.rid(), 'course_id': 'api'}
        self.assertEqual(self.a.post(PREFIX + '/sessions', json=body).status_code, 403)
        self.post_w('/sessions', {**body, 'owner': 'learner:someone'}, expected=422)
        self.post_w('/sessions?owner=someone', body, expected=422)
        self.assertEqual(self.a.get(PREFIX + '/sessions/' + chat['id'] + '?learner_id=someone').status_code, 422)
        self.assertEqual(self.b.get(PREFIX + '/teachers', headers={'Origin': 'https://evil.test'}).status_code, 403)

    def test_duplicate_request_refreshes_current_view_without_second_dispatch(self):
        chat, rid = self.open(), self.rid()
        pending = self.send(chat, request_id=rid)
        self.assertEqual(self.send(chat, request_id=rid)['revision'], pending['revision'])
        completed = self.finish(chat)
        replay = self.send(chat, request_id=rid)
        self.assertEqual(replay['messages'], completed['messages'])
        self.assertIsNone(self.workbench.worker_once())
        self.assertEqual(len(self.calls), 1)
        conflict = self.mutate(chat, 'messages', request_id=rid, content='不同要求', mode='mock', expected=409)
        self.assertEqual(conflict['error']['code'], 'idempotency_conflict')

    def test_revision_conflict_does_not_add_message_or_artifact(self):
        old = self.open()
        current = self.saved(old)
        self.assertEqual(self.send(old, expected=409)['error']['code'], 'revision_conflict')
        self.assertEqual(self.saved(old, expected=409)['error']['current_revision'], current['revision'])
        self.assertEqual(len(self.read_w(old)['artifact_versions']), 1)
        self.assertEqual(self.calls, [])

    def test_artifact_versions_selection_and_cross_session_source_protection(self):
        completed = self.finish(self.send(self.open()))
        mid = completed['messages'][0]['id']
        first = self.saved(completed, source_message_id=mid)
        old = first['selected_artifact_id']
        second = self.saved(first)
        chosen = self.mutate(second, 'select-artifact', version_id=old)
        self.assertEqual(chosen['selected_artifact_id'], old)
        self.assertEqual(len(chosen['artifact_versions']), 2)
        other = self.open('api')
        self.saved(other, source_message_id=mid, expected=404)
        self.mutate(other, 'select-artifact', version_id=old, expected=404)

    def test_drafts_confirmations_and_record_list_preserve_confirmed_text(self):
        chat = self.open()
        self.mutate(chat, 'record-draft', expected=409)
        chat = self.saved(chat)
        draft = self.mutate(chat, 'record-draft')
        self.assertEqual(draft['record']['method'], 'evidence')
        self.assertEqual(self.a.get(PREFIX + '/records').json()['items'], [])
        confirmed = self.mutate(draft, 'record-confirm', title='本人确认的标题', summary='我保留这段自己编辑的记录。', next_step='')
        rid = confirmed['record']['id']
        self.assertEqual(confirmed['record']['status'], 'confirmed')
        new_draft = self.mutate(confirmed, 'record-draft')
        self.assertEqual(new_draft['record']['id'], rid)
        self.assertEqual(new_draft['record']['status'], 'draft')
        self.assertEqual(new_draft['confirmed_record']['summary'], '我保留这段自己编辑的记录。')
        records = self.a.get(PREFIX + '/records').json()['items']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0], confirmed['record'])
        edited = self.mutate(new_draft, 'record-confirm', title='第二次确认', summary='我改变了下一步想法。', next_step='再验证一次')
        self.assertEqual(edited['record']['id'], rid)
        self.assertEqual(len(edited['record_versions']), 4)
        self.assertEqual(edited['record_versions'][1], confirmed['record'])
        self.assertEqual(len(self.a.get(PREFIX + '/records').json()['items']), 1)
        self.mutate(edited, 'record-confirm', title='未经草稿', summary='不能直接覆盖', next_step='', expected=409)

    def test_failed_submission_is_described_as_a_request_not_completed_work(self):
        self.workbench.runner = lambda _: (_ for _ in ()).throw(ValueError('private error'))
        chat = self.finish(self.send(self.open()))
        self.assertEqual(chat['messages'][0]['status'], 'failed')
        record = self.mutate(chat, 'record-draft')['record']
        self.assertIn('提交过的要求', record['summary'])
        self.assertIn('还没有保存实际作品', record['summary'])
        self.assertEqual(record['source_message_ids'], [chat['messages'][0]['id']])

    def test_pending_jobs_and_full_history_survive_service_recreation(self):
        chat = self.send(self.saved(self.open()))
        restarted = WorkbenchService(self.platform, self.provider, self.runner)
        restarted.migrate()
        self.assertEqual(self.calls, [])
        restarted.worker_once()
        recovered = self.read_w(chat)
        self.assertEqual(recovered['messages'][0]['status'], 'succeeded')
        self.assertEqual(len(recovered['artifact_versions']), 1)
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(restarted.worker_once())

    def test_demo_disables_live_and_real_mode_disables_mock(self):
        chat = self.open()
        self.assertTrue(chat['capabilities']['mock'])
        self.assertFalse(chat['capabilities']['live'])
        self.send(chat, mode='live', expected=423)
        self.live()
        self.send(chat, expected=403)
        self.cfg['enabled'] = False
        self.assertFalse(self.read_w(chat)['capabilities']['live'])
        self.send(chat, mode='live', expected=423)
        self.assertEqual(self.calls, [])

    def test_live_success_bounded_payload_and_no_secrets_in_snapshots(self):
        self.live()
        self.cfg['max_output_tokens'] = 4096
        chat = self.send(self.open(), mode='live')
        self.assertEqual(self.calls, [])
        final = self.finish(chat)
        message = final['messages'][0]
        self.assertEqual(message['actual_model'], 'fixture-model')
        self.assertEqual(message['artifact']['content'], '<script>never executed</script>')
        self.assertEqual(self.calls[0]['max_output_tokens'], 800)
        self.assertEqual(self.calls[0]['input']['course_id'], 'ai-tools')
        self.assertIn('help_strategy', self.calls[0]['teacher'])
        self.assertNotIn('config', self.calls[0])
        with self.service.store.transaction() as con:
            rows = list(con.execute('SELECT input_snapshot,config_hash FROM learning_workbench_jobs'))
            receipts = list(con.execute('SELECT result FROM platform_requests'))
        self.assertNotIn('fictional-secret', str(rows) + str(receipts) + json.dumps(final))
        self.assertTrue(self.provider_connections)

    def test_unknown_keeps_budget_and_is_never_retried_by_replay_get_or_restart(self):
        self.live()
        calls = []
        def timeout(payload):
            calls.append(payload)
            raise TimeoutError('fictional-secret must not leak')
        self.workbench.runner = timeout
        chat, rid = self.open(), self.rid()
        pending = self.send(chat, mode='live', request_id=rid)
        unknown = self.finish(pending)
        self.assertEqual(unknown['messages'][0]['status'], 'unknown')
        self.assertNotIn('fictional-secret', json.dumps(unknown))
        self.send(chat, mode='live', request_id=rid)
        self.send(unknown, mode='live', expected=409)
        restarted = WorkbenchService(self.platform, self.provider, timeout)
        restarted.migrate()
        self.assertIsNone(restarted.worker_once())
        with self.service.store.transaction() as con:
            self.assertEqual(restarted.used_calls(con), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.read_w(chat)['messages']), 1)

    def test_expired_running_lease_recovers_unknown_and_discards_late_success(self):
        self.live()
        def late(payload):
            self.calls.append(payload)
            self.now[0] += 46
            view = self.read_w(chat)
            self.assertEqual(view['messages'][0]['status'], 'unknown')
            return {'reply': '迟到的回复', 'actual_model': 'fixture-model'}
        self.workbench.runner = late
        chat = self.send(self.open(), mode='live')
        final = self.finish(chat)
        self.assertEqual(final['messages'][0]['status'], 'unknown')
        self.assertIsNone(final['messages'][0]['assistant_text'])
        self.assertIsNone(self.workbench.worker_once())
        self.assertEqual(len(self.calls), 1)

    def test_identity_switch_before_dispatch_cancels_and_releases_unspent_reservation(self):
        self.live()
        chat = self.send(self.open(), mode='live')
        self.login(self.a)
        self.workbench.worker_once()
        self.enter(self.a, self.lid)
        result = self.read_w(chat)
        self.assertEqual(result['messages'][0]['status'], 'failed')
        self.assertEqual(self.calls, [])
        with self.service.store.transaction() as con:
            self.assertEqual(self.workbench.used_calls(con), 0)

    def test_identity_switch_during_dispatch_rejects_late_private_output(self):
        self.live()
        def switch(payload):
            result = self.runner(payload)
            self.login(self.a)
            return result
        self.workbench.runner = switch
        chat = self.send(self.open(), mode='live')
        self.workbench.worker_once()
        self.read_w(chat, expected=404)
        self.enter(self.a, self.lid)
        final = self.read_w(chat)
        self.assertEqual(final['messages'][0]['status'], 'failed')
        self.assertIsNone(final['messages'][0]['assistant_text'])
        self.assertIsNone(final['messages'][0]['artifact'])
        with self.service.store.transaction() as con:
            self.assertEqual(self.workbench.used_calls(con), 1)

    def test_config_change_before_dispatch_cancels_without_call_and_cap_never_resets(self):
        self.live()
        self.cfg['max_calls'] = 1
        chat = self.send(self.open(), mode='live')
        self.cfg['revision'] += 1
        failed = self.finish(chat)
        self.assertEqual(failed['messages'][0]['failure_code'], 'configuration_changed')
        self.assertEqual(self.calls, [])
        done = self.finish(self.send(failed, mode='live'))
        self.cfg['revision'] += 1
        self.assertFalse(self.read_w(done)['capabilities']['live'])
        self.send(done, mode='live', expected=429)
        self.assertEqual(len(self.calls), 1)

    def test_provider_rejection_is_failed_and_duplicate_never_redispatches(self):
        self.live()
        calls = []
        def reject(payload):
            calls.append(payload)
            raise ModelRejected()
        self.workbench.runner = reject
        chat, rid = self.open(), self.rid()
        result = self.finish(self.send(chat, mode='live', request_id=rid))
        self.assertEqual(result['messages'][0]['status'], 'failed')
        self.send(chat, mode='live', request_id=rid)
        self.workbench.worker_once()
        self.assertEqual(len(calls), 1)

    def test_returned_invalid_model_output_is_failed_with_no_visible_partial_artifact(self):
        self.live()
        for output in ({'reply': ' ', 'actual_model': 'fixture'},
                       {'reply': 'ok', 'artifact': {'title': 'missing content'}, 'actual_model': 'fixture'},
                       {'reply': 'ok', 'actions': ['execute'], 'actual_model': 'fixture'},
                       {'reply': 'ok'}):
            with self.subTest(output=output):
                self.workbench.runner = lambda _, value=output: value
                chat = self.read_w(self.open())
                pending = self.send(chat, mode='live')
                result = self.finish(pending)
                message = result['messages'][-1]
                self.assertEqual(message['status'], 'failed')
                self.assertEqual(message['failure_code'], 'provider_invalid_output')
                self.assertIsNone(message['assistant_text'])
                self.assertIsNone(message['artifact'])
                self.assertIsNone(self.workbench.worker_once())
        with self.service.store.transaction() as con:
            self.assertEqual(self.workbench.used_calls(con), 4)

    def test_operator_reconciliation_preserves_spend_and_never_restarts_message(self):
        self.live()
        self.workbench.runner = lambda _: (_ for _ in ()).throw(TimeoutError())
        chat, rid = self.open(), self.rid()
        final = self.finish(self.send(chat, mode='live', request_id=rid))
        mid = final['messages'][0]['id']
        with self.assertRaises(ValueError):
            self.workbench.close_unknown(mid, evidence='短', authority='operator')
        self.workbench.close_unknown(mid, evidence='虚构人工核对：保留额度，关闭未知结果。', authority='synthetic-operator')
        self.workbench.close_unknown(mid, evidence='虚构人工核对：重复操作不改变记录。', authority='synthetic-operator')
        replay = self.send(chat, mode='live', request_id=rid)
        self.assertEqual(replay['messages'][0]['failure_code'], 'operator_closed_unknown')
        self.assertIsNone(self.workbench.worker_once())
        with self.service.store.transaction() as con:
            self.assertEqual(self.workbench.used_calls(con), 1)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM learning_workbench_reconciliations').fetchone()[0], 1)

    def test_two_workers_only_one_claims_the_request(self):
        self.live()
        started, release = threading.Event(), threading.Event()
        def held(payload):
            self.calls.append(payload)
            started.set()
            self.assertTrue(release.wait(5))
            return {'reply': '一次成功', 'actual_model': 'fixture-model'}
        self.workbench.runner = held
        chat = self.send(self.open(), mode='live')
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.workbench.worker_once)
            self.assertTrue(started.wait(5))
            try:
                self.assertIsNone(pool.submit(self.workbench.worker_once).result(timeout=5))
            finally:
                release.set()
            first.result(timeout=5)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.read_w(chat)['messages'][0]['status'], 'succeeded')

    def test_live_authorization_rechecked_and_revoked_output_not_replayed(self):
        self.live()
        chat, rid = self.open(), self.rid()
        self.finish(self.send(chat, mode='live', request_id=rid))
        with self.service.store.transaction() as con:
            con.execute("UPDATE learn_consents SET scopes='[\"learning\"]' WHERE learner_id=?", (self.lid,))
        current = self.send(chat, mode='live', request_id=rid)
        self.assertIsNone(current['messages'][0]['assistant_text'])
        self.assertIsNone(current['messages'][0]['artifact'])
        self.assertFalse(current['capabilities']['live'])
        self.send(current, mode='live', expected=403)

    def test_learning_pause_and_platform_pause_preserve_readable_history(self):
        chat = self.saved(self.open())
        self.platform.settings = replace(self.platform.settings, enabled=False)
        self.saved(chat, expected=423)
        self.assertEqual(self.read_w(chat)['artifact_versions'], chat['artifact_versions'])
        self.platform.settings = replace(self.platform.settings, enabled=True)
        self.service.settings = replace(self.service.settings, enabled=False)
        self.saved(chat, expected=423)
        self.assertEqual(self.read_w(chat)['artifact_versions'], chat['artifact_versions'])

    def test_mock_context_does_not_resurrect_revoked_live_candidate(self):
        self.live()
        self.workbench.runner = lambda _: {'reply': '以前授权时的回复', 'actual_model': 'fixture-model',
            'artifact': {'title': '以前的候选', 'content': '名字：不能复活的旧名字\n爱好：旧爱好\n本领：旧本领'}}
        chat = self.finish(self.send(self.open(), mode='live'))
        with self.service.store.transaction() as con:
            con.execute("UPDATE learn_consents SET scopes='[\"learning\"]' WHERE learner_id=?", (self.lid,))
        self.platform.settings = replace(self.platform.settings, demo_mode=True)
        self.workbench.runner = None
        result = self.finish(self.mutate(chat, 'messages', content='保留名字爱好，把本领改成给海星讲笑话', mode='mock'))
        self.assertNotIn('不能复活的旧名字', result['messages'][-1]['artifact']['content'])
        self.assertIsNone(result['messages'][0]['artifact'])


if __name__ == '__main__':
    unittest.main()
