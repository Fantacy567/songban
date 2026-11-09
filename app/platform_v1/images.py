"""Durable private image jobs. Saving assets never publishes or advances work.

All HTTP operations use the central platform session/CSRF/replay transaction.
Only execute()/worker_once() dispatch providers, after durable authorization and
budget checks. Unknown dispatches are never automatically sent a second time.
"""
from dataclasses import dataclass, field, replace
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
from typing import Annotated, Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from app.learning_v2.protocol import Problem, canonical, fail
from .doubao import DoubaoAdapter, ImageResult, ProviderRejected, ProviderUnknown, inspect_image
from .schemas import Identifier, StrictModel


IMAGE_PROMPT_VERSION = "songban-images@0.1.0"
IMAGE_SYSTEM_PROMPT = "请为孩子的创作制作合适的图片。不要包含私人身份信息；只创作图片，不宣称完成课程。"


@dataclass(frozen=True)
class ImageSettings:
    storage_dir: object = field(default=None, repr=False)
    config_version: str = "unconfigured"
    live_enabled: bool = False
    api_key: str = field(default="", repr=False)
    model: str = ""
    allowed_response_models: tuple = ()
    size: str = "2K"
    supports_sequential_generation: bool = True
    image_limit: int = 0
    max_concurrency: int = 1
    image_consent_versions: tuple = ()
    content_editors: tuple = ()
    sample_enabled: bool = False
    sample_path: object = field(default=None, repr=False)
    sample_limit: int = 0
    timeout_seconds: int = 60
    lease_seconds: int = 120
    max_bytes: int = 12582912
    max_pixels: int = 16777216
    transport: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if any(type(flag) is not bool for flag in (self.live_enabled, self.sample_enabled, self.supports_sequential_generation)):
            raise ValueError("Image switches must be booleans")
        if (type(self.image_limit) is not int or not 0 <= self.image_limit <= 10000
                or type(self.sample_limit) is not int or not 0 <= self.sample_limit <= 10000
                or type(self.max_concurrency) is not int or not 1 <= self.max_concurrency <= 8
                or not 1 <= self.timeout_seconds <= 120 or not self.timeout_seconds < self.lease_seconds <= 600
                or not 1024 <= self.max_bytes <= 25165824 or not 1 <= self.max_pixels <= 16777216):
            raise ValueError("Image limits must be explicit and bounded")
        for values in (self.allowed_response_models, self.image_consent_versions, self.content_editors):
            if not isinstance(values, tuple) or any(not isinstance(v, str) or not v or len(v) > 150 for v in values):
                raise ValueError("Image allowlists must be explicit tuples")
        if not isinstance(self.api_key, str) or len(self.api_key) > 4096 or any(c in self.api_key for c in "\r\n"):
            raise ValueError("Invalid provider configuration")
        for value in (self.model, self.config_version, self.size):
            if not isinstance(value, str) or len(value) > 150 or any(ord(c) < 32 for c in value):
                raise ValueError("Invalid image configuration")
        if self.storage_dir is not None:
            root = Path(self.storage_dir).expanduser().resolve()
            public = Path(__file__).resolve().parents[2] / "static"
            if root == Path(root.anchor) or root == public or public in root.parents:
                raise ValueError("Image storage must be a private directory")
            object.__setattr__(self, "storage_dir", root)
        if self.sample_path is not None:
            object.__setattr__(self, "sample_path", Path(self.sample_path).expanduser().resolve())

    def fingerprint(self):
        return hashlib.sha256(canonical({"version": self.config_version, "model": self.model,
            "key_hash": hashlib.sha256(self.api_key.encode()).hexdigest(), "size": self.size,
            "sequential": self.supports_sequential_generation, "allowed_models": list(self.allowed_response_models),
            "image_limit": self.image_limit, "consent_versions": list(self.image_consent_versions)}).encode()).hexdigest()


Purpose = Literal["course_cover", "work_cover", "illustration"]
Mode = Literal["live", "sample"]
State = Literal["queued", "dispatching", "unknown", "received", "stored", "storage_failed", "archived", "archive_conflict", "failed", "cancelled"]


class CreateImage(StrictModel):
    request_id: Identifier
    mode: Mode
    purpose: Purpose
    learner_id: Identifier | None = None
    target_id: Identifier
    target_version: Identifier
    expected_binding_revision: Annotated[int, Field(ge=0)]
    slot: Identifier
    prompt: Annotated[str, Field(min_length=1, max_length=1000)]

    @field_validator("prompt")
    @classmethod
    def present(cls, value):
        if not value.strip() or any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("A nonempty image prompt is required")
        return value.strip()

    @model_validator(mode="after")
    def appropriate_target(self):
        if (self.purpose == "course_cover") != (self.learner_id is None):
            raise ValueError("Image owner does not match purpose")
        if (self.purpose.endswith("cover") and self.slot != "cover") or (self.purpose == "illustration" and self.slot == "cover"):
            raise ValueError("Image slot does not match purpose")
        return self


class RecoverImage(StrictModel):
    request_id: Identifier


