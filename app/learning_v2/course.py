"""P2 isolated course domain. Explicit provisioning, SQLite evidence, no external I/O."""
import hashlib
import json
import secrets
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from .protocol import Problem, canonical, fail, revision

COURSE = 'invitation-course@0.1.0'
LESSON = 'class-activity-invitation@0.1.0'
RUBRIC = 'invitation-rubric@0.1.0'
TEMPLATE = 'invitation-template@0.1.0'
MODEL = 'invitation-mock@0.1.0'
MAT_A, MAT_B = 'MAT_A@0.1.0', 'MAT_B@0.1.0'
STAGES = ('clarify', 'create', 'review')
FACTS = ('event_name', 'audience', 'date', 'start_time', 'end_time', 'place', 'preparation')
REFS = {'requirements_ref': 'requirements', 'self_check_ref': 'self', 'reflection_ref': 'reflection', 'transfer_attempt_ref': 'attempt', 'readback_ref': 'readback'}
DDL = '''
CREATE TABLE learn_course_objects (id TEXT PRIMARY KEY, kind TEXT NOT NULL, learner_id TEXT REFERENCES learn_learners(id), run_id TEXT, revision INTEGER NOT NULL, body TEXT NOT NULL, private TEXT NOT NULL);
CREATE INDEX learn_course_owner ON learn_course_objects(learner_id,kind,run_id);
CREATE TABLE learn_course_history (id TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL, private TEXT NOT NULL, PRIMARY KEY(id,revision));
CREATE TABLE learn_course_grants (id TEXT PRIMARY KEY, learner_id TEXT NOT NULL REFERENCES learn_learners(id), course_id TEXT NOT NULL, expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE learn_course_receipts (id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES learn_sessions(id), artifact_id TEXT NOT NULL, version_id TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE learn_course_materials (course_id TEXT NOT NULL, material_id TEXT NOT NULL, available INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(course_id,material_id));
'''


def ident():
    return secrets.token_hex(16)


def ref(v):
    return {'id': v['id'], 'revision': v['revision']}


def norm(v):
    return ''.join(unicodedata.normalize('NFKC', v).split())


def action(kind, rid, label):
    return {'type': kind, 'resource_id': rid, 'label': label}


