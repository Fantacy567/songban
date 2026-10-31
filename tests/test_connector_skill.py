import importlib.util
import json
from tests.platform_files import assert_private, directory_link
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app.connector_skill import install_connector_skill
from app.team_install import InstallError

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('selected_connector',ROOT/'plugins/songban-connector/scripts/connector.py')
connector=importlib.util.module_from_spec(spec);spec.loader.exec_module(connector)


class SelectedSkillTests(unittest.TestCase):
 def test_unselected_turn_never_reads_binding_or_network(self):
  with patch.object(connector,'binding') as binding,patch.object(connector,'request') as request:
   with self.assertRaises(connector.ConnectorError):connector.main(['send'])
   binding.assert_not_called();request.assert_not_called()

 def test_only_allowlisted_current_turn_fields_and_redaction(self):
  data=connector.payload({'summary':'项目进展 API_KEY=sk-test-secret-1234567','excerpt':'Bearer sbconn_secret123456'})
  self.assertNotIn('secret',json.dumps(data));self.assertTrue(data['selected'])
  with self.assertRaises(connector.ConnectorError):connector.payload({'summary':'text','user_id':'other-person'})

 def test_empty_round_not_uploaded(self):
  with self.assertRaises(connector.ConnectorError):connector.payload({'summary':' '})

 def test_skill_is_global_explicit_only_and_has_chinese_title(self):
  with tempfile.TemporaryDirectory() as tmp:
   r=install_connector_skill('team','me','id','sbconn_test-token','http://127.0.0.1:8888',home=tmp,probe=lambda _:True)
   folder=Path(tmp)/'.codex/skills/songban-connector'
   meta=(folder/'agents/openai.yaml').read_text(encoding='utf-8')
   self.assertIn('display_name: "松伴连接器"',meta);self.assertIn('allow_implicit_invocation: false',meta)
   assert_private(self,folder/'binding.json')
   self.assertNotIn('sbconn_', (folder/'SKILL.md').read_text(encoding='utf-8'));self.assertEqual(r['kind'],'selected-turn-skill')

 def test_failed_binding_check_rolls_back(self):
  with tempfile.TemporaryDirectory() as tmp:
   with self.assertRaises(InstallError):install_connector_skill('team','me','id','sbconn_test-token','http://127.0.0.1:8888',home=tmp,probe=lambda _:False)
   self.assertFalse((Path(tmp)/'.codex/skills/songban-connector/binding.json').exists())

if __name__=='__main__':unittest.main()
