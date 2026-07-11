"""Unit tests for import/parse pure helpers (no Flask, no DB)."""

import pytest

from app import (
    count_template_blanks,
    extract_json_object,
    match_answers_to_underscore_blanks,
    normalize_build_data,
    normalize_sentence_template,
    parse_template_segments,
    render_sentence_from_template,
    scan_underscore_blanks,
)


# ---------------------------------------------------------------------------
# normalize_sentence_template
# ---------------------------------------------------------------------------


class TestNormalizeSentenceTemplate:
    def test_normal_blank_and_underscores(self):
        result = normalize_sentence_template("She ____ to the {{ 1 }}.")
        assert result == "She {{blank}} to the {{blank}}."

    def test_empty_and_whitespace(self):
        assert normalize_sentence_template("") == ""
        assert normalize_sentence_template("   ") == ""
        assert normalize_sentence_template(None) == ""


# ---------------------------------------------------------------------------
# count_template_blanks
# ---------------------------------------------------------------------------


class TestCountTemplateBlanks:
    def test_normal_count(self):
        assert count_template_blanks("{{blank}} went {{blank}} the {{blank}}.") == 3
        assert count_template_blanks("A ____ B ____") == 2

    def test_no_blanks_or_empty(self):
        assert count_template_blanks("no blanks here") == 0
        assert count_template_blanks("") == 0
        assert count_template_blanks(None) == 0


# ---------------------------------------------------------------------------
# render_sentence_from_template
# ---------------------------------------------------------------------------


class TestRenderSentenceFromTemplate:
    def test_normal_fill(self):
        sentence = render_sentence_from_template(
            "{{blank}} went to the {{blank}}.",
            ["Maria", "store"],
        )
        assert sentence == "Maria went to the store."

    def test_missing_tokens_leave_empty_slots(self):
        sentence = render_sentence_from_template(
            "{{blank}} and {{blank}}.",
            ["only"],
        )
        # Second blank has no token → empty string, trailing punctuation kept
        assert sentence == "only and."


# ---------------------------------------------------------------------------
# parse_template_segments
# ---------------------------------------------------------------------------


class TestParseTemplateSegments:
    def test_normal_mixed_segments(self):
        segments = parse_template_segments("{{blank}} during the {{blank}}.")
        assert segments == [
            {"type": "blank", "index": 1},
            {"type": "fixed", "text": " during the "},
            {"type": "blank", "index": 2},
            {"type": "fixed", "text": "."},
        ]

    def test_no_blanks_single_fixed(self):
        segments = parse_template_segments("Hello world.")
        assert segments == [{"type": "fixed", "text": "Hello world."}]

    def test_empty_template(self):
        assert parse_template_segments("") == []


# ---------------------------------------------------------------------------
# scan_underscore_blanks
# ---------------------------------------------------------------------------


class TestScanUnderscoreBlanks:
    def test_normal_passage(self):
        result = scan_underscore_blanks("The civiliza____ was advanced.")
        assert result["passageText"] == "The civiliza[[1]] was advanced."
        assert len(result["blanks"]) == 1
        assert result["blanks"][0]["prefix"] == "civiliza"
        assert result["blanks"][0]["blankLength"] == 4

    def test_no_underscores(self):
        result = scan_underscore_blanks("A complete sentence with no blanks.")
        assert result["blanks"] == []
        assert result["passageText"] == "A complete sentence with no blanks."


# ---------------------------------------------------------------------------
# match_answers_to_underscore_blanks
# ---------------------------------------------------------------------------


class TestMatchAnswersToUnderscoreBlanks:
    def test_normal_match(self):
        result = match_answers_to_underscore_blanks(
            "The civiliza____ built sys____.",
            ["tion", "tems"],
        )
        assert result["errors"] == []
        assert len(result["blanks"]) == 2
        assert result["blanks"][0]["fullWord"] == "civilization"
        assert result["blanks"][1]["fullWord"] == "systems"
        assert "civiliza[[1]]" in result["passageText"]
        assert "sys[[2]]" in result["passageText"]

    def test_count_mismatch_errors(self):
        result = match_answers_to_underscore_blanks(
            "Only one ne____ blank.",
            ["ver", "extra"],
        )
        assert result["errors"]
        assert "不一致" in result["errors"][0]

    def test_no_blanks_errors(self):
        result = match_answers_to_underscore_blanks("No blanks here.", ["tion"])
        assert result["errors"]
        assert result["blanks"] == []


# ---------------------------------------------------------------------------
# normalize_build_data
# ---------------------------------------------------------------------------


class TestNormalizeBuildData:
    def test_normal_template_and_order(self):
        data = normalize_build_data(
            {
                "sentenceTemplate": "____ went to the ____.",
                "wordBank": ["Maria", "store", "John"],
                "correctOrder": ["Maria", "store"],
            }
        )
        assert data["sentenceTemplate"] == "{{blank}} went to the {{blank}}."
        assert data["wordBank"] == ["Maria", "store", "John"]
        assert data["correctOrder"] == ["Maria", "store"]
        assert data["completeSentence"] == "Maria went to the store."
        assert any(seg["type"] == "blank" for seg in data["templateSegments"])

    def test_empty_input(self):
        data = normalize_build_data({})
        assert data["sentenceTemplate"] == ""
        assert data["wordBank"] == []
        assert data["correctOrder"] == []
        assert data["completeSentence"] == ""
        assert data["templateSegments"] == []


# ---------------------------------------------------------------------------
# extract_json_object
# ---------------------------------------------------------------------------


class TestExtractJsonObject:
    def test_plain_json(self):
        raw = '{"type": "reading_choice", "prompt": "Why?", "data": {"correctAnswer": "A"}}'
        result = extract_json_object(raw)
        assert result["type"] == "reading_choice"
        assert result["prompt"] == "Why?"
        assert result["data"]["correctAnswer"] == "A"

    def test_fenced_json_code_block(self):
        raw = """Here is the result:
```json
{"type": "build_sentence", "prompt": "What happened?", "data": {"wordBank": ["a", "b"]}}
```
"""
        result = extract_json_object(raw)
        assert result["type"] == "build_sentence"
        assert result["data"]["wordBank"] == ["a", "b"]

    def test_nested_under_other_key(self):
        raw = """{
  "status": "ok",
  "question": {
    "type": "complete_words",
    "article": "Hello",
    "data": {"blanks": []}
  }
}"""
        result = extract_json_object(raw)
        assert result["type"] == "complete_words"
        assert result["article"] == "Hello"

    def test_not_json_raises(self):
        with pytest.raises(ValueError, match="不是可解析的 JSON|必须是对象"):
            extract_json_object("This is just plain prose with no braces at all.")
