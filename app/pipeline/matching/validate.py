# OfficerPath AI — PDF Engine (Phase 1, M6)
# Validation of resolved MCQs: every resolved MCQ is checked and
# every failure is reported per-question with a reason code, never
# silently dropped.
#
# Issue codes:
# - "incomplete-options" (error): an MCQ with fewer than 4 options.
# - "too-many-options" (error): an MCQ with more than 4 options.
# - "empty-option" (error): an option whose text is empty.
# - "duplicate-option" (error): two options with identical text
#   (case-insensitive, whitespace-collapsed).
# - "answer-out-of-range" (error): correct_index outside 0..3.
# - "duplicate-number" (error): the same question number twice
#   (the duplicate is FLAGGED, never deleted).
# - "number-gap" (document-level error): question numbers are not
#   contiguous (missing numbers listed in the message).
# - "missing-answer" (review): answered state missing — the
#   question needs review, not a malformed record.
# - "unresolved-conflict" (review): detectors disagreed and the
#   verdict carries conflicts.
# - "promoted-with-incomplete-options" (error): a promoted question
#   somehow has fewer than 4 options (the promotion rule forbids
#   this; the issue is the safety net if it ever happens).
#
# Q&A pairs (kind "qa_pair") have no options by design and are
# validated only for a non-empty answer text. "error" issues make
# the document require review; "review" issues list what a human
# must look at.

from __future__ import annotations

from app.pipeline.matching.models import MatchedDocument, ResolvedMCQ, ValidationIssue

#: Codes that make the document require review as malformed data.
ERROR_CODES = frozenset(
    {
        "incomplete-options",
        "too-many-options",
        "empty-option",
        "duplicate-option",
        "answer-out-of-range",
        "duplicate-number",
        "number-gap",
        "promoted-with-incomplete-options",
    }
)


def validate_question(question: ResolvedMCQ) -> list[ValidationIssue]:
    """Validate one resolved MCQ (or Q&A pair)."""
    issues: list[ValidationIssue] = []
    number = question.number
    if question.kind == "qa_pair":
        if not (question.answer_text or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing-answer",
                    message="Q&A pair has no answer text.",
                    question_number=number,
                )
            )
        return issues
    if len(question.options) < 4:
        issues.append(
            ValidationIssue(
                code="incomplete-options",
                message=f"has {len(question.options)} options, needs exactly 4.",
                question_number=number,
            )
        )
        if question.promoted_from_pending:
            issues.append(
                ValidationIssue(
                    code="promoted-with-incomplete-options",
                    message="promoted from pending with fewer than 4 options.",
                    question_number=number,
                )
            )
    elif len(question.options) > 4:
        issues.append(
            ValidationIssue(
                code="too-many-options",
                message=f"has {len(question.options)} options, needs exactly 4.",
                question_number=number,
            )
        )
    seen: dict[str, int] = {}
    for i, option in enumerate(question.options):
        text = (option or "").strip()
        if not text:
            issues.append(
                ValidationIssue(
                    code="empty-option",
                    message=f"option {chr(65 + i)} is empty.",
                    question_number=number,
                )
            )
            continue
        key = " ".join(text.lower().split())
        if key in seen:
            issues.append(
                ValidationIssue(
                    code="duplicate-option",
                    message=(f"option {chr(65 + i)} duplicates option {chr(65 + seen[key])}."),
                    question_number=number,
                )
            )
        else:
            seen[key] = i
    if question.status == "answered":
        if not 0 <= question.correct_index < len(question.options):
            issues.append(
                ValidationIssue(
                    code="answer-out-of-range",
                    message=(
                        f"answer index {question.correct_index} is outside "
                        f"0..{len(question.options) - 1}."
                    ),
                    question_number=number,
                )
            )
    else:
        issues.append(
            ValidationIssue(
                code="missing-answer",
                message="no answer resolved (UNKNOWN) — needs review.",
                question_number=number,
            )
        )
    if question.conflicts:
        issues.append(
            ValidationIssue(
                code="unresolved-conflict",
                message=f"{len(question.conflicts)} detector conflict(s) recorded.",
                question_number=number,
            )
        )
    return issues


def validate_matched_document(matched: MatchedDocument) -> list[ValidationIssue]:
    """Validate every resolved MCQ/Q&A pair plus document-level
    rules (duplicate numbers, number gaps). Attaches the issues to
    the questions and returns the full list."""
    issues: list[ValidationIssue] = []
    seen_numbers: dict[int, ResolvedMCQ] = {}
    numbers: list[int] = []
    for question in matched.questions:
        issues.extend(validate_question(question))
        if question.number is not None:
            numbers.append(question.number)
            if question.number in seen_numbers:
                issues.append(
                    ValidationIssue(
                        code="duplicate-number",
                        message=(
                            f"question number {question.number} appears more "
                            "than once (duplicate flagged, never deleted)."
                        ),
                        question_number=question.number,
                    )
                )
            else:
                seen_numbers[question.number] = question
    for pair in matched.qa_pairs:
        issues.extend(validate_question(pair))
    # Document-level: number gaps.
    unique_numbers = sorted(set(numbers))
    if unique_numbers:
        missing = [
            n
            for n in range(unique_numbers[0], unique_numbers[-1] + 1)
            if n not in set(unique_numbers)
        ]
        if missing:
            issues.append(
                ValidationIssue(
                    code="number-gap",
                    message=f"missing question numbers: {missing[:20]}"
                    + (" ..." if len(missing) > 20 else ""),
                    question_number=None,
                )
            )
    # Re-attach per-question issues (the loop above attached before
    # duplicate-number issues existed; rebuild cleanly).
    by_number: dict[int | None, list[ValidationIssue]] = {}
    for issue in issues:
        by_number.setdefault(issue.question_number, []).append(issue)
    for question in matched.questions:
        question.validation_issues = list(by_number.get(question.number, []))
    for pair in matched.qa_pairs:
        pair.validation_issues = list(by_number.get(pair.number, []))
    matched.validation_issues = issues
    return issues
