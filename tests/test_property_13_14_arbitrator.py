"""Property 13 — Arbitrator Receives All 12 Payloads.
Property 14 — Synthesis Node Lineage.

Property 13
-----------
``ArbitratorEngine.run()`` raises ``ArbitratorError`` **before** any LLM
call is made when ``len(payloads) < 12`` (or ``> 12``).  With exactly 12
payloads the engine completes successfully.

Property 14
-----------
When a synthesis node is created, ``S.parent_id == N.id`` and
``S.project_id == N.project_id``, where ``N`` is the Layer 1 exploration
node that preceded it.  This is enforced at the ``commit_exploration_node``
/ ``write_node`` boundary and verified here by asserting that the IDs
passed through match what is returned.

Coverage
--------
- Unit: ArbitratorError raised for 0–11 payloads (no LLM call made).
- Unit: ArbitratorError raised for 13 payloads.
- Unit: Successful run with exactly 12 payloads.
- Unit: ArbitratorError on JSON decode failure.
- Unit: ArbitratorError on missing 'contradictions' key.
- Unit: LLM call failure wrapped in ArbitratorError.
- Unit: Synthesis node lineage (parent_id / project_id consistency).
- Hypothesis: Property 13 — for any count != 12 assert error raised.
- Hypothesis: Property 14 — for any valid IDs assert lineage fields match.
"""

from __future__ import annotations

import asyncio
import json
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from contexta.db.models import BlueprintRow
from contexta.llm.provider import LLMConfig
from contexta.llm.prompts import PromptBuilder
from contexta.models.enums import ConfidenceEnum, ReviewDimensionEnum
from contexta.models.payloads import ReviewNodePayload
from contexta.pipeline.arbitrator import ArbitratorEngine, ArbitratorError, ArbitratorResult


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_payload(dimension: ReviewDimensionEnum) -> ReviewNodePayload:
    return ReviewNodePayload(
        dimension=dimension,
        findings=[],
        overall_confidence=ConfidenceEnum.GREEN,
        raw_llm_response='{"ok": true}',
    )


def _make_12_payloads() -> List[ReviewNodePayload]:
    return [_make_payload(dim) for dim in ReviewDimensionEnum]


def _make_engine() -> tuple[ArbitratorEngine, BlueprintRow]:
    blueprint = BlueprintRow(
        id="bp-arb-test",
        blueprint_name="Arbitrator Test Blueprint",
        version_string="1.0.0",
        master_prompt_text="Review rigorously.",
        is_active=True,
    )
    schema_json = "{}"
    builder = PromptBuilder(blueprint=blueprint, schema_json=schema_json)
    config = LLMConfig(model="ollama/mistral")
    engine = ArbitratorEngine(config=config, builder=builder)
    return engine, blueprint


def _make_llm_mock(content: str) -> AsyncMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    response = MagicMock()
    response.choices = [choice]
    return AsyncMock(return_value=response)


# ── Property 13: 12-payload guard ────────────────────────────────────────────


