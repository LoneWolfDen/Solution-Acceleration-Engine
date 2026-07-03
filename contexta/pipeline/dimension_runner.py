"""Async 12-dimension task orchestration — Layer 1 Exploration.

Design contracts
----------------
- ``TaskOrchestrator`` pre-populates exactly one ``DimensionTask`` per
  ``ReviewDimensionEnum`` value at construction time.
- ``launch_all()`` runs all 12 dimensions **sequentially** with a configurable
  inter-task delay (``request_delay_seconds``) to respect the upstream LLM
  provider's TPM ceiling.  One task failure never aborts the remaining
  dimensions — ``_run_single()`` catches and records all exceptions internally.
- The runner function returned by ``make_dimension_runner()`` performs LLM
  call + Pydantic validation ONLY — it never writes to the database.
- ``commit_exploration_node()`` performs the single all-or-nothing DB write
  after all 12 tasks reach COMPLETE state.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Awaitable, Callable, List, Optional

import aiosqlite
from pydantic import ValidationError

from ..db.repositories import write_node
from ..llm.provider import LLMConfig, call_llm
from ..llm.prompts import PromptBuilder
from ..mcp.artifact_registry import ArtifactRegistry
from ..models.enums import ReviewDimensionEnum
from ..models.payloads import ReviewNodePayload


# ── Exceptions ────────────────────────────────────────────────────────────────


class DimensionValidationError(Exception):
    """Raised when Pydantic validation fails for a dimension LLM response."""


# ── State machine ─────────────────────────────────────────────────────────────


class TaskState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


# ── Task ──────────────────────────────────────────────────────────────────────


@dataclass
class DimensionTask:
    dimension: ReviewDimensionEnum
    state: TaskState = TaskState.PENDING
    payload: Optional[ReviewNodePayload] = None
    error_message: Optional[str] = None
    _task: Optional[asyncio.Task] = field(default=None, repr=False)  # type: ignore[type-arg]


# ── Orchestrator ──────────────────────────────────────────────────────────────


class TaskOrchestrator:
    """Manages exactly 12 ``DimensionTask`` instances — one per dimension.

    Parameters
    ----------
    on_state_change:
        Async callback invoked whenever a task changes state.  Used by the TUI
        to update ``DimensionRow`` widgets without polling.
    runner_fn:
        Async callable that accepts a ``ReviewDimensionEnum`` and returns a
        validated ``ReviewNodePayload``.  Constructed by
        ``make_dimension_runner()``.
    request_delay_seconds:
        Seconds to wait between consecutive dimension calls.  Defaults to
        ``0.0`` (no delay) so that unit tests run without artificial pausing.
        Production callers should pass ``config.llm_request_delay_seconds``
        (default 2.5 s) to stay within the provider's TPM ceiling.
    """

    def __init__(
        self,
        on_state_change: Callable[[DimensionTask], Awaitable[None]],
        runner_fn: Callable[[ReviewDimensionEnum], Awaitable[ReviewNodePayload]],
        request_delay_seconds: float = 0.0,
    ) -> None:
        self._tasks: dict[ReviewDimensionEnum, DimensionTask] = {
            dim: DimensionTask(dimension=dim) for dim in ReviewDimensionEnum
        }
        self._on_state_change = on_state_change
        self._runner_fn = runner_fn
        self._request_delay_seconds = request_delay_seconds

    # ── Public API ────────────────────────────────────────────────────────────

    async def launch_all(self) -> None:
        """Run all 12 dimension tasks sequentially with inter-task pacing.

        Each dimension is awaited to completion before the next one starts.
        If ``request_delay_seconds > 0``, the orchestrator sleeps for that
        duration between tasks to respect the provider's TPM ceiling.  The
        delay is skipped after the final dimension.

        Task failures are absorbed by ``_run_single()`` — a single dimension
        error never prevents the remaining dimensions from running.
        """
        dimensions = list(ReviewDimensionEnum)
        last_index = len(dimensions) - 1
        for index, dim in enumerate(dimensions):
            await self._run_single(dim)
            if index < last_index and self._request_delay_seconds > 0:
                await asyncio.sleep(self._request_delay_seconds)

    async def retry_dimension(self, dimension: ReviewDimensionEnum) -> None:
        """Reset a FAILED task to PENDING and re-run it independently."""
        task = self._tasks[dimension]
        if task.state != TaskState.FAILED:
            raise ValueError(
                f"Cannot retry dimension {dimension!r} in state {task.state!r}"
            )
        task.state = TaskState.PENDING
        task.error_message = None
        task.payload = None
        await self._run_single(dimension)

    def all_complete(self) -> bool:
        """Return ``True`` iff every dimension is in COMPLETE state."""
        return all(t.state == TaskState.COMPLETE for t in self._tasks.values())

    def incomplete_dimensions(self) -> List[ReviewDimensionEnum]:
        """Return dimensions that have not yet reached COMPLETE state."""
        return [
            dim
            for dim, t in self._tasks.items()
            if t.state != TaskState.COMPLETE
        ]

    def get_all_payloads(self) -> List[ReviewNodePayload]:
        """Return all 12 validated payloads.

        Raises
        ------
        RuntimeError
            If any dimension is not in COMPLETE state.
        """
        payloads: List[ReviewNodePayload] = []
        for t in self._tasks.values():
            if t.state != TaskState.COMPLETE or t.payload is None:
                raise RuntimeError(
                    f"Dimension {t.dimension!r} is not complete (state={t.state!r})"
                )
            payloads.append(t.payload)
        return payloads

    def get_task(self, dimension: ReviewDimensionEnum) -> DimensionTask:
        return self._tasks[dimension]

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _run_single(self, dimension: ReviewDimensionEnum) -> None:
        task = self._tasks[dimension]
        task.state = TaskState.RUNNING
        await self._on_state_change(task)
        try:
            payload = await self._runner_fn(dimension)
            task.payload = payload
            task.state = TaskState.COMPLETE
        except Exception as exc:
            task.error_message = str(exc)
            task.state = TaskState.FAILED
        await self._on_state_change(task)


# ── Runner factory ────────────────────────────────────────────────────────────


def make_dimension_runner(
    config: LLMConfig,
    builder: PromptBuilder,
    registry: ArtifactRegistry,
) -> Callable[[ReviewDimensionEnum], Awaitable[ReviewNodePayload]]:
    """Return a runner_fn closed over the given config, builder, and registry.

    The returned coroutine:
    1. Builds the (system, user) prompt pair for the dimension.
    2. Calls ``call_llm()`` (temperature=0.0 enforced internally).
    3. Validates the JSON response against ``ReviewNodePayload``.
    4. Returns the validated payload (in-memory only — no DB write here).

    Raises
    ------
    DimensionValidationError
        If Pydantic validation fails for the LLM response.
    """
    artifact_context = registry.build_context_string()

    async def run_dimension(dimension: ReviewDimensionEnum) -> ReviewNodePayload:
        system, user = builder.build_dimension_prompt(dimension, artifact_context)
        llm_response = await call_llm(config, system, user)
        try:
            # Parse into a dict first so we can inject raw_llm_response.
            # The LLM must not be asked to produce this field — it is a
            # transport-layer annotation set here after a successful call.
            parsed = json.loads(llm_response.content)
            parsed["raw_llm_response"] = llm_response.content
            payload = ReviewNodePayload.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise DimensionValidationError(
                f"Validation failed for {dimension.value!r}: {exc}"
            ) from exc
        return payload

    return run_dimension


# ── Batch commit ──────────────────────────────────────────────────────────────


async def commit_exploration_node(
    orchestrator: TaskOrchestrator,
    conn: aiosqlite.Connection,
    project_id: str,
    node_name: str = "Layer 1 — Full Exploration",
    parent_id: Optional[str] = None,
) -> "NodeRow":  # type: ignore[name-defined]  # imported lazily to avoid cycle
    """Collect all 12 validated payloads and write a single exploration node.

    This is the only place where Layer 1 results are persisted.  The ``nodes``
    table never contains a partial Layer 1 record (Property 23).

    Raises
    ------
    RuntimeError
        If any dimension is not in COMPLETE state.
    pydantic.ValidationError
        If the DB-level re-validation guard in ``write_node()`` fails.
    """
    from ..db.models import NodeRow  # local import avoids circular dependency

    payloads = orchestrator.get_all_payloads()
    combined_metadata: dict = {
        "dimensions": [p.model_dump() for p in payloads],
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "routing_decisions": [],
    }

    # Use the first payload as the representative schema-guard payload.
    return await write_node(
        conn,
        project_id=project_id,
        parent_id=parent_id,
        layer_type="exploration",
        node_name=node_name,
        payload=payloads[0],
        metadata=combined_metadata,
    )
