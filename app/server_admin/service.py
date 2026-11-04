"""Server-owned provider configuration and verified-email administration.

people.email is only written by the existing verified email registration/binding
flows. An email supplied in a request is never used to decide administration.
"""
from dataclasses import dataclass, replace
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

from app.learning_v2.protocol import canonical, fail
from app.learning_v2.service import digest, iso


@dataclass(frozen=True)
class AdminSettings:
    allowed_emails: tuple[str, ...] = ()
    secret_dir: Path | None = None
    enabled: bool = True


DEFAULTS = {
    'text': dict(enabled=False, provider='deepseek', base_url='https://api.deepseek.com', model='deepseek-chat',
                 max_calls=0, max_output_tokens=800, timeout_seconds=90, max_concurrency=1),
    'image': dict(enabled=False, provider='doubao', base_url='https://ark.cn-beijing.volces.com/api/v3', model='',
                  max_calls=0, max_output_tokens=800, timeout_seconds=120, max_concurrency=1,
                  size='2K', supports_sequential_generation=True, allowed_response_models=[]),
}

DDL = '''
CREATE TABLE IF NOT EXISTS server_admin_config (
 kind TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL,
 secret_ref TEXT, updated_at TEXT NOT NULL, actor_id TEXT);
CREATE TABLE IF NOT EXISTS server_admin_audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id TEXT NOT NULL, action TEXT NOT NULL,
 kind TEXT NOT NULL, revision INTEGER NOT NULL, changed_fields TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS server_admin_requests (
 actor_id TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
 kind TEXT NOT NULL, result_revision INTEGER NOT NULL, PRIMARY KEY(actor_id,request_id));
'''


class SecretFiles:
    """Opaque references to a private server directory, never stored in SQLite.

    Files are immutable: a failed transaction can leave an unused private file,
    but can never overwrite the key referenced by a committed configuration.
    """
    def __init__(self, directory):
        self.directory = Path(directory).resolve() if directory is not None else None

    def prepare(self):
        if self.directory is None:
            fail(503, 'secret_store_unavailable', '尚未配置服务端私密目录。')
        repository = Path(__file__).resolve().parents[2]
        if self.directory == repository or repository in self.directory.parents:
            fail(503, 'secret_store_unavailable', '私密目录必须位于源码和静态文件目录之外。')
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == 'nt':
            # SID avoids locale-specific user names; no secret is passed to a process.
            result = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True, text=True, check=True)
            match = re.search(r'S-1-[0-9-]+', result.stdout)
            if not match:
                raise OSError('Cannot resolve private directory owner')
            subprocess.run(['icacls', str(self.directory), '/inheritance:r', '/grant:r', '*'+match[0]+':(OI)(CI)F'],
                           check=True, capture_output=True)
        else:
            self.directory.chmod(0o700)

    def write(self, value):
        self.prepare()
        reference = secrets.token_hex(24)
        path = self.directory / (reference+'.secret')
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as target:
            target.write(value)
            target.flush()
            os.fsync(target.fileno())
        return reference

    def read(self, reference):
        if not reference or not self.directory or not re.fullmatch('[0-9a-f]{48}', reference):
            return ''
        path = self.directory / (reference+'.secret')
        if path.is_symlink() or path.resolve().parent != self.directory:
            return ''
        try:
            if path.stat().st_size > 4096:
                return ''
            return path.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            return ''


