"""Validation endpoints: create explicit runs, fetch metrics/status."""

from __future__ import annotations

import hashlib
import json
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend import db
from backend.auth import get_current_user, require_project_role
from backend.config import get_settings
from backend.errors import ApiError, JOB_CONFLICT, NOT_FOUND, VALIDATION_INCOMPLETE
from backend.schemas import ValidationOut

router = APIRouter(prefix="/v1/validations", tags=["validations"])


class ValidationCreate(BaseModel):
    job_id: str
    reference_id: str | None = None
    evaluation_grid_m: float = 2.5


@router.post("", status_code=201, response_model=ValidationOut)
async def create_validation(body: ValidationCreate,
                            user: dict = Depends(get_current_user)) -> ValidationOut:
    """Register a validation run and queue a worker-backed validation job atomically."""
    settings = get_settings()
    fingerprint = hashlib.sha256(
        f"{body.job_id}|{body.reference_id}|{body.evaluation_grid_m}|"
        f"{settings.validation_protocol_version}".encode()
    ).hexdigest()
    with db.transaction() as tx:
        tx.query(
            "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"validation:{body.job_id}:{fingerprint}",), one=True)
        job = tx.query(
            "select project_id, status, model_version_id, config_hash from jobs where id = %s",
            (body.job_id,), one=True)
        if job is None:
            raise ApiError(NOT_FOUND, "job not found", 404)
        require_project_role(user, job["project_id"], ["owner", "operator"])
        if job.get("status") != "COMPLETED":
            raise ApiError(VALIDATION_INCOMPLETE,
                           "source job must be COMPLETED before explicit validation")
        if body.reference_id:
            ref = tx.query(
                "select id from reference_assets where id = %s",
                (body.reference_id,), one=True)
            if ref is None:
                raise ApiError(NOT_FOUND, "reference asset not found", 404)
            # Reference catalog rows are global-readable; record the exact
            # reference on the validation run so the worker resolves the
            # request-scoped reference rather than any same-project asset.
        existing = tx.query(
            "select id from validation_runs where job_id = %s and request_fingerprint = %s "
            "order by created_at desc limit 1 for update",
            (body.job_id, fingerprint), one=True)
        if existing is not None:
            run = tx.query(
                "select id, overall_status, score, evaluation_grid_m, status, protocol_version "
                "from validation_runs where id = %s",
                (existing["id"],), one=True)
            return ValidationOut(
                id=run["id"], overall_status=run.get("overall_status"),
                score=run.get("score"), evaluation_grid_m=run["evaluation_grid_m"],
                metrics=[], uncertainty=None, protocol=run["protocol_version"],
                status=run["status"],
            )

        # Mandatory evidence must exist before queueing an explicit run.
        for artifact_type in ("sr_output", "uncertainty", "observation"):
            if tx.query(
                "select 1 as ok from raster_artifacts where job_id = %s and artifact_type = %s",
                (body.job_id, artifact_type), one=True,
            ) is None:
                raise ApiError(VALIDATION_INCOMPLETE,
                               f"source job is missing {artifact_type} evidence")

        row = tx.query(
            """
            insert into validation_runs
                (job_id, protocol_version, evaluation_grid_m, reference_id,
                 request_fingerprint)
            values (%s, %s, %s, %s, %s)
            on conflict (job_id, request_fingerprint)
                where request_fingerprint is not null do nothing
            returning id, overall_status, score, evaluation_grid_m, status, protocol_version
            """,
            (body.job_id, settings.validation_protocol_version,
             body.evaluation_grid_m, body.reference_id, fingerprint),
            one=True,
        )
        if row is None:
            # Lost a concurrent race; the winner holds the fingerprint row.
            existing = tx.query(
                "select id from validation_runs where job_id = %s and request_fingerprint = %s "
                "order by created_at desc limit 1",
                (body.job_id, fingerprint), one=True)
            if existing is None:
                raise ApiError(JOB_CONFLICT, "validation request conflicted; retry")
            run = tx.query(
                "select id, overall_status, score, evaluation_grid_m, status, protocol_version "
                "from validation_runs where id = %s",
                (existing["id"],), one=True)
            return ValidationOut(
                id=run["id"], overall_status=run.get("overall_status"),
                score=run.get("score"), evaluation_grid_m=run["evaluation_grid_m"],
                metrics=[], uncertainty=None, protocol=run["protocol_version"],
                status=run["status"],
            )
        validation_id = row["id"]
        idem = f"validation:{body.job_id}:{validation_id}"
        queued = tx.query(
            """
            insert into jobs (project_id, job_type, mode, status, requested_by,
                              idempotency_key, input_fingerprint, config_hash,
                              model_version_id)
            values (%s, 'validate', 'validate', 'QUEUED', %s, %s, %s, %s, %s)
            returning id
            """,
            (job["project_id"], user["id"], idem, fingerprint,
             job.get("config_hash"), job.get("model_version_id")),
            one=True,
        )
        queue_job_id = queued["id"]
        for step in ("validate", "report"):
            tx.execute(
                "insert into job_steps (job_id, step_name, status) values (%s, %s, 'QUEUED')",
                (queue_job_id, step),
            )
        tx.execute(
            """
            insert into job_inputs (job_id, role, object_key_snapshot)
            values (%s, 'source_job', %s)
            """,
            (queue_job_id, body.job_id),
        )
        if body.reference_id:
            tx.execute(
                "insert into job_inputs (job_id, ref_asset_id, role) values (%s, %s, 'reference')",
                (queue_job_id, body.reference_id),
            )
        tx.execute(
            """
            update validation_runs set queue_job_id = %s, request_fingerprint = %s
            where id = %s
            """,
            (queue_job_id, fingerprint, validation_id),
        )
        tx.execute(
            """
            insert into provenance_events
                (project_id, entity_type, entity_id, event_type, actor, payload)
            values (%s, 'validation_run', %s, 'validation_queued', %s, %s)
            """,
            (job["project_id"], validation_id, user["id"],
             json.dumps({"queue_job_id": queue_job_id, "source_job_id": body.job_id})),
        )
    return ValidationOut(
        id=validation_id, overall_status=None, score=None,
        evaluation_grid_m=row["evaluation_grid_m"], metrics=[],
        uncertainty=None, protocol=row["protocol_version"], status=row["status"],
    )


@router.get("/{validation_id}", response_model=ValidationOut)
async def get_validation(validation_id: str,
                         user: dict = Depends(get_current_user)) -> ValidationOut:
    """Return overall status, score, metrics and uncertainty summary (PRD 13)."""
    run = db.query(
        """
        select vr.id, vr.job_id, vr.overall_status, vr.score, vr.evaluation_grid_m,
               vr.status, vr.protocol_version
        from validation_runs vr where vr.id = %s
        """,
        (validation_id,),
        one=True,
    )
    if run is None:
        raise ApiError(NOT_FOUND, "validation not found", 404)
    job = db.query("select project_id from jobs where id = %s",
                   (run["job_id"],), one=True)
    require_project_role(user, job["project_id"],
                         ["owner", "operator", "reviewer", "viewer"])

    metrics = db.query(
        """
        select metric_name as name, band, value, threshold, pass
        from validation_metrics where validation_run_id = %s
        """,
        (validation_id,),
    )
    unc = db.query(
        """
        select us.mean, us.p50, us.p90, us.p95, us.max, us.coverage
        from uncertainty_summaries us
        join raster_artifacts ra on ra.id = us.raster_artifact_id
        where ra.job_id = %s and ra.artifact_type = 'uncertainty'
        limit 1
        """,
        (run["job_id"],),
        one=True,
    )
    return ValidationOut(
        id=run["id"], overall_status=run["overall_status"], score=run["score"],
        evaluation_grid_m=run["evaluation_grid_m"], metrics=metrics or [],
        uncertainty=unc, protocol=run["protocol_version"], status=run["status"],
    )
