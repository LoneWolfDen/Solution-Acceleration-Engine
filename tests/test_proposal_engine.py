"""Tests for Sprint 4 — ProposalEngine and ProposalValidator.

Coverage
--------
1.  ``ProposalEngine.build()`` returns a well-formed ``ProposalReport``.
2.  Every content paragraph in the proposal text contains a
    ``[ArtifactID:SectionID]`` citation reference (traceability injection).
3.  ``DesignRationale`` section is always present in the proposal text.
4.  All 12 ``ReviewDimensionEnum`` values are represented in
    ``dimension_paragraphs``.
5.  Gate 1 FAIL — paragraphs without ``[X:Y]`` refs are flagged.
6.  Gate 2 FAIL — unaddressed contradiction observations are flagged.
7.  Gate 3 FAIL — missing or filler dimensions are flagged.
8.  Gate 4 FAIL — draw.io metadata present but no DesignRationale section.
9.  Gate 4 PASS — draw.io metadata absent, gate skipped.
10. Gate 2 PASS — no conflicts present, gate skipped trivially.
11. Gate 2 PASS — observations addressed in proposal text.
12. ``ProposalReport`` is JSON-exportable (``model_dump_json`` round-trip).
13. ``JudgeValidationReport.all_passed`` reflects gate_failures correctly.
14. ``ProposalReport.citations`` contains all findings citations from input rows.
15. ``ComparisonReport`` drawio_metadata is carried through to ``ProposalReport``.
16. ``ProposalEngine.build()`` with empty review_rows produces a report with
    Gate 3 failure for all 12 dimensions.

All tests are synchronous — no LLM calls are made.
"""

from __future__ import annotations

import json
import re

import pytest

from contexta.llm.models import DimensionConflict, ReconciliationReport
from contexta.models.citations import SourceCitation
from contexta.models.enums import (
    CitationTypeEnum,
    ConfidenceEnum,
    MitigationRoutingEnum,
    ReviewDimensionEnum,
)
from contexta.models.findings import IssueFinding
from contexta.models.payloads import ReviewNodePayload
from contexta.models.proposal import (
    ComparisonReport,
    JudgeValidationReport,
    ProposalReport,
    ReviewRow,
)
from contexta.pipeline.proposal import (
    ProposalEngine,
    ProposalValidator,
    _CITATION_PATTERN,
)
from tests.fixtures import make_dimension_llm_response

# ── Helpers ───────────────────────────────────────────────────────────────────

_ARTIFACT_ID = "/proposal.md"


def _make_citation(line_start: int = 1, line_end: int = 5) -> SourceCitation:
    return SourceCitation(
        file_path=_ARTIFACT_ID,
        line_start=line_start,
        line_end=line_end,
        citation_type=CitationTypeEnum.DIRECT_REFERENCE,
        excerpt="test excerpt",
    )


def _make_finding(
    dim: ReviewDimensionEnum,
    summary: str = "Test finding",
    citations: list[SourceCitation] | None = None,
) -> IssueFinding:
    return IssueFinding(
        dimension=dim,
        confidence=ConfidenceEnum.AMBER,
        summary=summary,
        detail=f"Detailed analysis of {dim.value}",
        citations=citations if citations is not None else [_make_citation()],
        mitigation_routing=MitigationRoutingEnum.RISK_REGISTER,
    )


def _make_payload(dim: ReviewDimensionEnum) -> ReviewNodePayload:
    return ReviewNodePayload.model_validate_json(make_dimension_llm_response(dim))


def _make_review_row(
    dim: ReviewDimensionEnum,
    artifact_id: str = _ARTIFACT_ID,
) -> ReviewRow:
    return ReviewRow(artifact_id=artifact_id, payload=_make_payload(dim))


def _make_all_review_rows() -> list[ReviewRow]:
    """Return one ``ReviewRow`` per ``ReviewDimensionEnum`` value."""
    return [_make_review_row(dim) for dim in ReviewDimensionEnum]


