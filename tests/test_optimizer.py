"""tests/test_optimizer.py — Sprint 6: The Learning Loop.

Coverage
--------
Section 1 — JudgeValidationReport / evaluate_reconciliation_report
  - All 6 gates pass on a perfect report.
  - Each individual gate fails when its specific threshold is violated.
  - overall_passed reflects the AND of all gate results.
  - Failed gates always carry a rejection_reason; passed gates carry None.
  - evaluate_reconciliation_report() always produces exactly 6 gate results.

Section 2 — PromptOptimizer
  - Citation extraction returns empty on empty/synthesis-only input.
  - Citation counts are accurate; sorted descending by frequency.
  - Malformed metadata_json is skipped without raising.
  - run_for_project() persists a CITATION_TREND record to intelligence_layer.

Section 3 — KnowledgeAggregator
  - compute_confidence_matrix() returns correct structure for 0, 1, and N versions.
  - Versions with no assigned nodes produce an empty dimension dict.
  - run_for_project() persists a CONFIDENCE_TREND record to intelligence_layer.

Section 4 — PromptDelta
  - generate() returns empty delta when all gates pass.
  - Each failed gate maps to a distinct adjustment_key in delta_json.
  - All 6 gates failing produces 6 delta entries.
  - base_prompt_length and applied_to_blueprint_id are recorded accurately.
  - run() persists a PROMPT_DELTA record to intelligence_layer.

Section 5 — DB / Repository layer
  - intelligence_layer table is created by init_database().
  - SCHEMA_VERSION is 5.
  - write_intelligence_record() inserts and returns a correct IntelligenceRow.
  - project_id=None (global) and project_id=<id> (scoped) round-trips.
  - get_intelligence_for_project() filters by project only.
  - get_intelligence_global() returns only NULL-project records.
  - get_intelligence_by_type() filters by type; optionally scoped to project.
"""

from __future__ import annotations

import json
from typing import Optional

import pytest
import pytest_asyncio

from contexta.db.models import BlueprintRow, IntelligenceRow, NodeRow
from contexta.db.repositories import (
    create_project,
    create_version,
    get_intelligence_by_type,
    get_intelligence_for_project,
    get_intelligence_global,
    write_intelligence_record,
    write_node,
)
from contexta.db.schema import SCHEMA_VERSION, init_database

