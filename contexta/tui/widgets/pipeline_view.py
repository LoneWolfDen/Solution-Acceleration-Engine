"""PipelineView — right split pane (70% width).

Renders the Active Pipeline: metadata cluster, all 12 dimension status rows,
and (after Layer 2) the reconciliation panel.

Layout (vertical, inside a 70%-wide pane)
------------------------------------------
┌──────────────────────────────────────────────────────────────────┐
│  📦 Metadata Cluster                                             │
│     Tags: #Lean-Client-Team  #Complex-Testing                    │
│     Node: Draft v1                                               │
├──────────────────────────────────────────────────────────────────┤
│  ┌ Dimension Status ─────────────────────────────────────────┐  │
│  │  Intent      ○ PENDING                                     │  │
│  │  Scope       ● RUNNING  [━━━━━━━━━━]                       │  │
│  │  Ownership   ✓ COMPLETE                                     │  │
│  │  …                                                          │  │
│  └────────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│  Reconciliation Panel (hidden until Layer 2 complete)            │
└──────────────────────────────────────────────────────────────────┘

``CitationJumpRequested`` is emitted by this widget (not consumed here) when
the user selects an ``IssueFinding``.  ``MainScreen`` (or any ancestor) will
propagate it to ``ArtifactView``.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Label, Static

from contexta.models.enums import ReviewDimensionEnum
from contexta.models.findings import IssueFinding
from contexta.tui.messages import CitationJumpRequested, DimensionStateChanged, TaskState
from contexta.tui.widgets.dimension_row import DimensionRow


class MetadataCluster(Widget):
    """Compact project metadata display: tags and active node name."""

    DEFAULT_CSS = """
    MetadataCluster {
        height: auto;
        padding: 1 2;
        border-bottom: solid $accent-darken-2;
        background: $background-darken-1;
    }
    MetadataCluster .meta-title {
        text-style: bold;
        color: $accent;
    }
    MetadataCluster .meta-row {
        color: $text-muted;
    }
    """

    def __init__(
        self,
        project_name: str = "—",
        node_name: str = "—",
        tags: Optional[List[str]] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._project_name = project_name
        self._node_name = node_name
        self._tags: List[str] = tags or []

    def compose(self) -> ComposeResult:
        yield Static("📦 Metadata Cluster", classes="meta-title")
        yield Static(self._tags_line(), id="meta-tags", classes="meta-row")
        yield Static(f"Node: {self._node_name}", id="meta-node", classes="meta-row")

    def update_metadata(
        self,
        project_name: Optional[str] = None,
        node_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Refresh displayed metadata values."""
        if project_name is not None:
            self._project_name = project_name
        if node_name is not None:
            self._node_name = node_name
            self.query_one("#meta-node", Static).update(f"Node: {self._node_name}")
        if tags is not None:
            self._tags = tags
            self.query_one("#meta-tags", Static).update(self._tags_line())

    def _tags_line(self) -> str:
        if self._tags:
            return "Tags: " + "  ".join(self._tags)
        return "Tags: (none)"


