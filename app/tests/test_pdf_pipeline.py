# OfficerPath AI — PDF Engine (Phase 1, M2) — tests
# The PDF pipeline stage end to end: ingestion-classified file in,
# per-page analysis + rendering + preprocessing out, with stage
# history persisted. Per-page failures never fail the document.

import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Base, Document, DocumentPage, Job, ProcessingStage
from app.pipeline.ingestion.service import NullStageRecorder, SqlAlchemyStageRecorder
from app.pipeline.interfaces import PipelineStage
from app.pipeline.pdf.service import run_pdf_stage
from app.storage.local import LocalDiskStorage

FIXTURES = Path(__file__).parent / "fixtures" / "m2"
PPSC66 = Path(__file__).parent / "fixtures" / "ppsc66"


class _CapturingRecorder:
    """A StageRecorder that remembers every call (for assertions)."""

    def __init__(self):
        self.records: list[dict] = []
        self.errors: list[dict] = []
        self.page_updates: list[dict] = []

    def record(self, *, document_id, job_id, stage, status, detail=None, correlation_id=None):
        self.records.append({"stage": stage, "status": status, "detail": detail or {}})

    def update_page(self, document_id, page_number, **fields):
        self.page_updates.append({"page_number": page_number, **fields})

    def record_error(
        self, *, document_id, job_id, page_number, stage, error_code, message, detail=None
    ):
        self.errors.append({"page_number": page_number, "error_code": error_code})


def _run(name: str, tmp_path, recorder=None, **settings_overrides):
    data = (FIXTURES / name).read_bytes()
    storage = LocalDiskStorage(str(tmp_path / "store"))
    settings = Settings(**settings_overrides)
    return run_pdf_stage(
        document_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        filename=name,
        data=data,
        settings=settings,
        storage=storage,
        recorder=recorder or NullStageRecorder(),
    ), storage


def test_run_clean_pdf_two_digital_pages(tmp_path):
    result, storage = _run("clean.pdf", tmp_path)
    assert result.pages_processed == 2
    assert result.pages_failed == 0
    assert [p.classification for p in result.pages] == ["digital", "digital"]
    for page in result.pages:
        assert page.profile_name
        assert page.quality_before is not None and page.quality_after is not None
        assert page.original_render_path is not None
        assert page.processed_render_path is not None
        assert storage.exists(page.original_render_path)
        assert storage.exists(page.processed_render_path)
        assert page.render_width_px == 1653


def test_run_scanned_and_mixed_pdfs(tmp_path):
    scanned, _ = _run("scanned.pdf", tmp_path)
    assert [p.classification for p in scanned.pages] == ["scanned"]
    assert scanned.pages[0].profile_name == "clean"
    mixed, _ = _run("mixed.pdf", tmp_path)
    assert [p.classification for p in mixed.pages] == ["digital", "scanned"]


def test_run_blank_pdf(tmp_path):
    result, _ = _run("blank.pdf", tmp_path)
    assert result.pages_processed == 1
    assert result.pages[0].classification == "blank"
    assert result.pages[0].profile_name == "clean"


def test_run_noisy_pdf_compares_two_profiles(tmp_path):
    result, _ = _run("noisy.pdf", tmp_path)
    page = result.pages[0]
    assert page.profile_name in ("noisy", "low_quality")
    # Low-quality pages get a recorded second-profile comparison.
    assert page.profile_comparison is not None
    assert page.profile_comparison["first_profile"] in ("noisy", "low_quality")
    assert page.profile_comparison["chosen"] in ("noisy", "low_quality")
    assert page.quality_after is not None and page.quality_before is not None
    assert page.quality_after["noise_score"] < page.quality_before["noise_score"]


def test_run_skewed_pdf_selects_skewed_profile(tmp_path):
    result, _ = _run("skewed.pdf", tmp_path)
    page = result.pages[0]
    assert page.classification == "scanned"
    assert page.quality_before is not None
    assert abs(page.quality_before["skew_degrees"]) > 4
    assert page.quality_after is not None
    assert page.quality_after["skew_degrees"] is not None
    assert abs(page.quality_after["skew_degrees"]) < 1.0


def test_run_image_input_ppsc66(tmp_path):
    data = (PPSC66 / "p-1.png").read_bytes()
    storage = LocalDiskStorage(str(tmp_path / "store"))
    result = run_pdf_stage(
        document_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        filename="p-1.png",
        data=data,
        settings=Settings(),
        storage=storage,
        recorder=NullStageRecorder(),
    )
    assert result.pages_processed == 1
    assert result.pages[0].classification == "scanned"
    assert result.pages[0].render_width_px == 1105


