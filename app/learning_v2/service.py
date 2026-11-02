"""P1 identity and start domain. No app.main import, env loading or network I/O."""
import hashlib
import hmac
import ipaddress
import json
import secrets
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .protocol import Contract, canonical, fail, revision
from .storage import Store
from .course import CourseDomain
from .models import ModelDomain
from .reports import ReportDomain

P3_MODEL_OPS = {'usage', 'reconciliation', 'reconciliations', 'resolveReconciliation'}
P3_REPORT_OPS = {'createReport', 'report', 'reports', 'disputeReport', 'submitReport', 'reviewReport', 'publishReport', 'revokeReport'}


def uid():
    return secrets.token_hex(16)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ReviewQueue:
    reviewer_id: str
    display_name: str
    due_seconds: int
    support_contact_label: str


@dataclass(frozen=True)
class Settings:
    enabled: bool = False
    allowed_origins: tuple = ()
    loopback_http: bool = False
    session_seconds: int = 1800
    browser_seconds: int = 28800
    consent_version: str = "unconfigured"
    age_band_options: tuple = ()
    relationship_queue: ReviewQueue | None = None
    course_enabled: bool = False
    mock_enabled: bool = False
    learning_queue: ReviewQueue | None = None
    support_queue: ReviewQueue | None = None
    models_enabled: bool = False
    model_settings: object | None = None
    reports_enabled: bool = False
    publication_enabled: bool = False
    report_queue: ReviewQueue | None = None
    # No teaching mapping is approved yet. None deliberately means conservative fallback.
    recommendation_rule_version: str = "unconfigured-conservative-v1"
    navigation_enabled: bool = False

    def __post_init__(self):
        if not 60 <= self.session_seconds <= 3600 or not self.session_seconds <= self.browser_seconds <= 86400:
            raise ValueError("Session/browser TTL outside supported bounds")
        if self.loopback_http and not self.allowed_origins:
            raise ValueError("Loopback exception requires an explicit origin allowlist")
        for origin in self.allowed_origins:
            u = urlsplit(origin)
            if u.username or u.password or u.path or u.query or u.fragment or not u.hostname:
                raise ValueError("Origin must be exact scheme/host/port")
            if self.loopback_http:
                try:
                    local = ipaddress.ip_address(u.hostname).is_loopback
                except ValueError:
                    local = u.hostname == "localhost"
                if u.scheme != "http" or not local:
                    raise ValueError("HTTP exception is restricted to loopback origins")
            elif u.scheme != "https":
                raise ValueError("Production origins require HTTPS")
        for q in (self.relationship_queue, self.learning_queue, self.support_queue, self.report_queue):
            if q is None:
                continue
            if not q.reviewer_id or not q.display_name or not q.support_contact_label or q.due_seconds <= 0:
                raise ValueError("Relationship queue requires an owner, deadline and support route")


@dataclass(frozen=True)
class LegacyFence:
    actor_id: str | None
    auth_epoch: int
    token_hash: str | None
    browser_id: str | None
    mode_epoch: int | None
    session_hash: str | None
    connection_id: str | None = None
    connection_hash: str | None = None


class LearningV2(ModelDomain, ReportDomain, CourseDomain):
    def __init__(self, db_path, settings=None, *, password_verifier=None, clock=time.time):
        if settings is not None and not isinstance(settings, Settings):
            raise TypeError("Learning settings must be an explicit Settings instance")
        self.settings = settings or Settings()
        self.clock = clock
        self.store = Store(db_path)
        self.contract = Contract()
        with closing(self.store.connect()) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            metering_history = 'learn_model_jobs' in tables and con.execute('SELECT 1 FROM learn_model_jobs LIMIT 1').fetchone() is not None
            report_history = 'learn_course_objects' in tables and con.execute("SELECT 1 FROM learn_course_objects WHERE kind='report' LIMIT 1").fetchone() is not None
            self.course_history_available = 'learn_course_objects' in tables and con.execute("SELECT 1 FROM learn_course_objects WHERE kind IN ('run','artifact','enrollment','case') LIMIT 1").fetchone() is not None
        hidden = set()
        if not self.settings.course_enabled:
            hidden |= self.COURSE_OPS | P3_MODEL_OPS | P3_REPORT_OPS
        if not self.settings.models_enabled:
            hidden |= P3_MODEL_OPS
        if not self.settings.reports_enabled:
            hidden |= P3_REPORT_OPS
        # Disabling new work must not remove recovery, revocation or historical reads.
        if metering_history:
            hidden -= P3_MODEL_OPS | {'modelRun'}
        if report_history:
            hidden -= {'report', 'reports', 'revokeReport'}
        if self.course_history_available:
            hidden -= self.COURSE_READ_OPS
        self.contract.document['paths'] = {p: {m: s for m, s in methods.items() if s['operationId'] not in hidden}
                                           for p, methods in self.contract.document['paths'].items()
                                           if any(s['operationId'] not in hidden for s in methods.values())}
        if password_verifier is None:
            # Reuse the existing verifier, never initialize studio or its database.
            from app.studio import password_matches
            password_verifier = password_matches
        self.password_verifier = password_verifier
        self.cookie_name = "songban_dev_session" if self.settings.loopback_http else "__Host-songban_session"
        self.browser_cookie = "songban_dev_browser" if self.settings.loopback_http else "__Host-songban_browser"

    def migrate(self):
        self.store.migrate(iso(self.clock()))
        self.migrate_course()
        self.migrate_models()
        self.migrate_reports()

    def mac(self, con, value):
        secret = con.execute("SELECT value FROM learn_secrets WHERE name='hmac'").fetchone()[0]
        return hmac.new(bytes.fromhex(secret), value.encode(), hashlib.sha256).hexdigest()

    def audit(self, con, actor, action, target, details=None):
        con.execute("INSERT INTO learn_audit VALUES(?,?,?,?,?,?)",
                    (uid(), actor, action, target, iso(self.clock()), canonical(details or {})))

    def csrf(self, con, browser):
        return self.mac(con, f"csrf:{browser['id']}:{browser['epoch']}")

    def browser(self, con, request, required=True):
        token = request.cookies.get(self.browser_cookie, "")
        row = con.execute("SELECT * FROM learn_browsers WHERE token_hash=?", (digest(token),)).fetchone() if token else None
        if not row or row["expires"] <= self.clock():
            if required:
                fail(401, "session_expired", "请重新确认浏览器身份。", "reauthenticate")
            return None
        return row

    def origin(self, request):
        origin = request.headers.get("origin")
        # Never trust Forwarded/X-Forwarded-* to broaden the HTTP exception.
        if origin not in self.settings.allowed_origins or str(request.base_url).rstrip("/") != origin:
            fail(403, "origin_rejected", "请求来源不受允许。")

    def transport(self, request):
        if self.settings.loopback_http:
            if str(request.base_url).rstrip("/") not in self.settings.allowed_origins:
                fail(403, "origin_rejected", "开发会话仅限已配置的本机地址。")
        elif request.url.scheme != "https":
            fail(403, "secure_transport_required", "当前会话需要安全连接。")
        if request.headers.get("sec-fetch-site") == "cross-site":
            fail(403, "origin_rejected", "请求来源不受允许。")

    def write_guard(self, con, request, browser):
        self.origin(request)
        token = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(self.csrf(con, browser), token):
            fail(403, "csrf_rejected", "页面身份已变化，请重新读取。", "reload")

    def session_row(self, con, request, browser=None, *, ending=False):
        browser = browser if browser is not None else self.browser(con, request)
        token = request.cookies.get(self.cookie_name, "")
        row = con.execute("SELECT * FROM learn_sessions WHERE token_hash=?", (digest(token),)).fetchone() if token else None
        if not row or (row["revoked"] and not ending) or row["browser_id"] != browser["id"] or row["epoch"] != browser["epoch"]:
            fail(401, "session_revoked", "当前身份已失效，请重新认证。", "reauthenticate")
        if row["expires"] <= self.clock() and not ending:
            fail(401, "session_expired", "当前身份已过期，请重新认证。", "reauthenticate")
        if row["mode"] == "learner" and not ending:
            self.learning_access(con, row["learner_id"])
        if row["mode"] == "staff" and not ending and not self.scopes(con, row["actor_id"]):
            fail(403, "forbidden", "后台权限已失效。")
        return row

    def scopes(self, con, actor):
        return [r[0] for r in con.execute("SELECT scope FROM learn_grants WHERE actor_id=? AND expires>? ORDER BY scope", (actor, self.clock()))]

    def session_view(self, con, row):
        scopes = self.scopes(con, row["actor_id"]) if row["mode"] == "staff" else ["learning"] if row["mode"] == "learner" else ["family_manage"]
        return {"id": row["id"], "revision": row["revision"], "mode": row["mode"], "actor_id": row["actor_id"],
                "learner_id": row["learner_id"], "mode_epoch": row["epoch"], "scopes": scopes, "expires_at": iso(row["expires"])}

    def role(self, session, *allowed):
        if session["mode"] not in allowed:
            fail(403, "child_mode_restricted" if session["mode"] == "learner" else "forbidden", "当前身份不能执行这个操作。")

    def rotate(self, con, browser, actor=None, mode="anonymous", learner=None):
        epoch = browser["epoch"] + 1
        con.execute("UPDATE learn_browsers SET epoch=?,mode=? WHERE id=?", (epoch, mode, browser["id"]))
        con.execute("UPDATE learn_sessions SET revoked=1 WHERE browser_id=?", (browser["id"],))
        if actor is None:
            return {"revoked": True, "mode_epoch": epoch}, None
        token, sid = secrets.token_urlsafe(32), uid()
        expiry = min(self.clock() + self.settings.session_seconds, browser["expires"])
        con.execute("INSERT INTO learn_sessions(id,token_hash,browser_id,actor_id,learner_id,mode,epoch,revision,expires) VALUES(?,?,?,?,?,?,?,?,?)",
                    (sid, digest(token), browser["id"], actor, learner, mode, epoch, epoch, expiry))
        return self.session_view(con, con.execute("SELECT * FROM learn_sessions WHERE id=?", (sid,)).fetchone()), token

    def tombstone_legacy(self, con, actor):
        con.execute("INSERT INTO learn_auth_epochs VALUES(?,1) ON CONFLICT(actor_id) DO UPDATE SET epoch=epoch+1", (actor,))
        con.execute("UPDATE people SET token_hash=? WHERE id=?", (digest(secrets.token_urlsafe(48)), actor))

    def family(self, con, session, family_id):
        self.role(session, "manager")
        row = con.execute("SELECT * FROM learn_families WHERE id=? AND owner_id=?", (family_id, session["actor_id"])).fetchone()
        if not row:
            fail(404, "resource_not_found", "找不到可访问的记录。")
        return row

    def learner(self, con, session, learner_id):
        row = con.execute("SELECT * FROM learn_learners WHERE id=?", (learner_id,)).fetchone()
        if not row:
            fail(404, "resource_not_found", "找不到可访问的记录。")
        if session["mode"] == "learner":
            if learner_id != session["learner_id"]:
                fail(404, "resource_not_found", "找不到可访问的记录。")
        else:
            self.family(con, session, row["family_id"])
        return row

    def link(self, con, learner_id):
        return con.execute("SELECT * FROM learn_links WHERE learner_id=?", (learner_id,)).fetchone()

    def learner_view(self, con, row, child=False):
        value = {k: row[k] for k in ("id", "revision", "display_name", "age_band")}
        if not child:
            link = self.link(con, row["id"])
            value.update(family_id=row["family_id"], guardian_link={k: link[k] for k in ("id", "revision", "learner_id", "status", "declared_relationship", "verification_method")})
        return value

    def family_view(self, con, row):
        return {"id": row["id"], "revision": row["revision"], "learners": [self.learner_view(con, r) for r in con.execute("SELECT * FROM learn_learners WHERE family_id=?", (row["id"],))]}

    def age(self, value):
        if value is not None and value not in self.settings.age_band_options:
            fail(422, "invalid_input", "请选择当前配置的年龄选项，或暂不填写。")

    def consent_text(self, con, version):
        row = con.execute("SELECT body FROM learn_texts WHERE version=?", (version,)).fetchone()
        if not row:
            fail(404, "resource_not_found", "授权文本尚未配置。")
        return json.loads(row[0])

    def effective(self, con, row):
        link = self.link(con, row["learner_id"])
        text = self.consent_text(con, row["version"])
        if link["status"] != "verified" or row["status"] != "active" or text["approval_status"] != "approved_for_pilot" or not text["acceptance_enabled"] or text["text_sha256"] != row["text_hash"]:
            return []
        return json.loads(row["scopes"])

    def learning_access(self, con, learner_id):
        link = self.link(con, learner_id)
        if not link or link["status"] != "verified":
            fail(403, "consent_required", "关系尚未确认或已经失效。")
        rows = con.execute("SELECT * FROM learn_consents WHERE learner_id=?", (learner_id,)).fetchall()
        if not any("learning" in self.effective(con, r) for r in rows):
            fail(403, "consent_required", "有效学习授权尚未建立或已经撤回。")

    def consent_view(self, con, row, summary=False):
        value = {"id": row["id"], "revision": row["revision"], "learner_id": row["learner_id"], "consent_version": row["version"],
                 "scopes": json.loads(row["scopes"]), "status": row["status"], "recorded_at": row["recorded_at"]}
        if summary:
            value.update(text_sha256=row["text_hash"], effective_scopes=self.effective(con, row))
        return value

    def revoke_learner_sessions(self, con, learner_id):
        con.execute("UPDATE learn_sessions SET revoked=1 WHERE learner_id=?", (learner_id,))

    def start(self, con, learner):
        row = con.execute("SELECT body FROM learn_starts WHERE learner_id=?", (learner["id"],)).fetchone()
        if row:
            return json.loads(row[0])
        answers = {k: {"state": "unanswered", "value": None} for k in self.contract.schemas["StartAnswers"]["required"]}
        return self.project_start(learner, answers, 0, None)

    def project_start(self, learner, answers, rev, saved_at):
        missing = [k for k, v in answers.items() if v["state"] == "unanswered"]
        skipped = [k for k, v in answers.items() if v["state"] == "skipped"]
        choice = answers["chosen_start"]
        chosen = choice["state"] in ("answered", "accepted_default")
        return {"id": learner["start_id"], "revision": rev, "learner_id": learner["id"], "answers": answers,
                "completion_status": "not_started" if len(missing) == 6 else "draft" if missing else "completed_with_skips" if skipped else "completed",
                "mini_attempt_status": "not_attempted" if answers["mini_attempt_text"]["state"] == "unanswered" else answers["mini_attempt_text"]["state"],
                "recommendation": "guided", "recommendation_basis": "insufficient_evidence", "recommendation_revision": rev,
                "recommendation_rule_version": self.settings.recommendation_rule_version, "recommendation_source_fields": [],
                "missing_fields": missing, "skipped_fields": skipped, "effective_start": choice["value"] if chosen else "guided",
                "effective_start_source": ("accepted_default" if choice["state"] == "accepted_default" else "learner_choice") if chosen else "conservative_fallback", "saved_at": saved_at}

    def case_access(self, con, session, case_id, scope="relationship_review"):
        self.role(session, "staff")
        row = con.execute("SELECT * FROM learn_cases WHERE id=? AND assignee_id=?", (case_id, session["actor_id"])).fetchone()
        if not row or scope not in self.scopes(con, session["actor_id"]):
            fail(404, "resource_not_found", "找不到可访问的案件。")
        if self.link(con, row["learner_id"])["actor_id"] == session["actor_id"]:
            fail(403, "forbidden", "不能核验本人声明的关系。")
        return row

    def case_view(self, row):
        actions = ["claimCase"] if row["status"] == "open" else ["resolveCase"] if row["status"] == "claimed" else []
        return {"id": row["id"], "revision": row["revision"], "kind": "relationship", "target_id": row["learner_id"],
                "status": row["status"], "owner_display_name": row["owner_display_name"], "due_at": row["due_at"], "feedback": row["feedback"],
                "next_action": {"type": "contact_support", "resource_id": row["id"], "label": "按项目流程核对关系"},
                "parent_revision": row["target_revision"], "allowed_actions": actions, "support_contact_label": row["support_contact_label"], "learner_id": row["learner_id"]}

    def cursor(self, con, session, scope, row_id):
        return row_id + "." + self.mac(con, f"cursor:{session['actor_id']}:{scope}:{row_id}")

    def page(self, con, session, scope, rows, query):
        try:
            limit = int(query.get("limit", "20"))
            if not 1 <= limit <= 100:
                raise ValueError()
        except ValueError:
            fail(422, "invalid_input", "分页数量不正确。")
        cursor = query.get("cursor")
        if cursor:
            ident = cursor.split(".", 1)[0]
            if not secrets.compare_digest(cursor, self.cursor(con, session, scope, ident)):
                fail(422, "invalid_input", "分页位置无效。")
            indexes = [i for i, row in enumerate(rows) if row["id"] == ident]
            if not indexes:
                fail(422, "invalid_input", "分页位置无效。")
            rows = rows[indexes[0]+1:]
        selected = rows[:limit]
        return selected, self.cursor(con, session, scope, selected[-1]["id"]) if len(rows) > limit else None

    def read(self, con, op, session, params, query):
        if self.model_handles(con, op, params):
            return self.model_read(con, op, session, params, query)
        if self.report_handles(con, op, params):
            return self.report_read(con, op, session, params, query)
        if self.course_handles(con, op, params):
            return self.course_read(con, op, session, params, query)
        if op == "session":
            return self.session_view(con, session)
        if op == "listFamilies":
            self.role(session, "manager")
            return {"items": [self.family_view(con, r) for r in con.execute("SELECT * FROM learn_families WHERE owner_id=?", (session["actor_id"],))], "next_cursor": None}
        if op == "getFamily":
            return self.family_view(con, self.family(con, session, params["family_id"]))
        if op in ("getProfile", "getStart"):
            if op == "getStart":
                self.role(session, "learner")
            learner = self.learner(con, session, params["learner_id"])
            return self.start(con, learner) if op == "getStart" else self.learner_view(con, learner, session["mode"] == "learner")
        if op == "listConsents":
            self.role(session, "manager", "staff")
            lid = params["learner_id"]
            if session["mode"] == "staff":
                case = con.execute("SELECT id FROM learn_cases WHERE learner_id=?", (lid,)).fetchone()
                self.case_access(con, session, case[0] if case else "", "consent_read")
                visibility = "assigned_case"
            else:
                self.learner(con, session, lid)
                visibility = "linked_learner" if self.link(con, lid)["status"] == "verified" else "own_submissions"
            rows = con.execute("SELECT * FROM learn_consents WHERE learner_id=? ORDER BY recorded_at DESC,id DESC", (lid,)).fetchall()
            if visibility == "own_submissions":
                rows = [r for r in rows if r["submitted_by"] == session["actor_id"]]
            rows, cursor = self.page(con, session, lid, rows, query)
            return {"learner_id": lid, "relationship_status": self.link(con, lid)["status"], "visibility": visibility,
                    "items": [self.consent_view(con, r, True) for r in rows], "next_cursor": cursor}
        if op == "cases":
            self.role(session, "staff", "learner")
            # P1 has relationship cases only, which are never child-visible.
            rows = con.execute("SELECT * FROM learn_cases WHERE assignee_id=? ORDER BY due_at,id", (session["actor_id"],)).fetchall() if session["mode"] == "staff" and "relationship_review" in self.scopes(con, session["actor_id"]) else []
            rows = [r for r in rows if self.link(con, r["learner_id"])["actor_id"] != session["actor_id"]]
            rows, cursor = self.page(con, session, "cases", rows, query)
            return {"items": [self.case_view(r) for r in rows], "next_cursor": cursor}
        if op in ("case", "caseEvidence"):
            row = self.case_access(con, session, params["case_id"])
            if op == "case":
                return self.case_view(row)
            sources = [{"ref": {"source_id": r["id"], "source_version": str(r["version"]), "source_domain": "learning_v2", "nature": "human_review"},
                        "redacted_text": r["redacted_text"], "visibility": "assigned_reviewer_only"} for r in con.execute("SELECT * FROM learn_evidence WHERE case_id=?", (row["id"],))]
            return {"case_id": row["id"], "target_revision": row["target_revision"], "sources": sources}
        fail(503, "operation_unavailable", "该功能尚未实现。", "contact_support")

    def authorize_write(self, con, op, session, params, body):
        if (self.settings.models_enabled or op == 'resolveReconciliation') and self.model_handles(con, op, params):
            return self.model_authorize(con, op, session, params, body)
        if self.report_handles(con, op, params):
            return self.report_authorize(con, op, session, params, body)
        if self.course_handles(con, op, params):
            return self.course_authorize(con, op, session, params, body)
        if op in ("createFamily", "createLearner", "editProfile", "createConsent", "revokeConsent", "enterLearner"):
            self.role(session, "manager")
        elif op == "saveStart":
            self.role(session, "learner")
        elif op in ("claimCase", "resolveCase"):
            self.case_access(con, session, params["case_id"])
        if "family_id" in params:
            self.family(con, session, params["family_id"])
        if "learner_id" in params:
            learner = self.learner(con, session, params["learner_id"])
            if op == "createConsent" and self.link(con, learner["id"])["status"] != "verified":
                fail(403, "consent_required", "请先完成关系核对。")
            if op == "createConsent":
                text = self.consent_text(con, body["consent_version"])
                if text["approval_status"] != "approved_for_pilot" or not text["acceptance_enabled"]:
                    fail(403, "consent_text_unapproved", "授权文本尚未获准用于确认。")
        if op == "revokeConsent":
            row = con.execute("SELECT * FROM learn_consents WHERE id=?", (params["consent_id"],)).fetchone()
            if not row:
                fail(404, "resource_not_found", "找不到可访问的记录。")
            self.learner(con, session, row["learner_id"])

    def write(self, con, op, session, browser, params, body):
        if (self.settings.models_enabled or op == 'resolveReconciliation') and self.model_handles(con, op, params):
            return self.model_write(con, op, session, params, body)
        if self.report_handles(con, op, params):
            return self.report_write(con, op, session, params, body), None
        if self.course_handles(con, op, params):
            return self.course_write(con, op, session, params, body), None
        actor = session["actor_id"]
        if op == "createFamily":
            if con.execute("SELECT 1 FROM learn_families WHERE owner_id=?", (actor,)).fetchone():
                fail(409, "family_exists", "家庭已经存在，请读取本人家庭。", "reload")
            fid = uid()
            con.execute("INSERT INTO learn_families VALUES(?,?,1)", (fid, actor))
            return {"id": fid, "revision": 1, "learners": []}, None
        if op == "createLearner":
            family = self.family(con, session, params["family_id"])
            revision(body["expected_revision"], family["revision"])
            if con.execute("SELECT 1 FROM learn_learners WHERE family_id=?", (family["id"],)).fetchone():
                fail(409, "learner_exists", "本期每个家庭仅建立一位学习者。", "reload")
            self.age(body["age_band"])
            q = self.settings.relationship_queue
            if not q or q.reviewer_id == actor or "relationship_review" not in self.scopes(con, q.reviewer_id):
                fail(503, "support_unavailable", "关系核对尚未配置负责人，请稍后再试。", "contact_support")
            lid, link_id, case_id = uid(), uid(), uid()
            con.execute("INSERT INTO learn_learners VALUES(?,?,1,?,?,?)", (lid, family["id"], body["display_name"], body["age_band"], uid()))
            con.execute("INSERT INTO learn_links(id,learner_id,actor_id,revision,status,declared_relationship) VALUES(?,?,?,1,'pending',?)", (link_id, lid, actor, body["declared_relationship"]))
            con.execute("INSERT INTO learn_cases VALUES(?,?,?,1,'open',1,?,?,?,NULL)", (case_id, lid, q.reviewer_id, q.display_name, iso(self.clock()+q.due_seconds), q.support_contact_label))
            con.execute("UPDATE learn_families SET revision=revision+1 WHERE id=?", (family["id"],))
            return self.learner_view(con, self.learner(con, session, lid)), None
        if op == "editProfile":
            learner = self.learner(con, session, params["learner_id"])
            revision(body["expected_revision"], learner["revision"])
            self.age(body["age_band"])
            con.execute("UPDATE learn_learners SET revision=revision+1,display_name=?,age_band=? WHERE id=?", (body["display_name"], body["age_band"], learner["id"]))
            # Refresh the pending review target, never rewrite the immutable start history.
            con.execute("UPDATE learn_cases SET target_revision=target_revision+1,revision=revision+1 WHERE learner_id=? AND status!='resolved'", (learner["id"],))
            return self.learner_view(con, self.learner(con, session, learner["id"])), None
        if op == "createConsent":
            learner = self.learner(con, session, params["learner_id"])
            revision(body["expected_revision"], learner["revision"])
            text = self.consent_text(con, body["consent_version"])
            allowed = {p["scope"] for p in text["scope_purposes"]}
            if text["approval_status"] != "approved_for_pilot" or not text["acceptance_enabled"]:
                fail(403, "consent_text_unapproved", "授权文本尚未获准用于确认。")
            if not body["scopes"] or len(set(body["scopes"])) != len(body["scopes"]) or not set(body["scopes"]) <= allowed:
                fail(422, "invalid_input", "授权范围不符合该版本文本。")
            cid = uid()
            con.execute("INSERT INTO learn_consents VALUES(?,?,?,1,?,?,'active',?,?)", (cid, learner["id"], actor, body["consent_version"], canonical(body["scopes"]), iso(self.clock()), text["text_sha256"]))
            con.execute("UPDATE learn_learners SET revision=revision+1 WHERE id=?", (learner["id"],))
            return self.consent_view(con, con.execute("SELECT * FROM learn_consents WHERE id=?", (cid,)).fetchone()), None
        if op == "revokeConsent":
            row = con.execute("SELECT * FROM learn_consents WHERE id=?", (params["consent_id"],)).fetchone()
            revision(body["expected_revision"], row["revision"])
            if row["status"] != "revoked":
                con.execute("UPDATE learn_consents SET status='revoked',revision=revision+1 WHERE id=?", (row["id"],))
                self.revoke_learner_sessions(con, row["learner_id"])
                self.invalidate_learner_reports(con, row["learner_id"], actor_id=actor, reason="consent_revoked")
                self.audit(con, actor, "consent_revoked", row["id"], {"reason": body["reason"]})
            return self.consent_view(con, con.execute("SELECT * FROM learn_consents WHERE id=?", (row["id"],)).fetchone()), None
        if op == "enterLearner":
            revision(body["expected_revision"], session["revision"])
            self.learner(con, session, body["learner_id"])
            self.learning_access(con, body["learner_id"])
            boundary = getattr(self, "legacy_boundary", None)
            if boundary is not None:
                boundary.check_switch(con, actor_id=actor, browser_id=browser["id"])
            self.tombstone_legacy(con, actor)
            return self.rotate(con, browser, actor, "learner", body["learner_id"])
        if op == "logout":
            revision(body["expected_revision"], session["revision"])
            self.tombstone_legacy(con, actor)
            return self.rotate(con, browser)
        if op == "saveStart":
            learner = self.learner(con, session, params["learner_id"])
            old = self.start(con, learner)
            revision(body["expected_revision"], old["revision"])
            patch = body["answers"]
            if "age_band" in patch:
                self.age(patch["age_band"]["value"])
            choice = patch.get("chosen_start", {})
            if choice.get("state") == "accepted_default":
                if choice["recommendation_revision"] != old["recommendation_revision"] or choice["value"] != old["recommendation"]:
                    fail(409, "revision_conflict", "建议已变化，请读取后再确认。", "reload", old["revision"])
            answers = {**old["answers"], **patch}
            result = self.project_start(learner, answers, old["revision"]+1, iso(self.clock()))
            con.execute("INSERT INTO learn_starts VALUES(?,?,?) ON CONFLICT(learner_id) DO UPDATE SET revision=excluded.revision,body=excluded.body", (learner["id"], result["revision"], canonical(result)))
            con.execute("INSERT INTO learn_start_history VALUES(?,?,?)", (learner["id"], result["revision"], canonical(result)))
            return result, None
        if op in ("claimCase", "resolveCase"):
            case = self.case_access(con, session, params["case_id"])
            revision(body["expected_revision"], case["revision"])
            if op == "claimCase":
                if case["status"] != "open":
                    fail(409, "invalid_transition", "案件当前不能认领。", "reload")
                con.execute("UPDATE learn_cases SET status='claimed',revision=revision+1 WHERE id=?", (case["id"],))
            else:
                if case["status"] != "claimed" or body["decision"] not in ("verified", "rejected") or body["manual_findings"]:
                    fail(409, "invalid_transition", "本期只处理已认领关系案的核验结论。", "reload")
                learner = con.execute("SELECT * FROM learn_learners WHERE id=?", (case["learner_id"],)).fetchone()
                revision(body["target_revision"], learner["revision"])
                revision(body["target_revision"], case["target_revision"])
                evidence = {r[0] for r in con.execute("SELECT id FROM learn_evidence WHERE case_id=?", (case["id"],))}
                if not body["evidence_ids"] or not set(body["evidence_ids"]) <= evidence:
                    fail(422, "invalid_sources", "请引用该案件已记录的核验依据。")
                con.execute("UPDATE learn_links SET status=?,revision=revision+1,verification_method='manual_project_review',evidence_ids=?,reviewer_id=?,reviewed_at=? WHERE learner_id=?", (body["decision"], canonical(body["evidence_ids"]), actor, iso(self.clock()), learner["id"]))
                con.execute("UPDATE learn_learners SET revision=revision+1 WHERE id=?", (learner["id"],))
                con.execute("UPDATE learn_cases SET status='resolved',revision=revision+1,target_revision=?,feedback=? WHERE id=?", (learner["revision"]+1, body["note"], case["id"]))
                self.revoke_learner_sessions(con, learner["id"])
                self.audit(con, actor, "relationship_decision", case["id"], {"decision": body["decision"], "evidence_ids": body["evidence_ids"], "note": body["note"]})
            return self.case_view(con.execute("SELECT * FROM learn_cases WHERE id=?", (case["id"],)).fetchone()), None
        fail(503, "operation_unavailable", "该功能尚未实现。", "contact_support")

    # Server-only provisioning. No HTTP grant, approval, evidence upload or self-assignment route.
    def grant_staff(self, actor_id, scope, expires_at, *, authority):
        if scope not in ("relationship_review", "consent_read", "learning_review", "support", "report_review", "report_publish", "usage_reconcile") or expires_at <= self.clock() or not authority:
            raise ValueError("Explicit limited scope, expiry and authority are required")
        with self.store.transaction() as con:
            con.execute("INSERT INTO learn_grants VALUES(?,?,?) ON CONFLICT(actor_id,scope) DO UPDATE SET expires=excluded.expires", (actor_id, scope, expires_at))
            self.audit(con, None, "staff_grant", actor_id, {"scope": scope, "authority": authority, "expires_at": iso(expires_at)})

    def put_consent_text(self, text, *, authority):
        if not authority:
            raise ValueError("Text approval authority must be explicitly supplied")
        self.contract.check(text, self.contract.schemas["ConsentText"])
        content = {k: text[k] for k in ("locale", "title", "text", "scope_purposes")}
        content["scope_purposes"] = [{"scope": item["scope"], "purpose": item["purpose"]}
                                     for item in text["scope_purposes"]]
        # Contract specifies fixed key order, unlike request-body canonicalization.
        expected = digest(json.dumps(content, ensure_ascii=False, separators=(",", ":")))
        if text["text_sha256"] != expected:
            raise ValueError("Consent text checksum mismatch")
        with self.store.transaction() as con:
            old = con.execute("SELECT body FROM learn_texts WHERE version=?", (text["consent_version"],)).fetchone()
            if old and json.loads(old[0])["text_sha256"] != expected:
                raise ValueError("Text/purpose changes require a new version")
            con.execute("INSERT INTO learn_texts VALUES(?,?) ON CONFLICT(version) DO UPDATE SET body=excluded.body", (text["consent_version"], canonical(text)))
            if text["approval_status"] != "approved_for_pilot" or not text["acceptance_enabled"]:
                for row in con.execute("SELECT DISTINCT learner_id FROM learn_consents WHERE version=?", (text["consent_version"],)):
                    self.revoke_learner_sessions(con, row[0])
                    self.invalidate_learner_reports(con, row[0], reason="consent_text_withdrawn")
            self.audit(con, None, "consent_text_metadata", text["consent_version"], {"authority": authority, "text_sha256": expected, "approval_status": text["approval_status"], "acceptance_enabled": text["acceptance_enabled"]})

    def add_relationship_evidence(self, case_id, redacted_text, *, authority):
        if not authority or not isinstance(redacted_text, str) or not 1 <= len(redacted_text) <= 8000:
            raise ValueError("Evidence requires a redacted record and source authority")
        with self.store.transaction() as con:
            if not con.execute("SELECT 1 FROM learn_cases WHERE id=? AND status!='resolved'", (case_id,)).fetchone():
                raise ValueError("An open relationship case is required")
            eid = uid()
            con.execute("INSERT INTO learn_evidence VALUES(?,?,?,1)", (eid, case_id, redacted_text))
            self.audit(con, None, "relationship_evidence", eid, {"authority": authority, "case_id": case_id})
            return eid

    def revoke_relationship(self, learner_id, *, authority):
        if not authority:
            raise ValueError("Revocation requires authority")
        with self.store.transaction() as con:
            if not self.link(con, learner_id):
                raise ValueError("Unknown relationship")
            con.execute("UPDATE learn_links SET status='revoked',revision=revision+1 WHERE learner_id=?", (learner_id,))
            self.revoke_learner_sessions(con, learner_id)
            self.invalidate_learner_reports(con, learner_id, reason="relationship_revoked")
            self.audit(con, None, "relationship_revoked", learner_id, {"authority": authority})

    def legacy_request_guard(self, con, request, actor_id=None):
        """Call before every legacy credential issuer/read/write, including sbconn_."""
        browser = self.browser(con, request, required=False)
        if request.cookies.get(self.browser_cookie) and not browser:
            fail(401, "session_expired", "浏览器绑定已失效，请重新认证。", "reauthenticate")
        if browser and browser["mode"] == "learner":
            fail(403, "child_mode_restricted", "请通过学习入口重新认证后返回管理。")
        token = request.cookies.get(self.cookie_name)
        session = None
        if token:
            session = self.session_row(con, request, browser)
        epoch = con.execute("SELECT epoch FROM learn_auth_epochs WHERE actor_id=?", (actor_id,)).fetchone() if actor_id else None
        person = con.execute("SELECT token_hash FROM people WHERE id=?", (actor_id,)).fetchone() if actor_id else None
        if actor_id and not person:
            fail(401, "session_revoked", "账号身份已失效。", "reauthenticate")
        connection = None
        if actor_id:
            header = request.headers.get("authorization", "")
            bearer = header[7:] if header.startswith("Bearer ") and len(header) <= 600 else ""
            if bearer.startswith("sbconn_"):
                # Central still checks squad membership/action scopes. This only
                # binds the original credential to the fence and its revocation.
                connection = con.execute("SELECT * FROM core_connections WHERE token_hash=? AND user_id=?", (digest(bearer), actor_id)).fetchone()
                self.check_connection(connection)
            elif bearer:
                if not secrets.compare_digest(digest(bearer), person[0]):
                    fail(401, "session_revoked", "旧凭证已失效。", "reauthenticate")
            elif not session or session["actor_id"] != actor_id:
                fail(401, "session_revoked", "必须绑定本次请求实际验证的凭证。", "reauthenticate")
        return LegacyFence(actor_id, epoch[0] if epoch else 0, person[0] if person else None,
                           browser["id"] if browser else None, browser["epoch"] if browser else None, digest(token) if token else None,
                           connection["id"] if connection else None, connection["token_hash"] if connection else None)

    def check_connection(self, row):
        valid = False
        if row and not row["paused"] and not row["revoked"]:
            try:
                expiry = datetime.fromisoformat(row["expires_at"])
                valid = expiry.tzinfo is not None and expiry.timestamp() > self.clock()
            except ValueError:
                pass
        if not valid:
            fail(401, "session_revoked", "连接凭证已失效。", "reauthenticate")

    def legacy_commit_fence(self, con, fence):
        """On the SAME people DB transaction as the legacy write, BEFORE commit/dispatch.

        Caller must BEGIN IMMEDIATE before its first transactional read/write. This
        no-op write also acquires SQLite's write lock; busy/snapshot errors must
        roll back the whole legacy operation. Never call this on a second DB.
        """
        self.legacy_validate_fence(con, fence, write=True)

    def legacy_validate_fence(self, con, fence, *, write=False):
        """Validate on the caller's transaction; read checks never upgrade its lock."""
        if not con.in_transaction:
            raise RuntimeError("Commit fence requires the caller's active transaction")
        database = con.execute("PRAGMA database_list").fetchone()[2]
        from pathlib import Path
        if Path(database).resolve() != self.store.path:
            raise RuntimeError("Commit fence must use the same existing people database")
        if write:
            con.execute("UPDATE learn_secrets SET value=value WHERE name='hmac'")
        if fence.actor_id:
            epoch = con.execute("SELECT epoch FROM learn_auth_epochs WHERE actor_id=?", (fence.actor_id,)).fetchone()
            person = con.execute("SELECT token_hash FROM people WHERE id=?", (fence.actor_id,)).fetchone()
            if (epoch[0] if epoch else 0) != fence.auth_epoch or not person or person[0] != fence.token_hash:
                fail(401, "session_revoked", "提交前身份已失效，操作未保存。", "reauthenticate")
        if fence.browser_id:
            browser = con.execute("SELECT * FROM learn_browsers WHERE id=?", (fence.browser_id,)).fetchone()
            if not browser or browser["epoch"] != fence.mode_epoch or browser["mode"] == "learner" or browser["expires"] <= self.clock():
                fail(401, "session_revoked", "提交前浏览器身份已变化。", "reauthenticate")
        if fence.session_hash:
            session = con.execute("SELECT * FROM learn_sessions WHERE token_hash=?", (fence.session_hash,)).fetchone()
            if not session or session["revoked"] or session["expires"] <= self.clock():
                fail(401, "session_revoked", "提交前会话已失效。", "reauthenticate")
        if fence.connection_id:
            row = con.execute("SELECT * FROM core_connections WHERE id=? AND token_hash=? AND user_id=?", (fence.connection_id, fence.connection_hash, fence.actor_id)).fetchone()
            self.check_connection(row)

    def legacy_read_fence(self, fence):
        """Call immediately before serializing a private legacy response."""
        with self.store.transaction() as con:
            self.legacy_commit_fence(con, fence)
