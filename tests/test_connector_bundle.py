import io,json,os,sqlite3,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import create_app,digest,now
from app.connector_bundle import build_bundle

class ConnectorBundleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.path=self.root/'test.sqlite3';self.app=create_app(self.path,core_only=True,enforce_journey=False);self.c=TestClient(self.app,base_url='https://public.example',client=('203.0.113.1',123))
  with closing(sqlite3.connect(self.path)) as con:
   for user in ['a','b']:con.execute('INSERT INTO people(id,name,phone,token_hash,created_at) VALUES(?,?,?,?,?)',(user,user,'synthetic-'+user,digest('account-'+user),now()))
   con.commit()
  self.h={'Authorization':'Bearer account-a'};self.team=self.c.post('/api/core/teams',headers=self.h,json={'name':'远程包测试队'}).json();self.url='/api/core/teams/'+self.team['id']
 def tearDown(self):self.c.close();self.tmp.cleanup()
 def download(self,tool='connector-plugin'):
  r=self.c.post(self.url+'/installer.zip',headers=self.h,json={'tool':tool,'consent':True});self.assertEqual(r.status_code,200,r.text if r.status_code!=200 else '');return r
 def test_remote_download_works_without_server_installation(self):
  self.assertFalse(self.c.get('/api/core/install-options',headers=self.h).json()['available']);self.assertTrue(self.c.get('/api/core/install-options',headers=self.h).json()['download_available'])
  self.assertEqual(self.c.post(self.url+'/install',headers=self.h,json={'tool':'connector-plugin','consent':True}).status_code,403)
  with patch('app.team_core.install_connector_plugin') as native,patch('app.team_core.install_project') as project:
   r=self.download();native.assert_not_called();project.assert_not_called()
  self.assertEqual(r.headers['cache-control'],'no-store')
  with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
   names=archive.namelist();self.assertTrue(all(n.startswith('songban-connector-install/') and '..' not in n for n in names))
   binding=json.loads(archive.read('songban-connector-install/connection.json'));self.assertEqual(binding['url'],'https://public.example');self.assertEqual(binding['team_id'],self.team['id']);self.assertEqual(binding['tool'],'connector-plugin');self.assertNotIn('account-a',r.content.decode(errors='ignore'))
   for name in names:
    if name!='songban-connector-install/connection.json':self.assertNotIn(binding['token'].encode(),archive.read(name))
   for name in ['install.py','安装松伴.command','安装松伴.cmd','plugins/songban-native/server.py','app/connector_plugin.py']:self.assertIn('songban-connector-install/'+name,names)
  auth={'Authorization':'Bearer '+binding['token']};self.assertEqual(self.c.get(self.url+'/context',headers=auth).status_code,200)
  self.assertEqual(self.c.post(self.url+'/connections',headers=auth,json={'label':'不允许生成其他凭证'}).status_code,403)
 def test_membership_consent_limit_and_failed_package(self):
  self.assertEqual(self.c.post(self.url+'/installer.zip',headers={'Authorization':'Bearer account-b'},json={'consent':True}).status_code,403)
  self.assertEqual(self.c.post(self.url+'/installer.zip',headers=self.h,json={}).status_code,422)
  with patch('app.connector_bundle.build_bundle',side_effect=RuntimeError('synthetic failure')):self.assertEqual(self.c.post(self.url+'/installer.zip',headers=self.h,json={'consent':True}).status_code,500)
  with closing(sqlite3.connect(self.path)) as con:self.assertEqual(con.execute('SELECT revoked FROM core_connections').fetchone()[0],1)
 def test_demo_binding_and_compatibility_tool_are_retained(self):
  self.app.state.demo=True;self.app.state.demo_base_path='/demo'
  h={**self.h,'X-Songban-Demo':'00000000-0000-0000-0000-000000000001'}
  r=self.c.post(self.url+'/installer.zip',headers=h,json={'tool':'cursor','consent':True});self.assertEqual(r.status_code,200)
  with zipfile.ZipFile(io.BytesIO(r.content)) as archive:binding=json.loads(archive.read('songban-connector-install/connection.json'))
  self.assertEqual(binding['base_path'],'/demo');self.assertEqual(binding['demo_session'],h['X-Songban-Demo']);self.assertEqual(binding['tool'],'cursor')
 def test_unpacked_installer_is_self_contained_and_uses_client_paths(self):
  r=self.download()
  with zipfile.ZipFile(io.BytesIO(r.content)) as archive:archive.extractall(self.root/'unpacked')
  folder=self.root/'unpacked/songban-connector-install'
  # A bad binding should produce a readable error without touching tool configuration.
  (folder/'connection.json').write_text('{}')
  env={**os.environ,'PYTHONUTF8':'0','PYTHONIOENCODING':'cp1252'}
  result=subprocess.run([sys.executable,str(folder/'install.py'),'--check','--home',str(self.root/'client')],cwd=folder,capture_output=True,text=True,encoding='utf-8',env=env,timeout=15)
  self.assertNotEqual(result.returncode,0);self.assertNotIn('Traceback',result.stdout+result.stderr);self.assertIn('连接检查未通过',result.stdout);self.assertFalse((self.root/'client/.codex').exists())
