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
