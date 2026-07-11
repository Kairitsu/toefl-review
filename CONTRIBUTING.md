# Contributing to TOEFL Review

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

export APP_SECRET="$(openssl rand -hex 32)"
export DATA_DIR=data

flask --app app run --host 127.0.0.1 --port 8000
```

Runtime deps only: `pip install -r requirements.txt`  
Dev/test deps (includes runtime): `pip install -r requirements-dev.txt`

## Running tests

The suite uses **pytest** only (no extra mock frameworks). Tests live under `tests/`.

```bash
# From the repo root, with the venv active:
pip install -r requirements-dev.txt
python -m pytest
# or quieter:
python -m pytest -q
```

### Directory layout

```text
tests/
├── conftest.py                 # Env bootstrap + isolated DB fixtures
├── test_template_utils.py      # Pure import/parse helpers
├── test_grade_attempt.py       # Grading for all three question types
├── test_validate_question.py   # Validation boundary cases
└── test_api.py                 # Flask test_client integration (CRUD + auth)
```

### Isolation rules (important)

`app.py` reads `APP_SECRET` and `DATA_DIR` at **import time** and calls `init_db()` at module load. The test harness therefore:

1. Sets `APP_SECRET` and a throwaway `DATA_DIR` **before** the first `import app` (see `tests/conftest.py`).
2. Points each integration test at its **own** SQLite file via `tmp_path` + monkeypatch of `DATA_DIR` / `DB_PATH`.

Never point tests at the real `data/toefl_review.sqlite3` — that would pollute local user data.

### CI

GitHub Actions workflow: [`.github/workflows/test.yml`](.github/workflows/test.yml)

- Triggers on push / pull request to `main` or `master`
- Installs `requirements.txt` + `requirements-dev.txt`
- Runs `python -m pytest -q`

## Guidelines

- Prefer small, focused PRs.
- Do not change business logic only to make a test green. If a test exposes unexpected behavior, document the actual behavior (or fix a real bug intentionally).
- Keep the stack as-is: Flask + sqlite3 (no ORM), vanilla static frontend (no build step), pytest for tests.
- Backend layout: `create_app()` in `app.py`, domain modules (`db`, `security`, `parsing`, `grading`, `llm`, …), and Flask blueprints under `blueprints/`.
- Frontend layout: native ES modules under `static/js/` with `data-action` event delegation (no inline `onclick`). **Do not introduce a bundler.** After the `onclick` → `data-action` migration, a later change can tighten CSP `script-src` by dropping `'unsafe-inline'`; that header change is intentionally not part of the module split.

## Architecture notes (refactor)

- Gunicorn still loads `app:app` (`create_app()` builds the instance).
- Tests may `from app import …`; `app.py` re-exports public helpers for compatibility.
- Isolated DB tests patch `db.DATA_DIR` / `db.DB_PATH` (see `tests/conftest.py`).
