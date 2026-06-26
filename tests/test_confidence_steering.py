"""Sprint 5 — Confidence Steering & Synthesis Integration Tests.

Coverage
--------
ConfidenceEngine (tests 1–10):
  - build_matrix bucketing (GREEN / AMBER / RED / mixed)
  - has_red flag
  - get_red_summaries and get_red_citations formatting
  - build_risk_disclosure_items population

ProposalValidator individual gates (tests 11–27):
  - Gate 1: Traceability Density
  - Gate 2: Contradiction Check
  - Gate 3: Dimensional Coverage
  - Gate 4: Diagram Alignment
  - Gate 5: Steering Compliance (RED → ERD mandatory)
  - Gate 6: Relevance Check (filler ratio threshold)

validate() orchestrator (tests 28–30):
  - All-pass, single-gate failure, all-gates-run contract

ProposalEngine mock report (tests 31–35):
  - Schema completeness, ERD presence, dimension coverage, download_links

ProposalEngine generate() (tests 36–38):
  - LLM fallback, validation attachment, None-config mock path

Prompt building (tests 39–31):
  - ConfidenceMatrix injection, ERD directive presence/absence

No real LLM calls are made.  All LLM I/O is mocked via unittest.mock.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from contexta.models.enums import CitationTypeEnum, ConfidenceEnum, MitigationRoutingEnum, ReviewDimensionEnum
from contexta.models.citations import SourceCitation
from contexta.models.findings import IssueFinding
from contexta.models.payloads import ReviewNodePayload
from contexta.models.proposal import (
    ConfidenceMatrix,
    ExecutiveRiskDisclosure,
    JudgeValidationReport,
    ProposalReport,
    RiskDisclosureItem,
    ValidationGateResult,
)
from contexta.pipeline.confidence_engine import ConfidenceEngine
from contexta.pipeline.proposal import ProposalEngine
from contexta.pipeline.proposal_validator import ProposalValidator
from contexta.llm.prompts import build_proposal_prompt
from contexta.llm.provider import LLMConfig



# ── Shared fixtures ───────────────────────────────────────────────────────────


def _make_payload(dim: ReviewDimensionEnum, confidence: ConfidenceEnum) -> ReviewNodePayload:
    """Return a minimal ReviewNodePayload for *dim* with *confidence*."""
    citation = SourceCitation(
        file_path="proposal.md",
        line_start=1,
        line_end=5,
        citation_type=CitationTypeEnum.DIRECT_REFERENCE,
        excerpt="test excerpt",
    )
    finding = IssueFinding(
        dimension=dim,
        confidence=confidence,
        summary=f"Test finding for {dim.value}",
        detail=f"Detail for {dim.value}",
        citations=[citation],
        mitigation_routing=MitigationRoutingEnum.RISK_REGISTER,
    )
    return ReviewNodePayload(
        dimension=dim,
        findings=[finding],
        overall_confidence=confidence,
        raw_llm_response="{}",
    )


def _all_green_payloads() -> list[ReviewNodePayload]:
    return [_make_payload(d, ConfidenceEnum.GREEN) for d in ReviewDimensionEnum]


def _all_red_payloads() -> list[ReviewNodePayload]:
    return [_make_payload(d, ConfidenceEnum.RED) for d in ReviewDimensionEnum]


def _mixed_payloads() -> list[ReviewNodePayload]:
    """6 GREEN, 4 AMBER, 2 RED (Risk + Timeline)."""
    payloads = []
    for i, dim in enumerate(ReviewDimensionEnum):
        if dim in (ReviewDimensionEnum.RISK, ReviewDimensionEnum.TIMELINE):
            conf = ConfidenceEnum.RED
        elif i % 3 == 0:
            conf = ConfidenceEnum.AMBER
        else:
            conf = ConfidenceEnum.GREEN
        payloads.append(_make_payload(dim, conf))
    return payloads


def _red_matrix() -> ConfidenceMatrix:
    engine = ConfidenceEngine()
    return engine.build_matrix(_mixed_payloads())


def _green_matrix() -> ConfidenceMatrix:
    engine = ConfidenceEngine()
    return engine.build_matrix(_all_green_payloads())


def _make_report_with_citation(erd: ExecutiveRiskDisclosure | None = None) -> ProposalReport:
    """Return a ProposalReport that satisfies Gates 1, 3, 4, 6."""
    text = (
        "## Intent and Scope [artifacts:intent-001]\n"
        "The project intent and scope have been reviewed. [artifacts:scope-002]\n"
        "Ownership is clearly defined in the contract. [artifacts:ownership-003]\n"
        "Delivery timeline is aggressive but achievable. [artifacts:delivery-004]\n"
        "Timeline milestones are tracked weekly. [artifacts:timeline-005]\n"
        "Architecture follows a microservices pattern. [artifacts:arch-006]\n"
        "NFR requirements include 99.9% uptime. [artifacts:nfr-007]\n"
        "Resource allocation is documented. [artifacts:resource-008]\n"
        "Risk register is maintained. [artifacts:risk-009]\n"
        "Commercial terms are agreed. [artifacts:commercial-010]\n"
        "Language alignment confirmed. [artifacts:language-011]\n"
        "Consistency checks passed. [artifacts:consistency-012]\n"
    )
    return ProposalReport(
        proposal_text=text,
        executive_risk_disclosure=erd,
        diagram_metadata={},
        download_links={"proposal": "outputs/proposal.md"},
    )


def _make_full_erd(dims: list[ReviewDimensionEnum] | None = None) -> ExecutiveRiskDisclosure:
    dims = dims or [ReviewDimensionEnum.RISK]
    items = [
        RiskDisclosureItem(
            dimension=d,
            confidence=ConfidenceEnum.RED,
            summary=f"{d.value} is RED",
            citation_refs=[f"[artifacts:{d.value.lower()}-001]"],
        )
        for d in dims
    ]
    return ExecutiveRiskDisclosure(items=items, directive="Executive risk disclosure required.")



# ══════════════════════════════════════════════════════════════════════════════
# ConfidenceEngine tests (1–10)
# ══════════════════════════════════════════════════════════════════════════════


def test_1_build_matrix_all_green_has_no_red():
    """All-GREEN payloads → has_red is False and red_dimensions is empty."""
    engine = ConfidenceEngine()
    matrix = engine.build_matrix(_all_green_payloads())
    assert matrix.has_red is False
    assert matrix.red_dimensions == []
    assert len(matrix.green_dimensions) == 12


def test_2_build_matrix_all_red_flags_every_dimension():
    """All-RED payloads → has_red is True and all 12 dims are in red_dimensions."""
    engine = ConfidenceEngine()
    matrix = engine.build_matrix(_all_red_payloads())
    assert matrix.has_red is True
    assert len(matrix.red_dimensions) == 12
    assert matrix.green_dimensions == []
    assert matrix.amber_dimensions == []


def test_3_build_matrix_mixed_buckets_correctly():
    """Mixed payloads → Risk and Timeline land in red_dimensions."""
    engine = ConfidenceEngine()
    matrix = engine.build_matrix(_mixed_payloads())
    assert ReviewDimensionEnum.RISK in matrix.red_dimensions
    assert ReviewDimensionEnum.TIMELINE in matrix.red_dimensions
    assert len(matrix.red_dimensions) == 2


def test_4_build_matrix_has_red_true_when_any_red():
    """has_red is True as soon as at least one dimension is RED."""
    engine = ConfidenceEngine()
    payloads = [_make_payload(ReviewDimensionEnum.RISK, ConfidenceEnum.RED)]
    matrix = engine.build_matrix(payloads)
    assert matrix.has_red is True


def test_5_build_matrix_scores_maps_all_submitted_payloads():
    """scores dict contains every dimension that was submitted."""
    engine = ConfidenceEngine()
    payloads = _mixed_payloads()
    matrix = engine.build_matrix(payloads)
    for payload in payloads:
        assert payload.dimension in matrix.scores
        assert matrix.scores[payload.dimension] == payload.overall_confidence


def test_6_build_matrix_single_amber_payload():
    """Single AMBER payload → 1 amber, 0 red, 0 green, has_red False."""
    engine = ConfidenceEngine()
    matrix = engine.build_matrix([_make_payload(ReviewDimensionEnum.NFR, ConfidenceEnum.AMBER)])
    assert matrix.has_red is False
    assert ReviewDimensionEnum.NFR in matrix.amber_dimensions


def test_7_get_red_summaries_returns_first_finding():
    """get_red_summaries returns the first finding summary for each RED dim."""
    engine = ConfidenceEngine()
    payloads = _mixed_payloads()
    matrix = engine.build_matrix(payloads)
    summaries = engine.get_red_summaries(payloads, matrix)
    assert ReviewDimensionEnum.RISK in summaries
    assert summaries[ReviewDimensionEnum.RISK] == "Test finding for Risk"


def test_8_get_red_citations_formats_as_artifact_refs():
    """get_red_citations formats SourceCitations as [file:start-end] strings."""
    engine = ConfidenceEngine()
    payloads = _mixed_payloads()
    matrix = engine.build_matrix(payloads)
    citations = engine.get_red_citations(payloads, matrix)
    assert ReviewDimensionEnum.RISK in citations
    refs = citations[ReviewDimensionEnum.RISK]
    assert len(refs) > 0
    assert refs[0].startswith("[")
    assert "proposal.md" in refs[0]


def test_9_build_risk_disclosure_items_empty_when_no_red():
    """build_risk_disclosure_items returns [] when matrix.has_red is False."""
    engine = ConfidenceEngine()
    matrix = engine.build_matrix(_all_green_payloads())
    items = engine.build_risk_disclosure_items(_all_green_payloads(), matrix)
    assert items == []


def test_10_build_risk_disclosure_items_one_per_red_dim():
    """build_risk_disclosure_items returns one RiskDisclosureItem per RED dim."""
    engine = ConfidenceEngine()
    payloads = _mixed_payloads()
    matrix = engine.build_matrix(payloads)
    items = engine.build_risk_disclosure_items(payloads, matrix)
    assert len(items) == len(matrix.red_dimensions)
    dims_in_items = {item.dimension for item in items}
    assert dims_in_items == set(matrix.red_dimensions)
    for item in items:
        assert item.confidence == ConfidenceEnum.RED



# ══════════════════════════════════════════════════════════════════════════════
# ProposalValidator — Gate 1: Traceability Density (tests 11–12)
# ══════════════════════════════════════════════════════════════════════════════


def test_11_gate1_passes_when_citation_present():
    """Gate 1 passes when proposal_text contains a [X:Y] citation."""
    validator = ProposalValidator()
    report = ProposalReport(
        proposal_text="The project scope is clear. [artifacts:scope-001]",
        download_links={},
    )
    result = validator.gate_1_traceability_density(report)
    assert result.passed is True
    assert result.gate_number == 1
    assert result.reason is None


def test_12_gate1_fails_when_no_citation():
    """Gate 1 fails when proposal_text has no [X:Y] citation pattern."""
    validator = ProposalValidator()
    report = ProposalReport(
        proposal_text="The project scope is clear with no references.",
        download_links={},
    )
    result = validator.gate_1_traceability_density(report)
    assert result.passed is False
    assert "citation" in result.reason.lower()


# ══════════════════════════════════════════════════════════════════════════════
# ProposalValidator — Gate 2: Contradiction Check (tests 13–15)
# ══════════════════════════════════════════════════════════════════════════════


def test_13_gate2_passes_with_empty_contradictions():
    """Gate 2 passes when contradiction list is empty."""
    validator = ProposalValidator()
    report = ProposalReport(proposal_text="Some proposal text.", download_links={})
    result = validator.gate_2_contradiction_check(report, [])
    assert result.passed is True
    assert result.gate_number == 2


def test_14_gate2_fails_when_contradiction_echoed_verbatim():
    """Gate 2 fails when a 6-word fragment of a contradiction appears in text."""
    validator = ProposalValidator()
    contradiction_desc = "the timeline is too aggressive given resource constraints here"
    report = ProposalReport(
        proposal_text=f"We note that {contradiction_desc} in the proposal.",
        download_links={},
    )
    result = validator.gate_2_contradiction_check(
        report, [{"description": contradiction_desc}]
    )
    assert result.passed is False
    assert "contradiction" in result.reason.lower()


def test_15_gate2_passes_when_contradictions_not_echoed():
    """Gate 2 passes when contradiction descriptions don't appear in proposal text."""
    validator = ProposalValidator()
    report = ProposalReport(
        proposal_text="The delivery plan is sound. [artifacts:delivery-001]",
        download_links={},
    )
    contradictions = [{"description": "timeline is optimistic given identified resource gaps"}]
    result = validator.gate_2_contradiction_check(report, contradictions)
    assert result.passed is True


