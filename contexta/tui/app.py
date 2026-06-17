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

from contexta.mcp.artifact_registry import ArtifactRegistry
from contexta.tui.messages import ArbitrationStatusChanged, CitationJumpRequested, TaskState
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
        """Install screens and push the default MainScreen."""
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

        # All complete — guard prerequisites then launch the async worker.
        if self._llm_config is None:
            self.notify(
                "LLM not configured.",
                severity="error",
                title="Compare",
            )
            return

        if self._blueprint_manager is None:
            self.notify(
                "No blueprint manager available.",
                severity="error",
                title="Compare",
            )
            return

        self.run_worker(self._run_arbitration(), exclusive=True, name="arbitration")

    def handle_export(self, path: str) -> None:
        """Export the current node state to the given file path."""
        self.notify(
            f"Export to {path} initiated.",
            title="Export",
        )

    # ── Arbitration worker ────────────────────────────────────────────────────

    async def _run_arbitration(self) -> None:
        """Async worker: run ArbitratorEngine, stream status to TUI, handle errors.

        Lifecycle
        ---------
        1. Resolve the active blueprint; show ``BlueprintErrorModal`` if absent.
        2. Build ``ArbitratorEngine`` and call ``run()`` with an async callback
           that posts ``ArbitrationStatusChanged`` for every status transition.
        3. On success, push contradictions into ``PipelineView.show_reconciliation()``.
        4. On ``ArbitratorError``, emit a FAILED status update and open
           ``ArbitratorErrorModal`` so the user sees a readable description.
        5. On any unexpected exception, surface it as a non-fatal notification.
        """
        from contexta.pipeline.arbitrator import (
            ArbitratorEngine,
            ArbitratorError,
            ArbitrationStatus,
        )
        from contexta.llm.prompts import PromptBuilder

        async def _callback(status: ArbitrationStatus, detail: str) -> None:
            self.post_message(ArbitrationStatusChanged(status=status, detail=detail))

        try:
            active_bp = await self._blueprint_manager.get_active()
            if active_bp is None:
                try:
                    from contexta.tui.screens.main_screen import MainScreen as MS
                    main = self.get_screen("main")
                    if isinstance(main, MS):
                        main.show_blueprint_error()
                except Exception:
                    self.notify(
                        "No active blueprint. Activate one from the Admin Tab.",
                        severity="error",
                        title="Compare",
                    )
                return

            # schema_json is only consumed by build_dimension_prompt; the
            # arbitrator call uses ARBITRATOR_SYSTEM_TEMPLATE directly.
            builder = PromptBuilder(blueprint=active_bp, schema_json="")
            payloads = self._orchestrator.get_all_payloads()
            engine = ArbitratorEngine(config=self._llm_config, builder=builder)
            result = await engine.run(payloads, callback=_callback)

            # Deliver results to the TUI.
            try:
                from contexta.tui.screens.main_screen import MainScreen as MS
                main = self.get_screen("main")
                if isinstance(main, MS):
                    main.pipeline_view.show_reconciliation(result.contradictions)
            except Exception:
                pass

        except ArbitratorError as exc:
            await _callback(ArbitrationStatus.FAILED, str(exc))
            try:
                from contexta.tui.widgets.modals import ArbitratorErrorModal
                self.push_screen(ArbitratorErrorModal(message=str(exc)))
            except Exception:
                self.notify(
                    f"Arbitration failed: {exc}",
                    severity="error",
                    title="Compare Error",
                )

        except Exception as exc:
            self.notify(
                f"Unexpected error during arbitration: {exc}",
                severity="error",
                title="Compare Error",
            )

    # ── ArbitrationStatus routing ─────────────────────────────────────────────

    def on_arbitration_status_changed(self, event: ArbitrationStatusChanged) -> None:
        """Route ``ArbitrationStatusChanged`` to the PipelineView status bar."""
        try:
            from contexta.tui.screens.main_screen import MainScreen as MS
            main = self.get_screen("main")
            if isinstance(main, MS):
                main.pipeline_view.show_arbitration_status(event.status, event.detail)
        except Exception:
            pass

    # ── Orchestrator / blueprint injection ────────────────────────────────────

    def set_orchestrator(self, orchestrator) -> None:
        """Inject the TaskOrchestrator after async pipeline initialisation."""
        self._orchestrator = orchestrator

    def set_blueprint_manager(self, manager) -> None:
        """Inject the PromptBlueprintManager after DB initialisation."""
        self._blueprint_manager = manager
