# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
"""Private seven-course sessions, immutable evidence, and at-most-once dispatch."""
import json
import secrets
from contextlib import nullcontext

from app.learning_v2.protocol import Problem, canonical, fail, revision
from app.platform_v1.companion import CompanionService
from . import model, teachers
from .schemas import ModelOutput, REQUEST_SCHEMAS
from .storage import migrate
from .budget import text_used_calls, text_inflight


def uid(prefix):
    return prefix + secrets.token_hex(16)


class WorkbenchService:
    def __init__(self, platform, settings_provider=None, runner=None):
        self.platform, self.learning, self.store = platform, platform.learning, platform.store
        self.settings_provider, self.runner = settings_provider, runner
        self.guard = platform.companion or CompanionService(self.store, self.learning)

    def migrate(self):
        migrate(self.store, self.learning.stamp())

    def config(self, con):
        # The admin bound method defaults kind='text'; also supports a con-only adapter.
        if self.platform.settings.demo_mode or self.settings_provider is None:
            return None
        return model.validate_config(self.settings_provider(con=con))

    def config_hash(self, con, config):
        # Credentials never enter a persisted snapshot, receipt, error or response.
        return self.learning.mac(con, canonical(config)) if config else 'mock'

    def owner(self, con, session):
        return self.guard._identity(con, session)

    def session(self, con, auth, sid):
        row = con.execute('SELECT * FROM learning_workbench_sessions WHERE id=? AND owner=?',
                          (sid, self.owner(con, auth))).fetchone()
        if not row:
            fail(404, 'workbench_not_found', '找不到当前身份的课程会话。')
        return row

    def authorize(self, con, op, session, params, body):
        self.owner(con, session)
        if op in REQUEST_SCHEMAS and not self.learning.settings.enabled:
            fail(423, 'learning_paused', '新的学习操作暂时暂停，已保存记录仍可查看。')
        if params.get('session_id'):
            self.session(con, session, params['session_id'])

    def capabilities(self, con, auth):
        config = self.config(con)
        reason = None
        if not self.platform.settings.enabled or not self.learning.settings.enabled:
            reason = '新的学习操作暂时暂停，已保存内容仍可查看。'
        elif not config:
            reason = '实时老师尚未配置；模拟示例不会调用真实模型。' if self.platform.settings.demo_mode else '实时老师尚未配置，可以先编辑并保存文字成果。'
        elif self.used_calls(con) >= config['max_calls']:
            reason = '本期模型额度已用完或仍待核对，已保存内容仍可查看和编辑。'
        else:
            try:
                self.guard._live_consent(con, auth)
            except Problem:
                reason = '当前学习身份尚未获得实时模型授权，可以继续编辑已保存内容。'
        return {'mock': bool(self.platform.settings.demo_mode and self.platform.settings.enabled and self.learning.settings.enabled),
                'live': reason is None, 'reason': reason}

    def used_calls(self, con):
        # Shared text ceiling includes Studio reservations, across revisions/restarts.
        return text_used_calls(con)

    def bump(self, con, sid):
        con.execute('UPDATE learning_workbench_sessions SET revision=revision+1,updated_at=? WHERE id=?',
                    (self.learning.stamp(), sid))

    def artifact(self, con, sid, aid):
        row = con.execute('SELECT id,title,content,source_message_id,created_at FROM learning_workbench_artifacts WHERE id=? AND session_id=?', (aid, sid)).fetchone()
        if not row:
            fail(404, 'artifact_not_found', '找不到当前会话的成果版本。')
        return dict(row)

    def record_versions(self, con, sid):
        record = con.execute('SELECT * FROM learning_workbench_records WHERE session_id=?', (sid,)).fetchone()
        if not record:
            return [], None
        versions = [json.loads(r[0]) for r in con.execute('SELECT body FROM learning_workbench_record_versions WHERE record_id=? ORDER BY version', (record['id'],))]
        confirmed = next((r for r in versions if r['version'] == record['confirmed_version']), None)
        return versions, confirmed

    def view(self, con, row, auth):
        teacher = teachers.public_teacher(teachers.teacher_for(row['course_id']))
        messages = [dict(r) for r in con.execute('SELECT id,user_text,assistant_text,mode,status,actual_model,artifact,created_at FROM learning_workbench_messages WHERE session_id=? ORDER BY rowid', (row['id'],))]
        try:
            self.guard._live_consent(con, auth)
            visible = True
        except Problem:
            visible = False
        for message in messages:
            message['artifact'] = json.loads(message['artifact']) if message['artifact'] else None
            if message['mode'] == 'live' and not visible:
                message.update(assistant_text=None, artifact=None, actual_model=None)
            job = con.execute('SELECT failure_code FROM learning_workbench_jobs WHERE message_id=?', (message['id'],)).fetchone()
            message['failure_code'] = job[0] if job else None
        versions, confirmed = self.record_versions(con, row['id'])
        return {key: row[key] for key in ('id', 'course_id', 'title', 'revision', 'updated_at', 'selected_artifact_id')} | {
            'teacher': teacher, 'capabilities': self.capabilities(con, auth), 'messages': messages,
            'artifact_versions': [dict(r) for r in con.execute('SELECT id,title,content,source_message_id,created_at FROM learning_workbench_artifacts WHERE session_id=? ORDER BY rowid', (row['id'],))],
            'record': versions[-1] if versions else None, 'confirmed_record': confirmed, 'record_versions': versions}

    def expire_jobs(self, con):
        for row in con.execute("SELECT * FROM learning_workbench_jobs WHERE state='running' AND lease_until<=?", (self.learning.clock(),)).fetchall():
            self.job_status(con, row, 'unknown', failure='lease_expired')

    def read(self, con, op, session, params, query):
        self.authorize(con, op, session, params, {})
        # Local lease recovery does not perform model I/O or restart a request.
        self.expire_jobs(con)
        owner = self.owner(con, session)
        if op == 'workbenchSessions':
            return {'items': [dict(r) for r in con.execute('SELECT id,course_id,title,revision,updated_at FROM learning_workbench_sessions WHERE owner=? ORDER BY updated_at DESC,rowid DESC', (owner,))]}
        if op == 'workbenchRecords':
            return {'items': [json.loads(r[0]) for r in con.execute('''SELECT v.body FROM learning_workbench_records r
                JOIN learning_workbench_sessions s ON s.id=r.session_id
                JOIN learning_workbench_record_versions v ON v.record_id=r.id AND v.version=r.confirmed_version
                WHERE s.owner=? ORDER BY s.updated_at DESC,s.rowid DESC''', (owner,))]}
        return self.view(con, self.session(con, session, params['session_id']), session)

    def replay(self, con, op, session, params, body, old):
        self.expire_jobs(con)
        return self.view(con, self.session(con, session, old['id']), session)

    def write(self, con, op, session, params, body):
        b = REQUEST_SCHEMAS[op].model_validate(body).model_dump()
        self.authorize(con, op, session, params, b)
        stamp, owner = self.learning.stamp(), self.owner(con, session)
        if op == 'openWorkbench':
            teacher = teachers.teacher_for(b['course_id'])
            row = con.execute('SELECT id FROM learning_workbench_sessions WHERE owner=? AND course_id=?', (owner, b['course_id'])).fetchone()
            if row:
                sid = row[0]
            else:
                sid = uid('lws_')
                con.execute('INSERT INTO learning_workbench_sessions VALUES(?,?,?,?,1,NULL,?,?)',
                            (sid, owner, b['course_id'], teacher['name'] + ' · 我的探索', stamp, stamp))
        else:
            sid = params['session_id']
            row = self.session(con, session, sid)
            revision(b['expected_revision'], row['revision'])
            if op == 'messageWorkbench':
                self.enqueue(con, row, session, b)
            elif op == 'artifactWorkbench':
                if b['source_message_id']:
                    source = con.execute("SELECT mode FROM learning_workbench_messages WHERE id=? AND session_id=? AND status='succeeded'", (b['source_message_id'], sid)).fetchone()
                    if not source:
                        fail(404, 'message_not_found', '找不到这份成果所依据的有效回复。')
                    if source[0] == 'live':
                        self.guard._live_consent(con, session)
                if con.execute('SELECT COUNT(*) FROM learning_workbench_artifacts WHERE session_id=?', (sid,)).fetchone()[0] >= 200:
                    fail(409, 'artifact_limit', '这个课程的成果版本已达到保存上限，请联系支持。')
                aid = uid('lwa_')
                con.execute('INSERT INTO learning_workbench_artifacts VALUES(?,?,?,?,?,?)', (aid, sid, b['title'], b['content'], b['source_message_id'], stamp))
                con.execute('UPDATE learning_workbench_sessions SET selected_artifact_id=? WHERE id=?', (aid, sid))
            elif op == 'selectWorkbenchArtifact':
                self.artifact(con, sid, b['version_id'])
                con.execute('UPDATE learning_workbench_sessions SET selected_artifact_id=? WHERE id=?', (b['version_id'], sid))
            elif op == 'draftWorkbenchRecord':
                self.draft_record(con, row)
            elif op == 'confirmWorkbenchRecord':
                self.confirm_record(con, row, b)
            self.bump(con, sid)
        return self.view(con, self.session(con, session, sid), session)

    def append_record(self, con, row, body, *, confirmed=False):
        record = con.execute('SELECT * FROM learning_workbench_records WHERE session_id=?', (row['id'],)).fetchone()
        number = record['current_version'] + 1 if record else 1
        if number > 400:
            fail(409, 'record_limit', '这个课程的记录版本已达到保存上限，请联系支持。')
        rid = record['id'] if record else uid('lwr_')
        body.update(id=rid, session_id=row['id'], course_id=row['course_id'], version=number, updated_at=self.learning.stamp())
        if not record:
            con.execute('INSERT INTO learning_workbench_records VALUES(?,?,?,NULL)', (rid, row['id'], number))
        con.execute('INSERT INTO learning_workbench_record_versions VALUES(?,?,?)', (rid, number, canonical(body)))
        con.execute('UPDATE learning_workbench_records SET current_version=? WHERE id=?', (number, rid))
        if confirmed:
            con.execute('UPDATE learning_workbench_records SET confirmed_version=? WHERE id=?', (number, rid))

    def draft_record(self, con, row):
        messages = [dict(r) for r in con.execute('SELECT id,user_text,status,mode FROM learning_workbench_messages WHERE session_id=? ORDER BY rowid DESC LIMIT 8', (row['id'],))][::-1]
        artifact = self.artifact(con, row['id'], row['selected_artifact_id']) if row['selected_artifact_id'] else None
        if not messages and not artifact:
            fail(409, 'evidence_required', '先留下一次提问或保存一份文字成果，再整理记录。')
        statements = ['根据已保存的提问和文字成果整理；这是可编辑的事实草稿，不是能力评价。']
        if messages:
            statements.append('我提交过的要求：' + '；'.join(m['user_text'][:180] for m in messages))
        if artifact:
            statements.append('我保存并选择了文字成果《' + artifact['title'] + '》。这不代表软件已运行或已经学会。')
        elif messages:
            statements.append('目前保留的是探索对话，还没有保存实际作品。')
        if any(m['mode'] == 'mock' for m in messages):
            statements.append('其中包含模拟示例，未调用真实模型。')
        self.append_record(con, row, {'title': row['title'], 'summary': '\n'.join(statements),
            'next_step': '我想接着修改或验证的一件事：', 'status': 'draft', 'method': 'evidence',
            'source_message_ids': [m['id'] for m in messages], 'artifact_version_id': artifact['id'] if artifact else None})

    def confirm_record(self, con, row, body):
        versions, _ = self.record_versions(con, row['id'])
        if not versions or versions[-1]['status'] != 'draft':
            fail(409, 'record_draft_required', '请先整理或重新生成草稿，再由你编辑确认。')
        value = dict(versions[-1])
        value.update(title=body['title'], summary=body['summary'], next_step=body['next_step'], status='confirmed')
        self.append_record(con, row, value, confirmed=True)

    def enqueue(self, con, row, auth, body):
        active = con.execute("SELECT 1 FROM learning_workbench_jobs WHERE owner=? AND state IN ('pending','running','unknown')", (row['owner'],)).fetchone()
        if active:
            fail(409, 'workbench_busy', '有一条消息正在处理或结果待核对，请先读取原会话。', 'reload')
        if con.execute('SELECT COUNT(*) FROM learning_workbench_messages WHERE session_id=?', (row['id'],)).fetchone()[0] >= 500:
            fail(409, 'message_limit', '这个课程的消息已达到保存上限，已有内容仍可查看。')
        live, config = body['mode'] == 'live', None
        if live:
            self.guard._live_consent(con, auth)
            config = self.config(con)
            if not config:
                fail(423, 'model_unavailable', '实时老师尚未配置，已保存内容不会丢失。')
            if self.used_calls(con) >= config['max_calls']:
                fail(429, 'model_budget_exhausted', '本期模型额度已用完或仍待核对，不能再次发送。')
        elif not self.platform.settings.demo_mode:
            fail(403, 'mock_unavailable', '当前站点未开启模拟示例。')
        snapshot = self.guard._auth_snapshot(con, auth)
        teacher = teachers.teacher_for(row['course_id'])
        history = [dict(r) for r in con.execute("SELECT user_text,assistant_text,mode,status,artifact FROM learning_workbench_messages WHERE session_id=? ORDER BY rowid DESC LIMIT 6", (row['id'],))][::-1]
        try:
            self.guard._live_consent(con, auth)
            live_history_visible = True
        except Problem:
            live_history_visible = False
        # Bound context without silently truncating the current question. Preserve real status/mode.
        for item in history:
            item['user_text'] = item['user_text'][:600]
            item['assistant_text'] = item['assistant_text'][:600] if item['assistant_text'] else None
            item['artifact'] = json.loads(item['artifact']) if item['artifact'] else None
            if item['artifact']:
                item['artifact']['content'] = item['artifact']['content'][:1500]
            if item['mode'] == 'live' and not live_history_visible:
                item.update(assistant_text=None, artifact=None)
        artifact = self.artifact(con, row['id'], row['selected_artifact_id']) if row['selected_artifact_id'] else None
        if artifact:
            artifact['content'] = artifact['content'][:6000]
        payload = {'teacher': teacher, 'input': {'course_id': row['course_id'], 'content': body['content'],
            'history': history, 'selected_artifact': artifact}}
        if len(canonical(payload)) > 40000:
            fail(422, 'context_too_large', '课程材料与成果较长，请联系支持核对老师材料。')
        mid = uid('lwm_')
        con.execute("INSERT INTO learning_workbench_messages VALUES(?,?,?,NULL,?,'pending',NULL,NULL,?)", (mid, row['id'], body['content'], body['mode'], self.learning.stamp()))
        con.execute('''INSERT INTO learning_workbench_jobs
            (message_id,session_id,owner,mode,state,counted,config_hash,auth_snapshot,input_snapshot,created_at)
            VALUES(?,?,?,?,'pending',?,?,?,?,?)''',
            (mid, row['id'], row['owner'], body['mode'], int(live), self.config_hash(con, config), canonical(snapshot), canonical(payload), self.learning.stamp()))

    def job_status(self, con, job, state, *, output=None, failure=None):
        output = output or {}
        con.execute('UPDATE learning_workbench_jobs SET state=?,failure_code=?,usage=?,provider_request_id=? WHERE message_id=?',
                    (state, failure, canonical(output['usage']) if output.get('usage') is not None else None, output.get('provider_request_id'), job['message_id']))
        # Only validated, currently authorized results become visible in the conversation.
        visible = output if state == 'succeeded' else {}
        con.execute('UPDATE learning_workbench_messages SET status=?,assistant_text=?,actual_model=?,artifact=? WHERE id=?',
                    (state, visible.get('reply'), visible.get('actual_model'), canonical(visible['artifact']) if visible.get('artifact') else None, job['message_id']))
        self.bump(con, job['session_id'])

    def job_access(self, con, job):
        if not self.platform.settings.enabled or not self.learning.settings.enabled:
            fail(423, 'learning_paused', '新的学习操作暂时暂停。')
        auth = json.loads(job['auth_snapshot'])
        self.guard._verify_auth(con, auth)
        self.session(con, auth, job['session_id'])
        if job['mode'] == 'live':
            self.guard._live_consent(con, auth)
        elif not self.platform.settings.demo_mode:
            fail(403, 'mock_unavailable', '模拟模式已停用。')

    def worker_once(self):
        """Claim and commit before I/O. Pending jobs recover; dispatched jobs never retry."""
        with self.store.transaction() as con:
            self.expire_jobs(con)
            job = con.execute("SELECT * FROM learning_workbench_jobs WHERE state='pending' ORDER BY rowid LIMIT 1").fetchone()
            if not job:
                return None
            live = job['mode'] == 'live'
            config = self.config(con) if live else None
            try:
                self.job_access(con, job)
                if live and (not config or job['config_hash'] != self.config_hash(con, config)):
                    fail(409, 'configuration_changed', '模型配置已变化，请核对原记录。')
                if live and self.used_calls(con) > config['max_calls']:
                    # This job already holds one slot. Recheck in case another domain
                    # consumed capacity since enqueue; never dispatch above the ceiling.
                    fail(429, 'model_budget_exhausted', '共用文字模型额度已用完。')
            except Problem as error:
                self.job_status(con, job, 'failed', failure=error.code)
                con.execute('UPDATE learning_workbench_jobs SET counted=0 WHERE message_id=?', (job['message_id'],))
                return job['message_id']
            if live:
                if text_inflight(con) >= config['max_concurrency']:
                    return None
            lease = uid('lwl_')
            con.execute('UPDATE learning_workbench_jobs SET lease_token=?,lease_until=?,dispatched_at=? WHERE message_id=?',
                (lease, self.learning.clock() + (config['lease_seconds'] if live else 30), self.learning.stamp(), job['message_id']))
            self.job_status(con, job, 'running')
            payload = json.loads(job['input_snapshot'])
            payload.update(max_output_tokens=config['max_output_tokens'] if live else 800,
                           timeout_seconds=config['timeout_seconds'] if live else 10, mode=job['mode'])
        output = {}
        try:
            result = self.runner(payload) if self.runner is not None else (model.invoke_live(payload, config=config) if live else model.invoke_mock(payload))
            try:
                output = ModelOutput.model_validate(result).model_dump()
                canonical(output)  # Reject non-finite/nonserializable usage before opening a transaction.
                if len(canonical(output.get('usage'))) > 4000:
                    raise ValueError('Invalid provider usage')
                if live and not output.get('actual_model'):
                    raise ValueError('Provider model identity missing')
            except (ValueError, TypeError, OverflowError, RecursionError):
                # A runner returned a response: invalid content is a known failure,
                # distinct from a transport exception with no returned result.
                raise model.ModelOutputInvalid('provider_invalid_output', model.response_metadata(result)) from None
            if not live:
                output['actual_model'] = None
                if not output['reply'].startswith('【模拟'):
                    output['reply'] = '【模拟示例，未调用真实模型】' + output['reply']
            state, failure = 'succeeded', None
        except model.ModelRejected:
            state, failure = 'failed', 'provider_rejected'
        except model.ModelOutputInvalid as error:
            output, state, failure = error.metadata, 'failed', error.code if live else 'mock_failed'
        except Exception:
            state, failure = ('unknown', 'result_uncertain') if live else ('failed', 'mock_failed')
        with self.store.transaction() as con:
            current = con.execute('SELECT * FROM learning_workbench_jobs WHERE message_id=?', (job['message_id'],)).fetchone()
            if current['state'] != 'running' or current['lease_token'] != lease:
                return job['message_id']
            if current['lease_until'] <= self.learning.clock():
                self.job_status(con, current, 'unknown', failure='lease_expired')
                return job['message_id']
            try:
                self.job_access(con, current)
                if live:
                    latest = self.config(con)
                    if not latest or current['config_hash'] != self.config_hash(con, latest):
                        fail(409, 'configuration_changed', '模型配置已经变化。')
            except Problem as error:
                # Preserve uncertainty and the held budget even after identity changes.
                state, failure = ('unknown' if state == 'unknown' else 'failed'), error.code
            self.job_status(con, current, state, output=output, failure=failure)
        return job['message_id']

    def close_unknown(self, message_id, *, evidence, authority, con=None):
        """Internal operator reconciliation only; no refund, success claim or redispatch.

        The host must authenticate/authorize the operator before calling. No public
        learner route exposes this method. Evidence records why the hold was closed.
        """
        if not isinstance(evidence, str) or not 10 <= len(evidence.strip()) <= 3000 or not isinstance(authority, str) or not authority.strip():
            raise ValueError('Explicit operator and investigation evidence required')
        with (nullcontext(con) if con is not None else self.store.transaction()) as db:
            job = db.execute('SELECT * FROM learning_workbench_jobs WHERE message_id=?', (message_id,)).fetchone()
            if not job:
                fail(404, 'message_not_found', '找不到待核对的消息。')
            prior = db.execute('SELECT 1 FROM learning_workbench_reconciliations WHERE message_id=?', (message_id,)).fetchone()
            if prior:
                return
            if job['state'] != 'unknown':
                fail(409, 'not_unknown', '只有结果未知的请求可以登记人工核对。')
            db.execute('INSERT INTO learning_workbench_reconciliations VALUES(?,?,?,?)', (message_id, evidence, authority, self.learning.stamp()))
            self.job_status(db, job, 'failed', failure='operator_closed_unknown')
            db.execute('UPDATE learning_workbench_jobs SET lease_token=NULL WHERE message_id=?', (message_id,))
            self.learning.audit(db, None, 'workbench_unknown_closed', message_id, {'authority': authority})
