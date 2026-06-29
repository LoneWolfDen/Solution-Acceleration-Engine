# Refined API Contract + Implementation Plan

---

## Part 1 — Refined API Contract

### Standardised Response Envelope

Every endpoint, success or failure, includes an `error` field. The frontend checks this field to trigger Toast notifications without inspecting HTTP status codes.

```
Standard success shape:
  { ...payload fields..., error: null }

Standard error shape  (returned alongside the appropriate HTTP 4xx/5xx status):
  { error: "Human-readable description of what went wrong" }
```

---

### Full Endpoint Registry

```
── PROJECTS ────────────────────────────────────────────────────────────────

GET  /api/projects
  Response: {
    projects: [ { project_id, name, version_count, review_count, storage_bytes } ],
    error: null
  }

DELETE /api/projects/{project_id}
  Response: { project_id, status: "deleted", error: null }


── VERSIONS ────────────────────────────────────────────────────────────────

GET  /api/projects/{project_id}/versions
  Response: {
    versions: [ { version_id, name, created_at, artifact_count, review_count } ],
    error: null
  }

GET  /api/versions/{version_id}
  Response: {
    version_id, name, created_at,
    artifacts: [ { artifact_id, title, tags, is_active } ],
    error: null
  }

POST /api/versions
  Payload:  { project_id, version_name, artifact_ids: [str] }
  Response: { version_id, name, created_at, artifact_count, error: null }


── REVIEWS ─────────────────────────────────────────────────────────────────

GET  /api/versions/{version_id}/reviews
  Response: {
    reviews: [ { review_id, run_date, status, persona } ],
    error: null
  }

GET  /api/nodes/{node_id}
  Response:  Review_Payload {
    review_id, project_id, version_id,
    status, run_date, persona,
    findings: [
      { finding_id, type, severity, text, source_artifact, citation }
    ],
    summary: { risks, constraints, dependencies, assumptions, action_items },
    error: null
  }

POST /api/reviews                             ← NEW
  Payload:  { version_id, persona_roles: [str], context: str }
  Response: { review_id, status: "queued", error: null }

GET  /api/reviews/{review_id}/status          ← NEW (for UI polling)
  Response: { review_id, status: "queued"|"running"|"complete"|"failed",
              progress_message: str | null, error: null }


── ARTIFACTS ───────────────────────────────────────────────────────────────

GET  /api/projects/{project_id}/artifacts
  Response: {
    artifacts: [
      { artifact_id, title, tags, is_active: bool, created_at }  ← is_active explicit
    ],
    error: null
  }

POST /api/artifacts
  Payload:  multipart/form-data or JSON:
            { source: "upload"|"paste"|"url",
              title, project_id,
              content?:str, url?:str, file?:binary,
              tags: [str] }
  Response: { artifact_id, title, tags, is_active: true, created_at, error: null }

PATCH /api/artifacts/{artifact_id}
  Payload:  { active: bool }
  Response: { artifact_id, is_active: bool, error: null }

DELETE /api/artifacts/{artifact_id}
  Response: { artifact_id, status: "deleted", error: null }

GET  /api/artifacts/suggestions
  Query:    ?filename=<str>&content_preview=<str>
  Note:     Regex/file-type analysis ONLY. No LLM calls.
  Response: { suggestions: [str], error: null }


── PROPOSALS ───────────────────────────────────────────────────────────────

POST /api/proposals                           ← NEW
  Payload:  { review_id }
  Response: { proposal_id, status: "queued", error: null }

GET  /api/proposals/{proposal_id}/status      ← NEW (for UI polling)
  Response: { proposal_id, status: "queued"|"running"|"complete"|"failed",
              progress_message: str | null, error: null }


── ADMIN ────────────────────────────────────────────────────────────────────

GET  /api/admin/health
  Response: {
    last_run: str | null,
    providers: { groq, openrouter, gemini, ollama: "configured"|"not_set" },
    error: null
  }

GET  /api/admin/config
  Response: {
    providers: { groq, openrouter, gemini: "set"|"not_set" },
    ollama_url: str,
    thresholds: { risk: float, constraint: float, dependency: float },
    max_active_projects: int,
    error: null
  }

POST /api/admin/config
  Payload:  { field: "api_key"|"threshold"|"ollama_url",
              provider?:str, key?:str,
              threshold_name?:str, threshold_value?:float,
              ollama_url?:str }
  Response: { field, status: "saved", error: null }
```

