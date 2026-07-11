"""Import/parse normalization helpers (pure functions, no Flask)."""
from __future__ import annotations

import json
import re

ALLOWED_TYPES = {"reading_choice", "build_sentence", "complete_words"}
TYPE_LABELS = {
    "reading_choice": "阅读选择题",
    "build_sentence": "写作造句题",
    "complete_words": "阅读填词题",
}
MAX_RAW_IMPORT_CHARS = 60000


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


def match_answer_to_letter(answer, options):
    """Match an answer value to A/B/C/D. Accepts a bare letter or the full option text."""
    value = as_clean_string(answer)
    if not value:
        return ""
    # Bare letter forms: "A", "A.", "(A)", "答案 A"
    letter_match = re.search(r"\b([A-Da-d])\b", value)
    if letter_match and len(value) <= 6:
        return letter_match.group(1).upper()
    # Full-text match against option text (case-insensitive)
    for opt in options or []:
        if isinstance(opt, dict) and tokens_equal(opt.get("text"), value):
            return as_clean_string(opt.get("key")).upper()[:1]
    return ""


def parse_options_text(text):
    """Parse options from pasted text. Supports 'A. xxx\\nB. yyy', objects, or plain list."""
    text = as_clean_string(text)
    if not text:
        return []
    if isinstance(text, list):
        return normalize_options(text)
    # Labeled lines: "A. xxx" / "A) xxx" / "(A) xxx" / "A: xxx"
    labeled = re.findall(
        r"(?m)^\s*[\(]?\s*([A-Da-d])\s*[\).\):：]?\s*(.+?)\s*$",
        text,
    )
    if labeled:
        seen = {}
        for key, content in labeled:
            k = key.upper()
            if k in {"A", "B", "C", "D"} and k not in seen:
                seen[k] = as_clean_string(content)
        if seen:
            return [
                {"key": k, "text": seen.get(k, "")}
                for k in ["A", "B", "C", "D"]
                if k in seen
            ]
    # Fallback: split by newline / comma and label A/B/C/D in order
    items = [
        as_clean_string(item)
        for item in re.split(r"[\n,，;；]", text)
        if as_clean_string(item)
    ]
    return [
        {"key": chr(ord("A") + i), "text": item}
        for i, item in enumerate(items[:4])
    ]


def _reading_choice_options_valid(options):
    if not isinstance(options, list) or len(options) != 4:
        return False
    keys = [
        as_clean_string(o.get("key")).upper()[:1] if isinstance(o, dict) else ""
        for o in options
    ]
    return keys == ["A", "B", "C", "D"] and all(
        as_clean_string(o.get("text")) if isinstance(o, dict) else "" for o in options
    )


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


