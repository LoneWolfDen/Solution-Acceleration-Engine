"""Modal dialog widgets for Contexta TUI.

Six modals:
- ``ForkNameModal``       — text input for node name
- ``ScopeConfirmModal``   — explicit acknowledge checkbox before scope change
- ``RiskBlockingModal``   — high-risk pattern acknowledgement (blocking)
- ``CompareBlockingModal``— lists incomplete dimensions (dismiss only)
- ``ExportConfirmModal``  — file path input pre-filled with default export path
- ``BlueprintErrorModal`` — no active blueprint; dismiss only
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Static


# ── Fork Name ─────────────────────────────────────────────────────────────────


class ForkNameModal(ModalScreen[str | None]):
    """Prompts the user for a new fork node name."""

    DEFAULT_CSS = """
    ForkNameModal > Vertical {
        border: thick $primary;
        padding: 1 2;
        width: 50;
        height: auto;
        align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("🔀 Fork Node — Enter a name for the new branch:")
            yield Input(placeholder="e.g. Revised Risk Assessment", id="fork-name-input")
            with Static():
                yield Button("Confirm", variant="primary", id="fork-confirm")
                yield Button("Cancel", variant="default", id="fork-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "fork-confirm":
            name = self.query_one("#fork-name-input", Input).value.strip()
            self.dismiss(name if name else None)
        else:
            self.dismiss(None)


# ── Scope Confirm ─────────────────────────────────────────────────────────────


class ScopeConfirmModal(ModalScreen[bool]):
    """Requires explicit acknowledgement before accepting a scope change."""

    DEFAULT_CSS = """
    ScopeConfirmModal > Vertical {
        border: thick $warning;
        padding: 1 2;
        width: 60;
        height: auto;
        align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("⚠ Scope Change Confirmation", markup=False)
            yield Label(
                "Changing scope is a significant decision. Tick the box to acknowledge.",
                markup=False,
            )
            yield Checkbox("I confirm this scope change is approved", id="scope-ack")
            with Static():
                yield Button("Confirm", variant="warning", id="scope-confirm")
                yield Button("Cancel", variant="default", id="scope-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "scope-confirm":
            acked = self.query_one("#scope-ack", Checkbox).value
            self.dismiss(bool(acked))
        else:
            self.dismiss(False)


# ── Risk Blocking ─────────────────────────────────────────────────────────────


class RiskBlockingModal(ModalScreen[bool]):
    """Blocking modal for high-risk tag pattern detection (Req 8.3/8.4)."""

    DEFAULT_CSS = """
    RiskBlockingModal > Vertical {
        border: thick $error;
        padding: 1 2;
        width: 70;
        height: auto;
        align: center middle;
    }
    RiskBlockingModal .risk-item {
        color: $warning;
        padding: 0 2;
    }
    """

    def __init__(self, alerts: list, **kwargs) -> None:
        super().__init__(**kwargs)
        self._alerts = alerts

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("🚨 High-Risk Pattern Detected", markup=False)
            for alert in self._alerts:
                tags = ", ".join(alert.tag_combination)
                yield Label(
                    f"Tags: {tags} | Pattern: {alert.pattern} | Seen: {alert.frequency_count}×",
                    classes="risk-item",
                    markup=False,
                )
            yield Label(
                "You must acknowledge this risk before proceeding.",
                markup=False,
            )
            yield Button("Acknowledge & Continue", variant="error", id="risk-ack")
            yield Button("Cancel", variant="default", id="risk-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "risk-ack")


# ── Compare Blocking ──────────────────────────────────────────────────────────


class CompareBlockingModal(ModalScreen[None]):
    """Lists incomplete dimensions; blocks Compare until all are done."""

    DEFAULT_CSS = """
    CompareBlockingModal > Vertical {
        border: thick $warning;
        padding: 1 2;
        width: 60;
        height: auto;
        align: center middle;
    }
    CompareBlockingModal .incomplete-dim {
        color: $warning;
        padding: 0 2;
    }
    """

    def __init__(self, incomplete: List[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self._incomplete = incomplete

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("⏳ Compare unavailable — dimensions still pending:")
            for dim in self._incomplete:
                yield Label(f"  • {dim}", classes="incomplete-dim")
            yield Button("Dismiss", variant="default", id="compare-dismiss")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


# ── Export Confirm ────────────────────────────────────────────────────────────


class ExportConfirmModal(ModalScreen[str | None]):
    """File path input for JSON packet export."""

    DEFAULT_CSS = """
    ExportConfirmModal > Vertical {
        border: thick $primary;
        padding: 1 2;
        width: 70;
        height: auto;
        align: center middle;
    }
    """

    def __init__(self, default_path: str = "/exports/packet.json", **kwargs) -> None:
        super().__init__(**kwargs)
        self._default_path = default_path

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("📦 Export JSON Packet — confirm destination path:")
            yield Input(value=self._default_path, id="export-path-input")
            with Static():
                yield Button("Export", variant="primary", id="export-confirm")
                yield Button("Cancel", variant="default", id="export-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "export-confirm":
            path = self.query_one("#export-path-input", Input).value.strip()
            self.dismiss(path if path else None)
        else:
            self.dismiss(None)


# ── Blueprint Error ───────────────────────────────────────────────────────────


class BlueprintErrorModal(ModalScreen[None]):
    """Displayed when no active blueprint is found (dismiss only)."""

    DEFAULT_CSS = """
    BlueprintErrorModal > Vertical {
        border: thick $error;
        padding: 1 2;
        width: 60;
        height: auto;
        align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("❌ No Active Prompt Blueprint", markup=False)
            yield Label(
                "Go to Admin → Blueprints and activate a blueprint before reviewing.",
                markup=False,
            )
            yield Button("Dismiss", variant="default", id="bp-error-dismiss")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)
