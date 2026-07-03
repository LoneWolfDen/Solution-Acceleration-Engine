"""ReviewNodePayload Pydantic model.

The validated output of a single dimension review.  Every LLM response MUST
pass through ``ReviewNodePayload.model_validate_json()`` before any downstream
processing or database write occurs.
"""

from typing import List

from pydantic import BaseModel

from .enums import ConfidenceEnum, ReviewDimensionEnum
from .findings import IssueFinding


class ReviewNodePayload(BaseModel):
    dimension: ReviewDimensionEnum
    findings: List[IssueFinding]
    overall_confidence: ConfidenceEnum
    raw_llm_response: str = ""  # populated by pipeline after LLM validation, not by the LLM
