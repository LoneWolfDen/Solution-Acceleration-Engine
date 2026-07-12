"""tests/api/test_reviews.py — Review job lifecycle."""

import pytest


def _setup_version(client, project_id):
    aid = client.post(
        "/api/artifacts",
        data={"project_id": project_id, "title": "Rev Art", "source": "paste", "content": "content", "tags": "[]"},
    ).json()["artifact_id"]
    return client.post(
        "/api/versions", json={"project_id": project_id, "version_name": "v1", "artifact_ids": [aid]}
    ).json()["version_id"]


def test_create_review_returns_queued(test_app, project_id):
    ver_id = _setup_version(test_app, project_id)
    resp = test_app.post("/api/reviews", json={"version_id": ver_id, "persona_roles": ["Architect"], "context": ""})
    assert resp.status_code == 202
    data = resp.json()
    assert "review_id" in data
    assert data["status"] == "queued"
    assert data.get("error") is None


def test_get_review_status_valid_enum(test_app, project_id):
    ver_id = _setup_version(test_app, project_id)
    review_id = test_app.post(
        "/api/reviews", json={"version_id": ver_id, "persona_roles": ["PM"], "context": ""}
    ).json()["review_id"]
    resp = test_app.get(f"/api/reviews/{review_id}/status")
    assert resp.status_code == 200
    assert resp.json()["status"] in {"queued", "running", "complete", "failed"}


