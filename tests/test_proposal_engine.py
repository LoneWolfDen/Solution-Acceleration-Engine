"""Sprint 4 Traceable Proposal Engine — test suite (updated for Sprint 5 schemas).

Coverage
--------
1.  ``ProposalEngine.build()`` returns a well-formed ``ProposalReport``.
2.  Every content paragraph in the proposal text contains a
    ``[ArtifactID:SectionID]`` citation reference (traceability injection).
3.  ``DesignRationale`` section is always present in the proposal text.
4.  All 12 ``ReviewDimensionEnum`` values are represented in the proposal text.
5.  Gate 1 FAIL — paragraphs without ``[X:Y]`` refs are flagged.
6.  Gate 2 FAIL — unaddressed contradiction observations are flagged.
7.  Gate 3 FAIL — missing or filler dimensions are flagged.
8.  Gate 4 FAIL — draw.io metadata present but no DesignRationale section.
9.  Gate 4 PASS — draw.io metadata absent, gate skipped.
10. Gate 2 PASS — no conflicts present, gate skipped trivially.
11. Gate 2 PASS — observations addressed in proposal text.
12. ``ProposalReport`` is JSON-exportable (``model_dump_json`` round-trip).
13. ``JudgeValidationReport.overall_passed`` reflects gate results correctly.
14. ``ProposalReport.diagram_metadata`` carries drawio_metadata from input.
15. ``ProposalEngine.build()`` with empty review_rows produces Gate 3 failure.

All tests are synchronous — no LLM calls are made.

NOTE: Field names updated to Sprint 5 schema:
  - ``report.proposal_text``         (was ``validated_text``)
  - ``report.judge_validation_report`` (was ``judge_validation``)
  - ``jvr.overall_passed``           (was ``all_passed``)
  - ``jvr.gates``                    (was per-field booleans)
  - ``jvr.rejection_reason``         (new — first failing gate reason)
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
    ValidationGateResult,
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


def _make_payload(dim: ReviewDimensionEnum) -> ReviewNodePayload:
    return ReviewNodePayload.model_validate_json(make_dimension_llm_response(dim))


def _make_review_row(
    dim: ReviewDimensionEnum,
    artifact_id: str = _ARTIFACT_ID,
) -> ReviewRow:
    return ReviewRow(artifact_id=artifact_id, payload=_make_payload(dim))


def _make_all_review_rows() -> list[ReviewRow]:
    return [_make_review_row(dim) for dim in ReviewDimensionEnum]


def _make_reconciliation_report(
    conflicts: list[DimensionConflict] | None = None,
    ready: bool = False,
) -> ReconciliationReport:
    return ReconciliationReport(
        executive_summary="Project delivery is feasible with identified risks addressed.",
        delivery_confidence_score=72,
        critical_conflicts=conflicts or [],
        architectural_risks=["No DR plan documented."],
        actionable_recommendations=["Revisit resource allocation.", "Add NFR for DR."],
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


def _gate(jvr: JudgeValidationReport, number: int) -> ValidationGateResult:
    """Return the gate result for the given gate number."""
    return next(g for g in jvr.gates if g.gate_number == number)


def _gate_failures(jvr: JudgeValidationReport) -> list[str]:
    """Return all non-None gate reasons for failing gates."""
    return [g.reason for g in jvr.gates if not g.passed and g.reason]


# ── ProposalEngine — basic contract ──────────────────────────────────────────


def test_build_returns_proposal_report() -> None:
    """``ProposalEngine.build()`` returns a ``ProposalReport`` instance."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    assert isinstance(report, ProposalReport)


def test_proposal_text_is_non_empty() -> None:
    """The proposal_text field is a non-empty string."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    assert isinstance(report.proposal_text, str)
    assert len(report.proposal_text) > 0


def test_proposal_report_has_judge_validation_report() -> None:
    """``ProposalReport.judge_validation_report`` is a ``JudgeValidationReport``."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    assert isinstance(report.judge_validation_report, JudgeValidationReport)


# ── Traceability injection (Gate 1) ──────────────────────────────────────────


def test_every_content_paragraph_has_citation_reference() -> None:
    """Every non-header paragraph in the proposal text has a [X:Y] reference."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    paragraphs = [p.strip() for p in report.proposal_text.split("\n\n") if p.strip()]
    for para in paragraphs:
        if para.startswith("#"):
            continue
        assert _CITATION_PATTERN.search(para), (
            f"Paragraph lacks [ArtifactID:SectionID] citation:\n{para[:120]}"
        )


def test_citation_references_use_artifact_id() -> None:
    """Citation references embed the row's artifact_id."""
    artifact_id = "/my-sow.pdf"
    rows = [
        ReviewRow(artifact_id=artifact_id, payload=_make_payload(dim))
        for dim in ReviewDimensionEnum
    ]
    engine = ProposalEngine()
    report = engine.build(rows, _make_comparison_report())
    assert artifact_id in report.proposal_text


