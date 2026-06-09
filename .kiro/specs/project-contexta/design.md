# Design Document — Project Contexta

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Module Boundaries and Layer Map](#2-module-boundaries-and-layer-map)
3. [Docker Container Structure and Environment Configuration](#3-docker-container-structure-and-environment-configuration)
4. [Pydantic Model Definitions and Validation Pipeline](#4-pydantic-model-definitions-and-validation-pipeline)
5. [SQLite Schema and Data Access Layer](#5-sqlite-schema-and-data-access-layer)
6. [LiteLLM Binding and Provider Abstraction](#6-litellm-binding-and-provider-abstraction)
7. [MCP Host Client Architecture](#7-mcp-host-client-architecture)
8. [Async Task Management — 12-Dimension Concurrent Reviews](#8-async-task-management--12-dimension-concurrent-reviews)
9. [Layer 1 — Exploration Implementation](#9-layer-1--exploration-implementation)
10. [Layer 2 — Synthesis Implementation](#10-layer-2--synthesis-implementation)
11. [Textual TUI Component Hierarchy and Layout](#11-textual-tui-component-hierarchy-and-layout)
12. [Admin Tab — Dream Cycle and Prompt Blueprint Management](#12-admin-tab--dream-cycle-and-prompt-blueprint-management)
13. [JSON Export / Import Schema](#13-json-export--import-schema)
14. [Error Handling Strategy](#14-error-handling-strategy)
15. [Correctness Properties](#15-correctness-properties)

---

## 1. Architecture Overview

Project Contexta is structured as a single-process Python 3.11+ application running inside a Docker container. The application is driven by a Textual TUI event loop that orchestrates all user interactions. Background concurrency is provided by Python's built-in `asyncio` event loop, which Textual natively integrates with.

```
┌──────────────────────────────────────────────────────────┐
│                     Docker Container                       │
│                                                            │
│  ┌──────────────────────────────────────────────────┐     │
│  │              Textual TUI (main process)           │     │
│  │                                                    │     │
│  │  ┌─────────────┐    ┌──────────────────────────┐  │     │
│  │  │  MCP Client │    │   Pipeline Orchestrator   │  │     │
│  │  │  (stdio/SSE)│    │  (asyncio task group)     │  │     │
│  │  └──────┬──────┘    └───────────┬──────────────┘  │     │
│  │         │                       │                   │     │
│  │  ┌──────▼──────┐    ┌───────────▼──────────────┐  │     │
│  │  │ Artifact    │    │    LiteLLM Provider       │  │     │
│  │  │ Registry    │    │    Abstraction Layer       │  │     │
│  │  └─────────────┘    └───────────┬──────────────┘  │     │
│  │                                 │                   │     │
│  │  ┌──────────────────────────────▼──────────────┐  │     │
│  │  │           SQLite Data Access Layer            │  │     │
│  │  │   (projects / nodes / blueprints / insights) │  │     │
│  │  └─────────────────────────────────────────────┘  │     │
│  └──────────────────────────────────────────────────┘     │
│                                                            │
│  SQLite DB file: /data/contexta.db                        │
└──────────────────────────────────────────────────────────┘
```

**Key design decisions:**
- **Offline-first**: All LLM routing is through LiteLLM, which at runtime resolves to the configured backend (Ollama, OpenAI, Anthropic, etc.). No network calls are hardcoded.
- **Single asyncio event loop**: Textual provides the event loop; all async workers are registered as Textual `Worker` objects or bare `asyncio.Task` instances scheduled via `asyncio.gather`.
- **Pydantic as the schema contract**: Every external data boundary (LLM output, DB read, JSON import) is guarded by a Pydantic model. No unvalidated dictionaries cross module boundaries.
- **SQLite only**: `aiosqlite` for async access with manual migrations on startup (no ORM, no Alembic).

---

## 2. Module Boundaries and Layer Map

```
contexta/
├── __main__.py               # Entry point: env validation → DB init → TUI launch
├── config.py                 # Environment variable parsing and LLMConfig
├── db/
│   ├── __init__.py
│   ├── schema.py             # DDL strings and migration runner
│   ├── repositories.py       # All SQL read/write functions (no raw SQL outside this file)
│   └── models.py             # Python dataclasses mirroring DB row shapes
├── models/
│   ├── __init__.py
│   ├── enums.py              # ConfidenceEnum, CitationTypeEnum, ReviewDimensionEnum, MitigationRoutingEnum
│   ├── citations.py          # SourceCitation Pydantic model
│   ├── findings.py           # IssueFinding Pydantic model
│   ├── payloads.py           # ReviewNodePayload Pydantic model
│   └── export.py             # JSONPacket Pydantic model (export/import schema)
├── llm/
│   ├── __init__.py
│   ├── provider.py           # LiteLLM wrapper: call_llm(), validate_backend()
│   └── prompts.py            # PromptBuilder: assemble dimension prompts from blueprints
├── mcp/
│   ├── __init__.py
│   ├── client.py             # MCPHostClient: connect_stdio(), connect_sse(), ingest_file()
│   └── artifact_registry.py  # ArtifactRegistry: in-memory store of ingested files
├── pipeline/
│   ├── __init__.py
│   ├── dimension_runner.py   # DimensionTask + TaskOrchestrator (12-way concurrent)
│   ├── arbitrator.py         # ArbitratorEngine: Layer 2 synthesis
│   ├── advisor.py            # ProactiveAdvisor: high-risk tag pattern detection
│   └── scope_policy.py       # ScopePolicyEnforcer: Unalterable Scope Policy logic
├── admin/
│   ├── __init__.py
│   ├── dream_cycle.py        # DreamCycleWorker: background pattern aggregation
│   └── blueprint_manager.py  # PromptBlueprintManager: CRUD + one-active invariant
├── tui/
│   ├── __init__.py
│   ├── app.py                # ContextaApp (Textual App subclass)
│   ├── screens/
│   │   ├── main_screen.py    # MainScreen: header + left pane + right pane + footer
│   │   └── admin_screen.py   # AdminScreen: Dream Cycle + Blueprint management
│   ├── widgets/
│   │   ├── artifact_view.py  # ArtifactView widget (left pane)
│   │   ├── pipeline_view.py  # PipelineView widget (right pane)
│   │   ├── dimension_row.py  # DimensionRow widget (one per ReviewDimension)
│   │   └── modals.py         # All modal dialogs (fork name, scope confirmation, risk blocking)
│   └── messages.py           # Custom Textual Message classes for cross-widget communication
└── export/
    ├── __init__.py
    ├── serializer.py         # JSONPacket serialization
    └── deserializer.py       # JSONPacket validation + DB import
```

**Module boundary rules:**
- `db/repositories.py` is the **only** file that contains raw SQL.
- `models/` packages are **pure Pydantic**; they import nothing from `db/`, `llm/`, or `tui/`.
- `pipeline/` depends on `models/`, `llm/`, and `db/` — but never on `tui/`.
- `tui/` depends on `pipeline/`, `mcp/`, `admin/`, and `export/` — it drives everything but owns no business logic.

---

## 3. Docker Container Structure and Environment Configuration

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock ./
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev

COPY contexta/ ./contexta/

# Data volume for persistent SQLite DB
VOLUME ["/data"]

# Default DB path inside container
ENV CONTEXTA_DB_PATH=/data/contexta.db

ENTRYPOINT ["python", "-m", "contexta"]
```

### Required Environment Variables

| Variable | Description | Example |
|---|---|---|
| `CONTEXTA_LLM_BACKEND` | LiteLLM-compatible backend identifier | `ollama/mistral` |
| `CONTEXTA_DB_PATH` | Path to the SQLite database file | `/data/contexta.db` |
| `CONTEXTA_EXPORT_PATH` | Default directory for JSON packet exports | `/exports` |

### Optional Environment Variables

| Variable | Description | Default |
|---|---|---|
| `CONTEXTA_LLM_API_KEY` | API key if using a hosted backend | `""` |
| `CONTEXTA_LLM_BASE_URL` | Override base URL (for Ollama) | `http://localhost:11434` |
| `CONTEXTA_LOG_LEVEL` | Logging verbosity | `WARNING` |

### `config.py` — Environment Parsing Interface

```python
from pydantic import BaseSettings, validator
from typing import Optional

class ContextaConfig(BaseSettings):
    llm_backend: str                          # CONTEXTA_LLM_BACKEND
    db_path: str = "/data/contexta.db"        # CONTEXTA_DB_PATH
    export_path: str = "/exports"             # CONTEXTA_EXPORT_PATH
    llm_api_key: Optional[str] = None         # CONTEXTA_LLM_API_KEY
    llm_base_url: Optional[str] = None        # CONTEXTA_LLM_BASE_URL
    log_level: str = "WARNING"                # CONTEXTA_LOG_LEVEL

    class Config:
        env_prefix = "CONTEXTA_"

    @validator("llm_backend")
    def validate_backend(cls, v: str) -> str:
        if "/" not in v:
            raise ValueError(
                f"CONTEXTA_LLM_BACKEND must be in 'provider/model' format, got: {v!r}"
            )
        return v

def load_config() -> ContextaConfig:
    """Load and validate configuration from environment. Raises ConfigError on failure."""
    try:
        return ContextaConfig()
    except Exception as exc:
        raise ConfigError(f"Configuration error: {exc}") from exc
```

**Startup sequence in `__main__.py`:**

```python
async def main() -> None:
    try:
        config = load_config()
    except ConfigError as exc:
        # Display error in minimal TUI and halt
        await show_fatal_error(str(exc))
        raise SystemExit(1)

    await init_database(config.db_path)
    app = ContextaApp(config=config)
    await app.run_async()
```

---

## 4. Pydantic Model Definitions and Validation Pipeline

### 4.1 Enums — `models/enums.py`

```python
from enum import Enum

class ConfidenceEnum(str, Enum):
    RED   = "RED"
    AMBER = "AMBER"
    GREEN = "GREEN"

class CitationTypeEnum(str, Enum):
    DIRECT_REFERENCE    = "Direct Reference"
    ADVISED_IN_RELATION = "Advised in Relation"

class ReviewDimensionEnum(str, Enum):
    INTENT        = "Intent"
    SCOPE         = "Scope"
    OWNERSHIP     = "Ownership"
    DELIVERY      = "Delivery"
    TIMELINE      = "Timeline"
    ARCHITECTURE  = "Architecture"
    NFR           = "NFR"
    RESOURCE      = "Resource"
    RISK          = "Risk"
    COMMERCIAL    = "Commercial"
    LANGUAGE      = "Language"
    CONSISTENCY   = "Consistency"

class MitigationRoutingEnum(str, Enum):
    SCOPE_MODIFICATION   = "Scope Modification"
    RISK_REGISTER        = "Risk Register"
    ASSUMPTIONS_MATRIX   = "Assumptions Matrix"
    BOTH_R_AND_A         = "Both R&A"
    IGNORED              = "Ignored"
```

### 4.2 Core Models

**`models/citations.py`**

```python
from pydantic import BaseModel, validator
from .enums import CitationTypeEnum

class SourceCitation(BaseModel):
    file_path:     str
    line_start:    int
    line_end:      int
    citation_type: CitationTypeEnum
    excerpt:       str

    @validator("line_end")
    def end_gte_start(cls, v: int, values: dict) -> int:
        if "line_start" in values and v < values["line_start"]:
            raise ValueError("line_end must be >= line_start")
        return v
```

**`models/findings.py`**

```python
from pydantic import BaseModel
from typing import List
from .enums import ReviewDimensionEnum, ConfidenceEnum, MitigationRoutingEnum
from .citations import SourceCitation

class IssueFinding(BaseModel):
    dimension:          ReviewDimensionEnum
    confidence:         ConfidenceEnum
    summary:            str
    detail:             str
    citations:          List[SourceCitation]
    mitigation_routing: MitigationRoutingEnum
```

**`models/payloads.py`**

```python
from pydantic import BaseModel
from typing import List
from .enums import ReviewDimensionEnum, ConfidenceEnum
from .findings import IssueFinding

class ReviewNodePayload(BaseModel):
    dimension:          ReviewDimensionEnum
    findings:           List[IssueFinding]
    overall_confidence: ConfidenceEnum
    raw_llm_response:   str
```

### 4.3 Validation Pipeline Flow

```
LLM JSON string
      │
      ▼
json.loads()  ──── JSONDecodeError ──► mark task FAILED, log to footer
      │
      ▼
ReviewNodePayload(**data)
      │
      ├─── ValidationError ──────────► mark task FAILED, display errors in Active Pipeline
      │
      ▼
validated ReviewNodePayload
      │
      ▼
db/repositories.write_node(payload)
      │
      ├─── ValidationError (re-check) ► reject write, log to footer, no DB mutation
      │
      ▼
stored safely in nodes table
```

All validation uses `model_validate()` (Pydantic v2) with `strict=False` to allow enum coercion from string values returned by LLMs. Custom validators enforce domain constraints (e.g., `line_end >= line_start`).

---

## 5. SQLite Schema and Data Access Layer

### 5.1 DDL — `db/schema.py`

```python
SCHEMA_VERSION = 1

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        global_tags TEXT NOT NULL DEFAULT '[]'   -- JSON array of tag strings
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nodes (
        id               TEXT PRIMARY KEY,
        project_id       TEXT NOT NULL REFERENCES projects(id),
        parent_id        TEXT REFERENCES nodes(id),
        layer_type       TEXT NOT NULL,           -- 'exploration' | 'synthesis'
        node_name        TEXT NOT NULL,
        metadata_json    TEXT NOT NULL DEFAULT '{}',
        content_markdown TEXT NOT NULL DEFAULT '',
        created_at       TEXT NOT NULL             -- ISO-8601 UTC
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prompt_blueprints (
        id                TEXT PRIMARY KEY,
        blueprint_name    TEXT NOT NULL,
        version_string    TEXT NOT NULL,
        master_prompt_text TEXT NOT NULL,
        is_active         INTEGER NOT NULL DEFAULT 0  -- SQLite boolean: 0/1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS global_client_insights (
        id                     TEXT PRIMARY KEY,
        client_or_industry_tag TEXT NOT NULL,
        observed_pattern       TEXT NOT NULL,
        frequency_count        INTEGER NOT NULL DEFAULT 1,
        last_updated           TEXT NOT NULL,     -- ISO-8601 UTC
        UNIQUE(client_or_industry_tag, observed_pattern)
    )
    """,
]
```

### 5.2 Repository Interface — `db/repositories.py`

All functions are `async` and accept an `aiosqlite.Connection` as their first argument. No raw SQL appears outside this file.

```python
import aiosqlite
from typing import Optional, List
from ..models.payloads import ReviewNodePayload
from .models import NodeRow, ProjectRow, BlueprintRow, InsightRow
import uuid, json
from datetime import datetime, timezone

# ── Projects ────────────────────────────────────────────────────────────────

async def create_project(
    conn: aiosqlite.Connection,
    name: str,
    global_tags: List[str]
) -> ProjectRow: ...

async def get_project(
    conn: aiosqlite.Connection,
    project_id: str
) -> Optional[ProjectRow]: ...

# ── Nodes ───────────────────────────────────────────────────────────────────

async def write_node(
    conn: aiosqlite.Connection,
    project_id:       str,
    parent_id:        Optional[str],
    layer_type:       str,
    node_name:        str,
    payload:          ReviewNodePayload,
    metadata:         dict
) -> NodeRow:
    """Validates payload against ReviewNodePayload schema, then commits.
    Raises ValidationError if the payload fails validation (no DB write occurs)."""
    # Pydantic re-validation guard
    validated = ReviewNodePayload.model_validate(payload.model_dump())
    row_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await conn.execute(
        "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?)",
        (row_id, project_id, parent_id, layer_type, node_name,
         json.dumps(metadata), validated.model_dump_json(), now)
    )
    await conn.commit()
    return NodeRow(id=row_id, ...)

async def get_node(
    conn: aiosqlite.Connection,
    node_id: str
) -> Optional[NodeRow]: ...

async def list_nodes_for_project(
    conn: aiosqlite.Connection,
    project_id: str
) -> List[NodeRow]: ...

async def fork_node(
    conn: aiosqlite.Connection,
    parent_node_id: str,
    new_node_name: str
) -> NodeRow:
    """Creates a new node with parent_id = parent_node_id, inheriting project_id and global_tags."""
    ...

# ── Prompt Blueprints ────────────────────────────────────────────────────────

async def get_active_blueprint(
    conn: aiosqlite.Connection
) -> Optional[BlueprintRow]: ...

async def activate_blueprint(
    conn: aiosqlite.Connection,
    blueprint_id: str
) -> None:
    """Sets is_active=1 for the given blueprint, is_active=0 for all others.
    Executes both updates in a single transaction to preserve the one-active invariant."""
    async with conn.execute("BEGIN"):
        await conn.execute("UPDATE prompt_blueprints SET is_active = 0")
        await conn.execute(
            "UPDATE prompt_blueprints SET is_active = 1 WHERE id = ?",
            (blueprint_id,)
        )
    await conn.commit()

async def save_blueprint_version(
    conn: aiosqlite.Connection,
    name: str,
    version: str,
    prompt_text: str
) -> BlueprintRow:
    """Always inserts as new row. Never modifies existing rows."""
    ...

# ── Global Client Insights ───────────────────────────────────────────────────

async def upsert_insight(
    conn: aiosqlite.Connection,
    client_tag: str,
    pattern: str
) -> InsightRow:
    """Increments frequency_count if (client_tag, pattern) exists; inserts otherwise."""
    await conn.execute(
        """
        INSERT INTO global_client_insights (id, client_or_industry_tag, observed_pattern,
            frequency_count, last_updated)
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(client_or_industry_tag, observed_pattern)
        DO UPDATE SET
            frequency_count = frequency_count + 1,
            last_updated    = excluded.last_updated
        """,
        (str(uuid.uuid4()), client_tag, pattern, datetime.now(timezone.utc).isoformat())
    )
    await conn.commit()
    ...

async def get_insights_for_tags(
    conn: aiosqlite.Connection,
    tags: List[str]
) -> List[InsightRow]: ...
```

### 5.3 Connection Management

A single `aiosqlite.Connection` is opened at application start and passed through the application via a `DatabaseContext` dataclass held on the Textual `App` instance. Foreign keys are enabled on connection:

```python
async def init_database(db_path: str) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA foreign_keys = ON")
    await run_migrations(conn)
    return conn
```

---

## 6. LiteLLM Binding and Provider Abstraction

### 6.1 Provider Interface — `llm/provider.py`

```python
import litellm
from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class LLMConfig:
    model:    str                  # e.g. "ollama/mistral"
    api_key:  Optional[str] = None
    base_url: Optional[str] = None

@dataclass
class LLMResponse:
    content:         str
    raw_response:    Any
    finish_reason:   str

async def call_llm(
    config:  LLMConfig,
    system:  str,
    user:    str,
    max_tokens: int = 4096
) -> LLMResponse:
    """
    Makes a single LiteLLM completion call with:
      - temperature = 0.0 (Temperature-Zero Mode)
      - response_format = {"type": "json_object"}  (JSON-mode)
    Raises LLMCallError on network failure or non-200 response.
    """
    response = await litellm.acompletion(
        model=config.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
        api_key=config.api_key,
        base_url=config.base_url,
    )
    return LLMResponse(
        content=response.choices[0].message.content,
        raw_response=response,
        finish_reason=response.choices[0].finish_reason,
    )

def validate_backend(backend: str) -> bool:
    """Returns True if LiteLLM recognises the backend string."""
    try:
        litellm.get_llm_provider(backend)
        return True
    except Exception:
        return False
```

### 6.2 Prompt Assembly — `llm/prompts.py`

```python
from ..models.enums import ReviewDimensionEnum
from ..db.models import BlueprintRow

DIMENSION_SYSTEM_TEMPLATE = """\
You are a solution review AI operating as the {dimension} reviewer.
{master_prompt_text}

CRITICAL OUTPUT INSTRUCTIONS:
- You MUST respond with a single, raw JSON object.
- Do NOT wrap your response in markdown code fences (no ```json or ``` blocks).
- Do NOT include any explanatory text, preamble, or commentary before or after the JSON.
- Do NOT use any formatting other than the JSON structure itself.
- Your entire response must be valid, parseable JSON starting with {{ and ending with }}.
- The JSON object MUST conform exactly to this schema:
{schema_json}
"""

class PromptBuilder:
    def __init__(self, blueprint: BlueprintRow, schema_json: str):
        self._blueprint = blueprint
        self._schema_json = schema_json

    def build_dimension_prompt(
        self,
        dimension: ReviewDimensionEnum,
        artifact_context: str
    ) -> tuple[str, str]:
        """Returns (system_prompt, user_prompt) pair."""
        system = DIMENSION_SYSTEM_TEMPLATE.format(
            dimension=dimension.value,
            master_prompt_text=self._blueprint.master_prompt_text,
            schema_json=self._schema_json,
        )
        user = f"PROPOSAL ARTIFACTS:\n\n{artifact_context}"
        return system, user

    def build_arbitrator_prompt(
        self,
        payloads: list[str]   # list of ReviewNodePayload.model_dump_json()
    ) -> tuple[str, str]:
        """Returns (system_prompt, user_prompt) for the Layer 2 Arbitrator."""
        system = (
            "You are the Arbitrator Persona. Analyse the 12 dimension review outputs "
            "and identify all contradictions.\n\n"
            "CRITICAL OUTPUT INSTRUCTIONS:\n"
            "- Respond with a single, raw JSON object only.\n"
            "- Do NOT use markdown code fences, preamble, or commentary.\n"
            "- Your entire response must be valid JSON starting with { and ending with }.\n"
            "- The JSON object must have a single key 'contradictions' containing a list "
            "of objects, each with keys: 'dimension_a', 'dimension_b', 'description'."
        )
        user = "\n\n".join(f"--- {i+1} ---\n{p}" for i, p in enumerate(payloads))
        return system, user
```

> **Ollama JSON stability:** Local Ollama deployments do not universally honour `response_format={"type": "json_object"}` across all model families. The explicit CRITICAL OUTPUT INSTRUCTIONS block in the system prompt provides a defence-in-depth safeguard, ensuring the model receives unambiguous natural-language directives to return unwrapped JSON. This is additive to — not a replacement for — the `json_object` response_format flag.

---

## 7. MCP Host Client Architecture

### 7.1 Client Interface — `mcp/client.py`

The MCP Host Client uses the official `mcp` Python SDK. It maintains a single active transport at a time and delegates resource reads to the `ArtifactRegistry`.

```python
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Optional

@dataclass
class IngestedArtifact:
    uri:        str
    file_path:  str
    content:    str
    line_count: int

class MCPHostClient:
    def __init__(self, registry: "ArtifactRegistry"):
        self._registry = registry
        self._session: Optional[ClientSession] = None

    @asynccontextmanager
    async def connect_stdio(self, command: str, args: list[str]) -> AsyncIterator[None]:
        """Connect via stdio transport. Yields when session is ready."""
        async with stdio_client(command, args) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._session = session
                try:
                    yield
                finally:
                    self._session = None

    @asynccontextmanager
    async def connect_sse(self, url: str) -> AsyncIterator[None]:
        """Connect via SSE transport. Yields when session is ready."""
        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._session = session
                try:
                    yield
                finally:
                    self._session = None

    async def ingest_file(self, uri: str) -> IngestedArtifact:
        """
        Reads a resource from the connected MCP server by URI.
        Registers the result in the ArtifactRegistry.
        Raises MCPIngestError if the session is not connected or the resource read fails.
        """
        if self._session is None:
            raise MCPIngestError("No active MCP transport connection")
        result = await self._session.read_resource(uri)
        content = result.contents[0].text
        lines = content.splitlines()
        artifact = IngestedArtifact(
            uri=uri,
            file_path=uri.split("://", 1)[-1],
            content=content,
            line_count=len(lines),
        )
        self._registry.register(artifact)
        return artifact

    async def list_resources(self) -> list[dict]:
        """Lists available resources from the connected MCP server."""
        if self._session is None:
            raise MCPIngestError("No active MCP transport connection")
        result = await self._session.list_resources()
        return [r.model_dump() for r in result.resources]
```

### 7.2 Artifact Registry — `mcp/artifact_registry.py`

```python
from dataclasses import dataclass, field
from typing import Dict, Optional

class ArtifactRegistry:
    """In-memory store of ingested MCP artifacts, keyed by file_path."""

    def __init__(self):
        self._artifacts: Dict[str, IngestedArtifact] = {}

    def register(self, artifact: IngestedArtifact) -> None:
        self._artifacts[artifact.file_path] = artifact

    def get(self, file_path: str) -> Optional[IngestedArtifact]:
        return self._artifacts.get(file_path)

    def all(self) -> list[IngestedArtifact]:
        return list(self._artifacts.values())

    def build_context_string(self) -> str:
        """Concatenates all artifact contents into a single prompt context block."""
        parts = []
        for artifact in self._artifacts.values():
            parts.append(f"FILE: {artifact.file_path} ({artifact.line_count} lines)\n")
            parts.append(artifact.content)
            parts.append("\n---\n")
        return "\n".join(parts)
```

---

## 8. Async Task Management — 12-Dimension Concurrent Reviews

### 8.1 Task State Machine

Each dimension review is a state machine with the following states:

```
PENDING → RUNNING → COMPLETE
                 ↘ FAILED  (user can trigger PENDING again for retry)
```

### 8.2 `DimensionTask` — `pipeline/dimension_runner.py`

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import asyncio
from ..models.enums import ReviewDimensionEnum
from ..models.payloads import ReviewNodePayload

class TaskState(str, Enum):
    PENDING  = "PENDING"
    RUNNING  = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED   = "FAILED"

@dataclass
class DimensionTask:
    dimension:     ReviewDimensionEnum
    state:         TaskState = TaskState.PENDING
    payload:       Optional[ReviewNodePayload] = None
    error_message: Optional[str] = None
    _task:         Optional[asyncio.Task] = field(default=None, repr=False)
```

### 8.3 `TaskOrchestrator` — Concurrency Model

```python
import asyncio
from typing import Callable, Awaitable
from ..models.enums import ReviewDimensionEnum

class TaskOrchestrator:
    """
    Manages exactly 12 DimensionTask instances, one per ReviewDimensionEnum value.
    Notifies the TUI via a callback whenever a task changes state.
    """

    def __init__(
        self,
        on_state_change: Callable[[DimensionTask], Awaitable[None]],
        runner_fn:       Callable[[ReviewDimensionEnum], Awaitable[ReviewNodePayload]]
    ):
        self._tasks: dict[ReviewDimensionEnum, DimensionTask] = {
            dim: DimensionTask(dimension=dim)
            for dim in ReviewDimensionEnum
        }
        self._on_state_change = on_state_change
        self._runner_fn = runner_fn

    async def launch_all(self) -> None:
        """Launches all 12 dimension tasks concurrently using asyncio.gather."""
        await asyncio.gather(*[
            self._run_single(dim) for dim in ReviewDimensionEnum
        ], return_exceptions=True)

    async def retry_dimension(self, dimension: ReviewDimensionEnum) -> None:
        """Resets a FAILED task to PENDING and re-launches it independently."""
        task = self._tasks[dimension]
        if task.state != TaskState.FAILED:
            raise ValueError(f"Cannot retry dimension {dimension} in state {task.state}")
        task.state = TaskState.PENDING
        task.error_message = None
        await self._run_single(dimension)

    async def _run_single(self, dimension: ReviewDimensionEnum) -> None:
        task = self._tasks[dimension]
        task.state = TaskState.RUNNING
        await self._on_state_change(task)
        try:
            payload = await self._runner_fn(dimension)
            task.payload = payload
            task.state = TaskState.COMPLETE
        except Exception as exc:
            task.error_message = str(exc)
            task.state = TaskState.FAILED
        await self._on_state_change(task)

    def all_complete(self) -> bool:
        return all(t.state == TaskState.COMPLETE for t in self._tasks.values())

    def incomplete_dimensions(self) -> list[ReviewDimensionEnum]:
        return [
            dim for dim, t in self._tasks.items()
            if t.state != TaskState.COMPLETE
        ]

    def get_all_payloads(self) -> list[ReviewNodePayload]:
        """Returns payloads for all COMPLETE tasks. Raises if any are not COMPLETE."""
        payloads = []
        for t in self._tasks.values():
            if t.state != TaskState.COMPLETE or t.payload is None:
                raise RuntimeError(f"Dimension {t.dimension} is not complete")
            payloads.append(t.payload)
        return payloads
```

---

## 9. Layer 1 — Exploration Implementation

### 9.1 Dimension Runner Function

The `runner_fn` passed to `TaskOrchestrator` is constructed in the pipeline coordinator and closes over the `LLMConfig`, `PromptBuilder`, and `ArtifactRegistry`:

```python
async def make_dimension_runner(
    config:    LLMConfig,
    builder:   PromptBuilder,
    registry:  ArtifactRegistry,
) -> Callable[[ReviewDimensionEnum], Awaitable[ReviewNodePayload]]:
    """
    Returns a runner_fn that performs LLM call + Pydantic validation only.
    Does NOT write to the database. The validated payload is stored in
    DimensionTask.payload (in-memory). The database write occurs only once,
    after all 12 tasks have reached COMPLETE state, via a single
    commit_exploration_node() call from the TaskOrchestrator.
    """
    artifact_context = registry.build_context_string()

    async def run_dimension(dimension: ReviewDimensionEnum) -> ReviewNodePayload:
        system, user = builder.build_dimension_prompt(dimension, artifact_context)

        # LLM call (Temperature-Zero Mode enforced inside call_llm)
        llm_response = await call_llm(config, system, user)

        # Pydantic validation gate — raises DimensionValidationError on failure
        try:
            payload = ReviewNodePayload.model_validate_json(llm_response.content)
        except ValidationError as exc:
            raise DimensionValidationError(
                f"Validation failed for {dimension.value}: {exc}"
            ) from exc

        # Return validated payload to DimensionTask.payload (in-memory only)
        return payload

    return run_dimension
```

### 9.2 Batch Commit on Layer 1 Completion

After `TaskOrchestrator.launch_all()` returns, the orchestrator checks `all_complete()`.
If true, it calls `commit_exploration_node()`:

```python
async def commit_exploration_node(
    orchestrator: TaskOrchestrator,
    conn:         aiosqlite.Connection,
    project_id:   str,
    node_id:      str,
) -> NodeRow:
    """
    Collects all 12 validated ReviewNodePayload objects from in-memory DimensionTask state.
    Performs a single write_node() call to persist the complete exploration node.
    This ensures the nodes table never contains a partial Layer 1 record.

    Raises RuntimeError if any dimension is not in COMPLETE state.
    Raises ValidationError if any payload fails the DB-level re-validation guard.
    """
    payloads = orchestrator.get_all_payloads()  # raises if any not COMPLETE
    combined_metadata = {
        "dimensions": [p.model_dump() for p in payloads],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    return await write_node(
        conn,
        project_id=project_id,
        parent_id=node_id,
        layer_type="exploration",
        node_name="Layer 1 — Full Exploration",
        payload=payloads[0],          # representative payload for schema guard
        metadata=combined_metadata,
    )
```

**Design rationale:** Writing all 12 payloads in a single commit prevents the `nodes` table from ever containing a partial Layer 1 record (e.g., 7 of 12 dimensions committed before a crash). The in-memory `DimensionTask.payload` collection acts as the intermediate accumulator. If any dimension fails validation, `task.state = FAILED` and the user can retry that dimension independently before the commit is attempted.

### 9.3 Layer 1 Initiation Sequence

```
User triggers Layer 1
       │
       ▼
Check: active Prompt Blueprint exists?
  No  ──► Blocking error modal "No active Prompt Blueprint"
  Yes ──┐
        ▼
Check: at least one artifact ingested?
  No  ──► Blocking error modal "No source files ingested"
  Yes ──┐
        ▼
TaskOrchestrator.launch_all()
  → 12 asyncio coroutines running concurrently
  → Each coroutine:
       1. LLM call (temperature=0.0, json_object)
       2. ReviewNodePayload.model_validate_json()
       3. Store validated payload in DimensionTask.payload (in-memory only)
       4. Emit state_change callback → TUI updates DimensionRow widget
       │
       ▼
→ TaskOrchestrator.launch_all()  [all 12 complete]
       │
       ▼
all_complete() == True?
  Yes ──► commit_exploration_node() → single write_node() to SQLite
  No  ──► At least one dimension FAILED — user retries before commit
```

---

## 10. Layer 2 — Synthesis Implementation

### 10.1 Arbitrator Engine — `pipeline/arbitrator.py`

```python
from ..models.payloads import ReviewNodePayload
from ..llm.provider import call_llm, LLMConfig
from ..llm.prompts import PromptBuilder

@dataclass
class ArbitratorResult:
    contradictions:  list[dict]   # [{"dimension_a": ..., "dimension_b": ..., "description": ...}]
    raw_llm_response: str

class ArbitratorEngine:
    def __init__(self, config: LLMConfig, builder: PromptBuilder):
        self._config  = config
        self._builder = builder

    async def run(self, payloads: list[ReviewNodePayload]) -> ArbitratorResult:
        """
        Receives exactly 12 ReviewNodePayload objects.
        Returns ArbitratorResult with detected contradictions.
        Raises ArbitratorError if the LLM response fails validation.
        """
        if len(payloads) != 12:
            raise ArbitratorError(
                f"Arbitrator requires exactly 12 payloads, got {len(payloads)}"
            )
        serialised = [p.model_dump_json() for p in payloads]
        system, user = self._builder.build_arbitrator_prompt(serialised)
        response = await call_llm(self._config, system, user)

        try:
            data = json.loads(response.content)
            contradictions = data.get("contradictions", [])
        except (json.JSONDecodeError, KeyError) as exc:
            raise ArbitratorError(f"Arbitrator response parsing failed: {exc}") from exc

        return ArbitratorResult(
            contradictions=contradictions,
            raw_llm_response=response.content
        )
```

### 10.2 Proactive Advisor — `pipeline/advisor.py`

```python
from ..db.repositories import get_insights_for_tags
from ..db.models import InsightRow

@dataclass
class AdvisoryAlert:
    tag_combination: list[str]
    pattern:         str
    frequency_count: int

class ProactiveAdvisor:
    async def evaluate(
        self,
        global_tags: list[str],
        conn: aiosqlite.Connection
    ) -> list[AdvisoryAlert]:
        """
        Queries global_client_insights for any (client_tag, pattern) rows
        where client_tag appears in global_tags.
        Returns a list of AdvisoryAlert objects for all matches.
        """
        insights = await get_insights_for_tags(conn, global_tags)
        alerts = []
        for insight in insights:
            if insight.client_or_industry_tag in global_tags:
                alerts.append(AdvisoryAlert(
                    tag_combination=[insight.client_or_industry_tag],
                    pattern=insight.observed_pattern,
                    frequency_count=insight.frequency_count,
                ))
        return alerts
```

### 10.3 Layer 2 Initiation Sequence

```
User presses [C] Compare
       │
       ▼
orchestrator.all_complete()?
  No  ──► Blocking modal listing orchestrator.incomplete_dimensions()
  Yes ──┐
        ▼
ProactiveAdvisor.evaluate(project.global_tags)
  Any alerts? ──► Blocking modal (AdvisoryAlert details)
                  User must acknowledge (ACK recorded in metadata_json)
  No alerts / ACK received ──┐
                              ▼
ArbitratorEngine.run(orchestrator.get_all_payloads())
       │
       ▼
Store synthesis node (layer_type='synthesis', parent_id=current_node.id)
       │
       ▼
Display reconciliation summary in Active Pipeline pane
```

### 10.4 Scope Policy Enforcer — `pipeline/scope_policy.py`

```python
class ScopePolicyEnforcer:
    """
    Detects IssueFinding objects with mitigation_routing = SCOPE_MODIFICATION
    and manages routing decisions, recording them in node metadata_json.
    """

    def get_scope_findings(
        self,
        payloads: list[ReviewNodePayload]
    ) -> list[IssueFinding]:
        """Returns all findings across all payloads with Scope Modification routing."""
        findings = []
        for p in payloads:
            for f in p.findings:
                if f.mitigation_routing == MitigationRoutingEnum.SCOPE_MODIFICATION:
                    findings.append(f)
        return findings

    def apply_routing_decision(
        self,
        finding: IssueFinding,
        decision: MitigationRoutingEnum,
        metadata: dict
    ) -> dict:
        """
        Records the routing decision in metadata_json under key 'routing_decisions'.
        Returns updated metadata dict.
        """
        decisions = metadata.get("routing_decisions", [])
        decisions.append({
            "dimension":   finding.dimension.value,
            "summary":     finding.summary,
            "new_routing": decision.value,
        })
        metadata["routing_decisions"] = decisions
        return metadata
```

---

## 11. Textual TUI Component Hierarchy and Layout

### 11.1 Component Tree

```
ContextaApp (App)
└── MainScreen (Screen)
    ├── ContextaHeader (Header)           # project name + node name + admin access
    ├── Horizontal (layout container)
    │   ├── ArtifactView (Widget)         # left pane — MCP file browser + citation jump handler
    │   │   ├── ListView                  # file list
    │   │   └── TextLog                  # file preview (scrollable)
    │   └── PipelineView (Widget)         # right pane — pipeline state
    │       ├── MetadataCluster (Widget)  # project tags, node info
    │       ├── DimensionRow × 12        # one per ReviewDimension
    │       │   ├── Label (dimension name)
    │       │   ├── Label (status badge: PENDING/RUNNING/COMPLETE/FAILED)
    │       │   ├── ProgressBar           # visible when RUNNING
    │       │   └── Button (Retry)        # visible when FAILED
    │       └── ReconciliationPanel       # arbitrator output (visible post-Layer 2)
    └── ContextaFooter (Footer)           # [F] [C] [P] [E] keys

AdminScreen (Screen)
├── ContextaHeader
├── DreamCyclePanel (Widget)
│   ├── Button (Trigger Dream Cycle)
│   └── Label (status indicator)
├── BlueprintPanel (Widget)
│   ├── DataTable (blueprint list)
│   ├── Button (Activate)
│   └── Button (New Version)
└── ContextaFooter
```

### 11.2 Layout Specification

```
┌─────────────────────────────────────────────────────────────────┐
│  HEADER: [Project: {name}]  [Node: {name}]  [⚙ Admin]           │
├──────────────────────┬──────────────────────────────────────────┤
│  MCP Artifact View   │  Active Pipeline                          │
│  (left pane, 30%)    │  (right pane, 70%)                        │
│                      │                                            │
│  ► file_a.md  (120L) │  📦 Metadata Cluster                      │
│    file_b.docx (45L) │    Tags: #Lean-Client-Team                │
│    file_c.pdf  (89L) │    Node: Draft v1                         │
│                      │                                            │
│  [preview panel]     │  ┌─────────────────────────────────────┐  │
│  ...file content...  │  │ Intent     [●●●●●●●●●●] COMPLETE    │  │
│                      │  │ Scope      [●●●●●●●●──] RUNNING     │  │
│                      │  │ Ownership  [──────────] PENDING     │  │
│                      │  │ ...                                  │  │
│                      │  └─────────────────────────────────────┘  │
│                      │                                            │
│                      │  [Reconciliation Panel — post Layer 2]     │
├──────────────────────┴──────────────────────────────────────────┤
│  FOOTER: [F] Fork  [C] Compare  [P] Run Proposal  [E] Export     │
└─────────────────────────────────────────────────────────────────┘
```

**ArtifactView** handles `CitationJumpRequested` messages — on receipt, scrolls the file preview to `line_start` and applies a highlight style to lines `[line_start, line_end]`. Highlight clears when a different finding is selected or user navigates away.

### 11.3 Custom Textual Messages — `tui/messages.py`

```python
from textual.message import Message
from ..models.enums import ReviewDimensionEnum
from ..pipeline.dimension_runner import TaskState

class DimensionStateChanged(Message):
    """Posted by TaskOrchestrator when a dimension task changes state."""
    def __init__(self, dimension: ReviewDimensionEnum, state: TaskState, error: str | None = None):
        super().__init__()
        self.dimension = dimension
        self.state     = state
        self.error     = error

class ArtifactIngested(Message):
    """Posted by MCPHostClient when a new file is successfully ingested."""
    def __init__(self, artifact: "IngestedArtifact"):
        super().__init__()
        self.artifact = artifact

class AdvisoryAlertDetected(Message):
    """Posted by ProactiveAdvisor when a high-risk pattern is detected."""
    def __init__(self, alerts: list):
        super().__init__()
        self.alerts = alerts

class CitationJumpRequested(Message):
    """Posted by PipelineView when an IssueFinding is highlighted/selected.
    Carries the file_path, line_start, and line_end from the finding's first SourceCitation.
    ArtifactView handles this message to scroll and highlight the target line range."""
    def __init__(self, file_path: str, line_start: int, line_end: int):
        super().__init__()
        self.file_path  = file_path
        self.line_start = line_start
        self.line_end   = line_end
```

### 11.4 Modal Dialogs — `tui/widgets/modals.py`

| Modal | Trigger | Required Input |
|---|---|---|
| `ForkNameModal` | `[F]` key | Node name string |
| `ScopeConfirmModal` | `[Change Scope]` button | Explicit acknowledge checkbox |
| `RiskBlockingModal` | ProactiveAdvisor alert | Explicit acknowledge button |
| `CompareBlockingModal` | `[C]` key with incomplete dimensions | Dismiss only (lists incomplete dims) |
| `ExportConfirmModal` | `[E]` key | File path (pre-filled with default) |
| `BlueprintErrorModal` | No active blueprint at review start | Dismiss only |

---

## 12. Admin Tab — Dream Cycle and Prompt Blueprint Management

### 12.1 Dream Cycle Worker — `admin/dream_cycle.py`

The Dream Cycle runs as a Textual `Worker` (using `@work(exclusive=True, thread=False)`) to avoid blocking the event loop while still providing cancellation support.

```python
import asyncio
from ..db.repositories import list_all_nodes, upsert_insight
from ..db.models import NodeRow
from ..models.payloads import ReviewNodePayload

class DreamCycleWorker:
    """
    Analyses the global nodes table to identify recurring failure patterns.
    Uses SQLite's json_each() JSON table-valued function to extract RED-confidence
    findings directly within the SQL query, eliminating full object deserialization
    in the Python runtime for nodes that have no RED findings.
    """

    async def run(self, conn: aiosqlite.Connection) -> int:
        """
        Returns the number of insight rows created or updated.

        SQL strategy:
        - Uses json_each(n.metadata_json, '$.dimensions') to iterate the dimensions
          array stored in metadata_json without loading the full JSON blob into Python.
        - Filters for overall_confidence = 'RED' inside the SQL WHERE clause.
        - Joins to projects to retrieve global_tags for the upsert key.
        - Python loop only processes the filtered (tag, pattern) pairs — not raw node blobs.
        """
        EXTRACT_RED_FINDINGS_SQL = """
            SELECT
                p.global_tags                                        AS global_tags,
                json_extract(dim.value, '$.dimension')               AS dimension_name
            FROM nodes n
            JOIN projects p ON p.id = n.project_id
            JOIN json_each(n.metadata_json, '$.dimensions') AS dim
            WHERE n.layer_type = 'exploration'
              AND json_extract(dim.value, '$.overall_confidence') = 'RED'
        """
        updated = 0
        async with conn.execute(EXTRACT_RED_FINDINGS_SQL) as cursor:
            async for row in cursor:
                try:
                    tags = json.loads(row[0]) if row[0] else []
                    dimension_name = row[1] or "UNKNOWN"
                    pattern = f"HIGH_RISK_{dimension_name.upper()}"
                    for tag in tags:
                        await upsert_insight(conn, tag, pattern)
                        updated += 1
                except Exception:
                    # Log per-row error but do NOT abort; continue processing
                    continue
        return updated
```

> **json_each() optimization:** The previous implementation loaded and deserialized every exploration node's full `metadata_json` blob into Python memory before filtering for RED confidence. For large projects with hundreds of nodes, this was O(N) full-blob deserialization. The `json_each(n.metadata_json, '$.dimensions')` table-valued function pushes the filtering predicate into the SQLite execution engine, which reads only the relevant JSON paths. Python only receives the `(global_tags, dimension_name)` tuples for rows that actually matched the RED confidence filter — significantly reducing memory pressure during Dream Cycle runs.

### 12.2 Blueprint Manager — `admin/blueprint_manager.py`

```python
class PromptBlueprintManager:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    async def list_all(self) -> list[BlueprintRow]:
        return await list_blueprints(self._conn)

    async def activate(self, blueprint_id: str) -> None:
        """
        Atomically sets is_active=1 for blueprint_id, is_active=0 for all others.
        Preserves the one-active invariant at the DB transaction level.
        """
        await activate_blueprint(self._conn, blueprint_id)

    async def save_new_version(
        self,
        name: str,
        version: str,
        prompt_text: str
    ) -> BlueprintRow:
        """Always creates a new row; never modifies existing rows."""
        return await save_blueprint_version(self._conn, name, version, prompt_text)

    async def get_active(self) -> Optional[BlueprintRow]:
        return await get_active_blueprint(self._conn)
```

---

## 13. JSON Export / Import Schema

### 13.1 Export Schema — `models/export.py`

```python
from pydantic import BaseModel
from typing import Optional, List
from .payloads import ReviewNodePayload

EXPORT_SCHEMA_VERSION = "1.0"

class ExportArbitratorResult(BaseModel):
    contradictions:   list[dict]
    raw_llm_response: str

class JSONPacket(BaseModel):
    schema_version:       str = EXPORT_SCHEMA_VERSION
    export_timestamp:     str                           # ISO-8601 UTC
    project_name:         str
    project_global_tags:  List[str]
    node_id:              str
    node_name:            str
    parent_node_id:       Optional[str]
    layer_type:           str
    dimension_payloads:   List[ReviewNodePayload]       # exactly 12 for exploration nodes
    arbitrator_result:    Optional[ExportArbitratorResult]
    routing_decisions:    List[dict]                    # from metadata_json.routing_decisions
    metadata:             dict
    created_at:           str                           # ISO-8601 UTC
```

### 13.2 Serializer — `export/serializer.py`

```python
import json
from pathlib import Path
from ..models.export import JSONPacket

class JSONPacketSerializer:
    async def export(self, packet: JSONPacket, output_path: Path) -> None:
        """
        Writes packet to output_path as pretty-printed JSON.
        Uses a temp file in the same parent directory + shutil.move() for atomic,
        cross-device-safe rename. shutil.move() falls back to copy+delete when
        os.rename() would fail across Docker volume mount boundaries (EXDEV error).
        Raises ExportError if any filesystem error occurs.
        """
        tmp_path = output_path.with_suffix(".tmp")
        try:
            tmp_path.write_text(
                packet.model_dump_json(indent=2),
                encoding="utf-8"
            )
            shutil.move(str(tmp_path), str(output_path))
        except OSError as exc:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise ExportError(f"Export failed: {exc}") from exc
```

> **Cross-device safety:** `Path.rename()` maps to `os.rename()`, which raises `EXDEV` (cross-device link error) when the source and destination are on different filesystem mount points — a common scenario with Docker volume-mounted `/exports` directories. `shutil.move()` detects this condition and transparently falls back to a copy-then-delete sequence, preserving atomicity guarantees without requiring the source and destination to share the same mount point.

**Atomic rename** ensures no partial file is left on disk if the write fails, satisfying Requirement 11.5.

### 13.3 Deserializer — `export/deserializer.py`

```python
class JSONPacketDeserializer:
    async def import_packet(
        self,
        file_path: Path,
        conn: aiosqlite.Connection
    ) -> NodeRow:
        """
        1. Reads JSON file
        2. Validates against JSONPacket schema (raises ImportValidationError on failure — NO DB write)
        3. Creates project if not exists
        4. Writes node + all dimension payloads to DB
        5. Returns the created NodeRow
        """
        try:
            raw = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ImportError(f"Cannot read file: {exc}") from exc

        try:
            packet = JSONPacket.model_validate_json(raw)
        except ValidationError as exc:
            raise ImportValidationError(
                f"JSON Packet failed schema validation: {exc}"
            ) from exc

        # All validation passed — now write to DB (all-or-nothing transaction)
        return await _write_imported_packet(conn, packet)
```

---

## 14. Error Handling Strategy

### Error Categories

| Category | Handler | User-facing Action |
|---|---|---|
| `ConfigError` | `__main__.py` startup | Fatal error overlay, halt |
| `LLMCallError` | `dimension_runner.py` | Mark dimension FAILED, show error in DimensionRow |
| `DimensionValidationError` | `dimension_runner.py` | Mark dimension FAILED, show ValidationError detail in Active Pipeline |
| `ArbitratorError` | `arbitrator.py` | Display error in Active Pipeline footer area |
| `MCPIngestError` | `mcp/client.py` | Error notification in TUI footer bar |
| `ExportError` | `export/serializer.py` | Error message in TUI footer bar, no partial file |
| `ImportValidationError` | `export/deserializer.py` | Validation errors displayed in TUI, no DB write |
| `DreamCycleError` | `admin/dream_cycle.py` | Logged in Admin Tab panel, worker terminates cleanly |
| Pydantic `ValidationError` on DB write | `db/repositories.py` | Reject write, log to footer, DB unchanged |

### Footer Bar Error Pattern

All non-fatal errors surface in the TUI footer bar using a `notify()` call on the Textual `App` instance, which renders a timed notification bar. Critical errors requiring acknowledgement use modal dialogs instead.

---

## 15. Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

---

### Property 1: LiteLLM Backend String Acceptance

*For any* string in the format `"provider/model"`, the `ContextaConfig` validator should accept it without raising a `ConfigError`. *For any* string that does not contain a `/` separator, the validator should raise a `ConfigError` with a descriptive message.

**Validates: Requirements 1.4, 1.5**

---

### Property 2: Missing Environment Variable Rejection

*For any* non-empty subset of required environment variables that are absent from the environment, calling `load_config()` should raise a `ConfigError` whose message identifies at least one of the missing variables.

**Validates: Requirements 1.5**

---

### Property 3: Pydantic Enum Round-Trip Serialization

*For any* value in `ConfidenceEnum`, `CitationTypeEnum`, `ReviewDimensionEnum`, or `MitigationRoutingEnum`, serializing the value to a string and constructing the enum from that string should return the original value unchanged.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

---

### Property 4: ReviewNodePayload Round-Trip Serialization

*For any* valid `ReviewNodePayload` object (with arbitrary lists of `IssueFinding` and `SourceCitation` objects), calling `model_dump_json()` and then `model_validate_json()` should produce an object equal to the original.

**Validates: Requirements 3.5, 3.6, 3.7, 3.8**

---

### Property 5: LLM Response Validation Gate

*For any* JSON string that is a valid serialization of `ReviewNodePayload`, `ReviewNodePayload.model_validate_json()` should succeed. *For any* JSON string that violates the schema (wrong types, missing required fields, invalid enum values), the call should raise `ValidationError` and no downstream DB write should occur.

**Validates: Requirements 3.8, 3.9, 2.6, 2.7**

---

### Property 6: DB Node Write Validation Guard

*For any* call to `write_node()`, the function should perform a Pydantic re-validation of the payload before executing the SQL `INSERT`. If validation fails, the database must remain in its prior state — no partial row should appear in the `nodes` table.

**Validates: Requirements 2.6, 2.7**

---

### Property 7: Artifact Line Count Accuracy

*For any* string representing file content (with any number of lines, including zero), ingesting that content via `MCPHostClient.ingest_file()` should register an `IngestedArtifact` whose `line_count` equals the number of lines in the content as computed by `str.splitlines()`.

**Validates: Requirements 4.2, 4.3**

---

### Property 8: Citation File Path Referential Integrity

*For any* ingested artifact registered in the `ArtifactRegistry` with path `P`, any `SourceCitation` generated during a dimension review that references that file should have `file_path` equal to `P` as recorded at ingestion time.

**Validates: Requirements 4.5, 5.8**

---

### Property 9: Exactly 12 Dimension Tasks Launched

*For any* valid Layer 1 initiation, `TaskOrchestrator.launch_all()` should spawn exactly 12 concurrent tasks — one per `ReviewDimensionEnum` value — with no dimension repeated and no dimension omitted.

**Validates: Requirements 5.1**

---

### Property 10: Temperature-Zero LLM Call Invariant

*For any* call to `call_llm()` — whether for a dimension review or Arbitrator synthesis — the `temperature` parameter passed to `litellm.acompletion()` must equal `0.0` and the `response_format` must be `{"type": "json_object"}`.

**Validates: Requirements 5.2, 6.2**

---

### Property 11: Active Blueprint Prompt Inclusion

*For any* active `PromptBlueprint` record with `master_prompt_text = T`, and *for any* `ReviewDimensionEnum` value `D`, the system prompt produced by `PromptBuilder.build_dimension_prompt(D, ...)` must contain `T` as a substring.

**Validates: Requirements 5.3**

---

### Property 12: All 12 Dimensions Represented in Status Display

*For any* pipeline state (before, during, or after a Layer 1 run), the `PipelineView` widget must display exactly one status entry for each of the 12 `ReviewDimensionEnum` values — none missing, none duplicated.

**Validates: Requirements 5.5**

---

### Property 13: Arbitrator Receives All 12 Payloads

*For any* call to `ArbitratorEngine.run()`, the constructed arbitrator prompt must include references to all 12 dimension names from `ReviewDimensionEnum`. Calling `run()` with fewer than 12 payloads must raise `ArbitratorError` before any LLM call is made.

**Validates: Requirements 6.1**

---

### Property 14: Synthesis Node Lineage

*For any* Layer 1 node `N` and the synthesis node `S` produced by an Arbitrator run on `N`, `S.parent_id` must equal `N.id` and `S.project_id` must equal `N.project_id`.

**Validates: Requirements 6.4, 7.1, 7.2**

---

### Property 15: Compare Guard — Incomplete Dimensions Blocked

*For any* pipeline state where at least one dimension is not in `COMPLETE` state, invoking the Compare action must not call `ArbitratorEngine.run()`, and must instead surface a blocking modal that lists the non-complete dimensions.

**Validates: Requirements 6.5**

---

### Property 16: Proactive Advisor Tag Matching

*For any* set of project `global_tags` and *for any* set of `global_client_insights` rows, `ProactiveAdvisor.evaluate()` must return an `AdvisoryAlert` for every `(client_tag, pattern)` pair where `client_tag` is a member of `global_tags`, and must return no alerts for tags not present in `global_tags`.

**Validates: Requirements 8.1, 8.2**

---

### Property 17: Scope Policy Routing Decision Persistence

*For any* `IssueFinding` with `mitigation_routing = SCOPE_MODIFICATION` and *for any* routing decision `D` chosen by the user (`Risk Register`, `Assumptions Matrix`, or confirmed `Scope Modification`), after `ScopePolicyEnforcer.apply_routing_decision()` is called, the node's `metadata_json` must contain a routing decision entry whose `new_routing` field equals `D.value`.

**Validates: Requirements 9.3, 9.4, 9.5**

---

### Property 18: JSON Export / Import Round-Trip

*For any* complete pipeline node state (with all dimension payloads, optional Arbitrator result, and routing decisions), serializing to a `JSONPacket` and then importing it via `JSONPacketDeserializer` should produce a `NodeRow` whose `ReviewNodePayload` objects are equivalent to the originals. The `schema_version` field must be present and non-empty in every exported packet.

**Validates: Requirements 11.1, 11.2, 12.2, 12.4**

---

### Property 19: Import Validation — No Partial DB Write

*For any* JSON string that fails `JSONPacket.model_validate_json()` validation, calling `JSONPacketDeserializer.import_packet()` must not write any rows to the `nodes` table, `projects` table, or any other table. The database must remain in its prior state.

**Validates: Requirements 12.3**

---

### Property 20: Dream Cycle Frequency Count Monotonicity

*For any* collection of `nodes` records containing `k ≥ 1` findings with `confidence = RED` for a given `(client_tag, dimension)` pair, running the `DreamCycleWorker` should result in a `global_client_insights` row for that `(client_tag, HIGH_RISK_{dimension})` pair whose `frequency_count` is at least `k`. Running the Dream Cycle a second time on the same data must not decrease any existing `frequency_count`.

**Validates: Requirements 13.4**

---

### Property 21: One-Active Blueprint Invariant

*For any* set of blueprint records in `prompt_blueprints` and *for any* `activate_blueprint(id)` call, immediately after the call completes exactly one row in `prompt_blueprints` must have `is_active = 1`, and that row must be the one whose `id` matches the argument. This invariant must hold even if multiple blueprints previously had `is_active = 1` (a corrupted state) before the call.

**Validates: Requirements 14.2, 14.3**

---

### Property 22: Citation Jump Target Accuracy

*For any* `IssueFinding` with at least one `SourceCitation`, when that finding is selected in the `PipelineView`, the `CitationJumpRequested` message emitted must carry `file_path`, `line_start`, and `line_end` values that exactly match the first `SourceCitation` in `finding.citations[0]`.

**Validates: Requirements 10.8, 10.9**

---

### Property 23: Layer 1 Batch Commit Atomicity

*For any* Layer 1 run where all 12 dimension tasks reach `COMPLETE` state, exactly one row must be written to the `nodes` table containing all 12 dimension payloads in `metadata_json`. *For any* Layer 1 run where at least one dimension is in `FAILED` state, zero rows must be written to the `nodes` table as a result of that run.

**Validates: Requirements 5.4**
