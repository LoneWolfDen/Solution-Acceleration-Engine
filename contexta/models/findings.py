"""IssueFinding and UserAnnotation Pydantic models.

IssueFinding captures a single identified issue within a ReviewNodePayload,
including confidence rating, source citations, and mitigation routing.

UserAnnotation records a user override applied to a specific finding — the
core unit of the self-learning feedback loop.  Each annotation is persisted
to KnowledgeMemory so subsequent runs can incorporate prior interventions.
"""

from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, Field

from .citations import SourceCitation
from .enums import ConfidenceEnum, MitigationRoutingEnum, ReviewDimensionEnum


class IssueFinding(BaseModel):
    dimension: ReviewDimensionEnum
    confidence: ConfidenceEnum
    summary: str
    detail: str
    citations: List[SourceCitation]
    mitigation_routing: MitigationRoutingEnum


class UserAnnotation(BaseModel):
    """A user-supplied override for a single IssueFinding.

    Attributes
    ----------
    finding_index:
        Zero-based index into the parent ReviewNodePayload.base_findings list
        that this annotation targets.
    dimension:
        The ReviewDimensionEnum of the parent payload — duplicated here so the
        annotation is self-contained when read from KnowledgeMemory.
    base_value:
        Verbatim copy of the original finding summary at annotation time.
        Preserved as an immutable reference; never updated after creation.
    amended_value:
        The user's override text replacing base_value for downstream processing.
    rationale:
        Free-text explanation of why the user made this change.  Stored in
        KnowledgeMemory and injected as contextual constraints in future runs.
    timestamp:
        UTC datetime of annotation creation.  Defaults to now().
    annotator:
        Identifier for the annotating party.  Defaults to "user".
    """

    finding_index: int
    dimension: ReviewDimensionEnum
    base_value: str
    amended_value: str
    rationale: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    annotator: str = "user"
