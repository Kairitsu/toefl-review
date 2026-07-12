"""Unit tests for grade_attempt across all three question types."""

from app import grade_attempt


# ---------------------------------------------------------------------------
# reading_choice
# ---------------------------------------------------------------------------


class TestGradeReadingChoice:
    def _question(self, correct="B"):
        return {
            "type": "reading_choice",
            "data": {
                "correctAnswer": correct,
                "options": [
                    {"key": "A", "text": "A"},
                    {"key": "B", "text": "B"},
                    {"key": "C", "text": "C"},
                    {"key": "D", "text": "D"},
                ],
            },
        }

    def test_all_correct(self):
        ok, detail = grade_attempt(self._question("B"), {"choice": "B"})
        assert ok is True
        assert detail["selected"] == "B"
        assert detail["correctAnswer"] == "B"

    def test_wrong_choice(self):
        ok, detail = grade_attempt(self._question("B"), {"choice": "A"})
        assert ok is False
        assert detail["selected"] == "A"
        assert detail["correctAnswer"] == "B"

    def test_case_insensitive(self):
        """Lowercase input is normalized to uppercase before compare."""
        ok, detail = grade_attempt(self._question("B"), {"choice": "b"})
        assert ok is True
        assert detail["selected"] == "B"


# ---------------------------------------------------------------------------
# build_sentence
# ---------------------------------------------------------------------------


class TestGradeBuildSentence:
    def _question(self):
        return {
            "type": "build_sentence",
            "data": {
                "sentenceTemplate": "{{blank}} went to the {{blank}}.",
                "wordBank": ["Maria", "store", "John", "park"],
                "correctOrder": ["Maria", "store"],
                "completeSentence": "Maria went to the store.",
            },
        }

    def test_all_correct(self):
        ok, detail = grade_attempt(
            self._question(),
            {"order": ["Maria", "store"]},
        )
        assert ok is True
        assert all(p["correct"] for p in detail["positions"])
        assert detail["submittedSentence"] == "Maria went to the store."

    def test_partially_wrong(self):
        ok, detail = grade_attempt(
            self._question(),
            {"order": ["Maria", "park"]},
        )
        assert ok is False
        assert detail["positions"][0]["correct"] is True
        assert detail["positions"][1]["correct"] is False
        assert detail["positions"][1]["actual"] == "park"
        assert detail["positions"][1]["expected"] == "store"

    def test_case_insensitive(self):
        ok, detail = grade_attempt(
            self._question(),
            {"order": ["maria", "STORE"]},
        )
        assert ok is True
        assert all(p["correct"] for p in detail["positions"])


# ---------------------------------------------------------------------------
# complete_words
# ---------------------------------------------------------------------------


class TestGradeCompleteWords:
    def _question(self):
        return {
            "type": "complete_words",
            "data": {
                "passageText": "The civiliza[[1]] built sys[[2]].",
                "blanks": [
                    {
                        "id": "1",
                        "prefix": "civiliza",
                        "answer": "tion",
                        "fullWord": "civilization",
                        "blankLength": 4,
                    },
                    {
                        "id": "2",
                        "prefix": "sys",
                        "answer": "tems",
                        "fullWord": "systems",
                        "blankLength": 4,
                    },
                ],
                "completePassage": "The civilization built systems.",
            },
        }

    def test_all_correct(self):
        ok, detail = grade_attempt(
            self._question(),
            {"blanks": {"1": "tion", "2": "tems"}},
        )
        assert ok is True
        assert all(b["correct"] for b in detail["blanks"])

    def test_partially_wrong(self):
        ok, detail = grade_attempt(
            self._question(),
            {"blanks": {"1": "tion", "2": "tem"}},
        )
        assert ok is False
        by_id = {b["id"]: b for b in detail["blanks"]}
        assert by_id["1"]["correct"] is True
        assert by_id["2"]["correct"] is False

    def test_case_insensitive(self):
        ok, detail = grade_attempt(
            self._question(),
            {"blanks": {"1": "TION", "2": "Tems"}},
        )
        assert ok is True
        assert all(b["correct"] for b in detail["blanks"])
