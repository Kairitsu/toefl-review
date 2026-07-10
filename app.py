import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, jsonify, request, send_from_directory, session


DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DB_PATH = DATA_DIR / "toefl_review.sqlite3"
MAX_RAW_IMPORT_CHARS = 60000
ALLOWED_TYPES = {"reading_choice", "build_sentence", "complete_words"}
TYPE_LABELS = {
    "reading_choice": "阅读选择题",
    "build_sentence": "写作造句题",
    "complete_words": "阅读填词题",
}

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

_app_secret = os.environ.get("APP_SECRET", "")
app.secret_key = hashlib.sha256(_app_secret.encode("utf-8")).hexdigest() if _app_secret else secrets.token_hex(32)
app.permanent_session_lifetime = timedelta(days=7)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                article TEXT NOT NULL DEFAULT '',
                prompt TEXT NOT NULL DEFAULT '',
                explanation TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                data TEXT NOT NULL,
                needs_confirmation INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
                answer TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                detail TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_questions_type ON questions(type);
            CREATE INDEX IF NOT EXISTS idx_questions_updated_at ON questions(updated_at);
            CREATE INDEX IF NOT EXISTS idx_attempts_question_id ON attempts(question_id);
            CREATE INDEX IF NOT EXISTS idx_attempts_created_at ON attempts(created_at);
            """
        )


def app_fernet():
    secret = os.environ.get("APP_SECRET", "")
    if not secret:
        raise RuntimeError("APP_SECRET is not configured")
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value):
    if not value:
        return ""
    return app_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value):
    if not value:
        return ""
    try:
        return app_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Stored API key cannot be decrypted with the current APP_SECRET") from exc


def hash_password(password):
    salt = secrets.token_hex(16)
    iterations = 200000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password, stored):
    try:
        algo, iters_str, salt, expected_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iters_str)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
        return hmac.compare_digest(digest.hex(), expected_hex)
    except (ValueError, AttributeError):
        return False


AUTH_EXEMPT_EXACT = {"/", "/api/health", "/api/auth/login", "/api/auth/logout", "/api/auth/status"}


def auth_configured(db):
    username = get_setting(db, "auth_username", "")
    password_hash = get_setting(db, "auth_password_hash", "")
    return bool(username and password_hash)


def is_authed():
    authed_at = session.get("authed_at")
    if not authed_at:
        return False
    max_age = app.permanent_session_lifetime.total_seconds()
    return (time.time() - authed_at) < max_age


def get_setting(db, key, default=None):
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(db, key, value):
    db.execute(
        """
        INSERT INTO settings(key, value) VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def load_llm_settings():
    with get_db() as db:
        encrypted = get_setting(db, "api_key_encrypted", "")
        return {
            "api_key": decrypt_secret(encrypted) if encrypted else "",
            "api_key_configured": bool(encrypted),
            "base_url": get_setting(db, "base_url", ""),
            "model": get_setting(db, "model", ""),
            "custom_params": get_setting(db, "custom_params", "{}"),
        }


def parse_custom_params(custom_params):
    try:
        parsed = json.loads(custom_params or "{}")
    except json.JSONDecodeError:
        return None, ["自定义参数不是合法 JSON"]
    if not isinstance(parsed, dict):
        return None, ["自定义参数必须是 JSON 对象"]
    return parsed, []


def llm_settings_from_payload(payload, allow_saved_key=False):
    api_key = as_clean_string(payload.get("apiKey"))
    clear_api_key = bool(payload.get("clearApiKey"))
    base_url = as_clean_string(payload.get("baseUrl"))
    model = as_clean_string(payload.get("model"))
    raw_custom_params = payload.get("customParams")
    custom_params = as_clean_string(raw_custom_params if raw_custom_params is not None else "")

    saved = None
    if allow_saved_key:
        saved = load_llm_settings()
        if not api_key and not clear_api_key:
            api_key = saved["api_key"]
        if not base_url:
            base_url = saved["base_url"]
        if not model:
            model = saved["model"]
        if raw_custom_params is None:
            custom_params = saved["custom_params"]
    if not custom_params:
        custom_params = "{}"

    errors = []
    if base_url:
        errors.extend(validate_provider_url(base_url))
    else:
        errors.append("Base URL 或完整请求 URL不能为空")
    if not model:
        errors.append("模型名称不能为空")
    if not api_key:
        errors.append("API Key 未配置或未填写")

    parsed_params, param_errors = parse_custom_params(custom_params)
    errors.extend(param_errors)
    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "custom_params": custom_params,
        "parsed_params": parsed_params or {},
    }, errors


def validate_provider_url(url):
    errors = []
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return ["Base URL 或完整请求 URL 格式不正确"]
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        errors.append("Base URL 或完整请求 URL 必须是 http(s) URL")
    if parsed.username or parsed.password:
        errors.append("URL 中不能包含用户名或密码，请把认证信息放在 API Key 字段")
    query = urllib.parse.parse_qs(parsed.query)
    secret_names = {"api_key", "apikey", "key", "token", "access_token", "secret", "authorization"}
    if any(name.lower() in secret_names for name in query):
        errors.append("URL 查询参数中疑似包含密钥，请改用 API Key 字段")
    return errors


def redact(text, secrets=None):
    value = str(text or "")
    for secret in secrets or []:
        if secret and len(secret) >= 4:
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", value)
    value = re.sub(
        r"(?i)(api[_-]?key|authorization|access[_-]?token|token|secret)(['\"]?\s*[:=]\s*['\"]?)[^'\"&\s,}]+",
        r"\1\2[REDACTED]",
        value,
    )
    return value[:900]


def as_clean_string(value):
    return str(value or "").strip()


