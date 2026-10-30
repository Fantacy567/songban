"""INTERVIEW-03 HTTP tests: onboarding registration mode and the register → interview → confirm chain.
SMS is the existing test-code substitute (nothing is sent); the model is a protocol substitute."""
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from tests.test_interview_api import Script

SMS_ENV = ["DEEPSEEK_API_KEY", "MODEL_API_KEY", "MODEL_BASE_URL", "MODEL_NAME", "TEAM_MODEL_API_KEY", "TEAM_MODEL_BASE_URL", "TEAM_MODEL_NAME",
           "DASHSCOPE_API_KEY", "SONGBAI_REQUIRE_SMS", "SONGBAI_IMESSAGE", "SONGBAI_SMS", "ALIYUN_ACCESS_KEY_ID", "ALIYUN_ACCESS_KEY_SECRET",
           "ALIYUN_SMS_SIGN_NAME", "ALIYUN_SMS_TEMPLATE_CODE"]
BASE = "/api/core/interview"


class Onboarding(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {**{k: "" for k in SMS_ENV}, "SONGBAI_ALLOW_TEST_CODES": "1"})
        self.env.start()
        self.patches = [patch("app.team_core.team_model_config", return_value={"api_key": "", "model_id": "未配置"}),
                        patch("app.interview.team_model_config", return_value={"api_key": "", "model_id": "未配置"})]
        for p in self.patches:
            p.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "t.sqlite3"
        self.script = Script()
        self.client = TestClient(create_app(self.path, core_only=True, interview_runner=self.script))

    def tearDown(self):
        self.client.close()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()
        self.env.stop()

    def code(self, phone):
        r = self.client.post("/api/studio/codes", json={"phone": phone})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["sent"], "test substitute must not send a real SMS")
        return r.json()["code"]

    def register(self, phone, **body):
        return self.client.post("/api/studio/register", json={"phone": phone, "code": self.code(phone), "password": "test-only-pass", **body})

    def h(self, token):
        return {"Authorization": "Bearer " + token}

    def people(self):
        with closing(sqlite3.connect(self.path)) as con:
            return con.execute("SELECT phone,name,profile,skills FROM people ORDER BY phone").fetchall()

    def ok(self, r):
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def rid(self):
        return "req-" + uuid4().hex[:12]

    def test_onboarding_registration_leaves_profile_empty_and_logs_in(self):
        r = self.ok(self.register("13800000001", name="合成甲", onboarding=True))
        self.assertFalse(r["returning"])
        self.assertEqual((r["profile"], r["skills"]), ("", ""))
        self.assertEqual(self.people(), [("13800000001", "合成甲", "", "")])
        self.assertEqual(self.ok(self.client.get("/api/core/me", headers=self.h(r["token"])))["person"]["name"], "合成甲")
        self.assertEqual(self.ok(self.client.get(BASE, headers=self.h(r["token"]))), {"status": "not_started"})
        self.assertEqual(self.script.calls, [], "registration alone calls no model")

    def test_registration_checks_stay_strict(self):
        phone = "13800000002"
        issued = self.code(phone)
        wrong = "000000" if issued != "000000" else "111111"
        bad = self.client.post("/api/studio/register", json={"phone": phone, "code": wrong, "password": "test-only-pass", "name": "合成乙", "onboarding": True})
        self.assertEqual((bad.status_code, bad.json()["error"]["code"]), (401, "bad_code"))
        self.assertNotIn("token", bad.json())
        cases = [({"name": "合成乙", "onboarding": True, "password": ""}, 422, "password_required"),
                 ({"onboarding": True}, 422, "profile_required"),
                 ({"name": "   ", "onboarding": True}, 422, "profile_required"),
                 ({"name": "合成乙", "onboarding": "true"}, 422, "invalid_input"),
                 ({"name": "合成乙", "onboarding": 1}, 422, "invalid_input"),
                 ({"name": "合成乙"}, 422, "profile_required"),
                 ({"name": "合成乙", "onboarding": False}, 422, "profile_required"),
                 ({"name": "合成乙", "profile": "做过演示"}, 422, "profile_required")]
        for body, status, code in cases:
            r = self.client.post("/api/studio/register", json={"phone": phone, "code": issued, "password": "test-only-pass", **body})
            self.assertEqual((r.status_code, r.json()["error"]["code"]), (status, code), body)
        self.assertEqual(self.people(), [])
        self.assertEqual(self.ok(self.client.post("/api/studio/register", json={"phone": phone, "code": issued, "password": "test-only-pass", "name": "合成乙", "onboarding": True}))["returning"], False)

    def test_old_clients_and_old_accounts_are_unchanged(self):
        old = self.ok(self.register("13800000003", name="合成丙", profile="做过产品演示", skills="产品"))
        self.assertEqual((old["profile"], old["skills"]), ("做过产品演示", "产品"))
        again = self.ok(self.register("13800000003", name="冒名", onboarding=True))
        self.assertTrue(again["returning"])
        self.assertEqual((again["name"], again["profile"], again["skills"]), ("合成丙", "做过产品演示", "产品"))
        self.assertEqual(self.people(), [("13800000003", "合成丙", "做过产品演示", "产品")])
        self.assertEqual(self.ok(self.client.get(BASE, headers=self.h(again["token"]))), {"status": "not_started"})
        started = self.ok(self.client.post(BASE + "/start", json={}, headers=self.h(again["token"])))
        self.assertEqual(started["status"], "asking", "existing account without a team can interview")

    def test_register_to_confirm_chain(self):
        r = self.ok(self.register("13800000004", name="合成丁", onboarding=True))
        h = self.h(r["token"])
        self.assertEqual(self.ok(self.client.get(BASE, headers=h)), {"status": "not_started"})
        s = self.ok(self.client.post(BASE + "/start", json={"age_band": "undisclosed", "stage": "job_seeking"}, headers=h))
        self.assertEqual((s["version"], s["asked_count"], s["stage"]), (1, 1, "job_seeking"))
        s = self.ok(self.client.post(BASE + "/answer", json={"version": 1, "question_id": "q1", "request_id": self.rid(), "text": "想做一个记账小工具"}, headers=h))
        self.assertEqual((s["version"], s["asked_count"], s["current_question"]["id"]), (2, 2, "q3"))
        login = self.ok(self.client.post("/api/studio/login", json={"account": "13800000004", "password": "test-only-pass"}))
        h = self.h(login["token"])
        self.assertEqual(self.ok(self.client.get(BASE, headers=h)), s, "re-login restores the same state")
        s = self.ok(self.client.post(BASE + "/answer", json={"version": 2, "question_id": "q3", "request_id": self.rid(), "text": "不知道"}, headers=h))
        done = self.ok(self.client.post(BASE + "/finish", json={"version": s["version"], "request_id": self.rid()}, headers=h))
        self.assertEqual((done["status"], done["profile"]["reason"]), ("pending_confirmation", "user_finished"))
        self.assertEqual(self.ok(self.client.get(BASE, headers=h)), done, "leaving without confirming keeps the draft")
        calls = len(self.script.calls)
        confirmed = self.ok(self.client.post(BASE + "/confirm", json={"version": done["version"], "request_id": self.rid()}, headers=h))
        self.assertEqual((confirmed["status"], confirmed["profile"]["draft"]), ("confirmed", done["profile"]["draft"]))
        self.assertEqual(len(self.script.calls), calls)
        self.assertEqual(self.ok(self.client.get(BASE, headers=h)), confirmed)
        self.assertEqual(self.people(), [("13800000004", "合成丁", "", "")], "confirming does not write people.profile/skills")

    def test_stages_and_undisclosed_age_can_start(self):
        for i, stage in enumerate(["university", "secondary_school", "job_seeking", "working", "undisclosed", "other"]):
            token = self.ok(self.register(f"1390000000{i}", name=f"合成{i}", onboarding=True))["token"]
            s = self.ok(self.client.post(BASE + "/start", json={"age_band": "undisclosed", "stage": stage}, headers=self.h(token)))
            self.assertEqual((s["status"], s["stage"], s["age_band"]), ("asking", stage, "undisclosed"))
            self.assertEqual((self.script.calls[-1]["stage"], self.script.calls[-1]["age_band"]), (stage, "undisclosed"))
        token = self.ok(self.register("13900000099", name="不填", onboarding=True))["token"]
        self.assertEqual(self.ok(self.client.post(BASE + "/start", json={}, headers=self.h(token)))["age_band"], "undisclosed")

    def test_core_page_ships_interview_script_and_no_profile_inputs(self):
        page = self.client.get("/").text
        self.assertIn("/static/interview.js?v=", page)
        self.assertLess(page.index("/static/core.js"), page.index("/static/interview.js"))
        core = self.client.get("/static/core.js").text
        self.assertNotIn('name="profile"', core)
        self.assertNotIn('name="skills"', core)
        self.assertIn("onboarding:true", core)
        script = self.client.get("/static/interview.js").text
        self.assertNotIn("localStorage", script.split("\n", 1)[1])
        self.assertNotIn("innerText", script)
        self.assertNotIn("purpose", script)


if __name__ == "__main__":
    unittest.main()
