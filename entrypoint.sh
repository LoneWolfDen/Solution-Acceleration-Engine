#!/usr/bin/env bash
# entrypoint.sh — Solution Acceleration Engine container start-up script.
#
# Steps:
#   1. Ensure /app/data/ exists (volume may be freshly mounted and empty).
#   2. Run DB migrations (init_database is idempotent — safe on every start).
#   3. Start Reflex, which:
#        • Serves the pre-built static frontend on port 8000.
#        • Mounts the FastAPI app (contexta.api:app) on the backend port (8001).
#        • Proxies /api/* from 8000 → 8001 automatically.
#
# Single process — no supervisord required.
# All environment variables are injected at runtime via docker-compose.yml / --env.
#
# Environment variables (all optional — have defaults):
#   CONTEXTA_DB_PATH      default: /app/data/contexta.db
#   CONTEXTA_EXPORT_PATH  default: /app/exports
#   CONTEXTA_LOG_LEVEL    default: WARNING
#   GROQ_API_KEY          default: (empty — provider shows 'not_set' in admin)
#   OPENROUTER_API_KEY    default: (empty)
#   GEMINI_API_KEY        default: (empty)
#   OLLAMA_BASE_URL       default: http://localhost:11434

set -euo pipefail

DB_PATH="${CONTEXTA_DB_PATH:-/app/data/contexta.db}"
EXPORT_PATH="${CONTEXTA_EXPORT_PATH:-/app/exports}"

# ── Step 1: Ensure persistent directories exist ───────────────────────────────
mkdir -p "$(dirname "$DB_PATH")"
mkdir -p "$EXPORT_PATH"

echo "[entrypoint] DB path:     $DB_PATH"
echo "[entrypoint] Export path: $EXPORT_PATH"

# ── Step 2: Run DB migrations ─────────────────────────────────────────────────
# init_database() creates all tables (CREATE TABLE IF NOT EXISTS) and applies
# incremental column migrations. Safe to run on every container start.
echo "[entrypoint] Running database migrations..."
python - <<'PYEOF'
import asyncio, os, sys
sys.path.insert(0, "/app")
from contexta.db.schema import init_database

async def migrate():
    db_path = os.environ.get("CONTEXTA_DB_PATH", "/app/data/contexta.db")
    conn = await init_database(db_path)
    await conn.close()
    print(f"[entrypoint] Migrations complete: {db_path}")

asyncio.run(migrate())
PYEOF

# ── Step 3: Start Reflex (frontend + backend on port 8000) ───────────────────
# `reflex run --env prod` serves the pre-built static frontend and starts the
# Reflex/FastAPI backend. The --backend-only flag is NOT used so Reflex manages
# its own static file server + WebSocket state backend as a single process.
#
# Port mapping:
#   8000  → Reflex frontend static server (public)
#   8001  → FastAPI backend (internal; proxied by Reflex from 8000/api/*)
echo "[entrypoint] Starting Reflex application on port 8000..."
exec reflex run --env prod --loglevel warning
