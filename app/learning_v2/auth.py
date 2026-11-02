"""Existing people/password and login_attempts adapter; no second account store."""
from datetime import datetime, timezone

from .protocol import Problem, fail
from .service import digest, iso


class AuthFailure(Problem):
    """Only login_attempts changes may be committed on this failure."""


def password_actor(service, con, request, account, proof):
    # These are the existing normalization functions and shared rate-limit keys.
    from app.studio import normalize_phone
    from app.email_delivery import normalize_email
    phone = normalize_phone(account)
    account = account.strip()
    source = request.client.host if request.client else "unknown"
    keys = (("account:" + digest(phone or account.casefold()), 5), ("source:" + digest(source), 20))
    for key, _ in keys:
        row = con.execute("SELECT blocked_until FROM login_attempts WHERE key=?", (key,)).fetchone()
        if row and row[0]:
            stamp = datetime.fromisoformat(row[0])
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            if stamp.timestamp() > service.clock():
                fail(429, "rate_limited", "认证尝试过多，请五分钟后再试。")
    columns = {r[1] for r in con.execute("PRAGMA table_info(people)")}
    person = None
    if phone and "phone" in columns:
        person = con.execute("SELECT * FROM people WHERE phone=?", (phone,)).fetchone()
    elif normalize_email(account) and "email" in columns:
        person = con.execute("SELECT * FROM people WHERE email=?", (normalize_email(account),)).fetchone()
    if not person and "username" in columns:
        person = con.execute("SELECT * FROM people WHERE username=?", (account,)).fetchone()
    try:
        # Constant-cost missing-user path uses the existing algorithm too.
        stored = person["password_hash"] if person and person["password_hash"] else "pbkdf2_sha256$120000$00000000000000000000000000000000$" + "0" * 64
        matched = service.password_verifier(stored, proof)
    except (ValueError, TypeError, OverflowError):
        matched = False
    if not person or not matched:
        blocked = False
        for key, limit in keys:
            row = con.execute("SELECT attempts FROM login_attempts WHERE key=?", (key,)).fetchone()
            count = (row[0] if row else 0) + 1
            until = iso(service.clock() + 300) if count >= limit else ""
            blocked = blocked or bool(until)
            con.execute("INSERT INTO login_attempts VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET attempts=excluded.attempts,blocked_until=excluded.blocked_until,updated_at=excluded.updated_at", (key, count, until, iso(service.clock())))
        raise AuthFailure(429 if blocked else 401, "rate_limited" if blocked else "bad_login", "认证尝试过多，请五分钟后再试。" if blocked else "账号或密码不正确。", "reauthenticate")
    con.executemany("DELETE FROM login_attempts WHERE key=?", ((key,) for key, _ in keys))
    return person["id"]
