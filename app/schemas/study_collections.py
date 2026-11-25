# OfficerPath AI — B1/B2
# Schemas for the named study collections.
#
# Truth rules baked into the shapes:
# - The list/detail payloads carry titles + counts only — never
#   question text, answers, or user data, so they are safe to
#   serve without auth (the Main Page and the public collections
#   list read them).
# - ``sections`` mirrors the import's metadata: a section name
#   maps to a question count (PPSC / Computer) or a question
#   range label (Fact Book "Q1–Q39") — both are plain display
#   strings/numbers, never invented.
# - Questions reuse ``DocumentQuestionsResponse`` (app/schemas/
#   questions.py): Q+A cards arrive with ``kind`` "qa_pair",
#   no options, and the answer in ``explanation``.

from __future__ import annotations

from pydantic import BaseModel


class StudyCollectionDocument(BaseModel):
    id: str
    title: str
    paper: str | None = None
    question_count: int
    sections: dict[str, int | str] = {}
    created_at: str | None = None


class StudyCollection(BaseModel):
    name: str
    slug: str
    question_count: int
    document_count: int
    documents: list[StudyCollectionDocument]


class StudyCollectionListResponse(BaseModel):
    collections: list[StudyCollection]
    total: int
    #: Live bank total: questions across ALL shared, non-deleted
    #: documents — not just the named collections — so the home
    #: page never hardcodes a count again. It grows with every
    #: import; the seed-bank import alone is not the bank.
    bank_total: int