---

## Part 2 — Implementation Plan

### Architectural Decisions (stated upfront)

| Decision | Choice | Reason |
|---|---|---|
| UI framework | Reflex | Full-stack Python, no JS required |
| API layer | FastAPI, mounted on Reflex's internal app | Single process, single port |
| DB access | Reuse `contexta.db.repositories` | No duplication of DB logic |
| Pipeline calls | `contexta.pipeline` called as async background task | Non-blocking API response |
| State management | Reflex `State` class (no hidden globals) | All UI state derived from API responses |
| Container shape | Single container, `docker-compose.yml` for convenience | Matches project constraint |
| SQLite persistence | Docker volume mounted to `/app/data/` | DB survives container restarts |

---

### Milestone 1 — Backend API Skeleton

**Goal:** All API endpoints exist, return structured JSON with the `error` field, and the FastAPI `/docs` page is reachable.

**Tasks:**

```
1.1  Create contexta/api/__init__.py
     — Instantiate FastAPI app
     — Register all sub-routers
     — Add global exception handler that returns { error: str } on uncaught exceptions

1.2  Create contexta/api/schemas.py
     — Define all Pydantic request and response models
     — Every response model includes: error: str | None = None
     — Models: ProjectResponse, ArtifactResponse, VersionResponse,
       ReviewPayloadResponse, ReviewStatusResponse, ProposalStatusResponse,
       AdminConfigResponse, AdminHealthResponse

1.3  Create contexta/api/routers/projects.py
     — GET  /api/projects
     — DELETE /api/projects/{project_id}

1.4  Create contexta/api/routers/versions.py
     — GET  /api/projects/{project_id}/versions
     — GET  /api/versions/{version_id}
     — POST /api/versions

1.5  Create contexta/api/routers/reviews.py
     — GET  /api/versions/{version_id}/reviews
     — GET  /api/nodes/{node_id}
     — POST /api/reviews  (enqueues background task; returns queued status immediately)
     — GET  /api/reviews/{review_id}/status

1.6  Create contexta/api/routers/artifacts.py
     — GET  /api/projects/{project_id}/artifacts  (is_active field explicit)
     — POST /api/artifacts
     — PATCH /api/artifacts/{artifact_id}
     — DELETE /api/artifacts/{artifact_id}
     — GET  /api/artifacts/suggestions

1.7  Create contexta/api/routers/proposals.py
     — POST /api/proposals  (enqueues background task; returns queued status immediately)
     — GET  /api/proposals/{proposal_id}/status

1.8  Create contexta/api/routers/admin.py
     — GET  /api/admin/health
     — GET  /api/admin/config
     — POST /api/admin/config

1.9  Create contexta/api/dependencies.py
     — get_db() dependency (yields DB session using existing contexta.db)
     — get_config() dependency (reads from secure config store)

1.10 Implement real DB reads for GET /api/projects and GET /api/nodes/{node_id}
     — Wire to existing contexta.db.repositories (no new DB logic)

1.11 Implement real DB writes for POST /api/artifacts and POST /api/versions
     — Validate inputs, fail clearly with { error: ... } on bad data

1.12 Stub all async background tasks (POST /api/reviews, POST /api/proposals)
     — Return { status: "queued" } immediately
     — Background task logs "STUB: pipeline not yet wired" and sets status = "complete"
     — Real wiring deferred to Milestone 4
```

**Exit criteria:**
- `uvicorn contexta.api:app` starts without error
- `GET /api/projects` returns real data from `contexta.db`
- `GET /api/admin/health` returns correct provider statuses
- All endpoints appear in `/docs`
- Every response includes `error: null` on success

---

### Milestone 2 — UI Foundation

