"""ArtifactView — left split pane (30% width).

Responsibilities
----------------
- Display a ``ListView`` of ingested MCP artifacts (filename + line count).
- Show a scrollable ``RichLog`` file-content preview when an artifact is
  selected from the list.
- Handle ``CitationJumpRequested`` messages by:
    1. Switching the preview to the referenced ``file_path`` if needed.
    2. Scrolling the log so ``line_start`` is visible.
    3. Applying a distinct highlight style across ``[line_start, line_end]``.
  The highlight is cleared when a new jump is requested or the user selects
  a different file.

Layout (vertical, inside a 30%-wide pane)
------------------------------------------
┌──────────────────────────┐
│  FILE BROWSER            │  ← ListView  (id="artifact-list")
│  ► file_a.md  (120 lines)│
│    file_b.docx (45 lines)│
│    file_c.pdf  (89 lines)│
├──────────────────────────┤
│  [preview panel]         │  ← RichLog  (id="artifact-preview")
│  ...file content...      │
└──────────────────────────┘
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView, RichLog

from contexta.tui.messages import ArtifactIngested, CitationJumpRequested

if TYPE_CHECKING:
    from contexta.mcp.artifact_registry import ArtifactRegistry, IngestedArtifact

# Highlight style applied to cited lines in the preview.
_HIGHLIGHT_STYLE = "bold white on dark_orange3"
# Default style for non-highlighted lines.
_NORMAL_STYLE = ""


class ArtifactView(Widget):
    """Left pane: file browser + scrollable content preview with citation jump."""

    DEFAULT_CSS = """
    ArtifactView {
        width: 30%;
        height: 100%;
        border-right: solid $accent;
    }

    #artifact-list {
        height: 30%;
        border-bottom: solid $accent-darken-2;
    }

    #artifact-preview {
        height: 70%;
    }
    """

    # Reactive: currently displayed file path (drives re-render on switch).
    _active_path: reactive[Optional[str]] = reactive(None)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # file_path → IngestedArtifact
        self._artifacts: Dict[str, "IngestedArtifact"] = {}
        # Active citation highlight range (1-indexed, inclusive).
        self._highlight_start: Optional[int] = None
        self._highlight_end: Optional[int] = None

    # ── Compose ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield ListView(id="artifact-list")
        yield RichLog(id="artifact-preview", highlight=False, markup=False, wrap=False)

    # ── Public API ────────────────────────────────────────────────────────────

    def populate(self, registry: "ArtifactRegistry") -> None:
        """Batch-populate the browser from a complete ArtifactRegistry snapshot.

        Replaces any existing entries.  Call this once from ``ContextaApp.on_mount``
        (via ``call_after_refresh``) to fill the sidebar from pre-loaded artifacts.
        Subsequent single-file additions should use ``register_artifact()``.
        """
        self._artifacts = {a.file_path: a for a in registry.all()}
        self._refresh_list()

    def register_artifact(self, artifact: "IngestedArtifact") -> None:
        """Add or update an artifact entry in the browser list and registry.

        Called externally (e.g. by ``MainScreen``) after the MCP client
        ingests a file.  Posts ``ArtifactIngested`` so other widgets can react.
        """
        self._artifacts[artifact.file_path] = artifact
        self._refresh_list()
        self.post_message(ArtifactIngested(artifact))

    # ── Internal rendering ────────────────────────────────────────────────────

    def _refresh_list(self) -> None:
        """Rebuild the ListView from the current artifact registry."""
        list_view = self.query_one("#artifact-list", ListView)
        list_view.clear()
        for path, artifact in self._artifacts.items():
            label_text = f"{artifact.file_path}  ({artifact.line_count} lines)"
            list_view.append(ListItem(Label(label_text), id=self._path_to_id(path)))

    def _render_preview(
        self,
        path: str,
        highlight_start: Optional[int] = None,
        highlight_end: Optional[int] = None,
    ) -> None:
        """Render the file content into the RichLog, applying a highlight band.

        ``highlight_start`` and ``highlight_end`` are 1-indexed, inclusive.
        Lines outside that range are rendered with the normal style.
        Lines inside are rendered with ``_HIGHLIGHT_STYLE``.
        """
        log = self.query_one("#artifact-preview", RichLog)
        log.clear()

        artifact = self._artifacts.get(path)
        if artifact is None:
            log.write(Text("(file not loaded)", style="dim italic"))
            return

        lines = artifact.content.splitlines()
        for idx, raw_line in enumerate(lines, start=1):
            text = Text(f"{idx:>4}  {raw_line}")
            if (
                highlight_start is not None
                and highlight_end is not None
                and highlight_start <= idx <= highlight_end
            ):
                text.stylize(_HIGHLIGHT_STYLE)
            log.write(text, scroll_end=False)

    def _scroll_to_line(self, line_number: int) -> None:
        """Scroll the preview so that ``line_number`` (1-indexed) is in view.

        Uses ``RichLog.scroll_to`` with ``y`` calculated from the line index.
        Each rendered line is exactly 1 cell tall in the default terminal font.
        """
        log = self.query_one("#artifact-preview", RichLog)
        # line_number is 1-indexed; scroll_to y is 0-indexed row offset.
        target_y = max(0, line_number - 1)
        log.scroll_to(y=target_y, animate=False)

    @staticmethod
    def _path_to_id(path: str) -> str:
        """Convert a file path to a CSS-safe widget id."""
        # Replace path separators and dots with hyphens; strip leading hyphens.
        safe = path.replace("/", "-").replace(".", "-").replace("_", "-")
        return f"artifact-{safe.lstrip('-')}"

    # ── Event handlers ────────────────────────────────────────────────────────

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """User selected a file in the browser — render its preview."""
        if event.item.id is None:
            return
        # Find the matching artifact by id.
        for path in self._artifacts:
            if self._path_to_id(path) == event.item.id:
                self._active_path = path
                # Clear any prior citation highlight on manual navigation.
                self._highlight_start = None
                self._highlight_end = None
                self._render_preview(path)
                return

    def on_citation_jump_requested(self, event: CitationJumpRequested) -> None:
        """Handle a citation jump from ``PipelineView``.

        Steps:
        1. Switch preview to ``event.file_path`` if not already active.
        2. Re-render with highlight band across ``[line_start, line_end]``.
        3. Scroll so ``line_start`` is visible.
        """
        event.stop()  # Prevent further bubbling — handled here.

        target_path = event.file_path
        self._highlight_start = event.line_start
        self._highlight_end = event.line_end

        # Switch active file if needed.
        self._active_path = target_path

        # Re-render with the new highlight band.
        self._render_preview(target_path, event.line_start, event.line_end)

        # Scroll preview to bring line_start into view.
        self._scroll_to_line(event.line_start)
