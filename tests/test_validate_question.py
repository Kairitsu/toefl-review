"""
Boundary tests for validate_question.

These cover cases that *should* produce errors. If actual behavior diverges
from expectation, the test fails so the difference is visible — we do not
change app.py business logic to make tests pass.
"""

from app import validate_question


class TestValidateReadingChoice:
    def test_invalid_correct_answer_letter(self):
        """correctAnswer must be A/B/C/D — 'E' should be rejected."""
        question = {
            "type": "reading_choice",
            "article": "Some passage text.",
            "prompt": "What is the answer?",
            "data": {
                "options": [
                    {"key": "A", "text": "One"},
                    {"key": "B", "text": "Two"},
                    {"key": "C", "text": "Three"},
                    {"key": "D", "text": "Four"},
                ],
                "correctAnswer": "E",
            },
        }
        result = validate_question(question)
        assert result["ok"] is False
        assert any("正确答案" in e for e in result["errors"])

    def test_empty_option_text(self):
        """Empty option text should be rejected."""
        question = {
            "type": "reading_choice",
            "article": "Some passage text.",
            "prompt": "What is the answer?",
            "data": {
                "options": [
                    {"key": "A", "text": "One"},
                    {"key": "B", "text": ""},
                    {"key": "C", "text": "Three"},
                    {"key": "D", "text": "Four"},
                ],
                "correctAnswer": "A",
            },
        }
        result = validate_question(question)
        assert result["ok"] is False
        assert any("选项" in e and "不能为空" in e for e in result["errors"])


class TestValidateBuildSentence:
    def test_correct_order_word_not_in_bank(self):
        """
        correctOrder contains a token absent from wordBank.
        Expected: error (currently implemented).
        """
        question = {
            "type": "build_sentence",
            "prompt": "What did she do?",
            "data": {
                "sentenceTemplate": "{{blank}} is {{blank}}.",
                "wordBank": ["She", "happy", "He"],
                "correctOrder": ["She", "sad"],  # "sad" not in word bank
                "completeSentence": "She is sad.",
            },
        }
        result = validate_question(question)
        assert result["ok"] is False
        assert any("不在词库" in e for e in result["errors"]), (
            f"Expected 'not in word bank' error, got: {result['errors']}"
        )

    def test_blank_count_mismatch_with_order(self):
        """Template blank count must equal correctOrder length."""
        question = {
            "type": "build_sentence",
            "prompt": "What did she do?",
            "data": {
                "sentenceTemplate": "{{blank}} is {{blank}}.",
                "wordBank": ["She", "happy", "very"],
                "correctOrder": ["She"],  # only 1 item for 2 blanks
                "completeSentence": "She is happy.",
            },
        }
        result = validate_question(question)
        assert result["ok"] is False
        assert any("空格数" in e or "正确顺序" in e for e in result["errors"])


class TestValidateCompleteWords:
    def test_prefix_does_not_match_full_word(self):
        """
        fullWord does not start with prefix.
        Expected: error (currently implemented).
        """
        question = {
            "type": "complete_words",
            "data": {
                "passageText": "The civiliza[[1]] was advanced.",
                "blanks": [
                    {
                        "id": "1",
                        "prefix": "civiliza",
                        "answer": "tion",
                        "fullWord": "happiness",  # does not start with civiliza
                        "blankLength": 4,
                    }
                ],
            },
        }
        result = validate_question(question)
        assert result["ok"] is False
        assert any("不以前缀" in e or "前缀" in e for e in result["errors"]), (
            f"Expected prefix mismatch error, got: {result['errors']}"
        )

    def test_prefix_plus_answer_not_equal_full_word(self):
        """
        fullWord starts with prefix, but prefix+answer ≠ fullWord.
        Expected: error (currently implemented).
        """
        question = {
            "type": "complete_words",
            "data": {
                "passageText": "The civiliza[[1]] was advanced.",
                "blanks": [
                    {
                        "id": "1",
                        "prefix": "civiliza",
                        "answer": "tion",
                        "fullWord": "civilizations",  # extra 's'
                        "blankLength": 4,
                    }
                ],
            },
        }
        result = validate_question(question)
        assert result["ok"] is False
        assert any("≠" in e or "完整词" in e for e in result["errors"]), (
            f"Expected prefix+answer ≠ fullWord error, got: {result['errors']}"
        )
