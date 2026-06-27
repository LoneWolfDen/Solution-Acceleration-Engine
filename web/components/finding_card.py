"""web/components/finding_card.py — Renders a single IssueFinding dict.

IssueFinding shape (mirrors contexta/models/findings.py):
    dimension         str   — ReviewDimensionEnum value
    confidence        str   — "RED" | "AMBER" | "GREEN"
    summary           str   — one-line headline
    detail            str   — full narrative paragraph
    citations         list  — list of SourceCitation dicts
    mitigation_routing str  — MitigationRoutingEnum value

The card's left border and badge colour signal the confidence level.
Because `confidence` is a runtime Var inside rx.foreach, all colour
decisions use rx.cond chains rather than Python dicts.
"""

import reflex as rx


# ── Confidence → colour helpers (Var-safe rx.cond chains) ────────────────────

def _border_color(confidence: rx.Var) -> rx.Var:
    return rx.cond(
        confidence == "RED",
        "#ef4444",
        rx.cond(confidence == "AMBER", "#f59e0b", "#22c55e"),
    )


def _bg_color(confidence: rx.Var) -> rx.Var:
    return rx.cond(
        confidence == "RED",
        "#fff5f5",
        rx.cond(confidence == "AMBER", "#fffbeb", "#f0fdf4"),
    )


def _badge_color_scheme(confidence: rx.Var) -> rx.Var:
    return rx.cond(
        confidence == "RED",
        "red",
        rx.cond(confidence == "AMBER", "yellow", "green"),
    )


def _mitigation_badge_scheme(routing: rx.Var) -> rx.Var:
    return rx.cond(
        routing == "Scope Modification",
        "blue",
        rx.cond(
            routing == "Risk Register",
            "orange",
            rx.cond(routing == "Assumptions Matrix", "purple", "gray"),
        ),
    )


# ── Citation row ──────────────────────────────────────────────────────────────

def _citation_row(citation: dict) -> rx.Component:
    """Render a single SourceCitation as a compact inline block."""
    return rx.hstack(
        rx.badge(
            citation["citation_type"],
            color_scheme="blue",
            variant="outline",
            font_size="0.65rem",
        ),
        rx.text(
            citation["file_path"],
            font_size="0.75rem",
            font_weight="500",
            color="#374151",
        ),
        rx.text(
            "L",
            rx.text.span(citation["line_start"]),
            "–",
            rx.text.span(citation["line_end"]),
            font_size="0.7rem",
            color="#9ca3af",
        ),
        rx.text(
            citation["excerpt"],
            font_size="0.72rem",
            color="#6b7280",
            font_style="italic",
            overflow="hidden",
            text_overflow="ellipsis",
            white_space="nowrap",
            flex="1",
        ),
        align="center",
        spacing="2",
        width="100%",
        padding="0.3rem 0",
        border_top="1px solid #f3f4f6",
    )


# ── Main card ─────────────────────────────────────────────────────────────────

def finding_card(finding: dict) -> rx.Component:
    """Render one IssueFinding as a bordered card.

    Left border colour encodes confidence level (RED/AMBER/GREEN).
    Mitigation routing is shown as a badge in the card footer.
    Citations are listed below the detail text.
    """
    return rx.box(
        rx.vstack(
            # ── Header row: confidence badge + summary ────────────────────────
            rx.hstack(
                rx.badge(
                    finding["confidence"],
                    color_scheme=_badge_color_scheme(finding["confidence"]),
                    variant="soft",
                    font_size="0.7rem",
                    font_weight="700",
                ),
                rx.text(
                    finding["summary"],
                    font_size="0.875rem",
                    font_weight="600",
                    color="#111827",
                    flex="1",
                ),
                align="start",
                spacing="3",
                width="100%",
            ),
            # ── Dimension label ───────────────────────────────────────────────
            rx.text(
                finding["dimension"],
                font_size="0.72rem",
                color="#6b7280",
                font_weight="500",
                text_transform="uppercase",
                letter_spacing="0.05em",
            ),
            # ── Detail paragraph ──────────────────────────────────────────────
            rx.text(
                finding["detail"],
                font_size="0.85rem",
                color="#374151",
                line_height="1.6",
            ),
            # ── Citations ─────────────────────────────────────────────────────
            rx.cond(
                finding["citations"].length() > 0,
                rx.vstack(
                    rx.text(
                        "CITATIONS",
                        font_size="0.65rem",
                        font_weight="700",
                        color="#9ca3af",
                        letter_spacing="0.08em",
                        padding_top="0.25rem",
                    ),
                    rx.foreach(finding["citations"], _citation_row),
                    width="100%",
                    spacing="0",
                    gap="0",
                    align="start",
                ),
                rx.box(),
            ),
            # ── Footer: mitigation routing ────────────────────────────────────
            rx.hstack(
                rx.text(
                    "Mitigation:",
                    font_size="0.75rem",
                    color="#6b7280",
                    font_weight="500",
                ),
                rx.badge(
                    finding["mitigation_routing"],
                    color_scheme=_mitigation_badge_scheme(
                        finding["mitigation_routing"]
                    ),
                    variant="soft",
                    font_size="0.7rem",
                ),
                align="center",
                spacing="2",
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        background_color=_bg_color(finding["confidence"]),
        border_left=rx.cond(
            finding["confidence"] == "RED",
            "4px solid #ef4444",
            rx.cond(
                finding["confidence"] == "AMBER",
                "4px solid #f59e0b",
                "4px solid #22c55e",
            ),
        ),
        border_radius="0 6px 6px 0",
        padding="1rem",
        width="100%",
    )