def test_citation_references_contain_line_range() -> None:
    """Citation refs contain the L<start>-<end> section identifier."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    assert "L1-5" in report.proposal_text


def test_gate1_passes_for_engine_generated_proposal() -> None:
    """Gate 1 passes for proposals built by the engine (all paragraphs cited)."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    jvr = report.judge_validation_report
    g1 = _gate(jvr, 1)
    assert g1.passed is True
    assert g1.reason is None


# ── DesignRationale section (Gate 4) ─────────────────────────────────────────


def test_design_rationale_section_always_present() -> None:
    """The proposal text always includes a DesignRationale section."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    assert (
        "DesignRationale" in report.proposal_text
        or "Design Rationale" in report.proposal_text
    )


def test_design_rationale_no_drawio_contains_general_ref() -> None:
    """Without draw.io metadata, DesignRationale uses a [rationale:general] ref."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    assert "[rationale:general]" in report.proposal_text


def test_design_rationale_with_drawio_maps_dimensions() -> None:
    """With draw.io metadata, DesignRationale maps dimension findings to components."""
    drawio = {"components": ["API Gateway", "Data Layer"]}
    comparison = _make_comparison_report(drawio_metadata=drawio)
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), comparison)
    assert "Architecture Mapping" in report.proposal_text


# ── All 12 dimensions present ─────────────────────────────────────────────────


def test_all_12_dimensions_in_proposal_text() -> None:
    """All 12 ReviewDimensionEnum values appear in proposal_text."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    for dim in ReviewDimensionEnum:
        assert dim.value in report.proposal_text, (
            f"Missing dimension {dim.value} in proposal_text"
        )


def test_all_12_dimension_headers_in_text() -> None:
    """Each dimension name appears as a section header in the proposal text."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    for dim in ReviewDimensionEnum:
        assert f"### {dim.value}" in report.proposal_text, (
            f"Header for {dim.value} missing from proposal text"
        )


# ── draw.io metadata pass-through ─────────────────────────────────────────────


def test_drawio_metadata_carried_to_report() -> None:
    """``drawio_metadata`` from ComparisonReport is carried through to ProposalReport."""
    drawio = {"components": ["Auth Service"], "connections": 3}
    comparison = _make_comparison_report(drawio_metadata=drawio)
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), comparison)
    assert report.diagram_metadata == drawio


# ── JSON export ───────────────────────────────────────────────────────────────


def test_proposal_report_json_serialisable() -> None:
    """``ProposalReport.model_dump_json()`` produces valid JSON."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    raw = report.model_dump_json()
    parsed = json.loads(raw)
    assert "proposal_text" in parsed
    assert "judge_validation_report" in parsed
    assert "diagram_metadata" in parsed


def test_proposal_report_json_round_trip_judge_validation() -> None:
    """Judge validation fields survive a JSON round-trip."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    parsed = json.loads(report.model_dump_json())
    jv = parsed["judge_validation_report"]
    assert isinstance(jv["overall_passed"], bool)
    assert isinstance(jv["gates"], list)
    assert len(jv["gates"]) == 4
    for gate in jv["gates"]:
        assert isinstance(gate["passed"], bool)
        assert isinstance(gate["gate_name"], str)


# ── ProposalValidator — isolated gate tests ───────────────────────────────────