**Goal:** Reflex app runs, sidebar renders the project tree, selecting a node populates the content pane with API-sourced data.

**Tasks:**

```
2.1  Add reflex to pyproject.toml (open-source, no paid tier required)
     Run `reflex init` to scaffold web/ directory
     Confirm it runs with `reflex run` before continuing

2.2  Define web/state.py — AppState (inherits rx.State)
     Fields: projects[], selected_node_id, selected_node_type,
             review_payload, version_payload, is_loading, toast_message
     All fields populated exclusively from API responses

2.3  Build web/components/navbar.py
     — App title/logo, navigation links (Dashboard, Ingest, Admin)
     — Active link highlight driven by current route

2.4  Build web/components/sidebar.py — ProjectTreeSidebar
     — Renders projects[] from AppState
     — Collapsible: Project > Version > Review
     — Expand/collapse state stored in AppState
     — Click handler calls AppState.select_node(node_id, node_type)
     — [+ New Project] button placeholder (wired in M3)

2.5  Build web/components/content_pane.py — MainContentPane
     — Renders EmptyState when selected_node_id is None
     — Routes to ReviewDetailPane when node_type == "review"
     — Routes to VersionDetailPane when node_type == "version"

2.6  Build web/components/review_detail.py — ReviewDetailPane
     — Finding summary counts (Risks, Constraints, Dependencies,
       Assumptions, Action Items) from review_payload.summary
     — Scrollable FindingCard list from review_payload.findings[]

2.7  Build web/components/finding_card.py — FindingCard
     — Displays: type badge, severity badge, text body, source_artifact

2.8  Build web/components/version_detail.py — VersionDetailPane
     — Linked artifacts table (title, tags, is_active status)
     — Reviews list (run_date, status, persona)

2.9  Wire AppState.load_projects() → GET /api/projects
     — Called on page load via on_load event
     — Populates AppState.projects[]

2.10 Wire AppState.select_node() → GET /api/nodes/{node_id} or
     GET /api/versions/{version_id} depending on node_type
     — Populates review_payload or version_payload

2.11 Build web/components/toast.py — ToastNotification
     — Renders when AppState.toast_message is non-null
     — Auto-dismisses after 4 seconds
     — Error variant (red) and success variant (green)
     — Triggered by any API response where error != null
```

**Exit criteria:**
- `reflex run` shows the two-column layout
- Sidebar renders projects from the live API
- Clicking a review node populates the content pane with real findings
- Clicking a version node shows its artifact list

---

### Milestone 3 — Ingestion & Admin

**Goal:** Full artifact ingestion flow works end-to-end. Admin settings are editable and saved.

**Tasks:**

```
3.1  Build web/components/ingestion_modal.py — ArtifactIngestionModal
     — Tabbed: Upload File | Paste Text | URL Reference
     — Title field (shared across tabs)
     — File input, textarea, URL input per respective tab
     — Trigger: [+ New Artifact] button in sidebar or navbar

3.2  Build web/components/tag_chips.py — TagSuggestionChips
     — On title/content change: calls GET /api/artifacts/suggestions
     — Renders suggestion chips (hollow = unselected, filled = selected)
     — Custom tag input with Enter-to-add
     — Applied tags strip with ✕ to remove

3.3  Wire modal save → POST /api/artifacts
     — Shows loading spinner on save button
     — On success: transitions to ArtifactTriageWidget
     — On error: fires Toast with error message from response.error

3.4  Build web/components/triage_widget.py — ArtifactTriageWidget
     — Calls GET /api/projects/{project_id}/artifacts on mount
     — Renders table: title | tags | is_active toggle
     — Newly saved artifact highlighted

3.5  Wire is_active toggle → PATCH /api/artifacts/{artifact_id}
     — Optimistic UI update (toggle flips immediately)
     — Reverts and shows Toast if API returns error

3.6  Wire [Create Version] → POST /api/versions
     — Collects all is_active=true artifact_ids from triage state
     — On success: closes modal, sidebar tree refreshes

3.7  Build web/pages/admin.py — AdminDashboardPage
     — Section: System Health (provider status pills from GET /api/admin/health)
     — Section: LLM Configuration (API key fields, Ollama URL)
     — Section: Gate Thresholds (numeric inputs per dimension)
     — Section: Project Management (table with Delete buttons)

3.8  Wire GET /api/admin/config → pre-populate admin fields
     — API key fields display "••••••••" when status == "set", "Not set" otherwise
     — Threshold fields show current values

3.9  Wire [Save API Keys] and [Save Thresholds] → POST /api/admin/config
     — Separate save buttons for keys and thresholds (don't mix mutations)
     — Toast on success or error

3.10 Wire [Delete ⚠] → confirmation dialog → DELETE /api/projects/{project_id}
     — Dialog displays project name, version count, review count
     — On confirm: removes project row, refreshes sidebar tree via GET /api/projects
     — Toast confirms deletion

3.11 Integrate ToastNotification into AppState
     — All mutation handlers (POST, PATCH, DELETE) check response.error
     — If non-null: set AppState.toast_message = response.error
     — If null: set AppState.toast_message = success confirmation string
```

