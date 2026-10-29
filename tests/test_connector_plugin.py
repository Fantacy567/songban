import importlib.util
import json
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

 def test_real_cli_register_preserves_other_settings_and_keeps_secrets_out_of_cache(self):
  with tempfile.TemporaryDirectory(prefix='native-plugin-test-') as d:
   home=Path(d);conf=home/'.codex/config.toml';conf.parent.mkdir();conf.write_text('model="test-model"\nmodel_provider="openai"\n[plugins."other@demo"]\nenabled=false\n')
   r=install_connector_plugin('team','me','test-id','sbconn_synthetic-secret','http://127.0.0.1:8888',home=home,probe=lambda *_:True)
   self.assertTrue(r['enabled']);self.assertEqual(r['kind'],'native-plugin')
   from scripts.check_native_plugin_host import check
   host=check(home,home);self.assertTrue(host['upload_tool_loaded']);self.assertEqual(host['loader_errors'],[])
   mcp=json.loads((Path(r['project_dir'])/'mcp.json').read_text());self.assertEqual(mcp['mcpServers']['songban']['type'],'stdio')
   import tomllib
   c=tomllib.loads(conf.read_text());self.assertEqual(c['model'],'test-model');self.assertEqual(c['model_provider'],'openai');self.assertFalse(c['plugins']['other@demo']['enabled'])
   for p in (home/'.codex/plugins/cache/songban-local').rglob('*'):
    if p.is_file():self.assertNotIn(b'sbconn_synthetic-secret',p.read_bytes())
   self.assertEqual(Path(r['config_file']).stat().st_mode&0o777,0o600)

 def test_failed_probe_restores_binding_and_does_not_enable(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(InstallError):install_connector_plugin('team','me','test','sbconn_test','http://127.0.0.1:8888',home=d,probe=lambda *_:False)
   self.assertFalse((Path(d)/'.codex/plugins/songban-local/private/connection.json').exists())

if __name__=='__main__':unittest.main()
