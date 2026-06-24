"""MainScreen — master layout screen.

Combines:
- ContextaHeader  (persistent header)
- Horizontal split: ArtifactView (30%) + PipelineView (70%)
- ContextaFooter  (persistent footer with [F] [C] [P] [E] bindings)

All footer key handlers are registered as BINDINGS so Textual dispatches
them through its priority system, guaranteeing a sub-200ms response even on
slow terminals (no polling, pure event-driven).

The CitationJumpRequested message bubbles upward from PipelineView through
this screen.  MainScreen does NOT intercept it — it continues bubbling to
ArtifactView which handles it via ``on_citation_jump_requested``.  Both
widgets are peers inside the Horizontal container, so the message reaches
the App, then re-dispatches down the DOM to ArtifactView.

Layout
------
┌─────────────────────────────────────────────────────────────────┐
│  HEADER: [Project: {name}]  [Node: {name}]          [⚙ Admin]  │
├──────────────────────┬──────────────────────────────────────────┤
│  MCP Artifact View   │  Active Pipeline                         │
│  (left pane, 30%)    │  (right pane, 70%)                       │
│                      │  Metadata Cluster                         │
│  ► file_a.md  (120L) │  ┌ 12 × DimensionRow ─────────────────┐ │
│    file_b.docx (45L) │  │ Intent     ○ PENDING               │ │
│    file_c.pdf  (89L) │  │ Scope      ● RUNNING [━━━━━━━━━━]  │ │
│  [preview panel]     │  │ …                                   │ │
│  ...file content...  │  └────────────────────────────────────┘ │
│                      │  Reconciliation Panel (post Layer 2)     │
├──────────────────────┴──────────────────────────────────────────┤
│  FOOTER: [F] Fork  [C] Compare  [P] Proposal  [E] Export       │
└─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from typing import List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from contexta.tui.widgets.artifact_view import ArtifactView
from contexta.tui.widgets.modals import (
    BlueprintErrorModal,
    CompareBlockingModal,
    ExportConfirmModal,
    ForkNameModal,
    RiskBlockingModal,
)
from contexta.tui.widgets.pipeline_view import PipelineView


# ── PhaseStatusBar ─────────────────────────────────────────────────────────────


class PhaseStatusBar(Static):
    """Thin 1-line bar below the header showing the current review phase.

    Phases: IDLE → REVIEW → COMPLETE
    The bar changes accent colour when the REVIEW phase is active.
    """

    DEFAULT_CSS = """
    PhaseStatusBar {
        height: 1;
        padding: 0 2;
        background: $background-darken-1;
        color: $text-muted;
    }
    PhaseStatusBar.-review {
        background: $success-darken-3;
        color: $success;
        text-style: bold;
    }
    PhaseStatusBar.-complete {
        background: $primary-darken-2;
        color: $primary-lighten-2;
        text-style: bold;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("Phase: IDLE", **kwargs)
        self._phase: str = "IDLE"

    # ── Public API ────────────────────────────────────────────────────────────

    def set_phase(self, phase: str) -> None:
        """Update the displayed phase and apply the matching CSS class.

        Args:
            phase: One of ``"IDLE"``, ``"REVIEW"``, or ``"COMPLETE"``.
        """
        self._phase = phase.upper()
        self.update(f"Phase: {self._phase}")
        self.remove_class("-review", "-complete")
        if self._phase == "REVIEW":
            self.add_class("-review")
        elif self._phase == "COMPLETE":
            self.add_class("-complete")

    @property
    def current_phase(self) -> str:
        """Return the current phase string (read-only)."""
        return self._phase


class MainScreen(Screen):
    """The primary application screen."""

    BINDINGS = [
        Binding("f", "fork",     "[F] Fork Iteration",       show=True,  priority=True),
        Binding("c", "compare",  "[C] Compare",               show=True,  priority=True),
        Binding("p", "proposal", "[P] Run Proposal Generator", show=True,  priority=True),
        Binding("e", "export",   "[E] Export Flat JSON Packet", show=True, priority=True),
        Binding("r", "review",   "[R] Review",                show=True,  priority=True),
        Binding("a", "admin",    "[⚙] Admin Tab",             show=True,  priority=True),
    ]

    DEFAULT_CSS = """
    MainScreen {
        layout: vertical;
    }

    #main-split {
        height: 1fr;
        layout: horizontal;
    }
    """

    def __init__(
        self,
        project_name: str = "Untitled Project",
        node_name: str = "—",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._project_name = project_name
        self._node_name = node_name

    # ── Compose ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield PhaseStatusBar(id="phase-status-bar")
        with Horizontal(id="main-split"):
            yield ArtifactView(id="artifact-view")
            yield PipelineView(id="pipeline-view")
        yield Footer()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Set initial header title and metadata cluster values."""
        self.title = f"Contexta  ·  {self._project_name}"
        self.sub_title = f"Node: {self._node_name}"
        pipeline = self.query_one("#pipeline-view", PipelineView)
        pipeline.update_metadata(
            project_name=self._project_name,
            node_name=self._node_name,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def artifact_view(self) -> ArtifactView:
        return self.query_one("#artifact-view", ArtifactView)

    @property
    def pipeline_view(self) -> PipelineView:
        return self.query_one("#pipeline-view", PipelineView)

    def update_node_name(self, node_name: str) -> None:
        """Update the header and metadata cluster after a fork."""
        self._node_name = node_name
        self.sub_title = f"Node: {node_name}"
        self.pipeline_view.update_metadata(node_name=node_name)

    def set_phase(self, phase: str) -> None:
        """Update the PhaseStatusBar to reflect the new pipeline phase."""
        self.query_one("#phase-status-bar", PhaseStatusBar).set_phase(phase)

    # ── Footer actions ────────────────────────────────────────────────────────
    # Each action_ method completes synchronously or opens a modal within the
    # 200ms window mandated by Requirement 10.5.  Heavy async work (LLM calls,
    # DB writes) is delegated via the App instance so this screen stays thin.

    def action_fork(self) -> None:
        """[F] Open the fork-name modal; on confirm delegate to the App."""
        def _on_result(name: str | bool) -> None:
            if isinstance(name, str) and name:
                # handle_fork is synchronous and this callback is invoked on
                # the main asyncio thread — a direct call is both correct and
                # safe.  call_from_thread is reserved for background threads
                # calling into the event loop and must NOT be used here.
                self.app.handle_fork(name)  # type: ignore[attr-defined]

        self.app.push_screen(ForkNameModal(), callback=_on_result)

    def action_compare(self) -> None:
        """[C] Check all dimensions complete; open Compare or blocking modal."""
        # Delegate completion check to the App which owns the orchestrator.
        self.app.handle_compare()  # type: ignore[attr-defined]

    def action_proposal(self) -> None:
        """[P] Stub — Proposal Generator is out of MVP scope."""
        self.app.notify(
            "Proposal Generator is not yet available in this release.",
            title="[P] Not Implemented",
            severity="warning",
        )

    def action_export(self) -> None:
        """[E] Open export-path modal; on confirm delegate to the App."""
        default = getattr(self.app, "export_path", "/exports/contexta_export.json")

        def _on_result(path: str | bool) -> None:
            if isinstance(path, str) and path:
                self.app.handle_export(path)  # type: ignore[attr-defined]

        self.app.push_screen(ExportConfirmModal(default_path=default), callback=_on_result)

    def action_admin(self) -> None:
        """[A] Switch to the Admin screen."""
        self.app.push_screen("admin")

    def action_review(self) -> None:
        """[R] Activate Review phase — delegates to ContextaApp.action_review()."""
        # ContextaApp owns the PhaseStatusBar update logic so that any screen
        # (not just MainScreen) can trigger a phase transition consistently.
        self.app.action_review()  # type: ignore[attr-defined]

    # ── Modal helpers (called by App) ─────────────────────────────────────────

    def show_compare_blocking(self, incomplete: List[str]) -> None:
        """Open the compare-blocking modal listing incomplete dimensions."""
        self.app.push_screen(CompareBlockingModal(incomplete=incomplete))

    def show_risk_blocking(self, alerts: list, callback) -> None:
        """Open the risk advisory modal; ``callback`` receives True/False."""
        self.app.push_screen(RiskBlockingModal(alerts=alerts), callback=callback)

    def show_blueprint_error(self) -> None:
        """Open the no-active-blueprint error modal."""
        self.app.push_screen(BlueprintErrorModal())
