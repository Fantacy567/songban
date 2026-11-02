"""S10 independent P4 acceptance: real SQLite/ASGI; no provider/network/env.

Fixture provenance: S04 Fixture, S06 CourseFixture, S08 ModelFixture and
S09 ReportTests setup/helpers. load_tests selects ONLY methods defined here;
inherited historical tests are not counted as independent acceptance evidence.
"""
import copy
import unittest
from dataclasses import replace

try:
    from . import test_learning_v2_reports as reports_fixture
    from .test_learning_v2_course import CourseFixture
    from .test_learning_v2_models import ModelFixture
    from .test_learning_v2_identity import BASE, Fixture
except ImportError:
    import test_learning_v2_reports as reports_fixture
    from test_learning_v2_course import CourseFixture
    from test_learning_v2_models import ModelFixture
    from test_learning_v2_identity import BASE, Fixture

from app.learning_v2.integration import LegacyBoundary
from app.learning_v2.course import COURSE, MAT_A


def stopped(settings):
    return replace(settings, enabled=False, course_enabled=False,
                   models_enabled=False, reports_enabled=False,
                   publication_enabled=False)


class AcceptanceIdentityTests(Fixture, unittest.TestCase):
    def test_start_each_topic_survives_restart_and_explicit_choice_wins(self):
        lid, _ = self.create(self.a)
        self.enter(self.a, lid)
        path = '/learners/'+lid+'/start'
        draft = self.a.get(BASE+path).json()
        self.assertEqual(len(draft['missing_fields']), 6)
        for field in draft['answers']:
            body = dict(request_id=self.rid(), expected_revision=draft['revision'],
                        answers={field: {'state': 'skipped', 'value': None}})
            draft = self.write(self.a, path, body, method='PATCH').json()
            restarted = self.new_service(); restarted.migrate()
            peer = self.client(self.new_app(restarted)); peer.cookies.update(self.a.cookies)
            self.assertEqual(peer.get(BASE+path).json(), draft)
        self.assertEqual(draft['completion_status'], 'completed_with_skips')
        chosen = self.write(self.a, path, dict(request_id=self.rid(),
            expected_revision=draft['revision'], answers={
                'chosen_start': {'state': 'answered', 'value': 'challenge'},
                'experience': {'state': 'answered', 'value': 'none'}}), method='PATCH').json()
        self.assertEqual(chosen['effective_start'], 'challenge')
        self.assertEqual(chosen['effective_start_source'], 'learner_choice')
        self.assertEqual(chosen['recommendation'], 'guided')
        self.write(self.a, path, dict(request_id=self.rid(),
            expected_revision=draft['revision'], answers={
                'experience': {'state': 'answered', 'value': 'regular'}}), method='PATCH', expected=409)
        self.assertEqual(self.a.get(BASE+path).json(), chosen)

    def test_old_cookie_and_bearer_stay_revoked_after_password_reauthentication(self):
        boundary = LegacyBoundary(self.service)
        boundary.install(self.app)

        @self.app.get('/api/legacy/s10-probe')
        def probe():
            return {'fixture': 'private'}

        lid, fid = self.create(self.a)
        old = self.client()
        old.cookies.update(self.a.cookies)
        self.enter(self.a, lid)
        self.assertEqual(old.get(BASE+'/session').status_code, 401)
        self.assertEqual(old.get(BASE+'/families/'+fid).status_code, 401)
        denied = self.a.get('/api/legacy/s10-probe', headers={'Authorization': 'Bearer old-parent-a'})
        self.assertEqual(denied.status_code, 403)
        self.assertNotIn('private', denied.text)
        self.login(self.a)
        self.assertEqual(self.a.get(BASE+'/families/'+fid).status_code, 200)
        self.assertEqual(old.get(BASE+'/session').status_code, 401)
        naked = self.client()
        denied = naked.get('/api/legacy/s10-probe', headers={'Authorization': 'Bearer old-parent-a'})
        self.assertEqual(denied.status_code, 401)


