# OfficerPath AI — PDF Engine (Phase 1, M6)
# match_document / resolve_with_key_detection / report tests.

from pathlib import Path

from app.pipeline.answers.models import AnswerEvidence, ResolvedAnswer
from app.pipeline.answers.precedence import precedence_rank
from app.pipeline.answers.service import AnswerResolution
from app.pipeline.extract.models import (
    ExtractedQuestion,
    ParseResult,
    PendingQuestion,
    QAPair,
)
from app.pipeline.matching import match_document, resolve_with_key_detection
from app.pipeline.matching.promotion import promote_pending
from app.pipeline.matching.report import build_document_report, report_to_markdown

FIX = Path(__file__).resolve().parent / "fixtures/golden/ppsc66"


def _answered(
    number: int,
    *,
    source: str = "trailing-key",
    confidence: float = 1.0,
    correct_index: int = 1,
) -> ExtractedQuestion:
    return ExtractedQuestion(
        number=number,
        text=f"Q{number}?",
        options=["A", "B", "C", "D"],
        correct_index=correct_index,
        answer_source=source,
        confidence=confidence,
        verified=confidence >= 0.9,
        paper="Paper 66",
        page=1,
    )


def _verdict(
    number: int,
    *,
    source: str = "trailing-key",
    confidence: float = 1.0,
    correct_index: int = 1,
) -> ResolvedAnswer:
    return ResolvedAnswer(
        question_number=number,
        correct_index=correct_index,
        source=source,
        confidence=confidence,
        verified=confidence >= 0.9,
        evidences=[
            AnswerEvidence(
                detector=source,
                question_number=number,
                correct_index=1,
                confidence=confidence,
                evidence=f"key entry {number} -> (B)",
            )
        ],
    )


def test_match_document_joins_questions_verdicts_and_promotion() -> None:
    result = ParseResult(
        questions=[_answered(1), _answered(2)],
        pending=[
            PendingQuestion(
                text="Q3?",
                options=["A", "B", "C", "D"],
                reason="no-key-entry",
                number=3,
                paper="Paper 66",
                page=1,
            )
        ],
        qa_pairs=[QAPair(number=1, question="What is 2+2?", answer="4")],
    )
    resolution = AnswerResolution(resolved=[_verdict(1), _verdict(2), _verdict(3)])
    promotion_report = promote_pending(result, resolution)
    matched = match_document(
        result,
        resolution,
        promoted_numbers=set(promotion_report.promoted),
        promotion_report=promotion_report,
    )
    assert matched.counts["questions"] == 3
    assert matched.answered == 3
    assert matched.counts["pending"] == 0
    q1 = matched.questions[0]
    assert q1.correct_index == 1
    assert q1.correct_letter == "B"
    assert len(q1.evidences) == 1
    assert q1.evidences[0]["detector"] == "trailing-key"
    assert q1.evidences[0]["confidence"] == 1.0
    assert precedence_rank(q1.evidences[0]["detector"]) == "key"
    assert q1.promoted_from_pending is False
    q3 = matched.questions[2]
    assert q3.promoted_from_pending is True
    assert q3.status == "answered"
    assert "ADR-007" in q3.promotion_reason
    assert matched.qa_pairs[0].answer_text == "4"
    assert matched.qa_pairs[0].status == "answered"


def test_match_document_pairs_duplicate_numbers_by_occurrence() -> None:
    # M6 regression: two questions share number 5 (Sr# restarts
    # per section — TestPoint: 1375 rows, 476 unique numbers).
    # The old number-only join gave BOTH the first verdict's
    # answer (measured M6 end-to-end TestPoint answer accuracy
    # 0.5084). Occurrence pairing gives each question its own
    # verdict — and its own evidence trail.
    result = ParseResult(
        questions=[
            _answered(5, correct_index=1),
            _answered(5, correct_index=3),
        ]
    )
    result.questions[1].text = "Q5 second section?"
    resolution = AnswerResolution(
        resolved=[
            _verdict(5, correct_index=1),
            _verdict(5, correct_index=3),
        ]
    )
    matched = match_document(result, resolution)
    assert len(matched.questions) == 2
    assert matched.questions[0].correct_index == 1
    assert matched.questions[1].correct_index == 3


def test_match_document_keeps_unknown_unanswered() -> None:
    result = ParseResult(questions=[_answered(1, correct_index=-1, source="", confidence=0.0)])
    matched = match_document(result, AnswerResolution(resolved=[ResolvedAnswer(question_number=1)]))
    assert matched.answered == 0
    assert matched.unknown == 1
    assert matched.counts["pending"] == 0  # not pending: a question with no answer
    assert matched.questions[0].status == "unknown"
    assert matched.questions[0].evidences == []  # no answer without evidence
    assert matched.questions[0].correct_index == -1


def test_resolve_with_key_detection_uses_located_region() -> None:
    lines = (FIX / "ocr-p6.txt").read_text(encoding="utf-8").splitlines() + (
        (FIX / "ocr-p7.txt").read_text(encoding="utf-8").splitlines()
    )
    # All 100 questions: the key detector withholds the key when its
    # entries cover < 80% of the questions (cross-paper guard), so a
    # single-question document would correctly get nothing.
    result = ParseResult(
        questions=[_answered(n, correct_index=-1, source="", confidence=0.0) for n in range(1, 101)]
    )
    resolution, key_report = resolve_with_key_detection(result, lines, "paper-66")
    verdict = next(v for v in resolution.resolved if v.question_number == 1)
    # Real key entry 1 is "(B) Broke out" -> index 1; the explanation's
    # "(A) Possessed" must not hijack it.
    assert verdict.correct_index == 1
    assert verdict.source == "trailing-key"
    assert key_report["region"]["located"] is True
    assert key_report["region"]["method"] == "heading"
    assert key_report["entries_parsed"] == 100
    answered = [v for v in resolution.resolved if v.correct_index != -1]
    assert len(answered) == 100


def test_resolve_with_key_detection_reports_no_region() -> None:
    result = ParseResult(questions=[_answered(1, correct_index=-1, source="", confidence=0.0)])
    resolution, key_report = resolve_with_key_detection(
        result, ["just some prose", "no key here"], "doc-x"
    )
    assert key_report["region"]["located"] is False
    assert key_report["region"]["method"] == "none"
    assert key_report["entries_parsed"] == 0
    # No key applied: every verdict stays UNKNOWN (never guessed).
    assert all(v.correct_index == -1 for v in resolution.resolved)


def test_report_counts_and_markdown() -> None:
    result = ParseResult(
        questions=[
            _answered(1),
            _answered(2, correct_index=-1, source="", confidence=0.0),
        ],
        pending=[
            PendingQuestion(
                text="Q3?",
                options=["A", "B", "C", "D"],
                reason="no-key-entry",
                number=3,
                paper="Paper 66",
                page=1,
            )
        ],
    )
    resolution = AnswerResolution(resolved=[_verdict(1), ResolvedAnswer(question_number=2)])
    matched = match_document(result, resolution)
    report = build_document_report(matched, promotion=matched.promotion)
    assert report["counts"]["questions"] == 2
    assert report["counts"]["answered"] == 1
    assert report["counts"]["unknown"] == 1
    assert report["counts"]["pending"] == 1
    assert report["by_answer_source"]["trailing-key"] == 1
    assert len(report["pending"]) == 1
    assert report["pending"][0]["number"] == 3
    assert len(report["unknown"]) == 1
    assert report["evidence_trail"][0]["number"] == 1
    md = report_to_markdown(report)
    assert "# Extraction report" in md
    assert "Q3" in md
