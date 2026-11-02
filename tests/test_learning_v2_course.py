"""Offline P2 contract journey and adversarial tests against temporary SQLite/ASGI."""
import copy
import json
import unittest
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor

try:
    from .test_learning_v2_identity import Fixture, BASE, ORIGIN
except ImportError:
    from test_learning_v2_identity import Fixture, BASE, ORIGIN
from app.learning_v2 import ReviewQueue
from app.learning_v2.course import COURSE, LESSON, RUBRIC, TEMPLATE, MODEL, MAT_A, MAT_B, ref

DISC={'kind':'none_reported','note':'仅为虚构测试','child_confirmed':True,'example_source_ids':[]}


class CourseFixture(Fixture):
    def new_service(self, settings=None):
        settings=replace(settings or self.settings,course_enabled=True,mock_enabled=True,learning_queue=ReviewQueue('reviewer','虚构老师',3600,'隔离支持')) if settings is None else settings
        return super().new_service(settings)

    def setUp(self):
        super().setUp()
        self.service.provision_invitation_course(authority='synthetic-test-only')
        self.service.grant_staff('reviewer','learning_review',self.now[0]+86400,authority='synthetic-test-only')
        self.lid,self.fid=self.create(self.a)
        self.eid=self.service.grant_course_access(self.lid,COURSE,self.now[0]+86400,authority='synthetic-test-only')
        profile=self.get(f'/learners/{self.lid}/profile')
        self.enrollment=self.post(f'/learners/{self.lid}/enrollments',dict(expected_revision=profile['revision'],course_version_id=COURSE,entitlement_id=self.eid),201)
        self.enter(self.a,self.lid)
        profile=self.get(f'/learners/{self.lid}/profile')
        self.run=self.post(f'/learners/{self.lid}/runs',dict(expected_revision=profile['revision'],enrollment_id=self.enrollment['id']),201)
        self.rid_run=self.run['id']
        self.a_material=self.get(f'/courses/{COURSE}/materials/MAT_A')
        self.b_material=self.get(f'/courses/{COURSE}/materials/MAT_B')

    def get(self,path,client=None,expected=200):
        r=(client or self.a).get(BASE+path)
        self.assertEqual(r.status_code,expected,r.text)
        return r.json()

    def post(self,path,body,status=200,method='POST',client=None):
        return self.write(client or self.a,path,{'request_id':self.rid(),**body},method=method,expected=status).json()

    def fresh(self):
        self.run=self.get('/runs/'+self.rid_run)
        return self.run

    def requirements(self):
        self.req=self.post('/runs/'+self.rid_run+'/requirements',dict(expected_revision=0,material_version_id=MAT_A,facts=self.a_material['facts'],purpose='让同学了解活动',expression_preference='友好简短',source_locators=self.a_material['source_locators'],confirmed=True,help_disclosure=DISC),method='PUT')
        return self.req

    def check_body(self,stage,purpose='preflight'):
        run=self.fresh()
        return dict(expected_revision=run['revision'],lesson_version_id=LESSON,artifact_version_id=getattr(self,'art',{}).get('current_version',{}).get('id') if stage!='clarify' else None,rubric_version_id=RUBRIC,stage=stage,purpose=purpose,requirements_ref=run['current_requirements_ref'],self_check_ref=run['current_self_check_ref'] if stage=='review' else None,reflection_ref=run['current_reflection_ref'] if stage=='review' else None,transfer_attempt_ref=run['current_transfer_attempt_ref'] if stage=='review' else None,readback_ref=ref(self.rb) if stage!='clarify' and hasattr(self,'rb') else None)

    def check(self,stage,purpose='preflight'):
        return self.post('/runs/'+self.rid_run+'/checks',self.check_body(stage,purpose),201)

    def advance_one(self):
        self.requirements()
        c=self.check('clarify','preflight')
        self.assertEqual(c['progress_effect'],'none')
        self.assertEqual(self.fresh()['progress'][1]['state'],'locked')
        c=self.check('clarify','advance')
        self.assertEqual(c['outcome'],'advanced')

    def candidate(self):
        self.attempt=self.post('/runs/'+self.rid_run+'/attempts',dict(expected_revision=self.fresh()['revision'],lesson_version_id=LESSON,kind='practice',material_version_id=MAT_A,input_text='按我的要求写邀请',task_id='S2.1',requirements_ref=ref(self.req),transfer_response=None,help_disclosure=DISC),201)
        self.model=self.post('/attempts/'+self.attempt['id']+'/model-runs',dict(expected_revision=self.attempt['revision'],mode='mock',config_version=MODEL,replay_of=None),202)
        self.assertEqual(self.model['mode'],'mock'); self.assertIsNone(self.model['actual_model'])
        self.content=json.loads(self.model['output_text'])

    def save_artifact(self,revise=False):
        body=dict(expected_revision=self.get('/artifacts/'+self.art['id'])['revision'] if revise else self.fresh()['revision'],attempt_id=self.attempt['id'],attempt_revision=self.attempt['revision'],model_run_id=self.model['id'],template_version_id=TEMPLATE,help_event_ids=[],authorship='ai_candidate_edited' if revise else 'ai_candidate_unedited',content=self.content,help_disclosure=DISC)
        if revise:
            body.update(previous_artifact_version_id=self.art['current_version']['id'],change_explanation='说明一起分享故事，让同学知道活动内容。',change_intent='把邀请语写具体')
        self.art=self.post('/artifacts/'+self.art['id']+'/versions' if revise else '/runs/'+self.rid_run+'/artifacts',body,201)
        return self.art

    def readback(self):
        r=self.get('/artifacts/'+self.art['id']+'/versions/'+self.art['current_version']['id'])
        self.rb=self.post('/artifacts/'+self.art['id']+'/readbacks',dict(expected_revision=r['artifact_revision'],read_receipt_id=r['read_receipt_id']),201)
        return self.rb

    def advance_two(self):
        self.advance_one(); self.candidate(); self.save_artifact()
        c=self.check('create')
        self.assertIn('R04.readback',c['missing_evidence'])
        self.readback()
        self.assertEqual(self.check('create','advance')['outcome'],'advanced')

    def complete_evidence(self):
        self.advance_two()
        self.sc=self.post('/runs/'+self.rid_run+'/self-checks',dict(expected_revision=self.fresh()['revision'],artifact_version_id=self.art['current_version']['id'],field='place',source_locator=MAT_A+'#place',judgement='matches',reason='保存的地点与资料卡相同。生成后还要保存，再打开才是已保存作品。',help_disclosure=DISC),201)
        self.content['invitation_line']='带上你的故事书，一起来分享喜欢的故事吧！'
        self.save_artifact(True); self.readback()
        response=dict(facts=self.b_material['facts'],purpose='让同学了解纸桥挑战',expression_preference='友好简短',invitation_line='带上废纸一起试做纸桥吧！',changes=[dict(field=f,explanation='新材料中的'+f+'发生变化，不能沿用旧邀请。',source_locator=MAT_B+'#'+f) for f in ('place','preparation')],help_disclosure=DISC)
        self.transfer=self.post('/runs/'+self.rid_run+'/attempts',dict(expected_revision=self.fresh()['revision'],lesson_version_id=LESSON,kind='transfer',material_version_id=MAT_B,input_text='本人迁移练习',task_id='S3.3',requirements_ref=None,transfer_response=response,help_disclosure=DISC),201)
        self.reflection=self.post('/runs/'+self.rid_run+'/reflections',dict(expected_revision=self.fresh()['revision'],artifact_version_id=self.art['current_version']['id'],change_explanation='我把邀请语写具体，告诉同学一起分享故事。',judgement='我对照地点并打开保存版本核对。',transfer_attempt_id=self.transfer['id'],transfer_attempt_revision=self.transfer['revision'],self_check_ref=ref(self.sc),help_disclosure=DISC),201)


