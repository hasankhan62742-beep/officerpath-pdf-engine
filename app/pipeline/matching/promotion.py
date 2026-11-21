# OfficerPath AI — PDF Engine (Phase 1, M6)
# Pending-question promotion (ADR-007).
#
# M5 left 25 PPSC-66 pending questions answered in the resolution
# but still pending in the ParseResult. The promotion rule decides
# when a pending question becomes a resolved MCQ:
#
# Promote a pending question ONLY when ALL of these hold:
# 1. Its resolution verdict is "answered" (a letter, not UNKNOWN).
# 2. The winning evidence's precedence rank is manual, key, inline,
#    or style — NEVER visual alone (a pen mark needs review) and
#    NEVER inferred alone (an inference is a guess).
# 3. Confidence >= 0.9.
# 4. No conflicts on the verdict.
# 5. It has exactly 4 options.
# 6. No already-answered question carries the same number.
#
# Rationale (recorded in ADR-007): a key/inline/style verdict at
# confidence >= 0.9 is the same evidence that answers a full
# question, so withholding it from a pending question with 4
# options would be false modesty; a visual or inferred verdict
# alone is not strong enough to create an answer. Promotion never
# deletes the pending record's history: the promoted question
# carries ``promoted_from_pending=True`` and the promotion reason,
# and the promotion itself is reported (promoted + skipped with
# reasons) so the review list can audit it.

from __future__ import annotations

from dataclasses import dataclass, field

from app.pipeline.answers.models import ResolvedAnswer
from app.pipeline.answers.precedence import precedence_rank
from app.pipeline.answers.service import AnswerResolution
from app.pipeline.extract.models import ExtractedQuestion, ParseResult

#: Minimum confidence for promotion.
MIN_PROMOTION_CONFIDENCE = 0.9
#: Precedence ranks whose verdicts may promote a pending question.
PROMOTABLE_RANKS = frozenset({"manual", "key", "inline", "style"})


@dataclass
class PromotionReport:
    """What promotion did, and what it refused (with reasons)."""

    promoted: list[int] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "promoted": list(self.promoted),
            "promoted_count": len(self.promoted),
            "skipped": [dict(s) for s in self.skipped],
            "skipped_count": len(self.skipped),
        }


def _promotion_blocker(
    *,
    verdict_status: str,
    source: str,
    confidence: float,
    has_conflicts: bool,
    option_count: int,
    number: int | None,
    answered_numbers: set[int],
    min_confidence: float,
) -> str | None:
    """The reason this pending question must NOT be promoted, or
    None when promotion is allowed. Order matters for honest
    reasons: a conflicted verdict reports the conflict (not
    "UNKNOWN") — ResolvedAnswer.status is "conflict-resolved"
    when conflicts exist even though a letter was decided."""
    if number is None:
        return "question number unknown"
    if number in answered_numbers:
        return "number already answered by another question"
    if has_conflicts:
        return "verdict has unresolved conflicts"
    if verdict_status not in {"answered", "conflict-resolved"}:
        return "verdict is not answered (UNKNOWN)"
    rank = precedence_rank(source)
    if rank not in PROMOTABLE_RANKS:
        return f"winning rank {rank!r} may not promote (needs manual/key/inline/style)"
    if confidence < min_confidence:
        return f"confidence {confidence} below {min_confidence}"
    if option_count != 4:
        return f"has {option_count} options, promotion needs exactly 4"
    return None


def promote_pending(
    result: ParseResult,
    resolution: AnswerResolution,
    *,
    min_confidence: float = MIN_PROMOTION_CONFIDENCE,
) -> PromotionReport:
    """Promote answerable pending questions into ``result.questions``.
    Mutates ``result`` (pending entries move to questions) and
    returns what happened. A pending question is promoted only
    under the ADR-007 rule — see module docstring. Nothing is
    promoted on an inferred verdict alone, and nothing is deleted:
    skipped pendings stay pending with the reason recorded."""
    report = PromotionReport()
    by_number: dict[int | None, list[ResolvedAnswer]] = {}
    for v in resolution.resolved:
        by_number.setdefault(v.question_number, []).append(v)
    answered_numbers = {q.number for q in result.questions if q.number is not None}
    # Verdict lookup is POSITIONAL: resolve_document_answers
    # builds resolution.resolved in document order (questions,
    # then pendings), so the j-th pending's verdict is at
    # resolved[len(questions) + j]. Number-only lookup is wrong
    # when numbers repeat across sections (TestPoint: 1375 rows,
    # 476 unique numbers — every pending Q5 would take the first
    # section's Q5 verdict). A partial/hand-built resolution
    # (fewer verdicts than questions + pendings) falls back to
    # the number lookup, preserving the old behaviour there.
    full_coverage = len(resolution.resolved) == len(result.questions) + len(result.pending)
    question_count = len(result.questions)
    still_pending = []
    for j, pending in enumerate(result.pending):
        if full_coverage:
            verdict: ResolvedAnswer | None = resolution.resolved[question_count + j]
        else:
            verdicts = by_number.get(pending.number, [])
            verdict = verdicts[0] if verdicts else None
        if verdict is None:
            report.skipped.append({"number": pending.number, "reason": "no resolution verdict"})
            still_pending.append(pending)
            continue
        blocker = _promotion_blocker(
            verdict_status=verdict.status,
            source=verdict.source,
            confidence=verdict.confidence,
            has_conflicts=bool(verdict.conflicts),
            option_count=len(pending.options),
            number=pending.number,
            answered_numbers=answered_numbers,
            min_confidence=min_confidence,
        )
        if blocker is not None:
            report.skipped.append({"number": pending.number, "reason": blocker})
            still_pending.append(pending)
            continue
        question = ExtractedQuestion(
            number=pending.number,
            text=pending.text,
            options=list(pending.options),
            correct_index=verdict.correct_index,
            answer_source=verdict.source,
            confidence=verdict.confidence,
            verified=verdict.verified,
            verification_status="verified" if verdict.verified else "unverified",
            paper=pending.paper,
            page=pending.page,
            part=pending.part,
        )
        question.conflicts = list(verdict.conflicts)
        result.questions.append(question)
        answered_numbers.add(pending.number)  # type: ignore[arg-type]
        report.promoted.append(pending.number)  # type: ignore[arg-type]
    result.pending = still_pending
    return report