class AcceptanceReportTests(reports_fixture.ReportTests):
    def test_learning_human_review_then_report_approval_keeps_distinct_evidence(self):
        self.login(self.reviewer, 'reviewer')
        case = self.get('/cases/'+self.checked['case_id'], self.reviewer)
        case = self.post('/cases/'+case['id']+'/claim', dict(expected_revision=case['revision']), client=self.reviewer)
        evidence = self.get('/cases/'+case['id']+'/evidence', self.reviewer)
        ids = [source['ref']['source_id'] for source in evidence['sources']]
        self.post('/cases/'+case['id']+'/resolve', dict(
            expected_revision=case['revision'], target_revision=case['parent_revision'],
            decision='passed', evidence_ids=ids, note='仅合成身份的人工流程验证',
            manual_findings=[dict(rubric_id=criterion, verdict='supported', source_ids=ids,
                                 note='虚构学习依据已逐项核对') for criterion in ('M1', 'M2', 'M3', 'M4')]), client=self.reviewer)
        self.assertEqual(self.fresh()['progress'][2]['state'], 'passed')
        with self.service.store.transaction() as con:
            model_count = len(self.service.objects(con, 'model', run=self.rid_run))
        self.published()
        visible = self.get('/reports/'+self.report['id'], self.parent)
        self.assertEqual(visible['status'], 'published')
        self.assertFalse(visible['evidence_changed'])
        with self.service.store.transaction() as con:
            snapshot = self.service.report_snapshot(con, self.report)
            self.assertTrue(any(s['ref']['nature'] == 'human_review' for s in snapshot['sources']))
            self.assertEqual(len(self.service.objects(con, 'model', run=self.rid_run)), model_count+1)
        self.assertEqual(self.get('/artifacts/'+self.art['id'])['current_version']['version'], 2)

    def test_material_withdraw_restore_does_not_resurrect_old_approval(self):
        self.make_report(); self.send_report(); self.claim(); self.approve()
        self.service.set_material_available(COURSE, MAT_A, False, authority='synthetic-only')
        self.publish(409)
        self.service.set_material_available(COURSE, MAT_A, True, authority='synthetic-only')
        self.publish(409)
        self.assertTrue(self.read_report()['evidence_changed'])
        self.assertTrue(self.get('/checks/'+self.checked['id'])['stale'])
        self.assertEqual(self.get('/artifacts/'+self.art['id'])['current_version']['content'], self.content)

    def test_cross_family_resource_graph_is_hidden_for_parent_and_child(self):
        self.published()
        lid, _ = self.create(self.b, 'parent-b')
        shared = ['/artifacts/'+self.art['id'],
                  '/artifacts/'+self.art['id']+'/versions/'+self.art['current_version']['id'],
                  '/checks/'+self.checked['id'],
                  '/reports/'+self.report['id'],
                  '/learners/'+self.lid+'/reports',
                  '/learners/'+self.lid+'/artifacts']
        for role in ('parent', 'child'):
            if role == 'child':
                self.enter(self.b, lid)
            for path in shared:
                with self.subTest(role=role, path=path):
                    response = self.b.get(BASE+path)
                    self.assertEqual(response.status_code, 404, response.text)
                    self.assertEqual(response.json()['error']['code'], 'resource_not_found')
                    self.assertNotIn(self.content['invitation_line'], response.text)
        for path in ('/runs/'+self.rid_run, '/attempts/'+self.attempt['id'],
                     '/model-runs/'+self.model['id'], '/reflections/'+self.reflection['id'],
                     '/self-checks/'+self.sc['id'], '/cases/'+self.case['id']):
            with self.subTest(child_path=path):
                self.get(path, self.b, 404)

    def test_current_single_child_limit_preserves_existing_family_data(self):
        self.published()
        family = self.get('/families/'+self.fid, self.parent)
        denied = self.post('/families/'+self.fid+'/learners', dict(
            expected_revision=family['revision'], display_name='虚构小柏',
            age_band=None, declared_relationship='仅隔离测试声明'), 409, client=self.parent)
        self.assertEqual(denied['error']['code'], 'learner_exists')
        self.assertEqual(self.get('/families/'+self.fid, self.parent), family)
        self.assertEqual(self.get('/reports/'+self.report['id'], self.parent)['status'], 'published')

    def test_draft_pending_and_approved_remain_private_after_restart(self):
        self.make_report()
        for state in ('draft', 'pending', 'approved'):
            if state == 'pending':
                self.send_report()
            elif state == 'approved':
                self.claim(); self.approve()
            restarted = self.new_service(self.service.settings)
            restarted.migrate()
            parent = self.client(self.new_app(restarted))
            self.login(parent)
            with self.subTest(state=state):
                self.get('/reports/'+self.report['id'], parent, 404)
                self.assertEqual(self.get('/learners/'+self.lid+'/reports', parent)['items'], [])

    def test_http_duplicate_report_body_conflict_does_not_create_extra_model(self):
        body = dict(request_id=self.rid(), expected_revision=self.fresh()['revision'],
                    reflection_id=self.reflection['id'], artifact_version_id=self.art['current_version']['id'],
                    check_id=self.checked['id'], mode='mock')
        path = '/runs/'+self.rid_run+'/reports'
        first = self.write(self.a, path, body, expected=202).json()
        repeated = self.write(self.a, path, body, expected=202).json()
        self.assertEqual(first, repeated)
        conflict = self.write(self.a, path, {**body, 'mode': 'replay'}, expected=409).json()
        self.assertEqual(conflict['error']['code'], 'idempotency_conflict')
        with self.service.store.transaction() as con:
            self.assertEqual(len(self.service.objects(con, 'report', run=self.rid_run)), 1)
            self.assertEqual(sum(m['report_id'] == first['id'] for m in self.service.objects(con, 'model')), 1)

    def test_new_artifact_after_approval_restart_rejects_publication(self):
        self.make_report(); self.send_report(); self.claim(); self.approve()
        old = copy.deepcopy(self.report)
        self.content['invitation_line'] = '这次修改后必须重新检查再发布报告。'
        self.save_artifact(True)
        restarted = self.new_service(self.service.settings)
        restarted.migrate()
        staff = self.client(self.new_app(restarted))
        self.login(staff, 'reviewer')
        response = self.post('/reports/'+old['id']+'/publications', dict(
            expected_revision=old['revision'], review_id=old['review_id'],
            source_hash=old['source_hash']), 409, client=staff)
        self.assertEqual(response['error']['code'], 'evidence_stale')
        with restarted.store.transaction() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM learn_report_publications').fetchone()[0], 0)
        self.assertEqual(self.get('/artifacts/'+self.art['id'])['current_version']['content'], self.content)

    def test_consent_revocation_invalidates_cached_report_creation(self):
        body = dict(request_id=self.rid(), expected_revision=self.fresh()['revision'],
                    reflection_id=self.reflection['id'], artifact_version_id=self.art['current_version']['id'],
                    check_id=self.checked['id'], mode='mock')
        path = '/runs/'+self.rid_run+'/reports'
        created = self.write(self.a, path, body, expected=202).json()
        self.post('/consents/'+self.summary['id']+'/revoke', dict(
            expected_revision=self.summary['revision'], reason='隔离测试撤回授权'), client=self.parent)
        response = self.write(self.a, path, body, expected=401)
        self.assertNotIn(created['source_hash'], response.text)
        with self.service.store.transaction() as con:
            self.assertEqual(self.service.obj(con, created['id'])['status'], 'revoked')

    def test_all_stopped_restart_keeps_report_read_and_revocation_idempotent(self):
        self.published()
        restarted = self.new_service(stopped(self.service.settings))
        restarted.migrate()
        parent = self.client(self.new_app(restarted))
        self.login(parent)
        report = self.get('/reports/'+self.report['id'], parent)
        self.assertEqual(report['status'], 'published')
        body = dict(request_id=self.rid(), expected_revision=report['revision'], reason='停写时撤回')
        path = '/reports/'+report['id']+'/revocations'
        a = self.write(parent, path, body).json()
        b = self.write(parent, path, body).json()
        self.assertEqual(a, b)
        self.get('/reports/'+report['id'], parent, 410)
        self.assertEqual(self.get('/learners/'+self.lid+'/reports', parent)['items'], [])
        with restarted.store.transaction() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM learn_report_revocations').fetchone()[0], 1)
            self.assertEqual(con.execute('SELECT count(*) FROM learn_report_publications').fetchone()[0], 1)

    def test_all_stopped_restart_keeps_saved_artifact_readable(self):
        # S10-F01: report availability is not a substitute for the saved work.
        self.published()
        # Control: pausing only new writes already preserves these reads.
        paused = self.new_service(replace(self.service.settings, enabled=False))
        paused.migrate()
        reader = self.client(self.new_app(paused)); self.login(reader)
        paths = ('/artifacts/'+self.art['id'],
                 '/artifacts/'+self.art['id']+'/versions/'+self.art['current_version']['id'],
                 '/learners/'+self.lid+'/artifacts')
        for path in paths:
            self.get(path, reader)
        self.write(reader, '/families', dict(request_id=self.rid()), expected=423)
        restarted = self.new_service(stopped(self.service.settings))
        restarted.migrate()
        parent = self.client(self.new_app(restarted))
        self.login(parent)
        for path in paths:
            with self.subTest(path=path):
                self.get(path, parent)


