"""
Regression tests for the unified import pipeline.

All three question types flow through the same stages:
    parse_import(raw_text, type_hint)
        -> call_llm -> normalize_llm -> validate_llm
        -> local_fallback -> merge -> normalize_final -> validate_final

call_llm is mocked per test so every spec scenario (LLM valid / failure /
invalid JSON / wrong type / empty / partial / misaligned / passage rewrite)
is exercised deterministically without network access.
"""
from __future__ import annotations

import import_pipeline


def set_llm(monkeypatch, parsed, errors=None):
    """Mock the LLM call inside the pipeline. parsed=None simulates a failure."""
    monkeypatch.setattr(
        import_pipeline, "call_llm", lambda raw, t: (parsed, errors or [])
    )


# ---------------------------------------------------------------------------
# 通用流程
# ---------------------------------------------------------------------------


class TestGeneralFlow:
    def test_llm_full_valid_result(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "reading_choice",
                "title": "T",
                "article": "Art",
                "prompt": "Q?",
                "explanation": "E",
                "data": {
                    "options": [
                        {"key": "A", "text": "a"},
                        {"key": "B", "text": "b"},
                        {"key": "C", "text": "c"},
                        {"key": "D", "text": "d"},
                    ],
                    "correctAnswer": "B",
                },
            },
        )
        r = import_pipeline.parse_import("any raw", "reading_choice")
        assert r["validation"]["ok"] is True
        assert r["draft"]["data"]["correctAnswer"] == "B"
        assert r["validation"]["warnings"] == []

    def test_llm_request_failure(self, monkeypatch):
        set_llm(monkeypatch, None, ["LLM 请求失败：mock"])
        r = import_pipeline.parse_import(
            "标题：T\n文章：Art\n问题：Q?\n选项：\nA. a\nB. b\nC. c\nD. d\n正确答案：B",
            "reading_choice",
        )
        assert r["draft"]["data"]["correctAnswer"] == "B"
        assert any("LLM 解析失败" in w for w in r["validation"]["warnings"])

    def test_llm_invalid_json(self, monkeypatch):
        # call_llm returns None when extract_json_object fails (invalid JSON)
        set_llm(monkeypatch, None, ["LLM 解析结果失败：not json"])
        r = import_pipeline.parse_import(
            "标题：T\n文章：Art\n问题：Q?\n选项：\nA. a\nB. b\nC. c\nD. d\n正确答案：A",
            "reading_choice",
        )
        assert r["draft"]["data"]["correctAnswer"] == "A"
        assert any("LLM 解析失败" in w for w in r["validation"]["warnings"])

    def test_llm_wrong_type(self, monkeypatch):
        # User forced reading_choice but LLM returned build_sentence.
        # Pipeline must NOT粗暴 convert; it extracts per forced type and warns.
        set_llm(
            monkeypatch,
            {
                "type": "build_sentence",
                "prompt": "ignored",
                "data": {"sentenceTemplate": "{{blank}}", "wordBank": ["x"]},
            },
        )
        r = import_pipeline.parse_import(
            "标题：T\n文章：Art\n问题：Q?\n选项：\nA. a\nB. b\nC. c\nD. d\n正确答案：C",
            "reading_choice",
        )
        assert r["draft"]["type"] == "reading_choice"
        assert any("LLM 返回题型 build_sentence" in w for w in r["validation"]["warnings"])
        # reading_choice fields come from local fallback (LLM had none)
        assert r["draft"]["data"]["correctAnswer"] == "C"

    def test_llm_empty_fields(self, monkeypatch):
        set_llm(monkeypatch, {"type": "reading_choice", "data": {}})
        r = import_pipeline.parse_import(
            "标题：T\n文章：Art\n问题：Q?\n选项：\nA. a\nB. b\nC. c\nD. d\n正确答案：D",
            "reading_choice",
        )
        assert r["draft"]["article"] == "Art"
        assert r["draft"]["data"]["correctAnswer"] == "D"

    def test_llm_partial_fields(self, monkeypatch):
        # LLM provides article + options + answer but misses prompt/explanation
        set_llm(
            monkeypatch,
            {
                "type": "reading_choice",
                "article": "LLM article",
                "data": {
                    "options": [
                        {"key": "A", "text": "a"},
                        {"key": "B", "text": "b"},
                        {"key": "C", "text": "c"},
                        {"key": "D", "text": "d"},
                    ],
                    "correctAnswer": "A",
                },
            },
        )
        r = import_pipeline.parse_import(
            "文章：local art\n问题：local prompt?\n解析：local expl",
            "reading_choice",
        )
        assert r["draft"]["article"] == "LLM article"
        assert r["draft"]["prompt"] == "local prompt?"
        assert r["draft"]["explanation"] == "local expl"
        assert r["draft"]["data"]["correctAnswer"] == "A"

    def test_local_fallback_success(self, monkeypatch):
        set_llm(monkeypatch, None, ["down"])
        r = import_pipeline.parse_import(
            "标题：T\n文章：Art\n问题：Q?\n选项：\nA. a\nB. b\nC. c\nD. d\n正确答案：B",
            "reading_choice",
        )
        assert r["validation"]["ok"] is True
        assert r["draft"]["article"] == "Art"

    def test_raw_user_content_not_cleared(self, monkeypatch):
        raw = "标题：T\n文章：Art\n问题：Q?\n选项：\nA. a\nB. b\nC. c\nD. d\n正确答案：B"
        set_llm(monkeypatch, None, ["down"])
        r = import_pipeline.parse_import(raw, "reading_choice")
        assert r["rawText"] == raw
        assert r["draft"]["article"] == "Art"


