"""IssueFinding Pydantic model.

Captures a single identified issue within a ReviewNodePayload, including
confidence rating, source citations, and mitigation routing.
"""

from typing import List

from pydantic import BaseModel

from .citations import SourceCitation
from .enums import ConfidenceEnum, MitigationRoutingEnum, ReviewDimensionEnum


class IssueFinding(BaseModel):
    dimension: ReviewDimensionEnum
    confidence: ConfidenceEnum
    summary: str
    detail: str
    citations: List[SourceCitation]
    mitigation_routing: MitigationRoutingEnum