class CourseTests(CourseFixture, unittest.TestCase):
    def test_v3_restart_clears_v1_self_check_after_v2_human_pass(self):
        self.complete_evidence()
        v2 = self.art['current_version']
        self.assertEqual(v2['version'], 2)
        self.assertNotEqual(self.sc['artifact_version_id'], v2['id'])
        # The v1 self-check is valid for its direct successor v2.
        self.assertEqual(self.fresh()['current_self_check_ref'], ref(self.sc))
        self.assertEqual(self.check('review')['rule_result'], 'pass')
        checked = self.check('review', 'submit_review')
        self.login(self.reviewer, 'reviewer')
        case = self.get('/cases/'+checked['case_id'], self.reviewer)
        case = self.post('/cases/'+case['id']+'/claim',
                         dict(expected_revision=case['revision']), client=self.reviewer)
        evidence = self.get('/cases/'+case['id']+'/evidence', self.reviewer)
        ids = [s['ref']['source_id'] for s in evidence['sources']]
        self.post('/cases/'+case['id']+'/resolve', dict(
            expected_revision=case['revision'], target_revision=case['parent_revision'],
            decision='passed', evidence_ids=ids, note='虚构 v2 人工审核通过。',
            manual_findings=[dict(rubric_id=m, verdict='supported', source_ids=ids,
                                  note='已核对该项具体证据。') for m in ('M1','M2','M3','M4')]),
            client=self.reviewer)
        self.assertEqual(self.fresh()['progress'][2]['state'], 'passed')

        self.content['invitation_line'] = '带上喜欢的故事书，一起分享书里的精彩故事吧！'
        self.save_artifact(True)
        self.assertEqual(self.art['current_version']['version'], 3)
        current = self.fresh()
        self.assertIsNone(current['current_self_check_ref'])
        self.assertIsNone(current['current_reflection_ref'])
        self.assertTrue(current['progress'][2]['recheck_required'])
        self.assertNotEqual(current['progress'][2]['state'], 'passed')

        restarted = self.new_service()
        restarted.migrate()
        peer = self.client(self.new_app(restarted))
        self.login(peer)
        self.enter(peer, self.lid)
        self.assertEqual(self.get('/runs/'+self.rid_run, peer), current)
        self.assertEqual(self.get('/self-checks/'+self.sc['id'], peer), self.sc)
        self.assertEqual(self.get('/reflections/'+self.reflection['id'], peer), self.reflection)
        old_check = self.get('/checks/'+checked['id'], peer)
        self.assertTrue(old_check['stale'])
        self.assertEqual(old_check['human_result'], 'passed')
        with restarted.store.transaction() as con:
            history = [json.loads(r[0]) for r in con.execute(
                'SELECT body FROM learn_course_history WHERE id=? ORDER BY revision',
                (self.rid_run,))]
        self.assertEqual(history[-1], current)
        self.assertTrue(any(r['current_self_check_ref'] == ref(self.sc)
                            and r['current_reflection_ref'] == ref(self.reflection)
                            and r['progress'][2]['state'] == 'passed' for r in history))

    def test_v3_keeps_direct_v2_self_check_but_clears_v2_reflection(self):
        self.complete_evidence()
        sc_v2 = self.post('/runs/'+self.rid_run+'/self-checks', dict(
            expected_revision=self.fresh()['revision'],
            artifact_version_id=self.art['current_version']['id'], field='place',
            source_locator=MAT_A+'#place', judgement='matches',
            reason='再次对照资料核对当前版本的地点。', help_disclosure=DISC), 201)
        self.content['invitation_line'] = '一起分享书里最喜欢的故事吧！'
        self.save_artifact(True)
        current = self.fresh()
        self.assertEqual(current['current_self_check_ref'], ref(sc_v2))
        self.assertIsNone(current['current_reflection_ref'])
        self.assertEqual(self.get('/self-checks/'+sc_v2['id']), sc_v2)
        self.assertEqual(self.get('/reflections/'+self.reflection['id']), self.reflection)

    def test_complete_three_gates_human_review_and_restart(self):
        self.complete_evidence()
        c=self.check('review')
        self.assertEqual(c['rule_result'],'pass'); self.assertIsNone(c['case_id'])
        c=self.check('review','submit_review')
        self.assertEqual(c['outcome'],'awaiting_review')
        self.login(self.reviewer,'reviewer')
        case=self.get('/cases/'+c['case_id'],self.reviewer)
        case=self.post('/cases/'+case['id']+'/claim',dict(expected_revision=case['revision']),client=self.reviewer)
        sources=self.get('/cases/'+case['id']+'/evidence',self.reviewer)
        ids=[s['ref']['source_id'] for s in sources['sources']]
        case=self.post('/cases/'+case['id']+'/resolve',dict(expected_revision=case['revision'],target_revision=case['parent_revision'],decision='needs_information',evidence_ids=ids,note='请说明保存和生成有什么不同。',manual_findings=[dict(rubric_id='M2',verdict='unclear',source_ids=[self.sc['id']],note='需要具体说明')]),client=self.reviewer)
        self.assertEqual(case['status'],'claimed')
        case=self.post('/cases/'+case['id']+'/messages',dict(expected_revision=case['revision'],message='生成是候选，保存会留下版本；我打开保存版本核对。',source_ids=[self.sc['id']]))
        sources=self.get('/cases/'+case['id']+'/evidence',self.reviewer)
        ids=[s['ref']['source_id'] for s in sources['sources']]
        case=self.post('/cases/'+case['id']+'/resolve',dict(expected_revision=case['revision'],target_revision=case['parent_revision'],decision='passed',evidence_ids=ids,note='仅为模拟协议验证，按证据核对完成。',manual_findings=[dict(rubric_id=m,verdict='supported',source_ids=ids,note='已核对该项具体证据。') for m in ('M1','M2','M3','M4')]),client=self.reviewer)
        self.assertEqual(case['status'],'resolved')
        self.assertEqual(self.fresh()['progress'][2]['state'],'passed')
        new=self.new_service(); new.migrate()
        peer=self.client(self.new_app(new)); peer.cookies.update(self.a.cookies)
        self.assertEqual(self.get('/runs/'+self.rid_run,peer),self.fresh())
        self.assertEqual(self.get('/checks/'+c['id'])['human_result'],'passed')
        self.assertEqual(self.get('/artifacts/'+self.art['id'])['check_status'],'passed')

    def test_material_projection_and_default_off(self):
        for value in (self.a_material,self.b_material,self.get('/courses/'+COURSE)):
            text=json.dumps(value)
            for forbidden in ('reviewer_only','expected_','EX_B_TRANSFER','example_reason','example_changed_fields'):
                self.assertNotIn(forbidden,text)
        off=self.new_service(replace(self.service.settings,course_enabled=False))
        peer=self.client(self.new_app(off));peer.cookies.update(self.a.cookies)
        self.assertEqual(self.get('/courses',peer,503)['error']['code'],'operation_unavailable')

    def test_stage_skip_cross_family_and_server_grant(self):
        self.post('/runs/'+self.rid_run+'/attempts',dict(expected_revision=self.fresh()['revision'],lesson_version_id=LESSON,kind='practice',material_version_id=MAT_A,input_text='jump',task_id='S2.1',requirements_ref=None,transfer_response=None,help_disclosure=DISC),409)
        lid,_=self.create(self.b,'parent-b'); self.enter(self.b,lid)
        for path in ('/runs/'+self.rid_run,'/runs/'+self.rid_run+'/requirements'):
            self.get(path,self.b,404)
        self.post('/learners/'+lid+'/runs',dict(expected_revision=self.get('/learners/'+lid+'/profile',self.b)['revision'],enrollment_id=self.enrollment['id']),404,client=self.b)
        self.login(self.b,'parent-b')
        self.post('/learners/'+lid+'/enrollments',dict(expected_revision=self.get('/learners/'+lid+'/profile',self.b)['revision'],course_version_id=COURSE,entitlement_id=self.eid),403,client=self.b)

    def test_idempotency_conflict_revision_and_snapshot(self):
        self.requirements()
        body=dict(request_id=self.rid(),expected_revision=self.req['revision'],material_version_id=MAT_A,facts=self.a_material['facts'],purpose='新目的',expression_preference='简短',source_locators=self.a_material['source_locators'],confirmed=True,help_disclosure=DISC)
        path='/runs/'+self.rid_run+'/requirements'
        r=self.write(self.a,path,body,method='PUT').json()
        self.assertEqual(self.write(self.a,path,body,method='PUT').json(),r)
        self.write(self.a,path,{**body,'purpose':'不一样'},method='PUT',expected=409)
        self.write(self.a,path,{**body,'request_id':self.rid()},method='PUT',expected=409)
        with self.service.store.transaction() as con:
            rows=con.execute('SELECT body FROM learn_course_history WHERE id=? ORDER BY revision',(self.req['id'],)).fetchall()
            self.assertEqual(len(rows),2); self.assertEqual(json.loads(rows[0][0]),self.req)

    def test_read_receipt_session_bound_and_forged(self):
        self.advance_one();self.candidate();self.save_artifact()
        r=self.get('/artifacts/'+self.art['id']+'/versions/'+self.art['current_version']['id'])
        body=dict(expected_revision=r['artifact_revision'],read_receipt_id=r['read_receipt_id'])
        self.post('/artifacts/'+self.art['id']+'/readbacks',{**body,'read_receipt_id':'forged'},409)
        self.login(self.a);self.enter(self.a,self.lid)
        self.post('/artifacts/'+self.art['id']+'/readbacks',body,409)
        self.readback()

    def test_evidence_updates_invalidate_pending_review_and_old_version(self):
        self.complete_evidence(); c=self.check('review','submit_review')
        previous=self.art['current_version']
        self.content['invitation_line']='来分享书里的精彩故事吧！';self.save_artifact(True)
        self.assertTrue(self.get('/checks/'+c['id'])['stale'])
        old=self.get('/artifacts/'+self.art['id']+'/versions/'+previous['id'])
        self.assertEqual(old['artifact_version'],previous)
        self.assertEqual(self.get('/artifacts/'+self.art['id'])['check_status'],'recheck_required')
        self.assertNotEqual(self.fresh()['progress'][2]['state'],'passed')
        self.login(self.reviewer,'reviewer')
        case=self.get('/cases/'+c['case_id'],self.reviewer)
        case=self.post('/cases/'+case['id']+'/claim',dict(expected_revision=case['revision']),client=self.reviewer)
        self.post('/cases/'+case['id']+'/resolve',dict(expected_revision=case['revision'],target_revision=case['parent_revision'],decision='needs_information',evidence_ids=[self.sc['id']],note='旧证据不能通过',manual_findings=[]),409,client=self.reviewer)
        body=self.check_body('review');body['artifact_version_id']=previous['id']
        self.post('/runs/'+self.rid_run+'/checks',body,409)

    def test_no_queue_no_fake_success_and_revocation(self):
        self.complete_evidence()
        self.service.settings=replace(self.service.settings,learning_queue=None)
        c=self.check('review','submit_review')
        self.assertEqual(c['outcome'],'blocked_support');self.assertIsNone(c['case_id'])
        self.post('/runs/'+self.rid_run+'/cases',dict(expected_revision=self.fresh()['revision'],message='需要帮助',source_ids=[],reason_category='task_unclear'),503)
        self.service.revoke_course_access(self.eid,authority='synthetic-test-only')
        self.get('/runs/'+self.rid_run,expected=403)
        self.assertEqual(self.get('/learners/'+self.lid+'/home')['entitlements'][0]['status'],'revoked')

    def test_material_withdrawal_and_real_mode_blocked(self):
        self.advance_one();self.candidate()
        self.post('/attempts/'+self.attempt['id']+'/model-runs',dict(expected_revision=self.attempt['revision'],mode='live',config_version=MODEL,replay_of=None),503)
        self.service.set_material_available(COURSE,MAT_A,False,authority='synthetic-test-only')
        self.get('/courses/'+COURSE+'/materials/MAT_A',expected=409)
        self.check_body('clarify')
        self.post('/runs/'+self.rid_run+'/checks',self.check_body('clarify'),409)

