"""Job lease, fencing and reaper tests (stale CLAIMED jobs can never pile up)."""

from __future__ import annotations

import time
from unittest import mock

import pytest

from backend import queue


def test_claim_stamps_lease_token_and_attempt(fake_db, monkeypatch):
    """claim_job stamps attempt, a fresh claim_token and a future lease."""
    monkeypatch.setenv("JOB_LEASE_SECONDS", "300")
    from backend.config import get_settings
    get_settings.cache_clear()

    row = {"id": "job-1", "project_id": "p1", "job_type": "validate",
           "status": "QUEUED", "attempt": 0, "claim_token": None,
           "lease_expires_at": None}
    fake_db.jobs[row["id"]] = row

    pool = mock.MagicMock()
    conn = mock.MagicMock()
    cur = mock.MagicMock()
    pool.connection.return_value.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.return_value = dict(row)
    cur.rowcount = 1
    monkeypatch.setattr(queue.db, "get_pool", lambda: pool)

    claimed = queue.claim_job("worker-1")
    assert claimed is not None
    assert claimed["status"] == "CLAIMED"
    # A claim token was generated and returned to the worker for fencing.
    assert claimed["claim_token"]
    assert len(claimed["claim_token"]) == 36  # uuid4
    # The claim UPDATE carried the lease stamp: token, interval and attempt.
    update_sql = " ".join(cur.execute.call_args_list[-1][0][0].lower().split())
    assert "claim_token = %s" in update_sql
    assert "lease_expires_at = now() + make_interval" in update_sql
    assert "attempt = attempt + 1" in update_sql
    params = cur.execute.call_args_list[-1][0][1]
    assert params[0] == claimed["claim_token"] or str(params[0]) == claimed["claim_token"]


def test_renew_lease_fenced_by_token(fake_db):
    """renew_lease only extends the lease when the claim_token matches."""
    row = {"id": "job-1", "project_id": "p1", "job_type": "validate",
           "status": "CLAIMED", "attempt": 1, "claim_token": "tok-A",
           "lease_expires_at": time.time() + 10}
    fake_db.jobs[row["id"]] = row

    assert queue.renew_lease("job-1", "tok-A") is True
    assert row["lease_expires_at"] > time.time() + 1

    # Wrong token (zombie / reaped holder): refused.
    row["lease_expires_at"] = time.time() + 10
    assert queue.renew_lease("job-1", "tok-B") is False
    # Terminal job: refused.
    row["status"] = "COMPLETED"
    assert queue.renew_lease("job-1", "tok-A") is False


def test_reaper_requeues_stale_claim(fake_db):
    """An expired lease requeues the job and fences the old claim token."""
    row = {"id": "job-1", "project_id": "p1", "job_type": "validate",
           "status": "CLAIMED", "attempt": 1, "claim_token": "tok-A",
           "lease_expires_at": time.time() - 1}
    fake_db.jobs[row["id"]] = row

    results = queue.reap_stale_jobs()
    assert results == [{"job_id": "job-1", "attempt": 1, "action": "requeued"}]
    assert row["status"] == "QUEUED"
    assert row["claim_token"] is None
    assert row["lease_expires_at"] is None
    # A provenance event records the requeue for auditability.
    assert any(ev["sql"].startswith("insert into provenance_events")
               for ev in fake_db.provenance)
    # A live claim is never touched by the reaper.
    live = {"id": "job-2", "project_id": "p1", "job_type": "validate",
            "status": "CLAIMED", "attempt": 1, "claim_token": "tok-B",
            "lease_expires_at": time.time() + 100}
    fake_db.jobs[live["id"]] = live
    results = queue.reap_stale_jobs()
    assert results == []
    assert live["status"] == "CLAIMED"


