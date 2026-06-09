"""PipelineView widget — right pane containing the 12-dimension status cards.

Right pane (70% width):
- ``MetadataCluster``: project name, tags, active node name.
- 12 × ``DimensionRow``: one per ``ReviewDimensionEnum``.
- ``ReconciliationPanel``: arbitrator output (visible post-Layer 2 only).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Label, Static

from ...models.enums import ReviewDimensionEnum
from ...pipeline.dimension_runner import TaskState
from ..messages import DimensionStateChanged
from .dimension_row import DimensionRow


class ReconciliationPanel(Static):
    """Shows Layer 2 Arbitrator contradictions after Compare completes."""

    DEFAULT_CSS = """
    ReconciliationPanel {
        border: solid $warning;
        padding: 1;
        height: auto;
        display: none;
    }
    ReconciliationPanel .reconcile-title {
        text-style: bold;
        color: $warning;
    }
    ReconciliationPanel .contradiction {
        padding: 0 2;
        color: $text;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._contradictions: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Label("⚖ Reconciliation Summary", classes="reconcile-title")
        yield Label("", id="reconcile-body")

    def show_results(self, contradictions: list[dict]) -> None:
        """Populate and display the reconciliation panel."""
        self._contradictions = contradictions
        body = self.query_one("#reconcile-body", Label)
        if not contradictions:
            body.update("No contradictions detected.")
        else:
            lines = []
            for c in contradictions:
                a = c.get("dimension_a", "?")
                b = c.get("dimension_b", "?")
                desc = c.get("description", "")
                lines.append(f"• [{a}] ↔ [{b}]: {desc}")
            body.update("\n".join(lines))
        self.display = True


class PipelineView(Static):
    """Right pane widget containing dimension status rows and reconciliation panel.

    Parameters
    ----------
    project_name:
        Display name of the active project.
    node_name:
        Name of the currently active node.
    global_tags:
        Project tag list shown in the metadata cluster.
    """

    DEFAULT_CSS = """
    PipelineView {
        width: 70%;
        height: 100%;
    }
    PipelineView .meta-cluster {
        background: $panel;
        padding: 0 1;
        height: auto;
    }
    PipelineView .meta-label {
        color: $text-muted;
    }
    PipelineView .dimensions-title {
        background: $panel;
        padding: 0 1;
        text-style: bold;
    }
    """

    def __init__(
        self,
        project_name: str = "",
        node_name: str = "",
        global_tags: list | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._project_name = project_name
        self._node_name = node_name
        self._global_tags: list = global_tags or []

    def compose(self) -> ComposeResult:
        # Metadata cluster
        with Vertical(classes="meta-cluster"):
            yield Label(
                f"Project: {self._project_name}  |  Node: {self._node_name}",
                id="meta-header",
            )
            tags_str = "  ".join(f"#{t}" for t in self._global_tags)
            yield Label(f"Tags: {tags_str}" if tags_str else "Tags: (none)", id="meta-tags")

        yield Label("─── 12-Dimension Review ───", classes="dimensions-title")

        with VerticalScroll(id="dimensions-scroll"):
            for dim in ReviewDimensionEnum:
                yield DimensionRow(dim, id=f"row-{dim.name}")
            yield ReconciliationPanel(id="reconciliation-panel")

    def update_dimension(
        self,
        dimension: ReviewDimensionEnum,
        state: TaskState,
        error: str | None = None,
    ) -> None:
        """Update a specific dimension row's display state."""
        row = self.query_one(f"#row-{dimension.name}", DimensionRow)
        row.update_state(state, error)

    def update_node_info(self, project_name: str, node_name: str) -> None:
        """Refresh the metadata cluster header."""
        self._project_name = project_name
        self._node_name = node_name
        try:
            header = self.query_one("#meta-header", Label)
            header.update(f"Project: {project_name}  |  Node: {node_name}")
        except Exception:
            pass

    def show_reconciliation(self, contradictions: list[dict]) -> None:
        panel = self.query_one("#reconciliation-panel", ReconciliationPanel)
        panel.show_results(contradictions)

    # ── Message handler ───────────────────────────────────────────────────────

    def on_dimension_state_changed(self, message: DimensionStateChanged) -> None:
        self.update_dimension(message.dimension, message.state, message.error)
