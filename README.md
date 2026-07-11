<div align="center">

# TOEFL Review

**Turn scattered TOEFL mistakes into a private question bank you can actually practice, revisit, and review.**

A lightweight, open-source, self-hosted TOEFL mistake-review system.  
It supports structured imports, exam-style practice, instant grading, study reports, and practice history.

**English** · [简体中文](./README_ZH.md) · [日本語](./README_JA.md) · [한국어](./README_KO.md)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](./docker-compose.yml)
[![SQLite](https://img.shields.io/badge/Storage-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)

</div>

---

## What does TOEFL Review do?

Mistakes often end up as screenshots, chat messages, Word files, or notes scattered across different apps.

They may be “saved,” but they are rarely practiced again.

TOEFL Review provides a complete review workflow:

> **Paste a question → Choose the type → Structure the content → Preview and correct → Save to your private bank → Practice again → Read the study report → Review history or redo the session**

It is not merely a place to store questions. It is a personal practice system designed for long-term accumulation and repeated review.

---

## Main features

### Structured question import

Each question type has its own input form, so you do not need to force every field into one large text box.

Currently supported:

| Question type | Import fields |
| --- | --- |
| Reading multiple choice | Title, passage, question, A–D options, correct answer, explanation |
| Build a Sentence | Prompt, sentence template, word bank, correct order, complete sentence, explanation |
| Complete the Words | Passage with underscore blanks, answer list, explanation |

Reading multiple-choice questions and some Build a Sentence questions can be organized through any LLM endpoint compatible with the OpenAI Chat Completions protocol.

Complete the Words questions are primarily parsed locally from underscore positions in the original passage. This reduces the risk of an LLM rewriting the passage or inventing new blanks.

Parsed content is not saved immediately. You can review and edit every structured field before adding the question to your bank.

### Private question library

Every saved question is stored in the local question library.

You can:

- Filter by question type;
- Search prompts, passages, and other content;
- Sort by creation time, error rate, or most recent practice;
- View attempts, correct answers, and incorrect answers for each question;
- Practice, edit, or delete an individual question;
- Spot questions with a high repeated-error rate;
- Select specific questions and combine them into a practice session.

Deleting a question also deletes the attempt records associated with that question.

### Practice interfaces designed for each question type

#### Reading multiple choice

The passage and question are displayed in separate areas. Select A, B, C, or D directly.

#### Build a Sentence

Fixed text stays in its original position. Word-bank chunks can be clicked or dragged into the matching blanks.

#### Complete the Words

Letter cells appear directly where letters are missing in the passage, with one cell for each missing letter.

After every submission, the app immediately shows:

- Whether the answer is correct;
- Your answer;
- The correct answer;
- Per-option or per-blank feedback;
- The explanation;
- Cumulative statistics for that question.

### Choose the questions for each session

Start with a preset number of questions or enter a custom amount. You can also open the library, manually select specific questions, and create a focused practice session.

During practice, you can move backward and forward, retry the current question, or exit early.

### Complete study reports

At the end of a session, TOEFL Review generates a full study report instead of showing only an accuracy percentage.

The report includes total questions, correct and incorrect totals, accuracy, filters for all/correct/incorrect questions, the original question, your answer, the correct answer, per-option or per-blank results, and the explanation.

### Practice history

Each completed practice session is saved automatically. Open any historical session to view its full report again, or redo the entire session with the same questions.

### Bring your own LLM

TOEFL Review is not tied to a particular model or provider. The Settings page accepts:

- API Key;
- Base URL or full request URL;
- Model name;
- Optional custom JSON parameters.

Providers that implement the OpenAI Chat Completions request format will generally work. A built-in connection test lets you verify the URL, model, and API Key before importing questions.

> The project does not include an LLM service or usage quota. Pricing, rate limits, and data-processing policies are determined by your chosen provider.

### Local storage and optional login protection

Questions, attempts, practice reports, and settings are stored in a local SQLite database:

```text
data/toefl_review.sqlite3
```

The LLM API Key is encrypted with Fernet using a key derived from `APP_SECRET`. It is never displayed back in plaintext on the Settings page.

You can also enable access authentication in Settings. Once enabled, the instance requires a shared username and password.

Important limitations:

- This protects one personal instance; it is not a multi-user account system;
- The built-in login does not replace HTTPS;
- Public deployments should still use a reverse proxy such as Caddy or Nginx with HTTPS enabled.

> The current web interface is primarily written in Simplified Chinese. The documentation is multilingual, but the application UI has not yet been fully internationalized.

---

## Quick start

### Deploy with Docker Compose

Install Git, Docker, and Docker Compose, then run:

```bash
git clone https://github.com/Kairitsu/toefl-review.git
cd toefl-review

mkdir -p secrets data
cp secrets/app.env.example secrets/app.env
```

Generate a random secret:

```bash
openssl rand -hex 32
```

Place it in `secrets/app.env`:

```env
APP_SECRET=replace-this-with-the-generated-random-value
```

Keep `APP_SECRET` stable after data has been created. Changing it prevents the app from decrypting an API Key already stored in the database.

Start the service:

```bash
docker compose up -d --build
```

Open:

```text
http://127.0.0.1:3219
```

Useful commands:

```bash
docker compose ps
docker compose logs -f app
docker compose down
```

---

## Deploying on a server

Docker Compose binds the service to `127.0.0.1:3219` by default, preventing direct public exposure.

For a VPS or cloud server, use Caddy or Nginx to reverse proxy your domain to:

```text
http://127.0.0.1:3219
```

Enable HTTPS for the domain.

For temporary access, create an SSH tunnel:

```bash
ssh -L 3219:127.0.0.1:3219 username@server-address
```

Then open `http://127.0.0.1:3219` on your own computer.

---

## First-time setup

1. Open Settings.
2. Enter the LLM API Key, Base URL, and model name.
3. Run the connection test.
4. Optionally configure an access username and password.
5. Open Import and choose the question type.
6. Enter or paste the question, answer, and explanation.
7. Parse the content and review the preview.
8. Save the question to the library.
9. Open Practice and begin reviewing.

---

## Updating, backup, and restore

Back up the database before updating:

```bash
./scripts/backup-db.sh
```

Backups are written to `data/backups/`.

Update and rebuild:

```bash
git pull
docker compose up -d --build
```

For a manual backup, stop the containers and copy the entire `data` directory:

```bash
docker compose down
cp -a data data-backup
docker compose up -d
```

To restore, stop the service and restore the database as `data/toefl_review.sqlite3`, then start it again. Continue using the original `APP_SECRET`.

---

## Running without Docker

```bash
git clone https://github.com/Kairitsu/toefl-review.git
cd toefl-review

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export APP_SECRET="$(openssl rand -hex 32)"
export DATA_DIR="data"

flask --app app run --host 127.0.0.1 --port 8000
```

On Windows PowerShell, activate the virtual environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then open `http://127.0.0.1:8000`.

For long-running deployments, use the included Docker configuration or Gunicorn rather than Flask's development server.

---

## Data and privacy

- Questions and practice records stay in your SQLite database;
- The API Key is encrypted before being stored;
- The browser does not display the complete saved API Key again;
- Question content is sent to an LLM provider only when you explicitly run LLM parsing;
- The project does not automatically synchronize your question bank to a third-party cloud service.

Never commit:

```text
data/
secrets/app.env
API keys
Database files
Real login credentials
```

---

## Scope and limitations

The current version is designed primarily for personal self-hosting. It is not a multi-user learning platform, a TOEFL question downloader or scraper, an official ETS product, or a commercial service with included LLM usage.

---

<details>
<summary><strong>Technical architecture</strong></summary>

```text
Browser (vanilla HTML / CSS / JavaScript)
        │ HTTP JSON
        ▼
Flask + Gunicorn
        ├── Import parsing (local rules + optional LLM)
        ├── Question CRUD and grading
        ├── Settings and optional authentication
        └── SQLite WAL → data/toefl_review.sqlite3
```

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12, Flask, Gunicorn |
| Frontend | Vanilla HTML, CSS, and JavaScript |
| Storage | SQLite in WAL mode |
| API-key encryption | `cryptography` Fernet |
| Password hashing | PBKDF2-SHA256 |
| Deployment | Docker Compose |
| Default address | `127.0.0.1:3219` |

The frontend has no Node.js dependency and requires no build step.

</details>

<details>
<summary><strong>Project structure</strong></summary>

```text
toefl-review/
├── app.py
├── static/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── scripts/
│   └── backup-db.sh
├── secrets/
│   └── app.env.example
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── LICENSE
├── README.md
├── README_ZH.md
├── README_JA.md
└── README_KO.md
```

</details>

---

## Frequently asked questions

### Is an LLM API required?

The library, practice system, reports, and history do not depend on an LLM. Complete the Words is primarily handled by local rules, and well-structured Build a Sentence input may also be recognized locally. Automatic organization of reading multiple-choice content generally requires an OpenAI-compatible LLM endpoint.

### Is data uploaded to the author's server?

No. The project has no central server operated by the author. Data remains in your own SQLite database. Content is sent externally only when you invoke your configured LLM provider.

### Can I use it on a phone?

Yes. The interface includes responsive layouts for narrow screens, provided the phone can reach your deployment address.

### Can multiple users register accounts?

No. The built-in authentication protects one instance with one shared credential set. It does not provide registration, account isolation, or separate user libraries.

---

## Contributing

Issues and pull requests are welcome. Keep personal data and secrets out of commits, explain what the change solves, and note how it was tested.

---

## License

This project is licensed under the [GNU Affero General Public License v3.0](./LICENSE).

You may use, study, modify, and share the project. If you distribute a modified version or provide it to others as a network service, follow the source-code disclosure requirements of AGPL-3.0.

---

<div align="center">

**Do not let a mistake remain merely “saved.” Practice it again.**

</div>
