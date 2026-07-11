"""
web/components/review_link_selector.py — Review Link Selector (Gap 1).

A chip-selector component for selecting prior completed reviews
to link as context for a new review run.
"""

import reflex as rx

from web.state import AppState


def _review_link_chip(review: dict) -> rx.Component:
    """A single review link chip with toggle behavior."""
    is_selected = AppState.selected_linked_review_ids.contains(review["review_id"])
    return rx.badge(
        rx.hstack(
            rx.text(review["persona"], size="1", weight="medium"),
            rx.text("•", size="1"),
            rx.text(review["run_date"][:10], size="1", color_scheme="gray"),
            spacing="1",
            align="center",
        ),
        variant="solid",
        color_scheme=rx.cond(is_selected, "indigo", "gray"),
        size="2",
        cursor="pointer",
        on_click=AppState.toggle_linked_review(review["review_id"]),
        _hover={"opacity": 0.8},
    )


def review_link_selector(version_id: str) -> rx.Component:
    """Chip selector for prior completed reviews to link as context.
    
    Gap 1 — Requirements 1.6/1.7: displays linkable reviews from
    the /api/versions/{version_id}/reviews/linkable endpoint and
    includes selected review IDs in linked_review_ids when submitting
    a new review.
    
    Args:
        version_id: The version to fetch linkable reviews for.
    """
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("link", size=16, color="var(--gray-9)"),
                rx.text("Link Prior Reviews (Optional)", size="2", weight="medium"),
                spacing="2",
                align="center",
            ),
            rx.cond(
                AppState.linkable_reviews.length() > 0,
                rx.box(
                    rx.foreach(
                        AppState.linkable_reviews,
                        _review_link_chip,
                    ),
                    rx.divider(height="1rem"),
                ),
                rx.text(
                    "No completed reviews available to link.",
                    size="2",
                    color_scheme="gray",
                ),
            ),
            spacing="2",
            width="100%",
        ),
        width="100%",
        padding="1rem",
        background="var(--gray-1)",
        border="1px solid var(--gray-4)",
        border_radius="8px",
    )
