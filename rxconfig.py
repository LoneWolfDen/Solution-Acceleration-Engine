"""rxconfig.py — Reflex project configuration.

Place this file at the repository root (alongside pyproject.toml).
Reflex reads it automatically on startup.
"""

import reflex as rx

config = rx.Config(
    app_name="web",
    # Disable Reflex's own SQLite state persistence — we manage our own DB.
    db_url=None,
)
