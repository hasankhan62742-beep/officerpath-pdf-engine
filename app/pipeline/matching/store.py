# OfficerPath AI — PDF Engine (Phase 1, M6)
# Persistence of matched results + manual corrections, on the M1
# schema (no migration — the tables already exist: extracted
# questions / options / answers / evidence / sources, extraction
# reports, manual corrections, review history).
#
# Rules:
# - Originals are immutable: a correction NEVER edits
#   ``original_text`` (question or option). It writes the
#   normalized field and records old/new values in
#   manual_corrections (audit), plus a review_history row.
# - An answer correction creates/updates the ExtractedAnswer row
#   (status "manually_verified") and appends a manual AnswerEvidence
#   row; the previous answer row is replaced only after its old
#   value is recorded in manual_corrections.
# - Evidence is append-only in spirit: a correction adds a new
#   evidence row; it never rewrites an existing detector's row.
# - Re-persisting a document replaces its matched rows (delete +
#   insert, one transaction) so a re-run never duplicates.
#
# The store takes a SQLAlchemy Session (the API builds it from
# get_session; tests pass an in-memory SQLite session).

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db import models as db
from app.pipeline.matching.models import MatchedDocument, ResolvedMCQ
from app.pipeline.matching.validate import validate_question

#: Correctable fields: question text, option text by index
#: ("option_text:0" .. "option_text:3"), answer letter ("answer").
CORRECTABLE_FIELDS = ("question_text", "answer")


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_field(field: str) -> tuple[str, int | None]:
    if field == "question_text":
        return "question_text", None
    if field == "answer":
        return "answer", None
    if field.startswith("option_text:"):
        try:
            index = int(field.split(":", 1)[1])
        except ValueError:
            raise ValueError(f"invalid option field {field!r}") from None
        if not 0 <= index < 4:
            raise ValueError(f"option index out of range in {field!r}")
        return "option_text", index
    raise ValueError(
        f"field {field!r} is not correctable (use question_text, option_text:<0-3>, or answer)"
    )


def _store_question(
    session: Session,
    *,
    document_id: uuid.UUID,
    job_id: uuid.UUID | None,
    question: ResolvedMCQ,
    validation_status: str,
    rule_set_version: str = "m6",
) -> db.ExtractedQuestion:
    """Store one resolved MCQ (+ options + answer + evidence) as
    an ExtractedQuestion row. Extracted from
    :func:`persist_matched_document` (A3) so a page-scoped
    replacement can store the same rows with the same shape —
    the two paths must never drift apart."""
    row = db.ExtractedQuestion(
        document_id=document_id,
        job_id=job_id,
        question_number=str(question.number) if question.number is not None else None,
        original_text=question.text,
        normalized_text=question.text,
        source_pages=[question.page] if question.page else None,
        extraction_method="m6-matching",
        rule_set_version=rule_set_version,
        extraction_confidence=question.confidence,
        validation_status=validation_status,
        duplicate_of_id=None,
    )
    session.add(row)
    session.flush()  # assign row.id for options/answers
    for position, option_text in enumerate(question.options):
        session.add(
            db.QuestionOption(
                question_id=row.id,
                original_label=chr(65 + position),
                normalized_label=chr(65 + position),
                label_inferred=False,
                original_text=option_text,
                normalized_text=option_text,
                position=position,
            )
        )
    if question.status == "answered" and question.correct_index >= 0:
        answer = db.ExtractedAnswer(
            question_id=row.id,
            document_id=document_id,
            status=(
                "verified_explicit_key"
                if question.verified
                else "detected_inline"
                if question.answer_source in ("inline", "trailing-key")
                else "detected_visual"
                if question.answer_source == "visual"
                else "detected_digital_style"
            ),
            resolved_label=question.correct_letter,
            resolution_method=question.answer_source,
            resolution_score=question.confidence,
        )
        session.add(answer)
        session.flush()
        for evidence in question.evidences:
            session.add(
                db.AnswerEvidence(
                    answer_id=answer.id,
                    source_type=evidence.get("detector", ""),
                    value_normalized=evidence.get("correct_letter", ""),
                    page_number=question.page or None,
                    detector=evidence.get("detector", ""),
                    detector_confidence=evidence.get("confidence"),
                    artifact_ref=evidence.get("evidence", ""),
                )
            )
    return row


