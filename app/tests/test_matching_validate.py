# OfficerPath AI — PDF Engine (Phase 1, M6)
# Validation tests: every failure carries a reason code.

from app.pipeline.matching.models import MatchedDocument, ResolvedMCQ
from app.pipeline.matching.validate import validate_matched_document, validate_question


def _mcq(number: int, **overrides) -> ResolvedMCQ:
    base = {
        "number": number,
        "text": f"Q{number}?",
        "options": ["A", "B", "C", "D"],
        "correct_index": 1,
        "status": "answered",
    }
    base.update(overrides)
    return ResolvedMCQ(**base)


def test_clean_mcq_has_no_issues() -> None:
    assert validate_question(_mcq(1)) == []


def test_incomplete_options_flagged() -> None:
    issues = validate_question(_mcq(2, options=["A", "B"]))
    assert [i.code for i in issues] == ["incomplete-options"]


def test_too_many_options_flagged() -> None:
    issues = validate_question(_mcq(3, options=["A", "B", "C", "D", "E"]))
    assert "too-many-options" in [i.code for i in issues]


def test_empty_option_flagged() -> None:
    issues = validate_question(_mcq(4, options=["A", "", "C", "D"]))
    assert "empty-option" in [i.code for i in issues]


def test_duplicate_option_flagged() -> None:
    issues = validate_question(_mcq(5, options=["Paris", "paris ", "C", "D"]))
    assert "duplicate-option" in [i.code for i in issues]


def test_answer_out_of_range_flagged() -> None:
    issues = validate_question(_mcq(6, correct_index=7))
    assert "answer-out-of-range" in [i.code for i in issues]


def test_unknown_answer_is_missing_answer_issue() -> None:
    issues = validate_question(_mcq(7, correct_index=-1, status="unknown"))
    assert "missing-answer" in [i.code for i in issues]


def test_conflicts_flagged() -> None:
    issues = validate_question(_mcq(8, conflicts=["key says B, inline says C"]))
    assert "unresolved-conflict" in [i.code for i in issues]


def test_qa_pair_needs_no_options() -> None:
    pair = ResolvedMCQ(
        number=1,
        text="What is 2+2?",
        options=[],
        status="answered",
        kind="qa_pair",
        answer_text="4",
    )
    assert validate_question(pair) == []


def test_qa_pair_without_answer_text_flagged() -> None:
    pair = ResolvedMCQ(number=1, text="What?", options=[], status="unknown", kind="qa_pair")
    assert "missing-answer" in [i.code for i in validate_question(pair)]


def test_document_duplicate_numbers_and_gaps() -> None:
    matched = MatchedDocument(
        questions=[_mcq(1), _mcq(2), _mcq(2), _mcq(5)],
    )
    issues = validate_matched_document(matched)
    codes = [i.code for i in issues]
    assert "duplicate-number" in codes
    assert "number-gap" in codes
    gap = next(i for i in issues if i.code == "number-gap")
    assert "3" in gap.message and "4" in gap.message
    # Issues are attached to the questions too.
    assert any(i.code == "duplicate-number" for i in matched.questions[2].validation_issues)


def test_promoted_with_incomplete_options_flagged() -> None:
    question = _mcq(9, options=["A", "B"], promoted_from_pending=True)
    codes = [i.code for i in validate_question(question)]
    assert "incomplete-options" in codes
    assert "promoted-with-incomplete-options" in codes
