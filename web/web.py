"""
web/web.py — Reflex application entry point.

Registers the single index page, binds AppState, and configures the theme.
This is the module referenced by rxconfig.py (app_name = "web").

Run locally with:
    reflex run                        # dev mode (hot reload)

In production (inside Docker, managed by supervisord):
    python -m reflex run --env prod --backend-port 8001 --frontend-port 3000
"""

import reflex as rx

from .components.layout import layout
from .state import AppState


@rx.page(route="/", on_load=AppState.load_projects, title="Contexta")
def index() -> rx.Component:
    """Root page component — delegates entirely to the layout shell."""
    return layout()


# ── App instance ──────────────────────────────────────────────────────────────
# rx.theme sets the Radix UI design system baseline.
# appearance="light" keeps the UI clean and readable for non-technical users.
app = rx.App(
    theme=rx.theme(
        appearance="light",
        accent_color="blue",
        gray_color="slate",
        radius="medium",
    ),
)
