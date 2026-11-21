# OfficerPath AI — PDF Engine (Phase 1, M2)
# The preprocessor: runs one profile's operations on a rendered page.
#
# Invariants (prompt §7):
# - The colour copy is NEVER modified: it is returned byte-identical
#   to the input render, because binarisation erases highlights and
#   M5 needs the colour for highlight detection.
# - Marks must survive: ticks, stars, circles, underlines and
#   handwriting are dark strokes; no operation is allowed to erase
#   dark strokes. Binarisation (only in "low_quality") uses adaptive
#   thresholding, which preserves local dark strokes, and marks.py
#   checks the result on fixtures.
# - Every operation applied is recorded with its parameters, so a
#   processed render is reproducible and auditable.
# - Work is done on ONE page at a time; the input image is released
#   by the caller after this returns (streaming, M2 memory rule).

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from app.pipeline.pdf.quality import PageQuality, measure_quality
from app.pipeline.preprocess.profiles import (
    PROFILE_VERSION,
    PreprocessProfile,
    get_profile,
)


@dataclass
class ProcessedPage:
    """Result of preprocessing one page."""

    gray: np.ndarray  # processed grayscale (or binarised) image
    colour_copy: np.ndarray  # byte-identical to the input colour image
    profile_name: str
    profile_version: str
    operations_applied: list[dict] = field(default_factory=list)
    operations_skipped: list[dict] = field(default_factory=list)
    quality_before: PageQuality | None = None
    quality_after: PageQuality | None = None

    def to_record(self) -> dict:
        """The JSON stored in document_pages.preprocessing_applied."""
        return {
            "profile": self.profile_name,
            "profile_version": self.profile_version,
            "operations_applied": self.operations_applied,
            "operations_skipped": self.operations_skipped,
            "quality_before": self.quality_before.to_dict() if self.quality_before else None,
            "quality_after": self.quality_after.to_dict() if self.quality_after else None,
        }


def _deskew(gray: np.ndarray, skew: float | None) -> tuple[np.ndarray, dict | None, dict | None]:
    """Rotate by -skew. Applied only for 0.3 <= |skew| <= 10 degrees;
    outside that the estimate is distrusted (a 45-degree 'skew' is a
    diagonal figure, not a rotated page)."""
    if skew is None or abs(skew) < 0.3 or abs(skew) > 10.0:
        return gray, None, {"op": "deskew", "reason": f"skipped: skew={skew}"}
    height, width = gray.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), skew, 1.0)
    rotated = cv2.warpAffine(
        gray, matrix, (width, height), flags=cv2.INTER_LINEAR, borderValue=(255.0,)
    )
    return rotated, {"op": "deskew", "angle_degrees": round(float(skew), 3)}, None


def _denoise(gray: np.ndarray, strength: float) -> np.ndarray:
    return cv2.fastNlMeansDenoising(gray, None, h=float(strength))


def _clahe(gray: np.ndarray, clip: float) -> np.ndarray:
    equaliser = cv2.createCLAHE(clipLimit=float(clip), tileGridSize=(8, 8))
    return equaliser.apply(gray)


def _sharpen(gray: np.ndarray, amount: float) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray, (0, 0), 3.0)
    sharpened = cv2.addWeighted(gray, 1.0 + float(amount), blurred, -float(amount), 0)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


def _upscale(gray: np.ndarray, factor: float, max_pixels: int) -> tuple[np.ndarray, dict | None]:
    height, width = gray.shape[:2]
    new_w, new_h = int(width * factor), int(height * factor)
    if new_w * new_h > max_pixels:
        return gray, {"op": "upscale", "reason": "skipped: would exceed max_render_pixels"}
    return cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC), None


def _border_crop(gray: np.ndarray) -> tuple[np.ndarray, dict | None]:
    """Trim fully-white outer margins, keeping a 10 px safety margin.
    Only rows/columns that are >99% white are trimmed, so a mark
    touching the edge stops the crop."""
    binary = (gray < 250).astype(np.uint8)
    rows = np.where(binary.any(axis=1))[0]
    cols = np.where(binary.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return gray, {"op": "border_crop", "reason": "skipped: page is blank"}
    margin = 10
    top = max(0, int(rows[0]) - margin)
    bottom = min(gray.shape[0], int(rows[-1]) + margin + 1)
    left = max(0, int(cols[0]) - margin)
    right = min(gray.shape[1], int(cols[-1]) + margin + 1)
    if (bottom - top) < gray.shape[0] * 0.9 or (right - left) < gray.shape[1] * 0.9:
        # The crop would remove more than 10% — distrust it.
        return gray, {"op": "border_crop", "reason": "skipped: crop too aggressive"}
    return gray[top:bottom, left:right], None


def process_page(
    colour_bgr: np.ndarray,
    profile: PreprocessProfile | str,
    *,
    quality_before: PageQuality | None = None,
    max_pixels: int = 12_000_000,
) -> ProcessedPage:
    """Run one profile on one colour (BGR) page render.

    Returns the processed grayscale image plus the untouched colour
    copy. The caller owns both arrays and must release them.
    """
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    gray = cv2.cvtColor(colour_bgr, cv2.COLOR_BGR2GRAY)
    if quality_before is None:
        quality_before = measure_quality(gray)
    applied: list[dict] = []
    skipped: list[dict] = []
    params = resolved.params
    for op in resolved.operations:
        if op == "deskew":
            gray, record, skip = _deskew(gray, quality_before.skew_degrees)
            (applied if record else skipped).append(
                record if record else skip  # type: ignore[arg-type]
            )
        elif op == "denoise":
            gray = _denoise(gray, float(params.get("denoise_strength", 10.0)))
            applied.append({"op": "denoise", "h": params.get("denoise_strength", 10.0)})
        elif op == "clahe":
            gray = _clahe(gray, float(params.get("clahe_clip", 2.0)))
            applied.append({"op": "clahe", "clip_limit": params.get("clahe_clip", 2.0)})
        elif op == "sharpen":
            gray = _sharpen(gray, float(params.get("sharpen_amount", 0.5)))
            applied.append({"op": "sharpen", "amount": params.get("sharpen_amount", 0.5)})
        elif op == "upscale":
            gray, skip = _upscale(gray, float(params.get("upscale_factor", 1.5)), max_pixels)
            if skip is not None:
                skipped.append(skip)
            else:
                applied.append({"op": "upscale", "factor": params.get("upscale_factor", 1.5)})
        elif op == "threshold_otsu":
            _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            applied.append({"op": "threshold_otsu"})
        elif op == "threshold_adaptive":
            gray = cv2.adaptiveThreshold(
                gray,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                int(params.get("adaptive_block", 31)),
                int(params.get("adaptive_c", 10)),
            )
            applied.append(
                {
                    "op": "threshold_adaptive",
                    "block": params.get("adaptive_block", 31),
                    "c": params.get("adaptive_c", 10),
                }
            )
        elif op == "border_crop":
            gray, skip = _border_crop(gray)
            if skip is not None:
                skipped.append(skip)
            else:
                applied.append({"op": "border_crop"})
        else:  # pragma: no cover - profiles are validated at import
            raise ValueError(f"Unknown preprocessing operation: {op!r}")
    quality_after = measure_quality(gray)
    return ProcessedPage(
        gray=gray,
        colour_copy=colour_bgr.copy(),
        profile_name=resolved.name,
        profile_version=PROFILE_VERSION,
        operations_applied=applied,
        operations_skipped=skipped,
        quality_before=quality_before,
        quality_after=quality_after,
    )
