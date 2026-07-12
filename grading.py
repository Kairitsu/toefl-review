"""Question validation and attempt grading."""
from __future__ import annotations

import re

from parsing import (
    ALLOWED_TYPES,
    COMPLETE_MARKER_RE,
    COMPLETE_UNDERSCORE_RE,
    as_clean_string,
    count_template_blanks,
    normalize_sentence_template,
    parse_template_segments,
    render_complete_passage,
    render_sentence_from_template,
    tokens_equal,
)


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