def _make_reconciliation_report(
    conflicts: list[DimensionConflict] | None = None,
    ready: bool = False,
) -> ReconciliationReport:
    return ReconciliationReport(
        executive_summary=(
            "Project delivery is feasible with identified risks addressed."
        ),
        delivery_confidence_score=72,
        critical_conflicts=conflicts or [],
        architectural_risks=["No DR plan documented."],
        actionable_recommendations=[
            "Revisit resource allocation.",
            "Add NFR requirements for DR/HA.",
        ],
        ready_for_approval=ready,
    )


def _make_comparison_report(
    drawio_metadata: dict | None = None,
    knowledge_observations: list[str] | None = None,
    conflicts: list[DimensionConflict] | None = None,
) -> ComparisonReport:
    return ComparisonReport(
        reconciliation=_make_reconciliation_report(conflicts=conflicts),
        drawio_metadata=drawio_metadata or {},
        knowledge_observations=knowledge_observations or [],
    )


# ── ProposalEngine — basic contract ──────────────────────────────────────────


def test_build_returns_proposal_report() -> None:
    """``ProposalEngine.build()`` returns a ``ProposalReport`` instance."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    assert isinstance(report, ProposalReport)


def test_validated_text_is_non_empty() -> None:
    """The validated_text field is a non-empty string."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    assert isinstance(report.validated_text, str)
    assert len(report.validated_text) > 0


def test_proposal_report_has_judge_validation() -> None:
    """``ProposalReport.judge_validation`` is a ``JudgeValidationReport``."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    assert isinstance(report.judge_validation, JudgeValidationReport)


# ── Traceability injection (manifesto §3 Gate 1) ──────────────────────────────


def test_every_content_paragraph_has_citation_reference() -> None:
    """Every non-header paragraph in the proposal text has a [X:Y] reference."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())

    paragraphs = [p.strip() for p in report.validated_text.split("\n\n") if p.strip()]
    for para in paragraphs:
        if para.startswith("#"):
            continue  # headers are exempt
        assert _CITATION_PATTERN.search(para), (
            f"Paragraph lacks [ArtifactID:SectionID] citation:\n{para[:120]}"
        )


def test_citation_references_use_artifact_id() -> None:
    """Citation references embed the row's artifact_id as the ArtifactID part."""
    artifact_id = "/my-sow.pdf"
    rows = [ReviewRow(artifact_id=artifact_id, payload=_make_payload(dim)) for dim in ReviewDimensionEnum]
    engine = ProposalEngine()
    report = engine.build(rows, _make_comparison_report())

    assert artifact_id in report.validated_text


def test_citation_references_contain_line_range() -> None:
    """Citation refs contain the L<start>-<end> section identifier from citations."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    # make_dimension_llm_response produces citations with line_start=1, line_end=5
    assert "L1-5" in report.validated_text


def test_gate1_passes_for_engine_generated_proposal() -> None:
    """Gate 1 passes for proposals built by the engine (all paragraphs cited)."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    assert report.judge_validation.traceability_passed is True
    assert report.judge_validation.unsubstantiated_claims == []


# ── DesignRationale section (manifesto §3 Gate 4 + Diagram Rationale) ────────


def test_design_rationale_section_always_present() -> None:
    """The proposal text always includes a DesignRationale section."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    assert "DesignRationale" in report.validated_text or "Design Rationale" in report.validated_text


def test_design_rationale_no_drawio_contains_general_ref() -> None:
    """Without draw.io metadata, DesignRationale uses a [rationale:general] ref."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    assert "[rationale:general]" in report.design_rationale


