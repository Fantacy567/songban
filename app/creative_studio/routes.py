"""Shared platform transport plus a separate durable, bounded dispatch loop."""
import asyncio
import json
import re
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from app.learning_v2.protocol import Problem, fail
from contextlib import asynccontextmanager
from starlette.concurrency import run_in_threadpool
from app.platform_v1.routes import register_domain
from .service import StudioService
from .schemas import ROUTE_SPECS, REQUEST_SCHEMAS
from .preview import document, CSP

def register_studio(api, platform_service, settings_provider=None, runner=None):
    service=StudioService(platform_service,settings_provider,runner)
    service.migrate()
    api.state.creative_studio=service
    register_domain(api,platform_service,service,ROUTE_SPECS,REQUEST_SCHEMAS,{})
    @api.get('/api/platform/v1/studio/projects/{project_id}/preview/{version_id}/document')
    def preview_document(request: Request, project_id: str, version_id: str):
        headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff',
                 'Content-Security-Policy':"sandbox allow-scripts; "+CSP,
                 'Referrer-Policy':'no-referrer','Cross-Origin-Resource-Policy':'same-origin'}
        try:
            if request.query_params or not all(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',v) for v in (project_id,version_id)):
                fail(422,'invalid_preview','预览地址不正确。')
            if not request.cookies.get(service.learning.cookie_name):
                fail(401,'learning_session_required','请在学习身份中打开预览。')
            with service.store.transaction() as con:
                session,recheck=platform_service.identity(con,request,False)
                service.project(con,session,project_id)
                version=con.execute('SELECT files FROM creative_versions WHERE id=? AND project_id=?',(version_id,project_id)).fetchone()
                if not version: fail(404,'version_not_found','预览版本不存在。')
                content=document(json.loads(version[0])); recheck()
                response=HTMLResponse(content,headers=headers)
            return response
        except Problem as error:
            return JSONResponse(error.payload(),status_code=error.status,headers=headers)
    original=api.router.lifespan_context
    @asynccontextmanager
    async def lifespan(app):
        stop=asyncio.Event()
        async def work():
            while not stop.is_set():
                try: await run_in_threadpool(service.worker_once)
                except Exception:
                    # Persisted lease retains uncertainty; never retry the provider here.
                    import logging
                    logging.getLogger(__name__).warning('Studio worker requires inspection')
                try: await asyncio.wait_for(stop.wait(),timeout=1)
                except asyncio.TimeoutError: pass
        async with original(app):
            task=asyncio.create_task(work())
            try: yield
            finally:
                stop.set(); await task
    api.router.lifespan_context=lifespan
    return service
