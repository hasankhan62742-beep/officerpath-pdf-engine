# OfficerPath AI — A3: page inventory + completeness + per-page retry.
#
# Gap-report F7: retry was whole-job only, there was no
# GET /documents/{id}/pages, and the report had no per-page
# checklist. This module is the service layer for all three:
#
# - record_page_inventory: after a parse, upsert one
#   DocumentPage row per page (status / question count / error)
#   from the parse's matched result + debug dict.
# - get_page_inventory: the inventory + the completeness
#   comparison (expected vs extracted, missing numbers, zero /
#   low-confidence / failed pages).
# - create_page_retry_job / apply_page_retry: retry ONE page.
#
# Why a page retry re-parses the WHOLE document: answer-key
# detection and promotion are document-level — the trailing key
# may live on any page, and a question on page N is often
# answered from a key on page M. A page-only re-run would
# silently downgrade those answers to UNKNOWN (a worse result
# presented as a fix). So the retry re-runs the full parse and
# then replaces ONLY that page's stored rows: every other page's
# rows keep their ids, timestamps, and manual corrections. A
# page whose questions were manually corrected refuses the
# retry outright (409) instead of wiping the corrections.
#
# Statuses (stored on DocumentPage.extraction_status):
# - processed: questions found on the page.
# - no_questions: the page parsed cleanly and found nothing
#   (a blank page, a cover, a diagram-only page — not a failure).
# - failed: the pipeline itself failed for this page — OCR
#   returned no text from a page with ink, digital extraction
#   errored, or the page was classified unreadable with no
#   blocks at all.
# - low_confidence: the page parsed, but the kept OCR mean word
#   confidence stayed below the system's own PSM-4 retry bar
#   (85 — app/pipeline/ocr/psm.py). Digital pages never get
#   this status: their text is exact, not OCR'd.
#
# Nothing here fabricates answers: a retry can only replace
# stored rows with a fresh parse's rows, and a question the new
# parse cannot answer stays UNKNOWN.

from __future__ import annotations

import ast
import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models as db
from app.pipeline.matching.models import MatchedDocument
from app.pipeline.matching.store import rebuild_report_counts, replace_page_questions
from app.pipeline.ocr.psm import PSM4_RETRY_CONFIDENCE_THRESHOLD

#: Stored extraction statuses (DocumentPage.extraction_status).
PAGE_STATUSES = ("processed", "no_questions", "failed", "low_confidence")

#: Upper bound for an expected question count (a sanity cap, not
#: a measured limit — the largest real paper in the fixtures has
#: 1,375 questions).
MAX_EXPECTED_QUESTIONS = 100_000

#: Document.metadata key holding the expected question count.
EXPECTED_COUNT_KEY = "expected_question_count"

#: Ink coverage above which a rendered page visibly has content
#: (fraction of pixels darker than the Otsu threshold). A blank
#: page scores ~0; any text scores well above this. Used only to
#: separate "OCR failed" from "blank page".
INK_COVERAGE_THRESHOLD = 0.01


def _int_keys(mapping: dict | None) -> dict[int, Any]:
    """Debug dicts carry page numbers as str keys (JSON) or int
    keys (in-process) — normalise to int keys, dropping junk."""
    out: dict[int, Any] = {}
    for key, value in (mapping or {}).items():
        try:
            out[int(key)] = value
        except (TypeError, ValueError):
            continue
    return out


def mean_ocr_confidence(debug: dict, page_number: int) -> float | None:
    """Kept OCR mean word confidence for one page, from the
    PSM-4 retry info (mean_conf_psm4 when the retry was kept,
    else mean_conf_psm3). None when the page was not OCR'd this
    way (digital pages, multi-pass runs) — such a page is never
    flagged low-confidence for lack of a number."""
    retry = _int_keys(debug.get("psm4_retry_by_page"))
    info = retry.get(page_number) or {}
    if not isinstance(info, dict):
        return None
    if info.get("kept") and info.get("mean_conf_psm4") is not None:
        return float(info["mean_conf_psm4"])
    conf = info.get("mean_conf_psm3")
    return float(conf) if conf is not None else None


