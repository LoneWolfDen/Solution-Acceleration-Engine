"""Application entry point.

Startup sequence:
1. ``load_config()`` — parse and validate environment variables.
2. ``init_database()`` — open SQLite connection and run migrations.
3. Construct and run ``ContextaApp``.

On ``ConfigError``, prints a descriptive message and halts with exit code 1.

``run()`` is the synchronous entry point registered in pyproject.toml's
[project.scripts] table.  ``_async_main()`` contains the actual async logic.
"""

from __future__ import annotations

import asyncio
import logging
import sys


async def _async_main() -> None:
    from .config import ConfigError, load_config
    from .db.schema import init_database
    from .tui.app import ContextaApp

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    db = await init_database(config.db_path)

    try:
        app = ContextaApp(
            project_name="New Project",
            node_name="Draft v1",
            export_path=config.export_path,
            db_conn=db,
            config=config,
        )
        await app.run_async()
    finally:
        await db.close()


def run() -> None:
    """Synchronous entry point for the ``contexta`` console script."""
    asyncio.run(_async_main())


if __name__ == "__main__":
    run()