# ══════════════════════════════════════════════════════════════════════════════
# ProposalValidator — Gate 3: Dimensional Coverage (tests 16–17)
# ══════════════════════════════════════════════════════════════════════════════


def test_16_gate3_passes_with_six_or_more_dimensions():
    """Gate 3 passes when ≥6 ReviewDimensionEnum names appear in proposal_text."""
    validator = ProposalValidator()
    report = _make_report_with_citation()
    result = validator.gate_3_dimensional_coverage(report)
    assert result.passed is True
    assert result.gate_number == 3


def test_17_gate3_fails_with_fewer_than_six_dimensions():
    """Gate 3 fails when <6 ReviewDimensionEnum names appear in text."""
    validator = ProposalValidator()
    report = ProposalReport(
        proposal_text="Only Risk and Timeline are discussed. [artifacts:001]",
        download_links={},
    )
    result = validator.gate_3_dimensional_coverage(report)
    assert result.passed is False
    assert "dimension" in result.reason.lower()


# ══════════════════════════════════════════════════════════════════════════════
# ProposalValidator — Gate 4: Diagram Alignment (tests 18–20)
# ══════════════════════════════════════════════════════════════════════════════


def test_18_gate4_passes_when_no_diagram_metadata():
    """Gate 4 passes when diagram_metadata is empty (no diagrams expected)."""
    validator = ProposalValidator()
    report = ProposalReport(proposal_text="No diagrams here.", diagram_metadata={}, download_links={})
    result = validator.gate_4_diagram_alignment(report)
    assert result.passed is True
    assert result.gate_number == 4


