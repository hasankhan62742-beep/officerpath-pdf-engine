# OfficerPath AI — PDF Engine (Phase 1, M2)
# Preprocessing profiles (prompt §7): named, versioned, configurable
# operation lists. A profile is data, not code — M3+ can ship new
# profiles without touching the preprocessor. Selection is by
# MEASURED quality (see select_profile), never by guess.
#
# Operations (each is one step in the preprocessor, in list order):
# - deskew: rotate by the measured skew angle (only when |angle| is
#   between 0.3 and 10 degrees; outside that range the angle is
#   distrusted and the step is skipped + recorded).
# - denoise: fast non-local-means denoising on the grayscale image.
# - clahe: contrast-limited adaptive histogram equalisation.
# - sharpen: unsharp mask.
# - upscale: scale factor (bounded: the result must stay under
#   max_render_pixels, checked by the preprocessor).
# - threshold_otsu / threshold_adaptive: binarise. NOTE: binarisation
#   is the step most likely to destroy marks, so no profile binarises
#   by default except "low_quality" — and every profile's mark
#   preservation is checked by marks.py on fixtures (a failing check
#   fails the build).
# - border_crop: trim fully-white outer margins (conservative: only
#   rows/columns that are >99% white, with a 10 px safety margin
#   kept, so marks near the edge are never cut).
#
# Profile selection thresholds are descriptive, calibrated on the M2
# fixtures (see the M2 report for the measured numbers):
# - low contrast: contrast_score < 15 (clean print measures ~25;
#   the light-grey fixture measures 5.1)
# - noisy: background noise_score > 3 (clean print measures 0.0;
#   the sigma-18 fixture measures 4.4 after JPEG smoothing — a thin
#   margin, and real-world calibration is M3 benchmark work)
# - skewed: |skew_degrees| >= 0.5
# - blurry: blur_score < 30 (clean print ~700; light-grey text ~30)
# - blank: ink_coverage < 0.005 — nothing to enhance, use "clean"

from __future__ import annotations

from dataclasses import dataclass, field

PROFILE_VERSION = "m2-v1"

# Operation names the preprocessor knows how to run.
VALID_OPERATIONS = frozenset(
    {
        "deskew",
        "denoise",
        "clahe",
        "sharpen",
        "upscale",
        "threshold_otsu",
        "threshold_adaptive",
        "border_crop",
    }
)


@dataclass(frozen=True)
class PreprocessProfile:
    """One named preprocessing recipe."""

    name: str
    operations: tuple[str, ...]
    params: dict = field(default_factory=dict)
    description: str = ""


PREPROCESS_PROFILES: dict[str, PreprocessProfile] = {
    "clean": PreprocessProfile(
        name="clean",
        operations=("sharpen",),
        params={"sharpen_amount": 0.5},
        description="Clean print: keep the image almost as-is; light sharpen only.",
    ),
    "default": PreprocessProfile(
        name="default",
        operations=("deskew", "clahe", "sharpen"),
        params={"sharpen_amount": 0.5, "clahe_clip": 2.0},
        description="Ordinary scan: deskew when needed, gentle contrast lift.",
    ),
    "low_contrast": PreprocessProfile(
        name="low_contrast",
        operations=("deskew", "clahe", "sharpen"),
        params={"sharpen_amount": 0.7, "clahe_clip": 3.0},
        description="Faded / low-contrast print: stronger CLAHE.",
    ),
    "noisy": PreprocessProfile(
        name="noisy",
        operations=("denoise", "deskew", "clahe"),
        params={"denoise_strength": 10.0, "clahe_clip": 2.0},
        description="Noisy scan: denoise first, then contrast.",
    ),
    "skewed": PreprocessProfile(
        name="skewed",
        operations=("deskew", "clahe", "sharpen"),
        params={"sharpen_amount": 0.5, "clahe_clip": 2.0},
        description="Rotated page: deskew is the point; rest is gentle.",
    ),
    "low_quality": PreprocessProfile(
        name="low_quality",
        operations=("denoise", "deskew", "clahe", "threshold_adaptive"),
        params={
            "denoise_strength": 10.0,
            "clahe_clip": 2.5,
            "adaptive_block": 31,
            "adaptive_c": 10,
        },
        description=(
            "Worst case (blurry + noisy + low contrast): everything "
            "except upscaling, including adaptive thresholding. This is "
            "the only profile that binarises — its mark preservation is "
            "checked explicitly on fixtures. Upscaling was REMOVED from "
            "this profile in M2 calibration: upscaling a 200-DPI A4 page "
            "1.5x (3.9 MP -> 8.7 MP) before denoising pushed fresh-process "
            "peak RSS to ~457 MB — too close to Render free's 512 MB "
            "(ADR-001) for a Stage-1 default. The upscale operation still "
            "exists and can be enabled per page, but only M3 OCR evidence "
            "can justify its cost; see the M2 report."
        ),
    ),
}


def get_profile(name: str) -> PreprocessProfile:
    """Look a profile up by name. Raises ValueError on an unknown name
    — a typo must fail loudly, never silently fall back to default."""
    profile = PREPROCESS_PROFILES.get(name)
    if profile is None:
        raise ValueError(f"Unknown preprocessing profile: {name!r}")
    return profile


def profile_names() -> list[str]:
    return sorted(PREPROCESS_PROFILES)


@dataclass
class QualitySnapshot:
    """The measured numbers select_profile needs (a subset of
    PageQuality, so selection is testable without images)."""

    blur_score: float | None = None
    contrast_score: float | None = None
    noise_score: float | None = None
    skew_degrees: float | None = None
    ink_coverage: float | None = None


def select_profile(quality: QualitySnapshot) -> tuple[str, str]:
    """Pick a profile from MEASURED quality. Returns (name, reason).
    Rules, in priority order — the first matching rule wins and the
    reason is recorded so the choice is auditable per page."""
    if quality.ink_coverage is not None and quality.ink_coverage < 0.005:
        return "clean", "blank/near-blank page: nothing to enhance"
    skewed = quality.skew_degrees is not None and abs(quality.skew_degrees) >= 0.5
    low_contrast = quality.contrast_score is not None and quality.contrast_score < 15
    noisy = quality.noise_score is not None and quality.noise_score > 3
    blurry = quality.blur_score is not None and quality.blur_score < 30
    if blurry and (noisy or low_contrast):
        return "low_quality", (
            f"blur={quality.blur_score:.1f} (<30) with "
            f"noise={quality.noise_score} / contrast={quality.contrast_score}"
        )
    if skewed and (noisy or low_contrast or blurry):
        return "low_quality", f"skew={quality.skew_degrees:.2f} deg with other defects"
    if skewed:
        return "skewed", f"skew={quality.skew_degrees:.2f} deg"
    if noisy:
        return "noisy", f"noise={quality.noise_score:.1f} (>12)"
    if low_contrast:
        return "low_contrast", f"contrast={quality.contrast_score:.1f} (<25)"
    if blurry:
        return "low_quality", f"blur={quality.blur_score:.1f} (<30) alone"
    return "clean", "no defect measured above threshold"
