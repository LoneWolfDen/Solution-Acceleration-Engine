"""
web/components/triage_widget.py — ArtifactTriageWidget.

Key fix: use bracket notation (artifact["artifact_id"]) not .get()
for compile-safe Reflex Var access inside rx.foreach callbacks.
"""

import reflex as rx

from web.state import AppState


def _triage_row(artifact: dict) -> rx.Component:
    is_new = AppState.last_saved_artifact["artifact_id"] == artifact["artifact_id"]
    return rx.hstack(
        rx.text(
            artifact["title"],
            size="2",
            flex="1",
            truncate=True,
            color=rx.cond(is_new, "var(--accent-11)", "var(--gray-12)"),
            weight=rx.cond(is_new, "bold", "regular"),
        ),
        rx.hstack(
            rx.foreach(
                artifact["tags"].to(list[str]),
                lambda t: rx.badge(t, size="1", color_scheme="gray", variant="soft"),
            ),
            spacing="1",
            flex_wrap="wrap",
            width="160px",
        ),
        rx.switch(
            checked=artifact["is_active"],
            on_change=AppState.toggle_artifact_active(artifact["artifact_id"]),
            color_scheme="green",
        ),
        spacing="3",
        align="center",
        width="100%",
        padding="0.5rem 0.75rem",
        background=rx.cond(is_new, "var(--accent-2)", "var(--gray-2)"),
        border="1px solid",
        border_color=rx.cond(is_new, "var(--accent-6)", "var(--gray-4)"),
        border_radius="6px",
    )


def triage_widget() -> rx.Component:
    return rx.vstack(
        # Header
        rx.hstack(
            rx.text("Title", size="1", weight="bold", color_scheme="gray", flex="1"),
            rx.text("Tags", size="1", weight="bold", color_scheme="gray", width="160px"),
            rx.text("Active", size="1", weight="bold", color_scheme="gray"),
            spacing="3",
            align="center",
            width="100%",
            padding_x="0.75rem",
            padding_y="0.375rem",
        ),
        rx.cond(
            AppState.triage_artifacts.length() > 0,
            rx.vstack(
                rx.foreach(AppState.triage_artifacts, _triage_row),
                spacing="2",
                width="100%",
            ),
            rx.center(
                rx.text("No artifacts yet.", size="2", color_scheme="gray"),
                padding="1.5rem",
                width="100%",
            ),
        ),
        rx.separator(width="100%"),
        rx.hstack(
            rx.text(
                rx.fragment(AppState.triage_active_artifact_ids.length(), " artifact(s) selected"),
                size="2",
                color_scheme="gray",
            ),
            rx.spacer(),
            rx.button(
                rx.icon("plus", size=14),
                "Create Version",
                color_scheme="indigo",
                variant="solid",
                disabled=~AppState.can_create_version,
                on_click=AppState.create_version_from_triage("Version 1"),
            ),
            width="100%",
            align="center",
        ),
        spacing="3",
        align="start",
        width="100%",
    )
