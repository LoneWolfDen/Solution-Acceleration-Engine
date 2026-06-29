FROM python:3.11-slim

LABEL maintainer="Project Contexta"
LABEL description="Contexta validation pipeline — single-container deployment (Web + API + TUI)"

WORKDIR /app

# ── System dependencies ───────────────────────────────────────────────────────
# sqlite3   — DB CLI for debugging inside the container
# curl      — required by the bun installer (Reflex frontend toolchain)
# supervisor — manages uvicorn (FastAPI) + reflex (UI) as co-equal processes
# nodejs/npm — JS toolchain fallback; Reflex prefers bun when available
RUN apt-get update && apt-get install -y --no-install-recommends \
        sqlite3 \
        curl \
        supervisor \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ───────────────────────────────────────────────────────
# Two-stage COPY: copy pyproject.toml first so Docker can cache the dependency
# layer independently of source changes.  A minimal package stub satisfies
# hatchling's editable-install requirement; the real source is overlaid next.
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && mkdir -p contexta web \
    && printf '"""stub"""' > contexta/__init__.py \
    && pip install --no-cache-dir -e ".[dev]"

# ── Application source ────────────────────────────────────────────────────────
# Overwrite the stubs.  Because the install is editable (-e), Python resolves
# the package from /app/contexta/ immediately — no reinstall needed.
COPY contexta/ ./contexta/
COPY web/      ./web/
COPY rxconfig.py ./

# ── Frontend build (IMAGE BUILD TIME — network required) ─────────────────────
# reflex init   : downloads bun, bootstraps .web/ with Next.js + dependencies.
# reflex export : compiles a production Next.js bundle into .web/.
# The resulting .web/ directory is baked into the image; the container runs
# fully offline at runtime.
RUN python -m reflex init \
    && python -m reflex export --no-zip

# ── Supervisor program definitions ────────────────────────────────────────────
COPY supervisord.conf /etc/supervisor/conf.d/contexta.conf

# ── Volumes ───────────────────────────────────────────────────────────────────
# /data    — persistent SQLite database
# /exports — JSON packet exports produced by the pipeline
VOLUME ["/data", "/exports"]

# ── Runtime environment ───────────────────────────────────────────────────────
# CONTEXTA_LLM_BACKEND must be injected at `docker run` time when using the TUI.
# The Web UI (FastAPI + Reflex) starts without it; LLM backend is only required
# when running the pipeline.
ENV CONTEXTA_DB_PATH=/data/contexta.db \
    CONTEXTA_EXPORT_PATH=/exports \
    CONTEXTA_LOG_LEVEL=WARNING \
    CONTEXTA_API_URL=http://localhost:8000

# ── Exposed ports ─────────────────────────────────────────────────────────────
# 3000  Reflex frontend   — Next.js UI (map this to the host for browser access)
# 8000  FastAPI REST API  — data layer consumed by AppState via httpx
# 8001  Reflex backend    — WebSocket state-sync between AppState and frontend
EXPOSE 3000 8000 8001

# TODO(security-milestone): add a non-root runtime user.
# For the current single-user, self-hosted deployment running as root in the
# container is acceptable.  Harden in the dedicated Security milestone.

# supervisord -n runs in the foreground (required for Docker PID 1 behaviour).
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
