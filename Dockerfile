FROM python:3.11-slim

LABEL maintainer="Project Contexta"
LABEL description="Solution Acceleration Engine — single-container Reflex + FastAPI deployment"

WORKDIR /app

# ── System dependencies ────────────────────────────────────────────────────────
# curl: Reflex fetches the Bun/Node front-end toolchain at init time.
# unzip: required by Bun installer.
# sqlite3: for manual DB inspection inside the container.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        unzip \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ────────────────────────────────────────────────────────
# Copy only the manifest first so this layer is cached unless deps change.
COPY pyproject.toml ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        "fastapi>=0.111.0" \
        "uvicorn[standard]>=0.29.0" \
        "httpx>=0.27.0" \
        "pydantic>=2.5.0" \
        "pydantic-settings>=2.1.0" \
        "aiosqlite>=0.19.0" \
        "litellm>=1.20.0" \
        "mcp>=1.0.0" \
        "reflex>=0.5.0"

# ── Application source ─────────────────────────────────────────────────────────
COPY contexta/ ./contexta/
COPY rxconfig.py ./

# Copy the Reflex web app (created by Milestones 2–4).
# The web/ directory must exist before running `reflex export`.
COPY web/ ./web/

# ── Reflex front-end build ─────────────────────────────────────────────────────
# Export the compiled static frontend so the container needs no Node at runtime.
# CONTEXTA_DB_PATH points at a temp path during build to keep the build layer
# self-contained; the real volume is mounted at /app/data/ at runtime.
ENV CONTEXTA_DB_PATH=/tmp/build.db

RUN reflex export --frontend-only --no-zip --loglevel warning \
    || echo "[build] reflex export skipped — web/ not yet scaffolded (pre-M2 build)"

# ── Runtime configuration ──────────────────────────────────────────────────────
# /app/data  — SQLite DB + artifact files (mounted via Docker volume).
# /app/exports — generated export files (optional volume mount).
ENV CONTEXTA_DB_PATH=/app/data/contexta.db \
    CONTEXTA_EXPORT_PATH=/app/exports \
    CONTEXTA_LOG_LEVEL=WARNING \
    OLLAMA_BASE_URL=http://localhost:11434

VOLUME ["/app/data", "/app/exports"]

# Port 8000: Reflex serves the static frontend + proxies the FastAPI backend.
# The FastAPI backend itself listens on 8001 (rxconfig.py backend_port).
# Externally only 8000 is published.
EXPOSE 8000

# ── Entrypoint ────────────────────────────────────────────────────────────────
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Run as non-root for security.
RUN useradd --create-home --shell /bin/bash sae \
    && chown -R sae:sae /app
USER sae

ENTRYPOINT ["./entrypoint.sh"]
