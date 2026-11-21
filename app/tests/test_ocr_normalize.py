# OfficerPath AI — Phase 1, M3
# Normalisation: comparison form only — stored originals are never
# touched by these helpers (see normalize.py).

from app.pipeline.ocr.normalize import (
    detect_script,
    normalize_digits_only,
    normalize_for_comparison,
)


def test_normalize_unifies_urdu_and_arabic_indic_digits():
    assert normalize_for_comparison("Q۵ and Q٥") == "Q5 and Q5"


def test_normalize_collapses_whitespace():
    assert normalize_for_comparison("a\n\n  b\tc ") == "a b c"


def test_normalize_digits_only_keeps_text():
    assert normalize_digits_only("Q۵ (A) test") == "Q5 (A) test"


def test_detect_script_urdu():
    assert detect_script("یہ اردو ہے") == "urdu"


def test_detect_script_latin():
    assert detect_script("Hello world") == "latin"


def test_detect_script_mixed():
    assert detect_script("Hello اردو") == "mixed"


def test_detect_script_empty_and_digits():
    assert detect_script("   ") == "empty"
    assert detect_script("123-45") == "digits"
