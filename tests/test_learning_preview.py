"""Safety and preparation checks for the dedicated synthetic preview builder."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from fastapi.testclient import TestClient

_SPEC = importlib.util.spec_from_file_location('songban_preview_test', Path(__file__).resolve().parents[1] / 'scripts/serve_learning_preview.py')
preview = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(preview)


class LearningPreviewTests(unittest.TestCase):
    def test_catalog_requires_first_work_entry(self):
        from app.learning_v2 import Settings
        with self.assertRaisesRegex(ValueError, 'first-work'):
            Settings(catalog_enabled=True, studio_enabled=False)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / 'preview'
        guard = patch.dict(os.environ, dict(os.environ))
        guard.start()
        self.addCleanup(guard.stop)
        network = patch('socket.create_connection', side_effect=AssertionError('Synthetic preview must not contact external services'))
        network.start()
        self.addCleanup(network.stop)

    def test_fresh_app_prepares_legal_synthetic_access_without_work_or_live_model(self):
        os.environ['DEEPSEEK_API_KEY'] = 'synthetic-must-not-be-used'
        api, metadata = preview.build_preview(self.directory)
        self.assertTrue(metadata['synthetic'])
        self.assertEqual(metadata['scope'], preview.SCOPE)
        self.assertEqual(metadata['origin'], 'http://127.0.0.1:8897')
        self.assertEqual(metadata['password'], preview.PASSWORD)
        self.assertNotIn('token', metadata)
        self.assertEqual(Path(metadata['database']).parent, self.directory.resolve())
        self.assertNotIn('DEEPSEEK_API_KEY', os.environ)
        with api.state.learning_v2.store.transaction() as con:
            self.assertEqual({r[0] for r in con.execute('SELECT id FROM people')}, {a[0] for a in preview.ACTORS})
            self.assertEqual(con.execute("SELECT status FROM learn_links WHERE learner_id=?", (metadata['learner_id'],)).fetchone()[0], 'verified')
            self.assertEqual(con.execute("SELECT COUNT(*) FROM learn_course_objects WHERE kind IN ('run','artifact','check')").fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM learn_starts').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM learn_model_jobs').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM learn_model_accounts').fetchone()[0], 0)
        client = TestClient(api, base_url=metadata['origin'])
        self.addCleanup(client.close)
        config = client.get('/api/learning/v2/config').json()
        self.assertFalse(config['live_enabled'])
        self.assertTrue(config['mock_enabled'])
        self.assertTrue(config['reports_enabled'])
        self.assertTrue(config['publication_enabled'])
        self.assertTrue(config['studio_enabled'])
        self.assertTrue(config['catalog_enabled'])
        self.assertEqual(client.get('/health').status_code, 200)

    def test_marked_reuse_preserves_same_learner_and_does_not_reset_records(self):
        api, first = preview.build_preview(self.directory)
        with api.state.learning_v2.store.transaction() as con:
            before = con.execute('SELECT COUNT(*) FROM learn_course_history').fetchone()[0]
        _, second = preview.build_preview(self.directory, port=8898)
        self.assertEqual(first['learner_id'], second['learner_id'])
        self.assertEqual(second['origin'], 'http://127.0.0.1:8898')
        with api.state.learning_v2.store.transaction() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM learn_course_history').fetchone()[0], before)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM learn_learners').fetchone()[0], 1)

    def test_nonempty_unmarked_or_incomplete_directories_are_rejected(self):
        self.directory.mkdir()
        protected = self.directory / 'keep.txt'
        protected.write_text('do not overwrite', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'marker'):
            preview.build_preview(self.directory)
        self.assertEqual(protected.read_text(encoding='utf-8'), 'do not overwrite')
        (self.directory / preview.MARKER).write_text(json.dumps({'scope': preview.SCOPE, 'version': 1,
                                                              'database': preview.DATABASE, 'ready': False}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            preview.build_preview(self.directory)

    def test_existing_database_with_foreign_identity_is_not_opened_as_preview(self):
        _, metadata = preview.build_preview(self.directory)
        with closing(sqlite3.connect(metadata['database'])) as con:
            con.execute("UPDATE people SET id='non-fixture-identity' WHERE id='preview-parent-b'")
            con.commit()
        with self.assertRaisesRegex(ValueError, 'outside this synthetic fixture'):
            preview.build_preview(self.directory)

    def test_reserved_ports_and_repository_paths_are_rejected_before_writing(self):
        for port in (8893, 8894, 8895, 8896, 80, 65536):
            with self.assertRaises(ValueError):
                preview.build_preview(self.directory, port)
        self.assertFalse(self.directory.exists())
        for directory in (preview.ROOT, preview.ROOT / 'data' / 'preview-test', preview.ROOT.parent):
            with self.assertRaises(ValueError):
                preview.prepare_directory(directory)


if __name__ == '__main__':
    unittest.main()
