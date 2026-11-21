# OfficerPath AI — PDF Engine (Phase 1, M4)
# Validation layer — port of ``parse_validation.dart`` (spec §4.5-4.6,
# §8.2). Separate module, never mutates, never repairs — it only
# reports (D12: the duplicate-text check lives here, as in Dart).
#
# Severities: error (must be fixed or explicitly accepted before
# scoring — duplicates, wrong-paper keys), warning (needs a human
# look), info (expected in normal operation).

from __future__ import annotations

import re

from app.pipeline.extract.models import ParseResult

#: Spec §4.6: instruction verbs exempt from the fabrication
#: "short bare label" check.
INSTRUCTION_VERBS: frozenset[str] = frozenset(
    [
        "choose",
        "select",
        "identify",
        "what",
        "which",
        "who",
        "when",
        "where",
        "give",
        "name",
        "find",
        "translate",
        "fill",
        "complete",
    ]
)


def looks_fabricated(text: str, answer_source: str) -> str | None:
    """Spec §4.6 (``_looksFabricated``). Only for ``flashcard`` /
    ``q-only`` answer sources. Returns a reason string or None.
    (a) starts with an option-letter marker — a key fragment, never a
    stem; (b) bullet label; (c) dash-label tail; (d) short bare label
    ending ``:`` with no ``?`` and no instruction verb, <= 5 words."""
    if answer_source not in ("flashcard", "q-only"):
        return None
    stripped = text.strip()
    if re.match(r"^\(?[A-Da-d]\)", stripped):
        return "starts with an option-letter marker (key fragment, not a stem)"
    if re.match(r"^[-–—•]\s", stripped):
        return "starts with a bullet label"
    if re.search(r"\s+[-–—]\s+[A-Z][^:]{0,40}:\s*$", stripped):
        return "dash-label tail"
    if (
        stripped.endswith(":")
        and "?" not in stripped
        and "؟" not in stripped
        and len(stripped.split()) <= 5
        and not any(word.lower().strip(".,;:!?") in INSTRUCTION_VERBS for word in stripped.split())
    ):
        return "short bare label ending ':' with no '?' and no instruction verb"
    return None


def validate_parse_result(result: ParseResult) -> list[dict]:
    """Port of ``validateParseResult`` (parse_validation.dart:130-230).
    Missing answers -> info; duplicate question TEXT (key =
    ``text.trim().toLowerCase()``) and duplicate NUMBERS -> error;
    conflicting answers and unmatched key entries -> warning;
    suspected fabrications -> warning. Never mutates."""
    issues: list[dict] = []
    # Missing answers -> info.
    for question in result.questions:
        if question.correct_index == -1:
            issues.append(
                {
                    "kind": "missingAnswer",
                    "severity": "info",
                    "detail": (f"Paper {question.paper} Q{question.number} has no answer."),
                    "question_ref": question.number,
                }
            )
    # Duplicate question text -> error.
    text_counts: dict[str, int] = {}
    for question in result.questions:
        key = question.text.strip().lower()
        text_counts[key] = text_counts.get(key, 0) + 1
    for text, count in text_counts.items():
        if count > 1:
            issues.append(
                {
                    "kind": "duplicateQuestion",
                    "severity": "error",
                    "detail": f"Question text parsed {count} times.",
                    "question_ref": text[:60],
                }
            )
    # Duplicate numbers -> error.
    number_counts: dict[int, int] = {}
    for question in result.questions:
        if question.number is not None:
            number_counts[question.number] = number_counts.get(question.number, 0) + 1
    for number, count in number_counts.items():
        if count > 1:
            issues.append(
                {
                    "kind": "duplicateNumber",
                    "severity": "error",
                    "detail": f"Question number {number} parsed {count} times.",
                    "question_ref": number,
                }
            )
    # Conflicting answers -> warning.
    for conflict in result.conflicts:
        issues.append(
            {
                "kind": "conflictingAnswer",
                "severity": "warning",
                "detail": conflict,
                "question_ref": None,
            }
        )
    # Unmatched key entries -> warning.
    for entry in result.unmatched_key_entries:
        issues.append(
            {
                "kind": "unmatchedKeyEntry",
                "severity": "warning",
                "detail": entry,
                "question_ref": None,
            }
        )
    # Fabrication suspects -> warning.
    for question in result.questions:
        reason = looks_fabricated(question.text, question.answer_source)
        if reason:
            issues.append(
                {
                    "kind": "fabricationSuspect",
                    "severity": "warning",
                    "detail": f"Q{question.number}: {reason}",
                    "question_ref": question.number,
                }
            )
    for pair in result.qa_pairs:
        reason = looks_fabricated(pair.question, "flashcard")
        if reason:
            issues.append(
                {
                    "kind": "fabricationSuspect",
                    "severity": "warning",
                    "detail": f"QA pair {pair.number}: {reason}",
                    "question_ref": pair.number,
                }
            )
    return issues
