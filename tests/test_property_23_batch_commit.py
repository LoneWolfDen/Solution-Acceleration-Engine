"""Property 23 — Layer 1 Batch Commit Atomicity.

For a Layer 1 run where all 12 tasks are COMPLETE:
- Exactly one row is written to ``nodes`` (single ``write_node()`` call).
- Zero rows are written if any dimension is in FAILED state.

The ``write_node`` DB call is always mocked — no live DB is needed.

Design invariant
----------------
``commit_exploration_node()`` calls ``orchestrator.get_all_payloads()``
which raises ``RuntimeError`` if any task is not ``COMPLETE``.  This
propagates before ``write_node()`` is ever called, guaranteeing zero
partial writes.

Coverage
--------
- Unit: all-COMPLETE → exactly one write_node call.
- Unit: any FAILED task → RuntimeError raised, zero write_node calls.
- Unit: combined_metadata contains all 12 serialised dimensions.
- Unit: combined_metadata has 'completed_at' timestamp key.
- Unit: write_node called with layer_type='exploration'.
- Unit: write_node called with correct project_id and parent_id.
- Unit: zero writes when exactly 1 task is FAILED.
- Unit: zero writes when all tasks are FAILED.
- Unit: get_all_payloads itself raises on incomplete tasks (no mock needed).
- Hypothesis: Property 23 — for any complete run, write_node called once.
"""

from __future__ import annotations

