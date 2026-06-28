"""
contexta/api/schemas.py — Pydantic response/request models for the Contexta REST API.

Every response model includes an ``error: str | None = None`` field so the
frontend toast system has a single key to check, regardless of HTTP status.
Success responses always carry ``error=None``; failures carry the human-readable
message and are returned with an appropriate HTTP 4xx/5xx status code.

Hierarchy:
    Project → Version → Artifact (tagged, is_active) → Review Job → Proposal Job
"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


# ── Shared ─────────────────────────────────────────────────────────────────────

class DeleteResponse(BaseModel):
    """Generic deletion confirmation."""

    id: str
    status: str = "deleted"
    error: Optional[str] = None


# ── Projects ───────────────────────────────────────────────────────────────────

class ProjectItem(BaseModel):
    """One project row in the list response."""

    project_id: str
    name: str
    version_count: int = 0
    review_count: int = 0
    storage_bytes: int = 0


class ProjectListResponse(BaseModel):
    projects: List[ProjectItem]
    error: Optional[str] = None


# ── Versions ───────────────────────────────────────────────────────────────────

class VersionItem(BaseModel):
    """One version row in the list response (with counts)."""

    version_id: str
    name: str
    created_at: str
    artifact_count: int = 0
    review_count: int = 0


class VersionListResponse(BaseModel):
    versions: List[VersionItem]
    error: Optional[str] = None


class ArtifactInVersion(BaseModel):
    """Artifact linked to a version, with is_active state."""

    artifact_id: str
    title: str
    tags: List[str] = []
    is_active: bool = True


class VersionDetailResponse(BaseModel):
    """Version detail including all linked artifacts."""

    version_id: str
    name: str
    created_at: str
    artifacts: List[ArtifactInVersion] = []
    error: Optional[str] = None


class CreateVersionRequest(BaseModel):
    project_id: str
    version_name: str
    artifact_ids: List[str]


class CreateVersionResponse(BaseModel):
    version_id: str
    name: str
    created_at: str
    artifact_count: int
    error: Optional[str] = None


# ── Artifacts ──────────────────────────────────────────────────────────────────

class ArtifactItem(BaseModel):
    """One artifact in the list (is_active explicit on every item)."""

    artifact_id: str
    title: str
    tags: List[str] = []
    is_active: bool = True
    created_at: str


class ArtifactListResponse(BaseModel):
    artifacts: List[ArtifactItem]
    error: Optional[str] = None


class ArtifactResponse(BaseModel):
    """Single artifact response (create / patch)."""

    artifact_id: str
    title: str
    tags: List[str] = []
    is_active: bool = True
    created_at: str
    error: Optional[str] = None


class UpdateArtifactRequest(BaseModel):
    active: bool


class SuggestionsResponse(BaseModel):
    suggestions: List[str]
    error: Optional[str] = None


# ── Reviews ────────────────────────────────────────────────────────────────────

class ReviewItem(BaseModel):
    """One review job summary in a list response."""

    review_id: str
    run_date: str
    status: str
    persona: str


class ReviewListResponse(BaseModel):
    reviews: List[ReviewItem]
    error: Optional[str] = None


class FindingItem(BaseModel):
    finding_id: str
    type: str
    severity: str
    text: str
    source_artifact: str
    citation: str = ""


class FindingsSummary(BaseModel):
    risks: int = 0
    constraints: int = 0
    dependencies: int = 0
    assumptions: int = 0
    action_items: int = 0


class ReviewPayloadResponse(BaseModel):
    """Full Review_Payload — returned by GET /api/nodes/{node_id}."""

    review_id: str
    project_id: str
    version_id: str
    status: str
    run_date: str
    persona: str
    findings: List[FindingItem] = []
    summary: Optional[FindingsSummary] = None
    error: Optional[str] = None


class CreateReviewRequest(BaseModel):
    version_id: str
    persona_roles: List[str]
    context: str = ""


class CreateReviewResponse(BaseModel):
    review_id: str
    status: str = "queued"
    error: Optional[str] = None


class ReviewStatusResponse(BaseModel):
    review_id: str
    status: str
    progress_message: Optional[str] = None
    error: Optional[str] = None


# ── Proposals ──────────────────────────────────────────────────────────────────

class CreateProposalRequest(BaseModel):
    review_id: str


class CreateProposalResponse(BaseModel):
    proposal_id: str
    status: str = "queued"
    error: Optional[str] = None


class ProposalStatusResponse(BaseModel):
    proposal_id: str
    status: str
    progress_message: Optional[str] = None
    error: Optional[str] = None


# ── Admin ──────────────────────────────────────────────────────────────────────

class AdminProviders(BaseModel):
    """Provider connectivity / key-presence status."""

    groq: str = "not_set"
    openrouter: str = "not_set"
    gemini: str = "not_set"
    ollama: str = "not_set"


class AdminHealthResponse(BaseModel):
    last_run: Optional[str] = None
    providers: AdminProviders
    error: Optional[str] = None


class AdminThresholds(BaseModel):
    risk: float = 0.75
    constraint: float = 0.70
    dependency: float = 0.80


class AdminConfigResponse(BaseModel):
    providers: AdminProviders
    ollama_url: str = ""
    thresholds: AdminThresholds
    max_active_projects: int = 5
    error: Optional[str] = None


class UpdateAdminConfigRequest(BaseModel):
    field: str                           # "api_key" | "threshold" | "ollama_url" | "max_active_projects"
    provider: Optional[str] = None       # for field="api_key"
    key: Optional[str] = None            # for field="api_key"
    threshold_name: Optional[str] = None # for field="threshold"
    threshold_value: Optional[float] = None
    ollama_url: Optional[str] = None
    max_active_projects: Optional[int] = None


class AdminConfigUpdateResponse(BaseModel):
    field: str
    status: str = "saved"
    error: Optional[str] = None


# ── Legacy node / project detail (used by old inline routes, kept for compat) ──

class ProjectResponse(BaseModel):
    """Minimal project representation (legacy)."""

    id: str
    name: str
    global_tags: List[str] = []


class VersionResponse(BaseModel):
    """Version row (legacy)."""

    id: str
    project_id: str
    name: str
    description: Optional[str] = None
    created_at: str


class NodeSummaryResponse(BaseModel):
    """Node fields safe to include in list responses."""

    id: str
    project_id: str
    parent_id: Optional[str] = None
    layer_type: str
    node_name: str
    created_at: str
    version_tag: Optional[str] = None
    version_id: Optional[str] = None


class NodeDetailResponse(NodeSummaryResponse):
    """Full node including content and metadata."""

    content_markdown: str = ""
    metadata_json: Any = None


class ProjectDetailResponse(ProjectResponse):
    """Project with all its versions and node summaries."""

    versions: List[VersionResponse] = []
    nodes: List[NodeSummaryResponse] = []
