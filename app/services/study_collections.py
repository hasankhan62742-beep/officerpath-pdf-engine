# OfficerPath AI — B1/B2
# Named study collections (PPSC Past Paper 2026, Most Important
# Questions — Computer, Fact Book for PMS and CSS 2027).
#
# A collection is a set of admin-shared documents grouped by the
# ``collection`` value the verified-text import stored in
# ``documents.metadata`` — no new table, no migration. The tabs
# the Main Page shows are derived from that metadata, so a future
# import carrying a new collection name appears automatically.
#
# Reads only. The list/detail reads are public (titles + counts
# only — never question text, answers, or user data); the
# questions read is auth-gated and 404s for any document that is
# not shared, exactly like every other owner check in the app.
# Q+A cards (no options, answer in ``explanation``) are included
# in the questions read — unlike the test pool, which excludes
# them — so Read mode can show them as Q+A cards (decision #4).

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models as db
from app.services import questions as question_service

#: Display order of the named collections the user asked for
#: (naming decisions 2026-11-25/26). Any other collection a
#: future import adds sorts after these, alphabetically — so
#: the tabs stay stable while new collections still appear.
COLLECTION_ORDER = (
    "PPSC Past Paper 2026",
    "Most Important Questions — Computer",
    "Fact Book for PMS and CSS 2027",
)


def slugify_collection(name: str) -> str:
    """Same slug rule the import script uses for topic slugs:
    lowercase, runs of non-alphanumerics become one dash."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "collection"


def _not_found(what: str = "Collection not found.") -> ApiError:
    return ApiError(status_code=404, code="not_found", message=what)


def _parse_uuid(value: str, what: str = "Document not found.") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise _not_found(what) from None


def _collection_of(document: db.Document) -> str | None:
    """The collection name a document belongs to, if any."""
    metadata = document.metadata_json or {}
    name = metadata.get("collection")
    return name if isinstance(name, str) and name.strip() else None


def _sections_of(document: db.Document) -> dict[str, int | str]:
    metadata = document.metadata_json or {}
    sections = metadata.get("sections")
    if not isinstance(sections, dict):
        return {}
    return {str(k): v for k, v in sections.items() if isinstance(v, (int, str))}


def _sort_key(collection: dict) -> tuple[int, str]:
    name = collection["name"]
    if name in COLLECTION_ORDER:
        return (COLLECTION_ORDER.index(name), "")
    return (len(COLLECTION_ORDER), name)


def list_study_collections(session: Session) -> dict:
    """Every named collection among the shared documents, with
    its documents and question counts. Public data only."""
    documents = (
        session.query(db.Document)
        .filter(db.Document.is_shared.is_(True))
        .filter(db.Document.deleted_at.is_(None))
        .order_by(db.Document.created_at)
        .all()
    )
    counts: dict[uuid.UUID, int] = {}
    for doc_id, count in (
        session.query(
            db.ExtractedQuestion.document_id,
            func.count(db.ExtractedQuestion.id),
        )
        .group_by(db.ExtractedQuestion.document_id)
        .all()
    ):
        counts[doc_id] = count
    grouped: dict[str, list[dict]] = {}
    for document in documents:
        name = _collection_of(document)
        if name is None:
            continue
        metadata = document.metadata_json or {}
        grouped.setdefault(name, []).append(
            {
                "id": str(document.id),
                "title": document.title,
                "paper": metadata.get("paper") if isinstance(metadata.get("paper"), str) else None,
                "question_count": counts.get(document.id, 0),
                "sections": _sections_of(document),
                "created_at": document.created_at.isoformat() if document.created_at else None,
            }
        )
    collections = [
        {
            "name": name,
            "slug": slugify_collection(name),
            "question_count": sum(d["question_count"] for d in docs),
            "document_count": len(docs),
            "documents": docs,
        }
        for name, docs in grouped.items()
    ]
    collections.sort(key=_sort_key)
    # Live bank total: every question in every shared,
    # non-deleted document — the named collections are only a
    # part of the bank (seed bank + community + imports). The
    # home page reads this instead of hardcoding a count.
    bank_total = sum(counts.get(document.id, 0) for document in documents)
    return {"collections": collections, "total": len(collections), "bank_total": bank_total}


def get_study_collection(session: Session, slug: str) -> dict:
    """One collection by slug. 404 for an unknown slug."""
    collections: list[dict[str, Any]] = list_study_collections(session)["collections"]
    for collection in collections:
        if collection["slug"] == slug:
            return collection
    raise _not_found()


def list_shared_document_questions(
    session: Session,
    slug: str,
    document_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """One shared document's questions in printed-number order,
    including Q+A cards (``kind`` "qa_pair", answer in
    ``explanation``). 404 unless the document is shared, live,
    and belongs to the requested collection — a private document
    never leaks through this read."""
    document = (
        session.query(db.Document)
        .filter(db.Document.id == _parse_uuid(document_id))
        .filter(db.Document.is_shared.is_(True))
        .filter(db.Document.deleted_at.is_(None))
        .first()
    )
    if document is None or _collection_of(document) is None:
        raise _not_found("Document not found.")
    if slugify_collection(_collection_of(document) or "") != slug:
        raise _not_found("Document not found.")
    # Same paginated core as the owner's document-questions read
    # (SQL pagination + SQL counts) — never a second full-load
    # copy of it. The shared check above is the only difference.
    return question_service._list_questions_for_document(
        session, document, limit=limit, offset=offset
    )
