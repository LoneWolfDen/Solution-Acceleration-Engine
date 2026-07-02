"""
web/components/review_detail.py — ReviewDetailPane.

Shows finding summary counts and a scrollable FindingCard list.
Uses AppState computed vars (current_findings, finding_counts,
selected_node_name, selected_node_status, selected_node_persona)
so no raw dict access happens inside components.
"""

import reflex as rx

from web.state import AppState
from web.components.finding_card import finding_card
from web.components.status_banner import proposal_status_banner


def _count_pill(label: str, count: rx.Var, color: str) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(count, size="6", weight="bold", color=color),
            rx.text(label, size="1", color_scheme="gray", weight="medium"),
            align="center",
            spacing="1",
        ),
        padding="1rem 1.25rem",
        background="var(--gray-2)",
        border=f"1px solid {color}40",
        border_radius="8px",
        text_align="center",
        min_width="80px",
    )


def _summary_bar() -> rx.Component:
    counts = AppState.finding_counts
    return rx.hstack(
        _count_pill("Risks", counts["risks"], "#ef4444"),
        _count_pill("Constraints", counts["constraints"], "#f59e0b"),
        _count_pill("Dependencies", counts["dependencies"], "#3b82f6"),
        _count_pill("Assumptions", counts["assumptions"], "#8b5cf6"),
        _count_pill("Actions", counts["action_items"], "#22c55e"),
        spacing="3",
        flex_wrap="wrap",
    )


def _review_header() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.icon("scan-search", size=20, color="var(--accent-9)"),
            rx.vstack(
                rx.heading(
                    rx.fragment("Review #", AppState.selected_node_name),
                    size="5",
                    weight="bold",
                ),
                rx.hstack(
                    rx.badge(
                        AppState.selected_node_status,
                        color_scheme=rx.cond(
                            AppState.selected_node_status == "complete",
                            "green",
                            rx.cond(AppState.selected_node_status == "failed", "red", "blue"),
                        ),
                        variant="soft",
                    ),
                    rx.badge(AppState.selected_node_persona, color_scheme="purple", variant="soft"),
                    spacing="2",
                    align="center",
                ),
                spacing="1",
                align="start",
            ),
            spacing="3",
            align="start",
        ),
        padding_bottom="1rem",
        border_bottom="1px solid var(--gray-4)",
        width="100%",
    )


def _proposal_report_view(report: rx.Var) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("file-text", size=14, color="var(--gray-10)"),
            rx.text(
                "Executive Summary", size="1", weight="bold", color_scheme="gray",
                text_transform="uppercase", letter_spacing="0.08em",
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
        spacing="3",
        align="start",
        width="100%",
        padding="1rem",
        background="var(--gray-2)",
        border="1px solid var(--gray-4)",
        border_radius="8px",
    )


def _proposal_pane() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("sparkles", size=14, color="var(--gray-10)"),
            rx.text(
                "Proposal",
                size="1",
                weight="bold",
                color_scheme="gray",
                text_transform="uppercase",
                letter_spacing="0.08em",
            ),
            spacing="2",
            align="center",
        ),
        proposal_status_banner(),
        rx.cond(
            AppState.current_proposal_exists,
            rx.cond(
                AppState.current_proposal_status == "complete",
                _proposal_report_view(AppState.current_proposal_report),
                rx.fragment(),
            ),
            rx.button(
                rx.icon("sparkles", size=13),
                "Generate Proposal",
                variant="soft",
                color_scheme="indigo",
                disabled=AppState.selected_node_status != "complete",
                on_click=AppState.generate_proposal,
            ),
        ),
        spacing="3",
        align="start",
        width="100%",
    )


def review_detail_pane() -> rx.Component:
    return rx.box(
        rx.scroll_area(
            rx.vstack(
                _review_header(),
                _summary_bar(),
                rx.hstack(
                    rx.icon("list", size=14, color="var(--gray-10)"),
                    rx.text(
                        rx.fragment(AppState.current_findings.length(), " Findings"),
                        size="1",
                        weight="bold",
                        color_scheme="gray",
                        text_transform="uppercase",
                        letter_spacing="0.08em",
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.cond(
                    AppState.current_findings.length() > 0,
                    rx.vstack(
                        rx.foreach(AppState.current_findings, finding_card),
                        spacing="3",
                        width="100%",
                    ),
                    rx.center(
                        rx.vstack(
                            rx.icon("inbox", size=40, color="var(--gray-7)"),
                            rx.text(
                                "No findings recorded for this review.",
                                size="2",
                                color_scheme="gray",
                                text_align="center",
                            ),
                            spacing="3",
                            align="center",
                        ),
                        padding="3rem",
                        width="100%",
                    ),
                ),
                rx.separator(width="100%"),
                _proposal_pane(),
                spacing="4",
                align="start",
                width="100%",
                padding="1.5rem",
            ),
            width="100%",
            height="100vh",
            type="auto",
        ),
        width="100%",
        height="100vh",
        overflow="hidden",
    )
