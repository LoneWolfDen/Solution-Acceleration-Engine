"""web/components/sidebar.py — 3-level navigation tree.

Renders:  Project  →  Version  →  Node
Binds to: AppState.projects via rx.foreach at each level.

Selected items receive an accent background so the user always knows
which cursor is active.  Clicking any item fires the corresponding
AppState event handler with the item's id as the argument.
"""

import reflex as rx

from web.state import AppState

# ---------------------------------------------------------------------------
# Design tokens (kept as module constants — change here only)
# ---------------------------------------------------------------------------
SIDEBAR_BG = "#111318"
SIDEBAR_WIDTH = "280px"

PROJECT_BG = "transparent"
PROJECT_BG_ACTIVE = "#1e2130"
PROJECT_COLOR = "#e2e8f0"
PROJECT_FONT_SIZE = "0.875rem"
PROJECT_FONT_WEIGHT = "600"

VERSION_BG = "transparent"
VERSION_BG_ACTIVE = "#252a3d"
VERSION_COLOR = "#94a3b8"
VERSION_FONT_SIZE = "0.8125rem"

NODE_BG = "transparent"
NODE_BG_ACTIVE = "#2a3050"
NODE_COLOR = "#64748b"
NODE_COLOR_ACTIVE = "#93c5fd"
NODE_FONT_SIZE = "0.75rem"

HOVER_TRANSITION = "background 0.15s ease"


# ---------------------------------------------------------------------------
# Level 3 — Node item
# ---------------------------------------------------------------------------

def _node_item(node: dict) -> rx.Component:
    """Single clickable node row, highlighted when selected."""
    is_selected = AppState.selected_node_id == node["id"]

    return rx.box(
        rx.hstack(
            rx.icon(
                "circle-dot",
                size=10,
                color=rx.cond(is_selected, NODE_COLOR_ACTIVE, "#475569"),
                flex_shrink="0",
            ),
            rx.text(
                node["node_name"],
                font_size=NODE_FONT_SIZE,
                color=rx.cond(is_selected, NODE_COLOR_ACTIVE, NODE_COLOR),
                font_weight=rx.cond(is_selected, "500", "400"),
                no_of_lines=2,
                line_height="1.3",
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        padding_x="0.75rem",
        padding_y="0.4rem",
        padding_left="2.25rem",
        background=rx.cond(is_selected, NODE_BG_ACTIVE, NODE_BG),
        border_left=rx.cond(
            is_selected,
            "2px solid #3b82f6",
            "2px solid transparent",
        ),
        border_radius="0 4px 4px 0",
        cursor="pointer",
        transition=HOVER_TRANSITION,
        width="100%",
        on_click=AppState.select_node(node["id"]),
        _hover={"background": NODE_BG_ACTIVE},
    )


# ---------------------------------------------------------------------------
# Level 2 — Version item
# ---------------------------------------------------------------------------

def _version_item(version: dict) -> rx.Component:
    """Version row with nested node list beneath it."""
    is_selected = AppState.selected_version_id == version["id"]

    return rx.box(
        # Version label row
        rx.box(
            rx.hstack(
                rx.icon(
                    "layers",
                    size=12,
                    color=rx.cond(is_selected, "#60a5fa", "#64748b"),
                    flex_shrink="0",
                ),
                rx.text(
                    version["name"],
                    font_size=VERSION_FONT_SIZE,
                    color=rx.cond(is_selected, "#bfdbfe", VERSION_COLOR),
                    font_weight=rx.cond(is_selected, "500", "400"),
                    no_of_lines=2,
                    line_height="1.3",
                ),
                spacing="2",
                align="start",
                width="100%",
            ),
            padding_x="0.75rem",
            padding_y="0.45rem",
            padding_left="1.5rem",
            background=rx.cond(is_selected, VERSION_BG_ACTIVE, VERSION_BG),
            border_radius="4px",
            cursor="pointer",
            transition=HOVER_TRANSITION,
            width="100%",
            on_click=AppState.select_version(version["id"]),
            _hover={"background": VERSION_BG_ACTIVE},
        ),
        # Node list (always visible — no collapse in Milestone 2)
        rx.box(
            rx.foreach(version["nodes"], _node_item),
            padding_top="0.1rem",
            padding_bottom="0.25rem",
        ),
        width="100%",
    )


# ---------------------------------------------------------------------------
# Level 1 — Project item
# ---------------------------------------------------------------------------

def _project_item(project: dict) -> rx.Component:
    """Project header row with nested version/node tree beneath it."""
    is_selected = AppState.selected_project_id == project["id"]

    return rx.box(
        # Project label row
        rx.box(
            rx.hstack(
                rx.icon(
                    "folder",
                    size=14,
                    color=rx.cond(is_selected, "#818cf8", "#94a3b8"),
                    flex_shrink="0",
                ),
                rx.text(
                    project["name"],
                    font_size=PROJECT_FONT_SIZE,
                    font_weight=PROJECT_FONT_WEIGHT,
                    color=rx.cond(is_selected, "#e0e7ff", PROJECT_COLOR),
                    no_of_lines=2,
                    line_height="1.35",
                ),
                spacing="2",
                align="start",
                width="100%",
            ),
            padding_x="0.75rem",
            padding_y="0.55rem",
            background=rx.cond(is_selected, PROJECT_BG_ACTIVE, PROJECT_BG),
            border_radius="6px",
            cursor="pointer",
            transition=HOVER_TRANSITION,
            width="100%",
            on_click=AppState.select_project(project["id"]),
            _hover={"background": PROJECT_BG_ACTIVE},
        ),
        # Version tree (shown only when this project is selected)
        rx.cond(
            is_selected,
            rx.box(
                rx.foreach(project["versions"], _version_item),
                padding_top="0.15rem",
                padding_bottom="0.5rem",
            ),
            rx.fragment(),
        ),
        width="100%",
        margin_bottom="0.25rem",
    )


# ---------------------------------------------------------------------------
# Public sidebar component
# ---------------------------------------------------------------------------

def sidebar() -> rx.Component:
    """Full-height navigation sidebar with the 3-level project tree."""
    return rx.box(
        # Header
        rx.box(
            rx.hstack(
                rx.icon("zap", size=16, color="#818cf8"),
                rx.text(
                    "Projects",
                    font_size="0.8125rem",
                    font_weight="700",
                    letter_spacing="0.08em",
                    text_transform="uppercase",
                    color="#64748b",
                ),
                spacing="2",
                align="center",
            ),
            padding_x="0.75rem",
            padding_top="1.25rem",
            padding_bottom="0.75rem",
        ),
        rx.divider(color_scheme="gray", margin_bottom="0.5rem"),
        # Scrollable tree
        rx.box(
            rx.foreach(AppState.projects, _project_item),
            overflow_y="auto",
            flex="1",
            padding_x="0.25rem",
            padding_bottom="1rem",
        ),
        # Footer hint
        rx.box(
            rx.text(
                rx.cond(
                    AppState.is_loading,
                    "Loading…",
                    "Select a node to view findings",
                ),
                font_size="0.7rem",
                color="#334155",
                text_align="center",
            ),
            padding="0.75rem",
            border_top="1px solid #1e293b",
        ),
        # Container styles
        width=SIDEBAR_WIDTH,
        min_width=SIDEBAR_WIDTH,
        height="100vh",
        background=SIDEBAR_BG,
        border_right="1px solid #1e293b",
        display="flex",
        flex_direction="column",
        overflow="hidden",
    )
