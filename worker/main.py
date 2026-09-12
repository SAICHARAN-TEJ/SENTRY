"""Worker entrypoint: claim-execute loop with graceful shutdown."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sys
import time
from typing import Any

from backend.config import get_settings
from backend.queue import claim_job
from worker import run as run_mod

log = logging.getLogger("sentry.worker")

_shutdown = False


def _handle_signal(signum: int, _frame: Any) -> None:
    """Request graceful shutdown: finish the current job, then exit."""
    global _shutdown
    log.info("signal %s received: shutting down after current job", signum)
    _shutdown = True


def worker_id() -> str:
    """Stable per-process worker identity for job claiming."""
    return f"{socket.gethostname()}-{os.getpid()}"


def poll_once(job_types: list[str] | None = None) -> bool:
    """Claim and run one job; returns True when a job was executed."""
    job = claim_job(worker_id(), job_types)
    if job is None:
        return False
    log.info("claimed job %s (%s)", job["id"], job["job_type"])
    try:
        arts = run_mod.run(job)
        log.info("job %s completed with %d artifacts", job["id"], len(arts))
    except Exception:  # noqa: BLE001 - already marked FAILED in run()
        log.exception("job %s crashed", job["id"])
    return True


def main(argv: list[str] | None = None) -> int:
    """CLI loop: --once executes a single claim cycle; default runs forever."""
    parser = argparse.ArgumentParser(description="Sentry worker")
    parser.add_argument("--once", action="store_true", help="run one claim cycle then exit")
    parser.add_argument("--job-type", action="append", dest="job_types",
                        choices=["preprocess", "reconstruct", "validate", "benchmark"],
                        help="restrict claimable job types (repeatable)")
    parser.add_argument("--worker-id", default=None, help="override worker identity")
    args = parser.parse_args(argv)

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
            ran = poll_once(args.job_types)
        except Exception as exc:  # noqa: BLE001 - DB down etc: back off and retry
            log.warning("poll failed: %s", exc)
            time.sleep(5)
            continue
        if args.once and not ran:
            return 0
        if _shutdown:
            return 0
        if not ran:
            time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
