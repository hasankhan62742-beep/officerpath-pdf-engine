# OfficerPath AI — PDF Engine (M16)
# Community-contributed questions ("Add Questions").
#
# Flow under test: student submits (question + 4 options +
# correct answer + explanation + subject + source + paper) ->
# pending staging row -> admin approves (bank rows are minted
# under the shared community document, the question joins that
# subject's pool at once) or rejects with a note. Guards: field
# validation, 20/day cap, duplicate refusal (naming the paper
# the question already came from), and no email anywhere in
# any response — only the display name ("Submitted by Hasan").

import uuid

import pytest

from app.db import models as db
from app.services.community import fingerprint
from app.tests.conftest import USER_A, USER_ADMIN, USER_B, auth_headers

BANK_Q = "What is the chemical symbol for water?"
BANK_PAPER = "PPSC Tehsildar BS-16 2021"


@pytest.fixture()
def seeded_subjects(engine_db):
    """Everyday Science (with one topic) + General Knowledge,
    USER_A's profile (full name Hasan), and one bank question
    in General Knowledge from a known paper — the duplicate
    target."""
    factory = engine_db
    session = factory()
    eds = db.Subject(name="Everyday Science", slug="everyday-science")
    gk = db.Subject(name="General Knowledge", slug="general-knowledge")
    session.add_all([eds, gk])
    session.flush()
    topic = db.Topic(subject_id=eds.id, name="General Science", slug="general-science")
    session.add(topic)
    session.flush()
    session.add(
        db.StudentProfile(
            user_id=uuid.UUID(USER_A),
            full_name="Hasan",
            phone=None,
            preferred_exam=None,
            education_level=None,
        )
    )
    doc = db.Document(
        user_id=uuid.UUID(USER_ADMIN),
        title="General Knowledge Bank",
        storage_path="bank/gk",
        file_type="txt",
        file_size_bytes=0,
        is_shared=True,
    )
    session.add(doc)
    session.flush()
    question = db.ExtractedQuestion(
        document_id=doc.id,
        question_number=None,
        original_text=BANK_Q,
        normalized_text=BANK_Q,
        explanation=None,
        extraction_method="import",
        validation_status="manually_verified",
        content_fingerprint=fingerprint(BANK_Q),
        paper=BANK_PAPER,
    )
    session.add(question)
    session.flush()
    for position, text in enumerate(["H2O", "CO2", "O2", "N2"]):
        session.add(
            db.QuestionOption(
                question_id=question.id,
                original_label=chr(65 + position),
                normalized_label=chr(65 + position),
                original_text=text,
                normalized_text=text,
                position=position,
            )
        )
    session.add(
        db.ExtractedAnswer(
            question_id=question.id,
            document_id=doc.id,
            status="manually_verified",
            resolved_label="A",
            resolution_method="explicit_key",
        )
    )
    session.add(
        db.QuestionSubject(
            question_id=question.id,
            subject_id=gk.id,
            topic_id=None,
            assigned_by=uuid.UUID(USER_ADMIN),
            confidence="manual",
        )
    )
    session.commit()
    ids = {
        "eds": str(eds.id),
        "gk": str(gk.id),
        "topic": str(topic.id),
        "bank_q": str(question.id),
    }
    session.close()
    return ids


def _payload(seeded, **overrides):
    payload = {
        "question": "Which planet is known as the Red Planet?",
        "options": ["Venus", "Mars", "Jupiter", "Saturn"],
        "correct_index": 1,
        "explanation": "Mars looks red because of iron oxide on its surface.",
        "subject_id": seeded["eds"],
        "topic_id": seeded["topic"],
        "source": "PPSC past paper",
        "paper": "FIA Sub Inspector 2023",
    }
    payload.update(overrides)
    return payload


def _submit(client, payload, token="token-user-a"):
    return client.post("/api/v1/community/questions", json=payload, headers=auth_headers(token))


def _approve(client, submission_id, note=None):
    return client.patch(
        f"/api/v1/admin/community/questions/{submission_id}/review",
        json={"approved": True, "note": note},
        headers=auth_headers("token-admin"),
    )


# ---------------------------------------------------------------------------
# Submit: happy path + validation
# ---------------------------------------------------------------------------


def test_submit_returns_pending_with_display_name_and_paper(client, engine_db, seeded_subjects):
    res = _submit(client, _payload(seeded_subjects))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "pending"
    # Display name comes from the profile — never the email.
    assert body["contributor_name"] == "Hasan"
    assert "@" not in body["contributor_name"]
    mine = client.get("/api/v1/community/questions/mine", headers=auth_headers("token-user-a"))
    assert mine.status_code == 200, mine.text
    item = mine.json()["items"][0]
    assert item["question"] == "Which planet is known as the Red Planet?"
    assert item["options"] == ["Venus", "Mars", "Jupiter", "Saturn"]
    assert item["correct_index"] == 1
    assert item["correct_letter"] == "B"
    assert item["paper"] == "FIA Sub Inspector 2023"
    assert item["source"] == "PPSC past paper"
    assert item["subject"]["subject_name"] == "Everyday Science"
    assert item["subject"]["topic_name"] == "General Science"
    assert item["status"] == "pending"
    assert item["bank_question_id"] is None


