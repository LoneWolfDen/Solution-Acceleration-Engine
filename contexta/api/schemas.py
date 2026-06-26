"""
contexta/api/schemas.py — Pydantic response models for the Contexta REST API.

These are the public API contract types.  They are intentionally separate from
the internal db/models.py dataclasses: the DB layer owns its own shapes; the
API layer owns its serialisation contract.

Hierarchy reflected here:
    Project → Version → Node (summary | detail)
"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


class ProjectResponse(BaseModel):
    """Minimal project representation returned in list responses."""

    id: str
    name: str
    global_tags: List[str]


class VersionResponse(BaseModel):
    """One Version row belonging to a Project."""

    id: str
    project_id: str
    name: str
    description: Optional[str]
    created_at: str


class NodeSummaryResponse(BaseModel):
    """Node fields safe to include in list responses (no heavy content)."""

    id: str
    project_id: str
    parent_id: Optional[str]
    layer_type: str
    node_name: str
    created_at: str
    version_tag: Optional[str]
    version_id: Optional[str]


class NodeDetailResponse(NodeSummaryResponse):
    """Full node including content and metadata — returned by GET /api/nodes/{id}."""

    content_markdown: str
    metadata_json: Any  # parsed dict from the DB TEXT column


class ProjectDetailResponse(ProjectResponse):
    """Project with all its versions and node summaries."""

    versions: List[VersionResponse]
    nodes: List[NodeSummaryResponse]
