# OfficerPath AI — PDF Engine (Phase 1, M3)
# Geometry layout analyser (prompt §9). Input: one page's OCR blocks
# (any engine — the analyser only reads text + bboxes). Output: a
# JSON-able layout dict: column count + boundaries, reading order,
# header/footer/page-number blocks (excluded from question regions
# but RETAINED as metadata — nothing is deleted), per-block region
# classification, table candidates, figure candidates, and the
# content-rotation hint when an OSD probe was supplied.
#
# What this module does NOT do (M4/M5 own it): it does not extract
# questions, options or answers. Region labels are coarse structural
# hints (heading / question / option / key / table / figure / noise)
# with a stated method + confidence, so M4 can use or override them.
# A block labelled "question" is a candidate, not a question.
#
# Header/footer detection is positional + pattern-based on ONE page:
# a short block in the top/bottom 6% of the page whose text is a page
# number ("521", "Papers of 2021 521"), a running title, or a short
# all-caps line. Multi-page repetition (the same header on every
# page) is stronger evidence and is checked by the layout SERVICE
# across pages, not here.
#
# Table detection has two sources: (1) pdfplumber extract_tables on
# the PDF bytes when the page is digital (ruled tables only — the
# answer-key grid on PPSC-66 has no ruling lines, so this source
# usually finds nothing there and says so); (2) grid geometry from
# OCR blocks: >= 3 rows of >= 3 short tokens aligned in columns.
# A table candidate records its method; M4/M5 decide whether it is
# an answer key.

from __future__ import annotations

import re

from app.pipeline.interfaces import BoundingBox, OCRBlock, PageContext
from app.pipeline.layout.columns import (
    assign_columns,
    column_boundaries,
    reading_order_indices,
)

HEADER_FOOTER_BAND = 0.06  # top/bottom 6% of the page height
MIN_TABLE_ROWS = 3
MIN_TABLE_COLUMNS = 3
MAX_TABLE_CELL_CHARS = 12  # table cells are short tokens (1-A, 12, ...)

_QUESTION_MARKER = re.compile(r"^\s*\(?\d{1,3}\s*[.\)]\s+\S")
_OPTION_MARKER = re.compile(r"^\s*\(?[A-Za-z]\)\s+\S")
_KEY_TITLE = re.compile(r"answer\s*key", re.IGNORECASE)
_PAGE_NUMBER = re.compile(r"^\s*\d{1,4}\s*$")
_ROMAN_NUMERAL = re.compile(r"^\s*[ivxIVX]{1,5}\s*[.\)]\s+\S")


def _bbox_center_x(bbox: BoundingBox) -> float:
    return (bbox.x_min + bbox.x_max) / 2.0


def _classify_region(text: str, bbox: BoundingBox) -> tuple[str, float, str]:
    """Coarse region label for one block: (label, confidence, method).
    Order matters: key titles first, then question/option markers,
    then heading heuristics, then noise. Confidence is a stated
    heuristic weight, not a measured probability — the layout dict
    records the method so M4 knows what it is standing on."""
    stripped = text.strip()
    first_line = stripped.split("\n", 1)[0].strip()
    if _KEY_TITLE.search(stripped):
        return "key", 0.9, "answer-key title pattern"
    if _QUESTION_MARKER.match(first_line) or _ROMAN_NUMERAL.match(first_line):
        return "question", 0.75, "numbered-marker pattern"
    if _OPTION_MARKER.match(first_line):
        return "option", 0.75, "option-label pattern"
    words = stripped.split()
    if len(words) <= 8 and stripped.isupper() and len(stripped) >= 4:
        return "heading", 0.6, "short all-caps line"
    if len(words) <= 3 and not stripped:
        return "noise", 0.9, "empty block"
    if len(words) == 0:
        return "noise", 0.9, "empty block"
    return "text", 0.5, "default text block"


def _is_header_footer(block: OCRBlock) -> str | None:
    """'header' / 'footer' / None. Positional (top/bottom band) plus
    a page-number-like or running-title-like text."""
    if block.bbox is None:
        return None
    text = block.text.strip()
    if block.bbox.y_min < HEADER_FOOTER_BAND and (
        _PAGE_NUMBER.match(text) or len(text.split()) <= 6
    ):
        return "header"
    if block.bbox.y_max > 1.0 - HEADER_FOOTER_BAND and (
        _PAGE_NUMBER.match(text) or len(text.split()) <= 6
    ):
        return "footer"
    return None


