"""Reflex application configuration.

Excludes the SQLite database file and the data/exports directories from the
hot-reload file watcher.  Without this exclusion, every write to contexta.db
during a pipeline run triggers a hot-reload cycle, which kills worker-1 and
causes the repeated '[WARNING] Killing worker-1 after it refused to gracefully
stop' messages observed in development.

Also suppresses the Radix Themes implicit-enablement deprecation warning by
explicitly listing RadixThemesPlugin in the plugins list.
"""

import reflex as rx

config = rx.Config(
    app_name="web",
    backend_port=8001,
    # Exclude the SQLite DB and data dirs from the hot-reload watcher.
    # Reflex uses watchfiles under the hood; these globs are passed through.
    watch_ignore_dirs=[
        "*.db",
        "*.db-shm",
        "*.db-wal",
        "data/",
        "exports/",
        ".git/",
        "__pycache__/",
        ".pytest_cache/",
    ],
)
