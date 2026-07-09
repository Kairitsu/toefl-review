<div align="center">

# TOEFL Review · 托福错题复习系统

**自托管的托福错题本：粘贴 → 结构化 → 考试风练习 → 盯住薄弱项。**

把乱格式的题目原文变成可检索、可统计、可反复练的私人题库。

[English](./README.md) · [简体中文](./README_ZH.md) · [日本語](./README_JA.md) · [한국어](./README_KO.md)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](./docker-compose.yml)
[![SQLite](https://img.shields.io/badge/Storage-SQLite%20WAL-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)

</div>

---

## 为什么需要 TOEFL Review？

错题本常见下场：截图堆、备忘录、半整理的 Word——真正要「再做一遍」时，几乎帮不上忙。

**TOEFL Review** 把你粘贴的托福材料变成**结构化私人题库**：

| 痛点 | 本项目做法 |
|------|------------|
| PDF / 笔记复制格式很乱 | 导入预览，保存前可改字段 |
| 「回头再看」等于不看 | 考试风格练习页，即时判分 |
| 不知道哪些题还不会 | 次数、正确/错误、错误率、最近练习时间 |
| 云端刷题 App 锁数据 | 本地 SQLite，文件在自己机器上 |
| API Key 散落在配置文件 | 密钥加密入库，界面内配置 |

> 定位：**个人自托管**。一个进程（或一套 Compose），无需外部数据库，默认不必登录注册。

---

## 功能一览

### 📥 智能导入

- 粘贴题干、文章、选项、答案、解析——格式可以不完美。
- 支持**指定题型**或自动识别（三种题型）。
- 通过任意 **OpenAI 兼容 Chat Completions** 接口做 LLM 结构化。
- 阅读填词 / 造句等结构化原文可走**本地确定性解析**（尽量不胡编空格）。
- 流程：**解析 → 预览校正 → 保存进题库**；答案不明确时可标为**待确认**。

### 📚 题库管理

- 按题型筛选，搜索题干 / 文章 / 提示。
- 按创建时间、错误率、最近练习时间排序。
- 每题统计，支持练习 / 编辑 / 删除。
- 高错误率题目高亮提示。

### ✍️ 考试风练习

三种出题模式：

| 模式 | 说明 |
|------|------|
| **随机** | 从题库随机抽题 |
| **只练错题** | 优先抽做过且错过的题 |
| **高错误率** | 优先抽正确率最差的题 |

交互：

- **阅读选择题** — 点选 A/B/C/D，提交后看解析。
- **写作造句题** — 点击词库词块填空；模板中的固定短语保留不动。
- **阅读填词题** — 在短文缺失字母处逐格填写。

每次作答写入 `attempts`，供统计与薄弱复习。

### ⚙️ 自备 LLM

在 **设置** 页配置（不写进源码）：

- API Key（用 `APP_SECRET` 派生 Fernet 加密存储）
- Base URL 或完整 Chat Completions URL
- 模型名
- 可选自定义 JSON 参数

兼容 OpenAI Chat Completions 协议的服务商均可。可在界面内测连通。API Key **不会明文回显**。

### 🔒 偏隐私的默认设计

- 题目、练习记录、设置均在本地 **SQLite**（`data/`）。
- 密钥放在 `secrets/` 或环境变量，已被 `.gitignore` 忽略。
- 仅在你主动「调用 LLM 解析」时，才会把粘贴内容发给对应服务商。

---

## 支持的题型

覆盖经典阅读选择，以及 **2026 新托福** 风格的造句 / 填词形态：

| 题型 | 代码 | 说明 |
|------|------|------|
| 阅读选择题 | `reading_choice` | 文章 + 题干 + A–D 选项 + 答案 + 解析 |
| 写作造句题 | `build_sentence` | 提问、含空位与固定词的句子模板、词库、正确顺序 |
| 阅读填词题 | `complete_words` | 短文中缺失字母串；按空依次补全后缀 |

当前界面文案以**简体中文**为主。

---

## 架构

```text
浏览器（静态 SPA）
   │  HTTP JSON
   ▼
Flask + Gunicorn
   ├── 导入解析（本地规则 + 可选 LLM）
   ├── 题目 CRUD + 作答判分
   ├── 设置（API Key 加密）
   └── SQLite (WAL)  →  ./data/toefl_review.sqlite3
```

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.12、Flask、Gunicorn |
| 前端 | 原生 HTML / CSS / JS（无构建步骤） |
| 存储 | SQLite + WAL |
| 加密 | `cryptography` Fernet（由 `APP_SECRET` 派生） |
| 部署 | 可选 Docker Compose；默认映射 `127.0.0.1:3219` |

---

## 快速开始

### 方式 A — Docker Compose（推荐）

```bash
git clone https://github.com/Kairitsu/toefl-review.git
cd toefl-review

mkdir -p secrets data
cp secrets/app.env.example secrets/app.env
# 编辑 secrets/app.env，填入足够长的随机 APP_SECRET
# 已有数据库时请保持 secret 不变，否则无法解密已存 API Key

docker compose up -d --build
```

访问：**http://127.0.0.1:3219**

健康检查：`GET /api/health`

### 方式 B — 本地 Python

```bash
git clone https://github.com/Kairitsu/toefl-review.git
cd toefl-review

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export APP_SECRET="$(openssl rand -hex 32)"
export DATA_DIR=data

flask --app app run --host 127.0.0.1 --port 8000

# 生产风格可改用：
# gunicorn --workers 2 --bind 127.0.0.1:8000 app:app
```

访问：**http://127.0.0.1:8000**

---

## 配置项

| 变量 | 必填 | 说明 |
|------|------|------|
| `APP_SECRET` | **是** | 长随机串，用于加密 LLM API Key。对**已有数据库必须保持稳定**。 |
| `DATA_DIR` | 否 | 数据目录（本地默认 `data`；Compose 中为 `/app/data`）。 |

参考文件：

- `secrets/app.env.example` → 复制为 `secrets/app.env` 供 Compose 使用  
- `.env.example` → 本地导出环境变量时参考  

LLM 的 **Key / Base URL / 模型 / 自定义参数** 在网页 **设置** 中配置，存入 SQLite（Key 加密）。

---

## 日常使用流程

1. **设置** — 填 Base URL、模型、API Key，点连接测试。  
2. **导入** — 粘贴原文 → 解析 → 预览修改 → 保存。  
3. **题库** — 检索、修正、对单题直接练习。  
4. **练习** — 选「随机 / 只练错题 / 高错误率」反复巩固。  
5. **备份** — 定期备份 SQLite。

```bash
# 通过 Docker 在线备份（写入 data/backups/）
./scripts/backup-db.sh
```

---

## 目录结构

```text
toefl-review/
├── app.py                 # Flask API、导入解析、判分、SQLite
├── static/
│   ├── index.html         # 页面壳
│   ├── app.js             # 导入 / 题库 / 练习 / 设置
│   └── styles.css         # 考试风样式
├── scripts/
│   └── backup-db.sh       # 容器内 SQLite 在线备份
├── secrets/
│   └── app.env.example    # APP_SECRET 模板（勿提交真实密钥）
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── LICENSE                # AGPL-3.0
├── README.md              # English
├── README_ZH.md           # 简体中文
├── README_JA.md           # 日本語
└── README_KO.md           # 한국어
```

运行时目录（已忽略提交）：`data/`、`secrets/app.env`、虚拟环境、浏览器测试产物等。

---

## API 一览

| 方法 | 路径 | 作用 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` / `POST` | `/api/settings` | 读取 / 保存 LLM 设置 |
| `POST` | `/api/settings/test` | 测试连通 |
| `POST` | `/api/import/parse` | 原文 → 草稿题 |
| `GET` / `POST` | `/api/questions` | 列表 / 新建 |
| `GET` / `PUT` / `DELETE` | `/api/questions/<id>` | 读 / 改 / 删 |
| `GET` | `/api/practice/next` | 抽题（`mode=random\|wrong\|high_error`） |
| `POST` | `/api/questions/<id>/attempts` | 提交答案并判分 |

---

## 安全提示

- 默认只绑定本机（Compose：`127.0.0.1:3219`）。若对公网开放，请自行加反向代理与认证。  
- 不要提交 `data/`、`secrets/app.env`、API Key、数据库文件。  
- 改 `APP_SECRET` 会导致已加密 API Key 无法解密。  
- LLM 提供商会看到你粘贴的内容——只发送你愿意外传的材料。

---

## 技术取舍（简短）

- **无前端构建** — 小 VPS 上也好改、好部署。  
- **SQLite WAL** — 个人错题本零运维。  
- **仅 OpenAI 兼容协议** — 一条 HTTP 路径对接多家模型。  
- **填词优先本地解析** — 空格尽量忠实于原文。

---

## 欢迎贡献

欢迎 Issue 与 PR：

1. 勿提交密钥与个人 `data/`。  
2. 变更尽量小而清晰。  
3. 说明测试方式（本地 Flask 和/或 Docker Compose）。

---

## 许可证

本项目采用 **GNU Affero General Public License v3.0（AGPL-3.0）** 开源。

完整文本见 [`LICENSE`](./LICENSE)。

**简要说明：** 你可以在 AGPL-3.0 下使用、学习、修改与分发本软件。若你将修改后的版本作为网络服务提供给他人使用，必须向该服务的用户提供对应源代码。网络服务场景下的源码义务是 AGPL 的核心条款——商用 SaaS 分发前请仔细阅读全文。

---

<div align="center">

给真正会「再做一遍」的托福学习者 —— 不是一堆截图文件夹。

**[English](./README.md)** · **[简体中文](./README_ZH.md)** · **[日本語](./README_JA.md)** · **[한국어](./README_KO.md)**

</div>
