#!/usr/bin/env bash
# entrypoint.sh — Container startup script for Solution Acceleration Engine.
#
# Steps:
#   1. Ensure /app/data directory exists (bind-mounted from host)
#   2. Run DB migrations (create tables if not exist, apply schema upgrades)
#   3. Start Reflex in production mode — serves the UI and FastAPI API routes
#      on a single port (8000)
#
# No supervisord required: single process, single port.
set -e

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Solution Acceleration Engine — Starting...             ║"
echo "╚══════════════════════════════════════════════════════════╝"

# ── Step 1: Ensure data directory ──────────────────────────────────────────────
mkdir -p /app/data
echo "[entrypoint] Data directory: /app/data"

# ── Step 2: Run DB migrations ──────────────────────────────────────────────────
echo "[entrypoint] Running database migrations..."
python -c "
import asyncio
from contexta.db.schema import init_database
import os

db_path = os.environ.get('CONTEXTA_DB_PATH', '/app/data/contexta.db')

async def migrate():
    conn = await init_database(db_path)
    await conn.close()
    print(f'[entrypoint] Database ready at: {db_path}')

asyncio.run(migrate())
"

# ── Step 3: Start Reflex (serves UI + API on port 8000) ────────────────────────
echo "[entrypoint] Starting Reflex backend on port 8000..."
exec python -m reflex run --env prod --backend-only --backend-port 8000
