"""INTERVIEW-02 HTTP tests. The model is a protocol substitute; nothing here measures real model quality."""
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.interview import InterviewError
from app.main import create_app, digest, now
from app.studio import hash_password

MODEL = "protocol-substitute"
PURPOSE = "内部目的标记-不应出现在响应里"
MARKER = "紫色独角兽机器人"
BASE = "/api/core/interview"


def profile_json(user_ids):
    item = lambda text: [{"text": text, "basis": "self_reported", "evidence": user_ids[-1:]}] if user_ids else []
    return json.dumps({"type": "profile_draft", "interests": item("想做自己的作品"), "goals": [], "experiences": [], "possible_strengths": [],
                       "roles_to_try": [], "help_needed": [], "time_available": None, "next_practice": [], "conflicts": [], "unknowns": ["可投入时间"]},
                      ensure_ascii=False)


class Script:
    """Protocol substitute for the model: records calls and answers by mode."""

    def __init__(self):
        self.mode, self.calls, self.hook = "ok", [], None

    def __call__(self, system, payload):
        self.calls.append(payload)
        if self.hook:
            self.hook(payload)
        if self.mode == "fail":
            raise InterviewError("model_unavailable", "协议替身：模拟模型不可用；已有记录不变，可以重试。", 503, True)
        if self.mode == "bad":
            return "not json", MODEL
        users = [m["id"] for m in payload["transcript"] if m["role"] == "user"]
        if payload["mode"] == "profile_only" and self.mode != "ask_always":
            return profile_json(users), MODEL
        n = payload["asked_count"] + 1
        return json.dumps({"type": "ask", "question": f"替身问题{n}：你想做的作品下一步打算怎么试？", "purpose": PURPOSE, "dimension": "want_to_make"},
                          ensure_ascii=False), MODEL


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.sqlite3"
        self.patches = [patch("app.team_core.team_model_config", return_value={"api_key": "", "model_id": "未配置"}),
                        patch("app.interview.team_model_config", return_value={"api_key": "", "model_id": "未配置"})]
        for p in self.patches:
            p.start()
        self.script = Script()
        self.client = self.make_client()
        with closing(sqlite3.connect(self.path)) as con:
            for ident, name in [("a", "访谈测试甲"), ("b", "访谈测试乙"), ("c", "其他团队成员")]:
                con.execute("INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at,password_hash) VALUES(?,?,?,?,?,?,?,?)",
                            (ident, "1800000000" + str(ord(ident) - 97), name, "测试", "后端", digest("test-token-" + ident), now(), hash_password("test-only-password")))
            con.commit()
        self.h = lambda x: {"Authorization": "Bearer test-token-" + x}

    def make_client(self, runner="script"):
        return TestClient(create_app(self.path, core_only=True, interview_runner=self.script if runner == "script" else runner))

    def tearDown(self):
        self.client.close()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def get(self, who="a", client=None):
        r = (client or self.client).get(BASE, headers=self.h(who))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def start(self, who="a", client=None, **body):
        return (client or self.client).post(BASE + "/start", json=body, headers=self.h(who))

    def answer(self, state, text="想做一个记账小工具", who="a", rid=None, client=None, **override):
        body = {"version": state["version"], "question_id": state["current_question"]["id"], "request_id": rid or "req-" + uuid4().hex[:12], "text": text}
        body.update(override)
        return (client or self.client).post(BASE + "/answer", json=body, headers=self.h(who))

    def finish(self, state, who="a", rid=None, client=None):
        return (client or self.client).post(BASE + "/finish", json={"version": state["version"], "request_id": rid or "req-" + uuid4().hex[:12]}, headers=self.h(who))

    def confirm(self, version, who="a", rid=None, client=None):
        return (client or self.client).post(BASE + "/confirm", json={"version": version, "request_id": rid or "req-" + uuid4().hex[:12]}, headers=self.h(who))

    def ok(self, r):
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def err(self, r, status, code):
        self.assertEqual(r.status_code, status, r.text)
        self.assertEqual(r.json()["error"]["code"], code, r.text)
        return r.json()["error"]

    def rows(self, sql, *args):
        with closing(sqlite3.connect(self.path)) as con:
            return con.execute(sql, args).fetchall()


