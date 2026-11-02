"""The walkthrough seeds only its own DB and keeps external actions simulated."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from scripts.run_demo import account_login_url, build_demo


class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app = build_demo(Path(cls.tmp.name) / 'demo.sqlite3')
        cls.client = TestClient(cls.app)
        script = cls.client.get('/demo/bootstrap.js').text
        cls.fixture = json.loads(script.split('=', 1)[1].split(';\n', 1)[0])
        cls.headers = {'Authorization': 'Bearer ' + cls.fixture['users'][0]['token']}
        cls.base = '/api/core/teams/' + cls.fixture['team']['id']

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.tmp.cleanup()

    def test_five_people_and_populated_flow(self):
        snapshot = self.client.get(self.base, headers=self.headers).json()
        self.assertEqual(len(snapshot['members']), 5)
        self.assertEqual(len(snapshot['active_plan']['tasks']), 12)
        self.assertEqual(sum(t['handoff_state'] == 'accepted' for t in snapshot['active_plan']['tasks']), 5)
        self.assertEqual(len(snapshot['team_library']), 5)
        for user in self.fixture['users']:
            headers = {'Authorization': 'Bearer ' + user['token']}
            me = self.client.get('/api/core/me', headers=headers).json()
            self.assertEqual(me['preferences']['city'], '上海')
            materials = self.client.get('/api/materials/space', headers=headers).json()
            self.assertEqual(len(materials['sources']), 2)
            self.assertTrue(materials['result']['items'])
            sessions = self.client.get('/api/workbench/sessions', headers=headers).json()['sessions']
            self.assertTrue(sessions)
            history = self.client.get('/api/workbench/sessions/' + sessions[0]['id'], headers=headers).json()
            self.assertTrue(any(m['mode'] == 'fixture' for m in history['messages']))

    def test_no_real_install_or_sms_and_no_external_url_fetch(self):
        with patch('app.team_core.install_connector_plugin') as install, patch('app.studio.deliver_login_code') as sms, patch('app.materials_parse.public_request') as fetch:
            result = self.client.post(self.base + '/install', headers=self.headers, json={'tool':'connector-plugin', 'consent':True})
            self.assertEqual(result.json()['kind'], 'demo')
            self.assertEqual(self.client.post('/api/studio/login-code', json={'phone':'18800000001'}).status_code, 403)
            space = self.client.get('/api/materials/space', headers=self.headers).json()
            base = '/api/materials/spaces/' + space['id']
            source = self.client.post(base + '/sources', headers=self.headers, json={'request_id':'demo-url', 'kind':'url', 'name':'模拟网页', 'content':'https://example.invalid/demo'}).json()['source']
            revision = self.client.get(base, headers=self.headers).json()['revision']
            parsed = self.client.post(base + '/sources/' + source['id'] + '/parse', headers=self.headers, json={'expected_revision':revision})
            self.assertEqual(parsed.status_code, 200)
            install.assert_not_called();sms.assert_not_called();fetch.assert_not_called()

    def test_demo_assets_are_opt_in_and_bootstrap_not_cached(self):
        response = self.client.get('/')
        self.assertIn('/demo/bootstrap.js', response.text)
        self.assertIn('songban-demo.js', response.text)
        self.assertEqual(self.client.get('/demo/bootstrap.js').headers['cache-control'], 'no-store')
        source = (Path(__file__).resolve().parents[1] / 'static/songban.html').read_text(encoding='utf-8')
        self.assertNotIn('/demo/bootstrap.js', source)
        self.assertNotIn('songban-demo.js', source)

    def test_account_entry_does_not_enable_email_in_demo(self):
        self.assertEqual(self.fixture['login_url'], 'http://127.0.0.1:8893/#/login')
        with patch('app.email_login.deliver_email_code') as send:
            response = self.client.post('/api/studio/email-codes', json={'email': 'member@example.com'})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()['error']['code'], 'demo_only')
            send.assert_not_called()

    def test_account_entry_accepts_custom_service_but_rejects_unsafe_links(self):
        self.assertEqual(account_login_url('http://127.0.0.1:8894'), 'http://127.0.0.1:8894/#/login')
        self.assertEqual(account_login_url('https://example.com/songban/'), 'https://example.com/songban/#/login')
        for value in ['javascript:alert(1)', '//example.com', 'https://user:secret@example.com', 'https://example.com?token=secret', 'https://example.com/#login']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                account_login_url(value)

    def test_real_connector_opt_in_uses_checked_installer_and_keeps_login_blocked(self):
        app = build_demo(self.app.state.db_path, resume=self.fixture, real_connector=True)
        with TestClient(app, base_url='http://127.0.0.1:8895') as client, \
                patch('app.team_install.is_local_request', return_value=True), \
                patch('app.team_core.is_local_request', return_value=True), \
                patch('app.team_core.install_connector_plugin', return_value={'kind': 'native-plugin', 'installed': True}) as install, \
                patch('app.email_login.deliver_email_code') as email:
            options = client.get('/api/core/install-options', headers=self.headers).json()
            self.assertEqual(options['tools'][0]['id'], 'connector-plugin')
            self.assertTrue(options['available'])
            denied = client.post(self.base + '/install', headers=self.headers, json={'tool': 'connector-plugin'})
            self.assertNotEqual(denied.status_code, 200)
            install.assert_not_called()
            result = client.post(self.base + '/install', headers=self.headers, json={'tool': 'connector-plugin', 'consent': True})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()['kind'], 'native-plugin')
            self.assertEqual(install.call_args.args[0], self.fixture['team']['id'])
            self.assertEqual(install.call_args.args[1], self.fixture['users'][0]['id'])
            self.assertEqual(install.call_args.args[4], 'http://127.0.0.1:8895')
            self.assertEqual(client.post('/api/studio/email-codes', json={'email': 'member@example.com'}).status_code, 403)
            email.assert_not_called()

    def test_topic_walkthrough_has_five_people_and_no_live_model(self):
        base='/api/core/teams/'+self.fixture['topic_team']['id']
        def get():return self.client.get(base+'/topic-selection',headers=self.headers).json()['round']
        def advance(action):
            response=self.client.post('/demo/advance',json={'team_id':self.fixture['topic_team']['id'],'action':action},headers=self.headers)
            self.assertEqual(response.status_code,200,response.text)
            self.assertTrue(response.json()['simulated'])
        self.assertIsNone(get())
        snapshot=self.client.get(base,headers=self.headers).json()
        self.assertEqual(len(snapshot['members']),5)
        self.assertFalse(snapshot['guided_workflow'])
        result=self.client.post(base+'/topic-selection/rounds',json={'request_id':'demo-round-start','expected_revision':snapshot['revision'],'track':'校园 AI 创作'},headers=self.headers)
        self.assertEqual(result.status_code,200,result.text)
        with patch('app.topic_selection_model.httpx.Client') as network:
            advance('upload');advance('upload')
            self.assertEqual(len(get()['candidates']),5)
            for count in range(1,5):advance('confirm_next');self.assertEqual(get()['confirmed_count'],count)
            result=self.client.post(base+'/topic-selection/ready',json={'request_id':'demo-own-ready','expected_revision':get()['revision'],'complete':True},headers=self.headers)
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(get()['phase'],'voting');self.assertEqual(get()['ranking']['mode'],'fixture')
            candidate=get()['eligible'][0]
            result=self.client.post(base+'/topic-selection/votes',json={'request_id':'demo-own-vote','expected_revision':get()['revision'],'candidate_id':candidate,'ballot':1},headers=self.headers)
            self.assertEqual(result.status_code,200,result.text)
            advance('vote_others');self.assertEqual(get()['votes_count'],5)
            self.assertEqual(get()['phase'],'awaiting_selection')
            result=self.client.post(base+'/topic-selection/select',json={'request_id':'demo-own-select','expected_revision':get()['revision'],'candidate_id':candidate},headers=self.headers)
            self.assertEqual(result.status_code,200,result.text)
            proposal=self.client.post(base+'/review',json={},headers=self.headers).json()
            result=self.client.post(base+'/proposals/'+proposal['proposal_id']+'/confirm',json={'expected_revision':proposal['base_revision']},headers=self.headers)
            self.assertEqual(result.status_code,200,result.text)
            advance('claim_others')
            tasks=self.client.get(base,headers=self.headers).json()['active_plan']['tasks']
            self.assertEqual(sum(not t['owner_id'] for t in tasks),3)
            self.assertEqual(sum(bool(t['owner_id']) for t in tasks),9)
            network.assert_not_called()

    def test_demo_helper_requires_demo_identity_and_known_team(self):
        response=self.client.post('/demo/advance',json={'team_id':'anything','action':'upload'})
        self.assertEqual(response.status_code,401)
        response=self.client.post('/demo/advance',json={'team_id':'anything','action':'upload'},headers=self.headers)
        self.assertEqual(response.status_code,422)
