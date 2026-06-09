"""Custom Textual Message classes for cross-widget communication.

All messages are posted on the Textual app's message bus.  Widgets subscribe
by implementing ``on_<MessageClass>`` handlers (snake-cased class name).
"""

from __future__ import annotations

from textual.message import Message

from ..mcp.artifact_registry import IngestedArtifact
from ..models.enums import ReviewDimensionEnum
from ..pipeline.dimension_runner import TaskState


class DimensionStateChanged(Message):
    """Posted by ``TaskOrchestrator`` when a dimension task changes state."""

    def __init__(
        self,
        dimension: ReviewDimensionEnum,
        state: TaskState,
        error: str | None = None,
    ) -> None:
        super().__init__()
        self.dimension = dimension
        self.state = state
        self.error = error


class ArtifactIngested(Message):
    """Posted by the ingest flow when a new file is successfully registered."""

    def __init__(self, artifact: IngestedArtifact) -> None:
        super().__init__()
        self.artifact = artifact


class AdvisoryAlertDetected(Message):
    """Posted by ``ProactiveAdvisor`` when a high-risk pattern is found."""

    def __init__(self, alerts: list) -> None:
        super().__init__()
        self.alerts = alerts


class CitationJumpRequested(Message):
    """Posted by ``PipelineView`` when an ``IssueFinding`` is selected.

    Carries the coordinates of the first ``SourceCitation`` in the finding.
    ``ArtifactView`` handles this message to scroll and highlight the target
    line range (Requirements 10.8, 10.9).
    """

    def __init__(self, file_path: str, line_start: int, line_end: int) -> None:
        super().__init__()
        self.file_path = file_path
        self.line_start = line_start
        self.line_end = line_end
