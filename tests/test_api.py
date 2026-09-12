"""API tests via TestClient with the in-memory fake DB (dev auth header)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app

DEV = {"X-Dev-User": "00000000-0000-4000-8000-00000000aa01"}
GEOJSON = {
    "type": "MultiPolygon",
    "coordinates": [[[
        [12.40, 41.80], [12.50, 41.80], [12.50, 41.90],
        [12.40, 41.90], [12.40, 41.80],
    ]]],
}
BAD_GEOJSON = {
    "type": "Polygon",
    "coordinates": [[
        [0.0, 0.0], [2.0, 2.0], [2.0, 0.0], [0.0, 2.0], [0.0, 0.0],  # self-intersecting bowtie
    ]],
}


@pytest.fixture
def client(fake_db):
    """TestClient bound to the app with patched backend.db."""
    return TestClient(app)


def test_health(client):
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["protocol_version"] == "sih26142_v1"


def test_requires_auth(client):
    resp = client.get("/v1/projects")
    assert resp.status_code in (401, 403)
    assert resp.json()["error"]["code"] == "AUTH_FORBIDDEN"


def test_project_create_and_list(client):
    resp = client.post("/v1/projects", json={"name": "P1"}, headers=DEV)
    assert resp.status_code == 201
    pid = resp.json()["id"]
    assert resp.json()["default_crs"] == "EPSG:4326"

    resp = client.get("/v1/projects", headers=DEV)
    assert resp.status_code == 200
    assert any(p["id"] == pid for p in resp.json())


def test_aoi_create_valid_and_invalid(client):
    resp = client.post("/v1/projects", json={"name": "P2"}, headers=DEV)
    pid = resp.json()["id"]

    ok = client.post("/v1/aois", json={
        "project_id": pid, "name": "rome", "geometry": GEOJSON}, headers=DEV)
    assert ok.status_code == 201
    body = ok.json()
    assert body["area_m2"] > 0
    assert body["bbox"] == [12.40, 41.80, 12.50, 41.90]

    bad = client.post("/v1/aois", json={
        "project_id": pid, "name": "bowtie", "geometry": BAD_GEOJSON}, headers=DEV)
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "INVALID_AOI"

    listed = client.get(f"/v1/aois?project_id={pid}", headers=DEV)
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_job_idempotency(client, fake_db):
    resp = client.post("/v1/projects", json={"name": "P3"}, headers=DEV)
    pid = resp.json()["id"]

    body = {"project_id": pid, "scene_ids": [], "mode": "reconstruct_validate",
            "model": "custom_mf_sr", "idempotency_key": "run-42"}
    first = client.post("/v1/jobs", json=body, headers=DEV)
    assert first.status_code == 201
    job_id = first.json()["id"]
    assert len(first.json()["steps"]) == 5
    assert all(s["status"] == "QUEUED" for s in first.json()["steps"])

    second = client.post("/v1/jobs", json=body, headers=DEV)
    assert second.status_code == 200          # idempotent reuse, not duplicate
    assert second.json()["id"] == job_id

    fake_db.jobs[job_id]["status"] = "FAILED"  # simulate terminal failure
    third = client.post("/v1/jobs", json=body, headers=DEV)
    assert third.status_code == 201          # fresh attempt after failure
    assert third.json()["id"] != job_id


def test_job_get_and_cancel(client):
    resp = client.post("/v1/projects", json={"name": "P4"}, headers=DEV)
    pid = resp.json()["id"]
    job = client.post("/v1/jobs", json={
        "project_id": pid, "scene_ids": [], "mode": "reconstruct",
        "model": "bicubic_4x", "idempotency_key": "run-7"}, headers=DEV).json()

    got = client.get(f"/v1/jobs/{job['id']}", headers=DEV)
    assert got.status_code == 200
    assert got.json()["status"] == "QUEUED"
    assert got.json()["steps"][0]["name"] in ("preprocess", "reconstruct", "uncertainty",
                                              "validate", "report")

    cancel = client.post(f"/v1/jobs/{job['id']}/cancel", headers=DEV)
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"

    again = client.post(f"/v1/jobs/{job['id']}/cancel", headers=DEV)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "JOB_CONFLICT"


def test_validation_requires_evidence(client, fake_db):
    pid = client.post("/v1/projects", json={"name": "P5"}, headers=DEV).json()["id"]
    job = client.post("/v1/jobs", json={
        "project_id": pid, "scene_ids": [], "mode": "reconstruct",
        "model": "bicubic_4x", "idempotency_key": "run-ev"}, headers=DEV).json()
    fake_db.jobs[job["id"]]["status"] = "COMPLETED"
    resp = client.post("/v1/validations", json={"job_id": job["id"]}, headers=DEV)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_INCOMPLETE"


def test_validation_requires_completed_source(client, fake_db):
    pid = client.post("/v1/projects", json={"name": "P5b"}, headers=DEV).json()["id"]
    job = client.post("/v1/jobs", json={
        "project_id": pid, "scene_ids": [], "mode": "reconstruct",
        "model": "bicubic_4x", "idempotency_key": "run-evq"}, headers=DEV).json()
    for atype in ("sr_output", "uncertainty", "observation"):
        aid = f"q-{job['id']}-{atype}"
        fake_db.artifacts[aid] = {"id": aid, "job_id": job["id"],
                                  "artifact_type": atype, "storage_bucket": "b",
                                  "object_key": f"k/{atype}"}
    resp = client.post("/v1/validations", json={"job_id": job["id"]}, headers=DEV)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_INCOMPLETE"


def test_validation_rejects_unknown_reference(client, fake_db):
    pid = client.post("/v1/projects", json={"name": "P5c"}, headers=DEV).json()["id"]
    job = client.post("/v1/jobs", json={
        "project_id": pid, "scene_ids": [], "mode": "reconstruct",
        "model": "bicubic_4x", "idempotency_key": "run-evr"}, headers=DEV).json()
    fake_db.jobs[job["id"]]["status"] = "COMPLETED"
    for atype in ("sr_output", "uncertainty", "observation"):
        aid = f"r-{job['id']}-{atype}"
        fake_db.artifacts[aid] = {"id": aid, "job_id": job["id"],
                                  "artifact_type": atype, "storage_bucket": "b",
                                  "object_key": f"k/{atype}"}
    resp = client.post("/v1/validations",
                       json={"job_id": job["id"],
                             "reference_id": "00000000-0000-4000-8000-ffffffffffff"},
                       headers=DEV)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_validation_queue_links_job(client, fake_db):
    pid = client.post("/v1/projects", json={"name": "P6"}, headers=DEV).json()["id"]
    job = client.post("/v1/jobs", json={
        "project_id": pid, "scene_ids": [], "mode": "reconstruct",
        "model": "bicubic_4x", "idempotency_key": "run-ev2"}, headers=DEV).json()
    fake_db.jobs[job["id"]]["status"] = "COMPLETED"
    for atype in ("sr_output", "uncertainty", "observation"):
        aid = f"art-{atype}"
        fake_db.artifacts[aid] = {"id": aid, "job_id": job["id"],
                                  "artifact_type": atype, "storage_bucket": "b",
                                  "object_key": f"k/{atype}"}
    resp = client.post("/v1/validations", json={"job_id": job["id"]}, headers=DEV)
    assert resp.status_code == 201
    vid = resp.json()["id"]
    run = fake_db.validations[vid]
    assert run["queue_job_id"] is not None
    assert run["request_fingerprint"] is not None
    queued = fake_db.jobs[run["queue_job_id"]]
    assert queued["job_type"] == "validate"
    assert queued["mode"] == "validate"
    steps = {s for (jid, s) in fake_db.steps if jid == queued["id"]}
    assert steps == {"validate", "report"}
    repeat = client.post("/v1/validations", json={"job_id": job["id"]}, headers=DEV)
    assert repeat.status_code == 201
    assert repeat.json()["id"] == vid
    assert len([v for v in fake_db.validations.values() if v["job_id"] == job["id"]]) == 1


def test_migration_ordering():
    from pathlib import Path
    mig = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
    names = sorted(p.name for p in mig.glob("*.sql"))
    assert "0003a_compatibility.sql" in names
    assert "0003b_indexes.sql" in names
    assert names.index("0003a_compatibility.sql") < names.index("0003b_indexes.sql")
    text = (mig / "0003a_compatibility.sql").read_text()
    assert text.count("jobs.mode contains unsupported values") == 1


def test_job_unknown_model_rejected(client):
    resp = client.post("/v1/projects", json={"name": "P5"}, headers=DEV)
    pid = resp.json()["id"]
    out = client.post("/v1/jobs", json={
        "project_id": pid, "scene_ids": [], "mode": "reconstruct",
        "model": "does_not_exist", "idempotency_key": "x1"}, headers=DEV)
    assert out.status_code == 404
    assert out.json()["error"]["code"] == "MODEL_UNAVAILABLE"


def test_models_list(client):
    resp = client.get("/v1/models", headers=DEV)
    assert resp.status_code == 200
    names = {m["name"] for m in resp.json()}
    assert {"bicubic_4x", "custom_mf_sr", "opensr_ldsrs2"} <= names
