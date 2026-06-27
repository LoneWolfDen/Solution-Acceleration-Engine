"""rxconfig.py — Reflex project configuration.

The ``web`` package (web/__init__.py) is the Reflex app entry point.
Development:   reflex run             (frontend :3000 + backend :8000)
Production:    reflex run --env prod   (optimised build, same ports)
"""

import reflex as rx

config = rx.Config(
    app_name="web",
    frontend_port=3000,
    backend_port=8000,
)
