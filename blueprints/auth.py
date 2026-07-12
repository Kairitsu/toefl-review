"""Auth status, login, logout."""
from __future__ import annotations

import hmac
import time

from flask import Blueprint, jsonify, request, session

from auth_util import (
    any_login_lock_remaining,
    auth_configured,
    clear_login_attempts,
    is_authed,
    login_attempt_keys,
    record_login_failure,
)
from db import get_db, get_setting
from parsing import as_clean_string
from security import verify_password

bp = Blueprint("auth", __name__)


@bp.get("/api/auth/status")
def auth_status():
    with get_db() as db:
        configured = auth_configured(db)
    return jsonify({
        "authRequired": configured,
        "authed": is_authed() if configured else True,
        "username": session.get("username") if is_authed() else None,
    })


@bp.post("/api/auth/login")
def auth_login():
    payload = request.get_json(force=True, silent=True) or {}
    username = as_clean_string(payload.get("username"))
    password = payload.get("password", "")
    if not isinstance(password, str):
        return jsonify({"error": "用户名或密码错误"}), 401

    ip_key, user_key = login_attempt_keys(username)
    throttle_keys = [ip_key] + ([user_key] if user_key else [])

    with get_db() as db:
        if not auth_configured(db):
            return jsonify({"error": "尚未配置登录认证"}), 400

        # Check IP + username lockouts before PBKDF2 (skip expensive verify while locked)
        remaining = any_login_lock_remaining(db, throttle_keys)
        if remaining > 0:
            retry_after = max(1, int(remaining + 0.999))
            response = jsonify(
                {
                    "error": "登录尝试过于频繁，请稍后再试",
                    "locked": True,
                    "retryAfter": retry_after,
                }
            )
            response.status_code = 429
            response.headers["Retry-After"] = str(retry_after)
            return response

        stored_user = get_setting(db, "auth_username", "")
        stored_hash = get_setting(db, "auth_password_hash", "")
        password_ok = hmac.compare_digest(username, stored_user) and verify_password(
            password, stored_hash
        )
        if not password_ok:
            # Count against both buckets so distributed IPs and single-IP multi-user
            # sprays are both limited.
            for key in throttle_keys:
                record_login_failure(db, key)
            # If this failure just tripped the lock, surface 429 next time; still 401 now
            # so attackers learn less about whether they hit the threshold this attempt.
            return jsonify({"error": "用户名或密码错误"}), 401

        for key in throttle_keys:
            clear_login_attempts(db, key)
        db.commit()

    session.permanent = True
    session["authed_at"] = time.time()
    session["username"] = username
    return jsonify({"ok": True, "username": username})


@bp.post("/api/auth/logout")
def auth_logout():
    session.clear()
    return jsonify({"ok": True})
