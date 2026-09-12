"""Postgres-backed job claim queue and guarded lifecycle transitions (PRD 12)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import psycopg.rows

from backend import db
from backend.config import get_settings
from backend.errors import ApiError, JOB_CONFLICT, NOT_FOUND

VALID_ORDER = [
    "QUEUED", "CLAIMED", "PREPROCESSING", "RECONSTRUCTING",
    "UNCERTAINTY", "VALIDATING", "REPORTING", "COMPLETED",
]
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
STEP_TERMINAL = {"COMPLETED", "FAILED", "SKIPPED", "CANCELLED"}

# Active claim fencing tokens: job_id -> claim_token handed to the worker.
# Transitions automatically include the token so a zombie worker whose claim
# was reaped cannot move the requeued job (its writes raise JOB_CONFLICT).
_active_claims: dict[str, str] = {}


def set_active_claim(job_id: str, claim_token: str | None) -> None:
    """Register the current worker's claim token for fenced transitions."""
    if claim_token:
        _active_claims[job_id] = claim_token


def discard_active_claim(job_id: str) -> None:
    """Forget a finished claim so its token can never fence later writes."""
    _active_claims.pop(job_id, None)


def claim_job(worker_id: str, job_types: list[str] | None = None) -> dict | None:
    """Atomically claim one queued job with ``FOR UPDATE SKIP LOCKED``.

    The claim carries a lease (``lease_expires_at`` = now + JOB_LEASE_SECONDS)
    and a fresh ``claim_token``. A worker heartbeat renews the lease while it
    runs; ``reap_stale_jobs`` requeues claims whose lease lapses (worker died),
    so CLAIMED jobs can no longer get stuck forever.
    """
    del worker_id  # identity is recorded in worker logs; schema has no worker column.
    lease_seconds = max(1, int(get_settings().job_lease_seconds))
    token = uuid.uuid4()
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
                update jobs
                   set status = 'CLAIMED',
                       started_at = coalesce(started_at, now()),
                       attempt = attempt + 1,
                       claim_token = %s,
                       lease_expires_at = now() + make_interval(secs => %s)
                 where id = %s and status = 'QUEUED'
                """,
                (token, lease_seconds, row["id"]),
            )
            if cur.rowcount != 1:
                return None
        conn.commit()
    claimed = dict(row)
    claimed["status"] = "CLAIMED"
    claimed["claim_token"] = str(token)
    return claimed


def renew_lease(job_id: str, claim_token: str, *, extra_seconds: int | None = None) -> bool:
    """Renew a claim's lease while the worker is alive.

    Returns False when the claim was reaped or the job reached a terminal
    state — the caller should stop working immediately: the job now belongs to
    another attempt, and fenced transitions will reject its writes.
    """
    seconds = max(1, int(extra_seconds
                         if extra_seconds is not None
                         else get_settings().job_lease_seconds))
    changed = db.execute(
        """
        update jobs set lease_expires_at = now() + make_interval(secs => %s)
         where id = %s and claim_token = %s
           and status not in ('COMPLETED', 'FAILED', 'CANCELLED')
        """,
        (seconds, job_id, claim_token),
    )
    return changed == 1


def reap_stale_jobs(limit: int = 50) -> list[dict]:
    """Requeue CLAIMED jobs whose lease expired; fail those past max attempts.

    Single transaction with ``FOR UPDATE SKIP LOCKED`` so concurrent reapers
    and claimers never double-process a row. Requeued jobs get a fresh QUEUED
    status and a nulled claim_token (the old holder is fenced out); jobs at
    ``JOB_MAX_ATTEMPTS`` attempts are failed permanently with LEASE_LOST.
    Returns ``[{job_id, attempt, action}]`` for logging/provenance.
    """
    max_attempts = max(1, int(get_settings().job_max_attempts))
    results: list[dict] = []
    with db.transaction() as tx:
        rows = tx.query(
            """
            select id, project_id, attempt from jobs
             where status = 'CLAIMED'
               and lease_expires_at is not null
               and lease_expires_at < now()
             order by lease_expires_at asc
             limit %s
             for update skip locked
            """,
            (limit,),
        ) or []
        for row in rows:
            job_id, attempt = row["id"], int(row.get("attempt") or 0)
            if attempt >= max_attempts:
                changed = tx.execute(
                    """
                    update jobs
                       set status = 'FAILED',
                           error_code = 'LEASE_LOST',
                           error_message = %s,
                           lease_expires_at = null,
                           claim_token = null,
                           completed_at = coalesce(completed_at, now())
                     where id = %s and status = 'CLAIMED'
                    """,
                    (f"lease expired after {attempt} attempts "
                     f"(max {max_attempts}); worker likely crashed", job_id),
                )
                action = "failed"
                event = "job_lease_lost"
            else:
                changed = tx.execute(
                    """
                    update jobs
                       set status = 'QUEUED',
                           claim_token = null,
                           lease_expires_at = null
                     where id = %s and status = 'CLAIMED'
                    """,
                    (job_id,),
                )
                action = "requeued"
                event = "job_requeued"
            if changed == 1:
                tx.execute(
                    """
                    insert into provenance_events
                        (project_id, entity_type, entity_id, event_type, actor, payload)
                    values (%s, 'job', %s, %s, 'reaper', %s)
                    """,
                    (row.get("project_id"), job_id, event,
                     json.dumps({"attempt": attempt, "action": action})),
                )
                results.append({"job_id": str(job_id), "attempt": attempt,
                                "action": action})
    return results


def _current_job(job_id: str) -> str:
    row = db.query("select status from jobs where id = %s", (job_id,), one=True)
    if not isinstance(row, dict):
        raise ApiError(NOT_FOUND, f"job {job_id} not found")
    return str(row.get("status", ""))


def set_job_status(job_id: str, status: str, *, claim_token: str | None = None,
                   error_code: str | None = None,
                   error_message: str | None = None, progress: float | None = None) -> None:
    """Advance a job with an optimistic conditional update.

    The ``where status = expected`` predicate closes the cancellation race:
    a worker that read an old status cannot overwrite a concurrent CANCELLED
    or FAILED state. When a claim token is available (explicitly or via the
    worker's active claim), the update is additionally fenced on it, so a
    zombie worker whose claim was reaped cannot move the requeued job.
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
        discard_active_claim(job_id)
    params.extend([job_id, current])
    where_sql = "where id = %s and status = %s"
    token = claim_token or _active_claims.get(job_id)
    if token:
        where_sql += " and claim_token = %s"
        params.append(token)
    changed = db.execute(
        f"update jobs set {', '.join(assignments)} {where_sql}",
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
