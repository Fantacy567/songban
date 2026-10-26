import copy
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.advice import anchors_in, rubric_coverage, scope_advice
from app.main import create_app


RULES = "评分关注完成度。\n须在截止前提交演示视频和项目说明。\n另交仓库链接。"
SOURCES = [{"id": "r", "kind": "rules", "body": RULES}]


def task(title, status="todo", priority="must", hours=2.0, deliverable=""):
    return {"id": title, "task_key": title[:2], "title": title, "acceptance": "另一位成员核对成果。", "deliverable": deliverable, "status": status, "priority": priority, "estimated_hours": hours}


class RubricTests(unittest.TestCase):
    def test_anchors_keep_longer_phrase(self):
        self.assertEqual(anchors_in("提交需求文档和协作页面"), ["需求文档", "协作页面"])

    def test_quotes_are_verbatim_and_submission_line_needs_both_artifacts(self):
        report = rubric_coverage(SOURCES, [])
        quotes = [item["quote"] for item in report["items"]]
        self.assertEqual(quotes, ["评分关注完成度", "须在截止前提交演示视频和项目说明", "另交仓库链接"])
        for quote in quotes:
            self.assertIn(quote, RULES)
        by_quote = {item["quote"]: item for item in report["items"]}
        self.assertEqual(by_quote["评分关注完成度"]["status"], "manual")
        video = by_quote["须在截止前提交演示视频和项目说明"]
        self.assertEqual(video["status"], "missing")
        self.assertIn("演示视频", video["gap"])
        self.assertIn("项目说明", video["gap"])

    def test_pending_until_every_named_artifact_is_accepted(self):
        tasks = [task("录演示视频"), task("写项目说明", status="accepted")]
        item = next(item for item in rubric_coverage(SOURCES, tasks)["items"] if "演示视频" in item["quote"])
        self.assertEqual(item["status"], "pending")
        self.assertEqual(item["task_title"], "录演示视频")
        tasks[0]["status"] = "accepted"
        item = next(item for item in rubric_coverage(SOURCES, tasks)["items"] if "演示视频" in item["quote"])
        self.assertEqual(item["status"], "covered")
        self.assertEqual(item["gap"], "")

    def test_deliverable_text_can_cover_a_name(self):
        done = task("对照赛规核对提交清单", status="accepted", deliverable="演示视频和项目说明都已放进提交入口。")
        item = next(item for item in rubric_coverage(SOURCES, [done])["items"] if "演示视频" in item["quote"])
        self.assertEqual(item["status"], "covered")

    def test_no_criteria_stays_empty(self):
        report = rubric_coverage([{"id": "r", "kind": "rules", "body": "今天天气不错，大家加油。"}], [])
        self.assertEqual(report["items"], [])
        self.assertIn("请人工对照原文", report["note"])

    def test_coverage_does_not_edit_tasks(self):
        tasks = [task("录演示视频")]
        before = copy.deepcopy(tasks)
        rubric_coverage(SOURCES, tasks)
        self.assertEqual(tasks, before)


class ScopeTests(unittest.TestCase):
    def test_tight_deadline_suggests_optional_cuts_without_editing_tasks(self):
        tasks = [task("做接口", hours=4), task("画海报", priority="should", hours=2)]
        before = copy.deepcopy(tasks)
        advice = scope_advice("2026-10-26T12:00:00+00:00", "2026-10-26T11:00:00+00:00", tasks)
        self.assertEqual(tasks, before)
        self.assertTrue(advice["tight"])
        self.assertEqual(advice["remaining_hours"], 1.0)
        self.assertEqual(advice["unfinished_must_hours"], 4.0)
        self.assertEqual(advice["drop"], [{"task_key": "画海", "title": "画海报", "estimated_hours": 2.0}])
        self.assertEqual(advice["narrow"][0]["title"], "做接口")
        self.assertIn("不会被自动修改", advice["note"])

    def test_enough_time_does_not_list_cuts(self):
        advice = scope_advice("2026-10-28T10:00:00+00:00", "2026-10-27T10:00:00+00:00", [task("做接口", hours=3)])
        self.assertFalse(advice["tight"])
        self.assertEqual(advice["drop"], [])
        self.assertEqual(advice["narrow"], [])

    def test_no_tasks_is_not_applicable(self):
        advice = scope_advice("2026-10-28T10:00:00+00:00", "2026-10-27T10:00:00+00:00", [])
        self.assertFalse(advice["applicable"])
        self.assertEqual(advice["drop"], [])

    def test_accepted_work_is_not_counted_as_unfinished(self):
        advice = scope_advice("2026-10-26T12:00:00+00:00", "2026-10-26T11:00:00+00:00", [task("做接口", status="accepted", hours=8)])
        self.assertFalse(advice["tight"])
        self.assertEqual(advice["unfinished_must_hours"], 0.0)


class AdviceApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {k: "" for k in ["DEEPSEEK_API_KEY", "MODEL_API_KEY", "MODEL_BASE_URL", "MODEL_NAME"]})
        self.env.start()
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(Path(self.temp.name) / "t.sqlite3"))
        created = self.client.post("/api/projects", json={
            "name": "交卷核对",
            "deadline": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "members": [
                {"name": "队长", "role": "后端", "skills": "Python", "available_hours": 8},
                {"name": "胡", "role": "前端", "skills": "JavaScript", "available_hours": 8},
            ],
        }).json()
        self.pid = created["project_id"]
        self.headers = {"Authorization": "Bearer " + created["invites"][0]["access_token"]}
        self.token = created["invites"][0]["access_token"]

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()
        self.env.stop()

    def test_recap_workspace_and_export_include_rubric_and_scope(self):
        discussion = "目标：交得出作品\n任务：录制演示视频 2h\n任务：撰写项目说明 1h\n- [ ] 加分项：暗黑模式 3h"
        for kind, body in [("rules", RULES), ("discussion", discussion)]:
            self.assertEqual(self.client.post(f"/api/projects/{self.pid}/sources", json={"kind": kind, "title": kind, "body": body}, headers=self.headers).status_code, 201)
        draft = self.client.post(f"/api/projects/{self.pid}/proposals", json={"mode": "local_rules"}, headers=self.headers)
        self.assertEqual(draft.status_code, 201, draft.text)
        draft = draft.json()
        confirmed = self.client.post(f"/api/projects/{self.pid}/proposals/{draft['id']}/confirm", json={"expected_version": draft["version"]}, headers=self.headers)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        before = len(confirmed.json()["tasks"])
        state = self.client.get(f"/api/projects/{self.pid}", headers=self.headers).json()
        self.assertEqual(len(state["tasks"]), before)
        self.assertTrue(state["scope"]["applicable"])
        self.assertTrue(state["scope"]["tight"])
        self.assertTrue(state["scope"]["drop"])
        self.assertNotIn(self.token, str(state["scope"]))
        report = self.client.get(f"/api/projects/{self.pid}/recap", headers=self.headers).json()
        video = next(item for item in report["rubric"]["items"] if "演示视频" in item["quote"])
        self.assertEqual(video["status"], "pending")
        self.assertIn(video["quote"], RULES)
        manual = next(item for item in report["rubric"]["items"] if item["quote"] == "评分关注完成度")
        self.assertEqual(manual["status"], "manual")
        exported = self.client.get(f"/api/projects/{self.pid}/export", headers=self.headers).text
        self.assertIn("## 赛规对照", exported)
        self.assertIn("## 时间与范围", exported)
        self.assertIn("须在截止前提交演示视频和项目说明", exported)
        self.assertNotIn(self.token, exported)
        self.assertFalse(report["ready"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
