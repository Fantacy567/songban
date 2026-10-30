"""Both login methods authenticate the same account; no external SMS is sent."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import create_app, digest, now
from app.studio import hash_password


class DualLoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'auth.sqlite3'
        self.client = TestClient(create_app(self.db, core_only=True))
        for target, value in [('must_deliver', False), ('test_codes_allowed', True),
                              ('deliver_login_code', (False, '测试环境，不发送短信'))]:
            mock = patch('app.studio.' + target, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)
        with closing(sqlite3.connect(self.db)) as con:
            con.execute('INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at,password_hash) VALUES(?,?,?,?,?,?,?,?)',
                        ('member', '18800000001', '测试同伴', '创作', '设计', digest('initial-token'), now(), hash_password('test-password')))
            con.commit()

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def code(self, phone='18800000001'):
        response = self.client.post('/api/studio/codes', json={'phone': phone})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['code']

    def login_code(self, code, phone='18800000001'):
        return self.client.post('/api/studio/login-code', json={'phone': phone, 'code': code})

    def test_password_then_code_keeps_account_team_and_password(self):
        password = self.client.post('/api/studio/login', json={'account': '18800000001', 'password': 'test-password'}).json()
        headers = {'Authorization': 'Bearer ' + password['token']}
        team = self.client.post('/api/core/teams', json={'name': '同一个小队'}, headers=headers).json()
        sms = self.login_code(self.code())
        self.assertEqual(sms.status_code, 200, sms.text)
        self.assertEqual(sms.json()['user_id'], password['user_id'])
        self.assertNotEqual(sms.json()['token'], password['token'])
        self.assertEqual(self.client.get('/api/core/me', headers=headers).status_code, 401)
        me = self.client.get('/api/core/me', headers={'Authorization': 'Bearer ' + sms.json()['token']}).json()
        self.assertEqual(me['teams'][0]['id'], team['id'])
        again = self.client.post('/api/studio/login', json={'account': '18800000001', 'password': 'test-password'})
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()['user_id'], 'member')

    def test_used_code_cannot_be_replayed(self):
        code = self.code()
        self.assertEqual(self.login_code(code).status_code, 200)
        self.assertEqual(self.login_code(code).status_code, 401)

    def test_wrong_code_does_not_rotate_existing_login(self):
        self.code()
        self.assertEqual(self.login_code('wrong').status_code, 401)
        self.assertEqual(self.client.get('/api/core/me', headers={'Authorization': 'Bearer initial-token'}).status_code, 200)

    def test_expired_code_rejected(self):
        code = self.code()
        with closing(sqlite3.connect(self.db)) as con:
            con.execute("UPDATE phone_codes SET expires_at='2000-01-01T00:00:00+00:00'")
            con.commit()
        self.assertEqual(self.login_code(code).status_code, 401)

    def test_five_failures_persist_and_burn_code(self):
        self.code()
        for _ in range(4):
            self.assertEqual(self.login_code('wrong').status_code, 401)
        self.assertEqual(self.login_code('wrong').status_code, 429)
        with closing(sqlite3.connect(self.db)) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM phone_codes').fetchone()[0], 0)

    def test_new_phone_needs_explicit_registration_and_keeps_code(self):
        phone = '18800000002'
        code = self.code(phone)
        result = self.login_code(code, phone)
        self.assertEqual(result.status_code, 422)
        self.assertEqual(result.json()['error']['code'], 'registration_required')
        created = self.client.post('/api/studio/register', json={'phone': phone, 'code': code, 'password': 'new-password',
                                   'name': '新同伴', 'profile': '第一次参赛', 'skills': '学习中'})
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(self.login_code(code, phone).status_code, 401)

    def test_missing_sms_configuration_is_explicit(self):
        with patch('app.studio.test_codes_allowed', return_value=False):
            response = self.client.post('/api/studio/codes', json={'phone': '18800000001'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('code', response.json().get('data', {}))
