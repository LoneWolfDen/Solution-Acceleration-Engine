"""
contexta/models/findings.py — IssueFinding Pydantic model.

An IssueFinding captures a single identified risk or issue within one dimension
review.  It must always carry at least a summary, a confidence rating, and a
routing decision.  Source citations are optional (an LLM may produce zero).
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel

from .citations import SourceCitation
from .enums import ConfidenceEnum, MitigationRoutingEnum, ReviewDimensionEnum


class IssueFinding(BaseModel):
    """
    A single identified issue within a dimension review.

    Attributes:
        dimension:          The review axis this finding belongs to.
        confidence:         Risk confidence level: RED / AMBER / GREEN.
        summary:            Short headline description of the issue.
        detail:             Full explanation with context and implications.
        citations:          Zero or more SourceCitation objects grounding the
                            finding in specific artefact content.
        mitigation_routing: Governance routing decision for this finding.
    """

    dimension:          ReviewDimensionEnum
    confidence:         ConfidenceEnum
    summary:            str
    detail:             str
    citations:          List[SourceCitation]
    mitigation_routing: MitigationRoutingEnum
