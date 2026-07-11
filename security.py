"""Secrets, password hashing, and log redaction."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets

from cryptography.fernet import Fernet, InvalidToken


def app_fernet():
    secret = os.environ.get("APP_SECRET", "")
    if not secret:
        raise RuntimeError("APP_SECRET is not configured")
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value):
    if not value:
        return ""
    return app_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value):
    if not value:
        return ""
    try:
        return app_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Stored API key cannot be decrypted with the current APP_SECRET") from exc


def hash_password(password):
    salt = secrets.token_hex(16)
    iterations = 200000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password, stored):
    try:
        algo, iters_str, salt, expected_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iters_str)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
        return hmac.compare_digest(digest.hex(), expected_hex)
    except (ValueError, AttributeError):
        return False



def redact(text, secrets=None):
    value = str(text or "")
    for secret in secrets or []:
        if secret and len(secret) >= 4:
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", value)
    value = re.sub(
        r"(?i)(api[_-]?key|authorization|access[_-]?token|token|secret)(['\"]?\s*[:=]\s*['\"]?)[^'\"&\s,}]+",
        r"\1\2[REDACTED]",
        value,
    )
    return value[:900]
