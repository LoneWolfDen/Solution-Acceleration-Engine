"""web/components/content_pane.py — Main content area.

Uses rx.cond (chained) to switch between three detail panes based on
AppState.selected_node_type:

    "review"  → ReviewDetailPane  (findings + overall confidence)
    "version" → VersionDetailPane (version metadata)
    "project" → ProjectDetailPane (project overview + tags)
    ""        → EmptyState        (no selection yet)

The computed vars show_review_pane, show_version_pane, show_project_pane
on AppState drive the conditions — each is a simple string equality check
that is always safe to evaluate.
"""

import reflex as rx

from web.state import AppState
from web.components.finding_card import finding_card
from web.components.version_detail import version_detail_pane


# ── Confidence helpers (Var-safe) ─────────────────────────────────────────────

def _overall_badge_scheme(confidence: rx.Var) -> rx.Var:
    return rx.cond(
        confidence == "RED",
        "red",
        rx.cond(confidence == "AMBER", "yellow", "green"),
    )


# ── Empty state ───────────────────────────────────────────────────────────────

def _empty_state() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("◈", font_size="2.5rem", color="#d1d5db"),
            rx.text(
                "Select a project, version, or review node from the sidebar.",
                font_size="0.95rem",
                color="#9ca3af",
                text_align="center",
                max_width="320px",
            ),
            align="center",
            spacing="3",
        ),
        display="flex",
        align_items="center",
        justify_content="center",
        height="100%",
        width="100%",
    )


# ── Project detail pane ───────────────────────────────────────────────────────

def _tag_badge(tag: str) -> rx.Component:
    return rx.badge(tag, color_scheme="indigo", variant="soft", font_size="0.75rem")


def _project_detail_pane() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(
                "PROJECT",
                font_size="0.68rem",
                font_weight="700",
                color="#9ca3af",
                letter_spacing="0.08em",
            ),
            rx.heading(
                AppState.project_detail["name"],
                size="6",
                color="#111827",
                font_weight="700",
            ),
            # ── Tags ──────────────────────────────────────────────────────────
            rx.cond(
                AppState.current_project_tags.length() > 0,
                rx.hstack(
                    rx.foreach(AppState.current_project_tags, _tag_badge),
                    spacing="2",
                    flex_wrap="wrap",
                ),
                rx.box(),
            ),
            # ── Stats ─────────────────────────────────────────────────────────
            rx.hstack(
                rx.vstack(
                    rx.text(
                        "VERSIONS",
                        font_size="0.68rem",
                        font_weight="700",
                        color="#9ca3af",
                        letter_spacing="0.08em",
                    ),
                    rx.text(
                        AppState.project_detail["version_count"],
                        font_size="1.25rem",
                        font_weight="600",
                        color="#111827",
                    ),
                    spacing="0",
                    gap="2px",
                    align="start",
                ),
                spacing="6",
                padding="1rem",
                background_color="#f9fafb",
                border="1px solid #e5e7eb",
                border_radius="8px",
                margin_top="0.5rem",
            ),
            rx.text(
                "Expand a version in the sidebar to view its review nodes.",
                font_size="0.85rem",
                color="#9ca3af",
                margin_top="0.5rem",
            ),
            spacing="3",
            align="start",
            width="100%",
        ),
        padding="2rem",
        width="100%",
    )


# ── Review detail pane ────────────────────────────────────────────────────────

def _review_detail_pane() -> rx.Component:
    return rx.box(
        rx.vstack(
            # ── Breadcrumb ────────────────────────────────────────────────────
            rx.hstack(
                rx.text(
                    AppState.review_payload["project_name"],
                    font_size="0.8rem",
                    color="#6b7280",
                ),
                rx.text("›", color="#d1d5db", font_size="0.8rem"),
                rx.text(
                    AppState.review_payload["version_name"],
                    font_size="0.8rem",
                    color="#6b7280",
                ),
                rx.text("›", color="#d1d5db", font_size="0.8rem"),
                rx.text(
                    AppState.review_payload["node_name"],
                    font_size="0.8rem",
                    color="#374151",
                    font_weight="500",
                ),
                align="center",
                spacing="1",
                flex_wrap="wrap",
            ),
            # ── Heading row: node name + overall confidence ───────────────────
            rx.hstack(
                rx.heading(
                    AppState.review_payload["node_name"],
                    size="6",
                    color="#111827",
                    font_weight="700",
                    flex="1",
                ),
                rx.badge(
                    AppState.review_payload["overall_confidence"],
                    color_scheme=_overall_badge_scheme(
                        AppState.review_payload["overall_confidence"]
                    ),
                    variant="solid",
                    font_size="0.8rem",
                    padding_x="0.75rem",
                    padding_y="0.35rem",
                ),
                align="center",
                spacing="4",
                width="100%",
            ),
            # ── Dimension label ───────────────────────────────────────────────
            rx.text(
                AppState.review_payload["dimension"],
                font_size="0.75rem",
                color="#6b7280",
                font_weight="600",
                text_transform="uppercase",
                letter_spacing="0.06em",
            ),
            rx.divider(border_color="#e5e7eb", margin_y="0.5rem"),
            # ── Findings ─────────────────────────────────────────────────────
            rx.text(
                "FINDINGS",
                font_size="0.68rem",
                font_weight="700",
                color="#9ca3af",
                letter_spacing="0.08em",
            ),
            rx.cond(
                AppState.current_findings.length() > 0,
                rx.vstack(
                    rx.foreach(AppState.current_findings, finding_card),
                    width="100%",
                    spacing="3",
                    align="start",
                ),
                rx.text(
                    "No findings recorded for this review.",
                    font_size="0.85rem",
                    color="#9ca3af",
                ),
            ),
            spacing="3",
            align="start",
            width="100%",
        ),
        padding="2rem",
        width="100%",
        max_width="860px",
    )


# ── Root content pane ─────────────────────────────────────────────────────────

def content_pane() -> rx.Component:
    """Content area that switches view based on AppState.selected_node_type.

    Uses chained rx.cond to test show_review_pane → show_version_pane →
    show_project_pane → empty state.  This is the primary mechanism that
    proves sidebar clicks update the view without any API connection.
    """
    return rx.box(
        rx.cond(
            AppState.show_review_pane,
            _review_detail_pane(),
            rx.cond(
                AppState.show_version_pane,
                version_detail_pane(),
                rx.cond(
                    AppState.show_project_pane,
                    _project_detail_pane(),
                    _empty_state(),
                ),
            ),
        ),
        flex="1",
        height="100vh",
        overflow_y="auto",
        background_color="white",
        min_width="0",
    )
