# OfficerPath AI — Phase 1, M4 tests: candidate scoring (M4 addition
# over Dart — the score is evidence only, it never overrides a rule).

from app.pipeline.extract.blocks import apply_candidate_scoring
from app.pipeline.extract.scoring import WEIGHTS, score_candidate


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_score_bounds():
    for number_kind in ("clean", "decoded", "numberless", "none"):
        confidence, signals = score_candidate(
            number_kind=number_kind,
            n_options=4,
            marker_styles=["A."] * 4,
            position_continuous=True,
            column_consistent=True,
        )
        assert 0.0 <= confidence <= 1.0
        assert set(signals) == set(WEIGHTS)


def test_score_never_overrides_rules():
    # A decoded number with 4/4 options scores below a clean one,
    # but the score is only evidence — the parser's accept/reject
    # follows the ported rules (tested in test_extract_blocks).
    clean_conf, _ = score_candidate(
        number_kind="clean",
        n_options=4,
        marker_styles=["A."] * 4,
        position_continuous=True,
        column_consistent=True,
    )
    decoded_conf, _ = score_candidate(
        number_kind="decoded",
        n_options=4,
        marker_styles=["A."] * 4,
        position_continuous=True,
        column_consistent=True,
    )
    assert decoded_conf < clean_conf


def test_apply_candidate_scoring_attaches_fields():
    candidates = [
        {
            "number": 1,
            "number_kind": "clean",
            "options": ["a", "b", "c", "d"],
            "marker_styles": ["(A)"] * 4,
        },
        {
            "number": 2,
            "number_kind": "clean",
            "options": ["a", "b", "c", "d"],
            "marker_styles": ["(A)"] * 4,
        },
    ]
    apply_candidate_scoring(candidates)
    assert candidates[0]["candidate_confidence"] == 1.0
    assert candidates[1]["candidate_confidence"] == 1.0
    # A number jump breaks position continuity (1.0 -> 0.5 on that
    # component, -0.05 overall).
    candidates[1]["number"] = 5
    apply_candidate_scoring(candidates)
    assert candidates[1]["candidate_confidence"] == 0.95
