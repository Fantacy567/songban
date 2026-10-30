import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.cors import CORSMiddleware

from .advice import advice_markdown, rubric_coverage, scope_advice
from .studio import ensure_schema, register_studio
from .team_core import ensure_core_schema, register_core
from .models import Draft, DraftUpdate, GenerateInput, ModelDiscovery, ModelSelection, ProjectInput, SourceInput, TaskAction, VersionInput
from .planner import PlannerError, builtin_model, discover_models, local_plan, model_configured, model_plan

ROOT = Path(__file__).resolve().parent.parent


def load_env():
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                key = name.strip()
                if key in {"DEEPSEEK_API_KEY", "MODEL_API_KEY", "MODEL_BASE_URL", "MODEL_NAME", "TEAM_MODEL_API_KEY", "TEAM_MODEL_BASE_URL", "TEAM_MODEL_NAME", "DASHSCOPE_API_KEY", "MODEL_ALLOWED_HOSTS", "ALLOWED_ORIGINS", "SONGBAN_CORE_ONLY", "DATABASE_PATH", "PUBLIC_BASE_URL", "WECHAT_APP_ID", "WECHAT_APP_SECRET", "SONGBAI_IMESSAGE", "SONGBAI_SMS", "SONGBAI_REQUIRE_SMS", "SONGBAI_ALLOW_TEST_CODES", "ALIYUN_ACCESS_KEY_ID", "ALIYUN_ACCESS_KEY_SECRET", "ALIYUN_SMS_SIGN_NAME", "ALIYUN_SMS_TEMPLATE_CODE", "ALIYUN_SMS_MODE"}:
                    cleaned = value.strip().strip("\"'")
                    # Project .env wins so local DeepSeek / 短信配置不被外层环境顶掉。
                    if cleaned:
                        os.environ[key] = cleaned
                    else:
                        os.environ.setdefault(key, "")


load_env()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def uid():
    return uuid.uuid4().hex


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


FALLBACK_REASONS = {
    "model_not_configured": "未配置模型密钥",
    "model_insufficient_balance": "模型账户余额不足",
    "model_auth_failed": "模型密钥无效或无权限",
    "model_rate_limited": "模型服务限流",
    "model_timeout": "模型请求超时",
    "model_busy": "模型正忙",
    "model_invalid_output": "模型输出未通过校验",
    "model_config_invalid": "模型配置不正确",
    "model_unavailable": "模型服务不可用",
}


class Problem(Exception):
    def __init__(self, status, code, message, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, deadline TEXT NOT NULL, created_at TEXT NOT NULL,
 context_version INTEGER NOT NULL DEFAULT 1, active_proposal_id TEXT, goal TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS members (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), name TEXT NOT NULL,
 role TEXT NOT NULL, skills TEXT NOT NULL, available_hours REAL NOT NULL CHECK(available_hours > 0),
 captain INTEGER NOT NULL DEFAULT 0, token_hash TEXT NOT NULL UNIQUE,
 UNIQUE(project_id, name)
);
CREATE INDEX IF NOT EXISTS members_project ON members(project_id);
CREATE TABLE IF NOT EXISTS sources (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), kind TEXT NOT NULL,
 title TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sources_project ON sources(project_id);
CREATE TABLE IF NOT EXISTS proposals (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), context_version INTEGER NOT NULL,
 version INTEGER NOT NULL DEFAULT 1, mode TEXT NOT NULL, content TEXT NOT NULL,
 created_at TEXT NOT NULL, confirmed_at TEXT
);
CREATE INDEX IF NOT EXISTS proposals_project ON proposals(project_id);
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), task_key TEXT NOT NULL,
 title TEXT NOT NULL, owner_id TEXT NOT NULL REFERENCES members(id), acceptance TEXT NOT NULL,
 estimated_hours REAL NOT NULL, priority TEXT NOT NULL, due_at TEXT NOT NULL,
 depends_on TEXT NOT NULL, evidence TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'todo',
 version INTEGER NOT NULL DEFAULT 1, deliverable TEXT NOT NULL DEFAULT '',
 block_reason TEXT NOT NULL DEFAULT '', review_note TEXT NOT NULL DEFAULT '',
 reviewed_by TEXT REFERENCES members(id), updated_at TEXT NOT NULL,
 UNIQUE(project_id, task_key)
);
CREATE INDEX IF NOT EXISTS tasks_project ON tasks(project_id);
CREATE TABLE IF NOT EXISTS events (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id),
 actor_id TEXT REFERENCES members(id), kind TEXT NOT NULL, entity_id TEXT NOT NULL,
 detail TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_project ON events(project_id, sequence);
