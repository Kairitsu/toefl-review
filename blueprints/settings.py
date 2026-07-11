"""LLM and auth settings endpoints."""
from __future__ import annotations

import time

from flask import Blueprint, jsonify, request, session

from auth_util import auth_configured, is_authed
from db import get_db, get_setting, set_setting
from llm import (
    llm_settings_from_payload,
    load_llm_settings,
    parse_custom_params,
    test_llm_connection,
    validate_provider_url,
)
from parsing import as_clean_string
from security import encrypt_secret, hash_password

bp = Blueprint("settings", __name__)


@bp.get("/api/settings")
def get_settings():
    with get_db() as db:
        encrypted = get_setting(db, "api_key_encrypted", "")
        return jsonify(
            {
                "apiKeyConfigured": bool(encrypted),
                "baseUrl": get_setting(db, "base_url", ""),
                "model": get_setting(db, "model", ""),
                "customParams": get_setting(db, "custom_params", "{}"),
            }
        )


@bp.post("/api/settings")
def save_settings():
    payload = request.get_json(force=True, silent=True) or {}
    api_key = as_clean_string(payload.get("apiKey"))
    clear_api_key = bool(payload.get("clearApiKey"))
    base_url = as_clean_string(payload.get("baseUrl"))
    model = as_clean_string(payload.get("model"))
    custom_params = as_clean_string(payload.get("customParams") or "{}")
    errors = []
    if base_url:
        errors.extend(validate_provider_url(base_url))
    if custom_params:
        _, param_errors = parse_custom_params(custom_params)
        errors.extend(param_errors)
    if errors:
        return jsonify({"error": "设置校验失败", "details": errors}), 400
    with get_db() as db:
        if clear_api_key:
            db.execute("DELETE FROM settings WHERE key = ?", ("api_key_encrypted",))
        elif api_key:
            set_setting(db, "api_key_encrypted", encrypt_secret(api_key))
        set_setting(db, "base_url", base_url)
        set_setting(db, "model", model)
        set_setting(db, "custom_params", custom_params or "{}")
        db.commit()
    return jsonify({"ok": True, "apiKeyConfigured": bool(api_key) or load_llm_settings()["api_key_configured"]})


@bp.post("/api/settings/test")
def test_settings():
    payload = request.get_json(force=True, silent=True) or {}
    settings, errors = llm_settings_from_payload(payload, allow_saved_key=True)
    if errors:
        return jsonify({"error": "设置校验失败", "details": errors}), 400
    result, test_errors = test_llm_connection(settings)
    if test_errors:
        return jsonify({"error": "连接测试失败", "details": test_errors}), 502
    return jsonify({"ok": True, **result})


@bp.get("/api/settings/auth")
def get_auth_settings():
    with get_db() as db:
        username = get_setting(db, "auth_username", "")
        return jsonify({
            "configured": auth_configured(db),
            "username": username,
        })


@bp.post("/api/settings/auth")
def save_auth_settings():
    payload = request.get_json(force=True, silent=True) or {}
    username = as_clean_string(payload.get("username"))
    password = payload.get("password", "")
    clear_auth = bool(payload.get("clearAuth"))
    if not isinstance(password, str):
        password = ""
    errors = []
    if not clear_auth:
        if not username:
            errors.append("用户名不能为空")
        if not password:
            errors.append("密码不能为空")
    if errors:
        return jsonify({"error": "认证设置校验失败", "details": errors}), 400
    with get_db() as db:
        if clear_auth:
            db.execute("DELETE FROM settings WHERE key IN (?, ?)", ("auth_username", "auth_password_hash"))
            db.commit()
            session.clear()
            return jsonify({"ok": True, "configured": False})
        set_setting(db, "auth_username", username)
        set_setting(db, "auth_password_hash", hash_password(password))
        db.commit()
    session.permanent = True
    session["authed_at"] = time.time()
    session["username"] = username
    return jsonify({"ok": True, "configured": True, "username": username})