class ReconciliationPanel(Widget):
    """Displays Layer 2 Arbitrator contradiction summary in an interactive table.

    Hidden until ``show_results()`` is called.  Columns are initialised in
    ``on_mount()`` so the ``DataTable`` is ready before any data arrives.
    """

    DEFAULT_CSS = """
    ReconciliationPanel {
        height: auto;
        padding: 1 2 0 2;
        display: none;
        border-top: solid $warning;
        background: $background-darken-1;
    }
    ReconciliationPanel.-visible {
        display: block;
    }
    ReconciliationPanel .recon-title {
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    #recon-table {
        height: auto;
        max-height: 12;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("⚖  Reconciliation Summary", classes="recon-title")
        yield DataTable(id="recon-table", show_cursor=True)

    def on_mount(self) -> None:
        table = self.query_one("#recon-table", DataTable)
        table.add_columns("#", "Dimension A", "Dimension B", "Description")

    def show_results(self, contradictions: List[dict]) -> None:
        """Populate the table with Arbitrator contradictions and reveal the panel."""
        table = self.query_one("#recon-table", DataTable)
        table.clear()

        if not contradictions:
            table.add_row("—", "(none)", "(none)", "No contradictions detected.")
        else:
            for i, c in enumerate(contradictions, start=1):
                dim_a = c.get("dimension_a", "?")
                dim_b = c.get("dimension_b", "?")
                desc = c.get("description", "")
                table.add_row(str(i), dim_a, dim_b, desc)

        self.add_class("-visible")


class ArbitrationStatusBar(Widget):
    """Shows real-time ``ArbitratorEngine`` status below the dimension list.

    Hidden until the first ``update_status()`` call.  Stays visible after
    ``COMPLETE`` or ``FAILED`` so the outcome is readable without reopening
    a modal.

    ``status`` is typed ``object`` to keep this widget free of pipeline-layer
    imports; ``getattr(status, "value", str(status))`` extracts the string
    value at runtime from any ``ArbitrationStatus`` instance.
    """

    DEFAULT_CSS = """
    ArbitrationStatusBar {
        height: auto;
        padding: 0 2;
        display: none;
        border-top: solid $primary;
        background: $background-darken-1;
    }
    ArbitrationStatusBar.-active {
        display: block;
    }
    ArbitrationStatusBar .arb-label {
        color: $text;
        text-style: italic;
    }
    ArbitrationStatusBar .arb-label.-processing  { color: $warning; }
    ArbitrationStatusBar .arb-label.-rate-limited { color: $error;   }
    ArbitrationStatusBar .arb-label.-complete     { color: $success; }
    ArbitrationStatusBar .arb-label.-failed       { color: $error;   }
    """

    _ICONS: Dict[str, str] = {
        "PROCESSING":   "⏳",
        "RATE_LIMITED": "⏸",
        "COMPLETE":     "✓",
        "FAILED":       "✗",
    }

    def compose(self) -> ComposeResult:
        yield Static("", id="arb-status-label", classes="arb-label")

    def update_status(self, status: object, detail: str) -> None:
        """Reflect the latest ``ArbitrationStatus`` in the label and CSS class."""
        status_value: str = getattr(status, "value", str(status))
        icon = self._ICONS.get(status_value, "⚖")

        label = self.query_one("#arb-status-label", Static)
        label.update(f"{icon}  Arbitration: {status_value} — {detail}")

        for cls in ("-processing", "-rate-limited", "-complete", "-failed"):
            label.remove_class(cls)
        label.add_class(f"-{status_value.lower().replace('_', '-')}")

        self.add_class("-active")


class PipelineView(Widget):
    """Right pane: metadata cluster + 12 dimension rows + reconciliation panel.

    Emits ``CitationJumpRequested`` when an ``IssueFinding`` is selected.
    Exposes ``update_dimension()`` as the primary public API for the pipeline
    orchestrator to push state changes.
    """

    DEFAULT_CSS = """
    PipelineView {
        width: 70%;
        height: 100%;
    }

    #dimension-scroll {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Keyed by ReviewDimensionEnum for O(1) lookups.
        self._rows: Dict[ReviewDimensionEnum, DimensionRow] = {}
        # All active findings for citation jump support.
        self._findings: List[IssueFinding] = []

    # ── Compose ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield MetadataCluster(id="metadata-cluster")

        with ScrollableContainer(id="dimension-scroll"):
            for dim in ReviewDimensionEnum:
                row = DimensionRow(
                    dimension=dim,
                    id=self._dim_row_id(dim),
                )
                self._rows[dim] = row
                yield row

        yield ArbitrationStatusBar(id="arbitration-status-bar")
        yield ReconciliationPanel(id="reconciliation-panel")

    # ── Public API ────────────────────────────────────────────────────────────

    def update_dimension(
        self,
        dimension: ReviewDimensionEnum,
        state: TaskState,
        error: Optional[str] = None,
    ) -> None:
        """Push a new task state into the matching DimensionRow.

        Called by the pipeline orchestrator callback (``on_state_change``).
        """
        row = self._rows.get(dimension)
        if row is not None:
            row.update_state(state, error)

    def update_metadata(
        self,
        project_name: Optional[str] = None,
        node_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Forward metadata updates to the MetadataCluster widget."""
        self.query_one("#metadata-cluster", MetadataCluster).update_metadata(
            project_name=project_name,
            node_name=node_name,
            tags=tags,
        )

    def show_reconciliation(self, contradictions: List[dict]) -> None:
        """Make the ReconciliationPanel visible with Arbitrator results."""
        self.query_one("#reconciliation-panel", ReconciliationPanel).show_results(
            contradictions
        )

    def show_arbitration_status(self, status: object, detail: str) -> None:
        """Forward an ArbitrationStatus update to the ArbitrationStatusBar."""
        self.query_one("#arbitration-status-bar", ArbitrationStatusBar).update_status(
            status, detail
        )

    def load_findings(self, findings: List[IssueFinding]) -> None:
        """Register the current set of IssueFinding objects for navigation.

        Calling this after Layer 1 completion enables keyboard-driven citation
        jumps via ``select_finding()``.
        """
        self._findings = list(findings)

    def select_finding(self, finding: IssueFinding) -> None:
        """Emit a ``CitationJumpRequested`` for the first citation of *finding*.

        If the finding has no citations, this is a no-op (nothing to jump to).
        """
        if not finding.citations:
            return
        citation = finding.citations[0]
        self.post_message(
            CitationJumpRequested(
                file_path=citation.file_path,
                line_start=citation.line_start,
                line_end=citation.line_end,
            )
        )

    def get_dimension_rows(self) -> Dict[ReviewDimensionEnum, DimensionRow]:
        """Return the internal rows dict (used by tests for introspection)."""
        return dict(self._rows)

    # ── Keyboard navigation ───────────────────────────────────────────────────

    def action_jump_to_finding(self, index: int) -> None:
        """Jump to finding at *index* in the current findings list (0-based)."""
        if 0 <= index < len(self._findings):
            self.select_finding(self._findings[index])

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _dim_row_id(dim: ReviewDimensionEnum) -> str:
        """Stable CSS id for a DimensionRow, e.g. ``dim-row-architecture``."""
        return f"dim-row-{dim.value.lower()}"
