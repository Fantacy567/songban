import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


class PulseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(Path(self.temp.name) / "t.sqlite3"))
        members = [{"name": n, "role": r, "skills": s, "available_hours": 4.0} for n, r, s in [("队长", "后端", "Python"), ("胡", "前端", "JavaScript")]]
        deadline = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        created = self.client.post("/api/projects", json={"name": "同步", "deadline": deadline, "members": members}).json()
        self.pid = created["project_id"]
        self.tokens = [i["access_token"] for i in created["invites"]]
        other = self.client.post("/api/projects", json={"name": "另一队", "deadline": deadline, "members": members}).json()
        self.other_pid = other["project_id"]

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def pulse(self, who=1, pid=None):
        return self.client.get(f"/api/projects/{pid or self.pid}/pulse", headers={"Authorization": "Bearer " + self.tokens[who]})

    def test_pulse_advances_when_teammate_changes_project(self):
        before = self.pulse().json()["last_event"]
        self.assertGreater(before, 0)
        self.client.post(f"/api/projects/{self.pid}/sources", json={"kind": "rules", "title": "规则", "body": "原文"}, headers={"Authorization": "Bearer " + self.tokens[0]})
        after = self.pulse().json()["last_event"]
        self.assertGreater(after, before)
        workspace = self.client.get(f"/api/projects/{self.pid}", headers={"Authorization": "Bearer " + self.tokens[1]}).json()
        self.assertEqual(max(e["sequence"] for e in workspace["events"]), after)

    def test_pulse_requires_member_of_project(self):
        self.assertEqual(self.client.get(f"/api/projects/{self.pid}/pulse").status_code, 401)
        self.assertEqual(self.pulse(pid=self.other_pid).status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
