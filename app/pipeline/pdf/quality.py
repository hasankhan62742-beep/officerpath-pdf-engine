# OfficerPath AI — PDF Engine (Phase 1, M2)
# Per-page quality metrics, measured from the rendered image
# (prompt §7): blur, contrast, noise, skew, brightness, ink
# coverage. Every metric is a measured number or None with a reason
# — never a guess. Bleed-through has no reliable signal without a
# clean reference page, so it is recorded as NOT MEASURED, not faked.
#
# Definitions (recorded so M3/M6 can interpret the numbers):
# - blur_score: variance of the Laplacian of the grayscale image.
#   Higher = sharper. Clean print is typically > 100; a soft phone
#   photo is often < 30. (Thresholds are descriptive, not gates.)
# - contrast_score: standard deviation of grayscale pixel values.
# - noise_score: background noise — median absolute deviation of
#   (grayscale - 3x3 median-filtered grayscale), scaled to a sigma
#   estimate (x1.4826). Text edges cover ~1% of a page, so the
#   MEDIAN is dominated by paper background, not by text: a clean
#   print scores ~0-1, a sigma-18 Gaussian-noise scan ~12.
#   (Two earlier drafts failed calibration: whole-page high-frequency
#   energy scored clean print 17.9 — text edges, not noise; and a
#   flat-block std-dev filtered out exactly the noisy blocks it was
#   meant to measure. See the M2 report calibration notes.)
# - skew_degrees: dominant text-line angle from Hough lines on Canny
#   edges, in degrees, positive = clockwise. None when too few lines
#   were found to estimate (e.g. a blank page).
# - ink_coverage: fraction of pixels darker than the Otsu threshold.

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Minimum Hough line segments before a skew estimate is trusted.
MIN_SKEW_LINES = 8


@dataclass
class PageQuality:
    """Measured quality of one rendered page (before or after
    preprocessing — the caller records which)."""

    blur_score: float | None = None
    contrast_score: float | None = None
    noise_score: float | None = None
    skew_degrees: float | None = None
    brightness_mean: float | None = None
    ink_coverage: float | None = None
    bleed_through: float | None = None
    measurement_method: str = "opencv-m2"
    not_measured: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "blur_score": _round(self.blur_score),
            "contrast_score": _round(self.contrast_score),
            "noise_score": _round(self.noise_score),
            "skew_degrees": _round(self.skew_degrees),
            "brightness_mean": _round(self.brightness_mean),
            "ink_coverage": _round(self.ink_coverage),
            "bleed_through": self.bleed_through,
            "measurement_method": self.measurement_method,
            "not_measured": self.not_measured or ["bleed_through"],
        }


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def png_to_gray(png_bytes: bytes) -> np.ndarray:
    """Decode PNG bytes to a grayscale uint8 array (BGR order safe:
    colour is not used for these metrics)."""
    array = np.frombuffer(png_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("OpenCV could not decode the rendered PNG.")
    return image


def png_to_bgr(png_bytes: bytes) -> np.ndarray:
    array = np.frombuffer(png_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("OpenCV could not decode the rendered PNG.")
    return image


def measure_quality(gray: np.ndarray) -> PageQuality:
    """Measure quality from a grayscale image. Pure function — no I/O,
    no state — so tests can run it on synthetic arrays."""
    if gray.size == 0:
        return PageQuality(not_measured=["blur", "contrast", "noise", "skew", "bleed_through"])
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    blur = float(laplacian.var())
    contrast = float(gray.std())
    noise = _background_noise(gray)
    brightness = float(gray.mean())
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = float(np.mean(binary < 128))
    skew = estimate_skew(gray)
    return PageQuality(
        blur_score=blur,
        contrast_score=contrast,
        noise_score=noise,
        skew_degrees=skew,
        brightness_mean=brightness,
        ink_coverage=ink,
        bleed_through=None,  # no reliable signal without a reference page
        not_measured=["bleed_through"],
    )


def _background_noise(gray: np.ndarray) -> float:
    """Robust background-noise sigma estimate. A 3x3 median filter
    removes isolated noise spikes but keeps text strokes; the median
    absolute difference is therefore dominated by paper background
    (ink covers ~1% of a page), not by text edges."""
    filtered = cv2.medianBlur(gray, 3)
    diff = np.abs(gray.astype(np.float64) - filtered.astype(np.float64))
    return float(np.median(diff) * 1.4826)


def estimate_skew(gray: np.ndarray) -> float | None:
    """Dominant text-line angle in degrees. Returns None when fewer
    than MIN_SKEW_LINES usable line segments are found (blank pages,
    figure-only pages). Angles are wrapped to [-45, 45]."""
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180.0,
        threshold=200,
        minLineLength=80,
        maxLineGap=20,
    )
    if lines is None or len(lines) < MIN_SKEW_LINES:
        return None
    angles: list[float] = []
    for line in lines[:, 0, :]:
        x1, y1, x2, y2 = (int(v) for v in line)
        dx, dy = x2 - x1, y2 - y1
        length = (dx * dx + dy * dy) ** 0.5
        if length < 80:
            continue
        angle = float(np.degrees(np.arctan2(dy, dx)))
        # Keep near-horizontal lines only (text lines, not verticals).
        if -45.0 <= angle <= 45.0:
            angles.append(angle)
    if len(angles) < MIN_SKEW_LINES:
        return None
    # Skew is only defined when the lines AGREE: if the angles are
    # spread out (a sharpened noisy page produces spurious diagonals),
    # there is no dominant direction and the estimate is None.
    values = np.array(angles)
    q1, q3 = np.percentile(values, [25, 75])
    if float(q3 - q1) > 5.0:
        return None
    # Median is robust against a few stray diagonal strokes.
    return float(np.median(values))
