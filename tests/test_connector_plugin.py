import importlib.util
import json
from tests.platform_files import assert_private, directory_link
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from app.connector_plugin import install_connector_plugin
from app.team_install import InstallError

SOURCE=Path(__file__).resolve().parent.parent/'plugins/songban-native'
sys.path.insert(0,str(SOURCE))
spec=importlib.util.spec_from_file_location('native_server',SOURCE/'server.py');server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)

class NativePluginTests(unittest.TestCase):
 def test_topic_unselected_never_reads_binding_and_full_reply_kept(self):
  args={'selected':True,'round_id':'round','event_id':'topic-turn','topic_title':'选题','user_message':'  本人原话\n','assistant_message':'可见回复全文\n第二段'}
  with patch.object(server,'binding') as binding:
   with self.assertRaises(server.ConnectorError):server.invoke('songban_share_topic_turn',{**args,'selected':False},'missing')
   binding.assert_not_called()
  with patch.object(server,'binding',return_value={}),patch.object(server,'request',return_value={'note_id':'turn'}) as request:
   self.assertTrue(server.invoke('songban_share_topic_turn',args,'test')['synced'])
   self.assertEqual(request.call_args.args[1],'/topic-selection/turns')
   self.assertEqual(request.call_args.args[2]['assistant_message'],args['assistant_message'])
   self.assertEqual(request.call_args.args[2]['user_message'],args['user_message'])

 def test_topic_rejects_oversize_identity_and_missing_receipt(self):
  args={'selected':True,'round_id':'round','event_id':'topic-turn','topic_title':'选题','user_message':'本人原话','assistant_message':'回复'}
  for extra in ({'user_id':'other'},{'assistant_message':'x'*50001}):
   with patch.object(server,'binding') as binding:
    with self.assertRaises(server.ConnectorError):server.invoke('songban_share_topic_turn',{**args,**extra},'test')
    binding.assert_not_called()
  with patch.object(server,'binding',return_value={}),patch.object(server,'request',return_value={}):
   with self.assertRaises(server.ConnectorError):server.invoke('songban_share_topic_turn',args,'test')

 def test_unselected_never_reads_binding(self):
  with patch.object(server,'binding') as binding:
   with self.assertRaises(server.ConnectorError):server.invoke('songban_sync_selected_turn',{'selected':False},'missing')
   binding.assert_not_called()

 def test_success_receipt_and_missing_receipt(self):
  args={'selected':True,'event_id':'test-turn','summary':'合成测试 API_KEY=sk-test-secret12345'}
  with patch.object(server,'binding',return_value={}),patch.object(server,'request',return_value={'note_id':'note','duplicate':False}) as request:
   r=server.invoke('songban_sync_selected_turn',args,'test');self.assertTrue(r['synced']);self.assertNotIn('secret',json.dumps(request.call_args.args))
  with patch.object(server,'binding',return_value={}),patch.object(server,'request',return_value={}):
   with self.assertRaises(server.ConnectorError):server.invoke('songban_sync_selected_turn',args,'test')

 def test_full_reply_transport_and_readonly_library_tools(self):
  from urllib.parse import parse_qs,urlsplit
  long_reply='完整可见回复'*9000
  body=server.payload({'event_id':'long-turn','user_message':'请解释','assistant_summary':'解释要点','assistant_message':long_reply,'full_reply_authorized':True})
  self.assertEqual(body['assistant_message'],long_reply)
  with patch.object(server,'binding',return_value={}),patch.object(server,'request',return_value={'items':[]}) as request:
   server.invoke('songban_search_team_library',{'query':'设计','stage':'discussion'},'test')
   query=parse_qs(urlsplit(request.call_args.args[1]).query)
   self.assertEqual(query['q'],['设计']);self.assertEqual(query['brief'],['true'])
  with patch.object(server,'binding',return_value={}),patch.object(server,'request',return_value={'id':'note'}) as request:
   server.invoke('songban_read_library_record',{'record_id':'note'},'test');self.assertEqual(request.call_args.args[1],'/library/note')
  readonly={x['name']:x.get('annotations',{}).get('readOnlyHint') for x in server.TOOLS}
  self.assertTrue(readonly['songban_search_team_library']);self.assertTrue(readonly['songban_read_library_record'])

 def test_real_cli_register_preserves_other_settings_and_keeps_secrets_out_of_cache(self):
  with tempfile.TemporaryDirectory(prefix='native-plugin-test-') as d:
   home=Path(d);conf=home/'.codex/config.toml';conf.parent.mkdir();conf.write_text('model="test-model"\nmodel_provider="openai"\n[plugins."other@demo"]\nenabled=false\n')
   r=install_connector_plugin('team','me','test-id','sbconn_synthetic-secret','http://127.0.0.1:8888',home=home,probe=lambda *_:True)
   self.assertTrue(r['enabled']);self.assertEqual(r['kind'],'native-plugin')
   self.assertTrue(r['host_tools_loaded'])
   from scripts.check_native_plugin_host import check
   host=check(home,home);self.assertTrue(host['upload_tool_loaded']);self.assertEqual(host['loader_errors'],[])
   mcp=json.loads((Path(r['project_dir'])/'mcp.json').read_text(encoding='utf-8'));self.assertEqual(mcp['mcpServers']['songban']['type'],'stdio')
   if mcp['mcpServers']['songban']['args'][0].startswith('${PLUGIN_ROOT}'):
    self.assertEqual(Path(mcp['mcpServers']['songban']['command']).name,mcp['mcpServers']['songban']['command'])
   else:
    self.assertTrue(Path(mcp['mcpServers']['songban']['command']).is_absolute())
    self.assertTrue(Path(mcp['mcpServers']['songban']['args'][0]).is_file())
   import tomllib
   c=tomllib.loads(conf.read_text(encoding='utf-8'));self.assertEqual(c['model'],'test-model');self.assertEqual(c['model_provider'],'openai');self.assertFalse(c['plugins']['other@demo']['enabled'])
   for p in (home/'.codex/plugins/cache/songban-local').rglob('*'):
    if p.is_file():self.assertNotIn(b'sbconn_synthetic-secret',p.read_bytes())
   assert_private(self,Path(r['config_file']))

 def test_failed_probe_restores_binding_and_does_not_enable(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(InstallError):install_connector_plugin('team','me','test','sbconn_test','http://127.0.0.1:8888',home=d,probe=lambda *_:False)
   self.assertFalse((Path(d)/'.codex/plugins/songban-local/private/connection.json').exists())

 def test_host_rejection_is_not_reported_as_success(self):
  with tempfile.TemporaryDirectory() as d:
   with patch('app.connector_plugin.check_host',return_value={'upload_tool_loaded':False,'loader_errors':['fixture host rejection']}):
    with self.assertRaises(InstallError) as caught:
     install_connector_plugin('team','me','test','sbconn_test','http://127.0.0.1:8888',home=d,probe=lambda *_:True)
   self.assertEqual(caught.exception.code,'plugin_not_loaded')
   self.assertFalse((Path(d)/'.codex/plugins/songban-local/private/connection.json').exists())

if __name__=='__main__':unittest.main()