from contexta.llm.models import (
    GATE_DELIVERY_CONFIDENCE_THRESHOLD,
    GATE_EXECUTIVE_SUMMARY_MIN_LENGTH,
    GATE_MAX_CRITICAL_CONFLICTS,
    DimensionConflict,
    GateNameEnum,
    JudgeValidationReport,
    ReconciliationReport,
    evaluate_reconciliation_report,
)
from contexta.models.enums import ConfidenceEnum, ReviewDimensionEnum
from contexta.models.payloads import ReviewNodePayload
from contexta.pipeline.optimizer import (
    INSIGHT_TYPE_CITATION_TREND,
    INSIGHT_TYPE_CONFIDENCE_TREND,
    INSIGHT_TYPE_PROMPT_DELTA,
    CitationTrend,
    ConfidenceMatrix,
    KnowledgeAggregator,
    PromptDelta,
    PromptDeltaResult,
    PromptOptimizer,
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures and helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db():
    """Fresh in-memory database for each test."""
    conn = await init_database(":memory:")
    yield conn
    await conn.close()


def _good_report() -> ReconciliationReport:
    """A ReconciliationReport that passes all 6 gates."""
    return ReconciliationReport(
        executive_summary=(
            "Project delivery is feasible. "
            "Timeline and resource dimensions are well aligned."
        ),
        delivery_confidence_score=75,
        critical_conflicts=[],
        architectural_risks=["Minor API gateway risk."],
        actionable_recommendations=["Confirm headcount before sign-off."],
        ready_for_approval=True,
    )


def _conflict(severity: str = "High") -> DimensionConflict:
    return DimensionConflict(
        dimensions_involved=["Timeline", "Resource"],
        description="Timeline too aggressive.",
        severity=severity,
        source_references=["SOW §3"],
        suggested_mitigation="Extend by 4 weeks.",
    )


def _blueprint(prompt_text: str = "Review with rigour.") -> BlueprintRow:
    return BlueprintRow(
        id="bp-test-001",
        blueprint_name="Test Blueprint",
        version_string="1.0.0",
        master_prompt_text=prompt_text,
        is_active=True,
    )


def _exploration_node(metadata: dict, version_id: Optional[str] = None) -> NodeRow:
    """Construct an in-memory exploration NodeRow with given metadata dict."""
    return NodeRow(
        id="node-test-001",
        project_id="proj-test-001",
        parent_id=None,
        layer_type="exploration",
        node_name="Test Exploration",
        metadata_json=metadata,
        content_markdown="",
        created_at="2025-01-01T00:00:00+00:00",
        version_id=version_id,
    )


def _synthesis_node(metadata: dict) -> NodeRow:
    return NodeRow(
        id="node-synth-001",
        project_id="proj-test-001",
        parent_id=None,
        layer_type="synthesis",
        node_name="Test Synthesis",
        metadata_json=metadata,
        content_markdown="",
        created_at="2025-01-01T00:00:00+00:00",
    )


def _dimension_metadata(
    dimensions: Optional[list] = None,
) -> dict:
    """Build metadata_json['dimensions'] for an exploration node."""
    if dimensions is None:
        dimensions = [
            {
                "dimension": "Risk",
                "overall_confidence": "AMBER",
                "findings": [
                    {
                        "dimension": "Risk",
                        "confidence": "AMBER",
                        "summary": "Risk found",
                        "detail": "detail",
                        "citations": [
                            {
                                "file_path": "/proposal.md",
                                "line_start": 1,
                                "line_end": 5,
                                "citation_type": "Direct Reference",
                                "excerpt": "excerpt",
                            }
                        ],
                        "mitigation_routing": "Risk Register",
                    }
                ],
            }
        ]
    return {"dimensions": dimensions, "completed_at": "2025-01-01T00:00:00+00:00"}



# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — JudgeValidationReport / evaluate_reconciliation_report
# ─────────────────────────────────────────────────────────────────────────────

def test_evaluate_all_gates_pass_on_good_report() -> None:
    """A structurally sound report passes all 6 gates."""
    report = _good_report()
    result = evaluate_reconciliation_report(report)
    assert isinstance(result, JudgeValidationReport)
    assert result.overall_passed is True
    assert len(result.gate_checks) == 6
    assert all(g.passed for g in result.gate_checks)
    assert all(g.rejection_reason is None for g in result.gate_checks)


def test_evaluate_always_produces_exactly_6_gates() -> None:
    """Property: evaluate_reconciliation_report always returns exactly 6 gate results."""
    for ready in (True, False):
        for score in (10, 60, 100):
            report = ReconciliationReport(
                executive_summary="A" * 60,
                delivery_confidence_score=score,
                critical_conflicts=[],
                architectural_risks=[],
                actionable_recommendations=["Do something."],
                ready_for_approval=ready,
            )
            result = evaluate_reconciliation_report(report)
            assert len(result.gate_checks) == 6, (
                f"Expected 6 gates, got {len(result.gate_checks)} "
                f"for score={score}, ready={ready}"
            )


def test_overall_passed_is_false_when_any_gate_fails() -> None:
    """overall_passed must be False when at least one gate fails."""
    report = ReconciliationReport(
        executive_summary="A" * 60,
        delivery_confidence_score=75,
        critical_conflicts=[],
        architectural_risks=[],
        actionable_recommendations=["Step 1."],
        ready_for_approval=False,  # APPROVAL_GATE fails
    )
    result = evaluate_reconciliation_report(report)
    assert result.overall_passed is False


def test_failed_gate_always_carries_rejection_reason() -> None:
    """Every failed gate must have a non-empty rejection_reason string."""
    report = ReconciliationReport(
        executive_summary="short",  # EXECUTIVE_SUMMARY fails
        delivery_confidence_score=40,  # DELIVERY_CONFIDENCE fails
        critical_conflicts=[_conflict("Critical")],  # CONFLICT_SEVERITY fails
        architectural_risks=[],
        actionable_recommendations=[],  # RECOMMENDATIONS fails
        ready_for_approval=False,  # APPROVAL_GATE fails
    )
    result = evaluate_reconciliation_report(report)
    for gate in result.gate_checks:
        if not gate.passed:
            assert gate.rejection_reason is not None
            assert len(gate.rejection_reason) > 0, (
                f"Gate {gate.gate_name!r} failed but rejection_reason is empty."
            )


def test_gate_approval_gate_fails_on_false() -> None:
    """APPROVAL_GATE fails when ready_for_approval is False."""
    report = _good_report()
    object.__setattr__(report, "ready_for_approval", False)
    result = evaluate_reconciliation_report(report)
    gate = next(g for g in result.gate_checks if g.gate_name == GateNameEnum.APPROVAL_GATE)
    assert gate.passed is False
    assert "ready_for_approval" in gate.rejection_reason


def test_gate_delivery_confidence_fails_below_threshold() -> None:
    """DELIVERY_CONFIDENCE fails when score < GATE_DELIVERY_CONFIDENCE_THRESHOLD."""
    report = _good_report()
    object.__setattr__(report, "delivery_confidence_score", GATE_DELIVERY_CONFIDENCE_THRESHOLD - 1)
    result = evaluate_reconciliation_report(report)
    gate = next(g for g in result.gate_checks if g.gate_name == GateNameEnum.DELIVERY_CONFIDENCE)
    assert gate.passed is False
    assert str(GATE_DELIVERY_CONFIDENCE_THRESHOLD - 1) in gate.rejection_reason


def test_gate_delivery_confidence_passes_at_threshold() -> None:
    """DELIVERY_CONFIDENCE passes when score == GATE_DELIVERY_CONFIDENCE_THRESHOLD."""
    report = _good_report()
    object.__setattr__(report, "delivery_confidence_score", GATE_DELIVERY_CONFIDENCE_THRESHOLD)
    result = evaluate_reconciliation_report(report)
    gate = next(g for g in result.gate_checks if g.gate_name == GateNameEnum.DELIVERY_CONFIDENCE)
    assert gate.passed is True


def test_gate_conflict_severity_fails_on_critical() -> None:
    """CONFLICT_SEVERITY_CONTROL fails when any conflict has severity='Critical'."""
    report = _good_report()
    object.__setattr__(report, "critical_conflicts", [_conflict("Critical")])
    result = evaluate_reconciliation_report(report)
    gate = next(g for g in result.gate_checks if g.gate_name == GateNameEnum.CONFLICT_SEVERITY_CONTROL)
    assert gate.passed is False
    assert "Critical" in gate.rejection_reason


def test_gate_conflict_severity_passes_on_high() -> None:
    """CONFLICT_SEVERITY_CONTROL passes when severity is 'High' (not 'Critical')."""
    report = _good_report()
    object.__setattr__(report, "critical_conflicts", [_conflict("High")])
    result = evaluate_reconciliation_report(report)
    gate = next(g for g in result.gate_checks if g.gate_name == GateNameEnum.CONFLICT_SEVERITY_CONTROL)
    assert gate.passed is True


def test_gate_conflict_count_fails_above_max() -> None:
    """CONFLICT_COUNT_BOUNDED fails when len(critical_conflicts) > GATE_MAX_CRITICAL_CONFLICTS."""
    report = _good_report()
    too_many = [_conflict("High")] * (GATE_MAX_CRITICAL_CONFLICTS + 1)
    object.__setattr__(report, "critical_conflicts", too_many)
    result = evaluate_reconciliation_report(report)
    gate = next(g for g in result.gate_checks if g.gate_name == GateNameEnum.CONFLICT_COUNT_BOUNDED)
    assert gate.passed is False


def test_gate_conflict_count_passes_at_max() -> None:
    """CONFLICT_COUNT_BOUNDED passes when len(critical_conflicts) == GATE_MAX_CRITICAL_CONFLICTS."""
    report = _good_report()
    object.__setattr__(report, "critical_conflicts", [_conflict("High")] * GATE_MAX_CRITICAL_CONFLICTS)
    result = evaluate_reconciliation_report(report)
    gate = next(g for g in result.gate_checks if g.gate_name == GateNameEnum.CONFLICT_COUNT_BOUNDED)
    assert gate.passed is True


def test_gate_recommendations_present_fails_on_empty() -> None:
    """RECOMMENDATIONS_PRESENT fails when actionable_recommendations is empty."""
    report = _good_report()
    object.__setattr__(report, "actionable_recommendations", [])
    result = evaluate_reconciliation_report(report)
    gate = next(g for g in result.gate_checks if g.gate_name == GateNameEnum.RECOMMENDATIONS_PRESENT)
    assert gate.passed is False


def test_gate_executive_summary_fails_below_min_length() -> None:
    """EXECUTIVE_SUMMARY_SUBSTANTIVE fails when summary length < GATE_EXECUTIVE_SUMMARY_MIN_LENGTH."""
    report = _good_report()
    object.__setattr__(report, "executive_summary", "X" * (GATE_EXECUTIVE_SUMMARY_MIN_LENGTH - 1))
    result = evaluate_reconciliation_report(report)
    gate = next(g for g in result.gate_checks if g.gate_name == GateNameEnum.EXECUTIVE_SUMMARY_SUBSTANTIVE)
    assert gate.passed is False


def test_gate_executive_summary_passes_at_min_length() -> None:
    """EXECUTIVE_SUMMARY_SUBSTANTIVE passes when summary length == GATE_EXECUTIVE_SUMMARY_MIN_LENGTH."""
    report = _good_report()
    object.__setattr__(report, "executive_summary", "X" * GATE_EXECUTIVE_SUMMARY_MIN_LENGTH)
    result = evaluate_reconciliation_report(report)
    gate = next(g for g in result.gate_checks if g.gate_name == GateNameEnum.EXECUTIVE_SUMMARY_SUBSTANTIVE)
    assert gate.passed is True



# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — PromptOptimizer
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prompt_optimizer_empty_nodes_returns_empty_trends(db) -> None:
    """extract_citation_trends([]) returns an empty list."""
    optimizer = PromptOptimizer(db)
    result = optimizer.extract_citation_trends([])
    assert result == []


@pytest.mark.asyncio
async def test_prompt_optimizer_skips_synthesis_nodes(db) -> None:
    """Synthesis nodes are ignored; only exploration nodes contribute citations."""
    optimizer = PromptOptimizer(db)
    synth = _synthesis_node(_dimension_metadata())
    result = optimizer.extract_citation_trends([synth])
    assert result == []


@pytest.mark.asyncio
async def test_prompt_optimizer_counts_single_citation(db) -> None:
    """A single citation produces one CitationTrend with frequency=1."""
    optimizer = PromptOptimizer(db)
    node = _exploration_node(_dimension_metadata())
    result = optimizer.extract_citation_trends([node])
    assert len(result) == 1
    assert result[0].artifact_id == "/proposal.md"
    assert result[0].section_id == "1-5"
    assert result[0].frequency == 1


@pytest.mark.asyncio
async def test_prompt_optimizer_aggregates_duplicate_citations(db) -> None:
    """The same citation span across two nodes produces frequency=2."""
    optimizer = PromptOptimizer(db)
    node1 = _exploration_node(_dimension_metadata())
    node2 = NodeRow(
        id="node-002",
        project_id="proj-001",
        parent_id=None,
        layer_type="exploration",
        node_name="Node 2",
        metadata_json=_dimension_metadata(),
        content_markdown="",
        created_at="2025-01-02T00:00:00+00:00",
    )
    result = optimizer.extract_citation_trends([node1, node2])
    assert len(result) == 1
    assert result[0].frequency == 2


@pytest.mark.asyncio
async def test_prompt_optimizer_sorted_by_frequency_descending(db) -> None:
    """Citations are returned sorted descending by frequency."""
    optimizer = PromptOptimizer(db)
    meta_multi = {
        "dimensions": [
            {
                "dimension": "Risk",
                "overall_confidence": "AMBER",
                "findings": [
                    {
                        "dimension": "Risk",
                        "confidence": "AMBER",
                        "summary": "s",
                        "detail": "d",
                        "citations": [
                            {"file_path": "/a.md", "line_start": 1, "line_end": 2,
                             "citation_type": "Direct Reference", "excerpt": "e"},
                            {"file_path": "/b.md", "line_start": 10, "line_end": 20,
                             "citation_type": "Direct Reference", "excerpt": "e"},
                        ],
                        "mitigation_routing": "Risk Register",
                    }
                ],
            }
        ]
    }
    node1 = _exploration_node(meta_multi)
    # /a.md appears in both nodes → frequency 2; /b.md only in node1 → frequency 1
    node2 = _exploration_node(_dimension_metadata())  # cites /proposal.md:1-5
    # Replace /proposal.md with /a.md for node2
    meta_a = {
        "dimensions": [
            {
                "dimension": "Scope",
                "overall_confidence": "GREEN",
                "findings": [
                    {
                        "dimension": "Scope",
                        "confidence": "GREEN",
                        "summary": "s",
                        "detail": "d",
                        "citations": [
                            {"file_path": "/a.md", "line_start": 1, "line_end": 2,
                             "citation_type": "Direct Reference", "excerpt": "e"},
                        ],
                        "mitigation_routing": "Ignored",
                    }
                ],
            }
        ]
    }
    node2b = NodeRow(
        id="node-003", project_id="p", parent_id=None, layer_type="exploration",
        node_name="n", metadata_json=meta_a, content_markdown="",
        created_at="2025-01-03T00:00:00+00:00",
    )
    result = optimizer.extract_citation_trends([node1, node2b])
    # /a.md:1-2 appears twice, /b.md:10-20 once
    assert result[0].artifact_id == "/a.md"
    assert result[0].frequency == 2
    assert result[1].frequency == 1


@pytest.mark.asyncio
async def test_prompt_optimizer_malformed_metadata_skipped(db) -> None:
    """Nodes with malformed metadata_json are skipped silently without raising."""
    optimizer = PromptOptimizer(db)
    bad_node = NodeRow(
        id="node-bad", project_id="p", parent_id=None, layer_type="exploration",
        node_name="bad", metadata_json="NOT VALID JSON <<<", content_markdown="",
        created_at="2025-01-01T00:00:00+00:00",
    )
    result = optimizer.extract_citation_trends([bad_node])
    assert result == []


@pytest.mark.asyncio
async def test_prompt_optimizer_run_for_project_persists_citation_trend(db) -> None:
    """run_for_project() writes a CITATION_TREND record to intelligence_layer."""
    project = await create_project(db, "Test Project", [])
    payload = ReviewNodePayload(
        dimension=ReviewDimensionEnum.RISK,
        findings=[],
        overall_confidence=ConfidenceEnum.GREEN,
        raw_llm_response="{}",
    )
    await write_node(
        db, project.id, None, "exploration", "Node 1", payload,
        _dimension_metadata(),
    )
    optimizer = PromptOptimizer(db)
    record = await optimizer.run_for_project(project.id)
    assert isinstance(record, IntelligenceRow)
    assert record.insight_type == INSIGHT_TYPE_CITATION_TREND
    assert record.project_id == project.id
    payload_data = json.loads(record.payload_json)
    assert "trends" in payload_data



# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — KnowledgeAggregator
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_knowledge_aggregator_no_versions_returns_empty_matrix(db) -> None:
    """A project with no versions produces an empty ConfidenceMatrix."""
    project = await create_project(db, "Empty Project", [])
    aggregator = KnowledgeAggregator(db)
    matrix = await aggregator.compute_confidence_matrix(project.id)
    assert isinstance(matrix, ConfidenceMatrix)
    assert matrix.project_id == project.id
    assert matrix.version_order == []
    assert matrix.matrix == {}


@pytest.mark.asyncio
async def test_knowledge_aggregator_single_version_single_node(db) -> None:
    """A single version with one exploration node populates the matrix correctly."""
    project = await create_project(db, "Single Version Project", [])
    version = await create_version(db, project.id, "v1.0")
    payload = ReviewNodePayload(
        dimension=ReviewDimensionEnum.RISK,
        findings=[],
        overall_confidence=ConfidenceEnum.GREEN,
        raw_llm_response="{}",
    )
    meta = {
        "dimensions": [
            {"dimension": "Risk", "overall_confidence": "GREEN", "findings": []},
            {"dimension": "Timeline", "overall_confidence": "AMBER", "findings": []},
        ]
    }
    await write_node(
        db, project.id, None, "exploration", "v1 node", payload, meta,
        version_id=version.id,
    )
    aggregator = KnowledgeAggregator(db)
    matrix = await aggregator.compute_confidence_matrix(project.id)
    assert version.id in matrix.version_order
    assert matrix.matrix[version.id]["Risk"] == "GREEN"
    assert matrix.matrix[version.id]["Timeline"] == "AMBER"


@pytest.mark.asyncio
async def test_knowledge_aggregator_version_with_no_nodes_has_empty_dict(db) -> None:
    """A version with no exploration nodes appears in version_order with empty dict."""
    project = await create_project(db, "Sparse Project", [])
    v1 = await create_version(db, project.id, "v1.0")
    v2 = await create_version(db, project.id, "v2.0")
    payload = ReviewNodePayload(
        dimension=ReviewDimensionEnum.SCOPE,
        findings=[],
        overall_confidence=ConfidenceEnum.RED,
        raw_llm_response="{}",
    )
    meta = {"dimensions": [{"dimension": "Scope", "overall_confidence": "RED", "findings": []}]}
    await write_node(db, project.id, None, "exploration", "v1 node", payload, meta, version_id=v1.id)
    aggregator = KnowledgeAggregator(db)
    matrix = await aggregator.compute_confidence_matrix(project.id)
    assert v1.id in matrix.version_order
    assert v2.id in matrix.version_order
    assert matrix.matrix[v1.id] == {"Scope": "RED"}
    assert matrix.matrix[v2.id] == {}


@pytest.mark.asyncio
async def test_knowledge_aggregator_multi_version_trend(db) -> None:
    """Three versions show dimension confidence trend (RED → AMBER → GREEN)."""
    project = await create_project(db, "Trend Project", [])
    v1 = await create_version(db, project.id, "v1.0")
    v2 = await create_version(db, project.id, "v2.0")
    v3 = await create_version(db, project.id, "v3.0")
    confidences = [("RED", v1.id), ("AMBER", v2.id), ("GREEN", v3.id)]
    base_payload = ReviewNodePayload(
        dimension=ReviewDimensionEnum.TIMELINE,
        findings=[],
        overall_confidence=ConfidenceEnum.GREEN,
        raw_llm_response="{}",
    )
    for conf, vid in confidences:
        meta = {"dimensions": [{"dimension": "Timeline", "overall_confidence": conf, "findings": []}]}
        await write_node(db, project.id, None, "exploration", f"node-{conf}", base_payload, meta, version_id=vid)
    aggregator = KnowledgeAggregator(db)
    matrix = await aggregator.compute_confidence_matrix(project.id)
    assert matrix.matrix[v1.id]["Timeline"] == "RED"
    assert matrix.matrix[v2.id]["Timeline"] == "AMBER"
    assert matrix.matrix[v3.id]["Timeline"] == "GREEN"
    assert matrix.version_order == [v1.id, v2.id, v3.id]


@pytest.mark.asyncio
async def test_knowledge_aggregator_run_for_project_persists_confidence_trend(db) -> None:
    """run_for_project() writes a CONFIDENCE_TREND record to intelligence_layer."""
    project = await create_project(db, "KA Project", [])
    aggregator = KnowledgeAggregator(db)
    record = await aggregator.run_for_project(project.id)
    assert isinstance(record, IntelligenceRow)
    assert record.insight_type == INSIGHT_TYPE_CONFIDENCE_TREND
    assert record.project_id == project.id
    payload_data = json.loads(record.payload_json)
    assert "project_id" in payload_data
    assert "matrix" in payload_data
    assert "version_order" in payload_data



# ─────────────────────────────────────────────────────────────────────────────
# Section 4 — PromptDelta
# ─────────────────────────────────────────────────────────────────────────────

def _all_gates_pass_judge_report() -> JudgeValidationReport:
    return evaluate_reconciliation_report(_good_report())


def _failing_judge_report(*fail_gates: str) -> JudgeValidationReport:
    """Build a JudgeValidationReport that fails the specified gates."""
    report = _good_report()
    if GateNameEnum.APPROVAL_GATE in fail_gates:
        object.__setattr__(report, "ready_for_approval", False)
    if GateNameEnum.DELIVERY_CONFIDENCE in fail_gates:
        object.__setattr__(report, "delivery_confidence_score", 10)
    if GateNameEnum.CONFLICT_SEVERITY_CONTROL in fail_gates:
        object.__setattr__(report, "critical_conflicts", [_conflict("Critical")])
    if GateNameEnum.CONFLICT_COUNT_BOUNDED in fail_gates:
        existing = list(report.critical_conflicts)
        object.__setattr__(report, "critical_conflicts", existing + [_conflict("High")] * 4)
    if GateNameEnum.RECOMMENDATIONS_PRESENT in fail_gates:
        object.__setattr__(report, "actionable_recommendations", [])
    if GateNameEnum.EXECUTIVE_SUMMARY_SUBSTANTIVE in fail_gates:
        object.__setattr__(report, "executive_summary", "X")
    return evaluate_reconciliation_report(report)


@pytest.mark.asyncio
async def test_prompt_delta_generate_no_failures_returns_empty_delta(db) -> None:
    """generate() returns empty delta when all gates pass."""
    delta_svc = PromptDelta(db)
    judge = _all_gates_pass_judge_report()
    result = delta_svc.generate(judge, _blueprint())
    assert isinstance(result, PromptDeltaResult)
    assert result.gate_failures == []
    assert result.delta_json == {}


@pytest.mark.asyncio
async def test_prompt_delta_generate_approval_gate_failure(db) -> None:
    """APPROVAL_GATE failure produces approval_gate_guidance in delta_json."""
    delta_svc = PromptDelta(db)
    judge = _failing_judge_report(GateNameEnum.APPROVAL_GATE)
    result = delta_svc.generate(judge, _blueprint())
    assert GateNameEnum.APPROVAL_GATE in result.gate_failures
    assert "approval_gate_guidance" in result.delta_json
    assert len(result.delta_json["approval_gate_guidance"]) > 0


@pytest.mark.asyncio
async def test_prompt_delta_generate_each_gate_has_distinct_key(db) -> None:
    """Each failed gate maps to a distinct adjustment_key in delta_json."""
    delta_svc = PromptDelta(db)
    for gate in list(GateNameEnum):
        judge = _failing_judge_report(gate)
        result = delta_svc.generate(judge, _blueprint())
        assert gate in result.gate_failures
        assert len(result.delta_json) == 1, (
            f"Gate {gate!r} should produce exactly 1 delta entry, "
            f"got {len(result.delta_json)}: {list(result.delta_json.keys())}"
        )


@pytest.mark.asyncio
async def test_prompt_delta_generate_multiple_failures(db) -> None:
    """Multiple failing gates produce one delta entry each."""
    delta_svc = PromptDelta(db)
    judge = _failing_judge_report(
        GateNameEnum.APPROVAL_GATE,
        GateNameEnum.DELIVERY_CONFIDENCE,
        GateNameEnum.RECOMMENDATIONS_PRESENT,
    )
    result = delta_svc.generate(judge, _blueprint())
    assert len(result.gate_failures) == 3
    assert len(result.delta_json) == 3


@pytest.mark.asyncio
async def test_prompt_delta_generate_all_gates_fail_produces_six_entries(db) -> None:
    """When all 6 gates fail, delta_json contains exactly 6 entries."""
    delta_svc = PromptDelta(db)
    report = ReconciliationReport(
        executive_summary="X",      # EXECUTIVE_SUMMARY fails (len < 50)
        delivery_confidence_score=1,  # DELIVERY_CONFIDENCE fails
        critical_conflicts=[
            _conflict("Critical"),  # CONFLICT_SEVERITY fails
            _conflict("High"),
            _conflict("High"),
            _conflict("High"),
            _conflict("High"),      # CONFLICT_COUNT fails (5 > 3)
        ],
        architectural_risks=[],
        actionable_recommendations=[],  # RECOMMENDATIONS fails
        ready_for_approval=False,   # APPROVAL_GATE fails
    )
    judge = evaluate_reconciliation_report(report)
    result = delta_svc.generate(judge, _blueprint())
    assert len(result.gate_failures) == 6
    assert len(result.delta_json) == 6


@pytest.mark.asyncio
async def test_prompt_delta_records_base_prompt_length(db) -> None:
    """base_prompt_length matches len(blueprint.master_prompt_text)."""
    prompt_text = "A very specific review instruction."
    blueprint = _blueprint(prompt_text)
    delta_svc = PromptDelta(db)
    judge = _all_gates_pass_judge_report()
    result = delta_svc.generate(judge, blueprint)
    assert result.base_prompt_length == len(prompt_text)


@pytest.mark.asyncio
async def test_prompt_delta_records_blueprint_id(db) -> None:
    """applied_to_blueprint_id matches blueprint.id."""
    blueprint = _blueprint()
    delta_svc = PromptDelta(db)
    judge = _all_gates_pass_judge_report()
    result = delta_svc.generate(judge, blueprint)
    assert result.applied_to_blueprint_id == blueprint.id


@pytest.mark.asyncio
async def test_prompt_delta_run_persists_prompt_delta(db) -> None:
    """run() writes a PROMPT_DELTA record to intelligence_layer."""
    project = await create_project(db, "Delta Project", [])
    delta_svc = PromptDelta(db)
    judge = _failing_judge_report(GateNameEnum.APPROVAL_GATE)
    record = await delta_svc.run(judge, _blueprint(), project_id=project.id)
    assert isinstance(record, IntelligenceRow)
    assert record.insight_type == INSIGHT_TYPE_PROMPT_DELTA
    assert record.project_id == project.id
    payload_data = json.loads(record.payload_json)
    assert "gate_failures" in payload_data
    assert "delta_json" in payload_data
    assert GateNameEnum.APPROVAL_GATE in payload_data["gate_failures"]


@pytest.mark.asyncio
async def test_prompt_delta_run_global_has_null_project_id(db) -> None:
    """run() with project_id=None persists a global PROMPT_DELTA record."""
    delta_svc = PromptDelta(db)
    judge = _all_gates_pass_judge_report()
    record = await delta_svc.run(judge, _blueprint(), project_id=None)
    assert record.project_id is None
    assert record.insight_type == INSIGHT_TYPE_PROMPT_DELTA



# ─────────────────────────────────────────────────────────────────────────────
# Section 5 — DB / Repository layer
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schema_version_is_current(db) -> None:
    """SCHEMA_VERSION constant must match what is stored in the DB."""
    assert SCHEMA_VERSION == 5
    cursor = await db.execute("SELECT version FROM schema_version LIMIT 1")
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == SCHEMA_VERSION


@pytest.mark.asyncio
async def test_intelligence_layer_table_exists(db) -> None:
    """intelligence_layer table is created by init_database()."""
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='intelligence_layer'"
    )
    row = await cursor.fetchone()
    assert row is not None, "intelligence_layer table not found in schema"


