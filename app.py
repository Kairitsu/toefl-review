"""
TOEFL Review Flask application entrypoint.

Use `create_app()` for the app factory. Gunicorn continues to load `app:app`.
Module-level re-exports keep existing tests (`from app import …`) working.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

# ---------------------------------------------------------------------------
# Re-exports for tests and external callers (behavior-preserving refactor)
# ---------------------------------------------------------------------------
from auth_util import (  # noqa: F401
    AUTH_EXEMPT_EXACT,
    LOGIN_LOCKOUT_SECONDS,
    LOGIN_MAX_FAILURES,
    any_login_lock_remaining,
    auth_configured,
    clear_login_attempts,
    client_ip,
    is_authed,
    login_attempt_keys,
    login_lock_remaining,
    record_login_failure,
)
from db import DATA_DIR, DB_PATH, get_db, get_setting, init_db, now_iso, set_setting  # noqa: F401
from grading import grade_attempt, validate_question  # noqa: F401
from llm import (  # noqa: F401
    call_llm,
    endpoint_from_base,
    llm_settings_from_payload,
    load_llm_settings,
    parse_custom_params,
    parse_with_llm,
    test_llm_connection,
    validate_provider_url,
    validate_resolved_host,
)
from parsing import (  # noqa: F401
    ALLOWED_TYPES,
    MAX_RAW_IMPORT_CHARS,
    TYPE_LABELS,
    count_template_blanks,
    extract_json_object,
    match_answer_to_letter,
    match_answers_to_underscore_blanks,
    merge_build_sentence_draft,
    merge_complete_words_draft,
    merge_reading_choice_draft,
    normalize_build_data,
    normalize_question,
    normalize_sentence_template,
    parse_options_text,
    parse_structured_reading_choice,
    parse_template_segments,
    render_sentence_from_template,
    scan_underscore_blanks,
)
from security import (  # noqa: F401
    app_fernet,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    redact,
    verify_password,
)

from import_pipeline import parse_import  # noqa: F401

from blueprints.auth import bp as auth_bp
from blueprints.import_api import bp as import_bp
from blueprints.practice import bp as practice_bp
from blueprints.questions import bp as questions_bp
from blueprints.settings import bp as settings_bp


def create_app():
    """Application factory: registers blueprints, security hooks, and DB init."""
    application = Flask(__name__, static_folder="static")
    application.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

    app_secret = os.environ.get("APP_SECRET", "")
    application.secret_key = (
        hashlib.sha256(app_secret.encode("utf-8")).hexdigest()
        if app_secret
        else secrets.token_hex(32)
    )
    application.permanent_session_lifetime = timedelta(days=7)

    # README deploys behind a reverse proxy (Caddy/Nginx) on 127.0.0.1. ProxyFix
    # rewrites REMOTE_ADDR from X-Forwarded-For so login throttle keys use the real
    # client IP, not the proxy's. TRUST_PROXY_COUNT=0 when clients hit the app
    # directly (no reverse proxy) so X-Forwarded-For cannot be spoofed.
    try:
        trust_proxy_count = max(0, int(os.environ.get("TRUST_PROXY_COUNT", "1") or "0"))
    except ValueError:
        trust_proxy_count = 1
    if trust_proxy_count > 0:
        application.wsgi_app = ProxyFix(
            application.wsgi_app,
            x_for=trust_proxy_count,
            x_proto=trust_proxy_count,
            x_host=trust_proxy_count,
        )

    application.register_blueprint(auth_bp)
    application.register_blueprint(settings_bp)
    application.register_blueprint(import_bp)
    application.register_blueprint(questions_bp)
    application.register_blueprint(practice_bp)

    @application.before_request
    def require_auth():
        from flask import request

        path = request.path
        # 静态资源、首页、健康检查、认证端点一律放行
        if (
            path == "/"
            or path.startswith("/static/")
            or path in AUTH_EXEMPT_EXACT
            or path.startswith("/api/auth/")
        ):
            return None
        with get_db() as db:
            if not auth_configured(db):
                return None  # 未配置凭据，保持开放
        if is_authed():
            return None
        return jsonify({"error": "未登录或会话已过期", "authRequired": True}), 401

    @application.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        # CSP: frontend uses ES modules + data-action delegation (no inline onclick).
        # style-src still needs 'unsafe-inline' for remaining style="" attributes.
        # script-src keeps 'unsafe-inline' for now; a follow-up can drop it after a
        # full pass confirms no residual inline handlers. connect-src is 'self' only
        # (LLM calls go through Flask). img-src allows data: for the empty favicon.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'"
        )
        return response

    @application.errorhandler(413)
    def too_large(_):
        return jsonify({"error": "请求体过大", "details": ["请求体过大"]}), 413

    @application.errorhandler(404)
    def not_found(_):
        return jsonify({"error": "未找到", "details": ["请求的资源不存在"]}), 404

    @application.errorhandler(405)
    def method_not_allowed(_):
        return jsonify({"error": "方法不允许", "details": ["HTTP 方法不被允许"]}), 405

    @application.errorhandler(500)
    def internal_error(_):
        return jsonify(
            {
                "error": "服务器内部错误",
                "details": ["服务器解析失败，请查看服务日志"],
            }
        ), 500

    @application.errorhandler(Exception)
    def handle_error(exc):
        # Always JSON — never Flask's default HTML error page.
        import logging
        import traceback

        status = getattr(exc, "code", None)
        if status is None:
            status = 500
        try:
            status = int(status)
        except (TypeError, ValueError):
            status = 500
        if status < 400 or status > 599:
            status = 500
        if status >= 500:
            logging.getLogger(__name__).error(
                "unhandled exception:\n%s", traceback.format_exc()
            )
            message = "服务器内部错误"
            details = ["服务器解析失败，请查看服务日志"]
        else:
            message = redact(str(exc) or "请求失败")
            details = [message]
        return jsonify({"error": message, "details": details}), status

    @application.get("/")
    def index():
        return send_from_directory(application.static_folder, "index.html")

    @application.get("/static/<path:path>")
    def static_files(path):
        return send_from_directory(application.static_folder, path)

    @application.get("/api/health")
    def health():
        import time

        return jsonify({"ok": True, "time": int(time.time())})

    init_db()
    return application


app = create_app()
