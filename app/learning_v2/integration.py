"""Opt-in legacy API boundary. Never installs or imports app.main implicitly."""
import contextvars
import hashlib
import json
import re
import sqlite3
import tempfile
from dataclasses import dataclass, field, replace

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse

from .protocol import Problem, fail
from .service import digest, iso, uid


_current = contextvars.ContextVar("songban_legacy_request", default=None)
_DDL = """CREATE TABLE learn_legacy_activity (
 id TEXT PRIMARY KEY, actor_id TEXT, browser_id TEXT, method TEXT NOT NULL,
 path TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL,
 resolved_at TEXT, resolution TEXT
)"""
_SCOPE_DDL = """CREATE TABLE learn_legacy_activity_scopes (
 activity_id TEXT PRIMARY KEY REFERENCES learn_legacy_activity(id) ON DELETE CASCADE,
 actor_ids TEXT NOT NULL, team_ids TEXT NOT NULL, ownership_known INTEGER NOT NULL
)"""
_TASK_DDL = """CREATE TABLE learn_legacy_task_scopes (
 table_name TEXT NOT NULL, task_key TEXT NOT NULL, actor_ids TEXT NOT NULL,
 PRIMARY KEY(table_name,task_key)
)"""


@dataclass
class _Context:
    boundary: object
    fence: object
    member_id: str | None = None
    member_hash: str | None = None
    activity_id: str | None = None
    problem: Problem | None = None
    closed: bool = False
    had_automation: bool = False
    path: str = ""
    writes: set = field(default_factory=set)
    actor_ids: set = field(default_factory=set)
    team_ids: set = field(default_factory=set)
    ownership_known: bool = False
    tasks_before: dict = field(default_factory=dict)


