"""
API-level regression for /api/import/parse.

Covers:
- complete_words local fallback → 200 + draft
- unusable local input → structured JSON 400 (never HTML)
- unexpected exceptions → structured JSON 500 (never HTML)
- frontend api.js must not surface raw HTML error bodies
"""
from __future__ import annotations

from pathlib import Path

import import_pipeline

ROOT = Path(__file__).resolve().parents[1]

TRADE_RAW = (
    "题目/原始短文：\n"
    "Trade in the ancient Middle East played a crucial role in the development of "
    "civilizations. Merchants exc______ goods such as tex____, spices, and met___ "
    "across vast dis______.\n\n"
    "答案：\n"
    "1. hanged\n"
    "2. tiles\n"
    "3. als\n"
    "4. tances\n\n"
    "解析：\n"
    "test analysis"
)

BUILD_RAW = (
    "提问者：What did Maria do?\n"
    "题目详情：____ went to the ____.\n"
    "待选词：Maria, store, John, park\n"
    "正确答案：Maria, store\n"
    "解析：Match the subject and destination."
)

READING_COMBINED_RAW = (
    "标题：Weather Announcement\n"
    "文章：Classes will move online because severe weather is expected.\n"
    "问题与选项：\n"
    "What is the main purpose of the announcement?\n\n"
    "A. To describe a forecasting system.\n"
    "B. To announce that on-campus classes are canceled.\n"
    "C. To advertise optional online classes.\n"
    "D. To explain a permanent schedule change.\n"
    "正确答案：B\n"
    "解析：The announcement changes classes because of severe weather."
)


def _mock_llm(monkeypatch, parsed=None, errors=None):
    monkeypatch.setattr(
        import_pipeline, "call_llm", lambda raw, t: (parsed, errors or ["mock down"])
    )