def json_loads(value, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


BLANK_MARKER_RE = re.compile(r"\{\{\s*(?:blank|\d+)\s*\}\}|_{2,}", flags=re.I)
# Structured import labels (Chinese + English aliases)
BUILD_FIELD_LABELS = {
    "提问者": "questioner",
    "问题": "questioner",
    "提示": "questioner",
    "对话": "questioner",
    "句子模板": "sentenceTemplate",
    "模板": "sentenceTemplate",
    "句型模板": "sentenceTemplate",
    "sentence template": "sentenceTemplate",
    "template": "sentenceTemplate",
    "词库": "wordBank",
    "单词库": "wordBank",
    "word bank": "wordBank",
    "words": "wordBank",
    "正确答案": "correctAnswer",
    "正确顺序": "correctOrder",
    "答案": "correctAnswer",
    "correct answer": "correctAnswer",
    "correct order": "correctOrder",
    "完整句子": "completeSentence",
    "完整正确句子": "completeSentence",
    "解析": "analysis",
    "分析": "analysis",
    "explanation": "analysis",
}


def count_template_blanks(template):
    return len(BLANK_MARKER_RE.findall(normalize_sentence_template(template) if template else ""))


def normalize_sentence_template(template):
    """Normalize blank markers to {{blank}}; preserve fixed text and punctuation."""
    text = as_clean_string(template)
    if not text:
        return ""
    # Normalize explicit blank tokens first, then underscore blanks (2+ underscores)
    text = re.sub(r"\{\{\s*(?:blank|\d+)\s*\}\}", "{{blank}}", text, flags=re.I)
    text = re.sub(r"_{2,}", "{{blank}}", text)
    # Collapse excessive spaces around blanks while keeping single spaces as fixed separators
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *(\{\{blank\}\}) *", r" \1 ", text)
    text = re.sub(r" +([.,!?;:])", r"\1", text)
    text = re.sub(r" +", " ", text).strip()
    # Keep "{{blank}}." style without space before punctuation attached after blank
    text = re.sub(r"(\{\{blank\}\}) ([.,!?;:])", r"\1\2", text)
    return text


def parse_template_segments(template):
    """
    Split a sentence template into ordered segments of fixed text and blanks.
    Example: "{{blank}} during the {{blank}}."
    -> [{"type":"blank","index":1}, {"type":"fixed","text":" during the "},
        {"type":"blank","index":2}, {"type":"fixed","text":"."}]
    """
    normalized = normalize_sentence_template(template)
    segments = []
    blank_index = 0
    cursor = 0
    for match in BLANK_MARKER_RE.finditer(normalized):
        if match.start() > cursor:
            fixed = normalized[cursor : match.start()]
            if fixed:
                segments.append({"type": "fixed", "text": fixed})
        blank_index += 1
        segments.append({"type": "blank", "index": blank_index})
        cursor = match.end()
    if cursor < len(normalized):
        tail = normalized[cursor:]
        if tail:
            segments.append({"type": "fixed", "text": tail})
    return segments


def tokens_equal(left, right):
    return as_clean_string(left).casefold() == as_clean_string(right).casefold()


def normalize_options(options):
    normalized = []
    if isinstance(options, dict):
        for key in ["A", "B", "C", "D"]:
            normalized.append({"key": key, "text": as_clean_string(options.get(key, ""))})
        return normalized
    if not isinstance(options, list):
        return []
    for index, option in enumerate(options[:4]):
        key = chr(ord("A") + index)
        if isinstance(option, dict):
            key = as_clean_string(option.get("key", key)).upper()[:1] or key
            text = as_clean_string(option.get("text", option.get("content", "")))
        else:
            text = as_clean_string(option)
        normalized.append({"key": key, "text": text})
    return normalized


def normalize_build_data(data):
    template = normalize_sentence_template(
        data.get("sentenceTemplate") or data.get("template") or data.get("sentence") or ""
    )
    word_bank = list_from_any(data.get("wordBank", data.get("words", [])))
    correct_order = list_from_any(data.get("correctOrder", data.get("answerOrder", [])))
    complete_sentence = as_clean_string(data.get("completeSentence") or data.get("fullSentence") or "")

    # If only a full-sentence answer is present, try to derive order + template from word bank
    raw_answer = as_clean_string(data.get("correctAnswer") or data.get("answer") or "")
    if not correct_order and raw_answer:
        answer_items = list_from_any(raw_answer)
        if len(answer_items) > 1 and all(
            any(tokens_equal(item, bank) for bank in word_bank) for item in answer_items
        ):
            correct_order = answer_items
            if not complete_sentence:
                complete_sentence = " ".join(answer_items)
        elif word_bank:
            matches = find_answer_token_matches(raw_answer, word_bank)
            if matches:
                correct_order = [match["token"] for match in matches]
            if not complete_sentence:
                complete_sentence = raw_answer

    if not complete_sentence and correct_order:
        # Reconstruct best-effort complete sentence from template when possible later
        complete_sentence = " ".join(correct_order)

    if not template and complete_sentence and word_bank and correct_order:
        matches = find_answer_token_matches(complete_sentence, word_bank)
        if matches:
            template = normalize_sentence_template(template_from_answer_matches(complete_sentence, matches))

    if not template and correct_order:
        template = normalize_sentence_template(" ".join("{{blank}}" for _ in correct_order) + ".")

    # Rebuild complete sentence only when missing or it's a bare join of tokens
    # (so we inject fixed phrases like "during the"). Keep original prose casing.
    if correct_order and template:
        rebuilt = render_sentence_from_template(template, correct_order)
        bare_join = " ".join(correct_order)
        if rebuilt and (
            not complete_sentence
            or tokens_equal(complete_sentence, bare_join)
            or complete_sentence == bare_join
        ):
            complete_sentence = rebuilt
        elif not complete_sentence and rebuilt:
            complete_sentence = rebuilt

    return {
        "sentenceTemplate": template,
        "wordBank": word_bank,
        "correctOrder": correct_order,
        "completeSentence": complete_sentence,
        "templateSegments": parse_template_segments(template) if template else [],
    }


def render_sentence_from_template(template, order):
    """Fill blanks in template with order tokens to rebuild the full sentence."""
    tokens = list(order or [])
    index = 0

    def repl(_match):
        nonlocal index
        value = tokens[index] if index < len(tokens) else ""
        index += 1
        return value

    filled = BLANK_MARKER_RE.sub(repl, normalize_sentence_template(template))
    filled = re.sub(r"\s+", " ", filled).strip()
    filled = re.sub(r"\s+([.,!?;:])", r"\1", filled)
    return filled


# Visible word prefix + underscores (Complete the Words raw form).
# Supports both ne__ and spaced forms like met _ _ _.
COMPLETE_UNDERSCORE_RE = re.compile(r"([A-Za-z]+)((?:[ \t]*_){2,})")
# Internal marker form: civiliza[[1]]
COMPLETE_MARKER_RE = re.compile(r"([A-Za-z]*)\[\[[\s]*([A-Za-z0-9_-]+)[\s]*\]\]")
COMPLETE_FIELD_LABELS = {
    "标题": "title",
    "title": "title",
    "原始短文": "passage",
    "题目/原始短文": "passage",
    "题目": "passage",
    "短文": "passage",
    "文章": "passage",
    "passage": "passage",
    "原文": "passage",
    "答案": "answers",
    "正确答案": "answers",
    "答案列表": "answers",
    "answers": "answers",
    "解析": "analysis",
    "解析（可选）": "analysis",
    "分析": "analysis",
    "explanation": "analysis",
    "题型": "typeLabel",
    "提示": "prompt",
    "说明": "prompt",
}


def normalize_blank_item(blank, index=1):
    """Normalize one blank. Prefix comes only from underscore/marker positions, never invented."""
    if not isinstance(blank, dict):
        blank = {}
    blank_id = as_clean_string(blank.get("id") or index) or str(index)
    prefix = as_clean_string(blank.get("prefix") or blank.get("stem") or "")
    answer = as_clean_string(blank.get("answer") or blank.get("suffix") or blank.get("missing") or "")
    full_word = as_clean_string(blank.get("fullWord") or blank.get("word") or blank.get("completeWord") or "")
    try:
        blank_length = int(blank.get("blankLength") or blank.get("blank_length") or blank.get("length") or 0)
    except (TypeError, ValueError):
        blank_length = 0

    # Prefer answer + prefix to derive full word
    if prefix and answer and not full_word:
        # Answer may be missing letters OR the complete word
        if answer.casefold().startswith(prefix.casefold()) and len(answer) > len(prefix):
            full_word = answer
            answer = full_word[len(prefix) :]
        else:
            full_word = prefix + answer
    elif prefix and full_word and not answer:
        if full_word.casefold().startswith(prefix.casefold()):
            answer = full_word[len(prefix) :]
    elif prefix and answer and full_word:
        # If answer is actually the full word, re-split from prefix
        if tokens_equal(answer, full_word) and full_word.casefold().startswith(prefix.casefold()):
            answer = full_word[len(prefix) :]
            full_word = prefix + answer
        elif not tokens_equal(prefix + answer, full_word):
            if full_word.casefold().startswith(prefix.casefold()) and tokens_equal(answer, full_word):
                answer = full_word[len(prefix) :]
            elif answer.casefold().startswith(prefix.casefold()) and len(answer) > len(prefix):
                full_word = answer
                answer = full_word[len(prefix) :]
            else:
                # Keep provided values; validation will reject inconsistency
                pass

    if prefix and answer and not full_word:
        full_word = prefix + answer
    if blank_length <= 0 and answer:
        blank_length = len(answer)

    return {
        "id": blank_id,
        "prefix": prefix,
        "answer": answer,
        "fullWord": full_word,
        "blankLength": blank_length,
        "note": "",
        "confirmed": bool(answer and full_word),
    }


def scan_underscore_blanks(passage):
    """
    Scan passage for incomplete words that contain underscores.
    Only tokens matching letter(s) + 2+ underscores count as blanks.
    Complete words without underscores are never treated as blanks.
    """
    text = passage or ""
    blanks = []
    parts = []
    last = 0
    counter = 0
    for match in COMPLETE_UNDERSCORE_RE.finditer(text):
        parts.append(text[last : match.start()])
        counter += 1
        prefix = match.group(1)
        blank_length = len(re.findall(r"_", match.group(2)))
        blank_id = str(counter)
        blanks.append({"id": blank_id, "prefix": prefix, "answer": "", "fullWord": "", "blankLength": blank_length})
        parts.append(f"{prefix}[[{blank_id}]]")
        last = match.end()
    parts.append(text[last:])
    return {"passageText": "".join(parts), "blanks": blanks}


def apply_answer_value_to_blank(blank, value, index=1):
    """Apply one answer (missing letters or full word) to a blank that already has a prefix."""
    item = dict(blank or {})
    prefix = as_clean_string(item.get("prefix"))
    value = as_clean_string(value)
    if not value:
        return normalize_blank_item(item, index=index)
    if prefix and value.casefold().startswith(prefix.casefold()) and len(value) > len(prefix):
        # Full-word answer: civilization for civiliza____
        item["fullWord"] = value
        item["answer"] = value[len(prefix) :]
    elif prefix:
        # Missing-letter answer: tion for civiliza____
        item["answer"] = value
        item["fullWord"] = prefix + value
    else:
        item["answer"] = value
        item["fullWord"] = value
    return normalize_blank_item(item, index=index)


def match_answers_to_underscore_blanks(passage, answer_values):
    """
    Core complete-words rule:
    1. Scan underscores in passage order → blank list
    2. Match answers in the same order
    3. Do not invent blanks for complete words
    4. Do not rewrite the passage beyond underscore → [[id]] markers
    Returns {passageText, blanks, errors}
    """
    scanned = scan_underscore_blanks(passage)
    blanks = scanned["blanks"]
    # Keep positional empties (from structured blank rows); free-text parsers already drop blanks.
    answers = [as_clean_string(v) for v in (answer_values or [])]
    non_empty_answers = [a for a in answers if a]
    errors = []

    if not blanks:
        errors.append("没有识别到任何下划线空格（需要类似 ne__ / civiliza____ 的残缺词）")
        return {
            "passageText": as_clean_string(passage),
            "blanks": [],
            "errors": errors,
        }

    # Count check only when caller provided an answer list (possibly with empties for positions)
    if answers and len(answers) != len(blanks):
        errors.append(
            f"空格数量和答案数量不一致：识别到 {len(blanks)} 个下划线空格，但提供了 {len(non_empty_answers) or len(answers)} 个答案"
        )
        return {
            "passageText": scanned["passageText"],
            "blanks": [normalize_blank_item(b, index=i + 1) for i, b in enumerate(blanks)],
            "errors": errors,
        }

    matched = []
    for index, blank in enumerate(blanks):
        value = answers[index] if index < len(answers) else ""
        item = apply_answer_value_to_blank(blank, value, index=index + 1)
        prefix = item.get("prefix") or ""
        full_word = item.get("fullWord") or ""
        if full_word and prefix and not full_word.casefold().startswith(prefix.casefold()):
            errors.append(
                f"空格 {item.get('id')}：完整词“{full_word}”不以短文前缀“{prefix}”开头，不能匹配"
            )
        matched.append(item)

    return {
        "passageText": scanned["passageText"],
        "blanks": matched,
        "errors": errors,
    }


def normalize_complete_data(data):
    """
    Normalize complete-words payload.
    Underscores in passage are the only source of blank positions.
    Existing blank answers are re-applied by order after scanning.
    """
    raw_passage = as_clean_string(data.get("passageText") or data.get("passage") or data.get("article") or "")
    blanks_in = data.get("blanks", [])
    if not isinstance(blanks_in, list):
        blanks_in = []

    # Prefer underscore form when present — never invent blanks from complete words
    if raw_passage and COMPLETE_UNDERSCORE_RE.search(raw_passage):
        answer_values = []
        for blank in blanks_in:
            if not isinstance(blank, dict):
                continue
            # Preserve provided answer preference: answer (missing) or fullWord
            value = as_clean_string(blank.get("answer") or blank.get("fullWord") or "")
            answer_values.append(value)
        # If blanks_in empty, still scan passage (answers may be filled later)
        if any(answer_values):
            matched = match_answers_to_underscore_blanks(raw_passage, answer_values)
            # If count mismatch, still keep scanned structure with whatever we can
            blanks = matched["blanks"]
            raw_passage = matched["passageText"]
        else:
            scanned = scan_underscore_blanks(raw_passage)
            raw_passage = scanned["passageText"]
            blanks = [normalize_blank_item(b, index=i + 1) for i, b in enumerate(scanned["blanks"])]
    elif raw_passage and COMPLETE_MARKER_RE.search(raw_passage):
        # Already marker form: rebuild blanks strictly from markers in passage order
        marker_ids = re.findall(r"\[\[\s*([A-Za-z0-9_-]+)\s*\]\]", raw_passage)
        by_id = {
            str(b.get("id")): b
            for b in blanks_in
            if isinstance(b, dict) and as_clean_string(b.get("id"))
        }
        blanks = []
        for index, mid in enumerate(marker_ids, start=1):
            source = by_id.get(mid) or (blanks_in[index - 1] if index - 1 < len(blanks_in) else {})
            if not isinstance(source, dict):
                source = {}
            prefix = as_clean_string(source.get("prefix")) or extract_prefix_before_marker(raw_passage, mid)
            item = normalize_blank_item(
                {
                    "id": mid,
                    "prefix": prefix,
                    "answer": source.get("answer", ""),
                    "fullWord": source.get("fullWord", ""),
                    "blankLength": source.get("blankLength", 0),
                },
                index=index,
            )
            blanks.append(item)
    else:
        # No underscores and no markers: do not invent blanks from free text
        blanks = []

    return {
        "passageText": raw_passage,
        "blanks": blanks,
        "completePassage": render_complete_passage(raw_passage, blanks),
    }


def extract_prefix_before_marker(passage, blank_id):
    pattern = re.compile(rf"([A-Za-z]*)\[\[[\s]*{re.escape(str(blank_id))}[\s]*\]\]")
    match = pattern.search(passage or "")
    return match.group(1) if match else ""


def convert_underscore_passage_to_markers(passage, existing_blanks=None):
    """Convert 'civiliza____' style passage into 'civiliza[[1]]' + blank rows."""
    existing = list(existing_blanks or [])
    answer_values = []
    for source in existing:
        if not isinstance(source, dict):
            answer_values.append("")
            continue
        answer_values.append(
            as_clean_string(source.get("answer") or source.get("fullWord") or "")
        )
    if any(answer_values):
        matched = match_answers_to_underscore_blanks(passage, answer_values)
        return {"passageText": matched["passageText"], "blanks": matched["blanks"]}
    scanned = scan_underscore_blanks(passage)
    blanks = [normalize_blank_item(b, index=i + 1) for i, b in enumerate(scanned["blanks"])]
    return {"passageText": scanned["passageText"], "blanks": blanks}


def render_complete_passage(passage, blanks):
    """Replace markers with full words for a complete correct passage preview."""
    by_id = {str(b.get("id")): b for b in (blanks or []) if isinstance(b, dict)}

    def repl(match):
        prefix = match.group(1) or ""
        blank_id = match.group(2)
        blank = by_id.get(blank_id, {})
        full = as_clean_string(blank.get("fullWord"))
        if full:
            return full
        answer = as_clean_string(blank.get("answer"))
        stem = as_clean_string(blank.get("prefix") or prefix)
        if stem or answer:
            return f"{stem}{answer}"
        return match.group(0)

    text = COMPLETE_MARKER_RE.sub(repl, passage or "")
    # Also fill leftover underscore forms if any
    return text


def parse_numbered_answers(text):
    """
    Parse answer lists like:
      1. tion
      2. tems
    or:
      1) civilization
      - ever
    """
    answers = []
    if not text:
        return answers
    # Prefer numbered lines
    for match in re.finditer(
        r"(?m)^\s*(?:(\d+)[\.\)、:：]\s*|\-\s+|\*\s+)(.+?)\s*$",
        text,
    ):
        idx = match.group(1)
        value = as_clean_string(match.group(2))
        if not value:
            continue
        answers.append({"index": int(idx) if idx else len(answers) + 1, "value": value})
    if answers:
        answers.sort(key=lambda item: item["index"])
        return [item["value"] for item in answers]
    # Fallback: comma / newline split
    return list_from_any(text)


def extract_structured_complete_fields(raw_text):
    text = raw_text or ""
    label_names = sorted(COMPLETE_FIELD_LABELS.keys(), key=len, reverse=True)
    escaped = [re.escape(name) for name in label_names]
    pattern = re.compile(rf"(?:^|\n)\s*({'|'.join(escaped)})\s*[：:]\s*", flags=re.I)
    matches = list(pattern.finditer(text))
    if not matches:
        return {}
    fields = {}
    for index, match in enumerate(matches):
        raw_label = match.group(1)
        key = COMPLETE_FIELD_LABELS.get(raw_label)
        if not key:
            for name, mapped in COMPLETE_FIELD_LABELS.items():
                if name.casefold() == raw_label.casefold():
                    key = mapped
                    break
        if not key:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        fields[key] = as_clean_string(text[start:end])
    return fields


def looks_like_complete_words_raw(raw_text):
    text = raw_text or ""
    if extract_structured_complete_fields(text):
        # Need blank-like content
        if COMPLETE_UNDERSCORE_RE.search(text) or COMPLETE_MARKER_RE.search(text):
            return True
        if re.search(r"(短文|答案|complete the words|填词)", text, flags=re.I):
            return True
    signals = 0
    if COMPLETE_UNDERSCORE_RE.search(text):
        signals += 2
    if re.search(r"(?m)^\s*\d+[\.\)、]", text):
        signals += 1
    if re.search(r"(阅读填词|Complete the Words|civiliza|填词)", text, flags=re.I):
        signals += 1
    return signals >= 2


def apply_answers_to_blanks(blanks, answer_values):
    """Merge answers into blank rows by order; support suffix or full-word answers."""
    result = []
    for index, blank in enumerate(blanks):
        value = answer_values[index] if index < len(answer_values) else ""
        result.append(apply_answer_value_to_blank(blank, value, index=index + 1))
    return result


def build_complete_parts_from_structured_fields(fields):
    """Build complete-words data only from passage underscores + ordered answers."""
    passage = as_clean_string(fields.get("passage", ""))
    answers_raw = as_clean_string(fields.get("answers", ""))
    analysis = as_clean_string(fields.get("analysis", ""))

    if not passage and fields.get("body"):
        passage = as_clean_string(fields.get("body"))

    answer_values = parse_numbered_answers(answers_raw)
    matched = match_answers_to_underscore_blanks(passage, answer_values)
    data = {
        "passageText": matched["passageText"],
        "blanks": matched["blanks"],
        "completePassage": render_complete_passage(matched["passageText"], matched["blanks"]),
    }
    return {
        "title": "",
        "prompt": "Fill in the missing letters in the paragraph",
        "explanation": analysis,
        "data": data,
        "errors": list(matched.get("errors") or []),
    }


def parse_structured_complete_words(raw_text):
    fields = extract_structured_complete_fields(raw_text)
    if not fields:
        if not looks_like_complete_words_raw(raw_text):
            return None
        # Freeform: whole text as passage if underscores present
        fields = {"passage": as_clean_string(raw_text)}

    # If only passage+answers unlabeled: try split by 答案
    if "passage" not in fields and "answers" not in fields:
        split = re.split(r"(?i)(?:^|\n)\s*(?:答案|正确答案|答案列表)\s*[：:]\s*", raw_text, maxsplit=1)
        if len(split) == 2:
            fields["passage"] = as_clean_string(split[0])
            rest = split[1]
            analysis_split = re.split(r"(?i)(?:^|\n)\s*(?:解析|分析)\s*[：:]\s*", rest, maxsplit=1)
            fields["answers"] = as_clean_string(analysis_split[0])
            if len(analysis_split) == 2:
                fields["analysis"] = as_clean_string(analysis_split[1])

    parts = build_complete_parts_from_structured_fields(fields)
    data = parts["data"]
    question = normalize_question(
        {
            "type": "complete_words",
            "title": "",
            "article": data.get("passageText") or "",
            "prompt": parts.get("prompt") or "Fill in the missing letters in the paragraph",
            "explanation": parts.get("explanation") or "",
            "needsConfirmation": False,
            "data": data,
        }
    )
    parse_errors = list(parts.get("errors") or [])
    if parse_errors:
        question["_parseErrors"] = parse_errors
    return question


def merge_complete_words_draft(primary, fallback):
    """Prefer local underscore-based parse; never let LLM invent extra blanks."""
    if not fallback:
        return primary
    if not primary:
        return fallback
    # Local structured parse is authoritative for complete_words
    return normalize_question(fallback)


def normalize_type_hint(type_hint):
    hint = as_clean_string(type_hint)
    return hint if hint in ALLOWED_TYPES else ""


def list_from_any(value):
    if isinstance(value, list):
        return [as_clean_string(item) for item in value if as_clean_string(item)]
    if isinstance(value, str):
        return [as_clean_string(item) for item in re.split(r"[\n,，;；]", value) if as_clean_string(item)]
    return []


def extract_structured_build_fields(raw_text):
    """Parse labeled Build a Sentence paste formats into structured fields."""
    text = raw_text or ""
    # Longest labels first so "完整正确句子" wins over "完整句子", etc.
    label_names = sorted(BUILD_FIELD_LABELS.keys(), key=len, reverse=True)
    escaped = [re.escape(name) for name in label_names]
    pattern = re.compile(rf"(?:^|\n)\s*({'|'.join(escaped)})\s*[：:]\s*", flags=re.I)
    matches = list(pattern.finditer(text))
    if not matches:
        return {}
    fields = {}
    for index, match in enumerate(matches):
        raw_label = match.group(1)
        key = BUILD_FIELD_LABELS.get(raw_label) or BUILD_FIELD_LABELS.get(raw_label.casefold())
        if not key:
            # Case-insensitive lookup for English labels
            for name, mapped in BUILD_FIELD_LABELS.items():
                if name.casefold() == raw_label.casefold():
                    key = mapped
                    break
        if not key:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = as_clean_string(text[start:end])
        # Later labels of same key overwrite earlier (more specific paste order)
        fields[key] = value
    return fields


def looks_like_build_sentence_raw(raw_text):
    text = raw_text or ""
    if extract_structured_build_fields(text):
        return True
    signals = 0
    if re.search(r"(提问者|词库|句子模板|正确答案|Build a Sentence|word bank)", text, flags=re.I):
        signals += 1
    if BLANK_MARKER_RE.search(text) or re.search(r"_{3,}", text):
        signals += 1
    if re.search(r"(presentation|during the|word bank|词库)", text, flags=re.I):
        signals += 1
    return signals >= 2


def token_regex(token):
    parts = [part for part in re.split(r"\s+", as_clean_string(token)) if part]
    if not parts:
        return None
    return r"\s+".join(re.escape(part) for part in parts)


def ranges_overlap(start, end, ranges):
    return any(start < used_end and end > used_start for used_start, used_end in ranges)


def find_answer_token_matches(answer, word_bank):
    """Greedy longest-token matching of word-bank items inside the correct sentence."""
    matches = []
    used_ranges = []
    candidates = sorted({as_clean_string(item) for item in word_bank if as_clean_string(item)}, key=len, reverse=True)
    for token in candidates:
        pattern = token_regex(token)
        if not pattern:
            continue
        for match in re.finditer(pattern, answer or "", flags=re.I):
            if ranges_overlap(match.start(), match.end(), used_ranges):
                continue
            matches.append({"token": token, "start": match.start(), "end": match.end()})
            used_ranges.append((match.start(), match.end()))
            break
    return sorted(matches, key=lambda item: item["start"])


def template_from_answer_matches(answer, matches):
    if not matches:
        return ""
    parts = []
    cursor = 0
    for match in matches:
        parts.append(answer[cursor : match["start"]])
        parts.append("{{blank}}")
        cursor = match["end"]
    parts.append(answer[cursor:])
    return normalize_sentence_template("".join(parts))


def derive_correct_order_from_answer(answer, word_bank, expected_blank_count=0):
    """Derive ordered fill tokens from a full-sentence answer and word bank."""
    answer = as_clean_string(answer)
    word_bank = list_from_any(word_bank)
    if not answer:
        return [], answer

    answer_items = list_from_any(answer)
    # Explicit ordered list (comma / newline separated tokens all in bank)
    if len(answer_items) > 1 and all(any(tokens_equal(item, bank) for bank in word_bank) for item in answer_items):
        return answer_items, " ".join(answer_items)

    if word_bank:
        matches = find_answer_token_matches(answer, word_bank)
        if matches:
            order = [match["token"] for match in matches]
            if expected_blank_count and len(order) != expected_blank_count:
                # Prefer match count when blanks known; still return best effort
                pass
            return order, answer

    if any(tokens_equal(answer, bank) for bank in word_bank):
        return [next(bank for bank in word_bank if tokens_equal(answer, bank))], answer
    return [], answer


def build_sentence_parts_from_structured_fields(fields):
    word_bank = list_from_any(fields.get("wordBank", ""))
    explicit_template = normalize_sentence_template(fields.get("sentenceTemplate", ""))
    correct_answer = as_clean_string(fields.get("correctAnswer") or fields.get("correctOrder") or "")
    complete_sentence = as_clean_string(fields.get("completeSentence") or "")
    blank_count = count_template_blanks(explicit_template) if explicit_template else 0

    correct_order, inferred_sentence = derive_correct_order_from_answer(
        correct_answer or complete_sentence, word_bank, expected_blank_count=blank_count
    )
    if not complete_sentence:
        complete_sentence = inferred_sentence or correct_answer

    sentence_template = explicit_template
    if not sentence_template and complete_sentence and word_bank:
        matches = find_answer_token_matches(complete_sentence, word_bank)
        if matches:
            sentence_template = template_from_answer_matches(complete_sentence, matches)
            if not correct_order:
                correct_order = [match["token"] for match in matches]

    if not sentence_template and correct_order:
        sentence_template = normalize_sentence_template(
            " ".join("{{blank}}" for _ in correct_order) + ("." if complete_sentence.endswith(".") else "")
        )

    # Prefer the original full-sentence answer casing when available.
    # Rebuild only when we lack a proper sentence (no spaces / no fixed text).
    original_sentence = as_clean_string(fields.get("completeSentence") or correct_answer)
    if original_sentence and " " in original_sentence and not list_from_any(original_sentence) == correct_order:
        # original_sentence is a prose sentence, not a token list
        if not re.fullmatch(r"[\w\s,'-]+", original_sentence) or any(
            phrase in original_sentence.casefold()
            for phrase in (" during ", " because ", " of ", " to ", " the ")
        ) or original_sentence[:1].isupper():
            complete_sentence = original_sentence
    elif sentence_template and correct_order:
        rebuilt = render_sentence_from_template(sentence_template, correct_order)
        if rebuilt and "{{blank}}" not in rebuilt:
            complete_sentence = rebuilt

    if not complete_sentence and original_sentence:
        complete_sentence = original_sentence

    return {
        "sentenceTemplate": sentence_template,
        "wordBank": word_bank,
        "correctOrder": correct_order,
        "completeSentence": complete_sentence,
        "correctAnswer": correct_answer,
    }


def parse_structured_build_sentence(raw_text):
    fields = extract_structured_build_fields(raw_text)
    if not fields:
        # Freeform: still try if user pasted template + word bank without labels
        if not looks_like_build_sentence_raw(raw_text):
            return None
        fields = {"questioner": as_clean_string(raw_text)}

    data = build_sentence_parts_from_structured_fields(fields)
    needs_confirmation = not (
        as_clean_string(data.get("sentenceTemplate"))
        and data.get("wordBank")
        and data.get("correctOrder")
        and count_template_blanks(data.get("sentenceTemplate")) == len(data.get("correctOrder") or [])
    )
    return normalize_question(
        {
            "type": "build_sentence",
            "title": "",
            "article": "",
            "prompt": fields.get("questioner", ""),
            "explanation": fields.get("analysis", ""),
            "needsConfirmation": needs_confirmation,
            "data": data,
        }
    )


def merge_build_sentence_draft(primary, fallback):
    if not fallback:
        return primary
    merged = dict(primary or {})
    merged["type"] = "build_sentence"
    if not as_clean_string(merged.get("prompt")):
        merged["prompt"] = fallback.get("prompt", "")
    if not as_clean_string(merged.get("explanation")):
        merged["explanation"] = fallback.get("explanation", "")
    data = dict(merged.get("data") or {})
    fallback_data = fallback.get("data") or {}
    for key in ["sentenceTemplate", "wordBank", "correctOrder", "completeSentence"]:
        current = data.get(key)
        missing = not current if isinstance(current, list) else not as_clean_string(current)
        if missing:
            data[key] = fallback_data.get(key, [] if key in {"wordBank", "correctOrder"} else "")
    # Prefer the template that actually contains fixed text (not pure blanks only)
    primary_template = as_clean_string(data.get("sentenceTemplate"))
    fallback_template = as_clean_string(fallback_data.get("sentenceTemplate"))
    if fallback_template and primary_template:
        primary_has_fixed = bool(re.sub(r"\{\{blank\}\}|\s+", "", primary_template))
        fallback_has_fixed = bool(re.sub(r"\{\{blank\}\}|\s+", "", fallback_template))
        if fallback_has_fixed and not primary_has_fixed:
            data["sentenceTemplate"] = fallback_template
        elif (
            count_template_blanks(fallback_template) == len(data.get("correctOrder") or [])
            and count_template_blanks(primary_template) != len(data.get("correctOrder") or [])
        ):
            data["sentenceTemplate"] = fallback_template
    merged["data"] = data
    merged["needsConfirmation"] = bool(merged.get("needsConfirmation")) or bool(fallback.get("needsConfirmation"))
    return normalize_question(merged)


def apply_type_hint(parsed, type_hint):
    forced_type = normalize_type_hint(type_hint)
    if not forced_type or not isinstance(parsed, dict):
        return parsed
    if parsed.get("type") == forced_type:
        return parsed

    original_data = parsed.get("data", {})
    if not isinstance(original_data, dict):
        original_data = {}

    remapped = dict(parsed)
    remapped["type"] = forced_type
    remapped["needsConfirmation"] = True

    if forced_type == "reading_choice":
        remapped["data"] = {
            "options": original_data.get("options", parsed.get("options", [])),
            "correctAnswer": original_data.get("correctAnswer") or parsed.get("correctAnswer", ""),
        }
        return remapped

    if forced_type == "build_sentence":
        remapped["article"] = ""
        remapped["prompt"] = (
            as_clean_string(parsed.get("prompt"))
            or as_clean_string(parsed.get("question"))
            or as_clean_string(parsed.get("article"))
            or as_clean_string(original_data.get("prompt"))
        )
        remapped["data"] = {
            "sentenceTemplate": (
                original_data.get("sentenceTemplate")
                or original_data.get("template")
                or parsed.get("sentenceTemplate")
                or parsed.get("template")
                or parsed.get("sentence")
                or ""
            ),
            "wordBank": list_from_any(original_data.get("wordBank") or parsed.get("wordBank") or original_data.get("words") or parsed.get("words")),
            "correctOrder": list_from_any(
                original_data.get("correctOrder")
                or parsed.get("correctOrder")
                or original_data.get("answer")
                or parsed.get("answer")
            ),
            "completeSentence": original_data.get("completeSentence") or parsed.get("completeSentence") or "",
        }
        return remapped

    if forced_type == "complete_words":
        passage = (
            original_data.get("passageText")
            or original_data.get("passage")
            or parsed.get("article")
            or parsed.get("prompt")
            or ""
        )
        remapped["article"] = as_clean_string(passage)
        remapped["prompt"] = as_clean_string(parsed.get("prompt") or parsed.get("question"))
        remapped["data"] = {
            "passageText": passage,
            "blanks": original_data.get("blanks", parsed.get("blanks", [])),
        }
        return remapped

    return remapped


def normalize_question(payload):
    if not isinstance(payload, dict):
        raise ValueError("请求体必须是 JSON 对象")
    qtype = as_clean_string(payload.get("type"))
    raw_data = payload.get("data", {})
    if isinstance(raw_data, str):
        raw_data = json_loads(raw_data, {})
    if not isinstance(raw_data, dict):
        raw_data = {}

    normalized = {
        "type": qtype,
        "title": as_clean_string(payload.get("title")),
        "article": as_clean_string(payload.get("article")),
        "prompt": as_clean_string(payload.get("prompt") or payload.get("question")),
        "explanation": as_clean_string(payload.get("explanation") or payload.get("analysis")),
        "needsConfirmation": bool(payload.get("needsConfirmation") or payload.get("needs_confirmation")),
        "data": {},
    }

    if qtype == "reading_choice":
        normalized["data"] = {
            "options": normalize_options(raw_data.get("options", payload.get("options", []))),
            "correctAnswer": as_clean_string(raw_data.get("correctAnswer") or payload.get("correctAnswer")).upper()[:1],
        }
    elif qtype == "build_sentence":
        normalized["data"] = normalize_build_data(raw_data)
    elif qtype == "complete_words":
        normalized["title"] = ""  # Complete the Words has no title field
        normalized["data"] = normalize_complete_data(raw_data)
        if not normalized["article"] and normalized["data"].get("passageText"):
            normalized["article"] = normalized["data"]["passageText"]
        if not normalized.get("prompt"):
            normalized["prompt"] = "Fill in the missing letters in the paragraph"
    else:
        normalized["data"] = raw_data
    return normalized


def validate_question(question):
    errors = []
    warnings = []
    qtype = question.get("type")
    data = question.get("data") or {}

    if qtype not in ALLOWED_TYPES:
        errors.append("题型必须是 reading_choice、build_sentence 或 complete_words")

    if qtype == "reading_choice":
        if not question.get("article"):
            errors.append("阅读选择题必须填写文章")
        if not question.get("prompt"):
            errors.append("阅读选择题必须填写问题")
        options = data.get("options", [])
        keys = [item.get("key") for item in options if isinstance(item, dict)]
        if len(options) != 4 or keys != ["A", "B", "C", "D"]:
            errors.append("阅读选择题必须有 A/B/C/D 四个选项")
        for item in options:
            if not item.get("text"):
                errors.append(f"选项 {item.get('key', '?')} 不能为空")
        if data.get("correctAnswer") not in {"A", "B", "C", "D"}:
            errors.append("阅读选择题必须填写正确答案 A/B/C/D")

    if qtype == "build_sentence":
        if not question.get("prompt"):
            errors.append("写作造句题必须填写对话或问题提示（提问者问题）")
        template = normalize_sentence_template(data.get("sentenceTemplate", ""))
        word_bank = data.get("wordBank", [])
        correct_order = data.get("correctOrder", [])
        complete_sentence = as_clean_string(data.get("completeSentence", ""))
        if not template:
            errors.append("写作造句题必须填写句子模板（可用 ____ 或 {{blank}} 标记空位，固定词原样保留）")
        if not word_bank:
            errors.append("写作造句题必须填写词库")
        if not correct_order:
            errors.append("写作造句题必须填写正确填入顺序（每个空位对应一个词块）")
        blank_count = count_template_blanks(template)
        if template and blank_count == 0:
            errors.append("句子模板至少需要一个空格标记，例如 {{blank}} 或 ____")
        if blank_count and correct_order and blank_count != len(correct_order):
            errors.append(
                f"句子模板空格数是 {blank_count}，但正确顺序有 {len(correct_order)} 项；二者必须一致"
            )
        if word_bank and correct_order and len(word_bank) < len(correct_order):
            errors.append("词库词块数量不能少于正确顺序数量")
        bank_counts = {}
        for item in word_bank:
            key = item.casefold()
            bank_counts[key] = bank_counts.get(key, 0) + 1
        used_counts = {}
        for item in correct_order:
            key = item.casefold()
            used_counts[key] = used_counts.get(key, 0) + 1
            if used_counts[key] > bank_counts.get(key, 0):
                errors.append(f"正确顺序中的“{item}”不在词库中，或使用次数超过词库数量")
        # Fixed text should not appear as word-bank-only answers
        segments = parse_template_segments(template)
        fixed_chunks = [
            re.sub(r"\s+", " ", seg["text"]).strip(" .,:;!?").casefold()
            for seg in segments
            if seg.get("type") == "fixed"
        ]
        fixed_chunks = [chunk for chunk in fixed_chunks if chunk and len(chunk) > 1]
        for chunk in fixed_chunks:
            if any(tokens_equal(chunk, bank) for bank in word_bank):
                warnings.append(
                    f"固定文本 “{chunk}” 同时出现在词库中；请确认它是否真的是可填词块，而不是题目给定文本"
                )
        if not complete_sentence and correct_order and not errors:
            warnings.append("未填写完整正确句子；系统将根据模板与正确顺序自动生成预览")
        if question.get("needsConfirmation") and not errors:
            warnings.append("题目标记为需要人工确认，请核对句子模板、固定文本与正确顺序后再保存")

    if qtype == "complete_words":
        passage = data.get("passageText", "")
        blanks = data.get("blanks", [])
        if not passage:
            errors.append("阅读填词题必须填写短文")
        # Allow raw underscores; normalize_question already converts them
        marker_ids = re.findall(r"\[\[\s*([A-Za-z0-9_-]+)\s*\]\]", passage)
        underscore_count = len(COMPLETE_UNDERSCORE_RE.findall(passage or ""))
        blank_count = len(blanks)
        if not marker_ids and not underscore_count:
            errors.append("没有识别到任何下划线空格（需要类似 ne__ / civiliza____ 的残缺词）")
        elif not blanks:
            errors.append("阅读填词题必须至少有一个填空")
        if marker_ids and blanks and len(marker_ids) != len(blanks):
            errors.append(
                f"空格数量和答案数量不一致：短文有 {len(marker_ids)} 个空格，答案表有 {len(blanks)} 项"
            )
        blank_ids = [str(blank.get("id")) for blank in blanks]
        missing = [marker for marker in marker_ids if marker not in blank_ids]
        extra = [blank_id for blank_id in blank_ids if blank_id not in marker_ids]
        if missing:
            errors.append("短文中存在没有答案配置的空格：" + "、".join(missing))
        if extra:
            errors.append("答案表中存在没有出现在短文里的空格（不能匹配无下划线的普通单词）")
        for blank in blanks:
            bid = blank.get("id", "?")
            prefix = as_clean_string(blank.get("prefix"))
            answer = as_clean_string(blank.get("answer"))
            full_word = as_clean_string(blank.get("fullWord"))
            if not answer:
                errors.append(f"空格 {bid} 必须填写缺失字母")
            if not full_word and prefix and answer:
                full_word = prefix + answer
            if not full_word:
                errors.append(f"空格 {bid} 缺少完整词")
            if full_word and prefix and not full_word.casefold().startswith(prefix.casefold()):
                errors.append(f"空格 {bid}：完整词“{full_word}”不以前缀“{prefix}”开头")
            elif prefix and answer and full_word:
                expected = prefix + answer
                if not tokens_equal(expected, full_word):
                    errors.append(
                        f"空格 {bid}：前缀“{prefix}”+ 缺失字母“{answer}” ≠ 完整词“{full_word}”"
                    )

    return {"ok": not errors, "errors": list(dict.fromkeys(errors)), "warnings": warnings}


def question_to_row(question, existing_created_at=None):
    timestamp = now_iso()
    title = question.get("title") or (
        ""
        if question.get("type") in {"build_sentence", "complete_words"}
        else TYPE_LABELS.get(question["type"], "题目")
    )
    return {
        "type": question["type"],
        "title": title,
        "article": question.get("article", ""),
        "prompt": question.get("prompt", ""),
        "explanation": question.get("explanation", ""),
        "tags": "[]",
        "data": json.dumps(question.get("data", {}), ensure_ascii=False),
        "needs_confirmation": 1 if question.get("needsConfirmation") else 0,
        "created_at": existing_created_at or timestamp,
        "updated_at": timestamp,
    }


def row_to_question(row, stats=None):
    return {
        "id": row["id"],
        "type": row["type"],
        "title": row["title"],
        "article": row["article"],
        "prompt": row["prompt"],
        "explanation": row["explanation"],
        "data": json_loads(row["data"], {}),
        "needsConfirmation": bool(row["needs_confirmation"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "stats": stats or empty_stats(),
    }


def empty_stats():
    return {"attempts": 0, "correct": 0, "incorrect": 0, "errorRate": 0, "lastPracticedAt": None}


def stats_for_question(db, question_id):
    row = db.execute(
        """
        SELECT
            COUNT(*) AS attempts,
            COALESCE(SUM(is_correct), 0) AS correct,
            COALESCE(SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END), 0) AS incorrect,
            MAX(created_at) AS last_practiced_at
        FROM attempts
        WHERE question_id = ?
        """,
        (question_id,),
    ).fetchone()
    attempts = int(row["attempts"] or 0)
    incorrect = int(row["incorrect"] or 0)
    return {
        "attempts": attempts,
        "correct": int(row["correct"] or 0),
        "incorrect": incorrect,
        "errorRate": round((incorrect / attempts) * 100, 1) if attempts else 0,
        "lastPracticedAt": row["last_practiced_at"],
    }


def question_list_query(args):
    filters = []
    params = []
    qtype = as_clean_string(args.get("type"))
    query = as_clean_string(args.get("q"))
    if qtype:
        filters.append("q.type = ?")
        params.append(qtype)
    if query:
        like = f"%{query}%"
        filters.append("(q.title LIKE ? OR q.article LIKE ? OR q.prompt LIKE ? OR q.data LIKE ?)")
        params.extend([like, like, like, like])
    where = "WHERE " + " AND ".join(filters) if filters else ""
    sort = args.get("sort", "created")
    if sort == "error_rate":
        order_by = "ORDER BY error_rate DESC, attempts DESC, q.updated_at DESC"
    elif sort == "recent_practice":
        order_by = "ORDER BY last_practiced_at IS NULL, last_practiced_at DESC, q.updated_at DESC"
    else:
        order_by = "ORDER BY q.created_at DESC"
    return (
        f"""
        SELECT
            q.*,
            COUNT(a.id) AS attempts,
            COALESCE(SUM(a.is_correct), 0) AS correct,
            COALESCE(SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END), 0) AS incorrect,
            MAX(a.created_at) AS last_practiced_at,
            CASE WHEN COUNT(a.id) = 0 THEN 0
                 ELSE 100.0 * COALESCE(SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END), 0) / COUNT(a.id)
            END AS error_rate
        FROM questions q
        LEFT JOIN attempts a ON a.question_id = q.id
        {where}
        GROUP BY q.id
        {order_by}
        """,
        params,
    )


def endpoint_from_base(base_url):
    url = base_url.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    return url + "/chat/completions"


def extract_json_object(content):
    decoder = json.JSONDecoder()

    def key_value_list_to_dict(items):
        if not items:
            return None
        if len(items) % 2 == 0 and all(isinstance(items[index], str) for index in range(0, len(items), 2)):
            return {items[index]: items[index + 1] for index in range(0, len(items), 2)}
        result = {}
        for item in items:
            if isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[0], str):
                result[item[0]] = item[1]
            elif isinstance(item, dict) and isinstance(item.get("key"), str) and "value" in item:
                result[item["key"]] = item["value"]
            elif isinstance(item, dict) and isinstance(item.get("name"), str) and "value" in item:
                result[item["name"]] = item["value"]
            elif isinstance(item, dict) and isinstance(item.get("field"), str) and "value" in item:
                result[item["field"]] = item["value"]
            else:
                return None
        return result

    def unwrap_candidate(item):
        if not isinstance(item, dict):
            return None
        if item.get("type") in ALLOWED_TYPES:
            return item
        for key in ("question", "draft", "item", "result"):
            nested = item.get(key)
            if isinstance(nested, dict):
                return nested
            if isinstance(nested, (list, str)):
                try:
                    return coerce_payload(nested)
                except ValueError:
                    pass
        for key in ("questions", "items", "results", "output", "parsed", "arguments"):
            nested = item.get(key)
            if isinstance(nested, (dict, list, str)):
                try:
                    return coerce_payload(nested)
                except ValueError:
                    pass
        for key in ("text", "content", "output_text"):
            nested = item.get(key)
            if isinstance(nested, (dict, list, str)):
                try:
                    return coerce_payload(nested)
                except ValueError:
                    pass
        return item

    def candidate_score(item):
        candidate = unwrap_candidate(item)
        if not isinstance(candidate, dict):
            return -1
        score = 0
        if candidate.get("type") in ALLOWED_TYPES:
            score += 10
        if isinstance(candidate.get("data"), dict):
            score += 4
        for key in ("article", "prompt", "question", "title", "explanation"):
            if as_clean_string(candidate.get(key)):
                score += 1
        return score

    def coerce_payload(value):
        if isinstance(value, dict):
            candidate = unwrap_candidate(value)
            if isinstance(candidate, dict):
                return candidate
        if isinstance(value, list):
            mapped = key_value_list_to_dict(value)
            if mapped is not None:
                return coerce_payload(mapped)
            candidates = []
            string_parts = []
            for item in value:
                if isinstance(item, str):
                    string_parts.append(item)
                try:
                    candidate = coerce_payload(item)
                except ValueError:
                    continue
                if isinstance(candidate, dict):
                    candidates.append(candidate)
            if candidates:
                return sorted(candidates, key=candidate_score, reverse=True)[0]
            if string_parts:
                parsed = decode_first_object("\n".join(string_parts))
                if parsed is not None:
                    return parsed
            raise ValueError("LLM 返回的数组里没有可用题目对象")
        if isinstance(value, str):
            if "{" in value or "[" in value:
                parsed = decode_first_object(value)
                if parsed is not None:
                    return parsed
        raise ValueError("LLM JSON 顶层必须是对象")

    def decode_first_object(candidate):
        if not isinstance(candidate, str):
            return coerce_payload(candidate)
        stripped = candidate.strip()
        if not stripped:
            return None
        try:
            value, _ = decoder.raw_decode(stripped)
            return coerce_payload(value)
        except json.JSONDecodeError:
            pass
        for match in re.finditer(r"[\[{]", stripped):
            try:
                value, _ = decoder.raw_decode(stripped[match.start() :])
                return coerce_payload(value)
            except json.JSONDecodeError:
                continue
        return None

    if not isinstance(content, str):
        return coerce_payload(content)

    text = content.strip()
    for fence in re.finditer(r"```(?:json)?\s*(.*?)```", text, flags=re.I | re.S):
        parsed = decode_first_object(fence.group(1))
        if parsed is not None:
            return parsed

    parsed = decode_first_object(text)
    if parsed is not None:
        return parsed

    raise ValueError("LLM 返回内容不是可解析的 JSON")


def llm_system_prompt():
    return """
你是一个托福错题整理助手。你的任务是把用户手动粘贴的题目文本整理成严格 JSON，不能抓取网页，不能补写原文里没有的信息，不能凭空编造答案或解析。

只支持三种 type：
1. reading_choice：阅读选择题。
2. build_sentence：2026 新托福 Build a Sentence。
3. complete_words：2026 新托福 Complete the Words。

输出必须是一个 JSON 对象，不要 Markdown，不要解释。顶层绝对不要使用数组，即使原文很长或包含多个段落，也必须合并进同一个题目对象。字段：
{
  "type": "reading_choice | build_sentence | complete_words",
  "title": "简短题目标题，可为空",
  "article": "阅读文章或短文；Build a Sentence 可为空",
  "prompt": "问题、对话或提示",
  "explanation": "解析；原文没有就留空",
  "needsConfirmation": true/false,
  "data": {}
}

reading_choice 的 data：
{
  "options": [{"key":"A","text":""},{"key":"B","text":""},{"key":"C","text":""},{"key":"D","text":""}],
  "correctAnswer": "A/B/C/D；原文没有明确答案就留空"
}

build_sentence 的 data：
{
  "sentenceTemplate": "句子模板：每个可填空位写成 {{blank}}；题目给定的固定词/短语/标点必须原样保留在模板中，不要放进 wordBank",
  "wordBank": ["用户可选的词或短语，不要包含固定文本"],
  "correctOrder": ["第1个空应填的词块", "第2个空应填的词块"],
  "completeSentence": "填完后的完整正确句子"
}

Build a Sentence 关键规则：
1. 题干不一定是全空格句。固定词/短语/标点可出现在开头、中间、结尾，也可以有多处。
2. 固定文本必须保留在 sentenceTemplate 中。例如：
   原文：_____ _____ _____ _____ _____ during the _____ _____.
   输出：{{blank}} {{blank}} {{blank}} {{blank}} {{blank}} during the {{blank}} {{blank}}.
   其中 “during the” 和句末 “.” 是固定文本。
3. wordBank 只包含用户可点击选择的词块；绝不要把 “during the / because of / as a result of / in order to” 这类已给定固定短语误放进词库（除非原文词库里明确列出）。
4. correctOrder 是每个空位按从左到右的正确词块，长度必须等于 sentenceTemplate 中 {{blank}} 的数量。
5. 若原文给出完整正确答案句子，请用词库词块去匹配该句子，推出 correctOrder，并把未匹配到的部分保留为模板固定文本。
6. 若原文缺少句子模板或正确答案，needsConfirmation=true，对应字段留空；不要凭空补题。
7. 常见固定短语示例（仅当它们在题目中作为给定文本出现时保留为固定文本）：during the, because of, as a result of, in order to, according to。
8. 多词词块（如 public speaking）在 correctOrder 和 wordBank 中应作为单个元素，不要拆开。

示例：
输入含提问者、模板 “_____ _____ _____ _____ _____ during the _____ _____.”、词库与完整正确答案
Their public speaking skills were exceptional during the entire presentation.
则：
{
  "type": "build_sentence",
  "prompt": "What impressed you about the team's presentation yesterday?",
  "data": {
    "sentenceTemplate": "{{blank}} {{blank}} {{blank}} {{blank}} {{blank}} during the {{blank}} {{blank}}.",
    "wordBank": ["presentation","entire","their","exceptional","public speaking","were","skills"],
    "correctOrder": ["their","public speaking","skills","were","exceptional","entire","presentation"],
    "completeSentence": "Their public speaking skills were exceptional during the entire presentation."
  }
}

complete_words 的 data：
{
  "passageText": "短文。每个缺失位置写成 前缀[[序号]]，例如 civiliza[[1]]、sys[[2]]、how[[3]]",
  "blanks": [
    {"id":"1","prefix":"civiliza","answer":"tion","fullWord":"civilization","confirmed":true},
    {"id":"2","prefix":"sys","answer":"tems","fullWord":"systems","confirmed":true}
  ]
}

Complete the Words 关键规则：
1. 不要改写短文内容、标点、大小写和语序；只把空格位置结构化。
2. 原文中的 civiliza____ / ne__ / stand______ 等形式：
   - prefix = 下划线前的可见字母（civiliza / ne / stand）
   - 在 passageText 中写成 civiliza[[1]] 这种标记
3. blanks 按从左到右顺序编号，id 与 [[id]] 一致。
4. answer 是用户需要填写的缺失字母（后缀），不是整个单词。
5. fullWord = prefix + answer。若原文答案给的是完整词（如 civilization），请根据 prefix 自动拆出 answer。
6. 若原文答案编号列表与空格数量不一致，needsConfirmation=true，并尽量保留已识别空格。
7. 不要凭空发明答案；没有答案的空格 answer/fullWord 留空，needsConfirmation=true。
8. 支持答案写成：
   1. tion
   2. tems
   或
   1. civilization
   2. systems

示例：
短文含 civiliza____, sys____, how____ ...
答案：
1. tion
2. tems
3. ever
则 blanks 为：
[
  {"id":"1","prefix":"civiliza","answer":"tion","fullWord":"civilization"},
  {"id":"2","prefix":"sys","answer":"tems","fullWord":"systems"},
  {"id":"3","prefix":"how","answer":"ever","fullWord":"however"}
]

如果原始输入没有明确答案，必须 needsConfirmation=true，并把对应答案字段留空。不要因为常识推断答案。
""".strip()


def parse_with_llm(raw_text, type_hint=""):
    settings = load_llm_settings()
    if not settings["api_key_configured"] or not settings["base_url"] or not settings["model"]:
        return None, ["LLM API 尚未配置完整：需要 API Key、Base URL/请求 URL 和模型名称"]

    url_errors = validate_provider_url(settings["base_url"])
    if url_errors:
        return None, url_errors

    try:
        custom_params = json.loads(settings["custom_params"] or "{}")
        if not isinstance(custom_params, dict):
            raise ValueError
    except ValueError:
        return None, ["自定义参数必须是 JSON 对象"]

    endpoint = endpoint_from_base(settings["base_url"])
    forced_type = normalize_type_hint(type_hint)
    user_message = {
        "typeHint": forced_type or "auto",
        "instruction": (
            f"用户已经明确选择题型 {forced_type}，你必须输出这个 type，不要自动改成其他题型。"
            if forced_type
            else "用户未指定题型，请只在三种题型中选择最匹配的一种。"
        ),
        "rawText": raw_text,
    }
    body = {
        "model": settings["model"],
        "temperature": 0,
        "messages": [
            {"role": "system", "content": llm_system_prompt()},
            {"role": "user", "content": json.dumps(user_message, ensure_ascii=False)},
        ],
    }
    body.update(custom_params)

    request_obj = urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings['api_key']}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=60) as response:
            response_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        safe_body = redact(response_body, [settings["api_key"]])
        return None, [f"LLM 返回 HTTP {exc.code}：{safe_body or '无响应正文'}"]
    except urllib.error.URLError as exc:
        return None, [f"LLM 请求失败：{redact(exc.reason, [settings['api_key']])}"]
    except TimeoutError:
        return None, ["LLM 请求超时"]

    try:
        payload = json.loads(response_body)
        content = payload["choices"][0]["message"]["content"]
        parsed = extract_json_object(content)
        returned_type = parsed.get("type") if isinstance(parsed, dict) else ""
        parsed = apply_type_hint(parsed, forced_type)
        normalized = normalize_question(parsed)
        if forced_type and returned_type and returned_type != forced_type:
            normalized.setdefault("_importWarnings", []).append(
                f"LLM 返回题型 {returned_type}，已按你选择的 {forced_type} 处理"
            )
        return normalized, []
    except Exception as exc:
        return None, [f"LLM 解析结果失败：{redact(exc, [settings['api_key']])}"]


