"""
Unified import pipeline for the three TOEFL Review question types.

All three types share the same execution stages:

    parse_import(raw_text, type_hint)
        -> call_llm_parser(type)          # shared LLM HTTP call → raw JSON
        -> normalize_llm_result(type)     # per-type field extraction + normalize
        -> validate_llm_result(type)      # per-type structural check (diagnostic)
        -> run_local_fallback(type)       # per-type deterministic local parser
        -> merge_results(type)            # LLM fields win when valid; local fills
        -> normalize_final_result(type)   # normalize_question
        -> validate_final_result(type)    # grading.validate_question
        -> return draft

The LLM call (llm.call_llm) is shared. Each type owns its own schema aliases,
normalization, local fallback, merge, and validation via a per-type adapter
dict registered in ADAPTERS. There is no global parser that mixes fields from
different types: once the user picks a typeHint, only that type's adapter runs.
If the LLM returns a different type than the forced typeHint, the LLM payload
is discarded as invalid (no cross-type field remapping) and local fallback
supplies the draft.
"""
from __future__ import annotations

import logging

from grading import validate_question
from llm import call_llm
from parsing import (
    ALLOWED_TYPES,
    as_clean_string,
    count_template_blanks,
    looks_like_build_sentence_raw,
    looks_like_complete_words_raw,
    merge_build_sentence_draft,
    merge_complete_words_draft,
    merge_reading_choice_draft,
    normalize_question,
    normalize_type_hint,
    parse_options_text,
    parse_structured_build_sentence,
    parse_structured_complete_words,
    parse_structured_reading_choice,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _pick(parsed, field, aliases):
    """
    Pick the first non-empty value for ``field`` or any alias, looking at both
    the top-level object and its nested ``data`` dict. Lists/dicts are returned
    as-is when non-empty; strings are returned when non-blank.
    """
    if not isinstance(parsed, dict):
        return ""
    sources = [parsed]
    data = parsed.get("data")
    if isinstance(data, dict):
        sources.append(data)
    for src in sources:
        for key in [field] + list(aliases):
            value = src.get(key)
            if isinstance(value, (list, dict)):
                if value:
                    return value
            elif as_clean_string(value):
                return value
    return ""


def _empty_draft(qtype):
    return normalize_question({"type": qtype, "data": {}})


def _resolve_type(raw_text, type_hint):
    """Lock to the user-chosen type; fall back to heuristic detection when absent."""
    forced = normalize_type_hint(type_hint)
    if forced:
        return forced
    if looks_like_complete_words_raw(raw_text) and not looks_like_build_sentence_raw(raw_text):
        return "complete_words"
    if looks_like_build_sentence_raw(raw_text):
        return "build_sentence"
    return "reading_choice"


# ---------------------------------------------------------------------------
# reading_choice adapter
# ---------------------------------------------------------------------------


def _normalize_llm_reading_choice(parsed, raw_text):
    options = _pick(parsed, "options", [])
    if isinstance(options, str):
        options = parse_options_text(options)
    correct = _pick(parsed, "correctAnswer", ["answer"])
    payload = {
        "type": "reading_choice",
        "title": _pick(parsed, "title", []),
        "article": _pick(parsed, "article", ["passage", "readingText", "reading_text"]),
        "prompt": _pick(parsed, "prompt", ["question"]),
        "explanation": _pick(parsed, "explanation", ["analysis"]),
        "needsConfirmation": not as_clean_string(correct),
        "data": {
            "options": options if isinstance(options, (list, dict)) else [],
            "correctAnswer": correct,
        },
    }
    return normalize_question(payload)


def _validate_llm_reading_choice(normalized):
    errors = []
    data = normalized.get("data") or {}
    options = data.get("options")
    if not isinstance(options, list):
        errors.append("LLM 返回的 options 不是列表")
    elif not options:
        errors.append("LLM 未返回选项")
    if not as_clean_string(normalized.get("article")):
        errors.append("LLM 未返回文章")
    if not as_clean_string(normalized.get("prompt")):
        errors.append("LLM 未返回问题")
    return (not errors), errors


def _local_fallback_reading_choice(raw_text):
    return parse_structured_reading_choice(raw_text)


# ---------------------------------------------------------------------------
# build_sentence adapter
# ---------------------------------------------------------------------------


def _normalize_llm_build_sentence(parsed, raw_text):
    word_bank = _pick(parsed, "wordBank", ["words"])
    correct_order = _pick(parsed, "correctOrder", ["answerOrder"])
    payload = {
        "type": "build_sentence",
        "title": "",
        "article": "",
        "prompt": _pick(parsed, "prompt", ["question", "questioner"]),
        "explanation": _pick(parsed, "explanation", ["analysis"]),
        "needsConfirmation": not (correct_order and word_bank),
        "data": {
            "sentenceTemplate": _pick(parsed, "sentenceTemplate", ["template", "sentence"]),
            "wordBank": word_bank if isinstance(word_bank, list) else [],
            "correctOrder": correct_order if isinstance(correct_order, list) else [],
            "completeSentence": _pick(parsed, "completeSentence", ["fullSentence"]),
        },
    }
    return normalize_question(payload)


def _validate_llm_build_sentence(normalized):
    errors = []
    data = normalized.get("data") or {}
    template = as_clean_string(data.get("sentenceTemplate"))
    word_bank = data.get("wordBank")
    correct_order = data.get("correctOrder")
    if not template:
        errors.append("LLM 未返回句子模板")
    if not isinstance(word_bank, list) or not word_bank:
        errors.append("LLM 未返回词库")
    if not isinstance(correct_order, list) or not correct_order:
        errors.append("LLM 未返回正确顺序")
    if (
        template
        and isinstance(correct_order, list)
        and correct_order
        and count_template_blanks(template) != len(correct_order)
    ):
        errors.append(
            f"LLM 模板空位 {count_template_blanks(template)} 个，但正确顺序有 {len(correct_order)} 项"
        )
    return (not errors), errors


def _local_fallback_build_sentence(raw_text):
    draft = parse_structured_build_sentence(raw_text)
    if draft is None:
        return _empty_draft("build_sentence")
    return draft


# ---------------------------------------------------------------------------
# complete_words adapter
# ---------------------------------------------------------------------------


def _normalize_llm_complete_words(parsed, raw_text):
    passage = _pick(parsed, "passageText", ["passage", "article"])
    blanks = _pick(parsed, "blanks", [])
    payload = {
        "type": "complete_words",
        "title": "",
        "article": passage,
        "prompt": _pick(parsed, "prompt", ["question"]) or "Fill in the missing letters in the paragraph",
        "explanation": _pick(parsed, "explanation", ["analysis"]),
        "needsConfirmation": not blanks,
        "data": {
            "passageText": passage,
            "blanks": blanks if isinstance(blanks, list) else [],
        },
    }
    return normalize_question(payload)


def _validate_llm_complete_words(normalized):
    errors = []
    data = normalized.get("data") or {}
    passage = as_clean_string(data.get("passageText"))
    blanks = data.get("blanks")
    if not passage:
        errors.append("LLM 未返回短文")
    if not isinstance(blanks, list) or not blanks:
        errors.append("LLM 未返回空格列表")
    return (not errors), errors


def _local_fallback_complete_words(raw_text):
    draft = parse_structured_complete_words(raw_text)
    if draft is None:
        # Retry with an explicit 短文 label so the structured parser can find it
        draft = parse_structured_complete_words(f"短文：\n{raw_text}")
    if draft is None:
        return _empty_draft("complete_words")
    return draft


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

ADAPTERS = {
    "reading_choice": {
        "normalize_llm": _normalize_llm_reading_choice,
        "validate_llm": _validate_llm_reading_choice,
        "local_fallback": _local_fallback_reading_choice,
        "merge": merge_reading_choice_draft,
    },
    "build_sentence": {
        "normalize_llm": _normalize_llm_build_sentence,
        "validate_llm": _validate_llm_build_sentence,
        "local_fallback": _local_fallback_build_sentence,
        "merge": merge_build_sentence_draft,
    },
    "complete_words": {
        "normalize_llm": _normalize_llm_complete_words,
        "validate_llm": _validate_llm_complete_words,
        "local_fallback": _local_fallback_complete_words,
        "merge": merge_complete_words_draft,
    },
}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


def parse_import(raw_text, type_hint=""):
    """
    Run the unified LLM-first import pipeline.

    Returns a dict with: rawText, draft, validation. Never raises — LLM/local
    failures are captured into validation.warnings and a best-effort draft is
    always returned so the user's original input is never lost.
    """
    raw_text = as_clean_string(raw_text)
    forced_type = _resolve_type(raw_text, type_hint)
    try:
        return _parse_import_inner(raw_text, forced_type)
    except Exception:
        # Last-resort safety net: unexpected bugs must not produce HTTP 500 HTML.
        logger.exception("parse_import unexpected failure (type=%s)", forced_type)
        try:
            draft = ADAPTERS[forced_type]["local_fallback"](raw_text)
            if not isinstance(draft, dict):
                draft = _empty_draft(forced_type)
            draft = normalize_question(draft) if isinstance(draft, dict) else _empty_draft(forced_type)
            draft["type"] = forced_type
            validation = validate_question(draft)
        except Exception:
            logger.exception("parse_import local recovery also failed")
            draft = _empty_draft(forced_type)
            draft["type"] = forced_type
            validation = {
                "ok": False,
                "errors": ["解析过程中发生意外错误，请检查输入后重试"],
                "warnings": [],
            }
        warnings = ["解析过程中发生意外错误，已尽量使用本地结果"]
        validation["warnings"] = warnings + list(validation.get("warnings") or [])
        return {"rawText": raw_text, "draft": draft, "validation": validation}


def _parse_import_inner(raw_text, forced_type):
    adapter = ADAPTERS[forced_type]

    # Stage 1: LLM call (shared). call_llm must never raise; still guard.
    try:
        llm_parsed, llm_errors = call_llm(raw_text, forced_type)
    except Exception as exc:
        logger.exception("call_llm raised unexpectedly")
        llm_parsed, llm_errors = None, [f"LLM 请求失败：{exc}"]

    warnings = []
    llm_result = None

    if llm_parsed is not None:
        # Non-dict top-level (array / string / null-ish) → treat as invalid LLM payload.
        if not isinstance(llm_parsed, dict):
            warnings.append(
                f"LLM 返回了非对象结构（{type(llm_parsed).__name__}），已回退到本地解析"
            )
        else:
            returned_type = as_clean_string(llm_parsed.get("type"))
            # Wrong type = invalid LLM result. Do not remap fields across types.
            if returned_type and returned_type not in ALLOWED_TYPES:
                warnings.append(
                    f"LLM 返回未知题型 {returned_type}，已视为无效并回退到本地解析"
                )
            elif returned_type and returned_type != forced_type:
                warnings.append(
                    f"LLM 返回题型 {returned_type}，与选择的 {forced_type} 不一致，"
                    f"已视为无效并回退到本地解析（不跨题型转换字段）"
                )
            else:
                # Stages 2-3: normalize + validate LLM result (per-type)
                # Missing type is tolerated when typeHint is forced: extract under forced type.
                try:
                    llm_result = adapter["normalize_llm"](llm_parsed, raw_text)
                    llm_ok, llm_validate_errors = adapter["validate_llm"](llm_result)
                    if not llm_ok:
                        warnings.append(
                            "LLM 返回结果不完整，已用本地解析补充："
                            + "；".join(llm_validate_errors)
                        )
                except Exception:
                    logger.exception("LLM normalize/validate failed; discarding LLM result")
                    llm_result = None
                    warnings.append("LLM 返回结果无法规范化，已回退到本地解析")
    else:
        # Expected LLM failures (timeout / HTTP / bad JSON) — not app crashes.
        msg = "；".join(llm_errors) if llm_errors else "未知原因"
        warnings.append("LLM 解析失败，已回退到本地结构化识别：" + msg)
        logger.info("LLM parse fallback: %s", msg)

    # Stage 4: local fallback (always runs — it is the deterministic safety net)
    try:
        local_result = adapter["local_fallback"](raw_text)
    except Exception:
        logger.exception("local_fallback failed for type=%s", forced_type)
        local_result = _empty_draft(forced_type)
        warnings.append("本地解析也失败，请检查原始输入格式")

    # Stage 5: merge — LLM fields win when valid/complete; local fills missing
    try:
        if llm_result is not None and isinstance(llm_result, dict):
            draft = adapter["merge"](llm_result, local_result)
        elif isinstance(local_result, dict):
            draft = local_result
        else:
            draft = _empty_draft(forced_type)
    except Exception:
        logger.exception("merge failed for type=%s", forced_type)
        draft = local_result if isinstance(local_result, dict) else _empty_draft(forced_type)
        warnings.append("合并 LLM 与本地结果失败，已使用本地解析结果")

    # Stage 6: final normalize + lock type
    try:
        draft = normalize_question(draft) if isinstance(draft, dict) else _empty_draft(forced_type)
    except Exception:
        logger.exception("final normalize failed")
        draft = _empty_draft(forced_type)
    draft["type"] = forced_type

    # Stage 7: final validate
    try:
        validation = validate_question(draft)
    except Exception:
        logger.exception("validate_question failed")
        validation = {
            "ok": False,
            "errors": ["题目校验失败"],
            "warnings": [],
        }
    if not isinstance(validation, dict):
        validation = {"ok": False, "errors": ["题目校验返回异常"], "warnings": []}
    validation.setdefault("errors", [])
    validation.setdefault("warnings", [])
    if warnings:
        validation["warnings"] = warnings + list(validation.get("warnings") or [])
    if draft.get("needsConfirmation") and validation.get("ok"):
        validation["warnings"] = list(validation.get("warnings") or []) + [
            "题目部分字段可能不完整，请核对后再保存。"
        ]

    return {"rawText": raw_text, "draft": draft, "validation": validation}
