# OfficerPath AI — Phase 1, M3
# OCR + layout pipeline stages: routing, per-page failure isolation,
# OCR block persistence, layout persistence (Alembic 0002 column),
# and the cross-page continuation flags.
#
# PaddleOCR is NOT loaded here: the registry used in these tests is
# digital + Tesseract only (a fake registry), so the suite stays
# fast. The real PaddleOCR run is scripts/benchmark_m3.py.

import uuid
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.db.models import Base, Document, DocumentPage, Job, OCRBlock
from app.pipeline.ingestion.service import SqlAlchemyStageRecorder
from app.pipeline.layout.service import LayoutPageInput, run_layout_stage
from app.pipeline.ocr.registry import OCRRegistry
from app.pipeline.ocr.service import OcrPageInput, run_ocr_stage
from app.pipeline.ocr.tesseract import TesseractAdapter

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "m2"


def _sqlite_recorder():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    return SqlAlchemyStageRecorder(session), session, engine


def _document(session: Session) -> uuid.UUID:
    document_id = uuid.uuid4()
    session.add(
        Document(
            id=document_id,
            user_id=uuid.uuid4(),
            title="clean.pdf",
            storage_path="user-1/clean.pdf",
            file_type="pdf",
            file_size_bytes=10_000,
            page_count=2,
            content_hash="b" * 64,
        )
    )
    session.commit()
    return document_id


def _registry_tesseract_only() -> OCRRegistry:
    from app.pipeline.ocr.digital import DigitalExtractor

    registry = OCRRegistry()
    registry.register(DigitalExtractor())
    tess = TesseractAdapter(languages="eng+urd", psm=3)
    registry.register(tess, prober=tess)
    return registry


def test_ocr_stage_digital_page_uses_digital_only():
    recorder, session, _engine = _sqlite_recorder()
    document_id = _document(session)
    pdf_bytes = (FIXTURES / "clean.pdf").read_bytes()
    result = run_ocr_stage(
        settings=Settings(),
        storage=_NullStorage(),
        recorder=recorder,
        document_id=document_id,
        job_id=None,
        pages=[
            OcrPageInput(
                page_number=1,
                classification="digital",
                pdf_bytes=pdf_bytes,
            )
        ],
        registry=_registry_tesseract_only(),
    )
    assert result.pages_processed == 1
    page = result.pages[0]
    assert page.engines_run == ["digital-pymupdf"]
    assert page.block_count > 0
    assert page.error is None
    rows = session.query(OCRBlock).filter_by(document_id=document_id).all()
    assert len(rows) == page.block_count
    assert all(row.engine == "digital-pymupdf" for row in rows)
    assert any("Pakistan" in row.text for row in rows)


def test_ocr_stage_scanned_page_uses_tesseract_and_persists():
    recorder, session, _engine = _sqlite_recorder()
    document_id = _document(session)
    from app.pipeline.pdf.renderer import render_pdf_page

    png = render_pdf_page((FIXTURES / "scanned.pdf").read_bytes(), 1, dpi=200).png_bytes
    storage = _MemoryStorage({f"{document_id}/render.png": png})
    result = run_ocr_stage(
        settings=Settings(),
        storage=storage,
        recorder=recorder,
        document_id=document_id,
        job_id=None,
        pages=[
            OcrPageInput(
                page_number=1,
                classification="scanned",
                render_path=f"{document_id}/render.png",
            )
        ],
        registry=_registry_tesseract_only(),
    )
    assert result.pages_processed == 1
    page = result.pages[0]
    assert page.engines_run == ["tesseract"]
    assert page.block_count > 0
    text = " ".join(
        row.text for row in session.query(OCRBlock).filter_by(document_id=document_id).all()
    )
    assert "Pakistan" in text


def test_ocr_stage_page_failure_does_not_fail_document():
    recorder, session, _engine = _sqlite_recorder()
    document_id = _document(session)
    result = run_ocr_stage(
        settings=Settings(),
        storage=_NullStorage(),
        recorder=recorder,
        document_id=document_id,
        job_id=None,
        pages=[
            OcrPageInput(page_number=1, classification="digital", pdf_bytes=b"not a pdf"),
            OcrPageInput(
                page_number=2,
                classification="digital",
                pdf_bytes=(FIXTURES / "clean.pdf").read_bytes(),
            ),
        ],
        registry=_registry_tesseract_only(),
    )
    assert result.pages_processed == 1
    assert result.pages[0].error is not None
    assert result.pages[1].error is None


