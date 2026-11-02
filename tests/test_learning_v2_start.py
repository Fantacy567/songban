"""Persistent per-topic drafts and explicit choice semantics; no model calls."""
import json
import unittest
import threading
from dataclasses import replace

try:
    from .test_learning_v2_identity import BASE, ORIGIN, Fixture
except ImportError:  # unittest discover -s tests
    from test_learning_v2_identity import BASE, ORIGIN, Fixture


class StartTests(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.lid, _ = self.create(self.a)
        self.enter(self.a, self.lid)
        self.url = f"/learners/{self.lid}/start"

    def save(self, answers, rev, request_id=None, expected=200):
        return self.write(self.a, self.url, {"request_id": request_id or self.rid(), "expected_revision": rev, "answers": answers}, method="PATCH", expected=expected)

    def test_blank_one_topic_restore_restart_and_immutable_history(self):
        blank = self.a.get(BASE+self.url).json()
        self.assertEqual(blank["revision"], 0)
        self.assertEqual(len(blank["missing_fields"]), 6)
        self.assertEqual(blank["effective_start_source"], "conservative_fallback")
        self.assertEqual(blank["answers"]["chosen_start"], {"state": "unanswered", "value": None})
        saved = self.save({"age_band": {"state": "skipped", "value": None}}, 0).json()
        self.assertEqual(saved["skipped_fields"], ["age_band"])
        self.assertEqual(saved["completion_status"], "draft")
        restart = self.new_service()
        restart.migrate()
        new_client = self.client(self.new_app(restart))
        new_client.cookies.update(self.a.cookies)
        self.assertEqual(new_client.get(BASE+self.url).json(), saved)
        self.save({"interests": {"state": "answered", "value": []}}, 1)
        self.save({"age_band": {"state": "unanswered", "value": None}}, 2)
        current = self.a.get(BASE+self.url).json()
        self.assertEqual(current["answers"]["interests"]["state"], "answered")
        self.assertIn("age_band", current["missing_fields"])
        with self.service.store.transaction() as con:
            history = [json.loads(r[0]) for r in con.execute("SELECT body FROM learn_start_history WHERE learner_id=? ORDER BY revision", (self.lid,))]
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0], saved)

    def test_idempotency_normalization_and_conflicts(self):
        rid = self.rid()
        first = self.save({"experience": {"state": "answered", "value": "some"}}, 0, rid)
        replay = self.save({"experience": {"value": "some", "state": "answered"}}, 0, rid)
        self.assertEqual(first.json(), replay.json())
        self.assertEqual(first.headers["X-Request-ID"], rid)
        self.save({"experience": {"state": "answered", "value": "none"}}, 0, rid, expected=409)
        self.save({"mini_attempt_text": {"state": "answered", "value": "给虚构同学的邀请"}}, 0, expected=409)
        self.assertEqual(self.a.get(BASE+self.url).json()["revision"], 1)

    def test_explicit_acceptance_separate_and_stale(self):
        self.save({"chosen_start": {"state": "accepted_default", "value": "guided", "recommendation_revision": 0}, "experience": {"state": "answered", "value": "some"}}, 0, expected=422)
        accepted = self.save({"chosen_start": {"state": "accepted_default", "value": "guided", "recommendation_revision": 0}}, 0).json()
        self.assertEqual(accepted["effective_start_source"], "accepted_default")
        self.assertEqual(accepted["answers"]["chosen_start"]["recommendation_revision"], 0)
        self.save({"chosen_start": {"state": "accepted_default", "value": "guided", "recommendation_revision": 0}}, 1, expected=409)
        self.save({"chosen_start": {"state": "accepted_default", "value": "challenge", "recommendation_revision": 1}}, 1, expected=409)
        self.save({"chosen_start": {"state": "answered", "value": "challenge"}}, 1)
        result = self.save({"experience": {"state": "answered", "value": "none"}}, 2).json()
        self.assertEqual(result["recommendation"], "guided")
        self.assertEqual(result["effective_start"], "challenge")
        self.assertEqual(result["effective_start_source"], "learner_choice")

    def test_skips_not_answers_or_capability_and_age_not_ability(self):
        blank = self.a.get(BASE+self.url).json()
        all_skipped = {k: {"state": "skipped", "value": None} for k in blank["answers"]}
        value = self.save(all_skipped, 0).json()
        self.assertEqual(value["completion_status"], "completed_with_skips")
        self.assertEqual(value["mini_attempt_status"], "skipped")
        self.assertEqual(value["effective_start_source"], "conservative_fallback")
        young = self.save({"age_band": {"state": "answered", "value": "fixture-younger"}, "chosen_start": {"state": "answered", "value": "challenge"}}, 1).json()
        older = self.save({"age_band": {"state": "answered", "value": "fixture-older"}}, 2).json()
        for field in ("recommendation", "recommendation_basis", "effective_start"):
            self.assertEqual(young[field], older[field])
        self.save({"age_band": {"state": "answered", "value": "unconfigured-age"}}, 3, expected=422)

    def test_strict_input_and_no_fabricated_assessment(self):
        for answer in ({"state": "answered", "value": ""}, {"state": "answered", "value": "   "}, {"state": "answered", "value": None}, {"state": "skipped", "value": "text"}):
            self.save({"mini_attempt_text": answer}, 0, expected=422)
        self.save({}, 0, expected=422)
        self.save({"unknown": {"state": "answered", "value": "x"}}, 0, expected=422)
        result = self.save({"experience": {"state": "answered", "value": "regular"}, "mini_attempt_text": {"state": "answered", "value": "一条真实保存的虚构练习答案"}}, 0).json()
        self.assertEqual(result["mini_attempt_status"], "answered")
        self.assertEqual(result["recommendation_basis"], "insufficient_evidence")
        self.assertEqual(result["recommendation_source_fields"], [])

    def test_disabled_keeps_history_and_reauthentication(self):
        saved = self.save({"mini_attempt_text": {"state": "answered", "value": "暂停前保存"}}, 0).json()
        paused = self.new_service(replace(self.settings, enabled=False))
        c = self.client(self.new_app(paused))
        c.cookies.update(self.a.cookies)
        self.assertEqual(c.get(BASE+self.url).json(), saved)
        self.write(c, self.url, {"request_id": self.rid(), "expected_revision": 1, "answers": {"interests": {"state": "skipped", "value": None}}}, method="PATCH", expected=423)
        self.assertEqual(self.login(c)["mode"], "manager")
        self.assertEqual(c.get(BASE+self.url).status_code, 403)

    def test_competing_topic_writes_and_same_request_converge(self):
        peers = [self.client(), self.client()]
        for peer in peers:
            peer.cookies.update(self.a.cookies)
        csrf = self.bootstrap(self.a)["csrf_token"]
        def concurrent(bodies):
            barrier = threading.Barrier(2)
            responses, errors = [], []
            def send(index):
                try:
                    barrier.wait(timeout=5)
                    responses.append(peers[index].patch(BASE+self.url, json=bodies[index], headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}))
                except BaseException as exc:
                    errors.append(str(exc))
            threads = [threading.Thread(target=send, args=(i,)) for i in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(10)
            self.assertTrue(all(not t.is_alive() for t in threads))
            self.assertEqual(errors, [])
            return responses
        bodies = [{"request_id": self.rid(), "expected_revision": 0, "answers": {"experience": {"state": "answered", "value": v}}} for v in ("some", "regular")]
        responses = concurrent(bodies)
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        body = {"request_id": self.rid(), "expected_revision": 1, "answers": {"interests": {"state": "answered", "value": ["虚构兴趣"]}}}
        responses = concurrent([body, body])
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assertEqual(self.a.get(BASE+self.url).json()["revision"], 2)


if __name__ == "__main__":
    unittest.main()
