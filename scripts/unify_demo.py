"""Clone the existing fictional demo and import its separate learning preview.

Both sources remain unchanged. The new private receipt is consumed by run_demo.py
and serves both workflows on one origin. Never import a real account database.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.learning_backup import snapshot
from scripts.run_learning import create_application
from scripts.serve_learning_preview import ACTORS, _settings, prepare_directory


def quoted(name):
    return '"' + name.replace('"', '""') + '"'


def assemble(resume_path, learning_directory, destination, port=8895):
    if not 1024 <= port <= 65535:
        raise ValueError('Choose an explicit unprivileged demo port')
    receipt = json.loads(Path(resume_path).read_text(encoding='utf-8-sig'))
    source_demo = Path(receipt['db']).resolve(strict=True)
    if receipt.get('learning'):
        raise ValueError('This receipt is already unified; resume it instead of importing twice')
    users = receipt['bootstrap']['users']
    with closing(sqlite3.connect(source_demo.as_uri()+'?mode=ro', uri=True)) as con:
        rows = con.execute('SELECT id,token_hash,phone_real FROM people').fetchall()
        expected = {u['id']: hashlib.sha256(u['token'].encode()).hexdigest() for u in users}
        if not expected or any(not ident.startswith('demo-') for ident in expected) or {r[0] for r in rows} != set(expected) or any(r[1] != expected[r[0]] or r[2] for r in rows):
            raise ValueError('Only the known synthetic hackathon identities may be cloned')
    learning_directory = Path(learning_directory).resolve()
    if not (learning_directory/'.songban-learning-preview.json').is_file() or not (learning_directory/'preview-metadata.json').is_file():
        raise ValueError('An existing marked synthetic learning preview is required')
    learning_directory, fresh = prepare_directory(learning_directory)
    if fresh:
        raise ValueError('Learning preview must already be prepared')
    metadata = json.loads((learning_directory/'preview-metadata.json').read_text(encoding='utf-8'))
    source_learning = Path(metadata['database']).resolve(strict=True)
    target = Path(destination).resolve()
    if target.exists() or target == ROOT or target in ROOT.parents or ROOT/'data' in target.parents:
        raise ValueError('Use a NEW dedicated demo output directory, never real data')
    target.mkdir(parents=True)
    database = target/'demo.sqlite3'
    snapshot(source_demo, database)
    # Validate the exact snapshot, not only the live source before the backup.
    # A concurrent writer may have added a real/unknown actor in between.
    with closing(sqlite3.connect(database)) as copied:
        copied_rows = copied.execute('SELECT id,token_hash,phone_real FROM people').fetchall()
        if {r[0] for r in copied_rows} != set(expected) or any(r[1] != expected[r[0]] or r[2] for r in copied_rows):
            raise ValueError('The copied snapshot contains unexpected synthetic identities')
    origin = 'http://127.0.0.1:'+str(port)
    create_application(database, _settings(origin))
    counts = {}
    with closing(sqlite3.connect(source_learning.as_uri()+'?mode=ro', uri=True)) as src, closing(sqlite3.connect(database)) as dst:
        src.execute('BEGIN')
        dst.execute('PRAGMA foreign_keys=ON'); dst.execute('BEGIN IMMEDIATE'); dst.execute('PRAGMA defer_foreign_keys=ON')
        try:
            versions = lambda c: dict(c.execute('SELECT version,checksum FROM learn_migrations'))
            if versions(src) != versions(dst):
                raise ValueError('Learning migration versions/checksums differ')
            learn_tables = [r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'learn_*' ORDER BY name") if r[0] != 'learn_migrations']
            for table in learn_tables:
                if table != 'learn_secrets' and not table.startswith('learn_legacy_') and dst.execute('SELECT COUNT(*) FROM '+quoted(table)).fetchone()[0]:
                    raise ValueError('Target already has learning data; refusing to overwrite')
            dst.execute('DELETE FROM learn_secrets')  # No learner/session exists in this fresh clone.
            tables = ['people', 'core_interviews', 'core_interview_messages'] + learn_tables
            actor_ids = {a[0] for a in ACTORS}
            for table in tables:
                columns = [r[1] for r in src.execute('PRAGMA table_info('+quoted(table)+')')]
                target_columns = [r[1] for r in dst.execute('PRAGMA table_info('+quoted(table)+')')]
                if columns != target_columns:
                    raise ValueError('Schema mismatch while preserving '+table)
                rows = src.execute('SELECT * FROM '+quoted(table)).fetchall()
                if table == 'people' and {r[columns.index('id')] for r in rows} != actor_ids:
                    raise ValueError('Unexpected learning actors')
                if table in ('core_interviews', 'core_interview_messages') and any(r[columns.index('user_id')] not in actor_ids for r in rows):
                    raise ValueError('Unexpected interview owner')
                if rows:
                    dst.executemany('INSERT INTO '+quoted(table)+'('+','.join(map(quoted, columns))+') VALUES('+','.join('?' for _ in columns)+')', rows)
                counts[table] = len(rows)
            if dst.execute('PRAGMA foreign_key_check').fetchall() or dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Unified snapshot integrity check failed')
            dst.commit()
        except BaseException:
            dst.rollback()
            raise
    learning = {**metadata, 'database': str(database), 'origin': origin, 'learning_url': origin+'/learning-prep#/learn/first', 'manager_url': origin+'/learning-prep#/family'}
    unified = {**receipt, 'db': str(database), 'learning': learning, 'canonical_demo': True}
    (target/'resume.json').write_text(json.dumps(unified, ensure_ascii=False, indent=2), encoding='utf-8')
    (target/'learning-metadata.json').write_text(json.dumps(learning, ensure_ascii=False, indent=2), encoding='utf-8')
    report = {'source_demo': str(source_demo), 'source_learning': str(source_learning), 'database': str(database), 'resume': str(target/'resume.json'), 'origin': origin, 'imported_rows': counts, 'sources_modified': False, 'integrity': 'ok'}
    (target/'assembly.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume', type=Path, required=True)
    parser.add_argument('--learning-preview', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8895)
    args = parser.parse_args()
    print(json.dumps(assemble(args.resume, args.learning_preview, args.destination, args.port), ensure_ascii=False, indent=2))
