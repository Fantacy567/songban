"""Real ASGI + same-transaction legacy boundary tests, synthetic SQLite only."""
import importlib.util
import inspect
import os
import sqlite3
import sys
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi import Header, Request

from app.learning_v2.integration import LegacyBoundary, _current
from app.learning_v2.protocol import Problem
from app.learning_v2.service import digest, iso
from app.studio import hash_password
try:
    from .test_learning_v2_identity import BASE, ORIGIN, PASSWORD, Fixture
except ImportError:  # unittest discover -s tests
    from test_learning_v2_identity import BASE, ORIGIN, PASSWORD, Fixture


class BoundaryTests(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.boundary = LegacyBoundary(self.service)

        @contextmanager
        def db(write=False):
            con = self.service.store.connect()
            try:
                con.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                self.boundary.check_db(con, write)
                yield con
                self.boundary.check_db(con, write)
                if write:
                    con.commit()
            except BaseException:
                con.rollback()
                raise
            finally:
                con.close()
        self.db = db
        self.read_ready, self.read_release = threading.Event(), threading.Event()
        self.dispatch_ready, self.dispatch_release = threading.Event(), threading.Event()

        @self.app.get("/api/legacy/private")
        def private():
            with db() as con:
                result = dict(con.execute("SELECT id,name FROM people WHERE id='parent-a'").fetchone())
            return result

        @self.app.get("/api/legacy/slow-read")
        def slow_read():
            with db() as con:
                value = con.execute("SELECT name FROM people WHERE id='parent-a'").fetchone()[0]
            self.read_ready.set()
            if not self.read_release.wait(5):
                raise RuntimeError("test read barrier timed out")
            return {"private": value}

        @self.app.put("/api/core/me/preferences")
        def local_write():
            with db(True) as con:
                con.execute("INSERT INTO legacy_facts VALUES('local-write')")
            return {"saved": True}

        @self.app.post("/api/legacy/external")
        def external():
            # Models/dispatch are fixture barriers, never real network calls.
            self.dispatch_ready.set()
            if not self.dispatch_release.wait(5):
                raise RuntimeError("test dispatch barrier timed out")
            with db(True) as con:
                con.execute("INSERT INTO legacy_facts VALUES('dispatch-result')")
            return {"saved": True}

        @self.app.post("/api/legacy/uncertain")
        def uncertain():
            raise Problem(503, "fixture_unknown", "虚构外部结果未知。")

        self.boundary.install(self.app)

    def headers(self):
        return {"Authorization": "Bearer old-parent-a"}

    def thread_request(self, client, method, path, **kwargs):
        result = []
        def run():
            try:
                result.append(client.request(method, path, **kwargs))
            except BaseException as exc:
                result.append(exc)
        thread = threading.Thread(target=run)
        thread.start()
        return thread, result

    def joined(self, thread, result):
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(result), 1)
        if isinstance(result[0], BaseException):
            raise result[0]
        return result[0]

    def test_entry_checks_real_bearer_and_v2_is_excluded(self):
        self.assertEqual(self.a.get("/api/legacy/private", headers={"Authorization": "Bearer stale"}).status_code, 401)
        self.assertEqual(self.a.get("/api/legacy/private", headers=self.headers()).status_code, 200)
        lid, _ = self.create(self.a)
        old = self.client()
        old.cookies.update(self.a.cookies)
        self.enter(self.a, lid)
        self.assertEqual(self.a.get(BASE+"/session").status_code, 200)
        self.assertEqual(self.a.get("/api/legacy/private", headers=self.headers()).status_code, 403)
        self.assertEqual(old.get("/api/legacy/private", headers=self.headers()).status_code, 403)
        self.assertEqual(self.b.get("/api/legacy/private", headers=self.headers()).status_code, 401)

    def test_connector_entry_and_mid_request_revocation(self):
        with self.service.store.transaction() as con:
            con.execute("CREATE TABLE core_connections(id TEXT,user_id TEXT,token_hash TEXT,paused INTEGER,revoked INTEGER,expires_at TEXT)")
            con.execute("INSERT INTO core_connections VALUES('c','parent-a',?,0,0,?)", (digest("sbconn_fixture"), iso(self.now[0]+1000)))
        thread, result = self.thread_request(self.a, "GET", "/api/legacy/slow-read", headers={"Authorization": "Bearer sbconn_fixture"})
        self.assertTrue(self.read_ready.wait(5))
        with self.service.store.transaction() as con:
            con.execute("UPDATE core_connections SET revoked=1")
        self.read_release.set()
        denied = self.joined(thread, result)
        self.assertEqual(denied.status_code, 401)
        self.assertNotIn("虚构", denied.text)

    def test_read_body_held_until_independent_final_fence(self):
        lid, _ = self.create(self.a)
        old = self.client()
        old.cookies.update(self.a.cookies)
        thread, result = self.thread_request(old, "GET", "/api/legacy/slow-read", headers=self.headers())
        self.assertTrue(self.read_ready.wait(5))
        self.enter(self.a, lid)
        self.read_release.set()
        denied = self.joined(thread, result)
        self.assertEqual(denied.status_code, 401)
        self.assertNotIn('"private"', denied.text)
        self.assertEqual(denied.headers["cache-control"], "no-store")

    def test_switch_first_rolls_back_old_write_and_context_does_not_leak(self):
        lid, _ = self.create(self.a)
        old = self.client()
        old.cookies.update(self.a.cookies)
        ready, release = threading.Event(), threading.Event()
        original = self.boundary.capture
        def delayed(scope):
            context = original(scope)
            if scope["path"] == "/api/core/me/preferences":
                ready.set()
                if not release.wait(5):
                    raise RuntimeError("test capture barrier timed out")
            return context
        with patch.object(self.boundary, "capture", delayed):
            thread, result = self.thread_request(old, "PUT", "/api/core/me/preferences", headers=self.headers())
            self.assertTrue(ready.wait(5))
            self.enter(self.a, lid)
            release.set()
            self.assertEqual(self.joined(thread, result).status_code, 401)
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM legacy_facts").fetchone()[0], 0)
        self.assertIsNone(_current.get())
        # Startup/background DB work gets no synthesized request fence.
        with self.db(True) as con:
            con.execute("INSERT INTO legacy_facts VALUES('independent-background')")

    def test_unsafe_dispatch_blocks_switch_until_http_and_work_finish(self):
        lid, _ = self.create(self.a)
        old = self.client()
        old.cookies.update(self.a.cookies)
        thread, result = self.thread_request(old, "POST", "/api/legacy/external", headers=self.headers())
        self.assertTrue(self.dispatch_ready.wait(5))
        session = self.a.get(BASE+"/session").json()
        blocked = self.write(self.a, "/sessions/enter-learner", {"request_id": self.rid(), "expected_revision": session["revision"], "learner_id": lid}, expected=409)
        self.assertEqual(blocked.json()["error"]["code"], "legacy_work_in_progress")
        self.dispatch_release.set()
        self.assertEqual(self.joined(thread, result).status_code, 200)
        self.enter(self.a, lid)

    def test_uncertain_work_survives_restart_and_needs_explicit_reconciliation(self):
        lid, _ = self.create(self.a)
        self.assertEqual(self.a.post("/api/legacy/uncertain", headers=self.headers()).status_code, 503)
        with self.service.store.transaction() as con:
            row = con.execute("SELECT id,state FROM learn_legacy_activity").fetchone()
            self.assertEqual(row[1], "unknown")
        restart = self.new_service()
        restart.migrate()
        boundary = LegacyBoundary(restart)
        with restart.store.transaction() as con:
            with self.assertRaises(Problem):
                boundary.check_switch(con, actor_id="parent-a")
        with self.assertRaises(ValueError):
            boundary.resolve_activity(row[0], authority="", evidence="")
        boundary.resolve_activity(row[0], authority="synthetic-operator", evidence="虚构核对：外部请求已结束")
        self.enter(self.a, lid)

    def test_existing_busy_records_and_automation_fail_closed_in_switch_transaction(self):
        lid, _ = self.create(self.a)
        with self.service.store.transaction() as con:
            con.execute("CREATE TABLE workbench_requests(status TEXT)")
            con.execute("INSERT INTO workbench_requests VALUES('running')")
        session = self.a.get(BASE+"/session").json()
        self.write(self.a, "/sessions/enter-learner", {"request_id": self.rid(), "expected_revision": session["revision"], "learner_id": lid}, expected=409)
        with self.service.store.transaction() as con:
            con.execute("UPDATE workbench_requests SET status='succeeded'")
            con.execute("CREATE TABLE core_settings(auto_review INTEGER)")
            con.execute("INSERT INTO core_settings VALUES(1)")
        self.write(self.a, "/sessions/enter-learner", {"request_id": self.rid(), "expected_revision": session["revision"], "learner_id": lid}, expected=409)
        with self.service.store.transaction() as con:
            con.execute("UPDATE core_settings SET auto_review=0")
        self.enter(self.a, lid)

    def test_caught_fence_error_cannot_authorize_later_commit(self):
        self.login(self.a)
        context = self.boundary.capture(self.request_for(self.a).scope)
        # This synthetic capture is local-only so no activity marker is relevant.
        token = _current.set(context)
        try:
            with self.service.store.transaction() as con:
                con.execute("UPDATE learn_auth_epochs SET epoch=epoch+1 WHERE actor_id='parent-a'")
                con.execute("UPDATE people SET token_hash='fixture-tombstone' WHERE id='parent-a'")
            with self.db(True) as con:
                pass
        except Problem:
            with self.assertRaises(Problem):
                with self.db(True) as con:
                    con.execute("INSERT INTO legacy_facts VALUES('must-not-commit')")
        finally:
            _current.reset(token)


