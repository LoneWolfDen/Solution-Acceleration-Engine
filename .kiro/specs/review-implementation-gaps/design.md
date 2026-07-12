# Design Document

## Overview

This is an investigative audit, not a code-building feature. There is no application code to design, build, or test — the sole deliverable is a markdown report. This document instead specifies:

1. The **audit methodology** — which files are statically inspected and how three verification checks (backend existence, API wiring, UI rendering) are performed for each functional area.
2. The **classification decision procedure** — a deterministic mapping from inspection findings to one of the four `Status_Classification` values already defined in `requirements.md`.
3. The **structure/template** of the audit deliverable, `gap-analysis.md`.
4. The **output location** and the **read-only constraint** governing execution.

No source code, schema, or configuration is modified as part of this feature. The only artifact produced is `.kiro/specs/review-implementation-gaps/gap-analysis.md`. This `design.md` itself is a planning artifact for the *audit process*; the audit's findings are executed in the Tasks phase and written to `gap-analysis.md`, not to this file.

## Architecture

The audit is a single-pass, read-only static analysis pipeline over two codebases (`contexta/` backend, `web/` Reflex frontend) plus three specification documents (`project-contexta`, `core-scope-gaps-implementation`, and this spec's own `requirements.md`). It produces one output artifact.

```
                    ┌───────────────────────────┐
                    │ Original_Scope_Document    │
                    │ project-contexta/          │
                    │ requirements.md + design.md│
                    └─────────────┬─────────────┘
                                  │ (1) enumerate + filter Web_Scope
                                  ▼
                    ┌───────────────────────────┐
                    │ Scope Enumeration          │
                    │ Req 1–14 → Web_Scope items  │
                    └─────────────┬─────────────┘
                                  │ (2) for each item
                                  ▼
        ┌─────────────────────────────────────────────────┐
        │ Static Inspection (per Gap_Item)                 │
        │  - Backend existence check                       │
        │  - API wiring check                               │
        │  - UI rendering check                              │
        └───────────────────────┬─────────────────────────┘
                                 │ (3) evidence tuple
                                 ▼
                    ┌───────────────────────────┐
                    │ Classification Procedure   │
                    │ evidence → Status_Classif.  │
                    └─────────────┬─────────────┘
                                  │ (4) accumulate Gap_Items
                                  ▼
        ┌─────────────────────────────────────────────────┐
        │ Re-verification pass                              │
        │  - 11 Core_Gaps_Spec items (old vs new status)     │
        │  - Review_Linking_Finding / Project_Scoped_...     │
        │  - Artifact_Labeling_Finding / _Traceability_...    │
        │  - Tracking_Gap, Scripts_Markdown_Note              │
        └───────────────────────┬─────────────────────────┘
                                 │ (5) render
                                 ▼
                    ┌───────────────────────────┐
                    │ gap-analysis.md            │
                    │ (Audit_Report deliverable)  │
                    └───────────────────────────┘
```

There is no runtime component, no persisted state, and no user-facing UI. The "system" is the audit procedure itself, executed by the agent during the Tasks phase.

## Components and Interfaces

Since there is no running software, "components" here are inspection procedures, each scoped to a set of files. Every procedure is read-only (uses `read_files` / `grep_search` / `list_directory` only).

### 1. Scope Enumeration Component

**Input:** `.kiro/specs/project-contexta/requirements.md`, `.kiro/specs/project-contexta/design.md`
**Output:** An ordered list of `Web_Scope` items — one per acceptance criterion in Requirements 1–14 that is not exclusively TUI-mechanical.

**Procedure:**
- Read every acceptance criterion across Requirements 1–14.
- Classify each criterion as `tui_only`, `mixed`, or `web` using the filter rule in Requirement 1.2/1.3 of this spec's `requirements.md`:
  - `tui_only`: behavior defined exclusively via keyboard navigation, footer key bindings, TUI pane layout, `CitationJumpRequested`, or Admin Tab *screen navigation* mechanics.
  - `mixed`: the criterion names a TUI mechanic but also implies a web-realizable functional intent (e.g. "Fork", "Compare", "Export", "Admin Tab actions" such as triggering Dream Cycle or activating a Blueprint).
  - `web`: no TUI-specific mechanic is mentioned.
- `tui_only` criteria are excluded entirely (not turned into `Gap_Item`s).
- `mixed` criteria produce one `Gap_Item` for the web-realizable portion only, with a note identifying the excluded TUI-only portion.
- `web` criteria produce one `Gap_Item` each.

### 2. Backend-Existence Verification

**Files inspected:**
- `contexta/db/schema.py` — table/column DDL
- `contexta/models/*.py` (`citations.py`, `enums.py`, `export.py`, `findings.py`, `payloads.py`, `proposal.py`) — data model fields
- `contexta/api/repositories.py` and `contexta/db/repositories.py` — data-access functions
- `contexta/api/schemas.py` — Pydantic request/response models

**Verification technique:** `grep_search` for the expected table name, column name, dataclass/function name, or Pydantic model name (e.g. `grep "review_links"` across `contexta/db/schema.py` and `contexta/api/repositories.py`). A match with a real implementation body (not a comment or TODO) counts as backend-existent.

### 3. API-Wiring Verification

**Files inspected:** `contexta/api/routers/*.py` (`admin.py`, `artifacts.py`, `insights.py`, `nodes.py`, `projects.py`, `proposals.py`, `reviews.py`, `versions.py`), plus router-registration in `contexta/api/app.py` (or equivalent entrypoint).

**Verification technique:**
- `grep_search` for the route decorator (`@router.post`, `@router.get`) matching the expected path (e.g. `/api/reviews`, `/api/versions/{version_id}/proposals`).
- Confirm the router module itself is `include_router`'d in the FastAPI app — a handler that exists in a router file but whose router is never registered counts as **not wired**, not as fully implemented.
- Cross-check that the handler body actually calls the backend function identified in step 2 (e.g. `insert_review_links`, `list_linkable_reviews`) rather than a stub.

### 4. UI-Rendering Verification

**Files inspected:** `web/pages/*.py` (`run_review.py`, `admin.py`), `web/components/*.py` (all 19 component files), `web/state.py`.

**Verification technique:**
- `grep_search` for the component's function/class name (e.g. `review_link_selector`, `proposal_form`, `proposals_list`) inside the page files (`run_review.py`, `admin.py`) and inside parent components (e.g. `version_detail.py`) that assemble the page. A component defined but never imported/called from a page or parent component counts as **not wired** even though it is backend/UI-complete in isolation.
- `grep_search` for the corresponding `AppState` handler name (e.g. `submit_review_with_links`, `fetch_proposals_for_version`) inside `web/state.py` to confirm the handler exists, and inside the component file to confirm the handler is actually bound to an `on_click` / `on_submit` event — not just declared.
- For data-visibility findings (Artifact_Labeling, Artifact_Traceability), additionally check whether the *field* itself (e.g. `tags`, `source_artifact`, `citation`) is referenced anywhere in the render body (`rx.text(...)`, `rx.foreach(...)`, etc.) of `ingestion_modal.py`, `triage_widget.py`, `version_detail.py`, `finding_card.py`.

### 5. Classification Procedure Component

Pure decision function applied to the evidence gathered above. See "Classification Decision Procedure" below.

### 6. Report Rendering Component

Assembles all `Gap_Item` records plus the fixed sections (Requirement 9) into `gap-analysis.md`.

## Data Models

These are conceptual records used to organize the audit's findings while writing the report — they are not persisted anywhere except as prose/table rows inside `gap-analysis.md`.

```python
# Conceptual shape only — used to organize report content, not implemented as running code.

class Evidence:
    backend_exists: bool          # table/model/repo-function/schema present
    api_wired: bool                # route registered AND router included AND calls real backend fn
    ui_rendered: bool               # component imported+called from a reachable page AND bound to a handler
    diverges_from_spec: bool        # realized via a different mechanism/scope boundary than Original_Scope_Document
    file_paths: list[str]           # every file path examined to produce this evidence
    notes: str                      # free-text reasoning

class GapItem:
    title: str
    functional_area: str            # e.g. "Review Linking", "Proposals", "Admin / Blueprints"
    requirement_ref: str             # e.g. "project-contexta Req 3.2" or "reported symptom: artifact labeling"
    status: Literal[
        "Not_Implemented",
        "Implemented_Not_Wired",
        "Implemented_Differently",
        "Fully_Implemented",
    ]
    evidence: Evidence
    reasoning: str                   # cites evidence.file_paths and specific constructs
```

## Classification Decision Procedure

Given an `Evidence` tuple `(backend_exists, api_wired, ui_rendered, diverges_from_spec)`, the classification is computed in this fixed priority order:

1. **`diverges_from_spec == true`** → `Implemented_Differently`, regardless of the other three flags (a divergent mechanism takes precedence over a wiring judgment, per Requirement 2.4).
2. Else **`backend_exists == false`** → `Not_Implemented` (no backend, API, or UI exists at all — Requirement 2.2). Note: if only the UI exists with no backend, this still resolves to `Not_Implemented`, since a UI with nothing behind it is not a real implementation of the scope item.
3. Else **`backend_exists == true` AND (`api_wired == false` OR `ui_rendered == false`)** → `Implemented_Not_Wired` (Requirement 2.3).
4. Else (**`backend_exists == true` AND `api_wired == true` AND `ui_rendered == true`**) → `Fully_Implemented` (Requirement 2.5).

This procedure is deterministic and total: every possible combination of the four booleans maps to exactly one of the four `Status_Classification` values, satisfying Requirement 2.1 (exactly one value per `Gap_Item`) and Requirement 2.6 (each classification traces back to concrete evidence booleans, each of which is itself backed by cited file paths).

Applied to the two originally-reported issues and two newly-reported symptoms specifically (using findings already gathered in prior investigation, to be re-confirmed during Tasks execution):

| Finding | backend_exists | api_wired | ui_rendered | diverges | → Status |
|---|---|---|---|---|---|
| Review_Linking_Finding | true (`review_links` table, `POST /api/reviews`, `GET /.../linkable`) | true | **false** (disabled `rx.cond` in `run_review.py`; `review_link_selector.py` unused) | false | `Implemented_Not_Wired` |
| Project_Scoped_Proposal_Finding | true | true (but version-scoped, not project-scoped) | false (`proposal_form.py`/`proposals_list()` not imported in `version_detail.py`) | **true** (per-version instead of per-project scoping) | `Implemented_Differently` (with `Implemented_Not_Wired` UI factor noted) |
| Artifact_Labeling_Finding | true (tags persisted) | true (returned by API) | **to be determined per surface** — checked independently for `ingestion_modal.py`, `triage_widget.py`, `version_detail.py` | false | `Implemented_Not_Wired` for any surface where render is absent; `Fully_Implemented` (with a runtime-verification caveat) if all surfaces render it |
| Artifact_Traceability_Finding | true (`SourceCitation.file_path`, `FindingItem.source_artifact/citation`) | true (present in `FindingItem`) | **plain text only, no navigation** in `finding_card.py` | to be determined — navigable-reference vs label distinction | `Not_Implemented` or `Implemented_Differently` per Requirement 5.4, distinguishing "citation text shown" from "citation is a navigable reference" |

The Tasks phase re-runs the actual file inspection to confirm or correct every cell in this table before it is transcribed into `gap-analysis.md` — the table above is the design-time hypothesis carried forward from prior investigation, not the final report content.

## Audit Report Structure (`gap-analysis.md`)

Written to `.kiro/specs/review-implementation-gaps/gap-analysis.md`. Section order:

```markdown
# Contexta Implementation Gap Analysis

## (a) TL;DR — Originally Reported Issues
- Review Linking: <status> — one-paragraph summary + link to full finding below
- Project-Scoped Proposals: <status> — one-paragraph summary + link to full finding below

## (b) Newly Reported Symptoms
- Artifact Labeling Not Visible: <status> — one-paragraph summary
- Missing Artifact Traceability: <status> — one-paragraph summary

## (c) Full Scope Findings (by Functional Area)
### Review Linking & Prior Intelligence
  - Gap_Item: ... | Status | Reasoning (file paths) | Requirement ref
### Proposals & Synthesis
  ...
### Fork / Node Branching
### Scope Policy & Routing Decisions
### JSON Export
### JSON Import
### Dream Cycle
### Blueprint Management
### Global Client Insights Sidebar
### Artifact Ingestion, Labeling & Triage
### Artifact Traceability / Citations
### Projects, Versions & Navigation
(One subsection per non-TUI functional area derived from project-contexta Requirements 1–14; each lists every Gap_Item with title, Status_Classification, reasoning citing file paths, and originating requirement number.)

## (d) Re-verification of the 11 Core_Gaps_Spec Items
| # | Gap (from core-scope-gaps-implementation) | Prior Status (tasks.md) | Current Status (this audit) | Changed? | Evidence |
|---|---|---|---|---|---|
| 1 | Review Linking | unchecked / not implemented | ... | ... | ... |
| 2 | Proposal Re-Architecture | unchecked | ... | | |
| 3 | Fork Iteration | unchecked | | | |
| 4 | Proactive Advisor | unchecked | | | |
| 5 | Scope Policy UI | unchecked | | | |
| 6 | JSON Export | unchecked | | | |
| 7 | JSON Import | unchecked | | | |
| 8 | Dream Cycle | unchecked | | | |
| 9 | Blueprint Management | unchecked | | | |
| 10 | Insights Sidebar | unchecked | | | |
| 11 | Version-Level Proposal Listing | unchecked | | | |

## (e) Tracking_Gap
Notes the mismatch between `core-scope-gaps-implementation/tasks.md` (all boxes unchecked) and the
current code evidence gathered in section (d); lists exactly which task IDs are inconsistent.

## (f) Scripts_Markdown_Note
States that `/scripts` contains no markdown files, and lists its actual contents
(`dev-start.sh`, `healthcheck.sh`, `init_db.py`).
```

Each `Gap_Item` row/entry in section (c) and each row in section (d) always includes: title, `Status_Classification`, reasoning with cited file paths/constructs, and a reference back to the originating `project-contexta` requirement number or reported symptom name — satisfying Requirement 9.2.

## Error Handling

Since this is a read-only static-analysis task, "errors" are investigation-process failure modes rather than runtime exceptions:

| Situation | Handling |
|---|---|
| A referenced file (e.g. a path from prior investigation) no longer exists or was renamed | Note this explicitly in the `Gap_Item`'s reasoning rather than silently skipping the item; re-derive the finding from the current file if a renamed equivalent is found via `file_search`/`grep_search`. |
| A grep/search finds no match for an expected construct | Treat as evidence of `backend_exists=false` (or `api_wired=false` / `ui_rendered=false` as appropriate) rather than as a tool failure — record the negative search as part of the reasoning. |
| An Original_Scope_Document acceptance criterion is ambiguous about TUI-only vs mixed | Default to `mixed` (include the web-realizable portion) rather than dropping the item, per Requirement 1.3's bias toward not silently excluding scope. |
| Static inspection cannot resolve whether a UI surface renders correctly at runtime (e.g. conditional rendering logic that can't be fully traced statically) | State this explicitly and flag it as requiring runtime/browser verification, per Requirement 4.4, rather than guessing a classification. |
| No markdown files found in `/scripts` | Record as the fixed `Scripts_Markdown_Note` per Requirement 8.1 — this is an expected, not exceptional, outcome. |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — here, "executions" means all possible evidence inputs to the classification procedure, and all possible Gap_Item records that end up in the produced report, rather than repeated runs of a live program.*

### Property 1: Classification is total and deterministic

For any `Evidence` tuple `(backend_exists, api_wired, ui_rendered, diverges_from_spec)` of four booleans, applying the Classification Decision Procedure SHALL always terminate and SHALL always return exactly one of the four values `{Not_Implemented, Implemented_Not_Wired, Implemented_Differently, Fully_Implemented}` — never zero and never more than one — and applying the procedure twice to the same tuple SHALL always yield the same result.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

### Property 2: Divergence takes precedence over wiring state

For any `Evidence` tuple where `diverges_from_spec == true`, the Classification Decision Procedure SHALL return `Implemented_Differently` regardless of the values of `backend_exists`, `api_wired`, or `ui_rendered`.

**Validates: Requirements 2.4**

### Property 3: Absence of backend implies Not_Implemented

For any `Evidence` tuple where `diverges_from_spec == false` and `backend_exists == false`, the Classification Decision Procedure SHALL return `Not_Implemented`, regardless of the values of `api_wired` and `ui_rendered`.

**Validates: Requirements 2.2**

### Property 4: Backend presence with incomplete wiring implies Implemented_Not_Wired

For any `Evidence` tuple where `diverges_from_spec == false`, `backend_exists == true`, and at least one of `api_wired` or `ui_rendered` is `false`, the Classification Decision Procedure SHALL return `Implemented_Not_Wired`.

**Validates: Requirements 2.3**

### Property 5: Full wiring implies Fully_Implemented

For any `Evidence` tuple where `diverges_from_spec == false`, `backend_exists == true`, `api_wired == true`, and `ui_rendered == true`, the Classification Decision Procedure SHALL return `Fully_Implemented`.

**Validates: Requirements 2.5**

### Property 6: Every Gap_Item in the report has exactly one valid status and non-empty cited reasoning

For any `Gap_Item` entry appearing anywhere in the produced `gap-analysis.md` (sections (c) and (d)), that entry's `status` field SHALL be exactly one of the four defined `Status_Classification` values, and its reasoning text SHALL be non-empty and SHALL contain at least one file-path-like token drawn from `evidence.file_paths`.

**Validates: Requirements 2.1, 2.6, 9.2**

### Property 7: Scope filtering is a total, consistent classification over criteria

For any acceptance criterion drawn from `project-contexta` Requirements 1–14, applying the Web_Scope filter rule SHALL classify it into exactly one of `{tui_only, mixed, web}`, `tui_only` criteria SHALL never produce a `Gap_Item`, and `mixed`/`web` criteria SHALL always produce exactly one `Gap_Item` each, with `mixed` criteria's `Gap_Item` additionally carrying a note identifying the excluded TUI-only portion.

**Validates: Requirements 1.1, 1.2, 1.3**

## Testing Strategy

This feature produces a single markdown document, not executable application code, so there is no unit-test or property-test *suite* to add to the repository. Verification instead takes two forms during Tasks execution:

- **Procedural verification (unit/example-style, performed manually during the audit):** For each of the fixed, non-varying checklist items — the 11 Core_Gaps_Spec re-verifications (Requirement 6), the four named findings (Requirements 3–5), the Tracking_Gap cross-reference (Requirement 7), and the Scripts_Markdown_Note (Requirement 8) — confirm the specific cited file/construct exists (or does not) by direct inspection, and confirm the corresponding section is present in `gap-analysis.md` before the report is considered complete.
- **Property-style self-check (applied by reasoning, not by an automated test runner, since there is no source module implementing the classification function):** Before finalizing `gap-analysis.md`, walk every `Gap_Item` against Properties 1–6 above — i.e., confirm every assigned status follows deterministically from its own stated evidence booleans per the decision table, and confirm every entry carries a non-empty, file-path-citing reasoning string. Any entry that fails this self-check is corrected before the report is finalized.
- **Read-only guarantee check:** After producing `gap-analysis.md`, confirm no other file in the repository was modified (e.g. via `git status`), satisfying Requirement 9.6.
