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
        # Wrong type is invalid: discard LLM payload entirely (no field remapping).
        set_llm(
            monkeypatch,
            {
                "type": "build_sentence",
                "prompt": "POLLUTED_PROMPT",
                "article": "POLLUTED_ARTICLE",
                "data": {
                    "sentenceTemplate": "{{blank}}",
                    "wordBank": ["x"],
                    "correctOrder": ["x"],
                },
            },
        )
        r = import_pipeline.parse_import(
            "标题：T\n文章：Art\n问题：Q?\n选项：\nA. a\nB. b\nC. c\nD. d\n正确答案：C",
            "reading_choice",
        )
        assert r["draft"]["type"] == "reading_choice"
        assert any("LLM 返回题型 build_sentence" in w for w in r["validation"]["warnings"])
        assert any("视为无效" in w for w in r["validation"]["warnings"])
        # All fields from local fallback — no cross-type pollution
        assert r["draft"]["prompt"] == "Q?"
        assert r["draft"]["article"] == "Art"
        assert r["draft"]["data"]["correctAnswer"] == "C"
        assert "POLLUTED" not in (r["draft"]["prompt"] + r["draft"]["article"])

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

    def test_combined_question_and_options_common_formats(self, monkeypatch):
        set_llm(monkeypatch, None, ["down"])
        formats = [
            "A. one\nB. two\nC. three\nD. four",
            "A、one\nB、two\nC、three\nD、four",
            "A: one\nB: two\nC: three\nD: four",
            "(A) one\n(B) two\n(C) three\n(D) four",
        ]
        for options in formats:
            raw = (
                "标题：T\n文章：Article\n问题与选项：\n"
                "What is the main purpose?\n\n"
                f"{options}\n正确答案：B\n解析：Because"
            )
            r = import_pipeline.parse_import(raw, "reading_choice")
            assert r["validation"]["ok"] is True, (options, r["validation"])
            assert r["draft"]["prompt"] == "What is the main purpose?"
            assert [item["key"] for item in r["draft"]["data"]["options"]] == ["A", "B", "C", "D"]
            assert r["draft"]["data"]["correctAnswer"] == "B"

    def test_combined_question_and_incomplete_options_cannot_save(self, monkeypatch):
        set_llm(monkeypatch, None, ["down"])
        raw = (
            "标题：T\n文章：Article\n问题与选项：\nQuestion?\n\n"
            "A. one\nB. two\nC. three\n正确答案：B"
        )
        r = import_pipeline.parse_import(raw, "reading_choice")
        assert r["validation"]["ok"] is False
        assert any("A/B/C/D 四个选项" in error for error in r["validation"]["errors"])

    def test_raw_user_content_not_cleared(self, monkeypatch):
        raw = "标题：T\n文章：Art\n问题：Q?\n选项：\nA. a\nB. b\nC. c\nD. d\n正确答案：B"
        set_llm(monkeypatch, None, ["down"])
        r = import_pipeline.parse_import(raw, "reading_choice")
        assert r["rawText"] == raw
        assert r["draft"]["article"] == "Art"

    def test_llm_missing_type_still_used_under_forced_hint(self, monkeypatch):
        # LLM omits type but returns valid reading_choice fields; typeHint locks type.
        set_llm(
            monkeypatch,
            {
                "article": "Art from LLM",
                "prompt": "Q from LLM?",
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
        r = import_pipeline.parse_import("local", "reading_choice")
        assert r["draft"]["type"] == "reading_choice"
        assert r["draft"]["article"] == "Art from LLM"
        assert r["draft"]["data"]["correctAnswer"] == "A"

    def test_chains_do_not_cross_wire(self, monkeypatch):
        # Forced build_sentence must never produce complete_words / reading_choice data shapes
        # even if LLM returns complete_words payload.
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "data": {
                    "passageText": "civiliza[[1]]",
                    "blanks": [
                        {"id": "1", "prefix": "civiliza", "answer": "tion", "fullWord": "civilization"}
                    ],
                },
            },
        )
        raw = (
            "提问者：What did Maria do?\n"
            "句子模板：____ went to the ____.\n"
            "词库：Maria, store, John, park\n"
            "正确答案：Maria went to the store."
        )
        r = import_pipeline.parse_import(raw, "build_sentence")
        assert r["draft"]["type"] == "build_sentence"
        assert "blanks" not in r["draft"]["data"]
        assert "options" not in r["draft"]["data"]
        assert r["draft"]["data"]["correctOrder"] == ["Maria", "store"]


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