class Ownership(Base):
    def test_get_before_start_is_not_started_without_model_call(self):
        self.assertEqual(self.get(), {"status": "not_started"})
        self.assertEqual(self.script.calls, [])

    def test_unauthenticated_requests_get_401(self):
        for headers in ({}, {"Authorization": "Bearer wrong-token"}, {"Authorization": "Basic x"}):
            self.err(self.client.get(BASE, headers=headers), 401, "unauthorized")
            for path, body in (("/start", {}), ("/answer", {"version": 1, "question_id": "q1", "request_id": "req-00000001", "text": "x"}),
                               ("/finish", {"version": 1, "request_id": "req-00000001"}), ("/confirm", {"version": 1, "request_id": "req-00000001"})):
                self.err(self.client.post(BASE + path, json=body, headers=headers), 401, "unauthorized")
        self.assertEqual(self.script.calls, [])

    def test_owner_reads_trusted_version_and_count_others_and_plugin_cannot(self):
        s = self.ok(self.start(stage="university"))
        self.assertEqual((s["status"], s["version"], s["asked_count"], s["current_question"]["id"]), ("asking", 1, 1, "q1"))
        s = self.ok(self.answer(s))
        got = self.get()
        self.assertEqual(got, s)
        self.assertEqual((got["version"], got["asked_count"], [m["id"] for m in got["messages"]]), (2, 2, ["q1", "u2", "q3"]))
        self.assertNotIn(PURPOSE, json.dumps(got, ensure_ascii=False))
        self.assertEqual(self.get("b"), {"status": "not_started"})
        self.err(self.answer(got, who="b"), 409, "interview_not_started")
        self.err(self.finish(got, who="b"), 409, "interview_not_started")
        self.err(self.confirm(2, who="b"), 409, "no_draft")
        team = self.ok(self.client.post("/api/core/teams", json={"name": "访谈隔离"}, headers=self.h("a")))
        token = self.ok(self.client.post(f"/api/core/teams/{team['id']}/connections", json={"label": "插件"}, headers=self.h("a")))["token"]
        plugin = {"Authorization": "Bearer " + token}
        self.err(self.client.get(BASE, headers=plugin), 403, "browser_required")
        for path, body in (("/start", {}), ("/answer", {"version": 2, "question_id": "q3", "request_id": "req-plugin01", "text": "插件代答"}),
                           ("/finish", {"version": 2, "request_id": "req-plugin02"}), ("/confirm", {"version": 2, "request_id": "req-plugin03"})):
            self.err(self.client.post(BASE + path, json=body, headers=plugin), 403, "browser_required")
        self.assertEqual(self.get(), got)

    def test_client_cannot_supply_identity_or_counts(self):
        self.err(self.start(user_id="b"), 422, "invalid_input")
        s = self.ok(self.start())
        self.err(self.answer(s, asked_count=0), 422, "invalid_input")
        self.err(self.answer(s, user_id="b"), 422, "invalid_input")
        self.assertEqual(self.get(), s)
        self.assertEqual(self.get("b"), {"status": "not_started"})


class Persistence(Base):
    def test_restart_keeps_progress_draft_and_confirmation(self):
        s = self.ok(self.answer(self.ok(self.start(age_band="19_25", stage="job_seeking"))))
        self.client.close()
        self.client = self.make_client()
        self.assertEqual(self.get(), s)
        s = self.ok(self.answer(s, "还想做一个练习口语的小程序"))
        self.assertEqual((s["version"], s["asked_count"], s["stage"]), (3, 3, "job_seeking"))
        s = self.ok(self.finish(s))
        self.client.close()
        self.client = self.make_client()
        self.assertEqual(self.get(), s)
        self.assertEqual(s["profile"]["status"], "pending_confirmation")
        s = self.ok(self.confirm(s["version"]))
        self.client.close()
        self.client = self.make_client()
        got = self.get()
        self.assertEqual(got, s)
        self.assertEqual((got["status"], got["profile"]["status"]), ("confirmed", "confirmed"))
        self.assertTrue(got["profile"]["confirmed_at"])


