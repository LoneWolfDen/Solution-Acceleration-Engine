"""
contexta/api/schemas.py — Pydantic request and response models for the Web API.

Every response model inherits from APIResponse which carries:
    error: str | None = None

Convention:
  - Success responses: error=None, HTTP 200
  - Not-found responses: error="...", HTTP 404
  - Validation failures: error="...", HTTP 422
  - Server errors: error="...", HTTP 500
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


# ─────────────────────────────────────────────────────────────────────────────
# Shared envelope
# ─────────────────────────────────────────────────────────────────────────────

class APIResponse(BaseModel):
    """Base class that adds the standardised error envelope to every response."""
    error: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────────────────────────────────────

class ProjectItem(BaseModel):
    project_id: str
    name: str
    version_count: int
    review_count: int
    storage_bytes: int


class ProjectListResponse(APIResponse):
    projects: List[ProjectItem] = []


class DeleteResponse(APIResponse):
    id: str
    status: str


# ─────────────────────────────────────────────────────────────────────────────
# Versions
# ─────────────────────────────────────────────────────────────────────────────

class VersionItem(BaseModel):
    version_id: str
    name: str
    created_at: str
    artifact_count: int
    review_count: int


class VersionListResponse(APIResponse):
    versions: List[VersionItem] = []


class ArtifactInVersion(BaseModel):
    artifact_id: str
    title: str
    tags: List[str]
    is_active: bool


class VersionDetailResponse(APIResponse):
    version_id: str
    name: str
    created_at: str
    artifacts: List[ArtifactInVersion] = []


class CreateVersionRequest(BaseModel):
    project_id: str
    version_name: str
    artifact_ids: List[str]


class CreateVersionResponse(APIResponse):
    version_id: str
    name: str
    created_at: str
    artifact_count: int



# ─────────────────────────────────────────────────────────────────────────────
# Artifacts
# ─────────────────────────────────────────────────────────────────────────────

class ArtifactItem(BaseModel):
    artifact_id: str
    title: str
    tags: List[str]
    is_active: bool
    created_at: str


class ArtifactListResponse(APIResponse):
    artifacts: List[ArtifactItem] = []


class ArtifactResponse(APIResponse):
    artifact_id: str
    title: str
    tags: List[str]
    is_active: bool
    created_at: str


class UpdateArtifactRequest(BaseModel):
    active: bool


class SuggestionsResponse(APIResponse):
    suggestions: List[str] = []


# ─────────────────────────────────────────────────────────────────────────────
# Reviews
# ─────────────────────────────────────────────────────────────────────────────

class ReviewItem(BaseModel):
    review_id: str
    run_date: str
    status: str
    persona: str


class ReviewListResponse(APIResponse):
    reviews: List[ReviewItem] = []


class FindingItem(BaseModel):
    finding_id: str
    type: str
    severity: str
    text: str
    source_artifact: str
    citation: str


class FindingsSummary(BaseModel):
    risks: int = 0
    constraints: int = 0
    dependencies: int = 0
    assumptions: int = 0
    action_items: int = 0


class ReviewPayloadResponse(APIResponse):
    review_id: str
    project_id: str
    version_id: str
    status: str
    run_date: str
    persona: str
    findings: List[FindingItem] = []
    summary: FindingsSummary = FindingsSummary()


class CreateReviewRequest(BaseModel):
    version_id: str
    persona_roles: List[str]
    context: str = ""


class CreateReviewResponse(APIResponse):
    review_id: str
    status: str


class ReviewStatusResponse(APIResponse):
    review_id: str
    status: str
    progress_message: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Proposals
# ─────────────────────────────────────────────────────────────────────────────

class CreateProposalRequest(BaseModel):
    review_id: str


class CreateProposalResponse(APIResponse):
    proposal_id: str
    status: str


class ProposalStatusResponse(APIResponse):
    proposal_id: str
    status: str
    progress_message: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Admin
# ─────────────────────────────────────────────────────────────────────────────

class AdminProviders(BaseModel):
    groq: str = "not_set"
    openrouter: str = "not_set"
    gemini: str = "not_set"
    ollama: str = "not_set"


class AdminThresholds(BaseModel):
    risk: float = 0.75
    constraint: float = 0.70
    dependency: float = 0.80


class AdminHealthResponse(APIResponse):
    last_run: Optional[str] = None
    providers: AdminProviders = AdminProviders()


class AdminConfigResponse(APIResponse):
    providers: AdminProviders = AdminProviders()
    ollama_url: str = ""
    thresholds: AdminThresholds = AdminThresholds()
    max_active_projects: int = 5


class UpdateAdminConfigRequest(BaseModel):
    field: str                          # "api_key"|"threshold"|"ollama_url"|"max_active_projects"
    provider: Optional[str] = None      # for field="api_key"
    key: Optional[str] = None           # for field="api_key" (write-only)
    threshold_name: Optional[str] = None
    threshold_value: Optional[float] = None
    ollama_url: Optional[str] = None
    max_active_projects: Optional[int] = None


class AdminConfigUpdateResponse(APIResponse):
    field: str
    status: str
