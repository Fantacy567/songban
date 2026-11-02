"""Explicitly configured P3 model jobs. No environment loading or import-time I/O.

All dispatches are durable before network I/O. An uncertain dispatch is never
retried. Budget units are server-defined accounting units, never currency.
"""
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .course import FACTS, MAT_A, MAT_B, MODEL, ref
from .protocol import Problem, canonical, fail, revision, strict_json


def ident():
    return secrets.token_hex(16)


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='seconds')


@dataclass(frozen=True)
class ReconciliationQueue:
    reviewer_id: str
    display_name: str
    due_seconds: int
    support_contact_label: str
    escalation_actor_id: str


@dataclass(frozen=True)
class ModelSettings:
    config_version: str
    base_url: str = field(repr=False)
    api_key: str = field(repr=False)
    requested_model: str
    allowed_models: tuple
    pricing_version: str
    input_unit_rate: int
    output_unit_rate: int
    max_input_tokens: int
    max_output_tokens: int
    reservation_units: int
    reconciliation_queue: ReconciliationQueue
    timeout_seconds: int = 30
    lease_seconds: int = 90
    transport: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        u = urlsplit(self.base_url)
        positive = (self.input_unit_rate, self.output_unit_rate, self.max_input_tokens,
                    self.max_output_tokens, self.reservation_units, self.timeout_seconds, self.lease_seconds)
        q = self.reconciliation_queue
        if (u.scheme != 'https' or not u.hostname or u.username or u.password or u.query or u.fragment
                or not self.api_key or not self.config_version or len(self.config_version) > 100
                or not self.pricing_version or self.requested_model not in self.allowed_models
                or any(not isinstance(v, str) or not 1 <= len(v) <= 100 for v in self.allowed_models)
                or any(type(v) is not int or v <= 0 for v in positive)
                or self.lease_seconds <= self.timeout_seconds
                or self.reservation_units < self.max_input_tokens*self.input_unit_rate + self.max_output_tokens*self.output_unit_rate
                or not isinstance(q, ReconciliationQueue) or not q.reviewer_id or not q.display_name
                or not q.support_contact_label or not q.escalation_actor_id or q.due_seconds <= 0):
            raise ValueError('Incomplete or unsafe explicit model configuration')

    def fingerprint(self):
        # Hash the credential to detect rotation without persisting its contents.
        return sha([self.config_version, self.base_url, sha(self.api_key), self.requested_model,
                    self.allowed_models, self.pricing_version, self.input_unit_rate,
                    self.output_unit_rate, self.max_input_tokens, self.max_output_tokens,
                    self.reservation_units])


DDL = '''
CREATE TABLE learn_model_accounts (learner_id TEXT PRIMARY KEY REFERENCES learn_learners(id), config_version TEXT NOT NULL, expires REAL NOT NULL, granted INTEGER NOT NULL CHECK(granted>=0), held INTEGER NOT NULL DEFAULT 0 CHECK(held>=0), settled INTEGER NOT NULL DEFAULT 0 CHECK(settled>=0), adjustment INTEGER NOT NULL DEFAULT 0, CHECK(granted+adjustment>=held+settled));
CREATE TABLE learn_model_grants (grant_key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, learner_id TEXT NOT NULL REFERENCES learn_learners(id), units INTEGER NOT NULL);
CREATE TABLE learn_model_jobs (id TEXT PRIMARY KEY REFERENCES learn_course_objects(id), learner_id TEXT NOT NULL REFERENCES learn_learners(id), run_id TEXT NOT NULL REFERENCES learn_course_objects(id), purpose TEXT NOT NULL, target_id TEXT NOT NULL, input_revision INTEGER NOT NULL, state TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES learn_sessions(id), config_hash TEXT NOT NULL, snapshot TEXT NOT NULL, reservation_id TEXT NOT NULL UNIQUE, reserved INTEGER NOT NULL, lease_token TEXT, fence INTEGER NOT NULL DEFAULT 0, lease_until REAL, dispatch_started_at TEXT, provider_request_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
CREATE UNIQUE INDEX learn_model_one_active ON learn_model_jobs(learner_id) WHERE state IN ('pending','running','unknown');
CREATE TABLE learn_model_ledger (model_run_id TEXT PRIMARY KEY REFERENCES learn_model_jobs(id), settlement_kind TEXT NOT NULL, units INTEGER, adjustment_units INTEGER, evidence_ids TEXT NOT NULL, recorded_at TEXT NOT NULL);
CREATE TABLE learn_model_cases (id TEXT PRIMARY KEY, model_run_id TEXT NOT NULL REFERENCES learn_model_jobs(id), assignee_id TEXT NOT NULL REFERENCES people(id), escalation_id TEXT NOT NULL REFERENCES people(id), support_contact_label TEXT NOT NULL, body TEXT NOT NULL, discrepancy INTEGER NOT NULL DEFAULT 0);
CREATE TABLE learn_model_evidence (id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES learn_model_cases(id), body TEXT NOT NULL);
'''


