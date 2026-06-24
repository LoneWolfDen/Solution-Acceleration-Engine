"""PipelineView — right split pane (70% width).

Renders the Active Pipeline: metadata cluster, all 12 dimension status rows,
the reconciliation panel, and (after Layer 1 completion) the
FindingsAnnotationPanel with annotation indicators.

Layout (vertical, inside a 70%-wide pane)
------------------------------------------
┌──────────────────────────────────────────────────────────────────┐
│  📦 Metadata Cluster                                             │
├──────────────────────────────────────────────────────────────────┤
│  ┌ Dimension Status ─────────────────────────────────────────┐  │
│  │  Intent      ○ PENDING                                     │  │
│  │  …                                                          │  │
│  └────────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│  Reconciliation Panel (hidden until Layer 2 complete)            │
├──────────────────────────────────────────────────────────────────┤
│  📋 Findings Annotation Panel (hidden until Layer 1 complete)    │
│     ✏ [RED] Risk: Insufficient risk register…  ▶ expand         │
│       [AI Base]    original text…                                │
│       [User Override] amended text…                              │
│       Rationale: …                                               │
└──────────────────────────────────────────────────────────────────┘

FindingEditRequested bubbles up from AnnotatedFindingRow through this widget
to ContextaApp, which opens EditFindingModal and calls back with the result.
AnnotationApplied is handled by ContextaApp which calls
pipeline_view.refresh_annotation() to update the row in-place.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Label, Static

from contexta.models.enums import ReviewDimensionEnum
from contexta.models.findings import IssueFinding
from contexta.tui.messages import (
    CitationJumpRequested,
    DimensionStateChanged,
    FindingEditRequested,
    TaskState,
)
from contexta.tui.widgets.dimension_row import DimensionRow

if TYPE_CHECKING:
    from contexta.models.findings import UserAnnotation
    from contexta.models.payloads import ReviewNodePayload


# ── MetadataCluster ───────────────────────────────────────────────────────────


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


# ── ReconciliationPanel ───────────────────────────────────────────────────────


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


# ── AnnotatedFindingRow ───────────────────────────────────────────────────────


class AnnotatedFindingRow(Widget):
    """Single finding row with annotation indicator and toggle expansion.

    Visual structure
    ----------------
    Header (always visible):
        ✏  [RED] Risk: Insufficient risk register coverage…  ▶ expand
        ^   ^     ^     ^truncated summary                   ^hint

    Expanded panel (toggle on click or Enter):
        [AI Base]
            Original AI-produced detail text…
        [User Override]       ← only when annotation exists
            User's amended value
            Rationale: explanation text

    Key bindings
    ------------
    ``i``   — open EditFindingModal to add or replace an annotation.
    Enter   — toggle the expansion panel.
    """

    BINDINGS = [("i", "annotate", "Annotate")]

    DEFAULT_CSS = """
    AnnotatedFindingRow {
        height: auto;
        padding: 0 1;
        border-bottom: solid $background-darken-2;
    }
    AnnotatedFindingRow:focus {
        background: $surface;
    }
    AnnotatedFindingRow .ann-header-line {
        height: 2;
        color: $text;
        padding: 0 1;
    }
    AnnotatedFindingRow .ann-tree {
        padding: 0 2 1 4;
        display: none;
        background: $background-darken-1;
    }
    AnnotatedFindingRow .tree-section-base {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }
    AnnotatedFindingRow .tree-section-override {
        text-style: bold;
        color: $warning;
        margin-top: 1;
    }
    AnnotatedFindingRow .tree-content {
        color: $text;
        margin-left: 2;
    }
    AnnotatedFindingRow .tree-rationale {
        color: $text-muted;
        text-style: italic;
        margin-left: 2;
    }
    """

    def __init__(
        self,
        index: int,
        finding: IssueFinding,
        annotation: Optional["UserAnnotation"],
        payload_dim: ReviewDimensionEnum,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._index = index
        self._finding = finding
        self._annotation = annotation
        self._payload_dim = payload_dim
        self._expanded = False
        self.can_focus = True

    # ── Compose ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static(self._make_header_line(), id="ann-header-line", classes="ann-header-line")
        with Vertical(id="ann-tree", classes="ann-tree"):
            yield Static("[AI Base]", classes="tree-section-base")
            yield Static(
                self._finding.detail or self._finding.summary,
                id="ann-base-content",
                classes="tree-content",
            )
            yield Static("[User Override]", id="ann-override-label", classes="tree-section-override")
            yield Static(
                "(no annotation applied)",
                id="ann-override-content",
                classes="tree-content",
            )
            yield Static("", id="ann-rationale", classes="tree-rationale")

    def on_mount(self) -> None:
        self._sync_tree_visibility()
        self._sync_override_content()

    # ── Interaction ───────────────────────────────────────────────────────────

    def on_click(self) -> None:
        """Toggle the expansion panel."""
        self._expanded = not self._expanded
        self._sync_tree_visibility()
        self.query_one("#ann-header-line", Static).update(self._make_header_line())

    def action_annotate(self) -> None:
        """Post FindingEditRequested to open the annotation modal."""
        self.post_message(
            FindingEditRequested(
                finding_index=self._index,
                dimension=self._payload_dim,
                base_value=self._finding.summary,
                detail=self._finding.detail or "",
            )
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh_annotation(self, annotation: "UserAnnotation") -> None:
        """Update the row after a new annotation is applied.

        Called by ``FindingsAnnotationPanel.refresh_annotation()`` which is
        itself called by ``ContextaApp`` after the DB write succeeds.
        """
        self._annotation = annotation
        self.query_one("#ann-header-line", Static).update(self._make_header_line())
        self._sync_override_content()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_header_line(self) -> str:
        icon = "✏ " if self._annotation else "  "
        conf = self._finding.confidence.value
        dim = self._finding.dimension.value
        summary = self._finding.summary[:60]
        arrow = "▼" if self._expanded else "▶"
        return f"{icon}[{conf}] {dim}: {summary}  {arrow}"

    def _sync_tree_visibility(self) -> None:
        self.query_one("#ann-tree").display = self._expanded

    def _sync_override_content(self) -> None:
        if self._annotation:
            self.query_one("#ann-override-content", Static).update(
                self._annotation.amended_value
            )
            self.query_one("#ann-rationale", Static).update(
                f"Rationale: {self._annotation.rationale}"
            )
        else:
            self.query_one("#ann-override-content", Static).update(
                "(no annotation applied)"
            )
            self.query_one("#ann-rationale", Static).update("")


# ── FindingsAnnotationPanel ───────────────────────────────────────────────────


class FindingsAnnotationPanel(Widget):
    """Scrollable panel listing all findings with annotation indicators.

    Hidden until ``load_findings()`` is called with completed payloads.
    Each row is an ``AnnotatedFindingRow`` that emits ``FindingEditRequested``
    when the user presses [i], and toggles an inline tree on click.

    ``refresh_annotation()`` updates a specific row in-place after an
    annotation is persisted, without reloading the full list.
    """

    DEFAULT_CSS = """
    FindingsAnnotationPanel {
        height: auto;
        max-height: 22;
        display: none;
        border-top: solid $accent-darken-2;
    }
    FindingsAnnotationPanel.-visible {
        display: block;
    }
    FindingsAnnotationPanel .findings-panel-title {
        text-style: bold;
        color: $accent;
        padding: 1 2 0 2;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Keyed by (dimension, finding_index) for O(1) refresh lookups.
        self._row_map: Dict[Tuple[ReviewDimensionEnum, int], AnnotatedFindingRow] = {}

    def compose(self) -> ComposeResult:
        yield Static(
            "📋 Findings  [i] = annotate  [click] = expand",
            classes="findings-panel-title",
        )
        yield ScrollableContainer(id="findings-scroll")

    def load_findings(self, payloads: List["ReviewNodePayload"]) -> None:
        """Populate the panel from all completed dimension payloads.

        Called once after all 12 Layer 1 dimensions reach COMPLETE.  Clears
        any previous rows, then mounts one ``AnnotatedFindingRow`` per finding
        across all payloads.

        Parameters
        ----------
        payloads:
            Completed ``ReviewNodePayload`` objects (up to 12).  ``base_findings``
            is used when populated; falls back to ``findings`` for compatibility.
        """
        scroll = self.query_one("#findings-scroll", ScrollableContainer)

        # Detach existing rows before rebuilding.
        for child in list(scroll.children):
            child.remove()
        self._row_map.clear()

        rows: List[AnnotatedFindingRow] = []
        for payload in payloads:
            source = payload.base_findings if payload.base_findings else payload.findings
            for local_idx, finding in enumerate(source):
                annotation = next(
                    (
                        a
                        for a in payload.user_annotations
                        if a.finding_index == local_idx
                    ),
                    None,
                )
                row_id = f"ann-row-{payload.dimension.value.lower()}-{local_idx}"
                row = AnnotatedFindingRow(
                    index=local_idx,
                    finding=finding,
                    annotation=annotation,
                    payload_dim=payload.dimension,
                    id=row_id,
                )
                self._row_map[(payload.dimension, local_idx)] = row
                rows.append(row)

        if rows:
            scroll.mount(*rows)
            self.add_class("-visible")

    def refresh_annotation(
        self,
        dimension: ReviewDimensionEnum,
        finding_index: int,
        annotation: "UserAnnotation",
    ) -> None:
        """Update a single row's annotation display in-place.

        Called by ``PipelineView.refresh_annotation()`` after ContextaApp
        persists the observation and updates the in-memory payload.

        Parameters
        ----------
        dimension:
            The dimension of the annotated payload.
        finding_index:
            Zero-based index of the finding within the payload.
        annotation:
            The newly applied ``UserAnnotation``.
        """
        row = self._row_map.get((dimension, finding_index))
        if row is not None:
            row.refresh_annotation(annotation)


# ── PipelineView ──────────────────────────────────────────────────────────────
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
    """Right pane: metadata cluster + 12 dimension rows + reconciliation panel
    + findings annotation panel.

    Emits ``CitationJumpRequested`` when an ``IssueFinding`` is selected.
    ``FindingEditRequested`` bubbles up from ``AnnotatedFindingRow`` through
    this widget to ``ContextaApp`` without interception.

    Public API
    ----------
    update_dimension()          — push task state changes from the orchestrator.
    update_metadata()           — refresh the metadata cluster.
    show_reconciliation()       — display Layer 2 contradiction results.
    load_annotated_findings()   — populate the findings annotation panel.
    refresh_annotation()        — update a single row after annotation save.
    load_findings()             — register findings for citation navigation.
    select_finding()            — emit a CitationJumpRequested for a finding.
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
        self._rows: Dict[ReviewDimensionEnum, DimensionRow] = {}
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
        yield FindingsAnnotationPanel(id="findings-panel")

    # ── Public API ────────────────────────────────────────────────────────────

    def update_dimension(
        self,
        dimension: ReviewDimensionEnum,
        state: TaskState,
        error: Optional[str] = None,
    ) -> None:
        """Push a new task state into the matching DimensionRow."""
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

    def load_annotated_findings(
        self, payloads: List["ReviewNodePayload"]
    ) -> None:
        """Populate the FindingsAnnotationPanel from all completed payloads.
    def show_arbitration_status(self, status: object, detail: str) -> None:
        """Forward an ArbitrationStatus update to the ArbitrationStatusBar."""
        self.query_one("#arbitration-status-bar", ArbitrationStatusBar).update_status(
            status, detail
        )

    def load_findings(self, findings: List[IssueFinding]) -> None:
        """Register the current set of IssueFinding objects for navigation.

        Call this after all 12 Layer 1 dimensions reach COMPLETE state so
        the annotation panel is populated with AI findings ready for review.

        Parameters
        ----------
        payloads:
            All completed ``ReviewNodePayload`` objects from the orchestrator.
        """
        self.query_one("#findings-panel", FindingsAnnotationPanel).load_findings(
            payloads
        )

    def refresh_annotation(
        self,
        dimension: ReviewDimensionEnum,
        finding_index: int,
        annotation: "UserAnnotation",
    ) -> None:
        """Update a single finding row after an annotation is saved.

        Called by ``ContextaApp`` after the observation is persisted to
        KnowledgeMemory and the in-memory payload is updated.
        """
        self.query_one("#findings-panel", FindingsAnnotationPanel).refresh_annotation(
            dimension, finding_index, annotation
        )

    def load_findings(self, findings: List[IssueFinding]) -> None:
        """Register the current set of IssueFinding objects for navigation."""
        self._findings = list(findings)

    def select_finding(self, finding: IssueFinding) -> None:
        """Emit a ``CitationJumpRequested`` for the first citation of *finding*."""
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
        return f"dim-row-{dim.value.lower()}"
