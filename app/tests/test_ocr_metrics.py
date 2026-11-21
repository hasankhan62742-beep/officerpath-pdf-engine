# OfficerPath AI — Phase 1, M3
# Metrics: CER / WER / reading-order scores, pinned on hand-computed
# examples (the benchmark report stands on these definitions).

from app.pipeline.ocr.metrics import (
    cer,
    column_order_accuracy,
    pairwise_order_score,
    sequence_alignment,
    wer,
)


def test_cer_identical_is_zero():
    assert cer("hello world", "hello world") == 0.0


def test_cer_one_substitution():
    # "cat" vs "cut": 1 substitution / 3 chars.
    assert cer("cat", "cut") == 1 / 3


def test_cer_empty_reference():
    assert cer("", "") == 0.0
    assert cer("", "something") == 1.0


def test_cer_ignores_digit_encoding_and_whitespace():
    # Urdu digit ۵ vs ASCII 5, and a line break vs a space, are not errors.
    assert cer("Q5  answer", "Q۵\nanswer") == 0.0


def test_wer_one_word_wrong():
    assert wer("one two three", "one two four") == 1 / 3


def test_wer_empty():
    assert wer("", "") == 0.0
    assert wer("", "x") == 1.0


def test_pairwise_order_perfect():
    assert pairwise_order_score(["a", "b", "c"], ["a", "b", "c"]) == 1.0


def test_pairwise_order_swapped_pair():
    # One adjacent pair out of two is out of order.
    assert pairwise_order_score(["a", "b", "c"], ["b", "a", "c"]) == 0.5


def test_pairwise_order_ignores_missing_lines():
    # "b" was not recognised at all: the remaining pair a<c is ordered.
    assert pairwise_order_score(["a", "b", "c"], ["a", "c"]) == 1.0


def test_pairwise_order_too_few_to_order():
    assert pairwise_order_score(["a"], ["a"]) == 1.0
    assert pairwise_order_score(["a", "b"], ["b"]) == 1.0


def test_column_order_accuracy_interleaved_is_half():
    # Definition: fraction of left lines appearing before the FIRST
    # recognised right line. Interleaved: only L1 qualifies -> 0.5.
    left = ["L1", "L2"]
    right = ["R1", "R2"]
    assert column_order_accuracy(left, right, ["L1", "R1", "L2", "R2"]) == 0.5


def test_column_order_accuracy_all_left_after_right_is_zero():
    left = ["L1", "L2"]
    right = ["R1", "R2"]
    assert column_order_accuracy(left, right, ["R1", "R2", "L1", "L2"]) == 0.0


def test_column_order_accuracy_clean_is_one():
    left = ["L1", "L2"]
    right = ["R1", "R2"]
    assert column_order_accuracy(left, right, ["L1", "L2", "R1", "R2"]) == 1.0


def test_sequence_alignment_marks_missing_and_extra():
    rows = sequence_alignment(["a", "b", "c"], ["a", "x", "c", "d"])
    statuses = [row[0] for row in rows]
    assert statuses == ["match", "substitute", "match", "extra"]
