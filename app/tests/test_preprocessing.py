# OfficerPath AI — PDF Engine (Phase 1, M2) — tests
# Adaptive preprocessing: profile selection from measured quality,
# the operations themselves, and the hard requirement — marks must
# survive every profile. A failing mark check fails the build.

import json
from pathlib import Path

import numpy as np
import pytest

from app.pipeline.pdf.quality import measure_quality, png_to_bgr, png_to_gray
from app.pipeline.pdf.renderer import render_pdf_page
from app.pipeline.preprocess.marks import (
    MarkRegion,
    check_colour_copy_identical,
    check_mark_preservation,
    detect_highlight_regions,
)
from app.pipeline.preprocess.preprocessor import _border_crop, process_page
from app.pipeline.preprocess.profiles import (
    PROFILE_VERSION,
    QualitySnapshot,
    get_profile,
    profile_names,
    select_profile,
)

FIXTURES = Path(__file__).parent / "fixtures" / "m2"


def _clean_render():
    data = (FIXTURES / "clean.pdf").read_bytes()
    rendered = render_pdf_page(data, 1, dpi=200)
    bgr = png_to_bgr(rendered.png_bytes)
    gray = png_to_gray(rendered.png_bytes)
    return bgr, gray, measure_quality(gray)


def _mark_regions() -> list[MarkRegion]:
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    marks = manifest["files"]["clean.pdf"]["marks_page_1"]
    return [
        MarkRegion(
            kind=kind,
            x_min=v["pixels_at_200dpi"][0],
            y_min=v["pixels_at_200dpi"][1],
            x_max=v["pixels_at_200dpi"][2],
            y_max=v["pixels_at_200dpi"][3],
        )
        for kind, v in marks.items()
    ]


def test_all_profiles_are_known_and_versioned():
    assert set(profile_names()) == {
        "clean",
        "default",
        "low_contrast",
        "noisy",
        "skewed",
        "low_quality",
    }
    assert PROFILE_VERSION == "m2-v1"
    for name in profile_names():
        assert get_profile(name).name == name


def test_unknown_profile_fails_loudly():
    with pytest.raises(ValueError, match="Unknown preprocessing profile"):
        get_profile("nonexistent")


@pytest.mark.parametrize(
    "snapshot,expected",
    [
        (QualitySnapshot(ink_coverage=0.0), "clean"),  # blank page
        (
            QualitySnapshot(
                blur_score=700, contrast_score=25, noise_score=0, skew_degrees=0, ink_coverage=0.012
            ),
            "clean",
        ),
        (
            QualitySnapshot(
                blur_score=400,
                contrast_score=24,
                noise_score=0,
                skew_degrees=-5.0,
                ink_coverage=0.012,
            ),
            "skewed",
        ),
        (
            QualitySnapshot(
                blur_score=700,
                contrast_score=25,
                noise_score=4.4,
                skew_degrees=0,
                ink_coverage=0.012,
            ),
            "noisy",
        ),
        (
            QualitySnapshot(
                blur_score=30,
                contrast_score=5,
                noise_score=0,
                skew_degrees=None,
                ink_coverage=0.009,
            ),
            "low_contrast",
        ),
        (
            QualitySnapshot(
                blur_score=20, contrast_score=10, noise_score=9, skew_degrees=0, ink_coverage=0.012
            ),
            "low_quality",
        ),
    ],
)
def test_select_profile_from_measured_quality(snapshot, expected):
    name, reason = select_profile(snapshot)
    assert name == expected
    assert reason  # every selection records its reason


def test_process_page_records_operations_and_quality():
    bgr, gray, quality = _clean_render()
    processed = process_page(bgr, "default", quality_before=quality)
    assert processed.profile_name == "default"
    assert processed.profile_version == PROFILE_VERSION
    assert processed.operations_applied  # deskew skipped, clahe+sharpen applied
    assert processed.quality_before is not None
    assert processed.quality_after is not None
    record = processed.to_record()
    assert record["profile"] == "default"
    assert record["quality_before"]["blur_score"] is not None