def derive_page_status(
    *,
    page_number: int,
    classification: str,
    block_count: int | None,
    question_count: int,
    ocr_error: str | None,
    mean_confidence: float | None,
) -> tuple[str, str | None]:
    """(status, error_message) for one inventoried page. Pure —
    unit-testable without a database. A pipeline error only
    fails the page when it left no usable blocks: on a mixed
    page the digital half can still carry the page, and the
    OCR miss is not a page failure then."""
    blocks = block_count or 0
    if ocr_error is not None and blocks == 0:
        return "failed", ocr_error
    if classification == "unreadable" and blocks == 0 and question_count == 0:
        return "failed", "page_unreadable_no_text"
    if mean_confidence is not None and mean_confidence < PSM4_RETRY_CONFIDENCE_THRESHOLD:
        return "low_confidence", None
    if question_count > 0:
        return "processed", None
    return "no_questions", None


def record_page_inventory(
    session: Session,
    *,
    document_id: uuid.UUID,
    job_id: uuid.UUID | None,
    matched: MatchedDocument,
    debug: dict,
) -> dict:
    """Upsert the DocumentPage inventory rows for one parse.
    Rows recorded at ingest keep their classification; rows
    missing entirely (sync-parse documents never recorded pages
    at ingest) are created from the debug classifications.
    Also fills the latest ExtractionReport's pages_processed /
    pages_failed, which persist_matched_document leaves at 0.
    Commits once at the end."""
    page_count = int(debug.get("page_count") or 0)
    if page_count <= 0:
        seen = [q.page for q in matched.questions if q.page]
        seen += [p.get("page", 0) for p in matched.pending if p.get("page")]
        page_count = max(seen) if seen else 1
    classifications = _int_keys(debug.get("page_classifications"))
    blocks = _int_keys(debug.get("blocks_by_page"))
    errors = _int_keys(debug.get("ocr_errors_by_page"))
    found: dict[int, int] = {}
    for question in matched.questions:
        if question.page:
            found[question.page] = found.get(question.page, 0) + 1
    for pending in matched.pending:
        page = pending.get("page", 0)
        if page:
            found[page] = found.get(page, 0) + 1
    existing = {
        row.page_number: row
        for row in session.query(db.DocumentPage)
        .filter(db.DocumentPage.document_id == document_id)
        .all()
    }
    summary = {
        "pages_total": page_count,
        "processed": 0,
        "no_questions": 0,
        "failed": 0,
        "low_confidence": 0,
    }
    for page_number in range(1, page_count + 1):
        row = existing.get(page_number)
        classification = (
            row.classification
            if row is not None
            else str(classifications.get(page_number, "unknown"))
        )
        status, error = derive_page_status(
            page_number=page_number,
            classification=classification,
            block_count=blocks.get(page_number),
            question_count=found.get(page_number, 0),
            ocr_error=errors.get(page_number),
            mean_confidence=mean_ocr_confidence(debug, page_number),
        )
        summary[status] += 1
        if row is None:
            row = db.DocumentPage(
                document_id=document_id,
                page_number=page_number,
                classification=classification,
                classification_method="a3-inventory",
                classification_confidence=None,
            )
            session.add(row)
        row.extraction_status = status
        row.question_count = found.get(page_number, 0)
        row.error_message = error
    report = (
        session.query(db.ExtractionReport)
        .filter(db.ExtractionReport.document_id == document_id)
        .order_by(db.ExtractionReport.created_at.desc())
        .first()
    )
    if report is not None:
        report.pages_processed = (
            summary["processed"] + summary["no_questions"] + summary["low_confidence"]
        )
        report.pages_failed = summary["failed"]
    session.commit()
    return summary


def expected_question_count(document: db.Document) -> int | None:
    """The expected count the owner set (Document.metadata), or
    None when nobody set one — no expectation is invented."""
    value = (document.metadata_json or {}).get(EXPECTED_COUNT_KEY)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _missing_numbers_from_report(report: db.ExtractionReport | None) -> tuple[list[int], bool]:
    """Missing question numbers from the latest report's
    number-gap validation message ("missing question numbers:
    [1, 2, ...]"). The message is capped at 20 numbers by the
    validator, so the flag says whether the list was cut."""
    if report is None:
        return [], False
    for reason in report.review_reasons or []:
        if not isinstance(reason, str):
            continue
        if not reason.startswith("missing question numbers:"):
            continue
        raw = reason[len("missing question numbers:") :].strip()
        truncated = raw.endswith("...")
        raw = raw.removesuffix("...").strip()
        try:
            parsed = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return [], truncated
        if isinstance(parsed, list) and all(isinstance(n, int) for n in parsed):
            return parsed, truncated
        return [], truncated
    return [], False


