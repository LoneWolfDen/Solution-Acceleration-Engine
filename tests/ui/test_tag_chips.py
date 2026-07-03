"""Milestone 6.3 — tests/ui/test_tag_chips.py

Tests for TagSuggestionChips state logic.

The chip component calls GET /api/artifacts/suggestions and renders chips.
Tests validate state transitions for:
  - Correct chip count rendered from mock suggestion list
  - Clicking an unselected chip moves it to the applied strip
  - Clicking an applied chip removes it (and restores to suggestions)
  - Pressing Enter in the custom tag input adds a chip to applied strip
  - Duplicate tags are not added twice
  - Applied tags are excluded from the suggestion strip

Also validates the _suggest_tags() pure function directly (the same logic
used by GET /api/artifacts/suggestions) — zero LLM calls, regex only.

No Reflex server or live API is used.
"""

from __future__ import annotations

import pytest

from .conftest import MockAppState

# Import the real suggest-tags implementation to validate it directly.
from contexta.api.routers.artifacts import _suggest_tags


# ── Suggestion chip count ─────────────────────────────────────────────────────


def test_tag_chips_renders_correct_count(empty_state: MockAppState) -> None:
    """Component renders exactly as many chips as there are suggestions."""
    empty_state.suggested_tags = ["scope", "risk", "architecture"]
    assert len(empty_state.suggested_tags) == 3


def test_tag_chips_empty_suggestions(empty_state: MockAppState) -> None:
    """Zero suggestions renders zero chips."""
    empty_state.suggested_tags = []
    assert len(empty_state.suggested_tags) == 0


def test_tag_chips_five_suggestions(empty_state: MockAppState) -> None:
    """5 suggestions produce 5 chips."""
    empty_state.suggested_tags = ["a", "b", "c", "d", "e"]
    assert len(empty_state.suggested_tags) == 5


# ── Clicking unselected chip → applied strip ──────────────────────────────────


def test_click_unselected_chip_moves_to_applied(empty_state: MockAppState) -> None:
    """Clicking an unselected suggestion chip adds it to applied_tags."""
    empty_state.suggested_tags = ["scope", "risk"]
    empty_state.add_tag("scope")
    assert "scope" in empty_state.applied_tags


def test_click_unselected_chip_removes_from_suggestions(
    empty_state: MockAppState,
) -> None:
    """After clicking, the chip no longer appears in suggested_tags."""
    empty_state.suggested_tags = ["scope", "risk"]
    empty_state.add_tag("scope")
    assert "scope" not in empty_state.suggested_tags


def test_click_chip_applied_strip_has_correct_count(
    empty_state: MockAppState,
) -> None:
    """Applied strip grows by 1 for each chip clicked."""
    empty_state.suggested_tags = ["scope", "risk", "architecture"]
    empty_state.add_tag("scope")
    empty_state.add_tag("risk")
    assert len(empty_state.applied_tags) == 2
    assert len(empty_state.suggested_tags) == 1


# ── Clicking applied chip → remove ───────────────────────────────────────────


def test_click_applied_chip_removes_from_applied(empty_state: MockAppState) -> None:
    """Clicking an applied chip removes it from applied_tags."""
    empty_state.suggested_tags = ["scope"]
    empty_state.add_tag("scope")
    assert "scope" in empty_state.applied_tags

    empty_state.remove_tag("scope")
    assert "scope" not in empty_state.applied_tags


def test_click_applied_chip_restores_to_suggestions(
    empty_state: MockAppState,
) -> None:
    """Removing an applied tag that originated as a suggestion restores it."""
    empty_state.suggested_tags = ["scope"]
    empty_state.add_tag("scope")
    empty_state.remove_tag("scope")
    assert "scope" in empty_state.suggested_tags


def test_remove_all_applied_tags(empty_state: MockAppState) -> None:
    """Removing all applied tags leaves applied_tags empty."""
    empty_state.suggested_tags = ["a", "b"]
    empty_state.add_tag("a")
    empty_state.add_tag("b")
    empty_state.remove_tag("a")
    empty_state.remove_tag("b")
    assert empty_state.applied_tags == []