def _question_dedup_key(question: ResolvedMCQ) -> tuple[str, tuple[str, ...]]:
    """Identity of a question for cross-page dedup: normalized
    text + options, collapsed whitespace, lowercased. Two rows
    with the same key are the same question even when the parse
    found it on two pages (page-break split, repeated header)."""

    def _norm(text: str) -> str:
        return " ".join(text.split()).lower()

    return (_norm(question.text), tuple(_norm(o) for o in question.options))


def _row_dedup_key(row: db.ExtractedQuestion, options: list[str]) -> tuple[str, tuple[str, ...]]:
    def _norm(text: str) -> str:
        return " ".join(text.split()).lower()

    return (_norm(row.normalized_text), tuple(_norm(o) for o in options))


def replace_page_questions(
    session: Session,
    *,
    document_id: uuid.UUID,
    job_id: uuid.UUID | None,
    page_number: int,
    matched: MatchedDocument,
    rule_set_version: str = "m6",
) -> dict:
    """Replace ONLY one page's stored questions with a fresh
    parse's results for that page (A3 page retry). Every other
    page's rows are untouched — their ids, timestamps, and any
    manual corrections on them survive. A new question that
    duplicates a question already stored on another page is
    skipped (counted, never inserted twice). Repeats inside the
    retried page itself are stored as-is, exactly like the
    original full parse stored them, so a deterministic re-parse
    reproduces the page's original rows. Raises ValueError
    when a question on this page has a manual correction — the
    retry must never silently wipe a user's correction; the
    caller turns that into a 409. Commits once at the end."""
    rows = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == document_id)
        .all()
    )
    page_rows = [r for r in rows if page_number in (r.source_pages or [])]
    if page_rows:
        corrected = (
            session.query(db.ManualCorrection)
            .filter(db.ManualCorrection.target_id.in_([r.id for r in page_rows]))
            .first()
        )
        if corrected is not None:
            raise ValueError(
                "page has manually corrected questions; retry refused "
                "so the corrections are not lost"
            )
    # Dedup keys of the questions that stay (other pages).
    kept_ids = {r.id for r in rows} - {r.id for r in page_rows}
    kept_options: dict[uuid.UUID, list[str]] = {}
    if kept_ids:
        for opt in (
            session.query(db.QuestionOption)
            .filter(db.QuestionOption.question_id.in_(list(kept_ids)))
            .order_by(db.QuestionOption.question_id, db.QuestionOption.position)
            .all()
        ):
            kept_options.setdefault(opt.question_id, []).append(opt.normalized_text)
    kept_keys = {_row_dedup_key(r, kept_options.get(r.id, [])) for r in rows if r.id in kept_ids}
    for row in page_rows:
        session.delete(row)
    session.flush()
    inserted = 0
    skipped_duplicates = 0
    candidates: list[tuple[ResolvedMCQ, str]] = [
        (q, q.status) for q in matched.questions if q.page == page_number
    ]
    for pending in matched.pending:
        if pending.get("page", 0) == page_number:
            candidates.append(
                (
                    ResolvedMCQ(
                        number=pending.get("number"),
                        text=pending.get("text", ""),
                        options=list(pending.get("options", [])),
                        status="unknown",
                        page=pending.get("page", 0),
                        paper=pending.get("paper", ""),
                    ),
                    "pending",
                )
            )
    for question, validation_status in candidates:
        key = _question_dedup_key(question)
        if key in kept_keys:
            skipped_duplicates += 1
            continue
        _store_question(
            session,
            document_id=document_id,
            job_id=job_id,
            question=question,
            validation_status=validation_status,
            rule_set_version=rule_set_version,
        )
        # NOTE: the key is deliberately NOT added to kept_keys.
        # persist_matched_document stores every parsed question,
        # including repeats of the same question inside one page
        # (the NOA Urdu fixture has 7 such repeats on page 2), so
        # a retry must store the same repeats to reproduce the
        # original page. Only duplicates of questions surviving on
        # OTHER pages are skipped.
        inserted += 1
    session.commit()
    return {
        "page": page_number,
        "replaced": len(page_rows),
        "inserted": inserted,
        "skipped_duplicates": skipped_duplicates,
    }


