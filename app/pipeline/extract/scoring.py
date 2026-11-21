# OfficerPath AI — PDF Engine (Phase 1, M4)
# CANDIDATE SCORING (M4 addition over Dart's regex+guards).
#
# Each candidate question/option set is scored by multiple signals;
# the weighted sum is ``candidate_confidence`` (0..1) plus the
# component ``candidate_signals`` dict. The score is EVIDENCE ONLY:
# the parser's accept/reject still follows the ported rules — a score
# never overrides a rule, and a low score never deletes a candidate
# that the rules accept.

from __future__ import annotations

#: Weights sum to 1.0.
WEIGHTS: dict[str, float] = {
    "number_pattern": 0.35,
    "option_completeness": 0.30,
    "marker_consistency": 0.15,
    "position": 0.10,
    "column_consistency": 0.10,
}

_NUMBER_SCORES: dict[str, float] = {
    "clean": 1.0,
    "decoded": 0.6,
    "numberless": 0.3,
    "none": 0.0,
}


def score_candidate(
    *,
    number_kind: str,
    n_options: int,
    marker_styles: list[str],
    position_continuous: bool,
    column_consistent: bool,
) -> tuple[float, dict[str, float]]:
    """Score one candidate. ``number_kind`` is one of clean / decoded /
    numberless / none. ``marker_styles`` is one style string per
    option (e.g. ``"(A)"``, ``"A."``); all the same style scores 1.0,
    mixed scores 0.5. ``position_continuous`` is True when the
    candidate follows the previous candidate in reading order without
    a jump. ``column_consistent`` is True when all options sit in one
    column (from layout geometry when available, else True when the
    options were collected from consecutive lines)."""
    number_score = _NUMBER_SCORES.get(number_kind, 0.0)
    completeness = n_options / 4.0 if n_options <= 4 else 0.0
    if not marker_styles:
        marker_score = 0.0
    elif len(set(marker_styles)) == 1:
        marker_score = 1.0
    else:
        marker_score = 0.5
    position_score = 1.0 if position_continuous else 0.5
    column_score = 1.0 if column_consistent else 0.5
    signals = {
        "number_pattern": number_score,
        "option_completeness": completeness,
        "marker_consistency": marker_score,
        "position": position_score,
        "column_consistency": column_score,
    }
    confidence = sum(WEIGHTS[k] * v for k, v in signals.items())
    return round(max(0.0, min(1.0, confidence)), 3), signals