**Exit criteria:**
- Paste text → select tags → save → triage → toggle artifact OFF → Create Version completes without errors
- Admin page saves an API key; field shows masked display after save
- Delete project with confirmation removes it from sidebar and admin table

---

### Milestone 4 — Orchestration & Synthesis

**Goal:** Reviews can be triggered, proposals created, and asynchronous status is visible in the UI.

**Tasks:**

```
4.1  Build web/pages/run_review.py — RunReviewPage
     — Persona role checkboxes (populated from static enum list, not API)
     — AI backend selector dropdown (populated from GET /api/admin/config providers)
     — Context textarea (optional, appended to prompt on backend)
     — [Run Review] submit button

4.2  Wire [Run Review] → POST /api/reviews
     — Payload: { version_id, persona_roles, context }
     — On success: navigate to review status page with review_id

4.3  Wire POST /api/reviews backend task to contexta.pipeline
     — Remove stub from Milestone 1
     — Runs pipeline.run() as FastAPI BackgroundTask
     — Updates review status in DB as pipeline progresses

4.4  Build web/components/status_banner.py — AsyncStatusBanner
     — Accepts: endpoint_url (for polling), initial_status
     — States: "queued" (grey), "running" (blue spinner),
               "complete" (green), "failed" (red)
     — Polls every 3 seconds; stops on terminal state

4.5  Wire status banner to GET /api/reviews/{review_id}/status
     — On "complete": redirect to Master-Detail pane with new review node selected
     — On "failed": show Toast with error message from response.error
     — Sidebar refreshes to show new review node

4.6  Build ProposalPane within ReviewDetailPane
     — Shows "No proposal yet" + [Generate Proposal] button when no proposal exists
     — Shows proposal content (text) when proposal exists

4.7  Wire [Generate Proposal] → POST /api/proposals
     — On success: replaces button with AsyncStatusBanner for proposal

4.8  Wire POST /api/proposals backend task to contexta pipeline synthesis engine
     — Remove stub from Milestone 1
     — On "complete": proposal content appears in ProposalPane

4.9  Ensure sidebar auto-refreshes after review completes
     — AppState polls GET /api/projects/{id}/versions when a review is running
     — New review leaf node appears when pipeline finishes
```

**Exit criteria:**
- Clicking Run Review submits payload, status banner shows "queued" then "running" then "complete"
- New review node appears in sidebar on completion; content pane renders findings
- Clicking Generate Proposal triggers synthesis; proposal text renders in ProposalPane

---

### Milestone 5 — API Integration Tests

**Goal:** All API endpoints verified against the contract using pytest + FastAPI TestClient. No UI involved.

**Tasks:**

