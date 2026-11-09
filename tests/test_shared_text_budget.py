"""The coding domain also honors teacher reservations; no network calls."""
import json
import unittest
from app.creative_studio.service import StudioService
from app.learning_v2.protocol import Problem
from tests.test_learning_workbench import WorkbenchFixture


class SharedTextBudgetTests(WorkbenchFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.live()
        self.platform.companion = self.workbench.guard
        self.studio = StudioService(self.platform, self.provider, lambda _: {})
        self.studio.migrate()
        self.auth = self.a.get('/api/learning/v2/session').json()

    def project(self):
        with self.service.store.transaction() as con:
            return self.studio.write(con, 'createStudio', self.auth, {},
                {'request_id': self.rid(), 'title': '虚构网页', 'idea': '点击出现一句问候'})

    def queue(self, project):
        with self.service.store.transaction() as con:
            result = self.studio.write(con, 'messageStudio', self.auth, {'project_id': project['id']},
                {'request_id': self.rid(), 'expected_revision': project['revision'], 'text': '修改问候'})
            return result['jobs'][0]['id']

    def test_teacher_reservation_blocks_coding_enqueue(self):
        self.cfg['max_calls'] = 1
        self.send(self.open(), mode='live')
        with self.assertRaises(Problem) as caught:
            self.queue(self.project())
        self.assertEqual(caught.exception.code, 'studio_budget_exhausted')

    def test_teacher_reservation_blocks_coding_reserve_after_enqueue(self):
        self.cfg['max_calls'] = 1
        job = self.queue(self.project())
        self.send(self.open(), mode='live')
        with self.service.store.transaction() as con:
            con.execute("UPDATE creative_jobs SET state='running',lease_until=? WHERE id=?", (self.service.clock()+60,job))
        with self.assertRaises(Problem) as caught:
            self.studio.reserve_call(job)
        self.assertEqual(caught.exception.code, 'studio_budget_exhausted')
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM creative_calls').fetchone()[0], 0)

    def test_unknown_teacher_holds_shared_concurrency_slot(self):
        job = self.queue(self.project())
        self.send(self.open(), mode='live')
        with self.service.store.transaction() as con:
            con.execute("UPDATE learning_workbench_jobs SET state='unknown'")
        self.assertIsNone(self.studio.worker_once())
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute('SELECT state FROM creative_jobs WHERE id=?', (job,)).fetchone()[0], 'queued')
