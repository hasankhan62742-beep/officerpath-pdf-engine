# OfficerPath AI — Phase 1, M4 tests: answer signals and confidence
# (spec §6.1-6.3, §6.11-6.14, §7).

from app.pipeline.extract.keys import resolve_answer_token
from app.pipeline.extract.signals import (
    ANSWER_LINE_RE,
    BARE_ANSWER_RE,
    apply_ocr_provenance,
    confidence_for_source,
    resolve_signals,
    verification_status,
)


def _signals(bold=(), tick=(), asterisk=()):
    return [
        {
            "bold": i in bold,
            "tick": i in tick,
            "asterisk": i in asterisk,
        }
        for i in range(4)
    ]


OPTIONS = ["Karachi", "Lahore", "Islamabad", "Quetta"]


def test_answer_line_regex():
    assert ANSWER_LINE_RE.match("Answer: C")
    assert ANSWER_LINE_RE.match("Ans: (c)")
    assert ANSWER_LINE_RE.match("Correct: Islamabad")
    assert ANSWER_LINE_RE.match("Correct Answer: B) Asif Ali Zardari")
    assert ANSWER_LINE_RE.match("Right Answer: A")
    assert ANSWER_LINE_RE.match("Answer Key: C")
    assert ANSWER_LINE_RE.match("Final Answer: (C) 80")
    assert not ANSWER_LINE_RE.match("What is the capital?")


def test_bare_answer_regex():
    assert BARE_ANSWER_RE.match("(c)")
    assert BARE_ANSWER_RE.match("C")
    assert BARE_ANSWER_RE.match("3")
    assert not BARE_ANSWER_RE.match("CC")


def test_precedence_answer_line_beats_tick():
    index, source, conflicts = resolve_signals(
        _signals(tick=(2,)),
        "A",
        None,
        OPTIONS,
        resolve_token=resolve_answer_token,
    )
    assert index == 0 and source == "answer-line"
    assert conflicts  # the disagreement is recorded, never silent


def test_precedence_key_beats_bold():
    index, source, conflicts = resolve_signals(
        _signals(bold=(1,)),
        None,
        3,
        OPTIONS,
        resolve_token=resolve_answer_token,
    )
    assert index == 3 and source == "key"
    assert conflicts


def test_tick_bold_asterisk_order():
    index, source, _ = resolve_signals(
        _signals(bold=(1,), asterisk=(2,)),
        None,
        None,
        OPTIONS,
        resolve_token=resolve_answer_token,
    )
    assert (index, source) == (1, "bold")
    index, source, _ = resolve_signals(
        _signals(asterisk=(2,)),
        None,
        None,
        OPTIONS,
        resolve_token=resolve_answer_token,
    )
    assert (index, source) == (2, "asterisk")


def test_ambiguous_tick_is_null():
    index, source, conflicts = resolve_signals(
        _signals(tick=(0, 2)),
        None,
        None,
        OPTIONS,
        resolve_token=resolve_answer_token,
    )
    assert index == -1 and source == ""
    assert conflicts


def test_multiple_bold_ignored_with_conflict():
    index, source, conflicts = resolve_signals(
        _signals(bold=(0, 2)),
        None,
        None,
        OPTIONS,
        resolve_token=resolve_answer_token,
    )
    assert index == -1
    assert any("2 options are bold (A, C)" in c for c in conflicts)


def test_confidence_for_source():
    assert confidence_for_source("answer-line") == 1.0
    assert confidence_for_source("key") == 1.0
    assert confidence_for_source("tick") == 0.9
    assert confidence_for_source("bold") == 0.9
    assert confidence_for_source("asterisk") == 0.9
    assert confidence_for_source("flashcard") == 0.9
    assert confidence_for_source("manual") == 1.0
    assert confidence_for_source("ai") == 0.5
    assert confidence_for_source("") == 0.0
    # Unverified -> base x 0.6.
    assert confidence_for_source("tick", verified=False) == 0.54
    assert confidence_for_source("answer-line", verified=False) == 0.6


def test_ocr_provenance_downgrade():
    # OCR tick/bold -> unverified, 0.54.
    assert apply_ocr_provenance("tick", True, 0.9, "ocr") == (False, 0.54)
    assert apply_ocr_provenance("bold", True, 0.9, "ocr") == (False, 0.54)
    # Asterisk, key and answer-line are printed text: exempt.
    assert apply_ocr_provenance("asterisk", True, 0.9, "ocr") == (True, 0.9)
    assert apply_ocr_provenance("key", True, 1.0, "ocr") == (True, 1.0)
    assert apply_ocr_provenance("answer-line", True, 1.0, "ocr") == (True, 1.0)
    # Printed provenance is untouched.
    assert apply_ocr_provenance("tick", True, 0.9, "printed") == (True, 0.9)


def test_verification_status():
    assert verification_status(-1, False, "") == "no-answer"
    assert verification_status(1, True, "key") == "verified"
    assert verification_status(1, False, "tick") == "unverified"
    # Flashcard is never verified, even with an answer.
    assert verification_status(0, True, "flashcard") == "unverified"
    assert verification_status(0, True, "key", True) == "manually-corrected"
