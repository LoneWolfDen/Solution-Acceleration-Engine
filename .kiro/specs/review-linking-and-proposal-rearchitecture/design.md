# Design Document: Review Linking & Proposal Re-Architecture

## Architecture Overview

This feature introduces two junction tables and associated API/pipeline changes that extend Project Contexta's review and proposal subsystems from single-entity relationships to many-to-many associations. The architecture preserves backward compatibility while enabling multi-review context injection and multi-review proposal synthesis.

### High-Level Data Flow

```
┌─────────────┐     ┌──────────────┐     ┌───────────────────┐
│ Run Review  │────▶│ review_links │────▶│ Pipeline: Load    │
│ (with links)│     │ (junction)   │     │ Prior Intelligence│
└─────────────┘     └──────────────┘     └───────────────────┘
                                                   │
                                                   ▼
                                          ┌───────────────────┐
                                          │ LLM Prompt with   │
                                          │ Prior Review Intel │
                                          └───────────────────┘

┌─────────────────┐  ┌─────────────────────┐  ┌──────────────────┐
│ Generate        │─▶│ proposal_review_links│─▶│ Pipeline: Multi- │
│ Proposal (multi)│  │ (junction)           │  │ Review Synthesis  │
└─────────────────┘  └─────────────────────┘  └──────────────────┘
```

## Components

### 1. Database Schema (contexta/db/schema.py)

**SCHEMA_VERSION**: Incremented from 5 → 6.

#### New Tables

```python
# review_links — many-to-many: which prior reviews are linked to a new review
"""
CREATE TABLE IF NOT EXISTS review_links (
    review_id        TEXT NOT NULL REFERENCES review_jobs(id),
    linked_review_id TEXT NOT NULL REFERENCES review_jobs(id),
    PRIMARY KEY (review_id, linked_review_id),
    CHECK (review_id != linked_review_id)
)
"""

# proposal_review_links — many-to-many: which reviews feed a proposal
"""
CREATE TABLE IF NOT EXISTS proposal_review_links (
    proposal_id TEXT NOT NULL REFERENCES proposal_jobs(id),
    review_id   TEXT NOT NULL REFERENCES review_jobs(id),
    PRIMARY KEY (proposal_id, review_id)
)
"""
```

#### Migration Logic (v5 → v6)

```python
# Inside run_migrations(), after DDL execution:
if stored_version < 6:
    # Migrate existing proposal_jobs.review_job_id → proposal_review_links
    await conn.execute("""
        INSERT OR IGNORE INTO proposal_review_links (proposal_id, review_id)
        SELECT id, review_job_id FROM proposal_jobs
        WHERE review_job_id IS NOT NULL
    """)
```

The `INSERT OR IGNORE` ensures idempotent re-runs. The `review_job_id` column on `proposal_jobs` is retained for backward compatibility.