```
5.1  Create tests/api/conftest.py
     — TestClient fixture wrapping the FastAPI app
     — In-memory SQLite DB fixture (isolated per test)
     — Mock pipeline fixture (stubs background tasks, no LLM calls)

5.2  tests/api/test_projects.py
     — GET /api/projects returns list with all required fields
     — GET /api/projects returns empty list when no projects exist
     — DELETE /api/projects/{id} removes project and cascades to children
     — DELETE /api/projects/{unknown_id} returns 404 with error field

5.3  tests/api/test_artifacts.py
     — GET /api/projects/{id}/artifacts returns is_active: bool on every artifact
     — POST /api/artifacts source="paste" creates artifact with correct tags
     — POST /api/artifacts source="upload" creates artifact from file bytes
     — POST /api/artifacts source="url" creates artifact with url reference
     — PATCH /api/artifacts/{id} {active: false} sets is_active to false
     — GET /api/artifacts/suggestions returns string list; no LLM calls made

5.4  tests/api/test_versions.py
     — POST /api/versions creates version with correct artifact_ids
     — GET /api/versions/{id} returns artifacts with is_active field
     — POST /api/versions with empty artifact_ids returns 422 with error field

5.5  tests/api/test_reviews.py
     — POST /api/reviews returns { review_id, status: "queued", error: null }
     — GET /api/reviews/{id}/status returns valid status enum value
     — GET /api/nodes/{node_id} returns Review_Payload with findings array
     — GET /api/nodes/{unknown_id} returns 404 with error field

5.6  tests/api/test_proposals.py
     — POST /api/proposals returns { proposal_id, status: "queued", error: null }
     — POST /api/proposals with unknown review_id returns 404 with error field

5.7  tests/api/test_admin.py
     — GET /api/admin/config returns masked key statuses (never raw values)
     — POST /api/admin/config field="api_key" stores key server-side
     — GET /api/admin/config after key save shows status "set"
     — POST /api/admin/config field="threshold" updates threshold value
     — GET /api/admin/health returns provider connectivity status

5.8  tests/api/test_error_contract.py
     — Every 4xx and 5xx response contains a non-null error field
     — Success responses all contain error: null
     — Malformed JSON body returns 422 with error field
```

**Exit criteria:**
- `pytest tests/api/ -v` passes with zero failures
- No LLM calls made during test run (mock pipeline fixture enforced)

---

### Milestone 6 — Component UI Tests

**Goal:** Key Reflex components render correctly when given mock API responses. Tests run in isolation without a live server.

**Tasks:**

```
6.1  Create tests/ui/conftest.py
     — Test harness for Reflex component rendering (using reflex test utilities)
     — Mock AppState factory that accepts pre-set field values

6.2  tests/ui/test_triage_widget.py
     — ArtifactTriageWidget renders N rows given mock artifact list of length N
     — is_active=true artifact shows ON toggle state
     — is_active=false artifact shows OFF toggle state
     — Clicking toggle dispatches correct PATCH payload

6.3  tests/ui/test_tag_chips.py
     — TagSuggestionChips renders correct number of chips from mock suggestions
     — Clicking unselected chip moves it to "applied" strip
     — Clicking applied chip removes it
     — Pressing Enter in custom tag input adds chip to applied strip

6.4  tests/ui/test_finding_card.py
     — FindingCard renders type, severity, text, source_artifact from mock finding
     — Type badge shows correct label for each finding type enum value
     — Severity badge shows correct colour variant

6.5  tests/ui/test_toast.py
     — ToastNotification renders with error message when toast_message is set
     — ToastNotification is absent from DOM when toast_message is None
     — Error variant (red) shown when message originates from error field

6.6  tests/ui/test_sidebar.py
     — ProjectTreeSidebar renders correct number of project nodes from mock list
     — Clicking expand on a project reveals its version children
     — Selected node is highlighted in AppState
```

**Exit criteria:**
- `pytest tests/ui/ -v` passes with zero failures
- Tests run without a live Reflex server or API

---

### Milestone 7 — Docker Integration

**Goal:** `docker-compose up --build` from a clean clone produces a fully integrated stack. No manual steps.

**Tasks:**

