"""tests/test_navigate_to_artifact.py — Unit tests for AppState.navigate_to_artifact.

Covers Requirement C3.1/C3.2/C3.3: resolving a finding's source_artifact
(title/path) to an artifact_id within current_version_artifacts, and the
toast fallback when no match is found.

AppState is a Reflex ``rx.State`` subclass — end users are forbidden from
instantiating it directly (``ReflexRuntimeError``), but tests can pass
``_reflex_internal_init=True`` to bypass that guard, matching the framework's
own internal test pattern.  ``navigate_to_artifact`` is a plain synchronous
method with no httpx calls, so this is pure-Python and testable without a
running Reflex app or backend.
"""

from __future__ import annotations

from web.state import AppState


def _make_state(artifacts: list[dict]) -> AppState:
    state = AppState(_reflex_internal_init=True)
    state.selected_version = {"artifacts": artifacts}
    return state


def test_navigate_to_artifact_matching_title_sets_selected_artifact_id():
    state = _make_state(
        [
            {"artifact_id": "a1", "title": "Doc One"},
            {"artifact_id": "a2", "title": "Doc Two"},
        ]
    )
    state.navigate_to_artifact("Doc Two")
    assert state.selected_artifact_id == "a2"
    assert state.toast_message == ""
    assert state.toast_is_error is False


def test_navigate_to_artifact_first_match_wins_when_titles_present():
    state = _make_state(
        [
            {"artifact_id": "a1", "title": "Doc One"},
        ]
    )
    state.navigate_to_artifact("Doc One")
    assert state.selected_artifact_id == "a1"


def test_navigate_to_artifact_no_match_clears_selection_and_shows_toast():
    state = _make_state(
        [
            {"artifact_id": "a1", "title": "Doc One"},
        ]
    )
    state.navigate_to_artifact("unknown")
    assert state.selected_artifact_id == ""
    assert state.toast_is_error is True
    assert "No matching artifact found" in state.toast_message


def test_navigate_to_artifact_empty_artifact_list_shows_toast():
    state = _make_state([])
    state.navigate_to_artifact("Doc One")
    assert state.selected_artifact_id == ""
    assert state.toast_is_error is True


def test_navigate_to_artifact_resets_previous_selection_on_no_match():
    """A prior successful selection must be cleared when a later call fails
    to resolve, rather than leaving a stale selected_artifact_id."""
    state = _make_state(
        [
            {"artifact_id": "a1", "title": "Doc One"},
        ]
    )
    state.navigate_to_artifact("Doc One")
    assert state.selected_artifact_id == "a1"

    state.navigate_to_artifact("Nonexistent")
    assert state.selected_artifact_id == ""