# ---------------------------------------------------------------------------
# 阅读选择题
# ---------------------------------------------------------------------------


class TestReadingChoice:
    def test_six_fields_complete(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "reading_choice",
                "title": "Photosynthesis",
                "article": "Plants convert light.",
                "prompt": "What?",
                "explanation": "Because.",
                "data": {
                    "options": [
                        {"key": "A", "text": "Heat"},
                        {"key": "B", "text": "Chemical"},
                        {"key": "C", "text": "Kinetic"},
                        {"key": "D", "text": "Nuclear"},
                    ],
                    "correctAnswer": "B",
                },
            },
        )
        r = import_pipeline.parse_import("raw", "reading_choice")
        d = r["draft"]
        assert d["title"] == "Photosynthesis"
        assert d["article"] == "Plants convert light."
        assert d["prompt"] == "What?"
        assert d["explanation"] == "Because."
        assert len(d["data"]["options"]) == 4
        assert d["data"]["correctAnswer"] == "B"

    def test_article_or_prompt_missing_filled_by_local(self, monkeypatch):
        # LLM misses prompt; local provides it
        set_llm(
            monkeypatch,
            {
                "type": "reading_choice",
                "article": "LLM art",
                "data": {
                    "options": [
                        {"key": "A", "text": "a"},
                        {"key": "B", "text": "b"},
                        {"key": "C", "text": "c"},
                        {"key": "D", "text": "d"},
                    ],
                    "correctAnswer": "A",
                },
            },
        )
        r = import_pipeline.parse_import("文章：art\n问题：local question?", "reading_choice")
        assert r["draft"]["prompt"] == "local question?"

    def test_options_as_array(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "reading_choice",
                "article": "a",
                "prompt": "q",
                "data": {
                    "options": ["one", "two", "three", "four"],
                    "correctAnswer": "B",
                },
            },
        )
        r = import_pipeline.parse_import("raw", "reading_choice")
        opts = r["draft"]["data"]["options"]
        assert [o["key"] for o in opts] == ["A", "B", "C", "D"]
        assert opts[1]["text"] == "two"

    def test_options_as_object(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "reading_choice",
                "article": "a",
                "prompt": "q",
                "data": {
                    "options": {"A": "aa", "B": "bb", "C": "cc", "D": "dd"},
                    "correctAnswer": "C",
                },
            },
        )
        r = import_pipeline.parse_import("raw", "reading_choice")
        opts = r["draft"]["data"]["options"]
        assert opts[2]["text"] == "cc"
        assert r["draft"]["data"]["correctAnswer"] == "C"

    def test_options_as_text_with_letters(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "reading_choice",
                "article": "a",
                "prompt": "q",
                "data": {
                    "options": "A. alpha\nB. beta\nC. gamma\nD. delta",
                    "correctAnswer": "D",
                },
            },
        )
        r = import_pipeline.parse_import("raw", "reading_choice")
        opts = r["draft"]["data"]["options"]
        assert opts[3]["text"] == "delta"
        assert r["draft"]["data"]["correctAnswer"] == "D"

    def test_correct_answer_as_letter(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "reading_choice",
                "article": "a",
                "prompt": "q",
                "data": {
                    "options": [
                        {"key": "A", "text": "a"},
                        {"key": "B", "text": "b"},
                        {"key": "C", "text": "c"},
                        {"key": "D", "text": "d"},
                    ],
                    "correctAnswer": "C",
                },
            },
        )
        r = import_pipeline.parse_import("raw", "reading_choice")
        assert r["draft"]["data"]["correctAnswer"] == "C"

    def test_correct_answer_as_full_option_text(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "reading_choice",
                "article": "a",
                "prompt": "q",
                "data": {
                    "options": [
                        {"key": "A", "text": "Heat energy"},
                        {"key": "B", "text": "Chemical energy"},
                        {"key": "C", "text": "Kinetic energy"},
                        {"key": "D", "text": "Nuclear energy"},
                    ],
                    "correctAnswer": "Chemical energy",
                },
            },
        )
        r = import_pipeline.parse_import("raw", "reading_choice")
        assert r["draft"]["data"]["correctAnswer"] == "B"

    def test_fields_located_in_data(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "reading_choice",
                "data": {
                    "title": "InData",
                    "article": "art-in-data",
                    "prompt": "q-in-data",
                    "options": [
                        {"key": "A", "text": "a"},
                        {"key": "B", "text": "b"},
                        {"key": "C", "text": "c"},
                        {"key": "D", "text": "d"},
                    ],
                    "correctAnswer": "A",
                },
            },
        )
        r = import_pipeline.parse_import("raw", "reading_choice")
        assert r["draft"]["title"] == "InData"
        assert r["draft"]["article"] == "art-in-data"
        assert r["draft"]["prompt"] == "q-in-data"

    def test_common_aliases(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "reading_choice",
                "passage": "alias article",
                "question": "alias prompt",
                "analysis": "alias explanation",
                "data": {
                    "options": [
                        {"key": "A", "text": "a"},
                        {"key": "B", "text": "b"},
                        {"key": "C", "text": "c"},
                        {"key": "D", "text": "d"},
                    ],
                    "answer": "B",
                },
            },
        )
        r = import_pipeline.parse_import("raw", "reading_choice")
        assert r["draft"]["article"] == "alias article"
        assert r["draft"]["prompt"] == "alias prompt"
        assert r["draft"]["explanation"] == "alias explanation"
        assert r["draft"]["data"]["correctAnswer"] == "B"


