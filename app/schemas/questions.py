# OfficerPath AI — PDF Engine (Phase 2, M5)
# Schemas for the question bank + results reads (GAP-3) and
# subjects (GAP-4).
#
# Truth rules baked into the shapes:
# - ``correct_index`` is -1 when the engine does not know the
#   answer; the frontend renders that as UNKNOWN, never as a
#   correct option.
# - ``confidence`` is null when there is no answer row — never a
#   made-up number.
# - ``inferred`` and ``corrected`` are explicit flags; an
#   inferred answer is never shown as verified.
# - ``answer_status`` is one of verified / detected / unknown /
#   needs_review / conflicting (the M5 display labels).
# - Q&A pairs have no options by design (``kind`` "qa_pair",
#   ``options`` []) and are never padded to four options.

from __future__ import annotations

from pydantic import BaseModel


class EvidenceItem(BaseModel):
    detector: str
    source_type: str
    value_normalized: str | None
    page_number: int | None
    detector_confidence: float | None
    artifact_ref: str | None


class SubjectAssignment(BaseModel):
    subject_id: str
    subject_name: str
    subject_slug: str
    topic_id: str | None
    topic_name: str | None


class QuestionItem(BaseModel):
    question_id: str
    document_id: str
    document_title: str
    number: str | None
    text: str
    options: list[str]
    kind: str  # mcq | qa_pair
    correct_index: int  # -1 = UNKNOWN, never guessed
    correct_letter: str
    answer_source: str
    # Stored verbatim explanation (M10); None when the source
    # gave none — never invented.
    explanation: str | None = None
    # M16: community attribution, copied onto the bank row on
    # approval. None for every parsed/imported question. The UI
    # shows "Submitted by ..." and "Paper: ..." when present.
    submitted_by: str | None = None
    paper: str | None = None
    confidence: float | None
    verified: bool
    inferred: bool
    corrected: bool
    status: str  # answered | unknown | pending | conflict-resolved
    answer_status: str  # verified | detected | unknown | needs_review | conflicting
    page: int | None
    subjects: list[SubjectAssignment]
    created_at: str | None


class QuestionListResponse(BaseModel):
    questions: list[QuestionItem]
    total: int
    limit: int
    offset: int


class CorrectionItem(BaseModel):
    id: str
    field_name: str
    old_value: str | None
    new_value: str | None
    reason: str | None
    created_at: str | None


class CorrectionListResponse(BaseModel):
    question_id: str
    corrections: list[CorrectionItem]
    total: int


class QuestionDetailResponse(QuestionItem):
    evidence: list[EvidenceItem]
    corrections: list[CorrectionItem]


class DocumentQuestionsResponse(BaseModel):
    document_id: str
    questions: list[QuestionItem]
    total: int
    limit: int
    offset: int
    counts: dict
    qa_pairs: int


class SubjectTopic(BaseModel):
    id: str
    name: str
    slug: str


class SubjectItem(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None
    topics: list[SubjectTopic]


class SubjectListResponse(BaseModel):
    subjects: list[SubjectItem]
    total: int


class AssignSubjectRequest(BaseModel):
    subject_id: str
    topic_id: str | None = None


class AssignSubjectResponse(BaseModel):
    question_id: str
    subject_id: str
    subject_name: str
    subject_slug: str
    topic_id: str | None
    topic_name: str | None
    already_assigned: bool = False
