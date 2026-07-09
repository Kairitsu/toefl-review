<div align="center">

# TOEFL Review

**自分でホストする TOEFL 間違いノート — 貼り付け → 構造化 → 試験風ドリル → 弱点克服。**

雑な問題テキストを、検索・統計・再演習できるプライベート問題バンクに変えます。

[English](./README.md) · [简体中文](./README_ZH.md) · [日本語](./README_JA.md) · [한국어](./README_KO.md)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](./docker-compose.yml)
[![SQLite](https://img.shields.io/badge/Storage-SQLite%20WAL-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)

</div>

---

## なぜ TOEFL Review か？

間違いノートがスクリーンショットやメモの山だと、「もう一度解く」ときに役に立ちません。

**TOEFL Review** は、貼り付けた試験素材を**構造化された個人用問題庫**にします。

| 課題 | このアプリの対応 |
|------|------------------|
| PDF / メモのコピペが崩れる | 保存前にプレビューして修正 |
| 「後で復習」が永遠に来ない | 試験風 UI で即時採点 |
| まだ弱い問題がわからない | 試行回数・正誤・誤答率・最終練習時刻 |
| クラウド教材にデータが縛られる | ローカル SQLite、自分のマシン上 |
| API キーが設定ファイルに散らばる | DB に暗号化保存、UI から設定 |

> **セルフホスト向け**：1 プロセス（または 1 つの Compose）。外部 DB 不要。個人利用ならログイン必須ではありません。

---

## 機能

### 📥 スマート取り込み

- 設問・本文・選択肢・解答・解説をそのまま貼り付け（体裁は完璧でなくてよい）。
- **題型指定**または自動判定（3 種類）。
- **OpenAI 互換 Chat Completions** エンドポイントで LLM 構造化。
- Complete the Words / Build a Sentence の構造化入力は**ローカル決定論パーサ**も利用（空欄の捏造を避ける）。
- 流れ：**解析 → プレビュー修正 → バンクへ保存**。曖昧な場合は **要確認** フラグ。

### 📚 問題ライブラリ

- タイプ絞り込み、タイトル / 本文 / プロンプト検索。
- 作成日時・誤答率・最終練習でソート。
- 統計表示、練習 / 編集 / 削除。
- 高誤答率の問題を強調表示。

### ✍️ 試験風練習

| モード | 内容 |
|--------|------|
| **ランダム** | 任意の問題を抽選 |
| **誤答のみ** | 過去に間違えた問題を優先 |
| **高誤答率** | 正答率が悪い問題を優先 |

インタラクション：

- **読解選択** — A/B/C/D を選んで提出、解説表示。
- **Build a Sentence** — 語彙バンクをタップして空欄へ。固定フレーズはテンプレに残る。
- **Complete the Words** — 本文中の欠けた文字を埋める。

すべての解答は統計用に保存されます。

### ⚙️ 自分の LLM を使う

**設定**画面で構成（ソースコードには書かない）：

- API Key（`APP_SECRET` 由来の Fernet で暗号化）
- Base URL / 完全な Chat Completions URL
- モデル名
- 任意のカスタム JSON パラメータ

OpenAI Chat Completions 互換プロバイダに対応。接続テスト可能。API Key は平文で再表示しません。

### 🔒 プライバシー寄り

- 問題・履歴・設定はすべて **ローカル SQLite**（`data/`）。
- 秘密情報は `secrets/` または環境変数（gitignore 済み）。
- LLM には、取り込み時にあなたが送った内容だけが渡ります。

---

## 対応問題タイプ

定番の読解選択に加え、**2026 年スタイル**の TOEFL 造句 / 穴埋めにも対応：

| タイプ | コード | 説明 |
|--------|--------|------|
| 読解選択 | `reading_choice` | 本文 + 設問 + A–D + 正解 + 解説 |
| Build a Sentence | `build_sentence` | プロンプト、空欄と固定語を含むテンプレ、語彙バンク、正解順 |
| Complete the Words | `complete_words` | 欠けた文字列を順に補完 |

UI 文言は現状**主に中国語**です。

---

## アーキテクチャ

```text
ブラウザ（静的 SPA）
   │  HTTP JSON
   ▼
Flask + Gunicorn
   ├── 取り込み解析（ローカル規則 + 任意 LLM）
   ├── 問題 CRUD + 採点
   ├── 設定（API Key 暗号化）
   └── SQLite (WAL)  →  ./data/toefl_review.sqlite3
```

| 層 | 技術 |
|----|------|
| バックエンド | Python 3.12, Flask, Gunicorn |
| フロント | 素の HTML / CSS / JS（ビルド不要） |
| 保存 | SQLite + WAL |
| 暗号 | `cryptography` Fernet（`APP_SECRET` から派生） |
| デプロイ | 任意で Docker Compose。既定は `127.0.0.1:3219` |

---

## クイックスタート

### A — Docker Compose（推奨）

```bash
git clone https://github.com/Kairitsu/toefl-review.git
cd toefl-review

mkdir -p secrets data
cp secrets/app.env.example secrets/app.env
# secrets/app.env に十分長いランダム APP_SECRET を設定
# 既存 DB では secret を変えないこと（暗号化キーが壊れます）

docker compose up -d --build
```

URL：**http://127.0.0.1:3219**

ヘルスチェック：`GET /api/health`

### B — ローカル Python

```bash
git clone https://github.com/Kairitsu/toefl-review.git
cd toefl-review

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export APP_SECRET="$(openssl rand -hex 32)"
export DATA_DIR=data

flask --app app run --host 127.0.0.1 --port 8000

# 本番向け:
# gunicorn --workers 2 --bind 127.0.0.1:8000 app:app
```

URL：**http://127.0.0.1:8000**

---

## 設定

| 変数 | 必須 | 説明 |
|------|------|------|
| `APP_SECRET` | **はい** | API Key 暗号化用の長い乱数。**既存 DB では固定必須**。 |
| `DATA_DIR` | いいえ | データディレクトリ（既定 `data`、Compose は `/app/data`）。 |

- `secrets/app.env.example` → Compose 用に `secrets/app.env` へコピー  
- `.env.example` → ローカル export の参考  

LLM の Key / URL / モデル等は Web の**設定**から SQLite に保存されます。

---

## 日常の流れ

1. **設定** — Base URL・モデル・API Key を入れ、接続テスト。  
2. **取り込み** — 原文貼付 → 解析 → 修正 → 保存。  
3. **ライブラリ** — 検索・修正・単問練習。  
4. **練習** — ランダム / 誤答のみ / 高誤答率。  
5. **バックアップ** — SQLite を定期スナップショット。

```bash
./scripts/backup-db.sh
```

---

## ディレクトリ構成

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

ランタイム（gitignore）：`data/`、`secrets/app.env`、venv など。

---

## API 概要

| メソッド | パス | 用途 |
|----------|------|------|
| `GET` | `/api/health` | 稼働確認 |
| `GET` / `POST` | `/api/settings` | LLM 設定 |
| `POST` | `/api/settings/test` | 接続テスト |
| `POST` | `/api/import/parse` | 原文 → 下書き |
| `GET` / `POST` | `/api/questions` | 一覧 / 作成 |
| `GET` / `PUT` / `DELETE` | `/api/questions/<id>` | 取得 / 更新 / 削除 |
| `GET` | `/api/practice/next` | 次問（`mode=random\|wrong\|high_error`） |
| `POST` | `/api/questions/<id>/attempts` | 提出・採点 |

---

## セキュリティ

- 既定は **localhost** バインド（Compose：`127.0.0.1:3219`）。公開する場合はリバースプロキシと認証を。  
- `data/`、`secrets/app.env`、API キー、DB をコミットしない。  
- `APP_SECRET` 変更後は保存済み API Key を復号できなくなる。  
- LLM プロバイダへ送る内容に注意。

---

## ライセンス

**GNU Affero General Public License v3.0（AGPL-3.0）**。

全文は [`LICENSE`](./LICENSE) を参照。

要約：AGPL-3.0 の下で利用・改変・再配布が可能です。改変版をネットワークサービスとして提供する場合、その利用者に対応するソースコードを提供する義務があります。SaaS での再配布前に必ず全文を読んでください。

---

<div align="center">

スクリーンショットの山ではなく、本当に「もう一度解ける」間違いノートを。

**[English](./README.md)** · **[简体中文](./README_ZH.md)** · **[日本語](./README_JA.md)** · **[한국어](./README_KO.md)**

</div>
