# OfficerPath AI — PDF Engine (Phase 1, M3)
# PaddleOCR adapter (prompt §8, ADR-002): PP-OCRv5 Arabic-script
# models (det PP-OCRv5_server_det, rec arabic_PP-OCRv5_mobile_rec —
# the model names PaddleOCR 3.7 resolves for lang="ar"; verified in
# the installed package source). Urdu is officially listed among the
# Arabic-script languages; NASTALIQ QUALITY IS UNPROVEN until the
# M3 benchmark measures it on the real fixtures — this adapter makes
# no quality claim, it only runs the engine.
#
# Engine selection (measured finding, not a default): PaddleOCR 3.7
# ships WITHOUT paddlepaddle — `PaddleOCR(lang="ar")` fails with
# "Engine 'paddle_static' is unavailable because dependency
# 'paddlepaddle' is not installed". The adapter therefore runs the
# ONNX Runtime engine (onnxruntime pip package) via a full pipeline
# config dict carrying top-level "engine": "onnxruntime" (the key
# propagates to every sub-model). That avoids the ~400 MB
# paddlepaddle wheel AND fits the Render envelope better; it is also
# why paddleocr is an OPTIONAL dependency (requirements note in
# ADR-005), not a hard requirement.
#
# Models download on first use into ~/.paddlex/official_models
# (network, ~50-100 MB for det + rec + doc-preprocessor models).
# The first recognize() is therefore slow and is timed separately in
# the benchmark (warm-up, not a page time). If the download fails,
# recognize() raises EngineUnavailableError with the reason.
#
# Output: one OCRBlock per detected text line (PaddleOCR's rec unit),
# confidence = the line recognition score (0-1). PaddleOCR gives
# LINE-level scores only — word_confidences is None by design, never
# invented. Reading order is left None: the layout stage assigns it
# from geometry (same as Tesseract).

from __future__ import annotations

import io
from contextlib import suppress
from typing import Any

import numpy as np
from PIL import Image

from app.pipeline.interfaces import BoundingBox, OCRBlock, PageContext
from app.pipeline.ocr.normalize import detect_script
from app.pipeline.ocr.tesseract import EngineUnavailableError

ENGINE_NAME = "paddleocr"
# Model names PaddleOCR 3.7 resolves for lang="ar" (PP-OCRv5).
# Verified in the installed paddleocr source (ocr.py _get_det_rec).
DET_MODEL = "PP-OCRv5_server_det"
REC_MODEL = "arabic_PP-OCRv5_mobile_rec"


class PaddleOCRAdapter:
    """OCREngine backed by PaddleOCR 3.x (ONNX Runtime engine)."""

    name = ENGINE_NAME

    def __init__(self, language: str = "ar", engine: str = "onnxruntime") -> None:
        self.language = language
        self.engine = engine
        self._predictor: Any = None
        self._version: str | None = None
        self._probe: dict | None = None

    @property
    def version(self) -> str:
        if self._version is None:
            try:
                import paddleocr

                self._version = str(paddleocr.__version__)
            except Exception:
                self._version = "unknown"
        return self._version

    def probe(self) -> dict:
        """Light availability check (imports only — no model load, no
        download). Returns {"available": bool, "reason": str|None,
        "det_model": ..., "rec_model": ...}."""
        if self._probe is not None:
            return self._probe
        try:
            import paddleocr  # noqa: F401
            import paddlex  # noqa: F401
        except Exception as exc:
            self._probe = {
                "available": False,
                "reason": f"paddleocr/paddlex import failed: {exc}",
                "det_model": DET_MODEL,
                "rec_model": REC_MODEL,
            }
            return self._probe
        try:
            import onnxruntime  # noqa: F401
        except Exception as exc:
            self._probe = {
                "available": False,
                "reason": f"onnxruntime not installed (PaddleOCR needs it): {exc}",
                "det_model": DET_MODEL,
                "rec_model": REC_MODEL,
            }
            return self._probe
        self._probe = {
            "available": True,
            "reason": None,
            "det_model": DET_MODEL,
            "rec_model": REC_MODEL,
        }
        return self._probe

    def is_available(self) -> bool:
        return bool(self.probe().get("available"))

    def _load_predictor(self) -> Any:
        if self._predictor is not None:
            return self._predictor
        probe = self.probe()
        if not probe.get("available"):
            raise EngineUnavailableError(f"paddleocr unavailable: {probe.get('reason')}")
        try:
            from paddleocr import PaddleOCR
            from paddlex.inference.pipelines import load_pipeline_config

            config = load_pipeline_config("OCR")
            config["engine"] = self.engine
            # PaddleOCR(lang="ar") resolves det/rec to the PP-OCRv5
            # Arabic models (DET_MODEL / REC_MODEL above).
            self._predictor = PaddleOCR(lang=self.language, paddlex_config=config)
        except Exception as exc:
            raise EngineUnavailableError(
                f"paddleocr predictor could not load (model download? "
                f"engine {self.engine!r}?): {exc}"
            ) from exc
        return self._predictor

    def recognize(self, page: PageContext) -> list[OCRBlock]:
        if page.image_png is None:
            raise ValueError("PaddleOCRAdapter needs image_png on the PageContext.")
        predictor = self._load_predictor()
        image = np.array(Image.open(io.BytesIO(page.image_png)).convert("RGB"))
        height, width = image.shape[:2]
        try:
            results = predictor.predict(image)
        except Exception as exc:
            raise RuntimeError(f"paddleocr failed on page {page.page_number}: {exc}") from exc
        if not results:
            return []
        return _parse_result(results[0], page, width, height)

    def close(self) -> None:
        predictor = self._predictor
        self._predictor = None
        if predictor is not None and hasattr(predictor, "close"):
            with suppress(Exception):
                predictor.close()


def _parse_result(result: object, page: PageContext, width: int, height: int) -> list[OCRBlock]:
    """Parse one PaddleOCR 3.x OCRResult into OCRBlocks. The result
    object exposes rec_texts / rec_scores / dt_polys (attribute or
    dict access — both shapes are handled, because the API varies by
    minor version)."""
    texts = _get_field(result, "rec_texts") or []
    scores = _get_field(result, "rec_scores") or []
    polys = _get_field(result, "dt_polys") or []
    blocks: list[OCRBlock] = []
    for index, text in enumerate(texts):
        text = (text or "").strip()
        if not text:
            continue
        score = float(scores[index]) if index < len(scores) else None
        bbox = None
        if index < len(polys) and polys[index] is not None:
            points = np.asarray(polys[index], dtype=float).reshape(-1, 2)
            x_min, y_min = points.min(axis=0)
            x_max, y_max = points.max(axis=0)
            bbox = BoundingBox(
                x_min=max(0.0, x_min / width),
                y_min=max(0.0, y_min / height),
                x_max=min(1.0, x_max / width),
                y_max=min(1.0, y_max / height),
            )
        blocks.append(
            OCRBlock(
                text=text,
                bbox=bbox,
                page_number=page.page_number,
                reading_order=None,  # assigned by the layout stage
                confidence=score,
                word_confidences=None,  # line-level scores only (see module docstring)
                language=detect_script(text),
                engine=ENGINE_NAME,
                engine_version=None,  # filled by the caller from adapter.version
                style=None,
            )
        )
    return blocks


def _get_field(result: object, name: str) -> Any:
    """rec_texts / rec_scores / dt_polys by attribute first, then
    dict key (PaddleOCR 3.x OCRResult is a dict subclass, so both
    shapes are the same object in practice)."""
    if hasattr(result, name):
        return getattr(result, name)
    if isinstance(result, dict):
        return result.get(name)
    return None
