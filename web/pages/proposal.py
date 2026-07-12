"""
web/pages/proposal.py — ProposalDetailPage.

Route: /proposal/[proposal_id]

Renders the full ``ReconciliationReport`` for a single proposal by fetching
GET /api/proposals/{proposal_id}/status. Fixes the reported 404: no page was
previously registered for this route, even though proposal_form.py's
proposals_list() already links to it ("View" button) once a proposal
completes.
"""

import reflex as rx

from web.state import AppState


def _header() -> rx.Component:
    return rx.hstack(
        rx.link(
            rx.hstack(
                rx.icon("arrow-left", size=14),
                rx.text("Back", size="2"),
                spacing="2",
                align="center",
            ),
            href="/",
        ),
        rx.spacer(),
        rx.heading("Proposal", size="6", weight="bold"),
        rx.spacer(),
        width="100%",
        align="center",
    )


def _not_found_view() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.icon("file-x", size=40, color="var(--gray-7)"),
            rx.text(
                "Proposal not found.",
                size="3",
                color_scheme="gray",
                text_align="center",
            ),
            spacing="3",
            align="center",
        ),
        padding="3rem",
        width="100%",
    )


def _status_pending_view() -> rx.Component:
    status = AppState.proposal_detail_status
    return rx.center(
        rx.vstack(
            rx.spinner(size="3"),
            rx.text(
                rx.fragment("Status: ", status),
                size="2",
                color_scheme="gray",
            ),
            rx.cond(
                AppState.proposal_detail_progress_message != "",
                rx.text(
                    AppState.proposal_detail_progress_message,
                    size="1",
                    color_scheme="gray",
                ),
                rx.fragment(),
            ),
            spacing="3",
            align="center",
        ),
        padding="3rem",
        width="100%",
    )


def _failed_view() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.icon("alert-circle", size=40, color="var(--red-9)"),
            rx.text("Proposal generation failed.", size="3", color_scheme="red"),
            rx.cond(
                AppState.proposal_detail_progress_message != "",
                rx.text(
                    AppState.proposal_detail_progress_message,
                    size="2",
                    color_scheme="gray",
                    text_align="center",
                ),
                rx.fragment(),
            ),
            spacing="3",
            align="center",
        ),
        padding="3rem",
        width="100%",
    )


def _report_view() -> rx.Component:
    report = AppState.proposal_detail_report
    return rx.vstack(
        rx.hstack(
            rx.icon("file-text", size=16, color="var(--gray-10)"),
            rx.text(
                "Executive Summary",
                size="1",
                weight="bold",
                color_scheme="gray",
                text_transform="uppercase",
                letter_spacing="0.08em",
            ),
            spacing="2",
            align="center",
        ),
        rx.text(report["executive_summary"].to(str), size="2"),
        rx.hstack(
            rx.text("Delivery Confidence:", size="2", weight="medium"),
            rx.badge(
                rx.fragment(report["delivery_confidence_score"].to(int).to(str), " / 100"),
                color_scheme=rx.cond(
                    report["delivery_confidence_score"].to(int) >= 60, "green", "red"
                ),
                variant="soft",
            ),
            rx.badge(
                rx.cond(
                    report["ready_for_approval"].to(bool),
                    "Ready for Approval",
                    "Needs Revision",
                ),
                color_scheme=rx.cond(
                    report["ready_for_approval"].to(bool), "green", "amber"
                ),
                variant="soft",
            ),
            spacing="3",
            align="center",
        ),
        rx.cond(
            report["critical_conflicts"].to(list[str]).length() > 0,
            rx.vstack(
                rx.text("Critical Conflicts", size="1", weight="bold", color_scheme="gray"),
                rx.unordered_list(
                    rx.foreach(
                        report["critical_conflicts"].to(list[str]),
                        lambda item: rx.list_item(item, size="2"),
                    ),
                ),
                spacing="2",
                align="start",
                width="100%",
            ),
            rx.fragment(),
        ),
        rx.cond(
            report["architectural_risks"].to(list[str]).length() > 0,
            rx.vstack(
                rx.text("Architectural Risks", size="1", weight="bold", color_scheme="gray"),
                rx.unordered_list(
                    rx.foreach(
                        report["architectural_risks"].to(list[str]),
                        lambda item: rx.list_item(item, size="2"),
                    ),
                ),
                spacing="2",
                align="start",
                width="100%",
            ),
            rx.fragment(),
        ),
        rx.cond(
            report["actionable_recommendations"].to(list[str]).length() > 0,
            rx.vstack(
                rx.text("Recommendations", size="1", weight="bold", color_scheme="gray"),
                rx.unordered_list(
                    rx.foreach(
                        report["actionable_recommendations"].to(list[str]),
                        lambda rec: rx.list_item(rec, size="2"),
                    ),
                ),
                spacing="2",
                align="start",
                width="100%",
            ),
            rx.fragment(),
        ),
        spacing="4",
        align="start",
        width="100%",
        padding="1.5rem",
        background="var(--gray-2)",
        border="1px solid var(--gray-4)",
        border_radius="8px",
    )


def proposal_page() -> rx.Component:
    return rx.center(
        rx.box(
            rx.vstack(
                _header(),
                rx.separator(width="100%"),
                rx.cond(
                    AppState.proposal_detail_loading,
                    rx.center(rx.spinner(size="3"), padding="3rem", width="100%"),
                    rx.cond(
                        AppState.proposal_detail_not_found,
                        _not_found_view(),
                        rx.cond(
                            AppState.proposal_detail_status == "complete",
                            _report_view(),
                            rx.cond(
                                AppState.proposal_detail_status == "failed",
                                _failed_view(),
                                _status_pending_view(),
                            ),
                        ),
                    ),
                ),
                spacing="5",
                align="start",
                width="100%",
            ),
            max_width="720px",
            width="100%",
            padding="2rem",
            background="var(--gray-1)",
            border="1px solid var(--gray-4)",
            border_radius="12px",
        ),
        width="100vw",
        height="100vh",
        background="var(--gray-2)",
    )


# Registering the dynamic route via @rx.page adds ``proposal_id`` as an
# auto-populated AppState var (Reflex convention for [proposal_id] segments).
proposal_page = rx.page(
    route="/proposal/[proposal_id]",
    on_load=AppState.load_proposal_detail,
    title="Proposal — SAE",
)(proposal_page)