class Idempotency(Base):
    def test_duplicate_request_is_not_appended_twice(self):
        s = self.ok(self.start())
        first = self.ok(self.answer(s, rid="req-dup-0001"))
        calls = len(self.script.calls)
        again = self.ok(self.answer(s, rid="req-dup-0001"))
        self.assertTrue(again["replayed"])
        self.assertEqual({**again, "replayed": False}, first)
        self.assertEqual(len(self.script.calls), calls)
        self.err(self.answer(s, "换了内容", rid="req-dup-0001"), 409, "request_id_reused")
        self.assertEqual(len(self.rows("SELECT 1 FROM core_interview_messages WHERE user_id='a' AND role='user'")), 1)

    def test_stale_version_and_old_question_are_rejected_without_change(self):
        s1 = self.ok(self.start())
        s2 = self.ok(self.answer(s1))
        calls = len(self.script.calls)
        self.assertEqual(self.err(self.answer(s1), 409, "version_conflict")["details"]["current_version"], 2)
        self.err(self.answer(s2, question_id="q1"), 409, "stale_question")
        self.err(self.finish(s1), 409, "version_conflict")
        self.assertEqual(self.get(), s2)
        self.assertEqual(len(self.script.calls), calls)

    def test_invalid_inputs_are_controlled_and_leave_state(self):
        s = self.ok(self.start())
        cases = [({"text": "   "}, "empty_answer"), ({"text": "长" * 1001}, "text_too_long"), ({"text": 123}, "invalid_input"),
                 ({"text": "含\x07控制符"}, "invalid_input"), ({"version": True}, "invalid_input"), ({"version": "1"}, "invalid_input"),
                 ({"version": 0}, "invalid_input"), ({"request_id": "short"}, "invalid_input"), ({"request_id": "含有中文的编号abc"}, "invalid_input"),
                 ({"question_id": ["q1"]}, "invalid_input")]
        for override, code in cases:
            self.err(self.answer(s, **override), 422, code)
        self.err(self.client.post(BASE + "/answer", json={"version": 1, "question_id": "q1", "text": "缺请求编号"}, headers=self.h("a")), 422, "invalid_input")
        self.assertEqual(self.client.post(BASE + "/answer", json=[1], headers=self.h("a")).status_code, 422)
        self.err(self.start(), 409, "interview_exists")
        self.assertEqual(self.get(), s)
        self.assertEqual(len(self.script.calls), 1)

    def test_invalid_start_choices_are_rejected(self):
        self.err(self.start(stage="genius"), 422, "invalid_input")
        self.err(self.start(age_band="7"), 422, "invalid_input")
        self.err(self.start(stage=["university"]), 422, "invalid_input")
        self.assertEqual(self.get(), {"status": "not_started"})
        self.assertEqual(self.script.calls, [])

    def test_ended_interview_rejects_answers_and_start_never_overwrites(self):
        s = self.ok(self.answer(self.ok(self.start())))
        done = self.ok(self.finish(s))
        self.err(self.answer(s), 409, "interview_closed")
        self.err(self.answer({**s, "version": done["version"]}), 409, "interview_closed")
        self.err(self.finish(done), 409, "interview_closed")
        self.assertEqual(self.err(self.start(), 409, "interview_exists")["details"]["status"], "pending_confirmation")
        confirmed = self.ok(self.confirm(done["version"]))
        self.err(self.start(), 409, "interview_exists")
        self.assertEqual(self.get(), confirmed)


