"""
web/pages/admin.py — AdminDashboardPage (Milestone 3).

All dict access uses bracket notation (not .get()) for Reflex Var safety.
admin_config and admin_health are initialised with safe defaults in AppState
so bracket access is always valid.
"""

import reflex as rx

from web.state import AppState


def _provider_pill(name: str, status: rx.Var) -> rx.Component:
    is_ok = (status == "configured") | (status == "set")
    return rx.hstack(
        rx.icon(
            rx.cond(is_ok, "circle-check", "circle-x"),
            size=14,
            color=rx.cond(is_ok, "var(--green-9)", "var(--gray-9)"),
        ),
        rx.text(name.upper(), size="2", weight="medium"),
        rx.badge(status, color_scheme=rx.cond(is_ok, "green", "gray"), variant="soft", size="1"),
        spacing="2",
        align="center",
        padding="0.5rem 0.875rem",
        background="var(--gray-2)",
        border="1px solid var(--gray-4)",
        border_radius="8px",
    )


def _section_card(title: str, *children) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.heading(title, size="4", weight="bold"),
            rx.separator(width="100%"),
            *children,
            spacing="4",
            align="start",
            width="100%",
        ),
        padding="1.5rem",
        background="var(--gray-2)",
        border="1px solid var(--gray-4)",
        border_radius="12px",
        width="100%",
    )


# ── Section 1: System Health ──────────────────────────────────────────────────

def _health_section() -> rx.Component:
    providers = AppState.admin_health_providers
    last_run = AppState.admin_health_last_run
    return _section_card(
        "System Health",
        rx.hstack(
            _provider_pill("Groq", providers["groq"]),
            _provider_pill("OpenRouter", providers["openrouter"]),
            _provider_pill("Gemini", providers["gemini"]),
            _provider_pill("Ollama", providers["ollama"]),
            spacing="3",
            flex_wrap="wrap",
        ),
        rx.hstack(
            rx.text("Last review run:", size="2", color_scheme="gray"),
            rx.text(rx.cond(last_run, last_run, "Never"), size="2", font_family="monospace"),
            spacing="2",
            align="center",
        ),
    )


# ── Section 2: LLM Configuration ─────────────────────────────────────────────

def _api_key_field(provider: str) -> rx.Component:
    providers_cfg = AppState.admin_config_providers
    key_status = providers_cfg[provider]
    is_set = key_status == "set"
    placeholder = rx.cond(is_set, "••••••••  (currently set)", "Paste API key here…")
    return rx.hstack(
        rx.text(provider.upper(), size="2", weight="medium", width="120px"),
        rx.input(
            placeholder=placeholder,
            id=f"key_input_{provider}",
            size="2",
            type="password",
            flex="1",
        ),
        rx.button(
            "Save",
            size="2",
            variant="soft",
            color_scheme="indigo",
            on_click=rx.call_script(
                f"document.getElementById('key_input_{provider}').value",
                callback=lambda v: AppState.save_api_key(provider, v),
            ),
        ),
        rx.badge(key_status, color_scheme=rx.cond(is_set, "green", "gray"), variant="soft", size="1"),
        spacing="3",
        align="center",
        width="100%",
    )


def _llm_config_section() -> rx.Component:
    ollama_url = AppState.admin_config_ollama_url_value
    return _section_card(
        "LLM Configuration",
        _api_key_field("groq"),
        _api_key_field("openrouter"),
        _api_key_field("gemini"),
        rx.separator(width="100%"),
        rx.hstack(
            rx.text("Ollama URL", size="2", weight="medium", width="120px"),
            rx.input(
                placeholder="http://localhost:11434",
                default_value=ollama_url,
                id="ollama_url_input",
                size="2",
                flex="1",
            ),
            rx.button(
                "Save",
                size="2",
                variant="soft",
                color_scheme="indigo",
                on_click=rx.call_script(
                    "document.getElementById('ollama_url_input').value",
                    callback=lambda v: AppState.save_api_key("ollama", v),
                ),
            ),
            spacing="3",
            align="center",
            width="100%",
        ),
    )


# ── Section 3: Gate Thresholds ────────────────────────────────────────────────

