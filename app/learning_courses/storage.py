# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
"""Additive C01 migration; frozen learning/studio/portfolio DDL is untouched."""
import hashlib

DDL = """
CREATE TABLE learning_course_progress (
 learner_id TEXT NOT NULL REFERENCES learn_learners(id),
 course_id TEXT NOT NULL,
 course_version TEXT NOT NULL,
 revision INTEGER NOT NULL CHECK(revision>=1),
 answers TEXT NOT NULL,
 activity TEXT NOT NULL,
 project_id TEXT,
 updated_at TEXT NOT NULL,
 PRIMARY KEY(learner_id,course_id)
);
"""
MIGRATION = 'C01-learning-courses'


def migrate(store, timestamp):
    checksum = hashlib.sha256(DDL.encode()).hexdigest()
    with store.transaction() as con:
        con.execute('CREATE TABLE IF NOT EXISTS platform_migrations(version TEXT PRIMARY KEY,checksum TEXT NOT NULL,applied_at TEXT NOT NULL)')
        old = con.execute('SELECT checksum FROM platform_migrations WHERE version=?', (MIGRATION,)).fetchone()
        if old:
            if old[0] != checksum:
                raise ValueError('C01-learning-courses migration checksum mismatch')
            return
        for statement in DDL.split(';'):
            if statement.strip():
                con.execute(statement)
        con.execute('INSERT INTO platform_migrations VALUES(?,?,?)', (MIGRATION, checksum, timestamp))