class AcceptanceModelTests(ModelFixture, unittest.TestCase):
    def test_unknown_restart_pause_reconcile_duplicate_never_redispatches(self):
        value = self.unknown()
        before = self.account()
        restarted = self.new_service(stopped(self.service.settings))
        restarted.migrate()
        staff = self.client(self.new_app(restarted))
        self.login(staff, 'reviewer')
        case = self.get('/reconciliation-cases/'+value['reconciliation_case_id'], staff)
        self.assertTrue(case['owner_display_name'])
        self.assertTrue(case['due_at'])
        self.assertIsNone(case['resolution'])
        self.assertEqual(restarted.process_model_jobs(), 0)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.account()['held'], before['held'])
        restarted.record_reconciliation_evidence(case['id'], evidence_id='s10-no-charge',
            settled_units=0, confirms_no_charge=True, authority='synthetic-offline-only')
        body = dict(request_id=self.rid(), expected_revision=case['revision'],
            resolution='confirmed_no_charge', evidence_ids=['s10-no-charge'],
            settled_units=0, adjustment_units=None, reason='虚构已核查未收费')
        path = '/reconciliation-cases/'+case['id']+'/resolve'
        first = self.write(staff, path, body).json()
        self.assertEqual(first, self.write(staff, path, body).json())
        self.assertEqual(first['status'], 'resolved')
        again = self.new_service(stopped(self.service.settings)); again.migrate()
        self.assertEqual(again.process_model_jobs(), 0)
        self.assertEqual(self.account()['held'], 0)
        self.assertEqual(len(self.calls), 1)
        with again.store.transaction() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM learn_model_ledger').fetchone()[0], 1)

    def test_all_stopped_reconciliation_staff_can_read_linked_model_metadata(self):
        # S10-F02: details needed for unknown reconciliation must survive stop.
        value = self.unknown()
        self.login(self.reviewer, 'reviewer')
        before = self.get('/model-runs/'+value['id'], self.reviewer)
        self.assertIsNone(before['output_text'])
        restarted = self.new_service(stopped(self.service.settings)); restarted.migrate()
        staff = self.client(self.new_app(restarted)); self.login(staff, 'reviewer')
        self.get('/reconciliation-cases/'+value['reconciliation_case_id'], staff)
        after = self.get('/model-runs/'+value['id'], staff)
        self.assertEqual(after['status'], 'unknown')
        self.assertIsNone(after['output_text'])

    def test_unknown_family_and_unassigned_staff_cannot_read_or_resolve(self):
        value = self.unknown()
        self.create(self.b, 'parent-b')
        self.get('/learners/'+self.lid+'/usage', self.b, 404)
        self.get('/reconciliation-cases/'+value['reconciliation_case_id'], self.b, 403)
        outsider = self.client(); self.login(outsider, 'outsider')
        self.get('/reconciliation-cases/'+value['reconciliation_case_id'], outsider, 404)
        self.get('/model-runs/'+value['id'], outsider, 404)
        self.post('/reconciliation-cases/'+value['reconciliation_case_id']+'/resolve', dict(
            expected_revision=1, resolution='confirmed_no_charge', evidence_ids=['fake'],
            settled_units=0, adjustment_units=None, reason='越权核对测试'), 404, client=outsider)
        self.assertEqual(self.account()['held'], 17600)
        self.assertEqual(self.account()['settled'], 0)

    def test_identity_switch_after_queue_prevents_provider_dispatch(self):
        value = self.queue()
        self.login(self.a)
        restarted = self.new_service(self.service.settings); restarted.migrate()
        self.assertEqual(restarted.process_model_jobs(), 1)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.account()['held'], 0)
        with restarted.store.transaction() as con:
            saved = restarted.obj(con, value['id'], 'model')
            self.assertEqual(saved['status'], 'failed')
            self.assertIsNone(saved['output_text'])
            self.assertEqual(con.execute('SELECT settlement_kind FROM learn_model_ledger').fetchone()[0], 'confirmed_not_dispatched')


def load_tests(loader, standard_tests, pattern):
    suite = unittest.TestSuite()
    for cls in (AcceptanceIdentityTests, AcceptanceReportTests, AcceptanceModelTests):
        suite.addTests(cls(name) for name in sorted(cls.__dict__) if name.startswith('test_'))
    return suite


if __name__ == '__main__':
    unittest.main()
