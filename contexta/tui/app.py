"""ContextaApp — the Textual application root.

Responsibilities
----------------
- Holds the single ``aiosqlite.Connection``, ``ContextaConfig``,
  ``ArtifactRegistry``, and ``PromptBlueprintManager``.
- Registers ``MainScreen`` as the default screen and ``AdminScreen`` as a named
  screen accessible via ``push_screen("admin")``.
- Provides ``notify()`` for non-fatal error notifications (timed footer bar).
- Implements high-level action handlers (``handle_fork``, ``handle_compare``,
  ``handle_export``) that are called by ``MainScreen``'s footer action methods.
- Holds an optional ``KnowledgeMemoryService`` injected after async DB init.
- Handles ``FindingEditRequested`` by opening ``EditFindingModal``, then on
  confirm: persists the annotation to KnowledgeMemory, updates the in-memory
  payload via ``TaskOrchestrator.add_annotation()``, and refreshes the UI row.

Design constraint: this module owns no business logic.  It wires together the
pipeline, MCP, knowledge, and admin layers and delegates all heavy work there.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, List, Optional

from textual.app import App, ComposeResult

from contexta.mcp.artifact_registry import ArtifactRegistry
from contexta.tui.messages import (
    AnnotationApplied,
    CitationJumpRequested,
    FindingEditRequested,
    TaskState,
)
from contexta.tui.messages import ArbitrationStatusChanged, CitationJumpRequested, TaskState
from contexta.tui.screens.main_screen import MainScreen

if TYPE_CHECKING:
    import aiosqlite
    from contexta.config import ContextaConfig
    from contexta.knowledge.memory import KnowledgeMemoryService
    from contexta.tui.widgets.pipeline_view import PipelineView


class ContextaApp(App):
    """Textual application root for Project Contexta."""

    TITLE = "Project Contexta"
    SUB_TITLE = "Deterministic Solution Validation Pipeline"

    SCREENS = {}

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

        # Injected after construction by __main__.py after async DB init.
        self._orchestrator = None
        self._blueprint_manager = None
        self._llm_config = None
        self._knowledge_service: Optional["KnowledgeMemoryService"] = None

        # Wire up blueprint manager and LLM config eagerly if prerequisites
        # are available.
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
        return iter([])

    def on_mount(self) -> None:
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
        """Route CitationJumpRequested from PipelineView to ArtifactView."""
        try:
            from contexta.tui.widgets.artifact_view import ArtifactView

            av = self.query_one("#artifact-view", ArtifactView)
            av.on_citation_jump_requested(event)
        except Exception:
            pass

    # ── Annotation flow ───────────────────────────────────────────────────────

    def on_finding_edit_requested(self, event: FindingEditRequested) -> None:
        """Open EditFindingModal; on confirm persist and update in-memory state.

        Flow:
        1. Push EditFindingModal with the finding context pre-filled.
        2. On confirm (amended_value, rationale) tuple:
           a. Build a UserAnnotation.
           b. Schedule _persist_annotation() as an asyncio task.
           c. Call orchestrator.add_annotation() to update in-memory payload.
           d. Refresh the annotation row in the PipelineView immediately.
        """
        from contexta.tui.widgets.modals import EditFindingModal

        dim = event.dimension
        idx = event.finding_index

        def _on_modal_result(result) -> None:
            if not result:
                return
            amended_value, rationale = result
            self._apply_annotation(dim, idx, event.base_value, amended_value, rationale)

        self.push_screen(
            EditFindingModal(
                finding_summary=event.base_value,
                finding_detail=event.detail,
                current_value=event.base_value,
            ),
            callback=_on_modal_result,
        )

    def _apply_annotation(
        self,
        dimension,
        finding_index: int,
        base_value: str,
        amended_value: str,
        rationale: str,
    ) -> None:
        """Build the annotation, update in-memory state, persist async, refresh UI."""
        from contexta.models.findings import UserAnnotation

        annotation = UserAnnotation(
            finding_index=finding_index,
            dimension=dimension,
            base_value=base_value,
            amended_value=amended_value,
            rationale=rationale,
        )

        # Update in-memory payload immediately so subsequent LLM runs see it.
        if self._orchestrator is not None:
            try:
                self._orchestrator.add_annotation(dimension, annotation)
            except ValueError:
                # Dimension not yet complete — annotation cannot be applied.
                self.notify(
                    "Cannot annotate: dimension review not complete.",
                    severity="warning",
                    title="Annotate",
                )
                return

        # Persist to KnowledgeMemory asynchronously (non-blocking).
        asyncio.ensure_future(
            self._persist_observation(dimension, finding_index, base_value, amended_value, rationale)
        )

        # Refresh the PipelineView row immediately without waiting for DB.
        try:
            main = self.get_screen("main")
            from contexta.tui.screens.main_screen import MainScreen as MS

            if isinstance(main, MS):
                main.pipeline_view.refresh_annotation(dimension, finding_index, annotation)
        except Exception:
            pass

        self.notify(
            f"Annotation saved for [{dimension.value}] finding #{finding_index + 1}.",
            title="Annotate",
        )

    async def _persist_observation(
        self,
        dimension,
        finding_index: int,
        base_value: str,
        amended_value: str,
        rationale: str,
    ) -> None:
        """Write the observation to KnowledgeMemory (runs in the event loop)."""
        if self._knowledge_service is None:
            return

        from contexta.models.enums import PhaseEnum

        node_id = ""
        if self._orchestrator is not None:
            node_id = getattr(self._orchestrator, "_current_node_id", "") or ""

        try:
            await self._knowledge_service.record_observation(
                phase=PhaseEnum.DIMENSION_REVIEW,
                node_id=node_id,
                dimension=dimension.value,
                base_value=base_value,
                amended_value=amended_value,
                rationale=rationale,
            )
        except Exception as exc:
            self.notify(
                f"KnowledgeMemory write failed: {exc}",
                severity="error",
                title="Persist Annotation",
            )

    # ── High-level action handlers ────────────────────────────────────────────

    def handle_fork(self, name: str) -> None:
        """Create a forked node and update the header."""
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

        self.notify("Comparison initiated.", title="Compare")
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
        self.notify(f"Export to {path} initiated.", title="Export")

    # ── Injection API ──────────────────────────────────────────────────────────
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

            builder = PromptBuilder(blueprint=active_bp)
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

    def set_knowledge_service(self, service: "KnowledgeMemoryService") -> None:
        """Inject the KnowledgeMemoryService after async DB initialisation.

        Called by ``__main__.py`` once the DB connection is open and the
        KnowledgeMemoryService is constructed.  Enables annotation persistence
        and contextual constraint injection for all subsequent LLM calls.
        """
        self._knowledge_service = service
