"""Modal dialog widgets.

Six modals covering all blocking user interactions in the MVP:

Modal                | Trigger                          | Input required
---------------------|----------------------------------|---------------------------
ForkNameModal        | [F] footer key                   | Node name string
ScopeConfirmModal    | [Change Scope] routing button    | Explicit acknowledge
RiskBlockingModal    | ProactiveAdvisor alert           | Explicit acknowledge
CompareBlockingModal | [C] with incomplete dimensions   | Dismiss only
ExportConfirmModal   | [E] footer key                   | File path (pre-filled)
BlueprintErrorModal  | No active blueprint at run start | Dismiss only

Each modal calls ``self.dismiss(result)`` where ``result`` is:
- ``True``   — user confirmed / acknowledged
- ``False``  — user cancelled / dismissed
- ``str``    — user provided text input (ForkNameModal, ExportConfirmModal)
"""

from __future__ import annotations

from typing import List, Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


# ── Shared helpers ────────────────────────────────────────────────────────────

class _ModalBase(ModalScreen):
    """Base class providing a centered card layout with title + body area."""

    DEFAULT_CSS = """
    _ModalBase {
        align: center middle;
    }
    _ModalBase > Vertical {
        width: 60;
        height: auto;
        background: $surface;
        border: thick $accent;
        padding: 1 2;
    }
    _ModalBase .modal-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    _ModalBase .modal-body {
        color: $text;
        margin-bottom: 1;
    }
    _ModalBase .modal-buttons {
        height: auto;
        align-horizontal: right;
        margin-top: 1;
    }
    """


# ── ForkNameModal ─────────────────────────────────────────────────────────────

