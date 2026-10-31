"""Isolated loopback workbench QA; synthetic users, real SQLite, explicit fixtures.

Run with .venv/Scripts/python.exe scripts/qa_workbench_server.py --port 8896.
Each invocation creates a new DB; never uses .browser-cache/materials/manual.sqlite3.
"""
import argparse
import json
import os
import sqlite3
import sys
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from app.main import create_app, digest, now
from app.planner import PlannerError
from app.studio import hash_password
from tests.test_materials import fixture_model
from tests.test_team_core import plan_for

FIXTURE_MODEL = "workbench-protocol-fixture-v1"


def build_app(folder, resume=False):
    db_path = folder / "workbench.sqlite3"
    if db_path.exists() and not resume:
        raise RuntimeError("Refusing to reuse an existing QA DB; choose a new output folder")
    if resume and (not db_path.exists() or not (folder / "manifest.json").exists()):
        raise RuntimeError("--resume requires an existing isolated QA database and manifest")
    calls = json.loads((folder / "model-calls.json").read_text(encoding="utf-8")) if resume and (folder / "model-calls.json").exists() else []
    lock = threading.Lock()

    def workbench_fixture(context):
        # Intentionally deterministic protocol behavior; never a real model evaluation.
        with lock:
            calls.append(context)
            (folder / "model-calls.json").write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding="utf-8")
        # Match the latest prompt only: historical failure markers must not poison new turns.
        prompt = context.get("text", context.get("user_text", context.get("prompt", "")))
        if not prompt:
            history = context.get("messages", context.get("history", []))
            prompt = next((m.get("text", m.get("content", "")) for m in reversed(history) if m.get("role") == "user"), "")
        if "[QA_SLOW]" in prompt:
            time.sleep(3)
        if "[QA_TIMEOUT]" in prompt:
            raise PlannerError("model_timeout", "协议夹具模拟超时，结果未知。", 504)
        if "[QA_FAIL]" in prompt:
            raise PlannerError("model_invalid_response", "协议夹具模拟模型失败。", 502)
        names = [s.get("name", s.get("metadata", {}).get("name", s.get("id", ""))) for s in context.get("sources", [])]
        text = "【协议测试夹具，非真实模型效果】已选来源：" + ("、".join(names) or "未选择材料")
        text += "\n建议先核对范围，再由队长确认共同方向。\n" + str(prompt)
        text += '\n<img src=x onerror="window.__workbenchXSS=1"><script>window.__workbenchXSS=2</script>'
        text += '\nQA_PRIVATE_ASSISTANT_ONLY_MARKER：这条助手私密细节不应随编辑后的摘要外发。'
        return {"text": text, "requested_model": "qa-requested-model", "actual_model": FIXTURE_MODEL, "mode": "fixture", "actions": [
            {"type": "prepare_direction", "label": "核对方向草稿", "fields": {"goal": "夹具建议：校园失物招领助手", "rules": "先验证真实需求，提交可演示作品。"}},
            {"type": "share_turn", "label": "预览共享这轮讨论"},
            {"type": "request_team_review", "label": "进入团队统筹"},
            {"type": "open_page", "label": "查看原任务", "page": "tasks"},
            {"type": "open_page", "label": "非法跳转不得出现", "page": "javascript:window.__workbenchXSS=3"},
            {"type": "execute", "label": "非法执行不得出现", "command": "never execute"},
        ]}

    app = create_app(db_path, core_only=True, core_model_runner=plan_for,
                     materials_model_runner=fixture_model, workbench_model_runner=workbench_fixture)
    if resume:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if Path(manifest["db"]).resolve() != db_path.resolve():
            raise RuntimeError("Manifest database does not match isolated folder")
        manifest["pid"] = os.getpid()
        manifest["resumed_at"] = now()
        (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return app
    users = {}
    with closing(sqlite3.connect(db_path)) as con:
        for key, suffix, name in [("captain", "1", "验收队长"), ("member", "2", "验收队员"), ("outsider", "3", "他队验收成员"), ("personal", "4", "无团队验收成员")]:
            ident, token = "qa-workbench-" + key, "test-workbench-" + key
            phone = "1880000890" + suffix
            con.execute("INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at,password_hash) VALUES(?,?,?,?,?,?,?,?)",
                        (ident, phone, name, "本机合成测试身份", "验收", digest(token), now(), hash_password("workbench-test-password")))
            users[key] = {"id": ident, "token": token, "name": name, "phone": phone}
        con.commit()
    with TestClient(app) as client:
        def api(method, url, user="captain", body=None):
            response = client.request(method, url, headers={"Authorization": "Bearer " + users[user]["token"]}, **({"json": body} if body is not None else {}))
            if response.status_code != 200:
                raise RuntimeError(f"Fixture setup {method} {url}: {response.status_code} {response.text}")
            return response.json()

        team = api("POST", "/api/core/teams", body={"name": "工作台隔离验收小队"})
        api("POST", "/api/core/join", "member", {"code": team["code"]})
        other = api("POST", "/api/core/teams", "outsider", {"name": "不可访问的他队"})
        sources = {}
        for key, user, team_id in [("personal", "personal", None), ("captain_private", "captain", None), ("member_private", "member", None), ("team", "captain", team["id"]), ("other_team", "outsider", other["id"])]:
            space = api("GET", "/api/materials/space" + ("?team_id=" + team_id if team_id else ""), user)
            url = "/api/materials/spaces/" + space["id"]
            source = api("POST", url + "/sources", user, {"request_id": "fixture-source-" + key, "kind": "text", "name": "夹具来源-" + key, "content": "合成资料：提交一个可演示作品。来源范围=" + key, "nature": "sample"})["source"]
            snap = api("GET", url, user)
            api("POST", url + "/sources/" + source["id"] + "/parse", user, {"expected_revision": snap["revision"]})
            sources[key] = {"id": source["id"], "space_id": space["id"], "name": "夹具来源-" + key}
    manifest = {"pid": os.getpid(), "db": str(db_path), "created_at": now(), "users": users, "team": team, "other_team": other,
                "sources": sources, "model": "explicit protocol fixture; no paid model calls", "sms": "disabled; no login-code requests needed"}
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return app


if __name__ == "__main__":
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8896)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true", help="Reopen only a previously created isolated QA database")
    args = parser.parse_args()
    folder = args.output or ROOT / ".browser-cache" / "workbench" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    folder = folder.resolve()
    allowed = (ROOT / ".browser-cache" / "workbench").resolve()
    if not folder.is_relative_to(allowed):
        parser.error("--output must be inside .browser-cache/workbench")
    folder.mkdir(parents=True, exist_ok=True)
    with patch("app.studio.deliver_login_code", side_effect=RuntimeError("SMS is disabled in isolated workbench QA")), \
         patch("app.team_core.team_model_config", return_value={"api_key": "", "model_id": "协议测试夹具"}):
        app = build_app(folder, args.resume)
        print(json.dumps({"pid": os.getpid(), "url": f"http://127.0.0.1:{args.port}", "output": str(folder)}), flush=True)
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