def test_gate1_fails_when_paragraph_lacks_citation() -> None:
    """Gate 1 is triggered when a content paragraph has no [X:Y] reference."""
    validator = ProposalValidator()
    text = "# Proposal\n\nThis paragraph has no citation reference at all."
    result = validator.validate(
        text=text,
        dimension_paragraphs={d.value: "para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=_make_comparison_report(),
        citations=[],
    )
    g1 = _gate(result, 1)
    assert g1.passed is False
    assert "Gate 1 FAIL" in (g1.reason or "")


def test_gate1_passes_for_header_only_lines() -> None:
    """Gate 1 skips lines that start with '#' (Markdown headers)."""
    validator = ProposalValidator()
    text = "# Title\n\n## Subtitle\n\n### Section\n\n**Content** [artifact:L1-5]\n- finding"
    result = validator.validate(
        text=text,
        dimension_paragraphs={d.value: "para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=_make_comparison_report(),
        citations=[],
    )
    assert _gate(result, 1).passed is True


def test_gate2_passes_when_no_conflicts() -> None:
    """Gate 2 passes trivially when there are no critical_conflicts."""
    validator = ProposalValidator()
    comparison = _make_comparison_report(conflicts=[], knowledge_observations=["obs1"])
    result = validator.validate(
        text="# Proposal\n\n**Intent** [/f.md:L1-5]\n- finding",
        dimension_paragraphs={d.value: "para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=comparison,
        citations=[],
    )
    assert _gate(result, 2).passed is True


def test_gate2_passes_when_no_observations() -> None:
    """Gate 2 passes trivially when knowledge_observations is empty."""
    conflict = DimensionConflict(
        dimensions_involved=["Timeline", "Resource"],
        description="Conflict.",
        severity="High",
        source_references=[],
        suggested_mitigation="Fix it.",
    )
    validator = ProposalValidator()
    comparison = _make_comparison_report(conflicts=[conflict], knowledge_observations=[])
    result = validator.validate(
        text="# Proposal\n\n**Intent** [/f.md:L1-5]\n- finding",
        dimension_paragraphs={d.value: "para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=comparison,
        citations=[],
    )
    assert _gate(result, 2).passed is True


def test_gate2_fails_when_observations_not_addressed() -> None:
    """Gate 2 fails when conflicts and observations exist but text ignores them."""
    conflict = DimensionConflict(
        dimensions_involved=["Timeline", "Resource"],
        description="Conflict.",
        severity="High",
        source_references=[],
        suggested_mitigation="Fix it.",
    )
    validator = ProposalValidator()
    comparison = _make_comparison_report(
        conflicts=[conflict],
        knowledge_observations=["resource constraint from previous engagement"],
    )
    result = validator.validate(
        text="# Proposal\n\n**Intent** [/f.md:L1-5]\n- Completely unrelated finding.",
        dimension_paragraphs={d.value: "para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=comparison,
        citations=[],
    )
    g2 = _gate(result, 2)
    assert g2.passed is False
    assert "Gate 2 FAIL" in (g2.reason or "")


def test_gate2_passes_when_observation_addressed_in_text() -> None:
    """Gate 2 passes when at least one knowledge observation appears in the text."""
    conflict = DimensionConflict(
        dimensions_involved=["Timeline", "Resource"],
        description="Conflict.",
        severity="High",
        source_references=[],
        suggested_mitigation="Fix it.",
    )
    observation = "resource constraint from previous engagement"
    validator = ProposalValidator()
    comparison = _make_comparison_report(
        conflicts=[conflict], knowledge_observations=[observation]
    )
    text = (
        "# Proposal\n\n"
        f"**Intent** [/f.md:L1-5]\n"
        f"The {observation} has been reviewed and accounted for."
    )
    result = validator.validate(
        text=text,
        dimension_paragraphs={d.value: "para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=comparison,
        citations=[],
    )
    assert _gate(result, 2).passed is True


def test_gate3_fails_when_dimension_missing() -> None:
    """Gate 3 fails when one or more dimensions are absent from dimension_paragraphs."""
    validator = ProposalValidator()
    paragraphs = {
        d.value: "para [/f.md:L1-5]"
        for d in ReviewDimensionEnum
        if d != ReviewDimensionEnum.RISK
    }
    result = validator.validate(
        text="# Proposal\n\n**Intent** [/f.md:L1-5]\n- finding",
        dimension_paragraphs=paragraphs,
        comparison_report=_make_comparison_report(),
        citations=[],
    )
    g3 = _gate(result, 3)
    assert g3.passed is False
    assert "Risk" in (g3.reason or "")
    assert "Gate 3 FAIL" in (g3.reason or "")


def test_gate3_fails_for_filler_text() -> None:
    """Gate 3 flags dimensions whose paragraph text is filler (e.g. 'N/A')."""
    validator = ProposalValidator()
    paragraphs = {d.value: "para [/f.md:L1-5]" for d in ReviewDimensionEnum}
    paragraphs[ReviewDimensionEnum.ARCHITECTURE.value] = "N/A [/f.md:L1-5]"
    result = validator.validate(
        text="# Proposal\n\n**Content** [/f.md:L1-5]\n- finding",
        dimension_paragraphs=paragraphs,
        comparison_report=_make_comparison_report(),
        citations=[],
    )
    g3 = _gate(result, 3)
    assert g3.passed is False
    assert ReviewDimensionEnum.ARCHITECTURE.value in (g3.reason or "")


def test_gate3_passes_when_all_12_dimensions_present() -> None:
    """Gate 3 passes when all 12 dimensions have substantive paragraphs."""
    validator = ProposalValidator()
    paragraphs = {
        d.value: "Substantive finding text. [/f.md:L1-5]" for d in ReviewDimensionEnum
    }
    result = validator.validate(
        text="# Proposal\n\n**Content** [/f.md:L1-5]\n- finding",
        dimension_paragraphs=paragraphs,
        comparison_report=_make_comparison_report(),
        citations=[],
    )
    assert _gate(result, 3).passed is True


def test_gate4_passes_when_no_drawio_metadata() -> None:
    """Gate 4 passes trivially when drawio_metadata is empty."""
    validator = ProposalValidator()
    result = validator.validate(
        text="# Proposal\n\n**Content** [/f.md:L1-5]\n- finding",
        dimension_paragraphs={d.value: "para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=_make_comparison_report(drawio_metadata={}),
        citations=[],
    )
    assert _gate(result, 4).passed is True


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
        dimension_paragraphs={d.value: "para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=comparison,
        citations=[],
    )
    assert _gate(result, 4).passed is True


def test_gate4_fails_when_drawio_present_but_no_rationale() -> None:
    """Gate 4 fails when draw.io metadata is present but DesignRationale is absent."""
    validator = ProposalValidator()
    comparison = _make_comparison_report(drawio_metadata={"components": ["API Gateway"]})
    result = validator.validate(
        text="# Proposal\n\n**Content** [/f.md:L1-5]\n- finding",
        dimension_paragraphs={d.value: "para [/f.md:L1-5]" for d in ReviewDimensionEnum},
        comparison_report=comparison,
        citations=[],
    )
    g4 = _gate(result, 4)
    assert g4.passed is False
    assert "Gate 4 FAIL" in (g4.reason or "")


# ── JudgeValidationReport overall_passed ─────────────────────────────────────


def test_overall_passed_true_when_all_gates_pass() -> None:
    """``overall_passed`` is True when all gates pass."""
    gates = [
        ValidationGateResult(gate_number=i, gate_name=f"Gate {i}", passed=True)
        for i in range(1, 5)
    ]
    jvr = JudgeValidationReport(gates=gates, overall_passed=True)
    assert jvr.overall_passed is True
    assert jvr.rejection_reason is None


def test_overall_passed_false_when_any_gate_fails() -> None:
    """``overall_passed`` is False when at least one gate fails."""
    gates = [
        ValidationGateResult(
            gate_number=1,
            gate_name="Traceability Density",
            passed=False,
            reason="Gate 1 FAIL — 1 paragraph(s) lack citations",
        ),
        *[
            ValidationGateResult(gate_number=i, gate_name=f"Gate {i}", passed=True)
            for i in range(2, 5)
        ],
    ]
    jvr = JudgeValidationReport(
        gates=gates,
        overall_passed=False,
        rejection_reason="Gate 1 FAIL — 1 paragraph(s) lack citations",
    )
    assert jvr.overall_passed is False
    assert jvr.rejection_reason is not None


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_build_with_empty_rows_flags_all_dimensions_missing() -> None:
    """``ProposalEngine.build()`` with no rows triggers Gate 3 for all 12 dims."""
    engine = ProposalEngine()
    report = engine.build([], _make_comparison_report())
    jvr = report.judge_validation_report
    g3 = _gate(jvr, 3)
    assert g3.passed is False
    assert jvr.overall_passed is False


def test_multiple_gates_can_fail_simultaneously() -> None:
    """Multiple gate failures are all recorded in a single validate() call."""
    validator = ProposalValidator()
    result = validator.validate(
        text="# Proposal\n\nThis paragraph has no citation at all.",
        dimension_paragraphs={},
        comparison_report=_make_comparison_report(),
        citations=[],
    )
    failed_gates = [g for g in result.gates if not g.passed]
    assert len(failed_gates) >= 2
    assert result.overall_passed is False


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
    assert not _CITATION_PATTERN.search("[no-colon-here]")


# ── Integration: full 12-dimension build ─────────────────────────────────────


def test_full_12_dimension_build_all_gates_pass() -> None:
    """Full 12-row build with no draw.io and no conflicts: all 4 gates pass."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    jvr = report.judge_validation_report
    assert jvr.overall_passed is True
    assert jvr.rejection_reason is None
    for gate in jvr.gates:
        assert gate.passed is True, f"Gate {gate.gate_number} ({gate.gate_name}) failed"


def test_full_12_dimension_build_with_drawio_all_gates_pass() -> None:
    """Full 12-row build with draw.io metadata: Gate 4 passes (engine adds rationale)."""
    drawio = {"components": ["Auth Service", "API Gateway"], "connections": 2}
    comparison = _make_comparison_report(drawio_metadata=drawio)
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), comparison)
    jvr = report.judge_validation_report
    assert _gate(jvr, 4).passed is True
    assert jvr.overall_passed is True


def test_proposal_report_dimension_paragraphs_contain_finding_summaries() -> None:
    """The proposal text includes the finding summary text for each dimension."""
    engine = ProposalEngine()
    report = engine.build(_make_all_review_rows(), _make_comparison_report())
    for dim in ReviewDimensionEnum:
        assert f"Test finding for {dim.value}" in report.proposal_text, (
            f"Finding summary missing for {dim.value}"
        )
