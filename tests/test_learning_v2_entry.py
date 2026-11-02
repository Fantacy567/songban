"""E1 interview handoff: temporary DB and ASGI only, no private data or model."""
import json
import unittest
from dataclasses import replace

try:
    from .test_learning_v2_identity import BASE, Fixture
except ImportError:
    from test_learning_v2_identity import BASE, Fixture

from app.interview_store import SCHEMA as INTERVIEW_SCHEMA


class EntryTests(Fixture, unittest.TestCase):
    def new_service(self, settings=None):
        return super().new_service(settings or replace(self.settings, studio_enabled=True))

    def setUp(self):
        super().setUp()
        self.lid, _ = self.create(self.a)
        self.url = f'/learners/{self.lid}/entry'

    def source(self, actor='parent-a', version=7, status='confirmed', goals=None):
        draft = {'goals': goals if goals is not None else [
            {'text': '做一张故事交换会邀请卡', 'basis': 'self_reported', 'evidence': ['private-user-turn']},
            {'text': '推测将来一定是程序员', 'basis': 'inferred', 'evidence': ['private-ai-turn']}],
            'experiences': [{'text': '和朋友改过一次邀请文字', 'basis': 'self_reported', 'evidence': ['private-user-turn']}],
            'interests': [{'text': '私人兴趣不在本次授权字段', 'basis': 'self_reported', 'evidence': ['private-user-turn']}],
            'help_needed': [{'text': '无关家庭私事', 'basis': 'self_reported', 'evidence': ['private-user-turn']}],
            'time_available': None}
        with self.service.store.transaction() as con:
            for sql in INTERVIEW_SCHEMA.split(';'):
                if sql.strip():
                    con.execute(sql)
            con.execute('INSERT INTO core_interviews(user_id,age_band,stage,status,version,draft,source,confirmed_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET version=excluded.version,status=excluded.status,draft=excluded.draft',
                        (actor, 'fixture', 'initial', status, version, json.dumps(draft, ensure_ascii=False), '{}', '2026-11-02T00:00:00+00:00', '2026-11-02T00:00:00+00:00', '2026-11-02T00:00:00+00:00'))

    def offer(self, expected=200, **changes):
        body = {'request_id': self.rid(), 'expected_revision': 0, 'source_version': 7,
                'subject_confirmed': True, 'selected_fields': ['goals', 'experiences'], **changes}
        response = self.write(self.a, self.url, body, expected=expected)
        return response.json(), body

    def decide(self, decision='accept', revision=1, expected=200, request_id=None):
        body = {'request_id': request_id or self.rid(), 'expected_revision': revision, 'decision': decision}
        response = self.write(self.a, self.url+'/confirm', body, expected=expected)
        return response.json(), body

    def test_empty_compatible_without_interview_table_and_no_start_writes(self):
        value = self.a.get(BASE+self.url).json()
        self.assertEqual(value['status'], 'none')
        self.assertEqual(value['revision'], 0)
        self.assertIsNone(value['candidate'])
        self.offer(expected=409)
        self.enter(self.a, self.lid)
        self.assertEqual(self.a.get(BASE+self.url).json()['status'], 'none')
        start = self.a.get(BASE+f'/learners/{self.lid}/start').json()
        self.assertEqual(start['completion_status'], 'not_started')
        self.assertEqual(len(start['missing_fields']), 6)

    def test_manager_preview_is_minimal_and_child_cannot_preview_before_offer(self):
        self.source()
        data = self.a.get(BASE+self.url).json()
        self.assertEqual(data['candidate']['goals'], ['做一张故事交换会邀请卡'])
        self.assertEqual(data['candidate']['experiences'], ['和朋友改过一次邀请文字'])
        for private in ['private-user-turn', '私人兴趣', '无关家庭私事', '程序员', 'parent-a']:
            self.assertNotIn(private, json.dumps(data, ensure_ascii=False))
        self.enter(self.a, self.lid)
        child = self.a.get(BASE+self.url).json()
        self.assertIsNone(child['candidate'])
        self.assertEqual(child['goals'], [])
        self.assertNotIn('故事交换会', json.dumps(child, ensure_ascii=False))

    def test_unconfirmed_interview_and_other_owner_are_not_candidates(self):
        self.source(status='draft')
        self.source(actor='parent-b')
        self.assertIsNone(self.a.get(BASE+self.url).json()['candidate'])
        self.offer(expected=409)

    def test_offer_uses_server_selected_fields_and_keeps_provenance_private(self):
        self.source()
        data, _ = self.offer(selected_fields=['goals'])
        self.assertEqual(data['status'], 'offered')
        self.assertEqual(data['experiences'], [])
        self.enter(self.a, self.lid)
        child = self.a.get(BASE+self.url).json()
        self.assertIsNone(child['candidate'])
        self.assertEqual(child['goals'], ['做一张故事交换会邀请卡'])
        self.assertEqual(child['source_version'], 7)
        with self.service.store.transaction() as con:
            row = con.execute("SELECT private FROM learn_course_objects WHERE kind='entry' AND learner_id=?", (self.lid,)).fetchone()
            audit = json.loads(row['private'])
            self.assertEqual(audit['source_actor_id'], 'parent-a')
            self.assertTrue(audit['subject_confirmed'])
        self.assertNotIn('source_actor_id', child)

    def test_only_accepted_snapshot_is_available_for_teaching_and_no_answers_faked(self):
        self.source()
        self.offer()
        self.enter(self.a, self.lid)
        session = self.a.get(BASE+'/session').json()
        with self.service.store.transaction() as con:
            self.assertIsNone(self.service.confirmed_entry_context(con, session, self.lid))
        data, _ = self.decide()
        self.assertEqual(data['status'], 'confirmed')
        with self.service.store.transaction() as con:
            context = self.service.confirmed_entry_context(con, session, self.lid)
            self.assertEqual(context['goals'], ['做一张故事交换会邀请卡'])
            self.assertEqual(context['source_version'], 7)
            self.assertNotIn('candidate', context)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM learn_starts').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM learn_start_history').fetchone()[0], 0)

    def test_decline_is_saved_without_erasing_history_or_blocking_learning(self):
        self.source()
        self.offer()
        self.enter(self.a, self.lid)
        self.decide()
        data, _ = self.decide('decline', 2)
        self.assertEqual(data['status'], 'declined')
        session = self.a.get(BASE+'/session').json()
        with self.service.store.transaction() as con:
            self.assertIsNone(self.service.confirmed_entry_context(con, session, self.lid))
            self.assertEqual(con.execute("SELECT COUNT(*) FROM learn_course_history WHERE id=?", (data['id'],)).fetchone()[0], 3)
        self.assertEqual(self.a.get(BASE+f'/learners/{self.lid}/start').status_code, 200)

    def test_request_id_replays_and_conflicting_body_is_rejected(self):
        self.source()
        offered, body = self.offer()
        repeated = self.write(self.a, self.url, body).json()
        self.assertEqual(repeated, offered)
        self.write(self.a, self.url, {**body, 'selected_fields': ['goals']}, expected=409)
        self.enter(self.a, self.lid)
        accepted, body = self.decide()
        self.assertEqual(self.write(self.a, self.url+'/confirm', body).json(), accepted)
        self.write(self.a, self.url+'/confirm', {**body, 'decision': 'decline'}, expected=409)
        self.decide(revision=1, expected=409)

    def test_stale_source_and_entry_versions_do_not_overwrite(self):
        self.source()
        self.offer(source_version=6, expected=409)
        self.offer()
        self.offer(expected=409)
        self.source(version=8, goals=[{'text': '新目标', 'basis': 'self_reported'}])
        old = self.a.get(BASE+self.url).json()
        self.assertEqual(old['source_version'], 7)
        self.assertEqual(old['candidate']['source_version'], 8)
        self.offer(source_version=7, expected_revision=1, expected=409)
        newer, _ = self.offer(source_version=8, expected_revision=1)
        self.assertEqual(newer['goals'], ['新目标'])
        self.assertEqual(newer['status'], 'offered')
        self.enter(self.a, self.lid)
        self.decide(revision=1, expected=409)
        self.assertEqual(self.decide(revision=2)[0]['status'], 'confirmed')

    def test_reoffer_after_accept_requires_new_child_confirmation(self):
        self.source()
        self.offer()
        self.enter(self.a, self.lid)
        self.decide()
        self.login(self.a)
        data, _ = self.offer(expected_revision=2)
        self.assertEqual(data['status'], 'offered')
        self.assertIsNone(data['confirmed_at'])
        self.enter(self.a, self.lid)
        session = self.a.get(BASE+'/session').json()
        with self.service.store.transaction() as con:
            self.assertIsNone(self.service.confirmed_entry_context(con, session, self.lid))

    def test_manager_child_staff_and_cross_family_boundaries(self):
        self.source()
        self.offer()
        self.decide(expected=403)
        other, _ = self.create(self.b, 'parent-b')
        self.assertEqual(self.b.get(BASE+self.url).status_code, 404)
        self.write(self.b, self.url, {'request_id': self.rid(), 'expected_revision': 1, 'source_version': 7,
                                    'subject_confirmed': True, 'selected_fields': ['goals']}, expected=404)
        self.enter(self.a, self.lid)
        self.offer(expected=403)
        self.assertEqual(self.a.get(BASE+f'/learners/{other}/entry').status_code, 404)
        self.login(self.reviewer, 'reviewer')
        self.assertEqual(self.reviewer.get(BASE+self.url).status_code, 403)

    def test_missing_consent_and_revoked_relationship_block_snapshots(self):
        self.source()
        self.offer()
        other, _ = self.create(self.b, 'parent-b', consent=False)
        self.assertEqual(self.b.get(BASE+f'/learners/{other}/entry').status_code, 403)
        self.enter(self.a, self.lid)
        self.service.revoke_relationship(self.lid, authority='synthetic-test-only')
        self.assertIn(self.a.get(BASE+self.url).status_code, (401, 403))
        self.login(self.a)
        self.assertEqual(self.a.get(BASE+self.url).status_code, 403)

    def test_body_cannot_spoof_source_subject_or_text(self):
        self.source()
        for extra in ({'user_id': 'parent-b'}, {'goals': ['fake goal']}, {'subject_confirmed': False}, {'selected_fields': ['help_needed']}, {'selected_fields': ['goals', 'goals']}, {'selected_fields': []}):
            self.offer(expected=422, **extra)
        self.enter(self.a, self.lid)
        self.decide(expected=409)

    def test_pausing_keeps_authorized_history_readable_but_blocks_mutation(self):
        self.source()
        self.offer()
        self.enter(self.a, self.lid)
        self.decide()
        paused = self.new_service(replace(self.settings, enabled=False))
        reader = self.client(self.new_app(paused))
        reader.cookies.update(self.a.cookies)
        self.assertEqual(reader.get(BASE+self.url).json()['status'], 'confirmed')
        self.write(reader, self.url+'/confirm', {'request_id': self.rid(), 'expected_revision': 2, 'decision': 'decline'}, expected=423)

    def test_reload_does_not_duplicate_or_rewrite_confirmed_snapshot(self):
        self.source()
        self.offer()
        self.enter(self.a, self.lid)
        accepted, _ = self.decide()
        restarted = self.new_service()
        restarted.migrate()
        reader = self.client(self.new_app(restarted))
        reader.cookies.update(self.a.cookies)
        self.assertEqual(reader.get(BASE+self.url).json(), accepted)
        with restarted.store.transaction() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM learn_course_objects WHERE kind='entry'").fetchone()[0], 1)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM learn_start_history').fetchone()[0], 0)

    def test_studio_rollback_retains_history_without_new_confirmation(self):
        self.source()
        self.offer()
        self.enter(self.a, self.lid)
        self.decide()
        old_ui = self.new_service(replace(self.settings, studio_enabled=False))
        reader = self.client(self.new_app(old_ui))
        reader.cookies.update(self.a.cookies)
        self.assertEqual(reader.get(BASE+self.url).json()['status'], 'confirmed')
        self.write(reader, self.url+'/confirm', {'request_id': self.rid(), 'expected_revision': 2, 'decision': 'decline'}, expected=423)
        self.login(reader)
        self.write(reader, self.url, {'request_id': self.rid(), 'expected_revision': 2, 'source_version': 7,
                                    'subject_confirmed': True, 'selected_fields': ['goals']}, expected=423)


if __name__ == '__main__':
    unittest.main()
