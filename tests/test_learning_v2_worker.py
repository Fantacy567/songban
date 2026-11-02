"""Lifecycle tests use a blocking synthetic worker, never a provider."""
import asyncio
import threading
import unittest
from types import SimpleNamespace
from fastapi import FastAPI

from app.learning_v2.worker import install_model_worker


class WorkerLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_waits_for_active_dispatch_and_does_not_redispatch(self):
        app = FastAPI()
        started, release = threading.Event(), threading.Event()
        calls = []
        def work(limit):
            calls.append(limit); started.set()
            self.assertTrue(release.wait(3))
        state = install_model_worker(app, SimpleNamespace(recover_model_jobs=lambda: None, process_model_jobs=work), poll_seconds=.01)
        lifecycle = app.router.lifespan_context(app)
        await lifecycle.__aenter__()
        self.assertTrue(await asyncio.to_thread(started.wait, 2))
        shutdown = asyncio.create_task(lifecycle.__aexit__(None, None, None))
        await asyncio.sleep(.02)
        self.assertFalse(shutdown.done())
        release.set()
        await asyncio.wait_for(shutdown, 3)
        self.assertEqual(calls, [1]); self.assertEqual(state['status'], 'stopped')

    async def test_unexpected_failure_stops_without_logging_sensitive_error(self):
        app = FastAPI()
        def fail():
            raise ValueError('private provider response must not be logged')
        state = install_model_worker(app, SimpleNamespace(recover_model_jobs=fail, process_model_jobs=lambda **_: self.fail('Must not dispatch')))
        with self.assertLogs('app.learning_v2.worker', level='ERROR') as logs:
            lifecycle = app.router.lifespan_context(app)
            await lifecycle.__aenter__()
            for _ in range(100):
                if state['status'] == 'failed':
                    break
                await asyncio.sleep(.01)
            await lifecycle.__aexit__(None, None, None)
        self.assertEqual(state['status'], 'failed')
        self.assertEqual(state['error_type'], 'ValueError')
        self.assertNotIn('private provider', ''.join(logs.output))