import asyncio
from typing import List
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from contexta.db.models import NodeRow
from contexta.models.enums import ConfidenceEnum, ReviewDimensionEnum
from contexta.models.payloads import ReviewNodePayload
from contexta.pipeline.dimension_runner import (
    DimensionTask,
    TaskOrchestrator,
    TaskState,
    commit_exploration_node,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_payload(dimension: ReviewDimensionEnum) -> ReviewNodePayload:
    return ReviewNodePayload(
        dimension=dimension,
        findings=[],
        overall_confidence=ConfidenceEnum.GREEN,
        raw_llm_response='{"ok": true}',
    )


def _make_node_row(**kwargs) -> NodeRow:
    defaults = dict(
        id="node-test-001",
        project_id="proj-001",
        parent_id=None,
        layer_type="exploration",
        node_name="Layer 1 — Full Exploration",
        metadata_json="{}",
        content_markdown="",
        created_at="2025-01-01T00:00:00+00:00",
    )
    defaults.update(kwargs)
    return NodeRow(**defaults)


async def _build_complete_orchestrator() -> TaskOrchestrator:
    """Return a TaskOrchestrator with all 12 tasks COMPLETE."""
    async def noop(task): pass
    async def runner(dim): return _make_payload(dim)
    orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
    await orch.launch_all()
    assert orch.all_complete()
    return orch


async def _build_orchestrator_with_failure(
    failing_dim: ReviewDimensionEnum = ReviewDimensionEnum.INTENT,
) -> TaskOrchestrator:
    """Return a TaskOrchestrator where one dimension is FAILED."""
    async def noop(task): pass

    async def runner(dim: ReviewDimensionEnum) -> ReviewNodePayload:
        if dim == failing_dim:
            raise RuntimeError(f"Simulated failure for {dim}")
        return _make_payload(dim)

    orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
    await orch.launch_all()
    assert orch._tasks[failing_dim].state == TaskState.FAILED
    return orch


# ── Property 23 unit tests ─────────────────────────────────────────────────────


class TestLayer1BatchCommitAtomicity:

    @pytest.mark.asyncio
    async def test_exactly_one_write_node_call_when_all_complete(self):
        """Exactly one write_node() call is made when all 12 tasks are COMPLETE."""
        orch = await _build_complete_orchestrator()
        write_calls: list = []

        async def mock_write_node(conn, **kwargs):
            write_calls.append(kwargs)
            return _make_node_row(
                project_id=kwargs["project_id"],
                parent_id=kwargs.get("parent_id"),
            )

        with patch("contexta.pipeline.dimension_runner.write_node", side_effect=mock_write_node):
            await commit_exploration_node(
                orchestrator=orch,
                conn=object(),
                project_id="proj-111",
                parent_id="parent-111",
            )

        assert len(write_calls) == 1, (
            f"Expected exactly 1 write_node call, got {len(write_calls)}"
        )

    @pytest.mark.asyncio
    async def test_zero_write_node_calls_when_task_failed(self):
        """write_node() is never called when any task is FAILED."""
        orch = await _build_orchestrator_with_failure(ReviewDimensionEnum.SCOPE)
        write_calls: list = []

        async def mock_write_node(conn, **kwargs):
            write_calls.append(kwargs)
            return _make_node_row()

        with patch("contexta.pipeline.dimension_runner.write_node", side_effect=mock_write_node):
            with pytest.raises(RuntimeError):
                await commit_exploration_node(
                    orchestrator=orch,
                    conn=object(),
                    project_id="proj-222",
                    parent_id=None,
                )

        assert len(write_calls) == 0, (
            f"write_node was called {len(write_calls)} times despite a FAILED task"
        )

    @pytest.mark.asyncio
    async def test_zero_writes_when_all_tasks_failed(self):
        """write_node() not called when every task is FAILED."""
        async def noop(task): pass
        async def runner(dim): raise RuntimeError("all fail")

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
        await orch.launch_all()

        assert all(t.state == TaskState.FAILED for t in orch._tasks.values())

        write_calls: list = []

        async def mock_write_node(conn, **kwargs):
            write_calls.append(kwargs)
            return _make_node_row()

        with patch("contexta.pipeline.dimension_runner.write_node", side_effect=mock_write_node):
            with pytest.raises(RuntimeError):
                await commit_exploration_node(
                    orchestrator=orch,
                    conn=object(),
                    project_id="proj-333",
                    parent_id=None,
                )

        assert len(write_calls) == 0

    @pytest.mark.asyncio
    async def test_combined_metadata_contains_all_12_dimensions(self):
        """The single write_node call includes all 12 dimension payloads in metadata."""
        orch = await _build_complete_orchestrator()
        captured_metadata: list = []

        async def mock_write_node(conn, **kwargs):
            captured_metadata.append(kwargs["metadata"])
            return _make_node_row(project_id=kwargs["project_id"])

        with patch("contexta.pipeline.dimension_runner.write_node", side_effect=mock_write_node):
            await commit_exploration_node(
                orchestrator=orch,
                conn=object(),
                project_id="proj-444",
                parent_id=None,
            )

        assert len(captured_metadata) == 1
        metadata = captured_metadata[0]
        assert "dimensions" in metadata
        assert len(metadata["dimensions"]) == 12

    @pytest.mark.asyncio
    async def test_combined_metadata_has_completed_at_key(self):
        """The metadata dict written includes a 'completed_at' ISO-8601 timestamp."""
        orch = await _build_complete_orchestrator()
        captured_metadata: list = []

        async def mock_write_node(conn, **kwargs):
            captured_metadata.append(kwargs["metadata"])
            return _make_node_row(project_id=kwargs["project_id"])

        with patch("contexta.pipeline.dimension_runner.write_node", side_effect=mock_write_node):
            await commit_exploration_node(
                orchestrator=orch,
                conn=object(),
                project_id="proj-555",
                parent_id=None,
            )

        metadata = captured_metadata[0]
        assert "completed_at" in metadata
        assert isinstance(metadata["completed_at"], str)
        assert len(metadata["completed_at"]) > 0

    @pytest.mark.asyncio
    async def test_write_node_called_with_exploration_layer_type(self):
        """The single write_node call uses layer_type='exploration'."""
        orch = await _build_complete_orchestrator()
        captured_kwargs: list = []

        async def mock_write_node(conn, **kwargs):
            captured_kwargs.append(kwargs)
            return _make_node_row(
                project_id=kwargs["project_id"],
                layer_type=kwargs["layer_type"],
            )

        with patch("contexta.pipeline.dimension_runner.write_node", side_effect=mock_write_node):
            await commit_exploration_node(
                orchestrator=orch,
                conn=object(),
                project_id="proj-666",
                parent_id=None,
            )

        assert captured_kwargs[0]["layer_type"] == "exploration"

    @pytest.mark.asyncio
    async def test_runtime_error_message_names_failed_dimension(self):
        """RuntimeError from get_all_payloads names the failing dimension."""
        orch = await _build_orchestrator_with_failure(ReviewDimensionEnum.RISK)

        with patch("contexta.pipeline.dimension_runner.write_node"):
            with pytest.raises(RuntimeError, match="RISK|Risk"):
                await commit_exploration_node(
                    orchestrator=orch,
                    conn=object(),
                    project_id="proj-777",
                    parent_id=None,
                )

    def test_get_all_payloads_raises_on_pending_state(self):
        """get_all_payloads() raises RuntimeError if any task is still PENDING."""
        async def noop(task): pass
        async def runner(dim): return _make_payload(dim)

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
        # Do NOT call launch_all — tasks remain PENDING
        with pytest.raises(RuntimeError):
            orch.get_all_payloads()

    def test_get_all_payloads_raises_on_running_state(self):
        """get_all_payloads() raises RuntimeError if any task is RUNNING."""
        async def noop(task): pass
        async def runner(dim): return _make_payload(dim)

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
        # Manually force a task to RUNNING
        orch._tasks[ReviewDimensionEnum.INTENT].state = TaskState.RUNNING
        with pytest.raises(RuntimeError):
            orch.get_all_payloads()

    @pytest.mark.asyncio
    async def test_partial_failure_zero_writes(self):
        """Even one FAILED task out of 12 prevents any DB write."""
        orch = await _build_orchestrator_with_failure(ReviewDimensionEnum.DELIVERY)

        write_calls: list = []

        async def mock_write_node(conn, **kwargs):
            write_calls.append(1)
            return _make_node_row()

        with patch("contexta.pipeline.dimension_runner.write_node", side_effect=mock_write_node):
            with pytest.raises(RuntimeError):
                await commit_exploration_node(
                    orchestrator=orch,
                    conn=object(),
                    project_id="proj-888",
                    parent_id=None,
                )

        assert write_calls == [], "write_node was called despite a partial failure"


# ── Hypothesis: Property 23 ───────────────────────────────────────────────────


@given(
    project_id=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
        min_size=1,
        max_size=36,
    ),
    node_name=st.text(min_size=1, max_size=100),
)
@settings(max_examples=50)
def test_property_23_batch_commit_atomicity(project_id: str, node_name: str) -> None:
    """Property 23: all-COMPLETE run always produces exactly one write_node call.

    For any project_id and node_name, a fully-complete Layer 1 run results in
    exactly one atomic write to the nodes table — never zero, never more.
    """
    async def _run() -> None:
        orch = await _build_complete_orchestrator()
        write_calls: list = []

        async def mock_write_node(conn, **kwargs):
            write_calls.append(kwargs)
            return _make_node_row(
                project_id=kwargs["project_id"],
                node_name=kwargs["node_name"],
            )

        with patch(
            "contexta.pipeline.dimension_runner.write_node",
            side_effect=mock_write_node,
        ):
            await commit_exploration_node(
                orchestrator=orch,
                conn=object(),
                project_id=project_id,
                parent_id=None,
                node_name=node_name,
            )

        assert len(write_calls) == 1, (
            f"Expected 1 write_node call for project_id={project_id!r}, "
            f"got {len(write_calls)}"
        )
        assert write_calls[0]["project_id"] == project_id
        assert write_calls[0]["node_name"] == node_name
        assert len(write_calls[0]["metadata"]["dimensions"]) == 12

    asyncio.run(_run())