@pytest.mark.parametrize(
    "overrides, why",
    [
        ({"options": ["Venus", "Mars", "Jupiter"]}, "three options"),
        (
            {"options": ["Venus", "Mars", "Mars", "Saturn"]},
            "duplicate options",
        ),
        ({"options": ["Venus", "", "Jupiter", "Saturn"]}, "empty option"),
        ({"correct_index": 4}, "correct option out of range"),
        ({"question": "   "}, "empty question"),
        ({"subject_id": str(uuid.uuid4())}, "unknown subject"),
    ],
)
def test_submit_validation_errors(client, engine_db, seeded_subjects, overrides, why):
    res = _submit(client, _payload(seeded_subjects, **overrides))
    assert res.status_code in (404, 422), (why, res.text)


def test_submit_topic_of_another_subject_is_refused(client, engine_db, seeded_subjects):
    # The topic belongs to Everyday Science; GK must not accept it.
    res = _submit(
        client,
        _payload(
            seeded_subjects,
            subject_id=seeded_subjects["gk"],
            topic_id=seeded_subjects["topic"],
        ),
    )
    assert res.status_code == 404, res.text


def test_submit_without_profile_falls_back_to_email_local_part(client, engine_db, seeded_subjects):
    # USER_B has no StudentProfile: "Submitted by" is the email
    # local part (a UUID in tests), never the full address.
    res = _submit(client, _payload(seeded_subjects), token="token-user-b")
    assert res.status_code == 201, res.text
    assert res.json()["contributor_name"] == USER_B
    assert "@example.com" not in res.text


# ---------------------------------------------------------------------------
# Duplicate refusal (names the paper)
# ---------------------------------------------------------------------------


def test_submit_duplicate_against_bank_names_the_paper(client, engine_db, seeded_subjects):
    res = _submit(
        client,
        _payload(
            seeded_subjects,
            question=BANK_Q,
            options=["H2O", "CO2", "O2", "N2"],
            correct_index=0,
            subject_id=seeded_subjects["gk"],
            topic_id=None,
            paper="Some Other Paper 2020",
        ),
    )
    assert res.status_code == 409, res.text
    # The refusal tells the contributor which paper already has it.
    assert BANK_PAPER in res.text
    assert "already in the General Knowledge bank" in res.text


def test_submit_duplicate_staging_row_is_refused(client, engine_db, seeded_subjects):
    assert _submit(client, _payload(seeded_subjects)).status_code == 201
    res = _submit(client, _payload(seeded_subjects))
    assert res.status_code == 409, res.text
    assert "already submitted" in res.text


def test_submit_without_paper_still_duplicate_checked(client, engine_db, seeded_subjects):
    assert _submit(client, _payload(seeded_subjects)).status_code == 201
    # Paper left empty: the check still runs on the question text.
    res = _submit(client, _payload(seeded_subjects, paper=None))
    assert res.status_code == 409, res.text


def test_submit_same_question_other_subject_is_allowed(client, engine_db, seeded_subjects):
    res = _submit(
        client,
        _payload(seeded_subjects, subject_id=seeded_subjects["gk"], topic_id=None),
    )
    assert res.status_code == 201, res.text


# ---------------------------------------------------------------------------
# Daily cap + ownership
# ---------------------------------------------------------------------------


def test_daily_cap_20_submissions(client, engine_db, seeded_subjects):
    for i in range(20):
        res = _submit(client, _payload(seeded_subjects, question=f"Question number {i}?"))
        assert res.status_code == 201, res.text
    res = _submit(client, _payload(seeded_subjects, question="Question number 20?"))
    assert res.status_code == 429, res.text


def test_mine_lists_only_own_submissions(client, engine_db, seeded_subjects):
    assert _submit(client, _payload(seeded_subjects)).status_code == 201
    mine_b = client.get("/api/v1/community/questions/mine", headers=auth_headers("token-user-b"))
    assert mine_b.status_code == 200, mine_b.text
    assert mine_b.json()["total"] == 0
    mine_a = client.get("/api/v1/community/questions/mine", headers=auth_headers("token-user-a"))
    assert mine_a.json()["total"] == 1


# ---------------------------------------------------------------------------
# Admin review queue
# ---------------------------------------------------------------------------