def test_19_gate4_passes_when_diagram_metadata_and_text_mentions_diagram():
    """Gate 4 passes when diagram_metadata is present AND text mentions 'diagram'."""
    validator = ProposalValidator()
    report = ProposalReport(
        proposal_text="See the architecture diagram below. [artifacts:arch-001]",
        diagram_metadata={"arch-001": {"diagram_id": "arch-001"}},
        download_links={},
    )
    result = validator.gate_4_diagram_alignment(report)
    assert result.passed is True


def test_20_gate4_fails_when_diagram_metadata_present_but_text_lacks_reference():
    """Gate 4 fails when diagram_metadata is non-empty but text has no diagram mention."""
    validator = ProposalValidator()
    report = ProposalReport(
        proposal_text="The project scope is clear. [artifacts:scope-001]",
        diagram_metadata={"arch-001": {"diagram_id": "arch-001"}},
        download_links={},
    )
    result = validator.gate_4_diagram_alignment(report)
    assert result.passed is False
    assert "diagram" in result.reason.lower()



# ══════════════════════════════════════════════════════════════════════════════
# ProposalValidator — Gate 5: Steering Compliance (tests 21–25)
# ══════════════════════════════════════════════════════════════════════════════


def test_21_gate5_passes_when_no_red_dimensions():
    """Gate 5 passes when matrix has no RED dimensions (ERD not required)."""
    validator = ProposalValidator()
    report = ProposalReport(proposal_text="All green.", download_links={})
    result = validator.gate_5_steering_compliance(report, _green_matrix())
    assert result.passed is True
    assert result.gate_number == 5


