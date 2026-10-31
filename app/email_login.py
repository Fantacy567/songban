"""Email identities and one-time challenges, independent of the SMS transport."""
import secrets
from datetime import datetime, timedelta

from fastapi import Header, Request

from .email_delivery import deliver_email_code, email_status, normalize_email


def ensure_email_schema(con):
    columns = {row[1] for row in con.execute('PRAGMA table_info(people)')}
    if 'email' not in columns:
        con.execute('ALTER TABLE people ADD COLUMN email TEXT')
    con.execute('CREATE UNIQUE INDEX IF NOT EXISTS people_email_unique ON people(email) WHERE email IS NOT NULL')
    con.executescript('''
        CREATE TABLE IF NOT EXISTS email_codes (
            id TEXT PRIMARY KEY, email TEXT NOT NULL, purpose TEXT NOT NULL,
            owner_id TEXT NOT NULL DEFAULT '', code_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            UNIQUE(email, purpose, owner_id)
        );
        CREATE TABLE IF NOT EXISTS email_send_events (
            id TEXT PRIMARY KEY, recipient_key TEXT NOT NULL, source_key TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS email_send_recipient ON email_send_events(recipient_key, created_at);
        CREATE INDEX IF NOT EXISTS email_send_source ON email_send_events(source_key, created_at);
    ''')


