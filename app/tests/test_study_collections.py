# OfficerPath AI — B1/B2
# Named study collections: the shared bank documents grouped by
# the ``collection`` value in their metadata.
#
# Seed: one shared document per named collection (PPSC paper,
# Computer set with one MCQ + one Q+A card, Fact Book), plus a
# PRIVATE document carrying collection metadata and a shared
# document with NO collection metadata — both must stay out of
# the public list. Questions are inserted in the exact shape
# the verified-text import writes: MCQs with four options and
# a verified-explicit-key answer row; Q+A cards with no options,
# no answer row, and the answer text in ``explanation``.

import hashlib
import json
import uuid

import pytest

from app.db import models as db
from app.tests.conftest import USER_ADMIN, USER_B, auth_headers


def _seed_collection_doc(session, owner, title, collection, mcqs, qa_cards, is_shared=True):
    """One document + its questions. ``mcqs``: list of
    (number, text, options, correct_index). ``qa_cards``: list
    of (number, text, answer). Returns the document id."""
    doc_id = uuid.uuid4()
    doc = db.Document(
        id=doc_id,
        user_id=uuid.UUID(owner),
        title=title,
        storage_path="staging://test",
        file_type="txt",
        file_size_bytes=100,
        page_count=None,
        # One hash per document: the (user_id, content_hash) dedup
        # index rejects two documents sharing a hash.
        content_hash=hashlib.sha256(str(doc_id).encode()).hexdigest(),
        is_shared=is_shared,
        metadata_json={
            "collection": collection,
            "paper": title,
            "sections": {"General Knowledge": len(mcqs) + len(qa_cards)},
        }
        if collection
        else None,
    )
    session.add(doc)
    session.commit()
    for number, text, options, correct_index in mcqs:
        qid = uuid.uuid4()
        session.add(
            db.ExtractedQuestion(
                id=qid,
                document_id=doc_id,
                question_number=str(number),
                original_text=text,
                normalized_text=text,
                validation_status="answered",
                content_fingerprint=f"{doc_id}-{number}",
            )
        )
        session.flush()
        for position, option in enumerate(options):
            session.add(
                db.QuestionOption(
                    question_id=qid,
                    original_text=option,
                    normalized_text=option,
                    position=position,
                )
            )
        session.add(
            db.ExtractedAnswer(
                question_id=qid,
                document_id=doc_id,
                status="verified_explicit_key",
                resolved_label=chr(65 + correct_index),
                resolution_method="explicit-key",
                resolution_score=1.0,
            )
        )
    for number, text, answer in qa_cards:
        session.add(
            db.ExtractedQuestion(
                id=uuid.uuid4(),
                document_id=doc_id,
                question_number=str(number),
                original_text=text,
                normalized_text=text,
                explanation=answer,
                validation_status="unreviewed",
                content_fingerprint=f"{doc_id}-card-{number}",
            )
        )
    session.commit()
    return doc_id


@pytest.fixture()
def seeded_collections(engine_db):
    """Three named shared collections + two decoys (private doc
    with a collection name, shared doc with no collection)."""
    factory = engine_db
    session = factory()
    ppsc = _seed_collection_doc(
        session,
        USER_ADMIN,
        "PPSC Past Paper 2026 — Paper 246: JUNIOR CLERK (BS-11), 03.10.2026",
        "PPSC Past Paper 2026",
        [
            (
                1,
                "Which award were separate electorates granted?",
                ["Poona Pack", "Lucknow Pack", "Communal Award", "Nehru Report"],
                2,
            ),
            (
                2,
                "Who headed the Committee of Nehru Report?",
                ["Jawaharlal Nehru", "Mahatma Gadhi", "Motilal Nehru", "Shoaib Imam"],
                2,
            ),
        ],
        [],
    )
    miqc = _seed_collection_doc(
        session,
        USER_ADMIN,
        "Most Important Questions — Computer",
        "Most Important Questions — Computer",
        [
            (
                1,
                "The term 'Computer' is derived from?",
                ["Format", "Desktop", "Latin", "High level language"],
                2,
            ),
        ],
        [(2, "Who is the father of Computer?", "Charles Babbage")],
    )
    factbook = _seed_collection_doc(
        session,
        USER_ADMIN,
        "Fact Book for PMS and CSS 2027",
        "Fact Book for PMS and CSS 2027",
        [
            (
                1,
                "Pakistan's GDP growth in FY2025-26 was:",
                ["2.7%", "3.7%", "4.2%", "3.1%"],
                1,
            ),
        ],
        [],
    )
    private = _seed_collection_doc(
        session,
        USER_B,
        "PPSC Past Paper 2026 — Paper 999: SECRET, 03.10.2026",
        "PPSC Past Paper 2026",
        [
            (
                1,
                "A private question that must never leak.",
                ["A", "B", "C", "D"],
                0,
            ),
        ],
        [],
        is_shared=False,
    )
    _seed_collection_doc(
        session,
        USER_ADMIN,
        "Some other shared document",
        None,
        [
            (
                1,
                "A shared question with no collection.",
                ["A", "B", "C", "D"],
                0,
            ),
        ],
        [],
    )
    session.close()
    return {"ppsc": ppsc, "miqc": miqc, "factbook": factbook, "private": private}


