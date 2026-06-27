"""web/components/version_detail.py — VersionDetailPane.

Renders the version_detail dict from AppState:
    id           str
    name         str
    description  str
    created_at   str   (ISO-8601)
    node_count   int
    project_name str   (derived — parent project name for breadcrumb)

Shown in the content pane when selected_node_type == "version".
"""

import reflex as rx

from web.state import AppState


def _stat_block(label: str, value: rx.Var) -> rx.Component:
    """One label + value block for the stats row."""
    return rx.vstack(
        rx.text(
            label,
            font_size="0.68rem",
            font_weight="700",
            color="#9ca3af",
            letter_spacing="0.08em",
            text_transform="uppercase",
        ),
        rx.text(
            value,
            font_size="1.25rem",
            font_weight="600",
            color="#111827",
        ),
        spacing="0",
        gap="2px",
        align="start",
    )


def version_detail_pane() -> rx.Component:
    """Full VersionDetailPane rendered from AppState.version_detail."""
    return rx.box(
        rx.vstack(
            # ── Breadcrumb ────────────────────────────────────────────────────
            rx.hstack(
                rx.text(
                    AppState.version_detail["project_name"],
                    font_size="0.8rem",
                    color="#6b7280",
                    cursor="pointer",
                    _hover={"color": "#4f46e5"},
                    on_click=AppState.select_project(
                        AppState.version_detail["id"]
                    ),
                ),
                rx.text("›", color="#d1d5db", font_size="0.8rem"),
                rx.text(
                    AppState.version_detail["name"],
                    font_size="0.8rem",
                    color="#374151",
                    font_weight="500",
                ),
                align="center",
                spacing="1",
            ),
            # ── Version name heading ──────────────────────────────────────────
            rx.heading(
                AppState.version_detail["name"],
                size="6",
                color="#111827",
                font_weight="700",
                margin_bottom="0.25rem",
            ),
            # ── Description ───────────────────────────────────────────────────
            rx.cond(
                AppState.version_detail["description"] != "",
                rx.text(
                    AppState.version_detail["description"],
                    font_size="0.95rem",
                    color="#4b5563",
                    line_height="1.6",
                    max_width="700px",
                ),
                rx.box(),
            ),
            # ── Stats row ─────────────────────────────────────────────────────
            rx.hstack(
                _stat_block("Review Nodes", AppState.version_detail["node_count"]),
                _stat_block("Created",      AppState.version_detail["created_at"]),
                spacing="6",
                padding="1rem",
                background_color="#f9fafb",
                border="1px solid #e5e7eb",
                border_radius="8px",
                margin_top="0.5rem",
                width="100%",
            ),
            # ── Prompt ────────────────────────────────────────────────────────
            rx.text(
                "Select a review node from the sidebar to view its findings.",
                font_size="0.85rem",
                color="#9ca3af",
                margin_top="1rem",
            ),
            spacing="3",
            align="start",
            width="100%",
        ),
        padding="2rem",
        width="100%",
    )
