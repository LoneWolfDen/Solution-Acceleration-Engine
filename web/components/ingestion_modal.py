"""
web/components/ingestion_modal.py — ArtifactIngestionModal.

Tabbed modal: Upload File | Paste Text | URL Reference.
  - Title field shared across tabs.
  - TagSuggestionChips shown below content input.
  - Save → POST /api/artifacts → transitions to ArtifactTriageWidget.
  - Error surfaces as Toast via AppState.set_toast().
"""

import reflex as rx

from web.state import AppState
from web.components.tag_chips import tag_suggestion_chips
from web.components.triage_widget import triage_widget


def _source_tab_paste() -> rx.Component:
    return rx.vstack(
        rx.text_area(
            placeholder="Paste your document content here…",
            value=AppState.artifact_content,
            on_change=AppState.set_artifact_content,
            on_blur=AppState.fetch_tag_suggestions,
            rows="10",
            width="100%",
            resize="vertical",
        ),
        spacing="2",
        width="100%",
    )


def _source_tab_url() -> rx.Component:
    return rx.vstack(
        rx.input(
            placeholder="https://example.com/document.pdf",
            value=AppState.artifact_url,
            on_change=AppState.set_artifact_url,
            size="3",
            width="100%",
        ),
        rx.text(
            "Enter a publicly accessible URL to the source document.",
            size="1",
            color_scheme="gray",
        ),
        spacing="2",
        width="100%",
    )


def _form_body() -> rx.Component:
    """Common form body: title + source selector + content input + tags."""
    return rx.vstack(
        # Title
        rx.vstack(
            rx.text("Title", size="2", weight="medium"),
            rx.input(
                placeholder="e.g. Banking Statement of Work v2",
                value=AppState.artifact_title,
                on_change=AppState.set_artifact_title,
                on_blur=AppState.fetch_tag_suggestions,
                size="3",
                width="100%",
            ),
            spacing="1",
            width="100%",
        ),

        # Source selector
        rx.vstack(
            rx.text("Source", size="2", weight="medium"),
            rx.radio_group(
                rx.hstack(
                    rx.radio("Paste Text", value="paste"),
                    rx.radio("URL Reference", value="url"),
                    spacing="4",
                ),
                value=AppState.artifact_source,
                on_change=AppState.set_artifact_source,
            ),
            spacing="1",
            width="100%",
        ),

        # Content area (switches on source)
        rx.cond(
            AppState.artifact_source == "paste",
            _source_tab_paste(),
            _source_tab_url(),
        ),

        # Tag chips
        rx.vstack(
            rx.text("Tags", size="2", weight="medium"),
            tag_suggestion_chips(),
            spacing="1",
            width="100%",
        ),

        spacing="4",
        align="start",
        width="100%",
    )


def _save_phase() -> rx.Component:
    """Form + save button — shown before artifact is saved."""
    return rx.vstack(
        _form_body(),
        rx.hstack(
            rx.button(
                "Cancel",
                variant="soft",
                color_scheme="gray",
                on_click=AppState.close_ingestion_modal,
            ),
            rx.button(
                rx.cond(
                    AppState.ingestion_is_saving,
                    rx.spinner(size="2"),
                    rx.icon("save", size=14),
                ),
                rx.cond(AppState.ingestion_is_saving, "Saving…", "Save Artifact"),
                color_scheme="indigo",
                disabled=AppState.ingestion_is_saving,
                on_click=AppState.save_artifact,
            ),
            spacing="3",
            justify="end",
            width="100%",
        ),
        spacing="4",
        width="100%",
    )


def _triage_phase() -> rx.Component:
    """Triage widget — shown after artifact is saved."""
    return rx.vstack(
        rx.hstack(
            rx.icon("check-circle", size=16, color="var(--green-9)"),
            rx.text(
                rx.fragment(
                    "Artifact '",
                    AppState.last_saved_artifact.get("title", ""),
                    "' saved.",
                ),
                size="2",
                weight="medium",
            ),
            spacing="2",
            align="center",
        ),
        rx.separator(width="100%"),
        triage_widget(),
        rx.button(
            "Add Another Artifact",
            variant="soft",
            color_scheme="gray",
            on_click=AppState.open_ingestion_modal,
            width="100%",
        ),
        spacing="4",
        width="100%",
    )


def ingestion_modal() -> rx.Component:
    """
    Artifact ingestion modal dialog.
    Controlled by AppState.artifact_ingestion_open.
    """
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Ingest Artifact"),
            rx.dialog.description(
                "Add source documents to the selected project.",
                size="2",
                color_scheme="gray",
            ),
            rx.separator(width="100%", my="3"),
            # Phase 1: form / Phase 2: triage
            rx.cond(
                AppState.last_saved_artifact == {},
                _save_phase(),
                _triage_phase(),
            ),
            max_width="600px",
            padding="1.5rem",
        ),
        open=AppState.artifact_ingestion_open,
        on_open_change=AppState.close_ingestion_modal,
    )
