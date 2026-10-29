import copy
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from app.planner import discover_models, local_plan, model_plan


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(os.environ, {k:"" for k in ["DEEPSEEK_API_KEY","MODEL_API_KEY","MODEL_BASE_URL","MODEL_NAME"]})
        self.env_patch.start()
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "test.sqlite3"
        self.client = TestClient(create_app(self.db))
        self.payload = {
            "name": "协作流程测试",
            "deadline": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "members": [
                {"name": "队长", "role": "产品与后端", "skills": "Python", "available_hours": 4.0},
                {"name": "胡", "role": "前端", "skills": "JavaScript", "available_hours": 4.0},
            ],
        }
        created = self.client.post("/api/projects", json=self.payload)
        self.assertEqual(created.status_code, 201)
        self.pid = created.json()["project_id"]
        self.invites = created.json()["invites"]
        self.tokens = [i["access_token"] for i in self.invites]

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()
        self.env_patch.stop()

    def req(self, method, suffix="", body=None, who=0, expected=200, client=None):
        headers = {} if who is None else {"Authorization": "Bearer " + self.tokens[who]}
        result = (client or self.client).request(method, f"/api/projects/{self.pid}{suffix}", json=body, headers=headers)
        self.assertEqual(result.status_code, expected, result.text if result.status_code != expected else "")
        return result

    def workspace(self, who=0):
        return self.req("GET", who=who).json()

    def sources(self):
        for kind, text in [("rules", "需交付真实演示和说明，评分关注用户价值与实现质量。"), ("discussion", "目标：两人协作完成一个真实流程。\n决定：先完成接口与页面，再联调和整理交付。\n待确认：双方确认请求字段。")]:
            self.req("POST", "/sources", {"kind": kind, "title": kind, "body": text}, expected=201)

    def draft(self):
        self.sources()
        return self.req("POST", "/proposals", {"mode": "local_rules"}, expected=201).json()

    def confirmed(self):
        draft = self.draft()
        return self.req("POST", f"/proposals/{draft['id']}/confirm", {"expected_version": draft["version"]}).json()

    def act(self, key, action, who=0, note="", expected=200, version=None):
        task = next(t for t in self.workspace()["tasks"] if t["task_key"] == key)
        return self.req("POST", f"/tasks/{task['id']}/actions", {"expected_version": task["version"] if version is None else version, "action": action, "note": note}, who, expected)

    def finish(self, key, who):
        self.act(key, "start", who)
        self.act(key, "submit", who, "已按标准操作并保存成果地址与说明。")
        self.act(key, "accept", 1-who, "已核对成果与验收标准。")

    def test_F01_invalid_projects(self):
        changes = [
            {"name": "   "},
            {"deadline": "2026-01-01T01:00:00+08:00"},
            {"deadline": "2099-01-01T01:00:00"},
            {"members": [{**m, "name": "相同"} for m in self.payload["members"]]},
            {"members": [{**self.payload["members"][0], "available_hours": -1}, self.payload["members"][1]]},
            {"members": [{**self.payload["members"][0], "available_hours": True}, self.payload["members"][1]]},
        ]
        for change in changes:
            with self.subTest(change=list(change)):
                result = self.client.post("/api/projects", json={**self.payload, **change})
                self.assertEqual(result.status_code, 422)

    def test_F02_requires_both_sources(self):
        self.req("POST", "/proposals", {"mode": "local_rules"}, expected=422)
        self.req("POST", "/sources", {"kind": "rules", "title": "规则", "body": "原文"}, expected=201)
        self.req("POST", "/proposals", {"mode": "local_rules"}, expected=422)

    def test_F02_source_limit_and_whitespace(self):
        for body in [" ", "a" * 20001]:
            self.req("POST", "/sources", {"kind": "rules", "title": "规则", "body": body}, expected=422)
        for _ in range(12):
            self.req("POST", "/sources", {"kind": "rules", "title": "原文", "body": "小段原文"}, expected=201)
        self.req("POST", "/sources", {"kind": "rules", "title": "超过份数", "body": "原文"}, expected=422)

    def test_F02_rules_are_labelled_not_model(self):
        draft = self.draft()
        self.assertEqual(draft["mode"], "local_rules")
        self.assertIn("非大模型", draft["source_label"])
        self.assertEqual(self.workspace()["tasks"], [])
        self.assertIn("两人协作", draft["content"]["goal"])

    def test_F02_missing_model_keeps_sources_and_no_fake_success(self):
        self.sources()
        with patch.dict(os.environ, {k: "" for k in ["MODEL_API_KEY", "MODEL_BASE_URL", "MODEL_NAME"]}):
            self.req("POST", "/proposals", {"mode": "model"}, expected=503)
        state = self.workspace()
        self.assertEqual(len(state["sources"]), 2)
        self.assertEqual(state["proposals"], [])
        self.assertEqual(state["tasks"], [])

    def test_F03_edit_goal_owner_and_citations(self):
        draft = self.draft()
        content = copy.deepcopy(draft["content"])
        content["goal"] = "人工核对过的新目标"
        result = self.req("PUT", f"/proposals/{draft['id']}", {"expected_version": 1, "content": content}).json()
        self.assertEqual(result["version"], 2)
        self.assertEqual(result["content"]["goal"], content["goal"])
        self.req("PUT", f"/proposals/{draft['id']}", {"expected_version": 1, "content": content}, expected=409)
        for mutation in ["quote", "owner", "cycle", "missing", "duplicate", "all_optional", "late"]:
            bad = copy.deepcopy(content)
            if mutation == "quote": bad["tasks"][0]["evidence"][0]["quote"] = "不存在的来源内容"
            if mutation == "owner": bad["tasks"][0]["owner_id"] = "other-team-person"
            if mutation == "cycle": bad["tasks"][0]["depends_on"] = ["T4"]
            if mutation == "missing": bad["tasks"][0]["depends_on"] = ["unknown"]
            if mutation == "duplicate": bad["tasks"][1]["key"] = "T1"
            if mutation == "all_optional":
                for task in bad["tasks"]: task["priority"] = "should"
            if mutation == "late": bad["tasks"][0]["due_at"] = "2099-01-01T00:00:00Z"
            with self.subTest(mutation=mutation):
                self.req("PUT", f"/proposals/{draft['id']}", {"expected_version": 2, "content": bad}, expected=422)

    def test_F04_only_captain_confirm_and_single_plan(self):
        draft = self.draft()
        self.req("POST", f"/proposals/{draft['id']}/confirm", {"expected_version": 1}, who=1, expected=403)
        self.assertEqual(self.workspace()["tasks"], [])
        self.req("POST", f"/proposals/{draft['id']}/confirm", {"expected_version": 1})
        self.req("POST", f"/proposals/{draft['id']}/confirm", {"expected_version": 1}, expected=409)
        self.assertEqual(len(self.workspace()["tasks"]), 4)
        self.req("POST", "/sources", {"kind": "discussion", "title": "新增", "body": "新增范围"}, expected=409)
        self.req("POST", "/proposals", {"mode": "local_rules"}, expected=409)

    def test_F04_stale_proposal(self):
        draft = self.draft()
        self.req("POST", "/sources", {"kind": "discussion", "title": "变更", "body": "追加决定"}, expected=201)
        self.req("POST", f"/proposals/{draft['id']}/confirm", {"expected_version": 1}, expected=409)
        self.assertTrue(self.workspace()["proposals"][0]["stale"])

    def test_F04_capacity_exceeded_then_fixed(self):
        draft = self.draft()
        content = copy.deepcopy(draft["content"])
        content["tasks"][0]["estimated_hours"] = 8.0
        self.req("PUT", f"/proposals/{draft['id']}", {"expected_version": 1, "content": content})
        self.req("POST", f"/proposals/{draft['id']}/confirm", {"expected_version": 2}, expected=422)
        self.assertEqual(self.workspace()["tasks"], [])
        content["tasks"][0]["estimated_hours"] = 2.0
        self.req("PUT", f"/proposals/{draft['id']}", {"expected_version": 2, "content": content})
        self.req("POST", f"/proposals/{draft['id']}/confirm", {"expected_version": 3})

    def test_F05_owner_and_dependencies(self):
        self.confirmed()
        self.act("T1", "start", who=1, expected=403)
        self.act("T3", "start", expected=409)
        self.act("T1", "submit", note="直接提交", expected=409)
        self.finish("T1", 0)
        self.act("T3", "start", expected=409)
        self.finish("T2", 1)
        self.act("T3", "start")

    def test_F06_block_return_self_review_and_recovery(self):
        self.confirmed()
        self.act("T1", "start")
        self.act("T1", "block", expected=422)
        self.act("T1", "block", note="缺少双方确认的字段")
        self.act("T1", "resume")
        self.act("T1", "submit", note=" ", expected=422)
        self.act("T1", "submit", note="接口已实现并提供结果")
        self.act("T1", "accept", expected=403)
        self.act("T1", "return", who=1, expected=422)
        self.act("T1", "return", who=1, note="还缺少失败路径证据")
        self.act("T1", "submit", note="补齐成功与失败请求证据")
        self.act("T1", "accept", who=1, note="核对完成")
        self.act("T1", "start", expected=409)
        report = self.req("GET", "/recap").json()
        self.assertEqual(report["stats"]["block_events"], 1)
        self.assertEqual(report["stats"]["return_events"], 1)
        self.assertFalse(report["ready"])

    def test_F07_invalid_and_cross_project_auth(self):
        self.req("GET", who=None, expected=401)
        other = self.client.post("/api/projects", json={**self.payload, "name": "另一队"}).json()
        for method, suffix, body in [("GET", "", None), ("GET", "/recap", None), ("GET", "/export", None), ("POST", "/sources", {"kind":"rules","title":"越权","body":"原文"})]:
            response = self.client.request(method, f"/api/projects/{other['project_id']}{suffix}", json=body, headers={"Authorization": "Bearer " + self.tokens[0]})
            self.assertEqual(response.status_code, 401)

    def test_F07_tokens_hashed_and_rotation_revokes_old(self):
        with closing(sqlite3.connect(self.db)) as con:
            stored = [row[0] for row in con.execute("SELECT token_hash FROM members")]
        self.assertTrue(all(token not in stored for token in self.tokens))
        self.assertNotIn("token_hash", self.req("GET").text)
        mid = self.invites[1]["member_id"]
        self.req("POST", f"/members/{mid}/rotate-token", who=1, expected=403)
        rotated = self.req("POST", f"/members/{mid}/rotate-token").json()
        self.req("GET", who=1, expected=401)
        self.tokens[1] = rotated["access_token"]
        self.req("GET", who=1)
        self.req("POST", f"/members/{self.invites[0]['member_id']}/rotate-token", expected=422)

    def test_F07_concurrent_update_conflict(self):
        self.confirmed()
        task = self.workspace()["tasks"][0]
        url = f"/api/projects/{self.pid}/tasks/{task['id']}/actions"
        def update(_):
            return self.client.post(url, json={"expected_version":1,"action":"start","note":""}, headers={"Authorization":"Bearer " + self.tokens[0]}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = sorted(pool.map(update, range(2)))
        self.assertEqual(codes, [200, 409])
        self.assertEqual(self.workspace()["tasks"][0]["version"], 2)

    def test_F08_full_workflow_export_and_F09_reopen_database(self):
        self.confirmed()
        for key, who in [("T1", 0), ("T2", 1), ("T3", 0), ("T4", 1)]: self.finish(key, who)
        report = self.req("GET", "/recap").json()
        self.assertTrue(report["ready"])
        self.assertEqual(report["stats"]["must_accepted"], 4)
        self.assertEqual(self.workspace()["project"]["phase"], "ready")
        text = self.req("GET", "/export").text
        self.assertIn("过程记录", text)
        self.assertEqual(text.count("- [x]"), 4)
        self.assertNotIn(self.tokens[0], text)
        with TestClient(create_app(self.db)) as restarted:
            state = self.req("GET", client=restarted).json()
            self.assertEqual(state["project"]["phase"], "ready")
            self.assertEqual(len(state["tasks"]), 4)
            self.assertGreater(len(state["events"]), 10)

    def test_F08_optional_task_does_not_block_delivery(self):
        draft = self.draft()
        content = draft["content"]
        content["tasks"][-1]["priority"] = "should"
        self.req("PUT", f"/proposals/{draft['id']}", {"expected_version":1,"content":content})
        self.req("POST", f"/proposals/{draft['id']}/confirm", {"expected_version":2})
        for key,who in [("T1",0),("T2",1),("T3",0)]: self.finish(key,who)
        self.assertTrue(self.req("GET", "/recap").json()["ready"])

    def test_F09_malformed_requests_do_not_echo_input(self):
        secret = "FAKE_SENSITIVE_INPUT_ONLY_FOR_TEST"
        result = self.client.post("/api/projects", content='{"name":"' + secret, headers={"Content-Type":"application/json"})
        self.assertEqual(result.status_code, 422)
        self.assertNotIn(secret, result.text)
        oversized = self.client.post("/api/projects", content="a"*300001, headers={"Content-Type":"application/json"})
        self.assertEqual(oversized.status_code, 413)
        oversized_patch = self.client.patch("/api/studio/me", content="a"*300001, headers={"Content-Type":"application/json"})
        self.assertEqual(oversized_patch.status_code, 413)

    def test_F09_model_protocol_mock_and_errors(self):
        self.sources()
        captured = []
        def success(request):
            payload = json.loads(request.content)
            self.assertEqual(payload["response_format"], {"type":"json_object"})
            context = json.loads(payload["messages"][1]["content"])
            captured.append(context)
            return httpx.Response(200, json={"model":"mock-response-full-model-id","choices":[{"finish_reason":"stop","message":{"content":json.dumps(local_plan(context),ensure_ascii=False)}}]})
        env = {"MODEL_API_KEY":"FAKE_TEST_ONLY_KEY", "MODEL_BASE_URL":"https://model.example.invalid/v1", "MODEL_NAME":"mock-only"}
        with patch.dict(os.environ, env):
            with TestClient(create_app(self.db, model_runner=lambda c:model_plan(c,httpx.MockTransport(success)))) as mock_client:
                result = self.req("POST", "/proposals", {"mode":"model"}, expected=201, client=mock_client).json()
                self.assertEqual(result["mode"], "model")
                self.assertEqual(result["response_model_id"], "mock-response-full-model-id")
                self.assertEqual(len(captured[0]["sources"]),2)
                self.assertNotIn("token_hash", json.dumps(captured))
            for status in [401,403,429,500]:
                def fail(_request): return httpx.Response(status, text="FAKE_TEST_ONLY_KEY upstream-private-body")
                with TestClient(create_app(self.db, model_runner=lambda c:model_plan(c,httpx.MockTransport(fail)))) as mock_client:
                    result=self.req("POST", "/proposals", {"mode":"model"}, expected=502 if status==500 else 503, client=mock_client)
                    self.assertNotIn("FAKE_TEST_ONLY_KEY",result.text)
                    self.assertNotIn("upstream-private-body",result.text)

    def test_F09_insufficient_balance_preserves_data_and_returns_clear_error(self):
        self.sources()
        def insufficient(_request):
            return httpx.Response(402, json={"error":{"type":"insufficient_balance_error","message":"FAKE_TEST_ONLY_KEY private-provider-detail"}})
        env={"DEEPSEEK_API_KEY":"FAKE_TEST_ONLY_KEY"}
        with patch.dict(os.environ,env), TestClient(create_app(self.db,model_runner=lambda c:model_plan(c,httpx.MockTransport(insufficient)))) as model_client:
            result=self.req("POST","/proposals",{"mode":"model"},expected=503,client=model_client)
            self.assertEqual(result.json()["error"]["code"],"model_insufficient_balance")
            self.assertIn("余额不足",result.json()["error"]["message"])
            self.assertNotIn("FAKE_TEST_ONLY_KEY",result.text)
            self.assertNotIn("private-provider-detail",result.text)
        state=self.workspace()
        self.assertEqual(len(state["sources"]),2)
        self.assertEqual(state["tasks"],[])
        self.assertEqual(state["proposals"],[])

    def test_F09_invalid_model_semantics_and_timeout(self):
        self.sources()
        def bad(context):
            result=local_plan(context);result["tasks"][0]["evidence"][0]["quote"]="幻觉引用";return result
        with TestClient(create_app(self.db,model_runner=bad)) as model_client:
            self.req("POST","/proposals",{"mode":"model"},expected=502,client=model_client)
        self.assertEqual(self.workspace()["proposals"],[])
        env={"MODEL_API_KEY":"FAKE_TEST_ONLY_KEY","MODEL_BASE_URL":"https://model.example.invalid/v1","MODEL_NAME":"mock"}
        def timeout(request):raise httpx.ReadTimeout("test timeout",request=request)
        with patch.dict(os.environ,env),TestClient(create_app(self.db,model_runner=lambda c:model_plan(c,httpx.MockTransport(timeout)))) as model_client:
            self.req("POST","/proposals",{"mode":"model"},expected=504,client=model_client)

    def test_F09_generation_context_race(self):
        self.sources()
        def during(context):
            self.req("POST","/sources",{"kind":"discussion","title":"并发追加","body":"最新决定"},expected=201)
            return local_plan(context)
        with TestClient(create_app(self.db,model_runner=during)) as model_client:
            self.req("POST","/proposals",{"mode":"model"},expected=409,client=model_client)
        self.assertEqual(self.workspace()["proposals"],[])

    def test_F10_health_static_flow_and_cors(self):
        self.assertEqual(self.client.get("/health").json()["status"], "ok")
        for url in ["/","/static/app.js","/static/style.css","/workflow","/api/openapi.json"]:
            response=self.client.get(url)
            self.assertEqual(response.status_code,200,url)
        self.assertIn("不能自验",self.client.get("/workflow").text)
        response=self.client.options(f"/api/projects/{self.pid}",headers={"Origin":"http://localhost:5173","Access-Control-Request-Method":"GET","Access-Control-Request-Headers":"authorization"})
        self.assertEqual(response.headers.get("access-control-allow-origin"),"http://localhost:5173")
        response=self.client.get("/health",headers={"Origin":"https://untrusted.invalid"})
        self.assertNotIn("access-control-allow-origin",response.headers)

    def test_F11_builtin_deepseek_full_name_without_invented_connection(self):
        info=self.workspace()["current_model"]
        self.assertEqual(info["name"],"DeepSeek-V4.1-Flash")
        self.assertEqual(info["model_id"],"deepseek-flash")
        self.assertFalse(info["key_configured"])

    def test_F11_custom_model_discovery_selection_no_key_leak_and_restart_reset(self):
        fake_key="FAKE_CUSTOM_KEY_NOT_A_REAL_SECRET"
        full_id="vendor/complete-model-2026-10-26-version-pro"
        def list_models(request):
            self.assertEqual(request.method,"GET")
            self.assertEqual(request.url.path,"/v1/models")
            self.assertEqual(request.headers["authorization"],"Bearer "+fake_key)
            return httpx.Response(200,json={"data":[{"id":full_id,"name":"Complete Model Pro"},{"id":"full-id-without-display-name"}]})
        runner=lambda b,k:discover_models(b,k,httpx.MockTransport(list_models))
        with TestClient(create_app(self.db,discovery_runner=runner,model_runner=local_plan)) as model_client:
            body={"base_url":"https://api.deepseek.com/v1","api_key":fake_key}
            self.req("POST","/model/discover",body,who=1,expected=403,client=model_client)
            result=self.req("POST","/model/discover",body,client=model_client).json()
            self.assertEqual(result["models"][0]["id"],full_id)
            self.assertEqual(result["models"][1]["name"],"full-id-without-display-name")
            self.assertNotIn(fake_key,json.dumps(result))
            selection={"mode":"custom","expected_version":0,"discovery_id":result["discovery_id"],"model_id":full_id}
            self.req("PUT","/model",{**selection,"model_id":"guessed-model"},expected=422,client=model_client)
            selected=self.req("PUT","/model",selection,client=model_client).json()
            self.assertEqual(selected["model_id"],full_id)
            self.assertTrue(selected["key_configured"])
            self.req("PUT","/model",{"mode":"builtin","expected_version":0},expected=409,client=model_client)
            state=self.req("GET",client=model_client)
            self.assertNotIn(fake_key,state.text)
            self.sources()
            generated=self.req("POST","/proposals",{"mode":"model"},expected=201,client=model_client).json()
            self.assertEqual(generated["model_id"],full_id)
            self.assertIn(full_id,generated["source_label"])
            exported=self.req("GET","/export",client=model_client).text
            self.assertNotIn(fake_key,exported)
        with TestClient(create_app(self.db)) as restarted:
            self.assertEqual(self.req("GET",client=restarted).json()["current_model"]["mode"],"builtin")
        with closing(sqlite3.connect(self.db)) as con:
            dump="\n".join(con.iterdump())
        self.assertNotIn(fake_key,dump)

    def test_F11_discovery_rejects_unsafe_url_and_bad_key(self):
        for base in ["http://127.0.0.1:8886","https://127.0.0.1/v1","https://api.deepseek.com.evil.invalid/v1","https://api.deepseek.com/v1?secret=test"]:
            self.req("POST","/model/discover",{"base_url":base,"api_key":"FAKE_TEST_ONLY"},expected=422)
        def bad_auth(request): return httpx.Response(401,text="FAKE_TEST_ONLY upstream-private")
        with TestClient(create_app(self.db,discovery_runner=lambda b,k:discover_models(b,k,httpx.MockTransport(bad_auth)))) as model_client:
            result=self.req("POST","/model/discover",{"base_url":"https://api.deepseek.com","api_key":"FAKE_TEST_ONLY"},expected=422,client=model_client)
            self.assertNotIn("FAKE_TEST_ONLY",result.text)
            self.assertNotIn("upstream-private",result.text)

    def test_F11_model_discovery_ticket_is_project_bound_and_cleared_on_builtin(self):
        def runner(b,k):return {"base_url":b,"provider":"api.deepseek.com","models":[{"id":"deepseek-v4-pro","name":"DeepSeek-V4-Pro"}]}
        with TestClient(create_app(self.db,discovery_runner=runner)) as model_client:
            found=self.req("POST","/model/discover",{"base_url":"https://api.deepseek.com","api_key":"FAKE_TEST_ONLY"},client=model_client).json()
            self.req("PUT","/model",{"mode":"builtin","expected_version":0},client=model_client)
            self.req("PUT","/model",{"mode":"custom","expected_version":1,"discovery_id":found["discovery_id"],"model_id":"deepseek-v4-pro"},expected=409,client=model_client)


if __name__ == "__main__":
    unittest.main(verbosity=2)
