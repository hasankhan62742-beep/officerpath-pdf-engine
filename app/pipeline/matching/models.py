# OfficerPath AI — PDF Engine (Phase 1, M6)
# Matching output models: the resolved MCQ for one question, the
# validation issues on it, and the matched document as a whole.
#
# A ResolvedMCQ is the M6 join of M4's extraction and M5's answer
# resolution: question + options + answer + the FULL evidence trail
# (which detector fired, its confidence, its precedence rank, the
# source span/page). No answer without evidence — an UNKNOWN answer
# is a correct outcome, a guessed answer is the worst failure.
# All models are JSON-serialisable via ``to_dict()``.

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationIssue:
    """One validation failure on one question (or on the document
    when ``question_number`` is None). Validation failures are
    reported with a reason code, never silently dropped."""

    code: str  # incomplete-options | duplicate-number | answer-out-of-range
    # | missing-answer | empty-option | duplicate-option | number-gap
    # | unresolved-conflict | promoted-with-incomplete-options
    message: str
    question_number: int | None = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "question_number": self.question_number,
        }


@dataclass
class ResolvedMCQ:
    """One fully resolved MCQ: stem + options + answer + evidence."""

    number: int | None
    text: str
    options: list[str]  # exactly 4 for "mcq"; [] for "qa_pair"
    correct_index: int = -1  # -1 = UNKNOWN, never guessed
    answer_source: str = ""  # winning detector, "" when UNKNOWN
    confidence: float = 0.0  # calibrated confidence (see calibration.py)
    raw_confidence: float = 0.0  # confidence before calibration
    verified: bool = False
    inferred: bool = False
    status: str = "unknown"  # answered | unknown | conflict-resolved
    kind: str = "mcq"  # mcq | qa_pair
    answer_text: str | None = None  # free-text answer (qa_pair only)
    page: int = 0
    paper: str = ""
    duplicate: bool = False
    promoted_from_pending: bool = False
    promotion_reason: str = ""  # why this pending question was promoted
    evidences: list[dict] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    validation_issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def correct_letter(self) -> str:
        return chr(65 + self.correct_index) if 0 <= self.correct_index < 4 else ""

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "text": self.text,
            "options": list(self.options),
            "correct_index": self.correct_index,
            "correct_letter": self.correct_letter,
            "answer_source": self.answer_source,
            "confidence": self.confidence,
            "raw_confidence": self.raw_confidence,
            "verified": self.verified,
            "inferred": self.inferred,
            "status": self.status,
            "kind": self.kind,
            "answer_text": self.answer_text,
            "page": self.page,
            "paper": self.paper,
            "duplicate": self.duplicate,
            "promoted_from_pending": self.promoted_from_pending,
            "promotion_reason": self.promotion_reason,
            "evidences": [dict(e) for e in self.evidences],
            "conflicts": list(self.conflicts),
            "validation_issues": [i.to_dict() for i in self.validation_issues],
        }


@dataclass
class MatchedDocument:
    """The matched result for one document: resolved MCQs, Q&A
    pairs, still-pending/unknown items, and the validation summary."""

    questions: list[ResolvedMCQ] = field(default_factory=list)
    qa_pairs: list[ResolvedMCQ] = field(default_factory=list)
    pending: list[dict] = field(default_factory=list)
    validation_issues: list[ValidationIssue] = field(default_factory=list)
    promotion: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def answered(self) -> int:
        return sum(1 for q in self.questions if q.status == "answered")

    @property
    def unknown(self) -> int:
        return sum(1 for q in self.questions if q.status == "unknown")

    def to_dict(self) -> dict:
        return {
            "questions": [q.to_dict() for q in self.questions],
            "qa_pairs": [q.to_dict() for q in self.qa_pairs],
            "pending": [dict(p) for p in self.pending],
            "validation_issues": [i.to_dict() for i in self.validation_issues],
            "promotion": dict(self.promotion),
            "counts": dict(self.counts),
            "notes": list(self.notes),
            "answered": self.answered,
            "unknown": self.unknown,
        }
