# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.learning_v2.protocol import Problem, fail
from app.platform_v1.routes import register_domain
from .schemas import REQUEST_SCHEMAS, ROUTE_SPECS
from .service import WorkbenchService
from .teachers import load_teachers, public_teacher


class Boundary:
    def __init__(self, platform):
        self.platform, self.learning = platform, platform.learning

    def perform(self, domain, op, request, *args, **kwargs):
        if request.query_params:
            fail(422, 'invalid_query', '工作台接口不支持身份或其他查询参数。')
        return self.platform.perform(domain, op, request, *args, **kwargs)


def register_workbench(api, platform_service, settings_provider=None, runner=None):
    if getattr(api.state, 'learning_workbench', None) is not None:
        raise ValueError('Learning workbench already registered')
    service = WorkbenchService(platform_service, settings_provider, runner)
    service.migrate()
    api.state.learning_workbench = service
    register_domain(api, Boundary(platform_service), service, ROUTE_SPECS, REQUEST_SCHEMAS, {})

    @api.get('/api/platform/v1/learning-workbench/teachers')
    def teacher_catalog(request: Request):
        headers = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}
        try:
            service.learning.transport(request)
            if str(request.base_url).rstrip('/') not in service.learning.settings.allowed_origins:
                fail(403, 'origin_rejected', '请求来源不受允许。')
            if request.headers.get('origin'):
                service.learning.origin(request)
            if request.query_params:
                fail(422, 'invalid_query', '老师列表不支持查询参数。')
            value = load_teachers()
            return JSONResponse({'version': value['version'], 'teachers': [public_teacher(t) for t in value['teachers']]}, headers=headers)
        except Problem as error:
            return JSONResponse(error.payload(), status_code=error.status, headers=headers)

    original = api.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()

        async def work():
            while not stop.is_set():
                try:
                    await run_in_threadpool(service.worker_once)
                except Exception:
                    # No user text, model body or credentials in operational logs.
                    logging.getLogger(__name__).warning('Learning workbench worker requires inspection; persisted state retained')
                try:
                    await asyncio.wait_for(stop.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass

        async with original(app):
            task = asyncio.create_task(work())
            try:
                yield
            finally:
                stop.set()
                await task

    api.router.lifespan_context = lifespan
    return service