def count_stored_questions(session: Session, *, document_id: uuid.UUID) -> dict:
    """Document totals from the stored rows (the source of truth
    after any retry): extracted MCQs, answered, pending."""
    rows = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == document_id)
        .all()
    )
    return {
        "questions": sum(1 for r in rows if r.validation_status != "pending"),
        "answered": sum(
            1 for r in rows if r.validation_status in ("answered", "conflict-resolved")
        ),
        "pending": sum(1 for r in rows if r.validation_status == "pending"),
    }


def get_page_inventory(session: Session, *, document_id: uuid.UUID) -> dict:
    """The full inventory + completeness comparison for one
    document. Answered/unknown/pending splits come from the
    stored rows, grouped by their source page — never from the
    job summary, so a page retry is reflected immediately."""
    document = session.get(db.Document, document_id)
    if document is None:
        raise ApiError(status_code=404, code="not_found", message="Document not found.")
    page_rows = (
        session.query(db.DocumentPage)
        .filter(db.DocumentPage.document_id == document_id)
        .order_by(db.DocumentPage.page_number)
        .all()
    )
    question_rows = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == document_id)
        .all()
    )
    per_page: dict[int, dict[str, int]] = {}
    for row in question_rows:
        for page in row.source_pages or []:
            slot = per_page.setdefault(page, {"answered": 0, "unknown": 0, "pending": 0})
            if row.validation_status == "pending":
                slot["pending"] += 1
            elif row.validation_status == "unknown":
                slot["unknown"] += 1
            else:
                slot["answered"] += 1
    items = []
    for row in page_rows:
        slot = per_page.get(row.page_number, {"answered": 0, "unknown": 0, "pending": 0})
        items.append(
            {
                "page_number": row.page_number,
                "classification": row.classification,
                "extraction_status": row.extraction_status,
                "question_count": row.question_count or 0,
                "answered_count": slot["answered"],
                "unknown_count": slot["unknown"],
                "pending_count": slot["pending"],
                "error_message": row.error_message,
            }
        )
    expected = expected_question_count(document)
    totals = count_stored_questions(session, document_id=document_id)
    report = (
        session.query(db.ExtractionReport)
        .filter(db.ExtractionReport.document_id == document_id)
        .order_by(db.ExtractionReport.created_at.desc())
        .first()
    )
    missing_numbers, missing_truncated = _missing_numbers_from_report(report)
    return {
        "document_id": str(document_id),
        "page_count": document.page_count or len(items) or 0,
        "expected_question_count": expected,
        "extracted_question_count": totals["questions"],
        "pending_question_count": totals["pending"],
        "missing_question_count": (
            max(0, expected - totals["questions"]) if expected is not None else None
        ),
        "missing_numbers": missing_numbers,
        "missing_numbers_truncated": missing_truncated,
        "zero_question_pages": [i["page_number"] for i in items if i["question_count"] == 0],
        "low_confidence_pages": [
            i["page_number"] for i in items if i["extraction_status"] == "low_confidence"
        ],
        "failed_pages": [i["page_number"] for i in items if i["extraction_status"] == "failed"],
        "pages": items,
    }


def require_document_for_user(session: Session, document_id: str, user_id: str) -> db.Document:
    """The caller's own, not-deleted document — 404 otherwise
    (the Phase 1 pattern: never leak existence)."""
    try:
        doc_uuid = uuid.UUID(str(document_id))
    except (ValueError, TypeError, AttributeError):
        raise ApiError(status_code=404, code="not_found", message="Document not found.") from None
    document = session.get(db.Document, doc_uuid)
    if document is None or str(document.user_id) != user_id or document.deleted_at is not None:
        raise ApiError(status_code=404, code="not_found", message="Document not found.")
    return document


def set_expected_question_count(
    session: Session, *, document: db.Document, expected_count: int | None
) -> dict:
    """Store (or clear, with None) the expected question count
    in Document.metadata. The count is the owner's statement
    about the paper ("this paper has 100 questions") — it is
    never inferred from the extraction."""
    if expected_count is not None and (
        not isinstance(expected_count, int)
        or isinstance(expected_count, bool)
        or expected_count < 0
        or expected_count > MAX_EXPECTED_QUESTIONS
    ):
        raise ApiError(
            status_code=422,
            code="validation_error",
            message=(
                "expected_question_count must be an integer between 0 and "
                f"{MAX_EXPECTED_QUESTIONS}."
            ),
        )
    metadata = dict(document.metadata_json or {})
    if expected_count is None:
        metadata.pop(EXPECTED_COUNT_KEY, None)
    else:
        metadata[EXPECTED_COUNT_KEY] = expected_count
    document.metadata_json = metadata
    session.commit()
    totals = count_stored_questions(session, document_id=document.id)
    return {
        "document_id": str(document.id),
        "expected_question_count": expected_count,
        "extracted_question_count": totals["questions"],
        "missing_question_count": (
            max(0, expected_count - totals["questions"]) if expected_count is not None else None
        ),
    }


