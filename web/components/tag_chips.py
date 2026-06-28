"""
web/components/tag_chips.py — TagSuggestionChips.

Key fix: on_key_down binds to AppState.handle_tag_key_down (a state method),
not an inline lambda with rx.cond, which is invalid in Reflex.
"""

import reflex as rx

from web.state import AppState


def _suggestion_chip(tag: str) -> rx.Component:
    return rx.badge(
        rx.hstack(rx.text(tag, size="1"), rx.icon("plus", size=11), spacing="1", align="center"),
        color_scheme="gray",
        variant="outline",
        cursor="pointer",
        on_click=AppState.toggle_suggestion_tag(tag),
        _hover={"background": "var(--gray-3)"},
    )


def _applied_chip(tag: str) -> rx.Component:
    return rx.badge(
        rx.hstack(rx.text(tag, size="1"), rx.icon("x", size=11), spacing="1", align="center"),
        color_scheme="blue",
        variant="solid",
        cursor="pointer",
        on_click=AppState.remove_applied_tag(tag),
    )


def tag_suggestion_chips() -> rx.Component:
    return rx.vstack(
        # Input row
        rx.hstack(
            rx.input(
                placeholder="Add custom tag…",
                value=AppState.artifact_custom_tag,
                on_change=AppState.set_artifact_custom_tag,
                on_key_down=AppState.handle_tag_key_down,
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
        # Applied tags
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
        # Suggestions
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