def test_complete_words_local_fallback_returns_200(client, monkeypatch):
    _mock_llm(monkeypatch, None, ["LLM 请求超时"])
    resp = client.post(
        "/api/import/parse",
        json={"rawText": TRADE_RAW, "typeHint": "complete_words"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.content_type.startswith("application/json")
    body = resp.get_json()
    assert body["draft"]["type"] == "complete_words"
    blanks = body["draft"]["data"]["blanks"]
    assert len(blanks) == 4
    assert blanks[0]["fullWord"] == "exchanged"
    assert blanks[3]["fullWord"] == "distances"
    assert body["validation"]["ok"] is True
    assert any("LLM" in w for w in body["validation"]["warnings"])


def test_complete_words_no_blanks_returns_json_400(client, monkeypatch):
    _mock_llm(monkeypatch, None, ["down"])
    raw = "题目/原始短文：\nNo underscores here at all.\n\n答案：\n1. foo"
    resp = client.post(
        "/api/import/parse",
        json={"rawText": raw, "typeHint": "complete_words"},
    )
    assert resp.status_code == 400
    assert resp.content_type.startswith("application/json")
    body = resp.get_json()
    assert body["error"]
    assert isinstance(body.get("details"), list)
    assert "rawText" in body
    # Must not be HTML
    text = resp.get_data(as_text=True)
    assert "<html" not in text.lower()
    assert "<!doctype" not in text.lower()


def test_any_error_is_json_not_html(client, monkeypatch):
    def explode(*_a, **_k):
        raise RuntimeError("boom for test")

    # Force parse_import to raise past its safety net by patching the public entry
    monkeypatch.setattr(import_pipeline, "parse_import", explode)
    # import_api imports parse_import by name — patch the blueprint binding too
    import blueprints.import_api as import_api_mod

    monkeypatch.setattr(import_api_mod, "parse_import", explode)

    resp = client.post(
        "/api/import/parse",
        json={"rawText": TRADE_RAW, "typeHint": "complete_words"},
    )
    assert resp.status_code == 500
    assert resp.content_type.startswith("application/json")
    body = resp.get_json()
    assert body["error"] == "解析失败"
    assert body["details"]
    text = resp.get_data(as_text=True)
    assert "<html" not in text.lower()
    assert "Traceback" not in text
    assert "boom for test" not in text  # no internal leak


def test_empty_raw_text_json_400(client):
    resp = client.post("/api/import/parse", json={"rawText": "", "typeHint": "complete_words"})
    assert resp.status_code == 400
    assert resp.content_type.startswith("application/json")
    body = resp.get_json()
    assert "error" in body


def test_trade_example_can_be_saved(client, monkeypatch):
    _mock_llm(monkeypatch, None, ["LLM 请求超时"])
    parsed = client.post(
        "/api/import/parse",
        json={"rawText": TRADE_RAW, "typeHint": "complete_words"},
    )
    assert parsed.status_code == 200
    draft = parsed.get_json()["draft"]
    save = client.post("/api/questions", json=draft)
    assert save.status_code == 201, save.get_json()
    saved = save.get_json()
    assert saved["type"] == "complete_words"
    assert len(saved["data"]["blanks"]) == 4


def test_valid_llm_build_draft_becomes_confirmed_when_saved(client, monkeypatch):
    _mock_llm(
        monkeypatch,
        {
            "type": "build_sentence",
            "prompt": "What did Maria do?",
            "explanation": "LLM result",
            "needsConfirmation": True,
            "data": {
                "sentenceTemplate": "{{blank}} went to the {{blank}}.",
                "wordBank": ["Maria", "store", "John", "park"],
                "correctOrder": ["Maria", "store"],
                "completeSentence": "Maria went to the store.",
            },
        },
    )
    parsed = client.post(
        "/api/import/parse",
        json={"rawText": BUILD_RAW, "typeHint": "build_sentence"},
    )
    assert parsed.status_code == 200, parsed.get_json()
    draft = parsed.get_json()["draft"]
    save = client.post("/api/questions", json=draft)
    assert save.status_code == 201, save.get_json()
    assert save.get_json()["needsConfirmation"] is False


def test_local_fallback_build_draft_becomes_confirmed_when_saved(client, monkeypatch):
    _mock_llm(monkeypatch, None, ["LLM 请求超时"])
    parsed = client.post(
        "/api/import/parse",
        json={"rawText": BUILD_RAW, "typeHint": "build_sentence"},
    )
    assert parsed.status_code == 200, parsed.get_json()
    body = parsed.get_json()
    assert body["validation"]["ok"] is True
    assert any("本地" in warning for warning in body["validation"]["warnings"])
    save = client.post("/api/questions", json=body["draft"])
    assert save.status_code == 201, save.get_json()
    assert save.get_json()["needsConfirmation"] is False


def test_combined_reading_local_fallback_preserves_all_fields_on_save(client, monkeypatch):
    _mock_llm(monkeypatch, None, ["LLM 请求超时"])
    parsed = client.post(
        "/api/import/parse",
        json={"rawText": READING_COMBINED_RAW, "typeHint": "reading_choice"},
    )
    assert parsed.status_code == 200, parsed.get_json()
    draft = parsed.get_json()["draft"]
    save = client.post("/api/questions", json=draft)
    assert save.status_code == 201, save.get_json()
    saved = save.get_json()
    assert saved["title"] == "Weather Announcement"
    assert saved["article"].startswith("Classes will move online")
    assert saved["prompt"] == "What is the main purpose of the announcement?"
    assert [item["key"] for item in saved["data"]["options"]] == ["A", "B", "C", "D"]
    assert saved["data"]["correctAnswer"] == "B"
    assert saved["explanation"].startswith("The announcement")


def test_combined_reading_valid_llm_result_preserves_all_fields_on_save(client, monkeypatch):
    llm_question = {
        "type": "reading_choice",
        "title": "Weather Announcement",
        "article": "Classes will move online because severe weather is expected.",
        "prompt": "What is the main purpose of the announcement?",
        "explanation": "The announcement changes classes because of severe weather.",
        "data": {
            "options": [
                {"key": "A", "text": "To describe a forecasting system."},
                {"key": "B", "text": "To announce that on-campus classes are canceled."},
                {"key": "C", "text": "To advertise optional online classes."},
                {"key": "D", "text": "To explain a permanent schedule change."},
            ],
            "correctAnswer": "B",
        },
    }
    _mock_llm(monkeypatch, llm_question)
    parsed = client.post(
        "/api/import/parse",
        json={"rawText": READING_COMBINED_RAW, "typeHint": "reading_choice"},
    )
    assert parsed.status_code == 200, parsed.get_json()
    save = client.post("/api/questions", json=parsed.get_json()["draft"])
    assert save.status_code == 201, save.get_json()
    saved = save.get_json()
    assert saved["prompt"] == llm_question["prompt"]
    assert saved["data"] == llm_question["data"]
    assert saved["explanation"] == llm_question["explanation"]


def test_global_error_handler_returns_json(client, monkeypatch):
    """Unhandled exceptions elsewhere also must not yield HTML."""
    from flask import Flask

    # Invoke the registered Exception handler directly with a synthetic error
    handlers = client.application.error_handler_spec.get(None, {})
    # Flask stores handlers as {code_or_exc: {exc_class: handler}}
    handler = None
    for key, mapping in (client.application.error_handler_spec or {}).items():
        if mapping and Exception in mapping:
            handler = mapping[Exception]
            break
        if mapping:
            for exc_cls, fn in mapping.items():
                if exc_cls is Exception or (isinstance(exc_cls, type) and issubclass(Exception, exc_cls)):
                    handler = fn
                    break
    # Fallback: call through a one-off test app path registered before first request
    # by using the already-registered import_api explosion path (covered above).
    # Here we also hit a 404 JSON path and a bare 500 via abort.
    from werkzeug.exceptions import InternalServerError

    # Manually call handle_error by raising inside a request context via test client
    # using an undefined method that triggers 405 JSON
    resp = client.open("/api/health", method="TRACE")
    # TRACE may be 405 or 404 depending on werkzeug; either must be JSON
    assert resp.status_code in (404, 405, 501)
    if resp.status_code in (404, 405):
        assert resp.content_type.startswith("application/json")
        text = resp.get_data(as_text=True)
        assert "<html" not in text.lower()

    # Force the Exception handler by posting malformed content that still hits a view
    # that raises: monkeypatch health to raise
    import app as app_module

    def raise_secret():
        raise RuntimeError("secret path /tmp/x and key sk-test")

    # Replace health view function
    original = client.application.view_functions.get("health")
    client.application.view_functions["health"] = lambda: raise_secret()
    try:
        resp = client.get("/api/health")
    finally:
        if original is not None:
            client.application.view_functions["health"] = original

    assert resp.status_code == 500
    assert resp.content_type.startswith("application/json")
    body = resp.get_json()
    assert body["error"] == "服务器内部错误"
    text = resp.get_data(as_text=True)
    assert "<html" not in text.lower()
    assert "secret path" not in text
    assert "sk-test" not in text


# ---------------------------------------------------------------------------
# Frontend static guards
# ---------------------------------------------------------------------------


def test_api_js_does_not_assign_raw_html_as_error():
    src = (ROOT / "static" / "js" / "api.js").read_text(encoding="utf-8")
    assert "parseResponseBody" in src
    assert "looksLikeHtml" in src
    assert "服务器解析失败，请查看服务日志" in src
    # Old bug: data = { error: text } put entire HTML into message
    assert "data = { error: text || response.statusText }" not in src


def test_import_view_preserves_fields_on_error():
    src = (ROOT / "static" / "js" / "views" / "import_view.js").read_text(encoding="utf-8")
    assert "preservedCompleteFields" in src
    assert "preservedRaw" in src
    # errorHtml still escapes — never inject server HTML
    assert "escapeHtml(error.message" in src


def test_import_view_error_html_uses_escape():
    src = (ROOT / "static" / "js" / "views" / "import_view.js").read_text(encoding="utf-8")
    assert "function errorHtml" in src
    assert "innerHTML" not in src[src.index("function errorHtml") : src.index("function errorHtml") + 400]
    # message path uses escapeHtml
    assert "escapeHtml(error.message" in src
