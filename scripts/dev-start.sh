#!/usr/bin/env bash
# dev-start.sh — Start the full Contexta stack in a GitHub Codespace (no Docker).
#
# Starts two background processes:
#   1. uvicorn  — FastAPI REST API on port 8000
#   2. reflex   — Next.js frontend on port 3000  +  state-sync WS on port 8001
#
# Logs are written to /tmp/contexta-api.log and /tmp/contexta-reflex.log.
#
# Usage:
#   bash scripts/dev-start.sh          # start everything
#   bash scripts/dev-start.sh stop     # kill all managed processes

set -uo pipefail

API_PORT=8000
FRONTEND_PORT=3000
REFLEX_BACKEND_PORT=8001

PID_API=/tmp/contexta-api.pid
PID_REFLEX=/tmp/contexta-reflex.pid
LOG_API=/tmp/contexta-api.log
LOG_REFLEX=/tmp/contexta-reflex.log

# ── stop ─────────────────────────────────────────────────────────────────────

stop_services() {
    echo "Stopping Contexta services..."
    for pidfile in "$PID_API" "$PID_REFLEX"; do
        if [[ -f "$pidfile" ]]; then
            pid=$(cat "$pidfile")
            kill "$pid" 2>/dev/null && echo "  killed PID $pid" || true
            rm -f "$pidfile"
        fi
    done
    fuser -k "${API_PORT}/tcp"          2>/dev/null || true
    fuser -k "${FRONTEND_PORT}/tcp"     2>/dev/null || true
    fuser -k "${REFLEX_BACKEND_PORT}/tcp" 2>/dev/null || true
    echo "Done."
}

if [[ "${1:-}" == "stop" ]]; then
    stop_services
    exit 0
fi

# ── clear stale ports ─────────────────────────────────────────────────────────

echo ""
echo "=== Contexta Dev Startup ==="
echo ""
echo "Clearing ports ${API_PORT}, ${FRONTEND_PORT}, ${REFLEX_BACKEND_PORT}..."
fuser -k "${API_PORT}/tcp"          2>/dev/null || true
fuser -k "${FRONTEND_PORT}/tcp"     2>/dev/null || true
fuser -k "${REFLEX_BACKEND_PORT}/tcp" 2>/dev/null || true
sleep 1

# ── data directory ────────────────────────────────────────────────────────────

DB_PATH="${CONTEXTA_DB_PATH:-$(pwd)/data/contexta.db}"
mkdir -p "$(dirname "$DB_PATH")"

# ── start FastAPI ─────────────────────────────────────────────────────────────

echo "Starting FastAPI API on port ${API_PORT}..."
nohup uvicorn contexta.api:app \
    --host 0.0.0.0 \
    --port "${API_PORT}" \
    --reload \
    > "$LOG_API" 2>&1 &
echo $! > "$PID_API"
echo "  PID $(cat "$PID_API") — logs: $LOG_API"

# Wait until the API is ready (up to 20 s)
echo "  Waiting for API..."
for i in $(seq 1 20); do
    if curl -sf "http://localhost:${API_PORT}/api/health" > /dev/null 2>&1; then
        echo "  API ready ✓"
        break
    fi
    if [[ $i -eq 20 ]]; then
        echo "  ERROR: API did not start in 20 s. Check $LOG_API"
        exit 1
    fi
    sleep 1
done

# ── start Reflex ──────────────────────────────────────────────────────────────

echo ""
echo "Starting Reflex frontend on port ${FRONTEND_PORT}..."
nohup python -m reflex run \
    --frontend-port "${FRONTEND_PORT}" \
    --backend-port  "${REFLEX_BACKEND_PORT}" \
    > "$LOG_REFLEX" 2>&1 &
echo $! > "$PID_REFLEX"
echo "  PID $(cat "$PID_REFLEX") — logs: $LOG_REFLEX"

# ── summary ───────────────────────────────────────────────────────────────────

echo ""
echo "=== Services Running ==="
echo "  Frontend  → http://localhost:${FRONTEND_PORT}"
echo "  REST API  → http://localhost:${API_PORT}/api/health"
echo "  API Docs  → http://localhost:${API_PORT}/docs"
echo ""
echo "  Health check:"
echo "    bash scripts/healthcheck.sh"
echo ""
echo "  Tail logs:"
echo "    tail -f $LOG_API"
echo "    tail -f $LOG_REFLEX"
echo ""
echo "  Stop:"
echo "    bash scripts/dev-start.sh stop"
