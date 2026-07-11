"""
web/components/dream_cycle_panel.py — Dream Cycle Panel (Gap 8).

A panel for triggering and monitoring the Dream Cycle background
analysis worker via /api/admin/dream-cycle endpoints.
"""

import reflex as rx

from web.state import AppState


def dream_cycle_panel() -> rx.Component:
    """Panel for Dream Cycle management.
    
    Gap 8 — Requirements 8.6-8.7: displays a "Run Dream Cycle"
    button that's disabled while running, and shows status
    indicator with idle/running/complete/failed states and
    last run timestamp.
    """
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("database", size=16, color="var(--gray-9)"),
                rx.text("Dream Cycle Analysis", size="2", weight="medium"),
                spacing="3",
                align="center",
                width="100%",
            ),
            rx.divider(width="100%"),
            rx.box(
                rx.cond(
                    AppState.dream_cycle_status == "running",
                    rx.vstack(
                        rx.hstack(
                            rx.icon("loader", size=16, animation="rotate"),
                            rx.text("Running...", size="2"),
                            spacing="2",
                            align="center",
                        ),
                        rx.text(
                            "Analyzing database patterns...",
                            size="1",
                            color_scheme="gray",
                        ),
                        spacing="3",
                        align="start",
                    ),
                    rx.cond(
                        AppState.dream_cycle_status == "complete",
                        rx.vstack(
                            rx.hstack(
                                rx.icon("circle-check", size=16, color="var(--green-9)"),
                                rx.text("Completed", size="2", color_scheme="green"),
                                spacing="2",
                                align="center",
                            ),
                            rx.text(
                                f"Last run: {AppState.dream_cycle_last_run[:10]}",
                                size="1",
                                color_scheme="gray",
                            ),
                            spacing="3",
                            align="start",
                        ),
                        rx.cond(
                            AppState.dream_cycle_status == "failed",
                            rx.vstack(
                                rx.hstack(
                                    rx.icon("alert-circle", size=16, color="var(--red-9)"),
                                    rx.text("Failed", size="2", color_scheme="red"),
                                    spacing="2",
                                    align="center",
                                ),
                                rx.text(
                                    AppState.dream_cycle_error,
                                    size="1",
                                    color_scheme="gray",
                                ),
                                spacing="3",
                                align="start",
                            ),
                            rx.vstack(
                                rx.hstack(
                                    rx.icon("circle-x", size=16, color="var(--gray-9)"),
                                    rx.text("Idle", size="2"),
                                    spacing="2",
                                    align="center",
                                ),
                                rx.text(
                                    "No runs yet.",
                                    size="1",
                                    color_scheme="gray",
                                ),
                                spacing="3",
                                align="start",
                            ),
                        ),
                    ),
                ),
                rx.button(
                    rx.cond(
                        AppState.dream_cycle_status == "running",
                        rx.spinner(size="2"),
                        rx.icon("play", size=14),
                    ),
                    rx.cond(
                        AppState.dream_cycle_status == "running",
                        "Running...",
                        "Run Dream Cycle",
                    ),
                    width="100%",
                    size="2",
                    variant="soft",
                    color_scheme="indigo",
                    disabled=AppState.dream_cycle_status == "running",
                    on_click=AppState.trigger_dream_cycle,
                ),
                spacing="3",
                align="start",
                width="100%",
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
        padding="1.5rem",
        background="var(--gray-1)",
        border="1px solid var(--gray-4)",
        border_radius="12px",
    )