class CourseBoundaryTests(CourseFixture, unittest.TestCase):
    def test_static_help_material_sources_and_history(self):
        h=self.post('/runs/'+self.rid_run+'/help',dict(expected_revision=self.fresh()['revision'],role_id='guide',help_level=3,mode='static',question='需要提示',source_ids=[MAT_A],task_id='S1.1',task_card_version='0.1.0'),202)
        self.assertEqual(h['mode'],'static');self.assertIsNone(h['model_run_id'])
        self.assertNotIn('星叶',h['text']);self.assertNotIn('expected_',json.dumps(h))
        self.assertEqual(self.get('/runs/'+self.rid_run+'/help')['items'],[h])
        self.post('/runs/'+self.rid_run+'/help',dict(expected_revision=self.fresh()['revision'],role_id='guide',help_level=1,mode='static',question='跳关',source_ids=[MAT_B],task_id='S3.3',task_card_version='0.1.0'),409)
        self.post('/runs/'+self.rid_run+'/help',dict(expected_revision=self.fresh()['revision'],role_id='guide',help_level=1,mode='static',question='越界',source_ids=['EX_B_TRANSFER'],task_id='S1.1',task_card_version='0.1.0'),422)

    def test_public_catalog_and_private_role_projection(self):
        public=self.client()
        self.assertEqual(self.get('/courses',public)['items'][0]['id'],COURSE)
        self.get('/courses/'+COURSE,public,401)
        self.advance_two()
        self.login(self.a)
        self.assertEqual(self.get('/learners/'+self.lid+'/home')['run_id'],self.rid_run)
        self.get('/runs/'+self.rid_run,expected=403)
        self.get('/attempts/'+self.attempt['id'],expected=403)
        self.get('/runs/'+self.rid_run+'/requirements',expected=403)
        self.assertEqual(self.get('/artifacts/'+self.art['id'])['id'],self.art['id'])
        self.login(self.reviewer,'reviewer')
        self.get('/artifacts/'+self.art['id'],self.reviewer,404)

    def test_concurrent_revision_and_idempotency(self):
        self.requirements()
        path='/runs/'+self.rid_run+'/requirements'
        peers=[self.client(),self.client()]
        for p in peers:p.cookies.update(self.a.cookies)
        csrf=self.bootstrap(self.a)['csrf_token']
        base=dict(expected_revision=1,material_version_id=MAT_A,facts=self.a_material['facts'],purpose='并发目的',expression_preference='简短',source_locators=self.a_material['source_locators'],confirmed=True,help_disclosure=DISC)
        def send(index,body):
            return peers[index].put(BASE+path,json=body,headers={'Origin':ORIGIN,'X-CSRF-Token':csrf})
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda pair:send(*pair),enumerate([{**base,'request_id':self.rid()},{**base,'request_id':self.rid()}])))
        self.assertEqual(sorted(r.status_code for r in results),[200,409])
        body={**base,'expected_revision':2,'request_id':self.rid()}
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda index:send(index,body),range(2)))
        self.assertEqual([r.status_code for r in results],[200,200]);self.assertEqual(results[0].json(),results[1].json())
        self.assertEqual(self.get(path)['revision'],3)

    def test_unknown_run_never_retried_or_sent_to_review(self):
        self.complete_evidence()
        with self.service.store.transaction() as con:
            model=self.service.obj(con,self.model['id'],'model')
            model.update(status='unknown',revision=model['revision']+1)
            self.service.put(con,'model',model)
        check=self.check('review','submit_review')
        self.assertEqual(check['outcome'],'blocked_unknown');self.assertEqual(check['progress_effect'],'none')
        self.post('/attempts/'+self.attempt['id']+'/model-runs',dict(expected_revision=self.attempt['revision'],mode='mock',config_version=MODEL,replay_of=None),409)
        self.post('/attempts/'+self.attempt['id'],dict(expected_revision=self.attempt['revision'],input_text='retry',task_id='S2.1',requirements_ref=ref(self.req),transfer_response=None,help_disclosure=DISC),409,method='PATCH')

    def test_wrong_facts_and_duplicate_transfer_changes_do_not_pass(self):
        self.complete_evidence()
        tr=copy.deepcopy(self.transfer['transfer_response'])
        tr['facts']['place']='松果活动室'
        tr['changes']=[tr['changes'][0],tr['changes'][0]]
        self.transfer=self.post('/attempts/'+self.transfer['id'],dict(expected_revision=self.transfer['revision'],input_text='换材料仍有错',task_id='S3.3',requirements_ref=None,transfer_response=tr,help_disclosure=DISC),method='PATCH')
        c=self.check('review')
        self.assertIn('R08.reflection',c['missing_evidence'])
        self.assertTrue(any('修正小迁移' in x for x in c['feedback']))
        self.assertTrue(any('至少两处' in x for x in c['feedback']))
        self.assertIsNone(c['case_id'])

    def test_noop_revision_and_unedited_authorship(self):
        self.advance_two()
        a=self.get('/artifacts/'+self.art['id'])
        b=dict(expected_revision=a['revision'],attempt_id=self.attempt['id'],attempt_revision=self.attempt['revision'],model_run_id=self.model['id'],help_event_ids=[],authorship='child_edit',content=self.content,change_explanation='其实没改',previous_artifact_version_id=a['current_version']['id'],change_intent='测试',help_disclosure=DISC,template_version_id=TEMPLATE)
        self.post('/artifacts/'+a['id']+'/versions',b,422)
        b['authorship']='ai_candidate_unedited'
        self.art=self.post('/artifacts/'+a['id']+'/versions',b,201)
        c=self.check('review')
        self.assertTrue(any('没有看到内容变化' in x for x in c['feedback']))

    def test_forged_manual_pass_and_queue_scope_revocation(self):
        self.complete_evidence();c=self.check('review','submit_review')
        self.login(self.reviewer,'reviewer')
        case=self.get('/cases/'+c['case_id'],self.reviewer)
        case=self.post('/cases/'+case['id']+'/claim',dict(expected_revision=case['revision']),client=self.reviewer)
        body=dict(expected_revision=case['revision'],target_revision=case['parent_revision'],decision='passed',evidence_ids=[self.sc['id']],note='仅机器检查不能通过',manual_findings=[])
        self.post('/cases/'+case['id']+'/resolve',body,422,client=self.reviewer)
        body['manual_findings']=[dict(rubric_id=m,verdict='supported',source_ids=['forged'],note='伪造来源') for m in ('M1','M2','M3','M4')]
        self.post('/cases/'+case['id']+'/resolve',body,422,client=self.reviewer)
        with self.service.store.transaction() as con:
            con.execute("DELETE FROM learn_grants WHERE actor_id='reviewer' AND scope='learning_review'")
        self.get('/cases/'+case['id']+'/evidence',self.reviewer,404)
        self.assertEqual(self.fresh()['progress'][2]['state'],'pending_review')

    def test_consent_withdrawal_stops_child_and_reviewer(self):
        self.complete_evidence();c=self.check('review','submit_review')
        manager=self.client();self.login(manager)
        consent=self.get('/learners/'+self.lid+'/consents',manager)['items'][0]
        self.post('/consents/'+consent['id']+'/revoke',dict(expected_revision=consent['revision'],reason='虚构撤回'),client=manager)
        self.get('/runs/'+self.rid_run,expected=401)
        self.login(self.reviewer,'reviewer')
        self.get('/cases/'+c['case_id']+'/evidence',self.reviewer,403)

    def test_support_extensions_transfer_and_owner_authority(self):
        self.service.settings=replace(self.service.settings,support_queue=ReviewQueue('reviewer','虚构支持老师',3600,'隔离支持'))
        self.service.grant_staff('reviewer','support',self.now[0]+86400,authority='synthetic-test-only')
        case=self.post('/runs/'+self.rid_run+'/cases',dict(expected_revision=self.fresh()['revision'],message='需要解释要求',source_ids=[MAT_A],reason_category='task_unclear'),201)
        self.login(self.reviewer,'reviewer')
        case=self.post('/cases/'+case['id']+'/claim',dict(expected_revision=case['revision']),client=self.reviewer)
        self.post('/cases/'+case['id']+'/extensions',dict(expected_revision=case['revision'],new_due_at=case['due_at'],reason='同一期限不行'),422,client=self.reviewer)
        from datetime import datetime,timezone
        due=datetime.fromtimestamp(self.now[0]+7200,timezone.utc).isoformat()
        case=self.post('/cases/'+case['id']+'/extensions',dict(expected_revision=case['revision'],new_due_at=due,reason='已安排新的处理时段'),client=self.reviewer)
        self.service.grant_staff('outsider','support',self.now[0]+86400,authority='synthetic-test-only')
        other=self.client();self.login(other,'outsider')
        self.get('/cases/'+case['id']+'/evidence',other,404)
        case=self.post('/cases/'+case['id']+'/transfer',dict(expected_revision=case['revision'],assignee_id='outsider',reason='新老师接手'),client=self.reviewer)
        self.get('/cases/'+case['id'],self.reviewer,404)
        case=self.post('/cases/'+case['id']+'/claim',dict(expected_revision=case['revision']),client=other)
        e=self.get('/cases/'+case['id']+'/evidence',other)
        case=self.post('/cases/'+case['id']+'/resolve',dict(expected_revision=case['revision'],target_revision=case['parent_revision'],decision='answered',evidence_ids=[e['sources'][0]['ref']['source_id']],note='请先从资料卡找出对象。',manual_findings=[]),client=other)
        self.assertEqual(case['status'],'resolved')
        self.assertEqual(self.fresh()['progress'][0]['state'],'available')

    def test_pending_review_deduplicated_and_current_sources_visible_to_reviewer(self):
        self.complete_evidence();c=self.check('review','submit_review')
        repeated=self.post('/runs/'+self.rid_run+'/checks',self.check_body('review','submit_review'),201)
        self.assertEqual(repeated['id'],c['id']);self.assertEqual(repeated['case_id'],c['case_id'])
        self.login(self.reviewer,'reviewer')
        self.assertEqual(self.get('/artifacts/'+self.art['id'],self.reviewer)['id'],self.art['id'])
        evidence=self.get('/cases/'+c['case_id']+'/evidence',self.reviewer)
        self.assertTrue(any('change_intent' in x['redacted_text'] for x in evidence['sources']))
        self.assertTrue(any('"mode":"mock"' in x['redacted_text'] for x in evidence['sources']))
        self.assertEqual(self.get('/self-checks/'+self.sc['id']),self.sc)
        self.assertEqual(self.get('/reflections/'+self.reflection['id']),self.reflection)

    def test_existing_run_resume_revision_and_initial_requirements(self):
        self.get('/runs/'+self.rid_run+'/requirements',expected=404)
        profile=self.get('/learners/'+self.lid+'/profile')
        resumed=self.post('/learners/'+self.lid+'/runs',dict(expected_revision=profile['revision'],enrollment_id=self.enrollment['id']),201)
        self.assertEqual(resumed,self.run)
        self.post('/learners/'+self.lid+'/runs',dict(expected_revision=profile['revision']-1,enrollment_id=self.enrollment['id']),409)
        self.requirements()
        feedback=self.check('clarify')['feedback']
        self.assertFalse(any('R0' in x or '协议' in x for x in feedback))

    def test_pending_preflight_does_not_strand_reviewer(self):
        self.complete_evidence();c=self.check('review','submit_review')
        self.check('review','preflight')
        self.assertFalse(self.get('/checks/'+c['id'])['stale'])
        self.login(self.reviewer,'reviewer')
        case=self.get('/cases/'+c['case_id'],self.reviewer)
        case=self.post('/cases/'+case['id']+'/claim',dict(expected_revision=case['revision']),client=self.reviewer)
        case=self.post('/cases/'+case['id']+'/resolve',dict(expected_revision=case['revision'],target_revision=case['parent_revision'],decision='needs_information',evidence_ids=[self.sc['id']],note='请再解释具体依据。',manual_findings=[dict(rubric_id='M2',verdict='unclear',source_ids=[self.sc['id']],note='等待本人补充')]),client=self.reviewer)
        self.assertEqual(case['status'],'claimed')

    def test_unknown_cannot_escape_via_new_attempt(self):
        self.advance_one();self.candidate()
        with self.service.store.transaction() as con:
            model=self.service.obj(con,self.model['id'],'model')
            model.update(status='unknown',revision=2)
            self.service.put(con,'model',model)
        self.post('/runs/'+self.rid_run+'/attempts',dict(expected_revision=self.fresh()['revision'],lesson_version_id=LESSON,kind='practice',material_version_id=MAT_A,input_text='试图绕过未知运行',task_id='S2.1',requirements_ref=ref(self.req),transfer_response=None,help_disclosure=DISC),409)

    def test_support_scope_and_category_deduplication(self):
        body=dict(expected_revision=self.fresh()['revision'],message='请老师解释一下',source_ids=[],reason_category='task_unclear')
        self.post('/runs/'+self.rid_run+'/cases',body,503)
        self.service.settings=replace(self.service.settings,support_queue=ReviewQueue('reviewer','虚构支持老师',3600,'隔离支持'))
        # Merely being a learning reviewer does not grant support-case authority.
        self.post('/runs/'+self.rid_run+'/cases',body,503)
        self.service.grant_staff('reviewer','support',self.now[0]+86400,authority='synthetic-test-only')
        first=self.post('/runs/'+self.rid_run+'/cases',body,201)
        second=self.post('/runs/'+self.rid_run+'/cases',{**body,'expected_revision':self.fresh()['revision']},201)
        self.assertEqual(first['id'],second['id'])


    def test_edited_input_keeps_old_model_snapshot_and_requires_new_run(self):
        self.advance_one();self.candidate()
        original=self.model
        changed=self.post('/attempts/'+self.attempt['id'],dict(expected_revision=self.attempt['revision'],input_text='补充我自己的表达选择',task_id='S2.1',requirements_ref=ref(self.req),transfer_response=None,help_disclosure=DISC),method='PATCH')
        self.assertIsNone(self.fresh()['active_model_run_id'])
        self.assertEqual(self.get('/model-runs/'+original['id']),original)
        new=self.post('/attempts/'+changed['id']+'/model-runs',dict(expected_revision=changed['revision'],mode='mock',config_version=MODEL,replay_of=None),202)
        self.assertEqual(new['input_revision'],changed['revision'])
        self.assertNotEqual(new['id'],original['id'])


if __name__=='__main__':
    unittest.main()