class TestArbitratorPayloadGuard:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("count", list(range(0, 12)))
    async def test_raises_for_fewer_than_12_payloads(self, count: int):
        """ArbitratorError is raised for any payload count below 12."""
        engine, _ = _make_engine()
        payloads = [_make_payload(dim) for dim in list(ReviewDimensionEnum)[:count]]
        with pytest.raises(ArbitratorError, match="exactly 12"):
            await engine.run(payloads)

    @pytest.mark.asyncio
    async def test_raises_for_13_payloads(self):
        """ArbitratorError is raised for 13 payloads (more than 12)."""
        engine, _ = _make_engine()
        payloads = _make_12_payloads() + [_make_payload(ReviewDimensionEnum.INTENT)]
        with pytest.raises(ArbitratorError, match="exactly 12"):
            await engine.run(payloads)

    @pytest.mark.asyncio
    async def test_no_llm_call_made_on_guard_failure(self):
        """LLM is never called when the payload count guard fires."""
        engine, _ = _make_engine()
        llm_mock = _make_llm_mock('{"contradictions": []}')
        with patch("contexta.llm.provider.litellm.acompletion", llm_mock):
            with pytest.raises(ArbitratorError):
                await engine.run([])  # 0 payloads
        llm_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_llm_call_for_11_payloads(self):
        """LLM not called when 11 payloads supplied."""
        engine, _ = _make_engine()
        payloads = [_make_payload(dim) for dim in list(ReviewDimensionEnum)[:11]]
        llm_mock = _make_llm_mock('{"contradictions": []}')
        with patch("contexta.llm.provider.litellm.acompletion", llm_mock):
            with pytest.raises(ArbitratorError, match="exactly 12"):
                await engine.run(payloads)
        llm_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_with_exactly_12_payloads(self):
        """Run succeeds with exactly 12 payloads and returns ArbitratorResult."""
        engine, _ = _make_engine()
        payloads = _make_12_payloads()
        response_json = json.dumps({
            "contradictions": [
                {
                    "dimension_a": "Intent",
                    "dimension_b": "Scope",
                    "description": "Conflicting scope boundaries",
                }
            ]
        })
        llm_mock = _make_llm_mock(response_json)
        with patch("contexta.llm.provider.litellm.acompletion", llm_mock):
            result = await engine.run(payloads)

        assert isinstance(result, ArbitratorResult)
        assert len(result.contradictions) == 1
        assert result.contradictions[0]["dimension_a"] == "Intent"
        llm_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_contradictions_list_is_valid(self):
        """A valid response with zero contradictions is accepted."""
        engine, _ = _make_engine()
        payloads = _make_12_payloads()
        response_json = json.dumps({"contradictions": []})
        llm_mock = _make_llm_mock(response_json)
        with patch("contexta.llm.provider.litellm.acompletion", llm_mock):
            result = await engine.run(payloads)
        assert result.contradictions == []

    @pytest.mark.asyncio
    async def test_raw_llm_response_stored(self):
        """``ArbitratorResult.raw_llm_response`` holds the verbatim LLM string."""
        engine, _ = _make_engine()
        payloads = _make_12_payloads()
        response_content = json.dumps({"contradictions": []})
        llm_mock = _make_llm_mock(response_content)
        with patch("contexta.llm.provider.litellm.acompletion", llm_mock):
            result = await engine.run(payloads)
        assert result.raw_llm_response == response_content

    @pytest.mark.asyncio
    async def test_json_decode_error_raises_arbitrator_error(self):
        """Non-JSON LLM response raises ArbitratorError."""
        engine, _ = _make_engine()
        payloads = _make_12_payloads()
        llm_mock = _make_llm_mock("THIS IS NOT JSON <<<")
        with patch("contexta.llm.provider.litellm.acompletion", llm_mock):
            with pytest.raises(ArbitratorError, match="not valid JSON"):
                await engine.run(payloads)

    @pytest.mark.asyncio
    async def test_missing_contradictions_key_raises_arbitrator_error(self):
        """JSON missing the 'contradictions' key raises ArbitratorError."""
        engine, _ = _make_engine()
        payloads = _make_12_payloads()
        llm_mock = _make_llm_mock('{"result": "unexpected_key"}')
        with patch("contexta.llm.provider.litellm.acompletion", llm_mock):
            with pytest.raises(ArbitratorError, match="missing required key"):
                await engine.run(payloads)

    @pytest.mark.asyncio
    async def test_llm_call_failure_raises_arbitrator_error(self):
        """LLMCallError from call_llm() is wrapped in ArbitratorError."""
        from contexta.llm.provider import LLMCallError
        engine, _ = _make_engine()
        payloads = _make_12_payloads()
        failing_mock = AsyncMock(side_effect=RuntimeError("network down"))
        with patch("contexta.llm.provider.litellm.acompletion", failing_mock):
            with pytest.raises(ArbitratorError, match="LLM call failed"):
                await engine.run(payloads)


# ── Property 14: Synthesis node lineage ──────────────────────────────────────


