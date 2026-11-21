# OfficerPath AI — Phase 1, M3
# Geometry layout analyser: columns, reading order, header/footer,
# regions, grid tables, figures.

import uuid

from app.pipeline.interfaces import BoundingBox, OCRBlock, PageContext
from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer


def _block(text, x_min, y_min, x_max, y_max):
    return OCRBlock(
        text=text,
        bbox=BoundingBox(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max),
        page_number=1,
        engine="test",
    )


def _context():
    return PageContext(document_id=uuid.uuid4(), page_number=1, storage_path="")


def test_two_column_page_detected():
    blocks = [
        _block("1. Question one?", 0.05, 0.1, 0.45, 0.15),
        _block("(A) One", 0.05, 0.16, 0.45, 0.2),
        _block("10. Question ten?", 0.55, 0.1, 0.95, 0.15),
        _block("(A) Ten", 0.55, 0.16, 0.95, 0.2),
    ]
    layout = GeometryLayoutAnalyzer().analyze(_context(), blocks)
    assert layout["column_count"] == 2
    assert layout["block_count"] == 4
    regions = {r["block_index"]: r for r in layout["regions"]}
    assert regions[0]["region"] == "question"
    assert regions[1]["region"] == "option"
    # Reading order: left column first.
    assert regions[0]["reading_order"] < regions[2]["reading_order"]


def test_single_column_page():
    blocks = [
        _block("Title line", 0.1, 0.1, 0.9, 0.15),
        _block("Body text here", 0.1, 0.2, 0.9, 0.3),
    ]
    layout = GeometryLayoutAnalyzer().analyze(_context(), blocks)
    assert layout["column_count"] == 1


def test_page_number_in_footer_is_flagged():
    blocks = [
        _block("521", 0.85, 0.97, 0.95, 0.99),
        _block("1. Question one?", 0.05, 0.1, 0.45, 0.15),
    ]
    layout = GeometryLayoutAnalyzer().analyze(_context(), blocks)
    assert 0 in layout["header_footer_blocks"]
    assert 1 not in layout["header_footer_blocks"]


def test_answer_key_title_region():
    blocks = [_block("ANSWER KEY: Model Paper 66", 0.1, 0.1, 0.9, 0.15)]
    layout = GeometryLayoutAnalyzer().analyze(_context(), blocks)
    assert layout["regions"][0]["region"] == "key"


def test_grid_table_detected():
    blocks = []
    for row in range(3):
        for col in range(3):
            blocks.append(
                _block(
                    f"{row + 1}-{chr(65 + col)}",
                    0.1 + col * 0.2,
                    0.1 + row * 0.05,
                    0.25 + col * 0.2,
                    0.14 + row * 0.05,
                )
            )
    layout = GeometryLayoutAnalyzer().analyze(_context(), blocks)
    assert len(layout["tables"]) == 1
    assert layout["tables"][0]["rows"] == 3
    assert layout["tables"][0]["columns"] == 3


def test_figure_nearest_block():
    blocks = [_block("Caption text", 0.1, 0.7, 0.5, 0.75)]
    image = BoundingBox(x_min=0.1, y_min=0.4, x_max=0.5, y_max=0.65)
    layout = GeometryLayoutAnalyzer().analyze(_context(), blocks, images=[image])
    assert len(layout["figures"]) == 1
    assert layout["figures"][0]["nearest_block_index"] == 0


def test_rotation_hint_recorded():
    blocks = [_block("Some text", 0.1, 0.1, 0.9, 0.2)]
    hint = {"degrees": 90, "script": "Latin", "confidence": 42.0, "method": "tesseract-osd"}
    layout = GeometryLayoutAnalyzer().analyze(_context(), blocks, rotation_hint=hint)
    assert layout["content_rotation"] == hint


def test_empty_page():
    layout = GeometryLayoutAnalyzer().analyze(_context(), [])
    assert layout["column_count"] == 0
    assert layout["block_count"] == 0
    assert layout["regions"] == []
