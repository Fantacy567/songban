"""Central page boundaries use synthetic databases; no external providers."""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.learning_v2 import Settings


class LearningHostTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'fixture.sqlite3'
        module_name = 'app._learning_host_test_main'
        source = Path(__file__).resolve().parents[1] / 'app/main.py'
        spec = importlib.util.spec_from_file_location(module_name, source)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {'DATABASE_PATH': str(Path(self.folder.name)/'import.sqlite3')}, clear=True), patch('app.environment.load_env'):
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            finally:
                sys.modules.pop(module_name, None)
        self.create_app = module.create_app

    def client(self, **kwargs):
        with patch.dict(os.environ, {}, clear=True):
            client = TestClient(self.create_app(db_path=self.path, core_only=kwargs.pop('core_only', False), enforce_journey=False, **kwargs))
        self.addCleanup(client.close)
        return client

    def test_default_existing_site_does_not_opt_in(self):
        client = self.client()
        for path in ('/', '/core', '/learning', '/workflow', '/classic', '/static/songban.html'):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn('<meta name="songban-learning-v2"', response.text)
        self.assertEqual(client.get('/learning-prep').status_code, 404)

    def test_canonical_and_direct_bookmarks_share_boundary(self):
        client = self.client(learning_settings=Settings())
        for path in ('/', '/core', '/learning', '/workflow', '/classic',
                     '/static/songban.html', '/static/studio.html', '/static/core.html',
                     '/static/workflow.html', '/static/index.html'):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn('<meta name="songban-learning-v2"', response.text)
                self.assertIn('id="learning-identity-pending"', response.text)
        self.assertIn('/static/legacy-learning-boundary.js', client.get('/static/core.html').text)
        self.assertEqual(client.get('/learning-prep').status_code, 200)

    def test_direct_html_route_does_not_escape_static_directory(self):
        client = self.client(learning_settings=Settings())
        for path in ('/static/..%5cREADME.html', '/static/..%5c..%5csecret.html', '/static/not-a-page.html'):
            self.assertEqual(client.get(path).status_code, 404, path)

    def test_core_only_still_locks_legacy_compatibility_pages(self):
        client = self.client(core_only=True, learning_settings=Settings())
        for path in ('/workflow', '/classic', '/static/studio.html', '/static/workflow.html', '/static/index.html'):
            self.assertEqual(client.get(path).status_code, 423, path)

    def test_navigation_opt_in_preserves_old_bookmarks_and_pause_exit(self):
        client = self.client(learning_settings=Settings(navigation_enabled=True))
        for path in ('/', '/learning', '/static/songban.html'):
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('name="songban-learning-navigation"', response.text)
        response = client.get('/learning-prep')
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-stage-nav', response.text)
        self.assertIn('href="/#/events" data-learning-exit', response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_navigation_is_separate_from_identity_enablement(self):
        client = self.client(learning_settings=Settings(enabled=True))
        self.assertNotIn('name="songban-learning-navigation"', client.get('/').text)
        self.assertNotIn('data-stage-nav', client.get('/learning-prep').text)
