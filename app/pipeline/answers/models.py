# OfficerPath AI — PDF Engine (Phase 1, M5)
# Answer-detection output models. All models are JSON-serialisable
# via ``to_dict()``. Every detection carries its evidence — a
# detector that cannot say WHY it fired has not fired.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.pipeline.extract.models import (
    ExtractedQuestion,
    PendingQuestion,
    QAPair,
)


def section_key(
    question: ExtractedQuestion | PendingQuestion | QAPair | dict[str, Any],
) -> str:
    """The section key of a question: ``"<paper>|<part>"``.

    ``paper`` is the extractor's paper label ("Paper 1" when no
    heading was found) and ``part`` is the chapter/part label (""
    when none). Two questions in different sections of a
    multi-section paper (TestPoint: Sr# restarts per section) have
    different keys even when their numbers are equal; questions
    in one flat paper share one key. The key is a join key only —
    it is never shown as an answer or a paper identity claim.
    """
    if isinstance(question, dict):
        paper = question.get("paper", "") or ""
        part = question.get("part", "") or ""
    else:
        paper = getattr(question, "paper", "") or ""
        part = getattr(question, "part", "") or ""
    return f"{paper}|{part}"


@dataclass
class AnswerEvidence:
    """One detector's claim about one question's answer.

    ``section`` is the section key of the question this evidence
    belongs to (``"<paper>|<part>"`` — the extractor's paper label
    + chapter/part label; "" when the detector does not know it).
    Section-aware joining (M7) uses it so a key evidence from one
    section can never attach to a same-numbered question in another
    section: an evidence only joins a question in its own section,
    and an unsectioned evidence only joins when its number is
    unambiguous across the document's sections.
    """

    detector: str  # trailing-key | inline | style-bold | style-star
    # | visual | handwriting | manual | inferred
    question_number: int | None
    correct_index: int = -1  # -1 = this detector found no answer
    confidence: float = 0.0
    evidence: str = ""  # human-readable reason, e.g. "key entry 42 -> (B)"
    answer_text: str | None = None  # free-text answer (qa_pair only)
    detail: dict = field(default_factory=dict)
    section: str = ""

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
            "section": self.section,
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
