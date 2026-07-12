"""
web/components/insights_sidebar.py — Insights Sidebar (Gap 10).

A collapsible sidebar section displaying top advisory hints
from global_client_insights, ordered by frequency_count.
"""

import reflex as rx

from web.state import AppState


def _insight_card(insight: dict) -> rx.Component:
    """A single insight card displaying tag, pattern, and frequency."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.badge(
                    insight["client_or_industry_tag"],
                    color_scheme="blue",
                    variant="soft",
                    size="1",
                ),
                rx.spacer(),
                rx.icon("trending-up", size=14, color="var(--gray-9)"),
                spacing="2",
                align="center",
                width="100%",
            ),
            rx.text(
                insight["observed_pattern"],
                size="2",
                weight="medium",
                color_scheme="gray",
            ),
            rx.hstack(
                rx.text("Frequency:", size="1", color_scheme="gray"),
                rx.text(
                    insight["frequency_count"].to(str),
                    size="1",
                    weight="bold",
                    color_scheme="indigo",
                ),
                rx.text(
                    "Updated: " + insight["last_updated"].to(str)[:10],
                    size="1",
                    color_scheme="gray",
                ),
                spacing="2",
                align="center",
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        padding="0.75rem",
        background="var(--gray-2)",
        border="1px solid var(--gray-4)",
        border_radius="6px",
        width="100%",
    )


def insights_sidebar() -> rx.Component:
    """Collapsible sidebar section for global client insights.
    
    Gap 10 — Requirements 10.4-10.6: displays advisory cards
    with tag, pattern, and frequency for each insight. Badge
    on header indicates number of available insights.
    """
    return rx.box(
        rx.box(
            rx.accordion.root(
                rx.accordion.item(
                    header=rx.hstack(
                        rx.icon("lightbulb", size=16, color="var(--gray-9)"),
                        rx.text(
                            "Advisory Insights",
                            size="2",
                            weight="medium",
                        ),
                        rx.spacer(),
                        rx.badge(
                            AppState.insights.length().to(str),
                            color_scheme="indigo",
                            variant="solid",
                            size="1",
                        ),
                        spacing="3",
                        align="center",
                        width="100%",
                    ),
                    content=rx.cond(
                        AppState.insights.length() > 0,
                        rx.vstack(
                            rx.foreach(
                                AppState.insights,
                                _insight_card,
                            ),
                            spacing="2",
                            width="100%",
                        ),
                        rx.text(
                            "No insights available yet.",
                            size="2",
                            color_scheme="gray",
                        ),
                    ),
                    value="insights",
                ),
                default_value="insights",
                width="100%",
                variant="classic",
            ),
            width="100%",
        ),
        width="100%",
        background="var(--gray-1)",
        border="1px solid var(--gray-4)",
        border_radius="12px",
    )
