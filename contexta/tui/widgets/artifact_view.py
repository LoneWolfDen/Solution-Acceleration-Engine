"""ArtifactView widget — left pane MCP file browser with citation jump support.

Left pane (30% width):
- ``ListView`` of ingested files showing filename and line count.
- ``TextLog`` for scrollable file content preview.

Handles ``CitationJumpRequested`` messages: scrolls the preview to
``line_start`` and visually marks the target range (Requirement 10.9).
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, ListItem, ListView, Static, TextLog

from ...mcp.artifact_registry import ArtifactRegistry, IngestedArtifact
from ..messages import ArtifactIngested, CitationJumpRequested


class ArtifactView(Static):
    """Left pane widget displaying ingested source files and a content preview.

    Parameters
    ----------
    registry:
        Shared ``ArtifactRegistry`` instance from ``ContextaApp``.
    """

    DEFAULT_CSS = """
    ArtifactView {
        width: 30%;
        height: 100%;
        border-right: solid $panel;
    }
    ArtifactView .pane-title {
        background: $panel;
        padding: 0 1;
        color: $text;
        text-style: bold;
    }
    ArtifactView ListView {
        height: 40%;
        border-bottom: solid $panel-darken-1;
    }
    ArtifactView TextLog {
        height: 1fr;
    }
    """

    def __init__(self, registry: ArtifactRegistry, **kwargs) -> None:
        super().__init__(**kwargs)
        self._registry = registry
        self._current_file: str | None = None

    def compose(self) -> ComposeResult:
        yield Label("📂 Artifacts", classes="pane-title")
        yield ListView(id="artifact-list")
        yield Label("Preview", classes="pane-title")
        yield TextLog(id="artifact-preview", highlight=True, markup=False)

    def refresh_list(self) -> None:
        """Rebuild the file list from the current registry state."""
        list_view = self.query_one("#artifact-list", ListView)
        list_view.clear()
        for artifact in self._registry.all():
            name = Path(artifact.file_path).name
            item = ListItem(
                Label(f"{name}  ({artifact.line_count}L)"),
                id=f"artifact-{artifact.file_path.replace('/', '_')}",
            )
            list_view.append(item)

    def _show_preview(self, file_path: str) -> None:
        artifact = self._registry.get(file_path)
        if artifact is None:
            return
        self._current_file = file_path
        preview = self.query_one("#artifact-preview", TextLog)
        preview.clear()
        preview.write(artifact.content)

    # ── Message handlers ──────────────────────────────────────────────────────

    def on_artifact_ingested(self, message: ArtifactIngested) -> None:
        self.refresh_list()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Show content preview when user selects a file."""
        # Derive the file_path from the item's id
        if event.item.id:
            # Reverse the path mangling: replace leading _ with /
            raw = event.item.id.replace("artifact-", "", 1)
            # Restore slashes — find the artifact whose path mangled form matches
            for artifact in self._registry.all():
                mangled = artifact.file_path.replace("/", "_")
                if mangled == raw:
                    self._show_preview(artifact.file_path)
                    break

    def on_citation_jump_requested(self, message: CitationJumpRequested) -> None:
        """Scroll the preview to the requested line range and highlight it."""
        self._show_preview(message.file_path)
        artifact = self._registry.get(message.file_path)
        if artifact is None:
            return

        preview = self.query_one("#artifact-preview", TextLog)
        lines = artifact.content.splitlines()
        # Re-render with highlight markers around the target range
        preview.clear()
        for i, line in enumerate(lines, start=1):
            if message.line_start <= i <= message.line_end:
                preview.write(f"▶ {line}")
            else:
                preview.write(line)
        # Scroll to approximate position (Textual TextLog doesn't expose
        # line-level scroll, so we scroll to the percentage position)
        if len(lines) > 0:
            pct = (message.line_start - 1) / len(lines)
            preview.scroll_to(y=pct * preview.virtual_size.height)
