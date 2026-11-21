# OfficerPath AI — Phase 1, M5
# Document-level resolution tests: M4 evidence enters as
# evidence; a higher-precedence M5 detector can overturn it; a
# lower-precedence disagreement is a logged conflict, never a
# silent overwrite; UNKNOWN never clears an existing answer.

from app.pipeline.answers.models import AnswerEvidence
from app.pipeline.answers.service import (
    apply_resolution,
    resolve_document_answers,
)
from app.pipeline.extract.models import (
    ExtractedQuestion,
    ParseResult,
    PendingQuestion,
    QAPair,
)

OPTIONS = ["Alpha", "Beta", "Gamma", "Delta"]


def _question(number: int, correct_index: int = -1, source: str = "", confidence: float = 0.0):
    return ExtractedQuestion(
        number=number,
        text=f"Question {number}?",
        options=list(OPTIONS),
        correct_index=correct_index,
        answer_source=source,
        confidence=confidence,
        verified=bool(source),
    )


def _key_evidence(number: int, index: int) -> AnswerEvidence:
    return AnswerEvidence(
        detector="trailing-key",
        question_number=number,
        correct_index=index,
        confidence=1.0,
        evidence=f"key says {chr(65 + index)}",
    )


def test_m4_inline_answer_survives_with_no_new_evidence() -> None:
    result = ParseResult(questions=[_question(1, 1, "answer-line", 1.0)])
    resolution = resolve_document_answers(result)
    assert resolution.answered == 1
    assert resolution.unknown == 0
    assert resolution.resolved[0].correct_index == 1
    assert resolution.resolved[0].source == "inline"


def test_duplicate_numbers_keep_their_own_answers() -> None:
    # M6 regression: question numbers repeat across sections
    # (TestPoint Sr# restarts per section: 1375 rows, 476 unique
    # numbers). The old apply_resolution joined by number and took
    # the FIRST verdict for that number, so every Q5 got the first
    # section's answer and the others' correct M4 answers were
    # clobbered (measured M6 end-to-end TestPoint answer accuracy
    # 0.5084). Occurrence pairing keeps each question's own answer.
    result = ParseResult(
        questions=[
            _question(5, 1, "answer-line", 1.0),
            _question(5, 3, "answer-line", 1.0),
        ]
    )
    resolution = resolve_document_answers(result)
    assert resolution.resolved[0].correct_index == 1
    assert resolution.resolved[1].correct_index == 3
    assert apply_resolution(result, resolution) == 0
    assert result.questions[0].correct_index == 1
    assert result.questions[1].correct_index == 3


def test_trailing_key_overturns_m4_style_answer() -> None:
    # M4 said bold -> (B); the trailing key says (D). Key outranks
    # style, so the answer changes and the conflict is logged.
    result = ParseResult(questions=[_question(1, 1, "bold", 0.9)])
    resolution = resolve_document_answers(result, [_key_evidence(1, 3)])
    assert resolution.resolved[0].correct_index == 3
    assert resolution.resolved[0].source == "trailing-key"
    assert resolution.conflicts
    changed = apply_resolution(result, resolution)
    assert changed == 1
    assert result.questions[0].correct_index == 3
    assert result.questions[0].answer_source == "trailing-key"
    assert result.questions[0].conflicts


def test_style_detector_cannot_overturn_m4_key_answer() -> None:
    # M4 key answer (D) stands; a style detector saying (B) is a
    # logged conflict, never a silent overwrite.
    result = ParseResult(questions=[_question(1, 3, "key", 1.0)])
    style = AnswerEvidence(
        detector="style-bold",
        question_number=1,
        correct_index=1,
        confidence=0.9,
        evidence="bold option (B)",
    )
    resolution = resolve_document_answers(result, [style])
    assert resolution.resolved[0].correct_index == 3
    assert resolution.resolved[0].source == "trailing-key"
    assert resolution.conflicts
    changed = apply_resolution(result, resolution)
    assert changed == 0
    assert result.questions[0].correct_index == 3


def test_pending_question_resolves_from_key_evidence() -> None:
    result = ParseResult(
        pending=[
            PendingQuestion(
                text="Unanswered question?",
                options=list(OPTIONS),
                reason="no-key-entry",
                number=7,
            )
        ]
    )
    resolution = resolve_document_answers(result, [_key_evidence(7, 0)])
    assert resolution.resolved[0].correct_index == 0
    assert resolution.resolved[0].status == "answered"


def test_pending_question_with_no_evidence_stays_unknown() -> None:
    result = ParseResult(
        pending=[
            PendingQuestion(
                text="Unanswered question?",
                options=list(OPTIONS),
                reason="no-key-entry",
                number=8,
            )
        ]
    )
    resolution = resolve_document_answers(result)
    assert resolution.resolved[0].status == "unknown"
    assert resolution.unknown == 1


def test_unknown_verdict_never_clears_existing_answer() -> None:
    from app.pipeline.answers.models import ResolvedAnswer
    from app.pipeline.answers.service import AnswerResolution

    # A detector run that found NOTHING for Q1 returns UNKNOWN;
    # applying it must leave the M4 key answer untouched.
    result = ParseResult(questions=[_question(1, 2, "key", 1.0)])
    resolution = AnswerResolution(resolved=[ResolvedAnswer(question_number=1, correct_index=-1)])
    changed = apply_resolution(result, resolution)
    assert changed == 0
    assert result.questions[0].correct_index == 2
    assert result.questions[0].answer_source == "key"


def test_qa_pair_resolves_on_text_answer() -> None:
    result = ParseResult(
        qa_pairs=[QAPair(number=1, question="Physical part of computer?", answer="Hardware")]
    )
    resolution = resolve_document_answers(result)
    assert len(resolution.qa_resolved) == 1
    assert resolution.qa_resolved[0].answer_text == "Hardware"
    assert resolution.qa_resolved[0].status == "answered"


def test_resolution_summary_counts() -> None:
    result = ParseResult(
        questions=[_question(1, 0, "answer-line", 1.0), _question(2)],
        pending=[PendingQuestion(text="?", options=list(OPTIONS), reason="no-key-entry", number=3)],
    )
    resolution = resolve_document_answers(result)
    assert resolution.answered == 1
    assert resolution.unknown == 2
    assert resolution.to_dict()["answered"] == 1
