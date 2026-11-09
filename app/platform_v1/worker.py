"""Bounded background dispatch; refreshes never dispatch or retry paid jobs."""
import asyncio
from contextlib import asynccontextmanager
import logging
from starlette.concurrency import run_in_threadpool


def install_worker(api, service):
    original = api.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()

        async def run(domain):
            while not stop.is_set():
                try:
                    await run_in_threadpool(domain.worker_once)
                except Exception:
                    # Errors may carry provider or personal content: record only class-neutral status.
                    logging.getLogger(__name__).warning('Platform job worker needs inspection; persisted state retained')
                try:
                    await asyncio.wait_for(stop.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass

        async with original(app):
            tasks = [asyncio.create_task(run(d)) for d in (service.companion, service.images)]
            try:
                yield
            finally:
                stop.set()
                # Let an already dispatched request finish recording its result.
                await asyncio.gather(*tasks)

    api.router.lifespan_context = lifespan
