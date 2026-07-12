"""ReviewNodePayload — layered Pydantic model.

Layered structure
-----------------
findings:
    Raw LLM response field.  The LLM populates this key; it is preserved
    unchanged so downstream code that reads ``payload.findings`` continues
    to work without modification.

base_findings:
    Immutable snapshot of the AI output.  Auto-populated from ``findings``
    on first creation via the model validator.  When loaded from the DB both
    fields are present as serialised values; ``base_findings`` is the
    canonical source of truth for the original AI output.

user_annotations:
    Ordered list of ``UserAnnotation`` objects applied by users after the
    dimension review completes.  Starts empty; grows as annotations are
    persisted through KnowledgeMemory.  Used by the TUI annotation panel
    and by the ArbitrationService to merge user intent into subsequent runs.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, model_validator

from .enums import ConfidenceEnum, ReviewDimensionEnum
from .findings import IssueFinding, UserAnnotation

# Field excluded from the schema shown to the LLM — it is injected by the
# runner after parsing and must never be produced by the model itself.
_LLM_EXCLUDED_FIELDS = {"raw_llm_response"}


class ReviewNodePayload(BaseModel):
    dimension: ReviewDimensionEnum
    findings: List[IssueFinding]
    base_findings: List[IssueFinding] = Field(default_factory=list)
    user_annotations: List[UserAnnotation] = Field(default_factory=list)
    overall_confidence: ConfidenceEnum
    raw_llm_response: str = ""

    @model_validator(mode="after")
    def _populate_base_findings(self) -> "ReviewNodePayload":
        """Snapshot findings → base_findings on first creation.

        When the LLM response is parsed, ``findings`` is populated and
        ``base_findings`` is empty.  The validator copies the list so that
        ``base_findings`` always holds the original AI output even after
        ``user_annotations`` accumulate.

        When a payload is loaded from the database both fields are already
        serialised; the guard ``if not self.base_findings`` ensures the stored
        value is not overwritten.
        """
        if not self.base_findings and self.findings:
            self.base_findings = list(self.findings)
        return self