def test_22_gate5_passes_when_red_and_erd_present():
    """Gate 5 passes when RED exists AND executive_risk_disclosure is populated."""
    validator = ProposalValidator()
    erd = _make_full_erd([ReviewDimensionEnum.RISK, ReviewDimensionEnum.TIMELINE])
    report = _make_report_with_citation(erd=erd)
    result = validator.gate_5_steering_compliance(report, _red_matrix())
    assert result.passed is True


def test_23_gate5_fails_when_red_but_no_erd():
    """Gate 5 fails when RED dimensions exist but executive_risk_disclosure is None."""
    validator = ProposalValidator()
    report = _make_report_with_citation(erd=None)
    result = validator.gate_5_steering_compliance(report, _red_matrix())
    assert result.passed is False
    assert result.reason is not None


def test_24_gate5_failure_reason_names_red_dimensions():
    """Gate 5 failure reason contains the names of the RED dimensions."""
    validator = ProposalValidator()
    report = _make_report_with_citation(erd=None)
    matrix = _red_matrix()
    result = validator.gate_5_steering_compliance(report, matrix)
    assert result.passed is False
    for dim in matrix.red_dimensions:
        assert dim.value in result.reason


def test_25_gate5_fails_when_erd_present_but_items_empty():
    """Gate 5 fails when ERD is present but its items list is empty."""
    validator = ProposalValidator()
    empty_erd = ExecutiveRiskDisclosure(items=[], directive="No items.")
    report = _make_report_with_citation(erd=empty_erd)
    result = validator.gate_5_steering_compliance(report, _red_matrix())
    assert result.passed is False


