"""Additive portfolio migrations, isolated from frozen learning checksums."""
import hashlib


PORTFOLIO_DDL = """
CREATE TABLE platform_external_works (
 id TEXT PRIMARY KEY, learner_id TEXT NOT NULL REFERENCES learn_learners(id),
 revision INTEGER NOT NULL CHECK(revision>=1), created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE platform_external_versions (
 id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES platform_external_works(id),
 number INTEGER NOT NULL CHECK(number>=1), body TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(work_id,number)
);
CREATE TABLE platform_competition_links (
 id TEXT PRIMARY KEY, learner_id TEXT NOT NULL REFERENCES learn_learners(id),
 project_id TEXT NOT NULL, source_actor_id TEXT NOT NULL REFERENCES people(id),
 source_revision INTEGER NOT NULL CHECK(source_revision>=1), source_hash TEXT NOT NULL,
 revision INTEGER NOT NULL CHECK(revision>=1), state TEXT NOT NULL CHECK(state IN ('offered','accepted','declined','revoked')),
 body TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(learner_id,project_id,source_actor_id)
);
CREATE TABLE platform_competition_link_history (
 link_id TEXT NOT NULL REFERENCES platform_competition_links(id), revision INTEGER NOT NULL,
 state TEXT NOT NULL, body TEXT NOT NULL, recorded_at TEXT NOT NULL,
 PRIMARY KEY(link_id,revision)
);
CREATE INDEX platform_external_learner ON platform_external_works(learner_id,updated_at,id);
CREATE INDEX platform_links_learner ON platform_competition_links(learner_id,state,id);
"""


def migrate_portfolio(store, timestamp):
    checksum = hashlib.sha256(PORTFOLIO_DDL.encode()).hexdigest()
    with store.transaction() as con:
        con.execute("CREATE TABLE IF NOT EXISTS platform_migrations(version TEXT PRIMARY KEY,checksum TEXT NOT NULL,applied_at TEXT NOT NULL)")
        old = con.execute("SELECT checksum FROM platform_migrations WHERE version='P01-portfolio'").fetchone()
        if old:
            if old[0] != checksum:
                raise ValueError("P01-portfolio migration checksum mismatch")
            return
        for statement in PORTFOLIO_DDL.split(";"):
            if statement.strip():
                con.execute(statement)
        con.execute("INSERT INTO platform_migrations VALUES('P01-portfolio',?,?)", (checksum, timestamp))
