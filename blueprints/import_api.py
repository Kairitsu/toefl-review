"""Import parse endpoint.

Thin Flask wrapper around import_pipeline.parse_import. All three question
types flow through the same LLM-first pipeline (LLM → normalize → validate →
local fallback → merge → final normalize → final validate). Per-type logic
lives in import_pipeline.py and parsing.py; this endpoint only enforces size
limits and returns the draft + validation to the frontend.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from import_pipeline import parse_import
from parsing import MAX_RAW_IMPORT_CHARS, as_clean_string

bp = Blueprint("import_api", __name__)


@bp.post("/api/import/parse")
def import_parse():
    payload = request.get_json(force=True, silent=True) or {}
    raw_text = as_clean_string(payload.get("rawText"))
    type_hint = as_clean_string(payload.get("typeHint"))
    if not raw_text:
        return jsonify({"error": "请先粘贴题目原文"}), 400
    if len(raw_text) > MAX_RAW_IMPORT_CHARS:
        return jsonify({"error": f"题目原文过长，当前上限 {MAX_RAW_IMPORT_CHARS} 字符"}), 400

    result = parse_import(raw_text, type_hint)
    return jsonify(result)
