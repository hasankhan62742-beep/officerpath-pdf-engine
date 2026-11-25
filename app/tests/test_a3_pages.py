# OfficerPath AI — A3 tests: page inventory + completeness +
# per-page retry (gap-report F7).
#
# Coverage: status derivation (pure), inventory recording,
# expected-vs-extracted comparison + missing numbers, page-scoped
# replacement (preserves other pages, skips cross-page
# duplicates, refuses corrected pages), the three new API
# endpoints (ownership + validation + idempotency), the sync
# parse path recording inventory, and the worker running a real
# page-retry job end to end on the NOA Urdu fixture (digital,
# 9 pages — fast, multi-page, deterministic).

import uuid
from pathlib import Path

import pytest

from app.core.errors import ApiError
from app.db import models as db
from app.pipeline.matching.models import MatchedDocument, ResolvedMCQ, ValidationIssue
from app.pipeline.matching.store import (
    apply_manual_correction,
    persist_matched_document,
    replace_page_questions,
)
from app.services import pages as page_service
from app.tests.conftest import USER_A, auth_headers
from app.workers.runner import run_once

NOA_URDU = Path(__file__).parent / "fixtures" / "golden" / "ppsc66" / "PDF_Urdu_MCQs_NOA.pdf"
TXT_FIXTURE = Path(__file__).parent / "fixtures" / "text" / "two-mcq-with-key.txt"


def _mcq(number, text, page, status="answered"):
    return ResolvedMCQ(
        number=number,
        text=text,
        options=["Alpha", "Beta", "Gamma", "Delta"],
        correct_index=0 if status == "answered" else -1,
        answer_source="inline" if status == "answered" else "",
        confidence=0.9 if status == "answered" else 0.0,
        status=status,
        page=page,
    )


def _matched(questions, pending=None, issues=None):
    return MatchedDocument(
        questions=list(questions),
        qa_pairs=[],
        pending=list(pending or []),
        validation_issues=list(issues or []),
        counts={"questions": len(questions)},
    )


def _seed_document(session, user_id=USER_A, **overrides):
    document = db.Document(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user_id),
        title=overrides.get("title", "paper.pdf"),
        storage_path=overrides.get("storage_path", f"{user_id}/paper.pdf"),
        file_type=overrides.get("file_type", "pdf"),
        file_size_bytes=1234,
        page_count=overrides.get("page_count", 3),
        content_hash="a" * 64,
    )
    session.add(document)
    session.commit()
    return document


def _seed_pages(session, document_id, classifications):
    for page_number, classification in classifications.items():
        session.add(
            db.DocumentPage(
                document_id=document_id,
                page_number=page_number,
                classification=classification,
                classification_method="test",
                classification_confidence=0.9,
            )
        )
    session.commit()


# ------------------------------------------------------------------
# Pure status derivation
# ------------------------------------------------------------------


def test_derive_page_status_matrix():
    base = {
        "page_number": 1,
        "classification": "digital",
        "block_count": 5,
        "question_count": 2,
        "ocr_error": None,
        "mean_confidence": None,
    }
    assert page_service.derive_page_status(**base) == ("processed", None)
    assert page_service.derive_page_status(**{**base, "question_count": 0}) == (
        "no_questions",
        None,
    )
    # A pipeline error with no usable blocks fails the page.
    assert page_service.derive_page_status(
        **{**base, "block_count": 0, "question_count": 0, "ocr_error": "ocr_returned_no_text"}
    ) == ("failed", "ocr_returned_no_text")
    # ... but on a mixed page the digital half can still carry it.
    assert page_service.derive_page_status(**{**base, "ocr_error": "ocr_returned_no_text"}) == (
        "processed",
        None,
    )
    # Unreadable classification, nothing at all on the page.
    assert page_service.derive_page_status(
        **{**base, "classification": "unreadable", "block_count": 0, "question_count": 0}
    ) == ("failed", "page_unreadable_no_text")
    # Below the system's own 85 bar (M15) — low confidence even
    # with questions found.
    assert page_service.derive_page_status(**{**base, "mean_confidence": 60.0}) == (
        "low_confidence",
        None,
    )
    assert page_service.derive_page_status(**{**base, "mean_confidence": 85.0}) == (
        "processed",
        None,
    )
    # A failed page beats low confidence.
    assert page_service.derive_page_status(
        **{
            **base,
            "block_count": 0,
            "question_count": 0,
            "ocr_error": "ocr_returned_no_text",
            "mean_confidence": 10.0,
        }
    ) == ("failed", "ocr_returned_no_text")


