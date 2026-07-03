FROM python:3.11-slim

LABEL maintainer="Project Contexta"
LABEL description="Deterministic solution validation pipeline — single-container deployment"

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        "textual>=0.47.0" \
        "pydantic>=2.5.0" \
        "pydantic-settings>=2.1.0" \
        "aiosqlite>=0.19.0" \
        "litellm>=1.20.0" \
        "mcp>=1.0.0" \
        "fastapi>=0.110.0" \
        "uvicorn>=0.29.0"

# Copy application source
COPY contexta/ ./contexta/

# Persistent SQLite database and export output directories
VOLUME ["/data", "/exports"]

# Required environment variables (must be injected at runtime)
# CONTEXTA_LLM_BACKEND  — e.g. "ollama/mistral" or "openai/gpt-4o"
#
# Optional environment variables with defaults
ENV CONTEXTA_DB_PATH=/data/contexta.db \
    CONTEXTA_EXPORT_PATH=/exports \
    CONTEXTA_LOG_LEVEL=WARNING

# Run as non-root for security
RUN useradd --create-home --shell /bin/bash contexta
USER contexta

ENTRYPOINT ["python", "-m", "contexta"]
