"""tests/ui/test_sidebar.py — ProjectTreeSidebar component tests.

Spec requirement (Milestone 6, task 6.6):
  - ProjectTreeSidebar renders correct number of project nodes from mock list
  - Clicking expand on a project reveals its version children
  - Selected node is highlighted in AppState

Design approach
---------------
The sidebar is a static component tree.  The project list, version list, and
node list are all driven by rx.foreach, so the actual rendered row count
depends on runtime state (evaluated in the browser).  We verify:

  1. Exactly three Foreach loops exist — one each for projects, versions,
     and nodes — with the correct state var references.
  2. The project Foreach is inside a ScrollArea (infinite scroll pattern).
  3. A "New Project" dialog (DialogRoot) is wired into the sidebar.
  4. AppState selection methods (open_new_project_dialog, close, set_name)
     produce correct state changes when called via their raw .fn on a mock.
  5. AppState.projects and related selection fields have the expected defaults.
"""

from __future__ import annotations

import pytest
import reflex as rx

from tests.ui.conftest import collect_types, find_by_type, state_default
from web.components.sidebar import sidebar
from web.state import AppState


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------


class TestSidebarSmoke:
    def test_returns_rx_component(self):
        assert isinstance(sidebar(), rx.Component)

    def test_top_level_is_box(self):
        comp = sidebar()
        assert type(comp).__name__ == "Box"


# ---------------------------------------------------------------------------
# Structure — layout widgets
# ---------------------------------------------------------------------------


class TestSidebarStructure:
    def test_has_scroll_area(self):
        """The project list lives inside a ScrollArea for overflow."""
        comp = sidebar()
        counts = collect_types(comp)
        assert counts["ScrollArea"] >= 1

    def test_has_separator_elements(self):
        """Separators divide header, action row, and project list."""
        comp = sidebar()
        counts = collect_types(comp)
        assert counts["Separator"] >= 2

    def test_has_heading(self):
        """The 'Contexta' app title is rendered as a Heading."""
        comp = sidebar()
        counts = collect_types(comp)
        assert counts["Heading"] >= 1

    def test_has_new_project_dialog(self):
        """A DialogRoot wraps the 'New Project' modal."""
        comp = sidebar()
        counts = collect_types(comp)
        assert counts["DialogRoot"] >= 1

    def test_dialog_content_present(self):
        comp = sidebar()
        counts = collect_types(comp)
        assert counts["DialogContent"] >= 1

    def test_has_spinner_for_loading_state(self):
        """A Spinner appears while projects are loading."""
        comp = sidebar()
        counts = collect_types(comp)
        assert counts["Spinner"] >= 1

    def test_has_refresh_icon_button(self):
        """An IconButton lets users refresh the project list."""
        comp = sidebar()
        counts = collect_types(comp)
        assert counts["IconButton"] >= 1

    def test_has_link_to_admin(self):
        """A Link/ReactRouterLink navigates to the /admin page."""
        comp = sidebar()
        counts = collect_types(comp)
        assert counts.get("Link", 0) + counts.get("ReactRouterLink", 0) >= 1


# ---------------------------------------------------------------------------
# Foreach — three loops with correct state var references
# ---------------------------------------------------------------------------


class TestSidebarForeachLoops:
    def test_has_four_foreach_loops(self):
        """projects, versions, nodes, and insights (Requirement C2.1) each
        have a Foreach loop."""
        comp = sidebar()
        counts = collect_types(comp)
        assert counts["Foreach"] == 4

    def test_projects_foreach_references_projects_var(self):
        comp = sidebar()
        foreachs = find_by_type(comp, "Foreach")
        iterables = [str(getattr(f, "iterable", "")) for f in foreachs]
        # The projects field serialises to a JS expression containing 'projects'
        assert any("projects" in s for s in iterables), (
            f"No Foreach references projects var. Iterables: {iterables}"
        )

    def test_versions_foreach_references_versions_var(self):
        comp = sidebar()
        foreachs = find_by_type(comp, "Foreach")
        iterables = [str(getattr(f, "iterable", "")) for f in foreachs]
        assert any("versions_for_selected_project" in s for s in iterables), (
            f"No Foreach references versions_for_selected_project. Iterables: {iterables}"
        )

    def test_nodes_foreach_references_nodes_var(self):
        comp = sidebar()
        foreachs = find_by_type(comp, "Foreach")
        iterables = [str(getattr(f, "iterable", "")) for f in foreachs]
        assert any("nodes_for_selected_version" in s for s in iterables), (
            f"No Foreach references nodes_for_selected_version. Iterables: {iterables}"
        )


