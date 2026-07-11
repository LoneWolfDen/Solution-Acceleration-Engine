"""
web/components/blueprint_panel.py — Blueprint Panel (Gap 9).

A panel for managing prompt blueprints via CRUD operations
on /api/admin/blueprints endpoints.
"""

import reflex as rx

from web.state import AppState


def _blueprint_row(blueprint: dict) -> rx.Component:
    """A row in the blueprints table."""
    return rx.tr(
        rx.td(blueprint["name"], size="2", weight="medium"),
        rx.td(blueprint["version_string"], size="2", color_scheme="gray"),
        rx.td(
            rx.cond(
                blueprint["is_active"],
                rx.badge("Active", color_scheme="green", variant="soft", size="1"),
                rx.badge("Inactive", color_scheme="gray", variant="soft", size="1"),
            ),
        ),
        rx.td(
            rx.cond(
                blueprint["is_active"],
                rx.text("", width="0"),
                rx.button(
                    "Activate",
                    size="1",
                    variant="soft",
                    color_scheme="indigo",
                    on_click=AppState.activate_blueprint(blueprint["id"]),
                ),
            ),
        ),
    )


def blueprint_panel() -> rx.Component:
    """Panel for blueprint management.
    
    Gap 9 — Requirements 9.5-9.7: displays DataTable with
    blueprints (name, version, active status), provides create
    form, and activate buttons on non-active rows.
    """
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("file-text", size=16, color="var(--gray-9)"),
                rx.text("Prompt Blueprints", size="2", weight="medium"),
                spacing="3",
                align="center",
                width="100%",
            ),
            rx.divider(width="100%"),
            # Create form
            rx.box(
                rx.vstack(
                    rx.text("Create New Blueprint", size="1", weight="medium", color_scheme="gray"),
                    rx.input(
                        placeholder="Blueprint Name",
                        id="blueprint_name_input",
                        size="2",
                    ),
                    rx.input(
                        placeholder="Version String (e.g., v1.0)",
                        id="blueprint_version_input",
                        size="2",
                    ),
                    rx.text_area(
                        placeholder="Prompt Text",
                        id="blueprint_prompt_input",
                        rows="5",
                        size="2",
                    ),
                    rx.button(
                        "Create Blueprint",
                        size="2",
                        variant="soft",
                        color_scheme="indigo",
                        width="100%",
                        on_click=AppState.create_blueprint(
                            rx.call_script("document.getElementById('blueprint_name_input').value"),
                            rx.call_script("document.getElementById('blueprint_version_input').value"),
                            rx.call_script("document.getElementById('blueprint_prompt_input').value"),
                        ),
                    ),
                    spacing="2",
                    width="100%",
                ),
                padding="1rem",
                background="var(--gray-2)",
                border="1px solid var(--gray-4)",
                border_radius="8px",
                width="100%",
            ),
            rx.divider(width="100%"),
            # Blueprint list
            rx.box(
                rx.cond(
                    AppState.admin_blueprints.length() > 0,
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Name"),
                                rx.table.column_header_cell("Version"),
                                rx.table.column_header_cell("Status"),
                                rx.table.column_header_cell("Actions"),
                            ),
                        ),
                        rx.table.body(
                            rx.foreach(
                                AppState.admin_blueprints,
                                _blueprint_row,
                            ),
                        ),
                        variant="surface",
                        width="100%",
                    ),
                    rx.text(
                        "No blueprints yet.",
                        size="2",
                        color_scheme="gray",
                    ),
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
