#!/usr/bin/env bash
# entrypoint.sh — Container startup script for Solution Acceleration Engine.
#
# Steps:
#   1. Ensure the data directory for the DB exists (bind-mounted from host).
#   2. Run DB initialisation via scripts/init_db.py — creates every table
#      and applies migrations; fully idempotent on re-runs.
#   3. Start Reflex in production mode — serves the compiled UI and FastAPI
#      API routes on a single port (8000).
#
# Environment variables:
#   CONTEXTA_DB_PATH  — path to the SQLite file (default: /app/data/contexta.db)
#
# No supervisord required: single process, single port.
set -euo pipefail

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Solution Acceleration Engine — Starting...             ║"
echo "╚══════════════════════════════════════════════════════════╝"

# ── Step 1: Ensure data directory ─────────────────────────────────────────────
export CONTEXTA_DB_PATH="${CONTEXTA_DB_PATH:-/app/data/contexta.db}"
DB_DIR="$(dirname "$CONTEXTA_DB_PATH")"
mkdir -p "$DB_DIR"
echo "[entrypoint] Data directory: $DB_DIR"
echo "[entrypoint] Database path:  $CONTEXTA_DB_PATH"

# ── Step 2: Run DB initialisation (idempotent) ────────────────────────────────
echo "[entrypoint] Running database initialisation..."
python scripts/init_db.py

# ── Step 3: Start Reflex (serves UI + API on port 8000) ───────────────────────
echo "[entrypoint] Starting Reflex on port 8000..."
exec python -m reflex run --env prod --backend-only --backend-port 8000
