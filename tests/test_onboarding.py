"""Visitor access and private, persistent starting preferences."""
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'onboarding.sqlite3'
        self.client = TestClient(create_app(self.path, core_only=True))
        self.value = {'interests': ['音乐'], 'skills': ['画画或设计'], 'time': '半天', 'experience': '给班级做过海报', 'expected_revision': 0}

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def guest(self):
        response = self.client.post('/api/core/guest-session', json={})
        self.assertEqual(response.status_code, 201, response.text)
        return {'Authorization': 'Bearer ' + response.json()['token']}

    def test_guest_can_enter_without_sms_and_cannot_read_another_team(self):
        a, b = self.guest(), self.guest()
        first = self.client.get('/api/core/me', headers=a).json()
        second = self.client.get('/api/core/me', headers=b).json()
        self.assertTrue(first['guest'])
        self.assertIsNone(first['preferences'])
        self.assertNotEqual(first['person']['id'], second['person']['id'])
        created = self.client.post('/api/core/teams', headers=a, json={'name': '访客自己的小队'})
        self.assertEqual(created.status_code, 200, created.text)
        team = created.json()['id']
        self.assertEqual(self.client.get('/api/core/teams/' + team, headers=b).status_code, 403)
        self.assertEqual(self.client.get('/api/core/teams/' + team).status_code, 401)

    def test_preferences_survive_restart_and_are_private_to_identity(self):
        a, b = self.guest(), self.guest()
        saved = self.client.put('/api/core/me/preferences', headers=a, json={**self.value, 'city': ' 上海 '})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()['preferences']['revision'], 1)
        self.assertIsNone(self.client.get('/api/core/me', headers=b).json()['preferences'])
        with TestClient(create_app(self.path, core_only=True)) as restarted:
            data = restarted.get('/api/core/me', headers=a).json()
            self.assertEqual(data['preferences']['interests'], ['音乐'])
            self.assertEqual(data['preferences']['experience'], '给班级做过海报')
            self.assertEqual(data['preferences']['city'], '上海')
            self.assertEqual(data['person']['skills'], '')

    def test_stale_preference_save_cannot_overwrite_other_window(self):
        auth = self.guest()
        self.assertEqual(self.client.put('/api/core/me/preferences', headers=auth, json=self.value).status_code, 200)
        response = self.client.put('/api/core/me/preferences', headers=auth, json={**self.value, 'time': '一天'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get('/api/core/me', headers=auth).json()['preferences']['time'], '半天')
        response = self.client.put('/api/core/me/preferences', headers=auth, json={**self.value, 'time': '一天', 'expected_revision': 1})
        self.assertEqual(response.json()['preferences']['revision'], 2)

    def test_invalid_and_impersonated_preferences_are_rejected(self):
        auth = self.guest()
        for invalid in ({'interests': []}, {'interests': ['未定义选项']}, {'skills': ['整理资料', '都没做过，想试试']},
                        {'time': '永久'}, {'experience': '长' * 1501}, {'user_id': 'somebody'}, {'interests': ['音乐', '音乐']},
                        {'city': '长' * 61}, {'city': 123}):
            with self.subTest(invalid=invalid.keys()):
                self.assertEqual(self.client.put('/api/core/me/preferences', headers=auth, json={**self.value, **invalid}).status_code, 422)
        self.assertEqual(self.client.put('/api/core/me/preferences', json=self.value).status_code, 401)
        self.assertIsNone(self.client.get('/api/core/me', headers=auth).json()['preferences'])

    def test_optional_city_is_compatible_with_old_records_and_clients(self):
        auth = self.guest()
        saved = self.client.put('/api/core/me/preferences', headers=auth, json=self.value)
        self.assertEqual(saved.json()['preferences']['city'], '')
        saved = self.client.put('/api/core/me/preferences', headers=auth, json={**self.value, 'city': '景洪', 'expected_revision': 1})
        self.assertEqual(saved.json()['preferences']['city'], '景洪')
        saved = self.client.put('/api/core/me/preferences', headers=auth, json={**self.value, 'expected_revision': 2})
        self.assertEqual(saved.json()['preferences']['city'], '景洪')
        saved = self.client.put('/api/core/me/preferences', headers=auth, json={**self.value, 'city': '', 'expected_revision': 3})
        self.assertEqual(saved.json()['preferences']['city'], '')

    def test_normal_account_is_not_relabelled_as_guest(self):
        auth = self.guest()
        user_id = self.client.get('/api/core/me', headers=auth).json()['person']['id']
        with closing(sqlite3.connect(self.path)) as con:
            con.execute('DELETE FROM core_guest_people WHERE user_id=?', (user_id,))
            con.commit()
        self.assertFalse(self.client.get('/api/core/me', headers=auth).json()['guest'])
        self.assertEqual(self.client.put('/api/core/me/preferences', headers=auth, json=self.value).status_code, 200)

    def test_connector_cannot_read_or_change_private_preferences(self):
        auth = self.guest()
        team = self.client.post('/api/core/teams', headers=auth, json={'name': '连接器边界'}).json()['id']
        token = self.client.post(f'/api/core/teams/{team}/connections', headers=auth, json={'label': '测试'}).json()['token']
        connector = {'Authorization': 'Bearer ' + token}
        self.assertEqual(self.client.get('/api/core/me', headers=connector).status_code, 401)
        self.assertEqual(self.client.put('/api/core/me/preferences', headers=connector, json=self.value).status_code, 401)
