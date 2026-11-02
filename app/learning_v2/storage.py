"""M01 additive migration. The caller must supply the existing people database."""
import hashlib
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DDL = """
CREATE TABLE learn_secrets (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE learn_browsers (id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, epoch INTEGER NOT NULL, mode TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE learn_auth_epochs (actor_id TEXT PRIMARY KEY REFERENCES people(id), epoch INTEGER NOT NULL);
CREATE TABLE learn_sessions (id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, browser_id TEXT NOT NULL REFERENCES learn_browsers(id), actor_id TEXT NOT NULL REFERENCES people(id), learner_id TEXT REFERENCES learn_learners(id), mode TEXT NOT NULL, epoch INTEGER NOT NULL, revision INTEGER NOT NULL, expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE INDEX learn_sessions_browser ON learn_sessions(browser_id);
CREATE TABLE learn_families (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL UNIQUE REFERENCES people(id), revision INTEGER NOT NULL);
CREATE TABLE learn_learners (id TEXT PRIMARY KEY, family_id TEXT NOT NULL UNIQUE REFERENCES learn_families(id), revision INTEGER NOT NULL, display_name TEXT NOT NULL, age_band TEXT, start_id TEXT NOT NULL UNIQUE);
CREATE TABLE learn_links (id TEXT PRIMARY KEY, learner_id TEXT NOT NULL UNIQUE REFERENCES learn_learners(id), actor_id TEXT NOT NULL REFERENCES people(id), revision INTEGER NOT NULL, status TEXT NOT NULL, declared_relationship TEXT NOT NULL, verification_method TEXT, evidence_ids TEXT, reviewer_id TEXT REFERENCES people(id), reviewed_at TEXT);
CREATE TABLE learn_texts (version TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE learn_consents (id TEXT PRIMARY KEY, learner_id TEXT NOT NULL REFERENCES learn_learners(id), submitted_by TEXT NOT NULL REFERENCES people(id), revision INTEGER NOT NULL, version TEXT NOT NULL REFERENCES learn_texts(version), scopes TEXT NOT NULL, status TEXT NOT NULL, recorded_at TEXT NOT NULL, text_hash TEXT NOT NULL);
CREATE INDEX learn_consents_learner ON learn_consents(learner_id, recorded_at, id);
CREATE TABLE learn_starts (learner_id TEXT PRIMARY KEY REFERENCES learn_learners(id), revision INTEGER NOT NULL, body TEXT NOT NULL);
CREATE TABLE learn_start_history (learner_id TEXT NOT NULL REFERENCES learn_learners(id), revision INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(learner_id, revision));
CREATE TABLE learn_grants (actor_id TEXT NOT NULL REFERENCES people(id), scope TEXT NOT NULL, expires REAL NOT NULL, PRIMARY KEY(actor_id, scope));
CREATE TABLE learn_cases (id TEXT PRIMARY KEY, learner_id TEXT NOT NULL UNIQUE REFERENCES learn_learners(id), assignee_id TEXT NOT NULL REFERENCES people(id), revision INTEGER NOT NULL, status TEXT NOT NULL, target_revision INTEGER NOT NULL, owner_display_name TEXT NOT NULL, due_at TEXT NOT NULL, support_contact_label TEXT NOT NULL, feedback TEXT);
CREATE TABLE learn_evidence (id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES learn_cases(id), redacted_text TEXT NOT NULL, version INTEGER NOT NULL);
CREATE TABLE learn_requests (actor_id TEXT NOT NULL, scope_id TEXT NOT NULL, operation TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, result TEXT NOT NULL, status INTEGER NOT NULL, before_session TEXT, after_session TEXT, PRIMARY KEY(actor_id,scope_id,operation,request_id));
CREATE TABLE learn_audit (id TEXT PRIMARY KEY, actor_id TEXT, action TEXT NOT NULL, target_id TEXT NOT NULL, recorded_at TEXT NOT NULL, details TEXT NOT NULL);
"""


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)
        if not self.path.is_file():
            raise ValueError("An explicit existing SQLite database is required")

    def connect(self):
        con = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, isolation_level=None, timeout=5)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    @contextmanager
    def transaction(self):
        con = self.connect()
        try:
            # All short identity reads/writes share the switch/commit serialization point.
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def migrate(self, timestamp):
        checksum = hashlib.sha256(DDL.encode()).hexdigest()
        with self.transaction() as con:
            columns = {r[1] for r in con.execute("PRAGMA table_info(people)")}
            if not {"id", "password_hash", "token_hash"}.issubset(columns):
                raise ValueError("Initialize existing people/password schema before M01")
            rate_columns = {r[1] for r in con.execute("PRAGMA table_info(login_attempts)")}
            if not {"key", "attempts", "blocked_until", "updated_at"}.issubset(rate_columns):
                raise ValueError("Initialize existing shared login_attempts schema before M01")
            exists = con.execute("SELECT 1 FROM sqlite_master WHERE name='learn_migrations'").fetchone()
            if exists:
                old = con.execute("SELECT checksum FROM learn_migrations WHERE version='M01'").fetchone()
                if not old or old[0] != checksum:
                    raise ValueError("M01 checksum mismatch; an explicit new migration is required")
                return
            if con.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'learn_*'").fetchone():
                raise ValueError("Unversioned learning tables require manual migration review")
            con.execute("CREATE TABLE learn_migrations(version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)")
            for statement in DDL.split(";"):
                if statement.strip():
                    con.execute(statement)
            con.execute("INSERT INTO learn_secrets VALUES('hmac',?)", (secrets.token_hex(32),))
            con.execute("INSERT INTO learn_migrations VALUES('M01',?,?)", (checksum, timestamp))