# ══════════════════════════════════════════════════════════════════════════════
# ProposalValidator — Gate 6: Relevance Check (tests 26–28)
# ══════════════════════════════════════════════════════════════════════════════


def test_26_gate6_passes_when_filler_below_threshold():
    """Gate 6 passes when filler ratio is well below 20%."""
    validator = ProposalValidator()
    # 10 specific sentences (with citations), 1 filler → 9% filler
    specific = " ".join(
        f"The {d.value} dimension was reviewed. [artifacts:{d.value.lower()}-001]"
        for d in list(ReviewDimensionEnum)[:10]
    )
    filler = "Typically, projects of this nature require careful planning."
    report = ProposalReport(
        proposal_text=f"{specific} {filler}",
        download_links={},
    )
    result = validator.gate_6_relevance_check(report)
    assert result.passed is True
    assert result.gate_number == 6


def test_27_gate6_fails_when_filler_exceeds_threshold():
    """Gate 6 fails when more than 20% of sentences are generic filler."""
    validator = ProposalValidator()
    # 3 filler sentences out of 5 total → 60% filler
    filler_sentences = (
        "Typically, SDLC projects follow a structured approach. "
        "Best practice dictates a phased delivery model. "
        "Most organizations adopt agile methodologies. "
        "The project scope is defined. [artifacts:scope-001] "
        "Risk management is in place. [artifacts:risk-001]"
    )
    report = ProposalReport(proposal_text=filler_sentences, download_links={})
    result = validator.gate_6_relevance_check(report)
    assert result.passed is False
    assert "filler" in result.reason.lower() or "%" in result.reason


def test_28_gate6_cited_sentence_never_counted_as_filler():
    """A sentence with a [X:Y] citation is never counted as filler, even if it matches a pattern."""
    validator = ProposalValidator()
    # Sentence matches a filler pattern but has a citation — must NOT be filler.
    report = ProposalReport(
        proposal_text=(
            "Typically, delivery risk is elevated in this project [artifacts:risk-001]. "
            "Best practice here is to mitigate via a phased approach [artifacts:scope-002]. "
            "Risk and Delivery dimensions confirm this. [artifacts:risk-002]"
        ),
        download_links={},
    )
    result = validator.gate_6_relevance_check(report)
    assert result.passed is True



# ══════════════════════════════════════════════════════════════════════════════
# ProposalValidator — validate() orchestrator (tests 29–31)
# ══════════════════════════════════════════════════════════════════════════════


