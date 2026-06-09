"""AdminScreen — Dream Cycle and Prompt Blueprint management.

Accessible from the main screen via the [A] / [⚙] key.
This screen is a named screen installed as ``"admin"`` in ``ContextaApp``.

Layout
------
┌─────────────────────────────────────────────────────────────────┐
│  HEADER: [Contexta Admin]                                       │
├─────────────────────────────────────────────────────────────────┤
│  Dream Cycle Panel                                              │
│  [Trigger Dream Cycle]  Status: Idle                            │
├─────────────────────────────────────────────────────────────────┤
│  Prompt Blueprint Panel                                         │
│  DataTable: id | name | version | active                        │
│  [Activate]  [New Version]  [Import JSON]                       │
└─────────────────────────────────────────────────────────────────┘
│  FOOTER: [Esc] Back to Main                                     │
└─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Label, Static


class DreamCyclePanel(Static):
    """Trigger control + status indicator for the Dream Cycle worker."""

    DEFAULT_CSS = """
    DreamCyclePanel {
        height: auto;
        padding: 1 2;
        border: solid $accent-darken-2;
        margin-bottom: 1;
    }
    DreamCyclePanel .panel-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    DreamCyclePanel #dream-status {
        color: $text-muted;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Dream Cycle", classes="panel-title")
        yield Static("Status: Idle", id="dream-status")
        yield Button("Trigger Dream Cycle", variant="primary", id="btn-dream-trigger")

    def set_running(self) -> None:
        self.query_one("#dream-status", Static).update("Status: ● Running…")

    def set_idle(self, updated: int = 0) -> None:
        self.query_one("#dream-status", Static).update(
            f"Status: Idle  (last run updated {updated} insight row(s))"
        )

    def set_error(self, message: str) -> None:
        self.query_one("#dream-status", Static).update(f"Status: ✗ Error — {message}")


class BlueprintPanel(Static):
    """List all prompt blueprints; allow activate and new-version creation."""

    DEFAULT_CSS = """
    BlueprintPanel {
        height: 1fr;
        padding: 1 2;
        border: solid $accent-darken-2;
    }
    BlueprintPanel .panel-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    BlueprintPanel #blueprint-table {
        height: 1fr;
        margin-bottom: 1;
    }
    BlueprintPanel #blueprint-buttons {
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Prompt Blueprints", classes="panel-title")
        table = DataTable(id="blueprint-table")
        table.add_columns("ID", "Name", "Version", "Active")
        yield table
        with Vertical(id="blueprint-buttons"):
            yield Button("Activate Selected", variant="success", id="btn-activate")
            yield Button("New Version", variant="primary", id="btn-new-version")

    def populate(self, blueprints: list) -> None:
        """Load blueprint rows into the DataTable."""
        table = self.query_one("#blueprint-table", DataTable)
        table.clear()
        for bp in blueprints:
            active_marker = "✓" if getattr(bp, "is_active", False) else ""
            table.add_row(
                str(getattr(bp, "id", "")),
                str(getattr(bp, "blueprint_name", "")),
                str(getattr(bp, "version_string", "")),
                active_marker,
            )


class AdminScreen(Screen):
    """Admin tab: Dream Cycle + Blueprint management + JSON import."""

    BINDINGS = [
        Binding("escape", "back", "Back to Main", show=True, priority=True),
    ]

    DEFAULT_CSS = """
    AdminScreen {
        layout: vertical;
    }
    #admin-body {
        height: 1fr;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="admin-body"):
            yield DreamCyclePanel(id="dream-cycle-panel")
            yield BlueprintPanel(id="blueprint-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Contexta Admin"
        self.sub_title = "Dream Cycle · Blueprint Management"

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_back(self) -> None:
        """Return to the main screen."""
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-dream-trigger":
            self._trigger_dream_cycle()
        elif event.button.id == "btn-activate":
            self.app.notify("Select a blueprint row first.", severity="information")
        elif event.button.id == "btn-new-version":
            self.app.notify("New version creation — coming soon.", severity="information")

    # ── Dream Cycle ───────────────────────────────────────────────────────────

    def _trigger_dream_cycle(self) -> None:
        """Launch the DreamCycleWorker as a Textual Worker."""
        panel = self.query_one("#dream-cycle-panel", DreamCyclePanel)
        panel.set_running()
        self.run_worker(self._run_dream_cycle(), exclusive=True, name="dream-cycle")

    async def _run_dream_cycle(self) -> None:
        """Async worker body — calls DreamCycleWorker if DB is available."""
        panel = self.query_one("#dream-cycle-panel", DreamCyclePanel)
        try:
            db_conn = getattr(self.app, "_db_conn", None)
            if db_conn is None:
                panel.set_error("No database connection available.")
                return

            from contexta.admin.dream_cycle import DreamCycleWorker  # noqa: PLC0415

            worker = DreamCycleWorker()
            updated = await worker.run(db_conn)
            panel.set_idle(updated)
        except Exception as exc:
            panel.set_error(str(exc))
            self.app.notify(
                f"Dream Cycle error: {exc}",
                title="Dream Cycle",
                severity="error",
            )
