# Design Document — Core Scope Gaps Implementation

## Architecture Overview

This feature fills 11 gaps between the TUI specification and the web application by extending the existing vertical stack: **aiosqlite schema → FastAPI routers → Reflex UI**. All new code follows the established layering conventions — raw SQL only in repository modules, Pydantic request/response models in `schemas.py`, and all Reflex state management through `AppState` handlers.

The work divides into three layers:

1. **Data layer** — Schema version 5 → 6 migration adding `review_links` and `proposal_review_links` junction tables, plus a data migration for backward-compatible proposal linking.
2. **API layer** — New endpoints in dedicated router files (`contexta/api/routers/`) with shared schemas in `contexta/api/schemas.py`.
3. **UI layer** — New Reflex components in `web/components/` and handlers in `web/state.py`.

---

## Component Design

### 1. Database Schema (Gap 1–2)

#### New Tables

```python
# contexta/db/schema.py — appended to DDL_STATEMENTS for SCHEMA_VERSION = 6

# review_links: M:N junction — which prior reviews inform a new review
"""
CREATE TABLE IF NOT EXISTS review_links (
    review_job_id    TEXT NOT NULL REFERENCES review_jobs(id),
    linked_review_id TEXT NOT NULL REFERENCES review_jobs(id),
    PRIMARY KEY (review_job_id, linked_review_id),
    CHECK(review_job_id != linked_review_id)
)
"""

# proposal_review_links: M:N junction — which reviews feed a proposal
"""
CREATE TABLE IF NOT EXISTS proposal_review_links (
    proposal_job_id TEXT NOT NULL REFERENCES proposal_jobs(id),
    review_job_id   TEXT NOT NULL REFERENCES review_jobs(id),
    PRIMARY KEY (proposal_job_id, review_job_id)
)
"""
```

#### Migration (v5 → v6)

The incremental migration block:

```python
if stored_version < 6:
    # Data migration: copy existing 1:1 proposal→review links into junction table
    await conn.execute("""
        INSERT OR IGNORE INTO proposal_review_links (proposal_job_id, review_job_id)
        SELECT id, review_job_id FROM proposal_jobs WHERE review_job_id IS NOT NULL
    """)
```

All `CREATE TABLE IF NOT EXISTS` statements run idempotently on every startup, so the new tables are safe on fresh installs and existing databases alike.

---

### 2. Review Linking API (Gap 1)

**File:** `contexta/api/routers/reviews.py` (extended)

#### Schema Additions

```python
# contexta/api/schemas.py

class CreateReviewRequest(BaseModel):
    version_id: str
    persona_roles: List[str]
    context: str = ""
    backend: Optional[str] = None
    linked_review_ids: List[str] = []  # NEW — prior reviews to include as context


class LinkableReviewItem(BaseModel):
    review_id: str
    persona: str
    run_date: str


class LinkableReviewsResponse(BaseModel):
    reviews: List[LinkableReviewItem]
    error: Optional[str] = None
```

#### New Endpoint

```
GET /api/versions/{version_id}/reviews/linkable → LinkableReviewsResponse
```

Returns all `review_jobs` for the version with `status = 'complete'`.

#### Review Creation Extension

The existing `POST /api/reviews` handler gains validation:
1. For each ID in `linked_review_ids`, verify it exists in `review_jobs` with `status = 'complete'`.
2. If any fails validation → HTTP 422 with the invalid ID in the error message.
3. On success, insert rows into `review_links`.

#### Pipeline Injection (Prior Review Intelligence)

In `pipeline_bridge.py`, before launching the `TaskOrchestrator`:

```python
async def _build_prior_intelligence(conn, review_id: str) -> str:
    """Extract RED/AMBER findings from linked reviews as structured context."""
    cursor = await conn.execute(
        "SELECT linked_review_id FROM review_links WHERE review_job_id = ?",
        (review_id,),
    )
    linked_ids = [row[0] async for row in cursor]
    if not linked_ids:
        return ""

    sections = []
    for lid in linked_ids:
        job = await api_repo.get_review_job(conn, lid)
        if not job or not job.node_id:
            continue
        node = await db_repo.get_node(conn, job.node_id)
        if not node:
            continue
        payloads = _load_dimension_payloads(node)
        high_findings = [
            f for p in payloads for f in p.findings
            if f.confidence.value in ("RED", "AMBER")
        ]
        for f in high_findings:
            sections.append(
                f"[{f.dimension.value}/{f.confidence.value}] {f.summary}"
            )

    if not sections:
        return ""
    return (
        "\n\n--- PRIOR REVIEW INTELLIGENCE ---\n"
        + "\n".join(sections)
        + "\n--- END PRIOR REVIEW INTELLIGENCE ---\n"
    )
```

