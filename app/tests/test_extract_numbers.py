# OfficerPath AI — Phase 1, M4 tests: question-number detection
# (spec §1). Uses the spec's own examples as test cases.

from app.pipeline.extract.numbers import (
    bare_number_at_start,
    decode_ocr_number,
    is_misread_number_start,
    normalize_urdu_digits,
    question_number_detailed,
    strip_question_number_prefix,
)


def test_clean_number_regex():
    assert question_number_detailed("1. What is the capital?") == (1, False)
    assert question_number_detailed("Q12. What?") == (12, False)
    assert question_number_detailed("Q.12: What?") == (12, False)
    assert question_number_detailed("Q.1: What?") == (1, False)
    assert question_number_detailed("12) What?") == (12, False)
    # The (?!\d) guard: a decimal is never a question number.
    assert question_number_detailed("92.97 m of rope") is None


def test_ocr_misread_fallback():
    # "S1" decodes to 51 but the separator must be "." or ")" — never
    # ":" (S1:/S6: are source-bank sequence labels).
    assert question_number_detailed("S1. What?") == (51, True)
    assert question_number_detailed("S1: What?") is None
    assert question_number_detailed("l2. What?") == (12, True)


def test_decode_ocr_number_map():
    assert decode_ocr_number("I") is None  # bare letter, no real digit
    assert decode_ocr_number("B") is None
    assert decode_ocr_number("S") is None
    assert decode_ocr_number("1I") == 11
    assert decode_ocr_number("O") is None
    assert decode_ocr_number("1O") == 10
    assert decode_ocr_number("S1") == 51
    assert decode_ocr_number("8B") == 88
    assert decode_ocr_number("Z2") == 22
    assert decode_ocr_number("1234") == 1234  # pure digits, any length
    assert decode_ocr_number("3212") == 3212
    assert decode_ocr_number("12345") == 12345
    assert decode_ocr_number("1O2O") is None  # letter-bearing, max 3 chars
    assert decode_ocr_number("0") is None  # result must be >= 1
    assert decode_ocr_number("00") is None


def test_is_misread_number_start():
    assert is_misread_number_start("6. What is 2+2?")
    assert not is_misread_number_start("6.2x20 = 124.")
    assert is_misread_number_start("S1. First question")


def test_bare_number():
    assert bare_number_at_start("52 Who was the first?") == 52
    assert bare_number_at_start("1947 Was a leap year?") == 1947
    assert bare_number_at_start("3 apples are red.") is None


def test_strip_question_number_prefix():
    assert strip_question_number_prefix("1. What is this?") == "What is this?"
    assert strip_question_number_prefix("Q. 1. What is this?") == "What is this?"
    # Bare number strips only when the text ends with ?/؟.
    assert strip_question_number_prefix("52 Who was the first?") == ("Who was the first?")
    assert strip_question_number_prefix("3 apples are red.") == ("3 apples are red.")
    # Known ambiguity (ported, not fixed): a question opening with a
    # year loses the year.
    assert strip_question_number_prefix("1947 Was a leap year?") == ("Was a leap year?")
    # "Quality ..." is never stripped (bare-Q needs a separator).
    assert strip_question_number_prefix("Quality education matters.") == (
        "Quality education matters."
    )


def test_urdu_digits_normalised_for_matching_only():
    assert normalize_urdu_digits("۱۲. سوال؟") == "12. سوال؟"
    assert normalize_urdu_digits("۵") == "5"
    assert question_number_detailed("۱۲. سوال؟") == (12, False)
    # Stored text keeps the original digits (normalisation is for
    # matching only) — the function returns the ASCII form for the
    # match, the caller keeps the original line.
    assert "۱۲" in "۱۲. سوال؟"
