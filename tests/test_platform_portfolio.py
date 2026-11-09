"""Portfolio domain verification: real auth, synthetic SQLite, no network/model."""
import copy
import json
import unittest

from app.learning_v2.protocol import Problem
from app.platform_v1.portfolio import PortfolioService
from app.platform_v1.schemas import RESPONSE_SCHEMAS, validate_request
from app.platform_v1 import PlatformService, PlatformSettings, register_platform

try:
    from .test_learning_v2_course import CourseFixture
    from .test_learning_v2_identity import BASE
except ImportError:
    from test_learning_v2_course import CourseFixture
    from test_learning_v2_identity import BASE


class PortfolioTests(CourseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.portfolio = PortfolioService(self.service)
        self.portfolio.migrate()
        self.parent_mode()
        profile = self.get(f"/learners/{self.lid}/profile")
        self.post(f"/learners/{self.lid}/consents", dict(expected_revision=profile["revision"],
                  consent_version="fiction-v1", scopes=["learning", "parent_summary"], acknowledged=True), 201)
        self.enter(self.a, self.lid)

    def parent_mode(self):
        self.login(self.a, "parent-a")

    def call(self, op, body=None, *, client=None, lid=None, **params):
        client = client or self.a
        request = self.request_for(client)
        with self.service.store.transaction() as con:
            browser = self.service.browser(con, request)
            session = self.service.session_row(con, request, browser)
            params = {"learner_id": lid or self.lid, **params}
            if body is None:
                result = self.portfolio.read(con, op, session, params, {})
            else:
                result = self.portfolio.write(con, op, session, params, {"request_id": self.rid(), **body})
            RESPONSE_SCHEMAS[op].model_validate(result)
            return result

    @staticmethod
    def external(**overrides):
        return dict(title="校园节水小助手", summary="把教室的节水建议整理成一个可以点击查看的网页。",
                    url="https://example.test/fictional-water-project", tool_name="虚构网页工具",
                    contribution="我设计页面结构，修改按钮文案，并检查手机上的显示。",
                    ai_assistance="assisted", **overrides)

    def competition(self):
        with self.service.store.transaction() as con:
            con.execute("CREATE TABLE squads(id TEXT PRIMARY KEY,name TEXT NOT NULL)")
            con.execute("CREATE TABLE squad_members(squad_id TEXT,user_id TEXT,PRIMARY KEY(squad_id,user_id))")
            con.execute("CREATE TABLE core_settings(squad_id TEXT PRIMARY KEY,revision INTEGER,plan_version INTEGER,active_plan TEXT)")
            con.execute("CREATE TABLE core_reports(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE,squad_id TEXT,user_id TEXT,body TEXT)")
            con.execute("CREATE TABLE core_task_claims(squad_id TEXT,plan_version INTEGER,task_key TEXT,user_id TEXT)")
            con.execute("INSERT INTO squads VALUES('fiction-project','虚构校园创新队')")
            for actor in ("parent-a", "parent-b"):
                con.execute("INSERT INTO squad_members VALUES('fiction-project',?)", (actor,))
            tasks = [{"key": "design", "title": "交互原型", "description": "做出按钮切换的演示", "owner_id": "parent-a"},
                     {"key": "private", "title": "其他队员任务", "owner_id": "parent-b"},
                     {"key": "claimed", "title": "已领取讲解任务", "claim_required": True, "owner_id": "parent-b"}]
            con.execute("INSERT INTO core_settings VALUES('fiction-project',1,1,?)", (json.dumps({"tasks": tasks}),))
            con.execute("INSERT INTO core_task_claims VALUES('fiction-project',1,'claimed','parent-a')")
            own = {"summary": "我做出了可切换的节水建议页面。", "evidence": ["https://example.test/prototype"],
                   "assistant_message": "private-full-model-reply", "user_message": "private-user-chat",
                   "views": [{"topic": "not-for-portfolio"}]}
            other = {"summary": "other-member-private-progress", "evidence": []}
            con.execute("INSERT INTO core_reports(id,squad_id,user_id,body) VALUES('report-own','fiction-project','parent-a',?)", (json.dumps(own),))
            con.execute("INSERT INTO core_reports(id,squad_id,user_id,body) VALUES('report-other','fiction-project','parent-b',?)", (json.dumps(other),))

    def proposal(self):
        self.parent_mode()
        return self.call("createCompetitionLink", dict(project_id="fiction-project", expected_source_revision=1,
                         selected_refs=["report:report-own", "task:1:design"], title="校园节水小助手",
                         summary="在团队比赛中完成的一个交互原型。", contribution="孩子负责交互设计与按钮演示；这是家长声明，等待孩子核对。"))

    def accept(self, link):
        self.enter(self.a, self.lid)
        return self.call("decideCompetitionLink", dict(expected_revision=link["revision"], decision="accept"), link_id=link["id"])

    def install_platform(self):
        register_platform(self.app, PlatformService(self.service, PlatformSettings(enabled=True)))

    def platform_post(self, path, body, expected=200):
        csrf = self.bootstrap(self.a)["csrf_token"]
        response = self.a.post("/api/platform/v1/learners/" + self.lid + path, json=body,
                               headers={"Origin": "https://learning.example.test", "X-CSRF-Token": csrf})
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    def test_external_versions_are_immutable_and_private(self):
        first = self.call("createExternalWork", self.external())
        second_body = self.external()
        second_body.update(title="校园节水小助手第二版", url="https://example.test/fictional-v2", expected_revision=1)
        second = self.call("versionExternalWork", second_body, work_id=first["id"])
        self.assertEqual(second["revision"], 2)
        self.assertEqual(len(second["versions"]), 2)
        self.assertEqual(second["versions"][0]["actual_outputs"], first["actual_outputs"])
        self.assertEqual(second["actual_outputs"][0]["url"], second_body["url"])
        self.assertEqual(second["visibility"], "private")
        self.assertIsNone(second["cover_asset_id"])
        self.assertNotIn("publish", second["available_actions"])
        self.assertEqual(self.call("works")["items"][0]["id"], first["id"])

    def test_conflicting_revision_rolls_back_without_new_version(self):
        first = self.call("createExternalWork", self.external())
        stale = self.external(); stale["expected_revision"] = 77
        with self.assertRaises(Problem) as error:
            self.call("versionExternalWork", stale, work_id=first["id"])
        self.assertEqual(error.exception.code, "revision_conflict")
        self.assertEqual(len(self.call("work", work_id=first["id"])["versions"]), 1)

    def test_extra_publication_owner_and_missing_authorship_fields_are_rejected(self):
        for extra in ({"visibility": "public"}, {"actor_id": "parent-b"}, {"cover_asset_id": "unowned-image"}):
            with self.subTest(extra=extra), self.assertRaises(Problem):
                validate_request("createExternalWork", {"request_id": self.rid(), **self.external(), **extra})
        body = self.external(); body.pop("ai_assistance")
        with self.assertRaises(Problem):
            self.call("createExternalWork", body)

    def test_link_validation_never_fetches_and_rejects_active_schemes_credentials_controls(self):
        for url in ("javascript:alert(1)", "https://person:password@example.test/demo", "//example.test/demo", "https://example.test/\nattack", "https://example.test\\demo"):
            body = self.external(); body["url"] = url
            with self.subTest(url=url), self.assertRaises(Problem):
                self.call("createExternalWork", body)
        body = self.external(); body["url"] = "http://127.0.0.1:8999/local-work"
        self.assertEqual(self.call("createExternalWork", body)["actual_outputs"][0]["url"], body["url"])

    def test_cross_family_reads_and_writes_fail_closed(self):
        work = self.call("createExternalWork", self.external())
        other_lid, _ = self.create(self.b, "parent-b")
        self.enter(self.b, other_lid)
        for op, body, params in (("work", None, {"work_id": work["id"]}), ("works", None, {}),
                                 ("versionExternalWork", {**self.external(), "expected_revision": 1}, {"work_id": work["id"]})):
            with self.subTest(op=op), self.assertRaises(Problem) as error:
                self.call(op, body, client=self.b, **params)
            self.assertEqual(error.exception.status, 404)
        with self.assertRaises(Problem):
            self.call("work", client=self.b, lid=other_lid, work_id=work["id"])

    def test_manager_can_read_summary_but_cannot_save_as_child(self):
        work = self.call("createExternalWork", self.external())
        self.parent_mode()
        read = self.call("work", work_id=work["id"])
        self.assertEqual(read["available_actions"], [])
        with self.assertRaises(Problem):
            self.call("createExternalWork", self.external())
        with self.service.store.transaction() as con:
            con.execute("UPDATE learn_consents SET scopes='[\"learning\"]' WHERE learner_id=?", (self.lid,))
        with self.assertRaises(Problem) as error:
            self.call("works")
        self.assertEqual(error.exception.code, "consent_required")

    def test_learner_writes_do_not_silently_grant_parent_summary(self):
        with self.service.store.transaction() as con:
            con.execute("UPDATE learn_consents SET scopes='[\"learning\"]' WHERE learner_id=?", (self.lid,))
        work = self.call("createExternalWork", self.external())
        self.assertEqual(len(self.call("works")["items"]), 1)
        self.parent_mode()
        with self.assertRaises(Problem):
            self.call("work", work_id=work["id"])
        with self.service.store.transaction() as con:
            self.assertEqual(json.loads(con.execute("SELECT scopes FROM learn_consents WHERE learner_id=?", (self.lid,)).fetchone()[0]), ["learning"])

    def test_learning_projection_reuses_actual_saved_version_and_entitlement(self):
        self.advance_two()
        work = self.call("work", work_id="learning_" + self.art["id"])
        self.assertEqual(work["current_version"]["id"], self.art["current_version"]["id"])
        self.assertEqual(work["source_ref"]["id"], self.art["id"])
        self.assertEqual(work["provenance"]["ai_assistance"], "generated")
        self.assertIn(self.content["title"], work["actual_outputs"][0]["text"])
        with self.service.store.transaction() as con:
            con.execute("UPDATE learn_course_grants SET revoked=1 WHERE id=?", (self.eid,))
        self.assertEqual(self.call("works")["items"], [])
        with self.assertRaises(Problem):
            self.call("work", work_id=work["id"])

    def test_three_sources_aggregate_without_altering_course_or_team_state(self):
        self.advance_two()
        original_progress = copy.deepcopy(self.fresh()["progress"])
        external = self.call("createExternalWork", self.external())
        self.competition()
        accepted = self.accept(self.proposal())
        self.assertEqual(accepted["state"], "accepted")
        items = self.call("works")["items"]
        self.assertEqual({item["origin"] for item in items}, {"learning", "external", "competition"})
        self.assertEqual(next(item for item in items if item["origin"] == "external")["id"], external["id"])
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute("SELECT revision FROM core_settings").fetchone()[0], 1)
        self.assertEqual(self.fresh()["progress"], original_progress)

    def test_parent_proposal_only_selects_own_sources_and_child_must_confirm(self):
        self.competition(); self.parent_mode()
        sources = self.call("competitionSources")["items"][0]
        refs = {row["ref"] for row in sources["available_refs"]}
        self.assertIn("task:1:claimed", refs)
        self.assertNotIn("report:report-other", refs)
        self.assertNotIn("task:1:private", refs)
        encoded = json.dumps(sources)
        for private in ("private-full-model-reply", "private-user-chat", "not-for-portfolio", "other-member-private-progress"):
            self.assertNotIn(private, encoded)
        link = self.proposal()
        self.assertEqual(link["state"], "offered")
        self.assertEqual(self.call("works")["items"], [])
        with self.assertRaises(Problem):
            self.call("decideCompetitionLink", dict(expected_revision=1, decision="accept"), link_id=link["id"])
        accepted = self.accept(link)
        work = self.call("work", work_id="competition_" + accepted["id"])
        self.assertEqual(work["provenance"]["kind"], "guardian_statement_learner_confirmed")
        self.assertEqual(work["contribution"], link["contribution"])
        self.assertTrue(any(output["kind"] == "external_link" for output in work["actual_outputs"]))

    def test_other_member_report_cannot_be_injected_into_proposal(self):
        self.competition(); self.parent_mode()
        with self.assertRaises(Problem) as error:
            self.call("createCompetitionLink", dict(project_id="fiction-project", expected_source_revision=1,
                      selected_refs=["report:report-other"], title="冒用来源", summary="错误测试", contribution="不是本人的记录"))
        self.assertEqual(error.exception.code, "source_changed")

    def test_changed_proposal_requires_decline_and_new_preview_not_silent_refresh(self):
        self.competition()
        link = self.proposal()
        with self.service.store.transaction() as con:
            con.execute("UPDATE core_settings SET revision=2")
        self.enter(self.a, self.lid)
        with self.assertRaises(Problem) as error:
            self.call("decideCompetitionLink", dict(expected_revision=1, decision="accept"), link_id=link["id"])
        self.assertEqual(error.exception.code, "source_changed")
        declined = self.call("decideCompetitionLink", dict(expected_revision=1, decision="decline"), link_id=link["id"])
        self.assertEqual(declined["state"], "declined")
        self.parent_mode()
        renewed = self.call("createCompetitionLink", dict(project_id="fiction-project", expected_source_revision=2,
                            selected_refs=["report:report-own"], title="新版项目资料", summary="重新核对后的资料", contribution="孩子负责界面"))
        self.assertEqual(renewed["id"], link["id"])
        self.assertGreater(renewed["revision"], declined["revision"])
        self.assertEqual(self.accept(renewed)["state"], "accepted")

    def test_selected_content_change_without_revision_still_blocks_accept(self):
        self.competition(); link = self.proposal()
        with self.service.store.transaction() as con:
            con.execute("UPDATE core_reports SET body=? WHERE id='report-own'", (json.dumps({"summary": "已修改", "evidence": []}),))
        self.enter(self.a, self.lid)
        with self.assertRaises(Problem) as error:
            self.call("decideCompetitionLink", dict(expected_revision=1, decision="accept"), link_id=link["id"])
        self.assertEqual(error.exception.code, "source_changed")

    def test_accept_revoke_and_membership_removal_immediately_stop_projection(self):
        self.competition(); link = self.accept(self.proposal())
        wid = "competition_" + link["id"]
        revoked = self.call("decideCompetitionLink", dict(expected_revision=link["revision"], decision="revoke"), link_id=link["id"])
        self.assertEqual(revoked["state"], "revoked")
        with self.assertRaises(Problem):
            self.call("work", work_id=wid)
        self.assertEqual(self.call("works")["items"], [])
        link = self.accept(self.proposal())
        with self.service.store.transaction() as con:
            con.execute("DELETE FROM squad_members WHERE user_id='parent-a'")
        self.assertEqual(self.call("works")["items"], [])
        self.assertEqual(self.call("competitionLinks")["items"], [])
        with self.assertRaises(Problem):
            self.call("work", work_id="competition_" + link["id"])

    def test_consent_relationship_and_removed_report_are_rechecked(self):
        self.competition(); link = self.accept(self.proposal())
        with self.service.store.transaction() as con:
            con.execute("DELETE FROM core_reports WHERE id='report-own'")
        self.assertEqual(self.call("works")["items"], [])
        self.call("createExternalWork", self.external())
        with self.service.store.transaction() as con:
            con.execute("UPDATE learn_links SET status='revoked' WHERE learner_id=?", (self.lid,))
        with self.assertRaises(Problem) as error:
            self.call("works")
        self.assertEqual(error.exception.code, "consent_required")

    def test_no_source_tables_is_empty_not_fake_demo_data(self):
        self.parent_mode()
        self.assertEqual(self.call("competitionSources"), {"items": []})
        self.assertEqual(self.call("works")["items"], [])

    def test_migration_is_additive_idempotent_and_checks_own_checksum(self):
        with self.service.store.transaction() as con:
            before = [tuple(row) for row in con.execute("SELECT * FROM learn_migrations ORDER BY version")]
        self.portfolio.migrate()
        with self.service.store.transaction() as con:
            self.assertEqual(before, [tuple(row) for row in con.execute("SELECT * FROM learn_migrations ORDER BY version")])
            con.execute("UPDATE platform_migrations SET checksum='wrong' WHERE version='P01-portfolio'")
        with self.assertRaises(ValueError):
            self.portfolio.migrate()

    def test_http_replay_reads_current_external_version_and_does_not_repeat_write(self):
        self.install_platform()
        body = {"request_id": self.rid(), **self.external()}
        first = self.platform_post("/external-works", body, 201)
        changed = self.external(); changed.update(title="已改进的第二版", expected_revision=1)
        second = self.call("versionExternalWork", changed, work_id=first["id"])
        replay = self.platform_post("/external-works", body, 201)
        self.assertEqual(replay["revision"], 2)
        self.assertEqual(replay["title"], second["title"])
        self.assertEqual(len(replay["versions"]), 2)
        body["title"] = "同号不同内容"
        self.assertEqual(self.platform_post("/external-works", body, 409)["error"]["code"], "idempotency_conflict")

    def test_http_old_accept_replay_returns_revoked_without_resurrecting_data(self):
        self.competition(); self.install_platform()
        link = self.proposal()
        self.enter(self.a, self.lid)
        path = "/competition-source-links/" + link["id"] + "/decision"
        accept_body = {"request_id": self.rid(), "expected_revision": 1, "decision": "accept"}
        accepted = self.platform_post(path, accept_body)
        self.platform_post(path, {"request_id": self.rid(), "expected_revision": accepted["revision"], "decision": "revoke"})
        replay = self.platform_post(path, accept_body)
        self.assertEqual(replay["state"], "revoked")
        self.assertEqual(self.call("works")["items"], [])
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM platform_competition_link_history").fetchone()[0], 3)

    def test_http_source_permission_is_checked_before_cached_proposal_response(self):
        self.competition(); self.install_platform(); self.parent_mode()
        body = dict(request_id=self.rid(), project_id="fiction-project", expected_source_revision=1,
                    selected_refs=["report:report-own"], title="项目资料", summary="选中的真实自报资料", contribution="待孩子核对")
        self.platform_post("/competition-source-links", body, 201)
        with self.service.store.transaction() as con:
            con.execute("DELETE FROM squad_members WHERE user_id='parent-a'")
        result = self.platform_post("/competition-source-links", body, 403)
        self.assertEqual(result["error"]["code"], "source_account_mismatch")
        self.assertNotIn("sources", result)


if __name__ == "__main__":
    unittest.main()
