<div align="center">

# TOEFL Review

**Self-hosted mistake bank for TOEFL practice — paste, parse, drill, improve.**

Import messy question text → structure it (LLM or local rules) → practice in an exam-style UI → track what you still get wrong.

[English](./README.md) · [简体中文](./README_ZH.md) · [日本語](./README_JA.md) · [한국어](./README_KO.md)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](./docker-compose.yml)
[![SQLite](https://img.shields.io/badge/Storage-SQLite%20WAL-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)

</div>

---

## Why TOEFL Review?

Most “wrong-answer notebooks” are screenshots, sticky notes, or half-sorted Word docs. When you need to **re-drill** a reading choice, a Build-a-Sentence item, or a Complete-the-Words passage, that pile does not help.

**TOEFL Review** turns pasted exam material into a **private, structured question bank** you can practice anytime:

| Pain | What this app does |
|------|--------------------|
| Messy copy-paste from PDFs / notes | Structured import with preview & edit before save |
| “I’ll review later” never happens | Exam-style practice with immediate grading |
| No idea which items are still weak | Stats: attempts, accuracy, error rate, last practice |
| Cloud flashcard apps lock your data | Local SQLite — your machine, your files |
| API keys scattered in config files | Encrypted API key in the DB; settings in the UI |

> Built for **self-hosting**: one process (or one Compose stack), no external database, no account system required for personal use.

---

## Features

### 📥 Smart import

- Paste raw stems, passages, options, answers, and explanations — format can be imperfect.
- **Type hint** or auto-detect among three supported types.
- **LLM structuring** via any OpenAI-compatible Chat Completions endpoint.
- **Deterministic local parsers** for structured Complete the Words / Build a Sentence input (no invented blanks).
- Preview → fix fields → **Save to bank**. Items can be flagged **needs confirmation** when answers are ambiguous.

### 📚 Question library

- Filter by type, search title / passage / prompt.
- Sort by created time, error rate, or last practice.
- Per-item stats and one-click practice / edit / delete.
- High-error items are visually highlighted.

### ✍️ Exam-style practice

Three practice modes:

| Mode | Behavior |
|------|----------|
| **Random** | Draw any question at random |
| **Wrong only** | Prefer items you have missed before |
| **High error rate** | Prefer items with the worst accuracy |

Interactive UIs:

- **Reading choice** — select A/B/C/D, submit, see explanation.
- **Build a Sentence** — tap word bank chunks into blanks; fixed template text stays in place.
- **Complete the Words** — letter-level blanks in the passage.

Every attempt is stored for stats and weak-item review.

### ⚙️ Bring your own LLM

Configure in the **Settings** page (not in source code):

- API Key (encrypted at rest with `APP_SECRET`)
- Base URL / full Chat Completions URL
- Model name
- Optional custom JSON parameters

Supports providers that speak the **OpenAI Chat Completions** protocol. Connection can be tested from the UI. The API key is never echoed back in plaintext.

### 🔒 Privacy-minded defaults

- All questions, attempts, and settings live in **local SQLite** under `data/`.
- Secrets stay in `secrets/` (Compose) or environment variables — gitignored.
- LLM only sees what you paste for import (and only when you trigger parse).

---

## Supported question types

Aligned with classic reading practice and **2026-style** TOEFL writing/reading item shapes:

| Type | Code | Description |
|------|------|-------------|
| Reading multiple choice | `reading_choice` | Passage + stem + A–D options + answer + analysis |
| Build a Sentence | `build_sentence` | Prompt, sentence template with blanks & fixed phrases, word bank, correct order |
| Complete the Words | `complete_words` | Passage with missing letter runs; fill missing suffixes in order |

---

## Architecture

```text
Browser (static SPA)
   │  HTTP JSON
   ▼
Flask + Gunicorn
   ├── Import parse (local rules + optional LLM)
   ├── Question CRUD + attempt grading
   ├── Settings (Fernet-encrypted API key)
   └── SQLite (WAL)  →  ./data/toefl_review.sqlite3
```

| Layer | Stack |
|-------|--------|
| Backend | Python 3.12, Flask, Gunicorn |
| Frontend | Vanilla HTML / CSS / JS (no build step) |
| Storage | SQLite + WAL |
| Crypto | `cryptography` Fernet derived from `APP_SECRET` |
| Deploy | Docker Compose (optional), host port `127.0.0.1:3219` by default |

---

## Quick start

### Option A — Docker Compose (recommended)

```bash
git clone https://github.com/Kairitsu/toefl-review.git
cd toefl-review

mkdir -p secrets data
cp secrets/app.env.example secrets/app.env
# Edit secrets/app.env and set a long random APP_SECRET
# Keep the same secret for the lifetime of an existing database.

docker compose up -d --build
```

Open: **http://127.0.0.1:3219**

Health check: `GET /api/health`

### Option B — Local Python

```bash
git clone https://github.com/Kairitsu/toefl-review.git
cd toefl-review

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export APP_SECRET="$(openssl rand -hex 32)"
export DATA_DIR=data

# Development server
flask --app app run --host 127.0.0.1 --port 8000

# Or production-style
# gunicorn --workers 2 --bind 127.0.0.1:8000 app:app
```

Open: **http://127.0.0.1:8000**

---

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `APP_SECRET` | **Yes** | Long random string. Used to encrypt the LLM API key. **Must stay stable** for an existing database or stored keys cannot be decrypted. |
| `DATA_DIR` | No | Data directory (default `data`; Compose uses `/app/data`). |

Example files:

- `secrets/app.env.example` → copy to `secrets/app.env` for Compose
- `.env.example` → reference for local exports

LLM **API Key / Base URL / model / custom params** are configured in the web **Settings** UI and stored in SQLite (key encrypted).

---

## Day-to-day workflow

1. **Settings** — set provider Base URL, model, and API key; run connection test.
2. **Import** — paste a raw question → parse (LLM or local) → preview/edit → save.
3. **Library** — browse, search, fix, or drill a single item.
4. **Practice** — pick Random / Wrong / High error rate and grind until stats improve.
5. **Backup** — snapshot SQLite when you care about your bank.

```bash
# Offline backup via Docker (writes under data/backups/)
./scripts/backup-db.sh
```

---

## Project layout

```text
toefl-review/
├── app.py                 # Flask API, import parsers, grading, SQLite
├── static/
│   ├── index.html         # Shell page
│   ├── app.js             # SPA views: import / library / practice / settings
│   └── styles.css         # Exam-style UI
├── scripts/
│   └── backup-db.sh       # SQLite online backup inside the app container
├── secrets/
│   └── app.env.example    # APP_SECRET template (do not commit real secrets)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── LICENSE                # AGPL-3.0
├── README.md              # English
├── README_ZH.md           # 简体中文
├── README_JA.md           # 日本語
└── README_KO.md           # 한국어
```

Runtime (gitignored): `data/`, `secrets/app.env`, virtualenv, browser test artifacts.

---

## API sketch

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/health` | Liveness |
| `GET` / `POST` | `/api/settings` | Read / save LLM settings |
| `POST` | `/api/settings/test` | Test provider connectivity |
| `POST` | `/api/import/parse` | Parse raw text into a draft question |
| `GET` / `POST` | `/api/questions` | List / create |
| `GET` / `PUT` / `DELETE` | `/api/questions/<id>` | Read / update / delete |
| `GET` | `/api/practice/next` | Next item (`mode=random\|wrong\|high_error`) |
| `POST` | `/api/questions/<id>/attempts` | Submit answer & grade |

---

## Security notes

- Prefer binding to **localhost** (Compose already maps `127.0.0.1:3219`). Put a reverse proxy + auth in front if you expose it on a network.
- Never commit `data/`, `secrets/app.env`, API keys, or database files.
- Changing `APP_SECRET` after keys are stored will break decryption of the saved API key.
- Treat LLM providers as third parties: only paste content you are willing to send to that provider.

---

## Tech choices (short)

- **No frontend build** — easy to read, fork, and self-host on a small VPS.
- **SQLite WAL** — zero ops for a personal mistake bank.
- **OpenAI-compatible only** — one HTTP path, many providers.
- **Local parse first** where possible for Complete the Words so blanks stay faithful to the source text.

---

## Roadmap ideas (community welcome)

- Spaced-repetition scheduling beyond error-rate modes  
- Batch import / export (JSON)  
- Tags & custom collections  
- Multi-user auth for shared family/class instances  
- Official UI i18n (current UI copy is primarily Chinese)

---

## Contributing

Issues and pull requests are welcome. Please:

1. Keep secrets and personal `data/` out of commits.
2. Prefer small, focused changes.
3. Describe how you tested (local Flask and/or Docker Compose).

---

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

See the full text in [`LICENSE`](./LICENSE).

**In short:** you may use, study, modify, and share this software under AGPL-3.0. If you run a modified version as a network service, you must offer the corresponding source to users of that service. Network-use source obligations are a core part of AGPL — please read the license before commercial SaaS redistribution.

---

<div align="center">

Made for TOEFL learners who keep a real mistake bank — not a folder of screenshots.

**[English](./README.md)** · **[简体中文](./README_ZH.md)** · **[日本語](./README_JA.md)** · **[한국어](./README_KO.md)**

</div>
