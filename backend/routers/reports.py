"""Report endpoints: fetch validation report metadata + JSON summary."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend import db
from backend.auth import get_current_user, require_project_role
from backend.errors import ApiError, JOB_CONFLICT
from backend.schemas import ReportOut

router = APIRouter(prefix="/v1/reports", tags=["reports"])


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(report_id: str, user: dict = Depends(get_current_user)) -> ReportOut:
    """Return a validation report row (summary JSON + storage object reference)."""
    report = db.query(
        """
        select r.id, r.validation_run_id, r.summary_json, r.report_object_key, r.created_at,
               vr.job_id
        from reports r
        join validation_runs vr on vr.id = r.validation_run_id
        where r.id = %s
        """,
        (report_id,),
        one=True,
    )
    if report is None:
        raise ApiError(JOB_CONFLICT, "report not found", 404)
    job = db.query("select project_id from jobs where id = %s",
                   (report["job_id"],), one=True)
    require_project_role(user, job["project_id"],
                         ["owner", "operator", "reviewer", "viewer"])
    return ReportOut(
        id=report["id"], validation_run_id=report["validation_run_id"],
        summary_json=report["summary_json"], report_object_key=report.get("report_object_key"),
        created_at=report["created_at"],
    )
