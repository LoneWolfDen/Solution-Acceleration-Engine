"""
web/components/layout.py — Master-detail shell.

Composes the sidebar (fixed-width left panel) and the node detail pane
(flexible right pane) into a full-height horizontal split.

Also mounts rx.toast.provider() here so toast notifications triggered by
AppState event handlers are visible everywhere in the app.
"""

import reflex as rx

from .node_detail import node_detail
from .sidebar import sidebar


def layout() -> rx.Component:
    """
    Top-level page layout.

    ┌──────────────┬───────────────────────────────────┐
    │   Sidebar    │         Node Detail Pane           │
    │  (280px)     │         (flex: 1)                  │
    └──────────────┴───────────────────────────────────┘
    """
    return rx.fragment(
        rx.hstack(
            sidebar(),
            rx.box(
                node_detail(),
                flex="1",
                height="100vh",
                overflow="hidden",
                background_color="var(--color-background)",
            ),
            width="100%",
            height="100vh",
            spacing="0",
            overflow="hidden",
        ),
        # Global toast provider — required for rx.toast.error() / .success()
        # to render.  Must appear once in the component tree.
        rx.toast.provider(),
    )
