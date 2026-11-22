# OfficerPath AI — PDF Engine (Phase 1, M7)
# Worker runner: claims queued jobs and processes them, one at a
# time (Render free is 0.1 CPU — one job at a time is the honest
# shape; parallelism would only thrash). Two ways to run it:
#
# - In-process: WORKER_ENABLED=true starts it as a lifespan
#   background task inside the API process (see app/main.py).
# - Standalone: `python -m app.workers.runner [--once]` — its own
#   process, for the VPS stage or local runs. --once processes a
#   single job and exits (scripting / cron friendly).
#
# The runner never shares a SQLAlchemy session between the claim
# and the process: each run_once opens a fresh session so a long
# parse cannot hold a pooled connection, and a crashed worker
# leaves at most one 'processing' job behind (it is re-claimable
# only by an explicit retry — never silently re-run, so a job is
# never processed twice by accident).

from __future__ import annotations

import argparse
import time

from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.session import get_engine
from app.storage.local import LocalDiskStorage
from app.utils.logging import configure_logging, get_logger
from app.workers.processor import claim_next_job, process_job

log = get_logger(__name__)


def run_once(
    session_factory: sessionmaker, *, storage=None, settings_obj=None, bucket_downloader=None
) -> dict | None:
    """Claim and process one job. Returns its summary, or None
    when the queue is empty. `bucket_downloader` is passed through
    to `process_job` (tests inject a fake; the default is the real
    Supabase bucket download)."""
    settings_obj = settings_obj or settings
    storage = storage or LocalDiskStorage(settings_obj.storage_root)
    session: Session = session_factory()
    try:
        job = claim_next_job(session)
        if job is None:
            return None
        return process_job(
            session,
            job,
            storage=storage,
            settings=settings_obj,
            bucket_downloader=bucket_downloader,
        )
    finally:
        session.close()


def run_forever(
    session_factory: sessionmaker,
    *,
    storage=None,
    settings_obj=None,
    stop_after_idle: int | None = None,
    bucket_downloader=None,
) -> int:
    """Poll the queue until stopped. Returns the number of jobs
    processed. ``stop_after_idle`` (tests/benchmark only) stops
    after that many consecutive empty polls."""
    settings_obj = settings_obj or settings
    storage = storage or LocalDiskStorage(settings_obj.storage_root)
    processed = 0
    idle_polls = 0
    log.info(
        "worker runner started",
        extra={"fields": {"poll_seconds": settings_obj.worker_poll_seconds}},
    )
    while True:
        try:
            summary = run_once(
                session_factory,
                storage=storage,
                settings_obj=settings_obj,
                bucket_downloader=bucket_downloader,
            )
        except Exception as exc:  # noqa: BLE001 — the runner must never die on one job
            log.info("worker run_once failed", extra={"fields": {"error": str(exc)[:200]}})
            summary = None
        if summary is None:
            idle_polls += 1
            if stop_after_idle is not None and idle_polls >= stop_after_idle:
                break
            time.sleep(settings_obj.worker_poll_seconds)
            continue
        idle_polls = 0
        processed += 1
        log.info(
            "worker processed job",
            extra={"fields": {"job_id": summary.get("job_id"), "status": summary.get("status")}},
        )
    log.info("worker runner stopped", extra={"fields": {"processed": processed}})
    return processed


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="OfficerPath PDF engine worker")
    parser.add_argument("--once", action="store_true", help="Process one job, then exit.")
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=None,
        help="Override WORKER_POLL_SECONDS.",
    )
    args = parser.parse_args()
    if args.poll_seconds is not None:
        settings.worker_poll_seconds = args.poll_seconds
    engine = get_engine()
    if engine is None:
        raise SystemExit("DATABASE_URL is not configured — the worker needs a database.")
    factory = sessionmaker(bind=engine)
    if args.once:
        summary = run_once(factory)
        print("processed: " + str(summary) if summary else "queue empty")
        return
    run_forever(factory)


if __name__ == "__main__":
    main()
