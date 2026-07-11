"""
Login throttle / lockout tests (SQLite-backed, shared across workers).

Thresholds are monkeypatched small so tests stay fast; production defaults are
LOGIN_MAX_FAILURES=5 and LOGIN_LOCKOUT_SECONDS=900 (see app.py comments).
"""

from __future__ import annotations

import time

import pytest

import auth_util
from app import hash_password, set_setting


@pytest.fixture
def auth_ready(app_mod, monkeypatch):
    """Isolated DB with credentials; 3 failures → 60s lock for fast tests."""
    # Patch the module that record_login_failure actually reads
    monkeypatch.setattr(auth_util, "LOGIN_MAX_FAILURES", 3)
    monkeypatch.setattr(auth_util, "LOGIN_LOCKOUT_SECONDS", 60)
    monkeypatch.setattr(app_mod, "LOGIN_MAX_FAILURES", 3)
    monkeypatch.setattr(app_mod, "LOGIN_LOCKOUT_SECONDS", 60)
    with app_mod.get_db() as db:
        set_setting(db, "auth_username", "owner")
        set_setting(db, "auth_password_hash", hash_password("correct-horse"))
        db.commit()
    return app_mod


def _login(client, username, password, forwarded_for=None):
    headers = {}
    if forwarded_for is not None:
        headers["X-Forwarded-For"] = forwarded_for
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers=headers,
    )


def test_consecutive_failures_trigger_lockout(auth_ready):
    client = auth_ready.app.test_client()
    ip = "203.0.113.10"

    for _ in range(3):
        resp = _login(client, "owner", "wrong-password", forwarded_for=ip)
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "用户名或密码错误"

    locked = _login(client, "owner", "wrong-password", forwarded_for=ip)
    assert locked.status_code == 429
    body = locked.get_json()
    assert body["locked"] is True
    assert body["retryAfter"] >= 1
    assert locked.headers.get("Retry-After")


def test_lockout_rejects_even_with_correct_password(auth_ready, monkeypatch):
    """While locked, correct password must not run verify / must not open a session."""
    client = auth_ready.app.test_client()
    ip = "203.0.113.20"

    for _ in range(3):
        assert _login(client, "owner", "nope", forwarded_for=ip).status_code == 401

    # If verify_password were called during lockout, this would raise
    def boom(*args, **kwargs):
        raise AssertionError("verify_password must not run while locked")

    import security

    monkeypatch.setattr(security, "verify_password", boom)
    monkeypatch.setattr(auth_ready, "verify_password", boom)

    locked = _login(client, "owner", "correct-horse", forwarded_for=ip)
    assert locked.status_code == 429
    assert locked.get_json()["locked"] is True

    # Still unauthenticated
    assert client.get("/api/questions").status_code == 401


def test_successful_login_clears_failure_count(auth_ready):
    client = auth_ready.app.test_client()
    ip = "203.0.113.30"

    # Two failures (under threshold of 3)
    assert _login(client, "owner", "bad1", forwarded_for=ip).status_code == 401
    assert _login(client, "owner", "bad2", forwarded_for=ip).status_code == 401

    ok = _login(client, "owner", "correct-horse", forwarded_for=ip)
    assert ok.status_code == 200
    assert ok.get_json()["ok"] is True

    # Counters cleared: three more failures should be required to lock again
    for _ in range(3):
        assert _login(client, "owner", "bad-again", forwarded_for=ip).status_code == 401

    assert _login(client, "owner", "bad-again", forwarded_for=ip).status_code == 429


def test_ip_and_username_buckets_are_independent(auth_ready):
    """
    IP bucket and username bucket are separate:
    - failures from IP-A on user owner lock IP-A + owner
    - a different IP can still try a different username without inheriting IP-A lock
    - username lock still applies when the same username is tried from IP-B
    """
    client_a = auth_ready.app.test_client()
    client_b = auth_ready.app.test_client()
    ip_a = "198.51.100.1"
    ip_b = "198.51.100.2"

    # Lock owner via IP-A (also fills user:owner bucket)
    for _ in range(3):
        assert _login(client_a, "owner", "wrong", forwarded_for=ip_a).status_code == 401
    assert _login(client_a, "owner", "wrong", forwarded_for=ip_a).status_code == 429

    # Same username from a fresh IP is still locked (username bucket)
    assert _login(client_b, "owner", "wrong", forwarded_for=ip_b).status_code == 429

    # Different username from IP-B is not locked by user:owner
    # (auth will 401 for bad password, not 429 — username "other" has no failures)
    other = _login(client_b, "other", "wrong", forwarded_for=ip_b)
    assert other.status_code == 401
    assert other.get_json().get("locked") is not True


def test_different_ips_do_not_share_ip_bucket(auth_ready):
    """IP-only: failures on IP-A do not consume IP-B's budget (until username locks)."""
    client = auth_ready.app.test_client()
    ip_a = "203.0.113.40"
    ip_b = "203.0.113.41"

    # Two failures on IP-A for a non-existent user (username bucket: user:ghost)
    assert _login(client, "ghost", "x", forwarded_for=ip_a).status_code == 401
    assert _login(client, "ghost", "x", forwarded_for=ip_a).status_code == 401

    # IP-B still has full budget for a different username
    assert _login(client, "someone-else", "x", forwarded_for=ip_b).status_code == 401
    assert _login(client, "someone-else", "x", forwarded_for=ip_b).status_code == 401
    # not locked yet (threshold 3)
    assert _login(client, "someone-else", "x", forwarded_for=ip_b).status_code == 401
    assert _login(client, "someone-else", "x", forwarded_for=ip_b).status_code == 429


def test_forwarded_for_is_used_as_client_ip(auth_ready):
    """ProxyFix: distinct X-Forwarded-For values must use distinct IP buckets."""
    client = auth_ready.app.test_client()

    for _ in range(3):
        assert _login(client, "u1", "bad", forwarded_for="203.0.113.50").status_code == 401
    assert _login(client, "u1", "bad", forwarded_for="203.0.113.50").status_code == 429

    # Different client IP (as seen via X-Forwarded-For) is not locked by IP bucket;
    # also uses different username so user bucket is free.
    fresh = _login(client, "u2", "bad", forwarded_for="203.0.113.51")
    assert fresh.status_code == 401


def test_lock_expires_and_allows_retry(auth_ready, monkeypatch):
    client = auth_ready.app.test_client()
    ip = "203.0.113.60"
    monkeypatch.setattr(auth_util, "LOGIN_LOCKOUT_SECONDS", 1)
    monkeypatch.setattr(auth_ready, "LOGIN_LOCKOUT_SECONDS", 1)

    for _ in range(3):
        assert _login(client, "owner", "bad", forwarded_for=ip).status_code == 401
    assert _login(client, "owner", "bad", forwarded_for=ip).status_code == 429

    time.sleep(1.1)

    # After lock window, correct password works and clears state
    ok = _login(client, "owner", "correct-horse", forwarded_for=ip)
    assert ok.status_code == 200
    assert ok.get_json()["ok"] is True
