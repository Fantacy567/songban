"""Explicit SQLite snapshot/restore to a NEW file; never loads private config."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3


def snapshot(source, destination):
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve()
    if not source.is_file() or source == destination:
        raise ValueError('Choose an existing source and a different new destination')
    # O_EXCL protects existing backups and live databases from replacement.
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(destination.as_uri()+'?mode=rw', uri=True)) as dst:
            src.backup(dst)
            integrity = dst.execute('PRAGMA integrity_check').fetchall()
            foreign_keys = dst.execute('PRAGMA foreign_key_check').fetchall()
            if integrity != [('ok',)] or foreign_keys:
                raise ValueError('Snapshot verification failed; destination retained for investigation')
            versions = []
            if dst.execute("SELECT 1 FROM sqlite_master WHERE name='learn_migrations'").fetchone():
                versions = [r[0] for r in dst.execute('SELECT version FROM learn_migrations ORDER BY version')]
    return {'source': str(source), 'destination': str(destination), 'integrity': 'ok',
            'foreign_key_errors': 0, 'learning_migrations': versions}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create a verified snapshot or restore a backup into a new isolated SQLite file.')
    parser.add_argument('source')
    parser.add_argument('destination', help='A new file in an existing directory; existing files are never replaced')
    args = parser.parse_args()
    print(json.dumps(snapshot(args.source, args.destination), ensure_ascii=False, indent=2))
