"""
web/components/sidebar.py — Project tree sidebar.

Pure renderer: reads AppState vars, fires event handlers.
"""

import reflex as rx

from web.state import AppState


def _render_node(node: dict) -> rx.Component:
    is_selected = AppState.selected_node_id == node["id"]
    return rx.box(
        rx.button(
            rx.hstack(
                rx.icon("scan-search", size=12, flex_shrink="0"),
                rx.text(node["node_name"], size="1", truncate=True),
                align="center",
                spacing="2",
                width="100%",
            ),
            variant="ghost",
            width="100%",
            style={"justify_content": "flex-start"},
            background=rx.cond(is_selected, "var(--accent-3)", "transparent"),
            color=rx.cond(is_selected, "var(--accent-11)", "inherit"),
            on_click=AppState.select_node(node["id"]),
        ),
        padding_left="2.5rem",
        width="100%",
    )


def _render_version(version: dict) -> rx.Component:
    is_open = AppState.selected_version_id == version["id"]
    return rx.vstack(
        rx.button(
            rx.hstack(
                rx.cond(
                    is_open,
                    rx.icon("chevron-down", size=12),
                    rx.icon("chevron-right", size=12),
                ),
                rx.icon("tag", size=12),
                rx.text(version["name"], size="1", truncate=True),
                align="center",
                spacing="2",
                width="100%",
            ),
            variant="ghost",
            width="100%",
            style={"justify_content": "flex-start"},
            on_click=AppState.select_version(version["id"]),
        ),
        rx.cond(
            is_open,
            rx.vstack(
                rx.foreach(AppState.nodes_for_selected_version, _render_node),
                width="100%",
                spacing="0",
            ),
            rx.fragment(),
        ),
        width="100%",
        spacing="0",
    )


def _render_project(project: dict) -> rx.Component:
    is_open = AppState.selected_project_id == project["id"]
    return rx.vstack(
        rx.button(
            rx.hstack(
                rx.cond(
                    is_open,
                    rx.icon("folder-open", size=14),
                    rx.icon("folder", size=14),
                ),
                rx.text(project["name"], size="2", weight="medium", truncate=True),
                align="center",
                spacing="2",
                width="100%",
            ),
            variant="ghost",
            width="100%",
            style={"justify_content": "flex-start"},
            on_click=AppState.select_project(project["id"]),
        ),
        rx.cond(
            is_open,
            rx.box(
                rx.foreach(AppState.versions_for_selected_project, _render_version),
                padding_left="1rem",
                width="100%",
            ),
            rx.fragment(),
        ),
        width="100%",
        spacing="0",
    )


def sidebar() -> rx.Component:
    return rx.box(
        rx.vstack(
            # Header
            rx.hstack(
                rx.icon("layout-dashboard", size=18),
                rx.heading("Contexta", size="4"),
                align="center",
                spacing="2",
                padding_x="1rem",
                padding_y="0.875rem",
                width="100%",
            ),
            rx.separator(width="100%"),

            # Actions
            rx.hstack(
                rx.button(
                    rx.icon("plus", size=13),
                    "Ingest Artifact",
                    size="1",
                    variant="soft",
                    color_scheme="indigo",
                    disabled=AppState.selected_project_id == "",
                    on_click=AppState.open_ingestion_modal,
                    flex="1",
                ),
                rx.link(
                    rx.icon_button(
                        rx.icon("settings", size=14),
                        size="1",
                        variant="soft",
                        color_scheme="gray",
                    ),
                    href="/admin",
                ),
                spacing="2",
                align="center",
                padding_x="0.75rem",
                padding_y="0.5rem",
                width="100%",
            ),

            rx.separator(width="100%"),

            rx.hstack(
                rx.text(
                    "PROJECTS",
                    size="1",
                    weight="bold",
                    color_scheme="gray",
                    letter_spacing="0.08em",
                ),
                rx.spacer(),
                rx.cond(AppState.is_loading, rx.spinner(size="1"), rx.fragment()),
                padding_x="1rem",
                padding_top="0.625rem",
                padding_bottom="0.375rem",
                width="100%",
            ),

            rx.scroll_area(
                rx.vstack(
                    rx.foreach(AppState.projects, _render_project),
                    rx.cond(
                        AppState.projects.length() == 0,
                        rx.center(
                            rx.text("No projects found.", size="1", color_scheme="gray"),
                            padding_y="2rem",
                            width="100%",
                        ),
                        rx.fragment(),
                    ),
                    width="100%",
                    spacing="0",
                    align_items="stretch",
                    padding="0.5rem",
                ),
                flex="1",
                width="100%",
                type="auto",
            ),

            height="100vh",
            width="100%",
            spacing="0",
            align_items="stretch",
        ),
        width="280px",
        min_width="280px",
        height="100vh",
        border_right="1px solid var(--gray-4)",
        background="var(--gray-1)",
        overflow="hidden",
        flex_shrink="0",
    )