class ModelDomain:
    MODEL_OPS = {'usage', 'reconciliation', 'reconciliations', 'resolveReconciliation', 'createModelRun', 'modelRun', 'help', 'helps'}

    def migrate_models(self):
        checksum = hashlib.sha256(DDL.encode()).hexdigest()
        with self.store.transaction() as con:
            old = con.execute("SELECT checksum FROM learn_migrations WHERE version='M03-models'").fetchone()
            if old:
                if old[0] != checksum:
                    raise ValueError('M03-models checksum mismatch')
                return
            for sql in DDL.split(';'):
                if sql.strip():
                    con.execute(sql)
            con.execute("INSERT INTO learn_migrations VALUES('M03-models',?,?)", (checksum, self.stamp()))

    def model_handles(self, con, op, params):
        return op in self.MODEL_OPS

    def model_configuration_available(self, con=None):
        cfg = self.settings.model_settings
        if not self.settings.enabled or not self.settings.course_enabled or not self.settings.models_enabled or not isinstance(cfg, ModelSettings):
            return False
        if con is None:
            with self.store.transaction() as connection:
                return self.model_configuration_available(connection)
        q = cfg.reconciliation_queue
        return all('usage_reconcile' in self.scopes(con, actor) for actor in (q.reviewer_id, q.escalation_actor_id))

    def grant_model_budget(self, learner_id, units, *, grant_key, config_version, expires_at, authority):
        if not authority or not grant_key or type(units) is not int or units <= 0 or expires_at <= self.clock():
            raise ValueError('An explicit positive budget grant and authority are required')
        cfg = self.settings.model_settings
        if not isinstance(cfg, ModelSettings) or config_version != cfg.config_version:
            raise ValueError('Budget must bind to configured pricing/model version')
        fingerprint = sha([learner_id, units, config_version, expires_at, authority])
        with self.store.transaction() as con:
            previous = con.execute('SELECT fingerprint FROM learn_model_grants WHERE grant_key=?', (grant_key,)).fetchone()
            if previous:
                if previous[0] != fingerprint:
                    fail(409, 'idempotency_conflict', '预算授权号已被使用。')
                return grant_key
            account = con.execute('SELECT * FROM learn_model_accounts WHERE learner_id=?', (learner_id,)).fetchone()
            if account and account['config_version'] != config_version:
                fail(409, 'budget_version_conflict', '预算配置版本须人工迁移。')
            con.execute('INSERT INTO learn_model_accounts(learner_id,config_version,expires,granted) VALUES(?,?,?,?) ON CONFLICT(learner_id) DO UPDATE SET granted=granted+excluded.granted,expires=MAX(expires,excluded.expires)', (learner_id, config_version, expires_at, units))
            con.execute('INSERT INTO learn_model_grants VALUES(?,?,?,?)', (grant_key, fingerprint, learner_id, units))
            self.audit(con, None, 'model_budget_granted', learner_id, {'grant_key': grant_key, 'units': units, 'authority': authority})
        return grant_key

    def _model_access(self, con, run, *, live=False, session_id=None, source_ids=()):
        self.learning_access(con, run['learner_id'])
        enrollment = self.obj(con, run['enrollment_id'], 'enrollment')
        self.entitlement(con, enrollment['entitlement_id'], run['learner_id'], run['course_version_id'])
        self.sources(con, run, source_ids)
        if live:
            rows = con.execute('SELECT * FROM learn_consents WHERE learner_id=?', (run['learner_id'],)).fetchall()
            if not any('live_model' in self.effective(con, r) for r in rows):
                fail(403, 'consent_required', '真实模型授权尚未建立或已撤回。')
        if session_id:
            row = con.execute('SELECT s.*,b.epoch AS current_epoch,b.expires AS browser_expires FROM learn_sessions s JOIN learn_browsers b ON b.id=s.browser_id WHERE s.id=?', (session_id,)).fetchone()
            if not row or row['revoked'] or row['expires'] <= self.clock() or row['browser_expires'] <= self.clock() or row['epoch'] != row['current_epoch'] or row['learner_id'] != run['learner_id'] or row['mode'] != 'learner':
                fail(403, 'session_revoked', '发起身份已经失效。')

    def model_usage(self, con, learner_id, *, child=False, source='unknown'):
        row = con.execute('SELECT * FROM learn_model_accounts WHERE learner_id=?', (learner_id,)).fetchone()
        active = con.execute("SELECT 1 FROM learn_model_jobs WHERE learner_id=? AND state IN ('pending','running','unknown')", (learner_id,)).fetchone()
        available = row['granted']+row['adjustment']-row['held']-row['settled'] if row else None
        state = 'unconfigured' if not row else 'held_for_review' if active else 'exhausted' if available == 0 or row['expires'] <= self.clock() else 'available'
        notice = {'unconfigured': '真实模型预算尚未配置。', 'held_for_review': '本次额度已保留，请等待结果或人工核对，勿重复生成。', 'exhausted': '本次可用额度不足，请联系支持。', 'available': '已配置练习额度；费用估值尚未知。'}[state]
        value = {'status': state, 'notice': notice}
        if not child:
            value.update(available_units=available, held_units=row['held'] if row else None, settled_units=row['settled'] if row else None, cost_estimate=None, usage_source=source)
        return value

    def _reconciliation(self, con, session, case_id):
        self.role(session, 'staff')
        row = con.execute('SELECT * FROM learn_model_cases WHERE id=?', (case_id,)).fetchone()
        if not row or 'usage_reconcile' not in self.scopes(con, session['actor_id']) or row['assignee_id'] != session['actor_id']:
            fail(404, 'resource_not_found', '找不到可访问的用量核对案。')
        return row, json.loads(row['body'])

    def model_reconciliation_list(self, con, session):
        self.role(session, 'staff')
        if 'usage_reconcile' not in self.scopes(con, session['actor_id']):
            return []
        return [json.loads(r[0]) for r in con.execute('SELECT body FROM learn_model_cases WHERE assignee_id=? ORDER BY rowid', (session['actor_id'],))]

    def model_authorize(self, con, op, session, params, body):
        if op == 'resolveReconciliation':
            self._reconciliation(con, session, params['case_id'])
            return
        self.course_authorize(con, op, session, params, body)
        if op == 'createModelRun' and body['mode'] == 'live':
            attempt = self.owned(con, session, params['attempt_id'], 'attempt')
            self._model_access(con, self.run_for(con, attempt), live=True)
        if op == 'createModelRun' and body['mode'] == 'replay' and body.get('replay_of'):
            self.model_read(con, 'modelRun', session, {'model_run_id':body['replay_of']}, {})
        if op == 'help':
            run = self.owned(con, session, params['run_id'], 'run')
            if body['mode'] == 'live':
                self._model_access(con, run, live=True)
            # Central HTTP idempotency may return a completed replay Help. Recheck
            # its original live consent before allowing that cached payload out.
            prior = con.execute("SELECT result FROM learn_requests WHERE actor_id=? AND scope_id=? AND operation='help' AND request_id=?",(session['actor_id'],run['id'],body['request_id'])).fetchone()
            if prior:
                previous = json.loads(prior['result'])
                if previous.get('model_run_id'):
                    self.model_read(con,'modelRun',session,{'model_run_id':previous['model_run_id']},{})

    def model_read(self, con, op, session, params, query):
        if op == 'reconciliations':
            rows = self.model_reconciliation_list(con, session)
            rows, cursor = self.page(con, session, 'reconciliations', rows, query)
            return {'items': rows, 'next_cursor': cursor}
        if op == 'helps':
            result = self.course_read(con, op, session, params, query)
            for item in result['items']:
                if item['model_run_id']:
                    try:
                        model = self.model_read(con, 'modelRun', session, {'model_run_id':item['model_run_id']}, {})
                        if model['visibility'] == 'restricted':
                            item.update(text=None, actions=[])
                    except Problem:
                        item.update(text=None, actions=[])
            return result
        if op == 'usage':
            self.learner(con, session, params['learner_id'])
            return self.model_usage(con, params['learner_id'], child=session['mode'] == 'learner')
        if op == 'reconciliation':
            return self._reconciliation(con, session, params['case_id'])[1]
        if op == 'modelRun':
            mid = params['model_run_id']
            if session['mode'] == 'staff':
                model = self.obj(con, mid, 'model')
                self._reconciliation(con, session, model['reconciliation_case_id'])
                # Reconciliation staff can inspect metering, not children's raw output.
                return dict(model, output_text=None, visibility='restricted')
            self.role(session, 'learner')
            model = self.owned(con, session, mid, 'model')
            meta = self.meta(con, mid)
            row = con.execute('SELECT run_id FROM learn_course_objects WHERE id=?', (mid,)).fetchone()
            self._model_access(con, self.obj(con, row[0], 'run'), live=model['mode'] == 'live' or meta.get('origin_mode') == 'live', source_ids=meta.get('source_ids', []))
            if model['report_id']:
                self.report_access(con, session, model['report_id'])
            return dict(model, output_text=None) if model['visibility'] == 'restricted' else model
        fail(404, 'resource_not_found', '找不到模型操作。')

    def _roles(self):
        return json.loads(Path(__file__).with_name('learning_roles.json').read_text(encoding='utf-8'))

    def model_tool_card(self):
        card = self._roles()['tool_card']
        return {k:card[k] for k in ('id','version','steps','prompt_template','checks','notice')}

    def project_model_sources(self, con, run, role_id, source_ids):
        registry = self._roles()
        if role_id not in registry['roles']:
            fail(422, 'invalid_role', '未知的学习角色。')
        self.sources(con, run, source_ids)
        allowed = registry['roles'][role_id]['kinds']
        fields = {'requirements': ('facts','purpose','expression_preference'), 'attempt': ('input_text','kind'),
                  'version': ('content','change_explanation'), 'self': ('field','judgement','reason'),
                  'reflection': ('change_explanation','judgement'), 'help': ('role_id','help_level','text','mode'),
                  'check': ('rule_result','feedback','missing_evidence','human_result')}
        values = []
        for sid in source_ids:
            if sid in (MAT_A, MAT_B):
                kind = 'material'
                obj = self.active_material(con, run['course_version_id'], sid)
                content = {k: obj[k] for k in ('facts', 'source_locators')}
            else:
                row = con.execute('SELECT kind,body FROM learn_course_objects WHERE id=?', (sid,)).fetchone()
                kind, obj = row['kind'], json.loads(row['body'])
                content = {k: obj[k] for k in fields.get(kind, ()) if k in obj}
            if kind not in allowed:
                fail(422, 'role_source_forbidden', '该角色不需要读取这类资料。')
            values.append({'source_id': sid, 'source_version': str(obj.get('revision', obj.get('version', 1))),
                           'source_domain': 'learning_v2', 'nature': 'child_statement' if kind in ('requirements','attempt','version','self','reflection') else 'system_record', 'content': content})
        return values

    def model_write(self, con, op, session, params, body):
        if op == 'resolveReconciliation':
            return self._resolve_model_case(con, session, params['case_id'], body), None
        self.model_authorize(con, op, session, params, body)
        if op == 'createModelRun':
            attempt = self.owned(con, session, params['attempt_id'], 'attempt')
            revision(body['expected_revision'], attempt['revision'])
            run = self.run_for(con, attempt)
            self.stage(run, 'create')
            if attempt['kind'] != 'practice' or ref(attempt) != run['current_attempt_ref'] or attempt['requirements_ref'] != run['current_requirements_ref']:
                fail(409, 'stale_evidence', '请使用当前练习输入与要求。')
            req = self.evidence(con, run, attempt['requirements_ref'], 'requirements')
            self.active_material(con, run['course_version_id'], MAT_A)
            payload = {'input_text': attempt['input_text'], 'requirements': {k: req[k] for k in ('facts','purpose','expression_preference')}, 'source_ids': [MAT_A, req['id'], attempt['id']]}
            value = self.queue_model(con, session, run, mode=body['mode'], purpose='attempt', input_payload=payload, config_version=body['config_version'], attempt=attempt, replay_of=body['replay_of'])
            run['active_model_run_id'] = value['id']
            self.update_run(con, run, invalidate=True)
            return value, None
        if op == 'help':
            run = self.owned(con, session, params['run_id'], 'run')
            revision(body['expected_revision'], run['revision'])
            cards = self.obj(con, run['course_version_id'], 'course')['task_cards']
            card = next((c for c in cards if c['id'] == body['task_id'] and c['version'] == body['task_card_version']), None)
            if not card:
                fail(422, 'invalid_sources', '任务卡版本不匹配。')
            self.stage(run, card['stage'])
            sources = self.project_model_sources(con, run, body['role_id'], body['source_ids'])
            role = self._roles()['roles'][body['role_id']]
            value = dict(id=ident(), revision=1, run_id=run['id'], role_id=body['role_id'], prompt_version=role['prompt_version'], help_level=body['help_level'], mode=body['mode'], text=None, sources=[{k:v for k,v in s.items() if k!='content'} for s in sources], actions=[], model_run_id=None, parent_revision=run['revision']+1, task_id=card['id'], task_card_version=card['version'])
            private = {'question': body['question'], 'source_ids': body['source_ids'], 'content_version': self._roles()['version'], 'created_at': self.stamp()}
            if body['mode'] == 'static':
                value.update(text=role['hints'][body['help_level']-1], actions=['open_tool_card','request_human_help'])
                self.put(con, 'help', value, run['learner_id'], run['id'], private)
            else:
                # NewHelp has no replay_of: reuse the most recent exact matching input.
                payload = {'role_id':body['role_id'], 'help_level':body['help_level'], 'question':body['question'], 'task':{k:card[k] for k in ('id','version','stage','goal','instructions')}, 'sources':sources, 'source_ids':body['source_ids']}
                if self.settings.studio_enabled:
                    value['prompt_version'] = role['prompt_version'] + '+studio.1'
                    payload['workbench'] = self.studio_teaching_context(card['stage'])
                    payload['conversation'] = self.recent_teaching_context(con, session, run, body)
                    entry = self.confirmed_entry_context(con, session, run['learner_id'])
                    if entry:
                        payload['learner_self_report'] = entry
                replay = None
                if body['mode'] == 'replay':
                    replay = next((m['id'] for m in reversed(self.objects(con, 'model', run=run['id'])) if m['help_event_id'] and m['status']=='succeeded' and self.meta(con,m['id']).get('input_hash')==sha(payload)), None)
                    if not replay:
                        fail(409, 'replay_unavailable', '没有相同输入的可用帮助回放。')
                self.put(con, 'help', value, run['learner_id'], run['id'], private)
                model = self.queue_model(con, session, run, mode=body['mode'], purpose='help', input_payload=payload, help_event=value, replay_of=replay)
                value = self.obj(con, value['id'], 'help')
                if value['model_run_id'] != model['id']:
                    value.update(model_run_id=model['id'], revision=value['revision']+1)
                    self.put(con, 'help', value)
            self.update_run(con, run, invalidate=True)
            return self.help_projection(con, value), None
        fail(404, 'resource_not_found', '找不到模型操作。')

    def studio_teaching_context(self, stage):
        """Versioned product capabilities, not inferred learner abilities."""
        return {'version': 'invitation-studio-context@0.1.0', 'kind': 'controlled_text_invitation',
                'current_stage': stage, 'current_steps': {
                    'clarify': ['展开当前动手小任务', '阅读活动资料', '自己填写并保存要求', '核对后进入下一步'],
                    'create': ['展开当前动手小任务', '保存工具输入', '生成候选', '核对后保存这张作品', '打开已保存的作品'],
                    'review': ['做一次自己的检查', '亲手改进一处并另存版本', '换材料尝试', '写复盘并明确送老师复核'],
                }[stage],
                'limits': '本页只编辑文字字段并在平台保存作品；没有页面大小、横竖方向、外部空白画布、下载文件命名或上传文件的必做步骤。候选、保存、本人打开确认、过关和发布分别处理。'}

    def recent_teaching_context(self, con, session, run, body):
        """Small, authorized context; old full transcripts never enter the prompt."""
        history = []
        for item in reversed(self.objects(con, 'help', run=run['id'])):
            if item['task_id'] != body['task_id'] or item['task_card_version'] != body['task_card_version']:
                continue
            meta = self.meta(con, item['id'])
            question = meta.get('question')
            if not question or question == body['question'] or not set(meta.get('source_ids', [])) <= set(body['source_ids']):
                continue
            if item['model_run_id']:
                try:
                    model = self.model_read(con, 'modelRun', session, {'model_run_id': item['model_run_id']}, {})
                    if model['visibility'] != 'normal' or model['status'] != 'succeeded':
                        continue
                except Problem:
                    continue
            if item.get('text'):
                history.append({'help_id': item['id'], 'question': question[:500], 'reply': item['text'][:800], 'mode': item['mode']})
            if len(history) == 4:
                break
        return list(reversed(history))

    def _model_messages(self, purpose, payload):
        rules = self._roles()
        instruction = rules['system_rule']
        if purpose == 'help':
            role = rules['roles'][payload['role_id']]
            instruction += ' 当前角色：'+role['name']+'。只返回 {"text":提示,"actions":[建议动作],"source_ids":[引用]}。动作仅 open_tool_card/save_candidate/request_human_help。'
            if payload['role_id'] == 'tool_guide':
                instruction += ' 当前工具卡：'+canonical(rules['tool_card'])
            if 'workbench' in payload:
                instruction += (' 当前教学环境是松伴内置的受控文字邀请卡工作台。'
                    '只能依据workbench和当前task描述建议页面实际支持的操作，不得发明控件、外部软件或设置步骤。'
                    '历史回复可能不适合当前页面，不要继续错误指引。每次先给一个孩子能自己完成的小动作；'
                    '不确定界面时请孩子展开当前动手小任务，不要猜测。')
        elif purpose == 'attempt':
            instruction += ' 仅返回邀请候选 JSON，字段 title/audience/date/start_time/end_time/place/preparation/invitation_line；事实不补造，不含HTML、网址或联系方式。'
        else:
            instruction += ' 只读取冻结事实，不执行实验。仅返回 {"observations":[{"text":"观察","source_ids":["来源ID"],"nature":"ai_suggestion"}],"limitations":["限制说明"]}；每条观察必须引用提供的sources中ref.source_id。不推断人格、排名或天赋。'
        return [{'role':'system','content':instruction}, {'role':'user','content':canonical({'untrusted_learning_data':payload})}]

    def queue_model(self, con, session, run, *, mode, purpose, input_payload, config_version=None, attempt=None, help_event=None, report=None, replay_of=None):
        self.role(session, 'learner')
        self.learner(con, session, run['learner_id'])
        self.course_guard()
        if mode not in ('mock','live','replay') or purpose not in ('attempt','help','report') or (mode=='replay') != bool(replay_of):
            fail(422, 'invalid_model_mode', '模型模式或回放来源不匹配。')
        target = {'attempt':attempt, 'help':help_event, 'report':report}[purpose]
        if not isinstance(target, dict) or not target.get('id'):
            fail(422, 'invalid_model_target', '模型任务缺少已保存目标。')
        source_ids = input_payload.get('source_ids', [])
        if purpose == 'report':
            source_ids = [s['ref']['source_id'] for s in input_payload.get('sources', [])]
            if not self.report_consent(con, run['learner_id']):
                fail(403, 'consent_required', '报告授权尚未建立或已撤回。')
        self._model_access(con, run, live=mode=='live', session_id=session['id'], source_ids=source_ids)
        if purpose == 'attempt':
            for previous in self.objects(con,'model',run=run['id']):
                if previous['attempt_id']!=target['id'] or previous['input_revision']!=target['revision']:
                    continue
                settled = con.execute('SELECT 1 FROM learn_model_ledger WHERE model_run_id=?',(previous['id'],)).fetchone()
                if previous['status']!='failed' or (previous['mode']=='live' and not settled):
                    fail(409,'model_run_exists','这版输入已有运行，请读取原结果。')
        if (con.execute("SELECT 1 FROM learn_model_jobs WHERE learner_id=? AND state IN ('pending','running','unknown')", (run['learner_id'],)).fetchone()
                or any(m['status'] in ('pending','running','unknown') for m in self.objects(con,'model',lid=run['learner_id']))):
            fail(409,'model_run_unsettled','该学习者已有运行或用量待核对。')
        mid = ident()
        private = {'input_snapshot': input_payload, 'input_hash': sha(input_payload), 'source_ids':source_ids, 'purpose':purpose, 'prompt_version':help_event['prompt_version'] if help_event else self._roles()['version'], 'content_version':self._roles()['version'], 'created_at':self.stamp(), 'truncated':False}
        value = dict(id=mid, revision=1, attempt_id=attempt['id'] if attempt else None, report_id=report['id'] if report else None, help_event_id=help_event['id'] if help_event else None, mode=mode, status='pending', requested_model=None, actual_model=None, config_version=config_version or MODEL, input_revision=target['revision'], output_text=None, reservation_id=None, usage={'status':'unconfigured','notice':'模拟或回放不会调用真实模型，也不代表真实费用为零。'}, reconciliation_case_id=None, visibility='normal', parent_revision=target['revision'])
        if mode == 'live':
            cfg = self.settings.model_settings
            if not self.model_configuration_available(con) or (config_version is not None and config_version != cfg.config_version):
                fail(503,'model_configuration_unavailable','真实模型配置或核对值班尚不可用。','contact_support')
            messages = self._model_messages(purpose, input_payload)
            # UTF-8 bytes conservatively bound text tokens; explicit margin covers framing.
            if len(canonical(messages).encode('utf-8')) + 256 > cfg.max_input_tokens:
                fail(422,'model_input_too_large','资料超过本次额度允许范围，请缩小选取范围。')
            account = con.execute('SELECT * FROM learn_model_accounts WHERE learner_id=?', (run['learner_id'],)).fetchone()
            if not account or account['expires'] <= self.clock() or account['config_version'] != cfg.config_version:
                fail(403,'model_budget_required','需要当前配置的有效练习预算。','contact_support')
            updated = con.execute('UPDATE learn_model_accounts SET held=held+? WHERE learner_id=? AND granted+adjustment-settled-held>=?', (cfg.reservation_units,run['learner_id'],cfg.reservation_units))
            if updated.rowcount != 1:
                fail(409,'model_budget_exhausted','可用练习额度不足。','contact_support')
            value.update(requested_model=cfg.requested_model, config_version=cfg.config_version, reservation_id=ident(), usage={'status':'held_for_review','notice':'已保存输入并保留额度，等待运行结果。'})
            q = cfg.reconciliation_queue
            snapshot = dict(private, messages=messages, allowed_models=list(cfg.allowed_models), pricing_version=cfg.pricing_version, input_rate=cfg.input_unit_rate, output_rate=cfg.output_unit_rate, max_input=cfg.max_input_tokens, max_output=cfg.max_output_tokens, queue={'reviewer_id':q.reviewer_id,'display_name':q.display_name,'due_seconds':q.due_seconds,'support_contact_label':q.support_contact_label,'escalation_actor_id':q.escalation_actor_id})
            self.put(con,'model',value,run['learner_id'],run['id'],private)
            con.execute('INSERT INTO learn_model_jobs(id,learner_id,run_id,purpose,target_id,input_revision,state,session_id,config_hash,snapshot,reservation_id,reserved,provider_request_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (mid,run['learner_id'],run['id'],purpose,target['id'],target['revision'],'pending',session['id'],cfg.fingerprint(),canonical(snapshot),value['reservation_id'],cfg.reservation_units,ident(),self.stamp()))
        else:
            if mode == 'mock':
                if not self.settings.mock_enabled or config_version not in (None, MODEL):
                    fail(503,'model_mode_unavailable','模拟练习尚未开放。')
                output = self._mock_model_output(purpose, input_payload)
            else:
                source = self.model_read(con,'modelRun',session,{'model_run_id':replay_of},{})
                old = self.meta(con,replay_of)
                row = con.execute('SELECT run_id FROM learn_course_objects WHERE id=?',(replay_of,)).fetchone()
                if source['status']!='succeeded' or source['visibility']!='normal' or not source['output_text'] or row[0]!=run['id'] or old.get('purpose','attempt')!=purpose or (purpose!='attempt' and old.get('input_hash')!=private['input_hash']):
                    fail(409,'replay_unavailable','来源不能用于当前回放。')
                output=source['output_text']
                value.update(actual_model=source['actual_model'],config_version=source['config_version'])
                private.update(replay_of=replay_of, replayed_from_at=old.get('created_at'), origin_mode=old.get('origin_mode',source['mode']))
                private['source_ids'] = list(dict.fromkeys(source_ids+old.get('source_ids', [])))
            value.update(status='succeeded',output_text=self._validate_model_output(purpose,output,input_payload))
            private['output_hash']=sha(value['output_text'])
            self.put(con,'model',value,run['learner_id'],run['id'],private)
            self._complete_model_target(con,value)
        self.audit(con, session['actor_id'],'model_queued',mid,{'mode':mode,'purpose':purpose})
        return value

    def _mock_model_output(self, purpose, payload):
        if purpose=='attempt':
            facts=payload['requirements']['facts']
            card={k:facts[k] for k in FACTS if k!='event_name'}
            card.update(title=facts['event_name'][:40],invitation_line='欢迎来参加这次活动。')
            return canonical(card)
        if purpose=='help':
            return canonical({'text':self._roles()['roles'][payload['role_id']]['hints'][payload['help_level']-1], 'actions':['open_tool_card','request_human_help'], 'source_ids':payload['source_ids']})
        sources = payload.get('sources', [])
        if not sources:
            fail(422, 'invalid_sources', '报告没有可引用的冻结事实。')
        return canonical({'observations':[{'text':'已保存本次作品与过程记录；这不单独证明已掌握或独立完成。', 'source_ids':[sources[0]['ref']['source_id']], 'nature':'ai_suggestion'}], 'limitations':['mock 模拟报告只整理已保存事实，尚不能据此判断学习变化。']})

    def _validate_model_output(self, purpose, output, payload):
        if not isinstance(output,str) or not 1<=len(output)<=8000 or any(x in output.lower() for x in ('<script','javascript:','http://','https://','<iframe','<img')):
            fail(422,'invalid_model_output','模型内容未通过安全格式检查。')
        data=strict_json(output)
        if purpose=='attempt':
            self.contract.check(data,self.contract.schemas['CardText'])
        elif purpose=='help':
            if (not isinstance(data,dict) or set(data)!={'text','actions','source_ids'} or not isinstance(data['text'],str) or not 1<=len(data['text'])<=4000
                or not isinstance(data['actions'],list) or any(a not in ('open_tool_card','save_candidate','request_human_help') for a in data['actions'])
                or not isinstance(data['source_ids'],list) or any(s not in payload['source_ids'] for s in data['source_ids'])):
                fail(422,'invalid_model_output','帮助内容或建议超出本次许可范围。')
        else:
            if not isinstance(data,dict) or set(data)!={'observations','limitations'} or not isinstance(data['observations'],list) or not isinstance(data['limitations'],list):
                fail(422,'invalid_model_output','报告生成结构不正确。')
            self.contract.check(data['observations'], {'type':'array','minItems':1,'maxItems':100,'items':{'$ref':'#/components/schemas/Observation'}})
            ids = {s['ref']['source_id'] for s in payload.get('sources', [])}
            if any(o['nature']!='ai_suggestion' or not set(o['source_ids']) <= ids for o in data['observations']):
                fail(422, 'invalid_sources', '报告观察必须标为AI建议并引用冻结事实。')
            if len(data['limitations'])>90 or any(not isinstance(v,str) or not 1<=len(v)<=8000 for v in data['limitations']):
                fail(422, 'invalid_model_output', '报告限制说明格式不正确。')
        return canonical(data)

    def _complete_model_target(self, con, model):
        if model['report_id']:
            self.complete_report_generation(con,model['report_id'],model)
        if model['help_event_id']:
            help_event=self.obj(con,model['help_event_id'],'help')
            help_event.update(revision=help_event['revision']+1,model_run_id=model['id'])
            if model['status']=='succeeded' and model['visibility']=='normal':
                output=json.loads(model['output_text'])
                help_event.update(text=output['text'],actions=output['actions'])
            self.put(con,'help',help_event)

    def _settle_model(self, con, job, kind, units=None, adjustment=None, evidence_ids=()):
        if con.execute('SELECT 1 FROM learn_model_ledger WHERE model_run_id=?',(job['id'],)).fetchone():
            return False
        if units is not None and (type(units) is not int or units<0 or units>job['reserved']):
            fail(422,'invalid_settlement','结算超出预占范围，请人工处理。')
        adjustment=adjustment or 0
        con.execute('UPDATE learn_model_accounts SET held=held-?,settled=settled+?,adjustment=adjustment+? WHERE learner_id=?',(job['reserved'],units or 0,adjustment,job['learner_id']))
        con.execute('INSERT INTO learn_model_ledger VALUES(?,?,?,?,?,?)',(job['id'],kind,units,adjustment if kind=='administrative_adjustment' else None,canonical(list(evidence_ids)),self.stamp()))
        con.execute("UPDATE learn_model_jobs SET state='done',lease_token=NULL WHERE id=?",(job['id'],))
        return True

    def _new_model_case(self, con, job, *, discrepancy=False):
        snapshot=json.loads(job['snapshot']); q=snapshot['queue']
        cid=ident()
        case=dict(id=cid,revision=1,model_run_id=job['id'],status='open',owner_display_name=q['display_name'],due_at=stamp(self.clock()+q['due_seconds']),usage=self.model_usage(con,job['learner_id']),resolution=None)
        con.execute('INSERT INTO learn_model_cases VALUES(?,?,?,?,?,?,?)',(cid,job['id'],q['reviewer_id'],q['escalation_actor_id'],q['support_contact_label'],canonical(case),int(discrepancy)))
        return cid

    def _unknown_model(self, con, job, reason):
        model=self.obj(con,job['id'],'model')
        if job['state']=='done':
            return
        con.execute("UPDATE learn_model_jobs SET state='unknown',fence=fence+1,lease_token=NULL WHERE id=?",(job['id'],))
        if not model['reconciliation_case_id']:
            model['reconciliation_case_id']=self._new_model_case(con,job)
        model.update(status='unknown',revision=model['revision']+1,usage={'status':'held_for_review','notice':'结果或费用尚未知，已保留额度并交由人员核对。'})
        self.put(con,'model',model)
        self._complete_model_target(con,model)
        self.audit(con,None,'model_unknown',job['id'],{'reason':reason})

    def recover_model_jobs(self):
        count=0
        with self.store.transaction() as con:
            for job in con.execute("SELECT * FROM learn_model_jobs WHERE state='running' AND lease_until<=?",(self.clock(),)).fetchall():
                if job['dispatch_started_at']:
                    self._unknown_model(con,job,'expired_dispatched_lease')
                else:
                    con.execute("UPDATE learn_model_jobs SET state='pending',fence=fence+1,lease_token=NULL WHERE id=?",(job['id'],))
                count+=1
            for row in con.execute('SELECT * FROM learn_model_cases').fetchall():
                case=json.loads(row['body'])
                if case['status']=='open' and datetime.fromisoformat(case['due_at']).timestamp()<=self.clock():
                    case.update(status='escalated',revision=case['revision']+1,owner_display_name=row['support_contact_label']+'（升级核对）')
                    # Escalation never releases reservations or re-dispatches.
                    con.execute('UPDATE learn_model_cases SET assignee_id=?,body=? WHERE id=?',(row['escalation_id'],canonical(case),row['id']))
                    self.audit(con,None,'model_case_escalated',row['id'])
        return count

    def process_model_jobs(self, limit=1):
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError('A bounded worker batch is required')
        self.recover_model_jobs()
        processed=0
        for _ in range(limit):
            with self.store.transaction() as con:
                job=con.execute("SELECT * FROM learn_model_jobs WHERE state='pending' ORDER BY rowid LIMIT 1").fetchone()
                if not job:
                    break
                cfg=self.settings.model_settings
                snapshot=json.loads(job['snapshot'])
                try:
                    if not self.model_configuration_available(con) or cfg.fingerprint()!=job['config_hash']:
                        fail(503,'model_configuration_changed','模型配置已变化。')
                    run=self.obj(con,job['run_id'],'run')
                    self._model_access(con,run,live=True,session_id=job['session_id'],source_ids=snapshot['source_ids'])
                    if job['purpose']=='report' and (not self.report_consent(con,run['learner_id']) or self.report_changed(con,self.obj(con,job['target_id'],'report'))):
                        fail(403,'consent_required','报告来源或授权已经变化。')
                    account=con.execute('SELECT * FROM learn_model_accounts WHERE learner_id=?',(job['learner_id'],)).fetchone()
                    if account['expires']<=self.clock() or account['config_version']!=cfg.config_version:
                        fail(403,'model_budget_required','预算授权已到期。')
                    if job['purpose']=='attempt':
                        attempt=self.obj(con,job['target_id'],'attempt')
                        if attempt['revision']!=job['input_revision'] or ref(attempt)!=run['current_attempt_ref'] or attempt['requirements_ref']!=run['current_requirements_ref']:
                            fail(409,'stale_evidence','输入已经更新。')
                except Problem:
                    self._settle_model(con,job,'confirmed_not_dispatched',0)
                    model=self.obj(con,job['id'],'model')
                    model.update(revision=model['revision']+1,status='failed',visibility='restricted',usage=self.model_usage(con,job['learner_id'],child=True))
                    self.put(con,'model',model); self._complete_model_target(con,model)
                    processed+=1
                    continue
                token=ident(); fence=job['fence']+1
                con.execute("UPDATE learn_model_jobs SET state='running',lease_token=?,fence=?,lease_until=?,dispatch_started_at=? WHERE id=?",(token,fence,self.clock()+cfg.lease_seconds,self.stamp(),job['id']))
                model=self.obj(con,job['id'],'model'); model.update(status='running',revision=model['revision']+1)
                self.put(con,'model',model)
                dispatch=dict(job); dispatch.update(lease_token=token,fence=fence,state='running')
            # No SQLite transaction is held across provider I/O. No automatic retry.
            try:
                from app.model_transport import post_chat_completion
                body={'model':cfg.requested_model,'messages':snapshot['messages'],'max_tokens':cfg.max_output_tokens,'stream':False,'response_format':{'type':'json_object'}}
                if urlsplit(cfg.base_url).hostname == 'api.deepseek.com':
                    body['thinking']={'type':'disabled'}
                response=post_chat_completion(cfg.base_url,cfg.api_key,body,cfg.timeout_seconds,attempts=1,follow_redirects=False,trust_env=False,transport=cfg.transport)
                response.raise_for_status()
                payload=response.json()
            except Exception:
                payload=None  # Never persist exception messages, URLs, headers or secrets.
            self._finish_model_dispatch(dispatch,payload)
            processed+=1
        return processed

    def _finish_model_dispatch(self, dispatch, response):
        with self.store.transaction() as con:
            job=con.execute('SELECT * FROM learn_model_jobs WHERE id=?',(dispatch['id'],)).fetchone()
            if not job or job['state']!='running' or job['fence']!=dispatch['fence'] or job['lease_token']!=dispatch['lease_token'] or job['provider_request_id']!=dispatch['provider_request_id']:
                if job:
                    self.audit(con,None,'model_late_response',job['id'],{'response_hash':sha(response) if response is not None else None})
                    # Do not overwrite an operator's resolution or settle twice.
                    if job['state']=='done' and response is not None:
                        self._new_model_case(con,job,discrepancy=True)
                return
            if job['lease_until'] <= self.clock():
                self._unknown_model(con,job,'response_after_lease_expiry')
                return
            snapshot=json.loads(job['snapshot'])
            usage=response.get('usage') if isinstance(response,dict) else None
            units=None
            if isinstance(usage,dict) and all(type(usage.get(k)) is int and usage[k]>=0 for k in ('prompt_tokens','completion_tokens')):
                units=usage['prompt_tokens']*snapshot['input_rate']+usage['completion_tokens']*snapshot['output_rate']
                if units>job['reserved'] or usage['prompt_tokens']>snapshot['max_input'] or usage['completion_tokens']>snapshot['max_output']:
                    units=None
            model=self.obj(con,job['id'],'model'); private=self.meta(con,job['id'])
            private['response_received_at']=self.stamp()
            private['provider_usage']={k:usage[k] for k in ('prompt_tokens','completion_tokens') if isinstance(usage,dict) and type(usage.get(k)) is int and usage[k]>=0}
            response_id=response.get('id') if isinstance(response,dict) else None
            private['provider_response_id']=response_id if isinstance(response_id,str) and 1<=len(response_id)<=100 else None
            actual=response.get('model') if isinstance(response,dict) else None
            if isinstance(actual,str) and 1<=len(actual)<=100:
                model['actual_model']=actual
            output=None
            try:
                choice=response['choices'][0]
                private['truncated']=choice.get('finish_reason')=='length'
                if private['truncated'] or choice.get('finish_reason') not in ('stop',None):
                    raise ValueError('incomplete')
                output=self._validate_model_output(job['purpose'],choice['message']['content'],snapshot['input_snapshot'])
                if actual is not None and actual not in snapshot['allowed_models']:
                    output=None
            except (Problem,KeyError,IndexError,TypeError,ValueError,AttributeError):
                output=None
            visible=True
            try:
                self._model_access(con,self.obj(con,job['run_id'],'run'),live=True,source_ids=snapshot['source_ids'])
                if model['report_id']:
                    report = self.obj(con,model['report_id'],'report')
                    if report['status']=='revoked' or not self.report_consent(con,job['learner_id']) or self.report_changed(con,report):
                        fail(403,'report_access_revoked','报告来源或授权已变化。')
            except Problem:
                visible=False
            private.update(output_hash=sha(output) if output else None, usage_source='provider' if units is not None else 'unknown')
            # Unknown cost retains output only in the restricted server archive.
            if output and (not visible or units is None):
                private['restricted_output']=output
            model.update(visibility='normal' if visible else 'restricted')
            if units is None:
                self.put(con,'model',dict(model,revision=model['revision']+1),private=private)
                self._unknown_model(con,job,'unknown_usage_or_response')
                return
            self._settle_model(con,job,'provider',units)
            model.update(status='succeeded' if output else 'failed',revision=model['revision']+1,output_text=output if visible else None,usage=self.model_usage(con,job['learner_id'],child=True))
            self.put(con,'model',model,private=private)
            # Invalid report generation must not roll back metering.
            try:
                self._complete_model_target(con,model)
            except Problem:
                model.update(status='failed',output_text=None,revision=model['revision']+1)
                self.put(con,'model',model)
                self._complete_model_target(con,model)

    def record_reconciliation_evidence(self, case_id, *, evidence_id, settled_units=None, output_text=None, actual_model=None, confirms_no_charge=False, authority):
        if (not authority or not evidence_id or (settled_units is not None and (type(settled_units) is not int or settled_units<0)) or (confirms_no_charge and settled_units not in (None,0))
                or (actual_model is not None and (not isinstance(actual_model,str) or not 1<=len(actual_model)<=100))):
            raise ValueError('Explicit verified evidence and authority are required')
        value=dict(settled_units=settled_units,output_text=output_text,actual_model=actual_model,confirms_no_charge=confirms_no_charge,authority=authority)
        with self.store.transaction() as con:
            if not con.execute('SELECT 1 FROM learn_model_cases WHERE id=?',(case_id,)).fetchone():
                fail(404,'resource_not_found','核对案不存在。')
            old=con.execute('SELECT case_id,body FROM learn_model_evidence WHERE id=?',(evidence_id,)).fetchone()
            if old:
                if old['case_id']!=case_id or old['body']!=canonical(value):
                    fail(409,'idempotency_conflict','核对依据编号已使用。')
                return evidence_id
            con.execute('INSERT INTO learn_model_evidence VALUES(?,?,?)',(evidence_id,case_id,canonical(value)))
            self.audit(con,None,'model_evidence_recorded',case_id,{'evidence_id':evidence_id,'authority':authority})
        return evidence_id

    def _resolve_model_case(self, con, session, case_id, body):
        row,case=self._reconciliation(con,session,case_id)
        revision(body['expected_revision'],case['revision'])
        if case['status']=='resolved':
            fail(409,'case_resolved','核对案已结案。')
        evidence=[]
        for eid in body['evidence_ids']:
            e=con.execute('SELECT body FROM learn_model_evidence WHERE id=? AND case_id=?',(eid,case_id)).fetchone()
            if not e:
                fail(422,'invalid_sources','核对依据必须由受控核查录入。')
            evidence.append(json.loads(e[0]))
        if not evidence:
            fail(422,'invalid_sources','必须提供核对依据。')
        job=con.execute('SELECT * FROM learn_model_jobs WHERE id=?',(case['model_run_id'],)).fetchone()
        model=self.obj(con,job['id'],'model'); kind=body['resolution']; units=body['settled_units']; adjustment=body['adjustment_units']
        output=None
        if row['discrepancy']:
            # A separate evidence-only case preserves the original unique ledger.
            if kind!='administrative_adjustment' or units is not None or adjustment!=0:
                fail(422,'settlement_already_recorded','差异案只记录核查结果，不重复结算；额外账务须单独授权。')
        elif kind=='administrative_adjustment':
            if units is not None or type(adjustment) is not int or adjustment != -job['reserved']:
                fail(422,'invalid_settlement','行政关闭须以独立负向调整抵销全部预占，真实费用仍未知。')
        elif kind=='confirmed_no_charge':
            if units!=0 or adjustment is not None or not any(e['confirms_no_charge'] for e in evidence):
                fail(422,'invalid_settlement','未计费需要已核实依据。')
        elif kind in ('accepted_result','confirmed_charge_no_output'):
            if type(units) is not int or units<0 or adjustment is not None or not any(e['settled_units']==units for e in evidence):
                fail(422,'invalid_settlement','用量必须与核查依据一致。')
            if kind=='accepted_result':
                e=next((e for e in evidence if e['settled_units']==units and e['output_text']),None)
                if not e:
                    fail(422,'invalid_model_output','没有可核对的结果。')
                output=self._validate_model_output(job['purpose'],e['output_text'],json.loads(job['snapshot'])['input_snapshot'])
                model['actual_model']=e['actual_model']
        else:
            fail(422,'invalid_settlement','未知的核对决定。')
        if not row['discrepancy']:
            self._settle_model(con,job,kind,units,adjustment,body['evidence_ids'])
            try:
                self._model_access(con,self.obj(con,job['run_id'],'run'),live=True,source_ids=json.loads(job['snapshot'])['source_ids'])
            except Problem:
                model['visibility']='restricted'
            model.update(status='succeeded' if output else 'failed',output_text=output if model['visibility']=='normal' else None,revision=model['revision']+1,usage=self.model_usage(con,job['learner_id'],child=True))
            self.put(con,'model',model); self._complete_model_target(con,model)
        case.update(status='resolved',resolution=kind,revision=case['revision']+1,usage=self.model_usage(con,job['learner_id'],source='unknown' if kind=='administrative_adjustment' else 'provider'))
        con.execute('UPDATE learn_model_cases SET body=? WHERE id=?',(canonical(case),case_id))
        self.audit(con,session['actor_id'],'model_reconciled',job['id'],{'resolution':kind,'evidence_ids':body['evidence_ids'],'reason':body['reason']})
        return case
