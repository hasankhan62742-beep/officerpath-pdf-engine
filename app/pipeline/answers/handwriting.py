# OfficerPath AI — PDF Engine (Phase 1, M5)
# Handwriting detector (limited scope, honest): find ink that is
# NOT printed text, and classify it as marginalia/notes vs an
# answer mark.
#
# Method:
# 1. ``find_unmatched_ink`` — threshold the page, take connected
#    components, drop every component that overlaps a Tesseract
#    word box (dilated a few px). What remains is ink Tesseract
#    did not read as a word: handwriting, pen marks, smudges.
#    Components near each other (within ~1 line height) are merged
#    into regions, because one handwritten word is many components.
# 2. ``classify_ink_region`` — deterministic rules, documented
#    below. A region is an answer mark only when it is SMALL, close
#    to an option letter, and alone; anything wide, multi-word, or
#    far from every option in the margin/bottom is marginalia.
#    Anything else is "unknown" — never forced into either class.
#
# The Paper 60 photo's handwritten note ("Dot Matrix printer /
# impact printer") is the reference case: it must classify as
# marginalia, NEVER as an answer. A note is not an answer mark,
# and note text is never treated as an answer.

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

#: Components smaller than this (px) are scanner noise, not ink.
MIN_COMPONENT_PX = 25
#: Merge gap, in units of the median component height.
MERGE_GAP_LINES = 1.0
#: A region this wide (fraction of page width) is text-like, not a mark.
MARGINALIA_MIN_WIDTH_FRAC = 0.25
#: Bottom margin of the page (fraction of height) where notes live.
BOTTOM_MARGIN_FRAC = 0.12


@dataclass
class InkRegion:
    """One region of non-printed ink."""

    bbox: dict  # normalised x_min/y_min/x_max/y_max
    area_px: int = 0
    components: int = 0
    classification: str = "unknown"  # marginalia | answer-mark | unknown
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "bbox": {k: round(v, 4) for k, v in self.bbox.items()},
            "area_px": self.area_px,
            "components": self.components,
            "classification": self.classification,
            "reason": self.reason,
        }


def _dilated_word_boxes(
    word_boxes: list[dict], shape: tuple[int, int], dilate_px: int
) -> list[tuple[int, int, int, int]]:
    height, width = shape[:2]
    out: list[tuple[int, int, int, int]] = []
    for box in word_boxes:
        b = box["bbox"]
        out.append(
            (
                max(0, int(b["x_min"] * width) - dilate_px),
                max(0, int(b["y_min"] * height) - dilate_px),
                min(width, int(b["x_max"] * width) + dilate_px),
                min(height, int(b["y_max"] * height) + dilate_px),
            )
        )
    return out


def _overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def find_unmatched_ink(
    image_png: bytes,
    word_boxes: list[dict],
    *,
    dilate_px: int = 3,
    min_area_px: int = MIN_COMPONENT_PX,
) -> list[InkRegion]:
    """Find connected ink components that do not overlap any
    (dilated) Tesseract word box, merged into regions. Returns
    regions with normalised bboxes; classification is NOT done
    here (see ``classify_ink_region``)."""
    arr = np.frombuffer(image_png, dtype=np.uint8)
    gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError("could not decode image_png")
    height, width = gray.shape[:2]
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    num, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    dilated = _dilated_word_boxes(word_boxes, gray.shape, dilate_px)
    kept: list[tuple[int, int, int, int, int]] = []  # x, y, w, h, area
    heights: list[int] = []
    for i in range(1, num):
        x, y, w, h, area = (int(v) for v in stats[i])
        if area < min_area_px:
            continue
        box = (x, y, x + w, y + h)
        if any(_overlaps(box, wb) for wb in dilated):
            continue
        kept.append((x, y, w, h, area))
        heights.append(h)
    if not kept:
        return []
    median_h = float(np.median(heights)) if heights else 10.0
    gap = max(4.0, median_h * MERGE_GAP_LINES)
    # Merge components whose bboxes are within `gap` px (same word).
    regions: list[list[tuple[int, int, int, int, int]]] = []
    for comp in sorted(kept, key=lambda c: (c[1], c[0])):
        placed = False
        for region in regions:
            for other in region:
                if (
                    abs(comp[0] - (other[0] + other[2])) <= gap
                    or abs(other[0] - (comp[0] + comp[2])) <= gap
                ) and abs(comp[1] - other[1]) <= gap * 2:
                    region.append(comp)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            regions.append([comp])
    out: list[InkRegion] = []
    for region in regions:
        x0 = min(c[0] for c in region)
        y0 = min(c[1] for c in region)
        x1 = max(c[0] + c[2] for c in region)
        y1 = max(c[1] + c[3] for c in region)
        out.append(
            InkRegion(
                bbox={
                    "x_min": x0 / width,
                    "y_min": y0 / height,
                    "x_max": x1 / width,
                    "y_max": y1 / height,
                },
                area_px=sum(c[4] for c in region),
                components=len(region),
            )
        )
    return out


def classify_ink_region(
    region: InkRegion,
    *,
    option_boxes: list[dict] | None = None,
) -> InkRegion:
    """Classify one unmatched-ink region. Rules (in order):
    1. answer-mark: small (height < 3% of page height, width <
       10% of page width), a single component, and within ~1.5
       line-heights of an option letter box.
    2. marginalia: wide (>= 25% of page width) OR >= 4 components
       in a row OR sitting in the bottom 12% of the page away from
       every option.
    3. otherwise unknown — never forced.
    The region is returned with classification + reason set."""
    bbox = region.bbox
    w_frac = bbox["x_max"] - bbox["x_min"]
    h_frac = bbox["y_max"] - bbox["y_min"]
    options = option_boxes or []

    def _distance_to_options() -> float:
        """Smallest gap (in page-height fraction) to any option box."""
        best = 1.0
        cx = (bbox["x_min"] + bbox["x_max"]) / 2
        cy = (bbox["y_min"] + bbox["y_max"]) / 2
        for box in options:
            b = box["bbox"]
            dx = max(b["x_min"] - cx, 0.0, cx - b["x_max"])
            dy = max(b["y_min"] - cy, 0.0, cy - b["y_max"])
            best = min(best, (dx * dx + dy * dy) ** 0.5)
        return best

    near_option = _distance_to_options() < 0.03 if options else False
    if near_option and region.components <= 2 and h_frac < 0.03 and w_frac < 0.10:
        region.classification = "answer-mark"
        region.reason = (
            f"small ({region.components} components, "
            f"{w_frac:.1%} x {h_frac:.1%} of page) adjacent to an option letter"
        )
        return region
    if (
        w_frac >= MARGINALIA_MIN_WIDTH_FRAC
        or region.components >= 4
        or (bbox["y_min"] >= 1.0 - BOTTOM_MARGIN_FRAC and not near_option)
    ):
        region.classification = "marginalia"
        region.reason = (
            f"wide ({w_frac:.1%} of page) / {region.components} components / "
            f"bottom-margin note at y={bbox['y_min']:.2f}, away from options"
        )
        return region
    region.classification = "unknown"
    region.reason = (
        f"does not meet the answer-mark rules (near_option={near_option}, "
        f"{region.components} components, {w_frac:.1%} x {h_frac:.1%}) "
        "nor the marginalia rules — left unclassified"
    )
    return region
