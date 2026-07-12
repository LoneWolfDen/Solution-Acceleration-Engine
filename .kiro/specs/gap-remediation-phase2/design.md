# Design Document

## Architecture / Track Isolation

Three tracks, disjoint file ownership so parallel agents don't conflict:

| Track | Owns (write access) | Reads only |
|---|---|---|
| A — Backend | `contexta/db/schema.py`, `contexta/api/repositories.py`, `contexta/api/schemas.py`, `contexta/api/routers/proposals.py`, `contexta/api/routers/reviews.py`, `contexta/api/routers/artifacts.py`, new `tests/api/test_*` | — |
| B — Frontend views | `web/components/version_detail.py`, `web/components/review_detail.py` | `web/state.py` (no edits), Track A schema field names |
| C — Frontend state | `web/pages/run_review.py`, `web/components/sidebar.py`, `web/components/finding_card.py`, `web/web.py`, `web/state.py` | Track A response field names |

Track B and C both touch different files, so they can run fully in parallel with A. B depends on A's new response fields (`line_count`, `content_preview`, `citations[]`) only for full correctness, but can be implemented and reviewed against A's `requirements.md` contract without waiting for A to merge, since the fields are additive to existing schemas (no breaking renames).

## Key Design Decision: Proposal Scope (Requirement A1)

The gap-analysis report labeled version-scoped proposals `Implemented_Differently` relative to the user's original expectation. However, re-inspection during this planning phase found:
- `contexta/api/routers/proposals.py`'s version scoping is intentional, documented, tested (`tests/api/test_proposals.py`), and is the shipped Gap 2/11 implementation from `core-scope-gaps-implementation`.
- The data hierarchy in `contexta/db/schema.py` is explicitly `Project → Version → Node/Artifact → Review → Proposal`.

Removing the `WHERE rj.version_id = ?` guard would be a regression, not a fix — it would let proposals reference reviews from unrelated versions with no validation. Instead, Requirement A1 adds a new, additive `GET /api/projects/{project_id}/proposals` endpoint that aggregates read-only across versions, leaving the existing guarded endpoints untouched. This satisfies "genuine project-wide listing" without weakening validation.

## Data Model Additions (Track A)

```sql
-- v6 -> v7
ALTER TABLE artifacts ADD COLUMN line_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE artifacts ADD COLUMN content_preview TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS review_job_artifact_snapshots (
    review_job_id TEXT NOT NULL REFERENCES review_jobs(id),
    artifact_id   TEXT NOT NULL REFERENCES artifacts(id),
    PRIMARY KEY (review_job_id, artifact_id)
);
```

Migration backfills `line_count`/`content_preview` for existing rows from stored `content` (idempotent, safe to re-run).

## Error Handling

| Situation | Handling |
|---|---|
| Project has no versions (A1) | Return empty `proposals: []`, HTTP 200 |
| Version has zero active artifacts at review creation (A2) | Empty snapshot row set is valid, not an error |
| Finding has zero citations (A5) | `citations: []`, `source_artifact`/`citation` keep current fallback values |
| Citation click resolves to no artifact (C3) | Toast, no navigation/state change |
| Reflex `list[dict]` typing error still reproduces after C1 fix | Follow `triage_widget.py`'s established bracket-notation + `.to(list[str])` pattern rather than inventing a new one |

## Testing Strategy

- Track A: property/unit tests under `tests/api/` for each new/changed endpoint, plus a schema migration test verifying idempotency and backfill correctness.
- Track B: component-level smoke tests are not part of Reflex's typical test surface in this repo (no existing precedent in `tests/ui/`); verification is via `reflex run` manual check plus confirming imports resolve (`python -c "import web.web"`).
- Track C: same as B, plus a targeted unit test for `AppState.navigate_to_artifact` resolution logic (pure Python, testable without a running Reflex app).
