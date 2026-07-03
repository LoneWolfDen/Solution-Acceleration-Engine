"""contexta/api/schemas.py — All Pydantic request and response models.

Design rules:
  - Every response model includes ``error: str | None = None``.
  - ``error`` is ``None`` on success and a human-readable string on failure.
  - The frontend checks this field to trigger toast notifications.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ── Shared ────────────────────────────────────────────────────────────────────


class ErrorEnvelope(BaseModel):
    """Minimal error-only response for 4xx/5xx responses."""

    error: str


# ── Projects ──────────────────────────────────────────────────────────────────


class ProjectSummary(BaseModel):
    project_id: str
    name: str
    version_count: int
    review_count: int
    storage_bytes: int


class ProjectListResponse(BaseModel):
    projects: List[ProjectSummary]
    error: Optional[str] = None


class ProjectDeleteResponse(BaseModel):
    project_id: str
    status: str
    error: Optional[str] = None


# ── Versions ──────────────────────────────────────────────────────────────────


class ArtifactSummary(BaseModel):
    artifact_id: str
    title: str
    tags: List[str]
    is_active: bool
    created_at: Optional[str] = None


class VersionSummary(BaseModel):
    version_id: str
    name: str
    created_at: str
    artifact_count: int
    review_count: int


class VersionListResponse(BaseModel):
    versions: List[VersionSummary]
    error: Optional[str] = None


class VersionDetailResponse(BaseModel):
    version_id: str
    name: str
    created_at: str
    artifacts: List[ArtifactSummary]
    error: Optional[str] = None


class VersionCreateRequest(BaseModel):
    project_id: str
    version_name: str
    artifact_ids: List[str]


class VersionCreateResponse(BaseModel):
    version_id: str
    name: str
    created_at: str
    artifact_count: int
    error: Optional[str] = None


# ── Reviews ───────────────────────────────────────────────────────────────────


class ReviewSummary(BaseModel):
    review_id: str
    run_date: str
    status: str
    persona: str


class ReviewListResponse(BaseModel):
    reviews: List[ReviewSummary]
    error: Optional[str] = None


class ReviewCreateRequest(BaseModel):
    version_id: str
    persona_roles: List[str] = []
    context: str = ""


class ReviewCreateResponse(BaseModel):
    review_id: str
    status: str
    error: Optional[str] = None


class ReviewStatusResponse(BaseModel):
    review_id: str
    status: str
    progress_message: Optional[str] = None
    error: Optional[str] = None


# ── Node (review detail) ──────────────────────────────────────────────────────


class CitationOut(BaseModel):
    file_path: str
    line_start: int
    line_end: int
    citation_type: str
    excerpt: str


class FindingOut(BaseModel):
    finding_id: str
    type: str
    severity: str
    text: str
    source_artifact: str
    citation: Optional[CitationOut] = None


class ReviewSummaryDetail(BaseModel):
    risks: int
    constraints: int
    dependencies: int
    assumptions: int
    action_items: int


class NodeDetailResponse(BaseModel):
    review_id: str
    project_id: str
    version_id: Optional[str]
    status: str
    run_date: str
    persona: str
    findings: List[FindingOut]
    summary: ReviewSummaryDetail
    error: Optional[str] = None


# ── Artifacts ─────────────────────────────────────────────────────────────────


class ArtifactListResponse(BaseModel):
    artifacts: List[ArtifactSummary]
    error: Optional[str] = None


class ArtifactCreateRequest(BaseModel):
    source: str  # "upload" | "paste" | "url"
    title: str
    project_id: str
    content: Optional[str] = None
    url: Optional[str] = None
    tags: List[str] = []


class ArtifactCreateResponse(BaseModel):
    artifact_id: str
    title: str
    tags: List[str]
    is_active: bool
    created_at: str
    error: Optional[str] = None


class ArtifactPatchRequest(BaseModel):
    active: bool


class ArtifactPatchResponse(BaseModel):
    artifact_id: str
    is_active: bool
    error: Optional[str] = None


class ArtifactDeleteResponse(BaseModel):
    artifact_id: str
    status: str
    error: Optional[str] = None


class ArtifactSuggestionsResponse(BaseModel):
    suggestions: List[str]
    error: Optional[str] = None


# ── Proposals ─────────────────────────────────────────────────────────────────


class ProposalCreateRequest(BaseModel):
    review_id: str


class ProposalCreateResponse(BaseModel):
    proposal_id: str
    status: str
    error: Optional[str] = None


class ProposalStatusResponse(BaseModel):
    proposal_id: str
    status: str
    progress_message: Optional[str] = None
    error: Optional[str] = None


# ── Admin ─────────────────────────────────────────────────────────────────────


class ProviderStatuses(BaseModel):
    groq: str
    openrouter: str
    gemini: str
    ollama: str


class AdminHealthResponse(BaseModel):
    last_run: Optional[str] = None
    providers: ProviderStatuses
    error: Optional[str] = None


class ThresholdSettings(BaseModel):
    risk: float = 0.7
    constraint: float = 0.7
    dependency: float = 0.7


class AdminConfigResponse(BaseModel):
    providers: Dict[str, str]
    ollama_url: str
    thresholds: ThresholdSettings
    max_active_projects: int
    error: Optional[str] = None


class AdminConfigUpdateRequest(BaseModel):
    field: str  # "api_key" | "threshold" | "ollama_url"
    provider: Optional[str] = None
    key: Optional[str] = None
    threshold_name: Optional[str] = None
    threshold_value: Optional[float] = None
    ollama_url: Optional[str] = None


class AdminConfigUpdateResponse(BaseModel):
    field: str
    status: str
    error: Optional[str] = None
