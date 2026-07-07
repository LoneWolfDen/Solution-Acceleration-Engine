FROM python:3.11-slim

LABEL maintainer="Project Contexta"
LABEL description="Solution Acceleration Engine — single-container deployment on port 8000"

WORKDIR /app

# ── System dependencies ───────────────────────────────────────────────────────
# sqlite3   — DB CLI for debugging inside the container
# curl      — required by the bun installer (Reflex frontend toolchain)
# nodejs/npm — JS toolchain fallback; Reflex prefers bun when available
RUN apt-get update && apt-get install -y --no-install-recommends \
        sqlite3 \
        curl \
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
# reflex init       : downloads bun, bootstraps .web/ with dependencies.
# reflex export --frontend-only : compiles a production frontend bundle.
# The resulting static assets are baked into the image; at runtime the Reflex
# backend serves them on the same port (8000) alongside the FastAPI API routes.
RUN python -m reflex init \
    && python -m reflex export --frontend-only --no-zip

# ── Entrypoint ────────────────────────────────────────────────────────────────
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# ── Runtime environment ───────────────────────────────────────────────────────
ENV CONTEXTA_DB_PATH=/app/data/contexta.db \
    CONTEXTA_LOG_LEVEL=WARNING

# ── Exposed port ──────────────────────────────────────────────────────────────
# Single port: Reflex backend serves the UI and API routes on port 8000.
EXPOSE 8000

# TODO(security-milestone): add a non-root runtime user.
# For the current single-user, self-hosted deployment running as root in the
# container is acceptable.  Harden in the dedicated Security milestone.

ENTRYPOINT ["/app/entrypoint.sh"]
