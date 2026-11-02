"""Offline checks of the explicit live-test transport: zero actual requests."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import httpx

spec = importlib.util.spec_from_file_location('learning_live_check', Path(__file__).resolve().parents[1]/'scripts/check_learning_studio_live.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class LiveCapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.calls = []
        self.transport = live.CappedTransport(self.directory, httpx.MockTransport(self.respond))
        self.addCleanup(self.transport.close)

    def respond(self, request):
        self.calls.append(request)
        return httpx.Response(200, json={'model': 'deepseek-flash'})

    def request(self, url='https://api.deepseek.com/chat/completions', tokens=800):
        return httpx.Request('POST', url, json={'model': 'deepseek-flash', 'max_tokens': tokens})

    def test_seventh_dispatch_is_refused_before_transport(self):
        for _ in range(6):
            self.transport.handle_request(self.request())
        with self.assertRaisesRegex(ValueError, 'cap'):
            self.transport.handle_request(self.request())
        self.assertEqual(len(self.calls), 6)
        self.assertEqual(len(json.loads(self.transport.counter.read_text())), 6)

    def test_unknown_request_is_counted_and_not_retried(self):
        def timeout(request):
            raise httpx.ReadTimeout('fake timeout', request=request)
        self.transport.inner = httpx.MockTransport(timeout)
        with self.assertRaises(httpx.ReadTimeout):
            self.transport.handle_request(self.request())
        rows = json.loads(self.transport.counter.read_text())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'dispatch_started')
        self.assertFalse((self.directory/'.dispatch-lock').exists())

    def test_origin_and_output_bound_are_checked_before_dispatch(self):
        for request in (self.request('https://other.example/chat/completions'), self.request(tokens=801), self.request('http://api.deepseek.com/chat/completions')):
            with self.assertRaises(ValueError):
                self.transport.handle_request(request)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.transport.counter.exists())

    def test_parallel_dispatch_cannot_overwrite_counter(self):
        (self.directory/'.dispatch-lock').touch()
        with self.assertRaises(FileExistsError):
            self.transport.handle_request(self.request())
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
