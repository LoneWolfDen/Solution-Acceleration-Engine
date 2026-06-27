"""web/components/version_detail.py — Version detail panel.

Rendered by content_pane.py when AppState.active_view == "version".

Shows:
  - Version name + description
  - Created timestamp
  - List of nodes belonging to this version, each clickable to open
    the findings view.
"""

import reflex as rx

from web.state import AppState


# ---------------------------------------------------------------------------
# Node list item (quick-select within the version detail)
# ---------------------------------------------------------------------------

def _node_list_item(node: dict) -> rx.Component:
    """Clickable node row inside the version detail panel."""
    is_selected = AppState.selected_node_id == node["id"]

    return rx.box(
        rx.hstack(
            rx.icon(
                "circle-dot",
                size=14,
                color=rx.cond(is_selected, "#60a5fa", "#475569"),
                flex_shrink="0",
            ),
            rx.vstack(
                rx.text(
                    node["node_name"],
                    font_size="0.875rem",
                    font_weight=rx.cond(is_selected, "600", "400"),
                    color=rx.cond(is_selected, "#bfdbfe", "#94a3b8"),
                ),
                rx.hstack(
                    rx.badge(
                        node["layer_type"],
                        color_scheme="indigo",
                        variant="soft",
                        font_size="0.65rem",
                    ),
                    rx.text(
                        node["created_at"],
                        font_size="0.7rem",
                        color="#475569",
                        font_family="monospace",
                    ),
                    spacing="2",
                    align="center",
                ),
                spacing="1",
                align="start",
            ),
            rx.icon(
                "chevron-right",
                size=14,
                color="#475569",
                flex_shrink="0",
            ),
            justify="between",
            align="center",
            width="100%",
        ),
        padding="0.75rem 1rem",
        background=rx.cond(is_selected, "#1a2035", "#0f1117"),
        border="1px solid",
        border_color=rx.cond(is_selected, "#1d4ed8", "#1e293b"),
        border_radius="6px",
        cursor="pointer",
        transition="all 0.15s ease",
        width="100%",
        on_click=AppState.select_node(node["id"]),
        _hover={
            "background": "#1a2035",
            "border_color": "#334155",
        },
    )


# ---------------------------------------------------------------------------
# Public component
# ---------------------------------------------------------------------------

def version_detail() -> rx.Component:
    """Full version detail panel bound to AppState.current_version."""
    return rx.box(
        rx.vstack(
            # ── Header ───────────────────────────────────────────────────
            rx.box(
                rx.hstack(
                    rx.icon("layers", size=20, color="#818cf8"),
                    rx.vstack(
                        rx.heading(
                            AppState.current_version["name"],
                            size="5",
                            color="#e2e8f0",
                            font_weight="700",
                        ),
                        rx.text(
                            AppState.current_version["created_at"],
                            font_size="0.75rem",
                            color="#475569",
                            font_family="monospace",
                        ),
                        spacing="1",
                        align="start",
                    ),
                    spacing="3",
                    align="start",
                ),
                padding_bottom="1rem",
                border_bottom="1px solid #1e293b",
                width="100%",
            ),

            # ── Description ──────────────────────────────────────────────
            rx.cond(
                AppState.current_version["description"] != "",
                rx.box(
                    rx.text(
                        AppState.current_version["description"],
                        font_size="0.875rem",
                        color="#94a3b8",
                        line_height="1.65",
                    ),
                    padding_y="0.75rem",
                    border_bottom="1px solid #1e293b",
                    width="100%",
                ),
                rx.fragment(),
            ),

            # ── Node list ────────────────────────────────────────────────
            rx.vstack(
                rx.hstack(
                    rx.icon("git-branch", size=14, color="#64748b"),
                    rx.text(
                        "Review Nodes",
                        font_size="0.75rem",
                        font_weight="700",
                        letter_spacing="0.07em",
                        text_transform="uppercase",
                        color="#64748b",
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.foreach(
                    AppState.current_version["nodes"],
                    _node_list_item,
                ),
                spacing="2",
                align="start",
                width="100%",
            ),

            spacing="4",
            align="start",
            width="100%",
        ),
        padding="2rem",
        width="100%",
        height="100%",
        overflow_y="auto",
    )
