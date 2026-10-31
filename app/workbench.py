# AI 工作台 — Copyright © 2026 2292576833.
# AI 工作台负责人：https://github.com/2292576833
# 松伴项目由 2292576833、Fantacy567、andorwu5-dev 共同拥有，详见 COPYRIGHT.md。
# 第三方代码及素材保留其原有版权和许可。

"""Private project discussions, durable request identity and explicit core archives.

Python/SQLite design adaptations, NOT copied TypeScript or source databases:
  黑客松情报局/src/server/personal-workspace.ts: canonical request hashes,
    bounded history, lease expiry without automatic replay, durable message pairs.
  src/modules/team-assistant/service.ts: context checks before/after a model call.
  src/modules/module-assistants/registry.ts: bounded role/readable-fact registry.
  src/server/ai-actions.ts: closed suggestions with no automatic execution.
No source license or authorship is inferred; original sources remain read-only.
"""
import json
from datetime import datetime, timedelta
from typing import Literal

import httpx
from fastapi import Header
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .planner import PlannerError, team_model_config
from .workbench_model import ROLES, clean, clean_data, dump, request_workbench_model, safe_actions, validate_result

LEASE_SECONDS = 120
MAX_ACTIVE = 2
MAX_PER_MINUTE = 10
SCHEMA = '''
CREATE TABLE IF NOT EXISTS workbench_sessions (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, team_id TEXT, title TEXT NOT NULL,
 request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(owner_id,request_id)
);
CREATE INDEX IF NOT EXISTS workbench_owner ON workbench_sessions(owner_id,team_id);
CREATE TABLE IF NOT EXISTS workbench_session_edits (
 session_id TEXT NOT NULL REFERENCES workbench_sessions(id), request_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(session_id,request_id)
);
CREATE TABLE IF NOT EXISTS workbench_requests (
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES workbench_sessions(id),
 owner_id TEXT NOT NULL, fingerprint TEXT NOT NULL, status TEXT NOT NULL,
 error TEXT, message_id TEXT, source_refs TEXT NOT NULL, context_fingerprint TEXT NOT NULL,
 lease_token TEXT NOT NULL, lease_until TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(session_id,request_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS workbench_one_active ON workbench_requests(session_id)
 WHERE status IN ('pending','running');
CREATE INDEX IF NOT EXISTS workbench_limits ON workbench_requests(status,owner_id,created_at);
CREATE TABLE IF NOT EXISTS workbench_messages (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
 session_id TEXT NOT NULL REFERENCES workbench_sessions(id), request_id TEXT NOT NULL,
 role TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL, role_id TEXT NOT NULL,
 actions TEXT NOT NULL DEFAULT '[]', sources TEXT NOT NULL DEFAULT '[]',
 requested_model TEXT, actual_model TEXT, mode TEXT NOT NULL, coverage TEXT NOT NULL DEFAULT '{}',
 UNIQUE(session_id,request_id,role)
);
CREATE TABLE IF NOT EXISTS workbench_shares (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES workbench_sessions(id),
 request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, event_id TEXT NOT NULL UNIQUE,
 payload TEXT NOT NULL, result TEXT, created_at TEXT NOT NULL,
 UNIQUE(session_id,request_id)
);
'''


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    @field_validator('*', mode='after')
    @classmethod
    def nonblank(cls, value):
        if isinstance(value, str) and (not value.strip() or '\0' in value):
            raise ValueError('文字不能为空或含空字符')
        return value


class NewSession(Strict):
    request_id: str = Field(min_length=8, max_length=100)
    title: str = Field(default='新讨论', min_length=1, max_length=120)
    team_id: str | None = Field(default=None, min_length=1, max_length=100)


class RenameSession(Strict):
    request_id: str = Field(min_length=8, max_length=100)
    title: str = Field(min_length=1, max_length=120)


class Turn(Strict):
    request_id: str = Field(min_length=8, max_length=100)
    text: str = Field(min_length=1, max_length=8000)
    role_id: Literal['materials', 'direction', 'next_step']
    source_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator('source_ids')
    @classmethod
    def sources_valid(cls, value):
        if any(not s or len(s) > 100 for s in value) or len(set(value)) > 10:
            raise ValueError('最多选择10个来源')
        return sorted(set(value))


