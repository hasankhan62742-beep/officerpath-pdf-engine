# OfficerPath AI — Phase 1, M5
# Inline-answer detector tests: Ans-column letters, answer lines,
# Q&A text answers, and the monthly-CA UNKNOWN verdict.

from pathlib import Path

from app.pipeline.answers.inline_detector import (
    check_monthly_ca_answers,
    detect_inline_answer,
    detect_qa_answer,
)

OPTIONS = ["of", "for", "on", "with"]


def test_ans_column_letter_resolves() -> None:
    evidence = detect_inline_answer(1, OPTIONS, "A")
    assert evidence is not None
    assert evidence.correct_index == 0
    assert evidence.detector == "inline"
    assert evidence.confidence == 1.0


def test_answer_line_token_with_value_resolves_by_letter() -> None:
    # CA40 shape: "Correct Answer: (B) Privileged" — the letter
    # wins; the trailing value is a cross-check, never the source.
    evidence = detect_inline_answer(98, OPTIONS, "(B) Privileged")
    assert evidence is not None
    assert evidence.correct_index == 1


def test_unresolvable_token_is_rejected_not_guessed() -> None:
    evidence = detect_inline_answer(3, OPTIONS, "Zanzibar")
    assert evidence is not None
    assert evidence.correct_index == -1
    assert "resolves to no option" in evidence.evidence


def test_no_token_is_no_evidence() -> None:
    assert detect_inline_answer(3, OPTIONS, None) is None
    assert detect_inline_answer(3, OPTIONS, "  ") is None


def test_qa_answer_text_is_the_answer() -> None:
    evidence = detect_qa_answer(1, "Physical Part Of Computer Is Called?", "Hardware")
    assert evidence is not None
    assert evidence.answer_text == "Hardware"
    assert evidence.correct_index == -1
    assert evidence.detector == "inline"


def test_empty_qa_answer_is_no_evidence() -> None:
    assert detect_qa_answer(8, "Some question?", "") is None
    assert detect_qa_answer(8, "Some question?", "   ") is None


def test_monthly_ca_july_is_unknown() -> None:
    # Real fixture, span check only (image OCR sample is
    # benchmark work — ocr_images=False keeps the suite fast).
    pdf = (
        Path(__file__).resolve().parent
        / "fixtures/golden/ppsc66/Current-Affairs-July-2025-in-PDF.pdf"
    ).read_bytes()
    check = check_monthly_ca_answers(pdf, "july-2025", ocr_images=False)
    assert check.verdict == "unknown"
    assert check.bold_option_spans == 0
    assert check.coloured_option_spans == 0
    assert check.correct_answer_lines == 0
    assert check.option_spans_checked > 0
    assert check.questions > 0
    assert "no marking mechanism" in check.reason


def test_monthly_ca_march_is_unknown() -> None:
    pdf = (
        Path(__file__).resolve().parent
        / "fixtures/golden/ppsc66/Current-Affairs-March-2025-in-PDF.pdf"
    ).read_bytes()
    check = check_monthly_ca_answers(pdf, "march-2025", ocr_images=False)
    assert check.verdict == "unknown"
    assert check.bold_option_spans == 0
    assert check.correct_answer_lines == 0
