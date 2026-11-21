# OfficerPath AI — PDF Engine (Phase 1, M2)
# Mark preservation (prompt §7, hard requirement): ticks, stars,
# circles, underlines, highlights and handwriting must SURVIVE
# preprocessing. This module CHECKS that, it does not detect marks
# (detection is M5): given known mark regions (from fixtures, where
# the marks were drawn programmatically and their bboxes are known),
# it measures how much dark ink is still present after processing.
#
# Two checks:
# 1. Colour-copy identity: the stored colour copy must be
#    pixel-identical to the original render. Highlights live in
#    colour; binarisation erases them, so the colour copy is the
#    guarantee. This is a strict equality check.
# 2. Ink retention per mark region: fraction of dark pixels (below
#    the Otsu threshold of the ORIGINAL image) still dark in the
#    processed image, inside the mark's bbox. A mark is "preserved"
#    when retention >= 0.5 AND the processed region still has at
#    least 2% ink (so a faint smudge does not count as a tick).
#
# The checks are also runnable on REAL pages (PPSC-66) without known
# regions: highlight presence is measured on the colour copy in HSV
# (yellow/pink/green high-saturation regions) and reported, not gated.

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Minimum ink retention for a mark to count as preserved.
MIN_INK_RETENTION = 0.5
# Minimum ink fraction in the processed region (else it is a smudge).
MIN_INK_FRACTION = 0.02


@dataclass
class MarkRegion:
    """One known mark on a fixture page (bbox in pixels of the render)."""

    kind: str  # tick | star | circle | underline | highlight | handwriting
    x_min: int
    y_min: int
    x_max: int
    y_max: int


@dataclass
class MarkCheck:
    kind: str
    ink_before: float
    ink_after: float
    retention: float | None
    preserved: bool


def check_colour_copy_identical(original_bgr: np.ndarray, colour_copy: np.ndarray) -> bool:
    """Strict pixel equality between the original render and the
    stored colour copy. Any difference is a bug, not a tolerance."""
    if original_bgr.shape != colour_copy.shape:
        return False
    return bool(np.array_equal(original_bgr, colour_copy))


def _ink_fraction(gray: np.ndarray, region: MarkRegion, threshold: int) -> float:
    x0 = max(0, region.x_min)
    y0 = max(0, region.y_min)
    x1 = min(gray.shape[1], region.x_max)
    y1 = min(gray.shape[0], region.y_max)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    crop = gray[y0:y1, x0:x1]
    return float(np.mean(crop < threshold))


def check_mark_preservation(
    original_gray: np.ndarray,
    processed_gray: np.ndarray,
    regions: list[MarkRegion],
) -> list[MarkCheck]:
    """Ink retention per known mark region. The threshold is Otsu on
    the ORIGINAL image, so 'dark' means the same thing before/after.
    Regions are scaled by the processed/original shape ratio, so a
    profile that upscales (e.g. low_quality 1.5x) is measured in the
    right coordinates — measuring unscaled bboxes against an upscaled
    image falsely reports 0% retention (found during M2 calibration).
    Highlight regions are skipped here (they are colour, checked by
    the colour-copy identity check) and reported with retention None.
    """
    otsu_value, _ = cv2.threshold(original_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    otsu_value = int(otsu_value)
    scale_x = processed_gray.shape[1] / max(original_gray.shape[1], 1)
    scale_y = processed_gray.shape[0] / max(original_gray.shape[0], 1)
    checks: list[MarkCheck] = []
    for region in regions:
        # "before" is measured in the original coordinates; "after"
        # in the processed image's (possibly upscaled) coordinates.
        scaled = MarkRegion(
            kind=region.kind,
            x_min=int(region.x_min * scale_x),
            y_min=int(region.y_min * scale_y),
            x_max=int(region.x_max * scale_x),
            y_max=int(region.y_max * scale_y),
        )
        if region.kind == "highlight":
            checks.append(
                MarkCheck(
                    kind=region.kind,
                    ink_before=0.0,
                    ink_after=0.0,
                    retention=None,
                    preserved=True,  # colour check covers highlights
                )
            )
            continue
        before = _ink_fraction(original_gray, region, otsu_value)
        after = _ink_fraction(processed_gray, scaled, otsu_value)
        retention = (after / before) if before > 0 else None
        preserved = (
            retention is not None and retention >= MIN_INK_RETENTION and after >= MIN_INK_FRACTION
        )
        checks.append(
            MarkCheck(
                kind=region.kind,
                ink_before=round(before, 4),
                ink_after=round(after, 4),
                retention=round(retention, 3) if retention is not None else None,
                preserved=preserved,
            )
        )
    return checks


def detect_highlight_regions(bgr: np.ndarray) -> list[dict]:
    """Detect coloured highlight regions (yellow/pink/green) in a
    colour page, in HSV. Returns bboxes + areas. Used for reporting
    on real pages (PPSC-66) and as an M5 input; NOT a gate — a page
    with no highlights simply returns an empty list."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    # High saturation + high value = a highlighter stroke, not print.
    mask = cv2.inRange(
        hsv,
        np.array([0, 80, 150]),
        np.array([180, 255, 255]),
    )
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions: list[dict] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 200:  # specks and JPEG artefacts, not a highlight
            continue
        x, y, w, h = cv2.boundingRect(contour)
        regions.append(
            {
                "x_min": int(x),
                "y_min": int(y),
                "x_max": int(x + w),
                "y_max": int(y + h),
                "area_px": round(area, 1),
            }
        )
    return regions