class CreateAppTests(Fixture, unittest.TestCase):
    PREFS = {"expected_revision": 0, "interests": ["还在探索"], "skills": ["都没做过，想试试"], "time": "半天", "experience": "虚构经历"}
    def load_main(self):
        # app.main calls load_env and app=create_app at import. Both are confined
        # here to a temporary DB, with private config loader replaced before exec.
        path = Path(__file__).resolve().parents[1] / "app/main.py"
        module_name = "app._learning_v2_integration_main"
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {"DATABASE_PATH": str(Path(self.tmp.name)/"import.sqlite3")}, clear=True), patch("app.environment.load_env", return_value=None):
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            finally:
                sys.modules.pop(module_name, None)
        self.assertIn("learning_settings", inspect.signature(module.create_app).parameters,
                      "S00 create_app learning_settings interface is not ready")
        module.now = lambda: iso(self.now[0])
        return module.create_app

    def full_app(self, enabled=True):
        create_app = self.load_main()
        path = Path(self.tmp.name)/("full-enabled.sqlite3" if enabled else "full-default.sqlite3")
        with patch.dict(os.environ, {}, clear=True):
            api = create_app(db_path=path, core_only=False, enforce_journey=False,
                             **({"learning_settings": self.settings, "parent_report_options": {"runner": lambda context: {}}} if enabled else {}))
        if not enabled:
            return api
        self.path, self.app = path, api
        self.service = api.state.learning_v2
        self.service.clock = lambda: self.now[0]
        self.boundary = api.state.learning_legacy_boundary
        with self.service.store.transaction() as con:
            password_hash = hash_password(PASSWORD)
            for person in ("parent-a", "parent-b", "reviewer"):
                con.execute("INSERT INTO people(id,phone,name,token_hash,created_at,password_hash,username,email) VALUES(?,?,?,?,?,?,?,?)",
                            (person, "fiction:"+person, "虚构", digest("old-"+person), iso(self.now[0]), password_hash, person, person+"@example.test"))
        self.service.grant_staff("reviewer", "relationship_review", self.now[0]+86400, authority="synthetic-test")
        self.service.grant_staff("reviewer", "consent_read", self.now[0]+86400, authority="synthetic-test")
        self.service.put_consent_text(self.text, authority="synthetic-test")
        self.a, self.b, self.reviewer = self.client(), self.client(), self.client()
        return api

    def test_default_factory_preserves_legacy_and_does_not_register_v2(self):
        api = self.full_app(False)
        c = self.client(api)
        self.assertEqual(c.get(BASE+"/config").status_code, 404)
        # Invalid Authorization on a public endpoint keeps pre-integration behavior.
        self.assertEqual(c.get("/api/learning/v1/events", headers={"Authorization": "Bearer stale"}).status_code, 200)

    def test_real_factory_child_mode_blocks_all_old_issuers_and_domains(self):
        self.full_app()
        # Column names are checked against the schema built by real create_app,
        # including optional parent_report, rather than a claimed production DB.
        with self.service.store.transaction() as con:
            for table, column, states in self.boundary.BUSY:
                self.assertTrue(self.boundary.table_exists(con, table), table)
                self.assertIn(column, {r[1] for r in con.execute(f"PRAGMA table_info({table})")}, table)
        self.assertEqual(self.a.get("/api/core/me", headers={"Authorization": "Bearer old-parent-a"}).status_code, 200)
        lid, _ = self.create(self.a)
        self.enter(self.a, lid)
        paths = [("GET", "/api/core/me"), ("GET", "/api/studio/account"), ("GET", "/api/materials/spaces"),
                 ("GET", "/api/workbench/sessions"), ("POST", "/api/studio/login"), ("POST", "/api/studio/register"),
                 ("POST", "/api/studio/login-email"), ("POST", "/api/core/guest-session"), ("POST", "/api/projects"),
                 ("GET", "/api/core/teams/fake/recap"), ("POST", "/api/core/teams/fake/parent-report")]
        for method, path in paths:
            with self.subTest(path=path):
                denied = self.a.request(method, path, json={}, headers={"Authorization": "Bearer sbconn_fake"})
                self.assertEqual(denied.status_code, 403, denied.text)
                self.assertEqual(denied.json()["error"]["code"], "child_mode_restricted")
        self.assertEqual(self.a.get(BASE+"/session").status_code, 200)

    def test_real_preferences_switch_first_has_no_side_effect(self):
        self.full_app()
        lid, _ = self.create(self.a)
        old = self.client()
        old.cookies.update(self.a.cookies)
        ready, release = threading.Event(), threading.Event()
        original = self.boundary.capture
        def delayed(scope):
            context = original(scope)
            if scope["path"] == "/api/core/me/preferences":
                ready.set()
                if not release.wait(5):
                    raise RuntimeError("test capture barrier timeout")
            return context
        result = []
        def write_old():
            result.append(old.put("/api/core/me/preferences", json=self.PREFS, headers={"Authorization": "Bearer old-parent-a"}))
        with patch.object(self.boundary, "capture", delayed):
            thread = threading.Thread(target=write_old)
            thread.start()
            self.assertTrue(ready.wait(5))
            self.enter(self.a, lid)
            release.set()
            thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0].status_code, 401, result[0].text)
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM core_starting_preferences WHERE user_id='parent-a'").fetchone()[0], 0)

    def test_real_preferences_commit_first_retains_fact(self):
        self.full_app()
        lid, _ = self.create(self.a)
        old = self.client()
        old.cookies.update(self.a.cookies)
        ready, release, switching = threading.Event(), threading.Event(), threading.Event()
        original, counts = self.boundary.check_db, {}
        def checked(con, write):
            original(con, write)
            context = _current.get()
            if write and context and context.path == "/api/core/me/preferences":
                counts[con] = counts.get(con, 0)+1
                if counts[con] == 2:
                    ready.set()
                    if not release.wait(5):
                        raise RuntimeError("test commit barrier timeout")
        csrf = self.bootstrap(self.a)["csrf_token"]
        session = self.a.get(BASE+"/session").json()
        body = {"request_id": self.rid(), "expected_revision": session["revision"], "learner_id": lid}
        old_result, switch_result = [], []
        def write_old():
            old_result.append(old.put("/api/core/me/preferences", json=self.PREFS, headers={"Authorization": "Bearer old-parent-a"}))
        def enter():
            switching.set()
            switch_result.append(self.a.post(BASE+"/sessions/enter-learner", json=body, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}))
        with patch.object(self.boundary, "check_db", checked):
            writer = threading.Thread(target=write_old)
            writer.start()
            self.assertTrue(ready.wait(5))
            switcher = threading.Thread(target=enter)
            switcher.start()
            self.assertTrue(switching.wait(5))
            release.set()
            writer.join(10)
            switcher.join(10)
        self.assertFalse(writer.is_alive() or switcher.is_alive())
        self.assertIn(old_result[0].status_code, (200, 401))
        self.assertEqual(switch_result[0].status_code, 200, switch_result[0].text)
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute("SELECT revision FROM core_starting_preferences WHERE user_id='parent-a'").fetchone()[0], 1)

    def test_real_read_response_is_discarded_after_switch(self):
        self.full_app()
        lid, _ = self.create(self.a)
        old = self.client()
        old.cookies.update(self.a.cookies)
        ready, release = threading.Event(), threading.Event()
        original = self.boundary.finish
        def delayed(context, **kwargs):
            if context.path == "/api/core/me" and kwargs.get("validate", True):
                ready.set()
                if not release.wait(5):
                    raise RuntimeError("test read response barrier timeout")
            return original(context, **kwargs)
        result = []
        with patch.object(self.boundary, "finish", delayed):
            thread = threading.Thread(target=lambda: result.append(old.get("/api/core/me", headers={"Authorization": "Bearer old-parent-a"})))
            thread.start()
            self.assertTrue(ready.wait(5))
            self.enter(self.a, lid)
            release.set()
            thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0].status_code, 401)
        self.assertNotIn('"profile"', result[0].text)

    def test_real_old_password_login_and_guest_issuance_still_work_before_switch(self):
        self.full_app()
        response = self.a.post("/api/studio/login", json={"account": "parent-a", "password": PASSWORD}, headers={"Authorization": "Bearer old-parent-a"})
        self.assertEqual(response.status_code, 200, response.text)
        token = response.json()["token"]
        self.assertEqual(self.a.get("/api/core/me", headers={"Authorization": "Bearer "+token}).status_code, 200)
        self.assertEqual(self.b.post("/api/core/guest-session").status_code, 201)
        stale = self.client()
        renewed = stale.post("/api/studio/login", json={"account": "parent-a", "password": PASSWORD}, headers={"Authorization": "Bearer old-parent-a"})
        self.assertEqual(renewed.status_code, 200, renewed.text)

    def test_real_email_login_and_team_connection_regression(self):
        self.full_app()
        with self.service.store.transaction() as con:
            con.execute("INSERT INTO email_codes VALUES(?,?,'login','',?,?,'sent',0)",
                        ("synthetic-challenge", "parent-a@example.test", digest("synthetic-challenge:parent-a@example.test:login::123456"), iso(self.now[0]+3600)))
        logged = self.a.post("/api/studio/login-email", json={"email": "parent-a@example.test", "code": "123456"})
        self.assertEqual(logged.status_code, 200, logged.text)
        header = {"Authorization": "Bearer "+logged.json()["token"]}
        team = self.a.post("/api/core/teams", json={"name": "虚构联调队"}, headers=header)
        self.assertEqual(team.status_code, 200, team.text)
        sid = team.json()["id"]
        connection = self.a.post(f"/api/core/teams/{sid}/connections", json={"label": "虚构连接"}, headers=header)
        self.assertEqual(connection.status_code, 200, connection.text)
        connector = {"Authorization": "Bearer "+connection.json()["token"]}
        self.assertEqual(self.a.get(f"/api/core/teams/{sid}/context", headers=connector).status_code, 200)
        self.assertEqual(self.a.get(f"/api/core/teams/{sid}", headers=header).status_code, 200)
        # Actual preset preferences remain reachable without learning onboarding.
        prefs = self.a.put("/api/core/me/preferences", json=self.PREFS, headers=header)
        self.assertEqual(prefs.status_code, 200, prefs.text)

    def test_migrated_database_requires_explicit_paused_settings_on_rollback(self):
        from dataclasses import replace
        self.full_app()
        lid, _ = self.create(self.a)
        self.enter(self.a, lid)
        create_app = self.load_main()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                create_app(db_path=self.path, core_only=False, enforce_journey=False)
            paused = create_app(db_path=self.path, core_only=False, enforce_journey=False,
                                learning_settings=replace(self.settings, enabled=False))
        paused.state.learning_v2.clock = lambda: self.now[0]
        c = self.client(paused)
        c.cookies.update(self.a.cookies)
        self.assertFalse(c.get(BASE+"/config").json()["learning_enabled"])
        self.assertIsNotNone(paused.state.learning_legacy_boundary)
        self.assertEqual(c.get(BASE+f"/learners/{lid}/start").status_code, 200)
        self.assertEqual(c.get("/api/core/me", headers={"Authorization": "Bearer old-parent-a"}).status_code, 403)
        self.write(c, f"/learners/{lid}/start", {"request_id": self.rid(), "expected_revision": 0,
                   "answers": {"interests": {"state": "skipped", "value": None}}}, method="PATCH", expected=423)

    def family_pair(self):
        self.full_app()
        lid_a, _ = self.create(self.a)
        lid_b, _ = self.create(self.b, "parent-b")
        teams = []
        for client, actor in ((self.a, "parent-a"), (self.b, "parent-b")):
            response = client.post("/api/core/teams", json={"name": "虚构隔离队"}, headers={"Authorization": "Bearer old-"+actor})
            self.assertEqual(response.status_code, 200, response.text)
            teams.append(response.json()["id"])
        return lid_a, lid_b, teams[0], teams[1]

    def blocked_enter(self, client, learner):
        session = client.get(BASE+"/session").json()
        return self.write(client, "/sessions/enter-learner", {"request_id": self.rid(), "expected_revision": session["revision"], "learner_id": learner}, expected=409)

    def add_busy(self, con, table, values):
        columns = ",".join(values)
        con.execute(f"INSERT INTO {table}({columns}) VALUES({','.join('?' for _ in values)})", tuple(values.values()))

    def busy_fixtures(self, team):
        stamp = iso(self.now[0])
        return [
            ("workbench_requests", "status", "pending", {"id": "busy-wb", "request_id": "fixture-wb-request", "session_id": "fixture-wb", "owner_id": "parent-a", "fingerprint": "fixture", "source_refs": "[]", "context_fingerprint": "fixture", "lease_token": "fixture", "lease_until": "2000-01-01T00:00:00+00:00", "created_at": stamp, "updated_at": stamp}),
            ("materials_batches", "status", "running", {"id": "busy-materials", "space_id": "fixture-space", "request_id": "fixture-materials-request", "fingerprint": "fixture", "requester_id": "parent-a", "input_revision": 1, "inputs": "{}", "created_at": stamp}),
            ("recap_reports", "status", "running", {"id": "busy-recap", "squad_id": team, "user_id": "parent-a", "request_id": "fixture-recap-request", "fingerprint": "fixture", "reflection_version": 1, "sources": "[]", "created_at": stamp}),
            ("parent_reports", "state", "pending", {"user_id": "parent-a", "squad_id": team, "request_id": "fixture-parent-request", "request_hash": "fixture", "created_at": stamp}),
            ("idea_rankings", "status", "running", {"id": "busy-ideas", "squad_id": team, "request_id": "fixture-ideas-request", "fingerprint": "fixture", "created_at": stamp}),
            ("division_rounds", "status", "running", {"id": "busy-division", "squad_id": team, "fingerprint": "fixture", "updated_at": stamp}),
            ("core_topic_rounds", "phase", "ranking", {"id": "busy-topic", "squad_id": team, "revision": 1, "body": "{}", "created_at": stamp, "updated_at": stamp}),
        ]

    def test_each_real_busy_owner_or_team_blocks_a_but_not_unrelated_b(self):
        lid_a, lid_b, team_a, _ = self.family_pair()
        with self.service.store.transaction() as con:
            self.add_busy(con, "workbench_sessions", {"id": "fixture-wb", "owner_id": "parent-a", "title": "虚构", "request_id": "fixture-session", "fingerprint": "fixture", "created_at": iso(self.now[0]), "updated_at": iso(self.now[0])})
            self.add_busy(con, "materials_spaces", {"id": "fixture-space", "owner_id": "parent-a"})
        for table, column, active, values in self.busy_fixtures(team_a):
            for state in (active, "unknown"):
                with self.subTest(table=table, state=state):
                    with self.service.store.transaction() as con:
                        self.add_busy(con, table, {**values, column: state})
                    self.blocked_enter(self.a, lid_a)
                    self.assertEqual(self.enter(self.b, lid_b)["mode"], "learner")
                    self.login(self.b, "parent-b")
                    # Remove only this synthetic, never-dispatched fixture.
                    with self.service.store.transaction() as con:
                        con.execute(f"DELETE FROM {table}")

    def test_active_and_unknown_request_scope_and_original_browser(self):
        lid_a, lid_b, _, _ = self.family_pair()
        ready, release = threading.Event(), threading.Event()
        @self.app.post("/api/ownership/external")
        def external():
            ready.set()
            if not release.wait(5):
                raise RuntimeError("fixture dispatch timeout")
            raise Problem(503, "fixture_unknown", "虚构未知结果")
        result = []
        thread = threading.Thread(target=lambda: result.append(self.a.post("/api/ownership/external", headers={"Authorization": "Bearer old-parent-a"})))
        thread.start()
        self.assertTrue(ready.wait(5))
        self.blocked_enter(self.a, lid_a)
        self.enter(self.b, lid_b)
        self.login(self.b, "parent-b")
        release.set()
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0].status_code, 503)
        # A pre-M01C record still has its original trusted actor, so upgrading
        # does not force its unrelated family back into a global block.
        with self.service.store.transaction() as con:
            con.execute("DELETE FROM learn_legacy_activity_scopes WHERE activity_id IN (SELECT id FROM learn_legacy_activity WHERE state='unknown')")
        self.blocked_enter(self.a, lid_a)
        self.enter(self.b, lid_b)
        # Switching accounts in the original browser cannot evade its old work.
        self.login(self.a, "parent-b")
        self.blocked_enter(self.a, lid_b)

    def test_unknown_missing_owner_or_orphan_team_remains_global(self):
        lid_a, lid_b, _, team_b = self.family_pair()
        @self.app.post("/api/ownership/anonymous")
        def anonymous():
            raise Problem(503, "fixture_unknown", "虚构匿名未知任务")
        anonymous_client = self.client()
        self.assertEqual(anonymous_client.post("/api/ownership/anonymous").status_code, 503)
        self.blocked_enter(self.a, lid_a)
        self.blocked_enter(self.b, lid_b)
        with self.service.store.transaction() as con:
            ident = con.execute("SELECT id FROM learn_legacy_activity WHERE state='unknown'").fetchone()[0]
        self.boundary.resolve_activity(ident, authority="synthetic-operator", evidence="虚构任务已结束")
        with self.service.store.transaction() as con:
            # No snapshot: an original actor cannot be used to excuse historical
            # work on a team whose authorized relationship is no longer proved.
            con.execute("INSERT INTO learn_legacy_activity VALUES('legacy-unproven-team','parent-a',NULL,'POST',?,'unknown',?,NULL,NULL)",
                        (f"/api/core/teams/{team_b}/fixture-unknown", iso(self.now[0])))
        self.blocked_enter(self.a, lid_a)
        self.blocked_enter(self.b, lid_b)
        self.boundary.resolve_activity("legacy-unproven-team", authority="synthetic-operator", evidence="虚构历史任务已结束")
        with self.service.store.transaction() as con:
            self.add_busy(con, "idea_rankings", {"id": "orphan-task", "squad_id": "missing-squad", "request_id": "fixture-orphan", "fingerprint": "fixture", "status": "unknown", "created_at": iso(self.now[0])})
        self.blocked_enter(self.a, lid_a)
        self.blocked_enter(self.b, lid_b)

    def test_automation_and_connector_team_snapshot_isolated_and_persistent(self):
        lid_a, lid_b, team_a, _ = self.family_pair()
        with self.service.store.transaction() as con:
            con.execute("INSERT INTO people(id,phone,name,token_hash,created_at) VALUES('fixture-peer','fiction:peer','虚构队友','fixture-peer-hash',?)", (iso(self.now[0]),))
            con.execute("INSERT INTO squad_members(squad_id,user_id) VALUES(?,'fixture-peer')", (team_a,))
            con.execute("UPDATE core_settings SET auto_review=1 WHERE squad_id=?", (team_a,))
        self.blocked_enter(self.a, lid_a)
        self.enter(self.b, lid_b)
        self.login(self.b, "parent-b")
        connection = self.a.post(f"/api/core/teams/{team_a}/connections", json={"label": "虚构连接"}, headers={"Authorization": "Bearer old-parent-a"})
        self.assertEqual(connection.status_code, 200, connection.text)
        # Even a normal request started with automation on preserves a scoped
        # uncertainty marker; disable fixture automation without declaring it done.
        with self.service.store.transaction() as con:
            con.execute("UPDATE core_settings SET auto_review=0 WHERE squad_id=?", (team_a,))
        self.blocked_enter(self.a, lid_a)
        self.enter(self.b, lid_b)
        self.login(self.b, "parent-b")
        @self.app.post("/api/core/teams/{sid}/fixture-unknown")
        def unknown(sid: str):
            raise Problem(503, "fixture_unknown", "虚构连接器任务未知")
        connector_client = self.client()
        self.assertEqual(connector_client.post(f"/api/core/teams/{team_a}/fixture-unknown", headers={"Authorization": "Bearer "+connection.json()["token"]}).status_code, 503)
        # Original roster survives removal. No TTL or status fabrication releases it.
        with self.service.store.transaction() as con:
            con.execute("DELETE FROM squad_members WHERE squad_id=? AND user_id='fixture-peer'", (team_a,))
            with self.assertRaises(Problem):
                self.boundary.check_switch(con, actor_id="fixture-peer")
        restart = self.new_service()
        restart.migrate()
        boundary = LegacyBoundary(restart)
        with restart.store.transaction() as con:
            with self.assertRaises(Problem):
                boundary.check_switch(con, actor_id="parent-a")
            boundary.check_switch(con, actor_id="parent-b")
            con.execute("INSERT INTO squad_members(squad_id,user_id) VALUES(?,'parent-b')", (team_a,))
            with self.assertRaises(Problem):
                boundary.check_switch(con, actor_id="parent-b")

    def test_shared_materials_uses_space_team_not_just_requester(self):
        lid_a, lid_b, team_a, _ = self.family_pair()
        with self.service.store.transaction() as con:
            con.execute("INSERT INTO people(id,phone,name,token_hash,created_at) VALUES('fixture-peer','fiction:peer','虚构队友','fixture-peer-hash',?)", (iso(self.now[0]),))
            con.execute("INSERT INTO squad_members(squad_id,user_id) VALUES(?,'fixture-peer')", (team_a,))
            self.add_busy(con, "materials_spaces", {"id": "fixture-space", "team_id": team_a})
            table, column, active, values = self.busy_fixtures(team_a)[1]
            self.add_busy(con, table, {**values, column: active})
            with self.assertRaises(Problem):
                self.boundary.check_switch(con, actor_id="fixture-peer")
        self.blocked_enter(self.a, lid_a)
        self.enter(self.b, lid_b)

    def test_committed_team_task_keeps_dispatch_roster_after_request_and_restart(self):
        lid_a, lid_b, team_a, _ = self.family_pair()
        with self.service.store.transaction() as con:
            con.execute("INSERT INTO people(id,phone,name,token_hash,created_at) VALUES('fixture-peer','fiction:peer','虚构队友','fixture-peer-hash',?)", (iso(self.now[0]),))
            con.execute("INSERT INTO squad_members(squad_id,user_id) VALUES(?,'fixture-peer')", (team_a,))
        route = next(r for r in self.app.routes if getattr(r, "path", "") == "/api/core/me/preferences")
        legacy_db = inspect.getclosurevars(route.endpoint).nonlocals["db"]
        @self.app.post("/api/core/teams/{sid}/fixture-task")
        def task(sid: str):
            with legacy_db(True) as con:
                self.add_busy(con, "idea_rankings", {"id": "persisted-task", "squad_id": sid, "request_id": "fixture-committed", "fingerprint": "fixture", "status": "unknown", "created_at": iso(self.now[0])})
            return {"status": "unknown"}
        created = self.a.post(f"/api/core/teams/{team_a}/fixture-task", headers={"Authorization": "Bearer old-parent-a"})
        self.assertEqual(created.status_code, 200, created.text)
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM learn_legacy_activity WHERE state IN ('active','unknown')").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT count(*) FROM learn_legacy_task_scopes WHERE table_name='idea_rankings'").fetchone()[0], 1)
            con.execute("DELETE FROM squad_members WHERE squad_id=? AND user_id='fixture-peer'", (team_a,))
            with self.assertRaises(Problem):
                self.boundary.check_switch(con, actor_id="fixture-peer")
        restart = self.new_service()
        restart.migrate()
        boundary = LegacyBoundary(restart)
        with restart.store.transaction() as con:
            with self.assertRaises(Problem):
                boundary.check_switch(con, actor_id="fixture-peer")
            boundary.check_switch(con, actor_id="parent-b")
        self.blocked_enter(self.a, lid_a)
        self.enter(self.b, lid_b)

    def test_private_task_with_invalid_owner_stays_unattributed_and_blocks_both(self):
        lid_a, lid_b, team_a, _ = self.family_pair()
        with self.service.store.transaction() as con:
            self.add_busy(con, "workbench_sessions", {"id": "fixture-wb", "owner_id": "parent-a", "title": "虚构", "request_id": "fixture-session", "fingerprint": "fixture", "created_at": iso(self.now[0]), "updated_at": iso(self.now[0])})
            table, column, active, values = self.busy_fixtures(team_a)[0]
            self.add_busy(con, table, {**values, column: active, "owner_id": "unknown-deleted-person"})
        self.blocked_enter(self.a, lid_a)
        self.blocked_enter(self.b, lid_b)


if __name__ == "__main__":
    unittest.main()
