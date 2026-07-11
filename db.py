"""SQLite access and schema initialization."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DB_PATH = DATA_DIR / "toefl_review.sqlite3"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                article TEXT NOT NULL DEFAULT '',
                prompt TEXT NOT NULL DEFAULT '',
                explanation TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                data TEXT NOT NULL,
                needs_confirmation INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
                answer TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                detail TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS practice_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                total INTEGER NOT NULL,
                correct INTEGER NOT NULL,
                wrong INTEGER NOT NULL,
                accuracy REAL NOT NULL,
                items TEXT NOT NULL
            );

            -- Shared across gunicorn workers (must not live in process memory).
            -- identifier: "ip:<addr>" or "user:<normalized_username>"
            CREATE TABLE IF NOT EXISTS login_attempts (
                identifier TEXT PRIMARY KEY,
                fail_count INTEGER NOT NULL DEFAULT 0,
                last_failed_at REAL NOT NULL DEFAULT 0,
                locked_until REAL NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_questions_type ON questions(type);
            CREATE INDEX IF NOT EXISTS idx_questions_updated_at ON questions(updated_at);
            CREATE INDEX IF NOT EXISTS idx_attempts_question_id ON attempts(question_id);
            CREATE INDEX IF NOT EXISTS idx_attempts_created_at ON attempts(created_at);
            CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON practice_sessions(created_at);
            CREATE INDEX IF NOT EXISTS idx_login_attempts_locked_until ON login_attempts(locked_until);
            """
        )


def get_setting(db, key, default=None):
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(db, key, value):
    db.execute(
        """
        INSERT INTO settings(key, value) VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
