# OfficerPath AI — Phase 1, M4 tests: option markers and sanitisation
# (spec §2-§3). Uses the spec's own examples as test cases.

from app.pipeline.extract.markers import (
    clean_answer_token,
    clean_stored,
    defect_reason,
    has_asterisk,
    has_tick,
    is_noise_line,
    is_numeric_option_run,
    is_option_continuation,
    normalise_five_options,
    normalize_ligatures,
    option_line_match,
    split_option_line,
    strip_answer_tail,
    strip_asterisks,
    strip_leading_tick,
    strip_ticks,
)
from app.pipeline.extract.numbers import decode_ocr_number  # noqa: F401


def test_option_line_markers():
    assert option_line_match("(A) Karachi") == ("A", "Karachi")
    assert option_line_match("A. Karachi") == ("A", "Karachi")
    assert option_line_match("A) Karachi") == ("A", "Karachi")
    assert option_line_match("A: Karachi") == ("A", "Karachi")
    assert option_line_match("A- Karachi") == ("A", "Karachi")
    assert option_line_match("b. Lahore") == ("B", "Lahore")
    assert option_line_match("(C) Islamabad") == ("C", "Islamabad")
    # Misread digits match ONLY parenthesised: (8) -> B, (0) -> D.
    assert option_line_match("(8) Lahore") == ("B", "Lahore")
    assert option_line_match("(0) Quetta") == ("D", "Quetta")
    # A bare "8." is a question number (Q8), never an option marker.
    assert option_line_match("8. Lahore") is None
    assert option_line_match("4. Lahore") is None


def test_split_option_line():
    split = split_option_line("(A) 1941 (B) 1942")
    assert split == [("A", "1941"), ("B", "1942")]
    split = split_option_line("(A) 1941 (B) 1942 (C) 1943 (D) 1944")
    assert [letter for letter, _ in split] == ["A", "B", "C", "D"]
    # The word-boundary rule: the old regex split "(B) 80 Sec. ✓" at
    # the "c." of "Sec." — the word boundary blocks that.
    assert split_option_line("(B) 80 Sec.") is None
    # Non-consecutive markers are not a split.
    assert split_option_line("(A) x (C) y") is None
    # A non-empty prefix must open the set at A...
    assert split_option_line("Q1 (B) x (C) y") is None
    # ...but a bare two-option line may start at any letter.
    assert split_option_line("(C) 1944 (D) 1946") == [
        ("C", "1944"),
        ("D", "1946"),
    ]
    # "E" is not an A-D marker (§2.6), so the line splits as 4
    # options and the "(E) 5" tail stays inside D's text; the E rule
    # (§2.3) applies to own-line E options after A-D are collected.
    assert split_option_line("(A) 1 (B) 2 (C) 3 (D) 4 (E) 5") == [
        ("A", "1"),
        ("B", "2"),
        ("C", "3"),
        ("D", "4 (E) 5"),
    ]
    # OCR-misread markers are decoded BEFORE the consecutiveness check.
    assert split_option_line("(A) x (8) y") == [("A", "x"), ("B", "y")]


def test_option_continuation():
    # Last option is an open sentence + short line + lowercase start.
    assert is_option_continuation("the capital of", "pakistan")
    # Terminal punctuation closes the sentence: no continuation.
    assert not is_option_continuation("the capital of Pakistan.", "next")
    # A long line is explanation prose, never a continuation.
    assert not is_option_continuation("the capital of", "x" * 81)
    # Function-word ending allows a capitalised continuation.
    assert is_option_continuation("the capital of", "Pakistan")
    assert not is_option_continuation("Islamabad", "Pakistan")


def test_five_option_normalisation():
    options = ["A1", "B1", "C1", "D1", "None of these"]
    assert normalise_five_options(options, 1) == (
        ["A1", "B1", "C1", "D1"],
        1,
        "E",
    )
    # Answer E: keep E's text as the 4th option, drop D.
    assert normalise_five_options(options, 4) == (
        ["A1", "B1", "C1", "None of these"],
        3,
        "E",
    )
    # No answer: cannot normalise.
    assert normalise_five_options(options, -1) is None


def test_clean_stored_only_strips_bold_marker_and_whitespace():
    assert clean_stored("  Islamabad\ue000  ") == "Islamabad"
    # Spellings are preserved exactly (SECRATARY is never corrected).
    assert clean_stored("SECRATARY") == "SECRATARY"


def test_tick_and_asterisk_stripping():
    assert has_tick("China ✓")
    assert has_tick("✓ China")
    assert strip_ticks("China ✓") == "China"
    assert strip_leading_tick("✓ B) China") == "B) China"
    assert strip_leading_tick("(✓) B) China") == "B) China"
    assert has_asterisk("HTML*")
    assert has_asterisk("F5 *")
    assert has_asterisk("Flaming.*")
    assert strip_asterisks("HTML*") == "HTML"
    assert strip_asterisks("F5 *") == "F5"
    assert strip_asterisks("Flaming.*") == "Flaming."
    # A "*" in the MIDDLE (multiplication) is never a marker.
    assert not has_asterisk("2 * 3 = 6")
    assert strip_asterisks("2 * 3 = 6") == "2 * 3 = 6"


def test_ligatures():
    assert normalize_ligatures("ﬁnal ﬂag") == "final flag"
    assert normalize_ligatures("final flag") == "final flag"  # idempotent


def test_noise_lines():
    assert is_noise_line("123")
    assert is_noise_line("Page 1 of 71") is False  # furniture, not noise here
    assert is_noise_line("Like and follow us on Facebook")
    assert is_noise_line("For more informative material, visit")
    assert is_noise_line("+92 300 1234567")
    assert not is_noise_line("What is the capital of Pakistan?")
    # >= 3 consecutive bare-digit lines are a numeric option set.
    assert is_numeric_option_run(["3", "4", "5", "6"], 0)
    assert not is_numeric_option_run(["3", "4", "What?"], 0)


def test_defect_reason():
    assert defect_reason(["Q1. What?", "(A) [cut off]"]) is not None
    assert defect_reason(["Q1. What?", "could not determine"]) is not None
    assert defect_reason(["Q1. What?", "(A) Islamabad"]) is None


def test_strip_answer_tail():
    assert strip_answer_tail("What is this? Ans: C") == "What is this?"
    assert strip_answer_tail("What is this? Correct Answer: B") == ("What is this?")


def test_clean_answer_token_guards():
    # Guards keep "Chapter 5 Summary.", "Apollo 11 Mission Control",
    # "The 3 musketeers?" whole.
    assert clean_answer_token("Chapter 5 Summary.") == "Chapter 5 Summary."
    assert clean_answer_token("Apollo 11 Mission Control") == ("Apollo 11 Mission Control")
    assert clean_answer_token("The 3 musketeers?") == "The 3 musketeers?"
    # A token that is ONLY a page indicator is footer debris.
    assert clean_answer_token("- 2 of 62") == ""
    assert clean_answer_token("Page 11") == ""
    # But a bare number alone CAN be a legit answer.
    assert clean_answer_token("42") == "42"
