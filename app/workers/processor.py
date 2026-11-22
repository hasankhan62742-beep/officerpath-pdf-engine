# OfficerPath AI — PDF Engine (Phase 1, M7)
# Background job processing (ADR-009): the async job pipeline.
#
# Design (why this shape):
# - IN-PROCESS worker, no Redis/celery: Render free is ONE 0.1-CPU
#   instance with 512 MB (ADR-001). A queue broker would need its
#   own memory and a second paid service; the job table IS the
#   queue (status='queued' rows, claimed atomically). A separate
#   worker process is still possible — `python -m app.workers.runner`
#   — for the VPS stage, where it runs beside the API.
# - The worker processes SQLAlchemy jobs (the async-jobs API +
#   sync-parse jobs, and — since ADR-011, M3 — register/upload
#   jobs too, now that all of them live in the engine DB). A
#   register-source job is never claimed: its bytes live in the
#   Supabase bucket, not on local disk, so it is skipped by
#   claim_next_job until M4 wires bucket download. A sync-parse
#   job has no stored bytes (storage_path="inline-parse") and
#   fails fast with "no_stored_bytes" if ever queued.
# - Stages: the parse path calls the worker's on_stage hook at
#   every phase boundary (classify -> render -> ocr -> layout ->
#   extract -> answers -> matching -> report). Each hook records
#   a processing_stages row (per-stage timing in detail.seconds),
#   a structured log line, and enforces the two worker guarantees:
#   cancellation (checked between stages) and the per-stage
#   timeout (a stage whose cumulative time exceeds
#   worker_stage_timeout_seconds fails the job with the stage
#   named — never left hanging). A hung Tesseract page cannot hang
#   the worker either: the adapter has its own per-page timeout
#   (tesseract_timeout_seconds) and a timed-out page contributes
#   no blocks (M2 per-page failure isolation).
# - Cancellation is stored in Job.result_summary
#   ({"cancel_requested": true}) — the jobs table is owned by
#   Supabase migration 015, NOT Alembic-managed, so no column can
#   be added from here; the JSON flag is the schema-free way to
#   signal a running worker. A queued job cancels immediately; a
#   processing job cancels at the next stage boundary and is then
#   recorded as cancelled, never failed.
# - No log line, stage detail, or error message ever contains file
#   contents or OCR text — only counts, page numbers, and codes.

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import ApiError
from app.db import models as db
from app.pipeline.ingestion.service import SqlAlchemyStageRecorder
from app.pipeline.interfaces import PipelineStage
from app.pipeline.matching.service import parse_document_bytes, parse_image_bytes
from app.pipeline.matching.store import persist_matched_document
from app.storage.base import StorageBackend
from app.utils import metrics
from app.utils.logging import get_logger

log = get_logger(__name__)

#: Hook stage name (from the parse path) -> §5.3 PipelineStage.
HOOK_TO_STAGE: dict[str, PipelineStage] = {
    "ingest": PipelineStage.UPLOADED,
    "classify": PipelineStage.VALIDATED,
    "render": PipelineStage.PREPROCESSING,
    "ocr": PipelineStage.OCR_DONE,
    "layout": PipelineStage.LAYOUT_DONE,
    "extract": PipelineStage.EXTRACTED,
    "answers": PipelineStage.ANSWERS_DETECTED,
    "matching": PipelineStage.MATCHED,
    "report": PipelineStage.SCORED,
}


class JobCancelled(Exception):
    """The job was cancelled (at a stage boundary)."""

    def __init__(self, stage: str) -> None:
        super().__init__(f"job cancelled during stage '{stage}'")
        self.stage = stage


class StageTimeout(Exception):
    """A stage ran longer than worker_stage_timeout_seconds."""

    def __init__(self, stage: str, seconds: float, limit: float) -> None:
        super().__init__(f"stage '{stage}' exceeded the {limit:.0f}s timeout after {seconds:.1f}s")
        self.stage = stage
        self.seconds = seconds
        self.limit = limit


