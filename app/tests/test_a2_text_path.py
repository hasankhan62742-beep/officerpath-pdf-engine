# OfficerPath AI — Phase 2, A2 (gap-report F4)
# TXT/DOCX genuine text path: the validator accepts txt/docx and
# ingest classifies them digital, but the worker used to send every
# non-image file to parse_document_bytes (fitz) — "FileDataError:
# Failed to open stream". These tests prove the text path end to
# end: same fixture as TXT and as DOCX gives the same questions
# with the same key answers, the worker routes by file_type, and
# the sync endpoint accepts txt/docx too.

import io
from pathlib import Path

import pytest
from docx import Document

from app.pipeline.matching.text import decode_text_bytes, extract_docx_text, parse_text_bytes
from app.tests.conftest import auth_headers
from app.workers.runner import run_once

FIX = Path(__file__).resolve().parent / "fixtures/text"
TXT = FIX / "two-mcq-with-key.txt"
DOCX = FIX / "two-mcq-with-key.docx"


def _table_docx() -> bytes:
    """One MCQ whose options live in a table (not paragraphs)."""
    doc = Document()
    doc.add_paragraph("1. What is 2 + 2?")
    table = doc.add_table(rows=4, cols=1)
    for i, opt in enumerate(["(A) 3", "(B) 4", "(C) 5", "(D) 6"]):
        table.rows[i].cells[0].paragraphs[0].text = opt
    doc.add_paragraph("Answer Key")
    doc.add_paragraph("1. B")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _empty_docx() -> bytes:
    buf = io.BytesIO()
    Document().save(buf)
    return buf.getvalue()


def test_txt_fixture_parses_two_questions_with_key_answers() -> None:
    matched, _report, debug = parse_text_bytes(TXT.read_bytes(), "a2-txt", file_type="txt")
    assert len(matched.questions) == 2
    assert matched.answered == 2
    assert len(matched.pending) == 0
    assert [q.correct_index for q in matched.questions] == [2, 2]
    assert [q.answer_source for q in matched.questions] == ["trailing-key", "trailing-key"]
    assert matched.questions[0].text == "What is the capital of Pakistan?"
    assert matched.questions[1].text == "Which is the largest province?"
    assert debug["is_digital"] is True
    assert debug["page_count"] == 1
    assert debug["file_type"] == "txt"


def test_docx_fixture_matches_txt_fixture_exactly() -> None:
    txt_matched, _, _ = parse_text_bytes(TXT.read_bytes(), "a2-txt", file_type="txt")
    docx_matched, _, debug = parse_text_bytes(DOCX.read_bytes(), "a2-docx", file_type="docx")
    assert [(q.text, q.correct_index) for q in docx_matched.questions] == [
        (q.text, q.correct_index) for q in txt_matched.questions
    ]
    assert docx_matched.answered == txt_matched.answered == 2
    assert debug["file_type"] == "docx"


def test_docx_table_options_parse() -> None:
    matched, _, _ = parse_text_bytes(_table_docx(), "a2-table", file_type="docx")
    assert len(matched.questions) == 1
    assert matched.answered == 1
    assert matched.questions[0].correct_index == 1
    assert matched.questions[0].options == ["3", "4", "5", "6"]


def test_empty_txt_raises_value_error() -> None:
    with pytest.raises(ValueError, match="no extractable text"):
        parse_text_bytes(b"", "a2-empty", file_type="txt")
    with pytest.raises(ValueError, match="no extractable text"):
        parse_text_bytes(b"  \n\n ", "a2-blank", file_type="txt")


def test_empty_docx_raises_value_error() -> None:
    with pytest.raises(ValueError, match="no extractable text"):
        parse_text_bytes(_empty_docx(), "a2-empty-docx", file_type="docx")


def test_corrupt_docx_raises_value_error() -> None:
    with pytest.raises(ValueError, match="not a readable Word document"):
        parse_text_bytes(b"not a docx at all", "a2-bad-docx", file_type="docx")
    with pytest.raises(ValueError, match="not a readable Word document"):
        parse_text_bytes(b"PK\x03\x04garbage", "a2-bad-zip", file_type="docx")


def test_unknown_file_type_raises_value_error() -> None:
    with pytest.raises(ValueError, match="handles txt/docx"):
        parse_text_bytes(b"x", "a2-bad-type", file_type="pdf")


def test_non_utf8_txt_decodes_without_crashing() -> None:
    # Latin-1 bytes (validator warns on these; the parser must not crash).
    assert decode_text_bytes(b"caf\xe9 \xff") == "café ÿ"
    matched, _, _ = parse_text_bytes(
        b"caf\xe9 \xff no questions here", "a2-latin1", file_type="txt"
    )
    assert len(matched.questions) == 0


def test_txt_upload_worker_end_to_end(client, engine_db) -> None:
    """The F4 path itself: web upload -> queued job -> worker done.
    Before A2 the worker failed this job (fitz on text bytes)."""
    res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("two-mcq.txt", TXT.read_bytes(), "text/plain")},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "stored"
    assert res.json()["document"]["file_type"] == "txt"
    summary = run_once(engine_db)
    assert summary is not None
    assert summary["status"] == "done", summary
    assert summary["questions"] == 2
    assert summary["answered"] == 2


def test_docx_upload_worker_end_to_end(client, engine_db) -> None:
    res = client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                "two-mcq.docx",
                DOCX.read_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["document"]["file_type"] == "docx"
    summary = run_once(engine_db)
    assert summary is not None
    assert summary["status"] == "done", summary
    assert summary["questions"] == 2
    assert summary["answered"] == 2


def test_sync_parse_txt_returns_questions(client, engine_db) -> None:
    res = client.post(
        "/api/v1/documents/parse",
        files={"file": ("two-mcq.txt", TXT.read_bytes(), "text/plain")},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_digital"] is True
    assert body["page_count"] == 1
    assert body["matched"]["counts"]["questions"] == 2


def test_sync_parse_docx_returns_questions(client, engine_db) -> None:
    res = client.post(
        "/api/v1/documents/parse",
        files={
            "file": (
                "two-mcq.docx",
                DOCX.read_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["matched"]["counts"]["questions"] == 2


def test_sync_parse_empty_txt_is_422(client) -> None:
    res = client.post(
        "/api/v1/documents/parse",
        files={"file": ("empty.txt", b"", "text/plain")},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "invalid_file"


def test_docx_text_extraction_keeps_document_order() -> None:
    doc = Document()
    doc.add_paragraph("first paragraph")
    table = doc.add_table(rows=1, cols=1)
    table.rows[0].cells[0].paragraphs[0].text = "table line"
    doc.add_paragraph("last paragraph")
    buf = io.BytesIO()
    doc.save(buf)
    assert extract_docx_text(buf.getvalue()).split("\n") == [
        "first paragraph",
        "table line",
        "last paragraph",
    ]
