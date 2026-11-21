# OfficerPath AI — PDF Engine (Phase 1, M6)
# Regression test for the calibration-pairing harness bug found in
# the M6 benchmark run 2: ``_calibration_points`` paired detected
# questions to ground truth by NUMBER ONLY. TestPoint Sr# restarts
# per section (1375 rows, 476 unique numbers), so a detected Q5
# paired with the wrong section's GT Q5 and the fitted accuracy at
# confidence 1.0 came out 0.392 — a harness artifact, not a
# detector finding. Pairing must use number + stem similarity, the
# same pairing ``_score_mcq`` uses.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import benchmark_m6  # noqa: E402


def test_duplicate_numbers_pair_by_stem_not_by_last_row() -> None:
    detected = [
        {
            "number": 5,
            "text": "What is 2 plus 2?",
            "options": ["3", "4", "5", "6"],
            "correct_index": 1,
            "confidence": 1.0,
        }
    ]
    gt = [
        {
            "number": 5,
            "text": "What is 2 plus 2?",
            "options": ["3", "4", "5", "6"],
            "answer": "B",
        },
        {
            "number": 5,
            "text": "What is the capital of France?",
            "options": ["London", "Paris", "Berlin", "Rome"],
            "answer": "B",
        },
    ]
    # Number-only pairing would take the LAST Q5 (France, answer B
    # by coincidence here — so use a different letter below).
    gt[1]["answer"] = "C"
    points = benchmark_m6._calibration_points(detected, gt)
    assert points == [(1.0, True)]


def test_key_gt_pairs_by_number_when_stems_are_empty() -> None:
    # The PPSC-66 live key GT has no stems (text ""); number
    # pairing is valid there because numbers are unique 1..100.
    detected = [
        {
            "number": 5,
            "text": "Some OCR-garbled stem here",
            "options": ["A", "B", "C", "D"],
            "correct_index": 1,
            "confidence": 1.0,
        }
    ]
    gt = [{"number": 5, "text": "", "options": ["", "", "", ""], "answer": "B"}]
    points = benchmark_m6._calibration_points(detected, gt, by_number=True)
    assert points == [(1.0, True)]
    # ...but stem pairing with an empty GT stem matches nothing.
    assert benchmark_m6._calibration_points(detected, gt) == []


def test_points_use_raw_confidence_not_calibrated() -> None:
    # M6 regression (run 3): the run-2 fit (1.0 -> 0.392) was
    # still on disk, the parses loaded it, and the calibration
    # points came out at mean confidence 0.392 — the fit chasing
    # its own tail. Points must use raw_confidence.
    detected = [
        {
            "number": 1,
            "text": "Answered question here",
            "options": ["A", "B", "C", "D"],
            "correct_index": 0,
            "confidence": 0.392,
            "raw_confidence": 1.0,
        }
    ]
    gt = [
        {"number": 1, "text": "Answered question here", "options": [], "answer": "A"},
    ]
    assert benchmark_m6._calibration_points(detected, gt) == [(1.0, True)]


def test_unanswered_and_unknown_answers_excluded() -> None:
    detected = [
        {
            "number": 1,
            "text": "Answered question here",
            "options": ["A", "B", "C", "D"],
            "correct_index": 0,
            "confidence": 1.0,
        },
        {
            "number": 2,
            "text": "Unanswered question here",
            "options": ["A", "B", "C", "D"],
            "correct_index": -1,
            "confidence": 0.0,
        },
    ]
    gt = [
        {"number": 1, "text": "Answered question here", "options": [], "answer": "A"},
        {"number": 2, "text": "Unanswered question here", "options": [], "answer": None},
    ]
    assert benchmark_m6._calibration_points(detected, gt) == [(1.0, True)]
