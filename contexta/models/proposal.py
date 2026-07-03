"""Proposal pipeline data contracts.

Sprint 5 models (ConfidenceMatrix, ProposalReport, JudgeValidationReport and
supporting types) are the canonical pipeline output consumed by
ConfidenceEngine, ProposalEngine, and ProposalValidator.

Sprint 4 models (ReviewRow, ComparisonReport) are preserved for backward
compatibility with the traceable-proposal pipeline and its test suite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .citations import SourceCitation
from .enums import ConfidenceEnum, ReviewDimensionEnum
from ..llm.models import ReconciliationReport

if TYPE_CHECKING:
    from .payloads import ReviewNodePayload


# ── Sprint 5 models ───────────────────────────────────────────────────────────


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

    Captures one RED-scored dimension, its summary, and traceable source
    citations in ``[ArtifactID:SectionID]`` format.
    """

    dimension: ReviewDimensionEnum
    confidence: ConfidenceEnum
    summary: str
    citation_refs: List[str]


class ExecutiveRiskDisclosure(BaseModel):
    """Mandatory risk disclosure generated when any dimension scores RED.

    Present as the first element of a ``ProposalReport`` when the
    ``ConfidenceMatrix`` contains at least one RED-scored dimension.
    Gate 5 of ``ProposalValidator`` rejects reports that omit this when
    RED scores exist.
    """

    items: List[RiskDisclosureItem]
    directive: str


class DiagramMetadata(BaseModel):
    """JSON definition for a draw.io architecture diagram."""

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
        Short descriptive name, e.g. ``"Traceability Density"``.
    passed:
        ``True`` if the gate accepted the proposal.
    reason:
        Human-readable veto explanation.  ``None`` when ``passed`` is ``True``.
    """

    gate_number: int
    gate_name: str
    passed: bool
    reason: Optional[str] = None


class JudgeValidationReport(BaseModel):
    """Aggregated result of all ProposalValidator veto gates.

    Attributes
    ----------
    gates:
        Ordered list of ``ValidationGateResult`` objects.
    overall_passed:
        ``True`` only when every gate passes.
    rejection_reason:
        Summary of the first failing gate's reason.
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
        Generated proposal document in Markdown format.
    executive_risk_disclosure:
        Mandatory risk disclosure when RED dimensions exist.
    diagram_metadata:
        Keyed by ``diagram_id``; draw.io-compatible dicts.
    download_links:
        Relative paths to generated artefacts.
    judge_validation_report:
        Results of the veto validation run.  ``None`` before validation.
    """

    proposal_text: str
    executive_risk_disclosure: Optional[ExecutiveRiskDisclosure] = None
    diagram_metadata: Dict[str, Any] = {}
    download_links: Dict[str, str] = {}
    judge_validation_report: Optional[JudgeValidationReport] = None


# ── Sprint 4 models (backward compatibility) ──────────────────────────────────


@dataclass
class ReviewRow:
    """A single dimension review row with artifact provenance.

    Used by ``ProposalEngine.build()`` to pair an artifact path with a
    completed ``ReviewNodePayload`` for deterministic proposal generation.

    Attributes
    ----------
    artifact_id:
        The artifact ``file_path`` as recorded by ``ArtifactRegistry``.
        Used as the ``ArtifactID`` component in ``[ArtifactID:SectionID]``
        citation references injected into the proposal text.
    payload:
        The validated ``ReviewNodePayload`` produced by Layer 1.
    """

    artifact_id: str
    payload: "ReviewNodePayload"


class ComparisonReport(BaseModel):
    """Augmented Layer 2 synthesis output consumed by ``ProposalEngine.build()``.

    Wraps the ``ReconciliationReport`` from the ``LayerTwoArbitrator`` and
    optionally carries draw.io architecture diagram metadata and curated
    knowledge observations for Gate 2 contradiction checking.

    Attributes
    ----------
    reconciliation:
        Validated ``ReconciliationReport`` from Layer 2.
    drawio_metadata:
        Parsed draw.io component data.  If non-empty Gate 4 is enforced.
    knowledge_observations:
        Curated insights from ``global_client_insights`` (Dream Cycle output).
    """

    reconciliation: ReconciliationReport
    drawio_metadata: Dict[str, Any] = Field(default_factory=dict)
    knowledge_observations: List[str] = Field(default_factory=list)
