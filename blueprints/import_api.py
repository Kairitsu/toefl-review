"""Import parse endpoint.

Thin Flask wrapper around import_pipeline.parse_import. All three question
types flow through the same LLM-first pipeline (LLM → normalize → validate →
local fallback → merge → final normalize → final validate). Per-type logic
lives in import_pipeline.py and parsing.py; this endpoint only enforces size
limits and returns the draft + validation to the frontend.
"""
from __future__ import annotations

import logging
import traceback

from flask import Blueprint, jsonify, request

from import_pipeline import parse_import
from parsing import MAX_RAW_IMPORT_CHARS, as_clean_string
from security import redact

bp = Blueprint("import_api", __name__)
logger = logging.getLogger(__name__)


def _error_response(message, details=None, raw_text="", status=400):
    """Always return JSON — never Flask/Werkzeug HTML error pages."""
    payload = {
        "error": message,
        "details": list(details or []),
        "rawText": raw_text or "",
    }
    return jsonify(payload), status


def _is_unusable_draft(draft, validation):
    """True when local input produced nothing the user can preview/save."""
    if not isinstance(draft, dict):
        return True
    if validation.get("ok"):
        return False
    errors = validation.get("errors") or []
    if not errors:
        return False
    qtype = as_clean_string(draft.get("type"))
    data = draft.get("data") if isinstance(draft.get("data"), dict) else {}
    if qtype == "complete_words":
        blanks = data.get("blanks")
        return not isinstance(blanks, list) or not blanks
    if qtype == "reading_choice":
        options = data.get("options")
        return not isinstance(options, list) or not options
    if qtype == "build_sentence":
        template = as_clean_string(data.get("sentenceTemplate"))
        return not template
    return True


@bp.post("/api/import/parse")
def import_parse():
    payload = request.get_json(force=True, silent=True) or {}
    raw_text = as_clean_string(payload.get("rawText"))
    type_hint = as_clean_string(payload.get("typeHint"))
    if not raw_text:
        return _error_response("请先粘贴题目原文", details=["rawText 为空"])
    if len(raw_text) > MAX_RAW_IMPORT_CHARS:
        return _error_response(
            f"题目原文过长，当前上限 {MAX_RAW_IMPORT_CHARS} 字符",
            details=[f"当前长度 {len(raw_text)}"],
            raw_text=raw_text[:500],
        )

    try:
        result = parse_import(raw_text, type_hint)
    except Exception:
        # parse_import is designed never to raise; this is belt-and-suspenders.
        logger.error("import_parse uncaught exception:\n%s", traceback.format_exc())
        return _error_response(
            "解析失败",
            details=["服务器解析失败，请查看服务日志"],
            raw_text=raw_text,
            status=500,
        )

    if not isinstance(result, dict):
        return _error_response(
            "解析失败",
            details=["解析结果格式异常"],
            raw_text=raw_text,
            status=500,
        )

    draft = result.get("draft")
    validation = result.get("validation") if isinstance(result.get("validation"), dict) else {}
    validation.setdefault("errors", [])
    validation.setdefault("warnings", [])

    # Local input truly unusable → structured JSON 400 (never HTML 500).
    if _is_unusable_draft(draft, validation):
        details = list(validation.get("errors") or []) or ["无法从输入中识别有效题目结构"]
        return _error_response(
            "解析失败",
            details=[redact(d) if isinstance(d, str) else str(d) for d in details],
            raw_text=result.get("rawText") or raw_text,
            status=400,
        )

    return jsonify(result)
