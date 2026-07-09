# TOEFL Review

A small Flask-based TOEFL mistake review app with three question types:

- Reading multiple choice
- Writing sentence building
- Reading Complete the Words

## Local Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export APP_SECRET=replace-with-a-long-random-secret
export DATA_DIR=data
flask --app app run
```

For Docker Compose:

```bash
mkdir -p secrets data
cp secrets/app.env.example secrets/app.env
docker compose up -d --build
```

## Runtime Data

The app stores user questions, practice history, and LLM settings in SQLite under `data/`.
The real `APP_SECRET` lives in `secrets/app.env` for Docker Compose.

Do not commit `data/`, `secrets/app.env`, database files, API keys, local logs, or browser test artifacts.

LLM API Key, Base URL, model name, and custom parameters are configured from the app settings page and are stored in the local database, not in source code.
