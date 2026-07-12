"""
Frontend regression: import page type <select> must not be destroyed on click.

Root cause fixed: document click delegation used to run setImportTypeHint /
changeFormType on <select> click, which re-rendered the whole import page and
closed the native option list immediately. Only the change event may update type.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_main_js_ignores_select_on_click_delegation():
    """Static guard: click handler must not dispatch data-action for <select>."""
    main = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
    assert "shouldIgnoreClickAction" in main
    assert "select[data-action]" in main
    # Checkbox skip retained; select skip is the regression under test
    assert "input[type=\"checkbox\"][data-action]" in main or "input[type='checkbox'][data-action]" in main
    # Comment documents why (so future edits do not reintroduce click→render)
    assert "renderImport" in main or "native" in main.lower() or "option list" in main.lower()


def test_set_import_type_hint_skips_noop_and_preserves_fields():
    """setImportTypeHint must no-op on same type and keep per-type snapshots."""
    src = (ROOT / "static" / "js" / "views" / "import_view.js").read_text(encoding="utf-8")
    assert "function setImportTypeHint" in src
    assert "nextType === previousType" in src
    assert "importRawByType" in src
    assert "buildSentenceRawFields" in src
    # Must not reintroduce clobber: parseReadingChoiceRawFields(state.importRaw) on every switch
    # after leaving another type without type-scoped storage.
    assert "state.readingChoiceRawFields = parseReadingChoiceRawFields(state.importRaw)" not in src


def test_change_form_type_skips_same_type():
    src = (ROOT / "static" / "js" / "views" / "import_view.js").read_text(encoding="utf-8")
    assert "function changeFormType" in src
    assert "currentDraft.type === nextType" in src


def test_state_has_per_type_raw_buckets():
    src = (ROOT / "static" / "js" / "state.js").read_text(encoding="utf-8")
    assert "importRawByType" in src
    assert "buildSentenceRawFields" in src


def test_build_sentence_import_preview_is_read_only_and_saves_parsed_draft():
    """Build imports render one summary and save the normalized parser result."""
    src = (ROOT / "static" / "js" / "views" / "import_view.js").read_text(encoding="utf-8")
    assert 'scope === "import" && q.type === "build_sentence"' in src
    assert "return state.importDraft ? buildImportSummaryHtml(q)" in src
    assert 'state.importDraft?.type === "build_sentence"' in src
    assert "return normalizeFormQuestion(state.importDraft)" in src
    assert '<span class="k">题目详情</span>' in src
    assert '<span class="k">待选词</span>' in src


def test_build_sentence_user_facing_labels_are_unified():
    state_src = (ROOT / "static" / "js" / "state.js").read_text(encoding="utf-8")
    practice_src = (ROOT / "static" / "js" / "views" / "practice_view.js").read_text(encoding="utf-8")
    assert 'label: "题目详情"' in state_src
    assert 'label: "待选词"' in state_src
    assert "<h3>待选词</h3>" in practice_src
    assert '<div class="bs-section-label">题目详情</div>' in practice_src
    assert '<div class="report-field-label">题目详情</div>' in practice_src
    assert '<div class="report-field-label">待选词</div>' in practice_src


def test_library_has_no_persisted_pending_confirmation_label():
    library_src = (ROOT / "static" / "js" / "views" / "library_view.js").read_text(encoding="utf-8")
    import_src = (ROOT / "static" / "js" / "views" / "import_view.js").read_text(encoding="utf-8")
    assert "待确认" not in library_src
    assert "question.needsConfirmation = false" in import_src


def test_reading_choice_raw_input_is_merged_and_preview_is_read_only():
    state_src = (ROOT / "static" / "js" / "state.js").read_text(encoding="utf-8")
    import_src = (ROOT / "static" / "js" / "views" / "import_view.js").read_text(encoding="utf-8")
    assert 'key: "questionAndOptions"' in state_src
    assert 'label: "问题与选项"' in state_src
    assert 'key: "question", label: "问题"' not in state_src
    assert 'key: "options"' not in state_src
    assert 'scope === "import" && q.type === "reading_choice"' in import_src
    assert "return state.importDraft ? readingImportPreviewHtml(q)" in import_src
    assert "function readingImportPreviewHtml" in import_src
    assert '<div class="reading-preview-label">阅读文章</div>' in import_src
    assert '<div class="reading-preview-label">问题</div>' in import_src
    assert "collectQuestionForm" in import_src
    assert 'state.importDraft?.type === "reading_choice"' in import_src
    assert "readingSaveBlocked" in import_src
