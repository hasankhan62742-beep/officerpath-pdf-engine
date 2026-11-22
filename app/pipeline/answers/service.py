# OfficerPath AI — PDF Engine (Phase 1, M5)
# Document-level answer resolution: gather every detector's
# evidence for every question (including the M4 extractor's own
# inline resolution, carried in as evidence — never re-decided
# behind its back) and resolve each question under the standing
# precedence with ``precedence.resolve_answer``.
#
# Rules:
# - The M4 extractor's answer (answer-line / key / tick / bold /
#   asterisk, stored on the question) enters as evidence at its
#   M5 rank; an M5 detector can only overturn it when it fires at
#   a HIGHER precedence rank. A lower-rank detector disagreeing is
#   a logged conflict, never a silent overwrite.
# - Pending questions (no answer yet) resolve from M5 evidences
#   only; when nothing fires they stay UNKNOWN.
# - Q&A pairs resolve on their inline text answer only.
# - ``apply_resolution`` writes the verdict back onto the
#   ParseResult (correct_index / answer_source / confidence /
#   conflicts) and returns the count of questions whose answer
#   changed. An UNKNOWN verdict never clears an existing answer:
#   the question keeps the M4 answer and the verdict records the
#   disagreement as a note.

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from app.pipeline.answers.models import AnswerEvidence, ResolvedAnswer, section_key
from app.pipeline.answers.precedence import resolve_answer
from app.pipeline.extract.models import (
    ExtractedQuestion,
    ParseResult,
    PendingQuestion,
    QAPair,
)

#: M4 extractor answer_source -> M5 detector name.
M4_SOURCE_TO_DETECTOR: dict[str, str] = {
    "answer-line": "inline",
    "key": "trailing-key",
    "tick": "style-bold",
    "bold": "style-bold",
    "asterisk": "style-star",
    "flashcard": "inline",
}


@dataclass
class AnswerResolution:
    """The resolved answers for one document."""

    resolved: list[ResolvedAnswer] = field(default_factory=list)
    qa_resolved: list[ResolvedAnswer] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def answered(self) -> int:
        return sum(1 for r in self.resolved if r.status == "answered")

    @property
    def unknown(self) -> int:
        return sum(1 for r in self.resolved if r.status == "unknown")

    def to_dict(self) -> dict:
        return {
            "resolved": [r.to_dict() for r in self.resolved],
            "qa_resolved": [r.to_dict() for r in self.qa_resolved],
            "conflicts": list(self.conflicts),
            "notes": list(self.notes),
            "answered": self.answered,
            "unknown": self.unknown,
        }


def _m4_evidence(
    question: ExtractedQuestion | PendingQuestion | QAPair,
) -> AnswerEvidence | None:
    """The M4 extractor's own answer, as M5 evidence (or None
    when the extractor left the question unanswered). It is the
    question's OWN answer, so it always carries the question's
    section."""
    source = getattr(question, "answer_source", "") or ""
    detector = M4_SOURCE_TO_DETECTOR.get(source)
    if detector is None:
        return None
    correct_index = getattr(question, "correct_index", -1)
    if correct_index is None or correct_index < 0:
        return None
    return AnswerEvidence(
        detector=detector,
        question_number=getattr(question, "number", None),
        correct_index=correct_index,
        confidence=float(getattr(question, "confidence", 0.0) or 0.0),
        evidence=f"M4 extractor answer ({source}) -> ({chr(65 + correct_index)})",
        detail={"from": "m4-extractor"},
        section=section_key(question),
    )


def _join_evidences(
    question: ExtractedQuestion | PendingQuestion | QAPair,
    extra_by_number: dict[int | None, list[AnswerEvidence]],
    unambiguous_numbers: set[int | None],
    skipped: list[str],
) -> list[AnswerEvidence]:
    """The extra evidences that may join ``question`` (section-aware,
    M7).

    - An evidence stamped with a section joins ONLY a question in
      that section. This is the M6 residual fix: one key evidence
      per number used to attach to every same-numbered question in
      every section.
    - An unsectioned evidence (detector did not know the section)
      joins only when the number is unambiguous — it occurs in
      exactly one section of this document. When the number is
      ambiguous the evidence is skipped and the skip is recorded
      (never silently attached to the wrong section, never guessed).
    """
    evidences: list[AnswerEvidence] = []
    m4 = _m4_evidence(question)
    if m4 is not None:
        evidences.append(m4)
    q_section = section_key(question)
    number = getattr(question, "number", None)
    for evidence in extra_by_number.get(number, []):
        if evidence.section:
            if evidence.section == q_section:
                evidences.append(evidence)
            # else: another section's evidence — never attach.
        elif number in unambiguous_numbers:
            evidences.append(evidence)
        else:
            skipped.append(
                f"unsectioned {evidence.detector} evidence for Q{number} "
                f"skipped: number occurs in more than one section"
            )
    return evidences