def test_llm_connection(settings):
    body = dict(settings["parsed_params"])
    body.update(
        {
            "model": settings["model"],
            "stream": False,
            "messages": [
                {"role": "system", "content": "Reply with exactly: OK"},
                {"role": "user", "content": "ping"},
            ],
        }
    )
    body.setdefault("temperature", 0)
    if "max_tokens" not in body and "max_completion_tokens" not in body:
        body["max_tokens"] = 16

    request_obj = urllib.request.Request(
        endpoint_from_base(settings["base_url"]),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings['api_key']}",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request_obj, timeout=30) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        safe_body = redact(response_body, [settings["api_key"]])
        return None, [f"LLM 返回 HTTP {exc.code}：{safe_body or '无响应正文'}"]
    except urllib.error.URLError as exc:
        return None, [f"LLM 请求失败：{redact(exc.reason, [settings['api_key']])}"]
    except TimeoutError:
        return None, ["LLM 请求超时"]

    latency_ms = round((time.perf_counter() - started) * 1000)
    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError:
        return None, [f"LLM 返回 HTTP {status}，但响应不是合法 JSON"]

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None, ["LLM 返回了 JSON，但不是标准 Chat Completions 响应：缺少 choices"]

    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    preview = as_clean_string(message.get("content"))[:200]
    return {
        "status": status,
        "latencyMs": latency_ms,
        "responsePreview": preview,
    }, []