def test_get_review_payload_from_node(test_app, project_id):
    ver_id = _setup_version(test_app, project_id)
    review_id = test_app.post(
        "/api/reviews", json={"version_id": ver_id, "persona_roles": ["PM"], "context": ""}
    ).json()["review_id"]
    resp = test_app.get(f"/api/nodes/{review_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "review_id" in data
    assert isinstance(data["findings"], list)
    assert data.get("error") is None


def test_get_node_unknown_returns_404(test_app):
    resp = test_app.get("/api/nodes/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"] is not None


def test_list_reviews_for_version(test_app, project_id):
    ver_id = _setup_version(test_app, project_id)
    test_app.post("/api/reviews", json={"version_id": ver_id, "persona_roles": ["Architect"], "context": ""})
    resp = test_app.get(f"/api/versions/{ver_id}/reviews")
    assert resp.status_code == 200
    data = resp.json()
    assert "reviews" in data
    r = data["reviews"][0]
    assert "review_id" in r and "status" in r and "persona" in r


# ── Requirement A4/A5: 12-axis dimension fidelity + full citation array ──────


def _dimension_payload_dict(dimension: str, num_citations: int = 1) -> dict:
    """Build a single dimension's metadata dict (ReviewNodePayload shape)
    with `num_citations` SourceCitation entries on its one finding."""
    citations = [
        {
            "file_path": f"/docs/{dimension.lower()}_{i}.md",
            "line_start": i + 1,
            "line_end": i + 5,
            "citation_type": "Direct Reference",
            "excerpt": f"excerpt {i} for {dimension}",
        }
        for i in range(num_citations)
    ]
    return {
        "dimension": dimension,
        "overall_confidence": "AMBER",
        "findings": [
            {
                "dimension": dimension,
                "confidence": "AMBER",
                "summary": f"{dimension} finding",
                "detail": f"Detail for {dimension}",
                "citations": citations,
                "mitigation_routing": "Risk Register",
            }
        ],
        "base_findings": [],
        "user_annotations": [],
        "raw_llm_response": "{}",
    }


def test_all_12_dimension_values_round_trip_on_finding_type(test_app, project_id, event_loop):
    """FindingItem.type returns the exact original ReviewDimensionEnum value
    for all 12 axes, not a collapsed 5-bucket category."""
    from contexta.api import repositories as api_repo
    from contexta.db import repositories as db_repo
    from contexta.models.enums import ReviewDimensionEnum
    from contexta.models.payloads import ReviewNodePayload

    ver_id = _setup_version(test_app, project_id)
    review_id = test_app.post(
        "/api/reviews", json={"version_id": ver_id, "persona_roles": ["PM"], "context": ""}
    ).json()["review_id"]

    all_dims = [d.value for d in ReviewDimensionEnum]
    assert len(all_dims) == 12
    dim_dicts = [_dimension_payload_dict(d) for d in all_dims]

    conn = test_app.app.state.db

    async def _write_and_link():
        first_payload = ReviewNodePayload.model_validate(dim_dicts[0])
        node = await db_repo.write_node(
            conn,
            project_id=project_id,
            parent_id=None,
            layer_type="exploration",
            node_name="12-dim test node",
            payload=first_payload,
            metadata={"dimensions": dim_dicts},
            version_id=ver_id,
        )
        await api_repo.update_review_job_status(
            conn, review_id, status="complete", node_id=node.id
        )

    event_loop.run_until_complete(_write_and_link())

    resp = test_app.get(f"/api/nodes/{review_id}")
    assert resp.status_code == 200
    data = resp.json()
    finding_types = {f["type"] for f in data["findings"]}
    assert finding_types == set(all_dims)

    # summary counts (5-bucket) still sum correctly to the total finding count.
    summary = data["summary"]
    total = sum(summary.values())
    assert total == len(data["findings"]) == 12


def test_finding_citations_array_has_all_entries_while_legacy_fields_keep_first(
    test_app, project_id, event_loop
):
    """A finding with 3 citations exposes all 3 in `citations`, while the
    legacy `citation`/`source_artifact` fields reflect only the first."""
    from contexta.api import repositories as api_repo
    from contexta.db import repositories as db_repo
    from contexta.models.payloads import ReviewNodePayload

    ver_id = _setup_version(test_app, project_id)
    review_id = test_app.post(
        "/api/reviews", json={"version_id": ver_id, "persona_roles": ["PM"], "context": ""}
    ).json()["review_id"]

    dim_dict = _dimension_payload_dict("Risk", num_citations=3)
    conn = test_app.app.state.db

    async def _write_and_link():
        payload = ReviewNodePayload.model_validate(dim_dict)
        node = await db_repo.write_node(
            conn,
            project_id=project_id,
            parent_id=None,
            layer_type="exploration",
            node_name="citation test node",
            payload=payload,
            metadata={"dimensions": [dim_dict]},
            version_id=ver_id,
        )
        await api_repo.update_review_job_status(
            conn, review_id, status="complete", node_id=node.id
        )

    event_loop.run_until_complete(_write_and_link())

    resp = test_app.get(f"/api/nodes/{review_id}")
    data = resp.json()
    finding = data["findings"][0]

    assert len(finding["citations"]) == 3
    assert finding["source_artifact"] == finding["citations"][0]["file_path"]
    assert finding["citation"] == finding["citations"][0]["excerpt"]


def test_finding_zero_citations_falls_back_to_defaults(test_app, project_id, event_loop):
    """A finding with zero citations returns citations=[] and default
    source_artifact/citation values."""
    from contexta.api import repositories as api_repo
    from contexta.db import repositories as db_repo
    from contexta.models.payloads import ReviewNodePayload

    ver_id = _setup_version(test_app, project_id)
    review_id = test_app.post(
        "/api/reviews", json={"version_id": ver_id, "persona_roles": ["PM"], "context": ""}
    ).json()["review_id"]

    dim_dict = _dimension_payload_dict("Risk", num_citations=0)
    conn = test_app.app.state.db

    async def _write_and_link():
        payload = ReviewNodePayload.model_validate(dim_dict)
        node = await db_repo.write_node(
            conn,
            project_id=project_id,
            parent_id=None,
            layer_type="exploration",
            node_name="no-citation test node",
            payload=payload,
            metadata={"dimensions": [dim_dict]},
            version_id=ver_id,
        )
        await api_repo.update_review_job_status(
            conn, review_id, status="complete", node_id=node.id
        )

    event_loop.run_until_complete(_write_and_link())

    resp = test_app.get(f"/api/nodes/{review_id}")
    data = resp.json()
    finding = data["findings"][0]

    assert finding["citations"] == []
    assert finding["source_artifact"] == "unknown"
    assert finding["citation"] == ""