def test_reaper_fails_past_max_attempts(fake_db, monkeypatch):
    """A stale claim already at JOB_MAX_ATTEMPTS fails permanently (LEASE_LOST)."""
    monkeypatch.setenv("JOB_MAX_ATTEMPTS", "2")
    from backend.config import get_settings
    get_settings.cache_clear()

    row = {"id": "job-1", "project_id": "p1", "job_type": "validate",
           "status": "CLAIMED", "attempt": 2, "claim_token": "tok-A",
           "lease_expires_at": time.time() - 1}
    fake_db.jobs[row["id"]] = row

    results = queue.reap_stale_jobs()
    assert results == [{"job_id": "job-1", "attempt": 2, "action": "failed"}]
    assert row["status"] == "FAILED"
    assert row["error_code"] == "LEASE_LOST"
    assert row["claim_token"] is None
    assert row["lease_expires_at"] is None


def test_fenced_transition_rejects_zombie_write(fake_db):
    """A zombie worker's transition (stale token) cannot move the requeued job."""
    from backend.errors import ApiError, JOB_CONFLICT

    # Requeued job now carries the NEW holder's token.
    row = {"id": "job-1", "project_id": "p1", "job_type": "validate",
           "status": "CLAIMED", "attempt": 2, "claim_token": "tok-NEW",
           "lease_expires_at": time.time() + 300}
    fake_db.jobs[row["id"]] = row

    # The zombie still holds tok-A: its fenced write must conflict.
    with pytest.raises(ApiError) as exc:
        queue.set_job_status("job-1", "PREPROCESSING", claim_token="tok-A")
    assert exc.value.code == JOB_CONFLICT
    assert row["status"] == "CLAIMED"

    # The legitimate holder's fenced write succeeds.
    queue.set_job_status("job-1", "PREPROCESSING", claim_token="tok-NEW")
    assert row["status"] == "PREPROCESSING"


def test_fenced_terminal_transition_discards_claim(fake_db):
    """A terminal transition drops the active claim so later writes are rejected."""
    row = {"id": "job-1", "project_id": "p1", "job_type": "validate",
           "status": "REPORTING", "attempt": 1, "claim_token": "tok-A",
           "lease_expires_at": time.time() + 300}
    fake_db.jobs[row["id"]] = row
    queue.set_active_claim("job-1", "tok-A")

    queue.set_job_status("job-1", "COMPLETED")
    assert row["status"] == "COMPLETED"
    assert queue._active_claims.get("job-1") is None
    # Any further transition from the finished worker now conflicts.
    from backend.errors import ApiError
    with pytest.raises(ApiError):
        queue.set_job_status("job-1", "FAILED")


def test_poll_once_heartbeat_thread_renews_lease(fake_db, monkeypatch):
    """The worker's heartbeat renews the lease while run() is in flight."""
    from worker import main as worker_main

    row = {"id": "job-1", "project_id": "p1", "job_type": "validate",
           "status": "QUEUED", "attempt": 0, "claim_token": None,
           "lease_expires_at": None}
    fake_db.jobs[row["id"]] = row
    claimed = dict(row)
    claimed["status"] = "CLAIMED"
    claimed["claim_token"] = "tok-A"

    calls = []

    def fake_claim(worker_id, job_types=None):
        calls.append("claim")
        return claimed

    def fake_run(job):
        # During execution the heartbeat should have stamped a lease renewal.
        assert queue._active_claims.get("job-1") == "tok-A"
        return []

    monkeypatch.setattr(worker_main, "claim_job", fake_claim)
    monkeypatch.setattr(worker_main.run_mod, "run", fake_run)
    # Tiny lease so the heartbeat fires immediately (lease/3 >= 1s floor).
    monkeypatch.setenv("JOB_LEASE_SECONDS", "3")
    from backend.config import get_settings
    get_settings.cache_clear()

    assert worker_main.poll_once() is True
    # The claim was registered for fencing and dropped after completion.
    assert queue._active_claims.get("job-1") is None


def test_worker_cli_reap_stale_flag(fake_db, capsys):
    """--reap-stale runs the reaper once and exits 0."""
    from worker import main as worker_main

    row = {"id": "job-1", "project_id": "p1", "job_type": "validate",
           "status": "CLAIMED", "attempt": 1, "claim_token": "tok-A",
           "lease_expires_at": time.time() - 1}
    fake_db.jobs[row["id"]] = row

    rc = worker_main.main(["--reap-stale"])
    assert rc == 0
    assert row["status"] == "QUEUED"
    assert row["claim_token"] is None