def test_design_rationale_with_drawio_maps_dimensions() -> None:
    """With draw.io metadata, DesignRationale maps dimension findings to components."""
    drawio = {"components": ["API Gateway", "Data Layer"]}
    comparison = _make_comparison_report(drawio_metadata=drawio)
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), comparison)

    assert "Architecture Mapping" in report.design_rationale
    # Dimension names should appear in the rationale block
    assert "Intent" in report.design_rationale or "Architecture" in report.design_rationale


def test_design_rationale_stored_in_report_field() -> None:
    """The design_rationale field on ProposalReport matches the embedded section."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    assert report.design_rationale != ""
    # The rationale text must appear verbatim inside validated_text
    assert report.design_rationale in report.validated_text


# ── All 12 dimensions present ─────────────────────────────────────────────────


def test_all_12_dimensions_in_dimension_paragraphs() -> None:
    """``dimension_paragraphs`` contains an entry for all 12 ReviewDimensionEnum values."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    for dim in ReviewDimensionEnum:
        assert dim.value in report.dimension_paragraphs, (
            f"Missing dimension paragraph for {dim.value}"
        )


def test_all_12_dimension_headers_in_text() -> None:
    """Each dimension name appears as a section header in the proposal text."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    for dim in ReviewDimensionEnum:
        assert f"### {dim.value}" in report.validated_text, (
            f"Header for {dim.value} missing from proposal text"
        )


# ── Citations collection ───────────────────────────────────────────────────────


def test_citations_collected_from_all_rows() -> None:
    """``ProposalReport.citations`` contains all SourceCitation objects from rows."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    # make_dimension_llm_response produces 1 finding with 1 citation per dimension
    assert len(report.citations) == 12
    for c in report.citations:
        assert isinstance(c, SourceCitation)


def test_drawio_metadata_carried_to_report() -> None:
    """``drawio_metadata`` from ComparisonReport is carried through to ProposalReport."""
    drawio = {"components": ["Auth Service"], "connections": 3}
    comparison = _make_comparison_report(drawio_metadata=drawio)
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), comparison)
    assert report.drawio_metadata == drawio


# ── JSON export ───────────────────────────────────────────────────────────────


def test_proposal_report_json_serialisable() -> None:
    """``ProposalReport.model_dump_json()`` produces valid JSON."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    raw = report.model_dump_json()
    parsed = json.loads(raw)

    assert "validated_text" in parsed
    assert "citations" in parsed
    assert "judge_validation" in parsed
    assert "design_rationale" in parsed
    assert "dimension_paragraphs" in parsed


def test_proposal_report_json_round_trip_judge_validation() -> None:
    """Judge validation flags survive a JSON round-trip."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    parsed = json.loads(report.model_dump_json())

    jv = parsed["judge_validation"]
    assert isinstance(jv["traceability_passed"], bool)
    assert isinstance(jv["contradiction_check_passed"], bool)
    assert isinstance(jv["dimensional_coverage_passed"], bool)
    assert isinstance(jv["diagram_alignment_passed"], bool)
    assert isinstance(jv["gate_failures"], list)


# ── ProposalValidator — isolated gate tests ───────────────────────────────────


