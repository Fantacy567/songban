"""Controlled launcher tests; no real identities, credentials or provider calls."""
from contextlib import closing, redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('learning_launcher_test', ROOT / 'scripts/run_learning.py')
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def model_config():
    return {'config_version': 'synthetic-v1', 'base_url': 'https://models.example/v1',
            'api_key_env': 'TEST_LEARNING_MODEL_KEY', 'requested_model': 'fixture-model',
            'allowed_models': ['fixture-model'], 'pricing_version': 'synthetic-pricing',
            'input_unit_rate': 1, 'output_unit_rate': 1, 'max_input_tokens': 1000,
            'max_output_tokens': 200, 'reservation_units': 1200,
            'reconciliation_queue': {'reviewer_id': 'not-provisioned-reviewer', 'display_name': '示例核对负责人',
                                     'due_seconds': 3600, 'support_contact_label': '示例支持渠道',
                                     'escalation_actor_id': 'not-provisioned-escalation'}}


class LearningLauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.config = self.directory / 'learning.json'
        self.database = self.directory / 'explicit.sqlite3'
        self.document = {'schema_version': 1, 'settings': {}}
        self.write_config()
        environment = patch.dict(os.environ, dict(os.environ))
        environment.start()
        self.addCleanup(environment.stop)
        network = patch('socket.create_connection', side_effect=AssertionError('No external connections in launcher tests'))
        network.start()
        self.addCleanup(network.stop)

    def write_config(self):
        self.config.write_text(json.dumps(self.document), encoding='utf-8')

    def arguments(self, origin='http://127.0.0.1:8901'):
        return ['--config', str(self.config), '--database', str(self.database), '--origin', origin]

    def test_example_is_paused_and_check_has_no_database_factory_env_or_network_effects(self):
        self.config.write_bytes((ROOT / 'config/learning.example.json').read_bytes())
        output = io.StringIO()
        with patch('sqlite3.connect', side_effect=AssertionError('check must not open DB')), \
             patch.object(launcher, 'create_application', side_effect=AssertionError('check must not import main')), \
             patch.object(launcher, 'bind_local', side_effect=AssertionError('check must not bind')), \
             patch('app.environment.load_env', side_effect=AssertionError('no .env')), redirect_stdout(output):
            self.assertEqual(launcher.main(self.arguments() + ['--check']), 0)
        self.assertFalse(self.database.exists())
        self.assertEqual(json.loads(output.getvalue())['business_readiness'], 'not_verified')
        settings = launcher.load_settings(self.config, 'http://127.0.0.1:8901')
        self.assertFalse(settings.enabled)
        self.assertIsNone(settings.model_settings)

    def test_strict_whitelist_types_and_duplicate_keys(self):
        cases = [ {'enabled': 1}, {'session_seconds': True}, {'age_band_options': 'age'},
                  {'api_key': 'must-not-be-accepted'}, {'allowed_origins': ['https://example.org']},
                  {'relationship_queue': {'reviewer_id': 'x'}},
                  {'studio_enabled': False, 'catalog_enabled': True} ]
        for fields in cases:
            with self.subTest(fields=list(fields)):
                self.document['settings'] = fields
                self.write_config()
                with self.assertRaises(launcher.ConfigurationError):
                    launcher.load_settings(self.config, 'http://127.0.0.1:8901')
        self.config.write_text('{"schema_version":1,"settings":{},"settings":{}}', encoding='utf-8')
        with self.assertRaisesRegex(launcher.ConfigurationError, 'Duplicate'):
            launcher.load_settings(self.config, 'http://127.0.0.1:8901')

    def test_queues_are_typed_without_granting_the_configured_reviewer_permissions(self):
        self.document['settings'] = {'relationship_queue': {'reviewer_id': 'not-provisioned', 'display_name': '负责人', 'due_seconds': 300, 'support_contact_label': '项目支持'}}
        self.write_config()
        settings = launcher.load_settings(self.config, 'http://127.0.0.1:8901')
        self.assertIsInstance(settings.relationship_queue, launcher.ReviewQueue)
        self.assertFalse(self.database.exists())
        self.document['settings']['relationship_queue']['due_seconds'] = True
        self.write_config()
        with self.assertRaises(launcher.ConfigurationError):
            launcher.load_settings(self.config, 'http://127.0.0.1:8901')

    def test_model_key_only_comes_from_explicit_variable_and_never_appears_in_check_output(self):
        secret = 'synthetic-secret-not-a-real-key'
        self.document['settings'] = {'models_enabled': True, 'model_settings': model_config()}
        self.write_config()
        os.environ['TEST_LEARNING_MODEL_KEY'] = secret
        os.environ['DEEPSEEK_API_KEY'] = 'unrelated-credential-must-not-be-selected'
        settings = launcher.load_settings(self.config, 'http://127.0.0.1:8901')
        self.assertEqual(settings.model_settings.api_key, secret)
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error), patch('app.environment.load_env', side_effect=AssertionError('no .env')):
            self.assertEqual(launcher.main(self.arguments() + ['--check']), 0)
        self.assertNotIn(secret, output.getvalue() + error.getvalue() + repr(settings))
        self.assertFalse(self.database.exists())

    def test_model_rejects_inline_key_transport_missing_env_and_private_endpoint(self):
        fields = model_config()
        for change in ({'api_key': 'inline-secret'}, {'transport': 'unsafe'}, {'base_url': 'https://127.0.0.1/v1'},
                       {'base_url': 'http://models.example/v1'}, {'timeout_seconds': True}):
            with self.subTest(change=list(change)):
                self.document['settings'] = {'models_enabled': True, 'model_settings': {**fields, **change}}
                self.write_config()
                with self.assertRaises(launcher.ConfigurationError):
                    launcher.load_settings(self.config, 'http://127.0.0.1:8901', {'TEST_LEARNING_MODEL_KEY': 'synthetic'})
        self.document['settings'] = {'models_enabled': True, 'model_settings': fields}
        self.write_config()
        with self.assertRaises(launcher.ConfigurationError):
            launcher.load_settings(self.config, 'http://127.0.0.1:8901', {'DEEPSEEK_API_KEY': 'unrelated'})

    def test_public_origin_is_check_only_and_is_not_readiness_approval(self):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(launcher.main(self.arguments('https://learning.example') + ['--check']), 0)
        self.assertEqual(json.loads(output.getvalue())['public_deployment'], 'requires_separate_review')
        with patch.object(launcher, 'backup_before_start', side_effect=AssertionError('no database work')), redirect_stderr(error):
            self.assertEqual(launcher.main(self.arguments('https://learning.example')), 2)
        self.assertFalse(self.database.exists())

    def test_occupied_port_fails_before_database_backup_or_factory(self):
        with closing(socket.socket()) as busy:
            busy.bind(('127.0.0.1', 0)); busy.listen(1)
            origin = 'http://127.0.0.1:' + str(busy.getsockname()[1])
            with patch.object(launcher, 'backup_before_start', side_effect=AssertionError('backup must not run')), \
                 patch.object(launcher, 'create_application', side_effect=AssertionError('factory must not run')), redirect_stderr(io.StringIO()):
                self.assertEqual(launcher.main(self.arguments(origin)), 2)
        self.assertFalse(self.database.exists())

    def test_existing_database_backup_includes_committed_wal_and_preserves_original(self):
        with closing(sqlite3.connect(self.database)) as source:
            source.execute('PRAGMA journal_mode=WAL')
            source.execute('CREATE TABLE synthetic(id INTEGER PRIMARY KEY, text TEXT)')
            source.execute("INSERT INTO synthetic VALUES(1,'committed')"); source.commit()
            source.execute("INSERT INTO synthetic VALUES(2,'not-committed')")
            result = launcher.backup_before_start(self.database, self.directory)
            source.rollback()
            with closing(sqlite3.connect(result['destination'])) as backup:
                self.assertEqual(backup.execute('SELECT * FROM synthetic').fetchall(), [(1, 'committed')])
            self.assertEqual(source.execute('SELECT * FROM synthetic').fetchall(), [(1, 'committed')])
            self.assertEqual(result['integrity'], 'ok')

    def test_existing_database_needs_external_backup_and_snapshot_failure_stops_factory(self):
        with closing(sqlite3.connect(self.database)) as source:
            source.execute('CREATE TABLE synthetic(id INTEGER)')
        for directory in (None, ROOT / 'data', Path('relative')):
            with self.subTest(directory=str(directory)), self.assertRaises(launcher.ConfigurationError):
                launcher.backup_before_start(self.database, directory)
        # The complete execution path cannot skip failed backup and import main.
        with closing(socket.socket()) as candidate:
            candidate.bind(('127.0.0.1', 0)); port = candidate.getsockname()[1]
        with patch.object(launcher, 'snapshot', side_effect=ValueError('synthetic failure')), \
             patch.object(launcher, 'create_application', side_effect=AssertionError('factory must not run')), redirect_stderr(io.StringIO()):
            self.assertEqual(launcher.main(self.arguments(f'http://127.0.0.1:{port}') + ['--backup-directory', str(self.directory)]), 2)

    def test_new_database_uses_real_factory_without_seeding_or_implicit_env(self):
        settings = launcher.load_settings(self.config, 'http://127.0.0.1:8901')
        os.environ['DATABASE_PATH'] = str(self.directory / 'wrong-default.sqlite3')
        os.environ['DEEPSEEK_API_KEY'] = 'must-not-be-used'
        with patch('app.environment.load_env', side_effect=AssertionError('must not read .env')):
            app = launcher.create_application(self.database, settings)
        self.assertNotIn('DEEPSEEK_API_KEY', os.environ)
        self.assertFalse((self.directory / 'wrong-default.sqlite3').exists())
        with app.state.learning_v2.store.transaction() as con:
            for table in ('people', 'learn_learners', 'learn_consents', 'learn_grants', 'learn_course_objects', 'learn_course_grants', 'learn_model_accounts', 'learn_model_jobs'):
                self.assertEqual(con.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0, table)
        with closing(TestClient(app, base_url='http://127.0.0.1:8901')) as client:
            self.assertEqual(client.get('/learning-prep').status_code, 200)
            response = client.get('/api/learning/v2/config').json()
            self.assertFalse(response['learning_enabled'])
            self.assertFalse(response['live_enabled'])

    def test_execution_passes_reserved_socket_to_server_and_closes_it(self):
        with closing(socket.socket()) as candidate:
            candidate.bind(('127.0.0.1', 0)); port = candidate.getsockname()[1]
        observed = []
        application = object()
        def server(app, listener):
            self.assertIs(app, application)
            self.assertEqual(listener.getsockname()[1], port)
            observed.append(listener)
            with closing(socket.socket()) as contender, self.assertRaises(OSError):
                contender.bind(('127.0.0.1', port))
        with patch.object(launcher, 'create_application', return_value=application), patch.object(launcher, 'serve', side_effect=server), redirect_stdout(io.StringIO()):
            self.assertEqual(launcher.main(self.arguments(f'http://127.0.0.1:{port}')), 0)
        self.assertEqual(observed[0].fileno(), -1)


if __name__ == '__main__':
    unittest.main()
