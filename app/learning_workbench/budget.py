# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
"""Shared text-provider accounting, to be called inside the host's write transaction.

Both domains must check these counters before reserving/claiming. Tables are
optional so independent migrations and isolated domain tests remain supported.
Configuration revision never partitions the cumulative ceiling.
"""


def _tables(con):
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('learning_workbench_jobs','creative_calls','creative_jobs')")}


def text_used_calls(con):
    tables, total = _tables(con), 0
    if 'learning_workbench_jobs' in tables:
        total += con.execute("SELECT COALESCE(SUM(counted),0) FROM learning_workbench_jobs WHERE mode='live'").fetchone()[0]
    if 'creative_calls' in tables:
        total += con.execute('SELECT COUNT(*) FROM creative_calls').fetchone()[0]
    return total


def text_inflight(con):
    """Unknown dispatches retain a slot until explicit operator reconciliation."""
    tables, total = _tables(con), 0
    if 'learning_workbench_jobs' in tables:
        total += con.execute("SELECT COUNT(*) FROM learning_workbench_jobs WHERE mode='live' AND state IN ('running','unknown')").fetchone()[0]
    if 'creative_jobs' in tables:
        total += con.execute("SELECT COUNT(*) FROM creative_jobs WHERE state IN ('running','unknown')").fetchone()[0]
    return total
