"""Milestone 6.6 — tests/ui/test_sidebar.py

Tests for ProjectTreeSidebar state logic.

The sidebar renders the project tree from AppState.projects[].
Tests validate:
  - Correct number of project nodes rendered from mock list
  - Expanding a project reveals its version children
  - Collapsing an expanded project hides its version children
  - Selected node is highlighted in AppState (selected_node_id set)
  - Clicking a project node selects it
  - Empty project list renders zero nodes
  - expand/collapse state is per-project (toggling one does not affect others)
  - node_type is set correctly on selection

No Reflex server or live API is used.
"""

from __future__ import annotations

import pytest

from .conftest import MockAppState, ProjectItem, VersionSummary


# ── Project node count ────────────────────────────────────────────────────────


def test_sidebar_renders_correct_project_count(
    state_with_projects: MockAppState,
) -> None:
    """Sidebar renders exactly as many project nodes as are in AppState.projects."""
    assert len(state_with_projects.projects) == 3


def test_sidebar_empty_list_renders_zero_nodes(empty_state: MockAppState) -> None:
    """Sidebar renders zero project nodes when projects is empty."""
    assert len(empty_state.projects) == 0


def test_sidebar_single_project(empty_state: MockAppState) -> None:
    """Sidebar renders one node for a single project."""
    empty_state.projects = [
        ProjectItem("p1", "Solo Project", 0, 0, 0)
    ]
    assert len(empty_state.projects) == 1


def test_sidebar_project_names_correct(state_with_projects: MockAppState) -> None:
    """Each project node displays the correct name from AppState."""
    names = [p.name for p in state_with_projects.projects]
    assert "Alpha Project" in names
    assert "Beta Project" in names
    assert "Gamma Project" in names


# ── Expand / collapse ─────────────────────────────────────────────────────────


def test_sidebar_project_collapsed_by_default(
    state_with_projects: MockAppState,
) -> None:
    """All projects are collapsed (not expanded) on initial load."""
    for project in state_with_projects.projects:
        assert state_with_projects.expanded_projects.get(project.project_id, False) is False


def test_expand_project_reveals_children(state_with_projects: MockAppState) -> None:
    """Toggling a project sets expanded=True — children become visible."""
    pid = state_with_projects.projects[0].project_id
    state_with_projects.toggle_project_expanded(pid)
    assert state_with_projects.expanded_projects[pid] is True


def test_collapse_expanded_project_hides_children(
    state_with_projects: MockAppState,
) -> None:
    """Toggling an expanded project sets it back to collapsed."""
    pid = state_with_projects.projects[0].project_id
    state_with_projects.toggle_project_expanded(pid)   # expand
    state_with_projects.toggle_project_expanded(pid)   # collapse
    assert state_with_projects.expanded_projects[pid] is False


def test_expand_collapse_cycle_restores_state(
    state_with_projects: MockAppState,
) -> None:
    """Expand → collapse → expand produces correct sequence of states."""
    pid = state_with_projects.projects[1].project_id
    assert state_with_projects.expanded_projects.get(pid, False) is False  # initial

    state_with_projects.toggle_project_expanded(pid)
    assert state_with_projects.expanded_projects[pid] is True

    state_with_projects.toggle_project_expanded(pid)
    assert state_with_projects.expanded_projects[pid] is False

    state_with_projects.toggle_project_expanded(pid)
    assert state_with_projects.expanded_projects[pid] is True


# ── Per-project expand state isolation ────────────────────────────────────────


def test_expanding_one_project_does_not_affect_others(
    state_with_projects: MockAppState,
) -> None:
    """Toggling project-0 does not change the expanded state of project-1 or project-2."""
    pid0 = state_with_projects.projects[0].project_id
    pid1 = state_with_projects.projects[1].project_id
    pid2 = state_with_projects.projects[2].project_id

    state_with_projects.toggle_project_expanded(pid0)

    assert state_with_projects.expanded_projects[pid0] is True
    assert state_with_projects.expanded_projects.get(pid1, False) is False
    assert state_with_projects.expanded_projects.get(pid2, False) is False


def test_all_projects_can_be_expanded_independently(
    state_with_projects: MockAppState,
) -> None:
    """Each project can be expanded independently."""
    for project in state_with_projects.projects:
        state_with_projects.toggle_project_expanded(project.project_id)

    for project in state_with_projects.projects:
        assert state_with_projects.expanded_projects[project.project_id] is True


