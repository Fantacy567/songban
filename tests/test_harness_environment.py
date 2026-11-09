# Copyright (c) 2026 2292576833. Joint project ownership: COPYRIGHT.md.
"""Deployment diagnosis never runs containers or emits engine secrets."""
import unittest
from unittest.mock import Mock, patch

from scripts import verify_harness_environment as diagnosis


class HarnessEnvironmentTests(unittest.TestCase):
    def test_missing_binary_and_unreachable_daemon_are_not_ready(self):
        self.assertFalse(diagnosis.inspect_engine(None)['image_ready'])
        with patch.object(diagnosis, 'probe', return_value=(1, 'private diagnostic')):
            report = diagnosis.inspect_engine('fake-docker')
        self.assertFalse(report['image_ready'])
        self.assertNotIn('private diagnostic', str(report))

    def test_pinned_linux_image_is_only_prerequisite_evidence(self):
        image = 'sha256:fixture|linux|'+diagnosis.REVISION+'|'+diagnosis.CONTRACT
        with patch.object(diagnosis, 'probe', side_effect=[(0, 'linux'), (0, image)]) as probe:
            report = diagnosis.inspect_engine('fake-docker')
        self.assertTrue(report['image_ready'])
        self.assertEqual([call.args[0][1] for call in probe.call_args_list], ['info', 'image'])
        self.assertNotIn('real_container', report)

    def test_old_contract_or_non_linux_image_is_not_ready(self):
        for image in ('sha256:fixture|linux|'+diagnosis.REVISION+'|old',
                      'sha256:fixture|windows|'+diagnosis.REVISION+'|'+diagnosis.CONTRACT):
            with patch.object(diagnosis, 'probe', side_effect=[(0, 'linux'), (0, image)]):
                self.assertFalse(diagnosis.inspect_engine('fake-docker')['image_ready'])

    def test_windows_wsl_output_is_decoded_without_shell(self):
        output = '尚未安装，请运行 wsl.exe --install'.encode('utf-16-le')
        with patch.object(diagnosis.subprocess, 'run', return_value=Mock(returncode=1, stdout=b'', stderr=output)) as run:
            code, text = diagnosis.probe(['wsl', '--status'])
        self.assertEqual(code, 1)
        self.assertIn('wsl.exe --install', text)
        self.assertNotIn('shell', run.call_args.kwargs)


if __name__ == '__main__':
    unittest.main()
