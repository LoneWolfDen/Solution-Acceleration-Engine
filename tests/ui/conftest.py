"""Milestone 6 — Shared fixtures for component UI tests.

Design:
  - Tests run without a live Reflex server or API.
  - AppState behaviour is validated through its pure-Python data-transformation
    logic: state field shapes, tag-suggestion logic, finding-card rendering
    data contracts, toast state, and sidebar tree construction.
  - MockAppState provides pre-populated field values that mirror the real
    AppState fields defined in the architecture (web/state.py).
  - All fixtures are synchronous; no network calls or DB connections are made.

No Reflex runtime is started during any test in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Data shapes mirroring API response contracts ──────────────────────────────


@dataclass
class ArtifactItem:
    """Mirrors ArtifactSummary from contexta.api.schemas."""
    artifact_id: str
    title: str
    tags: List[str]
    is_active: bool
    created_at: str = "2024-01-01T00:00:00+00:00"


@dataclass
class FindingItem:
    """Mirrors FindingOut from contexta.api.schemas."""
    finding_id: str
    type: str        # ReviewDimensionEnum value
    severity: str    # ConfidenceEnum value: RED | AMBER | GREEN
    text: str
    source_artifact: str
    citation: Optional[Dict[str, Any]] = None


@dataclass
class ReviewSummary:
    """Mirrors ReviewSummaryDetail from contexta.api.schemas."""
    risks: int = 0
    constraints: int = 0
    dependencies: int = 0
    assumptions: int = 0
    action_items: int = 0


@dataclass
class ReviewPayload:
    """Mirrors NodeDetailResponse from contexta.api.schemas."""
    review_id: str
    project_id: str
    version_id: Optional[str]
    status: str
    run_date: str
    persona: str
    findings: List[FindingItem] = field(default_factory=list)
    summary: ReviewSummary = field(default_factory=ReviewSummary)
    error: Optional[str] = None


@dataclass
class VersionSummary:
    """Mirrors VersionSummary from contexta.api.schemas."""
    version_id: str
    name: str
    created_at: str
    artifact_count: int
    review_count: int


@dataclass
class ProjectItem:
    """Mirrors ProjectSummary from contexta.api.schemas."""
    project_id: str
    name: str
    version_count: int
    review_count: int
    storage_bytes: int
    versions: List[VersionSummary] = field(default_factory=list)
    expanded: bool = False


# ── Mock AppState ─────────────────────────────────────────────────────────────


@dataclass
class MockAppState:
    """In-memory mock of the Reflex AppState.

    Replicates the field names and state-transition logic of the real
    ``web/state.py`` AppState so that component rendering tests can assert
    on data shapes and state changes without starting a Reflex server.

    Field names match those specified in Milestone 2 Task 2.2.
    """

    projects: List[ProjectItem] = field(default_factory=list)
    selected_node_id: Optional[str] = None
    selected_node_type: Optional[str] = None  # "review" | "version" | None
    review_payload: Optional[ReviewPayload] = None
    version_payload: Optional[Any] = None
    is_loading: bool = False
    toast_message: Optional[str] = None
    toast_variant: str = "success"  # "success" | "error"

    # Triage-specific state (Milestone 3)
    triage_artifacts: List[ArtifactItem] = field(default_factory=list)

    # Tag-chip state (Milestone 3)
    suggested_tags: List[str] = field(default_factory=list)
    applied_tags: List[str] = field(default_factory=list)

    # Sidebar expand/collapse state (keyed by project_id)
    expanded_projects: Dict[str, bool] = field(default_factory=dict)

    # ── State transitions ─────────────────────────────────────────────────────

    def select_node(self, node_id: str, node_type: str) -> None:
        """Select a sidebar node; mirrors AppState.select_node."""
        self.selected_node_id = node_id
        self.selected_node_type = node_type

    def clear_selection(self) -> None:
        self.selected_node_id = None
        self.selected_node_type = None
        self.review_payload = None
        self.version_payload = None

    def set_toast(self, message: str, variant: str = "success") -> None:
        self.toast_message = message
        self.toast_variant = variant

    def clear_toast(self) -> None:
        self.toast_message = None

    def toggle_project_expanded(self, project_id: str) -> None:
        current = self.expanded_projects.get(project_id, False)
        self.expanded_projects[project_id] = not current

    def toggle_artifact_active(self, artifact_id: str) -> None:
        """Optimistic UI toggle for is_active — mirrors Milestone 3 Task 3.5."""
        for art in self.triage_artifacts:
            if art.artifact_id == artifact_id:
                art.is_active = not art.is_active
                return

    def add_tag(self, tag: str) -> None:
        if tag and tag not in self.applied_tags:
            self.applied_tags.append(tag)
            if tag in self.suggested_tags:
                self.suggested_tags.remove(tag)

    def remove_tag(self, tag: str) -> None:
        if tag in self.applied_tags:
            self.applied_tags.remove(tag)
            if tag not in self.suggested_tags:
                self.suggested_tags.append(tag)

    def get_active_artifact_ids(self) -> List[str]:
        """Return IDs of all is_active=True artifacts — used by Create Version."""
        return [a.artifact_id for a in self.triage_artifacts if a.is_active]


# ── Severity colour mapping (mirrors FindingCard badge logic) ─────────────────

SEVERITY_COLOUR: Dict[str, str] = {
    "RED": "red",
    "AMBER": "orange",
    "GREEN": "green",
}

FINDING_TYPE_LABELS: Dict[str, str] = {
    "Risk": "Risk",
    "Scope": "Scope",
    "Architecture": "Architecture",
    "NFR": "NFR",
    "Resource": "Resource",
    "Delivery": "Delivery",
    "Timeline": "Timeline",
    "Commercial": "Commercial",
    "Intent": "Intent",
    "Ownership": "Ownership",
    "Language": "Language",
    "Consistency": "Consistency",
}


# ── pytest fixtures ───────────────────────────────────────────────────────────

import pytest


@pytest.fixture
def empty_state() -> MockAppState:
    """A clean MockAppState with no data."""
    return MockAppState()


@pytest.fixture
def state_with_projects() -> MockAppState:
    """MockAppState pre-populated with 3 projects."""
    state = MockAppState()
    state.projects = [
        ProjectItem(
            project_id="proj-1",
            name="Alpha Project",
            version_count=2,
            review_count=3,
            storage_bytes=1024,
        ),
        ProjectItem(
            project_id="proj-2",
            name="Beta Project",
            version_count=1,
            review_count=1,
            storage_bytes=512,
        ),
        ProjectItem(
            project_id="proj-3",
            name="Gamma Project",
            version_count=0,
            review_count=0,
            storage_bytes=0,
        ),
    ]
    return state


@pytest.fixture
def state_with_review() -> MockAppState:
    """MockAppState with a selected review node and populated payload."""
    state = MockAppState()
    state.selected_node_id = "node-abc"
    state.selected_node_type = "review"
    state.review_payload = ReviewPayload(
        review_id="review-1",
        project_id="proj-1",
        version_id="ver-1",
        status="complete",
        run_date="2024-06-01T10:00:00+00:00",
        persona='["architect", "developer"]',
        findings=[
            FindingItem(
                finding_id="0",
                type="Risk",
                severity="RED",
                text="Delivery timeline is aggressive.",
                source_artifact="scope.md",
            ),
            FindingItem(
                finding_id="1",
                type="Architecture",
                severity="AMBER",
                text="No DR strategy defined.",
                source_artifact="architecture.md",
            ),
            FindingItem(
                finding_id="2",
                type="NFR",
                severity="GREEN",
                text="Performance targets well-defined.",
                source_artifact="nfr.md",
            ),
        ],
        summary=ReviewSummary(
            risks=1,
            constraints=1,
            dependencies=0,
            assumptions=1,
            action_items=0,
        ),
    )
    return state


@pytest.fixture
def triage_artifacts() -> List[ArtifactItem]:
    """A list of 4 artifacts — 3 active, 1 inactive."""
    return [
        ArtifactItem("art-1", "Scope Document", ["scope"], True),
        ArtifactItem("art-2", "Architecture Spec", ["architecture"], True),
        ArtifactItem("art-3", "Risk Register", ["risk"], False),
        ArtifactItem("art-4", "Resource Plan", ["resources"], True),
    ]


@pytest.fixture
def state_with_triage(triage_artifacts: List[ArtifactItem]) -> MockAppState:
    """MockAppState with 4 triage artifacts loaded."""
    state = MockAppState()
    state.triage_artifacts = triage_artifacts
    return state
