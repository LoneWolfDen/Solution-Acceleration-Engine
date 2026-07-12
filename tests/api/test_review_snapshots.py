"""tests/api/test_review_snapshots.py — Review-run artifact snapshot provenance.

Covers Requirement A2:
  - Creating a review job snapshots the version's currently-active artifacts.
  - GET /reviews/{review_id}/artifacts returns exactly the active artifacts
    at creation time.
  - Later deactivating an artifact does NOT retroactively change the snapshot
    (immutability).
  - Zero-active-artifact case returns an empty list without error.
"""

from __future__ import annotations

import json


def _create_artifact(client, project_id, title, active=True):
    resp = client.post(
        "/api/artifacts",
        data={
            "project_id": project_id,
            "title": title,
            "source": "paste",
            "content": f"content for {title}",
            "tags": "[]",
        },
    )
    artifact_id = resp.json()["artifact_id"]
    if not active:
        client.patch(f"/api/artifacts/{artifact_id}", json={"active": False})
    return artifact_id


def test_snapshot_captures_only_active_artifacts_at_review_creation(
    test_app, project_id
):
    active_1 = _create_artifact(test_app, project_id, "Active One")
    active_2 = _create_artifact(test_app, project_id, "Active Two")
    inactive_1 = _create_artifact(test_app, project_id, "Inactive One", active=False)

    version_id = test_app.post(
        "/api/versions",
        json={
            "project_id": project_id,
            "version_name": "v-snap",
            "artifact_ids": [active_1, active_2, inactive_1],
        },
    ).json()["version_id"]

    review_id = test_app.post(
        "/api/reviews",
        json={"version_id": version_id, "persona_roles": ["Architect"], "context": ""},
    ).json()["review_id"]

    resp = test_app.get(f"/api/reviews/{review_id}/artifacts")
    assert resp.status_code == 200
    snapshot_ids = {a["artifact_id"] for a in resp.json()["artifacts"]}
    assert snapshot_ids == {active_1, active_2}


def test_snapshot_is_immutable_against_later_deactivation(test_app, project_id):
    active_1 = _create_artifact(test_app, project_id, "Will Deactivate")
    active_2 = _create_artifact(test_app, project_id, "Stays Active")

    version_id = test_app.post(
        "/api/versions",
        json={
            "project_id": project_id,
            "version_name": "v-immutable",
            "artifact_ids": [active_1, active_2],
        },
    ).json()["version_id"]

    review_id = test_app.post(
        "/api/reviews",
        json={"version_id": version_id, "persona_roles": ["Architect"], "context": ""},
    ).json()["review_id"]

    # Original snapshot should show both active artifacts.
    original_ids = {
        a["artifact_id"]
        for a in test_app.get(f"/api/reviews/{review_id}/artifacts").json()["artifacts"]
    }
    assert original_ids == {active_1, active_2}

    # Deactivate one of the originally-active artifacts after the fact.
    test_app.patch(f"/api/artifacts/{active_1}", json={"active": False})

    # Snapshot should still show the original 2 — proving immutability.
    refetched_ids = {
        a["artifact_id"]
        for a in test_app.get(f"/api/reviews/{review_id}/artifacts").json()["artifacts"]
    }
    assert refetched_ids == {active_1, active_2}


def test_snapshot_empty_when_zero_active_artifacts(test_app, project_id):
    inactive_1 = _create_artifact(test_app, project_id, "Only Inactive", active=False)

    version_id = test_app.post(
        "/api/versions",
        json={
            "project_id": project_id,
            "version_name": "v-empty-snap",
            "artifact_ids": [inactive_1],
        },
    ).json()["version_id"]

    review_id = test_app.post(
        "/api/reviews",
        json={"version_id": version_id, "persona_roles": ["Architect"], "context": ""},
    ).json()["review_id"]

    resp = test_app.get(f"/api/reviews/{review_id}/artifacts")
    assert resp.status_code == 200
    assert resp.json()["artifacts"] == []
    assert resp.json()["error"] is None


def test_snapshot_unknown_review_returns_404(test_app):
    resp = test_app.get("/api/reviews/no-such-review/artifacts")
    assert resp.status_code == 404
    assert resp.json()["error"] is not None
