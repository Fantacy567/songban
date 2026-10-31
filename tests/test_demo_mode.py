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

 def test_demo_native_binding_routes_only_to_its_isolated_session(self):
  import json,io,importlib.util
  from urllib.parse import urlsplit
  root=Path(__file__).resolve().parents[1]
  spec=importlib.util.spec_from_file_location('demo_native_transport',root/'plugins/songban-native/transport.py');transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
  session=str(uuid.uuid4());headers={'X-Songban-Demo':session}
  with TestClient(self.preview,base_url='http://127.0.0.1:8890',client=('127.0.0.1',12345)) as client:
   token=client.post('/demo/api/demo/bootstrap',headers=headers).json()['token'];headers['Authorization']='Bearer '+token
   def call(path,body):
    response=client.post('/demo'+path,headers=headers,json=body);self.assertEqual(response.status_code,200,response.text);return response.json()
   iv=call('/api/core/interview/start',{})
   for answer in ['设计工具','会画草图','6小时']:iv=call('/api/core/interview/answer',{'version':iv['version'],'question_id':iv['current_question']['id'],'request_id':uuid.uuid4().hex,'text':answer})
   call('/api/core/interview/confirm',{'version':iv['version'],'request_id':uuid.uuid4().hex})
   call('/api/journey/contest',{'name':'演示赛','event_time':'两天','location':'线上','rubric':'完成度','requirements':'网页','source_text':'虚构公告','deadline':'2026-11-02T18:00:00+08:00'})
   team=call('/api/core/teams',{'name':'虚构绑定队'});base='/api/core/teams/'+team['id']
   connection=call(base+'/connections',{'label':'原生演示验证'})
   with patch('app.team_core.install_connector_plugin',return_value={'installed':True}) as install:
    call(base+'/install',{'tool':'connector-plugin','consent':True})
    options=install.call_args.kwargs['binding_options'];self.assertEqual(options,{'base_path':'/demo','demo_session':session})
   binding={'url':'http://127.0.0.1:8890','team_id':team['id'],'token':connection['token'],**options}
   class Opener:
    def open(inner,request,timeout):
     response=client.request(request.get_method(),urlsplit(request.full_url).path,headers=dict(request.header_items()),content=request.data)
     if response.status_code!=200:raise transport.ConnectorError(str(response.status_code))
     return io.BytesIO(response.content)
   with patch.object(transport.urllib.request,'build_opener',return_value=Opener()):
    context=transport.request(binding,'/context');self.assertEqual(context['team']['id'],team['id'])
    body={'event_id':'synthetic-demo-connector','selected':True,'origin':'personal_agent','tool':'协议测试','user_message':'虚构演示：做什么？','assistant_summary':'虚构演示：先做草图','assistant_message':'虚构演示：先做三个步骤','full_reply_authorized':True,'conversation_stage':'discussion'}
    receipt=transport.request(binding,'/conversation-notes',body);self.assertTrue(receipt['note_id'])
    with self.assertRaises(transport.ConnectorError):transport.request({**binding,'demo_session':str(uuid.uuid4())},'/context')
   self.assertEqual(client.get(base+'/context',headers={'Authorization':'Bearer '+connection['token']}).status_code,401)
