"""Images use synthetic auth/SQLite/files and MockTransport only; zero paid calls."""
import base64
from dataclasses import replace
import hashlib
from io import BytesIO
import json
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

from app.learning_v2.course import COURSE
from app.learning_v2.protocol import Problem
from app.platform_v1 import PlatformService, PlatformSettings, register_platform
from app.platform_v1.doubao import DoubaoAdapter, ImageResult, ProviderUnknown, ENDPOINT
from app.platform_v1.images import (ImageService, ImageSettings, REQUEST_SCHEMAS,
                                    RESPONSE_SCHEMAS, ROUTE_SPECS)
from app.platform_v1.portfolio import PortfolioService

try:
    from .test_learning_v2_course import CourseFixture
except ImportError:
    from test_learning_v2_course import CourseFixture


class ImageFixture(CourseFixture):
    def setUp(self):
        super().setUp()
        self.portfolio = PortfolioService(self.service)
        self.portfolio.migrate()
        # This is fictional, test-only approved text, not a production consent.
        text = self.make_text("fiction-images-v1")
        text["scope_purposes"].append({"scope": "live_model", "purpose": "虚构图像处理协议测试；不外发资料，不产生真实费用。"})
        content = {key: text[key] for key in ("locale", "title", "text", "scope_purposes")}
        text["text_sha256"] = hashlib.sha256(json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        self.service.put_consent_text(text, authority="synthetic-test-only")
        self.login(self.a, "parent-a")
        profile = self.get(f"/learners/{self.lid}/profile")
        self.consent = self.post(f"/learners/{self.lid}/consents", dict(expected_revision=profile["revision"],
            consent_version="fiction-images-v1", scopes=["learning", "parent_summary", "live_model"], acknowledged=True), 201)
        self.enter(self.a, self.lid)
        stream = BytesIO(); Image.new("RGB", (24, 16), "#8768ee").save(stream, format="PNG")
        self.png = stream.getvalue()
        self.sample = self.path.parent / "local-fixture.png"
        self.sample.write_bytes(self.png)
        self.calls, self.hook = [], None
        self.cfg = ImageSettings(storage_dir=self.path.parent / "private-images", config_version="offline-images-v1",
            live_enabled=True, api_key="synthetic-provider-credential-not-real", model="synthetic-seedream",
            image_limit=6, image_consent_versions=("fiction-images-v1",), sample_enabled=True,
            sample_path=self.sample, sample_limit=8, transport=httpx.MockTransport(self.respond))
        self.platform_settings = PlatformSettings(enabled=True, demo_mode=True, image_settings=self.cfg)
        self.images = ImageService(self.service.store, self.service, self.portfolio, self.platform_settings)
        self.images.migrate()
        self.images.grant_budget("learner:" + self.lid, 6, grant_key="fiction-image-budget", expires=self.now[0]+86400, authority="synthetic-test-only")
        self.work = self.external()

    def response(self):
        return {"model": "synthetic-seedream", "data": [{"b64_json": base64.b64encode(self.png).decode()}], "usage": {"generated_images": 1}}

    def respond(self, request):
        self.calls.append(json.loads(request.content))
        # A separate DB writer proves no transaction is held across the network.
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute("SELECT state FROM platform_image_jobs ORDER BY rowid DESC LIMIT 1").fetchone()[0], "dispatching")
        if self.hook:
            return self.hook(request)
        return httpx.Response(200, json=self.response(), headers={"x-request-id": "fiction-provider-request"})

    def session(self, con, client=None):
        request = self.request_for(client or self.a)
        return self.service.session_row(con, request, self.service.browser(con, request))

    def external(self, previous=None):
        body = dict(request_id=self.rid(), title="校园天气小助手", summary="我制作的天气展示页面。", url="https://example.test/weather",
                    tool_name="虚构工具", contribution="我设计界面并核对内容。", ai_assistance="assisted")
        params = {"learner_id": self.lid}
        op = "createExternalWork"
        if previous:
            body["expected_revision"] = previous["revision"]
            params["work_id"], op = previous["id"], "versionExternalWork"
        with self.service.store.transaction() as con:
            return self.portfolio.write(con, op, self.session(con), params, body)

    def call(self, op, body=None, *, client=None, **params):
        with self.service.store.transaction() as con:
            session = self.session(con, client)
            value = self.images.read(con, op, session, params, {}) if body is None else self.images.write(
                con, op, session, params, {"request_id": self.rid(), **body})
            RESPONSE_SCHEMAS[op].model_validate(value)
            return value

    def queue(self, mode="live", **overrides):
        body = dict(mode=mode, purpose="work_cover", learner_id=self.lid, target_id=self.work["id"],
                    target_version=self.work["current_version"]["id"], expected_binding_revision=0,
                    slot="cover", prompt="一张展示校园天气小助手的友好封面。")
        body.update(overrides)
        return self.call("createImage", body)

    def account(self):
        with self.service.store.transaction() as con:
            return dict(con.execute("SELECT * FROM platform_image_budgets WHERE subject=?", ("learner:" + self.lid,)).fetchone())

    def bindings(self):
        return self.call("workImages", learner_id=self.lid, work_id=self.work["id"])

    def content(self, asset_id, client=None):
        with self.service.store.transaction() as con:
            return self.images.asset_content(con, self.session(con, client), asset_id)

