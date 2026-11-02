"""Offline P1 tests: synthetic people, temporary SQLite, in-process ASGI only."""
import copy
import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
from dataclasses import replace
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.learning_v2 import LearningV2, ReviewQueue, Settings, register_learning_v2
from app.learning_v2.protocol import Problem
from app.learning_v2.service import digest
from app.studio import hash_password


PASSWORD = "fictional-password-only"
ORIGIN = "https://learning.example.test"
BASE = "/api/learning/v2"


class Fixture:
    def setUp(self):
        # Future accidental service/config calls fail closed in this offline suite.
        for target in ("socket.create_connection", "app.environment.load_env"):
            guard = patch(target, side_effect=AssertionError("Offline tests must not access network/private environment"))
            guard.start()
            self.addCleanup(guard.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "isolated.sqlite3"
        self.now = [1800000000.0]
        self.settings = Settings(enabled=True, allowed_origins=(ORIGIN,), consent_version="fiction-v1",
                                 age_band_options=("fixture-younger", "fixture-older"),
                                 relationship_queue=ReviewQueue("reviewer", "虚构核验员", 3600, "隔离测试支持"))
        with closing(sqlite3.connect(self.path)) as con:
            con.execute("CREATE TABLE people(id TEXT PRIMARY KEY,phone TEXT UNIQUE,username TEXT UNIQUE,email TEXT UNIQUE,password_hash TEXT,token_hash TEXT UNIQUE,name TEXT)")
            con.execute("CREATE TABLE login_attempts(key TEXT PRIMARY KEY,attempts INTEGER NOT NULL DEFAULT 0,blocked_until TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL)")
            con.execute("CREATE TABLE legacy_facts(id TEXT PRIMARY KEY)")
            password_hash = hash_password(PASSWORD)
            for person in ("parent-a", "parent-b", "reviewer", "outsider"):
                con.execute("INSERT INTO people VALUES(?,?,?,?,?,?,?)", (person, None, person, person+"@example.test", password_hash, digest("old-"+person), "虚构"))
            con.commit()
        self.service = self.new_service()
        self.service.migrate()
        self.service.grant_staff("reviewer", "relationship_review", self.now[0]+86400, authority="synthetic-test-only")
        self.service.grant_staff("reviewer", "consent_read", self.now[0]+86400, authority="synthetic-test-only")
        self.text = self.make_text()
        self.service.put_consent_text(self.text, authority="synthetic-test-only")
        self.app = self.new_app()
        self.a = self.client()
        self.b = self.client()
        self.reviewer = self.client()
        self.seq = 0

    def new_service(self, settings=None):
        return LearningV2(self.path, settings or self.settings, clock=lambda: self.now[0])

    def new_app(self, service=None):
        api = FastAPI()
        register_learning_v2(api, service or self.service)
        return api

    def client(self, app=None):
        client = TestClient(app or self.app, base_url=ORIGIN)
        self.addCleanup(client.close)
        return client

    def make_text(self, version="fiction-v1", status="approved_for_pilot"):
        content = {"locale": "zh-CN", "title": "虚构隔离测试授权", "text": "仅用于临时数据库测试，不是法律文本或真实批准。",
                   "scope_purposes": [{"scope": "learning", "purpose": "虚构起点保存"}, {"scope": "parent_summary", "purpose": "虚构摘要"}]}
        return {"consent_version": version, **content, "text_sha256": hashlib.sha256(json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(),
                "approval_status": status, "approved_at": "2027-01-15T08:00:00+00:00" if status == "approved_for_pilot" else None,
                "acceptance_enabled": status == "approved_for_pilot", "notice": "仅供隔离测试"}

    def rid(self):
        self.seq += 1
        return f"fiction-request-{self.seq:05}"

    def bootstrap(self, client):
        response = client.get(BASE+"/session-bootstrap")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def write(self, client, path, body, method="POST", expected=200):
        csrf = self.bootstrap(client)["csrf_token"]
        response = client.request(method, BASE+path, json=body, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
        if expected is not None:
            self.assertEqual(response.status_code, expected, response.text)
        return response

    def login(self, client, account="parent-a"):
        browser = self.bootstrap(client)
        response = self.write(client, "/sessions/authenticate", {"request_id": self.rid(), "browser_revision": browser["browser_revision"], "method": "password", "account": account, "proof": PASSWORD})
        return response.json()

    def create(self, client, account="parent-a", verified=True, consent=True):
        self.login(client, account)
        family = self.write(client, "/families", {"request_id": self.rid()}, expected=201).json()
        learner = self.write(client, f"/families/{family['id']}/learners", {"request_id": self.rid(), "expected_revision": family["revision"], "display_name": "虚构小松", "age_band": None, "declared_relationship": "测试声明，未自动核验"}, expected=201).json()
        if verified:
            self.verify(learner)
            learner = client.get(BASE+f"/learners/{learner['id']}/profile").json()
        if consent:
            self.write(client, f"/learners/{learner['id']}/consents", {"request_id": self.rid(), "expected_revision": learner["revision"], "consent_version": "fiction-v1", "scopes": ["learning"], "acknowledged": True}, expected=201)
        return learner["id"], family["id"]

    def verify(self, learner):
        self.login(self.reviewer, "reviewer")
        cases = self.reviewer.get(BASE+"/cases").json()["items"]
        case = next(c for c in cases if c["learner_id"] == learner["id"])
        eid = self.service.add_relationship_evidence(case["id"], "虚构核验依据，不含真实身份资料。", authority="synthetic-test-only")
        claimed = self.write(self.reviewer, f"/cases/{case['id']}/claim", {"request_id": self.rid(), "expected_revision": case["revision"]}).json()
        return self.write(self.reviewer, f"/cases/{case['id']}/resolve", {"request_id": self.rid(), "expected_revision": claimed["revision"], "target_revision": learner["revision"], "decision": "verified", "evidence_ids": [eid], "note": "虚构流程核对", "manual_findings": []}).json()

    def enter(self, client, learner):
        session = client.get(BASE+"/session").json()
        return self.write(client, "/sessions/enter-learner", {"request_id": self.rid(), "expected_revision": session["revision"], "learner_id": learner}).json()

    def request_for(self, client, extra=None):
        cookies = "; ".join(f"{c.name}={c.value}" for c in client.cookies.jar)
        return Request({"type": "http", "method": "POST", "scheme": "https", "path": "/api/core/synthetic", "query_string": b"", "server": ("learning.example.test", 443), "client": ("testclient", 1234),
                        "headers": [(b"cookie", cookies.encode()), *list(extra or [])]})


class IdentityTests(Fixture, unittest.TestCase):
    def test_import_registration_and_default_paused(self):
        import subprocess
        import sys
        script = """
import sys, sqlite3, socket
sys.path.insert(0, sys.argv[1])
def blocked(*args, **kwargs):
    raise AssertionError('Import must not load private config, database or network')
sqlite3.connect = blocked
socket.create_connection = blocked
from app import environment
environment.load_env = blocked
import app.learning_v2
assert 'app.main' not in sys.modules
print('isolated import boundary passed')
"""
        imported = subprocess.run([sys.executable, "-B", "-I", "-c", script, str(Path(__file__).resolve().parents[1])],
                                  capture_output=True, text=True, timeout=20, check=True)
        self.assertIn("isolated import boundary passed", imported.stdout)
        service = self.new_service(Settings(allowed_origins=(ORIGIN,)))
        service.migrate()
        c = self.client(self.new_app(service))
        self.assertFalse(c.get(BASE+"/config").json()["learning_enabled"])
        self.assertEqual(c.get("/families").status_code, 404)
        self.login(c)
        self.write(c, "/families", {"request_id": self.rid()}, expected=423)
        self.assertEqual(c.get(BASE+"/families").json()["items"], [])

    def test_cookie_origin_csrf_and_no_refresh(self):
        response = self.a.get(BASE+"/session-bootstrap")
        cookie = response.headers["set-cookie"]
        for flag in ("__Host-songban_browser", "HttpOnly", "Secure", "SameSite=strict", "Path=/"):
            self.assertIn(flag, cookie)
        self.assertNotIn("Domain=", cookie)
        browser = response.json()
        body = {"request_id": self.rid(), "browser_revision": 0, "method": "password", "account": "parent-a", "proof": PASSWORD}
        for headers in ({}, {"Origin": "https://evil.test", "X-CSRF-Token": browser["csrf_token"]}, {"Origin": ORIGIN, "X-CSRF-Token": "wrong"}):
            self.assertEqual(self.a.post(BASE+"/sessions/authenticate", json=body, headers=headers).status_code, 403)
        self.login(self.a)
        self.assertNotIn("set-cookie", self.a.get(BASE+"/session").headers)
        self.assertNotIn("set-cookie", self.a.get(BASE+"/session-bootstrap").headers)
        self.assertEqual(self.a.get(BASE+"/session").headers["cache-control"], "no-store")
        for origin in ("http://example.com", "https://localhost", "http://127.0.0.1.evil.test"):
            with self.assertRaises(ValueError):
                Settings(allowed_origins=(origin,), loopback_http=True)
        local = LearningV2(self.path, Settings(allowed_origins=("http://127.0.0.1:9000",), loopback_http=True))
        self.assertEqual(local.cookie_name, "songban_dev_session")
        with TestClient(self.new_app(local), base_url="http://127.0.0.1:9000") as local_client:
            boot = local_client.get(BASE+"/session-bootstrap")
            self.assertEqual(boot.status_code, 200)
            self.assertNotIn("Secure", boot.headers["set-cookie"])
            self.assertIn("songban_dev_browser", boot.headers["set-cookie"])
            self.assertEqual(local_client.get("http://public.example.test"+BASE+"/session-bootstrap").status_code, 403)
        with TestClient(self.app, base_url="http://learning.example.test") as insecure:
            self.assertEqual(insecure.get(BASE+"/session-bootstrap").status_code, 403)

    def test_no_bearer_exchange_or_challenge_or_role_injection(self):
        self.assertEqual(self.a.get(BASE+"/families", headers={"Authorization": "Bearer old-parent-a"}).status_code, 401)
        browser = self.bootstrap(self.a)
        body = {"request_id": self.rid(), "browser_revision": browser["browser_revision"], "method": "verified_challenge", "account": "parent-a", "proof": "old-parent-a"}
        self.write(self.a, "/sessions/authenticate", body, expected=503)
        body.update(method="password", proof=PASSWORD, role="staff")
        response = self.write(self.a, "/sessions/authenticate", body, expected=422)
        self.assertNotIn(PASSWORD, response.text)

    def test_shared_rate_limit_persists_and_no_credentials_stored(self):
        browser = self.bootstrap(self.a)
        for i in range(5):
            response = self.write(self.a, "/sessions/authenticate", {"request_id": self.rid(), "browser_revision": browser["browser_revision"], "method": "password", "account": "parent-a", "proof": "secret-wrong-proof"}, expected=401 if i < 4 else 429)
        self.assertEqual(response.headers["Retry-After"], "300")
        with self.service.store.transaction() as con:
            row = con.execute("SELECT attempts FROM login_attempts WHERE key=?", ("account:"+digest("parent-a"),)).fetchone()
            self.assertEqual(row[0], 5)
        restarted = self.client(self.new_app(self.new_service()))
        self.write(restarted, "/sessions/authenticate", {"request_id": self.rid(), "browser_revision": 0, "method": "password", "account": "parent-a", "proof": PASSWORD}, expected=429)
        self.now[0] += 301
        self.login(self.a)
        with self.service.store.transaction() as con:
            records = " ".join(str(tuple(r)) for table in ("learn_requests", "learn_audit", "login_attempts") for r in con.execute("SELECT * FROM "+table))
        for secret in (PASSWORD, "secret-wrong-proof", self.a.cookies.get(self.service.cookie_name)):
            self.assertNotIn(secret, records)

    def test_family_idempotency_and_recovery_after_restart(self):
        self.login(self.a)
        body = {"request_id": self.rid()}
        first = self.write(self.a, "/families", body, expected=201)
        self.assertEqual(self.write(self.a, "/families", body, expected=201).json(), first.json())
        self.write(self.a, "/families", {"request_id": self.rid()}, expected=409)
        restarted = self.new_service()
        restarted.migrate()
        fresh = self.client(self.new_app(restarted))
        self.login(fresh)
        self.assertEqual(fresh.get(BASE+"/families").json()["items"], [first.json()])
        self.assertEqual(fresh.get(BASE+"/families?owner_id=parent-b").status_code, 422)
        self.login(self.b, "parent-b")
        self.assertEqual(self.b.get(BASE+f"/families/{first.json()['id']}").status_code, 404)

    def test_pending_relationship_and_no_staff_self_grant(self):
        lid, _ = self.create(self.a, verified=False, consent=False)
        self.assertEqual(self.a.get(BASE+f"/learners/{lid}/profile").json()["guardian_link"]["status"], "pending")
        self.assertEqual(self.a.get(BASE+f"/learners/{lid}/consents").json()["items"], [])
        self.write(self.a, f"/learners/{lid}/consents", {"request_id": self.rid(), "expected_revision": 1, "consent_version": "fiction-v1", "scopes": ["learning"], "acknowledged": True}, expected=403)
        self.assertEqual(self.a.get(BASE+f"/learners/{lid}/start").status_code, 403)
        session = self.a.get(BASE+"/session").json()
        self.write(self.a, "/sessions/enter-learner", {"request_id": self.rid(), "expected_revision": session["revision"], "learner_id": lid}, expected=403)
        self.login(self.b, "outsider")
        self.assertEqual(self.b.get(BASE+"/cases").status_code, 403)
        noqueue = self.new_service(replace(self.settings, relationship_queue=None))
        client = self.client(self.new_app(noqueue))
        self.login(client, "parent-b")
        family = self.write(client, "/families", {"request_id": self.rid()}, expected=201).json()
        self.write(client, f"/families/{family['id']}/learners", {"request_id": self.rid(), "expected_revision": 1, "display_name": "虚构", "age_band": None, "declared_relationship": "声明"}, expected=503)
        self.assertEqual(client.get(BASE+f"/families/{family['id']}").json()["learners"], [])

    def test_assigned_review_evidence_and_revision(self):
        lid, _ = self.create(self.a, verified=False, consent=False)
        self.login(self.reviewer, "reviewer")
        case = self.reviewer.get(BASE+"/cases").json()["items"][0]
        self.service.grant_staff("outsider", "relationship_review", self.now[0]+1000, authority="synthetic-test-only")
        self.login(self.b, "outsider")
        self.assertEqual(self.b.get(BASE+f"/cases/{case['id']}").status_code, 404)
        self.assertEqual(self.b.get(BASE+"/cases").json()["items"], [])
        self.write(self.reviewer, f"/cases/{case['id']}/claim", {"request_id": self.rid(), "expected_revision": 1})
        body = {"request_id": self.rid(), "expected_revision": 2, "target_revision": 1, "decision": "verified", "evidence_ids": ["made-up-evidence"], "note": "测试", "manual_findings": []}
        self.write(self.reviewer, f"/cases/{case['id']}/resolve", body, expected=422)
        self.write(self.a, f"/learners/{lid}/profile", {"request_id": self.rid(), "expected_revision": 1, "display_name": "虚构新称呼", "age_band": None}, method="PATCH")
        body["request_id"] = self.rid()
        self.write(self.reviewer, f"/cases/{case['id']}/resolve", body, expected=409)

    def test_consent_version_hash_draft_and_revocation(self):
        lid, _ = self.create(self.a, consent=False)
        draft = self.make_text("draft-v1", "draft")
        self.service.put_consent_text(draft, authority="synthetic-test-only")
        profile = self.a.get(BASE+f"/learners/{lid}/profile").json()
        body = {"request_id": self.rid(), "expected_revision": profile["revision"], "consent_version": "draft-v1", "scopes": ["learning"], "acknowledged": True}
        self.write(self.a, f"/learners/{lid}/consents", body, expected=403)
        body.update(request_id=self.rid(), consent_version="fiction-v1")
        consent = self.write(self.a, f"/learners/{lid}/consents", body, expected=201).json()
        records = self.a.get(BASE+f"/learners/{lid}/consents").json()
        self.assertEqual(records["items"][0]["effective_scopes"], ["learning"])
        self.assertEqual(records["items"][0]["text_sha256"], self.text["text_sha256"])
        self.assertEqual(self.a.get(BASE+"/consent-texts/fiction-v1").json(), self.text)
        changed = copy.deepcopy(self.text)
        changed["text"] = "another text"
        with self.assertRaises(ValueError):
            self.service.put_consent_text(changed, authority="test")
        manager = self.client()
        self.login(manager)
        self.enter(self.a, lid)
        self.assertEqual(self.a.get(BASE+f"/learners/{lid}/consents").status_code, 403)
        self.write(manager, f"/consents/{consent['id']}/revoke", {"request_id": self.rid(), "expected_revision": 1, "reason": "虚构撤回"})
        self.assertEqual(self.a.get(BASE+"/session").status_code, 401)
        self.assertEqual(manager.get(BASE+f"/learners/{lid}/consents").json()["items"][0]["effective_scopes"], [])
        # Logout remains possible after derived permission revocation.
        self.write(self.a, "/sessions/logout", {"request_id": self.rid(), "expected_revision": 2})

    def test_switch_old_tabs_bearer_and_fences_both_commit_orders(self):
        lid, _ = self.create(self.a)
        old = self.client()
        old.cookies.update(self.a.cookies)
        request = self.request_for(old)
        with self.service.store.transaction() as con:
            fence = self.service.legacy_request_guard(con, request, "parent-a")
        # Deterministic writer-first ordering with a held SQLite transaction,
        # thread event/barrier rather than a timing sleep.
        entered = threading.Event()
        errors = []
        csrf = self.bootstrap(self.a)["csrf_token"]
        session = self.a.get(BASE+"/session").json()
        body = {"request_id": self.rid(), "expected_revision": session["revision"], "learner_id": lid}
        def switch():
            entered.set()
            try:
                res = self.a.post(BASE+"/sessions/enter-learner", json=body, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
                if res.status_code != 200:
                    errors.append(res.text)
            except BaseException as exc:
                errors.append(str(exc))
        with self.service.store.transaction() as con:
            con.execute("INSERT INTO legacy_facts VALUES('before-switch')")
            self.service.legacy_commit_fence(con, fence)
            thread = threading.Thread(target=switch)
            thread.start()
            self.assertTrue(entered.wait(3))
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(old.get(BASE+"/session").status_code, 401)
        self.assertEqual(self.a.get(BASE+"/families", headers={"Authorization": "Bearer old-parent-a"}).status_code, 403)
        with self.service.store.transaction() as con:
            self.assertNotEqual(con.execute("SELECT token_hash FROM people WHERE id='parent-a'").fetchone()[0], digest("old-parent-a"))
            with self.assertRaises(Problem) as caught:
                self.service.legacy_request_guard(con, self.request_for(self.a, [(b"authorization", b"Bearer sbconn_fake")]), "parent-a")
            self.assertEqual(caught.exception.code, "child_mode_restricted")
        # Switch-first: staged legacy mutation must be rolled back on the same connection.
        with self.assertRaises(Problem):
            with self.service.store.transaction() as con:
                con.execute("INSERT INTO legacy_facts VALUES('late-write')")
                self.service.legacy_commit_fence(con, fence)
        with self.assertRaises(Problem):
            self.service.legacy_read_fence(fence)
        with self.service.store.transaction() as con:
            self.assertEqual([r[0] for r in con.execute("SELECT id FROM legacy_facts")], ["before-switch"])
        self.assertEqual(self.login(self.a)["mode"], "manager")
        self.assertEqual(old.get(BASE+"/session").status_code, 401)

    def test_session_transition_replay_never_reissues_credentials(self):
        lid, _ = self.create(self.a)
        session = self.a.get(BASE+"/session").json()
        body = {"request_id": self.rid(), "expected_revision": session["revision"], "learner_id": lid}
        old = self.client()
        old.cookies.update(self.a.cookies)
        result = self.write(self.a, "/sessions/enter-learner", body)
        replay = self.write(self.a, "/sessions/enter-learner", body)
        self.assertEqual(replay.json(), result.json())
        self.assertNotIn("set-cookie", replay.headers)
        self.write(old, "/sessions/enter-learner", body, expected=401)
        self.now[0] += self.settings.session_seconds+1
        self.assertEqual(self.a.get(BASE+"/session").status_code, 401)

    def test_text_withdrawal_and_relationship_revocation_invalidate_sessions(self):
        lid, _ = self.create(self.a)
        self.enter(self.a, lid)
        withdrawn = {**self.text, "approval_status": "withdrawn", "acceptance_enabled": False}
        self.service.put_consent_text(withdrawn, authority="synthetic-withdrawal")
        self.assertEqual(self.a.get(BASE+"/session").status_code, 401)
        self.service.put_consent_text(self.text, authority="synthetic-reapproval")
        self.login(self.a)
        self.enter(self.a, lid)
        self.service.revoke_relationship(lid, authority="synthetic-revocation")
        self.assertEqual(self.a.get(BASE+"/session").status_code, 401)

    def test_consent_text_metadata_roundtrip_and_nested_key_order(self):
        returned = self.a.get(BASE+"/consent-texts/fiction-v1").json()
        # Persistence serializes nested keys alphabetically. Reimporting GET must
        # preserve the fixed semantic hash rather than depend on dict order.
        self.assertEqual(list(returned["scope_purposes"][0]), ["purpose", "scope"])
        self.service.put_consent_text(returned, authority="synthetic-roundtrip")
        withdrawn = {**returned, "approval_status": "withdrawn", "acceptance_enabled": False}
        self.service.put_consent_text(withdrawn, authority="synthetic-metadata-only")
        restored = {**returned, "scope_purposes": [dict(reversed(list(p.items()))) for p in returned["scope_purposes"]]}
        self.service.put_consent_text(restored, authority="synthetic-nested-key-reversal")
        self.assertEqual(self.a.get(BASE+"/consent-texts/fiction-v1").json(), returned)
        with self.service.store.transaction() as con:
            versions = [r[0] for r in con.execute("SELECT version FROM learn_texts ORDER BY version")]
        self.assertEqual(versions, ["fiction-v1"])

    def test_two_families_and_child_projection_and_unimplemented(self):
        lid, fid = self.create(self.a)
        other, _ = self.create(self.b, "parent-b")
        self.assertEqual(self.b.get(BASE+f"/learners/{lid}/consents").status_code, 404)
        self.enter(self.a, lid)
        profile = self.a.get(BASE+f"/learners/{lid}/profile").json()
        self.assertNotIn("family_id", profile)
        self.assertNotIn("guardian_link", profile)
        self.assertEqual(self.a.get(BASE+f"/learners/{other}/profile").status_code, 404)
        self.assertEqual(self.a.get(BASE+f"/learners/{other}/start").status_code, 404)
        self.assertEqual(self.a.get(BASE+f"/families/{fid}").status_code, 403)
        self.write(self.a, f"/learners/{lid}/enrollments", {"request_id": self.rid()}, expected=503)
        self.assertEqual(self.a.get(BASE+f"/learners/{lid}/home").status_code, 503)

    def test_duplicate_json_keys_nan_and_request_id_conflict(self):
        self.login(self.a)
        csrf = self.bootstrap(self.a)["csrf_token"]
        headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf, "Content-Type": "application/json"}
        for raw in ('{"request_id":"12345678","request_id":"different"}', '{"request_id":NaN}', '{"request_id":"12345678","extra":true}', '{"request_id":1e400}', '{"request_id":"\\ud80012345678"}'):
            self.assertEqual(self.a.post(BASE+"/families", content=raw, headers=headers).status_code, 422)

    def test_frozen_contract_and_registered_openapi(self):
        source = Path(__file__).resolve().parents[1] / "docs/planning/learning-roadmap/p0/contracts/openapi.proposed.json"
        frozen = self.service.contract.document
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), frozen["source_sha256"])
        document = json.loads(source.read_text(encoding="utf-8"))
        for name, schema in frozen["components"]["schemas"].items():
            if name in ('Config', 'Help'):
                original = document['components']['schemas'][name]
                self.assertEqual(schema['required'], original['required'])
                additions = ({'live_model_config_version', 'mock_enabled', 'reports_enabled', 'reports_readable', 'studio_enabled', 'catalog_enabled'}
                             if name == 'Config' else {'question', 'created_at'})
                self.assertEqual(set(schema['properties']) - set(original['properties']),
                                 additions)
                for field, shape in original['properties'].items():
                    self.assertEqual(schema['properties'][field], shape)
                projected = copy.deepcopy(schema)
                projected['properties'] = original['properties']
                self.assertEqual(projected, original)
            elif name in ('LearningEntry', 'EntryCandidate', 'SaveLearningEntry', 'ConfirmLearningEntry'):
                from app.learning_v2.entry_contract import ENTRY_SCHEMAS
                self.assertEqual(schema, ENTRY_SCHEMAS[name])
            else:
                self.assertEqual(schema, document["components"]["schemas"][name])
        openapi = self.app.openapi()
        self.assertEqual(len(openapi["paths"]), len(frozen["paths"]))
        for path, methods in frozen["paths"].items():
            for method, spec in methods.items():
                generated = openapi["paths"][BASE+path][method]
                self.assertEqual(generated["operationId"], spec["operationId"])
                if "requestBody" in spec:
                    self.assertIn("requestBody", generated)
        self.assertIn("LearningV2Session", openapi["components"]["securitySchemes"])

    def test_authenticate_retry_and_lost_cookie_do_not_mint_again(self):
        browser = self.bootstrap(self.a)
        old = self.client()
        old.cookies.update(self.a.cookies)
        body = {"request_id": self.rid(), "browser_revision": browser["browser_revision"], "method": "password", "account": "parent-a", "proof": PASSWORD}
        first = self.write(self.a, "/sessions/authenticate", body)
        replay = self.write(self.a, "/sessions/authenticate", body)
        self.assertEqual(first.json(), replay.json())
        self.assertNotIn("set-cookie", replay.headers)
        self.write(old, "/sessions/authenticate", body, expected=401)
        changed = {**body, "proof": "changed-proof"}
        self.write(self.a, "/sessions/authenticate", changed, expected=409)

    def test_consent_cursor_scope_pending_projection_and_staff_revocation(self):
        lid, _ = self.create(self.a)
        learner = self.a.get(BASE+f"/learners/{lid}/profile").json()
        self.write(self.a, f"/learners/{lid}/consents", {"request_id": self.rid(), "expected_revision": learner["revision"], "consent_version": "fiction-v1", "scopes": ["parent_summary"], "acknowledged": True}, expected=201)
        page1 = self.a.get(BASE+f"/learners/{lid}/consents?limit=1").json()
        self.assertIsNotNone(page1["next_cursor"])
        page2 = self.a.get(BASE+f"/learners/{lid}/consents", params={"limit": 1, "cursor": page1["next_cursor"]}).json()
        self.assertNotEqual(page1["items"][0]["id"], page2["items"][0]["id"])
        self.assertIsNone(page2["next_cursor"])
        staff = self.reviewer.get(BASE+f"/learners/{lid}/consents").json()
        self.assertEqual(staff["visibility"], "assigned_case")
        self.assertEqual(self.reviewer.get(BASE+f"/learners/{lid}/consents", params={"cursor": page1["next_cursor"]}).status_code, 422)
        # Simulate a reviewed relationship being returned to pending by central policy.
        with self.service.store.transaction() as con:
            con.execute("UPDATE learn_links SET status='pending',revision=revision+1 WHERE learner_id=?", (lid,))
        pending = self.a.get(BASE+f"/learners/{lid}/consents").json()
        self.assertEqual(pending["visibility"], "own_submissions")
        self.assertTrue(all(not r["effective_scopes"] for r in pending["items"]))
        with self.service.store.transaction() as con:
            con.execute("DELETE FROM learn_grants WHERE actor_id='reviewer'")
        self.assertEqual(self.reviewer.get(BASE+f"/learners/{lid}/consents").status_code, 403)

    def test_migration_checksum_and_atomic_failure(self):
        from app.learning_v2 import storage
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
            before = con.execute("SELECT token_hash FROM people WHERE id='parent-a'").fetchone()[0]
        self.service.migrate()
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute("SELECT token_hash FROM people WHERE id='parent-a'").fetchone()[0], before)
        with patch.object(storage, "DDL", storage.DDL + " CREATE TABLE drift(id TEXT);"):
            with self.assertRaises(ValueError):
                self.service.migrate()
        other_path = Path(self.tmp.name) / "migration-failure.sqlite3"
        with closing(sqlite3.connect(other_path)) as con:
            con.execute("CREATE TABLE people(id TEXT PRIMARY KEY,password_hash TEXT,token_hash TEXT)")
            con.execute("CREATE TABLE login_attempts(key TEXT,attempts INTEGER,blocked_until TEXT,updated_at TEXT)")
            con.commit()
        failed = LearningV2(other_path)
        with patch.object(storage, "DDL", storage.DDL + " INVALID SQL;"):
            with self.assertRaises(sqlite3.OperationalError):
                failed.migrate()
        with closing(sqlite3.connect(other_path)) as con:
            self.assertEqual(con.execute("SELECT name FROM sqlite_master WHERE name GLOB 'learn_*'").fetchall(), [])

    def test_backup_recovery_and_old_fence_does_not_restore(self):
        lid, _ = self.create(self.a)
        with self.service.store.transaction() as con:
            fence = self.service.legacy_request_guard(con, self.request_for(self.a), "parent-a")
        self.enter(self.a, lid)
        copy_path = Path(self.tmp.name) / "backup.sqlite3"
        with closing(self.service.store.connect()) as source, closing(sqlite3.connect(copy_path)) as destination:
            source.backup(destination)
        restored = LearningV2(copy_path, self.settings, clock=lambda: self.now[0])
        restored.migrate()
        c = self.client(self.new_app(restored))
        c.cookies.update(self.a.cookies)
        self.assertEqual(c.get(BASE+"/session").json()["mode"], "learner")
        with self.assertRaises(Problem):
            restored.legacy_read_fence(fence)

    def test_unverified_or_revoked_authorization_cannot_replay_private_result(self):
        lid, _ = self.create(self.a)
        self.enter(self.a, lid)
        body = {"request_id": self.rid(), "expected_revision": 0, "answers": {"mini_attempt_text": {"state": "answered", "value": "虚构学习答案"}}}
        self.write(self.a, f"/learners/{lid}/start", body, method="PATCH")
        self.service.revoke_relationship(lid, authority="synthetic-test-only")
        denied = self.write(self.a, f"/learners/{lid}/start", body, method="PATCH", expected=401)
        self.assertNotIn("虚构学习答案", denied.text)

    def test_guard_binds_actual_credential_after_legacy_auth_race(self):
        lid, _ = self.create(self.a)
        # Old central authentication may have returned parent-a just before switch.
        self.enter(self.a, lid)
        naked = self.client()
        stale_request = self.request_for(naked, [(b"authorization", b"Bearer old-parent-a")])
        with self.service.store.transaction() as con:
            with self.assertRaises(Problem):
                self.service.legacy_request_guard(con, stale_request, "parent-a")
            with self.assertRaises(Problem):
                self.service.legacy_request_guard(con, self.request_for(naked), "parent-a")

    def test_connector_fence_preserves_background_scope_and_checks_revocation(self):
        from app.learning_v2.service import iso
        with self.service.store.transaction() as con:
            con.execute("CREATE TABLE core_connections(id TEXT,user_id TEXT,token_hash TEXT,paused INTEGER,revoked INTEGER,expires_at TEXT)")
            con.execute("INSERT INTO core_connections VALUES('fiction-connector','parent-a',?,0,0,?)", (digest("sbconn_fiction"), iso(self.now[0]+3600)))
            request = self.request_for(self.a, [(b"authorization", b"Bearer sbconn_fiction")])
            fence = self.service.legacy_request_guard(con, request, "parent-a")
            self.service.legacy_commit_fence(con, fence)
        with self.service.store.transaction() as con:
            con.execute("UPDATE core_connections SET revoked=1")
        with self.assertRaises(Problem):
            self.service.legacy_read_fence(fence)


if __name__ == "__main__":
    unittest.main()