# ---------------------------------------------------------------------------
# 写作造句题
# ---------------------------------------------------------------------------


class TestBuildSentence:
    def test_template_with_start_middle_end_fixed_text(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "build_sentence",
                "prompt": "Q?",
                "data": {
                    "sentenceTemplate": "{{blank}} went to the {{blank}} yesterday.",
                    "wordBank": ["Maria", "store", "John", "park"],
                    "correctOrder": ["Maria", "store"],
                    "completeSentence": "Maria went to the store yesterday.",
                },
            },
        )
        r = import_pipeline.parse_import("raw", "build_sentence")
        d = r["draft"]["data"]
        assert "went to the" in d["sentenceTemplate"]
        assert "yesterday." in d["sentenceTemplate"]
        assert d["correctOrder"] == ["Maria", "store"]
        assert r["validation"]["ok"] is True

    def test_multi_word_tokens(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "build_sentence",
                "prompt": "Q?",
                "data": {
                    "sentenceTemplate": "{{blank}} {{blank}} {{blank}} {{blank}} {{blank}} during the {{blank}} {{blank}}.",
                    "wordBank": ["presentation", "entire", "their", "exceptional", "public speaking", "were", "skills"],
                    "correctOrder": ["their", "public speaking", "skills", "were", "exceptional", "entire", "presentation"],
                    "completeSentence": "Their public speaking skills were exceptional during the entire presentation.",
                },
            },
        )
        r = import_pipeline.parse_import("raw", "build_sentence")
        d = r["draft"]["data"]
        assert "public speaking" in d["wordBank"]
        assert "public speaking" in d["correctOrder"]
        assert r["validation"]["ok"] is True

    def test_llm_missing_correct_order(self, monkeypatch):
        # LLM omits correctOrder; local provides it
        set_llm(
            monkeypatch,
            {
                "type": "build_sentence",
                "prompt": "Q?",
                "data": {
                    "sentenceTemplate": "{{blank}} went to the {{blank}}.",
                    "wordBank": ["Maria", "store", "John"],
                },
            },
        )
        raw = (
            "提问者：Q?\n"
            "句子模板：____ went to the ____.\n"
            "词库：Maria, store, John\n"
            "正确答案：Maria went to the store."
        )
        r = import_pipeline.parse_import(raw, "build_sentence")
        assert r["draft"]["data"]["correctOrder"] == ["Maria", "store"]

    def test_llm_blank_count_mismatch_recovered_by_local(self, monkeypatch):
        # LLM template has 3 blanks but order has 2 (inconsistent);
        # local is consistent (2 blanks, 2 order) → local set wins.
        set_llm(
            monkeypatch,
            {
                "type": "build_sentence",
                "prompt": "Q?",
                "data": {
                    "sentenceTemplate": "{{blank}} {{blank}} {{blank}}.",
                    "wordBank": ["a", "b", "c"],
                    "correctOrder": ["a", "b"],
                },
            },
        )
        raw = (
            "提问者：Q?\n"
            "句子模板：____ went to the ____.\n"
            "词库：Maria, store, John\n"
            "正确答案：Maria went to the store."
        )
        r = import_pipeline.parse_import(raw, "build_sentence")
        d = r["draft"]["data"]
        # Local template (2 blanks) + local order (2) should win
        assert d["sentenceTemplate"].count("{{blank}}") == 2
        assert len(d["correctOrder"]) == 2
        assert r["validation"]["ok"] is True

    def test_llm_failure_local_recovers(self, monkeypatch):
        set_llm(monkeypatch, None, ["down"])
        raw = (
            "提问者：What did Maria do?\n"
            "句子模板：____ went to the ____.\n"
            "词库：Maria, store, John, park\n"
            "正确答案：Maria went to the store."
        )
        r = import_pipeline.parse_import(raw, "build_sentence")
        d = r["draft"]["data"]
        assert d["correctOrder"] == ["Maria", "store"]
        assert r["validation"]["ok"] is True

    def test_local_fallback_does_not_override_valid_llm(self, monkeypatch):
        # LLM is fully valid; local has different (wrong) order. LLM must win.
        set_llm(
            monkeypatch,
            {
                "type": "build_sentence",
                "prompt": "LLM prompt",
                "data": {
                    "sentenceTemplate": "{{blank}} went to the {{blank}}.",
                    "wordBank": ["Maria", "store", "John"],
                    "correctOrder": ["Maria", "store"],
                    "completeSentence": "Maria went to the store.",
                },
            },
        )
        raw = (
            "提问者：local prompt\n"
            "句子模板：____ went to the ____.\n"
            "词库：John, park, Maria, store\n"
            "正确答案：John went to the park."
        )
        r = import_pipeline.parse_import(raw, "build_sentence")
        d = r["draft"]["data"]
        assert d["correctOrder"] == ["Maria", "store"]
        assert r["draft"]["prompt"] == "LLM prompt"


