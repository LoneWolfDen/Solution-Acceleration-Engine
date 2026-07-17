# API PLAYBOOK

This document lists all active FastAPI endpoints in the contexta application, organized by HTTP method and URL path.

## Projects Endpoints

### GET /api/projects
- **Description**: List all projects with version/review counts
- **Database Table**: projects

### POST /api/projects
- **Description**: Create a new project
- **Database Table**: projects

### GET /api/projects/{project_id}
- **Description**: Project detail with versions and nodes
- **Database Table**: projects, versions, nodes

### DELETE /api/projects/{project_id}
- **Description**: Cascade-delete a project
- **Database Table**: projects, versions, nodes, artifacts, reviews, proposals, nodes

## Versions Endpoints

### GET /api/projects/{project_id}/versions
- **Description**: List versions for a project
- **Database Table**: versions

### GET /api/versions/{version_id}
- **Description**: Version detail + linked artifacts
- **Database Table**: versions, artifacts

### POST /api/versions
- **Description**: Create version and link artifacts
- **Database Table**: versions, version_artifact_links

## Artifacts Endpoints

### GET /api/projects/{project_id}/artifacts
- **Description**: List artifacts (with is_active)
- **Database Table**: artifacts

### POST /api/artifacts
- **Description**: Ingest upload / paste / url
- **Database Table**: artifacts

### PATCH /api/artifacts/{artifact_id}
- **Description**: Toggle is_active
- **Database Table**: artifacts

### DELETE /api/artifacts/{artifact_id}
- **Description**: Hard delete
- **Database Table**: artifacts

### GET /api/artifacts/suggestions
- **Description**: Regex-based tag hints (no LLM)
- **Database Table**: None (computed from filename/content)

## Proposals Endpoints

### POST /api/versions/{version_id}/proposals
- **Description**: Multi-review proposal creation
- **Database Table**: proposal_jobs, proposal_review_links

### GET /api/versions/{version_id}/proposals
- **Description**: List proposals for a version
- **Database Table**: proposal_jobs

### GET /api/projects/{project_id}/proposals
- **Description**: List proposals for all versions in a project
- **Database Table**: proposal_jobs

### POST /api/proposals
- **Description**: Legacy single-review proposal creation
- **Database Table**: proposal_jobs, proposal_review_links

### GET /api/proposals/{proposal_id}/status
- **Description**: Poll async status; returns report + alerts
- **Database Table**: proposal_jobs

### POST /api/proposals/{proposal_id}/acknowledge
- **Description**: Record advisor acknowledgement + resume
- **Database Table**: proposal_jobs

## Reviews Endpoints

### GET /api/versions/{version_id}/reviews
- **Description**: List review jobs for a version
- **Database Table**: review_jobs

### GET /api/nodes/{node_id}
- **Description**: Full Review_Payload for a review job
- **Database Table**: review_jobs, nodes

### POST /api/reviews
- **Description**: Trigger the real 12-dimension pipeline
- **Database Table**: review_jobs

### GET /api/reviews/{review_id}/status
- **Description**: Poll async status
- **Database Table**: review_jobs

### GET /api/versions/{version_id}/reviews/linkable
- **Description**: List completed reviews eligible for linking
- **Database Table**: review_jobs

### GET /api/reviews/{review_id}/artifacts
- **Description**: Return artifact set frozen at review creation time
- **Database Table**: review_jobs, review_job_artifact_snapshots

## Admin Endpoints

### GET /api/admin/health
- **Description**: Provider connectivity status + last run
- **Database Table**: review_jobs, config

### GET /api/admin/config
- **Description**: Current config (keys masked, never raw)
- **Database Table**: config

### POST /api/admin/config
- **Description**: Save one config field
- **Database Table**: config

### POST /api/admin/import
- **Description**: Multipart file upload → JSONPacket validation + DB write
- **Database Table**: projects, nodes, artifacts, versions, review_jobs, proposal_jobs

### POST /api/admin/dream-cycle
- **Description**: Launch background worker
- **Database Table**: None (background task)

### GET /api/admin/dream-cycle/status
- **Description**: Current state, last_run timestamp, error
- **Database Table**: None (in-memory state)

### GET /api/admin/blueprints
- **Description**: List all blueprints (with prompt preview)
- **Database Table**: blueprints

### POST /api/admin/blueprints
- **Description**: Create new blueprint (inactive by default)
- **Database Table**: blueprints

### POST /api/admin/blueprints/{id}/activate
- **Description**: Set one blueprint active, all others inactive
- **Database Table**: blueprints

## Insights Endpoints

### GET /api/insights
- **Description**: Return top advisory hints from global_client_insights
- **Database Table**: global_client_insights

## Nodes Endpoints

### POST /api/nodes/{node_id}/fork
- **Description**: Branch a node into a fork
- **Database Table**: nodes

### POST /api/nodes/{node_id}/routing-decision
- **Description**: Record scope routing choice
- **Database Table**: nodes

### GET /api/nodes/{node_id}/export
- **Description**: Download node as JSONPacket
- **Database Table**: nodes