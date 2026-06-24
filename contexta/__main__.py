"""Application entry point.

Startup sequence:
1. ``load_config()`` — parse and validate environment variables.
2. ``init_database()`` — open SQLite connection and run migrations.
3. Scan ``test_artifacts/`` directory into the ``ArtifactRegistry``.
4. Construct and run ``ContextaApp``.

On ``ConfigError``, prints a descriptive message and halts with exit code 1.

``run()`` is the synchronous entry point registered in pyproject.toml's
[project.scripts] table.  ``_async_main()`` contains the actual async logic.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path


async def _async_main() -> None:
    from .config import ConfigError, load_config
    from .db.schema import init_database
    from .mcp.artifact_registry import ArtifactRegistry
    from .tui.app import ContextaApp

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    db = await init_database(config.db_path)

    # Populate the registry from test_artifacts/ at startup so the TUI
    # displays artifacts immediately without requiring an MCP connection.
    registry = ArtifactRegistry()
    _scan_startup_artifacts(registry)

    try:
        app = ContextaApp(
            registry=registry,
            project_name="New Project",
            node_name="Draft v1",
            export_path=config.export_path,
            db_conn=db,
            config=config,
        )
        await app.run_async()
    finally:
        await db.close()


def _scan_startup_artifacts(registry: "ArtifactRegistry") -> None:  # type: ignore[name-defined]
    """Scan the ``test_artifacts/`` directory relative to the package root.

    Silently skips scanning when the directory is absent so production
    deployments without test fixtures start cleanly.
    """
    logger = logging.getLogger(__name__)
    # Resolve the package root: contexta/ → project root → test_artifacts/
    package_root = Path(__file__).parent.parent
    artifacts_dir = package_root / "test_artifacts"
    ingested = registry.scan_directory(artifacts_dir)
    if ingested:
        logger.info(
            "Startup: loaded %d artifact(s) from %s",
            len(ingested),
            artifacts_dir,
        )
    else:
        logger.debug("Startup: no artifacts found in %s", artifacts_dir)


def run() -> None:
    """Synchronous entry point for the ``contexta`` console script."""
    asyncio.run(_async_main())


if __name__ == "__main__":
    run()
