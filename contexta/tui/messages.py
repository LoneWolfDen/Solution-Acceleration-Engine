"""Custom Textual Message classes for cross-widget communication.

All four messages are pure data carriers — no logic, no side-effects.
Consumers subscribe by defining ``on_<MessageClass>`` handlers or using
the ``@on(MessageClass)`` decorator on their widget/screen/app class.

Import order in this module:
- stdlib typing
- textual
- contexta models  (no TUI or pipeline imports — keeps the layer clean)
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from textual.message import Message

from contexta.models.enums import ReviewDimensionEnum

if TYPE_CHECKING:
    # Avoid circular imports at runtime; only used for type hints.
    from contexta.mcp.artifact_registry import IngestedArtifact


# ── TaskState enum ────────────────────────────────────────────────────────────
# Defined here so the TUI layer has no dependency on the pipeline layer.
# When pipeline.dimension_runner ships it re-exports TaskState from here,
# keeping the canonical definition in one place.


class TaskState(str, Enum):
    """State machine values for a single dimension review task."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


# ── Messages ──────────────────────────────────────────────────────────────────


class DimensionStateChanged(Message):
    """Posted by TaskOrchestrator when a dimension task changes state.

    Consumed by ``DimensionRow`` to refresh its status badge, progress bar,
    and retry button visibility.
    """

    def __init__(
        self,
        dimension: ReviewDimensionEnum,
        state: TaskState,
        error: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.dimension: ReviewDimensionEnum = dimension
        self.state: TaskState = state
        self.error: Optional[str] = error


class ArtifactIngested(Message):
    """Posted by MCPHostClient when a new file is successfully ingested.

    Consumed by ``ArtifactView`` to add the file to its browser list and
    refresh the displayed line count.
    """

    def __init__(self, artifact: "IngestedArtifact") -> None:
        super().__init__()
        self.artifact = artifact


class AdvisoryAlertDetected(Message):
    """Posted by ProactiveAdvisor when a high-risk pattern is detected.

    Consumed by ``MainScreen`` to open the ``RiskBlockingModal`` before
    allowing the user to proceed with Layer 2 synthesis.

    ``alerts`` is a list of ``AdvisoryAlert`` dataclass instances, typed as
    ``list`` here to avoid importing the pipeline layer at message-definition
    time.
    """

    def __init__(self, alerts: List) -> None:
        super().__init__()
        self.alerts: List = alerts


class CitationJumpRequested(Message):
    """Posted by PipelineView when an IssueFinding is highlighted/selected.

    Carries the ``file_path``, ``line_start``, and ``line_end`` from
    ``finding.citations[0]``.

    ``ArtifactView`` handles this message to:
    1. Switch the preview to ``file_path`` if it is not already active.
    2. Scroll the content log to bring ``line_start`` into view.
    3. Apply a distinct highlight style across ``[line_start, line_end]``.

    The highlight is cleared when:
    - A different finding is selected (a new ``CitationJumpRequested`` is
      posted), or
    - The user navigates away from the current artifact.
    """

    def __init__(self, file_path: str, line_start: int, line_end: int) -> None:
        super().__init__()
        self.file_path: str = file_path
        self.line_start: int = line_start
        self.line_end: int = line_end
