"""Auth session helpers and SQLite-backed login throttle."""
from __future__ import annotations

import time

from flask import request, session

from db import get_setting
from parsing import as_clean_string


# Login throttle (stored in SQLite so gunicorn multi-worker processes share state).
# 5 failures / 15 min: personal self-host defaults — room for typos, but with
# PBKDF2-SHA256 (200k iters) even 5 tries is expensive; 5 per 15 min ≈ 480/day
# per IP bucket and per username bucket, enough to stall online guessing without
# long accidental lockouts for the real owner.
LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60

AUTH_EXEMPT_EXACT = {"/", "/api/health", "/api/auth/login", "/api/auth/logout", "/api/auth/status"}


def auth_configured(db):
    username = get_setting(db, "auth_username", "")
    password_hash = get_setting(db, "auth_password_hash", "")
    return bool(username and password_hash)


def is_authed():
    from flask import current_app

    authed_at = session.get("authed_at")
    if not authed_at:
        return False
    max_age = current_app.permanent_session_lifetime.total_seconds()
    return (time.time() - authed_at) < max_age


def client_ip():
    """
    Client address for login throttle keys.
    With ProxyFix (TRUST_PROXY_COUNT>0), request.remote_addr is rewritten from
    X-Forwarded-For so we see the real client behind Nginx/Caddy, not the proxy.
    """
    addr = (request.remote_addr or "").strip()
    return addr or "unknown"


def login_attempt_keys(username):
    """Return (ip_key, user_key_or_None) used as login_attempts.identifier values."""
    ip_key = f"ip:{client_ip()}"
    cleaned = as_clean_string(username)
    user_key = f"user:{cleaned.casefold()}" if cleaned else None
    return ip_key, user_key


def login_lock_remaining(db, identifier):
    """Seconds remaining on lock for identifier, or 0 if not locked."""
    if not identifier:
        return 0
    row = db.execute(
        "SELECT locked_until FROM login_attempts WHERE identifier = ?",
        (identifier,),
    ).fetchone()
    if not row:
        return 0
    remaining = float(row["locked_until"] or 0) - time.time()
    return remaining if remaining > 0 else 0


def any_login_lock_remaining(db, identifiers):
    """Max remaining lock seconds among identifiers (0 if none locked)."""
    remaining = 0.0
    for identifier in identifiers:
        remaining = max(remaining, login_lock_remaining(db, identifier))
    return remaining


def record_login_failure(db, identifier):
    """
    Atomically increment failure count for identifier; lock when threshold is reached.
    Single-statement UPSERT so concurrent gunicorn workers cannot lose increments
    even though they share one SQLite file (not process-local memory).
    """
    if not identifier:
        return
    now = time.time()
    # ON CONFLICT expressions see the pre-update row; reset the window if a prior
    # lock has already expired so the owner is not permanently ratcheted up.
    db.execute(
        """
        INSERT INTO login_attempts(identifier, fail_count, last_failed_at, locked_until)
        VALUES (?, 1, ?, 0)
        ON CONFLICT(identifier) DO UPDATE SET
            fail_count = CASE
                WHEN login_attempts.locked_until > 0
                     AND login_attempts.locked_until <= excluded.last_failed_at
                THEN 1
                ELSE login_attempts.fail_count + 1
            END,
            last_failed_at = excluded.last_failed_at,
            locked_until = CASE
                WHEN (
                    CASE
                        WHEN login_attempts.locked_until > 0
                             AND login_attempts.locked_until <= excluded.last_failed_at
                        THEN 1
                        ELSE login_attempts.fail_count + 1
                    END
                ) >= ?
                THEN excluded.last_failed_at + ?
                ELSE 0
            END
        """,
        (identifier, now, LOGIN_MAX_FAILURES, float(LOGIN_LOCKOUT_SECONDS)),
    )


def clear_login_attempts(db, identifier):
    if not identifier:
        return
    db.execute("DELETE FROM login_attempts WHERE identifier = ?", (identifier,))
