"""
web/components/content_pane.py — Main content area.

Routes on AppState.active_view:
  "welcome" → WelcomeView
  "version" → VersionDetailPane
  "node"    → ReviewDetailPane
"""

import reflex as rx

from web.state import AppState
from web.components.review_detail import review_detail_pane
from web.components.version_detail import version_detail
from web.components.status_banner import review_status_banner


def _welcome_view() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.icon("zap", size=48, color="var(--gray-7)"),
            rx.heading("Solution Acceleration Engine", size="6", text_align="center"),
            rx.text(
                "Select a project from the sidebar to begin.",
                size="2",
                color_scheme="gray",
                text_align="center",
            ),
            spacing="4",
            align="center",
            max_width="480px",
        ),
        display="flex",
        align_items="center",
        justify_content="center",
        width="100%",
        height="100%",
    )


def _loading_view() -> rx.Component:
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


def content_pane() -> rx.Component:
    return rx.box(
        rx.box(
            review_status_banner(),
            position="absolute",
            top="1rem",
            right="1rem",
            left="1rem",
            z_index="10",
            max_width="420px",
            margin_left="auto",
        ),
        rx.cond(
            AppState.is_loading,
            _loading_view(),
            rx.cond(
                AppState.active_view == "node",
                review_detail_pane(),
                rx.cond(
                    AppState.active_view == "version",
                    version_detail(),
                    _welcome_view(),
                ),
            ),
        ),
        flex="1",
        height="100vh",
        overflow="hidden",
        background="var(--gray-1)",
        position="relative",
    )
