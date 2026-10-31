import unittest,uuid,sqlite3,tempfile
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import create_app
from app.preview_server import Preview
class DemoModeTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'real.sqlite3';self.real=create_app(self.path,core_only=True,enforce_journey=True)
  with patch('app.preview_server.real_app',self.real):
   self.preview=Preview()
  self.patch=patch('app.preview_server.real_app',self.real);self.patch.start();self.client=TestClient(self.preview)
 def tearDown(self):self.client.close();self.preview.demo.tmp.cleanup();self.patch.stop();self.temp.cleanup()
 def test_same_frontend_separate_identity_and_database(self):
  real=self.client.get('/').text;demo=self.client.get('/demo/').text
  self.assertNotIn('window.SONGBAN_DEMO=true',real);self.assertIn('window.SONGBAN_DEMO_BASE="/demo"',demo)
  for page in [real,demo]:self.assertIn('songban.js?',page)
  tokens=[]
  for _ in range(2):
   h={'X-Songban-Demo':str(uuid.uuid4())};token=self.client.post('/demo/api/demo/bootstrap',headers=h).json()['token'];tokens.append(token);h['Authorization']='Bearer '+token
   self.assertEqual(self.client.get('/demo/api/journey',headers=h).json()['stage'],'interview')
   self.assertEqual(self.client.post('/demo/api/core/teams',headers=h,json={'name':'跳过'}).status_code,409)
   self.assertEqual(self.client.get('/api/core/me',headers=h).status_code,401)
  self.assertNotEqual(*tokens)
  with sqlite3.connect(self.path) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM people').fetchone()[0],0)
  self.assertEqual(self.client.post('/api/demo/bootstrap').status_code,404)
 def test_demo_rejects_remote_hosts_and_missing_session(self):
  self.assertEqual(self.client.get('/demo/',headers={'Host':'example.com'}).status_code,403)
  self.assertEqual(self.client.post('/demo/api/demo/bootstrap').status_code,409)

 def test_explicit_public_origin_keeps_session_and_real_account_isolation(self):
  with patch.dict('os.environ',{'SONGBAN_DEMO_PUBLIC_ORIGIN':'https://preview.example.com'}):
   self.assertEqual(self.client.get('/demo/',headers={'Host':'other.example.com'}).status_code,403)
   self.assertEqual(self.client.get('/demo/',headers={'Host':'preview.example.com'}).status_code,200)
   h={'Host':'preview.example.com','X-Songban-Demo':str(uuid.uuid4())}
   token=self.client.post('/demo/api/demo/bootstrap',headers=h).json()['token']
   h['Authorization']='Bearer '+token
   self.assertEqual(self.client.get('/demo/api/journey',headers=h).json()['stage'],'interview')
   self.assertEqual(self.client.get('/api/core/me',headers=h).status_code,401)
   app,_=self.preview.demo.sessions[h['X-Songban-Demo']]
   self.assertEqual(app.state.demo_base_url,'https://preview.example.com/demo')
