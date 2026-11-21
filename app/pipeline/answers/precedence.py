# OfficerPath AI — PDF Engine (Phase 1, M5)
# Answer precedence (standing rule, enforced in code):
#   manual verification > explicit key > inline answer >
#   digital style > visual > inferred.
#
# The M4 extractor's internal precedence (signals.PRECEDENCE:
# answer-line > key > tick > bold > asterisk) is preserved inside
# the parse — this module resolves ACROSS detectors, where M4's
# "answer-line" is the inline detector, M4's "tick"/"bold"/
# "asterisk" are the style detectors, and "visual" / "inferred" /
# "manual" are new M5 slots. When detectors disagree, the
# higher-precedence detector wins and the conflict is LOGGED, never
# silently overwritten. When NO detector fires, the answer is
# UNKNOWN — never fabricated.

from __future__ import annotations

from app.pipeline.answers.models import AnswerEvidence, ResolvedAnswer

#: Standing precedence, highest first.
PRECEDENCE: tuple[str, ...] = (
    "manual",
    "key",
    "inline",
    "style",
    "visual",
    "inferred",
)

#: Detector name -> precedence rank. M4 source names are mapped to
#: their M5 rank so extractor output can be resolved here too:
#: "answer-line" is the inline detector, "tick"/"bold"/"asterisk"
#: are style detectors (printed marks in the text layer).
DETECTOR_RANK: dict[str, str] = {
    "manual": "manual",
    "trailing-key": "key",
    "key": "key",
    "inline": "inline",
    "answer-line": "inline",
    "style-bold": "style",
    "style-star": "style",
    "bold": "style",
    "asterisk": "style",
    "tick": "style",
    "visual": "visual",
    "handwriting": "visual",
    "inferred": "inferred",
    "ai": "inferred",
}

#: Ranks whose winners count as verified (when confidence >= 0.9
#: and no conflict). Visual marks and inferred answers are never
#: verified — a pen mark needs review, an inference is a guess.
VERIFIED_RANKS: frozenset[str] = frozenset({"manual", "key", "inline", "style"})

#: Inferred answers are capped here (spec §7.1 "ai" 0.5).
INFERRED_CONFIDENCE_CAP = 0.5


def precedence_rank(detector: str) -> str:
    """The precedence rank of a detector name. Unknown detectors
    rank as "inferred" — an unrecognised source can never
    outrank a known one."""
    return DETECTOR_RANK.get(detector, "inferred")


def resolve_answer(evidences: list[AnswerEvidence]) -> ResolvedAnswer:
    """Resolve one question's answer from its detector evidences.
    Highest-precedence firing evidence wins; ANY disagreement
    with the winner — same rank or lower rank — is a logged
    conflict (winner = first in deterministic detector order,
    verified=False). A lower-rank disagreement is still a conflict:
    the higher detector wins, but the losing evidence is recorded,
    never silently overwritten. No firing evidence -> UNKNOWN
    (correct_index -1)."""
    number = evidences[0].question_number if evidences else None
    # An evidence fires when it names an option letter OR carries a
    # free-text answer (qa_pair). An evidence with neither is a
    # non-detection, recorded but not resolving.
    firing = [e for e in evidences if e.correct_index >= 0 or e.answer_text]
    if not firing:
        return ResolvedAnswer(
            question_number=number,
            correct_index=-1,
            source="",
            confidence=0.0,
            verified=False,
            inferred=False,
            conflicts=[],
            evidences=list(evidences),
            answer_text=None,
        )
    rank_order = {rank: i for i, rank in enumerate(PRECEDENCE)}
    firing.sort(key=lambda e: (rank_order[precedence_rank(e.detector)], e.detector))
    top_rank = precedence_rank(firing[0].detector)
    top = [e for e in firing if precedence_rank(e.detector) == top_rank]
    winner = top[0]
    conflicts: list[str] = []
    for other in firing[1:]:
        if (other.correct_index, other.answer_text) != (
            winner.correct_index,
            winner.answer_text,
        ):
            winner_text = (
                chr(65 + winner.correct_index)
                if winner.correct_index >= 0
                else repr(winner.answer_text)
            )
            other_text = (
                chr(65 + other.correct_index)
                if other.correct_index >= 0
                else repr(other.answer_text)
            )
            same_rank = precedence_rank(other.detector) == top_rank
            conflicts.append(
                f"answer conflict: {winner.detector} says {winner_text}, "
                f"{other.detector} says {other_text} — {winner.detector} wins"
                + ("." if same_rank else f" (higher precedence than {other.detector}).")
            )
    confidence = winner.confidence
    inferred = top_rank == "inferred"
    if inferred:
        confidence = min(confidence, INFERRED_CONFIDENCE_CAP)
    verified = not conflicts and top_rank in VERIFIED_RANKS and confidence >= 0.9
    return ResolvedAnswer(
        question_number=number,
        correct_index=winner.correct_index,
        source=winner.detector,
        confidence=round(confidence, 3),
        verified=verified,
        inferred=inferred,
        conflicts=conflicts,
        evidences=list(evidences),
        answer_text=winner.answer_text,
    )
