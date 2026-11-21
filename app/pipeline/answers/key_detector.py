# OfficerPath AI — PDF Engine (Phase 1, M5)
# Trailing-key detector: parse a trailing answer key (number ->
# letter) from the SAME paper and join it to the detected
# questions — with the noise the real fixtures actually produce
# filtered out and reported, never silently applied.
#
# Noise this detector filters (all measured on PPSC-66, M4):
# - OCR-noise numbers outside the paper's question range
#   (1088/1258/1335/2021 on p7 — page furniture / years read as
#   key entries).
# - Unknown key tokens (``?`` / ``unknown``) — excluded, never
#   guessed (spec §6.8).
# - Key tokens that resolve to no option of the matched question.
# - A key whose paper identity does not match the questions
#   (``decide_key_match``) — withheld entirely, never partially
#   applied (spec §5.5).
# - Entries from a following paper swallowed into the key section
#   (e.g. Paper 67's questions after the Paper-66 key on p7):
#   they parse as entries only when their value looks like an
#   answer token; anything else is rejected at the resolve step
#   with the reason recorded.
#
# The detector reuses the M4 primitives (``parse_key_entries``,
# ``resolve_answer_token``, ``decide_key_match``) — it adds the
# filtering, the evidence, and the measurement, not new key
# semantics.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.pipeline.answers.models import AnswerEvidence, DetectorResult
from app.pipeline.extract.keys import (
    decide_key_match,
    is_unknown_key_token,
    parse_key_entries,
    resolve_answer_token,
)


@dataclass
class KeyDetection:
    """The trailing-key detector's verdict for one key section."""

    entries_parsed: dict[int, str]
    applied: list[AnswerEvidence] = field(default_factory=list)
    filtered: list[dict] = field(default_factory=list)
    unmatched: list[int] = field(default_factory=list)
    decision: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "entries_parsed": {str(k): v for k, v in self.entries_parsed.items()},
            "applied": [e.to_dict() for e in self.applied],
            "filtered": [dict(f) for f in self.filtered],
            "unmatched": list(self.unmatched),
            "decision": dict(self.decision),
            "notes": list(self.notes),
        }


