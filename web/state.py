"""web/state.py — Reflex application state for the Solution Acceleration Engine web UI.

MOCK_MODE = True (default):
    AppState is populated from _get_mock_data() on page load.
    No database connection or LLM backend is required.
    All component bindings (rx.foreach, rx.cond) are fully exercised.

MOCK_MODE = False:
    AppState loads live data via the async repository functions in
    contexta/db/repositories.py.  Requires a running SQLite DB at the
    path configured in ContextaConfig.

Data hierarchy (mirrors the live DB schema):
    Project  →  Version  →  Node  →  Finding
"""

import reflex as rx

# ---------------------------------------------------------------------------
# Deployment flag — flip to False to wire against the live database.
# ---------------------------------------------------------------------------
MOCK_MODE: bool = True


# ---------------------------------------------------------------------------
# Mock data factory
# ---------------------------------------------------------------------------

def _get_mock_data() -> list[dict]:
    """Return a fully-populated fixture hierarchy for MOCK_MODE operation.

    Each level mirrors the shape produced by the real repository layer so
    that switching MOCK_MODE = False requires no changes to any component.

    Structure per project dict:
        id           str
        name         str
        global_tags  list[str]
        versions     list[version_dict]

    Structure per version dict:
        id           str
        project_id   str
        name         str
        description  str | None
        created_at   str  (ISO-8601)
        nodes        list[node_dict]

    Structure per node dict:
        id           str
        version_id   str
        project_id   str
        parent_id    str | None
        layer_type   str
        node_name    str
        created_at   str  (ISO-8601)
        findings     list[finding_dict]

    Structure per finding dict:
        dimension          str   (ReviewDimensionEnum value)
        confidence         str   ("RED" | "AMBER" | "GREEN")
        summary            str
        detail             str
        citations          list[citation_dict]
        mitigation_routing str   (MitigationRoutingEnum value)

    Structure per citation dict:
        file_path     str
        line_start    int
        line_end      int
        citation_type str
        excerpt       str
    """
    return [
        # ── Project 1 ── Banking Platform SOW ──────────────────────────────
        {
            "id": "mock-proj-banking",
            "name": "Banking Platform SOW",
            "global_tags": ["Banking", "Enterprise", "Fintech"],
            "versions": [
                {
                    "id": "mock-ver-banking-1",
                    "project_id": "mock-proj-banking",
                    "name": "v1.0 — Initial Review",
                    "description": (
                        "First-pass analysis of the Banking Platform "
                        "Statement of Work."
                    ),
                    "created_at": "2024-06-15T09:00:00+00:00",
                    "nodes": [
                        {
                            "id": "mock-node-banking-1-a",
                            "version_id": "mock-ver-banking-1",
                            "project_id": "mock-proj-banking",
                            "parent_id": None,
                            "layer_type": "exploration",
                            "node_name": "Layer 1 — Full Exploration",
                            "created_at": "2024-06-15T09:30:00+00:00",
                            "findings": [
                                {
                                    "dimension": "Intent",
                                    "confidence": "GREEN",
                                    "summary": (
                                        "Project intent is clearly articulated."
                                    ),
                                    "detail": (
                                        "The SOW clearly describes the goal of "
                                        "modernising the core banking ledger with "
                                        "a cloud-native microservices architecture. "
                                        "Stakeholder alignment is evident across "
                                        "all sections."
                                    ),
                                    "citations": [
                                        {
                                            "file_path": "banking_statement_of_work.md",
                                            "line_start": 1,
                                            "line_end": 15,
                                            "citation_type": "Direct Reference",
                                            "excerpt": "The objective of this engagement is…",
                                        }
                                    ],
                                    "mitigation_routing": "Ignored",
                                },
                                {
                                    "dimension": "Scope",
                                    "confidence": "AMBER",
                                    "summary": (
                                        "Data migration scope is under-specified."
                                    ),
                                    "detail": (
                                        "Section 3.2 references legacy data "
                                        "migration but provides no volume estimates, "
                                        "schema mapping, or cutover strategy. "
                                        "This creates material delivery risk."
                                    ),
                                    "citations": [
                                        {
                                            "file_path": "banking_statement_of_work.md",
                                            "line_start": 42,
                                            "line_end": 58,
                                            "citation_type": "Direct Reference",
                                            "excerpt": "Legacy data will be migrated…",
                                        }
                                    ],
                                    "mitigation_routing": "Scope Modification",
                                },
                                {
                                    "dimension": "Architecture",
                                    "confidence": "GREEN",
                                    "summary": (
                                        "Technical architecture is well-defined."
                                    ),
                                    "detail": (
                                        "The proposed event-driven architecture "
                                        "with Kafka and Kubernetes is appropriate "
                                        "for the stated load requirements. "
                                        "Technology choices are justified with "
                                        "explicit reference to NFRs."
                                    ),
                                    "citations": [
                                        {
                                            "file_path": "banking_technical_architecture.md",
                                            "line_start": 10,
                                            "line_end": 30,
                                            "citation_type": "Direct Reference",
                                            "excerpt": "The platform shall adopt an event-driven…",
                                        }
                                    ],
                                    "mitigation_routing": "Ignored",
                                },
                                {
                                    "dimension": "Risk",
                                    "confidence": "RED",
                                    "summary": (
                                        "Regulatory compliance dependencies "
                                        "are unmitigated."
                                    ),
                                    "detail": (
                                        "PCI-DSS and GDPR compliance requirements "
                                        "are cited in the SOW but there is no "
                                        "identified compliance workstream, "
                                        "responsible owner, or timeline allocation."
                                    ),
                                    "citations": [
                                        {
                                            "file_path": "banking_statement_of_work.md",
                                            "line_start": 78,
                                            "line_end": 92,
                                            "citation_type": "Advised in Relation",
                                            "excerpt": "All deliverables must comply with…",
                                        }
                                    ],
                                    "mitigation_routing": "Risk Register",
                                },
                                {
                                    "dimension": "Timeline",
                                    "confidence": "AMBER",
                                    "summary": (
                                        "Delivery milestones lack buffer "
                                        "for integration testing."
                                    ),
                                    "detail": (
                                        "The 18-month delivery plan assumes a "
                                        "linear progression without contingency "
                                        "windows. Integration testing phases are "
                                        "compressed to two weeks per service."
                                    ),
                                    "citations": [
                                        {
                                            "file_path": "banking_statement_of_work.md",
                                            "line_start": 105,
                                            "line_end": 120,
                                            "citation_type": "Direct Reference",
                                            "excerpt": "Milestone 4: Integration complete by…",
                                        }
                                    ],
                                    "mitigation_routing": "Risk Register",
                                },
                            ],
                        }
                    ],
                },
                {
                    "id": "mock-ver-banking-2",
                    "project_id": "mock-proj-banking",
                    "name": "v1.1 — Post-Architecture Review",
                    "description": (
                        "Updated analysis following the technical "
                        "architecture deep-dive session."
                    ),
                    "created_at": "2024-06-22T11:00:00+00:00",
                    "nodes": [
                        {
                            "id": "mock-node-banking-2-a",
                            "version_id": "mock-ver-banking-2",
                            "project_id": "mock-proj-banking",
                            "parent_id": "mock-node-banking-1-a",
                            "layer_type": "exploration",
                            "node_name": "Layer 1 — Architecture Iteration",
                            "created_at": "2024-06-22T11:30:00+00:00",
                            "findings": [
                                {
                                    "dimension": "Architecture",
                                    "confidence": "GREEN",
                                    "summary": (
                                        "NFRs now fully addressed in the "
                                        "revised architecture."
                                    ),
                                    "detail": (
                                        "The revised architecture document "
                                        "incorporates the security and performance "
                                        "NFRs identified in the v1.0 review cycle. "
                                        "All gaps have been closed."
                                    ),
                                    "citations": [
                                        {
                                            "file_path": "banking_technical_architecture.md",
                                            "line_start": 55,
                                            "line_end": 80,
                                            "citation_type": "Direct Reference",
                                            "excerpt": "Non-functional requirements addressed…",
                                        }
                                    ],
                                    "mitigation_routing": "Ignored",
                                },
                                {
                                    "dimension": "Risk",
                                    "confidence": "AMBER",
                                    "summary": (
                                        "Compliance workstream defined "
                                        "but ownership is TBD."
                                    ),
                                    "detail": (
                                        "A compliance workstream has been added "
                                        "to the project plan but the responsible "
                                        "owner is listed as 'TBD'. This does not "
                                        "satisfy the risk mitigation requirement "
                                        "from the previous review."
                                    ),
                                    "citations": [
                                        {
                                            "file_path": "banking_technical_architecture.md",
                                            "line_start": 90,
                                            "line_end": 105,
                                            "citation_type": "Advised in Relation",
                                            "excerpt": "Compliance workstream owner: TBD…",
                                        }
                                    ],
                                    "mitigation_routing": "Assumptions Matrix",
                                },
                            ],
                        }
                    ],
                },
            ],
        },

        # ── Project 2 ── Pharma Clinical Trial Platform ────────────────────
        {
            "id": "mock-proj-pharma",
            "name": "Pharma Clinical Trial Platform",
            "global_tags": ["Pharma", "Healthcare", "Regulated"],
            "versions": [
                {
                    "id": "mock-ver-pharma-1",
                    "project_id": "mock-proj-pharma",
                    "name": "v1.0 — Proposal Review",
                    "description": (
                        "Initial review of the clinical trial management "
                        "platform proposal."
                    ),
                    "created_at": "2024-07-01T14:00:00+00:00",
                    "nodes": [
                        {
                            "id": "mock-node-pharma-1-a",
                            "version_id": "mock-ver-pharma-1",
                            "project_id": "mock-proj-pharma",
                            "parent_id": None,
                            "layer_type": "exploration",
                            "node_name": "Layer 1 — Full Exploration",
                            "created_at": "2024-07-01T14:45:00+00:00",
                            "findings": [
                                {
                                    "dimension": "NFR",
                                    "confidence": "RED",
                                    "summary": (
                                        "21 CFR Part 11 compliance absent "
                                        "from NFR document."
                                    ),
                                    "detail": (
                                        "The non-functional requirements document "
                                        "contains no mention of electronic record "
                                        "and signature requirements under 21 CFR "
                                        "Part 11, which is mandatory for "
                                        "FDA-regulated clinical trial systems."
                                    ),
                                    "citations": [
                                        {
                                            "file_path": "pharma_non_functional_requirements.md",
                                            "line_start": 1,
                                            "line_end": 30,
                                            "citation_type": "Advised in Relation",
                                            "excerpt": "Security requirements include…",
                                        }
                                    ],
                                    "mitigation_routing": "Risk Register",
                                },
                                {
                                    "dimension": "Commercial",
                                    "confidence": "AMBER",
                                    "summary": (
                                        "Pricing model excludes regulatory "
                                        "audit overhead."
                                    ),
                                    "detail": (
                                        "The commercial proposal contains no line "
                                        "items for regulatory audit support, "
                                        "validation documentation, or IQ/OQ/PQ "
                                        "testing cycles required for GxP "
                                        "validation."
                                    ),
                                    "citations": [
                                        {
                                            "file_path": "pharma_proposal_main.md",
                                            "line_start": 62,
                                            "line_end": 78,
                                            "citation_type": "Direct Reference",
                                            "excerpt": "Commercial investment summary…",
                                        }
                                    ],
                                    "mitigation_routing": "Scope Modification",
                                },
                                {
                                    "dimension": "Ownership",
                                    "confidence": "GREEN",
                                    "summary": (
                                        "RACI is complete and unambiguous."
                                    ),
                                    "detail": (
                                        "The proposal contains a fully populated "
                                        "RACI matrix with named individuals for "
                                        "each workstream. No gaps identified."
                                    ),
                                    "citations": [
                                        {
                                            "file_path": "pharma_proposal_main.md",
                                            "line_start": 120,
                                            "line_end": 145,
                                            "citation_type": "Direct Reference",
                                            "excerpt": "Governance and ownership…",
                                        }
                                    ],
                                    "mitigation_routing": "Ignored",
                                },
                            ],
                        }
                    ],
                }
            ],
        },

        # ── Project 3 ── Drone Fleet Management ────────────────────────────
        {
            "id": "mock-proj-drone",
            "name": "Drone Fleet Management System",
            "global_tags": ["Aerospace", "IoT", "Edge"],
            "versions": [
                {
                    "id": "mock-ver-drone-1",
                    "project_id": "mock-proj-drone",
                    "name": "v1.0 — Scope Review",
                    "description": (
                        "Initial scope and resource plan review for the "
                        "drone fleet management platform."
                    ),
                    "created_at": "2024-07-10T10:00:00+00:00",
                    "nodes": [
                        {
                            "id": "mock-node-drone-1-a",
                            "version_id": "mock-ver-drone-1",
                            "project_id": "mock-proj-drone",
                            "parent_id": None,
                            "layer_type": "exploration",
                            "node_name": "Layer 1 — Full Exploration",
                            "created_at": "2024-07-10T10:30:00+00:00",
                            "findings": [
                                {
                                    "dimension": "Scope",
                                    "confidence": "RED",
                                    "summary": (
                                        "Edge compute requirements are "
                                        "entirely absent from scope."
                                    ),
                                    "detail": (
                                        "The scope document describes a "
                                        "cloud-centralised telemetry model but "
                                        "makes no provision for edge compute "
                                        "nodes required for low-latency "
                                        "collision avoidance."
                                    ),
                                    "citations": [
                                        {
                                            "file_path": "drone_project_scope_doc.md",
                                            "line_start": 35,
                                            "line_end": 55,
                                            "citation_type": "Advised in Relation",
                                            "excerpt": "Telemetry data will be streamed to…",
                                        }
                                    ],
                                    "mitigation_routing": "Risk Register",
                                },
                                {
                                    "dimension": "Resource",
                                    "confidence": "AMBER",
                                    "summary": (
                                        "Embedded systems expertise not "
                                        "represented in resource plan."
                                    ),
                                    "detail": (
                                        "The resource plan lists eight "
                                        "backend engineers but no embedded "
                                        "systems or RTOS specialists. "
                                        "Drone firmware development requires "
                                        "this skill set."
                                    ),
                                    "citations": [
                                        {
                                            "file_path": "drone_resource_plan.md",
                                            "line_start": 20,
                                            "line_end": 40,
                                            "citation_type": "Direct Reference",
                                            "excerpt": "Engineering team composition…",
                                        }
                                    ],
                                    "mitigation_routing": "Scope Modification",
                                },
                                {
                                    "dimension": "Delivery",
                                    "confidence": "GREEN",
                                    "summary": (
                                        "Agile delivery cadence is well-structured."
                                    ),
                                    "detail": (
                                        "The resource plan outlines a clear "
                                        "sprint cadence with defined ceremonies, "
                                        "escalation paths, and quarterly steering "
                                        "board reviews."
                                    ),
                                    "citations": [
                                        {
                                            "file_path": "drone_resource_plan.md",
                                            "line_start": 55,
                                            "line_end": 70,
                                            "citation_type": "Direct Reference",
                                            "excerpt": "Delivery governance model…",
                                        }
                                    ],
                                    "mitigation_routing": "Ignored",
                                },
                            ],
                        }
                    ],
                }
            ],
        },
    ]


# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------

class AppState(rx.State):
    """Central reactive state for the web UI.

    Navigation flow:
        select_project  →  active_view = "welcome"  (project selected, no detail)
        select_version  →  active_view = "version"  (VersionDetail rendered)
        select_node     →  active_view = "node"      (FindingCards rendered)
    """

    # ── Project tree (populated by on_load) ──────────────────────────────
    projects: list[dict] = []

    # ── Navigation cursors ───────────────────────────────────────────────
    selected_project_id: str = ""
    selected_version_id: str = ""
    selected_node_id: str = ""

    # ── Active view token ────────────────────────────────────────────────
    # One of: "welcome" | "version" | "node"
    active_view: str = "welcome"

    # ── Content payloads ─────────────────────────────────────────────────
    current_version: dict = {}
    current_node: dict = {}
    current_findings: list[dict] = []

    # ── UI state ─────────────────────────────────────────────────────────
    is_loading: bool = False

    # ── Lifecycle ────────────────────────────────────────────────────────

    def on_load(self) -> None:
        """Populate state on page load.

        When MOCK_MODE = True:  injects fixture data with no I/O.
        When MOCK_MODE = False: must be extended to call the async
            repository functions from contexta/db/repositories.py.
        """
        if MOCK_MODE:
            self.projects = _get_mock_data()
        else:
            # Live path: wire to contexta.db.repositories
            # Example (requires async event handler):
            #   async with aiosqlite.connect(config.db_path) as conn:
            #       raw = await list_projects(conn)
            #       self.projects = [_hydrate_project(p, conn) for p in raw]
            pass

    # ── Navigation event handlers ────────────────────────────────────────

    def select_project(self, project_id: str) -> None:
        """Select a project; reset all downstream selection state."""
        self.selected_project_id = project_id
        self.selected_version_id = ""
        self.selected_node_id = ""
        self.active_view = "welcome"
        self.current_version = {}
        self.current_node = {}
        self.current_findings = []

    def select_version(self, version_id: str) -> None:
        """Select a version and load its detail into current_version."""
        self.selected_version_id = version_id
        self.selected_node_id = ""
        self.active_view = "version"
        self.current_node = {}
        self.current_findings = []

        for project in self.projects:
            for version in project.get("versions", []):
                if version["id"] == version_id:
                    self.current_version = version
                    return

    def select_node(self, node_id: str) -> None:
        """Select a node and load its findings into current_findings."""
        self.selected_node_id = node_id
        self.active_view = "node"

        for project in self.projects:
            for version in project.get("versions", []):
                for node in version.get("nodes", []):
                    if node["id"] == node_id:
                        self.current_node = node
                        self.current_findings = node.get("findings", [])
                        return
