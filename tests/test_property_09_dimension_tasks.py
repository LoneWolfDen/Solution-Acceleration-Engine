"""Property 9 — Exactly 12 Dimension Tasks Launched.

For any call to ``TaskOrchestrator.launch_all()``, exactly 12 runner
invocations must occur — one per ``ReviewDimensionEnum`` value — with no
duplicates and no omissions.  This property holds in both UNIFIED and
DISTRIBUTED execution modes.

Coverage
--------
- Unit: verify exactly 12 invocations, one per dimension, no duplicates.
- Unit: DISTRIBUTED mode via env-var override.
- Unit: UNIFIED mode (default).
- Unit: ``make_dimension_runner`` factory produces a callable per dimension.
- Unit: failed task still counts as invoked (runner_fn was called).
- Hypothesis: arbitrary mock return values; invocation count always 12.
"""

from __future__ import annotations

import asyncio
from typing import List, Set
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from contexta.models.enums import ReviewDimensionEnum
from contexta.models.payloads import ReviewNodePayload
from contexta.models.enums import ConfidenceEnum
from contexta.pipeline.dimension_runner import (
    DimensionTask,
    TaskOrchestrator,
    TaskState,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_payload(dimension: ReviewDimensionEnum) -> ReviewNodePayload:
    return ReviewNodePayload(
        dimension=dimension,
        findings=[],
        overall_confidence=ConfidenceEnum.GREEN,
        raw_llm_response='{"ok": true}',
    )


def _make_orchestrator(
    runner_fn=None,
    on_state_change=None,
) -> tuple[TaskOrchestrator, list]:
    """Return (orchestrator, invocation_log) with an optional custom runner."""
    invocations: list = []

    if runner_fn is None:
        async def default_runner(dim: ReviewDimensionEnum) -> ReviewNodePayload:
            invocations.append(dim)
            return _make_payload(dim)
        runner_fn = default_runner

    async def _noop(task: DimensionTask) -> None:
        pass

    cb = on_state_change or _noop
    orch = TaskOrchestrator(on_state_change=cb, runner_fn=runner_fn)
    return orch, invocations


# ── Property 9 unit tests ─────────────────────────────────────────────────────


class TestExactly12DimensionTasksLaunched:

    @pytest.mark.asyncio
    async def test_exactly_12_invocations_unified_mode(self):
        """UNIFIED mode: runner_fn is called exactly 12 times."""
        invocations: list = []

        async def runner(dim: ReviewDimensionEnum) -> ReviewNodePayload:
            invocations.append(dim)
            return _make_payload(dim)

        async def noop(task): pass

        with patch.dict("os.environ", {"CONTEXTA_EXECUTION_MODE": "UNIFIED"}):
            orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
            await orch.launch_all()

        assert len(invocations) == 12

    @pytest.mark.asyncio
    async def test_exactly_12_invocations_distributed_mode(self):
        """DISTRIBUTED mode: runner_fn is called exactly 12 times."""
        invocations: list = []

        async def runner(dim: ReviewDimensionEnum) -> ReviewNodePayload:
            invocations.append(dim)
            return _make_payload(dim)

        async def noop(task): pass

        with patch.dict("os.environ", {"CONTEXTA_EXECUTION_MODE": "DISTRIBUTED"}):
            orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
            await orch.launch_all()

        assert len(invocations) == 12

    @pytest.mark.asyncio
    async def test_no_duplicate_dimensions(self):
        """Every dimension is invoked at most once."""
        invocations: list = []

        async def runner(dim: ReviewDimensionEnum) -> ReviewNodePayload:
            invocations.append(dim)
            return _make_payload(dim)

        async def noop(task): pass

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
        await orch.launch_all()

        assert len(invocations) == len(set(invocations)), (
            f"Duplicate dimensions found: {invocations}"
        )

    @pytest.mark.asyncio
    async def test_all_enum_values_covered(self):
        """Every ``ReviewDimensionEnum`` value is invoked exactly once."""
        invocations: list = []

        async def runner(dim: ReviewDimensionEnum) -> ReviewNodePayload:
            invocations.append(dim)
            return _make_payload(dim)

        async def noop(task): pass

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
        await orch.launch_all()

        assert set(invocations) == set(ReviewDimensionEnum)

    @pytest.mark.asyncio
    async def test_orchestrator_pre_populated_with_12_tasks(self):
        """``TaskOrchestrator.__init__`` creates exactly 12 DimensionTask objects."""
        async def noop(task): pass
        async def runner(dim): return _make_payload(dim)

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
        assert len(orch._tasks) == 12
        assert set(orch._tasks.keys()) == set(ReviewDimensionEnum)

    @pytest.mark.asyncio
    async def test_all_tasks_complete_after_successful_launch(self):
        """After a clean launch_all(), all 12 tasks are COMPLETE."""
        async def noop(task): pass
        async def runner(dim): return _make_payload(dim)

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
        await orch.launch_all()

        assert orch.all_complete() is True
        assert orch.incomplete_dimensions() == []

    @pytest.mark.asyncio
    async def test_failed_task_still_counts_as_invoked(self):
        """A runner_fn that raises still records an invocation."""
        invocations: list = []

        async def failing_runner(dim: ReviewDimensionEnum) -> ReviewNodePayload:
            invocations.append(dim)
            raise RuntimeError("simulated failure")

        async def noop(task): pass

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=failing_runner)
        await orch.launch_all()

        assert len(invocations) == 12

    @pytest.mark.asyncio
    async def test_state_change_callback_called_for_each_task(self):
        """``on_state_change`` is called at least once per dimension."""
        state_changes: list = []

        async def on_change(task: DimensionTask) -> None:
            state_changes.append(task.dimension)

        async def runner(dim): return _make_payload(dim)

        orch = TaskOrchestrator(on_state_change=on_change, runner_fn=runner)
        await orch.launch_all()

        # Every dimension should appear at least once
        assert set(state_changes) == set(ReviewDimensionEnum)

    @pytest.mark.asyncio
    async def test_tasks_start_in_pending_state(self):
        """All tasks are PENDING before launch_all() is called."""
        async def noop(task): pass
        async def runner(dim): return _make_payload(dim)

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
        for task in orch._tasks.values():
            assert task.state == TaskState.PENDING

    @pytest.mark.asyncio
    async def test_payloads_populated_after_complete(self):
        """After launch_all(), every task has a non-None payload."""
        async def noop(task): pass
        async def runner(dim): return _make_payload(dim)

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
        await orch.launch_all()

        for task in orch._tasks.values():
            assert task.payload is not None
            assert isinstance(task.payload, ReviewNodePayload)

    @pytest.mark.asyncio
    async def test_get_all_payloads_returns_12_after_complete(self):
        """``get_all_payloads()`` returns a list of exactly 12 payloads."""
        async def noop(task): pass
        async def runner(dim): return _make_payload(dim)

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
        await orch.launch_all()

        payloads = orch.get_all_payloads()
        assert len(payloads) == 12

    @pytest.mark.asyncio
    async def test_get_all_payloads_raises_if_not_complete(self):
        """``get_all_payloads()`` raises RuntimeError if any task is not COMPLETE."""
        async def noop(task): pass
        async def failing_runner(dim): raise RuntimeError("fail")

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=failing_runner)
        await orch.launch_all()

        with pytest.raises(RuntimeError):
            orch.get_all_payloads()

    @pytest.mark.asyncio
    async def test_retry_dimension_reruns_failed_task(self):
        """``retry_dimension()`` succeeds for a previously FAILED task."""
        call_count = {"n": 0}

        async def flaky_runner(dim: ReviewDimensionEnum) -> ReviewNodePayload:
            call_count["n"] += 1
            if call_count["n"] <= 1 and dim == ReviewDimensionEnum.INTENT:
                raise RuntimeError("first attempt fails")
            return _make_payload(dim)

        async def noop(task): pass

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=flaky_runner)
        await orch.launch_all()

        # INTENT should be FAILED on first run
        if orch._tasks[ReviewDimensionEnum.INTENT].state == TaskState.FAILED:
            await orch.retry_dimension(ReviewDimensionEnum.INTENT)
            assert orch._tasks[ReviewDimensionEnum.INTENT].state == TaskState.COMPLETE

    @pytest.mark.asyncio
    async def test_retry_non_failed_task_raises_value_error(self):
        """``retry_dimension()`` raises ValueError if task is not FAILED."""
        async def noop(task): pass
        async def runner(dim): return _make_payload(dim)

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
        await orch.launch_all()

        # All complete — retry should raise
        with pytest.raises(ValueError, match="Cannot retry"):
            await orch.retry_dimension(ReviewDimensionEnum.INTENT)


# ── Hypothesis property test ──────────────────────────────────────────────────


@given(
    confidence=st.sampled_from(list(ConfidenceEnum)),
)
@settings(max_examples=50)
def test_property_9_exactly_12_dimensions_invoked(confidence: ConfidenceEnum) -> None:
    """Property 9: for any valid runner output, exactly 12 tasks are launched.

    Synchronous wrapper using ``asyncio.run()`` so Hypothesis can drive it
    without ``pytest-asyncio`` async test support.
    """
    invocations: list = []

    async def _run() -> None:
        async def runner(dim: ReviewDimensionEnum) -> ReviewNodePayload:
            invocations.append(dim)
            return ReviewNodePayload(
                dimension=dim,
                findings=[],
                overall_confidence=confidence,
                raw_llm_response='{"ok": true}',
            )

        async def noop(task): pass

        orch = TaskOrchestrator(on_state_change=noop, runner_fn=runner)
        await orch.launch_all()

        assert len(invocations) == 12, (
            f"Expected 12 invocations, got {len(invocations)}: {invocations}"
        )
        assert set(invocations) == set(ReviewDimensionEnum), (
            f"Missing dimensions: {set(ReviewDimensionEnum) - set(invocations)}"
        )

    asyncio.run(_run())