class ImageTests(ImageFixture, unittest.TestCase):
    def test_live_request_is_queued_gets_never_dispatch_and_success_auto_saves(self):
        job = self.queue()
        self.assertEqual(job["state"], "queued")
        self.assertEqual(self.account()["held"], 1)
        for _ in range(3):
            self.assertEqual(self.call("imageJob", job_id=job["id"])["state"], "queued")
        self.assertEqual(self.calls, [])
        result = self.images.worker_once()
        self.assertEqual(result["state"], "archived")
        self.assertEqual(result["source"], "test_fixture")
        self.assertEqual(self.images.worker_once(), None)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.account()["held"], 0)
        self.assertEqual(self.account()["settled"], 1)
        binding = self.bindings()
        self.assertEqual(binding["cover_asset_id"], result["asset_id"])
        self.assertEqual(binding["items"][0]["binding_revision"], 1)
        self.assertEqual(binding["items"][0]["target_version"], self.work["current_version"]["id"])
        self.assertEqual(self.content(result["asset_id"]), (self.png, "image/png"))
        with self.service.store.transaction() as con:
            original = self.portfolio.read(con, "work", self.session(con), {"learner_id": self.lid, "work_id": self.work["id"]}, {})
        self.assertEqual(original["revision"], self.work["revision"])
        self.assertEqual(original["current_version"], self.work["current_version"])
        self.assertEqual(original["visibility"], "private")

    def test_sample_is_explicit_local_and_does_not_consume_live_budget(self):
        before = self.account()
        result = self.images.execute(self.queue("sample")["id"])
        self.assertEqual(result["state"], "archived")
        self.assertEqual(result["mode"], "sample")
        self.assertEqual(result["source"], "local_sample")
        self.assertIsNone(result["actual_model"])
        self.assertEqual(result["usage"]["status"], "sample")
        self.assertEqual(self.calls, [])
        self.assertEqual(before, self.account())

    def test_sample_disabled_outside_explicit_demo(self):
        self.images = ImageService(self.service.store, self.service, self.portfolio, replace(self.platform_settings, demo_mode=False))
        with self.assertRaises(Problem) as error:
            self.queue("sample")
        self.assertEqual(error.exception.code, "image_unavailable")
        self.assertEqual(self.calls, [])

    def test_missing_credential_or_model_never_dispatches_live(self):
        for cfg in (replace(self.cfg, api_key=""), replace(self.cfg, model=""), replace(self.cfg, live_enabled=False)):
            self.images = ImageService(self.service.store, self.service, self.portfolio, replace(self.platform_settings, image_settings=cfg))
            self.assertFalse(self.images.live_available)
            with self.assertRaises(Problem) as error:
                self.queue()
            self.assertEqual(error.exception.code, "image_unavailable")
        self.assertEqual(self.calls, [])

    def test_live_requires_explicit_image_purpose_consent_version(self):
        self.images = ImageService(self.service.store, self.service, self.portfolio, replace(self.platform_settings,
            image_settings=replace(self.cfg, image_consent_versions=())))
        with self.assertRaises(Problem) as error:
            self.queue()
        self.assertEqual(error.exception.code, "image_consent_required")
        self.assertEqual(self.calls, [])

    def test_no_budget_is_not_implicitly_granted_and_one_unknown_reserves_slot(self):
        with self.service.store.transaction() as con:
            con.execute("DELETE FROM platform_image_budgets")
        with self.assertRaises(Problem) as error:
            self.queue()
        self.assertEqual(error.exception.code, "image_budget_required")
        self.assertEqual(self.calls, [])

    def test_timeout_stays_unknown_keeps_hold_and_never_retries(self):
        def timeout(request):
            raise httpx.ReadTimeout("synthetic-provider-credential-not-real MUST NOT LEAK", request=request)
        self.hook = timeout
        result = self.images.execute(self.queue()["id"])
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(self.account()["held"], 1)
        self.assertEqual(self.account()["settled"], 0)
        for _ in range(3):
            self.images.execute(result["id"])
        self.images.worker_once()
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises(Problem) as error:
            self.queue()
        self.assertEqual(error.exception.code, "image_job_unsettled")
        self.assertNotIn("MUST NOT LEAK", json.dumps(result))
        self.assertFalse(result["can_recover"])

    def test_restarted_dispatched_job_becomes_unknown_without_network(self):
        job = self.queue()
        with self.service.store.transaction() as con:
            con.execute("UPDATE platform_image_jobs SET state='dispatching',lease_until=?,lease_token='old-worker' WHERE id=?", (self.now[0]-1, job["id"]))
        self.assertEqual(self.images.worker_once()["state"], "unknown")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.account()["held"], 1)

    def test_definite_provider_rejection_releases_hold_without_leaking_text(self):
        self.hook = lambda request: httpx.Response(400, json={"error": {"message": "SENSITIVE synthetic-provider-credential-not-real"}})
        result = self.images.execute(self.queue()["id"])
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["usage"]["status"], "released")
        self.assertEqual(self.account()["held"], 0)
        self.assertEqual(self.account()["settled"], 0)
        self.assertNotIn("SENSITIVE", json.dumps(result))

    def test_storage_failure_recovers_durable_image_without_second_generation(self):
        job = self.queue()
        with patch.object(self.images, "_save_file", side_effect=OSError("fictional disk unavailable")):
            failed = self.images.execute(job["id"])
        self.assertEqual(failed["state"], "storage_failed")
        self.assertTrue(failed["can_recover"])
        self.images = ImageService(self.service.store, self.service, self.portfolio, self.platform_settings)
        recovered = self.call("recoverImage", {}, job_id=job["id"])
        self.assertEqual(recovered["state"], "received")
        archived = self.images.worker_once()
        self.assertEqual(archived["state"], "archived")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.content(archived["asset_id"])[0], self.png)
        self.assertEqual(self.account()["settled"], 1)

    def test_recover_does_not_generate_for_queued_unknown_or_archived(self):
        job = self.queue()
        with self.assertRaises(Problem) as error:
            self.call("recoverImage", {}, job_id=job["id"])
        self.assertEqual(error.exception.code, "image_recovery_unavailable")
        self.assertEqual(self.calls, [])

    def test_session_rotated_before_dispatch_cancels_and_releases(self):
        job = self.queue()
        self.login(self.a, "parent-a")
        result = self.images.execute(job["id"])
        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(result["error_code"], "session_revoked")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.account()["held"], 0)

    def test_live_consent_revoked_before_dispatch_cancels(self):
        job = self.queue()
        with self.service.store.transaction() as con:
            con.execute("UPDATE learn_consents SET status='revoked' WHERE id=?", (self.consent["id"],))
        result = self.images.execute(job["id"])
        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(result["error_code"], "image_consent_required")
        self.assertEqual(self.calls, [])

    def test_target_changed_before_dispatch_does_not_generate(self):
        job = self.queue()
        self.external(self.work)
        result = self.images.execute(job["id"])
        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(result["error_code"], "source_changed")
        self.assertEqual(self.calls, [])

    def test_version_change_during_generation_preserves_private_asset_without_wrong_binding(self):
        def change(request):
            self.work = self.external(self.work)
            return httpx.Response(200, json=self.response())
        self.hook = change
        result = self.images.execute(self.queue()["id"])
        self.assertEqual(result["state"], "archive_conflict")
        self.assertEqual(result["error_code"], "source_changed")
        self.assertIsNotNone(result["asset_id"])
        self.assertIsNone(self.bindings()["cover_asset_id"])
        self.assertEqual(self.content(result["asset_id"])[0], self.png)
        self.assertEqual(len(self.calls), 1)

    def test_cross_family_cannot_read_job_asset_or_binding(self):
        result = self.images.execute(self.queue("sample")["id"])
        other_lid, _ = self.create(self.b, "parent-b")
        self.enter(self.b, other_lid)
        for op, params in (("imageJob", {"job_id": result["id"]}), ("imageAsset", {"asset_id": result["asset_id"]}),
                           ("workImages", {"learner_id": self.lid, "work_id": self.work["id"]})):
            with self.subTest(op=op), self.assertRaises(Problem) as error:
                self.call(op, client=self.b, **params)
            self.assertEqual(error.exception.status, 404)
        with self.assertRaises(Problem):
            self.content(result["asset_id"], self.b)

    def test_parent_can_read_authorized_asset_but_cannot_generate_for_child(self):
        result = self.images.execute(self.queue("sample")["id"])
        self.login(self.a, "parent-a")
        self.assertEqual(self.content(result["asset_id"])[0], self.png)
        with self.assertRaises(Problem):
            self.queue("sample")
        with self.service.store.transaction() as con:
            con.execute("UPDATE learn_consents SET status='revoked' WHERE id=?", (self.consent["id"],))
        with self.assertRaises(Problem):
            self.content(result["asset_id"])

    def test_course_cover_needs_explicit_editor_allowlist_not_child_actor_match(self):
        self.images = ImageService(self.service.store, self.service, self.portfolio, replace(self.platform_settings,
            image_settings=replace(self.cfg, content_editors=("parent-a",))))
        body = dict(mode="sample", purpose="course_cover", learner_id=None, target_id=COURSE, target_version="1",
                    expected_binding_revision=0, slot="cover", prompt="课程的示例封面")
        with self.assertRaises(Problem):
            self.call("createImage", body)
        self.login(self.a, "parent-a")
        result = self.images.execute(self.call("createImage", body)["id"])
        self.assertEqual(result["state"], "archived")
        self.assertEqual(self.call("courseImages", course_id=COURSE)["cover_asset_id"], result["asset_id"])
        self.enter(self.a, self.lid)
        with self.assertRaises(Problem):
            self.content(result["asset_id"])

    def test_illustration_slot_and_cover_have_independent_bindings(self):
        cover = self.images.execute(self.queue("sample")["id"])
        illustration = self.images.execute(self.queue("sample", purpose="illustration", slot="story-scene-1")["id"])
        self.assertEqual(cover["state"], "archived")
        self.assertEqual(illustration["state"], "archived")
        bindings = self.bindings()
        self.assertEqual(len(bindings["items"]), 2)
        self.assertEqual(bindings["cover_asset_id"], cover["asset_id"])

    def test_budget_hold_is_atomic_and_sample_limit_is_separate(self):
        with self.service.store.transaction() as con:
            con.execute("UPDATE platform_image_budgets SET granted=1")
        self.queue()
        with self.assertRaises(Problem) as error:
            self.queue(purpose="illustration", slot="other-position")
        self.assertEqual(error.exception.code, "image_budget_required")
        sample = self.queue("sample", purpose="illustration", slot="sample-position")
        self.assertEqual(sample["usage"]["status"], "sample")
        self.assertEqual(self.account()["held"], 1)

    def test_configuration_change_cancels_queued_job_not_retrying_provider(self):
        job = self.queue()
        changed = replace(self.cfg, config_version="new-profile")
        other = ImageService(self.service.store, self.service, self.portfolio, replace(self.platform_settings, image_settings=changed))
        result = other.execute(job["id"])
        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(self.account()["held"], 0)
        self.assertEqual(self.calls, [])

    def test_corrupt_asset_and_storage_key_escape_do_not_expose_files_or_generate(self):
        result = self.images.execute(self.queue("sample")["id"])
        with self.service.store.transaction() as con:
            con.execute("UPDATE platform_image_assets SET storage_key='../other-private-file' WHERE id=?", (result["asset_id"],))
        with self.assertRaises(Problem) as error:
            self.content(result["asset_id"])
        self.assertEqual(error.exception.code, "storage_unavailable")
        self.assertEqual(self.calls, [])

    def test_private_storage_cannot_be_mounted_static_directory(self):
        from pathlib import Path
        public = Path(__file__).resolve().parents[1] / "static" / "unsafe-image-output"
        with self.assertRaises(ValueError):
            replace(self.cfg, storage_dir=public)

    def test_adapter_payload_matches_single_image_ark_contract_without_client_provider_fields(self):
        result = self.images.execute(self.queue()["id"])
        self.assertEqual(result["state"], "archived")
        self.assertEqual(self.calls[0]["model"], "synthetic-seedream")
        self.assertEqual(self.calls[0]["response_format"], "b64_json")
        self.assertFalse(self.calls[0]["stream"])
        self.assertTrue(self.calls[0]["watermark"])
        self.assertEqual(self.calls[0]["sequential_image_generation"], "disabled")
        self.assertNotIn("url", self.calls[0])
        self.assertNotIn("synthetic-provider-credential-not-real", repr(self.cfg))

    def test_adapter_new_model_can_explicitly_omit_unsupported_sequential_parameter(self):
        cfg = replace(self.cfg, supports_sequential_generation=False)
        def reply(request):
            value = json.loads(request.content)
            self.assertEqual(str(request.url), ENDPOINT)
            self.assertNotIn("sequential_image_generation", value)
            return httpx.Response(200, json=self.response())
        result = DoubaoAdapter(replace(cfg, transport=httpx.MockTransport(reply))).generate("虚构测试")
        self.assertEqual(result.content, self.png)
        self.assertEqual(result.source, "test_fixture")

    def test_adapter_rejects_url_fallback_extra_images_invalid_bytes_or_usage_without_fetch(self):
        values = [[], {"model": "wrong", "data": []},
                  {"model": "synthetic-seedream", "data": [{"url": "http://127.0.0.1/private"}]},
                  {"model": "synthetic-seedream", "data": [{"b64_json": base64.b64encode(b"<html>not image</html>").decode()}]},
                  {**self.response(), "usage": {"generated_images": 2}},
                  {**self.response(), "data": self.response()["data"] * 2}]
        for value in values:
            with self.subTest(value=str(value)[:60]), self.assertRaises(ProviderUnknown):
                cfg = replace(self.cfg, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=value)))
                DoubaoAdapter(cfg).generate("虚构测试")

    def test_http_replay_uses_current_job_without_duplicate_budget_or_dispatch(self):
        platform = PlatformService(self.service, self.platform_settings)
        register_platform(self.app, platform)
        self.images = platform.images
        body = dict(request_id=self.rid(), mode="live", purpose="work_cover", learner_id=self.lid,
                    target_id=self.work["id"], target_version=self.work["current_version"]["id"],
                    expected_binding_revision=0, slot="cover", prompt="虚构封面")
        headers = {"Origin": "https://learning.example.test", "X-CSRF-Token": self.bootstrap(self.a)["csrf_token"]}
        first = self.a.post("/api/platform/v1/image-jobs", json=body, headers=headers)
        self.assertEqual(first.status_code, 202, first.text)
        archived = self.images.execute(first.json()["id"])
        replay = self.a.post("/api/platform/v1/image-jobs", json=body, headers=headers)
        self.assertEqual(replay.status_code, 202, replay.text)
        self.assertEqual(replay.json()["id"], archived["id"])
        self.assertEqual(replay.json()["state"], "archived")
        self.assertEqual(self.account()["settled"], 1)
        self.assertEqual(len(self.calls), 1)

    def test_migration_is_idempotent_and_old_learning_checksums_unchanged(self):
        with self.service.store.transaction() as con:
            before = [tuple(row) for row in con.execute("SELECT * FROM learn_migrations ORDER BY version")]
        self.images.migrate()
        with self.service.store.transaction() as con:
            self.assertEqual(before, [tuple(row) for row in con.execute("SELECT * FROM learn_migrations ORDER BY version")])
            con.execute("UPDATE platform_migrations SET checksum='corrupt' WHERE version='P03-images'")
        with self.assertRaises(ValueError):
            self.images.migrate()

    def test_new_work_version_retains_slot_revision_but_does_not_reuse_old_cover(self):
        first = self.images.execute(self.queue("sample")["id"])
        self.work = self.external(self.work)
        current = self.bindings()
        self.assertIsNone(current["cover_asset_id"])
        self.assertEqual(current["items"][0]["binding_revision"], 1)
        self.assertNotEqual(current["items"][0]["target_version"], current["target_version"])
        second = self.images.execute(self.queue("sample", expected_binding_revision=1)["id"])
        self.assertEqual(second["state"], "archived")
        self.assertEqual(second["binding_revision"], 2)
        self.assertNotEqual(second["asset_id"], first["asset_id"])

    def test_unknown_can_only_release_with_explicit_verified_server_evidence(self):
        self.hook = lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("fictional timeout", request=request))
        job = self.images.execute(self.queue()["id"])
        with self.assertRaises(ValueError):
            self.images.reconcile_unknown(job["id"], outcome="not_generated", evidence_id="", authority="")
        resolved = self.images.reconcile_unknown(job["id"], outcome="not_generated", evidence_id="fiction-provider-evidence-1", authority="synthetic-operator")
        self.assertEqual(resolved["state"], "cancelled")
        self.assertEqual(self.account()["held"], 0)
        self.assertEqual(self.account()["settled"], 0)
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises(Problem):
            self.images.reconcile_unknown(job["id"], outcome="not_generated", evidence_id="fiction-provider-evidence-1", authority="synthetic-operator")

    def test_unknown_verified_image_recovers_without_second_provider_request(self):
        self.hook = lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("fictional timeout", request=request))
        job = self.images.execute(self.queue()["id"])
        receipt = ImageResult(self.png, "synthetic-seedream", "fiction-verified-receipt", "test_fixture", 1)
        resolved = self.images.reconcile_unknown(job["id"], outcome="received", evidence_id="fiction-provider-evidence-2", authority="synthetic-operator", result=receipt)
        self.assertEqual(resolved["state"], "archived")
        self.assertEqual(self.account()["held"], 0)
        self.assertEqual(self.account()["settled"], 1)
        self.assertEqual(len(self.calls), 1)

    def test_refresh_job_list_restores_queued_unknown_without_client_saved_id_or_dispatch(self):
        first = self.queue("sample")
        second = self.queue(purpose="illustration", slot="pending-illustration")
        self.hook = lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("fictional timeout", request=request))
        self.images.execute(second["id"])
        self.images = ImageService(self.service.store, self.service, self.portfolio, self.platform_settings)
        jobs = self.call("workImageJobs", learner_id=self.lid, work_id=self.work["id"])["items"]
        self.assertEqual({job["id"]: job["state"] for job in jobs}, {first["id"]: "queued", second["id"]: "unknown"})
        self.assertEqual(len(self.calls), 1)
        other_lid, _ = self.create(self.b, "parent-b")
        self.enter(self.b, other_lid)
        with self.assertRaises(Problem) as error:
            self.call("workImageJobs", client=self.b, learner_id=self.lid, work_id=self.work["id"])
        self.assertEqual(error.exception.status, 404)

    def test_queued_input_records_prompt_model_and_target_versions_without_secret(self):
        job = self.queue()
        with self.service.store.transaction() as con:
            snapshot = json.loads(con.execute("SELECT body FROM platform_image_input_snapshots WHERE job_id=?", (job["id"],)).fetchone()[0])
        self.assertEqual(snapshot["prompt_version"], "songban-images@0.1.0")
        self.assertEqual(snapshot["config_version"], self.cfg.config_version)
        self.assertEqual(snapshot["requested_model"], self.cfg.model)
        self.assertEqual(snapshot["target_version"], self.work["current_version"]["id"])
        self.assertNotIn(self.cfg.api_key, json.dumps(snapshot))
        self.assertNotIn("storage_dir", snapshot)


if __name__ == "__main__":
    unittest.main()