def test_admin_list_requires_admin(client, engine_db, seeded_subjects):
    assert _submit(client, _payload(seeded_subjects)).status_code == 201
    res = client.get("/api/v1/admin/community/questions", headers=auth_headers("token-user-a"))
    assert res.status_code == 404, res.text
    res = client.get("/api/v1/admin/community/questions", headers=auth_headers("token-admin"))
    assert res.status_code == 200, res.text
    item = res.json()["items"][0]
    assert item["status"] == "pending"
    assert item["paper"] == "FIA Sub Inspector 2023"
    assert item["contributor_name"] == "Hasan"
    assert "@example.com" not in res.text


def test_approve_mints_bank_rows_and_joins_the_pool(client, engine_db, seeded_subjects):
    # Everyday Science pool is empty before approval.
    avail = client.get(
        "/api/v1/tests/availability",
        params={"source_type": "subjects", "subject_ids": [seeded_subjects["eds"]]},
        headers=auth_headers("token-user-a"),
    )
    assert avail.json()["available"] == 0
    submission = _submit(client, _payload(seeded_subjects)).json()
    res = _approve(client, submission["id"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "approved"
    bank_qid = body["bank_question_id"]
    assert bank_qid is not None
    # The question is in the subject pool at once.
    avail = client.get(
        "/api/v1/tests/availability",
        params={"source_type": "subjects", "subject_ids": [seeded_subjects["eds"]]},
        headers=auth_headers("token-user-a"),
    )
    assert avail.json()["available"] == 1
    # Reading mode shows it with its attribution + paper.
    reading = client.get(
        "/api/v1/tests/sections/questions",
        params={"topic_ids": [seeded_subjects["topic"]], "limit": 20, "offset": 0},
        headers=auth_headers("token-user-a"),
    )
    assert reading.status_code == 200, reading.text
    assert reading.json()["total"] == 1
    shown = reading.json()["questions"][0]
    assert shown["question_id"] == bank_qid
    assert shown["text"] == "Which planet is known as the Red Planet?"
    assert shown["correct_index"] == 1
    assert shown["explanation"] == "Mars looks red because of iron oxide on its surface."
    assert shown["submitted_by"] == "Hasan"
    assert shown["paper"] == "FIA Sub Inspector 2023"
    # A test can be built from it.
    created = client.post(
        "/api/v1/tests",
        json={
            "name": "Community Practice",
            "question_count": 1,
            "source_type": "subjects",
            "source_ids": [seeded_subjects["eds"]],
        },
        headers=auth_headers("token-user-a"),
    )
    assert created.status_code == 201, created.text
    assert created.json()["snapshots"][0]["question_id"] == bank_qid
    # Both approvals share the one community document.
    session = engine_db()
    doc_ids = {
        row.document_id
        for row in session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.contributor_name == "Hasan")
        .all()
    }
    assert len(doc_ids) == 1
    doc = session.query(db.Document).filter(db.Document.id == list(doc_ids)[0]).first()
    assert doc.is_shared is True
    assert (doc.metadata_json or {}).get("import_kind") == "community-questions"
    session.close()


def test_reject_records_note_and_stays_out_of_bank(client, engine_db, seeded_subjects):
    submission = _submit(client, _payload(seeded_subjects)).json()
    res = client.patch(
        f"/api/v1/admin/community/questions/{submission['id']}/review",
        json={"approved": False, "note": "Answer is wrong: Mars is not a star."},
        headers=auth_headers("token-admin"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "rejected"
    assert res.json()["review_note"] == "Answer is wrong: Mars is not a star."
    assert res.json()["bank_question_id"] is None
    avail = client.get(
        "/api/v1/tests/availability",
        params={"source_type": "subjects", "subject_ids": [seeded_subjects["eds"]]},
        headers=auth_headers("token-user-a"),
    )
    assert avail.json()["available"] == 0
    mine = client.get("/api/v1/community/questions/mine", headers=auth_headers("token-user-a"))
    assert mine.json()["items"][0]["status"] == "rejected"
    assert mine.json()["items"][0]["review_note"] == "Answer is wrong: Mars is not a star."


def test_double_review_is_refused(client, engine_db, seeded_subjects):
    submission = _submit(client, _payload(seeded_subjects)).json()
    assert _approve(client, submission["id"]).status_code == 200
    res = _approve(client, submission["id"])
    assert res.status_code == 409, res.text
    # One approval minted exactly one bank question.
    session = engine_db()
    count = (
        session.query(db.ExtractedQuestion)
        .filter(db.ExtractedQuestion.community_question_id == uuid.UUID(submission["id"]))
        .count()
    )
    session.close()
    assert count == 1


def test_review_unknown_submission_is_404(client, engine_db, seeded_subjects):
    res = _approve(client, str(uuid.uuid4()))
    assert res.status_code == 404, res.text
