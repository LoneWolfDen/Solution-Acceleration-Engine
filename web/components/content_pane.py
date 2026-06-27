"""web/components/content_pane.py — Main content area with rx.cond view switcher.

Active view is driven exclusively by AppState.active_view:

    "welcome"  →  WelcomeView  (initial state, nothing selected)
    "version"  →  VersionDetail (AppState.current_version populated)
    "node"     →  NodeFindingsView (AppState.current_findings populated)

The three views are mutually exclusive; only one is mounted at a time.
"""

import reflex as rx

from web.state import AppState
from web.components.finding_card import finding_card
from web.components.version_detail import version_detail


# ---------------------------------------------------------------------------
# Welcome view — shown before any selection is made
# ---------------------------------------------------------------------------

def _welcome_view() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.icon("zap", size=48, color="#1e293b"),
            rx.heading(
                "Solution Acceleration Engine",
                size="6",
                color="#334155",
                text_align="center",
                font_weight="700",
            ),
            rx.text(
                "Select a project from the sidebar to begin.",
                font_size="0.9375rem",
                color="#475569",
                text_align="center",
            ),
            rx.cond(
                AppState.selected_project_id != "",
                rx.text(
                    "Now select a version or node to view its analysis.",
                    font_size="0.875rem",
                    color="#64748b",
                    text_align="center",
                ),
                rx.fragment(),
            ),
            spacing="4",
            align="center",
        ),
        display="flex",
        align_items="center",
        justify_content="center",
        width="100%",
        height="100%",
        background="#0b0e14",
    )


# ---------------------------------------------------------------------------
# Node findings view — renders all findings for the selected node
# ---------------------------------------------------------------------------

def _node_findings_view() -> rx.Component:
    return rx.box(
        rx.vstack(
            # Header
            rx.box(
                rx.hstack(
                    rx.icon("scan-search", size=18, color="#818cf8"),
                    rx.vstack(
                        rx.heading(
                            AppState.current_node["node_name"],
                            size="5",
                            color="#e2e8f0",
                            font_weight="700",
                        ),
                        rx.hstack(
                            rx.badge(
                                AppState.current_node["layer_type"],
                                color_scheme="indigo",
                                variant="soft",
                                font_size="0.65rem",
                            ),
                            rx.text(
                                AppState.current_node["created_at"],
                                font_size="0.7rem",
                                color="#475569",
                                font_family="monospace",
                            ),
                            spacing="2",
                            align="center",
                        ),
                        spacing="1",
                        align="start",
                    ),
                    spacing="3",
                    align="start",
                ),
                padding_bottom="1rem",
                border_bottom="1px solid #1e293b",
                width="100%",
            ),

            # Finding count
            rx.hstack(
                rx.icon("list", size=14, color="#64748b"),
                rx.text(
                    rx.fragment(
                        AppState.current_findings.length().to_string(),
                        " findings",
                    ),
                    font_size="0.75rem",
                    font_weight="600",
                    letter_spacing="0.07em",
                    text_transform="uppercase",
                    color="#64748b",
                ),
                spacing="2",
                align="center",
            ),

            # Finding cards
            rx.cond(
                AppState.current_findings.length() > 0,
                rx.vstack(
                    rx.foreach(AppState.current_findings, finding_card),
                    spacing="3",
                    width="100%",
                ),
                rx.box(
                    rx.text(
                        "No findings recorded for this node.",
                        font_size="0.875rem",
                        color="#475569",
                        text_align="center",
                    ),
                    padding="2rem",
                    width="100%",
                    text_align="center",
                ),
            ),

            spacing="4",
            align="start",
            width="100%",
        ),
        padding="2rem",
        width="100%",
        height="100%",
        overflow_y="auto",
        background="#0b0e14",
    )


# ---------------------------------------------------------------------------
# Public content pane — rx.cond view switcher
# ---------------------------------------------------------------------------

def content_pane() -> rx.Component:
    """Render the correct view based on AppState.active_view.

    Hierarchy:
        active_view == "welcome"  →  _welcome_view()
        active_view == "version"  →  version_detail()
        active_view == "node"     →  _node_findings_view()
    """
    return rx.box(
        rx.cond(
            AppState.active_view == "welcome",
            _welcome_view(),
            rx.cond(
                AppState.active_view == "version",
                version_detail(),
                _node_findings_view(),
            ),
        ),
        flex="1",
        height="100vh",
        overflow="hidden",
        background="#0b0e14",
    )
