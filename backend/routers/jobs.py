"""Job submission, lifecycle inspection, cancellation and idempotency.

A client idempotency key identifies a *request*, not merely a project. The
fingerprint therefore includes every input that can change scientific output.
Terminal attempts remain immutable; migration 0007 allows a new active attempt
with the same client key while retaining the old attempt for auditability.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from backend import db
from backend.auth import get_current_user, require_project_role
from backend.config import get_settings
from backend.errors import ApiError, JOB_CONFLICT, MODEL_UNAVAILABLE, NOT_FOUND
from backend.schemas import JobCreate, JobOut

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])

MODES = {
    "reconstruct_validate": "reconstruct",
    "reconstruct": "reconstruct",
    "preprocess": "preprocess",
    "validate": "validate",
    "benchmark": "benchmark",
}
STEP_NAMES = ["preprocess", "reconstruct", "uncertainty", "validate", "report"]
STEP_SETS = {
    "reconstruct_validate": STEP_NAMES,
    "reconstruct": ["preprocess", "reconstruct", "uncertainty"],
    "preprocess": ["preprocess"],
    "validate": ["validate", "report"],
    "benchmark": ["preprocess", "validate", "report"],
}
TERMINAL = ("COMPLETED", "FAILED", "CANCELLED")


def _request_fingerprint(body: JobCreate, job_type: str, config_hash: str | None,
                         model: dict, protocol: str) -> str:
    """Hash all output-affecting request identity fields canonically."""
    canonical = {
        "project_id": body.project_id,
        "aoi_id": body.aoi_id,
        "scene_ids": sorted(str(s) for s in body.scene_ids),
        "reference_id": body.reference_id,
        "mode": body.mode,
        "job_type": job_type,
        "model": body.model,
        "model_version_id": str(model.get("id")),
        "config_id": body.config_id,
        "config_hash": config_hash,
        "validation_protocol": protocol,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _job_view(job_id: str) -> JobOut:
    """Assemble the public job response from normalized child rows."""
    job = db.query(
        """
        select id, project_id, job_type, status, progress, error_code, error_message
        from jobs where id = %s
        """,
        (job_id,), one=True)
    if job is None:
        raise ApiError(NOT_FOUND, "job not found")
    steps = db.query(
        """
        select step_name as name, status, progress, attempt, metrics
        from job_steps where job_id = %s
        """,
        (job_id,)) or []
    order = {name: i for i, name in enumerate(STEP_NAMES)}
    steps = sorted(steps, key=lambda row: order.get(row.get("name", ""), 99))
    artifacts = db.query(
        """
        select id, artifact_type, storage_bucket, object_key, checksum, bytes, media_type
        from raster_artifacts where job_id = %s order by created_at
        """,
        (job_id,)) or []
    validation = db.query(
        "select id from validation_runs where job_id = %s order by created_at desc limit 1",
        (job_id,), one=True)
    error = None
    if job.get("error_code"):
        error = {"code": job["error_code"], "message": job.get("error_message")}
    return JobOut(
        id=job["id"], project_id=job["project_id"], job_type=job["job_type"],
        status=job["status"], progress=job.get("progress") or 0.0,
        steps=steps, artifacts=artifacts,
        validation_id=validation["id"] if validation else None,
        error=error,
    )


def _provenance(tx: Any, project_id: str, entity_id: str, event: str,
                actor: str, payload: dict) -> None:
    tx.execute(
        """
        insert into provenance_events
            (project_id, entity_type, entity_id, event_type, actor, payload)
        values (%s, 'job', %s, %s, %s, %s)
        """,
        (project_id, entity_id, event, actor, json.dumps(payload)),
    )


def _validate_inputs(tx: Any, body: JobCreate, job_type: str,
                     protocol: str) -> tuple[dict, str | None, str]:
    """Validate references and compute the request fingerprint inside a tx."""
    config_hash = None
    if body.config_id:
        config = tx.query(
            "select config_hash from processing_configs where id = %s and project_id = %s",
            (body.config_id, body.project_id), one=True)
        if config is None:
            raise ApiError(NOT_FOUND, "processing config not found")
        config_hash = config.get("config_hash")

    model = tx.query(
        """
        select id, name, version, checksum from model_versions
        where name = %s order by created_at desc limit 1
        """,
        (body.model,), one=True)
    if model is None:
        raise ApiError(MODEL_UNAVAILABLE, f"model {body.model} not in registry")

    for scene_id in body.scene_ids:
        if tx.query("select id from scenes where id = %s", (scene_id,), one=True) is None:
            raise ApiError(NOT_FOUND, f"scene {scene_id} not found")
    if body.aoi_id and tx.query(
        "select id from aois where id = %s and project_id = %s",
        (body.aoi_id, body.project_id), one=True) is None:
        raise ApiError(NOT_FOUND, "AOI not found for project")
    if body.reference_id and tx.query(
        "select id from reference_assets where id = %s",
        (body.reference_id,), one=True) is None:
        raise ApiError(NOT_FOUND, "reference asset not found")

    return model, config_hash, _request_fingerprint(body, job_type, config_hash, model, protocol)


@router.post("", status_code=201, response_model=None)
async def create_job(body: JobCreate, user: dict = Depends(get_current_user)) -> JSONResponse:
    """Create a job and all required children atomically."""
    require_project_role(user, body.project_id, ["owner", "operator"])
    settings = get_settings()
    if body.mode not in MODES:
        raise ApiError(JOB_CONFLICT, f"unknown mode {body.mode}", 400)
    job_type = MODES[body.mode]
    protocol = body.validation_protocol or settings.validation_protocol_version

    active_existing: dict | None = None
    created_id: str | None = None
    with db.transaction() as tx:
        # Serialize requests with the same project/key across API replicas.
        tx.query(
            "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"{body.project_id}:{body.idempotency_key}",), one=True)
        model, config_hash, fingerprint = _validate_inputs(tx, body, job_type, protocol)

        active_rows = tx.query(
            """
            select * from jobs
            where project_id = %s and idempotency_key = %s
              and status not in ('FAILED', 'CANCELLED')
            order by created_at desc
            for update
            """,
            (body.project_id, body.idempotency_key)) or []
        if active_rows:
            active_existing = active_rows[0]
            if active_existing.get("input_fingerprint") != fingerprint:
                raise ApiError(
                    JOB_CONFLICT,
                    "idempotency key is already associated with a different request",
                )
        else:
            job = tx.query(
                """
                insert into jobs
                    (project_id, job_type, mode, status, requested_by,
                     idempotency_key, input_fingerprint, config_hash, model_version_id)
                values (%s, %s, %s, 'QUEUED', %s, %s, %s, %s, %s)
                returning id
                """,
                (body.project_id, job_type, body.mode, user["id"],
                 body.idempotency_key, fingerprint, config_hash, model["id"]),
                one=True)
            if job is None:
                raise ApiError(JOB_CONFLICT, "job could not be created", 500)
            created_id = job["id"]
            for step in STEP_SETS[body.mode]:
                tx.execute(
                    "insert into job_steps (job_id, step_name, status) values (%s, %s, 'QUEUED')",
                    (created_id, step))
            for scene_id in body.scene_ids:
                tx.execute(
                    "insert into job_inputs (job_id, scene_id, role) values (%s, %s, 'input')",
                    (created_id, scene_id))
            if body.reference_id:
                tx.execute(
                    "insert into job_inputs (job_id, ref_asset_id, role) values (%s, %s, 'reference')",
                    (created_id, body.reference_id))
            if body.aoi_id:
                tx.execute(
                    "insert into job_inputs (job_id, role, object_key_snapshot) values (%s, 'aoi', %s)",
                    (created_id, body.aoi_id))
            _provenance(tx, body.project_id, created_id, "job_submitted", user["id"], {
                "mode": body.mode, "model": body.model,
                "input_fingerprint": fingerprint, "protocol_version": protocol,
            })

    if active_existing is not None:
        return JSONResponse(_job_view(active_existing["id"]).model_dump(mode="json", by_alias=True),
                            status_code=200)
    return JSONResponse(_job_view(created_id).model_dump(mode="json", by_alias=True),
                        status_code=201)


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, user: dict = Depends(get_current_user)) -> JobOut:
    """Return job state, steps, artifacts and validation reference."""
    job = db.query("select project_id from jobs where id = %s", (job_id,), one=True)
    if job is None:
        raise ApiError(NOT_FOUND, "job not found")
    require_project_role(user, job["project_id"],
                         ["owner", "operator", "reviewer", "viewer"])
    return _job_view(job_id)


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: str, user: dict = Depends(get_current_user)) -> JobOut:
    """Atomically cancel a non-terminal job and its active steps."""
    job = db.query("select project_id from jobs where id = %s", (job_id,), one=True)
    if job is None:
        raise ApiError(NOT_FOUND, "job not found")
    require_project_role(user, job["project_id"], ["owner", "operator"])
    with db.transaction() as tx:
        changed = tx.execute(
            """
            update jobs set status = 'CANCELLED', completed_at = now()
            where id = %s and status not in ('COMPLETED', 'FAILED', 'CANCELLED')
            """,
            (job_id,))
        if changed != 1:
            raise ApiError(JOB_CONFLICT, "job is already terminal or was cancelled concurrently")
        tx.execute(
            """
            update job_steps set status = 'CANCELLED', completed_at = now()
            where job_id = %s and status in ('QUEUED', 'RUNNING')
            """,
            (job_id,))
        _provenance(tx, job["project_id"], job_id, "job_cancelled", user["id"], {})
    return _job_view(job_id)
