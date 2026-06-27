"""web/components/finding_card.py — Single finding display card.

Renders one IssueFinding dict produced by _get_mock_data() (or the live
pipeline).  Confidence level drives the card's accent colour:

    RED    →  red border + badge
    AMBER  →  amber/orange border + badge
    GREEN  →  green border + badge

Used inside content_pane.py via rx.foreach(AppState.current_findings, ...).
"""

import reflex as rx


# ---------------------------------------------------------------------------
# Confidence colour maps
# ---------------------------------------------------------------------------

_CONFIDENCE_BORDER: dict[str, str] = {
    "RED": "#ef4444",
    "AMBER": "#f59e0b",
    "GREEN": "#22c55e",
}

_CONFIDENCE_BADGE_SCHEME: dict[str, str] = {
    "RED": "red",
    "AMBER": "yellow",
    "GREEN": "green",
}


def _confidence_border(confidence: rx.Var) -> rx.Var:
    """Return the left-border colour string for a given confidence var."""
    return rx.match(
        confidence,
        ("RED", _CONFIDENCE_BORDER["RED"]),
        ("AMBER", _CONFIDENCE_BORDER["AMBER"]),
        ("GREEN", _CONFIDENCE_BORDER["GREEN"]),
        "#475569",
    )


def _confidence_badge(confidence: rx.Var) -> rx.Component:
    """Colour-coded confidence badge (RED / AMBER / GREEN)."""
    return rx.match(
        confidence,
        (
            "RED",
            rx.badge(
                "RED",
                color_scheme="red",
                variant="solid",
                font_size="0.65rem",
                font_weight="700",
            ),
        ),
        (
            "AMBER",
            rx.badge(
                "AMBER",
                color_scheme="yellow",
                variant="solid",
                font_size="0.65rem",
                font_weight="700",
            ),
        ),
        (
            "GREEN",
            rx.badge(
                "GREEN",
                color_scheme="green",
                variant="solid",
                font_size="0.65rem",
                font_weight="700",
            ),
        ),
        rx.badge(
            confidence,
            color_scheme="gray",
            variant="soft",
            font_size="0.65rem",
        ),
    )


def _mitigation_badge(routing: rx.Var) -> rx.Component:
    """Soft badge for the mitigation routing label."""
    return rx.match(
        routing,
        (
            "Risk Register",
            rx.badge("Risk Register", color_scheme="red", variant="soft"),
        ),
        (
            "Scope Modification",
            rx.badge("Scope Modification", color_scheme="blue", variant="soft"),
        ),
        (
            "Assumptions Matrix",
            rx.badge("Assumptions Matrix", color_scheme="purple", variant="soft"),
        ),
        (
            "Both R&A",
            rx.badge("Both R&A", color_scheme="orange", variant="soft"),
        ),
        rx.badge("Ignored", color_scheme="gray", variant="soft"),
    )


def _citation_row(citation: dict) -> rx.Component:
    """Single citation reference rendered as a compact row."""
    return rx.hstack(
        rx.icon("file-text", size=11, color="#475569", flex_shrink="0"),
        rx.text(
            citation["file_path"],
            font_size="0.7rem",
            color="#64748b",
            font_family="monospace",
        ),
        rx.text(
            rx.fragment(
                "L",
                citation["line_start"].to_string(),
                "–",
                citation["line_end"].to_string(),
            ),
            font_size="0.7rem",
            color="#475569",
        ),
        spacing="1",
        align="center",
        flex_wrap="wrap",
    )


# ---------------------------------------------------------------------------
# Public component
# ---------------------------------------------------------------------------

def finding_card(finding: dict) -> rx.Component:
    """Render a single finding dict as a styled card.

    Args:
        finding: dict with keys: dimension, confidence, summary, detail,
                 citations, mitigation_routing.
    """
    return rx.box(
        # ── Card body ────────────────────────────────────────────────────
        rx.vstack(
            # Row 1: dimension label + confidence badge
            rx.hstack(
                rx.text(
                    finding["dimension"],
                    font_size="0.875rem",
                    font_weight="600",
                    color="#e2e8f0",
                    text_transform="uppercase",
                    letter_spacing="0.05em",
                ),
                _confidence_badge(finding["confidence"]),
                justify="between",
                align="center",
                width="100%",
            ),

            # Row 2: summary
            rx.text(
                finding["summary"],
                font_size="0.875rem",
                font_weight="500",
                color="#cbd5e1",
                line_height="1.5",
            ),

            # Row 3: detail
            rx.text(
                finding["detail"],
                font_size="0.8125rem",
                color="#94a3b8",
                line_height="1.6",
            ),

            # Row 4: citations
            rx.cond(
                finding["citations"].length() > 0,
                rx.box(
                    rx.text(
                        "Citations",
                        font_size="0.7rem",
                        font_weight="600",
                        color="#475569",
                        text_transform="uppercase",
                        letter_spacing="0.06em",
                        margin_bottom="0.25rem",
                    ),
                    rx.foreach(finding["citations"], _citation_row),
                    padding="0.5rem",
                    background="#0f1117",
                    border_radius="4px",
                    border="1px solid #1e293b",
                    width="100%",
                ),
                rx.fragment(),
            ),

            # Row 5: mitigation routing
            rx.hstack(
                rx.text(
                    "Routing:",
                    font_size="0.75rem",
                    color="#475569",
                    font_weight="500",
                ),
                _mitigation_badge(finding["mitigation_routing"]),
                spacing="2",
                align="center",
            ),

            spacing="3",
            align="start",
            width="100%",
        ),
        # ── Card container ───────────────────────────────────────────────
        padding="1rem",
        background="#141720",
        border="1px solid #1e293b",
        border_left=rx.fragment(
            "4px solid ",
            _confidence_border(finding["confidence"]),
        ),
        border_radius="6px",
        width="100%",
        transition="border-color 0.15s ease",
        _hover={"border_color": "#334155"},
    )