@pytest.mark.asyncio
async def test_intelligence_layer_has_correct_columns(db) -> None:
    """intelligence_layer has all required columns."""
    cursor = await db.execute("PRAGMA table_info(intelligence_layer)")
    rows = await cursor.fetchall()
    columns = {r[1] for r in rows}
    assert {"id", "project_id", "insight_type", "source_node_id", "payload_json", "created_at"}.issubset(columns)


@pytest.mark.asyncio
async def test_write_intelligence_record_insert_and_round_trip(db) -> None:
    """write_intelligence_record inserts a row and returns a matching IntelligenceRow."""
    record = await write_intelligence_record(
        db,
        insight_type="CITATION_TREND",
        payload={"trends": []},
    )
    assert isinstance(record, IntelligenceRow)
    assert record.insight_type == "CITATION_TREND"
    assert record.project_id is None
    assert record.source_node_id is None
    payload = json.loads(record.payload_json)
    assert payload == {"trends": []}


@pytest.mark.asyncio
async def test_write_intelligence_record_project_scoped(db) -> None:
    """write_intelligence_record with project_id stores the FK correctly."""
    project = await create_project(db, "Scoped Project", [])
    record = await write_intelligence_record(
        db,
        insight_type="CONFIDENCE_TREND",
        payload={"matrix": {}},
        project_id=project.id,
    )
    assert record.project_id == project.id


