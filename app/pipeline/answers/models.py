# OfficerPath AI — PDF Engine (Phase 1, M5)
# Answer-detection output models. All models are JSON-serialisable
# via ``to_dict()``. Every detection carries its evidence — a
# detector that cannot say WHY it fired has not fired.

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AnswerEvidence:
    """One detector's claim about one question's answer."""

    detector: str  # trailing-key | inline | style-bold | style-star
    # | visual | handwriting | manual | inferred
    question_number: int | None
    correct_index: int = -1  # -1 = this detector found no answer
    confidence: float = 0.0
    evidence: str = ""  # human-readable reason, e.g. "key entry 42 -> (B)"
    answer_text: str | None = None  # free-text answer (qa_pair only)
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "detector": self.detector,
            "question_number": self.question_number,
            "correct_index": self.correct_index,
            "correct_letter": (
                chr(65 + self.correct_index) if 0 <= self.correct_index < 26 else ""
            ),
            "confidence": self.confidence,
            "evidence": self.evidence,
            "answer_text": self.answer_text,
            "detail": dict(self.detail),
        }


@dataclass
class ResolvedAnswer:
    """The precedence resolver's verdict for one question."""

    question_number: int | None
    correct_index: int = -1  # -1 = UNKNOWN, never guessed
    source: str = ""  # winning detector, "" when UNKNOWN
    confidence: float = 0.0
    verified: bool = False
    inferred: bool = False
    conflicts: list[str] = field(default_factory=list)
    evidences: list[AnswerEvidence] = field(default_factory=list)
    answer_text: str | None = None  # free-text answer (qa_pair only)

    @property
    def status(self) -> str:
        if self.correct_index == -1 and self.answer_text is None:
            return "unknown"
        if self.conflicts:
            return "conflict-resolved"
        return "answered"

    def to_dict(self) -> dict:
        return {
            "question_number": self.question_number,
            "correct_index": self.correct_index,
            "correct_letter": (
                chr(65 + self.correct_index) if 0 <= self.correct_index < 26 else ""
            ),
            "source": self.source,
            "confidence": self.confidence,
            "verified": self.verified,
            "inferred": self.inferred,
            "status": self.status,
            "conflicts": list(self.conflicts),
            "evidences": [e.to_dict() for e in self.evidences],
            "answer_text": self.answer_text,
        }


@dataclass
class DetectorResult:
    """One detector's run over one document: every evidence it
    produced, plus what it rejected and why (rejections are data,
    not silence)."""

    detector: str
    evidences: list[AnswerEvidence] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "detector": self.detector,
            "evidences": [e.to_dict() for e in self.evidences],
            "rejected": [dict(r) for r in self.rejected],
            "notes": list(self.notes),
        }
