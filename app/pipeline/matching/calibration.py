# OfficerPath AI — PDF Engine (Phase 1, M6)
# Confidence calibration: a confidence number that does not track
# real accuracy is a defect, not a feature.
#
# Method (empirical bucket calibration, explainable by design):
# collect (confidence, correct) pairs from resolved MCQs scored
# against ground truth, bucket them by confidence, and report the
# ACTUAL accuracy in each bucket. The expected calibration error
# (ECE) is sum over buckets of |accuracy - mean confidence| * n/N.
# The fitted mapping replaces a prediction's confidence with its
# bucket's measured accuracy — but ONLY for buckets with >=
# MIN_BUCKET_SAMPLES pairs; thin buckets keep their raw confidence
# (not enough evidence to recalibrate, and the report says so).
# A bucket whose accuracy is far below its mean confidence is a
# miscalibration finding, not something to hide by re-bucketing.

from __future__ import annotations

from dataclasses import dataclass, field

#: Confidence buckets: (low, high, label). The exact-1.0 bucket is
#: separate because most detector confidences sit exactly at 1.0.
BUCKETS: tuple[tuple[float, float, str], ...] = (
    (0.0, 0.5, "0.0-0.5"),
    (0.5, 0.7, "0.5-0.7"),
    (0.7, 0.9, "0.7-0.9"),
    (0.9, 1.0, "0.9-1.0"),
    (1.0, 1.0, "1.0"),
)

#: Minimum pairs in a bucket before its accuracy may recalibrate.
MIN_BUCKET_SAMPLES = 5


@dataclass
class CalibrationBucket:
    """One confidence bucket: what the model claimed vs what
    actually happened."""

    label: str
    low: float
    high: float
    n: int = 0
    mean_confidence: float = 0.0
    accuracy: float | None = None  # None when n == 0
    calibrated_confidence: float | None = None  # None = keep raw

    def to_dict(self) -> dict:
        return {
            "bucket": self.label,
            "n": self.n,
            "mean_confidence": round(self.mean_confidence, 3),
            "accuracy": round(self.accuracy, 3) if self.accuracy is not None else None,
            "calibrated_confidence": (
                round(self.calibrated_confidence, 3)
                if self.calibrated_confidence is not None
                else None
            ),
        }


@dataclass
class Calibration:
    """The fitted calibration: bucket table + ECE before/after."""

    buckets: list[CalibrationBucket] = field(default_factory=list)
    ece_before: float = 0.0
    ece_after: float = 0.0
    total_pairs: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "buckets": [b.to_dict() for b in self.buckets],
            "ece_before": round(self.ece_before, 4),
            "ece_after": round(self.ece_after, 4),
            "total_pairs": self.total_pairs,
            "notes": list(self.notes),
        }

    def calibrate(self, raw_confidence: float) -> float:
        """Map a raw confidence to its calibrated value. Buckets
        with too few samples keep the raw confidence. Uses the same
        bucket rule as ``bucketize`` (exact 1.0 is its own bucket)."""
        _, _, label = _bucket_for(raw_confidence)
        for bucket in self.buckets:
            if bucket.label == label:
                if bucket.calibrated_confidence is not None:
                    return bucket.calibrated_confidence
                return raw_confidence
        return raw_confidence


def _bucket_for(confidence: float) -> tuple[float, float, str]:
    for low, high, label in BUCKETS:
        if label == "1.0":
            if confidence == 1.0:
                return (low, high, label)
            continue
        if low <= confidence < high:
            return (low, high, label)
    return BUCKETS[-1]


def bucketize(points: list[tuple[float, bool]]) -> list[CalibrationBucket]:
    """Group (confidence, correct) pairs into buckets."""
    grouped: dict[str, list[tuple[float, bool]]] = {label: [] for _, _, label in BUCKETS}
    for confidence, correct in points:
        grouped[_bucket_for(confidence)[2]].append((confidence, correct))
    buckets: list[CalibrationBucket] = []
    for low, high, label in BUCKETS:
        pairs = grouped[label]
        if not pairs:
            buckets.append(CalibrationBucket(label=label, low=low, high=high))
            continue
        mean_conf = sum(c for c, _ in pairs) / len(pairs)
        accuracy = sum(1 for _, ok in pairs if ok) / len(pairs)
        buckets.append(
            CalibrationBucket(
                label=label,
                low=low,
                high=high,
                n=len(pairs),
                mean_confidence=round(mean_conf, 3),
                accuracy=round(accuracy, 3),
            )
        )
    return buckets


def expected_calibration_error(
    points: list[tuple[float, bool]], *, use_calibrated: Calibration | None = None
) -> float:
    """ECE = sum over buckets of |accuracy - mean confidence| * n/N.
    With ``use_calibrated`` the confidence is first mapped through
    the fitted calibration (the "after" error): the points are
    re-bucketed by their CALIBRATED confidence, so a bucket that
    was overconfident now claims its measured accuracy."""
    if not points:
        return 0.0
    if use_calibrated is not None:
        points = [(use_calibrated.calibrate(c), ok) for c, ok in points]
    total = len(points)
    buckets = bucketize(points)
    ece = 0.0
    for bucket in buckets:
        if bucket.n == 0 or bucket.accuracy is None:
            continue
        ece += abs(bucket.accuracy - bucket.mean_confidence) * (bucket.n / total)
    return round(ece, 4)


def fit_calibration(
    points: list[tuple[float, bool]], *, min_samples: int = MIN_BUCKET_SAMPLES
) -> Calibration:
    """Fit the empirical calibration on (confidence, correct) pairs
    and report ECE before/after. Buckets with fewer than
    ``min_samples`` pairs keep raw confidence (recorded in notes)."""
    buckets = bucketize(points)
    notes: list[str] = []
    for bucket in buckets:
        if bucket.n == 0:
            notes.append(f"bucket {bucket.label}: no samples")
        elif bucket.n < min_samples:
            notes.append(
                f"bucket {bucket.label}: only {bucket.n} samples "
                f"(below {min_samples}) — raw confidence kept"
            )
        else:
            bucket.calibrated_confidence = bucket.accuracy
    calibration = Calibration(
        buckets=buckets,
        total_pairs=len(points),
        notes=notes,
    )
    calibration.ece_before = expected_calibration_error(points)
    calibration.ece_after = expected_calibration_error(points, use_calibrated=calibration)
    return calibration
