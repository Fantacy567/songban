"""Persistent, member-confirmed topic selection; shared turns are untrusted data."""
import json
from datetime import datetime, timedelta
from threading import BoundedSemaphore

from fastapi import BackgroundTasks, Header
from pydantic import BaseModel, ConfigDict, Field

from .planner import PlannerError


SCHEMA = """
CREATE TABLE IF NOT EXISTS core_topic_rounds (
 id TEXT PRIMARY KEY, squad_id TEXT NOT NULL, phase TEXT NOT NULL,
 revision INTEGER NOT NULL, body TEXT NOT NULL, attempt_id TEXT NOT NULL DEFAULT '',
 lease_until TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS core_topic_team ON core_topic_rounds(squad_id);
CREATE TABLE IF NOT EXISTS core_topic_turns (
 id TEXT PRIMARY KEY, round_id TEXT NOT NULL, user_id TEXT NOT NULL,
 connection_id TEXT NOT NULL, event_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
 body TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(round_id,user_id,event_id)
);
CREATE TABLE IF NOT EXISTS core_topic_ready (
 round_id TEXT NOT NULL, user_id TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(round_id,user_id)
);
CREATE TABLE IF NOT EXISTS core_topic_votes (
 round_id TEXT NOT NULL, ballot INTEGER NOT NULL, user_id TEXT NOT NULL,
 candidate_id TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(round_id,ballot,user_id)
);
CREATE TABLE IF NOT EXISTS core_topic_operations (
 squad_id TEXT NOT NULL, user_id TEXT NOT NULL, request_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL, PRIMARY KEY(squad_id,user_id,request_id)
);
CREATE TABLE IF NOT EXISTS core_task_claims (
 squad_id TEXT NOT NULL, plan_version INTEGER NOT NULL, task_key TEXT NOT NULL,
 user_id TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(squad_id,plan_version,task_key)
);
"""
DIMENSIONS = {
    'team_fit': '团队综合能力', 'track_fit': '选题与赛道符合性',
    'advantage': '特殊优势', 'rubric_fit': '评分维度', 'feasibility': '时间与实现可行性',
}


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Operation(Strict):
    request_id: str = Field(min_length=8, max_length=120)
    expected_revision: int = Field(ge=0)


class Start(Operation):
    minutes: int = Field(default=20, ge=5, le=180)
    track: str = Field(min_length=1, max_length=1000)
    rules: str = Field(default='', max_length=12000)
    rubric: str = Field(default='', max_length=4000)


class Ready(Operation):
    complete: bool


class Reopen(Operation):
    minutes: int = Field(default=20, ge=5, le=180)


class Retry(Operation):
    acknowledge_unknown: bool = False


class Vote(Operation):
    candidate_id: str = Field(min_length=1, max_length=100)
    ballot: int = Field(ge=1)


class Select(Operation):
    candidate_id: str = Field(min_length=1, max_length=100)


class Turn(Strict):
    round_id: str = Field(min_length=1, max_length=100)
    event_id: str = Field(min_length=8, max_length=120)
    selected: bool
    topic_title: str = Field(min_length=1, max_length=160)
    user_message: str = Field(min_length=1, max_length=16000)
    assistant_message: str = Field(min_length=1, max_length=50000)
    model_name: str = Field(default='', max_length=160)
    session_label: str = Field(default='', max_length=120)


def latest(con, sid):
    row = con.execute('SELECT * FROM core_topic_rounds WHERE squad_id=? ORDER BY rowid DESC LIMIT 1', (sid,)).fetchone()
    return dict(row) if row else None


def current_phase(row, now):
    if row['phase'] == 'ranking' and row['lease_until'] <= now:
        return 'unknown'
    return row['phase']


def planning_guard(con, sid, problem):
    row = latest(con, sid)
    if row and row['phase'] != 'selected':
        raise problem(409, 'topic_not_selected', '请先完成全员确认、选题排名和投票，再由队长确认主方向。')