```
7.1  Update Dockerfile
     — Base image: python:3.11-slim (open-source)
     — Install poetry deps (including reflex)
     — Run `reflex export --frontend-only` to produce static build
     — Copy built frontend into container
     — Expose port 8000 (FastAPI + Reflex backend on same port)

7.2  Create entrypoint.sh
     — Step 1: Run DB migrations (create tables if not exist)
     — Step 2: Start Reflex with FastAPI API routes mounted
     — Single process; no supervisord needed

7.3  Create docker-compose.yml
     Services:
       sae:
         build: .
         ports: ["8000:8000"]
         volumes: ["./data:/app/data"]   # SQLite DB + artifact files
         environment:
           - GROQ_API_KEY=${GROQ_API_KEY:-}
           - OPENROUTER_API_KEY=${OPENROUTER_API_KEY:-}
           - GEMINI_API_KEY=${GEMINI_API_KEY:-}
           - OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://localhost:11434}

7.4  Create .env.example
     — Documents all environment variables
     — No keys baked into image; all injected at runtime

7.5  Update pyproject.toml
     — Add [tool.reflex] section with app_name and backend_port
     — Ensure all new dependencies (reflex, fastapi, httpx) declared

7.6  Smoke test checklist (manual, run before marking complete)
     — docker-compose up --build completes without error
     — http://localhost:8000 renders the Reflex UI
     — http://localhost:8000/api/projects returns JSON
     — http://localhost:8000/docs shows FastAPI docs
     — docker-compose down && docker-compose up  (no data loss — SQLite persists)
     — GROQ_API_KEY=test docker-compose up  (key visible in admin health as "configured")
```

**Exit criteria:**
- `docker-compose up --build` from clean clone shows running UI on `localhost:8000`
- SQLite DB survives `docker-compose down` and `up`
- No API keys baked into the image

---

## Milestone Dependency Map

```
M1 (Backend API Skeleton)
  └─► M2 (UI Foundation)
        └─► M3 (Ingestion & Admin)
              └─► M4 (Orchestration & Synthesis)

M1 ──────────────────────────────────────────► M5 (API Integration Tests)

M2 + M3 ─────────────────────────────────────► M6 (Component UI Tests)

M1 + M2 + M3 + M4 + M5 + M6 ────────────────► M7 (Docker Integration)
```

---

## File Structure (new additions)

```
Solution-Acceleration-Engine/
│
├── contexta/
│   └── api/                       ← NEW (Milestone 1)
│       ├── __init__.py            (FastAPI app instance)
│       ├── dependencies.py        (DB + config DI)
│       ├── schemas.py             (all Pydantic models with error field)
│       └── routers/
│           ├── projects.py
│           ├── versions.py
│           ├── reviews.py
│           ├── artifacts.py
│           ├── proposals.py
│           └── admin.py
│
├── web/                           ← NEW (Milestone 2)
│   ├── web.py                     (Reflex app entry, mounts FastAPI)
│   ├── state.py                   (AppState)
│   ├── pages/
│   │   ├── dashboard.py
│   │   ├── run_review.py
│   │   └── admin.py
│   └── components/
│       ├── navbar.py
│       ├── sidebar.py
│       ├── content_pane.py
│       ├── review_detail.py
│       ├── version_detail.py
│       ├── finding_card.py
│       ├── ingestion_modal.py
│       ├── triage_widget.py
│       ├── tag_chips.py
│       ├── status_banner.py
│       └── toast.py
│
├── tests/
│   ├── api/                       ← NEW (Milestone 5)
│   │   ├── conftest.py
│   │   ├── test_projects.py
│   │   ├── test_artifacts.py
│   │   ├── test_versions.py
│   │   ├── test_reviews.py
│   │   ├── test_proposals.py
│   │   ├── test_admin.py
│   │   └── test_error_contract.py
│   └── ui/                        ← NEW (Milestone 6)
│       ├── conftest.py
│       ├── test_triage_widget.py
│       ├── test_tag_chips.py
│       ├── test_finding_card.py
│       ├── test_toast.py
│       └── test_sidebar.py
│
├── Dockerfile                     ← UPDATED (Milestone 7)
├── docker-compose.yml             ← NEW (Milestone 7)
├── entrypoint.sh                  ← NEW (Milestone 7)
└── .env.example                   ← NEW (Milestone 7)