def create_page_retry_job(
    session: Session, *, document: db.Document, user_id: str, page_number: int
) -> dict:
    """Queue a background job that reprocesses ONE page (202
    semantics — the caller returns the job, the worker does the
    work). Refuses with 409 when the page cannot be retried
    (no stored bytes, or manually corrected questions on it)
    and with 422 for a page outside the document. An already
    queued/processing retry for the same page is returned
    instead of a duplicate."""
    page_count = document.page_count or 0
    if page_count <= 0:
        page_count = (
            session.query(func.max(db.DocumentPage.page_number))
            .filter(db.DocumentPage.document_id == document.id)
            .scalar()
            or 0
        )
    if page_number < 1 or page_number > page_count:
        raise ApiError(
            status_code=422,
            code="validation_error",
            message=f"Page {page_number} is out of range (1..{page_count}).",
        )
    if document.storage_path == "inline-parse":
        raise ApiError(
            status_code=409,
            code="page_retry_no_stored_bytes",
            message=(
                "This document has no stored file, so a single page cannot "
                "be reprocessed. Re-upload the file to retry it."
            ),
        )
    page_rows = [
        row
        for row in session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == document.id)
        .all()
        if page_number in (row.source_pages or [])
    ]
    if page_rows and (
        session.query(db.ManualCorrection)
        .filter(db.ManualCorrection.target_id.in_([r.id for r in page_rows]))
        .first()
        is not None
    ):
        raise ApiError(
            status_code=409,
            code="page_has_corrections",
            message=(
                "This page has manually corrected questions; retry refused "
                "so the corrections are not lost."
            ),
        )
    for job in (
        session.query(db.Job)
        .filter(
            db.Job.document_id == document.id,
            db.Job.status.in_(["queued", "processing"]),
        )
        .order_by(db.Job.created_at.desc())
        .all()
    ):
        if (job.result_summary or {}).get("page_retry") == page_number:
            return {
                "job_id": str(job.id),
                "document_id": str(document.id),
                "page_number": page_number,
                "status": job.status,
                "existing_job": True,
            }
    latest = (
        session.query(db.Job)
        .filter(db.Job.document_id == document.id)
        .order_by(db.Job.created_at.desc())
        .first()
    )
    multi_pass = bool((latest.result_summary or {}).get("multi_pass")) if latest else False
    job = db.Job(
        user_id=uuid.UUID(user_id),
        document_id=document.id,
        status="queued",
        retry_count=0,
        error=None,
        result_summary={
            "source": "page-retry",
            "page_retry": page_number,
            **({"multi_pass": True} if multi_pass else {}),
        },
    )
    session.add(job)
    session.commit()
    return {
        "job_id": str(job.id),
        "document_id": str(document.id),
        "page_number": page_number,
        "status": "queued",
        "existing_job": False,
    }


def apply_page_retry(
    session: Session,
    *,
    document_id: uuid.UUID,
    job_id: uuid.UUID | None,
    page_number: int,
    matched: MatchedDocument,
    debug: dict,
) -> dict:
    """Worker-side page retry: replace one page's rows with the
    fresh parse's results for that page, rebuild the report
    counts from the stored rows, and refresh the inventory.
    The parse itself is the full document (see the module
    docstring for why); only this page's rows are touched."""
    replaced = replace_page_questions(
        session,
        document_id=document_id,
        job_id=job_id,
        page_number=page_number,
        matched=matched,
    )
    counts = rebuild_report_counts(
        session,
        document_id=document_id,
        job_id=job_id,
        summary_extra={"page_retry": replaced},
    )
    inventory = record_page_inventory(
        session,
        document_id=document_id,
        job_id=job_id,
        matched=matched,
        debug=debug,
    )
    return {
        **replaced,
        "report_counts": counts,
        "inventory": inventory,
    }