def _canonical_passage(passage):
    """Collapse a passage to a comparable form: markers → ___, underscores stay, ws normalized."""
    text = as_clean_string(passage)
    # Treat [[id]] markers and underscore runs as the same blank placeholder
    text = re.sub(r"\[\[\s*[A-Za-z0-9_-]+\s*\]\]", "____", text)
    text = re.sub(r"_{2,}", "____", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _complete_words_llm_aligns_with_local(llm_data, local_data):
    """
    Decide whether the LLM complete-words result is structurally consistent with
    the deterministic local underscore scan. All of the following must hold:
      - same blank count
      - same prefixes in the same order
      - LLM passage text (minus markers) matches local passage (not rewritten)
      - every LLM blank satisfies fullWord == prefix + answer
    If any check fails, the LLM result is treated as misaligned and the local
    scan is used as the fallback for passage + blanks.
    """
    llm_blanks = llm_data.get("blanks", []) if isinstance(llm_data, dict) else []
    local_blanks = local_data.get("blanks", []) if isinstance(local_data, dict) else []
    if not llm_blanks or not local_blanks or len(llm_blanks) != len(local_blanks):
        return False
    for local_b, llm_b in zip(local_blanks, llm_blanks):
        if (
            as_clean_string(local_b.get("prefix")).casefold()
            != as_clean_string(llm_b.get("prefix")).casefold()
        ):
            return False
        prefix = as_clean_string(llm_b.get("prefix"))
        answer = as_clean_string(llm_b.get("answer"))
        full_word = as_clean_string(llm_b.get("fullWord"))
        if prefix and answer and full_word:
            if (prefix + answer).casefold() != full_word.casefold():
                return False
    # Passage text must not be rewritten (compare with markers normalized away)
    if _canonical_passage(llm_data.get("passageText")) != _canonical_passage(local_data.get("passageText")):
        return False
    return True


def merge_complete_words_draft(primary, fallback):
    """
    Merge complete-words LLM result with local underscore scan.

    Rules (per spec):
    - Local underscore scan is authoritative for passageText and blank positions;
      the LLM may never rewrite the passage.
    - When the LLM result is fully aligned with the local scan (same count,
      prefixes, passage text, and fullWord == prefix + answer for every blank),
      LLM answers fill local blanks; LLM-missing positions keep local answers.
    - When the LLM is misaligned (count mismatch / prefix mismatch / passage
      rewritten / fullWord inconsistency / request failure), local answers stand.
    - explanation: LLM priority, local fills missing.
    """
    if not fallback:
        return primary
    if not primary:
        return fallback

    primary_data = primary.get("data") if isinstance(primary.get("data"), dict) else {}
    fallback_data = fallback.get("data") if isinstance(fallback.get("data"), dict) else {}
    local_passage = as_clean_string(fallback_data.get("passageText"))
    local_blanks = fallback_data.get("blanks", []) or []

    # Start from local blank structure (prefix + blankLength from underscore scan)
    merged_blanks = [dict(b) for b in local_blanks]

    if _complete_words_llm_aligns_with_local(primary_data, fallback_data):
        llm_blanks = primary_data.get("blanks", []) or []
        for index, (local_b, llm_b) in enumerate(zip(merged_blanks, llm_blanks)):
            llm_answer = as_clean_string(llm_b.get("answer"))
            llm_full = as_clean_string(llm_b.get("fullWord"))
            if not (llm_answer or llm_full):
                continue  # LLM missing this position → keep local answer
            filled = apply_answer_value_to_blank(local_b, llm_full or llm_answer, index=index + 1)
            merged_blanks[index] = filled

    explanation = as_clean_string(primary.get("explanation")) or as_clean_string(fallback.get("explanation"))
    prompt = (
        as_clean_string(primary.get("prompt"))
        or as_clean_string(fallback.get("prompt"))
        or "Fill in the missing letters in the paragraph"
    )
    needs_confirmation = any(not as_clean_string(b.get("answer")) for b in merged_blanks)
    return normalize_question(
        {
            "type": "complete_words",
            "title": "",
            "article": local_passage,
            "prompt": prompt,
            "explanation": explanation,
            "needsConfirmation": needs_confirmation,
            "data": {
                "passageText": local_passage,
                "blanks": merged_blanks,
            },
        }
    )


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


READING_CHOICE_FIELD_LABELS = {
    "标题": "title",
    "title": "title",
    "题目": "title",
    "原始题目": "title",
    "阅读标题": "title",
    "文章": "article",
    "原文": "article",
    "阅读文章": "article",
    "短文": "article",
    "passage": "article",
    "article": "article",
    "reading text": "article",
    "readingtext": "article",
    "问题": "question",
    "题干": "question",
    "question": "question",
    "prompt": "question",
    "选项": "options",
    "选项列表": "options",
    "options": "options",
    "正确答案": "correctAnswer",
    "答案": "correctAnswer",
    "answer": "correctAnswer",
    "correct answer": "correctAnswer",
    "解析": "analysis",
    "分析": "analysis",
    "explanation": "analysis",
}


def extract_structured_reading_choice_fields(raw_text):
    """Parse labeled reading-choice paste formats into structured fields."""
    text = raw_text or ""
    label_names = sorted(READING_CHOICE_FIELD_LABELS.keys(), key=len, reverse=True)
    escaped = [re.escape(name) for name in label_names]
    pattern = re.compile(rf"(?:^|\n)\s*({'|'.join(escaped)})\s*[：:]\s*", flags=re.I)
    matches = list(pattern.finditer(text))
    if not matches:
        return {}
    fields = {}
    for index, match in enumerate(matches):
        raw_label = match.group(1)
        key = None
        for name, mapped in READING_CHOICE_FIELD_LABELS.items():
            if name.casefold() == raw_label.casefold():
                key = mapped
                break
        if not key:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        fields[key] = as_clean_string(text[start:end])
    return fields


def parse_structured_reading_choice(raw_text):
    """Local fallback parser for reading_choice: extract labeled fields."""
    fields = extract_structured_reading_choice_fields(raw_text)
    if not fields:
        # Freeform paste: whole text becomes the article
        return normalize_question(
            {
                "type": "reading_choice",
                "title": "",
                "article": as_clean_string(raw_text),
                "prompt": "",
                "explanation": "",
                "needsConfirmation": True,
                "data": {"options": [], "correctAnswer": ""},
            }
        )
    options = parse_options_text(fields.get("options", ""))
    correct = match_answer_to_letter(fields.get("correctAnswer", ""), options)
    return normalize_question(
        {
            "type": "reading_choice",
            "title": fields.get("title", ""),
            "article": fields.get("article", ""),
            "prompt": fields.get("question", ""),
            "explanation": fields.get("analysis", ""),
            "needsConfirmation": not correct,
            "data": {"options": options, "correctAnswer": correct},
        }
    )


def merge_reading_choice_draft(primary, fallback):
    """LLM (primary) fields win when valid/complete; local (fallback) fills missing."""
    if not fallback:
        return primary
    if not primary:
        return fallback
    merged = dict(primary)
    merged["type"] = "reading_choice"
    for key in ("title", "article", "prompt", "explanation"):
        if not as_clean_string(merged.get(key)):
            merged[key] = fallback.get(key, "")

    primary_data = merged.get("data") if isinstance(merged.get("data"), dict) else {}
    fallback_data = fallback.get("data") if isinstance(fallback.get("data"), dict) else {}
    primary_options = primary_data.get("options", [])
    fallback_options = fallback_data.get("options", [])
    options = (
        primary_options
        if _reading_choice_options_valid(primary_options)
        else (fallback_options if _reading_choice_options_valid(fallback_options) else primary_options)
    )
    primary_answer = as_clean_string(primary_data.get("correctAnswer")).upper()[:1]
    fallback_answer = as_clean_string(fallback_data.get("correctAnswer")).upper()[:1]
    correct = primary_answer if primary_answer in {"A", "B", "C", "D"} else fallback_answer
    merged["data"] = {"options": options, "correctAnswer": correct}
    merged["needsConfirmation"] = bool(merged.get("needsConfirmation")) or (
        not correct
        or not _reading_choice_options_valid(options)
        or not as_clean_string(merged.get("article"))
        or not as_clean_string(merged.get("prompt"))
    )
    return merged


def merge_build_sentence_draft(primary, fallback):
    """LLM (primary) fields win when valid/consistent; local (fallback) fills missing
    or replaces internally inconsistent template/order sets."""
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

    primary_template = as_clean_string(data.get("sentenceTemplate"))
    primary_order = data.get("correctOrder") or []
    primary_consistent = bool(
        primary_template
        and primary_order
        and count_template_blanks(primary_template) == len(primary_order)
    )
    fallback_template = as_clean_string(fallback_data.get("sentenceTemplate"))
    fallback_order = fallback_data.get("correctOrder") or []
    fallback_consistent = bool(
        fallback_template
        and fallback_order
        and count_template_blanks(fallback_template) == len(fallback_order)
    )

    # If LLM template/order are internally inconsistent but local is consistent,
    # take the local template + order + wordBank as the authoritative set.
    if not primary_consistent and fallback_consistent:
        data["sentenceTemplate"] = fallback_template
        data["correctOrder"] = fallback_order
        data["wordBank"] = fallback_data.get("wordBank", [])
        if not as_clean_string(data.get("completeSentence")):
            data["completeSentence"] = fallback_data.get("completeSentence", "")
    elif fallback_template and primary_template:
        # Prefer the template that actually contains fixed text (not pure blanks)
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
    """
    Lock the question to the user-chosen type.

    Per refactor spec: this function only confirms and locks the target type — it
    does NOT remap one type's fields into another type's shape. Cross-type field
    conversion was removed because it silently produced malformed drafts when the
    LLM returned the wrong type. Field extraction is now handled per-type by the
    import pipeline adapters (see import_pipeline.py).
    """
    forced_type = normalize_type_hint(type_hint)
    if not forced_type or not isinstance(parsed, dict):
        return parsed
    if parsed.get("type") == forced_type:
        return parsed
    remapped = dict(parsed)
    remapped["type"] = forced_type
    remapped["needsConfirmation"] = True
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
        options = normalize_options(raw_data.get("options", payload.get("options", [])))
        raw_answer = as_clean_string(
            raw_data.get("correctAnswer")
            or payload.get("correctAnswer")
            or raw_data.get("answer")
            or payload.get("answer")
        )
        normalized["data"] = {
            "options": options,
            "correctAnswer": match_answer_to_letter(raw_answer, options),
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
