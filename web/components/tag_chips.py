"""
web/components/tag_chips.py — TagSuggestionChips component.

Shows regex-derived tag suggestions (hollow chips) and lets the user
select them (filled chips) or add custom tags via an Enter-to-add input.
All state lives in AppState; this component is a pure renderer.
"""

import reflex as rx

from web.state import AppState


def _suggestion_chip(tag: str) -> rx.Component:
    """Hollow chip for an unselected suggestion."""
    return rx.badge(
        rx.hstack(
            rx.text(tag, size="1"),
            rx.icon("plus", size=11),
            spacing="1",
            align="center",
        ),
        color_scheme="gray",
        variant="outline",
        cursor="pointer",
        on_click=AppState.toggle_suggestion_tag(tag),
        _hover={"background": "var(--gray-3)"},
    )


def _applied_chip(tag: str) -> rx.Component:
    """Filled chip for a selected/applied tag."""
    return rx.badge(
        rx.hstack(
            rx.text(tag, size="1"),
            rx.icon("x", size=11),
            spacing="1",
            align="center",
        ),
        color_scheme="blue",
        variant="solid",
        cursor="pointer",
        on_click=AppState.remove_applied_tag(tag),
    )


def tag_suggestion_chips() -> rx.Component:
    """
    Full tag-selection widget:
      1. Applied tags (filled chips with ✕ to remove).
      2. Suggestions from API (hollow chips, click to apply).
      3. Custom tag input (Enter to add).
    """
    return rx.vstack(
        # Custom input
        rx.hstack(
            rx.input(
                placeholder="Add custom tag…",
                value=AppState.artifact_custom_tag,
                on_change=AppState.set_artifact_custom_tag,
                on_key_down=lambda key: rx.cond(
                    key == "Enter",
                    AppState.add_custom_tag(),
                    rx.fragment(),
                ),
                size="2",
                width="180px",
            ),
            rx.button(
                rx.icon("plus", size=14),
                size="2",
                variant="soft",
                on_click=AppState.add_custom_tag,
            ),
            spacing="2",
            align="center",
        ),

        # Applied tags strip
        rx.cond(
            AppState.artifact_tags_applied.length() > 0,
            rx.vstack(
                rx.text("Applied", size="1", color_scheme="gray", weight="medium"),
                rx.hstack(
                    rx.foreach(AppState.artifact_tags_applied, _applied_chip),
                    spacing="2",
                    flex_wrap="wrap",
                ),
                spacing="1",
                align="start",
                width="100%",
            ),
            rx.fragment(),
        ),

        # Suggestions from API
        rx.cond(
            AppState.artifact_tag_suggestions.length() > 0,
            rx.vstack(
                rx.text("Suggestions", size="1", color_scheme="gray", weight="medium"),
                rx.hstack(
                    rx.foreach(AppState.artifact_tag_suggestions, _suggestion_chip),
                    spacing="2",
                    flex_wrap="wrap",
                ),
                spacing="1",
                align="start",
                width="100%",
            ),
            rx.fragment(),
        ),

        spacing="3",
        align="start",
        width="100%",
    )
