"""
web/components/status_banner.py — AsyncStatusBanner (Milestone 4.4 / 4.5).

Renders the live status of an async review or proposal job.  The polling
itself happens server-side in AppState (start_review_status_poll /
start_proposal_status_poll — background tasks); this component is a pure
renderer that reads the resulting state vars and displays one of four
visual states:

  queued    — grey badge + clock icon
  running   — blue badge + spinner
  complete  — green badge + check icon
  failed    — red badge + alert icon, shows progress_message as the error

Two variants are exposed:
  review_status_banner()   — reads AppState.active_review_*
  proposal_status_banner() — reads AppState.active_proposal_*
"""

import reflex as rx

from web.state import AppState

_STATUS_COLOR: dict[str, str] = {
    "queued": "gray",
    "running": "blue",
    "complete": "green",
    "failed": "red",
}


def _status_icon(status: rx.Var) -> rx.Component:
    return rx.match(
        status,
        ("queued", rx.icon("clock", size=14)),
        ("running", rx.spinner(size="1")),
        ("complete", rx.icon("circle-check", size=14)),
        ("failed", rx.icon("circle-alert", size=14)),
        rx.icon("circle-dashed", size=14),
    )


def _status_color(status: rx.Var) -> rx.Var:
    return rx.match(
        status,
        ("queued", "gray"),
        ("running", "blue"),
        ("complete", "green"),
        ("failed", "red"),
        "gray",
    )


def _dismiss_button(handler) -> rx.Component:
    return rx.icon_button(
        rx.icon("x", size=12),
        size="1",
        variant="ghost",
        color_scheme="gray",
        on_click=handler,
    )


def _banner(
    label: str,
    status: rx.Var,
    progress_message: rx.Var,
    dismiss_slot: rx.Component,
) -> rx.Component:
    color = _status_color(status)
    return rx.box(
        rx.hstack(
            _status_icon(status),
            rx.vstack(
                rx.hstack(
                    rx.text(label, size="2", weight="bold"),
                    rx.badge(status, color_scheme=color, variant="soft", size="1"),
                    spacing="2",
                    align="center",
                ),
                rx.cond(
                    progress_message != "",
                    rx.text(progress_message, size="1", color_scheme="gray"),
                    rx.fragment(),
                ),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.cond(
                (status == "complete") | (status == "failed"),
                dismiss_slot,
                rx.fragment(),
            ),
            spacing="3",
            align="center",
            width="100%",
        ),
        padding="0.75rem 1rem",
        background=f"var(--{color}-3)",
        border=f"1px solid var(--{color}-6)",
        border_radius="8px",
        width="100%",
    )


def review_status_banner() -> rx.Component:
    """Status banner for the active review job (Milestone 4.4 / 4.5)."""
    return rx.cond(
        AppState.active_review_id != "",
        _banner(
            "Review",
            AppState.active_review_status,
            AppState.active_review_progress_message,
            _dismiss_button(AppState.dismiss_review_status),
        ),
        rx.fragment(),
    )


def proposal_status_banner() -> rx.Component:
    """Status banner for the active proposal job (Milestone 4.7 / 4.8).

    No dismiss action — the proposal result is expected to remain visible
    within the ProposalPane once complete, so an empty fragment is used.
    """
    return rx.cond(
        AppState.active_proposal_id != "",
        _banner(
            "Proposal",
            AppState.active_proposal_status,
            AppState.active_proposal_progress_message,
            rx.fragment(),
        ),
        rx.fragment(),
    )
