"""
web/components/import_panel.py — Import Panel (Gap 7).

A file upload component for importing JSONPacket bundles
via /api/admin/import endpoint.
"""

import reflex as rx

from web.state import AppState


def import_panel() -> rx.Component:
    """Panel for JSON import.
    
    Gap 7 — Requirements 7.5-7.6: file upload component in
    "Import" section of Admin page, POST file to /api/admin/import,
    display success/error toast.
    """
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("upload", size=16, color="var(--gray-9)"),
                rx.text("Import JSON Packet", size="2", weight="medium"),
                spacing="3",
                align="center",
                width="100%",
            ),
            rx.divider(width="100%"),
            rx.box(
                rx.vstack(
                    rx.text(
                        "Drag and drop a JSONPacket file here, or click to select",
                        size="2",
                        color_scheme="gray",
                    ),
                    rx.upload(
                        rx.cond(
                            rx.selected_files,
                            rx.text(rx.selected_files()[0], size="2", weight="medium"),
                            rx.vstack(
                                rx.icon("upload", size=32, color="var(--accent-9)"),
                                rx.text("Click or drag file", size="2", color_scheme="gray"),
                            ),
                        ),
                        id="import_upload",
                        border="2px dashed var(--gray-5)",
                        border_radius="8px",
                        padding="2rem",
                        width="100%",
                    ),
                    rx.button(
                        "Upload",
                        size="2",
                        variant="soft",
                        color_scheme="indigo",
                        width="100%",
                        disabled=~rx.selected_files,
                        on_click=AppState.handle_import(
                            rx.selected_files(),
                            rx.selected_files()[0],
                        ),
                    ),
                    spacing="3",
                    align="start",
                    width="100%",
                ),
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
