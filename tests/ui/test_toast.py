"""tests/ui/test_toast.py — ToastNotification component tests.

Spec requirement (Milestone 6, task 6.5):
  - ToastNotification renders with error message when toast_message is set
  - ToastNotification is absent from DOM when toast_message is None
  - Error variant (red) shown when message originates from error field

Design approach
---------------
The ToastNotification uses a top-level rx.cond:
  - When toast_message != "" → renders a Box with HStack (icon + text + dismiss)
  - When toast_message == "" → renders rx.fragment() (nothing)

We cannot evaluate rx.cond branches at import time (they are compiled to JS).
Instead we verify:
  1. The component tree always has a top-level Cond.
  2. A Box + HStack + DynamicIcon + IconButton are inside the truthy branch.
  3. AppState field defaults ensure the initial state is "no toast".
  4. The dismiss IconButton has an on_change/on_click trigger tied to
     AppState.clear_toast.

State defaults are tested against the AppState class-level __fields__ rather
than by instantiating the state (which Reflex prohibits outside the runtime).
"""

from __future__ import annotations

import pytest
import reflex as rx

from tests.ui.conftest import collect_types, event_handler_fn, find_by_type, state_default
from web.components.toast import toast_notification
from web.state import AppState


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------


class TestToastSmoke:
    def test_returns_rx_component(self):
        result = toast_notification()
        assert isinstance(result, rx.Component)

    def test_renders_multiple_times_consistently(self):
        """Calling the function twice must produce identical structures."""
        a = toast_notification()
        b = toast_notification()
        assert type(a).__name__ == type(b).__name__

    def test_top_level_is_fragment(self):
        """The outermost element wraps the cond in a Fragment."""
        comp = toast_notification()
        assert type(comp).__name__ == "Fragment"


# ---------------------------------------------------------------------------
# Structure — the toast is conditionally rendered
# ---------------------------------------------------------------------------


class TestToastStructure:
    def test_contains_cond(self):
        """Top-level Cond drives show/hide based on toast_message."""
        comp = toast_notification()
        counts = collect_types(comp)
        assert counts["Cond"] >= 1

    def test_contains_box(self):
        """The visible toast body is a positioned Box."""
        comp = toast_notification()
        counts = collect_types(comp)
        assert counts["Box"] >= 1

    def test_contains_hstack(self):
        """Icon + message text + dismiss button live in an HStack."""
        comp = toast_notification()
        counts = collect_types(comp)
        assert counts["HStack"] >= 1

    def test_contains_text_node(self):
        """The message text is rendered via a Text node."""
        comp = toast_notification()
        counts = collect_types(comp)
        assert counts["Text"] >= 1

    def test_contains_dynamic_icon(self):
        """The alert/check icon is a DynamicIcon driven by toast_is_error."""
        comp = toast_notification()
        counts = collect_types(comp)
        assert counts["DynamicIcon"] >= 1

    def test_contains_dismiss_button(self):
        """An IconButton lets the user dismiss the toast manually."""
        comp = toast_notification()
        counts = collect_types(comp)
        assert counts["IconButton"] >= 1


# ---------------------------------------------------------------------------
# Event wiring — dismiss button calls AppState.clear_toast
# ---------------------------------------------------------------------------


class TestToastEventWiring:
    def test_dismiss_button_triggers_clear_toast(self):
        """The dismiss IconButton's on_click chain references clear_toast."""
        comp = toast_notification()
        icon_buttons = find_by_type(comp, "IconButton")
        assert icon_buttons, "No IconButton found in toast component"

        dismiss_btn = icon_buttons[0]
        triggers = getattr(dismiss_btn, "event_triggers", {})
        assert "on_click" in triggers, "IconButton has no on_click trigger"

        fn = event_handler_fn(triggers["on_click"])
        assert fn is AppState.clear_toast.fn, (
            f"Expected clear_toast, got {fn}"
        )


# ---------------------------------------------------------------------------
# State defaults — initial state shows no toast
# ---------------------------------------------------------------------------


class TestToastStateDefaults:
    def test_toast_message_default_is_empty_string(self):
        """toast_message == '' so the component renders empty at startup."""
        assert state_default("toast_message") == ""

    def test_toast_is_error_default_is_false(self):
        """toast_is_error == False so the initial colour is success (green)."""
        assert state_default("toast_is_error") is False

    def test_toast_message_var_exists_on_state(self):
        """AppState.toast_message is a Reflex Var (StringCastedVar)."""
        assert hasattr(AppState, "toast_message")
        assert "Var" in type(AppState.toast_message).__name__

    def test_toast_is_error_var_exists_on_state(self):
        """AppState.toast_is_error is a Reflex Var (BooleanCastedVar)."""
        assert hasattr(AppState, "toast_is_error")
        assert "Var" in type(AppState.toast_is_error).__name__


# ---------------------------------------------------------------------------
# AppState event handlers for toast
# ---------------------------------------------------------------------------


class TestToastStateHandlers:
    def test_clear_toast_is_event_handler(self):
        from reflex_base.event import EventHandler

        assert isinstance(AppState.clear_toast, EventHandler)

    def test_set_toast_is_event_handler(self):
        from reflex_base.event import EventHandler

        assert isinstance(AppState.set_toast, EventHandler)

    def test_clear_toast_fn_resets_fields(self):
        """clear_toast underlying function sets message='' and is_error=False."""
        # We call the raw function (bypassing the Reflex event system) to
        # verify the logic directly without needing a running state.
        import types

        # Build a minimal mock with the two relevant attributes
        class _MockState:
            toast_message = "some error"
            toast_is_error = True

        mock = _MockState()
        # Call the underlying function directly
        AppState.clear_toast.fn(mock)
        assert mock.toast_message == ""
        assert mock.toast_is_error is False

    def test_set_toast_fn_sets_fields(self):
        """set_toast underlying function updates message and is_error."""

        class _MockState:
            toast_message = ""
            toast_is_error = False

        mock = _MockState()
        AppState.set_toast.fn(mock, "Something went wrong", is_error=True)
        assert mock.toast_message == "Something went wrong"
        assert mock.toast_is_error is True

    def test_set_toast_fn_defaults_to_success(self):
        """set_toast with no is_error kwarg defaults to success (False)."""

        class _MockState:
            toast_message = ""
            toast_is_error = True

        mock = _MockState()
        AppState.set_toast.fn(mock, "Done!")
        assert mock.toast_message == "Done!"
        assert mock.toast_is_error is False