def test_marks_survive_every_profile():
    """THE M2 gate test: tick, star, circle and underline must survive
    every profile, and the colour copy must be pixel-identical."""
    bgr, gray, quality = _clean_render()
    regions = [r for r in _mark_regions() if r.kind != "highlight"]
    assert len(regions) == 4  # tick, star, circle, underline
    for name in profile_names():
        processed = process_page(bgr, name, quality_before=quality)
        assert check_colour_copy_identical(bgr, processed.colour_copy), name
        checks = check_mark_preservation(gray, processed.gray, regions)
        for check in checks:
            assert check.preserved, f"{name}: {check.kind} lost (retention={check.retention})"
            assert check.retention is not None and check.retention >= 0.5


def test_deskew_corrects_the_skewed_fixture():
    data = (FIXTURES / "skewed.pdf").read_bytes()
    rendered = render_pdf_page(data, 1, dpi=200)
    bgr = png_to_bgr(rendered.png_bytes)
    gray = png_to_gray(rendered.png_bytes)
    before = measure_quality(gray)
    assert before.skew_degrees is not None and abs(before.skew_degrees) > 4
    processed = process_page(bgr, "skewed", quality_before=before)
    after = processed.quality_after
    assert after is not None and after.skew_degrees is not None
    assert abs(after.skew_degrees) < 1.0


def test_denoise_reduces_measured_noise_on_noisy_fixture():
    data = (FIXTURES / "noisy.pdf").read_bytes()
    rendered = render_pdf_page(data, 1, dpi=200)
    bgr = png_to_bgr(rendered.png_bytes)
    gray = png_to_gray(rendered.png_bytes)
    before = measure_quality(gray)
    assert before.noise_score is not None and before.noise_score > 3
    processed = process_page(bgr, "noisy", quality_before=before)
    after = processed.quality_after
    assert after is not None and after.noise_score is not None
    assert after.noise_score < before.noise_score
    assert after.ink_coverage is not None and before.ink_coverage is not None
    assert abs(after.ink_coverage - before.ink_coverage) < 0.005  # ink kept


def test_low_contrast_profile_lifts_contrast():
    data = (FIXTURES / "low_contrast.pdf").read_bytes()
    rendered = render_pdf_page(data, 1, dpi=200)
    bgr = png_to_bgr(rendered.png_bytes)
    gray = png_to_gray(rendered.png_bytes)
    before = measure_quality(gray)
    processed = process_page(bgr, "low_contrast", quality_before=before)
    after = processed.quality_after
    assert after is not None
    assert after.contrast_score is not None and before.contrast_score is not None
    assert after.contrast_score > before.contrast_score
    assert after.blur_score is not None and before.blur_score is not None
    assert after.blur_score > before.blur_score


def test_border_crop_is_conservative():
    # A realistic page: content spans most of the page with a white
    # border. The crop trims the border but keeps the content + the
    # 10 px safety margin.
    image = np.full((400, 400), 255, dtype=np.uint8)
    image[30:370, 30:370] = 0
    cropped, skip = _border_crop(image)
    assert skip is None
    assert cropped.shape == (360, 360)
    # A page whose content is a small island is NOT cropped: removing
    # >10% of a dimension means the "border" is probably content.
    island = np.full((400, 400), 255, dtype=np.uint8)
    island[150:250, 150:250] = 0
    _, skip_island = _border_crop(island)
    assert skip_island is not None
    # A fully blank page is not cropped at all.
    blank = np.full((400, 400), 255, dtype=np.uint8)
    _, skip_blank = _border_crop(blank)
    assert skip_blank is not None


def test_highlight_detection_finds_the_drawn_highlight():
    bgr, _, _ = _clean_render()
    regions = detect_highlight_regions(bgr)
    assert len(regions) >= 1
    assert all(r["area_px"] > 200 for r in regions)


def test_highlight_detection_empty_on_plain_page():
    image = np.full((400, 400, 3), 255, dtype=np.uint8)
    assert detect_highlight_regions(image) == []