def detect_trailing_key(
    key_text: str,
    *,
    questions: list,
    paper_identity: dict | None = None,
    source_document_id: str = "",
    key_is_bare: bool = True,
    single_paper_in_document: bool = True,
    position_evidence: bool = True,
) -> KeyDetection:
    """Detect answers from one trailing-key section.

    ``questions`` are the detected questions the key may join
    (ExtractedQuestion / PendingQuestion / dicts with ``number``
    and ``options``). ``paper_identity`` is the key's paper
    identity (paper_number / paper_title / exam / year); when
    omitted it is read from the first question's paper_identity.
    Returns the parsed entries, the applied evidences, everything
    filtered (with reasons), the unmatched entry numbers, and the
    paper-identity decision. Nothing is applied when the decision
    is needsReview / unverified / mismatch."""
    entries = parse_key_entries(key_text)
    detection = KeyDetection(entries_parsed=dict(entries))
    question_numbers = {q.number for q in questions if getattr(q, "number", None) is not None}
    # dict-shaped questions (benchmark convenience).
    if not question_numbers:
        question_numbers = {
            q["number"] for q in questions if isinstance(q, dict) and q.get("number") is not None
        }
    if not question_numbers:
        detection.notes.append("no questions to join — key withheld entirely, nothing applied.")
        detection.unmatched = sorted(entries)
        return detection
    max_number = max(question_numbers)

    # The KEY's identity comes from the caller; the QUESTIONS'
    # identity comes from the questions themselves. Passing the
    # same dict for both would make the gate vacuous (a key could
    # never mismatch) — the two sides are deliberately separate.
    first = questions[0]
    question_identity = (
        dict(getattr(first, "paper_identity", {}) or {})
        if not isinstance(first, dict)
        else dict(first.get("paper_identity", {}) or {})
    )
    # A default "Paper 1" label is the extractor's placeholder
    # when no paper heading was found (service.DEFAULT_PAPER_LABEL)
    # — it is the ABSENCE of identity, not evidence of a different
    # paper. Treating it as a conflicting identity would withhold
    # every key on every scanned paper whose heading OCR missed
    # (measured on PPSC-66 live: the questions carry the default
    # label while the key says Paper 66 — a "different paper
    # number" mismatch verdict on a placeholder). Drop the default
    # number/title so the gate treats them as absent; a REAL
    # different paper label (e.g. "Paper 67") still mismatches.
    if question_identity.get("paper_title") == "Paper 1" and str(
        question_identity.get("paper_number")
    ) in ("1", "None"):
        question_identity.pop("paper_number", None)
        question_identity.pop("paper_title", None)
    key_identity = dict(paper_identity or question_identity)
    question_identity = dict(question_identity or key_identity)
    key_identity.setdefault("source_document_id", source_document_id)
    question_identity.setdefault("source_document_id", source_document_id)
    coverage = sum(1 for n in entries if n in question_numbers) / len(entries) if entries else 0.0
    decision = decide_key_match(
        key_identity,
        question_identity,
        key_is_bare=key_is_bare,
        single_paper_in_document=single_paper_in_document,
        exclusive_coverage=coverage >= 0.8,
        position_evidence=position_evidence,
    )
    detection.decision = decision
    if decision["confidence"] in ("needsReview", "unverified", "mismatch"):
        detection.notes.append(f"key withheld — {decision['confidence']}: {decision['reason']}.")
        detection.unmatched = sorted(entries)
        return detection
    if decision["confidence"] == "highConfidence":
        detection.notes.append(
            f"key applied at HIGH CONFIDENCE ({decision['reason']}) — verify before saving."
        )

    by_number: dict[int, Any] = {}
    for q in questions:
        number = q.number if not isinstance(q, dict) else q.get("number")
        if number is not None and number not in by_number:
            by_number[number] = q

    for number in sorted(entries):
        token = entries[number]
        if number < 1 or number > max_number:
            detection.filtered.append(
                {
                    "number": number,
                    "token": token,
                    "reason": f"outside paper range 1..{max_number} (OCR noise)",
                }
            )
            continue
        if is_unknown_key_token(token):
            detection.filtered.append(
                {
                    "number": number,
                    "token": token,
                    "reason": "unknown key token — excluded, never guessed",
                }
            )
            continue
        question = by_number.get(number)
        if question is None:
            detection.unmatched.append(number)
            continue
        options = (
            question.options
            if not isinstance(question, dict)
            else list(question.get("options") or [])
        )
        resolved = resolve_answer_token(token, options)
        if resolved is None:
            detection.filtered.append(
                {
                    "number": number,
                    "token": token,
                    "reason": "token resolves to no option of the matched question",
                }
            )
            continue
        detection.applied.append(
            AnswerEvidence(
                detector="trailing-key",
                question_number=number,
                correct_index=resolved,
                confidence=1.0,
                evidence=f"key entry {number} -> ({chr(65 + resolved)}) from {token!r}",
                detail={"key_token": token, "key_decision": decision["confidence"]},
            )
        )
    return detection


def key_detection_to_result(detection: KeyDetection) -> DetectorResult:
    """Wrap a KeyDetection as a DetectorResult (rejections carry
    their reasons)."""
    rejected = [
        {"number": f["number"], "token": f["token"], "reason": f["reason"]}
        for f in detection.filtered
    ]
    rejected.extend(
        {"number": n, "token": None, "reason": "no matching question"} for n in detection.unmatched
    )
    return DetectorResult(
        detector="trailing-key",
        evidences=list(detection.applied),
        rejected=rejected,
        notes=list(detection.notes),
    )
