"""
web/components/version_detail.py — VersionDetailPane.

Shows linked artifacts table, reviews list, and review nodes.
Uses bracket notation (not .get()) for all Reflex Var dict access
to be compile-safe inside rx.foreach callbacks.
"""

import reflex as rx

from web.state import AppState


def _artifact_row(artifact: dict) -> rx.Component:
    return rx.hstack(
        rx.icon("file-text", size=14, color="var(--gray-9)", flex_shrink="0"),
        rx.vstack(
            rx.text(artifact["title"], size="2", weight="medium", truncate=True),
            rx.hstack(
                rx.foreach(
                    artifact["tags"],
                    lambda tag: rx.badge(tag, color_scheme="blue", variant="soft", size="1"),
                ),
                spacing="1",
                flex_wrap="wrap",
            ),
            spacing="1",
            align="start",
            flex="1",
            min_width="0",
        ),
        rx.badge(
            rx.cond(artifact["is_active"], "Active", "Inactive"),
            color_scheme=rx.cond(artifact["is_active"], "green", "gray"),
            variant="soft",
            flex_shrink="0",
        ),
        spacing="3",
        align="center",
        width="100%",
        padding="0.625rem 0.75rem",
        background="var(--gray-2)",
        border="1px solid var(--gray-4)",
        border_radius="6px",
    )


def _review_row(review: dict) -> rx.Component:
    return rx.hstack(
        rx.icon("git-branch", size=14, color="var(--gray-9)", flex_shrink="0"),
        rx.vstack(
            rx.text(review["persona"], size="2", weight="medium"),
            rx.text(
                review["run_date"],
                size="1",
                color_scheme="gray",
                font_family="monospace",
            ),
            spacing="1",
            align="start",
            flex="1",
        ),
        rx.badge(
            review["status"],
            color_scheme=rx.cond(
                review["status"] == "complete",
                "green",
                rx.cond(review["status"] == "failed", "red", "blue"),
            ),
            variant="soft",
            flex_shrink="0",
        ),
        spacing="3",
        align="center",
        width="100%",
        padding="0.625rem 0.75rem",
        background="var(--gray-2)",
        border="1px solid var(--gray-4)",
        border_radius="6px",
    )


def _node_row(node: dict) -> rx.Component:
    is_selected = AppState.selected_node_id == node["id"]
    return rx.box(
        rx.hstack(
            rx.icon(
                "circle-dot",
                size=14,
                color=rx.cond(is_selected, "var(--accent-9)", "var(--gray-9)"),
                flex_shrink="0",
            ),
            rx.vstack(
                rx.text(
                    node["node_name"],
                    size="2",
                    weight=rx.cond(is_selected, "bold", "regular"),
                    color=rx.cond(is_selected, "var(--accent-11)", "var(--gray-12)"),
                ),
                rx.hstack(
                    rx.badge(node["layer_type"], color_scheme="indigo", variant="soft", size="1"),
                    rx.text(
                        node["created_at"],
                        size="1",
                        color_scheme="gray",
                        font_family="monospace",
                    ),
                    spacing="2",
                    align="center",
                ),
                spacing="1",
                align="start",
            ),
            rx.icon("chevron-right", size=14, color="var(--gray-8)", flex_shrink="0"),
            justify="between",
            align="center",
            width="100%",
        ),
        padding="0.75rem",
        background=rx.cond(is_selected, "var(--accent-3)", "var(--gray-2)"),
        border="1px solid",
        border_color=rx.cond(is_selected, "var(--accent-6)", "var(--gray-4)"),
        border_radius="6px",
        cursor="pointer",
        width="100%",
        on_click=AppState.select_node(node["id"]),
        _hover={"background": "var(--accent-2)", "border_color": "var(--accent-6)"},
    )


def _section_label(icon_name: str, label: str) -> rx.Component:
    return rx.hstack(
        rx.icon(icon_name, size=14, color="var(--gray-9)"),
        rx.text(
            label,
            size="1",
            weight="bold",
            color_scheme="gray",
            text_transform="uppercase",
            letter_spacing="0.08em",
        ),
        spacing="2",
        align="center",
    )


def version_detail() -> rx.Component:
    version = AppState.current_version
    return rx.box(
        rx.scroll_area(
            rx.vstack(
                # Header
                rx.box(
                    rx.hstack(
                        rx.icon("layers", size=20, color="var(--accent-9)"),
                        rx.vstack(
                            rx.heading(version["name"], size="5", weight="bold"),
                            rx.text(
                                version["created_at"],
                                size="1",
                                color_scheme="gray",
                                font_family="monospace",
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
                ),

                # Linked artifacts
                rx.vstack(
                    _section_label("paperclip", "Linked Artifacts"),
                    rx.cond(
                        version["artifacts"].length() > 0,
                        rx.vstack(
                            rx.foreach(version["artifacts"], _artifact_row),
                            spacing="2",
                            width="100%",
                        ),
                        rx.text("No artifacts linked to this version.", size="2", color_scheme="gray"),
                    ),
                    spacing="2",
                    align="start",
                    width="100%",
                ),

                # Reviews
                rx.vstack(
                    _section_label("activity", "Review Runs"),
                    rx.cond(
                        AppState.selected_version_reviews.length() > 0,
                        rx.vstack(
                            rx.foreach(AppState.selected_version_reviews, _review_row),
                            spacing="2",
                            width="100%",
                        ),
                        rx.text("No reviews run for this version yet.", size="2", color_scheme="gray"),
                    ),
                    spacing="2",
                    align="start",
                    width="100%",
                ),

                # Review Nodes
                rx.vstack(
                    _section_label("git-branch", "Review Nodes"),
                    rx.cond(
                        AppState.nodes_for_selected_version.length() > 0,
                        rx.vstack(
                            rx.foreach(AppState.nodes_for_selected_version, _node_row),
                            spacing="2",
                            width="100%",
                        ),
                        rx.text("No review nodes for this version yet.", size="2", color_scheme="gray"),
                    ),
                    spacing="2",
                    align="start",
                    width="100%",
                ),

                spacing="5",
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