def rebuild_report_counts(
    session: Session,
    *,
    document_id: uuid.UUID,
    job_id: uuid.UUID | None,
    summary_extra: dict | None = None,
) -> dict | None:
    """Recompute a document's latest ExtractionReport question
    counts from the stored rows (A3: after a page retry changed
    one page's rows). Counts that cannot be derived from rows
    (duplicates_found, conflicting_answers, unmatched key
    entries) keep their previous values. Returns the new counts
    dict, or None when the document never had a report."""
    report = (
        session.query(db.ExtractionReport)
        .filter(db.ExtractionReport.document_id == document_id)
        .order_by(db.ExtractionReport.created_at.desc())
        .first()
    )
    if report is None:
        return None
    rows = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == document_id)
        .all()
    )
    option_counts: dict[uuid.UUID, int] = {}
    if rows:
        for opt in (
            session.query(db.QuestionOption)
            .filter(
                db.QuestionOption.question_id.in_([r.id for r in rows]),
            )
            .all()
        ):
            option_counts[opt.question_id] = option_counts.get(opt.question_id, 0) + 1
    questions = [r for r in rows if r.validation_status != "pending"]
    pending = [r for r in rows if r.validation_status == "pending"]
    report.questions_extracted = len(questions)
    report.questions_missing_options = sum(1 for r in questions if option_counts.get(r.id, 0) < 4)
    report.uncertain_answers = sum(1 for r in questions if r.validation_status == "unknown")
    report.requires_review = bool(
        pending or report.uncertain_answers or (report.review_reasons or [])
    )
    if summary_extra:
        report.summary = {**(report.summary or {}), **summary_extra}
    session.commit()
    return {
        "questions_extracted": report.questions_extracted,
        "questions_missing_options": report.questions_missing_options,
        "uncertain_answers": report.uncertain_answers,
        "pending": len(pending),
        "requires_review": report.requires_review,
    }


def persist_matched_document(
    session: Session,
    *,
    document_id: uuid.UUID,
    job_id: uuid.UUID | None,
    matched: MatchedDocument,
    rule_set_version: str = "m6",
) -> dict:
    """Persist a matched document's questions + pending items +
    report. Re-persisting replaces the document's matched rows.
    Returns counts. Q&A pairs are NOT stored as questions (they
    have no options by design); their count lives in the report."""
    # Replace previous matched rows for this document.
    existing = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == document_id)
        .all()
    )
    for row in existing:
        session.delete(row)
    session.query(db.ExtractionReport).filter(
        db.ExtractionReport.document_id == document_id
    ).delete()
    session.flush()

    stored_questions = 0
    stored_pending = 0

    for question in matched.questions:
        status = question.status  # answered | unknown | conflict-resolved
        _store_question(
            session,
            document_id=document_id,
            job_id=job_id,
            question=question,
            validation_status=status,
            rule_set_version=rule_set_version,
        )
        stored_questions += 1
    for pending in matched.pending:
        pending_mcq = ResolvedMCQ(
            number=pending.get("number"),
            text=pending.get("text", ""),
            options=list(pending.get("options", [])),
            status="unknown",
            page=pending.get("page", 0),
            paper=pending.get("paper", ""),
        )
        _store_question(
            session,
            document_id=document_id,
            job_id=job_id,
            question=pending_mcq,
            validation_status="pending",
            rule_set_version=rule_set_version,
        )
        stored_pending += 1
    report = db.ExtractionReport(
        document_id=document_id,
        job_id=job_id,
        rule_set_version=rule_set_version,
        pages_processed=0,
        pages_failed=0,
        questions_extracted=len(matched.questions),
        questions_missing_options=sum(1 for q in matched.questions if len(q.options) < 4),
        uncertain_answers=matched.unknown,
        conflicting_answers=sum(1 for q in matched.questions if q.conflicts),
        unmatched_key_entries=0,
        duplicates_found=sum(1 for q in matched.questions if q.duplicate),
        engine_disagreements=0,
        requires_review=bool(matched.pending or matched.unknown or matched.validation_issues),
        review_reasons=[i.message for i in matched.validation_issues[:20]],
        summary={
            "counts": dict(matched.counts),
            "qa_pairs": len(matched.qa_pairs),
            "pending": len(matched.pending),
            "promotion": dict(matched.promotion),
        },
    )
    session.add(report)
    session.commit()
    return {
        "questions_stored": stored_questions,
        "pending_stored": stored_pending,
        "qa_pairs_reported_only": len(matched.qa_pairs),
        "requires_review": report.requires_review,
    }


