<div align="center">

# TOEFL Review

**把散落的托福错题，变成真正可以反复练习、回看和复盘的私人题库。**

一个轻量、开源、自托管的托福错题复习系统。  
支持题目结构化导入、考试式练习、即时判分、学习报告和练习记录。

[English](./README.md) · **简体中文** · [日本語](./README_JA.md) · [한국어](./README_KO.md)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](./docker-compose.yml)
[![SQLite](https://img.shields.io/badge/Storage-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)

</div>

---

## TOEFL Review 能做什么？

很多错题最后都会变成截图、聊天记录、Word 文档或散落在各处的笔记。

它们虽然被“收藏”了，却很少真正被重新做一遍。

TOEFL Review 提供了一套完整的错题复习流程：

> **粘贴错题 → 选择题型 → 结构化解析 → 预览并校对 → 保存到私人题库 → 重新练习 → 查看学习报告 → 回顾记录或整轮重练**

它不是一个单纯保存题目的电子笔记，而是一个可以长期积累和反复使用的私人练习系统。

---

## 主要功能

### 结构化导入错题

根据题型提供专门的录入表格，不需要把所有内容塞进一个大文本框。

目前支持：

| 题型 | 导入内容 |
| --- | --- |
| 阅读选择题 | 标题、文章、问题、A—D 选项、正确答案、解析 |
| 写作造句题 | 提问内容、句子模板、词库、正确填入顺序、完整句子、解析 |
| 阅读填词题 | 带下划线空格的短文、答案列表、解析 |

阅读选择题和部分写作造句题可以通过兼容 OpenAI Chat Completions 协议的 LLM 接口进行整理。

阅读填词题会优先根据原文中的下划线位置进行本地解析，尽量避免模型擅自改写短文或凭空增加空格。

解析完成后不会立即入库。你可以先检查和修改结构化结果，确认无误后再保存。

### 私人题库

所有保存的题目都会进入本地题库。你可以：

- 按题型筛选题目；
- 搜索题干、文章和其他内容；
- 按创建时间、错误率或最近练习时间排序；
- 查看每道题的练习次数、正确次数和错误次数；
- 单独练习、编辑或删除某道题；
- 快速发现重复错误率较高的题目；
- 从题库中勾选指定题目组成一轮练习。

删除题目时，与该题关联的作答记录也会一并删除。

### 接近真实答题方式的练习界面

#### 阅读选择题

文章和问题分区展示，直接选择 A、B、C、D 选项。

#### 写作造句题

固定文本保留在句子原位，词库中的词块可以点击或拖动到对应空格中。

#### 阅读填词题

输入框直接出现在短文缺失字母的位置，并按照缺失字母数量显示逐字母输入格。

每次提交后都会立即显示：

- 本题是否正确；
- 你的答案；
- 正确答案；
- 每个空位的具体对错；
- 题目解析；
- 该题累计练习统计。

### 自由选择本轮题目

开始练习时，可以选择预设题数，也可以输入自定义题数。还可以进入题库，手动勾选希望练习的题目，再组成一轮专项练习。

练习过程中支持上一题、下一题、单题重做和提前退出。

### 完整学习报告

完成一轮练习后，系统不会只显示一个正确率数字，而是生成完整的学习报告。

报告包含总题数、答对数量、答错数量、正确率、全部/答对/答错筛选、每道题的原题、你的答案、正确答案、逐选项或逐空位判定以及题目解析。

### 练习记录

每轮练习结束后，系统会自动保存练习记录。点击任意历史记录，可以重新打开当时的完整学习报告，也可以直接重新练习这一整轮题目。

### 自备 LLM 接口

TOEFL Review 不绑定特定模型或服务商。在网页的“设置”页面中，可以填写：

- API Key；
- Base URL 或完整请求地址；
- 模型名称；
- 自定义 JSON 参数。

只要服务商兼容 OpenAI Chat Completions 请求格式，通常都可以接入。设置页面还提供连接测试功能。

> LLM 服务本身不包含在本项目中。调用费用、速率限制和数据处理规则由你选择的服务商决定。

### 本地保存与可选登录保护

题目、作答记录、练习报告和系统设置均保存在本地 SQLite 数据库中：

```text
data/toefl_review.sqlite3
```

LLM API Key 使用由 `APP_SECRET` 派生的 Fernet 密钥加密后写入数据库，不会在设置页面中明文回显。

你还可以在设置页面中启用访问认证。启用后，访问本系统需要输入统一的用户名和密码。

需要注意：

- 这是个人实例的访问保护，不是多用户账号系统；
- 内置登录不能代替 HTTPS；
- 对公网开放时仍应使用 Caddy、Nginx 等反向代理并配置 HTTPS。

---

## 快速开始

### 使用 Docker Compose 部署

请先安装 Git、Docker 和 Docker Compose，然后执行：

```bash
git clone https://github.com/Kairitsu/toefl-review.git
cd toefl-review

mkdir -p secrets data
cp secrets/app.env.example secrets/app.env
```

生成一个随机密钥：

```bash
openssl rand -hex 32
```

打开 `secrets/app.env`，把生成的随机字符串填写到等号后面：

```env
APP_SECRET=这里填写生成的随机字符串
```

项目产生数据后，请不要随意修改 `APP_SECRET`。更换它会导致数据库中原有的 API Key 无法解密。

启动服务：

```bash
docker compose up -d --build
```

访问：

```text
http://127.0.0.1:3219
```

常用命令：

```bash
docker compose ps
docker compose logs -f app
docker compose down
```

---

## 部署在服务器上

Docker Compose 默认只将服务绑定到服务器本机的 `127.0.0.1:3219`，避免应用端口直接暴露在公网。

在 VPS 或云服务器上部署时，建议使用 Caddy 或 Nginx 将域名反向代理到：

```text
http://127.0.0.1:3219
```

并为域名启用 HTTPS。

临时访问时，可以建立 SSH 隧道：

```bash
ssh -L 3219:127.0.0.1:3219 用户名@服务器地址
```

随后在本机浏览器访问 `http://127.0.0.1:3219`。

---

## 第一次使用

1. 打开“设置”页面；
2. 填写 LLM 的 API Key、Base URL 和模型名称；
3. 点击“测试连接”；
4. 根据需要设置访问用户名和密码；
5. 进入“导入”页面并选择题型；
6. 填写或粘贴题目、答案和解析；
7. 解析并检查预览结果；
8. 保存到题库；
9. 进入“练习”页面开始复习。

---

## 更新、备份与恢复

更新前建议先备份数据库：

```bash
./scripts/backup-db.sh
```

备份文件会保存到 `data/backups/`。

拉取最新代码并重新构建：

```bash
git pull
docker compose up -d --build
```

也可以停止容器后，手动备份整个 `data` 目录：

```bash
docker compose down
cp -a data data-backup
docker compose up -d
```

恢复时，将数据库文件放回 `data/toefl_review.sqlite3`，并继续使用原来的 `APP_SECRET`。

---

## 不使用 Docker

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

Windows PowerShell 激活虚拟环境时使用：

```powershell
.\.venv\Scripts\Activate.ps1
```

启动后访问 `http://127.0.0.1:8000`。

用于长期运行时，建议使用项目 Docker 配置或 Gunicorn，而不是 Flask 自带的开发服务器。

---

## 数据和隐私

- 题目和练习记录保存在自己的 SQLite 数据库中；
- API Key 加密后保存在数据库中；
- 浏览器不会重新显示已经保存的完整 API Key；
- 只有主动调用 LLM 解析时，题目内容才会发送给配置的 LLM 服务商；
- 项目本身不会自动将题库同步到第三方云端。

请勿提交：

```text
data/
secrets/app.env
任何 API Key
数据库文件
真实登录凭据
```

---

## 项目定位与限制

当前版本主要面向个人自托管使用。它不是多用户在线教育平台、托福题目下载或采集工具、带有内置大模型额度的商业服务，也不是 ETS 官方产品。

---

<details>
<summary><strong>技术架构</strong></summary>

```text
浏览器（原生 HTML / CSS / JavaScript）
        │ HTTP JSON
        ▼
Flask + Gunicorn
        ├── 导入解析（本地规则 + 可选 LLM）
        ├── 题目管理与判分
        ├── 设置与可选访问认证
        └── SQLite WAL → data/toefl_review.sqlite3
```

| 部分 | 技术 |
| --- | --- |
| 后端 | Python 3.12、Flask、Gunicorn |
| 前端 | 原生 HTML、CSS、JavaScript |
| 数据库 | SQLite，WAL 模式 |
| API Key 加密 | `cryptography` Fernet |
| 登录密码 | PBKDF2-SHA256 哈希 |
| 部署 | Docker Compose |
| 默认监听 | `127.0.0.1:3219` |

前端没有 Node.js 依赖，也不需要执行打包或构建命令。

</details>

<details>
<summary><strong>项目目录</strong></summary>

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

## 常见问题

### 必须配置 LLM API 才能使用吗？

题库、练习、学习报告和历史记录本身不依赖 LLM。阅读填词题主要通过本地规则解析，格式规范的写作造句题也可以优先使用本地结构化识别。阅读选择题等内容的自动整理通常需要兼容 OpenAI 协议的 LLM 接口。

### 数据会上传到项目作者的服务器吗？

不会。项目没有作者提供的中央服务器。数据默认保存在部署设备的 SQLite 数据库中。但在调用 LLM 解析时，粘贴的题目会发送给你自己配置的 LLM 服务商。

### 可以在手机上使用吗？

可以。页面针对窄屏设备进行了响应式适配，只要手机能够访问部署地址，就可以通过浏览器使用。

### 可以多人注册账号吗？

不可以。当前登录功能只为整个个人实例设置一组访问凭据，不包含注册、用户隔离和多人题库。

---

## 参与项目

发现问题或有改进建议时，欢迎提交 Issue 和 Pull Request。请勿把个人数据和密钥提交到仓库，并说明修改解决了什么问题以及完成了哪些测试。

---

## 开源许可证

本项目使用 [GNU Affero General Public License v3.0](./LICENSE)。

你可以使用、研究和修改本项目。分发修改版本，或将修改版本作为网络服务提供给他人使用时，需要遵守 AGPL-3.0 的源代码公开要求。

---

<div align="center">

**不要让错题只停留在“收藏过”。把它重新做一遍。**

</div>