def claim_next_job(session: Session) -> db.Job | None:
    """Claim the oldest queued job atomically: UPDATE ... WHERE
    id = (oldest queued) AND status='queued'. The status guard
    makes the claim safe if two workers race — the loser updates
    zero rows and gets None. Returns the claimed job, or None.

    ADR-011: register-source jobs are SKIPPED — their bytes live
    in the Supabase bucket, not on local disk, so claiming one
    would fail it with "no stored bytes". The source marker lives
    in the job's result_summary ({"source": "register"}); the
    predicate is null-safe (coalesce to '') so a missing marker —
    async submits, and failed jobs retried with a summary that
    carries no source — stays claimable. The same predicate guards
    the UPDATE, so a concurrent change of the marker cannot
    smuggle a register job into the claim.

    NOTE (measured): `result_summary["source"].is_(None)` does NOT
    work here — SQLAlchemy renders it as
    `JSON_QUOTE(JSON_EXTRACT(...)) IS NULL`, and JSON_QUOTE turns
    SQL NULL into JSON null, so the check is false even for NULL
    summaries. The coalesce form below is the tested shape (see
    test_job_store_unification)."""

    def _claimable() -> Any:
        source = db.Job.result_summary["source"].as_string()
        return func.coalesce(source, "") != "register"

    oldest_queued = (
        select(db.Job.id)
        .where(db.Job.status == "queued")
        .where(_claimable())
        .order_by(db.Job.created_at)
        .limit(1)
        .scalar_subquery()
    )
    now = datetime.now(UTC)
    result = session.execute(
        update(db.Job)
        .where(db.Job.id == oldest_queued, db.Job.status == "queued")
        .where(_claimable())
        .values(status="processing", started_at=now)
        .returning(db.Job.id)
    )
    row = result.first()
    if row is None:
        session.rollback()
        return None
    session.commit()
    claimed = session.get(db.Job, row[0])
    log.info(
        "worker claimed job",
        extra={"fields": {"job_id": str(row[0])}},
    )
    return claimed


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _cancel_requested(session: Session, job: db.Job) -> bool:
    """Re-read the job row (the cancel flag may have been set by
    the API after processing started)."""
    session.expire(job)
    summary = job.result_summary or {}
    return bool(summary.get("cancel_requested"))


