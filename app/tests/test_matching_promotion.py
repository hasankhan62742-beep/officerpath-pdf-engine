# OfficerPath AI — PDF Engine (Phase 1, M6)
# Pending-question promotion tests (ADR-007 rule).

from app.pipeline.answers.models import ResolvedAnswer
from app.pipeline.answers.service import AnswerResolution
from app.pipeline.extract.models import (
    ExtractedQuestion,
    ParseResult,
    PendingQuestion,
)
from app.pipeline.matching.promotion import promote_pending


def _pending(number: int | None, *, options: list[str] | None = None) -> PendingQuestion:
    return PendingQuestion(
        text=f"Question {number}?",
        options=options if options is not None else ["A", "B", "C", "D"],
        reason="no-key-entry",
        number=number,
        paper="Paper 66",
        page=1,
    )


def _verdict(
    number: int | None,
    *,
    source: str,
    confidence: float = 1.0,
    correct_index: int = 1,
    conflicts: list[str] | None = None,
) -> ResolvedAnswer:
    return ResolvedAnswer(
        question_number=number,
        correct_index=correct_index,
        source=source,
        confidence=confidence,
        verified=confidence >= 0.9 and not conflicts,
        inferred=source == "inferred",
        conflicts=list(conflicts or []),
    )


def _result_with_pending(numbers: list[int | None]) -> ParseResult:
    return ParseResult(pending=[_pending(n) for n in numbers])


def test_key_verdict_promotes() -> None:
    result = _result_with_pending([25])
    resolution = AnswerResolution(resolved=[_verdict(25, source="trailing-key")])
    report = promote_pending(result, resolution)
    assert report.promoted == [25]
    assert result.pending == []
    assert len(result.questions) == 1
    assert result.questions[0].correct_index == 1
    assert result.questions[0].answer_source == "trailing-key"


def test_inline_and_style_promote() -> None:
    result = _result_with_pending([26, 27])
    resolution = AnswerResolution(
        resolved=[
            _verdict(26, source="inline"),
            _verdict(27, source="style-star", confidence=0.9),
        ]
    )
    report = promote_pending(result, resolution)
    assert sorted(report.promoted) == [26, 27]


def test_duplicate_numbers_take_their_own_verdicts() -> None:
    # M6 regression: two pendings share number 5 (Sr# restarts per
    # section). The first one's verdict is inferred (unpromotable);
    # the second one's is a key verdict (promotable). The old
    # number-only join gave BOTH the first verdict, so the second
    # pending was skipped for the first one's reason. Occurrence
    # pairing gives each pending its own verdict in order.
    result = _result_with_pending([5, 5])
    resolution = AnswerResolution(
        resolved=[
            _verdict(5, source="inferred", confidence=0.4, correct_index=0),
            _verdict(5, source="trailing-key", confidence=1.0, correct_index=3),
        ]
    )
    report = promote_pending(result, resolution)
    assert report.promoted == [5]
    assert len(result.questions) == 1
    assert result.questions[0].correct_index == 3
    assert result.questions[0].answer_source == "trailing-key"
    assert len(result.pending) == 1


def test_visual_alone_never_promotes() -> None:
    result = _result_with_pending([28])
    resolution = AnswerResolution(resolved=[_verdict(28, source="visual")])
    report = promote_pending(result, resolution)
    assert report.promoted == []
    assert len(result.pending) == 1
    assert "visual" in report.skipped[0]["reason"]


def test_inferred_alone_never_promotes() -> None:
    result = _result_with_pending([29])
    resolution = AnswerResolution(resolved=[_verdict(29, source="inferred", confidence=0.5)])
    report = promote_pending(result, resolution)
    assert report.promoted == []
    assert "inferred" in report.skipped[0]["reason"]


def test_low_confidence_key_does_not_promote() -> None:
    result = _result_with_pending([30])
    resolution = AnswerResolution(resolved=[_verdict(30, source="trailing-key", confidence=0.8)])
    report = promote_pending(result, resolution)
    assert report.promoted == []
    assert "0.8" in report.skipped[0]["reason"]


def test_conflicted_verdict_does_not_promote() -> None:
    result = _result_with_pending([31])
    resolution = AnswerResolution(
        resolved=[_verdict(31, source="trailing-key", conflicts=["key says B, inline says C"])]
    )
    report = promote_pending(result, resolution)
    assert report.promoted == []
    assert "conflict" in report.skipped[0]["reason"]


def test_unknown_verdict_does_not_promote() -> None:
    result = _result_with_pending([32])
    resolution = AnswerResolution(resolved=[ResolvedAnswer(question_number=32, correct_index=-1)])
    report = promote_pending(result, resolution)
    assert report.promoted == []
    assert "not answered" in report.skipped[0]["reason"]


def test_number_already_answered_does_not_promote() -> None:
    result = ParseResult(
        questions=[
            ExtractedQuestion(number=33, text="Q33?", options=["A", "B", "C", "D"], correct_index=0)
        ],
        pending=[_pending(33)],
    )
    resolution = AnswerResolution(resolved=[_verdict(33, source="trailing-key")])
    report = promote_pending(result, resolution)
    assert report.promoted == []
    assert len(result.questions) == 1  # no duplicate created
    assert "already answered" in report.skipped[0]["reason"]


def test_pending_with_incomplete_options_does_not_promote() -> None:
    result = _result_with_pending([34])
    result.pending[0].options = ["A", "B"]
    resolution = AnswerResolution(resolved=[_verdict(34, source="trailing-key")])
    report = promote_pending(result, resolution)
    assert report.promoted == []
    assert "2 options" in report.skipped[0]["reason"]


def test_pending_without_number_does_not_promote() -> None:
    result = _result_with_pending([None])
    resolution = AnswerResolution(resolved=[_verdict(None, source="trailing-key")])
    report = promote_pending(result, resolution)
    assert report.promoted == []
    assert len(result.pending) == 1