class Share(Strict):
    request_id: str = Field(min_length=8, max_length=100)
    message_id: str = Field(min_length=1, max_length=100)
    team_id: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=3500)
    selected: bool


def session_json(row):
    result = {k: row[k] for k in ('id', 'title', 'team_id', 'created_at', 'updated_at')}
    renamed = row['explicit_title'] if 'explicit_title' in row.keys() else False
    if not renamed and result['title'] in ('新讨论', '新的项目讨论'):
        question = row['first_question'] if 'first_question' in row.keys() else None
        result['title'] = clean(' '.join(question.split()))[:48] if question else '未开始的讨论'
    return result


def message_json(row):
    return {k: row[k] for k in ('id', 'session_id', 'request_id', 'role', 'text', 'created_at', 'role_id', 'requested_model', 'actual_model', 'mode')} | {'actions': json.loads(row['actions']), 'sources': json.loads(row['sources']), 'coverage': json.loads(row['coverage'])}


def request_json(row):
    return {k: row[k] for k in ('id', 'request_id', 'session_id', 'status', 'created_at', 'updated_at', 'message_id')} | {'error': json.loads(row['error']) if row['error'] else None}


def register_workbench(api, db, problem, now, uid, digest, core, runner=None):
    def fingerprint(value):
        return digest(dump(value))

    def recover(con):
        # Never invalidate another live process merely because this app starts.
        con.execute("UPDATE workbench_requests SET status='unknown',error=?,updated_at=? WHERE status IN ('pending','running') AND lease_until<=?",
                    (dump({'code': 'request_expired', 'message': '请求已中断或超过等待期限，结果未知；不会自动重放。'}), now(), now()))

    with db(True) as con:
        con.executescript(SCHEMA)
        # sqlite3.executescript commits its caller's transaction; reacquire the
        # write lock for migration detection and expiry recovery across workers.
        con.execute('BEGIN IMMEDIATE')
        if 'coverage' not in {r['name'] for r in con.execute('PRAGMA table_info(workbench_messages)')}:
            con.execute("ALTER TABLE workbench_messages ADD COLUMN coverage TEXT NOT NULL DEFAULT '{}'")
        recover(con)

    def actor_scope(con, authorization, team_id=None):
        actor = core['person'](con, authorization)
        squad = None
        if team_id:
            actor, squad = core['access'](con, team_id, authorization, connector=False)
        return actor, squad

    def owned(con, sid, authorization):
        actor, _ = actor_scope(con, authorization)
        row = con.execute('''SELECT s.*, (SELECT text FROM workbench_messages WHERE session_id=s.id AND role='user' ORDER BY seq LIMIT 1) AS first_question,
                          EXISTS(SELECT 1 FROM workbench_session_edits WHERE session_id=s.id) AS explicit_title
                          FROM workbench_sessions s WHERE id=? AND owner_id=?''', (sid, actor['id'])).fetchone()
        if not row:
            raise problem(404, 'session_missing', '会话不存在或不属于当前账号。')
        actor, squad = actor_scope(con, authorization, row['team_id'])
        return row, actor, squad

    def facts(con, actor, squad, include_guidance=False):
        if not squad:
            return {'team': None, 'direction': None, 'my_tasks': []}
        snap = core['snapshot'](con, squad, actor)
        # Never forward snapshot members, reports, private profiles or unrelated tasks.
        team = {'id': squad['id'], 'name': squad['name'], 'is_captain': bool(snap['me']['captain']), 'revision': snap['revision'], 'plan_version': snap['plan_version']}
        direction = {k: str(snap['direction'].get(k, '')) for k in ('goal', 'rules', 'rubric', 'non_goals', 'deadline')}
        tasks = [{k: t.get(k) for k in ('key', 'title', 'acceptance', 'depends_on', 'status', 'owner_id')} for t in snap['active_plan'].get('tasks', []) if t.get('owner_id') == actor['id']][:30]
        result = {'team': team, 'direction': direction, 'my_tasks': tasks}
        if include_guidance:
            result['workflow'] = {k: snap['workflow'][k] for k in ('next_action', 'accepted_tasks', 'total_tasks')}
        return clean_data(result)

    def basis(context):
        # Sharing changes core.revision, but not necessarily the facts used by this turn.
        team = {k: v for k, v in (context['team'] or {}).items() if k != 'revision'}
        return fingerprint({'team': team, 'direction': context['direction'], 'my_tasks': context['my_tasks']})

    def sources(con, actor, team_id, selected=None):
        query = '''SELECT s.id,s.version,s.status,s.metadata,s.segments,s.warnings,p.team_id,p.owner_id
          FROM materials_sources s JOIN materials_spaces p ON p.id=s.space_id
          WHERE ((p.team_id IS NULL AND p.owner_id=?) OR (p.team_id=? AND ? IS NOT NULL))
          AND s.status IN ('ready','partial')'''
        args = [actor['id'], team_id, team_id]
        if selected is not None:
            if not selected:
                return []
            query += ' AND s.id IN (' + ','.join('?' for _ in selected) + ')'
            args.extend(selected)
        query += ' ORDER BY s.created_at DESC,s.id LIMIT 100'
        rows = con.execute(query, args).fetchall()
        if selected is not None and {r['id'] for r in rows} != set(selected):
            raise problem(403, 'source_unavailable', '选中的来源已失效、尚未解析或不在当前可读范围。')
        found = []
        for row in rows:
            meta = json.loads(row['metadata'])
            item = {'id': row['id'], 'name': str(meta.get('name', '未命名资料'))[:200], 'scope': 'team' if row['team_id'] else 'personal', 'version': row['version'], 'nature': meta.get('nature', 'unverified')}
            if selected is not None:
                item.update(segments=json.loads(row['segments']), warnings=json.loads(row['warnings']), status=row['status'], fingerprint=fingerprint(dict(row)))
            found.append(item)
        return found

    def refs_for(selected):
        return [clean_data({k: s[k] for k in ('id', 'name', 'scope', 'version', 'nature', 'fingerprint', 'status', 'warnings')}) | {'truncated': False} for s in selected]

    def check_refs(con, actor, team_id, refs):
        current = sources(con, actor, team_id, [s['id'] for s in refs])
        if sorted((s['id'], s['fingerprint']) for s in current) != sorted((s['id'], s['fingerprint']) for s in refs):
            raise problem(409, 'context_changed', '来源已更新，请核对新版本后明确发起新请求。')

    def recheck(con, sid, authorization, request, compare_context=True):
        session, actor, squad = owned(con, sid, authorization)
        check_refs(con, actor, session['team_id'], json.loads(request['source_refs']))
        current = facts(con, actor, squad)
        if compare_context and basis(current) != request['context_fingerprint']:
            raise problem(409, 'context_changed', '共同方向或本人任务已变化，旧回复没有采用。')
        return session, actor, current

    def request_result(con, request, authorization):
        # Cached success must still obey current source permissions and versions.
        message = None
        if request['status'] == 'succeeded':
            recheck(con, request['session_id'], authorization, request, compare_context=False)
            row = con.execute('SELECT * FROM workbench_messages WHERE id=?', (request['message_id'],)).fetchone()
            message = message_json(row) if row else None
        return {'request': request_json(request), 'message': message}

    def bounded_context(con, session, current, selected, body):
        refs = refs_for(selected)
        messages = con.execute('''SELECT m.* FROM workbench_messages m JOIN workbench_requests r
          ON r.session_id=m.session_id AND r.request_id=m.request_id
          WHERE m.session_id=? AND r.status='succeeded' AND r.context_fingerprint=?
          ORDER BY m.seq DESC LIMIT 24''', (session['id'], basis(current))).fetchall()
        history_total = con.execute('SELECT COUNT(*) FROM workbench_messages WHERE session_id=?', (session['id'],)).fetchone()[0]
        selected_versions = {s['id']: s['fingerprint'] for s in refs}
        history, history_size = [], 0
        for message in messages:
            prior_refs = json.loads(message['sources'])
            if any(selected_versions.get(s['id']) != s.get('fingerprint') for s in prior_refs):
                continue
            if history_size + len(message['text']) > 12000:
                break
            history.append({'role': message['role'], 'text': message['text']})
            history_size += len(message['text'])
        history.reverse()
        remaining, model_sources, truncated = 24000, [], []
        for source in selected:
            item = {k: source[k] for k in ('id', 'name', 'scope', 'version', 'nature', 'warnings', 'status')}
            item['segments'] = []
            for seg in source['segments']:
                text = str(seg.get('text', ''))
                take = min(len(text), remaining, 6000)
                if take:
                    item['segments'].append({k: seg[k] for k in ('id', 'location', 'method') if k in seg} | {'text': text[:take]})
                    remaining -= take
                if take < len(text) and source['id'] not in truncated:
                    truncated.append(source['id'])
            model_sources.append(item)
        context = current | {'role': next(r for r in ROLES if r['id'] == body.role_id), 'text': body.text, 'sources': model_sources, 'history': history,
                             'coverage': {'truncated_source_ids': truncated, 'history_limited': len(history) < history_total, 'source_selection_only': True}}
        context = clean_data(context)
        for ref in refs:
            ref['truncated'] = ref['id'] in truncated
        if len(dump(context)) > 80000:
            raise problem(422, 'context_too_large', '本轮资料过长，请减少选择或缩短共同方向。')
        return context, refs

    @api.get('/api/workbench/context')
    def get_context(team_id: str = '', authorization: str = Header(default='')):
        with db() as con:
            actor, squad = actor_scope(con, authorization, team_id or None)
            context = facts(con, actor, squad, include_guidance=True)
            context['personal_session_count'] = con.execute('SELECT COUNT(*) FROM workbench_sessions WHERE owner_id=? AND team_id IS NULL', (actor['id'],)).fetchone()[0]
            catalog = sources(con, actor, team_id or None)
        cfg = team_model_config()
        return context | {'roles': ROLES, 'sources': clean_data(catalog), 'model': {'configured': runner is not None or bool(cfg.get('api_key')), 'requested_model': cfg.get('model_id') if runner is None else None}}

    @api.get('/api/workbench/sessions')
    def list_sessions(team_id: str = '', authorization: str = Header(default='')):
        with db() as con:
            actor, _ = actor_scope(con, authorization, team_id or None)
            rows = con.execute('''SELECT s.*, (SELECT text FROM workbench_messages WHERE session_id=s.id AND role='user' ORDER BY seq LIMIT 1) AS first_question,
                               EXISTS(SELECT 1 FROM workbench_session_edits WHERE session_id=s.id) AS explicit_title
                               FROM workbench_sessions s WHERE owner_id=? AND team_id IS ? ORDER BY updated_at DESC,s.rowid DESC''', (actor['id'], team_id or None)).fetchall()
        return {'sessions': [session_json(r) for r in rows]}

    @api.patch('/api/workbench/sessions/{sid}')
    def rename_session(sid: str, body: RenameSession, authorization: str = Header(default='')):
        title = clean(body.title.strip())
        if not title:
            raise problem(422, 'invalid_title', '请填写会话名称。')
        with db(True) as con:
            owned(con, sid, authorization)
            fp = fingerprint({'title': body.title})
            prior = con.execute('SELECT fingerprint FROM workbench_session_edits WHERE session_id=? AND request_id=?', (sid, body.request_id)).fetchone()
            if prior:
                if prior['fingerprint'] != fp:
                    raise problem(409, 'request_conflict', '同一改名请求编号的内容不同。')
                session, _, _ = owned(con, sid, authorization)
                return {'session': session_json(session)}
            con.execute('INSERT INTO workbench_session_edits VALUES(?,?,?,?)', (sid, body.request_id, fp, now()))
            con.execute('UPDATE workbench_sessions SET title=?,updated_at=? WHERE id=?', (title, now(), sid))
            session, _, _ = owned(con, sid, authorization)
        return {'session': session_json(session)}

    @api.post('/api/workbench/sessions')
    def new_session(body: NewSession, authorization: str = Header(default='')):
        fp = fingerprint(body.model_dump(exclude={'request_id'}))
        with db(True) as con:
            actor, _ = actor_scope(con, authorization, body.team_id)
            prior = con.execute('SELECT * FROM workbench_sessions WHERE owner_id=? AND request_id=?', (actor['id'], body.request_id)).fetchone()
            if prior:
                if prior['fingerprint'] != fp:
                    raise problem(409, 'request_conflict', '同一请求编号的内容不同。')
                return {'session': session_json(prior)}
            ident, stamp = uid(), now()
            con.execute('INSERT INTO workbench_sessions VALUES(?,?,?,?,?,?,?,?)', (ident, actor['id'], body.team_id, clean(body.title.strip()), body.request_id, fp, stamp, stamp))
            result = con.execute('SELECT * FROM workbench_sessions WHERE id=?', (ident,)).fetchone()
        return {'session': session_json(result)}

    @api.get('/api/workbench/sessions/{sid}')
    def get_session(sid: str, authorization: str = Header(default='')):
        with db(True) as con:
            session, actor, _ = owned(con, sid, authorization)
            recover(con)
            requests = con.execute('SELECT * FROM workbench_requests WHERE session_id=? ORDER BY rowid', (sid,)).fetchall()
            hidden = set()
            for req in requests:
                if req['status'] == 'succeeded':
                    try:
                        check_refs(con, actor, session['team_id'], json.loads(req['source_refs']))
                    except problem:
                        hidden.add(req['request_id'])
            messages = con.execute('SELECT * FROM workbench_messages WHERE session_id=? ORDER BY seq', (sid,)).fetchall()
            reqs = [request_json(r) for r in requests]
            for req in reqs:
                if req['request_id'] in hidden:
                    req.update(status='failed', message_id=None, error={'code': 'context_changed', 'message': '来源已失效或更新，旧回复不可继续使用。'})
        return {'session': session_json(session), 'messages': [message_json(m) for m in messages if m['role'] == 'user' or m['request_id'] not in hidden], 'requests': reqs}

    @api.get('/api/workbench/requests/{ident}')
    def get_request(ident: str, authorization: str = Header(default='')):
        with db(True) as con:
            actor, _ = actor_scope(con, authorization)
            request = con.execute('SELECT * FROM workbench_requests WHERE id=? AND owner_id=?', (ident, actor['id'])).fetchone()
            if not request:
                raise problem(404, 'request_missing', '请求不存在。')
            owned(con, request['session_id'], authorization)
            recover(con)
            request = con.execute('SELECT * FROM workbench_requests WHERE id=?', (ident,)).fetchone()
            return request_result(con, request, authorization)

    @api.post('/api/workbench/sessions/{sid}/turns')
    def turn(sid: str, body: Turn, authorization: str = Header(default='')):
        fp = fingerprint(body.model_dump(exclude={'request_id'}))
        with db(True) as con:
            session, actor, squad = owned(con, sid, authorization)
            recover(con)
            prior = con.execute('SELECT * FROM workbench_requests WHERE session_id=? AND request_id=?', (sid, body.request_id)).fetchone()
            if prior:
                if prior['fingerprint'] != fp:
                    raise problem(409, 'request_conflict', '同一请求编号的内容不同。')
                return request_result(con, prior, authorization)
            if con.execute("SELECT 1 FROM workbench_requests WHERE session_id=? AND status IN ('pending','running')", (sid,)).fetchone():
                raise problem(409, 'turn_in_progress', '本会话仍有请求正在处理。')
            active = con.execute("SELECT COUNT(*) FROM workbench_requests WHERE status IN ('pending','running')").fetchone()[0]
            window = (datetime.fromisoformat(now()) - timedelta(minutes=1)).isoformat(timespec='seconds')
            recent = con.execute('SELECT COUNT(*) FROM workbench_requests WHERE owner_id=? AND created_at>=?', (actor['id'], window)).fetchone()[0]
            if active >= MAX_ACTIVE or recent >= MAX_PER_MINUTE:
                raise problem(429, 'workbench_busy', '工作台请求较多，请稍后再试。')
            current = facts(con, actor, squad)
            selected = sources(con, actor, session['team_id'], body.source_ids)
            context, refs = bounded_context(con, session, current, selected, body)
            ident, lease, stamp = uid(), uid(), now()
            expires = (datetime.fromisoformat(stamp) + timedelta(seconds=LEASE_SECONDS)).isoformat(timespec='seconds')
            con.execute('''INSERT INTO workbench_requests(id,request_id,session_id,owner_id,fingerprint,status,source_refs,context_fingerprint,lease_token,lease_until,created_at,updated_at)
              VALUES(?,?,?,?,?,'pending',?,?,?,?,?,?)''', (ident, body.request_id, sid, actor['id'], fp, dump(refs), basis(current), lease, expires, stamp, stamp))
            con.execute('''INSERT INTO workbench_messages(id,session_id,request_id,role,text,created_at,role_id,sources,mode,coverage)
              VALUES(?,?,?,'user',?,?,?,?,?,?)''', (uid(), sid, body.request_id, body.text, stamp, body.role_id, dump(refs), 'live', dump(context['coverage'])))
            con.execute('UPDATE workbench_sessions SET updated_at=? WHERE id=?', (stamp, sid))
        response_received = False
        try:
            with db(True) as con:
                request = con.execute('SELECT * FROM workbench_requests WHERE id=?', (ident,)).fetchone()
                recheck(con, sid, authorization, request)
                if request['status'] != 'pending' or request['lease_until'] <= now():
                    raise problem(409, 'request_expired', '请求等待已结束，没有再次调用模型。')
                changed = con.execute("UPDATE workbench_requests SET status='running',updated_at=? WHERE id=? AND status='pending' AND lease_token=? AND lease_until>?", (now(), ident, lease, now())).rowcount
                if changed != 1:
                    raise problem(409, 'request_expired', '请求占用已失效，没有再次调用模型。')
            raw = (runner or request_workbench_model)(context)
            response_received = True
            result = validate_result(raw, injected=runner is not None)
            with db(True) as con:
                recover(con)
                request = con.execute('SELECT * FROM workbench_requests WHERE id=?', (ident,)).fetchone()
                _, _, latest = recheck(con, sid, authorization, request)
                if request['status'] != 'running' or request['lease_token'] != lease:
                    raise problem(409, 'request_expired', '本次等待已结束，迟到回复没有采用。')
                mid = uid()
                con.execute('''INSERT INTO workbench_messages(id,session_id,request_id,role,text,created_at,role_id,actions,sources,requested_model,actual_model,mode,coverage)
                  VALUES(?,?,?,'assistant',?,?,?,?,?,?,?,?,?)''', (mid, sid, body.request_id, clean(result['text'].strip()), now(), body.role_id,
                  dump(safe_actions(result.get('actions'), bool((latest['team'] or {}).get('is_captain')))), dump(refs), result.get('requested_model'), result.get('actual_model'), result['mode'], dump(context['coverage'])))
                con.execute('UPDATE workbench_messages SET mode=? WHERE session_id=? AND request_id=? AND role=\'user\'', (result['mode'], sid, body.request_id))
                con.execute("UPDATE workbench_requests SET status='succeeded',message_id=?,updated_at=? WHERE id=?", (mid, now(), ident))
                con.execute('UPDATE workbench_sessions SET updated_at=? WHERE id=?', (now(), sid))
                return request_result(con, con.execute('SELECT * FROM workbench_requests WHERE id=?', (ident,)).fetchone(), authorization)
        except Exception as exc:
            if isinstance(exc, (PlannerError, problem)):
                code, message, status = exc.code, exc.message, exc.status
            elif isinstance(exc, (TimeoutError, httpx.TimeoutException)):
                code, message, status = 'model_timeout', '模型等待超时，结果未知；不会自动重放。', 504
            else:
                code, message, status = 'model_result_unknown', '本次请求中断，结果未知；输入已保存，不会自动重放。', 503
            uncertain = not response_received and (code in ('model_timeout', 'model_result_unknown', 'request_expired') or not isinstance(exc, (PlannerError, problem)))
            with db(True) as con:
                con.execute("UPDATE workbench_requests SET status=?,error=?,updated_at=? WHERE id=? AND status IN ('pending','running')", ('unknown' if uncertain else 'failed', dump({'code': code, 'message': message}), now(), ident))
            raise problem(status, code, message) from None

    @api.post('/api/workbench/sessions/{sid}/share')
    def share(sid: str, body: Share, authorization: str = Header(default='')):
        if body.selected is not True:
            raise problem(422, 'selection_required', '请先预览并显式确认本轮共享。')
        fp = fingerprint(body.model_dump(exclude={'request_id'}))
        with db(True) as con:
            session, actor, _ = owned(con, sid, authorization)
            core['access'](con, body.team_id, authorization, connector=False)
            if session['team_id'] and session['team_id'] != body.team_id:
                raise problem(403, 'share_scope', '团队会话只能共享给原团队。')
            prior = con.execute('SELECT * FROM workbench_shares WHERE session_id=? AND request_id=?', (sid, body.request_id)).fetchone()
            if prior and prior['fingerprint'] != fp:
                raise problem(409, 'request_conflict', '同一共享请求编号的内容不同。')
            message = con.execute("SELECT * FROM workbench_messages WHERE id=? AND session_id=? AND role='assistant'", (body.message_id, sid)).fetchone()
            request = con.execute("SELECT * FROM workbench_requests WHERE session_id=? AND message_id=? AND status='succeeded'", (sid, body.message_id)).fetchone()
            if not message or not request:
                raise problem(404, 'message_missing', '只能共享本人已经成功保存的助手回合。')
            recheck(con, sid, authorization, request, compare_context=False)
            if prior and prior['result']:
                return json.loads(prior['result']) | {'duplicate': True}
            if prior:
                payload, share_id = json.loads(prior['payload']), prior['id']
            else:
                user = con.execute("SELECT text FROM workbench_messages WHERE session_id=? AND request_id=? AND role='user'", (sid, message['request_id'])).fetchone()
                if len(message['actual_model'] or '') > 160:
                    raise problem(422, 'model_identity_too_long', '实际模型名称超过核心归档限制，未截断或伪造名称。')
                share_id = uid()
                payload = {'event_id': 'workbench:' + share_id, 'tool': '松伴项目工作台', 'session_label': session['title'],
                           'summary': body.summary, 'user_message': user['text'], 'assistant_summary': body.summary,
                           'model_name': message['actual_model'] or '', 'origin': 'human',
                           'excerpt': '用户编辑摘要；原始回复保留在本人会话。' + ('协议测试 fixture，非真实模型效果。' if message['mode'] == 'fixture' else '')}
                con.execute('INSERT INTO workbench_shares VALUES(?,?,?,?,?,?,?,?,?)', (share_id, actor['id'], sid, body.request_id, fp, payload['event_id'], dump(payload), None, now()))
        # Core owns its SQLite transaction; its stable event key also closes a crash
        # between archive commit and saving this local mapping. Retrying is safe.
        try:
            with db() as con:
                recheck(con, sid, authorization, request, compare_context=False)
                core['access'](con, body.team_id, authorization, connector=False)
            result = core['save_report'](body.team_id, payload, authorization, archive=True)
        except problem:
            raise
        except Exception:
            raise problem(503, 'share_unavailable', '共享未获得完成回执；原对话保留，可用同一请求编号核对重试。') from None
        with db(True) as con:
            recheck(con, sid, authorization, request, compare_context=False)
            core['access'](con, body.team_id, authorization, connector=False)
            con.execute('UPDATE workbench_shares SET result=? WHERE id=?', (dump(result), share_id))
        return result