class ForkNameModal(_ModalBase):
    """Prompt the user to name the forked node.

    Dismisses with the entered name string on confirm, or ``False`` on cancel.
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Fork Iteration", classes="modal-title")
            yield Static(
                "Enter a name for the new forked node:", classes="modal-body"
            )
            yield Input(placeholder="e.g. Draft v2 — Scope Revised", id="fork-name-input")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button("Fork", variant="primary", id="btn-confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm":
            name = self.query_one("#fork-name-input", Input).value.strip()
            if name:
                self.dismiss(name)
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)


# ── ScopeConfirmModal ─────────────────────────────────────────────────────────

class ScopeConfirmModal(_ModalBase):
    """Require explicit acknowledgement before confirming a scope change.

    Dismisses with ``True`` on acknowledge, ``False`` on cancel.
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, finding_summary: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._finding_summary = finding_summary

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("⚠  Scope Change Confirmation", classes="modal-title")
            yield Static(
                "You are about to approve a direct scope modification.\n\n"
                f"Finding: {self._finding_summary}\n\n"
                "This action cannot be undone without creating a new fork.",
                classes="modal-body",
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button(
                    "I acknowledge — Change Scope",
                    variant="error",
                    id="btn-confirm",
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-confirm")

    def action_cancel(self) -> None:
        self.dismiss(False)


# ── RiskBlockingModal ─────────────────────────────────────────────────────────

class RiskBlockingModal(_ModalBase):
    """Display a high-risk advisory alert before Layer 2 synthesis.

    Shows the tag combination, pattern, and frequency count.
    Dismisses with ``True`` when the user explicitly acknowledges.
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, alerts: Optional[List] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._alerts: List = alerts or []

    def compose(self) -> ComposeResult:
        alert_lines: List[str] = []
        for alert in self._alerts:
            tags = getattr(alert, "tag_combination", [])
            pattern = getattr(alert, "pattern", "")
            freq = getattr(alert, "frequency_count", 0)
            alert_lines.append(
                f"• Tags: {', '.join(tags)}\n"
                f"  Pattern: {pattern}\n"
                f"  Seen {freq} time(s) in prior projects"
            )

        body = (
            "High-risk patterns detected for this project's tags.\n\n"
            + ("\n\n".join(alert_lines) if alert_lines else "(no details)")
            + "\n\nYou must acknowledge before proceeding with synthesis."
        )

        with Vertical():
            yield Static("🔴  Proactive Risk Advisory", classes="modal-title")
            yield Static(body, classes="modal-body")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button(
                    "I acknowledge — Proceed",
                    variant="warning",
                    id="btn-confirm",
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-confirm")

    def action_cancel(self) -> None:
        self.dismiss(False)


# ── CompareBlockingModal ──────────────────────────────────────────────────────

class CompareBlockingModal(_ModalBase):
    """Inform the user that not all dimensions are complete.

    Dismiss only — no action taken.  Lists the incomplete dimension names.
    """

    BINDINGS = [("escape", "dismiss_modal", "Dismiss")]

    def __init__(self, incomplete: Optional[List[str]] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._incomplete: List[str] = incomplete or []

    def compose(self) -> ComposeResult:
        dim_list = "\n".join(f"  • {d}" for d in self._incomplete) or "  (none)"
        with Vertical():
            yield Static("Cannot Compare Yet", classes="modal-title")
            yield Static(
                "The following dimensions have not reached COMPLETE state:\n\n"
                f"{dim_list}\n\n"
                "Wait for all 12 dimensions to complete before running Compare.",
                classes="modal-body",
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("Dismiss", variant="primary", id="btn-dismiss")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(False)

    def action_dismiss_modal(self) -> None:
        self.dismiss(False)


# ── ExportConfirmModal ────────────────────────────────────────────────────────

class ExportConfirmModal(_ModalBase):
    """Confirm export path before writing the JSON Packet.

    Dismisses with the chosen path string on confirm, or ``False`` on cancel.
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, default_path: str = "/exports/contexta_export.json", **kwargs) -> None:
        super().__init__(**kwargs)
        self._default_path = default_path

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Export JSON Packet", classes="modal-title")
            yield Static(
                "Enter the output file path for the exported packet:",
                classes="modal-body",
            )
            yield Input(value=self._default_path, id="export-path-input")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button("Export", variant="primary", id="btn-confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm":
            path = self.query_one("#export-path-input", Input).value.strip()
            if path:
                self.dismiss(path)
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)


# ── BlueprintErrorModal ───────────────────────────────────────────────────────

class BlueprintErrorModal(_ModalBase):
    """Block pipeline start when no Prompt Blueprint is active.

    Dismiss only — user must activate a blueprint from the Admin Tab first.
    """

    BINDINGS = [("escape", "dismiss_modal", "Dismiss")]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("No Active Blueprint", classes="modal-title")
            yield Static(
                "No Prompt Blueprint is currently active.\n\n"
                "Go to the Admin Tab (⚙) and activate a blueprint before "
                "starting a dimension review.",
                classes="modal-body",
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("Dismiss", variant="error", id="btn-dismiss")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(False)

    def action_dismiss_modal(self) -> None:
        self.dismiss(False)


# ── EditFindingModal ──────────────────────────────────────────────────────────

class EditFindingModal(_ModalBase):
    """Capture a user override (amended value + rationale) for a finding.

    Displayed when the user presses [i] on an ``AnnotatedFindingRow``.
    The finding's current summary is shown for reference; the user enters:
    - **Amended Value** — their override text replacing the AI output.
    - **Rationale** — why they are making this change (stored in KnowledgeMemory).

    Dismisses with a ``(amended_value, rationale)`` tuple on confirm, or
    ``False`` on cancel / escape.
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(
        self,
        finding_summary: str = "",
        finding_detail: str = "",
        current_value: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._finding_summary = finding_summary
        self._finding_detail = finding_detail
        self._current_value = current_value

    def compose(self) -> ComposeResult:
        summary_truncated = (
            self._finding_summary[:140] + "…"
            if len(self._finding_summary) > 140
            else self._finding_summary
        )
        with Vertical():
            yield Static("✏  Annotate Finding", classes="modal-title")
            yield Static(
                f"Finding: {summary_truncated}",
                classes="modal-body",
            )
            yield Label("Amended Value:")
            yield Input(
                value=self._current_value,
                id="amended-value-input",
                placeholder="Enter your override for this finding…",
            )
            yield Label("Rationale:")
            yield Input(
                id="rationale-input",
                placeholder="Why are you overriding this finding?",
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button("Save Annotation", variant="primary", id="btn-confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm":
            amended = self.query_one("#amended-value-input", Input).value.strip()
            rationale = self.query_one("#rationale-input", Input).value.strip()
            if amended and rationale:
                self.dismiss((amended, rationale))
            # Both fields required — keep modal open if either is missing.
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)
