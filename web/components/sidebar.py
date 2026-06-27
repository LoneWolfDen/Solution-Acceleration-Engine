"""web/components/sidebar.py — Three-level navigation tree.

Renders: Projects → Versions → Nodes (reviews).

Each level is built with rx.foreach so the tree is fully data-driven
from AppState.projects.  Clicking any item calls the matching event
handler which updates selected_node_id and selected_node_type — those
two vars drive which pane the content area shows.

Selection highlight: the clicked item gets an indigo background.
All items show a hover state.
"""

import reflex as rx

from web.state import AppState

# ── Colour tokens ─────────────────────────────────────────────────────────────
_SELECTED_BG = "#e0e7ff"   # indigo-100
_HOVER_BG = "#f3f4f6"      # gray-100
_SIDEBAR_BG = "#f9fafb"    # gray-50
_BORDER = "#e5e7eb"        # gray-200
_TEXT_PRIMARY = "#111827"   # gray-900
_TEXT_SECONDARY = "#6b7280" # gray-500

# ── Layer-type icon map (unicode fallbacks — no external icon dep needed) ─────
_LAYER_ICONS: dict[str, str] = {
    "exploration": "○",
    "synthesis": "◆",
}


def _node_row(node: dict) -> rx.Component:
    """Render a single NodeRow as a clickable leaf item (deepest indent)."""
    is_selected = AppState.selected_node_id == node["id"]

    layer_icon = rx.match(
        node["layer_type"],
        ("exploration", rx.text("○", color=_TEXT_SECONDARY, font_size="0.65rem")),
        ("synthesis",   rx.text("◆", color="#6366f1",       font_size="0.65rem")),
        rx.text("·",    color=_TEXT_SECONDARY, font_size="0.65rem"),
    )

    return rx.box(
        rx.hstack(
            layer_icon,
            rx.text(
                node["node_name"],
                font_size="0.78rem",
                color=rx.cond(is_selected, "#3730a3", _TEXT_PRIMARY),
                overflow="hidden",
                text_overflow="ellipsis",
                white_space="nowrap",
            ),
            align="center",
            spacing="1",
            width="100%",
            overflow="hidden",
        ),
        on_click=AppState.select_review(node["id"]),
        padding_left="2.75rem",
        padding_right="0.5rem",
        padding_y="0.3rem",
        cursor="pointer",
        border_radius="4px",
        background_color=rx.cond(is_selected, _SELECTED_BG, "transparent"),
        _hover={
            "background_color": rx.cond(is_selected, _SELECTED_BG, _HOVER_BG),
        },
        width="100%",
    )


def _version_row(version: dict) -> rx.Component:
    """Render a VersionRow header + its nodes (always expanded)."""
    is_selected = AppState.selected_node_id == version["id"]

    return rx.vstack(
        # ── Version header ────────────────────────────────────────────────────
        rx.box(
            rx.hstack(
                rx.text(
                    "⎇",
                    font_size="0.7rem",
                    color=rx.cond(is_selected, "#3730a3", _TEXT_SECONDARY),
                ),
                rx.text(
                    version["name"],
                    font_size="0.82rem",
                    font_weight="500",
                    color=rx.cond(is_selected, "#3730a3", _TEXT_PRIMARY),
                    overflow="hidden",
                    text_overflow="ellipsis",
                    white_space="nowrap",
                ),
                align="center",
                spacing="1",
                width="100%",
                overflow="hidden",
            ),
            on_click=AppState.select_version(version["id"]),
            padding_left="1.5rem",
            padding_right="0.5rem",
            padding_y="0.35rem",
            cursor="pointer",
            border_radius="4px",
            background_color=rx.cond(is_selected, _SELECTED_BG, "transparent"),
            _hover={
                "background_color": rx.cond(is_selected, _SELECTED_BG, _HOVER_BG),
            },
            width="100%",
        ),
        # ── Node list (nested foreach) ────────────────────────────────────────
        rx.foreach(version["nodes"], _node_row),
        width="100%",
        spacing="0",
        align="start",
        gap="0",
    )


def _project_row(project: dict) -> rx.Component:
    """Render a ProjectRow header + its versions (always expanded)."""
    is_selected = AppState.selected_node_id == project["id"]

    return rx.vstack(
        # ── Project header ────────────────────────────────────────────────────
        rx.box(
            rx.hstack(
                rx.text(
                    "▸",
                    font_size="0.75rem",
                    color=rx.cond(is_selected, "#3730a3", _TEXT_SECONDARY),
                ),
                rx.text(
                    project["name"],
                    font_size="0.88rem",
                    font_weight="600",
                    color=rx.cond(is_selected, "#3730a3", _TEXT_PRIMARY),
                    overflow="hidden",
                    text_overflow="ellipsis",
                    white_space="nowrap",
                ),
                align="center",
                spacing="2",
                width="100%",
                overflow="hidden",
            ),
            on_click=AppState.select_project(project["id"]),
            padding_x="0.5rem",
            padding_y="0.4rem",
            cursor="pointer",
            border_radius="6px",
            background_color=rx.cond(is_selected, _SELECTED_BG, "transparent"),
            _hover={
                "background_color": rx.cond(is_selected, _SELECTED_BG, _HOVER_BG),
            },
            width="100%",
        ),
        # ── Version list (nested foreach) ─────────────────────────────────────
        rx.foreach(project["versions"], _version_row),
        width="100%",
        spacing="0",
        align="start",
        gap="0",
        padding_bottom="0.75rem",
    )


def sidebar() -> rx.Component:
    """Full sidebar panel with the project tree and a mock-mode status badge."""
    return rx.box(
        rx.vstack(
            # ── Header ────────────────────────────────────────────────────────
            rx.hstack(
                rx.text(
                    "PROJECTS",
                    font_size="0.68rem",
                    font_weight="700",
                    color=_TEXT_SECONDARY,
                    letter_spacing="0.08em",
                ),
                rx.cond(
                    AppState.mock_mode_label == "MOCK MODE",
                    rx.badge(
                        "MOCK",
                        color_scheme="orange",
                        variant="soft",
                        font_size="0.6rem",
                    ),
                    rx.box(),
                ),
                align="center",
                justify="between",
                width="100%",
                padding_bottom="0.5rem",
                border_bottom=f"1px solid {_BORDER}",
                margin_bottom="0.25rem",
            ),
            # ── Tree ──────────────────────────────────────────────────────────
            rx.cond(
                AppState.is_loading,
                rx.text("Loading…", color=_TEXT_SECONDARY, font_size="0.85rem"),
                rx.foreach(AppState.projects, _project_row),
            ),
            width="100%",
            align="start",
            spacing="0",
            gap="0",
        ),
        width="280px",
        min_width="280px",
        height="100vh",
        overflow_y="auto",
        background_color=_SIDEBAR_BG,
        border_right=f"1px solid {_BORDER}",
        padding="1rem",
        flex_shrink="0",
    )
