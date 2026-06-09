"""MainScreen — primary TUI layout.

Header (project / node / admin indicator)
Left pane  (30%): ArtifactView
Right pane (70%): PipelineView
Footer: [F] Fork  [C] Compare  [P] Proposal  [E] Export
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Header

from ...admin.blueprint_manager import PromptBlueprintManager
from ...db.repositories import fork_node
from ...export.serializer import ExportError, JSONPacketSerializer
from ...llm.prompts import PromptBuilder
from ...llm.provider import LLMConfig
from ...mcp.artifact_registry import ArtifactRegistry
from ...models.export import EXPORT_SCHEMA_VERSION, ExportArbitratorResult, JSONPacket
from ...models.payloads import ReviewNodePayload
from ...pipeline.arbitrator import ArbitratorEngine, ArbitratorError
from ...pipeline.advisor import ProactiveAdvisor
from ...pipeline.dimension_runner import (
    TaskOrchestrator,
    TaskState,
    commit_exploration_node,
    make_dimension_runner,
)
from ...pipeline.scope_policy import ScopePolicyEnforcer
from ..messages import (
    AdvisoryAlertDetected,
    ArtifactIngested,
    CitationJumpRequested,
    DimensionStateChanged,
)
from ..widgets.artifact_view import ArtifactView
from ..widgets.modals import (
    BlueprintErrorModal,
    CompareBlockingModal,
    ExportConfirmModal,
    ForkNameModal,
    RiskBlockingModal,
)
from ..widgets.pipeline_view import PipelineView


class MainScreen(Screen):
    """Primary application screen.

    Wires the ingest controls, pipeline triggers, and footer key bindings to
    the underlying backend services.
    """

    BINDINGS = [
        Binding("f", "fork", "[F] Fork Iteration", show=True),
        Binding("c", "compare", "[C] Compare", show=True),
        Binding("p", "proposal", "[P] Run Proposal Generator", show=True),
        Binding("e", "export", "[E] Export Flat JSON Packet", show=True),
        Binding("a", "admin", "⚙ Admin", show=True),
    ]

    def __init__(
        self,
        registry: ArtifactRegistry,
        llm_config: LLMConfig,
        blueprint_manager: PromptBlueprintManager,
        export_path: str = "/exports",
        project_name: str = "New Project",
        node_name: str = "Draft v1",
        global_tags: list | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._registry = registry
        self._llm_config = llm_config
        self._blueprint_manager = blueprint_manager
        self._export_path = export_path
        self._project_name = project_name
        self._node_name = node_name
        self._global_tags: list = global_tags or []

        self._orchestrator: TaskOrchestrator | None = None
        self._current_project_id: str | None = None
        self._current_node_id: str | None = None
        self._arbitrator_result = None

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            yield ArtifactView(self._registry, id="artifact-view")
            yield PipelineView(
                project_name=self._project_name,
                node_name=self._node_name,
                global_tags=self._global_tags,
                id="pipeline-view",
            )
        yield Footer()

    # ── Pipeline launch ───────────────────────────────────────────────────────

    async def launch_pipeline(
        self,
        project_id: str,
        node_id: str | None = None,
    ) -> None:
        """Wire the registry + LLM config into a TaskOrchestrator and launch all 12 tasks."""
        self._current_project_id = project_id
        self._current_node_id = node_id

        blueprint = await self._blueprint_manager.get_active()
        if blueprint is None:
            await self.app.push_screen(BlueprintErrorModal())
            return

        if not self._registry.all():
            self.app.notify("⚠ No source files ingested. Ingest files before running.", timeout=5)
            return

        schema_json = ReviewNodePayload.model_json_schema().__str__()
        builder = PromptBuilder(blueprint=blueprint, schema_json=schema_json)

        runner_fn = make_dimension_runner(
            config=self._llm_config,
            builder=builder,
            registry=self._registry,
        )

        async def _on_state_change(task) -> None:
            self.post_message(
                DimensionStateChanged(
                    dimension=task.dimension,
                    state=task.state,
                    error=task.error_message,
                )
            )

        self._orchestrator = TaskOrchestrator(
            on_state_change=_on_state_change,
            runner_fn=runner_fn,
        )

        self.app.notify("▶ Layer 1 exploration started across all 12 dimensions…")
        await self._orchestrator.launch_all()

        if self._orchestrator.all_complete():
            # Batch-commit to DB
            conn = getattr(self.app, "db", None)
            if conn is not None:
                await commit_exploration_node(
                    self._orchestrator,
                    conn,
                    project_id=project_id,
                    node_name=self._node_name,
                    parent_id=node_id,
                )
            self.app.notify("✅ Layer 1 complete — all 12 dimensions reviewed.")
        else:
            incomplete = self._orchestrator.incomplete_dimensions()
            self.app.notify(
                f"⚠ {len(incomplete)} dimension(s) failed. Use Retry to rerun.",
                timeout=8,
            )

    # ── Footer key bindings ───────────────────────────────────────────────────

    async def action_fork(self) -> None:
        """[F] Open fork name modal then create the new node."""

        def _on_name(name: str | None) -> None:
            if name:
                self.run_worker(self._do_fork(name), exclusive=False)

        await self.app.push_screen(ForkNameModal(), _on_name)

    async def _do_fork(self, name: str) -> None:
        conn = getattr(self.app, "db", None)
        if conn is None or self._current_node_id is None:
            self.app.notify("⚠ No active node to fork from.", timeout=4)
            return
        try:
            new_node = await fork_node(conn, self._current_node_id, name)
            self._current_node_id = new_node.id
            self._node_name = name
            pv = self.query_one("#pipeline-view", PipelineView)
            pv.update_node_info(self._project_name, name)
            self.app.notify(f"🔀 Forked to node: {name!r}")
        except Exception as exc:
            self.app.notify(f"❌ Fork failed: {exc}", timeout=6)

    async def action_compare(self) -> None:
        """[C] Run the Layer 2 Arbitrator synthesis."""
        if self._orchestrator is None:
            self.app.notify("⚠ Run Layer 1 first.", timeout=4)
            return

        if not self._orchestrator.all_complete():
            incomplete = [d.value for d in self._orchestrator.incomplete_dimensions()]
            await self.app.push_screen(CompareBlockingModal(incomplete))
            return

        # Proactive Advisor check
        conn = getattr(self.app, "db", None)
        if conn is not None:
            advisor = ProactiveAdvisor()
            alerts = await advisor.evaluate(self._global_tags, conn)
            if alerts:

                def _on_ack(acked: bool) -> None:
                    if acked:
                        self.run_worker(self._run_arbitrator(), exclusive=True)

                await self.app.push_screen(RiskBlockingModal(alerts), _on_ack)
                return

        await self._run_arbitrator()

    async def _run_arbitrator(self) -> None:
        blueprint = await self._blueprint_manager.get_active()
        if blueprint is None:
            await self.app.push_screen(BlueprintErrorModal())
            return

        schema_json = ReviewNodePayload.model_json_schema().__str__()
        builder = PromptBuilder(blueprint=blueprint, schema_json=schema_json)
        engine = ArbitratorEngine(config=self._llm_config, builder=builder)

        try:
            payloads = self._orchestrator.get_all_payloads()  # type: ignore[union-attr]
            result = await engine.run(payloads)
            self._arbitrator_result = result
            pv = self.query_one("#pipeline-view", PipelineView)
            pv.show_reconciliation(result.contradictions)
            self.app.notify("✅ Layer 2 synthesis complete.")
        except ArbitratorError as exc:
            self.app.notify(f"❌ Arbitrator error: {exc}", timeout=8)

    async def action_proposal(self) -> None:
        """[P] Proposal Generator — stub (out of MVP scope)."""
        self.app.notify("ℹ Proposal Generator not yet implemented.", timeout=4)

    async def action_export(self) -> None:
        """[E] Open export path modal then serialise the active node."""
        default = str(
            Path(self._export_path) / f"{self._node_name.replace(' ', '_')}.json"
        )

        def _on_path(path: str | None) -> None:
            if path:
                self.run_worker(self._do_export(path), exclusive=False)

        await self.app.push_screen(ExportConfirmModal(default_path=default), _on_path)

    async def _do_export(self, path: str) -> None:
        if self._orchestrator is None or not self._orchestrator.all_complete():
            self.app.notify("⚠ Complete Layer 1 before exporting.", timeout=4)
            return

        payloads = self._orchestrator.get_all_payloads()
        arb = None
        if self._arbitrator_result is not None:
            arb = ExportArbitratorResult(
                contradictions=self._arbitrator_result.contradictions,
                raw_llm_response=self._arbitrator_result.raw_llm_response,
            )

        conn = getattr(self.app, "db", None)
        routing: list = []
        if conn is not None and self._current_node_id is not None:
            from ...db.repositories import get_node
            node = await get_node(conn, self._current_node_id)
            if node:
                meta = json.loads(node.metadata_json)
                routing = meta.get("routing_decisions", [])

        packet = JSONPacket(
            schema_version=EXPORT_SCHEMA_VERSION,
            export_timestamp=datetime.now(timezone.utc).isoformat(),
            project_name=self._project_name,
            project_global_tags=self._global_tags,
            node_id=self._current_node_id or "unknown",
            node_name=self._node_name,
            parent_node_id=None,
            layer_type="exploration",
            dimension_payloads=payloads,
            arbitrator_result=arb,
            routing_decisions=routing,
            metadata={},
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        serializer = JSONPacketSerializer()
        try:
            await serializer.export(packet, Path(path))
            self.app.notify(f"✅ Exported to: {path}")
        except ExportError as exc:
            self.app.notify(f"❌ Export failed: {exc}", timeout=8)

    async def action_admin(self) -> None:
        """Switch to the Admin screen."""
        await self.app.push_screen("admin")