def _detect_grid_tables(blocks: list[OCRBlock]) -> list[dict]:
    """Grid tables from OCR geometry: rows of short tokens aligned
    into >= MIN_TABLE_COLUMNS columns, >= MIN_TABLE_ROWS rows. A row
    is a set of blocks sharing a y-band; columns come from x-centre
    clustering. Returns table candidates with method + bbox."""
    rows: list[list[OCRBlock]] = []
    remaining = sorted(
        (b for b in blocks if b.bbox is not None),
        key=lambda b: (b.bbox.y_min if b.bbox else 0.0),
    )
    for block in remaining:
        if len(block.text.strip()) > MAX_TABLE_CELL_CHARS * 3:
            continue  # long prose is not a table cell row
        placed = False
        for row in rows:
            row_y = row[0].bbox.y_min if row[0].bbox else 0.0
            if block.bbox is not None and abs(block.bbox.y_min - row_y) < 0.02:
                row.append(block)
                placed = True
                break
        if not placed:
            rows.append([block])
    tables: list[dict] = []
    run: list[list[OCRBlock]] = []
    for row in rows:
        cells = [b for b in row if len(b.text.strip()) <= MAX_TABLE_CELL_CHARS]
        if len(cells) >= MIN_TABLE_COLUMNS:
            run.append(cells)
        else:
            if len(run) >= MIN_TABLE_ROWS:
                tables.append(_table_from_rows(run))
            run = []
    if len(run) >= MIN_TABLE_ROWS:
        tables.append(_table_from_rows(run))
    return tables


def _table_from_rows(rows: list[list[OCRBlock]]) -> dict:
    boxes: list[BoundingBox] = [b.bbox for row in rows for b in row if b.bbox is not None]
    return {
        "method": "ocr-block grid",
        "rows": len(rows),
        "columns": max(len(row) for row in rows),
        "bbox": {
            "x_min": round(min(b.x_min for b in boxes), 3),
            "y_min": round(min(b.y_min for b in boxes), 3),
            "x_max": round(max(b.x_max for b in boxes), 3),
            "y_max": round(max(b.y_max for b in boxes), 3),
        },
        "confidence": 0.6,
    }


class GeometryLayoutAnalyzer:
    """LayoutAnalyzer: columns + reading order + regions from block
    geometry. `images` (optional) are embedded-image bboxes from the
    M2 analysis, used for figure candidates. `rotation_hint` is an
    optional OSD result (see tesseract.detect_rotation)."""

    def analyze(
        self,
        page: PageContext,
        blocks: list[OCRBlock],
        *,
        images: list[BoundingBox] | None = None,
        rotation_hint: dict | None = None,
    ) -> dict:
        blocks = [b for b in blocks if b.text.strip()]
        bboxes = [b.bbox for b in blocks if b.bbox is not None]
        columns = assign_columns(bboxes) if bboxes else []
        ranks = reading_order_indices(bboxes) if bboxes else []
        # Map bbox index -> column/rank for blocks that have bboxes.
        col_by_index: dict[int, int] = {}
        rank_by_index: dict[int, int] = {}
        bbox_index = 0
        for i, block in enumerate(blocks):
            if block.bbox is None:
                continue
            col_by_index[i] = columns[bbox_index]
            rank_by_index[i] = ranks[bbox_index]
            bbox_index += 1
        numbered = [c for c in columns if c >= 0]
        # Spanning blocks (column -1) are not columns; a page whose
        # blocks are all spanning is a single-column page.
        column_count = (max(numbered) + 1) if numbered else (1 if columns else 0)
        boundaries = column_boundaries(bboxes)
        regions: list[dict] = []
        header_footer: list[dict] = []
        for i, block in enumerate(blocks):
            if block.bbox:
                label, confidence, method = _classify_region(block.text, block.bbox)
            else:
                label, confidence, method = ("noise", 0.9, "no bbox")
            zone = _is_header_footer(block)
            entry = {
                "block_index": i,
                "text_preview": block.text[:80],
                "region": label,
                "region_confidence": confidence,
                "region_method": method,
                "column": col_by_index.get(i),
                "reading_order": rank_by_index.get(i),
                "header_footer": zone,
            }
            regions.append(entry)
            if zone:
                header_footer.append(entry)
        tables = _detect_grid_tables(blocks)
        figures: list[dict] = []
        for image_bbox in images or []:
            figures.append(
                {
                    "method": "embedded-image bbox (M2 analysis)",
                    "bbox": {
                        "x_min": round(image_bbox.x_min, 3),
                        "y_min": round(image_bbox.y_min, 3),
                        "x_max": round(image_bbox.x_max, 3),
                        "y_max": round(image_bbox.y_max, 3),
                    },
                    "nearest_block_index": _nearest_block_index(image_bbox, blocks),
                }
            )
        return {
            "page_number": page.page_number,
            "column_count": column_count,
            "column_boundaries": sorted(set(boundaries)),
            "regions": regions,
            "header_footer_blocks": [entry["block_index"] for entry in header_footer],
            "tables": tables,
            "figures": figures,
            "content_rotation": rotation_hint,
            "block_count": len(blocks),
            "method": "geometry-columns-v1",
        }


def _nearest_block_index(image_bbox: BoundingBox, blocks: list[OCRBlock]) -> int | None:
    """Index of the text block whose centre is closest to the image
    bbox centre (the figure's nearest question candidate, M4
    verifies). None when there are no blocks."""
    best: int | None = None
    best_distance = float("inf")
    image_cx = _bbox_center_x(image_bbox)
    image_cy = (image_bbox.y_min + image_bbox.y_max) / 2.0
    for i, block in enumerate(blocks):
        if block.bbox is None:
            continue
        distance = abs(_bbox_center_x(block.bbox) - image_cx) + abs(
            (block.bbox.y_min + block.bbox.y_max) / 2.0 - image_cy
        )
        if distance < best_distance:
            best_distance = distance
            best = i
    return best