def grade_attempt(question, answer):
    data = question["data"]
    if question["type"] == "reading_choice":
        selected = as_clean_string(answer.get("choice")).upper()[:1]
        correct = data.get("correctAnswer")
        return selected == correct, {"selected": selected, "correctAnswer": correct}

    if question["type"] == "build_sentence":
        submitted = [as_clean_string(item) for item in answer.get("order", [])]
        correct_order = [as_clean_string(item) for item in data.get("correctOrder", [])]
        template = normalize_sentence_template(data.get("sentenceTemplate", ""))
        blank_count = count_template_blanks(template) or len(correct_order)
        # Pad / trim submitted to blank count for stable slot grading
        while len(submitted) < blank_count:
            submitted.append("")
        if len(submitted) > blank_count:
            submitted = submitted[:blank_count]
        positions = []
        all_correct = True
        for index in range(blank_count):
            expected = correct_order[index] if index < len(correct_order) else ""
            actual = submitted[index] if index < len(submitted) else ""
            is_correct = bool(expected) and tokens_equal(actual, expected)
            all_correct = all_correct and is_correct
            positions.append(
                {
                    "index": index + 1,
                    "slotId": index + 1,
                    "actual": actual,
                    "expected": expected,
                    "correct": is_correct,
                }
            )
        if blank_count == 0 or len(correct_order) != blank_count:
            all_correct = False
        complete_sentence = as_clean_string(data.get("completeSentence")) or render_sentence_from_template(
            template, correct_order
        )
        submitted_sentence = render_sentence_from_template(template, submitted)
        return all_correct, {
            "submitted": submitted,
            "correctOrder": correct_order,
            "positions": positions,
            "completeSentence": complete_sentence,
            "submittedSentence": submitted_sentence,
            "sentenceTemplate": template,
        }

    if question["type"] == "complete_words":
        submitted = answer.get("blanks", {}) if isinstance(answer.get("blanks"), dict) else {}
        blanks = []
        all_correct = True
        for blank in data.get("blanks", []):
            blank_id = str(blank["id"])
            actual = as_clean_string(submitted.get(blank_id) if blank_id in submitted else submitted.get(blank["id"]))
            expected = as_clean_string(blank.get("answer"))
            is_correct = tokens_equal(actual, expected) if expected else False
            all_correct = all_correct and is_correct
            blanks.append(
                {
                    "id": blank_id,
                    "prefix": blank.get("prefix", ""),
                    "actual": actual,
                    "expected": expected,
                    "fullWord": blank.get("fullWord", ""),
                    "correct": is_correct,
                }
            )
        complete_passage = as_clean_string(data.get("completePassage")) or render_complete_passage(
            data.get("passageText", ""), data.get("blanks", [])
        )
        # Build user passage with their answers
        user_blanks = []
        for blank in data.get("blanks", []):
            bid = str(blank["id"])
            actual = as_clean_string(submitted.get(bid) if bid in submitted else submitted.get(blank["id"]))
            user_blanks.append(
                {
                    **blank,
                    "answer": actual,
                    "fullWord": f"{as_clean_string(blank.get('prefix'))}{actual}" if actual else "",
                }
            )
        submitted_passage = render_complete_passage(data.get("passageText", ""), user_blanks)
        return all_correct, {
            "blanks": blanks,
            "completePassage": complete_passage,
            "submittedPassage": submitted_passage,
        }

    return False, {"error": "unsupported type"}