class LegacyBoundary:
    CREDENTIAL_ISSUERS = {
        "/api/studio/login", "/api/studio/login-code", "/api/studio/login-email",
        "/api/studio/register", "/api/studio/register-email", "/api/studio/email-bind",
        "/api/studio/wechat/finish",
    }
    # Reviewed local mutations, with no model/network/filesystem dispatch after DB.
    # New/unknown unsafe routes conservatively get an external-activity barrier.
    LOCAL_MUTATIONS = (
        ("PUT", r"/api/core/me/preferences"),
        ("PUT", r"/api/core/teams/[^/]+/profile"),
        ("PATCH", r"/api/studio/me"),
        ("POST", r"/api/projects/[^/]+/tasks/[^/]+/actions"),
    )
    # A missing/invalid owner stays fail-closed; known owners are scoped below.
    BUSY = (
        ("workbench_requests", "status", ("pending", "running", "unknown")),
        ("materials_batches", "status", ("pending", "running", "unknown")),
        ("recap_reports", "status", ("pending", "running", "unknown")),
        ("parent_reports", "state", ("pending", "running", "unknown")),
        ("idea_rankings", "status", ("pending", "running", "unknown")),
        ("division_rounds", "status", ("running", "unknown")),
        ("core_topic_rounds", "phase", ("ranking", "unknown")),
    )

    def __init__(self, service):
        self.service = service
        # Set only by the central installer after an independently guarded domain
        # is registered. Unknown APIs continue through this legacy fence.
        self.managed_prefixes = ()
        if getattr(service, "legacy_boundary", None) is not None:
            raise ValueError("A legacy boundary is already attached to this service")
        with service.store.transaction() as con:
            for version, ddl in (("M01B-legacy-boundary", _DDL), ("M01C-legacy-ownership", _SCOPE_DDL),
                                 ("M01D-legacy-task-ownership", _TASK_DDL)):
                checksum = hashlib.sha256(ddl.encode()).hexdigest()
                previous = con.execute("SELECT checksum FROM learn_migrations WHERE version=?", (version,)).fetchone()
                if previous:
                    if previous[0] != checksum:
                        raise ValueError("Legacy boundary migration checksum mismatch")
                else:
                    con.execute(ddl)
                    con.execute("INSERT INTO learn_migrations VALUES(?,?,?)", (version, checksum, iso(service.clock())))
        service.legacy_boundary = self

    def install(self, api):
        if getattr(api.state, "learning_legacy_boundary", None) is not None:
            raise ValueError("A legacy API boundary is already installed")
        api.state.learning_legacy_boundary = self
        api.add_exception_handler(Problem, self.problem_handler)
        api.add_middleware(_Middleware, boundary=self)
        return self

    @staticmethod
    async def problem_handler(_request, problem):
        return JSONResponse(problem.payload(), status_code=problem.status, headers={"Cache-Control": "no-store"})

    @staticmethod
    def table_exists(con, table):
        return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None

    def external_possible(self, method, path):
        if method in ("GET", "HEAD", "OPTIONS"):
            # The legacy OAuth callback exchanges codes with an external provider.
            return path.startswith("/api/studio/wechat/")
        return not any(method == verb and re.fullmatch(pattern, path) for verb, pattern in self.LOCAL_MUTATIONS)

    def capture(self, scope):
        request = Request(scope)
        with self.service.store.transaction() as con:
            # Browser mode is checked even for public issuers and unknown Bearer.
            self.service.legacy_request_guard(con, request)
            actor, member = None, None
            header = request.headers.get("authorization", "")
            if header:
                if not header.startswith("Bearer ") or len(header) > 600:
                    fail(401, "session_revoked", "旧凭证无效，请重新认证。", "reauthenticate")
                token_hash = digest(header[7:])
                if header[7:].startswith("sbconn_"):
                    row = con.execute("SELECT user_id FROM core_connections WHERE token_hash=?", (token_hash,)).fetchone() if self.table_exists(con, "core_connections") else None
                    if not row:
                        fail(401, "session_revoked", "连接凭证已失效。", "reauthenticate")
                    actor = row[0]
                else:
                    row = con.execute("SELECT id FROM people WHERE token_hash=?", (token_hash,)).fetchone()
                    if row:
                        actor = row[0]
                    elif self.table_exists(con, "members"):
                        member = con.execute("SELECT id,token_hash FROM members WHERE token_hash=?", (token_hash,)).fetchone()
                    # Public legacy authentication can receive an obsolete token
                    # from its old client. It still needs its actual password/code
                    # proof; this is never a Bearer-to-cookie exchange. The browser
                    # restriction above remains mandatory, including child mode.
                    public_issuer = scope["path"] in self.CREDENTIAL_ISSUERS - {"/api/studio/email-bind"}
                    if not actor and not member and not public_issuer:
                        fail(401, "session_revoked", "旧凭证已失效。", "reauthenticate")
            elif request.cookies.get(self.service.cookie_name):
                actor = self.service.session_row(con, request)["actor_id"]
            fence = self.service.legacy_request_guard(con, request, actor)
            context = _Context(self, fence, member[0] if member else None, member[1] if member else None,
                               path=scope["path"])
            context.actor_ids, context.team_ids, context.ownership_known = self.request_ownership(con, actor, scope["path"])
            context.had_automation = self.auto_enabled(con, context.actor_ids, context.team_ids)
            if self.external_possible(scope["method"], scope["path"]):
                context.activity_id = uid()
                con.execute("INSERT INTO learn_legacy_activity VALUES(?,?,?,?,?,'active',?,NULL,NULL)",
                            (context.activity_id, actor, fence.browser_id, scope["method"], scope["path"], iso(self.service.clock())))
                con.execute("INSERT INTO learn_legacy_activity_scopes VALUES(?,?,?,?)",
                            (context.activity_id, json.dumps(sorted(context.actor_ids)), json.dumps(sorted(context.team_ids)), int(context.ownership_known)))
            return context

    def validate(self, con, context, write):
        if context.closed:
            fail(401, "session_revoked", "原请求已经结束，后台任务不能继承其权限。")
        if context.problem:
            raise context.problem
        try:
            # A credential issuer can intentionally rotate its own legacy token.
            # The first check already matched it under BEGIN IMMEDIATE; only the
            # same locked connection can have changed it before the second check.
            issuer = context.path in self.CREDENTIAL_ISSUERS
            if write and con in context.writes and issuer and context.fence.actor_id:
                row = con.execute("SELECT token_hash FROM people WHERE id=?", (context.fence.actor_id,)).fetchone()
                if row and row[0] != context.fence.token_hash:
                    rotated = replace(context.fence, token_hash=row[0])
                    self.service.legacy_validate_fence(con, rotated, write=True)
                    context.fence = rotated
            self.service.legacy_validate_fence(con, context.fence, write=write)
            if context.member_id:
                row = con.execute("SELECT token_hash FROM members WHERE id=?", (context.member_id,)).fetchone()
                if row and write and con in context.writes and re.fullmatch(r"/api/projects/[^/]+/members/[^/]+/rotate-token", context.path):
                    context.member_hash = row[0]
                if not row or row[0] != context.member_hash:
                    fail(401, "session_revoked", "成员凭证已轮换，操作未保存。", "reauthenticate")
        except Problem as problem:
            context.problem = problem  # A caught failure cannot authorize a later commit.
            raise

    def check_db(self, con, write):
        """S00 calls after BEGIN and before commit, on its SAME connection.

        Startup and independent threads have no request context: do nothing, and
        never manufacture a privileged/request fence for them.
        """
        context = _current.get()
        if context is None:
            return
        if context.boundary is not self:
            raise RuntimeError("Request fence belongs to another app/database")
        self.validate(con, context, write)
        if write:
            busy = self.busy_rows(con)
            if con not in context.writes:
                context.tasks_before[con] = {(t, self.task_key(t, r)) for t, r in busy}
                context.writes.add(con)
            else:
                before = context.tasks_before[con]
                for table, row in busy:
                    key = self.task_key(table, row)
                    if key is None or (table, key) in before:
                        continue
                    actors = self.busy_actors(con, table, row)
                    if actors is None:
                        continue
                    if context.fence.actor_id:
                        actors.add(context.fence.actor_id)
                    old = con.execute("SELECT actor_ids FROM learn_legacy_task_scopes WHERE table_name=? AND task_key=?", (table, key)).fetchone()
                    if old:
                        try:
                            original = json.loads(old[0])
                            if not isinstance(original, list) or not all(isinstance(a, str) for a in original):
                                continue  # Never repair an unproven old scope by guessing.
                            actors.update(original)
                        except (ValueError, TypeError):
                            continue
                    con.execute("INSERT INTO learn_legacy_task_scopes VALUES(?,?,?) ON CONFLICT(table_name,task_key) DO UPDATE SET actor_ids=excluded.actor_ids",
                                (table, key, json.dumps(sorted(actors))))
                context.tasks_before[con] = {(t, self.task_key(t, r)) for t, r in busy}

    def busy_rows(self, con):
        result = []
        for table, column, states in self.BUSY:
            if self.table_exists(con, table):
                slots = ",".join("?" for _ in states)
                result.extend((table, r) for r in con.execute(f"SELECT * FROM {table} WHERE {column} IN ({slots})", states))
        return result

    @staticmethod
    def task_key(table, row):
        values = dict(row)
        columns = ("user_id", "squad_id", "request_id") if table == "parent_reports" else ("id",)
        parts = [values.get(c) for c in columns]
        return json.dumps(parts, separators=(",", ":")) if all(isinstance(p, str) and p for p in parts) else None

    def person_exists(self, con, actor):
        return bool(actor and con.execute("SELECT 1 FROM people WHERE id=?", (actor,)).fetchone())

    def team_actors(self, con, team):
        """Only a real squad with a valid captain and roster proves ownership."""
        if not team or not self.table_exists(con, "squads") or not self.table_exists(con, "squad_members"):
            return None
        squad = con.execute("SELECT captain_id FROM squads WHERE id=?", (team,)).fetchone()
        if not squad:
            return None
        actors = {r[0] for r in con.execute("SELECT user_id FROM squad_members WHERE squad_id=?", (team,))}
        if squad[0] not in actors or not all(self.person_exists(con, a) for a in actors):
            return None
        return actors

    def request_ownership(self, con, actor, path):
        # A public issuer can authenticate a different account from a supplied
        # Bearer. Until its fresh proof is processed, its target is unproven.
        identity_request = path in self.CREDENTIAL_ISSUERS or path in {
            "/api/studio/codes", "/api/studio/email-codes", "/api/core/guest-session",
        } or path.startswith("/api/studio/wechat/")
        actors = {actor} if self.person_exists(con, actor) else set()
        teams = set()
        match = re.match(r"/api/(?:core/teams|studio/squads)/([^/]+)(?:/|$)", path)
        if match and actors:
            roster = self.team_actors(con, match[1])
            # A path ID alone is never trusted as a team assignment.
            if roster and actor in roster:
                teams.add(match[1])
                actors.update(roster)
        match = re.match(r"/api/materials/spaces/([^/]+)(?:/|$)", path)
        if match and actors and self.table_exists(con, "materials_spaces"):
            space = con.execute("SELECT owner_id,team_id FROM materials_spaces WHERE id=?", (match[1],)).fetchone()
            if space and space[1]:
                roster = self.team_actors(con, space[1])
                if roster and actor in roster:
                    teams.add(space[1])
                    actors.update(roster)
        return actors, teams, bool(actors) and not identity_request

    def activity_actors(self, con, row):
        saved = con.execute("SELECT * FROM learn_legacy_activity_scopes WHERE activity_id=?", (row["id"],)).fetchone()
        if not saved:
            # M01B records predate ownership snapshots. Preserve their trusted
            # original actor, and resolve only server-backed route membership.
            actors, teams, known = self.request_ownership(con, row["actor_id"], row["path"])
            if re.match(r"/api/(?:core/teams|studio/squads)/([^/]+)(?:/|$)", row["path"]) and not teams:
                return None  # Historical team access can no longer be proved.
            space_match = re.match(r"/api/materials/spaces/([^/]+)(?:/|$)", row["path"])
            if space_match and not teams:
                space = con.execute("SELECT owner_id,team_id FROM materials_spaces WHERE id=?", (space_match[1],)).fetchone() if self.table_exists(con, "materials_spaces") else None
                if not space or space[1] or space[0] != row["actor_id"]:
                    return None
            return actors if known else None
        if not saved["ownership_known"]:
            return None
        try:
            actors, teams = json.loads(saved["actor_ids"]), json.loads(saved["team_ids"])
            if not isinstance(actors, list) or not actors or not all(isinstance(a, str) and self.person_exists(con, a) for a in actors):
                return None
            if not isinstance(teams, list) or not all(isinstance(t, str) for t in teams):
                return None
            owners = set(actors)  # Includes the original roster even after removal.
            for team in teams:
                roster = self.team_actors(con, team)
                if roster is None:
                    return None
                owners.update(roster)  # New legitimate team members also count.
            return owners
        except (ValueError, TypeError):
            return None

    def busy_actors(self, con, table, row):
        row = dict(row)
        owner_column = {"workbench_requests": "owner_id", "materials_batches": "requester_id",
                        "recap_reports": "user_id", "parent_reports": "user_id"}.get(table)
        if owner_column:
            actor = row.get(owner_column)
            if not self.person_exists(con, actor):
                return None
            if table == "workbench_requests":
                if not self.table_exists(con, "workbench_sessions"):
                    return None
                session = con.execute("SELECT owner_id FROM workbench_sessions WHERE id=?", (row.get("session_id"),)).fetchone()
                if not session or session[0] != actor:
                    return None
            if table == "materials_batches":
                if not self.table_exists(con, "materials_spaces"):
                    return None
                space = con.execute("SELECT owner_id,team_id FROM materials_spaces WHERE id=?", (row.get("space_id"),)).fetchone()
                if not space:
                    return None
                if space[1]:
                    roster = self.team_actors(con, space[1])
                    return roster if roster and actor in roster else None
                if space[0] != actor:
                    return None
            return {actor}
        return self.team_actors(con, row.get("squad_id"))

    def check_switch(self, con, *, actor_id, browser_id=None):
        """Must run inside the enterLearner write transaction before epoch change."""
        if not self.person_exists(con, actor_id):
            fail(401, "session_revoked", "切换主体无法确认，请重新认证。", "reauthenticate")
        for row in con.execute("SELECT * FROM learn_legacy_activity WHERE state IN ('active','unknown')"):
            owners = self.activity_actors(con, row)
            if owners is None or actor_id in owners or (browser_id and row["browser_id"] == browser_id):
                fail(409, "legacy_work_in_progress", "关联旧请求或归属待核对任务尚未结束，请先核对。", "contact_support")
        for table, row in self.busy_rows(con):
            owners = self.busy_actors(con, table, row)
            saved = con.execute("SELECT actor_ids FROM learn_legacy_task_scopes WHERE table_name=? AND task_key=?", (table, self.task_key(table, row))).fetchone()
            if saved and owners is not None:
                try:
                    original = json.loads(saved[0])
                    if not isinstance(original, list) or not original or not all(isinstance(a, str) and self.person_exists(con, a) for a in original):
                        owners = None
                    else:
                        owners.update(original)
                except (ValueError, TypeError):
                    owners = None
            if owners is None or actor_id in owners:
                fail(409, "legacy_work_in_progress", "关联旧模型任务或归属待核对任务尚未结束。", "contact_support")
        if self.auto_enabled(con, {actor_id}):
            fail(409, "legacy_automation_active", "旧自动统筹仍开启，请先关闭并核对后台任务。", "contact_support")

    def auto_enabled(self, con, actor_ids, team_ids=()):
        if self.table_exists(con, "core_settings"):
            for row in con.execute("SELECT * FROM core_settings WHERE auto_review=1"):
                team = dict(row).get("squad_id")
                owners = self.team_actors(con, team)
                if owners is None or team in team_ids or set(actor_ids).intersection(owners):
                    return True
        return False

    def finish(self, context, *, uncertain=False, validate=True):
        with self.service.store.transaction() as con:
            if validate:
                self.validate(con, context, False)
            if context.activity_id:
                # Raw legacy auto-review threads do not inherit ContextVar; retain
                # a durable hazard even after HTTP completion when they may exist.
                if uncertain or context.had_automation or self.auto_enabled(con, context.actor_ids, context.team_ids):
                    con.execute("UPDATE learn_legacy_activity SET state='unknown' WHERE id=?", (context.activity_id,))
                else:
                    con.execute("DELETE FROM learn_legacy_activity WHERE id=?", (context.activity_id,))

    def resolve_activity(self, activity_id, *, authority, evidence):
        """Server-only, after operator verifies no outstanding external dispatch."""
        if not authority or not evidence:
            raise ValueError("Activity resolution requires authority and reviewed evidence")
        with self.service.store.transaction() as con:
            row = con.execute("SELECT state FROM learn_legacy_activity WHERE id=?", (activity_id,)).fetchone()
            if not row or row[0] != "unknown":
                raise ValueError("Only an uncertain, ended request can be reconciled")
            con.execute("UPDATE learn_legacy_activity SET state='resolved',resolved_at=?,resolution=? WHERE id=?",
                        (iso(self.service.clock()), evidence, activity_id))
            self.service.audit(con, None, "legacy_activity_resolved", activity_id, {"authority": authority, "evidence": evidence})


