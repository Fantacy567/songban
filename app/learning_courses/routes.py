# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
"""Register public content and private operations using platform identity/perform."""
import sqlite3

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.learning_v2.protocol import Problem, fail, strict_json
from app.platform_v1.routes import PREFIX, register_domain
from .catalog import load_catalog, load_course
from .schemas import Experiment, REQUEST_SCHEMAS, RESPONSE_SCHEMAS, ROUTE_SPECS
from .service import CoursesService, experiment_response

HEADERS = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}


def problem(error):
    return JSONResponse(error.payload(), status_code=error.status, headers=HEADERS)


class CourseBoundary:
    """Reject query identity hints also on POST, before the shared transaction."""
    def __init__(self, platform):
        self.platform, self.learning = platform, platform.learning

    def perform(self, domain, op, request, *args, **kwargs):
        if request.query_params:
            fail(422, 'invalid_query', '课程接口不支持这个查询参数。')
        return self.platform.perform(domain, op, request, *args, **kwargs)


def register_courses(api, platform_service):
    if getattr(api.state, 'learning_courses', None) is not None:
        raise ValueError('Learning courses already installed')
    service = CoursesService(platform_service)
    service.migrate()
    api.state.learning_courses = service
    register_domain(api, CourseBoundary(platform_service), service, ROUTE_SPECS, REQUEST_SCHEMAS, RESPONSE_SCHEMAS)

    def public(request, course_id=None):
        try:
            learning = service.learning
            learning.transport(request)
            # transport alone does not enforce HTTPS hosts or an optional
            # Origin header; the public catalog must enforce both as well.
            if str(request.base_url).rstrip('/') not in learning.settings.allowed_origins:
                fail(403, 'origin_rejected', '请求来源不受允许。')
            if request.headers.get('origin'):
                learning.origin(request)
            if not platform_service.settings.enabled:
                fail(423, 'platform_paused', '课程目录暂未开放，已保存记录仍可在原身份中查看。')
            if not learning.settings.enabled:
                fail(423, 'learning_paused', '课程目录暂未开放，已保存记录仍可在原身份中查看。')
            if request.query_params:
                fail(422, 'invalid_query', '课程目录不支持这个查询参数。')
            return JSONResponse(load_course(course_id) if course_id is not None else load_catalog(), headers=HEADERS)
        except Problem as error:
            return problem(error)

    @api.get(PREFIX+'/learning-catalog')
    def catalog(request: Request):
        return public(request)

    @api.get(PREFIX+'/learning-catalog/{course_id}')
    def course(request: Request, course_id: str):
        return public(request, course_id)

    @api.post(PREFIX+'/learning-courses/api/experiment')
    async def experiment(request: Request):
        # This small transport wrapper uses the same perform transaction as
        # register_domain, but reconstructs the response without persisting name.
        try:
            service.learning.transport(request)
            if request.query_params:
                fail(422, 'invalid_query', '教学接口不支持这个查询参数。')
            if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
                fail(415, 'json_required', '请使用当前页面提交内容。')
            raw = bytearray()
            async for part in request.stream():
                raw.extend(part)
                if len(raw) > 65536:
                    fail(413, 'request_too_large', '内容太长，请缩短后重试。')
            try:
                body = Experiment.model_validate(strict_json(raw)).model_dump()
            except ValidationError:
                fail(422, 'invalid_input', '请输入 1–40 个字符的名字，并使用 greet 操作。')
            return await run_in_threadpool(platform_service.perform, service, 'courseApiExperiment', request, body, 200, None,
                response_factory=lambda result, status: JSONResponse(experiment_response(body), status_code=status, headers=HEADERS))
        except Problem as error:
            return problem(error)
        except sqlite3.OperationalError:
            return problem(Problem(503, 'storage_unavailable', '实验结果暂时无法确认，请稍后重试。', 'reload'))

    return service
