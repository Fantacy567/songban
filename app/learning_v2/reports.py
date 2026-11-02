"""P3 reports: frozen learning facts, exact approvals and revocable publications.

No network calls here. ModelDomain owns dispatch; completion runs in its transaction.
"""
import copy
import hashlib
import json
from datetime import datetime, timezone

from .course import action, ident
from .protocol import Problem, canonical, fail, revision, strict_json

DDL = '''
CREATE TABLE learn_report_snapshots (id TEXT PRIMARY KEY, report_id TEXT NOT NULL UNIQUE, body TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TABLE learn_report_reviews (id TEXT PRIMARY KEY, report_id TEXT NOT NULL, revision INTEGER NOT NULL, content_hash TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE learn_report_publications (id TEXT PRIMARY KEY, report_id TEXT NOT NULL UNIQUE, body TEXT NOT NULL, snapshot TEXT NOT NULL);
CREATE TABLE learn_report_revocations (report_id TEXT PRIMARY KEY, reason TEXT NOT NULL, actor_id TEXT, recorded_at TEXT NOT NULL);
'''


def hashed(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def hidden():
    fail(404, 'resource_not_found', '找不到可访问的记录。')


class ReportDomain:
    REPORT_OPS = set('createReport report reports disputeReport submitReport reviewReport publishReport revokeReport'.split())

    def migrate_reports(self):
        checksum = hashlib.sha256(DDL.encode()).hexdigest()
        with self.store.transaction() as con:
            old = con.execute("SELECT checksum FROM learn_migrations WHERE version='M03_REPORTS'").fetchone()
            if old:
                if old[0] != checksum:
                    raise ValueError('M03_REPORTS checksum mismatch')
                return
            for sql in DDL.split(';'):
                if sql.strip():
                    con.execute(sql)
            con.execute("INSERT INTO learn_migrations VALUES('M03_REPORTS',?,?)", (checksum, self.stamp()))

    def report_handles(self, con, op, params):
        if op in self.REPORT_OPS:
            return True
        if op in ('case', 'caseEvidence', 'claimCase', 'resolveCase', 'transferCase', 'extendCase', 'appendCase'):
            row = con.execute("SELECT body FROM learn_course_objects WHERE id=? AND kind='case'", (params.get('case_id'),)).fetchone()
            return bool(row and json.loads(row[0])['kind'] == 'report_review')
        return False

    def report_consent(self, con, lid, summary=False):
        link = self.link(con, lid)
        if not link or link['status'] != 'verified':
            return False
        scopes = set()
        for row in con.execute('SELECT * FROM learn_consents WHERE learner_id=?', (lid,)):
            scopes.update(self.effective(con, row))
        return {'learning', 'parent_summary' if summary else 'learning'} <= scopes

    def report_case_for(self, con, report):
        cid = self.meta(con, report['id']).get('case_id')
        return self.obj(con, cid, 'case') if cid else None

    def report_staff(self, con, session, report, scope=None):
        case = self.report_case_for(con, report)
        scopes = self.scopes(con, session['actor_id'])
        if (session['mode'] != 'staff' or not case or
                self.meta(con, case['id'])['assignee'] != session['actor_id'] or
                (scope not in scopes if scope else not set(scopes) & {'report_review', 'report_publish'}) or
                self.link(con, report['learner_id'])['actor_id'] == session['actor_id']):
            hidden()
        return case

    def report_access(self, con, session, rid, scope=None, allow_revoked=False):
        r = self.obj(con, rid, 'report')
        if session['mode'] == 'staff':
            self.report_staff(con, session, r, scope)
        else:
            self.learner(con, session, r['learner_id'])
            if session['mode'] == 'manager' and not r['publication_id']:
                hidden()
        if not self.report_consent(con, r['learner_id'], session['mode'] == 'manager'):
            hidden()
        if r['status'] == 'revoked' and not allow_revoked:
            fail(410, 'report_revoked', '这份报告已经撤回。')
        return r

    def report_authorize(self, con, op, session, params, body):
        if op == 'createReport':
            self.role(session, 'learner')
            self.owned(con, session, params['run_id'], 'run')
        elif 'report_id' in params:
            r = self.report_access(con, session, params['report_id'],
                                   'report_review' if op == 'reviewReport' else 'report_publish' if op in ('publishReport', 'revokeReport') and session['mode'] == 'staff' else None,
                                   allow_revoked=op in ('revokeReport', 'disputeReport'))
            if op in ('disputeReport', 'submitReport'):
                self.role(session, 'learner')
            elif op in ('reviewReport', 'publishReport'):
                self.role(session, 'staff')
            elif op == 'revokeReport':
                self.role(session, 'staff', 'manager')
        elif 'case_id' in params:
            c = self.obj(con, params['case_id'], 'case')
            self.report_access(con, session, c['target_id'], 'report_review')
            if op != 'appendCase':
                self.role(session, 'staff')
        if op != 'revokeReport' and not self.settings.reports_enabled:
            fail(503, 'operation_unavailable', '报告整理暂未开放，已保存作品仍保留。')

    def report_snapshot(self, con, r):
        row = con.execute('SELECT body,hash FROM learn_report_snapshots WHERE id=? AND report_id=?', (r['source_snapshot_id'], r['id'])).fetchone()
        if not row or row['hash'] != r['source_hash'] or hashed(json.loads(row['body'])) != row['hash']:
            fail(409, 'invalid_sources', '报告来源无法核对。')
        return json.loads(row['body'])

    def report_facts(self, con, run, body):
        """Only persisted, current evidence. Raw prompts and private chats are excluded."""
        check = self.obj(con, body['check_id'], 'check')
        reflection = self.obj(con, body['reflection_id'], 'reflection')
        version = self.version_in_run(con, run, body['artifact_version_id'])
        artifact = self.obj(con, run['current_artifact_id'], 'artifact') if run['current_artifact_id'] else None
        if check['run_id'] != run['id'] or reflection['run_id'] != run['id']:
            hidden()
        if (not artifact or artifact['current_version']['id'] != version['id'] or
                check['stage'] != 'review' or check['stale'] or check['artifact_version_id'] != version['id'] or
                not check['evidence_complete'] or check['model_state'] != 'succeeded' or
                (run['progress'][2]['check_id'] and run['progress'][2]['check_id'] != check['id']) or
                run['current_reflection_ref'] != {'id': reflection['id'], 'revision': reflection['revision']} or
                check['reflection_ref'] != run['current_reflection_ref'] or reflection['artifact_version_id'] != version['id']):
            fail(409, 'evidence_stale', '请先保存复盘并检查当前作品，再整理报告。', 'reload')
        # Re-evaluate original saved checks; a later help/input change must not inherit approval.
        request = self.meta(con, check['id']).get('request')
        if request:
            missing, wrong, state, _ = self.evaluate(con, run, request)
            if missing or wrong or state != 'succeeded':
                fail(409, 'evidence_stale', '当前证据需要重新检查。', 'reload')
        sources = []
        def add(obj, nature, facts):
            sources.append({'ref': {'source_id': obj['id'], 'source_version': str(obj.get('revision', obj.get('version', 1))),
                                    'source_domain': 'learning_v2', 'nature': nature}, 'facts': facts})
        add(version, 'system_record', {k: version[k] for k in ('content', 'authorship', 'help_disclosure', 'model_run_id')})
        previous = self.meta(con, version['id']).get('previous_artifact_version_id')
        if previous:
            old = self.version_in_run(con, run, previous)
            add(old, 'system_record', {k: old[k] for k in ('content', 'authorship', 'help_disclosure')})
        add(check, 'system_record', {k: check[k] for k in ('rule_result', 'human_result', 'missing_evidence', 'stale', 'evidence_hash')})
        if check['human_result'] is not None:
            case = self.obj(con, check['case_id'], 'case')
            add(case, 'human_review', {'feedback': case['feedback'], 'decisions': self.meta(con, case['id']).get('decisions', [])})
        add(reflection, 'child_statement', {k: reflection[k] for k in ('change_explanation', 'judgement', 'help_disclosure')})
        for key, kind, fields in (
            ('self_check_ref', 'self', ('field', 'judgement', 'reason', 'source_locator', 'help_disclosure')),
            ('transfer_attempt_ref', 'attempt', ('transfer_response', 'material_version_id', 'help_disclosure')),
            ('requirements_ref', 'requirements', ('facts', 'purpose', 'expression_preference', 'help_disclosure'))):
            obj = self.evidence(con, run, check[key], kind)
            add(obj, 'child_statement', {k: obj[k] for k in fields})
        for help_event in self.objects(con, 'help', run=run['id']):
            add(help_event, 'system_record', {k: help_event[k] for k in ('role_id', 'help_level', 'mode', 'task_id') if k in help_event})
        model = self.obj(con, version['model_run_id'], 'model') if version['model_run_id'] else None
        if model:
            add(model, 'system_record', {k: model[k] for k in ('mode', 'status', 'actual_model', 'config_version')})
        if len(sources) > 90:
            fail(422, 'evidence_capacity_exceeded', '本次来源较多，请联系课程支持整理。')
        return {'sources': sources, 'source_ids': [s['ref']['source_id'] for s in sources], 'selection': {k: body[k] for k in ('reflection_id', 'artifact_version_id', 'check_id')},
                'limitations': ['仅描述本次平台内练习，不证明外部工具掌握、天赋或独立完成。',
                                '帮助披露与实际帮助可能不完整；自动检查、AI建议和人工意见分别记录。',
                                '本次作品操作模式：'+(model['mode'] if model else '无模型运行')+'。报告整理方式不能改变原操作模式。']}

    def report_changed(self, con, r):
        try:
            snapshot = self.report_snapshot(con, r)
            current = self.report_facts(con, self.obj(con, r['run_id'], 'run'), snapshot['selection'])
            return hashed(current) != r['source_hash']
        except Problem:
            return True

    def report_observations(self, con, r, observations, model=False):
        self.contract.check(observations, {'type': 'array', 'minItems': 0 if model else 1, 'maxItems': 100, 'items': {'$ref': '#/components/schemas/Observation'}})
        sources = {s['ref']['source_id']: s['ref']['nature'] for s in self.report_snapshot(con, r)['sources']}
        for o in observations:
            if not o['text'].strip() or not set(o['source_ids']) <= sources.keys():
                fail(422, 'invalid_sources', '每条观察都需要引用本次报告的有效来源。')
            if model and o['nature'] != 'ai_suggestion':
                fail(422, 'invalid_sources', 'AI整理只能标为AI建议，不能充当人工结论。')
            if o['nature'] in ('child_statement', 'system_record') and not any(sources[sid] == o['nature'] for sid in o['source_ids']):
                fail(422, 'invalid_sources', '观察类型与来源不一致。')

    def report_content_hash(self, r):
        return hashed({k: r[k] for k in ('observations', 'limitations', 'source_hash', 'source_snapshot_id')})

    def report_projection(self, con, session, r):
        value = copy.deepcopy(r)
        if session['mode'] == 'manager':
            row = con.execute('SELECT snapshot FROM learn_report_publications WHERE report_id=?', (r['id'],)).fetchone()
            if r['status'] != 'published' or not row:
                hidden()
            value = json.loads(row[0])
        value['evidence_changed'] = self.report_changed(con, r)
        actions = []
        if session['mode'] == 'learner' and r['generation_status'] == 'succeeded':
            if r['status'] in ('draft', 'pending_review', 'published'):
                actions.append('disputeReport')
            if r['status'] == 'draft' and not value['evidence_changed']:
                actions.append('submitReport')
        elif session['mode'] == 'staff':
            scopes = self.scopes(con, session['actor_id'])
            c = self.report_case_for(con, r)
            if c and c['status'] == 'claimed' and r['status'] == 'pending_review':
                if 'report_review' in scopes:
                    actions.append('reviewReport')
                if 'report_publish' in scopes and r['review_id'] and self.settings.publication_enabled:
                    actions.append('publishReport')
            if r['status'] == 'published' and 'report_publish' in scopes:
                actions.append('revokeReport')
        elif session['mode'] == 'manager' and r['status'] == 'published':
            actions.append('revokeReport')
        value['allowed_actions'] = actions
        return value

    def report_read(self, con, op, session, params, query):
        if op == 'reports':
            lid = params['learner_id']
            self.learner(con, session, lid)
            if not self.report_consent(con, lid, session['mode'] == 'manager'):
                hidden()
            rows = self.objects(con, 'report', lid=lid)
            rows = [r for r in rows if r['status'] != 'revoked' and (session['mode'] != 'manager' or r['status'] == 'published')]
            rows, cursor = self.page(con, session, 'reports:'+lid, rows, query)
            return {'items': [self.report_projection(con, session, r) for r in rows], 'next_cursor': cursor}
        if op == 'report':
            return self.report_projection(con, session, self.report_access(con, session, params['report_id']))
        c = self.obj(con, params['case_id'], 'case')
        r = self.report_access(con, session, c['target_id'])
        if op == 'case':
            value = dict(c)
            value['allowed_actions'] = (['claimCase'] if c['status'] == 'open' else ['appendCase', 'extendCase', 'transferCase'] if c['status'] == 'claimed' else []) if session['mode'] == 'staff' and 'report_review' in self.scopes(con, session['actor_id']) else (['appendCase'] if session['mode'] == 'learner' and c['status'] in ('open', 'claimed') else [])
            return value
        self.role(session, 'staff')
        sources = []
        for s in self.report_snapshot(con, r)['sources']:
            txt = canonical(s['facts'])
            for i in range(0, len(txt), 8000):
                sources.append({'ref': s['ref'], 'redacted_text': txt[i:i+8000], 'visibility': 'assigned_reviewer_only'})
        for d in self.objects(con, 'report_dispute', run=r['run_id']):
            if d['report_id'] == r['id']:
                sources.append({'ref': {'source_id': d['id'], 'source_version': str(d['revision']), 'source_domain': 'learning_v2', 'nature': 'child_statement'},
                                'redacted_text': canonical({**d, **self.meta(con, d['id'])}), 'visibility': 'assigned_reviewer_only'})
        sources += self.meta(con, c['id']).get('evidence', [])
        if len(sources) > 100:
            fail(422, 'evidence_capacity_exceeded', '证据超过读取容量，请联系课程支持。')
        return {'case_id': c['id'], 'target_revision': r['revision'], 'sources': sources}

    def complete_report_generation(self, con, report_id, model_run):
        r = self.obj(con, report_id, 'report')
        meta = self.meta(con, r['id'])
        if model_run.get('report_id') != r['id'] or meta.get('model_run_id') not in (None, model_run['id']):
            fail(409, 'invalid_transition', '生成记录与报告不匹配。')
        if r['generation_status'] in ('succeeded', 'failed') or r['status'] == 'revoked':
            return r
        meta['model_run_id'] = model_run['id']
        state = model_run['status']
        r['generation_status'] = {'queued': 'pending'}.get(state, state)
        if state == 'succeeded':
            try:
                if model_run.get('visibility') != 'normal' or not self.report_consent(con, r['learner_id']) or self.report_changed(con, r):
                    fail(409, 'evidence_stale', '生成期间来源或授权已变化。')
                if not isinstance(model_run.get('output_text'), str):
                    fail(422, 'invalid_model_output', '报告结果缺少可核对的内容。')
                output = strict_json(model_run['output_text'])
                self.contract.check(output, {'type': 'object', 'additionalProperties': False, 'required': ['observations', 'limitations'], 'properties': {'observations': {'type': 'array'}, 'limitations': {'type': 'array', 'maxItems': 90, 'items': {'type': 'string', 'minLength': 1, 'maxLength': 8000}}}})
                self.report_observations(con, r, output['observations'], model=True)
                r['observations'] = output['observations']
                r['limitations'] += output['limitations']
            except Problem as exc:
                r.update(status='failed', generation_status='failed')
                meta['failure_code'] = exc.code
        elif state == 'failed':
            r['status'] = 'failed'
        r['revision'] += 1
        self.put(con, 'report', r, private=meta)
        self.audit(con, None, 'report_generation_'+r['generation_status'], r['id'], {'model_run_id': model_run['id']})
        return r

    def invalidate_learner_reports(self, con, learner_id, *, actor_id=None, reason='consent_or_relationship_revoked'):
        """Central consent/link withdrawal MUST call inside its revocation transaction."""
        for r in self.objects(con, 'report', lid=learner_id):
            if r['status'] != 'revoked':
                self.revoke_report_record(con, r, actor_id, reason)

    def revoke_report_record(self, con, r, actor, reason):
        if r['status'] != 'revoked':
            con.execute('INSERT INTO learn_report_revocations VALUES(?,?,?,?)', (r['id'], reason, actor, self.stamp()))
            r.update(status='revoked', revision=r['revision']+1, allowed_actions=[])
            self.put(con, 'report', r)
            self.audit(con, actor, 'report_revoked', r['id'], {'reason': reason, 'publication_id': r['publication_id']})
        return r

    def report_write(self, con, op, session, params, body):
        self.report_authorize(con, op, session, params, body)
        if 'case_id' in params:
            if op == 'resolveCase':
                fail(422, 'invalid_input', '报告请使用报告校对与审核入口。')
            # Existing case writer has scope+assignment checks and durable messages/transfers.
            return self.write_learning_case(con, op, session, params, body)
        if op == 'createReport':
            run = self.owned(con, session, params['run_id'], 'run')
            revision(body['expected_revision'], run['revision'])
            pending = [r for r in self.objects(con, 'report', run=run['id']) if r['generation_status'] in ('pending', 'running', 'unknown') and r['status'] != 'revoked']
            if pending:
                fail(409, 'active_run_unknown', '上次报告整理仍在处理中，请先查看原记录。')
            snapshot = self.report_facts(con, run, body)
            r = dict(id=ident(), revision=1, learner_id=run['learner_id'], run_id=run['id'], status='draft', generation_status='pending', source_snapshot_id=ident(), source_hash=hashed(snapshot), observations=[], limitations=list(snapshot['limitations']), evidence_changed=False, review_id=None, publication_id=None, parent_revision=run['revision']+1, allowed_actions=[])
            r['limitations'].append({'mock': '报告整理模式：模拟（mock），未调用真实供应商。', 'live': '报告整理模式：真实调用（live）；AI整理须经人工复核。', 'replay': '报告整理模式：历史回放（replay），不是新调用。'}[body['mode']])
            con.execute('INSERT INTO learn_report_snapshots VALUES(?,?,?,?)', (r['source_snapshot_id'], r['id'], canonical(snapshot), r['source_hash']))
            self.put(con, 'report', r, run['learner_id'], run['id'], {'case_id': None, 'model_run_id': None})
            replay = {}
            if body['mode'] == 'replay':
                candidates = [m for m in self.objects(con, 'model', run=run['id']) if m['report_id'] and m['status'] == 'succeeded' and m['visibility'] == 'normal'
                              and self.meta(con, m['id']).get('input_snapshot') == snapshot]
                if not candidates:
                    fail(409, 'replay_unavailable', '没有与这些事实完全相同的可回放报告。')
                replay['replay_of'] = candidates[-1]['id']
            model = self.queue_model(con, session, run, mode=body['mode'], purpose='report', input_payload=copy.deepcopy(snapshot), report=r, **replay)
            current = self.obj(con, r['id'], 'report')
            if self.meta(con, r['id']).get('model_run_id') is None:
                current = self.complete_report_generation(con, r['id'], model)
            # Do not let report creation stale learning checks or re-run experiments.
            run = self.obj(con, run['id'], 'run')
            run['revision'] += 1
            self.put(con, 'run', run)
            return self.report_projection(con, session, current)
        r = self.report_access(con, session, params['report_id'], allow_revoked=op in ('revokeReport', 'disputeReport'))
        revision(body['expected_revision'], r['revision'])
        if op == 'revokeReport':
            return self.revoke_report_record(con, r, session['actor_id'], body['reason'])
        if op == 'disputeReport':
            if r['generation_status'] != 'succeeded' or r['status'] not in ('draft', 'pending_review', 'published'):
                fail(409, 'invalid_transition', '请等待报告整理结果。')
            valid = {s['ref']['source_id'] for s in self.report_snapshot(con, r)['sources']}
            if not set(body['source_ids']) <= valid:
                fail(422, 'invalid_sources', '请选择这份报告中的来源。')
            d = dict(id=ident(), revision=1, report_id=r['id'], status='open', parent_revision=r['revision']+1)
            self.put(con, 'report_dispute', d, r['learner_id'], r['run_id'], {'note': body['note'], 'source_ids': body['source_ids']})
            if r['status'] == 'published':
                self.revoke_report_record(con, r, session['actor_id'], 'child_dispute')
            else:
                r.update(revision=r['revision']+1, review_id=None)
                self.put(con, 'report', r)
            self.audit(con, session['actor_id'], 'report_disputed', r['id'], {'dispute_id': d['id']})
            return d
        if self.report_changed(con, r):
            fail(409, 'evidence_stale', '学习证据已有变化，请根据当前证据重新整理报告。', 'reload')
        if op == 'submitReport':
            if r['status'] != 'draft' or r['generation_status'] != 'succeeded' or not body['facts_confirmed']:
                fail(409, 'invalid_transition', '请先完成本人的事实核对。')
            q = self.settings.report_queue
            if not q or 'report_review' not in self.scopes(con, q.reviewer_id) or q.reviewer_id == self.link(con, r['learner_id'])['actor_id']:
                fail(503, 'support_unavailable', '目前没有已配置的报告复核人员，报告仍然保留。', 'contact_support')
            meta = self.meta(con, r['id'])
            c = self.report_case_for(con, r)
            if c:
                c.update(revision=c['revision']+1, status='open', parent_revision=r['revision']+1, allowed_actions=['claimCase'])
                cm = self.meta(con, c['id'])
                cm['assignee'] = q.reviewer_id
                c.update(owner_display_name=q.display_name, due_at=datetime.fromtimestamp(self.clock()+q.due_seconds, timezone.utc).isoformat(), support_contact_label=q.support_contact_label)
            else:
                cid = ident()
                c = dict(id=cid, revision=1, kind='report_review', target_id=r['id'], status='open', owner_display_name=q.display_name, due_at=datetime.fromtimestamp(self.clock()+q.due_seconds, timezone.utc).isoformat(), feedback=None, next_action=action('wait_review', cid, '等待报告复核'), parent_revision=r['revision']+1, allowed_actions=['claimCase'], support_contact_label=q.support_contact_label, learner_id=r['learner_id'])
                cm = {'assignee': q.reviewer_id, 'run_id': r['run_id'], 'evidence': [], 'messages': [], 'decisions': []}
            self.put(con, 'case', c, r['learner_id'], r['run_id'], cm)
            meta['case_id'] = c['id']
            meta['facts_confirmed_revision'] = r['revision']
            r.update(status='pending_review', revision=r['revision']+1, review_id=None)
            self.put(con, 'report', r, private=meta)
        elif op == 'reviewReport':
            c = self.report_staff(con, session, r, 'report_review')
            if r['status'] != 'pending_review' or c['status'] != 'claimed' or body['source_hash'] != r['source_hash']:
                fail(409, 'invalid_transition', '请先认领并核对当前报告及来源。')
            self.report_observations(con, r, body['corrected_observations'])
            disputes = {d['id']: d for d in self.objects(con, 'report_dispute', run=r['run_id']) if d['report_id'] == r['id'] and d['status'] == 'open'}
            resolved = set(body['resolved_dispute_ids'])
            if not resolved <= disputes.keys():
                fail(422, 'invalid_sources', '异议编号不属于当前未处理异议。')
            if body['decision'] == 'approved' and resolved != disputes.keys():
                fail(409, 'unresolved_dispute', '请先逐条处理孩子提出的异议。')
            for did in resolved:
                d = disputes[did]
                d.update(status='resolved', revision=d['revision']+1, parent_revision=r['revision']+1)
                self.put(con, 'report_dispute', d)
            r.update(observations=body['corrected_observations'], revision=r['revision']+1, review_id=ident(), status='pending_review' if body['decision'] == 'approved' else 'draft')
            review = {**body, 'actor_id': session['actor_id'], 'recorded_at': self.stamp(), 'approved_revision': r['revision']}
            con.execute('INSERT INTO learn_report_reviews VALUES(?,?,?,?,?)', (r['review_id'], r['id'], r['revision'], self.report_content_hash(r), canonical(review)))
            c.update(revision=c['revision']+1, parent_revision=r['revision'], feedback=body['note'])
            if body['decision'] == 'changes_requested':
                c.update(status='resolved', allowed_actions=[])
            self.put(con, 'case', c)
            self.put(con, 'report', r)
            self.audit(con, session['actor_id'], 'report_reviewed', r['id'], {'review_id': r['review_id'], 'decision': body['decision']})
        elif op == 'publishReport':
            c = self.report_staff(con, session, r, 'report_publish')
            run = self.obj(con, r['run_id'], 'run')
            enrollment = self.obj(con, run['enrollment_id'], 'enrollment')
            self.entitlement(con, enrollment['entitlement_id'], r['learner_id'], run['course_version_id'])
            if not self.settings.publication_enabled:
                fail(503, 'operation_unavailable', '报告发布尚未开放。')
            approved = con.execute('SELECT * FROM learn_report_reviews WHERE id=? AND report_id=?', (body['review_id'], r['id'])).fetchone()
            if (r['status'] != 'pending_review' or c['status'] != 'claimed' or not approved or body['review_id'] != r['review_id'] or
                    approved['revision'] != r['revision'] or approved['content_hash'] != self.report_content_hash(r) or
                    body['source_hash'] != r['source_hash'] or json.loads(approved['body'])['decision'] != 'approved'):
                fail(409, 'approval_stale', '批准记录与当前报告版本不一致，请重新复核。')
            if any(d['status'] == 'open' and d['report_id'] == r['id'] for d in self.objects(con, 'report_dispute', run=r['run_id'])):
                fail(409, 'unresolved_dispute', '还有未处理的事实异议。')
            if not self.report_consent(con, r['learner_id'], True):
                fail(403, 'consent_required', '家长摘要授权尚未生效或已经撤回。')
            r.update(status='published', revision=r['revision']+1, publication_id=ident(), allowed_actions=[])
            publication = dict(id=r['publication_id'], revision=1, report_id=r['id'], published_revision=r['revision'], published_at=self.stamp(), parent_revision=r['revision'])
            con.execute('INSERT INTO learn_report_publications VALUES(?,?,?,?)', (publication['id'], r['id'], canonical(publication), canonical(r)))
            self.put(con, 'report', r)
            c.update(status='resolved', revision=c['revision']+1, parent_revision=r['revision'], allowed_actions=[])
            self.put(con, 'case', c)
            self.audit(con, session['actor_id'], 'report_published', r['id'], {'publication_id': publication['id'], 'review_id': r['review_id']})
            return publication
        return self.report_projection(con, session, r)
