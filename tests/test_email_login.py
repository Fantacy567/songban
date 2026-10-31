"""QQ delivery is mocked: no real messages are sent by the test suite."""
import os
import smtplib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.email_delivery import deliver_email_code, email_status, normalize_email
from app.environment import load_env
from app.main import create_app, digest, now
from app.studio import hash_password


class EmailDeliveryTests(unittest.TestCase):
    def test_address_validation_and_normalization(self):
        self.assertEqual(normalize_email(' Team+demo@Example.COM '), 'team+demo@example.com')
        for value in [None, {}, 'x', 'a@localhost', 'a..b@example.com', 'a@-example.com', 'a@example..com',
                      'a@example.com\r\nBcc:evil@example.com', 'a@b.com@c.com', 'a' * 65 + '@example.com']:
            self.assertIsNone(normalize_email(value), repr(value))

    @patch.dict(os.environ, {'QQ_SMTP_EMAIL': 'sender@qq.com', 'QQ_SMTP_AUTH_CODE': 'private-test-secret'})
    def test_qq_tls_message_and_no_configuration_leak(self):
        with patch('app.email_delivery.smtplib.SMTP_SSL') as connection:
            smtp = connection.return_value.__enter__.return_value
            smtp.send_message.return_value = {}
            deliver_email_code('member@example.com', '123456')
            self.assertEqual(connection.call_args.args, ('smtp.qq.com', 465))
            self.assertTrue(connection.call_args.kwargs['context'].check_hostname)
            smtp.login.assert_called_once_with('sender@qq.com', 'private-test-secret')
            message = smtp.send_message.call_args.args[0]
            self.assertEqual(message['To'], 'member@example.com')
            self.assertIn('123456', message.get_content())
            self.assertNotIn('private-test-secret', str(message))
        self.assertEqual(email_status(), {'ready': True, 'provider': 'QQ邮箱', 'registration_available': True})

    @patch.dict(os.environ, {'QQ_SMTP_EMAIL': 'sender@qq.com', 'QQ_SMTP_AUTH_CODE': 'private-test-secret'})
    def test_smtp_failure_is_redacted(self):
        with patch('app.email_delivery.smtplib.SMTP_SSL', side_effect=smtplib.SMTPAuthenticationError(535, b'private-test-secret')):
            with self.assertRaises(RuntimeError) as caught:
                deliver_email_code('member@example.com', '123456')
        self.assertNotIn('private-test-secret', str(caught.exception))

    def test_private_env_loads_email_keys(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            config = Path(tmp) / 'mail.env'
            config.write_text('QQ_SMTP_EMAIL=sender@qq.com\nQQ_SMTP_AUTH_CODE="private-test-secret"\n', encoding='utf-8')
            load_env(config)
            self.assertTrue(email_status()['ready'])


class EmailLoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'auth.sqlite3'
        self.client = TestClient(create_app(self.db, core_only=True))
        self.codes = {}
        status = patch('app.email_login.email_status', return_value={'ready': True, 'registration_available': True})
        self.status = status.start()
        self.addCleanup(status.stop)
        delivery = patch('app.email_login.deliver_email_code', side_effect=lambda email, code, purpose: self.codes.update({(email, purpose): code}))
        self.delivery = delivery.start()
        self.addCleanup(delivery.stop)
        with closing(sqlite3.connect(self.db)) as con:
            con.execute('INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at,password_hash) VALUES(?,?,?,?,?,?,?,?)',
                        ('member', '18800000001', '同伴', '创作', '设计', digest('initial-token'), now(), hash_password('test-password')))
            con.commit()
        self.headers = {'Authorization': 'Bearer initial-token'}

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def sql(self, statement, args=()):
        with closing(sqlite3.connect(self.db)) as con:
            result = con.execute(statement, args).fetchall()
            con.commit()
            return result

    def send(self, email='member@example.com', purpose='login', headers=None):
        result = self.client.post('/api/studio/email-codes', json={'email': email, 'purpose': purpose}, headers=headers or {})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertNotIn('code', result.json())
        return self.codes[(email.strip().lower(), purpose)]

    def register(self, email='member@example.com', code=None, headers=None):
        code = code or self.send(email)
        return self.client.post('/api/studio/register-email', json={'email': email, 'code': code, 'password': 'new-password',
                                'name': '新同伴', 'skills': '设计', 'profile': '教育作品'}, headers=headers or {})

    def login(self, code, email='member@example.com'):
        return self.client.post('/api/studio/login-email', json={'email': email, 'code': code})

    def test_registration_password_login_and_single_use(self):
        code = self.send('Member@EXAMPLE.com')
        pending = self.login(code)
        self.assertEqual(pending.status_code, 422)
        self.assertEqual(pending.json()['error']['code'], 'registration_required')
        created = self.register(code=code)
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()['email'], 'member@example.com')
        self.assertEqual(created.json()['phone'], '')
        password = self.client.post('/api/studio/login', json={'account': 'MEMBER@example.com', 'password': 'new-password'})
        self.assertEqual(password.status_code, 200, password.text)
        self.assertEqual(password.json()['user_id'], created.json()['user_id'])
        self.assertEqual(self.login(code).status_code, 401)
        self.assertEqual(self.client.get('/api/core/me', headers={'Authorization': 'Bearer ' + created.json()['token']}).status_code, 401)

    def test_binding_preserves_phone_password_team_and_identity(self):
        team = self.client.post('/api/core/teams', json={'name': '同一个团队'}, headers=self.headers).json()
        code = self.send(purpose='bind', headers=self.headers)
        bound = self.client.post('/api/studio/email-bind', json={'email': 'member@example.com', 'code': code}, headers=self.headers)
        self.assertEqual(bound.status_code, 200, bound.text)
        self.assertEqual(bound.json()['user_id'], 'member')
        self.assertEqual(bound.json()['phone'], '18800000001')
        self.sql('DELETE FROM email_send_events')
        logged = self.login(self.send())
        self.assertEqual(logged.status_code, 200, logged.text)
        self.assertEqual(logged.json()['user_id'], 'member')
        auth = {'Authorization': 'Bearer ' + logged.json()['token']}
        me = self.client.get('/api/core/me', headers=auth).json()
        self.assertEqual(me['teams'][0]['id'], team['id'])
        self.assertEqual(self.client.get('/api/studio/account', headers=auth).json()['email'], 'member@example.com')
        for account in ['18800000001', 'member@example.com']:
            self.assertEqual(self.client.post('/api/studio/login', json={'account': account, 'password': 'test-password'}).json()['user_id'], 'member')

    def test_binding_requires_account_and_cannot_use_login_code(self):
        body = {'email': 'member@example.com', 'purpose': 'bind'}
        self.assertEqual(self.client.post('/api/studio/email-codes', json=body).status_code, 401)
        code = self.send()
        result = self.client.post('/api/studio/email-bind', json={'email': body['email'], 'code': code}, headers=self.headers)
        self.assertEqual(result.status_code, 401)
        self.assertIsNone(self.sql("SELECT email FROM people WHERE id='member'")[0][0])

    def test_binding_code_is_owned_by_requesting_user(self):
        code = self.send(purpose='bind', headers=self.headers)
        other = self.register('other@example.com').json()
        result = self.client.post('/api/studio/email-bind', json={'email': 'member@example.com', 'code': code}, headers={'Authorization': 'Bearer ' + other['token']})
        # Already-bound accounts cannot replace an address either.
        self.assertEqual(result.status_code, 409)
        self.sql("UPDATE people SET email=NULL WHERE id=?", (other['user_id'],))
        result = self.client.post('/api/studio/email-bind', json={'email': 'member@example.com', 'code': code}, headers={'Authorization': 'Bearer ' + other['token']})
        self.assertEqual(result.status_code, 401)

    def test_unique_email_cannot_overwrite_or_reset_an_account(self):
        created = self.register().json()
        self.sql('DELETE FROM email_send_events')
        code = self.send()
        self.assertEqual(self.register(code=code).status_code, 409)
        result = self.client.post('/api/studio/email-codes', json={'email': 'member@example.com', 'purpose': 'bind'}, headers=self.headers)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.sql('SELECT id FROM people WHERE email=?', ('member@example.com',))[0][0], created['user_id'])

    def test_guest_upgrade_keeps_existing_identity(self):
        guest = self.client.post('/api/core/guest-session').json()
        headers = {'Authorization': 'Bearer ' + guest['token']}
        before = self.client.get('/api/core/me', headers=headers).json()
        result = self.register(headers=headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['user_id'], before['person']['id'])
        after = self.client.get('/api/core/me', headers={'Authorization': 'Bearer ' + result.json()['token']}).json()
        self.assertFalse(after['guest'])

    def test_missing_configuration_sends_nothing(self):
        self.status.return_value = {'ready': False, 'registration_available': False}
        result = self.client.post('/api/studio/email-codes', json={'email': 'member@example.com'})
        self.assertEqual(result.status_code, 503)
        self.delivery.assert_not_called()
        self.assertFalse(self.sql('SELECT * FROM email_codes'))

    def test_failed_delivery_leaves_no_usable_code(self):
        self.delivery.side_effect = RuntimeError('private-test-secret')
        result = self.client.post('/api/studio/email-codes', json={'email': 'member@example.com'})
        self.assertEqual(result.status_code, 502)
        self.assertNotIn('private-test-secret', result.text)
        self.assertFalse(self.sql('SELECT * FROM email_codes'))

    def test_pending_expired_and_wrong_codes_cannot_log_in(self):
        self.sql("UPDATE people SET email='member@example.com' WHERE id='member'")
        code = self.send()
        self.sql("UPDATE email_codes SET status='pending'")
        self.assertEqual(self.login(code).status_code, 401)
        self.sql("UPDATE email_codes SET status='sent',expires_at='2000-01-01T00:00:00+00:00'")
        self.assertEqual(self.login(code).status_code, 401)
        self.assertEqual(self.client.get('/api/core/me', headers=self.headers).status_code, 200)

    def test_five_failures_burn_code_without_rotating_token(self):
        self.sql("UPDATE people SET email='member@example.com' WHERE id='member'")
        self.send()
        for _ in range(4):
            self.assertEqual(self.login('wrong').status_code, 401)
        self.assertEqual(self.login('wrong').status_code, 429)
        self.assertFalse(self.sql('SELECT * FROM email_codes'))
        self.assertEqual(self.client.get('/api/core/me', headers=self.headers).status_code, 200)

    def test_resend_and_hourly_recipient_limit(self):
        self.send()
        self.assertEqual(self.client.post('/api/studio/email-codes', json={'email': 'MEMBER@example.com'}).status_code, 429)
        for _ in range(4):
            self.sql('UPDATE email_send_events SET created_at=?', ((datetime.fromisoformat(now()) - timedelta(minutes=2)).isoformat(),))
            self.send()
        self.sql('UPDATE email_send_events SET created_at=?', ((datetime.fromisoformat(now()) - timedelta(minutes=2)).isoformat(),))
        self.assertEqual(self.client.post('/api/studio/email-codes', json={'email': 'member@example.com'}).status_code, 429)

    def test_source_limit_cannot_be_bypassed_with_forwarded_header(self):
        for i in range(20):
            self.send(f'member{i}@example.com')
        result = self.client.post('/api/studio/email-codes', json={'email': 'another@example.com'}, headers={'X-Forwarded-For': '203.0.113.1'})
        self.assertEqual(result.status_code, 429)


if __name__ == '__main__':
    unittest.main()
