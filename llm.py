"""LLM settings, SSRF-safe provider URLs, and Chat Completions calls."""
from __future__ import annotations

import ipaddress
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from db import get_db, get_setting
from parsing import (
    apply_type_hint,
    as_clean_string,
    extract_json_object,
    normalize_question,
    normalize_type_hint,
)
from security import decrypt_secret, redact

# Must stay well below gunicorn worker timeout (default 30s; Dockerfile uses 90s).
# If the LLM hangs, urllib must raise first so parse_import can fall back to local
# parsing instead of gunicorn aborting the worker with SystemExit → HTTP 500.
LLM_REQUEST_TIMEOUT_SECONDS = 20


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


def _ip_is_blocked_for_ssrf(ip):
    """True if an IP must not be used as an LLM provider target (SSRF guard)."""
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )


def validate_resolved_host(host):
    """
    Resolve host via DNS (all A/AAAA results) and reject private / loopback /
    link-local / reserved / multicast addresses. DNS failure is a hard error
    (never silently allow). Used at settings-save time and again immediately
    before every outbound LLM HTTP request to mitigate DNS rebinding.
    """
    host = as_clean_string(host)
    if not host:
        return ["Base URL 主机名无效，无法解析"]

    try:
        # family=AF_UNSPEC: both IPv4 and IPv6. type=SOCK_STREAM: TCP endpoints.
        addrinfo = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        return [f"无法解析 Base URL 主机名“{host}”：{exc}"]
    except OSError as exc:
        return [f"无法解析 Base URL 主机名“{host}”：{exc}"]

    if not addrinfo:
        return [f"无法解析 Base URL 主机名“{host}”：DNS 返回空结果"]

    blocked = []
    seen = set()
    for _family, _type, _proto, _canonname, sockaddr in addrinfo:
        # sockaddr[0] is the IP string for both IPv4 and IPv6
        ip_str = sockaddr[0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return [f"Base URL 主机名“{host}”解析到无法识别的地址：{ip_str}"]
        # Treat IPv4-mapped IPv6 (::ffff:x.x.x.x) as the underlying IPv4
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if _ip_is_blocked_for_ssrf(ip):
            blocked.append(str(ip))

    if blocked:
        # Deduplicate while preserving order
        unique_blocked = list(dict.fromkeys(blocked))
        return [
            "Base URL 不能指向内网、本机、链路本地或保留地址"
            f"（“{host}” 解析到：{', '.join(unique_blocked)}）"
        ]
    return []


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

    # SSRF: resolve every A/AAAA record for the host; reject if any is non-public.
    # Skip when scheme/netloc already invalid (no usable host).
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        host = parsed.hostname
        if not host:
            errors.append("Base URL 或完整请求 URL 必须包含有效主机名")
        else:
            errors.extend(validate_resolved_host(host))
    return errors



def endpoint_from_base(base_url):
    url = base_url.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    return url + "/chat/completions"



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
当输入使用“问题与选项”字段时，字段开头是 prompt，随后 A/B/C/D 四行必须拆分到 data.options；不要把选项文本并入 prompt。

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


def call_llm(raw_text, type_hint=""):
    """
    Send raw text to the configured LLM and return the parsed JSON object.

    This is the LLM call only — it does NOT apply type-locking, normalization, or
    validation. The import pipeline (import_pipeline.parse_import) is responsible
    for converting the raw JSON into a typed draft. Returns (parsed_dict, errors).
    parsed_dict is None when the request fails or the response is not valid JSON.
    """
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
        with urllib.request.urlopen(request_obj, timeout=LLM_REQUEST_TIMEOUT_SECONDS) as response:
            response_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        safe_body = redact(response_body, [settings["api_key"]])
        return None, [f"LLM 返回 HTTP {exc.code}：{safe_body or '无响应正文'}"]
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        # socket.timeout is a subclass of OSError/TimeoutError on modern Python;
        # also treat nested timeout reasons as request timeout.
        if isinstance(reason, TimeoutError) or isinstance(exc, TimeoutError):
            return None, ["LLM 请求超时"]
        return None, [f"LLM 请求失败：{redact(reason, [settings['api_key']])}"]
    except TimeoutError:
        return None, ["LLM 请求超时"]
    except OSError as exc:
        # Covers residual socket/ssl timeouts not wrapped as URLError.
        if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower():
            return None, ["LLM 请求超时"]
        return None, [f"LLM 请求失败：{redact(exc, [settings['api_key']])}"]
    except Exception as exc:
        # Never let unexpected network errors escape — local fallback must run.
        return None, [f"LLM 请求失败：{redact(exc, [settings['api_key']])}"]

    try:
        payload = json.loads(response_body)
        content = payload["choices"][0]["message"]["content"]
        parsed = extract_json_object(content)
        # extract_json_object raises on unusable top-level shapes; None is also a failure.
        if parsed is None:
            return None, ["LLM 返回了无法解析的内容（null 或空）"]
        return parsed, []
    except Exception as exc:
        return None, [f"LLM 解析结果失败：{redact(exc, [settings['api_key']])}"]


def parse_with_llm(raw_text, type_hint=""):
    """
    Legacy thin wrapper: call_llm + lock type + normalize.

    Kept for backwards compatibility with app re-exports. New import flow should
    use import_pipeline.parse_import, which runs the full LLM-first pipeline with
    local fallback and per-type merging.
    """
    parsed, errors = call_llm(raw_text, type_hint)
    if errors:
        return None, errors
    forced_type = normalize_type_hint(type_hint)
    returned_type = parsed.get("type") if isinstance(parsed, dict) else ""
    parsed = apply_type_hint(parsed, forced_type)
    normalized = normalize_question(parsed)
    if forced_type and returned_type and returned_type != forced_type:
        normalized.setdefault("_importWarnings", []).append(
            f"LLM 返回题型 {returned_type}，已按你选择的 {forced_type} 处理"
        )
    return normalized, []


def test_llm_connection(settings):
    # Re-validate at request time (DNS rebinding: save-time check is not enough)
    url_errors = validate_provider_url(settings["base_url"])
    if url_errors:
        return None, url_errors

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
