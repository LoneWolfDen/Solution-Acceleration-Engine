FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock* ./
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev --no-interaction --no-ansi

COPY contexta/ ./contexta/

# Data volume for persistent SQLite DB
VOLUME ["/data"]
# Export volume for JSON packet output
VOLUME ["/exports"]

# Required environment variables (must be supplied at runtime)
# CONTEXTA_LLM_BACKEND  — e.g. "ollama/mistral" or "openai/gpt-4o"

# Optional environment variables with defaults baked in
ENV CONTEXTA_DB_PATH=/data/contexta.db
ENV CONTEXTA_EXPORT_PATH=/exports
ENV CONTEXTA_LOG_LEVEL=WARNING

ENTRYPOINT ["python", "-m", "contexta"]
