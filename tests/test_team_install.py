import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from app.team_install import InstallError, install_project, is_local_request, project_path


class InstallerTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def install(self,tool='codex',token='sbconn_only-a-test-connection',**kw):
        return install_project(self.root,tool,'http://127.0.0.1:8888','team-test','user-test',kw.pop('connection_id','install-test'),token,probe=kw.pop('probe',lambda *a:{'bridge_verified':True,'plan_version':0}),**kw)

    def test_codex_preserves_model_and_all_other_settings(self):
        p=self.root/'.codex/config.toml';p.parent.mkdir();before='''# 用户原来的注释
model = "do-not-change-model"
model_provider = "do-not-change-provider"
[features]
keep = true
[mcp_servers.existing]
command = "existing-command"
''';p.write_text(before)
        r=self.install();after=tomllib.loads(p.read_text())
        self.assertEqual(after['model'],'do-not-change-model');self.assertEqual(after['model_provider'],'do-not-change-provider');self.assertTrue(after['features']['keep'])
        self.assertEqual(after['mcp_servers']['existing']['command'],'existing-command')
        self.assertIn('# 用户原来的注释',p.read_text());self.assertNotIn('sbconn_',p.read_text())
        self.assertTrue(r['bridge_verified']);self.assertFalse(r['client_loaded'])
        config=self.root/'.songban/connection.json';self.assertEqual(config.stat().st_mode&0o777,0o600)
        self.assertEqual(json.loads(config.read_text())['token'],'sbconn_only-a-test-connection')
        self.assertTrue((self.root/'.agents/skills/songban-team/SKILL.md').is_file())
        self.assertTrue((Path(r['backup_dir'])/'.codex/config.toml').is_file())

    def test_json_tools_merge_existing_servers(self):
        for tool,folder in [('cursor','.cursor'),('workbuddy','.workbuddy')]:
            with self.subTest(tool=tool):
                p=self.root/folder/'mcp.json';p.parent.mkdir();p.write_text(json.dumps({'mcpServers':{'keep':{'command':'keep-me'}},'other':True}))
                r=self.install(tool,connection_id='id-'+tool)
                data=json.loads(p.read_text());self.assertEqual(data['mcpServers']['keep']['command'],'keep-me');self.assertTrue(data['other'])
                self.assertIn('songban-team',data['mcpServers']);self.assertNotIn('sbconn_',p.read_text())

    def test_failure_restores_previous_config_and_removes_new_credentials(self):
        p=self.root/'.cursor/mcp.json';p.parent.mkdir();original='{"mcpServers":{"original":{"command":"keep"}}}';p.write_text(original)
        def fail(*a):raise InstallError('connection_check_failed','模拟网络失败',502)
        with self.assertRaises(InstallError):self.install('cursor',probe=fail)
        self.assertEqual(p.read_text(),original)
        self.assertFalse((self.root/'.songban/connection.json').exists())
        self.assertFalse((self.root/'.songban/install.lock').exists())

    def test_reinstall_only_replaces_our_managed_block(self):
        self.install();r=self.install(token='sbconn_new-test-connection',connection_id='new-install')
        p=self.root/'.codex/config.toml';self.assertEqual(p.read_text().count('[mcp_servers.songban-team]'),1)
        self.assertEqual(r['previous_connection_id'],'install-test')

    def test_existing_unrelated_named_connection_refused(self):
        p=self.root/'.cursor/mcp.json';p.parent.mkdir();before='{"mcpServers":{"songban-team":{"command":"not-ours"}}}';p.write_text(before)
        with self.assertRaises(InstallError):self.install('cursor')
        self.assertEqual(p.read_text(),before)

    def test_symlink_cannot_redirect_to_global_config(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            (self.root/'.codex').symlink_to(elsewhere,target_is_directory=True)
            with self.assertRaises(InstallError):self.install()
            self.assertFalse((Path(elsewhere)/'config.toml').exists())

    def test_backup_symlink_refused(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            d=self.root/'.songban';d.mkdir();(d/'install-backups').symlink_to(elsewhere,target_is_directory=True)
            with self.assertRaises(InstallError):self.install()
            self.assertEqual(list(Path(elsewhere).iterdir()),[])

    def test_invalid_config_not_overwritten(self):
        p=self.root/'.codex/config.toml';p.parent.mkdir();p.write_text('not [valid toml')
        with self.assertRaises(InstallError):self.install()
        self.assertEqual(p.read_text(),'not [valid toml')

    def test_other_member_cannot_replace_personal_connection(self):
        self.install()
        with self.assertRaises(InstallError):install_project(self.root,'codex','http://127.0.0.1:8888','team-test','another-user','other-id','sbconn_other-user',probe=lambda *a:{'bridge_verified':True})

    def test_home_root_not_accepted_as_project(self):
        with self.assertRaises(InstallError):project_path(str(Path.home()))

    def test_remote_and_cross_origin_cannot_trigger_installer(self):
        def req(ip='127.0.0.1',url='http://127.0.0.1:8886/',headers=None):return SimpleNamespace(client=SimpleNamespace(host=ip),url=url,headers=headers or {})
        self.assertTrue(is_local_request(req()))
        self.assertFalse(is_local_request(req(ip='192.168.1.8')))
        self.assertFalse(is_local_request(req(url='https://public.example.com/')))
        self.assertFalse(is_local_request(req(headers={'origin':'https://evil.example'})))
        self.assertFalse(is_local_request(req(headers={'x-forwarded-for':'127.0.0.1'})))
        self.assertFalse(is_local_request(req(headers={'sec-fetch-site':'cross-site'})))

if __name__=='__main__':unittest.main()
