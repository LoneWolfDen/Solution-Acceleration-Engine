"""ContextaApp — the Textual application root.

Responsibilities
----------------
- Holds the single ``aiosqlite.Connection``, ``ContextaConfig``,
- Holds the single ``aiosqlite.Connection``, ``ContextaConfig``,
  ``ArtifactRegistry``, and ``PromptBlueprintManager``.
- Registers ``MainScreen`` as the default screen and ``AdminScreen`` as a named
  screen accessible via ``push_screen("admin")``.
- Provides ``notify()`` for non-fatal error notifications (timed footer bar).
- Implements high-level action handlers (``handle_fork``, ``handle_compare``,
  ``handle_export``) that are called by ``MainScreen``'s footer action methods.

Design constraint: this module owns no business logic.  It wires together the
pipeline, MCP, and admin layers and delegates all heavy work to those modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding

from contexta.mcp.artifact_registry import ArtifactRegistry
from contexta.tui.messages import CitationJumpRequested, TaskState
from contexta.tui.screens.main_screen import MainScreen

if TYPE_CHECKING:
    # Only imported for type hints; optional at runtime so that the TUI can
    # be launched in environments where the full pipeline is not yet wired.
    import aiosqlite
    from contexta.config import ContextaConfig
    from contexta.config import ContextaConfig
    from contexta.tui.widgets.pipeline_view import PipelineView


class ContextaApp(App):
    """Textual application root for Project Contexta.

    Instantiate with optional config/db parameters; call ``run()`` or
    ``run_async()`` to start the event loop.
    """

    TITLE = "Project Contexta"
    SUB_TITLE = "Deterministic Solution Validation Pipeline"

    # App-level key bindings — act as fallbacks when no Screen binding matches.
    # 'r' is unique to the App: MainScreen propagates it upward to action_review().
    # f/c/p/e/a are shadowed by MainScreen's priority=True bindings while
    # MainScreen is active, but are available as fallbacks on other screens.
    BINDINGS = [
        Binding("f", "fork_iteration",  "Fork Iteration",          show=True),
        Binding("c", "compare",         "Compare",                  show=True),
        Binding("p", "run_proposal",    "Run Proposal Generator",   show=True),
        Binding("e", "export_json",     "Export Flat JSON Packet",  show=True),
        Binding("r", "review",          "Review",                   show=True),
        Binding("a", "admin",           "Admin Tab",                show=True),
    ]

    # Named screens — AdminScreen is imported lazily to avoid circular imports
    # and to keep the startup path fast.
    SCREENS = {}  # populated in on_mount to allow lazy import of AdminScreen

    DEFAULT_CSS = """
    ContextaApp {
        background: $background;
    }
    """

    def __init__(
        self,
        registry: Optional[ArtifactRegistry] = None,
        project_name: str = "Untitled Project",
        node_name: str = "—",
        export_path: str = "/exports",
        db_conn: Optional["aiosqlite.Connection"] = None,
        config: Optional["ContextaConfig"] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.registry: ArtifactRegistry = registry or ArtifactRegistry()
        self.project_name: str = project_name
        self.node_name: str = node_name
        self.export_path: str = export_path
        self._db_conn = db_conn
        self._config = config

        # Orchestrator and blueprint manager are injected after construction
        # (wired by __main__.py after async DB init).
        self._orchestrator = None
        self._blueprint_manager = None
        self._llm_config = None

        # Wire up blueprint manager and LLM config eagerly if prerequisites
        # are available — avoids the need for post-construction injection in
        # the common startup path.
        if db_conn is not None:
            from contexta.admin.blueprint_manager import PromptBlueprintManager
            self._blueprint_manager = PromptBlueprintManager(db_conn)

        if config is not None:
            from contexta.llm.provider import LLMConfig
            self._llm_config = LLMConfig(
                model=config.llm_backend,
                api_key=config.llm_api_key,
                base_url=config.llm_base_url,
            )

    # ── Compose / mount ───────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        # App.compose() yields nothing — the default screen is installed below.
        return iter([])

    def on_mount(self) -> None:
        """Install screens, push the default MainScreen, then populate the sidebar."""
        # Lazy import of AdminScreen to keep the startup critical path clean.
        from contexta.tui.screens.admin_screen import AdminScreen  # noqa: PLC0415

        self.install_screen(
            MainScreen(
                project_name=self.project_name,
                node_name=self.node_name,
            ),
            name="main",
        )
        self.install_screen(AdminScreen(), name="admin")
        self.push_screen("main")
        # Populate the ArtifactView after the first render cycle so that
        # MainScreen's widgets are fully composed and mounted.
        self.call_after_refresh(self._populate_artifact_view)

    def _populate_artifact_view(self) -> None:
        """Batch-populate the ArtifactView with current ArtifactRegistry contents.

        Called via ``call_after_refresh`` from ``on_mount`` so that the widget
        tree is fully composed before the query runs.  Safe to call when the
        registry is empty (no-op).
        """
        if not self.registry.all():
            return
        try:
            from contexta.tui.widgets.artifact_view import ArtifactView

            av = self.query_one("#artifact-view", ArtifactView)
            av.populate(self.registry)
        except Exception:
            # Widget not yet mounted or query missed — non-fatal; registry
            # entries can be added later via register_artifact().
            pass

    # ── CitationJump routing ──────────────────────────────────────────────────

    def on_citation_jump_requested(self, event: CitationJumpRequested) -> None:
        """Route CitationJumpRequested from PipelineView to ArtifactView.

        Both widgets are siblings inside MainScreen's Horizontal container.
        The message bubbles up from PipelineView to the App; we forward it
        down to ArtifactView by calling its handler directly.
        """
        try:
            from contexta.tui.widgets.artifact_view import ArtifactView

            av = self.query_one("#artifact-view", ArtifactView)
            av.on_citation_jump_requested(event)
        except Exception:
            # ArtifactView may not be mounted (e.g. during tests with minimal
            # app setup).  Fail silently — citation jumps are non-fatal.
            pass

    # ── High-level action handlers ────────────────────────────────────────────

    def handle_fork(self, name: str) -> None:
        """Create a forked node and update the header.

        The actual DB write happens in the pipeline layer.  Here we update
        the TUI to reflect the new node name immediately.
        """
        self.node_name = name
        try:
            main = self.get_screen("main")
            from contexta.tui.screens.main_screen import MainScreen as MS

            if isinstance(main, MS):
                main.update_node_name(name)
        except Exception as exc:
            self.notify(f"Fork display update failed: {exc}", severity="warning")

    def handle_compare(self) -> None:
        """Check orchestrator readiness, then trigger Layer 2 comparison."""
        if self._orchestrator is None:
            self.notify(
                "No active pipeline. Start a review first.",
                severity="warning",
                title="Compare",
            )
            return

        incomplete = self._orchestrator.incomplete_dimensions()
        if incomplete:
            incomplete_names = [d.value for d in incomplete]
            try:
                from contexta.tui.screens.main_screen import MainScreen as MS

                main = self.get_screen("main")
                if isinstance(main, MS):
                    main.show_compare_blocking(incomplete_names)
            except Exception:
                self.notify(
                    "Incomplete dimensions: " + ", ".join(incomplete_names),
                    severity="warning",
                    title="Cannot Compare",
                )
            return

        # All complete — proceed (full wiring done in __main__.py).
        self.notify("Comparison initiated.", title="Compare")

    def handle_export(self, path: str) -> None:
        """Export the current node state to the given file path."""
        self.notify(
            f"Export to {path} initiated.",
            title="Export",
        )

    # ── Orchestrator / blueprint injection ────────────────────────────────────

    def set_orchestrator(self, orchestrator) -> None:
        """Inject the TaskOrchestrator after async pipeline initialisation."""
        self._orchestrator = orchestrator

    def set_blueprint_manager(self, manager) -> None:
        """Inject the PromptBlueprintManager after DB initialisation."""
        self._blueprint_manager = manager

    # ── App-level action handlers (App.BINDINGS fallbacks) ────────────────────
    # These fire when no Screen binding shadows the key.  On MainScreen, f/c/p/e/a
    # are intercepted by MainScreen's priority=True BINDINGS; 'r' reaches the App
    # because MainScreen has no 'r' action defined.

    def action_review(self) -> None:
        """[R] Activate the Review phase and update the PhaseStatusBar."""
        try:
            main = self.get_screen("main")
            if isinstance(main, MainScreen):
                main.set_phase("REVIEW")
        except Exception as exc:
            self.notify(f"Phase update failed: {exc}", severity="warning")

    def action_fork_iteration(self) -> None:
        """[F] Fallback — delegates to handle_fork via a name modal."""
        try:
            main = self.get_screen("main")
            if isinstance(main, MainScreen):
                main.action_fork()
        except Exception:
            self.notify("Fork not available.", severity="warning")

    def action_run_proposal(self) -> None:
        """[P] Fallback — proposal stub."""
        self.notify(
            "Proposal Generator is not yet available in this release.",
            title="[P] Not Implemented",
            severity="warning",
        )

    def action_export_json(self) -> None:
        """[E] Fallback — export confirmation modal."""
        try:
            main = self.get_screen("main")
            if isinstance(main, MainScreen):
                main.action_export()
        except Exception:
            self.notify("Export not available.", severity="warning")
