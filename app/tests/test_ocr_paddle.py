# OfficerPath AI — Phase 1, M3
# PaddleOCR adapter: result parsing (fake result objects — no model
# load in unit tests) + probe behaviour. The REAL PaddleOCR
# measurement (model load, per-page time, CER/WER on fixtures) lives
# in scripts/benchmark_m3.py and docs/benchmarks/ — running the
# predictor in unit tests would add minutes to every suite run.

import uuid

import pytest

from app.pipeline.interfaces import PageContext
from app.pipeline.ocr.paddle import DET_MODEL, REC_MODEL, PaddleOCRAdapter, _parse_result


class _FakeResult(dict):
    """Mimics the PaddleOCR 3.x OCRResult dict shape."""

    def __init__(self):
        super().__init__(
            {
                "rec_texts": ["Hello world", "Second line"],
                "rec_scores": [0.99, 0.5],
                "dt_polys": [
                    [[10, 10], [100, 10], [100, 30], [10, 30]],
                    [[10, 40], [200, 40], [200, 60], [10, 60]],
                ],
            }
        )


def _context():
    return PageContext(document_id=uuid.uuid4(), page_number=1, storage_path="", image_png=b"fake")


def test_parse_result_maps_text_scores_and_bboxes():
    blocks = _parse_result(_FakeResult(), _context(), width=1000, height=1000)
    assert len(blocks) == 2
    assert blocks[0].text == "Hello world"
    assert blocks[0].confidence == pytest.approx(0.99)
    assert blocks[0].bbox is not None
    assert blocks[0].bbox.x_min == pytest.approx(0.01)
    assert blocks[0].bbox.y_max == pytest.approx(0.03)
    assert blocks[1].confidence == pytest.approx(0.5)
    assert all(b.engine == "paddleocr" for b in blocks)
    # Line-level scores only: no invented word confidences.
    assert all(b.word_confidences is None for b in blocks)
    # Reading order is the layout stage's job, not the adapter's.
    assert all(b.reading_order is None for b in blocks)


def test_parse_result_skips_empty_text():
    result = _FakeResult()
    result["rec_texts"] = ["", "Kept"]
    result["rec_scores"] = [0.9, 0.8]
    result["dt_polys"] = [[[0, 0], [1, 0], [1, 1], [0, 1]]] * 2
    blocks = _parse_result(result, _context(), width=100, height=100)
    assert [b.text for b in blocks] == ["Kept"]


def test_model_names_are_pp_ocrv5_arabic():
    assert DET_MODEL == "PP-OCRv5_server_det"
    assert REC_MODEL == "arabic_PP-OCRv5_mobile_rec"


def test_probe_reports_import_status():
    adapter = PaddleOCRAdapter()
    probe = adapter.probe()
    # In this environment paddleocr + onnxruntime ARE installed, so
    # the probe must say available (the predictor itself is NOT
    # loaded by probing — that would download models).
    assert probe["available"] is True
    assert probe["det_model"] == DET_MODEL
    assert probe["rec_model"] == REC_MODEL
    assert adapter._predictor is None


def test_recognize_without_image_raises_before_loading():
    adapter = PaddleOCRAdapter()
    context = PageContext(document_id=uuid.uuid4(), page_number=1, storage_path="")
    with pytest.raises(ValueError, match="image_png"):
        adapter.recognize(context)
    assert adapter._predictor is None
