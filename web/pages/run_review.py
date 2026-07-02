"""
web/pages/run_review.py — RunReviewPage (Milestone 4.1 / 4.2).

Route: /run-review/[version_id]

Lets the user select one or more persona roles, an AI backend, and optional
free-text context, then triggers POST /api/reviews via AppState.submit_run_review.
Persona roles are a static list (not sourced from the API); the backend
selector is populated from AppState.run_review_available_backends, which
reads the admin config providers loaded via AppState.load_admin_page.
"""

import reflex as rx

from web.state import AppState

# Static persona role list — matches the options already used in the
# Trigger Review dialog (web/components/version_detail.py) for consistency.
_PERSONA_ROLES: list[str] = [
    "Solution Architect",
    "Commercial Manager",
    "Risk Manager",
    "Delivery Lead",
    "Technical Lead",
]


def _persona_checkbox(persona: str) -> rx.Component:
    is_checked = AppState.run_review_selected_personas.contains(persona)
    return rx.hstack(
        rx.checkbox(
            checked=is_checked,
            on_change=lambda _checked: AppState.toggle_run_review_persona(persona),
        ),
        rx.text(persona, size="2"),
        spacing="2",
        align="center",
        padding="0.5rem 0.75rem",
        background="var(--gray-2)",
        border="1px solid var(--gray-4)",
        border_radius="6px",
        width="100%",
    )


def _backend_selector() -> rx.Component:
    return rx.vstack(
        rx.text("AI Backend", size="2", weight="medium"),
        rx.cond(
            AppState.run_review_available_backends.length() > 0,
            rx.select.root(
                rx.select.trigger(placeholder="Select a configured backend…"),
                rx.select.content(
                    rx.foreach(
                        AppState.run_review_available_backends,
                        lambda backend: rx.select.item(backend, value=backend),
                    ),
                ),
                value=AppState.run_review_backend,
                on_change=AppState.set_run_review_backend,
                width="100%",
            ),
            rx.hstack(
                rx.icon("triangle-alert", size=14, color="var(--amber-9)"),
                rx.text(
                    "No AI backend is configured yet. Visit the Admin page to add an API key.",
                    size="2",
                    color_scheme="amber",
                ),
                spacing="2",
                align="center",
            ),
        ),
        spacing="2",
        width="100%",
    )


def _context_textarea() -> rx.Component:
    return rx.vstack(
        rx.text("Additional Context (optional)", size="2", weight="medium"),
        rx.text_area(
            placeholder="Any extra briefing notes for the reviewer persona(s)…",
            value=AppState.run_review_context,
            on_change=AppState.set_run_review_context,
            rows="6",
            width="100%",
            resize="vertical",
        ),
        spacing="2",
        width="100%",
    )


def _header() -> rx.Component:
    return rx.hstack(
        rx.link(
            rx.hstack(
                rx.icon("arrow-left", size=14),
                rx.text("Back", size="2"),
                spacing="2",
                align="center",
            ),
            href="/",
        ),
        rx.spacer(),
        rx.heading("Run Review", size="6", weight="bold"),
        rx.spacer(),
        width="100%",
        align="center",
    )


def run_review_page() -> rx.Component:
    return rx.center(
        rx.box(
            rx.vstack(
                _header(),
                rx.separator(width="100%"),
                rx.vstack(
                    rx.text("Persona Role(s)", size="2", weight="medium"),
                    rx.vstack(
                        rx.foreach(_PERSONA_ROLES, _persona_checkbox),
                        spacing="2",
                        width="100%",
                    ),
                    spacing="2",
                    width="100%",
                ),
                _backend_selector(),
                _context_textarea(),
                rx.button(
                    rx.cond(
                        AppState.run_review_is_submitting,
                        rx.spinner(size="2"),
                        rx.icon("play", size=14),
                    ),
                    rx.cond(
                        AppState.run_review_is_submitting,
                        "Submitting…",
                        "Run Review",
                    ),
                    color_scheme="indigo",
                    size="3",
                    width="100%",
                    disabled=~AppState.run_review_can_submit,
                    on_click=AppState.submit_run_review,
                ),
                spacing="5",
                align="start",
                width="100%",
            ),
            max_width="560px",
            width="100%",
            padding="2rem",
            background="var(--gray-1)",
            border="1px solid var(--gray-4)",
            border_radius="12px",
        ),
        width="100vw",
        height="100vh",
        background="var(--gray-2)",
    )


# Registering the dynamic route via @rx.page adds ``version_id`` as an
# auto-populated AppState var (Reflex convention for [version_id] segments).
# on_load copies it into run_review_version_id and resets the form state.
run_review_page = rx.page(
    route="/run-review/[version_id]",
    on_load=AppState.init_run_review_page,
    title="Run Review — SAE",
)(run_review_page)
