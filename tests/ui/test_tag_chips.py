"""tests/ui/test_tag_chips.py — TagSuggestionChips component tests.

Spec requirement (Milestone 6, task 6.3):
  - TagSuggestionChips renders correct number of chips from mock suggestions
  - Clicking unselected chip moves it to "applied" strip
  - Clicking applied chip removes it
  - Pressing Enter in custom tag input adds chip to applied strip

Design approach
---------------
The component renders two rx.foreach loops (one for applied chips, one for
suggestions) behind rx.cond guards (so the sections only appear when non-empty).
Structure tests verify the Foreach/Cond/DebounceInput/Button layout.

State logic tests call the raw EventHandler.fn methods on a minimal mock
object, verifying add/remove/toggle/Enter-to-add behaviour in pure Python
without requiring a running Reflex server.
"""

from __future__ import annotations

import pytest
import reflex as rx

from tests.ui.conftest import collect_types, find_by_type, state_default
from web.components.tag_chips import tag_suggestion_chips
from web.state import AppState


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------


class TestTagChipsSmoke:
    def test_returns_rx_component(self):
        assert isinstance(tag_suggestion_chips(), rx.Component)

    def test_top_level_is_vstack(self):
        comp = tag_suggestion_chips()
        assert type(comp).__name__ == "VStack"


# ---------------------------------------------------------------------------
# Structure — the chip list uses Foreach + Cond
# ---------------------------------------------------------------------------


class TestTagChipsStructure:
    def test_has_two_foreach_loops(self):
        """One Foreach for applied chips, one for suggestion chips."""
        comp = tag_suggestion_chips()
        counts = collect_types(comp)
        assert counts["Foreach"] == 2

    def test_has_two_cond_guards(self):
        """Each chip strip is behind a Cond (renders only when non-empty)."""
        comp = tag_suggestion_chips()
        counts = collect_types(comp)
        assert counts["Cond"] == 2

    def test_has_custom_tag_input(self):
        """A DebounceInput field accepts the custom tag text."""
        comp = tag_suggestion_chips()
        counts = collect_types(comp)
        assert counts["DebounceInput"] == 1

    def test_has_add_button(self):
        """An explicit + Button adds the typed tag."""
        comp = tag_suggestion_chips()
        counts = collect_types(comp)
        assert counts["Button"] >= 1

    def test_has_badge_nodes(self):
        """Chip renderers use Badge components."""
        comp = tag_suggestion_chips()
        counts = collect_types(comp)
        assert counts["Badge"] >= 1

    def test_input_has_on_key_down_trigger(self):
        """The custom tag input wires on_key_down → handle_tag_key_down."""
        comp = tag_suggestion_chips()
        inputs = find_by_type(comp, "DebounceInput")
        assert inputs, "No DebounceInput found"
        inp = inputs[0]
        triggers = getattr(inp, "event_triggers", {})
        assert "on_key_down" in triggers, (
            "DebounceInput missing on_key_down trigger"
        )


# ---------------------------------------------------------------------------
# Applied chips foreach references the correct state var
# ---------------------------------------------------------------------------


class TestTagChipsForeachVars:
    def test_foreach_references_applied_tags_var(self):
        """At least one Foreach iterates over artifact_tags_applied."""
        comp = tag_suggestion_chips()
        foreachs = find_by_type(comp, "Foreach")
        iterables = [str(getattr(f, "iterable", "")) for f in foreachs]
        # The var serialises to a JS expression containing the field name
        assert any("artifact_tags_applied" in s for s in iterables), (
            f"No Foreach references artifact_tags_applied. Iterables: {iterables}"
        )

    def test_foreach_references_suggestions_var(self):
        """At least one Foreach iterates over artifact_tag_suggestions."""
        comp = tag_suggestion_chips()
        foreachs = find_by_type(comp, "Foreach")
        iterables = [str(getattr(f, "iterable", "")) for f in foreachs]
        assert any("artifact_tag_suggestions" in s for s in iterables), (
            f"No Foreach references artifact_tag_suggestions. Iterables: {iterables}"
        )


# ---------------------------------------------------------------------------
# State defaults
# ---------------------------------------------------------------------------