def test_public_list_returns_named_collections_in_order(client, seeded_collections):
    """No auth needed; only shared documents carrying a
    collection name appear, in the user's display order."""
    res = client.get("/api/v1/study-collections")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 3
    names = [c["name"] for c in body["collections"]]
    assert names == [
        "PPSC Past Paper 2026",
        "Most Important Questions — Computer",
        "Fact Book for PMS and CSS 2027",
    ]
    slugs = [c["slug"] for c in body["collections"]]
    assert slugs == [
        "ppsc-past-paper-2026",
        "most-important-questions-computer",
        "fact-book-for-pms-and-css-2027",
    ]
    counts = {c["name"]: c["question_count"] for c in body["collections"]}
    assert counts == {
        "PPSC Past Paper 2026": 2,
        "Most Important Questions — Computer": 2,
        "Fact Book for PMS and CSS 2027": 1,
    }
    # Live bank total: every question in every shared document —
    # the named collections (5) plus the uncollected shared doc
    # (1). The private document's question is never counted.
    assert body["bank_total"] == 6
    ppsc_docs = body["collections"][0]["documents"]
    assert len(ppsc_docs) == 1
    assert "Paper 999" not in json.dumps(ppsc_docs)
    assert "Some other shared document" not in json.dumps(body)


def test_public_detail_and_unknown_slug(client, seeded_collections):
    res = client.get("/api/v1/study-collections/ppsc-past-paper-2026")
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "PPSC Past Paper 2026"
    assert body["document_count"] == 1
    assert body["documents"][0]["question_count"] == 2
    assert body["documents"][0]["title"].startswith("PPSC Past Paper 2026 — Paper 246")

    res = client.get("/api/v1/study-collections/no-such-collection")
    assert res.status_code == 404


def test_questions_require_login(client, seeded_collections):
    """The list is public; opening a paper's questions is not."""
    doc_id = seeded_collections["ppsc"]
    res = client.get(f"/api/v1/study-collections/ppsc-past-paper-2026/documents/{doc_id}/questions")
    assert res.status_code == 401


def test_questions_shared_document_for_any_student(client, seeded_collections):
    """A logged-in student (not the admin owner) reads the
    shared paper's questions in printed-number order, Q+A card
    included as a card, not an MCQ."""
    doc_id = seeded_collections["miqc"]
    res = client.get(
        f"/api/v1/study-collections/most-important-questions-computer/documents/{doc_id}/questions",
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    assert body["qa_pairs"] == 1
    mcq, card = body["questions"]
    assert mcq["kind"] == "mcq"
    assert mcq["options"] == ["Format", "Desktop", "Latin", "High level language"]
    assert mcq["correct_index"] == 2
    assert mcq["correct_letter"] == "C"
    assert card["kind"] == "qa_pair"
    assert card["options"] == []
    assert card["correct_index"] == -1
    assert card["explanation"] == "Charles Babbage"
    assert card["text"] == "Who is the father of Computer?"


def test_questions_pagination_and_private_document_404(client, seeded_collections):
    doc_id = seeded_collections["ppsc"]
    res = client.get(
        f"/api/v1/study-collections/ppsc-past-paper-2026/documents/{doc_id}/questions",
        params={"limit": 1, "offset": 1},
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    assert len(body["questions"]) == 1
    assert body["questions"][0]["number"] == "2"

    # A private document never leaks — 404 even for its owner,
    # and 404 under the wrong collection slug.
    private_id = seeded_collections["private"]
    res = client.get(
        f"/api/v1/study-collections/ppsc-past-paper-2026/documents/{private_id}/questions",
        headers=auth_headers("token-user-b"),
    )
    assert res.status_code == 404
    res = client.get(
        f"/api/v1/study-collections/fact-book-for-pms-and-css-2027/documents/{doc_id}/questions",
        headers=auth_headers("token-user-a"),
    )
    assert res.status_code == 404


def test_no_forbidden_names_in_responses(client, seeded_collections):
    """Neither source name may ever appear in the API surface."""
    res = client.get("/api/v1/study-collections")
    assert res.status_code == 200
    dumped = json.dumps(res.json())
    assert "Star Computer" not in dumped
    assert "ExamVeda" not in dumped
    res = client.get("/api/v1/study-collections/most-important-questions-computer")
    dumped = json.dumps(res.json())
    assert "Star Computer" not in dumped
    assert "ExamVeda" not in dumped
