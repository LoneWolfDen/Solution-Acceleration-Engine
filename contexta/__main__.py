"""Application entry point.

Startup sequence:
1. ``load_config()`` — parse and validate environment variables.
2. ``init_database()`` — open SQLite connection and run migrations.
3. Construct and run ``ContextaApp``.

On ``ConfigError``, prints a descriptive message and halts with exit code 1.
"""

from __future__ import annotations

import asyncio
import sys


async def main() -> None:
    from .config import ConfigError, load_config
    from .db.schema import init_database
    from .tui.app import ContextaApp

    try:
        config = load_config()
    except ConfigError as exc:
        # Can't launch TUI yet — print to stderr and exit
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    db = await init_database(config.db_path)

    try:
        app = ContextaApp(config=config, db=db)
        await app.run_async()
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