class TestTagChipsStateDefaults:
    def test_artifact_custom_tag_default_is_empty(self):
        assert state_default("artifact_custom_tag") == ""

    def test_artifact_tags_applied_default_is_empty_list(self):
        assert state_default("artifact_tags_applied") == []

    def test_artifact_tag_suggestions_default_is_empty_list(self):
        assert state_default("artifact_tag_suggestions") == []


# ---------------------------------------------------------------------------
# State logic — raw fn calls on mock objects
# ---------------------------------------------------------------------------


class _MockTagState:
    """Minimal mock that mimics the tag-related AppState fields."""

    def __init__(self):
        self.artifact_custom_tag: str = ""
        self.artifact_tags_applied: list[str] = []
        self.artifact_tag_suggestions: list[str] = []


class TestTagChipsStateLogic:
    """Call EventHandler.fn directly on a mock to verify pure logic."""

    def test_set_artifact_custom_tag(self):
        mock = _MockTagState()
        AppState.set_artifact_custom_tag.fn(mock, "finance")
        assert mock.artifact_custom_tag == "finance"

    def test_add_custom_tag_appends_to_applied(self):
        mock = _MockTagState()
        mock.artifact_custom_tag = "finance"
        AppState.add_custom_tag.fn(mock)
        assert "finance" in mock.artifact_tags_applied
        assert mock.artifact_custom_tag == ""  # input cleared

    def test_add_custom_tag_strips_whitespace(self):
        mock = _MockTagState()
        mock.artifact_custom_tag = "  risk  "
        AppState.add_custom_tag.fn(mock)
        assert "risk" in mock.artifact_tags_applied

    def test_add_custom_tag_ignores_empty(self):
        mock = _MockTagState()
        mock.artifact_custom_tag = "   "
        AppState.add_custom_tag.fn(mock)
        assert mock.artifact_tags_applied == []

    def test_add_custom_tag_ignores_duplicate(self):
        mock = _MockTagState()
        mock.artifact_tags_applied = ["finance"]
        mock.artifact_custom_tag = "finance"
        AppState.add_custom_tag.fn(mock)
        assert mock.artifact_tags_applied.count("finance") == 1

    def test_handle_tag_key_down_enter_adds_tag(self):
        """Pressing Enter triggers add_custom_tag.

        handle_tag_key_down calls self.add_custom_tag() on the state object.
        We give the mock a real add_custom_tag implementation so the chained
        call works without a running Reflex server.
        """
        mock = _MockTagState()
        mock.artifact_custom_tag = "legal"

        # Bind the real add_custom_tag logic to the mock
        def _add_custom_tag(self):
            AppState.add_custom_tag.fn(self)

        import types
        mock.add_custom_tag = types.MethodType(_add_custom_tag, mock)

        AppState.handle_tag_key_down.fn(mock, "Enter")
        assert "legal" in mock.artifact_tags_applied

    def test_handle_tag_key_down_other_key_does_nothing(self):
        mock = _MockTagState()
        mock.artifact_custom_tag = "legal"
        AppState.handle_tag_key_down.fn(mock, "Tab")
        assert mock.artifact_tags_applied == []

    def test_toggle_suggestion_tag_adds_when_absent(self):
        mock = _MockTagState()
        AppState.toggle_suggestion_tag.fn(mock, "risk")
        assert "risk" in mock.artifact_tags_applied

    def test_toggle_suggestion_tag_removes_when_present(self):
        mock = _MockTagState()
        mock.artifact_tags_applied = ["risk"]
        AppState.toggle_suggestion_tag.fn(mock, "risk")
        assert "risk" not in mock.artifact_tags_applied

    def test_remove_applied_tag_removes_tag(self):
        mock = _MockTagState()
        mock.artifact_tags_applied = ["risk", "finance"]
        AppState.remove_applied_tag.fn(mock, "risk")
        assert "risk" not in mock.artifact_tags_applied
        assert "finance" in mock.artifact_tags_applied

    def test_remove_applied_tag_noop_if_absent(self):
        mock = _MockTagState()
        mock.artifact_tags_applied = ["finance"]
        AppState.remove_applied_tag.fn(mock, "risk")
        assert mock.artifact_tags_applied == ["finance"]

    def test_multiple_tag_operations_maintain_order(self):
        """Applied tags preserve insertion order."""
        mock = _MockTagState()
        for tag in ["c", "a", "b"]:
            AppState.toggle_suggestion_tag.fn(mock, tag)
        assert mock.artifact_tags_applied == ["c", "a", "b"]
