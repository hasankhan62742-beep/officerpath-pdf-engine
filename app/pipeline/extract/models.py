# OfficerPath AI — PDF Engine (Phase 1, M4)
# Output models — Python mirror of the Dart ``Question`` /
# ``PendingQuestion`` / ``ParseResult`` (spec §13), with the M4
# additions decided in the task brief:
# - D13: structured paper identity on the question record
#   (``paper_identity`` dict: source_document_id, paper_number,
#   paper_title, exam, year — all nullable, missing = unknown).
# - Candidate scoring fields (``candidate_confidence``,
#   ``candidate_signals``) — an M4 addition over Dart; the score is
#   evidence only, it never overrides a ported rule.
#
# All models are JSON-serialisable via ``to_dict()``.

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractedQuestion:
    number: int | None
    text: str
    options: list[str]  # exactly 4
    correct_index: int = -1  # -1 = no answer, never guessed
    answer_source: str = ""
    confidence: float = 0.0
    verified: bool = False
    verification_status: str = "no-answer"
    paper: str = "Paper 1"
    page: int = 0
    part: str = ""
    format: str = "block"
    explanation: str = ""
    mark_provenance: str = ""  # printed / ocr / ""
    paper_identity: dict = field(default_factory=dict)  # D13
    duplicate: bool = False
    conflicts: list[str] = field(default_factory=list)
    candidate_confidence: float = 0.0
    candidate_signals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "text": self.text,
            "options": list(self.options),
            "correct_index": self.correct_index,
            "correct_letter": (chr(65 + self.correct_index) if self.correct_index >= 0 else ""),
            "answer_source": self.answer_source,
            "confidence": self.confidence,
            "verified": self.verified,
            "verification_status": self.verification_status,
            "paper": self.paper,
            "page": self.page,
            "part": self.part,
            "format": self.format,
            "explanation": self.explanation,
            "mark_provenance": self.mark_provenance,
            "paper_identity": dict(self.paper_identity),
            "duplicate": self.duplicate,
            "conflicts": list(self.conflicts),
            "candidate_confidence": self.candidate_confidence,
            "candidate_signals": dict(self.candidate_signals),
        }


@dataclass
class QAPair:
    """Q&A without options (spec §10.1-10.2). Question + answer, NO
    options — the extractor must NEVER fabricate 4 options for
    these."""

    number: int | None
    question: str
    answer: str
    page: int = 0
    paper: str = "Paper 1"
    format: str = "qa_pair"

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "question": self.question,
            "answer": self.answer,
            "page": self.page,
            "paper": self.paper,
            "format": self.format,
        }


@dataclass
class PendingQuestion:
    text: str
    options: list[str]
    reason: str  # no-key-entry | unknown-key | option-marker-mismatch
    number: int | None = None
    paper: str = ""
    page: int = 0
    part: str = ""
    verification_status: str = "unverified"

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "options": list(self.options),
            "reason": self.reason,
            "number": self.number,
            "paper": self.paper,
            "page": self.page,
            "part": self.part,
            "verification_status": self.verification_status,
        }


@dataclass
class ParseResult:
    questions: list[ExtractedQuestion] = field(default_factory=list)
    qa_pairs: list[QAPair] = field(default_factory=list)
    pending: list[PendingQuestion] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    format_counts: dict = field(default_factory=dict)
    answer_sources: dict = field(default_factory=dict)
    key_sections_found: int = 0
    key_entries_applied: int = 0
    unmatched_key_entries: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    number_gaps: list[str] = field(default_factory=list)
    number_duplicates: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    noise_lines_filtered: int = 0
    five_option_normalised: int = 0

    @property
    def parsed(self) -> int:
        return len(self.questions)

    def to_dict(self) -> dict:
        return {
            "questions": [q.to_dict() for q in self.questions],
            "qa_pairs": [p.to_dict() for p in self.qa_pairs],
            "pending": [p.to_dict() for p in self.pending],
            "parsed": self.parsed,
            "skipped": list(self.skipped),
            "excluded": list(self.excluded),
            "format_counts": dict(self.format_counts),
            "answer_sources": dict(self.answer_sources),
            "key_sections_found": self.key_sections_found,
            "key_entries_applied": self.key_entries_applied,
            "unmatched_key_entries": list(self.unmatched_key_entries),
            "conflicts": list(self.conflicts),
            "number_gaps": list(self.number_gaps),
            "number_duplicates": list(self.number_duplicates),
            "notes": list(self.notes),
            "noise_lines_filtered": self.noise_lines_filtered,
            "five_option_normalised": self.five_option_normalised,
        }
