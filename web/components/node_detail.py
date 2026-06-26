"""
web/components/node_detail.py — Node content pane.

Pure renderer: reads computed vars from AppState, renders them.
Displays formatted JSON of the node's content_markdown field.
No data-fetching or logic lives here.

Three render states:
  1. Loading      — spinner while a node is being fetched
  2. Empty        — prompt when nothing is selected
  3. Content      — formatted JSON block with node header
"""

import reflex as rx

from ..state import AppState


# ── State 1: loading ──────────────────────────────────────────────────────────

def _loading() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.spinner(size="3"),
            rx.text("Loading…", size="2", color_scheme="gray"),
            align="center",
            spacing="3",
        ),
        height="100%",
        width="100%",
    )


# ── State 2: nothing selected ─────────────────────────────────────────────────

def _empty_state() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.icon("file-search", size=48, color="var(--gray-8)"),
            rx.text(
                "Select a project, version, and node from the sidebar.",
                size="2",
                color_scheme="gray",
                text_align="center",
            ),
            align="center",
            spacing="3",
            max_width="320px",
        ),
        height="100%",
        width="100%",
    )


# ── State 3: node loaded ──────────────────────────────────────────────────────

def _node_header() -> rx.Component:
    """Compact header row: node name, layer-type badge, and timestamp."""
    return rx.vstack(
        rx.heading(
            AppState.selected_node_name,
            size="5",
            weight="bold",
        ),
        rx.hstack(
            rx.badge(
                AppState.selected_node_layer_type,
                variant="soft",
                color_scheme="blue",
            ),
            rx.spacer(),
            rx.text(
                AppState.selected_node_created_at,
                size="1",
                color_scheme="gray",
            ),
            width="100%",
            align="center",
        ),
        rx.separator(width="100%"),
        width="100%",
        spacing="2",
        padding_x="1.5rem",
        padding_top="1.25rem",
        padding_bottom="0.75rem",
    )


def _node_content() -> rx.Component:
    """Scrollable JSON block showing the node's content_markdown."""
    return rx.scroll_area(
        rx.code_block(
            AppState.selected_node_content_json,
            language="json",
            width="100%",
            font_size="0.8rem",
            border_radius="6px",
        ),
        padding_x="1.5rem",
        padding_bottom="1.5rem",
        flex="1",
        width="100%",
        type="auto",
    )


def _loaded_view() -> rx.Component:
    return rx.vstack(
        _node_header(),
        _node_content(),
        height="100%",
        width="100%",
        spacing="0",
        align_items="stretch",
        overflow="hidden",
    )


# ── Public component ──────────────────────────────────────────────────────────

def node_detail() -> rx.Component:
    """
    Master-detail right pane.

    Renders one of three states based on AppState:
      is_loading  →  spinner
      no node selected  →  empty prompt
      node loaded  →  header + formatted JSON
    """
    return rx.cond(
        AppState.is_loading,
        _loading(),
        rx.cond(
            AppState.selected_node_id == "",
            _empty_state(),
            _loaded_view(),
        ),
    )