def register_email_login(api, db, problem, now, uid, digest, *, login_keys,
                         login_blocked, record_login_failure, login_response,
                         normalize_password, hash_password):
    def address(body):
        email = normalize_email(body.get('email'))
        if not email:
            raise problem(422, 'invalid_email', '填写有效的邮箱地址。')
        return email

    def actor(con, authorization):
        token = authorization[7:] if authorization.startswith('Bearer ') and len(authorization) < 600 else ''
        user = con.execute('SELECT * FROM people WHERE token_hash=?', (digest(token),)).fetchone() if token else None
        if not user:
            raise problem(401, 'unauthorized', '请先登录已有账号，再绑定邮箱。')
        if con.execute('SELECT 1 FROM core_guest_people WHERE user_id=?', (user['id'],)).fetchone():
            raise problem(403, 'registration_required', '访客请先用邮箱注册账号。')
        return user

    def binding_allowed(con, user, email):
        if user['email']:
            raise problem(409, 'email_already_bound', '此账号已绑定邮箱，可以直接用邮箱登录。')
        if con.execute('SELECT 1 FROM people WHERE email=?', (email,)).fetchone():
            raise problem(409, 'email_in_use', '这个邮箱已用于其他账号，请使用其他邮箱。')

    def verify(con, email, code, purpose, owner, request):
        keys = login_keys(request, email)
        if login_blocked(con, keys):
            raise problem(429, 'login_wait', '验证失败次数过多，请五分钟后再试。')
        row = con.execute('SELECT * FROM email_codes WHERE email=? AND purpose=? AND owner_id=?',
                          (email, purpose, owner)).fetchone()
        valid = bool(row and row['status'] == 'sent' and row['expires_at'] > now()
                     and row['attempts'] < 5 and secrets.compare_digest(row['code_hash'], digest(f"{row['id']}:{email}:{purpose}:{owner}:{code}")))
        if not valid:
            if row:
                if row['attempts'] >= 4 or row['expires_at'] <= now():
                    con.execute('DELETE FROM email_codes WHERE id=?', (row['id'],))
                else:
                    con.execute('UPDATE email_codes SET attempts=attempts+1 WHERE id=?', (row['id'],))
            blocked = record_login_failure(con, keys)
            con.commit()  # Retain failed-attempt counters when returning an HTTP error.
            raise problem(429 if blocked else 401, 'login_wait' if blocked else 'bad_code',
                          '验证失败次数过多，请五分钟后再试。' if blocked else '验证码不正确或已过期，请重新获取。')
        return row['id'], keys

    @api.get('/api/studio/email-status')
    def configuration_status():
        return email_status()

    @api.get('/api/studio/account')
    def account(authorization: str = Header(default='')):
        with db() as con:
            user = actor(con, authorization)
            return {'email': user['email'] or '', 'name': user['name']}

    @api.post('/api/studio/email-codes')
    def send_code(body: dict, request: Request, authorization: str = Header(default='')):
        email = address(body)
        purpose = body.get('purpose', 'login')
        if purpose not in ('login', 'bind'):
            raise problem(422, 'invalid_purpose', '请选择登录或绑定邮箱。')
        if not email_status()['ready']:
            raise problem(503, 'email_unavailable', '邮箱登录暂不可用，请联系管理员配置发件邮箱。')
        owner = ''
        code = f'{secrets.randbelow(1000000):06d}'
        challenge_id = uid()
        current = now()
        source = digest(request.client.host if request.client else 'unknown')
        recipient = digest(email)
        with db(True) as con:
            if purpose == 'bind':
                user = actor(con, authorization)
                binding_allowed(con, user, email)
                owner = user['id']
            hour_ago = (datetime.fromisoformat(current) - timedelta(hours=1)).isoformat()
            minute_ago = (datetime.fromisoformat(current) - timedelta(seconds=60)).isoformat()
            con.execute('DELETE FROM email_send_events WHERE created_at<?', (hour_ago,))
            count, latest = con.execute('SELECT count(*),max(created_at) FROM email_send_events WHERE recipient_key=?', (recipient,)).fetchone()
            source_count = con.execute('SELECT count(*) FROM email_send_events WHERE source_key=?', (source,)).fetchone()[0]
            if (latest and latest > minute_ago) or count >= 5 or source_count >= 20:
                raise problem(429, 'email_wait', '请求过于频繁：每次发送间隔 60 秒，每个邮箱每小时最多 5 次，请稍后重试。')
            con.execute('INSERT INTO email_send_events VALUES(?,?,?,?)', (challenge_id, recipient, source, current))
            con.execute('''INSERT INTO email_codes(id,email,purpose,owner_id,code_hash,expires_at,status)
                           VALUES(?,?,?,?,?,?,'pending') ON CONFLICT(email,purpose,owner_id) DO UPDATE SET
                           id=excluded.id,code_hash=excluded.code_hash,expires_at=excluded.expires_at,status='pending',attempts=0''',
                        (challenge_id, email, purpose, owner, digest(f'{challenge_id}:{email}:{purpose}:{owner}:{code}'),
                         (datetime.fromisoformat(current) + timedelta(minutes=10)).isoformat()))
        # Do not hold SQLite's write lock across a network call. Pending codes cannot authenticate.
        try:
            deliver_email_code(email, code, purpose)
        except RuntimeError:
            with db(True) as con:
                con.execute('DELETE FROM email_codes WHERE id=?', (challenge_id,))
            raise problem(502, 'email_delivery_failed', '验证码邮件未能发送，请稍后重试或联系管理员。') from None
        with db(True) as con:
            con.execute("UPDATE email_codes SET status='sent' WHERE id=?", (challenge_id,))
        return {'sent': True, 'expires_in': 600, 'retry_after': 60, 'notice': '验证码已发送，请查看邮箱；如未收到，请检查垃圾邮件。'}

    @api.post('/api/studio/login-email')
    def login(body: dict, request: Request):
        email = address(body)
        with db(True) as con:
            challenge, keys = verify(con, email, str(body.get('code') or '').strip(), 'login', '', request)
            user = con.execute('SELECT * FROM people WHERE email=?', (email,)).fetchone()
            if not user:
                raise problem(422, 'registration_required', '这个邮箱尚未注册，请补充姓名并设置密码。已有手机号账号请先登录并绑定邮箱。')
            con.execute('DELETE FROM email_codes WHERE id=?', (challenge,))
            return login_response(con, user, keys, '已用邮箱验证码进入。')

    @api.post('/api/studio/register-email')
    def register(body: dict, request: Request, authorization: str = Header(default='')):
        email = address(body)
        password = normalize_password(body.get('password'))
        if not password:
            raise problem(422, 'invalid_password', '密码需要 8–64 个字符，首尾不能有空格。')
        fields = {}
        for key, label, maximum in [('name', '名字', 40), ('skills', '目前做得到的事', 500), ('profile', '这次想尝试什么', 2000)]:
            value = body.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise problem(422, 'invalid_input', f'{label}不能为空或超过 {maximum} 字。')
            fields[key] = value.strip()
        encoded = hash_password(password)
        with db(True) as con:
            challenge, keys = verify(con, email, str(body.get('code') or '').strip(), 'login', '', request)
            if con.execute('SELECT 1 FROM people WHERE email=?', (email,)).fetchone():
                raise problem(409, 'email_in_use', '这个邮箱已经注册，请返回邮箱登录。')
            # An explicitly registered guest keeps their drafts, preferences, and team memberships.
            token = authorization[7:] if authorization.startswith('Bearer ') and len(authorization) < 600 else ''
            guest = con.execute('SELECT p.id FROM people p JOIN core_guest_people g ON g.user_id=p.id WHERE p.token_hash=?', (digest(token),)).fetchone() if token else None
            user_id = guest['id'] if guest else uid()
            if guest:
                con.execute('UPDATE people SET email=?,name=?,skills=?,profile=?,password_hash=? WHERE id=?',
                            (email, fields['name'], fields['skills'], fields['profile'], encoded, user_id))
                con.execute('DELETE FROM core_guest_people WHERE user_id=?', (user_id,))
            else:
                con.execute('''INSERT INTO people(id,phone,phone_real,email,name,skills,profile,password_hash,token_hash,created_at)
                               VALUES(?,?,0,?,?,?,?,?,?,?)''',
                            (user_id, 'email:' + user_id, email, fields['name'], fields['skills'], fields['profile'], encoded, digest(secrets.token_urlsafe(24)), now()))
            con.execute('DELETE FROM email_codes WHERE id=?', (challenge,))
            user = con.execute('SELECT * FROM people WHERE id=?', (user_id,)).fetchone()
            return login_response(con, user, keys, '邮箱注册成功。') | {'returning': False}

    @api.post('/api/studio/email-bind')
    def bind(body: dict, request: Request, authorization: str = Header(default='')):
        email = address(body)
        with db(True) as con:
            user = actor(con, authorization)
            binding_allowed(con, user, email)
            challenge, keys = verify(con, email, str(body.get('code') or '').strip(), 'bind', user['id'], request)
            con.execute('UPDATE people SET email=? WHERE id=?', (email, user['id']))
            con.execute('DELETE FROM email_codes WHERE id=?', (challenge,))
            user = con.execute('SELECT * FROM people WHERE id=?', (user['id'],)).fetchone()
            return login_response(con, user, keys, '邮箱已绑定，团队和资料保持不变。')