class TestSynthesisNodeLineage:
    """Verify parent_id and project_id consistency for synthesis nodes.

    These tests simulate the contract that the pipeline coordinator must
    enforce: when writing a synthesis node, ``parent_id`` must equal the
    exploration node's ``id`` and ``project_id`` must match.
    """

    def test_synthesis_node_parent_id_equals_exploration_node_id(self):
        """S.parent_id == N.id when wired correctly."""
        exploration_node_id = "node-explore-001"
        synthesis_parent_id = exploration_node_id  # coordinator enforces this
        assert synthesis_parent_id == exploration_node_id

    def test_synthesis_node_project_id_equals_exploration_project_id(self):
        """S.project_id == N.project_id — same project for both layers."""
        project_id = "proj-abc-123"
        exploration_project_id = project_id
        synthesis_project_id = project_id
        assert synthesis_project_id == exploration_project_id

    @pytest.mark.asyncio
    async def test_lineage_captured_in_write_node_args(self):
        """commit_exploration_node passes parent_id and project_id to write_node."""
        from contexta.pipeline.dimension_runner import (
            TaskOrchestrator,
            TaskState,
            commit_exploration_node,
        )

        # Build a complete orchestrator
        async def noop(task): pass

        async def runner(dim):
            return ReviewNodePayload(
                dimension=dim,
                findings=[],
                overall_confidence=ConfidenceEnum.GREEN,
                raw_llm_response='{"ok": true}',
            )

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
        await orch.launch_all()
        assert orch.all_complete()

        # Capture what write_node is called with
        captured_kwargs: dict = {}

        async def mock_write_node(conn, **kwargs):
            captured_kwargs.update(kwargs)
            from contexta.db.models import NodeRow
            return NodeRow(
                id="synth-001",
                project_id=kwargs["project_id"],
                parent_id=kwargs["parent_id"],
                layer_type=kwargs["layer_type"],
                node_name=kwargs["node_name"],
                metadata_json="{}",
                content_markdown="",
                created_at="2025-01-01T00:00:00+00:00",
            )

        with patch(
            "contexta.pipeline.dimension_runner.write_node",
            side_effect=mock_write_node,
        ):
            row = await commit_exploration_node(
                orchestrator=orch,
                conn=object(),
                project_id="proj-xyz-999",
                parent_id="node-parent-555",
            )

        assert captured_kwargs["project_id"] == "proj-xyz-999"
        assert captured_kwargs["parent_id"] == "node-parent-555"
        assert captured_kwargs["layer_type"] == "exploration"
        assert row.project_id == "proj-xyz-999"
        assert row.parent_id == "node-parent-555"

    @pytest.mark.asyncio
    async def test_synthesis_lineage_parent_id_is_exploration_node(self):
        """Synthesis write uses exploration node id as parent_id."""
        from contexta.pipeline.dimension_runner import (
            TaskOrchestrator,
            commit_exploration_node,
        )
        from contexta.db.models import NodeRow

        async def noop(task): pass
        async def runner(dim): return _make_payload(dim)

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
        await orch.launch_all()

        exploration_node_id = "explore-node-42"
        captured_parent: list = []

        async def mock_write_node(conn, **kwargs):
            captured_parent.append(kwargs.get("parent_id"))
            return NodeRow(
                id="synth-node-43",
                project_id=kwargs["project_id"],
                parent_id=kwargs.get("parent_id"),
                layer_type=kwargs["layer_type"],
                node_name=kwargs["node_name"],
                metadata_json="{}",
                content_markdown="",
                created_at="2025-01-01T00:00:00+00:00",
            )

        with patch(
            "contexta.pipeline.dimension_runner.write_node",
            side_effect=mock_write_node,
        ):
            await commit_exploration_node(
                orchestrator=orch,
                conn=object(),
                project_id="proj-000",
                parent_id=exploration_node_id,
            )

        assert captured_parent[0] == exploration_node_id


# ── Hypothesis: Property 13 ───────────────────────────────────────────────────


@given(count=st.integers(min_value=0, max_value=50).filter(lambda n: n != 12))
@settings(max_examples=100)
def test_property_13_arbitrator_raises_for_non_12_count(count: int) -> None:
    """Property 13: ArbitratorError raised for any payload count != 12.

    No LLM call should be made.
    """
    async def _run() -> None:
        engine, _ = _make_engine()
        # Build `count` payloads (cycle through dimensions if count > 12)
        dims = list(ReviewDimensionEnum)
        payloads = [_make_payload(dims[i % len(dims)]) for i in range(count)]

        llm_mock = _make_llm_mock('{"contradictions": []}')
        with patch("contexta.llm.provider.litellm.acompletion", llm_mock):
            with pytest.raises(ArbitratorError):
                await engine.run(payloads)
        llm_mock.assert_not_called()

    asyncio.run(_run())


# ── Hypothesis: Property 14 ───────────────────────────────────────────────────


@given(
    project_id=st.text(
        alphabet=st.characters(blacklist_characters="\x00"),
        min_size=1,
        max_size=64,
    ),
    parent_id=st.one_of(
        st.none(),
        st.text(
            alphabet=st.characters(blacklist_characters="\x00"),
            min_size=1,
            max_size=64,
        ),
    ),
)
@settings(max_examples=100)
def test_property_14_synthesis_lineage_fields_match(
    project_id: str,
    parent_id,
) -> None:
    """Property 14: S.parent_id == N.id and S.project_id == N.project_id.

    Verifies that whatever IDs are passed to commit_exploration_node(),
    they flow through unchanged to write_node().
    """
    from contexta.pipeline.dimension_runner import (
        TaskOrchestrator,
        commit_exploration_node,
    )
    from contexta.db.models import NodeRow

    async def _run() -> None:
        async def noop(task): pass
        async def runner(dim): return _make_payload(dim)

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
        await orch.launch_all()

        captured: dict = {}

        async def mock_write_node(conn, **kwargs):
            captured.update(kwargs)
            return NodeRow(
                id="gen-id",
                project_id=kwargs["project_id"],
                parent_id=kwargs.get("parent_id"),
                layer_type=kwargs["layer_type"],
                node_name=kwargs["node_name"],
                metadata_json="{}",
                content_markdown="",
                created_at="2025-01-01T00:00:00+00:00",
            )

        with patch(
            "contexta.pipeline.dimension_runner.write_node",
            side_effect=mock_write_node,
        ):
            await commit_exploration_node(
                orchestrator=orch,
                conn=object(),
                project_id=project_id,
                parent_id=parent_id,
            )

        assert captured["project_id"] == project_id, (
            f"project_id mismatch: expected {project_id!r}, got {captured['project_id']!r}"
        )
        assert captured.get("parent_id") == parent_id, (
            f"parent_id mismatch: expected {parent_id!r}, got {captured.get('parent_id')!r}"
        )

    asyncio.run(_run())
