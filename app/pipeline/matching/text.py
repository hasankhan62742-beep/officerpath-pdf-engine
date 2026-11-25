# OfficerPath AI — PDF Engine (Phase 2, A2)
# Plain-text parse path (gap-report F4): TXT and DOCX files carry
# real text, so they never go near PyMuPDF. The validator accepts
# them and ingest classifies them digital, but the worker used to
# send every non-image file to parse_document_bytes, which opens
# the bytes with fitz and fails with "FileDataError: Failed to
# open stream". This module decodes the text (TXT) or extracts it
# (DOCX, python-docx — paragraphs + tables, in document order)
# and runs the SAME extraction / key detection / resolution /
# matching tail as the PDF path, over one digital PageLines. No
# answer is ever invented: unanswered stays unknown, exactly as
# in the PDF path.

from __future__ import annotations

import codecs
import io
from collections.abc import Callable

from app.config import Settings
from app.pipeline.matching.models import MatchedDocument

#: File types this module handles. Anything else is a caller bug.
TEXT_FILE_TYPES = ("txt", "docx")


def decode_text_bytes(data: bytes) -> str:
    """Decode plain-text bytes without ever raising: UTF-8 (with
    or without BOM) first, UTF-16 when a BOM says so, Latin-1 as
    the last resort (it maps every byte). NUL bytes are stripped
    — PostgreSQL text cannot store them (the seed-bank import hit
    the same wall) and they carry no meaning in plain text."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        try:
            return data.decode("utf-16").replace("\x00", "")
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("utf-8-sig").replace("\x00", "")
    except UnicodeDecodeError:
        return data.decode("latin-1").replace("\x00", "")


def extract_docx_text(data: bytes) -> str:
    """Extract the text of a DOCX file: paragraphs and table cells,
    in document order (body order, not paragraphs-then-tables —
    a table between two questions stays between them). Table rows
    become one line per row, cells joined with spaces. Raises
    ValueError with a named reason on a corrupt / non-DOCX file —
    never a raw zip or python-docx exception, never silent."""
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:  # pragma: no cover - dep is pinned
        raise ValueError("DOCX support is not installed on this server.") from exc
    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - python-docx raises several types for bad input
        raise ValueError(
            "File is not a readable Word document (corrupt or not a DOCX file)."
        ) from exc
    lines: list[str] = []
    body = doc.element.body
    if body is None:
        return ""
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            lines.append(Paragraph(child, doc).text)
        elif tag == "tbl":
            for row in Table(child, doc).rows:
                cells = [" ".join(p.text for p in cell.paragraphs).strip() for cell in row.cells]
                lines.append(" ".join(cell for cell in cells if cell))
    return "\n".join(lines)


def parse_text_bytes(
    data: bytes,
    source_document_id: str,
    *,
    file_type: str,
    settings: Settings | None = None,
    promote: bool = True,
    multi_pass: bool = False,
    on_stage: Callable[[str, dict], None] | None = None,
) -> tuple[MatchedDocument, dict, dict]:
    """Parse TXT/DOCX bytes end to end: decode/extract the text,
    then the shared extraction tail (extract_document +
    _finish_parse) over one digital page. Returns the same
    (matched, report, debug) shape as parse_document_bytes, with
    debug carrying is_digital=True and page_count=1 (the worker
    reads both for the job summary). Raises ValueError on empty
    text or an unreadable DOCX — the worker records the reason
    on the job, never a crash. ``settings`` is accepted for
    call-site symmetry with the PDF/image paths (unused: text
    needs no OCR settings); ``multi_pass`` is likewise accepted
    and ignored — plain text has no OCR variants to union."""
    if file_type not in TEXT_FILE_TYPES:
        raise ValueError(f"parse_text_bytes handles txt/docx, not {file_type!r}.")
    text = decode_text_bytes(data) if file_type == "txt" else extract_docx_text(data)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Document contains no extractable text.")
    if on_stage is not None:
        on_stage("classify", {"is_digital": True, "page_count": 1})
    from app.pipeline.extract.service import PageLines, extract_document
    from app.pipeline.matching.service import _finish_parse

    pages = [PageLines(page_number=1, lines=lines, is_ocr=False)]
    result = extract_document(pages, source_document_id)
    if on_stage is not None:
        on_stage(
            "extract",
            {"questions": len(result.questions), "pending": len(result.pending)},
        )
    matched, report, debug = _finish_parse(
        result,
        lines,
        source_document_id,
        promote=promote,
        on_stage=on_stage,
        debug_extra={
            "is_digital": True,
            "page_count": 1,
            "file_type": file_type,
            "source": "text",
            # A3 (page inventory): the virtual single page is
            # exact text, never OCR.
            "page_classifications": {"1": "digital"},
        },
    )
    return matched, report, debug
