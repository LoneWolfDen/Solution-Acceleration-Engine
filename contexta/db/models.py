"""
contexta/db/models.py — Python dataclasses mirroring SQLite row shapes.

These dataclasses are the return types of all repository functions.  They are
deliberately kept as plain dataclasses (not Pydantic models) to make the
boundary explicit: data coming *out* of the DB is in these shapes; data going
*into* the DB is validated through Pydantic models in repositories.py.

Hierarchy (scope.md):
    Project (Root) → Version (Group) → Artifact/Node (Tagged) → Review → Proposal
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProjectRow:
    """Mirrors one row of the ``projects`` table.

    The root container in the data hierarchy.  All versions and reviews are
    scoped to a project.
    """

    id:          str
    name:        str
    global_tags: List[str] = field(default_factory=list)  # deserialised from JSON


@dataclass
class VersionRow:
    """Mirrors one row of the ``versions`` table.

    A Version groups one or more Artifact nodes under a named, ordered
    iteration within a Project.  Multiple Versions under a Project enable
    cross-version comparison (the Comparison module in scope.md).

    Attributes:
        id:          UUID primary key.
        project_id:  FK → projects.id (the owning project).
        name:        Human-readable version label, e.g. "v1.0 — Initial Review".
        description: Optional free-text notes about what changed in this version.
        created_at:  ISO-8601 UTC timestamp of version creation.
    """

    id:          str
    project_id:  str
    name:        str
    created_at:  str            # ISO-8601 UTC
    description: Optional[str] = None


@dataclass
class NodeRow:
    """
    Mirrors one row of the ``nodes`` table.

    Represents an Artifact review unit (Layer 1 exploration or Layer 2
    synthesis) within the hierarchy:
        Project → Version → Node (Artifact/Review)

    ``content_markdown`` contains the serialised ``ReviewNodePayload`` JSON
    written by ``write_node()``.  Callers that need structured access should
    re-parse via ``ReviewNodePayload.model_validate_json(row.content_markdown)``.

    Attributes:
        version_tag: Legacy human-assigned string label (preserved for
                     backwards compatibility with existing export packets).
        version_id:  FK → versions.id — the Version this node belongs to.
                     ``None`` for nodes not yet assigned to a named version.
    """

    id:               str
    project_id:       str
    parent_id:        Optional[str]
    layer_type:       str
    node_name:        str
    metadata_json:    Any                # raw JSON string (from DB reads) or dict (from direct construction)
    content_markdown: str               # raw JSON string from LLM / payload
    created_at:       str               # ISO-8601 UTC
    version_tag:      Optional[str] = None
    version_id:       Optional[str] = None   # FK → versions.id


@dataclass
class BlueprintRow:
    """Mirrors one row of the prompt_blueprints table."""

    id:                 str
    blueprint_name:     str
    version_string:     str
    master_prompt_text: str
    is_active:          bool


@dataclass
class InsightRow:
    """Mirrors one row of the global_client_insights table."""

    id:                     str
    client_or_industry_tag: str
    observed_pattern:       str
    frequency_count:        int
    last_updated:           str   # ISO-8601 UTC


@dataclass
class IntelligenceRow:
    """Mirrors one row of the ``intelligence_layer`` table.

    Stores learned insights produced by the Sprint 6 PromptOptimizer service.
    Three insight types are persisted here:

    CITATION_TREND
        [ArtifactID:SectionID] citation usage frequencies derived from
        Layer 1 exploration NodeRows.

    CONFIDENCE_TREND
        ConfidenceMatrix keyed by version_id, scoped per-project.
        Enables cross-version trend analysis for a specific project.

    PROMPT_DELTA
        Recommended prompt adjustments derived from JudgeValidationReport
        gate failures compared against the active BasePersona prompt.

    Attributes:
        id:             UUID primary key.
        insight_type:   One of 'CITATION_TREND', 'CONFIDENCE_TREND', 'PROMPT_DELTA'.
        payload_json:   Raw JSON string containing the insight payload.
        created_at:     ISO-8601 UTC timestamp of record creation.
        project_id:     FK → projects.id.  None for global (cross-project) insights.
        source_node_id: FK → nodes.id.  None for multi-node aggregated insights.
    """

    id:             str
    insight_type:   str
    payload_json:   str            # raw JSON string
    created_at:     str            # ISO-8601 UTC
    project_id:     Optional[str] = None   # nullable — None = global insight
    source_node_id: Optional[str] = None   # nullable — multi-node derivations
