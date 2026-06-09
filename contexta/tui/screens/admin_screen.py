"""AdminScreen — Dream Cycle trigger and Prompt Blueprint management.

Dream Cycle is launched as a Textual ``Worker`` with ``exclusive=True`` so
that concurrent triggers are prevented.  The worker runs in the asyncio event
loop (``thread=False``) to share the single ``aiosqlite.Connection``.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Label, Static
from textual.worker import Worker

from ...admin.blueprint_manager import PromptBlueprintManager
from ...admin.dream_cycle import DreamCycleWorker
from ...db.models import BlueprintRow


class AdminScreen(Screen):
    """Admin Tab: Dream Cycle control + Prompt Blueprint manager."""

    BINDINGS = [
        Binding("escape", "back", "← Back", show=True),
    ]

    def __init__(
        self,
        blueprint_manager: PromptBlueprintManager,
        db_conn,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._blueprint_manager = blueprint_manager
        self._db = db_conn
        self._dream_worker: Worker | None = None

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)

        with Vertical(id="admin-container"):
            # Dream Cycle panel
            yield Label("⚙ Dream Cycle", id="dream-title")
            yield Label("Analyses all nodes for recurring RED-confidence patterns.", id="dream-desc")
            with Static(id="dream-controls"):
                yield Button("▶ Trigger Dream Cycle", id="dream-trigger", variant="primary")
                yield Label("Status: idle", id="dream-status")

            # Blueprint panel
            yield Label("📋 Prompt Blueprints", id="bp-title")
            yield DataTable(id="blueprint-table")
            with Static(id="bp-controls"):
                yield Button("Activate Selected", id="bp-activate", variant="success")
                yield Button("New Version", id="bp-new-version", variant="default")

            # Import JSON panel
            yield Label("📥 Import JSON Packet", id="import-title")
            from textual.widgets import Input as TInput
            yield TInput(placeholder="/path/to/packet.json", id="import-path")
            yield Button("Import", id="import-btn", variant="primary")
            yield Label("", id="import-status")

        yield Footer()

    async def on_mount(self) -> None:
        await self._refresh_blueprint_table()

    async def _refresh_blueprint_table(self) -> None:
        table = self.query_one("#blueprint-table", DataTable)
        table.clear(columns=True)
        table.add_columns("ID (short)", "Name", "Version", "Active")
        blueprints = await self._blueprint_manager.list_all()
        for bp in blueprints:
            table.add_row(
                bp.id[:8],
                bp.blueprint_name,
                bp.version_string,
                "✅" if bp.is_active else "—",
            )

    # ── Button handlers ───────────────────────────────────────────────────────

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id

        if btn_id == "dream-trigger":
            await self._trigger_dream_cycle()

        elif btn_id == "bp-activate":
            table = self.query_one("#blueprint-table", DataTable)
            if table.cursor_row is not None:
                try:
                    row = table.get_row_at(table.cursor_row)
                    short_id = str(row[0])
                    # Resolve full ID from manager
                    all_bps = await self._blueprint_manager.list_all()
                    for bp in all_bps:
                        if bp.id.startswith(short_id):
                            await self._blueprint_manager.activate(bp.id)
                            await self._refresh_blueprint_table()
                            self.app.notify(f"✅ Blueprint {bp.blueprint_name!r} activated.")
                            break
                except Exception as exc:
                    self.app.notify(f"❌ Activate failed: {exc}", timeout=6)

        elif btn_id == "bp-new-version":
            self.app.notify("ℹ New Blueprint version UI — use the API directly for now.", timeout=4)

        elif btn_id == "import-btn":
            await self._do_import()

    # ── Dream Cycle ───────────────────────────────────────────────────────────

    async def _trigger_dream_cycle(self) -> None:
        status = self.query_one("#dream-status", Label)
        status.update("Status: running…")
        self.query_one("#dream-trigger", Button).disabled = True

        # @work(exclusive=True, thread=False) — runs in asyncio loop
        self._dream_worker = self.run_worker(
            self._run_dream_cycle(),
            exclusive=True,
            thread=False,
        )

    async def _run_dream_cycle(self) -> None:
        status = self.query_one("#dream-status", Label)
        try:
            worker = DreamCycleWorker()
            count = await worker.run(self._db)
            status.update(f"Status: complete — {count} insight(s) updated.")
            self.app.notify(f"✅ Dream Cycle complete: {count} insights updated.")
        except Exception as exc:
            status.update(f"Status: error — {exc}")
            self.app.notify(f"❌ Dream Cycle error: {exc}", timeout=8)
        finally:
            self.query_one("#dream-trigger", Button).disabled = False

    # ── JSON Import ───────────────────────────────────────────────────────────

    async def _do_import(self) -> None:
        from pathlib import Path

        from ...export.deserializer import ImportValidationError, JSONPacketDeserializer

        path_input = self.query_one("#import-path")
        status_label = self.query_one("#import-status", Label)
        path_str = path_input.value.strip()  # type: ignore[attr-defined]

        if not path_str:
            status_label.update("⚠ Please enter a file path.")
            return

        status_label.update("Importing…")
        try:
            deserializer = JSONPacketDeserializer()
            node = await deserializer.import_packet(Path(path_str), self._db)
            status_label.update(f"✅ Imported node: {node.id[:8]}…")
            self.app.notify(f"✅ Import complete: node {node.node_name!r} created.")
        except ImportValidationError as exc:
            status_label.update(f"❌ Validation error: {str(exc)[:120]}")
            self.app.notify(f"❌ Import failed (validation): {exc}", timeout=8)
        except Exception as exc:
            status_label.update(f"❌ Error: {str(exc)[:120]}")
            self.app.notify(f"❌ Import error: {exc}", timeout=8)

    # ── Navigation ────────────────────────────────────────────────────────────

    async def action_back(self) -> None:
        await self.app.pop_screen()