def _threshold_row(label: str, key: str) -> rx.Component:
    current_val = AppState.admin_config_thresholds[key]
    return rx.hstack(
        rx.text(label, size="2", weight="medium", width="140px"),
        rx.input(
            default_value=current_val.to(str),
            id=f"threshold_{key}",
            size="2",
            type="number",
            min="0",
            max="1",
            step="0.01",
            width="100px",
        ),
        rx.button(
            "Save",
            size="2",
            variant="soft",
            color_scheme="indigo",
            on_click=rx.call_script(
                f"parseFloat(document.getElementById('threshold_{key}').value)",
                callback=lambda v: AppState.save_threshold(key, v),
            ),
        ),
        spacing="3",
        align="center",
    )


def _thresholds_section() -> rx.Component:
    return _section_card(
        "Gate Thresholds",
        _threshold_row("Risk threshold", "risk"),
        _threshold_row("Constraint threshold", "constraint"),
        _threshold_row("Dependency threshold", "dependency"),
    )


# ── Section 4: Project Management ─────────────────────────────────────────────

def _project_row(project: dict) -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.text(project["name"], size="2", weight="medium"),
            rx.text(
                rx.fragment(project["version_count"], " versions  ·  ", project["review_count"], " reviews"),
                size="1",
                color_scheme="gray",
            ),
            spacing="1",
            align="start",
            flex="1",
        ),
        rx.alert_dialog.root(
            rx.alert_dialog.trigger(
                rx.button(rx.icon("trash-2", size=14), "Delete ⚠", variant="soft", color_scheme="red", size="2"),
            ),
            rx.alert_dialog.content(
                rx.alert_dialog.title("Delete Project?"),
                rx.alert_dialog.description(
                    rx.fragment(
                        "This will permanently delete '",
                        project["name"],
                        "' and all its versions, artifacts, and reviews.",
                    ),
                    size="2",
                    color_scheme="gray",
                ),
                rx.hstack(
                    rx.alert_dialog.cancel(rx.button("Cancel", variant="soft", color_scheme="gray")),
                    rx.alert_dialog.action(
                        rx.button(
                            "Delete Project",
                            color_scheme="red",
                            on_click=AppState.delete_project(project["id"]),
                        ),
                    ),
                    spacing="3",
                    justify="end",
                ),
                max_width="420px",
            ),
        ),
        justify="between",
        align="center",
        padding="0.75rem",
        background="var(--gray-2)",
        border="1px solid var(--gray-4)",
        border_radius="8px",
        width="100%",
    )


def _projects_section() -> rx.Component:
    return _section_card(
        "Project Management",
        rx.cond(
            AppState.projects.length() > 0,
            rx.vstack(rx.foreach(AppState.projects, _project_row), spacing="2", width="100%"),
            rx.text("No projects yet.", size="2", color_scheme="gray"),
        ),
    )


# ── Page ──────────────────────────────────────────────────────────────────────

@rx.page(route="/admin", on_load=AppState.load_admin_page, title="Admin — SAE")
def admin_page() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.icon("layout-dashboard", size=16),
                        rx.heading("Contexta", size="4"),
                        spacing="2",
                        align="center",
                        padding="0.875rem 1rem",
                    ),
                    rx.separator(width="100%"),
                    rx.link(
                        rx.hstack(
                            rx.icon("arrow-left", size=14),
                            rx.text("Back to Dashboard", size="2"),
                            spacing="2",
                            align="center",
                        ),
                        href="/",
                        padding="0.75rem 1rem",
                        width="100%",
                        _hover={"background": "var(--gray-3)"},
                        border_radius="6px",
                    ),
                    spacing="0",
                    align_items="stretch",
                    height="100vh",
                ),
                width="220px",
                min_width="220px",
                border_right="1px solid var(--gray-4)",
                background="var(--gray-1)",
                flex_shrink="0",
            ),
            rx.box(
                rx.cond(
                    AppState.admin_loading,
                    rx.center(rx.spinner(size="3"), height="80vh"),
                    rx.scroll_area(
                        rx.vstack(
                            rx.heading("Admin Dashboard", size="7", weight="bold"),
                            _health_section(),
                            _llm_config_section(),
                            _thresholds_section(),
                            _projects_section(),
                            spacing="5",
                            align="start",
                            width="100%",
                            max_width="900px",
                            padding="2rem",
                        ),
                        width="100%",
                        height="100vh",
                        type="auto",
                    ),
                ),
                flex="1",
                height="100vh",
                overflow="hidden",
            ),
            spacing="0",
            align="stretch",
            width="100vw",
            height="100vh",
        ),
        width="100vw",
        height="100vh",
        overflow="hidden",
    )