def test_29_validate_all_gates_pass_returns_overall_passed():
    """validate() returns overall_passed=True when all 6 gates pass."""
    validator = ProposalValidator()
    erd = _make_full_erd([ReviewDimensionEnum.RISK, ReviewDimensionEnum.TIMELINE])
    report = _make_report_with_citation(erd=erd)
    result = validator.validate(report, _red_matrix(), contradictions=[])
    assert isinstance(result, JudgeValidationReport)
    assert result.overall_passed is True
    assert result.rejection_reason is None
    assert len(result.gates) == 6


def test_30_validate_gate5_failure_sets_overall_failed():
    """validate() sets overall_passed=False when Gate 5 fails (RED without ERD)."""
    validator = ProposalValidator()
    report = _make_report_with_citation(erd=None)  # RED matrix but no ERD
    result = validator.validate(report, _red_matrix(), contradictions=[])
    assert result.overall_passed is False
    assert result.rejection_reason is not None
    failed_gates = [g for g in result.gates if not g.passed]
    assert any(g.gate_number == 5 for g in failed_gates)


def test_31_validate_runs_all_six_gates_regardless_of_failure():
    """validate() always returns exactly 6 gate results even when gates fail."""
    validator = ProposalValidator()
    # Deliberately bad report: no citation (Gate 1 fails) + no dimensions (Gate 3 fails)
    report = ProposalReport(
        proposal_text="No citations and no dimensions here.",
        executive_risk_disclosure=None,
        download_links={},
    )
    result = validator.validate(report, _red_matrix(), contradictions=[])
    assert len(result.gates) == 6
    gate_numbers = [g.gate_number for g in result.gates]
    assert gate_numbers == [1, 2, 3, 4, 5, 6]


# ══════════════════════════════════════════════════════════════════════════════
# ProposalEngine — mock report schema (tests 32–36)
# ══════════════════════════════════════════════════════════════════════════════


def test_32_mock_report_has_all_required_fields():
    """_build_mock_report produces a ProposalReport with all JSON fields populated."""
    engine = ProposalEngine(config=None)
    matrix = _red_matrix()
    report = engine._build_mock_report(matrix)
    assert isinstance(report.proposal_text, str)
    assert len(report.proposal_text) > 0
    assert isinstance(report.diagram_metadata, dict)
    assert isinstance(report.download_links, dict)
    assert len(report.diagram_metadata) > 0
    assert len(report.download_links) > 0


def test_33_mock_report_includes_erd_when_matrix_has_red():
    """_build_mock_report sets executive_risk_disclosure when matrix.has_red is True."""
    engine = ProposalEngine(config=None)
    report = engine._build_mock_report(_red_matrix())
    assert report.executive_risk_disclosure is not None
    assert len(report.executive_risk_disclosure.items) > 0
    for item in report.executive_risk_disclosure.items:
        assert item.confidence == ConfidenceEnum.RED


def test_34_mock_report_no_erd_when_all_green():
    """_build_mock_report sets executive_risk_disclosure to None when no RED."""
    engine = ProposalEngine(config=None)
    report = engine._build_mock_report(_green_matrix())
    assert report.executive_risk_disclosure is None


def test_35_mock_report_mentions_all_twelve_dimensions():
    """_build_mock_report proposal_text mentions all 12 ReviewDimensionEnum names."""
    engine = ProposalEngine(config=None)
    report = engine._build_mock_report(_red_matrix())
    text_lower = report.proposal_text.lower()
    for dim in ReviewDimensionEnum:
        assert dim.value.lower() in text_lower, (
            f"Dimension '{dim.value}' missing from mock proposal_text"
        )


def test_36_mock_report_download_links_non_empty():
    """_build_mock_report always produces at least one download_link entry."""
    engine = ProposalEngine(config=None)
    report = engine._build_mock_report(_green_matrix())
    assert len(report.download_links) >= 1
    for key, path in report.download_links.items():
        assert isinstance(key, str) and len(key) > 0
        assert isinstance(path, str) and len(path) > 0



