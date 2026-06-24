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
from textual.widgets import Label, Static

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
    """Displays Layer 2 Arbitrator contradiction summary.

    Hidden until ``show_results()`` is called.
    """

    DEFAULT_CSS = """
    ReconciliationPanel {
        height: auto;
        padding: 1 2;
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
    }
    ReconciliationPanel .recon-body {
        color: $text;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("⚖  Reconciliation Summary", classes="recon-title")
        yield Static("(no results yet)", id="recon-body", classes="recon-body")

    def show_results(self, contradictions: List[dict]) -> None:
        """Render the Arbitrator contradiction list and make the panel visible."""
        if not contradictions:
            body = "No contradictions detected across all 12 dimensions."
        else:
            lines: List[str] = []
            for i, c in enumerate(contradictions, start=1):
                dim_a = c.get("dimension_a", "?")
                dim_b = c.get("dimension_b", "?")
                desc = c.get("description", "")
                lines.append(f"  {i}. [{dim_a}] ↔ [{dim_b}]: {desc}")
            body = "\n".join(lines)

        self.query_one("#recon-body", Static).update(body)
        self.add_class("-visible")


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
        """Jump to finding at index in the current findings list (0-based)."""
        if 0 <= index < len(self._findings):
            self.select_finding(self._findings[index])

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _dim_row_id(dim: ReviewDimensionEnum) -> str:
        """Stable CSS id for a DimensionRow, e.g. ``dim-row-architecture``."""
        return f"dim-row-{dim.value.lower()}"
