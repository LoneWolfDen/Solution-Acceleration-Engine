"""
web/web.py — Reflex application entry point.

Routes:
  /       — Dashboard (sidebar + content pane)
  /admin  — Admin dashboard (registered via @rx.page decorator)
"""

import reflex as rx

from contexta.api import app as fastapi_app
from web.state import AppState
from web.components.sidebar import sidebar
from web.components.content_pane import content_pane
from web.components.toast import toast_notification
from web.components.ingestion_modal import ingestion_modal
from web.pages import admin as _admin_module  # noqa: F401 — registers /admin via @rx.page
from web.pages import run_review as _run_review_module  # noqa: F401 — registers /run-review/[version_id]


def index() -> rx.Component:
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
        ingestion_modal(),
        toast_notification(),
        width="100vw",
        height="100vh",
        overflow="hidden",
    )


app = rx.App(
    api_transformer=fastapi_app,
)

app.add_page(
    index,
    route="/",
    title="Solution Acceleration Engine",
    # Requirement C2.2 — populate the insights sidebar alongside the
    # existing project list load.
    on_load=[AppState.load_projects, AppState.fetch_insights],
)
