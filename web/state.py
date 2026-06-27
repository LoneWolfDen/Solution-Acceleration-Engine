"""web/state.py — Central application state for the Contexta Web UI.

MockMode
--------
MOCK_MODE = True  → load_data() and select_review() use _get_mock_data().
                    No database, no network, no httpx. Fully deterministic.

MOCK_MODE = False → Stub placeholders are in place for future httpx calls
                    to the REST API once a stable backend connection exists.

Flip the constant at line 22 when moving to staging.
"""

from __future__ import annotations

from typing import Any

import reflex as rx

# ── Single toggle to switch between mock and live data ────────────────────────
MOCK_MODE: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# Mock data factory
# ─────────────────────────────────────────────────────────────────────────────

def _get_mock_data() -> dict[str, Any]:
    """Return a fully populated data structure that mirrors the SQLite schema.

    Hierarchy: ProjectRow → VersionRow → NodeRow
    Each NodeRow's payload mirrors ReviewNodePayload (stored in
    nodes.content_markdown in production).

    Returns
    -------
    dict with two keys:
        "projects"       — list[ProjectDict] with nested versions and nodes
        "review_payload" — sample ReviewNodePayload for the pre-selected node
    """
    return {
        "projects": [
            {
                "id": "proj-001",
                "name": "Banking Transformation Platform",
                "global_tags": ["banking", "fintech"],
                "versions": [
                    {
                        "id": "ver-001",
                        "project_id": "proj-001",
                        "name": "v1.0 — Initial Review",
                        "description": (
                            "Baseline assessment of the core banking platform "
                            "migration scope."
                        ),
                        "created_at": "2026-06-01T10:00:00+00:00",
                        "nodes": [
                            {
                                "id": "node-001",
                                "project_id": "proj-001",
                                "version_id": "ver-001",
                                "parent_id": "",
                                "layer_type": "exploration",
                                "node_name": "Architecture Dimension Review",
                                "created_at": "2026-06-01T10:30:00+00:00",
                            },
                            {
                                "id": "node-002",
                                "project_id": "proj-001",
                                "version_id": "ver-001",
                                "parent_id": "",
                                "layer_type": "exploration",
                                "node_name": "Risk Dimension Review",
                                "created_at": "2026-06-01T10:45:00+00:00",
                            },
                            {
                                "id": "node-003",
                                "project_id": "proj-001",
                                "version_id": "ver-001",
                                "parent_id": "node-001",
                                "layer_type": "synthesis",
                                "node_name": "Layer 2 — Reconciliation Report",
                                "created_at": "2026-06-01T11:00:00+00:00",
                            },
                        ],
                    },
                    {
                        "id": "ver-002",
                        "project_id": "proj-001",
                        "name": "v2.0 — Post-Remediation Review",
                        "description": (
                            "Second pass after scope modifications were applied."
                        ),
                        "created_at": "2026-06-15T09:00:00+00:00",
                        "nodes": [
                            {
                                "id": "node-004",
                                "project_id": "proj-001",
                                "version_id": "ver-002",
                                "parent_id": "",
                                "layer_type": "exploration",
                                "node_name": "Architecture Dimension Review",
                                "created_at": "2026-06-15T09:30:00+00:00",
                            },
                        ],
                    },
                ],
            },
            {
                "id": "proj-002",
                "name": "Drone Fleet Management System",
                "global_tags": ["aerospace", "iot"],
                "versions": [
                    {
                        "id": "ver-003",
                        "project_id": "proj-002",
                        "name": "v1.0 — Scoping Review",
                        "description": (
                            "Initial feasibility assessment for drone fleet management."
                        ),
                        "created_at": "2026-06-10T14:00:00+00:00",
                        "nodes": [
                            {
                                "id": "node-005",
                                "project_id": "proj-002",
                                "version_id": "ver-003",
                                "parent_id": "",
                                "layer_type": "exploration",
                                "node_name": "Scope Dimension Review",
                                "created_at": "2026-06-10T14:30:00+00:00",
                            },
                            {
                                "id": "node-006",
                                "project_id": "proj-002",
                                "version_id": "ver-003",
                                "parent_id": "",
                                "layer_type": "exploration",
                                "node_name": "NFR Dimension Review",
                                "created_at": "2026-06-10T15:00:00+00:00",
                            },
                        ],
                    },
                ],
            },
            {
                "id": "proj-003",
                "name": "Pharma Clinical Trials Platform",
                "global_tags": ["pharma", "compliance", "healthcare"],
                "versions": [
                    {
                        "id": "ver-004",
                        "project_id": "proj-003",
                        "name": "v1.0 — Compliance Review",
                        "description": "Regulatory and NFR compliance assessment.",
                        "created_at": "2026-06-20T08:00:00+00:00",
                        "nodes": [
                            {
                                "id": "node-007",
                                "project_id": "proj-003",
                                "version_id": "ver-004",
                                "parent_id": "",
                                "layer_type": "exploration",
                                "node_name": "Commercial Dimension Review",
                                "created_at": "2026-06-20T08:30:00+00:00",
                            },
                        ],
                    },
                ],
            },
        ],
        # ── Sample ReviewNodePayload ─────────────────────────────────────────
        # Mirrors: ReviewNodePayload(dimension, findings, overall_confidence,
        #          raw_llm_response) plus context fields for the UI header.
        "review_payload": {
            "node_id": "node-001",
            "node_name": "Architecture Dimension Review",
            "version_name": "v1.0 — Initial Review",
            "project_name": "Banking Transformation Platform",
            "dimension": "Architecture",
            "overall_confidence": "AMBER",
            "raw_llm_response": (
                "LLM response stored verbatim for audit trail. "
                "Structured findings are extracted into the findings list below."
            ),
            "findings": [
                {
                    "dimension": "Architecture",
                    "confidence": "AMBER",
                    "summary": (
                        "Microservices decomposition lacks defined service boundaries"
                    ),
                    "detail": (
                        "The proposed architecture describes a microservices pattern "
                        "but does not define explicit service boundaries, ownership, "
                        "or inter-service communication contracts. This creates "
                        "ambiguity in the delivery timeline and resource allocation."
                    ),
                    "citations": [
                        {
                            "file_path": "banking_technical_architecture.md",
                            "line_start": 14,
                            "line_end": 28,
                            "citation_type": "Direct Reference",
                            "excerpt": (
                                "Services will be decomposed by domain capability..."
                            ),
                        }
                    ],
                    "mitigation_routing": "Risk Register",
                },
                {
                    "dimension": "Architecture",
                    "confidence": "RED",
                    "summary": (
                        "No data migration strategy for legacy core banking system"
                    ),
                    "detail": (
                        "The Statement of Work omits any reference to a data "
                        "migration plan for the existing Temenos T24 core banking "
                        "system. Given the 18-month timeline, this represents a "
                        "critical delivery risk that must be addressed before sign-off."
                    ),
                    "citations": [
                        {
                            "file_path": "banking_statement_of_work.md",
                            "line_start": 42,
                            "line_end": 55,
                            "citation_type": "Advised in Relation",
                            "excerpt": (
                                "Data migration activities to be scoped in Phase 2..."
                            ),
                        }
                    ],
                    "mitigation_routing": "Scope Modification",
                },
                {
                    "dimension": "Architecture",
                    "confidence": "GREEN",
                    "summary": (
                        "Cloud infrastructure selection is appropriate for the workload"
                    ),
                    "detail": (
                        "AWS EKS with RDS Aurora PostgreSQL is a well-validated "
                        "pattern for high-availability financial services workloads. "
                        "The proposed auto-scaling configuration aligns with peak "
                        "transaction volume estimates."
                    ),
                    "citations": [
                        {
                            "file_path": "banking_technical_architecture.md",
                            "line_start": 67,
                            "line_end": 74,
                            "citation_type": "Direct Reference",
                            "excerpt": (
                                "AWS EKS cluster with node auto-scaling enabled..."
                            ),
                        }
                    ],
                    "mitigation_routing": "Ignored",
                },
            ],
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Application state
# ─────────────────────────────────────────────────────────────────────────────

class AppState(rx.State):
    """Central state for the Contexta Web UI.

    All state vars are JSON-serialisable (list[dict], str, bool) so Reflex
    can sync them to the browser without additional serialisation steps.

    Navigation model
    ----------------
    selected_node_id   — the id of the currently highlighted sidebar item
    selected_node_type — "project" | "version" | "review" | ""
    The content pane uses these two vars to decide what to render.
    """

    # ── Project tree (Projects → Versions → Nodes) ────────────────────────────
    projects: list[dict] = []

    # ── Sidebar selection ─────────────────────────────────────────────────────
    selected_node_id: str = ""
    # "project" | "version" | "review" | ""
    selected_node_type: str = ""

    # ── Content pane data ─────────────────────────────────────────────────────
    # review_payload mirrors ReviewNodePayload + UI context fields
    review_payload: dict = {}
    # version_detail mirrors VersionRow + derived counts
    version_detail: dict = {}
    # project_detail mirrors ProjectRow + derived counts
    project_detail: dict = {}

    # ── UI state ──────────────────────────────────────────────────────────────
    is_loading: bool = False

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def load_data(self) -> None:
        """Load the project tree.

        MockMode path  → _get_mock_data() — no I/O, fully deterministic.
        Live path      → httpx GET /api/projects (stub; wire up post-staging).

        Also pre-selects the first review node so the content pane is
        never empty on first render.
        """
        self.is_loading = True

        if MOCK_MODE:
            data = _get_mock_data()
            self.projects = data["projects"]
            self.review_payload = data["review_payload"]

            # Pre-select first review node for immediate visual feedback.
            if self.projects:
                first_proj = self.projects[0]
                first_ver = (
                    first_proj["versions"][0]
                    if first_proj["versions"]
                    else None
                )
                if first_ver and first_ver["nodes"]:
                    first_node = first_ver["nodes"][0]
                    self.selected_node_id = first_node["id"]
                    self.selected_node_type = "review"
        else:
            # ── Live path (activate when MOCK_MODE = False) ───────────────────
            # import httpx
            # async with httpx.AsyncClient() as client:
            #     resp = await client.get("http://localhost:8001/api/projects")
            #     resp.raise_for_status()
            #     self.projects = resp.json()
            pass

        self.is_loading = False

    # ─────────────────────────────────────────────────────────────────────────
    # Navigation event handlers
    # Sidebar calls these with the id of the clicked item.
    # Each handler updates selected_node_id, selected_node_type, and the
    # matching detail dict so the content pane has data to render immediately.
    # ─────────────────────────────────────────────────────────────────────────

    def select_project(self, project_id: str) -> None:
        """Select a project node and populate project_detail."""
        self.selected_node_id = project_id
        self.selected_node_type = "project"

        for project in self.projects:
            if project["id"] == project_id:
                self.project_detail = {
                    "id": project["id"],
                    "name": project["name"],
                    "global_tags": project.get("global_tags", []),
                    "version_count": len(project.get("versions", [])),
                }
                return

    def select_version(self, version_id: str) -> None:
        """Select a version node and populate version_detail."""
        self.selected_node_id = version_id
        self.selected_node_type = "version"

        for project in self.projects:
            for version in project.get("versions", []):
                if version["id"] == version_id:
                    self.version_detail = {
                        "id": version["id"],
                        "name": version["name"],
                        "description": version.get("description", ""),
                        "created_at": version["created_at"],
                        "node_count": len(version.get("nodes", [])),
                        "project_name": project["name"],
                    }
                    return

    def select_review(self, node_id: str) -> None:
        """Select a review node and load its payload.

        MockMode: all nodes return the same sample payload with the
        node_id and node_name updated for accurate header display.
        Live mode: httpx GET /api/nodes/{node_id}/payload (stub).
        """
        self.selected_node_id = node_id
        self.selected_node_type = "review"

        if MOCK_MODE:
            data = _get_mock_data()
            payload = dict(data["review_payload"])
            payload["node_id"] = node_id

            # Update context fields from the tree for accurate display.
            for project in self.projects:
                for version in project.get("versions", []):
                    for node in version.get("nodes", []):
                        if node["id"] == node_id:
                            payload["node_name"] = node["node_name"]
                            payload["version_name"] = version["name"]
                            payload["project_name"] = project["name"]
                            break

            self.review_payload = payload
        else:
            # TODO: httpx GET /api/nodes/{node_id}/payload
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # Computed vars — used by content_pane.py to decide which pane to show
    # ─────────────────────────────────────────────────────────────────────────

    @rx.var
    def show_review_pane(self) -> bool:
        return self.selected_node_type == "review"

    @rx.var
    def show_version_pane(self) -> bool:
        return self.selected_node_type == "version"

    @rx.var
    def show_project_pane(self) -> bool:
        return self.selected_node_type == "project"

    @rx.var
    def mock_mode_label(self) -> str:
        """Text label shown in the header banner."""
        return "MOCK MODE" if MOCK_MODE else "LIVE"

    @rx.var
    def current_findings(self) -> list[dict]:
        """Findings list from review_payload. Typed for safe rx.foreach use."""
        return self.review_payload.get("findings", [])

    @rx.var
    def current_project_tags(self) -> list[str]:
        """Tags from project_detail. Typed for safe rx.foreach use."""
        return self.project_detail.get("global_tags", [])
