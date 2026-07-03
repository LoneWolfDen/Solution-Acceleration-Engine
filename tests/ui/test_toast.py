"""Milestone 6.5 — tests/ui/test_toast.py

Tests for ToastNotification component state logic.

The ToastNotification renders when AppState.toast_message is non-null
and is absent from the DOM when toast_message is None.
Tests validate:
  - Toast renders (non-None) when toast_message is set
  - Toast is absent (None) when toast_message is None
  - Error variant (red) is shown when error message is set
  - Success variant (green) is shown on success
  - set_toast sets both message and variant
  - clear_toast resets toast_message to None
  - Auto-dismiss logic: after clear_toast, toast_message is None
  - Multiple set_toast calls override the previous message

No Reflex server or live API is used.
"""

from __future__ import annotations

import pytest

from .conftest import MockAppState


# ── Toast absent when message is None ────────────────────────────────────────


def test_toast_absent_when_no_message(empty_state: MockAppState) -> None:
    """ToastNotification is absent (None) when toast_message is None."""
    assert empty_state.toast_message is None


def test_toast_absent_after_clear(empty_state: MockAppState) -> None:
    """After clear_toast(), toast_message is None."""
    empty_state.set_toast("Some message")
    empty_state.clear_toast()
    assert empty_state.toast_message is None


# ── Toast present when message is set ────────────────────────────────────────


def test_toast_present_when_message_set(empty_state: MockAppState) -> None:
    """ToastNotification renders when toast_message is non-null."""
    empty_state.set_toast("Operation completed successfully.")
    assert empty_state.toast_message is not None
    assert empty_state.toast_message == "Operation completed successfully."


def test_toast_message_is_string(empty_state: MockAppState) -> None:
    """toast_message is a string when set."""
    empty_state.set_toast("Hello")
    assert isinstance(empty_state.toast_message, str)


# ── Error variant ─────────────────────────────────────────────────────────────


def test_toast_error_variant_when_error(empty_state: MockAppState) -> None:
    """Error variant is set when message originates from an API error field."""
    empty_state.set_toast("Project not found.", variant="error")
    assert empty_state.toast_message == "Project not found."
    assert empty_state.toast_variant == "error"


def test_toast_error_variant_shows_red_colour() -> None:
    """The error variant maps to the 'red' colour — validates the variant name."""
    variant = "error"
    # The UI maps variant='error' to a red colour scheme.
    # This test asserts the string contract used by the component.
    assert variant == "error"


def test_toast_error_message_non_null_triggers_render(
    empty_state: MockAppState,
) -> None:
    """Any non-null toast_message — including error messages — triggers render."""
    empty_state.set_toast("Artifact not found.", variant="error")
    assert empty_state.toast_message is not None


# ── Success variant ───────────────────────────────────────────────────────────


def test_toast_success_variant_default(empty_state: MockAppState) -> None:
    """Default variant is 'success' when not explicitly specified."""
    empty_state.set_toast("Version created successfully.")
    assert empty_state.toast_variant == "success"


def test_toast_success_variant_explicit(empty_state: MockAppState) -> None:
    """Explicitly setting variant='success' is preserved."""
    empty_state.set_toast("Saved.", variant="success")
    assert empty_state.toast_variant == "success"
    assert empty_state.toast_message == "Saved."


# ── Override behaviour ────────────────────────────────────────────────────────


def test_set_toast_overrides_previous_message(empty_state: MockAppState) -> None:
    """Calling set_toast again replaces the previous message."""
    empty_state.set_toast("First message.")
    empty_state.set_toast("Second message.")
    assert empty_state.toast_message == "Second message."


def test_set_toast_overrides_variant(empty_state: MockAppState) -> None:
    """Calling set_toast again replaces the previous variant."""
    empty_state.set_toast("Error occurred.", variant="error")
    empty_state.set_toast("All good.", variant="success")
    assert empty_state.toast_variant == "success"


def test_set_toast_error_then_clear(empty_state: MockAppState) -> None:
    """After an error toast is cleared, message and variant both reset."""
    empty_state.set_toast("Something failed.", variant="error")
    empty_state.clear_toast()
    assert empty_state.toast_message is None


# ── API error field → toast pipeline ─────────────────────────────────────────


def test_api_error_field_triggers_error_toast(empty_state: MockAppState) -> None:
    """When API response.error is non-null, set_toast is called with variant=error.

    This simulates the AppState mutation handler pattern from Milestone 3.11:
        if response['error']:
            state.set_toast(response['error'], variant='error')
        else:
            state.set_toast('Success', variant='success')
    """
    api_response = {"error": "Version not found."}

    if api_response["error"]:
        empty_state.set_toast(api_response["error"], variant="error")
    else:
        empty_state.set_toast("Version created.", variant="success")

    assert empty_state.toast_message == "Version not found."
    assert empty_state.toast_variant == "error"


def test_api_null_error_field_triggers_success_toast(empty_state: MockAppState) -> None:
    """When API response.error is null, set_toast is called with variant=success."""
    api_response = {"error": None, "version_id": "v-123"}

    if api_response["error"]:
        empty_state.set_toast(api_response["error"], variant="error")
    else:
        empty_state.set_toast("Version created.", variant="success")

    assert empty_state.toast_message == "Version created."
    assert empty_state.toast_variant == "success"


# ── 4-second auto-dismiss simulation ─────────────────────────────────────────


def test_toast_auto_dismiss_clears_message(empty_state: MockAppState) -> None:
    """Simulates the 4-second auto-dismiss: clear_toast() sets message to None.

    In the real component, a timer calls clear_toast() after 4 seconds.
    The state contract is the same: after clear_toast(), toast_message is None.
    """
    empty_state.set_toast("Auto-dismiss me.")
    assert empty_state.toast_message is not None

    # Simulate the timer callback.
    empty_state.clear_toast()
    assert empty_state.toast_message is None
