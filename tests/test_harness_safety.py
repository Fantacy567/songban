# Copyright (c) 2026 2292576833. Joint project ownership: COPYRIGHT.md.
"""Host runner failure boundaries with process/HTTP doubles; no container claims."""
import io
import json
import subprocess
import unittest
from unittest.mock import Mock, patch

import httpx

from app.creative_studio.harness import HarnessRunner


class HarnessSafetyTests(unittest.TestCase):
    def payload(self):
        return dict(config={'model': 'synthetic', 'api_key': 'synthetic-private-token',
                            'max_output_tokens': 800, 'timeout_seconds': 10},
                    files=[], text='fixture', idea='', history=[], teaching='', curriculum={},
                    deadline_seconds=1, reserve_call=Mock(return_value='reserved'), record_call=Mock())

    def process(self, output):
        proc = Mock()
        proc.stdin = io.StringIO()
        proc.stdout = io.StringIO(output)
        proc.poll.return_value = None
        return proc

    def test_cleanup_failure_never_reports_completed_turn_as_success(self):
        output = json.dumps({'type': 'result', 'files': [], 'text': 'fixture', 'finish_reason': 'completed'})+'\n'
        for failure in (Mock(returncode=1), subprocess.TimeoutExpired('docker', 10), OSError('synthetic')):
            with self.subTest(failure=type(failure).__name__):
                proc = self.process(output)
                runner = HarnessRunner(docker='synthetic-docker')
                kwargs = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': failure}
                with patch.object(runner, 'available', return_value=True), patch('subprocess.Popen', return_value=proc), patch('subprocess.run', **kwargs):
                    with self.assertRaises((RuntimeError, subprocess.SubprocessError, OSError)):
                        runner(self.payload())
                proc.kill.assert_called_once()
                proc.wait.assert_called_once_with(timeout=10)
                self.assertTrue(proc.stdin.closed)
                self.assertTrue(proc.stdout.closed)

    def test_early_exit_cleans_up_and_never_reserves_a_model_call(self):
        proc = self.process('')
        runner, payload = HarnessRunner(docker='synthetic-docker'), self.payload()
        with patch.object(runner, 'available', return_value=True), patch('subprocess.Popen', return_value=proc), patch('subprocess.run', return_value=Mock(returncode=0)) as run:
            with self.assertRaisesRegex(RuntimeError, 'exited before a result'):
                runner(payload)
        self.assertEqual(run.call_args.args[0][:3], ['synthetic-docker', 'rm', '-f'])
        payload['reserve_call'].assert_not_called()

    def test_rejected_http_response_is_not_forwarded_or_recorded_as_success(self):
        for status in (301, 302, 307, 400, 401, 429, 500):
            with self.subTest(status=status):
                requests = []
                def provider(request):
                    requests.append(request)
                    return httpx.Response(status, text='synthetic-private-token',
                                          headers={'location': 'https://other.example.test'})
                runner = HarnessRunner(transport=httpx.MockTransport(provider))
                payload = self.payload()
                with self.assertRaisesRegex(RuntimeError, '^Provider did not complete$') as error:
                    runner.relay({'id': 'fixture', 'method': 'POST', 'path': '/chat/completions', 'body': {}}, payload)
                self.assertNotIn(payload['config']['api_key'], str(error.exception))
                self.assertEqual(len(requests), 1)
                payload['reserve_call'].assert_called_once()
                payload['record_call'].assert_not_called()


if __name__ == '__main__':
    unittest.main()