@app.before_request
def require_auth():
    path = request.path
    # 静态资源、首页、健康检查、认证端点一律放行
    if path == "/" or path.startswith("/static/") or path in AUTH_EXEMPT_EXACT or path.startswith("/api/auth/"):
        return None
    with get_db() as db:
        if not auth_configured(db):
            return None  # 未配置凭据，保持开放
    if is_authed():
        return None
    return jsonify({"error": "未登录或会话已过期", "authRequired": True}), 401


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "请求体过大"}), 413


@app.errorhandler(Exception)
def handle_error(exc):
    status = getattr(exc, "code", 500)
    message = "服务器内部错误" if status == 500 else str(exc)
    return jsonify({"error": redact(message)}), status


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/static/<path:path>")
def static_files(path):
    return send_from_directory(app.static_folder, path)


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "time": int(time.time())})


@app.get("/api/auth/status")
def auth_status():
    with get_db() as db:
        configured = auth_configured(db)
    return jsonify({
        "authRequired": configured,
        "authed": is_authed() if configured else True,
        "username": session.get("username") if is_authed() else None,
    })


@app.post("/api/auth/login")
def auth_login():
    payload = request.get_json(force=True, silent=True) or {}
    username = as_clean_string(payload.get("username"))
    password = payload.get("password", "")
    if not isinstance(password, str):
        return jsonify({"error": "用户名或密码错误"}), 401
    with get_db() as db:
        if not auth_configured(db):
            return jsonify({"error": "尚未配置登录认证"}), 400
        stored_user = get_setting(db, "auth_username", "")
        stored_hash = get_setting(db, "auth_password_hash", "")
    if not hmac.compare_digest(username, stored_user) or not verify_password(password, stored_hash):
        return jsonify({"error": "用户名或密码错误"}), 401
    session.permanent = True
    session["authed_at"] = time.time()
    session["username"] = username
    return jsonify({"ok": True, "username": username})


