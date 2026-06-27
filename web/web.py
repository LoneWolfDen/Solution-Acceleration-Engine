"""web/web.py — Reflex application entry point.

Wires the two-pane layout (sidebar + content_pane) and registers the
single page route with AppState.on_load as the page lifecycle hook.

Run with:
    reflex run          (development, hot-reload)
    reflex run --env prod  (production)

Ensure MOCK_MODE = True in web/state.py for offline / proxy-limited
environments.  Flip to False once a live DB is available.
"""

import reflex as rx

from web.state import AppState
from web.components.sidebar import sidebar
from web.components.content_pane import content_pane


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

def index() -> rx.Component:
    """Root page: full-viewport horizontal split — sidebar | content."""
    return rx.box(
        # Global reset / baseline
        rx.html(
            "<style>"
            "*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }"
            "body { background: #0b0e14; overflow: hidden; }"
            "</style>"
        ),
        rx.hstack(
            sidebar(),
            content_pane(),
            spacing="0",
            align="stretch",
            width="100vw",
            height="100vh",
            overflow="hidden",
        ),
        width="100vw",
        height="100vh",
        overflow="hidden",
    )


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

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
    on_load=AppState.on_load,
)
