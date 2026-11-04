"""Who may use the web app: only the owner, signed in with a one-time link the bot sends them on
Telegram (/web), or one printed on the server (`python -m claudebot web-login`).

- Login links carry a 256-bit token in the URL fragment (#t=...), which browsers never send to a
  server or put in a Referer, so it can't end up in a proxy log. The page posts it once; it works
  for 10 minutes and only once.
- A session is a random id in an HttpOnly, SameSite=Strict cookie. Only its SHA-256 is stored, so a
  copy of the database can't be used to sign in.
- Every change (POST/DELETE) also needs the session's CSRF token in a header, and a matching Origin
  when the browser sends one.
"""

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from ..db import Database

LOGIN_PREFIX = "weblogin:"
SESSION_PREFIX = "websession:"
LOGIN_TTL = timedelta(minutes=10)
SESSION_TTL = timedelta(days=30)
MAX_SESSIONS = 10
MAX_PENDING_LOGINS = 5


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_login_token(db: Database) -> str:
    """A one-time sign-in token; only its hash is kept. Older unused ones beyond a few are dropped."""
    token = secrets.token_urlsafe(32)
    db.set_setting(LOGIN_PREFIX + _hash(token), (_now() + LOGIN_TTL).isoformat())
    db.prune_settings(LOGIN_PREFIX, MAX_PENDING_LOGINS)
    return token


def redeem_login_token(db: Database, token: str) -> bool:
    """True once for a fresh token; it's gone afterwards whatever happens."""
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        return False
    key = LOGIN_PREFIX + _hash(token)
    expires = db.get_setting(key)
    if expires is None:
        return False
    db.delete_setting(key)
    return _now() < datetime.fromisoformat(expires)


def new_session(db: Database, user_agent: str = "") -> tuple[str, str]:
    """(session id for the cookie, CSRF token for the page). Only the id's hash is stored."""
    session_id, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    record = {"expires": (_now() + SESSION_TTL).isoformat(), "csrf": csrf, "created": _now().isoformat(),
              "agent": str(user_agent)[:120]}
    db.set_setting(SESSION_PREFIX + _hash(session_id), json.dumps(record))
    db.prune_settings(SESSION_PREFIX, MAX_SESSIONS)  # the oldest sign-ins drop off
    return session_id, csrf


def session(db: Database, session_id: str | None) -> dict | None:
    """The live session for this cookie, or None (expired ones are deleted)."""
    if not session_id or len(session_id) > 100:
        return None
    key = SESSION_PREFIX + _hash(session_id)
    raw = db.get_setting(key)
    if raw is None:
        return None
    record = json.loads(raw)
    if _now() >= datetime.fromisoformat(record["expires"]):
        db.delete_setting(key)
        return None
    return record


def end_session(db: Database, session_id: str | None) -> None:
    if session_id:
        db.delete_setting(SESSION_PREFIX + _hash(session_id))


def end_all_sessions(db: Database) -> int:
    """Sign out everywhere (and drop unused login links). Returns how many sessions ended."""
    rows = db.conn.execute(  # substr, not LIKE: "_" in a prefix would be a wildcard
        "SELECT key FROM settings WHERE substr(key, 1, ?) = ? OR substr(key, 1, ?) = ?",
        (len(SESSION_PREFIX), SESSION_PREFIX, len(LOGIN_PREFIX), LOGIN_PREFIX)).fetchall()
    for (key,) in rows:
        db.delete_setting(key)
    return sum(key.startswith(SESSION_PREFIX) for (key,) in rows)


def csrf_ok(record: dict, header: str | None) -> bool:
    return bool(header) and secrets.compare_digest(record["csrf"].encode(), str(header).encode())