@app.post("/api/auth/logout")
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/settings")
def get_settings():
    with get_db() as db:
        encrypted = get_setting(db, "api_key_encrypted", "")
        return jsonify(
            {
                "apiKeyConfigured": bool(encrypted),
                "baseUrl": get_setting(db, "base_url", ""),
                "model": get_setting(db, "model", ""),
                "customParams": get_setting(db, "custom_params", "{}"),
            }
        )


@app.post("/api/settings")
def save_settings():
    payload = request.get_json(force=True, silent=True) or {}
    api_key = as_clean_string(payload.get("apiKey"))
    clear_api_key = bool(payload.get("clearApiKey"))
    base_url = as_clean_string(payload.get("baseUrl"))
    model = as_clean_string(payload.get("model"))
    custom_params = as_clean_string(payload.get("customParams") or "{}")
    errors = []
    if base_url:
        errors.extend(validate_provider_url(base_url))
    if custom_params:
        _, param_errors = parse_custom_params(custom_params)
        errors.extend(param_errors)
    if errors:
        return jsonify({"error": "设置校验失败", "details": errors}), 400
    with get_db() as db:
        if clear_api_key:
            db.execute("DELETE FROM settings WHERE key = ?", ("api_key_encrypted",))
        elif api_key:
            set_setting(db, "api_key_encrypted", encrypt_secret(api_key))
        set_setting(db, "base_url", base_url)
        set_setting(db, "model", model)
        set_setting(db, "custom_params", custom_params or "{}")
        db.commit()
    return jsonify({"ok": True, "apiKeyConfigured": bool(api_key) or load_llm_settings()["api_key_configured"]})


