# OfficerPath AI — Phase 1, M7
# Section identity through the answer detectors: a key evidence
# from one section must never attach to a same-numbered question
# in another section (M6 residual limitation). The regression case
# is a two-section paper where Q5 exists in both sections with
# DIFFERENT correct answers.

from app.pipeline.answers.key_detector import detect_trailing_key
from app.pipeline.answers.models import AnswerEvidence, section_key
from app.pipeline.answers.service import resolve_document_answers
from app.pipeline.extract.models import ExtractedQuestion, ParseResult


def _question(number: int, paper: str, part: str, options=None) -> ExtractedQuestion:
    return ExtractedQuestion(
        number=number,
        text=f"Q{number} in {paper}/{part or 'main'}?",
        options=list(options or ["a", "b", "c", "d"]),
        paper=paper,
        part=part,
    )


def test_section_key_differs_across_sections() -> None:
    a = _question(5, "Paper 1", "Section A")
    b = _question(5, "Paper 1", "Section B")
    assert section_key(a) != section_key(b)
    assert section_key(a) == section_key(_question(9, "Paper 1", "Section A"))


def test_key_evidence_attaches_only_to_its_own_section() -> None:
    # Two sections, same number, different answers: section A Q5
    # is (B), section B Q5 is (D). The trailing key says 5 -> (B)
    # and belongs to section A (first occurrence).
    q_a = _question(5, "Paper 1", "Section A")
    q_b = _question(5, "Paper 1", "Section B")
    result = ParseResult(questions=[q_a, q_b])
    detection = detect_trailing_key(
        "5. (B)",
        questions=[q_a, q_b],
        source_document_id="two-section",
    )
    assert len(detection.applied) == 1
    assert detection.applied[0].section == section_key(q_a)
    resolution = resolve_document_answers(result, list(detection.applied))
    assert len(resolution.resolved) == 2
    # Section A takes the key answer (B = index 1).
    assert resolution.resolved[0].correct_index == 1
    assert resolution.resolved[0].source == "trailing-key"
    # Section B must NOT inherit section A's key entry: it stays
    # UNKNOWN (never guessed from another section's key).
    assert resolution.resolved[1].correct_index == -1
    assert resolution.resolved[1].status == "unknown"


def test_unsectioned_evidence_skipped_when_number_is_ambiguous() -> None:
    # A detector that does not know the section: its evidence for
    # an ambiguous number must be skipped with a recorded note,
    # not attached to the first question carrying that number.
    q_a = _question(5, "Paper 1", "Section A")
    q_b = _question(5, "Paper 1", "Section B")
    result = ParseResult(questions=[q_a, q_b])
    stray = AnswerEvidence(
        detector="trailing-key",
        question_number=5,
        correct_index=2,
        confidence=1.0,
        evidence="key entry 5 -> (C) (no section known)",
        section="",
    )
    resolution = resolve_document_answers(result, [stray])
    assert all(r.correct_index == -1 for r in resolution.resolved)
    assert any("more than one section" in n for n in resolution.notes)


def test_unsectioned_evidence_still_joins_when_number_is_unique() -> None:
    # Single-section paper (PPSC-66 shape): the number occurs in
    # exactly one section, so an unsectioned evidence still joins
    # — the M6 behaviour for flat papers is unchanged.
    q1 = _question(5, "Paper 1", "")
    q2 = _question(6, "Paper 1", "")
    result = ParseResult(questions=[q1, q2])
    evidence = AnswerEvidence(
        detector="trailing-key",
        question_number=5,
        correct_index=1,
        confidence=1.0,
        evidence="key entry 5 -> (B)",
        section="",
    )
    resolution = resolve_document_answers(result, [evidence])
    assert resolution.resolved[0].correct_index == 1
    assert resolution.resolved[1].correct_index == -1
    assert not resolution.notes


def test_m4_evidence_is_section_scoped_to_its_own_question() -> None:
    # Each question's own M4 inline answer stays with that
    # question even when the other section's same number has a
    # different M4 answer.
    q_a = _question(5, "Paper 1", "Section A")
    q_a.correct_index = 0
    q_a.answer_source = "answer-line"
    q_a.confidence = 1.0
    q_b = _question(5, "Paper 1", "Section B")
    q_b.correct_index = 3
    q_b.answer_source = "answer-line"
    q_b.confidence = 1.0
    result = ParseResult(questions=[q_a, q_b])
    resolution = resolve_document_answers(result, [])
    assert resolution.resolved[0].correct_index == 0
    assert resolution.resolved[1].correct_index == 3
