"""P4 paused history and explicit SQLite backup; synthetic and offline only."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest

try:
    from .test_learning_v2_reports import ReportTests
except ImportError:
    from test_learning_v2_reports import ReportTests
from scripts.learning_backup import snapshot


class ReleaseHistoryTests(ReportTests):
    def test_same_instance_pause_keeps_history_capabilities_without_new_writes(self):
        report = self.make_report()
        self.service.settings = replace(self.service.settings, enabled=False, course_enabled=False,
            models_enabled=False, reports_enabled=False, publication_enabled=False)
        config = self.get('/config')
        self.assertFalse(config['reports_enabled'])
        self.assertTrue(config['reports_readable'])
        self.assertFalse(config['live_enabled'])
        self.assertEqual(self.get('/artifacts/'+self.art['id'])['id'], self.art['id'])
        self.assertEqual(self.get('/runs/'+self.rid_run)['id'], self.rid_run)
        self.assertEqual(self.get('/reports/'+report['id'])['id'], report['id'])
        response = self.write(self.a, '/runs/'+self.rid_run+'/reports', dict(request_id=self.rid(),
            expected_revision=self.fresh()['revision'], reflection_id=self.reflection['id'],
            artifact_version_id=self.art['current_version']['id'], check_id=self.checked['id'], mode='mock'), expected=423)
        self.assertEqual(response.json()['error']['code'], 'learning_paused')


class SQLiteSnapshotTests(unittest.TestCase):
    def test_wal_snapshot_restores_committed_data_without_inflight_write(self):
        with tempfile.TemporaryDirectory() as folder:
            source, backup, restored = [Path(folder)/name for name in ('source.db','backup.db','restored.db')]
            with closing(sqlite3.connect(source)) as writer:
                writer.execute('PRAGMA journal_mode=WAL')
                writer.execute('CREATE TABLE facts(id INTEGER PRIMARY KEY, value TEXT)')
                writer.execute("INSERT INTO facts VALUES(1,'committed')"); writer.commit()
                writer.execute("INSERT INTO facts VALUES(2,'not committed')")
                result = snapshot(source, backup)
                self.assertEqual(result['integrity'], 'ok')
                snapshot(backup, restored)
                with closing(sqlite3.connect(restored)) as reader:
                    self.assertEqual(reader.execute('SELECT * FROM facts').fetchall(), [(1,'committed')])
                writer.rollback()

    def test_snapshot_never_overwrites_source_or_existing_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            source, destination = Path(folder)/'source.db', Path(folder)/'existing.db'
            with closing(sqlite3.connect(source)) as con:
                con.execute('CREATE TABLE keep(value TEXT)'); con.commit()
            destination.write_bytes(b'keep this file')
            original = source.read_bytes()
            with self.assertRaises(ValueError): snapshot(source, source)
            with self.assertRaises(FileExistsError): snapshot(source, destination)
            self.assertEqual(destination.read_bytes(), b'keep this file')
            self.assertEqual(source.read_bytes(), original)


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for cls in (ReleaseHistoryTests, SQLiteSnapshotTests):
        suite.addTests(cls(name) for name in cls.__dict__ if name.startswith('test_'))
    return suite
