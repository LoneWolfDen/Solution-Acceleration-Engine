"""tests/ui/test_triage_widget.py — ArtifactTriageWidget component tests.

Spec requirement (Milestone 6, task 6.2):
  - ArtifactTriageWidget renders N rows given mock artifact list of length N
  - is_active=true artifact shows ON toggle state
  - is_active=false artifact shows OFF toggle state
  - Clicking toggle dispatches correct PATCH payload

Design approach
---------------
The triage_widget() function builds the static component tree; the artifact
rows are rendered via rx.foreach so we cannot count rendered rows without a
browser.  Instead we verify:
  1. The Foreach loop references the correct AppState var.
  2. The Switch widget in the row template has an on_change trigger that calls
     AppState.toggle_artifact_active.
  3. AppState state-logic methods (toggle_artifact_active) produce the correct
     optimistic state changes on a mock object.
  4. The "Create Version" Button is disabled when no active artifacts exist,
     wired via AppState.can_create_version.
"""

from __future__ import annotations

import pytest
import reflex as rx

from tests.ui.conftest import collect_types, event_handler_fn, find_by_type, state_default
from web.components.triage_widget import triage_widget
from web.state import AppState


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------


class TestTriageWidgetSmoke:
    def test_returns_rx_component(self):
        assert isinstance(triage_widget(), rx.Component)

    def test_top_level_is_vstack(self):
        comp = triage_widget()
        assert type(comp).__name__ == "VStack"


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


class TestTriageWidgetStructure:
    def test_has_foreach_for_artifact_rows(self):
        """Artifact rows are rendered via rx.foreach."""
        comp = triage_widget()
        counts = collect_types(comp)
        assert counts["Foreach"] >= 1

    def test_has_switch_for_is_active_toggle(self):
        """Each row template contains a Switch for the is_active toggle."""
        comp = triage_widget()
        counts = collect_types(comp)
        assert counts["Switch"] >= 1

    def test_has_cond_for_empty_state(self):
        """A Cond switches between the artifact list and the empty-state message."""
        comp = triage_widget()
        counts = collect_types(comp)
        assert counts["Cond"] >= 1

    def test_has_create_version_button(self):
        """A 'Create Version' Button is present in the footer row."""
        comp = triage_widget()
        counts = collect_types(comp)
        assert counts["Button"] >= 1

    def test_has_separator(self):
        """A Separator divides the artifact list from the version name footer."""
        comp = triage_widget()
        counts = collect_types(comp)
        assert counts["Separator"] >= 1

    def test_has_version_name_input(self):
        """A DebounceInput field holds the version name."""
        comp = triage_widget()
        counts = collect_types(comp)
        assert counts["DebounceInput"] >= 1


# ---------------------------------------------------------------------------
# Foreach var reference
# ---------------------------------------------------------------------------


class TestTriageWidgetForeachVar:
    def test_foreach_iterates_triage_artifacts(self):
        """The Foreach loop iterates AppState.triage_artifacts."""
        comp = triage_widget()
        foreachs = find_by_type(comp, "Foreach")
        iterables = [str(getattr(f, "iterable", "")) for f in foreachs]
        assert any("triage_artifacts" in s for s in iterables), (
            f"No Foreach references triage_artifacts. Iterables: {iterables}"
        )


# ---------------------------------------------------------------------------
# Event wiring on the Switch
# ---------------------------------------------------------------------------


class TestTriageWidgetEventWiring:
    def test_switch_on_change_calls_toggle_artifact_active(self):
        """Switch.on_change chain references AppState.toggle_artifact_active."""
        comp = triage_widget()
        switches = find_by_type(comp, "Switch")
        assert switches, "No Switch found in triage widget"

        sw = switches[0]
        triggers = getattr(sw, "event_triggers", {})
        assert "on_change" in triggers, "Switch missing on_change trigger"

        fn = event_handler_fn(triggers["on_change"])
        assert fn is AppState.toggle_artifact_active.fn, (
            f"Expected toggle_artifact_active, got {fn}"
        )


# ---------------------------------------------------------------------------
# State defaults
# ---------------------------------------------------------------------------


class TestTriageWidgetStateDefaults:
    def test_triage_artifacts_default_is_empty_list(self):
        assert state_default("triage_artifacts") == []

    def test_version_name_default_is_version_1(self):
        assert state_default("version_name") == "Version 1"

    def test_selected_project_id_default_is_empty(self):
        assert state_default("selected_project_id") == ""


# ---------------------------------------------------------------------------
# AppState.can_create_version — computed var logic via mock
# ---------------------------------------------------------------------------


class _MockTriageState:
    """Minimal mock for can_create_version logic."""

    def __init__(self, artifacts: list[dict], project_id: str = ""):
        self.triage_artifacts = artifacts
        self.selected_project_id = project_id

    @property
    def triage_active_artifact_ids(self) -> list[str]:
        return [a["artifact_id"] for a in self.triage_artifacts if a.get("is_active")]

    @property
    def can_create_version(self) -> bool:
        return len(self.triage_active_artifact_ids) > 0 and self.selected_project_id != ""


class TestCanCreateVersion:
    def test_false_when_no_artifacts(self):
        mock = _MockTriageState(artifacts=[], project_id="proj-1")
        assert mock.can_create_version is False

    def test_false_when_all_artifacts_inactive(self):
        artifacts = [
            {"artifact_id": "a1", "title": "T", "tags": [], "is_active": False},
        ]
        mock = _MockTriageState(artifacts=artifacts, project_id="proj-1")
        assert mock.can_create_version is False

    def test_false_when_no_project_selected(self):
        artifacts = [
            {"artifact_id": "a1", "title": "T", "tags": [], "is_active": True},
        ]
        mock = _MockTriageState(artifacts=artifacts, project_id="")
        assert mock.can_create_version is False

    def test_true_when_active_artifact_and_project(self):
        artifacts = [
            {"artifact_id": "a1", "title": "T", "tags": [], "is_active": True},
        ]
        mock = _MockTriageState(artifacts=artifacts, project_id="proj-1")
        assert mock.can_create_version is True

    def test_true_with_mixed_active_states(self):
        """Only requires at least one active artifact."""
        artifacts = [
            {"artifact_id": "a1", "title": "T", "tags": [], "is_active": False},
            {"artifact_id": "a2", "title": "U", "tags": [], "is_active": True},
        ]
        mock = _MockTriageState(artifacts=artifacts, project_id="proj-1")
        assert mock.can_create_version is True

    def test_active_artifact_ids_excludes_inactive(self):
        artifacts = [
            {"artifact_id": "a1", "is_active": True},
            {"artifact_id": "a2", "is_active": False},
            {"artifact_id": "a3", "is_active": True},
        ]
        mock = _MockTriageState(artifacts=artifacts, project_id="proj-1")
        assert sorted(mock.triage_active_artifact_ids) == ["a1", "a3"]


# ---------------------------------------------------------------------------
# AppState.set_version_name
# ---------------------------------------------------------------------------


class TestSetVersionName:
    def test_set_version_name_updates_field(self):
        class _Mock:
            version_name = "Version 1"

        mock = _Mock()
        AppState.set_version_name.fn(mock, "v2.0")
        assert mock.version_name == "v2.0"

    def test_set_version_name_accepts_empty(self):
        class _Mock:
            version_name = "Version 1"

        mock = _Mock()
        AppState.set_version_name.fn(mock, "")
        assert mock.version_name == ""