@app.post("/api/settings/test")
def test_settings():
    payload = request.get_json(force=True, silent=True) or {}
    settings, errors = llm_settings_from_payload(payload, allow_saved_key=True)
    if errors:
        return jsonify({"error": "设置校验失败", "details": errors}), 400
    result, test_errors = test_llm_connection(settings)
    if test_errors:
        return jsonify({"error": "连接测试失败", "details": test_errors}), 502
    return jsonify({"ok": True, **result})


@app.get("/api/settings/auth")
def get_auth_settings():
    with get_db() as db:
        username = get_setting(db, "auth_username", "")
        return jsonify({
            "configured": auth_configured(db),
            "username": username,
        })


@app.post("/api/settings/auth")
def save_auth_settings():
    payload = request.get_json(force=True, silent=True) or {}
    username = as_clean_string(payload.get("username"))
    password = payload.get("password", "")
    clear_auth = bool(payload.get("clearAuth"))
    if not isinstance(password, str):
        password = ""
    errors = []
    if not clear_auth:
        if not username:
            errors.append("用户名不能为空")
        if not password:
            errors.append("密码不能为空")
    if errors:
        return jsonify({"error": "认证设置校验失败", "details": errors}), 400
    with get_db() as db:
        if clear_auth:
            db.execute("DELETE FROM settings WHERE key IN (?, ?)", ("auth_username", "auth_password_hash"))
            db.commit()
            session.clear()
            return jsonify({"ok": True, "configured": False})
        set_setting(db, "auth_username", username)
        set_setting(db, "auth_password_hash", hash_password(password))
        db.commit()
    session.permanent = True
    session["authed_at"] = time.time()
    session["username"] = username
    return jsonify({"ok": True, "configured": True, "username": username})