# ── Version children under an expanded project ───────────────────────────────


def test_expanded_project_with_versions_shows_children(
    empty_state: MockAppState,
) -> None:
    """An expanded project with version children exposes them via .versions."""
    project = ProjectItem(
        project_id="p1",
        name="Project With Versions",
        version_count=2,
        review_count=1,
        storage_bytes=512,
        versions=[
            VersionSummary("v1", "v1.0", "2024-01-01T00:00:00+00:00", 3, 1),
            VersionSummary("v2", "v1.1", "2024-02-01T00:00:00+00:00", 2, 0),
        ],
        expanded=False,
    )
    empty_state.projects = [project]
    empty_state.toggle_project_expanded("p1")

    is_expanded = empty_state.expanded_projects.get("p1", False)
    assert is_expanded is True
    # When expanded, the component renders project.versions as child nodes.
    assert len(project.versions) == 2


def test_collapsed_project_versions_not_shown(empty_state: MockAppState) -> None:
    """A collapsed project's version children are not shown (expanded=False)."""
    project = ProjectItem(
        project_id="p-col",
        name="Collapsed Project",
        version_count=1,
        review_count=0,
        storage_bytes=0,
        versions=[VersionSummary("v1", "v1.0", "2024-01-01T00:00:00+00:00", 1, 0)],
    )
    empty_state.projects = [project]
    # Never toggled — stays collapsed.
    assert empty_state.expanded_projects.get("p-col", False) is False


# ── Selected node state ───────────────────────────────────────────────────────


def test_selected_node_id_none_on_init(empty_state: MockAppState) -> None:
    """selected_node_id is None before any node is selected."""
    assert empty_state.selected_node_id is None


def test_clicking_project_sets_selected_node(
    state_with_projects: MockAppState,
) -> None:
    """Clicking a project node sets selected_node_id and selected_node_type."""
    pid = state_with_projects.projects[0].project_id
    state_with_projects.select_node(pid, "project")
    assert state_with_projects.selected_node_id == pid
    assert state_with_projects.selected_node_type == "project"


def test_clicking_review_node_sets_correct_type(
    state_with_projects: MockAppState,
) -> None:
    """Selecting a review node sets node_type to 'review'."""
    state_with_projects.select_node("review-abc", "review")
    assert state_with_projects.selected_node_type == "review"


def test_clicking_version_node_sets_correct_type(
    state_with_projects: MockAppState,
) -> None:
    """Selecting a version node sets node_type to 'version'."""
    state_with_projects.select_node("version-xyz", "version")
    assert state_with_projects.selected_node_type == "version"


def test_selected_node_highlighted(state_with_projects: MockAppState) -> None:
    """The selected project node is identifiable via selected_node_id."""
    pid = state_with_projects.projects[1].project_id
    state_with_projects.select_node(pid, "project")
    # A sidebar item is 'highlighted' when its id == selected_node_id.
    assert state_with_projects.selected_node_id == pid


def test_selecting_different_node_updates_selection(
    state_with_projects: MockAppState,
) -> None:
    """Selecting a new node replaces the previous selection."""
    pid0 = state_with_projects.projects[0].project_id
    pid1 = state_with_projects.projects[1].project_id

    state_with_projects.select_node(pid0, "project")
    assert state_with_projects.selected_node_id == pid0

    state_with_projects.select_node(pid1, "project")
    assert state_with_projects.selected_node_id == pid1


def test_clear_selection_resets_selected_node(
    state_with_projects: MockAppState,
) -> None:
    """clear_selection() resets selected_node_id and selected_node_type to None."""
    state_with_projects.select_node("some-id", "review")
    state_with_projects.clear_selection()
    assert state_with_projects.selected_node_id is None
    assert state_with_projects.selected_node_type is None


# ── Project metadata fields ───────────────────────────────────────────────────


def test_project_nodes_have_required_fields(
    state_with_projects: MockAppState,
) -> None:
    """Each project node exposes project_id, name, version_count, review_count."""
    for project in state_with_projects.projects:
        assert project.project_id
        assert isinstance(project.name, str) and project.name
        assert isinstance(project.version_count, int) and project.version_count >= 0
        assert isinstance(project.review_count, int) and project.review_count >= 0
        assert isinstance(project.storage_bytes, int) and project.storage_bytes >= 0
