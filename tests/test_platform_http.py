"""Full create_app ASGI boundary checks; synthetic people, files, and provider."""
import base64
from dataclasses import replace
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

from app.learning_v2 import Settings, ReviewQueue
from app.learning_v2.service import digest
from app.platform_v1 import PlatformSettings
from app.platform_v1.images import ImageSettings
from app.studio import hash_password

try:
    from .test_learning_v2_identity import Fixture, BASE, ORIGIN, PASSWORD
except ImportError:
    from test_learning_v2_identity import Fixture, BASE, ORIGIN, PASSWORD


PREFIX = "/api/platform/v1"


class PlatformHttpTests(Fixture, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.path = root / "full-app.sqlite3"
        self.now, self.seq = [1800000000.0], 0
        env = patch.dict(os.environ, {"DATABASE_PATH": str(root / "import.sqlite3"), "SONGBAN_CORE_ONLY": "1"}, clear=True)
        env.start(); self.addCleanup(env.stop)
        private = patch("app.environment.load_env", return_value=None)
        private.start(); self.addCleanup(private.stop)
        network = patch("socket.create_connection", side_effect=AssertionError("Full platform HTTP tests must not use real network"))
        network.start(); self.addCleanup(network.stop)
        self.calls = []
        output = BytesIO(); Image.new("RGB", (20, 12), "#bcdb40").save(output, format="PNG")
        self.png = output.getvalue()
        sample = root / "sample.png"; sample.write_bytes(self.png)
        self.image_settings = ImageSettings(storage_dir=root / "private-assets", config_version="http-offline-v1",
            live_enabled=True, api_key="http-fixture-key-not-real", model="http-fixture-seedream", image_limit=2,
            image_consent_versions=("fiction-v1",), sample_enabled=True, sample_path=sample, sample_limit=10,
            transport=httpx.MockTransport(self.provider))
        self.platform_settings = PlatformSettings(enabled=True, demo_mode=True, image_settings=self.image_settings)
        self.settings = Settings(enabled=True, allowed_origins=(ORIGIN,), consent_version="fiction-v1",
            relationship_queue=ReviewQueue("reviewer", "虚构审核员", 3600, "虚构支持"))
        from app.main import create_app
        self.factory = create_app
        self.app = self.factory(self.path, learning_settings=self.settings, platform_settings=self.platform_settings)
        self.service = self.app.state.learning_v2
        self.service.clock = lambda: self.now[0]
        with self.service.store.transaction() as con:
            password = hash_password(PASSWORD)
            for actor in ("parent-a", "parent-b", "reviewer", "outsider"):
                con.execute("""INSERT INTO people(id,phone,name,token_hash,created_at,password_hash,username,email)
                    VALUES(?,?,?,?,?,?,?,?)""", (actor, "fiction-"+actor, "虚构"+actor, digest("old-"+actor),
                    self.service.stamp(), password, actor, actor+"@example.test"))
        self.service.grant_staff("reviewer", "relationship_review", self.now[0]+86400, authority="synthetic-test-only")
        self.service.grant_staff("reviewer", "consent_read", self.now[0]+86400, authority="synthetic-test-only")
        text = self.make_text()
        text["scope_purposes"].append({"scope": "live_model", "purpose": "虚构图像协议测试，绝不联系供应商。"})
        content = {key: text[key] for key in ("locale", "title", "text", "scope_purposes")}
        text["text_sha256"] = hashlib.sha256(json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        self.service.put_consent_text(text, authority="synthetic-test-only")
        self.a, self.b, self.reviewer = self.client(), self.client(), self.client()
        self.lid, self.fid = self.create(self.a)
        profile = self.a.get(BASE+f"/learners/{self.lid}/profile").json()
        self.consent = self.write(self.a, f"/learners/{self.lid}/consents", dict(request_id=self.rid(), expected_revision=profile["revision"],
            consent_version="fiction-v1", scopes=["learning", "parent_summary", "live_model"], acknowledged=True), expected=201).json()
        self.enter(self.a, self.lid)
        self.images = self.app.state.platform_v1.images
        self.images.grant_budget("learner:"+self.lid, 2, grant_key="http-test-budget", expires=self.now[0]+86400, authority="synthetic-test-only")
        self.work = self.post(f"/learners/{self.lid}/external-works", dict(title="校园植物小助手", summary="记录校园植物的小作品。",
            url="https://example.test/fictional-plants", tool_name="虚构工具", contribution="我整理资料并修改界面。", ai_assistance="assisted"), 201)

    def provider(self, request):
        self.calls.append(json.loads(request.content))
        return httpx.Response(200, json={"model": "http-fixture-seedream", "data": [{"b64_json": base64.b64encode(self.png).decode()}],
            "usage": {"generated_images": 1}}, headers={"x-request-id": "http-fixture-receipt"})

    def post(self, path, body, expected=200, client=None, *, raw=False):
        client = client or self.a
        headers = {"Origin": ORIGIN, "X-CSRF-Token": self.bootstrap(client)["csrf_token"]}
        response = client.post(PREFIX+path, json=body if raw else {"request_id": self.rid(), **body}, headers=headers)
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    def image_body(self, mode="sample"):
        return dict(mode=mode, purpose="work_cover", learner_id=self.lid, target_id=self.work["id"],
                    target_version=self.work["current_version"]["id"], expected_binding_revision=0, slot="cover", prompt="校园植物小助手的插画封面。")

    def saved_image(self, mode="sample"):
        job = self.post("/image-jobs", self.image_body(mode), 202)
        result = self.images.execute(job["id"])
        self.assertEqual(result["state"], "archived", result)
        return result

    def test_create_app_registers_platform_and_keeps_legacy_child_fence(self):
        config = self.a.get(PREFIX+"/config")
        self.assertEqual(config.status_code, 200)
        self.assertEqual(config.json()["image_modes"], {"sample": True, "live": True})
        response = self.a.get(PREFIX+f"/learners/{self.lid}/works")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["items"][0]["id"], self.work["id"])
        blocked = self.a.get("/api/core/me", headers={"Authorization": "Bearer old-outsider"})
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()["error"]["code"], "child_mode_restricted")
        lookalike = self.a.get("/api/platform/v1-not-managed/private", headers={"Authorization": "Bearer old-outsider"})
        self.assertEqual(lookalike.status_code, 403)

    def test_current_cookie_wins_over_valid_unrelated_bearer(self):
        response = self.a.get(PREFIX+f"/learners/{self.lid}/works/{self.work['id']}", headers={"Authorization": "Bearer old-outsider"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["learner_id"], self.lid)
        outsider = self.client()
        response = outsider.get(PREFIX+f"/learners/{self.lid}/works", headers={"Authorization": "Bearer old-outsider"})
        self.assertEqual(response.status_code, 403)

    def test_browser_child_cookie_without_session_cannot_fall_back_to_bearer(self):
        browser_only = self.client()
        browser_only.cookies.update(self.a.cookies)
        for cookie in list(browser_only.cookies.jar):
            if cookie.name == self.service.cookie_name:
                browser_only.cookies.delete(cookie.name, domain=cookie.domain, path=cookie.path)
        response = browser_only.get(PREFIX+f"/learners/{self.lid}/works", headers={"Authorization": "Bearer old-outsider"})
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["error"]["code"], "child_mode_restricted")

    def test_platform_post_requires_csrf_exact_origin_and_json(self):
        path = PREFIX+"/image-jobs"
        body = {"request_id": self.rid(), **self.image_body()}
        self.assertEqual(self.a.post(path, json=body, headers={"Origin": ORIGIN}).status_code, 403)
        csrf = self.bootstrap(self.a)["csrf_token"]
        self.assertEqual(self.a.post(path, json=body, headers={"Origin": "https://foreign.example.test", "X-CSRF-Token": csrf}).status_code, 403)
        response = self.a.post(path, content=json.dumps(body), headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "Content-Type": "text/plain"})
        self.assertEqual(response.status_code, 415, response.text)
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM platform_image_jobs").fetchone()[0], 0)
        self.assertEqual(self.calls, [])

    def test_binary_asset_headers_are_private_and_cover_projection_is_enriched(self):
        image = self.saved_image()
        response = self.a.get(PREFIX+f"/assets/{image['asset_id']}/content")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, self.png)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["cross-origin-resource-policy"], "same-origin")
        self.assertIn("sandbox", response.headers["content-security-policy"])
        work = self.a.get(PREFIX+f"/learners/{self.lid}/works/{self.work['id']}").json()
        self.assertEqual(work["cover_asset_id"], image["asset_id"])
        self.assertEqual(self.calls, [])

    def test_foreign_child_cannot_read_metadata_binary_binding_or_job_restore(self):
        image = self.saved_image()
        other_lid, _ = self.create(self.b, "parent-b")
        self.enter(self.b, other_lid)
        for path in (f"/assets/{image['asset_id']}", f"/assets/{image['asset_id']}/content", f"/image-jobs/{image['id']}",
                     f"/learners/{self.lid}/works/{self.work['id']}/images", f"/learners/{self.lid}/works/{self.work['id']}/image-jobs"):
            response = self.b.get(PREFIX+path)
            with self.subTest(path=path):
                self.assertEqual(response.status_code, 404, response.text)
                self.assertIn("no-store", response.headers["cache-control"])
                self.assertNotEqual(response.content, self.png)

    def test_stale_child_cookie_after_mode_switch_cannot_read_image_even_with_bearer(self):
        image = self.saved_image()
        old = self.client(); old.cookies.update(self.a.cookies)
        self.login(self.a, "parent-a")
        response = old.get(PREFIX+f"/assets/{image['asset_id']}/content", headers={"Authorization": "Bearer old-outsider"})
        self.assertEqual(response.status_code, 401, response.text)
        self.assertIn("no-store", response.headers["cache-control"])
        parent = self.a.get(PREFIX+f"/assets/{image['asset_id']}/content")
        self.assertEqual(parent.status_code, 200)
        self.assertEqual(parent.content, self.png)

    def test_parent_summary_revocation_hides_asset_and_cached_receipt(self):
        image = self.saved_image()
        self.login(self.a, "parent-a")
        with self.service.store.transaction() as con:
            con.execute("UPDATE learn_consents SET scopes='[\"learning\",\"live_model\"]' WHERE id=?", (self.consent["id"],))
        response = self.a.get(PREFIX+f"/assets/{image['asset_id']}/content")
        self.assertEqual(response.status_code, 403, response.text)
        self.assertNotEqual(response.content, self.png)
        self.assertEqual(self.calls, [])

    def test_http_idempotency_replay_does_not_duplicate_real_protocol_dispatch(self):
        body = {"request_id": self.rid(), **self.image_body("live")}
        job = self.post("/image-jobs", body, 202, raw=True)
        self.images.execute(job["id"])
        replay = self.post("/image-jobs", body, 202, raw=True)
        self.assertEqual(replay["id"], job["id"])
        self.assertEqual(replay["state"], "archived")
        self.assertEqual(len(self.calls), 1)
        body["prompt"] = "同号改内容"
        result = self.post("/image-jobs", body, 409, raw=True)
        self.assertEqual(result["error"]["code"], "idempotency_conflict")
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM platform_image_jobs").fetchone()[0], 1)

    def test_refresh_job_restore_is_read_only_and_does_not_dispatch(self):
        job = self.post("/image-jobs", self.image_body("live"), 202)
        path = PREFIX+f"/learners/{self.lid}/works/{self.work['id']}/image-jobs"
        restored = self.a.get(path)
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["items"][0]["id"], job["id"])
        self.assertEqual(restored.json()["items"][0]["state"], "queued")
        self.assertEqual(self.calls, [])

    def test_paused_full_app_reads_history_blocks_new_writes_and_cancels_queued_dispatch(self):
        job = self.post("/image-jobs", self.image_body("live"), 202)
        paused = self.factory(self.path, learning_settings=self.settings, platform_settings=replace(self.platform_settings, enabled=False))
        paused.state.learning_v2.clock = lambda: self.now[0]
        client = self.client(paused); client.cookies.update(self.a.cookies)
        self.assertEqual(client.get(PREFIX+f"/learners/{self.lid}/works").status_code, 200)
        response = self.post("/image-jobs", self.image_body("live"), 423, client=client)
        self.assertEqual(response["error"]["code"], "platform_paused")
        result = paused.state.platform_v1.images.execute(job["id"])
        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(self.calls, [])

    def test_relationship_revocation_blocks_child_binary_without_waiting_for_ui_clear(self):
        image = self.saved_image()
        with self.service.store.transaction() as con:
            con.execute("UPDATE learn_links SET status='revoked' WHERE learner_id=?", (self.lid,))
        for path in (f"/assets/{image['asset_id']}/content", f"/learners/{self.lid}/works/{self.work['id']}/image-jobs"):
            response = self.a.get(PREFIX+path)
            self.assertEqual(response.status_code, 403, response.text)
            self.assertEqual(response.json()["error"]["code"], "consent_required")
            self.assertNotEqual(response.content, self.png)
            self.assertIn("no-store", response.headers["cache-control"])

    def test_binary_cross_site_fetch_is_rejected_even_with_manually_supplied_cookie(self):
        image = self.saved_image()
        response = self.a.get(PREFIX+f"/assets/{image['asset_id']}/content", headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(response.status_code, 403, response.text)
        self.assertNotEqual(response.content, self.png)


if __name__ == "__main__":
    unittest.main()