class _Middleware:
    """Pure ASGI: keeps ContextVar across sync threadpool and delays private output."""
    def __init__(self, app, boundary):
        self.app, self.boundary = app, boundary

    async def abandon(self, context):
        if context and context.activity_id:
            try:
                await run_in_threadpool(self.boundary.finish, context, uncertain=True, validate=False)
            except sqlite3.OperationalError:
                # The already-durable active marker also blocks switching. A
                # failed cleanup must not replace the intended fail-closed JSON.
                pass

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        managed = any(path == prefix or path.startswith(prefix+'/') for prefix in self.boundary.managed_prefixes)
        if scope["type"] != "http" or not (path == "/api" or path.startswith("/api/")) or path == "/api/learning/v2" or path.startswith("/api/learning/v2/") or managed:
            await self.app(scope, receive, send)
            return
        context = None
        token = None
        try:
            context = await run_in_threadpool(self.boundary.capture, scope)
            token = _current.set(context)
            start = None
            # Spooled buffering keeps a sensitive read from reaching the network
            # before final revalidation, without an unbounded in-memory zip/body.
            with tempfile.SpooledTemporaryFile(max_size=1024*1024) as body:
                async def collect(message):
                    nonlocal start
                    if message["type"] == "http.response.start":
                        start = dict(message)
                    elif message["type"] == "http.response.body":
                        body.write(message.get("body", b""))
                    elif message["type"] != "http.response.debug":
                        raise RuntimeError("Unsupported legacy response extension")
                safe_scope = dict(scope)
                safe_scope["extensions"] = {k: v for k, v in scope.get("extensions", {}).items() if k != "http.response.pathsend"}
                await self.app(safe_scope, receive, collect)
                if start is None:
                    raise RuntimeError("Legacy app did not produce a response")
                await run_in_threadpool(self.boundary.finish, context, uncertain=start["status"] >= 500)
                if context.problem:
                    raise context.problem
                headers = [(k, v) for k, v in start.get("headers", []) if k.lower() != b"cache-control"]
                headers.append((b"cache-control", b"no-store"))
                start["headers"] = headers
                await send(start)
                body.seek(0)
                while chunk := body.read(65536):
                    await send({"type": "http.response.body", "body": chunk, "more_body": True})
                await send({"type": "http.response.body", "body": b"", "more_body": False})
        except Problem as problem:
            await self.abandon(context)
            await JSONResponse(problem.payload(), status_code=problem.status, headers={"Cache-Control": "no-store"})(scope, receive, send)
        except sqlite3.OperationalError:
            await self.abandon(context)
            problem = Problem(503, "storage_unavailable", "身份核对暂不可用，请稍后核对原请求。", "reload")
            await JSONResponse(problem.payload(), status_code=503, headers={"Cache-Control": "no-store"})(scope, receive, send)
        except BaseException:
            await self.abandon(context)
            raise
        finally:
            if context:
                context.closed = True
                context.writes.clear()
                context.tasks_before.clear()
            if token is not None:
                _current.reset(token)
