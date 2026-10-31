"""Local SMS configuration, using synthetic secrets and no provider requests."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import environment, sms
from scripts import apply_aliyun_access_key as setup_sms
from scripts import check_sms_config
from tests.platform_files import assert_private


CONFIG = {
    'ALIYUN_ACCESS_KEY_ID': 'synthetic-local-key',
    'ALIYUN_ACCESS_KEY_SECRET': r'synthetic\secret=with"quotes"',
    'ALIYUN_SMS_SIGN_NAME': '松伴验证码',
    'ALIYUN_SMS_TEMPLATE_CODE': 'synthetic-template',
}


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.path = self.root / '.env'
        self.env = patch.dict(os.environ, {}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        for name in environment.ENV_KEYS:
            os.environ.pop(name, None)

    def test_utf8_bom_chinese_sign_and_allowed_keys(self):
        self.path.write_text('\n'.join(f'{key}="{value}"' for key, value in CONFIG.items()) +
                             '\nALIYUN_SMS_MODE=pnvs\nUNRELATED_SECRET=ignored\n', encoding='utf-8-sig')
        environment.load_env(self.path)
        self.assertTrue(sms.cloud_sms_ready())
        for key, value in CONFIG.items():
            self.assertEqual(os.environ[key], value)
        self.assertNotIn('UNRELATED_SECRET', os.environ)

    def test_project_values_win_but_blank_entries_keep_deployment_values(self):
        os.environ.update(ALIYUN_ACCESS_KEY_ID='injected', ALIYUN_SMS_SIGN_NAME='outer', MODEL_NAME='outer-model')
        self.path.write_text('ALIYUN_ACCESS_KEY_ID=\nALIYUN_SMS_SIGN_NAME="松伴"\nMODEL_NAME=private-model\n', encoding='utf-8')
        environment.load_env(self.path, keys=environment.SMS_KEYS)
        self.assertEqual(os.environ['ALIYUN_ACCESS_KEY_ID'], 'injected')
        self.assertEqual(os.environ['ALIYUN_SMS_SIGN_NAME'], '松伴')
        self.assertEqual(os.environ['MODEL_NAME'], 'outer-model')

    def test_writer_creates_private_file_and_preserves_other_settings_on_update(self):
        setup_sms.write_sms_config(self.path, CONFIG)
        assert_private(self, self.path)
        original = self.path.read_text(encoding='utf-8')
        self.path.write_text(original + '\n# existing model\nMODEL_NAME=keep-me\nDATABASE_PATH=keep.sqlite3\n', encoding='utf-8-sig')
        changed = dict(CONFIG, ALIYUN_SMS_SIGN_NAME='更新的中文签名')
        setup_sms.write_sms_config(self.path, changed, mode='enterprise')
        assert_private(self, self.path)
        environment.load_env(self.path)
        self.assertEqual(os.environ['MODEL_NAME'], 'keep-me')
        self.assertEqual(os.environ['DATABASE_PATH'], 'keep.sqlite3')
        self.assertEqual(os.environ['ALIYUN_SMS_SIGN_NAME'], changed['ALIYUN_SMS_SIGN_NAME'])
        self.assertEqual(os.environ['ALIYUN_ACCESS_KEY_SECRET'], CONFIG['ALIYUN_ACCESS_KEY_SECRET'])
        self.assertTrue(sms.enterprise_sms_ready())
        self.assertFalse(sms.test_codes_allowed())
        self.assertFalse(sms.mac_sms_enabled())
        self.assertIn('# existing model', self.path.read_text(encoding='utf-8'))

    def test_incomplete_or_multiline_values_do_not_change_existing_configuration(self):
        self.path.write_text('MODEL_NAME=original\n', encoding='utf-8')
        before = self.path.read_bytes()
        for invalid in ('', 'value\nSONGBAI_ALLOW_TEST_CODES=1', 'value\x00'):
            with self.subTest(invalid=repr(invalid)), self.assertRaises(ValueError):
                setup_sms.write_sms_config(self.path, dict(CONFIG, ALIYUN_ACCESS_KEY_SECRET=invalid))
            self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.root.glob('.env-write-*')), [])

    def test_failed_replace_preserves_old_configuration_and_removes_temporary_secret(self):
        self.path.write_text('MODEL_NAME=original\n', encoding='utf-8')
        with patch('scripts.apply_aliyun_access_key.os.replace', side_effect=OSError('fixture failure')):
            with self.assertRaises(OSError):
                setup_sms.write_sms_config(self.path, CONFIG)
        self.assertEqual(self.path.read_text(encoding='utf-8'), 'MODEL_NAME=original\n')
        self.assertEqual(list(self.root.glob('.env-write-*')), [])

    def test_check_automatically_reads_project_file_without_exposing_values(self):
        setup_sms.write_sms_config(self.path, CONFIG)
        output = io.StringIO()
        with patch('app.environment.ROOT', self.root), patch('sys.argv', ['check_sms_config.py']), \
                patch('app.sms._signed_get') as request, contextlib.redirect_stdout(output):
            self.assertEqual(check_sms_config.main(), 0)
        request.assert_not_called()
        status = json.loads(output.getvalue())
        self.assertTrue(status['configured'])
        self.assertFalse(status['delivery_verified'])
        self.assertTrue(status['test_codes_disabled'])
        for value in CONFIG.values():
            self.assertNotIn(value, output.getvalue())

    def test_interactive_setup_collects_all_four_values_without_preexisting_file(self):
        output = io.StringIO()
        with patch('scripts.apply_aliyun_access_key.ROOT', self.root), \
                patch('sys.argv', ['apply_aliyun_access_key.py']), \
                patch('sys.stdin.isatty', return_value=True), \
                patch('getpass.getpass', side_effect=[CONFIG['ALIYUN_ACCESS_KEY_ID'], CONFIG['ALIYUN_ACCESS_KEY_SECRET']]), \
                patch('builtins.input', side_effect=[CONFIG['ALIYUN_SMS_SIGN_NAME'], CONFIG['ALIYUN_SMS_TEMPLATE_CODE']]), \
                contextlib.redirect_stdout(output):
            self.assertEqual(setup_sms.main(), 0)
        self.assertTrue(sms.cloud_sms_ready())
        for value in CONFIG.values():
            self.assertNotIn(value, output.getvalue())

    def test_setup_refuses_input_without_a_private_interactive_terminal(self):
        with patch('sys.argv', ['apply_aliyun_access_key.py']), \
                patch('sys.stdin.isatty', return_value=False), \
                patch('getpass.getpass') as prompt, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup_sms.main(), 1)
        prompt.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_missing_configuration_remains_unconfigured(self):
        output = io.StringIO()
        with patch('app.environment.ROOT', self.root), patch('sys.argv', ['check_sms_config.py']), \
                contextlib.redirect_stdout(output):
            self.assertEqual(check_sms_config.main(), 1)
        self.assertFalse(json.loads(output.getvalue())['configured'])
        self.assertFalse(self.path.exists())
