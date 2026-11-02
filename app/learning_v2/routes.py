"""Explicit FastAPI registration; frozen 0.2.1 resource responses, no envelopes."""
import json
import secrets
import sqlite3

from fastapi import Depends, Request
from fastapi.security import APIKeyCookie
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .auth import AuthFailure, password_actor
from .protocol import Problem, canonical, fail, revision, strict_json
from .service import digest, uid

PREFIX = "/api/learning/v2"
PUBLIC = {"bootstrap", "config", "consentText", "courses"}
TRANSITIONS = {"authenticate", "enterLearner", "logout"}
PAUSE_ALLOWED = {"authenticate", "logout", "revokeConsent", "claimCase", "resolveCase", "resolveReconciliation", "revokeReport"}


def register_learning_v2(api, service):
    """Register P1 routes only; call service.migrate() separately under S00 control."""
    if getattr(api.state, "learning_v2", None) is not None:
        raise ValueError("Learning v2 is already registered")
    api.state.learning_v2 = service

    def cookie(response, name, token, max_age):
        response.set_cookie(name, token, max_age=max_age, path="/", secure=not service.settings.loopback_http, httponly=True, samesite="strict")

    def cached(con, actor, scope, op, body, path):
        fingerprint = service.mac(con, canonical({"path": path, "body": body}))
        row = con.execute("SELECT * FROM learn_requests WHERE actor_id=? AND scope_id=? AND operation=? AND request_id=?", (actor, scope, op, body["request_id"])).fetchone()
        if row and not secrets.compare_digest(row["fingerprint"], fingerprint):
            fail(409, "idempotency_conflict", "该操作号已用于不同内容，请核对原操作。")
        return row, fingerprint

    def endpoint_for(op, spec):
        def perform(request, body, request_id):
            writing = request.method != "GET"
            status = next(int(s) for s in spec["responses"] if s.isdigit())
            set_session = set_browser = None
            clear_session = False
            with service.store.transaction() as con:
                if op == "config":
                    available = getattr(service, 'model_configuration_available', lambda _con: False)(con)
                    result = {"contract_version": "0.2.3", "learning_enabled": service.settings.enabled, "live_enabled": available, "publication_enabled": service.settings.publication_enabled and service.settings.reports_enabled,
                              "live_model_config_version": service.settings.model_settings.config_version if available else None,
                              "mock_enabled": service.settings.course_enabled and service.settings.mock_enabled,
                              "reports_enabled": service.settings.course_enabled and service.settings.reports_enabled,
                              "reports_readable": service.settings.course_enabled and service.settings.reports_enabled or con.execute("SELECT 1 FROM learn_course_objects WHERE kind='report' LIMIT 1").fetchone() is not None,
                              "age_band_options": list(service.settings.age_band_options), "consent_version": service.settings.consent_version,
                              "notice": "从你的兴趣和经历开始，每题都可以暂时跳过。已保存的回答可以回来调整。"}
                elif op == "consentText":
                    result = service.consent_text(con, request.path_params["consent_version"])
                elif op == "courses":
                    result = service.course_read(con, op, {"mode": "anonymous", "actor_id": "public"}, request.path_params, request.query_params)
                elif op == "bootstrap":
                    # Cross-site GET must not create/rotate a browser binding.
                    if request.headers.get("sec-fetch-site") == "cross-site" or (request.headers.get("origin") and request.headers["origin"] not in service.settings.allowed_origins):
                        fail(403, "origin_rejected", "请求来源不受允许。")
                    browser = service.browser(con, request, False)
                    if not browser:
                        # Unknown/stale session cookies never silently replace browser state.
                        if request.cookies.get(service.cookie_name):
                            fail(401, "session_revoked", "浏览器绑定已失效，请清除该站点会话后重新认证。", "reauthenticate")
                        token, bid = secrets.token_urlsafe(32), uid()
                        con.execute("INSERT INTO learn_browsers VALUES(?,?,0,'anonymous',?)", (bid, digest(token), service.clock()+service.settings.browser_seconds))
                        browser = con.execute("SELECT * FROM learn_browsers WHERE id=?", (bid,)).fetchone()
                        set_browser = token
                    result = {"csrf_token": service.csrf(con, browser), "browser_revision": browser["epoch"]}
                else:
                    browser = service.browser(con, request)
                    if writing:
                        service.write_guard(con, request, browser)
                    if op == "authenticate":
                        if body["method"] != "password":
                            fail(503, "authentication_method_unavailable", "本期只支持已有账号密码重新认证。", "contact_support")
                        actor, scope = browser["id"], browser["id"]
                        prior, fingerprint = cached(con, actor, scope, op, body, request.url.path)
                        if prior:
                            session = service.session_row(con, request, browser)
                            if session["id"] != prior["after_session"]:
                                fail(401, "session_revoked", "认证结果不能通过旧凭证重放。", "reauthenticate")
                            result = json.loads(prior["result"])
                        else:
                            revision(body["browser_revision"], browser["epoch"])
                            try:
                                person = password_actor(service, con, request, body["account"], body["proof"])
                            except AuthFailure:
                                con.commit()  # Only durable shared failure counters have changed.
                                raise
                            mode = "staff" if service.scopes(con, person) else "manager"
                            before = con.execute("SELECT id FROM learn_sessions WHERE browser_id=? AND epoch=?", (browser["id"], browser["epoch"])).fetchone()
                            result, set_session = service.rotate(con, browser, person, mode)
                            con.execute("INSERT INTO learn_requests VALUES(?,?,?,?,?,?,?,?,?)", (actor, scope, op, request_id, fingerprint, canonical(result), status, before[0] if before else None, result["id"]))
                            service.audit(con, person, op, result["id"])
                    else:
                        session = service.session_row(con, request, browser, ending=op == "logout")
                        if not writing:
                            result = service.read(con, op, session, request.path_params, request.query_params)
                        else:
                            if not service.settings.enabled and op not in PAUSE_ALLOWED:
                                fail(423, "learning_paused", "学习新写入暂未开放，已保存记录仍可读取。")
                            # Transitions are keyed by browser: only the resulting current
                            # session may replay a result, never its revoked predecessor.
                            actor = session["actor_id"]
                            scope = browser["id"] if op in TRANSITIONS else next(iter(request.path_params.values()), actor)
                            if op not in TRANSITIONS:
                                service.authorize_write(con, op, session, request.path_params, body)
                            prior, fingerprint = cached(con, actor, scope, op, body, request.url.path)
                            if prior:
                                if op in TRANSITIONS and prior["after_session"] != session["id"]:
                                    fail(401, "session_revoked", "身份切换不能通过旧凭证重放。", "reauthenticate")
                                result, status = json.loads(prior["result"]), prior["status"]
                            else:
                                service.authorize_write(con, op, session, request.path_params, body)
                                result, set_session = service.write(con, op, session, browser, request.path_params, body)
                                clear_session = op == "logout"
                                con.execute("INSERT INTO learn_requests VALUES(?,?,?,?,?,?,?,?,?)", (actor, scope, op, request_id, fingerprint, canonical(result), status, session["id"] if op in TRANSITIONS else None, result.get("id") if op in TRANSITIONS else None))
                                service.audit(con, actor, op, next(iter(request.path_params.values()), result.get("id", browser["id"])))
                        # All ordinary private responses are rechecked in the same short,
                        # write-locked transaction before response serialization.
                        if op not in TRANSITIONS:
                            service.session_row(con, request, browser)
                schema = spec["responses"][str(status)]["content"]["application/json"]["schema"]
                if not service.contract.valid(result, schema):
                    raise RuntimeError("Learning response failed frozen contract validation: " + op)
                response = JSONResponse(result, status_code=status)
            # Set-Cookie only after the transaction committed successfully.
            if set_browser:
                cookie(response, service.browser_cookie, set_browser, service.settings.browser_seconds)
            if set_session:
                cookie(response, service.cookie_name, set_session, service.settings.session_seconds)
            if clear_session:
                response.delete_cookie(service.cookie_name, path="/", secure=not service.settings.loopback_http, httponly=True, samesite="strict")
            return response

        async def endpoint(request: Request):
            request_id = uid()
            response = None
            try:
                service.transport(request)
                writing = request.method != "GET"
                body = None
                if writing:
                    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
                        fail(422, "invalid_input", "请使用 JSON 请求。")
                    raw = bytearray()
                    async for chunk in request.stream():
                        raw.extend(chunk)
                        if len(raw) > 131072:
                            fail(413, "invalid_input", "请求内容过长。")
                    body = strict_json(bytes(raw))
                    service.contract.check(body, spec["requestBody"]["content"]["application/json"]["schema"])
                    request_id = body["request_id"]
                allowed_query = {p["name"] for p in spec.get("parameters", []) if p["in"] == "query"}
                if any(k not in allowed_query for k in request.query_params) or len(request.query_params.multi_items()) != len(request.query_params):
                    fail(422, "invalid_input", "查询参数不受支持。")
                for key, value in request.path_params.items():
                    if not 1 <= len(value) <= 100:
                        fail(422, "invalid_input", "资源标识不正确。")
                response = await run_in_threadpool(perform, request, body, request_id)
            except Problem as exc:
                response = JSONResponse(exc.payload(), status_code=exc.status)
                if exc.status == 429:
                    response.headers["Retry-After"] = "300"
            except sqlite3.OperationalError:
                response = JSONResponse(Problem(503, "storage_unavailable", "保存服务暂不可用，请用原操作号核对。", "reload").payload(), status_code=503)
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Request-ID"] = request_id
            return response
        endpoint.__name__ = op
        return endpoint

    def expand_schema(value):
        if isinstance(value, dict):
            if "$ref" in value:
                return expand_schema(service.contract.schemas[value["$ref"].rsplit("/", 1)[-1]])
            return {k: expand_schema(v) for k, v in value.items()}
        if isinstance(value, list):
            return [expand_schema(v) for v in value]
        return value

    session_security = APIKeyCookie(name=service.cookie_name, scheme_name="LearningV2Session", auto_error=False)
    browser_security = APIKeyCookie(name=service.browser_cookie, scheme_name="LearningV2Browser", auto_error=False)
    for path, methods in service.contract.document["paths"].items():
        for method, spec in methods.items():
            op = spec["operationId"]
            # The service's contract projection already preserves authorized
            # historical reads when new course/model work is disabled.
            extra = expand_schema({k: v for k, v in spec.items() if k in ("parameters", "requestBody", "responses")})
            dependencies = [] if op in PUBLIC else [Depends(browser_security if op == "authenticate" else session_security)]
            status = next(int(s) for s in spec["responses"] if s.isdigit())
            api.add_api_route(PREFIX + path, endpoint_for(op, spec), methods=[method.upper()], operation_id=op,
                              summary=spec["summary"], status_code=status, dependencies=dependencies, openapi_extra=extra)

    async def unavailable(request: Request):
        problem = Problem(503, "operation_unavailable", "本期尚未实现该操作。", "contact_support")
        try:
            service.transport(request)
            with service.store.transaction() as con:
                browser = service.browser(con, request)
                if request.method != "GET":
                    service.write_guard(con, request, browser)
                service.session_row(con, request, browser)
        except Problem as exc:
            problem = exc
        return JSONResponse(problem.payload(), status_code=problem.status, headers={"Cache-Control": "no-store", "X-Request-ID": uid()})

    api.add_api_route(PREFIX + "/{unimplemented:path}", unavailable, methods=["GET", "POST", "PATCH", "PUT", "DELETE"], include_in_schema=False)
    return service
