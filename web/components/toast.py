"""
web/components/toast.py — ToastNotification component.
"""

import reflex as rx

from web.state import AppState


def toast_notification() -> rx.Component:
    return rx.cond(
        AppState.toast_message != "",
        rx.box(
            rx.hstack(
                rx.icon(
                    rx.cond(AppState.toast_is_error, "circle-alert", "circle-check"),
                    size=16,
                    color=rx.cond(AppState.toast_is_error, "var(--red-11)", "var(--green-11)"),
                    flex_shrink="0",
                ),
                rx.text(AppState.toast_message, size="2", weight="medium", flex="1"),
                rx.icon_button(
                    rx.icon("x", size=14),
                    variant="ghost",
                    size="1",
                    on_click=AppState.clear_toast,
                    color_scheme=rx.cond(AppState.toast_is_error, "red", "green"),
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            position="fixed",
            bottom="1.5rem",
            right="1.5rem",
            z_index="9999",
            background=rx.cond(AppState.toast_is_error, "var(--red-3)", "var(--green-3)"),
            border=rx.cond(
                AppState.toast_is_error,
                "1px solid var(--red-6)",
                "1px solid var(--green-6)",
            ),
            border_radius="8px",
            padding="0.875rem 1rem",
            max_width="420px",
            min_width="280px",
            box_shadow="0 4px 24px rgba(0,0,0,0.25)",
        ),
        rx.fragment(),
    )
