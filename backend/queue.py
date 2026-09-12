"""Postgres-backed job claim queue and guarded lifecycle transitions (PRD 12)."""

from __future__ import annotations

import json
from typing import Any

import psycopg.rows

from backend import db
from backend.errors import ApiError, JOB_CONFLICT, NOT_FOUND

VALID_ORDER = [
    "QUEUED", "CLAIMED", "PREPROCESSING", "RECONSTRUCTING",
    "UNCERTAINTY", "VALIDATING", "REPORTING", "COMPLETED",
]
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
STEP_TERMINAL = {"COMPLETED", "FAILED", "SKIPPED", "CANCELLED"}


def claim_job(worker_id: str, job_types: list[str] | None = None) -> dict | None:
    """Atomically claim one queued job with ``FOR UPDATE SKIP LOCKED``."""
    del worker_id  # identity is recorded in worker logs; schema has no worker column.
    pool = db.get_pool()
    with pool.connection() as conn:
        conn.row_factory = psycopg.rows.dict_row
        with conn.cursor() as cur:
            if job_types:
                cur.execute(
                    """
                    select * from jobs
                    where status = 'QUEUED' and job_type = any(%s)
                    order by priority asc, created_at asc
                    for update skip locked limit 1
                    """,
                    (job_types,),
                )
            else:
                cur.execute(
                    """
                    select * from jobs
                    where status = 'QUEUED'
                    order by priority asc, created_at asc
                    for update skip locked limit 1
                    """
                )
            row = cur.fetchone()
            if row is None:
                return None
            cur.execute(
                """
                update jobs set status = 'CLAIMED', started_at = coalesce(started_at, now())
                where id = %s and status = 'QUEUED'
                """,
                (row["id"],),
            )
            if cur.rowcount != 1:
                return None
        conn.commit()
    claimed = dict(row)
    claimed["status"] = "CLAIMED"
    return claimed


def _current_job(job_id: str) -> str:
    row = db.query("select status from jobs where id = %s", (job_id,), one=True)
    if not isinstance(row, dict):
        raise ApiError(NOT_FOUND, f"job {job_id} not found")
    return str(row.get("status", ""))


def set_job_status(job_id: str, status: str, *, error_code: str | None = None,
                   error_message: str | None = None, progress: float | None = None) -> None:
    """Advance a job with an optimistic conditional update.

    The ``where status = expected`` predicate closes the cancellation race:
    a worker that read an old status cannot overwrite a concurrent CANCELLED
    or FAILED state.
    """
    current = _current_job(job_id)
    if status not in set(VALID_ORDER) | TERMINAL:
        raise ApiError(JOB_CONFLICT, f"unknown job status {status}")
    if status == current:
        return
    if current in TERMINAL:
        raise ApiError(JOB_CONFLICT, f"illegal transition {current}->{status}")
    if status in {"FAILED", "CANCELLED"}:
        allowed = True
    elif status == "COMPLETED":
        allowed = current in {"PREPROCESSING", "UNCERTAINTY", "REPORTING"}
    else:
        allowed = current in VALID_ORDER and VALID_ORDER.index(status) > VALID_ORDER.index(current)
    if not allowed:
        raise ApiError(JOB_CONFLICT, f"illegal transition {current}->{status}")

    assignments = ["status = %s"]
    params: list[Any] = [status]
    if error_code is not None:
        assignments.append("error_code = %s")
        params.append(error_code)
    if error_message is not None:
        assignments.append("error_message = %s")
        params.append(error_message)
    if progress is not None:
        assignments.append("progress = %s")
        params.append(float(progress))
    if status in TERMINAL:
        assignments.append("completed_at = coalesce(completed_at, now())")
    params.extend([job_id, current])
    changed = db.execute(
        f"update jobs set {', '.join(assignments)} where id = %s and status = %s",
        tuple(params),
    )
    if changed != 1:
        raise ApiError(JOB_CONFLICT, "job transition lost a concurrent race")