This string is injected into the `PromptBuilder` context between the blueprint text and artifact content.

---

### 3. Proposal Re-Architecture (Gap 2)

**File:** `contexta/api/routers/proposals.py` (extended) + new version-scoped endpoint

#### New Endpoint

```
POST /api/versions/{version_id}/proposals
  Body: { "review_ids": ["uuid1", "uuid2", ...] }
  → 202 { "proposal_id": "...", "status": "queued" }
```

Validation:
- Each `review_id` must exist in `review_jobs` with `status = 'complete'` and `version_id` matching the path parameter.
- Failure → HTTP 422 identifying the invalid ID.

On success:
1. Create a `proposal_jobs` row (with `review_job_id` set to the first in the list for backward-compat column).
2. Insert one row per review into `proposal_review_links`.
3. Launch `run_proposal_pipeline_task` in background.

#### Listing Endpoint

```
GET /api/versions/{version_id}/proposals → ProposalListResponse
```

Joins `proposal_review_links` → `review_jobs` to filter proposals belonging to the version.

#### Schema Additions

```python
class CreateVersionProposalRequest(BaseModel):
    review_ids: List[str]


class ProposalListItem(BaseModel):
    proposal_id: str
    status: str
    created_at: str
    progress_message: Optional[str] = None
    linked_review_count: int


class ProposalListResponse(BaseModel):
    proposals: List[ProposalListItem]
    error: Optional[str] = None
```

#### Legacy Endpoint Preservation

The existing `POST /api/proposals` with `{ "review_id": "..." }` is retained as a thin wrapper that internally calls the same logic with a single-element `review_ids` list.

---

### 4. Fork Iteration (Gap 3)

**File:** `contexta/api/routers/nodes.py` (new)

#### Endpoint

```
POST /api/nodes/{node_id}/fork
  Body: { "name": "Fork v2 — Alternative approach" }
  → 201 { "node_id": "...", "name": "...", "created_at": "..." }
```

Implementation delegates to `db.repositories.fork_node()` which already:
- Validates parent existence (raises `ValueError` → mapped to 404).
- Inherits `project_id`, `layer_type` from parent.
- Sets `parent_id = node_id`.

The API handler additionally inherits `version_id` from the parent node.

#### Schema Additions

```python
class ForkNodeRequest(BaseModel):
    name: str


class ForkNodeResponse(BaseModel):
    node_id: str
    name: str
    created_at: str
    error: Optional[str] = None
```

---

### 5. Proactive Advisor Integration (Gap 4)

**File:** `contexta/api/routers/proposals.py` (extended)

#### Flow

1. When `run_proposal_pipeline_task` starts, before invoking `LayerTwoArbitrator.synthesize()`:
   - Load project's `global_tags`.
   - Call `ProactiveAdvisor.evaluate(global_tags, conn)`.
   - If alerts are non-empty:
     - Store alerts in proposal metadata: `metadata_json = {"alerts": [...], "acknowledged_at": null}`.
     - Set proposal status to `awaiting_acknowledgement`.
     - Return (do not proceed to synthesis).

2. Status endpoint reflects alerts:
   ```python
   class ProposalStatusResponse(BaseModel):
       # ... existing fields ...
       alerts: Optional[List[AdvisoryAlertItem]] = None
   ```

3. Acknowledgement endpoint:
   ```
   POST /api/proposals/{proposal_id}/acknowledge
     → 200 { "status": "running" }
   ```
   - Records `acknowledged_at` ISO timestamp in `metadata_json`.
   - Re-launches `run_proposal_pipeline_task` (which now checks for acknowledgement before evaluating the advisor again).

#### Schema Additions

```python
class AdvisoryAlertItem(BaseModel):
    pattern: str
    tag_combination: List[str]
    frequency_count: int
    advisory_text: str


class AcknowledgeResponse(BaseModel):
    status: str
    error: Optional[str] = None
```

---

### 6. Scope Policy Enforcement UI (Gap 5)

**File:** `contexta/api/routers/nodes.py` (extended)

#### Endpoint

```
POST /api/nodes/{node_id}/routing-decision
  Body: {
    "finding_id": "...",
    "decision": "risk_register" | "assumptions_matrix" | "scope_modification",
    "acknowledged": true  // required only when decision = "scope_modification"
  }
  → 200 { "status": "recorded" }
```

