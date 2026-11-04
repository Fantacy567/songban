"""Local deployment validation must not create users, files or paid requests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.run_studio_platform import load_admin, main
from scripts.run_learning import ConfigurationError


class StudioLauncherTests(unittest.TestCase):
    def test_empty_allowlist_is_valid_but_invalid_directory_is_not(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'admin.json'
            path.write_text(json.dumps({'allowed_emails':[], 'secret_dir':str(Path(folder)/'keys'), 'enabled':True}))
            self.assertEqual(load_admin(path).allowed_emails, ())
            path.write_text(json.dumps({'allowed_emails':['not an email'], 'secret_dir':str(Path(folder)/'keys'), 'enabled':True}))
            with self.assertRaises(ConfigurationError): load_admin(path)

    def test_check_never_opens_database_loads_private_env_or_calls_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'learning.json').write_text('{"schema_version":1,"settings":{"enabled":true}}')
            (root/'admin.json').write_text(json.dumps({'allowed_emails':['owner@example.test'], 'secret_dir':str(root/'keys'), 'enabled':True}))
            with patch('scripts.run_studio_platform.application', side_effect=AssertionError('must not create app')), \
                 patch('scripts.run_studio_platform.bind_local', side_effect=AssertionError('must not listen')), \
                 patch('app.environment.load_env', side_effect=AssertionError('must not read keys')):
                code=main(['--learning-config',str(root/'learning.json'),'--admin-config',str(root/'admin.json'),
                           '--database',str(root/'not-created.sqlite3'),'--origin','http://127.0.0.1:8894','--check'])
                self.assertEqual(code,0)
                self.assertFalse((root/'not-created.sqlite3').exists())
                self.assertFalse((root/'keys').exists())


if __name__ == '__main__': unittest.main()