def process_job(
    session: Session,
    job: db.Job,
    *,
    storage: StorageBackend,
    settings: Settings,
) -> dict:
    """Process one claimed (status='processing') job to done,
    failed, or cancelled. Returns a summary dict. Never raises
    for a job failure — the failure is recorded on the job row
    (status + error + ProcessingError row) and returned."""
    started = time.monotonic()
    recorder = SqlAlchemyStageRecorder(session)
    document = session.get(db.Document, job.document_id)
    stage_totals: dict[str, float] = {}
    last_fire = time.monotonic()
    current_stage = "ingest"
    summary: dict = {
        "job_id": str(job.id),
        "document_id": str(job.document_id),
        "status": "failed",
        "stages": stage_totals,
    }

    def on_stage(name: str, detail: dict) -> None:
        nonlocal last_fire, current_stage
        current_stage = name
        now = time.monotonic()
        delta = now - last_fire
        last_fire = now
        stage_totals[name] = round(stage_totals.get(name, 0.0) + delta, 2)
        metrics.observe_stage(name, delta)
        # Guarantees, checked at every stage boundary: cancel
        # first (a cancel is not a failure), then the timeout.
        if _cancel_requested(session, job):
            raise JobCancelled(name)
        if stage_totals[name] > settings.worker_stage_timeout_seconds:
            raise StageTimeout(name, stage_totals[name], settings.worker_stage_timeout_seconds)
        stage = HOOK_TO_STAGE.get(name)
        if stage is not None and document is not None:
            recorder.record(
                document_id=document.id,
                job_id=job.id,
                stage=stage,
                status="done",
                detail={**detail, "seconds": stage_totals[name]},
            )
        log.info(
            "job stage",
            extra={
                "fields": {
                    "job_id": str(job.id),
                    "stage": name,
                    "seconds": stage_totals[name],
                }
            },
        )

    try:
        if document is None:
            raise ValueError(f"document {job.document_id} not found for job {job.id}")
        if document.storage_path == "inline-parse" or not storage.exists(document.storage_path):
            raise ValueError(
                "no stored bytes for this job (sync-parse jobs are not re-processable)"
            )
        on_stage("ingest", {"storage_path": "stored", "file_type": document.file_type})
        data = storage.get(document.storage_path)
        parse = (
            parse_image_bytes
            if document.file_type in ("jpg", "png", "jpeg")
            else parse_document_bytes
        )
        matched, report, debug = parse(
            data,
            str(document.id),
            settings=settings,
            on_stage=on_stage,
        )
        persist_matched_document(
            session,
            document_id=document.id,
            job_id=job.id,
            matched=matched,
        )
        total_seconds = round(time.monotonic() - started, 1)
        # ADR-011: terminal job status is "done" (the live 015 check
        # constraint rejects "completed").
        job.status = "done"
        job.completed_at = _utcnow()
        job.result_summary = {
            "questions": matched.counts["questions"],
            "answered": matched.answered,
            "pending": len(matched.pending),
            "qa_pairs": len(matched.qa_pairs),
            "seconds": total_seconds,
            "stages": dict(stage_totals),
            "is_digital": debug["is_digital"],
            "page_count": debug["page_count"],
        }
        recorder.record(
            document_id=document.id,
            job_id=job.id,
            stage=PipelineStage.COMPLETED,
            status="done",
            detail={"seconds": total_seconds},
        )
        metrics.inc("jobs_total", {"status": "done"})
        session.commit()
        summary.update(
            {
                "status": "done",
                "seconds": total_seconds,
                "questions": matched.counts["questions"],
                "answered": matched.answered,
            }
        )
        log.info(
            "job completed",
            extra={
                "fields": {
                    "job_id": str(job.id),
                    "seconds": total_seconds,
                    "questions": matched.counts["questions"],
                    "answered": matched.answered,
                }
            },
        )
        return summary
    except JobCancelled as exc:
        job.status = "cancelled"
        job.completed_at = _utcnow()
        job.result_summary = {
            **(job.result_summary or {}),
            "cancelled_at_stage": exc.stage,
            "seconds": round(time.monotonic() - started, 1),
            "stages": dict(stage_totals),
        }
        if document is not None:
            recorder.record(
                document_id=document.id,
                job_id=job.id,
                stage=PipelineStage.FAILED,
                status="cancelled",
                detail={"stage": exc.stage},
            )
        metrics.inc("jobs_total", {"status": "cancelled"})
        session.commit()
        summary.update({"status": "cancelled", "cancelled_at_stage": exc.stage})
        log.info(
            "job cancelled",
            extra={"fields": {"job_id": str(job.id), "stage": exc.stage}},
        )
        return summary
    except StageTimeout as exc:
        _fail_job(
            session,
            job,
            document,
            recorder,
            exc.stage,
            str(exc),
            stage_totals,
            started,
            summary,
        )
        return summary
    except Exception as exc:  # noqa: BLE001 — a job failure must never crash the worker
        _fail_job(
            session,
            job,
            document,
            recorder,
            current_stage,
            str(exc)[:500],
            stage_totals,
            started,
            summary,
        )
        return summary


