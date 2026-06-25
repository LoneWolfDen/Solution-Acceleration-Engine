"""Proposal pipeline data contracts — Sprint 5.

Defines the Pydantic models for ConfidenceMatrix, ProposalReport and all
supporting types produced by the ConfidenceEngine, ProposalEngine, and
ProposalValidator pipelines.

JSON-First Architecture
-----------------------
``ProposalReport`` is the terminal output of the full proposal pipeline.
Every field is designed to be directly serialisable to JSON so that
downstream consumers (TUI, export, tests) operate against a single
well-typed structure rather than ad-hoc dicts.
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

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from .enums import ConfidenceEnum, ReviewDimensionEnum


class ConfidenceMatrix(BaseModel):
    """Maps each ReviewDimension to its aggregated confidence score.

    Built by ``ConfidenceEngine.build_matrix()`` from the 12 completed
    ``ReviewNodePayload`` objects produced by Layer 1.

    Attributes
    ----------
    scores:
        Full mapping of every dimension to its ``ConfidenceEnum`` value.
    red_dimensions:
        Dimensions whose ``overall_confidence`` is ``RED`` (score 1).
    amber_dimensions:
        Dimensions whose ``overall_confidence`` is ``AMBER``.
    green_dimensions:
        Dimensions whose ``overall_confidence`` is ``GREEN``.
    has_red:
        Convenience flag — ``True`` when ``red_dimensions`` is non-empty.
        Drives mandatory Executive Risk Disclosure generation.
    """

    scores: Dict[ReviewDimensionEnum, ConfidenceEnum]
    red_dimensions: List[ReviewDimensionEnum]
    amber_dimensions: List[ReviewDimensionEnum]
    green_dimensions: List[ReviewDimensionEnum]
    has_red: bool


class RiskDisclosureItem(BaseModel):
    """Single entry in an Executive Risk Disclosure.

    Captures one RED-scored dimension, its summary, and traceable
    source citations in ``[ArtifactID:SectionID]`` format.

    Attributes
    ----------
    dimension:
        The RED-scored ``ReviewDimensionEnum`` value.
    confidence:
        Always ``ConfidenceEnum.RED`` for items in an ERD.
    summary:
        Human-readable risk summary derived from the dimension's findings.
    citation_refs:
        List of ``[ArtifactID:SectionID]`` reference strings pointing to
        the specific source material that produced the RED score.
    """

    dimension: ReviewDimensionEnum
    confidence: ConfidenceEnum
    summary: str
    citation_refs: List[str]


class ExecutiveRiskDisclosure(BaseModel):
    """Mandatory risk disclosure generated when any dimension scores RED.

    Present as the first element of a ``ProposalReport`` when the
    ``ConfidenceMatrix`` contains at least one RED-scored dimension.
    Gate 5 of ``ProposalValidator`` rejects reports that omit this
    when RED scores exist.

    Attributes
    ----------
    items:
        One ``RiskDisclosureItem`` per RED-scored dimension.
    directive:
        Overall risk directive statement summarising the disclosure scope.
    """

    items: List[RiskDisclosureItem]
    directive: str


class DiagramMetadata(BaseModel):
    """JSON definition for a draw.io architecture diagram.

    Embedded in ``ProposalReport.diagram_metadata`` keyed by
    ``diagram_id``.  The ``drawio_xml`` field contains a valid draw.io
    XML string that can be rendered or exported directly.

    Attributes
    ----------
    diagram_id:
        Unique identifier for the diagram (e.g. ``"arch-001"``).
    diagram_type:
        Category string, e.g. ``"architecture"``, ``"sequence"``,
        ``"deployment"``.
    title:
        Human-readable diagram title.
    description:
        Contextual description linking the diagram to project specifics.
    drawio_xml:
        Full draw.io XML definition string.
    related_dimensions:
        List of ``ReviewDimensionEnum`` value strings this diagram covers.
    """

    diagram_id: str
    diagram_type: str
    title: str
    description: str
    drawio_xml: str
    related_dimensions: List[str]


class ValidationGateResult(BaseModel):
    """Result of a single ProposalValidator veto gate.

    Attributes
    ----------
    gate_number:
        Integer gate index (1–6).
    gate_name:
        Short descriptive name (e.g. ``"Traceability Density"``).
    passed:
        ``True`` if the gate accepted the proposal; ``False`` if vetoed.
    reason:
        Human-readable explanation of a veto.  ``None`` when ``passed``
        is ``True``.
    """

    gate_number: int
    gate_name: str
    passed: bool
    reason: Optional[str] = None


class JudgeValidationReport(BaseModel):
    """Aggregated result of all 6 ProposalValidator veto gates.

    Attributes
    ----------
    gates:
        Ordered list of ``ValidationGateResult`` objects (gates 1–6).
    overall_passed:
        ``True`` only when every gate passes.
    rejection_reason:
        Summary of the first (or most critical) gate failure.
        ``None`` when ``overall_passed`` is ``True``.
    """

    gates: List[ValidationGateResult]
    overall_passed: bool
    rejection_reason: Optional[str] = None


class ProposalReport(BaseModel):
    """Terminal output of the full proposal pipeline.  JSON-first.

    Every field is directly serialisable.  ``proposal_text`` is Markdown
    with embedded ``[ArtifactID:SectionID]`` traceability references.
    ``executive_risk_disclosure`` is present when the ``ConfidenceMatrix``
    contains any RED-scored dimension.

    Attributes
    ----------
    proposal_text:
        Generated proposal document in Markdown format.  Every paragraph
        must contain at least one ``[ArtifactID:SectionID]`` citation.
    executive_risk_disclosure:
        Mandatory risk disclosure when RED dimensions exist.  ``None``
        when all dimensions are AMBER or GREEN.
    diagram_metadata:
        Keyed by ``diagram_id``; values are ``DiagramMetadata``-compatible
        dicts produced by the ProposalEngine.
    download_links:
        Dictionary of relative file paths to generated artefacts, e.g.
        ``{"architecture_diagram": "outputs/arch-001.drawio"}``.
    judge_validation_report:
        Results of the 6-Gate veto validation run against this report.
        ``None`` before validation is executed.
    """

    proposal_text: str
    executive_risk_disclosure: Optional[ExecutiveRiskDisclosure] = None
    diagram_metadata: Dict[str, Any] = {}
    download_links: Dict[str, str] = {}
    judge_validation_report: Optional[JudgeValidationReport] = None
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