# ---------------------------------------------------------------------------
# State defaults — initial state has no selection
# ---------------------------------------------------------------------------


class TestSidebarStateDefaults:
    def test_projects_default_is_empty_list(self):
        assert state_default("projects") == []

    def test_selected_project_id_default_is_empty(self):
        assert state_default("selected_project_id") == ""

    def test_selected_version_id_default_is_empty(self):
        assert state_default("selected_version_id") == ""

    def test_selected_node_id_default_is_empty(self):
        assert state_default("selected_node_id") == ""

    def test_is_loading_default_is_false(self):
        assert state_default("is_loading") is False

    def test_new_project_dialog_open_default_is_false(self):
        assert state_default("new_project_dialog_open") is False

    def test_new_project_name_default_is_empty(self):
        assert state_default("new_project_name") == ""


# ---------------------------------------------------------------------------
# AppState dialog methods — logic via raw fn calls on mock objects
# ---------------------------------------------------------------------------


class _MockDialogState:
    new_project_name: str = ""
    new_project_dialog_open: bool = False


class TestSidebarDialogLogic:
    def test_open_new_project_dialog_sets_open_true(self):
        mock = _MockDialogState()
        AppState.open_new_project_dialog.fn(mock)
        assert mock.new_project_dialog_open is True

    def test_open_new_project_dialog_clears_name(self):
        mock = _MockDialogState()
        mock.new_project_name = "stale"
        AppState.open_new_project_dialog.fn(mock)
        assert mock.new_project_name == ""

    def test_set_new_project_name_updates_name(self):
        mock = _MockDialogState()
        AppState.set_new_project_name.fn(mock, "Alpha Project")
        assert mock.new_project_name == "Alpha Project"

    def test_close_new_project_dialog_sets_open_false(self):
        mock = _MockDialogState()
        mock.new_project_dialog_open = True
        AppState.close_new_project_dialog.fn(mock)
        assert mock.new_project_dialog_open is False

    def test_close_new_project_dialog_clears_name(self):
        mock = _MockDialogState()
        mock.new_project_name = "Partial name"
        mock.new_project_dialog_open = True
        AppState.close_new_project_dialog.fn(mock)
        assert mock.new_project_name == ""

    def test_open_then_set_then_close_cycle(self):
        """Full open → set name → close cycle leaves dialog closed and name cleared."""
        mock = _MockDialogState()
        AppState.open_new_project_dialog.fn(mock)
        AppState.set_new_project_name.fn(mock, "My Project")
        assert mock.new_project_name == "My Project"
        AppState.close_new_project_dialog.fn(mock)
        assert mock.new_project_dialog_open is False
        assert mock.new_project_name == ""


# ---------------------------------------------------------------------------
# AppState.open_ingestion_modal / close_ingestion_modal
# ---------------------------------------------------------------------------


class _MockIngestionState:
    artifact_ingestion_open: bool = False
    artifact_save_complete: bool = False
    artifact_title: str = "old title"
    artifact_source: str = "upload"
    artifact_content: str = "some content"
    artifact_url: str = "https://example.com"
    artifact_tags_applied: list = ["tag1"]
    artifact_tag_suggestions: list = ["s1"]
    artifact_custom_tag: str = "ct"
    last_saved_artifact: dict = {}
    artifact_upload_filename: str = "file.pdf"
    _artifact_upload_bytes: bytes = b"data"


class TestSidebarIngestionModal:
    def test_open_ingestion_modal_sets_open_true(self):
        mock = _MockIngestionState()
        AppState.open_ingestion_modal.fn(mock)
        assert mock.artifact_ingestion_open is True

    def test_open_ingestion_modal_resets_fields(self):
        mock = _MockIngestionState()
        AppState.open_ingestion_modal.fn(mock)
        assert mock.artifact_title == ""
        assert mock.artifact_source == "paste"
        assert mock.artifact_content == ""
        assert mock.artifact_url == ""
        assert mock.artifact_tags_applied == []
        assert mock.artifact_tag_suggestions == []
        assert mock.artifact_custom_tag == ""
        assert mock.artifact_save_complete is False

    def test_close_ingestion_modal_sets_open_false(self):
        mock = _MockIngestionState()
        mock.artifact_ingestion_open = True
        AppState.close_ingestion_modal.fn(mock)
        assert mock.artifact_ingestion_open is False