def list_review_items(session: Session, *, job_id: uuid.UUID) -> list[dict]:
    """Pending + unknown questions for a job, oldest first.
    Returns dicts (question id, number, text, options, status,
    page) — the review list. Answered questions are NOT listed."""
    rows = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.job_id == job_id)
        .filter(db.ExtractedQuestion.validation_status.in_(("pending", "unknown")))
        .order_by(db.ExtractedQuestion.created_at)
        .all()
    )
    items: list[dict] = []
    for row in rows:
        options = (
            session.query(db.QuestionOption)
            .filter(db.QuestionOption.question_id == row.id)
            .order_by(db.QuestionOption.position)
            .all()
        )
        items.append(
            {
                "question_id": str(row.id),
                "document_id": str(row.document_id),
                "number": row.question_number,
                "text": row.normalized_text,
                "options": [o.normalized_text for o in options],
                "status": row.validation_status,
                "page": row.source_pages[0] if row.source_pages else None,
            }
        )
    return items


def _row_to_resolved_mcq(session: Session, row: db.ExtractedQuestion) -> ResolvedMCQ:
    options = (
        session.query(db.QuestionOption)
        .filter(db.QuestionOption.question_id == row.id)
        .order_by(db.QuestionOption.position)
        .all()
    )
    answer = (
        session.query(db.ExtractedAnswer)
        .filter(db.ExtractedAnswer.question_id == row.id)
        .order_by(db.ExtractedAnswer.created_at.desc())
        .first()
    )
    correct_index = -1
    if answer is not None and answer.resolved_label:
        correct_index = ord(answer.resolved_label) - ord("A")
    qn = row.question_number or ""
    number = int(qn) if qn.isdigit() else None
    return ResolvedMCQ(
        number=number,
        text=row.normalized_text,
        options=[o.normalized_text for o in options],
        correct_index=correct_index,
        answer_source=answer.resolution_method or "" if answer else "",
        confidence=answer.resolution_score or 0.0 if answer else 0.0,
        raw_confidence=answer.resolution_score or 0.0 if answer else 0.0,
        verified=answer.status == "manually_verified" if answer else False,
        status="answered" if correct_index >= 0 else "unknown",
        page=(row.source_pages or [0])[0] or 0,
        paper="",
    )


