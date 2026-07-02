"""
contexta/api/schemas.py — Pydantic response/request models for the Contexta REST API.

Every response model includes an ``error: str | None = None`` field so the
frontend toast system has a single key to check, regardless of HTTP status.
Success responses always carry ``error=None``; failures carry the human-readable
message and are returned with an appropriate HTTP 4xx/5xx status code.
"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


# ── Shared ─────────────────────────────────────────────────────────────────────

class DeleteResponse(BaseModel):
    id: str
    status: str = "deleted"
    error: Optional[str] = None


# ── Projects ───────────────────────────────────────────────────────────────────

class ProjectItem(BaseModel):
    project_id: str
    name: str
    version_count: int = 0
    review_count: int = 0
    storage_bytes: int = 0


class ProjectListResponse(BaseModel):
    projects: List[ProjectItem]
    error: Optional[str] = None


class CreateProjectRequest(BaseModel):
    name: str
    global_tags: List[str] = []


class CreateProjectResponse(BaseModel):
    project_id: str
    name: str
    error: Optional[str] = None


# ── Versions ───────────────────────────────────────────────────────────────────

class VersionItem(BaseModel):
    version_id: str
    name: str
    created_at: str
    artifact_count: int = 0
    review_count: int = 0


class VersionListResponse(BaseModel):
    versions: List[VersionItem]
    error: Optional[str] = None


class ArtifactInVersion(BaseModel):
    artifact_id: str
    title: str
    tags: List[str] = []
    is_active: bool = True


class VersionDetailResponse(BaseModel):
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
    artifact_id: str
    title: str
    tags: List[str] = []
    is_active: bool = True
    created_at: str


class ArtifactListResponse(BaseModel):
    artifacts: List[ArtifactItem]
    error: Optional[str] = None


class ArtifactResponse(BaseModel):
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
    field: str
    provider: Optional[str] = None
    key: Optional[str] = None
    threshold_name: Optional[str] = None
    threshold_value: Optional[float] = None
    ollama_url: Optional[str] = None
    max_active_projects: Optional[int] = None


class AdminConfigUpdateResponse(BaseModel):
    field: str
    status: str = "saved"
    error: Optional[str] = None


# ── Legacy node / project detail (backward-compat for existing endpoints) ───────

class ProjectResponse(BaseModel):
    id: str
    name: str
    global_tags: List[str] = []


class VersionResponse(BaseModel):
    id: str
    project_id: str
    name: str
    description: Optional[str] = None
    created_at: str


class NodeSummaryResponse(BaseModel):
    id: str
    project_id: str
    parent_id: Optional[str] = None
    layer_type: str
    node_name: str
    created_at: str
    version_tag: Optional[str] = None
    version_id: Optional[str] = None


class NodeDetailResponse(NodeSummaryResponse):
    content_markdown: str = ""
    metadata_json: Any = None


class ProjectDetailResponse(ProjectResponse):
    versions: List[VersionResponse] = []
    nodes: List[NodeSummaryResponse] = []
