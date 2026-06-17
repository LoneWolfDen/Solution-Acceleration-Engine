"""Tests for LayerTwoArbitrator — Layer 2 synthesis pipeline.

Coverage
--------
1. Valid synthesis produces a well-formed ``ReconciliationReport``.
2. Array-wrapped LLM response is correctly unwrapped by
   ``_normalise_json_content`` before Pydantic validation.
3. Empty findings list synthesises without error.
4. Invalid LLM schema raises ``LayerTwoArbitratorError`` with the substring
   ``'validation failed'``.
5. Non-JSON LLM response raises ``LayerTwoArbitratorError``.
6. ``_build_synthesis_prompt`` embeds finding summaries in the user prompt.
7. DB round-trip: ``write_synthesis_node`` → ``get_synthesis_report``.

All LLM I/O is mocked; no real network calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from contexta.config import ContextaConfig
from contexta.llm.models import ReconciliationReport
from contexta.models.enums import ReviewDimensionEnum
from contexta.models.payloads import ReviewNodePayload
from contexta.pipeline.arbitrator import LayerTwoArbitrator, LayerTwoArbitratorError
from tests.fixtures import (
    make_dimension_llm_response,
    make_reconciliation_report_response,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_llm_response(content: str) -> MagicMock:
    """Build a minimal ``litellm.acompletion`` return value with *content*."""
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    response = MagicMock()
    response.choices = [choice]
    return response


def _all_findings() -> list:
    """Return one ``IssueFinding`` per dimension using the shared mock factory."""
    findings = []
    for dim in ReviewDimensionEnum:
        payload = ReviewNodePayload.model_validate_json(make_dimension_llm_response(dim))
        findings.extend(payload.findings)
    return findings


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_arbitrator_synthesis_produces_valid_report(
    mock_config: ContextaConfig,
) -> None:
    """``synthesize()`` returns a validated ``ReconciliationReport``."""
    findings = _all_findings()
    mock_resp = _mock_llm_response(make_reconciliation_report_response())

    with patch(
        "contexta.llm.provider.litellm.acompletion",
        AsyncMock(return_value=mock_resp),
    ):
        result = await LayerTwoArbitrator(mock_config).synthesize(findings)

    assert isinstance(result, ReconciliationReport)
    assert 1 <= result.delivery_confidence_score <= 100
    assert isinstance(result.executive_summary, str)
    assert len(result.executive_summary) > 0
    assert isinstance(result.critical_conflicts, list)
    assert isinstance(result.architectural_risks, list)
    assert isinstance(result.actionable_recommendations, list)
    assert isinstance(result.ready_for_approval, bool)



@pytest.mark.asyncio
async def test_arbitrator_handles_array_wrapped_response(
    mock_config: ContextaConfig,
) -> None:
    """Array-unwrapping in ``_normalise_json_content`` handles ``[{...}]`` responses.

    Groq (and some local models) occasionally wrap a JSON object in a list.
    ``call_llm`` silently unwraps it before returning to the caller — this test
    confirms the full path through ``LayerTwoArbitrator.synthesize()`` succeeds
    and that the extracted values are correct.
    """
    findings = _all_findings()
    # Simulate the Groq array-wrap bug: valid report wrapped in a JSON array.
    array_wrapped = "[" + make_reconciliation_report_response() + "]"
    mock_resp = _mock_llm_response(array_wrapped)

    with patch(
        "contexta.llm.provider.litellm.acompletion",
        AsyncMock(return_value=mock_resp),
    ):
        result = await LayerTwoArbitrator(mock_config).synthesize(findings)

    assert isinstance(result, ReconciliationReport)
    # Confirm the specific value survives the unwrap — not just any valid object.
    assert result.delivery_confidence_score == 72
    assert result.ready_for_approval is False
    assert result.critical_conflicts[0].dimensions_involved == ["Timeline", "Resource"]


@pytest.mark.asyncio
async def test_arbitrator_synthesizes_with_empty_findings(
    mock_config: ContextaConfig,
) -> None:
    """``synthesize([])`` completes without error and returns a valid report."""
    mock_resp = _mock_llm_response(make_reconciliation_report_response())

    with patch(
        "contexta.llm.provider.litellm.acompletion",
        AsyncMock(return_value=mock_resp),
    ):
        result = await LayerTwoArbitrator(mock_config).synthesize([])

    assert isinstance(result, ReconciliationReport)


@pytest.mark.asyncio
async def test_arbitrator_raises_on_schema_mismatch(
    mock_config: ContextaConfig,
) -> None:
    """``LayerTwoArbitratorError`` is raised when LLM returns wrong JSON schema.

    The error message must contain 'validation failed' so test assertions in
    downstream consumers can match on it precisely.
    """
    findings = _all_findings()
    # Valid JSON but missing all required ReconciliationReport fields.
    mock_resp = _mock_llm_response('{"contradictions": [], "score": 50}')

    with patch(
        "contexta.llm.provider.litellm.acompletion",
        AsyncMock(return_value=mock_resp),
    ):
        with pytest.raises(LayerTwoArbitratorError, match="validation failed"):
            await LayerTwoArbitrator(mock_config).synthesize(findings)


@pytest.mark.asyncio
async def test_arbitrator_raises_on_non_json_response(
    mock_config: ContextaConfig,
) -> None:
    """``LayerTwoArbitratorError`` is raised when the LLM returns non-JSON text."""
    findings = _all_findings()
    mock_resp = _mock_llm_response("I cannot produce a JSON response right now.")

    with patch(
        "contexta.llm.provider.litellm.acompletion",
        AsyncMock(return_value=mock_resp),
    ):
        with pytest.raises(LayerTwoArbitratorError):
            await LayerTwoArbitrator(mock_config).synthesize(findings)



def test_build_synthesis_prompt_embeds_findings(mock_config: ContextaConfig) -> None:
    """``_build_synthesis_prompt`` includes each finding summary in the user prompt."""
    findings = _all_findings()
    arbitrator = LayerTwoArbitrator(mock_config)
    _system, user = arbitrator._build_synthesis_prompt(findings)

    # Every finding summary produced by make_dimension_llm_response follows
    # the pattern "Test finding for <Dimension>" — assert at least one is present.
    for dim in ReviewDimensionEnum:
        assert f"Test finding for {dim.value}" in user, (
            f"Finding summary for {dim.value!r} missing from synthesis prompt"
        )

    assert "LAYER 1 FINDINGS" in user


def test_build_synthesis_prompt_empty_findings(mock_config: ContextaConfig) -> None:
    """``_build_synthesis_prompt`` with no findings returns a well-formed prompt pair."""
    arbitrator = LayerTwoArbitrator(mock_config)
    system, user = arbitrator._build_synthesis_prompt([])

    assert "ReconciliationReport" in system or "executive_summary" in system
    assert "No findings" in user


@pytest.mark.asyncio
async def test_db_round_trip_write_and_retrieve_synthesis_node(
    mock_config: ContextaConfig,
) -> None:
    """``write_synthesis_node`` persists and ``get_synthesis_report`` retrieves correctly."""
    from contexta.db.repositories import (
        create_project,
        get_synthesis_report,
        write_synthesis_node,
    )
    from contexta.db.schema import init_database
    from contexta.llm.models import DimensionConflict

    report = ReconciliationReport(
        executive_summary="Feasible with caveats.",
        delivery_confidence_score=72,
        critical_conflicts=[
            DimensionConflict(
                dimensions_involved=["Timeline", "Resource"],
                description="Timeline too aggressive.",
                severity="High",
                source_references=["SOW §3"],
                suggested_mitigation="Extend by 4 weeks.",
            )
        ],
        architectural_risks=["No DR plan documented."],
        actionable_recommendations=["Confirm headcount.", "Add NFR for DR."],
        ready_for_approval=False,
    )

    conn = await init_database(":memory:")
    try:
        project = await create_project(conn, "Test Project", ["#ArbitratorTest"])
        node = await write_synthesis_node(
            conn, project.id, None, "Layer 2 Synthesis", report
        )

        assert node.layer_type == "synthesis"
        assert node.project_id == project.id

        retrieved = await get_synthesis_report(conn, node.id)
        assert retrieved is not None
        assert isinstance(retrieved, ReconciliationReport)
        assert retrieved.delivery_confidence_score == 72
        assert retrieved.ready_for_approval is False
        assert len(retrieved.critical_conflicts) == 1
        assert retrieved.critical_conflicts[0].severity == "High"
        assert "Extend by 4 weeks." in retrieved.critical_conflicts[0].suggested_mitigation

        # Missing node → None
        assert await get_synthesis_report(conn, "no-such-id") is None
    finally:
        await conn.close()
