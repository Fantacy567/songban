"""Unified entry/asset contracts and compatibility for legacy demo sessions.

Browser interactions and real core integration are checked separately.
"""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


class LearningShellTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "learning-shell.sqlite3"
        self.client = TestClient(create_app(self.db, core_only=True))

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def test_learning_route_serves_standalone_shell(self):
        response = self.client.get("/learning")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("松伴", response.text)
        self.assertIn("songban.css", response.text)
        self.assertIn("songban.js", response.text)
        self.assertIn('id="app"', response.text)

    def test_learning_assets_are_served(self):
        page = self.client.get("/learning").text
        self.assertEqual(self.client.get("/static/songban.css").status_code, 200)
        # The script is created by the experience frontend workstream.
        self.assertIn("songban.js", page)
        self.assertIn("#/login", page)

    def test_learning_demo_api_supports_session_and_evidence_guard(self):
        events = self.client.get("/api/learning/v1/events", params={"interests": "音乐"})
        self.assertEqual(events.status_code, 200, events.text)
        self.assertEqual(len(events.json()["items"]), 3)
        self.assertEqual(events.json()["mode"], "local_demo")

        created = self.client.post("/api/learning/v1/sessions", json={"role": "creator"})
        self.assertEqual(created.status_code, 201, created.text)
        session = created.json()
        sid = session["id"]
        self.assertEqual(session["revision"], 1)
        self.assertEqual(len(session["tasks"]), 6)

        missing = self.client.post(
            f"/api/learning/v1/sessions/{sid}/evidence",
            json={"task_id": "sketch-first-flow"},
        )
        self.assertEqual(missing.status_code, 422, missing.text)
        self.assertEqual(missing.json()["error"]["code"], "learning_evidence_required")

        saved = self.client.post(
            f"/api/learning/v1/sessions/{sid}/evidence",
            json={"task_id": "sketch-first-flow", "summary": "三张页面草图已连接。"},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["tasks"][0]["status"], "reported_done")

        stale = self.client.patch(
            f"/api/learning/v1/sessions/{sid}",
            json={"expected_revision": 1, "idea": {"text": "旧窗口"}},
        )
        self.assertEqual(stale.status_code, 409, stale.text)

    def test_learning_and_home_share_shell_with_legacy_core_available(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200, home.text)
        self.assertIn("songban.js", home.text)
        self.assertNotIn("learning.js", home.text)
        self.assertEqual(home.text, self.client.get('/learning').text)
        self.assertIn('core.js', self.client.get('/core').text)

    def test_unified_visual_shell_contract(self):
        home = self.client.get("/")
        learning = self.client.get("/learning")
        self.assertIn("songban.css?v=20261031-design-v1.2", home.text)
        self.assertIn("songban.js?v=20261031-design-v1.2", home.text)
        self.assertIn("songban-views.js?v=20261031-design-v1.2", learning.text)
        self.assertIn("songban-library.js?v=20261031-design-v1.2", home.text)
        self.assertIn('data-shell="songban-v1"', home.text)
        css = self.client.get('/static/songban.css').text
        for token in ('--sb-bg:#faf9f6', '--sb-purple:#8c71ed', '.app-shell', '.app-header', '.sidebar', '.surface'):
            self.assertIn(token, css)

    def test_learning_session_survives_app_restart(self):
        created = self.client.post("/api/learning/v1/sessions", json={"role": "creator"})
        self.assertEqual(created.status_code, 201, created.text)
        session = created.json()
        sid = session["id"]
        updated = self.client.patch(
            f"/api/learning/v1/sessions/{sid}",
            json={"expected_revision": 1, "idea": {"text": "保存到服务端"}},
        )
        self.assertEqual(updated.status_code, 200, updated.text)

        restarted = TestClient(create_app(self.db, core_only=True))
        try:
            restored = restarted.get(f"/api/learning/v1/sessions/{sid}")
            self.assertEqual(restored.status_code, 200, restored.text)
            self.assertEqual(restored.json()["idea"]["text"], "保存到服务端")
            self.assertEqual(restored.json()["revision"], 2)
        finally:
            restarted.close()


if __name__ == "__main__":
    unittest.main()