class Concurrency(Base):
    def test_no_write_lock_during_model_call_and_second_answer_is_not_adopted(self):
        s = self.ok(self.start())
        entered, release, seen = threading.Event(), threading.Event(), {}

        def hook(payload):
            with closing(sqlite3.connect(self.path, timeout=0.3)) as con:
                con.execute("BEGIN IMMEDIATE")
                con.rollback()
            seen["write_lock_free"] = True
            entered.set()
            release.wait(5)
        self.script.hook = hook
        result = {}
        same_app = TestClient(self.client.app)
        worker = threading.Thread(target=lambda: result.setdefault("r", self.answer(s, "第一份回答", rid="req-race-0001", client=same_app)))
        worker.start()
        self.assertTrue(entered.wait(5))
        self.assertTrue(seen["write_lock_free"])
        self.assertEqual(self.get(), s)
        self.script.hook = None
        self.err(self.answer(s, "第二份回答", rid="req-race-0002"), 409, "interview_busy")
        release.set()
        worker.join(5)
        self.assertEqual(self.ok(result["r"])["version"], 2)
        texts = [t for (t,) in self.rows("SELECT text FROM core_interview_messages WHERE user_id='a' AND role='user'")]
        self.assertEqual(texts, ["第一份回答"])
        same_app.close()

    def test_two_app_instances_racing_only_one_answer_is_saved(self):
        s = self.ok(self.start())
        entered, release = threading.Event(), threading.Event()
        slow = Script()
        slow.hook = lambda payload: (entered.set(), release.wait(5))
        other = self.make_client(runner=slow)
        result = {}
        worker = threading.Thread(target=lambda: result.setdefault("r", self.answer(s, "慢的一份", rid="req-slow-0001", client=other)))
        worker.start()
        self.assertTrue(entered.wait(5))
        self.assertEqual(self.ok(self.answer(s, "快的一份", rid="req-fast-0001"))["version"], 2)
        release.set()
        worker.join(5)
        self.assertEqual(self.err(result["r"], 409, "version_conflict")["details"]["current_version"], 2)
        texts = [t for (t,) in self.rows("SELECT text FROM core_interview_messages WHERE user_id='a' AND role='user'")]
        self.assertEqual(texts, ["快的一份"])
        self.assertEqual(self.get()["version"], 2)
        other.close()


class ModelFailure(Base):
    def test_failure_keeps_record_and_retry_counts_once(self):
        s = self.ok(self.start())
        for mode, status, code in (("fail", 503, "model_unavailable"), ("bad", 502, "model_invalid_json")):
            self.script.mode = mode
            error = self.err(self.answer(s, rid="req-retry-001"), status, code)
            self.assertEqual(error["details"], {"retryable": True, "current_version": 1})
            self.assertEqual(self.get(), s)
        self.script.mode = "ok"
        s2 = self.ok(self.answer(s, rid="req-retry-001"))
        self.assertEqual((s2["version"], s2["asked_count"], s2["replayed"]), (2, 2, False))
        self.assertEqual(len(self.rows("SELECT 1 FROM core_interview_messages WHERE user_id='a' AND role='user'")), 1)

    def test_start_failure_leaves_not_started(self):
        self.script.mode = "fail"
        self.err(self.start(), 503, "model_unavailable")
        self.assertEqual(self.get(), {"status": "not_started"})
        self.script.mode = "ok"
        self.assertEqual(self.ok(self.start())["version"], 1)

    def test_no_model_configured_returns_503_and_no_local_questions(self):
        self.client.close()
        self.client = self.make_client(runner=None)
        error = self.err(self.start(), 503, "model_not_configured")
        self.assertTrue(error["details"]["retryable"])
        self.assertEqual(self.get(), {"status": "not_started"})
        self.assertEqual(self.rows("SELECT * FROM core_interviews"), [])


