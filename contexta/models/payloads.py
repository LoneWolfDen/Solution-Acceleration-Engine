"""
contexta/models/payloads.py — ReviewNodePayload Pydantic model.

ReviewNodePayload is the validated structured output of a single dimension
review LLM call.  Every LLM response must successfully parse into this model
before any downstream processing or database write occurs.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel

from .enums import ConfidenceEnum, ReviewDimensionEnum
from .findings import IssueFinding


class ReviewNodePayload(BaseModel):
    """
    The validated output of one dimension review task.

    This is the primary data-contract object crossing every major boundary in
    the pipeline: LLM → validation → in-memory task state → DB write.

    Attributes:
        dimension:          The review axis this payload covers.
        findings:           All issue findings discovered for this dimension.
        overall_confidence: Aggregate confidence level for the whole dimension.
        raw_llm_response:   The unmodified JSON string returned by the LLM,
                            preserved for audit and debugging purposes.
    """

    dimension:          ReviewDimensionEnum
    findings:           List[IssueFinding]
    overall_confidence: ConfidenceEnum
    raw_llm_response:   str
