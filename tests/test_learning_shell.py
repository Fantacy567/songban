"""Smoke checks for the standalone learning/experience UI shell.

These tests intentionally validate only the serving boundary and the static
asset contract. The learning flow is client-side demo state, while the core
team workspace keeps its existing API and homepage contract.
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
        self.assertIn("learning.css", response.text)
        self.assertIn("learning.js", response.text)
        self.assertIn('id="app"', response.text)

    def test_learning_assets_are_served(self):
        page = self.client.get("/learning").text
        self.assertEqual(self.client.get("/static/learning.css").status_code, 200)
        # The script is created by the experience frontend workstream.
        self.assertIn("learning.js", page)
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

    def test_learning_shell_keeps_core_homepage_separate(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200, home.text)
        self.assertIn("core.js", home.text)
        self.assertNotIn("learning.js", home.text)


if __name__ == "__main__":
    unittest.main()
