"""Contexta Web UI — Reflex application package.

Reflex discovers this module via rxconfig.py (app_name="web").
The rx.App instance is defined in web/app.py and re-exported here
so Reflex can find it at the package root.
"""

from web.app import app  # noqa: F401 — required for Reflex discovery
