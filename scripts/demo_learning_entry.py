"""Child-only entry for the explicitly marked synthetic unified demo.

Only run_demo registers this endpoint. It consumes an existing fixture learner
and permissions, creates no consent/enrollment, and issues no manager credential.
"""
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.learning_v2.protocol import Problem, fail, revision, strict_json
from scripts.serve_learning_preview import ACTORS, SCOPE


def register_demo_learning_entry(app, database, manifest, demo_people):
    service = getattr(app.state, 'learning_v2', None)
    if (service is None or manifest.get('synthetic') is not True
            or manifest.get('scope') != SCOPE or not service.settings.loopback_http
            or Path(manifest.get('database', '')).resolve() != Path(database).resolve()):
        raise ValueError('Demo learning entry requires the bound synthetic learning fixture')
    learner_id, family_id = manifest['learner_id'], manifest['family_id']
    actor_id = ACTORS[0][0]
    allowed_people = {item[0] for item in ACTORS} | set(demo_people)

    def validate_fixture(con):
        people = con.execute('SELECT id,phone_real,phone,username FROM people').fetchall()
        fixture_accounts = {item[0]: (item[1], item[2]) for item in ACTORS}
        if any(p['id'] not in allowed_people or
               (p['id'] in fixture_accounts and (p['username'], p['phone']) != fixture_accounts[p['id']]) or
               (p['id'] not in fixture_accounts and p['phone_real']) for p in people):
            fail(403, 'demo_fixture_required', '这个入口仅供隔离的虚构演示使用。')
        learner = con.execute('SELECT family_id FROM learn_learners WHERE id=?', (learner_id,)).fetchone()
        family = con.execute('SELECT owner_id FROM learn_families WHERE id=?', (family_id,)).fetchone()
        if not learner or learner['family_id'] != family_id or not family or family['owner_id'] != actor_id:
            fail(403, 'demo_fixture_required', '演示学习资料需要由维护人员检查。')

    with service.store.transaction() as con:
        validate_fixture(con)

    def start(request, body):
        with service.store.transaction() as con:
            service.transport(request)
            browser = service.browser(con, request)
            service.write_guard(con, request, browser)
            revision(body['browser_revision'], browser['epoch'])
            if not service.settings.enabled:
                fail(423, 'learning_paused', '学习体验暂未开放，已有记录仍会保留。')
            validate_fixture(con)
            service.learning_access(con, learner_id)
            session = None
            if request.cookies.get(service.cookie_name):
                try:
                    session = service.session_row(con, request, browser)
                except Problem as problem:
                    if problem.status != 401:
                        raise
            if session and (session['actor_id'] != actor_id or session['mode'] == 'staff'
                            or session['mode'] == 'learner' and session['learner_id'] != learner_id):
                fail(409, 'different_identity', '请先退出当前身份，再开始虚构学习体验。')
            if session and session['mode'] == 'learner':
                return JSONResponse(service.session_view(con, session), headers={'Cache-Control': 'no-store'})
            boundary = getattr(service, 'legacy_boundary', None)
            if boundary is not None:
                boundary.check_switch(con, actor_id=actor_id, browser_id=browser['id'])
            service.tombstone_legacy(con, actor_id)
            result, token = service.rotate(con, browser, actor_id, 'learner', learner_id)
            service.audit(con, actor_id, 'demo_learning_start', learner_id, {'synthetic': True})
        response = JSONResponse(result, headers={'Cache-Control': 'no-store'})
        response.set_cookie(service.cookie_name, token, max_age=service.settings.session_seconds,
                            path='/', secure=False, httponly=True, samesite='strict')
        return response

    @app.post('/api/demo/learning/start', include_in_schema=False)
    async def demo_learning_start(request: Request):
        try:
            if request.headers.get('content-type', '').split(';', 1)[0] != 'application/json':
                fail(422, 'invalid_input', '请使用 JSON 请求。')
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 4096:
                    fail(413, 'invalid_input', '请求内容过长。')
            body = strict_json(bytes(raw))
            if (not isinstance(body, dict) or set(body) != {'browser_revision', 'request_id'}
                    or type(body['browser_revision']) is not int or body['browser_revision'] < 0
                    or not isinstance(body['request_id'], str) or not 8 <= len(body['request_id']) <= 100):
                fail(422, 'invalid_input', '请求格式不正确。')
            return await run_in_threadpool(start, request, body)
        except Problem as problem:
            return JSONResponse(problem.payload(), status_code=problem.status, headers={'Cache-Control': 'no-store'})

    # This endpoint owns the same browser/CSRF/epoch checks as learning v2.
    # Register only this guarded endpoint, so it is not tracked as an unknown
    # legacy mutation that would block its own identity rotation.
    boundary = getattr(service, 'legacy_boundary', None)
    if boundary is not None:
        boundary.managed_prefixes = (*boundary.managed_prefixes, '/api/demo/learning/start')