Implementation:
1. Load node from DB (404 if missing).
2. Parse `metadata_json`.
3. If `decision == "scope_modification"` and `acknowledged != true` → HTTP 422.
4. Append to `metadata_json["routing_decisions"]` list.
5. Write updated metadata back to the node row.

#### Schema Additions

```python
class RoutingDecisionRequest(BaseModel):
    finding_id: str
    decision: str  # "risk_register" | "assumptions_matrix" | "scope_modification"
    acknowledged: Optional[bool] = None


class RoutingDecisionResponse(BaseModel):
    status: str = "recorded"
    error: Optional[str] = None
```

---

### 7. JSON Export (Gap 6)

**File:** `contexta/api/routers/nodes.py` (extended)

#### Endpoint

```
GET /api/nodes/{node_id}/export
  → StreamingResponse (application/json, Content-Disposition: attachment)
```

Implementation:
1. Load node (404 if missing).
2. Load parent project for `project_name` and `global_tags`.
3. Build `JSONPacket` from node data using the same logic as `JSONPacketSerializer` but returning as HTTP response instead of writing to disk.
4. Return `StreamingResponse` with:
   - `Content-Type: application/json`
   - `Content-Disposition: attachment; filename="{node_name}_{node_id}.json"`

---

### 8. JSON Import (Gap 7)

**File:** `contexta/api/routers/admin.py` (new or extended)

#### Endpoint

```
POST /api/admin/import
  Content-Type: multipart/form-data
  Body: file upload
  → 201 { "node_id": "...", "status": "imported" }
  → 422 { "error": "validation details..." }
```

Implementation:
1. Read uploaded file bytes.
2. Validate against `JSONPacket` schema using Pydantic.
3. If validation fails → HTTP 422 with error details, no DB write.
4. On success, delegate to `JSONPacketDeserializer.import_packet()` logic (adapted to accept bytes instead of file path).
5. Return new node ID.

#### Schema Additions

```python
class ImportResponse(BaseModel):
    node_id: str
    status: str = "imported"
    error: Optional[str] = None
```

---

### 9. Dream Cycle Web Integration (Gap 8)

**File:** `contexta/api/routers/admin.py`

#### State Management

A module-level singleton tracks the running state:

```python
_dream_cycle_state: dict = {
    "status": "idle",       # idle | running | complete | failed
    "last_run": None,       # ISO timestamp
    "error": None,
    "job_id": None,
}
```

#### Endpoints

```
POST /api/admin/dream-cycle
  → 202 { "job_id": "...", "status": "running" }
  → 409 { "error": "Dream Cycle is already running." }

GET /api/admin/dream-cycle/status
  → 200 { "status": "idle", "last_run": "2025-...", "error": null }
```

Implementation:
- POST launches `DreamCycleWorker.run()` as a `BackgroundTask`.
- On completion, updates `_dream_cycle_state["status"] = "complete"` and records timestamp.
- On error, sets status to `"failed"` with error message.

#### Schema Additions

```python
class DreamCycleResponse(BaseModel):
    job_id: str
    status: str
    error: Optional[str] = None


class DreamCycleStatusResponse(BaseModel):
    status: str
    last_run: Optional[str] = None
    error: Optional[str] = None
```

---

### 10. Blueprint Management (Gap 9)

**File:** `contexta/api/routers/admin.py`

#### Endpoints

```
GET  /api/admin/blueprints          → BlueprintListResponse
POST /api/admin/blueprints          → BlueprintItemResponse (201)
POST /api/admin/blueprints/{id}/activate → ActivateResponse (200)
```

The list response includes a truncated prompt preview (first 200 characters).

#### Schema Additions

```python
class BlueprintItem(BaseModel):
    id: str
    name: str
    version_string: str
    is_active: bool
    prompt_preview: str  # first 200 chars of master_prompt_text


class BlueprintListResponse(BaseModel):
    blueprints: List[BlueprintItem]
    error: Optional[str] = None


class CreateBlueprintRequest(BaseModel):
    name: str
    version_string: str
    prompt_text: str


class BlueprintItemResponse(BaseModel):
    id: str
    name: str
    version_string: str
    is_active: bool
    error: Optional[str] = None


class ActivateResponse(BaseModel):
    status: str = "activated"
    error: Optional[str] = None
```

---

### 11. Global Client Insights Sidebar (Gap 10)

**File:** `contexta/api/routers/insights.py` (new)

#### Endpoint

```
GET /api/insights → InsightsResponse
```

Implementation:
```python
cursor = await conn.execute("""
    SELECT id, client_or_industry_tag, observed_pattern,
           frequency_count, last_updated
    FROM global_client_insights
    ORDER BY frequency_count DESC
    LIMIT 10
""")
```

