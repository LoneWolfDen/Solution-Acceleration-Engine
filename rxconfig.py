"""rxconfig.py — Reflex project configuration.

Place this file at the repository root (alongside pyproject.toml).
Reflex reads it automatically on startup.

Port layout
-----------
  8000  FastAPI REST API   (AppState calls this via httpx)
  8001  Reflex WebSocket state-sync backend
  3000  Reflex Next.js frontend

api_url tells the compiled Next.js bundle where to find the Reflex
WebSocket backend.  It must point to port 8001, not 8000 (FastAPI).

In GitHub Codespaces each port gets a distinct *.app.github.dev URL,
so we derive the correct hostname from the CODESPACE_NAME env var that
Codespaces injects automatically.  Locally (Docker or bare metal) we
fall back to http://localhost:8001, overridable via REFLEX_API_URL.
"""

import os

import reflex as rx

_codespace = os.environ.get("CODESPACE_NAME", "")
if _codespace:
    _api_url = f"https://{_codespace}-8001.app.github.dev"
else:
    _api_url = os.environ.get("REFLEX_API_URL", "http://localhost:8001")

config = rx.Config(
    app_name="web",
    # WebSocket backend URL — must be port 8001 to avoid collision with FastAPI.
    api_url=_api_url,
    # Disable Reflex's own SQLite state persistence — we manage our own DB.
    db_url=None,
)
