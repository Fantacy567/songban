"""Shared platform identity, transaction and replay boundary. No environment loading."""
from dataclasses import dataclass
import hashlib
import json
import secrets

from app.learning_v2.protocol import canonical, fail
from app.learning_v2.service import digest, iso


@dataclass(frozen=True)
class PlatformSettings:
    enabled: bool = False
    navigation_enabled: bool = False
    demo_mode: bool = False
    image_settings: object | None = None
    companion_settings: object | None = None
    creative_studio_enabled: bool = False


CORE_DDL = """
CREATE TABLE platform_requests (
 owner TEXT NOT NULL, scope TEXT NOT NULL, operation TEXT NOT NULL, request_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL, result TEXT NOT NULL, status INTEGER NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(owner,scope,operation,request_id)
);
"""


class PlatformService:
    version = '0.1.0'

    def __init__(self, learning, settings):
        if not isinstance(settings, PlatformSettings):
            raise TypeError('Explicit PlatformSettings required')
        self.learning, self.store, self.settings = learning, learning.store, settings
        self.domains = []
        self.portfolio = None
        self.companion = None
        self.images = None

    def migrate(self):
        checksum = hashlib.sha256(CORE_DDL.encode()).hexdigest()
        with self.store.transaction() as con:
            con.execute('CREATE TABLE IF NOT EXISTS platform_migrations(version TEXT PRIMARY KEY,checksum TEXT NOT NULL,applied_at TEXT NOT NULL)')
            old = con.execute("SELECT checksum FROM platform_migrations WHERE version='P00-platform'").fetchone()
            if old:
                if old[0] != checksum:
                    raise ValueError('Platform core checksum mismatch')
                return
            for sql in CORE_DDL.split(';'):
                if sql.strip():
                    con.execute(sql)
            con.execute("INSERT INTO platform_migrations VALUES('P00-platform',?,?)", (checksum, iso(self.learning.clock())))

    def identity(self, con, request, writing):
        """Cookie mode always wins. A bearer cannot escape a child's browser epoch."""
        learning = self.learning
        learning.transport(request)
        if request.cookies.get(learning.cookie_name):
            browser = learning.browser(con, request)
            session = learning.session_row(con, request, browser)
            if writing:
                learning.write_guard(con, request, browser)
            return dict(session), lambda: learning.session_row(con, request, browser)
        learning.legacy_request_guard(con, request)
        header = request.headers.get('authorization', '')
        if not header.startswith('Bearer ') or not 8 <= len(header) <= 600 or header[7:].startswith('sbconn_'):
            fail(401, 'session_required', '请先确认学习身份或登录比赛账号。', 'reauthenticate')
        actor = con.execute('SELECT id FROM people WHERE token_hash=?', (digest(header[7:]),)).fetchone()
        if not actor:
            fail(401, 'session_revoked', '当前账号已失效，请重新登录。', 'reauthenticate')
        fence = learning.legacy_request_guard(con, request, actor[0])
        if writing:
            learning.origin(request)
        return {'id': 'participant:'+actor[0], 'mode': 'participant', 'actor_id': actor[0], 'learner_id': None,
                'revision': fence.auth_epoch, 'epoch': fence.mode_epoch, 'browser_id': fence.browser_id,
                'auth_epoch': fence.auth_epoch, 'token_hash': fence.token_hash}, lambda: learning.legacy_validate_fence(con, fence, write=writing)

    def perform(self, domain, op, request, body, status, response_schema, *, response_factory=None):
        writing = request.method != 'GET'
        with self.store.transaction() as con:
            session, recheck = self.identity(con, request, writing)
            params = dict(request.path_params)
            if writing and not self.settings.enabled:
                # No new content while paused. History and explicit revocation stay readable.
                if not (op == 'decideCompetitionLink' and body.get('decision') == 'revoke'):
                    fail(423, 'platform_paused', '新操作暂时暂停，已保存记录仍可查看。')
            domain.authorize(con, op, session, params, body)
            if writing:
                owner = 'learner:'+session['learner_id'] if session['mode'] == 'learner' else session['mode']+':'+session['actor_id']
                scope = request.url.path
                fingerprint = self.learning.mac(con, canonical({'body': body, 'path': scope}))
                old = con.execute('SELECT * FROM platform_requests WHERE owner=? AND scope=? AND operation=? AND request_id=?',
                                  (owner, scope, op, body['request_id'])).fetchone()
                if old:
                    if not secrets.compare_digest(old['fingerprint'], fingerprint):
                        fail(409, 'idempotency_conflict', '这个操作号已用于不同内容，请核对原操作。')
                    result, status = json.loads(old['result']), old['status']
                    # Domains can refresh a replay to avoid resurrecting revoked projections.
                    if hasattr(domain, 'replay'):
                        result = domain.replay(con, op, session, params, body, result)
                else:
                    result = domain.write(con, op, session, params, body)
                    con.execute('INSERT INTO platform_requests VALUES(?,?,?,?,?,?,?,?)',
                                (owner, scope, op, body['request_id'], fingerprint, canonical(result), status, iso(self.learning.clock())))
                    self.learning.audit(con, session['actor_id'], 'platform:'+op, result.get('id', params.get('learner_id', owner)), {'request_id': body['request_id']})
            else:
                result = domain.read(con, op, session, params, request.query_params)
            if domain is self.portfolio and self.images and op in ('works', 'work', 'createExternalWork', 'versionExternalWork'):
                for work in result['items'] if op == 'works' else [result]:
                    if 'open_studio' in work.get('available_actions', []):
                        # Studio versions are private code archives; the existing
                        # image target domain does not yet support these IDs.
                        continue
                    projection = self.images.read(con, 'workImages', session,
                        {'learner_id': work['learner_id'], 'work_id': work['id']}, {})
                    work['cover_asset_id'] = projection['cover_asset_id']
            recheck()
            if response_schema is not None:
                result = response_schema.model_validate(result).model_dump()
            # Build/serialize the private response at the same serialized point
            # as its final identity check, as learning_v2 already does. The
            # optional factory preserves direct domain-test callers' tuple API.
            response = response_factory(result, status) if response_factory else None
        if response_factory:
            return response
        return result, status
