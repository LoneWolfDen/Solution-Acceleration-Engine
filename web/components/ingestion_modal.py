"""
web/components/ingestion_modal.py — ArtifactIngestionModal.
"""

import reflex as rx

from web.state import AppState
from web.components.tag_chips import tag_suggestion_chips
from web.components.triage_widget import triage_widget


def _source_tab_paste() -> rx.Component:
    return rx.text_area(
        placeholder="Paste your document content here…",
        value=AppState.artifact_content,
        on_change=AppState.set_artifact_content,
        on_blur=AppState.fetch_tag_suggestions,
        rows="10",
        width="100%",
        resize="vertical",
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
        rx.text("Enter a publicly accessible URL to the source document.", size="1", color_scheme="gray"),
        spacing="2",
        width="100%",
    )


def _source_tab_upload() -> rx.Component:
    return rx.vstack(
        rx.upload.root(
            rx.vstack(
                rx.icon("upload", size=28, color="var(--gray-8)"),
                rx.text(
                    "Drag and drop a file here, or click to browse",
                    size="2",
                    color_scheme="gray",
                    text_align="center",
                ),
                spacing="2",
                align="center",
            ),
            id="artifact_upload",
            multiple=False,
            max_files=1,
            on_drop=AppState.handle_artifact_upload(
                rx.upload_files(upload_id="artifact_upload")
            ),
            border="1px dashed var(--gray-7)",
            border_radius="8px",
            padding="2rem",
            width="100%",
            cursor="pointer",
        ),
        rx.cond(
            AppState.artifact_upload_filename != "",
            rx.hstack(
                rx.icon("file-check-2", size=14, color="var(--green-9)"),
                rx.text(AppState.artifact_upload_filename, size="2", weight="medium"),
                rx.icon_button(
                    rx.icon("x", size=12),
                    size="1",
                    variant="ghost",
                    color_scheme="gray",
                    on_click=AppState.clear_artifact_upload,
                ),
                spacing="2",
                align="center",
            ),
            rx.fragment(),
        ),
        spacing="2",
        width="100%",
    )


def _form_body() -> rx.Component:
    return rx.vstack(
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
        rx.vstack(
            rx.text("Source", size="2", weight="medium"),
            rx.radio_group(
                ["Upload File", "Paste Text", "URL Reference"],
                value=rx.cond(
                    AppState.artifact_source == "upload",
                    "Upload File",
                    rx.cond(
                        AppState.artifact_source == "paste",
                        "Paste Text",
                        "URL Reference",
                    ),
                ),
                on_change=AppState.set_artifact_source,
                direction="row",
                gap="4",
            ),
            spacing="1",
            width="100%",
        ),
        rx.cond(
            AppState.artifact_source == "upload",
            _source_tab_upload(),
            rx.cond(
                AppState.artifact_source == "paste",
                _source_tab_paste(),
                _source_tab_url(),
            ),
        ),
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
    return rx.vstack(
        _form_body(),
        rx.hstack(
            rx.button("Cancel", variant="soft", color_scheme="gray", on_click=AppState.close_ingestion_modal),
            rx.button(
                rx.cond(AppState.ingestion_is_saving, rx.spinner(size="2"), rx.icon("save", size=14)),
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
    return rx.vstack(
        rx.hstack(
            rx.icon("circle-check", size=16, color="var(--green-9)"),
            rx.text(
                rx.fragment("Artifact '", AppState.last_saved_artifact["title"], "' saved."),
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
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Ingest Artifact"),
            rx.dialog.description(
                "Add source documents to the selected project.",
                size="2",
                color_scheme="gray",
            ),
            rx.separator(width="100%", my="3"),
            rx.cond(
                AppState.artifact_save_complete,
                _triage_phase(),
                _save_phase(),
            ),
            max_width="600px",
            padding="1.5rem",
        ),
        open=AppState.artifact_ingestion_open,
        on_open_change=AppState.close_ingestion_modal,
    )
