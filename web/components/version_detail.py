"""
web/components/version_detail.py — VersionDetailPane.

Shows linked artifacts table, reviews list, and review nodes.
Uses bracket notation (not .get()) for all Reflex Var dict access
to be compile-safe inside rx.foreach callbacks.
"""

import reflex as rx

from web.state import AppState


def _trigger_review_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Trigger Review"),
            rx.dialog.description(
                "Select a reviewer persona for this analysis run.",
                size="2",
                color_scheme="gray",
                margin_bottom="1rem",
            ),
            rx.vstack(
                rx.select.root(
                    rx.select.trigger(placeholder="Select persona…"),
                    rx.select.content(
                        rx.select.item("Solution Architect", value="Solution Architect"),
                        rx.select.item("Commercial Manager", value="Commercial Manager"),
                        rx.select.item("Risk Manager", value="Risk Manager"),
                        rx.select.item("Delivery Lead", value="Delivery Lead"),
                        rx.select.item("Technical Lead", value="Technical Lead"),
                    ),
                    value=AppState.review_persona,
                    on_change=AppState.set_review_persona,
                    width="100%",
                ),
                rx.hstack(
                    rx.button(
                        "Cancel",
                        variant="soft",
                        color_scheme="gray",
                        on_click=AppState.close_review_trigger,
                    ),
                    rx.button(
                        rx.icon("play", size=13),
                        "Run Review",
                        color_scheme="indigo",
                        on_click=AppState.trigger_review,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            max_width="420px",
            padding="1.5rem",
        ),
        open=AppState.review_trigger_open,
        on_open_change=AppState.close_review_trigger,
    )


def _artifact_row(artifact: dict) -> rx.Component:
    return rx.hstack(
        rx.icon("file-text", size=14, color="var(--gray-9)", flex_shrink="0"),
        rx.vstack(
            rx.text(artifact["title"], size="2",
                    weight="medium", truncate=True),
            rx.hstack(
                rx.foreach(
                    artifact["tags"].to(list[str]),
                    lambda tag: rx.badge(
                        tag, color_scheme="blue", variant="soft", size="1"),
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
    is_selected = AppState.selected_node_id == review["review_id"]
    return rx.hstack(
        rx.icon("git-branch", size=14, color=rx.cond(is_selected, "var(--accent-9)", "var(--gray-9)"), flex_shrink="0"),
        rx.vstack(
            rx.text(review["persona"], size="2", weight="medium",
                    color=rx.cond(is_selected, "var(--accent-11)", "inherit")),
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
        background=rx.cond(is_selected, "var(--accent-3)", "var(--gray-2)"),
        border="1px solid",
        border_color=rx.cond(is_selected, "var(--accent-6)", "var(--gray-4)"),
        border_radius="6px",
        cursor="pointer",
        on_click=AppState.select_node(review["review_id"]),
        _hover={"background": "var(--accent-2)", "border_color": "var(--accent-6)"},
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
                    color=rx.cond(is_selected, "var(--accent-11)",
                                  "var(--gray-12)"),
                ),
                rx.hstack(
                    rx.badge(node["layer_type"], color_scheme="indigo",
                             variant="soft", size="1"),
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
            rx.icon("chevron-right", size=14,
                    color="var(--gray-8)", flex_shrink="0"),
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
        _hover={"background": "var(--accent-2)",
                "border_color": "var(--accent-6)"},
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
        _trigger_review_dialog(),
        rx.scroll_area(
            rx.vstack(
                # Header
                rx.box(
                    rx.hstack(
                        rx.icon("layers", size=20, color="var(--accent-9)"),
                        rx.vstack(
                            rx.heading(version["name"],
                                       size="5", weight="bold"),
                            rx.text(
                                version["created_at"],
                                size="1",
                                color_scheme="gray",
                                font_family="monospace",
                            ),
                            spacing="1",
                            align="start",
                            flex="1",
                        ),
                        rx.button(
                            rx.icon("play", size=13),
                            "Trigger Review",
                            size="1",
                            variant="soft",
                            color_scheme="indigo",
                            on_click=AppState.open_review_trigger,
                            flex_shrink="0",
                        ),
                        spacing="3",
                        align="center",
                        width="100%",
                    ),
                    padding_bottom="1rem",
                    border_bottom="1px solid var(--gray-4)",
                    width="100%",
                ),

                # Linked artifacts
                rx.vstack(
                    _section_label("paperclip", "Linked Artifacts"),
                    rx.cond(
                        AppState.current_version_artifacts.length() > 0,
                        rx.vstack(
                            rx.foreach(
                                AppState.current_version_artifacts, _artifact_row),
                            spacing="2",
                            width="100%",
                        ),
                        rx.text("No artifacts linked to this version.",
                                size="2", color_scheme="gray"),
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
                            rx.foreach(
                                AppState.selected_version_reviews, _review_row),
                            spacing="2",
                            width="100%",
                        ),
                        rx.text("No reviews run for this version yet.",
                                size="2", color_scheme="gray"),
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
                            rx.foreach(
                                AppState.nodes_for_selected_version, _node_row),
                            spacing="2",
                            width="100%",
                        ),
                        rx.text("No review nodes for this version yet.",
                                size="2", color_scheme="gray"),
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
