"""隔离版新手全链路验收。

只用临时 SQLite、合成账号和协议替身模型，不读取真实资料、不发短信、不调用真实模型。
它检查页面背后的关键动作是否能从注册后的访谈一路走到赛后成长记录。
"""
import json
import os
import sqlite3
import tempfile
import sys
from contextlib import closing
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import create_app, digest, now
from app.studio import hash_password
import app.studio as studio


def plan_runner(context):
    members = context["members"]
    return {"summary": "先做一条能演示的最小路径。",
            "findings": [],
            "tasks": [{"key": "T1", "title": "做一个能提交的最小页面", "owner_id": members[0]["id"],
                       "acceptance": "打开页面，输入内容后能看到真实返回；保存截图。", "depends_on": [],
                       "source_ids": ["direction"],
                       "execution": {"tool": "浏览器和代码编辑器", "steps": ["打开队长发来的项目文件夹", "先用假内容把页面按钮和结果区域摆出来", "等数据格式确认后换成真实返回", "截图并把地址发到团队"],
                                     "ai_prompt": "做出一条最小可演示页面。只按团队方向操作，不猜接口地址；交一张真实返回截图和改动位置；验收时按正常输入试一次。",
                                     "deliverable": "能打开的页面地址和一张真实返回截图", "help_hint": "把停住的页面、报错原文和截图发给队长"}}],
            "questions": []}


def interview_runner(_system, payload):
    if payload["mode"] == "profile_only":
        ids = [m["id"] for m in payload["transcript"] if m["role"] == "user"]
        return json.dumps({"type": "profile_draft", "interests": [], "goals": [], "experiences": [], "possible_strengths": [],
                           "roles_to_try": [], "help_needed": [], "time_available": None, "next_practice": [], "conflicts": [], "unknowns": ["还需要更多资料"]}, ensure_ascii=False), "test-interview"
    n = payload["asked_count"] + 1
    return json.dumps({"type": "ask", "question": f"你准备先做哪一小步？（第{n}问）", "purpose": "了解下一步", "dimension": "want_to_make"}, ensure_ascii=False), "test-interview"