def _fail_job(session, job, document, recorder, stage, message, stage_totals, started, summary):
    """Record a job failure: job row (failed + error), a
    ProcessingError row, a failed stage row, metrics, log. The
    message never contains file contents — parse errors carry
    page numbers and codes only."""
    job.status = "failed"
    job.completed_at = _utcnow()
    job.error = message
    job.result_summary = {
        **(job.result_summary or {}),
        "failed_at_stage": stage,
        "seconds": round(time.monotonic() - started, 1),
        "stages": dict(stage_totals),
    }
    if document is not None:
        recorder.record_error(
            document_id=document.id,
            job_id=job.id,
            page_number=None,
            stage=stage,
            error_code="job_failed",
            message=message,
        )
        recorder.record(
            document_id=document.id,
            job_id=job.id,
            stage=PipelineStage.FAILED,
            status="failed",
            detail={"stage": stage, "error": message},
        )
    metrics.inc("jobs_total", {"status": "failed"})
    metrics.inc("errors_total", {"code": "job_failed"})
    session.commit()
    summary.update({"status": "failed", "error": message, "failed_at_stage": stage})
    log.info(
        "job failed",
        extra={"fields": {"job_id": str(job.id), "stage": stage, "error": message}},
    )


def get_job_status(session: Session, *, job_id: uuid.UUID, user_id: str) -> dict:
    """Job + its stage history for one user. 404 for unknown or
    other-user jobs — never leak existence."""
    job = session.get(db.Job, job_id)
    if job is None or str(job.user_id) != user_id:
        raise ApiError(status_code=404, code="not_found", message="Job not found.")
    stages = (
        session.query(db.ProcessingStage)
        .filter(db.ProcessingStage.job_id == job.id)
        .order_by(db.ProcessingStage.created_at)
        .all()
    )
    return {
        "job_id": str(job.id),
        "document_id": str(job.document_id),
        "status": job.status,
        "retry_count": job.retry_count,
        "error": job.error,
        "result_summary": job.result_summary,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "stages": [
            {
                "stage": s.stage,
                "status": s.status,
                "detail": s.detail,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in stages
        ],
    }


def cancel_job(session: Session, *, job_id: uuid.UUID, user_id: str) -> db.Job:
    """Cancel a job. Queued -> cancelled immediately. Processing
    -> flag it; the worker cancels at the next stage boundary and
    records it as cancelled. Anything else -> 409."""
    job = session.get(db.Job, job_id)
    if job is None or str(job.user_id) != user_id:
        raise ApiError(status_code=404, code="not_found", message="Job not found.")
    if job.status == "queued":
        job.status = "cancelled"
        job.completed_at = _utcnow()
        session.commit()
        metrics.inc("jobs_total", {"status": "cancelled"})
        log.info("job cancelled", extra={"fields": {"job_id": str(job.id)}})
        return job
    if job.status == "processing":
        job.result_summary = {**(job.result_summary or {}), "cancel_requested": True}
        session.commit()
        log.info(
            "job cancel requested",
            extra={"fields": {"job_id": str(job.id)}},
        )
        return job
    raise ApiError(
        status_code=409,
        code="job_not_cancellable",
        message=f"Only queued or processing jobs can be cancelled. Current status: {job.status}.",
    )


def retry_job(session: Session, *, job_id: uuid.UUID, user_id: str) -> db.Job:
    """Re-queue a failed or cancelled job (SQLAlchemy store).
    Mirrors services/jobs.retry_job for the Supabase store."""
    job = session.get(db.Job, job_id)
    if job is None or str(job.user_id) != user_id:
        raise ApiError(status_code=404, code="not_found", message="Job not found.")
    if job.status not in ("failed", "cancelled"):
        raise ApiError(
            status_code=409,
            code="job_not_retryable",
            message=(
                f"Only failed or cancelled jobs can be retried. Current status: {job.status}."
            ),
        )
    job.status = "queued"
    job.retry_count = int(job.retry_count or 0) + 1
    job.started_at = None
    job.completed_at = None
    job.error = None
    summary = dict(job.result_summary or {})
    summary.pop("cancel_requested", None)
    job.result_summary = summary
    session.commit()
    metrics.inc("jobs_total", {"status": "queued"})
    log.info(
        "job retried",
        extra={"fields": {"job_id": str(job.id), "retry_count": job.retry_count}},
    )
    return job