def test_mean_ocr_confidence_kept_retry_wins():
    debug = {
        "psm4_retry_by_page": {
            "1": {
                "retried": True,
                "kept": True,
                "mean_conf_psm3": 55.0,
                "mean_conf_psm4": 70.0,
            },
            "2": {
                "retried": True,
                "kept": False,
                "mean_conf_psm3": 80.0,
                "mean_conf_psm4": 75.0,
            },
        }
    }
    assert page_service.mean_ocr_confidence(debug, 1) == 70.0
    assert page_service.mean_ocr_confidence(debug, 2) == 80.0
    assert page_service.mean_ocr_confidence(debug, 3) is None
    assert page_service.mean_ocr_confidence({}, 1) is None


# ------------------------------------------------------------------
# Inventory recording (service level, throwaway SQLite)
# ------------------------------------------------------------------


def _debug(**overrides):
    debug = {
        "page_count": 3,
        "page_classifications": {"1": "digital", "2": "scanned", "3": "scanned"},
        "blocks_by_page": {"1": 5, "2": 4, "3": 2},
        "ocr_errors_by_page": {},
        "psm4_retry_by_page": {},
    }
    debug.update(overrides)
    return debug


def test_record_page_inventory_digital_doc(engine_db):
    session = engine_db()
    document = _seed_document(session)
    matched = _matched(
        [_mcq(1, "Q one", 1), _mcq(2, "Q two", 1), _mcq(3, "Q three", 2)],
        pending=[{"number": 4, "text": "Q four", "options": [], "page": 2}],
    )
    persist_matched_document(session, document_id=document.id, job_id=None, matched=matched)
    summary = page_service.record_page_inventory(
        session,
        document_id=document.id,
        job_id=None,
        matched=matched,
        debug=_debug(),
    )
    assert summary == {
        "pages_total": 3,
        "processed": 2,
        "no_questions": 1,
        "failed": 0,
        "low_confidence": 0,
    }
    rows = (
        session.query(db.DocumentPage)
        .filter(db.DocumentPage.document_id == document.id)
        .order_by(db.DocumentPage.page_number)
        .all()
    )
    assert [(r.page_number, r.extraction_status, r.question_count) for r in rows] == [
        (1, "processed", 2),
        (2, "processed", 2),
        (3, "no_questions", 0),
    ]
    # The report's page counters (persist leaves them 0) are filled.
    report = (
        session.query(db.ExtractionReport)
        .filter(db.ExtractionReport.document_id == document.id)
        .first()
    )
    assert report.pages_processed == 3
    assert report.pages_failed == 0
    session.close()


def test_record_page_inventory_failed_and_low_confidence(engine_db):
    session = engine_db()
    document = _seed_document(session)
    matched = _matched([_mcq(1, "Q one", 1)])
    summary = page_service.record_page_inventory(
        session,
        document_id=document.id,
        job_id=None,
        matched=matched,
        debug=_debug(
            blocks_by_page={"1": 5, "2": 0, "3": 3},
            ocr_errors_by_page={"2": "ocr_returned_no_text"},
            psm4_retry_by_page={
                "3": {
                    "retried": True,
                    "kept": True,
                    "mean_conf_psm3": 50.0,
                    "mean_conf_psm4": 60.0,
                }
            },
        ),
    )
    assert summary["failed"] == 1
    assert summary["low_confidence"] == 1
    rows = {
        r.page_number: r
        for r in session.query(db.DocumentPage)
        .filter(db.DocumentPage.document_id == document.id)
        .all()
    }
    assert rows[2].extraction_status == "failed"
    assert rows[2].error_message == "ocr_returned_no_text"
    assert rows[3].extraction_status == "low_confidence"
    assert rows[3].error_message is None
    session.close()