def test_ocr_stage_no_engine_available_records_failure():
    recorder, session, _engine = _sqlite_recorder()
    document_id = _document(session)
    registry = OCRRegistry()  # empty: no engines at all
    result = run_ocr_stage(
        settings=Settings(),
        storage=_NullStorage(),
        recorder=recorder,
        document_id=document_id,
        job_id=None,
        pages=[OcrPageInput(page_number=1, classification="scanned")],
        registry=registry,
    )
    assert result.pages_processed == 0
    assert "no_ocr_engine" in (result.pages[0].error or "")


def test_layout_stage_persists_and_flags_continuation():
    recorder, session, _engine = _sqlite_recorder()
    document_id = _document(session)
    # Create the page rows the layout stage updates.
    for page_number in (1, 2):
        session.add(
            DocumentPage(
                document_id=document_id,
                page_number=page_number,
                classification="scanned",
                classification_method="test",
            )
        )
    session.commit()
    from app.pipeline.interfaces import BoundingBox
    from app.pipeline.interfaces import OCRBlock as DataOCRBlock

    def block(text, x0, y0, x1, y1, page):
        return DataOCRBlock(
            text=text,
            bbox=BoundingBox(x_min=x0, y_min=y0, x_max=x1, y_max=y1),
            page_number=page,
            engine="tesseract",
        )

    result = run_layout_stage(
        settings=Settings(),
        recorder=recorder,
        document_id=document_id,
        job_id=None,
        pages=[
            LayoutPageInput(
                page_number=1,
                blocks=[
                    block("1. Question one?", 0.05, 0.1, 0.45, 0.15, 1),
                    block("(A) One", 0.05, 0.16, 0.45, 0.2, 1),
                ],
            ),
            LayoutPageInput(
                page_number=2,
                blocks=[
                    block("(B) Two", 0.05, 0.1, 0.45, 0.15, 2),
                    block("2. Question two?", 0.05, 0.16, 0.45, 0.2, 2),
                ],
            ),
        ],
    )
    assert result.pages_processed == 2
    row1 = session.query(DocumentPage).filter_by(document_id=document_id, page_number=1).one()
    assert row1.layout_applied is not None
    assert row1.layout_applied["column_count"] == 1
    assert row1.layout_applied.get("continues_to_page") == 2
    row2 = session.query(DocumentPage).filter_by(document_id=document_id, page_number=2).one()
    assert row2.layout_applied.get("continues_from_page") == 1


def test_alembic_0002_layout_column(tmp_path, monkeypatch):
    """Alembic 0002 adds layout_applied to document_pages; downgrade
    to 0001 removes it; upgrade to head restores it."""
    from alembic.config import Config

    from alembic import command

    db_file = tmp_path / "alembic-m3.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine, tables=[Document.__table__, Job.__table__])
    engine.dispose()
    cfg = Config("alembic.ini")

    def _columns() -> set[str]:
        eng = create_engine(f"sqlite:///{db_file}")
        names = {c["name"] for c in inspect(eng).get_columns("document_pages")}
        eng.dispose()
        return names

    command.upgrade(cfg, "head")
    assert "layout_applied" in _columns()
    command.downgrade(cfg, "0001_m1_engine_tables")
    assert "layout_applied" not in _columns()
    command.upgrade(cfg, "head")
    assert "layout_applied" in _columns()


class _NullStorage:
    def put(self, path, data):
        raise NotImplementedError

    def get(self, path):
        raise FileNotFoundError(path)

    def exists(self, path):
        return False

    def delete(self, path):
        raise NotImplementedError


class _MemoryStorage:
    def __init__(self, files: dict):
        self._files = files

    def put(self, path, data):
        self._files[path] = data

    def get(self, path):
        return self._files[path]

    def exists(self, path):
        return path in self._files

    def delete(self, path):
        del self._files[path]
