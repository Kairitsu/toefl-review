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