def main():
    with tempfile.TemporaryDirectory(prefix="songban-full-flow-") as tmp:
        db = Path(tmp) / "flow.sqlite3"
        # Replace SMS delivery only inside this isolated process.
        studio.must_deliver = lambda: False
        studio.test_codes_allowed = lambda: True
        studio.deliver_login_code = lambda phone, code: (False, "isolated test")
        app = create_app(db, core_only=True, core_model_runner=plan_runner, interview_runner=interview_runner)
        # 只在这个临时进程打开测试验证码；真实服务不会把验证码显示在网页。
        os.environ["SONGBAN_ALLOW_TEST_CODES"] = "1"
        h_tokens = {}
        checks = []
        def ok(label, response, expected=200):
            checks.append((label, response.status_code == expected))
            if response.status_code != expected:
                raise AssertionError(f"{label}: {response.status_code} {response.text[:500]}")
            return response.json() if response.content else {}
        with TestClient(app) as client:
            for ident, name in (("a", "新手队长"), ("b", "新手队员")):
                phone = "1800000100" + ("1" if ident == "a" else "2")
                code = ok(f"{ident}申请验证码", client.post("/api/studio/codes", json={"phone": phone}))["code"]
                registered = ok(f"{ident}完成注册", client.post("/api/studio/register", json={"phone": phone, "code": code, "password": "password123", "name": name, "onboarding": True}))
                h_tokens[ident] = registered["token"]
            h = lambda who: {"Authorization": "Bearer " + h_tokens[who]}
            # 注册后的个人访谈
            state = ok("开始个人访谈", client.post("/api/core/interview/start", json={"age_band": "13_18", "stage": "secondary_school"}, headers=h("a")))
            state = ok("回答个人访谈", client.post("/api/core/interview/answer", json={"version": state["version"], "question_id": state["current_question"]["id"], "request_id": "iv-00000001", "text": "先做一个能演示的小页面"}, headers=h("a")))
            draft = ok("结束并生成个人画像", client.post("/api/core/interview/finish", json={"version": state["version"], "request_id": "iv-00000002"}, headers=h("a")))
            ok("确认个人画像", client.post("/api/core/interview/confirm", json={"version": draft["version"], "request_id": "iv-00000003"}, headers=h("a")))

            # 比赛卡和组队
            contest = ok("保存比赛公告", client.post("/api/studio/contests", json={"name": "隔离新手赛", "deadline": "2099-01-01T18:00:00+08:00", "source_text": "提交网页、GitHub、PPT、Demo视频；评分看功能和展示。"}, headers=h("a")))
            squad = ok("创建队伍", client.post("/api/studio/squads", json={"name": "新手小队", "contest_id": contest["id"], "project_brief": "做一个能演示的协作页面"}, headers=h("a")))
            ok("队员加入队伍", client.post("/api/studio/squads/join", json={"code": squad["code"]}, headers=h("b")))
            sid = squad["id"]
            for who in "ab": ok(f"{who}填写分工", client.post(f"/api/studio/squads/{sid}/intro", json={"role": "产品", "responsibility": "页面和演示"}, headers=h(who)))
            ok("队长确认分工", client.post(f"/api/studio/squads/{sid}/confirm", headers=h("a")))

            # 连接器对话进入资料库
            tokens = {who: ok(f"{who}生成连接凭证", client.post(f"/api/core/teams/{sid}/connections", json={"label": "个人AI工具"}, headers=h(who)))["token"] for who in "ab"}
            for who, text in (("a", "我想做一个让新手快速组队的页面"), ("b", "我想把比赛要求整理成一张简单清单")):
                ok(f"{who}上传AI对话", client.post(f"/api/core/teams/{sid}/conversation-notes", json={"selected": True, "event_id": "chat-" + who, "user_message": text, "assistant_summary": "先做最小可演示版本", "model_name": "Seed 2.1"}, headers={"Authorization": "Bearer " + tokens[who]}))

            phase = ok("开始首次选题讨论", client.post(f"/api/core/teams/{sid}/phases", json={"title": "首次选题讨论", "mode": "idea_collection"}, headers=h("a")))
            for who in "ab": ok(f"{who}确认已上传", client.post(f"/api/core/teams/{sid}/phase/{phase['id']}/conversation-confirm", json={"confirm": True}, headers=h(who)))
            analysis = ok("团队AI分析选题", client.post(f"/api/core/teams/{sid}/phase/{phase['id']}/ideas/analyze", headers=h("a")))
            idea_id = analysis["body"]["ranked"][0]["idea_id"]
            ok("成员投票", client.post(f"/api/core/teams/{sid}/phase/{phase['id']}/ideas/{idea_id}/vote", headers=h("b")))
            selected = ok("队长确定选题", client.post(f"/api/core/teams/{sid}/phase/{phase['id']}/ideas/select", json={"idea_id": idea_id, "intro": "做一个能演示的新手协作页面", "difficulty": "先把最小页面跑通", "core_chain": "打开页面→输入内容→看到结果"}, headers=h("a")))
            assert selected["phase"]["stage"] == "selected", selected["phase"]
            ok("选题后禁止继续投票", client.post(f"/api/core/teams/{sid}/phase/{phase['id']}/ideas/{idea_id}/vote", headers=h("b")), expected=409)
            ok("选题后禁止新增方案", client.post(f"/api/core/teams/{sid}/phase/{phase['id']}/ideas", json={"title": "不应再出现", "summary": "选题已经结束", "source_ids": []}, headers=h("b")), expected=409)

            proposal = ok("生成任务草案", client.post(f"/api/core/teams/{sid}/review", headers=h("a")))
            snap = ok("读取任务草案", client.get(f"/api/core/teams/{sid}", headers=h("a")))
            ok("队长发布任务", client.post(f"/api/core/teams/{sid}/proposals/{proposal['proposal_id']}/confirm", json={"expected_revision": snap["revision"]}, headers=h("a")))
            active = ok("成员读取自己的任务", client.get(f"/api/core/teams/{sid}/my-tasks", headers=h("a")))
            task = active["tasks"][0]
            ok("成员报告半成品", client.post(f"/api/core/teams/{sid}/reports", json={"event_id": "done-1", "tool": "个人AI工具", "summary": "页面已能打开并显示真实返回", "status": "reported_done", "evidence": ["页面截图"], "task_key": task["key"], "plan_version": active["plan_version"]}, headers={"Authorization": "Bearer " + tokens["a"]}))
            latest = ok("队员看到待检查成果", client.get(f"/api/core/teams/{sid}", headers=h("b")))
            report_id = latest["active_plan"]["tasks"][0]["latest_report_id"]
            ok("队友检查成果", client.post(f"/api/core/teams/{sid}/tasks/{task['key']}/check", json={"expected_revision": latest["revision"], "plan_version": latest["plan_version"], "report_id": report_id, "verdict": "accepted", "note": "按说明打开页面并核对截图，能看到真实返回。"}, headers=h("b")))
            ok("保存最终提交材料", client.put(f"/api/core/teams/{sid}/submission", json={"website_url": "https://example.com/demo", "github_url": "https://github.com/example/demo", "ppt_url": "https://example.com/ppt", "demo_url": "https://example.com/video", "image_url": "https://example.com/image"}, headers=h("a")))
            ok("队长确认已向主办方提交", client.post(f"/api/core/teams/{sid}/submission/confirm", json={"confirm": True}, headers=h("a")))
            ok("结束比赛并写入档案", client.post(f"/api/core/teams/{sid}/finish", json={"confirm": True}, headers=h("a")))
            final = ok("读取赛后档案", client.get("/api/studio/me", headers=h("a")))
            assert "本场角色是产品" in final["growth"], final["growth"]
        print(f"全链路通过：{sum(okay for _, okay in checks)}/{len(checks)} 项")
        os.environ.pop("SONGBAN_ALLOW_TEST_CODES", None)


if __name__ == "__main__":
    main()
