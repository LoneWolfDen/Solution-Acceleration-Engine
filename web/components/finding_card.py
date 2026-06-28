"""
web/components/finding_card.py — FindingCard component.

Renders a single FindingItem dict from the ReviewPayloadResponse:
  { finding_id, type, severity, text, source_artifact, citation }

Severity drives the card's accent colour:
  HIGH    → red border + badge
  MEDIUM  → amber/orange border + badge
  LOW     → green border + badge
"""

import reflex as rx


# ── Colour helpers ────────────────────────────────────────────────────────────

def _severity_border(severity: rx.Var) -> rx.Var:
    return rx.match(
        severity,
        ("HIGH", "#ef4444"),
        ("MEDIUM", "#f59e0b"),
        ("LOW", "#22c55e"),
        "#64748b",
    )


def _severity_badge(severity: rx.Var) -> rx.Component:
    return rx.match(
        severity,
        (
            "HIGH",
            rx.badge("HIGH", color_scheme="red", variant="solid", size="1"),
        ),
        (
            "MEDIUM",
            rx.badge("MEDIUM", color_scheme="yellow", variant="solid", size="1"),
        ),
        (
            "LOW",
            rx.badge("LOW", color_scheme="green", variant="solid", size="1"),
        ),
        rx.badge(severity, color_scheme="gray", variant="soft", size="1"),
    )


def _type_badge(finding_type: rx.Var) -> rx.Component:
    return rx.badge(
        finding_type,
        color_scheme="indigo",
        variant="soft",
        size="1",
    )


# ── Public component ──────────────────────────────────────────────────────────

def finding_card(finding: dict) -> rx.Component:
    """
    Render a single FindingItem dict as a styled card.

    Fields used: type, severity, text, source_artifact, citation.
    """
    return rx.box(
        rx.vstack(
            # Row 1: type badge + severity badge
            rx.hstack(
                _type_badge(finding["type"]),
                _severity_badge(finding["severity"]),
                rx.spacer(),
                rx.text(
                    finding["source_artifact"],
                    size="1",
                    color_scheme="gray",
                    font_family="monospace",
                    truncate=True,
                    max_width="200px",
                ),
                align="center",
                width="100%",
            ),

            # Row 2: finding text
            rx.text(
                finding["text"],
                size="2",
                color="var(--gray-12)",
                line_height="1.6",
            ),

            # Row 3: citation excerpt (if present)
            rx.cond(
                finding["citation"] != "",
                rx.box(
                    rx.text(
                        finding["citation"],
                        size="1",
                        color_scheme="gray",
                        font_family="monospace",
                        line_height="1.5",
                    ),
                    padding="0.5rem 0.75rem",
                    background="var(--gray-3)",
                    border_left="3px solid var(--gray-8)",
                    border_radius="0 4px 4px 0",
                    width="100%",
                ),
                rx.fragment(),
            ),

            spacing="3",
            align="start",
            width="100%",
        ),
        # Card container with severity-coloured left border
        padding="1rem",
        background="var(--gray-2)",
        border="1px solid var(--gray-4)",
        border_left=rx.fragment("4px solid ", _severity_border(finding["severity"])),
        border_radius="6px",
        width="100%",
        transition="border-color 0.15s ease",
        _hover={"border_color": "var(--gray-6)"},
    )
