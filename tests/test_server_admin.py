"""Offline admin integration: no email transport, provider or real credentials."""
from dataclasses import replace
import json
from pathlib import Path
import unittest

from app.server_admin import AdminSettings, register_server_admin
try:
    from .test_learning_v2_identity import Fixture, BASE, ORIGIN
except ImportError:
    from test_learning_v2_identity import Fixture, BASE, ORIGIN

PREFIX = '/api/server-admin/v1'


class AdminTests(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.admin = register_server_admin(self.app, self.service,
            AdminSettings(allowed_emails=('parent-a@example.test',), secret_dir=Path(self.tmp.name)/'private'))
        self.login(self.a)

    def body(self, **changes):
        return dict(request_id=self.rid(), expected_revision=0, enabled=True, model='deepseek-chat', max_calls=3,
                    max_output_tokens=800, timeout_seconds=90, max_concurrency=1, api_key='fictional-key-not-real', clear_key=False, **changes)

    def put(self, body=None, *, expected=200, client=None, kind='text', headers=None):
        client = client or self.a
        headers = headers if headers is not None else {'Origin':ORIGIN, 'X-CSRF-Token':self.bootstrap(client)['csrf_token']}
        response = client.put(PREFIX+'/providers/'+kind, json=body or self.body(), headers=headers)
        self.assertEqual(response.status_code, expected, response.text)
        return response

    def test_only_bound_allowlisted_account_enters(self):
        response = self.a.get(PREFIX+'/session')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['administrator']['email'], 'parent-a@example.test')
        self.assertFalse(response.json()['providers']['text']['enabled'])
        self.assertIn('no-store', response.headers['cache-control'])
        self.assertEqual(self.b.get(PREFIX+'/session').status_code, 401)
        self.login(self.b, 'parent-b')
        self.assertEqual(self.b.get(PREFIX+'/session', headers={'X-Admin-Email':'parent-a@example.test'}).status_code, 403)

    def test_cookie_identity_wins_and_child_cannot_use_admin_bearer(self):
        self.login(self.b, 'parent-b')
        self.assertEqual(self.b.get(PREFIX+'/session', headers={'Authorization':'Bearer old-parent-a'}).status_code, 403)
        learner, _ = self.create(self.a)
        self.enter(self.a, learner)
        response = self.a.get(PREFIX+'/session', headers={'Authorization':'Bearer old-parent-a'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error']['code'], 'child_mode_restricted')

    def test_child_browser_without_session_cannot_fall_back_to_admin_bearer(self):
        learner, _ = self.create(self.a); self.enter(self.a, learner)
        for cookie in list(self.a.cookies.jar):
            if cookie.name == self.service.cookie_name:
                self.a.cookies.delete(cookie.name, domain=cookie.domain, path=cookie.path)
        self.assertEqual(self.a.get(PREFIX+'/session', headers={'Authorization':'Bearer old-parent-a'}).status_code, 403)

    def test_revocation_checked_on_all_requests(self):
        self.put()
        self.admin.settings = replace(self.admin.settings, allowed_emails=())
        self.assertEqual(self.a.get(PREFIX+'/session').status_code, 403)
        self.assertEqual(self.a.get(PREFIX+'/audit').status_code, 403)
        self.put(expected=403)

    def test_missing_allowlist_and_guest_and_demo_rejected(self):
        self.admin.settings = replace(self.admin.settings, allowed_emails=())
        self.assertEqual(self.a.get(PREFIX+'/session').status_code, 403)
        self.admin.settings = replace(self.admin.settings, allowed_emails=('parent-a@example.test',))
        with self.service.store.transaction() as con:
            con.execute('CREATE TABLE core_guest_people(user_id TEXT PRIMARY KEY)')
            con.execute("INSERT INTO core_guest_people VALUES('parent-a')")
        self.assertEqual(self.a.get(PREFIX+'/session').status_code, 403)
        with self.service.store.transaction() as con:
            con.execute('DELETE FROM core_guest_people')
        self.app.state.demo = True
        self.assertEqual(self.a.get(PREFIX+'/session').status_code, 403)

    def test_csrf_origin_and_transport(self):
        self.put(expected=403, headers={'Origin':ORIGIN})
        csrf = self.bootstrap(self.a)['csrf_token']
        self.put(expected=403, headers={'Origin':'https://evil.example.test','X-CSRF-Token':csrf})
        self.assertEqual(self.a.get(PREFIX+'/session',headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)
        self.assertEqual(self.a.put(PREFIX+'/providers/text',content='{}',headers={'Content-Type':'text/plain'}).status_code,415)

    def test_save_uses_private_key_file_no_key_in_db_response_or_audit(self):
        response = self.put()
        view = response.json()
        self.assertTrue(view['key_configured']); self.assertTrue(view['configuration_ready'])
        self.assertFalse(view['provider_verified']); self.assertNotIn('api_key',view)
        config = self.admin.runtime_config()
        self.assertTrue(config['enabled']); self.assertEqual(config['api_key'],'fictional-key-not-real')
        self.assertEqual(config['max_calls'],3); self.assertEqual(config['max_output_tokens'],800)
        audit = self.a.get(PREFIX+'/audit').json()
        self.assertEqual(len(audit['items']),1)
        self.assertIn('api_key',audit['items'][0]['changed_fields'])
        self.assertNotIn('fictional-key-not-real', json.dumps(audit))
        with self.service.store.transaction() as con:
            for table in ('server_admin_config','server_admin_audit','server_admin_requests'):
                self.assertNotIn('fictional-key-not-real',repr([tuple(r) for r in con.execute('SELECT * FROM '+table)]))
        files = list((Path(self.tmp.name)/'private').glob('*.secret'))
        self.assertEqual(len(files),1)

    def test_compare_and_swap_and_replay(self):
        body = self.body(); first = self.put(body).json()
        self.assertEqual(self.put(body).json()['revision'],first['revision'])
        modified = dict(body, max_calls=9)
        self.put(modified,expected=409)
        self.put(dict(body,request_id=self.rid()),expected=409)
        self.assertEqual(len(self.a.get(PREFIX+'/audit').json()['items']),1)

    def test_rotation_clear_pause_and_missing_key(self):
        self.put()
        body = self.body(); body.update(expected_revision=1,api_key='',enabled=False,clear_key=True)
        self.put(body)
        runtime = self.admin.runtime_config()
        self.assertFalse(runtime['enabled']); self.assertEqual(runtime['api_key'],'')
        body.update(expected_revision=2,request_id=self.rid(),enabled=True,clear_key=False)
        self.put(body,expected=422)

    def test_zero_budget_is_not_runtime_ready(self):
        body = self.body(); body['max_calls']=0
        result=self.put(body).json()
        self.assertFalse(result['configuration_ready']); self.assertFalse(self.admin.runtime_config()['enabled'])

    def test_runtime_uses_existing_transaction_without_nested_lock(self):
        self.put()
        with self.service.store.transaction() as con:
            config = self.admin.runtime_config('text', con=con)
            self.assertEqual(config['max_calls'], 3)
            self.assertEqual(config['revision'], 1)

    def test_image_configuration_is_preparation_not_false_activation(self):
        body=self.body(); body.update(model='fictional-image-endpoint', enabled=False)
        result=self.put(body,kind='image').json()
        self.assertTrue(result['key_configured'])
        self.assertEqual(result['integration_status'],'pending')
        self.assertFalse(self.admin.runtime_config('image')['enabled'])
        body.update(request_id=self.rid(),expected_revision=1,enabled=True,api_key='')
        self.put(body,kind='image',expected=409)

    def test_migration_is_repeatable_and_checksum_protected(self):
        self.admin.migrate()
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM server_admin_config').fetchone()[0],2)
            con.execute("UPDATE server_admin_migrations SET checksum='tampered'")
        with self.assertRaises(ValueError):
            self.admin.migrate()

    def test_request_cannot_inject_endpoint_or_admin_email_and_errors_redact(self):
        self.put(kind='studio-jobs', expected=404)
        for field, value in [('base_url','http://127.0.0.1/internal'),('allowed_emails',['outsider@example.test']),('provider','another')]:
            body = self.body(); body[field]=value
            response=self.put(body,expected=422)
            self.assertNotIn('fictional-key-not-real',response.text)
        body = self.body(); body['max_concurrency']=100
        self.put(body,expected=422)
        for field, value in [('max_output_tokens',4097),('timeout_seconds',121)]:
            body=self.body(); body[field]=value
            self.put(body,expected=422)

    def test_secret_directory_must_not_be_in_served_repository(self):
        self.admin.secrets.directory=Path(__file__).resolve().parents[1]/'static'/'private'
        self.put(expected=503)
        self.assertFalse(self.admin.runtime_config()['enabled'])

    def test_bearer_from_verified_email_supported_with_origin(self):
        client=self.client()
        self.assertEqual(client.get(PREFIX+'/session',headers={'Authorization':'Bearer old-parent-b'}).status_code,403)
        self.assertEqual(client.get(PREFIX+'/session',headers={'Authorization':'Bearer sbconn_fake'}).status_code,401)
        # Password authentication rotated parent-a's old bearer; use a controlled synthetic credential.
        from app.learning_v2.service import digest
        with self.service.store.transaction() as con:
            con.execute("UPDATE people SET token_hash=? WHERE id='parent-a'",(digest('fixture-admin-token'),))
        headers={'Authorization':'Bearer fixture-admin-token','Origin':ORIGIN}
        self.put(client=client,headers=headers)
        self.assertEqual(client.get(PREFIX+'/session',headers=headers).status_code,200)

    def test_shell_contains_no_admin_email_or_config_and_is_framing_protected(self):
        response=self.b.get('/server-admin')
        self.assertEqual(response.status_code,200)
        self.assertNotIn('parent-a@example.test',response.text)
        self.assertIn("frame-ancestors 'none'",response.headers['content-security-policy'])
        self.assertIn('id="workspace" hidden',response.text)


if __name__ == '__main__':
    unittest.main()