# ---------------------------------------------------------------------------
# 阅读填词题
# ---------------------------------------------------------------------------


class TestCompleteWords:
    def test_continuous_underscores(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "data": {
                    "passageText": "The civiliza[[1]] built sys[[2]].",
                    "blanks": [
                        {"id": "1", "prefix": "civiliza", "answer": "tion", "fullWord": "civilization"},
                        {"id": "2", "prefix": "sys", "answer": "tems", "fullWord": "systems"},
                    ],
                },
            },
        )
        raw = "题目/原始短文：\nThe civiliza____ built sys____.\n\n答案：\n1. tion\n2. tems"
        r = import_pipeline.parse_import(raw, "complete_words")
        b = r["draft"]["data"]["blanks"]
        assert len(b) == 2
        assert b[0]["fullWord"] == "civilization"
        assert b[1]["fullWord"] == "systems"
        assert r["validation"]["ok"] is True

    def test_separated_underscores(self, monkeypatch):
        # "met _ _ _" form (letter + space-separated underscores)
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "data": {
                    "passageText": "they met [[1]] there.",
                    "blanks": [
                        {"id": "1", "prefix": "met", "answer": "als", "fullWord": "metals"},
                    ],
                },
            },
        )
        raw = "题目/原始短文：\nthey met _ _ _ there.\n\n答案：\n1. als"
        r = import_pipeline.parse_import(raw, "complete_words")
        b = r["draft"]["data"]["blanks"]
        assert len(b) == 1
        assert b[0]["prefix"] == "met"
        assert b[0]["answer"] == "als"

    def test_multiple_blanks(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "data": {
                    "passageText": "a[[1]] b[[2]] c[[3]].",
                    "blanks": [
                        {"id": "1", "prefix": "a", "answer": "1", "fullWord": "a1"},
                        {"id": "2", "prefix": "b", "answer": "2", "fullWord": "b2"},
                        {"id": "3", "prefix": "c", "answer": "3", "fullWord": "c3"},
                    ],
                },
            },
        )
        raw = "题目/原始短文：\na____ b____ c____.\n\n答案：\n1. 1\n2. 2\n3. 3"
        r = import_pipeline.parse_import(raw, "complete_words")
        assert len(r["draft"]["data"]["blanks"]) == 3

    def test_answer_as_missing_letters(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "data": {
                    "passageText": "civiliza[[1]]",
                    "blanks": [
                        {"id": "1", "prefix": "civiliza", "answer": "tion", "fullWord": "civilization"},
                    ],
                },
            },
        )
        raw = "题目/原始短文：\nciviliza____\n\n答案：\n1. tion"
        r = import_pipeline.parse_import(raw, "complete_words")
        b = r["draft"]["data"]["blanks"][0]
        assert b["answer"] == "tion"
        assert b["fullWord"] == "civilization"

    def test_answer_as_full_word(self, monkeypatch):
        # LLM returns the full word as the answer value; local applies prefix split
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "data": {
                    "passageText": "civiliza[[1]]",
                    "blanks": [
                        {"id": "1", "prefix": "civiliza", "answer": "tion", "fullWord": "civilization"},
                    ],
                },
            },
        )
        raw = "题目/原始短文：\nciviliza____\n\n答案：\n1. civilization"
        r = import_pipeline.parse_import(raw, "complete_words")
        b = r["draft"]["data"]["blanks"][0]
        # Local answer (civilization) is a full word → split by prefix → tion
        assert b["answer"] == "tion"
        assert b["fullWord"] == "civilization"
        assert r["validation"]["ok"] is True

    def test_llm_missing_blanks_count_mismatch(self, monkeypatch):
        # LLM returns 1 blank but local scans 2 → misaligned → local wins
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "data": {
                    "passageText": "civiliza[[1]] sys[[2]]",
                    "blanks": [
                        {"id": "1", "prefix": "civiliza", "answer": "tion", "fullWord": "civilization"},
                    ],
                },
            },
        )
        raw = "题目/原始短文：\nciviliza____ sys____\n\n答案：\n1. tion\n2. tems"
        r = import_pipeline.parse_import(raw, "complete_words")
        b = r["draft"]["data"]["blanks"]
        assert len(b) == 2
        # Local answers stand
        assert b[0]["answer"] == "tion"
        assert b[1]["answer"] == "tems"

    def test_llm_extra_blanks_count_mismatch(self, monkeypatch):
        # LLM returns 3 blanks but local scans 2 → misaligned → local wins
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "data": {
                    "passageText": "a[[1]] b[[2]] c[[3]]",
                    "blanks": [
                        {"id": "1", "prefix": "a", "answer": "1", "fullWord": "a1"},
                        {"id": "2", "prefix": "b", "answer": "2", "fullWord": "b2"},
                        {"id": "3", "prefix": "c", "answer": "3", "fullWord": "c3"},
                    ],
                },
            },
        )
        raw = "题目/原始短文：\nciviliza____ sys____\n\n答案：\n1. tion\n2. tems"
        r = import_pipeline.parse_import(raw, "complete_words")
        b = r["draft"]["data"]["blanks"]
        assert len(b) == 2
        assert b[0]["prefix"] == "civiliza"

    def test_llm_rewrote_passage(self, monkeypatch):
        # LLM changes surrounding text → passage mismatch → local passage + answers
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "data": {
                    "passageText": "The ancient civiliza[[1]] constructed sys[[2]].",
                    "blanks": [
                        {"id": "1", "prefix": "civiliza", "answer": "tion", "fullWord": "civilization"},
                        {"id": "2", "prefix": "sys", "answer": "tems", "fullWord": "systems"},
                    ],
                },
            },
        )
        raw = "题目/原始短文：\nThe civiliza____ built sys____.\n\n答案：\n1. la\n2. lb"
        r = import_pipeline.parse_import(raw, "complete_words")
        # Local passage is authoritative (not the rewritten one)
        assert "built" in r["draft"]["data"]["passageText"]
        assert "constructed" not in r["draft"]["data"]["passageText"]
        # Local answers stand
        b = r["draft"]["data"]["blanks"]
        assert b[0]["answer"] == "la"
        assert b[1]["answer"] == "lb"

    def test_llm_failure_local_scan_recovers(self, monkeypatch):
        set_llm(monkeypatch, None, ["down"])
        raw = "题目/原始短文：\nThe civiliza____ built sys____.\n\n答案：\n1. tion\n2. tems"
        r = import_pipeline.parse_import(raw, "complete_words")
        b = r["draft"]["data"]["blanks"]
        assert len(b) == 2
        assert b[0]["fullWord"] == "civilization"
        assert b[1]["fullWord"] == "systems"
        assert r["validation"]["ok"] is True

    def test_prefix_plus_answer_equals_full_word(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "data": {
                    "passageText": "civiliza[[1]]",
                    "blanks": [
                        {"id": "1", "prefix": "civiliza", "answer": "tion", "fullWord": "civilization"},
                    ],
                },
            },
        )
        raw = "题目/原始短文：\nciviliza____\n\n答案：\n1. tion"
        r = import_pipeline.parse_import(raw, "complete_words")
        b = r["draft"]["data"]["blanks"][0]
        assert (b["prefix"] + b["answer"]) == b["fullWord"]
        assert r["validation"]["ok"] is True

    def test_local_fallback_does_not_override_aligned_llm(self, monkeypatch):
        # LLM is fully aligned with local; LLM answers win even if local differs
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "explanation": "LLM expl",
                "data": {
                    "passageText": "civiliza[[1]] sys[[2]]",
                    "blanks": [
                        {"id": "1", "prefix": "civiliza", "answer": "tion", "fullWord": "civilization"},
                        {"id": "2", "prefix": "sys", "answer": "tems", "fullWord": "systems"},
                    ],
                },
            },
        )
        # Local answers are different (wrong) — LLM must win when aligned
        raw = "题目/原始短文：\nciviliza____ sys____\n\n答案：\n1. WRONG\n2. WRONG2"
        r = import_pipeline.parse_import(raw, "complete_words")
        b = r["draft"]["data"]["blanks"]
        assert b[0]["answer"] == "tion"
        assert b[1]["answer"] == "tems"
        assert r["draft"]["explanation"] == "LLM expl"