@pytest.mark.asyncio
async def test_write_intelligence_record_with_source_node_id(db) -> None:
    """write_intelligence_record with source_node_id stores the FK correctly."""
    project = await create_project(db, "Node Source Project", [])
    payload_model = ReviewNodePayload(
        dimension=ReviewDimensionEnum.RISK,
        findings=[],
        overall_confidence=ConfidenceEnum.GREEN,
        raw_llm_response="{}",
    )
    node = await write_node(
        db, project.id, None, "exploration", "Source Node", payload_model, {}
    )
    record = await write_intelligence_record(
        db,
        insight_type="CITATION_TREND",
        payload={"trends": []},
        project_id=project.id,
        source_node_id=node.id,
    )
    assert record.source_node_id == node.id


@pytest.mark.asyncio
async def test_get_intelligence_for_project_filters_correctly(db) -> None:
    """get_intelligence_for_project returns only records for the given project."""
    proj_a = await create_project(db, "Project A", [])
    proj_b = await create_project(db, "Project B", [])
    await write_intelligence_record(db, "CITATION_TREND", {}, project_id=proj_a.id)
    await write_intelligence_record(db, "CITATION_TREND", {}, project_id=proj_a.id)
    await write_intelligence_record(db, "CITATION_TREND", {}, project_id=proj_b.id)
    results_a = await get_intelligence_for_project(db, proj_a.id)
    assert len(results_a) == 2
    assert all(r.project_id == proj_a.id for r in results_a)