def apply_manual_correction(
    session: Session,
    *,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    question_id: uuid.UUID,
    field: str,
    new_value: str,
    reason: str = "",
) -> dict:
    """Apply a manual correction to one stored question. The
    original extraction is never edited (original_* untouched);
    the correction writes the normalized field, records old/new
    in manual_corrections, appends a review_history row, and
    re-runs validation on the corrected question. Returns the
    corrected question + its validation issues. Raises ValueError
    for an unknown question / field / value."""
    kind, index = _parse_field(field)
    row = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.id == question_id)
        .filter(db.ExtractedQuestion.document_id == document_id)
        .first()
    )
    if row is None:
        raise ValueError(f"question {question_id} not found in document {document_id}")
    old_value: str | None = None
    if kind == "question_text":
        old_value = row.normalized_text
        row.normalized_text = new_value
    elif kind == "option_text":
        options = (
            session.query(db.QuestionOption)
            .filter(db.QuestionOption.question_id == row.id)
            .order_by(db.QuestionOption.position)
            .all()
        )
        if index is None or index >= len(options):
            raise ValueError(f"option index {index} out of range for this question")
        old_value = options[index].normalized_text
        options[index].normalized_text = new_value
    elif kind == "answer":
        letter = new_value.strip().upper()
        options = (
            session.query(db.QuestionOption)
            .filter(db.QuestionOption.question_id == row.id)
            .order_by(db.QuestionOption.position)
            .all()
        )
        if letter not in [chr(65 + i) for i in range(len(options))]:
            raise ValueError(f"answer {letter!r} is not one of this question's options")
        old_answer = (
            session.query(db.ExtractedAnswer)
            .filter(db.ExtractedAnswer.question_id == row.id)
            .order_by(db.ExtractedAnswer.created_at.desc())
            .first()
        )
        old_value = old_answer.resolved_label if old_answer is not None else None
        if old_answer is None:
            answer = db.ExtractedAnswer(
                question_id=row.id,
                document_id=document_id,
                status="manually_verified",
                resolved_label=letter,
                resolution_method="manual",
                resolution_score=1.0,
            )
            session.add(answer)
            session.flush()
        else:
            old_answer.status = "manually_verified"
            old_answer.resolved_label = letter
            old_answer.resolution_method = "manual"
            old_answer.resolution_score = 1.0
            old_answer.updated_at = _now()
            answer = old_answer
        session.add(
            db.AnswerEvidence(
                answer_id=answer.id,
                source_type="manual",
                value_normalized=letter,
                detector="manual",
                detector_confidence=1.0,
                artifact_ref=reason or "manual correction",
            )
        )
        row.validation_status = "answered"
    session.add(
        db.ManualCorrection(
            document_id=document_id,
            user_id=user_id,
            target_type="question" if kind != "option_text" else "option",
            target_id=row.id,
            field_name=field,
            old_value=old_value,
            new_value=new_value,
            reason=reason or None,
        )
    )
    session.add(
        db.ReviewHistory(
            document_id=document_id,
            reviewer_id=user_id,
            target_type="question",
            target_id=row.id,
            decision="corrected",
            note=f"{field}: {old_value!r} -> {new_value!r}" + (f" ({reason})" if reason else ""),
        )
    )
    session.commit()
    corrected = _row_to_resolved_mcq(session, row)
    issues = validate_question(corrected)
    return {
        "question_id": str(row.id),
        "number": row.question_number,
        "field": field,
        "old_value": old_value,
        "new_value": new_value,
        "validation_status": row.validation_status,
        "validation_issues": [i.to_dict() for i in issues],
    }


def get_document_report(session: Session, *, document_id: uuid.UUID) -> dict | None:
    """The latest stored extraction report for a document, or None
    when nothing was ever persisted for it."""
    report = (
        session.query(db.ExtractionReport)
        .filter(db.ExtractionReport.document_id == document_id)
        .order_by(db.ExtractionReport.created_at.desc())
        .first()
    )
    if report is None:
        return None
    return {
        "document_id": str(report.document_id),
        "job_id": str(report.job_id) if report.job_id else None,
        "rule_set_version": report.rule_set_version,
        "questions_extracted": report.questions_extracted,
        "questions_missing_options": report.questions_missing_options,
        "uncertain_answers": report.uncertain_answers,
        "conflicting_answers": report.conflicting_answers,
        "unmatched_key_entries": report.unmatched_key_entries,
        "duplicates_found": report.duplicates_found,
        "requires_review": report.requires_review,
        "review_reasons": list(report.review_reasons or []),
        "summary": dict(report.summary or {}),
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }
