"""One synthetic demo origin, preserved data and the real learning boundary."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from scripts.run_demo import build_demo
from scripts.serve_learning_preview import build_preview, _settings
from scripts.unify_demo import assemble


class UnifiedDemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        guard = patch.dict(os.environ, dict(os.environ)); guard.start(); self.addCleanup(guard.stop)
        private = patch('app.environment.load_env'); private.start(); self.addCleanup(private.stop)
        network = patch('socket.create_connection', side_effect=AssertionError('No external calls in unified demo tests'))
        network.start(); self.addCleanup(network.stop)
        os.environ['DATABASE_PATH'] = str(self.folder/'import.sqlite3')
        original = self.folder/'old-demo.sqlite3'
        api = build_demo(original)
        with closing(TestClient(api)) as client:
            code = client.get('/demo/bootstrap.js').text
        self.bootstrap = json.loads(code.split('=', 1)[1].split(';\n', 1)[0])
        self.receipt = self.folder/'original-resume.json'
        self.receipt.write_text(json.dumps({'db': str(original), 'bootstrap': self.bootstrap}), encoding='utf-8')
        self.learning = self.folder/'learning'
        self.source_api, self.meta = build_preview(self.learning, 8901)
        self.target = self.folder/'unified'

    def build(self):
        report = assemble(self.receipt, self.learning, self.target, 8901)
        receipt = json.loads((self.target/'resume.json').read_text(encoding='utf-8'))
        api = build_demo(report['database'], resume=receipt['bootstrap'],
                         learning_settings=_settings(report['origin']), learning_demo=receipt['learning'])
        return api, report

    def test_clone_preserves_all_learning_rows_and_hackathon_people_without_changing_sources(self):
        old = self.folder/'old-demo.sqlite3'
        source = Path(self.meta['database'])
        before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (old, source)]
        _, report = self.build()
        self.assertEqual(before, [hashlib.sha256(p.read_bytes()).hexdigest() for p in (old, source)])
        with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(report['database'])) as dst:
            self.assertEqual(dst.execute('SELECT COUNT(*) FROM people').fetchone()[0], 8)
            for table, count in report['imported_rows'].items():
                if table == 'people' or table.startswith('learn_legacy_'):
                    continue
                self.assertEqual(src.execute('SELECT * FROM "'+table+'" ORDER BY rowid').fetchall(), dst.execute('SELECT * FROM "'+table+'" ORDER BY rowid').fetchall(), table)
            self.assertEqual(dst.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(dst.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_one_app_serves_both_frontends_and_demo_assistance_never_reaches_normal_app(self):
        api, _ = self.build()
        with closing(TestClient(api, base_url='http://127.0.0.1:8901')) as client:
            root = client.get('/').text
            self.assertIn('songban-learning-navigation', root)
            self.assertIn('/demo/bootstrap.js', root)
            learning = client.get('/learning-prep').text
            self.assertIn('songban-learning-demo-entry', learning)
            self.assertNotIn('SongbanLearningDemo=', learning)
            for private in ('manager_account', 'staff_account', self.meta['password']):
                self.assertNotIn(private, learning)
            self.assertIn('learning-demo-guide.js', learning)
            config = client.get('/api/learning/v2/config').json()
            self.assertTrue(config['studio_enabled']); self.assertFalse(config['live_enabled'])
            token = self.bootstrap['users'][0]['token']
            self.assertEqual(client.get('/api/core/me', headers={'Authorization': 'Bearer '+token}).status_code, 200)

    def demo_start(self, client, origin='http://127.0.0.1:8901', **overrides):
        boot = client.get('/api/learning/v2/session-bootstrap').json()
        return client.post('/api/demo/learning/start', json={
            'request_id': os.urandom(12).hex(), 'browser_revision': boot['browser_revision'], **overrides},
            headers={'Origin': origin, 'X-CSRF-Token': boot['csrf_token']})

    def test_explicit_demo_start_issues_only_child_session_and_preserves_learning_records(self):
        api, report = self.build()
        with closing(sqlite3.connect(report['database'])) as con:
            before = {table: con.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall()
                      for table in ('learn_learners', 'learn_links', 'learn_consents', 'learn_course_grants', 'learn_course_objects', 'learn_starts')}
            managers_before = con.execute("SELECT COUNT(*) FROM learn_sessions WHERE mode='manager'").fetchone()[0]
        with closing(TestClient(api, base_url='http://127.0.0.1:8901')) as client:
            response = self.demo_start(client)
            self.assertEqual(response.status_code, 200, response.text)
            current = response.json()
            self.assertEqual(current['mode'], 'learner')
            self.assertEqual(current['learner_id'], self.meta['learner_id'])
            self.assertEqual(current['scopes'], ['learning'])
            self.assertNotIn('password', response.text)
            self.assertEqual(client.get('/api/learning/v2/session').json(), current)
            self.assertEqual(client.get('/api/learning/v2/learners/'+current['learner_id']+'/home').status_code, 200)
            self.assertEqual(client.get('/api/learning/v2/families').status_code, 403)
            self.assertEqual(self.demo_start(client).json()['id'], current['id'])
            token = self.bootstrap['users'][0]['token']
            self.assertEqual(client.get('/api/core/me', headers={'Authorization': 'Bearer '+token}).status_code, 403)
            cookie = response.headers['set-cookie']
            self.assertIn('HttpOnly', cookie); self.assertIn('SameSite=strict', cookie)
        with closing(sqlite3.connect(report['database'])) as con:
            for table, rows in before.items():
                self.assertEqual(con.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall(), rows, table)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM learn_sessions WHERE mode='manager'").fetchone()[0], managers_before)

    def test_demo_start_requires_same_origin_csrf_and_current_browser_revision(self):
        api, _ = self.build()
        with closing(TestClient(api, base_url='http://127.0.0.1:8901')) as client:
            boot = client.get('/api/learning/v2/session-bootstrap').json()
            body = {'request_id': 'fictional-entry', 'browser_revision': boot['browser_revision']}
            self.assertEqual(client.post('/api/demo/learning/start', json=body).status_code, 403)
            self.assertEqual(self.demo_start(client, origin='https://outside.invalid').status_code, 403)
            self.assertEqual(self.demo_start(client, browser_revision=999).status_code, 409)
            self.assertEqual(self.demo_start(client, learner_id='another-child').status_code, 422)
            self.assertEqual(client.get('/api/learning/v2/session').status_code, 401)

    def test_revoked_consent_is_not_recreated_by_demo_entry(self):
        api, report = self.build()
        with closing(sqlite3.connect(report['database'])) as con:
            con.execute("UPDATE learn_consents SET status='revoked'"); con.commit()
        with closing(TestClient(api, base_url='http://127.0.0.1:8901')) as client:
            response = self.demo_start(client)
            self.assertEqual(response.status_code, 403, response.text)
            self.assertEqual(response.json()['error']['code'], 'consent_required')
        with closing(sqlite3.connect(report['database'])) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM learn_consents WHERE status='active'").fetchone()[0], 0)

    def test_demo_start_is_absent_from_normal_learning_app(self):
        with closing(TestClient(self.source_api, base_url='http://127.0.0.1:8901')) as client:
            self.assertEqual(client.post('/api/demo/learning/start', json={}).status_code, 404)

    def test_demo_start_cannot_replace_another_parent_or_staff_identity(self):
        api, _ = self.build(); origin = 'http://127.0.0.1:8901'
        for account in (self.meta['other_account'], self.meta['staff_account']):
            with self.subTest(account=account), closing(TestClient(api, base_url=origin)) as client:
                boot = client.get('/api/learning/v2/session-bootstrap').json()
                response = client.post('/api/learning/v2/sessions/authenticate', json={
                    'request_id': os.urandom(12).hex(), 'browser_revision': boot['browser_revision'],
                    'method': 'password', 'account': account, 'proof': self.meta['password']},
                    headers={'Origin': origin, 'X-CSRF-Token': boot['csrf_token']})
                self.assertEqual(response.status_code, 200)
                before = client.get('/api/learning/v2/session').json()
                denied = self.demo_start(client)
                self.assertEqual(denied.status_code, 409, denied.text)
                self.assertEqual(denied.json()['error']['code'], 'different_identity')
                self.assertEqual(client.get('/api/learning/v2/session').json(), before)

    def test_demo_entry_rechecks_fixture_at_request_time(self):
        api, report = self.build()
        with closing(sqlite3.connect(report['database'])) as con:
            con.execute("INSERT INTO people(id,phone,name,token_hash,created_at,phone_real) VALUES('unexpected','unexpected','fixture intrusion','unused','now',1)")
            con.commit()
        with closing(TestClient(api, base_url='http://127.0.0.1:8901')) as client:
            denied = self.demo_start(client)
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(denied.json()['error']['code'], 'demo_fixture_required')
            self.assertEqual(client.get('/api/learning/v2/session').status_code, 401)

    def test_demo_entry_does_not_ignore_real_pending_legacy_activity(self):
        api, report = self.build()
        with closing(sqlite3.connect(report['database'])) as con:
            con.execute("INSERT INTO learn_legacy_activity VALUES('entry-test-pending',NULL,NULL,'POST','/api/unknown','active','now',NULL,NULL)")
            con.commit()
        with closing(TestClient(api, base_url='http://127.0.0.1:8901')) as client:
            denied = self.demo_start(client)
            self.assertEqual(denied.status_code, 409)
            self.assertEqual(denied.json()['error']['code'], 'legacy_work_in_progress')

    def test_stale_browser_cannot_replay_start_after_logout(self):
        api, _ = self.build(); origin = 'http://127.0.0.1:8901'
        with closing(TestClient(api, base_url=origin)) as client:
            current = self.demo_start(client).json()
            stale = client.get('/api/learning/v2/session-bootstrap').json()
            response = client.post('/api/learning/v2/sessions/logout', json={
                'request_id': os.urandom(12).hex(), 'expected_revision': current['revision']},
                headers={'Origin': origin, 'X-CSRF-Token': stale['csrf_token']})
            self.assertEqual(response.status_code, 200)
            denied = client.post('/api/demo/learning/start', json={
                'request_id': 'stale-entry-replay', 'browser_revision': stale['browser_revision']},
                headers={'Origin': origin, 'X-CSRF-Token': stale['csrf_token']})
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(client.get('/api/learning/v2/session').status_code, 401)

    def test_learning_child_cannot_use_demo_bearer_to_escape_legacy_boundary(self):
        api, _ = self.build(); origin = 'http://127.0.0.1:8901'
        with closing(TestClient(api, base_url=origin)) as client:
            def post(path, body):
                bootstrap = client.get('/api/learning/v2/session-bootstrap').json()
                return client.post('/api/learning/v2'+path, json={'request_id': os.urandom(12).hex(), **body}, headers={'Origin': origin, 'X-CSRF-Token': bootstrap['csrf_token']})
            boot = client.get('/api/learning/v2/session-bootstrap').json()
            self.assertEqual(post('/sessions/authenticate', {'method': 'password', 'account': self.meta['manager_account'], 'proof': self.meta['password'], 'browser_revision': boot['browser_revision']}).status_code, 200)
            session = client.get('/api/learning/v2/session').json()
            self.assertEqual(post('/sessions/enter-learner', {'expected_revision': session['revision'], 'learner_id': self.meta['learner_id']}).status_code, 200)
            token = self.bootstrap['users'][0]['token']
            denied = client.get('/api/core/me', headers={'Authorization': 'Bearer '+token})
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(denied.json()['error']['code'], 'child_mode_restricted')

    def test_unknown_real_identity_is_rejected_before_target_is_created(self):
        with closing(sqlite3.connect(self.folder/'old-demo.sqlite3')) as con:
            con.execute("INSERT INTO people(id,phone,name,token_hash,created_at,phone_real) VALUES('real','real','not synthetic','unexpected','now',1)")
            con.commit()
        with self.assertRaisesRegex(ValueError, 'synthetic'):
            self.build()
        self.assertFalse(self.target.exists())

    def test_missing_learning_marker_does_not_create_a_source_directory(self):
        missing = self.folder/'missing'
        with self.assertRaisesRegex(ValueError, 'marked'):
            assemble(self.receipt, missing, self.target)
        self.assertFalse(missing.exists()); self.assertFalse(self.target.exists())

    def test_existing_destination_cannot_be_overwritten(self):
        self.build()
        with self.assertRaisesRegex(ValueError, 'NEW'):
            self.build()

    def test_fresh_cli_process_resumes_canonical_learning_database_with_explicit_settings(self):
        self.build()
        # A fresh interpreter is essential: importing app.main in setUp would
        # otherwise hide the module-level default-app initialization regression.
        program = r'''
import json, os, runpy, site, sys
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
site.addsitedir(sys.argv[3])
sys.path.insert(0, sys.argv[1])
receipt = Path(sys.argv[2])
data = json.loads(receipt.read_text(encoding='utf-8'))
os.environ['DATABASE_PATH'] = data['db']
def verify(app, **options):
    from fastapi.testclient import TestClient
    platform = app.state.platform_v1
    assert platform.settings.enabled and platform.settings.demo_mode
    assert platform.settings.image_settings.sample_enabled
    assert not platform.settings.image_settings.live_enabled
    assert platform.settings.image_settings.image_limit == 0
    assert not platform.companion.settings.enabled
    with closing(TestClient(app, base_url='http://127.0.0.1:8901')) as client:
        assert 'name="songban-platform"' in client.get('/').text
        assert client.get('/api/learning/v2/config').status_code == 200
        token = data['bootstrap']['users'][0]['token']
        assert client.get('/api/core/me', headers={'Authorization': 'Bearer '+token}).status_code == 200
    print('fresh canonical CLI settings passed')
sys.argv = ['scripts/run_demo.py', '--resume', str(receipt), '--port', '8901', '--app-url', 'http://127.0.0.1:8894', '--real-connector']
with patch('app.environment.load_env'), patch('socket.create_connection', side_effect=AssertionError('No network in CLI verification')), patch('uvicorn.run', side_effect=verify):
    runpy.run_module('scripts.run_demo', run_name='__main__')
'''
        result = subprocess.run([sys._base_executable, '-c', program, str(Path(__file__).resolve().parents[1]),
                                 str(self.target / 'resume.json'), sysconfig.get_paths()['purelib']],
                                capture_output=True, text=True, encoding='utf-8', timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('fresh canonical CLI settings passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