# ══════════════════════════════════════════════════════════════════════════════
# ProposalEngine — generate() async path (tests 37–39)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_37_generate_with_no_config_returns_mock_report():
    """generate() with config=None returns a valid mock ProposalReport."""
    engine = ProposalEngine(config=None)
    payloads = _mixed_payloads()
    report = await engine.generate(payloads, artifact_context="Test artifacts")
    assert isinstance(report, ProposalReport)
    assert report.judge_validation_report is not None
    assert isinstance(report.judge_validation_report, JudgeValidationReport)
    assert len(report.judge_validation_report.gates) == 6


@pytest.mark.asyncio
async def test_38_generate_falls_back_to_mock_on_llm_failure():
    """generate() falls back to mock report when LLM call raises an exception."""
    config = LLMConfig(model="ollama/mistral")
    engine = ProposalEngine(config=config)

    with patch(
        "contexta.llm.provider.litellm.acompletion",
        AsyncMock(side_effect=Exception("Connection refused")),
    ):
        report = await engine.generate(_mixed_payloads(), artifact_context="Test artifacts")

    assert isinstance(report, ProposalReport)
    assert len(report.proposal_text) > 0
    assert report.judge_validation_report is not None


@pytest.mark.asyncio
async def test_39_generate_attaches_judge_validation_report():
    """generate() always attaches a JudgeValidationReport with 6 gates."""
    engine = ProposalEngine(config=None)
    report = await engine.generate(_all_green_payloads(), artifact_context="Artifacts here")
    assert report.judge_validation_report is not None
    assert len(report.judge_validation_report.gates) == 6
    for gate in report.judge_validation_report.gates:
        assert isinstance(gate, ValidationGateResult)
        assert gate.gate_number in range(1, 7)


# ══════════════════════════════════════════════════════════════════════════════
# Proposal prompt building (tests 40–42)
# ══════════════════════════════════════════════════════════════════════════════


def test_40_proposal_prompt_contains_confidence_matrix_scores():
    """build_proposal_prompt system prompt contains each dimension and its score."""
    matrix = _red_matrix()
    system, user = build_proposal_prompt(matrix, artifact_context="Test artifacts")
    for dim, score in matrix.scores.items():
        assert dim.value in system
        assert score.value in system


def test_41_proposal_prompt_contains_erd_directive_when_red_exists():
    """build_proposal_prompt injects ERD directive when matrix.has_red is True."""
    matrix = _red_matrix()
    system, _ = build_proposal_prompt(matrix, artifact_context="Artifacts")
    assert "Executive Risk Disclosure" in system
    assert "RED" in system
    for dim in matrix.red_dimensions:
        assert dim.value in system


def test_42_proposal_prompt_no_erd_directive_when_all_green():
    """build_proposal_prompt omits ERD directive when matrix.has_red is False."""
    matrix = _green_matrix()
    system, _ = build_proposal_prompt(matrix, artifact_context="Artifacts")
    assert "MANDATORY EXECUTIVE RISK DISCLOSURE" not in system


def test_43_proposal_prompt_always_contains_conciseness_constraint():
    """build_proposal_prompt always injects the conciseness constraint."""
    for matrix in (_green_matrix(), _red_matrix()):
        system, _ = build_proposal_prompt(matrix, artifact_context="Artifacts")
        assert "project-specific" in system
        assert "ArtifactID:SectionID" in system


def test_44_proposal_prompt_includes_arbitrator_summary_when_provided():
    """build_proposal_prompt user prompt includes arbitrator summary when given."""
    matrix = _green_matrix()
    _, user = build_proposal_prompt(
        matrix,
        artifact_context="Test artifacts",
        arbitrator_summary="Timeline and Resource are in conflict.",
    )
    assert "ARBITRATOR SUMMARY" in user
    assert "Timeline and Resource are in conflict." in user


def test_45_proposal_prompt_artifact_context_in_user_message():
    """build_proposal_prompt places artifact_context in the user message."""
    matrix = _green_matrix()
    _, user = build_proposal_prompt(matrix, artifact_context="UNIQUE_ARTIFACT_CONTENT_XYZ")
    assert "UNIQUE_ARTIFACT_CONTENT_XYZ" in user
