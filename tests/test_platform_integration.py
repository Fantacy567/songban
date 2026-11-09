"""H0/H1 integration safeguards, using new synthetic databases only.

No listener, existing demo database, private configuration or provider is used.
These tests supplement test_unified_demo rather than counting as platform UI QA.
"""
from contextlib import closing
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from scripts.learning_backup import snapshot
from scripts.run_demo import build_demo
from scripts.run_learning import create_application
from scripts.serve_learning_preview import build_preview, _settings
from scripts.unify_demo import assemble
try:
    from .test_learning_v2_course import CourseFixture
except ImportError:
    from test_learning_v2_course import CourseFixture
from app.platform_v1 import PlatformService, PlatformSettings, register_platform
from app.platform_v1.companion import CompanionSettings


class PlatformIntegrationSafeguards(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        environment = patch.dict(os.environ, dict(os.environ))
        environment.start(); self.addCleanup(environment.stop)
        private = patch('app.environment.load_env')
        private.start(); self.addCleanup(private.stop)
        network = patch('socket.create_connection', side_effect=AssertionError('No network in platform safeguards'))
        network.start(); self.addCleanup(network.stop)
        os.environ['DATABASE_PATH'] = str(self.folder / 'import.sqlite3')
        self.source = self.folder / 'source-demo.sqlite3'
        app = build_demo(self.source)
        with closing(TestClient(app)) as client:
            bootstrap = client.get('/demo/bootstrap.js').text
        self.bootstrap = json.loads(bootstrap.split('=', 1)[1].split(';\n', 1)[0])
        self.receipt = self.folder / 'source-resume.json'
        self.receipt.write_text(json.dumps({'db': str(self.source), 'bootstrap': self.bootstrap}), encoding='utf-8')
        self.learning = self.folder / 'learning'
        _, self.metadata = build_preview(self.learning, 8901)
        self.target = self.folder / 'unified'

    def assemble(self, **kwargs):
        return assemble(self.receipt, self.learning, self.target, **kwargs)

    def test_navigation_rollback_disables_demo_navigation_opt_in(self):
        report = self.assemble()
        receipt = json.loads((self.target / 'resume.json').read_text(encoding='utf-8'))
        settings = replace(_settings(report['origin']), navigation_enabled=False)
        app = build_demo(report['database'], resume=receipt['bootstrap'],
                         learning_settings=settings, learning_demo=receipt['learning'])
        with closing(TestClient(app, base_url=report['origin'])) as client:
            root = client.get('/').text
            self.assertNotIn('name="songban-learning-navigation"', root,
                             'The demo must honor the navigation rollback flag')
            self.assertNotIn('data-stage-nav', client.get('/learning-prep').text)

    def test_snapshot_identity_change_is_rejected_before_receipt_is_published(self):
        def concurrent_change(source, destination):
            # Deliberately mutate only this test's temporary source between its
            # initial identity check and the online backup, as a concurrent writer.
            with closing(sqlite3.connect(source)) as con:
                con.execute("INSERT INTO people(id,phone,name,token_hash,created_at,phone_real) "
                            "VALUES('unexpected-after-check','synthetic-race','synthetic race actor','test-only','now',1)")
                con.commit()
            return snapshot(source, destination)

        with patch('scripts.unify_demo.snapshot', side_effect=concurrent_change):
            with self.assertRaisesRegex(ValueError, 'synthetic|identit|actor'):
                self.assemble()
        self.assertFalse((self.target / 'resume.json').exists(),
                         'A failed synthetic identity check must not publish a usable receipt')

    def test_online_clone_preserves_committed_wal_and_does_not_checkpoint_source(self):
        with closing(sqlite3.connect(self.source)) as writer:
            self.assertEqual(writer.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
            writer.execute('PRAGMA wal_autocheckpoint=0')
            writer.execute('UPDATE people SET profile=? WHERE id=?',
                           ('synthetic committed WAL update', self.bootstrap['users'][0]['id']))
            writer.commit()
            wal = Path(str(self.source) + '-wal')
            self.assertTrue(wal.is_file())
            files = (self.source, wal, Path(self.metadata['database']))
            before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in files]
            report = self.assemble()
            self.assertEqual(before, [hashlib.sha256(path.read_bytes()).hexdigest() for path in files])
            with closing(sqlite3.connect(report['database'])) as clone:
                actual = clone.execute('SELECT profile FROM people WHERE id=?',
                                       (self.bootstrap['users'][0]['id'],)).fetchone()[0]
                self.assertEqual(actual, 'synthetic committed WAL update')

    def test_migration_mismatch_publishes_no_receipt_and_keeps_sources_unchanged(self):
        source_learning = Path(self.metadata['database'])
        with closing(sqlite3.connect(source_learning)) as con:
            con.execute("UPDATE learn_migrations SET checksum='synthetic-mismatch' "
                        'WHERE version=(SELECT MIN(version) FROM learn_migrations)')
            con.commit()
        paths = (self.source, source_learning)
        before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
        with self.assertRaisesRegex(ValueError, 'migration'):
            self.assemble()
        self.assertEqual(before, [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths])
        self.assertFalse((self.target / 'resume.json').exists())
        self.assertTrue((self.target / 'demo.sqlite3').exists(),
                        'The failed clone remains available for diagnosis; sources are not replaced')

    def test_invalid_ports_do_not_create_a_target(self):
        for port in (0, 80, 1023, 65536):
            with self.subTest(port=port), self.assertRaisesRegex(ValueError, 'port'):
                self.assemble(port=port)
        self.assertFalse(self.target.exists())

    def test_unified_receipt_cannot_be_imported_again(self):
        self.assemble()
        second = self.folder / 'second-output'
        with self.assertRaisesRegex(ValueError, 'already unified'):
            assemble(self.target / 'resume.json', self.learning, second)
        self.assertFalse(second.exists())

    def test_normal_application_has_no_demo_bootstrap_or_prefilled_credentials(self):
        app = create_application(self.folder / 'normal.sqlite3', _settings('http://127.0.0.1:8901'))
        with closing(TestClient(app, base_url='http://127.0.0.1:8901')) as client:
            root = client.get('/').text
            learning = client.get('/learning-prep').text
            self.assertNotIn('/demo/bootstrap.js', root)
            self.assertNotIn('SongbanLearningDemo=', learning)
            self.assertNotIn('learning-demo-guide.js', learning)
            self.assertEqual(client.get('/demo/bootstrap.js').status_code, 404)

    def test_blob_images_allowed_only_for_platform_documents_and_binary_keeps_sandbox(self):
        from app.main import create_app
        settings = _settings('http://127.0.0.1:8901')
        application = create_app(self.folder / 'platform-headers.sqlite3', core_only=True, enforce_journey=False,
                                 learning_settings=settings, platform_settings=PlatformSettings(enabled=True, navigation_enabled=True))
        with closing(TestClient(application, base_url='http://127.0.0.1:8901')) as client:
            for route in ('/', '/learning-prep'):
                csp = client.get(route).headers['content-security-policy']
                directives = {part.strip().split(' ', 1)[0]: part.strip() for part in csp.split(';')}
                self.assertIn('blob:', directives['img-src'])
                self.assertNotIn('blob:', directives['script-src'])
                self.assertNotIn('blob:', directives['frame-ancestors'])
            self.assertNotIn('blob:', client.get('/api/platform/v1/config').headers['content-security-policy'])
            private = client.get('/api/platform/v1/assets/unknown-safe-id/content')
            self.assertEqual(private.headers['cache-control'], 'private, no-store')
            self.assertEqual(private.headers['content-security-policy'], "default-src 'none'; sandbox")
            self.assertEqual(private.headers['cross-origin-resource-policy'], 'same-origin')
        normal = create_application(self.folder / 'normal-headers.sqlite3', settings)
        with closing(TestClient(normal, base_url='http://127.0.0.1:8901')) as client:
            self.assertNotIn('blob:', client.get('/').headers['content-security-policy'])


class PlatformSharedBoundaryTests(CourseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        def fixture(payload):
            self.calls.append(payload)
            return {'text': 'private live fixture reply', 'actual_model': 'fixture-only'}
        live = CompanionSettings(enabled=True, config_version='shared-boundary-fixture', model_id='fixture-only', runner=fixture, max_calls=3)
        self.platform = PlatformService(self.service, PlatformSettings(enabled=True, companion_settings=live))
        register_platform(self.app, self.platform)
        with self.service.store.transaction() as con:
            con.execute("UPDATE learn_consents SET scopes='[\"learning\",\"live_model\"]' WHERE learner_id=?", (self.lid,))

    def platform_post(self, path, body, expected=200, extra_headers=None):
        response = self.a.post('/api/platform/v1' + path, json=body,
                               headers={'Origin': 'https://learning.example.test', 'X-CSRF-Token': self.bootstrap(self.a)['csrf_token'], **(extra_headers or {})})
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    def test_cached_open_projects_live_history_again_after_scope_withdrawal(self):
        context = {'domain': 'hall', 'resource_id': 'ai'}
        opened = self.platform_post('/companion/sessions', {'request_id': self.rid(), 'context': context})
        self.platform_post('/companion/sessions/' + opened['id'] + '/messages', {'request_id': self.rid(), 'expected_revision': 1, 'question': '虚构提问', 'mode': 'live'})
        self.platform.companion.worker_once()
        saved_request = {'request_id': self.rid(), 'context': context}
        receipt = self.platform_post('/companion/sessions', saved_request)
        self.assertEqual(receipt['messages'][0]['text'], 'private live fixture reply')
        with self.service.store.transaction() as con:
            con.execute("UPDATE learn_consents SET scopes='[\"learning\"]' WHERE learner_id=?", (self.lid,))
        replay = self.platform_post('/companion/sessions', saved_request)
        self.assertEqual(replay['messages'][0]['visibility'], 'restricted')
        self.assertIsNone(replay['messages'][0]['text'])
        self.assertEqual(replay['messages'][0]['actions'], [])
        self.assertEqual(len(self.calls), 1)

    def test_cached_pending_send_reads_current_result_without_new_dispatch(self):
        opened = self.platform_post('/companion/sessions', {'request_id': self.rid(), 'context': {'domain': 'hall'}})
        path = '/companion/sessions/' + opened['id'] + '/messages'
        body = {'request_id': self.rid(), 'expected_revision': 1, 'question': '虚构提问', 'mode': 'live'}
        pending = self.platform_post(path, body)
        self.assertEqual(pending['status'], 'pending')
        self.platform.companion.worker_once()
        replay = self.platform_post(path, body)
        self.assertEqual(replay['id'], pending['id'])
        self.assertEqual(replay['status'], 'succeeded')
        self.assertEqual(len(self.calls), 1)

    def test_cookie_learner_remains_authoritative_over_other_bearer(self):
        opened = self.platform_post('/companion/sessions', {'request_id': self.rid(), 'context': {'domain': 'hall'}}, extra_headers={'Authorization': 'Bearer old-outsider'})
        self.assertEqual(opened['context']['learner_id'], self.lid)
        self.platform_post('/companion/sessions', {'request_id': self.rid(), 'context': {'domain': 'hall', 'learner_id': 'forged-other-child'}}, 404, {'Authorization': 'Bearer old-outsider'})


if __name__ == '__main__':
    unittest.main()
