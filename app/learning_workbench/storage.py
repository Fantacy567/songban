# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
import hashlib

DDL = '''
CREATE TABLE learning_workbench_sessions (
 id TEXT PRIMARY KEY, owner TEXT NOT NULL, course_id TEXT NOT NULL, title TEXT NOT NULL,
 revision INTEGER NOT NULL CHECK(revision>=1), selected_artifact_id TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(owner,course_id));
CREATE TABLE learning_workbench_messages (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES learning_workbench_sessions(id),
 user_text TEXT NOT NULL, assistant_text TEXT, mode TEXT NOT NULL,
 status TEXT NOT NULL, actual_model TEXT, artifact TEXT, created_at TEXT NOT NULL);
CREATE INDEX learning_workbench_history ON learning_workbench_messages(session_id);
CREATE TABLE learning_workbench_jobs (
 message_id TEXT PRIMARY KEY REFERENCES learning_workbench_messages(id),
 session_id TEXT NOT NULL REFERENCES learning_workbench_sessions(id), owner TEXT NOT NULL,
 mode TEXT NOT NULL, state TEXT NOT NULL, counted INTEGER NOT NULL,
 config_hash TEXT NOT NULL, auth_snapshot TEXT NOT NULL, input_snapshot TEXT NOT NULL,
 lease_token TEXT, lease_until REAL, dispatched_at TEXT, usage TEXT,
 provider_request_id TEXT, failure_code TEXT, created_at TEXT NOT NULL);
CREATE UNIQUE INDEX learning_workbench_active ON learning_workbench_jobs(owner)
 WHERE state IN ('pending','running','unknown');
CREATE TABLE learning_workbench_artifacts (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES learning_workbench_sessions(id),
 title TEXT NOT NULL, content TEXT NOT NULL,
 source_message_id TEXT REFERENCES learning_workbench_messages(id), created_at TEXT NOT NULL);
CREATE TABLE learning_workbench_records (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL UNIQUE REFERENCES learning_workbench_sessions(id),
 current_version INTEGER NOT NULL, confirmed_version INTEGER);
CREATE TABLE learning_workbench_record_versions (
 record_id TEXT NOT NULL REFERENCES learning_workbench_records(id),
 version INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(record_id,version));
CREATE TABLE learning_workbench_reconciliations (
 message_id TEXT PRIMARY KEY REFERENCES learning_workbench_jobs(message_id),
 evidence TEXT NOT NULL, authority TEXT NOT NULL, created_at TEXT NOT NULL);
'''


def migrate(store, stamp):
    checksum = hashlib.sha256(DDL.encode()).hexdigest()
    with store.transaction() as con:
        con.execute('CREATE TABLE IF NOT EXISTS platform_migrations(version TEXT PRIMARY KEY,checksum TEXT NOT NULL,applied_at TEXT NOT NULL)')
        old = con.execute("SELECT checksum FROM platform_migrations WHERE version='U01-learning-workbench'").fetchone()
        if old:
            if old[0] != checksum:
                raise ValueError('U01-learning-workbench migration checksum mismatch')
            return
        for statement in DDL.split(';'):
            if statement.strip():
                con.execute(statement)
        con.execute('INSERT INTO platform_migrations VALUES(?,?,?)', ('U01-learning-workbench', checksum, stamp))