class CourseDomain:
    COURSE_OPS = set('enroll home courses course createRun run createAttempt attempt saveAttempt createModelRun modelRun help helps createArtifact artifacts artifact versionArtifact checkArtifact check reflect askHuman transferCase requirements saveRequirements selfCheck readVersion readback extendCase appendCase material getSelfCheck getReflection'.split())
    COURSE_READ_OPS = set('home course run attempt modelRun helps artifacts artifact check requirements readVersion material getSelfCheck getReflection'.split())

    def stamp(self):
        return datetime.fromtimestamp(self.clock(), timezone.utc).isoformat(timespec='seconds')

    def migrate_course(self):
        checksum = hashlib.sha256(DDL.encode()).hexdigest()
        with self.store.transaction() as con:
            old = con.execute("SELECT checksum FROM learn_migrations WHERE version='M02'").fetchone()
            if old:
                if old[0] != checksum:
                    raise ValueError('M02 checksum mismatch')
                return
            for sql in DDL.split(';'):
                if sql.strip():
                    con.execute(sql)
            con.execute("INSERT INTO learn_migrations VALUES('M02',?,?)", (checksum, self.stamp()))

    def obj(self, con, oid, kind=None):
        row = con.execute('SELECT * FROM learn_course_objects WHERE id=?', (oid,)).fetchone()
        if not row or (kind and row['kind'] != kind):
            fail(404, 'resource_not_found', '找不到可访问的记录。')
        return json.loads(row['body'])

    def meta(self, con, oid):
        return json.loads(con.execute('SELECT private FROM learn_course_objects WHERE id=?', (oid,)).fetchone()[0])

    def put(self, con, kind, value, lid=None, run=None, private=None):
        old = con.execute('SELECT * FROM learn_course_objects WHERE id=?', (value['id'],)).fetchone()
        if old:
            lid, run = old['learner_id'], old['run_id']
            if private is None:
                private = json.loads(old['private'])
        private = private or {}
        body, extra = canonical(value), canonical(private)
        con.execute('INSERT INTO learn_course_objects VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,body=excluded.body,private=excluded.private', (value['id'], kind, lid, run, value.get('revision', 1), body, extra))
        con.execute('INSERT INTO learn_course_history VALUES(?,?,?,?)', (value['id'], value.get('revision', 1), body, extra))
        return value

    def objects(self, con, kind, *, lid=None, run=None):
        sql, args = 'SELECT body FROM learn_course_objects WHERE kind=?', [kind]
        if lid is not None:
            sql += ' AND learner_id=?'; args.append(lid)
        if run is not None:
            sql += ' AND run_id=?'; args.append(run)
        return [json.loads(r[0]) for r in con.execute(sql+' ORDER BY rowid', args)]

    def course_handles(self, con, op, params):
        if op in self.COURSE_OPS:
            return True
        if not self.settings.course_enabled and not con.execute("SELECT 1 FROM learn_course_objects WHERE kind IN ('run','artifact','case') LIMIT 1").fetchone():
            return False
        if op == 'cases':
            return True
        if op in ('case', 'caseEvidence', 'claimCase', 'resolveCase'):
            return con.execute("SELECT 1 FROM learn_course_objects WHERE id=? AND kind='case'", (params['case_id'],)).fetchone() is not None
        return False

    def course_guard(self):
        if not self.settings.course_enabled:
            fail(503, 'operation_unavailable', '课程尚未开放。', 'contact_support')

    def entitlement(self, con, eid, lid, course):
        row = con.execute('SELECT * FROM learn_course_grants WHERE id=? AND learner_id=? AND course_id=?', (eid, lid, course)).fetchone()
        if not row or row['revoked'] or row['expires'] <= self.clock():
            fail(403, 'entitlement_required', '课程授权尚未建立、已到期或已撤回。', 'contact_support')
        return row

    def owned(self, con, session, oid, kind=None):
        row = con.execute('SELECT * FROM learn_course_objects WHERE id=?', (oid,)).fetchone()
        if not row or (kind and row['kind'] != kind):
            fail(404, 'resource_not_found', '找不到可访问的记录。')
        if session['mode'] == 'staff':
            if row['kind'] not in ('artifact', 'check'):
                fail(404, 'resource_not_found', '找不到可访问的记录。')
            self.assigned_run(con, session, row['run_id'])
        else:
            self.learner(con, session, row['learner_id'])
        self.learning_access(con, row['learner_id'])
        value = json.loads(row['body'])
        run = value if row['kind'] == 'run' else self.obj(con, row['run_id'], 'run') if row['run_id'] else None
        if run:
            e = self.obj(con, run['enrollment_id'], 'enrollment')
            self.entitlement(con, e['entitlement_id'], e['learner_id'], e['course_version_id'])
        return value

    def run_for(self, con, obj):
        return obj if 'progress' in obj else self.obj(con, obj['run_id'], 'run')

    def stage(self, run, stage):
        if run['progress'][STAGES.index(stage)]['state'] == 'locked':
            fail(409, 'stage_locked', '请先完成前一步的检查。', 'reload')

    def active_material(self, con, course, mid):
        row = con.execute('SELECT * FROM learn_course_materials WHERE course_id=? AND material_id=?', (course, mid)).fetchone()
        if not row or not row['available']:
            fail(409, 'source_unavailable', '材料暂不可读取，草稿已保留。', 'contact_support')
        return json.loads(row['body'])

    def evidence(self, con, run, reference, kind):
        value = self.obj(con, reference['id'], kind)
        row = con.execute('SELECT run_id FROM learn_course_objects WHERE id=?', (value['id'],)).fetchone()
        if row['run_id'] != run['id']:
            fail(404, 'resource_not_found', '找不到可访问的依据。')
        revision(reference['revision'], value.get('revision', 1))
        return value

    def disclosure(self, value):
        if value['example_source_ids']:
            fail(422, 'invalid_sources', '本期没有开放可引用样例，请保留实际帮助说明。')

    def sources(self, con, run, ids, kind=None):
        for sid in ids:
            if kind is None and sid in (MAT_A, MAT_B):
                self.active_material(con, run['course_version_id'], sid)
                if sid == MAT_B:
                    self.stage(run, 'review')
                continue
            row = con.execute('SELECT kind,run_id FROM learn_course_objects WHERE id=?', (sid,)).fetchone()
            if not row or row['run_id'] != run['id'] or (kind and row['kind'] != kind):
                fail(422, 'invalid_sources', '只能引用本次学习已保存的依据。')

    def course_authorize(self, con, op, session, params, body):
        if op not in ('claimCase', 'resolveCase'):
            self.course_guard()
        if op in ('claimCase', 'resolveCase', 'transferCase', 'extendCase', 'appendCase'):
            self.learning_case(con, session, params['case_id'], staff=op != 'appendCase')
            return
        self.role(session, 'manager' if op == 'enroll' else 'learner')
        if 'learner_id' in params:
            self.learner(con, session, params['learner_id'])
            self.learning_access(con, params['learner_id'])
        for key, kind in (('run_id', 'run'), ('attempt_id', 'attempt'), ('artifact_id', 'artifact')):
            if key in params:
                self.owned(con, session, params[key], kind)
        if op == 'enroll':
            self.entitlement(con, body['entitlement_id'], params['learner_id'], body['course_version_id'])
        if op == 'readback':
            receipt = con.execute('SELECT session_id,expires FROM learn_course_receipts WHERE id=?', (body['read_receipt_id'],)).fetchone()
            if not receipt or receipt['session_id'] != session['id'] or receipt['expires'] <= self.clock():
                fail(409, 'invalid_read_receipt', '请在当前学习会话重新打开作品。', 'reload')

    def update_run(self, con, run, *, invalidate=False, from_stage='review'):
        run['revision'] += 1
        if invalidate:
            for check in self.objects(con, 'check', run=run['id']):
                if not check['stale'] and STAGES.index(check['stage']) >= STAGES.index(from_stage):
                    check['stale'] = True; check['revision'] += 1
                    self.put(con, 'check', check)
            p = run['progress'][2]
            if p['state'] != 'locked':
                p.update(state='in_progress', recheck_required=True, check_id=None)
            if run['current_artifact_id']:
                art = self.obj(con, run['current_artifact_id'], 'artifact')
                if art['check_status'] != 'recheck_required':
                    art.update(check_status='recheck_required', revision=art['revision']+1, parent_revision=run['revision'])
                    self.put(con, 'artifact', art)
        current = next((p for p in run['progress'] if p['state'] not in ('passed', 'locked')), run['progress'][-1])
        pending = current['state'] == 'pending_review'
        run['current_action'] = action('wait_review' if pending else 'continue_run', run['id'], '查看老师检查进展' if pending else {'clarify':'确认我的要求','create':'生成并保存作品','review':'检查、改进并解释'}[current['stage']])
        run['allowed_actions'] = ['help', 'askHuman', 'saveRequirements', 'checkArtifact']
        if run['progress'][1]['state'] != 'locked':
            run['allowed_actions'] += ['createAttempt', 'createArtifact', 'versionArtifact']
        if run['progress'][2]['state'] != 'locked':
            run['allowed_actions'] += ['selfCheck', 'reflect']
        return self.put(con, 'run', run)

    def course_read(self, con, op, session, params, query):
        # Reads keep their ownership/consent checks below. Course shutdown blocks
        # new operations, not access to previously saved evidence.
        if op == 'courses':
            self.course_guard()  # The public catalog is not a historical record.
        if op == 'cases':
            self.role(session, 'staff', 'learner')
            rows = []
            if session['mode'] == 'staff':
                if 'relationship_review' in self.scopes(con, session['actor_id']):
                    rows += [self.case_view(r) for r in con.execute('SELECT * FROM learn_cases WHERE assignee_id=? ORDER BY due_at,id', (session['actor_id'],)) if self.link(con, r['learner_id'])['actor_id'] != session['actor_id']]
                candidates = self.objects(con, 'case')
            else:
                candidates = self.objects(con, 'case', lid=session['learner_id'])
            for case in candidates:
                try:
                    if case['kind'] == 'report_review':
                        rows.append(self.report_read(con, 'case', session, {'case_id': case['id']}, {}))
                    else:
                        rows.append(self.case_projection(self.learning_case(con, session, case['id']), session))
                except Problem as exc:
                    if exc.status not in (403, 404, 410):
                        raise
            rows.sort(key=lambda c: (c['due_at'], c['id']))
            rows, cursor = self.page(con, session, 'cases', rows, query)
            return {'items': [self.case_projection(c, session) for c in rows], 'next_cursor': cursor}
        if op in ('case', 'caseEvidence'):
            c = self.learning_case(con, session, params['case_id'], staff=op == 'caseEvidence')
            if op == 'case':
                return self.case_projection(c, session)
            meta = self.meta(con, c['id'])
            return {'case_id': c['id'], 'target_revision': c['parent_revision'], 'sources': meta['evidence']}
        if op == 'courses':
            rows, cursor = self.page(con, session, 'courses', self.objects(con, 'course'), query)
            return {'items': rows, 'next_cursor': cursor}
        roles = ('manager', 'learner', 'staff') if op in ('course', 'artifact', 'check', 'readVersion') else ('manager', 'learner') if op in ('home', 'artifacts') else ('learner', 'staff') if op == 'material' else ('learner',)
        self.role(session, *roles)
        if op in ('courses', 'course', 'material'):
            if op == 'courses':
                rows, cursor = self.page(con, session, 'courses', self.objects(con, 'course'), query)
                return {'items': rows, 'next_cursor': cursor}
            course = self.obj(con, params['course_version_id'], 'course')
            if op == 'course':
                return course
            mid = params['material_id']
            if '@' not in mid:
                mid += '@0.1.0'
            if session['mode'] == 'staff':
                if not any(r['course_version_id'] == course['id'] and self.has_assigned_run(con, session, r['id']) for r in self.objects(con, 'run')):
                    fail(404, 'resource_not_found', '找不到可访问的材料。')
            return self.active_material(con, course['id'], mid)
        if op == 'home':
            learner = self.learner(con, session, params['learner_id'])
            enrollments = self.objects(con, 'enrollment', lid=learner['id'])
            for e in enrollments:
                grant = con.execute('SELECT * FROM learn_course_grants WHERE id=?', (e['entitlement_id'],)).fetchone()
                e['status'] = 'revoked' if grant['revoked'] else 'expired' if grant['expires'] <= self.clock() else 'active'
            active_ids = {e['id'] for e in enrollments if e['status'] == 'active'}
            runs = [r for r in self.objects(con, 'run', lid=learner['id']) if r['enrollment_id'] in active_ids]
            run = runs[-1] if runs else None
            return {'learner_id': learner['id'], 'revision': run['revision'] if run else learner['revision'], 'current_action': run['current_action'] if run else action('start_run' if active_ids else 'contact_support', None, '开始邀请卡练习' if active_ids else '请家长查看课程开启方式'), 'run_id': run['id'] if run else None, 'progress': run['progress'] if run else [], 'entitlements': enrollments, 'allowed_actions': ['createRun'] if active_ids and not run else ['run'] if run else [], 'missing_fields': self.start(con, learner)['missing_fields']}
        if op == 'artifacts':
            self.learner(con, session, params['learner_id'])
            self.learning_access(con, params['learner_id'])
            rows = self.objects(con, 'artifact', lid=params['learner_id'])
            for row in rows:
                self.owned(con, session, row['id'], 'artifact')
            rows, cursor = self.page(con, session, params['learner_id']+':artifacts', rows, query)
            return {'items': rows, 'next_cursor': cursor}
        if op in ('helps', 'requirements'):
            run = self.owned(con, session, params['run_id'], 'run')
            if op == 'helps':
                rows, cursor = self.page(con, session, run['id']+':helps', self.objects(con, 'help', run=run['id']), query)
                return {'items': rows, 'next_cursor': cursor}
            if run['current_requirements_ref']:
                return self.obj(con, run['current_requirements_ref']['id'], 'requirements')
            fail(404, 'resource_not_found', '还没有保存要求草稿。')
        if op == 'readVersion':
            art = self.owned(con, session, params['artifact_id'], 'artifact')
            v = self.obj(con, params['version_id'], 'version')
            if v['artifact_id'] != art['id']:
                fail(404, 'resource_not_found', '找不到可访问的版本。')
            receipt = ident()
            con.execute('INSERT INTO learn_course_receipts VALUES(?,?,?,?,?)', (receipt, session['id'], art['id'], v['id'], min(session['expires'], self.clock()+600)))
            return {'artifact_version': v, 'read_receipt_id': receipt, 'artifact_revision': art['revision']}
        mapping = {'run': ('run_id','run'), 'attempt': ('attempt_id','attempt'), 'modelRun': ('model_run_id','model'), 'artifact': ('artifact_id','artifact'), 'check': ('check_id','check'), 'getSelfCheck': ('self_check_id','self'), 'getReflection': ('reflection_id','reflection')}
        key, kind = mapping[op]
        return self.owned(con, session, params[key], kind)

    def blank_requirements(self, run):
        return {'id': run['id']+'-requirements', 'revision': 0, 'run_id': run['id'], 'material_version_id': MAT_A, 'facts': {f:'' for f in FACTS}, 'purpose':'', 'expression_preference':'', 'source_locators':[], 'confirmed':False, 'help_disclosure': {'kind':'unknown','note':'','child_confirmed':False,'example_source_ids':[]}, 'parent_revision':run['revision'], 'saved_at':self.meta_time(run)}

    def meta_time(self, run):
        # Stable epoch for a not-yet-saved draft; no fabricated save event.
        return '1970-01-01T00:00:00+00:00'

    def provision_invitation_course(self, *, authority):
        if not authority:
            raise ValueError('Explicit authority required')
        goals = {'clarify':'说清要求','create':'操作与保存','review':'检查改进与解释'}
        cards=[]
        for task in ('S1.1','S1.2','S2.1','S2.2','S3.1','S3.2','S3.3','S3.4'):
            stage=STAGES[int(task[1])-1]
            cards.append({'id':task,'version':'0.1.0','stage':stage,'goal':goals[stage],'instructions':[{'clarify':'从材料找事实，再确认目的和表达偏好。','create':'看要求、生成候选、保存作品，再打开确认。','review':'对照材料检查，亲自改一处，换材料解释。'}[stage]],'material_version_ids':[MAT_B if task=='S3.3' else MAT_A],'tool_card_ids':['invitation-text-tool'],'rubric_version_id':RUBRIC,'help_levels':['先找材料中对应的一行。','把事实和你的想法分开写。','局部骨架：我修改了___，因为___。']})
        course={'id':COURSE,'revision':1,'title':'班级活动邀请卡（模拟练习）','state':'published','lesson_version_ids':[LESSON],'task_cards':cards,'tool_cards':[{'id':'invitation-text-tool','version':'0.1.0','steps':['查看已保存要求','模拟生成候选','选择并保存作品'],'prompt_template':'依据本人已确认要求生成邀请卡候选；不得新增材料外事实。','checks':['对照活动资料','保存后打开同一版本'],'notice':'P2 模拟工具，无真实模型调用。配置 invitation-mock@0.1.0；固定模板 invitation-template@0.1.0。'}]}
        with self.store.transaction() as con:
            if not con.execute('SELECT 1 FROM learn_course_objects WHERE id=?',(COURSE,)).fetchone():
                self.put(con,'course',course)
                for m in json.loads(Path(__file__).with_name('invitation_materials.json').read_text(encoding='utf-8')):
                    con.execute('INSERT INTO learn_course_materials VALUES(?,?,1,?)',(COURSE,m['id']+'@'+m['version'],canonical(m)))
                self.audit(con,None,'course_fixture_provisioned',COURSE,{'authority':authority,'mode':'mock'})
        return COURSE

    def grant_course_access(self, learner_id, course_version_id, expires_at, *, authority):
        if not authority or expires_at <= self.clock():
            raise ValueError('Explicit authority and future expiry required')
        with self.store.transaction() as con:
            self.obj(con,course_version_id,'course')
            eid=ident()
            con.execute('INSERT INTO learn_course_grants VALUES(?,?,?,?,0)',(eid,learner_id,course_version_id,expires_at))
            self.audit(con,None,'course_grant',eid,{'authority':authority,'learner_id':learner_id,'course_id':course_version_id})
            return eid

    def revoke_course_access(self, entitlement_id, *, authority):
        if not authority:
            raise ValueError('Explicit authority required')
        with self.store.transaction() as con:
            con.execute('UPDATE learn_course_grants SET revoked=1 WHERE id=?',(entitlement_id,))
            self.audit(con,None,'course_grant_revoked',entitlement_id,{'authority':authority})

    def set_material_available(self, course_version_id, material_id, available, *, authority):
        if not authority or type(available) is not bool:
            raise ValueError('Explicit authority and availability required')
        with self.store.transaction() as con:
            con.execute('UPDATE learn_course_materials SET available=? WHERE course_id=? AND material_id=?',(int(available),course_version_id,material_id))
            for run in self.objects(con,'run'):
                if run['course_version_id']==course_version_id:
                    self.update_run(con,run,invalidate=True,from_stage='clarify')
            self.audit(con,None,'material_availability',material_id,{'authority':authority,'available':available})

    def course_write(self, con, op, session, params, body):
        if op in ('claimCase','resolveCase','transferCase','extendCase','appendCase'):
            return self.write_learning_case(con,op,session,params,body)
        b={k:v for k,v in body.items() if k not in ('request_id','expected_revision')}
        if op=='enroll':
            learner=self.learner(con,session,params['learner_id'])
            revision(body['expected_revision'],learner['revision'])
            course=self.obj(con,b['course_version_id'],'course')
            if course['state']!='published':
                fail(409,'course_unavailable','课程尚未开放。')
            if any(e['course_version_id']==course['id'] for e in self.objects(con,'enrollment',lid=learner['id'])):
                fail(409,'enrollment_exists','已报名，请读取现有记录。','reload')
            con.execute('UPDATE learn_learners SET revision=revision+1 WHERE id=?',(learner['id'],))
            return self.put(con,'enrollment',dict(id=ident(),revision=1,learner_id=learner['id'],course_version_id=course['id'],entitlement_id=b['entitlement_id'],status='active',parent_revision=learner['revision']+1),learner['id'])
        if op=='createRun':
            learner=self.learner(con,session,params['learner_id'])
            revision(body['expected_revision'],learner['revision'])
            e=self.owned(con,session,b['enrollment_id'],'enrollment')
            self.entitlement(con,e['entitlement_id'],learner['id'],e['course_version_id'])
            existing = next((r for r in self.objects(con,'run',lid=learner['id']) if r['enrollment_id']==e['id']), None)
            if existing:
                return existing
            con.execute('UPDATE learn_learners SET revision=revision+1 WHERE id=?',(learner['id'],))
            rid=ident()
            run=dict(id=rid,revision=1,learner_id=learner['id'],enrollment_id=e['id'],course_version_id=e['course_version_id'],progress=[dict(lesson_version_id=LESSON,stage=s,state='available' if i==0 else 'locked',artifact_version_id=None,check_id=None,recheck_required=False) for i,s in enumerate(STAGES)],current_action=action('continue_run',rid,'确认我的要求'),parent_revision=learner['revision']+1,current_artifact_id=None,active_model_run_id=None,allowed_actions=['saveRequirements','checkArtifact','help','askHuman'])
            for name in ('attempt','requirements','self_check','reflection','transfer_attempt'):
                run['current_'+name+'_ref']=None
            return self.put(con,'run',run,learner['id'],rid)
        if 'run_id' in params:
            run=self.owned(con,session,params['run_id'],'run')
            obj=run
        elif 'attempt_id' in params:
            obj=self.owned(con,session,params['attempt_id'],'attempt'); run=self.run_for(con,obj)
        else:
            obj=self.owned(con,session,params['artifact_id'],'artifact'); run=self.run_for(con,obj)
        if op=='saveRequirements':
            old=self.obj(con,run['current_requirements_ref']['id'],'requirements') if run['current_requirements_ref'] else self.blank_requirements(run)
            revision(body['expected_revision'],old['revision'])
        else:
            revision(body['expected_revision'],obj['revision'])
        if 'help_disclosure' in b:
            self.disclosure(b['help_disclosure'])
        if op=='saveRequirements':
            if b['material_version_id']!=MAT_A:
                fail(422,'invalid_sources','要求必须引用本课材料 A。')
            material=self.active_material(con,run['course_version_id'],MAT_A)
            if not set(b['source_locators']) <= set(material['source_locators']):
                fail(422,'invalid_sources','材料定位不正确。')
            if b['confirmed'] and (any(not v.strip() for v in b['facts'].values()) or not b['purpose'].strip() or not b['expression_preference'].strip() or set(b['source_locators'])!=set(material['source_locators']) or not b['help_disclosure']['child_confirmed']):
                fail(422,'invalid_input','确认要求前请补齐事实、定位和本人确认。')
            v=dict(b,id=old['id'],revision=old['revision']+1,run_id=run['id'],parent_revision=run['revision']+1,saved_at=self.stamp())
            run['current_requirements_ref']=ref(v)
            # Reconfirm changed requirements through G1; never inherit its old check.
            for i,p in enumerate(run['progress']):
                p.update(state='in_progress' if i==0 else 'locked',check_id=None,recheck_required=i>0)
            self.put(con,'requirements',v,run['learner_id'],run['id'])
            self.update_run(con,run,invalidate=True,from_stage='clarify')
            return v
        if op in ('createAttempt','saveAttempt'):
            kind=b['kind'] if op=='createAttempt' else obj['kind']
            stage='review' if kind=='transfer' else 'create'
            self.stage(run,stage)
            if kind == 'practice' and any(m['status'] in ('pending','running','unknown') for m in self.objects(con,'model',run=run['id'])):
                fail(409,'model_run_unsettled','先核对正在运行的尝试。')
            if op=='saveAttempt' and any(m['status'] in ('pending','running','unknown') for m in self.objects(con,'model',run=run['id']) if m['attempt_id']==obj['id']):
                fail(409,'model_run_unsettled','先核对正在运行的尝试。')
            mid=MAT_B if kind=='transfer' else MAT_A
            material=self.active_material(con,run['course_version_id'],mid)
            if op=='createAttempt' and (b['lesson_version_id']!=LESSON or b['material_version_id']!=mid):
                fail(422,'invalid_sources','课次或材料不匹配。')
            if b['task_id']!=('S3.3' if kind=='transfer' else 'S2.1'):
                fail(422,'invalid_sources','尝试任务不匹配。')
            if kind=='practice':
                if b['transfer_response'] is not None or b['requirements_ref']!=run['current_requirements_ref'] or not b['requirements_ref']:
                    fail(409,'stale_evidence','请引用当前已确认要求。','reload')
                self.evidence(con,run,b['requirements_ref'],'requirements')
            else:
                if b['requirements_ref'] is not None:
                    fail(422,'invalid_sources','迁移独立使用材料 B。')
                tr=b['transfer_response']
                if tr:
                    self.disclosure(tr['help_disclosure'])
                    if tr['help_disclosure']!=b['help_disclosure']:
                        fail(422,'invalid_input','迁移帮助记录必须一致。')
                    for change in tr['changes']:
                        if change['field'] not in FACTS or change['source_locator']!=mid+'#'+change['field']:
                            fail(422,'invalid_sources','请定位材料 B 中实际变化的字段。')
            value=dict(obj if op=='saveAttempt' else {},**b)
            value.update(id=obj['id'] if op=='saveAttempt' else ident(),revision=obj['revision']+1 if op=='saveAttempt' else 1,run_id=run['id'],lesson_version_id=LESSON,kind=kind,material_version_id=mid,help_event_ids=[h['id'] for h in self.objects(con,'help',run=run['id']) if h['task_id']==b['task_id']],parent_revision=run['revision']+1,allowed_actions=['saveAttempt']+(['createModelRun'] if kind=='practice' else []),saved_at=self.stamp())
            self.put(con,'attempt',value,run['learner_id'],run['id'])
            run['current_transfer_attempt_ref' if kind=='transfer' else 'current_attempt_ref']=ref(value)
            if kind == 'practice':
                run['active_model_run_id'] = None
            self.update_run(con,run,invalidate=True,from_stage='create' if kind=='practice' else 'review')
            return value
        if op=='createModelRun':
            self.stage(run,'create')
            if obj['kind']!='practice' or ref(obj)!=run['current_attempt_ref'] or obj['requirements_ref']!=run['current_requirements_ref']:
                fail(409,'stale_evidence','请使用当前练习输入与要求。','reload')
            self.active_material(con,run['course_version_id'],MAT_A)
            if any(m['status'] in ('pending','running','unknown') for m in self.objects(con,'model',run=run['id'])):
                fail(409,'model_run_unsettled','之前的运行仍在核对，不能重复生成。')
            if b['mode']!='mock' or not self.settings.mock_enabled or b['config_version']!=MODEL or b['replay_of'] is not None:
                fail(503,'model_mode_unavailable','本期仅开放显式模拟配置，不调用真实模型。','contact_support')
            if any(m['attempt_id']==obj['id'] and m['input_revision']==obj['revision'] for m in self.objects(con,'model',run=run['id'])):
                fail(409,'model_run_exists','这版输入已有运行，请读取结果或保存新尝试。','reload')
            req=self.evidence(con,run,obj['requirements_ref'],'requirements')
            candidate={k:req['facts'][k] for k in FACTS if k!='event_name'}
            candidate.update(title=req['facts']['event_name'][:40],invitation_line='欢迎来参加这次活动。')
            self.contract.check(candidate,self.contract.schemas['CardText'])
            value=dict(id=ident(),revision=1,attempt_id=obj['id'],report_id=None,help_event_id=None,mode='mock',status='succeeded',requested_model=None,actual_model=None,config_version=MODEL,input_revision=obj['revision'],output_text=canonical(candidate),reservation_id=None,usage={'status':'unconfigured','notice':'模拟练习：没有调用真实模型，不代表真实用量。'},reconciliation_case_id=None,visibility='normal',parent_revision=obj['revision'])
            self.put(con,'model',value,run['learner_id'],run['id'],{'input_snapshot':obj,'requirements_snapshot':req,'prompt_version':MODEL,'mode':'mock'})
            run['active_model_run_id']=value['id']; self.update_run(con,run,invalidate=True)
            return value
        if op=='help':
            if b['mode']!='static':
                fail(503,'model_mode_unavailable','P2 只提供静态提示。','contact_support')
            cards=self.obj(con,run['course_version_id'],'course')['task_cards']
            card=next((c for c in cards if c['id']==b['task_id'] and c['version']==b['task_card_version']),None)
            if not card:
                fail(422,'invalid_sources','任务卡版本不匹配。')
            self.stage(run,card['stage'])
            self.sources(con,run,b['source_ids'])
            value=dict(id=ident(),revision=1,run_id=run['id'],role_id=b['role_id'],prompt_version='invitation-static@0.1.0',help_level=b['help_level'],mode='static',text=card['help_levels'][b['help_level']-1],sources=[{'source_id':card['id'],'source_version':card['version'],'source_domain':'learning_v2','nature':'system_record'}],actions=['open_tool_card','request_human_help'],model_run_id=None,parent_revision=run['revision']+1,task_id=card['id'],task_card_version=card['version'])
            self.put(con,'help',value,run['learner_id'],run['id'],{'question':b['question'],'source_ids':b['source_ids']})
            self.update_run(con,run,invalidate=True)
            return value
        if op in ('createArtifact','versionArtifact'):
            self.stage(run,'create')
            self.active_material(con,run['course_version_id'],MAT_A)
            attempt=self.evidence(con,run,{'id':b['attempt_id'],'revision':b['attempt_revision']},'attempt')
            if attempt['kind']!='practice' or b['template_version_id']!=TEMPLATE or attempt['requirements_ref']!=run['current_requirements_ref']:
                fail(422,'invalid_sources','作品必须引用本课当前练习、要求和固定模板。')
            self.sources(con,run,b['help_event_ids'],'help')
            model=self.model_read(con,'modelRun',session,{'model_run_id':b['model_run_id']},{}) if b['model_run_id'] else None
            if model and (model['attempt_id']!=attempt['id'] or model['input_revision']!=attempt['revision'] or model['status']!='succeeded' or model['visibility']!='normal' or not model['output_text']):
                fail(422,'invalid_sources','候选运行与尝试版本不匹配。')
            if b['authorship'].startswith('ai_candidate') and not model:
                fail(422,'invalid_sources','AI 候选必须有对应运行。')
            if model:
                equal=b['content']==json.loads(model['output_text'])
                if equal and b['authorship']!='ai_candidate_unedited':
                    fail(422,'authorship_mismatch','原样候选应记录为尚未编辑的工具输出。')
                if not equal and b['authorship']=='ai_candidate_unedited':
                    fail(422,'authorship_mismatch','已修改候选需要如实记录来源。')
            if b['authorship']=='adult_transcription' and b['help_disclosure']['kind']!='adult_transcription':
                fail(422,'authorship_mismatch','请记录成人代录帮助。')
            if op=='createArtifact' and run['current_artifact_id']:
                fail(409,'artifact_exists','本课已有主作品，请保存新版本。')
            if op=='versionArtifact':
                if b['previous_artifact_version_id']!=obj['current_version']['id']:
                    fail(409,'stale_evidence','修改应基于当前作品版本。','reload')
                if not b['change_explanation'].strip() or not b['change_intent'].strip():
                    fail(422,'invalid_input','请留下修改意图和理由。')
            aid=ident() if op=='createArtifact' else obj['id']
            ver={k:b[k] for k in ('content','attempt_id','model_run_id','help_event_ids','authorship','attempt_revision','template_version_id','help_disclosure')}
            ver.update(id=ident(),artifact_id=aid,version=1 if op=='createArtifact' else obj['current_version']['version']+1,created_at=self.stamp())
            extra={k:b[k] for k in ('previous_artifact_version_id','change_intent','change_explanation') if k in b}
            self.put(con,'version',ver,run['learner_id'],run['id'],extra)
            if op == 'versionArtifact':
                # Resume must use the same version eligibility as evaluate():
                # self-checks may describe this version or its direct predecessor.
                if run['current_self_check_ref']:
                    sc = self.obj(con, run['current_self_check_ref']['id'], 'self')
                    if sc['artifact_version_id'] not in (ver['id'], b['previous_artifact_version_id']):
                        run['current_self_check_ref'] = None
                if run['current_reflection_ref']:
                    reflection = self.obj(con, run['current_reflection_ref']['id'], 'reflection')
                    if reflection['artifact_version_id'] != ver['id'] or reflection['self_check_ref'] != run['current_self_check_ref']:
                        run['current_reflection_ref'] = None
            # Invalidate before writing the new artifact so its revision advances once.
            self.update_run(con,run,invalidate=True)
            current=self.obj(con,aid,'artifact') if op=='versionArtifact' else None
            art=dict(id=aid,revision=current['revision']+1 if current else 1,learner_id=run['learner_id'],run_id=run['id'],current_version=ver,check_status='recheck_required' if current else 'unchecked',parent_revision=run['revision'],allowed_actions=['versionArtifact','readVersion','readback'],saved_at=self.stamp())
            self.put(con,'artifact',art,run['learner_id'],run['id'])
            run['current_artifact_id']=aid
            run['progress'][2]['artifact_version_id']=ver['id']
            # update_run already wrote the revision; persist the pointer in that same history snapshot.
            self.replace_run_snapshot(con,run)
            return art
        if op=='readback':
            receipt=con.execute('SELECT * FROM learn_course_receipts WHERE id=?',(b['read_receipt_id'],)).fetchone()
            if not receipt or receipt['session_id']!=session['id'] or receipt['artifact_id']!=obj['id'] or receipt['expires']<=self.clock() or receipt['version_id']!=obj['current_version']['id']:
                fail(409,'invalid_read_receipt','请在当前学习会话重新打开当前作品版本。','reload')
            value=dict(id=ident(),revision=1,artifact_version_id=receipt['version_id'],receipt_id=receipt['id'],received_at=self.stamp(),parent_revision=obj['revision'])
            self.put(con,'readback',value,run['learner_id'],run['id'],{'session_id':session['id']})
            self.update_run(con,run,invalidate=True)
            return value
        if op=='selfCheck':
            self.stage(run,'review')
            self.version_in_run(con,run,b['artifact_version_id'],current=True)
            if b['source_locator']!=MAT_A+'#'+b['field'] and not (b['field']=='invitation_line' and b['source_locator'] in self.active_material(con,run['course_version_id'],MAT_A)['source_locators']):
                fail(422,'invalid_sources','自查必须定位当前材料中的具体字段。')
            if not b['reason'].strip():
                fail(422,'invalid_input','请留下判断理由。')
            value=dict(b,id=ident(),revision=1,run_id=run['id'],parent_revision=run['revision']+1,saved_at=self.stamp())
            self.put(con,'self',value,run['learner_id'],run['id'])
            run['current_self_check_ref']=ref(value); self.update_run(con,run,invalidate=True)
            return value
        if op=='reflect':
            self.stage(run,'review')
            self.version_in_run(con,run,b['artifact_version_id'],current=True)
            sc=self.evidence(con,run,b['self_check_ref'],'self')
            if b['self_check_ref']!=run['current_self_check_ref']:
                fail(409,'stale_evidence','请引用当前自查。','reload')
            tr=self.evidence(con,run,{'id':b['transfer_attempt_id'],'revision':b['transfer_attempt_revision']},'attempt')
            if tr['kind']!='transfer' or ref(tr)!=run['current_transfer_attempt_ref'] or not tr['transfer_response']:
                fail(422,'invalid_sources','请先保存本人的迁移练习。')
            if not b['change_explanation'].strip() or not b['judgement'].strip():
                fail(422,'invalid_input','请留下修改解释和判断。')
            value=dict(b,id=ident(),revision=1,run_id=run['id'],parent_revision=run['revision']+1,saved_at=self.stamp())
            self.put(con,'reflection',value,run['learner_id'],run['id'])
            run['current_reflection_ref']=ref(value); self.update_run(con,run,invalidate=True)
            return value
        if op=='checkArtifact':
            return self.make_check(con,session,run,b)
        if op=='askHuman':
            self.sources(con,run,b['source_ids'])
            existing = next((c for c in self.objects(con,'case',run=run['id']) if c['kind']=='support' and c['status'] in ('open','claimed') and self.meta(con,c['id']).get('reason_category')==b['reason_category']),None)
            if existing:
                return self.case_projection(existing,session)
            if not self.queue_available(con,run,'support'):
                fail(503,'support_unavailable','人工支持尚未开放，请先保存。','contact_support')
            self.update_run(con,run)
            return self.new_learning_case(con,run,'support',None,b['message'],b['source_ids'],reason_category=b['reason_category'])
        raise RuntimeError('Unhandled P2 operation: '+op)

    def replace_run_snapshot(self, con, run):
        # Only used within the same uncommitted mutation, never alters a prior revision.
        con.execute('UPDATE learn_course_objects SET body=? WHERE id=?',(canonical(run),run['id']))
        con.execute('UPDATE learn_course_history SET body=? WHERE id=? AND revision=?',(canonical(run),run['id'],run['revision']))

    def version_in_run(self, con, run, vid, current=False):
        v=self.obj(con,vid,'version')
        if v['artifact_id']!=run['current_artifact_id']:
            fail(404,'resource_not_found','找不到可访问的版本。')
        if current and vid!=self.obj(con,run['current_artifact_id'],'artifact')['current_version']['id']:
            fail(409,'stale_evidence','请使用当前作品版本重新检查。','reload')
        return v

    def queue_available(self, con, run, scope='learning_review'):
        q=self.settings.learning_queue if scope=='learning_review' else self.settings.support_queue
        return bool(q and q.reviewer_id!=self.link(con,run['learner_id'])['actor_id'] and scope in self.scopes(con,q.reviewer_id))

    def evaluate(self, con, run, b):
        self.stage(run,b['stage'])
        if b['lesson_version_id']!=LESSON or b['rubric_version_id']!=RUBRIC:
            fail(422,'invalid_sources','课次或检查规则版本不匹配。')
        a=self.active_material(con,run['course_version_id'],MAT_A)
        missing,wrong=[],[]
        ev={}
        for name,kind in REFS.items():
            if b[name]:
                ev[name]=self.evidence(con,run,b[name],kind)
                if name!='readback_ref' and b[name]!=run['current_'+name]:
                    fail(409,'stale_evidence','请引用当前保存的证据版本。','reload')
        req=ev.get('requirements_ref')
        if not req or not req['confirmed']:
            missing.append('R02.requirements')
        elif any(norm(req['facts'][f])!=norm(a['facts'][f]) for f in FACTS):
            wrong.append('R02.requirements_facts')
        state='none'
        ver=None
        if b['artifact_version_id']:
            ver=self.version_in_run(con,run,b['artifact_version_id'],current=True)
        if b['stage']!='clarify':
            if not ver:
                missing.append('R03.artifact')
            else:
                model=self.obj(con,ver['model_run_id'],'model') if ver['model_run_id'] else None
                state=model['status'] if model else 'none'
                if not model or state!='succeeded':
                    missing.append('R04.model_run')
                else:
                    attempt=self.obj(con,ver['attempt_id'],'attempt')
                    if attempt['revision']!=ver['attempt_revision'] or attempt['requirements_ref']!=run['current_requirements_ref'] or model['input_revision']!=ver['attempt_revision']:
                        missing.append('R08.attempt')
                rb=ev.get('readback_ref')
                if not rb or rb['artifact_version_id']!=ver['id']:
                    missing.append('R04.readback')
        elif b['artifact_version_id'] is not None:
            fail(422,'invalid_sources','第一关不引用作品。')
        if b['stage']=='review':
            material_b=self.active_material(con,run['course_version_id'],MAT_B)
            sc=ev.get('self_check_ref'); refl=ev.get('reflection_ref'); tr=ev.get('transfer_attempt_ref')
            if not sc:
                missing.append('R05.self_check')
            if ver:
                for f in FACTS[1:]:
                    if norm(ver['content'][f])!=norm(a['facts'][f]):
                        wrong.append('R05.'+f)
                meta=self.meta(con,ver['id'])
                previous=meta.get('previous_artifact_version_id')
                if not previous:
                    missing.append('R06.previous_version')
                else:
                    prev=self.version_in_run(con,run,previous)
                    if all(norm(prev['content'][f])==norm(ver['content'][f]) for f in ver['content']):
                        wrong.append('R06.no_change')
                    if sc and sc['artifact_version_id'] not in (prev['id'],ver['id']):
                        missing.append('R08.self_check_version')
            if not refl:
                missing.append('R06.reflection')
            elif not ver or refl['artifact_version_id']!=ver['id'] or refl['self_check_ref']!=b['self_check_ref'] or {'id':refl['transfer_attempt_id'],'revision':refl['transfer_attempt_revision']}!=b['transfer_attempt_ref']:
                missing.append('R08.reflection')
            if not tr or tr['kind']!='transfer' or tr['material_version_id']!=MAT_B or not tr['transfer_response']:
                missing.append('R07.transfer')
            else:
                response=tr['transfer_response']
                if any(norm(response['facts'][f])!=norm(material_b['facts'][f]) for f in FACTS):
                    wrong.append('R07.facts')
                changes={c['field'] for c in response['changes'] if c['explanation'].strip() and c['source_locator']==MAT_B+'#'+c['field'] and c['field'] in FACTS and norm(material_b['facts'][c['field']])!=norm(a['facts'][c['field']])}
                if len(changes)<2:
                    wrong.append('R07.changes')
                if not response['invitation_line'].strip():
                    missing.append('R07.invitation_line')
        return missing,wrong,state,ev

    def make_check(self, con, session, run, b):
        missing,wrong,state,ev=self.evaluate(con,run,b)
        complete=not missing
        unknown=state in ('pending','running','unknown')
        result='unknown' if unknown else 'incomplete' if missing else 'needs_practice' if wrong else 'pass'
        effect,outcome,available='none','feedback_only',None
        if b['purpose']!='preflight':
            if unknown:
                outcome='blocked_unknown'
            elif missing:
                outcome='blocked_evidence'
            elif wrong:
                effect,outcome='needs_practice','needs_practice'
            elif b['purpose']=='advance':
                effect,outcome='passed_and_unlocked','advanced'
            else:
                available=self.queue_available(con,run)
                effect,outcome=('pending_review','awaiting_review') if available else ('none','blocked_support')
        p=run['progress'][STAGES.index(b['stage'])]
        if effect=='passed_and_unlocked':
            p.update(state='passed',recheck_required=False,artifact_version_id=b['artifact_version_id'])
            following=run['progress'][STAGES.index(b['stage'])+1]
            if following['state']=='locked':
                following['state']='available'
        elif effect in ('needs_practice','pending_review'):
            p.update(state=effect,recheck_required=False,artifact_version_id=b['artifact_version_id'])
        messages = {
            'R02.requirements':'请先确认活动对象、时间、地点和准备物品，再说说邀请目的和表达方式。',
            'R02.requirements_facts':'请对照资料卡，改好要求里不一致的活动信息。',
            'R03.artifact':'请先保存你选择的邀请卡。',
            'R04.model_run':'请先保存这次输入，再完成一次模拟生成。',
            'R04.readback':'请重新打开并确认当前保存版本。',
            'R08.attempt':'这张作品的输入已有变化，请按当前要求重新保存并生成。',
            'R05.self_check':'请选作品中的一项信息，对照材料写下判断和理由。',
            'R06.previous_version':'请亲自修改作品的一处，再保存为新版本。',
            'R06.no_change':'这次还没有看到内容变化，请改进一处信息或邀请语，再保存。',
            'R08.self_check_version':'作品又有变化，请对当前作品重新做一次自查。',
            'R06.reflection':'请完成小迁移后，保存你改了什么、为什么改的解释。',
            'R08.reflection':'作品或小迁移已有更新，请重新保存对应的解释。',
            'R07.transfer':'请使用第二张资料卡，保存一次自己的小迁移练习。',
            'R07.facts':'请对照第二张资料卡，修正小迁移里的活动信息。',
            'R07.changes':'请说明新资料中至少两处不同的信息，以及为什么不能沿用上次的卡。',
            'R07.invitation_line':'请为第二个活动写一句自己的邀请语。'}
        labels=dict(audience='邀请对象',date='日期',start_time='开始时间',end_time='结束时间',place='地点',preparation='准备物品')
        messages.update({'R05.'+f:'请对照资料卡，核对作品中的'+label+'。' for f,label in labels.items()})
        feedback=[messages[x] for x in missing+wrong]
        if unknown:
            feedback=['工具结果还在核对，请先保留输入，稍后查看进展。']
        if not feedback:
            feedback=['这次规则检查没有发现缺项。模拟练习仍需要老师检查，不代表真实工具学习已经完成。']
        if outcome=='blocked_support':
            feedback.append('老师检查暂未开放，你可以先保存作品，稍后回来查看。')
        value=dict(b,id=ident(),revision=1,run_id=run['id'],learner_id=run['learner_id'],rule_result=result,human_result=None,missing_evidence=missing,feedback=feedback,case_id=None,evidence_hash='',stale=False,parent_revision=run['revision']+1,allowed_actions=['checkArtifact'],evidence_complete=complete,model_state=state,reviewer_available=available,progress_effect=effect,outcome=outcome)
        snapshots={'request':b,'evidence':ev,'help_events':self.objects(con,'help',run=run['id']),'mode':'mock'}
        if run['current_artifact_id']:
            snapshots['versions']=self.objects(con,'version',run=run['id'])
        value['evidence_hash']=hashlib.sha256(canonical(snapshots).encode()).hexdigest()
        if effect=='pending_review':
            for existing in self.objects(con,'case',run=run['id']):
                if existing['kind']=='learning_review' and existing['status'] in ('open','claimed'):
                    old_check=self.obj(con,existing['target_id'],'check')
                    if not old_check['stale'] and old_check['evidence_hash']==value['evidence_hash']:
                        return old_check
        if effect!='none':
            p['check_id']=value['id']
        self.update_run(con,run)
        if effect=='pending_review':
            # One active review for an evidence set, even with a new request ID.
            for old in self.objects(con,'case',run=run['id']):
                if old['kind']=='learning_review' and old['status'] in ('open','claimed'):
                    old_check=self.obj(con,old['target_id'],'check')
                    if not old_check['stale']:
                        fail(409,'review_already_pending','本次证据已交给老师，请查看进展。','reload')
                    old.update(status='escalated',revision=old['revision']+1,feedback='作品或证据已更新，请查看新送审记录。',allowed_actions=[])
                    self.put(con,'case',old)
            # Save check before gathering the review evidence, then attach case in this transaction.
            self.put(con,'check',value,run['learner_id'],run['id'],snapshots)
            c=self.new_learning_case(con,run,'learning_review',value,'请核对 M1–M4；本次为模拟协议练习。',[])
            value['case_id']=c['id']
            con.execute('UPDATE learn_course_objects SET body=? WHERE id=?',(canonical(value),value['id']))
            con.execute('UPDATE learn_course_history SET body=? WHERE id=? AND revision=1',(canonical(value),value['id']))
        else:
            self.put(con,'check',value,run['learner_id'],run['id'],snapshots)
        if run['current_artifact_id'] and effect in ('pending_review','needs_practice'):
            art=self.obj(con,run['current_artifact_id'],'artifact')
            art.update(check_status=effect,revision=art['revision']+1,parent_revision=run['revision'])
            self.put(con,'artifact',art)
        return value

    def case_projection(self, case, session):
        value=dict(case)
        if session['mode']=='learner':
            value['allowed_actions']=['appendCase'] if case['status'] in ('open','claimed') else []
        return value

    def has_assigned_run(self, con, session, run_id):
        if 'learning_review' not in self.scopes(con, session['actor_id']):
            return False
        return any(c['kind'] == 'learning_review' and self.meta(con, c['id'])['assignee'] == session['actor_id']
                   and self.link(con, c['learner_id'])['actor_id'] != session['actor_id']
                   for c in self.objects(con, 'case', run=run_id))

    def assigned_run(self, con, session, run_id):
        if not self.has_assigned_run(con, session, run_id):
            fail(404, 'resource_not_found', '找不到已分配的学习记录。')

    def learning_case(self, con, session, cid, staff=False):
        c=self.obj(con,cid,'case')
        if staff or session['mode']=='staff':
            self.role(session,'staff')
            meta=self.meta(con,cid)
            if meta['assignee']!=session['actor_id'] or c['kind'] not in self.scopes(con,session['actor_id']) or self.link(con,c['learner_id'])['actor_id']==session['actor_id']:
                fail(404,'resource_not_found','找不到可访问的案件。')
            self.learning_access(con, c['learner_id'])
            run = self.obj(con, meta['run_id'], 'run')
            enrollment = self.obj(con, run['enrollment_id'], 'enrollment')
            self.entitlement(con, enrollment['entitlement_id'], run['learner_id'], run['course_version_id'])
        else:
            self.role(session,'learner')
            self.owned(con,session,cid,'case')
        return c

    def new_learning_case(self, con, run, kind, check, message, source_ids, reason_category=None):
        q=self.settings.learning_queue if kind=='learning_review' else self.settings.support_queue
        cid=ident()
        case=dict(id=cid,revision=1,kind=kind,target_id=check['id'] if check else run['id'],status='open',owner_display_name=q.display_name,due_at=datetime.fromtimestamp(self.clock()+q.due_seconds,timezone.utc).isoformat(timespec='seconds'),feedback=None,next_action=action('wait_review',cid,'等待老师检查' if check else '等待老师回复'),parent_revision=run['revision'],allowed_actions=['claimCase'],support_contact_label=q.support_contact_label,learner_id=run['learner_id'])
        sources=[]
        def add_source(sid,version,nature,body):
            text=canonical(body)
            # The frozen evidence endpoint bounds each text to 8000 characters.
            # Split long saved input without dropping or silently truncating it.
            for start in range(0,len(text),8000):
                sources.append({'ref':{'source_id':sid,'source_version':str(version),'source_domain':'learning_v2','nature':nature},'redacted_text':text[start:start+8000],'visibility':'assigned_reviewer_only'})
        if check:
            selected={v['id'] for name in REFS if (v:=check[name])}
            ver=self.version_in_run(con,run,check['artifact_version_id'])
            selected.update([ver['id'],ver['attempt_id'],ver['model_run_id']])
            previous=self.meta(con,ver['id']).get('previous_artifact_version_id')
            if previous:
                selected.add(previous)
            for k in ('requirements','attempt','model','version','self','reflection','help','readback'):
                for v in self.objects(con,k,run=run['id']):
                    if k!='help' and v['id'] not in selected:
                        continue
                    # Preserve complete relevant evidence. Exclude credential-like receipt IDs.
                    view={key:value for key,value in v.items() if key!='receipt_id'}
                    if k == 'version':
                        view = {'artifact_version': view, 'change_record': self.meta(con, v['id'])}
                    add_source(v['id'],v.get('revision',v.get('version',1)),'system_record' if k in ('model','help','readback') else 'child_statement',view)
            add_source(check['id'],check['revision'],'system_record',check)
        for sid in source_ids:
            v=self.active_material(con,run['course_version_id'],sid) if sid in (MAT_A,MAT_B) else self.obj(con,sid)
            add_source(sid,v.get('revision',1),'child_statement',v)
        mid=ident()
        add_source(mid,1,'child_statement',{'message':message})
        if len(sources)>100:
            fail(422,'evidence_capacity_exceeded','本次证据超过审核容量，请联系课程支持整理；原记录已保留。','contact_support')
        meta={'assignee':q.reviewer_id,'run_id':run['id'],'reason_category':reason_category,'evidence':sources,'messages':[{'id':mid,'message':message,'source_ids':source_ids,'actor_id':None,'recorded_at':self.stamp()}],'decisions':[]}
        return self.put(con,'case',case,run['learner_id'],run['id'],meta)

    def write_learning_case(self, con, op, session, params, body):
        c=self.learning_case(con,session,params['case_id'],staff=op!='appendCase')
        revision(body['expected_revision'],c['revision'])
        meta=self.meta(con,c['id']); run=self.obj(con,meta['run_id'],'run')
        if c['status'] not in ('open','claimed'):
            fail(409,'invalid_transition','案件当前不能修改。','reload')
        if op=='claimCase':
            if c['status']!='open':
                fail(409,'invalid_transition','案件已经认领。','reload')
            c.update(status='claimed',allowed_actions=['resolveCase','appendCase','extendCase','transferCase'])
        elif op=='appendCase':
            self.sources(con,run,body['source_ids'])
            mid=ident()
            meta['messages'].append(dict(id=mid,message=body['message'],source_ids=body['source_ids'],actor_id=session['actor_id'],recorded_at=self.stamp()))
            if len(meta['evidence'])>=100:
                fail(422,'evidence_capacity_exceeded','本案件已达到证据容量，请联系课程支持。','contact_support')
            meta['evidence'].append({'ref':{'source_id':mid,'source_version':'1','source_domain':'learning_v2','nature':'child_statement' if session['mode']=='learner' else 'human_review'},'redacted_text':body['message'],'visibility':'assigned_reviewer_only'})
        elif op=='extendCase':
            due=datetime.fromisoformat(body['new_due_at'].replace('Z','+00:00'))
            if due.timestamp()<=max(self.clock(),datetime.fromisoformat(c['due_at']).timestamp()):
                fail(422,'invalid_input','新期限必须晚于原期限与当前时间。')
            c['due_at']=body['new_due_at']
            meta.setdefault('extensions',[]).append({'reason':body['reason'],'due_at':body['new_due_at'],'actor_id':session['actor_id']})
        elif op=='transferCase':
            target=body['assignee_id']
            if target==self.link(con,run['learner_id'])['actor_id'] or c['kind'] not in self.scopes(con,target):
                fail(422,'invalid_assignee','接手人员必须有有效复核权限且不能审核自己的孩子。')
            person=con.execute('SELECT name FROM people WHERE id=?',(target,)).fetchone()
            meta['assignee']=target
            c.update(owner_display_name=person[0] or '获准复核人员',status='open',allowed_actions=['claimCase'])
            meta.setdefault('transfers',[]).append({'actor_id':session['actor_id'],'assignee_id':target,'reason':body['reason']})
        elif op=='resolveCase':
            if c['status']!='claimed':
                fail(409,'invalid_transition','请先认领案件。','reload')
            revision(body['target_revision'],c['parent_revision'])
            # A help request does not freeze learner progress. Learning reviews do.
            if c['kind']=='learning_review':
                check=self.obj(con,c['target_id'],'check')
                if check['stale'] or run['progress'][2]['check_id']!=check['id']:
                    fail(409,'stale_evidence','证据已变化，请让孩子重新检查送审。','reload')
                self.learning_access(con,run['learner_id'])
                enrollment=self.obj(con,run['enrollment_id'],'enrollment')
                self.entitlement(con,enrollment['entitlement_id'],run['learner_id'],run['course_version_id'])
                missing,wrong,state,_=self.evaluate(con,run,self.meta(con,check['id'])['request'])
                if missing or wrong or state!='succeeded':
                    fail(409,'stale_evidence','当前证据不满足复核前置条件。','reload')
                if body['decision'] not in ('passed','needs_practice','needs_information'):
                    fail(422,'invalid_input','学习审核结论不适用。')
            elif body['decision']!='answered' or body['manual_findings']:
                fail(422,'invalid_input','支持案件只记录已回复。')
            valid_ids={s['ref']['source_id'] for s in meta['evidence']}
            if not body['evidence_ids'] or not set(body['evidence_ids'])<=valid_ids:
                fail(422,'invalid_sources','请引用本案件证据。')
            for finding in body['manual_findings']:
                if not set(finding['source_ids'])<=valid_ids or not set(finding['source_ids'])<=set(body['evidence_ids']):
                    fail(422,'invalid_sources','人工分项必须引用本次结论包含的案件证据。')
            decision_record = {**body,'reviewer_id':session['actor_id'],'recorded_at':self.stamp(),'mode':'mock'}
            meta['decisions'].append(decision_record)
            decision_id, decision_text = ident(), canonical(decision_record)
            parts = [decision_text[i:i+8000] for i in range(0,len(decision_text),8000)]
            if len(meta['evidence']) + len(parts) > 100:
                fail(422,'evidence_capacity_exceeded','审核记录超过案件容量，请联系课程支持整理；原记录已保留。','contact_support')
            meta['evidence'].extend({'ref':{'source_id':decision_id,'source_version':'1','source_domain':'learning_v2','nature':'human_review'},'redacted_text':part,'visibility':'assigned_reviewer_only'} for part in parts)
            c['feedback']=body['note']
            if body['decision']!='needs_information':
                c.update(status='resolved',allowed_actions=[],next_action=action('continue_run',run['id'],'查看作品与反馈'))
                if c['kind']=='learning_review':
                    check.update(revision=check['revision']+1,human_result=body['decision'])
                    self.put(con,'check',check)
                    run['progress'][2].update(state=body['decision'],recheck_required=False)
                    self.update_run(con,run)
                    c['parent_revision']=run['revision']
                    art=self.obj(con,run['current_artifact_id'],'artifact')
                    art.update(revision=art['revision']+1,check_status=body['decision'],parent_revision=run['revision'])
                    self.put(con,'artifact',art)
            else:
                c['next_action']=action('continue_run',run['id'],'请补充老师提出的依据')
        c['revision']+=1
        self.put(con,'case',c,private=meta)
        self.audit(con,session['actor_id'],op,c['id'],{'decision':body.get('decision'),'mode':'mock'})
        return self.case_projection(c,session)
