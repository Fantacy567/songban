"""App-owned dispatcher. Durable job/fence authority remains in ModelDomain."""
import asyncio
import logging
from contextlib import asynccontextmanager

from starlette.concurrency import run_in_threadpool


def install_model_worker(api, service, *, poll_seconds=1.0):
    if getattr(api.state, 'learning_model_worker', None) is not None:
        raise ValueError('Learning model worker already installed')
    state = {'status': 'stopped', 'error_type': None}
    api.state.learning_model_worker = state
    stop = asyncio.Event()
    task = None

    async def dispatch():
        state['status'] = 'running'
        try:
            while not stop.is_set():
                await run_in_threadpool(service.recover_model_jobs)
                if stop.is_set():
                    break
                await run_in_threadpool(service.process_model_jobs, limit=1)
                if not stop.is_set():
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
                    except asyncio.TimeoutError:
                        pass
        except Exception as exc:
            # Never put provider bodies, credentials or child inputs in runtime logs.
            state.update(status='failed', error_type=type(exc).__name__)
            logging.getLogger(__name__).error('Learning dispatcher stopped (%s); persisted jobs require recovery', type(exc).__name__)
        finally:
            if state['status'] != 'failed':
                state['status'] = 'stopped'

    async def start():
        nonlocal task
        if task is not None and not task.done():
            return
        stop.clear()
        task = asyncio.create_task(dispatch(), name='songban-learning-model-worker')

    async def shutdown():
        stop.set()
        if task is not None:
            # A request may already have reached the provider. Do not cancel and
            # relaunch it; await its bounded transport and durable settlement.
            await task

    previous_lifespan = api.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        async with previous_lifespan(app) as value:
            await start()
            try:
                yield value
            finally:
                await shutdown()

    api.router.lifespan_context = lifespan
    return state
