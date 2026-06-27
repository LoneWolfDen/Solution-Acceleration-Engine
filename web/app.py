"""web/app.py — Reflex application entry point.

Defines the root page layout (header + sidebar + content pane) and
registers it with the rx.App instance.

on_load=AppState.load_data fires on every page load, which populates
the project tree and pre-selects the first review node.  In MockMode
this is instant and requires no network or database.

Launch commands
---------------
Development (auto-reload):
    cd <repo-root>
    reflex run

Production (optimised build):
    reflex run --env prod

Docker (web mode — see Dockerfile):
    docker build -t contexta-web -f Dockerfile.web .
    docker run -p 3000:3000 -p 8000:8000 contexta-web
"""

import reflex as rx

from web.state import AppState, MOCK_MODE
from web.components.sidebar import sidebar
from web.components.content_pane import content_pane


# ── Header ────────────────────────────────────────────────────────────────────

def _header() -> rx.Component:
    return rx.hstack(
        rx.hstack(
            rx.text(
                "◈",
                font_size="1.1rem",
                color="#4f46e5",
            ),
            rx.text(
                "Contexta",
                font_size="1rem",
                font_weight="700",
                color="#111827",
            ),
            rx.text(
                "Solution Acceleration Engine",
                font_size="0.8rem",
                color="#9ca3af",
                display=["none", "none", "block"],
            ),
            align="center",
            spacing="2",
        ),
        rx.hstack(
            rx.cond(
                AppState.mock_mode_label == "MOCK MODE",
                rx.badge(
                    "MOCK MODE — UI preview only, no live data",
                    color_scheme="orange",
                    variant="soft",
                    font_size="0.72rem",
                ),
                rx.badge(
                    "LIVE",
                    color_scheme="green",
                    variant="soft",
                    font_size="0.72rem",
                ),
            ),
            spacing="3",
        ),
        justify="between",
        align="center",
        width="100%",
        padding_x="1rem",
        padding_y="0.6rem",
        background_color="white",
        border_bottom="1px solid #e5e7eb",
        height="48px",
        flex_shrink="0",
    )


# ── Root page layout ──────────────────────────────────────────────────────────

def index() -> rx.Component:
    """Full-screen layout: header bar + sidebar + scrollable content pane."""
    return rx.vstack(
        _header(),
        rx.hstack(
            sidebar(),
            content_pane(),
            spacing="0",
            gap="0",
            align="start",
            width="100%",
            flex="1",
            overflow="hidden",
        ),
        spacing="0",
        gap="0",
        height="100vh",
        width="100%",
        overflow="hidden",
        background_color="white",
    )


# ── App registration ──────────────────────────────────────────────────────────

app = rx.App(
    theme=rx.theme(
        appearance="light",
        accent_color="indigo",
        radius="medium",
    ),
)

app.add_page(
    index,
    route="/",
    title="Contexta — Solution Acceleration Engine",
    on_load=AppState.load_data,
)
