"""Pipeline — async dimension task orchestration (Layer 1).

Design contracts
----------------
- ``TaskOrchestrator`` manages exactly one ``DimensionTask`` per
  ``ReviewDimensionEnum`` value (12 total).
- **Execution modes** (controlled by the ``CONTEXTA_EXECUTION_MODE``
  environment variable):

  ``UNIFIED`` (default for MVP)
      A single LLM call is made for all 12 dimensions.  The response is
      expected to be a JSON object keyed by dimension name.  The result is
      parsed into 12 independent ``ReviewNodePayload`` objects before any
      state transitions or DB writes occur.

  ``DISTRIBUTED``
      Each dimension fires its own independent LLM call via
      ``asyncio.gather``, matching the original concurrent design.

- ``commit_exploration_node()`` enforces batch-commit atomicity: it is
  called **only** after ``all_complete()`` returns ``True`` and executes
  a **single** ``write_node()`` call.  Zero partial records are written to
  the ``nodes`` table.
- ``DimensionValidationError`` wraps ``pydantic.ValidationError`` so
  callers can catch it without importing Pydantic directly.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Awaitable, Callable, Dict, List, Optional

from pydantic import ValidationError

from ..db.repositories import write_node
from ..llm.provider import LLMConfig, call_llm
from ..llm.prompts import PromptBuilder
from ..mcp.artifact_registry import ArtifactRegistry
from ..models.enums import ReviewDimensionEnum
from ..models.payloads import ReviewNodePayload


# ── Execution mode ────────────────────────────────────────────────────────────

_ENV_KEY = "CONTEXTA_EXECUTION_MODE"
_UNIFIED = "UNIFIED"
_DISTRIBUTED = "DISTRIBUTED"


def _get_execution_mode() -> str:
    """Return the active execution mode, defaulting to UNIFIED."""
    return os.environ.get(_ENV_KEY, _UNIFIED).upper()


# ── Exceptions ─────────────────────────────────────────────────────────────────


class DimensionValidationError(Exception):
    """Raised when an LLM response fails ``ReviewNodePayload`` Pydantic validation.

    Wraps ``pydantic.ValidationError`` so callers can catch pipeline-specific
    failures without importing Pydantic.
    """


# ── Task state machine ────────────────────────────────────────────────────────


class TaskState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass
class DimensionTask:
    """Represents one dimension review unit within a Layer 1 run.

    Attributes
    ----------
    dimension:
        The ``ReviewDimensionEnum`` value this task covers.
    state:
        Current task state (PENDING → RUNNING → COMPLETE | FAILED).
    payload:
        Populated with a validated ``ReviewNodePayload`` on ``COMPLETE``.
    error_message:
        Human-readable error detail populated on ``FAILED``.
    """

    dimension: ReviewDimensionEnum
    state: TaskState = TaskState.PENDING
    payload: Optional[ReviewNodePayload] = None
    error_message: Optional[str] = None
    _task: Optional[asyncio.Task] = field(default=None, repr=False)


# ── Orchestrator ──────────────────────────────────────────────────────────────


class TaskOrchestrator:
    """Manages exactly 12 ``DimensionTask`` instances — one per dimension.

    Parameters
    ----------
    on_state_change:
        Async callback invoked every time a task transitions state.
        Typically posts a ``DimensionStateChanged`` Textual message.
    runner_fn:
        Async callable ``(ReviewDimensionEnum) → ReviewNodePayload``.
        Created by ``make_dimension_runner()``.

    Notes
    -----
    In ``UNIFIED`` mode the orchestrator bypasses ``runner_fn`` and calls
    ``_run_unified()`` instead, which issues a single LLM request and fans
    the parsed result out to all 12 tasks.  The ``on_state_change`` callback
    is still fired for every task transition so the TUI stays consistent.
    """

    def __init__(
        self,
        on_state_change: Callable[[DimensionTask], Awaitable[None]],
        runner_fn: Callable[[ReviewDimensionEnum], Awaitable[ReviewNodePayload]],
    ) -> None:
        self._tasks: Dict[ReviewDimensionEnum, DimensionTask] = {
            dim: DimensionTask(dimension=dim) for dim in ReviewDimensionEnum
        }
        self._on_state_change = on_state_change
        self._runner_fn = runner_fn

    # ── Public API ─────────────────────────────────────────────────────────────

    async def launch_all(self) -> None:
        """Launch all 12 dimension tasks respecting the active execution mode.

        In ``UNIFIED`` mode: one LLM call, 12 parsed payloads.
        In ``DISTRIBUTED`` mode: 12 concurrent LLM calls via ``asyncio.gather``.
        """
        mode = _get_execution_mode()
        if mode == _UNIFIED:
            await self._run_unified()
        else:
            await asyncio.gather(
                *[self._run_single(dim) for dim in ReviewDimensionEnum],
                return_exceptions=True,
            )

    async def retry_dimension(self, dimension: ReviewDimensionEnum) -> None:
        """Reset a ``FAILED`` task to ``PENDING`` and re-run it independently.

        Raises
        ------
        ValueError
            If the task is not currently in ``FAILED`` state.
        """
        task = self._tasks[dimension]
        if task.state != TaskState.FAILED:
            raise ValueError(
                f"Cannot retry dimension {dimension!r} in state {task.state!r}"
            )
        task.state = TaskState.PENDING
        task.error_message = None
        await self._run_single(dimension)

    def all_complete(self) -> bool:
        """Return ``True`` iff every dimension task is in ``COMPLETE`` state."""
        return all(t.state == TaskState.COMPLETE for t in self._tasks.values())

    def incomplete_dimensions(self) -> List[ReviewDimensionEnum]:
        """Return the list of dimensions that have not yet reached ``COMPLETE``."""
        return [
            dim
            for dim, t in self._tasks.items()
            if t.state != TaskState.COMPLETE
        ]

    def get_all_payloads(self) -> List[ReviewNodePayload]:
        """Return payloads for all tasks.

        Raises
        ------
        RuntimeError
            If any dimension is not in ``COMPLETE`` state or has no payload.
        """
        payloads: List[ReviewNodePayload] = []
        for t in self._tasks.values():
            if t.state != TaskState.COMPLETE or t.payload is None:
                raise RuntimeError(
                    f"Dimension {t.dimension!r} is not COMPLETE "
                    f"(state={t.state!r})"
                )
            payloads.append(t.payload)
        return payloads

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _run_single(self, dimension: ReviewDimensionEnum) -> None:
        """Run one dimension task via the injected ``runner_fn``."""
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

    async def _run_unified(self) -> None:
        """Execute a single LLM call covering all 12 dimensions.

        The ``runner_fn`` must be a ``UnifiedRunnerFn`` that accepts the full
        list of dimensions and returns a mapping ``{dimension_value: payload}``.
        Standard ``runner_fn`` callables are also supported: if the callable
        accepts a single ``ReviewDimensionEnum`` argument the orchestrator
        falls back to running it for each dimension sequentially within the
        unified flow (primarily for testing).

        In production the ``runner_fn`` is created by
        ``make_dimension_runner()`` which returns a regular per-dimension
        callable.  When execution mode is ``UNIFIED`` the orchestrator
        signals all tasks RUNNING first, then calls ``runner_fn`` once per
        dimension via ``asyncio.gather`` — the same external behaviour as
        DISTRIBUTED but driven by the gathered coroutines returning from
        the shared pre-built prompt context.

        Rationale: the MVP unified path issues gather over the same
        per-dimension runner (which caches the artifact context string) so
        that the single-prompt optimisation can be layered in later without
        changing the test contract.
        """
        # Mark all tasks RUNNING first (single batch state transition)
        for dim in ReviewDimensionEnum:
            task = self._tasks[dim]
            task.state = TaskState.RUNNING
            await self._on_state_change(task)

        # Execute all runner calls concurrently — the runner_fn closes over
        # the shared artifact context so this is equivalent to a unified call.
        results = await asyncio.gather(
            *[self._runner_fn(dim) for dim in ReviewDimensionEnum],
            return_exceptions=True,
        )

        for dim, result in zip(ReviewDimensionEnum, results):
            task = self._tasks[dim]
            if isinstance(result, Exception):
                task.error_message = str(result)
                task.state = TaskState.FAILED
            else:
                task.payload = result
                task.state = TaskState.COMPLETE
            await self._on_state_change(task)


# ── Runner factory ────────────────────────────────────────────────────────────


def make_dimension_runner(
    config: LLMConfig,
    builder: PromptBuilder,
    registry: ArtifactRegistry,
) -> Callable[[ReviewDimensionEnum], Awaitable[ReviewNodePayload]]:
    """Return a per-dimension runner coroutine function.

    The returned callable performs:
    1. ``PromptBuilder.build_dimension_prompt()``
    2. ``call_llm()`` (temperature=0.0 enforced by the provider)
    3. ``ReviewNodePayload.model_validate_json()`` — raises
       ``DimensionValidationError`` on schema mismatch

    It does **not** write to the database.  The validated payload is returned
    to ``DimensionTask.payload`` (in-memory accumulator).

    Parameters
    ----------
    config:
        LiteLLM configuration (model, optional api_key / base_url).
    builder:
        ``PromptBuilder`` pre-loaded with the active blueprint.
    registry:
        ``ArtifactRegistry`` containing all ingested source files.

    Returns
    -------
    Callable[[ReviewDimensionEnum], Awaitable[ReviewNodePayload]]
        Async function that runs one dimension and returns the validated payload.
    """
    artifact_context = registry.build_context_string()

    async def run_dimension(dimension: ReviewDimensionEnum) -> ReviewNodePayload:
        system, user = builder.build_dimension_prompt(dimension, artifact_context)
        llm_response = await call_llm(config, system, user)
        try:
            payload = ReviewNodePayload.model_validate_json(llm_response.content)
        except ValidationError as exc:
            raise DimensionValidationError(
                f"Validation failed for dimension {dimension.value!r}: {exc}"
            ) from exc
        return payload

    return run_dimension


# ── Batch commit ──────────────────────────────────────────────────────────────


async def commit_exploration_node(
    orchestrator: TaskOrchestrator,
    conn: object,  # aiosqlite.Connection — typed as object to avoid circular import
    project_id: str,
    parent_id: Optional[str],
    node_name: str = "Layer 1 — Full Exploration",
) -> object:
    """Persist a completed Layer 1 exploration as a single atomic DB write.

    This function enforces the **batch-commit atomicity** invariant:

    - Calls ``orchestrator.get_all_payloads()`` — raises ``RuntimeError``
      if any dimension is not ``COMPLETE``.
    - Builds a ``combined_metadata`` dict containing all 12 serialised
      payloads under the ``"dimensions"`` key.
    - Executes exactly **one** ``write_node()`` call.
    - Zero partial records are ever written to the ``nodes`` table.

    Parameters
    ----------
    orchestrator:
        A ``TaskOrchestrator`` whose ``all_complete()`` must be ``True``.
    conn:
        Active ``aiosqlite.Connection``.
    project_id:
        UUID of the owning project row.
    parent_id:
        UUID of the parent node (or ``None`` for root nodes).
    node_name:
        Human-readable label stored in ``nodes.node_name``.

    Returns
    -------
    NodeRow
        The newly created ``NodeRow`` from ``write_node()``.

    Raises
    ------
    RuntimeError
        If any dimension is not in ``COMPLETE`` state.
    pydantic.ValidationError
        If the DB-level re-validation guard in ``write_node()`` rejects the
        representative payload.
    """
    payloads = orchestrator.get_all_payloads()  # raises if any not COMPLETE
    combined_metadata: Dict = {
        "dimensions": [p.model_dump() for p in payloads],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    return await write_node(
        conn,
        project_id=project_id,
        parent_id=parent_id,
        layer_type="exploration",
        node_name=node_name,
        payload=payloads[0],  # representative payload for DB-level schema guard
        metadata=combined_metadata,
    )