@app.post("/api/import/parse")
def import_parse():
    payload = request.get_json(force=True, silent=True) or {}
    raw_text = as_clean_string(payload.get("rawText"))
    type_hint = as_clean_string(payload.get("typeHint"))
    if not raw_text:
        return jsonify({"error": "请先粘贴题目原文"}), 400
    if len(raw_text) > MAX_RAW_IMPORT_CHARS:
        return jsonify({"error": f"题目原文过长，当前上限 {MAX_RAW_IMPORT_CHARS} 字符"}), 400

    forced_type = normalize_type_hint(type_hint)

    # Reading fill-in: deterministic local parse only — never LLM rewrite of the passage
    if forced_type == "complete_words" or (
        not forced_type and looks_like_complete_words_raw(raw_text) and not looks_like_build_sentence_raw(raw_text)
    ):
        draft = parse_structured_complete_words(raw_text)
        if not draft:
            draft = parse_structured_complete_words(
                f"短文：\n{raw_text}"
            )
        if not draft:
            return jsonify({"error": "无法解析阅读填词题：请提供带下划线空格的短文和答案"}), 400
        parse_errors = draft.pop("_parseErrors", []) if isinstance(draft, dict) else []
        draft = normalize_question(draft)
        draft["title"] = ""
        draft["needsConfirmation"] = False
        validation = validate_question(draft)
        if parse_errors:
            validation["errors"] = list(dict.fromkeys(parse_errors + validation.get("errors", [])))
            validation["ok"] = False
        # Single error block only — no soft warnings for this type
        validation["warnings"] = []
        return jsonify({"rawText": raw_text, "draft": draft, "validation": validation})

    use_build_structured = forced_type == "build_sentence" or (
        not forced_type and looks_like_build_sentence_raw(raw_text)
    )

    structured_draft = None
    if use_build_structured or forced_type == "build_sentence":
        structured_draft = parse_structured_build_sentence(raw_text)

    # Prefer deterministic structured parse when it fully validates
    if structured_draft:
        structured_validation = validate_question(structured_draft)
        if structured_validation["ok"] and not structured_draft.get("needsConfirmation"):
            return jsonify(
                {"rawText": raw_text, "draft": structured_draft, "validation": structured_validation}
            )
        if structured_validation["ok"]:
            return jsonify(
                {"rawText": raw_text, "draft": structured_draft, "validation": structured_validation}
            )

    llm_hint = type_hint
    if not llm_hint and use_build_structured:
        llm_hint = "build_sentence"

    draft, errors = parse_with_llm(raw_text, llm_hint)
    if errors:
        if structured_draft:
            validation = validate_question(structured_draft)
            validation["warnings"] = [
                "LLM 解析失败，已回退到本地结构化识别结果，请人工确认。"
            ] + validation.get("warnings", [])
            return jsonify({"rawText": raw_text, "draft": structured_draft, "validation": validation})
        return jsonify({"error": "解析失败", "details": errors, "rawText": raw_text}), 502

    if structured_draft:
        if structured_draft.get("type") == "build_sentence" or draft.get("type") == "build_sentence":
            draft = merge_build_sentence_draft(draft, structured_draft)

    # Re-normalize so internal markers / prefixes stay consistent
    if draft and draft.get("type") == "build_sentence":
        draft = normalize_question(draft)
        data = draft.get("data") or {}
        if not as_clean_string(data.get("sentenceTemplate")) or not data.get("correctOrder"):
            draft["needsConfirmation"] = True
        elif count_template_blanks(data.get("sentenceTemplate")) != len(data.get("correctOrder") or []):
            draft["needsConfirmation"] = True
    if draft and draft.get("type") == "complete_words":
        # Even if LLM returned this type unexpectedly, re-run local underscore rules on its passage
        data = draft.get("data") or {}
        passage = as_clean_string(data.get("passageText") or draft.get("article") or "")
        answer_values = [as_clean_string(b.get("answer") or b.get("fullWord")) for b in (data.get("blanks") or [])]
        if not answer_values and isinstance(data.get("answers"), list):
            answer_values = [as_clean_string(v) for v in data.get("answers")]
        matched = match_answers_to_underscore_blanks(passage, answer_values)
        draft = normalize_question(
            {
                **draft,
                "type": "complete_words",
                "title": "",
                "article": matched["passageText"],
                "needsConfirmation": False,
                "data": {
                    "passageText": matched["passageText"],
                    "blanks": matched["blanks"],
                },
            }
        )
        validation = validate_question(draft)
        parse_errors = matched.get("errors") or []
        if parse_errors:
            validation["errors"] = list(dict.fromkeys(parse_errors + validation.get("errors", [])))
            validation["ok"] = False
        validation["warnings"] = []
        return jsonify({"rawText": raw_text, "draft": draft, "validation": validation})

    validation = validate_question(draft)
    import_warnings = draft.pop("_importWarnings", []) if isinstance(draft, dict) else []
    if import_warnings:
        validation["warnings"] = import_warnings + validation.get("warnings", [])
    if draft and draft.get("needsConfirmation") and validation.get("ok"):
        validation["warnings"] = [
            "题目需要人工确认：请核对句子模板、固定文本、词库与正确顺序。"
        ] + validation.get("warnings", [])
    return jsonify({"rawText": raw_text, "draft": draft, "validation": validation})


@app.get("/api/questions")
def list_questions():
    sql, params = question_list_query(request.args)
    with get_db() as db:
        rows = db.execute(sql, params).fetchall()
    items = []
    for row in rows:
        attempts = int(row["attempts"] or 0)
        incorrect = int(row["incorrect"] or 0)
        stats = {
            "attempts": attempts,
            "correct": int(row["correct"] or 0),
            "incorrect": incorrect,
            "errorRate": round((incorrect / attempts) * 100, 1) if attempts else 0,
            "lastPracticedAt": row["last_practiced_at"],
        }
        items.append(row_to_question(row, stats))
    return jsonify({"items": items})


@app.get("/api/questions/<int:question_id>")
def get_question(question_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if not row:
            return jsonify({"error": "题目不存在"}), 404
        return jsonify(row_to_question(row, stats_for_question(db, question_id)))


@app.post("/api/questions")
def create_question():
    payload = request.get_json(force=True, silent=True) or {}
    question = normalize_question(payload)
    validation = validate_question(question)
    if not validation["ok"]:
        return jsonify({"error": "题目结构校验失败", "validation": validation}), 400
    row = question_to_row(question)
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO questions(type, title, article, prompt, explanation, tags, data, needs_confirmation, created_at, updated_at)
            VALUES(:type, :title, :article, :prompt, :explanation, :tags, :data, :needs_confirmation, :created_at, :updated_at)
            """,
            row,
        )
        db.commit()
        created = db.execute("SELECT * FROM questions WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify(row_to_question(created, empty_stats())), 201


@app.put("/api/questions/<int:question_id>")
def update_question(question_id):
    payload = request.get_json(force=True, silent=True) or {}
    question = normalize_question(payload)
    validation = validate_question(question)
    if not validation["ok"]:
        return jsonify({"error": "题目结构校验失败", "validation": validation}), 400
    with get_db() as db:
        existing = db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if not existing:
            return jsonify({"error": "题目不存在"}), 404
        row = question_to_row(question, existing["created_at"])
        db.execute(
            """
            UPDATE questions
            SET type = :type,
                title = :title,
                article = :article,
                prompt = :prompt,
                explanation = :explanation,
                tags = :tags,
                data = :data,
                needs_confirmation = :needs_confirmation,
                updated_at = :updated_at
            WHERE id = :id
            """,
            {**row, "id": question_id},
        )
        db.commit()
        updated = db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        return jsonify(row_to_question(updated, stats_for_question(db, question_id)))


@app.delete("/api/questions/<int:question_id>")
def delete_question(question_id):
    with get_db() as db:
        cursor = db.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        db.commit()
    if cursor.rowcount == 0:
        return jsonify({"error": "题目不存在"}), 404
    return jsonify({"ok": True})


@app.get("/api/practice/next")
def practice_next():
    mode = request.args.get("mode", "random")
    qtype = as_clean_string(request.args.get("type"))
    filters = []
    params = []
    if qtype:
        filters.append("q.type = ?")
        params.append(qtype)
    where = "WHERE " + " AND ".join(filters) if filters else ""
    having = ""
    order = "ORDER BY RANDOM()"
    if mode == "wrong":
        having = "HAVING incorrect > 0"
        order = "ORDER BY last_practiced_at IS NULL, last_practiced_at ASC, RANDOM()"
    elif mode == "high_error":
        having = "HAVING attempts > 0"
        order = "ORDER BY error_rate DESC, incorrect DESC, RANDOM()"
    sql = f"""
        SELECT
            q.*,
            COUNT(a.id) AS attempts,
            COALESCE(SUM(a.is_correct), 0) AS correct,
            COALESCE(SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END), 0) AS incorrect,
            MAX(a.created_at) AS last_practiced_at,
            CASE WHEN COUNT(a.id) = 0 THEN 0
                 ELSE 100.0 * COALESCE(SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END), 0) / COUNT(a.id)
            END AS error_rate
        FROM questions q
        LEFT JOIN attempts a ON a.question_id = q.id
        {where}
        GROUP BY q.id
        {having}
        {order}
        LIMIT 1
    """
    with get_db() as db:
        row = db.execute(sql, params).fetchone()
    if not row:
        return jsonify({"error": "没有符合条件的题目"}), 404
    attempts = int(row["attempts"] or 0)
    incorrect = int(row["incorrect"] or 0)
    stats = {
        "attempts": attempts,
        "correct": int(row["correct"] or 0),
        "incorrect": incorrect,
        "errorRate": round((incorrect / attempts) * 100, 1) if attempts else 0,
        "lastPracticedAt": row["last_practiced_at"],
    }
    return jsonify(row_to_question(row, stats))


@app.post("/api/questions/<int:question_id>/attempts")
def submit_attempt(question_id):
    payload = request.get_json(force=True, silent=True) or {}
    answer = payload.get("answer", {})
    if not isinstance(answer, dict):
        return jsonify({"error": "答案必须是 JSON 对象"}), 400
    with get_db() as db:
        row = db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if not row:
            return jsonify({"error": "题目不存在"}), 404
        question = row_to_question(row)
        is_correct, detail = grade_attempt(question, answer)
        db.execute(
            """
            INSERT INTO attempts(question_id, answer, is_correct, detail, created_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                question_id,
                json.dumps(answer, ensure_ascii=False),
                1 if is_correct else 0,
                json.dumps(detail, ensure_ascii=False),
                now_iso(),
            ),
        )
        db.commit()
        stats = stats_for_question(db, question_id)
    return jsonify({"isCorrect": is_correct, "detail": detail, "stats": stats})


init_db()
