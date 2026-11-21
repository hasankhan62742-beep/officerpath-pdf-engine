# OfficerPath AI — PDF Engine (Phase 1, M1) — tests
# §14 schema: models create + round-trip on SQLite, Alembic 0001
# upgrade/downgrade on a local SQLite file, and the pipeline state
# machine transition table.
#
# LIMITATION (labelled, not hidden): SQLite cannot verify the
# Postgres-only parts — RLS, gen_random_uuid(), the storage bucket,
# CHECK-constraint rewrites. Those are verified only by the Dashboard
# queries in docs/migration-015-apply.md after the owner applies 015.

import uuid

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    AuditLog,
    Base,
    Document,
    DocumentPage,
    ExtractedAnswer,
    ExtractedQuestion,
    ExtractionReport,
    Job,
    ProcessingStage,
    QuestionOption,
    RuleSetVersion,
)
from app.pipeline.interfaces import PipelineStage, can_transition


@pytest.fixture()
def sqlite_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _document(session: Session) -> Document:
    doc = Document(
        user_id=uuid.uuid4(),
        title="Model Paper 66",
        storage_path="user-1/paper-66.pdf",
        file_type="pdf",
        file_size_bytes=5_900_000,
        page_count=7,
        content_hash="a" * 64,
    )
    session.add(doc)
    session.commit()
    return doc


def test_document_and_page_round_trip(sqlite_session):
    doc = _document(sqlite_session)
    page = DocumentPage(
        document_id=doc.id,
        page_number=1,
        classification="scanned",
        classification_method="byte-heuristic",
        classification_confidence=0.6,
        width_px=1200,
        height_px=1600,
    )
    sqlite_session.add(page)
    sqlite_session.commit()
    loaded = sqlite_session.get(Document, doc.id)
    assert loaded is not None
    assert len(loaded.pages) == 1
    assert loaded.pages[0].classification == "scanned"


def test_question_option_answer_chain(sqlite_session):
    doc = _document(sqlite_session)
    question = ExtractedQuestion(
        document_id=doc.id,
        question_number="1",
        original_text="What is the capital of Pakistan?",
        normalized_text="What is the capital of Pakistan?",
        source_pages=[1],
        extraction_confidence=0.95,
    )
    sqlite_session.add(question)
    sqlite_session.flush()
    sqlite_session.add(
        QuestionOption(
            question_id=question.id,
            original_label="C",
            normalized_label="C",
            original_text="Islamabad",
            normalized_text="Islamabad",
            position=2,
        )
    )
    answer = ExtractedAnswer(
        question_id=question.id,
        document_id=doc.id,
        status="verified_explicit_key",
        resolved_label="C",
        resolution_method="explicit_key",
        resolution_score=1.0,
    )
    sqlite_session.add(answer)
    sqlite_session.commit()
    loaded = sqlite_session.get(ExtractedQuestion, question.id)
    assert loaded is not None
    assert len(loaded.options) == 1
    assert loaded.options[0].normalized_text == "Islamabad"
    assert len(loaded.answers) == 1
    assert loaded.answers[0].status == "verified_explicit_key"


def test_stage_and_audit_rows(sqlite_session):
    doc = _document(sqlite_session)
    sqlite_session.add(
        ProcessingStage(
            document_id=doc.id,
            stage="validated",
            status="done",
            detail={"page_count_estimate": 7},
            correlation_id="corr-1",
        )
    )
    sqlite_session.add(
        AuditLog(
            user_id=doc.user_id,
            document_id=doc.id,
            action="document.uploaded",
            target_type="document",
            target_id=doc.id,
            correlation_id="corr-1",
        )
    )
    sqlite_session.add(
        RuleSetVersion(name="extraction", version="m1-default", rules={"a": 1}, active=True)
    )
    sqlite_session.add(
        ExtractionReport(document_id=doc.id, pages_processed=7, questions_extracted=100)
    )
    sqlite_session.commit()
    assert sqlite_session.query(ProcessingStage).count() == 1
    assert sqlite_session.query(AuditLog).count() == 1
    assert sqlite_session.query(RuleSetVersion).count() == 1


def test_state_machine_transitions():
    assert can_transition(PipelineStage.UPLOADED, PipelineStage.VALIDATED)
    assert can_transition(PipelineStage.SCORED, PipelineStage.COMPLETED)
    assert can_transition(PipelineStage.SCORED, PipelineStage.REQUIRES_REVIEW)
    assert can_transition(PipelineStage.FAILED, PipelineStage.QUEUED)
    assert not can_transition(PipelineStage.UPLOADED, PipelineStage.COMPLETED)
    assert not can_transition(PipelineStage.COMPLETED, PipelineStage.QUEUED)
    assert not can_transition(PipelineStage.EXTRACTED, PipelineStage.SCORED)


def test_alembic_upgrade_downgrade_sqlite(tmp_path, monkeypatch):
    """Alembic 0001 up -> down -> up on a local SQLite file.

    The 015 tables (documents/jobs) are pre-created via the models
    because 0001 has FKs to them — mirroring the real apply order
    (015 first, then Alembic)."""
    from alembic.config import Config

    from alembic import command

    db_file = tmp_path / "alembic-test.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")

    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine, tables=[Document.__table__, Job.__table__])
    engine.dispose()

    cfg = Config("alembic.ini")

    def _tables() -> set[str]:
        eng = create_engine(f"sqlite:///{db_file}")
        names = set(inspect(eng).get_table_names())
        eng.dispose()
        return names

    command.upgrade(cfg, "head")
    after_up = _tables()
    for expected in (
        "document_pages",
        "processing_stages",
        "ocr_blocks",
        "extracted_questions",
        "question_options",
        "question_assets",
        "extracted_answers",
        "answer_evidence",
        "answer_sources",
        "extraction_reports",
        "manual_corrections",
        "review_history",
        "processing_errors",
        "audit_log",
        "rule_set_versions",
    ):
        assert expected in after_up, f"missing after upgrade: {expected}"

    command.downgrade(cfg, "base")
    after_down = _tables()
    for expected in ("document_pages", "extracted_questions", "audit_log"):
        assert expected not in after_down, f"still present after downgrade: {expected}"
    # 015 tables survive the downgrade (Alembic never owned them).
    assert "documents" in after_down
    assert "jobs" in after_down

    command.upgrade(cfg, "head")
    assert "extracted_questions" in _tables()
