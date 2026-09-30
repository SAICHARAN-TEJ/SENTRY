"""Alerts endpoints: real detections linked to jobs/validations.

The console's Alerts tab tries these routes first. When rows exist they are
real backend detections (created automatically for completed jobs, triaged by
operators). When the backend is unreachable or has no rows, the console falls
back to its clearly-labeled simulated demo dataset — never presenting demo
content as a real detection.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend import db
from backend.auth import get_current_user, require_project_role
from backend.errors import ApiError, NOT_FOUND

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])


class AlertCreate(BaseModel):
    project_id: str
    job_id: str | None = None
    title: str | None = None
    classification: str | None = None
    confidence: float | None = None
    material_delta: str | None = None
    coord_lat: float | None = None
    coord_lon: float | None = None
    notes: str | None = None


class AlertStatusUpdate(BaseModel):
    status: str


def _alert_row(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "job_id": str(row["job_id"]) if row.get("job_id") else None,
        "classification": row.get("classification"),
        "confidence": row.get("confidence"),
        "status": row.get("status"),
        "material_delta": row.get("material_delta"),
        "coord_lat": row.get("coord_lat"),
        "coord_lon": row.get("coord_lon"),
        "notes": row.get("notes"),
        "title": row.get("title"),
        "created_at": row.get("created_at"),
    }


@router.get("", response_model=list[dict])
async def list_alerts(project_id: str,
                      status: str | None = None,
                      limit: int = 100,
                      user: dict = Depends(get_current_user)) -> list[dict]:
    """List real alerts for a project (newest first)."""
    require_project_role(user, project_id,
                         ["owner", "operator", "reviewer", "viewer"])
    clauses = ["project_id = %s"]
    params: list = [project_id]
    if status and status != "ALL":
        clauses.append("status = %s")
        params.append(status)
    params.append(min(max(limit, 1), 500))
    rows = db.query(
        f"""
        select id, project_id, job_id, title, classification, confidence,
               status, material_delta, coord_lat, coord_lon, notes, created_at
        from alerts where {' and '.join(clauses)}
        order by created_at desc limit %s
        """,
        tuple(params)) or []
    return [_alert_row(r) for r in rows]


@router.post("", status_code=201)
async def create_alert(body: AlertCreate,
                       user: dict = Depends(get_current_user)) -> dict:
    """Operator-created detection (owner/operator only)."""
    require_project_role(user, body.project_id, ["owner", "operator"])
    row = db.query(
        """
        insert into alerts
            (project_id, job_id, title, classification, confidence,
             material_delta, coord_lat, coord_lon, notes)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning id, project_id, job_id, title, classification, confidence,
                  status, material_delta, coord_lat, coord_lon, notes, created_at
        """,
        (body.project_id, body.job_id,
         body.title or "sub-pixel change candidate",
         body.classification or "HUMAN_REVIEW",
         body.confidence, body.material_delta,
         body.coord_lat, body.coord_lon, body.notes),
        one=True)
    return _alert_row(row)


@router.post("/{alert_id}/status")
async def update_alert_status(alert_id: str, body: AlertStatusUpdate,
                              user: dict = Depends(get_current_user)) -> dict:
    """Triage an alert: HUMAN_REVIEW / CONFIRMED / DISMISSED."""
    if body.status not in ("HUMAN_REVIEW", "CONFIRMED", "DISMISSED"):
        raise ApiError(NOT_FOUND, "unknown status", 404)
    row = db.query("select project_id from alerts where id = %s",
                   (alert_id,), one=True)
    if row is None:
        raise ApiError(NOT_FOUND, "alert not found", 404)
    require_project_role(user, row["project_id"], ["owner", "operator"])
    updated = db.query(
        "update alerts set status = %s where id = %s "
        "returning id, project_id, job_id, title, classification, confidence,"
        " status, material_delta, coord_lat, coord_lon, notes, created_at",
        (body.status, alert_id), one=True)
    return _alert_row(updated)


def create_job_alert(project_id: str, job_id: str,
                     validation_id: str | None,
                     overall_status: str | None,
                     score) -> None:
    """Auto-create one detection row per completed reconstruct job (best-effort).

    Called by the worker after validation. Never raises: alert creation must
    never fail a job that already produced valid outputs.
    """
    try:
        existing = db.query("select id from alerts where job_id = %s limit 1",
                            (job_id,), one=True)
        if existing is not None:
            return
        classification = "HUMAN_REVIEW" if overall_status != "PASS" else "CONFIRMED"
        status = "HUMAN_REVIEW" if overall_status != "PASS" else "CONFIRMED"
        db.execute(
            """
            insert into alerts
                (project_id, job_id, validation_run_id, title,
                 classification, confidence, status, notes)
            values (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (project_id, job_id, validation_id,
             f"reconstruction {overall_status or 'completed'}",
             classification, score if isinstance(score, (int, float)) else None,
             status,
             f"auto-created from job validation ({overall_status or 'no status'}); "
             "review the residual + uncertainty previews before use."),
        )
    except Exception:  # noqa: BLE001 - best-effort; log and never fail the job
        import logging
        logging.getLogger("sentry.alerts").exception("auto-create alert failed for job %s", job_id)