class LimitsAndConfirm(Base):
    def test_thirty_questions_then_draft_never_a_thirty_first(self):
        s = self.ok(self.start())
        for i in range(29):
            s = self.ok(self.answer(s, f"第{i + 1}次回答"))
        self.assertEqual((s["asked_count"], s["status"]), (30, "asking"))
        self.script.mode = "ask_always"
        self.err(self.answer(s, "最后一次回答", rid="req-limit-001"), 502, "question_limit_reached")
        self.assertEqual(self.get(), s)
        self.script.mode = "ok"
        done = self.ok(self.answer(s, "最后一次回答", rid="req-limit-001"))
        self.assertEqual((done["status"], done["asked_count"], done["profile"]["reason"]), ("pending_confirmation", 30, "limit_reached"))
        self.assertEqual(self.script.calls[-1]["mode"], "profile_only")
        self.assertIsNone(done["current_question"])
        self.assertEqual(len(self.rows("SELECT 1 FROM core_interview_messages WHERE user_id='a' AND role='assistant'")), 30)

    def test_finish_early_then_owner_confirms_without_model(self):
        s = self.ok(self.answer(self.ok(self.start())))
        done = self.ok(self.finish(s))
        self.assertEqual((done["status"], done["profile"]["status"], done["profile"]["reason"]), ("pending_confirmation", "pending_confirmation", "user_finished"))
        self.assertEqual(done["profile"]["draft"]["interests"][0]["evidence"], ["u2"])
        calls = len(self.script.calls)
        confirmed = self.ok(self.confirm(done["version"], rid="req-conf-0001"))
        self.assertEqual((confirmed["status"], confirmed["profile"]["status"], confirmed["version"]), ("confirmed", "confirmed", done["version"] + 1))
        self.assertEqual(confirmed["profile"]["draft"], done["profile"]["draft"])
        self.assertTrue(self.ok(self.confirm(done["version"], rid="req-conf-0001"))["replayed"])
        self.err(self.confirm(confirmed["version"]), 409, "already_confirmed")
        self.assertEqual(len(self.script.calls), calls)

    def test_finish_without_answers_makes_empty_draft_without_model(self):
        s = self.ok(self.start())
        done = self.ok(self.finish(s))
        self.assertEqual(done["source"], {"kind": "no_answers", "model": None})
        self.assertEqual(done["profile"]["draft"]["interests"], [])
        self.assertEqual(len(self.script.calls), 1)

    def test_missing_or_old_draft_cannot_be_confirmed(self):
        self.err(self.confirm(1), 409, "no_draft")
        s = self.ok(self.start())
        self.err(self.confirm(s["version"]), 409, "no_draft")
        s = self.ok(self.answer(s))
        done = self.ok(self.finish(s))
        self.assertEqual(self.err(self.confirm(done["version"] - 1), 409, "version_conflict")["details"]["current_version"], done["version"])
        self.assertEqual(self.get(), done)


class NoLeak(Base):
    def test_confirmed_profile_stays_with_owner(self):
        team = self.ok(self.client.post("/api/core/teams", json={"name": "访谈不外泄"}, headers=self.h("a")))
        base = "/api/core/teams/" + team["id"]
        self.ok(self.client.post("/api/core/join", json={"code": team["code"]}, headers=self.h("b")))
        plugin = {"Authorization": "Bearer " + self.ok(self.client.post(base + "/connections", json={"label": "插件"}, headers=self.h("a")))["token"]}
        s = self.ok(self.answer(self.ok(self.start()), f"我想做一个{MARKER}"))
        done = self.ok(self.confirm(self.ok(self.finish(s))["version"]))
        self.assertIn(MARKER, json.dumps(done, ensure_ascii=False))
        seen = [self.client.get(base, headers=self.h("a")), self.client.get(base, headers=self.h("b")), self.client.get("/api/core/me", headers=self.h("a")),
                self.client.get("/api/core/me", headers=self.h("b")), self.client.get(base + "/context", headers=plugin),
                self.client.get(base + "/my-tasks", headers=plugin), self.client.get(base + "/library", headers=self.h("b")),
                self.client.get(base + "/history", headers=self.h("b")), self.client.get(base + "/handoff.md", headers=self.h("b"))]
        for r in seen:
            self.assertEqual(r.status_code, 200, r.text)
            self.assertNotIn(MARKER, r.text)
            self.assertNotIn(PURPOSE, r.text)
            self.assertNotIn("想做自己的作品", r.text)
        self.assertEqual(self.get("b"), {"status": "not_started"})
        self.assertEqual(self.rows("SELECT profile,skills FROM people WHERE id='a'"), [("测试", "后端")])


if __name__ == "__main__":
    unittest.main()