class ImageUsage(StrictModel):
    unit: Literal["images"]
    reserved: int
    settled: int
    status: Literal["sample", "held", "settled", "released"]
    notice: str


class ImageJob(StrictModel):
    id: str
    revision: int
    mode: Mode
    source: Literal["local_sample", "doubao", "test_fixture"] | None
    purpose: Purpose
    learner_id: str | None
    target_id: str
    target_version: str
    slot: str
    state: State
    asset_id: str | None
    binding_revision: int | None
    actual_model: str | None
    error_code: str | None
    can_recover: bool
    usage: ImageUsage
    created_at: str
    updated_at: str


class ImageBinding(StrictModel):
    purpose: Purpose
    slot: str
    binding_revision: int
    target_version: str
    asset_id: str
    mode: Mode
    source: Literal["local_sample", "doubao", "test_fixture"]
    created_at: str


class ImageJobList(StrictModel):
    items: list[ImageJob]


class WorkImages(StrictModel):
    target_id: str
    target_version: str
    cover_asset_id: str | None
    items: list[ImageBinding]


class ImageAsset(StrictModel):
    id: str
    mime: str
    width: int
    height: int
    byte_size: int
    sha256: str
    mode: Mode
    source: Literal["local_sample", "doubao", "test_fixture"]
    purpose: Purpose
    target_id: str
    target_version: str
    created_at: str


REQUEST_SCHEMAS = {"createImage": CreateImage, "recoverImage": RecoverImage}
RESPONSE_SCHEMAS = {"createImage": ImageJob, "imageJob": ImageJob, "recoverImage": ImageJob,
                    "workImages": WorkImages, "courseImages": WorkImages, "imageAsset": ImageAsset,
                    "workImageJobs": ImageJobList}
ROUTE_SPECS = (
    ("POST", "/image-jobs", "createImage", 202),
    ("GET", "/image-jobs/{job_id}", "imageJob", 200),
    ("POST", "/image-jobs/{job_id}/recover-storage", "recoverImage", 202),
    ("GET", "/learners/{learner_id}/works/{work_id}/images", "workImages", 200),
    ("GET", "/learners/{learner_id}/works/{work_id}/image-jobs", "workImageJobs", 200),
    ("GET", "/courses/{course_id}/images", "courseImages", 200),
    ("GET", "/assets/{asset_id}", "imageAsset", 200),
)


DDL = """
CREATE TABLE platform_image_budgets (
 subject TEXT NOT NULL, config_hash TEXT NOT NULL, granted INTEGER NOT NULL CHECK(granted>=0),
 held INTEGER NOT NULL DEFAULT 0 CHECK(held>=0), settled INTEGER NOT NULL DEFAULT 0 CHECK(settled>=0),
 expires REAL NOT NULL, PRIMARY KEY(subject,config_hash), CHECK(held+settled<=granted)
);
CREATE TABLE platform_image_grants (grant_key TEXT PRIMARY KEY,fingerprint TEXT NOT NULL);
CREATE TABLE platform_image_jobs (
 id TEXT PRIMARY KEY, revision INTEGER NOT NULL, actor_id TEXT NOT NULL REFERENCES people(id),
 learner_id TEXT REFERENCES learn_learners(id), session_id TEXT NOT NULL REFERENCES learn_sessions(id),
 mode TEXT NOT NULL, purpose TEXT NOT NULL, target_id TEXT NOT NULL,target_version TEXT NOT NULL,slot TEXT NOT NULL,
 expected_binding_revision INTEGER NOT NULL, subject TEXT NOT NULL,config_hash TEXT NOT NULL,
 state TEXT NOT NULL,prompt TEXT NOT NULL,lease_token TEXT,lease_until REAL,fence INTEGER NOT NULL DEFAULT 0,
 result_bytes BLOB,result_meta TEXT,result_asset_id TEXT NOT NULL,provider_request_id TEXT,
 actual_model TEXT,source TEXT,error_code TEXT,binding_revision INTEGER,usage_status TEXT NOT NULL,
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL
);
CREATE INDEX platform_image_pending ON platform_image_jobs(state,created_at);
CREATE TABLE platform_image_ledger (
 job_id TEXT PRIMARY KEY REFERENCES platform_image_jobs(id),status TEXT NOT NULL,units INTEGER,
 evidence TEXT NOT NULL,recorded_at TEXT NOT NULL
);
CREATE TABLE platform_image_assets (
 id TEXT PRIMARY KEY,job_id TEXT NOT NULL UNIQUE REFERENCES platform_image_jobs(id),learner_id TEXT REFERENCES learn_learners(id),
 actor_id TEXT NOT NULL REFERENCES people(id),purpose TEXT NOT NULL,target_id TEXT NOT NULL,target_version TEXT NOT NULL,
 storage_key TEXT NOT NULL UNIQUE,mime TEXT NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,byte_size INTEGER NOT NULL,
 sha256 TEXT NOT NULL,mode TEXT NOT NULL,source TEXT NOT NULL,created_at TEXT NOT NULL
);
CREATE TABLE platform_image_bindings (
 target_kind TEXT NOT NULL,target_id TEXT NOT NULL,slot TEXT NOT NULL,revision INTEGER NOT NULL,
 target_version TEXT NOT NULL,asset_id TEXT NOT NULL REFERENCES platform_image_assets(id),
 purpose TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(target_kind,target_id,slot)
);
CREATE TABLE platform_image_binding_history (
 target_kind TEXT NOT NULL,target_id TEXT NOT NULL,slot TEXT NOT NULL,revision INTEGER NOT NULL,
 target_version TEXT NOT NULL,asset_id TEXT NOT NULL REFERENCES platform_image_assets(id),purpose TEXT NOT NULL,created_at TEXT NOT NULL,
 PRIMARY KEY(target_kind,target_id,slot,revision)
);
"""

