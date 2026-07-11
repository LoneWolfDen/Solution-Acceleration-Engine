"""
web/components/proposal_form.py — Proposal Form (Gap 2).

A form for selecting multiple completed reviews to generate
a multi-review proposal. Displays the list of completed reviews
for the current version and allows multi-selection.
"""

import reflex as rx

from web.state import AppState


def _review_checkbox(review: dict) -> rx.Component:
    """A checkbox for selecting a review to include in proposal."""
    return rx.hstack(
        rx.checkbox(
            checked=AppState.selected_linked_review_ids.contains(review["review_id"]),
            on_change=lambda checked: rx.cond(
                checked,
                AppState.selected_linked_review_ids.set(
                    AppState.selected_linked_review_ids + [review["review_id"]]
                ),
                AppState.selected_linked_review_ids.set(
                    AppState.selected_linked_review_ids.filter(
                        lambda rid: rid != review["review_id"]
                    )
                ),
            ),
        ),
        rx.vstack(
            rx.text(review["persona"], size="2", weight="medium"),
            rx.text(
                f"Completed: {review['run_date'][:10]}",
                size="1",
                color_scheme="gray",
            ),
            spacing="0",
            align="start",
        ),
        spacing="3",
        align="center",
        padding="0.5rem 0.75rem",
        background="var(--gray-2)",
        border="1px solid var(--gray-4)",
        border_radius="6px",
        width="100%",
    )


def proposal_form(version_id: str) -> rx.Component:
    """Form to select reviews and generate a multi-review proposal.
    
    Gap 2 — Requirements 2.7/2.8: displays completed reviews for
    the current version, allows multi-selection, and submits to
    /api/versions/{version_id}/proposals endpoint.
    
    Gap 11 — Requirements 11.3-11.6: displays the proposals list
    after generation with status indicators and polling.
    
    Args:
        version_id: The version to generate proposals for.
    """
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("file-text", size=16, color="var(--gray-9)"),
                rx.text("Generate Proposal", size="2", weight="medium"),
                rx.spacer(),
                rx.cond(
                    AppState.version_proposals.length() > 0,
                    rx.badge(
                        AppState.version_proposals.length().to(str),
                        color_scheme="indigo",
                        variant="solid",
                        size="1",
                    ),
                    rx.badge("0", color_scheme="gray", variant="soft", size="1"),
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            rx.divider(width="100%"),
            # Completed reviews for selection
            rx.cond(
                AppState.linkable_reviews.length() > 0,
                rx.vstack(
                    rx.foreach(
                        AppState.linkable_reviews,
                        _review_checkbox,
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.text(
                    "No completed reviews available to generate proposals.",
                    size="2",
                    color_scheme="gray",
                ),
            ),
            rx.divider(width="100%"),
            # Generate button
            rx.button(
                rx.cond(
                    AppState.is_loading,
                    rx.spinner(size="2"),
                    rx.icon("zap", size=14),
                ),
                "Generate Proposal",
                color_scheme="indigo",
                size="3",
                width="100%",
                disabled=~AppState.is_loading & (AppState.linkable_reviews.length() == 0),
                on_click=AppState.submit_version_proposal(
                    version_id, AppState.selected_linked_review_ids
                ),
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
        padding="1.5rem",
        background="var(--gray-1)",
        border="1px solid var(--gray-4)",
        border_radius="12px",
    )


def proposals_list(version_id: str) -> rx.Component:
    """List of proposals generated for a version.
    
    Gap 11 — Requirements 11.3-11.6: displays proposals with
    status indicators, linked review count, and polling for
    non-terminal states.
    
    Args:
        version_id: The version to list proposals for.
    """
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("git-branch", size=16, color="var(--gray-9)"),
                rx.text("Proposal History", size="2", weight="medium"),
                spacing="3",
                align="center",
                width="100%",
            ),
            rx.divider(width="100%"),
            rx.cond(
                AppState.version_proposals.length() > 0,
                rx.vstack(
                    rx.foreach(
                        AppState.version_proposals,
                        lambda p: rx.vstack(
                            rx.hstack(
                                rx.icon(
                                    rx.cond(
                                        p["status"] == "complete",
                                        "check-circle",
                                        rx.cond(
                                            p["status"] == "failed",
                                            "alert-circle",
                                            "loader",
                                        ),
                                    ),
                                    size=16,
                                    color=rx.cond(
                                        p["status"] == "complete",
                                        "var(--green-9)",
                                        rx.cond(
                                            p["status"] == "failed",
                                            "var(--red-9)",
                                            "var(--blue-9)",
                                        ),
                                    ),
                                ),
                                rx.vstack(
                                    rx.text(
                                        f"Proposal • {p['linked_review_count']} review(s)",
                                        size="2",
                                        weight="medium",
                                    ),
                                    rx.hstack(
                                        rx.badge(
                                            p["status"],
                                            color_scheme=rx.cond(
                                                p["status"] == "complete",
                                                "green",
                                                rx.cond(
                                                    p["status"] == "failed",
                                                    "red",
                                                    "blue",
                                                ),
                                            ),
                                            variant="soft",
                                            size="1",
                                        ),
                                        rx.text(
                                            p["created_at"][:10],
                                            size="1",
                                            color_scheme="gray",
                                        ),
                                        spacing="2",
                                        align="center",
                                    ),
                                    spacing="0",
                                    align="start",
                                ),
                                rx.spacer(),
                                rx.cond(
                                    p["status"] == "complete",
                                    rx.link(
                                        rx.button(
                                            "View",
                                            size="1",
                                            variant="soft",
                                            color_scheme="indigo",
                                        ),
                                        href=f"/proposal/{p['proposal_id']}",
                                    ),
                                    rx.text("", width="0"),
                                ),
                                spacing="3",
                                align="center",
                                width="100%",
                            ),
                            padding="0.75rem",
                            background="var(--gray-2)",
                            border="1px solid var(--gray-4)",
                            border_radius="6px",
                            width="100%",
                        ),
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.text(
                    "No proposals generated for this version yet.",
                    size="2",
                    color_scheme="gray",
                ),
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
        padding="1.5rem",
        background="var(--gray-1)",
        border="1px solid var(--gray-4)",
        border_radius="12px",
    )
