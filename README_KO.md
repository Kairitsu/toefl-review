<div align="center">

# TOEFL Review

**흩어진 TOEFL 오답을 실제로 반복 연습하고, 다시 보고, 복습할 수 있는 개인 문제 은행으로 바꾸세요.**

가볍고 오픈 소스이며 직접 호스팅할 수 있는 TOEFL 오답 복습 시스템입니다.  
문제 구조화 가져오기, 시험형 연습, 즉시 채점, 학습 보고서, 연습 기록을 지원합니다.

[English](./README.md) · [简体中文](./README_ZH.md) · [日本語](./README_JA.md) · **한국어**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](./docker-compose.yml)
[![SQLite](https://img.shields.io/badge/Storage-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)

</div>

---

## TOEFL Review는 무엇을 하나요?

오답은 스크린샷, 채팅 메시지, Word 파일, 여러 앱의 메모에 흩어지기 쉽습니다.

저장되어 있어도 실제로 다시 풀어보는 경우는 드뭅니다.

TOEFL Review는 다음 복습 과정을 하나의 시스템으로 연결합니다.

> **문제 붙여넣기 → 문제 유형 선택 → 내용 구조화 → 미리보기 및 수정 → 개인 문제 은행에 저장 → 다시 연습 → 학습 보고서 확인 → 기록을 다시 보거나 같은 세션 재연습**

단순한 문제 보관함이 아니라, 장기적으로 누적하고 반복 복습하기 위한 개인 연습 시스템입니다.

---

## 주요 기능

### 구조화된 문제 가져오기

문제 유형마다 전용 입력 양식이 있어 모든 내용을 하나의 큰 텍스트 상자에 넣을 필요가 없습니다.

| 문제 유형 | 가져오기 항목 |
| --- | --- |
| 독해 선택형 | 제목, 지문, 질문, A–D 선택지, 정답, 해설 |
| Build a Sentence | 프롬프트, 문장 템플릿, 단어 은행, 정답 순서, 완성 문장, 해설 |
| Complete the Words | 밑줄 빈칸이 있는 지문, 정답 목록, 해설 |

독해 선택형과 일부 Build a Sentence 문제는 OpenAI Chat Completions 호환 LLM API를 통해 정리할 수 있습니다.

Complete the Words는 원문의 밑줄 위치를 기준으로 로컬 파싱을 우선해, LLM이 지문을 바꾸거나 빈칸을 임의로 추가하는 위험을 줄입니다.

파싱 결과는 즉시 저장되지 않습니다. 구조화된 모든 항목을 확인하고 수정한 뒤 문제 은행에 추가할 수 있습니다.

### 개인 문제 라이브러리

- 문제 유형 필터;
- 질문과 지문 검색;
- 생성 시각, 오답률, 최근 연습 시각 기준 정렬;
- 문제별 시도 수, 정답 수, 오답 수 확인;
- 개별 연습, 편집, 삭제;
- 반복 오답률이 높은 문제 확인;
- 원하는 문제만 선택해 연습 세션 구성.

문제를 삭제하면 해당 문제와 연결된 풀이 기록도 함께 삭제됩니다.

### 문제 유형별 연습 화면

#### 독해 선택형

지문과 질문을 나누어 표시하고 A, B, C, D 중 하나를 직접 선택합니다.

#### Build a Sentence

고정 문구는 원래 위치에 유지되며, 단어 은행의 어구를 클릭하거나 드래그해 해당 빈칸에 넣을 수 있습니다.

#### Complete the Words

빠진 글자 위치에 입력 칸이 직접 표시되고, 빠진 글자 수만큼 한 글자씩 입력합니다.

제출 후에는 정오, 내 답, 정답, 빈칸별 판정, 해설, 누적 통계가 즉시 표시됩니다.

### 연습 문제 선택

미리 정해진 문제 수 또는 사용자 지정 문제 수로 시작할 수 있습니다. 라이브러리에서 원하는 문제를 직접 골라 전용 연습 세션을 만들 수도 있습니다.

### 학습 보고서

한 세션이 끝나면 정답률만 보여주는 대신 전체 문제, 정답, 오답 필터, 원문제, 내 답, 정답, 선택지별 또는 빈칸별 결과, 해설을 포함한 상세 보고서를 생성합니다.

### 연습 기록

완료된 연습 세션은 자동 저장됩니다. 과거 세션의 전체 보고서를 다시 열거나 같은 문제 구성으로 세션 전체를 다시 풀 수 있습니다.

### 사용자가 준비하는 LLM API

설정 페이지에서 다음 항목을 입력할 수 있습니다.

- API Key;
- Base URL 또는 전체 요청 URL;
- 모델 이름;
- 선택적 사용자 지정 JSON 파라미터.

OpenAI Chat Completions 형식과 호환되는 서비스라면 일반적으로 연결할 수 있으며, 내장 연결 테스트도 제공합니다.

> 이 프로젝트에는 LLM 서비스나 무료 사용량이 포함되지 않습니다. 요금, 속도 제한, 데이터 처리 정책은 사용자가 선택한 제공자에 따릅니다.

### 로컬 저장과 선택적 로그인 보호

문제, 풀이 기록, 학습 보고서, 설정은 로컬 SQLite 데이터베이스에 저장됩니다.

```text
data/toefl_review.sqlite3
```

API Key는 `APP_SECRET`에서 파생한 Fernet 키로 암호화되며 설정 화면에 평문으로 다시 표시되지 않습니다.

설정 페이지에서 공용 사용자 이름과 비밀번호를 활성화할 수 있습니다. 다만 이는 개인 인스턴스 보호 기능이며 다중 사용자 계정 시스템은 아닙니다. 공개 배포 시에는 Caddy 또는 Nginx와 HTTPS를 함께 사용해야 합니다.

> 현재 웹 UI는 주로 중국어 간체로 작성되어 있습니다. 문서는 다국어이지만 앱 UI는 아직 완전히 국제화되지 않았습니다.

---

## 빠른 시작

Git, Docker, Docker Compose를 설치한 뒤 실행합니다.

```bash
git clone https://github.com/Kairitsu/toefl-review.git
cd toefl-review

mkdir -p secrets data
cp secrets/app.env.example secrets/app.env
```

무작위 비밀값을 생성합니다.

```bash
openssl rand -hex 32
```

`secrets/app.env`에 입력합니다.

```env
APP_SECRET=생성한_무작위_값을_여기에_입력
```

데이터가 생성된 뒤에는 `APP_SECRET`을 변경하지 마세요. 변경하면 저장된 API Key를 복호화할 수 없습니다.

서비스 시작:

```bash
docker compose up -d --build
```

접속 주소:

```text
http://127.0.0.1:3219
```

자주 쓰는 명령:

```bash
docker compose ps
docker compose logs -f app
docker compose down
```

---

## 서버에 배포하기

Compose는 기본적으로 `127.0.0.1:3219`에만 바인딩합니다. VPS에서는 Caddy 또는 Nginx로 도메인을 다음 주소에 리버스 프록시하세요.

```text
http://127.0.0.1:3219
```

도메인에 HTTPS를 활성화해야 합니다.

임시 접속에는 SSH 터널을 사용할 수 있습니다.

```bash
ssh -L 3219:127.0.0.1:3219 username@server-address
```

---

## 처음 사용하는 순서

1. 설정 페이지 열기;
2. LLM API Key, Base URL, 모델 이름 입력;
3. 연결 테스트 실행;
4. 필요하면 접근 사용자 이름과 비밀번호 설정;
5. 가져오기 페이지에서 문제 유형 선택;
6. 문제, 정답, 해설 입력 또는 붙여넣기;
7. 파싱 결과 확인 및 수정;
8. 문제 라이브러리에 저장;
9. 연습 시작.

---

## 업데이트, 백업, 복원

백업:

```bash
./scripts/backup-db.sh
```

백업은 `data/backups/`에 저장됩니다.

업데이트:

```bash
git pull
docker compose up -d --build
```

수동 백업:

```bash
docker compose down
cp -a data data-backup
docker compose up -d
```

복원할 때는 데이터베이스를 `data/toefl_review.sqlite3`로 되돌리고 원래의 `APP_SECRET`을 계속 사용하세요.

---

## Docker 없이 실행하기

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

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

실행 후 `http://127.0.0.1:8000`을 엽니다. 장기 운영에는 Docker 또는 Gunicorn을 권장합니다.

---

## 데이터와 개인정보

- 문제와 연습 기록은 사용자 SQLite에 저장;
- API Key는 암호화 후 저장;
- 저장된 전체 API Key는 브라우저에 다시 표시하지 않음;
- 사용자가 LLM 파싱을 실행할 때만 문제 내용을 설정한 제공자에게 전송;
- 제3자 클라우드로 자동 동기화하지 않음.

다음 항목을 Git에 커밋하지 마세요.

```text
data/
secrets/app.env
API Key
데이터베이스 파일
실제 로그인 정보
```

---

## 범위와 제한

현재 버전은 개인 셀프호스팅을 주목적으로 합니다. 다중 사용자 학습 플랫폼, TOEFL 문제 다운로드·수집 도구, LLM 사용량이 포함된 상용 서비스, ETS 공식 제품이 아닙니다.

---

<details>
<summary><strong>기술 구성</strong></summary>

```text
브라우저(순수 HTML / CSS / JavaScript)
        │ HTTP JSON
        ▼
Flask + Gunicorn
        ├── 가져오기 파싱(로컬 규칙 + 선택적 LLM)
        ├── 문제 관리 및 채점
        ├── 설정 및 선택적 접근 인증
        └── SQLite WAL → data/toefl_review.sqlite3
```

| 계층 | 기술 |
| --- | --- |
| 백엔드 | Python 3.12, Flask, Gunicorn |
| 프론트엔드 | 순수 HTML, CSS, JavaScript |
| 저장소 | SQLite, WAL 모드 |
| API Key 암호화 | `cryptography` Fernet |
| 비밀번호 | PBKDF2-SHA256 |
| 배포 | Docker Compose |
| 기본 주소 | `127.0.0.1:3219` |

</details>

---

## 자주 묻는 질문

### LLM API가 반드시 필요한가요?

문제 라이브러리, 연습, 보고서, 기록은 LLM 없이도 사용할 수 있습니다. Complete the Words는 주로 로컬 규칙으로 처리됩니다. 독해 선택형 자동 정리에는 일반적으로 OpenAI 호환 LLM이 필요합니다.

### 데이터가 프로젝트 작성자의 서버로 업로드되나요?

아닙니다. 이 프로젝트에는 작성자가 운영하는 중앙 서버가 없습니다. 외부 전송은 사용자가 설정한 LLM 파싱을 직접 실행한 경우에만 발생합니다.

### 휴대폰에서도 사용할 수 있나요?

가능합니다. 휴대폰에서 배포 주소에 접근할 수 있다면 반응형 브라우저 UI를 사용할 수 있습니다.

### 여러 사용자가 계정을 등록할 수 있나요?

불가능합니다. 내장 인증은 하나의 인스턴스를 하나의 공용 인증 정보로 보호하는 기능입니다.

---

## 기여

Issue와 Pull Request를 환영합니다. 개인 데이터와 비밀값을 커밋하지 말고, 변경 목적과 테스트 방법을 설명해 주세요.

---

## 라이선스

이 프로젝트는 [GNU Affero General Public License v3.0](./LICENSE)으로 배포됩니다.

수정 버전을 배포하거나 네트워크 서비스로 다른 사람에게 제공할 경우 AGPL-3.0의 소스 코드 공개 요건을 따라야 합니다.

---

<div align="center">

**오답을 단순히 “저장”하는 데서 끝내지 말고, 다시 풀어보세요.**

</div>
