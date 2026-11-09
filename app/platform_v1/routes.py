"""Platform route registration. Every private operation uses the shared epoch guard."""
import sqlite3
import re
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.learning_v2.protocol import Problem, fail, strict_json
from app.learning_v2.service import iso

PREFIX = '/api/platform/v1'


def register_domain(api, service, domain, specs, requests, responses):
    for method, path, op, status in specs:
        def factory(operation, result_status, response_schema):
            async def endpoint(request: Request):
                try:
                    service.learning.transport(request)
                    if any(not re.fullmatch(r'[A-Za-z0-9_.:@-]{1,150}', value) for value in request.path_params.values()):
                        fail(422, 'invalid_path', '记录地址格式不正确。')
                    body = {}
                    if request.method != 'GET':
                        if request.headers.get('content-type','').split(';',1)[0].strip().lower() != 'application/json':
                            fail(415, 'json_required', '请使用当前页面提交内容。')
                        raw = bytearray()
                        async for part in request.stream():
                            raw.extend(part)
                            if len(raw) > 65536:
                                fail(413, 'request_too_large', '内容太长，请缩短后重试。')
                        try:
                            body = requests[operation].model_validate(strict_json(raw)).model_dump()
                        except ValidationError:
                            fail(422, 'invalid_input', '请核对填写的内容和版本，必填信息不能留空。')
                    elif request.query_params:
                        fail(422, 'invalid_query', '当前列表不支持这个查询参数。')
                    return await run_in_threadpool(service.perform, domain, operation, request, body, result_status, response_schema,
                        response_factory=lambda result, code: JSONResponse(result, status_code=code, headers={'Cache-Control': 'no-store'}))
                except Problem as error:
                    return JSONResponse(error.payload(), status_code=error.status, headers={'Cache-Control': 'no-store'})
                except sqlite3.OperationalError:
                    error = Problem(503, 'storage_unavailable', '保存结果暂时无法确认，请读取原记录后再继续。', 'reload')
                    return JSONResponse(error.payload(), status_code=503, headers={'Cache-Control': 'no-store'})
            return endpoint
        api.add_api_route(PREFIX+path, factory(op, status, responses.get(op)), methods=[method], name='platform_'+op)


def register_platform(api, service):
    if getattr(api.state, 'platform_v1', None) is not None:
        raise ValueError('Platform already installed')
    api.state.platform_v1 = service
    service.migrate()
    from .portfolio import PortfolioService
    from .storage import migrate_portfolio
    from .schemas import ROUTE_SPECS, REQUEST_SCHEMAS, RESPONSE_SCHEMAS
    migrate_portfolio(service.store, iso(service.learning.clock()))
    service.portfolio = PortfolioService(service.learning)
    register_domain(api, service, service.portfolio, ROUTE_SPECS, REQUEST_SCHEMAS, RESPONSE_SCHEMAS)
    from . import companion, images
    service.companion = companion.CompanionService(service.store, service.learning, portfolio=service.portfolio,
                                                   settings=service.settings.companion_settings)
    service.companion.migrate()
    register_domain(api, service, service.companion, companion.ROUTE_SPECS, companion.REQUEST_SCHEMAS, companion.RESPONSE_SCHEMAS)
    service.images = images.ImageService(service.store, service.learning, service.portfolio, service.settings)
    service.images.migrate()
    register_domain(api, service, service.images, images.ROUTE_SPECS, images.REQUEST_SCHEMAS, images.RESPONSE_SCHEMAS)
    from .worker import install_worker
    install_worker(api, service)

    @api.get(PREFIX+'/assets/{asset_id}/content')
    def asset_content(request: Request, asset_id: str):
        headers = {'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
                   'Content-Security-Policy': "default-src 'none'; sandbox", 'Cross-Origin-Resource-Policy': 'same-origin'}
        try:
            if not re.fullmatch(r'[A-Za-z0-9_.:@-]{1,150}', asset_id) or request.query_params:
                fail(422, 'invalid_asset', '图片地址格式不正确。')
            with service.store.transaction() as con:
                session, recheck = service.identity(con, request, False)
                content, mime = service.images.asset_content(con, session, asset_id)
                recheck()
                response = Response(content, media_type=mime, headers=headers)
            return response
        except Problem as error:
            return JSONResponse(error.payload(), status_code=error.status, headers=headers)
        except sqlite3.OperationalError:
            return JSONResponse(Problem(503, 'storage_unavailable', '图片暂时未读取成功，请稍后再试。', 'reload').payload(), status_code=503, headers=headers)

    @api.get(PREFIX+'/config')
    def config(request: Request):
        try:
            service.learning.transport(request)
        except Problem as error:
            return JSONResponse(error.payload(), status_code=error.status, headers={'Cache-Control': 'no-store'})
        return JSONResponse({'version': service.version, 'enabled': service.settings.enabled,
                             'creative_studio_enabled': service.settings.creative_studio_enabled,
                             'navigation_enabled': service.settings.navigation_enabled,
                             'demo_mode': service.settings.demo_mode,
                             'image_provider': 'doubao', 'images_available': bool(service.images and service.images.available),
                             'image_modes': {'sample': service.images.sample_available, 'live': service.images.live_available},
                             'notice': '生成的图片会自动保存；作品公开与课程通过需要分别确认。'},
                            headers={'Cache-Control': 'no-store'})