def _step_status(job_id: str, step_name: str) -> str:
    row = db.query(
        "select status from job_steps where job_id = %s and step_name = %s",
        (job_id, step_name), one=True)
    if not isinstance(row, dict):
        raise ApiError(NOT_FOUND, f"step {step_name} not found for job {job_id}")
    return str(row.get("status", ""))


def start_job_step(job_id: str, step_name: str) -> None:
    """Transition ``QUEUED -> RUNNING`` exactly once."""
    current = _step_status(job_id, step_name)
    if current in {"RUNNING", "COMPLETED"}:
        return
    if current in STEP_TERMINAL:
        raise ApiError(JOB_CONFLICT, f"cannot start terminal step {step_name}")
    changed = db.execute(
        """
        update job_steps js
           set status = 'RUNNING', started_at = coalesce(started_at, now()),
               attempt = attempt + 1
         where js.job_id = %s and js.step_name = %s and js.status = 'QUEUED'
           and exists (
               select 1 from jobs j
                where j.id = js.job_id
                  and j.status not in ('COMPLETED', 'FAILED', 'CANCELLED')
           )
        """,
        (job_id, step_name),
    )
    if changed != 1:
        raise ApiError(JOB_CONFLICT, f"cannot start step {step_name}; job is not active")


def complete_job_step(job_id: str, step_name: str, metrics: dict | None = None) -> None:
    """Transition ``RUNNING -> COMPLETED``; never complete after cancellation."""
    current = _step_status(job_id, step_name)
    if current == "COMPLETED":
        return
    if current != "RUNNING":
        raise ApiError(JOB_CONFLICT, f"cannot complete step {step_name} from {current}")
    if metrics is None:
        changed = db.execute(
            """
            update job_steps js
               set status = 'COMPLETED', completed_at = now(), progress = 1
             where js.job_id = %s and js.step_name = %s and js.status = 'RUNNING'
               and exists (
                   select 1 from jobs j where j.id = js.job_id
                     and j.status not in ('COMPLETED', 'FAILED', 'CANCELLED')
               )
            """,
            (job_id, step_name),
        )
    else:
        changed = db.execute(
            """
            update job_steps js
               set status = 'COMPLETED', completed_at = now(), progress = 1,
                   metrics = %s
             where js.job_id = %s and js.step_name = %s and js.status = 'RUNNING'
               and exists (
                   select 1 from jobs j where j.id = js.job_id
                     and j.status not in ('COMPLETED', 'FAILED', 'CANCELLED')
               )
            """,
            (json.dumps(metrics), job_id, step_name),
        )
    if changed != 1:
        raise ApiError(JOB_CONFLICT, f"cannot complete step {step_name}; race/cancellation")


def fail_job_step(job_id: str, step_name: str, error_code: str, error_message: str) -> None:
    """Transition an active step to FAILED, preserving the diagnostic."""
    changed = db.execute(
        """
        update job_steps js
           set status = 'FAILED', completed_at = now(),
               metrics = %s
         where js.job_id = %s and js.step_name = %s
           and js.status in ('QUEUED', 'RUNNING')
           and exists (
               select 1 from jobs j where j.id = js.job_id
                 and j.status not in ('COMPLETED', 'FAILED', 'CANCELLED')
           )
        """,
        (json.dumps({"error_code": error_code, "error_message": error_message}), job_id, step_name),
    )
    if changed != 1:
        raise ApiError(JOB_CONFLICT, f"cannot fail step {step_name}; it is terminal")


def skip_job_step(job_id: str, step_name: str) -> None:
    """Transition an unused queued step to SKIPPED."""
    current = _step_status(job_id, step_name)
    if current in STEP_TERMINAL:
        return
    changed = db.execute(
        """
        update job_steps js set status = 'SKIPPED', completed_at = now()
         where js.job_id = %s and js.step_name = %s and js.status = 'QUEUED'
           and exists (
               select 1 from jobs j where j.id = js.job_id
                 and j.status not in ('COMPLETED', 'FAILED', 'CANCELLED')
           )
        """,
        (job_id, step_name),
    )
    if changed != 1:
        raise ApiError(JOB_CONFLICT, f"cannot skip step {step_name}; race/cancellation")
