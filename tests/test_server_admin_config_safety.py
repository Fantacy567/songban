# Copyright (c) 2026 2292576833. Joint project ownership: COPYRIGHT.md.
"""Dynamic admin config revocation/rollback and response redaction; synthetic only."""
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from app.server_admin import AdminSettings, register_server_admin
from app.server_admin.routes import ConfigWrite
from tests.test_learning_v2_identity import Fixture, ORIGIN
from tests import test_server_admin as admin_fixture

PREFIX = admin_fixture.PREFIX


class AdminConfigSafetyTests(Fixture, unittest.TestCase):
    body, put = admin_fixture.AdminTests.body, admin_fixture.AdminTests.put

    def setUp(self):
        super().setUp()
        self.admin = register_server_admin(self.app, self.service,
            AdminSettings(allowed_emails=('parent-a@example.test',), secret_dir=Path(self.tmp.name)/'private'))
        self.login(self.a)

    def test_revocation_and_old_request_replay_cannot_restore_key_or_budget(self):
        initial = self.body()
        self.put(initial)
        revoke = dict(self.body(), expected_revision=1, enabled=False, clear_key=True, api_key='', max_calls=0)
        self.put(revoke)
        replay = self.put(initial).json()
        self.assertEqual(replay['revision'], 2)
        self.assertFalse(replay['key_configured'])
        self.assertFalse(replay['configuration_ready'])
        with self.service.store.transaction() as con:
            runtime = self.admin.runtime_config('text', con=con)
            self.assertEqual((runtime['enabled'], runtime['api_key'], runtime['max_calls']), (False, '', 0))
            self.assertEqual(con.execute('SELECT count(*) FROM server_admin_audit').fetchone()[0], 2)

    def test_outer_rollback_restores_committed_config_after_runtime_read(self):
        self.put()
        body = ConfigWrite.model_validate(dict(self.body(), expected_revision=1, api_key='', clear_key=True, enabled=False)).model_dump()
        class Rollback(Exception):
            pass
        with self.assertRaises(Rollback):
            with self.service.store.transaction() as con:
                self.admin.save(con, 'parent-a', 'text', body)
                self.assertFalse(self.admin.runtime_config('text', con=con)['enabled'])
                raise Rollback()
        runtime = self.admin.runtime_config('text')
        self.assertEqual(runtime['revision'], 1)
        self.assertTrue(runtime['enabled'])
        self.assertEqual(runtime['max_calls'], 3)

    def test_lost_secret_disables_runtime_without_exposing_previous_key(self):
        self.put()
        with patch.object(self.admin.secrets, 'read', return_value=''):
            self.assertEqual(self.admin.runtime_config('text')['api_key'], '')
            self.assertFalse(self.admin.runtime_config('text')['enabled'])
            view = self.a.get(PREFIX+'/session')
            self.assertFalse(view.json()['providers']['text']['configuration_ready'])
            self.assertNotIn('fictional-key-not-real', view.text)

    def test_deployment_disable_and_demo_do_not_return_saved_secret(self):
        self.put()
        self.admin.settings = replace(self.admin.settings, enabled=False)
        self.assertFalse(self.admin.runtime_config('text')['enabled'])
        self.assertEqual(self.admin.runtime_config('text')['api_key'], '')
        self.admin.settings = replace(self.admin.settings, enabled=True)
        self.admin.demo = True
        self.assertEqual(self.admin.runtime_config('text')['api_key'], '')

    def test_sensitive_validation_and_storage_errors_do_not_echo_payload(self):
        for change in ({'api_key': 'bad key'}, {'api_key': 'fixture-key', 'clear_key': True}, {'allowed_response_models': ['invalid token']}):
            body = dict(self.body(), **change)
            response = self.put(body, expected=422)
            self.assertNotIn(body['api_key'], response.text)
        with patch.object(self.admin.secrets, 'write', side_effect=OSError('fictional-key-not-real')):
            response = self.put(expected=503)
            self.assertNotIn('fictional-key-not-real', response.text)
        headers = {'Origin': ORIGIN, 'X-CSRF-Token': self.bootstrap(self.a)['csrf_token'], 'Content-Type': 'application/json'}
        response = self.a.put(PREFIX+'/providers/text', content='{"api_key":"fixture-secret","api_key":"fixture-secret"}', headers=headers)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('fixture-secret', response.text)


if __name__ == '__main__':
    unittest.main()