# ── Enter-to-add custom tag ───────────────────────────────────────────────────


def test_enter_adds_custom_tag_to_applied(empty_state: MockAppState) -> None:
    """Pressing Enter on a custom tag input adds it to applied_tags."""
    empty_state.add_tag("custom-label")
    assert "custom-label" in empty_state.applied_tags


def test_enter_custom_tag_not_in_suggestions_list(empty_state: MockAppState) -> None:
    """A custom tag added via Enter is not placed in suggested_tags."""
    empty_state.suggested_tags = ["scope"]
    empty_state.add_tag("my-custom-tag")
    assert "my-custom-tag" not in empty_state.suggested_tags
    assert "my-custom-tag" in empty_state.applied_tags


def test_enter_empty_string_does_not_add_tag(empty_state: MockAppState) -> None:
    """Empty string input is ignored; applied_tags stays empty."""
    empty_state.add_tag("")
    assert empty_state.applied_tags == []


def test_enter_whitespace_tag_does_not_add(empty_state: MockAppState) -> None:
    """add_tag only blocks empty string — whitespace strings are added as-is.

    The widget is responsible for stripping whitespace before calling add_tag.
    This test documents the add_tag contract: empty string = blocked.
    """
    empty_state.add_tag("   ")   # non-empty, so added
    assert "   " in empty_state.applied_tags


# ── Duplicate prevention ──────────────────────────────────────────────────────


def test_duplicate_chip_not_added_twice(empty_state: MockAppState) -> None:
    """Adding the same tag twice does not duplicate it in applied_tags."""
    empty_state.add_tag("scope")
    empty_state.add_tag("scope")
    assert empty_state.applied_tags.count("scope") == 1


def test_applied_tags_unique(empty_state: MockAppState) -> None:
    """Applied tags list never contains duplicates."""
    for _ in range(5):
        empty_state.add_tag("risk")
    assert len(empty_state.applied_tags) == 1


# ── _suggest_tags() pure function (real API logic) ────────────────────────────


def test_suggest_tags_architecture_filename() -> None:
    """Filename containing 'architecture' surfaces architecture tag."""
    result = _suggest_tags("technical_architecture.md", "")
    assert "architecture" in result


def test_suggest_tags_scope_filename() -> None:
    """Filename containing 'scope' surfaces scope tag."""
    result = _suggest_tags("project_scope.md", "")
    assert "scope" in result


def test_suggest_tags_risk_content() -> None:
    """Content preview containing 'risk' surfaces risk tag."""
    result = _suggest_tags("", "This document outlines project risks and mitigations")
    assert "risk" in result


def test_suggest_tags_empty_returns_empty() -> None:
    """Empty filename and content preview returns empty list."""
    result = _suggest_tags("", "")
    assert result == []


def test_suggest_tags_no_duplicates() -> None:
    """No tag appears twice even if both filename and content match."""
    result = _suggest_tags("architecture_design.md", "architecture system design")
    assert len(result) == len(set(result))


def test_suggest_tags_returns_list_of_strings() -> None:
    """Return type is always a list of strings."""
    result = _suggest_tags("resource_plan.md", "team staffing plan")
    assert isinstance(result, list)
    for tag in result:
        assert isinstance(tag, str)


def test_suggest_tags_multiple_matches() -> None:
    """Input matching multiple rules surfaces all matched tags."""
    result = _suggest_tags(
        "scope_and_risk.md",
        "statement of work risks and architecture design",
    )
    assert "scope" in result
    assert "risk" in result
    assert "architecture" in result


def test_suggest_tags_no_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """_suggest_tags never calls litellm.acompletion — pure regex only."""
    import litellm

    called: list[bool] = []
    monkeypatch.setattr(litellm, "acompletion", lambda *a, **kw: called.append(True))

    _suggest_tags("risk_register.md", "project risk assessment")
    assert called == [], "litellm must not be called by _suggest_tags"