def test_run_all_ppsc66_pages_scanned(tmp_path):
    storage = LocalDiskStorage(str(tmp_path / "store"))
    for n in range(1, 8):
        data = (PPSC66 / f"p-{n}.png").read_bytes()
        result = run_pdf_stage(
            document_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            filename=f"p-{n}.png",
            data=data,
            settings=Settings(),
            storage=storage,
            recorder=NullStageRecorder(),
        )
        assert result.pages_failed == 0, f"p-{n} failed"
        assert result.pages[0].classification == "scanned", f"p-{n}"
        assert result.pages[0].quality_before["ink_coverage"] > 0.005


def test_invalid_stage_transition_raises(tmp_path):
    data = (FIXTURES / "clean.pdf").read_bytes()
    storage = LocalDiskStorage(str(tmp_path / "store"))
    with pytest.raises(ValueError, match="state machine"):
        run_pdf_stage(
            document_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            filename="clean.pdf",
            data=data,
            settings=Settings(),
            storage=storage,
            recorder=NullStageRecorder(),
            current_stage=PipelineStage.COMPLETED,
        )


def test_corrupt_pdf_is_a_recorded_failure_not_an_exception(tmp_path):
    recorder = _CapturingRecorder()
    storage = LocalDiskStorage(str(tmp_path / "store"))
    result = run_pdf_stage(
        document_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        filename="broken.pdf",
        data=b"not a pdf at all",
        settings=Settings(),
        storage=storage,
        recorder=recorder,
    )
    assert result.pages == []
    assert len(recorder.errors) == 1
    assert recorder.errors[0]["error_code"] == "pdf_analysis_failed"
    assert any(r["status"] == "failed" for r in recorder.records)


def test_one_bad_page_does_not_fail_the_document(tmp_path, monkeypatch):
    import app.pipeline.pdf.service as service

    original_render = service.render_pdf_page

    def flaky_render(data, page_number, dpi=200, max_pixels=12_000_000):
        if page_number == 2:
            raise RuntimeError("simulated render failure")
        return original_render(data, page_number, dpi=dpi, max_pixels=max_pixels)

    monkeypatch.setattr(service, "render_pdf_page", flaky_render)
    recorder = _CapturingRecorder()
    result, _ = _run("clean.pdf", tmp_path, recorder=recorder)
    assert result.pages_processed == 1
    assert result.pages_failed == 1
    assert result.pages[1].error is not None
    assert len(recorder.errors) == 1
    assert recorder.errors[0]["page_number"] == 2
    # The document-level stage still records (with the failure counted).
    assert any(r["detail"].get("pages_failed") == 1 for r in recorder.records)


def test_page_metrics_persisted_to_database(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        doc = Document(
            user_id=uuid.uuid4(),
            title="clean.pdf",
            storage_path="user/clean.pdf",
            file_type="pdf",
            file_size_bytes=9601,
            page_count=2,
            content_hash="b" * 64,
        )
        session.add(doc)
        session.commit()
        job = Job(user_id=doc.user_id, document_id=doc.id, status="queued")
        session.add(job)
        session.commit()
        recorder = SqlAlchemyStageRecorder(session)
        # M1's record_pages creates the page rows first.
        from app.pipeline.ingestion.classifier import classify_pages
        from app.pipeline.ingestion.validator import validate_file

        data = (FIXTURES / "clean.pdf").read_bytes()
        report = validate_file("clean.pdf", data, Settings())
        recorder.record_pages(doc.id, classify_pages(report, data=data))
        storage = LocalDiskStorage(str(tmp_path / "store"))
        result = run_pdf_stage(
            document_id=doc.id,
            job_id=job.id,
            filename="clean.pdf",
            data=data,
            settings=Settings(),
            storage=storage,
            recorder=recorder,
        )
        assert result.pages_failed == 0
        rows = (
            session.query(DocumentPage)
            .filter_by(document_id=doc.id)
            .order_by(DocumentPage.page_number)
            .all()
        )
        assert len(rows) == 2
        for row in rows:
            assert row.classification == "digital"
            assert row.classification_method == "pymupdf-evidence"
            assert row.skew_degrees is not None
            assert row.blur_score is not None and row.blur_score > 0
            assert row.contrast_score is not None
            assert row.original_render_path is not None
            assert row.processed_render_path is not None
            assert row.preprocessing_applied is not None
            assert row.preprocessing_applied["profile"]
        stages = session.query(ProcessingStage).filter_by(document_id=doc.id).all()
        assert any(s.stage == PipelineStage.PREPROCESSING.value for s in stages)
