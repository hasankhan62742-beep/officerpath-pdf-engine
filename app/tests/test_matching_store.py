# OfficerPath AI — PDF Engine (Phase 1, M6)
# Persistence + review + manual-correction tests (in-memory SQLite).

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import models as db
from app.db.models import Base
from app.pipeline.matching.models import MatchedDocument, ResolvedMCQ
from app.pipeline.matching.store import (
    apply_manual_correction,
    get_document_report,
    list_review_items,
    persist_matched_document,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


def _matched() -> MatchedDocument:
    return MatchedDocument(
        questions=[
            ResolvedMCQ(
                number=1,
                text="Q1?",
                options=["A", "B", "C", "D"],
                correct_index=1,
                answer_source="trailing-key",
                confidence=1.0,
                raw_confidence=1.0,
                verified=True,
                status="answered",
                page=1,
                paper="Paper 66",
                evidences=[
                    {
                        "detector": "trailing-key",
                        "question_number": 1,
                        "correct_index": 1,
                        "correct_letter": "B",
                        "confidence": 1.0,
                        "evidence": "key entry 1 -> (B)",
                        "answer_text": None,
                        "detail": {},
                    }
                ],
            ),
            ResolvedMCQ(
                number=2,
                text="Q2?",
                options=["A", "B", "C", "D"],
                correct_index=-1,
                status="unknown",
                page=1,
                paper="Paper 66",
            ),
        ],
        pending=[
            {
                "number": 3,
                "text": "Q3?",
                "options": ["A", "B", "C", "D"],
                "reason": "no-key-entry",
                "page": 1,
                "paper": "Paper 66",
            }
        ],
        counts={"questions": 2, "answered": 1, "unknown": 1, "pending": 1},
    )


def test_persist_and_review_items(session) -> None:
    doc_id, job_id = uuid.uuid4(), uuid.uuid4()
    counts = persist_matched_document(
        session, document_id=doc_id, job_id=job_id, matched=_matched()
    )
    assert counts["questions_stored"] == 2
    assert counts["pending_stored"] == 1
    assert counts["requires_review"] is True  # unknown + pending present
    items = list_review_items(session, job_id=job_id)
    assert [i["number"] for i in items] == ["2", "3"]
    assert items[0]["status"] == "unknown"
    assert items[1]["status"] == "pending"
    assert items[0]["options"] == ["A", "B", "C", "D"]
    report = get_document_report(session, document_id=doc_id)
    assert report is not None
    assert report["questions_extracted"] == 2
    assert report["uncertain_answers"] == 1


def test_re_persist_replaces_rows(session) -> None:
    doc_id, job_id = uuid.uuid4(), uuid.uuid4()
    persist_matched_document(session, document_id=doc_id, job_id=job_id, matched=_matched())
    persist_matched_document(session, document_id=doc_id, job_id=job_id, matched=_matched())
    rows = (
        session.query(db.ExtractedQuestion).filter(db.ExtractedQuestion.document_id == doc_id).all()
    )
    assert len(rows) == 3  # 2 questions + 1 pending, not 6


def test_answer_correction_never_touches_original(session) -> None:
    doc_id, job_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    persist_matched_document(session, document_id=doc_id, job_id=job_id, matched=_matched())
    row = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == doc_id)
        .filter(db.ExtractedQuestion.question_number == "1")
        .one()
    )
    original_text = row.original_text
    result = apply_manual_correction(
        session,
        document_id=doc_id,
        user_id=user_id,
        question_id=row.id,
        field="answer",
        new_value="C",
        reason="reviewer checked key",
    )
    assert result["old_value"] == "B"
    assert result["new_value"] == "C"
    assert result["validation_status"] == "answered"
    session.refresh(row)
    assert row.original_text == original_text  # immutable
    answer = (
        session.query(db.ExtractedAnswer).filter(db.ExtractedAnswer.question_id == row.id).one()
    )
    assert answer.resolved_label == "C"
    assert answer.status == "manually_verified"
    assert answer.resolution_method == "manual"
    # Audit rows exist.
    corrections = (
        session.query(db.ManualCorrection).filter(db.ManualCorrection.document_id == doc_id).all()
    )
    assert len(corrections) == 1
    assert corrections[0].field_name == "answer"
    assert corrections[0].old_value == "B"
    assert corrections[0].user_id == user_id
    history = session.query(db.ReviewHistory).filter(db.ReviewHistory.document_id == doc_id).all()
    assert len(history) == 1
    assert history[0].decision == "corrected"


def test_question_and_option_text_corrections(session) -> None:
    doc_id, job_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    persist_matched_document(session, document_id=doc_id, job_id=job_id, matched=_matched())
    row = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == doc_id)
        .filter(db.ExtractedQuestion.question_number == "2")
        .one()
    )
    apply_manual_correction(
        session,
        document_id=doc_id,
        user_id=user_id,
        question_id=row.id,
        field="question_text",
        new_value="Q2 fixed?",
    )
    apply_manual_correction(
        session,
        document_id=doc_id,
        user_id=user_id,
        question_id=row.id,
        field="option_text:0",
        new_value="Alpha",
    )
    session.refresh(row)
    assert row.normalized_text == "Q2 fixed?"
    assert row.original_text == "Q2?"  # original untouched
    options = (
        session.query(db.QuestionOption)
        .filter(db.QuestionOption.question_id == row.id)
        .order_by(db.QuestionOption.position)
        .all()
    )
    assert options[0].normalized_text == "Alpha"
    assert options[0].original_text == "A"


def test_correction_rejects_bad_field_and_bad_answer(session) -> None:
    doc_id, job_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    persist_matched_document(session, document_id=doc_id, job_id=job_id, matched=_matched())
    row = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == doc_id)
        .filter(db.ExtractedQuestion.question_number == "1")
        .one()
    )
    with pytest.raises(ValueError, match="not correctable"):
        apply_manual_correction(
            session,
            document_id=doc_id,
            user_id=user_id,
            question_id=row.id,
            field="paper",
            new_value="Paper 67",
        )
    with pytest.raises(ValueError, match="not one of this question's options"):
        apply_manual_correction(
            session,
            document_id=doc_id,
            user_id=user_id,
            question_id=row.id,
            field="answer",
            new_value="Z",
        )
    with pytest.raises(ValueError, match="not found"):
        apply_manual_correction(
            session,
            document_id=doc_id,
            user_id=user_id,
            question_id=uuid.uuid4(),
            field="answer",
            new_value="A",
        )


def test_answer_correction_on_unknown_question_verifies_it(session) -> None:
    doc_id, job_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    persist_matched_document(session, document_id=doc_id, job_id=job_id, matched=_matched())
    row = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.document_id == doc_id)
        .filter(db.ExtractedQuestion.question_number == "2")
        .one()
    )
    result = apply_manual_correction(
        session,
        document_id=doc_id,
        user_id=user_id,
        question_id=row.id,
        field="answer",
        new_value="A",
    )
    assert result["old_value"] is None  # had no answer
    assert result["validation_status"] == "answered"
    assert result["validation_issues"] == []
    items = list_review_items(session, job_id=job_id)
    assert [i["number"] for i in items] == ["3"]  # Q2 left the review list
