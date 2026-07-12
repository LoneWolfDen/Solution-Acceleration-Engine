"""
web/components/version_detail.py — VersionDetailPane.

Shows linked artifacts table, reviews list, and review nodes.
Uses bracket notation (not .get()) for all Reflex Var dict access
to be compile-safe inside rx.foreach callbacks.
"""

import reflex as rx

from web.components.proposal_form import proposal_form, proposals_list
from web.state import AppState


def _artifact_row(artifact: dict) -> rx.Component:
    # Requirement C3.3 — highlight the artifact resolved via a citation click
    # in finding_card.py, using the same visual pattern as _review_row/_node_row.
    is_highlighted = AppState.selected_artifact_id == artifact["artifact_id"]
    return rx.vstack(
        rx.hstack(
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
        ),
        # Requirement B4.1 — line_count and content_preview beneath the
        # existing title/tags row, sourced from Track A's schema fields.
        rx.hstack(
            rx.icon("align-left", size=11, color="var(--gray-8)", flex_shrink="0"),
            rx.text(
                artifact["line_count"].to(str) + " lines",
                size="1",
                color_scheme="gray",
                flex_shrink="0",
            ),
            rx.text(
                artifact["content_preview"].to(str),
                size="1",
                color_scheme="gray",
                truncate=True,
            ),
            spacing="2",
            align="center",
            width="100%",
            padding_left="1.5rem",
        ),
        spacing="1",
        align="start",
        width="100%",
        padding="0.625rem 0.75rem",
        background=rx.cond(is_highlighted, "var(--accent-3)", "var(--gray-2)"),
        border="1px solid",
        border_color=rx.cond(is_highlighted, "var(--accent-6)", "var(--gray-4)"),
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


def _action_bar() -> rx.Component:
    """Action buttons for the version detail page."""
    return rx.hstack(
        rx.link(
            rx.button(
                rx.icon("play", size=13),
                "Run Review",
                size="2",
                variant="soft",
                color_scheme="indigo",
            ),
            href="/run-review/" + AppState.selected_version["id"].to(str),
        ),
        rx.button(
            rx.icon("share-2", size=13),
            "Export JSON",
            size="2",
            variant="soft",
            color_scheme="gray",
            on_click=AppState.export_node(AppState.selected_node_id),
        ),
        # Requirement B2.1 — Fork action in the version action bar.
        rx.button(
            rx.icon("git-fork", size=13),
            "Fork",
            size="2",
            variant="soft",
            color_scheme="grass",
            on_click=AppState.open_fork_dialog,
        ),
        spacing="2",
        width="100%",
    )


def _fork_dialog() -> rx.Component:
    """Requirement B2.2 — fork dialog prompting for a name, then forking the
    selected review node via AppState.fork_node."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Fork Review Node"),
            rx.dialog.description(
                "Enter a name for the forked node.",
                size="2",
                color_scheme="gray",
                margin_bottom="1rem",
            ),
            rx.vstack(
                rx.input(
                    placeholder="Forked node name…",
                    value=AppState._fork_name,
                    on_change=AppState.set_fork_name,
                    size="3",
                    width="100%",
                    auto_focus=True,
                ),
                rx.hstack(
                    rx.button(
                        "Cancel",
                        variant="soft",
                        color_scheme="gray",
                        on_click=AppState.close_fork_dialog,
                    ),
                    rx.button(
                        "Confirm",
                        color_scheme="grass",
                        on_click=[
                            AppState.fork_node(
                                AppState.selected_node_id, AppState._fork_name
                            ),
                            AppState.close_fork_dialog,
                        ],
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
        open=AppState._fork_dialog_open,
        on_open_change=AppState.close_fork_dialog,
    )


def version_detail() -> rx.Component:
    version = AppState.current_version
    return rx.box(
        _fork_dialog(),
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
                        rx.cond(
                            AppState.selected_node_id,
                            _action_bar(),
                            rx.link(
                                rx.button(
                                    rx.icon("play", size=13),
                                    "Run Review",
                                    size="1",
                                    variant="soft",
                                    color_scheme="indigo",
                                ),
                                href="/run-review/" + version["id"].to(str),
                                flex_shrink="0",
                            ),
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

                # Proposals (Requirement B1.1) — follows the Review Runs section.
                rx.vstack(
                    _section_label("sparkles", "Proposals"),
                    proposal_form(version["id"].to(str)),
                    proposals_list(version["id"].to(str)),
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