def claimed_owner(con, sid, version, task):
    if not task.get('claim_required'):
        return task.get('owner_id', '')
    row = con.execute('SELECT user_id FROM core_task_claims WHERE squad_id=? AND plan_version=? AND task_key=?',
                      (sid, version, task['key'])).fetchone()
    return row['user_id'] if row else ''


def register_topic_selection(api, db, problem, now, uid, digest, core, runner=None):
    from .team_core import dump, scrub
    from .topic_selection_model import request_ranking
    ranking_gate = BoundedSemaphore(2)

    def roster(con, sid):
        return [dict(r) for r in con.execute(
            'SELECT p.id,p.name,COALESCE(c.strengths,p.skills) AS strengths,c.willingness,c.hours FROM squad_members m JOIN people p ON p.id=m.user_id '
            'LEFT JOIN core_profiles c ON c.squad_id=m.squad_id AND c.user_id=m.user_id '
            'WHERE m.squad_id=? ORDER BY m.rowid', (sid,))]

    def roster_fingerprint(con, sid):
        return digest(dump(roster(con, sid)))

    def read_round(con, sid):
        row = latest(con, sid)
        if not row:
            raise problem(409, 'topic_round_missing', '请由队长先开启选题讨论。')
        return row

    def candidates(con, rid):
        grouped = {}
        for row in con.execute('SELECT * FROM core_topic_turns WHERE round_id=? ORDER BY rowid', (rid,)):
            body = json.loads(row['body'])
            key = digest(row['user_id'] + '\n' + body['topic_title'])[:32]
            item = grouped.setdefault(key, {'id': key, 'user_id': row['user_id'], 'title': body['topic_title'], 'turns': []})
            item['turns'].append({'id': row['id'], 'created_at': row['created_at'], **body})
        return list(grouped.values())

    def snapshot(con, sid, actor_id, include_turns=True):
        row = latest(con, sid)
        if not row:
            return None
        body = json.loads(row['body'])
        members = roster(con, sid)
        member_ids = {m['id'] for m in members}
        all_candidates = candidates(con, row['id'])
        ready = {r['user_id'] for r in con.execute('SELECT user_id FROM core_topic_ready WHERE round_id=?', (row['id'],))} & member_ids
        votes = [dict(r) for r in con.execute(
            'SELECT user_id,candidate_id FROM core_topic_votes WHERE round_id=? AND ballot=?',
            (row['id'], body.get('ballot', 1))) if r['user_id'] in member_ids]
        # Individual votes stay private until everyone has voted in this ballot.
        tallies = None
        if len(votes) == len(members) and members:
            tallies = {key: sum(v['candidate_id'] == key for v in votes) for key in body.get('eligible', [])}
        phase = current_phase(row, now())
        stale = phase not in ('discussion', 'selected') and body.get('roster_fingerprint') != roster_fingerprint(con, sid)
        for member in members:
            own = [c for c in all_candidates if c['user_id'] == member['id']]
            member.update(confirmed=member['id'] in ready, shared_turns=sum(len(c['turns']) for c in own),
                          voted=any(v['user_id'] == member['id'] for v in votes))
        if not include_turns:
            all_candidates = [{k: v for k, v in c.items() if k != 'turns'} for c in all_candidates]
        return {
            'id': row['id'], 'phase': phase, 'revision': row['revision'], 'track': body['track'],
            'rules': body['rules'], 'rubric': body['rubric'], 'deadline': body['deadline'],
            'members': members, 'confirmed_count': len(ready), 'member_count': len(members),
            'candidates': all_candidates, 'ranking': body.get('ranking'), 'dimensions': DIMENSIONS,
            'ballot': body.get('ballot', 1), 'eligible': body.get('eligible', []),
            'votes_count': len(votes), 'tallies': tallies, 'previous_tie': body.get('previous_tie'),
            'my_vote': next((v['candidate_id'] for v in votes if v['user_id'] == actor_id), None),
            'winner_id': body.get('winner_id'), 'roster_changed': stale,
            'error': row['error'] or ('请求中断或超时，结果未知；不会自动重试。' if phase == 'unknown' else ''),
        }

    def operation(con, sid, actor, label, body):
        value = body.model_dump()
        fp = digest(dump({'operation': label, 'body': value}))
        prior = con.execute('SELECT fingerprint FROM core_topic_operations WHERE squad_id=? AND user_id=? AND request_id=?',
                            (sid, actor['id'], body.request_id)).fetchone()
        if prior:
            if prior['fingerprint'] != fp:
                raise problem(409, 'request_conflict', '同一次请求内容已改变，请重新核对后提交。')
            return True
        con.execute('INSERT INTO core_topic_operations VALUES(?,?,?,?)', (sid, actor['id'], body.request_id, fp))
        return False

    def version(row, body):
        if row['revision'] != body.expected_revision:
            raise problem(409, 'topic_changed', '选题资料已更新，请读取最新状态后再确认。')

    def update(con, row, body=None, phase=None, **fields):
        values = {'body': dump(body if body is not None else json.loads(row['body'])),
                  'phase': phase or row['phase'], 'updated_at': now(), **fields}
        con.execute('UPDATE core_topic_rounds SET revision=revision+1,' + ','.join(k + '=?' for k in values) + ' WHERE id=?',
                    (*values.values(), row['id']))
        core['bump'](con, row['squad_id'])

    def same_roster(con, sid, data):
        if data.get('roster_fingerprint') != roster_fingerprint(con, sid):
            raise problem(409, 'topic_roster_changed', '成员或能力资料已变化，请队长重新开放讨论并由当前全员确认。')

    def ranking_context(con, sid, row, data):
        items = candidates(con, row['id'])
        members = roster(con, sid)
        count = sum(len(c['turns']) for c in items)
        budget = max(120, min(4000, 55000 // max(1, count)))
        coverage = {'turns': count, 'truncated_turns': 0}
        for item in items:
            for turn in item['turns']:
                turn['original_lengths'] = {k: len(turn[k]) for k in ('user_message', 'assistant_message')}
                for key in ('user_message', 'assistant_message'):
                    turn[key] = turn[key][:budget // 2]
                turn['truncated'] = any(turn['original_lengths'][k] > len(turn[k]) for k in turn['original_lengths'])
                coverage['truncated_turns'] += int(turn['truncated'])
        return {'track': data['track'], 'rules': data['rules'], 'rubric': data['rubric'],
                'members': members, 'candidates': items, 'dimensions': DIMENSIONS, 'coverage': coverage}

    def validate_ranking(raw, context):
        if not isinstance(raw, dict) or not isinstance(raw.get('items'), list):
            raise ValueError('排名格式错误')
        expected = {c['id'] for c in context['candidates']}
        if len(raw['items']) != len(expected) or {r.get('candidate_id') for r in raw['items'] if isinstance(r, dict)} != expected:
            raise ValueError('排名必须包含全部候选，且每个候选只出现一次')
        def text(value):
            if not isinstance(value, str) or not value.strip() or len(value) > 1800:
                raise ValueError('排名说明不完整')
            return scrub(value.strip())
        result = {'summary': text(raw.get('summary')), 'items': [], 'coverage': context['coverage']}
        sources = {t['id'] for c in context['candidates'] for t in c['turns']}
        sources |= {'rules', 'rubric', 'track'} | {'member:' + m['id'] for m in context['members']}
        for index, item in enumerate(raw['items'], 1):
            dims = item.get('dimensions')
            if not isinstance(dims, dict) or set(dims) != set(DIMENSIONS):
                raise ValueError('缺少评估维度')
            own_sources = {t['id'] for c in context['candidates'] if c['id'] == item['candidate_id'] for t in c['turns']}
            refs = item.get('source_ids')
            if not isinstance(refs, list) or not refs or not all(isinstance(x, str) and x in sources for x in refs) or not own_sources.intersection(refs):
                raise ValueError('排名缺少本候选的真实来源')
            entry = {'candidate_id': item['candidate_id'], 'rank': index,
                     'dimensions': {k: text(v) for k, v in dims.items()}, 'source_ids': refs}
            for key in ('advantages', 'risks', 'verification'):
                values = item.get(key)
                if not isinstance(values, list) or not 1 <= len(values) <= 5:
                    raise ValueError('每项必须说明优势、风险和待验证事项')
                entry[key] = [text(v) for v in values]
            result['items'].append(entry)
        return result

    def run_ranking(sid, rid, attempt):
        try:
            with db() as con:
                row = read_round(con, sid)
                if row['id'] != rid or row['phase'] != 'ranking' or row['attempt_id'] != attempt:
                    return
                data = json.loads(row['body'])
                same_roster(con, sid, data)
                context = ranking_context(con, sid, row, data)
            if not ranking_gate.acquire(blocking=False):
                raise PlannerError('model_busy', '排名服务正忙，讨论已保存；请稍后手动重试。', 429)
            try:
                raw = (runner or request_ranking)(context)
            finally:
                ranking_gate.release()
            result = validate_ranking(raw, context)
            result['mode'] = 'fixture' if runner else 'live'
            for key in ('requested_model','actual_model'):
                value=raw.get(key)
                result[key]=scrub(value)[:160] if isinstance(value,str) else None
            with db(True) as con:
                current = read_round(con, sid)
                if current['id'] != rid or current_phase(current,now()) != 'ranking' or current['attempt_id'] != attempt:
                    return
                same_roster(con, sid, data)
                data.update(ranking=result, eligible=[c['id'] for c in context['candidates']], ballot=data.get('next_ballot', 1))
                update(con, current, data, 'voting', lease_until='', error='')
        except Exception as error:
            with db(True) as con:
                current = latest(con, sid)
                if current and current['id'] == rid and current['phase'] == 'ranking' and current['attempt_id'] == attempt:
                    unknown = getattr(error, 'code', '') == 'model_timeout'
                    message = getattr(error, 'message', '排名未生成可用结果。请核对材料后重试，原讨论已保留。')
                    update(con, current, phase='unknown' if unknown else 'failed', error=scrub(message)[:1200], lease_until='')

    prefix = '/api/core/teams/{sid}/topic-selection'

    @api.get(prefix)
    def get_selection(sid: str, authorization: str = Header(default='')):
        with db() as con:
            actor, _ = core['access'](con, sid, authorization)
            return {'round': snapshot(con, sid, actor['id'])}

    @api.post(prefix + '/rounds')
    def start(sid: str, body: Start, authorization: str = Header(default='')):
        with db(True) as con:
            actor, squad = core['access'](con, sid, authorization, True, False)
            duplicate = operation(con, sid, actor, 'start', body)
            if not duplicate:
                settings = core['init'](con, squad)
                if latest(con, sid) or settings['plan_version']:
                    raise problem(409, 'topic_round_exists', '本队已有选题轮或已发布任务，请继续当前流程。')
                if body.expected_revision != settings['revision']:
                    raise problem(409, 'stale_context', '团队资料已变化，请刷新后开启。')
                if not body.track.strip():
                    raise problem(422, 'track_required', '请填写本轮赛道或待讨论的范围。')
                data = {k: scrub(v.strip()) for k, v in body.model_dump(include={'track', 'rules', 'rubric'}).items()}
                data['deadline'] = (datetime.fromisoformat(now()) + timedelta(minutes=body.minutes)).isoformat(timespec='seconds')
                con.execute('INSERT INTO core_topic_rounds(id,squad_id,phase,revision,body,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                            (uid(), sid, 'discussion', 1, dump(data), now(), now()))
                core['bump'](con, sid)
            return {'round': snapshot(con, sid, actor['id']), 'duplicate': duplicate}

    @api.post(prefix + '/turns')
    def upload(sid: str, body: Turn, authorization: str = Header(default='')):
        if not body.selected:
            raise problem(422, 'selection_required', '只有本人明确选择或授权的对话才能共享。')
        values = body.model_dump(exclude={'selected', 'round_id', 'event_id'})
        if any(not values[key].strip() for key in ('topic_title', 'user_message', 'assistant_message')):
            raise problem(422, 'turn_incomplete', '请同时提供选题名称、本人发言和 AI 可见回复。')
        fp = digest(dump(body.model_dump()))
        cleaned = {k: scrub(v if k in ('user_message','assistant_message') else v.strip()) for k, v in values.items()}
        cleaned['redacted'] = any(scrub(v) != v for v in values.values())
        with db(True) as con:
            actor, _ = core['access'](con, sid, authorization)
            row = read_round(con, sid)
            if body.round_id != row['id']:
                raise problem(409, 'topic_round_changed', '选题轮已变化，请重新读取团队上下文。')
            prior = con.execute('SELECT id,fingerprint FROM core_topic_turns WHERE round_id=? AND user_id=? AND event_id=?',
                                (row['id'], actor['id'], body.event_id)).fetchone()
            if prior:
                if prior['fingerprint'] != fp:
                    raise problem(409, 'event_conflict', '同一回合标识的内容不同，未覆盖原记录。')
                return {'synced': True, 'note_id': prior['id'], 'duplicate': True, 'analysis_triggered': False}
            data = json.loads(row['body'])
            if row['phase'] != 'discussion' or data['deadline'] <= now():
                raise problem(409, 'discussion_closed', '讨论时段已结束或已进入排名。请队长延长或重新开放后再补传。')
            items = candidates(con, row['id'])
            existing = any(c['user_id'] == actor['id'] and c['title'] == cleaned['topic_title'] for c in items)
            if (len(items) >= 24 and not existing) or sum(len(c['turns']) for c in items) >= 200:
                raise problem(422, 'topic_limit', '本轮最多 24 个候选、200 个共享回合，请与队长核对讨论范围。')
            ident = uid()
            con.execute('INSERT INTO core_topic_turns VALUES(?,?,?,?,?,?,?,?)',
                        (ident, row['id'], actor['id'], actor['connection_id'], body.event_id, fp, dump(cleaned), now()))
            con.execute('DELETE FROM core_topic_ready WHERE round_id=? AND user_id=?', (row['id'], actor['id']))
            con.execute('UPDATE core_connections SET last_seen=? WHERE id=?', (now(), actor['connection_id']))
            update(con, row)
            return {'synced': True, 'note_id': ident, 'duplicate': False, 'analysis_triggered': False,
                    'notice': '本轮发言与 AI 可见回复已保存到团队方向；新增回合后请本人重新确认上传完毕。'}

    @api.post(prefix + '/ready')
    def ready(sid: str, body: Ready, background: BackgroundTasks, authorization: str = Header(default='')):
        attempt = None
        with db(True) as con:
            actor, _ = core['access'](con, sid, authorization, connector=False)
            row = read_round(con, sid)
            duplicate = operation(con, sid, actor, 'ready:' + row['id'], body)
            if not duplicate:
                version(row, body)
                if row['phase'] != 'discussion':
                    raise problem(409, 'discussion_closed', '本轮已进入下一阶段。')
                if body.complete:
                    if not con.execute('SELECT 1 FROM core_topic_turns WHERE round_id=? AND user_id=?', (row['id'], actor['id'])).fetchone():
                        raise problem(409, 'no_shared_turn', '还没有收到你的讨论回合，请先核对连接器上传结果。')
                    con.execute('INSERT OR IGNORE INTO core_topic_ready VALUES(?,?,?)', (row['id'], actor['id'], now()))
                else:
                    con.execute('DELETE FROM core_topic_ready WHERE round_id=? AND user_id=?', (row['id'], actor['id']))
                snap = snapshot(con, sid, actor['id'], False)
                data = json.loads(row['body'])
                if snap['confirmed_count'] == snap['member_count'] and snap['member_count']:
                    attempt = uid()
                    data['roster_fingerprint'] = roster_fingerprint(con, sid)
                    update(con, row, data, 'ranking', attempt_id=attempt,
                           lease_until=(datetime.fromisoformat(now()) + timedelta(minutes=5)).isoformat(timespec='seconds'))
                else:
                    update(con, row)
            result = {'round': snapshot(con, sid, actor['id']), 'duplicate': duplicate}
        if attempt:
            background.add_task(run_ranking, sid, row['id'], attempt)
        return result

    @api.post(prefix + '/reopen')
    def reopen(sid: str, body: Reopen, authorization: str = Header(default='')):
        with db(True) as con:
            actor, _ = core['access'](con, sid, authorization, True, False)
            row = read_round(con, sid)
            duplicate = operation(con, sid, actor, 'reopen:' + row['id'], body)
            if not duplicate:
                version(row, body)
                if row['phase'] == 'selected':
                    raise problem(409, 'direction_already_selected', '主方向已确认，不能重新开放本轮讨论。')
                data = json.loads(row['body'])
                data = {k: data[k] for k in ('track', 'rules', 'rubric')}
                data['deadline'] = (datetime.fromisoformat(now()) + timedelta(minutes=body.minutes)).isoformat(timespec='seconds')
                con.execute('DELETE FROM core_topic_ready WHERE round_id=?', (row['id'],))
                # Preserve earlier ballot records; the next vote uses a new number.
                data['next_ballot'] = con.execute('SELECT COALESCE(MAX(ballot),0)+1 FROM core_topic_votes WHERE round_id=?', (row['id'],)).fetchone()[0]
                update(con, row, data, 'discussion', attempt_id='', lease_until='', error='')
            return {'round': snapshot(con, sid, actor['id']), 'duplicate': duplicate}

    @api.post(prefix + '/retry')
    def retry(sid: str, body: Retry, background: BackgroundTasks, authorization: str = Header(default='')):
        attempt = None
        with db(True) as con:
            actor, _ = core['access'](con, sid, authorization, True, False)
            row = read_round(con, sid)
            duplicate = operation(con, sid, actor, 'retry:' + row['id'], body)
            if not duplicate:
                version(row, body)
                phase = current_phase(row, now())
                if phase not in ('failed', 'unknown'):
                    raise problem(409, 'ranking_not_retryable', '当前没有需要重试的排名。')
                if phase == 'unknown' and not body.acknowledge_unknown:
                    raise problem(422, 'unknown_confirmation_required', '上次结果未知，新尝试可能重复调用，请先明确确认。')
                data = json.loads(row['body'])
                same_roster(con, sid, data)
                attempt = uid()
                update(con, row, phase='ranking', attempt_id=attempt, error='',
                       lease_until=(datetime.fromisoformat(now()) + timedelta(minutes=5)).isoformat(timespec='seconds'))
            result = {'round': snapshot(con, sid, actor['id']), 'duplicate': duplicate}
        if attempt:
            background.add_task(run_ranking, sid, row['id'], attempt)
        return result

    @api.post(prefix + '/votes')
    def vote(sid: str, body: Vote, authorization: str = Header(default='')):
        with db(True) as con:
            actor, _ = core['access'](con, sid, authorization, connector=False)
            row = read_round(con, sid)
            duplicate = operation(con, sid, actor, 'vote:' + row['id'], body)
            if not duplicate:
                version(row, body)
                data = json.loads(row['body'])
                same_roster(con, sid, data)
                if row['phase'] != 'voting' or body.ballot != data['ballot'] or body.candidate_id not in data['eligible']:
                    raise problem(409, 'ballot_changed', '投票轮次或候选已变化，请重新核对。')
                prior = con.execute('SELECT 1 FROM core_topic_votes WHERE round_id=? AND ballot=? AND user_id=?',
                                    (row['id'], data['ballot'], actor['id'])).fetchone()
                if prior:
                    raise problem(409, 'already_voted', '本轮已经投票，每人一票。')
                con.execute('INSERT INTO core_topic_votes VALUES(?,?,?,?,?)', (row['id'], data['ballot'], actor['id'], body.candidate_id, now()))
                snap = snapshot(con, sid, actor['id'], False)
                phase = 'voting'
                if snap['votes_count'] == snap['member_count']:
                    high = max(snap['tallies'].values())
                    winners = [key for key, count in snap['tallies'].items() if count == high]
                    if len(winners) > 1:
                        data.update(eligible=winners, ballot=data['ballot'] + 1, previous_tie=snap['tallies'])
                    else:
                        data['winner_id'] = winners[0]
                        phase = 'awaiting_selection'
                update(con, row, data, phase)
            return {'round': snapshot(con, sid, actor['id']), 'duplicate': duplicate}

    @api.post(prefix + '/select')
    def select(sid: str, body: Select, authorization: str = Header(default='')):
        with db(True) as con:
            actor, squad = core['access'](con, sid, authorization, True, False)
            row = read_round(con, sid)
            duplicate = operation(con, sid, actor, 'select:' + row['id'], body)
            if not duplicate:
                version(row, body)
                data = json.loads(row['body'])
                same_roster(con, sid, data)
                if row['phase'] != 'awaiting_selection' or body.candidate_id != data.get('winner_id'):
                    raise problem(409, 'vote_incomplete', '请等待全员完成投票，只能确认唯一最高票方向。')
                candidate = next(c for c in candidates(con, row['id']) if c['id'] == body.candidate_id)
                settings = core['init'](con, squad)
                direction = json.loads(settings['direction'])
                direction.update(goal=candidate['title'], rules=data['rules'], rubric=data['rubric'])
                con.execute('UPDATE core_settings SET direction=? WHERE squad_id=?', (dump(direction), sid))
                data['selected_title'] = candidate['title']
                update(con, row, data, 'selected')
            return {'round': snapshot(con, sid, actor['id']), 'duplicate': duplicate}

    @api.post('/api/core/teams/{sid}/tasks/{task_key}/claim')
    def claim(sid: str, task_key: str, body: Operation, authorization: str = Header(default='')):
        with db(True) as con:
            actor, squad = core['access'](con, sid, authorization, connector=False)
            settings = core['init'](con, squad)
            planning_guard(con, sid, problem)
            duplicate = operation(con, sid, actor, 'claim:' + task_key, body)
            if not duplicate:
                if body.expected_revision != settings['revision']:
                    raise problem(409, 'stale_context', '任务状态已更新，请刷新后领取。')
                task = next((t for t in json.loads(settings['active_plan']).get('tasks', []) if t['key'] == task_key), None)
                if not task or not task.get('claim_required'):
                    raise problem(409, 'task_not_claimable', '这项任务不在待领取列表中。')
                owner = claimed_owner(con, sid, settings['plan_version'], task)
                if owner and owner != actor['id']:
                    raise problem(409, 'task_already_claimed', '这项任务已被队友领取，请选择其他任务。')
                con.execute('INSERT OR IGNORE INTO core_task_claims VALUES(?,?,?,?,?)',
                            (sid, settings['plan_version'], task_key, actor['id'], now()))
                core['bump'](con, sid)
            return {'claimed': True, 'duplicate': duplicate, 'task_key': task_key}

    def planning_context(con, sid):
        row=latest(con,sid)
        if not row or row['phase']!='selected':
            return None
        data=json.loads(row['body'])
        chosen=next(c for c in candidates(con,row['id']) if c['id']==data['winner_id'])
        budget=max(1,12000//max(1,len(chosen['turns']))//2)
        turns=[{'id':t['id'],'user_message':t['user_message'][:budget],
                'assistant_message':t['assistant_message'][:budget],
                'truncated':len(t['user_message'])>budget or len(t['assistant_message'])>budget} for t in chosen['turns']]
        assessment=next(item for item in data['ranking']['items'] if item['candidate_id']==chosen['id'])
        return {'title':chosen['title'],'user_id':chosen['user_id'],'shared_turns':turns,
                'assessment':assessment,'notice':'成员共享讨论与模型建议，非独立核实的事实；截断回合有标记。'}

    return {'snapshot': snapshot, 'planning_context':planning_context}
