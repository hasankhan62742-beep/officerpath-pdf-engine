# OfficerPath AI — PDF Engine (Phase 1, M3)
# Per-page engine routing + disagreement handling (prompt §8, ADR-002).
#
# Routing (ADR-002 Option C, the approved hybrid):
# - digital page  -> digital extractor only (exact, no OCR).
# - scanned page -> one OCR engine: PaddleOCR when available, else
#   Tesseract. (Gemini is advisory-only and key-gated; it is never a
#   routing target in M3.)
# - mixed page    -> digital + the OCR engine, then DEDUPLICATE: an
#   OCR block that overlaps a digital block (same region, same text)
#   is dropped as a duplicate of the exact text — the digital block
#   wins because it is exact.
# - blank page    -> no engine (nothing to read); unknown/unreadable
#   -> OCR attempted once (best effort), failure recorded per page.
#
# Disagreement (prompt §8): when two engines run on the same page,
# their outputs are COMPARED, never silently merged. compare_engines
# aligns blocks by bbox overlap (IoU), scores each pair on the
# comparison form, and returns an agreement score + the flagged
# regions. Both outputs are persisted (the engine name on every
# OCRBlock row distinguishes them); the report lists the regions for
# review. A low agreement score routes the page to review (M6), it
# never picks a winner here.

from __future__ import annotations

import difflib

from app.pipeline.interfaces import BoundingBox, OCRBlock
from app.pipeline.ocr.normalize import normalize_for_comparison

# IoU above this means two blocks cover (approximately) the same region.
REGION_OVERLAP_IOU = 0.5
# Normalised-text similarity above this means two overlapping blocks
# agree (they read the same words). Below it, the region is flagged.
AGREEMENT_SIMILARITY = 0.8
# Digital text wins a dedup when the OCR text is this similar to it.
DEDUP_SIMILARITY = 0.85


def route_page(classification: str, available_engines: list[str]) -> list[str]:
    """Engine names to run for one page, in order. `available_engines`
    is the registry's available_names() (digital-pymupdf is always
    in it). Unknown classifications get a best-effort OCR attempt."""
    ocr_engine = None
    for candidate in ("paddleocr", "tesseract"):
        if candidate in available_engines:
            ocr_engine = candidate
            break
    if classification == "digital":
        return ["digital-pymupdf"]
    if classification == "blank":
        return []
    if classification in ("scanned", "mixed", "unknown", "unreadable"):
        if classification == "mixed":
            return ["digital-pymupdf"] + ([ocr_engine] if ocr_engine else [])
        return [ocr_engine] if ocr_engine else []
    return [ocr_engine] if ocr_engine else []


def _iou(a: BoundingBox, b: BoundingBox) -> float:
    x_min = max(a.x_min, b.x_min)
    y_min = max(a.y_min, b.y_min)
    x_max = min(a.x_max, b.x_max)
    y_max = min(a.y_max, b.y_max)
    inter_w = max(0.0, x_max - x_min)
    inter_h = max(0.0, y_max - y_min)
    inter = inter_w * inter_h
    if inter == 0.0:
        return 0.0
    area_a = max(0.0, (a.x_max - a.x_min) * (a.y_max - a.y_min))
    area_b = max(0.0, (b.x_max - b.x_min) * (b.y_max - b.y_min))
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(
        a=normalize_for_comparison(a), b=normalize_for_comparison(b), autojunk=False
    ).ratio()


def deduplicate_blocks(
    exact_blocks: list[OCRBlock], ocr_blocks: list[OCRBlock]
) -> tuple[list[OCRBlock], list[OCRBlock]]:
    """Drop OCR blocks that duplicate exact (digital) blocks: same
    region (IoU) AND same text (similarity). Returns (kept, dropped).
    The digital blocks are returned unchanged; only OCR blocks can be
    dropped, and every drop is reported (the caller logs the count)."""
    kept: list[OCRBlock] = []
    dropped: list[OCRBlock] = []
    for ocr in ocr_blocks:
        duplicate = False
        if ocr.bbox is not None:
            for exact in exact_blocks:
                if exact.bbox is None:
                    continue
                if (
                    _iou(ocr.bbox, exact.bbox) >= REGION_OVERLAP_IOU
                    and _similarity(ocr.text, exact.text) >= DEDUP_SIMILARITY
                ):
                    duplicate = True
                    break
        if duplicate:
            dropped.append(ocr)
        else:
            kept.append(ocr)
    return kept, dropped


def compare_engines(blocks_a: list[OCRBlock], blocks_b: list[OCRBlock]) -> dict:
    """Compare two engines' blocks on the same page. Blocks are
    aligned by bbox overlap (best IoU partner); pairs with no partner
    are 'unmatched'. Returns a JSON-able report:
    agreement_score (0..1 over matched pairs, or None when nothing
    matched), matched/unmatched counts, and the flagged regions
    (similarity < AGREEMENT_SIMILARITY) with both texts."""
    matched = 0
    similarities: list[float] = []
    flagged: list[dict] = []
    used_b: set[int] = set()
    for block_a in blocks_a:
        if block_a.bbox is None:
            continue
        best_i = -1
        best_iou = 0.0
        for i, block_b in enumerate(blocks_b):
            if i in used_b or block_b.bbox is None:
                continue
            iou = _iou(block_a.bbox, block_b.bbox)
            if iou > best_iou:
                best_iou = iou
                best_i = i
        if best_i < 0 or best_iou < REGION_OVERLAP_IOU:
            continue
        used_b.add(best_i)
        matched += 1
        similarity = _similarity(block_a.text, blocks_b[best_i].text)
        similarities.append(similarity)
        if similarity < AGREEMENT_SIMILARITY:
            flagged.append(
                {
                    "bbox": {
                        "x_min": round(block_a.bbox.x_min, 3),
                        "y_min": round(block_a.bbox.y_min, 3),
                        "x_max": round(block_a.bbox.x_max, 3),
                        "y_max": round(block_a.bbox.y_max, 3),
                    },
                    "similarity": round(similarity, 3),
                    "engine_a_text": block_a.text[:200],
                    "engine_b_text": blocks_b[best_i].text[:200],
                }
            )
    unmatched_a = len(blocks_a) - matched
    unmatched_b_count = len(blocks_b) - len(used_b)
    return {
        "engine_a_blocks": len(blocks_a),
        "engine_b_blocks": len(blocks_b),
        "matched_pairs": matched,
        "unmatched_a": unmatched_a,
        "unmatched_b": unmatched_b_count,
        "agreement_score": (
            round(sum(similarities) / len(similarities), 3) if similarities else None
        ),
        "flagged_regions": flagged,
        "flagged_count": len(flagged),
    }
