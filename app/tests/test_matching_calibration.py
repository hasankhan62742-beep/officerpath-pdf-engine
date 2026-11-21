# OfficerPath AI — PDF Engine (Phase 1, M6)
# Confidence calibration tests.

from app.pipeline.matching.calibration import (
    expected_calibration_error,
    fit_calibration,
)


def _points(*buckets: tuple[int, int, float]) -> list[tuple[float, bool]]:
    """buckets: (n_correct, n_total, confidence) per bucket."""
    points: list[tuple[float, bool]] = []
    for correct, total, conf in buckets:
        points.extend([(conf, True)] * correct)
        points.extend([(conf, False)] * (total - correct))
    return points


def test_perfect_calibration_has_zero_ece() -> None:
    points = _points((9, 10, 0.95), (7, 10, 0.7))
    fit = fit_calibration(points)
    # 0.95 bucket: 9/10 = 0.90 vs mean conf 0.95 -> 0.05 gap;
    # 0.70 bucket: 7/10 = 0.70 vs 0.70 -> 0.0 gap.
    assert abs(fit.ece_before - 0.025) < 1e-9


def test_overconfident_bucket_recalibrates_down() -> None:
    # 20 predictions at 0.95 confidence, only 10 correct.
    points = _points((10, 20, 0.95))
    fit = fit_calibration(points)
    assert fit.ece_before == 0.45
    # Calibrated score should be near the observed 0.5.
    assert abs(fit.calibrate(0.95) - 0.5) < 1e-9
    assert fit.ece_after < fit.ece_before


def test_thin_bucket_keeps_raw_confidence() -> None:
    points = _points((1, 2, 0.95), (9, 10, 0.7))
    fit = fit_calibration(points)
    assert fit.calibrate(0.95) == 0.95  # only 2 samples < MIN 5
    assert abs(fit.calibrate(0.7) - 0.9) < 1e-9  # 9/10 observed


def test_exact_1_0_bucket_is_separate() -> None:
    points = _points((5, 5, 1.0), (5, 10, 0.95))
    fit = fit_calibration(points)
    assert abs(fit.calibrate(1.0) - 1.0) < 1e-9
    assert abs(fit.calibrate(0.95) - 0.5) < 1e-9


def test_calibration_buckets_report() -> None:
    points = _points((9, 10, 0.95), (5, 10, 0.6))
    fit = fit_calibration(points)
    rows = {b.label: b for b in fit.buckets}
    assert rows["0.9-1.0"].accuracy == 0.9
    assert rows["0.5-0.7"].accuracy == 0.5
    assert rows["0.9-1.0"].n == 10


def test_ece_helper_matches_fit() -> None:
    points = _points((9, 10, 0.95))
    assert abs(expected_calibration_error(points) - 0.05) < 1e-9


def test_calibration_serialises() -> None:
    fit = fit_calibration(_points((9, 10, 0.95)))
    dumped = fit.to_dict()
    assert dumped["ece_before"] == fit.ece_before
    assert dumped["total_pairs"] == 10
    assert dumped["buckets"][3]["bucket"] == "0.9-1.0"
    assert dumped["buckets"][3]["accuracy"] == 0.9
    assert dumped["buckets"][3]["calibrated_confidence"] == 0.9