def test_get_page_inventory_expected_vs_missing(engine_db):
    session = engine_db()
    document = _seed_document(session)
    matched = _matched(
        [_mcq(n, f"Q {n}", 1) for n in (1, 2, 3, 4, 7)],
        issues=[ValidationIssue(code="number-gap", message="missing question numbers: [5, 6]")],
    )
    persist_matched_document(session, document_id=document.id, job_id=None, matched=matched)
    page_service.record_page_inventory(
        session, document_id=document.id, job_id=None, matched=matched, debug=_debug()
    )
    # No expectation set yet: nothing is "missing".
    inventory = page_service.get_page_inventory(session, document_id=document.id)
    assert inventory["expected_question_count"] is None
    assert inventory["missing_question_count"] is None
    assert inventory["extracted_question_count"] == 5
    assert inventory["missing_numbers"] == [5, 6]
    assert inventory["missing_numbers_truncated"] is False
    # The owner says the paper has 7 questions: 2 are missing.
    page_service.set_expected_question_count(session, document=document, expected_count=7)
    inventory = page_service.get_page_inventory(session, document_id=document.id)
    assert inventory["expected_question_count"] == 7
    assert inventory["missing_question_count"] == 2
    assert inventory["zero_question_pages"] == [2, 3]
    session.close()


def test_set_expected_question_count_validation(engine_db):
    session = engine_db()
    document = _seed_document(session)
    with pytest.raises(ApiError) as exc:
        page_service.set_expected_question_count(session, document=document, expected_count=-1)
    assert exc.value.status_code == 422
    with pytest.raises(ApiError):
        page_service.set_expected_question_count(session, document=document, expected_count=100_001)
    result = page_service.set_expected_question_count(
        session, document=document, expected_count=None
    )
    assert result["expected_question_count"] is None
    assert result["missing_question_count"] is None
    session.close()


# ------------------------------------------------------------------
# Page-scoped replacement
# ------------------------------------------------------------------


def _seed_three_page_doc(session):
    document = _seed_document(session)
    matched = _matched(
        [
            _mcq(1, "Page one Q1", 1),
            _mcq(2, "Page one Q2", 1),
            _mcq(3, "Page two Q1", 2),
            _mcq(4, "Page three Q1", 3),
        ]
    )
    persist_matched_document(session, document_id=document.id, job_id=None, matched=matched)
    return document


def _rows_by_page(session, document_id):
    rows = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == document_id)
        .all()
    )
    by_page: dict[int, list] = {}
    for row in rows:
        for page in row.source_pages or []:
            by_page.setdefault(page, []).append(row)
    return by_page


def test_replace_page_questions_preserves_other_pages(engine_db):
    session = engine_db()
    document = _seed_three_page_doc(session)
    before = _rows_by_page(session, document.id)
    page1_ids = {r.id for r in before[1]}
    page3_ids = {r.id for r in before[3]}
    # Fresh parse: page 2 has one genuinely new question plus a
    # duplicate of a page-1 question (same text + options, found
    # again on page 2 — e.g. a repeated header).
    fresh = _matched(
        [
            _mcq(3, "Page two Q1 redone", 2),
            _mcq(9, "Page one Q1", 2),
        ]
    )
    outcome = replace_page_questions(
        session,
        document_id=document.id,
        job_id=None,
        page_number=2,
        matched=fresh,
    )
    assert outcome == {"page": 2, "replaced": 1, "inserted": 1, "skipped_duplicates": 1}
    after = _rows_by_page(session, document.id)
    assert {r.id for r in after[1]} == page1_ids
    assert {r.id for r in after[3]} == page3_ids
    assert len(after[2]) == 1
    assert after[2][0].normalized_text == "Page two Q1 redone"
    assert after[2][0].id not in {r.id for r in before[2]}
    session.close()


def test_replace_page_questions_refuses_corrected_page(engine_db):
    session = engine_db()
    document = _seed_three_page_doc(session)
    target = _rows_by_page(session, document.id)[2][0]
    apply_manual_correction(
        session,
        document_id=document.id,
        user_id=uuid.UUID(USER_A),
        question_id=target.id,
        field="question_text",
        new_value="Page two Q1 (corrected)",
        reason="test correction",
    )
    with pytest.raises(ValueError, match="manually corrected"):
        replace_page_questions(
            session,
            document_id=document.id,
            job_id=None,
            page_number=2,
            matched=_matched([_mcq(3, "Page two Q1 redone", 2)]),
        )
    # Nothing was deleted: the corrected row is still there.
    assert len(_rows_by_page(session, document.id)[2]) == 1
    session.close()