class AdminService:
    def __init__(self, learning, settings, *, demo=False):
        if not isinstance(settings, AdminSettings):
            raise TypeError('Explicit AdminSettings required')
        self.learning, self.store, self.settings, self.demo = learning, learning.store, settings, demo
        self.secrets = SecretFiles(settings.secret_dir)
        self.image_base = None
        self.images = None

    def bind_image_runtime(self, images, base_settings):
        """Deployment-only storage/consent policy, write-only admin provider keys."""
        from app.platform_v1.images import ImageSettings
        if self.image_base is not None or not isinstance(base_settings, ImageSettings):
            raise ValueError('Explicit private image storage and policy required')
        images.bind_runtime(lambda *, con=None: self.image_runtime(con=con))
        self.image_base, self.images = base_settings, images

    def image_runtime(self, base_settings=None, *, con=None):
        from app.platform_v1.images import ImageSettings
        base = self.image_base if base_settings is None else base_settings
        if not isinstance(base, ImageSettings):
            raise ValueError('Image runtime is not bound')
        config = self.runtime_config('image', con=con)
        return replace(base, config_version='server-admin:image:'+str(config['revision']),
                       live_enabled=config['enabled'], api_key=config['api_key'], model=config['model'],
                       image_limit=min(config['max_calls'],10000), max_concurrency=config['max_concurrency'],
                       timeout_seconds=config['timeout_seconds'], lease_seconds=config['timeout_seconds']+30,
                       size=config['size'], supports_sequential_generation=config['supports_sequential_generation'],
                       allowed_response_models=tuple(config['allowed_response_models']))

    def migrate(self):
        with self.store.transaction() as con:
            checksum = hashlib.sha256(DDL.encode()).hexdigest()
            con.execute('CREATE TABLE IF NOT EXISTS server_admin_migrations(version TEXT PRIMARY KEY,checksum TEXT NOT NULL,applied_at TEXT NOT NULL)')
            prior = con.execute("SELECT checksum FROM server_admin_migrations WHERE version='SA01-config'").fetchone()
            if prior and prior[0] != checksum:
                raise ValueError('Server admin migration checksum mismatch')
            if not prior:
                for sql in DDL.split(';'):
                    if sql.strip():
                        con.execute(sql)
                con.execute("INSERT INTO server_admin_migrations VALUES('SA01-config',?,?)", (checksum, iso(self.learning.clock())))
            for kind, payload in DEFAULTS.items():
                con.execute('INSERT OR IGNORE INTO server_admin_config VALUES(?,0,?,NULL,?,NULL)',
                            (kind, canonical(payload), iso(self.learning.clock())))

    def permitted(self, con, actor):
        allowed = {email.strip().lower() for email in self.settings.allowed_emails}
        row = con.execute('SELECT * FROM people WHERE id=?', (actor,)).fetchone()
        columns = row.keys() if row else ()
        email = (row['email'] or '').strip().lower() if 'email' in columns else ''
        guest_table = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='core_guest_people'").fetchone()
        guest = guest_table and con.execute('SELECT 1 FROM core_guest_people WHERE user_id=?', (actor,)).fetchone()
        if not self.settings.enabled or self.demo or not email or email not in allowed or guest:
            fail(403, 'admin_required', '此账号没有服务端管理权限，请使用已授权且已验证的管理员邮箱登录。')
        return email

    def identity(self, con, request, writing=False):
        learn = self.learning
        learn.transport(request)
        if request.cookies.get(learn.cookie_name):
            browser = learn.browser(con, request)
            session = learn.session_row(con, request, browser)
            if session['mode'] not in ('manager', 'staff'):
                fail(403, 'child_mode_restricted', '请退出孩子模式并重新登录管理员账号。')
            if writing:
                learn.write_guard(con, request, browser)
            actor = session['actor_id']
            def recheck():
                current = learn.session_row(con, request, learn.browser(con, request))
                if current['mode'] not in ('manager', 'staff') or current['actor_id'] != actor:
                    fail(403, 'admin_required', '管理员身份已经变化，请重新登录。')
                self.permitted(con, actor)
        else:
            learn.legacy_request_guard(con, request)
            authorization = request.headers.get('authorization', '')
            token = authorization[7:] if authorization.startswith('Bearer ') and len(authorization) <= 600 else ''
            if not token or token.startswith('sbconn_'):
                fail(401, 'session_required', '请先登录管理员邮箱。', 'reauthenticate')
            row = con.execute('SELECT id FROM people WHERE token_hash=?', (digest(token),)).fetchone()
            if not row:
                fail(401, 'session_revoked', '账号已失效，请重新登录。', 'reauthenticate')
            actor = row[0]
            fence = learn.legacy_request_guard(con, request, actor)
            if writing:
                learn.origin(request)
            def recheck():
                learn.legacy_validate_fence(con, fence, write=writing)
                self.permitted(con, actor)
        email = self.permitted(con, actor)
        return actor, email, recheck

    def view(self, con, kind):
        row = con.execute('SELECT * FROM server_admin_config WHERE kind=?', (kind,)).fetchone()
        if not row:
            fail(404, 'config_not_found', '找不到这个配置。')
        payload = dict(DEFAULTS[kind], **json.loads(row['payload']))
        configured = bool(self.secrets.read(row['secret_ref']))
        bound = kind == 'text' or bool(self.image_base and self.image_base.storage_dir)
        ready = bound and payload['enabled'] and configured and bool(payload['model']) and payload['max_calls'] > 0
        return dict(payload, revision=row['revision'], key_configured=configured,
                    integration_status='creative_studio' if kind == 'text' else 'private_images' if bound else 'pending',
                    configuration_ready=ready, provider_verified=False, updated_at=row['updated_at'])

    def runtime_config(self, kind='text', *, con=None):
        """INTERNAL ONLY: never serialize this dictionary in a response or log.

        Credentials go to the host's fixed-provider proxy, not the agent sandbox.
        max_calls is a cumulative ceiling, not a fresh grant on every revision.
        """
        if kind not in DEFAULTS:
            raise ValueError('Unknown provider kind')
        with (nullcontext(con) if con is not None else self.store.transaction()) as con:
            row = con.execute('SELECT * FROM server_admin_config WHERE kind=?', (kind,)).fetchone()
            config = dict(DEFAULTS[kind], **json.loads(row['payload']))
            key = self.secrets.read(row['secret_ref'])
            enabled = (kind == 'text' or bool(self.image_base and self.image_base.storage_dir)) and self.settings.enabled and not self.demo and config['enabled'] and bool(key) and bool(config['model']) and config['max_calls'] > 0
            return dict(config, enabled=enabled, api_key=key if enabled else '', revision=row['revision'])

    def save(self, con, actor, kind, body):
        if kind not in DEFAULTS:
            fail(404, 'config_not_found', '找不到这个配置。')
        fingerprint = self.learning.mac(con, canonical({'kind': kind, 'body': body}))
        previous = con.execute('SELECT * FROM server_admin_requests WHERE actor_id=? AND request_id=?', (actor, body['request_id'])).fetchone()
        if previous:
            if not secrets.compare_digest(previous['fingerprint'], fingerprint):
                fail(409, 'idempotency_conflict', '该操作号已经用于其他内容，请重新读取。')
            return self.view(con, kind)
        row = con.execute('SELECT * FROM server_admin_config WHERE kind=?', (kind,)).fetchone()
        if row['revision'] != body['expected_revision']:
            fail(409, 'revision_conflict', '其他管理员已经更新配置，请重新读取。', 'reload', row['revision'])
        payload = {key: body[key] for key in DEFAULTS[kind] if key not in ('provider', 'base_url')}
        payload.update(provider=DEFAULTS[kind]['provider'], base_url=DEFAULTS[kind]['base_url'])
        if kind == 'image' and payload['max_calls'] > 10000:
            fail(422, 'invalid_image_limit', '累计图片请求上限不得超过10000次。')
        if kind == 'image' and payload['enabled'] and not (self.image_base and self.image_base.storage_dir):
            fail(409, 'image_integration_pending', '图片配置可保存准备，但尚未接入当前图片运行层，暂不能启用。')
        if payload['enabled'] and not payload['model']:
            fail(422, 'model_required', '启用前请填写已开通的模型或推理接入点。')
        reference = row['secret_ref']
        if body['clear_key']:
            reference = None
        elif body['api_key']:
            reference = self.secrets.write(body['api_key'])
        if payload['enabled'] and not self.secrets.read(reference):
            fail(422, 'key_required', '启用服务前需要在服务端保存有效配置密钥。')
        old = json.loads(row['payload'])
        fields = [key for key in payload if payload[key] != old.get(key)]
        if reference != row['secret_ref']:
            fields.append('api_key')
        revision = row['revision']+1
        stamp = iso(self.learning.clock())
        con.execute('UPDATE server_admin_config SET revision=?,payload=?,secret_ref=?,updated_at=?,actor_id=? WHERE kind=?',
                    (revision, canonical(payload), reference, stamp, actor, kind))
        if kind == 'image' and self.images is not None:
            self.images.cancel_stale_queued(con)
        con.execute('INSERT INTO server_admin_audit(actor_id,action,kind,revision,changed_fields,created_at) VALUES(?,?,?,?,?,?)',
                    (actor, 'configuration_saved', kind, revision, canonical(fields), stamp))
        con.execute('INSERT INTO server_admin_requests VALUES(?,?,?,?,?)', (actor, body['request_id'], fingerprint, kind, revision))
        return self.view(con, kind)
