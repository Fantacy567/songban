# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
"""Mixed text-ledger checks use real Studio migrations and synthetic persisted calls."""
import unittest

from app.creative_studio.service import StudioService
from app.learning_workbench.budget import text_used_calls, text_inflight
from tests.test_learning_workbench import WorkbenchFixture


class WorkbenchBudgetTests(WorkbenchFixture, unittest.TestCase):
    def studio_job(self):
        self.platform.companion = self.workbench.guard
        studio = StudioService(self.platform, self.provider, lambda _: {})
        studio.migrate()
        auth = self.a.get('/api/learning/v2/session').json()
        with self.service.store.transaction() as con:
            project = studio.write(con, 'createStudio', auth, {}, {'request_id': self.rid(), 'title': '虚构作品', 'idea': '点击一下出现虚构文字'})
            queued = studio.write(con, 'messageStudio', auth, {'project_id': project['id']},
                {'request_id': self.rid(), 'expected_revision': project['revision'], 'text': '改一行虚构文字'})
        return queued['jobs'][0]['id']

    def synthetic_call(self, jid, state='received'):
        with self.service.store.transaction() as con:
            con.execute('INSERT INTO creative_calls VALUES(?,?,?,?,?)', (self.rid(), jid, state, None, self.service.stamp()))

    def test_studio_calls_and_workbench_reservations_share_cumulative_cap(self):
        self.live()
        self.cfg['max_calls'] = 2
        jid = self.studio_job()
        self.synthetic_call(jid)
        chat = self.send(self.open(), mode='live')
        with self.service.store.transaction() as con:
            self.assertEqual(text_used_calls(con), 2)
        done = self.finish(chat)
        self.cfg['revision'] += 1
        self.send(done, mode='live', expected=429)
        self.assertEqual(len(self.calls), 1)

    def test_studio_reserved_unknown_still_consumes_budget(self):
        self.live()
        self.cfg['max_calls'] = 1
        jid = self.studio_job()
        self.synthetic_call(jid, 'reserved')
        with self.service.store.transaction() as con:
            con.execute("UPDATE creative_jobs SET state='unknown' WHERE id=?", (jid,))
            self.assertEqual(text_used_calls(con), 1)
            self.assertEqual(text_inflight(con), 1)
        self.send(self.open(), mode='live', expected=429)
        self.assertEqual(self.calls, [])

    def test_inflight_studio_blocks_workbench_until_resolved(self):
        self.live()
        jid = self.studio_job()
        with self.service.store.transaction() as con:
            con.execute("UPDATE creative_jobs SET state='running' WHERE id=?", (jid,))
        chat = self.send(self.open(), mode='live')
        self.assertIsNone(self.workbench.worker_once())
        self.assertEqual(self.read_w(chat)['messages'][0]['status'], 'pending')
        with self.service.store.transaction() as con:
            con.execute("UPDATE creative_jobs SET state='unknown' WHERE id=?", (jid,))
        self.assertIsNone(self.workbench.worker_once())
        with self.service.store.transaction() as con:
            con.execute("UPDATE creative_jobs SET state='failed' WHERE id=?", (jid,))
        self.assertEqual(self.finish(chat)['messages'][0]['status'], 'succeeded')
        self.assertEqual(len(self.calls), 1)

    def test_dispatch_rechecks_other_domain_spend_after_enqueue(self):
        self.live()
        self.cfg['max_calls'] = 1
        jid = self.studio_job()
        chat = self.send(self.open(), mode='live')
        # Simulate an older host's Studio reserve racing after the workbench reservation.
        self.synthetic_call(jid)
        final = self.finish(chat)
        self.assertEqual(final['messages'][0]['status'], 'failed')
        self.assertEqual(final['messages'][0]['failure_code'], 'model_budget_exhausted')
        self.assertEqual(self.calls, [])
        with self.service.store.transaction() as con:
            self.assertEqual(text_used_calls(con), 1)

    def test_two_owners_cannot_each_reserve_the_last_call(self):
        self.live()
        self.cfg['max_calls'] = 1
        self.send(self.open(), mode='live')
        self.login(self.b, 'parent-b')
        other = self.open(client=self.b)
        self.post_w('/sessions/' + other['id'] + '/messages', {'expected_revision': other['revision'],
            'content': '另一个人的虚构请求', 'mode': 'live'}, client=self.b, expected=429)
        with self.service.store.transaction() as con:
            self.assertEqual(text_used_calls(con), 1)
        self.assertEqual(self.calls, [])

    def test_revoked_config_during_call_discards_reply_without_refunding(self):
        self.live()
        def disable(payload):
            result = self.runner(payload)
            self.cfg['enabled'] = False
            self.cfg['revision'] += 1
            return result
        self.workbench.runner = disable
        chat = self.finish(self.send(self.open(), mode='live'))
        self.assertEqual(chat['messages'][0]['status'], 'failed')
        self.assertEqual(chat['messages'][0]['failure_code'], 'configuration_changed')
        self.assertIsNone(chat['messages'][0]['assistant_text'])
        with self.service.store.transaction() as con:
            self.assertEqual(text_used_calls(con), 1)

    def test_unknown_remains_unknown_when_config_is_disabled_during_call(self):
        self.live()
        def disable(_):
            self.cfg['enabled'] = False
            self.cfg['revision'] += 1
            raise TimeoutError('synthetic timeout')
        self.workbench.runner = disable
        chat = self.finish(self.send(self.open(), mode='live'))
        self.assertEqual(chat['messages'][0]['status'], 'unknown')
        with self.service.store.transaction() as con:
            self.assertEqual(text_used_calls(con), 1)
            self.assertEqual(text_inflight(con), 1)


if __name__ == '__main__':
    unittest.main()
