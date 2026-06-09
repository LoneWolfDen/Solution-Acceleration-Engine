"""DimensionRow — one status block per ReviewDimensionEnum value.

Renders inside ``PipelineView``'s scrollable dimension list.  One instance is
created for each of the 12 ``ReviewDimensionEnum`` values.

Visual structure (horizontal)
------------------------------
┌──────────────────────────────────────────────────────────────┐
│  [Architecture]  [● PENDING ]  [━━━━━━━━━━]  [Retry]        │
└──────────────────────────────────────────────────────────────┘
  ↑ dimension      ↑ status       ↑ progress     ↑ retry btn
  Label (fixed)    Static         ProgressBar    Button
                   (reactive)     (RUNNING only) (FAILED only)

State visibility matrix
-----------------------
State     | badge text   | progress bar | retry button
------    | -----------  | ------------ | ------------
PENDING   | ○ PENDING    | hidden       | hidden
RUNNING   | ● RUNNING    | shown        | hidden
COMPLETE  | ✓ COMPLETE   | hidden       | hidden
FAILED    | ✗ FAILED     | hidden       | shown
"""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Button, Label, ProgressBar, Static

from contexta.models.enums import ReviewDimensionEnum
from contexta.tui.messages import DimensionStateChanged, TaskState

# Maps TaskState → (display text, CSS class applied to the badge Static)
_STATE_BADGE: dict[TaskState, tuple[str, str]] = {
    TaskState.PENDING:  ("○ PENDING",  "badge-pending"),
    TaskState.RUNNING:  ("● RUNNING",  "badge-running"),
    TaskState.COMPLETE: ("✓ COMPLETE", "badge-complete"),
    TaskState.FAILED:   ("✗ FAILED",   "badge-failed"),
}

_ALL_BADGE_CLASSES = {cls for _, cls in _STATE_BADGE.values()}


class DimensionRow(Widget):
    """Single-row status block for one ``ReviewDimensionEnum``.

    Reacts to ``DimensionStateChanged`` messages whose ``dimension`` matches
    this row's dimension.  Other dimensions' messages are ignored.
    """

    DEFAULT_CSS = """
    DimensionRow {
        height: 3;
        width: 100%;
        layout: horizontal;
        align: left middle;
        padding: 0 1;
        border-bottom: solid $background-darken-2;
    }

    DimensionRow .dim-label {
        width: 14;
        color: $text;
    }

    DimensionRow .dim-badge {
        width: 14;
        text-align: center;
    }

    DimensionRow .badge-pending  { color: $text-muted; }
    DimensionRow .badge-running  { color: $warning; }
    DimensionRow .badge-complete { color: $success; }
    DimensionRow .badge-failed   { color: $error; }

    DimensionRow .dim-progress {
        width: 20;
    }

    DimensionRow .dim-retry {
        width: 10;
        display: none;
    }

    DimensionRow .dim-error {
        width: 1fr;
        color: $error;
        text-style: italic;
    }

    DimensionRow.-running .dim-progress {
        display: block;
    }

    DimensionRow.-failed .dim-retry {
        display: block;
    }
    """

    def __init__(self, dimension: ReviewDimensionEnum, **kwargs) -> None:
        super().__init__(**kwargs)
        self.dimension = dimension
        self._state: TaskState = TaskState.PENDING
        self._error: Optional[str] = None

    # ── Compose ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        badge_text, badge_class = _STATE_BADGE[TaskState.PENDING]
        yield Label(self.dimension.value, classes="dim-label")
        yield Static(badge_text, classes=f"dim-badge {badge_class}")
        yield ProgressBar(
            total=100,
            show_eta=False,
            show_percentage=False,
            classes="dim-progress",
        )
        yield Button("Retry", variant="warning", classes="dim-retry")
        yield Static("", classes="dim-error")

    # ── Public API ────────────────────────────────────────────────────────────

    def update_state(self, state: TaskState, error: Optional[str] = None) -> None:
        """Update the row to reflect the new task state.

        Called directly by ``PipelineView.update_dimension()`` and also by the
        ``on_dimension_state_changed`` handler when the message matches.
        """
        self._state = state
        self._error = error

        badge_text, badge_class = _STATE_BADGE[state]

        # Update badge text and class.
        badge = self.query_one(".dim-badge", Static)
        badge.update(badge_text)
        for cls in _ALL_BADGE_CLASSES:
            badge.remove_class(cls)
        badge.add_class(badge_class)

        # Update row-level modifier classes for CSS visibility toggles.
        self.remove_class("-pending", "-running", "-complete", "-failed")
        self.add_class(f"-{state.value.lower()}")

        # Animate the progress bar only while RUNNING.
        if state == TaskState.RUNNING:
            progress = self.query_one(".dim-progress", ProgressBar)
            progress.update(progress=50)  # indeterminate midpoint visual

        # Show error text when FAILED.
        error_label = self.query_one(".dim-error", Static)
        error_label.update(error or "")

    # ── Message handler ───────────────────────────────────────────────────────

    def on_dimension_state_changed(self, event: DimensionStateChanged) -> None:
        """React only to changes for this row's dimension."""
        if event.dimension != self.dimension:
            return
        event.stop()
        self.update_state(event.state, event.error)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Retry button — re-post a DimensionStateChanged(PENDING) upward.

        The actual retry logic lives in ``TaskOrchestrator``; this widget only
        signals intent by resetting the state to PENDING.  The screen wires
        the orchestrator call.
        """
        event.stop()
        # Optimistically reset display to PENDING.
        self.update_state(TaskState.PENDING)
        # Bubble a state change so the screen can trigger the retry.
        self.post_message(
            DimensionStateChanged(
                dimension=self.dimension,
                state=TaskState.PENDING,
                error=None,
            )
        )