SNAPSHOT_DDL = """
CREATE TABLE platform_image_input_snapshots (
 job_id TEXT PRIMARY KEY REFERENCES platform_image_jobs(id),body TEXT NOT NULL
);
"""


def validate_request(op, body):
    try:
        return REQUEST_SCHEMAS[op].model_validate(body).model_dump()
    except (KeyError, ValidationError):
        fail(422, "invalid_input", "请核对图片用途、归属、版本及提示内容。")


def absent():
    fail(404, "resource_not_found", "找不到可访问的图片或生成记录。")


def runtime_snapshot(*, transaction=False):
    """One immutable settings/adapter pair per operation, never a shared swap."""
    def decorate(method):
        @wraps(method)
        def invoke(self, *args, **kwargs):
            if self.runtime_provider is not None:
                con = (args[0] if args else kwargs.get('con')) if transaction else None
                config = self.runtime_provider(con=con)
                if not isinstance(config, ImageSettings):
                    raise TypeError('Image runtime must return frozen ImageSettings')
                snapshot = ImageService(self.store, self.learning, self.portfolio,
                                        replace(self.settings, image_settings=config))
                snapshot.current_config = self.runtime_provider
                return method(snapshot, *args, **kwargs)
            return method(self, *args, **kwargs)
        return invoke
    return decorate