def test_structured_build_sentence_accepts_new_ui_labels():
    raw = (
        "提问者：What did Maria do?\n"
        "题目详情：____ went to the ____.\n"
        "待选词：Maria, store, John, park\n"
        "正确答案：Maria, store\n"
        "解析：Match the subject and destination."
    )
    result = import_pipeline.parse_import(raw, "build_sentence")
    assert result["validation"]["ok"] is True
    draft = result["draft"]
    assert draft["data"]["sentenceTemplate"].count("{{blank}}") == 2
    assert draft["data"]["wordBank"] == ["Maria", "store", "John", "park"]
    assert draft["data"]["correctOrder"] == ["Maria", "store"]
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


# ---------------------------------------------------------------------------
# complete_words LLM failure shapes — must never raise; local recovers
# ---------------------------------------------------------------------------

COMPLETE_WORDS_RAW = (
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
    "exchanged / textiles / metals / distances"
)


class TestCompleteWordsLlmFailureShapes:
    """Every expected-bad LLM payload must yield HTTP-safe 200-path drafts via local."""

    def _assert_local_trade_passage(self, r):
        assert r["draft"]["type"] == "complete_words"
        b = r["draft"]["data"]["blanks"]
        assert len(b) == 4
        assert b[0]["prefix"] == "exc"
        assert b[0]["answer"] == "hanged"
        assert b[0]["fullWord"] == "exchanged"
        assert b[1]["fullWord"] == "textiles"
        assert b[2]["fullWord"] == "metals"
        assert b[3]["fullWord"] == "distances"
        assert r["validation"]["ok"] is True
        assert r["rawText"]  # original not lost

    def test_llm_full_valid_object(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "explanation": "from llm",
                "data": {
                    "passageText": (
                        "Trade in the ancient Middle East played a crucial role in the development of "
                        "civilizations. Merchants exc[[1]] goods such as tex[[2]], spices, and met[[3]] "
                        "across vast dis[[4]]."
                    ),
                    "blanks": [
                        {"id": "1", "prefix": "exc", "answer": "hanged", "fullWord": "exchanged"},
                        {"id": "2", "prefix": "tex", "answer": "tiles", "fullWord": "textiles"},
                        {"id": "3", "prefix": "met", "answer": "als", "fullWord": "metals"},
                        {"id": "4", "prefix": "dis", "answer": "tances", "fullWord": "distances"},
                    ],
                },
            },
        )
        r = import_pipeline.parse_import(COMPLETE_WORDS_RAW, "complete_words")
        self._assert_local_trade_passage(r)

    def test_llm_top_level_array(self, monkeypatch):
        set_llm(monkeypatch, [{"type": "complete_words", "data": {}}])
        r = import_pipeline.parse_import(COMPLETE_WORDS_RAW, "complete_words")
        self._assert_local_trade_passage(r)
        assert any("非对象" in w or "本地" in w for w in r["validation"]["warnings"])

    def test_llm_null_payload(self, monkeypatch):
        # call_llm returns None for null; pipeline must local-fallback
        set_llm(monkeypatch, None, ["LLM 返回了无法解析的内容（null 或空）"])
        r = import_pipeline.parse_import(COMPLETE_WORDS_RAW, "complete_words")
        self._assert_local_trade_passage(r)
        assert any("LLM 解析失败" in w for w in r["validation"]["warnings"])

    def test_llm_string_payload(self, monkeypatch):
        set_llm(monkeypatch, "not a question object")
        r = import_pipeline.parse_import(COMPLETE_WORDS_RAW, "complete_words")
        self._assert_local_trade_passage(r)

    def test_llm_invalid_json_as_none(self, monkeypatch):
        set_llm(monkeypatch, None, ["LLM 解析结果失败：Expecting value"])
        r = import_pipeline.parse_import(COMPLETE_WORDS_RAW, "complete_words")
        self._assert_local_trade_passage(r)

    def test_llm_wrong_type(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "reading_choice",
                "article": "polluted",
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
        r = import_pipeline.parse_import(COMPLETE_WORDS_RAW, "complete_words")
        self._assert_local_trade_passage(r)
        assert any("reading_choice" in w for w in r["validation"]["warnings"])

    def test_llm_missing_type(self, monkeypatch):
        # Missing type is tolerated under forced typeHint when fields look complete
        set_llm(
            monkeypatch,
            {
                "data": {
                    "passageText": (
                        "Trade in the ancient Middle East played a crucial role in the development of "
                        "civilizations. Merchants exc[[1]] goods such as tex[[2]], spices, and met[[3]] "
                        "across vast dis[[4]]."
                    ),
                    "blanks": [
                        {"id": "1", "prefix": "exc", "answer": "hanged", "fullWord": "exchanged"},
                        {"id": "2", "prefix": "tex", "answer": "tiles", "fullWord": "textiles"},
                        {"id": "3", "prefix": "met", "answer": "als", "fullWord": "metals"},
                        {"id": "4", "prefix": "dis", "answer": "tances", "fullWord": "distances"},
                    ],
                },
            },
        )
        r = import_pipeline.parse_import(COMPLETE_WORDS_RAW, "complete_words")
        self._assert_local_trade_passage(r)

    def test_llm_missing_data(self, monkeypatch):
        set_llm(monkeypatch, {"type": "complete_words", "title": "x"})
        r = import_pipeline.parse_import(COMPLETE_WORDS_RAW, "complete_words")
        self._assert_local_trade_passage(r)
        assert any("本地" in w or "不完整" in w for w in r["validation"]["warnings"])

    def test_llm_blanks_contain_non_dict(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "data": {
                    "passageText": "exc[[1]] tex[[2]] met[[3]] dis[[4]]",
                    "blanks": ["hanged", None, 3, {"id": "4", "prefix": "dis", "answer": "tances"}],
                },
            },
        )
        r = import_pipeline.parse_import(COMPLETE_WORDS_RAW, "complete_words")
        self._assert_local_trade_passage(r)

    def test_llm_timeout(self, monkeypatch):
        set_llm(monkeypatch, None, ["LLM 请求超时"])
        r = import_pipeline.parse_import(COMPLETE_WORDS_RAW, "complete_words")
        self._assert_local_trade_passage(r)
        assert any("超时" in w or "LLM 解析失败" in w for w in r["validation"]["warnings"])

    def test_llm_http_error(self, monkeypatch):
        set_llm(monkeypatch, None, ["LLM 返回 HTTP 502：bad gateway"])
        r = import_pipeline.parse_import(COMPLETE_WORDS_RAW, "complete_words")
        self._assert_local_trade_passage(r)

    def test_llm_rewrote_passage_trade_example(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "data": {
                    "passageText": "REWRITTEN exc[[1]] tex[[2]] met[[3]] dis[[4]]",
                    "blanks": [
                        {"id": "1", "prefix": "exc", "answer": "hanged", "fullWord": "exchanged"},
                        {"id": "2", "prefix": "tex", "answer": "tiles", "fullWord": "textiles"},
                        {"id": "3", "prefix": "met", "answer": "als", "fullWord": "metals"},
                        {"id": "4", "prefix": "dis", "answer": "tances", "fullWord": "distances"},
                    ],
                },
            },
        )
        r = import_pipeline.parse_import(COMPLETE_WORDS_RAW, "complete_words")
        assert "REWRITTEN" not in r["draft"]["data"]["passageText"]
        assert "Middle East" in r["draft"]["data"]["passageText"]
        self._assert_local_trade_passage(r)

    def test_llm_missing_blank(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "data": {
                    "passageText": "exc[[1]] tex[[2]] met[[3]]",
                    "blanks": [
                        {"id": "1", "prefix": "exc", "answer": "hanged", "fullWord": "exchanged"},
                        {"id": "2", "prefix": "tex", "answer": "tiles", "fullWord": "textiles"},
                        {"id": "3", "prefix": "met", "answer": "als", "fullWord": "metals"},
                    ],
                },
            },
        )
        r = import_pipeline.parse_import(COMPLETE_WORDS_RAW, "complete_words")
        self._assert_local_trade_passage(r)

    def test_llm_extra_blank(self, monkeypatch):
        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "data": {
                    "passageText": "exc[[1]] tex[[2]] met[[3]] dis[[4]] extra[[5]]",
                    "blanks": [
                        {"id": "1", "prefix": "exc", "answer": "hanged", "fullWord": "exchanged"},
                        {"id": "2", "prefix": "tex", "answer": "tiles", "fullWord": "textiles"},
                        {"id": "3", "prefix": "met", "answer": "als", "fullWord": "metals"},
                        {"id": "4", "prefix": "dis", "answer": "tances", "fullWord": "distances"},
                        {"id": "5", "prefix": "extra", "answer": "xx", "fullWord": "extraxx"},
                    ],
                },
            },
        )
        r = import_pipeline.parse_import(COMPLETE_WORDS_RAW, "complete_words")
        self._assert_local_trade_passage(r)

    def test_parse_import_never_raises_on_merge_bug(self, monkeypatch):
        """Even if merge blows up, parse_import returns a draft."""

        def boom(*_a, **_k):
            raise RuntimeError("simulated merge crash")

        set_llm(
            monkeypatch,
            {
                "type": "complete_words",
                "data": {
                    "passageText": "exc[[1]]",
                    "blanks": [{"id": "1", "prefix": "exc", "answer": "hanged", "fullWord": "exchanged"}],
                },
            },
        )
        original = import_pipeline.ADAPTERS["complete_words"]["merge"]
        import_pipeline.ADAPTERS["complete_words"]["merge"] = boom
        try:
            r = import_pipeline.parse_import(COMPLETE_WORDS_RAW, "complete_words")
        finally:
            import_pipeline.ADAPTERS["complete_words"]["merge"] = original
        assert r["draft"]["type"] == "complete_words"
        assert r["rawText"] == COMPLETE_WORDS_RAW