def resolve_document_answers(
    result: ParseResult,
    extra_evidences: list[AnswerEvidence] | None = None,
) -> AnswerResolution:
    """Resolve every question (answered + pending) and every Q&A
    pair in a ParseResult. ``extra_evidences`` are M5 detector
    outputs (key/inline/style/visual/manual/inferred) keyed by
    question_number; they join the M4 evidence for that question
    and the precedence resolver decides.

    The join is SECTION-AWARE (M7): see ``_join_evidences``. A
    number that occurs in more than one section only takes
    evidences stamped with its own section; unsectioned evidences
    for such a number are skipped with a recorded note."""
    by_number: dict[int | None, list[AnswerEvidence]] = {}
    for evidence in extra_evidences or []:
        by_number.setdefault(evidence.question_number, []).append(evidence)

    # A number is unambiguous when every question carrying it is
    # in one section. Computed once per document.
    sections_by_number: dict[int | None, set[str]] = {}
    for question in list(result.questions) + list(result.pending):
        sections_by_number.setdefault(getattr(question, "number", None), set()).add(
            section_key(question)
        )
    unambiguous_numbers = {
        number for number, sections in sections_by_number.items() if len(sections) == 1
    }

    resolution = AnswerResolution()
    skipped: list[str] = []
    for question in list(result.questions) + list(result.pending):
        evidences = _join_evidences(question, by_number, unambiguous_numbers, skipped)
        resolved = resolve_answer(evidences)
        # A pending question's number may be None; keep the text
        # for traceability in the note, not in the model.
        resolution.resolved.append(resolved)
        resolution.conflicts.extend(resolved.conflicts)
    for pair in result.qa_pairs:
        evidences = _join_evidences(pair, by_number, unambiguous_numbers, skipped)
        text_evidence = AnswerEvidence(
            detector="inline",
            question_number=pair.number,
            correct_index=-1,
            confidence=1.0,
            evidence=f"inline Q&A answer text: {pair.answer[:60]!r}",
            answer_text=pair.answer,
            detail={"from": "m4-extractor-qa-pair"},
            section=section_key(pair),
        )
        evidences.append(text_evidence)
        resolution.qa_resolved.append(resolve_answer(evidences))
    # De-duplicate the skip notes (the same ambiguous number is
    # skipped once per question carrying it).
    resolution.notes.extend(sorted(set(skipped)))
    return resolution


def apply_resolution(result: ParseResult, resolution: AnswerResolution) -> int:
    """Write resolved answers back onto the ParseResult's
    questions. Returns how many questions changed answer. An
    UNKNOWN verdict never clears an existing answer; a changed
    answer always carries its conflicts on the question."""
    changed = 0
    # Verdicts join to questions by number AND occurrence order.
    # Question numbers repeat across sections (TestPoint Sr#
    # restarts per section: 1375 rows, 476 unique numbers), so
    # "first verdict for number N" gave every Q5 the first
    # section's answer and clobbered the others' correct M4
    # answers (measured M6: end-to-end TestPoint answer accuracy
    # 0.5084 with the old join). The resolution list is in
    # document order, so the k-th question with number N takes
    # the k-th verdict for N. Unique numbers behave exactly as
    # before.
    by_number: dict[int | None, deque[ResolvedAnswer]] = {}
    for resolved in resolution.resolved:
        by_number.setdefault(resolved.question_number, deque()).append(resolved)
    for question in result.questions:
        queue = by_number.get(question.number)
        if not queue:
            continue
        verdict = queue.popleft()
        if verdict.correct_index == -1 and verdict.answer_text is None:
            continue  # UNKNOWN never clears an existing answer
        # A "change" is an answer change (index or text). A pure
        # source rename (M4 "key" vs M5 "trailing-key") for the
        # SAME answer is not a change — the answer stands.
        if verdict.correct_index != question.correct_index:
            question.correct_index = verdict.correct_index
            question.answer_source = verdict.source
            question.confidence = verdict.confidence
            question.verified = verdict.verified
            changed += 1
        if verdict.conflicts:
            for conflict in verdict.conflicts:
                if conflict not in question.conflicts:
                    question.conflicts.append(conflict)
            question.verified = False
    return changed
