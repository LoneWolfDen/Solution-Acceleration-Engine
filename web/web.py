"""
web/web.py — Reflex application entry point.

Registers:
  /       — Dashboard (sidebar + content pane)
  /admin  — Admin dashboard

Run with:
    reflex run                 (development)
    reflex run --env prod      (production)
"""

import reflex as rx

from web.state import AppState
from web.components.sidebar import sidebar
from web.components.content_pane import content_pane
from web.components.toast import toast_notification
from web.components.ingestion_modal import ingestion_modal
from web.pages import admin as _admin_module  # noqa: F401  (registers /admin via @rx.page)


# ── Dashboard page ────────────────────────────────────────────────────────────

def index() -> rx.Component:
    """Root page: sidebar | content pane, full-viewport split."""
    return rx.box(
        rx.hstack(
            sidebar(),
            content_pane(),
            spacing="0",
            align="stretch",
            width="100vw",
            height="100vh",
            overflow="hidden",
        ),
        # Global overlays
        ingestion_modal(),
        toast_notification(),
        width="100vw",
        height="100vh",
        overflow="hidden",
    )


# ── Application ───────────────────────────────────────────────────────────────

app = rx.App(
    theme=rx.theme(
        appearance="dark",
        accent_color="indigo",
        radius="medium",
    ),
)

app.add_page(
    index,
    route="/",
    title="Solution Acceleration Engine",
    on_load=AppState.load_projects,
)
