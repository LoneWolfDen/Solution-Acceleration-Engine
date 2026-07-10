"""rxconfig.py — Reflex project configuration.

Place this file at the repository root (alongside pyproject.toml).
Reflex reads it automatically on startup.

Single-port architecture (Milestone 7)
---------------------------------------
  8000  Reflex backend — serves the pre-built frontend static assets,
        handles WebSocket state-sync, and mounts FastAPI API routes
        (via api_transformer in web/web.py).

api_url tells the compiled frontend where to find the Reflex
WebSocket backend.  In the single-port setup this is the same port.

In GitHub Codespaces each port gets a distinct *.app.github.dev URL,
so we derive the correct hostname from the CODESPACE_NAME env var that
Codespaces injects automatically.  Locally (Docker or bare metal) we
fall back to http://localhost:8000, overridable via REFLEX_API_URL.
"""

import os

import reflex as rx

_codespace = os.environ.get("CODESPACE_NAME", "")
if _codespace:
    _api_url = f"https://{_codespace}-8000.app.github.dev"
else:
    _api_url = os.environ.get("REFLEX_API_URL", "http://localhost:8000")

config = rx.Config(
    app_name="web",
    backend_port=8000,
    api_url=_api_url,
    frontend_packages=[],
    db_url=None,
    vite_allowed_hosts=True,
    ignored_dirs=[".git", ".github", ".vscode", "venv", "__pycache__",".venv", "node_modules", "dist", "build", ".next", ".output", ".cache"],
)
