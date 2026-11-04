"""Authenticated management API. The HTML contains only a sign-in gate."""
import json
from pathlib import Path
import sqlite3
import subprocess
from typing import Literal

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from starlette.concurrency import run_in_threadpool

from app.learning_v2.protocol import Problem, fail, strict_json
from .service import AdminService, AdminSettings

PREFIX = '/api/server-admin/v1'
HEADERS = {'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'}


class ConfigWrite(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: str = Field(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_.:-]+$')
    expected_revision: int = Field(ge=0)
    enabled: bool
    model: str = Field(max_length=150, pattern=r'^[A-Za-z0-9_.:/-]*$')
    max_calls: int = Field(ge=0, le=100000)
    max_output_tokens: int = Field(ge=128, le=4096)
    timeout_seconds: int = Field(ge=10, le=120)
    max_concurrency: int = Field(ge=1, le=8)
    api_key: str = Field(default='', max_length=4096)
    clear_key: bool = False
    size: Literal['2K', '4K'] = '2K'
    supports_sequential_generation: bool = True
    allowed_response_models: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def valid_secret(self):
        if self.api_key and (self.clear_key or self.api_key != self.api_key.strip() or any(ord(c)<33 or ord(c)>126 for c in self.api_key)):
            raise ValueError('invalid secret')
        import re
        if any(not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,150}', item) for item in self.allowed_response_models):
            raise ValueError('invalid response model')
        return self


class CloseUnknown(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    evidence: str = Field(min_length=10, max_length=3000)

    @model_validator(mode='after')
    def nonempty(self):
        if len(self.evidence.strip()) < 10:
            raise ValueError('Investigation evidence required')
        return self


def register_server_admin(api, learning_service, settings: AdminSettings):
    if getattr(api.state, 'server_admin', None) is not None:
        raise ValueError('Server admin already registered')
    service = AdminService(learning_service, settings, demo=bool(getattr(api.state, 'demo', False)))
    service.migrate()
    api.state.server_admin = service

    def perform(request, kind=None, body=None):
        if getattr(request.app.state, 'demo', False):
            fail(403, 'admin_required', '演示身份不能进入服务端管理后台。')
        with service.store.transaction() as con:
            actor, email, recheck = service.identity(con, request, body is not None)
            path = request.url.path
            job_kind = next((name for name in ('studio', 'workbench')
                             if path == PREFIX+'/'+name+'-jobs' or path.startswith(PREFIX+'/'+name+'-jobs/')), None)
            if job_kind is not None:
                domain = getattr(request.app.state, 'learning_workbench' if job_kind == 'workbench' else 'creative_studio', None)
                if domain is None:
                    fail(503, job_kind+'_unavailable', '课程工作台尚未注册。' if job_kind == 'workbench' else '创作服务尚未注册。')
                if body is not None:
                    job_id = request.path_params['job_id']
                    if job_kind == 'workbench':
                        row = con.execute('SELECT state FROM learning_workbench_jobs WHERE message_id=?', (job_id,)).fetchone()
                        if not row:
                            fail(404, 'message_not_found', '找不到待核对的消息。')
                        # Domain reconciliation is idempotent; HTTP duplicate closure
                        # must not create a second administrator audit or new evidence.
                        if row['state'] != 'unknown':
                            fail(409, 'job_not_unknown', '任务不在待核对状态。')
                    domain.close_unknown(job_id, evidence=body['evidence'], authority=actor, con=con)
                    result = {'id': job_id, 'state': 'failed', 'usage_refunded': False,
                              'notice': '已记录核对证据并关闭未知任务；额度保留，未重试，未认定成功。'}
                    con.execute('INSERT INTO server_admin_audit(actor_id,action,kind,revision,changed_fields,created_at) VALUES(?,?,?,?,?,?)',
                                (actor,'unknown_job_closed',job_kind+'_job',0,json.dumps(['job:'+job_id]),service.learning.stamp()))
                else:
                    query = ("SELECT message_id AS id,state,failure_code,created_at FROM learning_workbench_jobs WHERE state='unknown' ORDER BY created_at,message_id LIMIT 100"
                             if job_kind == 'workbench' else
                             "SELECT id,state,failure_code,created_at FROM creative_jobs WHERE state='unknown' ORDER BY created_at,id LIMIT 100")
                    result = {'items': [dict(row) for row in con.execute(query)]}
            elif body is not None:
                result = service.save(con, actor, kind, body)
            elif request.url.path.endswith('/audit'):
                result = {'items': [dict(id=row['id'], actor_id=row['actor_id'], action=row['action'], kind=row['kind'],
                                        revision=row['revision'], changed_fields=json.loads(row['changed_fields']), created_at=row['created_at'])
                                    for row in con.execute('SELECT * FROM server_admin_audit ORDER BY id DESC LIMIT 100')]}
            else:
                creative = getattr(request.app.state, 'creative_studio', None)
                result = {'administrator': {'email': email}, 'providers': {k: service.view(con, k) for k in ('text', 'image')},
                          'runtime': {'creative_studio_registered': creative is not None,
                                      'learning_workbench_registered': getattr(request.app.state, 'learning_workbench', None) is not None,
                                      'image_runtime_registered': service.image_base is not None,
                                      'image_consent_policy_configured': bool(service.image_base and service.image_base.image_consent_versions),
                                      'provider_verification': 'not_run',
                                      'notice': '配置检查不代表真实供应商调用成功。保存不会调用模型，也不会发布课程。'},
                          'teaching': {'publication_requires_review': True,
                                       'notice': '教学内容需要真实来源、学习目标、检查方式和人工审核；游戏进度不等于学习效果。'}}
            recheck()
            return JSONResponse(result, headers=HEADERS)

    async def endpoint(request: Request):
        try:
            service.learning.transport(request)
            if request.query_params:
                fail(422, 'invalid_query', '当前接口不接受查询参数。')
            body = None
            if request.method in ('PUT', 'POST'):
                if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
                    fail(415, 'json_required', '请使用管理页面提交配置。')
                # Check identity before accepting any sensitive payload.
                def authorize():
                    with service.store.transaction() as con:
                        service.identity(con, request, True)
                await run_in_threadpool(authorize)
                raw = bytearray()
                async for chunk in request.stream():
                    raw.extend(chunk)
                    if len(raw)>16384:
                        fail(413, 'request_too_large', '配置内容过长。')
                try:
                    model = CloseUnknown if request.method == 'POST' else ConfigWrite
                    body = model.model_validate(strict_json(raw)).model_dump()
                except ValidationError:
                    fail(422, 'invalid_input', '请核对模型名称、额度和运行范围。')
            return await run_in_threadpool(perform, request, request.path_params.get('kind'), body)
        except Problem as error:
            return JSONResponse(error.payload(), status_code=error.status, headers=HEADERS)
        except (sqlite3.OperationalError, OSError, subprocess.SubprocessError):
            return JSONResponse(Problem(503, 'configuration_unavailable', '配置暂时无法读取或保存，请重新读取后核对。', 'reload').payload(), status_code=503, headers=HEADERS)

    api.add_api_route(PREFIX+'/session', endpoint, methods=['GET'])
    api.add_api_route(PREFIX+'/audit', endpoint, methods=['GET'])
    api.add_api_route(PREFIX+'/providers/{kind}', endpoint, methods=['PUT'])
    api.add_api_route(PREFIX+'/studio-jobs', endpoint, methods=['GET'])
    api.add_api_route(PREFIX+'/studio-jobs/{job_id}/close-unknown', endpoint, methods=['POST'])
    api.add_api_route(PREFIX+'/workbench-jobs', endpoint, methods=['GET'])
    api.add_api_route(PREFIX+'/workbench-jobs/{job_id}/close-unknown', endpoint, methods=['POST'])

    @api.get('/server-admin', response_class=HTMLResponse)
    def admin_page():
        path = Path(__file__).resolve().parents[2] / 'static' / 'server-admin.html'
        return HTMLResponse(path.read_text(encoding='utf-8'), headers={**HEADERS,
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})

    return service
