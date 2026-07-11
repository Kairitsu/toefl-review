<div align="center">

# TOEFL Review

**散らばった TOEFL の間違いを、繰り返し解き直し・確認・復習できる自分専用の問題バンクへ。**

軽量・オープンソース・セルフホスト型の TOEFL 間違い復習システムです。  
問題の構造化取り込み、試験形式の練習、即時採点、学習レポート、練習履歴に対応します。

[English](./README.md) · [简体中文](./README_ZH.md) · **日本語** · [한국어](./README_KO.md)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](./docker-compose.yml)
[![SQLite](https://img.shields.io/badge/Storage-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)

</div>

---

## TOEFL Review でできること

間違えた問題は、スクリーンショット、チャット、Word ファイル、さまざまなメモに散らばりがちです。

保存されていても、実際にもう一度解かれることはほとんどありません。

TOEFL Review は、次の流れを一つのシステムにまとめます。

> **問題を貼り付ける → 問題タイプを選ぶ → 内容を構造化する → プレビューして修正する → 個人用問題バンクへ保存する → 再び練習する → 学習レポートを見る → 履歴を確認する、または同じセットを解き直す**

単なる保存場所ではなく、長期的に蓄積し、繰り返し復習するための個人用練習システムです。

---

## 主な機能

### 構造化された問題取り込み

問題タイプごとに専用フォームが用意されているため、すべての情報を一つの大きなテキスト欄へ押し込む必要はありません。

| 問題タイプ | 取り込み内容 |
| --- | --- |
| 読解選択問題 | タイトル、本文、設問、A–D の選択肢、正解、解説 |
| Build a Sentence | プロンプト、文テンプレート、語彙バンク、正しい順序、完成文、解説 |
| Complete the Words | 下線の空欄を含む本文、解答リスト、解説 |

読解選択問題と一部の Build a Sentence 問題は、OpenAI Chat Completions 互換の LLM API で整理できます。

Complete the Words は、原文中の下線位置を基準にローカル解析を優先し、LLM が本文を書き換えたり空欄を追加したりするリスクを抑えます。

解析後はすぐ保存されません。構造化された項目を確認・修正してから問題バンクへ追加できます。

### 個人用問題ライブラリ

- 問題タイプで絞り込み；
- 設問や本文を検索；
- 作成日時、誤答率、最終練習日時で並べ替え；
- 問題ごとの試行回数、正解数、誤答数を確認；
- 単問練習、編集、削除；
- 誤答率の高い問題を把握；
- 指定した問題だけを選んで練習セットを作成。

問題を削除すると、その問題に紐づく解答履歴も削除されます。

### 問題タイプ別の練習 UI

#### 読解選択問題

本文と設問を分けて表示し、A、B、C、D を直接選択します。

#### Build a Sentence

固定テキストは元の位置に残り、語彙バンクの語句をクリックまたはドラッグして空欄へ配置できます。

#### Complete the Words

欠けた文字の位置に入力セルが直接表示され、欠けた文字数に応じて一文字ずつ入力します。

提出後は、正誤、自分の解答、正解、空欄ごとの判定、解説、累積統計がすぐ表示されます。

### 練習問題の選択

プリセットの問題数または任意の問題数を指定できます。ライブラリから問題を手動選択して、専用の練習セットを作ることもできます。

### 学習レポート

一回の練習が終わると、正答率だけではなく、全問題、正解、誤答のフィルター、原題、自分の解答、正解、空欄ごとの結果、解説を含む詳細レポートが作成されます。

### 練習履歴

完了した練習は自動保存されます。過去のレポートを開き直したり、同じ問題セットをそのまま解き直したりできます。

### 自分の LLM API を使用

設定画面で次の項目を入力できます。

- API Key；
- Base URL または完全なリクエスト URL；
- モデル名；
- 任意のカスタム JSON パラメータ。

OpenAI Chat Completions 互換のサービスであれば通常利用でき、接続テストも実行できます。

> 本プロジェクトには LLM サービスや利用枠は含まれません。料金、レート制限、データ処理方針は選択したサービスに依存します。

### ローカル保存と任意のログイン保護

問題、解答履歴、学習レポート、設定はローカル SQLite に保存されます。

```text
data/toefl_review.sqlite3
```

API Key は `APP_SECRET` から派生した Fernet キーで暗号化され、設定画面に平文で再表示されません。

設定画面から共通のユーザー名とパスワードを有効にできます。ただし、これは個人用インスタンスの保護であり、複数ユーザーのアカウントシステムではありません。公開時には Caddy や Nginx と HTTPS を併用してください。

> 現在の Web UI は主に簡体字中国語です。ドキュメントは多言語ですが、アプリ UI はまだ完全には国際化されていません。

---

## クイックスタート

Git、Docker、Docker Compose をインストールしてから実行します。

```bash
git clone https://github.com/Kairitsu/toefl-review.git
cd toefl-review

mkdir -p secrets data
cp secrets/app.env.example secrets/app.env
```

ランダムな秘密値を生成します。

```bash
openssl rand -hex 32
```

`secrets/app.env` に設定します。

```env
APP_SECRET=生成したランダム値をここに入力
```

データ作成後は `APP_SECRET` を変更しないでください。変更すると、保存済み API Key を復号できなくなります。

起動：

```bash
docker compose up -d --build
```

アクセス：

```text
http://127.0.0.1:3219
```

よく使うコマンド：

```bash
docker compose ps
docker compose logs -f app
docker compose down
```

---

## サーバーへの配置

Compose は既定で `127.0.0.1:3219` にのみバインドします。VPS では Caddy または Nginx を使い、ドメインを次へリバースプロキシしてください。

```text
http://127.0.0.1:3219
```

ドメインには HTTPS を有効にしてください。

一時的にアクセスする場合は SSH トンネルも利用できます。

```bash
ssh -L 3219:127.0.0.1:3219 username@server-address
```

---

## 初回利用の流れ

1. 設定画面を開く；
2. LLM の API Key、Base URL、モデル名を入力；
3. 接続テストを実行；
4. 必要に応じてアクセス認証を設定；
5. 取り込み画面で問題タイプを選択；
6. 問題、解答、解説を入力または貼り付け；
7. 解析結果を確認・修正；
8. 問題ライブラリへ保存；
9. 練習を開始。

---

## 更新・バックアップ・復元

バックアップ：

```bash
./scripts/backup-db.sh
```

バックアップは `data/backups/` に保存されます。

更新：

```bash
git pull
docker compose up -d --build
```

手動バックアップ：

```bash
docker compose down
cp -a data data-backup
docker compose up -d
```

復元時はデータベースを `data/toefl_review.sqlite3` に戻し、元の `APP_SECRET` を使い続けてください。

---

## Docker を使わない場合

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

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
```

起動後は `http://127.0.0.1:8000` を開きます。長期運用には Docker または Gunicorn を推奨します。

---

## データとプライバシー

- 問題と練習履歴は自分の SQLite に保存；
- API Key は暗号化して保存；
- 保存済み API Key はブラウザへ再表示しない；
- LLM 解析を実行したときだけ、問題内容を設定済みサービスへ送信；
- 第三者クラウドへの自動同期は行わない。

次の内容を Git にコミットしないでください。

```text
data/
secrets/app.env
API Key
データベースファイル
実際のログイン情報
```

---

## 対象範囲と制限

現在のバージョンは個人のセルフホスト利用を主目的としています。複数ユーザー向け学習プラットフォーム、TOEFL 問題のダウンロード・収集ツール、LLM 利用枠付き商用サービス、ETS 公式製品ではありません。

---

<details>
<summary><strong>技術構成</strong></summary>

```text
ブラウザ（素の HTML / CSS / JavaScript）
        │ HTTP JSON
        ▼
Flask + Gunicorn
        ├── 取り込み解析（ローカル規則 + 任意 LLM）
        ├── 問題管理と採点
        ├── 設定と任意のアクセス認証
        └── SQLite WAL → data/toefl_review.sqlite3
```

| レイヤー | 技術 |
| --- | --- |
| バックエンド | Python 3.12、Flask、Gunicorn |
| フロントエンド | 素の HTML、CSS、JavaScript |
| 保存 | SQLite、WAL モード |
| API Key 暗号化 | `cryptography` Fernet |
| パスワード | PBKDF2-SHA256 |
| 配置 | Docker Compose |
| 既定アドレス | `127.0.0.1:3219` |

</details>

---

## よくある質問

### LLM API は必須ですか？

問題ライブラリ、練習、レポート、履歴は LLM がなくても利用できます。Complete the Words は主にローカル規則で処理されます。読解選択問題の自動整理には、通常 OpenAI 互換 LLM が必要です。

### データは作者のサーバーへ送信されますか？

送信されません。本プロジェクトに作者運営の中央サーバーはありません。外部送信が発生するのは、設定した LLM の解析を自分で実行した場合だけです。

### スマートフォンでも使えますか？

はい。スマートフォンから配置先へアクセスできれば、レスポンシブなブラウザ UI を利用できます。

### 複数ユーザーが登録できますか？

できません。内蔵認証は一つのインスタンスを一組の共通認証情報で保護する機能です。

---

## コントリビューション

Issue と Pull Request を歓迎します。個人データや秘密情報をコミットせず、変更内容とテスト方法を説明してください。

---

## ライセンス

本プロジェクトは [GNU Affero General Public License v3.0](./LICENSE) の下で公開されています。

改変版を配布する場合や、ネットワークサービスとして他者へ提供する場合は、AGPL-3.0 のソースコード公開要件に従ってください。

---

<div align="center">

**間違いを「保存しただけ」で終わらせず、もう一度解きましょう。**

</div>