@pytest.mark.asyncio
async def test_get_intelligence_for_project_returns_empty_for_unknown(db) -> None:
    """get_intelligence_for_project returns [] for an unknown project_id."""
    results = await get_intelligence_for_project(db, "unknown-project-id")
    assert results == []


@pytest.mark.asyncio
async def test_get_intelligence_global_returns_only_null_project(db) -> None:
    """get_intelligence_global returns only records where project_id IS NULL."""
    project = await create_project(db, "Some Project", [])
    await write_intelligence_record(db, "PROMPT_DELTA", {"a": 1})            # global
    await write_intelligence_record(db, "PROMPT_DELTA", {"b": 2})            # global
    await write_intelligence_record(db, "PROMPT_DELTA", {"c": 3}, project_id=project.id)  # scoped
    globals_ = await get_intelligence_global(db)
    assert len(globals_) == 2
    assert all(r.project_id is None for r in globals_)


@pytest.mark.asyncio
async def test_get_intelligence_by_type_unscoped(db) -> None:
    """get_intelligence_by_type without project_id returns all records of that type."""
    proj = await create_project(db, "P", [])
    await write_intelligence_record(db, "CITATION_TREND", {})
    await write_intelligence_record(db, "CITATION_TREND", {}, project_id=proj.id)
    await write_intelligence_record(db, "CONFIDENCE_TREND", {}, project_id=proj.id)
    results = await get_intelligence_by_type(db, "CITATION_TREND")
    assert len(results) == 2
    assert all(r.insight_type == "CITATION_TREND" for r in results)


