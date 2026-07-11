"""
Shared fixtures for toefl-review tests.

CRITICAL: app.py reads APP_SECRET / DATA_DIR at import time and calls init_db()
at module bottom. Environment variables MUST be set before the first `import app`.
Each integration test points DATA_DIR/DB_PATH at an isolated SQLite file so we
never touch data/toefl_review.sqlite3 (or other tests' databases).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Environment bootstrap — must run before any import of app
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Stable secret so Fernet / session keys are deterministic across tests
os.environ["APP_SECRET"] = "pytest-app-secret-for-toefl-review-do-not-use-in-prod"

# Session-level throwaway data dir so the import-time init_db() never hits
# the developer's real data/ tree.
_SESSION_DATA_DIR = tempfile.mkdtemp(prefix="toefl_review_pytest_session_")
os.environ["DATA_DIR"] = _SESSION_DATA_DIR

# Import only after env is ready
import app as app_module  # noqa: E402
import auth_util as auth_util_module  # noqa: E402
import db as db_module  # noqa: E402
import security as security_module  # noqa: E402


@pytest.fixture
def app_mod(tmp_path, monkeypatch):
    """Provide the app module with an isolated SQLite database per test."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "toefl_review.sqlite3"
    # Patch the module that get_db() actually reads (db.py), plus app re-exports
    for mod in (db_module, app_module):
        monkeypatch.setattr(mod, "DATA_DIR", data_dir)
        monkeypatch.setattr(mod, "DB_PATH", db_path)
    app_module.init_db()
    return app_module


@pytest.fixture
def client(app_mod):
    """Flask test client bound to an isolated database."""
    app_mod.app.config["TESTING"] = True
    return app_mod.app.test_client()


@pytest.fixture
def sample_reading_choice():
    return {
        "type": "reading_choice",
        "title": "Photosynthesis",
        "article": "Plants convert light energy into chemical energy through photosynthesis.",
        "prompt": "What do plants convert light energy into?",
        "explanation": "The passage states chemical energy.",
        "data": {
            "options": [
                {"key": "A", "text": "Heat energy"},
                {"key": "B", "text": "Chemical energy"},
                {"key": "C", "text": "Kinetic energy"},
                {"key": "D", "text": "Nuclear energy"},
            ],
            "correctAnswer": "B",
        },
    }


@pytest.fixture
def sample_build_sentence():
    return {
        "type": "build_sentence",
        "prompt": "What did Maria do yesterday?",
        "explanation": "Subject + past verb + fixed phrase + place.",
        "data": {
            "sentenceTemplate": "{{blank}} went to the {{blank}}.",
            "wordBank": ["Maria", "store", "John", "park"],
            "correctOrder": ["Maria", "store"],
            "completeSentence": "Maria went to the store.",
        },
    }


@pytest.fixture
def sample_complete_words():
    return {
        "type": "complete_words",
        "prompt": "Fill in the missing letters in the paragraph",
        "explanation": "civilization + systems",
        "data": {
            "passageText": "The ancient civiliza____ built complex sys____.",
            "blanks": [
                {
                    "id": "1",
                    "prefix": "civiliza",
                    "answer": "tion",
                    "fullWord": "civilization",
                    "blankLength": 4,
                },
                {
                    "id": "2",
                    "prefix": "sys",
                    "answer": "tems",
                    "fullWord": "systems",
                    "blankLength": 4,
                },
            ],
        },
    }
