"""contexta/models/proposal.py — Proposal layer domain models.

Defines the typed inputs and outputs for the Sprint 4 ProposalEngine:

  - ReviewRow:               Input row pairing an artifact_id with a completed
                             ReviewNodePayload.
  - ComparisonReport:        Sprint 3 Layer 2 synthesis output augmented with
                             optional draw.io metadata and knowledge observations.
  - JudgeValidationReport:   4-gate veto output from ProposalValidator.
  - ProposalReport:          The complete, JSON-exportable proposal output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List

from pydantic import BaseModel, Field

from .citations import SourceCitation
from ..llm.models import ReconciliationReport  # concrete import — required by Pydantic v2

if TYPE_CHECKING:
    from .payloads import ReviewNodePayload


# ── Input types ───────────────────────────────────────────────────────────────


@dataclass
class ReviewRow:
    """A single dimension review row with artifact provenance.

    Attributes:
        artifact_id:  The artifact file_path as recorded by ArtifactRegistry.
                      Used as the ArtifactID component in ``[ArtifactID:SectionID]``
                      citation references injected into the proposal text.
        payload:      The validated ``ReviewNodePayload`` produced by Layer 1.
    """

    artifact_id: str
    payload: "ReviewNodePayload"


class ComparisonReport(BaseModel):
    """Augmented Layer 2 synthesis output consumed by the ProposalEngine.

    Wraps the ``ReconciliationReport`` from the ``LayerTwoArbitrator`` and
    optionally carries draw.io architecture diagram metadata and curated
    knowledge observations for Gate 2 contradiction checking.

    Attributes:
        reconciliation:          Validated ``ReconciliationReport`` from Layer 2.
        drawio_metadata:         Parsed draw.io component data.  If non-empty,
                                 Gate 4 (Diagram Alignment) is enforced.
        knowledge_observations:  Curated insights from ``global_client_insights``
                                 (Dream Cycle output).  If non-empty and
                                 ``reconciliation.critical_conflicts`` is also
                                 non-empty, Gate 2 checks that the proposal text
                                 addresses them.
    """

    reconciliation: ReconciliationReport
    drawio_metadata: Dict[str, Any] = Field(default_factory=dict)
    knowledge_observations: List[str] = Field(default_factory=list)


# ── Validation output ─────────────────────────────────────────────────────────


class JudgeValidationReport(BaseModel):
    """Output of the ProposalValidator 4-gate veto check.

    Each gate corresponds to a manifesto veto criterion:

    * **Gate 1 — Traceability Density:**   all content paragraphs contain
      ``[ArtifactID:SectionID]`` references.
    * **Gate 2 — Contradiction Check:**    proposal acknowledges known Layer 2
      conflicts when ``knowledge_observations`` are present.
    * **Gate 3 — Multi-Dimensional Coverage:**  all 12 dimensions are addressed
      with substantive text (no filler).
    * **Gate 4 — Diagram Alignment:**      draw.io artifacts have a
      DesignRationale section in the proposal text.

    Attributes:
        traceability_passed:           Gate 1 result.
        contradiction_check_passed:    Gate 2 result.
        dimensional_coverage_passed:   Gate 3 result.
        diagram_alignment_passed:      Gate 4 result.
        gate_failures:                 Human-readable failure messages per gate.
        unsubstantiated_claims:        Leading 80-char excerpts of paragraphs
                                       that failed Gate 1.
        insufficient_depth_dimensions: Dimension names that failed Gate 3.
    """

    traceability_passed: bool
    contradiction_check_passed: bool
    dimensional_coverage_passed: bool
    diagram_alignment_passed: bool
    gate_failures: List[str] = Field(default_factory=list)
    unsubstantiated_claims: List[str] = Field(default_factory=list)
    insufficient_depth_dimensions: List[str] = Field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        """``True`` only when all four gates have passed."""
        return len(self.gate_failures) == 0


# ── Proposal output ───────────────────────────────────────────────────────────


class ProposalReport(BaseModel):
    """JSON-exportable output of the ProposalEngine.

    Attributes:
        validated_text:       Full proposal text with ``[ArtifactID:SectionID]``
                              references injected throughout.
        citations:            All ``SourceCitation`` objects referenced by the
                              proposal text (order preserved from input rows).
        drawio_metadata:      draw.io component metadata carried from
                              ``ComparisonReport`` (may be empty).
        judge_validation:     ``JudgeValidationReport`` with per-gate pass/fail
                              flags and failure details.
        design_rationale:     The DesignRationale section text mapping draw.io
                              architecture to the 12-dimension findings.
        dimension_paragraphs: Per-dimension paragraph map keyed by
                              ``ReviewDimensionEnum.value`` for structured access.
    """

    validated_text: str
    citations: List[SourceCitation]
    drawio_metadata: Dict[str, Any] = Field(default_factory=dict)
    judge_validation: JudgeValidationReport
    design_rationale: str = ""
    dimension_paragraphs: Dict[str, str] = Field(default_factory=dict)
