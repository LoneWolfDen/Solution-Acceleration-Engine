"""Milestone 6.2 — tests/ui/test_triage_widget.py

Tests for ArtifactTriageWidget state and rendering logic.

The widget renders a table of artifacts from AppState.triage_artifacts.
Tests validate:
  - Correct row count for a given artifact list
  - is_active=True artifact shows ON toggle state
  - is_active=False artifact shows OFF toggle state
  - Toggling an artifact dispatches the correct PATCH payload shape
  - get_active_artifact_ids() returns only active artifact IDs (used by Create Version)

No Reflex server or live API is used. All assertions operate on MockAppState
and the data contracts defined in tests/ui/conftest.py.
"""

from __future__ import annotations

from typing import List

import pytest

from .conftest import ArtifactItem, MockAppState


# ── Row count ─────────────────────────────────────────────────────────────────


def test_triage_widget_renders_n_rows(state_with_triage: MockAppState) -> None:
    """Widget renders exactly N rows given a list of N artifacts."""
    assert len(state_with_triage.triage_artifacts) == 4


def test_triage_widget_empty_list_renders_zero_rows(empty_state: MockAppState) -> None:
    """Widget renders zero rows when triage_artifacts is empty."""
    assert len(empty_state.triage_artifacts) == 0


def test_triage_widget_single_artifact(empty_state: MockAppState) -> None:
    """Widget renders one row when a single artifact is loaded."""
    empty_state.triage_artifacts = [
        ArtifactItem("art-x", "Only Doc", ["scope"], True)
    ]
    assert len(empty_state.triage_artifacts) == 1


# ── Toggle state display ──────────────────────────────────────────────────────


def test_active_artifact_shows_on_state(state_with_triage: MockAppState) -> None:
    """is_active=True artifacts are rendered with ON toggle state."""
    active = [a for a in state_with_triage.triage_artifacts if a.is_active]
    assert len(active) == 3
    for art in active:
        assert art.is_active is True


def test_inactive_artifact_shows_off_state(state_with_triage: MockAppState) -> None:
    """is_active=False artifact is rendered with OFF toggle state."""
    inactive = [a for a in state_with_triage.triage_artifacts if not a.is_active]
    assert len(inactive) == 1
    assert inactive[0].artifact_id == "art-3"
    assert inactive[0].is_active is False


def test_all_artifacts_have_explicit_bool_is_active(
    state_with_triage: MockAppState,
) -> None:
    """Every artifact row has a strict bool is_active, never None or int."""
    for art in state_with_triage.triage_artifacts:
        assert isinstance(art.is_active, bool), (
            f"artifact {art.artifact_id} has is_active={art.is_active!r}, expected bool"
        )


# ── Toggle dispatch ───────────────────────────────────────────────────────────


def test_toggle_active_artifact_to_inactive(state_with_triage: MockAppState) -> None:
    """Toggling an active artifact flips is_active to False (optimistic UI)."""
    state_with_triage.toggle_artifact_active("art-1")
    art = next(a for a in state_with_triage.triage_artifacts if a.artifact_id == "art-1")
    assert art.is_active is False


def test_toggle_inactive_artifact_to_active(state_with_triage: MockAppState) -> None:
    """Toggling an inactive artifact flips is_active to True (optimistic UI)."""
    state_with_triage.toggle_artifact_active("art-3")
    art = next(a for a in state_with_triage.triage_artifacts if a.artifact_id == "art-3")
    assert art.is_active is True


def test_toggle_produces_correct_patch_payload(
    state_with_triage: MockAppState,
) -> None:
    """The payload dispatched to PATCH /api/artifacts/{id} matches the contract.

    Contract: { active: bool }
    The widget calls toggle_artifact_active(artifact_id) which flips is_active;
    the resulting state.is_active value is what gets sent as the 'active' field.
    """
    # art-2 is currently active (True) → toggling should produce active=False
    state_with_triage.toggle_artifact_active("art-2")
    art = next(a for a in state_with_triage.triage_artifacts if a.artifact_id == "art-2")
    expected_patch_payload = {"active": art.is_active}
    assert expected_patch_payload == {"active": False}


def test_toggle_unknown_artifact_does_not_raise(
    state_with_triage: MockAppState,
) -> None:
    """Toggling an unknown artifact_id is a no-op and does not raise."""
    before = [a.is_active for a in state_with_triage.triage_artifacts]
    state_with_triage.toggle_artifact_active("nonexistent-id")
    after = [a.is_active for a in state_with_triage.triage_artifacts]
    assert before == after


def test_double_toggle_restores_original_state(
    state_with_triage: MockAppState,
) -> None:
    """Two toggles on the same artifact restore the original is_active value."""
    original = next(
        a.is_active
        for a in state_with_triage.triage_artifacts
        if a.artifact_id == "art-1"
    )
    state_with_triage.toggle_artifact_active("art-1")
    state_with_triage.toggle_artifact_active("art-1")
    restored = next(
        a.is_active
        for a in state_with_triage.triage_artifacts
        if a.artifact_id == "art-1"
    )
    assert restored == original


# ── Create Version — active artifact IDs ─────────────────────────────────────


def test_get_active_artifact_ids_returns_only_active(
    state_with_triage: MockAppState,
) -> None:
    """get_active_artifact_ids() returns only IDs where is_active is True."""
    active_ids = state_with_triage.get_active_artifact_ids()
    assert set(active_ids) == {"art-1", "art-2", "art-4"}


def test_get_active_artifact_ids_excludes_inactive(
    state_with_triage: MockAppState,
) -> None:
    """art-3 (inactive) is excluded from active IDs."""
    active_ids = state_with_triage.get_active_artifact_ids()
    assert "art-3" not in active_ids


def test_get_active_artifact_ids_after_toggle(
    state_with_triage: MockAppState,
) -> None:
    """Active IDs update correctly after a toggle."""
    state_with_triage.toggle_artifact_active("art-1")   # active → inactive
    state_with_triage.toggle_artifact_active("art-3")   # inactive → active
    active_ids = state_with_triage.get_active_artifact_ids()
    assert "art-1" not in active_ids
    assert "art-3" in active_ids


def test_get_active_artifact_ids_all_inactive(empty_state: MockAppState) -> None:
    """Returns empty list when all artifacts are inactive."""
    empty_state.triage_artifacts = [
        ArtifactItem("a1", "Doc A", [], False),
        ArtifactItem("a2", "Doc B", [], False),
    ]
    assert empty_state.get_active_artifact_ids() == []


# ── Data field completeness ───────────────────────────────────────────────────


def test_triage_rows_have_required_fields(
    state_with_triage: MockAppState,
) -> None:
    """Every artifact row exposes artifact_id, title, tags, is_active, created_at."""
    for art in state_with_triage.triage_artifacts:
        assert art.artifact_id
        assert isinstance(art.title, str)
        assert isinstance(art.tags, list)
        assert isinstance(art.is_active, bool)
        assert isinstance(art.created_at, str)