@pytest.mark.asyncio
async def test_get_intelligence_by_type_scoped_to_project(db) -> None:
    """get_intelligence_by_type with project_id filters by both type and project."""
    proj_a = await create_project(db, "PA", [])
    proj_b = await create_project(db, "PB", [])
    await write_intelligence_record(db, "PROMPT_DELTA", {}, project_id=proj_a.id)
    await write_intelligence_record(db, "PROMPT_DELTA", {}, project_id=proj_b.id)
    await write_intelligence_record(db, "CITATION_TREND", {}, project_id=proj_a.id)
    results = await get_intelligence_by_type(db, "PROMPT_DELTA", project_id=proj_a.id)
    assert len(results) == 1
    assert results[0].project_id == proj_a.id
    assert results[0].insight_type == "PROMPT_DELTA"


@pytest.mark.asyncio
async def test_init_database_idempotent_with_new_schema(tmp_path) -> None:
    """init_database() on an existing DB file migrates cleanly to current SCHEMA_VERSION."""
    db_path = str(tmp_path / "migrate.db")
    conn1 = await init_database(db_path)
    v1_cursor = await conn1.execute("SELECT version FROM schema_version LIMIT 1")
    v1_row = await v1_cursor.fetchone()
    assert v1_row[0] == SCHEMA_VERSION
    await conn1.close()
    # Re-open: must not raise, must stay at current version.
    conn2 = await init_database(db_path)
    v2_cursor = await conn2.execute("SELECT version FROM schema_version LIMIT 1")
    v2_row = await v2_cursor.fetchone()
    assert v2_row[0] == SCHEMA_VERSION
    await conn2.close()