def test_gate1_fails_when_paragraph_lacks_citation() -> None:
    """Gate 1 is triggered when a content paragraph has no [X:Y] reference."""
    validator = ProposalValidator()
    text = "# Proposal\n\nThis paragraph has no citation reference at all."
    comparison = _make_comparison_report()

    result = validator.validate(
        text=text,
        dimension_paragraphs={d.value: f"para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=comparison,
        citations=[],
    )

    assert result.traceability_passed is False
    assert len(result.unsubstantiated_claims) == 1
    assert any("Gate 1 FAIL" in f for f in result.gate_failures)


def test_gate1_passes_for_header_only_lines() -> None:
    """Gate 1 skips lines that start with '#' (Markdown headers)."""
    validator = ProposalValidator()
    text = "# Title\n\n## Subtitle\n\n### Section\n\n**Content** [artifact:L1-5]\n- finding"
    comparison = _make_comparison_report()

    result = validator.validate(
        text=text,
        dimension_paragraphs={d.value: f"para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=comparison,
        citations=[],
    )

    assert result.traceability_passed is True
    assert result.unsubstantiated_claims == []


def test_gate2_passes_when_no_conflicts() -> None:
    """Gate 2 passes trivially when there are no critical_conflicts."""
    validator = ProposalValidator()
    comparison = _make_comparison_report(conflicts=[], knowledge_observations=["obs1"])
    text = "# Proposal\n\n**Intent** [/f.md:L1-5]\n- finding"

    result = validator.validate(
        text=text,
        dimension_paragraphs={d.value: f"para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=comparison,
        citations=[],
    )

    assert result.contradiction_check_passed is True


def test_gate2_passes_when_no_observations() -> None:
    """Gate 2 passes trivially when knowledge_observations is empty."""
    conflict = DimensionConflict(
        dimensions_involved=["Timeline", "Resource"],
        description="Conflict description.",
        severity="High",
        source_references=[],
        suggested_mitigation="Fix it.",
    )
    validator = ProposalValidator()
    comparison = _make_comparison_report(conflicts=[conflict], knowledge_observations=[])
    text = "# Proposal\n\n**Intent** [/f.md:L1-5]\n- finding"

    result = validator.validate(
        text=text,
        dimension_paragraphs={d.value: f"para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=comparison,
        citations=[],
    )

    assert result.contradiction_check_passed is True


def test_gate2_fails_when_observations_not_addressed() -> None:
    """Gate 2 fails when conflicts and observations exist but text ignores them."""
    conflict = DimensionConflict(
        dimensions_involved=["Timeline", "Resource"],
        description="Conflict description.",
        severity="High",
        source_references=[],
        suggested_mitigation="Fix it.",
    )
    validator = ProposalValidator()
    comparison = _make_comparison_report(
        conflicts=[conflict],
        knowledge_observations=["resource constraint from previous engagement"],
    )
    text = "# Proposal\n\n**Intent** [/f.md:L1-5]\n- Completely unrelated finding."

    result = validator.validate(
        text=text,
        dimension_paragraphs={d.value: f"para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=comparison,
        citations=[],
    )

    assert result.contradiction_check_passed is False
    assert any("Gate 2 FAIL" in f for f in result.gate_failures)


def test_gate2_passes_when_observation_addressed_in_text() -> None:
    """Gate 2 passes when at least one knowledge observation appears in the text."""
    conflict = DimensionConflict(
        dimensions_involved=["Timeline", "Resource"],
        description="Conflict description.",
        severity="High",
        source_references=[],
        suggested_mitigation="Fix it.",
    )
    validator = ProposalValidator()
    observation = "resource constraint from previous engagement"
    comparison = _make_comparison_report(
        conflicts=[conflict],
        knowledge_observations=[observation],
    )
    text = (
        "# Proposal\n\n"
        f"**Intent** [/f.md:L1-5]\n"
        f"The {observation} has been reviewed and accounted for."
    )

    result = validator.validate(
        text=text,
        dimension_paragraphs={d.value: f"para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=comparison,
        citations=[],
    )

    assert result.contradiction_check_passed is True


def test_gate3_fails_when_dimension_missing() -> None:
    """Gate 3 fails when one or more dimensions are absent from dimension_paragraphs."""
    validator = ProposalValidator()
    # Omit "Risk" dimension entirely
    paragraphs = {
        d.value: f"para [/f.md:L1-5]"
        for d in ReviewDimensionEnum
        if d != ReviewDimensionEnum.RISK
    }
    comparison = _make_comparison_report()
    text = "# Proposal\n\n**Intent** [/f.md:L1-5]\n- finding"

    result = validator.validate(
        text=text,
        dimension_paragraphs=paragraphs,
        comparison_report=comparison,
        citations=[],
    )

    assert result.dimensional_coverage_passed is False
    assert "Risk" in result.insufficient_depth_dimensions
    assert any("Gate 3 FAIL" in f for f in result.gate_failures)


def test_gate3_fails_for_filler_text() -> None:
    """Gate 3 flags dimensions whose paragraph text is filler (e.g. 'N/A')."""
    validator = ProposalValidator()
    paragraphs = {d.value: f"para [/f.md:L1-5]" for d in ReviewDimensionEnum}
    paragraphs[ReviewDimensionEnum.ARCHITECTURE.value] = "N/A [/f.md:L1-5]"
    comparison = _make_comparison_report()
    text = "# Proposal\n\n**Content** [/f.md:L1-5]\n- finding"

    result = validator.validate(
        text=text,
        dimension_paragraphs=paragraphs,
        comparison_report=comparison,
        citations=[],
    )

    assert result.dimensional_coverage_passed is False
    assert ReviewDimensionEnum.ARCHITECTURE.value in result.insufficient_depth_dimensions


def test_gate3_passes_when_all_12_dimensions_present() -> None:
    """Gate 3 passes when all 12 dimensions have substantive paragraphs."""
    validator = ProposalValidator()
    paragraphs = {
        d.value: f"Substantive finding text. [/f.md:L1-5]" for d in ReviewDimensionEnum
    }
    comparison = _make_comparison_report()
    text = "# Proposal\n\n**Content** [/f.md:L1-5]\n- finding"

    result = validator.validate(
        text=text,
        dimension_paragraphs=paragraphs,
        comparison_report=comparison,
        citations=[],
    )

    assert result.dimensional_coverage_passed is True
    assert result.insufficient_depth_dimensions == []


def test_gate4_passes_when_no_drawio_metadata() -> None:
    """Gate 4 passes trivially when drawio_metadata is empty."""
    validator = ProposalValidator()
    comparison = _make_comparison_report(drawio_metadata={})
    text = "# Proposal\n\n**Content** [/f.md:L1-5]\n- finding"

    result = validator.validate(
        text=text,
        dimension_paragraphs={d.value: f"para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=comparison,
        citations=[],
    )

    assert result.diagram_alignment_passed is True


def test_gate4_passes_when_drawio_present_and_rationale_exists() -> None:
    """Gate 4 passes when draw.io metadata is present and proposal has DesignRationale."""
    validator = ProposalValidator()
    comparison = _make_comparison_report(drawio_metadata={"components": ["API Gateway"]})
    text = (
        "# Proposal\n\n**Content** [/f.md:L1-5]\n- finding\n\n"
        "## DesignRationale\n\nDiagram rationale text. [rationale:general]"
    )

    result = validator.validate(
        text=text,
        dimension_paragraphs={d.value: f"para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=comparison,
        citations=[],
    )

    assert result.diagram_alignment_passed is True


def test_gate4_fails_when_drawio_present_but_no_rationale() -> None:
    """Gate 4 fails when draw.io metadata is present but DesignRationale is absent."""
    validator = ProposalValidator()
    comparison = _make_comparison_report(drawio_metadata={"components": ["API Gateway"]})
    text = "# Proposal\n\n**Content** [/f.md:L1-5]\n- finding"

    result = validator.validate(
        text=text,
        dimension_paragraphs={d.value: f"para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=comparison,
        citations=[],
    )

    assert result.diagram_alignment_passed is False
    assert any("Gate 4 FAIL" in f for f in result.gate_failures)


# ── JudgeValidationReport.all_passed ─────────────────────────────────────────


def test_all_passed_true_when_no_failures() -> None:
    """``all_passed`` is True when gate_failures is empty."""
    jvr = JudgeValidationReport(
        traceability_passed=True,
        contradiction_check_passed=True,
        dimensional_coverage_passed=True,
        diagram_alignment_passed=True,
    )
    assert jvr.all_passed is True


def test_all_passed_false_when_any_gate_fails() -> None:
    """``all_passed`` is False when at least one gate_failure is recorded."""
    jvr = JudgeValidationReport(
        traceability_passed=False,
        contradiction_check_passed=True,
        dimensional_coverage_passed=True,
        diagram_alignment_passed=True,
        gate_failures=["Gate 1 FAIL — 1 paragraph(s) lack citations"],
    )
    assert jvr.all_passed is False


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_build_with_empty_rows_flags_all_dimensions_missing() -> None:
    """``ProposalEngine.build()`` with no rows triggers Gate 3 for all 12 dims."""
    engine = ProposalEngine()
    report = engine.build([], _make_comparison_report())

    assert report.judge_validation.dimensional_coverage_passed is False
    assert len(report.judge_validation.insufficient_depth_dimensions) == 12


def test_build_with_empty_rows_citations_is_empty_list() -> None:
    """No citations when no rows are provided."""
    engine = ProposalEngine()
    report = engine.build([], _make_comparison_report())
    assert report.citations == []


def test_multiple_gates_can_fail_simultaneously() -> None:
    """Multiple gate failures are all recorded in a single validate() call."""
    validator = ProposalValidator()
    # Gate 1: no citations in text  |  Gate 3: missing dimensions
    text = "# Proposal\n\nThis paragraph has no citation at all."
    comparison = _make_comparison_report()

    result = validator.validate(
        text=text,
        dimension_paragraphs={},  # empty → Gate 3 fails for all 12
        comparison_report=comparison,
        citations=[],
    )

    assert result.traceability_passed is False
    assert result.dimensional_coverage_passed is False
    assert len(result.gate_failures) >= 2


def test_citation_pattern_regex_matches_expected_formats() -> None:
    """``_CITATION_PATTERN`` matches the canonical [ArtifactID:SectionID] format."""
    valid_refs = [
        "[/proposal.md:L1-5]",
        "[/doc.pdf:general]",
        "[sow-v2:arch-review]",
        "[reconciliation:executive-summary]",
        "[rationale:general]",
        "[rationale:no-drawio]",
    ]
    for ref in valid_refs:
        assert _CITATION_PATTERN.search(ref), f"Pattern did not match: {ref}"


def test_citation_pattern_does_not_match_plain_brackets() -> None:
    """``_CITATION_PATTERN`` does not match brackets without a colon separator."""
    invalid = "[no-colon-here]"
    assert not _CITATION_PATTERN.search(invalid)


# ── Integration: full 12-dimension build ─────────────────────────────────────


def test_full_12_dimension_build_all_gates_pass() -> None:
    """Full 12-row build with no draw.io and no conflicts: all 4 gates pass."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())

    jv = report.judge_validation
    assert jv.traceability_passed is True
    assert jv.contradiction_check_passed is True
    assert jv.dimensional_coverage_passed is True
    assert jv.diagram_alignment_passed is True
    assert jv.all_passed is True
    assert jv.gate_failures == []


def test_full_12_dimension_build_with_drawio_all_gates_pass() -> None:
    """Full 12-row build with draw.io metadata: Gate 4 passes because engine
    always generates a DesignRationale section."""
    drawio = {"components": ["Auth Service", "API Gateway"], "connections": 2}
    comparison = _make_comparison_report(drawio_metadata=drawio)
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), comparison)

    assert report.judge_validation.diagram_alignment_passed is True
    assert report.judge_validation.all_passed is True


def test_proposal_report_dimension_paragraphs_contain_finding_summaries() -> None:
    """Each dimension paragraph in the report includes the finding summary text."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())

    for dim in ReviewDimensionEnum:
        para = report.dimension_paragraphs[dim.value]
        # make_dimension_llm_response produces "Test finding for <DimValue>"
        assert f"Test finding for {dim.value}" in para, (
            f"Finding summary missing from paragraph for {dim.value}"
        )
