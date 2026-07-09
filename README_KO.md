<div align="center">

# TOEFL Review

**직접 호스팅하는 TOEFL 오답 노트 — 붙여넣기 → 구조화 → 시험형 연습 → 약점 공략.**

어수선한 문제 텍스트를 검색·통계·반복 연습이 가능한 개인 문제 은행으로 만듭니다.

[English](./README.md) · [简体中文](./README_ZH.md) · [日本語](./README_JA.md) · [한국어](./README_KO.md)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](./docker-compose.yml)
[![SQLite](https://img.shields.io/badge/Storage-SQLite%20WAL-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)

</div>

---

## 왜 TOEFL Review인가?

오답 노트가 스크린샷·메모·반쯤 정리된 문서뿐이면, **다시 풀어야 할 때** 도움이 되지 않습니다.

**TOEFL Review**는 붙여넣은 시험 자료를 **구조화된 개인 문제 은행**으로 바꿉니다.

| 문제 | 이 앱의 대응 |
|------|----------------|
| PDF/메모 복사 형식이 깨짐 | 저장 전 미리보기·수정 |
| “나중에 복습”이 오지 않음 | 시험형 UI + 즉시 채점 |
| 아직 약한 문항을 모름 | 시도 수, 정오, 오답률, 최근 연습 시각 |
| 클라우드 앱에 데이터가 묶임 | 로컬 SQLite, 내 기기 |
| API 키가 설정 파일에 흩어짐 | DB에 암호화 저장, UI에서 설정 |

> **셀프호스팅**용: 프로세스 하나(또는 Compose 한 세트). 외부 DB 불필요. 개인 사용 시 계정 시스템 필수 아님.

---

## 기능

### 📥 스마트 가져오기

- 지문·문항·선택지·정답·해설을 그대로 붙여넣기(형식이 완벽하지 않아도 됨).
- **유형 지정** 또는 자동 인식(3종).
- **OpenAI 호환 Chat Completions** 엔드포인트로 LLM 구조화.
- Complete the Words / Build a Sentence 구조화 입력은 **로컬 결정적 파서** 지원(빈칸 날조 최소화).
- 흐름: **파싱 → 미리보기 수정 → 은행 저장**. 모호하면 **확인 필요** 표시.

### 📚 문제 라이브러리

- 유형 필터, 제목/지문/프롬프트 검색.
- 생성 시각·오답률·최근 연습 순 정렬.
- 문항별 통계, 연습/편집/삭제.
- 고오답률 문항 강조.

### ✍️ 시험형 연습

| 모드 | 동작 |
|------|------|
| **랜덤** | 임의의 문항 추출 |
| **오답만** | 틀린 적 있는 문항 우선 |
| **고오답률** | 정답률이 낮은 문항 우선 |

인터랙션:

- **독해 선택** — A/B/C/D 선택 후 제출, 해설 표시.
- **Build a Sentence** — 단어 은행 탭으로 빈칸 채우기. 고정 구는 템플릿에 유지.
- **Complete the Words** — 지문 속 빠진 글자 채우기.

모든 시도는 통계용으로 저장됩니다.

### ⚙️ 내 LLM 사용

**설정** 페이지에서 구성(소스 코드에 넣지 않음):

- API Key(`APP_SECRET` 기반 Fernet 암호화)
- Base URL / 전체 Chat Completions URL
- 모델 이름
- 선택적 커스텀 JSON 파라미터

OpenAI Chat Completions 호환 제공자 지원. 연결 테스트 가능. API Key는 평문으로 다시 표시되지 않습니다.

### 🔒 프라이버시 지향

- 문제·기록·설정 전부 **로컬 SQLite**(`data/`).
- 비밀값은 `secrets/` 또는 환경 변수(gitignore).
- LLM에는 가져오기 시 사용자가 보낸 내용만 전달.

---

## 지원 문항 유형

고전 독해 선택과 **2026 스타일** TOEFL 문장 구성/빈칸 유형:

| 유형 | 코드 | 설명 |
|------|------|------|
| 독해 선택 | `reading_choice` | 지문 + 문항 + A–D + 정답 + 해설 |
| Build a Sentence | `build_sentence` | 프롬프트, 빈칸·고정어 템플릿, 단어 은행, 정답 순서 |
| Complete the Words | `complete_words` | 빠진 글자 구간을 순서대로 보완 |

현재 UI 문구는 **주로 중국어**입니다.

---

## 아키텍처

```text
브라우저(정적 SPA)
   │  HTTP JSON
   ▼
Flask + Gunicorn
   ├── 가져오기 파싱(로컬 규칙 + 선택적 LLM)
   ├── 문항 CRUD + 채점
   ├── 설정(API Key 암호화)
   └── SQLite (WAL)  →  ./data/toefl_review.sqlite3
```

| 계층 | 기술 |
|------|------|
| 백엔드 | Python 3.12, Flask, Gunicorn |
| 프론트 | 순수 HTML / CSS / JS(빌드 없음) |
| 저장 | SQLite + WAL |
| 암호 | `cryptography` Fernet(`APP_SECRET` 파생) |
| 배포 | 선택적 Docker Compose. 기본 `127.0.0.1:3219` |

---

## 빠른 시작

### A — Docker Compose(권장)

```bash
git clone https://github.com/Kairitsu/toefl-review.git
cd toefl-review

mkdir -p secrets data
cp secrets/app.env.example secrets/app.env
# secrets/app.env에 충분히 긴 무작위 APP_SECRET 설정
# 기존 DB에서는 secret을 바꾸지 마세요(복호화 실패)

docker compose up -d --build
```

접속: **http://127.0.0.1:3219**

헬스 체크: `GET /api/health`

### B — 로컬 Python

```bash
git clone https://github.com/Kairitsu/toefl-review.git
cd toefl-review

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export APP_SECRET="$(openssl rand -hex 32)"
export DATA_DIR=data

flask --app app run --host 127.0.0.1 --port 8000

# 프로덕션 스타일:
# gunicorn --workers 2 --bind 127.0.0.1:8000 app:app
```

접속: **http://127.0.0.1:8000**

---

## 설정

| 변수 | 필수 | 설명 |
|------|------|------|
| `APP_SECRET` | **예** | API Key 암호화용 긴 난수. **기존 DB에서는 고정 필수**. |
| `DATA_DIR` | 아니오 | 데이터 디렉터리(기본 `data`, Compose는 `/app/data`). |

- `secrets/app.env.example` → Compose용 `secrets/app.env`로 복사  
- `.env.example` → 로컬 export 참고  

LLM Key / URL / 모델 등은 웹 **설정**에서 SQLite에 저장됩니다.

---

## 일상 워크플로

1. **설정** — Base URL, 모델, API Key 입력 후 연결 테스트.  
2. **가져오기** — 원문 붙여넣기 → 파싱 → 수정 → 저장.  
3. **라이브러리** — 검색·수정·단일 문항 연습.  
4. **연습** — 랜덤 / 오답만 / 고오답률.  
5. **백업** — SQLite 스냅샷.

```bash
./scripts/backup-db.sh
```

---

## 디렉터리 구조

```text
toefl-review/
├── app.py
├── static/          # index.html, app.js, styles.css
├── scripts/backup-db.sh
├── secrets/app.env.example
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── LICENSE          # AGPL-3.0
├── README.md        # English
├── README_ZH.md     # 简体中文
├── README_JA.md     # 日本語
└── README_KO.md     # 한국어
```

런타임(gitignore): `data/`, `secrets/app.env`, venv 등.

---

## API 요약

| 메서드 | 경로 | 용도 |
|--------|------|------|
| `GET` | `/api/health` | 헬스 |
| `GET` / `POST` | `/api/settings` | LLM 설정 |
| `POST` | `/api/settings/test` | 연결 테스트 |
| `POST` | `/api/import/parse` | 원문 → 초안 |
| `GET` / `POST` | `/api/questions` | 목록 / 생성 |
| `GET` / `PUT` / `DELETE` | `/api/questions/<id>` | 조회 / 수정 / 삭제 |
| `GET` | `/api/practice/next` | 다음 문항(`mode=random\|wrong\|high_error`) |
| `POST` | `/api/questions/<id>/attempts` | 제출·채점 |

---

## 보안 참고

- 기본은 **localhost** 바인딩(Compose: `127.0.0.1:3219`). 공개 시 리버스 프록시와 인증을 추가하세요.  
- `data/`, `secrets/app.env`, API 키, DB를 커밋하지 마세요.  
- `APP_SECRET`을 바꾸면 저장된 API Key를 복호화할 수 없습니다.  
- LLM 제공자에 보내는 내용에 주의하세요.

---

## 라이선스

**GNU Affero General Public License v3.0 (AGPL-3.0)**.

전문은 [`LICENSE`](./LICENSE)를 참고하세요.

요약: AGPL-3.0 아래에서 사용·학습·수정·배포할 수 있습니다. 수정본을 네트워크 서비스로 제공하면 해당 서비스 사용자에게 대응 소스코드를 제공해야 합니다. 상용 SaaS 재배포 전에 라이선스 전문을 읽으세요.

---

<div align="center">

스크린샷 폴더가 아니라, 정말로 다시 풀 수 있는 오답 노트를.

**[English](./README.md)** · **[简体中文](./README_ZH.md)** · **[日本語](./README_JA.md)** · **[한국어](./README_KO.md)**

</div>
