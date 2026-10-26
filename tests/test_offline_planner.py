import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from app.planner import local_plan, model_plan

MEMBERS = [
    {"id": "a", "name": "孔祥梨", "role": "产品 / 后端", "skills": "Python、PPT", "available_hours": 6.0},
    {"id": "b", "name": "胡方耀", "role": "前端", "skills": "JavaScript", "available_hours": 5.0},
    {"id": "c", "name": "杨涵", "role": "设计", "skills": "海报、Figma", "available_hours": 3.0},
]
RULES = "评分关注创新。\n须在截止前提交演示视频和项目说明。"
DISCUSSION = "\n".join([
    "目标：做出能演示的分工助手",
    "决定：先做网页版",
    "任务：搭建 FastAPI 接口和数据库 3h",
    "任务：@胡方耀 做任务看板页面 (2.5小时)",
    "- [ ] 设计 logo 和海报",
    "待办：前后端联调 1h",
    "TODO: 加分项：做暗黑模式",
    "胡：登录要不要做？",
])


def context(discussion=DISCUSSION, members=MEMBERS):
    return {"project": {"name": "测试", "deadline": "2026-10-28T10:00:00+00:00"}, "now": "2026-10-27T10:00:00+00:00", "members": members,
            "sources": [{"id": "r", "kind": "rules", "body": RULES}, {"id": "d", "kind": "discussion", "body": discussion}]}


class OfflinePlannerTests(unittest.TestCase):
    def test_extracts_tasks_owners_hours_and_priority(self):
        plan = local_plan(context())
        tasks = {t["title"]: t for t in plan["tasks"]}
        self.assertEqual(plan["goal"], "做出能演示的分工助手")
        self.assertEqual(plan["decisions"], ["先做网页版"])
        self.assertIn("胡：登录要不要做？", plan["open_questions"])
        api = tasks["搭建 FastAPI 接口和数据库"]
        self.assertEqual((api["owner_id"], api["estimated_hours"], api["priority"]), ("a", 3.0, "must"))
        board = tasks["做任务看板页面"]
        self.assertEqual((board["owner_id"], board["estimated_hours"]), ("b", 2.5))
        self.assertEqual(tasks["设计 logo 和海报"]["owner_id"], "c")
        self.assertEqual(tasks["加分项：做暗黑模式"]["priority"], "should")

    def test_integration_depends_on_build_tasks_and_delivery_check_added(self):
        plan = local_plan(context())
        by_title = {t["title"]: t for t in plan["tasks"]}
        integration = by_title["前后端联调"]
        self.assertEqual(sorted(integration["depends_on"]), ["T1", "T2"])
        check = by_title["对照赛规核对提交清单"]
        self.assertEqual(check["depends_on"], [integration["key"]])
        self.assertEqual(check["evidence"][0], {"source_id": "r", "quote": "须在截止前提交演示视频和项目说明。"})

    def test_quotes_are_verbatim_source_lines(self):
        bodies = {"r": RULES, "d": DISCUSSION}
        for task in local_plan(context())["tasks"]:
            for ref in task["evidence"]:
                self.assertIn(ref["quote"], bodies[ref["source_id"]])

    def test_over_budget_is_reported_as_risk(self):
        plan = local_plan(context("任务：@杨涵 画全部插画 10h"))
        self.assertTrue(any("杨涵 超出" in r for r in plan["risks"]))

    def test_without_task_lines_falls_back_to_role_template(self):
        plan = local_plan(context("目标：随便聊聊\n我们觉得方向不错"))
        self.assertEqual([t["key"] for t in plan["tasks"]], ["T1", "T2", "T3", "T4"])
        self.assertTrue(any("角色模板" in r for r in plan["risks"]))


class OfflinePlannerApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {k: "" for k in ["DEEPSEEK_API_KEY", "MODEL_API_KEY", "MODEL_BASE_URL", "MODEL_NAME"]})
        self.env.start()
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "t.sqlite3"
        self.client = TestClient(create_app(self.db))
        members = [{k: v for k, v in m.items() if k != "id"} for m in MEMBERS]
        created = self.client.post("/api/projects", json={"name": "离线引擎", "deadline": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), "members": members}).json()
        self.pid, self.headers = created["project_id"], {"Authorization": "Bearer " + created["invites"][0]["access_token"]}

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()
        self.env.stop()

    def test_extracted_plan_passes_server_validation_and_confirms(self):
        for kind, body in [("rules", RULES), ("discussion", DISCUSSION)]:
            self.assertEqual(self.client.post(f"/api/projects/{self.pid}/sources", json={"kind": kind, "title": kind, "body": body}, headers=self.headers).status_code, 201)
        draft = self.client.post(f"/api/projects/{self.pid}/proposals", json={"mode": "local_rules"}, headers=self.headers)
        self.assertEqual(draft.status_code, 201, draft.text)
        draft = draft.json()
        self.assertIn("非大模型", draft["source_label"])
        self.assertEqual(len(draft["content"]["tasks"]), 6)
        confirmed = self.client.post(f"/api/projects/{self.pid}/proposals/{draft['id']}/confirm", json={"expected_version": draft["version"]}, headers=self.headers)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(len(confirmed.json()["tasks"]), 6)

    def add_sources(self, client=None):
        for kind, body in [("rules", RULES), ("discussion", DISCUSSION)]:
            (client or self.client).post(f"/api/projects/{self.pid}/sources", json={"kind": kind, "title": kind, "body": body}, headers=self.headers)

    def generate(self, client, mode="auto", expected=201):
        result = client.post(f"/api/projects/{self.pid}/proposals", json={"mode": mode}, headers=self.headers)
        self.assertEqual(result.status_code, expected, result.text)
        return result

    def test_auto_without_model_key_falls_back_with_visible_reason(self):
        self.add_sources()
        draft = self.generate(self.client).json()
        self.assertEqual(draft["mode"], "local_rules")
        self.assertEqual(draft["fallback_reason"], "未配置模型密钥")
        self.assertIn("已自动回退", draft["source_label"])
        self.assertIn("非大模型", draft["source_label"])
        events = self.client.get(f"/api/projects/{self.pid}", headers=self.headers).json()["events"]
        self.assertIn("已改用离线规则引擎", events[-1]["detail"])

    def test_auto_falls_back_on_insufficient_balance_without_leaking_provider_detail(self):
        self.add_sources()
        def insufficient(_request):
            return httpx.Response(402, json={"error": {"message": "FAKE_TEST_ONLY_KEY private-provider-detail"}})
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "FAKE_TEST_ONLY_KEY"}), TestClient(create_app(self.db, model_runner=lambda c: model_plan(c, httpx.MockTransport(insufficient)))) as client:
            result = self.generate(client)
            self.assertNotIn("FAKE_TEST_ONLY_KEY", result.text)
            self.assertNotIn("private-provider-detail", result.text)
            self.assertEqual(result.json()["fallback_reason"], "模型账户余额不足")
            self.assertEqual(result.json()["mode"], "local_rules")
            self.assertIsNone(result.json()["model_id"])
            self.generate(client, mode="model", expected=503)

    def test_auto_falls_back_when_model_output_fails_validation(self):
        self.add_sources()
        def hallucinated(context):
            plan = local_plan(context)
            plan["tasks"][0]["evidence"][0]["quote"] = "不存在的原文"
            return plan
        with TestClient(create_app(self.db, model_runner=hallucinated)) as client:
            draft = self.generate(client).json()
            self.assertEqual(draft["fallback_reason"], "模型输出未通过校验")
            self.generate(client, mode="model", expected=502)

    def test_auto_uses_model_when_it_succeeds(self):
        self.add_sources()
        with TestClient(create_app(self.db, model_runner=local_plan)) as client:
            draft = self.generate(client).json()
        self.assertEqual(draft["mode"], "model")
        self.assertIsNone(draft["fallback_reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
