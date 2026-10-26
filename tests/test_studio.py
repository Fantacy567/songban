import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.contest_intel import (
    extract_urls,
    extract_weixin_image_urls,
    heuristic_extract_facts,
    parse_weixin_article,
    prepare_weixin_url,
    weixin_error_page,
)
from app.studio import coach_reply, extract_submissions, skill_text, strategic_kind

SOURCE = "主办方要求：可演示作品、宣传片、PPT、分工说明，以及 GitHub 仓库链接。"


class ExtractTests(unittest.TestCase):
    def test_extracts_weixin_mp_links_from_chat_text(self):
        urls = extract_urls("群里发了 https://mp.weixin.qq.com/s/AbCdEfGhIjKl 大家看一下")
        self.assertEqual(urls[0], "https://mp.weixin.qq.com/s/AbCdEfGhIjKl")

    def test_parses_weixin_article_html(self):
        html = """
        <html><head>
          <meta property="og:title" content="回响黑客松报名通知">
          <meta property="og:description" content="需提交 PPT 和 GitHub 仓库">
        </head><body>
          <script>var msg_title = "回响黑客松报名通知"; var nickname = "主办方";</script>
          <div id="js_content"><p>主办方要求：可演示作品、宣传片、PPT、分工说明。</p><div><span>请按时提交</span></div></div>
        </body></html>
        """
        text, title = parse_weixin_article(html)
        self.assertEqual(title, "回响黑客松报名通知")
        self.assertIn("PPT", text)
        self.assertIn("公众号：主办方", text)

    def test_prepare_weixin_url_adds_nwr_flag(self):
        self.assertIn(
            "nwr_flag=1",
            prepare_weixin_url("https://mp.weixin.qq.com/s/RAfwuPBH1yFPtNJt0acOMQ"),
        )

    def test_detects_weixin_error_page_and_images(self):
        self.assertTrue(weixin_error_page("<title>未知错误</title><p>未知错误，请稍后再试</p>"))
        html = '<div id="js_content"><img data-src="https://mmecoa.qpic.cn/sz_mmecoa_png/abc/640?wx_fmt=png"/></div>'
        self.assertEqual(extract_weixin_image_urls(html)[0].startswith("https://mmecoa.qpic.cn/"), True)

    def test_heuristic_extracts_labeled_contest_facts(self):

        raw = """
        标题：ClawHunt 72小时黑客松上海站
        活动时间：2025年3月14日 至 2025年3月17日，共72小时
        地点：上海市徐汇区创新中心
        参赛人数：限120支队伍，每队3-5人
        赛道：AI Agent、具身智能、开源工具
        报名要求：面向在校生与初创团队
        奖品：总奖金10万元，冠军3万
        提交要求：Demo、GitHub 仓库、路演视频
        注意事项：需实名认证
        """
        facts = heuristic_extract_facts(raw)
        self.assertIn("2025", facts["time"])
        self.assertIn("上海", facts["location"])
        self.assertIn("120", facts["participants"])
        self.assertTrue("AI" in facts["tracks"] or "具身" in facts["tracks"])
        self.assertIn("在校生", facts["selection"])
        self.assertIn("10万", facts["prizes"].replace(" ", ""))
        self.assertIn("GitHub", facts["submissions_text"])
        self.assertIn("实名", facts["other"])

    def test_extracts_more_than_a_demo(self):
        self.assertEqual(extract_submissions(SOURCE), ["宣传片", "PPT", "分工说明", "GitHub 仓库", "可演示作品"])

    def test_strategic_kinds(self):
        self.assertEqual(strategic_kind("我们要改主干，必须任务加上登录"), "trunk")
        self.assertEqual(strategic_kind("海报晚上再做"), None)

    def test_private_coach_sends_team_direction_questions_back(self):
        reply = coach_reply("我们在做什么", "路演", "协作助手")
        self.assertIn("团队方向", reply)
        self.assertIn("协作助手", reply)
        self.assertNotIn("必须任务加上", reply)

    def test_skill_file_is_identical_for_the_same_inputs(self):
        one = skill_text("协作助手", "做出能演示的一条", ["PPT", "GitHub 仓库"])
        self.assertEqual(one, skill_text("协作助手", "做出能演示的一条", ["PPT", "GitHub 仓库"]))
        self.assertIn("全队相同", one)
        self.assertNotIn("技术设计：", one)


class StudioFlowTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {k: "" for k in [
                "DEEPSEEK_API_KEY", "MODEL_API_KEY", "MODEL_BASE_URL", "MODEL_NAME",
                "SONGBAI_REQUIRE_SMS", "ALIYUN_ACCESS_KEY_ID", "ALIYUN_ACCESS_KEY_SECRET",
                "ALIYUN_SMS_SIGN_NAME", "ALIYUN_SMS_TEMPLATE_CODE",
            ]},
        )
        self.env.start()
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(Path(self.temp.name) / "t.sqlite3"))
        self.deadline = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()
        self.env.stop()

    def issue(self, phone):
        result = self.client.post("/api/studio/codes", json={"phone": phone})
        self.assertEqual(result.status_code, 200, result.text)
        body = result.json()
        self.assertFalse(body["sent"])
        self.assertEqual(len(body["code"]), 6)
        self.assertTrue(body["code"].isdigit())
        self.assertEqual(self.client.get("/api/studio/me").status_code, 401)
        return body["code"]

    def enter(self, phone, name, skills, profile="做过产品和演示"):
        code = self.issue(phone)
        result = self.client.post("/api/studio/register", json={"phone": phone, "code": code, "name": name, "skills": skills, "profile": profile, "github": True, "feishu": True})
        self.assertIn(result.status_code, (200, 201), result.text)
        return result.json()

    def auth(self, token):
        return {"Authorization": "Bearer " + token}

    def test_phone_is_the_login_and_profile_is_asked_once(self):
        first = self.enter("13800001111", "孔祥梨", "产品、路演")
        self.assertFalse(first["returning"])
        again = self.enter("13800001111", "别人", "后端高手")
        self.assertTrue(again["returning"])
        self.assertEqual(again["skills"], "产品、路演")
        self.assertEqual(again["name"], "孔祥梨")
        issued = self.issue("13900002222")
        wrong = "000000" if issued != "000000" else "111111"
        rejected = self.client.post("/api/studio/register", json={"phone": "13900002222", "code": wrong, "name": "新", "profile": "做过", "skills": "产品"})
        self.assertEqual(rejected.status_code, 401, rejected.text)
        self.assertNotIn("token", rejected.json())
        missing = self.client.post("/api/studio/register", json={"phone": "13900002222", "code": issued})
        self.assertEqual(missing.status_code, 422, missing.text)
        self.assertEqual(missing.json()["error"]["code"], "profile_required")
        saved = self.client.patch("/api/studio/me", json={"name": "孔祥梨", "profile": "会整理讨论", "skills": "路演、文档"}, headers=self.auth(again["token"]))
        self.assertEqual(saved.status_code, 200, saved.text)
        noted = self.client.post("/api/studio/memory", json={"text": "路演可以独立完成"}, headers=self.auth(again["token"]))
        self.assertEqual(noted.status_code, 200, noted.text)
        self.assertIn("本人记下：路演可以独立完成", noted.json()["growth"])

    def test_full_local_flow_without_external_accounts(self):
        captain = self.enter("13800001111", "孔祥梨", "产品、文档、路演")
        mate = self.enter("13800003333", "胡方耀", "前端、页面")
        ca, ma = self.auth(captain["token"]), self.auth(mate["token"])
        pasted = self.client.post("/api/studio/contests", json={"name": "回响", "deadline": self.deadline, "source_text": "https://example.com/rules"}, headers=ca)
        self.assertEqual(pasted.status_code, 422)
        contest = self.client.post("/api/studio/contests", json={"name": "回响", "deadline": self.deadline, "source_text": SOURCE}, headers=ca)
        self.assertEqual(contest.status_code, 200, contest.text)
        contest = contest.json()
        self.assertIn("GitHub 仓库", contest["submissions"])
        self.assertIn("宣传片", contest["submissions"])
        squad = self.client.post("/api/studio/squads", json={"contest_id": contest["id"], "name": "回响小队"}, headers=ca).json()
        joined = self.client.post("/api/studio/squads/join", json={"code": squad["code"]}, headers=ma)
        self.assertEqual(joined.status_code, 200, joined.text)
        self.assertFalse(joined.json()["friend_of_captain"])
        sid = squad["id"]
        for headers, role, intro in ((ca, "产品", "我负责产品和路演，把规则收成文档。"), (ma, "前端", "我做页面和联调。")):
            saved = self.client.post(f"/api/studio/squads/{sid}/intro", json={"role": role, "intro": intro}, headers=headers)
            self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(self.client.post(f"/api/studio/squads/{sid}/confirm", headers=ma).status_code, 403)
        confirmed = self.client.post(f"/api/studio/squads/{sid}/confirm", headers=ca)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertTrue(confirmed.json()["show_check"])
        self.assertTrue(confirmed.json()["draft"])
        idea = self.client.post(f"/api/studio/squads/{sid}/ideas", json={"body": "做赛内协作助手，截止前演示分工和提交。"}, headers=ma)
        self.assertEqual(idea.status_code, 200, idea.text)
        other = self.client.post(f"/api/studio/squads/{sid}/ideas", json={"body": "做全国排名和主办方系统。"}, headers=ca)
        self.assertEqual(other.status_code, 200, other.text)
        state = self.client.get(f"/api/studio/squads/{sid}", headers=ca).json()
        self.assertEqual(state["contest"]["submissions"], contest["submissions"])
        self.assertGreaterEqual(state["ideas"]["top"][0]["score"], state["ideas"]["top"][-1]["score"])
        self.assertLessEqual(len(state["ideas"]["top"]), 3)
        self.assertEqual(self.client.post(f"/api/studio/squads/{sid}/topic", json={"idea_id": idea.json()["id"]}, headers=ma).status_code, 403)
        topic = self.client.post(f"/api/studio/squads/{sid}/topic", json={"idea_id": idea.json()["id"]}, headers=ca)
        self.assertEqual(topic.status_code, 200, topic.text)
        skill_a = self.client.get(f"/api/studio/squads/{sid}/skill", headers=ca).text
        skill_b = self.client.get(f"/api/studio/squads/{sid}/skill", headers=ma).text
        self.assertEqual(skill_a, skill_b)
        self.assertIn(topic.json()["topic"], skill_a)
        self.assertEqual(self.client.post(f"/api/studio/squads/{sid}/skill/install", json={"tool": "codex"}, headers=ca).status_code, 200)
        self.assertEqual(self.client.post(f"/api/studio/squads/{sid}/skill/install", json={"tool": "workbuddy"}, headers=ma).status_code, 200)
        topic_before = self.client.get(f"/api/studio/squads/{sid}", headers=ca).json()["squad"]["topic"]
        note = self.client.post(f"/api/studio/squads/{sid}/library", json={"body": "海报可以后做"}, headers=ma)
        self.assertEqual(note.status_code, 200, note.text)
        self.assertIsNone(note.json()["vote"])
        strategic = self.client.post(f"/api/studio/squads/{sid}/library", json={"body": "我们要改主干，必须任务加上登录"}, headers=ma)
        self.assertEqual(strategic.status_code, 200, strategic.text)
        self.assertEqual(strategic.json()["vote"]["kind"], "trunk")
        self.assertFalse(strategic.json()["vote"]["applied"])
        mid = self.client.get(f"/api/studio/squads/{sid}", headers=ca).json()
        self.assertEqual(mid["squad"]["topic"], topic_before)
        self.assertEqual(mid["squad"]["trunk"], topic.json()["trunk"])
        self.assertEqual(mid["tasks"], [])
        vote_id = strategic.json()["vote"]["id"]
        for headers in (ca, ma):
            cast = self.client.post(f"/api/studio/votes/{vote_id}/ballots", json={"choice": "yes"}, headers=headers)
            self.assertEqual(cast.status_code, 200, cast.text)
            self.assertFalse(cast.json()["applied"])
        after_vote = self.client.get(f"/api/studio/squads/{sid}", headers=ca).json()
        self.assertEqual(after_vote["squad"]["topic"], topic_before)
        self.assertEqual(after_vote["tasks"], [])
        self.assertEqual(after_vote["votes"][0]["status"], "recorded")
        self.assertEqual(self.client.post(f"/api/studio/squads/{sid}/tasks", json={"title": "页面", "owner_id": mate["user_id"], "priority": "must", "due_at": self.deadline}, headers=ma).status_code, 403)
        published = self.client.post(f"/api/studio/squads/{sid}/tasks", json={"title": "可演示页面", "owner_id": mate["user_id"], "priority": "must", "due_at": self.deadline, "talk_to": "孔祥梨", "alone": False}, headers=ca)
        self.assertEqual(published.status_code, 200, published.text)
        self.assertFalse(published.json()["waited_for_vote"])
        task_id = published.json()["id"]
        adjusted = self.client.patch(f"/api/studio/squads/{sid}/tasks/{task_id}", json={"priority": "should"}, headers=ca)
        self.assertEqual(adjusted.status_code, 200, adjusted.text)
        self.client.patch(f"/api/studio/squads/{sid}/tasks/{task_id}", json={"priority": "must"}, headers=ca)
        progressed = self.client.post(f"/api/studio/squads/{sid}/tasks/{task_id}/progress", json={"progress": 100, "doing": "正在写页面"}, headers=ma)
        self.assertEqual(progressed.status_code, 200, progressed.text)
        shelf = self.client.post(f"/api/studio/squads/{sid}/shelf", json={"kind": "link", "title": "演示", "body": "https://demo.example/hui"}, headers=ma)
        self.assertEqual(shelf.json()["stored"], "shelf")
        repo = self.client.post(f"/api/studio/squads/{sid}/repo", headers=ca)
        self.assertEqual(repo.status_code, 200, repo.text)
        self.assertFalse(repo.json()["remote"])
        self.assertTrue(repo.json()["url"].startswith("local://"))
        renamed = self.client.patch(f"/api/studio/squads/{sid}", json={"name": "回响小队"}, headers=ca)
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(self.client.patch(f"/api/studio/squads/{sid}", json={"name": "别人改的"}, headers=ma).status_code, 403)
        ppt = self.client.post(f"/api/studio/squads/{sid}/shelf", json={"kind": "ppt", "title": "路演要点", "body": "六页：题目、分工、演示。", "editors": []}, headers=ma)
        self.assertEqual(ppt.json()["stored"], "shelf")
        self.assertEqual(self.client.patch(f"/api/studio/squads/{sid}/shelf/{ppt.json()['id']}", json={"body": "队长不能改未授权的稿。"}, headers=ca).status_code, 403)
        self.assertEqual(self.client.patch(f"/api/studio/squads/{sid}/shelf/{ppt.json()['id']}", json={"body": "六页，版式我来改。"}, headers=ma).status_code, 200)
        shared = self.client.post(f"/api/studio/squads/{sid}/shelf", json={"kind": "ppt", "title": "共同路演", "body": "初稿", "editors": [captain["user_id"]]}, headers=ma)
        self.assertEqual(self.client.patch(f"/api/studio/squads/{sid}/shelf/{shared.json()['id']}", json={"body": "去掉PPT"}, headers=ca).status_code, 409)
        self.assertEqual(self.client.patch(f"/api/studio/squads/{sid}/shelf/{shared.json()['id']}", json={"body": "队长改了共同稿的版式。"}, headers=ca).status_code, 200)
        chart = self.client.post(f"/api/studio/squads/{sid}/flow", json={"request": "讨论，确认题目，安装技能，发布任务"}, headers=ca)
        self.assertIn("→", chart.json()["chart"])
        direction = self.client.post(f"/api/studio/squads/{sid}/direction", json={"message": "我们在做什么"}, headers=ma)
        self.assertIn(topic.json()["topic"], direction.json()["reply"])
        finished = self.client.post(f"/api/studio/squads/{sid}/finish", headers=ca)
        self.assertEqual(finished.status_code, 200, finished.text)
        returned = self.enter("13800003333", "胡方耀", "不该覆盖")
        self.assertTrue(returned["returning"])
        self.assertIn("前端", returned["skills"])
        self.assertIn("这场角色是前端", returned["growth"])
        log = self.client.get(f"/api/studio/squads/{sid}", headers=ca).json()["log"]
        self.assertTrue(any("发起表决" in item["detail"] for item in log))
        self.assertTrue(any("不等表决" in item["detail"] for item in log))
        home = self.client.get("/api/studio/me", headers=ca).json()
        self.assertEqual(home["contests"][0]["submissions"], contest["submissions"])

    def test_wechat_stays_closed_without_the_account_holders_app(self):
        status = self.client.get("/api/studio/connect")
        self.assertEqual(status.status_code, 200, status.text)
        body = status.json()
        self.assertFalse(body["wechat"]["ready"])
        self.assertIn("扫码", "".join(body["wechat"]["missing"]))
        self.assertNotIn("APP_SECRET", status.text)
        start = self.client.get("/api/studio/wechat/start")
        self.assertEqual(start.status_code, 409, start.text)
        self.assertNotIn("token", start.text)
        denied = self.client.post("/api/studio/wechat/finish", json={"ticket": "nope", "name": "甲", "profile": "做过产品和演示", "skills": "路演"})
        self.assertEqual(denied.status_code, 401, denied.text)
        self.assertNotIn("token", denied.json())
        self.assertFalse(body["sms"]["ready"])
        self.assertIn("dypns.console.aliyun.com", body["sms"]["notice"])

    def test_sent_code_is_not_returned(self):
        with patch.dict(os.environ, {"SONGBAI_IMESSAGE": "1"}):
            with patch("app.sms.send_phone_code", return_value=(True, "sms")) as mocked:
                with patch("app.studio.secrets.randbelow", return_value=123456):
                    result = self.client.post("/api/studio/codes", json={"phone": "13800004444"})
        self.assertEqual(result.status_code, 200, result.text)
        body = result.json()
        self.assertTrue(body["sent"])
        self.assertNotIn("code", body)
        self.assertNotIn("123456", result.text)
        mocked.assert_called_once_with("13800004444", "123456")
        entered = self.client.post("/api/studio/register", json={"phone": "13800004444", "code": "123456", "name": "甲", "profile": "做过产品和演示", "skills": "产品"})
        self.assertIn(entered.status_code, (200, 201), entered.text)
        self.assertIn("token", entered.json())

    def test_failed_sms_does_not_show_the_code(self):
        with patch.dict(os.environ, {"SONGBAI_IMESSAGE": "1"}):
            with patch("app.sms.send_phone_code", return_value=(False, "信息没有把这条发出去")):
                with patch("app.studio.secrets.randbelow", return_value=654321):
                    result = self.client.post("/api/studio/codes", json={"phone": "13800005555"})
        self.assertEqual(result.status_code, 503, result.text)
        self.assertNotIn("654321", result.text)
        self.assertNotIn("token", result.json())

    def test_personal_pnvs_code_is_not_returned(self):
        env = {"ALIYUN_ACCESS_KEY_ID": "id", "ALIYUN_ACCESS_KEY_SECRET": "secret",
               "ALIYUN_SMS_SIGN_NAME": "恒创联众", "ALIYUN_SMS_TEMPLATE_CODE": "100001", "ALIYUN_SMS_MODE": ""}
        with patch.dict(os.environ, env, clear=False):
            with patch("app.sms.send_pnvs_code", return_value=(True, "aliyun-pnvs")) as mocked:
                with patch("app.studio.secrets.randbelow", return_value=112233):
                    result = self.client.post("/api/studio/codes", json={"phone": "13800006666"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()["sent"])
        self.assertNotIn("code", result.json())
        self.assertNotIn("112233", result.text)
        mocked.assert_called_once_with("13800006666", "112233")
        entered = self.client.post("/api/studio/register", json={"phone": "13800006666", "code": "112233", "name": "乙", "profile": "做过产品和演示", "skills": "产品"})
        self.assertIn(entered.status_code, (200, 201), entered.text)

    def test_enterprise_sms_still_uses_dysms(self):
        env = {"ALIYUN_ACCESS_KEY_ID": "id", "ALIYUN_ACCESS_KEY_SECRET": "secret",
               "ALIYUN_SMS_SIGN_NAME": "松伴", "ALIYUN_SMS_TEMPLATE_CODE": "SMS_TEST", "ALIYUN_SMS_MODE": "enterprise"}
        with patch.dict(os.environ, env, clear=False):
            with patch("app.sms.send_aliyun_code", return_value=(True, "aliyun")) as mocked:
                with patch("app.sms.send_pnvs_code") as unused:
                    with patch("app.studio.secrets.randbelow", return_value=445566):
                        result = self.client.post("/api/studio/codes", json={"phone": "13800008888"})
        self.assertEqual(result.status_code, 200, result.text)
        mocked.assert_called_once_with("13800008888", "445566")
        unused.assert_not_called()

    def test_missing_cloud_sms_does_not_show_the_code_when_required(self):
        with patch.dict(os.environ, {"SONGBAI_REQUIRE_SMS": "1"}):
            with patch("app.studio.secrets.randbelow", return_value=998877):
                result = self.client.post("/api/studio/codes", json={"phone": "13800007777"})
        self.assertEqual(result.status_code, 503, result.text)
        self.assertNotIn("998877", result.text)
        self.assertIn("dypns.console.aliyun.com", result.text)

    def test_homepage_is_the_team_flow(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("/static/studio.js?v=", page.text)
        self.assertEqual(self.client.get("/static/studio.js").status_code, 200)
        self.assertEqual(self.client.get("/classic").status_code, 200)
        self.assertIn("不能自验", self.client.get("/workflow").text)

    def test_contest_file_import_and_confirm(self):
        captain = self.enter("13800004444", "导入员", "产品")
        headers = self.auth(captain["token"])
        bad = self.client.post(
            "/api/studio/contests/import-file",
            files={"file": ("rules.pdf", b"%PDF-1.4", "application/pdf")},
            headers=headers,
        )
        self.assertEqual(bad.status_code, 422)
        good = self.client.post(
            "/api/studio/contests/import-file",
            files={"file": ("rules.md", SOURCE.encode("utf-8"), "text/markdown")},
            headers=headers,
        )
        self.assertEqual(good.status_code, 200, good.text)
        self.assertIn("GitHub", good.json()["source_text"])
        fake_draft = {
            "name": "回响黑客松",
            "deadline": self.deadline,
            "source_text": SOURCE,
            "memory": SOURCE,
            "facts": {
                "time": "本周末",
                "location": "上海",
                "participants": "待补充",
                "tracks": "待补充",
                "selection": "待补充",
                "prizes": "待补充",
                "submissions_text": "PPT 与 GitHub 仓库",
                "other": "待补充",
            },
            "sources": [],
            "label": "比赛资料",
            "notice": "已搜到：提交要求。待补充：时间、地点。",
            "fact_lines": [],
            "submissions_preview": [],
        }
        with patch("app.studio.research_contest", return_value=fake_draft):
            confirmed = self.client.post(
                "/api/studio/contests/confirm",
                json={"name": "回响", "file_text": SOURCE},
                headers=headers,
            )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        body = confirmed.json()
        self.assertEqual(body["name"], "回响黑客松")
        self.assertIn("PPT", body["facts"]["submissions_text"])
        self.assertTrue(body["fact_lines"])
        asked = self.client.post(
            f"/api/studio/contests/{body['id']}/ask",
            json={"question": "提交什么"},
            headers=headers,
        )
        self.assertEqual(asked.status_code, 200, asked.text)
        self.assertIn("reply", asked.json())
        blocked = self.client.post(
            "/api/studio/contests/confirm",
            json={"name": "x", "url": "http://127.0.0.1/secret"},
            headers=headers,
        )
        self.assertEqual(blocked.status_code, 422)


if __name__ == "__main__":
    unittest.main(verbosity=2)