#### Schema Additions

```python
class InsightItem(BaseModel):
    id: str
    client_or_industry_tag: str
    observed_pattern: str
    frequency_count: int
    last_updated: str


class InsightsResponse(BaseModel):
    insights: List[InsightItem]
    error: Optional[str] = None
```

---

### 12. Version-Level Proposal Listing (Gap 11)

Covered by the listing endpoint defined in Gap 2 (§3 above):

```
GET /api/versions/{version_id}/proposals → ProposalListResponse
```

---

## Data Models

### Database Row Additions (`contexta/api/repositories.py`)

```python
@dataclass
class ReviewLinkRow:
    review_job_id: str
    linked_review_id: str


@dataclass
class ProposalReviewLinkRow:
    proposal_job_id: str
    review_job_id: str
```

### New Repository Functions

| Function | Table | Purpose |
|----------|-------|---------|
| `insert_review_links(conn, review_job_id, linked_ids)` | review_links | Bulk-insert linked review references |
| `get_linked_review_ids(conn, review_job_id)` | review_links | Fetch all linked reviews for a job |
| `list_linkable_reviews(conn, version_id)` | review_jobs | Filter by version + complete status |
| `insert_proposal_review_links(conn, proposal_job_id, review_ids)` | proposal_review_links | Bulk-insert proposal→review links |
| `list_proposals_for_version(conn, version_id)` | proposal_review_links + proposal_jobs | Join to find version-scoped proposals |
| `update_node_metadata(conn, node_id, metadata_json)` | nodes | Patch metadata_json in-place |

---

## Interfaces

### Router Registration

All new routers are registered in `contexta/api/app.py`:

```python
from contexta.api.routers import nodes, insights, admin

app.include_router(nodes.router, prefix="/api")
app.include_router(insights.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
```

### Reflex UI Components

| Component File | Section | Features |
|---------------|---------|----------|
| `web/components/review_link_selector.py` | Version Detail | Chip selector for linkable reviews |
| `web/components/proposal_form.py` | Version Detail | Multi-review checklist + submit |
| `web/components/scope_policy_panel.py` | Review Detail | Routing toggle buttons |
| `web/components/insights_sidebar.py` | Global Sidebar | Collapsible advisory cards |
| `web/components/blueprint_panel.py` | Admin Page | DataTable + create form + activate |
| `web/components/dream_cycle_panel.py` | Admin Page | Trigger button + status indicator |
| `web/components/import_panel.py` | Admin Page | File upload component |

### AppState Handlers

New event handlers added to `web/state.py`:

- `fetch_linkable_reviews(version_id)` → populates `linkable_reviews: list[dict]`
- `submit_review_with_links(linked_ids)` → POST with linked_review_ids
- `fetch_proposals_for_version(version_id)` → populates `version_proposals: list[dict]`
- `submit_version_proposal(review_ids)` → POST to version-level proposals endpoint
- `fork_node(node_id, name)` → POST to fork endpoint
- `submit_routing_decision(node_id, finding_id, decision, acknowledged)` → POST routing-decision
- `acknowledge_proposal(proposal_id)` → POST acknowledge
- `trigger_dream_cycle()` → POST dream-cycle
- `fetch_dream_cycle_status()` → GET dream-cycle status
- `fetch_blueprints()` → GET blueprints
- `create_blueprint(name, version, text)` → POST blueprints
- `activate_blueprint(id)` → POST activate
- `fetch_insights()` → GET insights

---

## Error Handling

All endpoints follow the existing project convention:

1. **Validation errors** (missing fields, invalid IDs) → HTTP 422 with descriptive `detail` message.
2. **Not found** → HTTP 404 with resource-identifying `detail`.
3. **Conflict** (Dream Cycle already running) → HTTP 409.
4. **Background task failures** → Recorded in `progress_message` field; status set to `"failed"`.
5. **All response models** include `error: Optional[str] = None` for frontend toast integration.

The Reflex UI displays errors via `AppState.set_toast(message, is_error=True)` — the same pattern used by all existing handlers.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Review link insertion integrity

*For any* list of `linked_review_ids` submitted with a new review request, if all IDs correspond to existing completed Review_Jobs then exactly that many rows SHALL be inserted into `review_links` with `review_job_id` equal to the newly created job; if any ID is invalid or non-complete, HTTP 422 SHALL be returned and zero rows SHALL be inserted into `review_links`.

**Validates: Requirements 1.2, 1.3**

### Property 2: Linkable reviews filter correctness

*For any* version containing a mix of review jobs with statuses in {queued, running, complete, failed}, the `/api/versions/{version_id}/reviews/linkable` endpoint SHALL return exactly those review jobs whose status is 'complete' and no others.

