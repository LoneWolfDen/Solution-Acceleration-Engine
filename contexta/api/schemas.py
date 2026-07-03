"""
contexta/api/schemas.py — Pydantic request and response models for the REST API.

Every response model includes ``error: str | None = None``.
Success responses set error=None; error responses set error to a human-readable string.

Design:
- Artifacts are stored as NodeRows with layer_type="exploration".
- Reviews are stored as NodeRows with layer_type in ("exploration", "synthesis").
- Proposals are stored as NodeRows with layer_type="synthesis".
- The API presents domain-facing names; the DB layer uses NodeRow for all three.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Shared base ──────────────────────────────────────────────────────────────


class APIResponse(BaseModel):
    """Base class guaranteeing every response carries an error field."""
    error: Optional[str] = None


# ── Projects ─────────────────────────────────────────────────────────────────


class ProjectSummary(BaseModel):
    project_id: str
    name: str
    version_count: int
    review_count: int
    storage_bytes: int


class ProjectListResponse(APIResponse):
    projects: List[ProjectSummary] = Field(default_factory=list)


class ProjectDeleteResponse(APIResponse):
    project_id: str
    status: str  # "deleted"


# ── Versions ─────────────────────────────────────────────────────────────────


class VersionSummary(BaseModel):
    version_id: str
    name: str
    created_at: str
    artifact_count: int
    review_count: int


class VersionListResponse(APIResponse):
    versions: List[VersionSummary] = Field(default_factory=list)


class ArtifactInVersion(BaseModel):
    artifact_id: str
    title: str
    tags: List[str]
    is_active: bool


class VersionDetailResponse(APIResponse):
    version_id: str
    name: str
    created_at: str
    artifacts: List[ArtifactInVersion] = Field(default_factory=list)


class VersionCreateRequest(BaseModel):
    project_id: str
    version_name: str
    artifact_ids: List[str] = Field(..., min_length=1)


class VersionCreateResponse(APIResponse):
    version_id: str
    name: str
    created_at: str
    artifact_count: int


# ── Artifacts ────────────────────────────────────────────────────────────────


class ArtifactSummary(BaseModel):
    artifact_id: str
    title: str
    tags: List[str]
    is_active: bool
    created_at: str


class ArtifactListResponse(APIResponse):
    artifacts: List[ArtifactSummary] = Field(default_factory=list)


class ArtifactCreateRequest(BaseModel):
    source: str  # "upload" | "paste" | "url"
    title: str
    project_id: str
    content: Optional[str] = None
    url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class ArtifactCreateResponse(APIResponse):
    artifact_id: str
    title: str
    tags: List[str]
    is_active: bool
    created_at: str


class ArtifactPatchRequest(BaseModel):
    active: bool


class ArtifactPatchResponse(APIResponse):
    artifact_id: str
    is_active: bool


class ArtifactDeleteResponse(APIResponse):
    artifact_id: str
    status: str  # "deleted"


class ArtifactSuggestionsResponse(APIResponse):
    suggestions: List[str] = Field(default_factory=list)


# ── Reviews ──────────────────────────────────────────────────────────────────


class ReviewSummary(BaseModel):
    review_id: str
    run_date: str
    status: str
    persona: str


class ReviewListResponse(APIResponse):
    reviews: List[ReviewSummary] = Field(default_factory=list)


class FindingResponse(BaseModel):
    finding_id: str
    type: str
    severity: str
    text: str
    source_artifact: str
    citation: str


class ReviewSummaryPayload(BaseModel):
    risks: int
    constraints: int
    dependencies: int
    assumptions: int
    action_items: int


class ReviewPayloadResponse(APIResponse):
    review_id: str
    project_id: str
    version_id: Optional[str]
    status: str
    run_date: str
    persona: str
    findings: List[FindingResponse] = Field(default_factory=list)
    summary: ReviewSummaryPayload


class ReviewCreateRequest(BaseModel):
    version_id: str
    persona_roles: List[str] = Field(default_factory=list)
    context: str = ""


class ReviewCreateResponse(APIResponse):
    review_id: str
    status: str  # "queued"


class ReviewStatusResponse(APIResponse):
    review_id: str
    status: str  # "queued" | "running" | "complete" | "failed"
    progress_message: Optional[str] = None


# ── Proposals ────────────────────────────────────────────────────────────────


class ProposalCreateRequest(BaseModel):
    review_id: str


class ProposalCreateResponse(APIResponse):
    proposal_id: str
    status: str  # "queued"


class ProposalStatusResponse(APIResponse):
    proposal_id: str
    status: str  # "queued" | "running" | "complete" | "failed"
    progress_message: Optional[str] = None


# ── Admin ─────────────────────────────────────────────────────────────────────


class ProviderStatuses(BaseModel):
    groq: str        # "configured" | "not_set"
    openrouter: str
    gemini: str
    ollama: str


class AdminHealthResponse(APIResponse):
    last_run: Optional[str]
    providers: ProviderStatuses


class ProviderKeyStatuses(BaseModel):
    groq: str        # "set" | "not_set"
    openrouter: str
    gemini: str


class AdminConfigResponse(APIResponse):
    providers: ProviderKeyStatuses
    ollama_url: str
    thresholds: Dict[str, float]
    max_active_projects: int


class AdminConfigRequest(BaseModel):
    field: str  # "api_key" | "threshold" | "ollama_url"
    provider: Optional[str] = None
    key: Optional[str] = None
    threshold_name: Optional[str] = None
    threshold_value: Optional[float] = None
    ollama_url: Optional[str] = None


class AdminConfigSaveResponse(APIResponse):
    field: str
    status: str  # "saved"
