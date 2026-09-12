"""Worker entrypoint: claim-execute loop with graceful shutdown."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sys
import threading
import time
from typing import Any

from backend.config import get_settings
from backend.queue import (claim_job, discard_active_claim, reap_stale_jobs,
                           renew_lease, set_active_claim)
from worker import run as run_mod

log = logging.getLogger("sentry.worker")

_shutdown = False


def _handle_signal(signum: int, _frame: Any) -> None:
    """Request graceful shutdown: finish the current job, then exit."""
    global _shutdown
    log.info("signal %s received: dropping lease so this claim can be reaped, "
             "then exiting after the current job", signum)
    _shutdown = True


def worker_id() -> str:
    """Stable per-process worker identity for job claiming."""
    return f"{socket.gethostname()}-{os.getpid()}"


def poll_once(job_types: list[str] | None = None) -> bool:
    """Claim and run one job with a heartbeat-renewed lease; True when it ran."""
    job = claim_job(worker_id(), job_types)
    if job is None:
        return False
    job_id, token = job["id"], job.get("claim_token")
    set_active_claim(job_id, token)
    stop = threading.Event()

    def _heartbeat() -> None:
        """Renew the lease while the job runs so the reaper leaves it alone."""
        interval = max(1.0, get_settings().job_lease_seconds / 3.0)
        while not stop.wait(interval):
            try:
                if not renew_lease(job_id, token):
                    log.warning("job %s lease lost (reaped/cancelled); stopping work",
                                job_id)
                    return  # fence kicks in; writes from here raise JOB_CONFLICT
            except Exception:  # noqa: BLE001 - transient DB hiccup: retry next tick
                log.warning("job %s lease renewal failed; will retry", job_id)

    lease_seconds = max(1, int(get_settings().job_lease_seconds))
    log.info("claimed job %s (%s) with a %ss lease", job_id, job["job_type"],
             lease_seconds)
    hb = threading.Thread(target=_heartbeat, name=f"lease-{job_id[:8]}", daemon=True)
    hb.start()
    try:
        try:
            arts = run_mod.run(job)
            log.info("job %s completed with %d artifacts", job_id, len(arts))
        except Exception:  # noqa: BLE001 - already marked FAILED in run()
            log.exception("job %s crashed", job_id)
    finally:
        stop.set()
        hb.join(timeout=lease_seconds / 3.0 + 2)
        discard_active_claim(job_id)
    return True


def main(argv: list[str] | None = None) -> int:
    """CLI loop: --once executes a single claim cycle; default runs forever."""
    parser = argparse.ArgumentParser(description="Sentry worker")
    parser.add_argument("--once", action="store_true", help="run one claim cycle then exit")
    parser.add_argument("--job-type", action="append", dest="job_types",
                        choices=["preprocess", "reconstruct", "validate", "benchmark"],
                        help="restrict claimable job types (repeatable)")
    parser.add_argument("--worker-id", default=None, help="override worker identity")
    parser.add_argument("--reap-stale", action="store_true",
                        help="run the stale-claim reaper once and exit (cron-friendly)")
    args = parser.parse_args(argv)

    if args.reap_stale:
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(name)s %(message)s")
        reaped = reap_stale_jobs()
        for entry in reaped:
            log.info("reaped job %s: %s (attempt %d)",
                     entry["job_id"], entry["action"], entry["attempt"])
        log.info("reaper done: %d job(s)", len(reaped))
        return 0

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    settings = get_settings()
    log.info("worker %s starting (concurrency=%d, protocol=%s)",
             args.worker_id or worker_id(), settings.worker_concurrency,
             settings.validation_protocol_version)

    while True:
        try:
            if _shutdown:
                # Signal received: sweep stale claims (from any crashed worker)
                # before exit so abandoned jobs requeue instead of waiting out
                # their full lease timeout.
                reap_stale_jobs()
                return 0
            ran = poll_once(args.job_types)
            if not ran:
                # Idle: opportunistically reap stale claims so crashed workers'
                # jobs requeue promptly even without a dedicated reaper process.
                reap_stale_jobs()
        except Exception as exc:  # noqa: BLE001 - DB down etc: back off and retry
            log.warning("poll failed: %s", exc)
            time.sleep(5)
            continue
        if args.once and not ran:
            return 0
        if not ran:
            time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
