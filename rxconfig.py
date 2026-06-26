"""
rxconfig.py — Reflex application configuration.

Port allocation (single-container):
  8000 → FastAPI  (contexta.api — REST data layer)
  8001 → Reflex backend  (WebSocket state-sync between AppState and the frontend)
  3000 → Reflex frontend (Next.js build, served by Reflex in prod mode)

api_url points to port 8000 so the Reflex-generated JS can reach the FastAPI
layer for the initial HTTP handshake.  The WebSocket state-sync channel uses
backend_port (8001) internally and is unaffected by this setting.
AppState event handlers call FastAPI independently via httpx on port 8000.
"""

import reflex as rx

config = rx.Config(
    app_name="web",
    # Move Reflex's own backend off 8000 so FastAPI can own that port.
    backend_port=8001,
    api_url="http://localhost:8000",
    # No telemetry — offline-first deployment.
    telemetry_enabled=False,
)
