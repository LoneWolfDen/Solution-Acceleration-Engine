"""DimensionRow widget — one per ReviewDimensionEnum value.

Renders: dimension name label, status badge, progress bar (RUNNING only),
and a Retry button (FAILED only).  Reacts to ``DimensionStateChanged``
messages to update its display.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Label, ProgressBar, Static

from ...models.enums import ReviewDimensionEnum
from ...pipeline.dimension_runner import TaskState
from ..messages import DimensionStateChanged

# State → display label mapping
_STATE_LABELS: dict[TaskState, str] = {
    TaskState.PENDING: "PENDING",
    TaskState.RUNNING: "RUNNING",
    TaskState.COMPLETE: "COMPLETE",
    TaskState.FAILED: "FAILED",
}

_STATE_CLASSES: dict[TaskState, str] = {
    TaskState.PENDING: "state-pending",
    TaskState.RUNNING: "state-running",
    TaskState.COMPLETE: "state-complete",
    TaskState.FAILED: "state-failed",
}


class DimensionRow(Static):
    """A single row in the pipeline status pane.

    Parameters
    ----------
    dimension:
        The ``ReviewDimensionEnum`` value this row represents.
    """

    DEFAULT_CSS = """
    DimensionRow {
        height: auto;
        padding: 0 1;
        border-bottom: solid $panel;
    }
    DimensionRow Horizontal {
        height: 1;
    }
    DimensionRow .dim-name {
        width: 15;
        color: $text;
    }
    DimensionRow .state-badge {
        width: 10;
        text-align: center;
    }
    DimensionRow .state-pending  { color: $text-muted; }
    DimensionRow .state-running  { color: $warning; }
    DimensionRow .state-complete { color: $success; }
    DimensionRow .state-failed   { color: $error; }
    DimensionRow ProgressBar {
        width: 20;
    }
    DimensionRow .retry-btn {
        width: 8;
        height: 1;
    }
    DimensionRow .error-label {
        color: $error;
        width: 1fr;
    }
    """

    def __init__(self, dimension: ReviewDimensionEnum, **kwargs) -> None:
        super().__init__(**kwargs)
        self._dimension = dimension
        self._state = TaskState.PENDING
        self._error: str | None = None

    @property
    def dimension(self) -> ReviewDimensionEnum:
        return self._dimension

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(
                self._dimension.value,
                classes="dim-name",
                id=f"dim-name-{self._dimension.name}",
            )
            yield Label(
                _STATE_LABELS[self._state],
                classes=f"state-badge {_STATE_CLASSES[self._state]}",
                id=f"dim-state-{self._dimension.name}",
            )
            yield ProgressBar(
                total=100,
                show_eta=False,
                id=f"dim-progress-{self._dimension.name}",
            )
            yield Button(
                "Retry",
                variant="warning",
                classes="retry-btn",
                id=f"dim-retry-{self._dimension.name}",
            )
            yield Label(
                "",
                classes="error-label",
                id=f"dim-error-{self._dimension.name}",
            )

    def on_mount(self) -> None:
        self._sync_display()

    def update_state(self, state: TaskState, error: str | None = None) -> None:
        """Update this row's display to reflect a new task state."""
        self._state = state
        self._error = error
        self._sync_display()

    def _sync_display(self) -> None:
        """Reconcile all child widget visibilities and labels to ``_state``."""
        state_label = self.query_one(f"#dim-state-{self._dimension.name}", Label)
        progress = self.query_one(f"#dim-progress-{self._dimension.name}", ProgressBar)
        retry_btn = self.query_one(f"#dim-retry-{self._dimension.name}", Button)
        error_label = self.query_one(f"#dim-error-{self._dimension.name}", Label)

        state_label.update(_STATE_LABELS[self._state])
        # Remove old state classes then add the current one
        for cls in _STATE_CLASSES.values():
            state_label.remove_class(cls)
        state_label.add_class(_STATE_CLASSES[self._state])

        # Progress bar: visible only while RUNNING
        progress.display = self._state == TaskState.RUNNING
        if self._state == TaskState.RUNNING:
            progress.advance(10)

        # Retry button: visible only when FAILED
        retry_btn.display = self._state == TaskState.FAILED

        # Error label
        if self._state == TaskState.FAILED and self._error:
            error_label.update(f" ✗ {self._error[:60]}")
            error_label.display = True
        else:
            error_label.update("")
            error_label.display = False

    # ── Message handlers ──────────────────────────────────────────────────────

    def on_dimension_state_changed(self, message: DimensionStateChanged) -> None:
        if message.dimension == self._dimension:
            self.update_state(message.state, message.error)
