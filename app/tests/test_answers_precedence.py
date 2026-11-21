# OfficerPath AI — Phase 1, M5
# Precedence resolver tests: manual > key > inline > style >
# visual > inferred; conflicts are logged, never silently resolved;
# UNKNOWN when nothing fires; inferred answers are capped at 0.5
# and never verified.

from app.pipeline.answers.models import AnswerEvidence
from app.pipeline.answers.precedence import resolve_answer


def _ev(detector: str, index: int, confidence: float = 1.0) -> AnswerEvidence:
    return AnswerEvidence(
        detector=detector,
        question_number=42,
        correct_index=index,
        confidence=confidence,
        evidence=f"{detector} says {chr(65 + index)}",
    )


def test_key_beats_inline_and_style() -> None:
    resolved = resolve_answer([_ev("inline", 0), _ev("style-bold", 1), _ev("trailing-key", 2)])
    assert resolved.correct_index == 2
    assert resolved.source == "trailing-key"
    assert resolved.conflicts
    # A conflict blocks verification even for a key answer — the
    # disagreement must be reviewed, not rubber-stamped.
    assert resolved.verified is False


def test_inline_beats_style_and_visual() -> None:
    resolved = resolve_answer([_ev("visual", 3, 0.9), _ev("style-star", 1), _ev("inline", 0)])
    assert resolved.correct_index == 0
    assert resolved.source == "inline"
    assert len(resolved.conflicts) == 2


def test_manual_beats_everything() -> None:
    resolved = resolve_answer([_ev("trailing-key", 1), _ev("manual", 3)])
    assert resolved.correct_index == 3
    assert resolved.source == "manual"
    assert resolved.conflicts
    assert resolved.verified is False  # conflict blocks verification


def test_agreeing_detectors_verify() -> None:
    resolved = resolve_answer([_ev("trailing-key", 1), _ev("inline", 1)])
    assert resolved.correct_index == 1
    assert resolved.source == "trailing-key"
    assert resolved.conflicts == []
    assert resolved.verified is True


def test_visual_beats_inferred_and_inferred_is_capped() -> None:
    resolved = resolve_answer([_ev("inferred", 2, 0.9), _ev("visual", 1, 0.8)])
    assert resolved.correct_index == 1
    assert resolved.source == "visual"
    assert resolved.verified is False  # visual marks are never verified
    alone = resolve_answer([_ev("inferred", 2, 0.9)])
    assert alone.correct_index == 2
    assert alone.confidence == 0.5  # capped (spec §7.1 ai 0.5)
    assert alone.inferred is True
    assert alone.verified is False


def test_no_evidence_is_unknown_never_guessed() -> None:
    resolved = resolve_answer([])
    assert resolved.correct_index == -1
    assert resolved.source == ""
    assert resolved.status == "unknown"
    resolved2 = resolve_answer(
        [AnswerEvidence(detector="inline", question_number=7, correct_index=-1)]
    )
    assert resolved2.status == "unknown"


def test_same_rank_agreement_is_not_a_conflict() -> None:
    resolved = resolve_answer([_ev("style-bold", 1), _ev("style-star", 1)])
    assert resolved.correct_index == 1
    assert resolved.conflicts == []
    assert resolved.verified is True


def test_same_rank_disagreement_is_a_logged_conflict() -> None:
    resolved = resolve_answer([_ev("style-bold", 1), _ev("style-star", 2)])
    assert resolved.correct_index in (1, 2)
    assert len(resolved.conflicts) == 1
    assert "conflict" in resolved.conflicts[0]
    assert resolved.verified is False


def test_unknown_detector_ranks_as_inferred() -> None:
    resolved = resolve_answer([_ev("mystery-detector", 0), _ev("visual", 1, 0.8)])
    assert resolved.correct_index == 1
    assert resolved.source == "visual"


def test_qa_pair_text_answer_resolves() -> None:
    resolved = resolve_answer(
        [
            AnswerEvidence(
                detector="inline",
                question_number=5,
                correct_index=-1,
                confidence=1.0,
                evidence="inline Q&A answer",
                answer_text="Hardware",
            )
        ]
    )
    assert resolved.status == "answered"
    assert resolved.answer_text == "Hardware"
    assert resolved.source == "inline"