**Validates: Requirements 1.4**

### Property 3: Prior review intelligence prompt injection

*For any* set of linked reviews containing RED or AMBER findings, the constructed LLM prompt SHALL contain a formatted representation of every such finding from every linked review, and SHALL contain no findings from reviews that are not linked.

**Validates: Requirements 1.5**

### Property 4: Proposal multi-review linking integrity

*For any* list of `review_ids` submitted to the version-level proposal endpoint, if all IDs correspond to completed Review_Jobs belonging to that version then a Proposal_Job is created with exactly that many rows in `proposal_review_links`; if any ID is invalid or belongs to a different version, HTTP 422 SHALL be returned and no Proposal_Job SHALL be created.

**Validates: Requirements 2.3, 2.4**

### Property 5: Version-scoped proposal listing completeness

*For any* version, the GET proposals listing SHALL return exactly the set of Proposal_Jobs whose linked reviews (via `proposal_review_links`) belong to that version, with correct `linked_review_count` values matching the actual junction row counts.

**Validates: Requirements 2.5, 11.1**

### Property 6: Fork node inheritance

*For any* existing node in the database, forking it with any non-empty name SHALL produce a new node whose `parent_id` equals the original node's ID, and whose `project_id`, `version_id`, and `layer_type` are identical to the parent node's values.

**Validates: Requirements 3.1, 3.2**

### Property 7: Advisor alerts surface in proposal status

*For any* non-empty list of `AdvisoryAlert` objects returned by `ProactiveAdvisor.evaluate()`, every alert's pattern, tag_combination, and frequency_count SHALL appear in the proposal's status response `alerts` array.

**Validates: Requirements 4.2**

### Property 8: Unacknowledged alerts block synthesis

*For any* Proposal_Job that has non-empty alerts in its metadata and no `acknowledged_at` timestamp, the proposal status SHALL be `awaiting_acknowledgement` and the synthesis pipeline SHALL NOT proceed.

**Validates: Requirements 4.3**

### Property 9: Acknowledgement audit trail

*For any* POST to the acknowledge endpoint for a proposal with unacknowledged alerts, the Proposal_Job's `metadata_json` SHALL contain an `acknowledged_at` field with a valid ISO-8601 UTC timestamp recorded at the time of acknowledgement.

**Validates: Requirements 4.7**

### Property 10: Routing decision persistence

*For any* valid POST to `/api/nodes/{node_id}/routing-decision` with a `finding_id` and `decision`, the node's `metadata_json["routing_decisions"]` list SHALL contain an entry matching the submitted finding_id and decision value.

**Validates: Requirements 5.3**

### Property 11: Scope modification requires explicit acknowledgement

*For any* routing decision POST where `decision` is `"scope_modification"`, the request SHALL be rejected with HTTP 422 if `acknowledged` is not `true`; it SHALL succeed only when `acknowledged` is `true`.

**Validates: Requirements 5.4**

### Property 12: Export produces valid JSONPacket

*For any* existing node with at least one dimension payload in its metadata, the GET export endpoint SHALL return a response body that validates against the `JSONPacket` Pydantic schema and whose `schema_version` field equals `EXPORT_SCHEMA_VERSION`, and whose `payloads` list contains all dimension payloads from the source node.

**Validates: Requirements 6.1, 6.2**

### Property 13: Import validation gate — round-trip safety

*For any* uploaded file, if it fails `JSONPacket` schema validation then the endpoint SHALL return HTTP 422 and the `nodes` table SHALL have zero new rows; if it passes validation then a new node SHALL be created whose dimension payloads match those in the uploaded packet.

**Validates: Requirements 7.1, 7.2, 7.3**

### Property 14: Blueprint one-active invariant

*For any* activation request targeting a valid blueprint ID, after the operation completes exactly one blueprint in the database SHALL have `is_active = true` (the targeted one) and all others SHALL have `is_active = false`.

**Validates: Requirements 9.3**

### Property 15: Blueprint creation inactive by default

*For any* valid blueprint creation request, the newly created blueprint row SHALL have `is_active = false` and SHALL NOT alter the `is_active` state of any existing blueprint.

**Validates: Requirements 9.2**

### Property 16: Insights ordering and completeness

*For any* state of the `global_client_insights` table, the GET `/api/insights` endpoint SHALL return at most 10 entries, ordered by `frequency_count` descending, each containing non-null `client_or_industry_tag`, `observed_pattern`, `frequency_count`, and `last_updated` fields.

**Validates: Requirements 10.1, 10.2**
