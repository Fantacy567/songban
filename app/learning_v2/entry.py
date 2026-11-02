"""Explicit, minimal interview-to-learner projection. Never reads chat messages.

The manager offers a snapshot after attesting whose interview it is. The learner
must accept that snapshot before a teaching model may use it. This resource does
not fill Start answers, grant course access, or assert observed ability.
"""
import hashlib
import json

from .protocol import fail, revision

ENTRY_FIELDS = ("goals", "experiences")
ENTRY_OPS = {"entry", "saveEntry", "confirmEntry"}


class EntryDomain:
    ENTRY_OPS = ENTRY_OPS

    def entry_authorize(self, con, op, session, params, body):
        self.role(session, *(('manager', 'learner') if op == 'entry' else ('manager',) if op == 'saveEntry' else ('learner',)))
        learner = self.learner(con, session, params['learner_id'])
        self.learning_access(con, learner['id'])
        if op != 'entry' and not self.settings.studio_enabled:
            fail(423, 'studio_paused', '新的学习摘要暂未开放，已保存记录仍可在原授权内读取。')

    def _entry_id(self, learner_id):
        return 'entry-' + hashlib.sha256(learner_id.encode()).hexdigest()[:48]

    def _entry_snapshot(self, con, learner_id):
        eid = self._entry_id(learner_id)
        row = con.execute("SELECT body FROM learn_course_objects WHERE id=? AND kind='entry' AND learner_id=?", (eid, learner_id)).fetchone()
        if row:
            return json.loads(row['body'])
        return dict(id=eid, revision=0, learner_id=learner_id, status='none', goals=[], experiences=[],
                    source_domain=None, source_version=None, source_confirmed_at=None, offered_at=None,
                    confirmed_at=None)

    def _entry_candidate(self, con, actor_id):
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='core_interviews'").fetchone():
            return None
        row = con.execute("SELECT version,draft,confirmed_at FROM core_interviews WHERE user_id=? AND status='confirmed'", (actor_id,)).fetchone()
        if not row or not row['draft'] or not row['confirmed_at']:
            return None
        try:
            draft = json.loads(row['draft'])
        except (ValueError, TypeError):
            return None
        if not isinstance(draft, dict):
            return None
        summary = {}
        for field in ENTRY_FIELDS:
            items = draft.get(field, [])
            # Legacy malformed fields do not become source facts. No inference
            # text or full evidence transcript is disclosed to the learner.
            summary[field] = [item['text'].strip() for item in items[:6]
                              if isinstance(item, dict) and item.get('basis') == 'self_reported'
                              and isinstance(item.get('text'), str) and 0 < len(item['text'].strip()) <= 60] if isinstance(items, list) else []
        return dict(source_domain='core_interview', source_version=row['version'], source_confirmed_at=row['confirmed_at'], **summary)

    def entry_read(self, con, op, session, params, query):
        self.entry_authorize(con, op, session, params, None)
        result = self._entry_snapshot(con, params['learner_id'])
        result['candidate'] = self._entry_candidate(con, session['actor_id']) if session['mode'] == 'manager' else None
        return result

    def entry_write(self, con, op, session, params, body):
        self.entry_authorize(con, op, session, params, body)
        learner_id = params['learner_id']
        old = self._entry_snapshot(con, learner_id)
        revision(body['expected_revision'], old['revision'])
        private = self.meta(con, old['id']) if old['revision'] else {}
        if op == 'saveEntry':
            if body.get('subject_confirmed') is not True:
                fail(422, 'subject_confirmation_required', '请先确认这份访谈描述的是当前孩子。')
            fields = body.get('selected_fields')
            if not isinstance(fields, list) or not fields or len(set(fields)) != len(fields) or not set(fields) <= set(ENTRY_FIELDS):
                fail(422, 'invalid_input', '请选择可带入的目标或经历摘要。')
            source = self._entry_candidate(con, session['actor_id'])
            if not source:
                fail(409, 'interview_unavailable', '当前账号没有可带入的已确认访谈。', 'reload')
            revision(body['source_version'], source['source_version'])
            snapshot = {**old, 'revision': old['revision'] + 1, 'status': 'offered',
                        'goals': source['goals'] if 'goals' in fields else [],
                        'experiences': source['experiences'] if 'experiences' in fields else [],
                        'source_domain': source['source_domain'], 'source_version': source['source_version'],
                        'source_confirmed_at': source['source_confirmed_at'], 'offered_at': self.stamp(), 'confirmed_at': None}
            private = {'source_actor_id': session['actor_id'], 'offered_by': session['actor_id'],
                       'subject_confirmed': True, 'selected_fields': fields,
                       'confirmation_session_id': None, 'decision': None}
        elif op == 'confirmEntry':
            if old['status'] == 'none':
                fail(409, 'entry_unavailable', '还没有待确认的学习摘要。', 'reload')
            if body.get('decision') not in ('accept', 'decline'):
                fail(422, 'invalid_input', '请选择采用或暂不采用这份摘要。')
            # Reversing a decision is explicit and versioned, not a silent rewrite.
            snapshot = {**old, 'revision': old['revision'] + 1,
                        'status': 'confirmed' if body['decision'] == 'accept' else 'declined',
                        'confirmed_at': self.stamp()}
            private = {**private, 'confirmation_session_id': session['id'], 'decision': body['decision']}
        else:
            fail(503, 'operation_unavailable', '入口操作尚未开放。')
        self.put(con, 'entry', snapshot, lid=learner_id, private=private)
        result = dict(snapshot)
        result['candidate'] = self._entry_candidate(con, session['actor_id']) if session['mode'] == 'manager' else None
        return result

    def confirmed_entry_context(self, con, session, learner_id):
        """Minimal optional model context. Call within the authorized transaction."""
        self.entry_authorize(con, 'entry', session, {'learner_id': learner_id}, None)
        entry = self._entry_snapshot(con, learner_id)
        if entry['status'] != 'confirmed':
            return None
        return {k: entry[k] for k in ('id', 'revision', 'goals', 'experiences', 'source_domain', 'source_version')}
