"""
rxconfig.py — Reflex application configuration.

Port allocation (single-container):
  8000 → FastAPI  (contexta.api — REST data layer)
  8001 → Reflex backend  (WebSocket state-sync between AppState and the frontend)
  3000 → Reflex frontend (Next.js build, served by Reflex in prod mode)

The Reflex frontend JS connects to the Reflex backend (api_url) for state sync
via a persistent WebSocket.  AppState event handlers call FastAPI *server-side*
via httpx on port 8000 — that traffic never leaves the container.

Codespace / proxy support
─────────────────────────
In GitHub Codespaces the browser runs on the developer's machine, NOT inside
the Codespace.  "localhost" in the browser resolves to the developer's laptop,
not the Codespace server.  The api_url therefore MUST be the public forwarded
URL for port 8001.

Automatic detection (two mechanisms, evaluated in order):

  1. CODESPACE_NAME env var — set automatically by Codespaces.
     Derives: https://{CODESPACE_NAME}-8001.app.github.dev

  2. REFLEX_API_URL env var — explicit override for any other proxy/tunnel
     environment (ngrok, devcontainer, custom reverse proxy).
     Example: export REFLEX_API_URL=https://my-tunnel.ngrok.io

  If neither is set, falls back to http://localhost:8001 for pure local dev.
"""

import os

import reflex as rx

# ── api_url: URL the BROWSER uses to reach the Reflex state-sync backend ──────
_codespace_name: str = os.environ.get("CODESPACE_NAME", "")
if _codespace_name:
    # GitHub Codespaces: derive the public forwarded URL for port 8001
    _api_url: str = f"https://{_codespace_name}-8001.app.github.dev"
else:
    # Allow an explicit override (ngrok, devcontainer, etc.); fall back to local
    _api_url = os.environ.get("REFLEX_API_URL", "http://localhost:8001")

config = rx.Config(
    app_name="web",
    # Reflex state-sync backend on 8001 — distinct from FastAPI on 8000.
    frontend_port=3000,
    backend_port=8001,
    api_url=_api_url,
    # No telemetry — offline-first deployment constraint.
    telemetry_enabled=False,
)