"""


def create_app(db_path=None, model_runner=None, discovery_runner=None, core_only=None, core_model_runner=None):
    path = Path(db_path or os.environ.get("DATABASE_PATH") or ROOT / "data" / "collab.sqlite3")
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def db(write=False):
        con = sqlite3.connect(path, timeout=8)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=8000")
        try:
            if write:
                con.execute("BEGIN IMMEDIATE")
            else:
                con.execute("BEGIN")
            yield con
            if write:
                con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    initial = sqlite3.connect(path)
    try:
        initial.execute("PRAGMA journal_mode=WAL")
        initial.executescript(SCHEMA)
        ensure_schema(initial)
        ensure_core_schema(initial)
        initial.execute(
            """
            CREATE TABLE IF NOT EXISTS learning_sessions (
                id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'local_demo',
                state TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        initial.execute("CREATE INDEX IF NOT EXISTS learning_sessions_updated ON learning_sessions(updated_at)")
        columns = {row[1] for row in initial.execute("PRAGMA table_info(proposals)")}
        for column in ("model_id", "model_display_name", "response_model_id", "fallback_reason"):
            if column not in columns:
                initial.execute(f"ALTER TABLE proposals ADD COLUMN {column} TEXT")
        initial.commit()
    finally:
        initial.close()

    api = FastAPI(title="松伴 API", version="0.5.0", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    api.state.db_path = path
    api.state.core_only = (os.environ.get("SONGBAN_CORE_ONLY", "1") != "0") if core_only is None else core_only
    configured_origins = [s.strip() for s in os.environ.get("ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",") if s.strip()]
    if "*" in configured_origins:
        raise ValueError("ALLOWED_ORIGINS 必须列出明确地址，不允许星号")
    api.add_middleware(CORSMiddleware, allow_origins=configured_origins, allow_methods=["GET", "POST", "PUT", "PATCH"], allow_headers=["Authorization", "Content-Type"], allow_credentials=False)
    public_base_url = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if public_base_url and not public_base_url.startswith(("http://", "https://")):
        raise ValueError("PUBLIC_BASE_URL 必须以 http:// 或 https:// 开头")
    model_slots = threading.BoundedSemaphore(2)
    settings_lock = threading.Lock()
    custom_models, discoveries, model_versions = {}, {}, {}

    # The learning/experience flow is intentionally isolated from the team
    # collaboration tables. It uses its own JSON state table so the local
    # experience survives service restarts while the schema remains easy to
    # evolve into normalized learning-domain tables later.
    learning_lock = threading.Lock()
    learning_events = [
        {
            "id": "education-agent-weekend",
            "title": "教育 Agent 创作周末",
            "date": "11月7日—8日",
            "location": "上海杨浦",
            "summary": "教育主题，适合第一次参赛的你。",
            "why": "从一个真实学习问题出发，完成一次可演示的小作品。",
            "featured": True,
            "rules": "活动日期：2026年11月7日至8日。教育主题，支持1—3人组队。提交一个可运行的作品链接、简短项目说明，并完成3分钟展示。具体年龄资格、AI使用范围和提交时间请向主办方核实。",
        },
        {
            "id": "campus-ai-cocreate",
            "title": "校园 AI 共创营",
            "date": "11月14日—15日",
            "location": "上海徐汇",
            "summary": "从校园问题出发，可以结伴完成作品。",
            "why": "适合把日常观察整理成一个小而完整的校园工具。",
            "featured": False,
            "rules": "活动日期：2026年11月14日至15日。具体主题、组队和提交要求请向主办方核实。",
        },
        {
            "id": "open-learning-tools",
            "title": "开放学习工具挑战",
            "date": "11月21日—22日",
            "location": "上海浦东",
            "summary": "把学习中的小想法，变成可以展示的工具。",
            "why": "适合先完成一个可走通的学习工具流程。",
            "featured": False,
            "rules": "活动日期：2026年11月21日至22日。具体资格与提交要求请向主办方核实。",
        },
    ]

    def learning_session_snapshot(session):
        value = dict(session)
        value["onboarding"] = dict(session.get("onboarding") or {})
        value["team"] = dict(session.get("team") or {})
        value["idea"] = dict(session.get("idea") or {})
        value["direction"] = dict(session.get("direction") or {})
        value["delivery"] = dict(session.get("delivery") or {})
        value["review"] = dict(session.get("review") or {})
        value["tasks"] = [dict(task) for task in session.get("tasks", [])]
        return value

    def learning_seed_tasks():
        return [
            {
                "id": "sketch-first-flow",
                "title": "画出第一轮体验",
                "status": "in_progress",
                "deliverable": "三张相互连接的页面草图或链接。",
                "steps": [
                    "选一个具体问题，写下一句话目标",
                    "画出开始、互动、结果三个页面",
                    "把三页连接成可以顺着走的流程",
                ],
                "evidence": {},
            },
            {"id": "content-check", "title": "整理一个知识点", "status": "todo", "deliverable": "一段可核对的内容说明。", "steps": [], "evidence": {}},
            {"id": "demo-rehearsal", "title": "完成一次完整演示", "status": "todo", "deliverable": "一条可以顺着走的演示流程。", "steps": [], "evidence": {}},
            {"id": "peer-check", "title": "找一位同学试用", "status": "todo", "deliverable": "一条试用反馈记录。", "steps": [], "evidence": {}},
            {"id": "project-note", "title": "写下项目说明", "status": "todo", "deliverable": "简短项目说明。", "steps": [], "evidence": {}},
            {"id": "submission-list", "title": "对照活动要求核对提交清单", "status": "todo", "deliverable": "提交前核对结果。", "steps": [], "evidence": {}},
        ]

    def learning_persisted_snapshot(row):
        state = json.loads(row["state"])
        state.update({
            "id": row["id"],
            "mode": row["mode"],
            "role": row["role"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "revision": row["revision"],
        })
        return learning_session_snapshot(state)

    def selected_model(pid):
        with settings_lock:
            return dict(custom_models.get(pid) or builtin_model())

    def model_info(pid):
        config = selected_model(pid)
        with settings_lock:
            version = model_versions.get(pid, 0)
        return {"mode": config["mode"], "model_id": config["model_id"], "name": config["name"], "provider": config["provider"], "key_configured": bool(config["api_key"]), "version": version, "name_source": "服务模型列表" if config["mode"] == "custom" else "服务端预设，未据此证明实际模型版本", "custom_key_memory_only": config["mode"] == "custom"}

    @api.middleware("http")
    async def headers_and_size(request: Request, call_next):
        path = request.url.path
        if api.state.core_only:
            legacy = path in {"/classic", "/workflow", "/static/studio.html", "/static/index.html", "/static/workflow.html"} or path.startswith("/api/projects")
            old_studio = path.startswith("/api/studio/") and path not in {"/api/studio/login", "/api/studio/register", "/api/studio/codes"}
            if legacy or old_studio:
                return JSONResponse({"error": {"code": "feature_locked", "message": "本轮只开放个人智能体与团队统筹主线，其他功能暂时封锁。"}}, status_code=423)
        if request.method in {"POST", "PUT", "PATCH"}:
            limit = 2_000_000 if request.url.path == "/api/studio/contests/import-file" else 300_000
            try:
                if int(request.headers.get("content-length", "0")) > limit:
                    return JSONResponse({"error": {"code": "request_too_large", "message": "请求内容过长。"}}, status_code=413)
            except ValueError:
                return JSONResponse({"error": {"code": "invalid_length", "message": "请求长度不正确。"}}, status_code=400)
            if len(await request.body()) > limit:
                return JSONResponse({"error": {"code": "request_too_large", "message": "请求内容过长。"}}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://*.qlogo.cn https://*.qpic.cn; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'"
        return response

    @api.exception_handler(Problem)
    async def problem_handler(_request, exc):
        content = {"code": exc.code, "message": exc.message}
        if exc.details is not None:
            content["details"] = exc.details
        return JSONResponse({"error": content}, status_code=exc.status)

    @api.exception_handler(RequestValidationError)
    async def validation_handler(_request, exc):
        fields = [{"field": ".".join(map(str, e["loc"])), "reason": str(e["msg"])} for e in exc.errors()]
        return JSONResponse({"error": {"code": "validation_error", "message": "输入不符合要求，请检查标记字段。", "details": fields}}, status_code=422)

    @api.exception_handler(Exception)
    async def unexpected_handler(_request, _exc):
        return JSONResponse({"error": {"code": "internal_error", "message": "服务暂时无法处理，请刷新后重试。"}}, status_code=500)

    def project(con, pid):
        row = con.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            raise Problem(404, "not_found", "项目不存在。")
        return dict(row)

    def auth(con, pid, header, captain=False):
        if not header.startswith("Bearer ") or len(header) > 600:
            raise Problem(401, "unauthorized", "请使用本成员的有效入口打开项目。")
        member = con.execute("SELECT * FROM members WHERE project_id=? AND token_hash=?", (pid, digest(header[7:]))).fetchone()
        if not member:
            raise Problem(401, "unauthorized", "成员入口无效、已失效或不属于本项目。")
        member = dict(member)
        if captain and not member["captain"]:
            raise Problem(403, "captain_required", "此操作需要队长确认。")
        return member

    def event(con, pid, actor, kind, entity, detail):
        con.execute("INSERT INTO events(project_id,actor_id,kind,entity_id,detail,created_at) VALUES(?,?,?,?,?,?)", (pid, actor, kind, entity, detail, now()))

    def members(con, pid):
        return [dict(r) for r in con.execute("SELECT id,name,role,skills,available_hours,captain FROM members WHERE project_id=? ORDER BY rowid", (pid,))]

    def sources(con, pid):
        return [dict(r) for r in con.execute("SELECT * FROM sources WHERE project_id=? ORDER BY rowid", (pid,))]

    def tasks(con, pid):
        result = []
        for r in con.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY rowid", (pid,)):
            item = dict(r)
            item["depends_on"] = json.loads(item["depends_on"])
            item["evidence"] = json.loads(item["evidence"])
            result.append(item)
        return result

    def proposal(row):
        value = dict(row)
        value["content"] = json.loads(value["content"])
        offline = "离线规则引擎 · 按讨论中的任务行与角色提取，非大模型"
        if value.get("fallback_reason"):
            offline = f"离线规则引擎（{value['fallback_reason']}，已自动回退）· 非大模型"
        value["source_label"] = offline if value["mode"] == "local_rules" else "模型生成建议 · " + (value.get("model_display_name") or value.get("model_id") or "未记录模型名") + " · " + (value.get("model_id") or "未知 ID") + " · 待人工核对"
        return value

    def draft_row(con, pid, did):
        row = con.execute("SELECT * FROM proposals WHERE id=? AND project_id=?", (did, pid)).fetchone()
        if not row:
            raise Problem(404, "not_found", "草案不存在。")
        return row

    def version_matches(row, expected):
        if row["version"] != expected:
            raise Problem(409, "version_conflict", "另一位成员或另一窗口已经更新，请刷新并核对后重试。", {"current_version": row["version"]})

    def preparing(p):
        if p["active_proposal_id"]:
            raise Problem(409, "plan_locked", "正式方案已确认。首版执行后冻结资料与分工，可通过阻塞和验收退回处理问题。")

    def validate_draft(con, p, content, budget=False):
        people = {m["id"]: m for m in members(con, p["id"])}
        texts = {s["id"]: s["body"] for s in sources(con, p["id"])}
        keys = [t.key for t in content.tasks]
        if len(set(keys)) != len(keys):
            raise Problem(422, "duplicate_task_key", "任务编号不可重复。")
        if not any(t.priority == "must" for t in content.tasks):
            raise Problem(422, "must_task_required", "至少需要一项必须任务。")
        graph, totals = {}, {m: 0.0 for m in people}
        deadline = datetime.fromisoformat(p["deadline"])
        for task in content.tasks:
            if task.owner_id not in people:
                raise Problem(422, "invalid_owner", "任务负责人必须属于本项目。")
            if task.due_at > deadline:
                raise Problem(422, "invalid_due_date", "任务截止不可晚于赛事截止。")
            if len(set(task.depends_on)) != len(task.depends_on) or any(k not in keys or k == task.key for k in task.depends_on):
                raise Problem(422, "invalid_dependency", "任务依赖重复、不存在或指向自身。")
            for ref in task.evidence:
                if ref.source_id not in texts or ref.quote not in texts[ref.source_id]:
                    raise Problem(422, "invalid_evidence", "来源引用必须是本项目原文中的连续文字。")
            graph[task.key] = task.depends_on
            totals[task.owner_id] += task.estimated_hours
        done, active = set(), set()

        def visit(key):
            if key in active:
                raise Problem(422, "dependency_cycle", "任务依赖形成循环，请调整后再保存。")
            if key in done:
                return
            active.add(key)
            for dep in graph[key]:
                visit(dep)
            active.remove(key)
            done.add(key)

        for key in keys:
            visit(key)
        over = [{"member": people[k]["name"], "planned_hours": round(v, 2), "available_hours": people[k]["available_hours"]} for k, v in totals.items() if v > people[k]["available_hours"] + 1e-8]
        if budget and over:
            raise Problem(422, "capacity_exceeded", "任务估时超过成员可用工时，请缩减任务或调整估时。", over)
        return over

    def phase(p, items):
        if not p["active_proposal_id"]:
            return "preparing"
        required = [t for t in items if t["priority"] == "must"]
        return "ready" if required and all(t["status"] == "accepted" for t in required) else "executing"

    @api.get("/health")
    def health():
        try:
            with db() as con:
                con.execute("SELECT 1 FROM projects LIMIT 1").fetchone()
        except sqlite3.Error:
            raise Problem(503, "database_unavailable", "数据库暂不可用。") from None
        return {"status": "ok", "service": "hackathon-collab", "version": "0.9.2" if api.state.core_only else "0.5.0", "model_configured": bool(model_configured()), "core_only": api.state.core_only}

    @api.post("/api/projects", status_code=201)
    def create_project(body: ProjectInput):
        pid, created, invites = uid(), now(), []
        with db(True) as con:
            con.execute("INSERT INTO projects(id,name,deadline,created_at) VALUES(?,?,?,?)", (pid, body.name, body.deadline.isoformat(), created))
            for i, m in enumerate(body.members):
                mid, token = uid(), secrets.token_urlsafe(32)
                con.execute("INSERT INTO members(id,project_id,name,role,skills,available_hours,captain,token_hash) VALUES(?,?,?,?,?,?,?,?)", (mid, pid, m.name, m.role, m.skills, m.available_hours, int(i == 0), digest(token)))
                invites.append({"member_id": mid, "name": m.name, "captain": i == 0, "access_token": token})
            event(con, pid, invites[0]["member_id"], "project_created", pid, "创建项目与成员；首位成员为队长。")
        return {"project_id": pid, "invites": invites, "notice": "入口包含成员访问口令，请分别私下保存；普通成员入口可由队长重发。"}

    @api.get("/api/projects/{pid}")
    def get_workspace(pid: str, authorization: str = Header(default="")):
        with db() as con:
            me = auth(con, pid, authorization)
            p = project(con, pid)
            items = tasks(con, pid)
            drafts = [proposal(r) for r in con.execute("SELECT * FROM proposals WHERE project_id=? ORDER BY rowid DESC LIMIT 10", (pid,))]
            if p["active_proposal_id"] and not any(d["id"] == p["active_proposal_id"] for d in drafts):
                drafts.append(proposal(draft_row(con, pid, p["active_proposal_id"])))
            for draft in drafts:
                draft["stale"] = draft["context_version"] != p["context_version"]
                draft["capacity_warnings"] = validate_draft(con, p, Draft.model_validate(draft["content"]))
            events = [dict(r) for r in con.execute("SELECT * FROM (SELECT * FROM events WHERE project_id=? ORDER BY sequence DESC LIMIT 200) ORDER BY sequence", (pid,))]
            info = model_info(pid)
            return {"project": {**p, "phase": phase(p, items)}, "me": {k: v for k, v in me.items() if k != "token_hash"}, "members": members(con, pid), "sources": sources(con, pid), "proposals": drafts, "tasks": items, "events": events, "model_configured": info["key_configured"], "current_model": info, "public_base_url": public_base_url, "scope": scope_advice(p["deadline"], now(), items)}

    @api.get("/api/projects/{pid}/pulse")
    def pulse(pid: str, authorization: str = Header(default="")):
        with db() as con:
            auth(con, pid, authorization)
            last = con.execute("SELECT COALESCE(MAX(sequence),0) FROM events WHERE project_id=?", (pid,)).fetchone()[0]
            return {"last_event": last, "model_version": model_versions.get(pid, 0)}

    @api.post("/api/projects/{pid}/model/discover")
    def model_discover(pid: str, body: ModelDiscovery, authorization: str = Header(default="")):
        with db() as con:
            auth(con, pid, authorization, captain=True)
        if not model_slots.acquire(blocking=False):
            raise Problem(429, "model_busy", "服务正在读取其他模型，请稍后重试。")
        try:
            found = (discovery_runner or discover_models)(body.base_url, body.api_key.get_secret_value())
        except PlannerError as exc:
            raise Problem(exc.status, exc.code, exc.message) from None
        finally:
            model_slots.release()
        ticket = secrets.token_urlsafe(24)
        with settings_lock:
            discoveries[pid] = {"id": ticket, "expires": time.monotonic() + 600, "api_key": body.api_key.get_secret_value(), **found}
        return {"discovery_id": ticket, "models": found["models"], "provider": found["provider"], "expires_in_seconds": 600, "notice": "名称和完整 ID 来自服务商模型列表；同一密钥可能可用多个模型。密钥仅暂存本次服务内存，不回显、不落盘。"}

    @api.put("/api/projects/{pid}/model")
    def model_select(pid: str, body: ModelSelection, authorization: str = Header(default="")):
        with db(True) as con:
            me = auth(con, pid, authorization, captain=True)
            with settings_lock:
                if body.expected_version != model_versions.get(pid, 0):
                    raise Problem(409, "model_version_conflict", "模型设置已被另一窗口修改，请刷新后重试。")
                if body.mode == "builtin":
                    custom_models.pop(pid, None)
                    discoveries.pop(pid, None)
                else:
                    found = discoveries.get(pid)
                    if not found or found["expires"] < time.monotonic() or not secrets.compare_digest(found["id"], body.discovery_id or ""):
                        discoveries.pop(pid, None)
                        raise Problem(409, "model_discovery_expired", "模型列表已失效，请重新输入密钥并读取。")
                    model = next((m for m in found["models"] if m["id"] == body.model_id), None)
                    if not model:
                        raise Problem(422, "model_not_in_list", "请选择当前密钥读取到的完整模型 ID，不能自行伪造名称。")
                    custom_models[pid] = {"mode": "custom", "api_key": found["api_key"], "base_url": found["base_url"], "provider": found["provider"], "model_id": model["id"], "name": model["name"]}
                    discoveries.pop(pid, None)
                model_versions[pid] = body.expected_version + 1
            event(con, pid, me["id"], "model_selected", pid, "更新模型选择；密钥不写入记录。")
        return model_info(pid)

    @api.post("/api/projects/{pid}/members/{mid}/rotate-token")
    def rotate_member(pid: str, mid: str, authorization: str = Header(default="")):
        with db(True) as con:
            me = auth(con, pid, authorization, captain=True)
            row = con.execute("SELECT id,captain,name FROM members WHERE id=? AND project_id=?", (mid, pid)).fetchone()
            if not row:
                raise Problem(404, "not_found", "成员不存在。")
            if row["captain"]:
                raise Problem(422, "captain_entry_fixed", "请保存队长原入口；首版不支持队长入口重发。")
            token = secrets.token_urlsafe(32)
            con.execute("UPDATE members SET token_hash=? WHERE id=?", (digest(token), mid))
            event(con, pid, me["id"], "member_entry_rotated", mid, "重发成员入口，旧入口已失效。")
        return {"member_id": mid, "name": row["name"], "access_token": token}

    @api.post("/api/projects/{pid}/sources", status_code=201)
    def add_source(pid: str, body: SourceInput, authorization: str = Header(default="")):
        with db(True) as con:
            me = auth(con, pid, authorization)
            p = project(con, pid)
            preparing(p)
            size = con.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(body)),0) FROM sources WHERE project_id=?", (pid,)).fetchone()
            if size[0] >= 12 or size[1] + len(body.body) > 60000:
                raise Problem(422, "source_limit", "首版每项目最多 12 份原文、合计 6 万字，请精简内容。")
            item = {"id": uid(), "project_id": pid, **body.model_dump(), "created_at": now()}
            con.execute("INSERT INTO sources(id,project_id,kind,title,body,created_at) VALUES(:id,:project_id,:kind,:title,:body,:created_at)", item)
            con.execute("UPDATE projects SET context_version=context_version+1 WHERE id=?", (pid,))
            event(con, pid, me["id"], "source_added", item["id"], f"添加{body.title}；此前草案需重新生成。")
        return item

    @api.post("/api/projects/{pid}/proposals", status_code=201)
    def generate(pid: str, body: GenerateInput, authorization: str = Header(default="")):
        with db() as con:
            me = auth(con, pid, authorization, captain=True)
            p = project(con, pid)
            preparing(p)
            originals = sources(con, pid)
            if not {"rules", "discussion"}.issubset({s["kind"] for s in originals}):
                raise Problem(422, "sources_required", "请至少录入一份赛事规则和一份讨论记录。")
            context = {"project": {"name": p["name"], "deadline": p["deadline"]}, "members": members(con, pid), "sources": originals, "now": now()}
        config = selected_model(pid)
        mode, raw, content, fallback = body.mode, None, None, None
        if mode == "auto":
            mode = "model" if (model_runner or config["api_key"]) else "local_rules"
            if mode == "local_rules":
                fallback = FALLBACK_REASONS["model_not_configured"]
        acquired = False
        try:
            if mode == "model":
                acquired = model_slots.acquire(blocking=False)
                if not acquired:
                    raise Problem(429, "model_busy", "服务正在生成其他方案，请稍后重试。")
                raw = model_runner(context) if model_runner else model_plan(context, config=config)
            else:
                raw = local_plan(context)
            content = Draft.model_validate(raw)
        except (PlannerError, Problem, ValidationError) as exc:
            code = getattr(exc, "code", "model_invalid_output")
            if body.mode != "auto":
                if isinstance(exc, PlannerError):
                    raise Problem(exc.status, exc.code, exc.message) from None
                if isinstance(exc, Problem):
                    raise
                raise Problem(502, "model_invalid_output", "生成结果不符合任务结构，未创建正式任务。") from None
            fallback = FALLBACK_REASONS.get(code, FALLBACK_REASONS["model_unavailable"])
        finally:
            if acquired:
                model_slots.release()
        with db(True) as con:
            current = project(con, pid)
            preparing(current)
            if current["context_version"] != p["context_version"]:
                raise Problem(409, "context_changed", "生成期间资料有更新，请重新生成以使用最新资料。")
            warnings = None
            if content is not None:
                try:
                    warnings = validate_draft(con, current, content, budget=mode == "model")
                except Problem as exc:
                    if mode != "model":
                        raise exc
                    if body.mode != "auto":
                        raise Problem(502, "model_invalid_output", "模型方案的引用、成员、工时或依赖未通过校验，请重新生成。") from None
                    fallback = FALLBACK_REASONS["model_invalid_output"]
            if content is None and mode != "model":
                raise Problem(502, "plan_invalid_output", "离线规则未能生成有效方案，请检查原文后重试。")
            if fallback and mode == "model":
                mode, raw = "local_rules", local_plan(context)
                content = Draft.model_validate(raw)
                warnings = validate_draft(con, current, content)
            used_model = mode == "model"
            did = uid()
            con.execute("INSERT INTO proposals(id,project_id,context_version,mode,content,created_at,model_id,model_display_name,response_model_id,fallback_reason) VALUES(?,?,?,?,?,?,?,?,?,?)", (did, pid, p["context_version"], mode, content.model_dump_json(), now(), config["model_id"] if used_model else None, config["name"] if used_model else None, getattr(raw, "response_model_id", None), fallback))
            event(con, pid, me["id"], "proposal_generated", did, "生成模型建议草案，尚未确认。" if used_model else f"{fallback}，已改用离线规则引擎生成草案。" if fallback else "生成离线规则草案。")
            result = proposal(draft_row(con, pid, did))
            result.update(stale=False, capacity_warnings=warnings)
        return result

    @api.put("/api/projects/{pid}/proposals/{did}")
    def edit_draft(pid: str, did: str, body: DraftUpdate, authorization: str = Header(default="")):
        with db(True) as con:
            me = auth(con, pid, authorization, captain=True)
            p = project(con, pid)
            preparing(p)
            row = draft_row(con, pid, did)
            version_matches(row, body.expected_version)
            if row["context_version"] != p["context_version"]:
                raise Problem(409, "stale_proposal", "草案引用的资料已更新，请重新生成。")
            validate_draft(con, p, body.content)
            con.execute("UPDATE proposals SET content=?, version=version+1 WHERE id=?", (body.content.model_dump_json(), did))
            event(con, pid, me["id"], "proposal_edited", did, "队长修改待确认方案。")
            return proposal(draft_row(con, pid, did))

    @api.post("/api/projects/{pid}/proposals/{did}/confirm")
    def confirm(pid: str, did: str, body: VersionInput, authorization: str = Header(default="")):
        with db(True) as con:
            me = auth(con, pid, authorization, captain=True)
            p = project(con, pid)
            preparing(p)
            row = draft_row(con, pid, did)
            version_matches(row, body.expected_version)
            if row["context_version"] != p["context_version"]:
                raise Problem(409, "stale_proposal", "草案引用的资料已更新，请重新生成。")
            content = Draft.model_validate_json(row["content"])
            validate_draft(con, p, content, budget=True)
            key_ids = {t.key: uid() for t in content.tasks}
            for task in content.tasks:
                con.execute("INSERT INTO tasks(id,project_id,task_key,title,owner_id,acceptance,estimated_hours,priority,due_at,depends_on,evidence,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (key_ids[task.key], pid, task.key, task.title, task.owner_id, task.acceptance, task.estimated_hours, task.priority, task.due_at.isoformat(), encode([key_ids[k] for k in task.depends_on]), encode([e.model_dump() for e in task.evidence]), now()))
            con.execute("UPDATE projects SET active_proposal_id=?,goal=? WHERE id=?", (did, content.goal, pid))
            con.execute("UPDATE proposals SET confirmed_at=?,version=version+1 WHERE id=?", (now(), did))
            event(con, pid, me["id"], "proposal_confirmed", did, f"确认目标与 {len(content.tasks)} 项任务；开始执行。")
            return {"project_id": pid, "phase": "executing", "tasks": tasks(con, pid)}

    @api.post("/api/projects/{pid}/tasks/{tid}/actions")
    def act(pid: str, tid: str, body: TaskAction, authorization: str = Header(default="")):
        with db(True) as con:
            me = auth(con, pid, authorization)
            row = con.execute("SELECT * FROM tasks WHERE id=? AND project_id=?", (tid, pid)).fetchone()
            if not row:
                raise Problem(404, "not_found", "任务不存在。")
            version_matches(row, body.expected_version)
            own = row["owner_id"] == me["id"]
            if body.action in {"start", "block", "resume", "submit"} and not own:
                raise Problem(403, "owner_required", "只有负责人能更新此任务的执行情况。")
            if body.action in {"accept", "return"} and own:
                raise Problem(403, "self_review_forbidden", "请由另一位成员验收，不能自行通过或退回。")
            transitions = {"start": ("todo", "in_progress"), "block": ("in_progress", "blocked"), "resume": ("blocked", "in_progress"), "submit": ("in_progress", "review"), "accept": ("review", "accepted"), "return": ("review", "in_progress")}
            before, after = transitions[body.action]
            if row["status"] != before:
                raise Problem(409, "invalid_transition", "当前状态不能执行此操作，请刷新任务。")
            if body.action in {"block", "submit", "return"} and not body.note:
                raise Problem(422, "note_required", "请填写阻塞原因、成果说明或退回原因。")
            if body.action in {"start", "resume"}:
                dependencies = json.loads(row["depends_on"])
                accepted = {t["id"] for t in tasks(con, pid) if t["status"] == "accepted"}
                if any(dep not in accepted for dep in dependencies):
                    raise Problem(409, "dependencies_pending", "前置任务还没有通过验收，请先完成依赖。")
            deliverable = body.note if body.action == "submit" else row["deliverable"]
            block_reason = body.note if body.action == "block" else ("" if body.action == "resume" else row["block_reason"])
            review_note = body.note if body.action in {"accept", "return"} else row["review_note"]
            reviewed_by = me["id"] if body.action in {"accept", "return"} else row["reviewed_by"]
            con.execute("UPDATE tasks SET status=?, version=version+1, deliverable=?,block_reason=?,review_note=?,reviewed_by=?,updated_at=? WHERE id=?", (after, deliverable, block_reason, review_note, reviewed_by, now(), tid))
            labels = {"start": "开始", "block": "阻塞", "resume": "恢复", "submit": "提交成果", "accept": "验收通过", "return": "退回"}
            event(con, pid, me["id"], "task_" + body.action, tid, f"{labels[body.action]}：{row['title']}" + (f"；{body.note}" if body.note else ""))
            result = next(t for t in tasks(con, pid) if t["id"] == tid)
            return {"task": result, "phase": phase(project(con, pid), tasks(con, pid))}

    def recap(con, pid):
        p, items = project(con, pid), tasks(con, pid)
        events = [dict(r) for r in con.execute("SELECT * FROM events WHERE project_id=? ORDER BY sequence", (pid,))]
        stats = {"total": len(items), "accepted": sum(t["status"] == "accepted" for t in items), "must_total": sum(t["priority"] == "must" for t in items), "must_accepted": sum(t["priority"] == "must" and t["status"] == "accepted" for t in items), "block_events": sum(e["kind"] == "task_block" for e in events), "return_events": sum(e["kind"] == "task_return" for e in events)}
        ready = phase(p, items) == "ready"
        checklist = [{"task_id": t["id"], "title": t["title"], "required": t["priority"] == "must", "accepted": t["status"] == "accepted", "deliverable": t["deliverable"], "acceptance": t["acceptance"]} for t in items]
        suggestions = []
        if stats["block_events"]:
            suggestions.append("复查阻塞记录，提前写明接口、依赖与所需资料，再做一次相同交接练习。")
        if stats["return_events"]:
            suggestions.append("复查退回原因，在开始前用一个具体例子共同确认验收标准。")
        if not ready:
            suggestions.append("先完成清单中未通过的必须任务；提交成果后仍需另一成员验收。")
        if ready:
            suggestions.append("所有必须任务已通过成员验收；仍需人工对照赛事原文核对最终提交材料和入口。")
        suggestions.append("本轮未测量节时、学习提升或获奖概率，不能据此生成成效百分比。")
        rubric = rubric_coverage([s for s in sources(con, pid) if s["kind"] == "rules"], items)
        return {"project_name": p["name"], "goal": p["goal"], "phase": phase(p, items), "ready": ready, "source_label": "本地数据库统计与规则建议 · 非大模型复盘", "stats": stats, "checklist": checklist, "suggestions": suggestions, "event_count": len(events), "rubric": rubric, "scope": scope_advice(p["deadline"], now(), items)}

    @api.get("/api/projects/{pid}/recap")
    def get_recap(pid: str, authorization: str = Header(default="")):
        with db() as con:
            auth(con, pid, authorization)
            return recap(con, pid)

    @api.get("/api/projects/{pid}/export", response_class=PlainTextResponse)
    def export(pid: str, authorization: str = Header(default="")):
        with db() as con:
            auth(con, pid, authorization)
            report = recap(con, pid)
            originals = sources(con, pid)
            events = [dict(r) for r in con.execute("SELECT * FROM events WHERE project_id=? ORDER BY sequence", (pid,))]
            labels = {m["id"]: m["name"] for m in members(con, pid)}
        lines = [f"# {report['project_name']} · 提交核对与复盘", "", f"目标：{report['goal'] or '尚未确认'}", f"来源：{report['source_label']}", f"可交付：{'是（仍需核对赛规）' if report['ready'] else '否'}", "", "## 任务清单"]
        for t in report["checklist"]:
            lines.extend([f"- [{'x' if t['accepted'] else ' '}] {t['title']}（{'必须' if t['required'] else '可选'}）", f"  - 验收：{t['acceptance']}", f"  - 成果：{t['deliverable'] or '未提交'}"])
        lines.extend(advice_markdown(report["rubric"], report["scope"]))
        lines.extend(["", "## 复盘建议", *[f"- {s}" for s in report["suggestions"]], "", "## 资料原文"])
        for source in originals:
            lines.extend([f"### {source['title']}", source["body"], ""])
        lines.extend(["## 过程记录", *[f"- {e['created_at']} · {labels.get(e['actor_id'], '系统')} · {e['detail']}" for e in events]])
        return PlainTextResponse("\n".join(lines), media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="hackathon-recap.md"'})

    @api.get("/api/learning/v1/events")
    def learning_events_list(role: str = "creator", interests: str = "", time: str = ""):
        """Return the local sample activity catalog used by the experience UI."""
        requested = {item.strip() for item in interests.split(",") if item.strip()}
        result = []
        for event_item in learning_events:
            item = dict(event_item)
            item["match_reason"] = item["why"]
            if requested and "教育" in requested:
                item["match_reason"] = "教育主题与你的兴趣相近，也适合从小作品开始。"
            result.append(item)
        return {"mode": "local_demo", "role": role, "time": time, "items": result, "notice": "活动为虚构样例；正式活动数据待接入。"}

    @api.get("/api/learning/v1/events/{event_id}")
    def learning_event_detail(event_id: str):
        event_item = next((item for item in learning_events if item["id"] == event_id), None)
        if not event_item:
            raise Problem(404, "learning_event_not_found", "活动不存在或已下线。")
        return {"mode": "local_demo", "item": dict(event_item), "notice": "保存规则原文不代表系统已核验资格或截止时间。"}

    @api.post("/api/learning/v1/sessions", status_code=201)
    def learning_session_create(body: dict | None = None):
        body = body or {}
        session_id = uid()
        session = {
            "id": session_id,
            "mode": "local_demo",
            "role": body.get("role", "creator"),
            "created_at": now(),
            "updated_at": now(),
            "onboarding": {},
            "selected_event": None,
            "team": {"members": [{"id": "me", "name": "林同学", "role": "设计与创作", "sample": False}], "sample": False},
            "idea": {"goal": "complete", "text": ""},
            "direction": {"status": "draft", "title": "知识闯关小助手", "summary": "让学生用三步互动，理解一个知识点。"},
            "tasks": learning_seed_tasks(),
            "delivery": {"checks": [], "rehearsal_seconds": 60, "script": ""},
            "review": {"reflection": "", "share": []},
            "revision": 1,
        }
        with learning_lock, db(True) as con:
            con.execute(
                "INSERT INTO learning_sessions(id,role,mode,state,revision,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (session_id, session["role"], session["mode"], encode({k: v for k, v in session.items() if k not in {"id", "mode", "role", "created_at", "updated_at", "revision"}}), session["revision"], session["created_at"], session["updated_at"]),
            )
        return learning_session_snapshot(session)

    @api.get("/api/learning/v1/sessions/{session_id}")
    def learning_session_get(session_id: str):
        with learning_lock, db() as con:
            row = con.execute("SELECT * FROM learning_sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                raise Problem(404, "learning_session_not_found", "体验会话不存在或已过期。")
            return learning_persisted_snapshot(row)

    @api.patch("/api/learning/v1/sessions/{session_id}")
    def learning_session_update(session_id: str, body: dict):
        allowed = {"role", "onboarding", "selected_event", "team", "idea", "direction", "tasks", "delivery", "review"}
        with learning_lock, db(True) as con:
            row = con.execute("SELECT * FROM learning_sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                raise Problem(404, "learning_session_not_found", "体验会话不存在或已过期。")
            expected = body.get("expected_revision")
            if expected is not None and expected != row["revision"]:
                raise Problem(409, "learning_revision_conflict", "体验资料已在另一窗口更新，请刷新后重试。", {"current_revision": row["revision"]})
            session = learning_persisted_snapshot(row)
            for key in allowed:
                if key in body:
                    session[key] = body[key]
            session["revision"] += 1
            session["updated_at"] = now()
            state = {k: v for k, v in session.items() if k not in {"id", "mode", "role", "created_at", "updated_at", "revision"}}
            con.execute("UPDATE learning_sessions SET state=?,revision=?,updated_at=? WHERE id=?", (encode(state), session["revision"], session["updated_at"], session_id))
            return learning_session_snapshot(session)

    @api.post("/api/learning/v1/sessions/{session_id}/evidence")
    def learning_session_evidence(session_id: str, body: dict):
        task_id = str(body.get("task_id") or "")
        if not task_id:
            raise Problem(422, "learning_task_required", "请先选择要提交的任务。")
        if not any(str(body.get(key) or "").strip() for key in ("summary", "url", "file_name")):
            raise Problem(422, "learning_evidence_required", "请添加成果说明、链接或文件。")
        with learning_lock, db(True) as con:
            row = con.execute("SELECT * FROM learning_sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                raise Problem(404, "learning_session_not_found", "体验会话不存在或已过期。")
            session = learning_persisted_snapshot(row)
            task = next((item for item in session["tasks"] if item["id"] == task_id), None)
            if not task:
                raise Problem(404, "learning_task_not_found", "任务不存在或已更新。")
            task["evidence"] = {"summary": str(body.get("summary") or "").strip(), "url": str(body.get("url") or "").strip(), "file_name": str(body.get("file_name") or "").strip()}
            task["status"] = "reported_done"
            session["revision"] += 1
            session["updated_at"] = now()
            state = {k: v for k, v in session.items() if k not in {"id", "mode", "role", "created_at", "updated_at", "revision"}}
            con.execute("UPDATE learning_sessions SET state=?,revision=?,updated_at=? WHERE id=?", (encode(state), session["revision"], session["updated_at"], session_id))
            return learning_session_snapshot(session)

    @api.get("/", include_in_schema=False)
    def homepage():
        return FileResponse(ROOT / "static" / ("core.html" if api.state.core_only else "studio.html"))

    @api.get("/learning", include_in_schema=False)
    @api.get("/learning/", include_in_schema=False)
    def learning_homepage():
        return FileResponse(ROOT / "static" / "learning.html")

    @api.get("/workflow", include_in_schema=False)
    def workflow():
        return FileResponse(ROOT / "static" / "workflow.html")

    register_studio(api, db, Problem, now, uid, digest)
    register_core(api, db, Problem, now, uid, digest, core_model_runner)

    @api.get("/classic", include_in_schema=False)
    def classic():
        return FileResponse(ROOT / "static" / "index.html")

    api.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    return api


app = create_app()