# ------------------------------------------------------------------
# API endpoints
# ------------------------------------------------------------------


def _seed_api_doc(engine_db, **overrides):
    """Seed a document + 3 page rows; returns the document id (the
    ORM object is detached once the session closes)."""
    session = engine_db()
    document = _seed_document(session, **overrides)
    _seed_pages(session, document.id, {1: "digital", 2: "scanned", 3: "scanned"})
    document_id = document.id
    session.close()
    return document_id


def test_pages_endpoint_lists_inventory_and_enforces_ownership(client, engine_db):
    document_id = _seed_api_doc(engine_db)
    session = engine_db()
    row = (
        session.query(db.DocumentPage)
        .filter(
            db.DocumentPage.document_id == document_id,
            db.DocumentPage.page_number == 1,
        )
        .first()
    )
    row.extraction_status = "processed"
    row.question_count = 2
    session.commit()
    session.close()
    res = client.get(f"/api/v1/documents/{document_id}/pages", headers=auth_headers("token-user-a"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["document_id"] == str(document_id)
    assert body["page_count"] == 3
    assert len(body["pages"]) == 3
    assert body["pages"][0]["extraction_status"] == "processed"
    assert body["pages"][0]["question_count"] == 2
    assert body["pages"][1]["extraction_status"] is None
    assert body["zero_question_pages"] == [2, 3]
    # Another user gets 404, no token gets 401, garbage id gets 404.
    assert (
        client.get(
            f"/api/v1/documents/{document_id}/pages",
            headers=auth_headers("token-user-b"),
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/documents/{document_id}/pages").status_code == 401
    assert (
        client.get(
            "/api/v1/documents/not-a-uuid/pages", headers=auth_headers("token-user-a")
        ).status_code
        == 404
    )


def test_patch_expected_count(client, engine_db):
    document_id = _seed_api_doc(engine_db)
    res = client.patch(
        f"/api/v1/documents/{document_id}",
        json={"expected_question_count": 100},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["expected_question_count"] == 100
    assert res.json()["missing_question_count"] == 100  # nothing extracted yet
    # Negative is a 422; clearing with null works.
    assert (
        client.patch(
            f"/api/v1/documents/{document_id}",
            json={"expected_question_count": -1},
            headers=auth_headers("token-user-a"),
        ).status_code
        == 422
    )
    res = client.patch(
        f"/api/v1/documents/{document_id}",
        json={"expected_question_count": None},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200
    assert res.json()["expected_question_count"] is None
    assert res.json()["missing_question_count"] is None
    # Another user's document is 404.
    assert (
        client.patch(
            f"/api/v1/documents/{document_id}",
            json={"expected_question_count": 5},
            headers=auth_headers("token-user-b"),
        ).status_code
        == 404
    )


def test_page_retry_endpoint_queues_job_and_is_idempotent(client, engine_db):
    document_id = _seed_api_doc(engine_db)
    res = client.post(
        f"/api/v1/documents/{document_id}/pages/1/retry",
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["page_number"] == 1
    assert body["status"] == "queued"
    assert body["existing_job"] is False
    session = engine_db()
    job = session.get(db.Job, uuid.UUID(body["job_id"]))
    assert (job.result_summary or {}).get("page_retry") == 1
    assert (job.result_summary or {}).get("source") == "page-retry"
    session.close()
    # Second identical request returns the same queued job.
    res2 = client.post(
        f"/api/v1/documents/{document_id}/pages/1/retry",
        headers=auth_headers("token-user-a"),
    )
    assert res2.status_code == 202
    assert res2.json()["existing_job"] is True
    assert res2.json()["job_id"] == body["job_id"]
    # Page outside the document is 422; another user is 404.
    assert (
        client.post(
            f"/api/v1/documents/{document_id}/pages/99/retry",
            headers=auth_headers("token-user-a"),
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/documents/{document_id}/pages/1/retry",
            headers=auth_headers("token-user-b"),
        ).status_code
        == 404
    )


def test_page_retry_endpoint_refuses_inline_parse_docs(client, engine_db):
    document_id = _seed_api_doc(engine_db, storage_path="inline-parse")
    res = client.post(
        f"/api/v1/documents/{document_id}/pages/1/retry",
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 409, res.text
    assert res.json()["error"]["code"] == "page_retry_no_stored_bytes"


def test_page_retry_endpoint_refuses_corrected_page(client, engine_db):
    session = engine_db()
    document = _seed_document(session)
    document_id = document.id
    matched = _matched([_mcq(1, "Page one Q1", 1)])
    persist_matched_document(session, document_id=document_id, job_id=None, matched=matched)
    target = _rows_by_page(session, document_id)[1][0]
    apply_manual_correction(
        session,
        document_id=document_id,
        user_id=uuid.UUID(USER_A),
        question_id=target.id,
        field="question_text",
        new_value="Page one Q1 (corrected)",
        reason="test correction",
    )
    session.close()
    res = client.post(
        f"/api/v1/documents/{document_id}/pages/1/retry",
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 409, res.text
    assert res.json()["error"]["code"] == "page_has_corrections"


# ------------------------------------------------------------------
# Sync parse path + worker end to end
# ------------------------------------------------------------------


def test_sync_parse_records_inventory(client, engine_db):
    res = client.post(
        "/api/v1/documents/parse",
        files={"file": ("two-mcq-with-key.txt", TXT_FIXTURE.read_bytes(), "text/plain")},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["persisted"] is True
    document_id = res.json()["document_id"]
    pages = client.get(
        f"/api/v1/documents/{document_id}/pages", headers=auth_headers("token-user-a")
    )
    assert pages.status_code == 200, pages.text
    body = pages.json()
    assert body["page_count"] == 1
    assert len(body["pages"]) == 1
    assert body["pages"][0]["classification"] == "digital"
    assert body["pages"][0]["extraction_status"] == "processed"
    assert body["pages"][0]["question_count"] == 2
    assert body["extracted_question_count"] == 2


def test_page_retry_worker_replaces_only_target_page(client, engine_db):
    """NOA Urdu (digital, 9 pages): upload -> worker -> retry
    page 2 -> worker. Other pages keep their row ids; page 2
    gets fresh rows for the same questions; totals unchanged."""
    data = NOA_URDU.read_bytes()
    res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("urdu.pdf", data, "application/pdf")},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    document_id = res.json()["document"]["id"]
    first = run_once(engine_db)
    assert first is not None and first["status"] == "done", first
    assert first["questions"] >= 15, first  # A1 floor for NOA Maths' sibling
    session = engine_db()
    before = _rows_by_page(session, uuid.UUID(document_id))
    assert len(before) >= 2, f"expected questions on >=2 pages, got {sorted(before)}"
    page2_before_ids = {r.id for r in before.get(2, [])}
    other_before_ids = {r.id for rows in before.values() for r in rows} - page2_before_ids
    session.close()
    retry = client.post(
        f"/api/v1/documents/{document_id}/pages/2/retry",
        headers=auth_headers("token-user-a"),
    )
    assert retry.status_code == 202, retry.text
    second = run_once(engine_db)
    assert second is not None and second["status"] == "done", second
    assert second["questions"] == first["questions"]
    assert (second.get("page_retry_outcome") or {}).get("page") == 2
    session = engine_db()
    after = _rows_by_page(session, uuid.UUID(document_id))
    after_ids = {r.id for rows in after.values() for r in rows}
    assert other_before_ids <= after_ids, "other pages' rows must survive the retry"
    assert not ({r.id for r in after.get(2, [])} & page2_before_ids), (
        "page 2 rows must be fresh rows, not the old ones"
    )
    session.close()
    pages = client.get(
        f"/api/v1/documents/{document_id}/pages", headers=auth_headers("token-user-a")
    )
    assert pages.status_code == 200
    body = pages.json()
    assert body["page_count"] == 9
    assert all(p["extraction_status"] is not None for p in body["pages"])
    # A page's question_count covers questions AND pending items
    # found on that page (the engine's questions/pending split is
    # kept separate in the headline counts), so the per-page sum
    # equals extracted + pending, not extracted alone.
    assert sum(p["question_count"] for p in body["pages"]) == (
        body["extracted_question_count"] + body["pending_question_count"]
    )