class ImageService:
    def __init__(self, store, learning, portfolio, settings):
        self.store, self.learning, self.portfolio, self.settings = store, learning, portfolio, settings
        self.config = settings.image_settings
        if self.config is not None and not isinstance(self.config, ImageSettings):
            raise TypeError("Explicit ImageSettings required")
        self.adapter = DoubaoAdapter(self.config) if self.config else None
        self.runtime_provider = None
        self.current_config = None

    def bind_runtime(self, provider):
        if self.runtime_provider is not None or not callable(provider):
            raise ValueError("Image runtime already bound or invalid")
        self.runtime_provider = provider

    def _check_config(self, con, row):
        current = self.current_config(con=con) if self.current_config else self.config
        if (not self.settings.enabled or not current or not self.config
                or row['config_hash'] != self.config.fingerprint() or row['config_hash'] != current.fingerprint()
                or (row['mode'] == 'live' and not current.live_enabled)):
            fail(403, 'image_configuration_changed', '图片配置已经变化，请核对已保存结果。')

    @runtime_snapshot(transaction=True)
    def cancel_stale_queued(self, con):
        """Administrative changes cancel only work that has not been dispatched."""
        for row in con.execute("SELECT * FROM platform_image_jobs WHERE state='queued'").fetchall():
            try:
                self._check_config(con, row)
            except Problem as error:
                self._settle(con, row, 'released', 'not_dispatched:' + error.code)
                self._state(con, row['id'], 'cancelled', error.code)

    @property
    @runtime_snapshot()
    def live_available(self):
        c = self.config
        return bool(self.settings.enabled and c and c.live_enabled and c.api_key and c.model and c.storage_dir and c.image_limit > 0)

    @property
    @runtime_snapshot()
    def sample_available(self):
        c = self.config
        return bool(self.settings.enabled and self.settings.demo_mode and c and c.sample_enabled and c.sample_limit > 0
                    and c.storage_dir and c.sample_path and c.sample_path.is_file())

    @property
    def available(self):
        return self.live_available or self.sample_available

    def migrate(self):
        with self.store.transaction() as con:
            con.execute("CREATE TABLE IF NOT EXISTS platform_migrations(version TEXT PRIMARY KEY,checksum TEXT NOT NULL,applied_at TEXT NOT NULL)")
            for version, ddl in (("P03-images", DDL), ("P03B-image-inputs", SNAPSHOT_DDL)):
                checksum = hashlib.sha256(ddl.encode()).hexdigest()
                old = con.execute("SELECT checksum FROM platform_migrations WHERE version=?", (version,)).fetchone()
                if old:
                    if old[0] != checksum:
                        raise ValueError(version + " migration checksum mismatch")
                    continue
                for statement in ddl.split(";"):
                    if statement.strip():
                        con.execute(statement)
                con.execute("INSERT INTO platform_migrations VALUES(?,?,?)", (version, checksum, self.learning.stamp()))

    def _target(self, con, session, target, *, writing=False, current=False):
        if target["purpose"] == "course_cover":
            if not self.config or session["mode"] not in ("manager", "staff") or session["actor_id"] not in self.config.content_editors:
                absent()
            course = self.learning.obj(con, target["target_id"], "course")
            version = str(course["revision"])
            kind = "course"
        else:
            if writing:
                self.learning.role(session, "learner")
            work = self.portfolio.read(con, "work", session,
                {"learner_id": target["learner_id"], "work_id": target["target_id"]}, {})
            version = work["current_version"]["id"]
            kind = "work"
        if current and version != target["target_version"]:
            fail(409, "source_changed", "作品或课程版本已变化，请保留图片并重新核对关联。", "reload")
        return kind, version

    def _job(self, con, job_id):
        row = con.execute("SELECT * FROM platform_image_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            absent()
        return row

    def _asset(self, con, asset_id):
        row = con.execute("SELECT * FROM platform_image_assets WHERE id=?", (asset_id,)).fetchone()
        if not row:
            absent()
        return row

    @runtime_snapshot(transaction=True)
    def authorize(self, con, op, session, params, body=None):
        if op == "createImage":
            b = validate_request(op, body)
            self._target(con, session, b, writing=True)
        elif op in ("imageJob", "recoverImage"):
            row = self._job(con, params["job_id"])
            self._target(con, session, row, writing=op == "recoverImage")
        elif op == "imageAsset":
            self._target(con, session, self._asset(con, params["asset_id"]))
        elif op in ("workImages", "workImageJobs"):
            self._target(con, session, {"purpose": "work_cover", "learner_id": params["learner_id"], "target_id": params["work_id"]})
        elif op == "courseImages":
            self._target(con, session, {"purpose": "course_cover", "target_id": params["course_id"]})
        else:
            raise ValueError("Unknown image operation")

    def _live_consent(self, con, session, target):
        if target["purpose"] == "course_cover":
            return
        c = self.config
        if not c or not c.image_consent_versions:
            fail(403, "image_consent_required", "图像处理用途尚未配置有效授权文本。")
        for row in con.execute("SELECT * FROM learn_consents WHERE learner_id=?", (target["learner_id"],)):
            if row["version"] in c.image_consent_versions and "live_model" in self.learning.effective(con, row):
                return
        fail(403, "image_consent_required", "适用于图像处理的真实模型授权尚未建立或已经撤回。")

    def _starting_session(self, con, row):
        session = con.execute("""SELECT s.*,b.epoch AS current_epoch,b.expires AS browser_expires
            FROM learn_sessions s JOIN learn_browsers b ON b.id=s.browser_id WHERE s.id=?""", (row["session_id"],)).fetchone()
        if (not session or session["revoked"] or session["expires"] <= self.learning.clock()
                or session["browser_expires"] <= self.learning.clock() or session["epoch"] != session["current_epoch"]
                or session["actor_id"] != row["actor_id"] or session["learner_id"] != row["learner_id"]):
            fail(403, "session_revoked", "发起图片请求的身份已经失效。")
        if session["mode"] == "staff" and not self.learning.scopes(con, session["actor_id"]):
            fail(403, "session_revoked", "发起图片请求的后台权限已经失效。")
        self._target(con, session, row, writing=True, current=True)
        if row["mode"] == "live":
            self._live_consent(con, session, row)
        return session

    def _view(self, row):
        status = row["usage_status"]
        usage = {"unit": "images", "reserved": 1 if status == "held" else 0, "settled": 1 if status == "settled" else 0,
                 "status": status, "notice": "本地样例，不是AI生成，未使用真实图片额度。" if status == "sample" else
                 "已保留一次图片请求额度，结果未确定时不会自动重发。" if status == "held" else
                 "已占用一次图片额度；实际费用以供应商账单为准。" if status == "settled" else "确定未生成，保留额度已释放。"}
        return {"id": row["id"], "revision": row["revision"], "mode": row["mode"], "source": row["source"],
                "purpose": row["purpose"], "learner_id": row["learner_id"], "target_id": row["target_id"],
                "target_version": row["target_version"], "slot": row["slot"], "state": row["state"],
                "asset_id": row["result_asset_id"] if row["state"] in ("stored", "archived", "archive_conflict") else None,
                "binding_revision": row["binding_revision"], "actual_model": row["actual_model"], "error_code": row["error_code"],
                "can_recover": row["state"] == "storage_failed" and row["result_bytes"] is not None,
                "usage": usage, "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def _binding_view(self, row):
        return {"purpose": row["purpose"], "slot": row["slot"], "binding_revision": row["revision"],
                "target_version": row["target_version"], "asset_id": row["asset_id"], "mode": row["mode"],
                "source": row["source"], "created_at": row["created_at"]}

    @runtime_snapshot(transaction=True)
    def read(self, con, op, session, params, query=None):
        self.authorize(con, op, session, params)
        if query:
            fail(422, "invalid_input", "图片接口不支持该查询参数。")
        if op == "imageJob":
            return self._view(self._job(con, params["job_id"]))
        if op == "imageAsset":
            row = self._asset(con, params["asset_id"])
            return {key: row[key] for key in ("id", "mime", "width", "height", "byte_size", "sha256", "mode", "source", "purpose", "target_id", "target_version", "created_at")}
        if op == "workImageJobs":
            rows = con.execute("""SELECT * FROM platform_image_jobs WHERE learner_id=? AND target_id=?
                AND purpose IN ('work_cover','illustration') ORDER BY created_at DESC,id DESC LIMIT 20""",
                (params["learner_id"], params["work_id"])).fetchall()
            items = []
            for row in rows:
                self._target(con, session, row)
                items.append(self._view(row))
            return {"items": items}
        if op in ("workImages", "courseImages"):
            target = {"purpose": "work_cover", "target_id": params["work_id"], "learner_id": params["learner_id"]} if op == "workImages" else {"purpose": "course_cover", "target_id": params["course_id"]}
            kind, version = self._target(con, session, target)
            rows = con.execute("""SELECT b.*,a.mode,a.source FROM platform_image_bindings b
                JOIN platform_image_assets a ON a.id=b.asset_id WHERE b.target_kind=? AND b.target_id=? ORDER BY b.slot""",
                (kind, target["target_id"])).fetchall()
            return {"target_id": target["target_id"], "target_version": version,
                    "cover_asset_id": next((row["asset_id"] for row in rows if row["slot"] == "cover" and row["target_version"] == version), None),
                    "items": [self._binding_view(row) for row in rows]}
        raise ValueError("Not an image read operation")

    @runtime_snapshot()
    def grant_budget(self, subject, images, *, grant_key, expires, authority):
        """Server-only reviewed allocation; no HTTP grant or implicit account."""
        c = self.config
        if not c or not authority or not grant_key or type(images) is not int or not 0 < images <= c.image_limit or expires <= self.learning.clock():
            raise ValueError("Explicit image allocation and authority required")
        if not isinstance(subject, str) or not subject.startswith(("learner:", "actor:")):
            raise ValueError("Unknown image budget subject")
        config_hash = c.fingerprint()
        digest = hashlib.sha256(canonical([subject, images, expires, config_hash, authority]).encode()).hexdigest()
        with self.store.transaction() as con:
            if self.current_config and self.current_config(con=con).fingerprint() != config_hash:
                raise ValueError('Image configuration changed before allocation')
            table = "learn_learners" if subject.startswith("learner:") else "people"
            if not con.execute("SELECT 1 FROM " + table + " WHERE id=?", (subject.split(":", 1)[1],)).fetchone():
                raise ValueError("Unknown image budget subject")
            old = con.execute("SELECT fingerprint FROM platform_image_grants WHERE grant_key=?", (grant_key,)).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError("Image grant key conflict")
                return
            account = con.execute("SELECT * FROM platform_image_budgets WHERE subject=? AND config_hash=?", (subject, config_hash)).fetchone()
            if account and account["granted"] + images > c.image_limit:
                raise ValueError("Image grant exceeds configured ceiling")
            con.execute("""INSERT INTO platform_image_budgets VALUES(?,?,?,0,0,?) ON CONFLICT(subject,config_hash)
                DO UPDATE SET granted=granted+excluded.granted,expires=excluded.expires""", (subject, config_hash, images, expires))
            con.execute("INSERT INTO platform_image_grants VALUES(?,?)", (grant_key, digest))

    def _settle(self, con, row, outcome, evidence):
        if row["mode"] != "live" or row["usage_status"] != "held":
            return
        units = 1 if outcome == "settled" else 0
        con.execute("UPDATE platform_image_budgets SET held=held-1,settled=settled+? WHERE subject=? AND config_hash=?", (units, row["subject"], row["config_hash"]))
        con.execute("UPDATE platform_image_jobs SET usage_status=? WHERE id=?", (outcome, row["id"]))
        con.execute("INSERT INTO platform_image_ledger VALUES(?,?,?,?,?)", (row["id"], outcome, units, evidence, self.learning.stamp()))

    @runtime_snapshot(transaction=True)
    def write(self, con, op, session, params, body):
        self.authorize(con, op, session, params, body)
        b = validate_request(op, body)
        stamp = self.learning.stamp()
        if op == "recoverImage":
            row = self._job(con, params["job_id"])
            if row["state"] != "storage_failed" or row["result_bytes"] is None:
                fail(409, "image_recovery_unavailable", "只有已取得图片但保存失败的请求可以恢复；不会重新出图。", "reload")
            con.execute("UPDATE platform_image_jobs SET state='received',error_code=NULL,revision=revision+1,updated_at=? WHERE id=?", (stamp, row["id"]))
            return self._view(self._job(con, row["id"]))
        if op != "createImage":
            raise ValueError("Not an image write operation")
        if not self.settings.enabled:
            fail(423, "platform_paused", "新的图片请求暂时暂停。")
        if (b["mode"] == "live" and not self.live_available) or (b["mode"] == "sample" and not self.sample_available):
            fail(503, "image_unavailable", "豆包图片生成尚未配置；本地样例也需显式开启。", "contact_support")
        kind, _ = self._target(con, session, b, writing=True, current=True)
        prior_binding = con.execute("SELECT revision FROM platform_image_bindings WHERE target_kind=? AND target_id=? AND slot=?", (kind, b["target_id"], b["slot"])).fetchone()
        if (prior_binding[0] if prior_binding else 0) != b["expected_binding_revision"]:
            fail(409, "revision_conflict", "图片位置已有新版本，请先读取当前图片。", "reload")
        if con.execute("""SELECT 1 FROM platform_image_jobs WHERE target_id=? AND slot=? AND
            state IN ('queued','dispatching','unknown','received','stored','storage_failed')""", (b["target_id"], b["slot"])).fetchone():
            fail(409, "image_job_unsettled", "这个图片位置已有待核对请求，请读取原结果，勿重复生成。", "reload")
        c = self.config
        subject = "learner:" + b["learner_id"] if b["learner_id"] else "actor:" + session["actor_id"]
        config_hash = c.fingerprint()
        self._check_config(con, {'mode': b['mode'], 'config_hash': config_hash})
        if b["mode"] == "live":
            self._live_consent(con, session, b)
            account = con.execute("SELECT * FROM platform_image_budgets WHERE subject=? AND config_hash=?", (subject, config_hash)).fetchone()
            # Configuration rotation never grants a fresh global allowance.
            total = con.execute("SELECT COALESCE(SUM(held+settled),0) FROM platform_image_budgets").fetchone()[0]
            if not account or account["expires"] <= self.learning.clock() or account["granted"] <= account["held"] + account["settled"] or total >= c.image_limit:
                fail(403, "image_budget_required", "图片额度尚未配置、已用完或有结果需要核对。", "contact_support")
            con.execute("UPDATE platform_image_budgets SET held=held+1 WHERE subject=? AND config_hash=?", (subject, config_hash))
        elif con.execute("SELECT COUNT(*) FROM platform_image_jobs WHERE mode='sample'", ()).fetchone()[0] >= c.sample_limit:
            fail(403, "sample_limit_reached", "本次演示的本地图片样例次数已用完。")
        job_id, asset_id = "pij_" + secrets.token_hex(16), "pia_" + secrets.token_hex(16)
        con.execute("""INSERT INTO platform_image_jobs
            (id,revision,actor_id,learner_id,session_id,mode,purpose,target_id,target_version,slot,expected_binding_revision,
             subject,config_hash,state,prompt,result_asset_id,usage_status,created_at,updated_at)
            VALUES(?,1,?,?,?,?,?,?,?,?,?,?,?,'queued',?,?,?, ?,?)""",
            (job_id, session["actor_id"], b["learner_id"], session["id"], b["mode"], b["purpose"], b["target_id"], b["target_version"], b["slot"],
             b["expected_binding_revision"], subject, config_hash, b["prompt"], asset_id, "held" if b["mode"] == "live" else "sample", stamp, stamp))
        con.execute("INSERT INTO platform_image_input_snapshots VALUES(?,?)", (job_id, canonical({
            "prompt_version": IMAGE_PROMPT_VERSION, "system_prompt": IMAGE_SYSTEM_PROMPT,
            "config_version": c.config_version, "requested_model": c.model if b["mode"] == "live" else None,
            "size": c.size, "supports_sequential_generation": c.supports_sequential_generation,
            "target_version": b["target_version"], "mode": b["mode"]})))
        return self._view(self._job(con, job_id))

    @runtime_snapshot(transaction=True)
    def replay(self, con, op, session, params, body, cached_result):
        self.authorize(con, op, session, params, body)
        return self.read(con, "imageJob", session, {"job_id": cached_result["id"]}, {})

    def _state(self, con, jid, state, error=None):
        con.execute("UPDATE platform_image_jobs SET state=?,error_code=?,revision=revision+1,updated_at=? WHERE id=?", (state, error, self.learning.stamp(), jid))

    def _save_file(self, asset_id, content, meta):
        if not self.config or not self.config.storage_dir:
            raise OSError("Private image storage unavailable")
        root = self.config.storage_dir
        root.mkdir(parents=True, exist_ok=True)
        target = root / (asset_id + meta["extension"])
        if target.is_symlink() or target.resolve().parent != root:
            raise OSError("Unsafe asset path")
        digest = hashlib.sha256(content).hexdigest()
        if target.exists():
            if target.stat().st_size != len(content) or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise OSError("Asset integrity mismatch")
            return target.name
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=root, prefix=".image-", delete=False) as output:
                temporary = output.name
                output.write(content); output.flush(); os.fsync(output.fileno())
            os.replace(temporary, target)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        return target.name

    def _archive(self, job_id):
        with self.store.transaction() as con:
            row = self._job(con, job_id)
            if row["state"] not in ("received", "stored"):
                return self._view(row)
            content, meta = row["result_bytes"], json.loads(row["result_meta"])
            asset_id = row["result_asset_id"]
        try:
            storage_key = self._save_file(asset_id, content, meta)
        except OSError:
            with self.store.transaction() as con:
                row = self._job(con, job_id)
                if row["state"] in ("received", "stored"):
                    self._state(con, job_id, "storage_failed", "private_storage_failed")
                return self._view(self._job(con, job_id))
        with self.store.transaction() as con:
            row = self._job(con, job_id)
            if row["state"] not in ("received", "stored"):
                return self._view(row)
            con.execute("""INSERT OR IGNORE INTO platform_image_assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (asset_id, job_id, row["learner_id"], row["actor_id"], row["purpose"], row["target_id"], row["target_version"], storage_key,
                 meta["mime"], meta["width"], meta["height"], meta["byte_size"], hashlib.sha256(content).hexdigest(), row["mode"], row["source"], self.learning.stamp()))
            self._state(con, job_id, "stored")
            try:
                self._check_config(con, row)
                session = self._starting_session(con, row)
                kind, _ = self._target(con, session, row, writing=True, current=True)
                binding = con.execute("SELECT revision FROM platform_image_bindings WHERE target_kind=? AND target_id=? AND slot=?", (kind, row["target_id"], row["slot"])).fetchone()
                rev = binding[0] if binding else 0
                if rev != row["expected_binding_revision"]:
                    fail(409, "revision_conflict", "图片位置已有新版本。")
            except Problem as error:
                self._state(con, job_id, "archive_conflict", error.code)
                return self._view(self._job(con, job_id))
            values = (kind, row["target_id"], row["slot"], rev + 1, row["target_version"], asset_id, row["purpose"], self.learning.stamp())
            con.execute("""INSERT INTO platform_image_bindings VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(target_kind,target_id,slot)
                DO UPDATE SET revision=excluded.revision,target_version=excluded.target_version,asset_id=excluded.asset_id,purpose=excluded.purpose,created_at=excluded.created_at""", values)
            con.execute("INSERT INTO platform_image_binding_history VALUES(?,?,?,?,?,?,?,?)", values)
            con.execute("UPDATE platform_image_jobs SET binding_revision=? WHERE id=?", (rev + 1, job_id))
            self._state(con, job_id, "archived")
            return self._view(self._job(con, job_id))

    @runtime_snapshot()
    def execute(self, job_id):
        """At most one dispatch. A restart may store received bytes, not re-generate."""
        with self.store.transaction() as con:
            row = self._job(con, job_id)
            if row["state"] == "dispatching" and row["lease_until"] <= self.learning.clock():
                self._state(con, job_id, "unknown", "provider_result_unknown")
                return self._view(self._job(con, job_id))
            state = row["state"]
            if state not in ("queued", "received", "stored"):
                return self._view(row)
            if state == "queued":
                try:
                    self._starting_session(con, row)
                    snapshot_row = con.execute("SELECT body FROM platform_image_input_snapshots WHERE job_id=?", (job_id,)).fetchone()
                    if not snapshot_row:
                        fail(403, "image_input_unavailable", "原图片请求缺少可核对的版本快照。")
                    input_snapshot = json.loads(snapshot_row["body"])
                    self._check_config(con, row)
                    if row["mode"] == "live":
                        if not self.live_available:
                            fail(503, "image_unavailable", "图片服务尚未配置。")
                        account = con.execute("SELECT * FROM platform_image_budgets WHERE subject=? AND config_hash=?", (row["subject"], row["config_hash"])).fetchone()
                        if not account or account["expires"] <= self.learning.clock():
                            fail(403, "image_budget_required", "图片额度已过期。")
                        active = con.execute("SELECT COUNT(*) FROM platform_image_jobs WHERE mode='live' AND state IN ('dispatching','unknown')").fetchone()[0]
                        if active >= self.config.max_concurrency:
                            return self._view(row)
                    elif not self.sample_available:
                        fail(503, "sample_unavailable", "本地样例未开启。")
                except Problem as error:
                    self._settle(con, row, "released", "not_dispatched:" + error.code)
                    self._state(con, job_id, "cancelled", error.code)
                    return self._view(self._job(con, job_id))
                token = secrets.token_hex(24)
                con.execute("UPDATE platform_image_jobs SET state='dispatching',lease_token=?,lease_until=?,fence=fence+1,revision=revision+1,updated_at=? WHERE id=?",
                            (token, self.learning.clock() + self.config.lease_seconds, self.learning.stamp(), job_id))
                fence = row["fence"] + 1
                prompt, mode = row["prompt"], row["mode"]
        if state in ("received", "stored"):
            return self._archive(job_id)
        try:
            if mode == "sample":
                path = self.config.sample_path
                if path.stat().st_size > self.config.max_bytes:
                    raise ProviderRejected("Local sample exceeds size limit")
                result = ImageResult(path.read_bytes(), source="local_sample")
            else:
                result = self.adapter.generate(input_snapshot["system_prompt"] + "\n" + prompt)
            meta = inspect_image(result.content, max_bytes=self.config.max_bytes, max_pixels=self.config.max_pixels)
            if result.source not in ("local_sample", "doubao", "test_fixture"):
                raise ValueError("Invalid image source")
        except ProviderRejected:
            with self.store.transaction() as con:
                row = self._job(con, job_id)
                if row["lease_token"] == token and row["fence"] == fence and row["state"] in ("dispatching", "unknown"):
                    self._settle(con, row, "released", "provider_rejected")
                    self._state(con, job_id, "failed", "provider_rejected")
                return self._view(self._job(con, job_id))
        except Exception:
            with self.store.transaction() as con:
                row = self._job(con, job_id)
                if row["lease_token"] == token and row["fence"] == fence and row["state"] in ("dispatching", "unknown"):
                    self._state(con, job_id, "unknown" if mode == "live" else "failed",
                                "provider_result_unknown" if mode == "live" else "sample_invalid")
                return self._view(self._job(con, job_id))
        with self.store.transaction() as con:
            row = self._job(con, job_id)
            if row["lease_token"] != token or row["fence"] != fence or row["state"] not in ("dispatching", "unknown"):
                return self._view(row)
            con.execute("UPDATE platform_image_jobs SET result_bytes=?,result_meta=?,source=?,actual_model=?,provider_request_id=? WHERE id=?",
                        (result.content, canonical(meta), result.source, result.actual_model, result.provider_request_id, job_id))
            self._settle(con, row, "settled", "one_returned_image:" + (result.provider_request_id or "provider_receipt_unavailable"))
            self._state(con, job_id, "received")
        return self._archive(job_id)

    def worker_once(self):
        """Run one persisted item; caller schedules this outside request handlers."""
        with self.store.transaction() as con:
            row = con.execute("""SELECT id FROM platform_image_jobs WHERE state IN ('queued','received','stored')
                OR (state='dispatching' AND lease_until<=?) ORDER BY created_at,id LIMIT 1""", (self.learning.clock(),)).fetchone()
        return self.execute(row[0]) if row else None

    @runtime_snapshot()
    def reconcile_unknown(self, job_id, *, outcome, evidence_id, authority, result=None):
        """Server-only evidence reconciliation, with no provider dispatch.

        An operator must obtain actual provider evidence. Passing time, a caller's
        guess, or a page refresh is not evidence. No public route is exported.
        """
        if (outcome not in ("not_generated", "generated_missing", "received") or not authority or not evidence_id
                or not isinstance(evidence_id, str) or len(evidence_id) > 200):
            raise ValueError("Explicit image evidence and authority required")
        meta = None
        if outcome == "received":
            if (not isinstance(result, ImageResult) or result.source not in ("doubao", "test_fixture")
                    or not result.actual_model or result.generated_images != 1 or not result.provider_request_id):
                raise ValueError("Verified provider image receipt required")
            meta = inspect_image(result.content, max_bytes=self.config.max_bytes if self.config else 12582912,
                                 max_pixels=self.config.max_pixels if self.config else 16777216)
        with self.store.transaction() as con:
            row = self._job(con, job_id)
            if row["state"] != "unknown" or row["mode"] != "live":
                fail(409, "image_reconciliation_conflict", "该图片请求已核对或不需要未知结果核对。", "reload")
            # Fence out a still-running request before applying verified evidence.
            con.execute("UPDATE platform_image_jobs SET fence=fence+1,lease_token=NULL,lease_until=NULL WHERE id=?", (job_id,))
            self._settle(con, row, "released" if outcome == "not_generated" else "settled", "verified:" + evidence_id)
            if outcome == "received":
                con.execute("UPDATE platform_image_jobs SET result_bytes=?,result_meta=?,source=?,actual_model=?,provider_request_id=? WHERE id=?",
                            (result.content, canonical(meta), result.source, result.actual_model, result.provider_request_id, job_id))
                self._state(con, job_id, "received")
            else:
                self._state(con, job_id, "cancelled" if outcome == "not_generated" else "failed",
                            "verified_not_generated" if outcome == "not_generated" else "image_result_unrecoverable")
            self.learning.audit(con, None, "platform:image_reconciled", job_id,
                                {"authority": authority, "evidence_id": evidence_id, "outcome": outcome})
            view = self._view(self._job(con, job_id))
        return self._archive(job_id) if outcome == "received" else view

    @runtime_snapshot(transaction=True)
    def asset_content(self, con, session, asset_id):
        self.authorize(con, "imageAsset", session, {"asset_id": asset_id})
        row = self._asset(con, asset_id)
        root = self.config.storage_dir if self.config else None
        if not root:
            fail(503, "storage_unavailable", "图片保存目录暂不可用，请保留原记录。", "reload")
        path = root / row["storage_key"]
        try:
            if path.is_symlink() or path.resolve().parent != root or path.stat().st_size != row["byte_size"]:
                raise OSError("Invalid private asset")
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != row["sha256"]:
                raise OSError("Image integrity mismatch")
        except OSError:
            fail(503, "storage_unavailable", "图片文件暂不可用；不会重新调用模型。", "reload")
        self.authorize(con, "imageAsset", session, {"asset_id": asset_id})
        return content, row["mime"]
